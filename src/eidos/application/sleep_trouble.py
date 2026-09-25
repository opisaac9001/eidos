"""Lying awake.

When something is weighing on him (Dad in hospital, a falling-out, a break-up, money
tight, a low patch), some nights he can't get off to sleep, or wakes at three and can't
get back. And the night before something big (a wedding, moving day, a first date, going
away) he lies there too, for better reasons. He's more tired the next day, and he
remembers the night the way people do: the ceiling, the same thought going round.

At most twice a week; the rest is the normal business of sleep, handled elsewhere.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.bookings import remember
from eidos.application.masking import what_is_weighing
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

KIND = "sleep.restless"
HOUR = 2
WORRIED_CHANCE = 0.35
MONEY_CHANCE = 0.12  # money worry is a low hum, not a nightly event
WORRIES = (
    "Woke at three and couldn't get back off. {what} The same thought going round and round "
    "until the birds started.",
    "Lay awake for hours. {what} Kept turning the pillow over like that would help.",
    "Couldn't switch my head off. {what} Gave up at five and made tea.",
)
EXCITED_CHANCE = 0.5
PER_WEEK = 2
REST_COST = 0.12
BIG_DAYS = frozenset({"moving_house", "on_holiday", "visiting_a_friend"})


def sleep_trouble_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    asleep: bool,
    rest: float,
    valence: float,
    money_tight: bool,
    tomorrow: Sequence[tuple[str, str]],
) -> list[DomainEvent]:
    """At two in the morning: is he lying awake? ``tomorrow`` is (title, activity type)."""
    if at.hour != HOUR or not asleep:
        return []
    week = at.isocalendar()[:2]
    recent = [
        e
        for e in events_of(history, KIND)[-PER_WEEK:]
        if datetime.fromisoformat(str(e.payload["simulated_at"])).isocalendar()[:2] == week
    ]
    if len(recent) >= PER_WEEK:
        return []
    night = at.date().isoformat()
    big = next(
        (
            title
            for title, activity in tomorrow
            if activity in BIG_DAYS or "wedding" in title.lower() or "evening with" in title.lower()
        ),
        None,
    )
    if big is not None and _roll("excited", night) < EXCITED_CHANCE:
        text = (
            f"Couldn't sleep for thinking about tomorrow: {big[:1].lower() + big[1:]}. Lay there "
            "like a kid on Christmas Eve."
        )
        return _restless("excited", text, at, rest)
    weighing = what_is_weighing(history, at, valence)
    chance = WORRIED_CHANCE
    if weighing is None and money_tight:
        weighing, chance = "Money. Going over the numbers again, as if they'd change.", MONEY_CHANCE
    if weighing is not None and _roll("worried", night) < chance:
        text = WORRIES[int(_roll("how", night) * len(WORRIES))].format(what=weighing)
        return _restless("worried", text, at, rest)
    return []


def _restless(why: str, text: str, at: datetime, rest: float) -> list[DomainEvent]:
    event = DomainEvent(
        KIND,
        "pathos",
        {"why": why, "text": text, "simulated_at": at.isoformat(), "owner": "pathos"},
        correlation_id=f"restless-{at.date().isoformat()}",
    )
    tired = DomainEvent(
        "needs.changed",
        "pathos",
        {
            "rest": round(max(0.0, rest - REST_COST), 4),
            "reason": "a restless night",
            "simulated_at": at.isoformat(),
        },
        causation_id=event.event_id,
        correlation_id=event.correlation_id,
    )
    return [
        event,
        tired,
        remember(event, text, at, 0.35, origin="lived-sleep", category="experience"),
    ]


def restless_lately(history: Sequence[DomainEvent], at: datetime) -> int:
    """Restless nights in the last week."""
    since = at - timedelta(days=7)
    return sum(
        1
        for e in events_of(history, KIND)[-7:]
        if datetime.fromisoformat(str(e.payload["simulated_at"])) >= since
    )


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
