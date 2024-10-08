import json

def import_data(file):
    with open(file) as f:
        data = json.load(f)

        # Initialize dictionaries for the imported data
        wind_data = {wind_data['type']: {'basic_wind_speed': wind_data['basic_wind_speed'], 'return_period': wind_data['return_period'],
                                         'terrain_category': wind_data['terrain_category'], 'altitude': wind_data['altitude'],
                                         'topographic_category': wind_data['topographic_category']}
                     for wind_data in data.get('wind_data', [])}
        nodes = {node['name']: {'x': node['x'], 'y': node['y'], 'z': node['z']} for node in data.get('nodes', [])}


