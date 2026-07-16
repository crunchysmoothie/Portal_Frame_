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
    utilisation: float


@dataclass(frozen=True)
class BracingMemberResult:
    member_type: str
    section_family: str
    section: str
    design_force_kn: float
    length_mm: float
    resistance_kn: float
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


def _select_angle(database, force_kn, fy):
    choices = database.get("Equal Angles", []) + database.get("Unequal Angles", [])
    choices.sort(key=lambda item: _float(item.get("m"), math.inf))
    for section in choices:
        resistance = PHI * _float(section.get("A")) * 1000 * fy / 1000
        if resistance >= force_kn:
            return section, resistance
    raise ValueError("No angle in the supplied database passes the roof X-brace tension check.")


def _select_chs(database, force_kn, length_mm, material):
    fy = _float(material["fy"])
    e = _float(material["E"]) * 1000
    for section in database.get("CHS", []):
        area = _float(section.get("A")) * 1000
        radius = _float(section.get("rx"))
        if area <= 0 or radius <= 0:
            continue
        slenderness = (length_mm / radius) * math.sqrt(fy / (math.pi ** 2 * e))
        compression = PHI * area * fy * (
            1 + slenderness ** (2 * BUCKLING_EXPONENT)
        ) ** (-1 / BUCKLING_EXPONENT) / 1000
        tension = PHI * area * fy / 1000
        resistance = min(compression, tension)
        if resistance >= force_kn:
            return section, resistance
    raise ValueError("No CHS in the supplied database passes the longitudinal brace check.")


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
    roof_points, loaded_shears, bay_mm, angle, purlin, material
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
    for index in range(len(roof_points) - 1):
        model.add_member(
            f"XB{index}A", f"R0_{index}", f"R1_{index + 1}",
            "STEEL", "ANGLE", tension_only=True,
        )
        model.add_member(
            f"XB{index}B", f"R0_{index + 1}", f"R1_{index}",
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
        "x_brace_count": 2 * (len(roof_points) - 1),
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
            bending_resistance_knm=float(sec["Mrx_ltb"]), utilisation=float(ratio),
        ))

    database = load_bracing_database(database_path)
    total_shear = sum(item.top_shear_kn for item in columns)
    bay_mm = _float(frame["rafter_spacing"])
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
    roof_cell_widths = [
        math.hypot(b["x_mm"] - a["x_mm"], b["y_mm"] - a["y_mm"])
        for a, b in zip(roof_points, roof_points[1:])
    ]
    longest_roof_brace = max(math.hypot(bay_mm, width) for width in roof_cell_widths)
    roof_force = total_shear / 2 * longest_roof_brace / bay_mm
    angle, angle_resistance = _select_angle(database, roof_force, _float(material["fy"]))

    side_length = math.hypot(bay_mm, _float(frame["eaves_height"]))
    side_force = total_shear / 2 * side_length / bay_mm
    chs, chs_resistance = _select_chs(database, side_force, side_length, material)
    purlin = database.get("Lipped Channels", [])[0]
    _, roof_model_summary = _analyse_roof_bracing_pynite(
        roof_points,
        {column.roof_node: column.top_shear_kn for column in columns},
        bay_mm,
        angle,
        purlin,
        material,
    )
    members = [
        BracingMemberResult(
            member_type="Roof X-brace", section_family=angle["section_type"],
            section=angle["Designation"], design_force_kn=float(roof_force),
            length_mm=longest_roof_brace, resistance_kn=angle_resistance,
            utilisation=float(roof_force / angle_resistance), behaviour="tension-only",
        ),
        BracingMemberResult(
            member_type="Longitudinal side-wall brace", section_family="CHS",
            section=chs["Designation"], design_force_kn=float(side_force),
            length_mm=side_length, resistance_kn=chs_resistance,
            utilisation=float(side_force / chs_resistance), behaviour="tension and compression",
        ),
    ]
    internal = data.wind_data[0].get("internal_pressure", {}) if data.wind_data else {}
    cpi_90 = internal.get("directions", {}).get("90", {})
    return {
        "inputs": {
            "gable_column_count": count,
            "gable_column_brace_intervals": brace_intervals,
            "rafter_bracing_spacing_count": int(frame["rafter_bracing_spacing"]),
            "column_bracing_spacing_count": int(frame["col_bracing_spacing"]),
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
            "loaded_nodes": [c.roof_node for c in columns],
            "x_bracing": True,
        },
        "pynite_roof_model": roof_model_summary,
        "assumptions": [
            "The maximum absolute W90 zone D/E pressure from the stored internal-pressure envelope governs both gable ends "
            f"(cpi max={_float(cpi_90.get('maximum_cpi'), 0.2):.3f}, "
            f"min={_float(cpi_90.get('minimum_cpi'), -0.3):.3f}).",
            "Gable columns are pinned at base and roof, bend about their strong axis, and use Mcr with equal unbraced intervals.",
            "The selected internal gable columns conservatively carry the full gable-wall width; no load-sharing credit is taken for corner portal columns.",
            "Roof X-braces are tension-only; reverse wind activates the opposite diagonal.",
            "All gable top shear is resisted by the roof and longitudinal bracing shown.",
            "Cold-formed purlin strut compression resistance is intentionally deferred to the following design function.",
        ],
    }
