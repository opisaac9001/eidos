"""Resident-owned biography that becomes shared knowledge only through disclosure."""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class CharacterFact:
    fact_id: str
    person_id: str
    topic: str
    text: str
    reveal_after_familiarity: float
    source_event_id: str
    status: str = "private"
    disclosed_at: str | None = None
    disclosure_event_id: str | None = None
    scene_id: str | None = None


@dataclass(frozen=True, slots=True)
class CharacterHistory:
    facts: Mapping[str, CharacterFact]

    def __post_init__(self) -> None:
        object.__setattr__(self, "facts", MappingProxyType(dict(self.facts)))

    @classmethod
    def empty(cls) -> CharacterHistory:
        return cls({})

    def apply(self, event: DomainEvent) -> CharacterHistory:
        facts = dict(self.facts)
        if event.kind == "npc.biography_seeded":
            fact_id = _required(event, "fact_id")
            person_id = _required(event, "person_id")
            if fact_id in facts:
                raise ValueError("Character fact already exists")
            if (
                event.payload.get("owner") != person_id
                or event.payload.get("visibility") != "private"
            ):
                raise ValueError("Character facts must begin private to their resident")
            threshold = event.payload.get("reveal_after_familiarity")
            if (
                isinstance(threshold, bool)
                or not isinstance(threshold, (int, float))
                or not 0 <= threshold <= 1
            ):
                raise ValueError("Character disclosure threshold must be between zero and one")
            text = _required(event, "text")
            if len(text) > 360:
                raise ValueError("Character fact text must be at most 360 characters")
            facts[fact_id] = CharacterFact(
                fact_id,
                person_id,
                _required(event, "topic"),
                text,
                float(threshold),
                str(event.event_id),
            )
        elif event.kind == "npc.biography_disclosed":
            fact_id = _required(event, "fact_id")
            if fact_id not in facts:
                raise ValueError("Unknown character fact was disclosed")
            fact = facts[fact_id]
            if fact.status != "private":
                raise ValueError("Character fact was already disclosed")
            if _required(event, "person_id") != fact.person_id:
                raise ValueError("Character fact owner cannot change during disclosure")
            if event.payload.get("audience_id") != "pathos":
                raise ValueError("Character disclosure must be addressed to Pathos")
            facts[fact_id] = replace(
                fact,
                status="disclosed",
                disclosed_at=_required(event, "simulated_at"),
                disclosure_event_id=str(event.event_id),
                scene_id=_required(event, "scene_id"),
            )
        return CharacterHistory(facts)


def project_character_history(events: Sequence[DomainEvent]) -> CharacterHistory:
    state = CharacterHistory.empty()
    prior: list[DomainEvent] = []
    for event in events:
        if event.kind == "npc.biography_disclosed":
            fact_id = _required(event, "fact_id")
            fact = state.facts.get(fact_id)
            source_id = _required(event, "source_turn_event_id")
            turn = next((item for item in prior if str(item.event_id) == source_id), None)
            if fact is None or turn is None or turn.kind != "scene.turn_taken":
                raise ValueError("Character disclosure needs a prior spoken scene turn")
            if (
                turn.event_id != event.causation_id
                or turn.payload.get("actor_id") != fact.person_id
                or turn.payload.get("audience_id") != "pathos"
                or turn.payload.get("scene_id") != event.payload.get("scene_id")
                or fact.text.casefold() not in str(turn.payload.get("text", "")).casefold()
            ):
                raise ValueError("Character disclosure does not match the cited utterance")
        state = state.apply(event)
        prior.append(event)
    return state


def eligible_character_fact(
    events: Sequence[DomainEvent], person_id: str, familiarity: float, scene_id: str
) -> CharacterFact | None:
    if not 0 <= familiarity <= 1:
        raise ValueError("Relationship familiarity must be between zero and one")
    state = project_character_history(events)
    if any(
        fact.status == "disclosed" and fact.scene_id == scene_id for fact in state.facts.values()
    ):
        return None
    return next(
        (
            fact
            for fact in state.facts.values()
            if fact.person_id == person_id
            and fact.status == "private"
            and familiarity >= fact.reveal_after_familiarity
        ),
        None,
    )


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()
