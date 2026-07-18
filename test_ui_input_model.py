import unittest

from ui.input_model import DEFAULT_VALUES, InputValidationError, build_analysis_payload


class UiInputModelTests(unittest.TestCase):
    def values(self, **updates):
        values = dict(DEFAULT_VALUES)
        values.update(updates)
        return values

    def test_defaults_build_engine_payload_with_mm_geometry(self):
        payload = build_analysis_payload(self.values())
        building = payload["building_data"]
        self.assertEqual(building["eaves_height"], 6500)
        self.assertEqual(building["gable_width"], 16000)
        self.assertEqual(building["gable_column_count"], 3)
        self.assertGreater(building["roof_pitch"], 0)

    def test_even_gable_column_count_is_rejected(self):
        with self.assertRaises(InputValidationError) as caught:
            build_analysis_payload(self.values(gable_column_count="4"))
        self.assertIn("gable_column_count", caught.exception.errors)

    def test_canopy_uses_blocking_factor_and_ignores_openings(self):
        payload = build_analysis_payload(
            self.values(
                building_type="Canopy",
                blocking_factor="0.45",
                wind_design_mode="Final design",
                opening_side_1_m2="12",
            )
        )
        building = payload["building_data"]
        self.assertEqual(building["blocking_factor"], 0.45)
        self.assertEqual(building["opening_areas_m2"]["side_1"], 0.0)

    def test_final_normal_design_accepts_nonnegative_openings(self):
        payload = build_analysis_payload(
            self.values(wind_design_mode="Final design", opening_gable_1_m2="4.2")
        )
        self.assertEqual(payload["building_data"]["opening_areas_m2"]["gable_1"], 4.2)

    def test_spring_support_requires_positive_stiffness(self):
        with self.assertRaises(InputValidationError) as caught:
            build_analysis_payload(
                self.values(base_rotational_stiffness_knm_per_rad="0")
            )
        self.assertIn(
            "base_rotational_stiffness_knm_per_rad", caught.exception.errors
        )

    def test_purlin_spacing_must_support_fixed_roof_brace_count(self):
        with self.assertRaises(InputValidationError) as caught:
            build_analysis_payload(
                self.values(
                    rafter_bracing_spacing="4",
                    purlin_max_spacing_mm="5000",
                )
            )
        self.assertIn("purlin_max_spacing_mm", caught.exception.errors)
        self.assertIn(
            "Need 4 purlin spaces/slope for 4 brace panels",
            caught.exception.errors["purlin_max_spacing_mm"],
        )


if __name__ == "__main__":
    unittest.main()
