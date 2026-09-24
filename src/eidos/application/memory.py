"""Explainable autobiographical recall over immutable source events."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping, NamedTuple
from uuid import UUID

from eidos.application.memory_retention import archived_memory_ids
from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, PersistentMap, events_of, kind_index
from eidos.domain.recollections import Recollection, project_recollections

WORDS = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "did",
    "do",
    "for",
    "from",
    "has",
    "have",
    "he",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "the",
    "to",
    "was",
    "we",
    "were",
    "what",
    "where",
    "with",
    "you",
    "your",
}


def terms(text: str) -> set[str]:
    return {word for word in WORDS.findall(text.lower()) if word not in STOP_WORDS}


@dataclass(frozen=True, slots=True)
class RecalledMemory:
    event: DomainEvent
    accessibility: float
    relevance: float
    score: float
    reason: str
    matched_terms: tuple[str, ...]
    matched_entities: tuple[str, ...]
    matched_goals: tuple[str, ...]
    matched_relationships: tuple[str, ...]
    components: Mapping[str, float]
    recalled_text: str
    detail_level: str
    affective_bias: float
    blended_memory_ids: tuple[str, ...]
    correction_evidence_id: str | None
    felt_confidence: float
    source_confidence: float
    confidence_basis: str
    reminder_count: int
    remembered_person_id: str | None
    remembered_location_id: str | None
    remembered_at: datetime
    encoded_valence: float
    encoded_arousal: float
    emotional_label: str
    emotional_intensity: float


_NO_IDS: frozenset[UUID] = frozenset()


class _Postings:
    """Memory ids by key while an index is built, refrozen only where they changed.

    Extending an index hour after hour used to thaw and refreeze every term's ids.
    Keys keep their original order and new keys follow in the order first seen.
    """

    __slots__ = ("_frozen", "_thawed")

    def __init__(self, frozen: dict[str, frozenset[UUID]], thawed: dict[str, set[UUID]]) -> None:
        self._frozen = frozen
        self._thawed = thawed

    @classmethod
    def extending(cls, frozen: Mapping[str, frozenset[UUID]]) -> _Postings:
        return cls(dict(frozen), {})

    @classmethod
    def thawed(cls, values: dict[str, set[UUID]]) -> _Postings:
        return cls(dict.fromkeys(values, _NO_IDS), values)

    def add(self, key: str, memory_id: UUID) -> None:
        ids = self._thawed.get(key)
        if ids is None:
            ids = self._thawed[key] = set(self._frozen.get(key, _NO_IDS))
            self._frozen.setdefault(key, _NO_IDS)
        ids.add(memory_id)

    def freeze(self) -> Mapping[str, frozenset[UUID]]:
        for key, ids in self._thawed.items():
            self._frozen[key] = frozenset(ids)
        return MappingProxyType(self._frozen)


@dataclass(frozen=True, slots=True)
class MemoryIndex:
    """Replay-safe indexes derived only from actor-owned memory events."""

    memories: tuple[DomainEvent, ...]
    terms_by_memory: Mapping[UUID, frozenset[str]]
    by_term: Mapping[str, frozenset[UUID]]
    by_entity: Mapping[str, frozenset[UUID]]
    by_goal: Mapping[str, frozenset[UUID]]
    by_relationship: Mapping[str, frozenset[UUID]]
    access_counts: Mapping[UUID, int]
    reminder_counts: Mapping[UUID, int]
    revision: int

    @classmethod
    def build(
        cls,
        history: list[DomainEvent],
        *,
        materialized_state: Mapping[str, Any] | None = None,
        materialized_revision: int = 0,
        base_index: MemoryIndex | None = None,
    ) -> MemoryIndex:
        if base_index is not None and materialized_state is not None:
            raise ValueError("Choose either an in-memory or materialized memory index base")
        if base_index is not None:
            materialized_revision = base_index.revision
        if not 0 <= materialized_revision <= len(history):
            raise ValueError("Materialized memory revision is outside the supplied history")
        memories: list[DomainEvent]
        term_sets: dict[UUID, frozenset[str]]
        terms_map: _Postings
        entities_map: _Postings
        goals_map: _Postings
        relationships_map: _Postings
        accesses: dict[UUID, int]
        reminders: dict[UUID, int]
        if base_index is not None:
            memories = list(base_index.memories)
            term_sets = dict(base_index.terms_by_memory)
            terms_map = _Postings.extending(base_index.by_term)
            entities_map = _Postings.extending(base_index.by_entity)
            goals_map = _Postings.extending(base_index.by_goal)
            relationships_map = _Postings.extending(base_index.by_relationship)
            accesses = dict(base_index.access_counts)
            reminders = dict(base_index.reminder_counts)
        elif materialized_state is None:
            memories = []
            term_sets = {}
            terms_map = _Postings.thawed({})
            entities_map = _Postings.thawed({})
            goals_map = _Postings.thawed({})
            relationships_map = _Postings.thawed({})
            accesses = {}
            reminders = {}
            materialized_revision = 0
        else:
            (
                memories,
                term_sets,
                restored_terms,
                restored_entities,
                restored_goals,
                restored_relationships,
                accesses,
                reminders,
            ) = cls._restore(history, materialized_state, materialized_revision)
            terms_map = _Postings.thawed(restored_terms)
            entities_map = _Postings.thawed(restored_entities)
            goals_map = _Postings.thawed(restored_goals)
            relationships_map = _Postings.thawed(restored_relationships)

        # Every memory has its terms recorded, so these are the known memories.
        known_memory_ids = set(term_sets)
        for event in history[materialized_revision:]:
            if event.kind == "memory.accessed":
                try:
                    memory_id = UUID(str(event.payload["memory_id"]))
                except (KeyError, ValueError):
                    continue
                if memory_id in known_memory_ids:
                    accesses[memory_id] = accesses.get(memory_id, 0) + 1
                continue
            if event.kind == "memory.reminded":
                try:
                    memory_id = UUID(str(event.payload["memory_id"]))
                except (KeyError, ValueError):
                    continue
                if memory_id in known_memory_ids:
                    reminders[memory_id] = reminders.get(memory_id, 0) + 1
                continue
            if event.kind != "memory.recorded" or event.payload.get("owner", "pathos") != "pathos":
                continue
            if event.event_id in known_memory_ids:
                raise ValueError("Materialized memory index contains a duplicate memory")
            memories.append(event)
            known_memory_ids.add(event.event_id)
            memory_terms = frozenset(terms(str(event.payload["text"])))
            term_sets[event.event_id] = memory_terms
            for term in memory_terms:
                terms_map.add(term, event.event_id)
            for key, value in event.payload.items():
                if (
                    key.endswith("_id")
                    and key not in {"source_event_id", "memory_id"}
                    and isinstance(value, str)
                ):
                    entities_map.add(value, event.event_id)
            goal_id = event.payload.get("goal_id")
            if isinstance(goal_id, str):
                goals_map.add(goal_id, event.event_id)
            person_id = event.payload.get("person_id")
            if isinstance(person_id, str):
                relationships_map.add(person_id, event.event_id)

        # Counts are only ever kept for known memories, and memories are never forgotten.
        return cls(
            tuple(memories),
            MappingProxyType(term_sets),
            terms_map.freeze(),
            entities_map.freeze(),
            goals_map.freeze(),
            relationships_map.freeze(),
            MappingProxyType(accesses),
            MappingProxyType(reminders),
            len(history),
        )

    @classmethod
    def _restore(
        cls,
        history: list[DomainEvent],
        state: Mapping[str, Any],
        revision: int,
    ) -> tuple[
        list[DomainEvent],
        dict[UUID, frozenset[str]],
        dict[str, set[UUID]],
        dict[str, set[UUID]],
        dict[str, set[UUID]],
        dict[str, set[UUID]],
        dict[UUID, int],
        dict[UUID, int],
    ]:
        schema = state.get("schema")
        if schema not in {1, 2}:
            raise ValueError("Unsupported materialized memory index schema")
        prefix = history[:revision]
        events_by_id = {str(event.event_id): event for event in prefix}
        raw_ids = _string_list(state.get("memory_ids"), "memory IDs")
        try:
            memories = [events_by_id[memory_id] for memory_id in raw_ids]
        except KeyError as error:
            raise ValueError("Materialized memory is outside its event prefix") from error
        expected = [
            event
            for event in prefix
            if event.kind == "memory.recorded" and event.payload.get("owner", "pathos") == "pathos"
        ]
        if memories != expected:
            raise ValueError("Materialized memories do not match their event prefix")
        memory_ids = {event.event_id for event in memories}

        raw_terms = state.get("terms_by_memory")
        if not isinstance(raw_terms, dict) or set(raw_terms) != set(raw_ids):
            raise ValueError("Materialized memory terms are incomplete")
        term_sets = {
            UUID(str(memory_id)): frozenset(_string_list(values, "memory terms"))
            for memory_id, values in raw_terms.items()
        }
        if set(term_sets) != memory_ids:
            raise ValueError("Materialized term keys do not match memories")

        def restore_map(name: str) -> dict[str, set[UUID]]:
            raw = state.get(name)
            if not isinstance(raw, dict):
                raise ValueError(f"Materialized {name} map is invalid")
            restored = {
                str(key): {UUID(item) for item in _string_list(values, name)}
                for key, values in raw.items()
            }
            if any(not ids <= memory_ids for ids in restored.values()):
                raise ValueError(f"Materialized {name} references an unknown memory")
            return restored

        raw_accesses = state.get("access_counts")
        if not isinstance(raw_accesses, dict):
            raise ValueError("Materialized access counts are invalid")
        accesses: dict[UUID, int] = {}
        for memory_id, count in raw_accesses.items():
            parsed = UUID(str(memory_id))
            if (
                parsed not in memory_ids
                or isinstance(count, bool)
                or not isinstance(count, int)
                or count < 0
            ):
                raise ValueError("Materialized access count is invalid")
            accesses[parsed] = count
        reminders: dict[UUID, int] = {}
        raw_reminders = state.get("reminder_counts", {}) if schema == 2 else {}
        if not isinstance(raw_reminders, dict):
            raise ValueError("Materialized reminder counts are invalid")
        for memory_id, count in raw_reminders.items():
            parsed = UUID(str(memory_id))
            if (
                parsed not in memory_ids
                or isinstance(count, bool)
                or not isinstance(count, int)
                or count < 0
            ):
                raise ValueError("Materialized reminder count is invalid")
            reminders[parsed] = count
        return (
            memories,
            term_sets,
            restore_map("by_term"),
            restore_map("by_entity"),
            restore_map("by_goal"),
            restore_map("by_relationship"),
            accesses,
            reminders,
        )

    def materialized_state(self) -> Mapping[str, Any]:
        def encode(values: Mapping[str, frozenset[UUID]]) -> dict[str, list[str]]:
            return {
                key: sorted(str(memory_id) for memory_id in memory_ids)
                for key, memory_ids in values.items()
            }

        return {
            "schema": 2,
            "memory_ids": [str(event.event_id) for event in self.memories],
            "terms_by_memory": {
                str(memory_id): sorted(values) for memory_id, values in self.terms_by_memory.items()
            },
            "by_term": encode(self.by_term),
            "by_entity": encode(self.by_entity),
            "by_goal": encode(self.by_goal),
            "by_relationship": encode(self.by_relationship),
            "access_counts": {
                str(memory_id): count for memory_id, count in self.access_counts.items()
            },
            "reminder_counts": {
                str(memory_id): count for memory_id, count in self.reminder_counts.items()
            },
        }


def _simulated_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return event.occurred_at


def _metadata(event: DomainEvent) -> tuple[float, float]:
    importance = float(event.payload.get("importance", 0.5))
    confidence = float(event.payload.get("confidence", 1.0))
    return max(0.0, min(1.0, importance)), max(0.0, min(1.0, confidence))


def _string_metadata(event: DomainEvent, key: str) -> str | None:
    value = event.payload.get(key)
    return value if isinstance(value, str) and value else None


def recall(
    history: list[DomainEvent],
    query: str,
    now: datetime,
    limit: int = 7,
    *,
    entity_ids: set[str] | None = None,
    goal_ids: set[str] | None = None,
    relationship_ids: set[str] | None = None,
    diverse: bool = False,
    index: MemoryIndex | None = None,
    include_archived: bool = False,
) -> list[RecalledMemory]:
    """Rank accessible Pathos memories without treating similarity as proof."""
    if now.utcoffset() is None or not 1 <= limit <= 1000:
        raise ValueError("Recall needs an aware time and a limit from 1–1000")
    query_terms = terms(query)
    entity_ids = entity_ids or set()
    goal_ids = goal_ids or set()
    relationship_ids = relationship_ids or set()
    index = index or MemoryIndex.build(history)
    if index.revision != len(history):
        raise ValueError("Memory index revision does not match supplied history")
    ranked: list[_Ranked] = []
    archived = archived_memory_ids(history)
    recollections = project_recollections(history).latest
    current_affect, emotional_tones, emotional_tags = _affective_context(
        history, now, recollections
    )
    for event in index.memories:
        memory_id = str(event.event_id)
        importance, source_confidence = _metadata(event)
        subjective = recollections.get(memory_id)
        felt_confidence = subjective.confidence if subjective is not None else source_confidence
        remembered_person_id = (
            subjective.remembered_person_id
            if subjective is not None and subjective.remembered_person_id is not None
            else _string_metadata(event, "person_id")
        )
        remembered_location_id = (
            subjective.remembered_location_id
            if subjective is not None and subjective.remembered_location_id is not None
            else _string_metadata(event, "location_id")
        )
        remembered_at = (
            subjective.remembered_at
            if subjective is not None and subjective.remembered_at is not None
            else _simulated_time(event)
        )
        age_days = max(0.0, (now - remembered_at).total_seconds() / 86400)
        half_life = 2.0 + 28.0 * importance
        base_access = 0.5 ** (age_days / half_life)
        rehearsals = min(5, index.access_counts.get(event.event_id, 0))
        reminders = min(3, index.reminder_counts.get(event.event_id, 0))
        reactivation = 0.0
        if subjective is not None:
            subjective_age = max(0.0, (now - subjective.changed_at).total_seconds() / 86400)
            reactivation = 0.55 * (0.5 ** (subjective_age / 14.0))
        reinforcement = min(0.32, rehearsals * 0.04 + reminders * 0.08)
        accessibility = min(1.0, base_access + reinforcement + reactivation)
        subjective_terms = (
            terms(subjective.text)
            if subjective is not None
            else set(index.terms_by_memory[event.event_id])
        )
        matched_terms = tuple(sorted(query_terms & subjective_terms))
        remembered_entities = {
            value
            for key, value in event.payload.items()
            if key.endswith("_id")
            and key not in {"source_event_id", "memory_id", "person_id", "location_id"}
            and isinstance(value, str)
        }
        remembered_entities.update(
            value for value in (remembered_person_id, remembered_location_id) if value is not None
        )
        matched_entities = tuple(sorted(entity_ids & remembered_entities))
        matched_goals = tuple(
            sorted(goal for goal in goal_ids if event.event_id in index.by_goal.get(goal, ()))
        )
        matched_relationships = (
            (remembered_person_id,)
            if remembered_person_id is not None and remembered_person_id in relationship_ids
            else ()
        )
        relevance = len(matched_terms) / max(1, len(query_terms))
        entity_relevance = min(1.0, len(matched_entities) / max(1, len(entity_ids)))
        goal_relevance = min(1.0, len(matched_goals) / max(1, len(goal_ids)))
        relationship_relevance = min(
            1.0, len(matched_relationships) / max(1, len(relationship_ids))
        )
        emotional_tone = emotional_tones.get(memory_id, 0.0)
        mood_congruence = 0.04 * current_affect * emotional_tone
        is_archived = memory_id in archived
        has_direct_cue = bool(
            matched_terms or matched_entities or matched_goals or matched_relationships
        )
        if is_archived and not include_archived and not has_direct_cue and importance < 0.75:
            continue
        components = {
            "lexical": 0.27 * relevance,
            "entity": 0.14 * entity_relevance,
            "goal": 0.15 * goal_relevance,
            "relationship": 0.1 * relationship_relevance,
            "accessibility": 0.17 * accessibility,
            "importance": 0.12 * importance,
            "confidence": 0.05 * felt_confidence,
            "mood_congruence": mood_congruence,
        }
        score = sum(components.values())
        ranked.append(
            _Ranked(
                round(score, 4),
                remembered_at,
                memory_id,
                event,
                accessibility,
                relevance,
                matched_terms,
                matched_entities,
                matched_goals,
                matched_relationships,
                components,
                importance,
                age_days,
                rehearsals,
                reminders,
                mood_congruence,
                subjective,
                felt_confidence,
                source_confidence,
                remembered_person_id,
                remembered_location_id,
            )
        )
    # Only the memories returned are rendered; ranking needs just the scores.
    ranked.sort(key=lambda item: (item.score, item.remembered_at, item.memory_id), reverse=True)
    chosen = _diversify(ranked, limit) if diverse else ranked[:limit]
    return [item.recalled(index, emotional_tags) for item in chosen]


class _Ranked(NamedTuple):
    """A memory's recall score and what its RecalledMemory is rendered from."""

    score: float
    remembered_at: datetime
    memory_id: str
    event: DomainEvent
    accessibility: float
    relevance: float
    matched_terms: tuple[str, ...]
    matched_entities: tuple[str, ...]
    matched_goals: tuple[str, ...]
    matched_relationships: tuple[str, ...]
    components: dict[str, float]
    importance: float
    age_days: float
    rehearsals: int
    reminders: int
    mood_congruence: float
    subjective: Recollection | None
    felt_confidence: float
    source_confidence: float
    remembered_person_id: str | None
    remembered_location_id: str | None

    def recalled(self, index: MemoryIndex, emotional_tags: Mapping[str, _Tag]) -> RecalledMemory:
        event, subjective = self.event, self.subjective
        matched_terms, matched_entities = self.matched_terms, self.matched_entities
        matched_goals, matched_relationships = self.matched_goals, self.matched_relationships
        encoded_valence, encoded_arousal, emotional_label, emotional_intensity = emotional_tags.get(
            self.memory_id, (0.0, 0.35, "quiet", 0.0)
        )
        reasons = []
        if matched_terms:
            reasons.append(f"{len(matched_terms)} cue term{'s' if len(matched_terms) != 1 else ''}")
        if matched_entities:
            reasons.append("entity link: " + ", ".join(matched_entities))
        if matched_goals:
            reasons.append("active goal: " + ", ".join(matched_goals))
        if matched_relationships:
            reasons.append("relationship: " + ", ".join(matched_relationships))
        if self.importance >= 0.7:
            reasons.append("important")
        if self.age_days < 1:
            reasons.append("recent")
        if self.rehearsals:
            reasons.append(f"recalled {self.rehearsals}×")
        if self.reminders:
            reasons.append(f"explicitly reminded {self.reminders}×")
        if self.mood_congruence >= 0.005:
            reasons.append("mood-congruent emotional tone")
        elif self.mood_congruence <= -0.005:
            reasons.append("mood-incongruent emotional tone")
        return RecalledMemory(
            event,
            round(self.accessibility, 4),
            round(self.relevance, 4),
            self.score,
            ", ".join(reasons) or "background accessibility",
            matched_terms,
            matched_entities,
            matched_goals,
            matched_relationships,
            MappingProxyType({key: round(value, 4) for key, value in self.components.items()}),
            *_render_recollection(event, self.accessibility, self.importance, subjective),
            subjective.affective_bias if subjective is not None else 0.0,
            subjective.blended_memory_ids if subjective is not None else (),
            subjective.correction_evidence_id if subjective is not None else None,
            round(self.felt_confidence, 4),
            round(self.source_confidence, 4),
            subjective.confidence_basis if subjective is not None else "source_encoding",
            index.reminder_counts.get(event.event_id, 0),
            self.remembered_person_id,
            self.remembered_location_id,
            self.remembered_at,
            encoded_valence,
            encoded_arousal,
            emotional_label,
            emotional_intensity,
        )


