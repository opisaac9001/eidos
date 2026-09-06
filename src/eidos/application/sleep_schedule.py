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
    if state.rest <= 0.35 or state.energy <= 0.3:
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
            },
            correlation_id=window_id,
        )
    ]
