import csv
import math

Cu, Lx, Kx = 500, 5.0, 1.0  # Example values; modify as needed
Ly, Ky = 2.5, 1
Mux_Top, Mux_Bot = 200, 50
Muy_Top, Muy_Bot = 150, 10

def classify_flange(fy, b, tf):
    ratio = b / (2 * tf)
    limits = [145 / math.sqrt(fy), 170 / math.sqrt(fy), 200 / math.sqrt(fy)]
    return f"Class {next((i + 1 for i, limit in enumerate(limits) if ratio < limit), 4)}"

def classify_web(fy, h, tf, tw, A):
    cy = A * fy
    web_ratio = (h - 2 * tf) / tw
    limits = [(1100, 0.39), (1700, 0.61), (1900, 0.65)]
    return f"Class {next((i + 1 for i, (limit, coeff) in enumerate(limits) if web_ratio < (limit / math.sqrt(fy)) * (1 - coeff * (Cu / (0.9 * cy)))), 4)}"

def calculate_css(section, fy, E):
    Cr = 0.9 * fy * section['A']
    Cex = (math.pi ** 2 * E * section['Ix']) / (Kx * Lx) ** 2
    section['Kappa_x'] = (min(Mux_Top, Mux_Bot) / max(Mux_Top, Mux_Bot)) if max(Mux_Top, Mux_Bot) else 0
    section['w1x'] = max(0.6 - 0.4 * section['Kappa_x'], 0.4)
    section['U1x'] = max(section['w1x'] / (1 - (Cu / Cex)), 1)

    section['Zx'] = section['Zplx'] if int(section['Flange Class'][-1]) in [1, 2] and int(section['Web Class'][-1]) in [1, 2] else section['Zex']
    section['Mrx'] = 0.9 * section['Zx'] * fy / 1000
    section['U1y'] = calculate_u1y(section, fy, E)
    section['Zy'] = section['Zply'] if int(section['Flange Class'][-1]) in [1, 2] and int(section['Web Class'][-1]) in [1, 2] else section['Zey']
    section['Mry'] = 0.9 * section['Zy'] * fy / 1000

    section['B'] = 0.6 if int(section['Flange Class'][-1]) in [1, 2] and int(section['Web Class'][-1]) in [1, 2] else 1
    section['CSS'] = (
        Cu / Cr + section['Mrx_co'] * section['U1x'] * max(Mux_Top, Mux_Bot) / section['Mrx'] +
        section['B'] * section['U1y'] * max(Muy_Top, Muy_Bot) / section['Mry']
    )

    print(f"Cross Sectional Strength (CSS): {section['CSS']:.3f}")

def calculate_u1y(section, fy, E):
    Cey = (math.pi ** 2 * E * section['Iy']) / (Ky * Ly) ** 2
    section['Kappa_y'] = (min(Muy_Top, Muy_Bot) / max(Muy_Top, Muy_Bot)) if max(Muy_Top, Muy_Bot) else 0
    section['w1y'] = max(0.6 - 0.4 * section['Kappa_y'], 0.4)
    return max(section['w1y'] / (1 - (Cu / Cey)), 1)

def calculate_oms(section, fy=350, E=200, Braced="No"):
    rx = section['rx']
    ry = section['ry']
    lamda_x = (Kx * Lx * 1000 / rx) * math.sqrt(fy / ((math.pi ** 2) * (E * 10 ** 3)))
    lamda_y = (Ky * Ly * 1000 / ry) * math.sqrt(fy / ((math.pi ** 2) * (E * 10 ** 3)))

    Crx = 0.9 * section['A'] * fy * ((1 + lamda_x ** (2 * 1.34)) ** (-1 / 1.34))
    Cry = 0.9 * section['A'] * fy * ((1 + lamda_y ** (2 * 1.34)) ** (-1 / 1.34))

    Cex = (math.pi ** 2 * E * section['Ix']) / (Kx * Lx) ** 2
    Cey = (math.pi ** 2 * E * section['Iy']) / (Ky * Ly) ** 2

    section['w1x'] = max(0.6 - 0.4 * (min(Mux_Top, Mux_Bot) / max(Mux_Top, Mux_Bot)), 0.4)
    U1x = section['w1x'] / (1 - (Cu / Cex)) if Braced.lower() == "yes" else 1
    section['w1y'] = max(0.6 - 0.4 * (min(Muy_Top, Muy_Bot) / max(Muy_Top, Muy_Bot)), 0.4)
    U1y = section['w1y'] / (1 - (Cu / Cey))

    B = 0.85 if int(section['Flange Class'][-1]) in [1, 2] and int(section['Web Class'][-1]) in [1, 2] else max(0.6 + 0.4 * lamda_y, 1)

    if Muy_Bot > 0 or Muy_Top > 0:
        if ((Kx * Lx / rx) / (Ky * Ly / ry)) > 1:
            OMS = (Cu / Crx + (section['Mrx_co'] * U1x * max(Mux_Bot, Mux_Top) / section['Mrx']) + (B * U1y * max(Muy_Top, Muy_Bot) / section['Mry']))
        else:
            OMS = (Cu / Cry + (section['Mrx_co'] * U1x * max(Mux_Bot, Mux_Top) / section['Mrx']) + (B * U1y * max(Muy_Top, Muy_Bot) / section['Mry']))
    else:
        OMS = (Cu / Crx + (section['Mrx_co'] * U1x * max(Mux_Bot, Mux_Top) / section['Mrx']) + (B * U1y * max(Muy_Top, Muy_Bot) / section['Mry']))


    print(f"Overall Member Strength (OMS): {OMS:.3f}")
    return

def read_member_database(filename, section_name, fy=350, E=200):
    for row in csv.DictReader(open(filename)):
        if row['Designation'] == section_name:
            section = {k: float(v) for k, v in row.items() if k != 'Designation'}
            section['Flange Class'] = classify_flange(fy, section['b'], section['tf'])
            section['Web Class'] = classify_web(fy, section['h'], section['tf'], section['tw'], section['A'])
            section['Mrx_co'] = 0.85 if int(section['Flange Class'][-1]) in [1, 2] and int(section['Web Class'][-1]) in [1, 2] else 1

            # Calculate CSS and OMS
            calculate_css(section, fy, E)
            calculate_oms(section, fy, E, Braced="No")
            return
    print(f"Section '{section_name}' not found in the database.")

# Example call
read_member_database('member_database.csv', '533x210x122')

def LTB (fy, d):
    return 0


