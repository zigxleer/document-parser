import pandas as pd
import sys


def compare_csvs(old_csv_path, new_csv_path, output_csv_path):
    """
    Compare two CSV files containing parsed legal documents and identify changes.

    Args:
        old_csv_path: Path to the existing (old) CSV file
        new_csv_path: Path to the updated (new) CSV file
        output_csv_path: Path where the output CSV will be saved
    """
    # Read both CSV files
    try:
        old_df = pd.read_csv(old_csv_path)
        new_df = pd.read_csv(new_csv_path)
    except Exception as e:
        print(f"Error reading CSV files: {e}")
        sys.exit(1)

    # Verify required columns exist
    required_columns = ['Name', 'Sub Activity', 'Topic', 'Legislation', 'Sections', 'Notes']

    for col in required_columns:
        if col not in old_df.columns:
            print(f"Error: Column '{col}' not found in old CSV")
            sys.exit(1)
        if col not in new_df.columns:
            print(f"Error: Column '{col}' not found in new CSV")
            sys.exit(1)

    # Check if ID column exists in old file
    if 'ID' not in old_df.columns:
        print("Warning: 'ID' column not found in old CSV. IDs will not be preserved.")
        old_df['ID'] = None

    # Create output list to store results
    output_rows = []

    # Create a dictionary for quick lookup of old clauses by (Sections, Notes)
    old_clauses = {}
    for idx, row in old_df.iterrows():
        key = (str(row['Sections']), str(row['Notes']))
        old_clauses[key] = row.to_dict()

    # Create a set to track which old clauses were matched
    matched_old_keys = set()

    # Process new clauses
    for idx, new_row in new_df.iterrows():
        sections = str(new_row['Sections'])
        notes = str(new_row['Notes'])
        key = (sections, notes)

        # Check if exact match exists (Same)
        if key in old_clauses:
            change_type = 'Same'
            clause_id = old_clauses[key].get('ID')
            matched_old_keys.add(key)
        else:
            # Check if Sections exists with different Notes (Updated)
            updated_match = None
            for old_key, old_clause in old_clauses.items():
                if old_key[0] == sections and old_key[1] != notes:
                    updated_match = old_clause
                    matched_old_keys.add(old_key)
                    break

            if updated_match:
                change_type = 'Updated'
                clause_id = updated_match.get('ID')
            else:
                # New clause
                change_type = 'New'
                clause_id = None

        # Create output row
        output_row = new_row.to_dict()
        output_row['Change Type'] = change_type
        output_row['ID'] = clause_id
        output_rows.append(output_row)

    # Find deleted clauses (in old but not in new)
    for old_key, old_clause in old_clauses.items():
        if old_key not in matched_old_keys:
            output_row = old_clause.copy()
            output_row['Change Type'] = 'Deleted'
            output_rows.append(output_row)

    # Create output DataFrame
    output_df = pd.DataFrame(output_rows)

    # Reorder columns to put ID and Change Type at the beginning
    cols = ['ID', 'Change Type'] + [col for col in required_columns if col in output_df.columns]
    # Add any additional columns that might exist
    for col in output_df.columns:
        if col not in cols:
            cols.append(col)

    output_df = output_df[cols]

    # Save to output file
    try:
        output_df.to_csv(output_csv_path, index=False)
        print(f"Comparison complete. Output saved to: {output_csv_path}")

        # Print summary statistics
        print("\nSummary:")
        print(f"  Same: {len(output_df[output_df['Change Type'] == 'Same'])}")
        print(f"  Updated: {len(output_df[output_df['Change Type'] == 'Updated'])}")
        print(f"  New: {len(output_df[output_df['Change Type'] == 'New'])}")
        print(f"  Deleted: {len(output_df[output_df['Change Type'] == 'Deleted'])}")
        print(f"  Total rows: {len(output_df)}")

    except Exception as e:
        print(f"Error writing output file: {e}")
        sys.exit(1)


def main():
    # Set your file paths here
    old_csv_path = r'output_old - output.csv (1).csv'
    new_csv_path = r'output_new - output.csv.csv'
    output_csv_path = r'C:\Users\Admin\Desktop\Parser\output_file.csv'

    compare_csvs(old_csv_path, new_csv_path, output_csv_path)


if __name__ == '__main__':
    main()
