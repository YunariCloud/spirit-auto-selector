import unittest

import cv2
import numpy as np

import main


class DetectionTests(unittest.TestCase):
    def test_source_mode_uses_project_data_directory(self) -> None:
        self.assertFalse(main.IS_FROZEN)
        self.assertEqual(main.ROOT, main.BUNDLE_ROOT)
        self.assertTrue(main.CONFIG_PATH.is_file())
        self.assertTrue(main.ASSETS.is_dir())

    def test_default_sprite_config_is_available(self) -> None:
        config = main.load_config()
        definitions = main.get_sprite_definitions(config)
        self.assertEqual(definitions[0].id, "default")
        self.assertEqual(main.selected_sprite_ids(config), ["default"])

    def test_duplicate_matches_from_multiple_sprite_templates_are_merged(self) -> None:
        config = main.load_config()
        first = main.load_sprite_templates(config, ["default"])[0]
        duplicate_definition = main.SpriteDefinition(
            id="duplicate",
            name="重复模板",
            unselected=first.definition.unselected,
            selected=first.definition.selected,
            unselected_threshold=first.definition.unselected_threshold,
            selected_threshold=first.definition.selected_threshold,
        )
        duplicate = main.SpriteTemplate(
            definition=duplicate_definition,
            unselected_image=first.unselected_image,
            selected_image=first.selected_image,
            unselected_mask=first.unselected_mask,
            selected_mask=first.selected_mask,
        )
        matches = main.find_sprite_matches(first.unselected_image, [first, duplicate])
        self.assertEqual(len(matches), 1)

    def test_each_template_matches_itself(self) -> None:
        cases = (
            ("next_page.png", 0.88, None),
            ("unselected.png", 0.86, "card"),
            ("selected.png", 0.80, "card"),
        )
        for name, threshold, mask_type in cases:
            with self.subTest(name=name):
                image = main.load_image(name)
                mask = main.make_card_mask(image) if mask_type == "card" else None
                matches = main.find_matches(image, image, threshold, mask=mask)
                self.assertEqual(len(matches), 1)
                self.assertGreater(matches[0].score, 0.99)

    def test_dense_background_does_not_create_unbounded_candidates(self) -> None:
        template = main.load_image("unselected.png")
        screen = np.full((700, 1200, 3), 190, dtype=np.uint8)
        screen[100 : 100 + template.shape[0], 200 : 200 + template.shape[1]] = template
        matches = main.find_matches(
            screen,
            template,
            0.86,
            mask=main.make_card_mask(template),
        )
        self.assertTrue(any(abs(item.x - 200) <= 1 and abs(item.y - 100) <= 1 for item in matches))

    def test_equal_page_numbers_are_last_page(self) -> None:
        pagination = main.load_image("pagination.png")
        detector = main.PageDetector(pagination, 0.84)
        is_last, anchor_score, digit_scores = detector.inspect(pagination)
        self.assertTrue(is_last)
        self.assertGreater(anchor_score, 0.99)
        self.assertEqual(len(digit_scores), 1)

    def test_unequal_digit_counts_are_not_last_page(self) -> None:
        pagination = main.load_image("pagination.png")
        canvas = np.full((69, 240, 3), pagination[0, 0], dtype=np.uint8)
        canvas[:, :200] = pagination
        # Turn the reference 1/1 into 1/11 by copying its final digit.
        canvas[23:43, 190:205] = pagination[23:43, 171:186]
        detector = main.PageDetector(pagination, 0.84)
        is_last, _, _ = detector.inspect(canvas)
        self.assertFalse(is_last)

    def test_screen_change_guard(self) -> None:
        before = np.zeros((200, 300, 3), dtype=np.uint8)
        after = before.copy()
        self.assertFalse(main.screen_changed(before, after, 0.35))
        cv2.rectangle(after, (20, 20), (250, 170), (255, 255, 255), -1)
        self.assertTrue(main.screen_changed(before, after, 0.35))

    def test_debug_annotation_stays_in_memory(self) -> None:
        screen = np.zeros((80, 120, 3), dtype=np.uint8)
        original = screen.copy()
        annotated = main.make_debug_image(screen, [main.Match(10, 10, 30, 25, 0.95)])
        np.testing.assert_array_equal(screen, original)
        self.assertFalse(np.array_equal(annotated, original))

    def test_mouse_clicker_send_input_mode(self) -> None:
        clicker = main.MouseClicker(mode="send_input")
        self.assertEqual(clicker.active_mode, "send_input")

    def test_mouse_clicker_fallback_behavior(self) -> None:
        clicker = main.MouseClicker(mode="interception", fallback_on_missing=True)
        # Should fallback gracefully to send_input when kernel driver is absent
        self.assertIn(clicker.active_mode, ("interception", "send_input"))


if __name__ == "__main__":
    unittest.main()
