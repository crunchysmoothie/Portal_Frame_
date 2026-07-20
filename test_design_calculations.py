import json
from pathlib import Path
import tempfile
import unittest

from matplotlib.mathtext import MathTextParser

import member_database as mdb
from analysis_snapshot import (
    StaleAnalysisError,
    create_analysis_snapshot,
    load_analysis_snapshot,
    validate_snapshot_input,
    write_analysis_snapshot,
)
from design_calculations import (
    CalculationSheetData,
    ReactionResult,
    ReportScope,
    calculate_member_design,
    _deflection_ratio,
    load_calculation_sheet_data,
)
from strength_checks import (
    element_property_details,
    member_class_check,
    member_class_details,
    member_design,
    section_properties,
)


class DesignCalculationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database = mdb.load_member_database()
        cls.section = mdb.member_properties("I-Sections", "457x191x74", database)
        cls.material = {"fy": 355.0, "E": 200.0, "G": 77.0, "nu": 0.3, "rho": 7.85e-8}

    def actions(self, axial_force):
        return {
            "Name": "M1",
            "kly": 3.5,
            "klx": 8.4,
            "type": "column",
            "section": "457x191x74",
            "Cu": axial_force,
            "Class": member_class_check(axial_force, self.section, [self.material]),
            "Mx_max": 19.68,
            "Mx_top": -7.021,
            "Mx_bot": 19.68,
            "w1": 1.0,
            "w2": 2.1628,
        }

    def test_deflection_ratio_uses_reference_length(self):
        self.assertAlmostEqual(_deflection_ratio(16_000, 116.19), 137.7055, places=3)
        self.assertIsNone(_deflection_ratio(16_000, 0))

    def test_gross_section_tension_resistance(self):
        actions = self.actions(-30.571)
        properties = section_properties(self.section, actions, self.material)
        self.assertAlmostEqual(properties["Tr"], 0.9 * self.section["A"] * self.material["fy"])

    def test_tension_is_additive_in_governing_interaction(self):
        actions = self.actions(-30.571)
        properties = section_properties(self.section, actions, self.material)
        cross_section, _, ltb = member_design(self.section, actions, self.material)
        pure_bending = abs(actions["Mx_max"]) / properties["Mrx"]
        expected = abs(actions["Cu"]) / properties["Tr"] + pure_bending

        self.assertAlmostEqual(cross_section, expected)
        self.assertGreater(cross_section, pure_bending)
        self.assertGreaterEqual(ltb[0], 0.0)

    def test_report_derives_resistances_before_utilisation(self):
        report = calculate_member_design(
            self.section, self.actions(-30.571), self.material, "TEST",
        )
        self.assertEqual(report.axial_action, "Tension")
        self.assertIn("R-00", {item.reference for item in report.resistances})
        self.assertIn("T-01", {item.reference for item in report.calculations})
        self.assertTrue(all(item.result >= 0.0 for item in report.calculations))

    def test_compression_report_calculates_u1x_and_uses_ltb_resistance(self):
        actions = self.actions(30.571)
        properties = section_properties(self.section, actions, self.material)
        report = calculate_member_design(self.section, actions, self.material, "TEST")
        resistance_by_ref = {item.reference: item for item in report.resistances}
        check_by_ref = {item.reference: item for item in report.calculations}

        self.assertEqual(report.axial_action, "Compression")
        self.assertIn("R-09", resistance_by_ref)
        expected_u1x = actions["w1"] / (1.0 - actions["Cu"] / properties["Cex"])
        self.assertAlmostEqual(resistance_by_ref["R-09"].result, expected_u1x)
        self.assertAlmostEqual(
            check_by_ref["C-04"].result,
            abs(actions["Mx_max"]) / properties["Mrx_ltb"],
        )

    def test_section_class_is_fully_reproducible(self):
        actions = self.actions(-30.571)
        details = member_class_details(actions["Cu"], self.section, self.material)
        report = calculate_member_design(self.section, actions, self.material, "TEST")
        classification_by_ref = {item.reference: item for item in report.classification}

        self.assertEqual(details["compression_ratio"], 0.0)
        self.assertEqual(details["class"], actions["Class"])
        self.assertEqual(classification_by_ref["CL-06"].result, actions["Class"])

    def test_effective_length_and_moment_factors_are_reported(self):
        actions = self.actions(30.571)
        actions.update({"kx": 1.2, "lx": 7.0, "klx": 8.4, "ky": 1.0, "ly": 3.5})
        report = calculate_member_design(self.section, actions, self.material, "TEST")
        parameters = {item.reference: item for item in report.parameters}
        expected_factors = element_property_details(
            actions["Mx_max"], actions["Mx_top"], actions["Mx_bot"],
        )

        self.assertAlmostEqual(parameters["P-01"].result, 1.2)
        self.assertAlmostEqual(parameters["P-02"].result, 8.4)
        self.assertAlmostEqual(parameters["P-05"].result, expected_factors["kappa"])
        self.assertAlmostEqual(parameters["P-06"].result, expected_factors["omega1"])
        self.assertAlmostEqual(parameters["P-07"].result, expected_factors["omega2"])

    def test_report_equations_are_valid_mathtext(self):
        parser = MathTextParser("agg")
        reports = (
            calculate_member_design(
                self.section, self.actions(-30.571), self.material, "TENSION",
            ),
            calculate_member_design(
                self.section, self.actions(30.571), self.material, "COMPRESSION",
            ),
        )

        for report in reports:
            for group in (
                report.inputs,
                report.classification,
                report.parameters,
                report.resistances,
                report.calculations,
            ):
                for item in group:
                    if item.latex:
                        with self.subTest(reference=item.reference, latex=item.latex):
                            parser.parse(f"${item.latex}$")

    def test_analysis_snapshot_round_trip_feeds_report_without_analysis(self):
        member = calculate_member_design(
            self.section, self.actions(30.571), self.material, "TEST",
        )
        complete = CalculationSheetData(
            title="Test calculation sheet",
            scope=ReportScope.FULL,
            project={"input_file": "input.json"},
            frame_summary={"governing_member": "M1"},
            members=[member],
            reactions=[ReactionResult("N1", "TEST", 1, 2, 0, 0, 0, 3)],
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            input_path.write_text(json.dumps({"layout": "A"}), encoding="utf-8")
            snapshot = create_analysis_snapshot(input_path, complete.to_dict())
            snapshot_path = write_analysis_snapshot(
                snapshot, root / "analysis_results.json"
            )

            loaded_snapshot = load_analysis_snapshot(snapshot_path)
            report = load_calculation_sheet_data(
                snapshot_path, scope=ReportScope.FULL
            )

        self.assertEqual(loaded_snapshot["input_data"], {"layout": "A"})
        self.assertEqual(len(report.members), 1)
        self.assertEqual(report.members[0].member, "M1")
        self.assertEqual(report.reactions[0].mz, 3)
        self.assertEqual(
            report.project["input_sha256"],
            loaded_snapshot["analysis"]["input_sha256"],
        )

    def test_changed_input_rejects_stale_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.json"
            input_path.write_text('{"layout":"A"}', encoding="utf-8")
            snapshot = create_analysis_snapshot(
                input_path,
                CalculationSheetData(
                    title="Test", scope=ReportScope.FULL
                ).to_dict(),
            )
            input_path.write_text('{"layout":"B"}', encoding="utf-8")

            with self.assertRaises(StaleAnalysisError):
                validate_snapshot_input(snapshot)
            self.assertEqual(
                validate_snapshot_input(snapshot, allow_stale=True),
                "stale-allowed",
            )


if __name__ == "__main__":
    unittest.main()
