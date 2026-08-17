"""First browser/desktop Flet draft for PortalFrame."""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any
from urllib.parse import quote

import flet as ft
import flet_webview as fwv
import httpx

# TODO(advanced-finishes): Finalise the UI after the remaining engineering and
# reporting workflows are complete.

from connection_workflow.viewer import list_connection_views
from foundation_workflow.design import (
    FOUNDATION_PASSIVE_RESISTANCE_OPTIONS,
    FOUNDATION_SLIDING_OPTIONS,
    FOUNDATION_STANDARDS,
)
from connection_workflow.haunch_geometry import HAUNCH_DEPTH_AUTO, HAUNCH_DEPTH_CUT
from portal_workflow.preview import build_preview_geometry
from truss_workflow import preview_truss
from ui.analysis_render import combination_names, load_case_svg
from ui.input_model import (
    AUTOMATIC_GABLE_SECTION,
    AUTOMATIC_SECTION,
    BASE_SUPPORTS,
    BUILDING_TYPES,
    COLUMN_BRACING_TYPES,
    CRAWL_APPLICATIONS,
    GABLE_SECTION_ORDERS,
    HAUNCH_DEPTH_OPTIONS,
    HOIST_CLASSES,
    DEFAULT_VALUES,
    LIPPED_CHANNEL_SECTIONS,
    LOAD_COMBINATION_STANDARDS,
    PORTAL_SECTION_FAMILIES,
    PORTAL_SECTIONS_BY_FAMILY,
    REPORT_SCOPES,
    ROOF_ACCESSIBILITY,
    ROOF_TYPES,
    STRUCTURAL_SYSTEMS,
    STEEL_GRADES,
    TERRAIN_CATEGORIES,
    TRUSS_CHORD_FORMS,
    TRUSS_CENTRE_COLUMN_MATERIALS,
    TRUSS_MEMBER_SECTION_ORDERS,
    TRUSS_STEEL_SECTION_ORDERS,
    TRUSS_INTERNAL_SUPPORTS,
    TRUSS_TYPES,
    WIND_DESIGN_MODES,
    InputValidationError,
    build_analysis_payload,
    build_civil_boq_inputs,
    normalize_sans_10160_loading_code,
    rafter_haunch_cut_limit,
)
from ui.project_file import (
    ProjectInputFileError,
    dump_project_inputs,
    load_project_inputs,
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
    input_file_picker = ft.FilePicker()
    page.services.append(input_file_picker)

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
        "SANS 10160 loading-code editions",
        LOAD_COMBINATION_STANDARDS,
        helper="Choose the current edition set or one previous edition set. Combination names remain C1 to C6.2.",
        col=12,
    )
    report_scope = dropdown(
        "report_scope",
        "Calculation report detail",
        REPORT_SCOPES,
        helper="Critical keeps governing results concise; Detailed reports one physical member per load case.",
    )
    use_permanent_deflection_baseline = ft.Switch(
        key="use_permanent_deflection_baseline",
        label="Use permanent-load deflection as the vertical baseline",
        value=bool(
            DEFAULT_VALUES["use_permanent_deflection_baseline"]
        ),
        active_color=ACCENT,
        col=12,
    )
    controls[
        "use_permanent_deflection_baseline"
    ] = use_permanent_deflection_baseline
    ignore_dead_live_vertical_limit = ft.Switch(
        key="ignore_1_1_dl_1_0_ll_vertical_deflection_limit",
        label="Ignore vertical span/deflection limit for 1.1 DL + 1.0 LL",
        value=bool(
            DEFAULT_VALUES[
                "ignore_1_1_dl_1_0_ll_vertical_deflection_limit"
            ]
        ),
        active_color=ACCENT,
        col=12,
    )
    controls[
        "ignore_1_1_dl_1_0_ll_vertical_deflection_limit"
    ] = ignore_dead_live_vertical_limit
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
        helper="Manual choices are ordered by section height, width and mass; Automatic selects the lightest passing section.",
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
        helper="Manual choices are ordered by section height, width and mass; Automatic selects the lightest passing section.",
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
        "Left eaves haunch length",
        unit="m",
        helper="Length along the left roof slope from the eaves.",
    )
    right_eaves_haunch_length = number_field(
        "right_eaves_haunch_length_m",
        "Right eaves haunch length",
        unit="m",
        helper="Length along the right roof slope; leave equal for a symmetric frame.",
    )
    eaves_haunch_depth_mode = dropdown(
        "eaves_haunch_depth_mode",
        "Eaves haunch sizing basis",
        HAUNCH_DEPTH_OPTIONS,
        helper="Auto Size uses span/15 and the donor maximum cut depth (hw + tf).",
    )
    eaves_haunch_depth = number_field(
        "eaves_haunch_depth_mm",
        "Maximum eaves haunch depth",
        unit="mm",
        helper="Additional depth below the selected rafter at the eaves.",
    )
    eaves_haunch_length.disabled = (
        DEFAULT_VALUES["eaves_haunch_depth_mode"] == HAUNCH_DEPTH_AUTO
    )
    right_eaves_haunch_length.disabled = (
        DEFAULT_VALUES["eaves_haunch_depth_mode"] == HAUNCH_DEPTH_AUTO
    )
    eaves_haunch_depth.disabled = (
        DEFAULT_VALUES["eaves_haunch_depth_mode"] == HAUNCH_DEPTH_AUTO
    )
    eaves_haunch_fields = ft.ResponsiveRow(
        controls=[
            eaves_haunch_length,
            right_eaves_haunch_length,
            eaves_haunch_depth_mode,
            eaves_haunch_depth,
        ],
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
    apex_haunch_depth_mode = dropdown(
        "apex_haunch_depth_mode",
        "Apex haunch sizing basis",
        HAUNCH_DEPTH_OPTIONS,
        helper="Auto Size uses span/15 and the donor maximum cut depth (hw + tf).",
    )
    apex_haunch_depth = number_field(
        "apex_haunch_depth_mm",
        "Maximum apex haunch depth",
        unit="mm",
        helper="Additional depth below the selected rafter at the apex.",
    )
    apex_haunch_length.disabled = (
        DEFAULT_VALUES["apex_haunch_depth_mode"] == HAUNCH_DEPTH_AUTO
    )
    apex_haunch_depth.disabled = (
        DEFAULT_VALUES["apex_haunch_depth_mode"] == HAUNCH_DEPTH_AUTO
    )
    apex_haunch_fields = ft.ResponsiveRow(
        controls=[
            apex_haunch_length,
            apex_haunch_depth_mode,
            apex_haunch_depth,
        ],
        visible=bool(DEFAULT_VALUES["use_apex_haunch"]),
    )
    haunch_cut_guidance = ft.Text(
        "",
        size=12,
        color=TEXT_MUTED,
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
        helper="Any positive whole number; columns are spaced evenly.",
        integer=True,
    )
    gable_brace_intervals = number_field(
        "gable_column_brace_intervals",
        "Gable-column brace intervals",
        helper="Equal unbraced intervals over each pinned gable column.",
        integer=True,
    )
    gable_section_type = dropdown(
        "gable_column_section_type",
        "Gable column section family",
        PORTAL_SECTION_FAMILIES,
        helper="Select the I- or H-section database family.",
    )
    gable_section = dropdown(
        "gable_column_section",
        "Gable column section",
        (AUTOMATIC_GABLE_SECTION,)
        + PORTAL_SECTIONS_BY_FAMILY["I-Sections"],
        helper="Manual choices are ordered by section height, width and mass; Automatic uses the design-order setting.",
        searchable=True,
    )
    gable_section_order = dropdown(
        "gable_column_section_order",
        "Gable steel section order",
        GABLE_SECTION_ORDERS,
        helper="Choose lightest passing or preferred database sections first.",
        col=12,
    )

    def sync_gable_section_options() -> None:
        family = str(gable_section_type.value)
        values = (AUTOMATIC_GABLE_SECTION,) + PORTAL_SECTIONS_BY_FAMILY.get(
            family, ()
        )
        gable_section.options = [
            ft.DropdownOption(
                key=value,
                content=ft.Text(value, color=TEXT_PRIMARY),
            )
            for value in values
        ]
        if gable_section.value not in values:
            gable_section.value = AUTOMATIC_GABLE_SECTION
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
    truss_member_section_order = dropdown(
        "truss_member_section_order",
        "Truss member section order",
        TRUSS_MEMBER_SECTION_ORDERS,
        helper=(
            "Controls the real equal-angle candidate search used for chords "
            "and ordinary webs."
        ),
        col=12,
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
        height=390,
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
        helper="Characteristic concrete strength used by the footing checks.",
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
        helper="Interface coefficient used for base friction: Rf = mu x normal force.",
    )
    foundation_soil_cover = number_field(
        "foundation_soil_cover_depth_m",
        "Soil cover above footing",
        unit="m",
        helper="Depth of soil cover contributing to stabilising weight.",
    )
    foundation_pedestal_height = number_field(
        "foundation_pedestal_height_m",
        "Pedestal height above footing",
        unit="m",
        helper=(
            "Distance from footing top to the frame support reaction level; "
            "used for pedestal weight and horizontal-force moment transfer."
        ),
    )
    foundation_sliding = dropdown(
        "foundation_sliding_resistance",
        "Sliding resistance",
        FOUNDATION_SLIDING_OPTIONS,
        helper=(
            "Sliding Resisted means a separate restraint is provided, so pad sliding "
            "does not govern sizing. Sliding Not Resisted designs the pad using base "
            "friction and optional passive resistance."
        ),
    )
    foundation_soil_friction_angle = number_field(
        "foundation_soil_friction_angle_deg",
        "Soil friction angle",
        unit="degrees",
        helper="Used to calculate Rankine Kp when passive resistance is included.",
    )
    foundation_passive_resistance = dropdown(
        "foundation_passive_resistance",
        "Passive soil resistance",
        FOUNDATION_PASSIVE_RESISTANCE_OPTIONS,
        helper="Include only where retained, compacted soil can be relied upon.",
    )
    foundation_passive_mobilisation = number_field(
        "foundation_passive_mobilisation_factor",
        "Passive mobilisation factor",
        helper="Fraction from 0 to 1 applied to characteristic passive resistance.",
    )
    foundation_uls_sliding_required_sf = number_field(
        "foundation_uls_sliding_required_sf",
        "Required ULS sliding SF",
        helper=(
            "Compared with stability resistance calculated from factor-1.0 "
            "characteristic frame actions."
        ),
    )
    foundation_control_keys = {
        "foundation_permissible_bearing_kpa",
        "foundation_concrete_strength_mpa",
        "foundation_soil_unit_weight_kn_m3",
        "foundation_soil_cover_depth_m",
        "foundation_pedestal_height_m",
        "foundation_friction_coefficient",
        "foundation_sliding_resistance",
        "foundation_soil_friction_angle_deg",
        "foundation_passive_resistance",
        "foundation_passive_mobilisation_factor",
        "foundation_uls_sliding_required_sf",
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
    connection_status_text = ft.Text(
        "Run a portal-frame analysis to calculate its connections.",
        size=12,
        weight=ft.FontWeight.W_600,
        color=TEXT_PRIMARY,
    )
    connection_status_card = ft.Container(
        bgcolor=WARNING_BG,
        border_radius=10,
        padding=12,
        content=ft.Row(
            spacing=9,
            controls=[
                ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color="#B87900"),
                connection_status_text,
            ],
        ),
    )
    connection_result_summary = ft.Column(
        spacing=9,
        controls=[
            ft.Text(
                "No connection calculations are available.",
                size=12,
                color=TEXT_MUTED,
            )
        ],
    )
    current_connection_design: dict[str, Any] = {}
    connection_view_status = ft.Text(
        "Run a portal-frame analysis to load the display-only 3D model.",
        size=12,
        color=TEXT_MUTED,
    )
    connection_3d_viewer = ft.Container(
        height=610,
        expand=True,
        visible=False,
        bgcolor="#F7FAF9",
    )
    connection_3d_viewer_generation = 0

    def build_connection_3d_viewer(url: str) -> ft.Container:
        """Create a keyed wrapper that forces a fresh web platform view."""

        nonlocal connection_3d_viewer_generation
        connection_3d_viewer_generation += 1
        return ft.Container(
            key=f"connection-viewer-host-{connection_3d_viewer_generation}",
            height=610,
            expand=True,
            content=fwv.WebView(
                url=url,
                height=610,
                expand=True,
                bgcolor="#F7FAF9",
            ),
        )

    foundation_status_text = ft.Text(
        "Run an analysis before designing foundations.",
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
        automatic = result.get("automatic_design", {})
        rows: list[ft.Control] = [
            analysis_summary_line(
                "Automatic pad size",
                f"{float(automatic.get('length_m', 0)):.2f} m long Ã— "
                f"{float(automatic.get('width_m', 0)):.2f} m wide Ã— "
                f"{float(automatic.get('height_mm', 0)):.0f} mm high",
                ft.Icons.STRAIGHTEN,
            ),
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
            analysis_summary_line(
                "Sliding basis",
                f"{result['inputs'].get('sliding_resistance', 'Sliding Not Resisted')} | "
                f"soil cover {float(result['inputs'].get('soil_cover_depth_m', 0.0)):.2f} m | "
                f"friction coefficient {float(result['inputs'].get('friction_coefficient', 0.0)):.2f} | "
                f"{result['inputs'].get('passive_resistance', 'Passive Resistance Excluded')} | "
                f"phi {float(result['inputs'].get('soil_friction_angle_deg', 0.0)):.1f} degrees | "
                f"mobilisation {float(result['inputs'].get('passive_mobilisation_factor', 0.0)):.2f}",
                ft.Icons.SWAP_HORIZ,
            ),
        ]
        for support in result.get("supports", []):
            bearing = support["serviceability"]["bearing"]
            service_sliding = support["serviceability"]["sliding"]
            uplift = support["serviceability"]["uplift"]
            structural = support["structural"]
            stability = support["uls_stability"]
            sliding = stability["sliding"]
            governing_check = max(
                structural["checks"],
                key=lambda item: float(item["utilisation"]),
            )
            rows.extend([
                analysis_summary_line(
                    f"Support {support['node']} - {support['status']}"
                    + (
                        f" ({int(support['quantity'])} bases)"
                        if int(support.get('quantity', 1)) > 1 else ""
                    ),
                    f"Bearing {bearing['status']} {float(bearing['q_max_kpa']):.1f} kPa "
                    f"(util {float(bearing['utilisation']):.3f}, {bearing['contact']} contact) | "
                    f"ULS sliding {sliding.get('status', 'PASS')} "
                    + (
                        f"SF {float(sliding['safety_factor']):.2f} "
                        f"(required {float(stability.get('required_sliding_safety_factor', 1.5)):.2f})"
                        if sliding.get('status') not in {'NOT_CHECKED', 'RESISTED_EXTERNALLY'}
                        else "(separate external restraint)"
                    ) + " | "
                    f"ULS overturning SF {float(stability['overturning']['safety_factor']):.2f} | "
                    f"uplift {uplift['status']} ({float(uplift['net_vertical_kN']):.1f} kN net)",
                    ft.Icons.FOUNDATION,
                ),
                analysis_summary_line(
                    f"Support {support['node']} - sliding resistance",
                    f"ULS normal {float(sliding.get('normal_force_kN', 0.0)):.1f} kN | "
                    f"friction {float(sliding.get('friction_resistance_kN', 0.0)):.1f} kN | "
                    f"passive {float(sliding.get('passive_resistance_kN', 0.0)):.1f} kN | "
                    f"total {float(sliding.get('total_resistance_kN', 0.0)):.1f} kN | "
                    f"{sliding.get('combination', '-')}",
                    ft.Icons.SWAP_HORIZ,
                ),
                analysis_summary_line(
                    f"Support {support['node']} - SLS sliding",
                    f"{service_sliding.get('status', 'NOT_CHECKED')} | "
                    f"SF {float(service_sliding.get('safety_factor', 0.0)):.2f} | "
                    f"demand {float(service_sliding.get('horizontal_demand_kN', 0.0)):.1f} kN | "
                    f"friction {float(service_sliding.get('friction_resistance_kN', 0.0)):.1f} kN | "
                    f"passive {float(service_sliding.get('passive_resistance_kN', 0.0)):.1f} kN | "
                    f"{service_sliding.get('combination', '-')}",
                    ft.Icons.SWAP_HORIZ,
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
                "development length, exposure detailing, whole-building stability and adjacent-footing interaction.",
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

    boq_status_text = ft.Text(
        "Run an analysis before creating the structural steel BOQ.",
        size=12,
        weight=ft.FontWeight.W_600,
        color=TEXT_PRIMARY,
    )
    boq_status_card = ft.Container(
        bgcolor=WARNING_BG,
        border_radius=10,
        padding=12,
        content=ft.Row(
            spacing=9,
            controls=[
                ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color="#B87900"),
                boq_status_text,
            ],
        ),
    )
    boq_additional_items = ft.Column(spacing=10)
    boq_item_rows: list[dict[str, ft.Control]] = []

    def add_boq_item(_=None, *, update_page: bool = True) -> None:
        description = ft.TextField(
            label="Description",
            col={"sm": 12, "lg": 5},
            dense=True,
            color=TEXT_PRIMARY,
            border_color="#93AAA7",
            focused_border_color=ACCENT,
        )
        unit = ft.Dropdown(
            label="Unit",
            value="No",
            options=[
                ft.DropdownOption(key=value, content=ft.Text(value, color=TEXT_PRIMARY))
                for value in ("t", "kg", "m", "m2", "m3", "No", "Sum")
            ],
            col={"sm": 4, "lg": 2},
            dense=True,
            color=TEXT_PRIMARY,
            border_color="#93AAA7",
            focused_border_color=ACCENT,
        )
        quantity = ft.TextField(
            label="Quantity",
            keyboard_type=ft.KeyboardType.NUMBER,
            col={"sm": 4, "lg": 2},
            dense=True,
            color=TEXT_PRIMARY,
            border_color="#93AAA7",
            focused_border_color=ACCENT,
        )
        rate = ft.TextField(
            label="Rate (optional)",
            keyboard_type=ft.KeyboardType.NUMBER,
            col={"sm": 4, "lg": 2},
            dense=True,
            color=TEXT_PRIMARY,
            border_color="#93AAA7",
            focused_border_color=ACCENT,
        )
        record: dict[str, ft.Control] = {
            "description": description,
            "unit": unit,
            "quantity": quantity,
            "rate": rate,
        }

        def remove_item(_=None) -> None:
            boq_item_rows.remove(record)
            boq_additional_items.controls.remove(item_row)
            page.update()

        item_row = ft.Container(
            bgcolor="#F8FBFA",
            border=ft.Border.all(1, "#D8E5E3"),
            border_radius=10,
            padding=10,
            content=ft.ResponsiveRow(
                controls=[
                    description,
                    unit,
                    quantity,
                    rate,
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        tooltip="Remove item",
                        col={"sm": 12, "lg": 1},
                        on_click=remove_item,
                    ),
                ]
            ),
        )
        boq_item_rows.append(record)
        boq_additional_items.controls.append(item_row)
        if update_page:
            page.update()

    boq_download_button = ft.OutlinedButton(
        "Download Structural Steel BOQ",
        icon=ft.Icons.DOWNLOAD,
        disabled=True,
    )
    boq_generate_button = ft.FilledButton(
        "Create Structural Steel BOQ",
        icon=ft.Icons.TABLE_VIEW,
        disabled=True,
    )

    async def create_boq(_=None) -> None:
        if current_analysis_id is None:
            return
        additional_items = []
        for record in boq_item_rows:
            description = str(record["description"].value or "").strip()
            quantity = str(record["quantity"].value or "").strip()
            rate = str(record["rate"].value or "").strip()
            if not description and not quantity and not rate:
                continue
            additional_items.append({
                "description": description,
                "unit": str(record["unit"].value or ""),
                "quantity": quantity,
                "rate": rate,
            })
        boq_generate_button.disabled = True
        boq_generate_button.content = "Creating BOQ..."
        boq_download_button.disabled = True
        boq_status_card.bgcolor = WARNING_BG
        boq_status_card.content.controls[0].name = ft.Icons.HOURGLASS_TOP
        boq_status_card.content.controls[0].color = "#B87900"
        boq_status_text.value = "Calculating member weights, sheeting, plates and bolts..."
        page.update()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{API_URL}/api/analysis/{current_analysis_id}/structural-boq",
                    json={"additional_items": additional_items},
                )
                if response.status_code == 422:
                    raise ValueError(str(response.json().get("detail", "Invalid BOQ item.")))
                response.raise_for_status()
                result = response.json()
            summary = result["summary"]
            boq_download_button.url = f"{API_URL}{result['download_url']}"
            boq_download_button.disabled = False
            boq_status_card.bgcolor = SUCCESS_BG
            boq_status_card.content.controls[0].name = ft.Icons.CHECK_CIRCLE
            boq_status_card.content.controls[0].color = "#1C8C62"
            boq_status_text.value = (
                f"BOQ ready: {float(summary['fabricated_steel_mass_t']):,.3f} t "
                f"fabricated steel, {int(summary['calculated_item_count'])} calculated "
                f"items and {int(summary['additional_item_count'])} additional items."
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            boq_status_card.bgcolor = ERROR_BG
            boq_status_card.content.controls[0].name = ft.Icons.ERROR_OUTLINE
            boq_status_card.content.controls[0].color = "#C43D34"
            boq_status_text.value = f"Structural BOQ error: {exc}"
        finally:
            boq_generate_button.disabled = current_analysis_id is None
            boq_generate_button.content = "Create Structural Steel BOQ"
            page.update()

    boq_generate_button.on_click = create_boq
    add_boq_item(update_page=False)

    civil_boq_status = ft.Text(
        "Enter the project-specific civil and earthworks quantities below.",
        size=12,
        color=TEXT_PRIMARY,
    )
    civil_surface_bed_area = ft.TextField(
        label="Surface bed area (m²)", value=str(DEFAULT_VALUES["civil_surface_bed_area_m2"]),
        keyboard_type=ft.KeyboardType.NUMBER, dense=True, color=TEXT_PRIMARY,
        border_color="#93AAA7", focused_border_color=ACCENT,
    )
    civil_surface_bed_thickness = ft.TextField(
        label="Surface bed thickness (mm)", value=str(DEFAULT_VALUES["civil_surface_bed_thickness_mm"]),
        keyboard_type=ft.KeyboardType.NUMBER, dense=True, color=TEXT_PRIMARY,
        border_color="#93AAA7", focused_border_color=ACCENT,
    )
    civil_joint_spacing = ft.TextField(
        label="Surface bed joint spacing (m)", value=str(DEFAULT_VALUES["civil_joint_spacing_m"]),
        keyboard_type=ft.KeyboardType.NUMBER, dense=True, color=TEXT_PRIMARY,
        border_color="#93AAA7", focused_border_color=ACCENT,
    )
    civil_excavation_depth = ft.TextField(
        label="Excavation below surface bed (m)", value=str(DEFAULT_VALUES["civil_excavation_below_surface_bed_m"]),
        keyboard_type=ft.KeyboardType.NUMBER, dense=True, color=TEXT_PRIMARY,
        border_color="#93AAA7", focused_border_color=ACCENT,
    )
    civil_footing_backfill = ft.TextField(
        label="Concrete footing backfill (m³)", value=str(DEFAULT_VALUES["civil_concrete_footing_backfill_m3"]),
        keyboard_type=ft.KeyboardType.NUMBER, dense=True, color=TEXT_PRIMARY,
        border_color="#93AAA7", focused_border_color=ACCENT,
    )
    civil_boq_summary = ft.Text("Calculated quantities will appear here.", size=12, color=TEXT_MUTED)

    def update_civil_boq_summary(_=None) -> None:
        try:
            values = build_civil_boq_inputs({
                "civil_surface_bed_area_m2": civil_surface_bed_area.value,
                "civil_surface_bed_thickness_mm": civil_surface_bed_thickness.value,
                "civil_joint_spacing_m": civil_joint_spacing.value,
                "civil_excavation_below_surface_bed_m": civil_excavation_depth.value,
                "civil_concrete_footing_backfill_m3": civil_footing_backfill.value,
            })
        except InputValidationError:
            civil_boq_summary.value = "Complete the civil BOQ inputs to calculate quantities."
            return
        civil_boq_summary.value = (
            f"Surface bed concrete: {values['surface_bed_concrete_m3']:.3f} m³ | "
            f"excavation: {values['excavation_volume_m3']:.3f} m³ | "
            f"joint length allowance: {values['surface_bed_joint_length_m']:.3f} m"
        )

    for field in (
        civil_surface_bed_area, civil_surface_bed_thickness, civil_joint_spacing,
        civil_excavation_depth, civil_footing_backfill,
    ):
        field.on_change = update_civil_boq_summary
    civil_boq_download_button = ft.OutlinedButton(
        "Download Civil BOQ", icon=ft.Icons.DOWNLOAD, disabled=True
    )
    civil_boq_generate_button = ft.FilledButton(
        "Create Civil BOQ", icon=ft.Icons.TABLE_VIEW, disabled=True
    )

    async def create_civil_boq(_=None) -> None:
        if current_analysis_id is None:
            return
        try:
            inputs = build_civil_boq_inputs({
                "civil_surface_bed_area_m2": civil_surface_bed_area.value,
                "civil_surface_bed_thickness_mm": civil_surface_bed_thickness.value,
                "civil_joint_spacing_m": civil_joint_spacing.value,
                "civil_excavation_below_surface_bed_m": civil_excavation_depth.value,
                "civil_concrete_footing_backfill_m3": civil_footing_backfill.value,
            })
        except InputValidationError as exc:
            civil_boq_status.value = str(exc)
            page.update()
            return
        civil_boq_generate_button.disabled = True
        civil_boq_status.value = "Creating civil/concrete BOQ from the completed foundation design..."
        page.update()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{API_URL}/api/analysis/{current_analysis_id}/civil-boq",
                    json=inputs,
                )
                response.raise_for_status()
                result = response.json()
            civil_boq_download_button.url = f"{API_URL}{result['download_url']}"
            civil_boq_download_button.disabled = False
            civil_boq_status.value = (
                f"Civil BOQ ready: {int(result['summary']['item_count'])} calculated items."
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            civil_boq_status.value = f"Civil BOQ error: {exc}"
        finally:
            civil_boq_generate_button.disabled = current_analysis_id is None
            page.update()

    civil_boq_generate_button.on_click = create_civil_boq
    civil_boq_page = ft.Column(
        spacing=18,
        controls=[
            section_heading(
                "Civil and Earthworks BOQ Inputs",
                "First input page for the civil/concrete and earthworks BOQs based on the supplied examples.",
            ),
            ft.Container(
                bgcolor=WARNING_BG, border_radius=10, padding=12,
                content=ft.Text(
                    "These inputs are quantity drivers only. The civil BOQ will retain the example workbook's descriptions, units and layout.",
                    color="#745B2B", weight=ft.FontWeight.BOLD,
                ),
            ),
            card(
                "Surface bed and joints",
                "Enter the surface-bed geometry and the joint spacing used to derive the first civil quantities.",
                ft.ResponsiveRow(controls=[
                    civil_surface_bed_area, civil_surface_bed_thickness, civil_joint_spacing,
                ]),
            ),
            card(
                "Excavation and footing backfill",
                "Enter the excavation level below the surface bed and the concrete footing backfill allowance.",
                ft.ResponsiveRow(controls=[civil_excavation_depth, civil_footing_backfill]),
            ),
            card("Calculated preview", "Derived quantities from the entered civil assumptions.", civil_boq_summary),
            civil_boq_status,
            ft.Row(
                alignment=ft.MainAxisAlignment.END,
                wrap=True,
                controls=[civil_boq_generate_button, civil_boq_download_button],
            ),
        ],
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
    download_prokon_a03_button = ft.OutlinedButton(
        "Download Prokon A03",
        icon=ft.Icons.DOWNLOAD,
        disabled=True,
    )
    download_prokon_json_button = ft.OutlinedButton(
        "Download Prokon audit JSON",
        icon=ft.Icons.DATA_OBJECT,
        disabled=True,
    )
    download_prokon_package_button = ft.OutlinedButton(
        "Download all Prokon models",
        icon=ft.Icons.FOLDER_ZIP,
        disabled=True,
    )

    def show_connection_results(result: dict[str, Any]) -> None:
        detailed = result.get("detailed_checks", {})
        status = str(detailed.get("status", result.get("status", "FAIL")))
        passed = status == "PASS"
        connection_status_card.bgcolor = (
            SUCCESS_BG if passed else (ERROR_BG if status == "FAIL" else WARNING_BG)
        )
        connection_status_card.content.controls[0].name = (
            ft.Icons.CHECK_CIRCLE
            if passed
            else (
                ft.Icons.ERROR_OUTLINE
                if status == "FAIL"
                else ft.Icons.WARNING_AMBER
            )
        )
        connection_status_card.content.controls[0].color = (
            "#1C8C62" if passed else ("#C43D34" if status == "FAIL" else "#B87900")
        )
        connection_status_text.value = (
            f"Post-analysis connection status: {status}. "
            "Review failed and input-required checks before fabrication."
        )
        rows: list[ft.Control] = []

        def add_connection(label: str, item: dict[str, Any], weld_key: str) -> None:
            checks = list(item.get("checks", []))
            checks.extend(item.get("local_member_checks", []))
            stiffener = item.get("stiffener_checks", {})
            checks.extend(stiffener.get("checks", []))
            completed = [
                check
                for check in checks
                if check.get("utilisation") is not None
            ]
            governing = max(
                completed,
                key=lambda check: float(check.get("utilisation", 0.0)),
                default=None,
            )
            weld = item.get(weld_key, {})
            selected_weld = weld.get("selected_weld", weld)
            weld_size = selected_weld.get(
                "provided_size_mm",
                selected_weld.get(
                    "weld_size_mm",
                    selected_weld.get("equivalent_fillet_size_mm", 0),
                ),
            )
            rows.append(
                analysis_summary_line(
                    f"{label} - {item.get('status', 'FAIL')}",
                    (
                        f"Governing {governing.get('reference', '-')}: "
                        f"{governing.get('name', '')} | utilisation "
                        f"{float(governing.get('utilisation', 0)):.3f} | "
                        f"{governing.get('status', '')}"
                        if governing
                        else "No completed checks."
                    ),
                    ft.Icons.FACT_CHECK,
                )
            )
            if weld:
                rows.append(
                    analysis_summary_line(
                        f"{label} - weld",
                        f"{selected_weld.get('type', selected_weld.get('weld_type', 'Weld'))} "
                        f"{float(weld_size or 0):.0f} mm | utilisation "
                        f"{float(selected_weld.get('utilisation', 0)):.3f} | "
                        f"{selected_weld.get('status', weld.get('status', ''))}",
                        ft.Icons.HARDWARE,
                    )
                )
            if stiffener:
                rows.append(
                    analysis_summary_line(
                        f"{label} - stiffeners",
                        (
                            f"{stiffener.get('status', '')} | "
                            f"governing utilisation "
                            f"{float(stiffener.get('governing_utilisation', 0) or 0):.3f}"
                        ),
                        ft.Icons.CALL_MERGE,
                    )
                )
            anchor = item.get("anchor_concrete")
            if anchor:
                anchor_check = next(iter(anchor.get("checks", [])), {})
                rows.append(
                    analysis_summary_line(
                        f"{label} - concrete anchorage",
                        f"{anchor.get('status', 'INPUT_REQUIRED')} | "
                        f"{anchor_check.get('note', '')}",
                        ft.Icons.REPORT_PROBLEM_OUTLINED,
                    )
                )

        for support in detailed.get("base_plates", {}).get("supports", []):
            add_connection(
                f"Base plate {support.get('support', '')}",
                support,
                "column_to_base_plate_weld",
            )
        for location in detailed.get("haunch_connections", {}).get("locations", []):
            add_connection(
                str(location.get("location", "Haunch")),
                location,
                "end_plate_weld",
            )
        rows.append(
            analysis_summary_line(
                "Calculation boundary",
                "Steel plates, bolts, prying, weld groups, stiffeners and local "
                "member effects are calculated. HD-bolt anchorage is estimated "
                "from Red Book Table 4.6 for 25 MPa concrete; pedestal geometry, "
                "7d edge distance and reinforcement require confirmation.",
                ft.Icons.INFO_OUTLINE,
            )
        )
        connection_result_summary.controls = rows
    connection_markup_button = ft.OutlinedButton(
        "View 2D PDF",
        icon=ft.Icons.PICTURE_AS_PDF,
        disabled=True,
    )
    connection_dxf_button = ft.OutlinedButton(
        "Download DXF",
        icon=ft.Icons.DOWNLOAD,
        disabled=True,
    )
    connection_dwg_button = ft.OutlinedButton(
        "Download DWG",
        icon=ft.Icons.DOWNLOAD,
        disabled=True,
    )
    connection_export_status_text = ft.Text(
        "The 2D PDF and DXF will be created after analysis; DWG conversion "
        "will be attempted when AutoCAD is available.",
        size=12,
        color=TEXT_MUTED,
    )
    connection_report_button = ft.OutlinedButton(
        "View calculation report",
        icon=ft.Icons.DESCRIPTION_OUTLINED,
        disabled=True,
    )
    connection_outputs_card = card(
        "Connection outputs",
        "Open the calculation report or export the same checked, "
        "dimensioned 2D connection sheets as PDF, DXF or DWG.",
        ft.Column(
            spacing=10,
            controls=[
                connection_export_status_text,
                ft.Row(
                    wrap=True,
                    controls=[
                        connection_report_button,
                        connection_markup_button,
                        connection_dxf_button,
                        connection_dwg_button,
                    ],
                ),
            ],
        ),
    )
    open_connections_button = ft.OutlinedButton(
        "Open connection design",
        icon=ft.Icons.HARDWARE,
        disabled=True,
        on_click=lambda _: go_to(6),
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
        values.update({
            "civil_surface_bed_area_m2": civil_surface_bed_area.value,
            "civil_surface_bed_thickness_mm": civil_surface_bed_thickness.value,
            "civil_joint_spacing_m": civil_joint_spacing.value,
            "civil_excavation_below_surface_bed_m": civil_excavation_depth.value,
            "civil_concrete_footing_backfill_m3": civil_footing_backfill.value,
        })
        values["crawl_beams"] = [
            {
                field: control.value
                for field, control in row["fields"].items()
            }
            for row in crawl_rows
        ]
        return values

    def additional_roof_load_text(building: dict[str, Any]) -> str:
        load_items = (
            ("services_load_kpa", "services"),
            ("ceiling_load_kpa", "ceiling"),
            ("solar_load_kpa", "solar"),
            ("fire_load_kpa", "fire services"),
            ("hvac_load_kpa", "HVAC"),
        )
        values = [
            (label, float(building.get(key, 0.0) or 0.0))
            for key, label in load_items
        ]
        maximum_total = sum(value for _, value in values)
        minimum_total = sum(
            value
            for label, value in values
            if label not in {"services", "solar"}
        )
        included = ", ".join(
            f"{label} {value:g}" for label, value in values if value > 0
        )
        return (
            f"D_MAX +{maximum_total:g} kPa; D_MIN +{minimum_total:g} kPa "
            f"(services and solar excluded from D_MIN). Entered: {included}"
            if included
            else "D_MAX +0 kPa; D_MIN +0 kPa (no additional permanent roof load)"
        )

    def show_input_file_message(message: str, *, error: bool = False) -> None:
        page.show_dialog(
            ft.SnackBar(
                ft.Text(message, color="#FFFFFF"),
                bgcolor="#A92F28" if error else ACCENT_DARK,
                show_close_icon=True,
                close_icon_color="#FFFFFF",
            )
        )
        page.update()

    async def save_inputs(_=None) -> None:
        project_name_value = str(controls["project_name"].value or "portalframe")
        safe_name = "".join(
            character if character.isalnum() or character in "-_" else "-"
            for character in project_name_value.strip()
        ).strip("-") or "portalframe"
        try:
            destination = await input_file_picker.save_file(
                dialog_title="Save PortalFrame inputs",
                file_name=f"{safe_name}.portalframe.json",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["json"],
                src_bytes=dump_project_inputs(raw_values()),
            )
        except (OSError, ValueError) as exc:
            show_input_file_message(f"Inputs could not be saved: {exc}", error=True)
            return
        if destination is not None:
            show_input_file_message(
                "Inputs saved. The file can be loaded later on this or another run."
            )

    def apply_loaded_inputs(inputs: dict[str, Any]) -> None:
        nonlocal crawl_row_counter
        for key, value in inputs.items():
            control = controls.get(key)
            if control is None or key == "crawl_beams":
                continue
            if isinstance(control, (ft.Checkbox, ft.Switch)):
                control.value = bool(value)
            elif isinstance(control, (ft.TextField, ft.Dropdown)):
                control.value = (
                    normalize_sans_10160_loading_code(value)
                    if key == "load_combination_standard"
                    else str(value)
                )

        for row in crawl_rows:
            for field in row["fields"].values():
                controls.pop(field.key, None)
        crawl_rows.clear()
        crawl_row_counter = 0
        refresh_crawl_editor()

        for saved_row in inputs.get("crawl_beams", []):
            add_crawl_beam()
            fields = crawl_rows[-1]["fields"]
            family = str(saved_row.get("section_type", "I-Sections"))
            section_values = PORTAL_SECTIONS_BY_FAMILY.get(family, ())
            fields["section"].options = [
                ft.DropdownOption(
                    key=item, content=ft.Text(item, color=TEXT_PRIMARY)
                )
                for item in section_values
            ]
            for field_name, control in fields.items():
                if field_name not in saved_row:
                    continue
                value = saved_row[field_name]
                if isinstance(control, (ft.TextField, ft.Dropdown)):
                    control.value = str(value)

        controls["use_crawl_beams"].value = bool(inputs["use_crawl_beams"])
        for key, control in {
            "civil_surface_bed_area_m2": civil_surface_bed_area,
            "civil_surface_bed_thickness_mm": civil_surface_bed_thickness,
            "civil_joint_spacing_m": civil_joint_spacing,
            "civil_excavation_below_surface_bed_m": civil_excavation_depth,
            "civil_concrete_footing_backfill_m3": civil_footing_backfill,
        }.items():
            if key in inputs:
                control.value = str(inputs[key])
        update_civil_boq_summary()
        clear_errors()
        update_conditionals()
        validate_form()

    async def load_inputs(_=None) -> None:
        try:
            files = await input_file_picker.pick_files(
                dialog_title="Load PortalFrame inputs",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["json"],
                allow_multiple=False,
                with_data=True,
            )
            if not files:
                return
            if files[0].bytes is None:
                raise ProjectInputFileError("The selected file contents were not available.")
            inputs = load_project_inputs(files[0].bytes)
            build_analysis_payload(inputs)
        except (InputValidationError, ProjectInputFileError, OSError, ValueError) as exc:
            if isinstance(exc, InputValidationError):
                detail = f"{len(exc.errors)} saved input(s) are no longer valid."
            else:
                detail = str(exc)
            show_input_file_message(f"Inputs could not be loaded: {detail}", error=True)
            return
        apply_loaded_inputs(inputs)
        show_input_file_message(
            f"Loaded {files[0].name}. Review the inputs, then run the analysis."
        )

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
                compact_summary_line(
                    "Additional permanent roof load",
                    additional_roof_load_text(building),
                    ft.Icons.VERTICAL_ALIGN_BOTTOM,
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
                "Additional permanent roof load",
                additional_roof_load_text(building),
                ft.Icons.VERTICAL_ALIGN_BOTTOM,
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
                        f"Eaves L/R "
                        f"{building.get('left_eaves_haunch_length', building['eaves_haunch_length']) / 1000:g}/"
                        f"{building.get('right_eaves_haunch_length', building['eaves_haunch_length']) / 1000:g} m x "
                        + (
                            (
                                "Auto Size (span/15 x max cut)"
                                if building.get("eaves_haunch_depth_mode")
                                == HAUNCH_DEPTH_AUTO
                                else "Cut-Depth (hw + tf)"
                            )
                            if building.get("eaves_haunch_depth_mode")
                            in (HAUNCH_DEPTH_CUT, HAUNCH_DEPTH_AUTO)
                            else f"{building['eaves_haunch_depth']:.0f} mm"
                        )
                        if building["use_eaves_haunch"] == "Yes"
                        else "Eaves none"
                    ),
                    (
                        f"Apex {building['apex_haunch_length'] / 1000:g} m/slope x "
                        + (
                            (
                                "Auto Size (span/15 x max cut)"
                                if building.get("apex_haunch_depth_mode")
                                == HAUNCH_DEPTH_AUTO
                                else "Cut-Depth (hw + tf)"
                            )
                            if building.get("apex_haunch_depth_mode")
                            in (HAUNCH_DEPTH_CUT, HAUNCH_DEPTH_AUTO)
                            else f"{building['apex_haunch_depth']:.0f} mm"
                        )
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
                f"{building['gable_column_brace_intervals']} restraint intervals | "
                f"{building['gable_column_section'] if building['gable_column_section'] != AUTOMATIC_GABLE_SECTION else building['gable_column_section_order']}",
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
                connection_destination.disabled = True
                foundation_destination.disabled = True
                foundation_design_button.disabled = True
                boq_destination.disabled = True
                civil_boq_destination.disabled = True
                civil_boq_generate_button.disabled = True
                civil_boq_download_button.disabled = True
                boq_generate_button.disabled = True
                boq_download_button.disabled = True
                download_markup_button.disabled = True
                download_prokon_a03_button.disabled = True
                download_prokon_json_button.disabled = True
                download_prokon_package_button.disabled = True
                connection_markup_button.disabled = True
                connection_dxf_button.disabled = True
                connection_dwg_button.disabled = True
                connection_report_button.disabled = True
                open_connections_button.disabled = True
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
        nonlocal current_analysis_id, current_visualisation
        nonlocal current_connection_design
        current_analysis_id = None
        current_visualisation = {}
        current_connection_design = {}
        analysis_progress.visible = False
        analysis_status_card.bgcolor = ERROR_BG
        analysis_status_icon.visible = True
        analysis_status_icon.name = ft.Icons.ERROR_OUTLINE
        analysis_status_icon.color = "#C43D34"
        analysis_status_text.value = message
        run_analysis_button.disabled = False
        run_analysis_button.content = "Run analysis"
        analysis_result_summary.controls = [
            ft.Text(
                "No current analysis results are available. Correct the inputs "
                "or design settings and run the analysis again.",
                size=13,
                color=TEXT_MUTED,
            )
        ]
        view_report_button.disabled = True
        open_analysis_button.disabled = True
        download_markup_button.disabled = True
        download_prokon_a03_button.disabled = True
        download_prokon_json_button.disabled = True
        download_prokon_package_button.disabled = True
        connection_markup_button.disabled = True
        connection_dxf_button.disabled = True
        connection_dwg_button.disabled = True
        connection_report_button.disabled = True
        open_connections_button.disabled = True
        connection_3d_viewer.content = None
        connection_3d_viewer.visible = False
        connection_view_status.value = (
            "Run a portal-frame analysis to load the display-only 3D model."
        )
        connection_export_status_text.value = (
            "The 2D PDF and DXF will be created after analysis; DWG conversion "
            "will be attempted when AutoCAD is available."
        )
        load_case_dropdown.disabled = True
        previous_load_case_button.disabled = True
        next_load_case_button.disabled = True
        expand_load_case_button.disabled = True
        load_case_image.visible = False
        analysis_destination.disabled = True
        connection_destination.disabled = True
        foundation_destination.disabled = True
        foundation_design_button.disabled = True
        boq_destination.disabled = True
        civil_boq_destination.disabled = True
        civil_boq_generate_button.disabled = True
        civil_boq_download_button.disabled = True
        boq_generate_button.disabled = True
        boq_download_button.disabled = True
        page.update()

    def show_analysis_results(result: dict[str, Any]) -> None:
        nonlocal current_visualisation, current_analysis_id
        nonlocal current_connection_design
        summary = result["design_summary"]
        if summary.get("structural_system") == "Truss":
            current_analysis_id = str(result["analysis_id"])
            current_connection_design = dict(
                summary.get("connection_design", {})
            )
            connection_3d_viewer.content = None
            connection_3d_viewer.visible = False
            connection_view_status.value = (
                "The truss connection scope contains calculated column base "
                "plates only; use the dimensioned 2D output for review."
            )
            connection_export_status_text.value = (
                "Base-plate calculation and 2D markup outputs are available. "
                "Truss haunch connections are not applicable."
            )
            connection_destination.disabled = False
            foundation_destination.disabled = False
            foundation_design_button.disabled = False
            boq_destination.disabled = False
            civil_boq_destination.disabled = False
            civil_boq_generate_button.disabled = False
            civil_boq_download_button.disabled = True
            boq_generate_button.disabled = False
            boq_download_button.disabled = True
            ranked = list(summary.get("ranked_solutions", []))
            best = ranked[0]
            current_visualisation = dict(
                best.get("load_case_visualisation", {})
            )
            set_analysis_view_options(truss_deflection_only=True)
            analysis_view_dropdown.value = "Deflection"
            ranked_text = " | ".join(
                f"#{item['rank']}: {item['geometry']['depth_mm'] / 1000:g} m, "
                f"{item['arrangement_mass_kg']:,.0f} kg total steel, "
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
                    "practical fabrication groups; both totals include purlins",
                    ft.Icons.SCALE_OUTLINED,
                ),
                analysis_summary_line(
                    "Purlins included in total",
                    f"{best['purlins']['section']} | "
                    f"{best['purlins']['line_count']} lines × "
                    f"{best['purlins']['building_length_m']:.1f} m | "
                    f"{best['purlins']['mass_kg']:,.1f} kg",
                    ft.Icons.HORIZONTAL_RULE,
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
                    "Truss section search order",
                    str(
                        summary.get("design_basis", {})
                        .get("member_section_order", {})
                        .get("selected", "")
                    ),
                    ft.Icons.SORT,
                ),
                analysis_summary_line(
                    "Rank 1 chord restraint",
                    f"Top requested every {best['chord_restraint_layout']['top_chord']['brace_every_n_purlins']} purlin(s) • "
                    f"bottom requested every {best['chord_restraint_layout']['bottom_chord']['brace_every_n_purlins']} • "
                    f"paired actual maximum interval "
                    f"{best['chord_restraint_layout']['top_chord'].get('actual_maximum_purlin_interval', '')} purlin(s), "
                    f"{max(best['chord_restraint_layout']['top_chord']['maximum_spacing_mm'], best['chord_restraint_layout']['bottom_chord']['maximum_spacing_mm']) / 1000:.2f} m",
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
                    "Independent validation, truss joints/bearings/splices, restraint-member capacity and concrete tilt-up capacity/detailing",
                    ft.Icons.REPORT_PROBLEM_OUTLINED,
                ),
            ]
            artifacts = result.get("artifacts", {})
            report = artifacts.get("truss-report-html")
            truss_markup = artifacts.get("truss-markup-html")
            if report:
                view_report_button.url = ft.Url(
                    url=f"{API_URL}{report['download_url']}", target=ft.UrlTarget.SELF
                )
                view_report_button.disabled = False
            if truss_markup:
                download_markup_button.url = (
                    f"{API_URL}{truss_markup['download_url']}"
                )
                download_markup_button.disabled = False
            else:
                download_markup_button.disabled = True
            connection_report = artifacts.get("connection-report-html")
            connection_markup = artifacts.get("connection-markup-pdf")
            connection_dxf = artifacts.get("connection-markup-dxf")
            if connection_report:
                connection_report_button.url = ft.Url(
                    url=f"{API_URL}{connection_report['download_url']}",
                    target=ft.UrlTarget.BLANK,
                )
                connection_report_button.disabled = False
            if connection_markup:
                connection_markup_button.url = ft.Url(
                    url=f"{API_URL}{connection_markup['download_url']}",
                    target=ft.UrlTarget.BLANK,
                )
                connection_markup_button.disabled = False
            if connection_dxf:
                connection_dxf_button.url = (
                    f"{API_URL}{connection_dxf['download_url']}"
                )
                connection_dxf_button.disabled = False
            connection_dwg_button.disabled = True
            show_connection_results(current_connection_design)
            open_connections_button.disabled = False
            boq_status_card.bgcolor = WARNING_BG
            boq_status_card.content.controls[0].name = ft.Icons.INFO_OUTLINE
            boq_status_card.content.controls[0].color = "#B87900"
            boq_status_text.value = (
                "Truss, column, purlin and calculated base-plate quantities "
                "are ready. Add project-specific items before export."
            )
            foundation_status_card.bgcolor = WARNING_BG
            foundation_status_card.content.controls[0].name = ft.Icons.INFO_OUTLINE
            foundation_status_card.content.controls[0].color = "#B87900"
            foundation_status_text.value = (
                "Truss-column base reactions are ready. Enter the project soil "
                "inputs, then run the automatic pad-foundation design."
            )
            prokon_a03 = artifacts.get("prokon-input-a03")
            prokon_json = artifacts.get("prokon-input-json")
            prokon_package = artifacts.get("prokon-package-zip")
            if prokon_a03 and prokon_json:
                download_prokon_a03_button.url = f"{API_URL}{prokon_a03['download_url']}"
                download_prokon_json_button.url = f"{API_URL}{prokon_json['download_url']}"
                download_prokon_a03_button.disabled = False
                download_prokon_json_button.disabled = False
            if prokon_package:
                download_prokon_package_button.url = f"{API_URL}{prokon_package['download_url']}"
                download_prokon_package_button.disabled = False
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
                "base plates are calculated, while truss joints and independent "
                "project verification remain outstanding."
            )
            run_analysis_button.disabled = False
            run_analysis_button.content = "Run analysis again"
            page.update()
            return
        set_analysis_view_options(truss_deflection_only=False)
        current_analysis_id = str(result["analysis_id"])
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
        gable_text = ", ".join(
            f"{item['name']}: {item['section']} | "
            f"{item['status']} {float(item['utilisation']):.3f}"
            for item in summary.get("gable_columns", [])
        ) or "No gable columns required."
        current_visualisation = dict(
            summary.get("load_case_visualisation", {})
        )
        connections = summary.get("connection_design", {})
        current_connection_design = dict(connections)
        base_plates = connections.get("base_plates", {})
        base_supports = list(base_plates.get("supports", []))
        base_plate_text = "No base-plate result."
        if base_supports and base_supports[0].get("plate"):
            plate = base_supports[0]["plate"]
            bolt_layout = (
                base_supports[0]
                .get("holding_down_bolts", {})
                .get("layout", {})
            )
            stiffeners = base_supports[0].get("stiffeners", {})
            base_plate_text = (
                f"{base_plates.get('status', 'HOLD_POINT')} | typical "
                f"{float(plate['length_mm']):.0f} Ã— "
                f"{float(plate['width_mm']):.0f} Ã— "
                f"{float(plate['provided_thickness_mm']):.0f} mm | "
                f"{int(bolt_layout.get('bolt_count', 0))} x "
                f"M{float(bolt_layout.get('diameter_mm', 0)):.0f}, "
                f"pitch/gauge {float(bolt_layout.get('pitch_mm', 0)):.0f}/"
                f"{float(bolt_layout.get('gauge_mm', 0)):.0f} mm | "
                + (
                    f"{int(stiffeners.get('count', 0))} stiffeners"
                    if stiffeners.get("required")
                    else "stiffeners not required"
                )
            )
        haunch_connection = connections.get("haunch_connections", {})

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
                "Selected rafter haunch-cut limit",
                (
                    f"{haunches.get('source_rafter_section', sections['rafter'])}: "
                    f"hw + tf = "
                    f"{float(haunches.get('source_clear_web_depth_mm', 0)):.1f} + "
                    f"{float(haunches.get('source_flange_thickness_mm', 0)):.1f} = "
                    f"{float(haunches.get('maximum_cut_depth_mm', 0)):.1f} mm"
                ),
                ft.Icons.STRAIGHTEN,
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
                + (
                    f"Variable vertical {deflection_text(serviceability['max_vertical_deflection_mm'], serviceability.get('vertical_deflection_ratio'), 'Span')} "
                    f"from permanent baseline {float(serviceability.get('permanent_baseline_deflection_mm', 0)):.2f} mm; "
                    if serviceability.get(
                        "uses_permanent_deflection_baseline",
                        True,
                    )
                    else
                    f"Total vertical {deflection_text(serviceability['max_vertical_deflection_mm'], serviceability.get('vertical_deflection_ratio'), 'Span')}; "
                )
                +
                f"total at that node {float(serviceability.get('total_vertical_deflection_mm', 0)):.2f} mm | "
                f"roof drainage {serviceability.get('roof_drainage_status', 'PASS')}"
                + (
                    " | Ignored 1.1 DL + 1.0 LL vertical "
                    f"{float(serviceability['ignored_vertical_deflections'][0]['max_dy']):.2f} mm "
                    "(still reported)"
                    if serviceability.get("ignored_vertical_deflections")
                    else ""
                ),
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
                "Gable columns (selected section and utilisation)",
                gable_text,
                ft.Icons.VERTICAL_ALIGN_CENTER,
            ),
            analysis_summary_line(
                "Bracing members (section and utilisation)",
                brace_text,
                ft.Icons.ACCOUNT_TREE_OUTLINED,
            ),
            analysis_summary_line(
                "Base-plate connection checks",
                base_plate_text,
                ft.Icons.FOUNDATION,
            ),
            analysis_summary_line(
                "Haunch connection design",
                (
                    f"{haunch_connection.get('status', 'NOT_REQUIRED')} | "
                    "bolt geometry, prying, end-plate, weld-group, stiffener "
                    "and supporting member checks calculated"
                ),
                ft.Icons.CALL_MERGE,
            ),
        ]

        artifacts = result.get("artifacts", {})
        report = artifacts.get("design-report-html")
        markup = artifacts.get("markup-pdf") or artifacts.get("markup-html")
        connection_report = artifacts.get("connection-report-html")
        connection_markup = artifacts.get("connection-markup-pdf")
        connection_dxf = artifacts.get("connection-markup-dxf")
        connection_dwg = artifacts.get("connection-markup-dwg")
        prokon_a03 = artifacts.get("prokon-input-a03")
        prokon_json = artifacts.get("prokon-input-json")
        prokon_package = artifacts.get("prokon-package-zip")
        if report:
            view_report_button.url = ft.Url(
                url=f"{API_URL}{report['download_url']}",
                target=ft.UrlTarget.SELF,
            )
            view_report_button.disabled = False
        if markup:
            download_markup_button.url = f"{API_URL}{markup['download_url']}"
            download_markup_button.disabled = False
        if prokon_a03 and prokon_json:
            download_prokon_a03_button.url = f"{API_URL}{prokon_a03['download_url']}"
            download_prokon_json_button.url = f"{API_URL}{prokon_json['download_url']}"
            download_prokon_a03_button.disabled = False
            download_prokon_json_button.disabled = False
        if prokon_package:
            download_prokon_package_button.url = f"{API_URL}{prokon_package['download_url']}"
            download_prokon_package_button.disabled = False
        if connection_markup:
            connection_markup_button.url = ft.Url(
                url=f"{API_URL}{connection_markup['download_url']}",
                target=ft.UrlTarget.BLANK,
            )
            connection_markup_button.disabled = False
        if connection_dxf:
            connection_dxf_button.url = (
                f"{API_URL}{connection_dxf['download_url']}"
            )
            connection_dxf_button.disabled = False
        if connection_dwg:
            connection_dwg_button.url = (
                f"{API_URL}{connection_dwg['download_url']}"
            )
            connection_dwg_button.disabled = False
        export_status = summary.get("connection_exports", {})
        formats = ", ".join(export_status.get("formats", []))
        dwg_status = export_status.get("dwg", {})
        connection_export_status_text.value = (
            f"Calculated 2D exports ready: {formats}. "
            "The interactive 3D model remains in-app only."
            if connection_dwg
            else (
                f"Calculated 2D exports ready: {formats}. "
                f"{dwg_status.get('reason', 'DWG conversion is unavailable.')}"
            )
        )
        if connection_report:
            connection_report_button.url = ft.Url(
                url=f"{API_URL}{connection_report['download_url']}",
                target=ft.UrlTarget.BLANK,
            )
            connection_report_button.disabled = False
        show_connection_results(connections)
        connection_views = list_connection_views(current_connection_design)
        if connection_views:
            preferred_view = next(
                (
                    item
                    for item in connection_views
                    if item["available"]
                ),
                connection_views[0],
            )
            if preferred_view["available"]:
                connection_3d_viewer.content = build_connection_3d_viewer(
                    f"{API_URL}/api/analysis/{current_analysis_id}/"
                    "connection-viewer?view="
                    f"{quote(preferred_view['key'], safe='')}"
                )
                connection_3d_viewer.visible = True
                connection_view_status.value = (
                    "Select a connection in the viewer, drag to orbit and "
                    "scroll to zoom. The model is in-app only and has no "
                    "3D export."
                )
            else:
                connection_3d_viewer.content = None
                connection_3d_viewer.visible = False
                connection_view_status.value = (
                    f"3D view unavailable: {preferred_view['reason']}"
                )
        else:
            connection_3d_viewer.content = None
            connection_3d_viewer.visible = False
            connection_view_status.value = (
                "No connection geometry is available for this analysis."
            )
        open_connections_button.disabled = False

        all_names = combination_names(current_visualisation)
        analysis_view_dropdown.disabled = not all_names
        open_analysis_button.disabled = not all_names
        analysis_destination.disabled = not all_names
        connection_destination.disabled = False
        foundation_destination.disabled = False
        foundation_design_button.disabled = False
        boq_destination.disabled = False
        civil_boq_destination.disabled = False
        civil_boq_generate_button.disabled = False
        civil_boq_download_button.disabled = True
        boq_generate_button.disabled = False
        boq_download_button.disabled = True
        boq_status_card.bgcolor = WARNING_BG
        boq_status_card.content.controls[0].name = ft.Icons.INFO_OUTLINE
        boq_status_card.content.controls[0].color = "#B87900"
        boq_status_text.value = (
            "Analysis quantities are ready. Add any project-specific items, "
            "then create the tender-format workbook."
        )
        foundation_status_card.bgcolor = WARNING_BG
        foundation_status_card.content.controls[0].name = ft.Icons.INFO_OUTLINE
        foundation_status_card.content.controls[0].color = "#B87900"
        foundation_status_text.value = (
            "Portal reactions are ready. Enter soil unit weight and permissible "
            "bearing pressure, then run the automatic foundation design."
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
        nonlocal current_connection_design
        if not validate_form() or last_payload is None:
            return

        current_analysis_id = None
        current_connection_design = {}
        submitted_payload_fingerprint = json.dumps(last_payload, sort_keys=True)
        run_analysis_button.disabled = True
        run_analysis_button.content = "Analysis running..."
        view_report_button.disabled = True
        open_analysis_button.disabled = True
        analysis_destination.disabled = True
        connection_destination.disabled = True
        foundation_destination.disabled = True
        foundation_design_button.disabled = True
        boq_destination.disabled = True
        civil_boq_destination.disabled = True
        civil_boq_generate_button.disabled = True
        civil_boq_download_button.disabled = True
        boq_generate_button.disabled = True
        boq_download_button.disabled = True
        download_markup_button.disabled = True
        download_prokon_a03_button.disabled = True
        download_prokon_json_button.disabled = True
        download_prokon_package_button.disabled = True
        connection_markup_button.disabled = True
        connection_dxf_button.disabled = True
        connection_dwg_button.disabled = True
        connection_report_button.disabled = True
        open_connections_button.disabled = True
        connection_3d_viewer.content = None
        connection_3d_viewer.visible = False
        connection_view_status.value = "Connection model will load after analysis."
        connection_export_status_text.value = (
            "The 2D PDF and DXF are being prepared; AutoCAD DWG conversion "
            "will be attempted if available."
        )
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
                "Steel and loading-code basis",
                f"{building['steel_grade']} • {building['load_combination_standard']}",
                ft.Icons.GAVEL,
            ),
            summary_line(
                "Vertical deflection acceptance",
                (
                    "1.1 DL + 1.0 LL limit ignored; result still reported"
                    if building[
                        "ignore_1_1_dl_1_0_ll_vertical_deflection_limit"
                    ]
                    == "Yes"
                    else "All SLS combinations checked"
                ),
                ft.Icons.SWAP_VERT,
            ),
            summary_line(
                "Wind",
                f"{wind['fundamental_basic_wind_speed']:g} m/s • terrain {wind['terrain_category']} • {wind['return_period']} years",
                ft.Icons.WIND_POWER,
            ),
            summary_line(
                "Additional permanent roof load",
                additional_roof_load_text(building),
                ft.Icons.VERTICAL_ALIGN_BOTTOM,
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
                        f"Eaves L/R "
                        f"{building.get('left_eaves_haunch_length', building['eaves_haunch_length']) / 1000:g}/"
                        f"{building.get('right_eaves_haunch_length', building['eaves_haunch_length']) / 1000:g} m x "
                        + (
                            (
                                "Auto Size (span/15 x max cut)"
                                if building.get("eaves_haunch_depth_mode")
                                == HAUNCH_DEPTH_AUTO
                                else "Cut-Depth (hw + tf)"
                            )
                            if building.get("eaves_haunch_depth_mode")
                            in (HAUNCH_DEPTH_CUT, HAUNCH_DEPTH_AUTO)
                            else f"{building['eaves_haunch_depth']:.0f} mm"
                        )
                        if building["use_eaves_haunch"] == "Yes"
                        else "Eaves none"
                    ),
                    (
                        f"Apex {building['apex_haunch_length'] / 1000:g} m/slope x "
                        + (
                            (
                                "Auto Size (span/15 x max cut)"
                                if building.get("apex_haunch_depth_mode")
                                == HAUNCH_DEPTH_AUTO
                                else "Cut-Depth (hw + tf)"
                            )
                            if building.get("apex_haunch_depth_mode")
                            in (HAUNCH_DEPTH_CUT, HAUNCH_DEPTH_AUTO)
                            else f"{building['apex_haunch_depth']:.0f} mm"
                        )
                        if building["use_apex_haunch"] == "Yes"
                        else "Apex none"
                    ),
                ]),
                ft.Icons.CALL_MERGE,
            ),
            summary_line(
                "Bracing",
                f"{building['column_bracing_type']}-bracing • "
                f"{building['gable_column_count']} evenly spaced gable columns/end • "
                f"{building['gable_column_section'] if building['gable_column_section'] != AUTOMATIC_GABLE_SECTION else building['gable_column_section_order']}",
                ft.Icons.CALL_SPLIT,
            ),
        ]
        if payload["structural_system"] == "Truss":
            truss = payload["truss_data"]
            extra_load = sum(
                float(building.get(key, 0.0) or 0.0)
                for key in (
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

    def sync_auto_haunch_values() -> None:
        """Keep disabled Auto Size fields visibly tied to the current span."""

        try:
            auto_length = float(gable_width.value) / 15.0
        except (TypeError, ValueError):
            return
        if eaves_haunch_depth_mode.value == HAUNCH_DEPTH_AUTO:
            eaves_haunch_length.value = f"{auto_length:g}"
            right_eaves_haunch_length.value = f"{auto_length:g}"
            eaves_haunch_depth.value = ""
        if apex_haunch_depth_mode.value == HAUNCH_DEPTH_AUTO:
            apex_haunch_length.value = f"{auto_length:g}"
            apex_haunch_depth.value = ""

    def update_conditionals(_=None) -> None:
        sync_portal_section_options()
        sync_gable_section_options()
        sync_auto_haunch_values()
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
        truss_additional_loads_card.visible = True
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
        ignore_dead_live_vertical_limit.disabled = False
        use_permanent_deflection_baseline.disabled = False
        eaves_haunch_fields.visible = (
            not is_truss and bool(use_eaves_haunch.value)
        )
        apex_haunch_fields.visible = (
            not is_truss and bool(use_apex_haunch.value)
        )
        eaves_auto_size = eaves_haunch_depth_mode.value == HAUNCH_DEPTH_AUTO
        apex_auto_size = apex_haunch_depth_mode.value == HAUNCH_DEPTH_AUTO
        eaves_haunch_length.disabled = eaves_auto_size
        right_eaves_haunch_length.disabled = eaves_auto_size
        apex_haunch_length.disabled = apex_auto_size
        eaves_haunch_depth.disabled = eaves_haunch_depth_mode.value in (
            HAUNCH_DEPTH_CUT,
            HAUNCH_DEPTH_AUTO,
        )
        apex_haunch_depth.disabled = apex_haunch_depth_mode.value in (
            HAUNCH_DEPTH_CUT,
            HAUNCH_DEPTH_AUTO,
        )
        cut_limit = rafter_haunch_cut_limit(
            str(rafter_section_type.value),
            str(rafter_section.value),
        )
        cut_properties = cut_limit.get("properties", {})
        cut_formula = (
            f"hw + tf = {float(cut_properties.get('hw', 0)):.1f} + "
            f"{float(cut_properties.get('tf', 0)):.1f} = "
            f"{float(cut_limit.get('maximum_cut_depth_mm', 0)):.1f} mm"
        )
        uses_auto_size = (
            bool(use_eaves_haunch.value)
            and eaves_haunch_depth_mode.value == HAUNCH_DEPTH_AUTO
        ) or (
            bool(use_apex_haunch.value)
            and apex_haunch_depth_mode.value == HAUNCH_DEPTH_AUTO
        )
        uses_cut_depth = (
            bool(use_eaves_haunch.value)
            and eaves_haunch_depth_mode.value == HAUNCH_DEPTH_CUT
        ) or (
            bool(use_apex_haunch.value)
            and apex_haunch_depth_mode.value == HAUNCH_DEPTH_CUT
        )
        try:
            auto_length_m = float(gable_width.value) / 15.0
            auto_length_text = f"{auto_length_m:.3f} m"
        except (TypeError, ValueError):
            auto_length_text = "span/15"
        if uses_auto_size and cut_limit.get("mode") == "automatic":
            haunch_cut_guidance.value = (
                f"Auto Size sets each haunch length to {auto_length_text} "
                "and resolves the maximum cut depth (hw + tf) for every "
                "trial rafter. The selected values are reported after analysis."
            )
        elif uses_auto_size and cut_limit.get("mode") == "manual":
            haunch_cut_guidance.value = (
                f"Auto Size sets each haunch length to {auto_length_text}. "
                f"Maximum cut depth for {cut_limit.get('section', '-')}: "
                f"{cut_formula}."
            )
        elif uses_cut_depth and cut_limit.get("mode") == "automatic":
            haunch_cut_guidance.value = (
                "Cut-Depth is resolved for every trial rafter as hw + tf, so "
                "it does not impose a fixed-depth section filter. The selected "
                "value is reported after analysis."
            )
        elif uses_cut_depth and cut_limit.get("mode") == "manual":
            haunch_cut_guidance.value = (
                f"Cut-Depth for selected donor "
                f"{cut_limit.get('section', '-')}: {cut_formula}."
            )
        elif cut_limit.get("mode") == "automatic":
            haunch_cut_guidance.value = (
                "Automatic sizing treats the entered haunch depth as a "
                "section filter and excludes every trial rafter whose usable "
                "donor depth (hw + tf) is too small. The selected rafter and "
                "its actual cut limit are reported after analysis."
            )
        elif cut_limit.get("mode") == "manual":
            haunch_cut_guidance.value = (
                f"Selected donor {cut_limit.get('section', '-')}: maximum "
                f"fabricable cut {cut_formula}."
            )
        else:
            haunch_cut_guidance.value = (
                "Select a valid rafter section to calculate its haunch cut limit."
            )
        haunch_cut_guidance.visible = not is_truss
        gable_column_count.disabled = is_canopy
        gable_brace_intervals.disabled = is_canopy
        gable_section_type.disabled = is_canopy
        gable_section.disabled = is_canopy
        gable_section_order.disabled = (
            is_canopy or gable_section.value != AUTOMATIC_GABLE_SECTION
        )
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
    rafter_section_type.on_select = update_conditionals
    rafter_section.on_select = update_conditionals
    use_eaves_haunch.on_change = update_conditionals
    use_apex_haunch.on_change = update_conditionals
    eaves_haunch_depth_mode.on_select = update_conditionals
    apex_haunch_depth_mode.on_select = update_conditionals
    ignore_dead_live_vertical_limit.on_change = update_conditionals
    use_permanent_deflection_baseline.on_change = update_conditionals
    use_crawl_beams.on_change = update_conditionals
    truss_internal_support.on_select = update_conditionals
    truss_design_centre_columns.on_change = update_conditionals
    truss_centre_column_material.on_select = update_conditionals
    gable_section_type.on_select = update_conditionals
    gable_section.on_select = update_conditionals

    def update_live_input(_=None) -> None:
        sync_auto_haunch_values()
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
        gable_section_type,
        gable_section,
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
                "remain separate design checks. For a like-for-like deflection "
                "comparison, keep the rafter and column sections fixed; Automatic "
                "sizing can exchange the added stiffness for lighter members.",
                ft.Column(
                    spacing=10,
                    controls=[
                        ft.ResponsiveRow(
                            controls=[use_eaves_haunch, use_apex_haunch]
                        ),
                        eaves_haunch_fields,
                        apex_haunch_fields,
                        haunch_cut_guidance,
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
                "Pinned columns are spaced evenly across the gable; the brace interval count controls their unbraced length.",
                ft.ResponsiveRow(
                    controls=[
                        gable_column_count,
                        gable_brace_intervals,
                        gable_section_type,
                        gable_section,
                        gable_section_order,
                    ]
                ),
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
        "Applied to portal-frame rafters or truss panel points as permanent load. Enter characteristic area loads; zero excludes an action.",
        ft.ResponsiveRow(controls=[
            truss_services_load, truss_ceiling_load, truss_solar_load,
            truss_fire_load, truss_hvac_load,
        ]),
    )
    truss_additional_loads_card.visible = True

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
                        truss_member_section_order,
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
                    "Select the SANS 10160 edition set used for the loading design basis. Analysis combinations remain C1 through C6.2.",
                    ft.Column(
                        spacing=10,
                        controls=[
                            ft.ResponsiveRow(
                                controls=[
                                    wind_design_mode,
                                    roof_accessibility,
                                    load_standard,
                                    steel_grade,
                                    report_scope,
                                ]
                            ),
                            use_permanent_deflection_baseline,
                            ft.Text(
                                "When enabled, vertical section sizing uses the "
                                "variable-action displacement relative to the "
                                "matching dead/permanent baseline. Roof fall is "
                                "always checked under total SLS loading to reject "
                                "contraflexure and ponding risk.",
                                size=12,
                                color=TEXT_MUTED,
                            ),
                            ignore_dead_live_vertical_limit,
                            ft.Text(
                                "When enabled, this combination is still analysed "
                                "and reported, but its vertical deflection does not "
                                "reject an automatically selected portal section.",
                                size=12,
                                color=TEXT_MUTED,
                            ),
                        ],
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
                                    download_prokon_a03_button,
                                    download_prokon_json_button,
                                    download_prokon_package_button,
                                    open_connections_button,
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
                    "Connection design",
                    "Post-analysis steel connection calculations using the final "
                    "member sections and governing connection actions. Truss "
                    "analyses include column base plates only.",
                ),
                connection_status_card,
                card(
                    "Calculated connection checks",
                    "The governing utilisation remains visible for each base plate "
                    "and each applicable haunch connection, including failed checks.",
                    connection_result_summary,
                ),
                connection_outputs_card,
                card(
                    "Interactive 3D connection model",
                    "Inspect the calculated members, plates, bolts and flat "
                    "stiffeners in the app. The model is display-only; all "
                    "exported deliverables remain two-dimensional.",
                    ft.Column(
                        spacing=10,
                        controls=[
                            connection_view_status,
                            connection_3d_viewer,
                        ],
                    ),
                ),
                ft.Container(
                    bgcolor=WARNING_BG,
                    border_radius=10,
                    padding=14,
                    content=ft.Text(
                        "DETAIL CONFIRMATION REQUIRED: Red Book HD-bolt anchorage "
                        "is estimated for 25 MPa concrete. Confirm the specified "
                        "embedment, anchor plate, 7d concrete edge distance, "
                        "pedestal geometry and reinforcement. All outputs require "
                        "competent-engineer review.",
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
                        ft.FilledButton(
                            "Continue to foundations",
                            icon=ft.Icons.ARROW_FORWARD,
                            on_click=lambda _: go_to(7),
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
                    "Automatically size identical isolated pads from the completed "
                    "column-base support reactions.",
                ),
                foundation_status_card,
                card(
                    "Required soil inputs",
                    "Enter the project-specific soil parameters. The program calculates "
                    "pad length, width and height while reporting the selected sliding basis.",
                    ft.Column(
                        spacing=10,
                        controls=[
                            ft.ResponsiveRow(
                                controls=[
                                    foundation_bearing,
                                    foundation_concrete,
                                    foundation_soil_weight,
                                    foundation_soil_cover,
                                    foundation_pedestal_height,
                                    foundation_friction,
                                    foundation_sliding,
                                    foundation_soil_friction_angle,
                                    foundation_passive_resistance,
                                    foundation_passive_mobilisation,
                                    foundation_uls_sliding_required_sf,
                                ]
                            ),
                        ],
                    ),
                ),
                card(
                    "Automatic design assumptions",
                    "Reinforcement and loaded-area assumptions remain fixed; automatic "
                    "isolated pads are limited to a 1.5 plan aspect ratio. "
                    "When the pad must resist sliding, the calculation uses the entered "
                    "base-friction and optional passive-pressure inputs. A selected "
                    "external restraint is excluded from pad sizing and remains a design hold point.",
                    ft.Text(
                        "SANS 10100-1 | user-entered concrete strength | 500 MPa reinforcement | "
                        "T16@150 bottom mesh | 75 mm cover | 400 Ã— 400 mm loaded area | "
                        "factor-1.0 characteristic reactions for bearing/stability | "
                        "1.2 foundation self-weight for ULS bearing | 0.9 for stability | "
                        "passive resistance divided by 1.4 at ULS | overturning SF 1.5."
                        if True else ""
                        "ULS sliding and overturning safety factors â‰¥ 1.5.",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                ),
                card(
                    "Foundation results",
                    "The common pad passes service bearing/uplift, ULS sliding and "
                    "overturning, flexure, one-way shear and punching shear.",
                    foundation_result_summary,
                ),
                ft.Container(
                    bgcolor=WARNING_BG,
                    border_radius=10,
                    padding=14,
                    content=ft.Text(
                        "HOLD POINTS: geotechnical bearing and settlement, anchors/base "
                        "plate, pedestal and dowels, development length, exposure "
                        "detailing, whole-building stability and adjacent-foundation interaction "
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
                            "Back to connections",
                            icon=ft.Icons.ARROW_BACK,
                            on_click=lambda _: go_to(6),
                        ),
                        foundation_design_button,
                        ft.FilledButton(
                            "Continue to BOQ",
                            icon=ft.Icons.ARROW_FORWARD,
                            on_click=lambda _: go_to(8),
                        ),
                    ],
                ),
            ],
        ),
        ft.Column(
            spacing=18,
            controls=[
                section_heading(
                    "Structural Steel BOQ",
                    "Create the tender-format steelwork schedule from the completed analysis.",
                ),
                boq_status_card,
                card(
                    "Calculated quantities",
                    "The designer lists each selected section designation separately. Portal frames include rafters and haunches; trusses include chord/web groups and omit haunches. Calculated base plates, columns, purlins, girts, cladding and flashings are included.",
                    ft.Text(
                        "The Excel workbook retains editable rate columns. Member masses use the section databases; sheeting uses the analysed building geometry and entered wall openings.",
                        size=12,
                        color=TEXT_MUTED,
                    ),
                ),
                card(
                    "Additional tender items",
                    "Add project-specific items that are outside the structural model. Leave the rate blank for tenderer pricing.",
                    ft.Column(
                        spacing=12,
                        controls=[
                            boq_additional_items,
                            ft.Row(
                                controls=[
                                    ft.OutlinedButton(
                                        "Add item",
                                        icon=ft.Icons.ADD,
                                        on_click=add_boq_item,
                                    )
                                ]
                            ),
                        ],
                    ),
                ),
                ft.Container(
                    bgcolor=WARNING_BG,
                    border_radius=10,
                    padding=14,
                    content=ft.Text(
                        "REFERENCE BOQ ASSUMPTIONS APPLIED: 0.8mm/0.6mm IBR AZ200 sheeting, 82° bullnose to 450mm radius, 600mm-girth ridge cap, SANS 121 galvanising and 4.5% erection-bolt allowance are carried through from the supplied BOQs.",
                        color="#745B2B",
                        weight=ft.FontWeight.BOLD,
                    ),
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    wrap=True,
                    controls=[
                        ft.OutlinedButton(
                            "Back to foundations",
                            icon=ft.Icons.ARROW_BACK,
                            on_click=lambda _: go_to(7),
                        ),
                        boq_generate_button,
                        boq_download_button,
                    ],
                ),
            ],
        ),
        civil_boq_page,
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
    connection_destination = ft.NavigationRailDestination(
        icon=ft.Icon(ft.Icons.HARDWARE_OUTLINED, color="#506A67"),
        selected_icon=ft.Icon(ft.Icons.HARDWARE, color=ACCENT_DARK),
        label="Connections",
        disabled=True,
    )
    foundation_destination = ft.NavigationRailDestination(
        icon=ft.Icon(ft.Icons.FOUNDATION_OUTLINED, color="#506A67"),
        selected_icon=ft.Icon(ft.Icons.FOUNDATION, color=ACCENT_DARK),
        label="Foundations",
        disabled=True,
    )
    boq_destination = ft.NavigationRailDestination(
        icon=ft.Icon(ft.Icons.TABLE_VIEW_OUTLINED, color="#506A67"),
        selected_icon=ft.Icon(ft.Icons.TABLE_VIEW, color=ACCENT_DARK),
        label="Structural BOQ",
        disabled=True,
    )
    civil_boq_destination = ft.NavigationRailDestination(
        icon=ft.Icon(ft.Icons.CONSTRUCTION_OUTLINED, color="#506A67"),
        selected_icon=ft.Icon(ft.Icons.CONSTRUCTION, color=ACCENT_DARK),
        label="Civil BOQ",
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
            connection_destination,
            foundation_destination,
            boq_destination,
            civil_boq_destination,
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
        visual_builder.visible = index not in (5, 6, 7, 8, 9)
        running_summary_panel.visible = index not in (5, 6, 7, 8, 9)
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
                        ft.OutlinedButton(
                            "Load inputs",
                            icon=ft.Icons.UPLOAD_FILE,
                            on_click=load_inputs,
                        ),
                        ft.OutlinedButton(
                            "Save inputs",
                            icon=ft.Icons.SAVE_OUTLINED,
                            on_click=save_inputs,
                        ),
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
