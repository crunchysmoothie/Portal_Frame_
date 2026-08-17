import tempfile
import unittest
from pathlib import Path

from foundation_workflow.design import (
    DEFAULT_FOUNDATION_VALUES,
    FoundationInputError,
    _validated_inputs,
    design_pad_foundations,
)
from foundation_workflow.report import (
    build_foundation_report_html,
    write_foundation_report_html,
)
from reporting_workflow.markup import build_markup_html


def _foundation_result(plan_shape: str = "Rectangular") -> dict:
    return {
        "schema_version": 2,
        "status": "PASS",
        "standard": "SANS 10100-1",
        "mode": "automatic_common_pad",
        "whole_building_support_count": 10,
        "inputs": {
            "standard": "SANS 10100-1",
            "plan_shape": plan_shape,
            "length_m": 3.0,
            "width_m": 3.0 if plan_shape == "Square" else 2.0,
            "thickness_mm": 450.0,
            "loaded_length_mm": 400.0,
            "loaded_width_mm": 400.0,
            "pedestal_height_m": 0.6,
            "concrete_strength_mpa": 25.0,
            "rebar_strength_mpa": 500.0,
            "bar_diameter_mm": 16.0,
            "bar_spacing_mm": 150.0,
            "cover_mm": 75.0,
            "permissible_bearing_kpa": 150.0,
            "base_depth_m": 0.75,
            "soil_cover_depth_m": 0.3,
            "friction_coefficient": 0.45,
            "passive_resistance": "Passive Resistance Excluded",
        },
        "automatic_design": {
            "plan_shape": plan_shape,
            "length_m": 3.0,
            "width_m": 3.0 if plan_shape == "Square" else 2.0,
            "height_mm": 450.0,
            "plan_aspect_ratio": 1.0 if plan_shape == "Square" else 1.5,
            "maximum_plan_aspect_ratio": 1.5,
        },
        "derived": {
            "footing_volume_m3": 2.7,
            "footing_self_weight_kN": 64.8,
            "soil_cover_weight_kN": 31.5,
            "pedestal_self_weight_kN": 2.3,
            "effective_depth_mm": 367.0,
            "provided_steel_mm2_per_m": 1340.4,
            "passive_coefficient_kp": 2.464,
        },
        "supports": [],
        "assumptions": ["One common isolated pad is used."],
        "warnings": ["Geotechnical confirmation is required."],
        "references": ["SANS 10100-1."],
    }


def _markup_data(foundation=None) -> dict:
    data = {
        "project": {
            "name": "Foundation markup test",
            "gable_width_mm": 16000.0,
            "eaves_height_mm": 6500.0,
            "apex_height_mm": 7500.0,
            "rafter_spacing_mm": 6000.0,
            "building_length_mm": 48000.0,
            "roof_type": "Duo Pitched",
            "purlin_section": "125x50x20x2.5",
            "girt_section": "125x50x20x2.5",
            "purlin_max_spacing_mm": 1600.0,
            "girt_max_spacing_mm": 1800.0,
            "rafter_bracing_spacing": 2,
            "column_bracing_type": "X",
            "column_section": "356x171x51",
            "rafter_section": "356x171x45",
        },
        "bracing_design": {
            "inputs": {"rafter_bracing_spacing_count": 2},
            "bracing_members": [],
            "gable_layout": {"columns": []},
            "gable_columns": [],
            "column_bracing_layout": {"type": "X", "panel_count": 1},
        },
    }
    if foundation is not None:
        data["foundation_design"] = foundation
    return data


