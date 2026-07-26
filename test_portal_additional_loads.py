import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from truss_loading import build_panel_point_loads
from truss_model import generate_truss_geometry
from ui.input_model import DEFAULT_VALUES, build_analysis_payload
import user_input


class AdditionalPermanentRoofLoadTests(unittest.TestCase):
    @staticmethod
    def raw_inputs() -> dict:
        raw = dict(DEFAULT_VALUES)
        raw.update(
            {
                "truss_services_load_kpa": "0.10",
                "truss_ceiling_load_kpa": "0.05",
                "truss_solar_load_kpa": "0.04",
                "truss_fire_load_kpa": "0.03",
                "truss_hvac_load_kpa": "0.03",
            }
        )
        return raw

    def test_shared_inputs_are_carried_by_portal_and_truss_payloads(self):
        payload = build_analysis_payload(self.raw_inputs())
        expected = {
            "services_load_kpa": 0.10,
            "ceiling_load_kpa": 0.05,
            "solar_load_kpa": 0.04,
            "fire_load_kpa": 0.03,
            "hvac_load_kpa": 0.03,
        }

        for key, value in expected.items():
            self.assertEqual(payload["building_data"][key], value)
            self.assertEqual(payload["truss_data"][key], value)

    def test_portal_dead_loads_include_the_shared_area_load_once(self):
        payload = build_analysis_payload(self.raw_inputs())
        with TemporaryDirectory() as directory:
            path = Path(directory) / "portal.json"
            path.write_text(
                json.dumps(
                    {
                        "frame_data": [payload["building_data"]],
                        "members": [
                            {"name": "R1", "type": "rafter"},
                            {"name": "C1", "type": "column"},
                        ],
                        "member_loads": [],
                    }
                ),
                encoding="utf-8",
            )

            user_input.add_dead_loads(path)
            stored = json.loads(path.read_text(encoding="utf-8"))

        loads = {
            item["case"]: item
            for item in stored["member_loads"]
            if item["member"] == "R1"
        }
        self.assertEqual(set(loads), {"D_MAX", "D_MIN"})
        self.assertAlmostEqual(loads["D_MAX"]["w1"], -0.0036)
        self.assertAlmostEqual(loads["D_MIN"]["w1"], -0.00216)
        self.assertFalse(any(item["member"] == "C1" for item in stored["member_loads"]))

    def test_truss_conversion_does_not_double_count_shared_loads(self):
        raw = self.raw_inputs()
        raw["structural_system"] = "Truss"
        payload = build_analysis_payload(raw)
        truss = payload["truss_data"]
        geometry = generate_truss_geometry(
            truss["transverse_bay_spans_mm"],
            payload["building_data"]["building_roof"],
            truss["roof_rise_mm"],
            truss["minimum_depth_mm"],
            truss["maximum_panel_width_mm"],
            topology=truss["topology"],
            chord_form=truss["chord_form"],
        )

        loading = build_panel_point_loads(
            payload["building_data"],
            payload["wind_data"],
            truss,
            geometry,
        )

        total_dmax = sum(
            components[1] for components in loading["cases"]["D_MAX"].values()
        )
        total_dmin = sum(
            components[1] for components in loading["cases"]["D_MIN"].values()
        )
        # The shared portal source contains four 10.038 m rafter segments.
        self.assertAlmostEqual(total_dmax, -0.0036 * 40_152, places=6)
        self.assertAlmostEqual(total_dmin, -0.00216 * 40_152, places=6)


if __name__ == "__main__":
    unittest.main()
