"""His work: a freelance writer on technology and how it changes ordinary life.

In the original Patrick was freelance, writing essays on tech, philosophy and everyday
life between technical writing jobs, and valuing being on no one's corporate path. The
rebuild gave him a part-time job at Ellis's workshop instead; this takes him back, as
something that happens in his life rather than a rewrite of it.

The change: his old team in Bristol asks him to rewrite their developer docs. He quotes,
they say yes, he tells Ellis on his next shift, works out the shifts already on the rota
(his notice), and has a last day. Then he's freelance.

The writing, as it actually goes for a freelance writer:
- He pitches. Ideas come from his own life and interests (the workshop gave him the right
  to repair; the news, his degree, the town give him the rest), to the kinds of places
  that take them: a tech magazine's features desk, a long-read site, a paper's opinion
  desk, a philosophy magazine, a design quarterly. Many editors never reply; some say it's
  not for them; some commission it, with a word count, a fee and a deadline.
- A feature means talking to people: a call or two with sources, booked in.
- He writes in sessions he books himself, pulled by the deadline and pushed back by
  tiredness and mood, at home or now and then at Juniper. Some hours go well; some go on
  his phone.
- He files. The editor comes back with edits (light, a new top, cut 300 words, or they
  loved it). He sends the final version, and a week or so later it's out. People react:
  his dad, his mum, a stranger who emails, someone on the internet who's cross.
- Publications pay on publication, in thirty to sixty days, often late; he chases.
- An editor who's run two of his pieces may ask him for a monthly column.
- Alongside, the technical writing his old contacts send now and then (it pays well), and
  local writing jobs once people in town know what he does: the Regent's history for its
  centenary, programme notes for The Listening Room.
- He drops into the workshop now and then to give Ellis a hand, because he likes it.

The rules decide all of it; the words are his short notes. No model calls.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, NamedTuple, Sequence

from eidos.application.bookings import remember
from eidos.application.day_rhythm import hour_today
from eidos.application.work_rota import AGREEMENT_ID, EMPLOYER_ID, ROTA_PREFIX
from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, events_of
from eidos.domain.planning import PlanningState

# The change.
OFFER = "career.offer_received"
TOLD = "career.told_employer"
LAST_SHIFT = "career.last_shift"
STARTED = "work.freelance_started"
# Finding work.
ENQUIRY = "freelance.enquiry"
QUOTED = "freelance.quoted"
PITCHED = "freelance.pitched"
ACCEPTED = "freelance.accepted"
HAGGLED = "freelance.haggled"
WENT_QUIET = "freelance.went_quiet"
DECLINED = "freelance.declined"
PASSED = "freelance.passed_on"
COLUMN_OFFERED = "freelance.column_offered"
# Doing it.
SESSION = "freelance.session_decided"
WORKED = "freelance.worked"
DRAFT = "freelance.draft_sent"
FEEDBACK = "freelance.feedback"
MOVED = "freelance.deadline_moved"
DELIVERED = "freelance.delivered"
PUBLISHED = "freelance.published"
REACTION = "freelance.reaction"
# Getting paid.
LATE = "freelance.payment_late"
CHASED = "freelance.chased"
PAID = "freelance.paid"
REACHED_OUT = "freelance.reached_out"
DROP_IN = "freelance.drop_in_decided"
JOB_KINDS = (ENQUIRY, QUOTED, PITCHED, ACCEPTED, HAGGLED, WENT_QUIET, DECLINED, PASSED,
             WORKED, DRAFT, FEEDBACK, MOVED, DELIVERED, PUBLISHED, REACTION, LATE, CHASED,
             PAID)  # fmt: skip
SESSION_PREFIX = "freelance-"
DROP_IN_PREFIX = "workshop-drop-in-"
FIRST_JOB = "old-team-docs"
FIRST_PITCH = "repair-feature"
MOST_HOURS_A_DAY = 6
CRUNCH_HOURS_A_DAY = 9
TOO_MUCH_ON = 35.0  # hours of work he already has before he turns things down
WRITING = frozenset({"feature", "essay", "review", "column"})


class Brief(NamedTuple):
    key: str
    client: str  # how he'd name them
    what: str  # the job, as a to-do
    short: str  # the thing itself: "the right-to-repair piece"
    hours: float  # what it should take him
    fee_pence: int
    days: int  # how long they give him
    kind: str  # feature, essay, review, column, docs or local
    pays_days: int  # payment terms after publication or delivery
    late_chance: float
    place_id: str | None = None  # a local job
    words: int = 0


_TECH_DESK = "the features editor at a tech magazine in London"
_LONG_READS = "a long-read site about technology and society"
_OPINION = "the opinion desk at a national paper"
_PHILOSOPHY = "a philosophy magazine"
_QUARTERLY = "a design and culture quarterly"
# What he'd pitch, and to whom: his interests, his degree, his life.
PITCHES: tuple[Brief, ...] = (
    Brief(FIRST_PITCH, _TECH_DESK, "write a feature on the right to repair, from a small-town "
          "workshop", "the right-to-repair piece", 14, 54_000, 21, "feature", 45, 0.4, words=1_800),
    Brief("boring-tech", _LONG_READS, "write an essay making the case for boring technology",
          "the boring technology essay", 18, 90_000, 28, "essay", 30, 0.3, words=3_000),
    Brief("doorbells", _OPINION, "write an opinion piece on smart doorbells and neighbourly "
          "privacy", "the doorbell piece", 6, 25_000, 7, "feature", 30, 0.3, words=900),
    Brief("grief-tech", _PHILOSOPHY, "write an essay on grief tech and talking to the dead",
          "the grief tech essay", 16, 50_000, 28, "essay", 60, 0.4, words=2_500),
    Brief("self-checkout", _QUARTERLY, "write a piece on self-checkouts and the end of small "
          "talk", "the self-checkout piece", 10, 40_000, 21, "feature", 45, 0.3, words=1_500),
    Brief("companions", _LONG_READS, "write an essay on AI companions and loneliness",
          "the AI companions essay", 18, 90_000, 28, "essay", 30, 0.3, words=3_000),
    Brief("data-after-death", _TECH_DESK, "write a feature on what happens to your data when "
          "you die", "the digital afterlife feature", 14, 54_000, 21, "feature", 45, 0.4,
          words=1_800),
    Brief("algorithm-review", _PHILOSOPHY, "write a review of a new book on the ethics of algorithms",
          "the book review", 5, 15_000, 14, "review", 60, 0.3, words=900),
    Brief("screen-time", _OPINION, "write an opinion piece on the screen-time panic",
          "the screen-time piece", 6, 25_000, 7, "feature", 30, 0.3, words=900),
    Brief("small-town-tech", _QUARTERLY, "write a piece on what small towns actually need from "
          "technology", "the small-town tech piece", 10, 40_000, 21, "feature", 45, 0.3,
          words=1_500),
)  # fmt: skip
# Technical writing from people who know him: it pays well and keeps things ticking over.
COMPANIES: tuple[Brief, ...] = (
    Brief(FIRST_JOB, "my old team in Bristol", "rewrite their developer documentation",
          "the developer docs", 24, 60_000, 21, "docs", 30, 0.2),
    Brief("leeds-api", "a small Leeds start-up making accounting software",
          "write a getting-started guide for their API", "the API guide", 14, 35_000, 14,
          "docs", 30, 0.4),
    Brief("agency-help", "the agency in Bristol I used to sit next to",
          "tidy up the help pages for a booking app", "the booking app help pages", 12,
          30_000, 10, "docs", 30, 0.35),
)  # fmt: skip
# Writing in town, once people know what he does.
LOCAL: tuple[Brief, ...] = (
    Brief("regent-history", "the heritage society", "write the history of the Regent for its "
          "centenary booklet", "the Regent's history", 12, 35_000, 21, "local", 14, 0.1, "cinema"),
    Brief("market-panels", "the market hall traders", "write the panels for the market hall's "
          "history display", "the market hall panels", 6, 20_000, 14, "local", 14, 0.1,
          "market-hall"),
    Brief("programme-notes", "The Listening Room", "write the programme notes for their autumn "
          "season", "the programme notes", 5, 15_000, 10, "local", 7, 0.1, "music-room"),
    Brief("bakery-words", "the bakery", "write the words for their new website",
          "the bakery's website words", 4, 15_000, 10, "local", 7, 0.1, "bakery"),
)  # fmt: skip
COLUMN = Brief("column", "", "write this month's column", "this month's column", 6, 30_000,
               0, "column", 30, 0.2, words=900)  # fmt: skip
BRIEFS = {brief.key: brief for brief in (*PITCHES, *COMPANIES, *LOCAL, COLUMN)}


@dataclass(frozen=True, slots=True)
class Job:
    job_id: str
    brief: Brief
    client: str
    client_id: str | None
    status: str  # enquiry, quoted, pitched, active, waiting, delivered, paid, declined, quiet
    since: datetime
    fee_pence: int = 0
    needed: float = 0.0
    worked: float = 0.0
    deadline: datetime | None = None
    reply_due: datetime | None = None
    waiting_until: datetime | None = None
    pay_due: datetime | None = None
    late: bool = False
    chased: bool = False
    moved: int = 0
    drafted: bool = False
    last_worked: datetime | None = None
    deposit_pence: int = 0
    deposit_due: datetime | None = None
    deposit_paid: bool = False
    publish_due: datetime | None = None
    published: bool = False
    reacted: bool = False

    @property
    def writing(self) -> bool:
        return self.brief.kind in WRITING


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _when(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _time(value: object) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value else None


def _cap(text: str) -> str:
    return text[0].upper() + text[1:] if text else text


def _step(jobs: dict[str, Job], event: DomainEvent) -> dict[str, Job]:
    if event.kind not in JOB_KINDS:
        return jobs
    p = event.payload
    job_id = str(p.get("job_id"))
    if event.kind in {ENQUIRY, PITCHED}:
        brief = BRIEFS.get(str(p.get("brief")))
        if brief is None:
            return jobs
        client_id = p.get("client_id")
        new = Job(
            job_id, brief, str(p.get("client") or brief.client),
            str(client_id) if client_id else None,
            "pitched" if event.kind == PITCHED else "enquiry", _when(event),
            reply_due=_time(p.get("reply_due")),
        )  # fmt: skip
        return {**jobs, job_id: new}
    job = jobs.get(job_id)
    if job is None:
        return jobs
    at = _when(event)
    if event.kind == QUOTED:
        job = replace(job, status="quoted", fee_pence=int(p.get("fee_pence", 0) or 0),
                      reply_due=_time(p.get("reply_due")))  # fmt: skip
    elif event.kind == HAGGLED:
        job = replace(job, fee_pence=int(p.get("fee_pence", job.fee_pence) or 0))
    elif event.kind == ACCEPTED:
        job = replace(
            job, status="active", since=at, needed=float(p.get("needed_hours", 0) or 0),
            deadline=_time(p.get("deadline")), fee_pence=int(p.get("fee_pence", job.fee_pence)),
            deposit_pence=int(p.get("deposit_pence", 0) or 0),
            deposit_due=_time(p.get("deposit_due")),
        )  # fmt: skip
    elif event.kind in {WENT_QUIET, DECLINED, PASSED}:
        job = replace(job, status="quiet" if event.kind == WENT_QUIET else "declined")
    elif event.kind == WORKED:
        job = replace(job, worked=float(p.get("worked_hours", job.worked)), last_worked=at)
    elif event.kind == DRAFT:
        job = replace(job, status="waiting", drafted=True,
                      waiting_until=_time(p.get("feedback_due")))  # fmt: skip
    elif event.kind == FEEDBACK:
        job = replace(job, status="active", waiting_until=None,
                      needed=float(p.get("needed_hours", job.needed)),
                      fee_pence=int(p.get("fee_pence", job.fee_pence)))  # fmt: skip
    elif event.kind == MOVED:
        job = replace(job, deadline=_time(p.get("deadline")), moved=job.moved + 1)
    elif event.kind == DELIVERED:
        job = replace(job, status="delivered", pay_due=_time(p.get("pay_due")),
                      publish_due=_time(p.get("publish_due")))  # fmt: skip
    elif event.kind == PUBLISHED:
        job = replace(job, published=True, pay_due=_time(p.get("pay_due")))
    elif event.kind == REACTION:
        job = replace(job, reacted=True)
    elif event.kind == LATE:
        job = replace(job, late=True)
    elif event.kind == CHASED:
        job = replace(job, chased=True, pay_due=_time(p.get("pay_due")))
    elif event.kind == PAID:
        job = replace(job, deposit_paid=True) if p.get("deposit") else replace(job, status="paid")
    return {**jobs, job_id: job}


_JOBS: IncrementalFold[dict[str, Job]] = IncrementalFold(dict, _step)


def jobs(history: Sequence[DomainEvent]) -> list[Job]:
    return list(_JOBS(history).values())


def is_freelance_session(schedule_id: object) -> bool:
    return isinstance(schedule_id, str) and schedule_id.startswith(SESSION_PREFIX)


def freelancing(history: Sequence[DomainEvent]) -> bool:
    """Whether he's taken on freelance work (from the first contract on)."""
    return any(e.payload.get("job_id") == FIRST_JOB for e in events_of(history, ACCEPTED)[:1])


