"""Present attentional absorption derived from subjective focus and actual activity."""

from datetime import datetime, timedelta
from typing import Sequence

from eidos.application.activity_execution import _timeline
from eidos.domain.events import DomainEvent
from eidos.domain.mind import CognitiveLayer, project_mind
from eidos.domain.planning import PlanningState


def attention_state(
    history: Sequence[DomainEvent], planning: PlanningState, now: datetime
) -> dict[str, object]:
    if now.utcoffset() is None:
        raise ValueError("Attention state requires timezone-aware time")
    latest_execution = next(
        (
            event
            for _, _, event in reversed(_timeline(history, now))
            if event.aggregate_id == "pathos" and event.kind.startswith("activity.execution_")
        ),
        None,
    )
    working = (
        latest_execution is not None
        and latest_execution.kind in {"activity.execution_started", "activity.execution_resumed"}
        and planning.calendar.get(str(latest_execution.payload.get("schedule_id"))) is not None
        and planning.calendar[str(latest_execution.payload.get("schedule_id"))].status
        == "scheduled"
    )
    pulse = project_mind(history).latest.get(CognitiveLayer.ATTENTION.value)
    pulse_at = datetime.fromisoformat(pulse.simulated_at) if pulse else None
    fresh_pulse = (
        pulse is not None and pulse_at is not None and now - pulse_at <= timedelta(hours=2)
    )
    activation = pulse.activation if fresh_pulse and pulse is not None else 0.35
    if working:
        activation += 0.24
    if latest_execution is not None and latest_execution.kind == "activity.execution_resumed":
        activation -= 0.08
    absorption = max(0.0, min(1.0, activation))
    return {
        "mode": "engrossed"
        if working and absorption >= 0.72
        else "occupied"
        if working
        else "open",
        "absorption": round(absorption, 3),
        "focus_type": pulse.focus_type if fresh_pulse and pulse else None,
        "focus_id": pulse.focus_id if fresh_pulse and pulse else None,
        "working_schedule_id": latest_execution.payload.get("schedule_id") if working else None,
        "action_authority": False,
        "meaning": (
            "Absorption can narrow notice and increase switching cost. It cannot invent work, force "
            "continuation, or prove that Patrick consciously ignored anything."
        ),
    }
