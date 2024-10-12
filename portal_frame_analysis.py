import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from PyNite import FEModel3D
from PyNite.Visualization import Renderer
import member_database as mdb

def import_data(file):
    """
    Imports structural data from a JSON file and structures it into dictionaries and lists.
    """
    with open(file) as f:
        data = json.load(f)

        frame_data = data.get('frame_data', {})

        # Initialize dictionaries for the imported data
        nodes = {node['name']: {'x': node['x'], 'y': node['y'], 'z': node['z']}
                 for node in data.get('nodes', [])}

        supports = {support['node']: {
                        'DX': support.get('DX', False),
                        'DY': support.get('DY', False),
                        'DZ': support.get('DZ', False),
                        'RX': support.get('RX', False),
                        'RY': support.get('RY', False),
                        'RZ': support.get('RZ', False)
                    }
                    for support in data.get('supports', [])}

        node_loads = data.get('nodal_loads', [])  # List of nodal load dictionaries

        member_loads = data.get('member_loads', [])  # List of member load dictionaries

        materials = {material['name']: {
                        'E': material['E'],
                        'G': material['G'],
                        'nu': material['nu'],
                        'rho': material['rho']
                    }
                    for material in data.get('materials', [])}

        members = data.get('members', [])  # List of member dictionaries

        rotational_springs = data.get('rotational_springs', [])  # List of spring dictionaries

        serviceability_load_combinations = data.get('serviceability_load_combinations', [])  # List of load combination dictionaries

        load_combinations = data.get('load_combinations', [])  # List of load combination dictionaries

        geometry_parameters = data.get('geometry_parameters', {})  # Geometry parameters dictionary

        return {
            'frame_data': frame_data,
            'nodes': nodes,
            'supports': supports,
            'nodal_loads': node_loads,
            'member_loads': member_loads,
            'materials': materials,
            'members': members,
            'rotational_springs': rotational_springs,
            'serviceability_load_combinations': serviceability_load_combinations,
            'load_combinations': load_combinations,
            'geometry_parameters': geometry_parameters
        }

def build_model(rmem, cmem):
    """
    Builds and returns the FE model based on the imported JSON data.
    """
    # Create a new model
    frame = FEModel3D()

    # Import data
    data = import_data('input_data.json')

    # Define materials
    for name, props in data['materials'].items():
        E = props['E']
        G = props['G']
        nu = props['nu']
        rho = props['rho']
        frame.add_material(name, E, G, nu, rho)

    # Define nodes
    for name, coords in data['nodes'].items():
        x = coords['x']
        y = coords['y']
        z = coords['z']
        frame.add_node(name, x, y, z)

    # Define supports
    for node, support in data['supports'].items():
        DX = support.get('DX', False)
        DY = support.get('DY', False)
        DZ = support.get('DZ', False)
        RX = support.get('RX', False)
        RY = support.get('RY', False)
        RZ = support.get('RZ', False)
        frame.def_support(node, DX, DY, DZ, RX, RY, RZ)

    # Convert units from cm^2 to mm^2 and cm^4 to mm^4 for rafters
    RA = rmem['A'] * 1e3       # Cross-sectional area in mm^3
    RIy = rmem['Iy'] * 1e6     # Moment of inertia about local y-axis in mm^6
    RIx = rmem['Ix'] * 1e6     # Moment of inertia about local x-axis in mm^6
    RJ = rmem['J'] * 1e3       # Torsional constant in mm^3

    # Convert units from cm^2 to mm^2 and cm^4 to mm^4 for columns
    CA = cmem['A'] * 1e3        # Cross-sectional area in mm^3
    CIy = cmem['Iy'] * 1e6     # Moment of inertia about local y-axis in mm^6
    CIx = cmem['Ix'] * 1e6     # Moment of inertia about local x-axis in mm^6
    CJ = cmem['J'] * 1e3       # Torsional constant in mm^3

    # Define members
    for member in data['members']:
        name = member['name']
        i_node = member['i_node']
        j_node = member['j_node']
        material = member['material']
        member_type = member['type'].lower()  # 'rafter' or 'column'

        # Select properties based on member type
        if member_type == 'rafter':
            Iy = RIy
            Iz = RIx
            J = RJ
            A = RA
        elif member_type == 'column':
            Iy = CIy
            Iz = CIx
            J = CJ
            A = CA
        else:
            raise ValueError(f"Invalid member type '{member['type']}' for member '{name}'")

        # Add the member to the model
        frame.add_member(name, i_node, j_node, material, Iy, Iz, J, A)

    # Add nodal loads
    for node_load in data['nodal_loads']:
        node = node_load['node']
        direction = node_load['direction']
        magnitude = node_load['magnitude']
        case = node_load.get('case', None)  # Optional
        frame.add_node_load(node, direction, magnitude, case)

    # Add member distributed loads
    for member_load in data['member_loads']:
        member_name = member_load['member']
        direction = member_load['direction']
        w1 = member_load['w1']
        w2 = member_load['w2']
        case = member_load.get('case', None)  # Optional
        frame.add_member_dist_load(member_name, direction, w1, w2, None, None, case)

    # Add member self weight (optional, adjust as needed)
    frame.add_member_self_weight('FY', -1, 'D')  # Example: Adding self-weight in FY direction

    return frame

