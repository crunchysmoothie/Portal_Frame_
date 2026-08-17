"""Detailed post-analysis checks for portal-frame steel connections.

The module consumes a completed analysis snapshot plus the selected connection
geometry. It does not alter the frame analysis. Each result carries its design
basis, substitution and status so the Connections workspace can be audited
independently from the member-design report.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from .components import supporting_member_components
from .haunch_geometry import haunch_cut_depth_check
from databases import load_member_database


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STEEL_FY_MPA = 355.0
ELASTIC_MODULUS_MPA = 200_000.0
RESISTANCE_FACTOR = 0.90
WELD_SIZES_MM = (5.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0)
E70_WELD_RESISTANCE_KN_PER_MM = {
    5.0: 0.762,
    6.0: 0.914,
    8.0: 1.219,
    10.0: 1.523,
    12.0: 1.828,
    14.0: 2.133,
    16.0: 2.437,
    18.0: 2.742,
}


def _section(designation: str) -> Mapping[str, Any]:
    database = load_member_database(PROJECT_ROOT / "databases" / "member_database.csv")
    for sections in database.values():
        if designation in sections:
            return sections[designation]
    raise ValueError(f"Section {designation!r} was not found.")


def _status(utilisation: float, *, completed: bool = True) -> str:
    if not completed:
        return "INPUT_REQUIRED"
    return "PASS" if math.isfinite(utilisation) and utilisation <= 1.0 else "FAIL"


def _check(
    *,
    reference: str,
    name: str,
    equation: str,
    substitution: str,
    demand: float,
    resistance: float,
    units: str,
    source: str,
    completed: bool = True,
    note: str = "",
) -> dict[str, Any]:
    utilisation = (
        demand / resistance
        if completed and resistance > 1e-12
        else math.inf
    )
    return {
        "reference": reference,
        "name": name,
        "equation": equation,
        "substitution": substitution,
        "demand": demand,
        "resistance": resistance,
        "units": units,
        "utilisation": utilisation if completed else None,
        "status": _status(utilisation, completed=completed),
        "source": source,
        "note": note,
    }


def _minimum_fillet_weld_size(thicker_part_mm: float) -> float:
    if thicker_part_mm <= 12.0:
        return 5.0
    if thicker_part_mm <= 20.0:
        return 6.0
    if thicker_part_mm <= 40.0:
        return 8.0
    if thicker_part_mm <= 60.0:
        return 10.0
    return 12.0


def _select_fillet_weld(
    demand_kn_per_mm: float,
    *,
    thicker_part_mm: float,
    thinner_part_mm: float,
) -> dict[str, Any]:
    minimum = _minimum_fillet_weld_size(thicker_part_mm)
    selected = next(
        (
            size
            for size in WELD_SIZES_MM
            if size >= minimum
            and E70_WELD_RESISTANCE_KN_PER_MM[size]
            >= demand_kn_per_mm
        ),
        None,
    )
    if selected is None:
        return {
            "status": "FAIL",
            "weld_type": "Fillet",
            "minimum_size_mm": minimum,
            "required_force_per_mm": demand_kn_per_mm,
            "reason": "No tabulated 5-18 mm E70XX fillet weld passes.",
        }
    resistance = E70_WELD_RESISTANCE_KN_PER_MM[selected]
    if selected > thinner_part_mm + 1e-9:
        return {
            "status": "PASS",
            "weld_type": "Complete joint penetration groove weld",
            "equivalent_fillet_size_mm": selected,
            "minimum_size_mm": minimum,
            "required_force_per_mm": demand_kn_per_mm,
            "fillet_resistance_kn_per_mm": resistance,
            "utilisation": demand_kn_per_mm / resistance,
            "reason": (
                "The equivalent fillet leg exceeds the thinner connected part; "
                "a matching-strength complete-joint-penetration detail is used."
            ),
        }
    return {
        "status": "PASS",
        "weld_type": "E70XX double fillet",
        "provided_size_mm": selected,
        "minimum_size_mm": minimum,
        "required_force_per_mm": demand_kn_per_mm,
        "resistance_kn_per_mm": resistance,
        "utilisation": demand_kn_per_mm / resistance,
    }


def _rectangular_weld_group(
    *,
    axial_kN: float,
    shear_kN: float,
    moment_kNm: float,
    height_mm: float,
    width_mm: float,
    thicker_part_mm: float,
    thinner_part_mm: float,
) -> dict[str, Any]:
    effective_length = 2.0 * (height_mm + width_mm)
    line_second_moment = (
        2.0 * width_mm * (height_mm / 2.0) ** 2
        + height_mm**3 / 6.0
    )
    direct_normal = axial_kN / max(effective_length, 1.0)
    direct_shear = shear_kN / max(effective_length, 1.0)
    moment_force = (
        moment_kNm
        * 1000.0
        * (height_mm / 2.0)
        / max(line_second_moment, 1.0)
    )
    resultant = math.hypot(
        direct_shear, abs(direct_normal) + abs(moment_force)
    )
    selected = _select_fillet_weld(
        resultant,
        thicker_part_mm=thicker_part_mm,
        thinner_part_mm=thinner_part_mm,
    )
    return {
        "status": selected["status"],
        "geometry": {
            "height_mm": height_mm,
            "width_mm": width_mm,
            "effective_length_mm": effective_length,
            "line_second_moment_mm3": line_second_moment,
        },
        "actions": {
            "axial_kN": axial_kN,
            "shear_kN": shear_kN,
            "moment_kNm": moment_kNm,
            "direct_normal_kn_per_mm": direct_normal,
            "direct_shear_kn_per_mm": direct_shear,
            "moment_force_kn_per_mm": moment_force,
            "resultant_kn_per_mm": resultant,
        },
        "selected_weld": selected,
        "equations": [
            "f_v = V_u / L_w",
            "f_m = M_u y / I_w",
            "f_r = sqrt(f_v^2 + (f_n + f_m)^2)",
        ],
        "source": (
            "Mahachi Chapter 7.8, equations 7.45-7.48, and Tables 7.5-7.6."
        ),
    }


def _stiffener_checks(
    stiffener: Mapping[str, Any],
    *,
    demand_kN: float,
    connected_thickness_mm: float,
    fy_mpa: float = STEEL_FY_MPA,
) -> dict[str, Any]:
    if not stiffener.get("required"):
        return {
            "status": "NOT_REQUIRED",
            "checks": [],
            "weld": None,
        }
    thickness = float(stiffener.get("provided_thickness_mm", 0.0) or 0.0)
    height = float(stiffener.get("height_mm", 0.0))
    length = float(stiffener.get("length_mm", 0.0))
    count = max(int(stiffener.get("count", 1)), 1)
    area = thickness * height
    demand_each = demand_kN / count
    yield_resistance = (
        RESISTANCE_FACTOR * area * float(fy_mpa) / 1000.0
    )
    radius = thickness / math.sqrt(12.0) if thickness > 0 else 0.0
    slenderness = 0.7 * height / max(radius, 1e-9)
    euler_stress = (
        math.pi**2 * ELASTIC_MODULUS_MPA / max(slenderness**2, 1e-9)
    )
    normalised = math.sqrt(
        float(fy_mpa) / max(euler_stress, 1e-9)
    )
    buckling_resistance = (
        RESISTANCE_FACTOR
        * area
        * float(fy_mpa)
        * (1.0 + normalised ** (2.0 * 1.34)) ** (-1.0 / 1.34)
        / 1000.0
    )
    checks = [
        _check(
            reference="ST-01",
            name="Stiffener gross-section yielding",
            equation="R_y = phi A_s f_y",
            substitution=(
                f"0.90 x {area:.1f} x 355 / 1000"
            ),
            demand=demand_each,
            resistance=yield_resistance,
            units="kN",
            source="SANS 10162 gross-section yielding model.",
        ),
        _check(
            reference="ST-02",
            name="Stiffener plate-column buckling",
            equation=(
                "C_r = phi A_s f_y [1 + lambda^(2n)]^(-1/n), n=1.34"
            ),
            substitution=(
                f"KL/r={slenderness:.2f}; lambda={normalised:.3f}"
            ),
            demand=demand_each,
            resistance=buckling_resistance,
            units="kN",
            source=(
                "SANS 10162 compression curve used by the portal member model."
            ),
            note=(
                "Stiffener idealised as a 0.7L plate-column strip; final edge "
                "restraint and out-of-plane detailing must match the markup."
            ),
        ),
    ]
    weld_demand = demand_each / max(2.0 * length, 1.0)
    weld = _select_fillet_weld(
        weld_demand,
        thicker_part_mm=max(thickness, connected_thickness_mm),
        thinner_part_mm=min(thickness, connected_thickness_mm),
    )
    return {
        "status": (
            "PASS"
            if all(item["status"] == "PASS" for item in checks)
            and weld["status"] == "PASS"
            else "FAIL"
        ),
        "demand_per_stiffener_kN": demand_each,
        "slenderness_kl_over_r": slenderness,
        "normalised_slenderness": normalised,
        "checks": checks,
        "weld": weld,
    }


def _t_stub_prying(
    connection: Mapping[str, Any],
    *,
    flange_force_kN: float,
    rafter: Mapping[str, Any],
) -> dict[str, Any]:
    bolts = connection["bolts"]
    plate = connection["plate"]
    gauge = float(bolts["gauge_mm"])
    edge = float(bolts["edge_distance_mm"])
    pitch = float(bolts["pitch_mm"])
    web_thickness = float(rafter["tw"])
    root_radius = float(rafter.get("r1", 0.0))
    m = max(
        (gauge - web_thickness - 1.6 * root_radius) / 2.0,
        1.0,
    )
    n = min(edge, 1.25 * m)
    effective_length = min(
        float(plate["height_mm"]),
        2.0 * float(bolts["end_distance_mm"]) + pitch,
    )
    plate_thickness = float(plate["provided_thickness_mm"])
    moment_resistance_nmm = (
        0.25
        * RESISTANCE_FACTOR
        * effective_length
        * plate_thickness**2
        * STEEL_FY_MPA
    )
    tension_bolts = 4.0
    external_per_bolt = flange_force_kN / tension_bolts
    calculated = (
        (
            (m + n) * flange_force_kN * 1000.0
            - 2.0 * moment_resistance_nmm
        )
        / max(n * tension_bolts, 1.0)
        / 1000.0
    )
    calculated = max(external_per_bolt, calculated)
    maximum_with_prying = 1.30 * external_per_bolt
    design_tension = min(calculated, maximum_with_prying)
    plate_mechanism_demand = (
        0.25 * m * flange_force_kN * 1000.0
    )
    plate_utilisation = (
        plate_mechanism_demand / moment_resistance_nmm
        if moment_resistance_nmm > 0
        else math.inf
    )
    return {
        "status": "PASS" if plate_utilisation <= 1.0 else "FAIL",
        "m_mm": m,
        "n_mm": n,
        "effective_length_mm": effective_length,
        "plate_moment_resistance_kNm": moment_resistance_nmm / 1e6,
        "plate_mechanism_utilisation": plate_utilisation,
        "external_tension_per_bolt_kN": external_per_bolt,
        "calculated_tension_per_bolt_kN": calculated,
        "maximum_prying_tension_per_bolt_kN": maximum_with_prying,
        "design_tension_per_bolt_kN": design_tension,
        "prying_force_per_bolt_kN": max(
            0.0, design_tension - external_per_bolt
        ),
        "prying_cap_applied": calculated > maximum_with_prying,
        "equations": [
            "n = min(e, 1.25m)",
            "M_r = 0.25 phi sum(l_eff) t_p^2 f_y",
            "T_u = ((m+n)P_u - 2M_r) / (nN)",
            "T_u <= 1.30(P_u/N)",
        ],
        "source": (
            "Mahachi Chapter 7.5 and Example E7.5 T-stub prying model; "
            "SANS 10162 limits prying to 30% of external bolt tension."
        ),
    }


def _base_plate_checks(
    snapshot: Mapping[str, Any],
    base_plates: Mapping[str, Any],
) -> dict[str, Any]:
    uls_names = {
        str(item["name"])
        for item in snapshot["input_data"].get("load_combinations", [])
    }
    reactions = [
        item
        for item in snapshot["results"].get("reactions", [])
        if str(item.get("load_combination", "")) in uls_names
    ]
    supports = []
    for support in base_plates.get("supports", []):
        if not support.get("plate"):
            supports.append({
                "support": support.get("support", ""),
                "status": "FAIL",
                "checks": [],
                "reason": support.get("reason", "No plate geometry."),
            })
            continue
        plate = support["plate"]
        bolt_design = support.get("holding_down_bolts", {})
        layout = bolt_design.get("layout", {})
        support_rows = [
            item
            for item in reactions
            if str(item.get("node", "")) == str(support["support"])
        ]
        column = _section(str(support["column_section"]))
        bearing = plate["governing_bearing"]
        checks = [
            _check(
                reference="BP-01",
                name="Concrete bearing below base plate",
                equation="U = q_max / (0.4 f_cu)",
                substitution=(
                    f"{float(bearing['q_max_kpa']):.2f} / "
                    f"{float(plate['bearing_resistance_mpa']) * 1000:.2f}"
                ),
                demand=float(bearing["q_max_kpa"]),
                resistance=float(plate["bearing_resistance_mpa"]) * 1000.0,
                units="kPa",
                source="Mahachi Chapter 7.9, equations 7.55-7.61.",
            ),
            _check(
                reference="BP-02",
                name="Base-plate cantilever bending",
                equation="U = (t_required / t_provided)^2",
                substitution=(
                    f"({float(plate['required_thickness_mm']):.2f} / "
                    f"{float(plate['provided_thickness_mm']):.2f})^2"
                ),
                demand=float(plate["required_thickness_mm"]) ** 2,
                resistance=float(plate["provided_thickness_mm"]) ** 2,
                units="mm2",
                source="Mahachi Chapter 7.9 slab-base plate bending.",
            ),
        ]
        if layout:
            checks.extend([
                _check(
                    reference="BP-03",
                    name="Anchor-bolt pitch",
                    equation="p >= 2.7d",
                    substitution=(
                        f"{float(layout['pitch_mm']):.1f} >= "
                        f"{float(layout['minimum_pitch_mm']):.1f}"
                    ),
                    demand=float(layout["minimum_pitch_mm"]),
                    resistance=float(layout["pitch_mm"]),
                    units="mm",
                    source="Mahachi Chapter 7.3, SANS 10162 Clause 22.3.3.1.",
                ),
                _check(
                    reference="BP-04",
                    name="Anchor-bolt edge distance",
                    equation="e >= Red Book recommended edge distance",
                    substitution=(
                        f"{float(layout['edge_distance_mm']):.1f} >= "
                        f"{float(layout.get('recommended_edge_distance_mm', layout['minimum_edge_distance_mm'])):.1f}"
                    ),
                    demand=float(
                        layout.get(
                            "recommended_edge_distance_mm",
                            layout["minimum_edge_distance_mm"],
                        )
                    ),
                    resistance=float(layout["edge_distance_mm"]),
                    units="mm",
                    source="The Red Book Table 6.19.",
                ),
                _check(
                    reference="BP-05",
                    name="Anchor-bolt clearance from column depth faces",
                    equation="c_provided >= B/2 + C1",
                    substitution=(
                        f"{float(layout['provided_section_face_clearance_depth_mm']):.1f} "
                        f">= {float(layout['minimum_section_face_clearance_mm']):.1f}"
                    ),
                    demand=float(layout["minimum_section_face_clearance_mm"]),
                    resistance=float(
                        layout["provided_section_face_clearance_depth_mm"]
                    ),
                    units="mm",
                    source="The Red Book Table 6.17 impact-wrench clearances.",
                ),
                _check(
                    reference="BP-06",
                    name="Anchor-bolt clearance from column width faces",
                    equation="c_provided >= B/2 + C1",
                    substitution=(
                        f"{float(layout['provided_section_face_clearance_width_mm']):.1f} "
                        f">= {float(layout['minimum_section_face_clearance_mm']):.1f}"
                    ),
                    demand=float(layout["minimum_section_face_clearance_mm"]),
                    resistance=float(
                        layout["provided_section_face_clearance_width_mm"]
                    ),
                    units="mm",
                    source="The Red Book Table 6.17 impact-wrench clearances.",
                ),
            ])
        governing_bolt = bolt_design.get("governing_check")
        if governing_bolt:
            checks.append(
                _check(
                    reference="BP-05",
                    name="Anchor-bolt steel shear/tension interaction",
                    equation="V_u/V_r + T_u/T_r <= 1.4",
                    substitution=(
                        f"{float(governing_bolt['bolt_shear_kN']):.2f}/"
                        f"{float(bolt_design['resistances']['shear_resistance_kN']):.2f}"
                        " + "
                        f"{float(governing_bolt['bolt_tension_kN']):.2f}/"
                        f"{float(bolt_design['resistances']['tension_resistance_kN']):.2f}"
                    ),
                    demand=float(governing_bolt["linear_interaction"]),
                    resistance=1.4,
                    units="interaction",
                    source="Mahachi Chapter 7.4, equation 7.18.",
                )
            )
        envelope = max(
            support_rows,
            key=lambda item: (
                abs(float(item.get("mz", 0.0))),
                abs(float(item.get("fy", 0.0))),
            ),
            default={},
        )
        weld = _rectangular_weld_group(
            axial_kN=abs(float(envelope.get("fy", 0.0))),
            shear_kN=abs(float(envelope.get("fx", 0.0))),
            moment_kNm=abs(float(envelope.get("mz", 0.0))),
            height_mm=float(column["h"]),
            width_mm=float(column["b"]),
            thicker_part_mm=max(
                float(column["tf"]),
                float(plate["provided_thickness_mm"]),
            ),
            thinner_part_mm=min(
                float(column["tw"]),
                float(plate["provided_thickness_mm"]),
            ),
        )
        stiffeners = _stiffener_checks(
            support.get("stiffeners", {}),
            demand_kN=float(
                support.get("stiffeners", {}).get(
                    "demand_per_stiffener_kN", 0.0
                )
            )
            * max(int(support.get("stiffeners", {}).get("count", 1)), 1),
            connected_thickness_mm=float(plate["provided_thickness_mm"]),
        )
        anchorage = bolt_design.get("anchorage_estimate", {})
        governing_bolt = bolt_design.get("governing_check", {})
        anchor_checks = []
        if anchorage and governing_bolt:
            anchor_checks.append(
                _check(
                    reference="BP-07",
                    name="Red Book HD-bolt concrete anchorage estimate",
                    equation="T_u <= T_rc from Table 4.6",
                    substitution=(
                        f"{float(governing_bolt['bolt_tension_kN']):.2f} <= "
                        f"{float(anchorage['concrete_tension_resistance_kN']):.2f}"
                    ),
                    demand=float(governing_bolt["bolt_tension_kN"]),
                    resistance=float(
                        anchorage["concrete_tension_resistance_kN"]
                    ),
                    units="kN/bolt",
                    source=(
                        "The Red Book Table 4.6, holding-down bolts with "
                        "anchor plates in 25 MPa concrete."
                    ),
                    note=(
                        f"Use anchorage length {float(anchorage['anchorage_length_mm']):.0f} mm, "
                        f"anchor plate {float(anchorage['anchor_plate_length_mm']):.0f} x "
                        f"{float(anchorage['anchor_plate_width_mm']):.0f} x "
                        f"{float(anchorage['minimum_anchor_plate_thickness_mm']):.1f} mm minimum."
                    ),
                )
            )
        anchor_checks.append(
            _check(
                reference="BP-08",
                name="Concrete edge distance and pedestal detailing",
                equation="Concrete edge distance >= 7d",
                substitution=(
                    f"Provide at least "
                    f"{float(anchorage.get('minimum_concrete_edge_distance_mm', 0.0)):.0f} mm"
                    if anchorage
                    else "Red Book anchorage geometry is unavailable"
                ),
                demand=float(
                    anchorage.get("minimum_concrete_edge_distance_mm", 0.0)
                ),
                resistance=0.0,
                units="mm",
                source="The Red Book Table 4.6 notes.",
                completed=False,
                note=(
                    "Confirm the stated pedestal dimensions, 7d concrete edge "
                    "distance, degreased bolt shank, reinforcement and anchor "
                    "plate installation on the project drawings."
                ),
            )
        )
        anchor_concrete = {
            "status": (
                "PRELIMINARY_PASS_WITH_DETAIL_REQUIRED"
                if anchorage
                else "INPUT_REQUIRED"
            ),
            "checks": anchor_checks,
            "estimate": anchorage,
        }
        calculated_pass = (
            all(item["status"] == "PASS" for item in checks)
            and weld["status"] == "PASS"
            and stiffeners["status"] in {"PASS", "NOT_REQUIRED"}
        )
        supports.append({
            "support": support["support"],
            "status": (
                "PASS_WITH_INPUT_REQUIRED"
                if calculated_pass
                else "FAIL"
            ),
            "checks": checks,
            "column_to_base_plate_weld": weld,
            "stiffener_checks": stiffeners,
            "anchor_concrete": anchor_concrete,
        })
    return {
        "status": (
            "PASS_WITH_INPUT_REQUIRED"
            if supports
            and all(
                item["status"] == "PASS_WITH_INPUT_REQUIRED"
                for item in supports
            )
            else "FAIL"
        ),
        "supports": supports,
    }


def _haunch_checks(
    snapshot: Mapping[str, Any],
    haunch_connections: Mapping[str, Any],
) -> dict[str, Any]:
    project = snapshot["results"].get("project", {})
    rafter_section = str(project.get("rafter_section", ""))
    column_section = str(project.get("column_section", ""))
    rafter = _section(rafter_section)
    common_envelope = haunch_connections.get("preliminary_uls_envelope", {})
    locations = []
    for location in haunch_connections.get("locations", []):
        envelope = location.get("uls_envelope", common_envelope)
        connection = location.get("connection", {})
        connection_type = str(
            location.get(
                "connection_type",
                (
                    "apex_splice"
                    if str(location.get("location", "")).lower().startswith(
                        "apex"
                    )
                    else "eaves_end_plate"
                ),
            )
        )
        is_apex = connection_type == "apex_splice"
        supporting_member_type = str(
            location.get(
                "supporting_member_type",
                "opposing_rafter" if is_apex else "column",
            )
        )
        supporting_member_section = str(
            location.get(
                "supporting_member_section",
                rafter_section if is_apex else column_section,
            )
        )
        supporting_member = _section(supporting_member_section)
        steel_yield_mpa = float(
            connection.get(
                "steel_yield_mpa",
                location.get("steel_yield_mpa", STEEL_FY_MPA),
            )
        )
        if is_apex:
            supporting_label = "Opposing rafter"
            resistance_suffix = "opposing-rafter"
            source_target = "opposing rafter"
        else:
            supporting_label = "Supporting column"
            resistance_suffix = "column"
            source_target = "supporting column"
        cut_depth = float(location.get("added_depth_mm", 0.0))
        cut_geometry = haunch_cut_depth_check(rafter, cut_depth)
        fabrication_check = _check(
            reference="HC-00",
            name="Donor-section haunch cut depth",
            equation="d_cut <= hw + tf",
            substitution=(
                f"{cut_depth:.1f} <= {cut_geometry.equation}"
            ),
            demand=cut_depth,
            resistance=cut_geometry.maximum_cut_depth_mm,
            units="mm",
            source=(
                "Fabrication geometry: haunch cut from the selected rafter "
                "with the donor top flange removed and the remaining web "
                "welded to the main rafter."
            ),
        )
        if not connection.get("plate"):
            locations.append({
                "location": location.get("location", ""),
                "connection_type": connection_type,
                "supporting_member_section": supporting_member_section,
                "supporting_member_type": supporting_member_type,
                "status": "FAIL",
                "checks": [fabrication_check],
                "reason": connection.get("reason", "No connection geometry."),
            })
            continue
        flange_force = float(connection["flange_force_kN"])
        prying = _t_stub_prying(
            connection,
            flange_force_kN=flange_force,
            rafter=rafter,
        )
        bolts = connection["bolts"]
        bolt_interaction = (
            float(bolts["bolt_shear_kN"])
            / float(bolts["shear_resistance_kN"])
            + float(prying["design_tension_per_bolt_kN"])
            / float(bolts["tension_resistance_kN"])
        )
        plate = connection["plate"]
        plate_t_stub = plate.get("t_stub", {})
        row_demand = float(
            connection.get(
                "row_demand_kN",
                flange_force
                / max(int(connection.get("tension_row_count", 2)), 1),
            )
        )
        checks = [
            fabrication_check,
            _check(
                reference="HC-01A",
                name="End-plate T-stub Mode 1 - complete yielding",
                equation="R_1 = 4 M_pl / m",
                substitution=(
                    f"{row_demand:.2f} / "
                    f"{float(plate_t_stub.get('mode_1_complete_yielding_kN', 0)):.2f}"
                ),
                demand=row_demand,
                resistance=float(
                    plate_t_stub.get("mode_1_complete_yielding_kN", 0.0)
                ),
                units="kN",
                source="EN 1993-1-8 component-method equivalent T-stub.",
            ),
            _check(
                reference="HC-01B",
                name="End-plate T-stub Mode 2 - bolt and plate yielding",
                equation="R_2 = (2 M_pl + n sum(B_t)) / (m + n)",
                substitution=(
                    f"{row_demand:.2f} / "
                    f"{float(plate_t_stub.get('mode_2_bolt_and_yielding_kN', 0)):.2f}"
                ),
                demand=row_demand,
                resistance=float(
                    plate_t_stub.get(
                        "mode_2_bolt_and_yielding_kN", 0.0
                    )
                ),
                units="kN",
                source="EN 1993-1-8 component-method equivalent T-stub.",
            ),
            _check(
                reference="HC-01C",
                name="End-plate T-stub Mode 3 - bolt failure",
                equation="R_3 = sum(B_t)",
                substitution=(
                    f"{row_demand:.2f} / "
                    f"{float(plate_t_stub.get('mode_3_bolt_failure_kN', 0)):.2f}"
                ),
                demand=row_demand,
                resistance=float(
                    plate_t_stub.get("mode_3_bolt_failure_kN", 0.0)
                ),
                units="kN",
                source="EN 1993-1-8 component-method equivalent T-stub.",
            ),
            _check(
                reference="HC-02",
                name="End-plate bolt interaction including prying",
                equation="V_u/V_r + T_u/T_r <= 1.4",
                substitution=(
                    f"{float(bolts['bolt_shear_kN']):.2f}/"
                    f"{float(bolts['shear_resistance_kN']):.2f} + "
                    f"{float(prying['design_tension_per_bolt_kN']):.2f}/"
                    f"{float(bolts['tension_resistance_kN']):.2f}"
                ),
                demand=bolt_interaction,
                resistance=1.4,
                units="interaction",
                source="Mahachi Chapter 7.4 equation 7.18 and Chapter 7.5.",
            ),
            _check(
                reference="HC-03",
                name="End-plate bearing at bolt hole",
                equation="B_r = 3 phi_b t_p d f_u",
                substitution=(
                    f"{float(bolts['bolt_shear_kN']):.2f} / "
                    f"{float(plate.get('bearing_resistance_per_bolt_kN', 0)):.2f}"
                ),
                demand=float(bolts["bolt_shear_kN"]),
                resistance=float(
                    plate.get("bearing_resistance_per_bolt_kN", 0.0)
                ),
                units="kN/bolt",
                source="SANS 10162 bearing-type bolted connection model.",
            ),
            _check(
                reference="HC-04A",
                name="End-plate bolt pitch",
                equation="2.7d <= p <= 200 mm",
                substitution=(
                    f"{float(bolts['minimum_pitch_mm']):.1f} <= "
                    f"{float(bolts['pitch_mm']):.1f} <= "
                    f"{float(bolts['maximum_pitch_mm']):.1f}"
                ),
                demand=max(
                    float(bolts["minimum_pitch_mm"]),
                    float(bolts["pitch_mm"]),
                ),
                resistance=float(bolts["maximum_pitch_mm"]),
                units="mm",
                source="Mahachi Chapter 7.3 and connection detailing limit.",
            ),
            _check(
                reference="HC-04B",
                name="End-plate bolt end and edge distances",
                equation="e >= 1.5d",
                substitution=(
                    f"min({float(bolts['edge_distance_mm']):.1f}, "
                    f"{float(bolts['end_distance_mm']):.1f}) >= "
                    f"{float(bolts['minimum_edge_distance_mm']):.1f}"
                ),
                demand=float(bolts["minimum_edge_distance_mm"]),
                resistance=min(
                    float(bolts["edge_distance_mm"]),
                    float(bolts["end_distance_mm"]),
                ),
                units="mm",
                source="Mahachi Chapter 7.3 and SANS 10162 bolt detailing.",
            ),
            _check(
                reference="HC-04C",
                name="End-plate minimum bolt gauge",
                equation="g >= 2.7d",
                substitution=(
                    f"{float(bolts['gauge_mm']):.1f} >= "
                    f"{float(bolts['minimum_gauge_mm']):.1f}"
                ),
                demand=float(bolts["minimum_gauge_mm"]),
                resistance=float(bolts["gauge_mm"]),
                units="mm",
                source="Mahachi Chapter 7.3 and SANS 10162 bolt detailing.",
            ),
            _check(
                reference="HC-04D",
                name="Bolt-line fit within supporting flange",
                equation="g/2 + e_min <= b_support/2",
                substitution=(
                    f"{float(bolts['gauge_mm']) / 2:.1f} + "
                    f"{float(bolts['minimum_edge_distance_mm']):.1f} <= "
                    f"{float(supporting_member['b']) / 2:.1f}"
                ),
                demand=(
                    float(bolts["gauge_mm"]) / 2.0
                    + float(bolts["minimum_edge_distance_mm"])
                ),
                resistance=float(supporting_member["b"]) / 2.0,
                units="mm",
                source="Inside-flange bolt-layout geometry.",
                note=(
                    "The bolt-hole centreline and minimum edge distance must "
                    "fit inside the supporting flange."
                ),
            ),
        ]
        weld = _rectangular_weld_group(
            axial_kN=float(envelope.get("axial_force_kN", 0.0)),
            shear_kN=float(envelope.get("shear_force_kN", 0.0)),
            moment_kNm=float(envelope.get("major_moment_kNm", 0.0)),
            height_mm=(
                float(rafter["h"])
                + float(location.get("added_depth_mm", 0.0))
            ),
            width_mm=float(rafter["b"]),
            thicker_part_mm=max(
                float(connection["plate"]["provided_thickness_mm"]),
                float(rafter["tf"]),
            ),
            thinner_part_mm=min(
                float(rafter["tw"]),
                float(connection["plate"]["provided_thickness_mm"]),
            ),
        )
        stiffeners = _stiffener_checks(
            connection.get("stiffeners", {}),
            demand_kN=flange_force,
            connected_thickness_mm=float(
                connection["plate"]["provided_thickness_mm"]
            ),
            fy_mpa=steel_yield_mpa,
        )
        components = connection.get("supporting_member_components")
        if not components:
            components = supporting_member_components(
                supporting_member=supporting_member,
                connected_member=rafter,
                bolt_gauge_mm=float(bolts["gauge_mm"]),
                bolt_tension_resistance_kN=float(
                    bolts["tension_resistance_kN"]
                ),
                row_demand_kN=row_demand,
                flange_force_kN=flange_force,
                panel_shear_kN=flange_force,
                fy_mpa=steel_yield_mpa,
            )
        flange_component = components["flange_t_stub"]
        local_checks = [
            _check(
                reference="HC-05A",
                name=f"{supporting_label} flange T-stub Mode 1",
                equation="R_1 = 4 M_pl / m",
                substitution=(
                    f"{row_demand:.2f} / "
                    f"{float(flange_component['mode_1_complete_yielding_kN']):.2f}"
                ),
                demand=row_demand,
                resistance=float(
                    flange_component["mode_1_complete_yielding_kN"]
                ),
                units="kN",
                source="EN 1993-1-8 component-method equivalent T-stub.",
                note=(
                    "A failed check requires transverse stiffeners or a "
                    f"thicker/stronger {source_target} flange."
                ),
            ),
            _check(
                reference="HC-05B",
                name=f"{supporting_label} flange T-stub Mode 2",
                equation="R_2 = (2 M_pl + n sum(B_t)) / (m + n)",
                substitution=(
                    f"{row_demand:.2f} / "
                    f"{float(flange_component['mode_2_bolt_and_yielding_kN']):.2f}"
                ),
                demand=row_demand,
                resistance=float(
                    flange_component["mode_2_bolt_and_yielding_kN"]
                ),
                units="kN",
                source="EN 1993-1-8 component-method equivalent T-stub.",
                note=(
                    "A failed check requires transverse stiffeners or a "
                    f"thicker/stronger {source_target} flange."
                ),
            ),
            _check(
                reference="HC-05C",
                name=f"{supporting_label} flange T-stub Mode 3",
                equation="R_3 = sum(B_t)",
                substitution=(
                    f"{row_demand:.2f} / "
                    f"{float(flange_component['mode_3_bolt_failure_kN']):.2f}"
                ),
                demand=row_demand,
                resistance=float(
                    flange_component["mode_3_bolt_failure_kN"]
                ),
                units="kN",
                source="EN 1993-1-8 component-method equivalent T-stub.",
            ),
            _check(
                reference="HC-06",
                name=f"{supporting_label} web tension yielding",
                equation="T_r = phi t_w l_eff f_y",
                substitution=(
                    f"{flange_force:.2f} / "
                    f"{float(components['web_tension_yielding']['resistance_kN']):.2f}"
                ),
                demand=flange_force,
                resistance=float(
                    components["web_tension_yielding"]["resistance_kN"]
                ),
                units="kN",
                source="SANS 10162 supporting-web tension-yielding model.",
            ),
            _check(
                reference="HC-07",
                name=f"{supporting_label} web compression crippling",
                equation="B_r = 0.80 t_w l_eff f_y",
                substitution=(
                    f"{flange_force:.2f} / "
                    f"{float(components['web_compression_crippling']['resistance_kN']):.2f}"
                ),
                demand=flange_force,
                resistance=float(
                    components["web_compression_crippling"]["resistance_kN"]
                ),
                units="kN",
                source="SANS 10162 web compression crippling model.",
            ),
            _check(
                reference="HC-08",
                name=f"{supporting_label} web compression buckling",
                equation="B_r = 0.80(640000)t_w l_eff/(h_w/t_w)^2",
                substitution=(
                    f"{flange_force:.2f} / "
                    f"{float(components['web_compression_buckling']['resistance_kN']):.2f}"
                ),
                demand=flange_force,
                resistance=float(
                    components["web_compression_buckling"]["resistance_kN"]
                ),
                units="kN",
                source="SANS 10162 supporting-web compression buckling model.",
            ),
            _check(
                reference="HC-09",
                name=f"{supporting_label} web panel shear",
                equation="V_r = 0.55 phi f_y t_w h",
                substitution=(
                    f"{float(components['web_panel_shear']['demand_kN']):.2f} / "
                    f"{float(components['web_panel_shear']['resistance_kN']):.2f}"
                ),
                demand=float(components["web_panel_shear"]["demand_kN"]),
                resistance=float(
                    components["web_panel_shear"]["resistance_kN"]
                ),
                units="kN",
                source="SANS 10162 supporting-web panel shear model.",
                note=(
                    "A failed panel-shear check requires a doubler plate or "
                    "revised connection; transverse flange stiffeners alone "
                    "do not resolve it."
                ),
            ),
        ]
        reinforced = (
            stiffeners["status"] == "PASS"
            and any(item["status"] == "FAIL" for item in local_checks[:-1])
        )
        if reinforced:
            for item in local_checks[:-1]:
                if item["status"] == "FAIL":
                    item["status"] = "STIFFENER_REQUIRED"
                    item["note"] = (
                        f"{item.get('note', '')} The automatic transverse "
                        "stiffener load path is checked separately under ST-01 "
                        "and ST-02."
                    ).strip()
        calculated_pass = (
            all(item["status"] == "PASS" for item in checks)
            and all(
                item["status"] in {"PASS", "STIFFENER_REQUIRED"}
                for item in local_checks
            )
            and weld["status"] == "PASS"
            and stiffeners["status"] in {"PASS", "NOT_REQUIRED"}
        )
        locations.append({
            "location": location["location"],
            "connection_type": connection_type,
            "supporting_member_section": supporting_member_section,
            "supporting_member_type": supporting_member_type,
            "status": (
                "PASS_WITH_STIFFENERS"
                if calculated_pass and reinforced
                else ("PASS" if calculated_pass else "FAIL")
            ),
            "checks": checks,
            "prying": prying,
            "end_plate_weld": weld,
            "stiffener_checks": stiffeners,
            "local_member_checks": local_checks,
            "haunch_section_checks": _haunch_section_checks(snapshot, location),
        })
    return {
        "status": (
            "PASS"
            if locations
            and all(
                item["status"] in {"PASS", "PASS_WITH_STIFFENERS"}
                and item.get("haunch_section_checks", {}).get("status") == "PASS"
                for item in locations
            )
            else (
                "NOT_REQUIRED" if not locations
                else (
                    "PASS_WITH_INPUT_REQUIRED"
                    if all(
                        item["status"] in {"PASS", "PASS_WITH_STIFFENERS"}
                        for item in locations
                    )
                    else "FAIL"
                )
            )
        ),
        "locations": locations,
    }


def _haunch_section_checks(
    snapshot: Mapping[str, Any],
    location: Mapping[str, Any],
) -> dict[str, Any]:
    """Run post-analysis gross-web checks for the tapered haunch segments."""

    # Imported lazily because design.py owns the connection-face grouping and
    # imports this module for the completed post-analysis checks.
    from .design import _connection_face_samples

    samples = _connection_face_samples(snapshot)
    action_key = str(location.get("action_key", ""))
    face_samples = (
        [*samples.get("left_eaves", []), *samples.get("right_eaves", [])]
        if action_key == "eaves"
        else samples.get(action_key, [])
    )
    parent_members = {str(item.get("member", "")) for item in face_samples}
    rows = []
    for item in snapshot.get("results", {}).get("members", []):
        if str(item.get("member_type", "")).lower() != "rafter":
            continue
        if str(item.get("parent_member", "")) not in parent_members:
            continue
        try:
            added_depth = float(item.get("section_properties", {}).get(
                "haunch_added_depth_mm", 0.0
            ))
        except (TypeError, ValueError):
            added_depth = 0.0
        if added_depth > 0.0:
            rows.append(item)
    if not rows:
        return {
            "status": "INPUT_REQUIRED",
            "checks": [],
            "load_combinations": [],
            "reason": "No stored tapered-haunch segment actions were found; re-run the analysis.",
        }

    fy = float(location.get("steel_yield_mpa", STEEL_FY_MPA))
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("load_combination", "")), []).append(row)
    combination_results = []
    for combination, combination_rows in sorted(grouped.items()):
        governing = max(
            combination_rows,
            key=lambda item: abs(float(item.get("shear_force", 0.0))),
        )
        properties = governing.get("section_properties", {})
        try:
            tw = float(properties["tw"])
            hw = float(properties["hw"])
            shear = abs(float(governing.get("shear_force", 0.0)))
        except (KeyError, TypeError, ValueError):
            combination_results.append({
                "load_combination": combination,
                "status": "INPUT_REQUIRED",
                "governing_segment": governing.get("governing_segment", ""),
                "checks": [],
                "reason": "Composite haunch web properties were not stored.",
            })
            continue
        resistance = RESISTANCE_FACTOR * 0.55 * fy * tw * hw / 1000.0
        check = _check(
            reference="HH-01",
            name="Haunch composite web shear yielding",
            equation="V_r = 0.55 phi f_y t_w h_w",
            substitution=(
                f"{shear:.3f} / (0.55 x {RESISTANCE_FACTOR:.2f} x {fy:.1f} x "
                f"{tw:.2f} x {hw:.1f} / 1000)"
            ),
            demand=shear,
            resistance=resistance,
            units="kN",
            source="SANS 10162 web shear resistance model used by the frame connection checks.",
            note=(
                "Gross-web yielding only; web shear buckling, local bearing and "
                "longitudinal donor-weld transfer remain separate checks."
            ),
        )
        combination_results.append({
            "load_combination": combination,
            "status": check["status"],
            "governing_segment": governing.get("governing_segment", ""),
            "station_start_mm": float(governing.get("segment_start_mm", 0.0)),
            "station_end_mm": float(governing.get("segment_end_mm", 0.0)),
            "haunch_added_depth_mm": float(properties.get("haunch_added_depth_mm", 0.0)),
            "checks": [check],
        })

    weld_transfer = _check(
        reference="HH-02",
        name="Longitudinal donor-haunch weld transfer",
        equation="q = VQ/I; weld resistance from effective throat",
        substitution="Not calculated until the continuous weld path and effective throat are confirmed.",
        demand=0.0,
        resistance=0.0,
        units="kN/mm",
        source="SANS 10162 welded-joint design basis; fabrication topology required.",
        completed=False,
        note=(
            "The donor web is shown welded to the main rafter, but the current "
            "connection input has no weld size, continuity or termination field."
        ),
    )
    statuses = [item["status"] for item in combination_results]
    status = (
        "FAIL" if "FAIL" in statuses else
        "INPUT_REQUIRED" if "INPUT_REQUIRED" in statuses or weld_transfer["status"] == "INPUT_REQUIRED" else
        "PASS"
    )
    return {
        "status": status,
        "checks": [weld_transfer],
        "load_combinations": combination_results,
        "weld_transfer": weld_transfer,
        "source": "Post-analysis tapered-haunch station checks; one governing segment per ULS combination.",
    }


def calculate_connection_checks(
    snapshot: Mapping[str, Any],
    *,
    base_plates: Mapping[str, Any],
    haunch_connections: Mapping[str, Any],
) -> dict[str, Any]:
    """Calculate post-analysis checks from final member sizes and actions."""

    base = _base_plate_checks(snapshot, base_plates)
    haunch = _haunch_checks(snapshot, haunch_connections)
    failed = base["status"] == "FAIL" or haunch["status"] == "FAIL"
    return {
        "schema_version": 2,
        "status": "FAIL" if failed else "PASS_WITH_INPUT_REQUIRED",
        "base_plates": base,
        "haunch_connections": haunch,
        "completed_check_scope": [
            "Donor-section haunch cut-depth geometry",
            "Base-plate concrete bearing and plate bending",
            "Bolt distances and steel shear/tension interaction",
            "Red Book HD-bolt anchor-plate estimate for 25 MPa concrete",
            "End-plate T-stub Modes 1, 2 and 3 including prying",
            "E70XX fillet/CJP weld selection from elastic weld-group demand",
            "Stiffener yielding, plate-column buckling and weld demand",
            (
                "Supporting-flange T-stub Modes 1, 2 and 3; web tension "
                "yielding, compression crippling/buckling and panel shear"
            ),
        ],
        "input_required_scope": [
            "Verification of the required 7d concrete edge distance",
            "Pedestal geometry, reinforcement and anchor load-path detailing",
        ],
        "references": [
            "EN 1993-1-8 equivalent T-stub component method.",
            "Mahachi Chapter 7.3-7.5, 7.7-7.9.",
            "SANS 10162 steel resistance models used by the frame engine.",
        ],
        "warning": (
            "Checks marked INPUT_REQUIRED are not passed automatically. "
            "Connection drawings remain calculation-review markups until all "
            "project anchor and fabrication inputs are confirmed."
        ),
    }


def calculate_base_plate_checks(
    snapshot: Mapping[str, Any],
    base_plates: Mapping[str, Any],
) -> dict[str, Any]:
    """Calculate the shared base-plate scope without any haunch dependency."""

    base = _base_plate_checks(snapshot, base_plates)
    return {
        "schema_version": 2,
        "status": (
            "PASS_WITH_INPUT_REQUIRED"
            if base["status"] == "PASS_WITH_INPUT_REQUIRED"
            else "FAIL"
        ),
        "base_plates": base,
        "haunch_connections": {"status": "NOT_REQUIRED", "locations": []},
        "completed_check_scope": [
            "Base-plate concrete bearing and plate bending",
            "Bolt distances and steel shear/tension interaction",
            "Red Book HD-bolt anchor-plate estimate for 25 MPa concrete",
            "Column-to-base-plate weld and required stiffeners",
        ],
        "input_required_scope": [
            "Verification of the required 7d concrete edge distance",
            "Pedestal geometry, reinforcement and anchor load-path detailing",
            "Truss bearings, gussets, splices and restraint connections",
        ],
        "references": [
            "Mahachi Chapter 7.3-7.5 and 7.9.",
            "SANS 10162 steel resistance models used by the frame engine.",
            "The Red Book holding-down-bolt anchorage estimates.",
        ],
        "warning": (
            "The truss connection scope is limited to column base plates. "
            "Items marked INPUT_REQUIRED must be resolved before fabrication."
        ),
    }
