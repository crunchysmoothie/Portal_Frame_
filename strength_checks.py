import math
import member_database as mdb
import json

def member_class_check(Cu, member_prop):
    fy = 355
    b, h, tf, tw = member_prop['b'], member_prop['h'], member_prop['tf'], member_prop['tw']
    # Flange Class
    ratio = b / (2 * tf)
    limits = [145 / math.sqrt(fy), 170 / math.sqrt(fy), 200 / math.sqrt(fy)]
    fl_cl = next((i + 1 for i, limit in enumerate(limits) if ratio < limit), 4)

    # Web Class
    cy = member_prop['A'] * fy
    web_ratio = (h - 2 * tf) / tw
    limits = [(1100, 0.39), (1700, 0.61), (1900, 0.65)]
    cl_w = next((j + 1 for j, (limit, coeff) in enumerate(limits) if
                 web_ratio < (limit / math.sqrt(fy)) * (1 - coeff * (Cu / (0.9 * cy)))), 4)

    return max(fl_cl, cl_w)

def element_properties(Mx_max, Mx_top, Mx_bot):
    # X-axis Checks
    m_min = min(Mx_top, Mx_bot, key=abs)
    m_max = max(Mx_top, Mx_bot, key=abs)
    k = -1 * m_min / m_max

    w1 = 1.0
    if Mx_max > abs(Mx_top) * 1.1 and Mx_max > abs(Mx_bot) * 1.1:
        w2 = 1.0
    else:
        w2 = min(1.75 + 1.05 * k + 0.3 * k ** 2, 2.5)

    return w1, round(w2, 4)

def section_properties(mb, mem, mat_prop):
    fy = mat_prop['fy']
    E = mat_prop['E']
    cl = mem['Class']
    Ix = mb['Ix']
    Iy = mb['Iy']
    Klx = mem['klx']
    Kly = mem['kly']
    Zx = mb['Zplx'] if cl < 3 else mb['Zex']
    Zy = mb['Zply'] if cl < 3 else mb['Zpy']

    Cr = 0.9 * mb['A'] * fy
    Cex = math.pi ** 2 * E * Ix / (Klx ** 2)
    Cey = math.pi ** 2 * E * Iy / (Kly ** 2)
    Mrx = 0.9 * fy * Zx / 1000
    Mry = 0.9 * fy * Zy / 1000
    Mrx_ltb = None

    Mcr = ltb_moment(cl, mem, mb, mat_prop)
    rx = mb['rx']
    ry = mb['ry']
    lamda_x = (Klx * 1000 / rx) * math.sqrt(fy / ((math.pi ** 2) * (E * 10 ** 3)))
    lamda_y = (Kly * 1000 / ry) * math.sqrt(fy / ((math.pi ** 2) * (E * 10 ** 3)))

    nm = ['Cr', 'Cex', 'Cey', 'Mrx', 'Mry', 'Mcr']
    val = [Cr, Cex, Cey, Mrx, Mry, Mcr]
    for i in range(len(nm)):
        print(f'{nm[i]} = {round(val[i], 2)}')

    return Cr, Cex, Cey, Mrx, Mry, Mrx_ltb, lamda_x, lamda_y

def ltb_moment(cl, mem, mem_prop, mat_prop):
    G = mat_prop['G']
    fy = mat_prop['fy']
    E = mat_prop['E']
    w2 = mem['w2']
    Klx = mem['klx']
    Iy = mem_prop['Iy']
    Cw = mem_prop['Cw']
    J = mem_prop['J']

    i1 = E * Iy * G * J
    i2 = (math.pi * E / Klx) ** 2 * Iy * Cw
    i3 = w2 * math.pi / Klx
    Mcr = i3 * ((i1 + i2) ** 0.5)
    print(f'Mcr = {round(Mcr, 2)}')
    return Mcr

def cross_sectional_strength(args):
    Cr, Cex, Cey, Mrx, Mry = args

    return None

def material_props(grade):
    with open("input_data.json") as f:
        data = json.load(f)["steel_grades"]  # list[dict]

    for item in data:  # scan the list
        if grade in item:  # found it
            return item[grade]

    # fallthrough → not found
    raise ValueError(f"Unknown steel grade: {grade!r}")


member_db = mdb.load_member_database()
mem_props = mdb.member_properties("I-Sections", '457x191x74', member_db)
mem = {'Name': 'M1', 'kly': 2.333, 'klx': 8.4, 'type': 'column', 'section': '457x191x74', 'Cu': 30.571, 'Class': 1,
       'Mx_max': 10.779, 'Mx_top': -7.021, 'Mx_bot': 10.777, 'w1': 1.0, 'w2': 1.1933}
max_m = mem['Mx_max']
top_m = mem['Mx_top']
bot_m = mem['Mx_bot']
mat_props = material_props('Steel_S355')
section_properties(mem_props, mem, mat_props)