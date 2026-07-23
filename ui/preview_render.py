"""Small SVG renderer for the analysis-independent preview geometry contract."""

from __future__ import annotations

import base64
import html
from typing import Any, Callable


INK = "#173C3A"
GRID = "#B8C9C7"
SECONDARY = "#3E8E89"
BRACE = "#C94B40"
GABLE = "#D08A2E"
CRAWL = "#7A3E9D"
HAUNCH = "#176B68"
MUTED = "#607472"
PAPER = "#F8FBFA"


def _uniform_axes(
    x_extent: float,
    y_extent: float,
    left: float,
    right: float,
    top: float,
    bottom: float,
    *,
    ground: bool = False,
) -> tuple[Callable[[float], float], Callable[[float], float], tuple[float, float, float, float]]:
    """Fit model coordinates without distorting their horizontal/vertical ratio."""

    if x_extent <= 0 or y_extent <= 0:
        raise ValueError("Renderer extents must be positive.")
    scale = min((right - left) / x_extent, (bottom - top) / y_extent)
    fitted_width = x_extent * scale
    fitted_height = y_extent * scale
    fitted_left = left + ((right - left) - fitted_width) / 2
    fitted_bottom = bottom if ground else top + ((bottom - top) + fitted_height) / 2
    fitted_top = fitted_bottom - fitted_height
    return (
        lambda value: fitted_left + value * scale,
        lambda value: fitted_bottom - value * scale,
        (fitted_left, fitted_left + fitted_width, fitted_top, fitted_bottom),
    )


def _data_url(svg: str) -> str:
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _svg_document(title: str, body: str, width: int, height: int) -> str:
    safe_title = html.escape(title)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{safe_title}">'
        f'<rect width="{width}" height="{height}" rx="14" fill="{PAPER}"/>'
        f'<text x="22" y="27" fill="{INK}" font-family="Arial,sans-serif" '
        f'font-size="14" font-weight="700">{safe_title}</text>'
        f'{body}</svg>'
    )


def _line(item: dict[str, Any], x: Callable[[float], float], y: Callable[[float], float], *, color: str, width: float = 2, dash: str = "") -> str:
    start = item["start"]
    end = item["end"]
    dashed = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{x(float(start["x_mm"])):.2f}" '
        f'y1="{y(float(start["y_mm"])):.2f}" '
        f'x2="{x(float(end["x_mm"])):.2f}" '
        f'y2="{y(float(end["y_mm"])):.2f}" '
        f'stroke="{color}" stroke-width="{width}" '
        f'vector-effect="non-scaling-stroke"{dashed}/>'
    )


