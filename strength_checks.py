import math
import member_database as mdb
import json

def member_class_check(Cu, member_prop, grade):
    fy = grade[0]['fy']
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
    rx = mb['rx']
    ry = mb['ry']
    lamda_x = (Klx * 1000 / rx) * math.sqrt(fy / ((math.pi ** 2) * (E * 10 ** 3)))
    lamda_y = (Kly * 1000 / ry) * math.sqrt(fy / ((math.pi ** 2) * (E * 10 ** 3)))

    Cr = 0.9 * mb['A'] * fy
    Crx = 0.9 * mb['A'] * fy * (1 + lamda_x ** (2 * 1.34)) ** (-1 / 1.34)
    Cry = 0.9 * mb['A'] * fy * (1 + lamda_y ** (2 * 1.34)) ** (-1 / 1.34)
    Cex = math.pi ** 2 * E * Ix / (Klx ** 2)
    Cey = math.pi ** 2 * E * Iy / (Kly ** 2)
    Mrx = 0.9 * fy * Zx / 1000
    Mry = 0.9 * fy * Zy / 1000
    Mrx_ltb = ltb_moment(mem, mb, mat_prop)

    sec_prop = {
        'Cr': Cr,
        'Crx': Crx,
        'Cry': Cry,
        'Cex': Cex,
        'Cey': Cey,
        'Mrx': Mrx,
        'Mry': Mry,
        'Mrx_ltb': Mrx_ltb,
        'lamda_x': lamda_x,
        'lamda_y': lamda_y
    }

    return sec_prop

def ltb_moment(mem, mem_prop, mat_prop):
    G = mat_prop['G']
    fy = mat_prop['fy']
    E = mat_prop['E']
    cl = mem['Class']
    w2 = mem['w2']
    Kly = mem['kly']
    Iy = mem_prop['Iy']
    Zplx = mem_prop['Zplx']
    Zex = mem_prop['Zex']
    Cw = mem_prop['Cw']
    J = mem_prop['J']

    i1 = E * 10 **3 * (Iy * 10 ** 6) * G * 10 ** 3 * J * 10 ** 3
    i2 = ((math.pi * (E * 10 ** 3) / (Kly/10 **3) ) ** 2 * Iy * 10 ** 3 * Cw)
    i3 = (w2 * math.pi / Kly) / 1000
    Mcr = i3 * ((i1 + i2) ** 0.5) / 10 ** 6
    Mp = fy * Zplx / 1000
    My = fy * Zex / 1000

    Mi = Mp if cl < 3 else My

    if Mcr > 0.67 * Mi:
        Mr = min(1.15 * 0.9 * Mi * (1 - (0.28 * Mi/Mcr)), 0.9 * Mi)
    else:
        Mr = 0.9 * Mcr

    return Mr

def cross_sectional_strength(mem, sec_props):
    cl = mem['Class']
    Cu = mem['Cu']
    w1 = mem['w1']
    Mx = abs(mem['Mx_max'])
    m_fac = 0.85 if cl < 3 else 1.0

    Cr = sec_props['Cr']
    Cex = sec_props['Cex']
    Mrx = sec_props['Mrx']

    U1x = max(1, w1/(1-(Cu/Cex)))

    return (Cu/Cr) + m_fac * U1x * Mx / Mrx

def overall_member_strength(mem, sec_props):
    cl = mem['Class']
    Cu = mem['Cu']
    w1 = mem['w1']
    Mx = abs(mem['Mx_max'])

    lamda_y = sec_props['lamda_y']
    m_fac = 0.85 if cl < 3 else 1.0

    Cr = sec_props['Crx']
    Cex = sec_props['Cex']
    Mrx = sec_props['Mrx']

    U1x = w1/(1-(Cu/Cex))

    return (Cu/Cr) + m_fac * U1x * Mx / Mrx

def lateral_torsional_buckling(mem, sec_props):
    cl = mem['Class']
    Cu = mem['Cu']
    w1 = mem['w1']
    Mx = abs(mem['Mx_max'])

    Cr = sec_props['Cry']
    Cex = sec_props['Cex']
    Mrx = sec_props['Mrx']

    U1x = max(1, w1 / (1 - (Cu / Cex)))
    m_fac = 0.85 if cl < 3 else 1.0


    Check1 = (Cu / Cr) + m_fac * U1x * Mx / Mrx
    Check2 = Mx / Mrx

    return Check1, Check2

def member_design(mb, mem, mat_prop):
    sec_props = section_properties(mb, mem, mat_prop)
    CSS = cross_sectional_strength(mem, sec_props)
    OMS = overall_member_strength(mem, sec_props)
    LTB = lateral_torsional_buckling(mem, sec_props)

    return CSS, OMS, LTB

# member_db = mdb.load_member_database()
# mem_props = mdb.member_properties("I-Sections", '457x191x74', member_db)
# mem = {'Name': 'M1', 'kly': 3.5, 'klx': 8.4, 'type': 'column', 'section': '457x191x74', 'Cu': 30.571,
#        'Class': 1, 'Mx_max': 19.68, 'Mx_top': -7.021, 'Mx_bot': 19.68, 'w1': 1.0, 'w2': 2.1628}
# max_m = mem['Mx_max']
# top_m = mem['Mx_top']
# bot_m = mem['Mx_bot']
# mat_props = {"fy":355,"E":200,"G":77 ,"nu":0.3,"rho":7.85e-08}
# sec_prop = section_properties(mem_props, mem, mat_props)
# print(cross_sectional_strength(mem, sec_prop))
# print(overall_member_strength(mem, sec_prop))
# print(lateral_torsional_buckling(mem, sec_prop))

