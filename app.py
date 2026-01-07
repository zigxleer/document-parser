import streamlit as st
import pandas as pd
import tempfile
import os
from parse_xml import parse_xml_to_csv
from compare_csvs import compare_csvs

# Set page configuration
st.set_page_config(
    page_title="Document Parser & Comparator",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Document Parser & Comparator")

# Create tabs
tab1, tab2 = st.tabs(["🔍 Parse XML", "📊 Compare CSVs"])

# Tab 1: Parse XML
with tab1:
    st.header("Parse XML to CSV")
    st.write("Parse documents from XML format (URL or file upload) into structured CSV.")

    # Input method selection
    input_method = st.radio("Select input method:", ["URL", "Upload File"])

    xml_source = None

    if input_method == "URL":
        xml_url = st.text_input(
            "Enter XML URL:",
            value="https://laws-lois.justice.gc.ca/eng/XML/P-21.xml",
            help="Enter the full URL to the XML file"
        )
        if xml_url:
            xml_source = xml_url
    else:
        uploaded_xml = st.file_uploader("Upload XML file", type=['xml'])
        if uploaded_xml is not None:
            # Save uploaded file to temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xml') as tmp_file:
                tmp_file.write(uploaded_xml.read())
                xml_source = tmp_file.name

    # Parse button
    if st.button("Parse XML", type="primary"):
        if xml_source:
            with st.spinner("Parsing XML..."):
                try:
                    # Create temporary output file
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w') as tmp_output:
                        output_path = tmp_output.name

                    # Parse XML to CSV
                    parse_xml_to_csv(xml_source, output_path)

                    # Read the resulting CSV
                    df = pd.read_csv(output_path)

                    st.success(f"✅ Successfully parsed {len(df)} rows from XML!")

                    # Display the dataframe
                    st.subheader("Parsed Data Preview")
                    st.dataframe(df, use_container_width=True, height=400)

                    # Download button
                    csv_data = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="⬇️ Download CSV",
                        data=csv_data,
                        file_name="parsed_output.csv",
                        mime="text/csv"
                    )

                    # Clean up temporary files
                    if os.path.exists(output_path):
                        os.unlink(output_path)
                    if input_method == "Upload File" and os.path.exists(xml_source):
                        os.unlink(xml_source)

                except Exception as e:
                    st.error(f"❌ Error parsing XML: {str(e)}")
        else:
            st.warning("⚠️ Please provide an XML source (URL or file upload)")

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

    st.subheader("Parse XML Tab")
    st.write("""
    1. Choose input method (URL or File)
    2. Provide XML source
    3. Click 'Parse XML'
    4. Review and download results
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
