#!/usr/bin/env python3
"""Command-line interface bots use to ask if this PC may be used."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import json
from datetime import datetime

from grokbot_switch.config import default_appdata_dir, load_config
from grokbot_switch.status import read_status
from grokbot_switch.lease import (
    heartbeat_status,
    release_lease,
    create_lease,
)
from grokbot_switch.ipc import send_request, DEFAULT_PORT


def _print_json(obj) -> None:
    """Print a JSON object on a single line and flush stdout."""
    print(json.dumps(obj, separators=(",", ":")), flush=True)


def _appdata() -> Path:
    return default_appdata_dir()


def _port(appdata: Path) -> int:
    st = read_status(appdata) or {}
    if isinstance(st.get("ipc_port"), int) and st["ipc_port"] > 0:
        return st["ipc_port"]
    cfg = load_config(appdata / "config.json")
    return int(cfg.get("ipc_port") or DEFAULT_PORT)


def cmd_heartbeat(appdata: Path, lease_id: str) -> int:
    ok, result = heartbeat_status(appdata, lease_id)
    _print_json({"allow": bool(ok), "result": result, "lease_id": lease_id})
    return 0 if ok else 1


def cmd_release(appdata: Path, lease_id: str) -> int:
    release_lease(appdata, lease_id, datetime.now())
    _print_json({"allow": False, "result": "released", "lease_id": lease_id})
    return 0


def cmd_check(
    appdata: Path,
    bot: str,
    job: str,
    minutes: int,
    show_popup,
) -> int:
    cfg = load_config(appdata / "config.json")
    port = _port(appdata)
    try:
        timeout_seconds = max(
            30,
            int((cfg.get("auto_allow_minutes") or 5) * 60) + 15,
        )
        # Use send_request, not request_with_fallback, so a down
        # widget does not wait minutes on a file inbox that nobody is watching.
        resp = send_request(
            {"type": "check", "bot": bot, "job": job, "minutes": minutes},
            port=port,
            timeout=timeout_seconds,
        )
        allow = bool(resp.get("allow"))
        if "result" not in resp:
            resp = {"allow": allow, "result": resp.get("result", "error"), **resp}
        _print_json(resp)
        return 0 if allow else 1
    except TimeoutError:
        _print_json(
            {"allow": False, "result": "error", "reason": "timeout waiting for an answer"}
        )
        return 2
    except (ConnectionRefusedError, OSError):
        pass

    st = read_status(appdata) or {}
    state = st.get("state") or "available"

    if state == "dnd":
        _print_json(
            {
                "allow": False,
                "result": "dnd",
                "reason": st.get("reason_text") or "Do Not Disturb",
            }
        )
        return 1

    if not cfg.get("ask_before_use", True):
        lease = create_lease(appdata, bot, job, minutes, datetime.now(), datetime.now())
        _print_json({"allow": True, "result": "accept", "lease_id": lease["lease_id"]})
        return 0

    if show_popup is None:
        try:
            from grokbot_switch.widget import show_permission_popup as show_popup
        except Exception:
            _print_json(
                {
                    "allow": False,
                    "result": "error",
                    "reason": "switch is not running and the popup could not be opened",
                }
            )
            return 2

    result = show_popup(bot, job, minutes, cfg.get("auto_allow_minutes", 5))

    if result in ("accept", "auto-accept"):
        lease = create_lease(appdata, bot, job, minutes, datetime.now(), datetime.now())
        _print_json(
            {"allow": True, "result": result, "lease_id": lease["lease_id"]}
        )
        return 0

    _print_json({"allow": False, "result": result or "decline"})
    return 1


def main(argv=None, show_popup=None) -> int:
    parser = argparse.ArgumentParser(
        description="Ask whether this PC may be used by a bot."
    )
    parser.add_argument("--bot", default="A bot")
    parser.add_argument("--job", default="")
    parser.add_argument("--minutes", type=int, default=0)
    parser.add_argument(
        "--heartbeat", metavar="LEASE", dest="heartbeat", help="heartbeat a lease"
    )
    parser.add_argument(
        "--release", metavar="LEASE", dest="release", help="release a lease"
    )
    args = parser.parse_args(argv)

    appdata = _appdata()

    try:
        if args.heartbeat:
            return cmd_heartbeat(appdata, args.heartbeat)
        if args.release:
            return cmd_release(appdata, args.release)
        return cmd_check(appdata, args.bot, args.job, args.minutes, show_popup)
    except Exception as exc:
        _print_json({"allow": False, "result": "error", "reason": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
