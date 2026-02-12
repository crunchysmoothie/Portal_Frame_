import json
from pathlib import Path
import math
from wind_loads import wind_out

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
    rotational_springs = [{"node": nodes[0]["name"], "direction": "RZ", "stiffness": 5E6},
                          {"node": nodes[-1]["name"], "direction": "RZ", "stiffness": 5E6}]
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

def apply_unaccessible_roof_uls_rule(load_combinations, roof_accessibility):
    """Set all ULS live-load factors to 0.0 when the roof is unaccessible."""
    if roof_accessibility != "Unaccessible":
        return load_combinations

    adjusted = []
    for combo in load_combinations:
        new_combo = dict(combo)
        factors = dict(combo.get("factors", {}))
        if "L" in factors:
            factors["L"] = 0.0
        new_combo["factors"] = factors
        adjusted.append(new_combo)
    return adjusted

def apply_unaccessible_roof_sls_rule(serviceability_load_combinations, roof_accessibility):
    """Set all SLS live-load factors to 0.0 when the roof is unaccessible."""
    if roof_accessibility != "Unaccessible":
        return serviceability_load_combinations

    adjusted = []
    for combo in serviceability_load_combinations:
        new_combo = dict(combo)
        factors = dict(combo.get("factors", {}))
        if "L" in factors:
            factors["L"] = 0.0
        new_combo["factors"] = factors
        adjusted.append(new_combo)
    return adjusted


def add_load_cases(roof_accessibility="Accessible"):
    load_cases = [
        {"name": "D_MIN", "type": "dead"},
        {"name": "D_MAX", "type": "dead"},
        {"name": "L", "type": "live"},
        {"name": "W0_0.2U", "type": "wind"},
        {"name": "W0_0.2D", "type": "wind"},
        {"name": "W0_0.3U", "type": "wind"},
        {"name": "W0_0.3D", "type": "wind"},
        {"name": "W90_0.2", "type": "wind"},
        {"name": "W90_0.3", "type": "wind"}
    ]

    serviceability_load_combinations = [
        {"name": "1.1 DL", "factors": {"D": 1.1, "D_MAX": 1.1}},
        {"name": "1.1 DL + 1.0 LL", "factors": {"D": 1.1, "D_MAX": 1.1, "L": 1.0}},
        {"name": "0.9 DL + 0.6 W0_0.2U", "factors": {"D": 0.9, "D_MIN": 0.9, "W0_0.2U": 0.6}},
        {"name": "1.1 DL + 0.3 LL + 0.6 W0_0.2D", "factors": {"D": 1.1, "D_MAX": 1.1, "L": 0.3, "W0_0.2D": 0.6}},
        {"name": "0.9 DL + 0.6 W0_0.3U", "factors": {"D": 0.9, "D_MIN": 0.9, "W0_0.3U": 0.6}},
        {"name": "1.1 DL + 0.3 LL + 0.6 W0_0.3D", "factors": {"D": 1.1, "D_MAX": 1.1, "L": 0.3, "W0_0.3D": 0.6}},
        {"name": "0.9 DL + 0.3 LL + 0.6 W90_0.2", "factors": {"D": 0.9, "D_MIN": 0.9, "L": 0.3, "W90_0.2": 0.6}},
        {"name": "0.9 DL + 0.3 LL + 0.6 W90_0.3", "factors": {"D": 0.9, "D_MIN": 0.9, "L": 0.3, "W90_0.3": 0.6}}
    ]

    load_combinations = [
        {"name": "1.5 DL", "factors": {"D": 1.5}},
        {"name": "1.2 DL + 1.6 LL", "factors": {"D": 1.2, "L": 1.6}},
        {"name": "0.9 DL + 1.3 W0_0.2U", "factors": {"D": 0.9, "W0_0.2U": 1.3}},
        {"name": "1.1 DL + 0.5 LL + 1.3 W0_0.2D", "factors": {"D": 1.1, "L": 0.5, "W0_0.2D": 1.3}},
        {"name": "0.9 DL + 1.3 W0_0.3U", "factors": {"D": 0.9, "W0_0.3U": 1.3}},
        {"name": "1.1 DL + 0.5 LL + 1.3 W0_0.3D", "factors": {"D": 1.1, "L": 0.5, "W0_0.3D": 1.3}},
        {"name": "0.9 DL + 1.3 W90_0.2", "factors": {"D": 1.1, "W90_0.2": 1.3}},
        {"name": "0.9 DL + 1.3 W90_0.3", "factors": {"D": 1.1, "W90_0.3": 1.3}}
    ]

    serviceability_load_combinations = apply_unaccessible_roof_sls_rule(
        serviceability_load_combinations, roof_accessibility
    )
    load_combinations = apply_unaccessible_roof_uls_rule(load_combinations, roof_accessibility)

    return load_cases, serviceability_load_combinations, load_combinations

