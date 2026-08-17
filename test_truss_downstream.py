import re
import tempfile
import unittest
from pathlib import Path

from reporting_workflow.boq import build_truss_structural_boq_takeoff
from truss_workflow.downstream import build_truss_analysis_snapshot
from truss_workflow.model import (
    WARREN_INTERMEDIATE_VERTICALS,
    calculate_chord_restraint_layout,
    generate_truss_geometry,
    member_length_mm,
)
from truss_workflow.report import write_truss_markup_html


class TrussDownstreamTests(unittest.TestCase):
    def setUp(self):
        self.geometry = generate_truss_geometry(
            (20_000.0,),
            "Duo Pitched",
            1_800.0,
            2_000.0,
            1_600.0,
            topology=WARREN_INTERMEDIATE_VERTICALS,
            chord_form="Parallel chords",
        )
        self.restraint = calculate_chord_restraint_layout(
            self.geometry, 1, 2
        )

    def test_top_and_bottom_restraints_share_transverse_lines(self):
        top = self.restraint["top_chord"]["restraint_nodes"]
        bottom = self.restraint["bottom_chord"]["restraint_nodes"]
        self.assertEqual(
            [round(item["x_mm"], 6) for item in top],
            [round(item["x_mm"], 6) for item in bottom],
        )
        self.assertTrue(any(not item["analysis_node"] for item in bottom))
        self.assertTrue(all(item["connection_node"] for item in bottom))

    def test_markup_uses_section_marks_without_node_callouts(self):
        schedule = []
        for member in self.geometry.members:
            schedule.append({
                "member": member.name,
                "role": member.role,
                "i_node": member.i_node,
                "j_node": member.j_node,
                "length_mm": member_length_mm(self.geometry, member),
                "section": {
                    "designation": (
                        "2L 120x120x8"
                        if member.role in {"top_chord", "bottom_chord"}
                        else "2L 60x60x5"
                    ),
                    "mass_kg_m": 10.0,
                },
                "utilisation": 0.5,
            })
        result = {
            "ranked_solutions": [{
                "geometry": self.geometry.to_dict(),
                "member_schedule": schedule,
                "chord_restraint_layout": self.restraint,
            }]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = write_truss_markup_html(
                result, Path(directory) / "markup.html"
            )
            html = path.read_text(encoding="utf-8")
        overview = html.split("</svg>", 1)[0]
        self.assertIsNone(re.search(r">[TB]\d+<", overview))
        self.assertRegex(overview, r">S\d+<")
        self.assertIn("paired chord restraint points", overview)

    def test_snapshot_and_boq_are_truss_specific(self):
        geometry = self.geometry.to_dict()
        combinations = [{"name": "ULS", "factors": {"D": 1.35}}]
        service = [{"name": "SLS", "factors": {"D": 1.0}}]
        support_reactions = {
            "ULS": {
                geometry["support_nodes"][0]: {"fx": 0.0, "fy": 100.0},
                geometry["support_nodes"][-1]: {"fx": 0.0, "fy": 100.0},
            }
        }
        service_reactions = {
            "SLS": {
                geometry["support_nodes"][0]: {"fx": 0.0, "fy": 75.0},
                geometry["support_nodes"][-1]: {"fx": 0.0, "fy": 75.0},
            }
        }
        characteristic = {
            "D": {
                geometry["support_nodes"][0]: {"fx": 0.0, "fy": 75.0},
                geometry["support_nodes"][-1]: {"fx": 0.0, "fy": 75.0},
            }
        }
        member = self.geometry.members[0]
        best = {
            "geometry": geometry,
            "building_layout": {
                "support_arrangement": {"internal_support": "Not required"},
                "longitudinal": {"grid_labels": ["A", "B", "C"]},
            },
            "truss_count": 3,
            "member_schedule": [{
                "member": member.name,
                "role": member.role,
                "length_mm": member_length_mm(self.geometry, member),
                "section": {"designation": "2L 120x120x8", "mass_kg_m": 28.0},
            }],
            "eave_column_design": {
                "status": "PASS", "section": "203x133x25",
                "mass_kg_m": 25.1, "height_mm": 6_500.0,
                "column_count": 6, "total_mass_kg": 978.9,
            },
            "centre_column_design": {"status": "NOT_REQUIRED"},
            "girder_design": {"status": "NOT_REQUIRED"},
            "purlins": {
                "section": "175x65x20x2.5", "total_length_m": 180.0,
                "mass_per_m_kg": 4.5, "mass_kg": 810.0,
            },
            "support_reactions_uls_kn": support_reactions,
            "support_reactions_sls_kn": service_reactions,
            "support_reactions_characteristic_kn": characteristic,
            "load_audit": {
                "uls_combinations": combinations,
                "sls_combinations": service,
                "eave_column_wall_actions": {
                    side: {"cases": {"D": {"resultant_kn": 0.0, "base_moment_knm": 0.0}}}
                    for side in ("left", "right")
                },
            },
        }
        result = {
            "ranked_solutions": [best],
            "bracing_design": {},
            "structural_system": "Truss",
        }
        payload = {
            "project": {"name": "Test truss", "number": "T-01", "designer": ""},
            "building_data": {
                "building_type": "Normal", "building_roof": "Duo Pitched",
                "building_length": 12_000.0, "rafter_spacing": 6_000.0,
                "eaves_height": 6_500.0, "purlin_section": "175x65x20x2.5",
                "girt_section": "175x65x20x2.5", "girt_max_spacing_mm": 1_600.0,
                "opening_areas_m2": {},
            },
            "truss_data": {},
        }
        snapshot = build_truss_analysis_snapshot(result, payload, "abc123def456")
        self.assertEqual(snapshot["results"]["project"]["structural_system"], "Truss")
        self.assertEqual(snapshot["results"]["foundation_support_quantities"]["BASE_LEFT"], 3)
        takeoff = build_truss_structural_boq_takeoff(snapshot, {}, [])
        descriptions = [item["description"] for item in takeoff["steel_items"]]
        self.assertTrue(any(
            item.startswith("Truss ") and item.endswith(" - 2L 120x120x8")
            for item in descriptions
        ))
        self.assertFalse(any("Haunch" in item for item in descriptions))


if __name__ == "__main__":
    unittest.main()
