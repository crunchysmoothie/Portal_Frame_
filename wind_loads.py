import json
import math
import numpy as np


def import_data(file):
    with open(file) as f:
        data = json.load(f)
        return data

def calculate_basic_wind_speed(fbs, return_period):
    if return_period == 0: return 0
    numerator = 1 - 0.2 * math.log(-math.log(1 - (1 / return_period)))
    denominator = 1 - 0.2 * math.log(-math.log(0.98))
    return (numerator / denominator) ** 0.5 * fbs

def calculate_terrain_roughness(apex_height, terrain_category):
    categories = {'A': (1, 0, 250, 0.07), 'B': (2, 0, 300, 0.095),
                  'C': (5, 3, 350, 0.12), 'D': (10, 5, 400, 0.15)}
    zc, z0, zg, alpha = categories.get(terrain_category, (1, 0, 250, 0.07))
    return 1.36 * ((max(apex_height, zc) - z0) / (zg - z0)) ** alpha

def calculate_air_density(altitude):
    return 1.2 if altitude == 0 else 0.94 + (2000 - altitude) * 0.06 / 500

def calculate_peak_wind_pressure(topography_factor, basic_speed, roughness, altitude):
    peak_speed = topography_factor * basic_speed * roughness
    air_density = calculate_air_density(altitude)
    return 0.5 * air_density * (peak_speed ** 2) / 1000

def interpolate_cpe(h_d, h_d_data, cpe_data):
    if h_d < h_d_data[0]:
        h_d = h_d_data[0]
    elif h_d > h_d_data[-1]:
        h_d = h_d_data[-1]
    return np.interp(h_d, h_d_data, cpe_data)

def interpolate_cpe_roof(roof_angle, angles, data):
    return np.array([np.interp(roof_angle, angles, data[:, col]) for col in range(data.shape[1])])

def calculate_pressure(peak_wind_pressure, cpe, cpi):
    return (peak_wind_pressure * cpe) - (peak_wind_pressure * cpi)

