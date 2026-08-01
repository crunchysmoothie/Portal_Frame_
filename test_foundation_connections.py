from __future__ import annotations

import math
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from connection_design import (
    _design_haunch_end_plate,
    design_portal_connections,
    write_connection_markup_html,
)
from connection_report import write_connection_report_html
from foundation_design import (
    FoundationInputError,
    design_pad_foundations,
    passive_sliding_resistance,
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
                1.0,
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

    def test_automatic_design_accepts_soil_cover_friction_and_sliding_basis(self):
        result = design_pad_foundations(
            _snapshot(),
            {
                "foundation_soil_unit_weight_kn_m3": 18,
                "foundation_permissible_bearing_kpa": 150,
                "foundation_soil_cover_depth_m": 0.9,
                "foundation_friction_coefficient": 0.55,
                "foundation_sliding_resistance": "Sliding Not Resisted",
                "foundation_soil_friction_angle_deg": 30,
                "foundation_passive_resistance": "Passive Resistance Included",
                "foundation_passive_mobilisation_factor": 0.4,
                "foundation_uls_sliding_required_sf": 1.0,
            },
        )
        self.assertAlmostEqual(result["user_inputs"]["soil_cover_depth_m"], 0.9)
        self.assertAlmostEqual(result["user_inputs"]["friction_coefficient"], 0.55)
        self.assertEqual(
            result["user_inputs"]["sliding_resistance"], "Sliding Not Resisted"
        )
        self.assertAlmostEqual(
            result["user_inputs"]["soil_friction_angle_deg"], 30.0
        )
        self.assertEqual(
            result["user_inputs"]["passive_resistance"],
            "Passive Resistance Included",
        )
        self.assertAlmostEqual(
            result["user_inputs"]["passive_mobilisation_factor"], 0.4
        )
        sliding = result["supports"][0]["uls_stability"]["sliding"]
        self.assertGreater(sliding["passive_resistance_kN"], 0.0)
        self.assertAlmostEqual(
            sliding["safety_factor"],
            sliding["total_resistance_kN"]
            / sliding["horizontal_demand_kN"],
        )
        self.assertEqual(
            result["supports"][0]["serviceability"]["sliding"]["status"],
            "PASS",
        )

    def test_sliding_resisted_uses_external_restraint_and_does_not_govern(self):
        result = design_pad_foundations(
            _snapshot(),
            {
                "foundation_soil_unit_weight_kn_m3": 18,
                "foundation_permissible_bearing_kpa": 150,
                "foundation_soil_cover_depth_m": 0.3,
                "foundation_friction_coefficient": 0.0,
                "foundation_sliding_resistance": "Sliding Resisted",
            },
        )
        support = result["supports"][0]
        self.assertEqual(
            support["serviceability"]["sliding"]["status"],
            "RESISTED_EXTERNALLY",
        )
        self.assertEqual(
            support["uls_stability"]["sliding"]["status"],
            "RESISTED_EXTERNALLY",
        )
        self.assertEqual(support["uls_stability"]["status"], "PASS")

    def test_external_sliding_restraint_avoids_friction_driven_oversizing(self):
        snapshot = _snapshot()
        for reaction in snapshot["results"]["reactions"]:
            reaction["fx"] *= 3.0
        common = {
            "foundation_soil_unit_weight_kn_m3": 18,
            "foundation_permissible_bearing_kpa": 150,
            "foundation_soil_cover_depth_m": 0.3,
            "foundation_friction_coefficient": 0.2,
        }
        restrained = design_pad_foundations(
            snapshot,
            {**common, "foundation_sliding_resistance": "Sliding Resisted"},
        )
        unrestrained = design_pad_foundations(
            snapshot,
            {**common, "foundation_sliding_resistance": "Sliding Not Resisted"},
        )
        restrained_volume = (
            restrained["automatic_design"]["length_m"]
            * restrained["automatic_design"]["width_m"]
            * restrained["automatic_design"]["height_mm"]
        )
        unrestrained_volume = (
            unrestrained["automatic_design"]["length_m"]
            * unrestrained["automatic_design"]["width_m"]
            * unrestrained["automatic_design"]["height_mm"]
        )
        self.assertLess(restrained_volume, unrestrained_volume)

    def test_rankine_passive_resistance_reports_each_calculation_component(self):
        result = passive_sliding_resistance(
            soil_unit_weight_kn_m3=19.0,
            soil_friction_angle_deg=25.0,
            embedment_depth_m=1.1,
            footing_face_width_m=2.6,
            mobilisation_factor=0.5,
        )
        expected_kp = math.tan(math.pi / 4 + math.radians(25.0) / 2) ** 2
        expected_characteristic = 0.5 * 19.0 * expected_kp * 1.1**2 * 2.6
        self.assertAlmostEqual(result["coefficient_kp"], expected_kp)
        self.assertAlmostEqual(
            result["characteristic_resistance_kN"],
            expected_characteristic,
        )
        self.assertAlmostEqual(
            result["mobilised_resistance_kN"],
            0.5 * expected_characteristic,
        )

    def test_factored_uls_actions_default_to_required_sliding_sf_of_one(self):
        result = design_pad_foundations(
            _snapshot(),
            {
                "foundation_soil_unit_weight_kn_m3": 18,
                "foundation_permissible_bearing_kpa": 150,
                "foundation_sliding_resistance": "Sliding Not Resisted",
            },
        )
        stability = result["supports"][0]["uls_stability"]
        self.assertAlmostEqual(stability["required_sliding_safety_factor"], 1.0)
        sliding_check = next(
            check
            for check in result["supports"][0]["structural"]["checks"]
            if check["name"].startswith("ULS sliding stability")
        )
        self.assertAlmostEqual(
            sliding_check["demand"],
            abs(
                result["supports"][0]["structural"][
                    "horizontal_reaction_kN"
                ]
            ),
        )

    def test_sliding_inputs_are_validated_and_project_sf_scales_demand(self):
        with self.assertRaises(FoundationInputError) as context:
            design_pad_foundations(
                _snapshot(),
                {
                    "foundation_soil_unit_weight_kn_m3": 18,
                    "foundation_permissible_bearing_kpa": 150,
                    "foundation_passive_mobilisation_factor": 1.2,
                },
            )
        self.assertIn(
            "foundation_passive_mobilisation_factor",
            context.exception.errors,
        )

        result = design_pad_foundations(
            _snapshot(),
            {
                "foundation_soil_unit_weight_kn_m3": 18,
                "foundation_permissible_bearing_kpa": 150,
                "foundation_uls_sliding_required_sf": 1.5,
                "foundation_sliding_resistance": "Sliding Not Resisted",
            },
        )
        support = result["supports"][0]
        sliding_check = next(
            check
            for check in support["structural"]["checks"]
            if check["name"].startswith("ULS sliding stability")
        )
        self.assertAlmostEqual(
            sliding_check["demand"],
            1.5 * abs(support["structural"]["horizontal_reaction_kN"]),
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
        self.assertGreaterEqual(
            bolt_layout["provided_section_face_clearance_depth_mm"],
            bolt_layout["minimum_section_face_clearance_mm"],
        )
        self.assertGreaterEqual(
            bolt_layout["provided_section_face_clearance_width_mm"],
            bolt_layout["minimum_section_face_clearance_mm"],
        )
        self.assertEqual(
            bolt_layout["hole_diameter_mm"],
            bolt_layout["diameter_mm"] + bolt_layout["hole_oversize_mm"],
        )
        self.assertEqual(bolt_layout["hole_oversize_mm"], 6.0)
        self.assertIn("Red Book", bolt_layout["detailing_source"])
        bolt_design = support["holding_down_bolts"]
        anchorage = bolt_design["anchorage_estimate"]
        self.assertEqual(anchorage["concrete_strength_mpa"], 25.0)
        self.assertGreaterEqual(
            anchorage["concrete_tension_resistance_kN"],
            bolt_design["governing_check"]["bolt_tension_kN"],
        )
        self.assertEqual(
            anchorage["minimum_concrete_edge_distance_mm"],
            7.0 * bolt_layout["diameter_mm"],
        )
        self.assertEqual(
            anchorage["anchor_plate_length_mm"],
            3.5 * bolt_layout["diameter_mm"],
        )
        self.assertEqual(
            anchorage["minimum_anchor_plate_thickness_mm"],
            2.0 * bolt_layout["diameter_mm"] / 3.0,
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
            "PRELIMINARY_PASS_WITH_DETAIL_REQUIRED",
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

    def test_all_concrete_design_uses_fixed_25_mpa_strength(self):
        foundation = design_pad_foundations(
            _snapshot(),
            {
                "foundation_soil_unit_weight_kn_m3": 18,
                "foundation_permissible_bearing_kpa": 150,
                "foundation_concrete_strength_mpa": 40,
            },
        )
        self.assertEqual(
            foundation["inputs"]["concrete_strength_mpa"],
            25.0,
        )
        connection = design_portal_connections(_snapshot())
        self.assertEqual(
            connection["base_plates"]["basis"]["concrete_strength_mpa"],
            25.0,
        )

    def test_heavier_haunch_connection_reports_panel_zone_hold_point(self):
        snapshot = deepcopy(_snapshot())
        snapshot["results"]["members"][1]["major_moment"] = 180.0
        result = design_portal_connections(snapshot)
        connection = result["haunch_connections"]["locations"][0][
            "connection"
        ]
        self.assertEqual(connection["status"], "HOLD_POINT")
        self.assertIn(
            "three-mode end-plate T-stub checks",
            connection["reason"],
        )

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

    def test_prokon_reference_geometry_passes_without_stiffeners(self):
        from member_database import load_member_database

        database = load_member_database()
        rafter = database["I-Sections"]["254x146x31"]
        column = database["I-Sections"]["254x146x37"]
        connection = _design_haunch_end_plate(
            {"added_depth_mm": 227.6},
            {
                "major_moment_kNm": 99.0,
                "axial_force_kN": 0.0,
                "shear_force_kN": 43.0,
            },
            rafter,
            column,
        )
        self.assertEqual(connection["status"], "PRELIMINARY_PASS")
        self.assertEqual(connection["bolts"]["diameter_mm"], 16.0)
        self.assertLessEqual(
            connection["bolts"]["gauge_mm"],
            column["b"]
            - 2.0 * connection["bolts"]["minimum_edge_distance_mm"],
        )
        self.assertLessEqual(
            connection["plate"]["provided_thickness_mm"],
            12.0,
        )
        self.assertFalse(connection["stiffeners"]["required"])
        components = connection["supporting_member_components"]
        self.assertAlmostEqual(
            components["flange_t_stub"]["resistance_kN"],
            150.731,
            delta=2.0,
        )
        self.assertAlmostEqual(
            components["web_compression_crippling"]["resistance_kN"],
            249.982,
            delta=2.0,
        )
        self.assertAlmostEqual(
            components["web_compression_buckling"]["resistance_kN"],
            372.952,
            delta=2.0,
        )
        self.assertAlmostEqual(
            components["web_panel_shear"]["resistance_kN"],
            283.409,
            delta=0.1,
        )


if __name__ == "__main__":
    unittest.main()