def self_employed(history: Sequence[DomainEvent]) -> bool:
    """Whether the workshop job is behind him and freelancing is his living."""
    return bool(events_of(history, STARTED))


def _event(kind: str, at: datetime, **payload: object) -> DomainEvent:
    job_id = payload.get("job_id")
    return DomainEvent(
        kind,
        "pathos",
        {**payload, "simulated_at": at.isoformat()},
        correlation_id=str(job_id) if job_id else None,
    )


def _note(cause: DomainEvent, text: str, at: datetime, importance: float, **where: str | None) -> DomainEvent:  # fmt: skip
    return remember(
        cause, _cap(text), at, importance, origin="lived-work", category="experience",
        person_id=where.get("person_id"), location_id=where.get("location_id"),
    )  # fmt: skip


def _weekday_hours(at: datetime, crunch: bool) -> bool:
    """When he'd sit down to work: from mid-morning (later some days), to about six, or
    into the evening with a deadline on top of him; weekends only in a crunch."""
    starts = hour_today("freelance-start", at.date(), 10, 1, 1)
    if at.weekday() >= 5:
        return crunch and 10 <= at.hour <= 18
    return starts <= at.hour < (22 if crunch else 18)


def _worked_today(history: Sequence[DomainEvent], at: datetime) -> float:
    today = at.date().isoformat()
    total = 0.0
    for event in reversed(events_of(history, WORKED)[-12:]):
        if str(event.payload.get("simulated_at", ""))[:10] != today:
            break
        total += float(event.payload.get("hours", 1.0) or 1.0)
    return total


