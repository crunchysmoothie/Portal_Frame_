import unittest

import member_database as mdb
from foundation_design import (
    DEFAULT_FOUNDATION_VALUES,
    FOUNDATION_STANDARDS,
    design_pad_foundations,
)
from frame_model import Member, Node, PortalFrame
from haunch_design import composite_haunch_properties
from portal_frame_analysis import build_model
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
        depths = (0.0, 1.0, 10.0, 100.0, 400.0)
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
            "N2": Node("N2", 0, 6000, 0),
            "N3": Node("N3", 5000, 7000, 0),
            "N4": Node("N4", 10000, 6000, 0),
            "N5": Node("N5", 10000, 0, 0),
        }
        members = [
            Member("M1", "N1", "N2", "Steel_S355", "column", 6.0),
            Member("M2", "N2", "N3", "Steel_S355", "rafter", 5.099),
            Member("M3", "N3", "N4", "Steel_S355", "rafter", 5.099),
            Member("M4", "N4", "N5", "Steel_S355", "column", 6.0),
        ]
        data = PortalFrame(
            frame_data=[{
                "building_roof": "Duo Pitched",
                "gable_width": 10000,
                "eaves_height": 6000,
                "apex_height": 7000,
                "use_eaves_haunch": "Yes",
                "eaves_haunch_length": 1500,
                "eaves_haunch_depth": 450,
                "use_apex_haunch": "Yes",
                "apex_haunch_length": 1000,
                "apex_haunch_depth": 300,
            }],
            nodes=nodes,
            members=members,
            supports={
                "N1": {"DX": True, "DY": True, "DZ": True},
                "N5": {"DX": True, "DY": True, "DZ": True},
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
        frame.members["M2"].descritize()
        sections = [
            member.section.name
            for member in frame.members["M2"].sub_members.values()
        ]
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
