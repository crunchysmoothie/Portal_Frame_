import unittest

import user_input


class SupportConditionTests(unittest.TestCase):
    def setUp(self):
        self.nodes = [{"name": "N1"}, {"name": "N2"}, {"name": "N3"}]

    def test_custom_spring_stiffness_is_converted_to_model_units(self):
        supports, springs = user_input.generate_base_supports(
            self.nodes, "Spring", 25_000
        )
        self.assertTrue(all(not support["RZ"] for support in supports))
        self.assertEqual([spring["stiffness"] for spring in springs], [25e6, 25e6])

    def test_fixed_support_restrains_rotation_without_spring(self):
        supports, springs = user_input.generate_base_supports(self.nodes, "Fixed")
        self.assertTrue(all(support["RZ"] for support in supports))
        self.assertEqual(springs, [])

    def test_pinned_support_releases_rotation_without_spring(self):
        supports, springs = user_input.generate_base_supports(self.nodes, "Pinned")
        self.assertTrue(all(not support["RZ"] for support in supports))
        self.assertEqual(springs, [])

    def test_rejects_invalid_condition_and_nonpositive_spring(self):
        with self.assertRaisesRegex(ValueError, "Pinned"):
            user_input.generate_base_supports(self.nodes, "Rigid")
        with self.assertRaisesRegex(ValueError, "positive"):
            user_input.generate_base_supports(self.nodes, "Spring", 0)


if __name__ == "__main__":
    unittest.main()
