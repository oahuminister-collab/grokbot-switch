"""Configuration handling for GrokBot switch."""

from pathlib import Path
import json, os, copy, re

# Constants
STATES = ("available", "dnd")
DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
APP_DIR_NAME = "GrokBotSwitch"

DEFAULT_CONFIG = {
    "schedule": [],
    "auto_dnd_when_active": True,
    "active_within_seconds": 120,
    "auto_available_after_idle": True,
    "idle_minutes": 30,
    "ask_before_use": True,
    "auto_allow_minutes": 5,
    "start_with_windows": False,
    "widget_position": None,
    "widget_minimized": False,
    "ipc_port": 47281,
    "yield_grace_seconds": 2,
}


def default_appdata_dir() -> Path:
    """Return the default directory for app data."""
    env = os.getenv("GROKBOT_SWITCH_APPDATA")
    if env:
        return Path(env)
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", str(Path.home())))
    else:
        base = Path.home()
    return base / APP_DIR_NAME


_time_re = re.compile(r"^(2[0-3]|[01]?\d):([0-5]\d)$")


def parse_hhmm(s: str):
    """Parse 'HH:MM' into (hour, minute) or None."""
    if not isinstance(s, str):
        return None
    m = _time_re.fullmatch(s.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def _minutes_since_midnight(t):
    h, m = t
    return h * 60 + m


def valid_schedule_rule(rule: dict) -> bool:
    """Validate a schedule rule dict."""
    if not isinstance(rule, dict):
        return False
    days = rule.get("days")
    if not (isinstance(days, (list, tuple)) and days):
        return False
    if any(d not in DAY_NAMES for d in days):
        return False
    start = parse_hhmm(rule.get("start", ""))
    end = parse_hhmm(rule.get("end", ""))
    if not (start and end):
        return False
    if _minutes_since_midnight(start) >= _minutes_since_midnight(end):
        return False
    if rule.get("state") not in STATES:
        return False
    return True


def _coerce_int(value, default):
    try:
        i = int(value)
        return i if i >= 0 else default
    except Exception:
        return default


def _coerce_bool(value, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, str)):
        s = str(value).strip().lower()
        if s in ("1", "true", "yes", "y"):
            return True
        if s in ("0", "false", "no", "n"):
            return False
    return default


def _coerce_widget_pos(value):
    """Accept {"x", "y"} or [x, y]; return {"x": int, "y": int} or None."""
    if value is None:
        return None
    if isinstance(value, dict):
        try:
            return {"x": int(value["x"]), "y": int(value["y"])}
        except Exception:
            return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return {"x": int(value[0]), "y": int(value[1])}
        except Exception:
            return None
    return None


def _sanitize(data):
    """Merge user data onto defaults, cleaning types."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(data, dict):
        return cfg

    # Schedule
    raw_sched = data.get("schedule")
    if isinstance(raw_sched, list):
        cfg["schedule"] = [r for r in raw_sched if valid_schedule_rule(r)]

    # Booleans
    for key in (
        "auto_dnd_when_active",
        "auto_available_after_idle",
        "ask_before_use",
        "start_with_windows",
        "widget_minimized",
    ):
        if key in data:
            cfg[key] = _coerce_bool(data[key], cfg[key])

    # Integers
    for key in (
        "active_within_seconds",
        "idle_minutes",
        "auto_allow_minutes",
        "ipc_port",
        "yield_grace_seconds",
    ):
        if key in data:
            cfg[key] = _coerce_int(data[key], cfg[key])

    # Widget position
    if "widget_position" in data:
        cfg["widget_position"] = _coerce_widget_pos(data["widget_position"])

    return cfg


def load_config(path: Path) -> dict:
    """Load config from *path*, returning a sanitized dict."""
    try:
        with Path(path).open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        raw = {}
    return _sanitize(raw)


def save_config(path: Path, data: dict):
    """Sanitize *data* and write atomically to *path*."""
    cfg = _sanitize(data)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


__all__ = [
    "STATES",
    "DAY_NAMES",
    "APP_DIR_NAME",
    "DEFAULT_CONFIG",
    "default_appdata_dir",
    "parse_hhmm",
    "valid_schedule_rule",
    "load_config",
    "save_config",
]
