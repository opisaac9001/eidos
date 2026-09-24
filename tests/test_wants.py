"""Money becomes part of a life: wants grow from who he is, and are saved for."""

from datetime import datetime, timedelta, timezone

from eidos.application.economy import financial_consequence_events, financial_foundation_events
from eidos.application.wants import GIVE_UP_AFTER, RESERVE_PENCE, want_events
from eidos.domain.events import DomainEvent
from eidos.domain.finances import project_finances
from eidos.domain.planning import project_planning
from eidos.domain.selfhood import value_evidence

SATURDAY = datetime(2026, 1, 17, 11, tzinfo=timezone.utc)


def lived_craft(days: int = 16) -> list[DomainEvent]:
    return [
        DomainEvent(
            "activity.completed",
            "pathos",
            {
                "activity": "work",
                "schedule_id": f"work-{day}",
                "simulated_at": (SATURDAY - timedelta(days=day)).isoformat(),
            },
        )
        for day in range(days, 0, -1)
    ]


def formed(history: list[DomainEvent]) -> DomainEvent:
    output = want_events(history, SATURDAY, balance_pence=0, location_id="home", awake=True)
    assert [item.kind for item in output] == ["want.formed"]
    return output[0]


def test_what_he_has_been_living_points_toward_one_ordinary_thing() -> None:
    want = formed(lived_craft())
    assert want.payload["option_id"] == "hand-plane"
    assert want.payload["value_id"] == "craft"
    assert (
        want_events(lived_craft(3), SATURDAY, balance_pence=0, location_id="home", awake=True) == []
    )


def test_he_sits_with_it_saves_a_cushion_and_buys_on_a_free_day_out() -> None:
    history = lived_craft()
    history.append(formed(history))
    price = int(history[-1].payload["price_pence"])
    rich = price + RESERVE_PENCE
    wednesday = SATURDAY + timedelta(days=4, hours=2)
    assert (
        want_events(
            history,
            SATURDAY + timedelta(days=1),
            balance_pence=rich,
            location_id="park",
            awake=True,
        )
        == []
    )
    assert (
        want_events(history, wednesday, balance_pence=rich - 1, location_id="park", awake=True)
        == []
    )
    assert want_events(history, wednesday, balance_pence=rich, location_id="home", awake=True) == []
    monday = SATURDAY + timedelta(days=9, hours=2)
    assert want_events(history, monday, balance_pence=rich, location_id="park", awake=True) == []
    bought = want_events(history, wednesday, balance_pence=rich, location_id="park", awake=True)
    assert [item.kind for item in bought] == [
        "want.purchased",
        "object.registered",
        "memory.recorded",
    ]
    assert value_evidence(bought[0])[0][:2] == ("craft", 1)
    planning = project_planning([*history, *bought])
    assert planning.objects["owned-hand-plane"].owner_id == "pathos"
    assert (
        want_events(
            [*history, *bought],
            wednesday + timedelta(hours=1),
            balance_pence=rich,
            location_id="park",
            awake=True,
        )
        == []
    )


def test_the_purchase_is_charged_to_the_household_ledger() -> None:
    history = [*lived_craft(), *financial_foundation_events([], SATURDAY - timedelta(days=30))]
    history.append(formed(history))
    wednesday = SATURDAY + timedelta(days=4, hours=2)
    history += want_events(history, wednesday, balance_pence=99_999, location_id="park", awake=True)
    money = financial_consequence_events(history, project_finances(history), wednesday)
    charged = [item for item in money if item.payload.get("category") == "personal_purchase"]
    assert charged and charged[0].payload["amount_pence"] == -6_000


def test_a_want_that_stays_out_of_reach_is_let_go() -> None:
    history = lived_craft()
    history.append(formed(history))
    later = SATURDAY + GIVE_UP_AFTER
    output = want_events(history, later, balance_pence=0, location_id="park", awake=True)
    assert [item.kind for item in output] == ["want.released"]


def test_what_he_bought_turns_up_in_what_he_chooses_to_do() -> None:
    import asyncio
    import json

    from eidos.adapters.standin_gateway import StandInGateway
    from eidos.ports.model_gateway import ModelMessage, ModelRequest

    chosen = set()
    for hour in range(24):
        context = {
            "time": (SATURDAY + timedelta(hours=hour)).isoformat(),
            "known_places": {"home": {"opens_hour": 0, "closes_hour": 24}},
            "known_people": {},
            "calendar": [],
            "usable_resources": {"owned-film-camera": {"location_id": "home"}},
        }
        request = ModelRequest(
            capability="pathos_agency",
            messages=(ModelMessage("user", json.dumps(context)),),
            output_schema={"type": "object"},
        )
        content = json.loads(asyncio.run(StandInGateway().generate(request)).content)
        chosen.add(content.get("resource_id"))
    assert "owned-film-camera" in chosen


def test_he_can_say_what_he_is_saving_for() -> None:
    import asyncio
    import json

    from eidos.adapters.standin_gateway import StandInGateway
    from eidos.application.selfhood import selfhood_context
    from eidos.ports.model_gateway import ModelMessage, ModelRequest

    history = lived_craft()
    history.append(formed(history))
    context = {
        "message": "are you saving for anything?",
        "voice": {"cadence": "steady"},
        "identity": {"selfhood": selfhood_context(history, SATURDAY)},
    }
    request = ModelRequest(
        capability="pathos", messages=(ModelMessage("user", json.dumps(context)),)
    )
    reply = json.loads(asyncio.run(StandInGateway().generate(request)).content)["text"]
    assert "hand plane" in reply


def taste(subject: str, stance: str, label: str) -> DomainEvent:
    return DomainEvent(
        "taste.formed",
        "pathos",
        {
            "subject": subject,
            "label": label,
            "stance": stance,
            "simulated_at": (SATURDAY - timedelta(days=2)).isoformat(),
        },
    )


def test_what_he_has_found_he_loves_shapes_what_he_wants() -> None:
    want = formed([*lived_craft(), taste("place:cafe", "likes", "Juniper Café")])
    assert want.payload["option_id"] == "coffee-grinder"
    assert want.payload["reason"].startswith("I've found I love Juniper Café.")


def test_he_does_not_want_something_tied_to_what_he_has_gone_off() -> None:
    cared = [
        DomainEvent(
            "follow_up.completed",
            "pathos",
            {"simulated_at": (SATURDAY - timedelta(days=day)).isoformat()},
        )
        for day in range(16, 0, -1)
    ]
    assert formed(cared).payload["option_id"] == "cookbook"
    put_off = [*cared, taste("activity:recipe_annotation", "dislikes", "annotating recipes")]
    output = want_events(put_off, SATURDAY, balance_pence=0, location_id="home", awake=True)
    assert all(item.payload.get("option_id") != "cookbook" for item in output)
