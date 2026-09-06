"""Distance- and attention-sensitive NPC simulation detail."""

from __future__ import annotations

from enum import IntEnum
from heapq import heappop, heappush
from typing import Mapping

from eidos.domain.world_catalog import WorldCatalog

_LOCAL_TRAVEL_MINUTES = 20


class NPCDetailTier(IntEnum):
    BACKGROUND = 0
    LOCAL = 1
    FOCUSED = 2


def nearby_npc_ids(
    *,
    pathos_location_id: str,
    npc_locations: Mapping[str, str],
    catalog: WorldCatalog,
    attention_person_id: str | None = None,
    active_scene_actor_ids: frozenset[str] = frozenset(),
) -> frozenset[str]:
    """Derive residents eligible for richer cognition without event-stream growth."""
    return frozenset(
        actor_id
        for actor_id, location_id in npc_locations.items()
        if npc_detail_tier(
            actor_id,
            location_id,
            pathos_location_id,
            catalog,
            attention_person_id,
            active_scene_actor_ids,
        )[0]
        is not NPCDetailTier.BACKGROUND
    )


def npc_detail_tier(
    actor_id: str,
    location_id: str,
    pathos_location_id: str,
    catalog: WorldCatalog,
    attention_person_id: str | None,
    active_scene_actor_ids: frozenset[str],
) -> tuple[NPCDetailTier, str]:
    if actor_id in active_scene_actor_ids:
        return NPCDetailTier.FOCUSED, "co-present and inside Pathos's active attention"
    if (
        location_id == pathos_location_id
        and location_id != "home"
        and actor_id == attention_person_id
    ):
        return NPCDetailTier.FOCUSED, "co-present and inside Pathos's active attention"
    if location_id == pathos_location_id and location_id != "home":
        return NPCDetailTier.LOCAL, "co-present with Pathos"
    if location_id == "home":
        return NPCDetailTier.BACKGROUND, "at their own private home"
    travel_minutes = _shortest_minutes(catalog, pathos_location_id, location_id)
    if travel_minutes is not None and travel_minutes <= _LOCAL_TRAVEL_MINUTES:
        return NPCDetailTier.LOCAL, f"within {travel_minutes} minutes of Pathos"
    return NPCDetailTier.BACKGROUND, "outside Pathos's immediate world"


def _shortest_minutes(catalog: WorldCatalog, start: str, end: str) -> int | None:
    if start == end:
        return 0
    graph: dict[str, list[tuple[int, str]]] = {}
    for endpoints, minutes in catalog.route_minutes.items():
        if len(endpoints) != 2:
            continue
        left, right = tuple(endpoints)
        graph.setdefault(left, []).append((minutes, right))
        graph.setdefault(right, []).append((minutes, left))
    queue: list[tuple[int, str]] = [(0, start)]
    best = {start: 0}
    while queue:
        minutes, node = heappop(queue)
        if node == end:
            return minutes
        if minutes != best.get(node):
            continue
        for cost, neighbor in graph.get(node, []):
            candidate = minutes + cost
            if candidate < best.get(neighbor, 10**9):
                best[neighbor] = candidate
                heappush(queue, (candidate, neighbor))
    return None
