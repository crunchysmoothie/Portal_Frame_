import math
import time
import multiprocessing
import warnings
from concurrent.futures import ProcessPoolExecutor
from scipy.sparse.linalg import MatrixRankWarning
from Pynite import FEModel3D
from Pynite.Visualization import Renderer
from tabulate import tabulate
import member_database as mdb
from strength_checks import (
    member_class_check,
    element_properties,
    member_design,
)
from frame_model import load_portal_frame, PortalFrame

# Weight-ordered batches retain the lightest-pair guarantee while limiting the
# number of PyNite worker processes.
num_cores = min(12, multiprocessing.cpu_count())


def _is_instability_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "singular" in msg
        or "unstable" in msg
        or "rigid body motion" in msg
    )

def import_data(file: str) -> PortalFrame:
    """Load ``file`` and return a :class:`PortalFrame` instance."""
    return load_portal_frame(file)

def build_model(r_mem, c_mem, data: PortalFrame):
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


    # Define materials
    for name, props in data.materials.items():
        frame.add_material(name, props['E'], props['G'], props['nu'], props['rho'])

    # Define nodes
    for name, node in data.nodes.items():
        frame.add_node(name, node.x, node.y, node.z)

    # Define supports
    for node, support in data.supports.items():
        frame.def_support(
            node,
            support.get('DX', False),
            support.get('DY', False),
            support.get('DZ', False),
            support.get('RX', False),
            support.get('RY', False),
            support.get('RZ', False),
        )

    # Define members
    for member in data.members:
        name = member.name
        i_node = member.i_node
        j_node = member.j_node
        material = member.material
        member_type = member.type.lower()

        # Select properties based on member-type
        if member_type == 'rafter':
            frame.add_member(name, i_node, j_node, material, r_mem["Designation"])

        elif member_type == 'column':
            frame.add_member(name, i_node, j_node, material, c_mem["Designation"])
        else:
            raise ValueError(f"Invalid member type '{member['type']}' for member '{name}'")

    # Add nodal loads
    for node in data.nodes.values():
        for load in node.loads:
            frame.add_node_load(node.name, load.direction, load.magnitude, load.case)

    # Add member distributed loads
    for m in data.members:
        for load in m.loads:
            # PyNite visualization fails on zero-magnitude distributed loads.
            # They are analytically irrelevant, so skip them.
            if abs(load.w1) < 1e-12 and abs(load.w2) < 1e-12:
                continue
            if (
                load.x1 is not None and load.x2 is not None
                and load.x2 - load.x1 <= 1e-6
            ):
                continue
            frame.add_member_dist_load(
                m.name,
                load.direction,
                load.w1,
                load.w2,
                load.x1,
                load.x2,
                load.case,
            )

        for load in m.point_loads:
            frame.add_member_pt_load(
                m.name,
                load.direction,
                load.magnitude,
                load.x,
                load.case,
            )

    # Add member self-weight (optional, adjust as needed)
    frame.add_member_self_weight('FY', -1, 'D')  # Example: Adding self-weight in FY direction

    # Add rotational springs
    for spring in data.rotational_springs:
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
    frame = build_model(r_mem, c_mem, data)

    # add serviceability and ultimate combos
    for SLS_combo in data.serviceability_load_combinations:
        frame.add_load_combo(SLS_combo['name'], SLS_combo['factors'])

    for ULS_combo in data.load_combinations:
        frame.add_load_combo(ULS_combo['name'], ULS_combo['factors'])

    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=MatrixRankWarning)
            frame.analyze(check_statics=False)
    except Exception as exc:
        if _is_instability_error(exc):
            return None
        # Data errors and broken load cases must remain visible. Treating every
        # ValueError/RuntimeError as a failed trial section can hide unsafe input.
        raise

    # --- deflection checks --------------------------------------------------
    worst_v = worst_h = 0.0
    worst_v_combo = worst_h_combo = ""

    for combo in data.serviceability_load_combinations:
        cn = combo['name']
        for nd in frame.nodes.values():
            dx = abs(nd.DX[cn])
            dy = abs(nd.DY[cn])
            # PyNite can complete a singular analysis with NaN results. Since
            # comparisons with NaN are false, those models previously appeared
            # to have zero deflection and were incorrectly accepted.
            if not math.isfinite(float(dx)) or not math.isfinite(float(dy)):
                return None
            if dy > worst_v:
                worst_v, worst_v_combo = dy, cn
            if dx > worst_h:
                worst_h, worst_h_combo = dx, cn

    if worst_v > v_lim or worst_h > h_lim:
        return None   # structure fails serviceability

    if not member_design_checks(frame, r_type, r_mem, c_type, c_mem, data, member_db):
        return None

    # --- weight (kN) --------------------------------------------------------
    weight = round(r_mem['m'] * r_total_m + c_mem['m'] * c_total_m, 1)

    return (weight,          # 0  – used for min()
            r_name,          # 1
            c_name,          # 2
            worst_v,         # 3
            worst_v_combo,   # 4
            worst_h,         # 5
            worst_h_combo)   # 6

