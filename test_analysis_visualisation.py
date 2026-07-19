import unittest
from types import SimpleNamespace

import numpy as np

from analysis_visualisation import build_analysis_visualisation


class FakeMember:
    def __init__(self, i_node, j_node):
        self.i_node = i_node
        self.j_node = j_node
        self.section = SimpleNamespace(name="TEST")
        self.DistLoads = [("FY", -0.001, -0.001, 0.0, 1000.0, "D")]
        self.PtLoads = [("FY", -5.0, 500.0, "L")]

    def L(self):
        return 1000.0

    def T(self):
        return np.eye(3)

    def deflection(self, direction, x, combination):
        if direction == "dy":
            return x / 1000 if combination == "SLS" else x / 2000
        return 0.0

    def axial(self, x, combination):
        return -10.0 + x / 1000

    def shear(self, direction, x, combination):
        self.assert_force_direction(direction, "Fy")
        return 5.0 - x / 100

    def moment(self, direction, x, combination):
        self.assert_force_direction(direction, "Mz")
        return 2000.0 * x / 1000

    @staticmethod
    def assert_force_direction(actual, expected):
        if actual != expected:
            raise AssertionError(f"Expected {expected}, received {actual}")


class AnalysisVisualisationTests(unittest.TestCase):
    def test_builds_factored_load_utilisation_and_deflection_contract(self):
        n1 = SimpleNamespace(
            X=0.0,
            Y=0.0,
            Z=0.0,
            DX={"ULS": 0.0, "SLS": 0.0},
            DY={"ULS": 0.0, "SLS": 0.0},
            NodeLoads=[],
        )
        n2 = SimpleNamespace(
            X=1000.0,
            Y=0.0,
            Z=0.0,
            DX={"ULS": 0.0, "SLS": 0.0},
            DY={"ULS": 0.5, "SLS": 1.0},
            NodeLoads=[],
        )
        frame = SimpleNamespace(
            nodes={"N1": n1, "N2": n2},
            members={"M1": FakeMember(n1, n2)},
        )
        data = SimpleNamespace(
            members=[SimpleNamespace(name="M1", type="rafter")],
            load_combinations=[{"name": "ULS", "factors": {"D": 1.2, "L": 1.6}}],
            serviceability_load_combinations=[{"name": "SLS", "factors": {"D": 1.0}}],
        )
        design = SimpleNamespace(
            load_combination="ULS",
            member="M1",
            governing_ratio=0.75,
            status="PASS",
            governing_check="C-02",
        )

        result = build_analysis_visualisation(frame, data, [design])

        uls, sls = result["combinations"]
        self.assertEqual(uls["members"][0]["utilisation"], 0.75)
        self.assertAlmostEqual(
            uls["members"][0]["distributed_loads"][0]["w1_kn_per_m"],
            -1.2,
        )
        self.assertAlmostEqual(
            uls["members"][0]["point_loads"][0]["magnitude_kn"],
            -8.0,
        )
        self.assertEqual(
            uls["members"][0]["local_axes"],
            {"x": [1.0, 0.0], "y": [0.0, 1.0]},
        )
        force_points = uls["members"][0]["force_points"]
        self.assertEqual(force_points[0]["axial_kn"], -10.0)
        self.assertEqual(force_points[-1]["shear_y_kn"], -5.0)
        self.assertEqual(force_points[-1]["moment_z_knm"], 2.0)
        self.assertIsNone(sls["members"][0]["utilisation"])
        self.assertAlmostEqual(sls["max_displacement_mm"], 1.0)


if __name__ == "__main__":
    unittest.main()
