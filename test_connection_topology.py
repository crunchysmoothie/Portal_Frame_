from __future__ import annotations

import unittest
from copy import deepcopy

from connection_design import design_portal_connections
from test_foundation_connections import _snapshot


def _two_haunch_snapshot() -> dict:
    snapshot = deepcopy(_snapshot())
    frame = snapshot["input_data"]["frame_data"][0]
    frame.update({
        "use_eaves_haunch": "Yes",
        "eaves_haunch_length": 1_500.0,
        "eaves_haunch_depth": 100.0,
        "use_apex_haunch": "Yes",
        "apex_haunch_length": 1_000.0,
        "apex_haunch_depth": 100.0,
    })
    snapshot["results"]["project"]["column_section"] = "305x165x40"
    snapshot["results"]["project"]["rafter_section"] = "254x146x31"
    return snapshot


def _by_type(items: list[dict], connection_type: str) -> dict:
    return next(
        item
        for item in items
        if item["connection_type"] == connection_type
    )


class ConnectionTopologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = design_portal_connections(_two_haunch_snapshot())
        cls.geometry = cls.result["haunch_connections"]["locations"]
        cls.detailed = cls.result["detailed_checks"]["haunch_connections"][
            "locations"
        ]

    def test_eaves_and_apex_have_distinct_supporting_members(self):
        eaves = _by_type(self.geometry, "eaves_end_plate")
        apex = _by_type(self.geometry, "apex_splice")

        self.assertEqual(eaves["supporting_member_type"], "column")
        self.assertEqual(eaves["supporting_member_section"], "305x165x40")
        self.assertEqual(
            eaves["connection"]["connection_type"],
            "eaves_end_plate",
        )
        self.assertEqual(
            eaves["connection"]["supporting_member_type"],
            "column",
        )

        self.assertEqual(apex["supporting_member_type"], "opposing_rafter")
        self.assertEqual(apex["supporting_member_section"], "254x146x31")
        self.assertEqual(
            apex["connection"]["connection_type"],
            "apex_splice",
        )
        self.assertEqual(
            apex["connection"]["supporting_member_type"],
            "opposing_rafter",
        )

    def test_local_checks_use_connection_specific_topology_wording(self):
        eaves = _by_type(self.detailed, "eaves_end_plate")
        apex = _by_type(self.detailed, "apex_splice")

        eaves_text = " ".join(
            str(check.get(field, ""))
            for check in eaves["local_member_checks"]
            for field in ("name", "equation", "source", "note")
        )
        apex_text = " ".join(
            str(check.get(field, ""))
            for check in apex["local_member_checks"]
            for field in ("name", "equation", "source", "note")
        )

        self.assertIn("Supporting column flange", eaves_text)
        self.assertIn("Supporting column web", eaves_text)
        self.assertIn("Opposing rafter flange", apex_text)
        self.assertIn("Opposing rafter web", apex_text)
        self.assertNotIn("column", apex_text.lower())
        self.assertEqual(apex["supporting_member_type"], "opposing_rafter")

    def test_bolt_coordinates_match_count_gauge_and_pitch(self):
        for location in self.geometry:
            with self.subTest(connection_type=location["connection_type"]):
                bolts = location["connection"]["bolts"]
                coordinates = bolts["coordinates_from_plate_centre_mm"]
                row_count = int(bolts["row_count"])
                pitch = float(bolts["pitch_mm"])
                gauge = float(bolts["gauge_mm"])

                self.assertEqual(len(coordinates), bolts["bolt_count"])
                x_values = sorted({float(point["x"]) for point in coordinates})
                y_values = sorted({float(point["y"]) for point in coordinates})
                self.assertEqual(len(x_values), 2)
                self.assertEqual(len(y_values), row_count)
                self.assertAlmostEqual(x_values[0], -gauge / 2.0)
                self.assertAlmostEqual(x_values[1], gauge / 2.0)
                for y_value in y_values:
                    self.assertEqual(
                        sum(
                            1
                            for point in coordinates
                            if float(point["y"]) == y_value
                        ),
                        2,
                    )
                for first, second in zip(y_values, y_values[1:]):
                    self.assertAlmostEqual(second - first, pitch)

                plate = location["connection"]["plate"]
                self.assertAlmostEqual(
                    float(plate["height_mm"]) / 2.0
                    - max(abs(value) for value in y_values),
                    float(bolts["end_distance_mm"]),
                )

    def test_source_rafter_geometry_and_donor_note_are_explicit(self):
        for location in self.geometry:
            with self.subTest(connection_type=location["connection_type"]):
                source = location["source_rafter_geometry"]
                self.assertEqual(
                    set(source), {"h", "b", "tw", "tf", "r1", "hw"}
                )
                self.assertTrue(all(float(value) > 0 for value in source.values()))
                note = location["donor_fabrication_note"].lower()
                self.assertIn("top flange removed", note)
                self.assertIn("remaining web welded", note)
                self.assertIn("main rafter", note)


if __name__ == "__main__":
    unittest.main()
