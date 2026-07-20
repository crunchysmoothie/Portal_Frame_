import unittest

from fastapi.testclient import TestClient

from backend.main import app
from preview_geometry import build_preview_geometry
from ui.input_model import DEFAULT_VALUES, build_analysis_payload


class PreviewGeometryTests(unittest.TestCase):
    def payload(self, **updates):
        values = dict(DEFAULT_VALUES)
        values.update(updates)
        return build_analysis_payload(values)

    def test_default_preview_uses_shared_roof_layout(self):
        preview = build_preview_geometry(self.payload())

        self.assertEqual(preview["status"], "layout_preview_only")
        self.assertEqual(preview["units"], "mm")
        self.assertEqual(preview["counts"]["bays"], 8)
        self.assertEqual(preview["counts"]["frame_lines"], 9)
        self.assertEqual(preview["counts"]["purlin_lines"], 13)
        self.assertEqual(preview["roof_layout"]["brace_panels_per_slope"], 2)
        self.assertLessEqual(
            preview["roof_layout"]["actual_purlin_spacing_mm"], 1600
        )

    def test_preview_contains_both_end_roof_bracing_bays(self):
        preview = build_preview_geometry(self.payload())
        braces = preview["roof_plan"]["braces"]

        self.assertEqual(len(braces), 16)
        self.assertTrue(any(item["id"].startswith("RB1-") for item in braces))
        self.assertTrue(any(item["id"].startswith("RB2-") for item in braces))

    def test_four_roof_panels_are_drawn_as_four_per_slope(self):
        preview = build_preview_geometry(
            self.payload(rafter_bracing_spacing="4")
        )

        self.assertEqual(preview["roof_layout"]["brace_panels_per_slope"], 4)
        self.assertEqual(len(preview["roof_plan"]["braces"]), 32)

    def test_canopy_omits_gable_columns(self):
        preview = build_preview_geometry(self.payload(building_type="Canopy"))

        self.assertEqual(preview["counts"]["gable_columns_per_end"], 0)
        self.assertEqual(preview["frame_elevation"]["gable_columns"], [])

    def test_mono_pitch_preview_has_one_rafter(self):
        preview = build_preview_geometry(self.payload(building_roof="Mono Pitched"))
        rafters = [
            member
            for member in preview["frame_elevation"]["members"]
            if member["kind"] == "rafter"
        ]

        self.assertEqual(len(rafters), 1)
        self.assertEqual(preview["counts"]["purlin_lines"], 12)

    def test_preview_contains_crawl_markers_on_the_selected_slope(self):
        preview = build_preview_geometry(
            self.payload(
                use_crawl_beams=True,
                crawl_beams=[
                    {
                        "name": "CB1",
                        "slope": "right",
                        "position_from_eaves_mm": "6000",
                        "section_type": "I-Sections",
                        "section": "IPE-AA100",
                        "swl_kg": "5000",
                        "hoist_trolley_mass_kg": "350",
                        "lifting_attachment_mass_kg": "100",
                        "hoist_class": "C2",
                        "hoisting_speed_m_s": "0.15",
                    }
                ],
            )
        )

        marker = preview["frame_elevation"]["crawl_beams"][0]
        self.assertEqual(marker["name"], "CB1")
        self.assertEqual(marker["slope"], "right")
        self.assertGreater(marker["point"]["x_mm"], 8000)
        self.assertGreater(marker["point"]["y_mm"], 6500)

    def test_preview_rejects_accidentally_oversized_geometry(self):
        with self.assertRaisesRegex(ValueError, "too many purlin spaces"):
            build_preview_geometry(self.payload(gable_width_m="2000"))

    def test_preview_endpoint_returns_renderer_contract(self):
        response = TestClient(app).post("/api/preview", json=self.payload())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["counts"]["frame_lines"], 9)


if __name__ == "__main__":
    unittest.main()
