import unittest

from draughtsman_markup import (
    _brace_pairs,
    _wall_view_geometry,
    build_markup_html,
    even_positions,
)
from user_input import generate_nodes


class DraughtsmanMarkupTests(unittest.TestCase):
    def test_even_positions_respect_maximum_and_fit_evenly(self):
        positions, actual = even_positions(6500, 1800)
        self.assertEqual(len(positions), 5)
        self.assertAlmostEqual(actual, 1625)
        self.assertAlmostEqual(positions[-1], 6500)

    def test_brace_pairs_stop_and_restart_at_ridge(self):
        self.assertEqual(
            _brace_pairs(15, 3, apex_index=7),
            [(0, 3), (3, 6), (6, 7), (7, 10), (10, 13), (13, 14)],
        )

    def test_side_wall_uses_one_horizontal_and_vertical_scale(self):
        x0, x1, yt, yb, scale = _wall_view_geometry(144_000, 10_000)
        self.assertAlmostEqual((x1 - x0) / 144_000, scale)
        self.assertAlmostEqual((yb - yt) / 10_000, scale)
        self.assertAlmostEqual((x1 - x0) / (yb - yt), 14.4)

    def test_markup_contains_four_a1_views_and_required_callouts(self):
        data = {
            "project": {
                "roof_type": "Duo Pitched", "gable_width_mm": 18000,
                "eaves_height_mm": 6500, "apex_height_mm": 8090,
                "rafter_spacing_mm": 6000, "building_length_mm": 42000,
                "rafter_section": "305x165x40", "column_section": "305x165x40",
                "column_bracing_type": "X", "purlin_section": "125x50x20x2.5",
                "purlin_max_spacing_mm": 1500, "roof_bracing_purlin_interval": 3,
                "girt_section": "125x50x20x2.5", "girt_max_spacing_mm": 1800,
            },
            "bracing_design": {
                "bracing_members": [
                    {"member_type": "Roof X-brace", "section": "90x90x6"},
                    {"member_type": "Longitudinal side-wall brace", "section": "100x100x8"},
                ],
                "column_bracing_layout": {"type": "X"},
                "gable_layout": {"columns": []}, "gable_columns": [],
            },
        }
        output = build_markup_html(data)
        self.assertEqual(output.count('<section class="sheet">'), 4)
        self.assertIn("HAUNCH L=1,200 mm", output)
        self.assertIn("EVERY 3 PURLIN SPACE(S)", output)
        self.assertIn("MAX 1,800 mm", output)

    def test_purlin_rows_do_not_split_the_portal_analysis_model(self):
        building = {
            "building_roof": "Duo Pitched", "gable_width": 18000,
            "eaves_height": 6500, "apex_height": 8090,
            "col_bracing_spacing": 1, "rafter_bracing_spacing": 2,
            "purlin_max_spacing_mm": 1500,
        }
        nodes = generate_nodes(building)
        self.assertEqual(len(nodes), 7)


if __name__ == "__main__":
    unittest.main()
