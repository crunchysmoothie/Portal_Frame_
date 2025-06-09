import json


def import_data(file):
    """Load project data from a JSON file."""
    with open(file) as f:
        data = json.load(f)

    # Convert the wind data list to a dictionary keyed by type
    wind_data = {
        entry['type']: {
            'basic_wind_speed': entry['basic_wind_speed'],
            'return_period': entry['return_period'],
            'terrain_category': entry['terrain_category'],
            'altitude': entry['altitude'],
            'topographic_category': entry['topographic_category'],
        }
        for entry in data.get('wind_data', [])
    }

    nodes = {
        node['name']: {'x': node['x'], 'y': node['y'], 'z': node['z']}
        for node in data.get('nodes', [])
    }

    return {
        'wind_data': wind_data,
        'nodes': nodes,
    }


def wind_data(filename="input_data.json"):
    """Calculate simple wind pressures for all wind load cases."""
    data = import_data(filename)
    # Assume a single wind entry is provided
    site = next(iter(data['wind_data'].values()))

    # Basic dynamic pressure approximation (kPa)
    v_basic = site['basic_wind_speed']
    q_basic = 0.613 * v_basic ** 2

    # Upward wind cases
    w0_02_up = 0.2 * q_basic
    w0_03_up = 0.3 * q_basic

    # Downward wind cases (sign reversed)
    w0_02_down = -0.2 * q_basic
    w0_03_down = -0.3 * q_basic

    # 90 degree cases
    w90_02 = 0.2 * q_basic
    w90_03 = 0.3 * q_basic

    return {
        'W0_0.2U': w0_02_up,
        'W0_0.3U': w0_03_up,
        'W0_0.2D': w0_02_down,
        'W0_0.3D': w0_03_down,
        'W90_0.2': w90_02,
        'W90_0.3': w90_03,
    }
