"""First browser/desktop Flet draft for PortalFrame."""

from __future__ import annotations

import json
import math
from typing import Any

import flet as ft
import httpx

from ui.input_model import (
    BASE_SUPPORTS,
    BUILDING_TYPES,
    COLUMN_BRACING_TYPES,
    CRAWL_APPLICATIONS,
    DEFAULT_VALUES,
    LIPPED_CHANNEL_SECTIONS,
    LOAD_COMBINATION_STANDARDS,
    ROOF_ACCESSIBILITY,
    ROOF_TYPES,
    STEEL_GRADES,
    TERRAIN_CATEGORIES,
    WIND_DESIGN_MODES,
    InputValidationError,
    build_analysis_payload,
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
    project_name = text_field("project_name", "Project name", col={"sm": 12, "md": 6})
    project_number = text_field(
        "project_number", "Project number", col={"sm": 12, "md": 3}
    )
    designer = text_field("designer", "Designer", col={"sm": 12, "md": 3})
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
        helper="Requested panel count; purlin spaces are distributed automatically.",
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
        "purlin_max_spacing_mm", "Maximum purlin spacing", unit="mm"
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
                "Bracing",
                f"{building['column_bracing_type']}-bracing • {building['gable_column_count']} gable columns/end",
                ft.Icons.CALL_SPLIT,
            ),
        ]
        json_preview.value = json.dumps(payload, indent=2)
        page.update()
        return True

    def update_conditionals(_=None) -> None:
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
        page.update()

    building_type.on_select = update_conditionals
    building_roof.on_select = update_conditionals
    wind_design_mode.on_select = update_conditionals
    base_support.on_select = update_conditionals
    use_crawl_beams.on_change = update_conditionals

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
                    ft.ResponsiveRow(controls=[building_type, building_roof]),
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
                                "Design summary",
                                "The summary refreshes after successful validation.",
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
                        ft.FilledButton(
                            "Run analysis",
                            icon=ft.Icons.PLAY_ARROW,
                            disabled=True,
                            tooltip="Enabled after POST /api/analysis is implemented.",
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
                        ft.Container(
                            expand=True,
                            padding=24,
                            content=content_host,
                        ),
                    ],
                ),
            ],
        )
    )
    update_conditionals()
    update_pitch()


if __name__ == "__main__":
    ft.run(main)
