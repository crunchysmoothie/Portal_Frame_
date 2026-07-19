"""Validated input boundary shared by the Flet UI and future API client."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Mapping

import member_database as portal_members
from roof_layout import calculate_roof_bracing_layout


PROJECT_ROOT = Path(__file__).resolve().parent.parent

BUILDING_TYPES = ("Normal", "Canopy")
ROOF_TYPES = ("Duo Pitched", "Mono Pitched")
WIND_DESIGN_MODES = ("Prelim", "Final design")
ROOF_ACCESSIBILITY = ("Inaccessible", "Accessible")
LOAD_COMBINATION_STANDARDS = ("SANS 10160-1:2019", "Pre-2019")
TERRAIN_CATEGORIES = ("A", "B", "C", "D")
STEEL_GRADES = ("Steel_S355", "Steel_S275")
BASE_SUPPORTS = ("Pinned", "Fixed", "Spring")
COLUMN_BRACING_TYPES = ("X", "K", "A")
CRAWL_APPLICATIONS = ("One at a time", "All at the same time")
PORTAL_SECTION_FAMILIES = ("I-Sections", "H-Sections")
AUTOMATIC_SECTION = "Automatic - lightest passing"


def load_lipped_channel_sections() -> tuple[str, ...]:
    """Load the finite purlin/girt choices used by the design engine."""

    path = PROJECT_ROOT / "bracing_member_database.csv"
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = csv.DictReader(stream)
        values = [
            row["Designation"].strip()
            for row in rows
            if row.get("section_type") == "Lipped Channels"
            and row.get("Designation", "").strip()
        ]
    return tuple(dict.fromkeys(values))


LIPPED_CHANNEL_SECTIONS = load_lipped_channel_sections()
_PORTAL_MEMBER_DATABASE = portal_members.load_member_database(
    PROJECT_ROOT / "member_database.csv"
)
PORTAL_SECTIONS_BY_FAMILY: dict[str, tuple[str, ...]] = {
    family: tuple(_PORTAL_MEMBER_DATABASE[family])
    for family in PORTAL_SECTION_FAMILIES
}

DEFAULT_VALUES: dict[str, Any] = {
    "project_name": "New portal frame",
    "project_number": "",
    "designer": "",
    "building_type": "Normal",
    "building_roof": "Duo Pitched",
    "eaves_height_m": "6.5",
    "apex_height_m": "7.5",
    "gable_width_m": "16",
    "rafter_spacing_m": "6",
    "building_length_m": "48",
    "wind_design_mode": "Prelim",
    "roof_accessibility": "Inaccessible",
    "load_combination_standard": "SANS 10160-1:2019",
    "steel_grade": "Steel_S355",
    "rafter_section_type": "I-Sections",
    "rafter_section": AUTOMATIC_SECTION,
    "column_section_type": "I-Sections",
    "column_section": AUTOMATIC_SECTION,
    "base_support_condition": "Spring",
    "base_rotational_stiffness_knm_per_rad": "10000",
    "fundamental_basic_wind_speed": "32",
    "return_period": "50",
    "terrain_category": "B",
    "topographic_factor": "1.0",
    "altitude": "830",
    "blocking_factor": "0.0",
    "opening_side_1_m2": "0.0",
    "opening_side_2_m2": "0.0",
    "opening_gable_1_m2": "0.0",
    "opening_gable_2_m2": "0.0",
    "col_bracing_spacing": "1",
    "column_bracing_type": "X",
    "rafter_bracing_spacing": "2",
    "gable_column_count": "3",
    "gable_column_brace_intervals": "2",
    "purlin_section": "175x65x20x2.5",
    "purlin_max_spacing_mm": "1600",
    "girt_section": "175x65x20x2.5",
    "girt_max_spacing_mm": "1600",
    "use_crawl_beams": False,
    "crawl_application": "One at a time",
}


class InputValidationError(ValueError):
    """Raised with field-keyed validation errors suitable for form display."""

    def __init__(self, errors: Mapping[str, str]):
        self.errors = dict(errors)
        super().__init__("PortalFrame input validation failed")


def build_analysis_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Validate UI values and convert display units into engine units."""

    errors: dict[str, str] = {}

    def choice(key: str, allowed: tuple[str, ...]) -> str:
        value = str(raw.get(key, "")).strip()
        if value not in allowed:
            errors[key] = f"Choose one of: {', '.join(allowed)}."
        return value

    def number(
        key: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        strictly_positive: bool = False,
    ) -> float:
        value = raw.get(key, "")
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            errors[key] = "Enter a number."
            return 0.0
        if not math.isfinite(parsed):
            errors[key] = "Enter a finite number."
        elif strictly_positive and parsed <= 0:
            errors[key] = "Enter a value greater than zero."
        elif minimum is not None and parsed < minimum:
            errors[key] = f"Enter a value of at least {minimum:g}."
        elif maximum is not None and parsed > maximum:
            errors[key] = f"Enter a value no greater than {maximum:g}."
        return parsed

    def integer(key: str, *, minimum: int = 1, odd: bool = False) -> int:
        parsed = number(key)
        if key not in errors and not parsed.is_integer():
            errors[key] = "Enter a whole number."
        result = int(parsed)
        if key not in errors and result < minimum:
            errors[key] = f"Enter a whole number of at least {minimum}."
        if key not in errors and odd and result % 2 == 0:
            errors[key] = "Enter a positive odd number: 1, 3, 5, ..."
        return result

    building_type = choice("building_type", BUILDING_TYPES)
    roof_type = choice("building_roof", ROOF_TYPES)
    wind_mode = choice("wind_design_mode", WIND_DESIGN_MODES)
    roof_accessibility = choice("roof_accessibility", ROOF_ACCESSIBILITY)
    combination_standard = choice(
        "load_combination_standard", LOAD_COMBINATION_STANDARDS
    )
    terrain = choice("terrain_category", TERRAIN_CATEGORIES)
    steel_grade = choice("steel_grade", STEEL_GRADES)
    base_support = choice("base_support_condition", BASE_SUPPORTS)
    bracing_type = choice("column_bracing_type", COLUMN_BRACING_TYPES)
    crawl_application = choice("crawl_application", CRAWL_APPLICATIONS)
    rafter_section_type = choice(
        "rafter_section_type", PORTAL_SECTION_FAMILIES
    )
    column_section_type = choice(
        "column_section_type", PORTAL_SECTION_FAMILIES
    )

    eaves_m = number("eaves_height_m", strictly_positive=True)
    apex_m = number("apex_height_m", strictly_positive=True)
    width_m = number("gable_width_m", strictly_positive=True)
    spacing_m = number("rafter_spacing_m", strictly_positive=True)
    length_m = number("building_length_m", strictly_positive=True)
    if "apex_height_m" not in errors and "eaves_height_m" not in errors:
        if apex_m <= eaves_m:
            errors["apex_height_m"] = "Apex/high-side height must exceed eaves height."

    base_stiffness = 0.0
    if base_support == "Spring":
        base_stiffness = number(
            "base_rotational_stiffness_knm_per_rad", strictly_positive=True
        )

    basic_wind_speed = number(
        "fundamental_basic_wind_speed", strictly_positive=True
    )
    return_period = integer("return_period", minimum=1)
    topographic_factor = number("topographic_factor", strictly_positive=True)
    altitude = number("altitude", minimum=0)

    blocking_factor = 0.0
    if building_type == "Canopy":
        blocking_factor = number("blocking_factor", minimum=0, maximum=1)

    openings = {"side_1": 0.0, "side_2": 0.0, "gable_1": 0.0, "gable_2": 0.0}
    if building_type == "Normal" and wind_mode == "Final design":
        for ui_key, payload_key in (
            ("opening_side_1_m2", "side_1"),
            ("opening_side_2_m2", "side_2"),
            ("opening_gable_1_m2", "gable_1"),
            ("opening_gable_2_m2", "gable_2"),
        ):
            openings[payload_key] = number(ui_key, minimum=0)

    col_intervals = integer("col_bracing_spacing", minimum=1)
    roof_panels = integer("rafter_bracing_spacing", minimum=1)
    gable_columns = integer("gable_column_count", minimum=1, odd=True)
    gable_intervals = integer("gable_column_brace_intervals", minimum=1)
    purlin_spacing = number("purlin_max_spacing_mm", strictly_positive=True)
    girt_spacing = number("girt_max_spacing_mm", strictly_positive=True)

    purlin_section = str(raw.get("purlin_section", "")).strip()
    girt_section = str(raw.get("girt_section", "")).strip()
    if purlin_section not in LIPPED_CHANNEL_SECTIONS:
        errors["purlin_section"] = "Choose a lipped channel from the section database."
    if girt_section not in LIPPED_CHANNEL_SECTIONS:
        errors["girt_section"] = "Choose a lipped channel from the section database."

    def portal_section(key: str, family: str) -> str:
        value = str(raw.get(key, "")).strip()
        if value == AUTOMATIC_SECTION:
            return value
        if value not in PORTAL_SECTIONS_BY_FAMILY.get(family, ()):
            errors[key] = f"Choose Automatic or a section from {family}."
        return value

    rafter_section = portal_section("rafter_section", rafter_section_type)
    column_section = portal_section("column_section", column_section_type)

    layout_fields = {
        "eaves_height_m",
        "apex_height_m",
        "gable_width_m",
        "building_roof",
        "purlin_max_spacing_mm",
        "rafter_bracing_spacing",
    }
    if not layout_fields.intersection(errors):
        try:
            calculate_roof_bracing_layout(
                width_m * 1000,
                eaves_m * 1000,
                apex_m * 1000,
                roof_type,
                purlin_spacing,
                roof_panels,
            )
        except ValueError as exc:
            errors["purlin_max_spacing_mm"] = str(exc)

    if errors:
        raise InputValidationError(errors)

    roof_span_m = width_m / 2 if roof_type == "Duo Pitched" else width_m
    roof_pitch = math.degrees(math.atan((apex_m - eaves_m) / roof_span_m))
    use_crawl_beams = bool(raw.get("use_crawl_beams", False))

    return {
        "project": {
            "name": str(raw.get("project_name", "")).strip() or "Untitled project",
            "number": str(raw.get("project_number", "")).strip(),
            "designer": str(raw.get("designer", "")).strip(),
        },
        "building_data": {
            "building_type": building_type,
            "building_roof": roof_type,
            "wind_design_mode": wind_mode,
            "roof_accessibility": roof_accessibility,
            "load_combination_standard": combination_standard,
            "blocking_factor": blocking_factor,
            "opening_areas_m2": openings,
            "eaves_height": eaves_m * 1000,
            "apex_height": apex_m * 1000,
            "gable_width": width_m * 1000,
            "rafter_spacing": spacing_m * 1000,
            "building_length": length_m * 1000,
            "roof_pitch": roof_pitch,
            "col_bracing_spacing": col_intervals,
            "column_bracing_type": bracing_type,
            "rafter_bracing_spacing": roof_panels,
            "purlin_section": purlin_section,
            "purlin_max_spacing_mm": purlin_spacing,
            "girt_section": girt_section,
            "girt_max_spacing_mm": girt_spacing,
            "gable_column_count": gable_columns,
            "gable_column_brace_intervals": gable_intervals,
            "steel_grade": steel_grade,
            "rafter_section_type": rafter_section_type,
            "rafter_section": rafter_section,
            "column_section_type": column_section_type,
            "column_section": column_section,
            "base_support_condition": base_support,
            "base_rotational_stiffness_knm_per_rad": base_stiffness,
            "use_crawl_beams": "Yes" if use_crawl_beams else "No",
            "crawl_application": crawl_application,
        },
        "wind_data": {
            "wind": "3s gust",
            "fundamental_basic_wind_speed": basic_wind_speed,
            "return_period": return_period,
            "terrain_category": terrain,
            "topographic_factor": topographic_factor,
            "altitude": altitude,
        },
    }