def _render_recollection(
    event: DomainEvent,
    accessibility: float,
    importance: float,
    subjective: Recollection | None,
) -> tuple[str, str]:
    """Render the current subjective recollection without changing source evidence."""
    text = subjective.text if subjective is not None else str(event.payload["text"])
    category = str(event.payload.get("category", "experience"))
    if category == "dream":
        return f"I remember this as a dream: {text}", "dream"
    accessible_detail = (
        "clear"
        if accessibility >= 0.55 or importance >= 0.75
        else "partial"
        if accessibility >= 0.2
        else "vague"
    )
    detail_level = (
        max((subjective.detail_level, accessible_detail), key=_detail_rank)
        if subjective is not None
        else accessible_detail
    )
    if subjective is not None and detail_level == subjective.detail_level:
        return text, detail_level
    if detail_level == "clear":
        return text, "clear"
    if detail_level == "partial":
        first_detail = re.split(r"[,;.!?]", text, maxsplit=1)[0].strip()
        return f"I remember {first_detail.lower()}, though some details are hazy.", "partial"
    links = [
        str(event.payload[key])
        for key in ("person_id", "goal_id", "location_id")
        if isinstance(event.payload.get(key), str)
    ]
    cue = ", ".join(links[:2]) or category
    return f"I have a faint {category} memory connected to {cue}; the details are unclear.", "vague"


