import json
from pathlib import Path
import math
from wind_loads import wind_out
from internal_pressure import normalize_design_mode, resolve_internal_pressure

# Function to generate nodes based on the portal frame structure with static values
def generate_nodes(b_data):
    eaves_height = b_data['eaves_height']
    apex_height = b_data['apex_height']
    gable_width = b_data['gable_width']

    nodes = []
    num_vertical = b_data['col_bracing_spacing'] + 1

    # Generate nodes for Duo Pitched type
    if b_data["building_roof"] == "Duo Pitched":
        # Generate 3 vertical nodes on the left side
        for i in range(num_vertical):
            node = {
                "name": f"N{i + 1}",
                "x": 0,
                "y": round(i * (eaves_height / (num_vertical - 1)), 2),
                "z": 0
            }
            nodes.append(node)

        # Generate 4 diagonal nodes for the rafter section
        num_diagonal = b_data['rafter_bracing_spacing'] * 2
        for i in range(1, num_diagonal):
            x = round(i * (gable_width / num_diagonal), 2)
            y = round(
                eaves_height + ((apex_height - eaves_height) * (1 - abs(i - (num_diagonal / 2)) / (num_diagonal / 2))),
                2)
            node = {
                "name": f"N{num_vertical + i}",
                "x": x,
                "y": y,
                "z": 0
            }
            nodes.append(node)

        # Generate 3 vertical nodes on the right side
        for i in range(num_vertical):
            node = {
                "name": f"N{num_vertical + num_diagonal + i}",
                "x": gable_width,
                "y": round(eaves_height - i * (eaves_height / (num_vertical - 1)), 2),
                "z": 0
            }
            nodes.append(node)

    # Generate nodes for Mono-Pitched type
    elif b_data["building_roof"] == "Mono Pitched":
        # Generate 3 vertical nodes on the left side
        for i in range(num_vertical):
            node = {
                "name": f"N{i + 1}",
                "x": 0,
                "y": round(i * (eaves_height / (num_vertical - 1)), 2),
                "z": 0
            }
            nodes.append(node)

        # Generate 4 diagonal nodes for the rafter section for a single slope
        num_diagonal = 4
        for i in range(1, num_diagonal + 1):
            x = round(i * (gable_width / num_diagonal), 2)
            y = round(eaves_height + (apex_height - eaves_height) * (i / num_diagonal), 2)
            node = {
                "name": f"N{num_vertical + i}",
                "x": x,
                "y": y,
                "z": 0
            }
            nodes.append(node)

        # Generate 3 vertical nodes on the right side
        for i in range(1, num_vertical):
            node = {
                "name": f"N{num_vertical + num_diagonal + i}",
                "x": gable_width,
                "y": round(apex_height - i * (apex_height / (num_vertical - 1)), 2),
                "z": 0
            }
            nodes.append(node)

    return nodes

def generate_supports(nodes):

    supports = [
        {"node": nodes[0]["name"], "DX": True, "DY": True, "DZ": True, "RX": False, "RY": False, "RZ": False},
        {"node": nodes[-1]["name"], "DX": True, "DY": True, "DZ": True, "RX": False, "RY": False, "RZ": False}
    ]

    return supports

def generate_members(nodes):
    members = []
    num_nodes = len(nodes)

    # Create members between consecutive nodes
    for i in range(1, num_nodes):
        xi = nodes[i - 1]['x']
        yi = nodes[i - 1]['y']
        xj = nodes[i]['x']
        yj = nodes[i]['y']
        member = {
            "name": f"M{i}",
            "i_node": nodes[i - 1]["name"],
            "j_node": nodes[i]["name"],
            "material": "Steel_S355",
            "type": "rafter" if xi != xj else "column",
            "length": round(math.sqrt((xj-xi)**2 + (yj-yi)**2) / 1_000, 3)
        }
        members.append(member)

    return members

def generate_spring_supports(nodes):
    rotational_springs = [{"node": nodes[0]["name"], "direction": "RZ", "stiffness": 10E6},
                          {"node": nodes[-1]["name"], "direction": "RZ", "stiffness": 10E6}]
    return rotational_springs

