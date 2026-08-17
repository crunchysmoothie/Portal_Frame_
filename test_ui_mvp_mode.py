import unittest

from ui.main import mvp_phase_for_section


class MvpInterfaceModeTests(unittest.TestCase):
    def test_detailed_input_pages_share_the_inputs_phase(self) -> None:
        for section_index in range(5):
            self.assertEqual(mvp_phase_for_section(section_index), (1, "Inputs"))

    def test_engineering_result_pages_follow_the_condensed_workflow(self) -> None:
        self.assertEqual(mvp_phase_for_section(5), (2, "Analysis"))
        self.assertEqual(mvp_phase_for_section(6), (3, "Connections"))
        self.assertEqual(mvp_phase_for_section(7), (4, "Foundations"))

    def test_both_output_pages_share_the_outputs_phase(self) -> None:
        self.assertEqual(mvp_phase_for_section(8), (5, "Outputs"))
        self.assertEqual(mvp_phase_for_section(9), (5, "Outputs"))

    def test_unknown_section_defaults_safely_to_inputs(self) -> None:
        self.assertEqual(mvp_phase_for_section(99), (1, "Inputs"))


if __name__ == "__main__":
    unittest.main()
