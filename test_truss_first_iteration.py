from __future__ import annotations

import math
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.analysis_service import _normalise_payload
from backend.main import preview
from roof_layout import calculate_roof_bracing_layout
from truss_design import (
    bounded_depth_candidates_mm,
    design_truss,
    load_angle_candidates,
)
from truss_loading import _consistent_segment_loads
from truss_model import (
    analyse_truss,
    calculate_chord_restraint_layout,
    generate_truss_geometry,
)
from truss_report import write_truss_html, write_truss_json
from ui.analysis_render import combination_names, load_case_svg
from ui.input_model import DEFAULT_VALUES, InputValidationError, build_analysis_payload
from ui.preview_render import (
    truss_elevation_svg,
    truss_girder_elevation_svg,
    truss_roof_plan_svg,
    truss_type_reference_svg,
)


class TrussGeometryTests(unittest.TestCase):
    def test_shared_portal_distribution_remains_remainder_first(self):
        layout = calculate_roof_bracing_layout(
            16_000, 6_500, 7_500, "Duo Pitched", 1_000, 2
        )
        self.assertEqual(layout["purlin_spaces_per_slope"], 9)
        self.assertEqual(layout["purlin_spaces_per_brace_panel"], [5, 4])

    def test_piecewise_line_load_preserves_zone_boundaries(self):
        loads = [
            {"x1": 0, "x2": 400, "w1": -0.001, "w2": -0.001},
            {"x1": 400, "x2": 1_000, "w1": -0.002, "w2": -0.002},
        ]
        integrated = _consistent_segment_loads(loads, 0, 1_000, 1_000)
        self.assertAlmostEqual(
            sum(i_force + j_force for _, i_force, j_force in integrated), -1.6
        )

    def test_single_span_supports_and_full_length_nth_purlin_restraint(self):
        geometry = generate_truss_geometry(
            (40_000,), "Duo Pitched", 3_500, 2_400, 1_800,
            topology="Warren with verticals", chord_form="Parallel chords",
        )
        self.assertEqual(len(geometry.support_nodes), 2)
        self.assertLessEqual(geometry.panel_width_mm, 1_800)
        self.assertEqual(len(geometry.members), 2 * len(geometry.nodes) - 3)
        restraints = calculate_chord_restraint_layout(geometry, 2, 3)
        self.assertEqual(restraints["top_chord"]["brace_every_n_purlins"], 2)
        self.assertEqual(restraints["bottom_chord"]["brace_every_n_purlins"], 3)
        self.assertEqual(restraints["top_chord"]["coverage"], "Entire building length")
        self.assertTrue(all(
            interval["panel_spaces"] <= 2
            for interval in restraints["top_chord"]["intervals"]
        ))

    def test_mono_pratt_horizontal_bottom_chord_geometry(self):
        geometry = generate_truss_geometry(
            (30_000,), "Mono Pitched", 3_000, 2_000, 1_500,
            topology="Pratt", chord_form="Horizontal bottom chord",
        )
        nodes = {node.name: node for node in geometry.nodes}
        self.assertEqual(geometry.roof_form, "Mono Pitched")
        self.assertTrue(all(math.isclose(nodes[name].y_mm, 0.0) for name in (
            f"B{index}" for index in range(geometry.panel_count + 1)
        )))
        self.assertGreater(nodes[f"T{geometry.panel_count}"].y_mm, nodes["T0"].y_mm)

    def test_duo_pitch_apex_is_a_panel_point_for_asymmetric_spans(self):
        geometry = generate_truss_geometry(
            (20_000, 40_000), "Duo Pitched", 5_000, 2_400, 1_700,
            topology="Warren with verticals", chord_form="Parallel chords",
        )
        top_nodes = [node for node in geometry.nodes if node.role == "top_chord"]
        apex = next(node for node in top_nodes if math.isclose(node.x_mm, 30_000))
        self.assertAlmostEqual(apex.y_mm, 7_400)
        self.assertLessEqual(geometry.panel_width_mm, 1_700)

    def test_linear_solver_balances_symmetric_vertical_load(self):
        geometry = generate_truss_geometry(
            (16_000,), "Duo Pitched", 1_000, 1_200, 1_600,
            topology="Howe", chord_form="Parallel chords",
        )
        areas = {member.name: 1_000.0 for member in geometry.members}
        loads = {node: (0.0, -10.0) for node in geometry.top_node_names}
        result = analyse_truss(geometry, areas, loads)
        left = result["reactions_kn"][geometry.left_support]
        right = result["reactions_kn"][geometry.right_support]
        self.assertAlmostEqual(left["fy"] + right["fy"], 10 * len(loads), places=6)
        self.assertAlmostEqual(left["fy"], right["fy"], places=6)

    def test_explicit_depth_search_includes_both_limits(self):
        self.assertEqual(
            bounded_depth_candidates_mm(2_000, 2_500, 200),
            [2_000, 2_200, 2_400, 2_500],
        )


