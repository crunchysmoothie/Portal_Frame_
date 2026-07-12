"""Structured design-calculation results for calculation-sheet generation.

This module deliberately contains no PDF or console formatting. It converts the
analysis and member-design results into stable, numbered records that can feed a
PDF, Word document, spreadsheet, or UI without repeating engineering formulas.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import math
from typing import Any, Iterable, Mapping, Sequence

from strength_checks import member_design, section_properties


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


@dataclass(frozen=True)
class MemberCalculation:
    member: str
    member_type: str
    section: str
    load_combination: str
    axial_force: float
    major_moment: float
    section_class: int
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
    assumptions: list[str] = field(default_factory=list)
    members: list[MemberCalculation] = field(default_factory=list)
    reactions: list[ReactionResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "scope": self.scope.value,
            "project": dict(self.project),
            "assumptions": list(self.assumptions),
            "members": [item.to_dict() for item in self.members],
            "reactions": [item.to_dict() for item in self.reactions],
            "warnings": list(self.warnings),
        }


def _check_item(
    reference: str,
    title: str,
    equation: str,
    substitution: str,
    result: float,
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
    mx = abs(float(member_actions["Mx_max"]))
    member_class = int(member_actions["Class"])
    m_fac = 0.85 if member_class < 3 else 1.0
    w1 = float(member_actions["w1"])
    u1x = w1 / (1.0 - cu / sec["Cex"])
    u1x_css = max(1.0, u1x)

    items = (
        _check_item(
            "M-01",
            "Cross-sectional strength",
            "U = Cu/Cr + m U1x Mx/Mrx",
            f"{cu:.3f}/{sec['Cr']:.3f} + {m_fac:.2f} x {u1x_css:.3f} x "
            f"{mx:.3f}/{sec['Mrx']:.3f}",
            float(css),
        ),
        _check_item(
            "M-02",
            "Overall member strength",
            "U = Cu/Crx + m U1x Mx/Mrx",
            f"{cu:.3f}/{sec['Crx']:.3f} + {m_fac:.2f} x {u1x:.3f} x "
            f"{mx:.3f}/{sec['Mrx']:.3f}",
            float(oms),
        ),
        _check_item(
            "M-03",
            "Lateral-torsional buckling interaction",
            "U = Cu/Cry + m U1x Mx/Mrx",
            f"{cu:.3f}/{sec['Cry']:.3f} + {m_fac:.2f} x {u1x_css:.3f} x "
            f"{mx:.3f}/{sec['Mrx']:.3f}",
            float(ltb[0]),
        ),
        _check_item(
            "M-04",
            "Bending resistance",
            "U = Mx/Mrx",
            f"{mx:.3f}/{sec['Mrx']:.3f}",
            float(ltb[1]),
        ),
    )
    governing = max(items, key=lambda item: item.result if math.isfinite(item.result) else math.inf)
    return MemberCalculation(
        member=str(member_actions["Name"]),
        member_type=str(member_actions["type"]),
        section=str(member_actions["section"]),
        load_combination=load_combination,
        axial_force=cu,
        major_moment=mx,
        section_class=member_class,
        calculations=items,
        governing_ratio=governing.result,
        governing_check=governing.reference,
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
                    mx=_result_value(node.RxnMX, combination),
                    my=_result_value(node.RxnMY, combination),
                    mz=_result_value(node.RxnMZ, combination),
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

    # Retain one governing result for each physical member. This keeps the
    # summary concise while still showing the critical rafter and both columns.
    critical: dict[str, MemberCalculation] = {}
    for item in results:
        current = critical.get(item.member)
        if current is None or item.governing_ratio > current.governing_ratio:
            critical[item.member] = item
    return sorted(critical.values(), key=lambda item: item.member)

