import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from PyNite import FEModel3D
from PyNite.Visualization import Renderer
import member_database as mdb
import tabulate
import math
import os

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

def build_model(r_mem, c_mem):
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
    RA = r_mem['A'] * 1e3       # Cross-sectional area in mm^3
    RIy = r_mem['Iy'] * 1e6     # Moment of inertia about local y-axis in mm^6
    RIx = r_mem['Ix'] * 1e6     # Moment of inertia about local x-axis in mm^6
    RJ = r_mem['J'] * 1e3       # Torsional constant in mm^3

    # Convert units from cm^2 to mm^2 and cm^4 to mm^4 for columns
    CA = c_mem['A'] * 1e3        # Cross-sectional area in mm^3
    CIy = c_mem['Iy'] * 1e6     # Moment of inertia about local y-axis in mm^6
    CIx = c_mem['Ix'] * 1e6     # Moment of inertia about local x-axis in mm^6
    CJ = c_mem['J'] * 1e3       # Torsional constant in mm^3

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

    # Add rotational springs
    for spring in data['rotational_springs']:
        node = spring['node']
        direction = spring['direction']
        stiffness = spring['stiffness']
        frame.def_support_spring(node, direction, stiffness, direction=None)


    return frame

def analyze_combination(args):
    """
    Analyzes a single combination of rafter and column sections.
    """
    (r_section_type, rafter_section_name, c_section_type, column_section_name,
     member_db, data, vert_deflection_limit, horiz_deflection_limit) = args

    # Get member properties
    r_mem = mdb.member_properties(r_section_type, rafter_section_name, member_db)
    c_mem = mdb.member_properties(c_section_type, column_section_name, member_db)

    # Check h and b constraints
    if r_mem['b'] > c_mem['b']:
        r_mem = c_mem

    # Build the model with current sections
    frame = build_model(r_mem, c_mem)

    # Add serviceability load combinations
    for SLS_combo in data.get('serviceability_load_combinations', []):
        combo_name = SLS_combo['name']
        factors = SLS_combo['factors']
        frame.add_load_combo(combo_name, factors=factors)

    # Analyze the model
    try:
        frame.analyze(check_statics=False)
    except (ValueError, RuntimeError):
        # Handle analysis failures gracefully
        return None

    # Initialize worst-case deflections
    worst_vert_deflection = 0
    vert_combo = ''
    worst_horiz_deflection = 0
    hor_combo = ''

    # Check deflections for each combo
    for combo in data.get('serviceability_load_combinations', []):
        combo_name = combo['name']
        for node in frame.nodes.values():
            dx = abs(node.DX[combo_name])
            dy = abs(node.DY[combo_name])

            # Update worst-case deflections
            if dy > worst_vert_deflection:
                worst_vert_deflection = dy
                vert_combo = combo_name
            if dx > worst_horiz_deflection:
                worst_horiz_deflection = dx
                hor_combo = combo_name

    # Check if deflections are within limits
    if (worst_vert_deflection <= vert_deflection_limit and
        worst_horiz_deflection <= horiz_deflection_limit):
        # Return necessary data
        total_weight = 2 * r_mem['m'] + 2 * c_mem['m']
        return total_weight, rafter_section_name, column_section_name, worst_vert_deflection, vert_combo, worst_horiz_deflection, hor_combo
    else:
        return None

def get_member_lengths(data):
    """Return (Σ rafter_len [m], Σ column_len [m]) from input_data.json."""
    xyz = {n: (nd['x'], nd['y'], nd['z']) for n, nd in data['nodes'].items()}
    r_len = c_len = 0.0
    for m in data['members']:
        xi, yi, zi = xyz[m['i_node']]
        xj, yj, zj = xyz[m['j_node']]
        L = math.sqrt((xj - xi)**2 + (yj - yi)**2 + (zj - zi)**2) / 1_000  # mm → m
        if m['type'].lower() == 'rafter':
            r_len += L
        else:
            c_len += L
    return r_len, c_len

def directional_search(primary, r_list, c_list, r_section_type, c_section_type, member_db, data, r_total_m, c_total_m, vert_limit, horiz_limit):
    """If primary=='rafter': outer=rafters, inner=columns; if primary=='column': outer=columns, inner=rafters."""
    if primary == 'column':
        outer_list, inner_list = c_list, r_list
        outer_type, inner_type = c_section_type, r_section_type
    else:
        outer_list, inner_list = r_list, c_list
        outer_type, inner_type = r_section_type, c_section_type

    best = None
    for o_name in outer_list:
        o_mem = member_db[outer_type][o_name]
        if best:
            key_m_outer = 'c_m' if primary == 'column' else 'r_m'
            key_h_outer = 'c_h' if primary == 'column' else 'r_h'
            if not (o_mem['m'] < best[key_m_outer] and o_mem['h'] > best[key_h_outer]):
                continue

        for i_name in inner_list:
            i_mem = member_db[inner_type][i_name]
            if best:
                key_m_inner = 'r_m' if primary == 'column' else 'c_m'
                key_h_inner = 'r_h' if primary == 'column' else 'c_h'
                if not (i_mem['m'] < best[key_m_inner] and i_mem['h'] > best[key_h_inner]):
                    continue

            if primary == 'column':
                c_name, r_name = o_name, i_name
                c_mem,  r_mem  = o_mem,  i_mem
            else:
                r_name, c_name = o_name, i_name
                r_mem,  c_mem  = o_mem,  i_mem

            if r_mem['b'] > c_mem['b']:
                continue

            frame = build_model(r_mem, c_mem)
            for combo in data['serviceability_load_combinations']:
                frame.add_load_combo(combo['name'], factors=combo['factors'])
            try:
                frame.analyze(check_statics=False)
            except (ValueError, RuntimeError):
                continue

            worst_v = worst_h = 0.0
            for combo in data['serviceability_load_combinations']:
                cn = combo['name']
                for node in frame.nodes.values():
                    worst_v = max(worst_v, abs(node.DY[cn]))
                    worst_h = max(worst_h, abs(node.DX[cn]))
            if worst_v > vert_limit or worst_h > horiz_limit:
                continue

            weight = r_mem['m'] * r_total_m + c_mem['m'] * c_total_m
            if (best is None) or (weight < best['weight']):
                best = {'weight': weight, 'frame': frame, 'r_name': r_name, 'c_name': c_name,
                        'r_m': r_mem['m'], 'r_h': r_mem['h'], 'c_m': c_mem['m'], 'c_h': c_mem['h'],
                        'dy': worst_v, 'dx': worst_h}

        if best:
            key_m_outer = 'c_m' if primary == 'column' else 'r_m'
            if o_mem['m'] >= best[key_m_outer]:
                break

    return best

