import base64
import unittest

from ui.analysis_render import combination_names, load_case_svg


class UiAnalysisRenderTests(unittest.TestCase):
    def setUp(self):
        points = [
            {"x_mm": 0, "y_mm": 0, "dx_mm": 0, "dy_mm": 0},
            {"x_mm": 500, "y_mm": 0, "dx_mm": 0, "dy_mm": -2},
            {"x_mm": 1000, "y_mm": 0, "dx_mm": 0, "dy_mm": 0},
        ]
        self.visualisation = {
            "combinations": [
                {
                    "name": "1.2 D + 1.6 L",
                    "kind": "ULS",
                    "factors": {"D": 1.2, "L": 1.6},
                    "max_displacement_mm": 2,
                    "nodes": [
                        {"name": "N1", "x_mm": 0, "y_mm": 0},
                        {"name": "N2", "x_mm": 1000, "y_mm": 0},
                    ],
                    "members": [
                        {
                            "name": "M1",
                            "utilisation": 0.75,
                            "displacement_points": points,
                            "distributed_loads": [
                                {
                                    "case": "D",
                                    "direction": "FY",
                                    "w1_kn_per_m": -1.2,
                                    "w2_kn_per_m": -1.2,
                                    "x1_mm": 0,
                                    "x2_mm": 1000,
                                }
                            ],
                            "point_loads": [],
                        }
                    ],
                }
            ]
        }

    def test_lists_combinations(self):
        self.assertEqual(combination_names(self.visualisation), ("1.2 D + 1.6 L",))

    def test_renders_load_utilisation_and_deflection(self):
        data_url = load_case_svg(self.visualisation, "1.2 D + 1.6 L")
        svg = base64.b64decode(data_url.split(",", 1)[1]).decode("utf-8")

        self.assertIn("U=0.75", svg)
        self.assertIn("D: -1.20→-1.20 kN/m", svg)
        self.assertIn("magnified deflection", svg)


if __name__ == "__main__":
    unittest.main()
