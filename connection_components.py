"""Shared component-method checks for bolted portal-frame end plates.

The preliminary geometry selector and the detailed calculation report must use
the same resistance model.  This module therefore contains only deterministic
component calculations and has no dependency on either renderer.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


RESISTANCE_FACTOR = 0.90
STEEL_FY_MPA = 355.0


def t_stub_modes(
    *,
    m_mm: float,
    n_mm: float,
    effective_length_mm: float,
    plate_thickness_mm: float,
    bolt_tension_resistance_kN: float,
    bolts_per_row: int = 2,
    fy_mpa: float = STEEL_FY_MPA,
    resistance_factor: float = RESISTANCE_FACTOR,
    backing_plate_moment_kNm: float = 0.0,
) -> dict[str, Any]:
    """Return the three equivalent T-stub resistance modes for one bolt row.

    The equations follow the component-method form used by the reference
    calculation: complete flange yielding, combined bolt/flange yielding and
    bolt failure.  All returned row resistances are in kN.
    """

    m = max(float(m_mm), 1.0)
    n = max(float(n_mm), 1.0)
    effective_length = max(float(effective_length_mm), 1.0)
    thickness = max(float(plate_thickness_mm), 0.0)
    bolt_count = max(int(bolts_per_row), 1)
    bolt_resistance = max(float(bolt_tension_resistance_kN), 0.0)
    plastic_moment_kNm = (
        0.25
        * resistance_factor
        * effective_length
        * thickness**2
        * fy_mpa
        / 1_000_000.0
    )
    mode_1 = (
        (4.0 * plastic_moment_kNm + 2.0 * backing_plate_moment_kNm)
        * 1000.0
        / m
    )
    mode_2 = (
        2.0 * plastic_moment_kNm * 1000.0
        + n * bolt_count * bolt_resistance
    ) / (m + n)
    mode_3 = bolt_count * bolt_resistance
    modes = {
        "mode_1_complete_yielding_kN": mode_1,
        "mode_2_bolt_and_yielding_kN": mode_2,
        "mode_3_bolt_failure_kN": mode_3,
    }
    governing_name, governing_resistance = min(
        modes.items(), key=lambda item: item[1]
    )
    return {
        "m_mm": m,
        "n_mm": n,
        "effective_length_mm": effective_length,
        "plate_thickness_mm": thickness,
        "plastic_moment_resistance_kNm": plastic_moment_kNm,
        **modes,
        "governing_mode": governing_name,
        "resistance_kN": governing_resistance,
        "equations": [
            "M_pl = 0.25 phi l_eff t^2 f_y",
            "R_1 = (4 M_pl + 2 M_bp) / m",
            "R_2 = (2 M_pl + n sum(B_t)) / (m + n)",
            "R_3 = sum(B_t)",
        ],
    }


def t_stub_geometry(
    *,
    bolt_gauge_mm: float,
    web_thickness_mm: float,
    root_radius_mm: float,
    free_edge_width_mm: float,
) -> dict[str, float]:
    """Return auditable ``m``, ``n`` and effective length for one component."""

    half_gauge = float(bolt_gauge_mm) / 2.0
    m = max(
        half_gauge
        - float(web_thickness_mm) / 2.0
        - 0.8 * float(root_radius_mm),
        1.0,
    )
    n = max(float(free_edge_width_mm) / 2.0 - half_gauge, 1.0)
    return {
        "m_mm": m,
        "n_mm": n,
        "effective_length_mm": min(
            float(free_edge_width_mm),
            2.0 * (m + n),
        ),
    }


def supporting_member_components(
    *,
    supporting_member: Mapping[str, Any],
    connected_member: Mapping[str, Any],
    bolt_gauge_mm: float,
    bolt_tension_resistance_kN: float,
    row_demand_kN: float,
    flange_force_kN: float,
    panel_shear_kN: float,
) -> dict[str, Any]:
    """Check the unreinforced supporting flange and web components."""

    flange_geometry = t_stub_geometry(
        bolt_gauge_mm=bolt_gauge_mm,
        web_thickness_mm=float(supporting_member["tw"]),
        root_radius_mm=float(supporting_member.get("r1", 0.0)),
        free_edge_width_mm=float(supporting_member["b"]),
    )
    flange_modes = t_stub_modes(
        **flange_geometry,
        plate_thickness_mm=float(supporting_member["tf"]),
        bolt_tension_resistance_kN=bolt_tension_resistance_kN,
    )
    flange_utilisation = (
        row_demand_kN / flange_modes["resistance_kN"]
        if flange_modes["resistance_kN"] > 0
        else math.inf
    )

    tw = float(supporting_member["tw"])
    hw = float(supporting_member["hw"])
    fy = STEEL_FY_MPA
    connected_width = float(connected_member["b"])
    tension_effective_length = 2.0 * connected_width
    compression_effective_length = max(
        float(supporting_member["b"]) - tw,
        1.0,
    )
    web_tension_resistance = (
        RESISTANCE_FACTOR
        * tw
        * tension_effective_length
        * fy
        / 1000.0
    )
    web_compression_crippling = (
        0.80 * tw * compression_effective_length * fy / 1000.0
    )
    web_compression_buckling = (
        0.80
        * 640_000.0
        * tw
        * compression_effective_length
        / max((hw / max(tw, 1e-9)) ** 2, 1e-9)
        / 1000.0
    )
    web_panel_shear = (
        0.55
        * RESISTANCE_FACTOR
        * fy
        * tw
        * float(supporting_member["h"])
        / 1000.0
    )

    checks = {
        "flange_t_stub": {
            **flange_modes,
            "demand_kN": row_demand_kN,
            "utilisation": flange_utilisation,
            "status": "PASS" if flange_utilisation <= 1.0 else "FAIL",
        },
        "web_tension_yielding": {
            "effective_length_mm": tension_effective_length,
            "demand_kN": flange_force_kN,
            "resistance_kN": web_tension_resistance,
        },
        "web_compression_crippling": {
            "effective_length_mm": compression_effective_length,
            "demand_kN": flange_force_kN,
            "resistance_kN": web_compression_crippling,
        },
        "web_compression_buckling": {
            "effective_length_mm": compression_effective_length,
            "demand_kN": flange_force_kN,
            "resistance_kN": web_compression_buckling,
        },
        "web_panel_shear": {
            "demand_kN": abs(panel_shear_kN),
            "resistance_kN": web_panel_shear,
        },
    }
    for key, check in checks.items():
        if key == "flange_t_stub":
            continue
        resistance = float(check["resistance_kN"])
        utilisation = (
            float(check["demand_kN"]) / resistance
            if resistance > 0
            else math.inf
        )
        check["utilisation"] = utilisation
        check["status"] = "PASS" if utilisation <= 1.0 else "FAIL"

    transverse_keys = (
        "flange_t_stub",
        "web_tension_yielding",
        "web_compression_crippling",
        "web_compression_buckling",
    )
    return {
        **checks,
        "transverse_stiffeners_required": any(
            checks[key]["status"] == "FAIL" for key in transverse_keys
        ),
        "panel_zone_reinforcement_required": (
            checks["web_panel_shear"]["status"] == "FAIL"
        ),
    }
