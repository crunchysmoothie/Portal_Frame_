import csv
import math
import member_database as mdb

member_db = mdb.load_member_database()
rafter_section_name = '254x146x31'
rafter_section_type = 'I-Sections'
r_mem_properties = mdb.member_properties(rafter_section_type, rafter_section_name, member_db)
column_section_name = '356x171x45'
column_section_type = 'I-Sections'
c_mem_properties = mdb.member_properties(column_section_type, column_section_name, member_db)

Cu = 2000
Lx, Kx = 5.0, 1.0
Ly, Ky = 2.5, 1
Mux_Top, Mux_Bot = 80, 30
Muy_Top, Muy_Bot = 50, 20
Braced = "no"
Section_Type = "I-Sections"

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

    Cey = (math.pi ** 2 * E * section['Iy']) / (Ky * Ly) ** 2
    section['Kappa_y'] = (min(Muy_Top, Muy_Bot) / max(Muy_Top, Muy_Bot)) if max(Mux_Top, Mux_Bot) else 0
    section['w1y'] = max(0.6 - 0.4 * section['Kappa_y'], 0.4)
    section['U1y'] = max(section['w1y'] / (1 - (Cu / Cey)), 1)
    section['Zy'] = section['Zply'] if int(section['Flange Class'][-1]) in [1, 2] and int(section['Web Class'][-1]) in [1, 2] else section['Zey']
    section['Mry'] = 0.9 * section['Zy'] * fy / 1000

    section['B'] = 0.6 if int(section['Flange Class'][-1]) in [1, 2] and int(section['Web Class'][-1]) in [1, 2] else 1
    section['CSS'] = (
        Cu / Cr + section['Mrx_co'] * section['U1x'] * max(Mux_Top, Mux_Bot) / section['Mrx'] +
        section['B'] * section['U1y'] * max(Muy_Top, Muy_Bot) / section['Mry']
    )
    return section['CSS']

def calculate_oms(section, fy=350, E=200):
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

    return OMS

def calculate_ltb(section, fy=350, E=200):
    rx = section['rx']
    ry = section['ry']
    lamda_x = (Kx * Lx * 1000 / rx) * math.sqrt(fy / ((math.pi ** 2) * (E * 10 ** 3)))
    lamda_y = (Ky * Ly * 1000 / ry) * math.sqrt(fy / ((math.pi ** 2) * (E * 10 ** 3)))

    Cry = 0.9 * section['A'] * fy * ((1 + lamda_y ** (2 * 1.34)) ** (-1 / 1.34))
    Cey = (math.pi ** 2 * E * section['Iy']) / (Ky * Ly) ** 2
    B = 0.85 if int(section['Flange Class'][-1]) in [1, 2] and int(section['Web Class'][-1]) in [1, 2] else max(0.6 + 0.4 * lamda_y, 1)
    U1y = section['w1y'] / (1 - (Cu / Cey))
    U1x = section['w1x'] / (1 - (Cu / ((math.pi ** 2 * E * section['Ix']) / (Kx * Lx) ** 2))) if section['w1x'] / (1 - (Cu / ((math.pi ** 2 * E * section['Ix']) / (Kx * Lx) ** 2))) > 1 else 1
    LTB = max((Cu / Cry + (section['Mrx_co'] * U1x * max(Mux_Bot, Mux_Top) / section['Mrx']) + (
                B * U1y * max(Muy_Top, Muy_Bot) / section['Mry'])),
              max(Mux_Bot, Mux_Top) / section['Mrx'] + max(Muy_Top, Muy_Bot) / section['Mry'])

    print(Cry)

    return LTB

def read_member_database(section_type, fy=350, E=200, preferred_section = "Yes"):
    list = [sec for sec in member_db[section_type] if member_db[section_type][sec].get('Preferred','No') == preferred_section]
    lightest_section = None
    for section in list:
        section_props = mdb.member_properties(section_type, section, member_db)
        section_props['Flange Class'] = classify_flange(fy, section_props['b'], section_props['tf'])
        section_props['Web Class'] = classify_web(fy, section_props['h'], section_props['tf'], section_props['tw'], section_props['A'])
        section_props['Mrx_co'] = 0.85 if int(section_props['Flange Class'][-1]) in [1, 2] and int(section_props['Web Class'][-1]) in [1, 2] else 1

        css = calculate_css(section_props, fy, E)
        oms = calculate_oms(section_props, fy, E)
        ltb = calculate_ltb(section_props, fy, E)

        if css <= 1.0 and oms <= 1.0 and ltb <= 1.0:
            if lightest_section is None or section_props['A'] < lightest_section['A']:
                lightest_section = {
                    'Designation': section_props['Designation'],
                    'A': section_props['A'],
                    'CSS': css,
                    'OMS': oms,
                    'LTB': ltb
                }

    return lightest_section


lightest_section = read_member_database(Section_Type)

if lightest_section:
    print(f"Lightest Section: {lightest_section['Designation']}")
    print(f"CSS: {lightest_section['CSS']:.3f}")
    print(f"OMS: {lightest_section['OMS']:.3f}")
    print(f"LTB: {lightest_section['LTB']:.3f}")
else:
    print("No suitable sections found.")
