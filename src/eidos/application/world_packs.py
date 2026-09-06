"""Atomic, versioned content packs that use ordinary world-continuity rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from eidos.domain.events import DomainEvent
from eidos.domain.world_catalog import (
    ENTITY_ID,
    parse_world_expansion_candidate,
    project_world_catalog,
    resolve_world_expansion,
)
from eidos.ports.event_store import EventStore

_PACK_FIELDS = {"schema_version", "pack_id", "version", "name", "description", "entities"}


@dataclass(frozen=True, slots=True)
class WorldPackReport:
    pack_id: str
    version: int
    name: str
    description: str
    checksum: str
    entity_count: int
    entity_ids: tuple[str, ...]
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
    if not isinstance(entities, list) or not 1 <= len(entities) <= 32:
        raise ValueError("World pack must contain between 1 and 32 entities")
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
    if not isinstance(raw, dict) or set(raw) != _PACK_FIELDS:
        raise ValueError("World-pack manifest fields do not match schema version 1")
    if raw["schema_version"] != 1:
        raise ValueError("Unsupported world-pack schema version")
    return raw


def _text(raw: dict[str, object], key: str, maximum: int) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"World-pack {key} is invalid")
    return value.strip()


def _linked_entity_ids(history: list[DomainEvent], pack_id: str, version: int) -> tuple[str, ...]:
    return tuple(
        str(event.payload["entity_id"])
        for event in history
        if event.kind == "world.pack_entity_linked"
        and event.payload.get("pack_id") == pack_id
        and event.payload.get("version") == version
    )
