"""News travels round the town, changes a little in the telling, and reaches him second-hand."""

from datetime import datetime, timedelta, timezone

from eidos.application.gossip import (
    HEARD,
    PATRICK,
    gossip_events,
    held,
    patrick_heard,
    they_remember,
    worth_mentioning,
)
from eidos.domain.events import DomainEvent

AT = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
NAMES = {"rowan": "Rowan", "mara": "Mara", "ellis": "Ellis", "beth": "Beth Pritchard"}
RESIDENTS = frozenset(NAMES)


def worry(at: datetime = AT) -> DomainEvent:
    return DomainEvent(
        "friend.life_event",
        "pathos",
        {
            "person_id": "rowan",
            "kind": "family_worry",
            "text": "Rowan told me their mum's not been well.",
            "simulated_at": at.isoformat(),
        },
    )


def test_news_starts_with_the_person_it_is_about() -> None:
    events = gossip_events([worry()], AT, names=NAMES, locations={}, residents=RESIDENTS)
    [claim] = [e for e in events if e.kind == HEARD]
    assert claim.payload["holder_id"] == "rowan" and claim.payload["teller_id"] == ""
    assert claim.payload["text"] == "Rowan's family's going through it; a parent's not well."


def test_it_spreads_between_people_together_and_sometimes_drifts() -> None:
    history = [worry()]
    history += gossip_events(history, AT, names=NAMES, locations={}, residents=RESIDENTS)
    together = {"rowan": "cafe", "mara": "cafe", "ellis": "cafe", "beth": "cafe"}
    for hour in range(1, 40):
        history += gossip_events(
            history,
            AT + timedelta(hours=hour),
            names=NAMES,
            locations=together,
            residents=RESIDENTS,
        )
    holders = {holder for (_, holder) in held(history)}
    assert {"mara", "ellis"} & holders
    # Across many tellings, some stories drift.
    stories = [worry(AT + timedelta(minutes=n)) for n in range(12)]
    many = list(stories)
    many += gossip_events(
        many, AT + timedelta(hours=1), names=NAMES, locations={}, residents=RESIDENTS
    )
    for hour in range(2, 30):
        many += gossip_events(
            many, AT + timedelta(hours=hour), names=NAMES, locations=together, residents=RESIDENTS
        )
    texts = {claim.text for claim in held(many).values()}
    assert "Rowan's mum's in hospital, apparently." in texts
    assert "Rowan's family's going through it; a parent's not well." in texts
    # Nobody at home or alone hears it.
    lonely = [worry()]
    lonely += gossip_events(lonely, AT, names=NAMES, locations={}, residents=RESIDENTS)
    lonely += gossip_events(
        lonely,
        AT + timedelta(hours=1),
        names=NAMES,
        locations={"rowan": "home", "mara": "cafe"},
        residents=RESIDENTS,
    )
    assert {holder for (_, holder) in held(lonely)} == {"rowan"}


def test_he_hears_it_second_hand_and_remembers_who_told_him() -> None:
    claim_heard = DomainEvent(
        HEARD,
        "pathos",
        {
            "claim_id": "news:1",
            "story": "family_worry",
            "subject_id": "rowan",
            "holder_id": "mara",
            "teller_id": "ellis",
            "text": "Rowan's mum's in hospital, apparently.",
            "version": 1,
            "strength": 0.7,
            "simulated_at": AT.isoformat(),
        },
    )
    news = worth_mentioning([claim_heard], "mara", AT + timedelta(hours=2))
    assert news is not None and news.text.endswith("apparently.")
    meeting = DomainEvent("npc.encountered", "pathos", {"person_id": "mara"})
    told = patrick_heard(news, "mara", "Mara", AT + timedelta(hours=2), meeting)
    assert (
        told[1].payload["text"]
        == "Mara told me they'd heard: Rowan's mum's in hospital, apparently."
    )
    after = [claim_heard, *told]
    assert ("news:1", PATRICK) in held(after)
    assert worth_mentioning(after, "mara", AT + timedelta(hours=3)) is None  # already told


def test_residents_remember_their_recent_moments_with_him() -> None:
    met = DomainEvent(
        "npc.encountered",
        "pathos",
        {
            "person_id": "ellis",
            "text": "Ellis asks Pathos whether the hinge ever got oiled.",
            "simulated_at": (AT - timedelta(days=2)).isoformat(),
        },
    )
    assert they_remember([met], "ellis", AT) == [
        "2 days ago: Ellis asks Pathos whether the hinge ever got oiled."
    ]
    assert they_remember([met], "mara", AT) == []


def test_an_encounter_carries_what_they_remember_and_passes_news_on(tmp_path) -> None:
    import asyncio
    import json

    from eidos.adapters.sqlite_store import SQLiteEventStore
    from eidos.adapters.standin_gateway import StandInGateway
    from eidos.application.life import Life
    from eidos.ports.model_gateway import ModelResponse

    class Chatty(StandInGateway):
        def __init__(self) -> None:
            self.contexts: list[dict] = []

        async def generate(self, request):
            if request.capability == "firmament":
                context = json.loads(request.messages[-1].content)
                self.contexts.append(context)
                if context.get("they_might_mention"):
                    said = f"{context['person']} mentions that {context['they_might_mention']}"
                    return ModelResponse(json.dumps({"text": said}), "test", "test", "stop")
            return await super().generate(request)

    gateway = Chatty()
    store = SQLiteEventStore(tmp_path / "world.sqlite3")
    life = Life(store, gateway)
    life.advance(10)
    history = life.history()
    catalog = life._world_catalog(history)
    people = list(catalog.people.values())
    teller, subject = people[0], people[1]
    now = datetime.fromisoformat(life.snapshot()["time"])
    claim = DomainEvent(
        HEARD,
        "pathos",
        {
            "claim_id": "news:test",
            "story": "new_partner",
            "subject_id": subject.person_id,
            "holder_id": teller.person_id,
            "teller_id": "",
            "text": f"{subject.name.split()[0]}'s got serious with someone, apparently.",
            "version": 1,  # drifted in the telling: news to him
            "strength": 0.9,
            "simulated_at": now.isoformat(),
        },
    )
    store.append("pathos", [claim], len(history))
    pending: list = []
    asyncio.run(
        life._meet(
            life.history(), pending, teller, "cafe", now.isoformat(), {"time": now.isoformat()}
        )
    )
    assert "serious with someone" in gateway.contexts[-1]["they_might_mention"]
    assert any(e.kind == HEARD and e.payload["holder_id"] == PATRICK for e in pending)
    assert any(
        e.kind == "memory.recorded" and "told me they'd heard" in e.payload["text"] for e in pending
    )


def test_his_friends_own_news_isnt_served_back_to_him_as_gossip() -> None:
    original = DomainEvent(
        HEARD,
        "pathos",
        {
            "claim_id": "news:2",
            "story": "family_worry",
            "subject_id": "rowan",
            "holder_id": "mara",
            "teller_id": "rowan",
            "text": "Rowan's family's going through it; a parent's not well.",
            "version": 0,
            "strength": 0.8,
            "simulated_at": AT.isoformat(),
        },
    )
    assert worth_mentioning([original], "mara", AT + timedelta(hours=1)) is None
    told = patrick_heard(
        held([original])[("news:2", "mara")], "mara", "Mara", AT, DomainEvent("x", "pathos", {})
    )
    assert told[0].payload["story"] == "family_worry"  # the story travels with it
