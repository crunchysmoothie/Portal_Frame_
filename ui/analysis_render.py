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


def combination_names(
    visualisation: dict[str, Any], kind: str | None = None
) -> tuple[str, ...]:
    return tuple(
        str(item["name"])
        for item in visualisation.get("combinations", [])
        if kind is None or str(item.get("kind", "")).upper() == kind.upper()
    )


def _selected_combination(
    visualisation: dict[str, Any], combination_name: str
) -> dict[str, Any]:
    combinations = {
        str(item["name"]): item
        for item in visualisation.get("combinations", [])
    }
    if combination_name not in combinations:
        raise ValueError(f"Unknown analysis combination {combination_name!r}.")
    return combinations[combination_name]


def load_schedule(
    visualisation: dict[str, Any], combination_name: str
) -> tuple[dict[str, str], ...]:
    """Return traceable factored-load records for export and diagnostics."""

    combination = _selected_combination(visualisation, combination_name)
    rows: list[dict[str, str]] = []

    def append_row(**values: str) -> None:
        rows.append({"tag": f"L{len(rows) + 1}", **values})

    for member in combination.get("members", []):
        target = str(member["name"])
        for load in member.get("distributed_loads", []):
            append_row(
                target=target,
                kind="Distributed",
                case=str(load["case"]),
                direction=str(load["direction"]),
                magnitude=(
                    f'{float(load["w1_kn_per_m"]):.2f} to '
                    f'{float(load["w2_kn_per_m"]):.2f} kN/m'
                ),
                position=(
                    f'{float(load["x1_mm"]) / 1000:.2f} to '
                    f'{float(load["x2_mm"]) / 1000:.2f} m'
                ),
            )
        for load in member.get("point_loads", []):
            append_row(
                target=target,
                kind="Point",
                case=str(load["case"]),
                direction=str(load["direction"]),
                magnitude=f'{float(load["magnitude_kn"]):.2f} kN',
                position=f'{float(load["x_mm"]) / 1000:.2f} m',
            )
    for load in combination.get("nodal_loads", []):
        append_row(
            target=str(load["node"]),
            kind="Nodal",
            case=str(load["case"]),
            direction=str(load["direction"]),
            magnitude=f'{float(load["magnitude_kn"]):.2f} kN',
            position="At node",
        )
    return tuple(rows)


def _utilisation_colour(value: float | None) -> str:
    if value is None:
        return "#6F807E"
    if value <= 0.7:
        return "#237A57"
    if value <= 1.0:
        return "#C17B00"
    return "#C43D34"


def _point_on_member(
    points: list[dict[str, float]], distance: float
) -> tuple[float, float]:
    first = points[0]
    last = points[-1]
    length = math.hypot(last["x_mm"] - first["x_mm"], last["y_mm"] - first["y_mm"])
    ratio = 0.0 if length <= 0 else max(0.0, min(1.0, distance / length))
    return (
        first["x_mm"] + (last["x_mm"] - first["x_mm"]) * ratio,
        first["y_mm"] + (last["y_mm"] - first["y_mm"]) * ratio,
    )


def _load_direction(member: dict[str, Any], direction: str) -> tuple[float, float]:
    """Return the stored load axis in model XY coordinates."""

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


def _halo_text(
    text: str,
    x: float,
    y: float,
    *,
    colour: str = MUTED,
    size: int = 10,
    anchor: str = "middle",
    weight: int = 700,
) -> str:
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}" fill="{colour}" '
        f'font-family="Arial,sans-serif" font-size="{size}" font-weight="{weight}">'
        f'{html.escape(text)}</text>'
    )


def _outside_label_position(
    start_x: float,
    start_y: float,
    target_x: float,
    target_y: float,
    lane: int,
) -> tuple[float, float]:
    vector_x = start_x - target_x
    vector_y = start_y - target_y
    vector_length = math.hypot(vector_x, vector_y) or 1.0
    offset = 7.0 + 14.0 * lane
    return (
        start_x + vector_x / vector_length * offset,
        start_y + vector_y / vector_length * offset - 3,
    )


