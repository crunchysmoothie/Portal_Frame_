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


def combination_names(visualisation: dict[str, Any]) -> tuple[str, ...]:
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


def _point_on_member(points: list[dict[str, float]], distance: float) -> tuple[float, float]:
    first = points[0]
    last = points[-1]
    length = math.hypot(last["x_mm"] - first["x_mm"], last["y_mm"] - first["y_mm"])
    ratio = 0.0 if length <= 0 else max(0.0, min(1.0, distance / length))
    return (
        first["x_mm"] + (last["x_mm"] - first["x_mm"]) * ratio,
        first["y_mm"] + (last["y_mm"] - first["y_mm"]) * ratio,
    )


def _load_direction(member: dict[str, Any], direction: str) -> tuple[float, float]:
    """Return the load axis in model XY coordinates."""

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
    """Return an SVG start point so the arrow points in the force direction."""

    axis_x, axis_y = _load_direction(member, direction)
    axis_length = math.hypot(axis_x, axis_y)
    if axis_length <= 1e-12:
        axis_x, axis_y, axis_length = 0.0, 1.0, 1.0
    sign = 1.0 if magnitude >= 0 else -1.0
    screen_x = sign * axis_x / axis_length
    screen_y = -sign * axis_y / axis_length
    return target_x - screen_x * length, target_y - screen_y * length


