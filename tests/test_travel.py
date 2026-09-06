import json
import unittest
from datetime import datetime, timedelta, timezone

from eidos.domain.proposals import ProposalRejected
from eidos.domain.travel import (
    TravelProposal,
    parse_travel_proposal,
    resolve_travel,
    route_duration,
)


class TravelTests(unittest.TestCase):
    now = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)

    def proposal(self, **changes):
        values = {
            "proposal_id": "home-to-cafe",
            "actor_id": "pathos",
            "origin_id": "home",
            "destination_id": "cafe",
            "depart_at": self.now - timedelta(minutes=20),
            "arrive_at": self.now,
            "expected_revision": 3,
        }
        values.update(changes)
        return TravelProposal(**values)

    def resolve(self, proposal=None, location="home", revision=3, history=()):
        return resolve_travel(
            proposal or self.proposal(),
            history=list(history),
            actor_location_id=location,
            known_location_ids={"home", "cafe", "workshop", "park"},
            actual_revision=revision,
            simulated_at=self.now,
        )

    def test_route_creates_departure_completion_and_causal_movement(self):
        result = self.resolve()
        self.assertTrue(result.accepted)
        self.assertEqual(
            [event.kind for event in result.events],
            ["travel.proposed", "travel.started", "travel.completed", "pathos.moved"],
        )
        self.assertEqual(result.events[-1].causation_id, result.events[-2].event_id)

    def test_impossible_stale_and_wrong_origin_trips_are_rejected(self):
        self.assertEqual(
            self.resolve(self.proposal(depart_at=self.now - timedelta(minutes=5))).code,
            "too_fast",
        )
        self.assertEqual(self.resolve(location="cafe").code, "wrong_origin")
        self.assertEqual(self.resolve(revision=2).code, "stale_revision")

    def test_a_registered_route_can_make_a_new_place_reachable(self):
        proposal = self.proposal(
            proposal_id="park-to-glasshouse",
            origin_id="park",
            destination_id="old-glasshouse",
            depart_at=self.now - timedelta(minutes=8),
        )
        result = resolve_travel(
            proposal,
            history=[],
            actor_location_id="park",
            known_location_ids={"park", "old-glasshouse"},
            actual_revision=3,
            simulated_at=self.now,
            route_minutes={frozenset(("park", "old-glasshouse")): 8},
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.events[-1].payload["location_id"], "old-glasshouse")

    def test_connected_routes_make_a_new_place_reachable_across_the_map(self):
        routes = {
            frozenset(("home", "park")): 15,
            frozenset(("park", "old-glasshouse")): 8,
        }
        self.assertEqual(route_duration("home", "old-glasshouse", routes), timedelta(minutes=23))
        proposal = self.proposal(
            proposal_id="home-to-glasshouse",
            destination_id="old-glasshouse",
            depart_at=self.now - timedelta(minutes=23),
        )
        result = resolve_travel(
            proposal,
            history=[],
            actor_location_id="home",
            known_location_ids={"home", "park", "old-glasshouse"},
            actual_revision=3,
            simulated_at=self.now,
            route_minutes=routes,
        )
        self.assertTrue(result.accepted)

    def test_json_contract_is_exact_and_timezone_aware(self):
        proposal = self.proposal()
        raw = {
            "schema_version": 1,
            "proposal_id": proposal.proposal_id,
            "actor_id": proposal.actor_id,
            "origin_id": proposal.origin_id,
            "destination_id": proposal.destination_id,
            "depart_at": proposal.depart_at.isoformat(),
            "arrive_at": proposal.arrive_at.isoformat(),
            "expected_revision": proposal.expected_revision,
        }
        self.assertEqual(parse_travel_proposal(json.dumps(raw)).arrive_at, self.now)
        with self.assertRaises(ProposalRejected):
            parse_travel_proposal(json.dumps({**raw, "arrive_at": "2026-01-01T09:00:00"}))


if __name__ == "__main__":
    unittest.main()
