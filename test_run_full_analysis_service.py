import unittest
from unittest.mock import patch

from run_full_analysis import run_analysis


class RunFullAnalysisServiceTests(unittest.TestCase):
    @patch("run_full_analysis.portal_frame_analysis.main")
    @patch("run_full_analysis.user_input.add_dead_loads")
    @patch("run_full_analysis.user_input.add_live_loads")
    @patch("run_full_analysis.user_input.add_wind_member_loads")
    @patch("run_full_analysis.user_input.update_json_file")
    def test_callable_workflow_uses_isolated_paths_and_disables_rendering(
        self, update, wind, live, dead, analyse
    ):
        analyse.return_value = "job/analysis_results.json"
        building = {"use_crawl_beams": "No"}
        wind_data = {"wind": "3s gust"}

        result = run_analysis(
            building,
            wind_data,
            input_path="job/input_data.json",
            snapshot_path="job/analysis_results.json",
            render=False,
            project_metadata={"name": "Test"},
        )

        self.assertEqual(result, "job/analysis_results.json")
        update.assert_called_once()
        wind.assert_called_once_with("job/input_data.json")
        live.assert_called_once_with("job/input_data.json")
        dead.assert_called_once_with("job/input_data.json")
        analyse.assert_called_once_with(
            render=False,
            snapshot_path="job/analysis_results.json",
            input_path="job/input_data.json",
            project_metadata={"name": "Test"},
        )


if __name__ == "__main__":
    unittest.main()