def generate_nodal_loads(nodes):
    apex_node = nodes[len(nodes) // 2]
    nodal_loads = [{"node": apex_node["name"], "direction": "FY", "magnitude": -10, "case": "CR"}]

    return nodal_loads

def steel_prop(grade):
    pro = {
        "Steel_S355": {"fy": 355, "E": 200, "G": 77, "nu": 0.3, "rho": 7.85e-08},
        "Steel_S275": {"fy": 275, "E": 200, "G": 77, "nu": 0.3, "rho": 7.85e-08}
    }
    return pro[grade]

def add_materials():
    materials = [{"name": "Steel_S355", "Fy": 355, "E": 200, "G": 80, "nu": 0.3, "rho": 7.85e-08},
        {"name": "Steel_S275", "Fy": 275, "E": 200, "G": 80, "nu": 0.3, "rho": 7.85e-08}]

    return materials

PRE_2019_COMBINATIONS = "Pre-2019"
SANS_2019_COMBINATIONS = "SANS 10160-1:2019"
LOAD_COMBINATION_STANDARDS = (PRE_2019_COMBINATIONS, SANS_2019_COMBINATIONS)


def _wind_factor(load_combination_standard):
    """Return the STR wind factor for the selected SANS 10160-1 edition."""
    if load_combination_standard == PRE_2019_COMBINATIONS:
        return 1.3
    if load_combination_standard == SANS_2019_COMBINATIONS:
        return 1.6
    raise ValueError(
        f"Unknown load-combination standard {load_combination_standard!r}. "
        f"Choose one of {LOAD_COMBINATION_STANDARDS}."
    )


def _roof_accompanying_factor(roof_accessibility):
    # SANS 10160-1 Table 2: category H = 0; category J = 0.3.
    return 0.0 if roof_accessibility == "Inaccessible" else 0.3


def _wind_combinations(wind_cases, roof_accessibility, load_combination_standard):
    gamma_w = _wind_factor(load_combination_standard)
    live_factor = 1.6 * _roof_accompanying_factor(roof_accessibility)
    combinations = []
    for case, action in wind_cases:
        if action == "up":
            combinations.append({
                "name": f"0.9 DL + {gamma_w:g} {case}",
                "factors": {"D": 0.9, "D_MIN": 0.9, case: gamma_w},
            })
        elif action == "down":
            live_text = f" + {live_factor:g} LL" if live_factor else ""
            factors = {"D": 1.2, "D_MAX": 1.2, case: gamma_w}
            if live_factor:
                factors["L"] = live_factor
            combinations.append({
                "name": f"1.2 DL{live_text} + {gamma_w:g} {case}",
                "factors": factors,
            })
        else:  # Direction can vary over the frame: envelope both dead-load signs.
            combinations.extend(_wind_combinations(
                ((case, "up"), (case, "down")),
                roof_accessibility,
                load_combination_standard,
            ))
    return combinations


def add_load_cases(
    roof_accessibility="Accessible",
    building_type="Normal",
    load_combination_standard=SANS_2019_COMBINATIONS,
    building_roof="Duo Pitched",
    wind_design_mode="Prelim",
):
    """Return fixed load cases and edition-dependent SLS/ULS combinations."""
    final_wind = normalize_design_mode(wind_design_mode) == "Final design"
    positive = "CPI_MAX" if final_wind else "0.2"
    negative = "CPI_MIN" if final_wind else "0.3"
    w0_positive = {suffix: f"W0_{positive}{suffix}" for suffix in ("U", "D", "M1", "M2")}
    w0_negative = {suffix: f"W0_{negative}{suffix}" for suffix in ("U", "D", "M1", "M2")}
    w90_positive = f"W90_{positive}"
    w90_negative = f"W90_{negative}"
    load_cases = [
        {"name": "D_MIN", "type": "dead"},
        {"name": "D_MAX", "type": "dead"},
        {"name": "L", "type": "live"},
        {"name": w0_positive["U"], "type": "wind"},
        {"name": w0_positive["D"], "type": "wind"},
        {"name": w0_negative["U"], "type": "wind"},
        {"name": w0_negative["D"], "type": "wind"},
        {"name": w90_positive, "type": "wind"},
        {"name": w90_negative, "type": "wind"},
    ]
    include_mixed = building_type == "Normal" and building_roof == "Duo Pitched"
    if include_mixed:
        load_cases.extend(
            {"name": name, "type": "wind"}
            for name in (w0_positive["M1"], w0_negative["M1"],
                         w0_positive["M2"], w0_negative["M2"])
        )

    psi_live = _roof_accompanying_factor(roof_accessibility)
    serviceability_load_combinations = [
        {"name": "1.1 DL", "factors": {"D": 1.1, "D_MAX": 1.1}},
        {"name": "1.1 DL + 1.0 LL", "factors": {"D": 1.1, "D_MAX": 1.1, "L": 1.0}},
    ]
    wind_actions = [
        (w0_positive["U"], "up"), (w0_positive["D"], "down"),
        (w0_negative["U"], "up"), (w0_negative["D"], "down"),
        (w90_positive, "variable"), (w90_negative, "variable"),
    ]
    if include_mixed:
        wind_actions.extend((case, "variable") for case in (
            w0_positive["M1"], w0_negative["M1"],
            w0_positive["M2"], w0_negative["M2"]
        ))
    for case, action in wind_actions:
        if action in ("up", "variable"):
            serviceability_load_combinations.append({
                "name": f"1.0 DL + 0.6 {case}",
                "factors": {"D": 1.0, "D_MIN": 1.0, case: 0.6},
            })
        if action in ("down", "variable"):
            live_text = f" + {psi_live:g} LL" if psi_live else ""
            factors = {"D": 1.1, "D_MAX": 1.1, case: 0.6}
            if psi_live:
                factors["L"] = psi_live
            serviceability_load_combinations.append({
                "name": f"1.1 DL{live_text} + 0.6 {case}",
                "factors": factors,
            })

    load_combinations = [
        {"name": "1.35 DL", "factors": {"D": 1.35, "D_MAX": 1.35}},
        {"name": "1.2 DL + 1.6 LL", "factors": {"D": 1.2, "D_MAX": 1.2, "L": 1.6}},
    ]
    load_combinations.extend(_wind_combinations(
        wind_actions,
        roof_accessibility,
        load_combination_standard,
    ))
    return load_cases, serviceability_load_combinations, load_combinations


def add_SLS(roof_accessibility="Accessible"):
    return add_load_cases(roof_accessibility)[1]


def add_ULS(
    roof_accessibility="Accessible",
    load_combination_standard=SANS_2019_COMBINATIONS,
):
    return add_load_cases(
        roof_accessibility,
        load_combination_standard=load_combination_standard,
    )[2]

def safe_load_json(path: str | Path) -> dict:
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # New file or corrupt content → start fresh
        return {}

def update_json_file(json_filename, b_data, wind_data):
    json_filename = Path(json_filename)

    b_data = dict(b_data)

    # --- generate fresh data -------------------------------------------------
    new_nodes           = generate_nodes(b_data)
    new_members         = generate_members(new_nodes)
    new_supports        = generate_supports(new_nodes)
    rotational_springs  = generate_spring_supports(new_nodes)
    nodal_loads         = generate_nodal_loads(new_nodes)
    materials           = add_materials()
    roof_accessibility = b_data.get("roof_accessibility", "Accessible")
    load_combination_standard = b_data.get(
        "load_combination_standard", SANS_2019_COMBINATIONS
    )
    LC, SLS, ULS = add_load_cases(
        roof_accessibility,
        b_data.get("building_type", "Normal"),
        load_combination_standard,
        b_data.get("building_roof", "Duo Pitched"),
        b_data.get("wind_design_mode", "Prelim"),
    )
    steel_props         = steel_prop(b_data['steel_grade'])

    # build wind_input without mutating caller's dict
    wind_input = wind_data | {k: (v/1000 if k in {
        "eaves_height","apex_height","gable_width",
        "rafter_spacing","building_length"} else v)
        for k, v in b_data.items()}
    wind_input["internal_pressure"] = resolve_internal_pressure(wind_input)

    # --- load (or initialise) the JSON --------------------------------------
    data = safe_load_json(json_filename)

    # --- overwrite the sections we care about --------------------------------
    data.update({
        "frame_data"        : [b_data],
        "nodes"             : new_nodes,
        "members"           : new_members,
        "supports"          : new_supports,
        "nodal_loads"       : nodal_loads,
        "rotational_springs": rotational_springs,
        "wind_data"         : [wind_input],
        "steel_grade"       : [steel_props],
        "materials"         : materials,
        "load_cases"        : LC,
        "serviceability_load_combinations" : SLS,
        "load_combinations" : ULS,
    })

    # --- write it back, *letting json handle the formatting* -----------------
    with open(json_filename, "w") as f:
        json.dump(data, f, indent=2)      # `indent` pretty-prints safely

    print(f"Portal frame data saved to {json_filename}")
    wind_out()

def add_wind_member_loads(json_filename):
    """Generate wind loads and append them to the member loads list."""
    from generate_wind_loading import wind_loading

    with open(json_filename, 'r') as file:
        data = json.load(file)

    loads = wind_loading(data)
    data.setdefault("member_loads", [])
    data["member_loads"] = loads
    with open(json_filename, 'w') as json_file:
        json.dump(data, json_file, indent=2)

def add_live_loads(json_filename):
    """Generate live loads and append them to the member loads list."""
    with open(json_filename, 'r') as file:
        data = json.load(file)

    live_load = round(data["frame_data"][0]["rafter_spacing"] / 1000 * -0.25/1000, 5)

    for member in data["members"]:
        if member["type"] == "rafter":
            lod = {
                'member': member["name"],
                'direction': 'FY',
                'w1': live_load,
                'w2': live_load,
                'case': 'L'
            }
            data["member_loads"].append(lod)

    with open(json_filename, 'w') as json_file:
        json.dump(data, json_file, indent=2)

def add_dead_loads(json_filename):
    """Generate live loads and append them to the member loads list."""
    with open(json_filename, 'r') as file:
        data = json.load(file)

    dead_load_max = round(data["frame_data"][0]["rafter_spacing"] / 1000 * -0.35/1000, 5)
    dead_load_min = round(data["frame_data"][0]["rafter_spacing"] / 1000 * -0.25/1000, 5)

    for member in data["members"]:
        if member["type"] == "rafter":
            d_max = {
                'member': member["name"],
                'direction': 'FY',
                'w1': dead_load_max,
                'w2': dead_load_max,
                'case': 'D_MAX'
            }
            data["member_loads"].append(d_max)

            d_min = {
                'member': member["name"],
                'direction': 'FY',
                'w1': dead_load_min,
                'w2': dead_load_min,
                'case': 'D_MIN'
            }
            data["member_loads"].append(d_min)

    with open(json_filename, 'w') as json_file:
        json.dump(data, json_file, indent=2)

def main() -> None:
    """Generate the default portal-frame input JSON and associated loads."""

    # Static inputs for eaves, apex, and rafter span (converted to mm)
    building_roof = "Duo Pitched"  # "Mono Pitched" or "Duo Pitched"
    building_type = "Normal"       # "Normal" or "Canopy"
    wind_design_mode = "Prelim"    # "Prelim" uses +0.2/-0.3; "Final design" uses wall openings.
    eaves_height = 6 * 1000        # Convert to mm
    apex_height = 6.8 * 1000         # Convert to mm
    gable_width = 16 * 1000        # Convert to mm
    rafter_spacing = 6 * 1000      # Convert to mm
    building_length = 72 * 1000    # Convert to mm
    col_bracing_spacing = 1        # number of braced points per column
    column_bracing_type = "X"     # "X" uses angles; "K" or "A" uses CHS
    rafter_bracing_spacing = 3     # number of braced points per rafter
    # One gable end: 1, 3, 5, ... columns. The apex column is mandatory and
    # each increment adds a symmetric pair at the next roof brace nodes.
    gable_column_count = 3
    # Number of equal laterally-unbraced intervals along each gable column.
    gable_column_brace_intervals = 2
    steel_grade = "Steel_S355"     # "Steel_S355" or "Steel_S275"
    roof_accessibility = "Inaccessible"  # "Accessible" or "Inaccessible"
    load_combination_standard = SANS_2019_COMBINATIONS  # or PRE_2019_COMBINATIONS
    blocking_factor = 0.0          # Canopy only: 0.0 (open) to 1.0 (fully blocked)
    roof_span = gable_width / 2 if building_roof == "Duo Pitched" else gable_width

    building_data = {
        "building_type": building_type,
        "wind_design_mode": wind_design_mode,
        # Required in Final design mode. Areas are the total openings on each
        # physical wall face in m2; the two side walls run along the ridge.
        "opening_areas_m2": {
            "side_1": 0.0,
            "side_2": 0.0,
            "gable_1": 0.0,
            "gable_2": 0.0,
        },
        "building_roof": building_roof,
        "eaves_height": eaves_height,
        "apex_height": apex_height,
        "gable_width": gable_width,
        "rafter_spacing": rafter_spacing,
        "building_length": building_length,
        "col_bracing_spacing": col_bracing_spacing,
        "column_bracing_type": column_bracing_type,
        "rafter_bracing_spacing": rafter_bracing_spacing,
        "gable_column_count": gable_column_count,
        "gable_column_brace_intervals": gable_column_brace_intervals,
        "roof_accessibility": roof_accessibility,
        "load_combination_standard": load_combination_standard,
        "blocking_factor": blocking_factor,
        "roof_pitch": math.degrees(math.atan((apex_height - eaves_height) / roof_span)),
        "steel_grade": steel_grade,
    }

    wind_data = {
        "wind": "3s gust",
        "fundamental_basic_wind_speed": 36,
        "return_period": 50,
        "terrain_category": "B",
        "topographic_factor": 1.0,
        "altitude": 1140,
    }

    # Filename of the existing JSON file
    json_filename = "input_data.json"

    # Generate the input file and associated loads
    update_json_file(json_filename, building_data, wind_data)
    add_wind_member_loads(json_filename)
    add_live_loads(json_filename)
    add_dead_loads(json_filename)

if __name__ == "__main__":
    main()

