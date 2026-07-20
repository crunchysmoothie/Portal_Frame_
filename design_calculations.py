"""Store structured design results once, then format reports without analysis.

The analysis engine calls ``build_calculation_sheet_data_from_frame`` after the
final model has been solved. Later invocations of this module load that stored
snapshot, select the requested scope, and export HTML, JSON and PDF without
building a PyNite model or searching sections again.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from enum import Enum
from html import escape
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import member_database as mdb
from analysis_visualisation import build_analysis_visualisation
from analysis_snapshot import load_analysis_snapshot, validate_snapshot_input
from strength_checks import (
    element_property_details,
    member_class_details,
    member_design,
    section_properties,
)


class ReportScope(str, Enum):
    """User-selectable calculation-sheet detail level."""

    CRITICAL = "critical"
    FULL = "full"
    LOAD_COMBINATION = "load_combination"


@dataclass(frozen=True)
class CalculationItem:
    reference: str
    title: str
    equation: str
    substitution: str
    result: float
    units: str = ""
    limit: float | None = None
    status: str = "INFO"
    latex: str = ""


@dataclass(frozen=True)
class MemberCalculation:
    member: str
    member_type: str
    section: str
    load_combination: str
    axial_force: float
    axial_action: str
    major_moment: float
    section_class: int
    inputs: tuple[CalculationItem, ...]
    classification: tuple[CalculationItem, ...]
    parameters: tuple[CalculationItem, ...]
    resistances: tuple[CalculationItem, ...]
    calculations: tuple[CalculationItem, ...]
    governing_ratio: float
    governing_check: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReactionResult:
    node: str
    load_combination: str
    fx: float
    fy: float
    fz: float
    mx: float
    my: float
    mz: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CalculationSheetData:
    title: str
    scope: ReportScope
    project: Mapping[str, Any] = field(default_factory=dict)
    frame_summary: Mapping[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    load_combinations: list[dict[str, Any]] = field(default_factory=list)
    deflections: list[dict[str, Any]] = field(default_factory=list)
    members: list[MemberCalculation] = field(default_factory=list)
    reactions: list[ReactionResult] = field(default_factory=list)
    bracing_design: Mapping[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    visualisation: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "scope": self.scope.value,
            "project": dict(self.project),
            "frame_summary": dict(self.frame_summary),
            "assumptions": list(self.assumptions),
            "load_combinations": list(self.load_combinations),
            "deflections": list(self.deflections),
            "members": [item.to_dict() for item in self.members],
            "reactions": [item.to_dict() for item in self.reactions],
            "bracing_design": dict(self.bracing_design),
            "warnings": list(self.warnings),
            "visualisation": dict(self.visualisation),
        }


def calculation_sheet_from_dict(raw: Mapping[str, Any]) -> CalculationSheetData:
    """Rebuild typed calculation-sheet data from a stored snapshot record."""

    members = []
    for member in raw.get("members", []):
        member_data = dict(member)
        for field_name in (
            "inputs", "classification", "parameters", "resistances", "calculations",
        ):
            member_data[field_name] = tuple(
                CalculationItem(**item) for item in member_data.get(field_name, [])
            )
        members.append(MemberCalculation(**member_data))
    reactions = [ReactionResult(**item) for item in raw.get("reactions", [])]
    return CalculationSheetData(
        title=raw["title"],
        scope=ReportScope(raw.get("scope", ReportScope.FULL.value)),
        project=dict(raw.get("project", {})),
        frame_summary=dict(raw.get("frame_summary", {})),
        assumptions=list(raw.get("assumptions", [])),
        load_combinations=list(raw.get("load_combinations", [])),
        deflections=list(raw.get("deflections", [])),
        members=members,
        reactions=reactions,
        bracing_design=dict(raw.get("bracing_design", {})),
        warnings=list(raw.get("warnings", [])),
        visualisation=dict(raw.get("visualisation", {})),
    )


def _check_item(
    reference: str,
    title: str,
    equation: str,
    substitution: str,
    result: float,
    latex: str = "",
) -> CalculationItem:
    finite = math.isfinite(float(result))
    return CalculationItem(
        reference=reference,
        title=title,
        equation=equation,
        substitution=substitution,
        result=float(result),
        limit=1.0,
        status="PASS" if finite and result <= 1.0 else "FAIL",
        latex=latex,
    )


def _info_item(reference, title, equation, substitution, result, units="", latex=""):
    return CalculationItem(
        reference=reference,
        title=title,
        equation=equation,
        substitution=substitution,
        result=float(result),
        units=units,
        status="INFO",
        latex=latex,
    )


def calculate_member_design(
    member_properties: Mapping[str, float],
    member_actions: Mapping[str, Any],
    material_properties: Mapping[str, float],
    load_combination: str,
) -> MemberCalculation:
    """Return auditable member checks matching ``strength_checks.member_design``.

    ``member_actions`` uses the same keys as ``portal_frame_analysis.internal_forces``:
    Name, type, section, Class, Cu, Mx_max, w1, klx and kly.
    """

    sec = section_properties(member_properties, member_actions, material_properties)
    css, oms, ltb = member_design(member_properties, member_actions, material_properties)
    cu = float(member_actions["Cu"])
    tu = abs(cu)
    mx = abs(float(member_actions["Mx_max"]))
    mx_i = float(member_actions["Mx_top"])
    mx_j = float(member_actions["Mx_bot"])
    member_class = int(member_actions["Class"])
    m_fac = 0.85 if member_class < 3 else 1.0
    w1 = float(member_actions["w1"])
    w2 = float(member_actions["w2"])
    klx = float(member_actions["klx"])
    kly = float(member_actions["kly"])
    lx = float(member_actions.get("lx", klx))
    ly = float(member_actions.get("ly", kly))
    kx = float(member_actions.get("kx", klx / lx if lx else 1.0))
    ky = float(member_actions.get("ky", kly / ly if ly else 1.0))
    fy = float(material_properties["fy"])
    elastic_modulus = float(material_properties["E"])
    shear_modulus = float(material_properties["G"])
    area = float(member_properties["A"])
    depth = float(member_properties["h"])
    flange_width = float(member_properties["b"])
    web_thickness = float(member_properties["tw"])
    flange_thickness = float(member_properties["tf"])
    ix = float(member_properties["Ix"])
    iy = float(member_properties["Iy"])
    rx = float(member_properties["rx"])
    ry = float(member_properties["ry"])
    zx = float(sec["Zx"])
    torsional_constant = float(member_properties["J"])
    warping_constant = float(member_properties["Cw"])
    class_details = member_class_details(cu, member_properties, material_properties)
    factor_details = element_property_details(mx, mx_i, mx_j)

    inputs = (
        _info_item("I-01", "Gross area, Ag", "A_g", "", area, "10^3 mm^2", latex=r"A_g"),
        _info_item("I-02", "Overall depth, h", "h", "", depth, "mm", latex=r"h"),
        _info_item("I-03", "Flange width, b", "b", "", flange_width, "mm", latex=r"b"),
        _info_item("I-04", "Web thickness, tw", "t_w", "", web_thickness, "mm", latex=r"t_w"),
        _info_item("I-05", "Flange thickness, tf", "t_f", "", flange_thickness, "mm", latex=r"t_f"),
        _info_item("I-06", "Major-axis second moment, Ix", "I_x", "", ix, "10^6 mm^4", latex=r"I_x"),
        _info_item("I-07", "Minor-axis second moment, Iy", "I_y", "", iy, "10^6 mm^4", latex=r"I_y"),
        _info_item("I-08", "Major-axis radius of gyration, rx", "r_x", "", rx, "mm", latex=r"r_x"),
        _info_item("I-09", "Minor-axis radius of gyration, ry", "r_y", "", ry, "mm", latex=r"r_y"),
        _info_item("I-10", "Major-axis section modulus, Zx", "Z_x", "", zx, "10^3 mm^3", latex=r"Z_x"),
        _info_item("I-11", "Torsional constant, J", "J", "", torsional_constant, "10^3 mm^4", latex=r"J"),
        _info_item("I-12", "Warping constant, Cw", "C_w", "", warping_constant, "10^9 mm^6", latex=r"C_w"),
        _info_item("I-13", "Yield strength, fy", "f_y", "", fy, "MPa", latex=r"f_y"),
        _info_item("I-14", "Elastic modulus, E", "E", "", elastic_modulus, "GPa", latex=r"E"),
        _info_item("I-15", "Shear modulus, G", "G", "", shear_modulus, "GPa", latex=r"G"),
    )

    flange_limits = class_details["flange_limits"]
    web_limits = class_details["web_limits"]
    classification = (
        _info_item(
            "CL-01", "Flange slenderness",
            "c_f/t_f = b/(2t_f)",
            f"{flange_width:.3f}/(2 x {flange_thickness:.3f})",
            class_details["flange_ratio"],
            latex=r"\frac{c_f}{t_f}=\frac{b}{2t_f}",
        ),
        _info_item(
            "CL-02", "Flange class",
            "Class from 145/sqrt(fy), 170/sqrt(fy), 200/sqrt(fy)",
            f"ratio={class_details['flange_ratio']:.3f}; limits={flange_limits[0]:.3f}, {flange_limits[1]:.3f}, {flange_limits[2]:.3f}",
            class_details["flange_class"],
            latex=r"\text{limits}=\frac{145,170,200}{\sqrt{f_y}}",
        ),
        _info_item(
            "CL-03", "Compression ratio",
            "alpha = max(Cu,0)/(0.9 Ag fy)",
            f"max({cu:.3f},0)/(0.90 x {area:.3f} x {fy:.1f})",
            class_details["compression_ratio"],
            latex=r"\alpha=\frac{\max(C_u,0)}{0.9A_gf_y}",
        ),
        _info_item(
            "CL-04", "Web slenderness",
            "cw/tw = (h - 2tf)/tw",
            f"({depth:.3f} - 2 x {flange_thickness:.3f})/{web_thickness:.3f}",
            class_details["web_ratio"],
            latex=r"\frac{c_w}{t_w}=\frac{h-2t_f}{t_w}",
        ),
        _info_item(
            "CL-05", "Web class",
            "Class from (1100,1700,1900)/sqrt(fy) x (1 - beta alpha)",
            f"ratio={class_details['web_ratio']:.3f}; limits={web_limits[0]:.3f}, {web_limits[1]:.3f}, {web_limits[2]:.3f}",
            class_details["web_class"],
            latex=r"\text{limits}=\frac{1100,1700,1900}{\sqrt{f_y}}(1-\beta\alpha)",
        ),
        _info_item(
            "CL-06", "Governing section class",
            "Class = max(flange class, web class)",
            f"max({class_details['flange_class']}, {class_details['web_class']})",
            class_details["class"],
            latex=r"\text{Class}=\max(\text{Class}_f,\text{Class}_w)",
        ),
    )

    if factor_details["intermediate_peak"]:
        omega2_substitution = (
            f"|Mmax|={mx:.3f} > 1.10 max(|Mi|,|Mj|)="
            f"{1.10 * max(abs(mx_i), abs(mx_j)):.3f}; omega2=1.000"
        )
        omega2_equation = "omega2 = 1.0 for an intermediate moment peak"
        omega2_latex = r"\omega_2=1.0"
    else:
        omega2_substitution = (
            f"min[1.75 + 1.05 x {factor_details['kappa']:.4f} + "
            f"0.30 x {factor_details['kappa']:.4f}^2, 2.50]"
        )
        omega2_equation = "omega2 = min[1.75 + 1.05 kappa + 0.30 kappa^2, 2.50]"
        omega2_latex = r"\omega_2=\min(1.75+1.05\kappa+0.30\kappa^2,2.50)"

    parameters = (
        _info_item("P-01", "Major-axis effective-length factor, Kx", "Kx", f"Kx={kx:.3f}", kx, latex=r"K_x"),
        _info_item(
            "P-02", "Major-axis effective length, KxLx",
            "KxLx = Kx x Lx", f"{kx:.3f} x {lx:.3f}", klx, "m",
            latex=r"K_xL_x=K_x\,L_x",
        ),
        _info_item("P-03", "Minor-axis effective-length factor, Ky", "Ky", f"Ky={ky:.3f}", ky, latex=r"K_y"),
        _info_item(
            "P-04", "Minor-axis unbraced length, KyLy",
            "KyLy = Ky x Ly", f"{ky:.3f} x {ly:.3f}", kly, "m",
            latex=r"K_yL_y=K_y\,L_y",
        ),
        _info_item(
            "P-05", "End-moment ratio, kappa",
            "kappa = -Mmin/Mmax",
            f"-({factor_details['m_min']:.3f})/({factor_details['m_max']:.3f})",
            factor_details["kappa"],
            latex=r"\kappa=-\frac{M_{\min}}{M_{\max}}",
        ),
        _info_item(
            "P-06", "Equivalent moment factor, omega1",
            "omega1 = 1.0 for transverse distributed loading",
            f"Clause 13.8.5; Mi={mx_i:.3f} kNm; Mj={mx_j:.3f} kNm",
            w1,
            latex=r"\omega_1=1.0",
        ),
        _info_item(
            "P-07", "LTB moment-gradient factor, omega2",
            omega2_equation, omega2_substitution, w2,
            latex=omega2_latex,
        ),
    )

    lambda_x = _info_item(
        "R-01", "Major-axis non-dimensional slenderness, lambda_x",
        "lambda_x = (KxLx/rx) sqrt[fy/(pi^2 E)]",
        f"({klx*1000:.1f}/{rx:.3f}) sqrt[{fy:.1f}/(pi^2 x {elastic_modulus*1000:.0f})]",
        sec["lamda_x"],
        latex=r"\lambda_x=\frac{K_xL_x}{r_x}\sqrt{\frac{f_y}{\pi^2E}}",
    )
    lambda_y = _info_item(
        "R-02", "Minor-axis non-dimensional slenderness, lambda_y",
        "lambda_y = (KyLy/ry) sqrt[fy/(pi^2 E)]",
        f"({kly*1000:.1f}/{ry:.3f}) sqrt[{fy:.1f}/(pi^2 x {elastic_modulus*1000:.0f})]",
        sec["lamda_y"],
        latex=r"\lambda_y=\frac{K_yL_y}{r_y}\sqrt{\frac{f_y}{\pi^2E}}",
    )
    euler_x = _info_item(
        "R-05", "Euler load about x-axis, Cex",
        "Cex = pi^2 E Ix/(KxLx)^2",
        f"pi^2 x {elastic_modulus:.1f} x {ix:.3f}/{klx:.3f}^2",
        sec["Cex"], "kN",
        latex=r"C_{ex}=\frac{\pi^2EI_x}{(K_xL_x)^2}",
    )
    critical_moment = _info_item(
        "R-06", "Elastic critical moment, Mcr",
        "Mcr = (omega2 pi/Lu) sqrt[EIy GJ + (pi E/Lu)^2 Iy Cw]",
        f"omega2={w2:.3f}; Lu={kly:.3f} m; Iy={iy:.3f}; J={torsional_constant:.3f}; Cw={warping_constant:.3f}",
        sec["Mcr"], "kNm",
        latex=r"M_{cr}=\frac{\omega_2\pi}{L_u}\sqrt{EI_yGJ+\left(\frac{\pi E}{L_u}\right)^2I_yC_w}",
    )
    supported_moment = _info_item(
        "R-07", "Supported major-axis moment resistance, Mrx",
        "Mrx = phi fy Zx",
        f"0.90 x {fy:.1f} x {zx:.3f}/1000",
        sec["Mrx"], "kNm",
        latex=r"M_{rx}=\phi f_yZ_x",
    )
    ltb_moment = _info_item(
        "R-08", "Laterally unsupported moment resistance, Mrx,LTB",
        "Clause 13.6 resistance from Mcr and Mi",
        f"Mcr={sec['Mcr']:.3f} kNm; Mi={min(sec['Mp'], sec['My']) if member_class >= 3 else sec['Mp']:.3f} kNm",
        sec["Mrx_ltb"], "kNm",
        latex=r"M_{rx,LTB}=f(M_{cr},M_i)",
    )

    if cu < 0.0:
        resistances = (
            _info_item(
                "R-00", "Gross-section tension resistance, Tr",
                "Tr = phi Ag fy", f"0.90 x {area:.3f} x {fy:.1f}",
                sec["Tr"], "kN", latex=r"T_r=\phi A_gf_y",
            ),
            CalculationItem(**{**asdict(critical_moment), "reference": "R-01"}),
            CalculationItem(**{**asdict(supported_moment), "reference": "R-02"}),
            CalculationItem(**{**asdict(ltb_moment), "reference": "R-03"}),
        )
        stress_relief_raw = mx / sec["Mrx_ltb"] - tu * zx / (sec["Mrx_ltb"] * area)
        items = (
            _check_item(
                "T-01", "Tension plus bending - additive check (13.9(a))",
                "U = Tu/Tr + Mx/Mrx",
                f"{tu:.3f}/{sec['Tr']:.3f} + {mx:.3f}/{sec['Mrx']:.3f}",
                float(css), latex=r"U=\frac{T_u}{T_r}+\frac{M_x}{M_{rx}}",
            ),
            _check_item(
                "T-02", "Tension plus LTB stress-relief check (13.9(b))",
                "U = max[0, Mx/Mrx,LTB - Tu Zx/(Mrx,LTB Ag)]",
                f"max[0, {mx:.3f}/{sec['Mrx_ltb']:.3f} - "
                f"{tu:.3f} x {zx:.3f}/({sec['Mrx_ltb']:.3f} x {area:.3f})] "
                f"(raw={stress_relief_raw:.3f})",
                float(ltb[0]),
                latex=r"U=\max\left[0,\frac{M_x}{M_{rx,LTB}}-\frac{T_uZ_x}{M_{rx,LTB}A_g}\right]",
            ),
            _check_item(
                "T-03", "Laterally unsupported bending",
                "U = Mx/Mrx,LTB", f"{mx:.3f}/{sec['Mrx_ltb']:.3f}",
                float(ltb[1]), latex=r"U=\frac{M_x}{M_{rx,LTB}}",
            ),
        )
        axial_action = "Tension"
    else:
        u1x = w1 / (1.0 - cu / sec["Cex"])
        u1x_min = max(1.0, u1x)
        resistances = (
            _info_item(
                "R-00", "Compressive resistance, Cr",
                "Cr = phi Ag fy", f"0.90 x {area:.3f} x {fy:.1f}",
                sec["Cr"], "kN", latex=r"C_r=\phi A_gf_y",
            ),
            lambda_x,
            lambda_y,
            _info_item(
                "R-03", "Major-axis compressive resistance, Crx",
                "Crx = phi Ag fy [1 + lambda_x^(2n)]^(-1/n); n=1.34",
                f"0.90 x {area:.3f} x {fy:.1f} x [1 + {sec['lamda_x']:.4f}^(2 x 1.34)]^(-1/1.34)",
                sec["Crx"], "kN",
                latex=r"C_{rx}=\phi A_gf_y\left(1+\lambda_x^{2n}\right)^{-1/n}",
            ),
            _info_item(
                "R-04", "Minor-axis compressive resistance, Cry",
                "Cry = phi Ag fy [1 + lambda_y^(2n)]^(-1/n); n=1.34",
                f"0.90 x {area:.3f} x {fy:.1f} x [1 + {sec['lamda_y']:.4f}^(2 x 1.34)]^(-1/1.34)",
                sec["Cry"], "kN",
                latex=r"C_{ry}=\phi A_gf_y\left(1+\lambda_y^{2n}\right)^{-1/n}",
            ),
            euler_x,
            critical_moment,
            supported_moment,
            ltb_moment,
            _info_item(
                "R-09", "Moment amplification factor, U1x",
                "U1x = omega1/(1 - Cu/Cex)",
                f"{w1:.3f}/(1 - {cu:.3f}/{sec['Cex']:.3f})", u1x,
                latex=r"U_{1x}=\frac{\omega_1}{1-C_u/C_{ex}}",
            ),
        )
        items = (
            _check_item(
                "C-01", "Cross-sectional strength",
                "U = Cu/Cr + m max(1,U1x) Mx/Mrx",
                f"{cu:.3f}/{sec['Cr']:.3f} + {m_fac:.2f} x {u1x_min:.3f} x {mx:.3f}/{sec['Mrx']:.3f}",
                float(css),
                latex=r"U=\frac{C_u}{C_r}+m\,\max(1,U_{1x})\frac{M_x}{M_{rx}}",
            ),
            _check_item(
                "C-02", "Overall member strength",
                "U = Cu/Crx + m U1x Mx/Mrx",
                f"{cu:.3f}/{sec['Crx']:.3f} + {m_fac:.2f} x {u1x:.3f} x {mx:.3f}/{sec['Mrx']:.3f}",
                float(oms),
                latex=r"U=\frac{C_u}{C_{rx}}+mU_{1x}\frac{M_x}{M_{rx}}",
            ),
            _check_item(
                "C-03", "Lateral-torsional buckling interaction",
                "U = Cu/Cry + m max(1,U1x) Mx/Mrx,LTB",
                f"{cu:.3f}/{sec['Cry']:.3f} + {m_fac:.2f} x {u1x_min:.3f} x {mx:.3f}/{sec['Mrx_ltb']:.3f}",
                float(ltb[0]),
                latex=r"U=\frac{C_u}{C_{ry}}+m\,\max(1,U_{1x})\frac{M_x}{M_{rx,LTB}}",
            ),
            _check_item(
                "C-04", "Laterally unsupported bending",
                "U = Mx/Mrx,LTB", f"{mx:.3f}/{sec['Mrx_ltb']:.3f}",
                float(ltb[1]), latex=r"U=\frac{M_x}{M_{rx,LTB}}",
            ),
        )
        axial_action = "Compression"

    governing = max(items, key=lambda item: item.result if math.isfinite(item.result) else math.inf)
    return MemberCalculation(
        member=str(member_actions["Name"]), member_type=str(member_actions["type"]),
        section=str(member_actions["section"]), load_combination=load_combination,
        axial_force=cu, axial_action=axial_action, major_moment=mx,
        section_class=member_class, inputs=inputs, classification=classification,
        parameters=parameters, resistances=resistances, calculations=items,
        governing_ratio=governing.result, governing_check=governing.reference,
        status="PASS" if all(item.status == "PASS" for item in items) else "FAIL",
    )


def _result_value(result_map: Any, combination: str) -> float:
    try:
        value = result_map.get(combination, 0.0)
    except AttributeError:
        value = result_map[combination]
    return float(value)


def collect_reactions(
    frame: Any,
    load_combinations: Iterable[str],
    support_nodes: Iterable[str] | None = None,
) -> list[ReactionResult]:
    """Collect six-component reactions from an analysed PyNite model."""

    selected = set(support_nodes) if support_nodes is not None else None
    reactions: list[ReactionResult] = []
    for combination in load_combinations:
        for node_name, node in frame.nodes.items():
            if selected is not None and node_name not in selected:
                continue
            if selected is None and not any(
                bool(getattr(node, restraint, False))
                for restraint in ("support_DX", "support_DY", "support_DZ",
                                  "support_RX", "support_RY", "support_RZ")
            ):
                continue
            reactions.append(
                ReactionResult(
                    node=node_name,
                    load_combination=combination,
                    fx=_result_value(node.RxnFX, combination),
                    fy=_result_value(node.RxnFY, combination),
                    fz=_result_value(node.RxnFZ, combination),
                    mx=_result_value(node.RxnMX, combination) / 1000,
                    my=_result_value(node.RxnMY, combination) / 1000,
                    mz=_result_value(node.RxnMZ, combination) / 1000,
                )
            )
    return reactions


def select_member_results(
    results: Sequence[MemberCalculation],
    scope: ReportScope,
    load_combination: str | None = None,
) -> list[MemberCalculation]:
    """Filter results for full, critical-only, or selected-combination reports."""

    if scope is ReportScope.FULL:
        return list(results)
    if scope is ReportScope.LOAD_COMBINATION:
        if not load_combination:
            raise ValueError("A load combination is required for LOAD_COMBINATION scope.")
        return [item for item in results if item.load_combination == load_combination]

    # Retain the governing tension and compression result for each member type.
    # This keeps the critical report concise while documenting both clause 13.8
    # (compression plus bending) and clause 13.9 (tension plus bending) paths.
    critical: dict[tuple[str, str], MemberCalculation] = {}
    for item in results:
        key = (item.member_type, item.axial_action)
        current = critical.get(key)
        if current is None or item.governing_ratio > current.governing_ratio:
            critical[key] = item
    return sorted(
        critical.values(),
        key=lambda item: (item.member_type, item.axial_action, item.member),
    )


def collect_member_calculations(
    actions_by_combination,
    member_db,
    rafter_section_type,
    column_section_type,
    material,
):
    """Convert the analysis engine's stored actions into full design records."""

    calculations = []
    for name, member_actions in actions_by_combination.items():
        for actions in member_actions:
            section_type = (
                rafter_section_type
                if actions["type"] == "rafter"
                else column_section_type
            )
            properties = mdb.member_properties(section_type, actions["section"], member_db)
            result = calculate_member_design(properties, actions, material, name)
            if not math.isfinite(result.governing_ratio):
                raise ValueError(
                    f"Non-finite design result for member {actions['Name']}, "
                    f"combination {name}."
                )
            calculations.append(result)
    return calculations


