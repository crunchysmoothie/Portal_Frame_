"""Shared fabrication geometry rules for cut portal-frame haunches.

The haunch is cut from the selected rafter section.  This module is deliberately
independent of PyNite so input validation, automatic section selection,
connection design and drawing renderers all use the same dimensions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


_TOLERANCE_MM = 1e-6

# The user-specified fabrication rule uses the database flange width ``b``.
# Keeping the property and label explicit makes the rule auditable and prevents
# renderers from substituting nominal designation dimensions.
HAUNCH_CUT_DEDUCTION_PROPERTY = "b"
HAUNCH_CUT_DEDUCTION_LABEL = "flange width"
HAUNCH_DEPTH_SPECIFIED = "Specified Depth"
HAUNCH_DEPTH_CUT = "Cut-Depth"
HAUNCH_DEPTH_MODES = (HAUNCH_DEPTH_SPECIFIED, HAUNCH_DEPTH_CUT)


@dataclass(frozen=True)
class HaunchCutDepthCheck:
    """Auditable comparison of one requested cut against its donor section."""

    status: str
    provided_cut_depth_mm: float
    maximum_cut_depth_mm: float
    source_section_depth_mm: float
    source_flange_width_mm: float
    deduction_property: str
    equation: str

    @property
    def is_valid(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def maximum_haunch_cut_depth_mm(section: Mapping[str, Any]) -> float:
    """Return the physical cut limit from actual database dimensions.

    The result is never rounded upward.  A section whose flange width equals or
    exceeds its depth cannot supply a positive haunch cut.
    """

    depth = float(section["h"])
    deduction = float(section[HAUNCH_CUT_DEDUCTION_PROPERTY])
    return max(depth - deduction, 0.0)


def haunch_cut_depth_check(
    section: Mapping[str, Any],
    provided_cut_depth_mm: float,
) -> HaunchCutDepthCheck:
    """Check one requested haunch cut and return all calculation operands."""

    provided = float(provided_cut_depth_mm)
    depth = float(section["h"])
    flange_width = float(section["b"])
    maximum = maximum_haunch_cut_depth_mm(section)
    status = (
        "PASS"
        if provided >= -_TOLERANCE_MM and provided <= maximum + _TOLERANCE_MM
        else "FAIL"
    )
    return HaunchCutDepthCheck(
        status=status,
        provided_cut_depth_mm=max(provided, 0.0),
        maximum_cut_depth_mm=maximum,
        source_section_depth_mm=depth,
        source_flange_width_mm=flange_width,
        deduction_property=HAUNCH_CUT_DEDUCTION_PROPERTY,
        equation=f"h - b = {depth:.1f} - {flange_width:.1f} = {maximum:.1f} mm",
    )


def governing_requested_haunch_cut_depth_mm(
    frame_data: Mapping[str, Any],
) -> float:
    """Return the largest enabled eaves/apex cut requested for a rafter."""

    requested: list[float] = []
    if str(frame_data.get("use_eaves_haunch", "No")).lower() == "yes":
        requested.append(float(frame_data.get("eaves_haunch_depth", 0.0)))
    if str(frame_data.get("use_apex_haunch", "No")).lower() == "yes":
        requested.append(float(frame_data.get("apex_haunch_depth", 0.0)))
    return max(requested, default=0.0)


def governing_specified_haunch_cut_depth_mm(
    frame_data: Mapping[str, Any],
) -> float:
    """Return only fixed cuts that must filter automatic section candidates."""

    requested: list[float] = []
    for location in ("eaves", "apex"):
        if (
            str(frame_data.get(f"use_{location}_haunch", "No")).lower()
            != "yes"
        ):
            continue
        mode = str(
            frame_data.get(
                f"{location}_haunch_depth_mode",
                HAUNCH_DEPTH_SPECIFIED,
            )
        )
        if mode == HAUNCH_DEPTH_CUT:
            continue
        requested.append(
            float(frame_data.get(f"{location}_haunch_depth", 0.0))
        )
    return max(requested, default=0.0)


def resolve_haunch_cut_depths(
    frame_data: Mapping[str, Any],
    rafter_section: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve candidate-dependent Cut-Depth inputs for one rafter section."""

    resolved = dict(frame_data)
    maximum = maximum_haunch_cut_depth_mm(rafter_section)
    for location in ("eaves", "apex"):
        mode_key = f"{location}_haunch_depth_mode"
        depth_key = f"{location}_haunch_depth"
        mode = str(resolved.get(mode_key, HAUNCH_DEPTH_SPECIFIED))
        if mode not in HAUNCH_DEPTH_MODES:
            mode = HAUNCH_DEPTH_SPECIFIED
        resolved[mode_key] = mode
        if (
            str(resolved.get(f"use_{location}_haunch", "No")).lower()
            == "yes"
            and mode == HAUNCH_DEPTH_CUT
        ):
            resolved[depth_key] = maximum
    resolved["resolved_haunch_source_section"] = str(
        rafter_section.get("Designation", "")
    )
    return resolved


def haunch_cut_error(
    section_name: str,
    check: HaunchCutDepthCheck,
) -> str:
    """Return a stable field/API error for an invalid requested cut."""

    return (
        f"Cut depth {check.provided_cut_depth_mm:.1f} mm exceeds "
        f"{section_name} limit: {check.equation}."
    )
