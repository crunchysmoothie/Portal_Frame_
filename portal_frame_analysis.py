import json
from PyNite import FEModel3D
from PyNite.Visualization import Renderer
import member_database as mdb


def import_data(file):
    """
    Imports structural data from a JSON file and structures it into dictionaries and lists.
    """
    with open(file) as f:
        data = json.load(f)

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


def build_model():
    """
    Builds and analyzes the FE model based on the imported JSON data.
    """
    # Create a new model
    frame = FEModel3D()

    # Import data
    data = import_data('input_data.json')

    # Load the member database
    member_db = mdb.load_member_database()

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

    # Define nodal spring supports (if any)
    for spring in data.get('rotational_springs', []):
        node = spring['node']
        dof = spring['dof']  # 'DX', 'DY', 'DZ', 'RX', 'RY', or 'RZ'
        stiffness = spring['stiffness']
        direction = spring.get('direction', None)  # '+', '-', or None
        # Define the support spring using the correct method signature
        frame.def_support_spring(node, dof=dof, stiffness=stiffness, direction=direction)

    # Function to determine the lightest sections
    def lightest_section():
        """
        Determines and returns the section names for rafters and columns.
        Modify this function based on your selection criteria.
        """
        rafter = '254x146x31'  # Example section name for rafters
        column = '356x171x45'  # Example section name for columns
        return rafter, column

    # Get the lightest sections
    rafter_section_name, column_section_name = lightest_section()

    # Get member properties from the member database
    rmem_properties = mdb.member_properties(rafter_section_name, member_db)
    cmem_properties = mdb.member_properties(column_section_name, member_db)

    # Convert units from cm^2 to mm^2 and cm^4 to mm^4 for rafters
    RA = rmem_properties['A'] * 1e3       # Cross-sectional area in mm^2
    RIy = rmem_properties['Iy'] * 1e6     # Moment of inertia about local y-axis in mm^4
    RIx = rmem_properties['Ix'] * 1e6     # Moment of inertia about local x-axis in mm^4
    RJ = rmem_properties['J'] * 1e3       # Torsional constant in mm^4

    # Convert units from cm^2 to mm^2 and cm^4 to mm^4 for columns
    CA = cmem_properties['A'] * 1e3       # Cross-sectional area in mm^2
    CIy = cmem_properties['Iy'] * 1e6     # Moment of inertia about local y-axis in mm^4
    CIx = cmem_properties['Ix'] * 1e6     # Moment of inertia about local x-axis in mm^4
    CJ = cmem_properties['J'] * 1e3       # Torsional constant in mm^4

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

    # Add load combinations
    for ULS_combo in data.get('load_combinations', []):
        combo_name = ULS_combo['name']
        factors = ULS_combo['factors']
        frame.add_load_combo(combo_name, factors=factors)

    # Add serviceability load combinations
    for SLS_combo in data.get('serviceability_load_combinations', []):
        combo_name = SLS_combo['name']
        factors = SLS_combo['factors']
        frame.add_load_combo(combo_name, factors=factors)


    # Add member self weight (optional, adjust as needed)
    frame.add_member_self_weight('FY', -1, 'D')  # Example: Adding self-weight in FY direction

    # Analyze the model
    frame.analyze(check_statics=True)

    # Render the deformed shape
    rndr = Renderer(frame)
    rndr.annotation_size = 140
    rndr.render_loads = True
    rndr.deformed_shape = True
    rndr.deformed_scale = 100
    rndr.combo_name = '1.2 DL + 1.6 LL'
    rndr.render_model()

    # Print results for specific load cases
    print("Member M1 Max Mz:", round(frame.members['M1'].max_moment('Mz', '1.2 DL + 1.6 LL') / 1000, 2), "kNm")
    print("Member M1 Min Mz:", round(frame.members['M1'].min_moment('Mz', '1.2 DL + 1.6 LL') / 1000, 2), "kNm")
    print("Node N1 FX Reaction:", round(frame.nodes['N1'].RxnFX['1.2 DL + 1.6 LL'], 2), "kN")
    print("Node N1 FY Reaction:", round(frame.nodes['N1'].RxnFY['1.2 DL + 1.6 LL'], 2), "kN")
    print("Node N1 MZ Reaction:", round(frame.nodes['N1'].RxnMZ['1.2 DL + 1.6 LL'] / 1000, 2), "kNm")
    print("Node N9 FX Reaction:", round(frame.nodes['N9'].RxnFX['1.2 DL + 1.6 LL'], 2),  "kN")
    print("Node N9 FY Reaction:", round(frame.nodes['N9'].RxnFY['1.2 DL + 1.6 LL'], 2), "kN")
    print("Node N9 MZ Reaction:", round(frame.nodes['N9'].RxnMZ['1.2 DL + 1.6 LL'] / 1000, 2), "kNm")
    print("Node N5 DX Displacement:", round(frame.nodes['N5'].DX['1.1 DL + 1.0 LL'], 2), "mm")
    print("Node N5 DY Displacement:", round(frame.nodes['N5'].DY['1.1 DL + 1.0 LL'], 2), "mm")


    return


build_model()
