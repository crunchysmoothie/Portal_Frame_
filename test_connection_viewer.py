import inspect
import unittest
from copy import deepcopy
from unittest.mock import patch

import plotly.graph_objects as go

from connection_design import design_portal_connections
from connection_viewer import (
    MODEBAR_EXPORT_ITEMS,
    VIEWER_CONFIG,
    build_connection_figure,
    build_connection_viewer_html,
    list_connection_views,
)
from test_foundation_connections import _snapshot


def _result():
    result = design_portal_connections(_snapshot())
    result["haunch_connections"]["locations"][0]["added_depth_mm"] = 230.0
    return result


def _valid_eaves_result():
    result = _result()
    result["haunch_connections"]["locations"][0]["added_depth_mm"] = 100.0
    return result


def _valid_apex_result():
    result = _valid_eaves_result()
    location = result["haunch_connections"]["locations"][0]
    location["location"] = "Apex haunch"
    location["connection_type"] = "apex_splice"
    location["connection"]["connection_type"] = "apex_splice"
    location["supporting_member_type"] = "opposing_rafter"
    location["supporting_member_section"] = location["rafter_section"]
    return result


def _mesh_traces(figure):
    return [trace for trace in figure.data if isinstance(trace, go.Mesh3d)]


def _roles(figure):
    return [
        (trace.meta or {}).get("role")
        for trace in _mesh_traces(figure)
    ]


def _trace_centre(trace):
    return tuple(
        sum(float(value) for value in coordinates) / len(coordinates)
        for coordinates in (trace.x, trace.y, trace.z)
    )


def _trace_spans(trace):
    return tuple(
        max(float(value) for value in coordinates)
        - min(float(value) for value in coordinates)
        for coordinates in (trace.x, trace.y, trace.z)
    )


