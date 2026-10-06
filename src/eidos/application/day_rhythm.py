"""When in the day something happens: about the same time, never the same time.

A person reads the news over breakfast and again in the evening, thinks back over the day
before bed, hears friends' news after work. Not at 07:00 and 18:00 on the dot every day.
Each of these keeps its rough place in the day and moves by an hour or two from day to day,
the same way on replay.
"""

from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256


def hour_today(key: str, day: date, usual: int, earlier: int = 1, later: int = 1) -> int:
    """The hour ``key`` happens on ``day``: ``usual``, give or take."""
    span = earlier + later + 1
    roll = int.from_bytes(sha256(f"{key}:{day.isoformat()}".encode()).digest()[:4], "big")
    return max(0, min(23, usual - earlier + roll % span))


def is_the_hour(key: str, at: datetime, usual: int, earlier: int = 1, later: int = 1) -> bool:
    return at.hour == hour_today(key, at.date(), usual, earlier, later)