_ON = frozenset({"scheduled", "active", "completed"})


def _session_now(planning: PlanningState, at: datetime) -> tuple[str, str] | None:
    """(schedule id, place) of a work session under way now."""
    for entry in planning.calendar.values():
        # The planner marks a work session completed once it's under way; it's still his
        # time to work until it ends, unless it was dropped.
        if not is_freelance_session(entry.schedule_id) or entry.status not in _ON:
            continue
        starts = datetime.fromisoformat(entry.starts_at)
        ends = datetime.fromisoformat(entry.ends_at) if entry.ends_at else starts
        if starts <= at < ends:
            return entry.schedule_id, entry.location_id
    return None


def working_now(planning: PlanningState, at: datetime) -> bool:
    return _session_now(planning, at) is not None


def _calendar_clear(planning: PlanningState, at: datetime, hours: float) -> bool:
    until = at + timedelta(hours=hours)
    for entry in planning.calendar.values():
        if entry.status not in {"scheduled", "active"} or entry.actor_id not in {None, "pathos"}:
            continue
        starts = datetime.fromisoformat(entry.starts_at)
        ends = datetime.fromisoformat(entry.ends_at) if entry.ends_at else starts
        if starts < until and at < ends:
            return False
    return True


def _book(cause: DomainEvent, schedule_id: str, title: str, starts: datetime, hours: float,
          place_id: str, at: datetime, *, activity: str, companion: str | None = None,
          motivation: str) -> list[DomainEvent]:  # fmt: skip
    """A session he decided on, on his calendar, the way the rota's shifts are."""
    intention_id = f"{schedule_id}-intention"
    return [
        DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "proposal_id": schedule_id,
                "intention_id": intention_id,
                "actor_id": "pathos",
                "action": "work",
                "target_id": place_id,
                "goal_id": None,
                "priority": 0.75,
                "motivation": motivation,
                "simulated_at": at.isoformat(),
            },
            causation_id=cause.event_id,
            correlation_id=schedule_id,
        ),  # fmt: skip
        DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": schedule_id,
                "intention_id": intention_id,
                "title": title,
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=hours)).isoformat(),
                "location_id": place_id,
                "actor_id": "pathos",
                "action": "work",
                "target_id": place_id,
                "resource_id": None,
                "companion_id": companion,
                "activity_type": activity,
                "source": "freelance",
                "simulated_at": at.isoformat(),
            },
            causation_id=cause.event_id,
            correlation_id=schedule_id,
        ),  # fmt: skip
    ]


def freelance_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    location_id: str,
    busy: bool,
    energy: float,
    valence: float,
    balance_pence: int,
    planning: PlanningState,
    places: frozenset[str],
    place_people: Mapping[str, tuple[str, str]],
    on_shift_at_workshop: bool,
    comfortable: bool = False,
) -> list[DomainEvent]:
    """This hour of his working life. ``comfortable``: money isn't why he works."""
    output = _the_change(history, at, awake=awake, planning=planning,
                         on_shift_at_workshop=on_shift_at_workshop)  # fmt: skip
    if output:
        return output
    if not freelancing(history) and not events_of(history, OFFER):
        return []
    everything = jobs(history)
    hour = at.isoformat()[:13]
    output += _replies(everything, at, balance_pence, comfortable)
    output += _payments(everything, at, awake, comfortable)
    if awake:
        output += _deadlines(everything, at)
        output += _out_in_the_world(history, everything, at)
    if output:
        return output
    if not awake:
        return []
    output += _new_work(
        history, everything, at, places, place_people, balance_pence, hour, comfortable
    )
    if output:
        return output
    session = _session_now(planning, at)
    if session is not None and location_id == session[1]:
        return _work_an_hour(history, everything, at, session, energy, hour)
    if busy or session is not None:
        return []
    sat_down = _maybe_sit_down(history, everything, at, location_id, energy, valence, planning,
                               places, hour, balance_pence, comfortable)  # fmt: skip
    booked = next((e for e in sat_down if e.kind == "schedule.created"), None)
    if booked is not None and booked.payload["starts_at"] == at.isoformat():
        # Sat down to it now: this hour's work counts.
        sat_down += _work_an_hour(
            [*history, *sat_down], jobs([*history, *sat_down]), at,
            (str(booked.payload["schedule_id"]), location_id), energy, hour,
        )  # fmt: skip
    return sat_down or _maybe_drop_in(history, at, planning, places)


# -- the change --------------------------------------------------------------------------