def _deflection_ratio(reference_mm, deflection_mm):
    """Return the reference-length/deflection ratio for serviceability display."""

    try:
        reference = float(reference_mm)
        deflection = abs(float(deflection_mm))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(reference) or not math.isfinite(deflection):
        return None
    if reference <= 0 or deflection <= 1e-12:
        return None
    return reference / deflection


def collect_deflections(
    frame,
    combinations,
    *,
    horizontal_reference_mm=0.0,
    vertical_reference_mm=0.0,
):
    results = []
    for combination in combinations:
        name = combination["name"]
        dx_node, dy_node = "", ""
        max_dx = max_dy = 0.0
        for node_name, node in frame.nodes.items():
            dx = abs(_result_value(node.DX, name))
            dy = abs(_result_value(node.DY, name))
            if dx > max_dx:
                max_dx, dx_node = dx, node_name
            if dy > max_dy:
                max_dy, dy_node = dy, node_name
        results.append({
            "load_combination": name,
            "max_dx": max_dx,
            "dx_node": dx_node,
            "horizontal_ratio": _deflection_ratio(horizontal_reference_mm, max_dx),
            "max_dy": max_dy,
            "dy_node": dy_node,
            "vertical_ratio": _deflection_ratio(vertical_reference_mm, max_dy),
        })
    return results


def build_frame_summary(data, member_db, rafter_section_type, column_section_type,
                        rafter_section, column_section, member_results,
                        reactions, deflections, bracing_design=None):
    """Build a compact whole-frame result and quantity summary."""

    frame_data = data.frame_data[0]
    rafter = mdb.member_properties(rafter_section_type, rafter_section, member_db)
    column = mdb.member_properties(column_section_type, column_section, member_db)
    rafter_members = [member for member in data.members if member.type == "rafter"]
    column_members = [member for member in data.members if member.type == "column"]
    rafter_length = sum(float(member.length) for member in rafter_members)
    column_length = sum(float(member.length) for member in column_members)
    steel_mass = rafter_length * float(rafter["m"]) + column_length * float(column["m"])
    mass_breakdown = _build_steel_mass_breakdown(
        data, member_db, steel_mass, dict(bracing_design or {})
    )

    governing_member = max(
        member_results,
        key=lambda item: item.governing_ratio if math.isfinite(item.governing_ratio) else math.inf,
    )
    governing_dx = max(deflections, key=lambda item: abs(item["max_dx"]), default=None)
    governing_dy = max(deflections, key=lambda item: abs(item["max_dy"]), default=None)
    governing_fx = max(reactions, key=lambda item: abs(item.fx), default=None)
    governing_fy = max(reactions, key=lambda item: abs(item.fy), default=None)

    return {
        "node_count": len(data.nodes),
        "member_count": len(data.members),
        "column_count": len(column_members),
        "rafter_count": len(rafter_members),
        "column_length_m": column_length,
        "rafter_length_m": rafter_length,
        "estimated_frame_steel_mass_kg": steel_mass,
        "steel_mass_breakdown": mass_breakdown,
        "roof_pitch_deg": float(frame_data.get("roof_pitch", 0.0)),
        "support_count": len(data.supports),
        "uls_combination_count": len(data.load_combinations),
        "sls_combination_count": len(data.serviceability_load_combinations),
        "governing_member": governing_member.member,
        "governing_member_type": governing_member.member_type,
        "governing_section": governing_member.section,
        "governing_combination": governing_member.load_combination,
        "governing_check": governing_member.governing_check,
        "governing_utilisation": governing_member.governing_ratio,
        "overall_status": governing_member.status,
        "max_horizontal_deflection_mm": governing_dx["max_dx"] if governing_dx else 0.0,
        "horizontal_deflection_ratio": governing_dx.get("horizontal_ratio") if governing_dx else None,
        "horizontal_deflection_node": governing_dx["dx_node"] if governing_dx else "",
        "horizontal_deflection_combination": governing_dx["load_combination"] if governing_dx else "",
        "max_vertical_deflection_mm": governing_dy["max_dy"] if governing_dy else 0.0,
        "vertical_deflection_ratio": governing_dy.get("vertical_ratio") if governing_dy else None,
        "vertical_deflection_node": governing_dy["dy_node"] if governing_dy else "",
        "vertical_deflection_combination": governing_dy["load_combination"] if governing_dy else "",
        "max_abs_horizontal_reaction_kN": abs(governing_fx.fx) if governing_fx else 0.0,
        "horizontal_reaction_node": governing_fx.node if governing_fx else "",
        "horizontal_reaction_combination": governing_fx.load_combination if governing_fx else "",
        "max_abs_vertical_reaction_kN": abs(governing_fy.fy) if governing_fy else 0.0,
        "vertical_reaction_node": governing_fy.node if governing_fy else "",
        "vertical_reaction_combination": governing_fy.load_combination if governing_fy else "",
    }