def get_member_lengths(data: PortalFrame):
    """Return total rafter and column lengths in metres."""
    r_len = 0.0
    c_len = 0.0
    for member in data.members:
        if member.type == 'rafter':
            r_len += member.length
        if member.type == 'column':
            c_len += member.length

    return r_len, c_len

def directional_search(primary, r_list, c_list, r_section_type, c_section_type,
                       member_db, data: PortalFrame, r_total_m, c_total_m,
                       vert_limit, horiz_limit, num_core):

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

            # Apply the flange-width compatibility rule before constructing
            # FE-analysis tasks. This can remove a substantial part of the
            # candidate matrix for large frames.
            if member_db[r_section_type][r_name]["b"] > (
                member_db[c_section_type][c_name]["b"] + 3.5
            ):
                continue

            tasks.append((r_section_type, r_name,
             c_section_type, c_name,
             member_db, data,
             vert_limit, horiz_limit,
             r_total_m, c_total_m))

    if not tasks:          # nothing to do
        return None

    tasks.sort(key=lambda task: (
        member_db[task[0]][task[1]]["m"] * r_total_m
        + member_db[task[2]][task[3]]["m"] * c_total_m
    ))

    acceptable = []
    workers = max(1, min(int(num_core), len(tasks)))
    print(f"Checking {len(tasks)} compatible section pairs using {workers} worker(s)...")
    if workers == 1:
        for task in tasks:
            result = analyze_combination(task)
            if result is not None:
                acceptable.append(result)
                # The first passing pair is globally lightest because the
                # candidate matrix is ordered by total steel mass.
                break
    else:
        # Evaluate small, mass-ordered batches. Waiting for each complete batch
        # preserves the guarantee that the first passing result is globally
        # lightest, while avoiding submission/analysis of the entire matrix.
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for start in range(0, len(tasks), workers):
                batch = tasks[start:start + workers]
                results = list(ex.map(analyze_combination, batch))
                passing = [result for result in results if result is not None]
                if passing:
                    acceptable.extend(passing)
                    break

    if not acceptable:
        return None

    # tuple order: (wt, r_name, c_name, dy, dy_comb, dx, dx_comb)
    wt, r_name, c_name, dy, dy_comb, dx, dx_comb = min(acceptable, key=lambda r: r[0])

    # --- rebuild the FE model for the best pair ------------------------
    r_mem = mdb.member_properties(r_section_type, r_name, member_db)
    c_mem = mdb.member_properties(c_section_type, c_name, member_db)
    best_frame = build_model(r_mem, c_mem, data)

    for combo in data.serviceability_load_combinations:
        best_frame.add_load_combo(combo['name'], combo['factors'])

    for combo in data.load_combinations:  # e.g. '1.1 DL + 1.0 LL'
        best_frame.add_load_combo(combo['name'], combo['factors'])

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=MatrixRankWarning)
        best_frame.analyze(check_statics=False)

    return {
        'weight': wt,
        'frame': best_frame,  # ← now an actual Pynite model
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


def section_candidates(
    member_db,
    section_type,
    preferred_section="Yes",
    selected_section=None,
):
    """Return one forced section or the normal preferred automatic candidates."""

    family = member_db.get(section_type)
    if family is None:
        raise ValueError(f"Unknown portal section family {section_type!r}.")
    selected = str(selected_section or "").strip()
    if selected and not selected.lower().startswith("automatic"):
        if selected not in family:
            raise ValueError(
                f"Section {selected!r} is not available in {section_type}."
            )
        return [selected]
    return [
        name
        for name, properties in family.items()
        if properties.get("Preferred", "No") == preferred_section
    ]

def sls_check(
    preferred_section: str,
    r_section_type: str,
    c_section_type: str,
    input_path="input_data.json",
    selected_rafter_section=None,
    selected_column_section=None,
):
    """Runs 'rafter-first' and 'column-first' searches, then returns the single lightest solution."""
    start = time.time()
    member_db = mdb.load_member_database()

    r_list = section_candidates(
        member_db, r_section_type, preferred_section, selected_rafter_section
    )
    c_list = section_candidates(
        member_db, c_section_type, preferred_section, selected_column_section
    )
    if not r_list or not c_list:
        raise ValueError(f"No sections flagged as Preferred='{preferred_section}' found.")

    data = import_data(str(input_path))
    r_total_m, c_total_m = get_member_lengths(data)
    vert_limit = data.frame_data[0]['gable_width'] / 180
    horiz_limit = data.frame_data[0]['eaves_height'] / 180

    # Search the full rafter/column matrix once in ascending mass order.
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
    candidates = [best_r] if best_r else []
    if not candidates:
        print("No acceptable section found that satisfies the serviceability limits.")
        print(f"Search time: {time.time() - start:.3f} s")
        return None, None, member_db, r_section_type, c_section_type, None

    best = min(candidates, key=lambda d: d['weight'])
    print("Lightest combination:")
    print(f"   Rafter: {best['r_name']}")
    print(f"   Column: {best['c_name']}")
    print(f"   Total steel: {best['weight']:.1f} kg")
    print(f"   Max dy: {best['dy']:.2f} mm   (limit {vert_limit:.2f})")
    print(f"   dy Load Combination: {best['dy_comb']}")
    print(f"   Max dx: {best['dx']:.2f} mm   (limit {horiz_limit:.2f})")
    print(f"   dx Load Combination: {best['dx_comb']}")
    print(f"   Search time: {time.time() - start:.3f} s")

    # --- Output the worst deflections for each SLS load case ---------------------
    table_data = []
    for combo in data.serviceability_load_combinations:
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

    # A direction can legitimately have zero displacement in every combination,
    # leaving its governing-combination name empty. Always return a real,
    # analysed SLS combination for deformation rendering.
    render_combo = best['dx_comb'] or best['dy_comb']
    if not render_combo and data.serviceability_load_combinations:
        render_combo = data.serviceability_load_combinations[0]['name']

    return best['frame'], render_combo, member_db, r_section_type, c_section_type, (best['r_name'], best['c_name'])

def extract_member_actions(frame, r_type, r_mem, c_type, c_mem,
                           data: PortalFrame, combo):
    """Extract final member actions once for analysis and downstream reports."""

    steel_grade = data.steel_grade
    fr = data.frame_data[0]
    rafter_span = fr['gable_width'] / (2 if fr['building_roof'] == "Duo Pitched" else 1)
    raf_kx = rafter_span
    internal_loads = []

    for mem in data.members:
        l = mem.length
        sec_type = r_type if mem.type == "rafter" else c_type
        mem_type = mem.type
        t_sec = r_mem['Designation'] if mem.type == 'rafter' else c_mem['Designation']
        Cu = round(frame.members[mem.name].max_axial(combo), 3)
        Mx_max = round(max(frame.members[mem.name].max_moment('Mz', combo),
                          abs(frame.members[mem.name].min_moment('Mz', combo)))/1000, 3)
        Mx_top = round(frame.members[mem.name].moment('Mz', 0, combo)/1000, 3)
        Mx_bot = round(frame.members[mem.name].moment('Mz', l * 999, combo)/1000, 3)

        w1, w2 = element_properties(Mx_max, Mx_top, Mx_bot)
        lx = (raf_kx if mem_type == 'rafter' else data.frame_data[0]['eaves_height']) / 1000
        kx = 1.0 if mem_type == 'rafter' else 1.2
        ly = l
        ky = 1.0

        internal_loads.append({
            'Name': mem.name,
            'kly': ky * ly,
            'klx': kx * lx,
            'kx': kx,
            'lx': lx,
            'ky': ky,
            'ly': ly,
            'type': mem_type,
            'section_type': sec_type,
            'section': t_sec,
            'Cu': Cu,
            'Class': member_class_check(Cu, r_mem if mem.type == 'rafter' else c_mem, steel_grade),
            'Mx_max': Mx_max,
            'Mx_top': Mx_top,
            'Mx_bot': Mx_bot,
            'w1': w1,
            'w2': w2
        })

    return internal_loads


def internal_forces(frame, r_type, r_mem, c_type, c_mem, data: PortalFrame, combo, md):
    internal_loads = extract_member_actions(
        frame, r_type, r_mem, c_type, c_mem, data, combo
    )
    member_des = []
    mat_props = data.steel_grade

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

def member_design_checks(frame, r_type, r_mem, c_type, c_mem, data, md):
    """Return True if all members pass design checks for all ULS combos."""
    for combo in data.load_combinations:
        results = internal_forces(frame, r_type, r_mem, c_type, c_mem,
                                 data, combo['name'], md)
        for res in results:
            ratios = (res['CSS'], res['OMS'], res['LTB'][0], res['LTB'][1])
            # Never interpret NaN or infinity as a passing utilisation ratio.
            if not all(math.isfinite(float(ratio)) for ratio in ratios):
                return False
            if (
                res['CSS'] > 1
                or res['OMS'] > 1
                or res['LTB'][0] > 1
                or res['LTB'][1] > 1
            ):
                return False
    return True

def uls_results(frame, r_type, r_mem, c_type, c_mem, data, md,
                calculation_results=None):
    """Print stored ULS results, falling back to direct calculation if needed."""

    if calculation_results is not None:
        table = [
            [
                result.member,
                result.load_combination,
                result.axial_action,
                result.governing_check,
                round(result.governing_ratio, 3),
                result.status,
            ]
            for result in calculation_results
        ]
        print(
            tabulate(
                table,
                headers=[
                    'Member', 'Load Case', 'Axial Action',
                    'Governing Check', 'Utilisation', 'Status',
                ],
                tablefmt='pretty',
            )
        )
        return

    table = []
    for combo in data.load_combinations:
        results = internal_forces(
            frame, r_type, r_mem, c_type, c_mem, data, combo['name'], md
        )
        for res in results:
            table.append([
                res['Name'],
                combo['name'],
                round(res['CSS'], 3),
                round(res['OMS'], 3),
                round(res['LTB'][0], 3),
                round(res['LTB'][1], 3),
            ])

    print(
        tabulate(
            table,
            headers=[
                'Member',
                'Load Case',
                'CSS',
                'OMS',
                'LTB(Mode1)',
                'LTB (Mode 2)',
            ],
            tablefmt='pretty',
        )
    )

def render_model(frame, combo):
    """Render the analysed model with nodal displacement labels and loads."""

    available_combos = getattr(frame, "load_combos", {})

    def _has_displacement_results(combo_name):
        if not combo_name or combo_name not in available_combos:
            return False
        for node in frame.nodes.values():
            displacements = getattr(node, "DX", {})
            try:
                if combo_name in displacements:
                    return True
            except TypeError:
                continue
        return False

    if not _has_displacement_results(combo):
        combo = next(
            (name for name in available_combos if _has_displacement_results(name)),
            None,
        )
    if combo is None:
        print("Warning: No analysed load combination is available to render.")
        return

    def _get_disp(comp, combo_name):
        try:
            return float(comp.get(combo_name, 0.0))
        except AttributeError:
            try:
                return float(comp[combo_name])
            except Exception:
                return 0.0

    original_node_names = {key: node.name for key, node in frame.nodes.items()}
    original_member_dist_loads = {}
    try:
        combo_factors = {}
        combo_obj = frame.load_combos.get(combo) if hasattr(frame, "load_combos") else None
        if combo_obj is not None and hasattr(combo_obj, "factors"):
            combo_factors = combo_obj.factors

        # Keep only distributed loads that are active in the selected combo.
        for key, member in frame.members.items():
            dist_loads = getattr(member, "DistLoads", [])
            filtered = []
            for load in dist_loads:
                # PyNite stores distributed loads as tuples:
                # (direction, w1, w2, x1, x2, case)
                case = load[5] if isinstance(load, tuple) and len(load) > 5 else None
                w1 = load[1] if isinstance(load, tuple) and len(load) > 2 else 0.0
                w2 = load[2] if isinstance(load, tuple) and len(load) > 2 else 0.0
                x1 = load[3] if isinstance(load, tuple) and len(load) > 4 else None
                x2 = load[4] if isinstance(load, tuple) and len(load) > 4 else None

                # Skip zero-magnitude loads.
                if abs(w1) < 1e-12 and abs(w2) < 1e-12:
                    continue

                # Avoid PyNite Visualization dividing by a zero glyph length.
                if x1 is not None and x2 is not None and x2 - x1 <= 1e-6:
                    continue

                # For combo rendering, skip loads from cases with zero factor.
                if case is not None and combo_factors:
                    if abs(combo_factors.get(case, 0.0)) < 1e-12:
                        continue

                filtered.append(load)

            if len(filtered) != len(dist_loads):
                original_member_dist_loads[key] = dist_loads
                member.DistLoads = filtered

        for key, node in frame.nodes.items():
            dx = _get_disp(node.DX, combo)
            dy = _get_disp(node.DY, combo)
            dz = _get_disp(node.DZ, combo)
            node.name = f"{original_node_names[key]} DX={dx:.2f} DY={dy:.2f} DZ={dz:.2f}"

        rndr = Renderer(frame)
        rndr.annotation_size = 80
        rndr.render_loads = True
        rndr.deformed_shape = True
        rndr.deformed_scale = 20
        rndr.labels = True
        rndr.combo_name = combo
        try:
            rndr.render_model()
        except (OverflowError, ZeroDivisionError):
            print(
                "Warning: Load glyph rendering failed in PyNite. "
                "Retrying without load glyphs."
            )
            rndr.render_loads = False
            rndr.render_model()
    finally:
        for key, node in frame.nodes.items():
            node.name = original_node_names[key]
        for key, dist_loads in original_member_dist_loads.items():
            frame.members[key].DistLoads = dist_loads

def main(
    render=True,
    snapshot_path="output/analysis/analysis_results.json",
    input_path="input_data.json",
    project_metadata=None,
):
    """Run one analysis, store its complete results, and optionally render it."""

    preferred_section = 'Yes'
    data = import_data(str(input_path))
    frame_input = data.frame_data[0]
    r_section_type = frame_input.get('rafter_section_type', 'I-Sections')
    c_section_type = frame_input.get('column_section_type', 'I-Sections')
    selected_rafter = frame_input.get('rafter_section')
    selected_column = frame_input.get('column_section')

    frame, combo, member_db, r_section_typ, c_section_typ, best_section = sls_check(
        preferred_section,
        r_section_type,
        c_section_type,
        input_path=input_path,
        selected_rafter_section=selected_rafter,
        selected_column_section=selected_column,
    )


    if frame is not None:
        r_mem = mdb.member_properties(r_section_typ, best_section[0], member_db)
        c_mem = mdb.member_properties(c_section_typ, best_section[1], member_db)
        actions_by_combination = {
            load_combination['name']: extract_member_actions(
                frame,
                r_section_typ,
                r_mem,
                c_section_typ,
                c_mem,
                data,
                load_combination['name'],
            )
            for load_combination in data.load_combinations
        }

        # Import locally so multiprocessing section-search workers do not load
        # report/export dependencies. The snapshot is written before rendering.
        from analysis_snapshot import create_analysis_snapshot, write_analysis_snapshot
        from bracing_design import design_bracing_system
        from design_calculations import build_calculation_sheet_data_from_frame

        bracing_results = design_bracing_system(data, member_db)

        calculation_data = build_calculation_sheet_data_from_frame(
            frame=frame,
            data=data,
            member_db=member_db,
            actions_by_combination=actions_by_combination,
            rafter_section_type=r_section_typ,
            column_section_type=c_section_typ,
            rafter_section=best_section[0],
            column_section=best_section[1],
            bracing_design=bracing_results,
            input_path=input_path,
            project_metadata=project_metadata,
        )
        snapshot = create_analysis_snapshot(
            input_path, calculation_data.to_dict()
        )
        written_snapshot = write_analysis_snapshot(snapshot, snapshot_path)
        print(f"Analysis results written to {written_snapshot.resolve()}")

        uls_results(
            frame, r_section_typ, r_mem, c_section_typ, c_mem, data, member_db,
            calculation_results=calculation_data.members,
        )
        if render:
            render_model(frame, combo)
        return written_snapshot
    else:
        print("Unable to find acceptable sections.")
        return None

if __name__ == "__main__":
    main()
