import json
import csv
import math
import itertools
from PyNite import FEModel3D


# Function to read input data from JSON file
def read_input_data(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
    return data


# Function to read member properties from CSV file
def read_member_database(filename):
    available_sections = []
    with open(filename, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Convert string values to appropriate types
            section = {
                'Section Name': row['Designation'],
                'm': float(row['m']),  # Mass per unit length
                'A': float(row['A']),  # Cross-sectional area
                'Ix': float(row['Ix']),  # Moment of inertia about x-axis
                'Zex': float(row['Zex']),  # Elastic section modulus x-axis
                'Zplx': float(row['Zplx']),  # Plastic section modulus x-axis
                'rx': float(row['rx']),  # Radius of gyration about x-axis
                'Iy': float(row['Iy']),  # Moment of inertia about y-axis
                'Zey': float(row['Zey']),  # Elastic section modulus y-axis
                'ry': float(row['ry']),  # Radius of gyration about y-axis
                'J': float(row['J']),  # Torsional constant
                'Cw': float(row['Cw']),  # Warping constant
            }
            available_sections.append(section)
    return print(available_sections)


# Function to calculate member length
def get_member_length(node_coords, node_start, node_end):
    x1, y1 = node_coords[node_start]
    x2, y2 = node_coords[node_end]
    dx = x2 - x1
    dy = y2 - y1
    return math.sqrt(dx ** 2 + dy ** 2)


# Strength check functions (implement your equations)
def cross_sectional_strength(forces, section):
    # Placeholder implementation
    # Use forces and section properties to calculate stress
    # Return True if the section passes the check
    return True


def overall_member_strength(forces, section):
    # Placeholder implementation
    return True


def lateral_torsional_buckling(forces, section):
    # Placeholder implementation
    return True


def strength_checks(member_forces, member_sections):
    for member_name, forces in member_forces.items():
        section = member_sections[member_name]
        if not cross_sectional_strength(forces, section):
            return False
        if not overall_member_strength(forces, section):
            return False
        if not lateral_torsional_buckling(forces, section):
            return False
    return True


# Function to analyze the frame using PyNite
def analyze_frame(input_data, member_sections, node_coords, members_info):
    model = FEModel3D()

    # Add nodes to the model
    for node_name, (x, y) in node_coords.items():
        model.AddNode(node_name, x, y, 0)

    # Define supports
    for node_name, restraint in input_data['supports'].items():
        model.DefineSupport(
            node_name,
            restraint.get('DX', False),
            restraint.get('DY', False),
            False,  # DZ
            False,  # RX
            False,  # RY
            restraint.get('RZ', False)
        )

    # Add members
    for member_name, (start_node, end_node) in members_info.items():
        section = member_sections[member_name]
        E = 200e9  # Young's modulus
        Iy = section['Iy']
        Iz = section['Iz']
        J = section['J']
        A = section['A']
        model.AddMember(member_name, start_node, end_node, E, G, Iy, Iz, J, A)

    # Apply loads (example: total vertical load at apex)
    total_vertical_load = input_data['dead_loads'] + input_data['live_loads']
    model.AddNodeLoad('N3', 'FY', -total_vertical_load)

    # Apply wind loads if specified
    if 'wind_loads' in input_data:
        wind_load = input_data['wind_loads']
        # Apply wind loads to nodes or members as needed

    # Analyze the model
    model.Analyze()

    # Retrieve results
    results = {}
    for member_name in members_info.keys():
        member = model.GetMember(member_name)
        forces = member.GetMemberForces()
        results[member_name] = forces

    return results


def main():
    # Read input data from JSON file
    input_data = read_input_data('load_case_input.json')

    # Read member properties from CSV file
    available_sections = read_member_database('member_database.csv')

    # Define node coordinates based on input data
    eave_height = input_data['eave_height']
    rafter_span = input_data['rafter_span']
    rafter_height = input_data['rafter_height']

    node_coords = {
        'N1': (0, 0),
        'N2': (0, eave_height),
        'N3': (rafter_span / 2, eave_height + rafter_height),
        'N4': (rafter_span, eave_height),
        'N5': (rafter_span, 0)
    }

    # Member information
    members_info = {
        'Column1': ('N1', 'N2'),
        'RafterLeft': ('N2', 'N3'),
        'RafterRight': ('N3', 'N4'),
        'Column2': ('N4', 'N5')
    }

    # For each member, assign the available sections
    member_section_options = {
        member_name: available_sections for member_name in members_info.keys()
    }

    # Generate combinations (limiting to first few sections for efficiency)
    section_limit = 3  # Adjust as needed
    for member_name in member_section_options:
        member_section_options[member_name] = available_sections[:section_limit]

    # Generate all possible combinations of sections
    combinations = list(itertools.product(
        *member_section_options.values()))

    best_weight = float('inf')
    best_configuration = None

    # Iterate over each combination
    for combo in combinations:
        member_sections = dict(zip(members_info.keys(), combo))
        total_weight = 0
        # Calculate total weight
        for member_name, section in member_sections.items():
            length = get_member_length(
                node_coords, *members_info[member_name])
            total_weight += section['w'] * length

        # Analyze the frame
        analysis_results = analyze_frame(
            input_data, member_sections, node_coords, members_info)

        # Perform strength checks
        if strength_checks(analysis_results, member_sections):
            if total_weight < best_weight:
                best_weight = total_weight
                best_configuration = member_sections.copy()

    # Output the best configuration
    if best_configuration:
        print("Optimal Member Sections:")
        for member_name, section in best_configuration.items():
            print(f"{member_name}: {section['Section Name']}")
        print(f"Total Weight: {best_weight} kg")

        # Write results to output file
        with open('optimal_sections.txt', 'w') as f:
            f.write("Optimal Member Sections:\n")
            for member_name, section in best_configuration.items():
                f.write(f"{member_name}: {section['Section Name']}\n")
            f.write(f"Total Weight: {best_weight} kg\n")
    else:
        print("No acceptable configuration found.")
        with open('optimal_sections.txt', 'w') as f:
            f.write("No acceptable configuration found.\n")


if __name__ == '__main__':
    read_member_database('member_database.csv')
