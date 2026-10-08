"""Freelance work: technical writing, and small web and IT jobs, the way he lived before.

In the original Patrick pieced a living together from documentation for software
companies and small web or IT jobs for local businesses, valuing being on no one's
corporate path. The rebuild gave him a part-time job at Ellis's workshop instead; this
takes him back, as something that happens in his life rather than a rewrite of it.

The change: his old team in Bristol asks him to rewrite their developer docs. He quotes,
they say yes, he tells Ellis on his next shift, works out the shifts already on the rota
(his notice), and has a last day. Then he's freelance.

Freelancing as it actually goes:
- Work comes from people who know him: old colleagues and agencies now and then, and,
  once he's done a job for someone in town, word of mouth. In a quiet patch he emails his
  old contacts, which helps a bit.
- He quotes. Most say yes, some haggle, some just go quiet.
- He undercounts the hours, like everyone does.
- Nobody sets his hours. He works when he's up and has nothing else on: more as a
  deadline gets close and less when it's far off, less when he's tired or low, at the
  kitchen table or now and then at Juniper. Some hours go well and some go on his phone.
- Drafts go to the client, then there's waiting, then feedback: fine, pleased, or wanting
  more than they asked for.
- A deadline that slips means an awkward email asking for a few more days.
- He invoices when it's done. Companies pay in a month, often late, so he chases; local
  shops pay within the week, or on the spot for an afternoon's IT help.
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
# The work.
ENQUIRY = "freelance.enquiry"
QUOTED = "freelance.quoted"
ACCEPTED = "freelance.accepted"
HAGGLED = "freelance.haggled"
WENT_QUIET = "freelance.went_quiet"
DECLINED = "freelance.declined"
SESSION = "freelance.session_decided"
WORKED = "freelance.worked"
DRAFT = "freelance.draft_sent"
FEEDBACK = "freelance.feedback"
MOVED = "freelance.deadline_moved"
DELIVERED = "freelance.delivered"
LATE = "freelance.payment_late"
CHASED = "freelance.chased"
PAID = "freelance.paid"
REACHED_OUT = "freelance.reached_out"
DROP_IN = "freelance.drop_in_decided"
JOB_KINDS = (ENQUIRY, QUOTED, ACCEPTED, HAGGLED, WENT_QUIET, DECLINED, WORKED, DRAFT,
             FEEDBACK, MOVED, DELIVERED, LATE, CHASED, PAID)  # fmt: skip
SESSION_PREFIX = "freelance-"
DROP_IN_PREFIX = "workshop-drop-in-"
FIRST_JOB = "old-team-docs"
MOST_HOURS_A_DAY = 6
CRUNCH_HOURS_A_DAY = 9
TOO_MUCH_ON = 35.0  # hours of work he already has before he turns things down


class Brief(NamedTuple):
    key: str
    client: str  # how he'd name them
    what: str  # the job, as a to-do
    short: str  # the thing itself: "the API guide"
    hours: float  # what he'd quote for
    rate_pence: int  # per hour, his rate for this kind of work
    days: int  # how long they give him
    kind: str  # docs, web or it
    pays_days: int  # payment terms: 30 for companies, a week for shops, 0 on the spot
    late_chance: float
    place_id: str | None = None  # a local business
    onsite: bool = False  # done there, in an afternoon


# Companies elsewhere: old colleagues, agencies, the occasional cold enquiry.
COMPANIES: tuple[Brief, ...] = (
    Brief(FIRST_JOB, "my old team in Bristol", "rewrite their developer documentation",
          "the developer docs", 24, 2_500, 21, "docs", 30, 0.2),
    Brief("leeds-api", "a small Leeds start-up making accounting software",
          "write a getting-started guide for their API", "the API guide", 14, 2_500, 14,
          "docs", 30, 0.4),
    Brief("bath-charity", "a homelessness charity in Bath",
          "document how their volunteer database works", "the charity's database guide", 8,
          2_200, 12, "docs", 30, 0.3),
    Brief("agency-help", "the agency in Bristol I used to sit next to",
          "tidy up the help pages for a booking app", "the booking app help pages", 12,
          2_500, 10, "docs", 30, 0.35),
    Brief("mapping-docs", "an open-source mapping project",
          "write a proper installation guide", "the installation guide", 10, 2_000, 14,
          "docs", 14, 0.2),
    Brief("museum-site", "a small museum near Wells",
          "fix the broken event pages on their website", "the museum's event pages", 10,
          2_500, 14, "web", 30, 0.3),
)  # fmt: skip
# Businesses in town, by place: what they'd want doing.
LOCAL: tuple[Brief, ...] = (
    Brief("cafe-booking", "Juniper Café", "sort out the café's online booking page",
          "the café's booking page", 4, 3_000, 5, "web", 7, 0.1, "cafe"),
    Brief("bakery-site", "the bakery", "build a simple website with their menu and hours",
          "the bakery's website", 14, 2_800, 14, "web", 7, 0.15, "bakery"),
    Brief("gig-listings", "The Listening Room",
          "set up a gig listings page they can update themselves", "the gig listings page", 10,
          2_800, 12, "web", 7, 0.2, "music-room"),
    Brief("shop-wifi", "the secondhand shop", "get their card reader and wifi working properly",
          "the shop's card reader", 2, 3_000, 3, "it", 0, 0.0, "secondhand", True),
    Brief("hall-projector", "the community hall", "set up the laptop and projector for their talks",
          "the hall's projector", 2, 3_000, 4, "it", 0, 0.0, "community-hall", True),
    Brief("grocer-orders", "the grocer", "move their order book off paper onto a spreadsheet",
          "the grocer's order spreadsheet", 5, 2_800, 8, "it", 7, 0.1, "grocer"),
    Brief("library-list", "the Friends of the Library",
          "sort out the mailing list for their newsletter", "the library mailing list", 3,
          2_500, 6, "it", 7, 0.1, "library"),
)  # fmt: skip
BRIEFS = {brief.key: brief for brief in (*COMPANIES, *LOCAL)}


@dataclass(frozen=True, slots=True)
class Job:
    job_id: str
    brief: Brief
    client: str
    client_id: str | None
    status: str  # enquiry, quoted, active, waiting, delivered, paid, declined, quiet
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


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _when(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _time(value: object) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value else None


def _step(jobs: dict[str, Job], event: DomainEvent) -> dict[str, Job]:
    if event.kind not in JOB_KINDS:
        return jobs
    p = event.payload
    job_id = str(p.get("job_id"))
    if event.kind == ENQUIRY:
        brief = BRIEFS.get(str(p.get("brief")))
        if brief is None:
            return jobs
        client_id = p.get("client_id")
        new = Job(
            job_id, brief, str(p.get("client", brief.client)),
            str(client_id) if client_id else None, "enquiry", _when(event),
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
    elif event.kind in {WENT_QUIET, DECLINED}:
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
        job = replace(job, status="delivered", pay_due=_time(p.get("pay_due")))
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
    text = text[0].upper() + text[1:] if text else text  # "the agency said yes" opens a sentence
    return remember(
        cause, text, at, importance, origin="lived-work", category="experience",
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
) -> list[DomainEvent]:
    """This hour of his working life."""
    output = _the_change(history, at, awake=awake, planning=planning,
                         on_shift_at_workshop=on_shift_at_workshop)  # fmt: skip
    if output:
        return output
    if not freelancing(history) and not events_of(history, OFFER):
        return []
    everything = jobs(history)
    hour = at.isoformat()[:13]
    output += _replies(everything, at, balance_pence)
    output += _payments(everything, at, awake)
    if awake:
        output += _deadlines(everything, at)
    if output:
        return output
    if not awake:
        return []
    output += _new_work(history, everything, at, places, place_people, balance_pence, hour)
    if output:
        return output
    session = _session_now(planning, at)
    if session is not None and location_id == session[1]:
        return _work_an_hour(history, everything, at, session, energy, hour)
    if busy or session is not None:
        return []
    sat_down = _maybe_sit_down(history, everything, at, location_id, energy, valence, planning,
                               places, hour, balance_pence)  # fmt: skip
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
                "Three weeks or so, paid properly. I keep thinking about it.",
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
            "Told Ellis I'm going freelance again. Ellis said they'd half seen it coming, and "
            "that the bench is there whenever I want to drop in. I'll work the shifts that are "
            "already on the rota."
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


def _new_work(
    history: Sequence[DomainEvent],
    everything: Sequence[Job],
    at: datetime,
    places: frozenset[str],
    place_people: Mapping[str, tuple[str, str]],
    balance_pence: int,
    hour: str,
) -> list[DomainEvent]:
    output: list[DomainEvent] = []
    # Replying to an enquiry: a quote, or a polite no when he's got too much on.
    for job in everything:
        if job.status != "enquiry" or not 9 <= at.hour <= 21:
            continue
        on = sum(
            max(0.0, j.needed - j.worked) for j in everything if j.status in {"active", "waiting"}
        )
        if on > TOO_MUCH_ON and job.brief.key != FIRST_JOB:
            no = _event(DECLINED, at, job_id=job.job_id)
            return [no, _note(no, f"Had to say no to {job.client}: {job.brief.what}. "
                              "Too much on already. Feels wrong turning work down.", at, 0.35)]  # fmt: skip
        fee = int(job.brief.hours * job.brief.rate_pence)
        reply_days = 1 if job.brief.key == FIRST_JOB else 1 + int(_roll("reply", job.job_id) * 4)
        quote = _event(QUOTED, at, job_id=job.job_id, fee_pence=fee,
                       reply_due=(at + timedelta(days=reply_days)).isoformat())  # fmt: skip
        return [quote, _note(quote, f"Sent {job.client} a quote for {job.brief.short}: "
                             f"£{fee // 100}. Always feels like guessing.", at, 0.3)]  # fmt: skip
    if not self_employed(history) and freelancing(history):
        return []  # one thing at a time until the workshop's behind him
    if at.minute != 0 or at.hour not in {10, 15}:
        return []
    live = [j for j in everything if j.status in {"enquiry", "quoted", "active", "waiting"}]
    on = sum(max(0.0, j.needed - j.worked) for j in live)
    done_local = [j for j in everything if j.brief.place_id and j.status in {"delivered", "paid"}]
    word_of_mouth = any(at - j.since <= timedelta(days=21) for j in done_local)
    reached = [
        e for e in events_of(history, REACHED_OUT)[-2:] if at - _when(e) <= timedelta(days=12)
    ]
    chance = (0.03 if on > 25 else 0.09) + (0.08 if word_of_mouth else 0) + (0.06 if reached else 0)
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
        client = f"{person[1]} at {brief.client}" if person else brief.client
        job_id = f"job-{brief.key}"
        enquiry = _event(ENQUIRY, at, job_id=job_id, brief=brief.key, client=client,
                         **({"client_id": person[0]} if person else {}))  # fmt: skip
        how = (
            f"{client} asked if I could {brief.what}. Someone had mentioned me, apparently."
            if word_of_mouth and brief.place_id
            else f"An enquiry from {client}: could I {brief.what}?"
        )
        return [enquiry, _note(enquiry, how, at, 0.4, person_id=person[0] if person else None)]
    # A quiet patch: nothing on and nothing coming, so he puts the word out.
    if not live and not reached and at.hour == 10 and at.weekday() < 5:
        last_job = max((j.since for j in everything), default=at)
        if at - last_job >= timedelta(days=7) and _roll("reach-out", at.date().isoformat()) < 0.35:
            out = _event(REACHED_OUT, at)
            output += [out, _note(out, "Emailed a few old contacts to say I'm taking on work. "
                                  "Hate doing it. Quiet weeks make me twitchy about money.", at, 0.4)]  # fmt: skip
    return output


def _replies(everything: Sequence[Job], at: datetime, balance_pence: int) -> list[DomainEvent]:
    for job in everything:
        if job.status != "quoted" or job.reply_due is None or at < job.reply_due:
            continue
        if not 9 <= at.hour <= 18:
            return []
        roll = 0.0 if job.brief.key == FIRST_JOB else _roll("answer", job.job_id)
        if roll < 0.15 and job.fee_pence and job.brief.key != FIRST_JOB:
            # They want it cheaper. With money in the bank he can afford to say no.
            offer = int(job.fee_pence * 0.85)
            haggle = _event(HAGGLED, at, job_id=job.job_id, fee_pence=offer)
            if balance_pence >= 50_000 and _roll("take-it", job.job_id) >= 0.6:
                no = _event(DECLINED, at, job_id=job.job_id)
                return [haggle, no, _note(no, f"{job.client[0].upper() + job.client[1:]} wanted "
                        f"{job.brief.short} for less. I said no, politely. Felt good, then "
                        "worrying.", at, 0.35)]  # fmt: skip
            return [haggle, *_accept(job, at, offer, haggled=True)]
        if roll < 0.8:
            return _accept(job, at, job.fee_pence)
        quiet = _event(WENT_QUIET, at, job_id=job.job_id)
        return [quiet, _note(quiet, f"Never heard back from {job.client} about {job.brief.short}. "
                             "They've gone quiet. Fine. Ish.", at, 0.3)]  # fmt: skip
    return []


def _accept(job: Job, at: datetime, fee: int, haggled: bool = False) -> list[DomainEvent]:
    # Everyone undercounts the hours.
    needed = round(job.brief.hours * (1.0 + 0.5 * _roll("really", job.job_id)), 1)
    deadline = (at + timedelta(days=job.brief.days)).replace(
        hour=17, minute=0, second=0, microsecond=0
    )
    # Bigger jobs for companies: half up front, as freelancers ask for.
    deposit = fee // 2 if fee >= 40_000 and not job.brief.place_id else 0
    deposit_due = (at + timedelta(days=7 + int(_roll("deposit", job.job_id) * 5))).replace(hour=11)
    yes = _event(ACCEPTED, at, job_id=job.job_id, fee_pence=fee, needed_hours=needed,
                 deadline=deadline.isoformat(), brief=job.brief.key, deposit_pence=deposit,
                 **({"deposit_due": deposit_due.isoformat()} if deposit else {}))  # fmt: skip
    words = (
        f"{job.client} said yes to {job.brief.short}, if I'd knock a bit off. I did."
        if haggled
        else "They said yes. I'm doing it: going freelance again. Need to tell Ellis."
        if job.brief.key == FIRST_JOB
        else f"{job.client} said yes to {job.brief.short}. Due {deadline:%A %-d %B}."
    )
    output = [yes, _note(yes, words, at, 0.55 if job.brief.key == FIRST_JOB else 0.4,
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
    if job.brief.onsite and job.brief.place_id:
        # An afternoon there, at a time they agreed.
        day = at + timedelta(days=1 if at.weekday() < 4 else 3)
        starts = day.replace(hour=14, minute=0, second=0, microsecond=0)
        output += _book(
            yes, f"{SESSION_PREFIX}{job.job_id}", f"Sort out {job.brief.short} at {job.brief.client}",
            starts, job.brief.hours, job.brief.place_id, at, activity="freelance_work",
            motivation=f"I said I'd {job.brief.what} this afternoon.",
        )  # fmt: skip
    return output


# -- doing the work ----------------------------------------------------------------------


def _workable(everything: Sequence[Job], at: datetime) -> list[Job]:
    return sorted(
        (j for j in everything if j.status == "active" and not j.brief.onsite),
        key=lambda j: j.deadline or at + timedelta(days=99),
    )


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
) -> list[DomainEvent]:
    """Whether he sits down to work now, and for how long, and where."""
    workable = _workable(everything, at)
    if not workable or location_id not in {"home", "cafe"}:
        return []
    job = workable[0]
    left = job.deadline - at if job.deadline else timedelta(days=30)
    crunch = left <= timedelta(days=2)
    if not _weekday_hours(at, crunch):
        return []
    worked = _worked_today(history, at)
    if worked >= (CRUNCH_HOURS_A_DAY if crunch else MOST_HOURS_A_DAY):
        return []
    # Parkinson's law, and how he is: far-off deadlines get put off, near ones don't.
    pull = 0.45 * (1.7 if crunch else 1.25 if left <= timedelta(days=5) else 0.6
                   if left > timedelta(days=10) else 1.0)  # fmt: skip
    pull *= 0.45 if energy < 0.35 else 0.8 if energy < 0.5 else 1.0
    pull *= 0.7 if valence < -0.2 else 1.0
    if _roll("sit-down", hour) >= min(0.92, pull):
        return []
    hours = 1 + int(_roll("how-long", hour) * (3 if crunch else 2.4))
    if not _calendar_clear(planning, at, hours):
        hours = 1
        if not _calendar_clear(planning, at, 1):
            return []
    # Now and then the café, for a change of scene.
    place = location_id
    starts = at
    # (A coffee there costs money; not when it's tight.)
    if (
        location_id == "home"
        and "cafe" in places
        and balance_pence >= 30_000
        and _roll("cafe", hour) < 0.2
        and not crunch
    ):
        place, starts = "cafe", at + timedelta(hours=1)
        if not _calendar_clear(planning, starts, hours):
            place, starts = "home", at
    decided = _event(SESSION, at, job_id=job.job_id, hours=hours, place_id=place)
    where = "at Juniper" if place == "cafe" else ""
    return [
        decided,
        *_book(
            decided, f"{SESSION_PREFIX}{job.job_id}-{hour}",
            f"Work on {job.brief.short}" + (f" {where}" if where else ""),
            starts, hours, place, at, activity="freelance_work",
            motivation=("It's due " + (f"{job.deadline:%A}" if job.deadline else "soon")
                        + "." if crunch else "Might as well get some of it done."),
        ),
    ]  # fmt: skip


# (how the hour went, progress, how he'd note it, chance of a note)
_HOURS: tuple[tuple[str, float, tuple[str, ...], float], ...] = (
    ("flow", 1.3, (
        "Got properly into {short}. An hour went by without me noticing.",
        "Good hour on {short}: worked out how to explain the awkward bit.",
        "Finally got {short} into a shape I like.",
    ), 0.45),
    ("steady", 1.0, (), 0.0),
    ("slog", 0.6, (
        "Slow going on {short}. Rewrote the same paragraph three times.",
        "Slogging through {short} today. Every sentence wants rewriting.",
        "Stuck on one section of {short} for most of the hour.",
    ), 0.4),
    ("distracted", 0.3, (
        "Meant to work on {short}. Mostly looked at my phone.",
        "Sat down to {short} and somehow tidied the desk instead.",
        "Kept drifting off {short} into reading the news.",
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
    if job is None or job.status not in {"active"}:
        return []
    if job.last_worked is not None and at - job.last_worked < timedelta(minutes=55):
        return []
    if job.brief.onsite:
        # An afternoon's IT help: done, and paid there and then.
        worked = _event(WORKED, at, job_id=job.job_id, worked_hours=job.needed, hours=job.brief.hours,
                        how="steady", place_id=place)  # fmt: skip
        done = _event(DELIVERED, at, job_id=job.job_id, pay_due=at.isoformat())
        paid = _event(PAID, at, job_id=job.job_id, fee_pence=job.fee_pence, what=job.brief.short,
                      client=job.client)  # fmt: skip
        return [worked, done, paid, _note(done, f"Sorted {job.brief.short} at {job.brief.client}. "
                f"Took longer than it should, then it just worked. £{job.fee_pence // 100}, paid "
                "on the spot.", at, 0.45, person_id=job.client_id, location_id=place)]  # fmt: skip
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
    if not job.drafted and job.brief.kind in {"docs", "web"} and total >= 0.6 * job.needed:
        due = at + timedelta(days=1 + int(_roll("feedback-in", job.job_id) * 3))
        draft = _event(DRAFT, at, job_id=job.job_id, feedback_due=due.replace(hour=11).isoformat())
        output += [draft, _note(draft, f"Sent the first draft of {job.brief.short} to {job.client}. "
                                "Now the waiting.", at, 0.4)]  # fmt: skip
    elif total >= job.needed:
        terms = job.brief.pays_days
        delivered = _event(DELIVERED, at, job_id=job.job_id,
                           pay_due=(at + timedelta(days=terms)).replace(hour=11).isoformat(),
                           short=job.brief.short, fee_pence=job.fee_pence)  # fmt: skip
        owed = job.fee_pence - (job.deposit_pence if job.deposit_paid else 0)
        output += [delivered, _note(delivered, f"Finished {job.brief.short} and sent the invoice: "
                                    f"£{owed // 100}" + (", thirty days." if terms >= 30
                                    else "."), at, 0.5)]  # fmt: skip
    return output


# (what they said, extra share of the hours, extra share of the fee, how he'd note it, feeling)
_FEEDBACK = (
    ("pleased", 0.05, 0.0, "{client} liked the draft of {short}. Just a couple of tweaks.", "contentment"),
    ("fine", 0.12, 0.0, "Feedback on {short} from {client}: fine, a list of changes. Fair enough.", ""),
    ("more", 0.35, 0.0, "{client} want {short} to cover a load of things nobody mentioned before. "
     "Same fee, apparently.", "irritation"),
    ("more_paid", 0.35, 0.15, "{client} want more in {short}; I said it'd cost a bit more and "
     "they agreed. Small victory.", ""),
)  # fmt: skip


def _deadlines(everything: Sequence[Job], at: datetime) -> list[DomainEvent]:
    for job in everything:
        if job.status == "waiting" and job.waiting_until is not None and at >= job.waiting_until:
            if not 9 <= at.hour <= 18:
                continue
            said, more, extra, words, feeling = _FEEDBACK[
                int(_roll("said", job.job_id) * len(_FEEDBACK))
            ]
            back = _event(
                FEEDBACK, at, job_id=job.job_id, said=said, feeling=feeling, short=job.brief.short,
                client=job.client, needed_hours=round(job.needed * (1 + more), 1),
                fee_pence=int(job.fee_pence * (1 + extra)),
            )  # fmt: skip
            return [back, _note(back, words.format(client=job.client[0].upper() + job.client[1:],
                                                   short=job.brief.short), at, 0.4)]  # fmt: skip
        if (
            job.status in {"active", "waiting"}
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


def _payments(everything: Sequence[Job], at: datetime, awake: bool) -> list[DomainEvent]:
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
                                f"£{job.deposit_pence // 100}. Breathing a bit easier.", at, 0.4)]  # fmt: skip
        if job.status != "delivered" or job.pay_due is None or at < job.pay_due:
            continue
        if not job.late and not job.chased and _roll("late", job.job_id) < job.brief.late_chance:
            late = _event(LATE, at, job_id=job.job_id, short=job.brief.short, client=job.client)
            return [
                late,
                _note(
                    late,
                    f"{job.client[0].upper() + job.client[1:]} haven't paid for "
                    f"{job.brief.short}. It was due. I'll have to chase it.",
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
        if (
            job.status in {"declined", "quiet", "paid"}
            or job.brief.onsite
            and job.status != "active"
        ):
            continue
        due = f", due {job.deadline:%A %-d %B}" if job.deadline else ""
        if job.status == "enquiry":
            found.append(f"{job.client} asked about {job.brief.short}; haven't replied yet")
        elif job.status == "quoted":
            found.append(
                f"quoted {job.client} £{job.fee_pence // 100} for {job.brief.short}; waiting to hear"
            )
        elif job.status == "waiting":
            found.append(
                f"{job.brief.short} for {job.client}: draft sent, waiting on feedback{due}"
            )
        elif job.status == "active":
            share = job.worked / job.needed if job.needed else 0
            state = ("not started" if share == 0 else "just started" if share < 0.3
                     else "about half done" if share < 0.65 else "nearly there")  # fmt: skip
            found.append(f"{job.brief.short} for {job.client}: {state}{due}")
        elif job.status == "delivered":
            owed = job.fee_pence - (job.deposit_pence if job.deposit_paid else 0)
            found.append(
                f"{job.brief.short}: done, invoice for £{owed // 100} "
                + ("overdue, chased" if job.chased else "overdue" if job.late else "not paid yet")
            )
    return found[:5]
