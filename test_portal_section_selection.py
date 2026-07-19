import unittest

from portal_frame_analysis import section_candidates


class PortalSectionSelectionTests(unittest.TestCase):
    def setUp(self):
        self.database = {
            "I-Sections": {
                "LIGHT": {"Preferred": "Yes"},
                "FORCED": {"Preferred": "No"},
            },
            "H-Sections": {"COLUMN": {"Preferred": "Yes"}},
        }

    def test_automatic_uses_preferred_candidates(self):
        self.assertEqual(
            section_candidates(
                self.database,
                "I-Sections",
                selected_section="Automatic - lightest passing",
            ),
            ["LIGHT"],
        )

    def test_user_selection_forces_exact_database_section(self):
        self.assertEqual(
            section_candidates(
                self.database, "I-Sections", selected_section="FORCED"
            ),
            ["FORCED"],
        )

    def test_wrong_family_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not available"):
            section_candidates(
                self.database, "H-Sections", selected_section="FORCED"
            )


if __name__ == "__main__":
    unittest.main()