def _build_steel_mass_breakdown(data, member_db, portal_mass_per_frame, bracing):
    """Return the estimated whole-building primary/secondary steel mass."""

    from bracing_design import load_bracing_database

    frame = data.frame_data[0]
    length_m = float(frame.get("building_length", 0.0)) / 1000
    spacing_m = float(frame.get("rafter_spacing", 0.0)) / 1000
    if length_m <= 0 or spacing_m <= 0:
        raise ValueError("building_length and rafter_spacing must be positive for steel quantities.")
    bay_count = max(1, math.ceil(length_m / spacing_m - 1e-9))
    frame_count = bay_count + 1
    portal_mass = portal_mass_per_frame * frame_count

    auxiliary = load_bracing_database()

    def auxiliary_mass(family, designation):
        row = next(
            (item for item in auxiliary.get(family, []) if item.get("Designation") == designation),
            None,
        )
        if row is None:
            raise ValueError(f"Mass data was not found for {family} {designation}.")
        return float(row["m"])

    gable_mass_one_end = 0.0
    for item in bracing.get("gable_columns", []):
        props = mdb.member_properties(item["section_type"], item["section"], member_db)
        gable_mass_one_end += float(item["height_mm"]) / 1000 * float(props["m"])
    gable_end_count = 2 if bracing.get("gable_columns") else 0
    gable_mass = gable_mass_one_end * gable_end_count

    braced_bay_count = min(2, bay_count) if bracing else 0
    roof_bracing_mass = 0.0
    side_bracing_mass = 0.0
    bracing_by_type = {
        item["member_type"]: item for item in bracing.get("bracing_members", [])
    }
    roof_brace = bracing_by_type.get("Roof X-brace")
    roof_points = bracing.get("roof_layout", {}).get("roof_points", [])
    if roof_brace and len(roof_points) >= 2:
        angle_mass = auxiliary_mass(roof_brace["section_family"], roof_brace["section"])
        panels = bracing.get("roof_layout", {}).get("brace_panels", [])
        if not panels:  # Backward compatibility for older snapshots.
            panels = [
                {"start_index": index, "end_index": index + 1}
                for index in range(len(roof_points) - 1)
            ]
        diagonal_length_one_bay_m = 2 * sum(
            math.hypot(
                spacing_m,
                math.hypot(
                    float(roof_points[item["end_index"]]["x_mm"]) - float(roof_points[item["start_index"]]["x_mm"]),
                    float(roof_points[item["end_index"]]["y_mm"]) - float(roof_points[item["start_index"]]["y_mm"]),
                ) / 1000,
            )
            for item in panels
        )
        roof_bracing_mass = diagonal_length_one_bay_m * braced_bay_count * angle_mass

    side_brace = bracing_by_type.get("Longitudinal side-wall brace")
    if side_brace:
        side_section_mass = auxiliary_mass(side_brace["section_family"], side_brace["section"])
        members_per_wall = int(
            bracing.get("column_bracing_layout", {}).get("members_per_wall", 1)
        )
        # The selected topology is repeated on both long walls in every end bay.
        side_bracing_mass = (
            float(side_brace["length_mm"]) / 1000
            * members_per_wall * 2 * braced_bay_count * side_section_mass
        )
    bracing_mass = roof_bracing_mass + side_bracing_mass

    purlin_section = bracing.get("pynite_roof_model", {}).get("stiffness_purlin_section")
    lipped = auxiliary.get("Lipped Channels", [])
    if not purlin_section:
        if not lipped:
            raise ValueError("No lipped-channel purlins are available for the quantity estimate.")
        purlin_section = lipped[0]["Designation"]
    purlin_mass_per_m = auxiliary_mass("Lipped Channels", purlin_section)
    purlin_line_count = len(bracing.get("roof_layout", {}).get("roof_points", []))
    if not purlin_line_count:
        rafter_nodes = {
            node_name
            for member in data.members if member.type == "rafter"
            for node_name in (member.i_node, member.j_node)
        }
        purlin_line_count = len(rafter_nodes)
    purlin_mass = purlin_line_count * length_m * purlin_mass_per_m

    total = portal_mass + bracing_mass + gable_mass + purlin_mass
    return {
        "portal_frames": {
            "quantity": frame_count,
            "mass_per_frame_kg": portal_mass_per_frame,
            "mass_kg": portal_mass,
        },
        "bracing": {
            "braced_bay_count": braced_bay_count,
            "roof_bracing_mass_kg": roof_bracing_mass,
            "side_bracing_mass_kg": side_bracing_mass,
            "mass_kg": bracing_mass,
        },
        "gable_columns": {
            "gable_end_count": gable_end_count,
            "mass_per_end_kg": gable_mass_one_end,
            "mass_kg": gable_mass,
        },
        "purlins": {
            "section": purlin_section,
            "line_count": purlin_line_count,
            "total_length_m": purlin_line_count * length_m,
            "mass_kg": purlin_mass,
            "design_status": "Provisional - compression resistance check deferred",
        },
        "total_steel_mass_kg": total,
        "exclusions": [
            "Girts, connections, base plates, cleats, bolts, welds and fabrication allowances.",
        ],
    }


def select_reaction_results(results, scope, load_combination=None):
    if scope is ReportScope.FULL:
        return list(results)
    if scope is ReportScope.LOAD_COMBINATION:
        return [r for r in results if r.load_combination == load_combination]

    # Keep every combination that governs at least one reported reaction
    # component at a support. This retains traceability without printing every row.
    selected = []
    by_node = {}
    for result in results:
        by_node.setdefault(result.node, []).append(result)
    for node_results in by_node.values():
        governing_names = set()
        for component in ("fx", "fy", "fz", "mx", "my", "mz"):
            governing = max(node_results, key=lambda row: abs(getattr(row, component)))
            governing_names.add(governing.load_combination)
        selected.extend(
            row for row in node_results if row.load_combination in governing_names
        )
    return selected


def build_calculation_sheet_data_from_frame(
    frame,
    data,
    member_db,
    actions_by_combination,
    rafter_section_type,
    column_section_type,
    rafter_section,
    column_section,
    bracing_design=None,
    input_path="input_data.json",
    project_metadata=None,
):
    """Build the complete stored result set from one finished FE analysis."""

    input_path = Path(input_path)
    all_members = collect_member_calculations(
        actions_by_combination,
        member_db,
        rafter_section_type,
        column_section_type,
        data.steel_grade[0],
    )
    combo_names = [item["name"] for item in data.load_combinations]
    reactions = collect_reactions(frame, combo_names, data.supports.keys())
    frame_data = dict(data.frame_data[0])
    wind_data = dict(data.wind_data[0]) if data.wind_data else {}
    internal_pressure = dict(wind_data.get("internal_pressure", {}))
    cpi_directions = internal_pressure.get("directions", {})
    deflections = collect_deflections(
        frame,
        data.serviceability_load_combinations,
        horizontal_reference_mm=frame_data.get("eaves_height", 0.0),
        vertical_reference_mm=frame_data.get("gable_width", 0.0),
    )
    frame_summary = build_frame_summary(
        data, member_db, rafter_section_type, column_section_type,
        rafter_section, column_section, all_members, reactions, deflections,
        bracing_design,
    )
    project = {
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "input_file": str(input_path.resolve()),
        "building_type": frame_data.get("building_type", ""),
        "roof_type": frame_data.get("building_roof", ""),
        "roof_accessibility": frame_data.get("roof_accessibility", ""),
        "load_combination_standard": frame_data.get("load_combination_standard", ""),
        "wind_design_mode": internal_pressure.get(
            "mode", frame_data.get("wind_design_mode", "Prelim")
        ),
        "wall_openings_m2": internal_pressure.get("opening_areas_m2", "Not required"),
        "cpi_0deg_envelope": (
            cpi_directions.get("0", {}).get("maximum_cpi", 0.2),
            cpi_directions.get("0", {}).get("minimum_cpi", -0.3),
        ),
        "cpi_90deg_envelope": (
            cpi_directions.get("90", {}).get("maximum_cpi", 0.2),
            cpi_directions.get("90", {}).get("minimum_cpi", -0.3),
        ),
        "steel_grade": frame_data.get("steel_grade", ""),
        "gable_width_mm": frame_data.get("gable_width", 0),
        "eaves_height_mm": frame_data.get("eaves_height", 0),
        "apex_height_mm": frame_data.get("apex_height", 0),
        "rafter_spacing_mm": frame_data.get("rafter_spacing", 0),
        "building_length_mm": frame_data.get("building_length", 0),
        "roof_pitch_deg": frame_data.get("roof_pitch", 0),
        "rafter_section": rafter_section,
        "column_section": column_section,
        "column_bracing_type": frame_data.get("column_bracing_type", "X"),
        "purlin_section": frame_data.get("purlin_section", ""),
        "purlin_max_spacing_mm": frame_data.get("purlin_max_spacing_mm", 0),
        "rafter_bracing_spacing": frame_data.get("rafter_bracing_spacing", 1),
        "roof_bracing_purlin_interval": frame_data.get("roof_bracing_purlin_interval", 1),
        "roof_bracing_purlin_intervals": frame_data.get("roof_bracing_purlin_intervals", []),
        "actual_purlin_spacing_mm": frame_data.get("actual_purlin_spacing_mm", 0),
        "girt_section": frame_data.get("girt_section", ""),
        "girt_max_spacing_mm": frame_data.get("girt_max_spacing_mm", 0),
    }
    if project_metadata:
        project.update(
            {
                "project_name": str(project_metadata.get("name", "")).strip(),
                "project_number": str(project_metadata.get("number", "")).strip(),
                "designer": str(project_metadata.get("designer", "")).strip(),
            }
        )
    assumptions = [
        "Two-dimensional transverse portal-frame analysis.",
        "Member self-weight is applied in load case D.",
        "Roof permanent actions are represented by D_MIN and D_MAX.",
        "Utilisation ratios are calculated using the existing strength_checks.py design model.",
        "SANS 10162-1:2011, including Amendment No. 1, is used for the reported steel resistance equations.",
        "The current in-plane effective-length factors are Kx = 1.2 for columns and Kx = 1.0 for rafters; Ky = 1.0 between modeled brace points.",
        "Tension resistance Tr = phi Ag fy is the gross-section yielding resistance. Net-section fracture and connection resistance require connection-specific inputs and are not checked here.",
        "For compression-bending checks, omega1 is reported and U1x is calculated explicitly in accordance with clause 13.8.",
        "For tension-bending, both clause 13.9 checks are retained. The additive Tu/Tr term prevents axial tension from reducing the governing utilisation.",
        "Results must be independently reviewed by the responsible competent engineer.",
    ]
    if internal_pressure.get("uniform_opening_distribution_assumed"):
        assumptions.append(
            "Wall openings are assumed uniformly distributed over each entered face when determining representative external pressure."
        )
    if internal_pressure.get("mode") == "Final design":
        assumptions.append("Roof opening area is assumed to be zero for the internal-pressure calculation.")
    assumptions.extend(
        f"Steel mass estimate excludes: {item}"
        for item in frame_summary.get("steel_mass_breakdown", {}).get("exclusions", [])
    )
    visualisation = build_analysis_visualisation(frame, data, all_members)
    return CalculationSheetData(
        title="Portal Frame Structural Calculation Sheet",
        scope=ReportScope.FULL,
        project=project,
        frame_summary=frame_summary,
        assumptions=assumptions,
        load_combinations=list(data.load_combinations),
        deflections=deflections,
        members=all_members,
        reactions=reactions,
        bracing_design=dict(bracing_design or {}),
        warnings=[
            "Tension-member net-section fracture and connection resistance are outside the current input model.",
        ],
        visualisation=visualisation,
    )


def load_calculation_sheet_data(
    snapshot_path="output/analysis/analysis_results.json",
    scope=ReportScope.CRITICAL,
    load_combination=None,
    allow_stale=False,
):
    """Load stored analysis results and select report rows without reanalysis."""

    scope = ReportScope(scope)
    snapshot_path = Path(snapshot_path)
    snapshot = load_analysis_snapshot(snapshot_path)
    input_status = validate_snapshot_input(snapshot, allow_stale=allow_stale)
    complete = calculation_sheet_from_dict(snapshot["results"])
    selected_members = select_member_results(
        complete.members, scope, load_combination
    )
    selected_reactions = select_reaction_results(
        complete.reactions, scope, load_combination
    )
    if scope is ReportScope.LOAD_COMBINATION and not selected_members:
        raise ValueError(f"Load combination {load_combination!r} was not found.")

    analysis = snapshot["analysis"]
    project = dict(complete.project)
    project.update({
        "analysis_id": analysis["analysis_id"],
        "analysis_created": analysis["created"],
        "analysis_snapshot": str(snapshot_path.resolve()),
        "input_sha256": analysis["input_sha256"],
        "input_status": input_status,
    })
    warnings = list(complete.warnings)
    if input_status == "missing":
        warnings.append(
            "The original input file is unavailable; this report uses the input "
            "embedded in the stored analysis snapshot."
        )
    elif input_status == "stale-allowed":
        warnings.append(
            "The current input file differs from the stored analysis; stale "
            "results were explicitly allowed for this report."
        )

    return replace(
        complete,
        scope=scope,
        project=project,
        members=selected_members,
        reactions=selected_reactions,
        warnings=warnings,
    )


def _fmt(value, digits=3):
    if value is None:
        return "-"
    if isinstance(value, (int, float)):
        return f"{value:,.{digits}f}"
    return escape(str(value))


def _deflection_display(value, ratio, reference_label):
    suffix = (
        f" ({reference_label}/{_fmt(ratio, 0)})"
        if ratio is not None
        else ""
    )
    return f"{_fmt(value)} mm{suffix}"


def _html_units(units):
    if not units:
        return ""
    value = escape(str(units))
    if value.startswith("10^"):
        value = "x " + value
    for exponent in ("2", "3", "4", "6", "9"):
        value = value.replace(f"^{exponent}", f"<sup>{exponent}</sup>")
    return value.replace("x ", "&times; ")


def _latex_group(text, start):
    if start >= len(text) or text[start] != "{":
        return None, start
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
    return None, start


def _replace_latex_group_command(text, command, replacer, groups=1):
    while command in text:
        start = text.find(command)
        cursor = start + len(command)
        values = []
        valid = True
        for _ in range(groups):
            value, cursor_next = _latex_group(text, cursor)
            if value is None:
                valid = False
                break
            values.append(value)
            cursor = cursor_next
        if not valid:
            break
        replacement = replacer(*(_latex_to_unicode(value) for value in values))
        text = text[:start] + replacement + text[cursor:]
    return text


