import xml.etree.ElementTree as ET
import csv
import re
import urllib.request

def construct_fulltext_url(xml_source, root_tag):
    """Construct FullText.html URL from XML source URL.

    Args:
        xml_source: The XML source URL (e.g., https://laws-lois.justice.gc.ca/eng/XML/P-21.xml)
        root_tag: The root element tag name ('Statute' or 'Regulation')

    Returns:
        The constructed FullText URL (e.g., https://laws-lois.justice.gc.ca/eng/acts/P-21/FullText.html)
    """
    # Only construct URL if source is a URL
    if not (xml_source.startswith('http://') or xml_source.startswith('https://')):
        return ''

    # Extract the identifier (e.g., P-21) from the XML URL
    # Pattern: .../XML/IDENTIFIER.xml
    match = re.search(r'/XML/([^/]+)\.xml$', xml_source, re.IGNORECASE)
    if not match:
        return ''

    identifier = match.group(1)

    # Determine if it's acts or regulations based on root tag
    document_type = 'regulations' if root_tag == 'Regulation' else 'acts'

    # Extract base URL (everything before /XML/)
    base_url = xml_source.split('/XML/')[0]

    # Construct the FullText URL
    fulltext_url = f"{base_url}/{document_type}/{identifier}/FullText.html"

    return fulltext_url

def extract_all_text(element, separator='\n', skip_direct_label=False, fulltext_url=''):
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
            if fulltext_url:
                table_message = f"[To consult the table, please visit: {fulltext_url}]"
            else:
                table_message = "[To consult the table, please visit the government website]"
            if texts:
                texts.append('\n' + table_message)
            else:
                texts.append(table_message)
            # Continue to process TableGroup content normally
            child_texts = extract_all_text(child, separator, skip_direct_label=False, fulltext_url=fulltext_url)
            if child_texts:
                texts.append('\n' + child_texts)
            # Process tail text after TableGroup
            if child.tail and child.tail.strip():
                texts.append('\n' + child.tail.strip())
            prev_child_tag = child.tag
            continue

        # Add consultation message before ImageGroup content with constructed URL
        if child.tag == 'ImageGroup':
            # Find Image tag and extract source attribute
            image_tag = child.find('.//Image')
            image_url = ''
            if image_tag is not None:
                source = image_tag.get('source', '')
                if source:
                    # Construct full URL with base URL
                    base_url = 'https://laws-lois.justice.gc.ca/images/'
                    image_url = base_url + source

            # Create message with URL
            if image_url:
                image_message = f"[To consult the image, please visit: {image_url}]"
            else:
                image_message = "[To consult the image, please visit the government website]"

            if texts:
                texts.append('\n' + image_message)
            else:
                texts.append(image_message)
            # Continue to process ImageGroup content normally
            child_texts = extract_all_text(child, separator, skip_direct_label=False, fulltext_url=fulltext_url)
            if child_texts:
                texts.append('\n' + child_texts)
            # Process tail text after ImageGroup
            if child.tail and child.tail.strip():
                texts.append('\n' + child.tail.strip())
            prev_child_tag = child.tag
            continue

        # Recursively extract text from child (don't pass skip_direct_label to children)
        child_texts = extract_all_text(child, separator, skip_direct_label=False, fulltext_url=fulltext_url)
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

def parse_introduction(intro_element, fulltext_url=''):
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
        row['Name'] = extract_all_text(marginal_note, ' ', fulltext_url=fulltext_url)

    # Extract all text for Notes
    row['Notes'] = extract_all_text(intro_element, '\n', fulltext_url=fulltext_url)

    return row

def is_numeric_label(label_text):
    """Check if label is in format (1), (2), etc. (numbers only, not letters or roman numerals).
    Also handles range labels like (3.2) to (3.5)."""
    if not label_text:
        return False
    # Match pattern like (1), (2), (123), (5.1) - parentheses with digits and optional decimal
    # Also match ranges like (3.2) to (3.5)
    single_pattern = r'^\(\d+(?:\.\d+)?\)$'
    range_pattern = r'^\(\d+(?:\.\d+)?\)\s+to\s+\(\d+(?:\.\d+)?\)$'

    label_stripped = label_text.strip()
    return bool(re.match(single_pattern, label_stripped) or re.match(range_pattern, label_stripped))

