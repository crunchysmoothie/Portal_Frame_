from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from connection_design import (
    design_portal_connections,
    write_connection_markup_html,
)
from connection_report import write_connection_report_html
from foundation_design import (
    FoundationInputError,
    design_pad_foundations,
)


def _snapshot() -> dict:
    uls = [
        {"name": "ULS gravity"},
        {"name": "ULS wind"},
        {"name": "ULS uplift"},
    ]
    sls = [
        {"name": "SLS gravity"},
        {"name": "SLS wind"},
    ]
    reactions = []
    for node, sign in (("N1", 1.0), ("N7", -1.0)):
        reactions.extend([
            {
                "node": node,
                "load_combination": "ULS gravity",
                "fx": 12.0 * sign,
                "fy": 140.0,
                "fz": 0.0,
                "mx": 0.0,
                "my": 0.0,
                "mz": 35.0 * sign,
            },
            {
                "node": node,
                "load_combination": "ULS wind",
                "fx": 35.0 * sign,
                "fy": 75.0,
                "fz": 0.0,
                "mx": 0.0,
                "my": 0.0,
                "mz": 70.0 * sign,
            },
            {
                "node": node,
                "load_combination": "ULS uplift",
                "fx": 20.0 * sign,
                "fy": -12.0,
                "fz": 0.0,
                "mx": 0.0,
                "my": 0.0,
                "mz": 30.0 * sign,
            },
            {
                "node": node,
                "load_combination": "SLS gravity",
                "fx": 8.0 * sign,
                "fy": 105.0,
                "fz": 0.0,
                "mx": 0.0,
                "my": 0.0,
                "mz": 25.0 * sign,
            },
            {
                "node": node,
                "load_combination": "SLS wind",
                "fx": 22.0 * sign,
                "fy": 62.0,
                "fz": 0.0,
                "mx": 0.0,
                "my": 0.0,
                "mz": 45.0 * sign,
            },
        ])
    members = [
        {
            "member": "M1",
            "member_type": "column",
            "section": "254x146x31",
            "load_combination": "ULS wind",
            "axial_force": 75.0,
            "major_moment": 70.0,
        },
        {
            "member": "M2",
            "member_type": "rafter",
            "section": "254x146x31",
            "load_combination": "ULS wind",
            "axial_force": 30.0,
            "major_moment": 85.0,
        },
    ]
    return {
        "input_data": {
            "load_combinations": uls,
            "serviceability_load_combinations": sls,
            "frame_data": [{
                "use_eaves_haunch": "Yes",
                "eaves_haunch_length": 1_500.0,
                "eaves_haunch_depth": 100.0,
                "use_apex_haunch": "No",
            }],
        },
        "results": {
            "project": {
                "column_section": "254x146x31",
                "rafter_section": "254x146x31",
            },
            "reactions": reactions,
            "members": members,
        },
    }


class AutomaticFoundationTests(unittest.TestCase):
    def test_only_two_soil_inputs_are_required_and_dimensions_are_automatic(self):
        result = design_pad_foundations(
            _snapshot(),
            {
                "foundation_soil_unit_weight_kn_m3": 18,
                "foundation_permissible_bearing_kpa": 150,
            },
        )
        automatic = result["automatic_design"]
        self.assertEqual(result["status"], "PASS")
        self.assertGreater(automatic["length_m"], 0)
        self.assertGreater(automatic["width_m"], 0)
        self.assertGreater(automatic["height_mm"], 0)
        for support in result["supports"]:
            self.assertGreaterEqual(
                support["uls_stability"]["sliding"]["safety_factor"],
                1.5,
            )
            self.assertGreaterEqual(
                support["uls_stability"]["overturning"]["safety_factor"],
                1.5,
            )

    def test_missing_soil_input_is_field_keyed(self):
        with self.assertRaises(FoundationInputError) as context:
            design_pad_foundations(
                _snapshot(),
                {
                    "foundation_permissible_bearing_kpa": 150,
                },
            )
        self.assertIn(
            "foundation_soil_unit_weight_kn_m3",
            context.exception.errors,
        )