def _scaled_arrow_length(value: float, maximum: float) -> float:
    if maximum <= 1e-12:
        return 22.0
    return 18.0 + 42.0 * math.sqrt(min(1.0, abs(value) / maximum))


def _force_definition(component: str) -> tuple[str, str, str]:
    definitions = {
        "axial": ("axial_kn", "Axial force N", "kN"),
        "shear": ("shear_y_kn", "Shear force Vy", "kN"),
        "moment": ("moment_z_knm", "Bending moment Mz", "kN.m"),
    }
    try:
        return definitions[component]
    except KeyError as exc:
        raise ValueError(
            "Internal-force component must be 'axial', 'shear' or 'moment'."
        ) from exc


def load_case_svg(
    visualisation: dict[str, Any],
    combination_name: str,
    view: str = "loads",
    component: str | None = None,
) -> str:
    """Render one engineering quantity without mixing unrelated results."""

    if view not in {"loads", "deflection", "forces", "utilisation"}:
        raise ValueError(
            "Analysis view must be 'loads', 'deflection', 'forces' or 'utilisation'."
        )
    combination = _selected_combination(visualisation, combination_name)
    combination_kind = str(combination.get("kind", "")).upper()
    if view == "deflection" and combination_kind != "SLS":
        raise ValueError("Deflection diagrams are available for SLS combinations only.")
    if view == "utilisation" and combination_kind != "ULS":
        raise ValueError("Utilisation diagrams are available for ULS combinations only.")
    if view == "deflection" and component not in {"dx", "dy", "total deflection"}:
        raise ValueError(
            "Deflection component must be 'dx', 'dy' or 'total deflection'."
        )
    if view == "forces":
        _force_definition(component or "")

    members = list(combination.get("members", []))
    nodes = list(combination.get("nodes", []))
    if not members or not nodes:
        raise ValueError("Analysis visualisation geometry is empty.")

    width, height = 980, 560
    plot_left, plot_right, plot_top, plot_bottom = 75, 905, 105, 445
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
        f'<text x="28" y="53" fill="{MUTED}" font-family="Arial,sans-serif" font-size="12">{html.escape(combination_kind)} &#183; {factors}</text>',
        f'<line x1="{origin_x:.2f}" y1="{baseline:.2f}" x2="{origin_x + fitted_width:.2f}" y2="{baseline:.2f}" stroke="{GRID}"/>',
    ]

    active_cases: list[str] = []
    case_colours: dict[str, str] = {}
    marker_ids: dict[str, str] = {}
    if view == "loads":
        active_cases = [
            str(case)
            for case, factor in combination.get("factors", {}).items()
            if abs(float(factor)) > 1e-12
        ]
        palette = (LOAD, DEFORMED, "#8A6A00", "#7B4EA3", "#237A57")
        case_colours = {
            case: palette[index % len(palette)]
            for index, case in enumerate(active_cases)
        }
        marker_ids = {
            case: f"load-arrow-{index}" for index, case in enumerate(active_cases)
        }
        marker_defs = []
        for case in active_cases:
            colour = case_colours[case]
            marker_defs.append(
                f'<marker id="{marker_ids[case]}" markerWidth="8" markerHeight="8" '
                f'refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" '
                f'fill="{colour}"/></marker>'
            )
        body.insert(1, f'<defs>{"".join(marker_defs)}</defs>')

    for member in members:
        points = member["displacement_points"]
        first, last = points[0], points[-1]
        utilisation = member.get("utilisation")
        colour = (
            _utilisation_colour(
                None if utilisation is None else float(utilisation)
            )
            if view == "utilisation"
            else INK
        )
        body.append(
            f'<line x1="{sx(float(first["x_mm"])):.2f}" y1="{sy(float(first["y_mm"])):.2f}" '
            f'x2="{sx(float(last["x_mm"])):.2f}" y2="{sy(float(last["y_mm"])):.2f}" '
            f'stroke="{colour}" stroke-width="{7 if view == "utilisation" else 4}" '
            'stroke-linecap="round"/>'
        )
        if view in {"loads", "forces", "utilisation"}:
            midpoint = points[len(points) // 2]
            label = str(member["name"])
            if view == "utilisation" and utilisation is not None:
                label += f" U={float(utilisation):.2f}"
            body.append(
                _halo_text(
                    label,
                    sx(float(midpoint["x_mm"])),
                    sy(float(midpoint["y_mm"])) - 8,
                    colour=colour,
                    size=10,
                )
            )

    if view == "loads":
        _render_loads(
            body,
            combination,
            members,
            nodes,
            sx,
            sy,
            active_cases,
            case_colours,
            marker_ids,
        )
    elif view == "deflection":
        _render_deflection(
            body,
            members,
            nodes,
            component or "",
            sx,
            sy,
            extent_x,
            extent_y,
        )
    elif view == "forces":
        _render_forces(body, members, component or "", sx, sy)
    else:
        _render_utilisation(body, members)

    return _data_url(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{safe_name}">{"".join(body)}</svg>'
    )


def _render_loads(
    body: list[str],
    combination: dict[str, Any],
    members: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    sx: Any,
    sy: Any,
    active_cases: list[str],
    case_colours: dict[str, str],
    marker_ids: dict[str, str],
) -> None:
    distributed_max = max(
        (
            abs(float(value))
            for member in members
            for load in member.get("distributed_loads", [])
            for value in (load["w1_kn_per_m"], load["w2_kn_per_m"])
        ),
        default=0.0,
    )
    concentrated_max = max(
        [
            abs(float(load["magnitude_kn"]))
            for member in members
            for load in member.get("point_loads", [])
        ]
        + [
            abs(float(load["magnitude_kn"]))
            for load in combination.get("nodal_loads", [])
        ],
        default=0.0,
    )
    default_marker = next(iter(marker_ids.values()), "")

    for member in members:
        points = member["displacement_points"]
        for load_index, load in enumerate(member.get("distributed_loads", [])):
            x1 = float(load["x1_mm"])
            x2 = float(load["x2_mm"])
            case = str(load["case"])
            colour = case_colours.get(case, LOAD)
            marker_id = marker_ids.get(case, default_marker)
            phase = 0.04 * (load_index % 3)
            for arrow_index, fraction in enumerate((0.18 + phase, 0.50, 0.82 - phase)):
                distance = x1 + (x2 - x1) * fraction
                px, py = _point_on_member(points, distance)
                magnitude = float(load["w1_kn_per_m"]) + (
                    float(load["w2_kn_per_m"]) - float(load["w1_kn_per_m"])
                ) * fraction
                start_x, start_y = _arrow_start(
                    member,
                    str(load["direction"]),
                    magnitude,
                    sx(px),
                    sy(py),
                    _scaled_arrow_length(magnitude, distributed_max),
                )
                body.append(
                    f'<line x1="{start_x:.2f}" y1="{start_y:.2f}" '
                    f'x2="{sx(px):.2f}" y2="{sy(py):.2f}" stroke="{colour}" '
                    f'stroke-width="1.6" marker-end="url(#{marker_id})"/>'
                )
                if arrow_index == load_index % 3:
                    label_x, label_y = _outside_label_position(
                        start_x,
                        start_y,
                        sx(px),
                        sy(py),
                        0,
                    )
                    body.append(
                        _halo_text(
                            f'{load["direction"]} {magnitude:+.2f}',
                            label_x,
                            label_y,
                            colour=colour,
                            size=11,
                        )
                    )

        for load_index, load in enumerate(member.get("point_loads", [])):
            px, py = _point_on_member(points, float(load["x_mm"]))
            magnitude = float(load["magnitude_kn"])
            case = str(load["case"])
            colour = case_colours.get(case, LOAD)
            marker_id = marker_ids.get(case, default_marker)
            target_x, target_y = sx(px), sy(py)
            start_x, start_y = _arrow_start(
                member,
                str(load["direction"]),
                magnitude,
                target_x,
                target_y,
                _scaled_arrow_length(magnitude, concentrated_max),
            )
            body.append(
                f'<line x1="{start_x:.2f}" y1="{start_y:.2f}" '
                f'x2="{target_x:.2f}" y2="{target_y:.2f}" stroke="{colour}" '
                f'stroke-width="2" marker-end="url(#{marker_id})"/>'
            )
            label_x, label_y = _outside_label_position(
                start_x,
                start_y,
                target_x,
                target_y,
                load_index,
            )
            body.append(
                _halo_text(
                    f'{load["direction"]} {magnitude:+.2f} kN',
                    label_x,
                    label_y,
                    colour=colour,
                    size=11,
                )
            )

    node_lookup = {str(node["name"]): node for node in nodes}
    for load_index, load in enumerate(combination.get("nodal_loads", [])):
        node = node_lookup.get(str(load["node"]))
        if node is None:
            continue
        target_x = sx(float(node["x_mm"]))
        target_y = sy(float(node["y_mm"]))
        magnitude = float(load["magnitude_kn"])
        case = str(load["case"])
        colour = case_colours.get(case, LOAD)
        marker_id = marker_ids.get(case, default_marker)
        start_x, start_y = _arrow_start(
            {},
            str(load["direction"]),
            magnitude,
            target_x,
            target_y,
            _scaled_arrow_length(magnitude, concentrated_max),
        )
        body.append(
            f'<line x1="{start_x:.2f}" y1="{start_y:.2f}" '
            f'x2="{target_x:.2f}" y2="{target_y:.2f}" stroke="{colour}" '
            f'stroke-width="2" marker-end="url(#{marker_id})"/>'
        )
        label_x, label_y = _outside_label_position(
            start_x,
            start_y,
            target_x,
            target_y,
            load_index % 3,
        )
        body.append(
            _halo_text(
                f'{load["direction"]} {magnitude:+.2f} kN',
                label_x,
                label_y,
                colour=colour,
                size=11,
            )
        )

    body.append(
        f'<text x="28" y="482" fill="{INK}" font-family="Arial,sans-serif" '
        'font-size="12" font-weight="700">Values are beside the arrows: distributed '
        'loads in kN/m; point and nodal loads in kN. Colour identifies the source case.</text>'
    )
    legend_x = 28
    for case in active_cases:
        colour = case_colours[case]
        factor = float(combination.get("factors", {}).get(case, 0.0))
        body.append(
            f'<line x1="{legend_x}" y1="510" x2="{legend_x + 26}" y2="510" '
            f'stroke="{colour}" stroke-width="3"/><text x="{legend_x + 32}" y="514" '
            f'fill="{MUTED}" font-family="Arial,sans-serif" font-size="10">'
            f'{html.escape(case)} &#215; {factor:g}</text>'
        )
        legend_x += 115 + 7 * len(case)
    body.append(
        f'<text x="28" y="542" fill="{MUTED}" font-family="Arial,sans-serif" '
        'font-size="10">Arrow direction follows the stored global or local member axis; '
        'length is scaled by magnitude within each load type.</text>'
    )


def _render_deflection(
    body: list[str],
    members: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    component: str,
    sx: Any,
    sy: Any,
    extent_x: float,
    extent_y: float,
) -> None:
    is_total = component == "total deflection"

    def displacement_value(point: dict[str, Any]) -> float:
        if is_total:
            return math.hypot(
                float(point.get("dx_mm", 0.0)),
                float(point.get("dy_mm", 0.0)),
            )
        return abs(float(point.get(f"{component}_mm", 0.0)))

    values = [
        displacement_value(point)
        for member in members
        for point in member.get("displacement_points", [])
    ] + [displacement_value(node) for node in nodes]
    maximum = max(values, default=0.0)
    model_size = max(extent_x, extent_y)
    deformation_scale = (
        1.0 if maximum <= 1e-9 else min(120.0, 0.10 * model_size / maximum)
    )

    for member in members:
        deformed = []
        for point in member["displacement_points"]:
            xx = float(point["x_mm"])
            yy = float(point["y_mm"])
            if is_total:
                xx += deformation_scale * float(point.get("dx_mm", 0.0))
                yy += deformation_scale * float(point.get("dy_mm", 0.0))
            elif component == "dx":
                xx += deformation_scale * float(point["dx_mm"])
            else:
                yy += deformation_scale * float(point["dy_mm"])
            deformed.append(f"{sx(xx):.2f},{sy(yy):.2f}")
        body.append(
            f'<polyline points="{" ".join(deformed)}" fill="none" stroke="{DEFORMED}" '
            'stroke-width="3"/>'
        )

    for node in nodes:
        dx = float(node.get("dx_mm", 0.0))
        dy = float(node.get("dy_mm", 0.0))
        if is_total:
            value = math.hypot(dx, dy)
            xx = float(node["x_mm"]) + deformation_scale * dx
            yy = float(node["y_mm"]) + deformation_scale * dy
            node_label = f'{node["name"]} Total {value:.2f} mm'
        else:
            value = float(node.get(f"{component}_mm", 0.0))
            xx = float(node["x_mm"]) + (
                deformation_scale * value if component == "dx" else 0
            )
            yy = float(node["y_mm"]) + (
                deformation_scale * value if component == "dy" else 0
            )
            node_label = f'{node["name"]} {component.upper()} {value:+.2f} mm'
        px, py = sx(xx), sy(yy)
        body.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3.5" fill="{DEFORMED}"/>')
        body.append(
            _halo_text(
                node_label,
                px,
                py - 10,
                colour=DEFORMED,
                size=10,
            )
        )

    component_label = "Total" if is_total else component.upper()
    legend_label = (
        "magnified complete displacement vector; node labels show exact resultant values"
        if is_total
        else "magnified selected component; node labels show exact unscaled values"
    )
    body.extend(
        [
            f'<text x="28" y="492" fill="{INK}" font-family="Arial,sans-serif" font-size="12" font-weight="700">{component_label} deflection &#183; maximum absolute value {maximum:.2f} mm &#183; displayed &#215;{deformation_scale:.1f}</text>',
            f'<line x1="28" y1="520" x2="68" y2="520" stroke="{DEFORMED}" stroke-width="3"/><text x="76" y="524" fill="{MUTED}" font-family="Arial,sans-serif" font-size="11">{legend_label}</text>',
            f'<text x="28" y="545" fill="{MUTED}" font-family="Arial,sans-serif" font-size="10">Deflection is intentionally limited to analysed SLS combinations.</text>',
        ]
    )


def _render_forces(
    body: list[str],
    members: list[dict[str, Any]],
    component: str,
    sx: Any,
    sy: Any,
) -> None:
    force_key, force_title, force_unit = _force_definition(component)
    values = [
        float(point.get(force_key, 0.0))
        for member in members
        for point in member.get("force_points", [])
    ]
    maximum = max((abs(value) for value in values), default=0.0)
    diagram_scale = 58.0 / maximum if maximum > 1e-12 else 0.0

    for member_index, member in enumerate(members):
        geometry = member["displacement_points"]
        samples = member.get("force_points", [])
        if not samples:
            continue
        local_y = member.get("local_axes", {}).get("y", [0.0, 1.0])
        local_x = member.get("local_axes", {}).get("x", [1.0, 0.0])
        offset_x = float(local_y[0])
        offset_y = -float(local_y[1])
        offset_length = math.hypot(offset_x, offset_y) or 1.0
        offset_x /= offset_length
        offset_y /= offset_length
        tangent_x = float(local_x[0])
        tangent_y = -float(local_x[1])
        tangent_length = math.hypot(tangent_x, tangent_y) or 1.0
        tangent_x /= tangent_length
        tangent_y /= tangent_length
        diagram_points = []
        for sample in samples:
            model_x, model_y = _point_on_member(geometry, float(sample["x_mm"]))
            value = float(sample.get(force_key, 0.0))
            diagram_points.append(
                (
                    sx(model_x) + offset_x * value * diagram_scale,
                    sy(model_y) + offset_y * value * diagram_scale,
                    value,
                )
            )
        polygon = [
            f'{sx(float(geometry[0]["x_mm"])):.2f},{sy(float(geometry[0]["y_mm"])):.2f}'
        ]
        polygon.extend(f"{px:.2f},{py:.2f}" for px, py, _ in diagram_points)
        polygon.append(
            f'{sx(float(geometry[-1]["x_mm"])):.2f},{sy(float(geometry[-1]["y_mm"])):.2f}'
        )
        body.append(
            f'<polygon points="{" ".join(polygon)}" fill="{DEFORMED}" '
            'fill-opacity="0.10" stroke="none"/>'
        )
        line_points = " ".join(
            f"{px:.2f},{py:.2f}" for px, py, _ in diagram_points
        )
        body.append(
            f'<polyline points="{line_points}" fill="none" stroke="{DEFORMED}" '
            'stroke-width="2.5"/>'
        )
        peak_index = max(
            range(len(diagram_points)),
            key=lambda index: abs(diagram_points[index][2]),
        )
        px, py, value = diagram_points[peak_index]
        stagger = 12.0 if member_index % 2 else -12.0
        body.append(
            _halo_text(
                f"{value:+.2f}",
                px + offset_x * 10 + tangent_x * stagger,
                py + offset_y * 10 + tangent_y * stagger - 3,
                colour=DEFORMED,
                size=10,
            )
        )

    body.extend(
        [
            f'<text x="28" y="492" fill="{INK}" font-family="Arial,sans-serif" font-size="12" font-weight="700">{force_title} ({force_unit}) &#183; peak absolute value {maximum:.2f} {force_unit}</text>',
            f'<line x1="28" y1="520" x2="68" y2="520" stroke="{DEFORMED}" stroke-width="2.5"/><text x="76" y="524" fill="{MUTED}" font-family="Arial,sans-serif" font-size="11">sampled diagram; each member is labelled at its peak absolute value</text>',
            f'<text x="28" y="545" fill="{MUTED}" font-family="Arial,sans-serif" font-size="10">Signs follow PyNite local member axes. Diagram offset is scaled independently for the selected component.</text>',
        ]
    )


def _render_utilisation(body: list[str], members: list[dict[str, Any]]) -> None:
    utilisations = [
        float(member["utilisation"])
        for member in members
        if member.get("utilisation") is not None
    ]
    maximum = max(utilisations, default=0.0)
    body.extend(
        [
            f'<text x="28" y="482" fill="{INK}" font-family="Arial,sans-serif" font-size="12" font-weight="700">Maximum member utilisation {maximum:.3f}</text>',
            '<line x1="28" y1="515" x2="68" y2="515" stroke="#237A57" stroke-width="7"/><text x="76" y="519" fill="#607472" font-family="Arial,sans-serif" font-size="11">U &lt;= 0.70</text>',
            '<line x1="210" y1="515" x2="250" y2="515" stroke="#C17B00" stroke-width="7"/><text x="258" y="519" fill="#607472" font-family="Arial,sans-serif" font-size="11">0.70 &lt; U &lt;= 1.00</text>',
            '<line x1="430" y1="515" x2="470" y2="515" stroke="#C43D34" stroke-width="7"/><text x="478" y="519" fill="#607472" font-family="Arial,sans-serif" font-size="11">U &gt; 1.00</text>',
            f'<text x="28" y="545" fill="{MUTED}" font-family="Arial,sans-serif" font-size="10">Utilisation is intentionally limited to analysed ULS combinations.</text>',
        ]
    )