def frame_elevation_svg(preview: dict[str, Any]) -> str:
    width, height = 600, 300
    dimensions = preview["dimensions"]
    span = float(dimensions["span_mm"])
    apex = float(dimensions["apex_height_mm"])
    left, right, top, bottom = 55, 545, 45, 250
    x, y, fitted = _uniform_axes(
        span, apex, left, right, top, bottom, ground=True
    )
    fitted_left, fitted_right, _, fitted_bottom = fitted

    body = [
        f'<line x1="{fitted_left:.2f}" y1="{fitted_bottom:.2f}" x2="{fitted_right:.2f}" y2="{fitted_bottom:.2f}" stroke="{GRID}" stroke-width="1"/>',
    ]
    for member in preview["frame_elevation"]["members"]:
        body.append(_line(member, x, y, color=INK, width=4))
    for haunch in preview["frame_elevation"].get("haunches", []):
        points = " ".join(
            f'{x(float(point["x_mm"])):.2f},{y(float(point["y_mm"])):.2f}'
            for point in haunch["points"]
        )
        body.append(
            f'<polygon points="{points}" fill="{HAUNCH}" fill-opacity="0.34" '
            f'stroke="{HAUNCH}" stroke-width="1.3"/>'
        )
    for member in preview["frame_elevation"]["gable_columns"]:
        body.append(_line(member, x, y, color=GABLE, width=1.5, dash="5 4"))
    for crawl in preview["frame_elevation"].get("crawl_beams", []):
        point = crawl["point"]
        cx = x(float(point["x_mm"]))
        cy = y(float(point["y_mm"]))
        body.extend(
            [
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="6" fill="#FFFFFF" stroke="{CRAWL}" stroke-width="2.5"/>',
                f'<line x1="{cx - 8:.2f}" y1="{cy:.2f}" x2="{cx + 8:.2f}" y2="{cy:.2f}" stroke="{CRAWL}" stroke-width="2"/>',
                f'<text x="{cx + 9:.2f}" y="{cy - 8:.2f}" fill="{CRAWL}" font-family="Arial,sans-serif" font-size="10" font-weight="700">{html.escape(str(crawl["name"]))}</text>',
            ]
        )
    for point in preview["frame_elevation"]["purlin_points"]:
        body.append(
            f'<circle cx="{x(float(point["x_mm"])):.2f}" '
            f'cy="{y(float(point["y_mm"])):.2f}" r="3.4" fill="{SECONDARY}"/>'
        )
    pitch = preview["roof_layout"]
    body.extend(
        [
            f'<text x="{left}" y="278" fill="{MUTED}" font-family="Arial,sans-serif" font-size="12">Span {span / 1000:g} m</text>',
            f'<text x="{right}" y="278" text-anchor="end" fill="{MUTED}" font-family="Arial,sans-serif" font-size="12">{preview["counts"]["purlin_lines"]} purlin lines</text>',
            f'<text x="{right}" y="48" text-anchor="end" fill="{SECONDARY}" font-family="Arial,sans-serif" font-size="11">Actual spacing {pitch["actual_purlin_spacing_mm"]:.0f} mm</text>',
            f'<text x="{left}" y="295" fill="{CRAWL}" font-family="Arial,sans-serif" font-size="11">{len(preview["frame_elevation"].get("crawl_beams", []))} crawl beam marker(s)</text>',
        ]
    )
    return _data_url(_svg_document("Portal frame section", "".join(body), width, height))