def _detail_rank(detail_level: str) -> int:
    return {"clear": 0, "partial": 1, "vague": 2}.get(detail_level, 2)


def _diversify(ranked: list[_Ranked], limit: int) -> list[_Ranked]:
    """Prevent one repeated phrase or category from monopolizing working context."""
    selected: list[_Ranked] = []
    texts: set[str] = set()
    categories: dict[str, int] = {}
    deferred: list[_Ranked] = []
    for item in ranked:
        fingerprint = " ".join(sorted(terms(str(item.event.payload["text"]))))
        if fingerprint in texts:
            continue
        category = str(item.event.payload.get("category", "experience"))
        if categories.get(category, 0) >= 2:
            deferred.append(item)
            continue
        selected.append(item)
        texts.add(fingerprint)
        categories[category] = categories.get(category, 0) + 1
        if len(selected) == limit:
            return selected
    for item in deferred:
        fingerprint = " ".join(sorted(terms(str(item.event.payload["text"]))))
        if fingerprint in texts:
            continue
        selected.append(item)
        texts.add(fingerprint)
        if len(selected) == limit:
            break
    return selected


def memory_view(
    history: list[DomainEvent], now: datetime, *, index: MemoryIndex | None = None
) -> list[dict[str, Any]]:
    """Return every Pathos-owned memory with current accessibility, without rehearsal."""
    owned_count = sum(
        event.payload.get("owner", "pathos") == "pathos"
        for event in events_of(history, "memory.recorded")
    )
    index = index or MemoryIndex.build(history)
    ranked = recall(
        history,
        "",
        now,
        limit=min(1000, max(1, owned_count)),
        index=index,
        include_archived=True,
    )
    by_id = {str(item.event.event_id): item for item in ranked}
    views = []
    archived = archived_memory_ids(history)
    for event in events_of(history, "memory.recorded"):
        if event.payload.get("owner", "pathos") != "pathos":
            continue
        item = by_id.get(str(event.event_id))
        if item is None:
            item = recall([event], "", now, 1)[0]
        views.append(
            {
                **dict(event.payload),
                "id": str(event.event_id),
                "kind": event.kind,
                "accessibility": item.accessibility,
                "recall_score": item.score,
                "recalled_text": item.recalled_text,
                "detail_level": item.detail_level,
                "affective_bias": item.affective_bias,
                "blended_memory_ids": list(item.blended_memory_ids),
                "correction_evidence_id": item.correction_evidence_id,
                "felt_confidence": item.felt_confidence,
                "source_confidence": item.source_confidence,
                "confidence_basis": item.confidence_basis,
                "reminder_count": item.reminder_count,
                "remembered_person_id": item.remembered_person_id,
                "remembered_location_id": item.remembered_location_id,
                "remembered_at": item.remembered_at.isoformat(),
                "encoded_valence": item.encoded_valence,
                "encoded_arousal": item.encoded_arousal,
                "emotional_label": item.emotional_label,
                "emotional_intensity": item.emotional_intensity,
                "archived": str(event.event_id) in archived,
            }
        )
    return views


