"""Shared PortalFrame loading converted to truss panel-point actions."""

from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import user_input
from truss_model import PrattTrussGeometry


EXTRA_PERMANENT_LOAD_KEYS = (
    "services_load_kpa",
    "ceiling_load_kpa",
    "solar_load_kpa",
    "fire_load_kpa",
    "hvac_load_kpa",
)


def _add_node_load(
    cases: dict[str, dict[str, list[float]]],
    case: str,
    node_name: str,
    fx_kn: float,
    fy_kn: float,
) -> None:
    components = cases.setdefault(case, {}).setdefault(node_name, [0.0, 0.0])
    components[0] += float(fx_kn)
    components[1] += float(fy_kn)


def _source_portal_data(
    building_data: Mapping[str, Any],
    wind_data: Mapping[str, Any],
    geometry: PrattTrussGeometry,
) -> dict[str, Any]:
    """Generate the existing portal loading model for the candidate roof pitch."""

    configured = deepcopy(dict(building_data))
    configured["building_roof"] = geometry.roof_form
    configured["gable_width"] = geometry.span_mm
    configured["apex_height"] = (
        float(configured["eaves_height"]) + geometry.roof_rise_mm
    )
    roof_run_mm = (
        geometry.span_mm / 2.0
        if geometry.roof_form == "Duo Pitched"
        else geometry.span_mm
    )
    configured["roof_pitch"] = math.degrees(
        math.atan2(geometry.roof_rise_mm, roof_run_mm)
    )
    # Crawl-beam actions need a dedicated truss-node placement workflow and are
    # deliberately excluded from this preliminary iteration.
    configured["use_crawl_beams"] = "No"
    configured["crawl_beams"] = []

    with TemporaryDirectory(prefix="portalframe-truss-loads-") as directory:
        path = Path(directory) / "source_portal.json"
        with redirect_stdout(StringIO()):
            user_input.update_json_file(path, configured, dict(wind_data))
            user_input.add_wind_member_loads(path)
            user_input.add_live_loads(path)
            user_input.add_dead_loads(path)
        return json.loads(path.read_text(encoding="utf-8"))


def _source_rafter_at_x(source: Mapping[str, Any], x_mm: float) -> tuple[dict, float]:
    nodes = {node["name"]: node for node in source["nodes"]}
    candidates = []
    for member in source["members"]:
        if str(member.get("type", "")).lower() != "rafter":
            continue
        i_node = nodes[member["i_node"]]
        j_node = nodes[member["j_node"]]
        low, high = sorted((float(i_node["x"]), float(j_node["x"])))
        if low - 1e-6 <= x_mm <= high + 1e-6:
            width = float(j_node["x"]) - float(i_node["x"])
            if abs(width) <= 1e-9:
                continue
            fraction = (x_mm - float(i_node["x"])) / width
            local_mm = max(0.0, min(1.0, fraction)) * float(member["length"])
            candidates.append((member, local_mm, high - low))
    if not candidates:
        raise ValueError(f"No source portal rafter contains roof position x={x_mm:.3f} mm.")
    member, local_mm, _ = min(candidates, key=lambda item: item[2])
    return member, local_mm


def _consistent_segment_loads(
    loads: list[dict],
    segment_start_mm: float,
    segment_end_mm: float,
    member_length_mm: float,
) -> list[tuple[dict, float, float]]:
    """Integrate piecewise-linear line loads to the two truss panel nodes."""

    if abs(segment_end_mm - segment_start_mm) <= 1e-9:
        return []
    segment_low, segment_high = sorted((segment_start_mm, segment_end_mm))
    integrated = []
    for load in loads:
        start = float(load.get("x1", 0.0) or 0.0)
        end = float(load.get("x2", member_length_mm) or member_length_mm)
        if end < start:
            start, end = end, start
        overlap_start = max(segment_low, start)
        overlap_end = min(segment_high, end)
        if overlap_end - overlap_start <= 1e-9:
            continue

        w1 = float(load["w1"])
        w2 = float(load["w2"])

        def values(local_mm: float) -> tuple[float, float, float]:
            load_fraction = 0.0 if end <= start else (local_mm - start) / (end - start)
            intensity = w1 + (w2 - w1) * load_fraction
            node_j_fraction = (
                (local_mm - segment_start_mm)
                / (segment_end_mm - segment_start_mm)
            )
            return intensity, 1.0 - node_j_fraction, node_j_fraction

        midpoint = (overlap_start + overlap_end) / 2.0
        start_values = values(overlap_start)
        midpoint_values = values(midpoint)
        end_values = values(overlap_end)
        width = overlap_end - overlap_start
        # Simpson integration is exact here because intensity and the element
        # shape functions are both linear over each source-load interval.
        i_force = width / 6.0 * (
            start_values[0] * start_values[1]
            + 4.0 * midpoint_values[0] * midpoint_values[1]
            + end_values[0] * end_values[1]
        )
        j_force = width / 6.0 * (
            start_values[0] * start_values[2]
            + 4.0 * midpoint_values[0] * midpoint_values[2]
            + end_values[0] * end_values[2]
        )
        integrated.append((load, i_force, j_force))
    return integrated


