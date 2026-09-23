"""An ordinary day has a shape: he goes home, sleeps there, works his shifts, and eats."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

from eidos.application.economy import financial_consequence_events, financial_foundation_events
from eidos.application.object_supply import (
    FOOD_REORDER_AT,
    WEEKLY_SHOP_PENCE,
    WEEKLY_SHOP_PORTIONS,
    object_supply_events,
)
from eidos.application.personal_journeys import journey_window_events
from eidos.application.work_rota import (
    SHIFT_WAGE_PENCE,
    partial_shift_wage,
    work_rota_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.finances import project_finances
from eidos.domain.identity import identity_established_event
from eidos.domain.planning import CalendarEntry, PlanningState, project_planning
from eidos.domain.world_catalog import project_world_catalog

MONDAY = datetime(2026, 1, 5, tzinfo=timezone.utc)


def at(hour: int, minute: int = 0, day: int = 0) -> datetime:
    return MONDAY + timedelta(days=day, hours=hour, minutes=minute)


def event(kind: str, when: datetime, **payload: object) -> DomainEvent:
    return DomainEvent(kind, "pathos", {**payload, "simulated_at": when.isoformat()})


def at_the_park_since(hour: int) -> list[DomainEvent]:
    return [
        event("sleep.ended", at(7)),
        event("pathos.moved", at(hour), location_id="park", from_location_id="home"),
    ]


def homeward(events: list[DomainEvent]) -> list[DomainEvent]:
    return [
        item
        for item in events
        if item.kind == "pathos.travel_started" and item.payload.get("purpose") == "return_home"
    ]


class TestGoingHome:
    catalog = project_world_catalog([])

    def test_he_heads_home_after_lingering_with_nothing_left_to_do(self) -> None:
        history = at_the_park_since(11)
        early = journey_window_events(history, PlanningState(), self.catalog, at(13), at(13))
        assert homeward(early) == []
        later = journey_window_events(history, PlanningState(), self.catalog, at(14), at(15))
        assert [item.payload["reason"] for item in homeward(later)] == ["nothing more to do there"]
        assert homeward(later)[0].payload["destination_id"] == "home"
        assert any(item.kind == "pathos.moved" for item in later)

    def test_he_heads_home_before_the_bedtime_he_chose(self) -> None:
        history = at_the_park_since(19) + [
            event(
                "sleep.window_selected",
                at(20),
                window_id="sleep:2026-01-05",
                night_date="2026-01-05",
                selected_at=at(20).isoformat(),
                bedtime=at(22).isoformat(),
                wake_at=at(6, day=1).isoformat(),
                reason="a familiar evening rhythm",
            )
        ]
        output = journey_window_events(history, PlanningState(), self.catalog, at(21), at(21))
        assert [item.payload["reason"] for item in homeward(output)] == [
            "heading home for the night"
        ]

    def test_planned_activity_here_keeps_him_until_it_is_wrapped_up(self) -> None:
        entry = CalendarEntry(
            "sketching",
            "Sketch by the pond",
            at(12).isoformat(),
            "park",
            ends_at=at(15).isoformat(),
            actor_id="pathos",
            action="attend",
            target_id="park",
        )
        planning = replace(PlanningState(), calendar={entry.schedule_id: entry})
        history = at_the_park_since(11)
        for hour in (14, 15):
            assert (
                homeward(journey_window_events(history, planning, self.catalog, at(hour), at(hour)))
                == []
            )
        output = journey_window_events(history, planning, self.catalog, at(16), at(16))
        assert len(homeward(output)) == 1

    def test_he_never_leaves_home_to_go_home(self) -> None:
        history = [event("sleep.ended", at(7))]
        assert journey_window_events(history, PlanningState(), self.catalog, at(23), at(23)) == []


class TestWorkRota:
    def history(self) -> list[DomainEvent]:
        return [identity_established_event(at(0).isoformat())]

    def test_the_coming_week_of_shifts_is_published_with_his_intention(self) -> None:
        output = work_rota_events(self.history(), PlanningState(), at(6))
        created = [item for item in output if item.kind == "schedule.created"]
        days = sorted(str(item.payload["schedule_id"])[-10:] for item in created)
        assert days == ["2026-01-05", "2026-01-06", "2026-01-08", "2026-01-09", "2026-01-12"]
        assert all(item.payload["location_id"] == "workshop" for item in created)
        assert all("estimate_confidence" not in item.payload for item in created)
        planning = project_planning([*self.history(), *output])
        assert all(
            planning.intentions[str(item.payload["intention_id"])].status == "active"
            for item in created
        )
        assert work_rota_events([*self.history(), *output], planning, at(7)) == []

    def test_older_lives_whose_identity_came_later_still_get_their_job(self) -> None:
        legacy = [event("time.advanced", at(0)) for _ in range(200)]
        history = [*legacy, identity_established_event(at(0).isoformat())]
        kinds = [item.kind for item in work_rota_events(history, PlanningState(), at(6))]
        assert kinds[0] == "work.agreement_accepted"
        assert "schedule.created" in kinds

    def test_existing_plans_keep_their_time(self) -> None:
        entry = CalendarEntry(
            "dentist",
            "Dentist",
            at(11, day=1).isoformat(),
            "cafe",
            ends_at=at(12, day=1).isoformat(),
            actor_id="pathos",
        )
        planning = replace(PlanningState(), calendar={entry.schedule_id: entry})
        output = work_rota_events(self.history(), planning, at(6))
        ids = {item.payload.get("schedule_id") for item in output}
        assert "work-rota-2026-01-06" not in ids
        assert "work-rota-2026-01-05" in ids

    def test_wages_follow_hours_actually_worked(self) -> None:
        assert partial_shift_wage(3_000) is None
        assert partial_shift_wage(2 * 3600) == 2_200
        assert partial_shift_wage(99 * 3600) == SHIFT_WAGE_PENCE
        history = [*self.history(), *financial_foundation_events([], at(1))]
        done = event(
            "activity.completed",
            at(16),
            activity="work",
            schedule_id="work-rota-2026-01-05",
            location_id="workshop",
        )
        cut_short = event(
            "activity.execution_unfinished",
            at(16, day=1),
            schedule_id="work-rota-2026-01-06",
            worked_seconds=3 * 3600 + 1200.0,
        )
        paid = financial_consequence_events(
            [*history, done, cut_short], project_finances(history), at(17, day=1)
        )
        wages = [
            item.payload["amount_pence"]
            for item in paid
            if item.payload.get("category") == "work_income"
        ]
        assert wages == [SHIFT_WAGE_PENCE, 3_575]


class TestFood:
    def provisions(self, quantity: int) -> list[DomainEvent]:
        return [
            event(
                "object.registered",
                at(1),
                object_id="household-provisions",
                name="Household provisions",
                owner_id="pathos",
                custodian_id="pathos",
                location_id="home",
                condition="usable",
                quantity=12,
                reorder_at=3,
                unit="meal portions",
            ),
            DomainEvent(
                "object.stock_changed",
                "pathos",
                {
                    "object_id": "household-provisions",
                    "from_quantity": 12,
                    "quantity": quantity,
                    "reason": "One meal portion was actually eaten.",
                    "simulated_at": at(8).isoformat(),
                },
                # Fixed so the replay-stable order/go-without sample is deterministic here.
                event_id=UUID("00000000-0000-0000-0000-000000000002"),
            ),
        ]

    def decide(self, history: list[DomainEvent], when: datetime) -> list[DomainEvent]:
        return object_supply_events(
            history,
            when,
            project_planning(history),
            pathos_awake=True,
            pathos_location_id="home",
            pathos_energy=0.8,
            curiosity=0.5,
            values={"reliability": 1.0},
            available_pence=20_000,
        )

    def test_a_weekly_shop_is_ordered_while_two_days_of_food_remain(self) -> None:
        output = self.decide(self.provisions(FOOD_REORDER_AT), at(9))
        order = next(item for item in output if item.kind == "object.replenishment_ordered")
        assert order.payload["restock_quantity"] == FOOD_REORDER_AT + WEEKLY_SHOP_PORTIONS
        assert order.payload["price_pence"] == WEEKLY_SHOP_PENCE

    def test_going_without_is_not_rerolled_every_hour(self) -> None:
        history = self.provisions(FOOD_REORDER_AT)
        first = object_supply_events(
            history,
            at(9),
            project_planning(history),
            pathos_awake=True,
            pathos_location_id="home",
            pathos_energy=0.8,
            curiosity=0.5,
            values={"reliability": 0.0},
            available_pence=0,
        )
        assert [item.payload.get("decision") for item in first] == ["go_without"]
        history += first
        history.append(
            event(
                "object.stock_changed",
                at(12),
                object_id="household-provisions",
                from_quantity=FOOD_REORDER_AT,
                quantity=FOOD_REORDER_AT - 1,
                reason="One meal portion was actually eaten.",
            )
        )
        assert self.decide(history, at(13)) == []
        assert any(
            item.kind == "object.replenishment_decided"
            for item in self.decide(history, at(9, day=1))
        )


class TestEmployerKeepsTheAgreedHours:
    def test_ellis_opens_the_workshop_for_the_shift_and_closes_up_after(self) -> None:
        from eidos.application.npc_movement import npc_movement_events
        from eidos.domain.npcs import project_npcs

        history = [identity_established_event(at(0).isoformat())]
        history += work_rota_events(history, PlanningState(), at(6))

        def ellis_after(when: datetime) -> tuple[str, list[DomainEvent]]:
            output = npc_movement_events(history, when)
            history.extend(output)
            arrived = npc_movement_events(history, when + timedelta(hours=1))
            history.extend(arrived)
            return (
                project_npcs(history, when + timedelta(hours=1)).people["ellis"].location_id,
                [*output, *arrived],
            )

        location, events = ellis_after(at(9, 30))
        assert location == "workshop"
        assert any(
            item.payload.get("reason") == "opening up for the agreed hours" for item in events
        )
        location, events = ellis_after(at(16, 30))
        assert location == "home"
        assert any(item.payload.get("reason") == "closing up for the day" for item in events)
