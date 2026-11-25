import unittest

from grokbot_switch.schedule_edit import (
    format_days,
    format_time_12h,
    format_time_range,
    format_rule_line,
    add_schedule_rule,
    remove_schedule_rule,
    parse_time_input,
)


WEEKDAY_RULE = {
    "days": ["mon", "tue", "wed", "thu", "fri"],
    "start": "09:00",
    "end": "17:00",
    "state": "dnd",
}
SAT_RULE = {
    "days": ["sat"],
    "start": "08:00",
    "end": "12:00",
    "state": "available",
}


class TestScheduleEdit(unittest.TestCase):
    def _config(self, *rules):
        return {"schedule": [dict(r) for r in rules], "idle_minutes": 30}

    def test_format_days(self):
        self.assertEqual(format_days(["mon", "tue", "wed", "thu", "fri"]), "Weekdays")
        self.assertEqual(format_days(["sat", "sun"]), "Weekends")
        self.assertEqual(format_days(["mon", "tue", "wed", "thu", "fri", "sat", "sun"]), "Every day")
        self.assertEqual(format_days(["mon", "wed", "fri"]), "Mon, Wed, Fri")
        self.assertEqual(format_days(["mon", "tue"]), "Mon–Tue")
        self.assertEqual(format_days([]), "No days")

    def test_format_time(self):
        self.assertEqual(format_time_12h("09:00"), "9:00 AM")
        self.assertEqual(format_time_12h("17:00"), "5:00 PM")
        self.assertEqual(format_time_12h("00:00"), "12:00 AM")
        self.assertEqual(format_time_12h("12:00"), "12:00 PM")
        self.assertEqual(format_time_12h("13:30"), "1:30 PM")
        self.assertEqual(format_time_range("09:00", "17:00"), "9:00 AM – 5:00 PM")
        self.assertEqual(parse_time_input("9:00 AM"), "09:00")
        self.assertEqual(parse_time_input("5:00pm"), "17:00")
        self.assertEqual(parse_time_input("09:00"), "09:00")
        self.assertEqual(parse_time_input("12:00 PM"), "12:00")
        self.assertEqual(parse_time_input("12:00 AM"), "00:00")
        self.assertIsNone(parse_time_input("nope"))

    def test_format_rule_line(self):
        self.assertEqual(
            format_rule_line(WEEKDAY_RULE),
            "Weekdays, 9:00 AM – 5:00 PM · Do Not Disturb",
        )
        self.assertEqual(
            format_rule_line(SAT_RULE),
            "Sat, 8:00 AM – 12:00 PM · Available",
        )

    def test_add_valid_rule_does_not_mutate_original(self):
        cfg = self._config(WEEKDAY_RULE)
        original_list = cfg["schedule"]
        out = add_schedule_rule(cfg, SAT_RULE)
        self.assertEqual(len(out["schedule"]), 2)
        self.assertEqual(out["schedule"][1], {
            "days": ["sat"], "start": "08:00", "end": "12:00", "state": "available",
        })
        self.assertEqual(len(original_list), 1)
        self.assertIsNot(out["schedule"], original_list)
        self.assertEqual(cfg["schedule"], [WEEKDAY_RULE])

    def test_add_rejects_invalid(self):
        cfg = self._config(WEEKDAY_RULE)
        with self.assertRaisesRegex(ValueError, "no days"):
            add_schedule_rule(cfg, {"days": [], "start": "09:00", "end": "17:00", "state": "dnd"})
        with self.assertRaisesRegex(ValueError, "end not after start"):
            add_schedule_rule(cfg, {"days": ["mon"], "start": "17:00", "end": "09:00", "state": "dnd"})
        with self.assertRaisesRegex(ValueError, "end not after start"):
            add_schedule_rule(cfg, {"days": ["mon"], "start": "22:00", "end": "02:00", "state": "dnd"})
        with self.assertRaisesRegex(ValueError, "bad state"):
            add_schedule_rule(cfg, {"days": ["mon"], "start": "09:00", "end": "17:00", "state": "busy"})
        with self.assertRaisesRegex(ValueError, "bad time"):
            add_schedule_rule(cfg, {"days": ["mon"], "start": "nine", "end": "17:00", "state": "dnd"})
        self.assertEqual(len(cfg["schedule"]), 1)

    def test_remove_rule(self):
        cfg = self._config(WEEKDAY_RULE, SAT_RULE)
        out = remove_schedule_rule(cfg, 0)
        self.assertEqual(out["schedule"], [SAT_RULE])
        self.assertEqual(len(cfg["schedule"]), 2)
        with self.assertRaises(IndexError):
            remove_schedule_rule(cfg, -1)
        with self.assertRaises(IndexError):
            remove_schedule_rule(cfg, 99)


if __name__ == "__main__":
    unittest.main()