def _eave_column_wall_actions(source: Mapping[str, Any]) -> dict[str, Any]:
    """Integrate source-portal wall loads for provisional eave-column design."""

    nodes = {node["name"]: node for node in source["nodes"]}
    columns = [
        member for member in source["members"]
        if str(member.get("type", "")).lower() == "column"
    ]
    columns.sort(
        key=lambda member: (
            float(nodes[member["i_node"]]["x"])
            + float(nodes[member["j_node"]]["x"])
        ) / 2.0
    )
    if len(columns) != 2:
        raise ValueError("The source portal must contain two eave columns.")

    by_member: dict[str, list[dict]] = {}
    for load in source.get("member_loads", []):
        if str(load.get("direction", "")).lower() == "fy":
            by_member.setdefault(load["member"], []).append(load)

    result = {}
    for side, member in zip(("left", "right"), columns):
        i_node = nodes[member["i_node"]]
        j_node = nodes[member["j_node"]]
        dx = float(j_node["x"]) - float(i_node["x"])
        dy = float(j_node["y"]) - float(i_node["y"])
        length_mm = math.hypot(dx, dy)
        i_is_base = float(i_node["y"]) <= float(j_node["y"])
        cases: dict[str, dict[str, float]] = {}
        for load in by_member.get(member["name"], []):
            start = float(load.get("x1", 0.0) or 0.0)
            end = float(load.get("x2", length_mm) or length_mm)
            start = max(0.0, min(length_mm, start))
            end = max(0.0, min(length_mm, end))
            if end < start:
                start, end = end, start
            if end - start <= 1e-9:
                continue
            w1 = float(load["w1"])
            w2 = float(load["w2"])

            def integrands(local_mm: float) -> tuple[float, float, float]:
                fraction = (local_mm - start) / (end - start)
                intensity = w1 + (w2 - w1) * fraction
                height = local_mm if i_is_base else length_mm - local_mm
                base_moment = intensity * height
                tip_numerator = (
                    intensity * height ** 2 * (3.0 * length_mm - height) / 6.0
                )
                return intensity, base_moment, tip_numerator

            midpoint = (start + end) / 2.0
            first = integrands(start)
            middle = integrands(midpoint)
            last = integrands(end)
            width = end - start
            integrated = [
                width / 6.0 * (first[index] + 4.0 * middle[index] + last[index])
                for index in range(3)
            ]
            case = cases.setdefault(load["case"], {
                "resultant_kn": 0.0,
                "base_moment_knm": 0.0,
                "tip_deflection_numerator_kn_mm3": 0.0,
            })
            case["resultant_kn"] += integrated[0]
            case["base_moment_knm"] += integrated[1] / 1000.0
            case["tip_deflection_numerator_kn_mm3"] += integrated[2]
        result[side] = {
            "source_member": member["name"],
            "height_mm": length_mm,
            "cases": cases,
        }
    return result


