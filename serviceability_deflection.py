"""Permanent-baseline serviceability deflection and roof-drainage checks."""

from __future__ import annotations

import math
import re
from typing import Any, Iterable, Mapping


def is_permanent_case(case_name: str) -> bool:
    """Return whether a generated load case is a permanent action."""

    name = str(case_name).upper()
    return name == "D" or name.startswith("D_")


def permanent_factors(combination: Mapping[str, Any]) -> dict[str, float]:
    """Extract the permanent part of one serviceability combination."""

    return {
        str(case): float(factor)
        for case, factor in combination.get("factors", {}).items()
        if is_permanent_case(str(case)) and abs(float(factor)) > 1e-12
    }


def permanent_baseline_name(combination: Mapping[str, Any]) -> str | None:
    """Return a deterministic internal combination name for its baseline."""

    factors = permanent_factors(combination)
    if not factors:
        return None
    tokens = []
    for case, factor in sorted(factors.items()):
        value = f"{factor:.6g}".replace("-", "m").replace(".", "p")
        tokens.append(f"{re.sub(r'[^A-Za-z0-9_]+', '_', case)}_{value}")
    return "__PERMANENT_BASELINE__" + "__".join(tokens)


def add_permanent_baseline_combinations(
    frame: Any,
    combinations: Iterable[Mapping[str, Any]],
) -> dict[str, str | None]:
    """Add each distinct permanent-action baseline to an FE model."""

    mapping: dict[str, str | None] = {}
    added: set[str] = set()
    for combination in combinations:
        name = str(combination["name"])
        baseline = permanent_baseline_name(combination)
        mapping[name] = baseline
        if baseline is None or baseline in added:
            continue
        frame.add_load_combo(baseline, permanent_factors(combination))
        added.add(baseline)
    return mapping


def uses_permanent_deflection_baseline(data: Any) -> bool:
    """Return whether vertical acceptance uses the variable-action increment."""

    frame_data = getattr(data, "frame_data", [{}])
    settings = frame_data[0] if frame_data else {}
    return (
        str(
            settings.get(
                "use_permanent_deflection_baseline",
                "Yes",
            )
        ).lower()
        == "yes"
    )


def _result_value(result_map: Any, combination: str | None) -> float:
    if combination is None:
        return 0.0
    try:
        value = result_map.get(combination, 0.0)
    except AttributeError:
        value = result_map[combination]
    return float(value)


def roof_drainage_check(
    frame: Any,
    data: Any,
    combination_name: str,
) -> dict[str, Any]:
    """Reject a deformed roof segment whose fall reverses under total SLS load.

    The check uses the original rafter segmentation, which coincides with the
    generated roof geometry and load-zone break points. A segment that loses
    the sign of its original fall can create a local low point and is therefore
    treated as a ponding risk.
    """

    failures = []
    checked = 0
    minimum_remaining_fall = math.inf
    for member in data.members:
        if str(member.type).lower() != "rafter":
            continue
        points = []
        physical = getattr(frame, "members", {}).get(str(member.name))
        if physical is not None and hasattr(physical, "deflection"):
            transform = physical.T()
            cos_x = [float(transform[0, index]) for index in range(3)]
            cos_y = [float(transform[1, index]) for index in range(3)]
            cos_z = [float(transform[2, index]) for index in range(3)]
            origin = [
                float(physical.i_node.X),
                float(physical.i_node.Y),
                float(physical.i_node.Z),
            ]
            length = float(physical.L())
            for index in range(13):
                distance = length * index / 12.0
                local = [
                    float(
                        physical.deflection(
                            component, distance, combination_name
                        )
                    )
                    for component in ("dx", "dy", "dz")
                ]
                global_dy = (
                    local[0] * cos_x[1]
                    + local[1] * cos_y[1]
                    + local[2] * cos_z[1]
                )
                original_y = origin[1] + distance * cos_x[1]
                points.append((distance, original_y, original_y + global_dy))
        if not points:
            i_data = data.nodes[str(member.i_node)]
            j_data = data.nodes[str(member.j_node)]
            i_node = frame.nodes[str(member.i_node)]
            j_node = frame.nodes[str(member.j_node)]
            points = [
                (
                    0.0,
                    float(i_data.y),
                    float(i_data.y)
                    + _result_value(i_node.DY, combination_name),
                ),
                (
                    float(getattr(member, "length", 1.0)),
                    float(j_data.y),
                    float(j_data.y)
                    + _result_value(j_node.DY, combination_name),
                ),
            ]
        for segment_index, (start, end) in enumerate(
            zip(points, points[1:]), 1
        ):
            original_delta_y = end[1] - start[1]
            if abs(original_delta_y) <= 1e-9:
                continue
            deformed_delta_y = end[2] - start[2]
            remaining_fall = (
                math.copysign(1.0, original_delta_y) * deformed_delta_y
            )
            minimum_remaining_fall = min(
                minimum_remaining_fall, remaining_fall
            )
            checked += 1
            if not math.isfinite(deformed_delta_y) or remaining_fall <= 0.0:
                failures.append({
                    "member": str(member.name),
                    "sample_segment": segment_index,
                    "start_x_mm": start[0],
                    "end_x_mm": end[0],
                    "i_node": str(member.i_node),
                    "j_node": str(member.j_node),
                    "original_delta_y_mm": original_delta_y,
                    "deformed_delta_y_mm": deformed_delta_y,
                    "remaining_fall_mm": remaining_fall,
                })
    return {
        "status": "PASS" if not failures else "FAIL",
        "combination": combination_name,
        "checked_rafter_segments": checked,
        "samples_per_member": 13,
        "minimum_remaining_fall_mm": (
            minimum_remaining_fall
            if math.isfinite(minimum_remaining_fall)
            else None
        ),
        "reversed_segments": failures,
        "criterion": (
            "Every deformed rafter segment must retain the sign of its "
            "original roof fall under the total serviceability combination."
        ),
    }


