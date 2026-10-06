"""His evening reflection, his plans and his encounters stay fresh and concrete."""

import json

import pytest

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life, _encounter_details
from eidos.domain.agency import parse_agency_candidate
from eidos.domain.proposals import ProposalRejected
from eidos.ports.model_gateway import ModelRequest, ModelResponse


def proposal(title: str) -> str:
    return json.dumps(
        {
            "activity_type": "home_noticing",
            "title": title,
            "motivation": "Something about the flat has been nagging at him.",
            "action": "attend",
            "location_id": "home",
            "resource_id": "none",
            "companion_id": "none",
            "starts_in_hours": 0,
            "duration_hours": 1,
            "estimate_confidence": 0.6,
            "priority": 0.4,
        }
    )


@pytest.mark.parametrize(
    "title",
    [
        "Follow something interesting",
        "Follow something interesting that catches my attention at home",
        "Notice an interesting detail in or around the apartment",
    ],
)
def test_a_drive_is_not_a_plan(title: str) -> None:
    with pytest.raises(ProposalRejected, match="concrete"):
        parse_agency_candidate(proposal(title))


def test_a_concrete_thing_to_do_is_a_plan() -> None:
    assert parse_agency_candidate(proposal("Oil the sticking hinge on the kitchen door"))


def test_encounters_leave_recent_details_alone() -> None:
    details = _encounter_details(
        [
            "Ellis hands Pathos a blueprint, eyes darting towards the clock.",
            "Beth Pritchard taps a blueprint against her palm and glances at the clock.",
        ],
        "Ellis",
    )
    assert {"blueprint", "clock"} <= set(details)
    assert "ellis" not in details and "pathos" not in details


def test_the_evening_reflection_is_about_today_and_not_last_nights(tmp_path) -> None:
    class Capturing(StandInGateway):
        def __init__(self) -> None:
            self.requests: list[ModelRequest] = []

        async def generate(self, request: ModelRequest) -> ModelResponse:
            self.requests.append(request)
            return await super().generate(request)

    gateway = Capturing()
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), gateway)
    life.advance(24)
    life.advance(24)
    reflections = [r for r in gateway.requests if r.capability == "reflection"]
    assert len(reflections) >= 2
    tonight = json.loads(reflections[-1].messages[-1].content)
    last_night = [e for e in life.history() if e.kind == "reflection.recorded"][0]
    assert tonight["recent_reflections"][0] == str(last_night.payload["text"])[:240]
    assert tonight["memories"]
