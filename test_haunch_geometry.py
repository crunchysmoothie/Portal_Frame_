import unittest

import member_database as mdb
from haunch_design import HaunchProfile, composite_haunch_properties
from haunch_geometry import (
    HAUNCH_DEPTH_AUTO,
    HAUNCH_DEPTH_CUT,
    HAUNCH_DEPTH_SPECIFIED,
    governing_specified_haunch_cut_depth_mm,
    haunch_cut_depth_check,
    maximum_haunch_cut_depth_mm,
    resolve_haunch_cut_depths,
)
from ui.input_model import (
    AUTOMATIC_SECTION,
    DEFAULT_VALUES,
    InputValidationError,
    build_analysis_payload,
    rafter_haunch_cut_limit,
)


class HaunchGeometryRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = mdb.load_member_database()
        cls.section_name = "254x146x31"
        cls.section = cls.database["I-Sections"][cls.section_name]

    def test_exact_database_usable_donor_depth_is_accepted(self):
        maximum = maximum_haunch_cut_depth_mm(self.section)
        self.assertAlmostEqual(maximum, 227.6, places=6)
        self.assertTrue(
            haunch_cut_depth_check(self.section, maximum).is_valid
        )
        self.assertFalse(
            haunch_cut_depth_check(self.section, maximum + 0.1).is_valid
        )

    def test_equal_depth_and_width_has_no_positive_cut(self):
        section = {"h": 200.0, "b": 200.0}
        self.assertEqual(maximum_haunch_cut_depth_mm(section), 0.0)
        self.assertFalse(haunch_cut_depth_check(section, 0.1).is_valid)

    def test_composite_properties_reject_impossible_donor_cut(self):
        maximum = maximum_haunch_cut_depth_mm(self.section)
        with self.assertRaisesRegex(ValueError, "hw \\+ tf"):
            composite_haunch_properties(self.section, maximum + 0.1)

    def test_manual_input_reports_selected_section_limit(self):
        values = dict(DEFAULT_VALUES)
        values.update(
            {
                "rafter_section_type": "I-Sections",
                "rafter_section": self.section_name,
                "use_eaves_haunch": True,
                "eaves_haunch_depth_mode": HAUNCH_DEPTH_SPECIFIED,
                "eaves_haunch_depth_mm": "228",
            }
        )
        with self.assertRaises(InputValidationError) as context:
            build_analysis_payload(values)
        message = context.exception.errors["eaves_haunch_depth_mm"]
        self.assertIn(self.section_name, message)
        self.assertIn("hw + tf", message)

    def test_automatic_input_rejects_depth_above_family_ceiling(self):
        limit = rafter_haunch_cut_limit(
            "I-Sections",
            AUTOMATIC_SECTION,
        )
        values = dict(DEFAULT_VALUES)
        values.update(
            {
                "rafter_section_type": "I-Sections",
                "rafter_section": AUTOMATIC_SECTION,
                "use_eaves_haunch": True,
                "eaves_haunch_depth_mode": HAUNCH_DEPTH_SPECIFIED,
                "eaves_haunch_depth_mm": str(
                    float(limit["maximum_cut_depth_mm"]) + 0.1
                ),
            }
        )
        with self.assertRaises(InputValidationError) as context:
            build_analysis_payload(values)
        self.assertIn(
            "Family maximum",
            context.exception.errors["eaves_haunch_depth_mm"],
        )

    def test_cut_depth_input_does_not_require_a_fixed_numeric_depth(self):
        values = dict(DEFAULT_VALUES)
        values.update(
            {
                "use_eaves_haunch": True,
                "eaves_haunch_depth_mode": HAUNCH_DEPTH_CUT,
                "eaves_haunch_length_m": "1.5",
                "eaves_haunch_depth_mm": "",
            }
        )
        payload = build_analysis_payload(values)
        frame = payload["building_data"]
        self.assertEqual(frame["eaves_haunch_depth_mode"], HAUNCH_DEPTH_CUT)
        self.assertEqual(frame["eaves_haunch_depth"], 0.0)
        self.assertEqual(
            governing_specified_haunch_cut_depth_mm(frame),
            0.0,
        )

    def test_default_inputs_use_auto_size_for_both_haunch_locations(self):
        payload = build_analysis_payload(dict(DEFAULT_VALUES))
        frame = payload["building_data"]
        self.assertEqual(frame["eaves_haunch_depth_mode"], HAUNCH_DEPTH_AUTO)
        self.assertEqual(frame["apex_haunch_depth_mode"], HAUNCH_DEPTH_AUTO)

    def test_cut_depth_resolves_to_each_trial_rafter_limit(self):
        frame = {
            "use_eaves_haunch": "Yes",
            "eaves_haunch_depth_mode": HAUNCH_DEPTH_CUT,
            "eaves_haunch_depth": 999.0,
            "use_apex_haunch": "No",
        }
        resolved = resolve_haunch_cut_depths(frame, self.section)
        self.assertAlmostEqual(
            resolved["eaves_haunch_depth"],
            maximum_haunch_cut_depth_mm(self.section),
        )
        self.assertEqual(
            resolved["resolved_haunch_source_section"],
            self.section_name,
        )

    def test_auto_size_uses_span_over_15_and_trial_rafter_cut_limit(self):
        values = dict(DEFAULT_VALUES)
        values.update(
            {
                "gable_width_m": "18",
                "use_eaves_haunch": True,
                "eaves_haunch_depth_mode": HAUNCH_DEPTH_AUTO,
                "eaves_haunch_length_m": "",
                "eaves_haunch_depth_mm": "",
                "use_apex_haunch": True,
                "apex_haunch_depth_mode": HAUNCH_DEPTH_AUTO,
                "apex_haunch_length_m": "",
                "apex_haunch_depth_mm": "",
            }
        )
        frame = build_analysis_payload(values)["building_data"]
        self.assertEqual(frame["eaves_haunch_length"], 1_200.0)
        self.assertEqual(frame["apex_haunch_length"], 1_200.0)
        self.assertEqual(
            governing_specified_haunch_cut_depth_mm(frame),
            0.0,
        )
        resolved = resolve_haunch_cut_depths(frame, self.section)
        maximum = maximum_haunch_cut_depth_mm(self.section)
        self.assertEqual(resolved["eaves_haunch_depth"], maximum)
        self.assertEqual(resolved["apex_haunch_depth"], maximum)

    def test_independent_eaves_lengths_are_normalised_and_modelled(self):
        values = dict(DEFAULT_VALUES)
        values.update({
            "use_eaves_haunch": True,
            "eaves_haunch_depth_mode": HAUNCH_DEPTH_SPECIFIED,
            "eaves_haunch_length_m": "0.8",
            "right_eaves_haunch_length_m": "1.0",
            "eaves_haunch_depth_mm": "180",
        })
        frame = build_analysis_payload(values)["building_data"]
        self.assertEqual(frame["left_eaves_haunch_length"], 800.0)
        self.assertEqual(frame["right_eaves_haunch_length"], 1000.0)

        profile = HaunchProfile(frame)
        slope_position = profile.slope_position(400.0, 0.0)
        self.assertIsNotNone(slope_position)
        self.assertAlmostEqual(
            profile.added_depth_at(400.0, 0.0),
            180.0 * (1.0 - slope_position / 800.0),
            places=6,
        )
        self.assertAlmostEqual(
            profile.added_depth_at(15_600.0, 0.0),
            180.0 * (1.0 - slope_position / 1000.0),
            places=6,
        )

    def test_missing_right_eaves_length_uses_legacy_common_value(self):
        values = dict(DEFAULT_VALUES)
        values.update({
            "use_eaves_haunch": True,
            "eaves_haunch_depth_mode": HAUNCH_DEPTH_SPECIFIED,
            "eaves_haunch_length_m": "0.8",
            "right_eaves_haunch_length_m": "",
            "eaves_haunch_depth_mm": "180",
        })
        frame = build_analysis_payload(values)["building_data"]
        self.assertEqual(frame["left_eaves_haunch_length"], 800.0)
        self.assertEqual(frame["right_eaves_haunch_length"], 800.0)


if __name__ == "__main__":
    unittest.main()
