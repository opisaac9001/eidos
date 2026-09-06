"""Slow, evidence-linked skill and habit development."""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class Skill:
    skill_id: str
    level: float
    practice_count: int
    last_source_id: str


@dataclass(frozen=True, slots=True)
class Habit:
    habit_id: str
    strength: float
    repetitions: int
    last_source_id: str


@dataclass(frozen=True, slots=True)
class DevelopmentState:
    skills: Mapping[str, Skill]
    habits: Mapping[str, Habit]

    def __post_init__(self) -> None:
        object.__setattr__(self, "skills", MappingProxyType(dict(self.skills)))
        object.__setattr__(self, "habits", MappingProxyType(dict(self.habits)))


def project_development(history: Sequence[DomainEvent]) -> DevelopmentState:
    skills: dict[str, Skill] = {}
    habits: dict[str, Habit] = {}
    used_sources: set[str] = set()
    for event in history:
        if event.kind not in {"skill.practiced", "habit.reinforced"}:
            continue
        source_id = _required(event, "source_event_id")
        if source_id in used_sources:
            raise ValueError("Development evidence cannot be applied twice")
        used_sources.add(source_id)
        delta = _bounded(event, "delta", 0.0, 0.1)
        if event.kind == "skill.practiced":
            skill_id = _required(event, "skill_id")
            current = skills.get(skill_id)
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
    return DevelopmentState(skills, habits)


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
