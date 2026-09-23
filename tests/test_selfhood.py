import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.selfhood import (
    inquiry_for_reflection,
    parse_chapter_proposal,
    parse_insight_proposal,
    reflection_inquiry_context,
    selfhood_after_reflection_events,
    selfhood_context,
    selfhood_daily_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.identity import identity_established_event, project_identity
from eidos.domain.proposals import ProposalRejected
from eidos.domain.selfhood import (
    STARTING_VALUES,
    developed_values,
    project_selfhood,
    source_payload,
    value_evidence,
)
from eidos.ports.model_gateway import ModelMessage, ModelRequest, ModelResponse

START = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)


def at(days: float, hour: int = 12) -> datetime:
    return START.replace(hour=hour) + timedelta(days=days)


def event(kind: str, when: datetime, **payload: object) -> DomainEvent:
    return DomainEvent(kind, "pathos", {**payload, "simulated_at": when.isoformat()})


def missed(days: float) -> DomainEvent:
    return event("schedule.failed", at(days), schedule_id=f"plan-{days}", reason="slipped")


def reflection(days: float, text: str = "I keep turning it over.") -> DomainEvent:
    return event("reflection.recorded", at(days, 21), text=text, role="reflection")


class FixedGateway:
    """Returns one canned structured proposal and records what it was asked."""

    def __init__(self, proposal: dict[str, object]) -> None:
        self.proposal = proposal
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(json.dumps(self.proposal), "fixed", "test", "stop")


class EvidenceTests(unittest.TestCase):
    def test_only_pathos_experience_is_felt_against_values(self) -> None:
        self.assertEqual(value_evidence(missed(1))[0][:2], ("reliability", -1))
        foreign = DomainEvent(
            "schedule.failed", "pathos", {"owner": "mara", "simulated_at": at(1).isoformat()}
        )
        self.assertEqual(value_evidence(foreign), ())
        self.assertEqual(value_evidence(event("time.advanced", at(1))), ())

    def test_his_own_replies_count_as_care_but_system_notices_do_not(self) -> None:
        reply = event("conversation.message", at(1), speaker="pathos", text="Hey.")
        notice = event("conversation.message", at(1), speaker="system", text="He left.")
        self.assertEqual(value_evidence(reply)[0][:2], ("care", 1))
        self.assertEqual(value_evidence(notice), ())

    def test_a_real_conversation_with_a_neighbour_counts_as_care(self) -> None:
        talk = event("scene.started", at(1), initiator_id="pathos", partner_id="ellis")
        overheard = event("scene.started", at(1), initiator_id="mara", partner_id="rowan")
        self.assertEqual(value_evidence(talk)[0][:2], ("care", 1))
        self.assertEqual(value_evidence(overheard), ())

    def test_one_lived_moment_is_felt_once_per_day(self) -> None:
        history = [missed(1), missed(1.1), missed(2)]
        state = project_selfhood(history)
        self.assertEqual(len(state.evidence), 2)

    def test_mood_counts_once_per_twelve_heavy_hours(self) -> None:
        samples = [
            event("emotion.sampled", at(1, hour), sustained_low_hours=hours)
            for hour, hours in enumerate(range(10, 26))
            if hour < 24
        ]
        felt = [item for item in project_selfhood(samples).evidence if item.value_id == "mood"]
        self.assertEqual(len(felt), 1)


class InquiryTests(unittest.TestCase):
    def test_repeated_neglect_of_a_held_value_opens_one_private_question(self) -> None:
        history = [identity_established_event(at(0).isoformat())] + [
            missed(day) for day in (1, 2, 3, 4)
        ]
        self.assertFalse(
            any(
                item.kind == "self.inquiry_opened"
                for item in selfhood_daily_events(history, at(5, 20))
            ),
            "a few awkward days are not yet a pattern",
        )
        output = selfhood_daily_events(history, at(9, 20))
        opened = [item for item in output if item.kind == "self.inquiry_opened"]
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0].payload["theme"], "reliability")
        self.assertEqual(opened[0].payload["kind"], "tension")
        self.assertIn("?", str(opened[0].payload["question"]))
        self.assertTrue(any(item.kind == "self.chapter_opened" for item in output))
        project_selfhood([*history, *output])  # replay validates what was emitted
        again = selfhood_daily_events([*history, *output], at(10, 20))
        self.assertFalse(any(item.kind == "self.inquiry_opened" for item in again))

    def test_daily_pass_only_runs_in_the_evening(self) -> None:
        history = [missed(day) for day in (1, 2, 3, 4)]
        self.assertEqual(selfhood_daily_events(history, at(5, 9)), [])

    def test_inquiry_cannot_cite_evidence_he_never_lived(self) -> None:
        forged = event(
            "self.inquiry_opened",
            at(2),
            inquiry_id="inquiry-x",
            theme="care",
            question="Why?",
            **source_payload(["not-an-event"]),
        )
        with self.assertRaises(ValueError):
            project_selfhood([forged])

    def test_unrevisited_question_quietly_fades(self) -> None:
        history = [missed(day) for day in (1, 2, 3, 4)]
        history += selfhood_daily_events(history, at(9, 20))
        output = selfhood_daily_events(history, at(31, 20))
        self.assertTrue(any(item.kind == "self.inquiry_faded" for item in output))