class TrussWorkflowTests(unittest.TestCase):
    @staticmethod
    def payload(**updates):
        raw = dict(DEFAULT_VALUES)
        raw["structural_system"] = "Truss"
        raw.update(updates)
        return build_analysis_payload(raw)

    def test_equal_angle_library_includes_single_and_back_to_back(self):
        candidates = load_angle_candidates()
        configurations = {item.configuration for item in candidates}
        self.assertEqual(
            configurations, {"Single equal angle", "Back-to-back equal angles"}
        )
        for candidate in candidates:
            leg_1, leg_2, thickness = (
                float(value) for value in candidate.base_designation.split("x")
            )
            self.assertGreaterEqual(leg_1, 50)
            self.assertGreaterEqual(leg_2, 50)
            self.assertGreaterEqual(thickness, 5)

    def test_single_span_payload_preview_and_visual_references(self):
        payload = self.payload()
        self.assertEqual(_normalise_payload(payload)["structural_system"], "Truss")
        self.assertEqual(payload["truss_data"]["span_count"], 1)
        self.assertEqual(payload["truss_data"]["building_width_mm"], 40_000)
        truss_preview = preview(payload)
        self.assertEqual(
            truss_preview["building_layout"]["support_arrangement"]["sequence"],
            ["Main column left", "Main column right"],
        )
        self.assertEqual(
            truss_preview["building_layout"]["bracing"]["coverage"],
            "Entire building length",
        )
        for image in (
            truss_type_reference_svg("Pratt"),
            truss_elevation_svg(truss_preview),
            truss_roof_plan_svg(truss_preview),
            truss_girder_elevation_svg(truss_preview),
        ):
            self.assertTrue(image.startswith("data:image/svg+xml;base64,"))
        elevation = base64.b64decode(
            truss_elevation_svg(truss_preview).split(",", 1)[1]
        ).decode("utf-8")
        self.assertIn("Same physical scale horizontally and vertically", elevation)
        self.assertEqual(elevation.count('data-role="support-column"'), 2)
        self.assertIn("Total width 40 m", elevation)
        self.assertNotIn("exaggerated", elevation)

    def test_multiple_span_centre_column_support_sequence(self):
        payload = self.payload(
            truss_transverse_bay_spans_m="30,30",
            truss_building_length_m="24",
            truss_spacing_m="6",
            truss_internal_support="Centre columns",
        )
        truss_preview = preview(payload)
        layout = truss_preview["building_layout"]
        self.assertEqual(payload["truss_data"]["span_count"], 2)
        self.assertEqual(payload["building_data"]["gable_width"], 60_000)
        self.assertEqual(
            layout["support_arrangement"]["sequence"],
            ["Main column left", "Centre columns", "Main column right"],
        )
        self.assertEqual(layout["columns"]["internal_count"], 5)
        self.assertFalse(layout["girders"])
        elevation = base64.b64decode(
            truss_elevation_svg(truss_preview).split(",", 1)[1]
        ).decode("utf-8")
        self.assertEqual(elevation.count('data-role="support-column"'), 3)
        self.assertEqual(elevation.count('data-role="span-dimension"'), 2)
        self.assertEqual(elevation.count(">30 m</text>"), 2)

    def test_centre_column_design_choice_and_axial_steel_result(self):
        payload = self.payload(
            truss_transverse_bay_spans_m="30,30",
            truss_building_length_m="24",
            truss_spacing_m="6",
            truss_internal_support="Centre columns",
            truss_design_centre_columns=True,
            truss_centre_column_material="Steel",
            truss_centre_column_bracing_spacing_m="6",
            truss_centre_column_steel_section_order="Automatic - lightest passing",
            truss_minimum_depth_m="2.4",
            truss_maximum_depth_m="2.4",
        )
        self.assertTrue(payload["truss_data"]["design_centre_columns"])
        self.assertEqual(payload["truss_data"]["centre_column_material"], "Steel")
        result = design_truss(payload)
        centre = result["ranked_solutions"][0]["centre_column_design"]
        self.assertEqual(centre["status"], "PASS")
        self.assertEqual(centre["material"], "Steel")
        self.assertGreater(centre["total_mass_kg"], 0)
        self.assertEqual(
            result["ranked_solutions"][0]["bearing_support_verticals"][1]["source"],
            "Designed axial centre column",
        )

    def test_concrete_tilt_up_is_explicit_hold_point(self):
        payload = self.payload(
            truss_transverse_bay_spans_m="30,30",
            truss_internal_support="Centre columns",
            truss_design_centre_columns=True,
            truss_centre_column_material="Concrete tilt-up",
        )
        result = design_truss(payload)
        centre = result["ranked_solutions"][0]["centre_column_design"]
        self.assertEqual(centre["status"], "HOLD_POINT")
        self.assertEqual(centre["material"], "Concrete tilt-up")

    def test_mono_pitch_is_preserved_through_loading_and_design(self):
        result = design_truss(self.payload(
            building_roof="Mono Pitched",
            truss_type="Pratt",
            truss_chord_form="Horizontal bottom chord",
            truss_transverse_bay_spans_m="30",
            truss_minimum_depth_m="2.4",
            truss_maximum_depth_m="2.4",
        ))
        solution = result["ranked_solutions"][0]
        self.assertEqual(solution["geometry"]["roof_form"], "Mono Pitched")
        self.assertAlmostEqual(solution["load_source"]["candidate_roof_pitch_deg"], 5.0)
        visualisation = solution["load_case_visualisation"]
        sls_names = combination_names(visualisation, "SLS")
        self.assertTrue(sls_names)
        self.assertNotIn("nodes", visualisation["combinations"][0])
        deflection_svg = base64.b64decode(
            load_case_svg(
                visualisation,
                solution["serviceability"]["governing_combination"],
                view="deflection",
                component="total deflection",
            ).split(",", 1)[1]
        ).decode("utf-8")
        self.assertIn('data-role="deformed-member"', deflection_svg)
        self.assertIn("Deformation is magnified", deflection_svg)
        self.assertIn("exact calculated value", deflection_svg)

    def test_multiple_span_girder_length_and_lightest_design(self):
        payload = self.payload(
            truss_transverse_bay_spans_m="30,30",
            truss_building_length_m="24",
            truss_spacing_m="6",
            truss_internal_support="Longitudinal girders",
            truss_girder_span_bays="2",
            truss_minimum_depth_m="2.4",
            truss_maximum_depth_m="2.4",
            truss_girder_minimum_depth_m="2.0",
            truss_girder_maximum_depth_m="2.0",
        )
        truss_preview = preview(payload)
        girder_layout = truss_preview["building_layout"]["girders"][0]
        self.assertEqual(girder_layout["span_length_mm"], 12_000)
        self.assertEqual(girder_layout["span_count"], 2)
        result = design_truss(payload)
        solution = result["ranked_solutions"][0]
        self.assertEqual(result["engine"], "preliminary_generic_truss_v0.6")
        self.assertEqual(solution["girder_design"]["status"], "PASS")
        self.assertEqual(solution["girder_design"]["geometry"]["span_mm"], 12_000)
        self.assertAlmostEqual(
            solution["arrangement_mass_kg"],
            solution["total_truss_mass_kg"]
            + solution["eave_column_design"]["total_mass_kg"]
            + solution["girder_design"]["total_mass_kg"],
        )
        for group in solution["girder_design"]["chord_fabrication_groups"]:
            sections = {
                item["section"]["designation"]
                for item in solution["girder_design"]["member_schedule"]
                if item["fabrication_group"] == group["group"]
            }
            self.assertEqual(len(sections), 1)
        self.assertEqual(solution["geometry"]["bearing_nodes"], ["T0", "T20", "T40"])
        self.assertEqual(
            solution["geometry"]["support_vertical_members"],
            ["V1", "V21", "V41"],
        )
        support_sources = [
            item["source"] for item in solution["bearing_support_verticals"]
        ]
        self.assertEqual(support_sources[0], "Main eave column")
        self.assertEqual(support_sources[-1], "Main eave column")
        self.assertEqual(
            support_sources[1], "Longitudinal girder bearing vertical"
        )
        self.assertTrue(all(
            group["member_count"] >= 3
            for group in solution["web_fabrication_groups"]
        ))

    def test_input_boundary_rejects_inconsistent_layouts(self):
        cases = (
            {"truss_transverse_bay_spans_m": ""},
            {"truss_transverse_bay_spans_m": "30,-5"},
            {"truss_top_chord_brace_every_n_purlins": "2.5"},
            {
                "truss_transverse_bay_spans_m": "30,30",
                "truss_building_length_m": "24", "truss_spacing_m": "6",
                "truss_internal_support": "Longitudinal girders",
                "truss_girder_span_bays": "3",
            },
        )
        for updates in cases:
            with self.subTest(updates=updates), self.assertRaises(InputValidationError):
                self.payload(**updates)

    def test_single_span_end_to_end_reports_lightest_arrangement(self):
        result = design_truss(self.payload(
            truss_minimum_depth_m="2.4", truss_maximum_depth_m="2.4"
        ))
        self.assertIn("CALCULATION DRAFT", result["validation_status"])
        solution = result["ranked_solutions"][0]
        self.assertEqual(solution["status"], "PASS")
        self.assertLessEqual(solution["governing_strength"]["utilisation"], 1.0)
        self.assertLessEqual(solution["serviceability"]["utilisation"], 1.0)
        self.assertEqual(solution["girder_design"]["status"], "NOT_REQUIRED")
        self.assertEqual(solution["eave_column_design"]["status"], "PASS")
        self.assertTrue(all(
            node["role"] == "bearing"
            for node in solution["geometry"]["nodes"]
            if node["name"] in solution["geometry"]["bearing_nodes"]
        ))
        self.assertTrue(all(
            item["role"] == "support_vertical"
            for item in solution["member_schedule"]
            if item["member"] in solution["geometry"]["support_vertical_members"]
        ))
        self.assertAlmostEqual(
            solution["platework_cost_allowance_equivalent_kg"],
            0.08 * solution["arrangement_mass_kg"],
        )
        self.assertAlmostEqual(
            solution["practical_cost_equivalent_kg"],
            1.08 * solution["arrangement_mass_kg"],
        )
        for group in solution["chord_fabrication_groups"]:
            sections = {
                item["section"]["designation"]
                for item in solution["member_schedule"]
                if item["fabrication_group"] == group["group"]
            }
            self.assertEqual(len(sections), 1)
        with TemporaryDirectory() as directory:
            html = write_truss_html(result, Path(directory) / "truss.html")
            data = write_truss_json(result, Path(directory) / "truss.json")
            report = html.read_text(encoding="utf-8")
            self.assertIn("Truss Design Calculation - Draft", report)
            self.assertIn("Every 1 purlin", report)
            self.assertIn("Arrangement mass", report)
            self.assertIn("Minimum base angle: 50x50x5", report)
            self.assertIn("Chord fabrication groups", report)
            self.assertIn("Web fabrication groups", report)
            self.assertIn("Bearing nodes and support verticals", report)
            self.assertIn("8% platework allowance", report)
            self.assertIn("below 75%", report)
            self.assertIn("slenderness", report)
            self.assertIn("ranked_solutions", data.read_text(encoding="utf-8"))

    def test_passing_depths_expose_practical_and_lightest_rankings(self):
        result = design_truss(self.payload(
            truss_minimum_depth_m="2.2",
            truss_maximum_depth_m="2.4",
            truss_depth_increment_m="0.2",
            truss_ranked_solution_count="2",
        ))
        practical_costs = [
            item["practical_cost_equivalent_kg"]
            for item in result["ranked_solutions"]
        ]
        lightest_masses = [
            item["lightest_member_arrangement_mass_kg"]
            for item in result["lightest_mass_solutions"]
        ]
        self.assertEqual(result["candidate_summary"]["passed"], 2)
        self.assertEqual(practical_costs, sorted(practical_costs))
        self.assertEqual(lightest_masses, sorted(lightest_masses))
        self.assertEqual(result["ranked_solutions"][0]["rank"], 1)
        self.assertEqual(
            result["lightest_mass_solutions"][0]["lightest_mass_rank"], 1
        )


if __name__ == "__main__":
    unittest.main()
