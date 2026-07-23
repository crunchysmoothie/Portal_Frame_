"""Preliminary main eave-column sizing from truss reactions and wall wind."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

import member_database
from strength_checks import element_properties, member_class_check, member_design


DEFAULT_DATABASE = Path(__file__).with_name("member_database.csv")
MATERIAL = {"fy": 355.0, "E": 200.0, "G": 77.0, "nu": 0.3, "rho": 7.85e-8}


def _ordered_ub_sections(
    database_path: str | Path = DEFAULT_DATABASE,
    section_order: str = "Preferred sections first",
):
    database = member_database.load_member_database(database_path)
    sections = [
        (name, props)
        for name, props in database.get("I-Sections", {}).items()
    ]
    if section_order == "Automatic - lightest passing":
        return sorted(sections, key=lambda item: float(item[1]["m"]))
    return sorted(
        sections,
        key=lambda item: (
            str(item[1].get("Preferred", "No")).strip().lower() != "yes",
            float(item[1]["m"]),
        ),
    )


def _wall_action(
    side: Mapping[str, Any], combination: Mapping[str, Any], key: str
) -> float:
    return sum(
        abs(float(factor))
        * abs(float(side.get("cases", {}).get(case, {}).get(key, 0.0)))
        for case, factor in combination.get("factors", {}).items()
    )


def design_eave_columns(
    geometry,
    uls_results: Mapping[str, Mapping[str, Any]],
    sls_results: Mapping[str, Mapping[str, Any]],
    uls_combinations: list[dict],
    sls_combinations: list[dict],
    wall_actions: Mapping[str, Any],
    building_layout: Mapping[str, Any],
    building_data: Mapping[str, Any],
) -> dict[str, Any]:
    """Select one UB section for all eave columns in the markup layout."""

    height_mm = float(building_data["eaves_height"])
    if height_mm <= 0:
        raise ValueError("Eave-column height must be positive.")
    minor_effective_length_mm = min(
        height_mm, float(building_data.get("girt_max_spacing_mm", height_mm))
    )
    left_support = geometry.left_support
    right_support = geometry.right_support
    combinations = {item["name"]: item for item in uls_combinations}
    sls_by_name = {item["name"]: item for item in sls_combinations}
    deflection_limit_mm = height_mm / 150.0
    column_count = int(building_layout["columns"]["eave_count"])
    rejection_reasons: dict[str, str] = {}

    for section_name, props in _ordered_ub_sections():
        mass_kg_m = float(props["m"])
        self_weight_kn = mass_kg_m * height_mm / 1000.0 * 9.80665 / 1000.0
        strength_checks = []
        candidate_passes = True
        for combination_name, result in uls_results.items():
            combination = combinations[combination_name]
            for side_name, support in (
                ("left", left_support), ("right", right_support)
            ):
                reaction = result["reactions_kn"][support]
                dead_factor = float(combination.get("factors", {}).get("D", 0.0))
                axial_kn = float(reaction["fy"]) + dead_factor * self_weight_kn
                wall_moment_knm = _wall_action(
                    wall_actions[side_name], combination, "base_moment_knm"
                )
                # The 2D truss solver places the whole global horizontal
                # reaction at its one pinned bearing. In the building that
                # action is collected by the marked roof/vertical bracing,
                # not by one eave column acting as an 11 m cantilever.
                top_moment_knm = 0.0
                moment_knm = wall_moment_knm
                omega_1, omega_2 = element_properties(
                    moment_knm, 0.0, moment_knm
                )
                actions = {
                    "Name": f"EAVE-{side_name.upper()}",
                    "kly": minor_effective_length_mm / 1000.0,
                    "klx": 1.2 * height_mm / 1000.0,
                    "kx": 1.2,
                    "lx": height_mm / 1000.0,
                    "ky": 1.0,
                    "ly": minor_effective_length_mm / 1000.0,
                    "type": "eave_column",
                    "section": section_name,
                    "Cu": axial_kn,
                    "Class": member_class_check(axial_kn, props, MATERIAL),
                    "Mx_max": moment_knm,
                    "Mx_top": 0.0,
                    "Mx_bot": moment_knm,
                    "w1": omega_1,
                    "w2": omega_2,
                }
                try:
                    css, oms, ltb = member_design(props, actions, MATERIAL)
                except (ArithmeticError, KeyError, TypeError, ValueError) as exc:
                    candidate_passes = False
                    rejection_reasons[section_name] = f"check error: {exc}"
                    break
                ratios = [float(css), float(oms), float(ltb[0]), float(ltb[1])]
                compression = axial_kn > 1e-9
                slenderness_limit = 200.0 if compression else 300.0
                slenderness = max(
                    actions["klx"] * 1000.0 / float(props["rx"]),
                    actions["kly"] * 1000.0 / float(props["ry"]),
                )
                utilisation = max(*ratios, slenderness / slenderness_limit)
                strength_checks.append({
                    "side": side_name,
                    "combination": combination_name,
                    "axial_kn": axial_kn,
                    "base_moment_knm": moment_knm,
                    "wall_moment_knm": wall_moment_knm,
                    "truss_horizontal_moment_knm": top_moment_knm,
                    "slenderness": slenderness,
                    "slenderness_limit": slenderness_limit,
                    "utilisation": utilisation,
                })
                if not math.isfinite(utilisation) or utilisation > 1.0:
                    candidate_passes = False
                    rejection_reasons[section_name] = (
                        f"strength utilisation {utilisation:.3f} in "
                        f"{combination_name} ({side_name}); axial {axial_kn:.1f} kN, "
                        f"moment {moment_knm:.1f} kNm, slenderness {slenderness:.1f}, "
                        f"component ratios {[round(value, 3) for value in ratios]}"
                    )
                    break
            if not candidate_passes:
                break
        if not candidate_passes:
            continue

        maximum_deflection = 0.0
        deflection_combination = ""
        deflection_side = ""
        elastic_modulus = MATERIAL["E"] * 1000.0
        inertia_mm4 = float(props["Ix"]) * 1e6
        for combination_name, result in sls_results.items():
            combination = sls_by_name[combination_name]
            for side_name, support in (
                ("left", left_support), ("right", right_support)
            ):
                reaction = result["reactions_kn"][support]
                wall_numerator = _wall_action(
                    wall_actions[side_name],
                    combination,
                    "tip_deflection_numerator_kn_mm3",
                )
                top_numerator = 0.0
                deflection_mm = (
                    (wall_numerator + top_numerator) * 1000.0
                    / (elastic_modulus * inertia_mm4)
                )
                if deflection_mm > maximum_deflection:
                    maximum_deflection = deflection_mm
                    deflection_combination = combination_name
                    deflection_side = side_name
        if maximum_deflection > deflection_limit_mm:
            rejection_reasons[section_name] = (
                f"deflection {maximum_deflection:.1f} mm exceeds "
                f"{deflection_limit_mm:.1f} mm"
            )
            continue

        governing = max(strength_checks, key=lambda item: item["utilisation"])
        return {
            "status": "PASS",
            "section_family": "I-Sections",
            "section": section_name,
            "area_mm2": float(props["A"]) * 1000.0,
            "mass_kg_m": mass_kg_m,
            "column_count": column_count,
            "height_mm": height_mm,
            "total_mass_kg": mass_kg_m * height_mm / 1000.0 * column_count,
            "governing_strength": governing,
            "serviceability": {
                "limit": "Eaves height/150",
                "limit_mm": deflection_limit_mm,
                "maximum_horizontal_deflection_mm": maximum_deflection,
                "governing_combination": deflection_combination,
                "governing_side": deflection_side,
                "utilisation": maximum_deflection / deflection_limit_mm,
            },
            "assumptions": [
                "One mass-ordered UB section is used for every main column at the two outer support lines.",
                "Major-axis effective length uses K=1.2 over the full eaves height, consistent with the existing portal-column model.",
                "Minor-axis effective length uses the entered maximum girt spacing; the girts and their restraint connections require separate verification.",
                "Column base moments include wall-wind cantilever action; global truss horizontal reaction is assigned to the marked roof and vertical bracing system.",
                "Base plates, anchors, truss bearings, column splices and connection stiffness are excluded.",
            ],
        }

    reference_reason = (
        list(rejection_reasons.values())[-1]
        if rejection_reasons else "not evaluated"
    )
    raise ValueError(
        "No UB section passes the preliminary eave-column strength and "
        f"height/150 checks. Last check: {reference_reason}."
    )


def design_centre_columns_axial(
    geometry,
    uls_results: Mapping[str, Mapping[str, Any]],
    uls_combinations: list[dict],
    building_layout: Mapping[str, Any],
    truss_data: Mapping[str, Any],
    building_data: Mapping[str, Any],
) -> dict[str, Any]:
    """Preliminary steel centre-column design using axial reactions only."""

    internal_support = str(
        building_layout.get("support_arrangement", {}).get(
            "internal_support", "Not required"
        )
    )
    if internal_support != "Centre columns":
        return {"status": "NOT_REQUIRED", "material": "Steel", "total_mass_kg": 0.0}

    bearing_nodes = list(geometry.bearing_nodes)[1:-1]
    column_count = int(building_layout.get("columns", {}).get("internal_count", 0))
    if not bearing_nodes or column_count <= 0:
        return {"status": "NOT_REQUIRED", "material": "Steel", "total_mass_kg": 0.0}

    height_mm = float(building_data["eaves_height"])
    brace_spacing_mm = float(
        truss_data.get("centre_column_bracing_spacing_mm") or height_mm
    )
    if height_mm <= 0 or brace_spacing_mm <= 0:
        raise ValueError("Centre-column height and bracing spacing must be positive.")
    section_order = str(
        truss_data.get(
            "centre_column_steel_section_order",
            "Automatic - lightest passing",
        )
    )
    combinations = {item["name"]: item for item in uls_combinations}
    rejection_reasons: dict[str, str] = {}

    for section_name, props in _ordered_ub_sections(section_order=section_order):
        mass_kg_m = float(props["m"])
        self_weight_kn = mass_kg_m * height_mm / 1000.0 * 9.80665 / 1000.0
        checks: list[dict[str, Any]] = []
        candidate_passes = True
        for combination_name, result in uls_results.items():
            combination = combinations[combination_name]
            dead_factor = float(combination.get("factors", {}).get("D", 0.0))
            for bearing_node in bearing_nodes:
                reaction = result["reactions_kn"][bearing_node]
                axial_kn = float(reaction.get("fy", 0.0)) + dead_factor * self_weight_kn
                actions = {
                    "Name": f"CENTRE-{bearing_node}",
                    "kly": brace_spacing_mm / 1000.0,
                    "klx": height_mm / 1000.0,
                    "kx": 1.0,
                    "lx": height_mm / 1000.0,
                    "ky": 1.0,
                    "ly": brace_spacing_mm / 1000.0,
                    "type": "centre_column_axial",
                    "section": section_name,
                    "Cu": axial_kn,
                    "Class": member_class_check(axial_kn, props, MATERIAL),
                    "Mx_max": 0.0,
                    "Mx_top": 0.0,
                    "Mx_bot": 0.0,
                    "w1": 1.0,
                    "w2": 1.0,
                }
                try:
                    css, oms, ltb = member_design(props, actions, MATERIAL)
                except (ArithmeticError, KeyError, TypeError, ValueError) as exc:
                    candidate_passes = False
                    rejection_reasons[section_name] = f"check error: {exc}"
                    break
                slenderness = max(
                    actions["klx"] * 1000.0 / float(props["rx"]),
                    actions["kly"] * 1000.0 / float(props["ry"]),
                )
                slenderness_limit = 200.0 if axial_kn >= 0.0 else 300.0
                utilisation = max(
                    float(css), float(oms), float(ltb[0]), float(ltb[1]),
                    slenderness / slenderness_limit,
                )
                checks.append({
                    "bearing_node": bearing_node,
                    "combination": combination_name,
                    "axial_kn": axial_kn,
                    "slenderness": slenderness,
                    "slenderness_limit": slenderness_limit,
                    "utilisation": utilisation,
                })
                if not math.isfinite(utilisation) or utilisation > 1.0:
                    candidate_passes = False
                    rejection_reasons[section_name] = (
                        f"axial utilisation {utilisation:.3f} in "
                        f"{combination_name} ({bearing_node}); "
                        f"axial {axial_kn:.1f} kN, slenderness {slenderness:.1f}"
                    )
                    break
            if not candidate_passes:
                break
        if candidate_passes:
            governing = max(checks, key=lambda item: item["utilisation"])
            return {
                "status": "PASS",
                "material": "Steel",
                "section_family": "I-Sections",
                "section": section_name,
                "area_mm2": float(props["A"]) * 1000.0,
                "mass_kg_m": mass_kg_m,
                "column_count": column_count,
                "height_mm": height_mm,
                "bracing_spacing_mm": brace_spacing_mm,
                "total_mass_kg": mass_kg_m * height_mm / 1000.0 * column_count,
                "governing_strength": {
                    **governing,
                    "check": "axial strength and slenderness",
                },
                "section_order": section_order,
                "assumptions": [
                    "All centre columns use one common UB section and are checked for axial force only (compression and uplift tension; no bending).",
                    "Major-axis effective length is the full eaves height; minor-axis effective length is the entered centre-column brace spacing.",
                    "Centre-column actions are the factored vertical reactions at the internal bearing nodes; wall wind moments are excluded.",
                    "Base plates, anchors, panel joints, lifting inserts and tilt-up stability during erection are excluded.",
                ],
            }

    reference_reason = list(rejection_reasons.values())[-1] if rejection_reasons else "not evaluated"
    raise ValueError(
        "No UB section passes the preliminary axial centre-column checks. "
        f"Last check: {reference_reason}."
    )


def describe_concrete_centre_columns(
    building_layout: Mapping[str, Any], truss_data: Mapping[str, Any], building_data: Mapping[str, Any]
) -> dict[str, Any]:
    """Capture concrete tilt-up inputs without presenting an unverified capacity check."""

    column_count = int(building_layout.get("columns", {}).get("internal_count", 0))
    height_mm = float(building_data.get("eaves_height", 0.0))
    width_mm = float(truss_data.get("centre_column_concrete_width_mm", 0.0))
    thickness_mm = float(truss_data.get("centre_column_concrete_thickness_mm", 0.0))
    return {
        "status": "HOLD_POINT",
        "material": "Concrete tilt-up",
        "column_count": column_count,
        "height_mm": height_mm,
        "width_mm": width_mm,
        "thickness_mm": thickness_mm,
        "bracing_spacing_mm": float(
            truss_data.get("centre_column_concrete_bracing_spacing_mm", 0.0)
        ),
        "fck_mpa": float(truss_data.get("centre_column_concrete_fck_mpa", 0.0)),
        "rebar_area_mm2": float(truss_data.get("centre_column_concrete_rebar_area_mm2", 0.0)),
        "total_mass_kg": 0.0,
        "assumptions": [
            "Concrete tilt-up centre-column inputs are recorded, but no concrete axial resistance is reported until the concrete design standard, reinforcement layout and erection/bracing basis are confirmed.",
            "Centre columns remain axial-only in the truss model; wall wind moments are excluded.",
        ],
    }
