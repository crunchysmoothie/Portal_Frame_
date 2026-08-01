import base64
import gzip
import json
from pathlib import Path
import unittest

from prokon_export import (
    DEFAULT_TEMPLATE,
    build_portal_comparison,
    build_truss_comparison,
    render_a03,
)


class ProkonExportTests(unittest.TestCase):
    def test_packaged_seed_is_a_prokon_v12_file(self):
        encoded = "".join(DEFAULT_TEMPLATE.read_text(encoding="ascii").split())
        seed = gzip.decompress(base64.b64decode(encoded))
        self.assertTrue(seed.startswith(b"Frame Analysis - Ver W5.3.13"))
        self.assertIn(b"File Version:12", seed[:100])

    def test_portal_snapshot_maps_selected_sections_and_model_tables(self):
        snapshot_path = Path("output/analysis/analysis_results.json")
        if not snapshot_path.exists():
            self.skipTest("No completed local portal snapshot is available.")
        model = build_portal_comparison(json.loads(snapshot_path.read_text(encoding="utf-8")))
        self.assertEqual(model["structural_system"], "Portal frame")
        self.assertGreaterEqual(len(model["nodes"]), 3)
        self.assertGreaterEqual(len(model["members"]), 2)
        self.assertTrue({"COL", "RFT"}.issubset({item["name"] for item in model["sections"]}))
        self.assertTrue(model["load_combinations"])
        self.assertTrue(all(len(alias) <= 6 for alias in model["load_case_map"].values()))
        self.assertEqual(len(set(model["load_case_map"].values())), len(model["load_case_map"]))
        member_load = next(item for item in model["member_loads"] if "w1_kn_m" in item)
        self.assertGreater(abs(member_load["w1_kn_m"]), 0.01)
        spring = next((item for item in model["supports"] if item["rz_spring_knm_per_rad"] is not None), None)
        if spring:
            self.assertGreater(spring["rz_spring_knm_per_rad"], 100.0)
        rendered = render_a03(model)
        marker = b"Modeller underlay file name:\r\n"
        text_end = rendered.find(marker) + len(marker)
        text = rendered[:text_end].decode("latin-1")
        self.assertIn("TITLE : PortalFrame comparison", text)
        self.assertIn("|PF01", text)
        self.assertIn("|D     |                       |", text)
        self.assertIn("|7  |Steel:S355JR      | 200.0E6|              0.3|   78.5000|", text)
        if spring:
            self.assertIn("10E3", text)
        self.assertNotIn("Projects Misc", text)
        encoded = "".join(DEFAULT_TEMPLATE.read_text(encoding="ascii").split())
        seed = gzip.decompress(base64.b64decode(encoded))
        seed_end = seed.find(marker) + len(marker)
        self.assertEqual(rendered[text_end:], seed[seed_end:])

    def test_local_load_is_reoriented_for_prokon_node_order(self):
        snapshot_path = Path("output/analysis/analysis_results.json")
        if not snapshot_path.exists():
            self.skipTest("No completed local portal snapshot is available.")
        model = build_portal_comparison(json.loads(snapshot_path.read_text(encoding="utf-8")))
        right_column = next(
            load for load in model["member_loads"]
            if load["source_member"] == "M6" and load["case"] == "W90_0.2"
        )
        self.assertGreater(right_column["node_path"][0], right_column["node_path"][1])
        self.assertLess(right_column["w1_kn_m"], 0.0)

    def test_truss_export_uses_panel_nodes_and_end_releases(self):
        result = {
            "analysis_id": "test123",
            "ranked_solutions": [{
                "geometry": {
                    "left_support": "T0", "right_support": "T1",
                    "nodes": [
                        {"name": "T0", "x_mm": 0, "y_mm": 0},
                        {"name": "T1", "x_mm": 1000, "y_mm": 0},
                    ],
                    "members": [{"name": "TC1", "i_node": "T0", "j_node": "T1"}],
                },
                "member_schedule": [{
                    "member": "TC1",
                    "section": {"designation": "L 50x50x5", "area_mm2": 480, "rx_mm": 15, "ry_mm": 15},
                }],
                "load_audit": {
                    "characteristic_node_loads_kn": {"D": {"T0": [0, -1], "T1": [0, -1]}},
                    "uls_combinations": [{"name": "1.35 DL", "factors": {"D": 1.35}}],
                    "sls_combinations": [{"name": "1.0 DL", "factors": {"D": 1.0}}],
                },
            }],
        }
        model = build_truss_comparison(result)
        self.assertEqual(model["members"][0]["release_i"], "T")
        self.assertEqual(model["members"][0]["release_j"], "T")
        self.assertEqual(len(model["nodal_loads"]), 0)
        self.assertEqual(model["supports"][1]["fixity"], "Y")
        self.assertEqual(model["analysis"]["self_weight_case"], "D")
        self.assertFalse(any(load["case"] == "D" for load in model["nodal_loads"]))
        rendered = render_a03(model)
        self.assertIn(b" Self weight to be added to:D\r\n", rendered)


if __name__ == "__main__":
    unittest.main()
