"""Explicit authored seed world. No generated text is presented as AI output."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class RoutineBeat:
    hour: int
    location_id: str
    description: str
    energy: float


DAILY_ROUTINE = (
    RoutineBeat(7, "home", "Woke up and made breakfast.", 0.9),
    RoutineBeat(9, "cafe", "Visited the cafe before work.", 0.85),
    RoutineBeat(10, "workshop", "Started work at the neighborhood workshop.", 0.75),
    RoutineBeat(13, "park", "Took a lunch break in the park.", 0.65),
    RoutineBeat(14, "workshop", "Returned to the workshop.", 0.6),
    RoutineBeat(18, "home", "Returned home for dinner.", 0.4),
    RoutineBeat(22, "home", "Settled down for the night.", 0.2),
)


def beats_between(start: datetime, end: datetime) -> list[tuple[datetime, RoutineBeat]]:
    """Left-open interval prevents repeating a beat after a restart."""
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    result = []
    while day <= end:
        for beat in DAILY_ROUTINE:
            at = day + timedelta(hours=beat.hour)
            if start < at <= end:
                result.append((at, beat))
        day += timedelta(days=1)
    return result
