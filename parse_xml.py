import xml.etree.ElementTree as ET
import csv
import re
import urllib.request

def extract_all_text(element, separator='\n', skip_direct_label=False):
    """Extract all text from an element and its children, separated by the given separator."""
    # Tags that should use space separator instead of newline
    space_separator_tags = {'XRefExternal', 'DefinedTermEn', 'DefinedTermFr', 'Label', 'DefinitionRef', 'Language', 'Sup', 'XRefInternal', 'Sub'}
    # Tags that should always have newline after them
    newline_after_tags = {'MarginalNote'}

    texts = []
    prev_child_tag = None

    # Get direct text
    if element.text and element.text.strip():
        texts.append(element.text.strip())

    # Get text from all children
    for child in element:
        # Skip only direct Label child if requested (don't skip labels in nested elements)
        if skip_direct_label and child.tag == 'Label':
            # Still process tail text after the label
            if child.tail and child.tail.strip():
                if texts:
                    texts.append(' ' + child.tail.strip())
                else:
                    texts.append(child.tail.strip())
            # Don't update prev_child_tag when skipping - act as if this tag wasn't there
            continue

        # Add consultation message before TableGroup content
        if child.tag == 'TableGroup':
            table_message = "[To consult the table, please visit: [primary URL to be added here in production]]"
            if texts:
                texts.append('\n' + table_message)
            else:
                texts.append(table_message)
            # Continue to process TableGroup content normally
            child_texts = extract_all_text(child, separator, skip_direct_label=False)
            if child_texts:
                texts.append('\n' + child_texts)
            # Process tail text after TableGroup
            if child.tail and child.tail.strip():
                texts.append('\n' + child.tail.strip())
            prev_child_tag = child.tag
            continue

        # Recursively extract text from child (don't pass skip_direct_label to children)
        child_texts = extract_all_text(child, separator, skip_direct_label=False)
        if child_texts:
            # Determine what separator to use for this child tag
            # If previous tag had newline after it, don't add space
            if prev_child_tag in newline_after_tags:
                # Previous tag already added newline, no separator needed
                sep_to_use = ''
            # Use space if current child OR previous child is in space_separator_tags
            elif child.tag in space_separator_tags or prev_child_tag in space_separator_tags:
                # Use space before this tag's content
                if texts and texts[-1]:  # If there's already content, use space
                    sep_to_use = ' '
                else:
                    sep_to_use = ''
            else:
                sep_to_use = separator

            if texts and sep_to_use:
                texts.append(sep_to_use + child_texts)
            else:
                texts.append(child_texts)

            # Add newline after specific tags
            if child.tag in newline_after_tags:
                texts.append('\n')

        # Remember this child's tag for the next iteration
        prev_child_tag = child.tag

        # Get tail text after child element
        if child.tail and child.tail.strip():
            # Determine separator for tail text based on the child tag that preceded it
            # If the previous tag had a newline after it, don't add extra separator
            if child.tag in newline_after_tags:
                # Newline was already added, so no separator needed
                texts.append(child.tail.strip())
            elif child.tag in space_separator_tags:
                sep_to_use = ' '
                if texts and sep_to_use:
                    texts.append(sep_to_use + child.tail.strip())
                else:
                    texts.append(child.tail.strip())
            else:
                sep_to_use = separator
                if texts and sep_to_use:
                    texts.append(sep_to_use + child.tail.strip())
                else:
                    texts.append(child.tail.strip())

    return ''.join(texts) if texts else ''

def parse_introduction(intro_element):
    """Parse Introduction section and return a row."""
    row = {
        'Name': '',
        'Sub Activity': '',
        'Topic': '',
        'Legislation': '',
        'Sections': '',
        'Notes': ''
    }

    # Find first MarginalNote for Name
    marginal_note = intro_element.find('.//MarginalNote')
    if marginal_note is not None:
        row['Name'] = extract_all_text(marginal_note, ' ')

    # Extract all text for Notes
    row['Notes'] = extract_all_text(intro_element, '\n')

    return row

def is_numeric_label(label_text):
    """Check if label is in format (1), (2), etc. (numbers only, not letters or roman numerals)."""
    if not label_text:
        return False
    # Match pattern like (1), (2), (123), (5.1) - parentheses with digits and optional decimal
    pattern = r'^\(\d+(?:\.\d+)?\)$'
    return bool(re.match(pattern, label_text.strip()))

