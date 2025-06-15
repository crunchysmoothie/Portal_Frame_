import json

def wind_loads():
    data = json.load(open('input_data.json'))
    wd = data['wind_data']

    wl_0D = data['wind_zones_0U']
    wl_0U = data['wind_zones_0U']
    wl_90 = data['wind_zones_90']

    members = data['members']

    if wd['building_roof'] == 'Duo Pitched':
        nodes = data['nodes']
        apex_node = nodes[len(nodes) // 2]
        eaves_node = []
        for i in nodes:
            if i['x'] == 0 and i['y'] == data['frame_data'][0]['eaves_height']:
                eaves_node.append(i)
            if i['x'] == data['frame_data'][0]['gable_width'] and i['y'] == data['frame_data'][0]['eaves_height']:
                eaves_node.append(i)

    return

wind_loads()