def process_section_elements(section_element, heading_level1, heading_level2, heading_level3, section_label, fulltext_url=''):
    """Process elements within a Section, creating separate rows for subsections with numeric labels."""
    rows = []

    # Check if there's a MarginalNote at Section level (before subsections)
    section_marginal_note = None
    for child in section_element:
        if child.tag == 'MarginalNote':
            section_marginal_note = extract_all_text(child, ' ', fulltext_url=fulltext_url)
            break

    # Find all Subsection elements
    subsections = section_element.findall('.//Subsection')

    if subsections:
        # Process each subsection
        for idx, subsection in enumerate(subsections):
            subsection_label = subsection.find('Label')

            # Check if this subsection has a numeric label like (1), (2)
            if subsection_label is not None:
                label_text = extract_all_text(subsection_label, ' ', fulltext_url=fulltext_url)

                if is_numeric_label(label_text):
                    # Create a separate row for this subsection
                    # Combine section label with subsection label (e.g., "3 (1)")
                    combined_sections = f"{section_label} {label_text}" if section_label else label_text
                    # Prepend "s." to sections column
                    sections_with_prefix = f"s.{combined_sections}" if combined_sections else ''

                    # Extract notes without the direct subsection label and prepend the combined sections
                    notes_text = extract_all_text(subsection, '\n', skip_direct_label=True, fulltext_url=fulltext_url)

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
        notes_text = extract_all_text(section_element, '\n', skip_direct_label=True, fulltext_url=fulltext_url)
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

def parse_body(body_element, fulltext_url=''):
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

            label_text = extract_all_text(label, ' ', fulltext_url=fulltext_url) if label is not None else ''
            title_text_str = extract_all_text(title_text, ' ', fulltext_url=fulltext_url) if title_text is not None else ''

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
                section_label = extract_all_text(label, ' ', fulltext_url=fulltext_url)

            # Process the section and its subsections
            section_rows = process_section_elements(element, heading_level1, heading_level2, heading_level3, section_label, fulltext_url)
            rows.extend(section_rows)

    return rows

def parse_schedules(root, fulltext_url=''):
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
                schedule_label = extract_all_text(label, ' ', fulltext_url=fulltext_url)

        # Skip schedules without labels (exclude last two schedules like RELATED PROVISIONS, AMENDMENTS NOT IN FORCE)
        if not schedule_label:
            continue

        # Keep original label for Name column
        schedule_name = schedule_label

        # Convert "SCHEDULE 1" to "s.sch.1" format for Sections column
        schedule_section = schedule_label.replace('SCHEDULE ', 's.sch.').replace('SCHEDULE', 's.sch.')

        # Extract all text from the schedule
        schedule_text = extract_all_text(schedule, '\n', fulltext_url=fulltext_url)

        # Prepend consultation message to schedule notes
        if fulltext_url:
            consultation_message = f"[To consult the schedule, please visit: {fulltext_url}]"
        else:
            consultation_message = "[To consult the schedule, please visit the government website]]"
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
    """Parse XML from URL or file path and export to CSV.

    Returns:
        dict: A dictionary containing:
            - 'name': "Imported automatically. Last amended" + date
            - 'coming_into_force_date': the lastAmendedDate
            - 'row_count': number of rows parsed
    """
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

    # Get root tag name (Statute or Regulation)
    # Remove namespace from tag if present
    root_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag

    # Construct FullText URL
    fulltext_url = construct_fulltext_url(xml_source, root_tag)
    if fulltext_url:
        print(f"Constructed FullText URL: {fulltext_url}")

    # Extract metadata from root element (Statute or Regulation)
    last_amended_date = root.get('{http://justice.gc.ca/lims}lastAmendedDate', '')
    metadata = {
        'name': f"Imported automatically. Last amended {last_amended_date}" if last_amended_date else "Imported automatically",
        'coming_into_force_date': last_amended_date,
        'row_count': 0
    }

    rows = []

    # Process Introduction if it exists
    introduction = root.find('.//Introduction')
    if introduction is not None:
        intro_row = parse_introduction(introduction, fulltext_url)
        rows.append(intro_row)

    # Process Body if it exists
    body = root.find('.//Body')
    if body is not None:
        body_rows = parse_body(body, fulltext_url)
        rows.extend(body_rows)

    # Process Schedules if they exist
    schedule_rows = parse_schedules(root, fulltext_url)
    rows.extend(schedule_rows)

    # Write to CSV
    if rows:
        fieldnames = ['Name', 'Sub Activity', 'Topic', 'Legislation', 'Sections', 'Notes']

        with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        metadata['row_count'] = len(rows)
        print(f"Successfully parsed {len(rows)} rows from XML to CSV")
        print(f"Output file: {csv_file_path}")
    else:
        print("No data found to export")

    return metadata

if __name__ == "__main__":
    # Can be either a URL or a local file path
    # Example URL: "https://example.com/path/to/file.xml"
    # Example file: r"c:\Users\Admin\Desktop\Parser\A-12.xml"
    xml_source = r"https://laws-lois.justice.gc.ca/eng/XML/P-21.xml"
    csv_file = r"c:\Users\Admin\Desktop\Parser\output.csv"

    parse_xml_to_csv(xml_source, csv_file)
