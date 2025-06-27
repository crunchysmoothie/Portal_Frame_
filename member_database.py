import csv


def load_member_database(filename='member_database.csv'):
    member_db = {'I-Sections': {}, 'H-Sections': {}}

    with open(filename, mode='r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for index, row in enumerate(reader, start=1):
            section_name = row['Designation']
            for key in row:
                if key != 'Designation':
                    try:
                        row[key] = float(row[key])
                    except ValueError:
                        pass

            # Check the row index to determine section-type
            if index < 44:
                member_db['I-Sections'][section_name] = row
            else:
                member_db['H-Sections'][section_name] = row

    # Sort each section by the weight column 'm'
    member_db['I-Sections'] = dict(sorted(member_db['I-Sections'].items(), key=lambda item: item[1].get('m', 0)))
    member_db['H-Sections'] = dict(sorted(member_db['H-Sections'].items(), key=lambda item: item[1].get('m', 0)))

    return member_db


def member_properties(section_type, section_choice, member_db):
    try:
        return member_db[section_type][section_choice]
    except KeyError:
        raise KeyError(f"Section '{section_choice}' not found in '{section_type}' of the member database.")
