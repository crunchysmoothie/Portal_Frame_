"""Crawl-beam actions and placement on portal-frame rafters.

The crawl beam is assumed to run longitudinally across every portal bay.  For
the transverse portal analysis no continuity or reaction-distribution
reduction is taken: each portal attachment receives the full characteristic
vertical crane action and one full bay of crawl-beam self-weight.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Tuple

import member_database as mdb


GRAVITY = 9.80665  # m/s2
PHI_1 = 1.1
DEFAULT_HORIZONTAL_RATIO = 0.05
_PHI_2 = {
    "C1": (1.05, 0.17),
    "C2": (1.10, 0.34),
    "C3": (1.15, 0.51),
    "C4": (1.20, 0.68),
}


def hoist_dynamic_factor(hoist_class: str, hoisting_speed_m_s: float) -> float:
    """Return SANS 10160-6 vertical hoist dynamic factor ``phi_2``."""
    crane_class = str(hoist_class).upper()
    if crane_class not in _PHI_2:
        raise ValueError(f"Unknown hoist class {hoist_class!r}; choose C1, C2, C3 or C4.")
    speed = float(hoisting_speed_m_s)
    if speed < 0:
        raise ValueError("Hoisting speed cannot be negative.")
    phi_min, beta = _PHI_2[crane_class]
    return phi_min + beta * speed


def _member_length_mm(member: Dict, nodes: Dict[str, Dict]) -> float:
    i_node = nodes[member["i_node"]]
    j_node = nodes[member["j_node"]]
    return math.hypot(j_node["x"] - i_node["x"], j_node["y"] - i_node["y"])


def _slope_members(data: Dict, slope: str) -> Tuple[List[Dict], bool]:
    nodes = {node["name"]: node for node in data["nodes"]}
    rafters = [member for member in data["members"] if member["type"].lower() == "rafter"]
    if not rafters:
        raise ValueError("The frame contains no rafter members.")

    roof_type = data["frame_data"][0].get("building_roof", "Duo Pitched")
    side = str(slope).strip().lower()
    if roof_type == "Mono Pitched":
        if side not in {"left", "single"}:
            raise ValueError("A mono-pitched frame accepts slope='left' or slope='single'.")
        return sorted(
            rafters,
            key=lambda member: min(nodes[member["i_node"]]["x"], nodes[member["j_node"]]["x"]),
        ), True

    if side not in {"left", "right"}:
        raise ValueError("A duo-pitched frame requires slope='left' or slope='right'.")

    apex_x = nodes[max(nodes, key=lambda name: nodes[name]["y"])]["x"]
    if side == "left":
        selected = [
            member for member in rafters
            if max(nodes[member["i_node"]]["x"], nodes[member["j_node"]]["x"]) <= apex_x + 1e-6
        ]
        selected.sort(
            key=lambda member: min(nodes[member["i_node"]]["x"], nodes[member["j_node"]]["x"])
        )
        return selected, True

    selected = [
        member for member in rafters
        if min(nodes[member["i_node"]]["x"], nodes[member["j_node"]]["x"]) >= apex_x - 1e-6
    ]
    selected.sort(
        key=lambda member: max(nodes[member["i_node"]]["x"], nodes[member["j_node"]]["x"]),
        reverse=True,
    )
    return selected, False


def locate_rafter_point(data: Dict, slope: str, position_from_eaves_mm: float) -> Tuple[str, float]:
    """Return ``(member name, local x in mm)`` for a slope distance from eaves."""
    distance = float(position_from_eaves_mm)
    if distance < 0:
        raise ValueError("Crawl position from eaves cannot be negative.")

    nodes = {node["name"]: node for node in data["nodes"]}
    members, increasing_x = _slope_members(data, slope)
    remaining = distance

    for member in members:
        length = _member_length_mm(member, nodes)
        if remaining <= length + 1e-6:
            i_x = nodes[member["i_node"]]["x"]
            j_x = nodes[member["j_node"]]["x"]
            travel_starts_at_i = i_x <= j_x if increasing_x else i_x >= j_x
            local_x = remaining if travel_starts_at_i else length - remaining
            return member["name"], min(max(local_x, 0.0), length)
        remaining -= length

    available = sum(_member_length_mm(member, nodes) for member in members)
    raise ValueError(
        f"Crawl position {distance:.1f} mm exceeds the {slope} slope length "
        f"of {available:.1f} mm."
    )


def _mass_to_kn(mass_kg: float) -> float:
    mass = float(mass_kg)
    if mass < 0:
        raise ValueError("Crawl and hoist masses cannot be negative.")
    return mass * GRAVITY / 1000


def _nominal_crane_components(crawl: Dict) -> Tuple[float, float]:
    """Return nominal crane self-weight and hoist load in kN."""
    required = ("swl_kg", "hoist_trolley_mass_kg")
    missing = [key for key in required if key not in crawl]
    if missing:
        raise ValueError(
            "Nominal crane components require " + ", ".join(missing) + "."
        )
    crane_self_weight = _mass_to_kn(crawl["hoist_trolley_mass_kg"])
    hoist_load = _mass_to_kn(
        float(crawl["swl_kg"]) + float(crawl.get("lifting_attachment_mass_kg", 0.0))
    )
    return crane_self_weight, hoist_load


def characteristic_vertical_crane_load(crawl: Dict) -> float:
    """Return the unreduced characteristic vertical crane action in kN."""
    supplier_load = crawl.get(
        "manufacturer_characteristic_vertical_load_kn",
        crawl.get("manufacturer_vertical_load_kn"),
    )
    if supplier_load is not None:
        load = float(supplier_load)
        if load <= 0:
            raise ValueError("The manufacturer characteristic vertical load must be positive.")
        return load

    required = ("swl_kg", "hoist_trolley_mass_kg", "hoist_class", "hoisting_speed_m_s")
    missing = [key for key in required if key not in crawl]
    if missing:
        raise ValueError(
            "A crawl without a manufacturer reaction requires " + ", ".join(missing) + "."
        )

    phi_2 = hoist_dynamic_factor(crawl["hoist_class"], crawl["hoisting_speed_m_s"])
    crane_self_weight, hoist_load = _nominal_crane_components(crawl)
    return PHI_1 * crane_self_weight + phi_2 * hoist_load


def static_vertical_crane_load(crawl: Dict) -> float:
    """Return the nominal vertical action before dynamic amplification."""
    supplier_static = crawl.get("manufacturer_static_vertical_load_kn")
    if supplier_static is not None:
        load = float(supplier_static)
        if load <= 0:
            raise ValueError("manufacturer_static_vertical_load_kn must be positive.")
        return load
    try:
        crane_self_weight, hoist_load = _nominal_crane_components(crawl)
        return crane_self_weight + hoist_load
    except ValueError:
        # If a supplier gives only the dynamic characteristic reaction, using
        # it for the 5% rule is conservative because SANS 10160-6 clause 5.5.2
        # normally excludes dynamic amplification from the horizontal action.
        return characteristic_vertical_crane_load(crawl)


def horizontal_crane_load(crawl: Dict) -> float:
    """Return the characteristic portal-plane horizontal action in kN.

    An explicit supplier/user value governs. Otherwise SANS 10160-6 clause
    5.5.2's 5% monorail value is used, without dynamic amplification when the
    nominal crane components are available.
    """
    vertical = characteristic_vertical_crane_load(crawl)
    explicit_horizontal = crawl.get("horizontal_load_kn")
    explicit_diagonal = crawl.get("diagonal_resultant_load_kn")

    if explicit_horizontal is not None:
        horizontal = float(explicit_horizontal)
        if horizontal < 0:
            raise ValueError("horizontal_load_kn cannot be negative.")
        if explicit_diagonal is not None and not math.isclose(
            math.hypot(vertical, horizontal),
            float(explicit_diagonal),
            rel_tol=1e-6,
            abs_tol=1e-6,
        ):
            raise ValueError(
                "horizontal_load_kn and diagonal_resultant_load_kn are inconsistent."
            )
        return horizontal

    if explicit_diagonal is not None:
        diagonal = float(explicit_diagonal)
        if diagonal < vertical:
            raise ValueError(
                "diagonal_resultant_load_kn cannot be smaller than the vertical crane action."
            )
        return math.sqrt(max(diagonal**2 - vertical**2, 0.0))

    ratio = float(crawl.get("horizontal_load_ratio", DEFAULT_HORIZONTAL_RATIO))
    if ratio < 0:
        raise ValueError("horizontal_load_ratio cannot be negative.")
    return ratio * static_vertical_crane_load(crawl)


def diagonal_crane_resultant(crawl: Dict) -> Tuple[float, float]:
    """Return diagonal resultant magnitude and angle from vertical in degrees."""
    vertical = characteristic_vertical_crane_load(crawl)
    horizontal = horizontal_crane_load(crawl)
    return math.hypot(vertical, horizontal), math.degrees(math.atan2(horizontal, vertical))


def crane_combination_factor(crawl: Dict) -> float:
    """Return ``psi_crane`` from SANS 10160-6 equation 20."""
    explicit = crawl.get("crane_combination_factor")
    if explicit is not None:
        factor = float(explicit)
        if not 0 <= factor <= 1:
            raise ValueError("crane_combination_factor must be between 0 and 1.")
        return factor
    try:
        crane_self_weight, hoist_load = _nominal_crane_components(crawl)
    except ValueError:
        # A supplier reaction without its Qc/Qhl split cannot reproduce
        # equation 20. Taking psi=1 is the conservative fallback.
        return 1.0
    total = crane_self_weight + hoist_load
    return crane_self_weight / total if total else 1.0


def governing_crane_combination_factor(crawls: List[Dict]) -> float:
    """Return a conservative common factor for a combined crawl load case."""
    return max((crane_combination_factor(crawl) for crawl in crawls), default=1.0)


def crawl_case_names(crawl: Dict) -> Dict[str, str]:
    """Return stable, unique load-case names derived from a crawl name."""
    name = str(crawl.get("name", "")).strip()
    if not name:
        raise ValueError("Every crawl in the crawl library requires a name.")
    token = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    if not token:
        raise ValueError(f"Crawl name {name!r} cannot form a load-case name.")
    return {
        "vertical": f"CR_{token}",
        "horizontal_positive": f"CRH_{token}_POS",
        "horizontal_negative": f"CRH_{token}_NEG",
    }


def generate_crawl_member_point_loads(
    data: Dict,
    member_db: Dict | None = None,
) -> List[Dict]:
    """Generate permanent and crane point loads for every configured crawl."""
    crawls = data.get("crawl_beams", [])
    enabled = str(data.get("use_crawl_beams", "Yes")).strip().lower() == "yes"
    if not enabled or not crawls:
        return []

    database = member_db if member_db is not None else mdb.load_member_database()
    bay_length_m = float(data["frame_data"][0]["rafter_spacing"]) / 1000
    loads: List[Dict] = []

    for crawl in crawls:
        name = crawl.get("name", "crawl")
        member, x = locate_rafter_point(
            data,
            crawl["slope"],
            crawl["position_from_eaves_mm"],
        )
        section_type = crawl.get("section_type", "I-Sections")
        section = crawl["section"]
        try:
            mass_kg_m = float(database[section_type][section]["m"])
        except KeyError as exc:
            raise KeyError(
                f"Unknown crawl-beam section {section!r} in {section_type!r}."
            ) from exc

        # Conservative user assumption: one complete bay of beam self-weight
        # and the full crane action are transferred at every portal support.
        permanent_kn = _mass_to_kn(mass_kg_m * bay_length_m)
        crane_kn = characteristic_vertical_crane_load(crawl)
        horizontal_kn = horizontal_crane_load(crawl)
        cases = crawl_case_names(crawl)
        common = {"member": member, "direction": "FY", "x": round(x, 6), "source": name}
        loads.append({**common, "magnitude": -permanent_kn, "case": "D_CRAWL"})
        loads.append({**common, "magnitude": -crane_kn, "case": cases["vertical"]})
        horizontal_common = {**common, "direction": "FX"}
        loads.append({
            **horizontal_common,
            "magnitude": horizontal_kn,
            "case": cases["horizontal_positive"],
        })
        loads.append({
            **horizontal_common,
            "magnitude": -horizontal_kn,
            "case": cases["horizontal_negative"],
        })

    return loads