def truss_elevation_svg(preview: dict[str, Any]) -> str:
    """Render the selected transverse truss and its calculated supports."""

    width, height = 600, 300
    geometry = preview["geometry"]
    span = float(geometry["span_mm"])
    depth = float(geometry["depth_mm"])
    node_by_name = {node["name"]: node for node in geometry["nodes"]}
    supports = sorted(
        (node_by_name[name] for name in geometry.get("support_nodes", [])),
        key=lambda node: float(node["x_mm"]),
    )
    eaves_height = max(float(preview.get("eaves_height_mm", 0.0)), 0.0)
    support_y_values = [float(node["y_mm"]) for node in supports]
    ground_y = min(support_y_values) - eaves_height if support_y_values else 0.0
    node_y_values = [float(node["y_mm"]) for node in geometry["nodes"]]
    minimum_y = min([*node_y_values, ground_y])
    maximum_y = max(node_y_values)
    vertical_extent = max(maximum_y - minimum_y, 1.0)
    left, right, top, bottom = 55, 545, 55, 235
    scale = min((right - left) / span, (bottom - top) / vertical_extent)
    drawing_width = span * scale
    drawing_height = vertical_extent * scale
    drawing_left = left + ((right - left) - drawing_width) / 2.0
    drawing_bottom = bottom - ((bottom - top) - drawing_height) / 2.0
    x = lambda value: drawing_left + value * scale
    y = lambda value: drawing_bottom - (value - minimum_y) * scale
    body = []
    colours = {
        "top_chord": INK,
        "bottom_chord": INK,
        "vertical": SECONDARY,
        "support_vertical": GABLE,
        "diagonal": BRACE,
    }
    if supports:
        ground_screen_y = y(ground_y)
        body.append(
            f'<line x1="{x(float(supports[0]["x_mm"])):.2f}" y1="{ground_screen_y:.2f}" '
            f'x2="{x(float(supports[-1]["x_mm"])):.2f}" y2="{ground_screen_y:.2f}" '
            f'stroke="{GRID}" stroke-width="1.2"/>'
        )
        for support in supports:
            sx = x(float(support["x_mm"]))
            sy = y(float(support["y_mm"]))
            body.extend([
                f'<line data-role="support-column" x1="{sx:.2f}" y1="{sy:.2f}" '
                f'x2="{sx:.2f}" y2="{ground_screen_y:.2f}" stroke="{INK}" stroke-width="4"/>',
                f'<path d="M {sx - 6:.2f} {ground_screen_y + 8:.2f} L {sx + 6:.2f} '
                f'{ground_screen_y + 8:.2f} L {sx:.2f} {ground_screen_y:.2f} Z" fill="{GABLE}"/>',
            ])
        dimension_y = ground_screen_y + 18
        for left_support, right_support in zip(supports, supports[1:]):
            x1 = x(float(left_support["x_mm"]))
            x2 = x(float(right_support["x_mm"]))
            bay_span_m = (
                float(right_support["x_mm"]) - float(left_support["x_mm"])
            ) / 1000.0
            body.extend([
                f'<line data-role="span-dimension" x1="{x1:.2f}" y1="{dimension_y:.2f}" '
                f'x2="{x2:.2f}" y2="{dimension_y:.2f}" stroke="{MUTED}" stroke-width="0.9"/>',
                f'<line x1="{x1:.2f}" y1="{dimension_y - 4:.2f}" x2="{x1:.2f}" '
                f'y2="{dimension_y + 4:.2f}" stroke="{MUTED}" stroke-width="0.9"/>',
                f'<line x1="{x2:.2f}" y1="{dimension_y - 4:.2f}" x2="{x2:.2f}" '
                f'y2="{dimension_y + 4:.2f}" stroke="{MUTED}" stroke-width="0.9"/>',
                f'<text x="{(x1 + x2) / 2:.2f}" y="{dimension_y - 4:.2f}" text-anchor="middle" '
                f'fill="{MUTED}" font-family="Arial,sans-serif" font-size="10">{bay_span_m:g} m</text>',
            ])
    for member in geometry["members"]:
        body.append(_line(
            {"start": node_by_name[member["i_node"]], "end": node_by_name[member["j_node"]]},
            x, y, color=colours.get(member["role"], INK),
            width=(
                3.4 if member["role"] == "support_vertical"
                else 3.0 if "chord" in member["role"]
                else 1.8
            ),
        ))
    for node in geometry["nodes"]:
        body.append(
            f'<circle cx="{x(float(node["x_mm"])):.2f}" cy="{y(float(node["y_mm"])):.2f}" '
            f'r="2.8" fill="#FFFFFF" stroke="{INK}" stroke-width="1.2"/>'
        )
    restraint_layout = preview.get("chord_restraint_layout", {})
    for chord_key, colour in (("top_chord", BRACE), ("bottom_chord", GABLE)):
        for restraint in restraint_layout.get(chord_key, {}).get("restraint_nodes", []):
            body.append(
                f'<circle cx="{x(float(restraint["x_mm"])):.2f}" '
                f'cy="{y(float(restraint["y_mm"])):.2f}" r="5.2" '
                f'fill="#FFFFFF" stroke="{colour}" stroke-width="2.4"/>'
            )
    body.extend([
        f'<text x="{left}" y="42" fill="{BRACE}" font-family="Arial,sans-serif" font-size="11">Top restraint nodes</text>',
        f'<text x="{right}" y="42" text-anchor="end" fill="{GABLE}" font-family="Arial,sans-serif" font-size="11">Bottom restraint nodes</text>',
        f'<text x="{left}" y="274" fill="{MUTED}" font-family="Arial,sans-serif" font-size="12">Total width {span / 1000:g} m</text>',
        f'<text x="{right}" y="274" text-anchor="end" fill="{MUTED}" font-family="Arial,sans-serif" font-size="12">Preview depth {depth / 1000:g} m</text>',
        f'<text x="{right}" y="292" text-anchor="end" fill="{SECONDARY}" font-family="Arial,sans-serif" font-size="11">{geometry["panel_count"]} panels at {geometry["panel_width_mm"]:.0f} mm</text>',
        f'<text x="{left}" y="292" fill="{MUTED}" font-family="Arial,sans-serif" font-size="10">Columns mark span boundaries; Same physical scale horizontally and vertically</text>',
    ])
    return _data_url(_svg_document(
        f'{geometry["topology"]} transverse truss', "".join(body), width, height
    ))


