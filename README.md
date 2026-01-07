# Document Parser & Comparator

A Python-based tool for parsing legal documents from XML format and comparing different versions to identify changes.

## Features

### 📄 XML Parser
- Parse legal documents from XML (supports both URLs and local files)
- Extract structured information into CSV format
- Handles sections, subsections, schedules, and legal clauses
- Supports Canadian legal document format (laws-lois.justice.gc.ca)

### 📊 CSV Comparator
- Compare two versions of parsed documents
- Automatically identify changes:
  - **Same**: No changes in Sections and Notes
  - **Updated**: Same Sections but different Notes
  - **New**: Clauses added in new version
  - **Deleted**: Clauses removed from old version
- Preserves clause IDs for tracking
- Color-coded visualization in web interface

## Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd Parser
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Streamlit Web Application

Run the interactive web interface:
```bash
streamlit run app.py
```

The app provides two tabs:
1. **Parse XML**: Convert XML documents to CSV
2. **Compare CSVs**: Compare two CSV versions with visual highlighting

### Command Line Scripts

#### Parse XML to CSV
```bash
python parse_xml.py
```
Edit the file paths in the `main()` function before running.

#### Compare CSV Files
```bash
python compare_csvs.py
```
Edit the file paths in the `main()` function before running.

## File Structure

```
Parser/
├── app.py              # Streamlit web application
├── parse_xml.py        # XML parsing script
├── compare_csvs.py     # CSV comparison script
├── requirements.txt    # Python dependencies
├── README.md          # This file
└── .gitignore         # Git ignore patterns
```

## Output Format

### Parsed CSV Columns
- Name
- Sub Activity
- Topic
- Legislation
- Sections
- Notes

### Comparison CSV Columns
All original columns plus:
- ID (from old version)
- Change Type (Same/Updated/New/Deleted)

## Requirements

- Python 3.7+
- pandas
- streamlit
- xml.etree.ElementTree (standard library)

## License

MIT License - feel free to use and modify as needed.
