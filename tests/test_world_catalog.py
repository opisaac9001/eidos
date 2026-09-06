import unittest

from eidos.domain.planning import project_planning
from eidos.domain.world_catalog import (
    WorldEntityKind,
    WorldExpansionProposal,
    project_world_catalog,
    resolve_world_expansion,
)


class WorldCatalogTests(unittest.TestCase):
    def proposal(self, kind, **changes):
        values = {
            "proposal_id": f"introduce-{kind.value}",
            "entity_kind": kind,
            "entity_id": {
                WorldEntityKind.PERSON: "nina-vale",
                WorldEntityKind.OBJECT: "blue-handcart",
                WorldEntityKind.PLACE: "old-glasshouse",
            }[kind],
            "name": {
                WorldEntityKind.PERSON: "Nina Vale",
                WorldEntityKind.OBJECT: "The blue handcart",
                WorldEntityKind.PLACE: "The old glasshouse",
            }[kind],
            "description": "A specific new part of the neighborhood with an ordinary history.",
            "location_id": "park",
            "purpose": "Gardener" if kind is WorldEntityKind.PERSON else "Shared neighborhood use",
            "color": "#8fa7c9",
            "label": "Glasshouse",
            "x": 44,
            "y": 82,
            "opens_hour": 8,
            "closes_hour": 19,
            "travel_minutes": 12,
            "expected_revision": 0,
        }
        values.update(changes)
        return WorldExpansionProposal(**values)

    def test_seed_catalog_preserves_the_original_world_without_events(self):
        catalog = project_world_catalog([])
        self.assertEqual(set(catalog.places), {"home", "cafe", "workshop", "park"})
        self.assertEqual(set(catalog.people), {"mara", "ellis", "rowan"})
        self.assertEqual(catalog.location_name("cafe"), "Juniper Café")

    def test_people_places_and_objects_are_additive_replayable_facts(self):
        history = []
        for kind in WorldEntityKind:
            catalog = project_world_catalog(history)
            result = resolve_world_expansion(
                self.proposal(kind, expected_revision=len(history)),
                catalog=catalog,
                actual_revision=len(history),
                simulated_at="2026-01-14T17:00:00+00:00",
            )
            self.assertTrue(result.accepted)
            history.extend(result.events)
        catalog = project_world_catalog(history)
        self.assertIn("nina-vale", catalog.people)
        self.assertIn("old-glasshouse", catalog.places)
        self.assertEqual(catalog.route_minutes[frozenset(("park", "old-glasshouse"))], 12)
        self.assertIn("blue-handcart", project_planning(history).objects)
        self.assertTrue(catalog.people["nina-vale"].introduced)
        self.assertTrue(catalog.places["old-glasshouse"].introduced)

    def test_collisions_unknown_connections_and_bad_layout_are_rejected(self):
        catalog = project_world_catalog([])
        cases = (
            (self.proposal(WorldEntityKind.PERSON, entity_id="mara"), "duplicate_id"),
            (
                self.proposal(WorldEntityKind.PLACE, location_id="nowhere"),
                "unknown_location",
            ),
            (
                self.proposal(WorldEntityKind.PLACE, opens_hour=20, closes_hour=10),
                "invalid_place",
            ),
            (
                self.proposal(WorldEntityKind.PLACE, x=25, y=75),
                "crowded_layout",
            ),
        )
        for proposal, code in cases:
            with self.subTest(code=code):
                result = resolve_world_expansion(
                    proposal,
                    catalog=catalog,
                    actual_revision=0,
                    simulated_at="2026-01-14T17:00:00+00:00",
                )
                self.assertFalse(result.accepted)
                self.assertEqual(result.code, code)


if __name__ == "__main__":
    unittest.main()
