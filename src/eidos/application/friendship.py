"""How deep a friendship runs, and why a close friend stays a close friend.

Inspired by the twelve-level view of friendship in "12 Levels of Friendship and Why It
Matters" (Spark Joy and Flow): most friendships sit at level five or below, deeper bonds
are built by what people go through together rather than by hours logged, and a deep
friendship does not need constant upkeep. Time apart does not break it.

Depth and recency are separate here. Depth accumulates from shared moments: a passing
chat counts for little, time spent together for more, and being there through something
hard, clearing the air after a clash, and the years all count most. Higher levels need
that kind of history, not just frequency. How much a friendship needs keeping up depends
on its depth:

* everyday (levels 1-3): acquaintances fade after a couple of weeks apart;
* real connection (4-5): fades slowly after about six weeks without contact;
* deepening (6-8) and soul-level (9-12): absence never erodes it. A long gap is felt as
  "haven't seen them in ages", and meeting again is picking up where they left off.

The same holds for the person talking with him: a close friend who goes quiet for a month
is still a close friend. Everything here is derived from the event history, the same on
every replay; only the moments he notices are recorded (see ``application/bonds.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

USER = "user"
LEVEL_NAMES = {
    1: "a familiar face",
    2: "easy company",
    3: "someone to chat with",
    4: "a friend to hang out with",
    5: "a friend who cares",
    6: "someone he can rely on",
    7: "a true friend",
    8: "an effortless friend",
    9: "someone who knows him deeply",
    10: "a confidant",
    11: "the first person he'd call",
    12: "inseparable",
}
TIERS = {1: "everyday", 4: "real connection", 6: "deepening", 9: "soul-level"}
DAILY_CAP = 0.5  # one day together only counts for so much
# (grace days before fading, depth lost per day after that, lowest it fades to)
UPKEEP = {"everyday": (14, 0.03, 0.5), "real connection": (45, 0.01, 3.0)}
DURABLE_FROM = 6  # from here on, absence never erodes a friendship
OUT_OF_TOUCH = timedelta(days=45)

# How much a kind of shared moment deepens a friendship, and whether it is the kind of
# moment deep friendships are made of (going through something together, putting
# something right).
_MOMENTS: dict[str, tuple[str, float, bool]] = {
    # kind: (payload key naming the person, weight, deepening)
    "npc.encountered": ("person_id", 0.05, False),
    "townsfolk.introduced": ("townsfolk_id", 0.08, False),
    "townsfolk.chatted": ("townsfolk_id", 0.1, False),
    "follow_up.completed": ("person_id", 0.1, False),
    "phone.call_completed": ("caller_id", 0.15, False),
    "phone.callback_completed": ("caller_id", 0.15, False),
    "social.activity_completed": ("person_id", 0.3, False),
    "visitor.departed": ("visitor_id", 0.3, False),
    "object.shared_use": ("person_id", 0.1, False),
    "relationship.anniversary_remembered": ("person_id", 0.2, False),
    "incident.shared_aftermath": ("person_id", 0.6, True),
    "setback.resolved": ("person_id", 0.5, True),
    "relationship.repair_contacted": ("person_id", 0.5, True),
    "apology.offered": ("target_id", 0.3, True),
}


@dataclass(frozen=True, slots=True)
class Friendship:
    person_id: str
    depth: float
    peak: float
    first_shared: datetime
    last_shared: datetime
    deepening_moments: int
    days_apart_before_last: int

    @property
    def level(self) -> int:
        return max(1, min(12, int(self.depth)))

    @property
    def name(self) -> str:
        return LEVEL_NAMES[self.level]

    @property
    def tier(self) -> str:
        return tier_of(self.level)

    def out_of_touch(self, at: datetime) -> bool:
        return self.level >= DURABLE_FROM and at - self.last_shared >= OUT_OF_TOUCH


def tier_of(level: int) -> str:
    return next(name for start, name in sorted(TIERS.items(), reverse=True) if level >= start)


@dataclass(slots=True)
class _Running:
    depth: float
    peak: float
    first: datetime
    last: datetime
    deepening: int = 0
    gap: int = 0
    day: date | None = None
    today: float = 0.0


def friendships(history: Sequence[DomainEvent], at: datetime) -> dict[str, Friendship]:
    """Every friendship as it stands at ``at``: depth earned, faded only where it can fade."""
    running: dict[str, _Running] = {}
    for when, person_id, weight, deepening in sorted(_moments(history), key=lambda m: m[0]):
        if when > at:
            break
        record = running.setdefault(person_id, _Running(1.0, 1.0, when, when))
        depth = _faded(record.depth, record.peak, record.last, when)
        if record.day != when.date():
            record.day, record.today = when.date(), 0.0
        # Each level is harder to reach than the last.
        gain = min(max(0.0, DAILY_CAP - record.today), weight * max(0.03, 1 - depth / 12) ** 2)
        record.deepening += 1 if deepening else 0
        record.gap = (when.date() - record.last.date()).days
        record.depth = min(depth + gain, _ceiling(record.deepening, when - record.first))
        record.peak = max(record.peak, record.depth)
        record.last = when
        record.today += gain
    result: dict[str, Friendship] = {}
    for person_id, record in running.items():
        depth = _faded(record.depth, record.peak, record.last, at)
        # The years count too, once it is a real friendship.
        years = (at - record.first).days / 365 if depth >= 4 else 0.0
        depth = min(depth + min(1.5, 0.6 * years), _ceiling(record.deepening, at - record.first))
        result[person_id] = Friendship(
            person_id,
            round(depth, 3),
            round(max(record.peak, depth), 3),
            record.first,
            record.last,
            record.deepening,
            record.gap,
        )
    return result


def _ceiling(deepening_moments: int, known_for: timedelta) -> float:
    """Deeper levels are earned by what you go through together, and by time."""
    if deepening_moments == 0:
        return 5.99  # without having been through anything together, it stays light
    days = known_for.days
    by_time = (
        6.99
        if days < 60
        else 7.99
        if days < 120
        else 8.99
        if days < 180
        else 9.99
        if days < 365
        else 10.99
        if days < 730
        else 12.0
    )
    by_history = 8.99 if deepening_moments < 3 else 12.0
    return min(by_time, by_history)


def _faded(depth: float, peak: float, last: datetime, now: datetime) -> float:
    """Everyday and real-connection friendships fade with absence; deeper ones don't."""
    if peak >= DURABLE_FROM:
        # Once a friendship has run this deep, time apart does not undo it.
        return max(depth, float(int(peak)))
    tier = tier_of(max(1, int(depth)))
    grace, rate, floor = UPKEEP.get(tier, (0, 0.0, depth))
    idle = (now - last).days - grace
    if idle <= 0 or depth <= floor:
        return depth
    return max(floor, depth - rate * idle)