def add_SLS():
    serviceability_load_combinations = [
        {"name": "1.1 DL", "factors": {"D": 1.1, "D_MAX": 1.1}},
        {"name": "1.1 DL + 1.0 LL", "factors": {"D": 1.1, "D_MAX": 1.1, "L": 1.0}},
        {"name": "0.9 DL + 0.6 W0_0.2U", "factors": {"D": 0.9, "D_MIN": 0.9, "W0_0.2U": 0.6}},
        {"name": "1.1 DL + 0.3 LL + 0.6 W0_0.2D", "factors": {"D": 1.1, "D_MAX": 1.1, "L": 0.3, "W0_0.2D": 0.6}},
        {"name": "0.9 DL + 0.6 W0_0.3U", "factors": {"D": 0.9, "D_MIN": 0.9, "W0_0.3U": 0.6}},
        {"name": "1.1 DL + 0.3 LL + 0.6 W0_0.3D", "factors": {"D": 1.1, "D_MAX": 1.1, "L": 0.3, "W0_0.3D": 0.6}},
        {"name": "0.9 DL + 0.3 LL + 0.6 W90_0.2", "factors": {"D": 0.9, "D_MIN": 0.9, "L": 0.3, "W90_0.2": 0.6}},
        {"name": "0.9 DL + 0.3 LL + 0.6 W90_0.3", "factors": {"D": 0.9, "D_MIN": 0.9, "L": 0.3, "W90_0.3": 0.6}}
    ]
    return apply_unaccessible_roof_sls_rule(serviceability_load_combinations, "Accessible")

def add_ULS(roof_accessibility="Accessible"):
    load_combinations = [
        {"name": "1.5 DL", "factors": {"D": 1.5}},
        {"name": "1.2 DL + 1.6 LL", "factors": {"D": 1.2, "L": 1.6}},
        {"name": "0.9 DL + 1.3 W0_0.2U", "factors": {"D": 0.9, "W0_0.2U": 1.3}},
        {"name": "1.1 DL + 0.5 LL + 1.3 W0_0.2D", "factors": {"D": 1.1, "L": 0.5, "W0_0.2D": 1.3}},
        {"name": "0.9 DL + 1.3 W0_0.3U", "factors": {"D": 0.9, "W0_0.3U": 1.3}},
        {"name": "1.1 DL + 0.5 LL + 1.3 W0_0.3D", "factors": {"D": 1.1, "L": 0.5, "W0_0.3D": 1.3}},
        {"name": "0.9 DL + 1.3 W90_0.2", "factors": {"D": 1.1, "W90_0.2": 1.3}},
        {"name": "0.9 DL + 1.3 W90_0.3", "factors": {"D": 1.1, "W90_0.3": 1.3}}
    ]
    return apply_unaccessible_roof_uls_rule(load_combinations, roof_accessibility)

def safe_load_json(path: str | Path) -> dict:
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # New file or corrupt content → start fresh
        return {}

def update_json_file(json_filename, b_data, wind_data):
    json_filename = Path(json_filename)

    # --- generate fresh data -------------------------------------------------
    new_nodes           = generate_nodes(b_data)
    new_members         = generate_members(new_nodes)
    new_supports        = generate_supports(new_nodes)
    rotational_springs  = generate_spring_supports(new_nodes)
    nodal_loads         = generate_nodal_loads(new_nodes)
    materials           = add_materials()
    roof_accessibility = b_data.get("roof_accessibility", "Accessible")
    LC, SLS, ULS        = add_load_cases(roof_accessibility)
    steel_props         = steel_prop(b_data['steel_grade'])

    # build wind_input without mutating caller's dict
    wind_input = wind_data | {k: (v/1000 if k in {
        "eaves_height","apex_height","gable_width",
        "rafter_spacing","building_length"} else v)
        for k, v in b_data.items()}

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
    eaves_height = 4 * 1000        # Convert to mm
    apex_height = 6 * 1000         # Convert to mm
    gable_width = 12 * 1000        # Convert to mm
    rafter_spacing = 5 * 1000      # Convert to mm
    building_length = 20 * 1000    # Convert to mm
    col_bracing_spacing = 1        # number of braced points per column
    rafter_bracing_spacing = 4     # number of braced points per rafter
    steel_grade = "Steel_S355"     # "Steel_S355" or "Steel_S275"
    roof_accessibility = "Unaccessible"  # "Accessible" or "Unaccessible"
    blocking_factor = 0.0          # Canopy only: 0.0 (open) to 1.0 (fully blocked)
    roof_span = gable_width / 2 if building_roof == "Duo Pitched" else gable_width

    building_data = {
        "building_type": building_type,
        "building_roof": building_roof,
        "eaves_height": eaves_height,
        "apex_height": apex_height,
        "gable_width": gable_width,
        "rafter_spacing": rafter_spacing,
        "building_length": building_length,
        "col_bracing_spacing": col_bracing_spacing,
        "rafter_bracing_spacing": rafter_bracing_spacing,
        "roof_accessibility": roof_accessibility,
        "blocking_factor": blocking_factor,
        "roof_pitch": math.degrees(math.atan((apex_height - eaves_height) / roof_span)),
        "steel_grade": steel_grade,
    }

    wind_data = {
        "wind": "3s gust",
        "fundamental_basic_wind_speed": 36,
        "return_period": 50,
        "terrain_category": "C",
        "topographic_factor": 1.0,
        "altitude": 1450,
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

