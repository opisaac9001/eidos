import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.social_preferences import social_preference_events
from eidos.domain.events import DomainEvent
from eidos.domain.social_preferences import project_social_preferences


class SocialPreferenceTests(unittest.TestCase):
    now = datetime(2026, 3, 2, 9, tzinfo=timezone.utc)

    def user_message(self, text: str, *, at: datetime | None = None) -> DomainEvent:
        return DomainEvent(
            "conversation.message",
            "pathos",
            {
                "speaker": "you",
                "text": text,
                "simulated_at": (at or self.now).isoformat(),
            },
        )

    def test_explicit_first_person_preference_is_remembered_from_its_message(self):
        source = self.user_message("I really love jasmine tea.")
        events = social_preference_events([source], self.now)
        self.assertEqual([event.kind for event in events], ["social.preference_remembered"])
        self.assertEqual(events[0].causation_id, source.event_id)
        preference = next(iter(project_social_preferences([source, *events]).values()))
        self.assertEqual((preference.person_id, preference.topic), ("user", "jasmine tea"))
        self.assertEqual((preference.stance, preference.status), ("likes", "held"))

    def test_opposite_direct_statement_corrects_without_erasing_history(self):
        liked = self.user_message("I like jasmine tea.")
        remembered = social_preference_events([liked], self.now)
        disliked = self.user_message("I hate jasmine tea.", at=self.now + timedelta(days=2))
        revised = social_preference_events(
            [liked, *remembered, disliked], self.now + timedelta(days=2)
        )
        self.assertEqual([event.kind for event in revised], ["social.preference_revised"])
        final = next(
            iter(project_social_preferences([liked, *remembered, disliked, *revised]).values())
        )
        self.assertEqual(final.stance, "avoids")
        self.assertEqual(final.revision, 2)
        self.assertEqual(final.evidence_count, 2)

    def test_ambiguous_conversation_does_not_become_a_preference(self):
        source = self.user_message("Tea might be nice if everyone else wants it.")
        self.assertEqual(social_preference_events([source], self.now), [])
        conflicted = self.user_message("I like tea, but hate coffee.")
        self.assertEqual(social_preference_events([conflicted], self.now), [])

    def test_npc_self_report_is_kept_but_gossip_is_not(self):
        self_report = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "pathos",
                "speaker_id": "mara",
                "claim_subject_id": "mara",
                "claim_predicate": "prefers",
                "claim_value": "Willow Square",
                "claim_confidence": 0.8,
                "simulated_at": self.now.isoformat(),
            },
        )
        gossip = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "pathos",
                "speaker_id": "ellis",
                "claim_subject_id": "mara",
                "claim_predicate": "likes",
                "claim_value": "the workshop",
                "claim_confidence": 0.9,
                "simulated_at": self.now.isoformat(),
            },
        )
        events = social_preference_events([self_report, gossip], self.now)
        self.assertEqual(len(events), 1)
        preference = next(iter(project_social_preferences([self_report, gossip, *events]).values()))
        self.assertEqual((preference.person_id, preference.topic), ("mara", "willow square"))

    def test_old_unreinforced_preference_becomes_uncertain(self):
        source = self.user_message("I enjoy long walks.")
        remembered = social_preference_events([source], self.now)
        later = (self.now + timedelta(days=181)).replace(hour=8)
        faded = social_preference_events([source, *remembered], later)
        self.assertEqual([event.kind for event in faded], ["social.preference_faded"])
        final = next(iter(project_social_preferences([source, *remembered, *faded]).values()))
        self.assertEqual(final.status, "uncertain")
        self.assertEqual(final.confidence, 0.25)
        self.assertEqual(social_preference_events([source, *remembered, *faded], later), [])

    def test_claim_without_matching_source_is_rejected_on_replay(self):
        source = self.user_message("I like jasmine tea.")
        fabricated = DomainEvent(
            "social.preference_remembered",
            "pathos",
            {
                "preference_id": "social-preference-user-coffee",
                "person_id": "user",
                "topic": "coffee",
                "stance": "likes",
                "confidence": 0.98,
                "evidence_event_id": str(source.event_id),
                "simulated_at": self.now.isoformat(),
            },
            causation_id=source.event_id,
        )
        with self.assertRaises(ValueError):
            project_social_preferences([source, fabricated])


if __name__ == "__main__":
    unittest.main()
