"""Patrick's part-time job: an agreement he accepted, and the rota that follows from it.

An ordinary life has a livelihood. Only his explicit choice or an agreement he accepts may
book his time, so the job is recorded first as a standing agreement with Ellis. Shifts are
then published a week ahead, each citing that agreement, the way real rotas are, so his own
plans are made around them rather than colliding with them. A shift is a normal calendar
entry: he has to travel there, be present and awake, and actually put the hours in. Wages
follow only hours he actually worked.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from eidos.application.seasons import workshop_closed
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.planning import PlanningState

SHIFT_WEEKDAYS = frozenset({0, 1, 3, 4})  # Monday, Tuesday, Thursday, Friday.
SHIFT_START_HOUR = 10
SHIFT_END_HOUR = 16
ROTA_HORIZON_DAYS = 7
ROTA_PREFIX = "work-rota-"
AGREEMENT_ID = "workshop-part-time-v1"
EMPLOYER_ID = "ellis"
HOURLY_WAGE_PENCE = 1_100
SHIFT_WAGE_PENCE = HOURLY_WAGE_PENCE * (SHIFT_END_HOUR - SHIFT_START_HOUR)


def current_terms(history: Sequence[DomainEvent]) -> tuple[frozenset[int], int]:
    """(weekdays, hourly wage in pence) under the job as it stands now."""
    weekdays, wage = SHIFT_WEEKDAYS, HOURLY_WAGE_PENCE
    for event in events_of(history, "work.agreement_accepted", "work.terms_changed"):
        if event.payload.get("agreement_id") not in (None, AGREEMENT_ID):
            continue
        raw_days = event.payload.get("weekdays")
        if isinstance(raw_days, str) and raw_days:
            weekdays = frozenset(int(day) for day in raw_days.split(","))
        raw_wage = event.payload.get("hourly_wage_pence")
        if isinstance(raw_wage, int) and not isinstance(raw_wage, bool) and raw_wage > 0:
            wage = raw_wage
    return weekdays, wage


def partial_shift_wage(
    worked_seconds: object, hourly_wage_pence: int = HOURLY_WAGE_PENCE
) -> int | None:
    """Hours actually worked on an unfinished shift, paid to the quarter hour."""
    if isinstance(worked_seconds, bool) or not isinstance(worked_seconds, (int, float)):
        return None
    quarters = int(worked_seconds // 900)
    if quarters < 4:
        return None
    full_shift = hourly_wage_pence * (SHIFT_END_HOUR - SHIFT_START_HOUR)
    return min(full_shift, quarters * hourly_wage_pence // 4)


def work_rota_events(
    history: Sequence[DomainEvent], planning: PlanningState, simulated_at: datetime
) -> list[DomainEvent]:
    """Publish any shift in the coming week that is not yet on his calendar."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Rota time must be timezone-aware")
    if not any(event.kind == "identity.established" for event in history):
        return []
    output: list[DomainEvent] = []
    agreement = next(
        (
            event
            for event in history
            if event.kind == "work.agreement_accepted"
            and event.payload.get("agreement_id") == AGREEMENT_ID
        ),
        None,
    )
    if any(
        event.kind == "work.agreement_ended" and event.payload.get("agreement_id") == AGREEMENT_ID
        for event in history
    ):
        return []
    if agreement is None:
        agreement = DomainEvent(
            "work.agreement_accepted",
            "pathos",
            {
                "agreement_id": AGREEMENT_ID,
                "employer_id": EMPLOYER_ID,
                "location_id": "workshop",
                "weekdays": ",".join(str(day) for day in sorted(SHIFT_WEEKDAYS)),
                "starts_hour": SHIFT_START_HOUR,
                "ends_hour": SHIFT_END_HOUR,
                "hourly_wage_pence": HOURLY_WAGE_PENCE,
                "reason": (
                    "The standing part-time arrangement to help Ellis at the repair "
                    "workshop four days a week."
                ),
                "simulated_at": simulated_at.isoformat(),
            },
            correlation_id=AGREEMENT_ID,
        )
        output.append(agreement)
    weekdays, hourly_wage = current_terms([*history, *output])
    for offset in range(ROTA_HORIZON_DAYS + 1):
        day = (simulated_at + timedelta(days=offset)).date()
        # The workshop shuts on bank holidays and from Christmas Eve to New Year.
        if day.weekday() not in weekdays or workshop_closed(day):
            continue
        schedule_id = f"{ROTA_PREFIX}{day.isoformat()}"
        if schedule_id in planning.calendar:
            continue
        starts = simulated_at.replace(
            year=day.year,
            month=day.month,
            day=day.day,
            hour=SHIFT_START_HOUR,
            minute=0,
            second=0,
            microsecond=0,
        )
        if starts <= simulated_at:
            continue
        ends = starts.replace(hour=SHIFT_END_HOUR)
        if any(
            _overlaps(entry.starts_at, entry.ends_at, starts, ends)
            for entry in planning.calendar.values()
            if entry.status == "scheduled"
        ):
            # Already-accepted plans keep their time; the rota simply has a gap that week.
            continue
        intention_id = f"{schedule_id}-intention"
        output.append(
            DomainEvent(
                "intention.adopted",
                "pathos",
                {
                    "agreement_id": AGREEMENT_ID,
                    "proposal_id": f"rota-{schedule_id}",
                    "intention_id": intention_id,
                    "actor_id": "pathos",
                    "action": "work",
                    "target_id": "workshop",
                    "goal_id": None,
                    "priority": 0.82,
                    "motivation": "It's my shift at the workshop, and Ellis is counting on me.",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=agreement.event_id,
                correlation_id=schedule_id,
            )
        )
        output.append(
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": schedule_id,
                    "agreement_id": AGREEMENT_ID,
                    "intention_id": intention_id,
                    "title": "Shift at the repair workshop",
                    "starts_at": starts.isoformat(),
                    "ends_at": ends.isoformat(),
                    "location_id": "workshop",
                    "actor_id": "pathos",
                    "action": "work",
                    "target_id": "workshop",
                    "resource_id": None,
                    "companion_id": None,
                    "activity_type": "workshop_shift",
                    "hourly_wage_pence": hourly_wage,
                    # A shift is time served, not an open-ended task: no hidden effort.
                    "source": "published-work-rota",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=agreement.event_id,
                correlation_id=schedule_id,
            )
        )
    return output


def is_rota_shift(schedule_id: object) -> bool:
    return isinstance(schedule_id, str) and schedule_id.startswith(ROTA_PREFIX)


def _overlaps(start: str, end: str | None, starts: datetime, ends: datetime) -> bool:
    other_start = datetime.fromisoformat(start)
    other_end = datetime.fromisoformat(end) if end else other_start
    return other_start < ends and starts < other_end
