import unittest

from audrey_llm.config import render_mode_menu, resolve_backend_choice


class BackendSelectionTests(unittest.TestCase):
    def test_blank_input_defaults_to_deepseek(self):
        self.assertEqual(resolve_backend_choice(""), "deepseek")

    def test_local_choice_is_accepted(self):
        self.assertEqual(resolve_backend_choice("2"), "local")

    def test_menu_mentions_both_modes(self):
        menu = render_mode_menu()
        self.assertIn("DeepSeek", menu)
        self.assertIn("Local", menu)


if __name__ == "__main__":
    unittest.main()