def analyze_combination(args):
    """
    Analyzes a single combination of rafter and column sections.
    """
    (r_section_type, rafter_section_name, c_section_type, column_section_name,
     member_db, data, vert_deflection_limit, horiz_deflection_limit) = args

    # Get member properties
    rmem = mdb.member_properties(r_section_type, rafter_section_name, member_db)
    cmem = mdb.member_properties(c_section_type, column_section_name, member_db)

    # Check h and b constraints
    if rmem['h'] > cmem['h'] or rmem['b'] > cmem['b']:
        return None  # Constraints not satisfied

    # Build the model with current sections
    frame = build_model(rmem, cmem)

    # Add serviceability load combinations
    for SLS_combo in data.get('serviceability_load_combinations', []):
        combo_name = SLS_combo['name']
        factors = SLS_combo['factors']
        frame.add_load_combo(combo_name, factors=factors)

    # Analyze the model
    try:
        frame.analyze(check_statics=False)
    except Exception as e:
        # Handle analysis failures gracefully
        return None

    # Initialize worst-case deflections
    worst_vert_deflection = 0
    worst_horiz_deflection = 0

    # Check deflections for each combo
    for combo in data.get('serviceability_load_combinations', []):
        combo_name = combo['name']
        for node in frame.nodes.values():
            dx = abs(node.DX[combo_name])
            dy = abs(node.DY[combo_name])

            # Update worst-case deflections
            if dy > worst_vert_deflection:
                worst_vert_deflection = dy
            if dx > worst_horiz_deflection:
                worst_horiz_deflection = dx

    # Check if deflections are within limits
    if (worst_vert_deflection <= vert_deflection_limit and
        worst_horiz_deflection <= horiz_deflection_limit):
        # Return necessary data
        total_weight = rmem['m'] + cmem['m']
        return total_weight, rafter_section_name, column_section_name, worst_vert_deflection, worst_horiz_deflection
    else:
        return None

