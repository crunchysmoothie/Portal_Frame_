"""Internal wind-pressure coefficients for enclosed buildings.

Final-design wall openings are entered for the four physical wall faces.  The
calculation is repeated for both senses of each principal wind direction and
the resulting maximum/minimum cpi values are used by the existing wind-case
envelope.  Openings are assumed to be uniformly distributed over each face.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


FACES = ("side_1", "side_2", "gable_1", "gable_2")


def _number(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite value greater than or equal to zero.")
    return result


def normalize_design_mode(value: Any) -> str:
    text = str(value or "Prelim").strip().lower().replace("_", " ")
    if text in {"prelim", "preliminary"}:
        return "Prelim"
    if text in {"final", "final design"}:
        return "Final design"
    raise ValueError("wind_design_mode must be 'Prelim' or 'Final design'.")


def wall_face_areas_m2(wind: Mapping[str, Any]) -> dict[str, float]:
    width = _number(wind.get("gable_width"), "gable_width")
    length = _number(wind.get("building_length"), "building_length")
    eaves = _number(wind.get("eaves_height"), "eaves_height")
    apex = _number(wind.get("apex_height"), "apex_height")
    # Geometry in wind_data is stored in metres.
    side_area = length * eaves
    roof_type = wind.get("building_roof", "Duo Pitched")
    if roof_type == "Duo Pitched":
        gable_area = width * eaves + width * max(apex - eaves, 0.0) / 2
    else:
        gable_area = width * (eaves + apex) / 2
    return {
        "side_1": side_area,
        "side_2": side_area,
        "gable_1": gable_area,
        "gable_2": gable_area,
    }


def _parallel_wall_cpe(depth: float, height: float) -> float:
    # Uniform-opening average of wall zones A/B/C using their clause zone
    # extents. Local A/B coefficients remain in the external-pressure model.
    edge = min(depth, 2 * height)
    zone_a = edge / 5
    zone_b = min(4 * edge / 5, depth - zone_a)
    zone_c = max(depth - zone_a - zone_b, 0.0)
    return (-1.2 * zone_a - 0.8 * zone_b - 0.5 * zone_c) / depth


def _wall_cpe(h_over_d: float, windward: bool) -> float:
    ratio = min(max(h_over_d, 0.25), 1.0)
    if windward:
        return 0.70 + (ratio - 0.25) / 0.75 * 0.10
    return -0.30 + (ratio - 0.25) / 0.75 * -0.20


def _direction_face_cpe(wind: Mapping[str, Any], direction: str, reverse: bool) -> dict[str, float]:
    height = _number(wind.get("apex_height"), "apex_height")
    width = _number(wind.get("gable_width"), "gable_width")
    length = _number(wind.get("building_length"), "building_length")
    if direction == "0":
        first, second = "side_1", "side_2"
        parallel = ("gable_1", "gable_2")
        depth = width
    elif direction == "90":
        first, second = "gable_1", "gable_2"
        parallel = ("side_1", "side_2")
        depth = length
    else:
        raise ValueError("direction must be '0' or '90'.")
    if reverse:
        first, second = second, first
    h_over_d = height / depth
    result = {face: _parallel_wall_cpe(depth, height) for face in parallel}
    result[first] = _wall_cpe(h_over_d, True)
    result[second] = _wall_cpe(h_over_d, False)
    return result


def _chart_cpi(mu: float, h_over_d: float) -> float:
    """Interpolate SANS 10160-3 Figure 16 for a building without a dominant face."""

    mu = min(max(mu, 0.33), 1.0)
    # Both bounding curves pass through (0.33, +0.35), become horizontal at
    # mu=0.90, and end at -0.30 and -0.50 respectively.
    fraction = min(max((mu - 0.33) / (0.90 - 0.33), 0.0), 1.0)
    cpi_low_building = 0.35 + fraction * (-0.30 - 0.35)  # h/d <= 0.25
    cpi_tall_building = 0.35 + fraction * (-0.50 - 0.35)  # h/d >= 1.00
    height_fraction = min(max((h_over_d - 0.25) / 0.75, 0.0), 1.0)
    return cpi_low_building + height_fraction * (cpi_tall_building - cpi_low_building)


def _dominant_face(openings: Mapping[str, float]) -> tuple[str | None, float | None]:
    total = sum(openings.values())
    for face, area in openings.items():
        others = total - area
        if area <= 0:
            continue
        if others == 0:
            return face, math.inf
        ratio = area / others
        if ratio >= 2.0:
            return face, ratio
    return None, None


def _one_direction_cpi(
    openings: Mapping[str, float], face_cpe: Mapping[str, float], h_over_d: float,
) -> tuple[float, dict[str, Any]]:
    dominant, ratio = _dominant_face(openings)
    if dominant is not None:
        factor = 0.90 if math.isinf(ratio) or ratio >= 3 else 0.75 + (ratio - 2) * 0.15
        cpi = factor * face_cpe[dominant]
        return cpi, {
            "wall_type": "Dominant",
            "dominant_face": dominant,
            "dominance_ratio": None if math.isinf(ratio) else ratio,
            "dominant_factor": factor,
            "mu": None,
        }

    total = sum(openings.values())
    if total <= 0:
        raise ValueError("Final design requires at least one non-zero wall opening area.")
    negative = sum(area for face, area in openings.items() if face_cpe[face] <= 0)
    mu = negative / total
    return _chart_cpi(mu, h_over_d), {
        "wall_type": "Non-dominant",
        "dominant_face": None,
        "dominance_ratio": None,
        "dominant_factor": None,
        "mu": mu,
    }


def resolve_internal_pressure(wind: Mapping[str, Any]) -> dict[str, Any]:
    mode = normalize_design_mode(wind.get("wind_design_mode", "Prelim"))
    if wind.get("building_type") == "Canopy":
        return {"mode": mode, "applicable": False, "reason": "Canopy net coefficients apply."}
    if mode == "Prelim":
        return {
            "mode": mode,
            "applicable": True,
            "basis": "Preliminary envelope",
            "directions": {
                "0": {"maximum_cpi": 0.2, "minimum_cpi": -0.3},
                "90": {"maximum_cpi": 0.2, "minimum_cpi": -0.3},
            },
        }

    raw = wind.get("opening_areas_m2")
    if not isinstance(raw, Mapping) or any(face not in raw for face in FACES):
        raise ValueError(
            "Final design requires opening_areas_m2 for side_1, side_2, gable_1 and gable_2."
        )
    openings = {face: _number(raw[face], f"opening_areas_m2.{face}") for face in FACES}
    face_areas = wall_face_areas_m2(wind)
    for face in FACES:
        if openings[face] > face_areas[face] + 1e-9:
            raise ValueError(f"Opening area on {face} exceeds its gross wall area.")
    highly_open = [face for face in FACES if face_areas[face] and openings[face] / face_areas[face] > 0.30]
    if len(highly_open) >= 2:
        raise ValueError(
            "At least two wall faces are more than 30% open; the enclosed-building pressure model is not applicable."
        )

    if sum(openings.values()) <= 0:
        return {
            "mode": mode,
            "applicable": True,
            "basis": "No estimated openings; conservative envelope",
            "opening_areas_m2": openings,
            "wall_face_areas_m2": face_areas,
            "roof_openings_assumed_m2": 0.0,
            "directions": {
                "0": {"maximum_cpi": 0.2, "minimum_cpi": -0.3},
                "90": {"maximum_cpi": 0.2, "minimum_cpi": -0.3},
            },
        }

    directions: dict[str, Any] = {}
    height = _number(wind.get("apex_height"), "apex_height")
    depths = {"0": _number(wind.get("gable_width"), "gable_width"),
              "90": _number(wind.get("building_length"), "building_length")}
    for direction in ("0", "90"):
        senses = []
        for reverse in (False, True):
            cpi, detail = _one_direction_cpi(
                openings, _direction_face_cpe(wind, direction, reverse), height / depths[direction]
            )
            senses.append({"sense": "reverse" if reverse else "forward", "cpi": cpi, **detail})
        # Include cpi=0 because it must also be considered where the calculated
        # internal pressure would act favourably for the effect under review.
        values = [0.0, *(item["cpi"] for item in senses)]
        directions[direction] = {
            "maximum_cpi": max(values),
            "minimum_cpi": min(values),
            "senses": senses,
            "zero_case_included": True,
        }
    return {
        "mode": mode,
        "applicable": True,
        "basis": "Wall-opening calculation",
        "opening_areas_m2": openings,
        "wall_face_areas_m2": face_areas,
        "roof_openings_assumed_m2": 0.0,
        "uniform_opening_distribution_assumed": True,
        "directions": directions,
    }


def pressure_coefficients(wind: Mapping[str, Any], direction: str) -> tuple[float, float]:
    result = wind.get("internal_pressure") or resolve_internal_pressure(wind)
    values = result.get("directions", {}).get(direction, {})
    return float(values.get("maximum_cpi", 0.2)), float(values.get("minimum_cpi", -0.3))
