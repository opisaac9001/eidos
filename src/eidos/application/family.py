"""His family: the people he keeps in touch with from a distance.

Patrick grew up in Wye. His mum Helen and dad Richard still live there; his older brother
Tom lives in London with his partner Jess and their daughter Isla. Their lives carry on
off-screen in small, ordinary storylines (Dad's knee, Tom's house hunt, Mum's gallery), and
Patrick only learns what happens when they talk: Mum rings most Sunday evenings, Tom
messages the family chat, Dad comes on the line for a bit. He can miss a call and owe one
back, ring when he's missing them, remember a birthday or forget it and feel it.

Family is not a friendship that deepens or fades with contact. It is always there; what
changes is how in touch he is, what he knows of their lives, and whether he owes someone a
call. Everything is decided by rules from the event history and replay-stable; the models
only voice it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.seasons import _easter
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.world_catalog import WorldCatalog


@dataclass(frozen=True, slots=True)
class Relative:
    person_id: str
    name: str
    called: str  # what Patrick calls them
    relation: str
    birthday: tuple[int, int]  # (month, day)
    about: str
    pronoun: str = "they"


FAMILY: dict[str, Relative] = {
    "mum": Relative(
        "mum",
        "Helen Shaw",
        "Mum",
        "mother",
        (3, 14),
        "Retired from the arts council; gardens, volunteers at a Canterbury gallery, "
        "worries a bit and rings most Sundays.",
        "she",
    ),
    "dad": Relative(
        "dad",
        "Richard Shaw",
        "Dad",
        "father",
        (8, 2),
        "Retired solicitor who restores old clocks in his shed. Dry, not a phone person, and "
        "never quite understood why Patrick left the obvious career path.",
        "he",
    ),
    "tom": Relative(
        "tom",
        "Tom Shaw",
        "Tom",
        "older brother",
        (6, 9),
        "Lives in London with his partner Jess and their daughter Isla. Teases Patrick in "
        "the family chat; closer than either of them lets on.",
        "he",
    ),
}
# People he hears about but doesn't ring himself.
ALSO_FAMILY = {"jess": "Jess, Tom's partner", "isla": "Isla, his niece"}
ISLA_BIRTHDAY = (11, 21)
PARENTS_ANNIVERSARY = (9, 18)

# Their lives, as short storylines he hears about one step at a time.
NEWS: dict[str, tuple[tuple[str, ...], ...]] = {
    "mum": (
        (
            "Mum's volunteering at the gallery again; there's a new exhibition of local "
            "printmakers she's excited about.",
            "The printmakers' exhibition opened. Mum says it was busier than they'd hoped.",
        ),
        ("Mum's allotment neighbour has been stealing her rhubarb, or so she's convinced.",),
        ("Mum's book group is doing a novel she hates. She's going anyway, for the cake.",),
        (
            "Mum went for a check-up about her dizzy spells.",
            "Mum's tests came back fine. She sounded relieved, though she'd said she wasn't worried.",
        ),
        ("Mum's been clearing out the loft and found a box of my old school reports.",),
        ("Mum and Dad are thinking about a week in the Lake District in the spring.",),
    ),
    "dad": (
        (
            "Dad's knee is bad again; he's on the waiting list for an operation.",
            "Dad's got a date for his knee operation. He's pretending it's nothing.",
            "Dad had the operation. Mum says he's a terrible patient.",
            "Dad's walking the long way round to the village again, knee and all.",
        ),
        ("Dad finally got the old longcase clock ticking. He sent a video of it.",),
        ("Dad asked, again, whether the workshop job 'leads anywhere'. Not unkindly, but still.",),
        ("Dad's taken up the crossword in earnest. He rings Mum from the shed for clues.",),
        ("Dad's been asked to help with the village hall accounts, and is quietly pleased.",),
    ),
    "tom": (
        (
            "Tom and Jess are looking at houses outside London; they're tired of renting.",
            "Tom and Jess had an offer accepted on a house in Kent, not far from Mum and Dad.",
            "Tom's moving date is set. He's already asked if I can help carry things.",
            "Tom and Jess are in the new house. Isla has claimed the biggest bedroom.",
        ),
        ("Isla's started nursery and apparently bit someone on the first day.",),
        ("Tom's up for a promotion at work and is being very casual about it.",),
        ("Isla's learned to say my name, sort of. It comes out as 'Pat-pat'.",),
        ("Tom's football team lost again. He's blaming the referee, and the weather.",),
        ("Jess is running a half marathon; Tom's 'training' by buying expensive trainers.",),
    ),
}

# The things that come round every year, heard once a year in their month.
SEASONAL: dict[str, tuple[tuple[int, str], ...]] = {
    "mum": (
        (3, "Mum's seed trays have taken over the kitchen windowsill again."),
        (
            5,
            "Mum's been at the garden centre every weekend. Dad says they're running out of garden.",
        ),
        (7, "Mum says the tomatoes have gone mad this year; she'll post me some chutney."),
        (9, "Mum's gallery is doing its autumn open studios; she's roped Dad into stewarding."),
        (10, "Mum's already asking what I want for Christmas. It's October."),
        (12, "Mum wants to know which train I'm getting at Christmas, and whether I've booked it."),
        (1, "Mum's doing dry January and is not enjoying it."),
    ),
    "dad": (
        (3, "The clocks go forward this weekend, which means Dad has forty clocks to change."),
        (6, "Dad's been sitting out in the garden with the radio and the cricket."),
        (10, "The clocks go back this weekend. Dad has already started, room by room."),
        (11, "Dad's been battling the leaves on the drive, and losing."),
        (12, "Dad's put the old ship's clock on the mantelpiece for Christmas, like every year."),
    ),
    "tom": (
        (4, "Tom took Isla to see the lambs at a farm park; she wasn't sure about them."),
        (8, "Tom, Jess and Isla are off to Cornwall for a week. He's sent a photo of the traffic."),
        (11, "Isla's birthday is coming up and Tom wants ideas that aren't noisy."),
        (12, "Tom's organising Secret Santa for the family, very badly."),
    ),
}
SUNDAY_OPENERS = (
    "Mum rang, as she does on a Sunday.",
    "The Sunday call from Mum.",
    "Mum rang for our Sunday catch-up.",
    "Mum on the phone, Sunday evening, as ever.",
)
QUIET_CALLS = (
    "Not much news; we talked about nothing in particular, which was nice.",
    "Quiet week at home, she said. We talked about the weather and the garden.",
    "Mostly she wanted to know I was eating properly.",
    "She asked about the workshop, and I told her more than I expected to.",
    "Nothing much to report either side. It was still good to hear her.",
)
TOM_CHAT = (
    "Tom sent the family chat a photo of Isla covered in yoghurt.",
    "Tom sent a meme to the family chat. Dad replied with a thumbs up, as always.",
    "Tom asked in the family chat who had the good cake tin. Nobody knew.",
    "Tom sent me a link to a record shop in Hackney 'for next time'.",
    "Tom sent a voice note of Isla singing something that might have been a song.",
    "Tom wanted my opinion on a second-hand drill. I have opinions about drills.",
    "Tom sent a picture of a terrible pun on a shop sign. Mum didn't get it.",
    "Tom asked if I'd seen the match. I hadn't. He told me anyway.",
    "Tom forwarded a very long article Dad sent him, with just 'help'.",
    "Tom sent a photo of Isla's drawing of 'Uncle Pat's workshop'. It was mostly brown.",
    "Tom asked what the name of that old film was, the one with the lighthouse. We never worked it out.",
    "Tom sent the family chat a blurry photo of a fox in their garden at 2am.",
)
SUNDAY_CALL_CHANCE = 0.75
TOM_MESSAGE_DAYS = (1, 3, 5)  # Tuesday, Thursday, Saturday
TOM_MESSAGE_CHANCE = 0.55
TOM_CALL_EVERY = timedelta(days=24)
RING_BACK_WITHIN = timedelta(days=3)


def family_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    at_home: bool,
    in_conversation: bool,
    connection: float,
    values: dict[str, float] | None = None,
) -> list[DomainEvent]:
    """At most one bit of family life this hour."""
    values = values or {}
    return (
        _his_birthday(history, at, awake)
        or _occasion(history, at, awake, values)
        or _sunday_call(history, at, awake, at_home, in_conversation)
        or _ring_back(history, at, awake, in_conversation, values)
        or _missing_them(history, at, awake, in_conversation, connection)
        or _tom(history, at, awake, in_conversation)
    )


def family_context(history: Sequence[DomainEvent], at: datetime) -> list[dict[str, object]]:
    """What he knows of his family right now, for his own voice and thoughts."""
    contacts = events_of(history, "family.contact")
    news = events_of(history, "family.news")
    owed = _owed_calls(history)
    result: list[dict[str, object]] = []
    for relative in FAMILY.values():
        spoke = [
            e
            for e in contacts
            if e.payload.get("person_id") == relative.person_id and not e.payload.get("missed")
        ]
        heard = [e for e in news if e.payload.get("person_id") == relative.person_id]
        last = _time(spoke[-1]) if spoke else None
        result.append(
            {
                "who": f"{relative.called} ({relative.name})",
                "relation": relative.relation,
                "about": relative.about,
                "last_spoke_days_ago": (at - last).days if last else None,
                "latest_news": [str(e.payload["text"]) for e in heard[-2:]],
                "owes_them_a_call": relative.person_id in owed,
            }
        )
    return result


# -- the Sunday call -------------------------------------------------------------------


def _sunday_call(
    history: Sequence[DomainEvent],
    at: datetime,
    awake: bool,
    at_home: bool,
    in_conversation: bool,
) -> list[DomainEvent]:
    if at.weekday() != 6 or at.hour != _hour_for("mum-sunday", at, 17, 19):
        return []
    week = at.isocalendar()
    call_id = f"mum-sunday-{week.year}-W{week.week:02d}"
    if _roll(call_id) >= SUNDAY_CALL_CHANCE or _happened(history, call_id):
        return []
    answer = 0.0 if not awake else 0.1 if in_conversation else 0.95 if at_home else 0.6
    if _roll(call_id, "answer") >= answer:
        return _contact(
            call_id,
            "mum",
            at,
            channel="call",
            incoming=True,
            missed=True,
            text="Missed a call from Mum. Must ring her back.",
        )
    news = _news(history, at, "mum", call_id, chance=0.7)
    dad_news = (
        _news([*history, *news], at, "dad", call_id + "-dad", chance=0.45)
        if _roll(call_id, "dad on") < 0.5
        else []
    )
    together = [
        e
        for e in events_of(history, "family.contact")
        if e.payload.get("channel") == "in_person" and at - _time(e) <= timedelta(days=3)
    ]
    if together:
        # Just back from a visit, the Sunday call is to check he got home.
        return _contact(
            call_id,
            "mum",
            at,
            channel="call",
            incoming=True,
            text="Mum rang to check I'd got back alright, and to say the house was quiet now.",
        )
    parts = [_fresh(history, SUNDAY_OPENERS, call_id)]
    parts += [str(e.payload["text"]) for e in news if e.kind == "family.news"]
    if dad_news:
        parts.append("Dad came on for a bit.")
        parts += [str(e.payload["text"]) for e in dad_news if e.kind == "family.news"]
    elif not news:
        parts.append(_fresh(history, QUIET_CALLS, call_id + "-quiet"))
    return [
        *_contact(call_id, "mum", at, channel="call", incoming=True, text=" ".join(parts)),
        *news,
        *dad_news,
    ]


def _ring_back(
    history: Sequence[DomainEvent],
    at: datetime,
    awake: bool,
    in_conversation: bool,
    values: dict[str, float],
) -> list[DomainEvent]:
    """He rings back a missed call, usually within a day or two, if he gets round to it."""
    if not awake or in_conversation or not 10 <= at.hour <= 20:
        return []
    for person_id, missed in _owed_calls(history).items():
        waited = at - _time(missed)
        if waited < timedelta(hours=3):
            continue
        call_id = f"ringback-{missed.payload['contact_id']}"
        if waited > RING_BACK_WITHIN and not _happened(history, f"{call_id}-lapsed"):
            called = FAMILY[person_id].called
            return [
                DomainEvent(
                    "family.call_owed",
                    "pathos",
                    {
                        "contact_id": f"{call_id}-lapsed",
                        "person_id": person_id,
                        "text": f"Still haven't rung {called} back. It's been days.",
                        "simulated_at": at.isoformat(),
                        "owner": "pathos",
                    },
                    correlation_id=call_id,
                ),
                _memory(f"Still haven't rung {called} back. It's been days.", at, person_id, 0.45),
            ]
        # Caring and reliable people ring back sooner; nobody manages it every time.
        chance = 0.25 * (
            0.12 + 0.12 * values.get("care", 0.78) + 0.08 * values.get("reliability", 0.74)
        )
        if _roll(call_id, at.isoformat()) >= chance:
            continue
        news = _news(history, at, person_id, call_id, chance=0.6)
        called = FAMILY[person_id].called
        text = f"Rang {called} back." + "".join(
            f" {e.payload['text']}" for e in news if e.kind == "family.news"
        )
        return [
            *_contact(call_id, person_id, at, channel="call", incoming=False, text=text),
            *news,
        ]
    return []


def _missing_them(
    history: Sequence[DomainEvent],
    at: datetime,
    awake: bool,
    in_conversation: bool,
    connection: float,
) -> list[DomainEvent]:
    """Now and then, on a quiet evening, he rings home because he wants to."""
    if not awake or in_conversation or at.hour != 19 or at.weekday() == 6:
        return []
    last = _last_spoke(history, "mum")
    if last is not None and at - last < timedelta(days=9):
        return []
    call_id = f"ring-home-{at.date().isoformat()}"
    if _roll(call_id) >= 0.1 + 0.3 * (1 - connection):
        return []
    person_id = "dad" if _roll(call_id, "who") < 0.2 else "mum"
    news = _news(history, at, person_id, call_id, chance=0.7)
    opener = (
        "Rang Dad, which I don't do often enough. He sounded pleased, in his way."
        if person_id == "dad"
        else "Rang Mum for no reason. She was delighted and pretended not to be."
    )
    text = opener + "".join(f" {e.payload['text']}" for e in news if e.kind == "family.news")
    return [*_contact(call_id, person_id, at, channel="call", incoming=False, text=text), *news]


def _tom(
    history: Sequence[DomainEvent], at: datetime, awake: bool, in_conversation: bool
) -> list[DomainEvent]:
    if not awake or at.hour != _hour_for("tom", at, 12, 21):
        return []
    last_call = _last_spoke(history, "tom", channel="call")
    if (
        at.weekday() == 5
        and (last_call is None or at - last_call >= TOM_CALL_EVERY)
        and not in_conversation
    ):
        call_id = f"tom-call-{at.date().isoformat()}"
        news = _news(history, at, "tom", call_id, chance=0.8)
        text = "Long call with Tom. He took the mick, I took it back, and it was good." + "".join(
            f" {e.payload['text']}" for e in news if e.kind == "family.news"
        )
        return [*_contact(call_id, "tom", at, channel="call", incoming=True, text=text), *news]
    if at.weekday() not in TOM_MESSAGE_DAYS:
        return []
    message_id = f"tom-chat-{at.date().isoformat()}"
    if _roll(message_id) >= TOM_MESSAGE_CHANCE:
        return []
    news = _news(history, at, "tom", message_id, chance=0.35)
    if news:
        text = "Tom in the family chat: " + " ".join(
            str(e.payload["text"]) for e in news if e.kind == "family.news"
        )
    else:
        text = _fresh(history, TOM_CHAT, message_id)
    return [*_contact(message_id, "tom", at, channel="message", incoming=True, text=text), *news]


# -- birthdays and occasions -----------------------------------------------------------


def _occasions(year: int) -> dict[date, tuple[str, str, str]]:
    """date -> (occasion id, person, how he'd put it)."""
    easter = _easter(year)
    fathers_day = date(year, 6, 15) + timedelta(days=(6 - date(year, 6, 15).weekday()) % 7)
    found = {
        date(year, *FAMILY["mum"].birthday): ("mum-birthday", "mum", "Mum's birthday"),
        date(year, *FAMILY["dad"].birthday): ("dad-birthday", "dad", "Dad's birthday"),
        date(year, *FAMILY["tom"].birthday): ("tom-birthday", "tom", "Tom's birthday"),
        date(year, *ISLA_BIRTHDAY): ("isla-birthday", "tom", "Isla's birthday"),
        date(year, *PARENTS_ANNIVERSARY): ("anniversary", "mum", "Mum and Dad's anniversary"),
        easter - timedelta(days=21): ("mothering-sunday", "mum", "Mothering Sunday"),
        fathers_day: ("fathers-day", "dad", "Father's Day"),
    }
    return found


def _occasion(
    history: Sequence[DomainEvent], at: datetime, awake: bool, values: dict[str, float]
) -> list[DomainEvent]:
    """Remember the day, or forget it and realise the next morning."""
    if not awake or at.hour != 10:
        return []
    today = at.date()
    for day, (occasion, person_id, label) in _occasions(today.year).items():
        occasion_id = f"{occasion}-{day.year}"
        if day == today and not _happened(history, occasion_id):
            remembered = (
                0.72 + 0.1 * values.get("care", 0.78) + 0.1 * values.get("reliability", 0.74)
            )
            if _roll(occasion_id) < remembered:
                return _marked(occasion_id, person_id, label, at, remembered=True)
            return [
                DomainEvent(
                    "family.occasion",
                    "pathos",
                    {
                        "occasion_id": occasion_id,
                        "person_id": person_id,
                        "outcome": "slipped_his_mind",
                        "label": label,
                        "simulated_at": at.isoformat(),
                        "owner": "pathos",
                    },
                    correlation_id=occasion_id,
                )
            ]
        if day == today - timedelta(days=1):
            slipped = [
                e
                for e in events_of(history, "family.occasion")
                if e.payload.get("occasion_id") == occasion_id
                and e.payload.get("outcome") == "slipped_his_mind"
            ]
            if slipped and not _happened(history, f"{occasion_id}-late"):
                return _marked(f"{occasion_id}-late", person_id, label, at, remembered=False)
    return []


def _his_birthday(history: Sequence[DomainEvent], at: datetime, awake: bool) -> list[DomainEvent]:
    """Home rings on his birthday; they never forget."""
    if not awake or (at.month, at.day) != (10, 27) or at.hour != 9:
        return []
    contact_id = f"his-birthday-{at.year}"
    if _happened(history, contact_id):
        return []
    text = (
        "Mum and Dad rang first thing to sing, badly. Dad asked what I'd done with my "
        "twenties so far. Tom sent a photo of Isla holding a card she'd scribbled for me."
    )
    return _contact(contact_id, "mum", at, channel="call", incoming=True, text=text)


def _marked(
    occasion_id: str, person_id: str, label: str, at: datetime, *, remembered: bool
) -> list[DomainEvent]:
    called = FAMILY[person_id].called
    if remembered:
        text = (
            f"{label} today. Rang {called} first thing; {FAMILY[person_id].pronoun} "
            "sounded chuffed."
            if "birthday" in occasion_id and not occasion_id.startswith("isla")
            else f"{label}. Sent a message and rang later; it was nice to hear everyone."
        )
    else:
        text = (
            f"Realised this morning I'd completely forgotten {label} yesterday. "
            f"Rang {called} full of apologies. They were gracious about it, which made it worse."
        )
    occasion = DomainEvent(
        "family.occasion",
        "pathos",
        {
            "occasion_id": occasion_id,
            "person_id": person_id,
            "outcome": "remembered" if remembered else "forgot",
            "label": label,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=occasion_id,
    )
    return [
        occasion,
        *_contact(occasion_id + "-call", person_id, at, channel="call", incoming=False, text=text),
    ]


# -- helpers ---------------------------------------------------------------------------


def _news(
    history: Sequence[DomainEvent], at: datetime, person_id: str, salt: str, *, chance: float
) -> list[DomainEvent]:
    """Whatever has happened in their life since he last heard, one step at a time."""
    if _roll(salt, "news") >= chance:
        return []
    heard = {str(e.payload.get("news_id")) for e in events_of(history, "family.news")}
    last_heard = {
        str(e.payload.get("story")): _time(e)
        for e in events_of(history, "family.news")
        if e.payload.get("person_id") == person_id
    }
    stories = NEWS[person_id]
    # Carry on an unfinished storyline if a fortnight has passed since the last step.
    for index, story in enumerate(stories):
        story_id = f"{person_id}-{index}"
        done = [step for step in range(len(story)) if f"{story_id}-{step}" in heard]
        if done and len(done) < len(story):
            if at - last_heard[story_id] >= timedelta(days=14):
                return [_heard(person_id, story_id, len(done), story[len(done)], at)]
    fresh = [index for index in range(len(stories)) if f"{person_id}-{index}-0" not in heard]
    if not fresh or _roll(salt, "seasonal") < 0.35:
        # The things that come round every year: once a year each, in their season.
        seasonal = [
            (item_index, text)
            for item_index, (month, text) in enumerate(SEASONAL.get(person_id, ()))
            if month == at.month and f"{person_id}-season-{item_index}-{at.year}-0" not in heard
        ]
        if seasonal:
            item_index, text = seasonal[int(_roll(salt, "which season") * len(seasonal))]
            return [_heard(person_id, f"{person_id}-season-{item_index}-{at.year}", 0, text, at)]
        if not fresh:
            return []
    index = fresh[int(_roll(salt, "story") * len(fresh))]
    return [_heard(person_id, f"{person_id}-{index}", 0, stories[index][0], at)]


def _heard(person_id: str, story_id: str, step: int, text: str, at: datetime) -> DomainEvent:
    return DomainEvent(
        "family.news",
        "pathos",
        {
            "news_id": f"{story_id}-{step}",
            "story": story_id,
            "step": step,
            "person_id": person_id,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=story_id,
    )


def _contact(
    contact_id: str,
    person_id: str,
    at: datetime,
    *,
    channel: str,
    incoming: bool,
    text: str,
    missed: bool = False,
) -> list[DomainEvent]:
    contact = DomainEvent(
        "family.contact",
        "pathos",
        {
            "contact_id": contact_id,
            "person_id": person_id,
            "channel": channel,
            "direction": "incoming" if incoming else "outgoing",
            "missed": missed,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=contact_id,
    )
    return [contact, _memory(text, at, person_id, 0.35 if missed else 0.5, contact)]


def _memory(
    text: str,
    at: datetime,
    person_id: str,
    importance: float,
    source: DomainEvent | None = None,
) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "family",
            "source": "lived-family",
            "family_member": person_id,
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
            **({"source_event_id": str(source.event_id)} if source else {}),
        },
        causation_id=source.event_id if source else None,
        correlation_id=source.correlation_id if source else None,
    )


def _owed_calls(history: Sequence[DomainEvent]) -> dict[str, DomainEvent]:
    """Missed calls he hasn't returned yet (and hasn't spoken to them since)."""
    owed: dict[str, DomainEvent] = {}
    for event in events_of(history, "family.contact"):
        person_id = str(event.payload.get("person_id"))
        if event.payload.get("missed"):
            owed[person_id] = event
        elif person_id in owed:
            del owed[person_id]
    return owed


def _last_spoke(
    history: Sequence[DomainEvent], person_id: str, channel: str | None = None
) -> datetime | None:
    for event in reversed(events_of(history, "family.contact")):
        payload = event.payload
        if (
            payload.get("person_id") == person_id
            and not payload.get("missed")
            and (channel is None or payload.get("channel") == channel)
        ):
            return _time(event)
    return None


def _happened(history: Sequence[DomainEvent], contact_id: str) -> bool:
    return any(
        e.payload.get("contact_id") == contact_id or e.payload.get("occasion_id") == contact_id
        for e in events_of(
            history, "family.contact", "family.occasion", "family.call_owed", "family.plan_agreed"
        )
    )


def _hour_for(salt: str, at: datetime, first: int, last: int) -> int:
    return first + int(_roll(salt, at.date().isoformat(), "hour") * (last - first + 1))


def _fresh(history: Sequence[DomainEvent], options: tuple[str, ...], salt: str) -> str:
    """One of several ways it goes, not one he has heard in his last few weeks."""
    recent = {
        str(event.payload.get("text")) for event in events_of(history, "family.contact")[-12:]
    }
    choices = [option for option in options if not any(option in text for text in recent)]
    pool = choices or list(options)
    return pool[int(_roll(salt, "fresh") * len(pool))]


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


# -- Christmas at home -----------------------------------------------------------------

FAMILY_HOME = "wye-home"
TRAIN_MINUTES = 150
CHRISTMAS_ARRIVES = (12, 23, 19)  # month, day, hour he gets in, after the train
CHRISTMAS_LEAVES = (12, 27, 12)
_CHRISTMAS = {
    (12, 24, 19): (
        "Christmas Eve at home. Dad's clocks all chimed seven slightly out of time with each "
        "other, like every year. Mum made too much food, like every year.",
    ),
    (12, 25, 14): (
        "Christmas Day. Isla opened everything, including other people's presents. Dad fell "
        "asleep in the film and denied it.",
        "Christmas Day. Tom and I did the washing up and actually talked, for once.",
    ),
    (12, 26, 11): (
        "Boxing Day walk along the Stour with Tom. Cold, muddy, and exactly what I needed.",
        "Boxing Day. Helped Dad with a clock he's restoring; he let me do the fiddly bit.",
    ),
}
_DADS_QUESTION = (
    " Dad asked about my 'long-term plans' over the pudding. I changed the subject; "
    "Mum changed it again for me."
)


def christmas_events(
    history: Sequence[DomainEvent],
    at: datetime,
    catalog: WorldCatalog,
    *,
    awake: bool,
    location_id: str,
) -> list[DomainEvent]:
    """Agreeing to come home for Christmas, and Christmas itself once he's there."""
    return _agree_christmas(history, at, catalog, awake) or _christmas_at_home(
        history, at, awake, location_id
    )


def _agree_christmas(
    history: Sequence[DomainEvent], at: datetime, catalog: WorldCatalog, awake: bool
) -> list[DomainEvent]:
    """Early December, Mum asks about Christmas and he books the train home."""
    if not awake or at.month != 12 or at.day != 6 or at.hour != 19:
        return []
    plan_id = f"christmas-{at.year}"
    if _happened(history, plan_id):
        return []
    arrives = at.replace(month=12, day=CHRISTMAS_ARRIVES[1], hour=CHRISTMAS_ARRIVES[2])
    leaves = at.replace(month=12, day=CHRISTMAS_LEAVES[1], hour=CHRISTMAS_LEAVES[2])
    text = (
        "Mum asked about Christmas. Booked the train home for the 23rd, back on the 27th. "
        "Already looking forward to it more than I'll admit."
    )
    agreed = DomainEvent(
        "family.plan_agreed",
        "pathos",
        {
            "contact_id": plan_id,
            "person_id": "mum",
            "text": text,
            "starts_at": arrives.isoformat(),
            "ends_at": leaves.isoformat(),
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=plan_id,
    )
    output = [agreed]
    if FAMILY_HOME not in catalog.places:
        output.append(_register_family_home(catalog, at, agreed))
    intention_id = f"{plan_id}-intention"
    output += [
        DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "proposal_id": plan_id,
                "intention_id": intention_id,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": FAMILY_HOME,
                "goal_id": None,
                "priority": 0.9,
                "motivation": "Christmas at home with Mum, Dad, Tom, Jess and Isla.",
                "simulated_at": at.isoformat(),
            },
            causation_id=agreed.event_id,
            correlation_id=plan_id,
        ),
        DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": plan_id,
                "intention_id": intention_id,
                "title": "Christmas at Mum and Dad's",
                "starts_at": arrives.isoformat(),
                "ends_at": leaves.isoformat(),
                "location_id": FAMILY_HOME,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": FAMILY_HOME,
                "resource_id": None,
                "companion_id": None,
                "activity_type": "christmas_at_home",
                "source": "family-plan",
                "simulated_at": at.isoformat(),
            },
            causation_id=agreed.event_id,
            correlation_id=plan_id,
        ),
        _memory(text, at, "mum", 0.55, agreed),
    ]
    return output


