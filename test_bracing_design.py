import math
import unittest
from unittest.mock import patch

import member_database as mdb
from bracing_design import (
    COMPRESSION_SLENDERNESS_LIMIT,
    MIN_ANGLE_LEG_MM,
    MIN_ANGLE_THICKNESS_MM,
    TENSION_SLENDERNESS_LIMIT,
    _column_brace_geometry,
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
        width = self.frame.frame_data[0]["gable_width"]
        centre = width / 2
        spacing = width / 4
        self.assertEqual(positions, [spacing, 2 * spacing, 3 * spacing])
        self.assertEqual(positions[1], centre)
        self.assertAlmostEqual(centre - positions[0], positions[2] - centre)

    def test_five_gable_columns_divide_full_width_into_six_equal_bays(self):
        width = self.frame.frame_data[0]["gable_width"]
        positions = [item["x"] for item in select_gable_nodes(self.frame, 5)]
        all_positions = [0.0, *positions, width]
        bays = [b - a for a, b in zip(all_positions, all_positions[1:])]
        self.assertTrue(all(math.isclose(bay, width / 6) for bay in bays))

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
        self.assertLessEqual(roof["slenderness_ratio"], TENSION_SLENDERNESS_LIMIT)
        self.assertAlmostEqual(
            roof["slenderness_utilisation"],
            roof["slenderness_ratio"] / TENSION_SLENDERNESS_LIMIT,
        )
        angle = next(
            row for row in load_bracing_database()[roof["section_family"]]
            if row["Designation"] == roof["section"]
        )
        self.assertGreaterEqual(angle["h"], MIN_ANGLE_LEG_MM)
        self.assertGreaterEqual(angle["b"], MIN_ANGLE_LEG_MM)
        self.assertGreaterEqual(angle["t"], MIN_ANGLE_THICKNESS_MM)
        side = next(item for item in result["bracing_members"] if item["member_type"] == "Longitudinal side-wall brace")
        self.assertIn("Angles", side["section_family"])
        self.assertEqual(side["behaviour"], "tension-only")
        self.assertLessEqual(side["slenderness_ratio"], TENSION_SLENDERNESS_LIMIT)
        self.assertLessEqual(side["resistance_utilisation"], 1)
        model = result["pynite_roof_model"]
        self.assertTrue(model["tension_only_x_braces"])
        self.assertEqual(model["purlin_resistance_check"], "deferred")
        self.assertGreater(model["member_count"], 0)
        panels = result["roof_layout"]["brace_panels"]
        self.assertEqual(model["x_brace_count"], 2 * len(panels))
        points = result["roof_layout"]["roof_points"]
        interval = int(self.frame.frame_data[0].get("roof_bracing_purlin_interval", 1))
        for panel in panels:
            start = points[panel["start_index"]]
            end = points[panel["end_index"]]
            self.assertGreater(abs(end["x_mm"] - start["x_mm"]), 0)
            self.assertLessEqual(panel["end_index"] - panel["start_index"], interval)
        self.assertAlmostEqual(
            roof["slenderness_vv"],
            0.5 * roof["length_mm"] / roof["rv_mm"],
        )
        self.assertLessEqual(roof["slenderness_xx"], TENSION_SLENDERNESS_LIMIT)
        self.assertLessEqual(roof["slenderness_yy"], TENSION_SLENDERNESS_LIMIT)
        self.assertLessEqual(roof["slenderness_vv"], TENSION_SLENDERNESS_LIMIT)

    def test_column_bracing_type_selects_expected_section_family(self):
        database = mdb.load_member_database()
        for bracing_type in ("K", "A"):
            with self.subTest(bracing_type=bracing_type):
                self.frame.frame_data[0]["column_bracing_type"] = bracing_type
                result = design_bracing_system(self.frame, database)
                side = next(
                    item for item in result["bracing_members"]
                    if item["member_type"] == "Longitudinal side-wall brace"
                )
                self.assertEqual(side["section_family"], "CHS")
                self.assertEqual(side["behaviour"], "tension and compression")
                self.assertEqual(result["column_bracing_layout"]["type"], bracing_type)
                self.assertLessEqual(side["slenderness_ratio"], COMPRESSION_SLENDERNESS_LIMIT)

    def test_invalid_column_bracing_type_is_rejected(self):
        self.frame.frame_data[0]["column_bracing_type"] = "V"
        with self.assertRaisesRegex(ValueError, "column_bracing_type"):
            design_bracing_system(self.frame, mdb.load_member_database())

    def test_two_column_bracing_intervals_create_midheight_restraint(self):
        layout = _column_brace_geometry("X", 6000, 6500, panel_count=2)
        self.assertEqual(layout["panel_count"], 2)
        self.assertEqual(layout["panel_height_mm"], 3250)
        self.assertEqual(layout["members_per_wall"], 4)
        self.assertAlmostEqual(layout["member_length_mm"], math.hypot(6000, 3250))

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

        expected_frames = math.ceil(
            self.frame.frame_data[0]["building_length"] /
            self.frame.frame_data[0]["rafter_spacing"]
        ) + 1
        self.assertEqual(mass["portal_frames"]["quantity"], expected_frames)
        self.assertEqual(mass["portal_frames"]["mass_kg"], expected_frames * 1000.0)
        self.assertEqual(mass["gable_columns"]["gable_end_count"], 2)
        self.assertGreater(mass["gable_columns"]["mass_kg"], 0)
        self.assertEqual(mass["bracing"]["braced_bay_count"], 2)
        self.assertGreater(mass["bracing"]["mass_kg"], 0)
        expected_lines = len(result["roof_layout"]["roof_points"])
        self.assertEqual(mass["purlins"]["line_count"], expected_lines)
        self.assertAlmostEqual(
            mass["purlins"]["total_length_m"],
            expected_lines * self.frame.frame_data[0]["building_length"] / 1000,
        )
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
