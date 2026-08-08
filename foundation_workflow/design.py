"""Post-analysis isolated pad-foundation design.

The module uses stored portal-frame reactions.  Service combinations size/check
the soil contact using a user-supplied permissible bearing pressure.  ULS
combinations check reinforced-concrete flexure, one-way shear and punching
shear using either EN 1992-1-1 (EC2) or SANS 10100-1 rules.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


FOUNDATION_STANDARDS = (
    "EN 1992-1-1 (EC2)",
    "SANS 10100-1",
)
FOUNDATION_SLIDING_OPTIONS = (
    "Sliding Resisted",
    "Sliding Not Resisted",
)
FOUNDATION_PASSIVE_RESISTANCE_OPTIONS = (
    "Passive Resistance Excluded",
    "Passive Resistance Included",
)
FAILED_NUMERIC = 1e12
DESIGN_CONCRETE_STRENGTH_MPA = 25.0
# TODO(advanced-finishes): Create printable foundation calculation sheets from
# the completed foundation design result.

DEFAULT_FOUNDATION_VALUES: dict[str, Any] = {
    "foundation_standard": "SANS 10100-1",
    "foundation_length_m": "2.4",
    "foundation_width_m": "2.0",
    "foundation_thickness_mm": "500",
    "foundation_loaded_length_mm": "400",
    "foundation_loaded_width_mm": "400",
    "foundation_pedestal_height_m": "0.6",
    "foundation_concrete_strength_mpa": "25",
    "foundation_rebar_strength_mpa": "500",
    "foundation_bar_diameter_mm": "16",
    "foundation_bar_spacing_mm": "200",
    "foundation_cover_mm": "75",
    "foundation_permissible_bearing_kpa": "150",
    "foundation_base_depth_m": "0.8",
    "foundation_soil_cover_depth_m": "0.3",
    "foundation_soil_unit_weight_kn_m3": "18",
    "foundation_friction_coefficient": "0.45",
    "foundation_sliding_resistance": "Sliding Not Resisted",
    "foundation_soil_friction_angle_deg": "25",
    "foundation_passive_resistance": "Passive Resistance Excluded",
    "foundation_passive_mobilisation_factor": "0.75",
    "foundation_passive_uls_partial_factor": "1.4",
    "foundation_stability_self_weight_factor": "0.9",
    "foundation_uls_self_weight_factor": "1.2",
    "foundation_uls_sliding_required_sf": "1.5",
}

AUTOMATIC_FOUNDATION_ASSUMPTIONS: dict[str, float | str] = {
    "foundation_standard": "SANS 10100-1",
    "foundation_loaded_length_mm": 400.0,
    "foundation_loaded_width_mm": 400.0,
    "foundation_pedestal_height_m": 0.6,
    "foundation_concrete_strength_mpa": DESIGN_CONCRETE_STRENGTH_MPA,
    "foundation_rebar_strength_mpa": 500.0,
    "foundation_bar_diameter_mm": 16.0,
    "foundation_bar_spacing_mm": 150.0,
    "foundation_cover_mm": 75.0,
    "soil_cover_above_footing_m": 0.5,
    "foundation_friction_coefficient": 0.35,
    "foundation_soil_friction_angle_deg": 25.0,
    "foundation_passive_resistance": "Passive Resistance Excluded",
    "foundation_passive_mobilisation_factor": 0.75,
    "foundation_passive_uls_partial_factor": 1.4,
    "foundation_stability_self_weight_factor": 0.9,
    "foundation_uls_self_weight_factor": 1.2,
    "uls_sliding_required_sf": 1.5,
    "minimum_overturning_safety_factor": 1.5,
    "maximum_plan_aspect_ratio": 1.5,
}


class FoundationInputError(ValueError):
    """Raised when post-analysis foundation inputs are invalid."""

    def __init__(self, errors: Mapping[str, str]):
        self.errors = dict(errors)
        super().__init__("Foundation design input validation failed")


def _validated_inputs(raw: Mapping[str, Any]) -> dict[str, float | str]:
    errors: dict[str, str] = {}

    def number(
        key: str,
        *,
        minimum: float = 0.0,
        maximum: float | None = None,
        strictly_positive: bool = True,
        default: Any = "",
    ) -> float:
        try:
            value = float(raw.get(key, default))
        except (TypeError, ValueError):
            errors[key] = "Enter a number."
            return 0.0
        if not math.isfinite(value):
            errors[key] = "Enter a finite number."
        elif strictly_positive and value <= minimum:
            errors[key] = f"Enter a value greater than {minimum:g}."
        elif not strictly_positive and value < minimum:
            errors[key] = f"Enter a value of at least {minimum:g}."
        elif maximum is not None and value > maximum:
            errors[key] = f"Enter a value no greater than {maximum:g}."
        return value

    standard = str(raw.get("foundation_standard", "")).strip()
    if standard not in FOUNDATION_STANDARDS:
        errors["foundation_standard"] = (
            f"Choose one of: {', '.join(FOUNDATION_STANDARDS)}."
        )
    length = number("foundation_length_m")
    width = number("foundation_width_m")
    thickness = number("foundation_thickness_mm")
    loaded_length = number("foundation_loaded_length_mm")
    loaded_width = number("foundation_loaded_width_mm")
    pedestal_height = number(
        "foundation_pedestal_height_m",
        minimum=0,
        strictly_positive=False,
        default=0.6,
    )
    concrete = number(
        "foundation_concrete_strength_mpa",
        minimum=20,
        maximum=80,
    )
    rebar = number("foundation_rebar_strength_mpa", minimum=250)
    diameter = number("foundation_bar_diameter_mm", minimum=6)
    spacing = number("foundation_bar_spacing_mm", minimum=50)
    cover = number("foundation_cover_mm", minimum=25)
    bearing = number("foundation_permissible_bearing_kpa")
    base_depth = number(
        "foundation_base_depth_m", minimum=0, strictly_positive=False
    )
    soil_cover_depth = (
        number(
            "foundation_soil_cover_depth_m", minimum=0, strictly_positive=False
        )
        if "foundation_soil_cover_depth_m" in raw
        else 0.0
    )
    soil_weight = number("foundation_soil_unit_weight_kn_m3")
    friction = number(
        "foundation_friction_coefficient",
        minimum=0,
        maximum=1.5,
        strictly_positive=False,
    )
    soil_friction_angle = number(
        "foundation_soil_friction_angle_deg",
        minimum=0,
        maximum=60,
        strictly_positive=False,
        default=25.0,
    )
    passive_mobilisation = number(
        "foundation_passive_mobilisation_factor",
        minimum=0,
        maximum=1,
        strictly_positive=False,
        default=0.5,
    )
    passive_uls_partial_factor = number(
        "foundation_passive_uls_partial_factor",
        minimum=1,
        default=1.4,
    )
    stability_self_weight_factor = number(
        "foundation_stability_self_weight_factor",
        minimum=0,
        default=0.9,
    )
    uls_self_weight_factor = number(
        "foundation_uls_self_weight_factor",
        minimum=0,
        default=1.2,
    )
    uls_sliding_required_sf = number(
        "foundation_uls_sliding_required_sf",
        minimum=0,
        default=1.0,
    )
    passive_resistance = str(
        raw.get(
            "foundation_passive_resistance",
            "Passive Resistance Excluded",
        )
    ).strip()
    if passive_resistance not in FOUNDATION_PASSIVE_RESISTANCE_OPTIONS:
        errors["foundation_passive_resistance"] = (
            f"Choose one of: {', '.join(FOUNDATION_PASSIVE_RESISTANCE_OPTIONS)}."
        )
    sliding_resistance = str(
        raw.get("foundation_sliding_resistance", "Sliding Not Resisted")
    ).strip()
    if sliding_resistance in {"Yes", "True", "true"}:
        sliding_resistance = "Sliding Resisted"
    elif sliding_resistance in {"No", "False", "false"}:
        sliding_resistance = "Sliding Not Resisted"
    if sliding_resistance not in FOUNDATION_SLIDING_OPTIONS:
        errors["foundation_sliding_resistance"] = (
            f"Choose one of: {', '.join(FOUNDATION_SLIDING_OPTIONS)}."
        )

    if loaded_length >= length * 1000:
        errors["foundation_loaded_length_mm"] = (
            "Loaded length must be smaller than the footing length."
        )
    if loaded_width >= width * 1000:
        errors["foundation_loaded_width_mm"] = (
            "Loaded width must be smaller than the footing width."
        )
    effective_depth = thickness - cover - diameter / 2
    if effective_depth <= 0:
        errors["foundation_thickness_mm"] = (
            "Thickness must exceed cover plus half the bar diameter."
        )
    if "foundation_soil_cover_depth_m" not in raw and base_depth * 1000 < thickness:
        errors["foundation_base_depth_m"] = (
            "Depth to the footing base must be at least the footing thickness."
        )
    if errors:
        raise FoundationInputError(errors)
    return {
        "standard": standard,
        "length_m": length,
        "width_m": width,
        "thickness_mm": thickness,
        "loaded_length_mm": loaded_length,
        "loaded_width_mm": loaded_width,
        "pedestal_height_m": pedestal_height,
        "concrete_strength_mpa": concrete,
        "rebar_strength_mpa": rebar,
        "bar_diameter_mm": diameter,
        "bar_spacing_mm": spacing,
        "cover_mm": cover,
        "effective_depth_mm": effective_depth,
        "permissible_bearing_kpa": bearing,
        "base_depth_m": base_depth,
        "soil_cover_depth_m": (
            soil_cover_depth
            if "foundation_soil_cover_depth_m" in raw
            else max(base_depth - thickness / 1000.0, 0.0)
        ),
        "soil_unit_weight_kn_m3": soil_weight,
        "friction_coefficient": friction,
        "sliding_resistance": sliding_resistance,
        "soil_friction_angle_deg": soil_friction_angle,
        "passive_resistance": passive_resistance,
        "passive_mobilisation_factor": passive_mobilisation,
        "passive_uls_partial_factor": passive_uls_partial_factor,
        "stability_self_weight_factor": stability_self_weight_factor,
        "uls_self_weight_factor": uls_self_weight_factor,
        "uls_sliding_required_sf": uls_sliding_required_sf,
    }


def bearing_pressures(
    vertical_kn: float,
    moment_knm: float,
    length_m: float,
    width_m: float,
) -> dict[str, float | str]:
    """Return elastic/triangular soil pressure for uniaxial eccentricity."""

    if vertical_kn <= 0:
        return {
            "contact": "none",
            "eccentricity_m": FAILED_NUMERIC,
            "contact_length_m": 0.0,
            "q_min_kpa": 0.0,
            "q_max_kpa": 0.0,
        }
    eccentricity = abs(moment_knm) / vertical_kn
    if eccentricity <= length_m / 6 + 1e-12:
        average = vertical_kn / (length_m * width_m)
        variation = 6 * abs(moment_knm) / (width_m * length_m**2)
        return {
            "contact": "full",
            "eccentricity_m": eccentricity,
            "contact_length_m": length_m,
            "q_min_kpa": max(average - variation, 0.0),
            "q_max_kpa": average + variation,
        }
    if eccentricity < length_m / 2:
        contact_length = 3 * (length_m / 2 - eccentricity)
        return {
            "contact": "partial",
            "eccentricity_m": eccentricity,
            "contact_length_m": contact_length,
            "q_min_kpa": 0.0,
            "q_max_kpa": 2 * vertical_kn / (width_m * contact_length),
        }
    return {
        "contact": "resultant_outside_base",
        "eccentricity_m": eccentricity,
        "contact_length_m": 0.0,
        "q_min_kpa": 0.0,
        "q_max_kpa": FAILED_NUMERIC,
    }


def _flexural_steel(
    moment_knm_per_m: float,
    d_mm: float,
    fck_mpa: float,
    fyk_mpa: float,
    standard: str,
) -> tuple[float, float]:
    """Return required and minimum steel, both in mm2/m."""

    if standard == FOUNDATION_STANDARDS[0]:
        fctm = (
            0.3 * fck_mpa ** (2 / 3)
            if fck_mpa <= 50
            else 2.12 * math.log(1 + fck_mpa / 10)
        )
        minimum = max(
            0.26 * fctm / fyk_mpa, 0.0013
        ) * 1000 * d_mm
    else:
        minimum = 0.0013 * 1000 * d_mm

    if moment_knm_per_m <= 0:
        required = 0.0
    elif standard == FOUNDATION_STANDARDS[0]:
        k_value = (
            moment_knm_per_m * 1e6
            / (1000.0 * d_mm**2 * fck_mpa)
        )
        if k_value >= 1 / 3.53:
            required = FAILED_NUMERIC
        else:
            lever_arm = min(
                0.95 * d_mm,
                d_mm / 2 * (1 + math.sqrt(max(0.0, 1 - 3.53 * k_value))),
            )
            required = moment_knm_per_m * 1e6 / (
                0.87 * fyk_mpa * lever_arm
            )
    else:
        lever_arm = 0.95 * d_mm
        required = moment_knm_per_m * 1e6 / (
            0.87 * fyk_mpa * lever_arm
        )
    return max(required, minimum), minimum


def _concrete_shear_capacity(
    standard: str,
    fck_mpa: float,
    d_mm: float,
    reinforcement_mm2_per_m: float,
) -> float:
    ratio = min(
        max(reinforcement_mm2_per_m / (1000 * d_mm), 0.0013),
        0.02,
    )
    if standard == FOUNDATION_STANDARDS[0]:
        k_value = min(1 + math.sqrt(200 / d_mm), 2.0)
        calculated = 0.12 * k_value * (
            100 * ratio * fck_mpa
        ) ** (1 / 3)
        minimum = 0.035 * k_value ** 1.5 * math.sqrt(fck_mpa)
        return max(calculated, minimum)
    return (
        0.75
        / 1.4
        * (min(fck_mpa, 40.0) / 25.0) ** (1 / 3)
        * (100 * ratio) ** (1 / 3)
        * (400 / d_mm) ** 0.25
    )


def _check(name: str, demand: float, capacity: float, units: str) -> dict[str, Any]:
    utilisation = demand / capacity if capacity > 0 else FAILED_NUMERIC
    if not math.isfinite(utilisation):
        utilisation = FAILED_NUMERIC
    return {
        "name": name,
        "demand": demand,
        "capacity": capacity,
        "units": units,
        "utilisation": utilisation,
        "status": "PASS" if math.isfinite(utilisation) and utilisation <= 1 else "FAIL",
    }


def _reaction_sets(
    snapshot: Mapping[str, Any],
) -> tuple[list[dict], list[dict], list[dict]]:
    input_data = snapshot["input_data"]
    results = snapshot["results"]
    uls_names = {
        str(item["name"]) for item in input_data.get("load_combinations", [])
    }
    sls_names = {
        str(item["name"])
        for item in input_data.get("serviceability_load_combinations", [])
    }
    reactions = [dict(item) for item in results.get("reactions", [])]
    characteristic = [
        dict(item)
        for item in results.get("foundation_characteristic_reactions", [])
    ]
    return (
        [item for item in reactions if item["load_combination"] in uls_names],
        [item for item in reactions if item["load_combination"] in sls_names],
        characteristic,
    )


def _check_pad_foundations(
    snapshot: Mapping[str, Any], raw_inputs: Mapping[str, Any]
) -> dict[str, Any]:
    """Design identical isolated pad footings at every portal support."""

    values = _validated_inputs(raw_inputs)
    uls_reactions, sls_reactions, characteristic_reactions = _reaction_sets(
        snapshot
    )
    if not uls_reactions:
        raise ValueError("The analysis snapshot does not contain ULS reactions.")
    if not sls_reactions:
        raise ValueError(
            "The analysis snapshot does not contain SLS reactions; rerun the "
            "portal analysis with the current engine."
        )
    if not characteristic_reactions:
        raise ValueError(
            "The analysis snapshot does not contain characteristic foundation "
            "reactions; rerun the portal analysis with the current engine."
        )

    standard = str(values["standard"])
    length = float(values["length_m"])
    width = float(values["width_m"])
    thickness_m = float(values["thickness_mm"]) / 1000
    loaded_length = float(values["loaded_length_mm"]) / 1000
    loaded_width = float(values["loaded_width_mm"]) / 1000
    pedestal_height = float(values["pedestal_height_m"])
    d_mm = float(values["effective_depth_mm"])
    footprint = length * width
    footing_weight = footprint * thickness_m * 24.0
    cover_depth = max(float(values["soil_cover_depth_m"]), 0.0)
    soil_cover_weight = max(
        footprint - loaded_length * loaded_width, 0.0
    ) * cover_depth * float(values["soil_unit_weight_kn_m3"])
    pedestal_weight = (
        loaded_length * loaded_width * pedestal_height * 24.0
    )
    stabilising_weight = footing_weight + soil_cover_weight + pedestal_weight
    load_transfer_height = pedestal_height + thickness_m
    passive_included = (
        values["passive_resistance"] == "Passive Resistance Included"
    )
    sliding_check_required = (
        values["sliding_resistance"] == "Sliding Not Resisted"
    )
    passive = passive_sliding_resistance(
        float(values["soil_unit_weight_kn_m3"]),
        float(values["soil_friction_angle_deg"]),
        float(values["base_depth_m"]),
        width,
        float(values["passive_mobilisation_factor"]),
    )
    passive_characteristic_resistance = (
        float(passive["mobilised_resistance_kN"])
        if passive_included and sliding_check_required
        else 0.0
    )
    passive_uls_resistance = (
        passive_characteristic_resistance
        / float(values["passive_uls_partial_factor"])
    )
    provided_steel = (
        math.pi * float(values["bar_diameter_mm"]) ** 2 / 4
        * 1000
        / float(values["bar_spacing_mm"])
    )
    concrete_shear = _concrete_shear_capacity(
        standard,
        float(values["concrete_strength_mpa"]),
        d_mm,
        provided_steel,
    )

    nodes = sorted({
        item["node"]
        for item in (
            uls_reactions + sls_reactions + characteristic_reactions
        )
    })
    support_results = []
    for node in nodes:
        node_uls = [item for item in uls_reactions if item["node"] == node]
        node_characteristic = [
            item for item in characteristic_reactions if item["node"] == node
        ]

        service_rows = []
        for reaction in node_characteristic:
            vertical = float(reaction["fy"]) + stabilising_weight
            transferred_moment = (
                float(reaction["mz"])
                - float(reaction["fx"]) * load_transfer_height
            )
            pressures = bearing_pressures(
                vertical, transferred_moment, length, width
            )
            horizontal = abs(float(reaction["fx"]))
            friction_resistance = (
                float(values["friction_coefficient"]) * max(vertical, 0.0)
                if sliding_check_required else 0.0
            )
            sliding_capacity = (
                friction_resistance + passive_characteristic_resistance
                if sliding_check_required else 0.0
            )
            sliding_safety_factor = (
                sliding_capacity / horizontal
                if sliding_check_required and horizontal > 1e-9
                else math.inf
            )
            overturning_moment = abs(transferred_moment)
            overturning_safety_factor = (
                max(vertical, 0.0) * length / 2.0 / overturning_moment
                if overturning_moment > 1e-9
                else math.inf
            )
            service_rows.append({
                "combination": reaction["load_combination"],
                "vertical_reaction_kN": float(reaction["fy"]),
                "horizontal_reaction_kN": float(reaction["fx"]),
                "support_moment_kNm": float(reaction["mz"]),
                "transferred_base_moment_kNm": transferred_moment,
                **pressures,
                "bearing_utilisation": (
                    float(pressures["q_max_kpa"])
                    / float(values["permissible_bearing_kpa"])
                ),
                "sliding_utilisation": (
                    horizontal / sliding_capacity
                    if sliding_check_required and sliding_capacity > 0
                    else 0.0
                ),
                "sliding_safety_factor": sliding_safety_factor,
                "sliding_normal_force_kN": max(vertical, 0.0),
                "sliding_friction_resistance_kN": friction_resistance,
                "sliding_passive_resistance_kN": (
                    passive_characteristic_resistance
                ),
                "sliding_total_resistance_kN": sliding_capacity,
                "overturning_moment_kNm": overturning_moment,
                "overturning_safety_factor": overturning_safety_factor,
                "sliding_status": (
                    "RESISTED_EXTERNALLY"
                    if not sliding_check_required
                    else (
                        "PASS"
                        if sliding_safety_factor >= 1.0
                        else "FAIL"
                    )
                ),
                "uplift_status": "PASS" if vertical > 0 else "FAIL",
            })
        governing_bearing = max(
            service_rows, key=lambda item: item["bearing_utilisation"]
        )
        governing_sliding = max(
            service_rows, key=lambda item: item["sliding_utilisation"]
        )
        governing_uplift = min(
            service_rows,
            key=lambda item: (
                item["vertical_reaction_kN"] + stabilising_weight
            ),
        )

        structural_rows = []
        for reaction in node_uls:
            column_vertical = max(float(reaction["fy"]), 0.0)
            uls_foundation_weight = (
                float(values["uls_self_weight_factor"])
                * stabilising_weight
            )
            foundation_vertical = (
                float(reaction["fy"]) + uls_foundation_weight
            )
            transferred_moment = (
                float(reaction["mz"])
                - float(reaction["fx"]) * load_transfer_height
            )
            pressures = bearing_pressures(
                foundation_vertical,
                transferred_moment,
                length,
                width,
            )
            contact_equilibrium = (
                pressures["contact"]
                not in {"none", "resultant_outside_base"}
            )
            uniform_stabilising_pressure = uls_foundation_weight / footprint
            design_q_max = (
                max(
                    float(pressures["q_max_kpa"])
                    - uniform_stabilising_pressure,
                    0.0,
                )
                if contact_equilibrium else 0.0
            )
            design_q_min = (
                max(
                    float(pressures["q_min_kpa"])
                    - uniform_stabilising_pressure,
                    0.0,
                )
                if contact_equilibrium else 0.0
            )
            projection_x = (length - loaded_length) / 2
            projection_y = (width - loaded_width) / 2
            moment_x = design_q_max * projection_x**2 / 2
            moment_y = design_q_max * projection_y**2 / 2
            required_x, minimum_x = _flexural_steel(
                moment_x,
                d_mm,
                float(values["concrete_strength_mpa"]),
                float(values["rebar_strength_mpa"]),
                standard,
            )
            required_y, minimum_y = _flexural_steel(
                moment_y,
                d_mm,
                float(values["concrete_strength_mpa"]),
                float(values["rebar_strength_mpa"]),
                standard,
            )

            shear_distance = (
                d_mm / 1000
                if standard == FOUNDATION_STANDARDS[0]
                else 1.5 * d_mm / 1000
            )
            shear_x = design_q_max * max(projection_x - shear_distance, 0.0)
            shear_y = design_q_max * max(projection_y - shear_distance, 0.0)
            shear_stress_x = shear_x / d_mm
            shear_stress_y = shear_y / d_mm

            punching_distance_mm = (
                2.0 * d_mm
                if standard == FOUNDATION_STANDARDS[0]
                else 1.5 * d_mm
            )
            control_length_mm = min(
                float(values["loaded_length_mm"]) + 2 * punching_distance_mm,
                length * 1000,
            )
            control_width_mm = min(
                float(values["loaded_width_mm"]) + 2 * punching_distance_mm,
                width * 1000,
            )
            control_perimeter_mm = 2 * (
                control_length_mm + control_width_mm
            )
            inside_area_m2 = control_length_mm * control_width_mm / 1e6
            punching_force = max(
                column_vertical - design_q_min * inside_area_m2, 0.0
            )
            punching_stress = (
                punching_force * 1000
                / (control_perimeter_mm * d_mm)
            )
            face_perimeter = 2 * (
                float(values["loaded_length_mm"])
                + float(values["loaded_width_mm"])
            )
            face_stress = (
                column_vertical * 1000 / (face_perimeter * d_mm)
                if face_perimeter > 0 else math.inf
            )
            fck = float(values["concrete_strength_mpa"])
            if standard == FOUNDATION_STANDARDS[0]:
                face_capacity = 0.5 * 0.6 * (1 - fck / 250) * fck / 1.5
            else:
                face_capacity = min(0.75 * math.sqrt(fck), 4.75)

            checks = [
                {
                    "name": "ULS soil contact equilibrium",
                    "demand": (
                        0.0 if contact_equilibrium else 1.0
                    ),
                    "capacity": 1.0,
                    "units": "",
                    "utilisation": (
                        0.0 if contact_equilibrium else FAILED_NUMERIC
                    ),
                    "status": (
                        "PASS" if contact_equilibrium else "FAIL"
                    ),
                },
                _check("Flexure - frame direction", required_x, provided_steel, "mm2/m"),
                _check("Flexure - transverse direction", required_y, provided_steel, "mm2/m"),
                _check("One-way shear - frame direction", shear_stress_x, concrete_shear, "MPa"),
                _check("One-way shear - transverse direction", shear_stress_y, concrete_shear, "MPa"),
                _check("Punching shear - control perimeter", punching_stress, concrete_shear, "MPa"),
                _check("Punching shear - loaded face", face_stress, face_capacity, "MPa"),
            ]
            structural_rows.append({
                "combination": reaction["load_combination"],
                "vertical_reaction_kN": float(reaction["fy"]),
                "uls_foundation_weight_kN": uls_foundation_weight,
                "uls_net_vertical_kN": foundation_vertical,
                "support_moment_kNm": float(reaction["mz"]),
                "transferred_base_moment_kNm": transferred_moment,
                "horizontal_reaction_kN": float(reaction["fx"]),
                "contact": pressures["contact"],
                "q_min_kpa": float(pressures["q_min_kpa"]),
                "q_max_kpa": float(pressures["q_max_kpa"]),
                "design_q_min_kpa": design_q_min,
                "design_q_max_kpa": design_q_max,
                "design_moment_frame_knm_per_m": moment_x,
                "design_moment_transverse_knm_per_m": moment_y,
                "required_steel_frame_mm2_per_m": required_x,
                "required_steel_transverse_mm2_per_m": required_y,
                "minimum_steel_frame_mm2_per_m": minimum_x,
                "minimum_steel_transverse_mm2_per_m": minimum_y,
                "checks": checks,
                "governing_utilisation": max(
                    check["utilisation"] for check in checks
                ),
            })

        stability_rows = []
        for reaction in node_characteristic:
            foundation_vertical = (
                float(reaction["fy"])
                + float(values["stability_self_weight_factor"])
                * stabilising_weight
            )
            transferred_moment = (
                float(reaction["mz"])
                - float(reaction["fx"]) * load_transfer_height
            )
            horizontal = abs(float(reaction["fx"]))
            friction_resistance = (
                float(values["friction_coefficient"])
                * max(foundation_vertical, 0.0)
                if sliding_check_required else 0.0
            )
            total_sliding_resistance = (
                friction_resistance + passive_uls_resistance
                if sliding_check_required else 0.0
            )
            sliding_safety_factor = (
                total_sliding_resistance / horizontal
                if sliding_check_required and horizontal > 1e-9
                else math.inf
            )
            overturning_moment = abs(transferred_moment)
            stabilising_moment = (
                max(foundation_vertical, 0.0) * length / 2.0
            )
            overturning_safety_factor = (
                stabilising_moment / overturning_moment
                if overturning_moment > 1e-9 else math.inf
            )
            stability_rows.append({
                "combination": reaction["load_combination"],
                "vertical_reaction_kN": float(reaction["fy"]),
                "horizontal_reaction_kN": float(reaction["fx"]),
                "support_moment_kNm": float(reaction["mz"]),
                "transferred_base_moment_kNm": transferred_moment,
                "foundation_vertical_kN": foundation_vertical,
                "sliding_normal_force_kN": max(foundation_vertical, 0.0),
                "sliding_friction_resistance_kN": friction_resistance,
                "sliding_passive_resistance_kN": passive_uls_resistance,
                "sliding_total_resistance_kN": total_sliding_resistance,
                "sliding_safety_factor": sliding_safety_factor,
                "overturning_moment_kNm": overturning_moment,
                "stabilising_moment_kNm": stabilising_moment,
                "overturning_safety_factor": overturning_safety_factor,
            })
        governing_structural = max(
            structural_rows, key=lambda item: item["governing_utilisation"]
        )
        governing_service_overturning = min(
            service_rows,
            key=lambda item: item["overturning_safety_factor"],
        )
        governing_sliding_uls = min(
            stability_rows,
            key=lambda item: item["sliding_safety_factor"],
        )
        governing_overturning_uls = min(
            stability_rows,
            key=lambda item: item["overturning_safety_factor"],
        )

        bearing_status = (
            "PASS"
            if (
                math.isfinite(governing_bearing["bearing_utilisation"])
                and governing_bearing["bearing_utilisation"] <= 1
                and governing_bearing["contact"] != "resultant_outside_base"
            )
            else "FAIL"
        )
        sliding_status = (
            "RESISTED_EXTERNALLY"
            if not sliding_check_required
            else (
                "PASS"
                if (
                    math.isfinite(governing_sliding["sliding_utilisation"])
                    and governing_sliding["sliding_utilisation"] <= 1
                )
                else "FAIL"
            )
        )
        structural_status = (
            "PASS"
            if governing_structural["governing_utilisation"] <= 1
            else "FAIL"
        )
        uls_stability_status = (
            "PASS"
            if (
                (
                    not sliding_check_required
                    or governing_sliding_uls["sliding_safety_factor"]
                    >= float(values["uls_sliding_required_sf"])
                )
                and governing_overturning_uls["overturning_safety_factor"]
                >= 1.5
            )
            else "FAIL"
        )
        statuses = (
            bearing_status,
            governing_uplift["uplift_status"],
            structural_status,
            uls_stability_status,
            *(
                (sliding_status,)
                if sliding_check_required
                else ()
            ),
        )
        support_results.append({
            "node": node,
            "status": "PASS" if all(item == "PASS" for item in statuses) else "FAIL",
            "serviceability": {
                "cases": service_rows,
                "bearing": {
                    "status": bearing_status,
                    "combination": governing_bearing["combination"],
                    "q_min_kpa": governing_bearing["q_min_kpa"],
                    "q_max_kpa": governing_bearing["q_max_kpa"],
                    "utilisation": governing_bearing["bearing_utilisation"],
                    "contact": governing_bearing["contact"],
                    "eccentricity_m": governing_bearing["eccentricity_m"],
                },
                "sliding": {
                    "status": sliding_status,
                    "combination": governing_sliding["combination"],
                    "utilisation": governing_sliding["sliding_utilisation"],
                    "safety_factor": governing_sliding[
                        "sliding_safety_factor"
                    ],
                    "normal_force_kN": governing_sliding[
                        "sliding_normal_force_kN"
                    ],
                    "horizontal_demand_kN": abs(
                        float(governing_sliding["horizontal_reaction_kN"])
                    ),
                    "friction_resistance_kN": governing_sliding[
                        "sliding_friction_resistance_kN"
                    ],
                    "passive_resistance_kN": governing_sliding[
                        "sliding_passive_resistance_kN"
                    ],
                    "total_resistance_kN": governing_sliding[
                        "sliding_total_resistance_kN"
                    ],
                },
                "uplift": {
                    "status": governing_uplift["uplift_status"],
                    "combination": governing_uplift["combination"],
                    "net_vertical_kN": (
                        governing_uplift["vertical_reaction_kN"]
                        + stabilising_weight
                    ),
                },
                "overturning": {
                    "combination": governing_service_overturning[
                        "combination"
                    ],
                    "safety_factor": governing_service_overturning[
                        "overturning_safety_factor"
                    ],
                },
            },
            "structural": {
                "status": structural_status,
                "cases": structural_rows,
                "combination": governing_structural["combination"],
                "provided_steel_mm2_per_m": provided_steel,
                **{
                    key: value
                    for key, value in governing_structural.items()
                    if key not in {"combination"}
                },
            },
            "uls_stability": {
                "status": uls_stability_status,
                "action_basis": "Characteristic factor-1.0 frame actions",
                "cases": stability_rows,
                "required_sliding_safety_factor": float(
                    values["uls_sliding_required_sf"]
                ),
                "required_overturning_safety_factor": 1.5,
                "sliding": {
                    "status": (
                        "RESISTED_EXTERNALLY"
                        if not sliding_check_required
                        else (
                            "PASS"
                            if governing_sliding_uls[
                                "sliding_safety_factor"
                            ] >= float(values["uls_sliding_required_sf"])
                            else "FAIL"
                        )
                    ),
                    "combination": governing_sliding_uls["combination"],
                    "safety_factor": governing_sliding_uls[
                        "sliding_safety_factor"
                    ],
                    "normal_force_kN": governing_sliding_uls[
                        "sliding_normal_force_kN"
                    ],
                    "horizontal_demand_kN": abs(
                        float(governing_sliding_uls["horizontal_reaction_kN"])
                    ),
                    "friction_resistance_kN": governing_sliding_uls[
                        "sliding_friction_resistance_kN"
                    ],
                    "passive_resistance_kN": governing_sliding_uls[
                        "sliding_passive_resistance_kN"
                    ],
                    "total_resistance_kN": governing_sliding_uls[
                        "sliding_total_resistance_kN"
                    ],
                },
                "overturning": {
                    "combination": governing_overturning_uls[
                        "combination"
                    ],
                    "safety_factor": governing_overturning_uls[
                        "overturning_safety_factor"
                    ],
                    "overturning_moment_kNm": governing_overturning_uls[
                        "overturning_moment_kNm"
                    ],
                    "stabilising_moment_kNm": governing_overturning_uls[
                        "stabilising_moment_kNm"
                    ],
                },
            },
        })

    overall = "PASS" if all(
        result["status"] == "PASS" for result in support_results
    ) else "FAIL"
    return {
        "schema_version": 1,
        "status": overall,
        "standard": standard,
        "inputs": values,
        "derived": {
            "footing_volume_m3": footprint * thickness_m,
            "footing_self_weight_kN": footing_weight,
            "soil_cover_weight_kN": soil_cover_weight,
            "pedestal_self_weight_kN": pedestal_weight,
            "stabilising_weight_kN": stabilising_weight,
            "load_transfer_height_m": load_transfer_height,
            "provided_steel_mm2_per_m": provided_steel,
            "effective_depth_mm": d_mm,
            "passive_coefficient_kp": passive["coefficient_kp"],
            "passive_characteristic_resistance_kN": passive[
                "characteristic_resistance_kN"
            ],
            "passive_mobilised_sls_resistance_kN": (
                passive_characteristic_resistance
            ),
            "passive_design_uls_resistance_kN": passive_uls_resistance,
        },
        "supports": support_results,
        "references": (
            [
                "RC Design Manual chapter 10.1: prescriptive pad-footing method and eccentric bearing pressure.",
                "EN 1992-1-1 clauses 6.2.2, 6.4 and 9.2.1.1: shear, punching shear and minimum flexural reinforcement.",
                "SANS 10161 clause 5.2.3: permissible bearing pressure is a project/geotechnical input.",
            ]
            if standard == FOUNDATION_STANDARDS[0]
            else [
                "SANS 10100-1 clauses 4.10.3, 4.4.5.2 and 4.3.4.1: pad-footing, punching and concrete shear checks.",
                "SANS 10161 clause 5.2.3: permissible bearing pressure is a project/geotechnical input.",
            ]
        ),
        "assumptions": [
            "One isolated rectangular pad is centred below each portal support.",
            "Only in-plane portal reaction Fx, Fy and Mz are applied; out-of-plane actions require a separate model.",
            "Service bearing uses footing self-weight and soil cover above the pad.",
            (
                "Pad sliding is excluded from automatic sizing because a separate "
                "external sliding restraint is specified; that restraint requires "
                "an independent design and load path."
                if not sliding_check_required
                else (
                    "Sliding resistance includes base friction plus mobilised "
                    "Rankine passive pressure against one footing face."
                    if passive_included
                    else "Passive soil resistance is excluded; base friction only is included."
                )
            ),
            (
                "Footing bearing and stability use separately stored factor-1.0 "
                "characteristic frame actions. Strength reactions are reserved "
                "for reinforced-concrete ULS checks."
            ),
            (
                "Horizontal reactions are transferred from the support level to "
                "the footing underside through the pedestal height plus footing "
                "thickness. Pedestal self-weight is included."
            ),
            (
                f"Stability foundation self-weight factor {float(values['stability_self_weight_factor']):.2f}; "
                f"ULS bearing self-weight factor {float(values['uls_self_weight_factor']):.2f}; "
                f"passive ULS partial factor {float(values['passive_uls_partial_factor']):.2f}."
            ),
            "ULS footing bending and shear exclude footing self-weight, following the pad-footing design procedure in the supplied RC manual.",
            "A single bottom reinforcement mesh is used in both directions at the entered bar diameter and spacing.",
        ],
        "warnings": [
            "Permissible bearing pressure and settlement require project-specific geotechnical confirmation.",
            (
                "Credited passive resistance requires confirmation that the soil "
                "will remain in place, is adequately compacted and drained, and "
                "can mobilise the entered resistance for the design life."
                if passive_included and sliding_check_required
                else "Passive soil resistance is not credited."
            ),
            "Anchor bolts, base plate, pedestal, dowels, development length, crack width, durability exposure and construction joints are outside this calculation.",
            "Overall building overturning and interaction between adjacent foundations are not checked by an isolated-pad calculation.",
        ],
    }


def passive_sliding_resistance(
    soil_unit_weight_kn_m3: float,
    soil_friction_angle_deg: float,
    embedment_depth_m: float,
    footing_face_width_m: float,
    mobilisation_factor: float,
) -> dict[str, float]:
    """Return Rankine passive resistance mobilised against one footing face.

    The in-plane portal reaction acts along the footing length, so the resisting
    face is the footing width. The passive wedge is calculated from ground level
    to the footing base. Cohesion and surcharge are excluded.
    """

    angle_rad = math.radians(soil_friction_angle_deg)
    coefficient = math.tan(math.pi / 4 + angle_rad / 2) ** 2
    characteristic = (
        0.5
        * soil_unit_weight_kn_m3
        * coefficient
        * embedment_depth_m**2
        * footing_face_width_m
    )
    return {
        "coefficient_kp": coefficient,
        "characteristic_resistance_kN": characteristic,
        "mobilisation_factor": mobilisation_factor,
        "mobilised_resistance_kN": mobilisation_factor * characteristic,
    }


def _automatic_user_inputs(
    raw_inputs: Mapping[str, Any],
) -> tuple[
    float, float, float, float, float, float, str, float, str, float, float
]:
    errors: dict[str, str] = {}

    def positive(key: str) -> float:
        try:
            value = float(raw_inputs.get(key, ""))
        except (TypeError, ValueError):
            errors[key] = "Enter a number."
            return 0.0
        if not math.isfinite(value) or value <= 0:
            errors[key] = "Enter a finite value greater than zero."
        return value

    soil_weight = positive("foundation_soil_unit_weight_kn_m3")
    bearing = positive("foundation_permissible_bearing_kpa")
    try:
        concrete = float(
            raw_inputs.get(
                "foundation_concrete_strength_mpa",
                DESIGN_CONCRETE_STRENGTH_MPA,
            )
        )
        soil_cover = float(raw_inputs.get("foundation_soil_cover_depth_m", 0.5))
        pedestal_height = float(
            raw_inputs.get("foundation_pedestal_height_m", 0.6)
        )
        friction = float(raw_inputs.get("foundation_friction_coefficient", 0.35))
        soil_friction_angle = float(
            raw_inputs.get("foundation_soil_friction_angle_deg", 25.0)
        )
        passive_mobilisation = float(
            raw_inputs.get("foundation_passive_mobilisation_factor", 0.75)
        )
        uls_sliding_required_sf = float(
            raw_inputs.get("foundation_uls_sliding_required_sf", 1.5)
        )
    except (TypeError, ValueError):
        concrete = soil_cover = pedestal_height = friction = soil_friction_angle = 0.0
        passive_mobilisation = uls_sliding_required_sf = 0.0
        errors["foundation_sliding_inputs"] = (
            "Enter numbers for soil cover, friction angle, mobilisation and safety factor."
        )
    sliding = str(
        raw_inputs.get("foundation_sliding_resistance", "Sliding Not Resisted")
    ).strip()
    if sliding not in FOUNDATION_SLIDING_OPTIONS:
        errors["foundation_sliding_resistance"] = (
            f"Choose one of: {', '.join(FOUNDATION_SLIDING_OPTIONS)}."
        )
    passive = str(
        raw_inputs.get(
            "foundation_passive_resistance",
            "Passive Resistance Excluded",
        )
    ).strip()
    if passive not in FOUNDATION_PASSIVE_RESISTANCE_OPTIONS:
        errors["foundation_passive_resistance"] = (
            f"Choose one of: {', '.join(FOUNDATION_PASSIVE_RESISTANCE_OPTIONS)}."
        )
    if not math.isfinite(soil_cover) or soil_cover < 0:
        errors["foundation_soil_cover_depth_m"] = "Enter a value of at least 0."
    if not math.isfinite(pedestal_height) or pedestal_height < 0:
        errors["foundation_pedestal_height_m"] = "Enter a value of at least 0."
    if not math.isfinite(concrete) or concrete < 20 or concrete > 80:
        errors["foundation_concrete_strength_mpa"] = (
            "Enter a concrete strength from 20 to 80 MPa."
        )
    if not math.isfinite(friction) or friction < 0 or friction > 1.5:
        errors["foundation_friction_coefficient"] = "Enter a value from 0 to 1.5."
    if (
        not math.isfinite(soil_friction_angle)
        or soil_friction_angle < 0
        or soil_friction_angle > 60
    ):
        errors["foundation_soil_friction_angle_deg"] = (
            "Enter a value from 0 to 60 degrees."
        )
    if (
        not math.isfinite(passive_mobilisation)
        or passive_mobilisation < 0
        or passive_mobilisation > 1
    ):
        errors["foundation_passive_mobilisation_factor"] = (
            "Enter a value from 0 to 1."
        )
    if (
        not math.isfinite(uls_sliding_required_sf)
        or uls_sliding_required_sf <= 0
    ):
        errors["foundation_uls_sliding_required_sf"] = (
            "Enter a finite value greater than zero."
        )
    if errors:
        raise FoundationInputError(errors)
    return (
        soil_weight,
        bearing,
        concrete,
        soil_cover,
        pedestal_height,
        friction,
        sliding,
        soil_friction_angle,
        passive,
        passive_mobilisation,
        uls_sliding_required_sf,
    )


def _round_up(value: float, increment: float) -> float:
    return math.ceil((value - 1e-12) / increment) * increment


def design_pad_foundations(
    snapshot: Mapping[str, Any], raw_inputs: Mapping[str, Any]
) -> dict[str, Any]:
    """Automatically size one common isolated pad for all portal supports.

    The user supplies concrete strength, soil unit weight, permissible bearing
    pressure, soil cover, friction and the sliding-resistance basis. Plan
    dimensions and thickness are searched in practical increments using fixed,
    reported reinforcement, cover and loaded-area assumptions.
    """

    # Preserve the existing explicit-input calculation contract for saved API
    # clients and regression comparisons. The product UI omits explicit footing
    # dimensions and therefore always uses automatic sizing.
    if "foundation_length_m" in raw_inputs:
        return _check_pad_foundations(snapshot, raw_inputs)

    (
        soil_weight,
        bearing,
        concrete,
        soil_cover,
        pedestal_height,
        friction,
        sliding,
        soil_friction_angle,
        passive,
        passive_mobilisation,
        uls_sliding_required_sf,
    ) = _automatic_user_inputs(raw_inputs)
    _, _, characteristic_reactions = _reaction_sets(snapshot)
    downward = max(
        (
            max(float(item["fy"]), 0.0)
            for item in characteristic_reactions
        ),
        default=0.0,
    )
    preliminary_area = max(downward / bearing, 0.64)
    dimensions: set[tuple[float, float, float]] = set()
    for length_tenth in range(8, 81):
        length = length_tenth / 10.0
        starting_width = max(
            0.8, _round_up(preliminary_area / length, 0.1)
        )
        for extra_tenth in range(0, 16):
            width = starting_width + extra_tenth / 10.0
            if width > 8.0 + 1e-9:
                continue
            if max(length, width) / min(length, width) > float(
                AUTOMATIC_FOUNDATION_ASSUMPTIONS[
                    "maximum_plan_aspect_ratio"
                ]
            ):
                continue
            for thickness_mm in range(300, 2001, 50):
                dimensions.add((length, width, float(thickness_mm)))
    ordered_dimensions = sorted(
        dimensions,
        key=lambda item: (
            item[0] * item[1] * item[2],
            item[0] * item[1],
            item[2],
            item[0],
            item[1],
        ),
    )

    assumptions = AUTOMATIC_FOUNDATION_ASSUMPTIONS
    attempted = 0
    selected: dict[str, Any] | None = None
    for length, width, thickness_mm in ordered_dimensions:
        attempted += 1
        internal_inputs = {
            "foundation_standard": assumptions["foundation_standard"],
            "foundation_length_m": length,
            "foundation_width_m": width,
            "foundation_thickness_mm": thickness_mm,
            "foundation_loaded_length_mm": assumptions[
                "foundation_loaded_length_mm"
            ],
            "foundation_loaded_width_mm": assumptions[
                "foundation_loaded_width_mm"
            ],
            "foundation_pedestal_height_m": pedestal_height,
            "foundation_concrete_strength_mpa": concrete,
            "foundation_rebar_strength_mpa": assumptions[
                "foundation_rebar_strength_mpa"
            ],
            "foundation_bar_diameter_mm": assumptions[
                "foundation_bar_diameter_mm"
            ],
            "foundation_bar_spacing_mm": assumptions[
                "foundation_bar_spacing_mm"
            ],
            "foundation_cover_mm": assumptions["foundation_cover_mm"],
            "foundation_permissible_bearing_kpa": bearing,
            "foundation_base_depth_m": (
                thickness_mm / 1000.0 + soil_cover
            ),
            "foundation_soil_cover_depth_m": soil_cover,
            "foundation_soil_unit_weight_kn_m3": soil_weight,
            "foundation_friction_coefficient": friction,
            "foundation_sliding_resistance": sliding,
            "foundation_soil_friction_angle_deg": soil_friction_angle,
            "foundation_passive_resistance": passive,
            "foundation_passive_mobilisation_factor": passive_mobilisation,
            "foundation_passive_uls_partial_factor": assumptions[
                "foundation_passive_uls_partial_factor"
            ],
            "foundation_stability_self_weight_factor": assumptions[
                "foundation_stability_self_weight_factor"
            ],
            "foundation_uls_self_weight_factor": assumptions[
                "foundation_uls_self_weight_factor"
            ],
            "foundation_uls_sliding_required_sf": uls_sliding_required_sf,
        }
        result = _check_pad_foundations(snapshot, internal_inputs)
        if result["status"] == "PASS":
            selected = result
            break

    if selected is None:
        raise ValueError(
            "No automatic pad foundation passed within the 0.8-8.0 m plan "
            "and 300-2000 mm thickness search limits. Review reactions, soil "
            "parameters or the disclosed automatic-design assumptions."
        )

    selected["schema_version"] = 2
    selected["mode"] = "automatic_common_pad"
    selected["user_inputs"] = {
        "soil_unit_weight_kn_m3": soil_weight,
        "permissible_bearing_kpa": bearing,
        "concrete_strength_mpa": concrete,
        "soil_cover_depth_m": soil_cover,
        "pedestal_height_m": pedestal_height,
        "friction_coefficient": friction,
        "sliding_resistance": sliding,
        "soil_friction_angle_deg": soil_friction_angle,
        "passive_resistance": passive,
        "passive_mobilisation_factor": passive_mobilisation,
        "passive_uls_partial_factor": assumptions[
            "foundation_passive_uls_partial_factor"
        ],
        "stability_self_weight_factor": assumptions[
            "foundation_stability_self_weight_factor"
        ],
        "uls_self_weight_factor": assumptions[
            "foundation_uls_self_weight_factor"
        ],
        "uls_sliding_required_sf": uls_sliding_required_sf,
    }
    selected["automatic_design"] = {
        "length_m": float(selected["inputs"]["length_m"]),
        "width_m": float(selected["inputs"]["width_m"]),
        "height_mm": float(selected["inputs"]["thickness_mm"]),
        "search_increment_plan_m": 0.1,
        "search_increment_height_mm": 50.0,
        "maximum_plan_aspect_ratio": float(
            assumptions["maximum_plan_aspect_ratio"]
        ),
        "candidates_checked": attempted,
        "objective": (
            "Minimum concrete volume common pad passing all support, SLS "
            "bearing/uplift, ULS stability and reinforced-concrete checks."
        ),
    }
    selected["assumptions"] = [
        *selected.get("assumptions", []),
        (
            "Concrete strength, soil unit weight, permissible bearing pressure, soil cover depth, "
            "base friction, soil friction angle, passive mobilisation and the "
            "ULS sliding safety factor are project inputs."
        ),
        (
            f"Automatic basis: {assumptions['foundation_standard']}, "
            f"{concrete:.0f} MPa "
            f"concrete, {assumptions['foundation_rebar_strength_mpa']:.0f} MPa "
            f"reinforcement, T{assumptions['foundation_bar_diameter_mm']:.0f}"
            f"@{assumptions['foundation_bar_spacing_mm']:.0f}, "
            f"{assumptions['foundation_cover_mm']:.0f} mm cover, "
            f"{soil_cover:.2f} m soil cover, base friction coefficient "
            f"{friction:.2f}, soil friction angle {soil_friction_angle:.1f} degrees, "
            f"{passive} at mobilisation factor {passive_mobilisation:.2f}, "
            f"ULS sliding SF {uls_sliding_required_sf:.2f}."
            f" Maximum plan aspect ratio {float(assumptions['maximum_plan_aspect_ratio']):.2f}."
        ),
    ]
    return selected