class FoundationGeometryTests(unittest.TestCase):
    def test_automatic_square_search_keeps_equal_plan_dimensions(self):
        snapshot = {
            "input_data": {
                "load_combinations": [{"name": "ULS"}],
                "serviceability_load_combinations": [{"name": "SLS"}],
            },
            "results": {
                "reactions": [
                    {"node": "BASE", "load_combination": "ULS", "fx": 1.0, "fy": 20.0, "mz": 1.0},
                    {"node": "BASE", "load_combination": "SLS", "fx": 1.0, "fy": 15.0, "mz": 1.0},
                ],
                "foundation_characteristic_reactions": [
                    {"node": "BASE", "load_combination": "CHAR", "fx": 1.0, "fy": 15.0, "mz": 1.0}
                ],
            },
        }
        result = design_pad_foundations(snapshot, {
            "foundation_plan_shape": "Square",
            "foundation_soil_unit_weight_kn_m3": 18.0,
            "foundation_permissible_bearing_kpa": 150.0,
            "foundation_concrete_strength_mpa": 25.0,
            "foundation_soil_cover_depth_m": 0.3,
            "foundation_pedestal_height_m": 0.6,
            "foundation_friction_coefficient": 0.45,
            "foundation_sliding_resistance": "Sliding Resisted",
            "foundation_soil_friction_angle_deg": 25.0,
            "foundation_passive_resistance": "Passive Resistance Excluded",
            "foundation_passive_mobilisation_factor": 0.75,
            "foundation_uls_sliding_required_sf": 1.5,
        })
        self.assertEqual(result["automatic_design"]["plan_shape"], "Square")
        self.assertEqual(result["inputs"]["length_m"], result["inputs"]["width_m"])
        self.assertEqual(result["automatic_design"]["plan_aspect_ratio"], 1.0)

    def test_rectangular_ratio_may_equal_one_point_five(self):
        raw = dict(DEFAULT_FOUNDATION_VALUES)
        raw.update({
            "foundation_plan_shape": "Rectangular",
            "foundation_length_m": "3.0",
            "foundation_width_m": "2.0",
        })
        values = _validated_inputs(raw)
        self.assertEqual(values["length_m"] / values["width_m"], 1.5)

    def test_rectangular_ratio_above_one_point_five_is_rejected(self):
        raw = dict(DEFAULT_FOUNDATION_VALUES)
        raw.update({
            "foundation_plan_shape": "Rectangular",
            "foundation_length_m": "3.01",
            "foundation_width_m": "2.0",
        })
        with self.assertRaises(FoundationInputError) as caught:
            _validated_inputs(raw)
        self.assertIn("foundation_width_m", caught.exception.errors)
        self.assertIn("1:1.5", caught.exception.errors["foundation_width_m"])

    def test_square_requires_equal_dimensions(self):
        raw = dict(DEFAULT_FOUNDATION_VALUES)
        raw["foundation_plan_shape"] = "Square"
        with self.assertRaises(FoundationInputError) as caught:
            _validated_inputs(raw)
        self.assertIn("equal length and breadth", caught.exception.errors["foundation_width_m"])
        raw["foundation_width_m"] = raw["foundation_length_m"]
        self.assertEqual(_validated_inputs(raw)["plan_shape"], "Square")


class FoundationArtifactTests(unittest.TestCase):
    def test_printable_report_records_geometry_limit_and_hold_points(self):
        result = _foundation_result("Square")
        html = build_foundation_report_html(result, {"name": "Test project"})
        self.assertIn("Foundation Calculation Sheets", html)
        self.assertIn("Square", html)
        self.assertIn("&lt;= 1.500", html)
        self.assertIn("Geotechnical confirmation is required", html)
        with tempfile.TemporaryDirectory() as directory:
            path = write_foundation_report_html(
                result, Path(directory) / "foundation.html", {"name": "Test"}
            )
            self.assertTrue(path.is_file())

    def test_building_markup_warns_until_foundations_are_designed(self):
        html = build_markup_html(_markup_data())
        self.assertIn("FOUNDATIONS HAVE NOT YET BEEN DESIGNED", html)
        self.assertIn("SHEET 5 OF 5", html)

    def test_building_markup_adds_designed_pad_plan_and_detail(self):
        result = _foundation_result("Square")
        result["supports"] = [{"node": "BASE_LEFT", "quantity": 5}, {"node": "BASE_RIGHT", "quantity": 5}]
        html = build_markup_html(_markup_data(result))
        self.assertNotIn("NO PAD SIZES SHOWN", html)
        self.assertIn("TYPICAL PAD 3.0 x 3.0 m", html)
        self.assertIn("PLAN SHAPE Square", html)
        self.assertIn("TYPICAL COMMON PAD QUANTITY 10", html)


if __name__ == "__main__":
    unittest.main()