def _latex_to_unicode(value):
    """Convert the report's limited LaTeX subset to clean linear math text."""
    text = str(value or "")
    text = _replace_latex_group_command(text, r"\frac", lambda a, b: f"({a})/({b})", 2)
    text = _replace_latex_group_command(text, r"\sqrt", lambda a: f"sqrt({a})")
    text = _replace_latex_group_command(text, r"\text", lambda a: a)
    text = text.replace(r"\left", "").replace(r"\right", "").replace(r"\,", " ")
    commands = {
        r"\alpha": "alpha", r"\beta": "beta", r"\phi": "phi",
        r"\kappa": "kappa", r"\lambda": "lambda", r"\omega": "omega",
        r"\pi": "pi", r"\max": "max", r"\min": "min",
    }
    for command, replacement in commands.items():
        text = text.replace(command, replacement)

    subscript = str.maketrans({
        "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
        "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
        "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
        "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ",
        "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ",
        "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ",
        "v": "ᵥ", "x": "ₓ", "y": "ᵧ",
    })
    superscript = str.maketrans({
        "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
        "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
        "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
        "i": "ⁱ", "n": "ⁿ",
    })

    def sub_value(match):
        raw = match.group(1) or match.group(2)
        translated = raw.translate(subscript)
        return translated if translated != raw else f"_{raw}"

    def super_value(match):
        raw = match.group(1) or match.group(2)
        translated = raw.translate(superscript)
        return translated if translated != raw else f"^({raw})"

    text = re.sub(r"_\{([^{}]+)\}|_([A-Za-z0-9])", sub_value, text)
    text = re.sub(r"\^\{([^{}]+)\}|\^(-?[A-Za-z0-9]+)", super_value, text)
    text = text.replace("alpha", "α").replace("beta", "β").replace("phi", "φ")
    text = text.replace("kappa", "κ").replace("lambda", "λ").replace("omega", "ω")
    text = text.replace("pi", "π").replace("sqrt", "√")
    return text.replace("{", "").replace("}", "")


def _html_value(item):
    if item.reference in {"CL-02", "CL-05", "CL-06"}:
        return f"Class {int(round(item.result))}"
    units = _html_units(item.units)
    return f"{_fmt(item.result)}{(' ' + units) if units else ''}"


def _html_formula(item):
    fallback_text = _latex_to_unicode(item.latex) if item.latex else item.equation
    fallback = f'<span class="math-fallback">{escape(fallback_text)}</span>'
    if not item.latex:
        return fallback
    latex = escape(item.latex)
    return f'<span class="math-tex">\\({latex}\\)</span>{fallback}'


def _html_table(headers, rows, classes=""):
    head = "".join(f"<th>{escape(str(item))}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{item}</td>" for item in row) + "</tr>"
        for row in rows
    )
    return f'<table class="{classes}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _building_layout_html(project, bracing):
    """Return annotated roof plan and typical transverse portal section SVGs."""

    span = max(float(project.get("gable_width_mm", 0)), 1.0)
    length = max(float(project.get("building_length_mm", 0)), 1.0)
    spacing = max(float(project.get("rafter_spacing_mm", 0)), 1.0)
    eaves = max(float(project.get("eaves_height_mm", 0)), 0.0)
    apex = max(float(project.get("apex_height_mm", 0)), eaves, 1.0)
    roof_type = str(project.get("roof_type", ""))
    column_section = escape(str(project.get("column_section", "")))
    rafter_section = escape(str(project.get("rafter_section", "")))
    members = {item["member_type"]: item for item in bracing.get("bracing_members", [])}
    roof_brace = escape(str(members.get("Roof X-brace", {}).get("section", "")))
    purlin = escape(str(bracing.get("pynite_roof_model", {}).get("stiffness_purlin_section", "")))

    px = lambda value: 70 + 560 * float(value) / length
    py = lambda value: 55 + 180 * float(value) / span
    frame_lines = []
    frame_count = max(1, int(round(length / spacing)))
    frame_positions = [min(index * spacing, length) for index in range(frame_count + 1)]
    if frame_positions[-1] < length - 1e-6:
        frame_positions.append(length)
    for grid_index, position in enumerate(frame_positions, 1):
        x = px(position)
        frame_lines.append(
            f'<line x1="{x:.1f}" y1="42" x2="{x:.1f}" y2="248" stroke="#8c98a4" stroke-dasharray="5 4"/>'
            f'<circle cx="{x:.1f}" cy="35" r="10" fill="#fff" stroke="#59636e"/>'
            f'<text x="{x:.1f}" y="39" text-anchor="middle">{grid_index}</text>'
        )
    brace_lines = []
    roof_layout = bracing.get("roof_layout", {})
    roof_points = roof_layout.get("roof_points", [])
    brace_panels = roof_layout.get("brace_panels", [])
    if len(frame_positions) >= 2:
        for left_pos, right_pos in (
            (frame_positions[0], frame_positions[1]),
            (frame_positions[-2], frame_positions[-1]),
        ):
            left, right = px(left_pos), px(right_pos)
            for panel in brace_panels:
                y_start = py(roof_points[panel["start_index"]]["x_mm"])
                y_end = py(roof_points[panel["end_index"]]["x_mm"])
                brace_lines.extend((
                    f'<line x1="{left:.1f}" y1="{y_start:.1f}" x2="{right:.1f}" y2="{y_end:.1f}" stroke="#174f78" stroke-width="3"/>',
                    f'<line x1="{left:.1f}" y1="{y_end:.1f}" x2="{right:.1f}" y2="{y_start:.1f}" stroke="#174f78" stroke-width="3"/>',
                ))
    transverse_grid_lines = []
    for grid_index, point in enumerate(roof_points):
        y = py(point["x_mm"])
        grid_label = chr(ord("A") + grid_index)
        transverse_grid_lines.append(
            f'<circle cx="52" cy="{y:.1f}" r="10" fill="#fff" stroke="#59636e"/>'
            f'<text x="52" y="{y + 4:.1f}" text-anchor="middle">{grid_label}</text>'
        )
    roof_plan = f"""
    <h3>Roof plan and bracing arrangement</h3>
    <svg class="layout" viewBox="0 0 700 320" role="img" aria-label="Dimensioned roof bracing plan">
      <rect x="70" y="55" width="560" height="180" fill="none" stroke="#17202a" stroke-width="2"/>
      {''.join(frame_lines)}{''.join(brace_lines)}{''.join(transverse_grid_lines)}
      <line x1="70" y1="265" x2="630" y2="265" stroke="#17202a"/><line x1="70" y1="258" x2="70" y2="272" stroke="#17202a"/><line x1="630" y1="258" x2="630" y2="272" stroke="#17202a"/>
      <text x="350" y="285" text-anchor="middle">Building length {_fmt(length, 0)} mm</text>
      <line x1="42" y1="55" x2="42" y2="235" stroke="#17202a"/><line x1="35" y1="55" x2="49" y2="55" stroke="#17202a"/><line x1="35" y1="235" x2="49" y2="235" stroke="#17202a"/>
      <text x="25" y="145" text-anchor="middle" transform="rotate(-90 25 145)">Span {_fmt(span, 0)} mm</text>
      <text x="350" y="18" text-anchor="middle">Typical portal spacing {_fmt(spacing, 0)} mm</text>
      <text x="350" y="305" text-anchor="middle">Roof X-bracing {roof_brace}: continuous eave-to-eave; each panel spans half a rafter slope; purlin/strut {purlin}</text>
    </svg>"""

    sx = lambda value: 80 + 540 * float(value) / span
    sy = lambda value: 270 - 215 * float(value) / apex
    if roof_type == "Mono Pitched":
        roof_points = f"80,{sy(eaves):.1f} 620,{sy(apex):.1f}"
        rafter_label_x = 440
    else:
        roof_points = f"80,{sy(eaves):.1f} 350,{sy(apex):.1f} 620,{sy(eaves):.1f}"
        rafter_label_x = 455
    portal_section = f"""
    <h3>Typical portal-frame section</h3>
    <svg class="layout" viewBox="0 0 700 340" role="img" aria-label="Dimensioned typical portal frame section">
      <line x1="80" y1="270" x2="80" y2="{sy(eaves):.1f}" stroke="#174f78" stroke-width="4"/>
      <line x1="620" y1="270" x2="620" y2="{sy(apex if roof_type == 'Mono Pitched' else eaves):.1f}" stroke="#174f78" stroke-width="4"/>
      <polyline points="{roof_points}" fill="none" stroke="#174f78" stroke-width="4"/>
      <line x1="65" y1="270" x2="635" y2="270" stroke="#17202a"/>
      <line x1="80" y1="35" x2="80" y2="290" stroke="#8c98a4" stroke-dasharray="5 4"/>
      <line x1="620" y1="35" x2="620" y2="290" stroke="#8c98a4" stroke-dasharray="5 4"/>
      <circle cx="80" cy="315" r="11" fill="#fff" stroke="#59636e"/><text x="80" y="319" text-anchor="middle">A</text>
      <circle cx="620" cy="315" r="11" fill="#fff" stroke="#59636e"/><text x="620" y="319" text-anchor="middle">B</text>
      <line x1="80" y1="300" x2="620" y2="300" stroke="#17202a"/><line x1="80" y1="293" x2="80" y2="307" stroke="#17202a"/><line x1="620" y1="293" x2="620" y2="307" stroke="#17202a"/>
      <text x="350" y="322" text-anchor="middle">Portal span {_fmt(span, 0)} mm (grid A-B)</text>
      <line x1="48" y1="270" x2="48" y2="{sy(eaves):.1f}" stroke="#17202a"/><line x1="41" y1="270" x2="55" y2="270" stroke="#17202a"/><line x1="41" y1="{sy(eaves):.1f}" x2="55" y2="{sy(eaves):.1f}" stroke="#17202a"/>
      <text x="30" y="{(270 + sy(eaves))/2:.1f}" text-anchor="middle" transform="rotate(-90 30 {(270 + sy(eaves))/2:.1f})">Eaves {_fmt(eaves, 0)} mm</text>
      <line x1="652" y1="270" x2="652" y2="{sy(apex):.1f}" stroke="#17202a"/><line x1="645" y1="270" x2="659" y2="270" stroke="#17202a"/><line x1="645" y1="{sy(apex):.1f}" x2="659" y2="{sy(apex):.1f}" stroke="#17202a"/>
      <text x="674" y="{(270 + sy(apex))/2:.1f}" text-anchor="middle" transform="rotate(-90 674 {(270 + sy(apex))/2:.1f})">Apex {_fmt(apex, 0)} mm</text>
      <text x="128" y="175" transform="rotate(-90 128 175)">Columns: {column_section}</text>
      <text x="{rafter_label_x}" y="80" text-anchor="middle">Rafters: {rafter_section}</text>
      <text x="350" y="25" text-anchor="middle">Roof pitch {_fmt(project.get('roof_pitch_deg', 0), 2)} degrees</text>
    </svg>"""
    return roof_plan + portal_section


