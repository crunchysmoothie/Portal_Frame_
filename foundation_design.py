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
FAILED_NUMERIC = 1e12

DEFAULT_FOUNDATION_VALUES: dict[str, Any] = {
    "foundation_standard": FOUNDATION_STANDARDS[0],
    "foundation_length_m": "2.4",
    "foundation_width_m": "2.0",
    "foundation_thickness_mm": "500",
    "foundation_loaded_length_mm": "400",
    "foundation_loaded_width_mm": "400",
    "foundation_concrete_strength_mpa": "30",
    "foundation_rebar_strength_mpa": "500",
    "foundation_bar_diameter_mm": "16",
    "foundation_bar_spacing_mm": "200",
    "foundation_cover_mm": "75",
    "foundation_permissible_bearing_kpa": "150",
    "foundation_base_depth_m": "0.8",
    "foundation_soil_unit_weight_kn_m3": "18",
    "foundation_friction_coefficient": "0.45",
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
    ) -> float:
        try:
            value = float(raw.get(key, ""))
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
    concrete = number(
        "foundation_concrete_strength_mpa", minimum=15, maximum=100
    )
    rebar = number("foundation_rebar_strength_mpa", minimum=250)
    diameter = number("foundation_bar_diameter_mm", minimum=6)
    spacing = number("foundation_bar_spacing_mm", minimum=50)
    cover = number("foundation_cover_mm", minimum=25)
    bearing = number("foundation_permissible_bearing_kpa")
    base_depth = number(
        "foundation_base_depth_m", minimum=0, strictly_positive=False
    )
    soil_weight = number("foundation_soil_unit_weight_kn_m3")
    friction = number(
        "foundation_friction_coefficient",
        minimum=0,
        maximum=1.5,
        strictly_positive=False,
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
    if base_depth * 1000 < thickness:
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
        "concrete_strength_mpa": concrete,
        "rebar_strength_mpa": rebar,
        "bar_diameter_mm": diameter,
        "bar_spacing_mm": spacing,
        "cover_mm": cover,
        "effective_depth_mm": effective_depth,
        "permissible_bearing_kpa": bearing,
        "base_depth_m": base_depth,
        "soil_unit_weight_kn_m3": soil_weight,
        "friction_coefficient": friction,
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


def _reaction_sets(snapshot: Mapping[str, Any]) -> tuple[list[dict], list[dict]]:
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
    return (
        [item for item in reactions if item["load_combination"] in uls_names],
        [item for item in reactions if item["load_combination"] in sls_names],
    )


def design_pad_foundations(
    snapshot: Mapping[str, Any], raw_inputs: Mapping[str, Any]
) -> dict[str, Any]:
    """Design identical isolated pad footings at every portal support."""

    values = _validated_inputs(raw_inputs)
    uls_reactions, sls_reactions = _reaction_sets(snapshot)
    if not uls_reactions:
        raise ValueError("The analysis snapshot does not contain ULS reactions.")
    if not sls_reactions:
        raise ValueError(
            "The analysis snapshot does not contain SLS reactions; rerun the "
            "portal analysis with the current engine."
        )

    standard = str(values["standard"])
    length = float(values["length_m"])
    width = float(values["width_m"])
    thickness_m = float(values["thickness_mm"]) / 1000
    loaded_length = float(values["loaded_length_mm"]) / 1000
    loaded_width = float(values["loaded_width_mm"]) / 1000
    d_mm = float(values["effective_depth_mm"])
    footprint = length * width
    footing_weight = footprint * thickness_m * 24.0
    cover_depth = max(float(values["base_depth_m"]) - thickness_m, 0.0)
    soil_cover_weight = max(
        footprint - loaded_length * loaded_width, 0.0
    ) * cover_depth * float(values["soil_unit_weight_kn_m3"])
    stabilising_weight = footing_weight + soil_cover_weight
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

    nodes = sorted({item["node"] for item in uls_reactions + sls_reactions})
    support_results = []
    for node in nodes:
        node_sls = [item for item in sls_reactions if item["node"] == node]
        node_uls = [item for item in uls_reactions if item["node"] == node]

        service_rows = []
        for reaction in node_sls:
            vertical = float(reaction["fy"]) + stabilising_weight
            pressures = bearing_pressures(
                vertical, float(reaction["mz"]), length, width
            )
            horizontal = abs(float(reaction["fx"]))
            sliding_capacity = (
                float(values["friction_coefficient"]) * max(vertical, 0.0)
            )
            service_rows.append({
                "combination": reaction["load_combination"],
                "vertical_reaction_kN": float(reaction["fy"]),
                "horizontal_reaction_kN": float(reaction["fx"]),
                "base_moment_kNm": float(reaction["mz"]),
                **pressures,
                "bearing_utilisation": (
                    float(pressures["q_max_kpa"])
                    / float(values["permissible_bearing_kpa"])
                ),
                "sliding_utilisation": (
                    horizontal / sliding_capacity
                    if sliding_capacity > 0 else FAILED_NUMERIC
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
            favourable_uls_weight = 0.9 * stabilising_weight
            foundation_vertical = (
                float(reaction["fy"]) + favourable_uls_weight
            )
            pressures = bearing_pressures(
                foundation_vertical,
                float(reaction["mz"]),
                length,
                width,
            )
            contact_equilibrium = (
                pressures["contact"]
                not in {"none", "resultant_outside_base"}
            )
            uniform_stabilising_pressure = favourable_uls_weight / footprint
            q_max = (
                max(
                    float(pressures["q_max_kpa"])
                    - uniform_stabilising_pressure,
                    0.0,
                )
                if contact_equilibrium else 0.0
            )
            q_min = (
                max(
                    float(pressures["q_min_kpa"])
                    - uniform_stabilising_pressure,
                    0.0,
                )
                if contact_equilibrium else 0.0
            )
            projection_x = (length - loaded_length) / 2
            projection_y = (width - loaded_width) / 2
            moment_x = q_max * projection_x**2 / 2
            moment_y = q_max * projection_y**2 / 2
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
            shear_x = q_max * max(projection_x - shear_distance, 0.0)
            shear_y = q_max * max(projection_y - shear_distance, 0.0)
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
                column_vertical - q_min * inside_area_m2, 0.0
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
                "uls_stabilising_weight_kN": favourable_uls_weight,
                "uls_net_vertical_kN": foundation_vertical,
                "base_moment_kNm": float(reaction["mz"]),
                "contact": pressures["contact"],
                "q_min_kpa": q_min,
                "q_max_kpa": q_max,
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
        governing_structural = max(
            structural_rows, key=lambda item: item["governing_utilisation"]
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
            "PASS"
            if (
                math.isfinite(governing_sliding["sliding_utilisation"])
                and governing_sliding["sliding_utilisation"] <= 1
            )
            else "FAIL"
        )
        structural_status = (
            "PASS"
            if governing_structural["governing_utilisation"] <= 1
            else "FAIL"
        )
        statuses = (
            bearing_status,
            sliding_status,
            governing_uplift["uplift_status"],
            structural_status,
        )
        support_results.append({
            "node": node,
            "status": "PASS" if all(item == "PASS" for item in statuses) else "FAIL",
            "serviceability": {
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
                },
                "uplift": {
                    "status": governing_uplift["uplift_status"],
                    "combination": governing_uplift["combination"],
                    "net_vertical_kN": (
                        governing_uplift["vertical_reaction_kN"]
                        + stabilising_weight
                    ),
                },
            },
            "structural": {
                "status": structural_status,
                "combination": governing_structural["combination"],
                "provided_steel_mm2_per_m": provided_steel,
                **{
                    key: value
                    for key, value in governing_structural.items()
                    if key not in {"combination"}
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
            "stabilising_weight_kN": stabilising_weight,
            "provided_steel_mm2_per_m": provided_steel,
            "effective_depth_mm": d_mm,
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
            "Passive soil resistance is omitted from sliding resistance; base friction only is included.",
            "ULS footing bending and shear exclude footing self-weight, following the pad-footing design procedure in the supplied RC manual.",
            "A single bottom reinforcement mesh is used in both directions at the entered bar diameter and spacing.",
        ],
        "warnings": [
            "Permissible bearing pressure and settlement require project-specific geotechnical confirmation.",
            "Anchor bolts, base plate, pedestal, dowels, development length, crack width, durability exposure and construction joints are outside this calculation.",
            "Overall building overturning and interaction between adjacent foundations are not checked by an isolated-pad calculation.",
        ],
    }
