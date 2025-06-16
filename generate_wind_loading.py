import json
from typing import List, Dict, Any, Optional


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
                pos: float = 0.0) -> (int, float):
    """Distribute a load sequentially along ``members`` starting from (idx, pos).

    Returns the new ``(idx, pos)`` after ``length`` of load has been applied.
    """
    remaining = length

    while remaining > 0 and idx < len(members):
        m = members[idx]
        m_len = m["length"] - pos
        seg = min(m_len, remaining)

        if seg <= 0:
            idx += 1
            pos = 0.0
            continue

        start = pos if pos > 0 else None
        end = pos + seg if seg < m["length"] or start is not None else None
        _add_load(loads, m["name"], intensity, case, start, end)

        remaining -= seg
        pos += seg
        if pos >= m["length"]:
            idx += 1
            pos = 0.0

    return idx, pos


def _process_0deg(zones: List[Dict[str, Any]], left_cols: List[Dict[str, Any]],
                  rafters: List[Dict[str, Any]], right_cols: List[Dict[str, Any]],
                  case_02: str, case_03: str, loads: List[Dict[str, Any]]) -> None:
    zd = _zone_dict(zones)
    for key, case in [("cpi=0.2", case_02), ("cpi=-0.3", case_03)]:
        # Left columns - Zone D
        _distribute(zd["D"]["Length"], left_cols, zd["D"][key], case, loads)
        # Roof zones along slope
        r_seq = ["G", "H", "J", "I"]
        idx, pos = 0, 0.0
        for z in r_seq:
            # lay out zones sequentially along rafters
            idx, pos = _distribute(zd[z]["Length"], rafters, zd[z][key], case,
                                   loads, idx, pos)
        # Right columns - Zone E
        _distribute(zd["E"]["Length"], right_cols, zd["E"][key], case, loads)


def _process_90deg(zones: List[Dict[str, Any]], left_cols: List[Dict[str, Any]],
                   rafters: List[Dict[str, Any]], right_cols: List[Dict[str, Any]],
                   case_02: str, case_03: str, loads: List[Dict[str, Any]]) -> None:
    zd = _zone_dict(zones)
    roof_len = sum(m["length"] for m in rafters)
    for key, case in [("cpi=0.2", case_02), ("cpi=-0.3", case_03)]:
        _distribute(zd["A"]["Length"], left_cols, zd["A"][key], case, loads)
        _distribute(roof_len, rafters, zd["H"][key], case, loads)
        _distribute(zd["A"]["Length"], right_cols, zd["A"][key], case, loads)
 
def wind_loading(data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if data is None:
        data = json.load(open("input_data.json"))

    wd = data["wind_data"]

    if wd.get("building_type") != "Normal" or wd.get("building_roof") != "Duo Pitched":
        raise NotImplementedError("Only Normal Duo Pitched buildings are handled")

    nodes = _get_nodes(data)
    gable_width = data["frame_data"][0]["gable_width"]

    members = data["members"]
    left_cols = _sort_columns(members, nodes, 0)
    right_cols = _sort_columns(members, nodes, gable_width)
    rafters = _sort_rafters(members, nodes)

    loads: List[Dict[str, Any]] = []

    _process_0deg(data["wind_zones_0U"], left_cols, rafters, right_cols,"W0_0.2U", "W0_0.3U", loads)
    _process_0deg(data["wind_zones_0D"], left_cols, rafters, right_cols,"W0_0.2D", "W0_0.3D", loads)
    _process_90deg(data["wind_zones_90"], left_cols, rafters, right_cols,"W90_0.2", "W90_0.3", loads)

    return loads

if __name__ == "__main__":
    wind_loading()

