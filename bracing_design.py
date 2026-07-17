"""Gable-column and longitudinal bracing design.

The module keeps the end-wall load path separate from the transverse portal
frame.  Wind normal to a gable is taken from the existing W90 wall zones,
distributed to gable columns by tributary width, and transferred as column top
shears into a triangulated roof-bracing layout.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from Pynite import FEModel3D

from strength_checks import member_class_check, member_design, section_properties


PHI = 0.9
BUCKLING_EXPONENT = 1.34
TENSION_SLENDERNESS_LIMIT = 300.0
COMPRESSION_SLENDERNESS_LIMIT = 200.0
MIN_ANGLE_LEG_MM = 50.0
MIN_ANGLE_THICKNESS_MM = 5.0
COLUMN_BRACING_TYPES = {"X", "K", "A"}


@dataclass(frozen=True)
class GableColumnResult:
    name: str
    roof_node: str
    x_mm: float
    height_mm: float
    tributary_width_mm: float
    brace_intervals: int
    unbraced_length_mm: float
    section_type: str
    section: str
    characteristic_pressure_kpa: float
    factored_line_load_kn_m: float
    top_shear_kn: float
    major_moment_knm: float
    mcr_knm: float
    bending_resistance_knm: float
    section_class: int
    omega2: float
    iy_cm4: float
    torsional_constant_cm4: float
    warping_constant: float
    plastic_moment_knm: float
    yield_moment_knm: float
    utilisation: float


@dataclass(frozen=True)
class BracingMemberResult:
    member_type: str
    section_family: str
    section: str
    design_force_kn: float
    length_mm: float
    area_mm2: float
    fy_mpa: float
    resistance_kn: float
    resistance_utilisation: float
    radius_of_gyration_mm: float
    effective_length_factor: float
    slenderness_axis: str
    rx_mm: float
    ry_mm: float
    rv_mm: float
    slenderness_xx: float
    slenderness_yy: float
    slenderness_vv: float
    slenderness_ratio: float
    nondimensional_slenderness: float
    slenderness_limit: float
    slenderness_utilisation: float
    utilisation: float
    behaviour: str


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_bracing_database(
    filename: str | Path = "bracing_member_database.csv",
) -> dict[str, list[dict[str, Any]]]:
    """Load the normalized workbook tables, sorted by mass."""

    families: dict[str, list[dict[str, Any]]] = {}
    with Path(filename).open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            converted: dict[str, Any] = {}
            for key, value in row.items():
                if key in {"section_type", "Designation"}:
                    converted[key] = value
                elif value in (None, ""):
                    converted[key] = None
                else:
                    converted[key] = _float(value)
            families.setdefault(row["section_type"], []).append(converted)
    for rows in families.values():
        rows.sort(key=lambda item: _float(item.get("m"), math.inf))
    return families


def _roof_candidates(data) -> list[dict[str, Any]]:
    frame = data.frame_data[0]
    width = _float(frame["gable_width"])
    candidates = [
        {"name": name, "x": _float(node.x), "y": _float(node.y)}
        for name, node in data.nodes.items()
        if 1e-6 < _float(node.x) < width - 1e-6 and _float(node.y) > 0
    ]
    return sorted(candidates, key=lambda item: item["x"])


def select_gable_nodes(data, count: int) -> list[dict[str, Any]]:
    """Select the apex and successive symmetric braced-node pairs."""

    if count < 1 or count % 2 == 0:
        raise ValueError("gable_column_count must be a positive odd number (1, 3, 5, ...).")
    candidates = _roof_candidates(data)
    if count > len(candidates):
        raise ValueError(
            f"gable_column_count={count} exceeds the {len(candidates)} internal roof "
            "brace points. Increase rafter_bracing_spacing or reduce the count."
        )
    centre = _float(data.frame_data[0]["gable_width"]) / 2
    apex = min(candidates, key=lambda item: abs(item["x"] - centre))
    if abs(apex["x"] - centre) > 1e-6:
        raise ValueError("The generated roof geometry does not contain an apex brace node.")
    selected = [apex]
    by_x = {round(item["x"], 6): item for item in candidates}
    offsets = sorted(
        {round(abs(item["x"] - centre), 6) for item in candidates if item is not apex}
    )
    for offset in offsets:
        if len(selected) >= count:
            break
        left = by_x.get(round(centre - offset, 6))
        right = by_x.get(round(centre + offset, 6))
        if left and right:
            selected.extend((left, right))
    if len(selected) != count:
        raise ValueError("The available roof brace nodes cannot form the requested symmetric layout.")
    return sorted(selected, key=lambda item: item["x"])


def tributary_widths(x_positions: Iterable[float], width_mm: float) -> dict[float, float]:
    positions = sorted(float(x) for x in x_positions)
    bounds = [0.0]
    bounds.extend((a + b) / 2 for a, b in zip(positions, positions[1:]))
    bounds.append(float(width_mm))
    return {x: bounds[index + 1] - bounds[index] for index, x in enumerate(positions)}


def gable_wall_pressure_cases(data) -> list[dict[str, float | str]]:
    """Return D/E gable-wall pressures for both internal-pressure cases."""

    zones = {item["Zone"]: item for item in data.wind_zones_90}
    if "D" not in zones or "E" not in zones:
        raise ValueError("W90 wall zones D and E are required for gable design.")
    spacing_m = _float(data.frame_data[0]["rafter_spacing"]) / 1000
    if spacing_m <= 0:
        raise ValueError("rafter_spacing must be positive.")
    cases = []
    internal = (data.wind_data[0].get("internal_pressure", {})
                if data.wind_data else {})
    direction = internal.get("directions", {}).get("90", {})
    cpi_by_key = {
        "cpi=0.2": _float(direction.get("maximum_cpi"), 0.2),
        "cpi=-0.3": _float(direction.get("minimum_cpi"), -0.3),
    }
    final_wind = internal.get("mode") == "Final design"
    names = ("W90_CPI_MAX", "W90_CPI_MIN") if final_wind else ("W90_0.2", "W90_0.3")
    for key, name in (("cpi=0.2", names[0]), ("cpi=-0.3", names[1])):
        for zone in ("D", "E"):
            # Stored wind-zone values are kN/mm line loads for one portal bay.
            # Multiplying by 1000 gives kN/m; divide by bay width for kN/m2.
            pressure = abs(_float(zones[zone][key]) * 1000 / spacing_m)
            cases.append({
                "case": name, "zone": zone, "cpi": cpi_by_key[key],
                "pressure_kpa": pressure,
            })
    return cases


def _wind_uls_factor(data) -> float:
    factors = []
    for combo in data.load_combinations:
        for case, factor in combo.get("factors", {}).items():
            if case.startswith("W90_"):
                factors.append(_float(factor))
    if not factors:
        raise ValueError("No ULS factor was found for the W90 load cases.")
    return max(factors)


def _ordered_gable_sections(member_db: Mapping[str, Mapping[str, Mapping[str, Any]]]):
    sections = []
    for family in ("I-Sections", "H-Sections"):
        for name, props in member_db.get(family, {}).items():
            sections.append((family, name, props))
    return sorted(
        sections,
        key=lambda item: (
            str(item[2].get("Preferred", "No")).strip().lower() != "yes",
            _float(item[2].get("m"), math.inf),
        ),
    )


def _column_check(props, height_mm, brace_intervals, moment_knm, material):
    actions = {
        "Name": "GABLE",
        "kly": height_mm / brace_intervals / 1000,
        "klx": height_mm / 1000,
        "kx": 1.0,
        "lx": height_mm / 1000,
        "ky": 1.0,
        "ly": height_mm / brace_intervals / 1000,
        "type": "gable_column",
        "section": props["Designation"],
        "Cu": 0.0,
        "Class": member_class_check(0.0, props, material),
        "Mx_max": moment_knm,
        "Mx_top": 0.0,
        "Mx_bot": 0.0,
        "w1": 1.0,
        "w2": 1.0,
    }
    css, oms, ltb = member_design(props, actions, material)
    sec = section_properties(props, actions, material)
    ratios = (css, oms, ltb[0], ltb[1])
    return max(float(value) for value in ratios), sec


def _select_gable_section(member_db, demands, brace_intervals, material):
    for family, name, props in _ordered_gable_sections(member_db):
        checks = [
            _column_check(props, item["height_mm"], brace_intervals, item["moment_knm"], material)
            for item in demands
        ]
        if all(math.isfinite(ratio) and ratio <= 1 for ratio, _ in checks):
            return family, name, props
    raise ValueError("No I/H section passes the gable-column Mcr design envelope.")


def _angle_slenderness(section, length_mm):
    """Return angle slenderness about x-x, y-y and v-v (Kv = 0.5)."""

    rx = _float(section.get("rx"))
    ry = _float(section.get("ry")) or rx  # Equal-angle tables omit duplicate ry.
    rv = _float(section.get("rv"))
    if min(rx, ry, rv) <= 0:
        return None
    checks = {
        "x-x": {"k": 1.0, "radius": rx, "ratio": length_mm / rx},
        "y-y": {"k": 1.0, "radius": ry, "ratio": length_mm / ry},
        "v-v": {"k": 0.5, "radius": rv, "ratio": 0.5 * length_mm / rv},
    }
    axis = max(checks, key=lambda name: checks[name]["ratio"])
    return {
        "axis": axis,
        "governing": checks[axis],
        "checks": checks,
        "rx": rx,
        "ry": ry,
        "rv": rv,
    }


def _angle_meets_minimum_size(section):
    """Apply the practical bolted-brace minimum of 50 x 50 x 5."""

    return (
        _float(section.get("h")) >= MIN_ANGLE_LEG_MM
        and _float(section.get("b")) >= MIN_ANGLE_LEG_MM
        and _float(section.get("t")) >= MIN_ANGLE_THICKNESS_MM
    )


def _select_angle(database, force_kn, length_mm, fy):
    choices = database.get("Equal Angles", []) + database.get("Unequal Angles", [])
    choices.sort(key=lambda item: _float(item.get("m"), math.inf))
    for section in choices:
        if not _angle_meets_minimum_size(section):
            continue
        slenderness = _angle_slenderness(section, length_mm)
        if slenderness is None:
            continue
        resistance = PHI * _float(section.get("A")) * 1000 * fy / 1000
        if (
            resistance >= force_kn
            and all(
                check["ratio"] <= TENSION_SLENDERNESS_LIMIT
                for check in slenderness["checks"].values()
            )
        ):
            return section, resistance, slenderness
    raise ValueError(
        "No angle in the supplied database passes the roof X-brace tension, "
        "KL/r <= 300 about x-x and y-y with K=1.0 and about v-v with K=0.5, "
        "and minimum 50x50x5 checks."
    )


def _select_chs(database, force_kn, length_mm, material):
    fy = _float(material["fy"])
    e = _float(material["E"]) * 1000
    for section in database.get("CHS", []):
        area = _float(section.get("A")) * 1000
        radius = _float(section.get("rx"))
        if area <= 0 or radius <= 0:
            continue
        slenderness_ratio = length_mm / radius
        slenderness = slenderness_ratio * math.sqrt(fy / (math.pi ** 2 * e))
        compression = PHI * area * fy * (
            1 + slenderness ** (2 * BUCKLING_EXPONENT)
        ) ** (-1 / BUCKLING_EXPONENT) / 1000
        tension = PHI * area * fy / 1000
        resistance = min(compression, tension)
        if resistance >= force_kn and slenderness_ratio <= COMPRESSION_SLENDERNESS_LIMIT:
            return section, resistance, radius, slenderness_ratio
    raise ValueError(
        "No CHS in the supplied database passes the longitudinal brace resistance "
        "and KL/r <= 200 checks."
    )


def _column_brace_geometry(bracing_type, bay_mm, height_mm, panel_count=1):
    """Return one brace-member geometry for the selected side-wall topology."""

    bracing_type = str(bracing_type).strip().upper()
    panel_count = int(panel_count)
    if bracing_type not in COLUMN_BRACING_TYPES:
        raise ValueError("column_bracing_type must be X, K, or A.")
    if panel_count < 1:
        raise ValueError("col_bracing_spacing must be at least 1.")
    panel_height = height_mm / panel_count
    if bracing_type == "X":
        horizontal = bay_mm
        vertical = panel_height
    elif bracing_type == "K":
        horizontal = bay_mm
        vertical = panel_height / 2
    else:  # A: diagonals rise from the column bases to the bay centre.
        horizontal = bay_mm / 2
        vertical = panel_height
    return {
        "type": bracing_type,
        "bay_width_mm": float(bay_mm),
        "height_mm": float(height_mm),
        "panel_count": panel_count,
        "panel_height_mm": float(panel_height),
        "horizontal_projection_mm": float(horizontal),
        "member_length_mm": float(math.hypot(horizontal, vertical)),
        "members_per_panel": 2,
        "members_per_wall": 2 * panel_count,
    }


def _roof_brace_panels(roof_points, roof_type, purlin_interval=1):
    """Locate continuous X-brace panels at the selected purlin interval."""

    if len(roof_points) < 3:
        raise ValueError("Roof X-bracing requires eave and rafter-midspan nodes.")

    interval = int(purlin_interval)
    if interval < 1:
        raise ValueError("roof_bracing_purlin_interval must be at least 1.")

    def panels_between(start_index, end_index):
        return [
            (start, min(start + interval, end_index))
            for start in range(start_index, end_index, interval)
        ]

    if str(roof_type) == "Duo Pitched":
        centre_x = (roof_points[0]["x_mm"] + roof_points[-1]["x_mm"]) / 2
        apex_index = min(
            range(1, len(roof_points) - 1),
            key=lambda item: abs(roof_points[item]["x_mm"] - centre_x),
        )
        return panels_between(0, apex_index) + panels_between(
            apex_index, len(roof_points) - 1
        )

    return panels_between(0, len(roof_points) - 1)


def _roof_purlin_points(frame):
    """Return roof-plan connection rows without splitting the portal model."""

    span = _float(frame["gable_width"])
    eaves = _float(frame["eaves_height"])
    apex = _float(frame["apex_height"])
    maximum = _float(frame.get("purlin_max_spacing_mm"))
    roof_type = str(frame.get("building_roof"))
    if maximum <= 0:
        return []

    run = span / 2 if roof_type == "Duo Pitched" else span
    rise = apex - eaves
    divisions = max(1, math.ceil(math.hypot(run, rise) / maximum))
    coordinates = [
        (run * index / divisions, eaves + rise * index / divisions)
        for index in range(divisions + 1)
    ]
    if roof_type == "Duo Pitched":
        coordinates.extend(
            (span - run * index / divisions, eaves + rise * index / divisions)
            for index in range(divisions - 1, -1, -1)
        )
    return [
        {"name": f"P{index}", "x_mm": x, "y_mm": y}
        for index, (x, y) in enumerate(coordinates, 1)
    ]


def _analyse_gable_columns_pynite(columns, selections, material):
    """Solve the pinned gable columns and return PyNite action envelopes."""

    model = FEModel3D()
    model.add_material("STEEL", material["E"] * 1000, material["G"] * 1000, 0.3, 0)
    added_sections = set()
    for _, _, props in selections:
        if props["Designation"] in added_sections:
            continue
        model.add_section(
            props["Designation"], props["A"] * 1000, props["Iy"] * 1e6,
            props["Ix"] * 1e6, props["J"] * 1000,
        )
        added_sections.add(props["Designation"])
    for index, (column, selection) in enumerate(zip(columns, selections), 1):
        props = selection[2]
        bottom, top = f"GB{index}", f"GT{index}"
        model.add_node(bottom, column["x_mm"], 0, 0)
        model.add_node(top, column["x_mm"], column["height_mm"], 0)
        # Pinned in the loaded XY plane; out-of-plane and torsional DOFs are
        # restrained because those effects are covered by the Mcr check.
        model.def_support(bottom, True, True, True, True, True, False)
        model.def_support(top, True, True, True, True, True, False)
        member = f"GC{index}"
        model.add_member(member, bottom, top, "STEEL", props["Designation"])
        model.add_member_dist_load(
            member, "FX", column["line_load_kn_mm"],
            column["line_load_kn_mm"], case="GABLE_ULS",
        )
    model.add_load_combo("GABLE_ULS", {"GABLE_ULS": 1.0})
    model.analyze_linear(check_statics=False)
    actions = []
    for index, column in enumerate(columns, 1):
        member = model.members[f"GC{index}"]
        moment = max(
            abs(member.max_moment("Mz", "GABLE_ULS")),
            abs(member.min_moment("Mz", "GABLE_ULS")),
        ) / 1000
        shear = abs(model.nodes[f"GB{index}"].RxnFX["GABLE_ULS"])
        actions.append({"moment_knm": moment, "top_shear_kn": shear})
    return model, actions


def _analyse_roof_bracing_pynite(
    roof_points, brace_panels, loaded_shears, bay_mm, angle, purlin, material
):
    """Build and solve the first roof-bracing bay with tension-only X members.

    The purlin section supplies stiffness only in this stage; its compression
    resistance is deliberately not accepted or rejected here.
    """

    model = FEModel3D()
    model.add_material("STEEL", material["E"] * 1000, material["G"] * 1000, 0.3, 0)
    angle_iy = _float(angle.get("Iv") or angle.get("Iy") or angle.get("Ix"))
    angle_iz = _float(angle.get("Iu") or angle.get("Ix"))
    model.add_section(
        "ANGLE", _float(angle["A"]) * 1000, angle_iy * 1e6,
        angle_iz * 1e6, _float(angle["J"]) * 1000,
    )
    model.add_section(
        "PURLIN", _float(purlin["A"]) * 1000, _float(purlin["Iy"]) * 1e6,
        _float(purlin["Ix"]) * 1e6, _float(purlin["J"]) * 1000,
    )
    for row, z in ((0, 0.0), (1, bay_mm)):
        for index, point in enumerate(roof_points):
            name = f"R{row}_{index}"
            model.add_node(name, point["x_mm"], point["y_mm"], z)
            if row == 1:
                model.def_support(name, True, True, True, True, True, True)
            else:
                model.def_support(name, False, False, False, True, True, True)
    for index in range(len(roof_points)):
        model.add_member(f"S{index}", f"R0_{index}", f"R1_{index}", "STEEL", "PURLIN")
    for panel_index, (start_index, end_index) in enumerate(brace_panels):
        model.add_member(
            f"XB{panel_index}A", f"R0_{start_index}", f"R1_{end_index}",
            "STEEL", "ANGLE", tension_only=True,
        )
        model.add_member(
            f"XB{panel_index}B", f"R0_{end_index}", f"R1_{start_index}",
            "STEEL", "ANGLE", tension_only=True,
        )
    point_index = {point["name"]: index for index, point in enumerate(roof_points)}
    for node_name, shear in loaded_shears.items():
        model.add_node_load(f"R0_{point_index[node_name]}", "FZ", shear, "GABLE_ULS")
    model.add_load_combo("GABLE_ULS", {"GABLE_ULS": 1.0})
    model.analyze(check_stability=False, check_statics=False)
    max_dz = max(abs(_float(node.DZ.get("GABLE_ULS", 0))) for node in model.nodes.values())
    return model, {
        "node_count": len(model.nodes),
        "member_count": len(model.members),
        "x_brace_count": 2 * len(brace_panels),
        "tension_only_x_braces": True,
        "analysis": "PyNite nonlinear tension-only",
        "stiffness_purlin_section": purlin["Designation"],
        "purlin_resistance_check": "deferred",
        "max_longitudinal_displacement_mm": float(max_dz),
    }


def design_bracing_system(data, member_db, database_path="bracing_member_database.csv"):
    """Design gable columns, roof X-braces, and longitudinal CHS braces."""

    frame = data.frame_data[0]
    # Canopies have no enclosed gable wall and therefore no gable columns or
    # associated end-wall bracing load path. Keep this guard inside the design
    # function so callers cannot accidentally generate them.
    if frame.get("building_type") == "Canopy":
        return {}
    count = int(frame.get("gable_column_count", 1))
    column_bracing_type = str(frame.get("column_bracing_type", "X")).strip().upper()
    if column_bracing_type not in COLUMN_BRACING_TYPES:
        raise ValueError("column_bracing_type must be X, K, or A.")
    brace_intervals = int(frame.get("gable_column_brace_intervals", 1))
    if brace_intervals < 1:
        raise ValueError("gable_column_brace_intervals must be at least 1.")
    nodes = select_gable_nodes(data, count)
    widths = tributary_widths((item["x"] for item in nodes), frame["gable_width"])
    pressure_cases = gable_wall_pressure_cases(data)
    pressure = max(_float(item["pressure_kpa"]) for item in pressure_cases)
    wind_factor = _wind_uls_factor(data)
    demands = []
    for item in nodes:
        tributary_m = widths[item["x"]] / 1000
        line_load_kn_m = pressure * tributary_m * wind_factor
        height_m = item["y"] / 1000
        demands.append({
            "roof_node": item["name"], "x_mm": item["x"], "height_mm": item["y"],
            "tributary_width_mm": widths[item["x"]],
            "line_load_kn_m": line_load_kn_m,
            "line_load_kn_mm": line_load_kn_m / 1000,
            "moment_knm": line_load_kn_m * height_m ** 2 / 8,
            "top_shear_kn": line_load_kn_m * height_m / 2,
        })
    material = data.steel_grade[0]
    selections = [
        _select_gable_section(member_db, [demand], brace_intervals, material)
        for demand in demands
    ]
    _, fe_actions = _analyse_gable_columns_pynite(demands, selections, material)
    columns = []
    for index, (demand, fe_action, selection) in enumerate(
        zip(demands, fe_actions, selections), 1
    ):
        family, section_name, props = selection
        ratio, sec = _column_check(
            props, demand["height_mm"], brace_intervals, fe_action["moment_knm"], material
        )
        columns.append(GableColumnResult(
            name=f"GC{index}", roof_node=demand["roof_node"], x_mm=demand["x_mm"],
            height_mm=demand["height_mm"], tributary_width_mm=demand["tributary_width_mm"],
            brace_intervals=brace_intervals,
            unbraced_length_mm=demand["height_mm"] / brace_intervals,
            section_type=family, section=section_name,
            characteristic_pressure_kpa=pressure,
            factored_line_load_kn_m=demand["line_load_kn_m"],
            top_shear_kn=float(fe_action["top_shear_kn"]),
            major_moment_knm=float(fe_action["moment_knm"]), mcr_knm=float(sec["Mcr"]),
            bending_resistance_knm=float(sec["Mrx_ltb"]),
            section_class=int(member_class_check(0.0, props, material)),
            omega2=float(sec["omega2"]), iy_cm4=_float(props.get("Iy")),
            torsional_constant_cm4=_float(props.get("J")),
            warping_constant=_float(props.get("Cw")),
            plastic_moment_knm=float(sec["Mp"]), yield_moment_knm=float(sec["My"]),
            utilisation=float(ratio),
        ))

    database = load_bracing_database(database_path)
    total_shear = sum(item.top_shear_kn for item in columns)
    bay_mm = _float(frame["rafter_spacing"])
    roof_points = _roof_purlin_points(frame)
    if not roof_points:
        rafter_node_names = {
            node_name
            for member in data.members if member.type == "rafter"
            for node_name in (member.i_node, member.j_node)
        }
        roof_points = [
            {"name": name, "x_mm": node.x, "y_mm": node.y}
            for name, node in sorted(data.nodes.items(), key=lambda pair: pair[1].x)
            if name in rafter_node_names
        ]
    purlin_interval = int(frame.get("roof_bracing_purlin_interval", 1))
    brace_panels = _roof_brace_panels(
        roof_points, frame.get("building_roof"), purlin_interval
    )
    roof_panel_widths = [
        math.hypot(
            roof_points[end]["x_mm"] - roof_points[start]["x_mm"],
            roof_points[end]["y_mm"] - roof_points[start]["y_mm"],
        )
        for start, end in brace_panels
    ]
    longest_roof_brace = max(math.hypot(bay_mm, width) for width in roof_panel_widths)
    roof_force = total_shear / 2 * longest_roof_brace / bay_mm
    angle, angle_resistance, angle_slenderness = _select_angle(
        database, roof_force, longest_roof_brace, _float(material["fy"])
    )

    column_layout = _column_brace_geometry(
        column_bracing_type, bay_mm, _float(frame["eaves_height"]),
        int(frame.get("col_bracing_spacing", 1)),
    )
    side_length = column_layout["member_length_mm"]
    side_force = (
        total_shear / 2 * side_length /
        column_layout["horizontal_projection_mm"]
    )
    if column_bracing_type == "X":
        side_section, side_resistance, side_slenderness = _select_angle(
            database, side_force, side_length, _float(material["fy"])
        )
        side_behaviour = "tension-only"
        side_slenderness_limit = TENSION_SLENDERNESS_LIMIT
    else:
        side_section, side_resistance, side_radius, side_ratio = _select_chs(
            database, side_force, side_length, material
        )
        side_slenderness = {
            "axis": "x-x",
            "governing": {"k": 1.0, "radius": side_radius, "ratio": side_ratio},
            "checks": {"x-x": {"k": 1.0, "radius": side_radius, "ratio": side_ratio}},
            "rx": side_radius, "ry": side_radius, "rv": 0.0,
        }
        side_behaviour = "tension and compression"
        side_slenderness_limit = COMPRESSION_SLENDERNESS_LIMIT
    purlins = database.get("Lipped Channels", [])
    purlin_designation = str(frame.get("purlin_section", "")).strip()
    if purlin_designation:
        purlin = next(
            (item for item in purlins if item.get("Designation") == purlin_designation),
            None,
        )
        if purlin is None:
            raise ValueError(
                f"purlin_section {purlin_designation!r} is not in the Lipped Channels database. "
                "Use depthxflangexlipxthickness, for example 125x50x20x2.5."
            )
    else:
        purlin = purlins[0]
    loaded_shears = {}
    for column in columns:
        point = min(roof_points, key=lambda item: abs(item["x_mm"] - column.x_mm))
        loaded_shears[point["name"]] = loaded_shears.get(point["name"], 0.0) + column.top_shear_kn
    _, roof_model_summary = _analyse_roof_bracing_pynite(
        roof_points,
        brace_panels,
        loaded_shears,
        bay_mm,
        angle,
        purlin,
        material,
    )
    members = [
        BracingMemberResult(
            member_type="Roof X-brace", section_family=angle["section_type"],
            section=angle["Designation"], design_force_kn=float(roof_force),
            length_mm=longest_roof_brace, area_mm2=_float(angle["A"]) * 1000,
            fy_mpa=_float(material["fy"]), resistance_kn=angle_resistance,
            resistance_utilisation=float(roof_force / angle_resistance),
            radius_of_gyration_mm=float(angle_slenderness["governing"]["radius"]),
            effective_length_factor=float(angle_slenderness["governing"]["k"]),
            slenderness_axis=angle_slenderness["axis"],
            rx_mm=float(angle_slenderness["rx"]), ry_mm=float(angle_slenderness["ry"]),
            rv_mm=float(angle_slenderness["rv"]),
            slenderness_xx=float(angle_slenderness["checks"]["x-x"]["ratio"]),
            slenderness_yy=float(angle_slenderness["checks"]["y-y"]["ratio"]),
            slenderness_vv=float(angle_slenderness["checks"]["v-v"]["ratio"]),
            slenderness_ratio=float(angle_slenderness["governing"]["ratio"]),
            nondimensional_slenderness=float(
                angle_slenderness["governing"]["ratio"] * math.sqrt(
                    _float(material["fy"]) /
                    (math.pi ** 2 * _float(material["E"]) * 1000)
                )
            ),
            slenderness_limit=TENSION_SLENDERNESS_LIMIT,
            slenderness_utilisation=float(angle_slenderness["governing"]["ratio"] / TENSION_SLENDERNESS_LIMIT),
            utilisation=float(max(
                roof_force / angle_resistance,
                angle_slenderness["governing"]["ratio"] / TENSION_SLENDERNESS_LIMIT,
            )), behaviour="tension-only",
        ),
        BracingMemberResult(
            member_type="Longitudinal side-wall brace",
            section_family=side_section["section_type"],
            section=side_section["Designation"], design_force_kn=float(side_force),
            length_mm=side_length, area_mm2=_float(side_section["A"]) * 1000,
            fy_mpa=_float(material["fy"]), resistance_kn=side_resistance,
            resistance_utilisation=float(side_force / side_resistance),
            radius_of_gyration_mm=float(side_slenderness["governing"]["radius"]),
            effective_length_factor=float(side_slenderness["governing"]["k"]),
            slenderness_axis=side_slenderness["axis"],
            rx_mm=float(side_slenderness["rx"]), ry_mm=float(side_slenderness["ry"]),
            rv_mm=float(side_slenderness["rv"]),
            slenderness_xx=float(side_slenderness["checks"].get("x-x", {}).get("ratio", 0)),
            slenderness_yy=float(side_slenderness["checks"].get("y-y", {}).get("ratio", 0)),
            slenderness_vv=float(side_slenderness["checks"].get("v-v", {}).get("ratio", 0)),
            slenderness_ratio=float(side_slenderness["governing"]["ratio"]),
            nondimensional_slenderness=float(
                side_slenderness["governing"]["ratio"] * math.sqrt(
                    _float(material["fy"]) /
                    (math.pi ** 2 * _float(material["E"]) * 1000)
                )
            ),
            slenderness_limit=side_slenderness_limit,
            slenderness_utilisation=float(side_slenderness["governing"]["ratio"] / side_slenderness_limit),
            utilisation=float(max(
                side_force / side_resistance,
                side_slenderness["governing"]["ratio"] / side_slenderness_limit,
            )), behaviour=side_behaviour,
        ),
    ]
    internal = data.wind_data[0].get("internal_pressure", {}) if data.wind_data else {}
    cpi_90 = internal.get("directions", {}).get("90", {})
    return {
        "inputs": {
            "gable_column_count": count,
            "gable_column_brace_intervals": brace_intervals,
            "rafter_bracing_spacing_count": int(frame["rafter_bracing_spacing"]),
            "purlin_section": purlin["Designation"],
            "purlin_max_spacing_mm": _float(frame.get("purlin_max_spacing_mm")),
            "roof_bracing_purlin_interval": purlin_interval,
            "column_bracing_spacing_count": int(frame["col_bracing_spacing"]),
            "column_bracing_type": column_bracing_type,
        },
        "pressure_cases": pressure_cases,
        "governing_characteristic_pressure_kpa": pressure,
        "wind_uls_factor": wind_factor,
        "total_gable_top_shear_kn": float(total_shear),
        "gable_columns": [asdict(item) for item in columns],
        "bracing_members": [asdict(item) for item in members],
        "gable_layout": {
            "width_mm": _float(frame["gable_width"]),
            "eaves_height_mm": _float(frame["eaves_height"]),
            "apex_height_mm": _float(frame["apex_height"]),
            "columns": [{"name": c.name, "x_mm": c.x_mm, "height_mm": c.height_mm} for c in columns],
        },
        "roof_layout": {
            "bay_length_mm": bay_mm,
            "roof_points": roof_points,
            "loaded_nodes": list(loaded_shears),
            "brace_panels": [
                {
                    "start": roof_points[start]["name"],
                    "end": roof_points[end]["name"],
                    "start_index": start,
                    "end_index": end,
                }
                for start, end in brace_panels
            ],
            "x_bracing": True,
        },
        "column_bracing_layout": column_layout,
        "pynite_roof_model": roof_model_summary,
        "assumptions": [
            "The maximum absolute W90 zone D/E pressure from the stored internal-pressure envelope governs both gable ends "
            f"(cpi max={_float(cpi_90.get('maximum_cpi'), 0.2):.3f}, "
            f"min={_float(cpi_90.get('minimum_cpi'), -0.3):.3f}).",
            "Gable columns are pinned at base and roof, bend about their strong axis, and use Mcr with equal unbraced intervals.",
            "The selected internal gable columns conservatively carry the full gable-wall width; no load-sharing credit is taken for corner portal columns.",
            "Roof X-braces are tension-only; reverse wind activates the opposite diagonal.",
            f"Roof X-bracing continues across the complete roof width in each braced bay and connects at every {purlin_interval} purlin space(s); the final panel on each slope is shortened where required.",
            "Roof brace angles satisfy KL/r <= 300 about x-x and y-y with K=1.0 and about v-v with K=0.5; they are not smaller than 50x50x5 so practical bolt edge and end distances can be detailed.",
            (
                "Column X-bracing uses tension-only angles satisfying KL/r <= 300 about x-x and y-y with K=1.0 and about v-v with K=0.5, plus the minimum 50x50x5 envelope."
                if column_bracing_type == "X" else
                f"Column {column_bracing_type}-bracing uses CHS members satisfying KL/r <= 200 in addition to the tension/compression resistance envelope."
            ),
            "All gable top shear is resisted by the roof and longitudinal bracing shown.",
            "Cold-formed purlin strut compression resistance is intentionally deferred to the following design function.",
        ],
    }
