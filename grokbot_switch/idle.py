"""Idle time providers for GrokBot switch.

Provides a protocol and two concrete implementations:
* WindowsIdleProvider – uses Win32 APIs.
* FakeIdleProvider – deterministic provider for testing.
"""

from __future__ import annotations

import ctypes
import os
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable, Optional


@runtime_checkable
class IdleProvider(Protocol):
    """Protocol for idle-time providers."""

    def seconds_idle(self) -> float:
        """Return the number of seconds the system has been idle."""
        ...

    def last_input_time(self, now: Optional[datetime] = None) -> datetime:
        """Return the naive local datetime of the last user input.

        If *now* is supplied it is used as the reference point, otherwise
        ``datetime.now()`` is used.
        """
        ...


# ----------------------------------------------------------------------
# Windows implementation
# ----------------------------------------------------------------------
class WindowsIdleProvider:
    """Idle provider that works on Windows using GetLastInputInfo."""

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint),
                    ("dwTime", ctypes.c_uint)]

    def __init__(self) -> None:
        if os.name != "nt":
            raise NotImplementedError("WindowsIdleProvider is only available on Windows")
        # Load required functions lazily; they may be missing on very old systems.
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

        # Verify that GetLastInputInfo exists.
        if not hasattr(self._user32, "GetLastInputInfo"):
            raise NotImplementedError("GetLastInputInfo not available on this Windows version")

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------
    def _get_tick_count(self) -> int:
        """Return the current tick count in milliseconds."""
        if hasattr(self._kernel32, "GetTickCount64"):
            return self._kernel32.GetTickCount64()
        # Fallback to 32-bit version (wraps every ~49.7 days)
        return self._kernel32.GetTickCount()

    def _get_last_input_tick(self) -> int:
        """Return the tick count (ms) at the last input event."""
        li = self._LASTINPUTINFO()
        li.cbSize = ctypes.sizeof(self._LASTINPUTINFO)
        if not self._user32.GetLastInputInfo(ctypes.byref(li)):
            raise ctypes.WinError()
        return li.dwTime

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def seconds_idle(self) -> float:
        """Idle time in seconds, never negative."""
        now_tick = self._get_tick_count()
        last_tick = self._get_last_input_tick()
        diff = now_tick - last_tick
        if diff < 0:
            diff = 0
        return diff / 1000.0

    def last_input_time(self, now: Optional[datetime] = None) -> datetime:
        """Naive local datetime of the last input."""
        if now is None:
            now = datetime.now()
        idle_seconds = self.seconds_idle()
        return now - timedelta(seconds=idle_seconds)


# ----------------------------------------------------------------------
# Fake implementation for testing
# ----------------------------------------------------------------------
class FakeIdleProvider:
    """Deterministic idle provider useful in unit tests."""

    def __init__(self, clock, seconds_idle: float = 0.0) -> None:
        """
        Parameters
        ----------
        clock: object with a ``now() -> datetime`` method.
        seconds_idle: initial idle duration (ignored if an explicit last input
                      time is later set).
        """
        self._clock = clock
        self._seconds_idle = max(0.0, float(seconds_idle))
        self._explicit_last_input: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------
    def set_seconds_idle(self, n: float) -> None:
        """Set the idle duration directly and clear any explicit last input."""
        self._seconds_idle = max(0.0, float(n))
        self._explicit_last_input = None

    def set_last_input_time(self, dt: datetime) -> None:
        """Force a specific last-input timestamp."""
        self._explicit_last_input = dt

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def seconds_idle(self) -> float:
        """Return the current idle duration in seconds."""
        if self._explicit_last_input is not None:
            delta = self._clock.now() - self._explicit_last_input
            secs = delta.total_seconds()
            return max(0.0, secs)
        return self._seconds_idle

    def last_input_time(self, now: Optional[datetime] = None) -> datetime:
        """Return the last-input timestamp."""
        if now is None:
            now = self._clock.now()
        if self._explicit_last_input is not None:
            return self._explicit_last_input
        return now - timedelta(seconds=self._seconds_idle)


__all__ = [
    "IdleProvider",
    "WindowsIdleProvider",
    "FakeIdleProvider",
]
