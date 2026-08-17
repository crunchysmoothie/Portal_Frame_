from __future__ import annotations

import unittest

from ui.input_model import InputValidationError, build_civil_boq_inputs


class CivilBoqInputTests(unittest.TestCase):
    def test_surface_bed_and_excavation_quantities(self) -> None:
        values = build_civil_boq_inputs({
            "civil_surface_bed_area_m2": "1200",
            "civil_surface_bed_thickness_mm": "150",
            "civil_joint_spacing_m": "6",
            "civil_excavation_below_surface_bed_m": "0.3",
            "civil_concrete_footing_backfill_m3": "25",
        })
        self.assertAlmostEqual(values["surface_bed_concrete_m3"], 180.0)
        self.assertAlmostEqual(values["surface_bed_joint_length_m"], 400.0)
        self.assertAlmostEqual(values["excavation_volume_m3"], 360.0)

    def test_joint_spacing_must_be_positive(self) -> None:
        with self.assertRaises(InputValidationError):
            build_civil_boq_inputs({
                "civil_surface_bed_area_m2": "1200",
                "civil_surface_bed_thickness_mm": "150",
                "civil_joint_spacing_m": "0",
                "civil_excavation_below_surface_bed_m": "0.3",
                "civil_concrete_footing_backfill_m3": "25",
            })


if __name__ == "__main__":
    unittest.main()