def wind_data():
    angles = np.array([5, 15, 30, 45])

    # Wind 0 Upward
    negative_pressure_data_w0 = np.array([
        [-1.7, -1.2, -0.6, -0.6, -0.6],
        [-0.9, -0.8, -0.3, -0.4, -1.0],
        [-0.5, -0.5, -0.2, -0.4, -0.5],
        [0, 0, 0, -0.2, -0.3]
    ])

    # Wind 0 Downward
    positive_pressure_data_w0 = np.array([
        [0, 0, 0, -0.6, 0.2],
        [0.2, 0.2, 0.2, 0, 0],
        [0.7, 0.7, 0.4, 0, 0],
        [0.7, 0.7, 0.6, 0, 0]
    ])

    # Wind 90 Upward
    negative_pressure_data_w90 = np.array([
        [-1.6, -1.3, -0.7, -0.6],
        [-1.3, -1.3, -0.6, -0.5],
        [-1.1, -1.4, -0.8, -0.5],
        [-1.1, -1.4, -0.9, -0.5]
    ])

    data = import_data("input_data.json")
    h_d_data = [0.25, 1.0]
    cpe_d = [0.70, 0.80]
    cpe_e = [-0.3, -0.50]

    results_up = []
    results_down = []

    for wind in data['wind_data']:
        bs = calculate_basic_wind_speed(wind['fundamental_basic_wind_speed'], wind['return_period'])
        roughness = calculate_terrain_roughness(wind['apex_height'], wind['terrain_category'])
        peak_pressure = calculate_peak_wind_pressure(wind['topographic_factor'], bs, roughness, wind['altitude'])

        h_d_zone_d = wind['eaves_height'] / wind['gable_width']
        h_d_zone_e = wind['apex_height'] / wind['gable_width']

        cpe_d_coeff = min([max([0.85+((1-0.85)/(5-1)*(h_d_zone_d-1)), 0.85]), 1])
        cpe_e_coeff = min([max([0.85+((1-0.85)/(5-1)*(h_d_zone_e-1)), 0.85]), 1])

        cpe_value_d = interpolate_cpe(h_d_zone_d, h_d_data, cpe_d) * cpe_d_coeff
        cpe_value_e = interpolate_cpe(h_d_zone_e, h_d_data, cpe_e) * cpe_e_coeff

        cpe_negative = np.array([
            np.interp(wind['roof_pitch'], angles, negative_pressure_data_w0[:, i])
            for i in range(negative_pressure_data_w0.shape[1])
        ])

        cpe_positive = np.array([
            np.interp(wind['roof_pitch'], angles, positive_pressure_data_w0[:, i])
            for i in range(positive_pressure_data_w0.shape[1])
        ])

        zones_up = {
            "A": -1.2,
            "B": -0.8,
            "C": -0.5,
            "D": cpe_value_d,
            "E": cpe_value_e,
            "F": cpe_negative[0],
            "G": cpe_negative[1],
            "H": cpe_negative[2],
            "I": cpe_negative[3],
            "J": cpe_negative[4]
        }

        zones_down = {
            "A": -1.2,
            "B": -0.8,
            "C": -0.5,
            "D": cpe_value_d,
            "E": cpe_value_e,
            "F": cpe_positive[0],
            "G": cpe_positive[1],
            "H": cpe_positive[2],
            "I": cpe_positive[3],
            "J": cpe_positive[4]
        }

        for zone, cpe in zones_up.items():
            results_up.append({
                "Zone": zone,
                "cpe": round(cpe, 4),
                "cpi=0.2": round(calculate_pressure(peak_pressure, cpe, 0.2), 4),
                "cpi=-0.3": round(calculate_pressure(peak_pressure, cpe, -0.3), 4)
            })

        for zone, cpe in zones_down.items():
            results_down.append({
                "Zone": zone,
                "cpe": round(cpe, 4),
                "cpi=0.2": round(calculate_pressure(peak_pressure, cpe, 0.2), 4),
                "cpi=-0.3": round(calculate_pressure(peak_pressure, cpe, -0.3), 4)
            })

    print("Wind Upward Pressures")
    print(f"{'Zone':<6}{'cpe':<10}{'Press. cpi=0.2':<15}{'Press. cpi=-0.3'}")
    print("-" * 56)
    for result in results_up:

        cpe_display = f"+{result['cpe']:.2f}" if result['cpe'] > 0 else f"{result['cpe']:.2f}"
        pressure_cpi_0_2 = f"+{result['cpi=0.2']:.2f}" if result['cpi=0.2'] > 0 else f"{result['cpi=0.2']:.2f}"
        pressure_cpi_neg_0_3 = f"+{result['cpi=-0.3']:.2f}" if result['cpi=-0.3'] > 0 else f"{result['cpi=-0.3']:.2f}"

        print(f"{result['Zone']:<6}{cpe_display:<10}{pressure_cpi_0_2 + ' kpa' :<15} {pressure_cpi_neg_0_3} kPa")

    print("\nWind Downward Pressures")
    print(f"{'Zone':<6}{'cpe':<10}{'Press. cpi=0.2':<15}{'Press. cpi=-0.3'}")
    print("-" * 56)
    for result in results_down:
        cpe_display = f"+{result['cpe']:.2f}" if result['cpe'] > 0 else f"{result['cpe']:.2f}"
        pressure_cpi_0_2 = (
            f"+{result['cpi=0.2']:.2f}" if result['cpi=0.2'] > 0 else f"{result['cpi=0.2']:.2f}"
        )
        pressure_cpi_neg_0_3 = (
            f"+{result['cpi=-0.3']:.2f}" if result['cpi=-0.3'] > 0 else f"{result['cpi=-0.3']:.2f}"
        )

        print(f"{result['Zone']:<6}{cpe_display:<10}{pressure_cpi_0_2 + ' kpa':<15} {pressure_cpi_neg_0_3} kPa")

    data["wind_zones_0U"] = results_up
    data["wind_zones_0D"] = results_down

    json_str = json.dumps(data, separators=(',', ':'))

    # Insert line breaks between JSON objects
    formatted_json_str = json_str.replace('},{', '},\n  {')
    formatted_json_str = formatted_json_str.replace('[{', '[\n  {')
    formatted_json_str = formatted_json_str.replace('}]', '}\n]')
    formatted_json_str = formatted_json_str.replace('],', '],\n')
    formatted_json_str = formatted_json_str.replace(']}', ']\n}')

    # Save the formatted JSON string to a file
    with open("input_data.json", 'w') as json_file:
        json_file.write(formatted_json_str)

    return

if __name__ == "__main__":
    wind_data()
