import json
import math
import numpy as np


def import_data(file):
    with open(file) as f:
        data = json.load(f)
        return data

def normalize_wind_data(data):
    wind = data.get("wind_data", {})
    if isinstance(wind, list):
        return wind[0] if wind else {}
    return wind

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

def wind_data_duo_n():
    angles = np.array([5, 15, 30, 45])

    # Wind 0 Upward
    neg_w0 = np.array([
        [-1.7, -1.2, -0.6, -0.6, -0.6],
        [-0.9, -0.8, -0.3, -0.4, -1.0],
        [-0.5, -0.5, -0.2, -0.4, -0.5],
        [0, 0, 0, -0.2, -0.3]
    ])

    # Wind 0 Downward
    pos_w0 = np.array([
        [0, 0, 0, -0.6, 0.2],
        [0.2, 0.2, 0.2, 0, 0],
        [0.7, 0.7, 0.4, 0, 0],
        [0.7, 0.7, 0.6, 0, 0]
    ])

    # Wind 90 Upward
    neg_w90 = np.array([
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
    results_90 = []

    wind = data['wind_data'][0]
    bs = calculate_basic_wind_speed(wind['fundamental_basic_wind_speed'], wind['return_period'])
    roughness = calculate_terrain_roughness(wind['apex_height'], wind['terrain_category'])
    peak_pressure = calculate_peak_wind_pressure(wind['topographic_factor'], bs, roughness, wind['altitude'])

    h_d_zone_d = wind['apex_height'] / wind['gable_width']
    h_d_zone_e = wind['apex_height'] / wind['gable_width']

    cpe_d_coeff = min([max([0.85+((1-0.85)/(5-1)*(h_d_zone_d-1)), 0.85]), 1])
    cpe_e_coeff = min([max([0.85+((1-0.85)/(5-1)*(h_d_zone_e-1)), 0.85]), 1])

    cpe_value_d = interpolate_cpe(h_d_zone_d, h_d_data, cpe_d) * cpe_d_coeff
    cpe_value_e = interpolate_cpe(h_d_zone_e, h_d_data, cpe_e) * cpe_e_coeff

    cpe_negative = np.array([
        np.interp(wind['roof_pitch'], angles, neg_w0[:, i])
        for i in range(neg_w0.shape[1])
    ])

    cpe_positive = np.array([
        np.interp(wind['roof_pitch'], angles, pos_w0[:, i])
        for i in range(pos_w0.shape[1])
    ])

    cpe_wind_90 = np.array([
        np.interp(wind['roof_pitch'], angles, neg_w90[:, i])
        for i in range(neg_w90.shape[1])
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

    zones_90 = {
        "A": -1.2,
        "B": -0.8,
        "C": -0.5,
        "D": cpe_value_d,
        "E": cpe_value_e,
        "F": cpe_wind_90[0],
        "G": cpe_wind_90[1],
        "H": cpe_wind_90[2],
        "I": cpe_wind_90[3]
    }

    zones = zones_normal()
    r_spacing = wind['rafter_spacing']


    for zone, cpe in zones_up.items():
        results_up.append({
            "Zone": zone,
            "cpe": round(cpe, 4),
            "Length": zones[zone]["0_deg"],
            "cpi=0.2": round(calculate_pressure(peak_pressure, cpe, 0.2) * r_spacing / -1000, 5),
            "cpi=-0.3": round(calculate_pressure(peak_pressure, cpe, -0.3) * r_spacing / -1000, 5)
        })


    for zone, cpe in zones_down.items():
        results_down.append({
            "Zone": zone,
            "cpe": round(cpe, 4),
            "Length": zones[zone]["0_deg"],
            "cpi=0.2": round(calculate_pressure(peak_pressure, cpe, 0.2) * r_spacing / -1000, 5),
            "cpi=-0.3": round(calculate_pressure(peak_pressure, cpe, -0.3) * r_spacing / -1000, 5)
        })

    for zone, cpe in zones_90.items():
        results_90.append({
            "Zone": zone,
            "cpe": round(cpe, 4),
            "Length": zones[zone]["90_deg"],
            "cpi=0.2": round(calculate_pressure(peak_pressure, cpe, 0.2) * r_spacing / -1000, 5),
            "cpi=-0.3": round(calculate_pressure(peak_pressure, cpe, -0.3) * r_spacing / -1000, 5)
        })

    print("Wind Upward Pressures")
    print(f"{'Zone':<6}{'cpe':<10}{'Length':<10}{'Load. cpi=0.2':<18}{'Load. cpi=-0.3'}")
    print("-" * 56)
    for result in results_up:
        cpe_display = f"+{result['cpe']:.2f}" if result['cpe'] > 0 else f"{result['cpe']:.2f}"
        length_display = f"{result['Length']:.2f}"
        pressure_cpi_0_2 = f"+{result['cpi=0.2'] * 1000:.2f}" if result['cpi=0.2'] > 0 else f"{result['cpi=0.2'] * 1000:.2f}"
        pressure_cpi_neg_0_3 = f"+{result['cpi=-0.3'] * 1000:.2f}" if result['cpi=-0.3'] > 0 else f"{result['cpi=-0.3'] * 1000:.2f}"

        print(f"{result['Zone']:<6}{cpe_display:<10}{length_display + ' m':<10}{pressure_cpi_0_2 + ' kN/m' :<18} {pressure_cpi_neg_0_3} kN/m")

    print("\nWind Downward Pressures")
    print(f"{'Zone':<6}{'cpe':<10}{'Length':<10}{'Load cpi=0.2':<18}{'Load cpi=-0.3'}")
    print("-" * 56)
    for result in results_down:
        cpe_display = f"+{result['cpe']:.2f}" if result['cpe'] > 0 else f"{result['cpe']:.2f}"
        length_display = f"{result['Length']:.2f}"
        pressure_cpi_0_2 = (f"+{result['cpi=0.2'] * 1000:.2f}" if result['cpi=0.2'] > 0 else f"{result['cpi=0.2'] * 1000:.2f}")
        pressure_cpi_neg_0_3 = (f"+{result['cpi=-0.3'] * 1000:.2f}" if result['cpi=-0.3'] > 0 else f"{result['cpi=-0.3'] * 1000:.2f}")

        print(f"{result['Zone']:<6}{cpe_display:<10}{length_display + ' m':<10}{pressure_cpi_0_2 + ' kN/m':<18} {pressure_cpi_neg_0_3} kN/m")

    print("\nWind 90 Pressures")
    print(f"{'Zone':<6}{'cpe':<10}{'Length':<10}{'Load cpi=0.2':<18}{'Load cpi=-0.3'}")
    print("-" * 56)
    for result in results_90:
        cpe_display = f"+{result['cpe']:.2f}" if result['cpe'] > 0 else f"{result['cpe']:.2f}"
        length_display = f"{result['Length']:.2f}"
        pressure_cpi_0_2 = (f"+{result['cpi=0.2'] * 1000:.2f}" if result['cpi=0.2'] > 0 else f"{result['cpi=0.2'] * 1000:.2f}")
        pressure_cpi_neg_0_3 = (f"+{result['cpi=-0.3'] * 1000:.2f}" if result['cpi=-0.3'] > 0 else f"{result['cpi=-0.3'] * 1000:.2f}")

        print(f"{result['Zone']:<6}{cpe_display:<10}{length_display + ' m':<10}{pressure_cpi_0_2 + ' kN/m':<18} {pressure_cpi_neg_0_3} kN/m")

    data["wind_zones_0U"] = results_up
    data["wind_zones_0D"] = results_down
    data["wind_zones_90"] = results_90

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

def wind_data_mono_n():
    angles = np.array([5, 15, 30, 45])

    # Wind 0 Upward
    neg_w0 = np.array([
        [-1.7, -1.2, -0.6, -0.6, -0.6],
        [-0.9, -0.8, -0.3, -0.4, -1.0],
        [-0.5, -0.5, -0.2, -0.4, -0.5],
        [0, 0, 0, -0.2, -0.3]
    ])

    # Wind 0 Downward
    pos_w0 = np.array([
        [0, 0, 0, -0.6, 0.2],
        [0.2, 0.2, 0.2, 0, 0],
        [0.7, 0.7, 0.4, 0, 0],
        [0.7, 0.7, 0.6, 0, 0]
    ])

    # Wind 90 coefficients from SANS 10160-3 Table 9 (mono-pitch, cpe,10)
    # Columns mapped as: Fup, G, H, I
    neg_w90 = np.array([
        [-2.1, -1.8, -0.6, -0.5],  # 5 deg
        [-2.4, -1.9, -0.8, -0.7],  # 15 deg
        [-2.1, -1.5, -1.0, -0.8],  # 30 deg
        [-1.5, -1.4, -1.0, -0.9],  # 45 deg
    ])

    data = import_data("input_data.json")
    h_d_data = [0.25, 1.0]
    cpe_d = [0.70, 0.80]
    cpe_e = [-0.3, -0.50]

    results_up = []
    results_down = []
    results_90 = []

    wind = normalize_wind_data(data)
    bs = calculate_basic_wind_speed(wind['fundamental_basic_wind_speed'], wind['return_period'])
    roughness = calculate_terrain_roughness(wind['apex_height'], wind['terrain_category'])
    peak_pressure = calculate_peak_wind_pressure(wind['topographic_factor'], bs, roughness, wind['altitude'])

    h_d_zone_d = wind['eaves_height'] / wind['gable_width']
    h_d_zone_e = wind['apex_height'] / wind['gable_width']

    cpe_d_coeff = min([max([0.85 + ((1 - 0.85) / (5 - 1) * (h_d_zone_d - 1)), 0.85]), 1])
    cpe_e_coeff = min([max([0.85 + ((1 - 0.85) / (5 - 1) * (h_d_zone_e - 1)), 0.85]), 1])

    cpe_value_d = interpolate_cpe(h_d_zone_d, h_d_data, cpe_d) * cpe_d_coeff
    cpe_value_e = interpolate_cpe(h_d_zone_e, h_d_data, cpe_e) * cpe_e_coeff

    cpe_negative = np.array([
        np.interp(wind['roof_pitch'], angles, neg_w0[:, i])
        for i in range(neg_w0.shape[1])
    ])

    cpe_positive = np.array([
        np.interp(wind['roof_pitch'], angles, pos_w0[:, i])
        for i in range(pos_w0.shape[1])
    ])

    cpe_wind_90 = np.array([
        np.interp(wind['roof_pitch'], angles, neg_w90[:, i])
        for i in range(neg_w90.shape[1])
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

    zones_90 = {
        "A": -1.2,
        "B": -0.8,
        "C": -0.5,
        "D": cpe_value_d,
        "E": cpe_value_e,
        "F": cpe_wind_90[0],
        "G": cpe_wind_90[1],
        "H": cpe_wind_90[2],
        "I": cpe_wind_90[3]
    }

    zones = zones_normal()
    r_spacing = wind['rafter_spacing']

    for zone, cpe in zones_up.items():
        results_up.append({
            "Zone": zone,
            "cpe": round(cpe, 4),
            "Length": zones[zone]["0_deg"],
            "cpi=0.2": round(calculate_pressure(peak_pressure, cpe, 0.2) * r_spacing / -1000, 5),
            "cpi=-0.3": round(calculate_pressure(peak_pressure, cpe, -0.3) * r_spacing / -1000, 5)
        })

    for zone, cpe in zones_down.items():
        results_down.append({
            "Zone": zone,
            "cpe": round(cpe, 4),
            "Length": zones[zone]["0_deg"],
            "cpi=0.2": round(calculate_pressure(peak_pressure, cpe, 0.2) * r_spacing / -1000, 5),
            "cpi=-0.3": round(calculate_pressure(peak_pressure, cpe, -0.3) * r_spacing / -1000, 5)
        })

    for zone, cpe in zones_90.items():
        results_90.append({
            "Zone": zone,
            "cpe": round(cpe, 4),
            "Length": zones[zone]["90_deg"],
            "cpi=0.2": round(calculate_pressure(peak_pressure, cpe, 0.2) * r_spacing / -1000, 5),
            "cpi=-0.3": round(calculate_pressure(peak_pressure, cpe, -0.3) * r_spacing / -1000, 5)
        })

    data["wind_zones_0U"] = results_up
    data["wind_zones_0D"] = results_down
    data["wind_zones_90"] = results_90

    with open("input_data.json", 'w') as json_file:
        json.dump(data, json_file, indent=2)

    return


def _get_blocking_factor(wind):
    """Return canopy blocking factor in [0, 1]."""
    bf = wind.get("blocking_factor", 0.0)
    try:
        bf = float(bf)
    except (TypeError, ValueError):
        bf = 0.0
    return min(max(bf, 0.0), 1.0)


def _interp(angle, angles, values):
    return float(np.interp(angle, np.array(angles), np.array(values)))


def _interp_phi(min_phi0, min_phi1, phi):
    return min_phi0 + phi * (min_phi1 - min_phi0)


def _wind_data_canopy(roof_type):
    data = import_data("input_data.json")
    wind = normalize_wind_data(data)

    bs = calculate_basic_wind_speed(wind['fundamental_basic_wind_speed'], wind['return_period'])
    roughness = calculate_terrain_roughness(wind['apex_height'], wind['terrain_category'])
    peak_pressure = calculate_peak_wind_pressure(wind['topographic_factor'], bs, roughness, wind['altitude'])
    bf = _get_blocking_factor(wind)
    pitch = wind['roof_pitch']

    if roof_type == "Mono Pitched":
        # SANS Table 13: cp,net zones A/B/C and D=max(B,C)
        ang = [0, 5, 10, 15, 20, 25, 30]
        A_max = [0.5, 0.8, 1.2, 1.4, 1.7, 2.0, 2.2]
        A_min0 = [-0.6, -1.1, -1.5, -1.8, -2.2, -2.6, -3.0]
        A_min1 = [-1.5, -1.6, -2.1, -1.6, -1.6, -1.5, -1.5]

        B_max = [1.8, 2.1, 2.4, 2.7, 2.9, 3.1, 3.2]
        B_min0 = [-1.3, -1.7, -2.0, -2.4, -2.8, -3.2, -3.8]
        B_min1 = [-1.8, -2.2, -2.6, -2.9, -2.9, -2.5, -2.2]

        C_max = [1.1, 1.3, 1.6, 1.8, 2.1, 2.3, 2.4]
        C_min0 = [-1.4, -1.8, -2.1, -2.5, -2.9, -3.2, -3.6]
        C_min1 = [-2.2, -2.5, -2.7, -3.0, -3.0, -2.8, -2.7]

        a_down = _interp(pitch, ang, A_max)
        b_down = _interp(pitch, ang, B_max)
        c_down = _interp(pitch, ang, C_max)
        d_down = max(b_down, c_down)

        a_up = _interp_phi(_interp(pitch, ang, A_min0), _interp(pitch, ang, A_min1), bf)
        b_up = _interp_phi(_interp(pitch, ang, B_min0), _interp(pitch, ang, B_min1), bf)
        c_up = _interp_phi(_interp(pitch, ang, C_min0), _interp(pitch, ang, C_min1), bf)
        d_up = max(b_up, c_up)

        # Map Table 13 zones into existing A..J container for compatibility.
        zones_down = {"A": a_down, "B": b_down, "C": c_down, "D": d_down, "E": d_down,
                      "F": a_down, "G": b_down, "H": c_down, "I": d_down, "J": d_down}
        zones_up = {"A": a_up, "B": b_up, "C": c_up, "D": d_up, "E": d_up,
                    "F": a_up, "G": b_up, "H": c_up, "I": d_up, "J": d_up}
        zones_90 = {"A": a_up, "B": b_up, "C": c_up, "D": d_up, "E": d_up,
                    "F": a_up, "G": b_up, "H": c_up, "I": d_up}
    else:
        # SANS Table 14: cp,net zones A/B/C/D and E=max(B,C)
        ang = [-20, -15, -10, -5, 5, 10, 15, 20, 25, 30]
        A_max = [0.8, 0.6, 0.6, 0.5, 0.6, 0.7, 0.9, 1.1, 1.2, 1.3]
        A_min0 = [-0.9, -0.8, -0.8, -0.7, -0.6, -0.7, -0.9, -1.2, -1.4, -1.4]
        A_min1 = [-1.5, -1.6, -1.6, -1.5, -1.3, -1.3, -1.3, -1.4, -1.4, -1.4]

        B_max = [1.6, 1.5, 1.4, 1.5, 1.8, 1.8, 1.9, 1.9, 1.9, 1.9]
        B_min0 = [-1.3, -1.3, -1.3, -1.3, -1.4, -1.5, -1.7, -1.8, -1.9, -1.9]
        B_min1 = [-2.4, -2.7, -2.7, -2.4, -2.0, -2.0, -2.2, -2.2, -2.0, -1.8]

        C_max = [0.6, 0.7, 0.8, 0.8, 1.3, 1.4, 1.4, 1.5, 1.6, 1.6]
        C_min0 = [-1.6, -1.6, -1.5, -1.6, -1.4, -1.4, -1.4, -1.4, -1.4, -1.4]
        C_min1 = [-2.4, -2.6, -2.6, -2.4, -1.8, -1.8, -1.6, -1.6, -1.5, -1.4]

        D_max = [1.7, 1.4, 1.1, 0.8, 0.4, 0.4, 0.4, 0.4, 0.5, 0.7]
        D_min0 = [-0.6, -0.6, -0.6, -0.6, -1.1, -1.4, -1.8, -2.0, -2.0, -2.0]
        D_min1 = [-0.6, -0.6, -0.6, -0.6, -1.5, -1.8, -2.1, -2.1, -2.0, -2.0]

        a_down = _interp(pitch, ang, A_max)
        b_down = _interp(pitch, ang, B_max)
        c_down = _interp(pitch, ang, C_max)
        d_down = _interp(pitch, ang, D_max)
        e_down = max(b_down, c_down)

        a_up = _interp_phi(_interp(pitch, ang, A_min0), _interp(pitch, ang, A_min1), bf)
        b_up = _interp_phi(_interp(pitch, ang, B_min0), _interp(pitch, ang, B_min1), bf)
        c_up = _interp_phi(_interp(pitch, ang, C_min0), _interp(pitch, ang, C_min1), bf)
        d_up = _interp_phi(_interp(pitch, ang, D_min0), _interp(pitch, ang, D_min1), bf)
        e_up = max(b_up, c_up)

        zones_down = {"A": a_down, "B": b_down, "C": c_down, "D": d_down, "E": e_down,
                      "F": a_down, "G": b_down, "H": c_down, "I": d_down, "J": e_down}
        zones_up = {"A": a_up, "B": b_up, "C": c_up, "D": d_up, "E": e_up,
                    "F": a_up, "G": b_up, "H": c_up, "I": d_up, "J": e_up}
        zones_90 = {"A": a_up, "B": b_up, "C": c_up, "D": d_up, "E": e_up,
                    "F": a_up, "G": b_up, "H": c_up, "I": d_up}

    zone_lengths = zones_normal()
    r_spacing = wind['rafter_spacing']

    results_up = []
    results_down = []
    results_90 = []

    for zone, cpe in zones_up.items():
        results_up.append({
            "Zone": zone,
            "cpe": round(cpe, 4),
            "Length": zone_lengths[zone]["0_deg"],
            # cp,net is already net pressure coefficient for canopy roofs.
            "cpi=0.2": round(peak_pressure * cpe * r_spacing / -1000, 5),
            "cpi=-0.3": round(peak_pressure * cpe * r_spacing / -1000, 5)
        })

    for zone, cpe in zones_down.items():
        results_down.append({
            "Zone": zone,
            "cpe": round(cpe, 4),
            "Length": zone_lengths[zone]["0_deg"],
            "cpi=0.2": round(peak_pressure * cpe * r_spacing / -1000, 5),
            "cpi=-0.3": round(peak_pressure * cpe * r_spacing / -1000, 5)
        })

    for zone, cpe in zones_90.items():
        results_90.append({
            "Zone": zone,
            "cpe": round(cpe, 4),
            "Length": zone_lengths[zone]["90_deg"],
            "cpi=0.2": round(peak_pressure * cpe * r_spacing / -1000, 5),
            "cpi=-0.3": round(peak_pressure * cpe * r_spacing / -1000, 5)
        })

    data["wind_zones_0U"] = results_up
    data["wind_zones_0D"] = results_down
    data["wind_zones_90"] = results_90

    with open("input_data.json", 'w') as json_file:
        json.dump(data, json_file, indent=2)


def wind_data_duo_c():
    return _wind_data_canopy("Duo Pitched")


def wind_data_mono_c():
    return _wind_data_canopy("Mono Pitched")
def print_zones(zones):
    print(f"{'Zone':<5} {'0_deg':<20} {'90_deg':<20}")
    print("-" * 50)

    def fmt(val):
        # scalar (int or float)
        if isinstance(val, (int, float)):
            return f"({val:.2f})"
        # 2-component tuple / list
        elif isinstance(val, (tuple, list)) and len(val) == 2:
            return f"({val[0]:.2f}, {val[1]:.2f})"
        # fallback – show whatever it is
        return str(val)

    for zone, v in zones.items():
        print(f"{zone:<5} {fmt(v['0_deg']):<20} {fmt(v['90_deg']):<20}")

def zones_normal():
    data = import_data('input_data.json')['wind_data'][0]


    b_0 = data['building_length']
    b_90 = data['gable_width']
    d_0 = data['gable_width']
    d_90 = data['building_length']
    e_height = data['eaves_height']
    a_height = data['apex_height']

    e_0 = min(b_0, a_height * 2)
    e_90 = min(b_90, a_height * 2)

    if e_0 < d_0:
        A_l0 = e_0 / 5
        B_l0 = e_0 * 4 / 5
        C_l0 = d_0 - e_0

    elif e_0 >= d_0:
        A_l0 = e_0 / 5
        B_l0 = d_0 - e_0 / 5
        C_l0 = 0

    else:
        A_l0 = d_0 - e_0
        B_l0 = 0
        C_l0 = 0

    if e_90 < d_90:
        A_l90 = e_90 / 5
        B_l90 = e_90 * 4 / 5
        C_l90 = d_90 - e_90

    elif e_90 >= d_90:
        A_l90 = e_90 / 5
        B_l90 = d_90 - e_90 / 5
        C_l90 = 0

    else:
        A_l90 = d_90
        B_l90 = 0
        C_l90 = 0

    D_l0 = b_0
    E_l0 = b_0
    D_l90 = b_90
    E_l90 = b_90
    F_l0 = e_0 / 10
    G_l0 = e_0 / 10
    F_l90 = e_90 / 10
    G_l90 = e_90 / 10
    H_l90 = e_90 / 2 - b_90 / 10
    I_l90 = d_90 - e_90 / 2
    J_l90 = 0

    if data['building_roof'] == 'Duo Pitched':

        H_l0 = d_0 / 2 - e_0 / 10
        I_l0 = d_0 / 2 - e_0 / 10
        J_l0 = e_0 / 10

    else:
        H_l0 = d_0 - e_0 / 10
        I_l0 = 0
        J_l0 = 0


    zones = {
        "A": {"0_deg": A_l0, "90_deg": A_l90},
        "B": {"0_deg": B_l0, "90_deg": B_l90},
        "C": {"0_deg": C_l0, "90_deg": C_l90},
        "D": {"0_deg": D_l0, "90_deg": D_l90},
        "E": {"0_deg": E_l0, "90_deg": E_l90},
        "F": {"0_deg": F_l0, "90_deg": F_l90},
        "G": {"0_deg": G_l0, "90_deg": G_l90},
        "H": {"0_deg": H_l0, "90_deg": H_l90},
        "I": {"0_deg": I_l0, "90_deg": I_l90},
        "J": {"0_deg": J_l0, "90_deg": J_l90},
    }
    return zones

def wind_out():
    data = import_data('input_data.json')['wind_data'][0]
    if data['building_type'] == 'Normal':
        if data['building_roof'] == 'Duo Pitched':
            return wind_data_duo_n()
        elif data['building_roof'] == 'Mono Pitched':
            return wind_data_mono_n()

    elif data['building_type'] == 'Canopy':
        if data['building_roof'] == 'Duo Pitched':
            return wind_data_duo_c()
        elif data['building_roof'] == 'Mono Pitched':
            return wind_data_mono_c()

if __name__ == "__main__":
    wind_out()
    # print_zones(zones_normal())

