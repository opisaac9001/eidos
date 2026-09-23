import asyncio
import json

import pytest

from eidos.application.cognition import perform_pathos_reply
from eidos.application.semantic_quality import semantic_quality_findings
from eidos.ports.model_gateway import ModelResponse


@pytest.mark.parametrize(
    "text,completed",
    [
        ("Yeah, they're done. Just finished up.", False),
        ("Yeah, I just finished washing them.", False),
        ("Nah, I've only just started.", True),
    ],
)
def test_measured_current_activity_contradictions(text, completed):
    context = {
        "message": "Did you finish the dishes?",
        "ongoing_activities": [
            {
                "title": "Wash the dishes",
                "schedule_status": "completed" if completed else "scheduled",
            }
        ],
    }
    assert "contradicted_activity_status" in semantic_quality_findings("pathos", text, context)


def test_still_travelling_is_not_an_arrival():
    context = {"message": "Are you there?", "journey": {"remaining_minutes": 1}}
    assert "premature_arrival" in semantic_quality_findings(
        "pathos", "Yeah, just arrived.", context
    )
    assert "premature_arrival" not in semantic_quality_findings(
        "pathos", "Almost there, another minute.", context
    )


def test_completed_substage_and_uncertain_memory_are_not_full_completion():
    context = {
        "message": "Are the dishes done?",
        "ongoing_activities": [
            {
                "title": "Wash the dishes",
                "schedule_status": "scheduled",
                "completed_stages": ["Wash the dishes"],
            }
        ],
    }
    assert "contradicted_activity_status" not in semantic_quality_findings(
        "pathos", "I finished washing, but haven't put them away.", context
    )
    assert "contradicted_activity_status" not in semantic_quality_findings(
        "pathos", "Not yet, still washing.", context
    )
    assert "contradicted_activity_status" not in semantic_quality_findings(
        "pathos", "I remember finishing them yesterday.", {"message": "What do you remember?"}
    )


def test_persistent_contradiction_is_withheld_after_one_revision():
    class Gateway:
        calls = 0

        async def generate(self, request):
            self.calls += 1
            return ModelResponse(
                json.dumps({"text": "Yeah, just arrived."}), "test", "test", "stop"
            )

    gateway = Gateway()
    context = {
        "message": "Are you there?",
        "journey": {"remaining_minutes": 1},
        "time": "2026-01-08T11:00:00+00:00",
    }
    assert asyncio.run(perform_pathos_reply(gateway, context, context["time"], [])) is None
    assert gateway.calls == 2
