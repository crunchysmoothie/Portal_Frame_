import unittest

from portal_workflow.inputs import add_load_cases
from portal_workflow.standards import (
    SANS_10160_LATEST_EDITIONS,
    SANS_10160_PREVIOUS_EDITIONS,
    normalize_sans_10160_loading_code,
)
from ui.input_model import DEFAULT_VALUES, build_analysis_payload
from ui.main import load_standard_display


class LoadingCodeEditionTests(unittest.TestCase):
    def test_ui_uses_short_labels_and_keeps_full_code_details(self):
        latest_label, latest_detail = load_standard_display(
            SANS_10160_LATEST_EDITIONS
        )
        previous_label, previous_detail = load_standard_display(
            SANS_10160_PREVIOUS_EDITIONS
        )

        self.assertEqual(latest_label, "2019")
        self.assertEqual(previous_label, "Pre-2019")
        self.assertIn("SANS 10160-1:2019 Ed. 1.3", latest_detail)
        self.assertIn("SANS 10160-3:2011 Ed. 1.1", previous_detail)

    def test_previous_set_uses_editions_applicable_with_part_3_2011(self):
        self.assertIn("10160-1:2010 Ed. 1", SANS_10160_PREVIOUS_EDITIONS)
        self.assertIn("10160-2:2011 Ed. 1.1", SANS_10160_PREVIOUS_EDITIONS)
        self.assertIn("10160-3:2011 Ed. 1.1", SANS_10160_PREVIOUS_EDITIONS)

    def test_latest_and_previous_sets_are_accepted_without_renaming_combinations(self):
        for loading_code in (
            SANS_10160_LATEST_EDITIONS,
            SANS_10160_PREVIOUS_EDITIONS,
        ):
            with self.subTest(loading_code=loading_code):
                raw = dict(DEFAULT_VALUES)
                raw["load_combination_standard"] = loading_code
                payload = build_analysis_payload(raw)
                self.assertEqual(
                    payload["building_data"]["load_combination_standard"],
                    loading_code,
                )
                _, sls, uls = add_load_cases(
                    load_combination_standard=loading_code
                )
                expected = [
                    "C1", "C2", "C3.1", "C3.2", "C3.3", "C3.4",
                    "C4.1", "C4.2", "C4.3", "C4.4", "C5.1", "C5.2",
                    "C6.1", "C6.2",
                ]
                self.assertEqual([item["name"] for item in uls], expected)
                self.assertEqual([item["name"] for item in sls], expected)

    def test_legacy_saved_values_migrate_to_the_corresponding_edition_set(self):
        self.assertEqual(
            normalize_sans_10160_loading_code("2019"),
            SANS_10160_LATEST_EDITIONS,
        )
        self.assertEqual(
            normalize_sans_10160_loading_code("SANS 10160-1:2019"),
            SANS_10160_LATEST_EDITIONS,
        )
        self.assertEqual(
            normalize_sans_10160_loading_code("Pre-2019"),
            SANS_10160_PREVIOUS_EDITIONS,
        )
        self.assertEqual(
            normalize_sans_10160_loading_code("Project C1-C6 schedule"),
            SANS_10160_LATEST_EDITIONS,
        )

    def test_analysis_boundary_rejects_an_unsupported_edition(self):
        with self.assertRaisesRegex(ValueError, "Unknown SANS 10160 loading code"):
            add_load_cases(load_combination_standard="SANS 10160-3:2018 Ed. 2")


if __name__ == "__main__":
    unittest.main()
