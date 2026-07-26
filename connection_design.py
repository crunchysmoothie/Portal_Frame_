"""Portal-frame haunch and base-plate geometry and connection workflow.

This module deliberately separates completed calculations from required inputs.
Base-plate concrete bearing and plate cantilever bending are calculated from
stored ULS reactions. Haunch demand envelopes and selected geometry feed the
separate detailed post-analysis check module.
"""

from __future__ import annotations

import math
from html import escape
from pathlib import Path
from typing import Any, Mapping

from connection_checks import calculate_connection_checks
from foundation_design import bearing_pressures
from member_database import load_member_database


PROJECT_ROOT = Path(__file__).resolve().parent
PLATE_THICKNESSES_MM = (10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80)
BOLT_DIAMETERS_MM = (20, 24, 30, 36)
BOLT_TENSILE_AREAS_MM2 = {20: 245.0, 24: 353.0, 30: 561.0, 36: 817.0}
BOLT_GRADE_FUB_MPA = 800.0
BOLT_RESISTANCE_FACTOR = 0.80
PLATE_RESISTANCE_FACTOR = 0.90


def _uls_names(snapshot: Mapping[str, Any]) -> set[str]:
    return {
        str(item["name"])
        for item in snapshot["input_data"].get("load_combinations", [])
    }


def _round_up_plate(value_mm: float) -> float:
    return math.ceil((value_mm - 1e-9) / 25.0) * 25.0


def _plate_thickness(required_mm: float) -> float | None:
    return next(
        (value for value in PLATE_THICKNESSES_MM if value >= required_mm),
        None,
    )


def _round_up(value: float, increment: float = 5.0) -> float:
    return math.ceil((value - 1e-9) / increment) * increment


def _bolt_resistances(diameter_mm: float) -> dict[str, float]:
    area_t = BOLT_TENSILE_AREAS_MM2[int(diameter_mm)]
    nominal_area = math.pi * diameter_mm**2 / 4.0
    tension = (
        0.75
        * BOLT_RESISTANCE_FACTOR
        * area_t
        * BOLT_GRADE_FUB_MPA
        / 1000.0
    )
    shear = (
        0.70
        * 0.60
        * BOLT_RESISTANCE_FACTOR
        * nominal_area
        * BOLT_GRADE_FUB_MPA
        / 1000.0
    )
    return {
        "tension_resistance_kN": tension,
        "shear_resistance_kN": shear,
    }


def _minimum_bolt_distances(diameter_mm: float) -> dict[str, float]:
    return {
        "minimum_edge_distance_mm": 1.5 * diameter_mm,
        "minimum_pitch_mm": 2.7 * diameter_mm,
        "minimum_gauge_mm": 2.7 * diameter_mm,
    }


def _four_bolt_layout(
    length_mm: float,
    width_mm: float,
    diameter_mm: float,
) -> dict[str, Any] | None:
    minimums = _minimum_bolt_distances(diameter_mm)
    end_distance = _round_up(
        max(minimums["minimum_edge_distance_mm"], 50.0)
    )
    edge_distance = _round_up(
        max(minimums["minimum_edge_distance_mm"], 50.0)
    )
    pitch = length_mm - 2.0 * end_distance
    gauge = width_mm - 2.0 * edge_distance
    if (
        pitch + 1e-9 < minimums["minimum_pitch_mm"]
        or gauge + 1e-9 < minimums["minimum_gauge_mm"]
    ):
        return None
    return {
        "bolt_count": 4,
        "diameter_mm": diameter_mm,
        "hole_diameter_mm": diameter_mm + (2.0 if diameter_mm <= 24 else 3.0),
        "end_distance_mm": end_distance,
        "edge_distance_mm": edge_distance,
        "pitch_mm": pitch,
        "gauge_mm": gauge,
        **minimums,
        "distance_status": "PASS",
        "coordinates_from_plate_centre_mm": [
            {"x": x, "y": y}
            for x in (-pitch / 2.0, pitch / 2.0)
            for y in (-gauge / 2.0, gauge / 2.0)
        ],
    }


