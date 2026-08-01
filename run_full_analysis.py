import user_input
import portal_frame_analysis
from crawl_beam_inputs import crawl_beam_library


def run_analysis(
    building_data,
    wind_data,
    *,
    input_path="input_data.json",
    snapshot_path="output/analysis/analysis_results.json",
    render=False,
    project_metadata=None,
):
    """Generate one isolated input file and run the complete design workflow."""

    building_data = dict(building_data)
    if "crawl_beams" not in building_data:
        building_data["crawl_beams"] = crawl_beam_library()

    user_input.update_json_file(input_path, building_data, dict(wind_data))
    user_input.add_wind_member_loads(input_path)
    user_input.add_live_loads(input_path)
    user_input.add_dead_loads(input_path)

    return portal_frame_analysis.main(
        render=render,
        snapshot_path=snapshot_path,
        input_path=input_path,
        project_metadata=project_metadata,
    )
