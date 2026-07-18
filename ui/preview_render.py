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
MUTED = "#607472"
PAPER = "#F8FBFA"


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
    x = lambda value: left + (right - left) * value / span
    y = lambda value: bottom - (bottom - top) * value / apex

    body = [
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="{GRID}" stroke-width="1"/>',
    ]
    for member in preview["frame_elevation"]["members"]:
        body.append(_line(member, x, y, color=INK, width=4))
    for member in preview["frame_elevation"]["gable_columns"]:
        body.append(_line(member, x, y, color=GABLE, width=1.5, dash="5 4"))
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
        ]
    )
    return _data_url(_svg_document("Portal frame section", "".join(body), width, height))


def roof_plan_svg(preview: dict[str, Any]) -> str:
    width, height = 600, 300
    dimensions = preview["dimensions"]
    length = float(dimensions["building_length_mm"])
    span = float(dimensions["span_mm"])
    left, right, top, bottom = 55, 545, 45, 250
    x = lambda value: left + (right - left) * value / length
    y = lambda value: top + (bottom - top) * value / span

    body: list[str] = []
    for index, position in enumerate(preview["roof_plan"]["frame_positions_mm"], 1):
        xx = x(float(position))
        body.append(
            f'<line x1="{xx:.2f}" y1="{top}" x2="{xx:.2f}" y2="{bottom}" stroke="{INK}" stroke-width="1.5"/>'
        )
        body.append(
            f'<text x="{xx:.2f}" y="{top - 8}" text-anchor="middle" fill="{MUTED}" font-family="Arial,sans-serif" font-size="9">{index}</text>'
        )
    for position in preview["roof_plan"]["purlin_rows_mm"]:
        yy = y(float(position))
        body.append(
            f'<line x1="{left}" y1="{yy:.2f}" x2="{right}" y2="{yy:.2f}" stroke="{SECONDARY}" stroke-width="1" opacity="0.75"/>'
        )
    for brace in preview["roof_plan"]["braces"]:
        body.append(_line(brace, x, y, color=BRACE, width=2.2))
    body.extend(
        [
            f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="none" stroke="{INK}" stroke-width="1.5"/>',
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
    x = lambda value: left + (right - left) * value / length
    y = lambda value: bottom - (bottom - top) * value / eaves

    body: list[str] = []
    for position in preview["wall_elevation"]["frame_positions_mm"]:
        xx = x(float(position))
        body.append(
            f'<line x1="{xx:.2f}" y1="{top}" x2="{xx:.2f}" y2="{bottom}" stroke="{INK}" stroke-width="1.5"/>'
        )
    for position in preview["wall_elevation"]["girt_positions_mm"]:
        yy = y(float(position))
        body.append(
            f'<line x1="{left}" y1="{yy:.2f}" x2="{right}" y2="{yy:.2f}" stroke="{SECONDARY}" stroke-width="1" opacity="0.7"/>'
        )
    for brace in preview["wall_elevation"]["braces"]:
        body.append(_line(brace, x, y, color=BRACE, width=2.2))
    body.extend(
        [
            f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="none" stroke="{INK}" stroke-width="1.5"/>',
            f'<text x="{left}" y="242" fill="{MUTED}" font-family="Arial,sans-serif" font-size="12">Girts at {preview["wall_elevation"]["actual_girt_spacing_mm"]:.0f} mm actual</text>',
            f'<text x="{right}" y="242" text-anchor="end" fill="{BRACE}" font-family="Arial,sans-serif" font-size="12">{html.escape(preview["wall_elevation"]["bracing_type"])}-bracing</text>',
        ]
    )
    return _data_url(_svg_document("Longitudinal wall elevation", "".join(body), width, height))
