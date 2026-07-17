import math

import user_input
import portal_frame_analysis


def main(render: bool = True) -> None:
    """Generate input/load data from local settings, then run analysis."""

    # Update these values in THIS file as needed.
    building_roof = "Duo Pitched"     # "Mono Pitched" or "Duo Pitched"
    building_type = "Normal"          # "Normal" or "Canopy"
    wind_design_mode = "Prelim"       # "Prelim" or "Final design"
    roof_accessibility = "Inaccessible"  # "Accessible" or "Inaccessible"
    load_combination_standard = "SANS 10160-1:2019"  # "SANS 10160-1:2019" or "Pre-2019"
    blocking_factor = 0.0             # Canopy only: 0.0 (open) to 1.0 (fully blocked)
    eaves_height = 6.5 * 1000
    apex_height = 8.09 * 1000
    gable_width = 18 * 1000
    rafter_spacing = 6 * 1000
    building_length = 42 * 1000
    col_bracing_spacing = 1
    column_bracing_type = "X"       # "X" uses angles; "K" or "A" uses CHS
    # CFLC format: depth x flange x lip x thickness, e.g. 125x50x20x2.5.
    purlin_section = "175x65x20x2.5"
    purlin_max_spacing_mm = 1536
    roof_bracing_purlin_interval = 3  # 1=every purlin, 2=every second, etc.
    girt_section = "175x65x20x2.5"
    girt_max_spacing_mm = 1536
    # Recalculated from purlin_max_spacing_mm by update_json_file().
    rafter_bracing_spacing = 2
    # Gable-column count for one gable end. Use 1, 3, 5, ...: the apex column
    # is always present and each increase adds one symmetric column per side.
    gable_column_count = 3
    # Number of equal unbraced intervals over each pinned gable-column height.
    gable_column_brace_intervals = 2
    steel_grade = "Steel_S355"

    roof_span = gable_width / 2 if building_roof == "Duo Pitched" else gable_width

    building_data = {
        "building_type": building_type,
        "wind_design_mode": wind_design_mode,

        "opening_areas_m2": {
            "side_1": 0.0,
            "side_2": 0.0,
            "gable_1": 0.0,
            "gable_2": 0.0,
        },
        "building_roof": building_roof,
        "roof_accessibility": roof_accessibility,
        "load_combination_standard": load_combination_standard,
        "blocking_factor": blocking_factor,
        "eaves_height": eaves_height,
        "apex_height": apex_height,
        "gable_width": gable_width,
        "rafter_spacing": rafter_spacing,
        "building_length": building_length,
        "col_bracing_spacing": col_bracing_spacing,
        "column_bracing_type": column_bracing_type,
        "rafter_bracing_spacing": rafter_bracing_spacing,
        "purlin_section": purlin_section,
        "purlin_max_spacing_mm": purlin_max_spacing_mm,
        "roof_bracing_purlin_interval": roof_bracing_purlin_interval,
        "girt_section": girt_section,
        "girt_max_spacing_mm": girt_max_spacing_mm,
        "gable_column_count": gable_column_count,
        "gable_column_brace_intervals": gable_column_brace_intervals,
        "roof_pitch": math.degrees(math.atan((apex_height - eaves_height) / roof_span)),
        "steel_grade": steel_grade,
    }

    wind_data = {
        "wind": "3s gust",
        "fundamental_basic_wind_speed": 32,
        "return_period": 50,
        "terrain_category": "B",
        "topographic_factor": 1.0,
        "altitude": 830,
    }

    json_filename = "input_data.json"

    user_input.update_json_file(json_filename, building_data, wind_data)
    user_input.add_wind_member_loads(json_filename)
    user_input.add_live_loads(json_filename)
    user_input.add_dead_loads(json_filename)

    snapshot_path = portal_frame_analysis.main(render=render)
    if snapshot_path is not None:
        print(
            "Stored analysis is ready for reporting. Run "
            "'.\\.venv314\\Scripts\\python.exe design_calculations.py' to "
            "generate the report without "
            "reanalysing the frame."
        )


if __name__ == "__main__":
    main()
