"""How the day and the week feel, from his calendar, the season and his bank balance.

Time isn't neutral to a person. Sunday evening has a low hum of dread when there's work in
the morning; Monday is back to it; Friday afternoon at the bench is nearly the weekend; a
day off with nothing that has to be done feels like space. In autumn it's dark already at
six; in summer the light lasts. The end of the month with not much left is its own mood.
Each is felt once that day, nudges his mood a little, and reaches his passing thoughts.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

FELT = "time.felt"
# Roughly when it gets dark in a small English town, by month (local hour).
_DARK_BY = (16, 17, 18, 20, 20, 21, 21, 20, 19, 18, 16, 16)


def _days_with_work(shift_starts: Iterable[datetime]) -> set[date]:
    return {start.date() for start in shift_starts}


def how_it_feels(
    at: datetime,
    *,
    work_days: set[date],
    balance_pence: int,
    at_work: bool,
) -> list[tuple[str, str, float]]:
    """(kind, his words, tone) for what this hour feels like, if anything in particular."""
    today, tomorrow = at.date(), at.date() + timedelta(days=1)
    yesterday, before = today - timedelta(days=1), today - timedelta(days=2)
    found: list[tuple[str, str, float]] = []
    if today not in work_days and tomorrow in work_days and 17 <= at.hour <= 22:
        found.append(
            ("sunday_feeling", "Work tomorrow. That end-of-weekend feeling.", -0.15)
            if yesterday not in work_days
            else ("sunday_feeling", "Back at the bench tomorrow.", -0.05)
        )
    if (
        today in work_days
        and yesterday not in work_days
        and before not in work_days
        and 7 <= at.hour <= 11
    ):
        found.append(("back_to_it", "Back to it after the days off.", -0.1))
    after = tomorrow + timedelta(days=1)
    weekend_next = tomorrow not in work_days and after not in work_days
    if today in work_days and weekend_next and at_work and 13 <= at.hour <= 16:
        found.append(("nearly_weekend", "Nearly done for the week. Can feel it.", 0.15))
    if today not in work_days and 8 <= at.hour <= 11:
        found.append(("day_off", "Day off. Nothing that has to be done.", 0.15))
    dark = _DARK_BY[at.month - 1]
    if at.month in {10, 11, 12, 1, 2} and at.hour == dark + 1:
        found.append(("dark_early", "Dark already. Proper autumn now.", -0.05))
    if at.month in {6, 7, 8} and 20 <= at.hour <= 21:
        found.append(("light_evening", "Still light out. Proper summer evening.", 0.1))
    if at.day >= 25 and balance_pence < 30_000 and 9 <= at.hour <= 20:
        found.append(("month_end", "End of the month. Counting the pennies.", -0.1))
    return found


def time_feel_events(
    history: list[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    shift_starts: Iterable[datetime],
    balance_pence: int,
    at_work: bool,
) -> list[DomainEvent]:
    """At most one way the time feels this hour, each kind once a day."""
    if not awake:
        return []
    felt_today = {
        str(event.payload.get("feeling"))
        for event in events_of(history, FELT)[-10:]
        if str(event.payload.get("simulated_at", ""))[:10] == at.date().isoformat()
    }
    for kind, text, tone in how_it_feels(
        at,
        work_days=_days_with_work(shift_starts),
        balance_pence=balance_pence,
        at_work=at_work,
    ):
        if kind not in felt_today:
            return [
                DomainEvent(
                    FELT,
                    "pathos",
                    {"feeling": kind, "text": text, "tone": tone, "simulated_at": at.isoformat()},
                )
            ]
    return []


def time_feel_now(history: list[DomainEvent], at: datetime) -> str | None:
    """How the time's been feeling in the last few hours, in his words."""
    for event in reversed(events_of(history, FELT)[-3:]):
        try:
            when = datetime.fromisoformat(str(event.payload["simulated_at"]))
        except (KeyError, ValueError):
            continue
        if timedelta(0) <= at - when <= timedelta(hours=4):
            return str(event.payload.get("text"))
    return None
