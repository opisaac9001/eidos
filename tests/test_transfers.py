import json
import unittest
from datetime import datetime, timezone

from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.proposals import ProposalRejected
from eidos.domain.transfers import (
    TransferKind,
    TransferOfferProposal,
    TransferResponse,
    TransferResponseProposal,
    parse_transfer_offer,
    parse_transfer_response,
    project_transfers,
    resolve_transfer_offer,
    resolve_transfer_response,
)


class TransferTests(unittest.TestCase):
    now = datetime(2026, 1, 1, 14, tzinfo=timezone.utc)

    def object_event(self, owner: str = "ellis", custodian: str = "ellis") -> DomainEvent:
        return DomainEvent(
            "object.registered",
            "awl",
            {
                "object_id": "awl",
                "name": "Bookbinder's awl",
                "owner_id": owner,
                "custodian_id": custodian,
                "location_id": "workshop",
                "condition": "usable",
            },
        )

    def offer(self, kind: TransferKind = TransferKind.LEND) -> TransferOfferProposal:
        return TransferOfferProposal(
            "offer-awl", "awl-loan", "ellis", "pathos", "awl", kind, "For the notebook", 1
        )

    def test_lending_changes_custody_but_not_ownership_after_explicit_acceptance(self):
        history = [self.object_event()]
        offered = resolve_transfer_offer(
            self.offer(),
            planning=project_planning(history),
            transfers=project_transfers(history),
            actor_location_id="workshop",
            counterparty_location_id="workshop",
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertTrue(offered.accepted)
        history.extend(offered.events)
        accepted = resolve_transfer_response(
            TransferResponseProposal(
                "accept-awl", "awl-loan", "pathos", TransferResponse.ACCEPT, "Thank you", 3
            ),
            planning=project_planning(history),
            transfers=project_transfers(history),
            actor_location_id="workshop",
            counterparty_location_id="workshop",
            actual_revision=3,
            simulated_at=self.now,
        )
        history.extend(accepted.events)
        item = project_planning(history).objects["awl"]
        self.assertEqual(item.owner_id, "ellis")
        self.assertEqual(item.custodian_id, "pathos")
        self.assertEqual(project_transfers(history).offers["awl-loan"].status, "accepted")

    def test_gift_changes_ownership_and_return_restores_only_custody(self):
        for kind, expected_owner in ((TransferKind.GIVE, "pathos"), (TransferKind.LEND, "ellis")):
            with self.subTest(kind=kind):
                history = [self.object_event()]
                offered = resolve_transfer_offer(
                    self.offer(kind),
                    planning=project_planning(history),
                    transfers=project_transfers(history),
                    actor_location_id="workshop",
                    counterparty_location_id="workshop",
                    actual_revision=1,
                    simulated_at=self.now,
                )
                history.extend(offered.events)
                accepted = resolve_transfer_response(
                    TransferResponseProposal(
                        "answer", "awl-loan", "pathos", TransferResponse.ACCEPT, "Accepted", 3
                    ),
                    planning=project_planning(history),
                    transfers=project_transfers(history),
                    actor_location_id="workshop",
                    counterparty_location_id="workshop",
                    actual_revision=3,
                    simulated_at=self.now,
                )
                item = project_planning([*history, *accepted.events]).objects["awl"]
                self.assertEqual(item.owner_id, expected_owner)
                self.assertEqual(item.custodian_id, "pathos")

        borrowed = [self.object_event(owner="ellis", custodian="pathos")]
        returned = resolve_transfer_offer(
            TransferOfferProposal(
                "return", "return-awl", "pathos", "ellis", "awl", TransferKind.RETURN, "Done", 1
            ),
            planning=project_planning(borrowed),
            transfers=project_transfers(borrowed),
            actor_location_id="workshop",
            counterparty_location_id="workshop",
            actual_revision=1,
            simulated_at=self.now,
        )
        borrowed.extend(returned.events)
        answer = resolve_transfer_response(
            TransferResponseProposal(
                "take-back", "return-awl", "ellis", TransferResponse.ACCEPT, "Received", 3
            ),
            planning=project_planning(borrowed),
            transfers=project_transfers(borrowed),
            actor_location_id="workshop",
            counterparty_location_id="workshop",
            actual_revision=3,
            simulated_at=self.now,
        )
        item = project_planning([*borrowed, *answer.events]).objects["awl"]
        self.assertEqual((item.owner_id, item.custodian_id), ("ellis", "ellis"))

    def test_transfer_revalidates_authority_location_revision_and_recipient(self):
        history = [self.object_event()]
        for proposal, place, code in (
            (self.offer(), "park", "not_co_present"),
            (
                TransferOfferProposal(
                    "x", "x", "pathos", "ellis", "awl", TransferKind.GIVE, "x", 1
                ),
                "workshop",
                "no_authority",
            ),
            (
                TransferOfferProposal(
                    "x", "x", "ellis", "pathos", "awl", TransferKind.LEND, "x", 0
                ),
                "workshop",
                "stale_revision",
            ),
        ):
            with self.subTest(code=code):
                result = resolve_transfer_offer(
                    proposal,
                    planning=project_planning(history),
                    transfers=project_transfers(history),
                    actor_location_id="workshop",
                    counterparty_location_id=place,
                    actual_revision=1,
                    simulated_at=self.now,
                )
                self.assertEqual(result.code, code)

    def test_json_contracts_are_exact_and_versioned(self):
        raw = {
            "schema_version": 1,
            "proposal_id": "offer-awl",
            "offer_id": "awl-loan",
            "actor_id": "ellis",
            "counterparty_id": "pathos",
            "object_id": "awl",
            "kind": "lend",
            "reason": "For the notebook",
            "expected_revision": 1,
        }
        self.assertEqual(parse_transfer_offer(json.dumps(raw)).kind, TransferKind.LEND)
        for invalid in ({**raw, "extra": True}, {**raw, "schema_version": 2}):
            with self.assertRaises(ProposalRejected):
                parse_transfer_offer(json.dumps(invalid))
        response = {
            "schema_version": 1,
            "proposal_id": "accept-awl",
            "offer_id": "awl-loan",
            "actor_id": "pathos",
            "response": "accept",
            "reason": "Thank you",
            "expected_revision": 3,
        }
        self.assertEqual(
            parse_transfer_response(json.dumps(response)).response, TransferResponse.ACCEPT
        )
        with self.assertRaises(ProposalRejected):
            parse_transfer_response(json.dumps({**response, "response": "take"}))


if __name__ == "__main__":
    unittest.main()
