import unittest

from prokon_results import compare_results, parse_fout


class ProkonResultTests(unittest.TestCase):
    def test_parser_keeps_continuation_node_number(self):
        # The checked-in workspace result is optional because it is user output.
        try:
            result = parse_fout("output/prokon/current/f.out")
        except FileNotFoundError:
            self.skipTest("No Prokon f.out is available.")
        self.assertEqual(result["sls_displacements"][0]["node"], 1)
        self.assertEqual(result["sls_displacements"][1]["node"], 1)
        self.assertEqual(result["sls_displacements"][1]["combination_id"], "PF02")
        self.assertTrue(result["uls_reactions"])

    def test_comparison_matches_aliases_and_source_nodes(self):
        parsed = {
            "title": "PortalFrame comparison analysis id abc",
            "sls_displacements": [
                {"node": 2, "combination_id": "PF01", "dx_mm": -4.0, "dy_mm": -3.0},
                {"node": 3, "combination_id": "PF01", "dx_mm": 2.0, "dy_mm": -5.0},
            ],
            "uls_reactions": [
                {"node": 1, "combination_id": "PF01", "fx_kn": 9.0, "fy_kn": 21.0, "mz_knm": -4.0},
            ],
            "sls_reactions": [],
        }
        model = {
            "analysis_id": "abc",
            "nodes": [
                {"id": 1, "source_name": "N1"},
                {"id": 2, "source_name": "N2"},
                {"id": 3, "source_name": "N3"},
            ],
            "load_combinations": [{"id": "PF01", "uls_name": "ULS A", "sls_name": "SLS A"}],
        }
        snapshot = {"results": {
            "deflections": [{
                "load_combination": "SLS A",
                "max_dx": 4.2,
                "dx_node": "N2",
                "max_dy": 1.1,
                "dy_node": "N3",
                "total_max_dy": 5.1,
                "total_dy_node": "N3",
            }],
            "reactions": [{"node": "N1", "load_combination": "ULS A", "fx": 10.0, "fy": 20.0, "fz": 0, "mx": 0, "my": 0, "mz": -5.0}],
        }}
        result = compare_results(parsed, model, snapshot)
        self.assertEqual(len(result["deflections"]), 2)
        self.assertEqual(result["deflections"][0]["prokon_node"], "N2")
        self.assertEqual(len(result["uls_reactions"]), 3)
        self.assertAlmostEqual(result["uls_reactions"][0]["difference"], -1.0)


if __name__ == "__main__":
    unittest.main()