def truss_type_reference_svg(selected: str) -> str:
    """Show the load-path distinction between the supported web layouts."""

    width, height = 600, 225
    types = ("Warren with verticals", "Pratt", "Howe")
    body: list[str] = []
    for type_index, name in enumerate(types):
        x0 = 25 + type_index * 193
        box_width = 172
        selected_fill = "#E4F5EE" if name == selected else "#FFFFFF"
        stroke = SECONDARY if name == selected else GRID
        body.append(
            f'<rect x="{x0}" y="48" width="{box_width}" height="145" rx="10" fill="{selected_fill}" stroke="{stroke}" stroke-width="{2 if name == selected else 1}"/>'
        )
        left, right, top_y, bottom_y = x0 + 16, x0 + box_width - 16, 82, 154
        panels = 6
        dx = (right - left) / panels
        for index in range(panels):
            body.extend([
                f'<line x1="{left + index * dx:.2f}" y1="{top_y:.2f}" x2="{left + (index + 1) * dx:.2f}" y2="{top_y:.2f}" stroke="{INK}" stroke-width="2"/>',
                f'<line x1="{left + index * dx:.2f}" y1="{bottom_y:.2f}" x2="{left + (index + 1) * dx:.2f}" y2="{bottom_y:.2f}" stroke="{INK}" stroke-width="2"/>',
            ])
        for index in range(panels + 1):
            xx = left + index * dx
            body.append(f'<line x1="{xx:.2f}" y1="{top_y:.2f}" x2="{xx:.2f}" y2="{bottom_y:.2f}" stroke="{SECONDARY}" stroke-width="1"/>')
        for index in range(panels):
            if name == "Warren with verticals":
                left_top = index % 2 == 0
            else:
                left_top = index < panels / 2
                if name == "Howe":
                    left_top = not left_top
            x1, x2 = left + index * dx, left + (index + 1) * dx
            y1, y2 = (top_y, bottom_y) if left_top else (bottom_y, top_y)
            body.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{BRACE}" stroke-width="2"/>')
        body.append(
            f'<text x="{x0 + box_width / 2:.2f}" y="178" text-anchor="middle" fill="{INK}" font-family="Arial,sans-serif" font-size="11" font-weight="700">{html.escape(name)}</text>'
        )
    return _data_url(_svg_document("Truss type reference", "".join(body), width, height))


