import json
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from Pynite import FEModel3D
from Pynite.Visualization import Renderer
import member_database as mdb
import tabulate
import math
import os

num_cores = multiprocessing.cpu_count()

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

    # Add Sections to Frame
    try:
        frame.add_section(r_mem["Designation"], r_mem["A"] * 1e3, r_mem["Iy"] * 1e6, r_mem["Ix"] * 1e6, r_mem["J"] * 1e3)
    except (NameError, AttributeError):
        pass

    try:
        frame.add_section(c_mem["Designation"], c_mem["A"] * 1e3, c_mem["Iy"] * 1e6, c_mem["Ix"] * 1e6, c_mem["J"] * 1e3)
    except (NameError, AttributeError):
        pass

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

    # Define members
    for member in data['members']:
        name = member['name']
        i_node = member['i_node']
        j_node = member['j_node']
        material = member['material']
        member_type = member['type'].lower()  # 'rafter' or 'column'

        # Select properties based on member type
        if member_type == 'rafter':
            frame.add_member(name, i_node, j_node, material, r_mem["Designation"])

        elif member_type == 'column':
            frame.add_member(name, i_node, j_node, material, c_mem["Designation"])
        else:
            raise ValueError(f"Invalid member type '{member['type']}' for member '{name}'")

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
    Analyse ONE rafter/column pair for all serviceability load-combinations
    and return the lightest acceptable option, or None if it fails limits.
    """
    (r_type, r_name,
     c_type, c_name,
     member_db, data,
     v_lim, h_lim,
     r_total_m, c_total_m) = args

    # --- section properties -------------------------------------------------
    r_mem = mdb.member_properties(r_type, r_name, member_db)
    c_mem = mdb.member_properties(c_type, c_name, member_db)

    # ❶ Reject combos where the rafter flange is wider than the column flange
    if r_mem['b'] > c_mem['b'] + 3.5:
        return None

    # --- build and analyse FE model ----------------------------------------
    frame = build_model(r_mem, c_mem)

    # add serviceability combos (they’re already defined in *data*)
    for SLS_combo in data['serviceability_load_combinations']:
        frame.add_load_combo(SLS_combo['name'], SLS_combo['factors'])

    try:
        frame.analyze(check_statics=False)
    except (ValueError, RuntimeError):
        # Solver failed → discard this combination
        return None

    # --- deflection checks --------------------------------------------------
    worst_v = worst_h = 0.0
    worst_v_combo = worst_h_combo = ""

    for combo in data['serviceability_load_combinations']:
        cn = combo['name']
        for nd in frame.nodes.values():
            dx = abs(nd.DX[cn])
            dy = abs(nd.DY[cn])
            if dy > worst_v:
                worst_v, worst_v_combo = dy, cn
            if dx > worst_h:
                worst_h, worst_h_combo = dx, cn

    if worst_v > v_lim or worst_h > h_lim:
        return None   # fails serviceability

    # --- weight (kN) --------------------------------------------------------
    weight = round(r_mem['m'] * r_total_m + c_mem['m'] * c_total_m, 1)

    return (weight,          # 0  – used for min()
            r_name,          # 1
            c_name,          # 2
            worst_v,         # 3
            worst_v_combo,   # 4
            worst_h,         # 5
            worst_h_combo)   # 6

def get_member_lengths(data):
    """Return (Σ rafter_len [m], Σ column_len [m]) from input_data.json."""
    r_len = 0
    c_len = 0
    for member in data['members']:
        if member['type'] == 'rafter':
            r_len += member['length']
        if member['type'] == 'column':
            c_len += member['length']

    return r_len, c_len

def directional_search(primary, r_list, c_list, r_section_type, c_section_type,member_db, data,r_total_m, c_total_m, vert_limit, horiz_limit, num_core):

    # Decide which list is the outer loop
    if primary == 'column':
        outer_list, inner_list = c_list, r_list
        outer_type, inner_type = c_section_type, r_section_type
    else:
        outer_list, inner_list = r_list, c_list
        outer_type, inner_type = r_section_type, c_section_type

    tasks = []
    for o_name in outer_list:
        for i_name in inner_list:
            if primary == 'column':
                c_name, r_name = o_name, i_name
            else:
                r_name, c_name = o_name, i_name

            tasks.append((r_section_type, r_name,
             c_section_type, c_name,
             member_db, data,
             vert_limit, horiz_limit,
             r_total_m, c_total_m))

    if not tasks:          # nothing to do
        return None


    acceptable = []
    with ProcessPoolExecutor(max_workers=(num_core-8)) as ex:
        futures = [ex.submit(analyze_combination, t) for t in tasks]
        for fut in as_completed(futures):
            result = fut.result()
            print(result)
            if result is not None:
                acceptable.append(result)

    if not acceptable:
        return None

    # tuple order: (wt, r_name, c_name, dy, dy_comb, dx, dx_comb)
    wt, r_name, c_name, dy, dy_comb, dx, dx_comb = min(acceptable, key=lambda r: r[0])

    # --- rebuild the FE model for the best pair ------------------------
    r_mem = mdb.member_properties(r_section_type, r_name, member_db)
    c_mem = mdb.member_properties(c_section_type, c_name, member_db)
    best_frame = build_model(r_mem, c_mem)

    for combo in data['serviceability_load_combinations']:
        best_frame.add_load_combo(combo['name'], combo['factors'])

    for combo in data['load_combinations']:  # e.g. '1.1 DL + 1.0 LL'
        best_frame.add_load_combo(combo['name'], combo['factors'])

    best_frame.analyze(check_statics=False)

    return {
        'weight': wt,
        'frame': best_frame,  # ← now an actual PyNite model
        'r_name': r_name,
        'c_name': c_name,
        'r_m': r_mem['m'],
        'r_h': r_mem['h'],
        'c_m': c_mem['m'],
        'c_h': c_mem['h'],
        'dy': dy,
        'dy_comb': dy_comb,
        'dx': dx,
        'dx_comb': dx_comb
    }

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
    vert_limit  = data['frame_data'][0]['gable_width'] / 300
    horiz_limit = data['frame_data'][0]['eaves_height'] / 300

    # ❶ Search by fixing rafters first, then columns
    best_r = directional_search(
        'rafter',  # primary search direction
        r_list, c_list,  # candidate names
        r_section_type, c_section_type,
        member_db, data,
        r_total_m, c_total_m,  # totals still needed for weight ranking
        vert_limit, horiz_limit,
        num_cores
    )

    # ❷ Search by fixing columns first, then rafters
    best_c = directional_search(
        'column',
        r_list, c_list,
        r_section_type, c_section_type,
        member_db, data,
        r_total_m, c_total_m,
        vert_limit, horiz_limit,
        num_cores
    )

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
    print(f"   Δy Load Combination: {best['dy_comb']}")
    print(f"   Max Δx: {best['dx']:.2f} mm   (limit {horiz_limit:.2f})")
    print(f"   Δx Load Combination: {best['dx_comb']}")
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
    rndr.combo_name = '1.1 DL + 0.3 LL + 0.6 W0_0.2D'  # Adjust as necessary
    rndr.render_model()

def main():
    preferred_section = 'Yes'      # or 'No', based on user preference
    r_section_type = 'I-Sections'  # or 'H-Sections', based on user preference
    c_section_type = 'I-Sections'  # or 'H-Sections', based on user preference

    frame, member_db, r_section_typ, c_section_typ, best_section = sls_check(preferred_section, r_section_type, c_section_type)

    # uls_output((frame, member_db, r_section_typ, c_section_typ, best_section))

    if frame is not None:
        print("Pass")
        render_model(frame)
    else:
        print("Unable to find acceptable sections.")

if __name__ == "__main__":
    main()
