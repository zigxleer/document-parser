import re
import urllib.error
import xml.etree.ElementTree as ET
import streamlit as st
import pandas as pd
import tempfile
import os
from parse_xml import parse_xml_to_csv
from compare_csvs import compare_csvs
from fetch_loda import get_token, fetch_loda, filter_by_section, collect_articles, html_to_text, clean, find_section_title


def run_irregularity_checks(df):
    # Coerce to string — XML parser may leave NaN floats in empty cells
    for col in ["Level 1 Header", "Level 2 Header", "Level 3 Header", "Sections", "Notes"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    issues = []

    # 1. No header
    no_header_rows = df.index[
        df["Level 1 Header"].str.strip().eq("") &
        df["Level 2 Header"].str.strip().eq("") &
        df["Level 3 Header"].str.strip().eq("")
    ].tolist()
    if no_header_rows:
        issues.append(f"**No header found** on {len(no_header_rows)} row(s): rows {no_header_rows}")

    # 2. No section number
    no_section_rows = df.index[df["Sections"].str.strip().eq("")].tolist()
    if no_section_rows:
        issues.append(f"**No section number** on {len(no_section_rows)} row(s): rows {no_section_rows}")

    # 3. No text
    no_text_rows = df.index[df["Notes"].str.strip().eq("")].tolist()
    if no_text_rows:
        issues.append(f"**No text** on {len(no_text_rows)} row(s): rows {no_text_rows}")

    # 4. Duplicate section numbers (excluding [continued])
    non_continued = df[~df["Notes"].str.startswith("[continued]")]
    dup_sections = non_continued[
        non_continued["Sections"].str.strip().ne("") &
        non_continued["Sections"].duplicated(keep=False)
    ]
    if not dup_sections.empty:
        dup_vals = dup_sections["Sections"].unique().tolist()
        issues.append(f"**Duplicate section numbers** (excluding [continued]): {dup_vals} — rows {dup_sections.index.tolist()}")

    # 5. Header hierarchy violations
    l1_blank = df["Level 1 Header"].str.strip().eq("")
    l2_blank = df["Level 2 Header"].str.strip().eq("")
    l2_filled = df["Level 2 Header"].str.strip().ne("")
    l3_filled = df["Level 3 Header"].str.strip().ne("")
    hier_rows = df.index[(l2_filled & l1_blank) | (l3_filled & l2_blank)].tolist()
    if hier_rows:
        issues.append(f"**Header hierarchy violation** (child header filled without parent) on {len(hier_rows)} row(s): rows {hier_rows}")

    # 7. HTML remnants in Notes
    html_rows = df.index[df["Notes"].str.contains(r'<[^>]+>', regex=True, na=False)].tolist()
    if html_rows:
        issues.append(f"**HTML remnants in Notes** on {len(html_rows)} row(s): rows {html_rows}")

    # 8. Orphaned [continued] rows
    orphaned_continued = []
    for idx in df.index:
        if df.at[idx, "Notes"].startswith("[continued]"):
            if idx == 0:
                orphaned_continued.append(idx)
            elif df.at[idx - 1, "Sections"] != df.at[idx, "Sections"]:
                orphaned_continued.append(idx)
    if orphaned_continued:
        issues.append(f"**Orphaned [continued] rows** (no matching preceding row with same section) on {len(orphaned_continued)} row(s): rows {orphaned_continued}")

    return issues


def show_irregularity_checks(df):
    issues = run_irregularity_checks(df)
    if issues:
        with st.expander(f"⚠️ {len(issues)} irregularity type(s) found", expanded=True):
            for issue in issues:
                st.warning(issue)
    else:
        st.info("✅ No irregularities found.")

# Set page configuration
st.set_page_config(
    page_title="Document Parser & Comparator",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Document Parser & Comparator")

# Create tabs
tab1, tab2 = st.tabs(["🔍 Parse Document", "📊 Compare CSVs"])

# Tab 1: Parse Document (XML or French Law)
with tab1:
    st.header("Parse Document to CSV")
    st.write("Parse Canadian XML documents or French law text IDs into structured CSV.")

    input_method = st.radio("Select input method:", ["Canadian XML URL", "French Law (Legifrance)"])

    xml_source = None
    loda_text_id = None
    loda_section_id = None

    if input_method == "Canadian XML URL":
        xml_url = st.text_input(
            "Enter Canadian XML URL:",
            value="https://laws-lois.justice.gc.ca/eng/XML/P-21.xml",
            help="Enter the full URL to the XML file"
        )
        if xml_url:
            xml_source = xml_url

    else:  # French Law
        loda_text_id = st.text_input(
            "Enter Legifrance Text ID:",
            value="JORFTEXT000000643230",
            help="LEGITEXT, JORFTEXT, or LEGISCTA identifier"
        )
        loda_section_id = st.text_input(
            "Section ID (optional):",
            placeholder="e.g. LEGISCTA000018488409",
            help="Leave blank to fetch the entire text"
        )

    if st.button("Parse Document", type="primary"):
        if input_method == "French Law (Legifrance)":
            if loda_text_id:
                with st.spinner("Fetching from Legifrance API..."):
                    try:
                        token = get_token()
                        effective_section = loda_section_id.strip() or None
                        if loda_text_id.startswith("LEGISCTA"):
                            effective_section = loda_text_id.strip()
                        data = fetch_loda(token, loda_text_id.strip())
                        if effective_section:
                            data = filter_by_section(data, effective_section)

                        offset = 0
                        if effective_section:
                            sec_title = find_section_title(data.get("sections", []), effective_section)
                            if sec_title:
                                for art in collect_articles(data.get("sections", []), data.get("articles", [])):
                                    path = art.get("pathTitle") or []
                                    for i, title in enumerate(path):
                                        if title == sec_title:
                                            offset = i + 1
                                            break
                                    break

                        # Compute last amended date
                        if effective_section:
                            all_dates = [
                                art.get("modificatorDate")
                                for art in collect_articles(data.get("sections", []), data.get("articles", []))
                                if art.get("modificatorDate")
                            ]
                            last_amended = max(all_dates) if all_dates else ""
                        else:
                            last_amended = data.get("modifDate", "")

                        # Build base Legifrance URL for annex/table references
                        text_cid = data.get("cid") or loda_text_id.strip()
                        is_code_text = data.get("nature") == "CODE"
                        if is_code_text:
                            lf_url_base = f"https://www.legifrance.gouv.fr/codes/section_lc/{text_cid}"
                        else:
                            lf_url_base = f"https://www.legifrance.gouv.fr/loda/id/{text_cid}"

                        rows = []
                        for art in collect_articles(data.get("sections", []), data.get("articles", [])):
                            path = (art.get("pathTitle") or [])[offset:]
                            num = art.get("num") or ""
                            is_annex = num.lower().startswith("annexe")

                            # Article-specific URL (codes need section ID)
                            if is_code_text:
                                sec_id = effective_section or next(iter(re.findall(r'LEGISCTA\w+', art.get("path", ""))), None)
                                lf_url = f"{lf_url_base}/{sec_id}" if sec_id else lf_url_base
                            else:
                                lf_url = lf_url_base

                            if is_annex:
                                annex_subtitle = clean(path[-1]) if len(path) >= 2 else ""
                                l1 = f"{clean(num)} ({annex_subtitle})" if annex_subtitle else clean(num)
                                l2 = ""
                                l3 = ""
                            else:
                                article_label = f"Article {num}" if num else ""
                                l1 = clean(path[0]) if len(path) > 0 else ""
                                l2 = clean(path[1]) if len(path) > 1 else ""
                                l3 = clean(path[2]) if len(path) > 2 else ""
                                # Insert article label at the next level after the path
                                if article_label:
                                    if len(path) == 0:
                                        l1 = article_label
                                    elif len(path) == 1:
                                        l2 = article_label
                                    else:
                                        l3 = article_label

                            # Inject table reference message before each <table> in HTML (not for annexes)
                            content_html = art.get("content", "")
                            if not is_annex and re.search(r'<table', content_html, re.IGNORECASE):
                                table_msg = f"[To consult the table, please visit: {lf_url}] "
                                content_html = re.sub(r'<table', table_msg + "<table", content_html, flags=re.IGNORECASE)
                            notes = html_to_text(content_html)
                            nota = html_to_text(art.get("nota", ""))
                            if nota:
                                notes = f"{notes}\n{nota}" if notes else nota

                            # Prepend annex reference message (before chunking so it leads the first chunk)
                            if is_annex:
                                notes = f"[To consult this schedule, please visit: {lf_url}]\n{notes}"
                            if is_annex:
                                annex_num = num[len("Annexe"):].strip() if num.lower().startswith("annexe") else num
                                section_val = f"s.ann. {annex_num}" if annex_num else "s.ann."
                            elif num:
                                section_val = f"s.{num}"
                            elif path and clean(path[0]).lower().startswith("annexe"):
                                annex_num = clean(path[0])[len("Annexe"):].strip() if clean(path[0]).lower().startswith("annexe") else clean(path[0])
                                section_val = f"s.ann. {annex_num}" if annex_num else "s.ann."
                            else:
                                section_val = ""
                            # Detect Roman numeral subsections (I., II., III. at line start)
                            roman_matches = (
                                list(re.finditer(r'(?m)^\s*([IVXLCDM]+)\.\s*[-–]', notes))
                                if not is_annex and section_val else []
                            )
                            if roman_matches:
                                sub_parts = []
                                preamble = notes[:roman_matches[0].start()].strip()
                                if preamble:
                                    sub_parts.append((None, preamble))
                                for i, m in enumerate(roman_matches):
                                    roman = m.group(1)
                                    end = roman_matches[i + 1].start() if i + 1 < len(roman_matches) else len(notes)
                                    sub_parts.append((roman, notes[m.start():end].strip()))
                            else:
                                sub_parts = [(None, notes)]

                            for roman_label, sub_notes in sub_parts:
                                sub_section_val = f"{section_val} {roman_label}" if roman_label else section_val
                                # Prepend section number (without "s.") to the start of notes
                                section_num = sub_section_val[2:] if sub_section_val.startswith("s.") else sub_section_val
                                text_with_prefix = f"{section_num} {sub_notes}" if section_num else sub_notes
                                chunk_size = 50000
                                chunks = []
                                remaining = text_with_prefix
                                while remaining:
                                    if len(remaining) <= chunk_size:
                                        chunks.append(remaining)
                                        break
                                    split_at = remaining.rfind(' ', 0, chunk_size)
                                    if split_at == -1:
                                        split_at = chunk_size
                                    chunks.append(remaining[:split_at])
                                    remaining = remaining[split_at:].lstrip()
                                for i, chunk in enumerate(chunks):
                                    rows.append({
                                        "Level 1 Header": l1,
                                        "Level 2 Header": l2,
                                        "Level 3 Header": l3,
                                        "Sections": sub_section_val,
                                        "Notes": chunk if i == 0 else f"[continued] {chunk}",
                                    })

                        if rows:
                            df = pd.DataFrame(rows)
                            st.success(f"✅ Successfully fetched {len(df)} articles!")

                            st.subheader("Document Metadata")
                            loda_metadata_df = pd.DataFrame([
                                {"Field": "Name", "Value": f"Imported automatically. Last amended {last_amended}" if last_amended else "Imported automatically"},
                                {"Field": "Coming into force date", "Value": last_amended or "N/A"},
                            ])
                            st.dataframe(loda_metadata_df, hide_index=True, use_container_width=False)

                            show_irregularity_checks(df)

                            st.subheader("Parsed Data Preview")
                            st.dataframe(df, use_container_width=True, height=400)
                            csv_data = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                            st.download_button(
                                label="⬇️ Download CSV",
                                data=csv_data,
                                file_name=f"{loda_text_id}_loda.csv",
                                mime="text/csv"
                            )
                        else:
                            st.warning("⚠️ No digitized articles found for this text ID.")
                    except Exception as e:
                        st.error(f"❌ Error fetching from Legifrance: {str(e)}")
            else:
                st.warning("⚠️ Please enter a Legifrance Text ID")

        elif xml_source:
            xml_url_stripped = xml_source.strip()
            if not xml_url_stripped.lower().startswith("http"):
                st.error("❌ URL must start with http:// or https://")
            elif not xml_url_stripped.lower().endswith(".xml"):
                st.error("❌ URL must point to an .xml file")
            else:
                output_path = None
                with st.spinner("Parsing XML..."):
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w') as tmp_output:
                            output_path = tmp_output.name

                        metadata = parse_xml_to_csv(xml_url_stripped, output_path)
                        df = pd.read_csv(output_path)

                        if df.empty:
                            st.warning("⚠️ The XML was fetched but no rows were parsed. The document may be empty or in an unsupported format.")
                        else:
                            st.success(f"✅ Successfully parsed {len(df)} rows from XML!")

                            st.subheader("Document Metadata")
                            metadata_df = pd.DataFrame([
                                {"Field": "Name", "Value": metadata.get('name', 'N/A')},
                                {"Field": "Coming into force date", "Value": metadata.get('coming_into_force_date', 'N/A')}
                            ])
                            st.dataframe(metadata_df, hide_index=True, use_container_width=False)

                            show_irregularity_checks(df)

                            st.subheader("Parsed Data Preview")
                            st.dataframe(df, use_container_width=True, height=400)

                            csv_data = df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label="⬇️ Download CSV",
                                data=csv_data,
                                file_name="parsed_output.csv",
                                mime="text/csv"
                            )

                    except urllib.error.HTTPError as e:
                        st.error(f"❌ HTTP error fetching XML: {e.code} {e.reason}")
                    except urllib.error.URLError as e:
                        st.error(f"❌ Network error fetching XML: {e.reason}")
                    except ET.ParseError as e:
                        st.error(f"❌ XML parse error — the document may not be valid XML: {e}")
                    except Exception as e:
                        st.error(f"❌ Error parsing XML: {e}")
                    finally:
                        if output_path and os.path.exists(output_path):
                            os.unlink(output_path)
        else:
            st.warning("⚠️ Please provide an input source")

# Tab 2: Compare CSVs
with tab2:
    st.header("Compare CSV Files")
    st.write("Compare two versions of parsed documents and identify changes.")

    # Initialize session state for comparison results
    if 'comparison_df' not in st.session_state:
        st.session_state.comparison_df = None

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📁 Old Version")
        old_csv = st.file_uploader("Upload old CSV file", type=['csv'], key="old")

    with col2:
        st.subheader("📁 New Version")
        new_csv = st.file_uploader("Upload new CSV file", type=['csv'], key="new")

    # Compare button
    if st.button("Compare CSVs", type="primary"):
        if old_csv is not None and new_csv is not None:
            with st.spinner("Comparing CSV files..."):
                try:
                    # Save uploaded files to temporary locations
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_old:
                        tmp_old.write(old_csv.read())
                        old_path = tmp_old.name

                    with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_new:
                        tmp_new.write(new_csv.read())
                        new_path = tmp_new.name

                    # Create temporary output file
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_output:
                        output_path = tmp_output.name

                    # Compare CSVs
                    compare_csvs(old_path, new_path, output_path)

                    # Read the resulting CSV and store in session state
                    st.session_state.comparison_df = pd.read_csv(output_path)

                    # Clean up temporary files
                    for path in [old_path, new_path, output_path]:
                        if os.path.exists(path):
                            os.unlink(path)

                    st.success("✅ Comparison complete!")

                except Exception as e:
                    st.error(f"❌ Error comparing CSVs: {str(e)}")
                    st.session_state.comparison_df = None
        else:
            st.warning("⚠️ Please upload both old and new CSV files")

    # Display results if comparison has been done
    if st.session_state.comparison_df is not None:
        df = st.session_state.comparison_df

        # Display summary statistics
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            same_count = len(df[df['Change Type'] == 'Same'])
            st.metric("Same", same_count, delta=None)
        with col2:
            minor_count = len(df[df['Change Type'] == 'Same (Minor Edit)'])
            st.metric("Minor Edit", minor_count, delta=None)
        with col3:
            updated_count = len(df[df['Change Type'] == 'Updated'])
            st.metric("Updated", updated_count, delta=None)
        with col4:
            new_count = len(df[df['Change Type'] == 'New'])
            st.metric("New", new_count, delta=None)
        with col5:
            deleted_count = len(df[df['Change Type'] == 'Deleted'])
            st.metric("Deleted", deleted_count, delta=None)

        # Filter options
        st.subheader("Filter Results")
        filter_option = st.multiselect(
            "Show change types:",
            options=['Same', 'Same (Minor Edit)', 'Updated', 'New', 'Deleted'],
            default=['Same', 'Same (Minor Edit)', 'Updated', 'New', 'Deleted']
        )

        # Filter dataframe
        filtered_df = df[df['Change Type'].isin(filter_option)]

        # Display the dataframe with color coding
        st.subheader("Comparison Results")

        if len(filtered_df) > 0:
            # Apply styling based on Change Type
            def highlight_changes(row):
                if row['Change Type'] == 'Same':
                    return ['background-color: #d4edda'] * len(row)
                elif row['Change Type'] == 'Same (Minor Edit)':
                    return ['background-color: #e8f5e9'] * len(row)
                elif row['Change Type'] == 'Updated':
                    return ['background-color: #fff3cd'] * len(row)
                elif row['Change Type'] == 'New':
                    return ['background-color: #d1ecf1'] * len(row)
                elif row['Change Type'] == 'Deleted':
                    return ['background-color: #f8d7da'] * len(row)
                return [''] * len(row)

            styled_df = filtered_df.style.apply(highlight_changes, axis=1)
            st.dataframe(styled_df, use_container_width=True, height=400)
        else:
            st.info("No results match the selected filters.")

        # Legend
        st.markdown("""
        **Legend:**
        - 🟢 **Same**: No changes
        - 🌿 **Same (Minor Edit)**: Formatting or editorial change only
        - 🟡 **Updated**: Sections match but Notes changed substantively
        - 🔵 **New**: New clause added
        - 🔴 **Deleted**: Clause removed
        """)

        # Download button
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Download Comparison Results",
            data=csv_data,
            file_name="comparison_results.csv",
            mime="text/csv"
        )

# Sidebar with instructions
with st.sidebar:
    st.header("ℹ️ Instructions")

    st.subheader("Parse Document Tab")
    st.write("""
    **Canadian XML**
    1. Choose URL
    2. Provide XML URL
    3. Click 'Parse Document'

    **French Law (Legifrance)**
    1. Choose French Law (Legifrance)
    2. Enter a LEGITEXT, JORFTEXT, or LEGISCTA ID
    3. Optionally enter a Section ID
    4. Click 'Parse Document'
    """)

    st.subheader("Compare CSVs Tab")
    st.write("""
    1. Upload old version CSV
    2. Upload new version CSV
    3. Click 'Compare CSVs'
    4. Review changes with color coding
    5. Download comparison results
    """)

    st.subheader("Change Types")
    st.write("""
    - **Same**: Identical Sections & Notes
    - **Updated**: Same Sections, different Notes
    - **New**: Not in old file
    - **Deleted**: Not in new file
    """)

    st.divider()
    st.caption("Document Parser v1.0")
