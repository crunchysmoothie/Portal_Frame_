"""Generic preliminary truss, column, girder and bracing arrangement."""

from __future__ import annotations

import math
from typing import Any, Mapping

from truss_model import PrattTrussGeometry


def grid_label(index: int) -> str:
    if index < 0:
        raise ValueError("Grid index cannot be negative.")
    value = index + 1
    label = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


def build_truss_layout(
    building_data: Mapping[str, Any],
    truss_data: Mapping[str, Any],
    geometry: PrattTrussGeometry,
    restraint_layout: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate supports from span count and girder bay count, never grid lists."""

    length_mm = float(building_data["building_length"])
    spacing_mm = float(building_data["rafter_spacing"])
    if min(length_mm, spacing_mm) <= 0:
        raise ValueError("Building length and truss spacing must be positive.")
    longitudinal_bays = length_mm / spacing_mm
    if not math.isclose(longitudinal_bays, round(longitudinal_bays), abs_tol=1e-8):
        raise ValueError("Building length must be a whole number of truss-grid bays.")
    bay_count = int(round(longitudinal_bays))
    labels = [grid_label(index) for index in range(bay_count + 1)]
    positions = [index * spacing_mm for index in range(bay_count + 1)]

    transverse_positions = [0.0]
    for span in geometry.bay_spans_mm:
        transverse_positions.append(transverse_positions[-1] + span)
    transverse_rows = [str(index + 1) for index in range(len(transverse_positions))]
    internal_rows = list(zip(
        transverse_rows[1:-1], transverse_positions[1:-1]
    ))

    internal_support = str(truss_data.get("internal_support", "Centre columns"))
    if len(geometry.bay_spans_mm) == 1:
        internal_support = "Not required"
    if internal_support not in {
        "Not required", "Centre columns", "Longitudinal girders"
    }:
        raise ValueError("Unsupported internal support arrangement.")

    eave_columns = []
    for row, transverse in (
        (transverse_rows[0], transverse_positions[0]),
        (transverse_rows[-1], transverse_positions[-1]),
    ):
        eave_columns.extend({
            "grid": label,
            "row": row,
            "x_mm": position,
            "y_mm": transverse,
            "support_role": "Main column",
        } for label, position in zip(labels, positions))

    internal_columns = []
    girders = []
    if internal_support == "Centre columns":
        support_indices = list(range(bay_count + 1))
    elif internal_support == "Longitudinal girders":
        girder_bays = int(truss_data.get("girder_span_bays", 0))
        if girder_bays < 2 or bay_count % girder_bays:
            raise ValueError(
                "Girder bay count must divide the building bays into equal spans."
            )
        support_indices = list(range(0, bay_count + 1, girder_bays))
        for row, transverse in internal_rows:
            girders.append({
                "row": row,
                "y_mm": transverse,
                "support_grids": [labels[index] for index in support_indices],
                "span_bays": girder_bays,
                "span_length_mm": girder_bays * spacing_mm,
                "span_count": bay_count // girder_bays,
            })
    else:
        support_indices = []

    for row, transverse in internal_rows:
        internal_columns.extend({
            "grid": labels[index],
            "row": row,
            "x_mm": positions[index],
            "y_mm": transverse,
            "support_role": (
                "Centre column" if internal_support == "Centre columns"
                else "Girder support column"
            ),
        } for index in support_indices)

    truss_lines = [{
        "grid": label,
        "position_mm": position,
        "support_sequence": [
            "Main column",
            *([internal_support] * len(internal_rows)),
            "Main column",
        ],
    } for label, position in zip(labels, positions)]

    top_restraints = (
        list(restraint_layout.get("top_chord", {}).get("restraint_nodes", []))
        if restraint_layout else []
    )
    bottom_restraints = (
        list(restraint_layout.get("bottom_chord", {}).get("restraint_nodes", []))
        if restraint_layout else []
    )
    return {
        "reference": "Generic preliminary truss arrangement",
        "longitudinal": {
            "grid_labels": labels,
            "grid_positions_mm": positions,
            "bay_spacing_mm": spacing_mm,
            "bay_count": bay_count,
            "building_length_mm": length_mm,
        },
        "transverse": {
            "grid_labels": transverse_rows,
            "grid_positions_mm": transverse_positions,
            "bay_spans_mm": list(geometry.bay_spans_mm),
            "span_count": len(geometry.bay_spans_mm),
            "total_width_mm": geometry.span_mm,
        },
        "support_arrangement": {
            "single_span": len(geometry.bay_spans_mm) == 1,
            "internal_support": internal_support,
            "sequence": [
                "Main column left",
                *([internal_support] * len(internal_rows)),
                "Main column right",
            ],
        },
        "truss_lines": truss_lines,
        "columns": {
            "eave": eave_columns,
            "internal": internal_columns,
            "internal_girder": internal_columns if girders else [],
            "eave_count": len(eave_columns),
            "internal_count": len(internal_columns),
        },
        "girders": girders,
        "bracing": {
            "coverage": "Entire building length",
            "top_chord_restraint_lines": top_restraints,
            "bottom_chord_restraint_lines": bottom_restraints,
        },
    }
