"""Opinions about his town: the ordinary rows that come up in a place like Alderwick.

Every few months there is something: the old mill going to flats, the 12 bus being cut, a
coffee chain after the empty unit on Market Row. He hears about it the way people do (the
noticeboard, the paper, someone at the café) and forms a view from what matters to him:
care pulls one way, craft or curiosity another. It is his view, held with some strength,
and it can change. The public meeting at the council rooms may turn him, if he goes, and
he goes if he cares enough and is curious enough. Talking it over with Ellis at the bench
may turn him too; Ellis has a view on everything, fixed and usually a bit contrary.

Some months later the council decides. He is pleased or disappointed, as much as he cared,
and it becomes part of the town's history as he knows it. Only one issue is live at a time,
and there are only a handful, over a few years: it is background, not a campaign.

The town's side is recorded as ``town.issue`` (``raised``, ``meeting``, ``decided``), his
as ``opinion.formed``, ``opinion.changed``, ``opinion.discussed`` and ``opinion.outcome``,
and deciding to go to the meeting as ``town.meeting_planned``, which the booking cites.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

KIND = "town.issue"
FORMED = "opinion.formed"
CHANGED = "opinion.changed"
DISCUSSED = "opinion.discussed"
OUTCOME = "opinion.outcome"
PLANNED = "town.meeting_planned"
OPINION_KINDS = (FORMED, CHANGED)

SETTLED_FOR = timedelta(days=100)  # a few months in town before he notices the rows
FIRST_SPREAD = 50  # days of variation in when the first one comes up
GAP_DAYS = 120  # one issue every four to six months
GAP_SPREAD = 60
MEETING_AFTER = (21, 35)  # days from hearing about it to the public meeting
DECIDED_AFTER = (45, 84)  # days from the meeting to the council's decision
RAISE_HOUR = 13
TALK_HOUR = 12
DECISION_HOUR = 18
REVIEW_HOUR = 22
HOURS = frozenset({TALK_HOUR, RAISE_HOUR, DECISION_HOUR, REVIEW_HOUR})
MEETING_HOUR = 19
NOISE = 0.3  # how far his lean may sit from what his values alone would say
TORN_BELOW = 0.1
ATTEND_BAR = 0.25
MEETING_PULL = 0.35
ELLIS_PULL = 0.3
TALK_CHANCE = 0.03  # per shift lunchtime while an issue is live
RECENT = timedelta(days=180)

# where he hears about it -> how he'd say so
SOURCES = {
    "the noticeboard outside the post office": "Saw a notice outside the post office about",
    "the Advertiser": "Read in the Advertiser about",
    "someone at the café": "Someone at the café was going on about",
}
ROOMS = (
    "Standing room only. A man in a fleece read out a letter from 1974 and got a round of "
    "applause.",
    "About forty people and one very tired councillor. It got heated for a bit, then "
    "everyone went home.",
    "Half the town turned up. Someone's nan told the chairman he ought to be ashamed, and "
    "he looked like he agreed.",
)


@dataclass(frozen=True, slots=True)
class Issue:
    issue_id: str
    title: str
    topic: str  # mid-sentence, what the row is about
    description: str
    for_case: str
    against_case: str
    for_values: tuple[tuple[str, float], ...]
    against_values: tuple[tuple[str, float], ...]
    words_for: str
    words_against: str
    words_torn: str
    ellis_side: str  # "for" or "against", fixed
    ellis_says: str
    approve_odds: float
    approved: str
    rejected: str


ISSUES = (
    Issue(
        "old-mill-flats",
        "Flats in the old mill",
        "the old mill being turned into flats",
        "A developer wants to turn the empty upper floors of the old mill into two dozen "
        "flats. The museum would keep its two rooms downstairs.",
        "People need somewhere to live that isn't an estate by the bypass, and an empty "
        "building just rots.",
        "It's the last of the mill buildings. They'll gut the old timber and squeeze the "
        "museum into a corner.",
        (("care", 0.7), ("autonomy", 0.2)),
        (("craft", 0.5), ("curiosity", 0.4)),
        "I think they should let them. People need somewhere to live, and an empty mill just rots.",
        "I'd rather they didn't. It's the last proper mill building, and I don't trust "
        "them with those beams.",
        "I honestly can't make my mind up. Homes matter, but so does the building.",
        "against",
        "Ellis says they'll have plasterboard over those beams inside a month.",
        0.6,
        "The council approved the mill flats, with conditions about keeping the beams and "
        "the museum rooms.",
        "The council turned the mill flats down. The building stays empty, and nobody seems "
        "to know what happens now.",
    ),
    Issue(
        "twelve-bus",
        "Cutting the 12 bus",
        "the council cutting the 12 bus",
        "The council wants to cut the 12, which loops out to the villages and the hospital, "
        "down to three buses a day.",
        "It runs half empty most of the day, and the money would keep the town routes going.",
        "For older people and anyone without a car it's the only way to the hospital.",
        (("reliability", 0.3), ("autonomy", 0.1)),
        (("care", 0.9),),
        "Honestly, I can see why. It runs empty most of the day, and the money has to come "
        "from somewhere.",
        "I think it's wrong. There are people who can't get to the hospital without it, "
        "and they're not the ones at council meetings.",
        "I go back and forth. It's a lot of money for an empty bus, but it isn't empty for "
        "the people on it.",
        "for",
        "Ellis says he's never caught a bus in his life and doesn't see why he should pay for one.",
        0.55,
        "The 12 is going down to three a day from next month. There's a petition, for what "
        "it's worth.",
        "The 12 is staying as it is, for now. Someone at the café said it was the petition "
        "that did it.",
    ),
    Issue(
        "market-row-coffee",
        "A coffee chain on Market Row",
        "a coffee chain wanting the empty unit on Market Row",
        "A national coffee chain has applied for the empty unit on Market Row, the one "
        "that used to be the shoe shop.",
        "An empty shop is worse than a chain. It'd bring people into town, and a few jobs.",
        "It would take trade from the independents, and Market Row would look like "
        "everywhere else.",
        (("care", 0.3), ("curiosity", 0.2)),
        (("craft", 0.6), ("autonomy", 0.4)),
        "I'd let them have it. An empty window's worse than a chain, and it's jobs.",
        "I'd rather it went to someone local. The café's good, and it'd struggle.",
        "I don't mind either way, if I'm honest. It's coffee.",
        "against",
        "Ellis says over his dead body, which seems a lot for a coffee shop.",
        0.5,
        "The chain got the unit on Market Row. It opens in the spring, apparently.",
        "The council said no to the chain on Market Row. The unit's still empty.",
    ),
    Issue(
        "old-town-20mph",
        "20mph through the old town",
        "a 20mph zone through the old town",
        "A proposal to make the old town streets 20mph, with speed tables on Mill Street.",
        "Children walk to school down those streets, and the pavements are barely a pram wide.",
        "Nobody can do more than twenty down there anyway. It's signs and speed bumps for "
        "the sake of it, and the vans hate it.",
        (("care", 0.8),),
        (("autonomy", 0.5), ("reliability", 0.2)),
        "I'm for it. Those pavements are barely a pram wide, and kids walk to school down there.",
        "I think it's a lot of signs for nothing. Nobody can go faster than that down there "
        "anyway.",
        "I can't get worked up either way. Probably for it, just about.",
        "against",
        "Ellis says he's driven those streets for forty years without flattening anyone.",
        0.65,
        "The 20mph zone's going ahead. The speed tables go in over the summer.",
        "The council shelved the 20mph zone. Too expensive, they said.",
    ),
    Issue(
        "library-hours",
        "Cutting the library's hours",
        "the library's opening hours being cut",
        "The council wants to open the library three days a week and drop the Thursday "
        "late opening.",
        "The council has to save money somewhere, and fewer people use it than used to.",
        "It's the one warm, free place in town where you don't have to buy anything, and "
        "it's where people learn things.",
        (("reliability", 0.4),),
        (("curiosity", 0.6), ("care", 0.5)),
        "I suppose they've got to save money somewhere, and it's quiet most days.",
        "I think it's a mistake. It's the one place in town you can sit somewhere warm "
        "without buying anything.",
        "I don't like it, but I don't know what they'd cut instead.",
        "against",
        "For once Ellis and I agree. He says he learned to wire a plug from a library book "
        "in 1971.",
        0.5,
        "The library's going down to three days a week. The Thursday late opening's gone.",
        "The library keeps its hours. Someone found the money, or found somewhere else to cut.",
    ),
)
BY_ID = {issue.issue_id: issue for issue in ISSUES}


@dataclass(frozen=True, slots=True)
class View:
    """His current view on one issue."""

    lean: float  # -1 against, +1 for
    side: str
    strength: float
    changed_from: str | None = None
    ellis_heard: bool = False


def town_issue_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    values: Mapping[str, float],
    calendar: Mapping[str, str],
    venue: str | None,
    with_ellis: bool = False,
) -> list[DomainEvent]:
    """Hear about a row, take a view, maybe go to the meeting, and live with the outcome."""
    if at.hour not in HOURS:
        return []
    raised = events_of(history, KIND)
    live = _live(raised)
    if live is not None:
        met = raised[-1].payload.get("stage") == "meeting"
        return _while_live(history, live, met, at, calendar, with_ellis and awake)
    if at.hour != RAISE_HOUR or not awake:
        return []
    due = _next_due(history, raised)
    if due is None or at < due:
        return []
    used = {str(e.payload["issue_id"]) for e in raised if e.payload.get("stage") == "raised"}
    remaining = [issue for issue in ISSUES if issue.issue_id not in used]
    if not remaining:
        return []
    issue = remaining[int(_roll("which", at.date().isoformat()) * len(remaining))]
    return _raise(issue, at, values, venue)


def _next_due(history: Sequence[DomainEvent], raised: Sequence[DomainEvent]) -> datetime | None:
    starts = [e for e in raised if e.payload.get("stage") == "raised"]
    if starts:
        last = _time(starts[-1])
        spread = int(_roll("gap", last.date().isoformat()) * GAP_SPREAD)
        return last + timedelta(days=GAP_DAYS + spread)
    opened = events_of(history, "finance.account_opened")
    if not opened:
        return None
    return _time(opened[0]) + SETTLED_FOR + timedelta(days=int(_roll("first") * FIRST_SPREAD))


def _live(raised: Sequence[DomainEvent]) -> DomainEvent | None:
    """The issue that has been raised and not yet decided, if any."""
    for event in reversed(raised):
        if event.payload.get("stage") == "decided":
            return None
        if event.payload.get("stage") == "raised":
            return event
    return None


def lean_from_values(issue: Issue, values: Mapping[str, float], noise: float = 0.0) -> float:
    """Which way his values pull him on this, from -1 (against) to 1 (for)."""
    pull = sum(weight * float(values.get(value, 0.7)) for value, weight in issue.for_values)
    push = sum(weight * float(values.get(value, 0.7)) for value, weight in issue.against_values)
    return round(max(-1.0, min(1.0, pull - push + noise)), 3)


def _side(lean: float) -> str:
    return "for" if lean > TORN_BELOW else "against" if lean < -TORN_BELOW else "torn"


def _strength(lean: float) -> float:
    return round(min(1.0, 0.25 + abs(lean)), 3)


def _words(issue: Issue, side: str) -> str:
    return {"for": issue.words_for, "against": issue.words_against}.get(side, issue.words_torn)


def _raise(
    issue: Issue, at: datetime, values: Mapping[str, float], venue: str | None
) -> list[DomainEvent]:
    key = at.date().isoformat()
    source = list(SOURCES)[int(_roll("source", issue.issue_id, key) * len(SOURCES))]
    meeting_day = at.date() + timedelta(
        days=MEETING_AFTER[0]
        + int(_roll("meeting", issue.issue_id, key) * (MEETING_AFTER[1] - MEETING_AFTER[0]))
    )
    meeting_day += timedelta(days=(2 - meeting_day.weekday()) % 7)  # a Wednesday evening
    decided_on = meeting_day + timedelta(
        days=DECIDED_AFTER[0]
        + int(_roll("decided", issue.issue_id, key) * (DECIDED_AFTER[1] - DECIDED_AFTER[0]))
    )
    correlation = f"town-issue-{issue.issue_id}"
    raised = DomainEvent(
        KIND,
        "pathos",
        {
            "issue_id": issue.issue_id,
            "stage": "raised",
            "title": issue.title,
            "text": issue.description,
            "heard_from": source,
            "meeting_on": meeting_day.isoformat(),
            "decided_on": decided_on.isoformat(),
            "location_id": "council-office",
            "simulated_at": at.isoformat(),
            "owner": "world",
        },
        correlation_id=correlation,
    )
    noise = (_roll("lean", issue.issue_id, key) - 0.5) * NOISE
    lean = lean_from_values(issue, values, noise)
    side = _side(lean)
    strength = _strength(lean)
    weights = [*issue.for_values, *issue.against_values]
    moved_by = max(weights, key=lambda item: item[1] * float(values.get(item[0], 0.7)))[0]
    view = _words(issue, side)
    formed = DomainEvent(
        FORMED,
        "pathos",
        {
            "issue_id": issue.issue_id,
            "lean": lean,
            "side": side,
            "strength": strength,
            "value_id": moved_by,
            "text": view,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=raised.event_id,
        correlation_id=correlation,
    )
    text = f"{SOURCES[source]} {issue.topic}. {issue.description} {view}"
    output = [raised, formed, _memory(formed, text, at, 0.3 + 0.2 * strength)]
    curiosity = float(values.get("curiosity", 0.84))
    interest = 0.5 * strength + 0.5 * curiosity
    if venue is not None and _roll("go", issue.issue_id, key) < interest - ATTEND_BAR:
        output += _plan_meeting(issue, formed, meeting_day, at, venue)
    return output


def _plan_meeting(
    issue: Issue, formed: DomainEvent, day: date, at: datetime, venue: str
) -> list[DomainEvent]:
    schedule_id = f"town-meeting-{issue.issue_id}"
    intention_id = f"{schedule_id}-intention"
    starts = datetime(day.year, day.month, day.day, MEETING_HOUR, tzinfo=at.tzinfo)
    title = f"Public meeting: {issue.title.lower()}"
    planned = DomainEvent(
        PLANNED,
        "pathos",
        {
            "issue_id": issue.issue_id,
            "schedule_id": schedule_id,
            "meeting_on": day.isoformat(),
            "location_id": venue,
            "text": "I might go to the meeting. I'd like to hear what people actually say.",
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=formed.event_id,
        correlation_id=schedule_id,
    )
    return [
        planned,
        DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "proposal_id": schedule_id,
                "intention_id": intention_id,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": venue,
                "goal_id": None,
                "priority": 0.6,
                "motivation": f"The public meeting about {issue.topic}.",
                "simulated_at": at.isoformat(),
            },
            causation_id=planned.event_id,
            correlation_id=schedule_id,
        ),
        DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": schedule_id,
                "intention_id": intention_id,
                "title": title,
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=2)).isoformat(),
                "location_id": venue,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": venue,
                "resource_id": None,
                "companion_id": None,
                "activity_type": "a_public_meeting",
                "source": "town_issues",
                "simulated_at": at.isoformat(),
            },
            causation_id=planned.event_id,
            correlation_id=schedule_id,
        ),
    ]


def _while_live(
    history: Sequence[DomainEvent],
    raised: DomainEvent,
    met: bool,
    at: datetime,
    calendar: Mapping[str, str],
    talk: bool,
) -> list[DomainEvent]:
    issue = BY_ID[str(raised.payload["issue_id"])]
    meeting_on = date.fromisoformat(str(raised.payload["meeting_on"]))
    decided_on = date.fromisoformat(str(raised.payload["decided_on"]))
    view = views(history).get(issue.issue_id)
    if view is None:
        return []
    if at.hour == REVIEW_HOUR and not met and at.date() >= meeting_on:
        return _meeting(issue, raised, view, at, calendar)
    if at.hour == DECISION_HOUR and at.date() >= decided_on:
        return _decided(issue, raised, view, at)
    if at.hour == TALK_HOUR and talk and not view.ellis_heard:
        if _roll("talk", issue.issue_id, at.date().isoformat()) < TALK_CHANCE:
            return _talk_to_ellis(issue, raised, view, at)
    return []


def _meeting(
    issue: Issue,
    raised: DomainEvent,
    view: View,
    at: datetime,
    calendar: Mapping[str, str],
) -> list[DomainEvent]:
    went = calendar.get(f"town-meeting-{issue.issue_id}") == "completed"
    key = _time(raised).date().isoformat()
    room_side = "for" if _roll("room", issue.issue_id, key) < 0.5 else "against"
    room = ROOMS[int(_roll("room-tone", issue.issue_id, key) * len(ROOMS))]
    meeting = DomainEvent(
        KIND,
        "pathos",
        {
            "issue_id": issue.issue_id,
            "stage": "meeting",
            "room_side": room_side,
            "text": f"The public meeting about {issue.topic}. {room}",
            "location_id": "council-office",
            "simulated_at": at.isoformat(),
            "owner": "world",
        },
        causation_id=raised.event_id,
        correlation_id=raised.correlation_id,
    )
    output = [meeting]
    if not went:
        text = (
            f"Read how the meeting about {issue.topic} went. {room} "
            "Sounds like I didn't miss much, or missed everything."
        )
        return [*output, _memory(meeting, text, at, 0.2)]
    chance = 0.1 + 0.4 * (1.0 - view.strength)
    changed: list[DomainEvent] = []
    if room_side != view.side and _roll("swayed", issue.issue_id, key) < chance:
        pull = MEETING_PULL if room_side == "for" else -MEETING_PULL
        changed = _change(
            issue,
            meeting,
            view,
            pull,
            at,
            "the meeting",
            "Something someone said at the meeting stuck with me.",
        )
    if changed:
        after = str(changed[0].payload["text"])
        text = (
            f"Went to the public meeting at the council rooms about {issue.topic}. {room} "
            f"I went in fairly sure and came out less so. {after}"
        )
    else:
        text = (
            f"Went to the public meeting at the council rooms about {issue.topic}. {room} "
            "Heard both sides out. Didn't change my mind, but I understand the other lot "
            "better."
        )
    return [*output, *changed, _memory(meeting, text, at, 0.55)]


def _talk_to_ellis(
    issue: Issue, raised: DomainEvent, view: View, at: datetime
) -> list[DomainEvent]:
    agree = issue.ellis_side == view.side
    discussed = DomainEvent(
        DISCUSSED,
        "pathos",
        {
            "issue_id": issue.issue_id,
            "person_id": "ellis",
            "their_side": issue.ellis_side,
            "text": issue.ellis_says,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=raised.event_id,
        correlation_id=raised.correlation_id,
    )
    changed: list[DomainEvent] = []
    if not agree:
        chance = 0.15 + 0.35 * (1.0 - view.strength)
        if _roll("ellis-sways", issue.issue_id, _time(raised).date().isoformat()) < chance:
            pull = ELLIS_PULL if issue.ellis_side == "for" else -ELLIS_PULL
            changed = _change(
                issue, discussed, view, pull, at, "Ellis", "Annoyingly, Ellis had a point."
            )
    if agree:
        coda = "We were on the same side, which unsettled us both."
    elif changed:
        coda = f"He wore me down a bit. {changed[0].payload['text']}"
    else:
        coda = "We agreed to disagree, loudly, over the lathe."
    text = f"Talked about {issue.topic} with Ellis at the bench. {issue.ellis_says} {coda}"
    return [discussed, *changed, _memory(discussed, text, at, 0.4, person_id="ellis")]


def _change(
    issue: Issue,
    cause: DomainEvent,
    view: View,
    pull: float,
    at: datetime,
    because: str,
    why: str,
) -> list[DomainEvent]:
    """A nudge that only counts as changing his mind if it moves him off where he stood."""
    lean = round(max(-1.0, min(1.0, view.lean + pull)), 3)
    side = _side(lean)
    if side == view.side:
        return []
    return [
        DomainEvent(
            CHANGED,
            "pathos",
            {
                "issue_id": issue.issue_id,
                "lean": lean,
                "side": side,
                "previous_side": view.side,
                "strength": _strength(lean),
                "because_of": because,
                "text": f"{why} {_words(issue, side)}",
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            causation_id=cause.event_id,
            correlation_id=cause.correlation_id,
        )
    ]


def _decided(issue: Issue, raised: DomainEvent, view: View, at: datetime) -> list[DomainEvent]:
    key = _time(raised).date().isoformat()
    approved = _roll("outcome", issue.issue_id, key) < issue.approve_odds
    result = issue.approved if approved else issue.rejected
    decided = DomainEvent(
        KIND,
        "pathos",
        {
            "issue_id": issue.issue_id,
            "stage": "decided",
            "outcome": "approved" if approved else "rejected",
            "text": result,
            "location_id": "council-office",
            "simulated_at": at.isoformat(),
            "owner": "world",
        },
        causation_id=raised.event_id,
        correlation_id=raised.correlation_id,
    )
    if view.side == "torn":
        feeling = "unbothered"
        coda = "I still don't know what I think, so I can't be cross about it."
    elif (view.side == "for") == approved:
        feeling = "pleased"
        coda = "Good. I didn't do anything, but I'm glad."
        if view.strength >= 0.7:
            coda = "Good. Properly glad, actually. Sometimes they get one right."
    else:
        feeling = "disappointed"
        coda = "Disappointed, if I'm honest. Nobody asked me, but still."
        if view.strength >= 0.7:
            coda = "That one annoyed me more than I expected. It's my town now, I suppose."
    outcome = DomainEvent(
        OUTCOME,
        "pathos",
        {
            "issue_id": issue.issue_id,
            "feeling": feeling,
            "side": view.side,
            "strength": view.strength,
            "outcome": "approved" if approved else "rejected",
            "text": f"{result} {coda}",
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=decided.event_id,
        correlation_id=raised.correlation_id,
    )
    importance = 0.3 if feeling == "unbothered" else 0.35 + 0.25 * view.strength
    return [decided, outcome, _memory(outcome, f"{result} {coda}", at, importance)]


def views(history: Sequence[DomainEvent]) -> dict[str, View]:
    """His current view on every issue he has heard about."""
    output: dict[str, View] = {}
    for event in events_of(history, FORMED, CHANGED, DISCUSSED):
        issue_id = str(event.payload.get("issue_id"))
        if event.kind == DISCUSSED:
            if issue_id in output:
                output[issue_id] = _with(output[issue_id], ellis_heard=True)
            continue
        lean = float(event.payload["lean"])
        previous = output.get(issue_id)
        output[issue_id] = View(
            lean=lean,
            side=str(event.payload["side"]),
            strength=float(event.payload["strength"]),
            changed_from=(
                (previous.changed_from or previous.side)
                if event.kind == CHANGED and previous is not None
                else None
            ),
            ellis_heard=previous.ellis_heard if previous is not None else False,
        )
    return output


def _with(view: View, *, ellis_heard: bool) -> View:
    return View(view.lean, view.side, view.strength, view.changed_from, ellis_heard)


def town_issues_context(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[dict[str, object]]:
    """The live row, and recent ones, with his view in his own words."""
    stages = events_of(history, KIND)
    if not stages:
        return []
    current = views(history)
    latest: dict[str, DomainEvent] = {}
    raised: dict[str, DomainEvent] = {}
    for event in stages:
        issue_id = str(event.payload["issue_id"])
        latest[issue_id] = event
        if event.payload.get("stage") == "raised":
            raised[issue_id] = event
    going = {str(e.payload.get("issue_id")) for e in events_of(history, PLANNED)}
    output: list[dict[str, object]] = []
    for issue_id, event in latest.items():
        issue = BY_ID.get(issue_id)
        view = current.get(issue_id)
        if issue is None or view is None or issue_id not in raised:
            continue
        stage = str(event.payload.get("stage"))
        if stage == "decided" and simulated_at - _time(event) > RECENT:
            continue
        meeting_on = date.fromisoformat(str(raised[issue_id].payload["meeting_on"]))
        where = {
            "raised": (
                f"public meeting at the council rooms on {meeting_on:%A} {meeting_on.day} "
                f"{meeting_on:%B}" + (", and he means to go" if issue_id in going else "")
            ),
            "meeting": "the meeting's been; waiting on the council",
            "decided": f"decided: {event.payload['text']}",
        }.get(stage, stage)
        entry: dict[str, object] = {
            "issue": issue.title,
            "what_its_about": issue.description,
            "people_for_it_say": issue.for_case,
            "people_against_it_say": issue.against_case,
            "his_view": _words(issue, view.side),
            "how_strongly": (
                "strongly"
                if view.strength >= 0.7
                else "fairly firmly"
                if view.strength >= 0.45
                else "not strongly"
            ),
            "where_it_stands": where,
        }
        if view.changed_from is not None:
            entry["he_used_to_think"] = _words(issue, view.changed_from)
        if view.ellis_heard:
            entry["ellis_thinks"] = issue.ellis_says
        output.append(entry)
    return output[-3:]


def _memory(
    source: DomainEvent, text: str, at: datetime, importance: float, person_id: str | None = None
) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "world-event",
            "source": "lived-town-issue",
            "source_event_id": str(source.event_id),
            "owner": "pathos",
            "importance": round(importance, 3),
            "confidence": 1.0,
            **({"person_id": person_id} if person_id else {}),
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
