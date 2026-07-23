"""Renderer-neutral load-combination results extracted from the analysed FE model."""

from __future__ import annotations

import math
from typing import Any, Iterable


def _result_value(values: Any, combination: str) -> float:
    try:
        value = values.get(combination, 0.0)
    except AttributeError:
        value = values[combination]
    return float(value)


def _factored_distributed_loads(member: Any, factors: dict[str, float]) -> list[dict[str, Any]]:
    loads = []
    for load in getattr(member, "DistLoads", []):
        if not isinstance(load, tuple) or len(load) < 6:
            continue
        direction, w1, w2, x1, x2, case = load[:6]
        factor = float(factors.get(case, 0.0))
        fw1 = float(w1) * factor
        fw2 = float(w2) * factor
        if abs(fw1) < 1e-12 and abs(fw2) < 1e-12:
            continue
        if float(x2) - float(x1) <= 1e-6:
            continue
        loads.append(
            {
                "direction": str(direction),
                "case": str(case),
                "factor": factor,
                "w1_kn_per_m": fw1 * 1000,
                "w2_kn_per_m": fw2 * 1000,
                "x1_mm": float(x1),
                "x2_mm": float(x2),
            }
        )
    return loads


def _factored_point_loads(member: Any, factors: dict[str, float]) -> list[dict[str, Any]]:
    loads = []
    for load in getattr(member, "PtLoads", []):
        if not isinstance(load, tuple) or len(load) < 4:
            continue
        direction, magnitude, x, case = load[:4]
        factor = float(factors.get(case, 0.0))
        factored = float(magnitude) * factor
        if abs(factored) < 1e-12:
            continue
        loads.append(
            {
                "direction": str(direction),
                "case": str(case),
                "factor": factor,
                "magnitude_kn": factored,
                "x_mm": float(x),
            }
        )
    return loads


def _member_displacement_points(member: Any, combination: str, count: int = 13) -> list[dict[str, float]]:
    """Sample exact PyNite member displacement and transform it to global axes."""

    length = float(member.L())
    transform = member.T()
    cos_x = [float(value) for value in transform[0, 0:3]]
    cos_y = [float(value) for value in transform[1, 0:3]]
    cos_z = [float(value) for value in transform[2, 0:3]]
    origin = [
        float(member.i_node.X),
        float(member.i_node.Y),
        float(member.i_node.Z),
    ]
    points = []
    for index in range(count):
        distance = length * index / (count - 1)
        local = [
            float(member.deflection("dx", distance, combination)),
            float(member.deflection("dy", distance, combination)),
            float(member.deflection("dz", distance, combination)),
        ]
        global_displacement = [
            local[0] * cos_x[axis]
            + local[1] * cos_y[axis]
            + local[2] * cos_z[axis]
            for axis in range(3)
        ]
        original = [
            origin[axis] + distance * cos_x[axis]
            for axis in range(3)
        ]
        points.append(
            {
                "x_mm": original[0],
                "y_mm": original[1],
                "dx_mm": global_displacement[0],
                "dy_mm": global_displacement[1],
            }
        )
    return points


def _member_force_points(
    member: Any, combination: str, count: int = 13
) -> list[dict[str, float]]:
    """Sample member actions in PyNite's local member sign convention."""

    length = float(member.L())
    points = []
    for index in range(count):
        distance = length * index / (count - 1)
        points.append(
            {
                "x_mm": distance,
                "axial_kn": float(member.axial(distance, combination)),
                "shear_y_kn": float(member.shear("Fy", distance, combination)),
                "moment_z_knm": float(
                    member.moment("Mz", distance, combination)
                )
                / 1000,
            }
        )
    return points


def build_analysis_visualisation(
    frame: Any,
    data: Any,
    member_results: Iterable[Any],
) -> dict[str, Any]:
    """Build serialisable geometry, factored loads, utilisation and deflection."""

    result_lookup = {}
    for result in member_results:
        parent_name = str(result.member).split("[", 1)[0]
        key = (result.load_combination, parent_name)
        current = result_lookup.get(key)
        if (
            current is None
            or float(result.governing_ratio) > float(current.governing_ratio)
        ):
            result_lookup[key] = result
    member_types = {item.name: item.type for item in data.members}
    combinations: list[tuple[str, str, dict[str, float]]] = []
    seen = set()
    for kind, source in (
        ("ULS", data.load_combinations),
        ("SLS", data.serviceability_load_combinations),
    ):
        for item in source:
            name = str(item["name"])
            if name in seen:
                continue
            seen.add(name)
            combinations.append(
                (name, kind, {key: float(value) for key, value in item["factors"].items()})
            )

    combination_results = []
    for name, kind, factors in combinations:
        members = []
        max_displacement = 0.0
        for member_name, member in frame.members.items():
            design = result_lookup.get((name, member_name))
            points = _member_displacement_points(member, name)
            force_points = _member_force_points(member, name)
            transform = member.T()
            max_displacement = max(
                max_displacement,
                max(
                    math.hypot(point["dx_mm"], point["dy_mm"])
                    for point in points
                ),
            )
            members.append(
                {
                    "name": member_name,
                    "type": member_types.get(member_name, ""),
                    "section": member.section.name,
                    "utilisation": (
                        float(design.governing_ratio) if design is not None else None
                    ),
                    "status": design.status if design is not None else "SLS",
                    "governing_check": (
                        design.governing_check if design is not None else ""
                    ),
                    "local_axes": {
                        "x": [float(transform[0, 0]), float(transform[0, 1])],
                        "y": [float(transform[1, 0]), float(transform[1, 1])],
                    },
                    "distributed_loads": _factored_distributed_loads(
                        member, factors
                    ),
                    "point_loads": _factored_point_loads(member, factors),
                    "displacement_points": points,
                    "force_points": force_points,
                }
            )

        nodal_loads = []
        nodes = []
        for node_name, node in frame.nodes.items():
            dx = _result_value(node.DX, name)
            dy = _result_value(node.DY, name)
            max_displacement = max(max_displacement, math.hypot(dx, dy))
            nodes.append(
                {
                    "name": node_name,
                    "x_mm": float(node.X),
                    "y_mm": float(node.Y),
                    "dx_mm": dx,
                    "dy_mm": dy,
                }
            )
            for load in getattr(node, "NodeLoads", []):
                if not isinstance(load, tuple) or len(load) < 3:
                    continue
                direction, magnitude, case = load[:3]
                factor = float(factors.get(case, 0.0))
                factored = float(magnitude) * factor
                if abs(factored) < 1e-12:
                    continue
                nodal_loads.append(
                    {
                        "node": node_name,
                        "direction": str(direction),
                        "case": str(case),
                        "factor": factor,
                        "magnitude_kn": factored,
                    }
                )

        combination_results.append(
            {
                "name": name,
                "kind": kind,
                "factors": factors,
                "max_displacement_mm": max_displacement,
                "nodes": nodes,
                "members": members,
                "nodal_loads": nodal_loads,
            }
        )

    return {
        "schema_version": "1.1",
        "units": {
            "geometry": "mm",
            "displacement": "mm",
            "distributed_load": "kN/m",
            "point_load": "kN",
            "axial_force": "kN",
            "shear_force": "kN",
            "bending_moment": "kN.m",
        },
        "combinations": combination_results,
    }