def SLS_check(preferred_section ,r_section_type, c_section_type):
    """
    Iterates through the member database to find the lightest acceptable sections
    for rafters and columns that satisfy the serviceability limit state checks.
    """
    start_time = time.time()

    # Load the member database
    member_db = mdb.load_member_database()

    # Verify the section types
    if r_section_type not in member_db or c_section_type not in member_db:
        raise ValueError("Invalid section type. Choose either 'I-Sections' or 'H-Sections'.")

    # Extract sorted lists of section names for rafters and columns
    rafter_sections = [
        sec for sec in member_db[r_section_type]
        if member_db[r_section_type][sec].get('Preferred', 'No') == preferred_section
    ]
    column_sections = [
        sec for sec in member_db[c_section_type]
        if member_db[c_section_type][sec].get('Preferred', 'No') == preferred_section
    ]

    # Ensure that there are sections to process
    if not rafter_sections or not column_sections:
        raise ValueError(f"No sections found with Preferred='{preferred_section}' for the given section types.")


    # Get geometry parameters for deflection limits
    data = import_data('input_data.json')
    # Check vertical (dy) deflection of rafters
    vert_deflection_limit = data['frame_data'][0]['rafter_span']/300  # L/300
    print(f"Vertical deflection limit: {vert_deflection_limit:.2f} mm")
    horiz_deflection_limit = data['frame_data'][0]['eaves_height']/300  # L/300
    print(f"Horizontal deflection limit: {horiz_deflection_limit:.2f} mm")


    # Prepare arguments for multiprocessing
    tasks = []
    for column_section_name in column_sections:
        for rafter_section_name in rafter_sections:
            args = (
                r_section_type, rafter_section_name,
                c_section_type, column_section_name,
                member_db, data, vert_deflection_limit, horiz_deflection_limit
            )
            tasks.append(args)

    acceptable_sections = []

    # Use ProcessPoolExecutor for multiprocessing
    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(analyze_combination, task) for task in tasks]

        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                acceptable_sections.append(result)

    if acceptable_sections:
        # Sort acceptable sections by total weight
        acceptable_sections.sort(key=lambda x: x[0])  # x[0] is total_weight
        best_section = acceptable_sections[0]
        total_weight, rafter_section_name, column_section_name, worst_vert_deflection, worst_horiz_deflection = best_section
        print(f"Lightest acceptable rafter section: {rafter_section_name}")
        print(f"Lightest acceptable column section: {column_section_name}")
        print(f"Total weight: {total_weight} kg/m")
        print(f"Worst vertical deflection: {worst_vert_deflection:.2f} mm")
        print(f"Worst horizontal deflection: {worst_horiz_deflection:.2f} mm")

        end_time = time.time()
        print(f"Script execution time: {end_time - start_time:.2f} seconds")

        # Rebuild and analyze the frame with the best sections in the main process
        rmem = member_db[r_section_type][rafter_section_name]
        cmem = member_db[c_section_type][column_section_name]
        frame = build_model(rmem, cmem)

        # Add serviceability load combinations
        for SLS_combo in data.get('serviceability_load_combinations', []):
            combo_name = SLS_combo['name']
            factors = SLS_combo['factors']
            frame.add_load_combo(combo_name, factors=factors)

        # Analyze the frame
        frame.analyze(check_statics=False)

        return frame, member_db, r_section_type, c_section_type, (rafter_section_name, column_section_name)
    else:
        print("No acceptable section found that satisfies the serviceability limit states.")
        end_time = time.time()
        print(f"Script execution time: {end_time - start_time:.2f} seconds")
        return None, None, None, None, None

def render_model(frame):
    # Render the model
    rndr = Renderer(frame)
    rndr.annotation_size = 250
    rndr.render_loads = True
    rndr.deformed_shape = True
    rndr.deformed_scale = 5
    rndr.combo_name = '1.1 DL + 1.0 LL'  # Adjust as necessary
    rndr.render_model()

def main():
    preferred_section = 'Yes'      # or 'No', based on user preference
    r_section_type = 'I-Sections'  # or 'H-Sections', based on user preference
    c_section_type = 'I-Sections'  # or 'H-Sections', based on user preference

    frame, member_db, r_section_type, c_section_type, best_section = SLS_check(preferred_section, r_section_type, c_section_type)

    if frame is not None:
        render_model(frame)
    else:
        print("Unable to find acceptable sections.")

if __name__ == "__main__":
    main()
