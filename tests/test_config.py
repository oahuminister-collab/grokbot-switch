import json
import tempfile
import unittest
from pathlib import Path

from grokbot_switch.config import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
    _sanitize,
    _coerce_widget_pos,
)

WEEKDAY_RULE = {
    "days": ["mon", "tue", "wed", "thu", "fri"],
    "start": "09:00",
    "end": "17:00",
    "state": "dnd",
}


class TestConfigDefaults(unittest.TestCase):
    def test_new_install_has_empty_schedule(self):
        self.assertEqual(DEFAULT_CONFIG["schedule"], [])
        self.assertFalse(DEFAULT_CONFIG["widget_minimized"])

    def test_load_missing_path_uses_new_defaults(self):
        missing = Path(tempfile.mkdtemp()) / "no-such-config.json"
        loaded = load_config(missing)
        self.assertEqual(loaded["schedule"], [])
        self.assertFalse(loaded["widget_minimized"])

    def test_existing_weekday_rule_is_kept(self):
        data = {
            "schedule": [WEEKDAY_RULE],
            "auto_dnd_when_active": True,
        }
        loaded = _sanitize(data)
        self.assertEqual(len(loaded["schedule"]), 1)
        self.assertEqual(loaded["schedule"][0]["start"], "09:00")
        self.assertEqual(loaded["schedule"][0]["state"], "dnd")

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            from_file = load_config(path)
            self.assertEqual(len(from_file["schedule"]), 1)
            self.assertEqual(from_file["schedule"][0]["end"], "17:00")

    def test_widget_minimized_and_position_round_trip(self):
        data = {
            "schedule": [],
            "widget_minimized": True,
            "widget_position": {"x": 40, "y": 80},
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            loaded = load_config(path)
            self.assertTrue(loaded["widget_minimized"])
            self.assertEqual(loaded["widget_position"], {"x": 40, "y": 80})
            save_config(path, loaded)
            again = load_config(path)
            self.assertTrue(again["widget_minimized"])
            self.assertEqual(again["widget_position"], {"x": 40, "y": 80})

    def test_coerce_widget_pos(self):
        self.assertEqual(_coerce_widget_pos({"x": 10, "y": 20}), {"x": 10, "y": 20})
        self.assertEqual(_coerce_widget_pos([10, 20]), {"x": 10, "y": 20})
        self.assertEqual(_coerce_widget_pos((10, 20)), {"x": 10, "y": 20})
        self.assertIsNone(_coerce_widget_pos(None))
        self.assertIsNone(_coerce_widget_pos({"x": "nope"}))
        self.assertIsNone(_coerce_widget_pos([1]))

    def test_sanitize_empty_uses_new_defaults(self):
        for raw in ({}, None, "bad"):
            cfg = _sanitize(raw)
            self.assertEqual(cfg["schedule"], [])
            self.assertFalse(cfg["widget_minimized"])


if __name__ == "__main__":
    unittest.main()