_Tag = tuple[float, float, str, float]


class _Affect(NamedTuple):
    """The affect and memory tags _affective_context derives, folded over all of history.

    _affective_context leaves out affect and memories timed after ``now``. Events without a
    simulated time are timed by when they were recorded, which can lie on either side of
    it, so one fold leaves every such event out and another keeps them all. A fold answers
    for ``now`` exactly when everything it kept is timed at or before ``now`` and everything
    it left out after it.
    """

    keep_recorded_times: bool
    current: float
    arousal: float
    label: str
    tags: PersistentMap[str, _Tag]
    appraisals: PersistentMap[str, float]
    kept_until: datetime | None
    left_out_from: datetime | None

    def answers(self, now: datetime) -> bool:
        return (self.kept_until is None or self.kept_until <= now) and (
            self.left_out_from is None or self.left_out_from > now
        )


def _affect_step(state: _Affect, event: DomainEvent) -> _Affect:
    if event.kind == "appraisal.recorded":
        source_id = event.payload.get("source_event_id")
        desirability = event.payload.get("desirability")
        if (
            isinstance(source_id, str)
            and isinstance(desirability, (int, float))
            and not isinstance(desirability, bool)
        ):
            return state._replace(
                appraisals=state.appraisals.with_item(
                    source_id, max(-1.0, min(1.0, float(desirability)))
                )
            )
        return state
    if event.kind not in {"emotion.sampled", "affect.changed", "memory.recorded"}:
        return state
    event_time = _simulated_time(event)
    if not state.keep_recorded_times and not isinstance(
        event.payload.get("simulated_at"), (datetime, str)
    ):
        earliest = state.left_out_from
        return state._replace(
            left_out_from=event_time if earliest is None or event_time < earliest else earliest
        )
    kept_until = (
        state.kept_until
        if state.kept_until is not None and event_time <= state.kept_until
        else event_time
    )
    current, arousal, label, tags = state.current, state.arousal, state.label, state.tags
    if event.kind in {"emotion.sampled", "affect.changed"}:
        value = event.payload.get("valence")
        activation = event.payload.get("arousal")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and -1 <= value <= 1:
            current = float(value)
        if (
            isinstance(activation, (int, float))
            and not isinstance(activation, bool)
            and 0 <= activation <= 1
        ):
            arousal = float(activation)
        explicit_label = event.payload.get("label")
        label = (
            explicit_label
            if isinstance(explicit_label, str) and explicit_label.strip()
            else _emotional_label(current, arousal)
        )
    if event.kind == "memory.recorded" and event.payload.get("owner", "pathos") == "pathos":
        intensity = min(1.0, max(abs(current), abs(arousal - 0.35) * 1.25))
        tags = tags.with_item(
            str(event.event_id),
            (round(current, 4), round(arousal, 4), label, round(intensity, 4)),
        )
    return state._replace(
        current=current, arousal=arousal, label=label, tags=tags, kept_until=kept_until
    )


