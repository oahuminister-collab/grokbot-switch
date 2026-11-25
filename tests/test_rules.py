import unittest
import copy
from datetime import datetime, timedelta

from grokbot_switch.rules import decide, next_boundary, in_window
from grokbot_switch.config import DEFAULT_CONFIG


def dt(date_str: str, time_str: str) -> datetime:
    """Helper to build a naive datetime from date (YYYY-MM-DD) and time (HH:MM)."""
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")


class TestRules(unittest.TestCase):
    """Comprehensive unit tests for the rule engine."""

    def setUp(self):
        # Work with a fresh copy of the default configuration for each test.
        # New installs have an empty schedule; these tests cover the weekday
        # 9:00-17:00 DND rule, so attach that fixture here.
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.config["schedule"] = [{
            "days": ["mon", "tue", "wed", "thu", "fri"],
            "start": "09:00",
            "end": "17:00",
            "state": "dnd",
        }]

    def test_weekday_schedule_wins_over_idle(self):
        now = dt("2026-11-23", "10:00")          # Monday
        decision = decide(now, seconds_idle=7200, config=self.config)
        self.assertEqual(decision.state, "dnd")
        self.assertEqual(decision.reason, "schedule")

    def test_weekday_end_exclusive_idle(self):
        now = dt("2026-11-23", "17:00")          # Monday, exactly at end
        decision = decide(now, seconds_idle=7200, config=self.config)
        self.assertEqual(decision.state, "available")
        self.assertEqual(decision.reason, "idle")

    def test_weekday_end_active(self):
        now = dt("2026-11-23", "17:00")          # Monday, exactly at end
        decision = decide(now, seconds_idle=30, config=self.config)
        self.assertEqual(decision.state, "dnd")
        self.assertEqual(decision.reason, "active")

    def test_saturday_active(self):
        now = dt("2026-11-21", "10:00")          # Saturday
        decision = decide(now, seconds_idle=30, config=self.config)
        self.assertEqual(decision.state, "dnd")
        self.assertEqual(decision.reason, "active")

    def test_saturday_idle(self):
        now = dt("2026-11-21", "10:00")          # Saturday
        decision = decide(now, seconds_idle=1800, config=self.config)
        self.assertEqual(decision.state, "available")
        self.assertEqual(decision.reason, "idle")

    def test_sticky_after_active(self):
        now = dt("2026-11-21", "10:00")          # Saturday
        decision = decide(
            now,
            seconds_idle=600,
            config=self.config,
            last_state="dnd",
        )
        self.assertEqual(decision.state, "dnd")
        self.assertEqual(decision.reason, "default")

    def test_manual_available_holds_during_schedule(self):
        manual = {
            "state": "available",
            "set_at": dt("2026-11-23", "10:00"),
            "seconds_idle_at_set": 30,
        }
        now = dt("2026-11-23", "10:05")
        decision = decide(
            now,
            seconds_idle=30,
            config=self.config,
            manual=manual,
        )
        self.assertEqual(decision.state, "available")
        self.assertEqual(decision.reason, "manual")
        self.assertIsNotNone(decision.manual_until)

    def test_manual_expires_at_boundary_then_active(self):
        manual = {
            "state": "available",
            "set_at": dt("2026-11-23", "10:00"),
            "seconds_idle_at_set": 30,
        }
        now = dt("2026-11-23", "17:00")          # boundary of default schedule
        decision = decide(
            now,
            seconds_idle=30,
            config=self.config,
            manual=manual,
        )
        self.assertEqual(decision.state, "dnd")
        self.assertEqual(decision.reason, "active")

    def test_manual_expires_at_boundary_then_idle(self):
        manual = {
            "state": "available",
            "set_at": dt("2026-11-23", "10:00"),
            "seconds_idle_at_set": 30,
        }
        now = dt("2026-11-23", "17:00")
        decision = decide(
            now,
            seconds_idle=7200,
            config=self.config,
            manual=manual,
        )
        self.assertEqual(decision.state, "available")
        self.assertEqual(decision.reason, "idle")

    def test_manual_dnd_already_idle_holds(self):
        manual = {
            "state": "dnd",
            "set_at": dt("2026-11-21", "10:00"),
            "seconds_idle_at_set": 2400,
        }
        now = dt("2026-11-21", "10:40")          # 40 min later, still idle 2400 s
        decision = decide(
            now,
            seconds_idle=2400,
            config=self.config,
            manual=manual,
        )
        self.assertEqual(decision.state, "dnd")
        self.assertEqual(decision.reason, "manual")

    def test_manual_available_then_walks_away(self):
        manual = {
            "state": "available",
            "set_at": dt("2026-11-21", "10:00"),
            "seconds_idle_at_set": 30,
        }
        now = dt("2026-11-21", "10:40")
        decision = decide(
            now,
            seconds_idle=2400,
            config=self.config,
            manual=manual,
        )
        self.assertEqual(decision.state, "available")
        self.assertEqual(decision.reason, "idle")

    def test_manual_dnd_then_user_returns(self):
        manual = {
            "state": "dnd",
            "set_at": dt("2026-11-21", "10:00"),
            "seconds_idle_at_set": 400,
        }
        now = dt("2026-11-21", "10:05")
        decision = decide(
            now,
            seconds_idle=10,
            config=self.config,
            manual=manual,
        )
        self.assertEqual(decision.state, "dnd")
        # An older assertion used reason "manual"; decide() expires
        # the override when the user comes back, then auto-DND applies.
        self.assertEqual(decision.reason, "active")

    def test_overlapping_rules_dnd_wins(self):
        # Add two overlapping rules for Saturday 10:00 – 12:00
        self.config["schedule"] = [
            {
                "days": ["sat"],
                "start": "10:00",
                "end": "12:00",
                "state": "available",
            },
            {
                "days": ["sat"],
                "start": "10:00",
                "end": "12:00",
                "state": "dnd",
            },
        ]
        now = dt("2026-11-21", "10:30")
        decision = decide(now, seconds_idle=30, config=self.config)
        self.assertEqual(decision.state, "dnd")
        self.assertEqual(decision.reason, "schedule")

    def test_midnight_crossing_rule_ignored(self):
        # Replace schedule with a rule that spans midnight on Monday.
        self.config["schedule"] = [
            {
                "days": ["mon"],
                "start": "22:00",
                "end": "06:00",
                "state": "dnd",
            }
        ]
        now = dt("2026-11-23", "23:00")          # Monday 23:00; start>=end is invalid
        decision = decide(now, seconds_idle=7200, config=self.config)
        self.assertEqual(decision.state, "available")
        self.assertEqual(decision.reason, "idle")

    def test_next_boundary_friday_afternoon(self):
        now = dt("2026-11-20", "16:00")          # Friday
        nb = next_boundary(now, self.config)
        expected = dt("2026-11-20", "17:00")
        self.assertEqual(nb, expected)

    def test_next_boundary_friday_1700(self):
        now = dt("2026-11-20", "17:00")          # Friday exactly at schedule end
        nb = next_boundary(now, self.config)
        expected = dt("2026-11-23", "09:00")     # Next Monday start
        self.assertEqual(nb, expected)

    def test_next_boundary_saturday(self):
        now = dt("2026-11-21", "12:00")          # Saturday
        nb = next_boundary(now, self.config)
        expected = dt("2026-11-23", "09:00")     # Next Monday start
        self.assertEqual(nb, expected)


if __name__ == "__main__":
    unittest.main()
