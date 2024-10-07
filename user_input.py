import json

# Function to generate nodes based on the portal frame structure with static values
def generate_nodes(eaves_height, apex_height, rafter_span):
    nodes = []

    # Generate 4 vertical nodes on the left side
    num_vertical = 4
    for i in range(num_vertical):
        node = {
            "name": f"N{i + 1}",
            "x": 0,
            "y": round(i * (eaves_height / (num_vertical - 1)), 2),
            "z": 0
        }
        nodes.append(node)

    # Generate 10 diagonal nodes for the rafter section
    num_diagonal = 10
    for i in range(num_diagonal):
        x = round((i + 1) * (rafter_span / (num_diagonal + 1)), 2)
        y = round(
            eaves_height + ((apex_height - eaves_height) * (1 - abs(i + 1 - (num_diagonal / 2)) / (num_diagonal / 2))),
            2)
        node = {
            "name": f"N{num_vertical + i + 1}",
            "x": x,
            "y": y,
            "z": 0
        }
        nodes.append(node)

    # Generate 4 vertical nodes on the right side
    for i in range(num_vertical):
        node = {
            "name": f"N{num_vertical + num_diagonal + i + 1}",
            "x": rafter_span,
            "y": round(eaves_height - i * (eaves_height / (num_vertical - 1)), 2),
            "z": 0
        }
        nodes.append(node)

    return nodes

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
            "type": "rafter" if i in range(2, num_nodes - 1) else "column"
        }
        members.append(member)

    return members

# Function to update nodes and members in the JSON data
def update_nodes_and_members(json_filename, eaves_height, apex_height, rafter_span):
    # Generate new node and member data based on input dimensions
    new_nodes = generate_nodes(eaves_height, apex_height, rafter_span)
    new_members = generate_members(new_nodes)

    # Load existing JSON data
    with open(json_filename, 'r') as file:
        data = json.load(file)

    # Update only the "nodes" and "members" sections
    data["nodes"] = new_nodes
    data["members"] = new_members

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

# Main function
if __name__ == "__main__":
    # Static inputs for eaves, apex, and rafter span (converted to mm)
    eaves_height = 5 * 1000  # Convert to mm
    apex_height = 7 * 1000  # Convert to mm
    rafter_span = 8 * 1000  # Convert to mm

    # Filename of the existing JSON file
    json_filename = 'generated_input.json'

    # Call the function to update the nodes and members in the JSON file
    update_nodes_and_members(json_filename, eaves_height, apex_height, rafter_span)
