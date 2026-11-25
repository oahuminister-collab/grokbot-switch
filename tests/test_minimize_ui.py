import unittest

from grokbot_switch.minimize_ui import (
    MINI_SIZE,
    tooltip_text,
    in_box,
    pill_anchor,
    pill_from_dot,
)


class TestMinimizeUi(unittest.TestCase):
    def test_tooltip_text(self):
        self.assertEqual(tooltip_text("available"), "Available · click to open")
        self.assertEqual(tooltip_text("dnd"), "Do Not Disturb · click to open")
        self.assertEqual(tooltip_text(""), "Available · click to open")

    def test_in_box(self):
        box = (10, 10, 20, 20)
        self.assertTrue(in_box(10, 10, box))
        self.assertTrue(in_box(15, 15, box))
        self.assertTrue(in_box(20, 20, box))
        self.assertFalse(in_box(9, 15, box))
        self.assertFalse(in_box(15, 21, box))
        self.assertFalse(in_box(15, 15, None))

    def test_anchor_round_trip(self):
        pill = (100, 200, 248, 52)
        dot = pill_anchor(*pill)
        self.assertEqual(dot, (100 + 248 - MINI_SIZE, 200 + 52 - MINI_SIZE))
        back = pill_from_dot(*dot, 248, 52)
        self.assertEqual(back, (100, 200))
        # Inverse also holds after a move
        moved = (dot[0] + 40, dot[1] - 10)
        self.assertEqual(pill_anchor(*pill_from_dot(*moved, 248, 52), 248, 52), moved)


if __name__ == "__main__":
    unittest.main()
