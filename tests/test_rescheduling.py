import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID

from eidos.application.rescheduling import reflective_rescheduling_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.rescheduling import (
    RescheduleProposal,
    ScheduleCancellationProposal,
    resolve_reschedule,
    resolve_schedule_cancellation,
)
from eidos.domain.world_catalog import project_world_catalog


class ReschedulingTests(unittest.TestCase):
    now = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
    catalog = project_world_catalog([])

    def history(
        self,
        *,
        commitment_id: str | None = None,
        aggregate_id: str = "pathos",
    ) -> list[DomainEvent]:
        created = DomainEvent(
            "schedule.created",
            aggregate_id,
            {
                "schedule_id": "reading-hour",
                "title": "Read at the workshop",
                "starts_at": (self.now - timedelta(hours=2)).isoformat(),
                "ends_at": (self.now - timedelta(hours=1)).isoformat(),
                "location_id": "workshop",
                "actor_id": "pathos",
                "activity_type": "reading",
                "commitment_id": commitment_id,
            },
        )
        interrupted = DomainEvent(
            "schedule.interrupted",
            "pathos",
            {"schedule_id": "reading-hour", "reason": "The workshop had to close early."},
        )
        decision = DomainEvent(
            "reflection.reconsideration_decided",
            "pathos",
            {
                "decision_id": "review-reading",
                "target_type": "schedule",
                "target_id": "reading-hour",
                "decision": "seek_new_time",
                "simulated_at": self.now.isoformat(),
            },
            event_id=UUID(int=42),
        )
        return [created, interrupted, decision]

    def test_personal_review_finds_a_real_new_interval_once(self):
        history = self.history()
        before = project_planning(history).calendar["reading-hour"]

        events = reflective_rescheduling_events(
            history,
            self.now,
            len(history),
            planning=project_planning(history),
            catalog=self.catalog,
        )
        after = project_planning([*history, *events]).calendar["reading-hour"]

        self.assertEqual(
            [event.kind for event in events[:3]],
            [
                "schedule.reschedule_proposed",
                "schedule.reschedule_accepted",
                "schedule.rescheduled",
            ],
        )
        self.assertEqual(after.status, "scheduled")
        self.assertNotEqual(after.starts_at, before.starts_at)
        self.assertEqual(
            datetime.fromisoformat(after.ends_at) - datetime.fromisoformat(after.starts_at),
            timedelta(hours=1),
        )
        self.assertEqual(
            reflective_rescheduling_events(
                [*history, *events],
                self.now,
                len(history) + len(events),
                planning=project_planning([*history, *events]),
                catalog=self.catalog,
            ),
            [],
        )

    def test_external_commitment_and_foreign_schedule_cannot_be_changed_privately(self):
        for history in (
            self.history(commitment_id="promise-to-mara"),
            self.history(aggregate_id="mara"),
        ):
            events = reflective_rescheduling_events(
                history,
                self.now,
                len(history),
                planning=project_planning(history),
                catalog=self.catalog,
            )
            self.assertEqual(
                [event.kind for event in events], ["schedule.reflective_rescheduling_handled"]
            )
            self.assertEqual(events[0].payload["outcome"], "schedule_no_longer_eligible")
            self.assertEqual(
                project_planning([*history, *events]).calendar["reading-hour"].status,
                "interrupted",
            )

    def test_domain_rejects_conflict_and_changed_duration(self):
        history = self.history()[:2]
        history.append(
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": "existing",
                    "title": "Existing work",
                    "starts_at": (self.now + timedelta(days=1)).replace(hour=10).isoformat(),
                    "ends_at": (self.now + timedelta(days=1)).replace(hour=12).isoformat(),
                    "location_id": "workshop",
                    "actor_id": "pathos",
                },
            )
        )
        planning = project_planning(history)
        start = (self.now + timedelta(days=1)).replace(hour=10)
        conflict = resolve_reschedule(
            RescheduleProposal(
                "try-conflict",
                "reading-hour",
                "pathos",
                start,
                start + timedelta(hours=1),
                "Try another time.",
                len(history),
            ),
            planning=planning,
            actual_revision=len(history),
            simulated_at=self.now,
            opening_hours=self.catalog.opening_hours,
            route_minutes=self.catalog.route_minutes,
        )
        changed_duration = resolve_reschedule(
            RescheduleProposal(
                "try-longer",
                "reading-hour",
                "pathos",
                start + timedelta(days=1),
                start + timedelta(days=1, hours=2),
                "Try longer instead.",
                len(history),
            ),
            planning=planning,
            actual_revision=len(history),
            simulated_at=self.now,
            opening_hours=self.catalog.opening_hours,
            route_minutes=self.catalog.route_minutes,
        )

        self.assertEqual(conflict.code, "schedule_conflict")
        self.assertEqual(changed_duration.code, "changed_duration")
        self.assertEqual(planning.calendar["reading-hour"].status, "interrupted")

    def test_domain_rejects_closed_hours_travel_and_external_promise_bypass(self):
        base = self.history()[:2]
        tomorrow = self.now + timedelta(days=1)
        travel_history = [
            *base,
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": "before",
                    "title": "Breakfast at home",
                    "starts_at": tomorrow.replace(hour=7).isoformat(),
                    "ends_at": tomorrow.replace(hour=8).isoformat(),
                    "location_id": "home",
                    "actor_id": "pathos",
                },
            ),
        ]

        def attempt(history, proposal_id, start):
            return resolve_reschedule(
                RescheduleProposal(
                    proposal_id,
                    "reading-hour",
                    "pathos",
                    start,
                    start + timedelta(hours=1),
                    "Try another time.",
                    len(history),
                ),
                planning=project_planning(history),
                actual_revision=len(history),
                simulated_at=self.now,
                opening_hours=self.catalog.opening_hours,
                route_minutes=self.catalog.route_minutes,
            )

        self.assertEqual(
            attempt(travel_history, "too-close", tomorrow.replace(hour=8)).code,
            "travel_conflict",
        )
        self.assertEqual(
            attempt(base, "after-closing", tomorrow.replace(hour=20)).code,
            "location_closed",
        )
        external = self.history(commitment_id="promise-to-mara")[:2]
        self.assertEqual(
            attempt(external, "private-bypass", tomorrow.replace(hour=10)).code,
            "external_commitment",
        )

    def test_optional_cancellation_cannot_release_promised_or_goal_work(self):
        for history, code in (
            (self.history(commitment_id="promise-to-mara")[:2], "external_commitment"),
            (
                [
                    DomainEvent(
                        "goal.activated",
                        "pathos",
                        {"goal_id": "reading-goal", "title": "Finish the book"},
                    ),
                    DomainEvent(
                        "schedule.created",
                        "pathos",
                        {
                            "schedule_id": "reading-hour",
                            "title": "Read",
                            "starts_at": (self.now - timedelta(hours=2)).isoformat(),
                            "ends_at": (self.now - timedelta(hours=1)).isoformat(),
                            "location_id": "home",
                            "actor_id": "pathos",
                            "goal_id": "reading-goal",
                        },
                    ),
                    DomainEvent(
                        "schedule.interrupted",
                        "pathos",
                        {"schedule_id": "reading-hour", "reason": "The hour was interrupted."},
                    ),
                ],
                "linked_goal",
            ),
        ):
            planning = project_planning(history)
            result = resolve_schedule_cancellation(
                ScheduleCancellationProposal(
                    "release-reading",
                    "reading-hour",
                    "pathos",
                    "It no longer fits.",
                    len(history),
                ),
                planning=planning,
                actual_revision=len(history),
                simulated_at=self.now,
            )

            self.assertEqual(result.code, code)
            self.assertEqual(planning.calendar["reading-hour"].status, "interrupted")


if __name__ == "__main__":
    unittest.main()
