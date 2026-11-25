from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import Optional, List, Any

from grokbot_switch.config import STATES, DAY_NAMES, parse_hhmm, valid_schedule_rule

# mon=0 ... sun=6
DAY_INDEX = {name: i for i, name in enumerate(DAY_NAMES)}


def day_name(dt: datetime) -> str:
    """Return short day name matching DAY_NAMES."""
    return DAY_NAMES[dt.weekday()]


def in_window(now: datetime, rule: dict) -> bool:
    """True if now falls inside rule's time window."""
    if not valid_schedule_rule(rule):
        return False
    if day_name(now) not in rule["days"]:
        return False
    sh, sm = parse_hhmm(rule["start"])
    eh, em = parse_hhmm(rule["end"])
    start_sec = sh * 3600 + sm * 60
    end_sec = eh * 3600 + em * 60
    cur_sec = now.hour * 3600 + now.minute * 60 + now.second
    return start_sec <= cur_sec < end_sec


def valid_rule(rule: dict) -> bool:
    """Alias for config validator."""
    return valid_schedule_rule(rule)


def _rule_instants_on_date(d, rule: dict) -> List[datetime]:
    """Return start and end datetimes for rule on given date.

    Skip dates whose weekday is not in the rule's days list.
    """
    if DAY_NAMES[d.weekday()] not in rule.get("days", []):
        return []
    sh, sm = parse_hhmm(rule["start"])
    eh, em = parse_hhmm(rule["end"])
    start_dt = datetime.combine(d, time(sh, sm))
    end_dt = datetime.combine(d, time(eh, em))
    return [start_dt, end_dt]


def next_boundary(now: datetime, config: dict) -> Optional[datetime]:
    """Soonest start/end after now within the next 8 days."""
    candidates: List[datetime] = []
    schedule = config.get("schedule") or []
    for offset in range(0, 8):
        day = (now + timedelta(days=offset)).date()
        for rule in schedule:
            if not valid_schedule_rule(rule):
                continue
            for instant in _rule_instants_on_date(day, rule):
                if instant > now:
                    candidates.append(instant)
    return min(candidates) if candidates else None


@dataclass
class Decision:
    state: str
    reason: str  # schedule|active|idle|manual|default
    reason_text: str
    manual_until: Optional[datetime] = None


def reason_text(reason: str, state: str) -> str:
    if reason == "schedule" and state == "dnd":
        return "Scheduled: Do Not Disturb"
    if reason == "schedule" and state == "available":
        return "Scheduled: Available"
    if reason == "active":
        return "Auto: you're using this PC"
    if reason == "idle":
        return "Auto: idle"
    if reason == "manual":
        return "Manual"
    return "Available" if state == "available" else "Do Not Disturb"


def decide(
    now: datetime,
    seconds_idle: Any,
    config: dict,
    manual: Optional[dict] = None,
    last_state: Optional[str] = None,
) -> Decision:
    seconds_idle = float(seconds_idle)
    active_within = int(config.get("active_within_seconds", 120))
    idle_limit = int(config.get("idle_minutes", 30)) * 60
    auto_dnd = bool(config.get("auto_dnd_when_active", True))
    auto_avail = bool(config.get("auto_available_after_idle", True))

    # 1) manual override
    if isinstance(manual, dict):
        mstate = manual.get("state")
        set_at = manual.get("set_at")
        if mstate in ("available", "dnd") and isinstance(set_at, datetime):
            boundary = next_boundary(set_at, config)
            expired = False
            if boundary is not None and now >= boundary:
                expired = True
            sis = manual.get("seconds_idle_at_set")
            if sis is not None and not expired:
                sis = float(sis)
                if auto_dnd and seconds_idle < active_within and sis >= active_within:
                    expired = True
                elif auto_avail and seconds_idle >= idle_limit and sis < idle_limit:
                    expired = True
            if not expired:
                return Decision(
                    mstate,
                    "manual",
                    reason_text("manual", mstate),
                    manual_until=boundary,
                )

    # 2) schedule
    hits = [
        r["state"]
        for r in config.get("schedule") or []
        if in_window(now, r)
    ]
    if hits:
        state = "dnd" if "dnd" in hits else "available"
        return Decision(state, "schedule", reason_text("schedule", state))

    # 3) auto DND when active
    if auto_dnd and seconds_idle < active_within:
        return Decision("dnd", "active", reason_text("active", "dnd"))

    # 4) auto available after idle
    if auto_avail and seconds_idle >= idle_limit:
        return Decision("available", "idle", reason_text("idle", "available"))

    # 5) sticky last state
    if last_state in ("available", "dnd"):
        return Decision(last_state, "default", reason_text("default", last_state))

    return Decision("available", "default", reason_text("default", "available"))


__all__ = [
    "Decision",
    "day_name",
    "in_window",
    "valid_rule",
    "next_boundary",
    "reason_text",
    "decide",
]
