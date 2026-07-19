"""First browser/desktop Flet draft for PortalFrame."""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any

import flet as ft
import httpx

from preview_geometry import build_preview_geometry
from ui.analysis_render import combination_names, load_case_svg
from ui.input_model import (
    AUTOMATIC_SECTION,
    BASE_SUPPORTS,
    BUILDING_TYPES,
    COLUMN_BRACING_TYPES,
    CRAWL_APPLICATIONS,
    DEFAULT_VALUES,
    LIPPED_CHANNEL_SECTIONS,
    LOAD_COMBINATION_STANDARDS,
    PORTAL_SECTION_FAMILIES,
    PORTAL_SECTIONS_BY_FAMILY,
    ROOF_ACCESSIBILITY,
    ROOF_TYPES,
    STEEL_GRADES,
    TERRAIN_CATEGORIES,
    WIND_DESIGN_MODES,
    InputValidationError,
    build_analysis_payload,
)
from ui.preview_render import (
    frame_elevation_svg,
    roof_plan_svg,
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
    page.title = "PortalFrame Designer"
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
            if component == "total deflection":
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
        return {
            key: control.value
            for key, control in controls.items()
        }

    def set_validation_error(key: str, message: str) -> None:
        control = controls.get(key)
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
            preview = build_preview_geometry(payload)
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
        analysis_progress.visible = False
        analysis_status_card.bgcolor = ERROR_BG
        analysis_status_icon.visible = True
        analysis_status_icon.name = ft.Icons.ERROR_OUTLINE
        analysis_status_icon.color = "#C43D34"
        analysis_status_text.value = message
        run_analysis_button.disabled = False
        run_analysis_button.content = "Run analysis"
        analysis_destination.disabled = True
        page.update()

    def show_analysis_results(result: dict[str, Any]) -> None:
        nonlocal current_visualisation
        summary = result["design_summary"]
        sections = summary["portal_sections"]
        strength = summary["governing_strength"]
        serviceability = summary["serviceability"]
        mass = summary.get("steel_mass_breakdown", {})
        portal_mass = mass.get("portal_frames", {}).get("mass_kg", 0)
        bracing_mass = mass.get("bracing", {}).get("mass_kg", 0)
        gable_mass = mass.get("gable_columns", {}).get("mass_kg", 0)
        purlin_mass = mass.get("purlins", {}).get("mass_kg", 0)
        total_mass = mass.get("total_steel_mass_kg", 0)
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
                "Governing strength check",
                f"{strength['member']} | {strength['combination']} | "
                f"{strength['check']}",
                ft.Icons.QUERY_STATS,
            ),
            analysis_summary_line(
                "Serviceability results",
                f"Horizontal {float(serviceability['max_horizontal_deflection_mm']):.2f} mm | "
                f"Vertical {float(serviceability['max_vertical_deflection_mm']):.2f} mm",
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
        nonlocal submitted_payload_fingerprint
        if not validate_form() or last_payload is None:
            return

        submitted_payload_fingerprint = json.dumps(last_payload, sort_keys=True)
        run_analysis_button.disabled = True
        run_analysis_button.content = "Analysis running..."
        view_report_button.disabled = True
        open_analysis_button.disabled = True
        analysis_destination.disabled = True
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
                "Bracing",
                f"{building['column_bracing_type']}-bracing • {building['gable_column_count']} gable columns/end",
                ft.Icons.CALL_SPLIT,
            ),
        ]
        json_preview.value = json.dumps(payload, indent=2)
        page.update()
        return True

    def update_conditionals(_=None) -> None:
        sync_portal_section_options()
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
        gable_column_count.disabled = is_canopy
        gable_brace_intervals.disabled = is_canopy
        crawl_application.disabled = not use_crawl_beams.value
        update_pitch()
        refresh_workspace(update_page=False)
        page.update()

    building_type.on_select = update_conditionals
    building_roof.on_select = update_conditionals
    wind_design_mode.on_select = update_conditionals
    base_support.on_select = update_conditionals
    use_crawl_beams.on_change = update_conditionals

    def update_live_input(_=None) -> None:
        update_pitch()
        refresh_workspace()

    conditional_dropdowns = {
        building_type,
        building_roof,
        wind_design_mode,
        base_support,
        rafter_section_type,
        column_section_type,
    }
    for live_control in controls.values():
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
                    ft.ResponsiveRow(
                        controls=[building_type_field, building_roof_field]
                    ),
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
                card(
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
                footer_buttons(0, 2),
            ],
        ),
        ft.Column(
            spacing=18,
            controls=[
                section_heading(
                    "Design basis & wind",
                    "Select code-defined choices and enter site-specific numerical values.",
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
                    "Frame & secondary steel",
                    "Configure restraints, bracing topology, gables, purlins, girts and crawl loading.",
                ),
                card(
                    "Portal member sections",
                    "Choose automatic mass-ordered sizing or force a database section for checking.",
                    ft.ResponsiveRow(
                        controls=[
                            rafter_section_type,
                            rafter_section,
                            column_section_type,
                            column_section,
                        ]
                    ),
                ),
                card(
                    "Portal support and bracing",
                    "Integer fields represent counts of modelled intervals or panels.",
                    ft.ResponsiveRow(
                        controls=[
                            base_support,
                            spring_stiffness,
                            col_bracing_spacing,
                            column_bracing_type,
                            rafter_bracing_spacing,
                        ]
                    ),
                ),
                card(
                    "Gable columns",
                    "Gables are pinned; the brace interval count controls their unbraced length.",
                    ft.ResponsiveRow(controls=[gable_column_count, gable_brace_intervals]),
                ),
                card(
                    "Purlins and girts",
                    "Sections are searchable dropdowns sourced from the Lipped Channels database.",
                    ft.ResponsiveRow(
                        controls=[purlin_section, purlin_spacing, girt_section, girt_spacing]
                    ),
                ),
                card(
                    "Crawl beam loading",
                    "The detailed crawl library remains in crawl_beam_inputs.py for this draft.",
                    ft.ResponsiveRow(controls=[use_crawl_beams, crawl_application]),
                ),
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
                    "Portal frame",
                    "The selected engineering quantity is labelled directly on a dedicated frame diagram.",
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
                label="Design & wind",
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
        visual_builder.visible = index != 5
        running_summary_panel.visible = index != 5
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
                            "Portal frame design",
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


if __name__ == "__main__":
    ft.run(main)