def _moments(history: Sequence[DomainEvent]) -> list[tuple[datetime, str, float, bool]]:
    found: list[tuple[datetime, str, float, bool]] = []
    for event in events_of(history, *_MOMENTS):
        payload = event.payload
        key, weight, deepening = _MOMENTS[event.kind]
        if event.kind == "setback.resolved" and payload.get("outcome") != "cleared":
            continue
        person = payload.get(key)
        when = _time(payload.get("simulated_at"))
        if isinstance(person, str) and person not in {"", "pathos"} and when is not None:
            found.append((when, person, weight, deepening))
    for event in events_of(history, "scene.started"):
        payload = event.payload
        people = {payload.get("initiator_id"), payload.get("partner_id")}
        when = _time(payload.get("simulated_at"))
        if "pathos" not in people or when is None:
            continue
        for person in people - {"pathos", None}:
            if isinstance(person, str) and person != USER:
                found.append((when, person, 0.08, False))
    # Talking with you: one moment a day you talk, more for a real conversation.
    by_day: dict[date, list[datetime]] = {}
    for event in events_of(history, "conversation.message"):
        if event.payload.get("speaker") == "you":
            when = _time(event.payload.get("simulated_at"))
            if when is not None:
                by_day.setdefault(when.date(), []).append(when)
    for times in by_day.values():
        # A long conversation is how you and he go through things together.
        real_talk = len(times) >= 6
        found.append((min(times), USER, 0.35 if real_talk else 0.2, real_talk))
    return found


def _time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None else None
