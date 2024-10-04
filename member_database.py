import csv

def load_member_database(filename='member_database.csv'):

    member_db = {}
    with open(filename, mode='r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            section_name = row['Designation']
            for key in row:
                if key != 'Designation':
                    try:
                        row[key] = float(row[key])
                    except ValueError:
                        pass
            member_db[section_name] = row
    return member_db

def member_properties(section_choice, member_db):

    try:
        return member_db[section_choice]
    except KeyError:
        raise KeyError(f"Section '{section_choice}' not found in the member database.")