def _the_change(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    planning: PlanningState,
    on_shift_at_workshop: bool,
) -> list[DomainEvent]:
    if self_employed(history):
        return []
    offered = events_of(history, OFFER)
    if not offered:
        if not awake or not 9 <= at.hour <= 20:
            return []
        offer = _event(OFFER, at, from_client=COMPANIES[0].client, job_id=FIRST_JOB)
        enquiry = _event(ENQUIRY, at, job_id=FIRST_JOB, brief=FIRST_JOB, client=COMPANIES[0].client)
        return [
            offer,
            enquiry,
            _note(
                offer,
                "An email from my old team in Bristol: their docs person has left and they "
                "want someone who knows the product to rewrite the developer documentation. "
                "Three weeks or so, paid properly. Enough to go freelance on, and finally "
                "pitch some of the pieces I keep writing in my head.",
                at, 0.65,
            ),
        ]  # fmt: skip
    if not freelancing(history):
        return []
    told = events_of(history, TOLD)
    ended = [e for e in events_of(history, "work.agreement_ended")
             if e.payload.get("agreement_id") == AGREEMENT_ID]  # fmt: skip
    if not told:
        accepted = _when(events_of(history, ACCEPTED)[0])
        shifts_soon = [
            datetime.fromisoformat(entry.starts_at)
            for entry in planning.calendar.values()
            if entry.schedule_id.startswith(ROTA_PREFIX) and entry.status == "scheduled"
            and at <= datetime.fromisoformat(entry.starts_at) <= at + timedelta(days=4)
        ]  # fmt: skip
        in_person = on_shift_at_workshop and 11 <= at.hour <= 15
        by_phone = (not shifts_soon and awake and 10 <= at.hour <= 19
                    and at - accepted >= timedelta(hours=20))  # fmt: skip
        if not (in_person or by_phone):
            return []
        # His notice is the shifts already on the rota; Ellis publishes no more.
        rota = sorted(
            entry.starts_at[:10]
            for entry in planning.calendar.values()
            if entry.schedule_id.startswith(ROTA_PREFIX) and entry.status == "scheduled"
            and entry.starts_at[:10] >= at.date().isoformat()
        )  # fmt: skip
        last_day = rota[-1] if rota else at.date().isoformat()
        told_ellis = _event(TOLD, at, employer_id=EMPLOYER_ID, last_day=last_day,
                            channel="in person" if in_person else "phone")  # fmt: skip
        meant = [
            DomainEvent(
                "intention.done",
                "pathos",
                {"intention_id": e.payload["intention_id"], "text": e.payload.get("text"),
                 "by_event_id": str(told_ellis.event_id), "simulated_at": at.isoformat()},
                causation_id=told_ellis.event_id,
            )
            for e in events_of(history, "intention.formed")[-40:]
            if e.payload.get("source") == "freelance" and e.payload.get("person_id") == EMPLOYER_ID
        ]  # fmt: skip
        words = (
            "Told Ellis I'm going freelance again, writing. Ellis said they'd half seen it "
            "coming, and that the bench is there whenever I want to drop in. I'll work the "
            "shifts that are already on the rota."
            if in_person
            else "Rang Ellis to say I'm going freelance again. Easier than I'd made it in my "
            "head. Ellis said to drop by whenever."
        )
        return [
            told_ellis,
            DomainEvent(
                "work.agreement_ended",
                "pathos",
                {
                    "agreement_id": AGREEMENT_ID,
                    "employer_id": EMPLOYER_ID,
                    "last_day": last_day,
                    "reason": "Going freelance: he gave notice and works the shifts already on the rota.",
                    "simulated_at": at.isoformat(),
                },
                causation_id=told_ellis.event_id,
                correlation_id=AGREEMENT_ID,
            ),
            _note(told_ellis, words, at, 0.6, person_id=EMPLOYER_ID,
                  location_id="workshop" if in_person else None),
            *meant,
        ]  # fmt: skip
    last_day = str(told[0].payload.get("last_day", ""))
    if (
        on_shift_at_workshop
        and at.date().isoformat() == last_day
        and at.hour == 15
        and not events_of(history, LAST_SHIFT)
    ):
        last = _event(LAST_SHIFT, at, employer_id=EMPLOYER_ID)
        return [
            last,
            _note(last, "Last proper shift at the workshop. Ellis made a pot of tea and "
                  "pretended it wasn't a thing. It was a bit of a thing.", at, 0.6,
                  person_id=EMPLOYER_ID, location_id="workshop"),
        ]  # fmt: skip
    rota_left = any(
        entry.schedule_id.startswith(ROTA_PREFIX) and entry.status in {"scheduled", "active"}
        and datetime.fromisoformat(entry.ends_at or entry.starts_at) > at
        for entry in planning.calendar.values()
    )  # fmt: skip
    if (
        ended
        and not rota_left
        and awake
        and 8 <= at.hour <= 12
        and at.date().isoformat() > last_day
    ):
        started = _event(STARTED, at)
        return [
            started,
            _note(started, "First proper day of being freelance again. Nobody's expecting me "
                  "anywhere. That's either the best or the worst thing about it.", at, 0.55),
        ]  # fmt: skip
    return []


# -- finding work ------------------------------------------------------------------------


def _live(everything: Sequence[Job]) -> list[Job]:
    return [
        j for j in everything if j.status in {"enquiry", "quoted", "pitched", "active", "waiting"}
    ]


def _on(everything: Sequence[Job]) -> float:
    return sum(
        max(0.0, j.needed - j.worked) for j in everything if j.status in {"active", "waiting"}
    )


def _new_work(
    history: Sequence[DomainEvent],
    everything: Sequence[Job],
    at: datetime,
    places: frozenset[str],
    place_people: Mapping[str, tuple[str, str]],
    balance_pence: int,
    hour: str,
    comfortable: bool = False,
) -> list[DomainEvent]:
    output: list[DomainEvent] = []
    # Replying to an enquiry: a quote, or a polite no when he's got too much on.
    for job in everything:
        if job.status != "enquiry" or not 9 <= at.hour <= 21:
            continue
        if _on(everything) > TOO_MUCH_ON and job.brief.key != FIRST_JOB:
            no = _event(DECLINED, at, job_id=job.job_id)
            return [no, _note(no, f"Had to say no to {job.client}: {job.brief.what}. "
                              "Too much on already. Feels wrong turning work down.", at, 0.35)]  # fmt: skip
        fee = job.brief.fee_pence
        reply_days = 1 if job.brief.key == FIRST_JOB else 1 + int(_roll("reply", job.job_id) * 4)
        quote = _event(QUOTED, at, job_id=job.job_id, fee_pence=fee,
                       reply_due=(at + timedelta(days=reply_days)).isoformat())  # fmt: skip
        return [quote, _note(quote, f"Sent {job.client} a quote for {job.brief.short}: "
                             f"£{fee // 100}. Always feels like guessing.", at, 0.3)]  # fmt: skip
    column = _column_job(history, everything, at)
    if column:
        return column
    if not self_employed(history):
        return []  # one thing at a time until the workshop's behind him
    if at.minute != 0 or at.hour not in {10, 15}:
        return []
    pitch = _pitch(history, everything, at, hour)
    if pitch:
        return pitch
    live = _live(everything)
    done_local = [j for j in everything if j.brief.place_id and j.status in {"delivered", "paid"}]
    published = [j for j in everything if j.published]
    word_of_mouth = any(at - j.since <= timedelta(days=30) for j in [*done_local, *published])
    reached = [
        e for e in events_of(history, REACHED_OUT)[-2:] if at - _when(e) <= timedelta(days=12)
    ]
    chance = (
        (0.02 if _on(everything) > 25 else 0.05)
        + (0.06 if word_of_mouth else 0)
        + (0.05 if reached else 0)
    )
    if _roll("enquiry", hour) < chance:
        used = {j.brief.key for j in everything}
        local = [b for b in LOCAL if b.key not in used and b.place_id in places]
        companies = [b for b in COMPANIES if b.key not in used]
        pool = (
            local
            if (word_of_mouth and local and _roll("local", hour) < 0.6)
            else companies or local
        )
        if not pool:
            return []
        brief = pool[int(_roll("brief", hour) * len(pool))]
        person = place_people.get(brief.place_id or "")
        client = f"{person[1]} from {brief.client}" if person else brief.client
        job_id = f"job-{brief.key}"
        enquiry = _event(ENQUIRY, at, job_id=job_id, brief=brief.key, client=client,
                         **({"client_id": person[0]} if person else {}))  # fmt: skip
        how = (
            f"{client} asked if I could {brief.what}. They'd read something of mine, apparently."
            if word_of_mouth and brief.place_id
            else f"An email from {client}: could I {brief.what}? Good money."
        )
        return [enquiry, _note(enquiry, how, at, 0.4, person_id=person[0] if person else None)]
    # A quiet patch: nothing on and nothing coming, so he puts the word out.
    if not live and not reached and at.hour == 10 and at.weekday() < 5:
        last_job = max((j.since for j in everything), default=at)
        if at - last_job >= timedelta(days=7) and _roll("reach-out", at.date().isoformat()) < 0.35:
            out = _event(REACHED_OUT, at)
            output += [out, _note(out, "Emailed a few old contacts to say I'm taking on work. "
                                  + ("Not for the money. I just like having something on."
                                     if comfortable else
                                     "Hate doing it. Quiet weeks make me twitchy about money."),
                                  at, 0.4)]  # fmt: skip
    return output


