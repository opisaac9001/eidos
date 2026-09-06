"""Atomic, versioned content packs that use ordinary world-continuity rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from eidos.domain.character_history import project_character_history
from eidos.domain.events import DomainEvent
from eidos.domain.world_catalog import (
    ENTITY_ID,
    parse_world_expansion_candidate,
    project_world_catalog,
    resolve_world_expansion,
)
from eidos.ports.event_store import EventStore

_PACK_FIELDS_V1 = {"schema_version", "pack_id", "version", "name", "description", "entities"}
_PACK_FIELDS_V2 = {*_PACK_FIELDS_V1, "character_facts"}
_CHARACTER_FACT_FIELDS = {
    "fact_id",
    "person_id",
    "topic",
    "text",
    "reveal_after_familiarity",
}


@dataclass(frozen=True, slots=True)
class WorldPackReport:
    pack_id: str
    version: int
    name: str
    description: str
    checksum: str
    entity_count: int
    entity_ids: tuple[str, ...]
    character_fact_count: int
    character_fact_ids: tuple[str, ...]
    events_appended: int
    status: str


def import_world_pack(
    store: EventStore,
    path: Path,
    *,
    simulated_at: datetime,
) -> WorldPackReport:
    if simulated_at.utcoffset() is None:
        raise ValueError("World-pack import time must be timezone-aware")
    raw = _read_manifest(path)
    pack_id = _text(raw, "pack_id", 40)
    if not ENTITY_ID.fullmatch(pack_id):
        raise ValueError("World-pack ID must be a stable lowercase slug")
    version = raw["version"]
    if isinstance(version, bool) or not isinstance(version, int) or not 1 <= version <= 10000:
        raise ValueError("World-pack version must be between 1 and 10000")
    name = _text(raw, "name", 100)
    description = _text(raw, "description", 500)
    entities = raw["entities"]
    character_facts = raw.get("character_facts", [])
    if (
        not isinstance(entities, list)
        or not isinstance(character_facts, list)
        or len(entities) > 32
        or len(character_facts) > 32
        or not entities
        and not character_facts
    ):
        raise ValueError("World pack must contain one to 32 entities or character facts")
    checksum = hashlib.sha256(
        json.dumps(raw, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    history = store.read("pathos")
    prior = [
        event
        for event in history
        if event.kind == "world.pack_imported" and event.payload.get("pack_id") == pack_id
    ]
    if prior:
        latest = max(int(event.payload["version"]) for event in prior)
        exact = next((event for event in prior if int(event.payload["version"]) == version), None)
        if exact is not None:
            if exact.payload.get("checksum") != checksum:
                raise ValueError("An imported world-pack version cannot be rewritten")
            return WorldPackReport(
                pack_id,
                version,
                name,
                description,
                checksum,
                int(exact.payload["entity_count"]),
                _linked_entity_ids(history, pack_id, version),
                int(exact.payload.get("character_fact_count", 0)),
                _linked_character_fact_ids(history, pack_id, version),
                0,
                "already_imported",
            )
        if version < latest:
            raise ValueError("World-pack version cannot move backwards")
        if version != latest + 1:
            raise ValueError("World-pack releases must be imported in version order")
    elif version != 1:
        raise ValueError("A new world pack must begin at version 1")

    catalog = project_world_catalog(history)
    events: list[DomainEvent] = []
    entity_ids: list[str] = []
    character_fact_ids: list[str] = []
    release_id = f"world-pack:{pack_id}:v{version}"
    seen: set[str] = set()
    for index, entity in enumerate(entities, 1):
        if not isinstance(entity, dict):
            raise ValueError(f"World-pack entity {index} must be an object")
        proposal_id = f"{release_id}:{index}"
        proposal = parse_world_expansion_candidate(
            json.dumps(entity),
            proposal_id=proposal_id,
            expected_revision=len(history) + len(events),
        )
        if proposal.entity_id in seen:
            raise ValueError(f"World-pack entity {proposal.entity_id} is duplicated")
        seen.add(proposal.entity_id)
        resolution = resolve_world_expansion(
            proposal,
            catalog=catalog,
            actual_revision=len(history) + len(events),
            simulated_at=simulated_at.isoformat(),
        )
        if not resolution.accepted:
            raise ValueError(
                f"World-pack entity {proposal.entity_id} was rejected: {resolution.code}"
            )
        events.extend(resolution.events)
        registration = resolution.events[1]
        catalog = catalog.apply(registration)
        linked = DomainEvent(
            "world.pack_entity_linked",
            "pathos",
            {
                "pack_id": pack_id,
                "version": version,
                "entity_id": proposal.entity_id,
                "entity_kind": proposal.entity_kind.value,
                "registration_event_id": str(registration.event_id),
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=registration.event_id,
            correlation_id=release_id,
        )
        events.append(linked)
        entity_ids.append(proposal.entity_id)
    known_fact_ids = set(project_character_history(history).facts)
    for index, raw_fact in enumerate(character_facts, 1):
        if not isinstance(raw_fact, dict) or set(raw_fact) != _CHARACTER_FACT_FIELDS:
            raise ValueError(f"World-pack character fact {index} has invalid fields")
        fact_id = _fact_text(raw_fact, "fact_id", 40)
        person_id = _fact_text(raw_fact, "person_id", 40)
        topic = _fact_text(raw_fact, "topic", 80)
        text = _fact_text(raw_fact, "text", 360)
        threshold = raw_fact["reveal_after_familiarity"]
        if not ENTITY_ID.fullmatch(fact_id):
            raise ValueError("Character fact ID must be a stable lowercase slug")
        if person_id not in catalog.people:
            raise ValueError(f"Character fact {fact_id} belongs to an unknown resident")
        if fact_id in known_fact_ids or fact_id in character_fact_ids:
            raise ValueError(f"Character fact {fact_id} already exists")
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not 0 <= threshold <= 1
        ):
            raise ValueError("Character fact familiarity threshold must be between zero and one")
        seeded = DomainEvent(
            "npc.biography_seeded",
            "pathos",
            {
                "fact_id": fact_id,
                "person_id": person_id,
                "topic": topic,
                "text": text,
                "reveal_after_familiarity": float(threshold),
                "owner": person_id,
                "visibility": "private",
                "pack_id": pack_id,
                "version": version,
                "simulated_at": simulated_at.isoformat(),
            },
            correlation_id=release_id,
        )
        events.append(seeded)
        character_fact_ids.append(fact_id)
    imported = DomainEvent(
        "world.pack_imported",
        "pathos",
        {
            "pack_id": pack_id,
            "version": version,
            "name": name,
            "description": description,
            "checksum": checksum,
            "entity_count": len(entity_ids),
            "character_fact_count": len(character_fact_ids),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=events[-1].event_id,
        correlation_id=release_id,
    )
    events.append(imported)
    store.append("pathos", events, len(history))
    return WorldPackReport(
        pack_id,
        version,
        name,
        description,
        checksum,
        len(entity_ids),
        tuple(entity_ids),
        len(character_fact_ids),
        tuple(character_fact_ids),
        len(events),
        "imported",
    )


def _read_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValueError("World-pack file does not exist")
    if path.stat().st_size > 1_000_000:
        raise ValueError("World-pack file must be at most one megabyte")
    try:
        raw = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("World-pack file is not valid UTF-8 JSON") from error
    if not isinstance(raw, dict):
        raise ValueError("World-pack manifest must be a JSON object")
    schema_version = raw.get("schema_version")
    if schema_version not in {1, 2}:
        raise ValueError("Unsupported world-pack schema version")
    expected = _PACK_FIELDS_V1 if schema_version == 1 else _PACK_FIELDS_V2
    if set(raw) != expected:
        raise ValueError(f"World-pack manifest fields do not match schema version {schema_version}")
    return raw


def _text(raw: dict[str, object], key: str, maximum: int) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"World-pack {key} is invalid")
    return value.strip()


def _fact_text(raw: dict[str, object], key: str, maximum: int) -> str:
    return _text(raw, key, maximum)


def _linked_entity_ids(history: list[DomainEvent], pack_id: str, version: int) -> tuple[str, ...]:
    return tuple(
        str(event.payload["entity_id"])
        for event in history
        if event.kind == "world.pack_entity_linked"
        and event.payload.get("pack_id") == pack_id
        and event.payload.get("version") == version
    )


def _linked_character_fact_ids(
    history: list[DomainEvent], pack_id: str, version: int
) -> tuple[str, ...]:
    return tuple(
        str(event.payload["fact_id"])
        for event in history
        if event.kind == "npc.biography_seeded"
        and event.payload.get("pack_id") == pack_id
        and event.payload.get("version") == version
    )
