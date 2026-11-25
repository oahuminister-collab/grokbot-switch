import os
from pathlib import Path
from typing import Optional

STARTUP_NAME = "GrokBotSwitch"

def _is_windows() -> bool:
    return os.name == "nt"

def startup_folder() -> Optional[Path]:
    """Return the current user's Startup folder on Windows, else None."""
    if not _is_windows():
        return None
    appdata = os.getenv("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

def shortcut_path() -> Optional[Path]:
    """Path to the .bat file that enables the startup entry."""
    folder = startup_folder()
    return folder / f"{STARTUP_NAME}.bat" if folder else None

def is_enabled() -> bool:
    """True if the startup .bat exists."""
    p = shortcut_path()
    return bool(p and p.is_file())

def enable(command_line: str) -> Path:
    """
    Create a .bat file in the user's Startup folder that runs ``command_line``.
    ``command_line`` should already be properly quoted.
    Raises NotImplementedError on non-Windows platforms.
    Returns the path to the created .bat file.
    """
    if not _is_windows():
        raise NotImplementedError("Startup helper is only implemented for Windows.")
    bat_path = shortcut_path()
    if bat_path is None:  # pragma: no cover
        raise RuntimeError("Unable to determine startup folder.")
    bat_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""@echo off
{command_line}
"""
    bat_path.write_text(content, encoding="utf-8")
    return bat_path

def disable() -> None:
    """Remove the startup .bat file if it exists."""
    p = shortcut_path()
    if p and p.is_file():
        p.unlink()

def set_enabled(enabled: bool, command_line: str) -> None:
    """Enable or disable the startup entry."""
    if enabled:
        enable(command_line)
    else:
        disable()
