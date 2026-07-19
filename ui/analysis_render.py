"""SVG rendering for stored load-combination analysis results."""

from __future__ import annotations

import base64
import html
import math
from typing import Any


INK = "#173C3A"
MUTED = "#607472"
GRID = "#D8E5E3"
LOAD = "#A53D35"
DEFORMED = "#2767B0"
PAPER = "#F8FBFA"


def _data_url(svg: str) -> str:
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


    return tuple(
        str(item["name"])
        for item in visualisation.get("combinations", [])
            )


def _utilisation_colour(value: float | None) -> str:
    if value is None:
        return "#6F807E"
    if value <= 0.7:
        return "#237A57"
    if value <= 1.0:
        return "#C17B00"
    return "#C43D34"


    first = points[0]
    last = points[-1]
    length = math.hypot(last["x_mm"] - first["x_mm"], last["y_mm"] - first["y_mm"])
    ratio = 0.0 if length <= 0 else max(0.0, min(1.0, distance / length))
    return (
        first["x_mm"] + (last["x_mm"] - first["x_mm"]) * ratio,
        first["y_mm"] + (last["y_mm"] - first["y_mm"]) * ratio,
    )


def _load_direction(member: dict[str, Any], direction: str) -> tuple[float, float]:

    if direction == "FX":
        return 1.0, 0.0
    if direction == "FY":
        return 0.0, 1.0
    axes = member.get("local_axes", {})
    axis_name = direction[-1:].lower()
    axis = axes.get(axis_name)
    if isinstance(axis, list) and len(axis) >= 2:
        return float(axis[0]), float(axis[1])
    return (1.0, 0.0) if axis_name == "x" else (0.0, 1.0)


def _arrow_start(
    member: dict[str, Any],
    direction: str,
    magnitude: float,
    target_x: float,
    target_y: float,
    length: float,
) -> tuple[float, float]:
    axis_x, axis_y = _load_direction(member, direction)
    axis_length = math.hypot(axis_x, axis_y)
    if axis_length <= 1e-12:
        axis_x, axis_y, axis_length = 0.0, 1.0, 1.0
    sign = 1.0 if magnitude >= 0 else -1.0
    screen_x = sign * axis_x / axis_length
    screen_y = -sign * axis_y / axis_length
    return target_x - screen_x * length, target_y - screen_y * length


def load_case_svg(
) -> str:
    members = list(combination.get("members", []))
    nodes = list(combination.get("nodes", []))
    if not members or not nodes:
        raise ValueError("Analysis visualisation geometry is empty.")

    all_x = [float(node["x_mm"]) for node in nodes]
    all_y = [float(node["y_mm"]) for node in nodes]
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    extent_x = max(max_x - min_x, 1.0)
    extent_y = max(max_y - min_y, 1.0)
    scale = min(
        (plot_right - plot_left) / extent_x,
        (plot_bottom - plot_top) / extent_y,
    )
    fitted_width = extent_x * scale
    fitted_height = extent_y * scale
    origin_x = plot_left + ((plot_right - plot_left) - fitted_width) / 2
    baseline = plot_bottom

    def sx(value: float) -> float:
        return origin_x + (value - min_x) * scale

    def sy(value: float) -> float:
        return baseline - (value - min_y) * scale

    factors = ", ".join(
        f"{html.escape(str(case))}={float(factor):g}"
        for case, factor in combination.get("factors", {}).items()
        if abs(float(factor)) > 1e-12
    )
    safe_name = html.escape(combination_name)
    body = [
        f'<rect width="{width}" height="{height}" rx="14" fill="{PAPER}"/>',
        f'<text x="28" y="32" fill="{INK}" font-family="Arial,sans-serif" font-size="18" font-weight="700">{safe_name}</text>',
        f'<line x1="{origin_x:.2f}" y1="{baseline:.2f}" x2="{origin_x + fitted_width:.2f}" y2="{baseline:.2f}" stroke="{GRID}"/>',
    ]

    for member in members:
        points = member["displacement_points"]
        first, last = points[0], points[-1]
        utilisation = member.get("utilisation")
                None if utilisation is None else float(utilisation)
            )
        body.append(
            f'<line x1="{sx(float(first["x_mm"])):.2f}" y1="{sy(float(first["y_mm"])):.2f}" '
            f'x2="{sx(float(last["x_mm"])):.2f}" y2="{sy(float(last["y_mm"])):.2f}" '
        )
            midpoint = points[len(points) // 2]
            body.append(
    )

    )

    for member in members:
        points = member["displacement_points"]
            x1 = float(load["x1_mm"])
            x2 = float(load["x2_mm"])
                px, py = _point_on_member(points, distance)
                start_x, start_y = _arrow_start(
                    member,
                    str(load["direction"]),
                    magnitude,
                    sx(px),
                    sy(py),
                )
                body.append(
                )
                    body.append(
                        )
            px, py = _point_on_member(points, float(load["x_mm"]))
            magnitude = float(load["magnitude_kn"])
            target_x, target_y = sx(px), sy(py)
            start_x, start_y = _arrow_start(
                member,
                str(load["direction"]),
                magnitude,
                target_x,
                target_y,
        )
        body.append(
            f'<line x1="{start_x:.2f}" y1="{start_y:.2f}" '
        )
        body.append(
    )

    body.extend(
        [
        ]
    )
