import tempfile
import unittest
from pathlib import Path

from portal_workflow.inputs import add_load_cases, display_load_case_name
from portal_workflow.prokon_export import (
    build_gable_columns_comparison,
    build_girder_comparison,
    build_truss_comparison,
    write_comparison_bundle,
)


def _audit():
    _, sls, uls = add_load_cases()
    return {
        "characteristic_node_loads_kn": {
            "D": {"B0": [0.0, -1.0], "B1": [0.0, -1.0]},
            "D_MAX": {"B0": [0.0, -2.0], "B1": [0.0, -2.0]},
            "L": {"B0": [0.0, -0.5], "B1": [0.0, -0.5]},
        },
        "uls_combinations": uls,
        "sls_combinations": sls,
    }


def _truss_result():
    geometry = {
        "nodes": [
            {"name": "B0", "x_mm": 0.0, "y_mm": 0.0},
            {"name": "B1", "x_mm": 10000.0, "y_mm": 0.0},
        ],
        "members": [{"name": "BC1", "i_node": "B0", "j_node": "B1"}],
        "left_support": "B0", "right_support": "B1",
        "support_nodes": ["B0", "B1"],
    }
    section = {
        "designation": "50x50x5 EA", "area_mm2": 480.0,
        "rx_mm": 15.0, "ry_mm": 15.0, "mass_kg_m": 3.8,
    }
    best = {
        "geometry": geometry,
        "member_schedule": [{"member": "BC1", "section": section}],
        "load_audit": _audit(),
        "eave_column_design": {"height_mm": 6000.0},
        "building_layout": {"support_arrangement": {"internal_support": "Not required"}},
        "bearing_support_verticals": [
            {"bearing_node": "B0", "section": {"designation": "203x133x25"}},
            {"bearing_node": "B1", "section": {"designation": "203x133x25"}},
        ],
        "girder_design": {"status": "NOT_REQUIRED"},
    }
    return {"analysis_id": "test", "ranked_solutions": [best]}


class ProkonExportModelTests(unittest.TestCase):
    def test_project_combination_table_and_labels(self):
        _, sls, uls = add_load_cases()
        self.assertEqual([item["name"] for item in uls], [
            "C1", "C2", "C3.1", "C3.2", "C3.3", "C3.4",
            "C4.1", "C4.2", "C4.3", "C4.4", "C5.1", "C5.2", "C6.1", "C6.2",
        ])
        self.assertEqual([item["name"] for item in sls], [item["name"] for item in uls])
        self.assertEqual(display_load_case_name("D_MAX"), "DLMAX")
        self.assertEqual(display_load_case_name("W90_0.3"), "W9.3")
        self.assertEqual(uls[0]["factors"], {"D": 1.5, "D_MAX": 1.5})
        self.assertEqual(sls[-1]["factors"]["W90_0.2"], 0.6)

    def test_truss_only_and_with_columns_write_separate_models(self):
        result = _truss_result()
        truss = build_truss_comparison(result)
        combined = build_truss_comparison(result, include_columns=True)
        self.assertEqual(len(combined["members"]), len(truss["members"]) + 2)
        self.assertEqual({item["source_name"] for item in combined["nodes"] if item["source_name"].startswith("BASE-")}, {"BASE-B0", "BASE-B1"})
        self.assertEqual([item["id"] for item in truss["load_combinations"]], [
            "C1", "C2", "C3.1", "C3.2", "C3.3", "C3.4",
            "C4.1", "C4.2", "C4.3", "C4.4", "C5.1", "C5.2", "C6.1", "C6.2",
        ])
        with tempfile.TemporaryDirectory() as directory:
            bundle = write_comparison_bundle({"truss": truss, "combined": combined}, directory)
            self.assertTrue(bundle["zip"].is_file())
            self.assertTrue((Path(directory) / "truss_prokon_input.A03").is_file())
            self.assertTrue((Path(directory) / "truss_with_columns_prokon_input.A03").is_file())

    def test_gable_model_uses_calculated_sections_and_w90_cases(self):
        truss = build_truss_comparison(_truss_result())
        bracing = {
            "pressure_cases": [
                {"case": "W90_0.2", "pressure_kpa": 0.8},
                {"case": "W90_0.3", "pressure_kpa": 1.0},
            ],
            "gable_columns": [{
                "name": "GC1", "x_mm": 5000.0, "height_mm": 7000.0,
                "tributary_width_mm": 5000.0, "section_type": "I-Sections",
                "section": "203x133x25",
            }],
        }
        model = build_gable_columns_comparison(bracing, truss["load_combinations"])
        self.assertIsNotNone(model)
        self.assertEqual(model["load_case_map"]["W90_0.3"], "W9.3")
        self.assertEqual(len(model["member_loads"]), 2)
        self.assertAlmostEqual(model["member_loads"][1]["w1_kn_m"], 5.0)

    def test_no_girder_model_when_not_required(self):
        self.assertIsNone(build_girder_comparison(_truss_result()))


if __name__ == "__main__":
    unittest.main()
