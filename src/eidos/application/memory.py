"""Explainable autobiographical recall over immutable source events."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

from eidos.application.memory_retention import archived_memory_ids
from eidos.domain.events import DomainEvent

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
        terms_map: dict[str, set[UUID]]
        entities_map: dict[str, set[UUID]]
        goals_map: dict[str, set[UUID]]
        relationships_map: dict[str, set[UUID]]
        accesses: dict[UUID, int]
        if base_index is not None:
            memories = list(base_index.memories)
            term_sets = dict(base_index.terms_by_memory)
            terms_map = {key: set(values) for key, values in base_index.by_term.items()}
            entities_map = {key: set(values) for key, values in base_index.by_entity.items()}
            goals_map = {key: set(values) for key, values in base_index.by_goal.items()}
            relationships_map = {
                key: set(values) for key, values in base_index.by_relationship.items()
            }
            accesses = dict(base_index.access_counts)
        elif materialized_state is None:
            memories = []
            term_sets = {}
            terms_map = {}
            entities_map = {}
            goals_map = {}
            relationships_map = {}
            accesses = {}
            materialized_revision = 0
        else:
            (
                memories,
                term_sets,
                terms_map,
                entities_map,
                goals_map,
                relationships_map,
                accesses,
            ) = cls._restore(history, materialized_state, materialized_revision)

        known_memory_ids = {event.event_id for event in memories}
        for event in history[materialized_revision:]:
            if event.kind == "memory.accessed":
                try:
                    memory_id = UUID(str(event.payload["memory_id"]))
                except (KeyError, ValueError):
                    continue
                accesses[memory_id] = accesses.get(memory_id, 0) + 1
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
                terms_map.setdefault(term, set()).add(event.event_id)
            for key, value in event.payload.items():
                if (
                    key.endswith("_id")
                    and key not in {"source_event_id", "memory_id"}
                    and isinstance(value, str)
                ):
                    entities_map.setdefault(value, set()).add(event.event_id)
            goal_id = event.payload.get("goal_id")
            if isinstance(goal_id, str):
                goals_map.setdefault(goal_id, set()).add(event.event_id)
            person_id = event.payload.get("person_id")
            if isinstance(person_id, str):
                relationships_map.setdefault(person_id, set()).add(event.event_id)

        def freeze(values: dict[str, set[UUID]]) -> Mapping[str, frozenset[UUID]]:
            return MappingProxyType({key: frozenset(ids) for key, ids in values.items()})

        accesses = {
            memory_id: count
            for memory_id, count in accesses.items()
            if memory_id in known_memory_ids
        }
        return cls(
            tuple(memories),
            MappingProxyType(term_sets),
            freeze(terms_map),
            freeze(entities_map),
            freeze(goals_map),
            freeze(relationships_map),
            MappingProxyType(accesses),
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
    ]:
        if state.get("schema") != 1:
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
        return (
            memories,
            term_sets,
            restore_map("by_term"),
            restore_map("by_entity"),
            restore_map("by_goal"),
            restore_map("by_relationship"),
            accesses,
        )

    def materialized_state(self) -> Mapping[str, Any]:
        def encode(values: Mapping[str, frozenset[UUID]]) -> dict[str, list[str]]:
            return {
                key: sorted(str(memory_id) for memory_id in memory_ids)
                for key, memory_ids in values.items()
            }

        return {
            "schema": 1,
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
    ranked = []
    archived = archived_memory_ids(history)
    for event in index.memories:
        importance, confidence = _metadata(event)
        age_days = max(0.0, (now - _simulated_time(event)).total_seconds() / 86400)
        half_life = 2.0 + 28.0 * importance
        base_access = 0.5 ** (age_days / half_life)
        rehearsals = min(5, index.access_counts.get(event.event_id, 0))
        accessibility = min(1.0, base_access + rehearsals * 0.04)
        matched_terms = tuple(sorted(query_terms & index.terms_by_memory[event.event_id]))
        matched_entities = tuple(
            sorted(
                entity for entity in entity_ids if event.event_id in index.by_entity.get(entity, ())
            )
        )
        matched_goals = tuple(
            sorted(goal for goal in goal_ids if event.event_id in index.by_goal.get(goal, ()))
        )
        matched_relationships = tuple(
            sorted(
                person
                for person in relationship_ids
                if event.event_id in index.by_relationship.get(person, ())
            )
        )
        relevance = len(matched_terms) / max(1, len(query_terms))
        entity_relevance = min(1.0, len(matched_entities) / max(1, len(entity_ids)))
        goal_relevance = min(1.0, len(matched_goals) / max(1, len(goal_ids)))
        relationship_relevance = min(
            1.0, len(matched_relationships) / max(1, len(relationship_ids))
        )
        is_archived = str(event.event_id) in archived
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
            "confidence": 0.05 * confidence,
        }
        score = sum(components.values())
        reasons = []
        if matched_terms:
            reasons.append(f"{len(matched_terms)} cue term{'s' if len(matched_terms) != 1 else ''}")
        if matched_entities:
            reasons.append("entity link: " + ", ".join(matched_entities))
        if matched_goals:
            reasons.append("active goal: " + ", ".join(matched_goals))
        if matched_relationships:
            reasons.append("relationship: " + ", ".join(matched_relationships))
        if importance >= 0.7:
            reasons.append("important")
        if age_days < 1:
            reasons.append("recent")
        if rehearsals:
            reasons.append(f"recalled {rehearsals}×")
        ranked.append(
            RecalledMemory(
                event,
                round(accessibility, 4),
                round(relevance, 4),
                round(score, 4),
                ", ".join(reasons) or "background accessibility",
                matched_terms,
                matched_entities,
                matched_goals,
                matched_relationships,
                MappingProxyType({key: round(value, 4) for key, value in components.items()}),
                *_render_recollection(event, accessibility, importance),
            )
        )
    ranked.sort(
        key=lambda item: (item.score, _simulated_time(item.event), str(item.event.event_id)),
        reverse=True,
    )
    if not diverse:
        return ranked[:limit]
    return _diversify(ranked, limit)


def _render_recollection(
    event: DomainEvent, accessibility: float, importance: float
) -> tuple[str, str]:
    """Blur low-access detail by omission only; never synthesize a replacement fact."""
    text = str(event.payload["text"])
    category = str(event.payload.get("category", "experience"))
    if category == "dream":
        return f"I remember this as a dream: {text}", "dream"
    if accessibility >= 0.55 or importance >= 0.75:
        return text, "clear"
    if accessibility >= 0.2:
        first_detail = re.split(r"[,;.!?]", text, maxsplit=1)[0].strip()
        return f"I remember {first_detail.lower()}, though some details are hazy.", "partial"
    links = [
        str(event.payload[key])
        for key in ("person_id", "goal_id", "location_id")
        if isinstance(event.payload.get(key), str)
    ]
    cue = ", ".join(links[:2]) or category
    return f"I have a faint {category} memory connected to {cue}; the details are unclear.", "vague"


def _diversify(ranked: list[RecalledMemory], limit: int) -> list[RecalledMemory]:
    """Prevent one repeated phrase or category from monopolizing working context."""
    selected: list[RecalledMemory] = []
    texts: set[str] = set()
    categories: dict[str, int] = {}
    deferred: list[RecalledMemory] = []
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
        event.kind == "memory.recorded" and event.payload.get("owner", "pathos") == "pathos"
        for event in history
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
    for event in history:
        if event.kind != "memory.recorded" or event.payload.get("owner", "pathos") != "pathos":
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
                "archived": str(event.event_id) in archived,
            }
        )
    return views


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
        "dream",
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