_AFFECT_FOLD: IncrementalFold[_Affect] = IncrementalFold(
    lambda: _Affect(False, 0.0, 0.35, "quiet", PersistentMap(), PersistentMap(), None, None),
    _affect_step,
)


def _affective_context(
    history: list[DomainEvent],
    now: datetime,
    recollections: Mapping[str, Recollection],
) -> tuple[float, dict[str, float], dict[str, _Tag]]:
    """Derive bounded mood congruence from recorded affect and sourced appraisals."""
    state = _AFFECT_FOLD(history)
    if not state.answers(now):
        state = _AFFECT_FOLD(
            history,
            key=True,
            initial=lambda: _Affect(
                True, 0.0, 0.35, "quiet", PersistentMap(), PersistentMap(), None, None
            ),
        )
        if not state.answers(now):
            return _affective_context_at(history, now, recollections)
    tags: dict[str, _Tag] = {}
    tones: dict[str, float] = {}
    for event in events_of(history, "memory.recorded"):
        if event.payload.get("owner", "pathos") != "pathos":
            continue
        memory_id = str(event.event_id)
        tag = state.tags.get(memory_id)
        if tag is not None:
            tags[memory_id] = tag
        linked_source = event.payload.get("source_event_id")
        source_tone = state.appraisals.get(memory_id)
        if source_tone is None:
            source_tone = 0.0
        if isinstance(linked_source, str):
            linked_tone = state.appraisals.get(linked_source)
            if linked_tone is not None:
                source_tone = linked_tone
        if source_tone == 0.0:
            source_tone = tags.get(memory_id, (0.0, 0.35, "quiet", 0.0))[0]
        subjective = recollections.get(memory_id)
        bias = subjective.affective_bias if subjective is not None else 0.0
        tones[memory_id] = max(-1.0, min(1.0, source_tone * 0.8 + bias * 0.2))
    return state.current, tones, tags


