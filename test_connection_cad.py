from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import ezdxf

import connection_cad as cad
from connection_design import design_portal_connections
from test_foundation_connections import _snapshot


def _connection_result(*, include_apex: bool = True) -> dict:
    snapshot = _snapshot()
    snapshot["results"]["project"]["column_section"] = "305x165x40"
    snapshot["input_data"]["frame_data"][0]["eaves_haunch_depth"] = 80.0
    if include_apex:
        snapshot["input_data"]["frame_data"][0].update(
            {
                "use_apex_haunch": "Yes",
                "apex_haunch_length": 1_000.0,
                "apex_haunch_depth": 80.0,
            }
        )
    return design_portal_connections(snapshot)


def _sheet_text(sheet: cad.ConnectionSheet) -> str:
    return "\n".join(
        primitive.value
        for primitive in sheet.primitives
        if isinstance(primitive, cad.Text)
    )


class CanonicalConnectionSheetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = _connection_result()

    def test_builds_base_eaves_and_true_rafter_to_rafter_apex_sheets(self):
        sheets = cad.build_connection_sheets(self.result)
        self.assertEqual(
            [sheet.sheet_id for sheet in sheets],
            ["BP-N1", "BP-N7", "HC-EAVES", "HC-APEX"],
        )
        self.assertEqual(len({sheet.layout_name for sheet in sheets}), len(sheets))
        apex = next(sheet for sheet in sheets if sheet.sheet_id == "HC-APEX")
        apex_text = _sheet_text(apex)
        self.assertIn("APEX RAFTER-TO-RAFTER BOLTED SPLICE", apex_text)
        self.assertNotIn("305x165x40", apex_text)
        self.assertIn("NO COLUMN OCCURS AT THE APEX", apex_text)
        eaves = next(sheet for sheet in sheets if sheet.sheet_id == "HC-EAVES")
        self.assertIn("COLUMN 305x165x40", _sheet_text(eaves))

    def test_no_utilisation_or_design_status_and_collision_validation_passes(self):
        sheets = cad.build_connection_sheets(self.result)
        for sheet in sheets:
            text = _sheet_text(sheet).casefold()
            self.assertNotIn("utilisation", text)
            self.assertNotIn("design status", text)
            self.assertNotRegex(text, r"\bu\s*=")
            sheet.validate_collisions()

    def test_dimensions_are_taken_from_calculated_geometry(self):
        sheets = cad.build_connection_sheets(self.result)
        base = next(sheet for sheet in sheets if sheet.sheet_id == "BP-N1")
        support = self.result["base_plates"]["supports"][0]
        layout = support["holding_down_bolts"]["layout"]
        base_values = {
            primitive.value
            for primitive in base.primitives
            if isinstance(primitive, cad.Text) and primitive.layer == "DIMS"
        }
        for value in (
            support["plate"]["length_mm"],
            support["plate"]["width_mm"],
            layout["pitch_mm"],
            layout["gauge_mm"],
            layout["end_distance_mm"],
            layout["edge_distance_mm"],
        ):
            self.assertIn(cad._fmt(float(value)), base_values)

        eaves = next(sheet for sheet in sheets if sheet.sheet_id == "HC-EAVES")
        location = self.result["haunch_connections"]["locations"][0]
        bolts = location["connection"]["bolts"]
        eaves_values = {
            primitive.value
            for primitive in eaves.primitives
            if isinstance(primitive, cad.Text) and primitive.layer == "DIMS"
        }
        self.assertIn(cad._fmt(float(bolts["gauge_mm"])), eaves_values)
        self.assertIn(cad._fmt(float(bolts["edge_distance_mm"])), eaves_values)
        self.assertIn(
            f"{int(bolts['row_count']) - 1} @ {cad._fmt(float(bolts['pitch_mm']))}",
            eaves_values,
        )

    def test_haunch_donor_has_removed_top_flange_and_retained_bottom_flange(self):
        eaves = next(
            sheet
            for sheet in cad.build_connection_sheets(self.result)
            if sheet.sheet_id == "HC-EAVES"
        )
        text = _sheet_text(eaves)
        self.assertIn("TOP FLANGE REMOVED", text)
        self.assertIn("RETAINED BOTTOM FLANGE", text)
        self.assertTrue(
            any(
                isinstance(primitive, cad.Line)
                and primitive.layer == "WELDS"
                for primitive in eaves.primitives
            )
        )

    def test_required_base_stiffener_is_a_separate_flat_rectangle(self):
        result = deepcopy(self.result)
        result["base_plates"]["supports"][0]["stiffeners"] = {
            "required": True,
            "count": 4,
            "height_mm": 180.0,
            "length_mm": 120.0,
            "provided_thickness_mm": 10.0,
        }
        base = cad.build_connection_sheets(result)[0]
        detail = base.zones["detail"]
        detail_polygons = [
            primitive
            for primitive in base.primitives
            if isinstance(primitive, cad.Polyline)
            and primitive.closed
            and all(
                detail.contains(cad.Rect(x, y, 0, 0), tolerance=0.1)
                for x, y in primitive.points
            )
        ]
        self.assertTrue(detail_polygons)
        self.assertTrue(all(len(item.points) == 4 for item in detail_polygons))
        self.assertIn("FLAT RECTANGULAR PLATE", _sheet_text(base))

    def test_eaves_stiffener_detail_uses_calculated_plate_geometry(self):
        result = deepcopy(self.result)
        stiffener = result["haunch_connections"]["locations"][0]["connection"][
            "stiffeners"
        ]
        stiffener.update(
            {
                "count": 3,
                "height_mm": 140.0,
                "length_mm": 80.0,
                "provided_thickness_mm": 12.0,
                "position": "Outer calculated bolt rows",
            }
        )
        eaves = next(
            sheet
            for sheet in cad.build_connection_sheets(result)
            if sheet.sheet_id == "HC-EAVES"
        )
        notes = eaves.zones["notes"]
        detail_polygons = [
            primitive
            for primitive in eaves.primitives
            if isinstance(primitive, cad.Polyline)
            and primitive.closed
            and min(x for x, _ in primitive.points) > notes.x + 100.0
            and all(
                notes.contains(cad.Rect(x, y, 0.0, 0.0), tolerance=0.1)
                for x, y in primitive.points
            )
        ]
        self.assertEqual(len(detail_polygons), 1)
        plate = detail_polygons[0]
        drawn_width = max(x for x, _ in plate.points) - min(
            x for x, _ in plate.points
        )
        drawn_height = max(y for _, y in plate.points) - min(
            y for _, y in plate.points
        )
        self.assertAlmostEqual(drawn_width / drawn_height, 80.0 / 140.0)
        dimension_values = {
            primitive.value
            for primitive in eaves.primitives
            if isinstance(primitive, cad.Text)
            and primitive.layer == "DIMS"
            and primitive.allowed_zone == "notes"
        }
        self.assertEqual(dimension_values, {"80", "140"})
        text = _sheet_text(eaves)
        self.assertIn("3-PL12", text)
        self.assertIn("140 HIGH x 80 LONG", text)
        self.assertIn("POSITION: OUTER CALCULATED BOLT ROWS", text)

    def test_apex_stiffener_has_calculated_flat_plate_geometry_and_dimensions(self):
        result = deepcopy(self.result)
        apex_location = next(
            location
            for location in result["haunch_connections"]["locations"]
            if location["connection_type"] == "apex_splice"
        )
        apex_location["connection"]["stiffeners"].update(
            {
                "count": 2,
                "height_mm": 90.0,
                "length_mm": 130.0,
                "provided_thickness_mm": 8.0,
                "position": "Outer calculated bolt rows",
            }
        )
        apex = next(
            sheet
            for sheet in cad.build_connection_sheets(result)
            if sheet.sheet_id == "HC-APEX"
        )
        notes = apex.zones["notes"]
        detail_polygons = [
            primitive
            for primitive in apex.primitives
            if isinstance(primitive, cad.Polyline)
            and primitive.closed
            and min(x for x, _ in primitive.points) > notes.x + 100.0
            and all(
                notes.contains(cad.Rect(x, y, 0.0, 0.0), tolerance=0.1)
                for x, y in primitive.points
            )
        ]
        self.assertEqual(len(detail_polygons), 1)
        plate = detail_polygons[0]
        drawn_width = max(x for x, _ in plate.points) - min(
            x for x, _ in plate.points
        )
        drawn_height = max(y for _, y in plate.points) - min(
            y for _, y in plate.points
        )
        self.assertAlmostEqual(drawn_width / drawn_height, 130.0 / 90.0)
        dimension_values = {
            primitive.value
            for primitive in apex.primitives
            if isinstance(primitive, cad.Text)
            and primitive.layer == "DIMS"
            and primitive.allowed_zone == "notes"
        }
        self.assertEqual(dimension_values, {"90", "130"})
        text = _sheet_text(apex)
        self.assertIn("2-PL8", text)
        self.assertIn("90 HIGH x 130 LONG", text)
        self.assertIn("POSITION: OUTER CALCULATED BOLT ROWS", text)

    def test_invalid_bolt_geometry_returns_clear_validation_error(self):
        result = deepcopy(self.result)
        del result["base_plates"]["supports"][0]["holding_down_bolts"]["layout"][
            "coordinates_from_plate_centre_mm"
        ]
        with self.assertRaisesRegex(
            cad.ConnectionDrawingError,
            "explicit bolt-centre coordinates",
        ):
            cad.build_connection_sheets(result)

    def test_collision_validator_is_deterministic(self):
        sheet = cad.ConnectionSheet(
            sheet_id="TEST",
            layout_name="TEST",
            title="Test",
            subtitle="Test",
            zones={"notes": cad.Rect(10, 10, 100, 100)},
        )
        sheet.add(
            cad.Text(20, 20, "FIRST", allowed_zone="notes"),
            cad.Text(20, 20, "SECOND", allowed_zone="notes"),
        )
        with self.assertRaisesRegex(
            cad.ConnectionDrawingError,
            "overlapping text boxes",
        ):
            sheet.validate_collisions()


class ConnectionExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = _connection_result()

    def test_pdf_is_vector_a3_multipage_from_the_same_sheets(self):
        sheets = cad.build_connection_sheets(self.result)
        with TemporaryDirectory() as directory:
            path = cad.write_connection_pdf(
                self.result,
                Path(directory) / "connections.pdf",
            )
            payload = path.read_bytes()
            self.assertTrue(payload.startswith(b"%PDF-"))
            page_count = len(re.findall(rb"/Type\s*/Page\b", payload))
            self.assertEqual(page_count, len(sheets))
            self.assertGreater(path.stat().st_size, 10_000)

    def test_r2018_dxf_has_mm_units_layers_and_one_layout_per_connection(self):
        sheets = cad.build_connection_sheets(self.result)
        with TemporaryDirectory() as directory:
            path = cad.write_connection_dxf(
                self.result,
                Path(directory) / "connections.dxf",
            )
            document = ezdxf.readfile(path)
            self.assertEqual(document.dxfversion, "AC1032")
            self.assertEqual(document.header["$INSUNITS"], 4)
            layer_names = {layer.dxf.name for layer in document.layers}
            self.assertTrue(set(cad.DXF_LAYERS).issubset(layer_names))
            paper_layouts = [
                layout
                for layout in document.layouts
                if layout.name.casefold() != "model"
            ]
            self.assertEqual(
                [layout.name for layout in paper_layouts],
                [sheet.layout_name for sheet in sheets],
            )
            for layout in paper_layouts:
                entity_types = {entity.dxftype() for entity in layout}
                self.assertIn("LINE", entity_types)
                self.assertIn("LWPOLYLINE", entity_types)
                self.assertIn("TEXT", entity_types)
                self.assertIn("MTEXT", entity_types)
                self.assertIn("CIRCLE", entity_types)
            auditor = document.audit()
            self.assertFalse(auditor.errors)

    def test_dwg_converter_uses_fixed_executable_list_args_and_removes_script(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            converter = root / "accoreconsole.exe"
            converter.write_bytes(b"stub")
            source = root / "connections.dxf"
            source.write_text("non-empty dxf", encoding="ascii")
            target = root / "connections.dwg"
            calls: list[tuple[list[str], dict]] = []

            def fake_run(args, **kwargs):
                calls.append((args, kwargs))
                script = Path(args[args.index("/s") + 1])
                self.assertEqual(script.parent, target.parent)
                self.assertTrue(script.is_file())
                self.assertIn(str(target), script.read_text(encoding="utf-8"))
                (target.parent / "acad.err").write_text(
                    "AutoCAD diagnostic",
                    encoding="utf-8",
                )
                target.write_bytes(b"AC1032-DWG")
                return subprocess.CompletedProcess(args, 0, "", "")

            with (
                patch.object(cad, "DWG_CONVERTER", converter),
                patch.object(cad.subprocess, "run", side_effect=fake_run),
            ):
                written = cad.write_connection_dwg(source, target)
            self.assertEqual(written, target.resolve())
            self.assertEqual(len(calls), 1)
            args, kwargs = calls[0]
            self.assertIsInstance(args, list)
            self.assertEqual(args[0], str(converter))
            self.assertIs(kwargs["shell"], False)
            self.assertEqual(kwargs["timeout"], 180)
            self.assertEqual(kwargs["cwd"], str(target.parent))
            self.assertFalse(list(root.glob("portal_connection_*.scr")))
            self.assertFalse((root / "acad.err").exists())

    def test_dwg_converter_failure_text_is_short_and_has_no_nul_characters(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            converter = root / "accoreconsole.exe"
            converter.write_bytes(b"stub")
            source = root / "connections.dxf"
            source.write_text("non-empty dxf", encoding="ascii")
            target = root / "connections.dwg"
            console_error = "\x00FATAL ERROR:\x00 " + ("profile failure " * 80)

            with (
                patch.object(cad, "DWG_CONVERTER", converter),
                patch.object(
                    cad.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        [str(converter)],
                        1,
                        "",
                        console_error,
                    ),
                ),
                self.assertRaises(RuntimeError) as raised,
            ):
                cad.write_connection_dwg(source, target)

            message = str(raised.exception)
            self.assertNotIn("\x00", message)
            self.assertLess(len(message), 450)

    def test_dwg_does_not_silently_overwrite(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "connections.dxf"
            target = root / "connections.dwg"
            source.write_text("non-empty dxf", encoding="ascii")
            target.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                cad.write_connection_dwg(source, target)

    def test_converter_status_reports_only_the_fixed_path(self):
        status = cad.dwg_converter_status()
        self.assertEqual(status["path"], str(cad.DWG_CONVERTER))
        self.assertEqual(status["available"], cad.DWG_CONVERTER.is_file())


if __name__ == "__main__":
    unittest.main()