_PITCH_FEELINGS = (
    "Rewrote the email four times. Sent it before I could rewrite it a fifth.",
    "Short and to the point, for once. Now the not-checking-my-inbox part.",
    "Felt good about it for ten minutes, then reread it.",
    "Probably nothing will come of it. Most don't.",
)


def _pitch(
    history: Sequence[DomainEvent], everything: Sequence[Job], at: datetime, hour: str
) -> list[DomainEvent]:
    """Sending an editor an idea, when he has room for one and something to say."""
    if at.weekday() >= 5:
        return []
    out = [j for j in everything if j.status == "pitched"]
    writing_on = [j for j in everything if j.writing and j.status in {"active", "waiting"}]
    # Only with room for it: a pitch that comes good has to be written.
    if len(out) >= 2 or len(writing_on) >= 2 or _on(everything) > 15:
        return []
    last = events_of(history, PITCHED)[-1:]
    if last and at - _when(last[0]) < timedelta(days=3):
        return []
    # The first one, the week he starts: the piece the workshop gave him.
    first = not last
    if not first and _roll("pitch", hour) >= 0.3:
        return []
    used = {j.brief.key for j in everything}
    ideas = [b for b in PITCHES if b.key not in used]
    if not ideas:
        return []
    brief = (
        BRIEFS[FIRST_PITCH]
        if first and FIRST_PITCH not in used
        else ideas[int(_roll("idea", hour) * len(ideas))]
    )
    reply = at + timedelta(days=2 + int(_roll("editor", brief.key) * 8))
    pitched = _event(PITCHED, at, job_id=f"piece-{brief.key}", brief=brief.key,
                     client=brief.client, reply_due=reply.isoformat())  # fmt: skip
    idea = brief.what.removeprefix("write ")
    words = (
        f"Pitched {brief.client} {idea}. "
        + _PITCH_FEELINGS[int(_roll("pitch-felt", brief.key) * len(_PITCH_FEELINGS))]
    )
    return [pitched, _note(pitched, words, at, 0.45)]


def _column_job(
    history: Sequence[DomainEvent], everything: Sequence[Job], at: datetime
) -> list[DomainEvent]:
    """A monthly column, once an editor has asked for one: due on the 20th."""
    offered = events_of(history, COLUMN_OFFERED)
    if not offered or at.day != 1 or at.hour != 9:
        return []
    month = at.strftime("%Y-%m")
    job_id = f"column-{month}"
    if any(j.job_id == job_id for j in everything):
        return []
    client = str(offered[0].payload.get("client"))
    deadline = at.replace(day=20, hour=17)
    asked = _event(PITCHED, at, job_id=job_id, brief=COLUMN.key, client=client)
    return [
        asked,
        _event(ACCEPTED, at, job_id=job_id, fee_pence=COLUMN.fee_pence, needed_hours=COLUMN.hours,
               deadline=deadline.isoformat(), brief=COLUMN.key),
    ]  # fmt: skip


def _replies(
    everything: Sequence[Job], at: datetime, balance_pence: int, comfortable: bool = False
) -> list[DomainEvent]:
    for job in everything:
        if job.status == "pitched" and job.reply_due is not None:
            if at < job.reply_due or not 9 <= at.hour <= 18:
                continue
            said = _editor(job, at)
            if said:
                return said
            continue
        if job.status != "quoted" or job.reply_due is None or at < job.reply_due:
            continue
        if not 9 <= at.hour <= 18:
            return []
        roll = 0.0 if job.brief.key == FIRST_JOB else _roll("answer", job.job_id)
        if roll < 0.15 and job.fee_pence and job.brief.key != FIRST_JOB:
            # They want it cheaper. With money in the bank he can afford to say no.
            offer = int(job.fee_pence * 0.85)
            haggle = _event(HAGGLED, at, job_id=job.job_id, fee_pence=offer)
            if (comfortable or balance_pence >= 50_000) and _roll("take-it", job.job_id) >= (
                0.25 if comfortable else 0.6
            ):
                no = _event(DECLINED, at, job_id=job.job_id)
                return [haggle, no, _note(no, f"{job.client} wanted {job.brief.short} for less. "
                        "I said no, politely.", at, 0.35)]  # fmt: skip
            return [haggle, *_accept(job, at, offer, haggled=True)]
        if roll < 0.8:
            return _accept(job, at, job.fee_pence)
        quiet = _event(WENT_QUIET, at, job_id=job.job_id)
        return [quiet, _note(quiet, f"Never heard back from {job.client} about {job.brief.short}. "
                             "They've gone quiet. Fine. Ish.", at, 0.3)]  # fmt: skip
    return []


def _editor(job: Job, at: datetime) -> list[DomainEvent]:
    """What an editor does with a pitch: commission it, pass, or never reply."""
    roll = _roll("editor-says", job.job_id)
    yes = 0.75 if job.brief.key == FIRST_PITCH else 0.4
    if roll < yes:
        return _accept(job, at, job.brief.fee_pence)
    if roll < yes + 0.3:
        passed = _event(PASSED, at, job_id=job.job_id)
        return [passed, _note(passed, f"{job.client} passed on {job.brief.short}: 'not quite right "
                              "for us at the moment'. Might try it somewhere else.", at, 0.35)]  # fmt: skip
    if at - job.reply_due < timedelta(days=10):  # type: ignore[operator]
        return []
    quiet = _event(WENT_QUIET, at, job_id=job.job_id)
    return [quiet, _note(quiet, f"Nothing back from {job.client} about {job.brief.short}. "
                         "Taking that as a no. Editors are busy, apparently forever.", at, 0.3)]  # fmt: skip


def _accept(job: Job, at: datetime, fee: int, haggled: bool = False) -> list[DomainEvent]:
    # Everyone undercounts the hours.
    needed = round(job.brief.hours * (1.0 + 0.5 * _roll("really", job.job_id)), 1)
    deadline = (at + timedelta(days=job.brief.days)).replace(
        hour=17, minute=0, second=0, microsecond=0
    )
    # Bigger technical jobs: half up front, as freelancers ask for.
    deposit = fee // 2 if fee >= 40_000 and job.brief.kind == "docs" else 0
    deposit_due = (at + timedelta(days=7 + int(_roll("deposit", job.job_id) * 5))).replace(hour=11)
    yes = _event(ACCEPTED, at, job_id=job.job_id, fee_pence=fee, needed_hours=needed,
                 deadline=deadline.isoformat(), brief=job.brief.key, deposit_pence=deposit,
                 **({"deposit_due": deposit_due.isoformat()} if deposit else {}))  # fmt: skip
    if job.writing:
        words = (
            f"{job.client} want {job.brief.short}: {job.brief.words:,} words by "
            f"{deadline:%A %-d %B}, £{fee // 100}. I may have punched the air."
            if job.brief.key == FIRST_PITCH
            else f"{job.client} commissioned {job.brief.short}: {job.brief.words:,} words by "
            f"{deadline:%A %-d %B}, £{fee // 100}."
        )
    else:
        words = (
            f"{job.client} said yes to {job.brief.short}, if I'd knock a bit off. I did."
            if haggled
            else "They said yes. I'm doing it: going freelance again. Need to tell Ellis."
            if job.brief.key == FIRST_JOB
            else f"{job.client} said yes to {job.brief.short}. Due {deadline:%A %-d %B}."
        )
    output = [yes, _note(yes, words, at, 0.55 if job.brief.key in {FIRST_JOB, FIRST_PITCH} else 0.4,
                         person_id=job.client_id)]  # fmt: skip
    if job.brief.key == FIRST_JOB:
        output.append(
            DomainEvent(
                "intention.formed",
                "pathos",
                {
                    "intention_id": f"loop:{yes.event_id}",
                    "text": "tell Ellis I'm going freelance",
                    "importance": 0.75,
                    "source": "freelance",
                    "source_event_id": str(yes.event_id),
                    "person_id": EMPLOYER_ID,
                    "simulated_at": at.isoformat(),
                },
                causation_id=yes.event_id,
            )
        )
    if job.brief.kind in {"feature", "essay"}:
        # A feature means talking to people: a call with a source, in a couple of days.
        day = at + timedelta(days=2 if at.weekday() < 3 else 4)
        starts = day.replace(hour=11, minute=0, second=0, microsecond=0)
        output += _book(
            yes, f"{SESSION_PREFIX}{job.job_id}-call", f"Call with a source for {job.brief.short}",
            starts, 1, "home", at, activity="interview",
            motivation="Someone who actually knows about this, on the record.",
        )  # fmt: skip
    return output


