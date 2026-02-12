import math
from typing import List, Dict, Any, Optional, Tuple, Union
from frame_model import PortalFrame, load_portal_frame
from wind_loads import (
    calculate_basic_wind_speed,
    calculate_terrain_roughness,
    calculate_peak_wind_pressure,
)

# Zone F is kept for local sheeting/fixings checks only.
# Structural frame loading excludes zone F by default.
STRUCTURAL_ROOF_ZONES_0DEG = ("G", "H", "J", "I")

def _get_nodes(data: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    return {n["name"]: n for n in data["nodes"]}

def _sort_columns(members: List[Dict[str, Any]], nodes: Dict[str, Dict[str, float]], x_pos: float) -> List[Dict[str, Any]]:
    cols = [m for m in members if m["type"] == "column" and nodes[m["i_node"]]["x"] == x_pos]
    return sorted(cols, key=lambda m: nodes[m["i_node"]]["y"])

def _sort_rafters(members: List[Dict[str, Any]], nodes: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
    raf = [m for m in members if m["type"] == "rafter"]
    return sorted(raf, key=lambda m: nodes[m["i_node"]]["x"])

def _zone_dict(zones: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {z["Zone"]: z for z in zones}

def _add_load(loads: List[Dict[str, Any]], member: str, intensity: float, case: str,
              start: float = None, end: float = None) -> None:
    load = {
        "member": member,
        "direction": "Fy",
        "w1": intensity,
        "w2": intensity,
        "case": case
    }
    if start is not None:
        load["x1"] = round(start, 3)
    if end is not None:
        load["x2"] = round(end, 3)
    loads.append(load)

def _distribute(length: float, members: List[Dict[str, Any]], intensity: float,
                case: str, loads: List[Dict[str, Any]], idx: int = 0,
                pos: float = 0.0) -> Tuple[int, float]:
    """Distribute a load sequentially along ``members`` starting from ``(idx, pos)``.

    ``length`` and ``pos`` are given in **mm**. Member lengths are converted to
    mm before processing. The returned ``(idx, pos)`` is also in mm.
    """
    remaining = length

    while remaining > 0 and idx < len(members):
        m = members[idx]
        m_len = m["length"] * 1000 - pos  # convert member length to mm
        seg = min(m_len, remaining)

        if seg <= 0:
            idx += 1
            pos = 0.0
            continue

        start = pos if pos > 0 else None
        end = (pos + seg) if seg < m["length"] * 1000 or start is not None else None
        _add_load(loads, m["name"], intensity, case, start, end)

        remaining -= seg
        pos += seg
        if pos >= m["length"] * 1000:
            idx += 1
            pos = 0.0

    return idx, pos

def _process_0deg(zones: List[Dict[str, Any]], left_cols: List[Dict[str, Any]],
                  rafters: List[Dict[str, Any]], right_cols: List[Dict[str, Any]],
                  pitch: float, case_02: str, case_03: str,
                  loads: List[Dict[str, Any]], roof_type: str = "Duo Pitched") -> None:
    """Distribute 0° wind zones sequentially along the roof members.

    ``pitch`` is the rafter angle in radians used to convert horizontal zone
    lengths to lengths along the rafter slope.
    """
    zd = _zone_dict(zones)
    for key, case in [("cpi=0.2", case_02), ("cpi=-0.3", case_03)]:
        # Left columns - Zone D (lengths converted to mm)
        _distribute(zd["D"]["Length"] * 1000, left_cols, zd["D"][key], case, loads)
        # Roof zones along slope
        idx, pos = 0, 0.0
        for z in STRUCTURAL_ROOF_ZONES_0DEG:
            # lay out zones sequentially along rafters
            # convert horizontal zone length to mm of inclined rafter
            length = zd[z]["Length"] * 1000 / math.cos(pitch)
            idx, pos = _distribute(length, rafters, zd[z][key], case,
                                   loads, idx, pos)
        # Right columns - Zone E (lengths converted to mm)
        _distribute(zd["E"]["Length"] * 1000, right_cols, zd["E"][key], case, loads)


def _process_90deg(zones: List[Dict[str, Any]], left_cols: List[Dict[str, Any]],
                   rafters: List[Dict[str, Any]], right_cols: List[Dict[str, Any]],
                   case_02: str, case_03: str, loads: List[Dict[str, Any]]) -> None:
    zd = _zone_dict(zones)
    roof_len = sum(m["length"] for m in rafters) * 1000  # total rafter length in mm
    for key, case in [("cpi=0.2", case_02), ("cpi=-0.3", case_03)]:
        _distribute(zd["A"]["Length"] * 1000, left_cols, zd["A"][key], case, loads)
        _distribute(roof_len, rafters, zd["H"][key], case, loads)
        _distribute(zd["A"]["Length"] * 1000, right_cols, zd["A"][key], case, loads)


def _process_canopy_0deg(zones: List[Dict[str, Any]], rafters: List[Dict[str, Any]],
                         pitch: float, case_02: str, case_03: str,
                         loads: List[Dict[str, Any]], roof_type: str = "Duo Pitched") -> None:
    """Canopy 0° wind: apply roof actions only (no wall/column loading)."""
    zd = _zone_dict(zones)
    for key, case in [("cpi=0.2", case_02), ("cpi=-0.3", case_03)]:
        idx, pos = 0, 0.0
        for z in STRUCTURAL_ROOF_ZONES_0DEG:
            length = zd[z]["Length"] * 1000 / math.cos(pitch)
            idx, pos = _distribute(length, rafters, zd[z][key], case, loads, idx, pos)


def _process_canopy_90deg(zones: List[Dict[str, Any]], rafters: List[Dict[str, Any]],
                          case_02: str, case_03: str, loads: List[Dict[str, Any]]) -> None:
    """Canopy 90° wind: apply roof actions only (no wall/column loading)."""
    zd = _zone_dict(zones)
    roof_len = sum(m["length"] for m in rafters) * 1000
    for key, case in [("cpi=0.2", case_02), ("cpi=-0.3", case_03)]:
        _distribute(roof_len, rafters, zd["H"][key], case, loads)


def _interp(angle: float, angles: List[float], values: List[float]) -> float:
    if angle <= angles[0]:
        return values[0]
    if angle >= angles[-1]:
        return values[-1]
    for i in range(1, len(angles)):
        if angle <= angles[i]:
            a0, a1 = angles[i - 1], angles[i]
            v0, v1 = values[i - 1], values[i]
            t = (angle - a0) / (a1 - a0)
            return v0 + t * (v1 - v0)
    return values[-1]


def _cf_mono(pitch_deg: float, phi: float) -> Tuple[float, float]:
    # SANS 10160-3 Table 13 (mono-pitch canopy)
    angles = [0, 5, 10, 15, 20, 25, 30]
    cf_max = [0.2, 0.4, 0.5, 0.7, 0.8, 1.0, 1.2]
    cf_min_phi0 = [-0.5, -0.7, -0.9, -1.1, -1.3, -1.6, -1.8]
    cf_min_phi1 = [-1.3, -1.4, -1.4, -1.4, -1.4, -1.4, -1.4]

    cmax = _interp(pitch_deg, angles, cf_max)
    cmin0 = _interp(pitch_deg, angles, cf_min_phi0)
    cmin1 = _interp(pitch_deg, angles, cf_min_phi1)
    cmin = cmin0 + phi * (cmin1 - cmin0)
    return cmax, cmin


def _cf_duo(pitch_deg: float, phi: float) -> Tuple[float, float]:
    # SANS 10160-3 Table 14 (duo-pitch canopy)
    angles = [-20, -15, -10, -5, 5, 10, 15, 20, 25, 30]
    cf_max = [0.7, 0.5, 0.4, 0.3, 0.3, 0.4, 0.4, 0.6, 0.7, 0.9]
    cf_min_phi0 = [-0.7, -0.6, -0.6, -0.5, -0.6, -0.7, -0.8, -0.9, -1.0, -1.0]
    cf_min_phi1 = [-1.3, -1.4, -1.4, -1.3, -1.3, -1.3, -1.3, -1.3, -1.3, -1.3]

    # Table does not provide exactly 0 deg. Linear interpolation across -5/+5.
    cmax = _interp(pitch_deg, angles, cf_max)
    cmin0 = _interp(pitch_deg, angles, cf_min_phi0)
    cmin1 = _interp(pitch_deg, angles, cf_min_phi1)
    cmin = cmin0 + phi * (cmin1 - cmin0)
    return cmax, cmin


def _advance_position(members: List[Dict[str, Any]], distance_mm: float) -> Tuple[int, float]:
    idx, pos = 0, 0.0
    remaining = distance_mm
    while remaining > 0 and idx < len(members):
        m_len = members[idx]["length"] * 1000 - pos
        step = min(m_len, remaining)
        remaining -= step
        pos += step
        if pos >= members[idx]["length"] * 1000:
            idx += 1
            pos = 0.0
    return idx, pos


def _process_canopy_structural(wd: Dict[str, Any], rafters: List[Dict[str, Any]],
                               loads: List[Dict[str, Any]]) -> None:
    """Apply canopy structural loads using resultant-force coefficient cf."""
    phi = wd.get("blocking_factor", 0.0)
    try:
        phi = float(phi)
    except (TypeError, ValueError):
        phi = 0.0
    phi = max(0.0, min(1.0, phi))

    pitch = wd.get("roof_pitch", 0.0)
    roof_type = wd.get("building_roof", "Duo Pitched")

    if roof_type == "Mono Pitched":
        cf_max, cf_min = _cf_mono(pitch, phi)
    else:
        cf_max, cf_min = _cf_duo(pitch, phi)

    bs = calculate_basic_wind_speed(wd['fundamental_basic_wind_speed'], wd['return_period'])
    roughness = calculate_terrain_roughness(wd['apex_height'], wd['terrain_category'])
    qp = calculate_peak_wind_pressure(wd['topographic_factor'], bs, roughness, wd['altitude'])
    r_spacing = wd['rafter_spacing']

    # Convert pressure coefficient to line load intensity.
    w_down = round((qp * cf_max) * r_spacing / -1000, 5)
    w_up = round((qp * cf_min) * r_spacing / -1000, 5)

    roof_len = sum(m["length"] for m in rafters) * 1000

    # Mono-pitch: apply resultant at d/4 from windward edge by loading half-span.
    if roof_type == "Mono Pitched":
        # Windward from left -> first half loaded.
        _distribute(roof_len / 2, rafters, w_up, "W0_0.2U", loads)
        _distribute(roof_len / 2, rafters, w_up, "W0_0.3U", loads)
        _distribute(roof_len / 2, rafters, w_down, "W0_0.2D", loads)
        _distribute(roof_len / 2, rafters, w_down, "W0_0.3D", loads)

        # Windward from right -> second half loaded.
        i_mid, p_mid = _advance_position(rafters, roof_len / 2)
        _distribute(roof_len / 2, rafters, w_down, "W90_0.2", loads, i_mid, p_mid)
        _distribute(roof_len / 2, rafters, w_up, "W90_0.3", loads, i_mid, p_mid)
        return

    # Duo-pitch: one-pitch-loaded requirement.
    left_len = roof_len / 2
    i_mid, p_mid = _advance_position(rafters, left_len)

    # Wind from left: load left pitch only.
    _distribute(left_len, rafters, w_up, "W0_0.2U", loads)
    _distribute(left_len, rafters, w_up, "W0_0.3U", loads)
    _distribute(left_len, rafters, w_down, "W0_0.2D", loads)
    _distribute(left_len, rafters, w_down, "W0_0.3D", loads)

    # Wind from right: load right pitch only.
    _distribute(left_len, rafters, w_down, "W90_0.2", loads, i_mid, p_mid)
    _distribute(left_len, rafters, w_up, "W90_0.3", loads, i_mid, p_mid)
 
def wind_loading(data: Optional[Union[PortalFrame, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    if data is None:
        data = load_portal_frame("input_data.json")

    if isinstance(data, PortalFrame):
        nodes = {name: {"x": n.x, "y": n.y, "z": n.z} for name, n in data.nodes.items()}
        gable_width = data.frame_data[0]["gable_width"]
        members = [{
            "name": m.name,
            "i_node": m.i_node,
            "j_node": m.j_node,
            "type": m.type,
            "length": m.length,
        } for m in data.members]
        wind_data = data.wind_data[0]
        zones_0u = data.wind_zones_0U
        zones_0d = data.wind_zones_0D
        zones_90 = data.wind_zones_90
    else:
        nodes = _get_nodes(data)
        gable_width = data["frame_data"][0]["gable_width"]
        members = data["members"]
        wind_data = data["wind_data"][0]
        zones_0u = data["wind_zones_0U"]
        zones_0d = data["wind_zones_0D"]
        zones_90 = data["wind_zones_90"]

    wd = wind_data

    if wd.get("building_type") not in {"Normal", "Canopy"}:
        raise NotImplementedError("Only Normal and Canopy buildings are handled")

    # ``nodes`` and ``members`` derived above depending on input type
    left_cols = _sort_columns(members, nodes, 0)
    right_cols = _sort_columns(members, nodes, gable_width)
    rafters = _sort_rafters(members, nodes)

    # Rafter pitch for converting roof zone lengths to the inclined length
    dy = nodes[rafters[0]["j_node"]]["y"] - nodes[rafters[0]["i_node"]]["y"]
    dx = nodes[rafters[0]["j_node"]]["x"] - nodes[rafters[0]["i_node"]]["x"]
    pitch = math.atan2(dy, dx)

    loads: List[Dict[str, Any]] = []

    roof_type = wd.get("building_roof", "Duo Pitched")
    if wd.get("building_type") == "Canopy":
        _process_canopy_structural(wd, rafters, loads)
    else:
        _process_0deg(zones_0u, left_cols, rafters, right_cols, pitch, "W0_0.2U", "W0_0.3U", loads, roof_type)
        _process_0deg(zones_0d, left_cols, rafters, right_cols, pitch, "W0_0.2D", "W0_0.3D", loads, roof_type)
        _process_90deg(zones_90, left_cols, rafters, right_cols, "W90_0.2", "W90_0.3", loads)

    return loads

if __name__ == "__main__":
    print(wind_loading())
