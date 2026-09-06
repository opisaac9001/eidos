import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.relationship_repairs import relationship_repair_events
from eidos.domain.events import DomainEvent
from eidos.domain.relationship_repairs import project_relationship_repairs
from eidos.domain.relationships import project_relationships


class RelationshipRepairTests(unittest.TestCase):
    now = datetime(2026, 4, 3, 13, tzinfo=timezone.utc)

    def rupture_and_apology(self) -> tuple[DomainEvent, DomainEvent]:
        rupture = DomainEvent(
            "disagreement.expressed",
            "pathos",
            {
                "actor_id": "pathos",
                "target_id": "rowan",
                "topic_id": "park-bench",
                "simulated_at": self.now.isoformat(),
            },
        )
        apology = DomainEvent(
            "apology.offered",
            "pathos",
            {
                "actor_id": "pathos",
                "target_id": "rowan",
                "topic_id": "park-bench",
                "simulated_at": (self.now + timedelta(days=1)).isoformat(),
            },
        )
        return rupture, apology

    def test_apology_opens_an_attempt_without_claiming_forgiveness(self):
        rupture, apology = self.rupture_and_apology()
        events = relationship_repair_events([rupture, apology], self.now + timedelta(days=1))
        self.assertEqual([event.kind for event in events], ["relationship.repair_opened"])
        opened = events[0]
        self.assertEqual(opened.causation_id, apology.event_id)
        self.assertIn("response remains unknown", opened.payload["text"])
        repair = next(iter(project_relationship_repairs([rupture, apology, opened]).values()))
        self.assertEqual((repair.status, repair.contact_count), ("open", 0))

    def test_later_direct_contact_softens_tension_in_small_capped_steps(self):
        rupture, apology = self.rupture_and_apology()
        opened = relationship_repair_events([rupture, apology], self.now + timedelta(days=1))
        contact = DomainEvent(
            "phone.call_completed",
            "pathos",
            {
                "call_id": "rowan-call",
                "caller_id": "rowan",
                "simulated_at": (self.now + timedelta(days=2)).isoformat(),
            },
        )
        history = [rupture, apology, *opened, contact]
        events = relationship_repair_events(history, self.now + timedelta(days=2))
        self.assertEqual(
            [event.kind for event in events],
            ["relationship.repair_contacted", "relationship.changed"],
        )
        self.assertEqual(events[0].causation_id, contact.event_id)
        self.assertEqual(events[1].causation_id, events[0].event_id)
        self.assertEqual(events[1].payload["trust_delta"], 0.0)
        repair = next(iter(project_relationship_repairs([*history, *events]).values()))
        self.assertEqual((repair.status, repair.contact_count), ("improving", 1))
        relationship = project_relationships(events).for_person("rowan")
        self.assertEqual(relationship.trust, 0.3)
        self.assertEqual(relationship.tension, 0.0)
        self.assertEqual(
            relationship_repair_events([*history, *events], self.now + timedelta(days=2)), []
        )

    def test_only_three_contacts_can_contribute_to_one_repair_arc(self):
        rupture, apology = self.rupture_and_apology()
        history = [
            rupture,
            apology,
            *relationship_repair_events([rupture, apology], self.now + timedelta(days=1)),
        ]
        for index in range(4):
            contact = DomainEvent(
                "social.activity_completed",
                "pathos",
                {
                    "person_id": "rowan",
                    "simulated_at": (self.now + timedelta(days=index + 2)).isoformat(),
                },
            )
            history.append(contact)
            history.extend(
                relationship_repair_events(history, self.now + timedelta(days=index + 2))
            )
        repair = next(iter(project_relationship_repairs(history).values()))
        self.assertEqual(repair.contact_count, 3)
        self.assertEqual(sum(event.kind == "relationship.repair_contacted" for event in history), 3)

    def test_inactivity_marks_attempt_dormant_without_relationship_change(self):
        rupture, apology = self.rupture_and_apology()
        opened = relationship_repair_events([rupture, apology], self.now + timedelta(days=1))
        later = (self.now + timedelta(days=32)).replace(hour=8)
        events = relationship_repair_events([rupture, apology, *opened], later)
        self.assertEqual([event.kind for event in events], ["relationship.repair_became_dormant"])
        repair = next(
            iter(project_relationship_repairs([rupture, apology, *opened, *events]).values())
        )
        self.assertEqual(repair.status, "dormant")
        self.assertFalse(any(event.kind == "relationship.changed" for event in events))

    def test_unrelated_contact_cannot_be_fabricated_as_repair_evidence(self):
        rupture, apology = self.rupture_and_apology()
        opened = relationship_repair_events([rupture, apology], self.now + timedelta(days=1))[0]
        contact = DomainEvent(
            "phone.call_completed",
            "pathos",
            {
                "caller_id": "mara",
                "simulated_at": (self.now + timedelta(days=2)).isoformat(),
            },
        )
        fabricated = DomainEvent(
            "relationship.repair_contacted",
            "pathos",
            {
                "repair_id": opened.payload["repair_id"],
                "source_event_id": str(contact.event_id),
                "contact_number": 1,
                "simulated_at": (self.now + timedelta(days=2)).isoformat(),
            },
            causation_id=contact.event_id,
        )
        with self.assertRaises(ValueError):
            project_relationship_repairs([rupture, apology, opened, contact, fabricated])


if __name__ == "__main__":
    unittest.main()
