import base64
import unittest
from types import SimpleNamespace

import member_database as mdb
from foundation_design import (
    DEFAULT_FOUNDATION_VALUES,
    FOUNDATION_STANDARDS,
    design_pad_foundations,
)
from frame_model import Member, Node, PortalFrame
from haunch_design import composite_haunch_properties
from portal_frame_analysis import (
    _vertical_deflection_limit_applies,
    build_model,
)
from serviceability_deflection import (
    permanent_baseline_name,
    serviceability_deflection_rows,
)
from design_calculations import governing_serviceability_deflections
from ui.analysis_render import load_case_svg
from ui.input_model import (
    DEFAULT_VALUES,
    InputValidationError,
    build_analysis_payload,
)


class HaunchDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = mdb.load_member_database()
        cls.rafter_name = next(iter(cls.database["I-Sections"]))
        cls.column_name = next(iter(cls.database["H-Sections"]))
        cls.rafter = mdb.member_properties(
            "I-Sections", cls.rafter_name, cls.database
        )
        cls.column = mdb.member_properties(
            "H-Sections", cls.column_name, cls.database
        )

    def test_composite_ix_converges_and_increases_monotonically(self):
        maximum_cut = self.rafter["h"] - self.rafter["b"]
        depths = (0.0, 1.0, 10.0, maximum_cut * 0.75, maximum_cut)
        properties = [
            composite_haunch_properties(self.rafter, depth)
            for depth in depths
        ]
        self.assertEqual(properties[0]["Ix"], self.rafter["Ix"])
        self.assertEqual(properties[0]["A"], self.rafter["A"])
        self.assertTrue(all(
            first["Ix"] < second["Ix"]
            for first, second in zip(properties, properties[1:])
        ))
        self.assertTrue(all(
            first["A"] < second["A"]
            for first, second in zip(properties, properties[1:])
        ))

    def test_pynite_rafter_retains_physical_name_and_gets_tapered_subsections(self):
        nodes = {
            "N1": Node("N1", 0, 0, 0),
            "N2": Node("N2", 0, 6500, 0),
            "N3": Node("N3", 3000, 7033.33, 0),
            "N4": Node("N4", 6000, 7566.67, 0),
            "N5": Node("N5", 9000, 8100, 0),
            "N6": Node("N6", 12000, 7566.67, 0),
            "N7": Node("N7", 15000, 7033.33, 0),
            "N8": Node("N8", 18000, 6500, 0),
            "N9": Node("N9", 18000, 0, 0),
        }
        members = [
            Member("M1", "N1", "N2", "Steel_S355", "column", 6.5),
            Member("M2", "N2", "N3", "Steel_S355", "rafter", 3.047),
            Member("M3", "N3", "N4", "Steel_S355", "rafter", 3.047),
            Member("M4", "N4", "N5", "Steel_S355", "rafter", 3.047),
            Member("M5", "N5", "N6", "Steel_S355", "rafter", 3.047),
            Member("M6", "N6", "N7", "Steel_S355", "rafter", 3.047),
            Member("M7", "N7", "N8", "Steel_S355", "rafter", 3.047),
            Member("M8", "N8", "N9", "Steel_S355", "column", 6.5),
        ]
        data = PortalFrame(
            frame_data=[{
                "building_roof": "Duo Pitched",
                "gable_width": 18000,
                "eaves_height": 6500,
                "apex_height": 8100,
                "use_eaves_haunch": "Yes",
                "eaves_haunch_length": 1500,
                "eaves_haunch_depth": 40,
                "use_apex_haunch": "Yes",
                "apex_haunch_length": 1000,
                "apex_haunch_depth": 30,
            }],
            nodes=nodes,
            members=members,
            supports={
                "N1": {"DX": True, "DY": True, "DZ": True},
                "N9": {"DX": True, "DY": True, "DZ": True},
            },
            materials={
                "Steel_S355": {
                    "E": 200,
                    "G": 80,
                    "nu": 0.3,
                    "rho": 7.85e-8,
                }
            },
            rotational_springs=[],
            serviceability_load_combinations=[],
            load_combinations=[],
            geometry_parameters={},
            steel_grade=[{"fy": 355, "E": 200, "G": 77}],
        )
        frame = build_model(self.rafter, self.column, data)
        self.assertIn("M2", frame.members)
        connected_nodes = set()
        sections = []
        for member in members:
            if member.type != "rafter":
                continue
            physical = frame.members[member.name]
            physical.descritize()
            for sub_member in physical.sub_members.values():
                connected_nodes.update(
                    (id(sub_member.i_node), id(sub_member.j_node))
                )
                sections.append(sub_member.section.name)
        haunch_nodes = [
            node for name, node in frame.nodes.items() if name.startswith("HN")
        ]
        self.assertTrue(haunch_nodes)
        self.assertTrue(all(id(node) in connected_nodes for node in haunch_nodes))
        self.assertTrue(any("haunch" in name for name in sections))
        self.assertTrue(any(name == self.rafter_name for name in sections))

    def test_haunch_zones_cannot_overlap(self):
        values = dict(DEFAULT_VALUES)
        values.update({
            "use_eaves_haunch": True,
            "eaves_haunch_length_m": "5",
            "use_apex_haunch": True,
            "apex_haunch_length_m": "4",
        })
        with self.assertRaises(InputValidationError) as context:
            build_analysis_payload(values)
        self.assertIn("apex_haunch_length_m", context.exception.errors)

    def test_portal_deflection_view_uses_height_scale_and_hides_internal_nodes(self):
        def point(x_mm, y_mm, dx_mm=0.0, dy_mm=0.0):
            return {
                "x_mm": x_mm,
                "y_mm": y_mm,
                "dx_mm": dx_mm,
                "dy_mm": dy_mm,
            }

        visualisation = {
            "structural_system": "portal",
            "combinations": [{
                "name": "1.1 DL + 1.0 LL",
                "kind": "SLS",
                "factors": {"D": 1.1, "D_MAX": 1.1, "L": 1.0},
                "nodes": [
                    {"name": "N1", **point(0.0, 0.0)},
                    {"name": "N2", **point(0.0, 6500.0, -19.0, -0.3)},
                    {"name": "N3", **point(9000.0, 8500.0, 0.0, -89.9)},
                    {"name": "N4", **point(18000.0, 6500.0, 19.0, -0.3)},
                    {"name": "N5", **point(18000.0, 0.0)},
                    {"name": "HN1", **point(250.0, 6555.0, -18.5, -2.0)},
                ],
                "members": [
                    {
                        "name": "M1",
                        "displacement_points": [
                            point(0.0, 0.0),
                            point(0.0, 6500.0, -19.0, -0.3),
                        ],
                    },
                    {
                        "name": "M2",
                        "displacement_points": [
                            point(0.0, 6500.0, -19.0, -0.3),
                            point(9000.0, 8500.0, 0.0, -89.9),
                        ],
                    },
                    {
                        "name": "M3",
                        "displacement_points": [
                            point(9000.0, 8500.0, 0.0, -89.9),
                            point(18000.0, 6500.0, 19.0, -0.3),
                        ],
                    },
                    {
                        "name": "M4",
                        "displacement_points": [
                            point(18000.0, 6500.0, 19.0, -0.3),
                            point(18000.0, 0.0),
                        ],
                    },
                ],
            }],
        }
        svg = base64.b64decode(
            load_case_svg(
                visualisation,
                "1.1 DL + 1.0 LL",
                view="deflection",
                component="total deflection",
            ).split(",", 1)[1]
        ).decode("utf-8")

        self.assertIn("displayed &#215;9.5", svg)
        self.assertIn('data-node-name="N3"', svg)
        self.assertNotIn('data-node-name="HN1"', svg)
        self.assertNotIn("HN1 Total", svg)
        self.assertIn("physical-node labels", svg)

    def test_dead_live_vertical_limit_can_be_ignored_without_removing_combo(self):
        frame_data = {
            "ignore_1_1_dl_1_0_ll_vertical_deflection_limit": "Yes"
        }
        self.assertFalse(
            _vertical_deflection_limit_applies(
                frame_data, "1.1 DL + 1.0 LL"
            )
        )
        self.assertTrue(
            _vertical_deflection_limit_applies(
                frame_data, "1.1 DL + 0.6 W0_0.3M2"
            )
        )
        values = dict(DEFAULT_VALUES)
        values[
            "ignore_1_1_dl_1_0_ll_vertical_deflection_limit"
        ] = True
        payload = build_analysis_payload(values)
        self.assertEqual(
            payload["building_data"][
                "ignore_1_1_dl_1_0_ll_vertical_deflection_limit"
            ],
            "Yes",
        )
        deflections = [
            {
                "load_combination": "1.1 DL + 1.0 LL",
                "max_dx": 4.0,
                "max_dy": 120.0,
            },
            {
                "load_combination": "1.1 DL + 0.6 W0_0.3M2",
                "max_dx": 20.0,
                "max_dy": 75.0,
            },
        ]
        governing_dx, governing_dy, ignored = (
            governing_serviceability_deflections(
                deflections,
                payload["building_data"],
            )
        )
        self.assertEqual(
            governing_dx["load_combination"],
            "1.1 DL + 0.6 W0_0.3M2",
        )
        self.assertEqual(
            governing_dy["load_combination"],
            "1.1 DL + 0.6 W0_0.3M2",
        )
        self.assertEqual(ignored, [deflections[0]])


