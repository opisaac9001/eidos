"""Design checks only: this blueprint must not create live events or memories."""

import json
from math import hypot
from pathlib import Path

PLAN = Path(__file__).parents[1] / "world_plans" / "alderwick-v1.json"


def test_blueprint_is_explicitly_not_personal_knowledge():
    plan = json.loads(PLAN.read_text())
    assert plan["status"] == "design_blueprint_not_live_world_facts"
    policy = plan["discovery_policy"]
    assert policy["planned_is_known"] is False
    assert policy["operator_blueprint_is_never_model_context"] is True
    assert policy["existing_history_is_preserved"] is True
    assert policy["private_interiors_require_permission"] is True
    assert policy["default"] == "undiscovered"


def test_town_geometry_is_connected_and_respects_the_river():
    plan = json.loads(PLAN.read_text())
    junctions = {item["id"]: item for item in plan["junctions"]}
    districts = {item["id"]: item for item in plan["districts"]}
    assert len(junctions) == len(plan["junctions"]) == 30
    assert len(districts) == len(plan["districts"]) == 6
    streets = plan["streets"]
    assert len({item["id"] for item in streets}) == len(streets) == 46
    graph = {key: set() for key in junctions}
    edges = set()
    crossings = []
    river = plan["town"]["river"]
    for street in streets:
        start, end = street["from"], street["to"]
        assert start != end
        edge = frozenset((start, end))
        assert edge not in edges
        edges.add(edge)
        a, b = junctions[start], junctions[end]
        assert street["distance_m"] == hypot(a["x"] - b["x"], a["y"] - b["y"])
        assert street["distance_m"] > 0
        if min(a["y"], b["y"]) <= river["north_bank_y"] and max(
            a["y"], b["y"]
        ) >= river["south_bank_y"]:
            assert street["kind"] in {"bridge", "footbridge"}
            crossings.append(street["name"])
        graph[start].add(end)
        graph[end].add(start)
    assert set(crossings) == {"Willow Footbridge", "Foundry Bridge"}
    seen, pending = set(), [next(iter(graph))]
    while pending:
        node = pending.pop()
        if node not in seen:
            seen.add(node)
            pending.extend(graph[node] - seen)
    assert seen == set(junctions)
    width, height = plan["town"]["extent_m"]
    for junction in junctions.values():
        assert 0 <= junction["x"] <= width
        assert 0 <= junction["y"] <= height
    places = plan["places"]
    assert len({place["id"] for place in places}) == len(places) == 42
    for place in places:
        junction = junctions[place["junction"]]
        left, top, right, bottom = districts[place["district"]]["bounds"]
        assert left <= junction["x"] <= right, place["id"]
        assert top <= junction["y"] <= bottom, place["id"]
        assert place["purpose"] and place["address"]


def test_existing_place_ids_survive_the_plan():
    plan = json.loads(PLAN.read_text())
    pack = json.loads((PLAN.parents[1] / "world_packs/city-life-v1.json").read_text())
    existing = {place["id"] for place in plan["places"] if place["status"] == "existing"}
    assert existing == {"home", "cafe", "workshop", "park"} | {
        place["entity_id"] for place in pack["entities"] if place["entity_kind"] == "place"
    }
