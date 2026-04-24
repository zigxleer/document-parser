import streamlit as st
import pandas as pd
import tempfile
import os
from parse_xml import parse_xml_to_csv
from compare_csvs import compare_csvs
from fetch_loda import get_token, fetch_loda, filter_by_section, collect_articles, html_to_text, clean, find_section_title

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

                        rows = []
                        for art in collect_articles(data.get("sections", []), data.get("articles", [])):
                            path = (art.get("pathTitle") or [])[offset:]
                            rows.append({
                                "Level 1 Header": clean(path[0]) if len(path) > 0 else "",
                                "Level 2 Header": clean(path[1]) if len(path) > 1 else "",
                                "Level 3 Header": clean(path[2]) if len(path) > 2 else "",
                                "Section": f"s.{art.get('num')}" if art.get("num") else "",
                                "Notes": html_to_text(art.get("content", "")),
                            })

                        if rows:
                            df = pd.DataFrame(rows)
                            st.success(f"✅ Successfully fetched {len(df)} articles!")
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
            with st.spinner("Parsing XML..."):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w') as tmp_output:
                        output_path = tmp_output.name

                    metadata = parse_xml_to_csv(xml_source, output_path)
                    df = pd.read_csv(output_path)

                    st.success(f"✅ Successfully parsed {len(df)} rows from XML!")

                    st.subheader("Document Metadata")
                    metadata_df = pd.DataFrame([
                        {"Field": "Name", "Value": metadata.get('name', 'N/A')},
                        {"Field": "Coming into force date", "Value": metadata.get('coming_into_force_date', 'N/A')}
                    ])
                    st.dataframe(metadata_df, hide_index=True, use_container_width=False)

                    st.subheader("Parsed Data Preview")
                    st.dataframe(df, use_container_width=True, height=400)

                    csv_data = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="⬇️ Download CSV",
                        data=csv_data,
                        file_name="parsed_output.csv",
                        mime="text/csv"
                    )

                    if os.path.exists(output_path):
                        os.unlink(output_path)

                except Exception as e:
                    st.error(f"❌ Error parsing XML: {str(e)}")
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
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            same_count = len(df[df['Change Type'] == 'Same'])
            st.metric("Same", same_count, delta=None)
        with col2:
            updated_count = len(df[df['Change Type'] == 'Updated'])
            st.metric("Updated", updated_count, delta=None)
        with col3:
            new_count = len(df[df['Change Type'] == 'New'])
            st.metric("New", new_count, delta=None)
        with col4:
            deleted_count = len(df[df['Change Type'] == 'Deleted'])
            st.metric("Deleted", deleted_count, delta=None)

        # Filter options
        st.subheader("Filter Results")
        filter_option = st.multiselect(
            "Show change types:",
            options=['Same', 'Updated', 'New', 'Deleted'],
            default=['Same', 'Updated', 'New', 'Deleted']
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
        - 🟡 **Updated**: Sections match but Notes changed
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