class ConnectionViewerTests(unittest.TestCase):
    def test_views_are_stable_and_invalid_geometry_remains_selectable(self):
        result = _result()
        views = list_connection_views(result)
        self.assertEqual(
            [item["key"] for item in views],
            ["base:n1", "base:n7", "haunch:eaves-haunch"],
        )
        self.assertTrue(views[0]["available"])
        self.assertFalse(views[-1]["available"])
        self.assertIn("source-rafter limit", views[-1]["reason"])

    def test_base_plate_has_section_plate_and_cylindrical_anchors(self):
        result = _result()
        figure = build_connection_figure(result, "base:n1")
        roles = _roles(figure)
        self.assertEqual(roles.count("base_plate"), 1)
        self.assertEqual(roles.count("section_flange"), 2)
        self.assertEqual(roles.count("section_web"), 1)
        anchors = [
            trace
            for trace in _mesh_traces(figure)
            if (trace.meta or {}).get("role") == "anchor"
        ]
        self.assertEqual(len(anchors), 4)
        self.assertTrue(
            all((trace.meta or {}).get("shape") == "cylinder" for trace in anchors)
        )

    def test_eaves_topology_has_column_rafter_plate_bolts_and_cut_donor(self):
        result = _valid_eaves_result()
        figure = build_connection_figure(result, "haunch:eaves-haunch")
        meshes = _mesh_traces(figure)
        roles = _roles(figure)
        members = {(trace.meta or {}).get("member") for trace in meshes}
        self.assertIn("column", members)
        self.assertIn("rafter", members)
        self.assertEqual(roles.count("end_plate"), 1)
        self.assertEqual(roles.count("bolt"), 8)
        self.assertEqual(roles.count("haunch_web"), 1)
        self.assertEqual(roles.count("haunch_bottom_flange"), 1)
        self.assertNotIn("haunch_top_flange", roles)
        self.assertNotIn("haunch_solid", roles)

    def test_eaves_rafter_and_plate_are_flush_with_column_flange(self):
        result = _valid_eaves_result()
        figure = build_connection_figure(result, "haunch:eaves-haunch")
        plate = next(
            trace
            for trace in _mesh_traces(figure)
            if (trace.meta or {}).get("role") == "end_plate"
        )
        rafter = next(
            trace
            for trace in _mesh_traces(figure)
            if (trace.meta or {}).get("member") == "rafter"
            and (trace.meta or {}).get("role") == "section_web"
        )
        plate_thickness = float(
            result["haunch_connections"]["locations"][0]["connection"][
                "plate"
            ]["provided_thickness_mm"]
        )
        plate_spans = _trace_spans(plate)
        self.assertAlmostEqual(plate_spans[0], plate_thickness)
        self.assertAlmostEqual(
            min(float(value) for value in rafter.x),
            max(float(value) for value in plate.x),
        )
        column = [
            trace
            for trace in _mesh_traces(figure)
            if (trace.meta or {}).get("member") == "column"
        ]
        self.assertAlmostEqual(
            max(float(value) for trace in column for value in trace.x),
            min(float(value) for value in plate.x),
        )
        self.assertLess(_trace_centre(plate)[2], _trace_centre(rafter)[2])

    def test_eaves_column_projects_50_mm_above_end_plate(self):
        figure = build_connection_figure(
            _valid_eaves_result(),
            "haunch:eaves-haunch",
        )
        plate = next(
            trace
            for trace in _mesh_traces(figure)
            if (trace.meta or {}).get("role") == "end_plate"
        )
        column = [
            trace
            for trace in _mesh_traces(figure)
            if (trace.meta or {}).get("member") == "column"
        ]
        self.assertAlmostEqual(
            max(float(value) for trace in column for value in trace.z)
            - max(float(value) for value in plate.z),
            50.0,
        )

    def test_eaves_stiffeners_span_between_column_flanges(self):
        result = _valid_eaves_result()
        location = result["haunch_connections"]["locations"][0]
        location["connection"]["stiffeners"].update(
            {
                "required": True,
                "count": 2,
                "height_mm": 100.0,
                "length_mm": 100.0,
                "provided_thickness_mm": 10.0,
            }
        )
        figure = build_connection_figure(result, "haunch:eaves-haunch")
        stiffeners = [
            trace
            for trace in _mesh_traces(figure)
            if (trace.meta or {}).get("member") == "eaves"
            and (trace.meta or {}).get("role") == "stiffener"
        ]
        column = location["column_section"]
        from member_database import load_member_database

        section = next(
            family[column]
            for family in load_member_database().values()
            if column in family
        )
        expected_clear_depth = float(section["h"]) - 2.0 * float(
            section["tf"]
        )
        self.assertEqual(len(stiffeners), 2)
        for trace in stiffeners:
            self.assertTrue(
                (trace.meta or {}).get("spans_between_column_flanges")
            )
            self.assertAlmostEqual(_trace_spans(trace)[0], expected_clear_depth)
            self.assertAlmostEqual(_trace_spans(trace)[1], float(section["b"]))

    def test_apex_has_two_rafters_and_never_draws_a_column(self):
        result = _valid_apex_result()
        views = list_connection_views(result)
        self.assertEqual(views[-1]["key"], "haunch:apex-haunch")
        figure = build_connection_figure(result, "haunch:apex-haunch")
        mesh_meta = [trace.meta or {} for trace in _mesh_traces(figure)]
        members = {meta.get("member") for meta in mesh_meta}
        self.assertNotIn("column", members)
        self.assertIn("apex rafter 1", members)
        self.assertIn("apex rafter 2", members)
        self.assertEqual(
            sum(meta.get("role") == "haunch_web" for meta in mesh_meta),
            2,
        )

    def test_apex_stiffeners_follow_outer_bolt_rows_and_are_transverse(self):
        result = _valid_apex_result()
        location = result["haunch_connections"]["locations"][0]
        connection = location["connection"]
        figure = build_connection_figure(result, "haunch:apex-haunch")
        stiffeners = [
            trace
            for trace in _mesh_traces(figure)
            if (trace.meta or {}).get("role") == "stiffener"
        ]
        bolt_levels = [
            float(point["y"])
            for point in connection["bolts"][
                "coordinates_from_plate_centre_mm"
            ]
        ]
        expected_levels = [min(bolt_levels), max(bolt_levels)]
        self.assertEqual(len(stiffeners), 2)
        self.assertEqual(
            [round(_trace_centre(trace)[2], 6) for trace in stiffeners],
            [round(level, 6) for level in expected_levels],
        )
        for trace, expected_level in zip(stiffeners, expected_levels):
            meta = trace.meta or {}
            centre = _trace_centre(trace)
            spans = _trace_spans(trace)
            self.assertAlmostEqual(centre[0], 0.0)
            self.assertAlmostEqual(centre[1], 0.0)
            self.assertAlmostEqual(centre[2], expected_level)
            self.assertEqual(meta.get("orientation"), "transverse")
            self.assertEqual(
                meta.get("level_source"),
                "calculated_outer_bolt_rows",
            )
            self.assertAlmostEqual(
                spans[0],
                float(connection["stiffeners"]["length_mm"]),
            )
            self.assertAlmostEqual(
                spans[1],
                min(
                    float(connection["stiffeners"]["height_mm"]),
                    float(connection["plate"]["width_mm"]),
                ),
            )
            self.assertAlmostEqual(
                spans[2],
                float(
                    connection["stiffeners"]["provided_thickness_mm"]
                ),
            )
            self.assertLess(spans[2], spans[0])
            self.assertLess(spans[2], spans[1])
            self.assertLess(min(float(value) for value in trace.x), 0.0)
            self.assertGreater(max(float(value) for value in trace.x), 0.0)

    def test_apex_stiffeners_fall_back_to_actual_flange_centrelines(self):
        result = _valid_apex_result()
        location = result["haunch_connections"]["locations"][0]
        connection = location["connection"]
        connection["bolts"].pop("coordinates_from_plate_centre_mm")
        connection["bolts"]["row_count"] = 0
        connection["bolts"]["pitch_mm"] = 0.0
        rafter = location["source_rafter_geometry"]
        expected_levels = [
            (
                -float(rafter["h"]) / 2.0
                - float(location["added_depth_mm"])
                + float(rafter["tf"]) / 2.0
            ),
            (float(rafter["h"]) - float(rafter["tf"])) / 2.0,
        ]
        figure = build_connection_figure(result, "haunch:apex-haunch")
        stiffeners = [
            trace
            for trace in _mesh_traces(figure)
            if (trace.meta or {}).get("role") == "stiffener"
        ]
        self.assertEqual(
            [round(_trace_centre(trace)[2], 6) for trace in stiffeners],
            [round(level, 6) for level in expected_levels],
        )
        self.assertTrue(
            all(
                (trace.meta or {}).get("level_source")
                == "calculated_flange_centrelines"
                for trace in stiffeners
            )
        )

    def test_stiffeners_are_flat_rectangular_plates(self):
        result = _result()
        support = result["base_plates"]["supports"][0]
        support["stiffeners"] = {
            "required": True,
            "count": 4,
            "height_mm": 180.0,
            "length_mm": 120.0,
            "provided_thickness_mm": 10.0,
        }
        figure = build_connection_figure(result, "base:n1")
        stiffeners = [
            trace
            for trace in _mesh_traces(figure)
            if (trace.meta or {}).get("role") == "stiffener"
        ]
        self.assertEqual(len(stiffeners), 4)
        for trace in stiffeners:
            meta = trace.meta or {}
            self.assertEqual(meta.get("shape"), "flat_rectangular_plate")
            dimensions = sorted(float(value) for value in meta["dimensions_mm"])
            self.assertEqual(dimensions[0], 10.0)
            self.assertGreater(dimensions[1], dimensions[0])

    def test_valid_scene_has_no_text_or_annotations(self):
        figures = (
            build_connection_figure(
                _valid_eaves_result(),
                "haunch:eaves-haunch",
            ),
            build_connection_figure(
                _valid_apex_result(),
                "haunch:apex-haunch",
            ),
        )
        for figure in figures:
            self.assertFalse(tuple(figure.layout.scene.annotations or ()))
            self.assertFalse(tuple(figure.layout.annotations or ()))
            for trace in figure.data:
                self.assertNotIn("text", str(getattr(trace, "mode", "")))
                self.assertFalse(tuple(getattr(trace, "text", None) or ()))

    def test_figure_removes_export_buttons_and_uses_equal_orthographic_view(self):
        figure = build_connection_figure(_result(), "base:n1")
        removed = set(figure.layout.modebar.remove or ())
        self.assertTrue(set(MODEBAR_EXPORT_ITEMS).issubset(removed))
        self.assertEqual(figure.layout.scene.camera.projection.type, "orthographic")
        self.assertEqual(figure.layout.scene.aspectmode, "data")
        self.assertFalse(
            figure.layout.meta["connection_viewer"]["three_dimensional_export"]
        )

    def test_invalid_geometry_returns_clean_placeholder(self):
        figure = build_connection_figure(_result(), "haunch:eaves-haunch")
        self.assertEqual(len(figure.data), 0)
        self.assertTrue(figure.layout.meta["connection_viewer"]["placeholder"])
        self.assertFalse(tuple(figure.layout.scene.annotations or ()))

    def test_runtime_html_is_interactive_but_has_no_modebar_or_export(self):
        html = build_connection_viewer_html(_result(), "base:n1")
        self.assertIn("<html", html.casefold())
        self.assertIn("plotly", html.casefold())
        self.assertIn("Connection to inspect", html)
        self.assertIn('id="connection-view-select"', html)
        self.assertIn("next.searchParams.set('view',this.value)", html)
        self.assertIn("Base plate N1", html)
        self.assertIn("Base plate N7", html)
        self.assertIn('"displayModeBar": false', html)
        self.assertFalse(VIEWER_CONFIG["displayModeBar"])
        self.assertFalse(VIEWER_CONFIG["showLink"])

    def test_module_has_no_plotly_file_or_image_export_calls(self):
        import connection_viewer

        source = inspect.getsource(connection_viewer)
        for forbidden in (
            ".write_html(",
            ".write_image(",
            ".to_image(",
        ):
            self.assertNotIn(forbidden, source)

    def test_backend_viewer_allows_embedding_from_the_flet_web_origin(self):
        from backend import main as backend_main

        job = {
            "status": "complete",
            "design_summary": {
                "connection_design": _valid_eaves_result(),
            },
        }
        with patch.object(backend_main, "get_analysis_job", return_value=job):
            response = backend_main.connection_viewer(
                "0123456789ab",
                "base:n1",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["cross-origin-resource-policy"],
            "cross-origin",
        )
        self.assertEqual(
            response.headers["cross-origin-embedder-policy"],
            "require-corp",
        )
        self.assertEqual(response.headers["cache-control"], "no-store")


if __name__ == "__main__":
    unittest.main()
