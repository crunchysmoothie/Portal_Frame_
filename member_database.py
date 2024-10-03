import csv

def load_member_database(filename='member_database.csv'):

    member_db = {}
    with open(filename, mode='r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            section_name = row['Designation']
            # Convert numerical values from strings to appropriate types
            for key in row:
                if key != 'Designation':  # Leave the section name as a string
                    try:
                        row[key] = float(row[key])
                    except ValueError:
                        pass  # Keep the value as a string if it cannot be converted
            member_db[section_name] = row
    return member_db

def member_properties(section_choice, member_db):

    try:
        return member_db[section_choice]
    except KeyError:
        raise KeyError(f"Section '{section_choice}' not found in the member database.")

# Example usage:

# Load the member database once
member_database = load_member_database()

# Get properties for a specific section
section_name = 'IPE100'  # Replace with the desired section name
try:
    properties = member_properties(section_name, member_database)
    print(f"Properties for {section_name}:")
    for key, value in properties.items():
        print(f"{key}: {value}")
except KeyError as e:
    print(e)
