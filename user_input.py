import json
import math

# Function to generate nodes based on the portal frame structure with static values
def generate_nodes(b_data):
    eaves_height = b_data['eaves_height']
    apex_height = b_data['apex_height']
    rafter_span = b_data['rafter_span']

    nodes = []
    num_vertical = 5

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
        num_diagonal = 8
        for i in range(1, num_diagonal):
            x = round(i * (rafter_span / num_diagonal), 2)
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
                "x": rafter_span,
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
            x = round(i * (rafter_span / num_diagonal), 2)
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
                "x": rafter_span,
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
        member = {
            "name": f"M{i}",
            "i_node": nodes[i - 1]["name"],
            "j_node": nodes[i]["name"],
            "material": "Steel_S355",
            "type": "rafter" if i in range(3, num_nodes - 2) else "column"
        }
        members.append(member)

    return members

def generate_nodal_loads(nodes):
    apex_node = nodes[len(nodes) // 2]
    eaves_node = nodes[2]
    nodal_loads = [{"node": apex_node["name"], "direction": "FY", "magnitude": -50, "case": "L"},
                   {"node": apex_node["name"], "direction": "FY", "magnitude": -50, "case": "D"},]

    return nodal_loads

def generate_member_loads(members):
    member_loads = []

    for member in members[0: len(members) // 2]:
        if member["type"] == "column":
            member_loads.append({"member": member["name"], "direction":"Fy","w1":-0.003,"w2":-0.003,"case":"D"})

    return member_loads

def generate_spring_supports(nodes):
    rotational_springs = [{"node": nodes[0]["name"], "direction": "RZ", "stiffness": 5E6},
                          {"node": nodes[-1]["name"], "direction": "RZ", "stiffness": 5E6}]
    return rotational_springs


def update_json_file(json_filename, b_data, wind_data):
    # Generate new node and member data based on input dimensions
    new_nodes = generate_nodes(b_data)
    new_members = generate_members(new_nodes)
    new_supports = generate_supports(new_nodes)
    new_loads = generate_nodal_loads(new_nodes)
    new_member_loads = generate_member_loads(new_members)
    rotational_springs = generate_spring_supports(new_nodes)
    wind_input = wind_data
    for i in b_data:
        if i in ["eaves_height", "apex_height", "rafter_span", "rafter_spacing", "building_length"]:
            wind_input[i] = b_data[i]/1000
        else:
            wind_input[i] = b_data[i]

    # Load existing JSON data
    with open(json_filename, 'r') as file:
        data = json.load(file)

    # Update only the "nodes" and "members" sections
    data["frame_data"] = [b_data]
    data["nodes"] = new_nodes
    data["members"] = new_members
    data["supports"] = new_supports
    data["nodal_loads"] = new_loads
    data["member_loads"] = new_member_loads
    data["rotational_springs"] = rotational_springs
    data["wind_data"] = wind_input

    # Convert data to a compact JSON string
    json_str = json.dumps(data, separators=(',', ':'))

    # Insert line breaks between JSON objects
    formatted_json_str = json_str.replace('},{', '},\n  {')
    formatted_json_str = formatted_json_str.replace('[{', '[\n  {')
    formatted_json_str = formatted_json_str.replace('}]', '}\n]')
    formatted_json_str = formatted_json_str.replace('],', '],\n')
    formatted_json_str = formatted_json_str.replace(']}', ']\n}')

    # Save the formatted JSON string to a file
    with open(json_filename, 'w') as json_file:
        json_file.write(formatted_json_str)

    print(f"Portal frame data saved to {json_filename}")

# Static inputs for eaves, apex, and rafter span (converted to mm)
building_roof = "Duo Pitched" # "Mono Pitched" or "Duo Pitched"
building_type = "Normal"    # "Normal" or "Canopy"
eaves_height = 5 * 1000     # Convert to mm
apex_height = 7 * 1000      # Convert to mm
rafter_span = 8 * 1000      # Convert to mm
rafter_spacing = 5 * 1000   # Convert to mm
building_length = 50 * 1000 # Convert to mm
col_bracing_spacing = 1     # number of braced points per column (1: Lx=Ly = L)
rafter_bracing_spacing = 4  # number of braced points per rafter (1: Lx=Ly = L)

building_data = {
    "building_type": building_type,
    "building_roof": building_roof,
    "eaves_height": eaves_height,
    "apex_height": apex_height,
    "rafter_span": rafter_span,
    "rafter_spacing": rafter_spacing,
    "building_length": building_length,
    "col_bracing_spacing": col_bracing_spacing,
    "rafter_bracing_spacing": rafter_bracing_spacing,
}
wind_data = {
    "wind": "3s gust",
    "fundamental_basic_wind_speed": 36,
    "return_period": 50,
    "terrain_category": "B",
    "topographic_factor": 1.0,
    "altitude": 1450
}

# Filename of the existing JSON file
json_filename = 'input_data.json'

# Call the function to update the nodes and members in the JSON file
update_json_file(json_filename,
                 building_data,
                 wind_data)