"""Scripted choices prove contracts/consequences, not humanlike model behavior."""

import asyncio
import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import pytest

from eidos.application.preparation import preparation_context
from eidos.application.time_budget import personal_time_budget
from eidos.domain.planning import project_planning
from eidos.domain.world_catalog import project_world_catalog
from eidos.ports.model_gateway import ModelResponse

spec = importlib.util.spec_from_file_location(
    "morning_trial", Path(__file__).resolve().parents[1] / "infra/morning_trial.py"
)
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


class ChoiceFixture:
    def __init__(self, minutes=None, location="home", starts=0):
        self.minutes, self.location, self.starts = minutes, location, starts

    async def generate(self, request):
        context = json.loads(request.messages[-1].content)
        if request.capability == "pathos_deliberation":
            field = context["choice_field"]
            if field["attention_capacity"] == 3:
                output = {"no_change": True}
            else:
                dishes = next(
                    item for item in field["attended_impulses"] if item.get("target_id") == "dishes"
                )
                output = {
                    "mode": "pursue",
                    "chosen_impulse_id": dishes["impulse_id"],
                    "intention": "Wash a realistically sized batch of dishes.",
                }
            return ModelResponse(json.dumps(output), "explicit-test-choice", "fixture", "stop")
        minutes = (
            self.minutes
            or {
                15: 5,
                40: 15,
                90: 30,
            }[context["time_budget"]["free_minutes"]]
        )
        output = {
            "activity_type": "household_dishes",
            "title": "Wash a batch of dishes",
            "motivation": "Make some room by the sink before leaving",
            "action": "work",
            "location_id": self.location,
            "resource_id": "none",
            "companion_id": "none",
            "starts_in_hours": self.starts,
            "duration_hours": minutes / 60,
            "estimate_confidence": 1.0,
            "priority": 0.4,
        }
        return ModelResponse(json.dumps(output), "explicit-test-choice", "fixture", "stop")


def test_three_mornings_have_different_work_not_just_different_prose():
    rows = [asyncio.run(trial.run_case(ChoiceFixture(), m)) for m in (15, 40, 90)]
    assert rows[0]["dish_load_after"] > rows[1]["dish_load_after"] > rows[2]["dish_load_after"]
    for row, duration in zip(rows, (5, 15, 30)):
        schedule = next(e["payload"] for e in row["decisions"] if e["kind"] == "schedule.created")
        assert schedule["location_id"] == "home"
        arrivals = [e["payload"] for e in row["execution"] if e["kind"] == "pathos.travel_arrived"]
        assert len(arrivals) == 1
        assert arrivals[0]["simulated_at"] == trial.WORK_START.isoformat()
        stages = [
            e
            for e in row["execution"]
            if e["kind"] == "activity.stage_completed"
            and e["payload"]["activity_type"] == "household_dishes"
        ]
        actual = sum(s["payload"]["required_seconds"] for s in stages)
        assert duration * 60 * 0.92 <= actual <= duration * 60
        assert row["dish_load_after"] == pytest.approx(0.8 - 0.55 * actual / 1800)


def test_tired_and_lonely_can_make_no_new_plan_without_cleaning_or_moving_work():
    row = asyncio.run(trial.run_case(ChoiceFixture(), 40, energy=0.2, connection=0.2))
    assert row["decisions"] == []
    assert row["dish_load_after"] == 0.8
    field = row["calls"][0]["context"]["choice_field"]
    assert field["attention_capacity"] == 3
    assert any(item["kind"] == "inaction" for item in field["attended_impulses"])
    assert any(e["kind"] == "pathos.travel_arrived" for e in row["execution"])


def test_overlong_choice_is_rejected_not_silently_shrunk_or_booked():
    row = asyncio.run(trial.run_case(ChoiceFixture(30), 15))
    assert not any(e["kind"] == "schedule.created" for e in row["decisions"])
    assert any(e["kind"] == "agency.activity_rejected" for e in row["decisions"])
    assert row["dish_load_after"] == 0.8


def test_future_start_still_requires_enough_time_to_reach_the_place():
    row = asyncio.run(trial.run_case(ChoiceFixture(5, "workshop", 1 / 60), 90))
    assert any(e["payload"].get("error_code") == "travel_required" for e in row["decisions"])
    assert not any(e["kind"] == "schedule.created" for e in row["decisions"])


@pytest.mark.parametrize("minutes", [1, 5, 15, 30])
def test_small_reservations_cannot_claim_a_full_batch_of_cleaning(minutes):
    row = asyncio.run(trial.run_case(ChoiceFixture(minutes), 90))
    effects = [e for e in row["execution"] if e["kind"] == "household.task_completed"]
    assert len(effects) == 1
    stages = [
        e
        for e in row["execution"]
        if e["kind"] == "activity.stage_completed"
        and e["payload"]["activity_type"] == "household_dishes"
    ]
    actual = sum(stage["payload"]["required_seconds"] for stage in stages)
    assert effects[0]["payload"]["amount"] == pytest.approx(0.55 * actual / 1800)
    assert row["dish_load_after"] == pytest.approx(0.8 - effects[0]["payload"]["amount"])


def test_preparation_is_local_optional_and_estimates_change_with_fatigue():
    now, history, needs = trial.morning_fixture(15)
    planning, catalog = project_planning(history), project_world_catalog(history)
    budget = personal_time_budget(planning, catalog, now, "home")
    fresh = preparation_context(history, location_id="home", needs=needs, time_budget=budget)
    tired = preparation_context(
        history, location_id="home", needs={**needs, "energy": 0.2}, time_budget=budget
    )
    assert [o["fits_before_departure"] for o in fresh["optional_scales"]] == [True, False, False]
    assert (
        tired["optional_scales"][0]["estimated_minutes"][1]
        > fresh["optional_scales"][0]["estimated_minutes"][1]
    )
    assert (
        preparation_context(history, location_id="park", needs=needs, time_budget=budget)[
            "optional_scales"
        ]
        == []
    )
    assert (
        preparation_context([], location_id="home", needs=needs, time_budget={})["optional_scales"]
        == []
    )
    late = personal_time_budget(planning, catalog, trial.WORK_START - timedelta(minutes=1), "home")
    assert late["free_minutes"] == 0
    assert all(
        not o["fits_before_departure"]
        for o in preparation_context(history, location_id="home", needs=needs, time_budget=late)[
            "optional_scales"
        ]
    )