def serviceability_deflection_rows(
    frame: Any,
    data: Any,
) -> list[dict[str, Any]]:
    """Return total, permanent, and incremental-variable SLS deflections."""

    rows = []
    use_baseline = uses_permanent_deflection_baseline(data)
    for combination in data.serviceability_load_combinations:
        name = str(combination["name"])
        baseline = permanent_baseline_name(combination)
        max_dx = max_total_dy = max_permanent_dy = max_variable_dy = 0.0
        dx_node = total_dy_node = permanent_dy_node = variable_dy_node = ""
        governing_total_dy = governing_permanent_dy = 0.0
        governing_variable_dy = 0.0
        total_node_values = (0.0, 0.0, 0.0)
        for node_name, node in frame.nodes.items():
            dx = abs(_result_value(node.DX, name))
            total_dy_value = _result_value(node.DY, name)
            permanent_dy_value = _result_value(node.DY, baseline)
            variable_dy_value = total_dy_value - permanent_dy_value
            total_dy = abs(total_dy_value)
            permanent_dy = abs(permanent_dy_value)
            variable_dy = abs(variable_dy_value)
            values = (dx, total_dy, permanent_dy, variable_dy)
            if not all(math.isfinite(value) for value in values):
                raise ValueError(
                    f"Non-finite serviceability displacement in {name}."
                )
            if dx > max_dx:
                max_dx, dx_node = dx, str(node_name)
            if total_dy > max_total_dy:
                max_total_dy, total_dy_node = total_dy, str(node_name)
                total_node_values = (
                    total_dy_value,
                    permanent_dy_value,
                    variable_dy_value,
                )
            if permanent_dy > max_permanent_dy:
                max_permanent_dy = permanent_dy
                permanent_dy_node = str(node_name)
            if variable_dy > max_variable_dy:
                max_variable_dy = variable_dy
                variable_dy_node = str(node_name)
                governing_total_dy = total_dy_value
                governing_permanent_dy = permanent_dy_value
                governing_variable_dy = variable_dy_value
        if use_baseline:
            checked_max_dy = max_variable_dy
            checked_dy_node = variable_dy_node
            checked_values = (
                governing_total_dy,
                governing_permanent_dy,
                governing_variable_dy,
            )
            basis = (
                "Incremental variable-action deflection relative to the "
                "matching permanent-action baseline."
            )
        else:
            checked_max_dy = max_total_dy
            checked_dy_node = total_dy_node
            checked_values = total_node_values
            basis = (
                "Total serviceability deflection including permanent and "
                "variable actions."
            )
        rows.append({
            "load_combination": name,
            "permanent_baseline_combination": baseline or "Zero permanent action",
            "max_dx": max_dx,
            "dx_node": dx_node,
            "max_dy": checked_max_dy,
            "dy_node": checked_dy_node,
            "total_max_dy": max_total_dy,
            "total_dy_node": total_dy_node,
            "permanent_max_dy": max_permanent_dy,
            "permanent_dy_node": permanent_dy_node,
            "total_dy_at_variable_node": governing_total_dy,
            "permanent_dy_at_variable_node": governing_permanent_dy,
            "variable_dy_at_variable_node": governing_variable_dy,
            "total_dy_at_checked_node": checked_values[0],
            "permanent_dy_at_checked_node": checked_values[1],
            "variable_dy_at_checked_node": checked_values[2],
            "uses_permanent_deflection_baseline": use_baseline,
            "vertical_deflection_basis": basis,
            "roof_drainage": roof_drainage_check(frame, data, name),
        })
    return rows