def _affective_context_at(
    history: list[DomainEvent],
    now: datetime,
    recollections: Mapping[str, Recollection],
) -> tuple[float, dict[str, float], dict[str, _Tag]]:
    """_affective_context from scratch, leaving out affect recorded after ``now``."""
    current = 0.0
    arousal = 0.35
    label = "quiet"
    tags: dict[str, tuple[float, float, str, float]] = {}
    index = kind_index(history)
    for event in index.select("emotion.sampled", "affect.changed", "memory.recorded"):
        event_time = _simulated_time(event)
        if event_time > now:
            continue
        if event.kind in {"emotion.sampled", "affect.changed"}:
            value = event.payload.get("valence")
            activation = event.payload.get("arousal")
            if isinstance(value, (int, float)) and not isinstance(value, bool) and -1 <= value <= 1:
                current = float(value)
            if (
                isinstance(activation, (int, float))
                and not isinstance(activation, bool)
                and 0 <= activation <= 1
            ):
                arousal = float(activation)
            explicit_label = event.payload.get("label")
            label = (
                explicit_label
                if isinstance(explicit_label, str) and explicit_label.strip()
                else _emotional_label(current, arousal)
            )
        if event.kind == "memory.recorded" and event.payload.get("owner", "pathos") == "pathos":
            intensity = min(1.0, max(abs(current), abs(arousal - 0.35) * 1.25))
            tags[str(event.event_id)] = (
                round(current, 4),
                round(arousal, 4),
                label,
                round(intensity, 4),
            )
    appraisals: dict[str, float] = {}
    for event in index.select("appraisal.recorded"):
        source_id = event.payload.get("source_event_id")
        desirability = event.payload.get("desirability")
        if (
            isinstance(source_id, str)
            and isinstance(desirability, (int, float))
            and not isinstance(desirability, bool)
        ):
            appraisals[source_id] = max(-1.0, min(1.0, float(desirability)))
    tones: dict[str, float] = {}
    for event in index.select("memory.recorded"):
        if event.payload.get("owner", "pathos") != "pathos":
            continue
        memory_id = str(event.event_id)
        linked_source = event.payload.get("source_event_id")
        source_tone = appraisals.get(memory_id, 0.0)
        if isinstance(linked_source, str):
            source_tone = appraisals.get(linked_source, source_tone)
        if source_tone == 0.0:
            source_tone = tags.get(memory_id, (0.0, 0.35, "quiet", 0.0))[0]
        subjective = recollections.get(memory_id)
        bias = subjective.affective_bias if subjective is not None else 0.0
        tones[memory_id] = max(-1.0, min(1.0, source_tone * 0.8 + bias * 0.2))
    return current, tones, tags


