"""Derive bounded development events from authoritative repeated behavior."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.development import Habit, project_development
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of, kind_index


def development_events(history: Sequence[DomainEvent], simulated_at: str) -> list[DomainEvent]:
    index = kind_index(history)
    processed = {
        str(event.payload["source_event_id"])
        for event in index.select(
            "skill.practiced", "habit.formed", "habit.reinforced", "habit.reactivated"
        )
        if isinstance(event.payload.get("source_event_id"), str)
    }
    at = _time(simulated_at)
    output: list[DomainEvent] = []
    for source in index.select(*_SKILL_EVIDENCE_KINDS):
        source_id = str(source.event_id)
        if source_id in processed:
            continue
        skill_id = _skill_evidence(source)
        if skill_id is None:
            continue
        state = project_development([*history, *output])
        current = state.skills.get(skill_id)
        if current is None and len(state.skills) >= 12:
            continue
        practiced_at = _source_time(source) or at
        if practiced_at > at or (
            current is not None
            and _optional_time(current.last_practiced_at) is not None
            and practiced_at <= _required_skill_time(current.last_practiced_at)
        ):
            continue
        delta = _skill_delta(current.level if current is not None else None)
        output.append(
            DomainEvent(
                "skill.practiced",
                "pathos",
                {
                    "skill_id": skill_id,
                    "revision": 1 if current is None else current.revision + 1,
                    "delta": delta,
                    "source_event_id": source_id,
                    "source_kind": source.kind,
                    "practiced_at": practiced_at.isoformat(),
                    "owner": "pathos",
                    "simulated_at": simulated_at,
                },
                causation_id=source.event_id,
                correlation_id=source.correlation_id or f"skill:{skill_id}",
            )
        )
        processed.add(source_id)
    if at.hour == 19:
        state = project_development([*history, *output])
        rust_candidates = [
            skill
            for skill in state.skills.values()
            if skill.last_practiced_at is not None
            and skill.updated_at is not None
            and skill.level > 0.1
            and at - _required_skill_time(skill.last_practiced_at) >= timedelta(days=90)
            and at - _required_skill_time(skill.updated_at) >= timedelta(days=30)
        ]
        if rust_candidates:
            skill = min(
                rust_candidates,
                key=lambda item: (_required_skill_time(item.last_practiced_at), item.skill_id),
            )
            output.append(
                DomainEvent(
                    "skill.rusted",
                    "pathos",
                    {
                        "skill_id": skill.skill_id,
                        "revision": skill.revision + 1,
                        "amount": 0.03,
                        "reason": "Long disuse made this ability less immediately fluent.",
                        "owner": "pathos",
                        "simulated_at": simulated_at,
                    },
                    correlation_id=f"skill:{skill.skill_id}",
                )
            )
    cafe_visits = [
        event
        for event in index.select("memory.recorded")
        if event.payload.get("source") == "authored-routine"
        and (
            event.payload.get("activity") == "morning_cafe"
            or event.payload.get("text") == "Visited the cafe before work."
        )
    ]
    if len(cafe_visits) >= 3:
        source = cafe_visits[-1]
        source_id = str(source.event_id)
        if source_id not in processed:
            output.append(
                DomainEvent(
                    "habit.reinforced",
                    "pathos",
                    {
                        "habit_id": "morning-cafe-visit",
                        "delta": 0.025,
                        "source_event_id": source_id,
                        "owner": "pathos",
                        "simulated_at": simulated_at,
                    },
                    causation_id=source.event_id,
                    correlation_id="habit-morning-cafe-visit",
                )
            )
    output.extend(behavioral_habit_events([*history, *output], at))
    return output


def behavioral_habit_events(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[DomainEvent]:
    """Form, strengthen, lapse, or revive one contextual rhythm at an evening review."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Habit review time must be timezone-aware")
    if simulated_at.hour != 19:
        return []
    state = project_development(history)
    rich_habits = {
        habit_id: habit
        for habit_id, habit in state.habits.items()
        if habit.activity_type is not None
    }
    lapse_candidates = [
        habit
        for habit in rich_habits.values()
        if habit.status == "active"
        and _optional_time(habit.last_evidence_at) is not None
        and simulated_at - _required_habit_time(habit.last_evidence_at) >= timedelta(days=45)
        and simulated_at - _required_habit_time(habit.updated_at) >= timedelta(days=14)
    ]
    if lapse_candidates:
        habit = max(lapse_candidates, key=lambda item: (item.strength, item.habit_id))
        return [
            DomainEvent(
                "habit.lapsed",
                "pathos",
                {
                    "habit_id": habit.habit_id,
                    "revision": habit.revision + 1,
                    "reason": "This rhythm has not recurred for forty-five simulated days.",
                    "simulated_at": simulated_at.isoformat(),
                    "owner": "pathos",
                },
                correlation_id=habit.habit_id,
            )
        ]

    grouped: dict[tuple[str, str, str], list[DomainEvent]] = defaultdict(list)
    # _habit_signature is None for every other kind.
    for event in events_of(history, "agency.activity_realized"):
        signature = _habit_signature(event)
        age = simulated_at - _event_time(event) if signature is not None else None
        if signature is not None and age is not None and timedelta(0) <= age <= timedelta(days=60):
            grouped[signature].append(event)
    candidates: list[tuple[int, str, str, Habit | None, list[DomainEvent]]] = []
    for (activity_type, location_id, time_band), all_sources in grouped.items():
        all_sources.sort(key=lambda event: (_event_time(event), str(event.event_id)))
        # Repeating an activity several times today is still one day's evidence
        # for a sustained rhythm. Keep the latest source per day deterministically.
        by_day = {_event_time(event).date(): event for event in all_sources}
        all_sources = list(by_day.values())
        habit_id = f"habit:{activity_type}:{location_id}:{time_band}"
        prior = rich_habits.get(habit_id)
        threshold = 3
        sources = all_sources
        if prior is not None:
            updated_at = _required_habit_time(prior.updated_at)
            if simulated_at - updated_at < timedelta(days=14):
                continue
            cutoff = (
                updated_at
                if prior.status == "lapsed"
                else _required_habit_time(prior.last_evidence_at)
            )
            sources = [event for event in sources if _event_time(event) > cutoff]
            threshold = 2 if prior.status == "lapsed" else 3
        if len(sources) < threshold:
            continue
        if _event_time(sources[-1]) - _event_time(sources[0]) < timedelta(days=7):
            continue
        candidates.append((len(sources), activity_type, habit_id, prior, sources))
    if not candidates:
        return []
    _, activity_type, habit_id, prior, sources = max(
        candidates, key=lambda item: (item[0], item[1], item[2])
    )
    selected = sources if len(sources) <= 8 else [sources[0], *sources[-7:]]
    latest = selected[-1]
    signature = _habit_signature(latest)
    if signature is None:
        return []
    _, location_id, time_band = signature
    kind = (
        "habit.formed"
        if prior is None
        else "habit.reactivated"
        if prior.status == "lapsed"
        else "habit.reinforced"
    )
    delta = 0.1 if prior is None else 0.08 if prior.status == "lapsed" else 0.05
    selected_event = DomainEvent(
        kind,
        "pathos",
        {
            "habit_id": habit_id,
            "revision": 1 if prior is None else prior.revision + 1,
            "activity_type": activity_type,
            "location_id": location_id,
            "time_band": time_band,
            "delta": delta,
            "source_count": len(selected),
            "source_event_id": str(latest.event_id),
            **{
                f"source_event_{position}": str(source.event_id)
                for position, source in enumerate(selected, 1)
            },
            "owner": "pathos",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=latest.event_id,
        correlation_id=habit_id,
    )
    output = [selected_event]
    competitors: list[tuple[Habit, list[DomainEvent]]] = []
    for other_id, habit in rich_habits.items():
        if (
            other_id == habit_id
            or habit.status != "active"
            or habit.time_band != time_band
            or _optional_time(habit.updated_at) is None
            or simulated_at - _required_habit_time(habit.updated_at) < timedelta(days=14)
        ):
            continue
        competing_sources = [
            source
            for source in sources
            if _event_time(source) > _required_habit_time(habit.updated_at)
        ]
        if len(competing_sources) < 3 or (
            _event_time(competing_sources[-1]) - _event_time(competing_sources[0])
            < timedelta(days=7)
        ):
            continue
        competitors.append((habit, competing_sources))
    if competitors:
        displaced, displacement_sources = max(
            competitors, key=lambda item: (item[0].strength, item[0].habit_id)
        )
        displacement_sources = (
            displacement_sources
            if len(displacement_sources) <= 8
            else [displacement_sources[0], *displacement_sources[-7:]]
        )
        displacement_latest = displacement_sources[-1]
        output.append(
            DomainEvent(
                "habit.weakened",
                "pathos",
                {
                    "habit_id": displaced.habit_id,
                    "revision": displaced.revision + 1,
                    "competing_habit_id": habit_id,
                    "amount": 0.05,
                    "source_count": len(displacement_sources),
                    "source_event_id": str(displacement_latest.event_id),
                    **{
                        f"source_event_{position}": str(source.event_id)
                        for position, source in enumerate(displacement_sources, 1)
                    },
                    "reason": "A different lived rhythm repeatedly occupied the same part of day.",
                    "owner": "pathos",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=displacement_latest.event_id,
                correlation_id=displaced.habit_id,
            )
        )
    return output


def active_habit_context(history: Sequence[DomainEvent]) -> list[dict[str, object]]:
    """Expose active learned rhythms as influences, never scheduled obligations."""
    active = [
        habit
        for habit in project_development(history).habits.values()
        if habit.activity_type is not None and habit.status == "active"
    ]
    return [
        {
            "activity_type": habit.activity_type,
            "location_id": habit.location_id,
            "time_band": habit.time_band,
            "strength": habit.strength,
            "repetitions": habit.repetitions,
            "status": habit.status,
            "authority": "soft_pattern_only",
            "competes_with": [
                other.habit_id
                for other in sorted(active, key=lambda item: (-item.strength, item.habit_id))
                if other.habit_id != habit.habit_id and other.time_band == habit.time_band
            ],
        }
        for habit in active
    ]


def active_skill_context(history: Sequence[DomainEvent]) -> list[dict[str, object]]:
    """Expose demonstrated capability without turning it into permission or certainty."""
    skills = sorted(
        project_development(history).skills.values(),
        key=lambda item: (-item.level, item.skill_id),
    )
    return [
        {
            "skill_id": skill.skill_id,
            "level": skill.level,
            "practice_count": skill.practice_count,
            "status": skill.status,
            "rust_count": skill.rust_count,
            "authority": "capability_signal_only",
        }
        for skill in skills[:12]
    ]


def effective_capability(
    history: Sequence[DomainEvent], skill_id: str, general_mastery: float
) -> float:
    """Blend broad confidence with demonstrated specific ability for feasibility checks."""
    if not 0 <= general_mastery <= 1:
        raise ValueError("General mastery must be between zero and one")
    skill = project_development(history).skills.get(skill_id)
    if skill is None:
        return general_mastery
    return round(max(0.1, min(1.0, 0.4 * general_mastery + 0.6 * skill.level)), 4)


def _habit_signature(event: DomainEvent) -> tuple[str, str, str] | None:
    if event.kind != "agency.activity_realized" or event.aggregate_id != "pathos":
        return None
    activity_type = event.payload.get("activity_type")
    location_id = event.payload.get("location_id")
    if not isinstance(activity_type, str) or not isinstance(location_id, str):
        return None
    at = _event_time(event)
    band = "morning" if at.hour < 12 else "afternoon" if at.hour < 18 else "evening"
    return activity_type, location_id, band


# The only kinds _skill_evidence can return a skill for.
_SKILL_EVIDENCE_KINDS = (
    "action.accepted",
    "object.repair_attempted",
    "activity.completed",
    "agency.activity_realized",
)


def _skill_evidence(event: DomainEvent) -> str | None:
    if event.aggregate_id != "pathos":
        return None
    if event.kind == "action.accepted" and event.payload.get("action") == "repair":
        return "repair"
    if event.kind == "object.repair_attempted":
        return "repair"
    if (
        event.kind == "activity.completed"
        and event.payload.get("activity") == "work"
        and str(event.payload.get("schedule_id", "")).startswith("work-rota-")
    ):
        # A shift at the repair workshop is practice at repair.
        return "repair"
    if (
        event.kind == "activity.completed"
        and event.payload.get("activity") == "learn"
        and event.payload.get("target_id") == "bookbinding-basics"
    ):
        return "bookbinding"
    if event.kind == "agency.activity_realized" and event.payload.get("action") == "learn":
        activity_type = event.payload.get("activity_type")
        return activity_type if isinstance(activity_type, str) and activity_type else None
    return None


def _source_time(event: DomainEvent) -> datetime | None:
    value = event.payload.get("simulated_at")
    return _time(value) if isinstance(value, str) else None


def _skill_delta(level: float | None) -> float:
    if level is None or level < 0.5:
        return 0.05
    if level < 0.75:
        return 0.03
    return 0.015


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if not isinstance(value, str):
        raise ValueError("Habit evidence needs simulated time")
    return _time(value)


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Habit time must be timezone-aware")
    return parsed


def _optional_time(value: str | None) -> datetime | None:
    return None if value is None else _time(value)


def _required_habit_time(value: str | None) -> datetime:
    parsed = _optional_time(value)
    if parsed is None:
        raise ValueError("Rich habits require lifecycle timestamps")
    return parsed


def _required_skill_time(value: str | None) -> datetime:
    parsed = _optional_time(value)
    if parsed is None:
        raise ValueError("Source-linked skills require lifecycle timestamps")
    return parsed
