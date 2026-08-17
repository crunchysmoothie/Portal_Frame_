"""Adapters from the truss result to shared connections/foundations/BOQs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def _combination_rows(
    best: Mapping[str, Any],
    reaction_key: str,
    combinations: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    reactions_by_combination = best.get(reaction_key, {})
    geometry = best.get("geometry", {})
    supports = list(geometry.get("support_nodes", []))
    if len(supports) < 2:
        return []
    left_support, right_support = str(supports[0]), str(supports[-1])
    wall_actions = (
        best.get("load_audit", {}).get("eave_column_wall_actions", {})
    )
    eave_column = best.get("eave_column_design", {})
    column_weight_kn = (
        float(eave_column.get("mass_kg_m", 0.0))
        * float(eave_column.get("height_mm", 0.0))
        / 1000.0
        * 9.80665
        / 1000.0
    )
    rows: list[dict[str, Any]] = []
    for combination in combinations:
        name = str(combination.get("name", ""))
        result = reactions_by_combination.get(name, {})
        factors = combination.get("factors", {})
        dead_factor = float(factors.get("D", 0.0) or 0.0)
        for side, support, base_node in (
            ("left", left_support, "BASE_LEFT"),
            ("right", right_support, "BASE_RIGHT"),
        ):
            reaction = result.get(support, {})
            side_cases = wall_actions.get(side, {}).get("cases", {})
            wall_force = sum(
                float(factor) * float(side_cases.get(case, {}).get("resultant_kn", 0.0))
                for case, factor in factors.items()
            )
            wall_moment = sum(
                float(factor) * float(side_cases.get(case, {}).get("base_moment_knm", 0.0))
                for case, factor in factors.items()
            )
            rows.append({
                "node": base_node,
                "load_combination": name,
                "fx": -wall_force,
                "fy": float(reaction.get("fy", 0.0)) + dead_factor * column_weight_kn,
                "mz": -wall_moment,
                "source": "Truss bearing reaction plus eave-column wall action and self-weight",
            })
    return rows


def _characteristic_rows(best: Mapping[str, Any]) -> list[dict[str, Any]]:
    reactions_by_case = best.get("support_reactions_characteristic_kn", {})
    geometry = best.get("geometry", {})
    supports = list(geometry.get("support_nodes", []))
    if len(supports) < 2:
        return []
    left_support, right_support = str(supports[0]), str(supports[-1])
    wall_actions = (
        best.get("load_audit", {}).get("eave_column_wall_actions", {})
    )
    eave_column = best.get("eave_column_design", {})
    column_weight_kn = (
        float(eave_column.get("mass_kg_m", 0.0))
        * float(eave_column.get("height_mm", 0.0))
        / 1000.0
        * 9.80665
        / 1000.0
    )
    case_names = set(reactions_by_case)
    for side in ("left", "right"):
        case_names.update(wall_actions.get(side, {}).get("cases", {}))
    rows: list[dict[str, Any]] = []
    for case in sorted(case_names):
        result = reactions_by_case.get(case, {})
        for side, support, base_node in (
            ("left", left_support, "BASE_LEFT"),
            ("right", right_support, "BASE_RIGHT"),
        ):
            reaction = result.get(support, {})
            wall_case = wall_actions.get(side, {}).get("cases", {}).get(case, {})
            rows.append({
                "node": base_node,
                "load_combination": case,
                "fx": -float(wall_case.get("resultant_kn", 0.0)),
                "fy": float(reaction.get("fy", 0.0)) + (
                    column_weight_kn if case == "D" else 0.0
                ),
                "mz": -float(wall_case.get("base_moment_knm", 0.0)),
                "source": "Factor-1.0 truss and eave-column characteristic action",
            })
    return rows


def _append_centre_column_rows(
    rows: list[dict[str, Any]],
    best: Mapping[str, Any],
    reaction_key: str,
    combinations: list[Mapping[str, Any]],
) -> None:
    layout = best.get("building_layout", {})
    if (
        layout.get("support_arrangement", {}).get("internal_support")
        != "Centre columns"
        or best.get("centre_column_design", {}).get("status") != "PASS"
    ):
        return
    support_nodes = list(best.get("geometry", {}).get("support_nodes", []))[1:-1]
    centre = best.get("centre_column_design", {})
    column_weight_kn = (
        float(centre.get("mass_kg_m", 0.0))
        * float(centre.get("height_mm", 0.0))
        / 1000.0
        * 9.80665
        / 1000.0
    )
    reactions_by_combination = best.get(reaction_key, {})
    for combination in combinations:
        name = str(combination.get("name", ""))
        factors = combination.get("factors", {})
        dead_factor = float(factors.get("D", 0.0) or 0.0)
        result = reactions_by_combination.get(name, {})
        for index, support in enumerate(support_nodes, 1):
            reaction = result.get(str(support), {})
            rows.append({
                "node": f"BASE_CENTRE_{index}",
                "load_combination": name,
                "fx": 0.0,
                "fy": float(reaction.get("fy", 0.0)) + dead_factor * column_weight_kn,
                "mz": 0.0,
                "source": "Internal truss-bearing reaction plus centre-column self-weight",
            })


def _append_centre_characteristic_rows(
    rows: list[dict[str, Any]], best: Mapping[str, Any]
) -> None:
    layout = best.get("building_layout", {})
    if (
        layout.get("support_arrangement", {}).get("internal_support")
        != "Centre columns"
        or best.get("centre_column_design", {}).get("status") != "PASS"
    ):
        return
    support_nodes = list(best.get("geometry", {}).get("support_nodes", []))[1:-1]
    centre = best.get("centre_column_design", {})
    column_weight_kn = (
        float(centre.get("mass_kg_m", 0.0))
        * float(centre.get("height_mm", 0.0))
        / 1000.0
        * 9.80665
        / 1000.0
    )
    for case, result in best.get("support_reactions_characteristic_kn", {}).items():
        for index, support in enumerate(support_nodes, 1):
            reaction = result.get(str(support), {})
            rows.append({
                "node": f"BASE_CENTRE_{index}",
                "load_combination": str(case),
                "fx": 0.0,
                "fy": float(reaction.get("fy", 0.0)) + (
                    column_weight_kn if str(case) == "D" else 0.0
                ),
                "mz": 0.0,
                "source": "Factor-1.0 internal truss-bearing and centre-column action",
            })


def build_truss_analysis_snapshot(
    result: Mapping[str, Any],
    payload: Mapping[str, Any],
    analysis_id: str,
) -> dict[str, Any]:
    """Build the shared downstream-result contract for a completed truss."""

    ranked = list(result.get("ranked_solutions", []))
    if not ranked:
        raise ValueError("The truss result does not contain a ranked solution.")
    best = ranked[0]
    audit = best.get("load_audit", {})
    uls_combinations = list(audit.get("uls_combinations", []))
    sls_combinations = list(audit.get("sls_combinations", []))
    reactions = _combination_rows(
        best, "support_reactions_uls_kn", uls_combinations
    )
    reactions.extend(_combination_rows(
        best, "support_reactions_sls_kn", sls_combinations
    ))
    _append_centre_column_rows(
        reactions, best, "support_reactions_uls_kn", uls_combinations
    )
    _append_centre_column_rows(
        reactions, best, "support_reactions_sls_kn", sls_combinations
    )
    characteristic = _characteristic_rows(best)
    _append_centre_characteristic_rows(characteristic, best)

    project_meta = dict(payload.get("project", {}))
    building = dict(payload.get("building_data", {}))
    truss_data = dict(payload.get("truss_data", {}))
    geometry = dict(best.get("geometry", {}))
    layout = dict(best.get("building_layout", {}))
    eave = dict(best.get("eave_column_design", {}))
    centre = dict(best.get("centre_column_design", {}))
    support_sections = {
        "BASE_LEFT": str(eave.get("section", "")),
        "BASE_RIGHT": str(eave.get("section", "")),
    }
    support_quantities = {
        "BASE_LEFT": int(best.get("truss_count", 0) or 0),
        "BASE_RIGHT": int(best.get("truss_count", 0) or 0),
    }
    if centre.get("status") == "PASS":
        internal_nodes = list(geometry.get("support_nodes", []))[1:-1]
        for index, _ in enumerate(internal_nodes, 1):
            support_sections[f"BASE_CENTRE_{index}"] = str(centre.get("section", ""))
            support_quantities[f"BASE_CENTRE_{index}"] = int(
                best.get("truss_count", 0) or 0
            )

    roof_rise = float(geometry.get("roof_rise_mm", 0.0))
    eaves_height = float(building.get("eaves_height", 0.0))
    project = {
        "project_name": str(
            project_meta.get("project_name", project_meta.get("name", "Untitled project"))
        ),
        "project_number": str(
            project_meta.get("project_number", project_meta.get("number", ""))
        ),
        "designer": str(project_meta.get("designer", "")),
        "structural_system": "Truss",
        "building_type": str(building.get("building_type", "Normal")),
        "roof_type": str(building.get("building_roof", "")),
        "building_length_mm": float(building.get("building_length", 0.0)),
        "gable_width_mm": float(geometry.get("span_mm", 0.0)),
        "eaves_height_mm": eaves_height,
        "apex_height_mm": eaves_height + roof_rise,
        "rafter_spacing_mm": float(building.get("rafter_spacing", 0.0)),
        "purlin_section": str(building.get("purlin_section", "")),
        "girt_section": str(building.get("girt_section", "")),
        "girt_max_spacing_mm": float(building.get("girt_max_spacing_mm", 0.0)),
        "column_section": str(eave.get("section", "")),
        "rafter_section": "Not applicable - truss angles",
        "steel_grade": "Steel_S355",
        "use_eaves_haunch": "No",
        "use_apex_haunch": "No",
        "wall_openings_m2": dict(building.get("opening_areas_m2", {})),
    }
    for key, value in building.items():
        if "opening" in str(key).lower():
            project[str(key)] = value

    return {
        "schema_version": 1,
        "analysis": {
            "analysis_id": str(analysis_id),
            "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
            "structural_system": "Truss",
        },
        "input_data": {
            "load_combinations": uls_combinations,
            "serviceability_load_combinations": sls_combinations,
            "frame_data": [{
                "column_section": str(eave.get("section", "")),
                "use_eaves_haunch": "No",
                "use_apex_haunch": "No",
                "building_roof": str(building.get("building_roof", "")),
            }],
            "truss_data": truss_data,
        },
        "results": {
            "project": project,
            "reactions": reactions,
            "foundation_characteristic_reactions": characteristic,
            "support_sections": support_sections,
            "foundation_support_quantities": support_quantities,
            "frame_summary": {
                "steel_mass_breakdown": {
                    "portal_frames": {"quantity": int(best.get("truss_count", 0) or 0)}
                }
            },
            "bracing_design": dict(result.get("bracing_design", {})),
            "truss_design": dict(result),
            "truss_layout": layout,
        },
    }
