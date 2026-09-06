import unittest
from datetime import datetime, timezone

from eidos.application.followups import follow_up_events
from eidos.application.relationship_dates import relationship_date_events
from eidos.domain.events import DomainEvent
from eidos.domain.relationship_dates import project_relationship_dates


class RelationshipDateTests(unittest.TestCase):
    origin = datetime(2026, 2, 10, 14, tzinfo=timezone.utc)

    def source(self, person_id: str = "mara") -> DomainEvent:
        return DomainEvent(
            "social.activity_completed",
            "pathos",
            {"person_id": person_id, "simulated_at": self.origin.isoformat()},
        )

    def test_first_meaningful_interaction_establishes_one_source_linked_date(self):
        source = self.source()
        events = relationship_date_events([source], self.origin)
        self.assertEqual([event.kind for event in events], ["relationship.milestone_recorded"])
        milestone = events[0]
        self.assertEqual(milestone.causation_id, source.event_id)
        self.assertEqual(milestone.payload["origin_date"], "2026-02-10")
        state = project_relationship_dates([source, milestone])
        self.assertEqual(state["mara"].source_event_id, str(source.event_id))
        self.assertEqual(relationship_date_events([source, milestone], self.origin), [])

    def test_anniversary_is_remembered_as_fact_and_can_prompt_npc_follow_up(self):
        source = self.source()
        milestone = relationship_date_events([source], self.origin)[0]
        anniversary_at = datetime(2027, 2, 10, 8, tzinfo=timezone.utc)
        events = relationship_date_events([source, milestone], anniversary_at)
        self.assertEqual(
            [event.kind for event in events],
            ["relationship.anniversary_remembered", "memory.recorded"],
        )
        anniversary, memory = events
        self.assertEqual(anniversary.causation_id, milestone.event_id)
        self.assertEqual(anniversary.payload["years"], 1)
        self.assertEqual(memory.payload["source_event_id"], str(anniversary.event_id))
        self.assertEqual(
            project_relationship_dates([source, milestone, *events])["mara"].anniversaries,
            1,
        )
        followups = follow_up_events([source, milestone, *events], anniversary_at)
        anniversary_followup = next(
            event
            for event in followups
            if event.kind == "follow_up.scheduled"
            and event.payload["source_event_id"] == str(anniversary.event_id)
        )
        self.assertEqual(anniversary_followup.payload["person_id"], "mara")

    def test_user_date_remains_private_and_does_not_schedule_contact(self):
        visit = DomainEvent(
            "visit.ended",
            "pathos",
            {"simulated_at": self.origin.isoformat()},
        )
        milestone = relationship_date_events([visit], self.origin)[0]
        anniversary_at = datetime(2027, 2, 10, 8, tzinfo=timezone.utc)
        events = relationship_date_events([visit, milestone], anniversary_at)
        anniversary = events[0]
        self.assertEqual(anniversary.payload["person_id"], "user")
        self.assertEqual(
            [
                event
                for event in follow_up_events([visit, milestone, *events], anniversary_at)
                if event.payload.get("source_event_id") == str(anniversary.event_id)
            ],
            [],
        )

    def test_leap_day_recurs_on_february_twenty_eighth(self):
        source = DomainEvent(
            "social.activity_completed",
            "pathos",
            {
                "person_id": "mara",
                "simulated_at": datetime(2024, 2, 29, 14, tzinfo=timezone.utc).isoformat(),
            },
        )
        milestone = relationship_date_events([source], self.origin)[0]
        anniversary_at = datetime(2025, 2, 28, 8, tzinfo=timezone.utc)
        events = relationship_date_events([source, milestone], anniversary_at)
        self.assertEqual(events[0].kind, "relationship.anniversary_remembered")

    def test_fabricated_or_mistimed_anniversary_is_rejected(self):
        source = self.source()
        milestone = relationship_date_events([source], self.origin)[0]
        bad = DomainEvent(
            "relationship.anniversary_remembered",
            "pathos",
            {
                "person_id": "mara",
                "milestone_event_id": str(milestone.event_id),
                "years": 1,
                "simulated_at": datetime(2027, 2, 9, 8, tzinfo=timezone.utc).isoformat(),
            },
            causation_id=milestone.event_id,
        )
        with self.assertRaises(ValueError):
            project_relationship_dates([source, milestone, bad])

    def test_legacy_interaction_without_simulated_time_is_ignored(self):
        source = DomainEvent("social.activity_completed", "pathos", {"person_id": "mara"})
        self.assertEqual(relationship_date_events([source], self.origin), [])


if __name__ == "__main__":
    unittest.main()
