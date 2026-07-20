import unittest
from types import SimpleNamespace
from unittest.mock import patch

from portal_frame_analysis import analyze_combination, section_candidates


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

    def test_explicit_pair_is_returned_for_reporting_when_checks_fail(self):
        frame = SimpleNamespace(
            nodes={
                "N1": SimpleNamespace(
                    DX={"SLS": 80.0},
                    DY={"SLS": 120.0},
                )
            },
            add_load_combo=lambda *args: None,
            analyze=lambda **kwargs: None,
        )
        data = SimpleNamespace(
            serviceability_load_combinations=[{"name": "SLS", "factors": {}}],
            load_combinations=[{"name": "ULS", "factors": {}}],
        )
        member_db = {
            "I-Sections": {
                "FORCED": {"Designation": "FORCED", "b": 300.0, "m": 20.0},
                "COLUMN": {"Designation": "COLUMN", "b": 200.0, "m": 20.0},
            }
        }

        with patch("portal_frame_analysis.mdb.member_properties", side_effect=lambda family, name, db: db[family][name]), \
             patch("portal_frame_analysis.build_model", return_value=frame):
            result = analyze_combination(
                (
                    "I-Sections", "FORCED",
                    "I-Sections", "COLUMN",
                    member_db, data,
                    10.0, 10.0,
                    10.0, 10.0,
                    True,
                )
            )

        self.assertIsNotNone(result)
        self.assertEqual(result[1:3], ("FORCED", "COLUMN"))
        self.assertEqual(result[3:7], (120.0, "SLS", 80.0, "SLS"))


if __name__ == "__main__":
    unittest.main()
