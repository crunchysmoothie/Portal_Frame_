"""Validated input boundary shared by the Flet UI and future API client."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Mapping

import member_database as portal_members
from foundation_design import DEFAULT_FOUNDATION_VALUES
from roof_layout import calculate_roof_bracing_layout


PROJECT_ROOT = Path(__file__).resolve().parent.parent

BUILDING_TYPES = ("Normal", "Canopy")
STRUCTURAL_SYSTEMS = ("Portal frame", "Truss")
ROOF_TYPES = ("Duo Pitched", "Mono Pitched")
WIND_DESIGN_MODES = ("Prelim", "Final design")
ROOF_ACCESSIBILITY = ("Inaccessible", "Accessible")
LOAD_COMBINATION_STANDARDS = ("SANS 10160-1:2019", "Pre-2019")
TERRAIN_CATEGORIES = ("A", "B", "C", "D")
STEEL_GRADES = ("Steel_S355", "Steel_S275")
BASE_SUPPORTS = ("Pinned", "Fixed", "Spring")
COLUMN_BRACING_TYPES = ("X", "K", "A")
CRAWL_APPLICATIONS = ("One at a time", "All at the same time")
CRAWL_SLOPES = ("left", "right", "single")
HOIST_CLASSES = ("C1", "C2", "C3", "C4")
PORTAL_SECTION_FAMILIES = ("I-Sections", "H-Sections")
AUTOMATIC_SECTION = "Automatic - lightest passing"
TRUSS_TYPES = ("Warren with verticals", "Pratt", "Howe")
TRUSS_CHORD_FORMS = ("Parallel chords", "Horizontal bottom chord")
TRUSS_INTERNAL_SUPPORTS = ("Centre columns", "Longitudinal girders")
TRUSS_CENTRE_COLUMN_MATERIALS = ("Steel", "Concrete tilt-up")
TRUSS_STEEL_SECTION_ORDERS = ("Automatic - lightest passing", "Preferred sections first")


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
    "structural_system": "Portal frame",
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
    "use_eaves_haunch": False,
    "eaves_haunch_length_m": "1.5",
    "eaves_haunch_depth_mm": "450",
    "use_apex_haunch": False,
    "apex_haunch_length_m": "1.0",
    "apex_haunch_depth_mm": "300",
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
    "crawl_beams": [],
    "truss_minimum_depth_m": "2.0",
    "truss_maximum_depth_m": "4.0",
    "truss_depth_increment_m": "0.2",
    "truss_ranked_solution_count": "3",
    "truss_transverse_bay_spans_m": "40",
    "truss_building_length_m": "60",
    "truss_spacing_m": "6",
    "truss_eaves_height_m": "8",
    "truss_roof_pitch_deg": "5",
    "truss_type": "Warren with verticals",
    "truss_chord_form": "Parallel chords",
    "truss_internal_support": "Centre columns",
    "truss_design_centre_columns": False,
    "truss_centre_column_material": "Steel",
    "truss_centre_column_bracing_spacing_m": "6",
    "truss_centre_column_steel_section_order": "Automatic - lightest passing",
    "truss_centre_column_concrete_width_mm": "300",
    "truss_centre_column_concrete_thickness_mm": "200",
    "truss_centre_column_concrete_bracing_spacing_m": "6",
    "truss_centre_column_concrete_fck_mpa": "30",
    "truss_centre_column_concrete_rebar_area_mm2": "4000",
    "truss_girder_span_bays": "4",
    "truss_girder_minimum_depth_m": "2.0",
    "truss_girder_maximum_depth_m": "4.0",
    "truss_girder_depth_increment_m": "0.25",
    "truss_girder_deflection_denominator": "360",
    "truss_top_chord_brace_every_n_purlins": "1",
    "truss_bottom_chord_brace_every_n_purlins": "2",
    "truss_deflection_denominator": "180",
    "truss_services_load_kpa": "0",
    "truss_ceiling_load_kpa": "0",
    "truss_solar_load_kpa": "0",
    "truss_fire_load_kpa": "0",
    "truss_hvac_load_kpa": "0",
}
DEFAULT_VALUES.update(DEFAULT_FOUNDATION_VALUES)


class InputValidationError(ValueError):
    """Raised with field-keyed validation errors suitable for form display."""

    def __init__(self, errors: Mapping[str, str]):
        self.errors = dict(errors)
        super().__init__("Structural design input validation failed")


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

    def number_list(key: str, *, minimum_count: int = 1) -> list[float]:
        values = [item.strip() for item in str(raw.get(key, "")).split(",")]
        if any(not item for item in values):
            errors[key] = "Enter comma-separated numbers."
            return []
        try:
            parsed = [float(item) for item in values]
        except ValueError:
            errors[key] = "Enter comma-separated numbers."
            return []
        if len(parsed) < minimum_count or any(
            not math.isfinite(value) or value <= 0 for value in parsed
        ):
            errors[key] = (
                f"Enter at least {minimum_count} positive comma-separated values."
            )
        return parsed

    structural_system = choice("structural_system", STRUCTURAL_SYSTEMS)
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
    if structural_system == "Truss" and building_type != "Normal":
        errors["building_type"] = "The first truss iteration supports Normal enclosed buildings only."
    if structural_system == "Truss" and steel_grade != "Steel_S355":
        errors["steel_grade"] = "The first truss iteration supports S355JR only."

    truss_bay_spans_m = number_list(
        "truss_transverse_bay_spans_m", minimum_count=1
    )
    truss_span_count = len(truss_bay_spans_m)
    truss_width_m = sum(truss_bay_spans_m)
    truss_eaves_height_m = number(
        "truss_eaves_height_m", strictly_positive=True
    )
    truss_building_length_m = number(
        "truss_building_length_m", strictly_positive=True
    )
    truss_spacing_m = number("truss_spacing_m", strictly_positive=True)
    truss_roof_pitch_deg = number(
        "truss_roof_pitch_deg", minimum=0.1, maximum=30.0
    )
    truss_type = choice("truss_type", TRUSS_TYPES)
    truss_chord_form = choice("truss_chord_form", TRUSS_CHORD_FORMS)
    truss_internal_support = choice(
        "truss_internal_support", TRUSS_INTERNAL_SUPPORTS
    )
    centre_column_design = bool(raw.get("truss_design_centre_columns", False))
    centre_column_material = str(
        raw.get("truss_centre_column_material", "Steel")
    ).strip()
    centre_column_section_order = str(
        raw.get(
            "truss_centre_column_steel_section_order",
            "Automatic - lightest passing",
        )
    ).strip()
    centre_column_bracing_spacing_m = 0.0
    centre_column_concrete_width_mm = 0.0
    centre_column_concrete_thickness_mm = 0.0
    centre_column_concrete_bracing_spacing_m = 0.0
    centre_column_concrete_fck_mpa = 0.0
    centre_column_concrete_rebar_area_mm2 = 0.0
    if (
        structural_system == "Truss"
        and truss_span_count > 1
        and truss_internal_support == "Centre columns"
        and centre_column_design
    ):
        centre_column_material = choice(
            "truss_centre_column_material", TRUSS_CENTRE_COLUMN_MATERIALS
        )
        if centre_column_material == "Steel":
            centre_column_bracing_spacing_m = number(
                "truss_centre_column_bracing_spacing_m", strictly_positive=True
            )
            centre_column_section_order = choice(
                "truss_centre_column_steel_section_order",
                TRUSS_STEEL_SECTION_ORDERS,
            )
        elif centre_column_material == "Concrete tilt-up":
            centre_column_concrete_width_mm = number(
                "truss_centre_column_concrete_width_mm", strictly_positive=True
            )
            centre_column_concrete_thickness_mm = number(
                "truss_centre_column_concrete_thickness_mm", strictly_positive=True
            )
            centre_column_concrete_bracing_spacing_m = number(
                "truss_centre_column_concrete_bracing_spacing_m", strictly_positive=True
            )
            centre_column_concrete_fck_mpa = number(
                "truss_centre_column_concrete_fck_mpa", minimum=20
            )
            centre_column_concrete_rebar_area_mm2 = number(
                "truss_centre_column_concrete_rebar_area_mm2", minimum=0
            )
    truss_girder_span_bays = integer("truss_girder_span_bays", minimum=2)
    truss_girder_minimum_depth_m = number(
        "truss_girder_minimum_depth_m", strictly_positive=True
    )
    truss_girder_maximum_depth_m = number(
        "truss_girder_maximum_depth_m", strictly_positive=True
    )
    truss_girder_depth_increment_m = number(
        "truss_girder_depth_increment_m", strictly_positive=True
    )
    truss_girder_deflection_denominator = number(
        "truss_girder_deflection_denominator", strictly_positive=True
    )
    if truss_girder_maximum_depth_m < truss_girder_minimum_depth_m:
        errors["truss_girder_maximum_depth_m"] = (
            "Maximum girder depth must be at least the minimum depth."
        )
    if structural_system == "Truss" and truss_spacing_m > 0:
        building_bays = truss_building_length_m / truss_spacing_m
        if not math.isclose(building_bays, round(building_bays), abs_tol=1e-8):
            errors["truss_building_length_m"] = (
                "Building length must be a whole number of truss-grid bays."
            )
        elif (
            truss_span_count > 1
            and truss_internal_support == "Longitudinal girders"
            and int(round(building_bays)) % truss_girder_span_bays != 0
        ):
            errors["truss_girder_span_bays"] = (
                f"The {int(round(building_bays))} building bays must divide evenly "
                "by the selected girder bay count."
            )
    roof_rise_m = apex_m - eaves_m
    if structural_system == "Truss" and truss_bay_spans_m:
        width_m = truss_width_m
        eaves_m = truss_eaves_height_m
        roof_run_m = width_m / 2.0 if roof_type == "Duo Pitched" else width_m
        roof_rise_m = math.tan(math.radians(truss_roof_pitch_deg)) * roof_run_m
        apex_m = truss_eaves_height_m + roof_rise_m
        length_m = truss_building_length_m
        spacing_m = truss_spacing_m

    truss_minimum_depth_m = number(
        "truss_minimum_depth_m", strictly_positive=True
    )
    truss_maximum_depth_m = number(
        "truss_maximum_depth_m", strictly_positive=True
    )
    if truss_maximum_depth_m < truss_minimum_depth_m:
        errors["truss_maximum_depth_m"] = (
            "Maximum truss depth must be at least the minimum depth."
        )
    truss_depth_increment_m = number(
        "truss_depth_increment_m", strictly_positive=True
    )
    truss_ranked_solution_count = integer(
        "truss_ranked_solution_count", minimum=1
    )
    truss_top_chord_brace_every_n_purlins = integer(
        "truss_top_chord_brace_every_n_purlins", minimum=1
    )
    truss_bottom_chord_brace_every_n_purlins = integer(
        "truss_bottom_chord_brace_every_n_purlins", minimum=1
    )
    truss_deflection_denominator = number(
        "truss_deflection_denominator", strictly_positive=True
    )
    truss_loads = {
        name: number(f"truss_{name}_load_kpa", minimum=0)
        for name in ("services", "ceiling", "solar", "fire", "hvac")
    }

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

    use_eaves_haunch = (
        structural_system == "Portal frame"
        and bool(raw.get("use_eaves_haunch", False))
    )
    use_apex_haunch = (
        structural_system == "Portal frame"
        and bool(raw.get("use_apex_haunch", False))
    )
    eaves_haunch_length_m = 0.0
    eaves_haunch_depth_mm = 0.0
    apex_haunch_length_m = 0.0
    apex_haunch_depth_mm = 0.0
    if use_eaves_haunch:
        eaves_haunch_length_m = number(
            "eaves_haunch_length_m", strictly_positive=True
        )
        eaves_haunch_depth_mm = number(
            "eaves_haunch_depth_mm", strictly_positive=True, maximum=2000
        )
    if use_apex_haunch:
        apex_haunch_length_m = number(
            "apex_haunch_length_m", strictly_positive=True
        )
        apex_haunch_depth_mm = number(
            "apex_haunch_depth_mm", strictly_positive=True, maximum=2000
        )
    roof_slope_length_m = math.hypot(
        width_m / (2 if roof_type == "Duo Pitched" else 1),
        apex_m - eaves_m,
    )
    if (
        use_eaves_haunch
        and "eaves_haunch_length_m" not in errors
        and eaves_haunch_length_m >= roof_slope_length_m
    ):
        errors["eaves_haunch_length_m"] = (
            f"Length must be less than the roof slope length of "
            f"{roof_slope_length_m:.2f} m."
        )
    if (
        use_apex_haunch
        and "apex_haunch_length_m" not in errors
        and apex_haunch_length_m >= roof_slope_length_m
    ):
        errors["apex_haunch_length_m"] = (
            f"Length must be less than the roof slope length of "
            f"{roof_slope_length_m:.2f} m."
        )
    if (
        use_eaves_haunch
        and use_apex_haunch
        and not {
            "eaves_haunch_length_m",
            "apex_haunch_length_m",
        }.intersection(errors)
        and eaves_haunch_length_m + apex_haunch_length_m
        >= roof_slope_length_m
    ):
        errors["apex_haunch_length_m"] = (
            "Eaves and apex haunch zones must not overlap on a roof slope."
        )

    raw_crawls = raw.get("crawl_beams", [])
    if raw_crawls is None:
        raw_crawls = []
    if not isinstance(raw_crawls, (list, tuple)):
        errors["crawl_beams"] = "Crawl beams must be entered as a list."
        raw_crawls = []

    crawl_beams: list[dict[str, Any]] = []
    crawl_names: set[str] = set()
    slope_length_mm = math.hypot(
        (width_m / (2 if roof_type == "Duo Pitched" else 1)) * 1000,
        (apex_m - eaves_m) * 1000,
    )
    for index, raw_crawl in enumerate(raw_crawls):
        prefix = f"crawl_beams[{index}]"
        if not isinstance(raw_crawl, Mapping):
            errors[prefix] = "Enter a crawl beam object."
            continue

        def crawl_text(field: str, label: str) -> str:
            value = str(raw_crawl.get(field, "")).strip()
            if not value:
                errors[f"{prefix}.{field}"] = f"Enter {label}."
            return value

        def crawl_number(
            field: str,
            label: str,
            *,
            minimum: float = 0.0,
            strictly_positive: bool = False,
        ) -> float:
            value = raw_crawl.get(field, "")
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                errors[f"{prefix}.{field}"] = f"Enter {label} as a number."
                return 0.0
            if not math.isfinite(parsed):
                errors[f"{prefix}.{field}"] = f"Enter a finite {label}."
            elif strictly_positive and parsed <= 0:
                errors[f"{prefix}.{field}"] = f"Enter a {label} greater than zero."
            elif parsed < minimum:
                errors[f"{prefix}.{field}"] = f"Enter a {label} of at least {minimum:g}."
            return parsed

        name = crawl_text("name", "a crawl beam name")
        name_key = name.casefold()
        if name_key and name_key in crawl_names:
            errors[f"{prefix}.name"] = "Crawl beam names must be unique."
        if name_key:
            crawl_names.add(name_key)

        slope = str(raw_crawl.get("slope", "")).strip().lower()
        allowed_slopes = ("left", "right") if roof_type == "Duo Pitched" else ("single", "left")
        if slope not in allowed_slopes:
            errors[f"{prefix}.slope"] = (
                f"Choose one of: {', '.join(allowed_slopes)}."
            )

        position = crawl_number(
            "position_from_eaves_mm", "the position from the eaves", minimum=0
        )
        if (
            f"{prefix}.position_from_eaves_mm" not in errors
            and position > slope_length_mm + 1e-6
        ):
            errors[f"{prefix}.position_from_eaves_mm"] = (
                f"Position must not exceed the roof slope length of {slope_length_mm:.0f} mm."
            )

        section_type = str(raw_crawl.get("section_type", "")).strip()
        if section_type not in PORTAL_SECTION_FAMILIES:
            errors[f"{prefix}.section_type"] = (
                f"Choose one of: {', '.join(PORTAL_SECTION_FAMILIES)}."
            )
        section = str(raw_crawl.get("section", "")).strip()
        if section not in PORTAL_SECTIONS_BY_FAMILY.get(section_type, ()):
            errors[f"{prefix}.section"] = f"Choose a section from {section_type}."

        swl = crawl_number("swl_kg", "the safe working load", strictly_positive=True)
        trolley_mass = crawl_number("hoist_trolley_mass_kg", "the hoist/trolley mass")
        attachment_mass = crawl_number(
            "lifting_attachment_mass_kg", "the lifting attachment mass"
        )
        hoist_class = str(raw_crawl.get("hoist_class", "")).strip().upper()
        if hoist_class not in HOIST_CLASSES:
            errors[f"{prefix}.hoist_class"] = f"Choose one of: {', '.join(HOIST_CLASSES)}."
        speed = crawl_number(
            "hoisting_speed_m_s", "the hoisting speed", minimum=0
        )

        crawl_beams.append(
            {
                "name": name,
                "slope": slope,
                "position_from_eaves_mm": position,
                "section_type": section_type,
                "section": section,
                "swl_kg": swl,
                "hoist_trolley_mass_kg": trolley_mass,
                "lifting_attachment_mass_kg": attachment_mass,
                "hoist_class": hoist_class,
                "hoisting_speed_m_s": speed,
            }
        )

    use_crawl_beams = bool(raw.get("use_crawl_beams", False))
    if use_crawl_beams and not crawl_beams:
        errors["crawl_beams"] = "Add at least one crawl beam when crawl loading is enabled."

    layout_fields = {
        "eaves_height_m",
        "apex_height_m",
        "gable_width_m",
        "building_roof",
        "purlin_max_spacing_mm",
        "rafter_bracing_spacing",
    }
    if structural_system != "Truss" and not layout_fields.intersection(errors):
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
    return {
        "structural_system": structural_system,
        "project": {
            "name": str(raw.get("project_name", "")).strip() or "Untitled project",
            "number": str(raw.get("project_number", "")).strip(),
            "designer": str(raw.get("designer", "")).strip(),
            "structural_system": structural_system,
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
            "use_eaves_haunch": "Yes" if use_eaves_haunch else "No",
            "eaves_haunch_length": eaves_haunch_length_m * 1000,
            "eaves_haunch_depth": eaves_haunch_depth_mm,
            "use_apex_haunch": "Yes" if use_apex_haunch else "No",
            "apex_haunch_length": apex_haunch_length_m * 1000,
            "apex_haunch_depth": apex_haunch_depth_mm,
            "base_support_condition": base_support,
            "base_rotational_stiffness_knm_per_rad": base_stiffness,
            "use_crawl_beams": "Yes" if use_crawl_beams else "No",
            "crawl_application": crawl_application,
            "crawl_beams": crawl_beams,
        },
        "wind_data": {
            "wind": "3s gust",
            "fundamental_basic_wind_speed": basic_wind_speed,
            "return_period": return_period,
            "terrain_category": terrain,
            "topographic_factor": topographic_factor,
            "altitude": altitude,
        },
        "truss_data": {
            "topology": truss_type,
            "joint_model": "Pinned",
            "section_families": ["Equal Angles", "Back-to-back Equal Angles"],
            "steel_grade": "S355JR",
            "fy_mpa": 355.0,
            "elastic_modulus_mpa": 200_000.0,
            "transverse_bay_spans_mm": [
                value * 1000.0 for value in truss_bay_spans_m
            ],
            "span_count": truss_span_count,
            "building_width_mm": truss_width_m * 1000.0,
            "roof_pitch_deg": truss_roof_pitch_deg,
            "roof_rise_mm": roof_rise_m * 1000.0,
            "chord_form": truss_chord_form,
            "internal_support": truss_internal_support,
            "design_centre_columns": centre_column_design,
            "centre_column_material": centre_column_material,
            "centre_column_bracing_spacing_mm": centre_column_bracing_spacing_m * 1000.0,
            "centre_column_steel_section_order": centre_column_section_order,
            "centre_column_concrete_width_mm": centre_column_concrete_width_mm,
            "centre_column_concrete_thickness_mm": centre_column_concrete_thickness_mm,
            "centre_column_concrete_bracing_spacing_mm": centre_column_concrete_bracing_spacing_m * 1000.0,
            "centre_column_concrete_fck_mpa": centre_column_concrete_fck_mpa,
            "centre_column_concrete_rebar_area_mm2": centre_column_concrete_rebar_area_mm2,
            "girder_span_bays": truss_girder_span_bays,
            "girder_span_mm": truss_girder_span_bays * truss_spacing_m * 1000.0,
            "girder_minimum_depth_mm": truss_girder_minimum_depth_m * 1000.0,
            "girder_maximum_depth_mm": truss_girder_maximum_depth_m * 1000.0,
            "girder_depth_increment_mm": truss_girder_depth_increment_m * 1000.0,
            "girder_deflection_denominator": truss_girder_deflection_denominator,
            "minimum_depth_mm": truss_minimum_depth_m * 1000.0,
            "maximum_depth_mm": truss_maximum_depth_m * 1000.0,
            "depth_increment_mm": truss_depth_increment_m * 1000.0,
            "maximum_panel_width_mm": purlin_spacing,
            "ranked_solution_count": truss_ranked_solution_count,
            "top_chord_brace_every_n_purlins": truss_top_chord_brace_every_n_purlins,
            "bottom_chord_brace_every_n_purlins": truss_bottom_chord_brace_every_n_purlins,
            "bracing_coverage": "Entire building length",
            "deflection_denominator": truss_deflection_denominator,
            "services_load_kpa": truss_loads["services"],
            "ceiling_load_kpa": truss_loads["ceiling"],
            "solar_load_kpa": truss_loads["solar"],
            "fire_load_kpa": truss_loads["fire"],
            "hvac_load_kpa": truss_loads["hvac"],
        },
    }