def sls_check(preferred_section: str, r_section_type: str, c_section_type: str):
    """Runs 'rafter-first' and 'column-first' searches, then returns the single lightest solution."""
    start = time.time()
    member_db = mdb.load_member_database()

    r_list = [sec for sec in member_db[r_section_type] if member_db[r_section_type][sec].get('Preferred','No') == preferred_section]
    c_list = [sec for sec in member_db[c_section_type] if member_db[c_section_type][sec].get('Preferred','No') == preferred_section]
    if not r_list or not c_list:
        raise ValueError(f"No sections flagged as Preferred='{preferred_section}' found.")

    data = import_data('input_data.json')
    r_total_m, c_total_m = get_member_lengths(data)
    vert_limit  = data['frame_data'][0]['rafter_span'] / 300
    horiz_limit = data['frame_data'][0]['eaves_height'] / 300

    best_r = directional_search('rafter', r_list, c_list, r_section_type, c_section_type, member_db, data, r_total_m, c_total_m, vert_limit, horiz_limit)
    best_c = directional_search('column', r_list, c_list, r_section_type, c_section_type, member_db, data, r_total_m, c_total_m, vert_limit, horiz_limit)

    candidates = [b for b in (best_r, best_c) if b]
    if not candidates:
        print("No acceptable section found that satisfies the serviceability limits.")
        return None, None, None, None, None

    best = min(candidates, key=lambda d: d['weight'])
    print(f"► Lightest combination:")
    print(f"   Rafter: {best['r_name']}")
    print(f"   Column: {best['c_name']}")
    print(f"   Total steel: {best['weight']:.1f} kg")
    print(f"   Max Δy: {best['dy']:.2f} mm   (limit {vert_limit:.2f})")
    print(f"   Max Δx: {best['dx']:.2f} mm   (limit {horiz_limit:.2f})")
    print(f"   Search time: {time.time() - start:.3f} s")

    return best['frame'], member_db, r_section_type, c_section_type, (best['r_name'], best['c_name'])

def uls_output(sls_check_output):

    # Use sections from SLS check
    frame_old, member_db, r_section_type, c_section_type, best_section = sls_check_output

    r_mem = member_db[r_section_type][best_section[0]]
    c_mem = member_db[c_section_type][best_section[1]]

    frame = build_model(r_mem, c_mem)

    # Add load combinations
    data = import_data('input_data.json')
    for combo in data.get('load_combinations', []):
        combo_name = combo['name']
        factors = combo['factors']
        frame.add_load_combo(combo_name, factors=factors)

    # Analyze the frame
    frame.analyze(check_statics=False)

    # # Get the maximum strong-axis moment from member 'M1' for load combination '1.4D'
    # my_model.members['M1'].max_moment('Mz', '1.4D')
    #
    # # Get the minimum weak-axis moment from member 'M3' for load combination '1.2D+1.6L'
    # my_model.members['M3'].min_moment('My', '1.2D+1.6L')

    # Print maximum and minimum moments for each member

    # for combo in data.get('load_combinations', []):
    #     member_results = []
    #     print(f"Load combination: {combo['name']}")
    #     for member in frame.members.values():
    #         mz_max = member.max_moment('Mz', combo['name']) / 1000
    #         mz_min = member.min_moment('Mz', combo['name']) / 1000
    #         n_max = member.max_axial(combo['name'])
    #         n_min = member.min_axial(combo['name'])
    #         member_results.append([member.name, round(mz_max, 4), round(mz_min, 4), round(n_max, 4), round(n_min, 4)])
    #     print(tabulate.tabulate(member_results, headers=['Member', 'Max Mz (kNm)', 'Min Mz (kNm)', 'Axial Max (kN)',
    #                                                      'Axial Min (kN)' ], tablefmt='pretty'))

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
    c_section_type = 'H-Sections'  # or 'H-Sections', based on user preference

    frame, member_db, r_section_type, c_section_type, best_section = sls_check(preferred_section, r_section_type, c_section_type)

    #
    uls_output((frame, member_db, r_section_type, c_section_type, best_section))

    if frame is not None:
        render_model(frame)
    else:
        print("Unable to find acceptable sections.")

if __name__ == "__main__":
    main()
