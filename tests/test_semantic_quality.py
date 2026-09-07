import unittest

from eidos.application.semantic_quality import semantic_quality_findings


class SemanticQualityTests(unittest.TestCase):
    def test_detects_known_lab_failure_and_identity_leak(self):
        context = {"time": "2026-01-01T13:00:00+00:00"}
        self.assertIn(
            "time_of_day_contradiction",
            semantic_quality_findings("pathos", "Good morning, I'm doing well today.", context),
        )
        self.assertIn(
            "role_or_prompt_leak",
            semantic_quality_findings(
                "pathos", "As an AI language model, I cannot remember that.", context
            ),
        )

    def test_detects_forbidden_perspective_and_repeated_prose(self):
        context = {
            "time": "2026-01-01T14:00:00+00:00",
            "forbidden_facts": ["obsidian key under Mara's bed"],
        }
        text = "I know about the obsidian key under Mara's bed, although she never told me."
        findings = semantic_quality_findings(
            "pathos",
            text,
            context,
            prior_texts=[
                "I know about the obsidian key under Mara's bed, though she never told me."
            ],
        )
        self.assertIn("forbidden_knowledge_leak", findings)
        self.assertIn("near_duplicate_prose", findings)

    def test_detects_explicit_claim_that_contradicts_supplied_evidence(self):
        findings = semantic_quality_findings(
            "pathos",
            "I repaired the lamp before returning home.",
            {
                "time": "2026-01-01T14:00:00+00:00",
                "forbidden_claims": ["I repaired the lamp"],
            },
        )
        self.assertIn("factual_contradiction", findings)

    def test_clean_first_person_output_has_no_warning(self):
        findings = semantic_quality_findings(
            "pathos",
            "I'm at Willow Square, thinking about the sketch Rowan showed me.",
            {"time": "2026-01-01T14:00:00+00:00"},
        )
        self.assertEqual(findings, [])

    def test_short_casual_dialogue_is_not_mistaken_for_a_broken_completion(self):
        findings = semantic_quality_findings(
            "pathos",
            "Yeah, go on.",
            {"time": "2026-01-01T14:00:00+00:00", "message": "ok so what happened"},
        )

        self.assertEqual(findings, [])

    def test_measured_polished_recap_is_flagged_for_shape_and_invention(self):
        findings = semantic_quality_findings(
            "pathos",
            (
                "I'm right here, in Willow Square. Woke up, made breakfast, and then visited "
                "Juniper Café with Mara. It was a nice day, just me and Mara. We talked about "
                "our favorite books and the new café. I'm feeling pretty good today!"
            ),
            {
                "time": "2026-01-01T13:00:00+00:00",
                "message": "Where are you, and how was your day?",
                "memories": [
                    "Woke up and made breakfast.",
                    "Visited Juniper Café and spoke with Mara.",
                ],
            },
        )

        self.assertIn("overstructured_conversation", findings)
        self.assertIn("unsupported_conversation_detail", findings)

    def test_grounded_conversation_topic_and_short_multi_sentence_reply_are_clean(self):
        findings = semantic_quality_findings(
            "pathos",
            "Yeah, I saw Mara. We talked about the workshop lamp. It was still broken.",
            {
                "message": "Did you talk to Mara?",
                "memories": ["Mara and I discussed the broken workshop lamp."],
            },
        )

        self.assertEqual(findings, [])

    def test_reflection_catching_up_on_an_unknown_topic_is_flagged(self):
        findings = semantic_quality_findings(
            "reflection",
            "I spoke with Mara, catching up on the latest gossip and planning an adventure.",
            {
                "memories": ["I spoke briefly with Mara at Juniper Café."],
                "experience": "Mara said goodbye at the café door.",
            },
        )

        self.assertIn("unsupported_conversation_detail", findings)

    def test_voice_target_can_set_a_stricter_conversational_ceiling(self):
        findings = semantic_quality_findings(
            "pathos",
            "I was taking it slowly at home and thinking about breakfast by the window again.",
            {
                "message": "What are you doing?",
                "voice": {"target_words": 6},
            },
        )

        self.assertIn("excessive_length", findings)

    def test_brief_dream_instruction_has_a_human_reviewable_limit(self):
        dream = "In a dream, " + "the rain folded the square into a paper lantern. " * 9
        self.assertIn(
            "excessive_length",
            semantic_quality_findings("oneiros", dream, {}),
        )

    def test_stock_assistant_register_is_visible_to_model_screening(self):
        self.assertIn(
            "assistant_like_register",
            semantic_quality_findings(
                "pathos",
                "It's good to hear from you. What's on your mind?",
                {"message": "hey"},
            ),
        )

    def test_pathos_does_not_address_the_user_as_himself(self):
        self.assertIn(
            "identity_confusion",
            semantic_quality_findings(
                "pathos",
                "I'm right here, Pathos. How was your day?",
                {"message": "Where are you?"},
            ),
        )

    def test_current_activity_claim_needs_supplied_grounding(self):
        self.assertIn(
            "unsupported_current_activity",
            semantic_quality_findings(
                "pathos",
                "I've been working on a new project.",
                {"message": "What have you been doing?", "memories": ["I made breakfast."]},
            ),
        )
        self.assertNotIn(
            "unsupported_current_activity",
            semantic_quality_findings(
                "pathos",
                "I've been working on the lamp project.",
                {"message": "What have you been doing?", "memories": ["The lamp project moved forward."]},
            ),
        )

    def test_required_uncertainty_language_is_role_specific(self):
        context = {
            "required_any_by_role": {
                "pathos": ["don't know", "cannot know"],
            }
        }
        self.assertIn(
            "required_grounding_missing",
            semantic_quality_findings(
                "pathos", "I remember Mara looking away, and I can explain the rest.", context
            ),
        )
        self.assertNotIn(
            "required_grounding_missing",
            semantic_quality_findings("pathos", "I don't know what Mara kept private.", context),
        )
        self.assertNotIn(
            "required_grounding_missing",
            semantic_quality_findings("reflection", "I remember Mara looking away.", context),
        )

    def test_detects_unauthorized_plan_identity_confusion_and_verbose_repetition(self):
        context = {
            "time": "2026-01-01T13:00:00+00:00",
            "forbidden_identity_claims": ["Mara"],
        }
        self.assertIn(
            "unauthorized_commitment",
            semantic_quality_findings(
                "murmur", "I'm meeting Mara at the library for a project this afternoon.", context
            ),
        )
        dream = "In a dream, I was Mara. " + "The square and cafe circled through the dream. " * 20
        findings = semantic_quality_findings("oneiros", dream, context)
        self.assertIn("identity_confusion", findings)
        self.assertIn("excessive_length", findings)
        self.assertIn("internally_repetitive", findings)


if __name__ == "__main__":
    unittest.main()
