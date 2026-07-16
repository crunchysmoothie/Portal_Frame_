import math
import unittest
from unittest.mock import patch

import member_database as mdb
from bracing_design import (
    design_bracing_system,
    load_bracing_database,
    select_gable_nodes,
    tributary_widths,
)
from frame_model import load_portal_frame
from design_calculations import _build_steel_mass_breakdown


class BracingDesignTests(unittest.TestCase):
    def setUp(self):
        self.frame = load_portal_frame("input_data.json")

    def test_gable_count_expands_symmetrically_from_apex(self):
        selected = select_gable_nodes(self.frame, 3)
        positions = [item["x"] for item in selected]
        centre = self.frame.frame_data[0]["gable_width"] / 2
        self.assertEqual(positions[1], centre)
        self.assertAlmostEqual(centre - positions[0], positions[2] - centre)

    def test_gable_count_must_be_positive_and_odd(self):
        for count in (0, 2, 4):
            with self.subTest(count=count), self.assertRaises(ValueError):
                select_gable_nodes(self.frame, count)

    def test_tributary_width_covers_whole_gable(self):
        widths = tributary_widths([6000, 9000, 12000], 18000)
        self.assertEqual(widths, {6000.0: 7500.0, 9000.0: 3000.0, 12000.0: 7500.0})
        self.assertAlmostEqual(sum(widths.values()), 18000)

    def test_supplied_database_contains_requested_families(self):
        database = load_bracing_database()
        self.assertGreater(len(database["Equal Angles"]), 0)
        self.assertGreater(len(database["Unequal Angles"]), 0)
        self.assertGreater(len(database["CHS"]), 0)
        self.assertGreater(len(database["Lipped Channels"]), 0)

    def test_design_uses_mcr_and_tension_only_x_bracing(self):
        self.frame.frame_data[0]["gable_column_count"] = 3
        self.frame.frame_data[0]["gable_column_brace_intervals"] = 2
        result = design_bracing_system(self.frame, mdb.load_member_database())
        self.assertEqual(len(result["gable_columns"]), 3)
        for column in result["gable_columns"]:
            self.assertIn(column["section_type"], {"I-Sections", "H-Sections"})
            self.assertGreater(column["mcr_knm"], 0)
            self.assertLessEqual(column["utilisation"], 1)
            q = column["factored_line_load_kn_m"]
            length = column["height_mm"] / 1000
            self.assertTrue(math.isclose(column["major_moment_knm"], q * length**2 / 8, rel_tol=1e-6))
        roof = next(item for item in result["bracing_members"] if item["member_type"] == "Roof X-brace")
        self.assertEqual(roof["behaviour"], "tension-only")
        self.assertIn("Angles", roof["section_family"])
        self.assertLessEqual(roof["utilisation"], 1)
        model = result["pynite_roof_model"]
        self.assertTrue(model["tension_only_x_braces"])
        self.assertEqual(model["purlin_resistance_check"], "deferred")
        self.assertGreater(model["member_count"], 0)

    def test_canopy_skips_all_gable_and_bracing_design(self):
        self.frame.frame_data[0]["building_type"] = "Canopy"
        with patch("bracing_design._analyse_gable_columns_pynite") as gable_analysis, \
             patch("bracing_design._analyse_roof_bracing_pynite") as roof_analysis:
            result = design_bracing_system(self.frame, mdb.load_member_database())
        self.assertEqual(result, {})
        gable_analysis.assert_not_called()
        roof_analysis.assert_not_called()

    def test_whole_building_steel_mass_breakdown(self):
        database = mdb.load_member_database()
        result = design_bracing_system(self.frame, database)
        mass = _build_steel_mass_breakdown(self.frame, database, 1000.0, result)

        self.assertEqual(mass["portal_frames"]["quantity"], 8)
        self.assertEqual(mass["portal_frames"]["mass_kg"], 8000.0)
        self.assertEqual(mass["gable_columns"]["gable_end_count"], 2)
        self.assertGreater(mass["gable_columns"]["mass_kg"], 0)
        self.assertEqual(mass["bracing"]["braced_bay_count"], 2)
        self.assertGreater(mass["bracing"]["mass_kg"], 0)
        expected_lines = len({
            node
            for member in self.frame.members if member.type == "rafter"
            for node in (member.i_node, member.j_node)
        })
        self.assertEqual(mass["purlins"]["line_count"], expected_lines)
        self.assertAlmostEqual(mass["purlins"]["total_length_m"], expected_lines * 42)
        category_sum = sum((
            mass["portal_frames"]["mass_kg"],
            mass["bracing"]["mass_kg"],
            mass["gable_columns"]["mass_kg"],
            mass["purlins"]["mass_kg"],
        ))
        self.assertAlmostEqual(mass["total_steel_mass_kg"], category_sum)

    def test_canopy_mass_has_no_gables_or_bracing_but_retains_purlins(self):
        database = mdb.load_member_database()
        mass = _build_steel_mass_breakdown(self.frame, database, 1000.0, {})
        self.assertEqual(mass["gable_columns"]["mass_kg"], 0.0)
        self.assertEqual(mass["bracing"]["mass_kg"], 0.0)
        self.assertGreater(mass["purlins"]["mass_kg"], 0.0)


if __name__ == "__main__":
    unittest.main()
