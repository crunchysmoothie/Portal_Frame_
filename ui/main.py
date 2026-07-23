"""First browser/desktop Flet draft for PortalFrame."""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any

import flet as ft
import httpx

from foundation_design import FOUNDATION_STANDARDS
from preview_geometry import build_preview_geometry
from truss_design import preview_truss
from ui.analysis_render import combination_names, load_case_svg
from ui.input_model import (
    AUTOMATIC_SECTION,
    BASE_SUPPORTS,
    BUILDING_TYPES,
    COLUMN_BRACING_TYPES,
    CRAWL_APPLICATIONS,
    HOIST_CLASSES,
    DEFAULT_VALUES,
    LIPPED_CHANNEL_SECTIONS,
    LOAD_COMBINATION_STANDARDS,
    PORTAL_SECTION_FAMILIES,
    PORTAL_SECTIONS_BY_FAMILY,
    ROOF_ACCESSIBILITY,
    ROOF_TYPES,
    STRUCTURAL_SYSTEMS,
    STEEL_GRADES,
    TERRAIN_CATEGORIES,
    TRUSS_CHORD_FORMS,
    TRUSS_CENTRE_COLUMN_MATERIALS,
    TRUSS_STEEL_SECTION_ORDERS,
    TRUSS_INTERNAL_SUPPORTS,
    TRUSS_TYPES,
    WIND_DESIGN_MODES,
    InputValidationError,
    build_analysis_payload,
)
from ui.preview_render import (
    frame_elevation_svg,
    roof_plan_svg,
    truss_girder_elevation_svg,
    truss_elevation_svg,
    truss_roof_plan_svg,
    truss_type_reference_svg,
    wall_elevation_svg,
)


API_URL = "http://127.0.0.1:8000"
ACCENT = "#176B68"
ACCENT_DARK = "#0D4846"
PAGE_BG = "#F4F7F7"
CARD_BG = "#FFFFFF"
TEXT_PRIMARY = "#18302F"
TEXT_MUTED = "#607472"
SUCCESS_BG = "#E4F5EE"
WARNING_BG = "#FFF4D9"
ERROR_BG = "#FCE8E6"