def _bracing_html(bracing, project=None):
    if not bracing:
        return "<p>No gable/bracing design results were stored.</p>"
    columns = bracing.get("gable_columns", [])
    members = bracing.get("bracing_members", [])
    gable = bracing.get("gable_layout", {})
    roof = bracing.get("roof_layout", {})
    width = max(float(gable.get("width_mm", 1)), 1.0)
    apex = max(float(gable.get("apex_height_mm", 1)), 1.0)

    def gx(value):
        return 35 + 630 * float(value) / width

    def gy(value):
        return 270 - 235 * float(value) / apex

    eaves_y = gy(gable.get("eaves_height_mm", 0))
    apex_y = gy(gable.get("apex_height_mm", 0))
    gable_lines = [
        f'<polyline points="35,{eaves_y:.1f} 350,{apex_y:.1f} 665,{eaves_y:.1f}" fill="none" stroke="#174f78" stroke-width="3"/>',
        '<line x1="35" y1="270" x2="665" y2="270" stroke="#17202a"/>',
        '<line x1="35" y1="20" x2="35" y2="290" stroke="#8c98a4" stroke-dasharray="5 4"/>',
        '<line x1="665" y1="20" x2="665" y2="290" stroke="#8c98a4" stroke-dasharray="5 4"/>',
        '<circle cx="35" cy="292" r="10" fill="#fff" stroke="#59636e"/><text x="35" y="296" text-anchor="middle">A</text>',
        '<circle cx="665" cy="292" r="10" fill="#fff" stroke="#59636e"/><text x="665" y="296" text-anchor="middle">B</text>',
    ]
    columns_by_name = {item["name"]: item for item in columns}
    for item in gable.get("columns", []):
        x = gx(item["x_mm"])
        y = gy(item["height_mm"])
        result = columns_by_name.get(item["name"], {})
        gable_lines.append(
            f'<line x1="{x:.1f}" y1="270" x2="{x:.1f}" y2="{y:.1f}" stroke="#a21f2d" stroke-width="3"/>'
            f'<text x="{x + 14:.1f}" y="{(270 + y)/2:.1f}" transform="rotate(-90 {x + 14:.1f} {(270 + y)/2:.1f})" text-anchor="middle">{escape(str(item["name"]))}: {escape(str(result.get("section", "")))}</text>'
        )

    roof_points = roof.get("roof_points", [])
    loaded = set(roof.get("loaded_nodes", []))
    plan_lines = [
        '<line x1="35" y1="35" x2="665" y2="35" stroke="#17202a" stroke-width="2"/>',
        '<line x1="35" y1="185" x2="665" y2="185" stroke="#17202a" stroke-width="2"/>',
    ]
    xs = []
    for item in roof_points:
        x = gx(item["x_mm"])
        xs.append(x)
        plan_lines.append(f'<line x1="{x:.1f}" y1="35" x2="{x:.1f}" y2="185" stroke="#8c98a4"/>')
        if item["name"] in loaded:
            plan_lines.append(f'<circle cx="{x:.1f}" cy="35" r="5" fill="#a21f2d"/>')
    brace_panels = roof.get("brace_panels", [])
    if not brace_panels:
        brace_panels = [
            {"start_index": index, "end_index": index + 1}
            for index in range(len(xs) - 1)
        ]
    roof_section = escape(str(next(
        (item.get("section", "") for item in members if item["member_type"] == "Roof X-brace"),
        "",
    )))
    for panel in brace_panels:
        left, right = xs[panel["start_index"]], xs[panel["end_index"]]
        plan_lines.append(
            f'<line x1="{left:.1f}" y1="35" x2="{right:.1f}" y2="185" stroke="#174f78" stroke-width="2"/>'
            f'<line x1="{right:.1f}" y1="35" x2="{left:.1f}" y2="185" stroke="#174f78" stroke-width="2"/>'
            f'<text x="{(left + right)/2:.1f}" y="24" text-anchor="middle" fill="#a21f2d">{roof_section}</text>'
        )
    plan_lines.extend((
        '<text x="18" y="40" text-anchor="middle">1</text>',
        '<text x="18" y="190" text-anchor="middle">2</text>',
    ))
    plan_lines.extend(
        f'<text x="{x:.1f}" y="212" text-anchor="middle">{chr(ord("A") + index)}</text>'
        for index, x in enumerate(xs)
    )

    column_layout = bracing.get("column_bracing_layout", {})
    column_bracing_type = str(column_layout.get("type", "X"))
    side_member = next(
        (item for item in members if item["member_type"] == "Longitudinal side-wall brace"),
        {},
    )
    side_lines = [
        '<line x1="100" y1="45" x2="100" y2="245" stroke="#17202a" stroke-width="3"/>',
        '<line x1="600" y1="45" x2="600" y2="245" stroke="#17202a" stroke-width="3"/>',
    ]
    panel_count = max(1, int(column_layout.get("panel_count", 1)))
    panel_ys = [45 + 200 * index / panel_count for index in range(panel_count + 1)]
    side_lines.extend(
        f'<line x1="100" y1="{y:.1f}" x2="600" y2="{y:.1f}" stroke="#17202a" stroke-width="{2 if index in (0, panel_count) else 1}"/>'
        for index, y in enumerate(panel_ys)
    )
    brace_segments = []
    for top, bottom in zip(panel_ys, panel_ys[1:]):
        middle = (top + bottom) / 2
        if column_bracing_type == "A":
            brace_segments.extend(((100,bottom,350,top),(600,bottom,350,top)))
        elif column_bracing_type == "K":
            brace_segments.extend(((100,top,600,middle),(100,bottom,600,middle)))
        else:
            brace_segments.extend(((100,bottom,600,top),(100,top,600,bottom)))
    side_lines.extend(
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#a21f2d" stroke-width="4"/>'
        for x1, y1, x2, y2 in brace_segments
    )
    side_lines.append(
        f'<text x="350" y="280" text-anchor="middle">{escape(column_bracing_type)}-bracing: {escape(str(side_member.get("section", "")))}; {panel_count} panel(s) at {_fmt(column_layout.get("panel_height_mm", 0), 0)} mm; bay {_fmt(column_layout.get("bay_width_mm", 0), 0)} mm</text>'
    )
    side_lines.extend((
        '<circle cx="100" cy="270" r="10" fill="#fff" stroke="#59636e"/><text x="100" y="274" text-anchor="middle">1</text>',
        '<circle cx="600" cy="270" r="10" fill="#fff" stroke="#59636e"/><text x="600" y="274" text-anchor="middle">2</text>',
    ))

    column_rows = [(
        escape(item["name"]), escape(item["roof_node"]), escape(item["section"]),
        _fmt(item["tributary_width_mm"], 0), _fmt(item["top_shear_kn"]),
        _fmt(item["major_moment_knm"]), _fmt(item["mcr_knm"]),
        _fmt(item["bending_resistance_knm"]), _fmt(item["utilisation"]),
    ) for item in columns]
    gable_calculation_rows = []
    wind_factor = float(bracing.get("wind_uls_factor", 0))
    for item in columns:
        name = escape(item["name"])
        pressure = float(item.get("characteristic_pressure_kpa", 0))
        tributary_m = float(item.get("tributary_width_mm", 0)) / 1000
        height_m = float(item.get("height_mm", 0)) / 1000
        line_load = float(item.get("factored_line_load_kn_m", 0))
        moment = float(item.get("major_moment_knm", 0))
        shear = float(item.get("top_shear_kn", 0))
        unbraced_m = float(item.get("unbraced_length_mm", 0)) / 1000
        mi = (
            float(item.get("plastic_moment_knm", 0))
            if int(item.get("section_class", 4)) < 3
            else float(item.get("yield_moment_knm", 0))
        )
        gable_calculation_rows.extend((
            (name, "GC-01", "Factored line load", "wu = p btr gammaw", f"{_fmt(pressure)} x {_fmt(tributary_m, 3)} x {_fmt(wind_factor)}", f"{_fmt(line_load)} kN/m"),
            (name, "GC-02", "Pinned-column moment", "M* = wu L^2 / 8", f"{_fmt(line_load)} x {_fmt(height_m, 3)}^2 / 8", f"{_fmt(moment)} kNm"),
            (name, "GC-03", "Top shear", "V* = wu L / 2", f"{_fmt(line_load)} x {_fmt(height_m, 3)} / 2", f"{_fmt(shear)} kN"),
            (name, "GC-04", "Unbraced length", "Lu = L / n", f"{_fmt(height_m, 3)} / {int(item.get('brace_intervals', 1))}", f"{_fmt(unbraced_m, 3)} m"),
            (name, "GC-05", "Elastic critical moment", "Mcr = (omega2 pi/Lu) sqrt[EIyGJ + (pi E/Lu)^2 IyCw]", f"omega2={_fmt(item.get('omega2', 0))}; Iy={_fmt(item.get('iy_cm4', 0))}; J={_fmt(item.get('torsional_constant_cm4', 0))}; Cw={_fmt(item.get('warping_constant', 0))}", f"{_fmt(item.get('mcr_knm', 0))} kNm"),
            (name, "GC-06", "LTB bending resistance", "Mr = clause 13.6(Mcr, Mi)", f"Mcr={_fmt(item.get('mcr_knm', 0))}; Mi={_fmt(mi)}", f"{_fmt(item.get('bending_resistance_knm', 0))} kNm"),
            (name, "GC-07", "Utilisation", "U = M* / Mr", f"{_fmt(moment)} / {_fmt(item.get('bending_resistance_knm', 0))}", _fmt(item.get("utilisation", 0))),
        ))
    member_rows = [(
        escape(item["member_type"]), escape(item["section"]), escape(item["behaviour"]),
        _fmt(item["design_force_kn"]), _fmt(item["resistance_kn"]),
        _fmt(item.get("resistance_utilisation", item["utilisation"])),
        escape(str(item.get("slenderness_axis", "x-x"))),
        _fmt(item.get("slenderness_ratio", 0)), _fmt(item.get("slenderness_limit", 0)),
        _fmt(item.get("slenderness_utilisation", 0)), _fmt(item["utilisation"]),
    ) for item in members]
    calculation_rows = []
    total_shear = float(bracing.get("total_gable_top_shear_kn", 0))
    bay_length = float(roof.get("bay_length_mm", 0))
    for item in members:
        name = escape(item["member_type"])
        force_projection = (
            float(column_layout.get("horizontal_projection_mm", bay_length))
            if item["member_type"] == "Longitudinal side-wall brace" else bay_length
        )
        calculation_rows.append((
            name, "Brace force", "T* = (V*/2)(Ld/b)",
            f"({_fmt(total_shear)}/2)({_fmt(item.get('length_mm', 0), 1)}/{_fmt(force_projection, 1)})",
            f"{_fmt(item.get('design_force_kn', 0))} kN",
        ))
        length_mm = float(item.get("length_mm", 0))
        slenderness_limit = item.get("slenderness_limit", 0)
        if "Angles" in str(item.get("section_family", "")):
            for axis, factor, radius_key, ratio_key in (
                ("x-x", 1.0, "rx_mm", "slenderness_xx"),
                ("y-y", 1.0, "ry_mm", "slenderness_yy"),
                ("v-v", 0.5, "rv_mm", "slenderness_vv"),
            ):
                calculation_rows.append((
                    name, f"Slenderness {axis}", "K L / r",
                    f"{_fmt(factor, 1)} x {_fmt(length_mm, 1)} / {_fmt(item.get(radius_key, 0), 2)}",
                    f"{_fmt(item.get(ratio_key, 0))} &le; {_fmt(slenderness_limit, 0)}",
                ))
        else:
            factor = float(item.get("effective_length_factor", 1.0))
            calculation_rows.append((
                name, "Slenderness", "K L / r",
                f"{_fmt(factor, 1)} x {_fmt(length_mm, 1)} / {_fmt(item.get('radius_of_gyration_mm', 0), 2)}",
                f"{_fmt(item.get('slenderness_ratio', 0))} &le; {_fmt(slenderness_limit, 0)}",
            ))
        if item.get("behaviour") == "tension-only":
            equation = "Tr = &phi;Ag fy"
            substitution = f"0.9({_fmt(item.get('area_mm2', 0), 1)})({_fmt(item.get('fy_mpa', 0), 0)})/1000"
        else:
            equation = "Cr = &phi;Ag fy[1 + &lambda;^(2n)]^(-1/n)"
            substitution = (
                f"0.9({_fmt(item.get('area_mm2', 0), 1)})({_fmt(item.get('fy_mpa', 0), 0)})"
                f"[1 + {_fmt(item.get('nondimensional_slenderness', 0))}^(2x1.34)]^(-1/1.34)/1000"
            )
        calculation_rows.append((
            name, "Member resistance", equation, substitution,
            f"{_fmt(item.get('resistance_kn', 0))} kN",
        ))
    pressure_rows = [(
        escape(item["case"]), escape(item["zone"]), _fmt(item.get("cpi")),
        _fmt(item["pressure_kpa"]),
    ) for item in bracing.get("pressure_cases", [])]
    roof_model = bracing.get("pynite_roof_model", {})
    return f"""
    {_building_layout_html(project or {}, bracing) if project else ''}
    <p><b>Governing gable pressure:</b> {_fmt(bracing.get('governing_characteristic_pressure_kpa', 0))} kPa;
    <b>ULS factor:</b> {_fmt(bracing.get('wind_uls_factor', 0))};
    <b>total top shear:</b> {_fmt(bracing.get('total_gable_top_shear_kn', 0))} kN.</p>
    {_html_table(("Case", "Wall zone", "cpi", "|Pressure| (kPa)"), pressure_rows)}
    <h3>Gable-end elevation</h3><svg class="layout" viewBox="0 0 700 300" role="img" aria-label="Gable column layout">{''.join(gable_lines)}</svg>
    {_html_table(("Column", "Roof node", "Section", "Tributary width (mm)", "Top shear (kN)", "M (kNm)", "Mcr (kNm)", "Mr (kNm)", "Util."), column_rows)}
    <h3>Gable-column design calculations</h3>
    {_html_table(("Column", "Ref.", "Calculation", "Equation", "Substitution", "Result"), gable_calculation_rows, "details")}
    <h3>Roof-bracing plan - first braced bay</h3><svg class="layout" viewBox="0 0 700 220" role="img" aria-label="Roof X bracing layout">{''.join(plan_lines)}</svg>
    <p><b>Roof PyNite model:</b> {escape(str(roof_model.get('analysis', '')))};
    {int(roof_model.get('node_count', 0))} nodes, {int(roof_model.get('member_count', 0))} members,
    {int(roof_model.get('x_brace_count', 0))} tension-only X-braces. Purlin stiffness section
    {escape(str(roof_model.get('stiffness_purlin_section', '')))}; resistance check deferred.</p>
    <h3>Typical longitudinal column-bracing bay</h3><svg class="layout" viewBox="0 0 700 300" role="img" aria-label="Selected longitudinal column bracing layout">{''.join(side_lines)}</svg>
    <h3>Bracing design calculations</h3>
    <p>Brace force is calculated from <i>T* = (V*/2)(L<sub>d</sub>/b)</i>. Tension resistance is <i>T<sub>r</sub> = &phi;A<sub>g</sub>f<sub>y</sub></i>; the CHS compression resistance additionally uses the SANS column curve already implemented by the analysis.</p>
    {_html_table(("Member", "Check", "Equation", "Substitution", "Result"), calculation_rows)}
    {_html_table(("Member", "Section", "Behaviour", "Force (kN)", "Resistance (kN)", "Resistance util.", "Gov. axis", "Gov. KL/r", "Limit", "Slenderness util.", "Governing util."), member_rows)}
    <ul>{''.join(f'<li>{escape(item)}</li>' for item in bracing.get('assumptions', []))}</ul>
    """


