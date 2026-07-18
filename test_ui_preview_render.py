import base64
import unittest

from preview_geometry import build_preview_geometry
from ui.input_model import DEFAULT_VALUES, build_analysis_payload
from ui.preview_render import frame_elevation_svg, roof_plan_svg, wall_elevation_svg


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

    def test_roof_renderer_contains_bracing(self):
        svg = self.decode(roof_plan_svg(self.preview))
        self.assertIn("Roof X-bracing in end bays", svg)
        self.assertIn("#C94B40", svg)

    def test_wall_renderer_contains_topology(self):
        svg = self.decode(wall_elevation_svg(self.preview))
        self.assertIn("X-bracing", svg)


if __name__ == "__main__":
    unittest.main()
