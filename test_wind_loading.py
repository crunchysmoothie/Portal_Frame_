import math
import os
from pathlib import Path
import tempfile
import unittest

import user_input


class WindLoadingGenerationTests(unittest.TestCase):
    def _generate(self, building_type, roof_type, building_updates=None):
        eaves = 6_000.0
        apex = 6_800.0
        width = 16_000.0
        roof_span = width / 2 if roof_type == "Duo Pitched" else width
        building = {
            "building_type": building_type,
            "building_roof": roof_type,
            "roof_accessibility": "Accessible",
            "blocking_factor": 0.0,
            "eaves_height": eaves,
            "apex_height": apex,
            "gable_width": width,
            "rafter_spacing": 6_000.0,
            "building_length": 72_000.0,
            "col_bracing_spacing": 1,
            "rafter_bracing_spacing": 3,
            "roof_pitch": math.degrees(math.atan((apex - eaves) / roof_span)),
            "steel_grade": "Steel_S355",
        }
        building.update(building_updates or {})
        wind = {
            "wind": "3s gust",
            "fundamental_basic_wind_speed": 36,
            "return_period": 50,
            "terrain_category": "B",
            "topographic_factor": 1.0,
            "altitude": 1140,
        }

        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                user_input.update_json_file("input_data.json", building, wind)
                user_input.add_wind_member_loads("input_data.json")
                data = user_input.safe_load_json("input_data.json")
            finally:
                os.chdir(original_cwd)
        return data

    def _assert_dead_load_factors(self, combinations):
        for combination in combinations:
            factors = combination["factors"]
            if factors.get("D") == 0.9:
                self.assertEqual(factors.get("D_MIN"), 0.9, combination["name"])
                self.assertNotIn("D_MAX", factors, combination["name"])
            else:
                self.assertIn("D_MAX", factors, combination["name"])
                self.assertEqual(factors["D_MAX"], factors["D"], combination["name"])

    def test_all_supported_building_and_roof_configurations(self):
        normal_cases = {
            "W0_0.2U", "W0_0.2D", "W0_0.3U", "W0_0.3D",
            "W90_0.2", "W90_0.3",
        }
        mixed_duo_cases = {"W0_0.2M1", "W0_0.3M1", "W0_0.2M2", "W0_0.3M2"}
        for building_type in ("Normal", "Canopy"):
            for roof_type in ("Duo Pitched", "Mono Pitched"):
                with self.subTest(building_type=building_type, roof_type=roof_type):
                    data = self._generate(building_type, roof_type)
                    generated = {load["case"] for load in data["member_loads"]}
                    expected = set(normal_cases)
                    if building_type == "Normal" and roof_type == "Duo Pitched":
                        expected.update(mixed_duo_cases)
                    self.assertTrue(data["member_loads"])
                    self.assertEqual(generated, expected)
                    self._assert_dead_load_factors(data["load_combinations"])
                    member_types = {m["name"]: m["type"] for m in data["members"]}
                    loads_90 = [
                        load for load in data["member_loads"]
                        if load["case"].startswith("W90")
                    ]
                    self.assertTrue(loads_90)
                    if building_type == "Normal":
                        self.assertTrue(any(
                            member_types[load["member"]] == "column" for load in loads_90
                        ))
                        self.assertTrue(any(
                            member_types[load["member"]] == "rafter" for load in loads_90
                        ))
                    else:
                        self.assertTrue(all(
                            member_types[load["member"]] == "rafter" for load in loads_90
                        ))

                    if building_type == "Canopy":
                        w0_members = {
                            load["member"] for load in data["member_loads"]
                            if load["case"] == "W0_0.2U"
                        }
                        rafter_names = {
                            m["name"] for m in data["members"] if m["type"] == "rafter"
                        }
                        if roof_type == "Duo Pitched":
                            self.assertEqual(w0_members, rafter_names)
                        else:
                            self.assertLess(len(w0_members), len(rafter_names))

    def test_wind_90_uses_zone_b_for_repeated_portal_columns(self):
        data = self._generate("Normal", "Duo Pitched")
        member_types = {member["name"]: member["type"] for member in data["members"]}
        zone_b = next(zone for zone in data["wind_zones_90"] if zone["Zone"] == "B")
        column_loads = [
            load for load in data["member_loads"]
            if load["case"] == "W90_0.2"
            and member_types[load["member"]] == "column"
        ]
        self.assertTrue(column_loads)
        self.assertTrue(all(
            math.isclose(load["w1"], zone_b["cpi=0.2"])
            for load in column_loads
        ))

    def test_load_combination_standard_selects_wind_factor(self):
        for standard, expected in (
            (user_input.PRE_2019_COMBINATIONS, 1.3),
            (user_input.SANS_2019_COMBINATIONS, 1.6),
        ):
            with self.subTest(standard=standard):
                _, sls, uls = user_input.add_load_cases(
                    "Inaccessible", "Normal", standard
                )
                wind_factors = {
                    factors[case]
                    for combination in uls
                    for case, factors in ((
                        next((name for name in combination["factors"] if name.startswith("W")), None),
                        combination["factors"],
                    ),)
                    if case is not None
                }
                self.assertEqual(wind_factors, {expected})
                leading_live = next(c for c in uls if c["name"] == "1.2 DL + 1.6 LL")
                self.assertEqual(leading_live["factors"]["L"], 1.6)
                self.assertTrue(any(c["factors"].get("D") == 1.0 for c in sls))

    def test_final_design_cpi_is_stored_and_used_in_wind_pressures(self):
        final = self._generate("Normal", "Duo Pitched", {
            "wind_design_mode": "Final design",
            "opening_areas_m2": {
                "side_1": 0.5, "side_2": 0.5,
                "gable_1": 3.0, "gable_2": 0.5,
            },
        })
        prelim = self._generate("Normal", "Duo Pitched")
        internal = final["wind_data"][0]["internal_pressure"]
        self.assertEqual(internal["mode"], "Final design")
        self.assertEqual(
            internal["directions"]["90"]["senses"][0]["dominant_face"],
            "gable_1",
        )
        final_zone_d = next(item for item in final["wind_zones_90"] if item["Zone"] == "D")
        prelim_zone_d = next(item for item in prelim["wind_zones_90"] if item["Zone"] == "D")
        self.assertNotEqual(final_zone_d["cpi=0.2"], prelim_zone_d["cpi=0.2"])
        generated = {load["case"] for load in final["member_loads"]}
        self.assertIn("W90_CPI_MAX", generated)
        self.assertIn("W90_CPI_MIN", generated)
        self.assertNotIn("W90_0.2", generated)


if __name__ == "__main__":
    unittest.main()
