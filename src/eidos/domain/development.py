"""Slow, evidence-linked skill and habit development."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Mapping, NamedTuple, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import GrowOnlyMap, IncrementalFold, PersistentMap


@dataclass(frozen=True, slots=True)
class Skill:
    skill_id: str
    level: float
    practice_count: int
    last_source_id: str
    status: str = "active"
    revision: int = 1
    updated_at: str | None = None
    last_practiced_at: str | None = None
    rust_count: int = 0


@dataclass(frozen=True, slots=True)
class Habit:
    habit_id: str
    strength: float
    repetitions: int
    last_source_id: str
    activity_type: str | None = None
    location_id: str | None = None
    time_band: str | None = None
    status: str = "active"
    revision: int = 1
    updated_at: str | None = None
    last_evidence_at: str | None = None


@dataclass(frozen=True, slots=True)
class DevelopmentState:
    skills: Mapping[str, Skill]
    habits: Mapping[str, Habit]

    def __post_init__(self) -> None:
        object.__setattr__(self, "skills", MappingProxyType(dict(self.skills)))
        object.__setattr__(self, "habits", MappingProxyType(dict(self.habits)))


_DEVELOPMENT_KINDS = frozenset(
    {
        "skill.practiced",
        "skill.rusted",
        "habit.formed",
        "habit.reinforced",
        "habit.lapsed",
        "habit.reactivated",
        "habit.weakened",
    }
)


class _DevelopmentFold(NamedTuple):
    state: DevelopmentState
    used_sources: GrowOnlyMap[str, bool]
    seen: PersistentMap[str, DomainEvent]


def _development_result(
    fold: _DevelopmentFold,
    skills: dict[str, Skill],
    habits: dict[str, Habit],
    used_sources: GrowOnlyMap[str, bool],
    event: DomainEvent,
) -> _DevelopmentFold:
    return _DevelopmentFold(
        DevelopmentState(skills, habits),
        used_sources,
        fold.seen.with_item(str(event.event_id), event),
    )


def _development_step(fold: _DevelopmentFold, event: DomainEvent) -> _DevelopmentFold:
    if event.kind not in _DEVELOPMENT_KINDS:
        return fold._replace(seen=fold.seen.with_item(str(event.event_id), event))
    # Development events are rare; copying the small skill and habit maps keeps every
    # earlier fold state immutable.
    skills = dict(fold.state.skills)
    habits = dict(fold.state.habits)
    used_sources = fold.used_sources
    seen = fold.seen
    if event.kind.startswith("skill.") and event.aggregate_id != "pathos":
        raise ValueError("Skills belong to Pathos")
    if event.kind.startswith("habit.") and event.aggregate_id != "pathos":
        raise ValueError("Habits belong to Pathos")
    if event.kind == "skill.rusted":
        skill_id = _required(event, "skill_id")
        current_skill = skills.get(skill_id)
        if current_skill is None or current_skill.last_practiced_at is None:
            raise ValueError("Only a source-linked skill can become rusty")
        revision = _integer(event, "revision")
        if revision != current_skill.revision + 1:
            raise ValueError("Skill revision must be sequential")
        changed_at = _time(event, "simulated_at")
        last_practiced = _parsed(current_skill.last_practiced_at)
        previous_update = _parsed(current_skill.updated_at)
        if last_practiced is None or changed_at - last_practiced < timedelta(days=90):
            raise ValueError("A skill cannot rust before ninety days of disuse")
        if previous_update is None or changed_at - previous_update < timedelta(days=30):
            raise ValueError("Skill rust changes must be at least thirty days apart")
        amount = _bounded(event, "amount", 0.0, 0.05)
        if amount != 0.03:
            raise ValueError("Skill rust uses the bounded monthly amount")
        skills[skill_id] = replace(
            current_skill,
            level=round(max(0.1, current_skill.level - amount), 4),
            status="rusty",
            revision=revision,
            updated_at=changed_at.isoformat(),
            rust_count=current_skill.rust_count + 1,
        )
        return _development_result(fold, skills, habits, used_sources, event)
    if event.kind == "habit.lapsed":
        habit_id = _required(event, "habit_id")
        current_habit = habits.get(habit_id)
        if current_habit is None or current_habit.status != "active":
            raise ValueError("Only an active habit can lapse")
        revision = _integer(event, "revision")
        if revision != current_habit.revision + 1:
            raise ValueError("Habit revision must be sequential")
        changed_at = _time(event, "simulated_at")
        last_evidence = _parsed(current_habit.last_evidence_at)
        if last_evidence is None or changed_at - last_evidence < timedelta(days=45):
            raise ValueError("A habit cannot lapse before forty-five days of disuse")
        habits[habit_id] = replace(
            current_habit,
            status="lapsed",
            strength=round(max(0.1, current_habit.strength - 0.15), 4),
            revision=revision,
            updated_at=changed_at.isoformat(),
        )
        return _development_result(fold, skills, habits, used_sources, event)
    if event.kind == "habit.weakened":
        habit_id = _required(event, "habit_id")
        current_habit = habits.get(habit_id)
        if current_habit is None or current_habit.status != "active":
            raise ValueError("Only an active contextual habit can weaken")
        if current_habit.activity_type is None or current_habit.time_band is None:
            raise ValueError("Only a contextual habit can weaken through competition")
        revision = _integer(event, "revision")
        if revision != current_habit.revision + 1:
            raise ValueError("Habit revision must be sequential")
        changed_at = _time(event, "simulated_at")
        previous_update = _parsed(current_habit.updated_at)
        if previous_update is None or changed_at - previous_update < timedelta(days=14):
            raise ValueError("Habit changes must be at least fourteen days apart")
        amount = _bounded(event, "amount", 0.0, 0.1)
        if amount != 0.05:
            raise ValueError("Competing behavior weakens a habit by the bounded amount")
        source_count = _integer(event, "source_count")
        if not 3 <= source_count <= 8:
            raise ValueError("Habit competition evidence count is outside policy")
        source_ids = [
            _required(event, f"source_event_{position}") for position in range(1, source_count + 1)
        ]
        source_id = _required(event, "source_event_id")
        if len(set(source_ids)) != len(source_ids) or source_id != source_ids[-1]:
            raise ValueError("Habit competition evidence must be distinct and ordered")
        sources = [seen.get(item) for item in source_ids]
        if any(source is None for source in sources):
            raise ValueError("Habit competition evidence must already exist")
        typed_sources = [source for source in sources if source is not None]
        signatures = {_habit_signature(source) for source in typed_sources}
        if len(signatures) != 1 or None in signatures:
            raise ValueError("Habit competition must derive from one alternative rhythm")
        competing_signature = next(iter(signatures))
        if competing_signature is None:
            raise ValueError("Habit competition needs realized behavior")
        activity_type, location_id, time_band = competing_signature
        competing_habit_id = _required(event, "competing_habit_id")
        if competing_habit_id != f"habit:{activity_type}:{location_id}:{time_band}":
            raise ValueError("Competing habit identity must derive from lived behavior")
        if competing_habit_id == habit_id or time_band != current_habit.time_band:
            raise ValueError("Only a different rhythm in the same time band can compete")
        source_times = [_time(source, "simulated_at") for source in typed_sources]
        if len({item.date() for item in source_times}) != len(source_times):
            raise ValueError("Habit competition evidence must come from distinct days")
        if max(source_times) - min(source_times) < timedelta(days=7):
            raise ValueError("Habit competition evidence must span at least one week")
        if min(source_times) <= previous_update:
            raise ValueError("Habit competition requires wholly new behavior")
        if max(source_times) > changed_at or changed_at - min(source_times) > timedelta(days=60):
            raise ValueError("Habit competition evidence must be recent and not future")
        habits[habit_id] = replace(
            current_habit,
            strength=round(max(0.1, current_habit.strength - amount), 4),
            revision=revision,
            updated_at=changed_at.isoformat(),
        )
        return _development_result(fold, skills, habits, used_sources, event)
    source_id = _required(event, "source_event_id")
    rich_habit = event.kind.startswith("habit.") and isinstance(
        event.payload.get("activity_type"), str
    )
    if event.kind in {"habit.formed", "habit.reactivated"} and not rich_habit:
        raise ValueError("Contextual habit events require their lived signature")
    rich_skill = event.kind == "skill.practiced" and isinstance(event.payload.get("revision"), int)
    if source_id in used_sources and not rich_habit:
        raise ValueError("Development evidence cannot be applied twice")
    if not rich_habit:
        used_sources = used_sources.with_item(source_id, True)
    delta = _bounded(event, "delta", 0.0, 0.1)
    if event.kind == "skill.practiced":
        skill_id = _required(event, "skill_id")
        current = skills.get(skill_id)
        if not rich_skill:
            skills[skill_id] = (
                Skill(skill_id, min(1.0, 0.25 + delta), 1, source_id)
                if current is None
                else replace(
                    current,
                    level=min(1.0, current.level + delta),
                    practice_count=current.practice_count + 1,
                    last_source_id=source_id,
                )
            )
        else:
            source = seen.get(source_id)
            if source is None or _skill_signature(source) != skill_id:
                raise ValueError("Skill practice must derive from matching lived evidence")
            revision = _integer(event, "revision")
            if revision != (1 if current is None else current.revision + 1):
                raise ValueError("Skill revision must be sequential")
            practiced_at = _time(event, "practiced_at")
            changed_at = _time(event, "simulated_at")
            source_at = _event_time_if_present(source)
            if source_at is not None and source_at != practiced_at:
                raise ValueError("Skill practice time must match its lived evidence")
            if practiced_at > changed_at:
                raise ValueError("Skill practice cannot come from the future")
            previous_practice = _parsed(current.last_practiced_at) if current else None
            if previous_practice is not None and practiced_at <= previous_practice:
                raise ValueError("Skill practice must be newer than prior evidence")
            if delta != _skill_delta(current.level if current else None):
                raise ValueError("Skill growth must follow the bounded learning curve")
            skills[skill_id] = Skill(
                skill_id=skill_id,
                level=round(min(1.0, (0.25 if current is None else current.level) + delta), 4),
                practice_count=(0 if current is None else current.practice_count) + 1,
                last_source_id=source_id,
                status="active",
                revision=revision,
                updated_at=changed_at.isoformat(),
                last_practiced_at=practiced_at.isoformat(),
                rust_count=0 if current is None else current.rust_count,
            )
    elif not rich_habit:
        habit_id = _required(event, "habit_id")
        current_habit = habits.get(habit_id)
        habits[habit_id] = (
            Habit(habit_id, min(1.0, 0.2 + delta), 1, source_id)
            if current_habit is None
            else replace(
                current_habit,
                strength=min(1.0, current_habit.strength + delta),
                repetitions=current_habit.repetitions + 1,
                last_source_id=source_id,
            )
        )
    else:
        habit_id = _required(event, "habit_id")
        activity_type = _required(event, "activity_type")
        location_id = _required(event, "location_id")
        time_band = _required(event, "time_band")
        if time_band not in {"morning", "afternoon", "evening"}:
            raise ValueError("Habit time band is invalid")
        if habit_id != f"habit:{activity_type}:{location_id}:{time_band}":
            raise ValueError("Habit identity must derive from its lived context")
        current_habit = habits.get(habit_id)
        expected_kind = (
            "habit.formed"
            if current_habit is None
            else "habit.reactivated"
            if current_habit.status == "lapsed"
            else "habit.reinforced"
        )
        if event.kind != expected_kind:
            raise ValueError("Habit event kind does not match its lifecycle")
        revision = _integer(event, "revision")
        if revision != (1 if current_habit is None else current_habit.revision + 1):
            raise ValueError("Habit revision must be sequential")
        source_count = _integer(event, "source_count")
        minimum = 2 if event.kind == "habit.reactivated" else 3
        if not minimum <= source_count <= 8:
            raise ValueError("Habit evidence count is outside policy")
        source_ids = [
            _required(event, f"source_event_{position}") for position in range(1, source_count + 1)
        ]
        if len(set(source_ids)) != len(source_ids) or source_id != source_ids[-1]:
            raise ValueError("Habit evidence must be distinct and end at its latest source")
        sources = [seen.get(item) for item in source_ids]
        if any(source is None for source in sources):
            raise ValueError("Habit evidence must already exist")
        typed_sources = [source for source in sources if source is not None]
        if any(
            _habit_signature(source) != (activity_type, location_id, time_band)
            for source in typed_sources
        ):
            raise ValueError("Habit evidence does not match the claimed rhythm")
        source_times = [_time(source, "simulated_at") for source in typed_sources]
        if len({item.date() for item in source_times}) != len(source_times):
            raise ValueError("Habit evidence must come from distinct days")
        if max(source_times) - min(source_times) < timedelta(days=7):
            raise ValueError("Habit evidence must span at least one week")
        changed_at = _time(event, "simulated_at")
        if max(source_times) > changed_at:
            raise ValueError("Habit evidence cannot come from the future")
        if changed_at - min(source_times) > timedelta(days=60):
            raise ValueError("Habit evidence must be recent")
        if current_habit is not None:
            if (activity_type, location_id, time_band) != (
                current_habit.activity_type,
                current_habit.location_id,
                current_habit.time_band,
            ):
                raise ValueError("A habit revision cannot change its identity")
            previous_update = _parsed(current_habit.updated_at)
            if previous_update is None or changed_at - previous_update < timedelta(days=14):
                raise ValueError("Habit changes must be at least fourteen days apart")
            last_evidence = _parsed(current_habit.last_evidence_at)
            if last_evidence is None or min(source_times) <= last_evidence:
                raise ValueError("Habit reinforcement requires wholly new evidence")
        strength = round(
            min(
                1.0,
                (0.2 if current_habit is None else current_habit.strength) + delta,
            ),
            4,
        )
        expected_delta = (
            0.1
            if event.kind == "habit.formed"
            else 0.08
            if event.kind == "habit.reactivated"
            else 0.05
        )
        if delta != expected_delta:
            raise ValueError("Habit strength change must match its lifecycle")
        habits[habit_id] = Habit(
            habit_id=habit_id,
            strength=strength,
            repetitions=(0 if current_habit is None else current_habit.repetitions) + source_count,
            last_source_id=source_id,
            activity_type=activity_type,
            location_id=location_id,
            time_band=time_band,
            status="active",
            revision=revision,
            updated_at=changed_at.isoformat(),
            last_evidence_at=max(source_times).isoformat(),
        )
        for used_id in source_ids:
            used_sources = used_sources.with_item(used_id, True)
    return _development_result(fold, skills, habits, used_sources, event)


_DEVELOPMENT_FOLD: IncrementalFold[_DevelopmentFold] = IncrementalFold(
    lambda: _DevelopmentFold(DevelopmentState({}, {}), GrowOnlyMap(), PersistentMap()),
    _development_step,
)


def project_development(history: Sequence[DomainEvent]) -> DevelopmentState:
    return _DEVELOPMENT_FOLD(history).state


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _bounded(event: DomainEvent, key: str, lower: float, upper: float) -> float:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    result = float(value)
    if not lower < result <= upper:
        raise ValueError(f"{key} must be greater than {lower} and at most {upper}")
    return result


def _integer(event: DomainEvent, key: str) -> int:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{key} must be a positive integer")
    return value


def _time(event: DomainEvent, key: str) -> datetime:
    value = event.payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError(f"{key} must be timezone-aware")
    return parsed


def _parsed(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Habit state time must be timezone-aware")
    return parsed


def _habit_signature(event: DomainEvent) -> tuple[str, str, str] | None:
    if event.kind != "agency.activity_realized" or event.aggregate_id != "pathos":
        return None
    activity_type = event.payload.get("activity_type")
    location_id = event.payload.get("location_id")
    value = event.payload.get("simulated_at")
    if (
        not isinstance(activity_type, str)
        or not isinstance(location_id, str)
        or not isinstance(value, str)
    ):
        return None
    at = datetime.fromisoformat(value)
    if at.utcoffset() is None:
        return None
    band = "morning" if at.hour < 12 else "afternoon" if at.hour < 18 else "evening"
    return activity_type, location_id, band


def _skill_signature(event: DomainEvent) -> str | None:
    if event.aggregate_id != "pathos":
        return None
    if event.kind == "action.accepted" and event.payload.get("action") == "repair":
        return "repair"
    if event.kind == "object.repair_attempted":
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


def _event_time_if_present(event: DomainEvent) -> datetime | None:
    value = event.payload.get("simulated_at")
    if not isinstance(value, str):
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Skill evidence time must be timezone-aware")
    return parsed


def _skill_delta(level: float | None) -> float:
    if level is None or level < 0.5:
        return 0.05
    if level < 0.75:
        return 0.03
    return 0.015