# -- doing the work ----------------------------------------------------------------------


def _workable(everything: Sequence[Job], at: datetime) -> list[Job]:
    return sorted(
        (j for j in everything if j.status == "active"),
        key=lambda j: j.deadline or at + timedelta(days=99),
    )


WORK_PLACES = frozenset({"home", "cafe", "library"})


def _maybe_sit_down(
    history: Sequence[DomainEvent],
    everything: Sequence[Job],
    at: datetime,
    location_id: str,
    energy: float,
    valence: float,
    planning: PlanningState,
    places: frozenset[str],
    hour: str,
    balance_pence: int = 0,
    comfortable: bool = False,
) -> list[DomainEvent]:
    """Whether he works now or plans to shortly, for how long, and where.

    A loose routine keeps the day from filling up with everything else: on a working day
    he plans the morning's writing block before it starts and the afternoon's over lunch,
    and in between sits down to it when he's at home or at Juniper with nothing else on.
    """
    workable = _workable(everything, at)
    if not workable:
        return []
    job = workable[0]
    left = job.deadline - at if job.deadline else timedelta(days=30)
    crunch = left <= timedelta(days=2)
    morning = hour_today("freelance-start", at.date(), 10, 1, 1)
    planning_ahead = at.weekday() < 5 and at.hour in {morning - 1, 13}
    if not planning_ahead and (location_id not in WORK_PLACES or not _weekday_hours(at, crunch)):
        return []
    worked = _worked_today(history, at)
    if worked >= (CRUNCH_HOURS_A_DAY if crunch else MOST_HOURS_A_DAY):
        return []
    # Parkinson's law, and how he is: far-off deadlines get put off, near ones don't.
    pull = 0.5 * (1.8 if crunch else 1.5 if left <= timedelta(days=5) else 0.65
                  if left > timedelta(days=10) else 1.1)  # fmt: skip
    pull *= 0.45 if energy < 0.35 else 0.8 if energy < 0.5 else 1.0
    pull *= 0.7 if valence < -0.2 else 1.0
    pull *= 0.85 if comfortable else 1.0  # no rent riding on it
    if planning_ahead:
        afternoon = 0.85 if left <= timedelta(days=5) else 0.6
        pull = max(
            pull,
            (0.85 if at.hour == morning - 1 else afternoon) * (0.7 if valence < -0.2 else 1.0),
        )
    if _roll("sit-down", hour) >= min(0.92, pull):
        return []
    hours = (2 if planning_ahead else 1) + int(_roll("how-long", hour) * (3 if crunch else 2))
    starts = at + timedelta(hours=1) if planning_ahead else at
    # Where: here if he can work here; otherwise home, or now and then Juniper for a change
    # of scene (a coffee there costs money).
    place = location_id if location_id in WORK_PLACES and not planning_ahead else "home"
    if (
        place == "home"
        and "cafe" in places
        and balance_pence >= 30_000
        and _roll("cafe", hour) < 0.2
        and not crunch
    ):
        place = "cafe"
        if starts == at:
            starts = at + timedelta(hours=1)
    if not _calendar_clear(planning, starts, hours):
        hours = 1
        if not _calendar_clear(planning, starts, 1):
            return []
    decided = _event(SESSION, at, job_id=job.job_id, hours=hours, place_id=place)
    verb = "Write" if job.writing or job.brief.kind == "local" else "Work on"
    where = " at Juniper" if place == "cafe" else " at the library" if place == "library" else ""
    return [
        decided,
        *_book(
            decided, f"{SESSION_PREFIX}{job.job_id}-{hour}", f"{verb} {job.brief.short}{where}",
            starts, hours, place, at, activity="freelance_work",
            motivation=("It's due " + (f"{job.deadline:%A}" if job.deadline else "soon")
                        + "." if crunch else "Mornings are for writing, in theory."
                        if planning_ahead else "Might as well get some of it done."),
        ),
    ]  # fmt: skip


# (how the hour went, progress, how he'd note it, chance of a note)
_HOURS: tuple[tuple[str, float, tuple[str, ...], float], ...] = (
    ("flow", 1.3, (
        "Got properly into {short}. An hour went by without me noticing.",
        "Good hour on {short}: worked out how to say the awkward bit.",
        "Finally got {short} into a shape I like.",
        "Found the line {short} has been missing. Wrote it on a Post-it in case it vanished.",
    ), 0.45),
    ("steady", 1.0, (), 0.0),
    ("slog", 0.6, (
        "Slow going on {short}. Rewrote the same paragraph three times.",
        "Slogging through {short} today. Every sentence wants rewriting.",
        "Stuck on the middle of {short} for most of the hour.",
    ), 0.4),
    ("distracted", 0.3, (
        "Meant to work on {short}. Mostly looked at my phone.",
        "Sat down to {short} and somehow tidied the desk instead.",
        "Kept drifting off {short} into reading the news. Called it research.",
    ), 0.5),
)  # fmt: skip


