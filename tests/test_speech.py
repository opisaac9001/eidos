import json
import unittest

from eidos.domain.proposals import ProposalRejected
from eidos.domain.speech import (
    Privacy,
    SpeechProposal,
    parse_speech_proposal,
    resolve_speech,
)


class SpeechTests(unittest.TestCase):
    def proposal(self, **changes):
        values = {
            "proposal_id": "ellis-switch",
            "speaker_id": "ellis",
            "audience_id": "pathos",
            "text": "I found a replacement switch.",
            "privacy": Privacy.PRIVATE,
            "expected_revision": 4,
            "topic_id": "mara-lamp",
        }
        values.update(changes)
        return SpeechProposal(**values)

    def resolve(self, proposal=None, locations=None, revision=4, history=()):
        return resolve_speech(
            proposal or self.proposal(),
            history=list(history),
            actor_locations=locations or {"ellis": "workshop", "pathos": "workshop"},
            known_actor_ids={"pathos", "mara", "ellis", "rowan"},
            actual_revision=revision,
            simulated_at="2026-01-02T10:00:00+00:00",
        )

    def test_co_present_speech_creates_only_the_audiences_perception(self):
        result = self.resolve()
        self.assertTrue(result.accepted)
        self.assertEqual(
            [event.kind for event in result.events],
            ["speech.proposed", "speech.delivered", "perception.recorded"],
        )
        perception = result.events[-1]
        self.assertEqual(perception.payload["owner"], "pathos")
        self.assertEqual(perception.payload["source_event_id"], str(result.events[1].event_id))
        self.assertTrue(perception.payload["reported"])

    def test_absent_unknown_stale_and_duplicate_speech_are_rejected(self):
        self.assertEqual(
            self.resolve(locations={"ellis": "workshop", "pathos": "cafe"}).code,
            "not_co_present",
        )
        self.assertEqual(self.resolve(self.proposal(speaker_id="unknown")).code, "unknown_actor")
        self.assertEqual(self.resolve(revision=3).code, "stale_revision")
        first = self.resolve()
        duplicate = self.resolve(
            self.proposal(expected_revision=4 + len(first.events)),
            revision=4 + len(first.events),
            history=first.events,
        )
        self.assertEqual(duplicate.code, "duplicate_proposal")

    def test_json_contract_is_exact_and_bounded(self):
        raw = {
            "schema_version": 1,
            "proposal_id": "p",
            "speaker_id": "ellis",
            "audience_id": "pathos",
            "text": "Hello",
            "privacy": "private",
            "expected_revision": 1,
            "topic_id": None,
        }
        self.assertEqual(parse_speech_proposal(json.dumps(raw)).privacy, Privacy.PRIVATE)
        with self.assertRaises(ProposalRejected):
            parse_speech_proposal(json.dumps({**raw, "text": "x" * 501}))


if __name__ == "__main__":
    unittest.main()