def _design_holding_down_bolts(
    reactions: list[Mapping[str, Any]],
    length_mm: float,
    width_mm: float,
) -> dict[str, Any]:
    for diameter in BOLT_DIAMETERS_MM:
        layout = _four_bolt_layout(length_mm, width_mm, float(diameter))
        if layout is None:
            continue
        resistances = _bolt_resistances(float(diameter))
        pitch = float(layout["pitch_mm"])
        sum_x_squared = 4.0 * (pitch / 2.0) ** 2
        checks = []
        for reaction in reactions:
            axial_tension_per_bolt = max(
                0.0, -float(reaction["fy"]) / 4.0
            )
            moment_tension_per_bolt = (
                abs(float(reaction["mz"]))
                * 1_000_000.0
                * (pitch / 2.0)
                / max(sum_x_squared, 1.0)
                / 1000.0
            )
            tension = max(
                0.0, axial_tension_per_bolt + moment_tension_per_bolt
            )
            shear = abs(float(reaction.get("fx", 0.0))) / 4.0
            interaction = (
                shear / resistances["shear_resistance_kN"]
                + tension / resistances["tension_resistance_kN"]
            )
            checks.append({
                "combination": str(reaction["load_combination"]),
                "bolt_tension_kN": tension,
                "bolt_shear_kN": shear,
                "linear_interaction": interaction,
                "interaction_limit": 1.4,
                "status": "PASS" if interaction <= 1.4 else "FAIL",
            })
        if all(item["status"] == "PASS" for item in checks):
            governing = max(
                checks, key=lambda item: float(item["linear_interaction"])
            )
            return {
                "status": "PRELIMINARY_PASS",
                "layout": layout,
                "resistances": resistances,
                "checks": checks,
                "governing_check": governing,
                "steel_grade": "8.8",
                "qualification": (
                    "Bolt steel tension/shear interaction only. Concrete "
                    "breakout, pull-out, pedestal reinforcement and embedment "
                    "remain HOLD_POINT checks."
                ),
            }
    return {
        "status": "HOLD_POINT",
        "reason": (
            "No four-bolt M20-M36 layout passed steel interaction and minimum "
            "distance checks within the selected base plate."
        ),
    }


def _base_plate_stiffeners(
    plate: Mapping[str, Any],
    column_depth_mm: float,
    column_width_mm: float,
    steel_yield_mpa: float,
) -> dict[str, Any]:
    projection = float(plate["plate_projection_mm"])
    pressure_mpa = float(
        plate["governing_bearing"]["q_max_kpa"]
    ) / 1000.0
    required = (
        float(plate["required_thickness_mm"]) > 50.0
        or projection > 200.0
    )
    if not required:
        return {
            "required": False,
            "status": "NOT_REQUIRED",
            "reason": (
                "Unstiffened plate thickness is at most 50 mm and the maximum "
                "projection is at most 200 mm."
            ),
        }
    stiffener_count = 4
    stiffener_height = _round_up(
        max(100.0, min(300.0, 0.60 * column_depth_mm)), 10.0
    )
    stiffener_length = _round_up(max(100.0, projection), 10.0)
    tributary_width = max(column_width_mm / 2.0, 75.0)
    demand_per_stiffener_kN = (
        pressure_mpa
        * stiffener_length
        * tributary_width
        / 1000.0
    )
    required_thickness = (
        demand_per_stiffener_kN
        * 1000.0
        / (
            0.67
            * PLATE_RESISTANCE_FACTOR
            * steel_yield_mpa
            * stiffener_height
        )
    )
    provided = _plate_thickness(max(10.0, required_thickness))
    return {
        "required": True,
        "status": "PRELIMINARY_PASS" if provided is not None else "HOLD_POINT",
        "count": stiffener_count,
        "arrangement": (
            "Two stiffeners aligned with each column flange, welded to the "
            "column and base plate."
        ),
        "height_mm": stiffener_height,
        "length_mm": stiffener_length,
        "required_thickness_mm": required_thickness,
        "provided_thickness_mm": provided,
        "demand_per_stiffener_kN": demand_per_stiffener_kN,
        "qualification": (
            "Preliminary stiffener shear-area check. Welds, local buckling "
            "and force introduction into the column remain HOLD_POINT checks."
        ),
    }


def _section_properties(
    designation: str,
) -> tuple[str, Mapping[str, Any]]:
    database = load_member_database(PROJECT_ROOT / "member_database.csv")
    for family, sections in database.items():
        if designation in sections:
            return family, sections[designation]
    raise ValueError(
        f"Column section {designation!r} was not found for base-plate design."
    )


