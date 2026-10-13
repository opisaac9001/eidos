"""The rest of a resident's day: lunch out, a walk after work, the market on Saturday.

Their working hours come from their own rhythm (``domain.world.npc_location``); this is
what fills the rest, so Alderwick has people in it outside nine to five and Patrick can
bump into Mara at the market or Stuart by the river. Each person has their own leanings
(some are walkers, some go to the market, some to the cinema) and each day turns out
differently. Rules only; nobody's whereabouts are told to Patrick, he only sees who's
where he is.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256

# Places people go out to, with the hours they'd be there (start, end) and when.
_LUNCH = ("cafe",)
_AFTER_WORK = ("park", "riverside", "cafe", "market-hall", "secondhand", "library")
_EVENING = ("community-hall", "cinema", "music-room", "sports-ground")
_WEEKEND_MORNING = ("market-hall", "cafe", "secondhand", "library")
_WEEKEND_AFTERNOON = ("park", "riverside", "library", "secondhand", "cafe")
# Who works weekends: the café's open on Saturdays.
_SATURDAY_WORK = frozenset({"mara"})


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


def _pick(actor_id: str, places: tuple[str, ...], *day: object) -> str:
    """Where this person tends to go, leaning on their own tastes, varying day to day."""
    weights = [0.2 + _roll("taste", actor_id, place) ** 2 for place in places]
    point = _roll("pick", actor_id, *day) * sum(weights)
    for place, weight in zip(places, weights, strict=True):
        point -= weight
        if point <= 0:
            return place
    return places[-1]


def day_off(actor_id: str, now: datetime) -> bool:
    """Weekends are their own, except for whoever works them."""
    weekday = now.weekday()
    if weekday == 6:
        return True
    return weekday == 5 and actor_id not in _SATURDAY_WORK


def outings(actor_id: str, usual_location_id: str, now: datetime) -> list[tuple[float, float, str]]:
    """Their outings today: (from hour, until hour, place)."""
    day = now.date().isoformat()
    found: list[tuple[float, float, str]] = []

    def maybe(
        kind: str, chance: float, start: float, length: float, places: tuple[str, ...]
    ) -> None:
        if _roll(kind, actor_id, day) < chance:
            shift = (_roll(kind, "when", actor_id, day) - 0.5) * 1.0
            stay = length * (0.7 + 0.6 * _roll(kind, "long", actor_id, day))
            found.append((start + shift, start + shift + stay, _pick(actor_id, places, kind, day)))

    sociable = 0.6 + 0.8 * _roll("sociable", actor_id)  # some go out a lot, some rarely
    if day_off(actor_id, now):
        maybe("weekend-morning", 0.45 * sociable, 10.5, 1.5, _WEEKEND_MORNING)
        maybe("weekend-afternoon", 0.5 * sociable, 14.5, 2.0, _WEEKEND_AFTERNOON)
    else:
        if usual_location_id not in {"cafe", "home"}:
            maybe("lunch", 0.25 * sociable, 12.6, 0.7, _LUNCH)
        maybe("after-work", 0.3 * sociable, 18.0, 1.5, _AFTER_WORK)
    maybe("evening", 0.12 * sociable, 19.75, 2.0, _EVENING)
    return found


def outing_now(actor_id: str, usual_location_id: str, now: datetime) -> str | None:
    """Where they've gone out to right now, if they're out."""
    hour = now.hour + now.minute / 60
    for start, end, place in outings(actor_id, usual_location_id, now):
        if start <= hour < end:
            return place
    return None