class PostAnalysisConnectionTests(unittest.TestCase):
    def test_base_plate_and_haunch_checks_are_reported_from_stored_actions(self):
        result = design_portal_connections(_snapshot())
        self.assertEqual(result["status"], "PASS_WITH_INPUT_REQUIRED")
        support = result["base_plates"]["supports"][0]
        base_plate = support["plate"]
        self.assertGreater(base_plate["length_mm"], 0)
        self.assertGreater(base_plate["provided_thickness_mm"], 0)
        bolt_layout = support["holding_down_bolts"]["layout"]
        self.assertEqual(bolt_layout["distance_status"], "PASS")
        self.assertGreaterEqual(
            bolt_layout["pitch_mm"], bolt_layout["minimum_pitch_mm"]
        )
        self.assertGreaterEqual(
            bolt_layout["gauge_mm"], bolt_layout["minimum_gauge_mm"]
        )
        self.assertIn("required", support["stiffeners"])
        haunch = result["haunch_connections"]
        self.assertEqual(haunch["status"], "PRELIMINARY_PASS")
        self.assertEqual(haunch["locations"][0]["location"], "Eaves haunch")
        self.assertEqual(
            haunch["preliminary_uls_envelope"]["major_moment_kNm"],
            85.0,
        )
        connection = haunch["locations"][0]["connection"]
        self.assertEqual(connection["bolts"]["distance_status"], "PASS")
        self.assertLessEqual(
            connection["bolts"]["pitch_mm"],
            connection["bolts"]["maximum_pitch_mm"],
        )
        self.assertIn("required", connection["stiffeners"])
        self.assertTrue(haunch["next_checks"])
        detailed = result["detailed_checks"]
        self.assertEqual(
            detailed["base_plates"]["supports"][0]["anchor_concrete"]["status"],
            "INPUT_REQUIRED",
        )
        detailed_haunch = detailed["haunch_connections"]["locations"][0]
        self.assertIn(
            detailed_haunch["status"],
            {"PASS", "PASS_WITH_STIFFENERS"},
        )
        self.assertGreater(
            detailed_haunch["prying"]["design_tension_per_bolt_kN"],
            0,
        )
        self.assertEqual(detailed_haunch["end_plate_weld"]["status"], "PASS")
        with TemporaryDirectory() as directory:
            path = write_connection_markup_html(
                result, Path(directory) / "connections.html"
            )
            markup = path.read_text(encoding="utf-8")
            self.assertIn("BASE PLATE N1", markup)
            self.assertIn("PLAN OF BASE PLATE", markup)
            self.assertIn("SECTION A-A", markup)
            self.assertIn("HOLDING-DOWN BOLTS", markup)
            self.assertIn("STIFFENER DETAIL B", markup)
            self.assertIn("END-PLATE ELEVATION", markup)
            self.assertIn("CJP WELD", markup)
            self.assertIn(
                (
                    f"{connection['bolts']['row_count'] - 1} @ "
                    f"{connection['bolts']['pitch_mm']:.0f}"
                ),
                markup,
            )
            self.assertIn('data-role="flat-stiffener"', markup)
            self.assertIn("FLAT-PLATE STIFFENER DETAIL B", markup)
            self.assertIn("TAPERED HAUNCH", markup)
            self.assertNotIn("DESIGN STATUS", markup)
            self.assertNotIn(" U=", markup)
            report_path = write_connection_report_html(
                result, Path(directory) / "connection_calculations.html"
            )
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("Post-analysis connection calculations", report)
            self.assertIn("HC-02", report)
            self.assertIn("INPUT_REQUIRED", report)
            self.assertIn("Elastic line-weld group", report)

    def test_heavier_haunch_connection_adds_calculated_stiffeners(self):
        snapshot = deepcopy(_snapshot())
        snapshot["results"]["members"][1]["major_moment"] = 180.0
        result = design_portal_connections(snapshot)
        connection = result["haunch_connections"]["locations"][0][
            "connection"
        ]
        stiffeners = connection["stiffeners"]
        self.assertTrue(stiffeners["required"])
        self.assertGreater(stiffeners["provided_thickness_mm"], 0)
        self.assertGreater(stiffeners["height_mm"], 0)
        self.assertEqual(stiffeners["status"], "PRELIMINARY_PASS")

    def test_local_column_overstress_automatically_adds_checked_stiffeners(self):
        result = design_portal_connections(_snapshot())
        geometry = result["haunch_connections"]["locations"][0]["connection"]
        detailed = result["detailed_checks"]["haunch_connections"]["locations"][0]
        self.assertTrue(geometry["stiffeners"]["required"])
        self.assertEqual(detailed["stiffener_checks"]["status"], "PASS")
        self.assertTrue(
            all(
                check["status"] == "PASS"
                for check in detailed["stiffener_checks"]["checks"]
            )
        )
        self.assertIn(
            "STIFFENER_REQUIRED",
            {check["status"] for check in detailed["local_member_checks"]},
        )


if __name__ == "__main__":
    unittest.main()
