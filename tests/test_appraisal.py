import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.appraisal import (
    affect_episode_events,
    appraisal_events,
    baseline_affect_events,
    sleep_and_need_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


class AppraisalTests(unittest.TestCase):
    now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)

    def test_experience_changes_bounded_need_once_with_source_lineage(self):
        source = DomainEvent(
            "npc.encountered",
            "pathos",
            {"person_id": "mara", "simulated_at": self.now.isoformat()},
        )
        state = PathosState()
        events, updated = appraisal_events([source], state, self.now)
        self.assertEqual([event.kind for event in events], ["appraisal.recorded", "needs.changed"])
        self.assertGreater(updated.connection, state.connection)
        self.assertEqual(events[0].causation_id, source.event_id)
        repeated, same = appraisal_events([source, *events], updated, self.now)
        self.assertEqual(repeated, [])
        self.assertEqual(same, updated)

    def test_need_projection_rejects_unbounded_values(self):
        with self.assertRaises(ValueError):
            PathosState().apply(DomainEvent("needs.changed", "pathos", {"rest": 1.1}))

    def test_dream_residue_is_appraised_without_directly_changing_needs(self):
        dream_effect = DomainEvent(
            "dream.effect_applied",
            "pathos",
            {"valence_delta": -0.05, "source_dream_id": "dream"},
        )
        state = PathosState()
        events, updated = appraisal_events([dream_effect], state, self.now)
        self.assertEqual([event.kind for event in events], ["appraisal.recorded"])
        self.assertEqual(updated, state)
        affect, unchanged = affect_episode_events([dream_effect, *events], state, self.now)
        self.assertTrue(affect[0].payload["already_applied"])
        self.assertEqual(affect[0].payload["valence_delta"], 0.0)
        self.assertEqual(unchanged.valence, state.valence)

    def test_completed_learning_satisfies_mastery_from_action_evidence(self):
        source = DomainEvent(
            "activity.completed",
            "pathos",
            {"activity": "learn", "schedule_id": "lesson"},
        )
        state = PathosState(mastery=0.4)
        events, updated = appraisal_events([source], state, self.now)
        self.assertGreater(updated.mastery, state.mastery)
        self.assertEqual(events[0].causation_id, source.event_id)

    def test_anticipation_shapes_affect_once_without_claiming_the_plan_happened(self):
        first = DomainEvent(
            "mind.layer_pulsed",
            "pathos",
            {
                "pulse_id": "prospective-1",
                "layer": "prospective",
                "mode": "background",
                "focus_type": "planned_activity",
                "focus_id": "walk",
                "focus_text": "Look ahead to a walk, while knowing the plan may still change",
                "activation": 0.6,
                "anticipatory_valence": 0.22,
                "simulated_at": self.now.isoformat(),
                "action_authority": False,
            },
        )
        appraisals, state = appraisal_events([first], PathosState(), self.now)

        self.assertEqual([event.kind for event in appraisals], ["appraisal.recorded"])
        self.assertEqual(appraisals[0].payload["source_kind"], "mind.layer_pulsed")
        self.assertEqual(appraisals[0].payload["desirability"], 0.22)
        self.assertEqual(state, PathosState())
        episodes, affected = affect_episode_events(
            [first, *appraisals], state, self.now
        )
        self.assertGreater(affected.valence, state.valence)
        second = DomainEvent(
            "mind.layer_pulsed",
            "pathos",
            {**dict(first.payload), "pulse_id": "prospective-2"},
        )
        repeated, unchanged = appraisal_events(
            [first, *appraisals, *episodes, second], affected, self.now
        )
        self.assertEqual(repeated, [])
        self.assertEqual(unchanged, affected)

    def test_cancellation_feels_like_disappointment_or_relief_from_prior_anticipation(self):
        def prospective(tone: float, schedule_id: str) -> DomainEvent:
            return DomainEvent(
                "mind.layer_pulsed",
                "pathos",
                {
                    "pulse_id": f"prospective-{schedule_id}",
                    "layer": "prospective",
                    "mode": "background",
                    "focus_type": "planned_activity",
                    "focus_id": schedule_id,
                    "focus_text": "A changeable future plan",
                    "activation": 0.6,
                    "anticipatory_valence": tone,
                    "simulated_at": self.now.isoformat(),
                    "action_authority": False,
                },
            )

        pleasant = prospective(0.25, "pleasant")
        pleasant_cancelled = DomainEvent(
            "schedule.cancelled",
            "pathos",
            {
                "schedule_id": "pleasant",
                "reason": "The other person could not make it.",
                "simulated_at": self.now.isoformat(),
            },
        )
        pressured = prospective(-0.2, "pressured")
        pressured_cancelled = DomainEvent(
            "schedule.cancelled",
            "pathos",
            {
                "schedule_id": "pressured",
                "reason": "The obligation was lifted.",
                "simulated_at": self.now.isoformat(),
            },
        )

        appraisals, _ = appraisal_events(
            [pleasant, pleasant_cancelled, pressured, pressured_cancelled],
            PathosState(),
            self.now,
        )
        by_source = {
            event.payload["source_event_id"]: event
            for event in appraisals
            if event.kind == "appraisal.recorded"
        }

        self.assertLess(
            by_source[str(pleasant_cancelled.event_id)].payload["desirability"], 0
        )
        self.assertGreater(
            by_source[str(pressured_cancelled.event_id)].payload["desirability"], 0
        )

    def test_unanticipated_cancellation_has_no_assumed_emotional_meaning(self):
        cancelled = DomainEvent(
            "schedule.cancelled",
            "pathos",
            {
                "schedule_id": "unnoticed",
                "reason": "The plan changed.",
                "simulated_at": self.now.isoformat(),
            },
        )

        events, unchanged = appraisal_events([cancelled], PathosState(), self.now)

        self.assertEqual(events, [])
        self.assertEqual(unchanged, PathosState())

    def test_realizing_a_personal_plan_was_forgotten_has_mild_negative_affect(self):
        lapse = DomainEvent(
            "prospective_memory.lapsed",
            "pathos",
            {
                "schedule_id": "optional",
                "reason": "A low-priority personal plan slipped Pathos's mind.",
                "simulated_at": self.now.isoformat(),
            },
        )

        appraisals, state = appraisal_events([lapse], PathosState(), self.now)
        episodes, affected = affect_episode_events(
            [lapse, *appraisals], state, self.now
        )

        self.assertEqual(appraisals[0].payload["source_event_id"], str(lapse.event_id))
        self.assertLess(appraisals[0].payload["desirability"], 0)
        self.assertLess(affected.valence, state.valence)
        self.assertLess(abs(affected.valence), 0.1)

    def test_unperceived_world_fact_does_not_change_pathos_but_owned_memory_does(self):
        occurred = DomainEvent(
            "world_event.occurred",
            "pathos",
            {"simulated_at": self.now.isoformat()},
        )
        state = PathosState(curiosity=0.4)
        events, unchanged = appraisal_events([occurred], state, self.now)
        self.assertEqual(events, [])
        self.assertEqual(unchanged, state)
        memory = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "owner": "pathos",
                "source": "direct-perception",
                "category": "world-thread",
                "simulated_at": self.now.isoformat(),
            },
        )
        events, changed = appraisal_events([occurred, memory], state, self.now)
        self.assertEqual(events[0].causation_id, memory.event_id)
        self.assertGreater(changed.curiosity, state.curiosity)

    def test_private_offscreen_dialogue_does_not_change_pathos(self):
        turn = DomainEvent(
            "scene.turn_taken",
            "pathos",
            {
                "actor_id": "mara",
                "audience_id": "rowan",
                "privacy": "private",
                "simulated_at": self.now.isoformat(),
            },
        )
        state = PathosState(connection=0.4)

        events, unchanged = appraisal_events([turn], state, self.now)

        self.assertEqual(events, [])
        self.assertEqual(unchanged, state)

    def test_an_exact_owned_perception_allows_public_dialogue_appraisal(self):
        turn = DomainEvent(
            "scene.turn_taken",
            "pathos",
            {
                "actor_id": "mara",
                "audience_id": "rowan",
                "privacy": "public",
                "simulated_at": self.now.isoformat(),
            },
        )
        perceived = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "pathos",
                "source_event_id": str(turn.event_id),
                "simulated_at": self.now.isoformat(),
            },
            causation_id=turn.event_id,
        )
        state = PathosState(connection=0.4)

        events, changed = appraisal_events([turn, perceived], state, self.now)

        self.assertEqual(events[0].causation_id, turn.event_id)
        self.assertGreater(changed.connection, state.connection)

    def test_sleep_recovers_rest_while_waking_hours_create_need_pressure(self):
        sleeping = PathosState(rest=0.4)
        night_events, rested = sleep_and_need_events(
            sleeping, datetime(2026, 1, 1, 2, tzinfo=timezone.utc)
        )
        self.assertGreater(rested.rest, sleeping.rest)
        self.assertFalse(rested.awake)
        morning_events, awake = sleep_and_need_events(
            rested, datetime(2026, 1, 1, 7, tzinfo=timezone.utc)
        )
        self.assertEqual(morning_events[0].kind, "sleep.ended")
        self.assertTrue(awake.awake)
        _, pressured = sleep_and_need_events(awake, datetime(2026, 1, 1, 8, tzinfo=timezone.utc))
        self.assertLess(pressured.connection, awake.connection)
        evening_events, asleep = sleep_and_need_events(
            pressured, datetime(2026, 1, 1, 23, tzinfo=timezone.utc)
        )
        self.assertEqual(evening_events[0].kind, "sleep.started")
        self.assertFalse(asleep.awake)

    def test_appraisals_create_one_bounded_affect_episode_with_source_lineage(self):
        source = DomainEvent(
            "npc.encountered",
            "pathos",
            {"person_id": "mara", "simulated_at": self.now.isoformat()},
        )
        appraisals, state = appraisal_events([source], PathosState(), self.now)
        events, affected = affect_episode_events([source, *appraisals], state, self.now)
        self.assertEqual(
            [event.kind for event in events], ["affect.episode_started", "affect.changed"]
        )
        self.assertEqual(events[0].causation_id, appraisals[0].event_id)
        self.assertGreater(affected.valence, state.valence)
        self.assertGreater(affected.arousal, state.arousal)
        repeated, same = affect_episode_events([source, *appraisals, *events], affected, self.now)
        self.assertEqual(repeated, [])
        self.assertEqual(same, affected)

    def test_repeated_positive_experiences_adapt_instead_of_ratchet_to_euphoria(self):
        sources = [
            DomainEvent(
                "npc.encountered",
                "pathos",
                {"person_id": f"person-{index}", "simulated_at": self.now.isoformat()},
            )
            for index in range(3)
        ]
        appraisals, state = appraisal_events(sources, PathosState(), self.now)
        episodes, affected = affect_episode_events([*sources, *appraisals], state, self.now)
        deltas = [
            float(event.payload["valence_delta"])
            for event in episodes
            if event.kind == "affect.episode_started"
        ]
        self.assertEqual(len(deltas), 3)
        self.assertGreater(deltas[0], deltas[1])
        self.assertGreater(deltas[1], deltas[2])
        self.assertLess(affected.valence, sum([0.024] * 3))

    def test_perceived_world_trouble_can_outweigh_routine_positive_affect(self):
        troubling = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "owner": "pathos",
                "source": "direct-perception",
                "category": "world-event",
                "affective_tone": -0.8,
                "importance": 0.7,
                "simulated_at": self.now.isoformat(),
            },
        )
        pleasant = DomainEvent(
            "npc.encountered",
            "pathos",
            {"person_id": "mara", "simulated_at": self.now.isoformat()},
        )
        appraisals, state = appraisal_events([pleasant, troubling], PathosState(), self.now)
        self.assertEqual(
            [
                event.payload["desirability"]
                for event in appraisals
                if event.kind == "appraisal.recorded"
            ],
            [0.4, -0.8],
        )
        episodes, affected = affect_episode_events(
            [pleasant, troubling, *appraisals], state, self.now
        )
        negative = [
            event
            for event in episodes
            if event.kind == "affect.episode_started" and float(event.payload["valence_delta"]) < 0
        ][0]
        self.assertLess(float(negative.payload["valence_delta"]), -0.1)
        self.assertLess(affected.valence, 0)

    def test_physical_discomfort_and_recovery_have_bounded_emotional_residue(self):
        condition = DomainEvent(
            "wellbeing.episode_started",
            "pathos",
            {
                "episode_id": "condition",
                "condition_kind": "headache",
                "severity": 0.45,
                "expected_end_at": (self.now + timedelta(days=1)).isoformat(),
                "reason": "Ordinary temporary symptoms.",
                "simulated_at": self.now.isoformat(),
                "clinical_diagnosis": False,
            },
        )
        appraisals, state = appraisal_events([condition], PathosState(), self.now)
        self.assertEqual([event.kind for event in appraisals], ["appraisal.recorded"])
        self.assertLess(float(appraisals[0].payload["desirability"]), 0)
        affect, changed = affect_episode_events([condition, *appraisals], state, self.now)
        self.assertEqual(
            [event.kind for event in affect], ["affect.episode_started", "affect.changed"]
        )
        self.assertLess(changed.valence, state.valence)

    def test_transient_affect_recovers_toward_baseline_without_overshoot(self):
        state = PathosState(valence=0.5, arousal=0.8, awake=True)
        events, recovered = baseline_affect_events(state, self.now)
        self.assertEqual(len(events), 1)
        self.assertLess(recovered.valence, state.valence)
        self.assertLess(recovered.arousal, state.arousal)
        settled = PathosState(valence=0.0, arousal=0.35, awake=True)
        self.assertEqual(baseline_affect_events(settled, self.now), ([], settled))

    def test_reflection_carries_a_bounded_emotional_echo_without_parsing_its_prose(self):
        missed = DomainEvent(
            "commitment.missed",
            "pathos",
            {"simulated_at": (self.now - timedelta(hours=2)).isoformat()},
        )
        source_appraisals, _ = appraisal_events([missed], PathosState(), self.now)
        source_appraisal = source_appraisals[0]
        memory = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "I missed something I meant to do.",
                "owner": "pathos",
                "category": "experience",
                "source_event_id": str(missed.event_id),
                "simulated_at": (self.now - timedelta(hours=1)).isoformat(),
            },
        )
        reflection = DomainEvent(
            "reflection.recorded",
            "pathos",
            {
                "text": "This prose can say anything; lineage, not sentiment parsing, decides.",
                "source_memory_id": str(memory.event_id),
                "simulated_at": self.now.isoformat(),
            },
            causation_id=memory.event_id,
        )
        history = [missed, source_appraisal, memory, reflection]

        appraisals, unchanged = appraisal_events(history, PathosState(), self.now)

        echo = next(
            event
            for event in appraisals
            if event.kind == "appraisal.recorded"
            and event.payload["source_event_id"] == str(reflection.event_id)
        )
        self.assertLess(echo.payload["desirability"], 0)
        self.assertGreater(echo.payload["desirability"], source_appraisal.payload["desirability"])
        self.assertEqual(unchanged.valence, 0)
        affect, changed = affect_episode_events([*history, *appraisals], unchanged, self.now)
        self.assertTrue(affect)
        self.assertLess(changed.valence, unchanged.valence)

    def test_reflection_on_a_dream_cannot_create_a_factual_emotional_cause(self):
        dream_memory = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "I remember dreaming about an empty station.",
                "owner": "pathos",
                "category": "dream",
                "simulated_at": self.now.isoformat(),
            },
        )
        reflection = DomainEvent(
            "reflection.recorded",
            "pathos",
            {
                "text": "The station felt lonely.",
                "source_memory_id": str(dream_memory.event_id),
                "simulated_at": self.now.isoformat(),
            },
        )

        events, _ = appraisal_events([dream_memory, reflection], PathosState(), self.now)

        self.assertFalse(
            any(
                event.payload.get("source_event_id") == str(reflection.event_id) for event in events
            )
        )


if __name__ == "__main__":
    unittest.main()
