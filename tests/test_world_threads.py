import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.world_threads import world_thread_events
from eidos.domain.events import DomainEvent
from eidos.domain.world_threads import project_world_threads


class WorldThreadTests(unittest.TestCase):
    start = datetime(2026, 1, 7, 20, tzinfo=timezone.utc)

    def occurrence(self, duration: int = 4) -> DomainEvent:
        return DomainEvent(
            "world_event.occurred",
            "pathos",
            {
                "proposal_id": "mapmaker-visit",
                "event_type": "visiting_mapmaker",
                "description": "A visiting mapmaker lays out an unfinished river atlas.",
                "location_id": "cafe",
                "theme": "curiosity",
                "duration_hours": duration,
                "simulated_at": self.start.isoformat(),
            },
        )

    def test_event_opens_progresses_and_resolves_a_persistent_world_thread(self):
        occurred = self.occurrence()
        opened = world_thread_events([occurred], self.start, {"pathos": "home"})
        self.assertEqual([event.kind for event in opened], ["world_thread.opened"])
        halfway = world_thread_events(
            [occurred, *opened], self.start + timedelta(hours=2), {"pathos": "cafe"}
        )
        self.assertEqual(
            [event.kind for event in halfway],
            ["world_thread.progressed", "perception.recorded", "memory.recorded"],
        )
        due = world_thread_events(
            [occurred, *opened, *halfway],
            self.start + timedelta(hours=4),
            {"pathos": "home"},
        )
        self.assertIn(due[0].kind, {"world_thread.extended", "world_thread.resolved"})
        thread = project_world_threads([occurred, *opened, *halfway, *due])[
            "world-thread-mapmaker-visit"
        ]
        self.assertIn(thread.status, {"active", "resolved"})
        self.assertGreaterEqual(thread.stage, 3)

    def test_causal_incident_does_not_invent_progress_or_outcomes_when_time_passes(self):
        occurred = self.occurrence()
        occurred = DomainEvent(
            occurred.kind,
            occurred.aggregate_id,
            {
                **occurred.payload,
                "source": "causal-world-response",
            },
        )
        opened = world_thread_events([occurred], self.start, {})
        history = [occurred, *opened]
        assert (
            world_thread_events(history, self.start + timedelta(hours=2), {"pathos": "cafe"}) == []
        )
        expired = world_thread_events(history, self.start + timedelta(hours=4), {"pathos": "cafe"})
        assert len(expired) == 1
        assert expired[0].payload["outcome"] == "observation_window_ended"
        assert expired[0].payload["visibility"] == "operator"
        assert world_thread_events([*history, *expired], self.start + timedelta(hours=5), {}) == []

    def test_only_present_actors_perceive_later_developments(self):
        occurred = self.occurrence()
        opened = world_thread_events([occurred], self.start, {})
        progressed = world_thread_events(
            [occurred, *opened],
            self.start + timedelta(hours=2),
            {"pathos": "home", "mara": "cafe"},
        )
        perceptions = [event for event in progressed if event.kind == "perception.recorded"]
        self.assertEqual([event.payload["owner"] for event in perceptions], ["mara"])
        self.assertFalse(any(event.kind == "memory.recorded" for event in progressed))

    def test_old_events_are_not_retroactively_turned_into_live_threads(self):
        occurred = self.occurrence()
        self.assertEqual(
            world_thread_events([occurred], self.start + timedelta(days=2), {}),
            [],
        )

    def test_projection_rejects_fabricated_or_stale_transitions(self):
        fake = DomainEvent(
            "world_thread.opened",
            "pathos",
            {
                "thread_id": "fake",
                "source_event_id": "missing",
                "event_type": "rumor",
                "location_id": "cafe",
                "theme": "uncertainty",
                "summary": "Something supposedly happened.",
                "started_at": self.start.isoformat(),
                "due_at": (self.start + timedelta(hours=2)).isoformat(),
            },
        )
        with self.assertRaisesRegex(ValueError, "occurred world event"):
            project_world_threads([fake])

    def test_projection_rejects_a_transition_before_its_real_due_time(self):
        occurred = self.occurrence()
        opened = world_thread_events([occurred], self.start, {})
        thread_id = "world-thread-mapmaker-visit"
        premature = DomainEvent(
            "world_thread.resolved",
            "pathos",
            {
                "thread_id": thread_id,
                "outcome": "settled quietly",
                "summary": "It supposedly ended immediately.",
                "simulated_at": self.start.isoformat(),
            },
            causation_id=opened[0].event_id,
            correlation_id=thread_id,
        )
        with self.assertRaisesRegex(ValueError, "before it is due"):
            project_world_threads([occurred, *opened, premature])


if __name__ == "__main__":
    unittest.main()