def truss_roof_plan_svg(preview: dict[str, Any]) -> str:
    """Render the generated roof, columns, girders and full-length restraint."""

    width, height = 600, 320
    layout = preview["building_layout"]
    longitudinal = layout["longitudinal"]
    transverse = layout["transverse"]
    length = float(longitudinal["building_length_mm"])
    roof_width = float(transverse["total_width_mm"])
    left, right, top, bottom = 55, 545, 48, 270
    x, y_up, fitted = _uniform_axes(length, roof_width, left, right, top, bottom)
    fitted_left, fitted_right, fitted_top, fitted_bottom = fitted
    y = lambda value: fitted_top + value * ((fitted_bottom - fitted_top) / roof_width)
    labels = longitudinal["grid_labels"]
    positions = longitudinal["grid_positions_mm"]
    rows = transverse["grid_positions_mm"]
    body: list[str] = []

    for index, (label, position) in enumerate(zip(labels, positions)):
        xx = x(float(position))
        body.append(
            f'<line x1="{xx:.2f}" y1="{y(0.0):.2f}" x2="{xx:.2f}" y2="{y(rows[-1]):.2f}" stroke="{GRID}" stroke-width="0.8"/>'
        )
        body.append(
            f'<text x="{xx:.2f}" y="{fitted_top - 7:.2f}" text-anchor="middle" fill="{MUTED}" font-family="Arial,sans-serif" font-size="7">{html.escape(label)}</text>'
        )
    for row_index, row_position in enumerate(rows, 1):
        body.append(
            f'<line x1="{fitted_left:.2f}" y1="{y(row_position):.2f}" x2="{fitted_right:.2f}" y2="{y(row_position):.2f}" stroke="{INK}" stroke-width="1.7"/>'
        )
        body.append(
            f'<text x="{fitted_left - 10:.2f}" y="{y(row_position) + 3:.2f}" text-anchor="end" fill="{INK}" font-family="Arial,sans-serif" font-size="9">{row_index}</text>'
        )
    for girder in layout["girders"]:
        row_index = transverse["grid_labels"].index(str(girder["row"]))
        body.append(
            f'<line x1="{fitted_left:.2f}" y1="{y(rows[row_index]):.2f}" '
            f'x2="{fitted_right:.2f}" y2="{y(rows[row_index]):.2f}" '
            f'stroke="{GABLE}" stroke-width="4" opacity="0.8"/>'
        )
    for restraint in layout.get("bracing", {}).get("top_chord_restraint_lines", []):
        yy = y(float(restraint["x_mm"]))
        body.append(
            f'<line x1="{fitted_left:.2f}" y1="{yy:.2f}" x2="{fitted_right:.2f}" y2="{yy:.2f}" stroke="{BRACE}" stroke-width="1.4" opacity="0.8"/>'
        )
    for restraint in layout.get("bracing", {}).get("bottom_chord_restraint_lines", []):
        yy = y(float(restraint["x_mm"]))
        body.append(
            f'<line x1="{fitted_left:.2f}" y1="{yy:.2f}" x2="{fitted_right:.2f}" y2="{yy:.2f}" stroke="{GABLE}" stroke-width="1.2" stroke-dasharray="5 3" opacity="0.8"/>'
        )
    for group, colour, radius in (
        (layout["columns"]["eave"], INK, 2.6),
        (layout["columns"]["internal"], GABLE, 3.3),
    ):
        for column in group:
            body.append(
                f'<circle cx="{x(float(column["x_mm"])):.2f}" cy="{y(float(column["y_mm"])):.2f}" r="{radius}" fill="#FFFFFF" stroke="{colour}" stroke-width="1.7"/>'
            )
    body.extend([
        f'<text x="{left}" y="300" fill="{MUTED}" font-family="Arial,sans-serif" font-size="11">{length / 1000:g} m building; {transverse["span_count"]} transverse span(s)</text>',
        f'<text x="{right}" y="300" text-anchor="end" fill="{BRACE}" font-family="Arial,sans-serif" font-size="11">Solid/dashed: top/bottom restraint, full length</text>',
    ])
    return _data_url(_svg_document("Generated roof and support plan", "".join(body), width, height))


