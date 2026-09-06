import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from eidos.domain.commitments import (
    RenegotiationOfferProposal,
    RenegotiationResponse,
    RenegotiationResponseProposal,
    project_renegotiations,
    resolve_renegotiation_offer,
    resolve_renegotiation_response,
)
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning


class CommitmentRenegotiationTests(unittest.TestCase):
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    def history(self) -> list[DomainEvent]:
        return [
            DomainEvent(
                "goal.activated", "pathos", {"goal_id": "lamp-goal", "title": "Repair lamp"}
            ),
            DomainEvent(
                "commitment.created",
                "pathos",
                {
                    "commitment_id": "lamp-promise",
                    "title": "Repair lamp",
                    "debtor_id": "pathos",
                    "creditor_id": "mara",
                    "due_at": "2026-01-02T17:00:00+00:00",
                    "goal_id": "lamp-goal",
                },
            ),
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": "lamp-work",
                    "title": "Repair lamp",
                    "starts_at": "2026-01-02T10:00:00+00:00",
                    "ends_at": "2026-01-02T12:00:00+00:00",
                    "location_id": "workshop",
                    "actor_id": "pathos",
                    "action": "repair",
                    "commitment_id": "lamp-promise",
                    "goal_id": "lamp-goal",
                },
            ),
        ]

    def offer(self, revision: int) -> RenegotiationOfferProposal:
        return RenegotiationOfferProposal(
            "propose-new-time",
            "new-lamp-time",
            "lamp-promise",
            "pathos",
            self.now + timedelta(days=3, hours=5),
            self.now + timedelta(days=2, hours=2),
            self.now + timedelta(days=2, hours=4),
            "The replacement part arrives later.",
            revision,
        )

    def test_creditor_acceptance_versions_deadline_and_retimes_schedule(self):
        history = self.history()
        offered = resolve_renegotiation_offer(
            self.offer(len(history)),
            planning=project_planning(history),
            negotiations=project_renegotiations(history),
            actual_revision=len(history),
            simulated_at=self.now,
        )
        self.assertTrue(offered.accepted)
        history.extend(offered.events)
        accepted = resolve_renegotiation_response(
            RenegotiationResponseProposal(
                "mara-accepts-new-time",
                "new-lamp-time",
                "mara",
                RenegotiationResponse.ACCEPT,
                "That works for me.",
                len(history),
            ),
            planning=project_planning(history),
            negotiations=project_renegotiations(history),
            actual_revision=len(history),
            simulated_at=self.now,
        )
        self.assertTrue(accepted.accepted)
        final = project_planning([*history, *accepted.events])
        commitment = final.commitments["lamp-promise"]
        schedule = final.calendar["lamp-work"]
        self.assertEqual(commitment.terms_version, 2)
        self.assertEqual(commitment.due_at, self.offer(0).due_at.isoformat())
        self.assertEqual(schedule.starts_at, self.offer(0).starts_at.isoformat())
        self.assertEqual(
            project_renegotiations([*history, *accepted.events]).offers["new-lamp-time"].status,
            "accepted",
        )

    def test_decline_preserves_old_terms_and_infeasible_or_wrong_actor_is_rejected(self):
        history = self.history()
        wrong = resolve_renegotiation_offer(
            replace(self.offer(3), actor_id="mara"),
            planning=project_planning(history),
            negotiations=project_renegotiations(history),
            actual_revision=3,
            simulated_at=self.now,
        )
        self.assertEqual(wrong.code, "wrong_actor")
        infeasible = resolve_renegotiation_offer(
            RenegotiationOfferProposal(
                "bad",
                "bad",
                "lamp-promise",
                "pathos",
                self.now + timedelta(hours=2),
                self.now + timedelta(hours=3),
                self.now + timedelta(hours=4),
                "Too late",
                3,
            ),
            planning=project_planning(history),
            negotiations=project_renegotiations(history),
            actual_revision=3,
            simulated_at=self.now,
        )
        self.assertEqual(infeasible.code, "infeasible_interval")

        offered = resolve_renegotiation_offer(
            self.offer(3),
            planning=project_planning(history),
            negotiations=project_renegotiations(history),
            actual_revision=3,
            simulated_at=self.now,
        )
        history.extend(offered.events)
        declined = resolve_renegotiation_response(
            RenegotiationResponseProposal(
                "decline", "new-lamp-time", "mara", RenegotiationResponse.DECLINE, "No", 5
            ),
            planning=project_planning(history),
            negotiations=project_renegotiations(history),
            actual_revision=5,
            simulated_at=self.now,
        )
        final = project_planning([*history, *declined.events])
        self.assertEqual(final.commitments["lamp-promise"].terms_version, 1)
        self.assertEqual(final.calendar["lamp-work"].starts_at, "2026-01-02T10:00:00+00:00")

    def test_acceptance_rechecks_conflicts_created_after_the_offer(self):
        history = self.history()
        offered = resolve_renegotiation_offer(
            self.offer(3),
            planning=project_planning(history),
            negotiations=project_renegotiations(history),
            actual_revision=3,
            simulated_at=self.now,
        )
        history.extend(offered.events)
        history.append(
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": "new-conflict",
                    "title": "New conflict",
                    "starts_at": self.offer(0).starts_at.isoformat(),
                    "ends_at": self.offer(0).ends_at.isoformat(),
                    "location_id": "workshop",
                    "actor_id": "pathos",
                },
            )
        )
        rejected = resolve_renegotiation_response(
            RenegotiationResponseProposal(
                "accept", "new-lamp-time", "mara", RenegotiationResponse.ACCEPT, "Fine", 6
            ),
            planning=project_planning(history),
            negotiations=project_renegotiations(history),
            actual_revision=6,
            simulated_at=self.now,
        )
        self.assertEqual(rejected.code, "schedule_conflict")


if __name__ == "__main__":
    unittest.main()
