"""Build a bounded subjective choice field without granting action authority.

The world and body supply pressures. Attention admits only a few of them. A later
agency model may choose, reshape, defer or ignore every attended impulse. Stable
variation breaks exact score ties without rerolling the same decision on replay.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState


def attended_impulses(
    history: Sequence[DomainEvent],
    *,
    decision_id: str,
    planning: PlanningState,
    needs: Mapping[str, float],
    emotion: Mapping[str, object],
    traits: Mapping[str, float],
    workspace: Sequence[Mapping[str, object]],
    opportunities: Sequence[Mapping[str, object]],
    preparation: Mapping[str, object],
    time_budget: Mapping[str, object],
    current_location_id: str | None,
    possible_selves: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Return what reaches deliberation, not an omniscient list of all possibilities."""
    energy = _level(needs, "energy", 0.5)
    rest = _level(needs, "rest", 0.5)
    arousal = _level(emotion, "arousal", 0.35)
    follow_through = _level(traits, "follow_through", 0.64)
    sociability = _level(traits, "sociability", 0.52)
    openness = _level(traits, "openness", 0.68)
    impulses: list[dict[str, object]] = []

    def add(
        impulse_id: str,
        kind: str,
        description: str,
        pull: float,
        friction: float,
        source: str,
        *,
        target_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        if any(item["impulse_id"] == impulse_id for item in impulses):
            return
        settled = max(0.0, min(1.0, pull - friction))
        # Replay-stable variability is subordinate to causal pressure. It prevents
        # deterministic alphabetical ties, not arbitrary actions from nowhere.
        digest = sha256(f"{decision_id}:{impulse_id}".encode()).digest()
        variability = (int.from_bytes(digest[:2], "big") / 65535 - 0.5) * 0.1
        impulses.append(
            {
                "impulse_id": impulse_id,
                "kind": kind,
                "description": description,
                "target_id": target_id,
                "felt_pull": round(max(0.0, min(1.0, pull)), 3),
                "felt_friction": round(max(0.0, min(1.0, friction)), 3),
                "attention_strength": round(max(0.0, min(1.0, settled + variability)), 3),
                "source": source,
                "action_authority": False,
                **(dict(metadata) if metadata is not None else {}),
            }
        )

    latest_execution = next(
        (
            event
            for event in reversed(history)
            if event.aggregate_id == "pathos" and event.kind.startswith("activity.execution_")
        ),
        None,
    )
    ongoing = (
        latest_execution
        if latest_execution is not None
        and latest_execution.kind in {"activity.execution_started", "activity.execution_resumed"}
        and planning.calendar.get(str(latest_execution.payload.get("schedule_id"))) is not None
        and planning.calendar[str(latest_execution.payload.get("schedule_id"))].status
        == "scheduled"
        else None
    )
    if ongoing is not None:
        add(
            f"continue:{ongoing.payload.get('schedule_id')}",
            "continuation",
            f"Stay with {ongoing.payload.get('title', 'what I am already doing')}",
            0.58 + 0.28 * follow_through,
            0.08,
            "current_momentum",
            target_id=str(ongoing.payload.get("schedule_id")),
        )

    free = time_budget.get("free_minutes")
    if time_budget.get("next_plan") is not None:
        free_minutes = float(str(free)) if free is not None else 120.0
        urgency = 1 - min(1.0, max(0.0, free_minutes) / 120)
        add(
            f"protect:{time_budget.get('schedule_id')}",
            "prospective",
            f"Protect enough time to reach {time_budget['next_plan']}",
            0.5 + 0.45 * urgency + 0.08 * follow_through,
            0.04,
            "accepted_plan",
            target_id=str(time_budget.get("schedule_id")),
        )

    need_specs = (
        ("hunger", _level(needs, "hunger", 0.0), "Find something to eat", 0.12),
        ("rest", 1 - rest, "Rest or remain still", 0.08),
        (
            "connection",
            1 - _level(needs, "connection", 0.5),
            "Seek some kind of contact",
            0.18 - 0.1 * sociability,
        ),
        (
            "curiosity",
            1 - _level(needs, "curiosity", 0.5),
            "Follow something interesting",
            0.22 - 0.12 * openness,
        ),
        ("mastery", 1 - _level(needs, "mastery", 0.5), "Make progress on something", 0.2),
    )
    for key, pressure, description, base_friction in need_specs:
        if pressure >= 0.3:
            add(
                f"need:{key}",
                "need",
                description,
                0.25 + 0.68 * pressure,
                base_friction + 0.22 * (1 - energy),
                "felt_need",
                target_id=key,
            )

    optional_scales = preparation.get("optional_scales")
    if isinstance(optional_scales, Sequence) and optional_scales:
        first = optional_scales[0]
        if isinstance(first, Mapping):
            add(
                "household:dishes",
                "domestic",
                "Deal with some of the dishes, at whatever scale actually fits",
                0.48 + 0.22 * _level(needs, "household_dishes", 0.5),
                0.12 + 0.25 * (1 - energy),
                "noticed_home",
                target_id="dishes",
            )

    for item in opportunities[-4:]:
        text = item.get("text")
        opportunity_id = item.get("opportunity_id")
        if isinstance(text, str) and isinstance(opportunity_id, str):
            pull = 0.48 + 0.18 * openness
            if item.get("kind") == "public_happening":
                # Something on in town pulls harder when he is short of company, and as it
                # gets close enough to actually go.
                hours_away = item.get("starts_in_hours")
                soon = isinstance(hours_away, (int, float)) and hours_away <= 12
                pull = (
                    0.44
                    + 0.14 * openness
                    + 0.3 * sociability * (1 - _level(needs, "connection", 0.5))
                    + (0.08 if soon else 0.0)
                )
            add(
                f"opportunity:{opportunity_id}",
                "opportunity",
                text[:180],
                pull,
                0.16 + 0.18 * (1 - energy),
                "noticed_opportunity",
                target_id=opportunity_id,
            )

    for item in workspace[-5:]:
        content = item.get("content")
        source_id = item.get("source_event_id")
        salience = item.get("salience", 0.5)
        if not isinstance(content, str) or not isinstance(source_id, str):
            continue
        value = float(salience) if isinstance(salience, (int, float)) else 0.5
        add(
            f"thought:{source_id}",
            "thought",
            content[:180],
            0.28 + 0.58 * max(0.0, min(1.0, value)),
            0.14 + 0.15 * (1 - energy),
            "private_workspace",
            target_id=source_id,
            metadata={
                "workspace_kind": item.get("kind"),
                "epistemic_status": item.get("epistemic_status"),
                "target_type": item.get("target_type"),
                "target_entity_id": item.get("target_id"),
            },
        )

    for item in possible_selves:
        aspiration_id = item.get("aspiration_id")
        text = item.get("text")
        if not isinstance(aspiration_id, str) or not isinstance(text, str):
            continue
        held = _level(item, "value_level", 0.7)
        # Drifting from who he hopes to be pulls harder than living up to it already.
        lived, strayed = item.get("lived", 0), item.get("strayed", 0)
        lagging = (
            0.12 if isinstance(lived, int) and isinstance(strayed, int) and strayed > lived else 0.0
        )
        hoped = item.get("kind") == "hoped"
        add(
            f"aspiration:{aspiration_id}",
            "aspiration",
            (
                f"Do something that fits who I want to be: {text}"
                if hoped
                else f"Do something that keeps me from becoming what I fear: {text}"
            )[:180],
            0.26 + 0.34 * held + lagging,
            0.18 + 0.2 * (1 - energy),
            "possible_self",
            target_id=aspiration_id,
            metadata={
                "value_id": item.get("value_id"),
                "epistemic_status": "possible_self",
            },
        )

    add(
        "quiet:none",
        "inaction",
        "Do not make a new plan; wait, continue idling, or let the moment pass",
        0.24 + 0.38 * (1 - energy) + 0.16 * (1 - rest),
        0.02,
        "behavioral_inertia",
    )

    previous = next(
        (
            event
            for event in reversed(history)
            if event.kind == "agency.impulses_attended" and event.aggregate_id == "pathos"
        ),
        None,
    )
    previous_ids = (
        {
            str(previous.payload[f"attended_impulse_{index}"])
            for index in range(1, int(previous.payload.get("attended_count", 0)) + 1)
            if f"attended_impulse_{index}" in previous.payload
        }
        if previous
        else set()
    )
    for item in impulses:
        if item["impulse_id"] in previous_ids:
            item["attention_strength"] = round(
                min(1.0, float(str(item["attention_strength"])) + 0.1), 3
            )
            item["inertial_carryover"] = True

    capacity = 3 if energy < 0.3 or arousal > 0.75 else 4
    ranked = sorted(
        impulses,
        key=lambda item: (float(str(item["attention_strength"])), str(item["impulse_id"])),
        reverse=True,
    )
    selected = ranked[:capacity]
    return {
        "attended_impulses": selected,
        "attention_capacity": capacity,
        "current_location_id": current_location_id,
        "action_authority": False,
        "meaning": (
            "These are the few possibilities currently reaching awareness, not commands or a complete "
            "menu. Strength is felt pull after friction, not a probability or winner. Patrick may reshape "
            "one, continue what he is doing, defer all of them, wait, or do nothing. Unattended possibilities "
            "are not available to this decision. Do not maximize a score or invent an accomplished result."
        ),
    }


def impulse_attention_event(
    field: Mapping[str, object], decision_id: str, source: DomainEvent, simulated_at: datetime
) -> DomainEvent:
    attended = field.get("attended_impulses", ())
    items = (
        [item for item in attended if isinstance(item, Mapping)]
        if isinstance(attended, (list, tuple))
        else []
    )
    scalar_items: dict[str, object] = {}
    for index, item in enumerate(items, 1):
        scalar_items.update(
            {
                f"attended_impulse_{index}": str(item.get("impulse_id", "unknown")),
                f"attended_kind_{index}": str(item.get("kind", "unknown")),
                f"attended_description_{index}": str(item.get("description", "")),
                f"attended_strength_{index}": float(item.get("attention_strength", 0)),
                f"attended_friction_{index}": float(item.get("felt_friction", 0)),
            }
        )
    return DomainEvent(
        "agency.impulses_attended",
        "pathos",
        {
            "decision_id": decision_id,
            "source_event_id": str(source.event_id),
            "attended_count": len(items),
            **scalar_items,
            "attention_capacity": field.get("attention_capacity"),
            "simulated_at": simulated_at.isoformat(),
            "action_authority": False,
        },
        causation_id=source.event_id,
        correlation_id=decision_id,
    )


def volition_snapshot(history: Sequence[DomainEvent]) -> dict[str, object] | None:
    attended = next(
        (
            event
            for event in reversed(history)
            if event.aggregate_id == "pathos" and event.kind == "agency.impulses_attended"
        ),
        None,
    )
    if attended is None:
        return None
    count = int(attended.payload.get("attended_count", 0))
    choice = next(
        (
            event
            for event in reversed(history)
            if event.kind == "agency.choice_made"
            and event.correlation_id == attended.correlation_id
        ),
        None,
    )
    chosen = next(
        (
            event
            for event in reversed(history)
            if event.kind == "agency.impulse_chosen"
            and event.correlation_id == attended.correlation_id
        ),
        None,
    )
    return {
        "decision_id": attended.payload.get("decision_id"),
        "simulated_at": attended.payload.get("simulated_at"),
        "impulses": [
            {
                "id": attended.payload.get(f"attended_impulse_{index}"),
                "kind": attended.payload.get(f"attended_kind_{index}"),
                "description": attended.payload.get(f"attended_description_{index}"),
                "strength": attended.payload.get(f"attended_strength_{index}"),
                "friction": attended.payload.get(f"attended_friction_{index}"),
            }
            for index in range(1, count + 1)
        ],
        "chosen_impulse_id": chosen.payload.get("impulse_id") if chosen else None,
        "stated_intention": chosen.payload.get("stated_intention") if chosen else None,
        "choice": choice.payload.get("decision")
        if choice
        else "forming_plan"
        if chosen
        else "deliberating",
        "action_authority": False,
    }


def _level(values: Mapping[str, object], key: str, default: float) -> float:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(0.0, min(1.0, float(value)))
