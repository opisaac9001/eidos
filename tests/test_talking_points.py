"""Conversations are about what's really going on between two people, and why they're there."""

from datetime import datetime, timedelta, timezone

from eidos.application.freelance import TOLD
from eidos.application.talking_points import setting, talking_points
from eidos.domain.events import DomainEvent

AT = datetime(2026, 9, 1, 11, 30, tzinfo=timezone.utc)


def _told() -> DomainEvent:
    return DomainEvent(
        TOLD,
        "pathos",
        {"employer_id": "ellis", "last_day": "2026-09-08", "simulated_at": AT.isoformat()},
    )


def test_the_morning_he_tells_ellis_its_what_they_talk_about() -> None:
    points = dict(talking_points([_told()], AT, "ellis", "Ellis", "workshop"))
    leaving = points["leaving-the-workshop"]
    assert "freelance" in leaving and "Tuesday 8 September" in leaving


def test_with_anyone_else_its_his_news_to_tell() -> None:
    points = dict(talking_points([_told()], AT, "mara", "Mara", "cafe"))
    assert "going-freelance" in points and "leaving-the-workshop" not in points


def test_on_shift_hes_at_work_not_dropping_in() -> None:
    shift = DomainEvent(
        "schedule.created",
        "pathos",
        {
            "schedule_id": "work-rota-2026-09-01",
            "title": "Shift at the repair workshop",
            "starts_at": (AT - timedelta(hours=1)).isoformat(),
            "ends_at": (AT + timedelta(hours=4)).isoformat(),
            "location_id": "workshop",
            "actor_id": "pathos",
            "simulated_at": (AT - timedelta(days=2)).isoformat(),
        },
    )
    assert "on his shift" in setting([shift], AT, "The workshop", "Ellis")
    assert setting([], AT, "Juniper Café", "Mara") == "Patrick is at Juniper Café"


def test_a_real_model_is_actually_sent_the_setting_and_any_correction() -> None:
    from eidos.adapters.http_gateway import ROLE_FIELDS

    # Unlisted keys never reach a real model (the stand-in sees everything, so only this
    # catches it): the shared-past retry was resent unchanged for months.
    assert {"setting", "revision_instruction", "scene_topic", "his_news"} <= set(
        ROLE_FIELDS["firmament"]
    )


def test_nobody_in_alderwick_calls_him_pathos() -> None:
    import asyncio

    from eidos.adapters.standin_gateway import StandInGateway
    from eidos.application.cognition import perform
    from eidos.ports.model_gateway import ModelResponse

    class SaysPathos(StandInGateway):
        async def generate(self, request):
            return ModelResponse('{"text": "Sure, Pathos. See you at 11."}', "x", "test", "stop")

    pending: list = []
    text = asyncio.run(
        perform(
            SaysPathos(),
            "firmament",
            {
                "person": "Ellis",
                "scene_mode": True,
                "scene_speaker": "ellis",
                "scene_audience": "pathos",
            },
            "2026-09-02T19:00:00+00:00",
            pending,
        )
    )
    assert text == "Sure, Patrick. See you at 11."


def test_his_own_project_is_something_people_can_ask_about() -> None:
    from eidos.application.talking_points import his_projects

    goal = DomainEvent(
        "goal.activated",
        "pathos",
        {
            "goal_id": "pathos-project-atlas",
            "title": "Make a small atlas of neighbourhood sounds",
            "simulated_at": AT.isoformat(),
        },
    )
    assert his_projects([goal]) == ["his own project: Make a small atlas of neighbourhood sounds"]
    points = dict(talking_points([goal], AT, "mara", "Mara", "cafe"))
    assert "his-project-0" in points
