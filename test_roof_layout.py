import math
import unittest

from roof_layout import calculate_roof_bracing_layout, roof_brace_pairs


class RoofLayoutTests(unittest.TestCase):
    def test_calculates_purlin_intervals_from_geometry_and_bracing_count(self):
        layout = calculate_roof_bracing_layout(
            24_000, 10_000, 14_500, "Duo Pitched", 1_600, 2
        )
        self.assertEqual(layout["purlin_spaces_per_slope"], 9)
        self.assertEqual(layout["purlin_spaces_per_brace_panel"], [5, 4])
        self.assertEqual(layout["maximum_purlin_interval"], 5)
        self.assertLessEqual(layout["actual_purlin_spacing_mm"], 1_600)
        self.assertTrue(math.isclose(
            layout["actual_purlin_spacing_mm"],
            math.hypot(12_000, 4_500) / 9,
        ))

    def test_duo_pitch_pairs_cover_both_slopes_symmetrically(self):
        pairs = roof_brace_pairs(9, "Duo Pitched", [5, 4])
        self.assertEqual(pairs, [(0, 5), (5, 9), (9, 13), (13, 18)])

    def test_requested_panels_are_not_reduced_by_purlin_layout(self):
        with self.assertRaisesRegex(
            ValueError, "Need 10 purlin spaces/slope for 10 brace panels"
        ):
            calculate_roof_bracing_layout(
                6_000, 4_000, 4_500, "Mono Pitched", 2_000, 10
            )

    def test_four_requested_panels_remain_four(self):
        layout = calculate_roof_bracing_layout(
            16_000, 6_500, 7_500, "Duo Pitched", 1_600, 4
        )
        self.assertEqual(layout["brace_panels_per_slope"], 4)
        self.assertEqual(len(layout["purlin_spaces_per_brace_panel"]), 4)


if __name__ == "__main__":
    unittest.main()
