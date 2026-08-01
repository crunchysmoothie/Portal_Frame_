from types import SimpleNamespace
import unittest

import member_database as portal_members
from bracing_design import (
    _ordered_gable_sections,
    _select_gable_section,
    select_gable_nodes,
)
from preview_geometry import build_preview_geometry
from ui.input_model import (
    DEFAULT_VALUES,
    PORTAL_SECTIONS_BY_FAMILY,
    build_analysis_payload,
)
from ui.project_file import (
    ProjectInputFileError,
    dump_project_inputs,
    load_project_inputs,
)


class GableInputTests(unittest.TestCase):
    def test_manual_portal_sections_are_sorted_by_height_then_width(self):
        database = portal_members.load_member_database()
        for family, designations in PORTAL_SECTIONS_BY_FAMILY.items():
            geometry = [
                (
                    float(database[family][designation]["h"]),
                    float(database[family][designation]["b"]),
                    float(database[family][designation]["m"]),
                    designation.casefold(),
                )
                for designation in designations
            ]
            self.assertEqual(geometry, sorted(geometry))

    def test_even_gable_columns_are_equally_spaced(self):
        raw = dict(DEFAULT_VALUES)
        raw["gable_column_count"] = "2"
        payload = build_analysis_payload(raw)

        preview = build_preview_geometry(payload)
        columns = preview["frame_elevation"]["gable_columns"]

        self.assertEqual(len(columns), 2)
        self.assertAlmostEqual(columns[0]["start"]["x_mm"], 16000 / 3)
        self.assertAlmostEqual(columns[1]["start"]["x_mm"], 2 * 16000 / 3)

    def test_bracing_layout_accepts_even_gable_column_count(self):
        data = SimpleNamespace(
            frame_data=[
                {
                    "gable_width": 18000,
                    "eaves_height": 6500,
                    "apex_height": 7500,
                    "building_roof": "Duo Pitched",
                }
            ],
            nodes={"APEX": SimpleNamespace(x=9000, y=7500)},
        )

        columns = select_gable_nodes(data, 2)

        self.assertEqual([column["x"] for column in columns], [6000, 12000])
        self.assertEqual([column["y"] for column in columns], [7166.666666666667] * 2)

    def test_gable_section_order_changes_candidate_priority(self):
        database = {
            "I-Sections": {
                "I preferred": {"m": 30, "Preferred": "Yes"},
            },
            "H-Sections": {
                "H light": {"m": 10, "Preferred": "No"},
            },
        }

        preferred = _ordered_gable_sections(
            database, "Preferred sections first"
        )
        lightest = _ordered_gable_sections(
            database, "Automatic - lightest passing"
        )

        self.assertEqual(preferred[0][1], "I preferred")
        self.assertEqual(lightest[0][1], "H light")

    def test_explicit_gable_section_is_used_without_automatic_rejection(self):
        selected_props = {"m": 30, "Preferred": "No"}
        database = {
            "I-Sections": {"I selected": selected_props},
            "H-Sections": {},
        }

        family, name, props = _select_gable_section(
            database,
            demands=[],
            brace_intervals=1,
            material={},
            section_order="Automatic - lightest passing",
            selected_family="I-Sections",
            selected_section="I selected",
        )

        self.assertEqual((family, name), ("I-Sections", "I selected"))
        self.assertIs(props, selected_props)


class ProjectInputFileTests(unittest.TestCase):
    def test_saved_inputs_round_trip_and_restore_new_defaults(self):
        raw = dict(DEFAULT_VALUES)
        raw["project_name"] = "Warehouse A"
        raw["gable_column_count"] = "4"
        raw["gable_column_section_order"] = "Automatic - lightest passing"
        raw["ignore_1_1_dl_1_0_ll_vertical_deflection_limit"] = True
        raw["crawl_beams"] = [{"name": "CB1", "section_type": "I-Sections"}]

        loaded = load_project_inputs(dump_project_inputs(raw))

        self.assertEqual(loaded["project_name"], "Warehouse A")
        self.assertEqual(loaded["gable_column_count"], "4")
        self.assertEqual(
            loaded["gable_column_section_order"], "Automatic - lightest passing"
        )
        self.assertTrue(
            loaded[
                "ignore_1_1_dl_1_0_ll_vertical_deflection_limit"
            ]
        )
        self.assertEqual(loaded["crawl_beams"][0]["name"], "CB1")

    def test_unrelated_json_is_rejected(self):
        with self.assertRaises(ProjectInputFileError):
            load_project_inputs('{"inputs": {}}')


if __name__ == "__main__":
    unittest.main()
