import math

import user_input
import portal_frame_analysis


def main() -> None:
    """Generate input/load data from local settings, then run analysis."""

    # Update these values in THIS file as needed.
    building_roof = "Duo Pitched"     # "Mono Pitched" or "Duo Pitched"
    building_type = "Normal"          # "Normal" or "Canopy"
    roof_accessibility = "Inaccessible"  # "Accessible" or "Inaccessible"
    load_combination_standard = "SANS 10160-1:2019"  # "SANS 10160-1:2019" or "Pre-2019"
    blocking_factor = 0.0             # Canopy only: 0.0 (open) to 1.0 (fully blocked)
    eaves_height = 6.5 * 1000
    apex_height = 8.09 * 1000
    gable_width = 18 * 1000
    rafter_spacing = 6 * 1000
    building_length = 42 * 1000
    col_bracing_spacing = 1
    rafter_bracing_spacing = 3
    steel_grade = "Steel_S355"

    roof_span = gable_width / 2 if building_roof == "Duo Pitched" else gable_width

    building_data = {
        "building_type": building_type,
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
        "rafter_bracing_spacing": rafter_bracing_spacing,
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

    snapshot_path = portal_frame_analysis.main()
    if snapshot_path is not None:
        print(
            "Stored analysis is ready for reporting. Run "
            "'.\\.venv314\\Scripts\\python.exe design_calculations.py' to "
            "generate the report without "
            "reanalysing the frame."
        )


if __name__ == "__main__":
    main()