class PermanentBaselineDeflectionTests(unittest.TestCase):
    @staticmethod
    def model(*, reversed_fall=False):
        combination = {
            "name": "1.1 DL + 1.0 LL",
            "factors": {"D": 1.1, "D_MAX": 1.1, "L": 1.0},
        }
        baseline = permanent_baseline_name(combination)
        n1_total = 0.0 if reversed_fall else -10.0
        n2_total = -120.0 if reversed_fall else -20.0
        frame = SimpleNamespace(nodes={
            "N1": SimpleNamespace(
                DX={combination["name"]: 0.0, baseline: 0.0},
                DY={combination["name"]: n1_total, baseline: -8.0},
            ),
            "N2": SimpleNamespace(
                DX={combination["name"]: 0.0, baseline: 0.0},
                DY={combination["name"]: n2_total, baseline: -12.0},
            ),
        })
        data = SimpleNamespace(
            serviceability_load_combinations=[combination],
            nodes={
                "N1": SimpleNamespace(y=0.0),
                "N2": SimpleNamespace(y=100.0),
            },
            members=[
                SimpleNamespace(
                    name="R1",
                    type="rafter",
                    i_node="N1",
                    j_node="N2",
                )
            ],
        )
        return frame, data

    def test_variable_deflection_is_measured_from_permanent_baseline(self):
        frame, data = self.model()
        row = serviceability_deflection_rows(frame, data)[0]
        self.assertEqual(row["permanent_max_dy"], 12.0)
        self.assertEqual(row["total_max_dy"], 20.0)
        self.assertEqual(row["max_dy"], 8.0)
        self.assertEqual(row["variable_dy_at_variable_node"], -8.0)
        self.assertEqual(
            row["total_dy_at_variable_node"]
            - row["permanent_dy_at_variable_node"],
            row["variable_dy_at_variable_node"],
        )
        self.assertEqual(row["roof_drainage"]["status"], "PASS")

    def test_toggle_off_uses_total_vertical_deflection(self):
        frame, data = self.model()
        data.frame_data = [{
            "use_permanent_deflection_baseline": "No",
        }]
        row = serviceability_deflection_rows(frame, data)[0]
        self.assertEqual(row["max_dy"], 20.0)
        self.assertEqual(row["dy_node"], "N2")
        self.assertFalse(row["uses_permanent_deflection_baseline"])
        self.assertIn("Total serviceability", row["vertical_deflection_basis"])
        self.assertEqual(row["total_dy_at_checked_node"], -20.0)
        self.assertEqual(row["permanent_dy_at_checked_node"], -12.0)
        self.assertEqual(row["variable_dy_at_checked_node"], -8.0)
        self.assertEqual(row["roof_drainage"]["status"], "PASS")

    def test_toggle_is_saved_in_the_analysis_payload(self):
        values = dict(DEFAULT_VALUES)
        values["use_permanent_deflection_baseline"] = False
        payload = build_analysis_payload(values)
        self.assertEqual(
            payload["building_data"]["use_permanent_deflection_baseline"],
            "No",
        )

    def test_reversed_roof_fall_is_a_ponding_failure(self):
        frame, data = self.model(reversed_fall=True)
        data.frame_data = [{
            "use_permanent_deflection_baseline": "No",
        }]
        row = serviceability_deflection_rows(frame, data)[0]
        self.assertEqual(row["max_dy"], 120.0)
        self.assertEqual(row["roof_drainage"]["status"], "FAIL")
        self.assertEqual(
            row["roof_drainage"]["reversed_segments"][0]["member"], "R1"
        )


class FoundationDesignTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "input_data": {
                "load_combinations": [{"name": "ULS"}],
                "serviceability_load_combinations": [{"name": "SLS"}],
            },
            "results": {
                "reactions": [
                    {
                        "node": "N1",
                        "load_combination": "SLS",
                        "fx": 20.0,
                        "fy": 300.0,
                        "fz": 0.0,
                        "mx": 0.0,
                        "my": 0.0,
                        "mz": 30.0,
                    },
                    {
                        "node": "N1",
                        "load_combination": "ULS",
                        "fx": 30.0,
                        "fy": 450.0,
                        "fz": 0.0,
                        "mx": 0.0,
                        "my": 0.0,
                        "mz": 45.0,
                    },
                ]
            },
        }

    def test_both_concrete_standards_return_auditable_checks(self):
        for standard in FOUNDATION_STANDARDS:
            inputs = dict(DEFAULT_FOUNDATION_VALUES)
            inputs["foundation_standard"] = standard
            result = design_pad_foundations(self.snapshot, inputs)
            self.assertEqual(result["standard"], standard)
            self.assertEqual(result["supports"][0]["node"], "N1")
            check_names = {
                check["name"]
                for check in result["supports"][0]["structural"]["checks"]
            }
            self.assertIn("Punching shear - control perimeter", check_names)
            self.assertIn("One-way shear - frame direction", check_names)
            self.assertTrue(result["references"])
            self.assertTrue(result["warnings"])

    def test_missing_sls_reactions_is_rejected(self):
        snapshot = {
            **self.snapshot,
            "results": {
                "reactions": [
                    row
                    for row in self.snapshot["results"]["reactions"]
                    if row["load_combination"] == "ULS"
                ]
            },
        }
        with self.assertRaisesRegex(ValueError, "SLS reactions"):
            design_pad_foundations(snapshot, DEFAULT_FOUNDATION_VALUES)


if __name__ == "__main__":
    unittest.main()