def truss_girder_elevation_svg(preview: dict[str, Any]) -> str:
    """Render one generated longitudinal girder span, when required."""

    width, height = 600, 280
    layout = preview["building_layout"]
    girder = preview.get("girder_preview")
    if not girder:
        body = (
            f'<text x="300" y="135" text-anchor="middle" fill="{MUTED}" '
            f'font-family="Arial,sans-serif" font-size="14">No longitudinal girder is required for this support arrangement.</text>'
        )
        return _data_url(_svg_document("Longitudinal girder", body, width, height))
    length = float(girder["span_mm"])
    girder_depth = float(girder["depth_mm"])
    left, right, top, bottom = 55, 545, 52, 205
    scale = min((right - left) / length, (bottom - top) / girder_depth)
    drawing_width = length * scale
    drawing_height = girder_depth * scale
    drawing_left = left + ((right - left) - drawing_width) / 2.0
    drawing_bottom = bottom - ((bottom - top) - drawing_height) / 2.0
    x = lambda value: drawing_left + value * scale
    y = lambda value: drawing_bottom - value * scale
    body: list[str] = []
    nodes = {node["name"]: node for node in girder["nodes"]}
    colours = {"top_chord": INK, "bottom_chord": INK, "vertical": SECONDARY, "diagonal": BRACE}
    for member in girder["members"]:
        body.append(_line(
            {"start": nodes[member["i_node"]], "end": nodes[member["j_node"]]},
            x, y,
            color=colours.get(member["role"], INK),
            width=2.5 if "chord" in member["role"] else 1.4,
        ))
    for support_x in (0.0, length):
        xx = x(support_x)
        support_y = y(0.0)
        body.extend([
            f'<line x1="{xx:.2f}" y1="{support_y + 2:.2f}" x2="{xx:.2f}" y2="{support_y + 10:.2f}" stroke="{INK}" stroke-width="2"/>',
            f'<path d="M {xx - 6:.2f} {support_y + 18:.2f} L {xx + 6:.2f} {support_y + 18:.2f} L {xx:.2f} {support_y + 10:.2f} Z" fill="{INK}"/>',
        ])
    girder_layout = layout["girders"][0]
    building_bays = int(girder_layout["span_bays"])
    for bay in range(building_bays + 1):
        xx = x(length * bay / building_bays)
        body.append(f'<text x="{xx:.2f}" y="{drawing_bottom + 32:.2f}" text-anchor="middle" fill="{MUTED}" font-family="Arial,sans-serif" font-size="8">{bay}</text>')
    body.extend([
        f'<text x="{left}" y="263" fill="{MUTED}" font-family="Arial,sans-serif" font-size="11">{building_bays} bays = {length / 1000:g} m; preview depth {girder_depth / 1000:g} m</text>',
        f'<text x="{right}" y="263" text-anchor="end" fill="{MUTED}" font-family="Arial,sans-serif" font-size="11">Same physical scale in both directions</text>',
    ])
    return _data_url(_svg_document("Representative longitudinal girder span", "".join(body), width, height))