def load_case_svg(
    visualisation: dict[str, Any], combination_name: str
) -> str:
    combinations = {
        str(item["name"]): item
        for item in visualisation.get("combinations", [])
    }
    if combination_name not in combinations:
        raise ValueError(f"Unknown analysis combination {combination_name!r}.")
    combination = combinations[combination_name]
    members = list(combination.get("members", []))
    nodes = list(combination.get("nodes", []))
    if not members or not nodes:
        raise ValueError("Analysis visualisation geometry is empty.")

    width, height = 900, 520
    plot_left, plot_right, plot_top, plot_bottom = 60, 840, 80, 405
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

    max_displacement = float(combination.get("max_displacement_mm", 0.0))
    model_size = max(extent_x, extent_y)
    deformation_scale = (
        1.0
        if max_displacement <= 1e-9
        else min(100.0, 0.10 * model_size / max_displacement)
    )

    factors = ", ".join(
        f"{html.escape(str(case))}={float(factor):g}"
        for case, factor in combination.get("factors", {}).items()
        if abs(float(factor)) > 1e-12
    )
    safe_name = html.escape(combination_name)
    body = [
        f'<rect width="{width}" height="{height}" rx="14" fill="{PAPER}"/>',
        f'<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="{LOAD}"/></marker></defs>',
        f'<text x="28" y="32" fill="{INK}" font-family="Arial,sans-serif" font-size="18" font-weight="700">{safe_name}</text>',
        f'<text x="28" y="53" fill="{MUTED}" font-family="Arial,sans-serif" font-size="12">{html.escape(str(combination.get("kind", "")))} • {factors}</text>',
        f'<line x1="{origin_x:.2f}" y1="{baseline:.2f}" x2="{origin_x + fitted_width:.2f}" y2="{baseline:.2f}" stroke="{GRID}"/>',
    ]

    # Undeformed members, coloured by the selected combination's utilisation.
    for member in members:
        points = member["displacement_points"]
        first, last = points[0], points[-1]
        utilisation = member.get("utilisation")
        colour = _utilisation_colour(
            None if utilisation is None else float(utilisation)
        )
        body.append(
            f'<line x1="{sx(float(first["x_mm"])):.2f}" y1="{sy(float(first["y_mm"])):.2f}" '
            f'x2="{sx(float(last["x_mm"])):.2f}" y2="{sy(float(last["y_mm"])):.2f}" '
            f'stroke="{colour}" stroke-width="6" stroke-linecap="round"/>'
        )
        midpoint = points[len(points) // 2]
        util_text = "SLS" if utilisation is None else f"U={float(utilisation):.2f}"
        body.append(
            f'<text x="{sx(float(midpoint["x_mm"])):.2f}" y="{sy(float(midpoint["y_mm"])) - 9:.2f}" '
            f'text-anchor="middle" fill="{colour}" font-family="Arial,sans-serif" font-size="11" font-weight="700">'
            f'{html.escape(str(member["name"]))} {util_text}</text>'
        )

    # Magnified curved deflection sampled directly from PyNite member results.
    for member in members:
        deformed = []
        for point in member["displacement_points"]:
            xx = float(point["x_mm"]) + deformation_scale * float(point["dx_mm"])
            yy = float(point["y_mm"]) + deformation_scale * float(point["dy_mm"])
            deformed.append(f"{sx(xx):.2f},{sy(yy):.2f}")
        body.append(
            f'<polyline points="{" ".join(deformed)}" fill="none" stroke="{DEFORMED}" '
            'stroke-width="2.5" stroke-dasharray="7 4"/>'
        )

    # Factored member loads. Arrow size is fixed for readability; labels retain magnitude.
    for member in members:
        points = member["displacement_points"]
        for load in member.get("distributed_loads", []):
            x1 = float(load["x1_mm"])
            x2 = float(load["x2_mm"])
            for index in range(4):
                distance = x1 + (x2 - x1) * index / 3
                px, py = _point_on_member(points, distance)
                magnitude = (
                    float(load["w1_kn_per_m"])
                    + (float(load["w2_kn_per_m"]) - float(load["w1_kn_per_m"]))
                    * index
                    / 3
                )
                start_x, start_y = _arrow_start(
                    member,
                    str(load["direction"]),
                    magnitude,
                    sx(px),
                    sy(py),
                    24,
                )
                body.append(
                    f'<line x1="{start_x:.2f}" y1="{start_y:.2f}" x2="{sx(px):.2f}" y2="{sy(py):.2f}" '
                    f'stroke="{LOAD}" stroke-width="1.5" marker-end="url(#arrow)"/>'
                )
            label_x, label_y = _point_on_member(points, (x1 + x2) / 2)
            body.append(
                f'<text x="{sx(label_x):.2f}" y="{sy(label_y) - 31:.2f}" text-anchor="middle" '
                f'fill="{LOAD}" font-family="Arial,sans-serif" font-size="9">'
                f'{html.escape(str(load["case"]))}: {float(load["w1_kn_per_m"]):.2f}→{float(load["w2_kn_per_m"]):.2f} kN/m</text>'
            )
        for load in member.get("point_loads", []):
            px, py = _point_on_member(points, float(load["x_mm"]))
            magnitude = float(load["magnitude_kn"])
            target_x, target_y = sx(px), sy(py)
            start_x, start_y = _arrow_start(
                member,
                str(load["direction"]),
                magnitude,
                target_x,
                target_y,
                35,
            )
            body.append(
                f'<line x1="{start_x:.2f}" y1="{start_y:.2f}" '
                f'x2="{target_x:.2f}" y2="{target_y:.2f}" stroke="{LOAD}" stroke-width="2" marker-end="url(#arrow)"/>'
            )
            body.append(
                f'<text x="{sx(px) + 5:.2f}" y="{sy(py) - 39:.2f}" fill="{LOAD}" font-family="Arial,sans-serif" font-size="9">'
                f'{html.escape(str(load["case"]))}: {magnitude:.2f} kN</text>'
            )

    body.extend(
        [
            f'<text x="28" y="444" fill="{INK}" font-family="Arial,sans-serif" font-size="12" font-weight="700">Maximum displacement: {max_displacement:.2f} mm • displayed ×{deformation_scale:.1f}</text>',
            f'<line x1="28" y1="471" x2="68" y2="471" stroke="{DEFORMED}" stroke-width="2.5" stroke-dasharray="7 4"/><text x="75" y="475" fill="{MUTED}" font-family="Arial,sans-serif" font-size="11">magnified deflection</text>',
            '<line x1="235" y1="471" x2="275" y2="471" stroke="#237A57" stroke-width="6"/><text x="282" y="475" fill="#607472" font-family="Arial,sans-serif" font-size="11">U ≤ 0.70</text>',
            '<line x1="370" y1="471" x2="410" y2="471" stroke="#C17B00" stroke-width="6"/><text x="417" y="475" fill="#607472" font-family="Arial,sans-serif" font-size="11">0.70 &lt; U ≤ 1.00</text>',
            '<line x1="560" y1="471" x2="600" y2="471" stroke="#C43D34" stroke-width="6"/><text x="607" y="475" fill="#607472" font-family="Arial,sans-serif" font-size="11">U &gt; 1.00</text>',
            f'<text x="28" y="505" fill="{MUTED}" font-family="Arial,sans-serif" font-size="10">Factored loads shown for this combination. SLS combinations intentionally do not display a strength utilisation.</text>',
        ]
    )
    return _data_url(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{safe_name}">{"".join(body)}</svg>'
    )
