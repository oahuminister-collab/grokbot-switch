"""Pure helpers for reading and editing the schedule list. No UI."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from grokbot_switch.config import DAY_NAMES, STATES, parse_hhmm, valid_schedule_rule

_EN_DASH = "\u2013"
_DOT = "\u00b7"

_DAY_LABEL = {
    "mon": "Mon",
    "tue": "Tue",
    "wed": "Wed",
    "thu": "Thu",
    "fri": "Fri",
    "sat": "Sat",
    "sun": "Sun",
}


def format_days(days: Iterable[str]) -> str:
    ordered = [d for d in DAY_NAMES if d in set(days or [])]
    if not ordered:
        return "No days"
    if len(ordered) == 7:
        return "Every day"
    if ordered == list(DAY_NAMES[:5]):
        return "Weekdays"
    if ordered == list(DAY_NAMES[5:]):
        return "Weekends"

    groups: list[list[str]] = []
    for d in ordered:
        if groups and DAY_NAMES.index(d) == DAY_NAMES.index(groups[-1][-1]) + 1:
            groups[-1].append(d)
        else:
            groups.append([d])

    parts = []
    for grp in groups:
        if len(grp) == 1:
            parts.append(_DAY_LABEL[grp[0]])
        else:
            parts.append(f"{_DAY_LABEL[grp[0]]}{_EN_DASH}{_DAY_LABEL[grp[-1]]}")
    return ", ".join(parts)


def format_time_12h(hhmm: str) -> str:
    parsed = parse_hhmm(hhmm) if isinstance(hhmm, str) else None
    if parsed is None:
        return str(hhmm or "")
    hour, minute = parsed
    suffix = "AM" if hour < 12 else "PM"
    hour_12 = hour % 12 or 12
    return f"{hour_12}:{minute:02d} {suffix}"


def format_time_range(start: str, end: str) -> str:
    return f"{format_time_12h(start)} {_EN_DASH} {format_time_12h(end)}"


def format_rule_line(rule: Dict[str, Any]) -> str:
    days_str = format_days(rule.get("days") or [])
    time_range = format_time_range(rule.get("start", ""), rule.get("end", ""))
    state = rule.get("state", "")
    state_str = {"dnd": "Do Not Disturb", "available": "Available"}.get(state, str(state or ""))
    return f"{days_str}, {time_range} {_DOT} {state_str}"


def normalize_rule(rule: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not valid_schedule_rule(rule):
        return None
    start_h, start_m = parse_hhmm(rule["start"])
    end_h, end_m = parse_hhmm(rule["end"])
    return {
        "days": [d for d in DAY_NAMES if d in set(rule["days"])],
        "start": f"{start_h:02d}:{start_m:02d}",
        "end": f"{end_h:02d}:{end_m:02d}",
        "state": rule["state"],
    }


def add_schedule_rule(config: Dict[str, Any], rule: Dict[str, Any]) -> Dict[str, Any]:
    new_config = dict(config)
    schedule = list(config.get("schedule") or [])

    days = rule.get("days") if isinstance(rule, dict) else None
    if not days:
        raise ValueError("no days")

    start = rule.get("start")
    end = rule.get("end")
    state = rule.get("state")
    start_parsed = parse_hhmm(start) if isinstance(start, str) else None
    end_parsed = parse_hhmm(end) if isinstance(end, str) else None
    if start_parsed is None or end_parsed is None:
        raise ValueError("bad time")
    if start_parsed >= end_parsed:
        raise ValueError("end not after start")
    if state not in STATES:
        raise ValueError("bad state")

    normalized = normalize_rule(rule)
    if normalized is None:
        raise ValueError("invalid rule")

    schedule.append(normalized)
    new_config["schedule"] = schedule
    return new_config


def remove_schedule_rule(config: Dict[str, Any], index: int) -> Dict[str, Any]:
    schedule = list(config.get("schedule") or [])
    if not (0 <= index < len(schedule)):
        raise IndexError("schedule index out of range")
    new_config = dict(config)
    del schedule[index]
    new_config["schedule"] = schedule
    return new_config


def parse_time_input(s: str) -> Optional[str]:
    """Return zero-padded HH:MM, or None. Accepts '09:00', '9:00', '9:00 AM', '5:00pm'."""
    if not isinstance(s, str):
        return None
    raw = s.strip().upper().replace(".", "")
    ampm = None
    if raw.endswith("AM") or raw.endswith("PM"):
        ampm = raw[-2:]
        raw = raw[:-2].strip()
    parsed = parse_hhmm(raw)
    if parsed is None:
        return None
    hour, minute = parsed
    if ampm:
        if hour == 12:
            hour = 0 if ampm == "AM" else 12
        elif ampm == "PM":
            hour += 12
        if hour > 23:
            return None
    return f"{hour:02d}:{minute:02d}"