def write_html_report(data, output_path):
    """Write a printable calculation sheet with MathJax equation enhancement."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    project_rows = [
        ("Project", escape(str(data.project.get("project_name", "")))),
        ("Project number", escape(str(data.project.get("project_number", "")))),
        ("Designer", escape(str(data.project.get("designer", "")))),
        ("Building", f"{escape(str(data.project['building_type']))} - {escape(str(data.project['roof_type']))}"),
        ("Geometry", f"Span {_fmt(data.project['gable_width_mm'], 0)} mm; eaves {_fmt(data.project['eaves_height_mm'], 0)} mm; apex {_fmt(data.project['apex_height_mm'], 0)} mm"),
        ("Frame spacing", f"{_fmt(data.project['rafter_spacing_mm'], 0)} mm"),
        ("Steel", escape(str(data.project["steel_grade"]))),
        ("Sections", f"Rafter {escape(str(data.project['rafter_section']))}; column {escape(str(data.project['column_section']))}"),
        ("Roof accessibility", escape(str(data.project["roof_accessibility"]))),
        ("Combinations", escape(str(data.project["load_combination_standard"]))),
        ("Wind design mode", escape(str(data.project.get("wind_design_mode", "Prelim")))),
        ("Wall openings", escape(str(data.project.get("wall_openings_m2", "Not required")))),
        ("cpi envelopes", escape(
            f"0 deg {data.project.get('cpi_0deg_envelope')}; 90 deg {data.project.get('cpi_90deg_envelope')}"
        )),
        ("Report scope", escape(data.scope.value.replace("_", " ").title())),
        ("Analysis ID", escape(str(data.project.get("analysis_id", "")))),
        ("Analysis completed", escape(str(data.project.get("analysis_created", "")))),
        ("Input verification", escape(str(data.project.get("input_status", "")))),
        ("Input SHA-256", escape(str(data.project.get("input_sha256", "")))),
    ]
    summary = data.frame_summary
    mass = summary.get("steel_mass_breakdown", {})
    portal_mass = mass.get("portal_frames", {})
    bracing_mass = mass.get("bracing", {})
    gable_mass = mass.get("gable_columns", {})
    purlin_mass = mass.get("purlins", {})
    frame_rows = [
        ("Analysis model", f"{summary['node_count']} nodes; {summary['member_count']} members "
         f"({summary['column_count']} columns, {summary['rafter_count']} rafters); "
         f"{summary['support_count']} supports"),
        ("Member lengths", f"Columns {_fmt(summary['column_length_m'])} m; "
         f"rafters {_fmt(summary['rafter_length_m'])} m"),
        ("Portal frames", f"{_fmt(portal_mass.get('mass_kg', summary['estimated_frame_steel_mass_kg']), 1)} kg "
         f"({int(portal_mass.get('quantity', 1))} frames at "
         f"{_fmt(portal_mass.get('mass_per_frame_kg', summary['estimated_frame_steel_mass_kg']), 1)} kg/frame)"),
        ("Bracing", f"{_fmt(bracing_mass.get('mass_kg', 0), 1)} kg "
         f"(roof {_fmt(bracing_mass.get('roof_bracing_mass_kg', 0), 1)} kg; "
         f"side walls {_fmt(bracing_mass.get('side_bracing_mass_kg', 0), 1)} kg)"),
        ("Gable columns", f"{_fmt(gable_mass.get('mass_kg', 0), 1)} kg "
         f"for {int(gable_mass.get('gable_end_count', 0))} gable ends"),
        ("Purlins", f"{_fmt(purlin_mass.get('mass_kg', 0), 1)} kg; "
         f"{int(purlin_mass.get('line_count', 0))} lines, "
         f"{_fmt(purlin_mass.get('total_length_m', 0), 1)} m total; "
         f"{escape(str(purlin_mass.get('section', '')))} (provisional)"),
        ("Total estimated steel mass", f"{_fmt(mass.get('total_steel_mass_kg', summary['estimated_frame_steel_mass_kg']), 1)} kg"),
        ("Roof pitch", f"{_fmt(summary['roof_pitch_deg'], 2)} degrees"),
        ("Analysed combinations", f"{summary['uls_combination_count']} ULS; {summary['sls_combination_count']} SLS"),
        ("Governing member strength", f"{escape(summary['governing_member'])} ({escape(summary['governing_member_type'])}, "
         f"{escape(summary['governing_section'])}) - {escape(summary['governing_combination'])}; "
         f"{escape(summary['governing_check'])} = {_fmt(summary['governing_utilisation'])} "
         f"[{escape(summary['overall_status'])}]"),
        ("Maximum horizontal deflection", f"{_deflection_display(summary['max_horizontal_deflection_mm'], summary.get('horizontal_deflection_ratio'), 'Eaves')} at "
         f"{escape(summary['horizontal_deflection_node'])} - {escape(summary['horizontal_deflection_combination'])}"),
        ("Maximum vertical deflection", f"{_deflection_display(summary['max_vertical_deflection_mm'], summary.get('vertical_deflection_ratio'), 'Span')} at "
         f"{escape(summary['vertical_deflection_node'])} - {escape(summary['vertical_deflection_combination'])}"),
        ("Maximum absolute horizontal reaction", f"{_fmt(summary['max_abs_horizontal_reaction_kN'])} kN at "
         f"{escape(summary['horizontal_reaction_node'])} - {escape(summary['horizontal_reaction_combination'])}"),
        ("Maximum absolute vertical reaction", f"{_fmt(summary['max_abs_vertical_reaction_kN'])} kN at "
         f"{escape(summary['vertical_reaction_node'])} - {escape(summary['vertical_reaction_combination'])}"),
    ]
    combination_rows = [
        (escape(item["name"]), escape(", ".join(f"{k}={v:g}" for k, v in item["factors"].items())))
        for item in data.load_combinations
    ]
    deflection_rows = [
        (
            escape(item["load_combination"]),
            _deflection_display(item["max_dx"], item.get("horizontal_ratio"), "Eaves"),
            escape(item["dx_node"]),
            _deflection_display(item["max_dy"], item.get("vertical_ratio"), "Span"),
            escape(item["dy_node"]),
        )
        for item in data.deflections
    ]
    reaction_rows = [
        (
            escape(item.node), escape(item.load_combination), _fmt(item.fx), _fmt(item.fy),
            _fmt(item.fz), _fmt(item.mx), _fmt(item.my), _fmt(item.mz),
        )
        for item in data.reactions
    ]
    member_sections = []
    for index, member in enumerate(data.members, start=1):
        inputs = _html_table(
            ("Ref.", "Input", "Value"),
            [
                (
                    escape(f"{member.member}-{item.reference}"), escape(item.title),
                    _html_value(item),
                )
                for item in member.inputs
            ],
            "details",
        )
        classification = _html_table(
            ("Ref.", "Classification check", "Equation", "Substitution", "Result"),
            [
                (
                    escape(f"{member.member}-{item.reference}"), escape(item.title),
                    _html_formula(item), f"<code>{escape(item.substitution)}</code>",
                    _html_value(item),
                )
                for item in member.classification
            ],
            "details",
        )
        parameters = _html_table(
            ("Ref.", "Design parameter", "Equation", "Substitution / basis", "Result"),
            [
                (
                    escape(f"{member.member}-{item.reference}"), escape(item.title),
                    _html_formula(item), f"<code>{escape(item.substitution)}</code>",
                    _html_value(item),
                )
                for item in member.parameters
            ],
            "details",
        )
        resistances = _html_table(
            ("Ref.", "Resistance", "Equation", "Substitution", "Result"),
            [
                (
                    escape(f"{member.member}-{item.reference}"), escape(item.title),
                    _html_formula(item),
                    f"<code>{escape(item.substitution)}</code>", _html_value(item),
                )
                for item in member.resistances
            ],
            "details",
        )
        checks = _html_table(
            ("Ref.", "Check", "Equation", "Substitution", "Ratio", "Limit", "Status"),
            [
                (
                    escape(f"{member.member}-{item.reference}"), escape(item.title),
                    _html_formula(item),
                    f"<code>{escape(item.substitution)}</code>", _fmt(item.result),
                    _fmt(item.limit), f'<span class="status {item.status.lower()}">{item.status}</span>',
                )
                for item in member.calculations
            ],
            "checks",
        )
        member_sections.append(f"""
        <section class="member">
          <h3>{index}. {escape(member.member)} - {escape(member.member_type.title())}</h3>
          <div class="member-meta">
            <span><b>Section:</b> {escape(member.section)}</span>
            <span><b>Combination:</b> {escape(member.load_combination)}</span>
            <span><b>Axial action:</b> {escape(member.axial_action)} ({_fmt(member.axial_force)} kN signed)</span>
            <span><b>Class:</b> {member.section_class}</span>
            <span><b>Mx:</b> {_fmt(member.major_moment)} kNm</span>
            <span><b>Governing:</b> {escape(member.governing_check)} = {_fmt(member.governing_ratio)}</span>
          </div>
          <h4>Design inputs</h4>
          {inputs}
          <h4>Section classification</h4>
          {classification}
          <h4>Effective lengths and moment factors</h4>
          {parameters}
          <h4>Resistance calculations</h4>
          {resistances}
          <h4>Utilisation checks</h4>
          {checks}
        </section>""")

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(data.title)}</title>
<script>
window.MathJax = {{
  tex: {{ inlineMath: [['\\\\(', '\\\\)']] }},
  startup: {{
    ready: () => {{
      MathJax.startup.defaultReady();
      MathJax.startup.promise.then(() => document.documentElement.classList.add('mathjax-ready'));
    }}
  }}
}};
</script>
<script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
<style>
@page {{ size: A4; margin: 16mm 13mm 16mm; }}
:root {{ --ink:#17202a; --muted:#59636e; --line:#cbd2d9; --soft:#f3f6f8; --accent:#174f78; --pass:#176b3a; --fail:#a21f2d; }}
* {{ box-sizing:border-box; }}
body {{ margin:0 auto; max-width:1100px; color:var(--ink); font:13px/1.42 Arial, Helvetica, sans-serif; background:#fff; }}
.report-toolbar {{ position:sticky; top:0; z-index:5; display:flex; justify-content:flex-end; padding:10px 0; background:rgba(255,255,255,.96); border-bottom:1px solid var(--line); }}
.report-toolbar button {{ border:0; border-radius:8px; padding:9px 14px; color:#fff; background:var(--accent); font:600 13px Arial,Helvetica,sans-serif; cursor:pointer; }}
header {{ border-bottom:3px solid var(--accent); padding:18px 0 12px; margin-bottom:18px; }}
h1 {{ font-size:25px; margin:0 0 4px; color:var(--accent); }}
h2 {{ font-size:18px; color:var(--accent); margin:24px 0 8px; border-bottom:1px solid var(--line); padding-bottom:4px; }}
h3 {{ font-size:15px; margin:0 0 8px; }}
h4 {{ font-size:12px; color:var(--accent); margin:10px 0 4px; }}
.subtitle,.footer-note {{ color:var(--muted); }}
table {{ width:100%; border-collapse:collapse; margin:7px 0 14px; page-break-inside:auto; }}
tr {{ page-break-inside:avoid; }}
th {{ background:var(--accent); color:#fff; font-weight:600; text-align:left; }}
th,td {{ border:1px solid var(--line); padding:5px 6px; vertical-align:top; }}
tbody tr:nth-child(even) {{ background:var(--soft); }}
.summary td:first-child {{ width:24%; font-weight:600; }}
.member {{ margin:14px 0 20px; }}
.member-meta {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:5px 14px; background:var(--soft); padding:8px; margin-bottom:8px; border-left:3px solid var(--accent); }}
.checks {{ font-size:11px; }}
.details {{ font-size:10.5px; }}
code {{ white-space:normal; font-family:Consolas, monospace; font-size:10.5px; }}
.math-tex {{ display:none; }}
.mathjax-ready .math-tex {{ display:inline; }}
.mathjax-ready .math-fallback {{ display:none; }}
.math-fallback {{ font-family:"Cambria Math", "Times New Roman", serif; font-size:12px; }}
.status {{ font-weight:bold; }} .pass {{ color:var(--pass); }} .fail {{ color:var(--fail); }}
.layout {{ width:100%; max-height:330px; border:1px solid var(--line); background:#fff; margin:6px 0 14px; }}
ul {{ margin-top:6px; }}
footer {{ margin-top:28px; border-top:1px solid var(--line); padding-top:8px; color:var(--muted); font-size:11px; }}
@media print {{ body {{ max-width:none; }} .report-toolbar {{ display:none; }} header {{ padding-top:0; }} a {{ color:inherit; text-decoration:none; }} }}
@media (max-width:700px) {{ .member-meta {{ grid-template-columns:1fr; }} table {{ font-size:11px; }} }}
</style></head><body>
<div class="report-toolbar"><button type="button" onclick="window.print()">Print / save as PDF</button></div>
<header><h1>{escape(data.title)}</h1>
<div class="subtitle">Generated {escape(str(data.project['generated']))} from {escape(str(data.project['input_file']))}</div></header>
<h2>1. Project and design basis</h2>
{_html_table(("Item", "Value"), project_rows, "summary")}
<h2>2. Frame summary</h2>
{_html_table(("Item", "Value"), frame_rows, "summary")}
<h2>3. Basis and assumptions</h2><ul>{''.join(f'<li>{escape(item)}</li>' for item in data.assumptions)}</ul>
{('<p><b>Limitations:</b> ' + ' '.join(escape(item) for item in data.warnings) + '</p>') if data.warnings else ''}
<h2>4. Ultimate load combinations</h2>
{_html_table(("Combination", "Factors"), combination_rows)}
<h2>5. Serviceability results</h2>
{_html_table(("Combination", "Max dx (mm)", "Node", "Max dy (mm)", "Node"), deflection_rows)}
<h2>6. Support reactions</h2>
<p class="subtitle">Forces in kN; moments in kNm. Critical scope retains combinations governing at least one component.</p>
{_html_table(("Node", "Combination", "Fx", "Fy", "Fz", "Mx", "My", "Mz"), reaction_rows)}
<h2>7. Member design calculations</h2>
{''.join(member_sections)}
{('<h2>8. Gable columns and longitudinal bracing</h2>' + _bracing_html(data.bracing_design, data.project)) if data.bracing_design else ''}
<footer>This calculation sheet is generated from the current analysis implementation and is subject to independent engineering review.</footer>
</body></html>"""
    output_path.write_text(html, encoding="utf-8")
    return output_path


def write_json_data(data, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data.to_dict(), indent=2), encoding="utf-8")
    return output_path