def process_section_elements(section_element, heading_level1, heading_level2, heading_level3, section_label):
    """Process elements within a Section, creating separate rows for subsections with numeric labels."""
    rows = []

    # Check if there's a MarginalNote at Section level (before subsections)
    section_marginal_note = None
    for child in section_element:
        if child.tag == 'MarginalNote':
            section_marginal_note = extract_all_text(child, ' ')
            break

    # Find all Subsection elements
    subsections = section_element.findall('.//Subsection')

    if subsections:
        # Process each subsection
        for idx, subsection in enumerate(subsections):
            subsection_label = subsection.find('Label')

            # Check if this subsection has a numeric label like (1), (2)
            if subsection_label is not None:
                label_text = extract_all_text(subsection_label, ' ')

                if is_numeric_label(label_text):
                    # Create a separate row for this subsection
                    # Combine section label with subsection label (e.g., "3 (1)")
                    combined_sections = f"{section_label} {label_text}" if section_label else label_text
                    # Prepend "s." to sections column
                    sections_with_prefix = f"s.{combined_sections}" if combined_sections else ''

                    # Extract notes without the direct subsection label and prepend the combined sections
                    notes_text = extract_all_text(subsection, '\n', skip_direct_label=True)

                    # If this is the first subsection and there's a section-level MarginalNote, include it
                    if idx == 0 and section_marginal_note:
                        notes_with_section = f"{combined_sections} {section_marginal_note}\n{notes_text}"
                    else:
                        notes_with_section = f"{combined_sections} {notes_text}"

                    row = {
                        'Name': heading_level1,
                        'Sub Activity': heading_level2,
                        'Topic': heading_level3,
                        'Legislation': '',
                        'Sections': sections_with_prefix,
                        'Notes': notes_with_section
                    }
                    rows.append(row)

    # If no subsections with numeric labels were found, create a single row for the entire section
    if not rows:
        # Extract notes without the direct section label and prepend the section label
        notes_text = extract_all_text(section_element, '\n', skip_direct_label=True)
        notes_with_section = f"{section_label} {notes_text}" if section_label else notes_text
        # Prepend "s." to sections column
        sections_with_prefix = f"s.{section_label}" if section_label else ''

        row = {
            'Name': heading_level1,
            'Sub Activity': heading_level2,
            'Topic': heading_level3,
            'Legislation': '',
            'Sections': sections_with_prefix,
            'Notes': notes_with_section
        }
        rows.append(row)

    return rows

def parse_body(body_element):
    """Parse Body section and return multiple rows."""
    rows = []
    # Track up to 3 levels of headings
    heading_level1 = ''  # For level 1 headings
    heading_level2 = ''  # For level 2 headings
    heading_level3 = ''  # For level 3+ headings

    # Iterate through all children of Body
    for element in body_element:
        if element.tag == 'Heading':
            # Get heading level
            level = element.get('level', '1')

            # Extract Label and TitleText
            label = element.find('Label')
            title_text = element.find('TitleText')

            label_text = extract_all_text(label, ' ') if label is not None else ''
            title_text_str = extract_all_text(title_text, ' ') if title_text is not None else ''

            # Combine Label and TitleText if both exist (with newline after label)
            if label_text and title_text_str:
                heading_text = f"{label_text}\n{title_text_str}"
            elif label_text:
                heading_text = label_text
            else:
                heading_text = title_text_str

            # Assign to appropriate heading level
            if level == '1':
                heading_level1 = heading_text
                heading_level2 = ''
                heading_level3 = ''
            elif level == '2':
                heading_level2 = heading_text
                heading_level3 = ''
            else:  # level 3 or higher
                heading_level3 = heading_text

        elif element.tag == 'Section':
            # Extract section Label if present
            section_label = ''
            label = element.find('Label')
            if label is not None:
                section_label = extract_all_text(label, ' ')

            # Process the section and its subsections
            section_rows = process_section_elements(element, heading_level1, heading_level2, heading_level3, section_label)
            rows.extend(section_rows)

    return rows

