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

from portal_workflow import inputs as user_input
from .model import PrattTrussGeometry
from portal_workflow.wind import (
    calculate_basic_wind_speed,
    calculate_peak_wind_pressure,
    calculate_terrain_roughness,
)


EXTRA_PERMANENT_LOAD_KEYS = (
    "services_load_kpa",
    "ceiling_load_kpa",
    "solar_load_kpa",
    "fire_load_kpa",
    "hvac_load_kpa",
)
MINIMUM_PERMANENT_LOAD_KEYS = (
    "ceiling_load_kpa",
    "fire_load_kpa",
    "hvac_load_kpa",
)
WIND_ZONE_TABLES = (
    ("wind_zones_0U", "Wind 0 degrees - upward"),
    ("wind_zones_0D", "Wind 0 degrees - downward"),
    ("wind_zones_0M1", "Wind 0 degrees - arrangement M1"),
    ("wind_zones_0M2", "Wind 0 degrees - arrangement M2"),
    ("wind_zones_90", "Wind 90 degrees"),
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


def build_source_portal_data(
    building_data: Mapping[str, Any],
    wind_data: Mapping[str, Any],
    geometry: PrattTrussGeometry,
) -> dict[str, Any]:
    """Return the generated portal-format loading model used by a truss design."""

    return _source_portal_data(building_data, wind_data, geometry)


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
    *,
    shape_start: float = 0.0,
    shape_end: float = 1.0,
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
            overlap_fraction = (
                (local_mm - segment_start_mm)
                / (segment_end_mm - segment_start_mm)
            )
            node_j_fraction = (
                shape_start
                + (shape_end - shape_start) * overlap_fraction
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
    column_members = [
        member for member in source["members"]
        if str(member.get("type", "")).lower() == "column"
    ]
    columns_by_x: dict[float, list[dict[str, Any]]] = {}
    for member in column_members:
        centre_x = round(
            (
            float(nodes[member["i_node"]]["x"])
            + float(nodes[member["j_node"]]["x"])
            )
            / 2.0,
            6,
        )
        columns_by_x.setdefault(centre_x, []).append(member)
    column_lines = sorted(columns_by_x.items())
    if len(column_lines) != 2:
        raise ValueError(
            "The source portal must contain two eave column lines."
        )

    by_member: dict[str, list[dict]] = {}
    for load in source.get("member_loads", []):
        if str(load.get("direction", "")).lower() == "fy":
            by_member.setdefault(load["member"], []).append(load)

    result = {}
    for side, (_, members) in zip(("left", "right"), column_lines):
        member_nodes = [
            nodes[node_name]
            for member in members
            for node_name in (member["i_node"], member["j_node"])
        ]
        base_y = min(float(node["y"]) for node in member_nodes)
        top_y = max(float(node["y"]) for node in member_nodes)
        height_mm = top_y - base_y
        if height_mm <= 0.0:
            raise ValueError(f"The source portal {side} eave column has no height.")
        cases: dict[str, dict[str, float]] = {}
        for member in members:
            i_node = nodes[member["i_node"]]
            j_node = nodes[member["j_node"]]
            dx = float(j_node["x"]) - float(i_node["x"])
            dy = float(j_node["y"]) - float(i_node["y"])
            member_length_mm = math.hypot(dx, dy)
            if member_length_mm <= 0.0:
                raise ValueError(
                    f"Source column member {member['name']} has no length."
                )
            vertical_direction = dy / member_length_mm
            for load in by_member.get(member["name"], []):
                start = float(load.get("x1", 0.0) or 0.0)
                end = float(
                    load.get("x2", member_length_mm) or member_length_mm
                )
                start = max(0.0, min(member_length_mm, start))
                end = max(0.0, min(member_length_mm, end))
                if end < start:
                    start, end = end, start
                if end - start <= 1e-9:
                    continue
                w1 = float(load["w1"])
                w2 = float(load["w2"])

                def integrands(
                    local_mm: float,
                ) -> tuple[float, float, float]:
                    fraction = (local_mm - start) / (end - start)
                    intensity = w1 + (w2 - w1) * fraction
                    load_height = (
                        float(i_node["y"])
                        + vertical_direction * local_mm
                        - base_y
                    )
                    base_moment = intensity * load_height
                    tip_numerator = (
                        intensity
                        * load_height ** 2
                        * (3.0 * height_mm - load_height)
                        / 6.0
                    )
                    return intensity, base_moment, tip_numerator

                midpoint = (start + end) / 2.0
                first = integrands(start)
                middle = integrands(midpoint)
                last = integrands(end)
                width = end - start
                integrated = [
                    width
                    / 6.0
                    * (first[index] + 4.0 * middle[index] + last[index])
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
            "source_member": ", ".join(
                str(member["name"]) for member in members
            ),
            "source_members": [
                str(member["name"]) for member in members
            ],
            "height_mm": height_mm,
            "cases": cases,
        }
    return result


def _eave_column_member_loads(source: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return characteristic wall-load segments on the two source eave columns."""

    nodes = {node["name"]: node for node in source["nodes"]}
    column_members = [
        member for member in source["members"]
        if str(member.get("type", "")).lower() == "column"
    ]
    columns_by_x: dict[float, list[dict[str, Any]]] = {}
    for member in column_members:
        centre_x = round(
            (float(nodes[member["i_node"]]["x"]) + float(nodes[member["j_node"]]["x"])) / 2.0,
            6,
        )
        columns_by_x.setdefault(centre_x, []).append(member)
    column_lines = sorted(columns_by_x.items())
    if len(column_lines) != 2:
        raise ValueError("The source portal must contain two eave column lines.")
    loads_by_member: dict[str, list[dict[str, Any]]] = {}
    for load in source.get("member_loads", []):
        if str(load.get("direction", "")).lower() == "fy":
            loads_by_member.setdefault(str(load["member"]), []).append(load)
    result: dict[str, list[dict[str, Any]]] = {}
    for side, (_, members) in zip(("left", "right"), column_lines):
        base_y = min(
            float(nodes[node_name]["y"])
            for member in members
            for node_name in (member["i_node"], member["j_node"])
        )
        segments = []
        for member in members:
            i_node, j_node = nodes[member["i_node"]], nodes[member["j_node"]]
            dx = float(j_node["x"]) - float(i_node["x"])
            dy = float(j_node["y"]) - float(i_node["y"])
            length_mm = math.hypot(dx, dy)
            if length_mm <= 0.0:
                continue
            for load in loads_by_member.get(str(member["name"]), []):
                x1 = float(load.get("x1", 0.0) or 0.0)
                x2 = float(load.get("x2", length_mm) or length_mm)
                y1 = float(i_node["y"]) + dy * x1 / length_mm
                y2 = float(i_node["y"]) + dy * x2 / length_mm
                w1 = float(load["w1"]) * 1000.0
                w2 = float(load["w2"]) * 1000.0
                if y2 < y1:
                    y1, y2 = y2, y1
                    w1, w2 = w2, w1
                segments.append({
                    "case": str(load["case"]),
                    "start_m": (y1 - base_y) / 1000.0,
                    "length_m": (y2 - y1) / 1000.0,
                    "w1_kn_m": w1,
                    "w2_kn_m": w2,
                })
        result[side] = segments
    return result


def build_panel_point_loads(
    building_data: Mapping[str, Any],
    wind_data: Mapping[str, Any],
    truss_data: Mapping[str, Any],
    geometry: PrattTrussGeometry,
) -> dict[str, Any]:
    """Return characteristic nodal load cases and existing SANS combinations."""

    shared_building_data = dict(building_data)
    for key in EXTRA_PERMANENT_LOAD_KEYS:
        shared_building_data.setdefault(key, truss_data.get(key, 0.0))
    source = _source_portal_data(shared_building_data, wind_data, geometry)
    source_loads: dict[str, dict[str, list[dict]]] = {}
    for load in source.get("member_loads", []):
        source_loads.setdefault(load["member"], {}).setdefault(load["case"], []).append(load)

    nodes = {node.name: node for node in geometry.nodes}
    source_nodes = {node["name"]: node for node in source["nodes"]}
    cases: dict[str, dict[str, list[float]]] = {}
    top_members = [
        member for member in geometry.members if member.role == "top_chord"
    ]
    source_rafter_members = [
        member
        for member in source["members"]
        if str(member.get("type", "")).lower() == "rafter"
    ]
    applied_wind_segments: list[dict[str, Any]] = []
    for member in top_members:
        i_node = nodes[member.i_node]
        j_node = nodes[member.j_node]
        truss_dx = j_node.x_mm - i_node.x_mm
        if abs(truss_dx) <= 1e-9:
            continue
        truss_low, truss_high = sorted((i_node.x_mm, j_node.x_mm))
        for source_member in source_rafter_members:
            source_i = source_nodes[source_member["i_node"]]
            source_j = source_nodes[source_member["j_node"]]
            source_dx = float(source_j["x"]) - float(source_i["x"])
            source_dy = float(source_j["y"]) - float(source_i["y"])
            source_low, source_high = sorted(
                (float(source_i["x"]), float(source_j["x"]))
            )
            overlap_low = max(truss_low, source_low)
            overlap_high = min(truss_high, source_high)
            if overlap_high - overlap_low <= 1e-9:
                continue
            source_length_mm = float(source_member["length"]) * 1000.0
            if abs(source_dx) <= 1e-9 or source_length_mm <= 0:
                raise ValueError(
                    f"Source rafter {source_member['name']} has invalid geometry."
                )
            local_start = (
                (overlap_low - float(source_i["x"]))
                / source_dx
                * source_length_mm
            )
            local_end = (
                (overlap_high - float(source_i["x"]))
                / source_dx
                * source_length_mm
            )
            shape_start = (overlap_low - i_node.x_mm) / truss_dx
            shape_end = (overlap_high - i_node.x_mm) / truss_dx
            loads_by_case = source_loads.get(source_member["name"], {})
            for case, loads in loads_by_case.items():
                for load, i_force_kn, j_force_kn in _consistent_segment_loads(
                    loads,
                    local_start,
                    local_end,
                    source_length_mm,
                    shape_start=shape_start,
                    shape_end=shape_end,
                ):
                    if str(load["direction"]) == "FY":
                        i_fx_kn, i_fy_kn = 0.0, i_force_kn
                        j_fx_kn, j_fy_kn = 0.0, j_force_kn
                    else:
                        # Existing roof wind loads use source-member local Fy.
                        normal_x = -source_dy / source_length_mm
                        normal_y = source_dx / source_length_mm
                        i_fx_kn = i_force_kn * normal_x
                        i_fy_kn = i_force_kn * normal_y
                        j_fx_kn = j_force_kn * normal_x
                        j_fy_kn = j_force_kn * normal_y
                    _add_node_load(cases, case, member.i_node, i_fx_kn, i_fy_kn)
                    _add_node_load(cases, case, member.j_node, j_fx_kn, j_fy_kn)
                    if str(case).upper().startswith("W"):
                        load_start = float(load.get("x1", 0.0) or 0.0)
                        load_end = float(
                            load.get("x2", source_length_mm)
                            or source_length_mm
                        )
                        if load_end < load_start:
                            load_start, load_end = load_end, load_start
                        segment_start, segment_end = sorted(
                            (local_start, local_end)
                        )
                        applied_start = max(segment_start, load_start)
                        applied_end = min(segment_end, load_end)

                        def intensity_at(position_mm: float) -> float:
                            if load_end - load_start <= 1e-9:
                                return float(load["w1"])
                            fraction = (
                                (position_mm - load_start)
                                / (load_end - load_start)
                            )
                            return float(load["w1"]) + (
                                float(load["w2"]) - float(load["w1"])
                            ) * fraction

                        source_fraction_start = applied_start / source_length_mm
                        source_fraction_end = applied_end / source_length_mm
                        global_x_start = (
                            float(source_i["x"])
                            + source_fraction_start * source_dx
                        )
                        global_x_end = (
                            float(source_i["x"])
                            + source_fraction_end * source_dx
                        )
                        applied_wind_segments.append({
                            "case": str(case),
                            "truss_member": member.name,
                            "i_node": member.i_node,
                            "j_node": member.j_node,
                            "source_member": str(source_member["name"]),
                            "global_x_start_m": global_x_start / 1000.0,
                            "global_x_end_m": global_x_end / 1000.0,
                            "loaded_length_m": (
                                applied_end - applied_start
                            ) / 1000.0,
                            "direction": (
                                "Global Y"
                                if str(load["direction"]) == "FY"
                                else "Normal to roof"
                            ),
                            "line_load_start_kn_m": (
                                intensity_at(applied_start) * 1000.0
                            ),
                            "line_load_end_kn_m": (
                                intensity_at(applied_end) * 1000.0
                            ),
                            "equivalent_i_fx_kn": i_fx_kn,
                            "equivalent_i_fy_kn": i_fy_kn,
                            "equivalent_j_fx_kn": j_fx_kn,
                            "equivalent_j_fy_kn": j_fy_kn,
                        })

    extra_kpa = sum(
        float(shared_building_data.get(key, 0.0) or 0.0)
        for key in EXTRA_PERMANENT_LOAD_KEYS
    )
    minimum_extra_kpa = sum(
        float(shared_building_data.get(key, 0.0) or 0.0)
        for key in MINIMUM_PERMANENT_LOAD_KEYS
    )
    source_wind = dict(source.get("wind_data", [{}])[0])
    tributary_width_m = float(
        source_wind.get("rafter_spacing", 0.0) or 0.0
    )
    wind_zone_tables = []
    for source_key, label in WIND_ZONE_TABLES:
        rows = []
        for zone in source.get(source_key, []):
            row = {
                "zone": str(zone.get("Zone", "")),
                "cpe": float(zone.get("cpe", 0.0) or 0.0),
                "zone_length_m": float(zone.get("Length", 0.0) or 0.0),
            }
            for pressure_key in ("cpi=0.2", "cpi=-0.3"):
                line_load_kn_m = (
                    float(zone.get(pressure_key, 0.0) or 0.0) * 1000.0
                )
                row[f"{pressure_key}_line_load_kn_m"] = line_load_kn_m
                row[f"{pressure_key}_pressure_kpa"] = (
                    line_load_kn_m / tributary_width_m
                    if tributary_width_m > 0.0
                    else 0.0
                )
            rows.append(row)
        if rows:
            wind_zone_tables.append({
                "source": source_key,
                "label": label,
                "rows": rows,
            })

    basic_wind_speed = calculate_basic_wind_speed(
        source_wind["fundamental_basic_wind_speed"],
        source_wind["return_period"],
    )
    terrain_roughness = calculate_terrain_roughness(
        source_wind["apex_height"],
        source_wind["terrain_category"],
    )
    peak_pressure_kpa = calculate_peak_wind_pressure(
        source_wind["topographic_factor"],
        basic_wind_speed,
        terrain_roughness,
        source_wind["altitude"],
    )
    case_resultants = []
    for case, node_loads in sorted(cases.items()):
        if not str(case).upper().startswith("W"):
            continue
        case_resultants.append({
            "case": case,
            "sum_fx_kn": sum(value[0] for value in node_loads.values()),
            "sum_fy_kn": sum(value[1] for value in node_loads.values()),
            "loaded_node_count": len(node_loads),
        })

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
            "base_dead_load_max_kpa": 0.0,
            "base_dead_load_min_kpa": 0.0,
            "roof_imposed_load_kpa": 0.25,
            "extra_permanent_load_kpa": extra_kpa,
            "minimum_extra_permanent_load_kpa": minimum_extra_kpa,
            "d_min_excluded_extra_loads": ["services_load_kpa", "solar_load_kpa"],
            "purlins_at_panel_points": True,
        },
        "load_audit": {
            "wind_calculation": {
                "fundamental_basic_wind_speed_m_s": float(
                    source_wind["fundamental_basic_wind_speed"]
                ),
                "return_period_years": float(source_wind["return_period"]),
                "design_basic_wind_speed_m_s": float(basic_wind_speed),
                "terrain_category": str(source_wind["terrain_category"]),
                "terrain_roughness_factor": float(terrain_roughness),
                "topographic_factor": float(source_wind["topographic_factor"]),
                "altitude_m": float(source_wind["altitude"]),
                "peak_velocity_pressure_kpa": float(peak_pressure_kpa),
                "roof_pitch_deg": float(
                    source["frame_data"][0]["roof_pitch"]
                ),
                "tributary_width_m": tributary_width_m,
                "internal_pressure": source_wind.get("internal_pressure", {}),
            },
            "wind_zone_tables": wind_zone_tables,
            "applied_wind_segments": applied_wind_segments,
            "wind_case_resultants": case_resultants,
            "uls_combinations": list(source["load_combinations"]),
            "sls_combinations": list(
                source["serviceability_load_combinations"]
            ),
            "sign_convention": (
                "Line loads follow the generated portal source model. "
                "Positive global Y is upward; local roof loads are resolved "
                "normal to the roof into equivalent truss-node Fx and Fy."
            ),
        },
        "eave_column_wall_actions": _eave_column_wall_actions(source),
        "eave_column_member_loads": _eave_column_member_loads(source),
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