def _design_base_plates(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    results = snapshot["results"]
    project = results.get("project", {})
    column_section = str(project.get("column_section", "")).strip()
    family, properties = _section_properties(column_section)
    column_depth = float(properties["h"])
    column_width = float(properties["b"])
    concrete_strength_mpa = 30.0
    steel_yield_mpa = 355.0
    concrete_bearing_mpa = 0.4 * concrete_strength_mpa
    uls_names = _uls_names(snapshot)
    reactions = [
        dict(item)
        for item in results.get("reactions", [])
        if str(item.get("load_combination", "")) in uls_names
    ]
    supports = sorted({str(item["node"]) for item in reactions})
    support_results: list[dict[str, Any]] = []
    for support in supports:
        rows = [item for item in reactions if str(item["node"]) == support]
        compression_rows = [
            item for item in rows if float(item["fy"]) > 1e-9
        ]
        if not compression_rows:
            support_results.append({
                "support": support,
                "status": "HOLD_POINT",
                "reason": "No compressive ULS reaction is available.",
            })
            continue

        minimum_length = _round_up_plate(column_depth + 100.0)
        minimum_width = _round_up_plate(column_width + 100.0)
        candidates: list[tuple[float, float]] = []
        for length in range(int(minimum_length), 2001, 25):
            for width in range(int(minimum_width), 1201, 25):
                candidates.append((float(length), float(width)))
        candidates.sort(key=lambda item: (item[0] * item[1], item[0], item[1]))

        selected: dict[str, Any] | None = None
        for length_mm, width_mm in candidates:
            if _four_bolt_layout(length_mm, width_mm, 20.0) is None:
                continue
            checks = []
            acceptable = True
            for reaction in compression_rows:
                pressures = bearing_pressures(
                    float(reaction["fy"]),
                    float(reaction["mz"]),
                    length_mm / 1000.0,
                    width_mm / 1000.0,
                )
                if pressures["contact"] == "resultant_outside_base":
                    pressures = {
                        **pressures,
                        "contact": "anchor_tension_required",
                        "q_min_kpa": 0.0,
                        "q_max_kpa": (
                            float(reaction["fy"])
                            / (
                                (length_mm / 1000.0)
                                * (width_mm / 1000.0)
                            )
                        ),
                    }
                if float(pressures["q_max_kpa"]) > concrete_bearing_mpa * 1000.0:
                    acceptable = False
                    break
                checks.append({
                    "combination": reaction["load_combination"],
                    "compression_kN": float(reaction["fy"]),
                    "moment_kNm": float(reaction["mz"]),
                    **pressures,
                })
            if not acceptable:
                continue
            governing = max(checks, key=lambda item: item["q_max_kpa"])
            projection_mm = max(
                (length_mm - column_depth) / 2.0,
                (width_mm - column_width) / 2.0,
            )
            pressure_mpa = float(governing["q_max_kpa"]) / 1000.0
            required_thickness = projection_mm * math.sqrt(
                3.0 * pressure_mpa / steel_yield_mpa
            )
            provided_thickness = _plate_thickness(required_thickness)
            if provided_thickness is None:
                continue
            selected = {
                "length_mm": length_mm,
                "width_mm": width_mm,
                "required_thickness_mm": required_thickness,
                "provided_thickness_mm": provided_thickness,
                "governing_bearing": governing,
                "bearing_resistance_mpa": concrete_bearing_mpa,
                "plate_projection_mm": projection_mm,
            }
            break

        if selected is None:
            support_results.append({
                "support": support,
                "status": "HOLD_POINT",
                "reason": (
                    "No unstiffened plate passed within the 2000 x 1200 x "
                    "80 mm preliminary search limits."
                ),
            })
            continue

        tension_rows = [
            item for item in rows if float(item["fy"]) <= 0
        ]
        partial_contact = any(
            bearing_pressures(
                float(item["fy"]),
                float(item["mz"]),
                selected["length_mm"] / 1000.0,
                selected["width_mm"] / 1000.0,
            )["contact"] != "full"
            for item in compression_rows
        )
        holding_down_required = bool(tension_rows or partial_contact)
        bolt_design = _design_holding_down_bolts(
            rows,
            float(selected["length_mm"]),
            float(selected["width_mm"]),
        )
        stiffener_design = _base_plate_stiffeners(
            selected,
            column_depth,
            column_width,
            steel_yield_mpa,
        )
        support_results.append({
            "support": support,
            "status": (
                "HOLD_POINT"
                if (
                    holding_down_required
                    or bolt_design["status"] != "PRELIMINARY_PASS"
                    or stiffener_design["status"] == "HOLD_POINT"
                )
                else "PRELIMINARY_PASS"
            ),
            "column_section": column_section,
            "column_section_family": family,
            "plate": selected,
            "holding_down_bolts_required": holding_down_required,
            "holding_down_bolts": bolt_design,
            "stiffeners": stiffener_design,
            "uplift_combinations": [
                {
                    "combination": item["load_combination"],
                    "uplift_kN": abs(float(item["fy"])),
                    "moment_kNm": float(item["mz"]),
                }
                for item in tension_rows
            ],
        })

    return {
        "status": (
            "PRELIMINARY_PASS"
            if support_results
            and all(
                item["status"] == "PRELIMINARY_PASS"
                for item in support_results
            )
            else "HOLD_POINT"
        ),
        "supports": support_results,
        "basis": {
            "concrete_strength_mpa": concrete_strength_mpa,
            "concrete_bearing_resistance_mpa": concrete_bearing_mpa,
            "plate_yield_strength_mpa": steel_yield_mpa,
            "dimension_increment_mm": 25.0,
            "available_plate_thicknesses_mm": list(PLATE_THICKNESSES_MM),
        },
        "references": [
            (
                "Mahachi, Design of Structural Steelwork to SANS 10162, "
                "Chapter 7.9, equations 7.55-7.61: concrete bearing, slab-base "
                "plate bending and axial-load-plus-moment contact."
            ),
            (
                "Mahachi Chapter 7.3-7.4: minimum edge distance 1.5d, "
                "minimum bolt pitch 2.7d, bolt tension/shear resistance and "
                "equation 7.18 combined shear/tension interaction."
            ),
        ],
        "hold_points": [
            "Concrete anchor breakout, pull-out, embedment and pedestal reinforcement remain INPUT_REQUIRED.",
            "Grout, shear keys, fabrication tolerances and erection detailing require project confirmation.",
            "A plate thicker than 50 mm requires a fabrication and stiffener review.",
        ],
    }


def _connection_face_envelope(
    snapshot: Mapping[str, Any],
    fallback_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    visualisation = snapshot.get("results", {}).get("visualisation", {})
    samples = []
    for combination in visualisation.get("combinations", []):
        if str(combination.get("kind", "")).upper() != "ULS":
            continue
        for member in combination.get("members", []):
            if str(member.get("type", "")).lower() != "rafter":
                continue
            force_points = list(member.get("force_points", []))
            if not force_points:
                continue
            for point in (force_points[0], force_points[-1]):
                samples.append({
                    "combination": str(combination.get("name", "")),
                    "member": str(member.get("name", "")),
                    "axial_force_kN": abs(float(point.get("axial_kn", 0.0))),
                    "shear_force_kN": abs(float(point.get("shear_y_kn", 0.0))),
                    "major_moment_kNm": abs(
                        float(point.get("moment_z_knm", 0.0))
                    ),
                })
    if samples:
        moment = max(samples, key=lambda item: item["major_moment_kNm"])
        axial = max(samples, key=lambda item: item["axial_force_kN"])
        shear = max(samples, key=lambda item: item["shear_force_kN"])
        return {
            "major_moment_kNm": moment["major_moment_kNm"],
            "moment_combination": moment["combination"],
            "moment_member": moment["member"],
            "axial_force_kN": axial["axial_force_kN"],
            "axial_combination": axial["combination"],
            "axial_member": axial["member"],
            "shear_force_kN": shear["shear_force_kN"],
            "shear_combination": shear["combination"],
            "shear_member": shear["member"],
            "qualification": (
                "Envelope of stored ULS rafter end-force samples at connection "
                "faces."
            ),
        }
    moment_row = max(
        fallback_rows, key=lambda item: abs(float(item["major_moment"]))
    )
    axial_row = max(
        fallback_rows, key=lambda item: abs(float(item["axial_force"]))
    )
    return {
        "major_moment_kNm": abs(float(moment_row["major_moment"])),
        "moment_combination": moment_row["load_combination"],
        "moment_member": moment_row["member"],
        "axial_force_kN": abs(float(axial_row["axial_force"])),
        "axial_combination": axial_row["load_combination"],
        "axial_member": axial_row["member"],
        "shear_force_kN": 0.0,
        "shear_combination": "Unavailable in legacy snapshot",
        "shear_member": "",
        "qualification": (
            "Conservative stored member envelope; exact connection-face shear "
            "was unavailable in this legacy snapshot."
        ),
    }


def _design_haunch_end_plate(
    location: Mapping[str, Any],
    envelope: Mapping[str, Any],
    rafter: Mapping[str, Any],
    column: Mapping[str, Any],
) -> dict[str, Any]:
    steel_yield_mpa = 355.0
    effective_depth = (
        float(rafter["h"])
        + float(location.get("added_depth_mm", 0.0))
        - float(rafter["tf"])
    )
    flange_force = (
        float(envelope["major_moment_kNm"]) * 1000.0
        / max(effective_depth, 1.0)
        + float(envelope["axial_force_kN"]) / 2.0
    )
    maximum_pitch_mm = 200.0
    row_count = max(
        4, int(math.ceil(effective_depth / maximum_pitch_mm)) + 1
    )
    selected = None
    for diameter in BOLT_DIAMETERS_MM:
        minimums = _minimum_bolt_distances(float(diameter))
        nominal_edge = _round_up(max(1.5 * diameter, 40.0))
        gauge = _round_up(
            max(float(rafter["b"]), float(column["b"]), 2.7 * diameter),
            5.0,
        )
        plate_width = _round_up(gauge + 2.0 * nominal_edge, 25.0)
        edge = (plate_width - gauge) / 2.0
        plate_height = _round_up(
            max(
                effective_depth + 2.0 * nominal_edge,
                (row_count - 1) * minimums["minimum_pitch_mm"]
                + 2.0 * nominal_edge,
            ),
            25.0,
        )
        pitch = math.floor(
            (
                (plate_height - 2.0 * nominal_edge)
                / (row_count - 1)
            )
            / 5.0
        ) * 5.0
        end_distance = (
            plate_height - (row_count - 1) * pitch
        ) / 2.0
        if pitch + 1e-9 < minimums["minimum_pitch_mm"]:
            continue
        if pitch - 1e-9 > maximum_pitch_mm:
            continue
        resistances = _bolt_resistances(float(diameter))
        tension_bolts = 4
        bolt_tension = 1.30 * flange_force / tension_bolts
        bolt_shear = float(envelope["shear_force_kN"]) / (row_count * 2)
        interaction = (
            bolt_shear / resistances["shear_resistance_kN"]
            + bolt_tension / resistances["tension_resistance_kN"]
        )
        if interaction > 1.4:
            continue
        lever = max(edge, end_distance)
        strip_width = max(gauge / 2.0, 1.0)
        required_plate_thickness = math.sqrt(
            6.0
            * bolt_tension
            * 1000.0
            * lever
            / (PLATE_RESISTANCE_FACTOR * steel_yield_mpa * strip_width)
        )
        provided_plate_thickness = _plate_thickness(
            required_plate_thickness
        )
        if provided_plate_thickness is None:
            continue
        selected = {
            "status": "PRELIMINARY_PASS",
            "plate": {
                "height_mm": plate_height,
                "width_mm": plate_width,
                "required_thickness_mm": required_plate_thickness,
                "provided_thickness_mm": provided_plate_thickness,
            },
            "bolts": {
                "status": "PRELIMINARY_PASS",
                "bolt_count": row_count * 2,
                "row_count": row_count,
                "columns": 2,
                "diameter_mm": float(diameter),
                "hole_diameter_mm": float(
                    diameter + (2 if diameter <= 24 else 3)
                ),
                "edge_distance_mm": edge,
                "end_distance_mm": end_distance,
                "pitch_mm": pitch,
                "gauge_mm": gauge,
                **minimums,
                "maximum_pitch_mm": maximum_pitch_mm,
                "distance_status": "PASS",
                "bolt_tension_kN": bolt_tension,
                "bolt_shear_kN": bolt_shear,
                "linear_interaction": interaction,
                "interaction_limit": 1.4,
                **resistances,
            },
            "flange_force_kN": flange_force,
            "prying_allowance": 1.30,
        }
        break
    if selected is None:
        return {
            "status": "HOLD_POINT",
            "reason": (
                "No four-row M20-M36 end-plate bolt layout passed the "
                "preliminary bolt interaction and plate-bending checks."
            ),
        }

    plate = selected["plate"]
    column_flange_resistance_kN = (
        0.25
        * PLATE_RESISTANCE_FACTOR
        * float(column["b"])
        * float(column["tf"]) ** 2
        * steel_yield_mpa
        / max(0.25 * max(float(selected["bolts"]["gauge_mm"]) / 2.0, 1.0), 1.0)
        / 1000.0
    )
    bearing_length = (
        float(plate["provided_thickness_mm"])
        + 2.5 * float(column["tf"])
        + 2.0 * float(column.get("r1", 0.0))
    )
    column_web_resistance_kN = (
        PLATE_RESISTANCE_FACTOR
        * float(column["tw"])
        * bearing_length
        * steel_yield_mpa
        / 1000.0
    )
    stiffeners_required = (
        float(plate["provided_thickness_mm"]) > 25.0
        or float(selected["bolts"]["linear_interaction"]) > 0.85
        or flange_force > column_flange_resistance_kN
        or flange_force > column_web_resistance_kN
    )
    stiffener_height = _round_up(max(100.0, effective_depth * 0.25), 10.0)
    required_stiffener_thickness = (
        flange_force
        * 1000.0
        / (
            2.0
            * PLATE_RESISTANCE_FACTOR
            * steel_yield_mpa
            * stiffener_height
        )
    )
    provided_stiffener_thickness = _plate_thickness(
        max(10.0, required_stiffener_thickness)
    )
    selected["stiffeners"] = (
        {
            "required": True,
            "status": (
                "PRELIMINARY_PASS"
                if provided_stiffener_thickness is not None
                else "HOLD_POINT"
            ),
            "count": 2,
            "position": "Aligned with the tension flange/outer bolt rows",
            "height_mm": stiffener_height,
            "length_mm": _round_up(max(100.0, effective_depth * 0.30), 10.0),
            "required_thickness_mm": required_stiffener_thickness,
            "provided_thickness_mm": provided_stiffener_thickness,
            "qualification": (
                "Transverse stiffeners are automatically added when the "
                "unreinforced supporting flange or web screen is exceeded. "
                "Yielding, buckling and weld checks follow in the detailed "
                "post-analysis module."
            ),
        }
        if stiffeners_required
        else {
            "required": False,
            "status": "NOT_REQUIRED",
            "reason": (
                "End plate is at most 25 mm thick and bolt interaction is at "
                "most 0.85."
            ),
        }
    )
    if selected["stiffeners"]["status"] == "HOLD_POINT":
        selected["status"] = "HOLD_POINT"
    return selected


def _haunch_connection_start(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    input_frame = snapshot["input_data"].get("frame_data", [{}])[0]
    results = snapshot["results"]
    uls_names = _uls_names(snapshot)
    rafter_rows = [
        item
        for item in results.get("members", [])
        if str(item.get("member_type", "")).lower() == "rafter"
        and str(item.get("load_combination", "")) in uls_names
    ]
    if not rafter_rows:
        return {
            "status": "HOLD_POINT",
            "reason": "No ULS rafter member calculations were stored.",
        }

    envelope = _connection_face_envelope(snapshot, rafter_rows)
    locations = []
    if str(input_frame.get("use_eaves_haunch", "No")).lower() == "yes":
        locations.append({
            "location": "Eaves haunch",
            "length_mm": float(input_frame.get("eaves_haunch_length", 0.0)),
            "added_depth_mm": float(input_frame.get("eaves_haunch_depth", 0.0)),
        })
    if str(input_frame.get("use_apex_haunch", "No")).lower() == "yes":
        locations.append({
            "location": "Apex haunch",
            "length_mm": float(input_frame.get("apex_haunch_length", 0.0)),
            "added_depth_mm": float(input_frame.get("apex_haunch_depth", 0.0)),
        })
    project = results.get("project", {})
    _, rafter_properties = _section_properties(
        str(project.get("rafter_section", "")).strip()
    )
    _, column_properties = _section_properties(
        str(project.get("column_section", "")).strip()
    )
    designs = [
        {
            **location,
            "rafter_section": str(project.get("rafter_section", "")).strip(),
            "column_section": str(project.get("column_section", "")).strip(),
            "connection": _design_haunch_end_plate(
                location,
                envelope,
                rafter_properties,
                column_properties,
            ),
        }
        for location in locations
    ]
    return {
        "status": (
            "PRELIMINARY_PASS"
            if designs
            and all(
                item["connection"]["status"] == "PRELIMINARY_PASS"
                for item in designs
            )
            else ("NOT_REQUIRED" if not designs else "HOLD_POINT")
        ),
        "locations": designs,
        "preliminary_uls_envelope": envelope,
        "references": [
            (
                "Mahachi Chapter 7.8, equations 7.45-7.48: fillet-weld "
                "force per unit length under direct force and moment."
            ),
            (
                "Mahachi Chapter 7.3-7.5: minimum edge distance 1.5d, "
                "minimum pitch 2.7d, bolt resistance, combined interaction "
                "and prying action."
            ),
        ],
        "next_checks": [
            "Review the detailed post-analysis prying, weld, stiffener and local-member checks.",
            "Confirm fabrication detailing, tolerances and the project connection standard.",
        ],
    }


def design_portal_connections(
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Return geometry plus detailed post-analysis connection checks."""

    base_plates = _design_base_plates(snapshot)
    haunch_connections = _haunch_connection_start(snapshot)
    detailed_checks = calculate_connection_checks(
        snapshot,
        base_plates=base_plates,
        haunch_connections=haunch_connections,
    )
    return {
        "schema_version": 3,
        "status": detailed_checks["status"],
        "base_plates": base_plates,
        "haunch_connections": haunch_connections,
        "detailed_checks": detailed_checks,
        "warning": (
            "Steel component checks are calculated from the completed analysis. "
            "Items marked INPUT_REQUIRED must not be treated as passed, and the "
            "package must not be issued for fabrication until they are resolved."
        ),
    }


def _base_plate_markup_svg(support: Mapping[str, Any]) -> str:
    plate = support.get("plate", {})
    bolt_design = support.get("holding_down_bolts", {})
    layout = bolt_design.get("layout", {})
    length = float(plate.get("length_mm", 1.0))
    width = float(plate.get("width_mm", 1.0))
    scale = min(520.0 / max(length, 1.0), 360.0 / max(width, 1.0))
    x0, y0 = 70.0, 105.0
    plate_w, plate_h = length * scale, width * scale
    bolt_circles = []
    for point in layout.get("coordinates_from_plate_centre_mm", []):
        cx = x0 + plate_w / 2.0 + float(point["x"]) * scale
        cy = y0 + plate_h / 2.0 + float(point["y"]) * scale
        bolt_circles.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="9" '
            'fill="#FFFFFF" stroke="#C94B40" stroke-width="4"/>'
        )
    stiffeners = support.get("stiffeners", {})
    stiffener_note = (
        f"{int(stiffeners.get('count', 0))} stiffeners, "
        f"{float(stiffeners.get('provided_thickness_mm', 0) or 0):.0f} mm"
        if stiffeners.get("required")
        else "Stiffeners not required by calculated trigger"
    )
    return "".join([
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 560">',
        '<rect width="1200" height="560" fill="#FFFFFF"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#173C3A}</style>',
        f'<text x="45" y="42" font-size="26" font-weight="700">Base plate {escape(str(support.get("support", "")))} - plan markup</text>',
        f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{plate_w:.1f}" height="{plate_h:.1f}" fill="#EAF2F1" stroke="#173C3A" stroke-width="4"/>',
        f'<rect x="{x0 + plate_w * 0.32:.1f}" y="{y0 + plate_h * 0.30:.1f}" width="{plate_w * 0.36:.1f}" height="{plate_h * 0.40:.1f}" fill="#BFD6D3" stroke="#3E8E89" stroke-width="3"/>',
        *bolt_circles,
        f'<text x="680" y="115" font-size="21" font-weight="700">Plate {length:.0f} x {width:.0f} x {float(plate.get("provided_thickness_mm", 0)):.0f} mm</text>',
        f'<text x="680" y="158" font-size="19">{int(layout.get("bolt_count", 0))} x M{float(layout.get("diameter_mm", 0)):.0f}, holes {float(layout.get("hole_diameter_mm", 0)):.0f} mm</text>',
        f'<text x="680" y="198" font-size="19">Pitch {float(layout.get("pitch_mm", 0)):.0f} mm (min {float(layout.get("minimum_pitch_mm", 0)):.1f})</text>',
        f'<text x="680" y="238" font-size="19">Gauge {float(layout.get("gauge_mm", 0)):.0f} mm (min {float(layout.get("minimum_gauge_mm", 0)):.1f})</text>',
        f'<text x="680" y="278" font-size="19">End/edge {float(layout.get("end_distance_mm", 0)):.0f}/{float(layout.get("edge_distance_mm", 0)):.0f} mm</text>',
        f'<text x="680" y="318" font-size="19">Minimum edge {float(layout.get("minimum_edge_distance_mm", 0)):.1f} mm</text>',
        f'<text x="680" y="366" font-size="19">{escape(stiffener_note)}</text>',
        '<text x="45" y="522" font-size="16" fill="#607472">Calculation-review markup only. Concrete anchor breakout, pull-out and embedment remain INPUT_REQUIRED.</text>',
        '</svg>',
    ])


def _haunch_markup_svg(location: Mapping[str, Any]) -> str:
    connection = location.get("connection", {})
    plate = connection.get("plate", {})
    bolts = connection.get("bolts", {})
    stiffeners = connection.get("stiffeners", {})
    plate_h = float(plate.get("height_mm", 1.0))
    plate_w = float(plate.get("width_mm", 1.0))
    scale = min(360.0 / max(plate_h, 1.0), 300.0 / max(plate_w, 1.0))
    x0, y0 = 190.0, 95.0
    draw_w, draw_h = plate_w * scale, plate_h * scale
    rows = max(int(bolts.get("row_count", 0)), 1)
    pitch = float(bolts.get("pitch_mm", 0.0)) * scale
    gauge = float(bolts.get("gauge_mm", 0.0)) * scale
    centre_x = x0 + draw_w / 2.0
    centre_y = y0 + draw_h / 2.0
    bolt_circles = []
    first_y = centre_y - pitch * (rows - 1) / 2.0
    for row in range(rows):
        for sign in (-1.0, 1.0):
            bolt_circles.append(
                f'<circle cx="{centre_x + sign * gauge / 2.0:.1f}" '
                f'cy="{first_y + row * pitch:.1f}" r="8" '
                'fill="#FFFFFF" stroke="#C94B40" stroke-width="4"/>'
            )
    stiffener_shapes = []
    if stiffeners.get("required"):
        stiffener_shapes = [
            f'<path d="M {x0 - 70:.1f} {centre_y - 60:.1f} L {x0:.1f} {centre_y - 60:.1f} L {x0:.1f} {centre_y - 135:.1f} Z" fill="#F5D9B0" stroke="#C17B00" stroke-width="3"/>',
            f'<path d="M {x0 - 70:.1f} {centre_y + 60:.1f} L {x0:.1f} {centre_y + 60:.1f} L {x0:.1f} {centre_y + 135:.1f} Z" fill="#F5D9B0" stroke="#C17B00" stroke-width="3"/>',
        ]
    return "".join([
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 560">',
        '<rect width="1200" height="560" fill="#FFFFFF"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#173C3A}</style>',
        f'<text x="45" y="42" font-size="26" font-weight="700">{escape(str(location.get("location", "Haunch")))} - end-plate markup</text>',
        f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{draw_w:.1f}" height="{draw_h:.1f}" fill="#EAF2F1" stroke="#173C3A" stroke-width="4"/>',
        f'<path d="M 45 {centre_y:.1f} L {x0:.1f} {centre_y:.1f}" stroke="#173C3A" stroke-width="14"/>',
        *stiffener_shapes,
        *bolt_circles,
        f'<text x="650" y="110" font-size="21" font-weight="700">Plate {plate_h:.0f} x {plate_w:.0f} x {float(plate.get("provided_thickness_mm", 0)):.0f} mm</text>',
        f'<text x="650" y="153" font-size="19">{int(bolts.get("bolt_count", 0))} x M{float(bolts.get("diameter_mm", 0)):.0f}, {rows} rows x 2 columns</text>',
        f'<text x="650" y="193" font-size="19">Pitch {float(bolts.get("pitch_mm", 0)):.0f} mm (min {float(bolts.get("minimum_pitch_mm", 0)):.1f})</text>',
        f'<text x="650" y="233" font-size="19">Gauge {float(bolts.get("gauge_mm", 0)):.0f} mm (min {float(bolts.get("minimum_gauge_mm", 0)):.1f})</text>',
        f'<text x="650" y="273" font-size="19">End/edge {float(bolts.get("end_distance_mm", 0)):.0f}/{float(bolts.get("edge_distance_mm", 0)):.0f} mm</text>',
        f'<text x="650" y="313" font-size="19">Bolt interaction {float(bolts.get("linear_interaction", 0)):.3f} / 1.400</text>',
        f'<text x="650" y="360" font-size="19">Stiffeners: {escape("required" if stiffeners.get("required") else "not required")}</text>',
        (
            f'<text x="650" y="400" font-size="19">{int(stiffeners.get("count", 0))} x '
            f'{float(stiffeners.get("provided_thickness_mm", 0) or 0):.0f} mm, '
            f'{float(stiffeners.get("height_mm", 0)):.0f} x {float(stiffeners.get("length_mm", 0)):.0f} mm</text>'
            if stiffeners.get("required")
            else ""
        ),
        '<text x="45" y="522" font-size="16" fill="#607472">Calculation-review markup only. Prying, weld, stiffener and supporting-member results are in the connection calculation report.</text>',
        '</svg>',
    ])


def write_connection_markup_html(
    result: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Write coordinated fabrication-review connection drawing sheets."""

    from connection_markup import write_connection_markup_html as write_markup

    return write_markup(result, path)