def build_panel_point_loads(
    building_data: Mapping[str, Any],
    wind_data: Mapping[str, Any],
    truss_data: Mapping[str, Any],
    geometry: PrattTrussGeometry,
) -> dict[str, Any]:
    """Return characteristic nodal load cases and existing SANS combinations."""

    source = _source_portal_data(building_data, wind_data, geometry)
    source_loads: dict[str, dict[str, list[dict]]] = {}
    for load in source.get("member_loads", []):
        source_loads.setdefault(load["member"], {}).setdefault(load["case"], []).append(load)

    nodes = {node.name: node for node in geometry.nodes}
    source_nodes = {node["name"]: node for node in source["nodes"]}
    cases: dict[str, dict[str, list[float]]] = {}
    top_members = [
        member for member in geometry.members if member.role == "top_chord"
    ]
    for member in top_members:
        i_node = nodes[member.i_node]
        j_node = nodes[member.j_node]
        midpoint_x = (i_node.x_mm + j_node.x_mm) / 2.0
        source_member, _ = _source_rafter_at_x(source, midpoint_x)
        source_i = source_nodes[source_member["i_node"]]
        source_j = source_nodes[source_member["j_node"]]
        source_dx = float(source_j["x"]) - float(source_i["x"])
        source_dy = float(source_j["y"]) - float(source_i["y"])
        source_length = float(source_member["length"])
        if abs(source_dx) <= 1e-9 or source_length <= 0:
            raise ValueError(f"Source rafter {source_member['name']} has invalid geometry.")
        local_i = (
            (i_node.x_mm - float(source_i["x"])) / source_dx * source_length
        )
        local_j = (
            (j_node.x_mm - float(source_i["x"])) / source_dx * source_length
        )
        loads_by_case = source_loads.get(source_member["name"], {})
        for case, loads in loads_by_case.items():
            for load, i_force_kn, j_force_kn in _consistent_segment_loads(
                loads, local_i, local_j, source_length
            ):
                if str(load["direction"]) == "FY":
                    i_fx_kn, i_fy_kn = 0.0, i_force_kn
                    j_fx_kn, j_fy_kn = 0.0, j_force_kn
                else:
                    # Existing roof wind loads use source-member local Fy.
                    normal_x = -source_dy / source_length
                    normal_y = source_dx / source_length
                    i_fx_kn, i_fy_kn = i_force_kn * normal_x, i_force_kn * normal_y
                    j_fx_kn, j_fy_kn = j_force_kn * normal_x, j_force_kn * normal_y
                _add_node_load(cases, case, member.i_node, i_fx_kn, i_fy_kn)
                _add_node_load(cases, case, member.j_node, j_fx_kn, j_fy_kn)

    extra_kpa = sum(float(truss_data.get(key, 0.0) or 0.0) for key in EXTRA_PERMANENT_LOAD_KEYS)
    spacing_m = float(building_data["rafter_spacing"]) / 1000.0
    if extra_kpa > 0:
        vertical_line_kn_m = extra_kpa * spacing_m
        for member in top_members:
            i_node = nodes[member.i_node]
            j_node = nodes[member.j_node]
            total_kn = -vertical_line_kn_m * abs(j_node.x_mm - i_node.x_mm) / 1000.0
            for case in ("D_MAX", "D_MIN"):
                _add_node_load(cases, case, member.i_node, 0.0, total_kn / 2.0)
                _add_node_load(cases, case, member.j_node, 0.0, total_kn / 2.0)

    return {
        "cases": {
            case: {node: tuple(components) for node, components in loads.items()}
            for case, loads in cases.items()
        },
        "uls_combinations": list(source["load_combinations"]),
        "sls_combinations": list(source["serviceability_load_combinations"]),
        "source": {
            "engine": "PortalFrame user_input + generate_wind_loading",
            "load_standard": building_data.get("load_combination_standard", ""),
            "candidate_roof_pitch_deg": float(source["frame_data"][0]["roof_pitch"]),
            "base_dead_load_max_kpa": 0.35,
            "base_dead_load_min_kpa": 0.25,
            "roof_imposed_load_kpa": 0.25,
            "extra_permanent_load_kpa": extra_kpa,
            "purlins_at_panel_points": True,
        },
        "eave_column_wall_actions": _eave_column_wall_actions(source),
    }


def with_self_weight(
    base_cases: Mapping[str, Mapping[str, tuple[float, float]]],
    geometry: PrattTrussGeometry,
    member_masses_kg_m: Mapping[str, float],
) -> dict[str, dict[str, tuple[float, float]]]:
    """Add member self-weight to case D, shared equally by member end nodes."""

    cases = {
        case: {node: [float(value[0]), float(value[1])] for node, value in loads.items()}
        for case, loads in base_cases.items()
    }
    nodes = {node.name: node for node in geometry.nodes}
    for member in geometry.members:
        i_node = nodes[member.i_node]
        j_node = nodes[member.j_node]
        length_m = math.hypot(j_node.x_mm - i_node.x_mm, j_node.y_mm - i_node.y_mm) / 1000.0
        weight_kn = float(member_masses_kg_m[member.name]) * length_m * 9.80665 / 1000.0
        _add_node_load(cases, "D", member.i_node, 0.0, -weight_kn / 2.0)
        _add_node_load(cases, "D", member.j_node, 0.0, -weight_kn / 2.0)
    return {
        case: {node: tuple(components) for node, components in loads.items()}
        for case, loads in cases.items()
    }


def factored_node_loads(
    cases: Mapping[str, Mapping[str, tuple[float, float]]],
    combination: Mapping[str, Any],
) -> dict[str, tuple[float, float]]:
    """Combine characteristic nodal actions using the supplied factors."""

    factored: dict[str, list[float]] = {}
    for case, factor in combination.get("factors", {}).items():
        for node, components in cases.get(case, {}).items():
            target = factored.setdefault(node, [0.0, 0.0])
            target[0] += float(factor) * float(components[0])
            target[1] += float(factor) * float(components[1])
    return {node: tuple(components) for node, components in factored.items()}
