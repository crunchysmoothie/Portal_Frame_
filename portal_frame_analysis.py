import json
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from Pynite import FEModel3D
from Pynite.Visualization import Renderer
from tabulate import tabulate
import member_database as mdb
from strength_checks import member_class_check, element_properties, member_design

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

        steel_grade = data.get('steel_grade', False)

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
            'geometry_parameters': geometry_parameters,
            'steel_grade': steel_grade
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
        x1 = None
        x2 = None
        if 'x1' in member_load:
            x1 = member_load['x1']
        if 'x2' in member_load:
            x2 = member_load['x2']
        case = member_load.get('case', None)  # Optional
        frame.add_member_dist_load(member_name, direction, w1, w2, x1, x2, case)

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

# def analyze_combination_uls(args):
#     """
#     Analyse ONE rafter/column pair for all serviceability load-combinations
#     and return the lightest acceptable option, or None if it fails limits.
#     """
#     (r_type, r_name,
#      c_type, c_name,
#      member_db, data) = args
#
#     # --- section properties -------------------------------------------------
#     r_mem = mdb.member_properties(r_type, r_name, member_db)
#     c_mem = mdb.member_properties(c_type, c_name, member_db)
#
#     # ❶ Reject combos where the rafter flange is wider than the column flange
#     if r_mem['b'] > c_mem['b'] + 3.5:
#         return None
#
#     # --- build and analyse FE model ----------------------------------------
#     frame = build_model(r_mem, c_mem)
#
#     for ULS_combo in data['load_combinations']:
#         frame.add_load_combo(ULS_combo['name'], ULS_combo['factors'])
#
#     try:
#         frame.analyze(check_statics=False)
#     except (ValueError, RuntimeError):
#         return None
#
#     uls_out = []
#     for combo_u in data['load_combinations']:
#         mem_d = internal_forces(frame, r_type, r_mem, c_type, c_mem, data, combo_u['name'], member_db)
#         for mem in mem_d:
#             if mem["CSS"] > 1 or mem['OMS'] > 1 or mem['LTB'][0] > 1 or mem['LTB'][1] > 1:
#                 uls_out.append({
#                     'Member': mem['name'],
#                     'Combo': combo_u['name'],
#                     'CSS': mem['CSS'],
#                     'OMS': mem['OMS'],
#                     'LTB': mem['LTB']
#                 })
#                 return None
#
#     return uls_out

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
    with ProcessPoolExecutor(max_workers=(num_core-4)) as ex:
        futures = [ex.submit(analyze_combination, t) for t in tasks]
        for fut in as_completed(futures):
            result = fut.result()
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

    print("Rafter-first Done")

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

    print("Column-first Done")

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

    # --- Output the worst deflections for each SLS load case ---------------------
    table_data = []
    for combo in data['serviceability_load_combinations']:
        cn = combo['name']
        worst_dx = 0.0
        worst_dx_node = ''
        worst_dy = 0.0
        worst_dy_node = ''
        for nd in best['frame'].nodes.values():
            dx = abs(nd.DX[cn])
            dy = abs(nd.DY[cn])
            if dx > worst_dx:
                worst_dx = dx
                worst_dx_node = nd.name
            if dy > worst_dy:
                worst_dy = dy
                worst_dy_node = nd.name
        table_data.append([
            cn,
            round(worst_dx, 2),
            worst_dx_node,
            round(worst_dy, 2),
            worst_dy_node
        ])

    print(tabulate(table_data,
                   headers=['Load Case', 'Deflection in X', 'Node',
                            'Deflection in Y', 'Node'],
                   tablefmt='pretty'))

    return best['frame'], best['dx_comb'], member_db, r_section_type, c_section_type, (best['r_name'], best['c_name'])

def internal_forces(frame, r_type, r_mem, c_type, c_mem, data, combo, md):
    steel_grade = data['steel_grade']
    fr = data['frame_data'][0]
    rafter_span = fr['gable_width'] / (2 if fr['building_roof'] == "Duo Pitched" else 1)
    col_kx = 1.2 * data['frame_data'][0]['eaves_height']
    raf_kx = rafter_span
    internal_loads = []
    member_des = []
    mat_props = data['steel_grade']

    for mem in data['members']:
        l = mem['length']
        sec_type = r_type if mem['type'] == "rafter" else c_type
        mem_type = mem['type']
        t_sec = r_mem['Designation'] if mem['type'] == 'rafter' else c_mem['Designation']
        Cu = round(frame.members[mem['name']].max_axial(combo), 3)
        Mx_max = round(max(frame.members[mem['name']].max_moment('Mz', combo),
                          abs(frame.members[mem['name']].min_moment('Mz', combo)))/1000, 3)
        Mx_top = round(frame.members[mem['name']].moment('Mz', 0, combo)/1000, 3)
        Mx_bot = round(frame.members[mem['name']].moment('Mz', l * 1000, combo)/1000, 3)

        w1, w2 = element_properties(Mx_max, Mx_top, Mx_bot)

        internal_loads.append({
            'Name': mem['name'],
            'kly': l,
            'klx': (raf_kx if mem_type == 'rafter' else col_kx)/1000,
            'type': mem_type,
            'section_type': sec_type,
            'section': t_sec,
            'Cu': Cu,
            'Class': member_class_check(Cu, r_mem if mem['type'] == 'rafter' else c_mem, steel_grade),
            'Mx_max': Mx_max,
            'Mx_top': Mx_top,
            'Mx_bot': Mx_bot,
            'w1': w1,
            'w2': w2
        })

    for memb in internal_loads:
        mem_props = mdb.member_properties(memb['section_type'], memb['section'], md)
        CSS, OMS, LTB = member_design(mem_props, memb, mat_props[0])
        member_des.append({
            'Name': memb['Name'],
            'CSS': CSS,
            'OMS': OMS,
            'LTB': LTB
        })

    return member_des

def render_model(frame, combo):
    # Render the model
    rndr = Renderer(frame)
    rndr.annotation_size = 80
    rndr.render_loads = True
    rndr.deformed_shape = True
    rndr.deformed_scale = 20
    rndr.combo_name = combo  # Adjust as necessary
    rndr.render_model()

def main():
    preferred_section = 'Yes'      # or 'No', based on user preference
    r_section_type = 'I-Sections'  # or 'H-Sections', based on user preference
    c_section_type = 'I-Sections'  # or 'H-Sections', based on user preference

    frame, combo, member_db, r_section_typ, c_section_typ, best_section = sls_check(preferred_section, r_section_type, c_section_type)

    if frame is not None:
        print("Done")
        render_model(frame, combo)
    else:
        print("Unable to find acceptable sections.")

if __name__ == "__main__":
    main()
