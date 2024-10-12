import json


# Function to generate nodes based on the portal frame structure with static values
def generate_nodes(eaves_height, apex_height, rafter_span):
    nodes = []

    # Generate 3 vertical nodes on the left side
    num_vertical = 3
    for i in range(num_vertical):
        node = {
            "name": f"N{i + 1}",
            "x": 0,
            "y": round(i * (eaves_height / (num_vertical - 1)), 2),
            "z": 0
        }
        nodes.append(node)

    # Generate 4 diagonal nodes for the rafter section
    num_diagonal = 4
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

    return nodes

def generate_supports(nodes):

    supports = [
        {"node": nodes[0]["name"], "DX": True, "DY": True, "DZ": True, "RX": True, "RY": True, "RZ": True},
        {"node": nodes[-1]["name"], "DX": True, "DY": True, "DZ": True, "RX": True, "RY": True, "RZ": True}
    ]

    return supports


# Function to generate members based on the nodes
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
    nodal_loads = [{"node": apex_node["name"], "direction": "FY", "magnitude": -50, "case": "L"}]

    return nodal_loads

def generate_member_loads(members):
    member_loads = []

    for member in members[0: len(members) // 2]:
        if member["type"] == "column":
            member_loads.append({"member": member["name"], "direction":"Fy","w1":-0.006,"w2":-0.006,"case":"L"})

    return member_loads



# Function to update nodes and members in the JSON data
def update_nodes_and_members(json_filename, eaves_height, apex_height, rafter_span):
    # Generate new node and member data based on input dimensions
    updated_frame = [{"type": "portal", "eaves_height": eaves_height, "apex_height": apex_height, "rafter_span": rafter_span, "bay_spacing": 6000}]
    new_nodes = generate_nodes(eaves_height, apex_height, rafter_span)
    new_members = generate_members(new_nodes)
    new_supports = generate_supports(new_nodes)
    new_loads = generate_nodal_loads(new_nodes)
    new_member_loads = generate_member_loads(new_members)

    # Load existing JSON data
    with open(json_filename, 'r') as file:
        data = json.load(file)



    # Update only the "nodes" and "members" sections
    data["frame_data"] = updated_frame
    data["nodes"] = new_nodes
    data["members"] = new_members
    data["supports"] = new_supports
    data["nodal_loads"] = new_loads
    data["member_loads"] = new_member_loads


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
eaves_height = 5 * 1000  # Convert to mm
apex_height = 7 * 1000  # Convert to mm
rafter_span = 8 * 1000  # Convert to mm
rafter_spacing = 5 * 1000 # Convert to mm

# Filename of the existing JSON file
json_filename = 'input_data.json'

# Call the function to update the nodes and members in the JSON file
update_nodes_and_members(json_filename, eaves_height, apex_height, rafter_span)
