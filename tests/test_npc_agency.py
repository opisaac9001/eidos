import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.npc_agency import autonomous_npc_plan_events
from eidos.application.offscreen import authored_npc_world_events as npc_world_events
from eidos.domain.events import DomainEvent
from eidos.domain.npc_agency import parse_npc_agency_candidate
from eidos.domain.npcs import project_npcs
from eidos.domain.proposals import ProposalRejected
from eidos.domain.world_catalog import project_world_catalog
from eidos.ports.model_gateway import ModelResponse


class InvalidGateway:
    model = "invalid-fixture"

    async def generate(self, request):
        return ModelResponse(
            json.dumps(
                {
                    "activity_type": "private_project",
                    "title": "Finished a private project",
                    "motivation": "Restore purpose through a concrete activity.",
                    "action": "write",
                    "location_id": "park",
                    "day_offset": 1,
                    "scheduled_hour": 12,
                }
            ),
            "invalid-fixture",
            "test",
            "stop",
        )


class CapturingStandIn(StandInGateway):
    def __init__(self):
        self.contexts = []

    async def generate(self, request):
        self.contexts.append(json.loads(request.messages[-1].content))
        return await super().generate(request)


class NPCAgencyTests(unittest.TestCase):
    now = datetime(2026, 1, 11, 19, tzinfo=timezone.utc)

    def evidence(self, owner="rowan"):
        return DomainEvent(
            "npc.needs_changed",
            "pathos",
            {
                "actor_id": owner,
                "energy": 0.7,
                "connection": 0.7,
                "purpose": 0.2,
                "owner": owner,
                "visibility": "private",
                "simulated_at": self.now.isoformat(),
            },
        )

    def test_candidate_contract_does_not_allow_narrated_success(self):
        with self.assertRaisesRegex(ProposalRejected, "cannot claim"):
            parse_npc_agency_candidate(
                json.dumps(
                    {
                        "activity_type": "private_project",
                        "title": "Already finished the neighborhood notes",
                        "motivation": "Restore purpose through close observation.",
                        "action": "write",
                        "location_id": "park",
                        "day_offset": 1,
                        "scheduled_hour": 12,
                    }
                )
            )

    def test_resident_originates_private_plan_then_physically_completes_it(self):
        evidence = self.evidence()
        events = asyncio.run(
            autonomous_npc_plan_events(
                [evidence], self.now, StandInGateway(), project_world_catalog([])
            )
        )
        kinds = [event.kind for event in events]
        self.assertIn("npc.agency_accepted", kinds)
        self.assertIn("npc.goal_formed", kinds)
        self.assertIn("npc.plan_created", kinds)
        self.assertNotIn("npc.plan_completed", kinds)
        plan = next(event for event in events if event.kind == "npc.plan_created")
        self.assertEqual((plan.payload["owner"], plan.payload["visibility"]), ("rowan", "private"))
        self.assertTrue(plan.payload["activity_type"])

        due = datetime.fromisoformat(plan.payload["scheduled_for"])
        completion = npc_world_events([evidence, *events], due)
        self.assertIn("npc.plan_completed", [event.kind for event in completion])
        final = project_npcs([evidence, *events, *completion], due)
        self.assertEqual(final.people["rowan"].plan_status, "completed")
        self.assertEqual(final.people["rowan"].goal_status, "achieved")

    def test_invalid_private_proposal_is_visible_but_does_not_become_a_plan(self):
        evidence = self.evidence()
        events = asyncio.run(
            autonomous_npc_plan_events(
                [evidence], self.now, InvalidGateway(), project_world_catalog([])
            )
        )
        self.assertIn("npc.agency_rejected", [event.kind for event in events])
        self.assertNotIn("npc.plan_created", [event.kind for event in events])
        retry = asyncio.run(
            autonomous_npc_plan_events(
                [evidence, *events],
                self.now + timedelta(days=1),
                InvalidGateway(),
                project_world_catalog([]),
            )
        )
        self.assertEqual(retry, [])

    def test_costly_agency_only_runs_for_promoted_residents(self):
        gateway = CapturingStandIn()
        events = asyncio.run(
            autonomous_npc_plan_events(
                [self.evidence("rowan")],
                self.now,
                gateway,
                project_world_catalog([]),
                allowed_actor_ids=frozenset({"mara"}),
            )
        )
        self.assertEqual(events, [])
        self.assertEqual(gateway.contexts, [])

    def test_one_resident_never_receives_anothers_private_context(self):
        rowan = self.evidence()
        mara_secret = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "mara",
                "visibility": "private",
                "text": "Mara privately worries about an unopened letter.",
                "location_id": "cafe",
                "simulated_at": self.now.isoformat(),
            },
        )
        rowan_memory = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "rowan",
                "visibility": "private",
                "text": "Rowan noticed long shadows across the square.",
                "location_id": "park",
                "simulated_at": self.now.isoformat(),
            },
        )
        rowan_history = DomainEvent(
            "npc.biography_seeded",
            "pathos",
            {
                "fact_id": "rowan-old-maps",
                "person_id": "rowan",
                "topic": "old maps",
                "text": "I used to name every shortcut on my childhood walks.",
                "reveal_after_familiarity": 0.5,
                "owner": "rowan",
                "visibility": "private",
                "simulated_at": self.now.isoformat(),
            },
        )
        mara_history = DomainEvent(
            "npc.biography_seeded",
            "pathos",
            {
                "fact_id": "mara-unheard-song",
                "person_id": "mara",
                "topic": "unheard song",
                "text": "I've never played the song I wrote as a teenager.",
                "reveal_after_familiarity": 0.7,
                "owner": "mara",
                "visibility": "private",
                "simulated_at": self.now.isoformat(),
            },
        )
        gateway = CapturingStandIn()
        asyncio.run(
            autonomous_npc_plan_events(
                [mara_secret, mara_history, rowan_memory, rowan_history, rowan],
                self.now,
                gateway,
                project_world_catalog([]),
            )
        )
        serialized = json.dumps(gateway.contexts)
        self.assertIn("long shadows", serialized)
        self.assertIn("name every shortcut", serialized)
        self.assertNotIn("unopened letter", serialized)
        self.assertNotIn("song I wrote", serialized)


if __name__ == "__main__":
    unittest.main()
