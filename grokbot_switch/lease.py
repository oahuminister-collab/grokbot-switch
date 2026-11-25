import json
import os
import uuid
import copy
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from grokbot_switch.status import atomic_write_json, _iso

LEASE_ACTIVE = "active"
LEASE_REVOKED = "revoked"
LEASE_RELEASED = "released"
TOAST = "{bot} stopped. Moving the job to your other computer."

def leases_dir(appdata_dir: str) -> Path:
    """Directory that stores lease JSON files."""
    return Path(appdata_dir) / "leases"

def lease_path(appdata_dir: str, lease_id: str) -> Path:
    """Full path to a lease file."""
    return leases_dir(appdata_dir) / f"{lease_id}.json"

def new_lease_id() -> str:
    """Generate a new random lease identifier."""
    return uuid.uuid4().hex

def _parse_iso(s):
    """Parse ISO strings used in lease files."""
    if s is None:
        return None
    if isinstance(s, datetime):
        return s
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

def write_lease(appdata_dir: str, lease: dict) -> dict:
    """Persist a lease dict to disk."""
    atomic_write_json(lease_path(appdata_dir, lease["lease_id"]), lease)
    return lease

def read_lease(appdata_dir: str, lease_id: str) -> Optional[dict]:
    """Read a lease from disk, returning None on error."""
    p = lease_path(appdata_dir, lease_id)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def create_lease(appdata_dir: str, bot: str, job: str, minutes, now: datetime, last_input_time: Optional[datetime]) -> dict:
    """Create a new lease and store it."""
    lid = new_lease_id()
    lease = {
        "lease_id": lid,
        "bot": bot,
        "job": job,
        "minutes": int(minutes) if minutes is not None else 0,
        "status": LEASE_ACTIVE,
        "started_at": _iso(now),
        "last_input_at_start": _iso(last_input_time),
        "revoked_at": None,
        "revoke_reason": None,
    }
    leases_dir(appdata_dir).mkdir(parents=True, exist_ok=True)
    return write_lease(appdata_dir, lease)

def release_lease(appdata_dir: str, lease_id: str, now: datetime) -> Optional[dict]:
    """Mark a lease as released."""
    lease = read_lease(appdata_dir, lease_id)
    if not lease:
        return None
    lease["status"] = LEASE_RELEASED
    lease["released_at"] = _iso(now)
    return write_lease(appdata_dir, lease)

def list_active_leases(appdata_dir: str) -> list:
    """Return all leases whose status is active."""
    d = leases_dir(appdata_dir)
    if not d.is_dir():
        return []
    out = []
    for p in d.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("status") == LEASE_ACTIVE:
            out.append(data)
    return out

@dataclass
class YieldResult:
    revoked: bool                     # True only when newly revoked in this check
    lease: Optional[dict]            # Updated lease (or original)
    toast: Optional[str]             # Message for UI, if any

def check_yield(lease: Optional[dict], now: datetime, last_input_time: Optional[datetime],
                grace_seconds: int = 2) -> YieldResult:
    """
    Determine whether a lease should be revoked due to user input.
    Does not modify the supplied lease dict.
    """
    if not lease or lease.get("status") != LEASE_ACTIVE:
        return YieldResult(False, lease, None)

    started = _parse_iso(lease.get("started_at"))
    start_input = _parse_iso(lease.get("last_input_at_start"))

    if started is None or last_input_time is None:
        return YieldResult(False, lease, None)

    # Grace period after start
    if (now - started).total_seconds() < float(grace_seconds):
        return YieldResult(False, lease, None)

    # Revoke only if input after the recorded start input
    if start_input is not None and last_input_time > start_input:
        new = copy.deepcopy(lease)
        new["status"] = LEASE_REVOKED
        new["revoked_at"] = _iso(now)
        new["revoke_reason"] = "user_input"
        bot = new.get("bot") or "A bot"
        return YieldResult(True, new, TOAST.format(bot=bot))

    return YieldResult(False, lease, None)

def apply_yield(appdata_dir: str, now: datetime, last_input_time: Optional[datetime],
                grace_seconds: int = 2) -> list:
    """
    Scan active leases, revoke those that need revoking, and persist changes.
    Returns a list of YieldResult objects for the revoked leases.
    """
    results = []
    for lease in list_active_leases(appdata_dir):
        r = check_yield(lease, now, last_input_time, grace_seconds=grace_seconds)
        if r.revoked and r.lease is not None:
            write_lease(appdata_dir, r.lease)
            results.append(r)
    return results

def heartbeat_status(appdata_dir: str, lease_id: str) -> tuple:
    """
    Return (True, "hold") if lease exists and is active,
    otherwise (False, "revoked").
    """
    lease = read_lease(appdata_dir, lease_id)
    if lease and lease.get("status") == LEASE_ACTIVE:
        return (True, "hold")
    return (False, "revoked")
