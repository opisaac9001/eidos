import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.appraisal import appraisal_events
from eidos.application.followups import follow_up_events
from eidos.application.messaging import communication_availability
from eidos.application.urgent_incidents import (
    active_incident_location,
    urgent_incident_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.relationships import project_relationships
from eidos.domain.scenes import project_scenes
from eidos.domain.state import PathosState


class UrgentIncidentTests(unittest.TestCase):
    now = datetime(2026, 1, 10, 15, tzinfo=timezone.utc)
    locations = {"pathos": "home", "user": "home"}

    def perception(self, suffix: str, *, intensity: float = 0.8) -> DomainEvent:
        return DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "pathos",
                "source_kind": "world_event",
                "source_event_id": f"world-{suffix}",
                "location_id": "home",
                "event_type": "brief_power_fault",
                "cause": "a loose aging connection",
                "opportunity": "investigate safely",
                "text": "The stairwell lights flickered and the junction box began to warm.",
                "intensity": intensity,
                "duration_hours": 2,
                "simulated_at": self.now.isoformat(),
            },
        )

    def scene(self) -> DomainEvent:
        return DomainEvent(
            "scene.started",
            "pathos",
            {
                "scene_id": "user-visit",
                "initiator_id": "pathos",
                "partner_id": "user",
                "location_id": "home",
                "topic_id": "open-conversation",
                "max_turns": 40,
                "simulated_at": (self.now - timedelta(hours=1)).isoformat(),
            },
        )

    def decide(self, history):
        return urgent_incident_events(
            history,
            self.now,
            len(history),
            actor_locations=self.locations,
            pathos_energy=0.8,
            values={"care": 0.9},
        )

    def test_response_interrupts_live_visit_holds_place_then_leaves_aftermath(self):
        history, started_events = self._find_outcome("incident.response_started", self.scene())
        self.assertIn("scene.interrupted", [event.kind for event in started_events])
        started = next(
            event for event in started_events if event.kind == "incident.response_started"
        )
        active = [*history, *started_events]
        due = datetime.fromisoformat(str(started.payload["responds_until"]))
        self.assertEqual(active_incident_location(active, due), "home")
        availability = communication_availability(
            active, PathosState(simulated_at=self.now, awake=True)
        )
        self.assertEqual(availability.status, "interrupted")
        completed = urgent_incident_events(
            active,
            due,
            len(active),
            actor_locations=self.locations,
            pathos_energy=0.65,
            values={"care": 0.9},
        )
        kinds = [event.kind for event in completed]
        self.assertIn("incident.response_completed", kinds)
        self.assertIn("memory.recorded", kinds)
        self.assertIn("scene.resumption_decided", kinds)
        final = [*active, *completed]
        self.assertIsNone(active_incident_location(final, due))
        self.assertIn(project_scenes(final).scenes["user-visit"].status, {"active", "ended"})
        outcome = next(event for event in completed if event.kind == "incident.response_completed")
        memory = next(event for event in completed if event.kind == "memory.recorded")
        self.assertEqual(memory.payload["source_event_id"], str(outcome.event_id))
        appraisals, _ = appraisal_events(final, PathosState(simulated_at=due), due)
        self.assertTrue(
            any(
                event.kind == "appraisal.recorded"
                and event.payload["source_event_id"] == str(outcome.event_id)
                for event in appraisals
            )
        )

    def test_pathos_can_decline_without_interrupting_and_feels_the_aftermath(self):
        history, events = self._find_outcome(
            "incident.response_declined", self.scene(), energy=0.0, care=0.0
        )
        self.assertFalse(any(event.kind == "scene.interrupted" for event in events))
        decision = next(event for event in events if event.kind == "incident.attention_decided")
        self.assertEqual(decision.payload["decision"], "decline")
        appraisals, _ = appraisal_events(
            [*history, *events], PathosState(simulated_at=self.now), self.now
        )
        declined = next(event for event in events if event.kind == "incident.response_declined")
        appraisal = next(
            event
            for event in appraisals
            if event.kind == "appraisal.recorded"
            and event.payload["source_event_id"] == str(declined.event_id)
        )
        self.assertLess(appraisal.payload["desirability"], 0)

    def test_nonurgent_or_unwitnessed_events_do_not_claim_pathos_attention(self):
        source = self.perception("quiet", intensity=0.1)
        quiet = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                **dict(source.payload),
                "event_type": "street_music",
                "cause": "a sunny afternoon",
                "opportunity": "listen",
                "text": "Someone played a gentle tune near an open window.",
            },
        )
        self.assertEqual(self.decide([quiet]), [])
        source = self.perception("other")
        private = DomainEvent(
            "perception.recorded", "pathos", {**dict(source.payload), "owner": "mara"}
        )
        self.assertEqual(self.decide([private]), [])

    def test_shared_response_uses_present_resource_and_changes_real_relationship(self):
        resource = DomainEvent(
            "object.registered",
            "pathos",
            {
                "object_id": "hall-repair-kit",
                "name": "Hallway repair kit",
                "owner_id": "community",
                "custodian_id": "community",
                "location_id": "home",
                "condition": "good",
            },
        )
        for index in range(300):
            pathos_perception = self.perception(f"shared-{index}")
            mara_perception = DomainEvent(
                "perception.recorded",
                "pathos",
                {**dict(pathos_perception.payload), "owner": "mara"},
            )
            history = [resource, pathos_perception, mara_perception]
            started_events = urgent_incident_events(
                history,
                self.now,
                len(history),
                actor_locations={**self.locations, "mara": "home"},
                pathos_energy=0.9,
                values={"care": 1.0},
            )
            if any(event.kind == "incident.response_started" for event in started_events):
                break
        else:
            self.fail("No deterministic fixture produced a shared incident response")
        started = next(
            event for event in started_events if event.kind == "incident.response_started"
        )
        self.assertEqual(started.payload["participant_ids"], "mara")
        self.assertEqual(started.payload["resource_id"], "hall-repair-kit")
        active = [*history, *started_events]
        due = datetime.fromisoformat(str(started.payload["responds_until"]))
        completed = urgent_incident_events(
            active,
            due,
            len(active),
            actor_locations={**self.locations, "mara": "home"},
            pathos_energy=0.7,
            values={"care": 1.0},
        )
        self.assertTrue(any(event.kind == "incident.resource_used" for event in completed))
        shared = next(event for event in completed if event.kind == "incident.shared_aftermath")
        relationship = project_relationships([*active, *completed]).for_person("mara")
        self.assertGreater(relationship.trust, 0.3)
        followups = follow_up_events([*active, *completed], due)
        scheduled = next(event for event in followups if event.kind == "follow_up.scheduled")
        self.assertEqual(scheduled.payload["person_id"], "mara")
        self.assertEqual(scheduled.causation_id, shared.event_id)

    def _find_outcome(
        self,
        kind: str,
        *extra: DomainEvent,
        energy: float = 0.8,
        care: float = 0.9,
    ) -> tuple[list[DomainEvent], list[DomainEvent]]:
        for index in range(300):
            history = [self.perception(str(index)), *extra]
            events = urgent_incident_events(
                history,
                self.now,
                len(history),
                actor_locations=self.locations,
                pathos_energy=energy,
                values={"care": care},
            )
            if any(event.kind == kind for event in events):
                return history, events
        self.fail(f"No deterministic fixture produced {kind}")


if __name__ == "__main__":
    unittest.main()
