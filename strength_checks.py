import math
import member_database as mdb
import json

def member_class_details(Cu, member_prop, grade):
    """Return the flange/web classification calculation and governing class."""
    fy = grade[0]['fy'] if isinstance(grade, (list, tuple)) else grade['fy']
    b, h, tf, tw = member_prop['b'], member_prop['h'], member_prop['tf'], member_prop['tw']
    # Flange Class
    flange_ratio = b / (2 * tf)
    flange_limits = [145 / math.sqrt(fy), 170 / math.sqrt(fy), 200 / math.sqrt(fy)]
    fl_cl = next((i + 1 for i, limit in enumerate(flange_limits) if flange_ratio < limit), 4)

    # Web Class
    cy = member_prop['A'] * fy
    web_ratio = (h - 2 * tf) / tw
    web_coefficients = [(1100, 0.39), (1700, 0.61), (1900, 0.65)]
    # Axial tension must not reduce the allowable web slenderness through a
    # negative compression ratio. For combined tension and bending, section
    # classification is based on the flexural compression component here.
    compression = max(float(Cu), 0.0)
    compression_ratio = compression / (0.9 * cy)
    web_limits = [
        (limit / math.sqrt(fy)) * (1 - coeff * compression_ratio)
        for limit, coeff in web_coefficients
    ]
    cl_w = next((j + 1 for j, limit in enumerate(web_limits) if web_ratio < limit), 4)

    return {
        'flange_ratio': flange_ratio,
        'flange_limits': flange_limits,
        'flange_class': fl_cl,
        'web_ratio': web_ratio,
        'web_limits': web_limits,
        'web_class': cl_w,
        'compression_ratio': compression_ratio,
        'class': max(fl_cl, cl_w),
    }


def member_class_check(Cu, member_prop, grade):
    return member_class_details(Cu, member_prop, grade)['class']

def element_property_details(Mx_max, Mx_top, Mx_bot):
    """Return the moment-gradient quantities used for omega1 and omega2."""
    # X-axis Checks
    m_min = min(Mx_top, Mx_bot, key=abs)
    m_max = max(Mx_top, Mx_bot, key=abs)
    kappa = -m_min / m_max if abs(m_max) > 1e-12 else 0.0

    # Clause 13.8.5: the analysed members carry transverse distributed loads.
    w1 = 1.0
    intermediate_peak = Mx_max > abs(Mx_top) * 1.1 and Mx_max > abs(Mx_bot) * 1.1
    if intermediate_peak:
        w2 = 1.0
        w2_uncapped = 1.0
    else:
        w2_uncapped = 1.75 + 1.05 * kappa + 0.3 * kappa ** 2
        w2 = min(w2_uncapped, 2.5)

    return {
        'm_min': m_min,
        'm_max': m_max,
        'kappa': kappa,
        'omega1': w1,
        'omega1_reason': 'transverse distributed load between supports',
        'omega2': round(w2, 4),
        'omega2_uncapped': w2_uncapped,
        'intermediate_peak': intermediate_peak,
    }


def element_properties(Mx_max, Mx_top, Mx_bot):
    details = element_property_details(Mx_max, Mx_top, Mx_bot)

    return details['omega1'], details['omega2']

def section_properties(mb, mem, mat_prop):
    fy = mat_prop['fy']
    E = mat_prop['E']
    cl = mem['Class']
    Ix = mb['Ix']
    Iy = mb['Iy']
    Klx = mem['klx']
    Kly = mem['kly']
    Zx = mb['Zplx'] if cl < 3 else mb.get('Zex', mb.get('Zplx'))
    # member_database.csv uses 'Zey' (elastic minor-axis modulus), not 'Zpy'
    Zy = mb['Zply'] if cl < 3 else mb.get('Zey', mb.get('Zply', mb.get('Zex')))
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
    ltb = ltb_properties(mem, mb, mat_prop)
    Mrx_ltb = ltb['Mrx_ltb']

    sec_prop = {
        'Cr': Cr,
        'Crx': Crx,
        'Cry': Cry,
        'Cex': Cex,
        'Cey': Cey,
        'Mrx': Mrx,
        'Mry': Mry,
        'Tr': Cr,
        'Mrx_ltb': Mrx_ltb,
        'Mcr': ltb['Mcr'],
        'Mp': ltb['Mp'],
        'My': ltb['My'],
        'omega2': ltb['omega2'],
        'Zx': Zx,
        'A': mb['A'],
        'lamda_x': lamda_x,
        'lamda_y': lamda_y
    }

    return sec_prop

def ltb_properties(mem, mem_prop, mat_prop):
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

    return {
        'omega2': w2,
        'Mcr': Mcr,
        'Mp': Mp,
        'My': My,
        'Mi': Mi,
        'Mrx_ltb': Mr,
    }


def ltb_moment(mem, mem_prop, mat_prop):
    """Return the factored laterally unsupported moment resistance."""
    return ltb_properties(mem, mem_prop, mat_prop)['Mrx_ltb']

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
    Mrx = sec_props['Mrx_ltb']

    U1x = max(1, w1 / (1 - (Cu / Cex)))
    m_fac = 0.85 if cl < 3 else 1.0


    Check1 = (Cu / Cr) + m_fac * U1x * Mx / Mrx
    Check2 = Mx / Mrx

    return Check1, Check2


def tension_and_bending(mem, sec_props):
    """SANS 10162-1 clause 13.9 combined axial tension and bending."""
    Tu = abs(float(mem['Cu']))
    Mx = abs(float(mem['Mx_max']))
    Tr = sec_props['Tr']
    Mr_yield = sec_props['Mrx']
    Mr_ltb = sec_props['Mrx_ltb']
    area = sec_props['A']
    zx = sec_props['Zx']

    # Clause 13.9(a): tension is additive and can never reduce utilisation.
    cross_section = Tu / Tr + Mx / Mr_yield

    # Clause 13.9(b): tension relieves compressive bending stress. Preserve the
    # code check but do not report a negative utilisation. The additive check
    # above remains part of the governing envelope.
    ltb_stress = max(0.0, Mx / Mr_ltb - Tu * zx / (Mr_ltb * area))
    bending = Mx / Mr_ltb
    return cross_section, cross_section, (ltb_stress, bending)

def member_design(mb, mem, mat_prop):
    sec_props = section_properties(mb, mem, mat_prop)
    if float(mem['Cu']) < 0:
        return tension_and_bending(mem, sec_props)
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