def roof_plan_svg(preview: dict[str, Any]) -> str:
    width, height = 600, 300
    dimensions = preview["dimensions"]
    length = float(dimensions["building_length_mm"])
    span = float(dimensions["span_mm"])
    left, right, top, bottom = 55, 545, 45, 250
    x_up, _, fitted = _uniform_axes(length, span, left, right, top, bottom)
    fitted_left, fitted_right, fitted_top, fitted_bottom = fitted
    x = x_up
    y = lambda value: fitted_top + value * ((fitted_bottom - fitted_top) / span)

    body: list[str] = []
    for index, position in enumerate(preview["roof_plan"]["frame_positions_mm"], 1):
        xx = x(float(position))
        body.append(
            f'<line x1="{xx:.2f}" y1="{fitted_top:.2f}" x2="{xx:.2f}" y2="{fitted_bottom:.2f}" stroke="{INK}" stroke-width="1.5"/>'
        )
        body.append(
            f'<text x="{xx:.2f}" y="{fitted_top - 8:.2f}" text-anchor="middle" fill="{MUTED}" font-family="Arial,sans-serif" font-size="9">{index}</text>'
        )
    for position in preview["roof_plan"]["purlin_rows_mm"]:
        yy = y(float(position))
        body.append(
            f'<line x1="{fitted_left:.2f}" y1="{yy:.2f}" x2="{fitted_right:.2f}" y2="{yy:.2f}" stroke="{SECONDARY}" stroke-width="1" opacity="0.75"/>'
        )
    for crawl in preview["roof_plan"].get("crawl_rows", []):
        yy = y(float(crawl["x_mm"]))
        body.extend(
            [
                f'<line x1="{fitted_left:.2f}" y1="{yy:.2f}" x2="{fitted_right:.2f}" y2="{yy:.2f}" stroke="{CRAWL}" stroke-width="3" opacity="0.9"/>',
                f'<text x="{fitted_left + 5:.2f}" y="{yy - 5:.2f}" fill="{CRAWL}" font-family="Arial,sans-serif" font-size="10" font-weight="700">{html.escape(str(crawl["name"]))}</text>',
            ]
        )
    for brace in preview["roof_plan"]["braces"]:
        body.append(_line(brace, x, y, color=BRACE, width=2.2))
    body.extend(
        [
            f'<rect x="{fitted_left:.2f}" y="{fitted_top:.2f}" width="{fitted_right-fitted_left:.2f}" height="{fitted_bottom-fitted_top:.2f}" fill="none" stroke="{INK}" stroke-width="1.5"/>',
            f'<text x="{left}" y="278" fill="{MUTED}" font-family="Arial,sans-serif" font-size="12">Length {length / 1000:g} m</text>',
            f'<text x="{right}" y="278" text-anchor="end" fill="{BRACE}" font-family="Arial,sans-serif" font-size="12">Roof X-bracing in end bays</text>',
        ]
    )
    return _data_url(_svg_document("Roof purlin and bracing plan", "".join(body), width, height))


def wall_elevation_svg(preview: dict[str, Any]) -> str:
    width, height = 600, 260
    dimensions = preview["dimensions"]
    length = float(dimensions["building_length_mm"])
    eaves = float(dimensions["eaves_height_mm"])
    left, right, top, bottom = 55, 545, 45, 215
    x, y, fitted = _uniform_axes(
        length, eaves, left, right, top, bottom, ground=True
    )
    fitted_left, fitted_right, fitted_top, fitted_bottom = fitted

    body: list[str] = []
    for position in preview["wall_elevation"]["frame_positions_mm"]:
        xx = x(float(position))
        body.append(
            f'<line x1="{xx:.2f}" y1="{fitted_top:.2f}" x2="{xx:.2f}" y2="{fitted_bottom:.2f}" stroke="{INK}" stroke-width="1.5"/>'
        )
    for position in preview["wall_elevation"]["girt_positions_mm"]:
        yy = y(float(position))
        body.append(
            f'<line x1="{fitted_left:.2f}" y1="{yy:.2f}" x2="{fitted_right:.2f}" y2="{yy:.2f}" stroke="{SECONDARY}" stroke-width="1" opacity="0.7"/>'
        )
    for brace in preview["wall_elevation"]["braces"]:
        body.append(_line(brace, x, y, color=BRACE, width=2.2))
    body.extend(
        [
            f'<rect x="{fitted_left:.2f}" y="{fitted_top:.2f}" width="{fitted_right-fitted_left:.2f}" height="{fitted_bottom-fitted_top:.2f}" fill="none" stroke="{INK}" stroke-width="1.5"/>',
            f'<text x="{left}" y="242" fill="{MUTED}" font-family="Arial,sans-serif" font-size="12">Girts at {preview["wall_elevation"]["actual_girt_spacing_mm"]:.0f} mm actual</text>',
            f'<text x="{right}" y="242" text-anchor="end" fill="{BRACE}" font-family="Arial,sans-serif" font-size="12">{html.escape(preview["wall_elevation"]["bracing_type"])}-bracing</text>',
        ]
    )
    return _data_url(_svg_document("Longitudinal wall elevation", "".join(body), width, height))
