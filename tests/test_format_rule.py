import unittest
from grokbot_switch.schedule_edit import format_rule_line


class TestFormatRule(unittest.TestCase):
    def test_weekday_range(self):
        text = format_rule_line({
            "days": ["mon", "tue", "wed", "thu", "fri"],
            "start": "09:00",
            "end": "17:00",
            "state": "dnd",
        })
        self.assertEqual(text, "Weekdays, 9:00 AM – 5:00 PM · Do Not Disturb")

    def test_single_day_available(self):
        text = format_rule_line({
            "days": ["sat"],
            "start": "08:00",
            "end": "12:00",
            "state": "available",
        })
        self.assertEqual(text, "Sat, 8:00 AM – 12:00 PM · Available")

    def test_split_days(self):
        text = format_rule_line({
            "days": ["mon", "wed", "fri"],
            "start": "13:30",
            "end": "14:00",
            "state": "dnd",
        })
        self.assertEqual(text, "Mon, Wed, Fri, 1:30 PM – 2:00 PM · Do Not Disturb")


if __name__ == "__main__":
    unittest.main()
