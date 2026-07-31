import unittest

import member_database as mdb
from haunch_design import composite_haunch_properties
from haunch_geometry import (
    HAUNCH_DEPTH_CUT,
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

    def test_exact_database_h_minus_b_limit_is_accepted(self):
        maximum = maximum_haunch_cut_depth_mm(self.section)
        self.assertAlmostEqual(maximum, 105.4, places=6)
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
        with self.assertRaisesRegex(ValueError, "h - b"):
            composite_haunch_properties(self.section, maximum + 0.1)

    def test_manual_input_reports_selected_section_limit(self):
        values = dict(DEFAULT_VALUES)
        values.update(
            {
                "rafter_section_type": "I-Sections",
                "rafter_section": self.section_name,
                "use_eaves_haunch": True,
                "eaves_haunch_depth_mm": "106",
            }
        )
        with self.assertRaises(InputValidationError) as context:
            build_analysis_payload(values)
        message = context.exception.errors["eaves_haunch_depth_mm"]
        self.assertIn(self.section_name, message)
        self.assertIn("h - b", message)

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


if __name__ == "__main__":
    unittest.main()