def _history_with_open_question() -> list[DomainEvent]:
    history = [identity_established_event(at(0).isoformat())]
    history += [missed(day) for day in (1, 2, 3, 4, 5)]
    history += selfhood_daily_events(history, at(15, 20))
    return history


def _revisit(history: list[DomainEvent], day: float, gateway: object) -> list[DomainEvent]:
    inquiry = inquiry_for_reflection(history, at(day, 21))
    assert inquiry is not None
    note = reflection(day)
    return [
        note,
        *asyncio.run(
            selfhood_after_reflection_events(
                [*history, note],
                note,
                inquiry,
                at(day, 21),
                gateway,  # type: ignore[arg-type]
            )
        ),
    ]


INSIGHT = {
    "mode": "insight",
    "insight": "I think I take on more than my days can hold, and keeping my word matters to me.",
    "value_id": "reliability",
    "direction": 1,
    "aspiration_kind": "hoped",
    "aspiration": "I want my small promises to hold.",
}


class InsightTests(unittest.TestCase):
    def test_insight_needs_repeated_reflection_across_days(self) -> None:
        gateway = FixedGateway(INSIGHT)
        history = _history_with_open_question()
        for day in (15, 16):
            history += _revisit(history, day, gateway)
        self.assertEqual(gateway.requests, [])
        history += _revisit(history, 19, gateway)
        self.assertEqual(len(gateway.requests), 1)
        kinds = [item.kind for item in history]
        self.assertIn("self.insight_formed", kinds)
        self.assertIn("self.value_shifted", kinds)
        self.assertIn("self.aspiration_formed", kinds)
        state = project_selfhood(history)
        self.assertAlmostEqual(developed_values(STARTING_VALUES, state)["reliability"], 0.77)
        self.assertAlmostEqual(project_identity(history).values["reliability"], 0.77)
        context = selfhood_context(history, at(19, 22))
        self.assertEqual(context["hopes"], ["I want my small promises to hold."])
        self.assertEqual(
            context["values_that_have_shifted"],
            [{"value": "reliability", "direction": "matters more"}],
        )

    def test_reflection_is_asked_about_the_question_without_answering_it(self) -> None:
        history = _history_with_open_question()
        inquiry = inquiry_for_reflection(history, at(15, 21))
        assert inquiry is not None
        context = reflection_inquiry_context(history, inquiry)
        self.assertEqual(context["question"], inquiry.question)
        self.assertEqual(context["epistemic_status"], "private_open_question")
        self.assertIn("let something I'd planned slip", context["what_prompted_it"])

    def test_values_do_not_move_in_his_first_fortnight(self) -> None:
        gateway = FixedGateway(INSIGHT)
        history = [identity_established_event(at(0).isoformat())]
        history += [missed(day) for day in (1, 2, 3, 4)]
        history += selfhood_daily_events(history, at(8, 20))
        for day in (8, 10, 12):
            history += _revisit(history, day, gateway)
        kinds = [item.kind for item in history]
        self.assertIn("self.insight_formed", kinds)
        self.assertNotIn("self.value_shifted", kinds)

    def test_keep_wondering_leaves_the_question_open(self) -> None:
        gateway = FixedGateway({**INSIGHT, "mode": "keep_wondering"})
        history = _history_with_open_question()
        for day in (15, 16, 19):
            history += _revisit(history, day, gateway)
        self.assertEqual(len(project_selfhood(history).open_inquiries()), 1)

    def test_replay_rejects_a_value_leap(self) -> None:
        history = _history_with_open_question()
        for day in (15, 16, 19):
            history += _revisit(history, day, FixedGateway(INSIGHT))
        shift = next(item for item in history if item.kind == "self.value_shifted")
        leap = DomainEvent(
            shift.kind, "pathos", {**shift.payload, "next": 0.95}, event_id=shift.event_id
        )
        with self.assertRaises(ValueError):
            project_selfhood([leap if item is shift else item for item in history])


class ProposalValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        history = _history_with_open_question()
        self.state = project_selfhood(history)
        self.inquiry = self.state.open_inquiries()[0]

    def parse(self, **changes: object) -> object:
        return parse_insight_proposal(
            json.dumps({**INSIGHT, **changes}), self.inquiry, self.state, at(20)
        )

    def test_rejects_diagnoses_second_person_and_third_person(self) -> None:
        for text in (
            "I think I might have depression and that explains everything about me.",
            "You always let people down and you know it deep down, honestly.",
            "Patrick has been letting plans slip because he takes on too much.",
        ):
            with self.subTest(text=text), self.assertRaises(ProposalRejected):
                self.parse(insight=text)

    def test_rejects_moving_a_value_his_life_does_not_bear_out(self) -> None:
        with self.assertRaises(ProposalRejected):
            self.parse(value_id="care", direction=1)

    def test_keep_wondering_is_a_valid_answer(self) -> None:
        self.assertIsNone(self.parse(mode="keep_wondering"))

    def test_chapter_titles_must_be_new_names_citing_candidates(self) -> None:
        proposal = json.dumps(
            {"title": "Keeping my word", "summary": "I started noticing it.", "cited": ["a", "b"]}
        )
        with self.assertRaises(ProposalRejected):
            parse_chapter_proposal(proposal, {"a", "b"})
        good = json.dumps(
            {
                "title": "Keeping my word",
                "summary": "I started to notice what my plans cost me when they slipped.",
                "cited": ["a", "b"],
            }
        )
        self.assertEqual(parse_chapter_proposal(good, {"a", "b"})[0], "Keeping my word")
        with self.assertRaises(ProposalRejected):
            parse_chapter_proposal(good, {"a", "b"}, {"keeping my word"})
        with self.assertRaises(ProposalRejected):
            parse_chapter_proposal(good, {"a"})


class StandInSelfhoodTests(unittest.TestCase):
    def test_standin_waits_for_repeated_reflection_then_answers_the_question_kind(self) -> None:
        gateway = StandInGateway()
        history = _history_with_open_question()
        for day in (15, 16, 19, 20, 21, 22):
            if project_selfhood(history).open_inquiries():
                history += _revisit(history, day, gateway)
        insights = [item for item in history if item.kind == "self.insight_formed"]
        self.assertEqual(len(insights), 1)
        self.assertIn("my word", str(insights[0].payload["text"]))
        project_selfhood(history)


if __name__ == "__main__":
    unittest.main()


class StandInVoiceTests(unittest.TestCase):
    def test_he_answers_questions_about_himself_from_his_actual_self_understanding(self) -> None:
        history = _history_with_open_question()
        context = {
            "message": "What's been on your mind lately?",
            "identity": {"selfhood": selfhood_context(history, at(16))},
            "voice": {"cadence": "steady"},
        }
        request = ModelRequest(
            capability="pathos",
            messages=(ModelMessage("user", json.dumps(context)),),
        )
        reply = json.loads(asyncio.run(StandInGateway().generate(request)).content)["text"]
        question = project_selfhood(history).open_inquiries()[0].question
        self.assertIn(question.rstrip("?").lower(), reply)
        self.assertIn("don't have an answer", reply)


class BirthdayTests(unittest.TestCase):
    def test_his_birthday_leaves_one_grounded_memory_a_year(self) -> None:
        evening = datetime(2026, 10, 27, 20, tzinfo=timezone.utc)
        history = [identity_established_event(evening.replace(month=1).isoformat())]
        output = selfhood_daily_events(history, evening)
        memory = next(item for item in output if item.kind == "memory.recorded")
        self.assertEqual(memory.payload["text"], "Turned 28 today.")
        self.assertEqual(memory.payload["category"], "milestone")
        self.assertFalse(
            any(
                item.kind == "self.birthday_marked"
                for item in selfhood_daily_events([*history, *output], evening)
            )
        )
        self.assertEqual(
            [
                item
                for item in selfhood_daily_events(history, evening.replace(day=26))
                if item.kind == "self.birthday_marked"
            ],
            [],
        )


class StandInHonestyTests(unittest.TestCase):
    def reply(self, message: str, **context: object) -> str:
        request = ModelRequest(
            capability="pathos",
            messages=(
                ModelMessage(
                    "user",
                    json.dumps({"message": message, "voice": {"cadence": "steady"}, **context}),
                ),
            ),
        )
        return str(json.loads(asyncio.run(StandInGateway().generate(request)).content)["text"])

    def test_he_never_denies_being_simulated_when_asked_directly(self) -> None:
        for question in ("are you a real person?", "wait, are you an AI", "Are you human?"):
            with self.subTest(question=question):
                self.assertIn("simulated person", self.reply(question.lower()))

    def test_he_talks_about_the_job_he_actually_has(self) -> None:
        reply = self.reply(
            "how's work at the workshop been?",
            time_budget={"next_plan": "Shift at the repair workshop"},
        )
        self.assertIn("Ellis", reply)
