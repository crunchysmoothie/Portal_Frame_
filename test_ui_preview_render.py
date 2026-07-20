import base64
import unittest

from preview_geometry import build_preview_geometry
from ui.input_model import DEFAULT_VALUES, build_analysis_payload
from ui.preview_render import (
    _uniform_axes,
    frame_elevation_svg,
    roof_plan_svg,
    wall_elevation_svg,
)


class UiPreviewRenderTests(unittest.TestCase):
    def setUp(self):
        self.preview = build_preview_geometry(
            build_analysis_payload(dict(DEFAULT_VALUES))
        )

    def decode(self, data_url):
        prefix, encoded = data_url.split(",", 1)
        self.assertEqual(prefix, "data:image/svg+xml;base64")
        return base64.b64decode(encoded).decode("utf-8")

    def test_frame_renderer_labels_preview(self):
        svg = self.decode(frame_elevation_svg(self.preview))
        self.assertIn("Portal frame section", svg)
        self.assertIn("13 purlin lines", svg)

    def test_frame_renderer_labels_crawl_marker(self):
        preview = build_preview_geometry(
            build_analysis_payload(
                {
                    **DEFAULT_VALUES,
                    "use_crawl_beams": True,
                    "crawl_beams": [{
                        "name": "CB1",
                        "slope": "left",
                        "position_from_eaves_mm": "6000",
                        "section_type": "I-Sections",
                        "section": "IPE-AA100",
                        "swl_kg": "5000",
                        "hoist_trolley_mass_kg": "350",
                        "lifting_attachment_mass_kg": "100",
                        "hoist_class": "C2",
                        "hoisting_speed_m_s": "0.15",
                    }],
                }
            )
        )
        svg = self.decode(frame_elevation_svg(preview))
        self.assertIn("CB1", svg)
        self.assertIn("crawl beam marker", svg)

    def test_roof_renderer_contains_bracing(self):
        svg = self.decode(roof_plan_svg(self.preview))
        self.assertIn("Roof X-bracing in end bays", svg)
        self.assertIn("#C94B40", svg)

    def test_wall_renderer_contains_topology(self):
        svg = self.decode(wall_elevation_svg(self.preview))
        self.assertIn("X-bracing", svg)

    def test_uniform_axes_do_not_exaggerate_eaves_height(self):
        x, y, fitted = _uniform_axes(
            48_000, 6_500, 55, 545, 45, 215, ground=True
        )
        horizontal_scale = (x(48_000) - x(0)) / 48_000
        vertical_scale = (y(0) - y(6_500)) / 6_500

        self.assertAlmostEqual(horizontal_scale, vertical_scale)
        self.assertLess(fitted[3] - fitted[2], 70)


if __name__ == "__main__":
    unittest.main()
