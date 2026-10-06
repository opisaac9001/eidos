"""Select bounded sleep windows from Pathos's condition and obligations."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
from eidos.domain.sleep import project_sleep_windows
from eidos.domain.state import PathosState


def sleep_window_events(
    history: Sequence[DomainEvent],
    state: PathosState,
    at: datetime,
    planning: PlanningState,
) -> list[DomainEvent]:
    """Choose tonight's sleep once, at the evening planning boundary."""
    if at.utcoffset() is None:
        raise ValueError("Sleep planning time must be timezone-aware")
    night = at.date().isoformat()
    if at.hour != 20 or night in project_sleep_windows(history):
        return []

    reason = "a familiar evening rhythm"
    stable = sha256(night.encode()).digest()[0] % 5
    bedtime_hour = (22, 23, 23, 23, 24)[stable]
    # Tired at the end of a day is ordinary; only real depletion sends him to bed early.
    # (At energy 0.3 this fired nearly every night: 22:00 to 06:00, day in, day out.)
    if state.rest <= 0.35 or state.energy <= 0.12:
        bedtime_hour, reason = 22, "low reserves and a need for recovery"
    elif state.arousal >= 0.7 and state.rest > 0.35:
        bedtime_hour, reason = 24, "a keyed-up mind that may take longer to settle"

    bedtime = at.replace(hour=0) + timedelta(hours=bedtime_hour)
    duration = 9 if state.rest <= 0.35 else 7 if state.rest >= 0.75 else 8

    # A late obligation can delay bedtime. An early one can shorten the window,
    # but never below a safety floor of five hours.
    appointments = []
    for item in planning.calendar.values():
        if item.status not in {"scheduled", "interrupted"} or item.actor_id not in {None, "pathos"}:
            continue
        try:
            starts = datetime.fromisoformat(item.starts_at)
            ends = (
                datetime.fromisoformat(item.ends_at)
                if item.ends_at
                else starts + timedelta(hours=1)
            )
        except ValueError:
            continue
        if at <= starts < at + timedelta(hours=18):
            appointments.append((starts, ends))
    for starts, ends in sorted(appointments):
        if starts <= bedtime < ends:
            bedtime = ends.replace(minute=0, second=0, microsecond=0)
            if ends != bedtime:
                bedtime += timedelta(hours=1)
            reason = "a late commitment followed by protected recovery"

    wake = bedtime + timedelta(hours=duration)
    later = [starts for starts, _ in appointments if starts > bedtime]
    if later:
        ready_by = min(later) - timedelta(hours=1)
        if bedtime + timedelta(hours=5) <= ready_by < wake:
            wake = ready_by.replace(minute=0, second=0, microsecond=0)
            reason = "rest shaped around an early commitment"
    wake = min(wake, bedtime + timedelta(hours=10))
    first = min((starts for starts in later), default=None)
    body = body_clock(night, bedtime, wake, state, first)
    window_id = f"sleep:{night}"
    return [
        DomainEvent(
            "sleep.window_selected",
            "pathos",
            {
                "window_id": window_id,
                "night_date": night,
                "selected_at": at.isoformat(),
                "bedtime": bedtime.isoformat(),
                "wake_at": wake.isoformat(),
                "reason": reason,
                **body,
            },
            correlation_id=window_id,
        )
    ]


ALARM_LEAD = timedelta(hours=3)


def _roll(night: str, what: str) -> float:
    return int.from_bytes(sha256(f"{night}:{what}".encode()).digest()[:6], "big") / float(1 << 48)


def body_clock(
    night: str,
    bedtime: datetime,
    wake: datetime,
    state: PathosState,
    first_commitment: datetime | None,
) -> dict[str, object]:
    """When he really drops off and comes to, and how: a body, not a timetable.

    He drifts off a little before or after he meant to, later when keyed up. With
    somewhere to be soon after, the alarm wakes him (now and then a few minutes before
    it), and some mornings he snoozes. With nowhere to be he sleeps in, longer when he's
    worn down; and a worried mind sometimes wakes him early anyway.
    """
    settle = -20 + _roll(night, "settle") * 50
    if state.arousal >= 0.7:
        settle += 15 + _roll(night, "racing") * 30
    asleep = bedtime + timedelta(minutes=settle)
    snoozes = 0
    if first_commitment is not None and first_commitment - wake <= ALARM_LEAD:
        if _roll(night, "before-alarm") < 0.2:
            up, waking = (
                wake - timedelta(minutes=3 + _roll(night, "early") * 15),
                "just before the alarm",
            )
        else:
            snoozes = (
                2 if _roll(night, "snooze") < 0.12 else 1 if _roll(night, "snooze") < 0.4 else 0
            )
            up = wake + timedelta(minutes=9 * snoozes)
            waking = "to the alarm" if not snoozes else "to the alarm, after snoozing"
        # However long the snoozing, he still has to get there.
        up = min(up, first_commitment - timedelta(minutes=45))
    elif state.arousal >= 0.6 and state.valence < -0.05 and _roll(night, "worry") < 0.35:
        up = wake - timedelta(minutes=20 + _roll(night, "worry-early") * 50)
        waking = "early, his mind already going"
    else:
        lie_in = 5 + _roll(night, "lie-in") * 60
        if state.rest <= 0.35 or bedtime.hour == 0:
            lie_in += 30 + _roll(night, "catch-up") * 50
        up = wake + timedelta(minutes=lie_in)
        waking = "in his own time, a lie-in" if lie_in >= 45 else "in his own time"
    if first_commitment is not None:
        up = min(up, first_commitment - timedelta(minutes=45))
    # Within what a night can be, and never before he's dropped off.
    up = max(asleep + timedelta(hours=5), min(up, asleep + timedelta(hours=11)))
    return {
        "asleep_at": asleep.replace(second=0, microsecond=0).isoformat(),
        "up_at": up.replace(second=0, microsecond=0).isoformat(),
        "waking": waking,
        "snoozes": snoozes,
    }