def write_pdf_from_json(json_path, output_path):
    """Render saved calculation data to PDF with typeset mathematical equations."""

    try:
        from io import BytesIO

        from matplotlib.font_manager import FontProperties
        from matplotlib.mathtext import math_to_image
        import reportlab
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, String
        from reportlab.platypus import (
            BaseDocTemplate, Frame, PageTemplate, PageBreak, Paragraph,
            Image as ReportLabImage, KeepTogether, Spacer, Table, TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            "PDF output requires ReportLab 4.4.9 and Matplotlib. Install them with "
            "'python -m pip install -r requirements-pdf.txt'. The HTML report "
            "is dependency-free and can also be printed to PDF from a browser."
        ) from exc
    if getattr(reportlab, "Version", "") == "5.0.0":
        raise RuntimeError(
            "ReportLab 5.0.0 corrupts the equation tables in this report. "
            "Install the verified version with "
            "'python -m pip install -r requirements-pdf.txt'."
        )

    source = json.loads(Path(json_path).read_text(encoding="utf-8"))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    font_dir = Path(reportlab.__file__).parent / "fonts"
    math_font_candidates = (
        Path("C:/Windows/Fonts/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        font_dir / "Vera.ttf",
    )
    math_font = next(path for path in math_font_candidates if path.exists())
    pdfmetrics.registerFont(TTFont("CalcMath", str(math_font)))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CalcTitle", parent=styles["Title"], textColor=colors.HexColor("#174f78"), alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="CalcH2", parent=styles["Heading2"], textColor=colors.HexColor("#174f78"), spaceBefore=8, spaceAfter=5))
    styles.add(ParagraphStyle(name="CalcH4", parent=styles["Heading4"], textColor=colors.HexColor("#174f78"), fontSize=8.5, leading=10, spaceBefore=5, spaceAfter=3))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=7.5, leading=9))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["BodyText"], fontName="CalcMath", fontSize=6.1, leading=7.2))
    styles.add(ParagraphStyle(name="MathTiny", parent=styles["BodyText"], fontName="CalcMath", fontSize=7.0, leading=8.2, textColor=colors.HexColor("#142638")))
    styles.add(ParagraphStyle(name="SubTiny", parent=styles["BodyText"], fontName="CalcMath", fontSize=5.7, leading=6.8, textColor=colors.HexColor("#4d5964")))
    math_font_properties = FontProperties(family="DejaVu Sans", size=10)
    equation_buffers = []

    def pdf_units(units):
        if not units:
            return ""
        value = escape(str(units))
        if value.startswith("10^"):
            value = "&times; " + value
        for exponent in ("2", "3", "4", "6", "9"):
            value = value.replace(f"^{exponent}", f"<super>{exponent}</super>")
        return value

    def pdf_value(item):
        if item.get("reference") in {"CL-02", "CL-05", "CL-06"}:
            return Paragraph(f"Class {int(round(item['result']))}", styles["Tiny"])
        units = pdf_units(item.get("units", ""))
        value = f"{_fmt(item['result'])}{(' ' + units) if units else ''}"
        return Paragraph(value, styles["Tiny"])

    def pdf_formula(item):
        latex = item.get("latex")
        if not latex:
            return Paragraph(escape(item["equation"]), styles["MathTiny"])
        # Keep older stored snapshots visually compatible with the corrected
        # spacing now written by calculate_member_design().
        latex = latex.replace(r"m\max", r"m\,\max")

        # ReportLab paragraphs do not typeset LaTeX. Matplotlib's mathtext
        # renderer handles the limited equation set stored in the snapshot and
        # produces a sharp transparent image for the table cell.
        buffer = BytesIO()
        math_dpi = 300
        math_to_image(
            f"${latex}$",
            buffer,
            prop=math_font_properties,
            dpi=math_dpi,
            format="png",
            color="#142638",
        )
        buffer.seek(0)
        equation_buffers.append(buffer)  # Keep the stream alive until doc.build().
        image = ReportLabImage(buffer)
        max_width = 53 * mm
        max_height = 8 * mm
        natural_width = image.imageWidth * 72.0 / math_dpi
        natural_height = image.imageHeight * 72.0 / math_dpi
        scale = min(1.0, max_width / natural_width, max_height / natural_height)
        image.drawWidth = natural_width * scale
        image.drawHeight = natural_height * scale
        image.hAlign = "LEFT"
        return image

    def pdf_substitution(item):
        return Paragraph(escape(item["substitution"]), styles["SubTiny"])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#59636e"))
        canvas.drawString(14 * mm, 9 * mm, "Portal frame calculation sheet")
        canvas.drawRightString(A4[0] - 14 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(str(output_path), pagesize=A4, rightMargin=13*mm, leftMargin=13*mm, topMargin=14*mm, bottomMargin=15*mm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates(PageTemplate(id="calc", frames=frame, onPage=footer))
    story = [Paragraph(escape(source["title"]), styles["CalcTitle"]), Spacer(1, 5*mm)]
    project = source["project"]
    summary = [["Item", "Value"]] + [
        [key.replace("_", " ").title(), str(value)]
        for key, value in project.items()
        if key not in {"input_file", "analysis_snapshot"}
    ]
    table = Table(summary, colWidths=[50*mm, 120*mm], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story += [Paragraph("1. Project and design basis", styles["CalcH2"]), table]

    frame_summary = source["frame_summary"]
    mass = frame_summary.get("steel_mass_breakdown", {})
    portal_mass = mass.get("portal_frames", {})
    bracing_mass = mass.get("bracing", {})
    gable_mass = mass.get("gable_columns", {})
    purlin_mass = mass.get("purlins", {})
    frame_rows = [
        ["Analysis model", f"{frame_summary['node_count']} nodes; {frame_summary['member_count']} members "
         f"({frame_summary['column_count']} columns and {frame_summary['rafter_count']} rafters); "
         f"{frame_summary['support_count']} supports"],
        ["Member lengths", f"Columns {_fmt(frame_summary['column_length_m'])} m; rafters {_fmt(frame_summary['rafter_length_m'])} m"],
        ["Portal frames", f"{_fmt(portal_mass.get('mass_kg', frame_summary['estimated_frame_steel_mass_kg']), 1)} kg "
         f"({int(portal_mass.get('quantity', 1))} at {_fmt(portal_mass.get('mass_per_frame_kg', frame_summary['estimated_frame_steel_mass_kg']), 1)} kg/frame)"],
        ["Bracing", f"{_fmt(bracing_mass.get('mass_kg', 0), 1)} kg "
         f"(roof {_fmt(bracing_mass.get('roof_bracing_mass_kg', 0), 1)}; side {_fmt(bracing_mass.get('side_bracing_mass_kg', 0), 1)} kg)"],
        ["Gable columns", f"{_fmt(gable_mass.get('mass_kg', 0), 1)} kg for "
         f"{int(gable_mass.get('gable_end_count', 0))} ends"],
        ["Purlins", f"{_fmt(purlin_mass.get('mass_kg', 0), 1)} kg; "
         f"{int(purlin_mass.get('line_count', 0))} lines; {_fmt(purlin_mass.get('total_length_m', 0), 1)} m; "
         f"{purlin_mass.get('section', '')} (provisional)"],
        ["Total estimated steel mass", f"{_fmt(mass.get('total_steel_mass_kg', frame_summary['estimated_frame_steel_mass_kg']), 1)} kg"],
        ["Roof pitch", f"{_fmt(frame_summary['roof_pitch_deg'], 2)} degrees"],
        ["Analysed combinations", f"{frame_summary['uls_combination_count']} ULS; {frame_summary['sls_combination_count']} SLS"],
        ["Governing member strength", f"{frame_summary['governing_member']} ({frame_summary['governing_member_type']}, "
         f"{frame_summary['governing_section']}) - {frame_summary['governing_combination']}; "
         f"{frame_summary['governing_check']} = {_fmt(frame_summary['governing_utilisation'])} [{frame_summary['overall_status']}]"],
        ["Maximum horizontal deflection", f"{_deflection_display(frame_summary['max_horizontal_deflection_mm'], frame_summary.get('horizontal_deflection_ratio'), 'Eaves')} at "
         f"{frame_summary['horizontal_deflection_node']} - {frame_summary['horizontal_deflection_combination']}"],
        ["Maximum vertical deflection", f"{_deflection_display(frame_summary['max_vertical_deflection_mm'], frame_summary.get('vertical_deflection_ratio'), 'Span')} at "
         f"{frame_summary['vertical_deflection_node']} - {frame_summary['vertical_deflection_combination']}"],
        ["Maximum absolute horizontal reaction", f"{_fmt(frame_summary['max_abs_horizontal_reaction_kN'])} kN at "
         f"{frame_summary['horizontal_reaction_node']} - {frame_summary['horizontal_reaction_combination']}"],
        ["Maximum absolute vertical reaction", f"{_fmt(frame_summary['max_abs_vertical_reaction_kN'])} kN at "
         f"{frame_summary['vertical_reaction_node']} - {frame_summary['vertical_reaction_combination']}"],
    ]
    frame_table = Table([["Item", "Value"], *frame_rows], colWidths=[50*mm, 120*mm], repeatRows=1)
    frame_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),7.5),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story += [Paragraph("2. Frame summary", styles["CalcH2"]), frame_table]
    story += [Paragraph("3. Basis and assumptions", styles["CalcH2"])]
    story += [Paragraph(f"- {escape(item)}", styles["BodyText"]) for item in source["assumptions"]]
    if source.get("warnings"):
        story += [Paragraph("Limitations", styles["CalcH4"])]
        story += [Paragraph(f"- {escape(item)}", styles["Small"]) for item in source["warnings"]]

    combo_rows = [["Combination", "Factors"]] + [[c["name"], ", ".join(f"{k}={v:g}" for k,v in c["factors"].items())] for c in source["load_combinations"]]
    combo_table = Table(combo_rows, colWidths=[100*mm,70*mm], repeatRows=1)
    combo_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),7)]))
    story += [Paragraph("4. Ultimate load combinations", styles["CalcH2"]), combo_table]

    deflection_rows = [["Combination", "Max dx", "Node", "Max dy", "Node"]] + [
        [
            row["load_combination"],
            _deflection_display(row["max_dx"], row.get("horizontal_ratio"), "Eaves"),
            row["dx_node"],
            _deflection_display(row["max_dy"], row.get("vertical_ratio"), "Span"),
            row["dy_node"],
        ]
        for row in source["deflections"]
    ]
    deflection_table = Table(
        deflection_rows,
        colWidths=[92*mm, 22*mm, 16*mm, 22*mm, 16*mm],
        repeatRows=1,
    )
    deflection_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),6.5)]))
    story += [Paragraph("5. Serviceability results", styles["CalcH2"]), deflection_table]

    reaction_rows = [["Node","Combination","Fx","Fy","Fz","Mx","My","Mz"]] + [[r["node"],r["load_combination"],*[_fmt(r[k]) for k in ("fx","fy","fz","mx","my","mz")]] for r in source["reactions"]]
    reaction_table = Table(reaction_rows, colWidths=[13*mm,66*mm]+[15*mm]*6, repeatRows=1)
    reaction_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),6.5)]))
    story += [Paragraph("6. Support reactions", styles["CalcH2"]), reaction_table, PageBreak()]

    story += [Paragraph("7. Member design calculations", styles["CalcH2"])]
    for member_index, member in enumerate(source["members"]):
        if member_index:
            story += [PageBreak()]
        story += [Paragraph(f"{escape(member['member'])} - {escape(member['member_type'].title())}", styles["Heading3"])]
        story += [Paragraph(
            f"Section {escape(member['section'])}; combination {escape(member['load_combination'])}; "
            f"axial action {escape(member['axial_action'])} ({_fmt(member['axial_force'])} kN signed); "
            f"Mx {_fmt(member['major_moment'])} kNm; class {member['section_class']}; "
            f"governing {escape(member['governing_check'])} = {_fmt(member['governing_ratio'])} [{escape(member['status'])}]",
            styles["Small"],
        )]

        story += [Paragraph("Design inputs", styles["CalcH4"])]
        input_rows = [["Ref.", "Input", "Value"]]
        for item in member["inputs"]:
            input_rows.append([
                Paragraph(escape(f"{member['member']}-{item['reference']}"), styles["Tiny"]),
                Paragraph(escape(item["title"]), styles["Tiny"]),
                pdf_value(item),
            ])
        input_table = Table(input_rows, colWidths=[24*mm, 104*mm, 44*mm], repeatRows=1)
        input_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),6.1),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story += [input_table]

        story += [Paragraph("Section classification", styles["CalcH4"])]
        class_rows = [["Ref.", "Check", "Equation", "Substitution", "Result"]]
        for item in member["classification"]:
            class_rows.append([
                Paragraph(escape(f"{member['member']}-{item['reference']}"), styles["Tiny"]),
                Paragraph(escape(item["title"]), styles["Tiny"]),
                pdf_formula(item), pdf_substitution(item), pdf_value(item),
            ])
        class_table = Table(class_rows, colWidths=[20*mm, 40*mm, 55*mm, 46*mm, 21*mm], repeatRows=1)
        class_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),6.0),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story += [class_table]

        story += [Paragraph("Effective lengths and moment factors", styles["CalcH4"])]
        parameter_rows = [["Ref.", "Parameter", "Equation", "Substitution / basis", "Result"]]
        for item in member["parameters"]:
            parameter_rows.append([
                Paragraph(escape(f"{member['member']}-{item['reference']}"), styles["Tiny"]),
                Paragraph(escape(item["title"]), styles["Tiny"]),
                pdf_formula(item), pdf_substitution(item), pdf_value(item),
            ])
        parameter_table = Table(parameter_rows, colWidths=[20*mm, 40*mm, 55*mm, 46*mm, 21*mm], repeatRows=1)
        parameter_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),6.0),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story += [parameter_table]

        story += [Paragraph("Resistance calculations", styles["CalcH4"])]
        resistance_rows = [["Ref.", "Resistance", "Equation", "Substitution", "Result"]]
        for item in member["resistances"]:
            resistance_rows.append([
                Paragraph(escape(f"{member['member']}-{item['reference']}"), styles["Tiny"]),
                Paragraph(escape(item["title"]), styles["Tiny"]),
                pdf_formula(item), pdf_substitution(item), pdf_value(item),
            ])
        resistance_table = Table(resistance_rows, colWidths=[20*mm, 40*mm, 55*mm, 46*mm, 21*mm], repeatRows=1)
        resistance_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),6.1),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story += [resistance_table]

        rows = [["Ref.","Check","Equation","Substitution","Ratio","Status"]]
        for item in member["calculations"]:
            rows.append([
                Paragraph(escape(f"{member['member']}-{item['reference']}"), styles["Tiny"]),
                Paragraph(escape(item["title"]), styles["Tiny"]),
                pdf_formula(item), pdf_substitution(item),
                _fmt(item["result"]), item["status"],
            ])
        table = Table(rows, colWidths=[18*mm,38*mm,55*mm,43*mm,14*mm,14*mm], repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),6.5),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story += [KeepTogether([Paragraph("Utilisation checks", styles["CalcH4"]), table]), Spacer(1, 5*mm)]

    bracing = source.get("bracing_design", {})
    if bracing:
        story += [PageBreak(), Paragraph("8. Gable columns and longitudinal bracing", styles["CalcH2"])]
        project = source.get("project", {})
        building_length = max(float(project.get("building_length_mm", 0)), 1)
        building_span = max(float(project.get("gable_width_mm", 0)), 1)
        portal_spacing = max(float(project.get("rafter_spacing_mm", 0)), 1)
        story += [Paragraph("Roof plan and bracing arrangement", styles["CalcH4"])]
        roof_plan = Drawing(170*mm, 72*mm)
        plan_x = lambda value: 12*mm + 146*mm*float(value)/building_length
        plan_y0, plan_y1 = 14*mm, 58*mm
        roof_plan.add(Line(plan_x(0),plan_y0,plan_x(building_length),plan_y0,strokeColor=colors.black,strokeWidth=1.2))
        roof_plan.add(Line(plan_x(0),plan_y1,plan_x(building_length),plan_y1,strokeColor=colors.black,strokeWidth=1.2))
        frame_count = max(1, int(round(building_length / portal_spacing)))
        frame_positions = [min(index * portal_spacing, building_length) for index in range(frame_count + 1)]
        if frame_positions[-1] < building_length - 1e-6:
            frame_positions.append(building_length)
        for grid_index, position in enumerate(frame_positions, 1):
            x = plan_x(position)
            roof_plan.add(Line(x,plan_y0-3*mm,x,plan_y1+3*mm,strokeColor=colors.HexColor("#8c98a4"),strokeDashArray=[2,2]))
            roof_plan.add(String(x-1.5*mm,plan_y1+4*mm,str(grid_index),fontSize=6))
        stored_roof = bracing.get("roof_layout", {})
        stored_points = stored_roof.get("roof_points", [])
        stored_panels = stored_roof.get("brace_panels", [])
        roof_y = lambda value: plan_y0 + (plan_y1-plan_y0)*float(value)/building_span
        if len(frame_positions) >= 2:
            for left_position, right_position in ((frame_positions[0],frame_positions[1]),(frame_positions[-2],frame_positions[-1])):
                left, right = plan_x(left_position), plan_x(right_position)
                for panel in stored_panels:
                    ya = roof_y(stored_points[panel["start_index"]]["x_mm"])
                    yb = roof_y(stored_points[panel["end_index"]]["x_mm"])
                    roof_plan.add(Line(left,ya,right,yb,strokeColor=colors.HexColor("#174f78"),strokeWidth=1.5))
                    roof_plan.add(Line(left,yb,right,ya,strokeColor=colors.HexColor("#174f78"),strokeWidth=1.5))
        for grid_index, point in enumerate(stored_points):
            roof_plan.add(String(5*mm,roof_y(point["x_mm"])-1*mm,chr(ord("A")+grid_index),fontSize=7))
        roof_plan.add(String(55*mm,63*mm,f"Portal spacing {_fmt(portal_spacing,0)} mm",fontSize=6.5))
        roof_plan.add(String(55*mm,4*mm,f"Length {_fmt(building_length,0)} mm; span {_fmt(building_span,0)} mm",fontSize=6.5))
        brace_by_type = {item["member_type"]: item for item in bracing.get("bracing_members", [])}
        roof_plan.add(String(31*mm,67*mm,f"Roof brace {brace_by_type.get('Roof X-brace',{}).get('section','')} continuous eave-eave; each panel half-slope; purlin/strut {bracing.get('pynite_roof_model',{}).get('stiffness_purlin_section','')}",fontSize=6.5))
        story += [roof_plan, Paragraph("Typical portal-frame section", styles["CalcH4"])]

        eaves_height = max(float(project.get("eaves_height_mm", 0)), 0)
        apex_height = max(float(project.get("apex_height_mm", 0)), eaves_height, 1)
        section = Drawing(170*mm, 72*mm)
        sec_x = lambda value: 15*mm + 140*mm*float(value)/building_span
        sec_y = lambda value: 10*mm + 48*mm*float(value)/apex_height
        roof_type = project.get("roof_type", "")
        section.add(Line(sec_x(0),sec_y(0),sec_x(0),sec_y(eaves_height),strokeColor=colors.HexColor("#174f78"),strokeWidth=2))
        right_top = apex_height if roof_type == "Mono Pitched" else eaves_height
        section.add(Line(sec_x(building_span),sec_y(0),sec_x(building_span),sec_y(right_top),strokeColor=colors.HexColor("#174f78"),strokeWidth=2))
        if roof_type == "Mono Pitched":
            points = [sec_x(0),sec_y(eaves_height),sec_x(building_span),sec_y(apex_height)]
        else:
            points = [sec_x(0),sec_y(eaves_height),sec_x(building_span/2),sec_y(apex_height),sec_x(building_span),sec_y(eaves_height)]
        section.add(PolyLine(points,strokeColor=colors.HexColor("#174f78"),strokeWidth=2))
        section.add(Line(sec_x(0),sec_y(0),sec_x(building_span),sec_y(0),strokeColor=colors.black))
        section.add(Line(sec_x(0),sec_y(0)-2*mm,sec_x(0),sec_y(apex_height)+4*mm,strokeColor=colors.HexColor("#8c98a4"),strokeDashArray=[2,2]))
        section.add(Line(sec_x(building_span),sec_y(0)-2*mm,sec_x(building_span),sec_y(apex_height)+4*mm,strokeColor=colors.HexColor("#8c98a4"),strokeDashArray=[2,2]))
        section.add(String(sec_x(0)-2*mm,2*mm,"A",fontSize=7))
        section.add(String(sec_x(building_span)-2*mm,2*mm,"B",fontSize=7))
        section.add(String(55*mm,2*mm,f"Span {_fmt(building_span,0)} mm",fontSize=6.5))
        section.add(String(2*mm,30*mm,f"Eaves {_fmt(eaves_height,0)}",fontSize=6.2,angle=90))
        section.add(String(162*mm,27*mm,f"Apex {_fmt(apex_height,0)}",fontSize=6.2,angle=90))
        section.add(String(20*mm,61*mm,f"Columns {project.get('column_section','')}; rafters {project.get('rafter_section','')}; pitch {_fmt(project.get('roof_pitch_deg',0),2)} deg",fontSize=6.5))
        story += [section]
        story += [Paragraph(
            f"Governing characteristic pressure {_fmt(bracing.get('governing_characteristic_pressure_kpa', 0))} kPa; "
            f"ULS wind factor {_fmt(bracing.get('wind_uls_factor', 0))}; total gable top shear "
            f"{_fmt(bracing.get('total_gable_top_shear_kn', 0))} kN.", styles["Small"]
        )]
        pressure_rows = [["Case", "Zone", "cpi", "|Pressure| (kPa)"]] + [[
            item["case"], item["zone"], _fmt(item.get("cpi")), _fmt(item["pressure_kpa"])
        ] for item in bracing.get("pressure_cases", [])]
        pressure_table = Table(pressure_rows, colWidths=[45*mm, 25*mm, 25*mm, 40*mm], repeatRows=1)
        pressure_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),7)]))
        story += [pressure_table, Paragraph("Bracing design assumptions", styles["CalcH4"])]
        story += [Paragraph(f"- {escape(item)}", styles["Small"]) for item in bracing.get("assumptions", [])]
        story += [PageBreak(), Paragraph("Gable-end elevation", styles["CalcH4"])]

        layout = bracing.get("gable_layout", {})
        width = max(float(layout.get("width_mm", 1)), 1)
        apex = max(float(layout.get("apex_height_mm", 1)), 1)
        drawing = Drawing(170*mm, 65*mm)
        gx = lambda value: 8*mm + 154*mm*float(value)/width
        gy = lambda value: 7*mm + 50*mm*float(value)/apex
        eaves_y = gy(layout.get("eaves_height_mm", 0))
        drawing.add(PolyLine([gx(0),eaves_y,gx(width/2),gy(apex),gx(width),eaves_y], strokeColor=colors.HexColor("#174f78"), strokeWidth=2))
        drawing.add(Line(gx(0),7*mm,gx(width),7*mm,strokeColor=colors.black))
        drawing.add(Line(gx(0),3*mm,gx(0),60*mm,strokeColor=colors.HexColor("#8c98a4"),strokeDashArray=[2,2]))
        drawing.add(Line(gx(width),3*mm,gx(width),60*mm,strokeColor=colors.HexColor("#8c98a4"),strokeDashArray=[2,2]))
        drawing.add(String(gx(0)-2*mm,0,"A",fontSize=6))
        drawing.add(String(gx(width)-2*mm,0,"B",fontSize=6))
        gable_by_name = {item["name"]: item for item in bracing.get("gable_columns", [])}
        for item in layout.get("columns", []):
            x = gx(item["x_mm"])
            drawing.add(Line(x,7*mm,x,gy(item["height_mm"]),strokeColor=colors.HexColor("#a21f2d"),strokeWidth=2))
            result = gable_by_name.get(item["name"], {})
            drawing.add(String(x-4*mm,2*mm,item["name"],fontSize=6))
            drawing.add(String(x+3.5*mm,(7*mm+gy(item["height_mm"]))/2,f"{result.get('section','')}",fontSize=5.5,angle=90))
        story += [drawing]

        column_rows = [["Column","Node","Section","Trib. mm","V kN","M kNm","Mcr","Mr","Util."]] + [[
            item["name"],item["roof_node"],item["section"],_fmt(item["tributary_width_mm"],0),
            _fmt(item["top_shear_kn"]),_fmt(item["major_moment_knm"]),_fmt(item["mcr_knm"]),
            _fmt(item["bending_resistance_knm"]),_fmt(item["utilisation"]),
        ] for item in bracing.get("gable_columns", [])]
        column_table = Table(column_rows, colWidths=[15*mm,15*mm,25*mm,20*mm,18*mm,18*mm,18*mm,18*mm,15*mm], repeatRows=1)
        column_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),6.2)]))
        story += [column_table, Paragraph("Gable-column design calculations", styles["CalcH4"])]
        gable_calc_rows = [["Column","Ref.","Calculation","Equation","Substitution","Result"]]
        wind_factor = float(bracing.get("wind_uls_factor", 0))
        for item in bracing.get("gable_columns", []):
            pressure = float(item.get("characteristic_pressure_kpa", 0))
            tributary_m = float(item.get("tributary_width_mm", 0))/1000
            height_m = float(item.get("height_mm", 0))/1000
            line_load = float(item.get("factored_line_load_kn_m", 0))
            moment = float(item.get("major_moment_knm", 0))
            shear = float(item.get("top_shear_kn", 0))
            mi = (
                float(item.get("plastic_moment_knm", 0))
                if int(item.get("section_class", 4)) < 3
                else float(item.get("yield_moment_knm", 0))
            )
            gable_calc_rows.extend([
                [item["name"],"GC-01","Factored line load","wu = p btr gammaw",f"{_fmt(pressure)}x{_fmt(tributary_m,3)}x{_fmt(wind_factor)}",f"{_fmt(line_load)} kN/m"],
                [item["name"],"GC-02","Pinned moment","M* = wu L^2/8",f"{_fmt(line_load)}x{_fmt(height_m,3)}^2/8",f"{_fmt(moment)} kNm"],
                [item["name"],"GC-03","Top shear","V* = wu L/2",f"{_fmt(line_load)}x{_fmt(height_m,3)}/2",f"{_fmt(shear)} kN"],
                [item["name"],"GC-04","Unbraced length","Lu = L/n",f"{_fmt(height_m,3)}/{int(item.get('brace_intervals',1))}",f"{_fmt(float(item.get('unbraced_length_mm',0))/1000,3)} m"],
                [item["name"],"GC-05","Elastic critical moment","Mcr=(w2*pi/Lu)sqrt[EIyGJ+(piE/Lu)^2IyCw]",f"w2={_fmt(item.get('omega2',0))}; Iy={_fmt(item.get('iy_cm4',0))}; J={_fmt(item.get('torsional_constant_cm4',0))}; Cw={_fmt(item.get('warping_constant',0))}",f"{_fmt(item.get('mcr_knm',0))} kNm"],
                [item["name"],"GC-06","LTB resistance","Mr = clause 13.6(Mcr,Mi)",f"Mcr={_fmt(item.get('mcr_knm',0))}; Mi={_fmt(mi)}",f"{_fmt(item.get('bending_resistance_knm',0))} kNm"],
                [item["name"],"GC-07","Utilisation","U = M*/Mr",f"{_fmt(moment)}/{_fmt(item.get('bending_resistance_knm',0))}",_fmt(item.get('utilisation',0))],
            ])
        gable_calc_formatted = [gable_calc_rows[0]] + [
            [Paragraph(escape(str(value)), styles["Tiny"]) for value in row]
            for row in gable_calc_rows[1:]
        ]
        gable_calc_table = Table(gable_calc_formatted,colWidths=[14*mm,14*mm,32*mm,39*mm,57*mm,25*mm],repeatRows=1)
        gable_calc_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),5.5),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story += [gable_calc_table]

        column_layout = bracing.get("column_bracing_layout", {})
        roof_model = bracing.get("pynite_roof_model", {})
        side = Drawing(170*mm, 48*mm)
        x0, x1, y0, y1, ym = 25*mm, 145*mm, 8*mm, 40*mm, 24*mm
        side.add(Line(x0,y0,x0,y1,strokeColor=colors.black,strokeWidth=1.5))
        side.add(Line(x1,y0,x1,y1,strokeColor=colors.black,strokeWidth=1.5))
        side_type = str(column_layout.get("type", "X"))
        panel_count = max(1, int(column_layout.get("panel_count", 1)))
        levels = [y0 + (y1-y0)*index/panel_count for index in range(panel_count+1)]
        for level in levels:
            side.add(Line(x0,level,x1,level,strokeColor=colors.black,strokeWidth=0.7))
        segments = []
        for bottom, top in zip(levels, levels[1:]):
            middle = (bottom + top)/2
            if side_type == "A":
                segments.extend(((x0,bottom,(x0+x1)/2,top),(x1,bottom,(x0+x1)/2,top)))
            elif side_type == "K":
                segments.extend(((x0,top,x1,middle),(x0,bottom,x1,middle)))
            else:
                segments.extend(((x0,bottom,x1,top),(x0,top,x1,bottom)))
        for xa, ya, xb, yb in segments:
            side.add(Line(xa,ya,xb,yb,strokeColor=colors.HexColor("#a21f2d"),strokeWidth=2))
        side_member = next((item for item in bracing.get("bracing_members", []) if item["member_type"] == "Longitudinal side-wall brace"), {})
        side.add(String(42*mm,2*mm,f"{side_type}-bracing: {side_member.get('section','')}; {panel_count} panels at {_fmt(column_layout.get('panel_height_mm',0),0)} mm; bay {_fmt(column_layout.get('bay_width_mm',0),0)} mm",fontSize=6.5))
        story += [KeepTogether([
            Paragraph("Typical longitudinal column-bracing bay", styles["CalcH4"]),
            side,
        ])]
        story += [Paragraph(
            f"Roof PyNite model: {escape(str(roof_model.get('analysis', '')))}; "
            f"{int(roof_model.get('node_count', 0))} nodes, {int(roof_model.get('member_count', 0))} members, "
            f"{int(roof_model.get('x_brace_count', 0))} tension-only X-braces. "
            f"Purlin stiffness section {escape(str(roof_model.get('stiffness_purlin_section', '')))}; "
            "resistance check deferred.", styles["Small"]
        )]
        story += [Paragraph("Bracing design calculations", styles["CalcH4"])]
        story += [Paragraph(
            "Brace force T* = (V*/2)(Ld/b). Tension resistance Tr = phi Ag fy. "
            "The CHS compression resistance also uses the implemented SANS column curve.",
            styles["Small"],
        )]
        calculation_rows = [["Member","Check","Equation","Substitution","Result"]]
        total_shear = float(bracing.get("total_gable_top_shear_kn", 0))
        bay_length = float(bracing.get("roof_layout", {}).get("bay_length_mm", 0))
        for item in bracing.get("bracing_members", []):
            force_projection = (
                float(column_layout.get("horizontal_projection_mm", bay_length))
                if item["member_type"] == "Longitudinal side-wall brace" else bay_length
            )
            calculation_rows.append([
                item["member_type"], "Brace force", "T* = (V*/2)(Ld/b)",
                f"({_fmt(total_shear)}/2)({_fmt(item.get('length_mm',0),1)}/{_fmt(force_projection,1)})",
                f"{_fmt(item.get('design_force_kn',0))} kN",
            ])
            length_mm = float(item.get("length_mm", 0))
            slenderness_limit = item.get("slenderness_limit", 0)
            if "Angles" in str(item.get("section_family", "")):
                for axis, factor, radius_key, ratio_key in (
                    ("x-x", 1.0, "rx_mm", "slenderness_xx"),
                    ("y-y", 1.0, "ry_mm", "slenderness_yy"),
                    ("v-v", 0.5, "rv_mm", "slenderness_vv"),
                ):
                    calculation_rows.append([
                        item["member_type"], f"Slenderness {axis}", "K L / r",
                        f"{_fmt(factor,1)} x {_fmt(length_mm,1)} / {_fmt(item.get(radius_key,0),2)}",
                        f"{_fmt(item.get(ratio_key,0))} <= {_fmt(slenderness_limit,0)}",
                    ])
            else:
                factor = float(item.get("effective_length_factor", 1.0))
                calculation_rows.append([
                    item["member_type"], "Slenderness", "K L / r",
                    f"{_fmt(factor,1)} x {_fmt(length_mm,1)} / {_fmt(item.get('radius_of_gyration_mm',0),2)}",
                    f"{_fmt(item.get('slenderness_ratio',0))} <= {_fmt(slenderness_limit,0)}",
                ])
            if item.get("behaviour") == "tension-only":
                equation = "Tr = phi Ag fy"
                substitution = f"0.9({_fmt(item.get('area_mm2',0),1)})({_fmt(item.get('fy_mpa',0),0)})/1000"
            else:
                equation = "Cr = phi Ag fy [1 + lambda^(2n)]^(-1/n)"
                substitution = (
                    f"0.9({_fmt(item.get('area_mm2',0),1)})({_fmt(item.get('fy_mpa',0),0)})"
                    f"[1+{_fmt(item.get('nondimensional_slenderness',0))}^(2x1.34)]^(-1/1.34)/1000"
                )
            calculation_rows.append([
                item["member_type"], "Resistance", equation, substitution,
                f"{_fmt(item.get('resistance_kn',0))} kN",
            ])
        calculation_table = Table(calculation_rows, colWidths=[36*mm,24*mm,39*mm,55*mm,20*mm], repeatRows=1)
        calculation_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),5.8),("VALIGN",(0,0),(-1,-1),"TOP")]))
        story += [calculation_table]
        member_rows = [["Member","Section","Behaviour","Force","Resistance","R util.","Axis / KLr","Slender util.","Gov. util."]] + [[
            item["member_type"],item["section"],item["behaviour"],_fmt(item["design_force_kn"]),
            _fmt(item["resistance_kn"]),_fmt(item.get("resistance_utilisation",item["utilisation"])),
            f"{item.get('slenderness_axis','x-x')} / {_fmt(item.get('slenderness_ratio',0))}",
            _fmt(item.get("slenderness_utilisation",0)),_fmt(item["utilisation"]),
        ] for item in bracing.get("bracing_members", [])]
        member_table = Table(member_rows, colWidths=[33*mm,23*mm,27*mm,15*mm,19*mm,14*mm,20*mm,19*mm,18*mm], repeatRows=1)
        member_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#cbd2d9")),("FONTSIZE",(0,0),(-1,-1),6.5)]))
        story += [member_table]
    doc.build(story)
    return output_path

