import math
import unittest

import user_input
from crawl_beam_loading import (
    GRAVITY,
    characteristic_vertical_crane_load,
    crane_combination_factor,
    diagonal_crane_resultant,
    generate_crawl_member_point_loads,
    hoist_dynamic_factor,
    horizontal_crane_load,
    locate_rafter_point,
)
from crawl_beam_inputs import ALL_AT_ONCE, ONE_AT_A_TIME, resolve_crawl_selection


def _duo_frame(crawls=None):
    building = {
        "building_roof": "Duo Pitched",
        "eaves_height": 6500.0,
        "apex_height": 8090.0,
        "gable_width": 18000.0,
        "rafter_spacing": 6000.0,
        "col_bracing_spacing": 1,
        "rafter_bracing_spacing": 2,
    }
    nodes = user_input.generate_nodes(building)
    return {
        "frame_data": [building],
        "nodes": nodes,
        "members": user_input.generate_members(nodes),
        "crawl_beams": crawls or [],
    }


class CrawlBeamLoadingTests(unittest.TestCase):
    def test_locates_crawl_from_each_eaves_and_converts_to_member_local_x(self):
        data = _duo_frame()
        segment = math.hypot(4500.0, 795.0)

        left_member, left_x = locate_rafter_point(data, "left", 5000.0)
        right_member, right_x = locate_rafter_point(data, "right", 5000.0)

        self.assertEqual(left_member, "M3")
        self.assertAlmostEqual(left_x, 5000.0 - segment)
        self.assertEqual(right_member, "M4")
        self.assertAlmostEqual(right_x, 2 * segment - 5000.0)

    def test_rejects_position_beyond_selected_slope(self):
        with self.assertRaisesRegex(ValueError, "exceeds the left slope length"):
            locate_rafter_point(_duo_frame(), "left", 20_000)

    def test_calculates_sans_vertical_dynamic_action_without_reaction_reduction(self):
        crawl = {
            "swl_kg": 2000,
            "hoist_trolley_mass_kg": 350,
            "lifting_attachment_mass_kg": 100,
            "hoist_class": "C2",
            "hoisting_speed_m_s": 0.15,
        }
        phi_2 = 1.10 + 0.34 * 0.15
        expected = (1.1 * 350 + phi_2 * 2100) * GRAVITY / 1000

        self.assertAlmostEqual(hoist_dynamic_factor("c2", 0.15), phi_2)
        self.assertAlmostEqual(characteristic_vertical_crane_load(crawl), expected)

    def test_generates_full_bay_dead_load_and_full_crane_load_at_rafter(self):
        crawl = {
            "name": "CB1",
            "slope": "left",
            "position_from_eaves_mm": 3500,
            "section_type": "I-Sections",
            "section": "TEST",
            "manufacturer_characteristic_vertical_load_kn": 30.0,
        }
        database = {"I-Sections": {"TEST": {"m": 25.0}}}

        loads = generate_crawl_member_point_loads(_duo_frame([crawl]), database)

        self.assertEqual(loads[0]["member"], "M2")
        self.assertAlmostEqual(loads[0]["x"], 3500.0)
        self.assertEqual(loads[0]["case"], "D_CRAWL")
        self.assertAlmostEqual(loads[0]["magnitude"], -(25.0 * 6.0 * GRAVITY / 1000))
        self.assertEqual(loads[1]["case"], "CR_CB1")
        self.assertAlmostEqual(loads[1]["magnitude"], -30.0)
        self.assertEqual(loads[2]["case"], "CRH_CB1_POS")
        self.assertEqual(loads[2]["direction"], "FX")
        self.assertAlmostEqual(loads[2]["magnitude"], 1.5)
        self.assertEqual(loads[3]["case"], "CRH_CB1_NEG")
        self.assertAlmostEqual(loads[3]["magnitude"], -1.5)

    def test_defaults_horizontal_to_five_percent_and_derives_diagonal(self):
        crawl = {
            "swl_kg": 2000,
            "hoist_trolley_mass_kg": 350,
            "lifting_attachment_mass_kg": 100,
            "hoist_class": "C2",
            "hoisting_speed_m_s": 0.15,
        }
        static_vertical = (350 + 2100) * GRAVITY / 1000
        vertical = characteristic_vertical_crane_load(crawl)
        expected_horizontal = 0.05 * static_vertical

        self.assertAlmostEqual(horizontal_crane_load(crawl), expected_horizontal)
        resultant, angle = diagonal_crane_resultant(crawl)
        self.assertAlmostEqual(resultant, math.hypot(vertical, expected_horizontal))
        self.assertAlmostEqual(angle, math.degrees(math.atan2(expected_horizontal, vertical)))
        self.assertAlmostEqual(crane_combination_factor(crawl), 350 / 2450)

    def test_explicit_diagonal_resultant_derives_horizontal_component(self):
        crawl = {
            "manufacturer_characteristic_vertical_load_kn": 30.0,
            "diagonal_resultant_load_kn": 34.0,
        }
        self.assertAlmostEqual(horizontal_crane_load(crawl), math.sqrt(34**2 - 30**2))

    def test_one_at_a_time_generates_separate_crawl_scenarios(self):
        crawls = [
            {"name": "CB1", "manufacturer_characteristic_vertical_load_kn": 30,
             "crane_combination_factor": 0.2},
            {"name": "CB2", "manufacturer_characteristic_vertical_load_kn": 40,
             "crane_combination_factor": 0.3},
        ]
        cases, sls, uls = user_input.add_load_cases(
            roof_accessibility="Inaccessible",
            include_crawl_beams=True,
            crawl_beams=crawls,
            crawl_application=ONE_AT_A_TIME,
        )

        self.assertGreaterEqual(
            {case["name"] for case in cases},
            {"D_CRAWL", "CR_CB1", "CRH_CB1_POS", "CRH_CB1_NEG",
             "CR_CB2", "CRH_CB2_POS", "CRH_CB2_NEG"},
        )
        self.assertTrue(all(
            combo["factors"]["D_CRAWL"] == combo["factors"]["D"] for combo in sls
        ))
        self.assertTrue(any(combo["factors"].get("CR_CB1") == 1.0 for combo in sls))
        self.assertTrue(any(combo["name"] == "1.2 DL + 1.6 CR CB1" for combo in uls))
        self.assertFalse(any(
            "CR_CB1" in combo["factors"] and "CR_CB2" in combo["factors"]
            for combo in sls + uls
        ))
        self.assertTrue(any(
            math.isclose(combo["factors"].get("CR_CB1", -1), 0.32)
            and any(case.startswith("W") for case in combo["factors"])
            for combo in uls
        ))
        self.assertTrue(any(
            combo["factors"].get("CR_CB1") == 1.6
            and combo["factors"].get("CRH_CB1_POS") == 1.6
            for combo in uls
        ))

    def test_all_at_once_combines_full_vertical_actions(self):
        crawls = [
            {"name": "CB1", "manufacturer_characteristic_vertical_load_kn": 30},
            {"name": "CB2", "manufacturer_characteristic_vertical_load_kn": 40},
        ]
        _, _, uls = user_input.add_load_cases(
            include_crawl_beams=True,
            crawl_beams=crawls,
            crawl_application=ALL_AT_ONCE,
        )
        combined = [combo for combo in uls if combo["name"] == "1.2 DL + 1.6 CR CB1+CB2"]
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined[0]["factors"]["CR_CB1"], 1.6)
        self.assertEqual(combined[0]["factors"]["CR_CB2"], 1.6)
        self.assertTrue(any(
            combo["factors"].get("CRH_CB1_POS") == 1.6
            and combo["factors"].get("CRH_CB2_NEG") == 1.6
            for combo in uls
        ))

    def test_use_switch_disables_library_without_removing_it(self):
        crawl = {"name": "CB1"}
        enabled, mode, library = resolve_crawl_selection("No", ONE_AT_A_TIME, [crawl])
        self.assertFalse(enabled)
        self.assertEqual(mode, ONE_AT_A_TIME)
        self.assertEqual(library, [crawl])

        data = _duo_frame([crawl])
        data["use_crawl_beams"] = "No"
        self.assertEqual(generate_crawl_member_point_loads(data, {}), [])

    def test_rejects_invalid_mode_and_duplicate_names(self):
        with self.assertRaisesRegex(ValueError, "Crawl application"):
            resolve_crawl_selection("Yes", "Sometimes", [])
        with self.assertRaisesRegex(ValueError, "unique"):
            resolve_crawl_selection("Yes", ONE_AT_A_TIME, [{"name": "CB1"}, {"name": "cb1"}])
        with self.assertRaisesRegex(ValueError, "contains no crawls"):
            resolve_crawl_selection("Yes", ONE_AT_A_TIME, [])


if __name__ == "__main__":
    unittest.main()
