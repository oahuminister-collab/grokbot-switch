"""Simple clock abstractions.

Provides a minimal `Clock` protocol and two concrete implementations:
- `SystemClock` – returns the current local time.
- `FakeClock` – a mutable clock useful for testing.
"""

from __future__ import annotations

import datetime as _dt
from typing import Protocol, runtime_checkable, Union

__all__ = ["Clock", "SystemClock", "FakeClock"]


@runtime_checkable
class Clock(Protocol):
    """Protocol for objects that can report the current time."""

    def now(self) -> _dt.datetime:
        """Return the current local time as a naive ``datetime``."""
        ...


class SystemClock:
    """Clock that returns the actual system time."""

    def now(self) -> _dt.datetime:
        """Return ``datetime.now()`` (naive, local)."""
        return _dt.datetime.now()


class FakeClock:
    """A controllable clock useful for deterministic tests."""

    def __init__(self, start: _dt.datetime) -> None:
        """
        Initialise the fake clock.

        Parameters
        ----------
        start: datetime
            The initial time the clock should report. Must be naive (no tzinfo).
        """
        if start.tzinfo is not None:
            raise ValueError("FakeClock expects a naive datetime (no tzinfo).")
        self._now = start

    def now(self) -> _dt.datetime:
        """Return the clock's current time."""
        return self._now

    def set(self, dt: _dt.datetime) -> None:
        """
        Set the clock to a specific time.

        Parameters
        ----------
        dt: datetime
            New current time (must be naive).
        """
        if dt.tzinfo is not None:
            raise ValueError("FakeClock expects a naive datetime (no tzinfo).")
        self._now = dt

    def advance(self, seconds: Union[int, float, _dt.timedelta]) -> None:
        """
        Move the clock forward.

        Parameters
        ----------
        seconds: int, float, or timedelta
            Amount of time to add. ``int``/``float`` are interpreted as seconds.
        """
        if isinstance(seconds, _dt.timedelta):
            delta = seconds
        else:
            delta = _dt.timedelta(seconds=float(seconds))
        self._now = self._now + delta