def _emotional_label(valence: float, arousal: float) -> str:
    if valence >= 0.3:
        return "joyful" if arousal >= 0.55 else "content"
    if valence <= -0.3:
        return "anxious" if arousal >= 0.55 else "sad"
    if arousal >= 0.65:
        return "keyed-up"
    return "quiet"


def memory_archive_page(
    history: list[DomainEvent],
    now: datetime,
    *,
    offset: int = 0,
    limit: int = 100,
    query: str = "",
    category: str = "all",
    index: MemoryIndex | None = None,
) -> dict[str, Any]:
    """Page newest-first through Pathos's complete owned archive without rehearsal."""
    if (
        isinstance(offset, bool)
        or isinstance(limit, bool)
        or not isinstance(offset, int)
        or not isinstance(limit, int)
        or offset < 0
        or not 1 <= limit <= 100
    ):
        raise ValueError("Memory archive offset and limit are invalid")
    clean_query = query.strip().casefold()
    if len(clean_query) > 200:
        raise ValueError("Memory archive search must be at most 200 characters")
    allowed = {
        "all",
        "archived",
        "experience",
        "encounter",
        "conversation",
        "commitment",
        "plan-change",
        "accomplishment",
        "milestone",
        "dream",
        "family",
        "relationship",
    }
    if category not in allowed:
        raise ValueError("Memory archive category is unknown")
    memories = list(reversed(memory_view(history, now, index=index)))
    filtered = [
        item
        for item in memories
        if (not clean_query or clean_query in str(item.get("text", "")).casefold())
        and (
            category == "all"
            or (category == "archived" and item["archived"])
            or item.get("category", "experience") == category
        )
    ]
    items = filtered[offset : offset + limit]
    next_offset = offset + len(items) if offset + len(items) < len(filtered) else None
    return {
        "revision": len(history),
        "items": items,
        "offset": offset,
        "next_offset": next_offset,
        "matching": len(filtered),
        "total": len(memories),
        "archived": sum(bool(item["archived"]) for item in memories),
        "query": query.strip(),
        "category": category,
    }


def _string_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Materialized {name} must be a string list")
    return value