def parse_schedules(root):
    """Parse Schedule elements and return rows."""
    rows = []
    schedules = root.findall('.//Schedule')

    # Maximum character limit for a cell (Excel has ~32,767 character limit)
    MAX_CELL_LENGTH = 32000

    for schedule in schedules:
        # Get Label from ScheduleFormHeading
        schedule_form_heading = schedule.find('.//ScheduleFormHeading')
        schedule_label = ''
        if schedule_form_heading is not None:
            label = schedule_form_heading.find('Label')
            if label is not None:
                schedule_label = extract_all_text(label, ' ')

        # Skip schedules without labels (exclude last two schedules like RELATED PROVISIONS, AMENDMENTS NOT IN FORCE)
        if not schedule_label:
            continue

        # Keep original label for Name column
        schedule_name = schedule_label

        # Convert "SCHEDULE 1" to "s.sch.1" format for Sections column
        schedule_section = schedule_label.replace('SCHEDULE ', 's.sch.').replace('SCHEDULE', 's.sch.')

        # Extract all text from the schedule
        schedule_text = extract_all_text(schedule, '\n')

        # Prepend consultation message to schedule notes
        consultation_message = "[To consult the schedule, please visit: [primary URL to be added here in production]]"
        schedule_notes = f"{consultation_message}\n{schedule_text}"

        # Check if text exceeds limit and split if necessary
        if len(schedule_notes) <= MAX_CELL_LENGTH:
            # Single row
            row = {
                'Name': schedule_name,
                'Sub Activity': '',
                'Topic': '',
                'Legislation': '',
                'Sections': schedule_section,
                'Notes': schedule_notes
            }
            rows.append(row)
        else:
            # Split into multiple rows
            chunks = []
            current_chunk = ''

            # Split by lines to avoid breaking mid-sentence
            lines = schedule_notes.split('\n')
            for line in lines:
                if len(current_chunk) + len(line) + 1 <= MAX_CELL_LENGTH:
                    if current_chunk:
                        current_chunk += '\n' + line
                    else:
                        current_chunk = line
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = line

            if current_chunk:
                chunks.append(current_chunk)

            # Create a row for each chunk
            for chunk in chunks:
                row = {
                    'Name': schedule_name,
                    'Sub Activity': '',
                    'Topic': '',
                    'Legislation': '',
                    'Sections': schedule_section,
                    'Notes': chunk
                }
                rows.append(row)

    return rows

def parse_xml_to_csv(xml_source, csv_file_path):
    """Parse XML from URL or file path and export to CSV."""
    # Check if source is a URL or file path
    if xml_source.startswith('http://') or xml_source.startswith('https://'):
        print(f"Fetching XML from URL: {xml_source}")
        # Fetch XML from URL
        with urllib.request.urlopen(xml_source) as response:
            xml_content = response.read()
        root = ET.fromstring(xml_content)
    else:
        print(f"Reading XML from file: {xml_source}")
        # Parse XML from file
        tree = ET.parse(xml_source)
        root = tree.getroot()

    rows = []

    # Process Introduction if it exists
    introduction = root.find('.//Introduction')
    if introduction is not None:
        intro_row = parse_introduction(introduction)
        rows.append(intro_row)

    # Process Body if it exists
    body = root.find('.//Body')
    if body is not None:
        body_rows = parse_body(body)
        rows.extend(body_rows)

    # Process Schedules if they exist
    schedule_rows = parse_schedules(root)
    rows.extend(schedule_rows)

    # Write to CSV
    if rows:
        fieldnames = ['Name', 'Sub Activity', 'Topic', 'Legislation', 'Sections', 'Notes']

        with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"Successfully parsed {len(rows)} rows from XML to CSV")
        print(f"Output file: {csv_file_path}")
    else:
        print("No data found to export")

if __name__ == "__main__":
    # Can be either a URL or a local file path
    # Example URL: "https://example.com/path/to/file.xml"
    # Example file: r"c:\Users\Admin\Desktop\Parser\A-12.xml"
    xml_source = r"https://laws-lois.justice.gc.ca/eng/XML/P-21.xml"
    csv_file = r"c:\Users\Admin\Desktop\Parser\output.csv"

    parse_xml_to_csv(xml_source, csv_file)
