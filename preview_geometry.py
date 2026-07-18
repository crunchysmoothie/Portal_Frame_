"""Analysis-independent geometry contract for UI previews.

The preview deliberately contains geometry and layout only.  It does not
represent member adequacy, analysis results, or a completed structural design.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from roof_layout import calculate_roof_bracing_layout, roof_brace_pairs


MAX_PREVIEW_BAYS = 500
MAX_PREVIEW_SECONDARY_SPACES = 500


def _positive(building: Mapping[str, Any], key: str) -> float:
    try:
        value = float(building[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a positive number.") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{key} must be a positive number.")
    return value


def _positive_integer(building: Mapping[str, Any], key: str) -> int:
    value = _positive(building, key)
    if not value.is_integer():
        raise ValueError(f"{key} must be a positive whole number.")
    return int(value)


def _frame_positions(length_mm: float, spacing_mm: float) -> list[float]:
    positions = [0.0]
    while positions[-1] < length_mm - 1e-6:
        positions.append(min(length_mm, positions[-1] + spacing_mm))
    return positions


def _even_positions(total_mm: float, maximum_mm: float) -> tuple[list[float], float]:
    spaces = max(1, math.ceil(total_mm / maximum_mm))
    actual = total_mm / spaces
    return [index * actual for index in range(spaces + 1)], actual


def _roof_points(
    span_mm: float,
    eaves_mm: float,
    apex_mm: float,
    roof_type: str,
    spaces_per_slope: int,
) -> list[dict[str, float | str]]:
    run = span_mm / 2 if roof_type == "Duo Pitched" else span_mm
    coordinates = [
        (
            run * index / spaces_per_slope,
            eaves_mm + (apex_mm - eaves_mm) * index / spaces_per_slope,
        )
        for index in range(spaces_per_slope + 1)
    ]
    if roof_type == "Duo Pitched":
        coordinates.extend(
            (
                span_mm - run * index / spaces_per_slope,
                eaves_mm + (apex_mm - eaves_mm) * index / spaces_per_slope,
            )
            for index in range(spaces_per_slope - 1, -1, -1)
        )
    return [
        {"id": f"P{index}", "x_mm": x, "y_mm": y}
        for index, (x, y) in enumerate(coordinates, 1)
    ]


def _line(
    member_id: str,
    kind: str,
    start: tuple[float, float],
    end: tuple[float, float],
) -> dict[str, Any]:
    return {
        "id": member_id,
        "kind": kind,
        "start": {"x_mm": float(start[0]), "y_mm": float(start[1])},
        "end": {"x_mm": float(end[0]), "y_mm": float(end[1])},
    }


def _wall_braces(
    frame_positions: list[float],
    eaves_mm: float,
    bracing_type: str,
    panel_count: int,
) -> list[dict[str, Any]]:
    if len(frame_positions) < 2:
        return []
    braced_bays = [(frame_positions[0], frame_positions[1])]
    last_bay = (frame_positions[-2], frame_positions[-1])
    if last_bay != braced_bays[0]:
        braced_bays.append(last_bay)

    members: list[dict[str, Any]] = []
    panel_height = eaves_mm / panel_count
    for bay_index, (x0, x1) in enumerate(braced_bays, 1):
        for panel_index in range(panel_count):
            y0 = panel_index * panel_height
            y1 = (panel_index + 1) * panel_height
            prefix = f"WB{bay_index}-{panel_index + 1}"
            if bracing_type == "X":
                members.extend(
                    [
                        _line(f"{prefix}A", "wall_brace", (x0, y0), (x1, y1)),
                        _line(f"{prefix}B", "wall_brace", (x0, y1), (x1, y0)),
                    ]
                )
            elif bracing_type == "K":
                middle = (y0 + y1) / 2
                members.extend(
                    [
                        _line(f"{prefix}A", "wall_brace", (x0, middle), (x1, y0)),
                        _line(f"{prefix}B", "wall_brace", (x0, middle), (x1, y1)),
                    ]
                )
            else:  # A-bracing rises from both panel corners to the bay centre.
                centre = (x0 + x1) / 2
                members.extend(
                    [
                        _line(f"{prefix}A", "wall_brace", (x0, y0), (centre, y1)),
                        _line(f"{prefix}B", "wall_brace", (x1, y0), (centre, y1)),
                    ]
                )
    return members


def build_preview_geometry(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a renderer-neutral layout preview from a validated UI payload."""

    try:
        building = payload["building_data"]
    except (KeyError, TypeError) as exc:
        raise ValueError("A building_data object is required.") from exc
    if not isinstance(building, Mapping):
        raise ValueError("building_data must be an object.")

    span = _positive(building, "gable_width")
    eaves = _positive(building, "eaves_height")
    apex = _positive(building, "apex_height")
    spacing = _positive(building, "rafter_spacing")
    length = _positive(building, "building_length")
    purlin_max = _positive(building, "purlin_max_spacing_mm")
    girt_max = _positive(building, "girt_max_spacing_mm")
    roof_panels = _positive_integer(building, "rafter_bracing_spacing")
    wall_panels = _positive_integer(building, "col_bracing_spacing")

    if apex <= eaves:
        raise ValueError("apex_height must exceed eaves_height.")
    roof_type = str(building.get("building_roof", ""))
    if roof_type not in {"Duo Pitched", "Mono Pitched"}:
        raise ValueError("building_roof must be Duo Pitched or Mono Pitched.")
    bracing_type = str(building.get("column_bracing_type", "")).upper()
    if bracing_type not in {"X", "K", "A"}:
        raise ValueError("column_bracing_type must be X, K, or A.")

    layout = calculate_roof_bracing_layout(
        span, eaves, apex, roof_type, purlin_max, roof_panels
    )
    if layout["purlin_spaces_per_slope"] > MAX_PREVIEW_SECONDARY_SPACES:
        raise ValueError(
            "The preview would contain too many purlin spaces; check the portal "
            "span and maximum purlin spacing."
        )
    if math.ceil(length / spacing) > MAX_PREVIEW_BAYS:
        raise ValueError(
            "The preview would contain too many frame bays; check the building "
            "length and portal spacing."
        )
    if math.ceil(eaves / girt_max) > MAX_PREVIEW_SECONDARY_SPACES:
        raise ValueError(
            "The preview would contain too many girt spaces; check the eaves "
            "height and maximum girt spacing."
        )
    roof_points = _roof_points(
        span, eaves, apex, roof_type, layout["purlin_spaces_per_slope"]
    )
    frame_positions = _frame_positions(length, spacing)

    portal_members = [
        _line("C1", "column", (0, 0), (0, eaves)),
        _line("R1", "rafter", (0, eaves), (roof_points[-1]["x_mm"] if roof_type == "Mono Pitched" else span / 2, apex)),
    ]
    if roof_type == "Duo Pitched":
        portal_members.extend(
            [
                _line("R2", "rafter", (span / 2, apex), (span, eaves)),
                _line("C2", "column", (span, eaves), (span, 0)),
            ]
        )
    else:
        portal_members.append(_line("C2", "column", (span, apex), (span, 0)))

    gable_columns: list[dict[str, Any]] = []
    if str(building.get("building_type")) != "Canopy":
        gable_count = _positive_integer(building, "gable_column_count")
        if gable_count % 2 == 0:
            raise ValueError("gable_column_count must be a positive odd number.")
        for index in range(1, gable_count + 1):
            x = span * index / (gable_count + 1)
            if roof_type == "Mono Pitched":
                height = eaves + (apex - eaves) * x / span
            else:
                centre = span / 2
                height = eaves + (apex - eaves) * (1 - abs(x - centre) / centre)
            gable_columns.append(
                _line(f"GC{index}", "gable_column", (x, 0), (x, height))
            )

    pair_indices = roof_brace_pairs(
        layout["purlin_spaces_per_slope"],
        roof_type,
        layout["purlin_spaces_per_brace_panel"],
    )
    braced_bays = [(frame_positions[0], frame_positions[1])]
    last_bay = (frame_positions[-2], frame_positions[-1])
    if last_bay != braced_bays[0]:
        braced_bays.append(last_bay)
    roof_braces: list[dict[str, Any]] = []
    for bay_index, (x0, x1) in enumerate(braced_bays, 1):
        for panel_index, (first, last) in enumerate(pair_indices, 1):
            y0 = float(roof_points[first]["x_mm"])
            y1 = float(roof_points[last]["x_mm"])
            prefix = f"RB{bay_index}-{panel_index}"
            roof_braces.extend(
                [
                    _line(f"{prefix}A", "roof_brace", (x0, y0), (x1, y1)),
                    _line(f"{prefix}B", "roof_brace", (x0, y1), (x1, y0)),
                ]
            )

    girt_positions, actual_girt_spacing = _even_positions(eaves, girt_max)
    wall_braces = _wall_braces(
        frame_positions, eaves, bracing_type, wall_panels
    )

    return {
        "schema_version": "1.0",
        "status": "layout_preview_only",
        "units": "mm",
        "dimensions": {
            "span_mm": span,
            "eaves_height_mm": eaves,
            "apex_height_mm": apex,
            "building_length_mm": length,
            "nominal_frame_spacing_mm": spacing,
        },
        "counts": {
            "bays": len(frame_positions) - 1,
            "frame_lines": len(frame_positions),
            "purlin_lines": len(roof_points),
            "gable_columns_per_end": len(gable_columns),
        },
        "roof_layout": layout,
        "frame_elevation": {
            "members": portal_members,
            "purlin_points": roof_points,
            "gable_columns": gable_columns,
        },
        "roof_plan": {
            "frame_positions_mm": frame_positions,
            "purlin_rows_mm": [float(point["x_mm"]) for point in roof_points],
            "braces": roof_braces,
        },
        "wall_elevation": {
            "frame_positions_mm": frame_positions,
            "girt_positions_mm": girt_positions,
            "actual_girt_spacing_mm": actual_girt_spacing,
            "bracing_type": bracing_type,
            "braces": wall_braces,
        },
    }
