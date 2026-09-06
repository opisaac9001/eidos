import json
import unittest
from datetime import datetime, timedelta, timezone

from eidos.domain.proposals import ProposalRejected
from eidos.domain.world_events import (
    WorldEventKind,
    WorldEventProposal,
    parse_world_event_proposal,
    resolve_world_event,
)


class WorldEventTests(unittest.TestCase):
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    def proposal(self, **changes):
        values = {
            "proposal_id": "weather-noon",
            "director_id": "moira",
            "event_kind": WorldEventKind.WEATHER,
            "description": "Breezy",
            "location_id": "park",
            "starts_at": self.now,
            "intensity": 0.2,
            "expected_revision": 0,
            "source": "stand-in",
        }
        values.update(changes)
        return WorldEventProposal(**values)

    def resolve(self, proposal=None, history=()):
        return resolve_world_event(
            proposal or self.proposal(),
            history=history,
            known_location_ids={"park", "home"},
            actual_revision=0,
            simulated_at=self.now,
        )

    def test_weather_proposal_becomes_correlated_world_fact(self):
        result = self.resolve()
        self.assertTrue(result.accepted)
        self.assertEqual(
            [event.kind for event in result.events],
            ["world_event.proposed", "world_event.accepted", "world.weather"],
        )
        self.assertEqual(result.events[-1].payload["text"], "Breezy")
        self.assertEqual(result.events[-1].causation_id, result.events[0].event_id)

    def test_location_lead_time_vocabulary_and_cooldown_are_enforced(self):
        accepted = self.resolve().events
        cases = (
            (self.proposal(location_id="moon"), (), "unknown_location"),
            (self.proposal(description="Fire tornado"), (), "invalid_weather"),
            (
                self.proposal(
                    event_kind=WorldEventKind.COMMUNITY,
                    description="A small market",
                    starts_at=self.now + timedelta(minutes=30),
                ),
                (),
                "insufficient_lead_time",
            ),
            (self.proposal(starts_at=self.now + timedelta(hours=1)), accepted, "cooldown"),
        )
        for proposal, history, code in cases:
            with self.subTest(code=code):
                result = self.resolve(proposal, history)
                self.assertFalse(result.accepted)
                self.assertEqual(result.code, code)

    def test_json_contract_is_exact_and_timezone_aware(self):
        raw = {
            "schema_version": 1,
            "proposal_id": "weather-noon",
            "director_id": "moira",
            "event_kind": "weather",
            "description": "Breezy",
            "location_id": "park",
            "starts_at": self.now.isoformat(),
            "intensity": 0.2,
            "expected_revision": 0,
            "source": "stand-in",
        }
        self.assertEqual(
            parse_world_event_proposal(json.dumps(raw)).event_kind, WorldEventKind.WEATHER
        )
        for invalid in ({**raw, "extra": True}, {**raw, "starts_at": "2026-01-01T12:00:00"}):
            with self.assertRaises(ProposalRejected):
                parse_world_event_proposal(json.dumps(invalid))


if __name__ == "__main__":
    unittest.main()
