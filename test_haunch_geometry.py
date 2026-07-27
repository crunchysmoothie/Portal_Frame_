import unittest

import member_database as mdb
from haunch_design import composite_haunch_properties
from haunch_geometry import (
    haunch_cut_depth_check,
    maximum_haunch_cut_depth_mm,
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


if __name__ == "__main__":
    unittest.main()