def _register_family_home(catalog: WorldCatalog, at: datetime, cause: DomainEvent) -> DomainEvent:
    from eidos.application.town_pack import _free_spot

    occupied = [(place.x, place.y) for place in catalog.places.values()]
    x, y = _free_spot(92, 92, occupied)
    return DomainEvent(
        "world.place_registered",
        "pathos",
        {
            "entity_id": FAMILY_HOME,
            "entity_kind": "place",
            "name": "Mum and Dad's, Wye",
            "label": "Wye",
            "description": "The house he grew up in: Dad's clocks on every wall, the good "
            "biscuits in the tin, and his old room with the same curtains.",
            "connected_to_id": "station" if "station" in catalog.places else "home",
            "x": x,
            "y": y,
            "opens_hour": 0,
            "closes_hour": 24,
            "travel_minutes": TRAIN_MINUTES,
            "purpose": "His parents' home, a train ride away.",
            "origin": "family",
            "simulated_at": at.isoformat(),
        },
        causation_id=cause.event_id,
        correlation_id=cause.correlation_id,
    )


def _christmas_at_home(
    history: Sequence[DomainEvent], at: datetime, awake: bool, location_id: str
) -> list[DomainEvent]:
    if not awake or location_id != FAMILY_HOME:
        return []
    options = _CHRISTMAS.get((at.month, at.day, at.hour))
    if options is None:
        return []
    contact_id = f"christmas-{at.date().isoformat()}"
    if _happened(history, contact_id):
        return []
    text = options[int(_roll(contact_id, "which") * len(options))]
    if at.day == 25 and _roll(contact_id, "dad") < 0.4:
        text += _DADS_QUESTION
    return _contact(contact_id, "mum", at, channel="in_person", incoming=True, text=text)