def _work_an_hour(
    history: Sequence[DomainEvent],
    everything: Sequence[Job],
    at: datetime,
    session: tuple[str, str],
    energy: float,
    hour: str,
) -> list[DomainEvent]:
    schedule_id, place = session
    job = next(
        (j for j in everything if schedule_id.startswith(f"{SESSION_PREFIX}{j.job_id}")), None
    )
    if job is None or job.status != "active":
        return []
    if job.last_worked is not None and at - job.last_worked < timedelta(minutes=55):
        return []
    if schedule_id.endswith("-call"):
        call = _event(WORKED, at, job_id=job.job_id, worked_hours=round(job.worked + 1.5, 2),
                      hours=1.0, how="call", place_id=place)  # fmt: skip
        return [call, _note(call, f"Interviewed someone for {job.brief.short}. Forty minutes of "
                            "gold and twenty of them asking what the piece was for again.", at, 0.4)]  # fmt: skip
    evening = at.hour >= 15
    weights = (0.07 + 0.12 * energy, 0.5, 0.2 + (0.1 if evening else 0),
               0.1 + (0.2 if energy < 0.4 else 0) + (0.1 if evening else 0))  # fmt: skip
    roll = _roll("hour-went", job.job_id, hour) * sum(weights)
    how, gain, words, noted = _HOURS[-1]
    for option, weight in zip(_HOURS, weights):
        if roll < weight:
            how, gain, words, noted = option
            break
        roll -= weight
    total = round(job.worked + gain, 2)
    worked = _event(
        WORKED, at, job_id=job.job_id, worked_hours=total, hours=1.0, how=how, place_id=place
    )
    output = [worked]
    if words and _roll("note", job.job_id, hour) < noted:
        said = words[int(_roll("words", job.job_id, hour) * len(words))]
        output.append(
            _note(worked, said.format(short=job.brief.short), at, 0.25, location_id=place)
        )
    # Writing is filed whole and then edited; other work goes as a draft part way.
    draft_at = 1.0 if job.writing else 0.6
    if not job.drafted and job.brief.kind != "column" and total >= draft_at * job.needed:
        due = at + timedelta(days=1 + int(_roll("feedback-in", job.job_id) * 4))
        draft = _event(DRAFT, at, job_id=job.job_id, feedback_due=due.replace(hour=11).isoformat())
        filed = (
            f"Filed {job.brief.short} to {job.client}. Now the waiting, and the rereading it "
            "in my head."
            if job.writing
            else f"Sent the first draft of {job.brief.short} to {job.client}. Now the waiting."
        )
        output += [draft, _note(draft, filed, at, 0.45)]
    elif total >= job.needed:
        output += _finished(job, at)
    return output


def _finished(job: Job, at: datetime) -> list[DomainEvent]:
    if job.writing:
        # The final version: out in a week or so, and paid for after that.
        out = at + timedelta(days=3 + int(_roll("out-in", job.job_id) * 8))
        final = _event(DELIVERED, at, job_id=job.job_id, short=job.brief.short,
                       publish_due=out.replace(hour=8).isoformat())  # fmt: skip
        return [final, _note(final, f"Sent the final version of {job.brief.short}. Out "
                             f"{out:%A %-d %B}, they say.", at, 0.45)]  # fmt: skip
    terms = job.brief.pays_days
    owed = job.fee_pence - (job.deposit_pence if job.deposit_paid else 0)
    delivered = _event(DELIVERED, at, job_id=job.job_id,
                       pay_due=(at + timedelta(days=terms)).replace(hour=11).isoformat(),
                       short=job.brief.short, fee_pence=job.fee_pence)  # fmt: skip
    return [delivered, _note(delivered, f"Finished {job.brief.short} and sent the invoice: "
                             f"£{owed // 100}" + (", thirty days." if terms >= 30 else "."),
                             at, 0.5)]  # fmt: skip


# (what they said, extra share of the hours, extra share of the fee, how he'd note it, feeling)
_FEEDBACK = (
    ("pleased", 0.05, 0.0, "{client} liked the draft of {short}. Just a couple of tweaks.", "contentment"),
    ("fine", 0.12, 0.0, "Feedback on {short} from {client}: fine, a list of changes. Fair enough.", ""),
    ("more", 0.35, 0.0, "{client} want {short} to cover a load of things nobody mentioned before. "
     "Same fee, apparently.", "irritation"),
    ("more_paid", 0.35, 0.15, "{client} want more in {short}; I said it'd cost a bit more and "
     "they agreed. Small victory.", ""),
)  # fmt: skip
_EDITS = (
    ("loved", 0.05, "The editor loved {short}. Changed two words. I read the email three times.",
     "contentment"),
    ("light", 0.1, "Light edits on {short}. A couple of questions, one cut I'd have made myself.", ""),
    ("new_top", 0.25, "Edits on {short}: they want a new top. They're right, which is annoying.",
     "irritation"),
    ("cut", 0.15, "Edits on {short}: cut three hundred words. Every one of them was a favourite.",
     ""),
)  # fmt: skip


def _deadlines(everything: Sequence[Job], at: datetime) -> list[DomainEvent]:
    for job in everything:
        if job.status == "waiting" and job.waiting_until is not None and at >= job.waiting_until:
            if not 9 <= at.hour <= 18:
                continue
            if job.writing:
                said, more, words, feeling = _EDITS[int(_roll("edits", job.job_id) * len(_EDITS))]
                extra = 0.0
            else:
                said, more, extra, words, feeling = _FEEDBACK[
                    int(_roll("said", job.job_id) * len(_FEEDBACK))
                ]
            back = _event(
                FEEDBACK, at, job_id=job.job_id, said=said, feeling=feeling, short=job.brief.short,
                client=job.client, needed_hours=round(job.needed * (1 + more), 1),
                fee_pence=int(job.fee_pence * (1 + extra)),
            )  # fmt: skip
            return [back, _note(back, words.format(client=_cap(job.client), short=job.brief.short),
                                at, 0.4)]  # fmt: skip
        if (
            # Filed or sent is on time; only work still in his hands can run late.
            job.status == "active"
            and not (job.writing and job.drafted)
            and job.deadline is not None
            and at >= job.deadline
            and job.moved < 2
            and 9 <= at.hour <= 18
        ):
            moved = _event(MOVED, at, job_id=job.job_id, short=job.brief.short,
                           deadline=(at + timedelta(days=3)).replace(hour=17).isoformat())  # fmt: skip
            return [moved, _note(moved, f"Had to email {job.client} for a few more days on "
                                 f"{job.brief.short}. They were fine about it. I wasn't.", at, 0.45)]  # fmt: skip
    return []


_REACTIONS = (
    "Dad read {short}. Said 'very good', which from Dad is practically a parade.",
    "Mum has shared {short} with everyone she's ever met, including the vicar.",
    "A stranger emailed about {short} to say it put into words something they'd been feeling. "
    "That's the bit that makes it worth it.",
    "Someone online was very cross about {short}. Read it twice. They'd only read the headline.",
    "Tom sent a link to {short} to the family chat with 'my little brother, the intellectual'.",
)


