import base64
import unittest

from ui.analysis_render import combination_names, load_case_svg, load_schedule


def decoded_svg(data_url: str) -> str:
    return base64.b64decode(data_url.split(",", 1)[1]).decode("utf-8")


class UiAnalysisRenderTests(unittest.TestCase):
    def setUp(self):
        points = [
            {"x_mm": 0, "y_mm": 0, "dx_mm": 0, "dy_mm": 0},
            {"x_mm": 500, "y_mm": 0, "dx_mm": 0.5, "dy_mm": -2},
            {"x_mm": 1000, "y_mm": 0, "dx_mm": 1, "dy_mm": 0},
        ]
        force_points = [
            {
                "x_mm": 0,
                "axial_kn": -10,
                "shear_y_kn": 5,
                "moment_z_knm": 0,
            },
            {
                "x_mm": 500,
                "axial_kn": -10,
                "shear_y_kn": 0,
                "moment_z_knm": 12,
            },
            {
                "x_mm": 1000,
                "axial_kn": -10,
                "shear_y_kn": -5,
                "moment_z_knm": 0,
            },
        ]

        def combination(name, kind, utilisation):
            return {
                "name": name,
                "kind": kind,
                "factors": {"D": 1.2, "L": 1.6},
                "max_displacement_mm": 2,
                "nodes": [
                    {
                        "name": "N1",
                        "x_mm": 0,
                        "y_mm": 0,
                        "dx_mm": 0,
                        "dy_mm": 0,
                    },
                    {
                        "name": "N2",
                        "x_mm": 1000,
                        "y_mm": 0,
                        "dx_mm": 1,
                        "dy_mm": -2,
                    },
                ],
                "members": [
                    {
                        "name": "M1",
                        "utilisation": utilisation,
                        "local_axes": {"x": [1, 0], "y": [0, 1]},
                        "displacement_points": points,
                        "force_points": force_points,
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
                "nodal_loads": [],
            }

        self.visualisation = {
            "combinations": [
                combination("1.2 D + 1.6 L", "ULS", 0.75),
                combination("1.0 D + 1.0 L", "SLS", None),
            ]
        }

    def test_lists_and_filters_combinations(self):
        self.assertEqual(
            combination_names(self.visualisation),
            ("1.2 D + 1.6 L", "1.0 D + 1.0 L"),
        )
        self.assertEqual(
            combination_names(self.visualisation, "ULS"),
            ("1.2 D + 1.6 L",),
        )
        self.assertEqual(
            combination_names(self.visualisation, "SLS"),
            ("1.0 D + 1.0 L",),
        )

    def test_loading_view_labels_values_directly_at_arrows(self):
        svg = decoded_svg(
            load_case_svg(self.visualisation, "1.2 D + 1.6 L", view="loads")
        )
        schedule = load_schedule(self.visualisation, "1.2 D + 1.6 L")

        self.assertIn("FY -1.20", svg)
        self.assertIn("Colour identifies the source case", svg)
        self.assertIn("Values are beside the arrows", svg)
        self.assertNotIn(">L1<", svg)
        self.assertEqual(schedule[0]["target"], "M1")

    def test_utilisation_is_uls_only(self):
        svg = decoded_svg(
            load_case_svg(
                self.visualisation,
                "1.2 D + 1.6 L",
                view="utilisation",
            )
        )
        self.assertIn("U=0.75", svg)
        self.assertIn("ULS combinations", svg)
        with self.assertRaisesRegex(ValueError, "ULS combinations only"):
            load_case_svg(
                self.visualisation,
                "1.0 D + 1.0 L",
                view="utilisation",
            )

    def test_deflection_is_sls_only_and_labels_selected_component(self):
        svg = decoded_svg(
            load_case_svg(
                self.visualisation,
                "1.0 D + 1.0 L",
                view="deflection",
                component="dy",
            )
        )
        self.assertIn("N2 DY -2.00 mm", svg)
        self.assertIn("DY deflection", svg)
        self.assertNotIn("U=0.75", svg)
        with self.assertRaisesRegex(ValueError, "SLS combinations only"):
            load_case_svg(
                self.visualisation,
                "1.2 D + 1.6 L",
                view="deflection",
                component="dx",
            )

    def test_total_deflection_uses_complete_vector_and_resultant_labels(self):
        svg = decoded_svg(
            load_case_svg(
                self.visualisation,
                "1.0 D + 1.0 L",
                view="deflection",
                component="total deflection",
            )
        )
        self.assertIn("N2 Total 2.24 mm", svg)
        self.assertIn("Total deflection", svg)
        self.assertIn("complete displacement vector", svg)
        self.assertNotIn("N2 DX", svg)
        self.assertNotIn("N2 DY", svg)

    def test_internal_force_components_have_independent_diagrams(self):
        svg = decoded_svg(
            load_case_svg(
                self.visualisation,
                "1.2 D + 1.6 L",
                view="forces",
                component="moment",
            )
        )
        self.assertIn("Bending moment Mz", svg)
        self.assertIn("+12.00", svg)
        self.assertIn("peak absolute value", svg)
        self.assertNotIn("U=0.75", svg)


if __name__ == "__main__":
    unittest.main()
