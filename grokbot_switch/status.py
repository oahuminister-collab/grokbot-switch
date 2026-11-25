from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional


def atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    """Write *data* as JSON to *path* atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def status_path(appdata_dir: str | Path) -> Path:
    """Return the full path to the status file."""
    return Path(appdata_dir) / "status.json"


def _iso(dt: Optional[datetime | str]) -> Optional[str]:
    """Convert *dt* to an ISO-8601 string (seconds precision) or pass through."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat(timespec="seconds")


def write_status(
    appdata_dir: str | Path,
    decision: Any,
    last_input_time: Optional[datetime],
    idle_seconds: float,
    extra: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """
    Write a status JSON file.

    *decision* must expose ``state``, ``reason``, ``reason_text`` and optionally
    ``manual_until`` attributes.
    """
    payload: dict[str, Any] = {
        "state": getattr(decision, "state", None),
        "reason": getattr(decision, "reason", None),
        "reason_text": getattr(decision, "reason_text", None),
        "last_input_time": _iso(last_input_time),
        "idle_seconds": int(idle_seconds),
        "updated_at": _iso(now or datetime.now()),
        "manual_until": _iso(getattr(decision, "manual_until", None)),
    }

    if isinstance(extra, Mapping):
        payload.update(extra)

    atomic_write_json(status_path(appdata_dir), payload)
    return payload


def read_status(appdata_dir: str | Path) -> Optional[dict[str, Any]]:
    """Read the status file; return ``None`` if missing or invalid."""
    try:
        with status_path(appdata_dir).open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