def _out_in_the_world(
    history: Sequence[DomainEvent], everything: Sequence[Job], at: datetime
) -> list[DomainEvent]:
    """Publication day, what people make of it, and an editor asking for more."""
    for job in everything:
        if (
            job.writing
            and job.status == "delivered"
            and not job.published
            and job.publish_due is not None
            and at >= job.publish_due
            and 8 <= at.hour <= 11
        ):
            pay = (at + timedelta(days=job.brief.pays_days)).replace(hour=11)
            out = _event(PUBLISHED, at, job_id=job.job_id, short=job.brief.short,
                         client=job.client, pay_due=pay.isoformat())  # fmt: skip
            words = (
                f"My piece is out: {job.brief.short}, with {job.client}. Read it on my phone in "
                "the kitchen like it was someone else's. Sent the invoice."
                if job.brief.kind != "column"
                else f"This month's column is up with {job.client}. Sent the invoice."
            )
            output = [out, _note(out, words, at, 0.6 if job.brief.kind != "column" else 0.35)]
            # Two of his pieces in, an editor may want him regularly.
            theirs = [j for j in everything if j.client == job.client and j.published and j.writing
                      and j.brief.kind != "column"]  # fmt: skip
            if (
                job.brief.kind != "column"
                and len(theirs) >= 1
                and not events_of(history, COLUMN_OFFERED)
                and _roll("column", job.client) < 0.8
            ):
                offer = _event(COLUMN_OFFERED, at, client=job.client)
                output += [offer, _note(offer, f"{_cap(job.client)} asked if I'd write a monthly "
                                        "column. £300 a month, nine hundred words, whatever I "
                                        "like within reason. I said yes before they'd finished "
                                        "the sentence.", at, 0.7)]  # fmt: skip
            return output
        if (
            job.published
            and not job.reacted
            and job.brief.kind != "column"
            and job.pay_due is not None
            and 18 <= at.hour <= 20
        ):
            published_at = job.pay_due - timedelta(days=job.brief.pays_days)
            if at - published_at < timedelta(days=1):
                continue
            # Not the same reaction every time.
            used = {str(e.payload.get("said")) for e in events_of(history, REACTION)[-4:]}
            fresh = [r for r in _REACTIONS if r not in used] or list(_REACTIONS)
            said = fresh[int(_roll("reaction", job.job_id) * len(fresh))]
            reacted = _event(REACTION, at, job_id=job.job_id, short=job.brief.short, said=said)
            return [reacted, _note(reacted, said.format(short=job.brief.short), at, 0.45)]
    return []


def _payments(
    everything: Sequence[Job], at: datetime, awake: bool, comfortable: bool = False
) -> list[DomainEvent]:
    for job in everything:
        if (
            job.deposit_pence
            and not job.deposit_paid
            and job.deposit_due is not None
            and at >= job.deposit_due
            and job.status in {"active", "waiting", "delivered"}
        ):
            paid = _event(PAID, at, job_id=job.job_id, fee_pence=job.deposit_pence, deposit=True,
                          what=f"{job.brief.short} (half up front)", client=job.client)  # fmt: skip
            return [paid, _note(paid, f"The first half for {job.brief.short} came in: "
                                f"£{job.deposit_pence // 100}." + ("" if comfortable else
                                " Breathing a bit easier."), at, 0.4)]  # fmt: skip
        if job.status != "delivered" or job.pay_due is None or at < job.pay_due:
            continue
        if job.writing and not job.published:
            continue
        if not job.late and not job.chased and _roll("late", job.job_id) < job.brief.late_chance:
            late = _event(LATE, at, job_id=job.job_id, short=job.brief.short, client=job.client)
            return [
                late,
                _note(
                    late,
                    f"{_cap(job.client)} haven't paid for {job.brief.short}. It was "
                    "due. I'll have to chase it.",
                    at,
                    0.45,
                ),
                DomainEvent(
                    "intention.formed",
                    "pathos",
                    {
                        "intention_id": f"loop:{late.event_id}",
                        "text": f"chase the invoice for {job.brief.short}",
                        "importance": 0.6,
                        "source": "freelance",
                        "source_event_id": str(late.event_id),
                        "simulated_at": at.isoformat(),
                    },
                    causation_id=late.event_id,
                ),
            ]
        if job.late and not job.chased:
            if (
                not awake
                or not 9 <= at.hour <= 17
                or _roll("chase-now", job.job_id, at.date()) >= 0.4
            ):
                continue
            chased = _event(CHASED, at, job_id=job.job_id, short=job.brief.short,
                            pay_due=(at + timedelta(days=2 + int(_roll("after", job.job_id) * 5))).isoformat())  # fmt: skip
            return [chased, _note(chased, f"Sent a polite chaser about the invoice for "
                                  f"{job.brief.short}. Hate doing it.", at, 0.3)]  # fmt: skip
        owed = job.fee_pence - (job.deposit_pence if job.deposit_paid else 0)
        paid = _event(PAID, at, job_id=job.job_id, fee_pence=owed, what=job.brief.short,
                      client=job.client, late=job.late)  # fmt: skip
        return [paid, _note(paid, f"Got paid for {job.brief.short}: £{owed // 100}."
                            + (" Finally." if job.late else ""), at, 0.4)]  # fmt: skip
    return []


def _maybe_drop_in(
    history: Sequence[DomainEvent], at: datetime, planning: PlanningState, places: frozenset[str]
) -> list[DomainEvent]:
    """Now and then an afternoon at the workshop, giving Ellis a hand, for the love of it."""
    if not self_employed(history) or "workshop" not in places:
        return []
    if at.weekday() not in {1, 3} or at.hour != 12:
        return []
    recent = [e for e in events_of(history, DROP_IN)[-1:] if at - _when(e) < timedelta(days=9)]
    if recent or _roll("drop-in", at.date().isoformat()) >= 0.3:
        return []
    starts = at.replace(hour=14)
    if not _calendar_clear(planning, starts, 2):
        return []
    decided = _event(DROP_IN, at)
    return [
        decided,
        *_book(decided, f"{DROP_IN_PREFIX}{at.date().isoformat()}", "Drop in at the workshop to "
               "give Ellis a hand", starts, 2, "workshop", at, activity="workshop_visit",
               companion=EMPLOYER_ID, motivation="I miss the bench a bit, honestly."),
    ]  # fmt: skip


# -- what he'd say about it -------------------------------------------------------------


def work_view(history: Sequence[DomainEvent], at: datetime) -> list[str]:
    """His work as he'd think of it: what's on, how it's going, what's owed."""
    found: list[str] = []
    for job in jobs(history):
        if job.status in {"declined", "quiet", "paid"}:
            continue
        due = f", due {job.deadline:%A %-d %B}" if job.deadline else ""
        owed = job.fee_pence - (job.deposit_pence if job.deposit_paid else 0)
        if job.status == "enquiry":
            found.append(f"{job.client} asked about {job.brief.short}; haven't replied yet")
        elif job.status == "quoted":
            found.append(
                f"quoted {job.client} £{job.fee_pence // 100} for {job.brief.short}; waiting to hear"
            )
        elif job.status == "pitched":
            found.append(f"pitched {job.brief.short} to {job.client}; waiting to hear")
        elif job.status == "waiting":
            found.append(
                f"{job.brief.short} for {job.client}: "
                + ("filed, waiting on edits" if job.writing else "draft sent, waiting on feedback")
                + due
            )
        elif job.status == "active":
            share = job.worked / job.needed if job.needed else 0
            state = ("not started" if share == 0 else "just started" if share < 0.3
                     else "about half done" if share < 0.65 else "nearly there")  # fmt: skip
            found.append(f"{job.brief.short} for {job.client}: {state}{due}")
        elif job.status == "delivered" and job.writing and not job.published:
            out = f" {job.publish_due:%A}" if job.publish_due else " soon"
            found.append(f"{job.brief.short}: final version in, out{out}")
        elif job.status == "delivered":
            found.append(
                f"{job.brief.short}: "
                + ("out, " if job.published else "done, ")
                + f"invoice for £{owed // 100} "
                + ("overdue, chased" if job.chased else "overdue" if job.late else "not paid yet")
            )
    if events_of(history, COLUMN_OFFERED):
        client = str(events_of(history, COLUMN_OFFERED)[0].payload.get("client"))
        found.append(f"writes a monthly column for {client}")
    return found[:6]
