"""Shared purlin and roof-bracing layout calculations."""

from __future__ import annotations

import math


def calculate_roof_bracing_layout(
    span_mm,
    eaves_height_mm,
    apex_height_mm,
    roof_type,
    purlin_max_spacing_mm,
    bracing_intervals_per_slope,
):
    """Return actual purlin spacing and evenly distributed brace-panel sizes."""
    span = float(span_mm)
    rise = float(apex_height_mm) - float(eaves_height_mm)
    maximum = float(purlin_max_spacing_mm)
    requested = int(bracing_intervals_per_slope)
    if span <= 0 or maximum <= 0:
        raise ValueError("Roof span and maximum purlin spacing must be positive.")
    if requested < 1:
        raise ValueError("rafter_bracing_spacing must be at least 1.")

    run = span / 2 if str(roof_type) == "Duo Pitched" else span
    slope_length = math.hypot(run, rise)
    purlin_spaces = max(1, math.ceil(slope_length / maximum))
    panel_count = min(requested, purlin_spaces)
    base, remainder = divmod(purlin_spaces, panel_count)
    panel_sizes = [base + 1] * remainder + [base] * (panel_count - remainder)
    return {
        "slope_length_mm": slope_length,
        "purlin_spaces_per_slope": purlin_spaces,
        "actual_purlin_spacing_mm": slope_length / purlin_spaces,
        "brace_panels_per_slope": panel_count,
        "purlin_spaces_per_brace_panel": panel_sizes,
        "maximum_purlin_interval": max(panel_sizes),
    }


def roof_brace_pairs(purlin_spaces_per_slope, roof_type, panel_sizes):
    """Return purlin-point index pairs for the calculated bracing panels."""
    spaces = int(purlin_spaces_per_slope)
    sizes = [int(size) for size in panel_sizes]

    def pairs_from(start, sequence):
        pairs = []
        current = start
        for size in sequence:
            pairs.append((current, current + size))
            current += size
        return pairs

    left = pairs_from(0, sizes)
    if str(roof_type) != "Duo Pitched":
        return left
    # Point ordering is left eave -> apex -> right eave. Reverse the panel
    # sizes after the apex to keep the two slopes geometrically symmetric.
    return left + pairs_from(spaces, reversed(sizes))
