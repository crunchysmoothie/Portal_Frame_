import unittest

from internal_pressure import resolve_internal_pressure


def _wind(**updates):
    data = {
        "building_type": "Normal",
        "building_roof": "Duo Pitched",
        "wind_design_mode": "Final design",
        "gable_width": 18.0,
        "building_length": 42.0,
        "eaves_height": 6.5,
        "apex_height": 8.09,
        "opening_areas_m2": {
            "side_1": 1.0,
            "side_2": 1.0,
            "gable_1": 1.0,
            "gable_2": 1.0,
        },
    }
    data.update(updates)
    return data


class InternalPressureTests(unittest.TestCase):
    def test_prelim_retains_existing_envelope(self):
        result = resolve_internal_pressure(_wind(wind_design_mode="Prelim"))
        for direction in ("0", "90"):
            self.assertEqual(result["directions"][direction]["maximum_cpi"], 0.2)
            self.assertEqual(result["directions"][direction]["minimum_cpi"], -0.3)

    def test_dominant_wall_uses_direction_dependent_external_coefficient(self):
        result = resolve_internal_pressure(_wind(opening_areas_m2={
            "side_1": 0.5, "side_2": 0.5, "gable_1": 3.0, "gable_2": 0.5,
        }))
        senses = result["directions"]["90"]["senses"]
        self.assertTrue(all(item["wall_type"] == "Dominant" for item in senses))
        self.assertTrue(all(item["dominant_face"] == "gable_1" for item in senses))
        self.assertGreater(senses[0]["cpi"], 0)
        self.assertLess(senses[1]["cpi"], 0)
        self.assertAlmostEqual(senses[0]["dominant_factor"], 0.75)

    def test_non_dominant_wall_uses_mu_chart_and_includes_zero(self):
        result = resolve_internal_pressure(_wind())
        direction = result["directions"]["0"]
        self.assertTrue(all(item["wall_type"] == "Non-dominant" for item in direction["senses"]))
        self.assertAlmostEqual(direction["senses"][0]["mu"], 0.75)
        self.assertEqual(direction["maximum_cpi"], 0.0)
        self.assertLess(direction["minimum_cpi"], 0.0)
        self.assertTrue(direction["zero_case_included"])

    def test_final_requires_all_four_faces(self):
        with self.assertRaisesRegex(ValueError, "requires opening_areas_m2"):
            resolve_internal_pressure(_wind(opening_areas_m2={"side_1": 1.0}))

    def test_final_with_no_estimated_openings_uses_conservative_envelope(self):
        result = resolve_internal_pressure(_wind(opening_areas_m2={face: 0 for face in (
            "side_1", "side_2", "gable_1", "gable_2"
        )}))
        self.assertEqual(result["basis"], "No estimated openings; conservative envelope")
        self.assertEqual(result["directions"]["90"]["maximum_cpi"], 0.2)
        self.assertEqual(result["directions"]["90"]["minimum_cpi"], -0.3)

    def test_two_faces_over_thirty_percent_reject_enclosed_model(self):
        wind = _wind()
        wind["opening_areas_m2"]["side_1"] = 100.0
        wind["opening_areas_m2"]["side_2"] = 100.0
        with self.assertRaisesRegex(ValueError, "more than 30% open"):
            resolve_internal_pressure(wind)

    def test_canopy_does_not_request_wall_openings(self):
        result = resolve_internal_pressure({
            "building_type": "Canopy", "wind_design_mode": "Final design"
        })
        self.assertFalse(result["applicable"])


if __name__ == "__main__":
    unittest.main()
