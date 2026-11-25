"""Pure helpers for the minimize/restore control. No UI toolkit required."""

from __future__ import annotations

from typing import Optional, Tuple

MINI_SIZE = 28
_DOT = "\u00b7"

Box = Optional[Tuple[float, float, float, float]]


def tooltip_text(state: str) -> str:
    if state == "dnd":
        return f"Do Not Disturb {_DOT} click to open"
    return f"Available {_DOT} click to open"


def in_box(event_x: float, event_y: float, box: Box) -> bool:
    if not box:
        return False
    x1, y1, x2, y2 = box
    return x1 <= event_x <= x2 and y1 <= event_y <= y2


def pill_anchor(
    pill_x: int, pill_y: int, pill_w: int, pill_h: int, mini: int = MINI_SIZE
) -> tuple[int, int]:
    """Top-left of a mini dot whose bottom-right matches the pill body's."""
    return (int(pill_x + pill_w - mini), int(pill_y + pill_h - mini))


def pill_from_dot(
    dot_x: int, dot_y: int, pill_w: int, pill_h: int, mini: int = MINI_SIZE
) -> tuple[int, int]:
    """Inverse of pill_anchor."""
    return (int(dot_x + mini - pill_w), int(dot_y + mini - pill_h))