def main(page: ft.Page) -> None:
    page.title = "Portal Frame and Truss Designer"
    page.padding = 0
    page.bgcolor = PAGE_BG
    page.theme = ft.Theme(
        color_scheme_seed=ACCENT,
        use_material3=True,
        color_scheme=ft.ColorScheme(
            primary=ACCENT,
            on_primary="#FFFFFF",
            surface="#FFFFFF",
            on_surface=TEXT_PRIMARY,
        ),
    )

    controls: dict[str, Any] = {}

    def dropdown(
        key: str,
        label: str,
        values: tuple[str, ...],
        *,
        helper: str = "",
        col: dict[str, int] | int = 6,
        searchable: bool = False,
    ) -> ft.Dropdown:
        control = ft.Dropdown(
            key=key,
            label=label,
            value=str(DEFAULT_VALUES[key]),
            options=[
                ft.DropdownOption(
                    key=value,
                    content=ft.Text(value, color=TEXT_PRIMARY),
                )
                for value in values
            ],
            enable_filter=searchable,
            enable_search=True,
            editable=False,
            helper_text=helper or None,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_MUTED),
            border_color="#93AAA7",
            focused_border_color=ACCENT,
            helper_style=ft.TextStyle(color=TEXT_MUTED, size=11),
            menu_style=ft.MenuStyle(bgcolor="#FFFFFF", shadow_color="#607472"),
            col=col,
            dense=True,
        )
        controls[key] = control
        return control

    def text_field(
        key: str,
        label: str,
        *,
        helper: str = "",
        col: dict[str, int] | int = 6,
    ) -> ft.TextField:
        control = ft.TextField(
            key=key,
            label=label,
            value=str(DEFAULT_VALUES[key]),
            helper=helper or None,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_MUTED),
            border_color="#93AAA7",
            focused_border_color=ACCENT,
            helper_style=ft.TextStyle(color=TEXT_MUTED, size=11),
            col=col,
            dense=True,
        )
        controls[key] = control
        return control

    def number_field(
        key: str,
        label: str,
        *,
        unit: str = "",
        helper: str = "",
        integer: bool = False,
        col: dict[str, int] | int = 6,
        on_change=None,
    ) -> ft.TextField:
        control = ft.TextField(
            key=key,
            label=label,
            value=str(DEFAULT_VALUES[key]),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter() if integer else None,
            suffix=unit or None,
            helper=helper or None,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_MUTED),
            border_color="#93AAA7",
            focused_border_color=ACCENT,
            helper_style=ft.TextStyle(color=TEXT_MUTED, size=11),
            suffix_style=ft.TextStyle(color=TEXT_MUTED),
            col=col,
            dense=True,
            on_change=on_change,
        )
        controls[key] = control
        return control

    def card(title: str, subtitle: str, content: ft.Control) -> ft.Card:
        return ft.Card(
            elevation=0,
            bgcolor=CARD_BG,
            content=ft.Container(
                padding=22,
                content=ft.Column(
                    spacing=16,
                    controls=[
                        ft.Column(
                            spacing=3,
                            controls=[
                                ft.Text(
                                    title,
                                    size=18,
                                    weight=ft.FontWeight.W_600,
                                    color=TEXT_PRIMARY,
                                ),
                                ft.Text(subtitle, size=12, color=TEXT_MUTED),
                            ],
                        ),
                        content,
                    ],
                ),
            ),
        )

    def section_heading(title: str, subtitle: str) -> ft.Column:
        return ft.Column(
            spacing=3,
            controls=[
                ft.Text(title, size=26, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                ft.Text(subtitle, size=13, color=TEXT_MUTED),
            ],
        )

    # Project and building controls.
    project_name = text_field("project_name", "Project name", col=12)
    project_number = text_field(
        "project_number", "Project number", col=6
    )
    designer = text_field("designer", "Designer", col=6)
    structural_system = dropdown(
        "structural_system",
        "Structural system",
        STRUCTURAL_SYSTEMS,
        helper="Select one engineering system for this project.",
        col=12,
    )
    building_type = dropdown(
        "building_type",
        "Building type",
        BUILDING_TYPES,
        helper="Normal enclosed building or open canopy.",
    )
    building_roof = dropdown(
        "building_roof",
        "Roof form",
        ROOF_TYPES,
        helper="Duo-pitched or mono-pitched portal.",
    )
    building_type.helper_text = None
    building_roof.helper_text = None
    building_type.col = 12
    building_roof.col = 12
    building_type_field = ft.Container(
        col=6,
        content=ft.Column(
            spacing=2,
            controls=[
                building_type,
                ft.Text(
                    "Normal enclosed building or open canopy.",
                    size=11,
                    color=TEXT_MUTED,
                ),
            ],
        ),
    )
    building_roof_field = ft.Container(
        col=6,
        content=ft.Column(
            spacing=2,
            controls=[
                building_roof,
                ft.Text(
                    "Duo-pitched or mono-pitched portal.",
                    size=11,
                    color=TEXT_MUTED,
                ),
            ],
        ),
    )

    pitch_text = ft.Text("", size=22, weight=ft.FontWeight.BOLD, color=ACCENT_DARK)
    frame_summary = ft.Text("", size=12, color=TEXT_MUTED)

    def update_pitch(_=None) -> None:
        try:
            eaves = float(controls["eaves_height_m"].value)
            apex = float(controls["apex_height_m"].value)
            width = float(controls["gable_width_m"].value)
            if structural_system.value == "Truss":
                bays = [
                    float(value.strip())
                    for value in controls["truss_transverse_bay_spans_m"].value.split(",")
                ]
                if not bays or any(value <= 0 for value in bays):
                    raise ValueError
                truss_total_width_text.value = f"{sum(bays):g} m"
                minimum_depth = float(controls["truss_minimum_depth_m"].value)
                maximum_depth = float(controls["truss_maximum_depth_m"].value)
                pitch_text.value = f"{minimum_depth:.2f}–{maximum_depth:.2f} m"
                longest_span = max(bays)
                truss_depth_suggestion.value = (
                    f"Suggested starting depths using the longest transverse span "
                    f"({longest_span:g} m): span/14 = {longest_span / 14:.2f} m; "
                    f"span/18 = {longest_span / 18:.2f} m."
                )
                spacing = float(controls["truss_spacing_m"].value)
                frame_summary.value = (
                    f"{controls['truss_type'].value} • {sum(bays):g} m total width • "
                    f"{len(bays)} span(s) • "
                    f"trusses at {spacing:g} m • purlins define panel points"
                )
                return
            span = width / 2 if building_roof.value == "Duo Pitched" else width
            pitch = math.degrees(math.atan((apex - eaves) / span))
            if width <= 0 or apex <= eaves:
                raise ValueError
            pitch_text.value = f"{pitch:.2f}°"
            spacing = float(controls["rafter_spacing_m"].value)
            length = float(controls["building_length_m"].value)
            bays = math.ceil(length / spacing) if spacing > 0 and length > 0 else 0
            frame_summary.value = f"Calculated automatically • {bays} bay(s) • {bays + 1} portal frame lines"
        except (TypeError, ValueError):
            pitch_text.value = "—"
            frame_summary.value = "Enter valid geometry to calculate pitch and frame quantity."
            if structural_system.value == "Truss":
                truss_total_width_text.value = "—"
                truss_depth_suggestion.value = "Enter valid transverse spans to calculate suggested depths."

    eaves_height = number_field(
        "eaves_height_m", "Eaves height", unit="m", on_change=update_pitch
    )
    apex_height = number_field(
        "apex_height_m",
        "Apex / high-side height",
        unit="m",
        on_change=update_pitch,
    )
    gable_width = number_field(
        "gable_width_m", "Portal span", unit="m", on_change=update_pitch
    )
    rafter_spacing = number_field(
        "rafter_spacing_m", "Portal spacing", unit="m", on_change=update_pitch
    )
    building_length = number_field(
        "building_length_m", "Building length", unit="m", on_change=update_pitch
    )
    truss_bay_spans = text_field(
        "truss_transverse_bay_spans_m",
        "Transverse span lengths",
        helper="Comma-separated in metres, for example 26, 24, 24, 26. Building width and span count are calculated automatically.",
        col={"sm": 12, "md": 9},
    )
    truss_total_width_text = ft.Text(
        "—", size=20, weight=ft.FontWeight.W_600, color=ACCENT_DARK
    )
    truss_total_width = ft.Container(
        col={"sm": 12, "md": 3},
        padding=ft.Padding.only(left=12, top=3),
        content=ft.Column(
            spacing=2,
            controls=[
                ft.Text("Total building width", size=12, color=TEXT_MUTED),
                truss_total_width_text,
            ],
        ),
    )
    truss_building_length = number_field(
        "truss_building_length_m", "Building length", unit="m"
    )
    truss_spacing = number_field(
        "truss_spacing_m", "Truss spacing", unit="m"
    )
    truss_eaves_height = number_field(
        "truss_eaves_height_m", "Eave-column height", unit="m"
    )
    truss_roof_pitch = number_field(
        "truss_roof_pitch_deg", "Roof pitch", unit="°"
    )

    # Design basis and wind controls.
    wind_design_mode = dropdown(
        "wind_design_mode",
        "Internal-pressure design mode",
        WIND_DESIGN_MODES,
        helper="Final design uses the entered wall openings.",
    )
    roof_accessibility = dropdown(
        "roof_accessibility", "Roof accessibility", ROOF_ACCESSIBILITY
    )
    load_standard = dropdown(
        "load_combination_standard",
        "Load-combination standard",
        LOAD_COMBINATION_STANDARDS,
    )
    steel_grade = dropdown("steel_grade", "Steel grade", STEEL_GRADES)
    wind_speed = number_field(
        "fundamental_basic_wind_speed", "Basic wind speed", unit="m/s"
    )
    return_period = number_field(
        "return_period", "Return period", unit="years", integer=True
    )
    terrain = dropdown("terrain_category", "Terrain category", TERRAIN_CATEGORIES)
    topographic = number_field(
        "topographic_factor", "Topographic factor", helper="Dimensionless multiplier."
    )
    altitude = number_field("altitude", "Site altitude", unit="m")
    blocking = number_field(
        "blocking_factor",
        "Canopy blocking factor",
        helper="0 = open below; 1 = fully blocked.",
    )
    opening_side_1 = number_field("opening_side_1_m2", "Side wall 1 openings", unit="m²")
    opening_side_2 = number_field("opening_side_2_m2", "Side wall 2 openings", unit="m²")
    opening_gable_1 = number_field("opening_gable_1_m2", "Gable 1 openings", unit="m²")
    opening_gable_2 = number_field("opening_gable_2_m2", "Gable 2 openings", unit="m²")
    opening_fields = [opening_side_1, opening_side_2, opening_gable_1, opening_gable_2]
    openings_note = ft.Text("", size=12, color=TEXT_MUTED)

    # Frame, bracing and secondary steel controls.
    rafter_section_type = dropdown(
        "rafter_section_type",
        "Rafter section family",
        PORTAL_SECTION_FAMILIES,
        helper="Select the database family used for automatic or manual sizing.",
    )
    rafter_section = dropdown(
        "rafter_section",
        "Rafter section",
        (AUTOMATIC_SECTION,) + PORTAL_SECTIONS_BY_FAMILY["I-Sections"],
        helper="Automatic selects the lightest passing section; otherwise the chosen size is checked.",
        searchable=True,
    )
    column_section_type = dropdown(
        "column_section_type",
        "Column section family",
        PORTAL_SECTION_FAMILIES,
        helper="Select the database family used for automatic or manual sizing.",
    )
    column_section = dropdown(
        "column_section",
        "Column section",
        (AUTOMATIC_SECTION,) + PORTAL_SECTIONS_BY_FAMILY["I-Sections"],
        helper="Automatic selects the lightest passing section; otherwise the chosen size is checked.",
        searchable=True,
    )
    use_eaves_haunch = ft.Switch(
        key="use_eaves_haunch",
        label="Use eaves haunches",
        value=bool(DEFAULT_VALUES["use_eaves_haunch"]),
        active_color=ACCENT,
        col=6,
    )
    controls["use_eaves_haunch"] = use_eaves_haunch
    eaves_haunch_length = number_field(
        "eaves_haunch_length_m",
        "Eaves haunch length",
        unit="m",
        helper="Length along each roof slope from the eaves.",
    )
    eaves_haunch_depth = number_field(
        "eaves_haunch_depth_mm",
        "Maximum eaves haunch depth",
        unit="mm",
        helper="Additional depth below the selected rafter at the eaves.",
    )
    eaves_haunch_fields = ft.ResponsiveRow(
        controls=[eaves_haunch_length, eaves_haunch_depth],
        visible=bool(DEFAULT_VALUES["use_eaves_haunch"]),
    )
    use_apex_haunch = ft.Switch(
        key="use_apex_haunch",
        label="Use apex haunches",
        value=bool(DEFAULT_VALUES["use_apex_haunch"]),
        active_color=ACCENT,
        col=6,
    )
    controls["use_apex_haunch"] = use_apex_haunch
    apex_haunch_length = number_field(
        "apex_haunch_length_m",
        "Apex haunch length per slope",
        unit="m",
        helper="Length from the apex along each adjoining roof slope.",
    )
    apex_haunch_depth = number_field(
        "apex_haunch_depth_mm",
        "Maximum apex haunch depth",
        unit="mm",
        helper="Additional depth below the selected rafter at the apex.",
    )
    apex_haunch_fields = ft.ResponsiveRow(
        controls=[apex_haunch_length, apex_haunch_depth],
        visible=bool(DEFAULT_VALUES["use_apex_haunch"]),
    )

    def sync_portal_section_options() -> None:
        for family_control, section_control in (
            (rafter_section_type, rafter_section),
            (column_section_type, column_section),
        ):
            family = str(family_control.value)
            values = (AUTOMATIC_SECTION,) + PORTAL_SECTIONS_BY_FAMILY.get(
                family, ()
            )
            section_control.options = [
                ft.DropdownOption(
                    key=value,
                    content=ft.Text(value, color=TEXT_PRIMARY),
                )
                for value in values
            ]
            if section_control.value not in values:
                section_control.value = AUTOMATIC_SECTION

    base_support = dropdown(
        "base_support_condition", "Portal base restraint", BASE_SUPPORTS
    )
    spring_stiffness = number_field(
        "base_rotational_stiffness_knm_per_rad",
        "Rotational spring stiffness",
        unit="kN·m/rad",
        helper="Used only when the portal base is Spring.",
    )
    col_bracing_spacing = number_field(
        "col_bracing_spacing",
        "Column bracing intervals",
        helper="Equal vertical intervals per portal column.",
        integer=True,
    )
    column_bracing_type = dropdown(
        "column_bracing_type",
        "Longitudinal wall bracing",
        COLUMN_BRACING_TYPES,
        helper="X uses angles; K and A use CHS.",
    )
    rafter_bracing_spacing = number_field(
        "rafter_bracing_spacing",
        "Roof brace panels per slope",
        helper="Fixed panel count; reduce purlin spacing if more support lines are needed.",
        integer=True,
    )
    gable_column_count = number_field(
        "gable_column_count",
        "Internal gable columns per end",
        helper="Positive odd number: 1, 3, 5, ...",
        integer=True,
    )
    gable_brace_intervals = number_field(
        "gable_column_brace_intervals",
        "Gable-column brace intervals",
        helper="Equal unbraced intervals over each pinned gable column.",
        integer=True,
    )
    purlin_section = dropdown(
        "purlin_section",
        "Purlin section",
        LIPPED_CHANNEL_SECTIONS,
        helper="Lipped Channels database.",
        searchable=True,
    )
    purlin_spacing = number_field(
        "purlin_max_spacing_mm",
        "Maximum purlin spacing",
        unit="mm",
        helper="Must create at least one purlin space per roof-brace panel.",
    )
    girt_section = dropdown(
        "girt_section",
        "Girt section",
        LIPPED_CHANNEL_SECTIONS,
        helper="Lipped Channels database.",
        searchable=True,
    )
    girt_spacing = number_field(
        "girt_max_spacing_mm", "Maximum girt spacing", unit="mm"
    )
    truss_type = dropdown(
        "truss_type", "Truss type", TRUSS_TYPES, col=6
    )
    truss_chord_form = dropdown(
        "truss_chord_form", "Chord form", TRUSS_CHORD_FORMS, col=6
    )
    truss_internal_support = dropdown(
        "truss_internal_support", "Internal support", TRUSS_INTERNAL_SUPPORTS,
        helper="Used only when more than one transverse span is entered.", col=12,
    )
    truss_design_centre_columns = ft.Checkbox(
        key="truss_design_centre_columns",
        label="Design centre columns",
        value=bool(DEFAULT_VALUES["truss_design_centre_columns"]),
        fill_color=ACCENT,
        check_color="#FFFFFF",
    )
    controls["truss_design_centre_columns"] = truss_design_centre_columns
    truss_centre_column_material = dropdown(
        "truss_centre_column_material",
        "Centre-column material",
        TRUSS_CENTRE_COLUMN_MATERIALS,
        helper="Steel is checked axially; concrete tilt-up is captured as a design hold point.",
        col=6,
    )
    truss_centre_column_bracing_spacing = number_field(
        "truss_centre_column_bracing_spacing_m",
        "Centre-column brace spacing",
        unit="m",
        helper="Weak-axis effective length assumption for axial steel columns.",
        col=6,
    )
    truss_centre_column_section_order = dropdown(
        "truss_centre_column_steel_section_order",
        "Steel section order",
        TRUSS_STEEL_SECTION_ORDERS,
        helper="Choose lightest passing or preferred database sections first.",
        col=6,
    )
    truss_centre_column_concrete_width = number_field(
        "truss_centre_column_concrete_width_mm",
        "Tilt-up column width",
        unit="mm",
        col=6,
    )
    truss_centre_column_concrete_thickness = number_field(
        "truss_centre_column_concrete_thickness_mm",
        "Tilt-up column thickness",
        unit="mm",
        col=6,
    )
    truss_centre_column_concrete_bracing_spacing = number_field(
        "truss_centre_column_concrete_bracing_spacing_m",
        "Tilt-up brace/effective length spacing",
        unit="m",
        helper="Captured for the future concrete stability check and erection design.",
        col=6,
    )
    truss_centre_column_concrete_fck = number_field(
        "truss_centre_column_concrete_fck_mpa",
        "Concrete strength fck",
        unit="MPa",
        col=6,
    )
    truss_centre_column_concrete_rebar_area = number_field(
        "truss_centre_column_concrete_rebar_area_mm2",
        "Longitudinal reinforcement area",
        unit="mm²",
        helper="Input only; capacity and detailing remain a hold point until the concrete design basis is confirmed.",
        col=6,
    )
    truss_centre_column_steel_controls = ft.Column(
        controls=[ft.ResponsiveRow(controls=[
            truss_centre_column_bracing_spacing,
            truss_centre_column_section_order,
        ])],
        spacing=12,
    )
    truss_centre_column_concrete_controls = ft.Column(
        controls=[ft.ResponsiveRow(controls=[
            truss_centre_column_concrete_width,
            truss_centre_column_concrete_thickness,
            truss_centre_column_concrete_bracing_spacing,
            truss_centre_column_concrete_fck,
            truss_centre_column_concrete_rebar_area,
        ])],
        spacing=12,
        visible=False,
    )
    truss_centre_column_card = card(
        "Centre-column design",
        "Centre columns always use the internal bearing reactions for axial-only checking. Enable design to include steel column mass and a real section; concrete tilt-up is intentionally reported as a hold point until its design standard and erection basis are confirmed.",
        ft.Column(controls=[
            ft.ResponsiveRow(controls=[truss_design_centre_columns, truss_centre_column_material]),
            truss_centre_column_steel_controls,
            truss_centre_column_concrete_controls,
        ], spacing=12),
    )
    truss_centre_column_card.visible = False
    truss_type_reference = ft.Image(
        src=truss_type_reference_svg(str(DEFAULT_VALUES["truss_type"])),
        fit=ft.BoxFit.CONTAIN,
        width=600,
        height=225,
        semantics_label="Warren, Pratt and Howe truss type reference",
    )
    truss_minimum_depth = number_field(
        "truss_minimum_depth_m", "Minimum truss depth", unit="m"
    )
    truss_maximum_depth = number_field(
        "truss_maximum_depth_m", "Maximum truss depth", unit="m"
    )
    truss_depth_increment = number_field(
        "truss_depth_increment_m", "Depth search increment", unit="m"
    )
    truss_solution_count = number_field(
        "truss_ranked_solution_count", "Ranked solutions", integer=True
    )
    truss_depth_suggestion = ft.Text(
        "Suggested starting depths will be calculated from the entered span(s).",
        size=12,
        color=TEXT_MUTED,
    )
    truss_girder_span_bays = number_field(
        "truss_girder_span_bays", "Girder span", unit="building bays", integer=True
    )
    truss_girder_minimum_depth = number_field(
        "truss_girder_minimum_depth_m", "Minimum girder depth", unit="m"
    )
    truss_girder_maximum_depth = number_field(
        "truss_girder_maximum_depth_m", "Maximum girder depth", unit="m"
    )
    truss_girder_depth_increment = number_field(
        "truss_girder_depth_increment_m", "Girder depth increment", unit="m"
    )
    truss_girder_deflection = number_field(
        "truss_girder_deflection_denominator", "Girder deflection: Span /"
    )
    girder_span_summary = ft.Text("", size=12, color=TEXT_MUTED)
    girder_depth_suggestion = ft.Text(
        "Suggested girder depth will be calculated from the girder span.",
        size=12,
        color=TEXT_MUTED,
    )

    def update_girder_depth_suggestion() -> None:
        try:
            girder_bays = int(float(truss_girder_span_bays.value))
            grid_spacing = float(truss_spacing.value)
            girder_depth_suggestion.value = (
                f"Suggested starting girder depth: span/10 = "
                f"{girder_bays * grid_spacing / 10:.2f} m."
            )
        except (TypeError, ValueError):
            girder_depth_suggestion.value = (
                "Enter valid bay count and truss spacing to calculate the suggested depth."
            )
    truss_top_brace_panels = number_field(
        "truss_top_chord_brace_every_n_purlins", "Top chord: every Nth purlin",
        helper="1 = every purlin, 2 = every second purlin, etc.",
        integer=True,
    )
    truss_bottom_brace_panels = number_field(
        "truss_bottom_chord_brace_every_n_purlins", "Bottom chord: every Nth purlin",
        helper="Restraint is assumed across the entire building length.",
        integer=True,
    )
    truss_deflection_limit = number_field(
        "truss_deflection_denominator", "Vertical deflection: Span /"
    )
    truss_services_load = number_field(
        "truss_services_load_kpa", "Services load", unit="kPa"
    )
    truss_ceiling_load = number_field(
        "truss_ceiling_load_kpa", "Ceiling load", unit="kPa"
    )
    truss_solar_load = number_field(
        "truss_solar_load_kpa", "Solar load", unit="kPa"
    )
    truss_fire_load = number_field(
        "truss_fire_load_kpa", "Fire-services load", unit="kPa"
    )
    truss_hvac_load = number_field(
        "truss_hvac_load_kpa", "HVAC load", unit="kPa"
    )
    use_crawl_beams = ft.Switch(
        key="use_crawl_beams",
        label="Include configured crawl beams",
        value=bool(DEFAULT_VALUES["use_crawl_beams"]),
        active_color=ACCENT,
    )
    controls["use_crawl_beams"] = use_crawl_beams
    crawl_application = dropdown(
        "crawl_application",
        "Crawl load application",
        CRAWL_APPLICATIONS,
        helper="Whether configured crawls act separately or together.",
    )

    crawl_rows: list[dict[str, Any]] = []
    crawl_row_counter = 0
    crawl_editor = ft.Column(spacing=12)
    crawl_editor_hint = ft.Text(
        "No crawl beams added. Select Add crawl beam to define one.",
        size=12,
        color=TEXT_MUTED,
    )

    def crawl_text_field(key: str, label: str, value: str, *, col=6) -> ft.TextField:
        control = ft.TextField(
            key=key,
            label=label,
            value=value,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_MUTED),
            border_color="#93AAA7",
            focused_border_color=ACCENT,
            helper_style=ft.TextStyle(color=TEXT_MUTED, size=11),
            col=col,
            dense=True,
        )
        controls[key] = control
        return control

    def crawl_number_field(
        key: str,
        label: str,
        value: str,
        *,
        unit: str = "",
        col=6,
    ) -> ft.TextField:
        control = ft.TextField(
            key=key,
            label=label,
            value=value,
            keyboard_type=ft.KeyboardType.NUMBER,
            suffix=unit or None,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_MUTED),
            border_color="#93AAA7",
            focused_border_color=ACCENT,
            helper_style=ft.TextStyle(color=TEXT_MUTED, size=11),
            suffix_style=ft.TextStyle(color=TEXT_MUTED),
            col=col,
            dense=True,
        )
        controls[key] = control
        return control

    def crawl_dropdown(
        key: str,
        label: str,
        values: tuple[str, ...],
        value: str,
        *,
        col=6,
        searchable=False,
    ) -> ft.Dropdown:
        control = ft.Dropdown(
            key=key,
            label=label,
            value=value if value in values else values[0],
            options=[
                ft.DropdownOption(key=item, content=ft.Text(item, color=TEXT_PRIMARY))
                for item in values
            ],
            enable_filter=searchable,
            enable_search=True,
            editable=False,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_MUTED),
            border_color="#93AAA7",
            focused_border_color=ACCENT,
            helper_style=ft.TextStyle(color=TEXT_MUTED, size=11),
            menu_style=ft.MenuStyle(bgcolor="#FFFFFF", shadow_color="#607472"),
            col=col,
            dense=True,
        )
        controls[key] = control
        return control

    def refresh_crawl_editor() -> None:
        crawl_editor.controls = []
        if not crawl_rows:
            crawl_editor.controls.append(crawl_editor_hint)
            return
        crawl_editor.controls.extend(row["container"] for row in crawl_rows)

    def add_crawl_beam(_=None) -> None:
        nonlocal crawl_row_counter
        index = crawl_row_counter
        crawl_row_counter += 1
        prefix = f"crawl_{index}"
        default_section = PORTAL_SECTIONS_BY_FAMILY["I-Sections"][0]
        slope_default = "left" if building_roof.value == "Duo Pitched" else "single"
        fields = {
            "name": crawl_text_field(f"{prefix}_name", "Crawl beam name", f"CB{index + 1}"),
            "slope": crawl_dropdown(
                f"{prefix}_slope", "Roof slope", ("left", "right") if building_roof.value == "Duo Pitched" else ("single", "left"), slope_default
            ),
            "position_from_eaves_mm": crawl_number_field(
                f"{prefix}_position_from_eaves_mm", "Position from eaves", "6000", unit="mm"
            ),
            "section_type": crawl_dropdown(
                f"{prefix}_section_type", "Crawl section family", PORTAL_SECTION_FAMILIES, "I-Sections"
            ),
            "section": crawl_dropdown(
                f"{prefix}_section", "Crawl beam section", PORTAL_SECTIONS_BY_FAMILY["I-Sections"], default_section, searchable=True
            ),
            "swl_kg": crawl_number_field(f"{prefix}_swl_kg", "Safe working load", "5000", unit="kg"),
            "hoist_trolley_mass_kg": crawl_number_field(f"{prefix}_hoist_trolley_mass_kg", "Hoist / trolley mass", "350", unit="kg"),
            "lifting_attachment_mass_kg": crawl_number_field(f"{prefix}_lifting_attachment_mass_kg", "Lifting attachment mass", "100", unit="kg"),
            "hoist_class": crawl_dropdown(f"{prefix}_hoist_class", "Hoist class", HOIST_CLASSES, "C2"),
            "hoisting_speed_m_s": crawl_number_field(f"{prefix}_hoisting_speed_m_s", "Hoisting speed", "0.15", unit="m/s"),
        }

        def sync_crawl_section_options(event=None) -> None:
            family = str(fields["section_type"].value)
            values = PORTAL_SECTIONS_BY_FAMILY.get(family, ())
            fields["section"].options = [
                ft.DropdownOption(key=item, content=ft.Text(item, color=TEXT_PRIMARY))
                for item in values
            ]
            if fields["section"].value not in values:
                fields["section"].value = values[0] if values else None
            refresh_workspace()

        fields["section_type"].on_select = sync_crawl_section_options
        for field_name, field in fields.items():
            if field_name == "section_type":
                continue
            if isinstance(field, ft.TextField):
                field.on_change = update_live_input
            elif isinstance(field, ft.Dropdown):
                field.on_select = update_live_input
        row = ft.Container(
            padding=14,
            border=ft.Border.all(1, "#DCE7E5"),
            border_radius=10,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(f"Crawl beam {index + 1}", weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                tooltip="Remove crawl beam",
                                icon_color="#A53D35",
                                on_click=lambda _, row_index=index: remove_crawl_beam(row_index),
                            ),
                        ],
                    ),
                    ft.ResponsiveRow(controls=[fields["name"], fields["slope"], fields["position_from_eaves_mm"]]),
                    ft.ResponsiveRow(controls=[fields["section_type"], fields["section"]]),
                    ft.ResponsiveRow(controls=[fields["swl_kg"], fields["hoist_trolley_mass_kg"], fields["lifting_attachment_mass_kg"]]),
                    ft.ResponsiveRow(controls=[fields["hoist_class"], fields["hoisting_speed_m_s"]]),
                ],
            ),
        )
        crawl_rows.append({"index": index, "fields": fields, "container": row})
        use_crawl_beams.value = True
        refresh_crawl_editor()
        update_conditionals()

    def remove_crawl_beam(index: int) -> None:
        row = next((item for item in crawl_rows if item["index"] == index), None)
        if row is None:
            return
        crawl_rows.remove(row)
        for field in row["fields"].values():
            controls.pop(field.key, None)
        if not crawl_rows:
            use_crawl_beams.value = False
        refresh_crawl_editor()
        update_conditionals()

    add_crawl_beam_button = ft.OutlinedButton(
        "Add crawl beam",
        icon=ft.Icons.ADD,
        on_click=add_crawl_beam,
    )
    refresh_crawl_editor()

    # Foundation design is deliberately post-analysis. These controls are not
    # included in the portal-analysis request fingerprint.
    foundation_standard = dropdown(
        "foundation_standard",
        "Concrete design standard",
        FOUNDATION_STANDARDS,
        col=12,
    )
    foundation_length = number_field(
        "foundation_length_m",
        "Footing length (frame direction)",
        unit="m",
    )
    foundation_width = number_field(
        "foundation_width_m",
        "Footing width (transverse)",
        unit="m",
    )
    foundation_thickness = number_field(
        "foundation_thickness_mm", "Footing thickness", unit="mm"
    )
    foundation_loaded_length = number_field(
        "foundation_loaded_length_mm",
        "Loaded length / pedestal",
        unit="mm",
    )
    foundation_loaded_width = number_field(
        "foundation_loaded_width_mm",
        "Loaded width / pedestal",
        unit="mm",
    )
    foundation_concrete = number_field(
        "foundation_concrete_strength_mpa",
        "Concrete strength",
        unit="MPa",
        helper="Cylinder strength for EC2; cube strength for SANS 10100.",
    )
    foundation_rebar = number_field(
        "foundation_rebar_strength_mpa",
        "Reinforcement yield strength",
        unit="MPa",
    )
    foundation_bar_diameter = number_field(
        "foundation_bar_diameter_mm", "Bottom bar diameter", unit="mm"
    )
    foundation_bar_spacing = number_field(
        "foundation_bar_spacing_mm", "Bottom bar spacing", unit="mm"
    )
    foundation_cover = number_field(
        "foundation_cover_mm", "Nominal bottom cover", unit="mm"
    )
    foundation_bearing = number_field(
        "foundation_permissible_bearing_kpa",
        "Permissible soil bearing pressure",
        unit="kPa",
        helper="Project-specific value confirmed by the geotechnical engineer.",
    )
    foundation_base_depth = number_field(
        "foundation_base_depth_m",
        "Depth to footing base",
        unit="m",
    )
    foundation_soil_weight = number_field(
        "foundation_soil_unit_weight_kn_m3",
        "Soil unit weight",
        unit="kN/m³",
    )
    foundation_friction = number_field(
        "foundation_friction_coefficient",
        "Base friction coefficient",
        helper="Passive soil resistance is omitted.",
    )
    foundation_control_keys = {
        key for key in controls if key.startswith("foundation_")
    }

    api_status_text = ft.Text(
        "API not checked", size=12, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY
    )
    api_status = ft.Container(
        padding=10,
        border_radius=20,
        bgcolor=WARNING_BG,
        content=ft.Row(
            tight=True,
            spacing=7,
            controls=[ft.Icon(ft.Icons.CIRCLE, size=9, color="#C88800"), api_status_text],
        ),
    )

    def check_api(_=None) -> None:
        try:
            response = httpx.get(f"{API_URL}/api/health", timeout=1.5)
            response.raise_for_status()
            api_status_text.value = "API connected"
            api_status.bgcolor = SUCCESS_BG
            api_status.content.controls[0].color = "#1C8C62"
        except (httpx.HTTPError, ValueError):
            api_status_text.value = "API offline"
            api_status.bgcolor = ERROR_BG
            api_status.content.controls[0].color = "#C43D34"
        page.update()

    review_summary = ft.Column(spacing=10)
    json_preview = ft.TextField(
        value="Validate the form to preview the API payload.",
        multiline=True,
        min_lines=12,
        max_lines=18,
        read_only=True,
        text_size=11,
        color=TEXT_PRIMARY,
        bgcolor="#FFFFFF",
        border_color="#93AAA7",
    )
    last_payload: dict[str, Any] | None = None
    submitted_payload_fingerprint: str | None = None
    current_analysis_id: str | None = None

    analysis_status_text = ft.Text(
        "No analysis has been run for these inputs.",
        size=12,
        weight=ft.FontWeight.W_600,
        color=TEXT_PRIMARY,
    )
    analysis_status_icon = ft.Icon(
        ft.Icons.HOURGLASS_TOP, size=18, color="#B87900"
    )
    analysis_progress = ft.ProgressRing(width=18, height=18, stroke_width=2, visible=False)
    analysis_status_card = ft.Container(
        bgcolor=WARNING_BG,
        border_radius=10,
        padding=12,
        content=ft.Row(
            spacing=9,
            controls=[analysis_status_icon, analysis_progress, analysis_status_text],
        ),
    )
    analysis_result_summary = ft.Column(
        spacing=9,
        controls=[
            ft.Text(
                "Run the validated inputs to populate the structural design summary.",
                size=12,
                color=TEXT_MUTED,
            )
        ],
    )
    current_visualisation: dict[str, Any] = {}
    foundation_status_text = ft.Text(
        "Run a portal-frame analysis before designing foundations.",
        size=12,
        weight=ft.FontWeight.W_600,
        color=TEXT_PRIMARY,
    )
    foundation_status_card = ft.Container(
        bgcolor=WARNING_BG,
        border_radius=10,
        padding=12,
        content=ft.Row(
            spacing=9,
            controls=[
                ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color="#B87900"),
                foundation_status_text,
            ],
        ),
    )
    foundation_result_summary = ft.Column(
        spacing=9,
        controls=[
            ft.Text(
                "No foundation design has been run.",
                size=12,
                color=TEXT_MUTED,
            )
        ],
    )

    def show_foundation_results(result: dict[str, Any]) -> None:
        status = str(result.get("status", "FAIL"))
        foundation_status_card.bgcolor = (
            SUCCESS_BG if status == "PASS" else ERROR_BG
        )
        foundation_status_card.content.controls[0].name = (
            ft.Icons.CHECK_CIRCLE
            if status == "PASS"
            else ft.Icons.ERROR_OUTLINE
        )
        foundation_status_card.content.controls[0].color = (
            "#1C8C62" if status == "PASS" else "#C43D34"
        )
        foundation_status_text.value = (
            f"Foundation design {status}. Review every support and the listed hold points."
        )
        derived = result["derived"]
        rows: list[ft.Control] = [
            analysis_summary_line(
                "Design basis",
                f"{result['standard']} | effective depth "
                f"{float(derived['effective_depth_mm']):.0f} mm | "
                f"provided steel {float(derived['provided_steel_mm2_per_m']):.0f} mm²/m",
                ft.Icons.GAVEL,
            ),
            analysis_summary_line(
                "Stabilising permanent weight",
                f"Footing {float(derived['footing_self_weight_kN']):.1f} kN | "
                f"soil cover {float(derived['soil_cover_weight_kN']):.1f} kN",
                ft.Icons.SCALE_OUTLINED,
            ),
        ]
        for support in result.get("supports", []):
            bearing = support["serviceability"]["bearing"]
            sliding = support["serviceability"]["sliding"]
            uplift = support["serviceability"]["uplift"]
            structural = support["structural"]
            governing_check = max(
                structural["checks"],
                key=lambda item: float(item["utilisation"]),
            )
            rows.extend([
                analysis_summary_line(
                    f"Support {support['node']} - {support['status']}",
                    f"Bearing {bearing['status']} {float(bearing['q_max_kpa']):.1f} kPa "
                    f"(util {float(bearing['utilisation']):.3f}, {bearing['contact']} contact) | "
                    f"sliding {sliding['status']} (util {float(sliding['utilisation']):.3f}) | "
                    f"uplift {uplift['status']} ({float(uplift['net_vertical_kN']):.1f} kN net)",
                    ft.Icons.FOUNDATION,
                ),
                analysis_summary_line(
                    f"Support {support['node']} - governing RC check",
                    f"{governing_check['name']} | {structural['combination']} | "
                    f"utilisation {float(governing_check['utilisation']):.3f} | "
                    f"{governing_check['status']}",
                    ft.Icons.FACT_CHECK,
                ),
            ])
        rows.append(
            analysis_summary_line(
                "Engineering hold points",
                "Geotechnical bearing/settlement, anchors and base plate, pedestal/dowels, "
                "development length, exposure detailing, global overturning and adjacent-footing interaction.",
                ft.Icons.REPORT_PROBLEM_OUTLINED,
            )
        )
        foundation_result_summary.controls = rows
        page.update()

    async def run_foundation_design(_=None) -> None:
        if current_analysis_id is None:
            return
        for key in foundation_control_keys:
            control = controls[key]
            if isinstance(control, ft.TextField):
                control.error = None
            elif isinstance(control, ft.Dropdown):
                control.error_text = None
        payload = {
            key: controls[key].value for key in foundation_control_keys
        }
        foundation_design_button.disabled = True
        foundation_design_button.content = "Designing foundations..."
        foundation_status_card.bgcolor = WARNING_BG
        foundation_status_text.value = "Checking service bearing and ULS reinforced concrete design..."
        page.update()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{API_URL}/api/analysis/{current_analysis_id}/foundation",
                    json=payload,
                )
                if response.status_code == 422:
                    detail = response.json().get("detail", {})
                    if isinstance(detail, dict):
                        for key, message in (detail.get("errors") or {}).items():
                            control = controls.get(key)
                            if isinstance(control, ft.TextField):
                                control.error = str(message)
                            elif isinstance(control, ft.Dropdown):
                                control.error_text = str(message)
                    raise ValueError(
                        detail.get("message", "Foundation inputs are invalid.")
                        if isinstance(detail, dict)
                        else str(detail)
                    )
                response.raise_for_status()
                show_foundation_results(response.json())
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            foundation_status_card.bgcolor = ERROR_BG
            foundation_status_card.content.controls[0].name = ft.Icons.ERROR_OUTLINE
            foundation_status_card.content.controls[0].color = "#C43D34"
            foundation_status_text.value = f"Foundation design error: {exc}"
            page.update()
        finally:
            foundation_design_button.disabled = current_analysis_id is None
            foundation_design_button.content = "Design foundations"
            page.update()

    foundation_design_button = ft.FilledButton(
        "Design foundations",
        icon=ft.Icons.FOUNDATION,
        disabled=True,
        on_click=run_foundation_design,
    )
    analysis_view_dropdown = ft.Dropdown(
        label="Engineering view",
        value="Loading",
        options=[
            ft.DropdownOption(
                key="Loading", content=ft.Text("Loading", color=TEXT_PRIMARY)
            ),
            ft.DropdownOption(
                key="Deflection",
                content=ft.Text("Deflection (SLS)", color=TEXT_PRIMARY),
            ),
            ft.DropdownOption(
                key="Internal forces",
                content=ft.Text("Internal forces", color=TEXT_PRIMARY),
            ),
            ft.DropdownOption(
                key="Utilisation",
                content=ft.Text("Utilisation (ULS)", color=TEXT_PRIMARY),
            ),
        ],
        disabled=True,
        width=240,
        color=TEXT_PRIMARY,
        border_color="#93AAA7",
        focused_border_color=ACCENT,
        menu_style=ft.MenuStyle(bgcolor="#FFFFFF", shadow_color="#607472"),
    )

    def set_analysis_view_options(*, truss_deflection_only: bool) -> None:
        option_values = (
            (("Deflection", "Deflection (SLS)"),)
            if truss_deflection_only
            else (
                ("Loading", "Loading"),
                ("Deflection", "Deflection (SLS)"),
                ("Internal forces", "Internal forces"),
                ("Utilisation", "Utilisation (ULS)"),
            )
        )
        analysis_view_dropdown.options = [
            ft.DropdownOption(key=key, content=ft.Text(label, color=TEXT_PRIMARY))
            for key, label in option_values
        ]
        valid_values = {key for key, _ in option_values}
        if analysis_view_dropdown.value not in valid_values:
            analysis_view_dropdown.value = option_values[0][0]
    analysis_component_dropdown = ft.Dropdown(
        label="Component",
        options=[],
        disabled=True,
        visible=False,
        width=240,
        color=TEXT_PRIMARY,
        border_color="#93AAA7",
        focused_border_color=ACCENT,
        menu_style=ft.MenuStyle(bgcolor="#FFFFFF", shadow_color="#607472"),
    )
    load_case_dropdown = ft.Dropdown(
        label="Load combination",
        options=[],
        disabled=True,
        width=420,
        color=TEXT_PRIMARY,
        border_color="#93AAA7",
        focused_border_color=ACCENT,
        menu_style=ft.MenuStyle(bgcolor="#FFFFFF", shadow_color="#607472"),
    )
    load_case_image = ft.Image(
        src="",
        height=420,
        fit=ft.BoxFit.CONTAIN,
        visible=False,
        semantics_label="Portal frame engineering diagram",
    )
    expanded_load_case_image = ft.Image(
        src="",
        width=900,
        height=520,
        fit=ft.BoxFit.CONTAIN,
        semantics_label="Large portal frame engineering diagram",
    )
    expanded_load_case_title = ft.Text("Load combination", size=18, weight=ft.FontWeight.BOLD)
    expanded_load_case_dialog = ft.AlertDialog(
        modal=True,
        title=expanded_load_case_title,
        content=ft.Container(
            width=900,
            height=600,
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                spacing=12,
                controls=[
                    expanded_load_case_image,
                ],
            ),
        ),
        actions=[
            ft.TextButton("Close", on_click=lambda _: page.pop_dialog()),
        ],
    )
    load_case_description = ft.Text(
        "Run the analysis to inspect each ULS and SLS combination.",
        size=11,
        color=TEXT_MUTED,
    )

    def selected_analysis_view() -> tuple[str, str | None]:
        view = str(analysis_view_dropdown.value or "Loading")
        if view == "Deflection":
            return "deflection", str(analysis_component_dropdown.value or "Dy").lower()
        if view == "Internal forces":
            force_components = {
                "Axial force N": "axial",
                "Shear force Vy": "shear",
                "Bending moment Mz": "moment",
            }
            return "forces", force_components.get(
                str(analysis_component_dropdown.value), "moment"
            )
        if view == "Utilisation":
            return "utilisation", None
        return "loads", None

    def selected_combination_kind() -> str | None:
        view, _ = selected_analysis_view()
        if view == "deflection":
            return "SLS"
        if view == "utilisation":
            return "ULS"
        return None

    def refresh_analysis_controls(_=None) -> None:
        view, _ = selected_analysis_view()
        if view == "deflection":
            component_options = (
                ("Dx", "Dx"),
                ("Dy", "Dy"),
                ("Total Deflection", "Total deflection"),
            )
        elif view == "forces":
            component_options = (
                ("Axial force N", "Axial force N"),
                ("Shear force Vy", "Shear force Vy"),
                ("Bending moment Mz", "Bending moment Mz"),
            )
        else:
            component_options = ()

        analysis_component_dropdown.visible = bool(component_options)
        analysis_component_dropdown.disabled = not component_options
        analysis_component_dropdown.options = [
            ft.DropdownOption(
                key=key,
                content=ft.Text(label, color=TEXT_PRIMARY),
            )
            for key, label in component_options
        ]
        component_keys = [key for key, _ in component_options]
        if component_keys and analysis_component_dropdown.value not in component_keys:
            analysis_component_dropdown.value = component_keys[-1]

        names = combination_names(current_visualisation, selected_combination_kind())
        load_case_dropdown.options = [
            ft.DropdownOption(
                key=name,
                content=ft.Text(name, color=TEXT_PRIMARY),
            )
            for name in names
        ]
        if names and load_case_dropdown.value not in names:
            load_case_dropdown.value = names[0]
        if not names:
            load_case_dropdown.value = None
        load_case_dropdown.disabled = not names
        previous_load_case_button.disabled = len(names) < 2
        next_load_case_button.disabled = len(names) < 2
        expand_load_case_button.disabled = not names
        if names:
            update_load_case_view()

    def update_load_case_view(_=None) -> None:
        name = str(load_case_dropdown.value or "")
        if not current_visualisation or not name:
            return
        valid_names = combination_names(
            current_visualisation, selected_combination_kind()
        )
        if name not in valid_names:
            if not valid_names:
                return
            name = valid_names[0]
            load_case_dropdown.value = name
        view, component = selected_analysis_view()
        load_case_image.src = load_case_svg(
            current_visualisation,
            name,
            view=view,
            component=component,
        )
        expanded_load_case_image.src = load_case_image.src
        expanded_load_case_title.value = f"{name} — {analysis_view_dropdown.value}"
        load_case_image.visible = True
        selected = next(
            item
            for item in current_visualisation["combinations"]
            if item["name"] == name
        )
        utilisations = [
            float(member["utilisation"])
            for member in selected.get("members", [])
            if member.get("utilisation") is not None
        ]
        active_loads = sum(
            len(member.get("distributed_loads", []))
            + len(member.get("point_loads", []))
            for member in selected.get("members", [])
        ) + len(selected.get("nodal_loads", []))
        utilisation_text = (
            f"maximum member utilisation {max(utilisations):.3f}"
            if utilisations
            else "strength utilisation not applicable to SLS"
        )
        if view == "loads":
            load_case_description.value = (
                f"{selected.get('kind', '')} • {active_loads} active factored load "
                "entries. Magnitudes, axes and source cases are labelled directly at the arrows."
            )
        elif view == "deflection":
            if current_visualisation.get("structural_system") == "Truss":
                movements = selected.get("node_displacements_mm", {}).values()
                if component == "total deflection":
                    node_maximum = max(
                        (
                            math.hypot(
                                float(movement.get("dx", 0.0)),
                                float(movement.get("dy", 0.0)),
                            )
                            for movement in movements
                        ),
                        default=0.0,
                    )
                    component_label = "total"
                else:
                    movement_key = "dx" if component == "dx" else "dy"
                    node_maximum = max(
                        (
                            abs(float(movement.get(movement_key, 0.0)))
                            for movement in movements
                        ),
                        default=0.0,
                    )
                    component_label = str(component).upper()
            elif component == "total deflection":
                node_maximum = max(
                    (
                        math.hypot(
                            float(node.get("dx_mm", 0.0)),
                            float(node.get("dy_mm", 0.0)),
                        )
                        for node in selected.get("nodes", [])
                    ),
                    default=0.0,
                )
                component_label = "total"
            else:
                component_key = f"{component}_mm"
                node_maximum = max(
                    (
                        abs(float(node.get(component_key, 0.0)))
                        for node in selected.get("nodes", [])
                    ),
                    default=0.0,
                )
                component_label = str(component).upper()
            load_case_description.value = (
                f"SLS • {component_label} nodal and member deflection • "
                f"maximum nodal magnitude {node_maximum:.2f} mm."
            )
        elif view == "forces":
            load_case_description.value = (
                f"{selected.get('kind', '')} • sampled {analysis_component_dropdown.value} "
                "diagram using PyNite local member signs."
            )
        else:
            load_case_description.value = (
                f"ULS • {utilisation_text}."
            )
        page.update()

    def show_large_load_case(_=None) -> None:
        if expanded_load_case_image.src:
            page.show_dialog(expanded_load_case_dialog)

    def step_load_case(offset: int) -> None:
        names = list(
            combination_names(current_visualisation, selected_combination_kind())
        )
        if not names:
            return
        try:
            index = names.index(str(load_case_dropdown.value))
        except ValueError:
            index = 0
        load_case_dropdown.value = names[(index + offset) % len(names)]
        update_load_case_view()

    load_case_dropdown.on_select = update_load_case_view
    analysis_view_dropdown.on_select = refresh_analysis_controls
    analysis_component_dropdown.on_select = update_load_case_view
    previous_load_case_button = ft.IconButton(
        icon=ft.Icons.CHEVRON_LEFT,
        tooltip="Previous load combination",
        disabled=True,
        on_click=lambda _: step_load_case(-1),
    )
    next_load_case_button = ft.IconButton(
        icon=ft.Icons.CHEVRON_RIGHT,
        tooltip="Next load combination",
        disabled=True,
        on_click=lambda _: step_load_case(1),
    )
    expand_load_case_button = ft.OutlinedButton(
        "Open large view",
        icon=ft.Icons.OPEN_IN_FULL,
        disabled=True,
        on_click=show_large_load_case,
    )
    view_report_button = ft.OutlinedButton(
        "View report",
        icon=ft.Icons.DESCRIPTION_OUTLINED,
        disabled=True,
    )
    open_analysis_button = ft.OutlinedButton(
        "Open analysis views",
        icon=ft.Icons.QUERY_STATS,
        disabled=True,
        on_click=lambda _: go_to(5),
    )
    download_markup_button = ft.OutlinedButton(
        "Download markup drawings",
        icon=ft.Icons.ARCHITECTURE,
        disabled=True,
    )

    def clear_errors() -> None:
        for control in controls.values():
            if isinstance(control, ft.TextField):
                control.error = None
            elif isinstance(control, ft.Dropdown):
                control.error_text = None

    def raw_values() -> dict[str, Any]:
        values = {
            key: control.value
            for key, control in controls.items()
        }
        values["crawl_beams"] = [
            {
                field: control.value
                for field, control in row["fields"].items()
            }
            for row in crawl_rows
        ]
        return values

    def set_validation_error(key: str, message: str) -> None:
        control = controls.get(key)
        if control is None and key.startswith("crawl_beams["):
            try:
                index_text, field = key[len("crawl_beams["):].split("].", 1)
                row = crawl_rows[int(index_text)]
                control = row["fields"].get(field)
            except (ValueError, IndexError, KeyError):
                control = None
        if isinstance(control, ft.TextField):
            control.error = message
        elif isinstance(control, ft.Dropdown):
            control.error_text = message

    def summary_line(label: str, value: str, icon) -> ft.Container:
        return ft.Container(
            bgcolor="#F3F8F7",
            border_radius=10,
            padding=12,
            content=ft.Row(
                controls=[
                    ft.Icon(icon, color=ACCENT, size=19),
                    ft.Column(
                        spacing=1,
                        controls=[
                            ft.Text(label, size=11, color=TEXT_MUTED),
                            ft.Text(
                                value,
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color=TEXT_PRIMARY,
                            ),
                        ],
                    ),
                ]
            ),
        )

    preview_status_text = ft.Text(
        "Preparing layout preview...",
        size=11,
        weight=ft.FontWeight.W_600,
        color=TEXT_PRIMARY,
    )
    preview_status = ft.Container(
        padding=10,
        border_radius=10,
        bgcolor=WARNING_BG,
        content=ft.Row(
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color="#B87900"),
                preview_status_text,
            ],
        ),
    )
    frame_preview_image = ft.Image(
        src=frame_elevation_svg(
            build_preview_geometry(build_analysis_payload(dict(DEFAULT_VALUES)))
        ),
        height=205,
        fit=ft.BoxFit.CONTAIN,
        semantics_label="Portal frame section layout preview",
    )
    roof_preview_image = ft.Image(
        src=roof_plan_svg(
            build_preview_geometry(build_analysis_payload(dict(DEFAULT_VALUES)))
        ),
        height=205,
        fit=ft.BoxFit.CONTAIN,
        semantics_label="Roof purlin and bracing plan preview",
    )
    wall_preview_image = ft.Image(
        src=wall_elevation_svg(
            build_preview_geometry(build_analysis_payload(dict(DEFAULT_VALUES)))
        ),
        height=180,
        fit=ft.BoxFit.CONTAIN,
        semantics_label="Longitudinal wall bracing preview",
    )
    preview_description = ft.Text("", size=11, color=TEXT_MUTED)
    live_summary = ft.Column(spacing=9)
    live_validation = ft.Container(
        padding=10,
        border_radius=10,
        bgcolor=SUCCESS_BG,
        content=ft.Row(
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=17, color="#1C8C62"),
                ft.Text(
                    "Inputs ready for preview",
                    size=11,
                    weight=ft.FontWeight.W_600,
                    color=TEXT_PRIMARY,
                    expand=True,
                    max_lines=4,
                ),
            ],
        ),
    )

    def compact_summary_line(label: str, value: str, icon) -> ft.Container:
        return ft.Container(
            padding=10,
            border=ft.Border(bottom=ft.BorderSide(1, "#DCE7E5")),
            content=ft.Row(
                spacing=9,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Icon(icon, color=ACCENT, size=17),
                    ft.Column(
                        spacing=1,
                        expand=True,
                        controls=[
                            ft.Text(label, size=10, color=TEXT_MUTED),
                            ft.Text(
                                value,
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color=TEXT_PRIMARY,
                            ),
                        ],
                    ),
                ],
            ),
        )

    def refresh_workspace(_=None, *, update_page: bool = True) -> None:
        clear_errors()
        try:
            payload = build_analysis_payload(raw_values())
            preview = (
                preview_truss(payload)
                if payload["structural_system"] == "Truss"
                else build_preview_geometry(payload)
            )
        except (InputValidationError, ValueError) as exc:
            error_count = len(exc.errors) if isinstance(exc, InputValidationError) else 1
            if isinstance(exc, InputValidationError):
                for key, message in exc.errors.items():
                    set_validation_error(key, message)
                first_error = next(iter(exc.errors.values()))
            else:
                first_error = str(exc)
            preview_status.bgcolor = WARNING_BG
            preview_status.content.controls[0].color = "#B87900"
            preview_status_text.value = "Showing the last valid layout"
            live_validation.bgcolor = WARNING_BG
            live_validation.content.controls[0].name = ft.Icons.WARNING_AMBER
            live_validation.content.controls[0].color = "#B87900"
            live_validation.content.controls[1].value = (
                f"{error_count} input{'s' if error_count != 1 else ''} need attention: "
                f"{first_error}"
            )
            if update_page:
                page.update()
            return

        building = payload["building_data"]
        wind = payload["wind_data"]
        if payload["structural_system"] == "Truss":
            geometry = preview["geometry"]
            restraint = preview["chord_restraint_layout"]
            frame_preview_image.src = truss_elevation_svg(preview)
            roof_preview_image.src = truss_roof_plan_svg(preview)
            wall_preview_image.src = truss_girder_elevation_svg(preview)
            frame_preview_image.visible = True
            roof_preview_image.visible = True
            wall_preview_image.visible = True
            preview_status.bgcolor = WARNING_BG
            preview_status.content.controls[0].name = ft.Icons.WARNING_AMBER
            preview_status.content.controls[0].color = "#B87900"
            preview_status_text.value = "Generated preliminary truss layout"
            preview_description.value = (
                f"Middle search depth {geometry['depth_mm'] / 1000:g} m; "
                f"{geometry['panel_count']} panels at {geometry['panel_width_mm']:.0f} mm. "
                f"Calculated maximum restraint spacing: top "
                f"{restraint['top_chord']['maximum_spacing_mm'] / 1000:.2f} m, "
                f"bottom {restraint['bottom_chord']['maximum_spacing_mm'] / 1000:.2f} m. "
                f"The plan contains {preview['building_layout']['columns']['eave_count']} main columns and "
                f"{preview['building_layout']['columns']['internal_count']} internal support columns."
            )
            live_validation.bgcolor = WARNING_BG
            live_validation.content.controls[0].name = ft.Icons.WARNING_AMBER
            live_validation.content.controls[0].color = "#B87900"
            live_validation.content.controls[1].value = (
                "Inputs are ready for preliminary optimisation; project-specific engineering validation remains required."
            )
            live_summary.controls = [
                compact_summary_line("Project", payload["project"]["name"], ft.Icons.FOLDER_OUTLINED),
                compact_summary_line(
                    "Structural system",
                    f"{geometry['topology']} • {geometry['chord_form']} • pinned joints",
                    ft.Icons.ACCOUNT_TREE_OUTLINED,
                ),
                compact_summary_line(
                    "Search envelope",
                    f"{payload['truss_data']['minimum_depth_mm'] / 1000:g} to "
                    f"{payload['truss_data']['maximum_depth_mm'] / 1000:g} m • "
                    f"{payload['truss_data']['depth_increment_mm']:.0f} mm increments",
                    ft.Icons.TUNE,
                ),
                compact_summary_line(
                    "Geometry",
                    f"{building['gable_width'] / 1000:g} m span • "
                    f"{building['rafter_spacing'] / 1000:g} m truss spacing • "
                    f"{payload['truss_data']['span_count']} span(s) • "
                    f"purlins/panels ≤ {payload['truss_data']['maximum_panel_width_mm']:.0f} mm",
                    ft.Icons.STRAIGHTEN,
                ),
                compact_summary_line(
                    "Chord restraint",
                    f"Top every {payload['truss_data']['top_chord_brace_every_n_purlins']} purlin(s) • "
                    f"bottom every {payload['truss_data']['bottom_chord_brace_every_n_purlins']} • full length",
                    ft.Icons.SWAP_VERT,
                ),
                compact_summary_line(
                    "Wind inputs",
                    f"{wind['fundamental_basic_wind_speed']:g} m/s • terrain {wind['terrain_category']} • "
                    f"{wind['return_period']} years",
                    ft.Icons.AIR,
                ),
            ]
            if submitted_payload_fingerprint is not None:
                current_fingerprint = json.dumps(payload, sort_keys=True)
                if current_fingerprint != submitted_payload_fingerprint:
                    analysis_status_card.bgcolor = WARNING_BG
                    analysis_status_icon.name = ft.Icons.WARNING_AMBER
                    analysis_status_icon.color = "#B87900"
                    analysis_status_text.value = "Inputs changed after analysis; run again before using outputs."
                    view_report_button.disabled = True
            if update_page:
                page.update()
            return

        frame_preview_image.visible = True
        roof_preview_image.visible = True
        wall_preview_image.visible = True
        counts = preview["counts"]
        layout = preview["roof_layout"]
        frame_preview_image.src = frame_elevation_svg(preview)
        roof_preview_image.src = roof_plan_svg(preview)
        wall_preview_image.src = wall_elevation_svg(preview)
        preview_status.bgcolor = SUCCESS_BG
        preview_status.content.controls[0].name = ft.Icons.VISIBILITY_OUTLINED
        preview_status.content.controls[0].color = "#1C8C62"
        preview_status_text.value = "Live layout preview - no analysis results"
        preview_description.value = (
            f"{counts['purlin_lines']} purlin lines at "
            f"{layout['actual_purlin_spacing_mm']:.0f} mm actual spacing. "
            f"Roof brace panels per slope: "
            f"{' / '.join(str(value) for value in layout['purlin_spaces_per_brace_panel'])} "
            "purlin spaces."
        )
        live_validation.bgcolor = SUCCESS_BG
        live_validation.content.controls[0].name = ft.Icons.CHECK_CIRCLE_OUTLINE
        live_validation.content.controls[0].color = "#1C8C62"
        live_validation.content.controls[1].value = "Inputs ready for preview"
        live_summary.controls = [
            compact_summary_line(
                "Project",
                payload["project"]["name"],
                ft.Icons.FOLDER_OUTLINED,
            ),
            compact_summary_line(
                "Portal dimensions",
                f"{building['gable_width'] / 1000:g} m span | "
                f"{building['eaves_height'] / 1000:g} m eaves | "
                f"{building['apex_height'] / 1000:g} m apex | "
                f"{building['roof_pitch']:.2f} deg",
                ft.Icons.STRAIGHTEN,
            ),
            compact_summary_line(
                "Building arrangement",
                f"{building['building_length'] / 1000:g} m long | "
                f"{building['rafter_spacing'] / 1000:g} m nominal spacing | "
                f"{counts['frame_lines']} frame lines",
                ft.Icons.VIEW_WEEK_OUTLINED,
            ),
            compact_summary_line(
                "Wind inputs",
                f"{wind['fundamental_basic_wind_speed']:g} m/s | terrain "
                f"{wind['terrain_category']} | {wind['return_period']} years | "
                f"{building['wind_design_mode']}",
                ft.Icons.AIR,
            ),
            compact_summary_line(
                "Portal member selection",
                f"Rafter {building['rafter_section']} | "
                f"Column {building['column_section']}",
                ft.Icons.VIEW_WEEK_OUTLINED,
            ),
            compact_summary_line(
                "Rafter haunches",
                " | ".join([
                    (
                        f"Eaves {building['eaves_haunch_length'] / 1000:g} m x "
                        f"{building['eaves_haunch_depth']:.0f} mm"
                        if building["use_eaves_haunch"] == "Yes"
                        else "Eaves none"
                    ),
                    (
                        f"Apex {building['apex_haunch_length'] / 1000:g} m/slope x "
                        f"{building['apex_haunch_depth']:.0f} mm"
                        if building["use_apex_haunch"] == "Yes"
                        else "Apex none"
                    ),
                ]),
                ft.Icons.CALL_MERGE,
            ),
            compact_summary_line(
                "Purlins",
                f"{building['purlin_section']} | {counts['purlin_lines']} lines | "
                f"{layout['actual_purlin_spacing_mm']:.0f} mm actual",
                ft.Icons.HORIZONTAL_RULE,
            ),
            compact_summary_line(
                "Bracing and restraint",
                f"{building['column_bracing_type']}-wall bracing | "
                f"{layout['brace_panels_per_slope']} roof panels/slope | "
                f"{building['base_support_condition']} bases",
                ft.Icons.ACCOUNT_TREE_OUTLINED,
            ),
            compact_summary_line(
                "Gables",
                "Not included for canopy"
                if building["building_type"] == "Canopy"
                else f"{building['gable_column_count']} columns/end | "
                f"{building['gable_column_brace_intervals']} restraint intervals",
                ft.Icons.CELL_TOWER,
            ),
        ]
        if submitted_payload_fingerprint is not None:
            current_fingerprint = json.dumps(payload, sort_keys=True)
            if current_fingerprint != submitted_payload_fingerprint:
                analysis_status_card.bgcolor = WARNING_BG
                analysis_status_icon.name = ft.Icons.WARNING_AMBER
                analysis_status_icon.color = "#B87900"
                analysis_status_text.value = (
                    "Inputs changed after analysis; run again before using downloads."
                )
                view_report_button.disabled = True
                open_analysis_button.disabled = True
                analysis_destination.disabled = True
                foundation_destination.disabled = True
                foundation_design_button.disabled = True
                download_markup_button.disabled = True
                load_case_dropdown.disabled = True
                analysis_view_dropdown.disabled = True
                analysis_component_dropdown.disabled = True
                previous_load_case_button.disabled = True
                next_load_case_button.disabled = True
                expand_load_case_button.disabled = True
                load_case_description.value = (
                    "Inputs changed after analysis; run again before using these results."
                )
                load_case_image.visible = False
        if update_page:
            page.update()

    def analysis_summary_line(label: str, value: str, icon) -> ft.Container:
        return ft.Container(
            bgcolor="#F3F8F7",
            border_radius=9,
            padding=11,
            content=ft.Row(
                spacing=9,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Icon(icon, color=ACCENT, size=18),
                    ft.Column(
                        spacing=1,
                        expand=True,
                        controls=[
                            ft.Text(label, size=10, color=TEXT_MUTED),
                            ft.Text(
                                value,
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color=TEXT_PRIMARY,
                            ),
                        ],
                    ),
                ],
            ),
        )

    def show_analysis_failure(message: str) -> None:
        nonlocal current_analysis_id
        current_analysis_id = None
        analysis_progress.visible = False
        analysis_status_card.bgcolor = ERROR_BG
        analysis_status_icon.visible = True
        analysis_status_icon.name = ft.Icons.ERROR_OUTLINE
        analysis_status_icon.color = "#C43D34"
        analysis_status_text.value = message
        run_analysis_button.disabled = False
        run_analysis_button.content = "Run analysis"
        analysis_destination.disabled = True
        foundation_destination.disabled = True
        foundation_design_button.disabled = True
        page.update()

    def show_analysis_results(result: dict[str, Any]) -> None:
        nonlocal current_visualisation, current_analysis_id
        summary = result["design_summary"]
        if summary.get("structural_system") == "Truss":
            current_analysis_id = None
            foundation_destination.disabled = True
            foundation_design_button.disabled = True
            ranked = list(summary.get("ranked_solutions", []))
            best = ranked[0]
            current_visualisation = dict(
                best.get("load_case_visualisation", {})
            )
            set_analysis_view_options(truss_deflection_only=True)
            analysis_view_dropdown.value = "Deflection"
            ranked_text = " | ".join(
                f"#{item['rank']}: {item['geometry']['depth_mm'] / 1000:g} m, "
                f"{item['arrangement_mass_kg']:,.0f} kg steel, "
                f"{item['practical_cost_equivalent_kg']:,.0f} kg-eq practical, "
                f"util {item['governing_strength']['utilisation']:.3f}"
                for item in ranked
            )
            chord_text = " | ".join(
                f"Span {item['span']} {str(item['role']).replace('_', ' ')}: "
                f"{item['section']} (util {item['governing_utilisation']:.3f})"
                for item in best.get("chord_fabrication_groups", [])
            )
            web_groups = list(best.get("web_fabrication_groups", []))
            web_sections = sorted({
                str(item["section"]) for item in web_groups
            })
            web_text = (
                f"{len(web_groups)} groups using {len(web_sections)} section(s): "
                f"{', '.join(web_sections)}. Minimum group "
                f"{min((item['member_count'] for item in web_groups), default=0)} panels; "
                "smaller sections introduced only below 75% retained utilisation."
            )
            bearing_text = " | ".join(
                f"{item['bearing_node']}: {item['section']['designation']} "
                f"from {item['source']}"
                for item in best.get("bearing_support_verticals", [])
            )
            analysis_result_summary.controls = [
                analysis_summary_line(
                    "Validation status", summary["validation_status"], ft.Icons.WARNING_AMBER
                ),
                analysis_summary_line(
                    "Practical ranked solutions", ranked_text, ft.Icons.FORMAT_LIST_NUMBERED
                ),
                analysis_summary_line(
                    "Lightest-member comparison",
                    f"{best['lightest_member_arrangement_mass_kg']:,.0f} kg with individually "
                    f"optimised webs versus {best['arrangement_mass_kg']:,.0f} kg using "
                    "practical fabrication groups",
                    ft.Icons.SCALE_OUTLINED,
                ),
                analysis_summary_line(
                    "Rank 1 geometry",
                    f"{best['geometry']['topology']} • {best['geometry']['chord_form']} • "
                    f"{best['geometry']['panel_count']} panels at "
                    f"{best['geometry']['panel_width_mm']:.0f} mm • depth "
                    f"{best['geometry']['depth_mm'] / 1000:g} m",
                    ft.Icons.ACCOUNT_TREE_OUTLINED,
                ),
                analysis_summary_line(
                    "Rank 1 chord restraint",
                    f"Top every {best['chord_restraint_layout']['top_chord']['brace_every_n_purlins']} purlin(s) "
                    f"(max {best['chord_restraint_layout']['top_chord']['maximum_spacing_mm'] / 1000:.2f} m) • "
                    f"bottom every {best['chord_restraint_layout']['bottom_chord']['brace_every_n_purlins']} "
                    f"(max {best['chord_restraint_layout']['bottom_chord']['maximum_spacing_mm'] / 1000:.2f} m)",
                    ft.Icons.SWAP_VERT,
                ),
                analysis_summary_line(
                    "Common chord sections by span",
                    chord_text or "No chord groups returned",
                    ft.Icons.HORIZONTAL_RULE,
                ),
                analysis_summary_line(
                    "Practical web groups",
                    web_text or "No ordinary web groups returned",
                    ft.Icons.GRID_VIEW,
                ),
                analysis_summary_line(
                    "Bearing support verticals",
                    bearing_text or "No bearing support verticals returned",
                    ft.Icons.VERTICAL_ALIGN_CENTER,
                ),
                analysis_summary_line(
                    "Rank 1 strength",
                    f"{best['governing_strength']['member']} • "
                    f"{best['governing_strength']['section']} • utilisation "
                    f"{best['governing_strength']['utilisation']:.3f} • "
                    f"{best['governing_strength']['check'].replace('_', ' ')}",
                    ft.Icons.FACT_CHECK,
                ),
                analysis_summary_line(
                    "Rank 1 serviceability",
                    f"{best['serviceability']['maximum_vertical_deflection_mm']:.1f} mm / "
                    f"{best['serviceability']['limit_mm']:.1f} mm "
                    f"({best['serviceability']['governing_combination']})",
                    ft.Icons.SWAP_VERT,
                ),
                analysis_summary_line(
                    "Eave columns",
                    f"{best['eave_column_design']['column_count']} × {best['eave_column_design']['section']} • "
                    f"ULS utilisation {best['eave_column_design']['governing_strength']['utilisation']:.3f} • "
                    f"SLS utilisation {best['eave_column_design']['serviceability']['utilisation']:.3f}",
                    ft.Icons.VIEW_WEEK_OUTLINED,
                ),
                analysis_summary_line(
                    "Longitudinal girder",
                    (
                        "Not required"
                        if best["girder_design"]["status"] == "NOT_REQUIRED"
                        else f"{best['girder_design']['geometry']['span_mm'] / 1000:g} m span • "
                             f"{best['girder_design']['geometry']['depth_mm'] / 1000:g} m lightest depth • "
                             f"utilisation {best['girder_design']['governing_strength']['utilisation']:.3f}"
                    ),
                    ft.Icons.ACCOUNT_TREE_OUTLINED,
                ),
                analysis_summary_line(
                    "Centre columns",
                    (
                        "Not designed; main eave-column section used as a preliminary stiffness proxy"
                        if best.get("centre_column_design", {}).get("status") == "NOT_DESIGNED"
                        else (
                            f"{best['centre_column_design'].get('column_count', 0)} Ã— "
                            f"{best['centre_column_design'].get('section', 'steel section')} â€¢ "
                            f"axial utilisation {best['centre_column_design'].get('governing_strength', {}).get('utilisation', 0):.3f}"
                            if best.get("centre_column_design", {}).get("status") == "PASS"
                            else "Concrete tilt-up inputs captured; concrete capacity is a hold point"
                        )
                    ),
                    ft.Icons.VERTICAL_ALIGN_CENTER,
                ),
                analysis_summary_line(
                    "Exclusions",
                    "Independent validation, connections, restraint capacity and concrete tilt-up capacity/detailing",
                    ft.Icons.REPORT_PROBLEM_OUTLINED,
                ),
            ]
            artifacts = result.get("artifacts", {})
            report = artifacts.get("truss-report-html")
            if report:
                view_report_button.url = ft.Url(
                    url=f"{API_URL}{report['download_url']}", target=ft.UrlTarget.SELF
                )
                view_report_button.disabled = False
            download_markup_button.disabled = True
            all_names = combination_names(current_visualisation, "SLS")
            analysis_view_dropdown.disabled = not all_names
            open_analysis_button.disabled = not all_names
            analysis_destination.disabled = not all_names
            if all_names:
                governing = str(best["serviceability"].get("governing_combination", ""))
                load_case_dropdown.value = (
                    governing if governing in all_names else all_names[0]
                )
                refresh_analysis_controls()
            else:
                load_case_description.value = (
                    "This truss result does not contain SLS displacement data."
                )
            analysis_progress.visible = False
            analysis_status_icon.visible = True
            analysis_status_icon.name = ft.Icons.WARNING_AMBER
            analysis_status_icon.color = "#B87900"
            analysis_status_card.bgcolor = WARNING_BG
            analysis_status_text.value = (
                f"Truss calculation draft {result['analysis_id']} complete; "
                "connections and independent project verification remain outstanding."
            )
            run_analysis_button.disabled = False
            run_analysis_button.content = "Run analysis again"
            page.update()
            return
        set_analysis_view_options(truss_deflection_only=False)
        sections = summary["portal_sections"]
        haunches = summary.get("haunches", {})
        strength = summary["governing_strength"]
        serviceability = summary["serviceability"]
        mass = summary.get("steel_mass_breakdown", {})
        portal_mass = mass.get("portal_frames", {}).get("mass_kg", 0)
        bracing_mass = mass.get("bracing", {}).get("mass_kg", 0)
        gable_mass = mass.get("gable_columns", {}).get("mass_kg", 0)
        purlin_mass = mass.get("purlins", {}).get("mass_kg", 0)
        total_mass = mass.get("total_steel_mass_kg", 0)

        def deflection_text(value, ratio, reference_label: str) -> str:
            try:
                ratio_value = float(ratio)
            except (TypeError, ValueError):
                ratio_value = math.nan
            suffix = (
                f" ({reference_label}/{ratio_value:.0f})"
                if math.isfinite(ratio_value)
                else ""
            )
            return f"{float(value):.2f} mm{suffix}"

        brace_text = ", ".join(
            f"{item['member_type']}: {item['section']} ({float(item['utilisation']):.3f})"
            for item in summary.get("bracing_members", [])
        ) or "No gable or longitudinal bracing design required."
        current_visualisation = dict(
            summary.get("load_case_visualisation", {})
        )

        analysis_result_summary.controls = [
            analysis_summary_line(
                "Member design status",
                f"{strength['status']} | governing utilisation "
                f"{float(strength['utilisation']):.3f}",
                ft.Icons.FACT_CHECK,
            ),
            analysis_summary_line(
                "Selected portal sections",
                f"Rafter {sections['rafter']} | Column {sections['column']}",
                ft.Icons.VIEW_WEEK_OUTLINED,
            ),
            analysis_summary_line(
                "Modelled haunches",
                " | ".join([
                    (
                        f"Eaves {float(haunches.get('eaves', {}).get('length_mm', 0)) / 1000:g} m x "
                        f"{float(haunches.get('eaves', {}).get('depth_mm', 0)):.0f} mm"
                        if haunches.get("eaves", {}).get("used")
                        else "Eaves none"
                    ),
                    (
                        f"Apex {float(haunches.get('apex', {}).get('length_mm', 0)) / 1000:g} m/slope x "
                        f"{float(haunches.get('apex', {}).get('depth_mm', 0)):.0f} mm"
                        if haunches.get("apex", {}).get("used")
                        else "Apex none"
                    ),
                ]),
                ft.Icons.CALL_MERGE,
            ),
            analysis_summary_line(
                "Governing strength check",
                f"{strength['member']} | {strength['combination']} | "
                f"{strength['check']}",
                ft.Icons.QUERY_STATS,
            ),
            analysis_summary_line(
                "Serviceability results",
                f"Horizontal {deflection_text(serviceability['max_horizontal_deflection_mm'], serviceability.get('horizontal_deflection_ratio'), 'Eaves')} | "
                f"Vertical {deflection_text(serviceability['max_vertical_deflection_mm'], serviceability.get('vertical_deflection_ratio'), 'Span')}",
                ft.Icons.SWAP_VERT,
            ),
            analysis_summary_line(
                "Estimated steel mass",
                f"Portal {float(portal_mass):,.1f} kg | Bracing {float(bracing_mass):,.1f} kg | "
                f"Gables {float(gable_mass):,.1f} kg | Purlins {float(purlin_mass):,.1f} kg | "
                f"Total {float(total_mass):,.1f} kg",
                ft.Icons.SCALE_OUTLINED,
            ),
            analysis_summary_line(
                "Bracing members (section and utilisation)",
                brace_text,
                ft.Icons.ACCOUNT_TREE_OUTLINED,
            ),
        ]

        artifacts = result.get("artifacts", {})
        report = artifacts.get("design-report-html")
        markup = artifacts.get("markup-pdf") or artifacts.get("markup-html")
        if report:
            view_report_button.url = ft.Url(
                url=f"{API_URL}{report['download_url']}",
                target=ft.UrlTarget.SELF,
            )
            view_report_button.disabled = False
        if markup:
            download_markup_button.url = f"{API_URL}{markup['download_url']}"
            download_markup_button.disabled = False

        all_names = combination_names(current_visualisation)
        analysis_view_dropdown.disabled = not all_names
        open_analysis_button.disabled = not all_names
        analysis_destination.disabled = not all_names
        current_analysis_id = str(result["analysis_id"])
        foundation_destination.disabled = False
        foundation_design_button.disabled = False
        foundation_status_card.bgcolor = WARNING_BG
        foundation_status_card.content.controls[0].name = ft.Icons.INFO_OUTLINE
        foundation_status_card.content.controls[0].color = "#B87900"
        foundation_status_text.value = (
            "Portal reactions are ready. Confirm the geotechnical and footing "
            "inputs, then run the foundation design."
        )
        if all_names:
            governing = str(strength.get("combination", ""))
            load_case_dropdown.value = (
                governing if governing in all_names else all_names[0]
            )
            refresh_analysis_controls()
        else:
            load_case_description.value = (
                "This analysis snapshot does not contain renderer data."
            )

        analysis_progress.visible = False
        analysis_status_icon.visible = True
        analysis_status_icon.name = ft.Icons.CHECK_CIRCLE
        analysis_status_icon.color = "#1C8C62"
        analysis_status_card.bgcolor = SUCCESS_BG
        analysis_status_text.value = (
            f"Analysis {result['analysis_id']} complete. Review required before use."
        )
        run_analysis_button.disabled = False
        run_analysis_button.content = "Run analysis again"
        page.update()

    async def run_analysis(_=None) -> None:
        nonlocal submitted_payload_fingerprint, current_analysis_id
        if not validate_form() or last_payload is None:
            return

        current_analysis_id = None
        submitted_payload_fingerprint = json.dumps(last_payload, sort_keys=True)
        run_analysis_button.disabled = True
        run_analysis_button.content = "Analysis running..."
        view_report_button.disabled = True
        open_analysis_button.disabled = True
        analysis_destination.disabled = True
        foundation_destination.disabled = True
        foundation_design_button.disabled = True
        download_markup_button.disabled = True
        load_case_dropdown.disabled = True
        analysis_view_dropdown.disabled = True
        analysis_component_dropdown.disabled = True
        previous_load_case_button.disabled = True
        next_load_case_button.disabled = True
        expand_load_case_button.disabled = True
        load_case_image.visible = False
        analysis_status_card.bgcolor = WARNING_BG
        analysis_status_icon.visible = False
        analysis_progress.visible = True
        analysis_status_text.value = "Submitting analysis..."
        page.update()

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(f"{API_URL}/api/analysis", json=last_payload)
                response.raise_for_status()
                job = response.json()
                analysis_id = job["analysis_id"]

                while job["status"] in {"queued", "running"}:
                    analysis_status_text.value = job.get(
                        "message", "Running structural analysis."
                    )
                    page.update()
                    await asyncio.sleep(0.8)
                    status_response = await client.get(
                        f"{API_URL}/api/analysis/{analysis_id}/status"
                    )
                    status_response.raise_for_status()
                    job = status_response.json()

                if job["status"] == "failed":
                    show_analysis_failure(job.get("error", "Analysis failed."))
                    return

                result_response = await client.get(
                    f"{API_URL}/api/analysis/{analysis_id}/results"
                )
                result_response.raise_for_status()
                show_analysis_results(result_response.json())
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            show_analysis_failure(f"Analysis API error: {exc}")

    run_analysis_button = ft.FilledButton(
        "Run analysis",
        icon=ft.Icons.PLAY_ARROW,
        on_click=run_analysis,
        tooltip="Runs analysis with PyNite deformation rendering disabled.",
    )

    def validate_form(_=None) -> bool:
        nonlocal last_payload
        clear_errors()
        try:
            payload = build_analysis_payload(raw_values())
        except InputValidationError as exc:
            for key, message in exc.errors.items():
                set_validation_error(key, message)
            last_payload = None
            page.show_dialog(
                ft.SnackBar(
                    ft.Text(
                        f"Please correct {len(exc.errors)} highlighted input(s).",
                        color="#FFFFFF",
                    ),
                    bgcolor="#A92F28",
                    show_close_icon=True,
                    close_icon_color="#FFFFFF",
                )
            )
            page.update()
            return False

        last_payload = payload
        building = payload["building_data"]
        wind = payload["wind_data"]
        refresh_workspace(update_page=False)
        review_summary.controls = [
            summary_line(
                "Building",
                f"{building['building_type']} • {building['building_roof']}",
                ft.Icons.HOME_WORK,
            ),
            summary_line(
                "Geometry",
                f"{building['gable_width'] / 1000:g} m span • {building['building_length'] / 1000:g} m long • {building['roof_pitch']:.2f}°",
                ft.Icons.STRAIGHTEN,
            ),
            summary_line(
                "Design basis",
                f"{building['steel_grade']} • {building['load_combination_standard']}",
                ft.Icons.GAVEL,
            ),
            summary_line(
                "Wind",
                f"{wind['fundamental_basic_wind_speed']:g} m/s • terrain {wind['terrain_category']} • {wind['return_period']} years",
                ft.Icons.WIND_POWER,
            ),
            summary_line(
                "Portal sections",
                f"Rafter {building['rafter_section']} • Column {building['column_section']}",
                ft.Icons.VIEW_WEEK_OUTLINED,
            ),
            summary_line(
                "Haunches",
                " | ".join([
                    (
                        f"Eaves {building['eaves_haunch_length'] / 1000:g} m x "
                        f"{building['eaves_haunch_depth']:.0f} mm"
                        if building["use_eaves_haunch"] == "Yes"
                        else "Eaves none"
                    ),
                    (
                        f"Apex {building['apex_haunch_length'] / 1000:g} m/slope x "
                        f"{building['apex_haunch_depth']:.0f} mm"
                        if building["use_apex_haunch"] == "Yes"
                        else "Apex none"
                    ),
                ]),
                ft.Icons.CALL_MERGE,
            ),
            summary_line(
                "Bracing",
                f"{building['column_bracing_type']}-bracing • {building['gable_column_count']} gable columns/end",
                ft.Icons.CALL_SPLIT,
            ),
        ]
        if payload["structural_system"] == "Truss":
            truss = payload["truss_data"]
            extra_load = sum(
                truss[key] for key in (
                    "services_load_kpa", "ceiling_load_kpa", "solar_load_kpa",
                    "fire_load_kpa", "hvac_load_kpa",
                )
            )
            review_summary.controls = [
                summary_line(
                    "System",
                    f"{truss['topology']} • {truss['chord_form']} • {building['building_roof']}",
                    ft.Icons.ACCOUNT_TREE_OUTLINED,
                ),
                summary_line(
                    "Geometry search",
                    f"{building['gable_width'] / 1000:g} m width • {truss['span_count']} span(s) • "
                    f"{truss['minimum_depth_mm'] / 1000:g} to {truss['maximum_depth_mm'] / 1000:g} m depth",
                    ft.Icons.STRAIGHTEN,
                ),
                summary_line(
                    "Supports",
                    (
                        "Main column left • Main column right"
                        if truss["span_count"] == 1
                        else f"Main column left • {truss['internal_support']} • Main column right"
                    ),
                    ft.Icons.VIEW_WEEK_OUTLINED,
                ),
                summary_line(
                    "Sections",
                    "Common chords per span • independent web angles • minimum 50x50x5 • S355JR",
                    ft.Icons.VIEW_WEEK_OUTLINED,
                ),
                summary_line(
                    "Loads",
                    f"PortalFrame environmental actions + {extra_load:g} kPa additional permanent load",
                    ft.Icons.WIND_POWER,
                ),
                summary_line(
                    "Hold point", "Project-specific validation and SANS editions pending",
                    ft.Icons.WARNING_AMBER,
                ),
            ]
        json_preview.value = json.dumps(payload, indent=2)
        page.update()
        return True

    def entered_truss_span_count() -> int:
        return len([
            value for value in str(truss_bay_spans.value).split(",")
            if value.strip()
        ])

    def update_conditionals(_=None) -> None:
        sync_portal_section_options()
        is_truss = structural_system.value == "Truss"
        if is_truss:
            building_type.value = "Normal"
            steel_grade.value = "Steel_S355"
        building_type.disabled = is_truss
        building_roof.disabled = False
        steel_grade.disabled = is_truss
        portal_system_controls.visible = not is_truss
        truss_system_controls.visible = is_truss
        portal_dimensions.visible = not is_truss
        truss_dimensions.visible = is_truss
        truss_additional_loads_card.visible = is_truss
        apex_height.disabled = is_truss
        span_count = entered_truss_span_count()
        has_internal_support = is_truss and span_count > 1
        truss_internal_support.disabled = not has_internal_support
        uses_girder = (
            has_internal_support
            and truss_internal_support.value == "Longitudinal girders"
        )
        truss_girder_card.visible = uses_girder
        uses_centre_columns = (
            has_internal_support
            and truss_internal_support.value == "Centre columns"
        )
        truss_centre_column_card.visible = uses_centre_columns
        centre_design_enabled = uses_centre_columns and bool(
            truss_design_centre_columns.value
        )
        truss_centre_column_material.disabled = not centre_design_enabled
        is_concrete_centre = (
            centre_design_enabled
            and truss_centre_column_material.value == "Concrete tilt-up"
        )
        truss_centre_column_steel_controls.visible = (
            centre_design_enabled and not is_concrete_centre
        )
        truss_centre_column_concrete_controls.visible = is_concrete_centre
        try:
            girder_bays = int(float(truss_girder_span_bays.value))
            grid_spacing = float(truss_spacing.value)
            girder_span_summary.value = (
                f"Calculated girder span: {girder_bays} bays × "
                f"{grid_spacing:g} m = {girder_bays * grid_spacing:g} m."
            )
        except (TypeError, ValueError):
            girder_span_summary.value = "Enter valid bay count and truss spacing."
        truss_type_reference.src = truss_type_reference_svg(str(truss_type.value))
        update_girder_depth_suggestion()
        is_canopy = building_type.value == "Canopy"
        is_final_normal = not is_canopy and wind_design_mode.value == "Final design"
        blocking.disabled = not is_canopy
        wind_design_mode.disabled = is_canopy
        for field in opening_fields:
            field.disabled = not is_final_normal
        openings_note.value = (
            "Opening areas are active because Final design resolves internal pressure from wall openings."
            if is_final_normal
            else "Opening areas are only used for a normal building in Final design mode."
        )
        spring_stiffness.disabled = base_support.value != "Spring"
        use_eaves_haunch.disabled = is_truss
        use_apex_haunch.disabled = is_truss
        eaves_haunch_fields.visible = (
            not is_truss and bool(use_eaves_haunch.value)
        )
        apex_haunch_fields.visible = (
            not is_truss and bool(use_apex_haunch.value)
        )
        gable_column_count.disabled = is_canopy
        gable_brace_intervals.disabled = is_canopy
        crawl_application.disabled = is_truss or not use_crawl_beams.value
        crawl_slope_values = (
            ("left", "right") if building_roof.value == "Duo Pitched" else ("single", "left")
        )
        for row in crawl_rows:
            slope_control = row["fields"]["slope"]
            slope_control.options = [
                ft.DropdownOption(key=value, content=ft.Text(value, color=TEXT_PRIMARY))
                for value in crawl_slope_values
            ]
            if slope_control.value not in crawl_slope_values:
                slope_control.value = crawl_slope_values[0]
        update_pitch()
        refresh_workspace(update_page=False)
        page.update()

    building_type.on_select = update_conditionals
    building_roof.on_select = update_conditionals
    structural_system.on_select = update_conditionals
    wind_design_mode.on_select = update_conditionals
    base_support.on_select = update_conditionals
    use_eaves_haunch.on_change = update_conditionals
    use_apex_haunch.on_change = update_conditionals
    use_crawl_beams.on_change = update_conditionals
    truss_internal_support.on_select = update_conditionals
    truss_design_centre_columns.on_change = update_conditionals
    truss_centre_column_material.on_select = update_conditionals

    def update_live_input(_=None) -> None:
        if structural_system.value == "Truss":
            span_count = entered_truss_span_count()
            truss_internal_support.disabled = span_count <= 1
            truss_girder_card.visible = (
                span_count > 1
                and truss_internal_support.value == "Longitudinal girders"
            )
            truss_centre_column_card.visible = (
                span_count > 1
                and truss_internal_support.value == "Centre columns"
            )
            centre_design_enabled = (
                truss_centre_column_card.visible
                and bool(truss_design_centre_columns.value)
            )
            is_concrete_centre = (
                centre_design_enabled
                and truss_centre_column_material.value == "Concrete tilt-up"
            )
            truss_centre_column_material.disabled = not centre_design_enabled
            truss_centre_column_steel_controls.visible = (
                centre_design_enabled and not is_concrete_centre
            )
            truss_centre_column_concrete_controls.visible = is_concrete_centre
            try:
                girder_bays = int(float(truss_girder_span_bays.value))
                grid_spacing = float(truss_spacing.value)
                girder_span_summary.value = (
                    f"Calculated girder span: {girder_bays} bays × "
                    f"{grid_spacing:g} m = {girder_bays * grid_spacing:g} m."
                )
            except (TypeError, ValueError):
                girder_span_summary.value = "Enter valid bay count and truss spacing."
            truss_type_reference.src = truss_type_reference_svg(str(truss_type.value))
            update_girder_depth_suggestion()
        update_pitch()
        refresh_workspace()

    conditional_dropdowns = {
        building_type,
        building_roof,
        structural_system,
        wind_design_mode,
        base_support,
        rafter_section_type,
        column_section_type,
        truss_internal_support,
        truss_centre_column_material,
    }
    for control_key, live_control in controls.items():
        if control_key in foundation_control_keys:
            continue
        if isinstance(live_control, ft.TextField):
            live_control.on_change = update_live_input
        elif isinstance(live_control, ft.Dropdown) and live_control not in conditional_dropdowns:
            live_control.on_select = update_live_input

    def footer_buttons(previous: int | None, next_index: int | None) -> ft.Row:
        buttons: list[ft.Control] = []
        if previous is not None:
            buttons.append(
                ft.OutlinedButton(
                    "Back", icon=ft.Icons.ARROW_BACK, on_click=lambda _: go_to(previous)
                )
            )
        if next_index is not None:
            buttons.append(
                ft.FilledButton(
                    "Continue",
                    icon=ft.Icons.ARROW_FORWARD,
                    on_click=lambda _: go_to(next_index),
                )
            )
        return ft.Row(alignment=ft.MainAxisAlignment.END, controls=buttons)

    secondary_steel_card = card(
        "Purlins and girts",
        "Portal purlins follow the roof layout; truss purlins coincide with calculated vertical panel points. Sections come from the lipped-channel database.",
        ft.ResponsiveRow(controls=[
            purlin_section, purlin_spacing, girt_section, girt_spacing
        ]),
    )
    portal_system_controls = ft.Column(
        spacing=18,
        controls=[
            card(
                "Portal member sections",
                "Choose automatic mass-ordered sizing or force a database section for checking.",
                ft.ResponsiveRow(controls=[
                    rafter_section_type, rafter_section,
                    column_section_type, column_section,
                ]),
            ),
            card(
                "Rafter haunches",
                "Haunches are cut from the selected rafter. The tapered composite "
                "stiffness is discretised internally; welds and connection detailing "
                "remain separate design checks.",
                ft.Column(
                    spacing=10,
                    controls=[
                        ft.ResponsiveRow(
                            controls=[use_eaves_haunch, use_apex_haunch]
                        ),
                        eaves_haunch_fields,
                        apex_haunch_fields,
                    ],
                ),
            ),
            card(
                "Portal support and bracing",
                "Integer fields represent counts of modelled intervals or panels.",
                ft.ResponsiveRow(controls=[
                    base_support, spring_stiffness, col_bracing_spacing,
                    column_bracing_type, rafter_bracing_spacing,
                ]),
            ),
            card(
                "Gable columns",
                "Gables are pinned; the brace interval count controls their unbraced length.",
                ft.ResponsiveRow(controls=[gable_column_count, gable_brace_intervals]),
            ),
            card(
                "Crawl beam loading",
                "Add each crawl beam, its roof position and hoist data.",
                ft.Column(spacing=12, controls=[
                    ft.ResponsiveRow(controls=[use_crawl_beams, crawl_application]),
                    ft.Row(controls=[add_crawl_beam_button]),
                    crawl_editor,
                ]),
            ),
        ],
    )
    truss_additional_loads_card = card(
        "Additional permanent roof actions",
        "Enter project-specific characteristic area loads. Zero means the action is excluded.",
        ft.ResponsiveRow(controls=[
            truss_services_load, truss_ceiling_load, truss_solar_load,
            truss_fire_load, truss_hvac_load,
        ]),
    )
    truss_additional_loads_card.visible = False

    truss_system_controls = ft.Column(
        spacing=18,
        visible=False,
        controls=[
            card(
                "Truss form",
                "Choose the web arrangement and chord geometry; the diagrams show the diagonal directions used by the model.",
                ft.Column(controls=[
                    ft.ResponsiveRow(controls=[
                        truss_type, truss_chord_form, truss_internal_support,
                    ]),
                    truss_type_reference,
                ]),
            ),
            truss_centre_column_card,
            card(
                "Truss depth search",
                "Every depth within the limits is designed; passing arrangements are ranked by total modelled mass.",
                ft.Column(controls=[
                    truss_depth_suggestion,
                    ft.ResponsiveRow(controls=[
                        truss_minimum_depth, truss_maximum_depth,
                        truss_depth_increment, truss_solution_count,
                    ]),
                ]),
            ),
            truss_girder_card := card(
                "Longitudinal girder search",
                "Column positions and girder length are calculated from the selected number of building bays.",
                ft.Column(controls=[
                    girder_span_summary,
                    girder_depth_suggestion,
                    ft.ResponsiveRow(controls=[
                        truss_girder_span_bays,
                        truss_girder_minimum_depth,
                        truss_girder_maximum_depth,
                        truss_girder_depth_increment,
                        truss_girder_deflection,
                    ]),
                ]),
            ),
            card(
                "Chord restraint and serviceability",
                "Restraint is assumed across the full building length at every selected Nth purlin; vertical truss deflection defaults to Span/180.",
                ft.ResponsiveRow(controls=[
                    truss_top_brace_panels, truss_bottom_brace_panels,
                    truss_deflection_limit,
                ]),
            ),
            ft.Container(
                bgcolor=ERROR_BG,
                border_radius=10,
                padding=14,
                content=ft.Text(
                    "CALCULATION SCOPE: member forces, axial resistance, slenderness and vertical deflection are calculated. Gussets, bolts, welds, bearings and restraint-member capacity still require separate design and an independent project check.",
                    color="#9C3C16", weight=ft.FontWeight.BOLD,
                ),
            ),
        ],
    )

    sections: list[ft.Control] = [
        ft.Column(
            spacing=18,
            controls=[
                section_heading(
                    "Project setup",
                    "Identify the job and select the overall building configuration.",
                ),
                card(
                    "Project details",
                    "Administrative information carried with the design.",
                    ft.ResponsiveRow(controls=[project_name, project_number, designer]),
                ),
                card(
                    "Building configuration",
                    "These are finite model choices, so they are controlled selections.",
                    ft.Column(controls=[
                        ft.ResponsiveRow(controls=[structural_system]),
                        ft.ResponsiveRow(controls=[building_type_field, building_roof_field]),
                    ]),
                ),
                footer_buttons(None, 1),
            ],
        ),
        ft.Column(
            spacing=18,
            controls=[
                section_heading(
                    "Geometry",
                    "Enter measured dimensions in metres; the analysis payload converts them to millimetres.",
                ),
                portal_dimensions := card(
                    "Portal dimensions",
                    "Apex/high-side height must be greater than eaves height.",
                    ft.ResponsiveRow(
                        controls=[
                            eaves_height,
                            apex_height,
                            gable_width,
                            rafter_spacing,
                            building_length,
                            ft.Container(
                                col={"sm": 12, "md": 6},
                                bgcolor="#EAF4F3",
                                border_radius=12,
                                padding=16,
                                content=ft.Column(
                                    spacing=3,
                                    controls=[
                                        ft.Text("Calculated roof pitch", size=12, color=TEXT_MUTED),
                                        pitch_text,
                                        frame_summary,
                                    ],
                                ),
                            ),
                        ]
                    ),
                ),
                truss_dimensions := card(
                    "Truss building geometry",
                    "Enter each transverse span length; their count and total establish the span arrangement and building width.",
                    ft.ResponsiveRow(controls=[
                        truss_bay_spans, truss_total_width, truss_building_length,
                        truss_spacing, truss_eaves_height, truss_roof_pitch,
                    ]),
                ),
                footer_buttons(0, 2),
            ],
        ),
        ft.Column(
            spacing=18,
            controls=[
                section_heading(
                    "Design and Loading",
                    "Select the design basis and enter the loading inputs shared by portal-frame and truss buildings.",
                ),
                card(
                    "Design basis",
                    "Selections map directly to implemented calculation branches.",
                    ft.ResponsiveRow(
                        controls=[wind_design_mode, roof_accessibility, load_standard, steel_grade]
                    ),
                ),
                card(
                    "Wind site data",
                    "Confirm these values against the project design basis.",
                    ft.ResponsiveRow(
                        controls=[
                            wind_speed,
                            return_period,
                            terrain,
                            topographic,
                            altitude,
                            blocking,
                        ]
                    ),
                ),
                truss_additional_loads_card,
                card(
                    "Wall openings",
                    "Used to resolve internal pressure for a normal building in Final design mode.",
                    ft.Column(
                        controls=[
                            openings_note,
                            ft.ResponsiveRow(controls=opening_fields),
                        ]
                    ),
                ),
                footer_buttons(1, 3),
            ],
        ),
        ft.Column(
            spacing=18,
            controls=[
                section_heading(
                    "Structural system design",
                    "Configure the selected portal-frame or preliminary truss design workflow.",
                ),
                secondary_steel_card,
                portal_system_controls,
                truss_system_controls,
                footer_buttons(2, 4),
            ],
        ),
        ft.Column(
            spacing=18,
            controls=[
                section_heading(
                    "Review",
                    "Validate every field and inspect the exact payload before analysis.",
                ),
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(
                            col={"sm": 12, "lg": 5},
                            content=card(
                                "Validated input summary",
                                "This describes the model inputs before analysis.",
                                review_summary,
                            ),
                        ),
                        ft.Container(
                            col={"sm": 12, "lg": 7},
                            content=card(
                                "API payload preview",
                                "Display units have been converted to the engine's expected units.",
                                json_preview,
                            ),
                        ),
                    ]
                ),
                card(
                    "Structural design summary",
                    "Populated from the completed analysis snapshot; serviceability results are available in the SLS analysis views.",
                    ft.Column(
                        spacing=12,
                        controls=[
                            analysis_status_card,
                            analysis_result_summary,
                            ft.Row(
                                wrap=True,
                                controls=[
                                    view_report_button,
                                    open_analysis_button,
                                    download_markup_button,
                                ],
                            ),
                            ft.Text(
                                "Generated outputs require review by the responsible competent engineer.",
                                size=10,
                                color=TEXT_MUTED,
                            ),
                        ],
                    ),
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    wrap=True,
                    controls=[
                        ft.OutlinedButton(
                            "Back", icon=ft.Icons.ARROW_BACK, on_click=lambda _: go_to(3)
                        ),
                        ft.FilledButton(
                            "Validate inputs",
                            icon=ft.Icons.CHECK_CIRCLE,
                            on_click=validate_form,
                        ),
                        run_analysis_button,
                    ],
                ),
            ],
        ),
        ft.Column(
            spacing=18,
            controls=[
                section_heading(
                    "Analysis views",
                    "Inspect loading, SLS deflection, internal forces and ULS utilisation independently.",
                ),
                card(
                    "Load combination",
                    "Select a ULS or SLS combination and the engineering information to display.",
                    ft.Column(
                        spacing=10,
                        controls=[
                            ft.Row(
                                wrap=True,
                                controls=[
                                    analysis_view_dropdown,
                                    analysis_component_dropdown,
                                    previous_load_case_button,
                                    load_case_dropdown,
                                    next_load_case_button,
                                ],
                            ),
                            load_case_description,
                        ],
                    ),
                ),
                card(
                    "Structural model",
                    "The selected engineering quantity is labelled directly on the portal-frame or truss diagram.",
                    ft.Column(
                        spacing=10,
                        controls=[
                            ft.Container(
                                bgcolor="#F8FBFA",
                                border_radius=12,
                                border=ft.Border.all(1, "#D8E5E3"),
                                padding=8,
                                content=load_case_image,
                            ),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.END,
                                controls=[expand_load_case_button],
                            ),
                        ],
                    ),
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.OutlinedButton(
                            "Back to review",
                            icon=ft.Icons.ARROW_BACK,
                            on_click=lambda _: go_to(4),
                        ),
                    ],
                ),
            ],
        ),
        ft.Column(
            spacing=18,
            controls=[
                section_heading(
                    "Foundation design",
                    "Design identical isolated pads from the completed portal-frame "
                    "support reactions.",
                ),
                foundation_status_card,
                card(
                    "Design basis and soil",
                    "The permissible bearing pressure is a project-specific "
                    "geotechnical input. SANS 10161 is not used to infer a soil value.",
                    ft.Column(
                        spacing=10,
                        controls=[
                            ft.ResponsiveRow(controls=[foundation_standard]),
                            ft.ResponsiveRow(
                                controls=[
                                    foundation_bearing,
                                    foundation_base_depth,
                                    foundation_soil_weight,
                                    foundation_friction,
                                ]
                            ),
                        ],
                    ),
                ),
                card(
                    "Pad geometry and materials",
                    "The loaded area represents the centred pedestal or base-transfer area.",
                    ft.Column(
                        spacing=10,
                        controls=[
                            ft.ResponsiveRow(
                                controls=[
                                    foundation_length,
                                    foundation_width,
                                    foundation_thickness,
                                    foundation_loaded_length,
                                    foundation_loaded_width,
                                ]
                            ),
                            ft.ResponsiveRow(
                                controls=[
                                    foundation_concrete,
                                    foundation_rebar,
                                    foundation_bar_diameter,
                                    foundation_bar_spacing,
                                    foundation_cover,
                                ]
                            ),
                        ],
                    ),
                ),
                card(
                    "Foundation results",
                    "Service bearing, sliding and uplift are separated from ULS "
                    "flexure, one-way shear and punching shear.",
                    foundation_result_summary,
                ),
                ft.Container(
                    bgcolor=WARNING_BG,
                    border_radius=10,
                    padding=14,
                    content=ft.Text(
                        "HOLD POINTS: geotechnical bearing and settlement, anchors/base "
                        "plate, pedestal and dowels, development length, exposure "
                        "detailing, global overturning and adjacent-foundation interaction "
                        "require separate project checks.",
                        color="#745B2B",
                        weight=ft.FontWeight.BOLD,
                    ),
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    wrap=True,
                    controls=[
                        ft.OutlinedButton(
                            "Back to analysis",
                            icon=ft.Icons.ARROW_BACK,
                            on_click=lambda _: go_to(5),
                        ),
                        foundation_design_button,
                    ],
                ),
            ],
        ),
    ]

    content_host = ft.Column(
        controls=[sections[0]],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    def preview_block(image: ft.Image) -> ft.Container:
        return ft.Container(
            bgcolor="#FFFFFF",
            border_radius=12,
            padding=8,
            border=ft.Border.all(1, "#D8E5E3"),
            content=image,
        )

    visual_builder = ft.Container(
        width=380,
        bgcolor="#EDF4F3",
        padding=16,
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
            controls=[
                ft.Column(
                    spacing=2,
                    controls=[
                        ft.Text(
                            "Live structural layout",
                            size=17,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT_PRIMARY,
                        ),
                        ft.Text(
                            "Frame, secondary steel and stability arrangement",
                            size=11,
                            color=TEXT_MUTED,
                        ),
                    ],
                ),
                preview_status,
                preview_block(frame_preview_image),
                preview_block(roof_preview_image),
                preview_block(wall_preview_image),
                ft.Container(
                    bgcolor=WARNING_BG,
                    border_radius=10,
                    padding=12,
                    content=ft.Column(
                        spacing=5,
                        controls=[
                            ft.Text(
                                "LAYOUT PREVIEW ONLY",
                                size=10,
                                weight=ft.FontWeight.BOLD,
                                color="#8A5A00",
                            ),
                            preview_description,
                            ft.Text(
                                "Member adequacy, design actions and analysis results are not shown.",
                                size=10,
                                color="#745B2B",
                            ),
                        ],
                    ),
                ),
            ],
        ),
    )

    running_summary_panel = ft.Container(
        width=280,
        bgcolor="#FFFFFF",
        padding=16,
        border=ft.Border(left=ft.BorderSide(1, "#D8E5E3")),
        content=ft.Column(
            scroll=ft.ScrollMode.AUTO,
            spacing=10,
            controls=[
                ft.Column(
                    spacing=2,
                    controls=[
                        ft.Text(
                            "Running summary",
                            size=17,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT_PRIMARY,
                        ),
                        ft.Text(
                            "Updates as project inputs change",
                            size=11,
                            color=TEXT_MUTED,
                        ),
                    ],
                ),
                live_validation,
                live_summary,
                ft.Container(
                    bgcolor="#F3F8F7",
                    border_radius=10,
                    padding=11,
                    content=ft.Text(
                        "Values shown here are inputs and layout quantities, not verified analysis results.",
                        size=10,
                        color=TEXT_MUTED,
                    ),
                ),
            ],
        ),
    )

    analysis_destination = ft.NavigationRailDestination(
        icon=ft.Icon(ft.Icons.QUERY_STATS_OUTLINED, color="#506A67"),
        selected_icon=ft.Icon(ft.Icons.QUERY_STATS, color=ACCENT_DARK),
        label="Analysis",
        disabled=True,
    )
    foundation_destination = ft.NavigationRailDestination(
        icon=ft.Icon(ft.Icons.FOUNDATION_OUTLINED, color="#506A67"),
        selected_icon=ft.Icon(ft.Icons.FOUNDATION, color=ACCENT_DARK),
        label="Foundations",
        disabled=True,
    )

    rail = ft.NavigationRail(
        extended=True,
        selected_index=0,
        min_width=72,
        min_extended_width=225,
        bgcolor="#E7F0EF",
        indicator_color="#C8E4E1",
        selected_label_text_style=ft.TextStyle(
            color=ACCENT_DARK, weight=ft.FontWeight.W_600
        ),
        unselected_label_text_style=ft.TextStyle(color="#506A67"),
        leading=ft.Container(
            padding=16,
            content=ft.Row(
                controls=[
                    ft.Container(
                        width=40,
                        height=40,
                        border_radius=10,
                        bgcolor=ACCENT,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Text(
                            "PF", color="#FFFFFF", weight=ft.FontWeight.BOLD, size=16
                        ),
                    ),
                    ft.Column(
                        spacing=0,
                        controls=[
                            ft.Text("PortalFrame", weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            ft.Text("Designer", size=11, color=TEXT_MUTED),
                        ],
                    ),
                ]
            ),
        ),
        destinations=[
            ft.NavigationRailDestination(
                icon=ft.Icon(ft.Icons.FOLDER_OUTLINED, color="#506A67"),
                selected_icon=ft.Icon(ft.Icons.FOLDER, color=ACCENT_DARK),
                label="Project",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icon(ft.Icons.STRAIGHTEN_OUTLINED, color="#506A67"),
                selected_icon=ft.Icon(ft.Icons.STRAIGHTEN, color=ACCENT_DARK),
                label="Geometry",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icon(ft.Icons.AIR_OUTLINED, color="#506A67"),
                selected_icon=ft.Icon(ft.Icons.AIR, color=ACCENT_DARK),
                label="Design & loading",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icon(ft.Icons.ACCOUNT_TREE_OUTLINED, color="#506A67"),
                selected_icon=ft.Icon(ft.Icons.ACCOUNT_TREE, color=ACCENT_DARK),
                label="Frame & bracing",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icon(ft.Icons.FACT_CHECK_OUTLINED, color="#506A67"),
                selected_icon=ft.Icon(ft.Icons.FACT_CHECK, color=ACCENT_DARK),
                label="Review",
            ),
            analysis_destination,
            foundation_destination,
        ],
    )

    current_index = 0

    def go_to(index: int) -> None:
        nonlocal current_index
        if index == 4 and not validate_form():
            rail.selected_index = current_index
            page.update()
            return
        current_index = index
        rail.selected_index = index
        content_host.controls = [sections[index]]
        visual_builder.visible = index not in (5, 6)
        running_summary_panel.visible = index not in (5, 6)
        page.update()
        page.run_task(content_host.scroll_to, offset=0, duration=0)

    def on_nav_change(event) -> None:
        go_to(event.control.selected_index)

    rail.on_change = on_nav_change

    header = ft.Container(
        bgcolor="#FFFFFF",
        padding=18,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Column(
                    spacing=1,
                    controls=[
                        ft.Text(
                            "Portal frame and truss design",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT_PRIMARY,
                        ),
                        ft.Text("Input workspace • Draft UI", size=11, color=TEXT_MUTED),
                    ],
                ),
                ft.Row(
                    controls=[
                        api_status,
                        ft.OutlinedButton(
                            "Check API", icon=ft.Icons.SYNC, on_click=check_api
                        ),
                    ]
                ),
            ],
        ),
    )

    page.add(
        ft.Row(
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Container(bgcolor="#E7F0EF", content=rail),
                ft.Column(
                    spacing=0,
                    expand=True,
                    controls=[
                        header,
                        ft.Row(
                            expand=True,
                            spacing=0,
                            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                            controls=[
                                ft.Container(
                                    expand=True,
                                    padding=20,
                                    content=content_host,
                                ),
                                visual_builder,
                                running_summary_panel,
                            ],
                        ),
                    ],
                ),
            ],
        )
    )
    update_conditionals()
    update_pitch()
    refresh_workspace()
