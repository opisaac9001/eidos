"""The actual work: things people bring in, the jobs on his bench, and how they go.

A shift isn't six hours of "working at the workshop". Someone brings in a radio that
hums, he opens it up, it turns out to be worse than it looked or needs a part Ellis has
to order, and a few shifts later it works and they come back for it, pleased or wincing
at the price. Each job is a small story with its own frustrations and satisfactions,
the kind of thing you'd actually mention when someone asks how work was. He gets a bit
quicker as the jobs add up.

The rules decide everything here (what comes in, how long it takes, what goes wrong),
so it costs no model time; the words are his own short notes of it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, NamedTuple, Sequence

from eidos.application.bookings import remember
from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, events_of

TAKEN = "work.job_taken"
WORKED = "work.job_worked"
SETBACK = "work.job_setback"
FINISHED = "work.job_finished"
COLLECTED = "work.job_collected"
KINDS = (TAKEN, WORKED, SETBACK, FINISHED, COLLECTED)


class Job(NamedTuple):
    item: str  # "a Roberts radio"
    short: str  # "the radio"
    complaint: str  # what the owner says is wrong
    hours: float
    setback_chance: float
    setback: str  # what it turns out to be
    needs_part: bool
    extra_hours: float
    fixed: str


JOBS: tuple[Job, ...] = (
    Job("a Roberts radio", "the Roberts radio", "it hums and then cuts out", 3, 0.4,
        "it wasn't the volume knob after all, it's a dried-out capacitor on the board", False,
        2, "Re-capped the board on the Roberts radio and the hum's gone."),
    Job("a mantel clock", "the mantel clock", "it stops at ten past every time", 4, 0.5,
        "a worn pivot; Ellis has ordered a bush for it", True, 2,
        "Rebushed the pivot on the mantel clock and it's ticked all afternoon."),
    Job("a kitchen chair", "the kitchen chair", "a leg's gone wobbly", 2, 0.3,
        "the joint split once I got it apart, so it needs a new dowel and gluing up", False,
        1, "Glued and clamped the chair leg; it's solid again."),
    Job("a toaster", "the toaster", "it won't stay down", 1, 0.3,
        "the latch spring's gone and it's riveted in", False, 1,
        "Drilled out the rivet on the toaster and fitted a new spring."),
    Job("a bike with a buckled back wheel", "the bike wheel", "it rubs on the brake", 2, 0.35,
        "two spokes are snapped; we're waiting on spokes", True, 1,
        "Trued the bike wheel, near enough perfect."),
    Job("a table lamp", "the lamp", "the flex is frayed and it flickers", 1, 0.2,
        "the switch is cracked inside as well", False, 1,
        "Rewired the lamp with a new flex and switch."),
    Job("a sewing machine", "the sewing machine", "it keeps skipping stitches", 3, 0.4,
        "the timing's out and it's fiddly to set", False, 2,
        "Reset the timing on the sewing machine; it sews a straight seam again."),
    Job("a record player", "the record player", "it runs slow", 2, 0.45,
        "the belt's perished; Ellis has ordered a new one", True, 1,
        "Fitted the new belt on the record player and it's spot on at 33."),
    Job("a vacuum cleaner", "the hoover", "it smells of burning", 2, 0.35,
        "the motor brushes are worn right down", False, 1,
        "New motor brushes in the hoover, and no more burning smell."),
    Job("a chest of drawers", "the chest of drawers", "the drawers stick", 2, 0.2,
        "one of the runners has split", False, 1,
        "Planed and waxed the runners on the chest of drawers; they glide now."),
    Job("a kettle", "the kettle", "it won't switch itself off", 1, 0.3,
        "it's the thermostat, not just the switch", False, 1,
        "Fitted a new thermostat in the kettle."),
    Job("a wooden radio cabinet", "the radio cabinet", "the veneer's lifting", 3, 0.3,
        "there's damp under the veneer, so it has to dry out first", False, 2,
        "Laid the veneer back down on the cabinet; you can barely see it."),
    Job("a child's rocking horse", "the rocking horse", "one rocker's cracked", 3, 0.3,
        "the crack runs further than it looked", False, 2,
        "Scarfed a new piece into the rocking horse's rocker."),
    Job("a Hornby train set", "the train set", "the engine won't go round", 2, 0.35,
        "the motor's fine, it's corroded track joins all the way round", False, 1,
        "Cleaned every track join on the train set and the engine goes round."),
)  # fmt: skip

# People who aren't anyone he knows.
_STRANGERS = (
    "a woman from Mill Lane",
    "an older man who'd come in on the bus",
    "a man who'd clearly had a go at it himself first",
    "a woman who said it was her dad's",
    "a lad who'd found it at a car boot sale",
    "a young woman who'd just moved into one of the new houses",
)
# (reaction, how he'd note it, importance, feeling it leaves)
_REACTIONS = (
    ("delighted", "was really pleased with it, said it hadn't worked that well in years", 0.55,
     "contentment"),
    ("pleased", "seemed pleased and paid without any fuss", 0.4, ""),
    ("price", "winced a bit at the price, though it's fair for the hours", 0.4, ""),
    ("chatty", "stayed to hear what had been wrong with it, which I liked", 0.45, "contentment"),
    ("brief", "barely looked at it before taking it away", 0.35, ""),
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class OnTheBench:
    job_id: str
    job: Job
    owner: str  # how he'd name them
    owner_id: str | None
    taken_at: datetime
    worked: float = 0.0
    needs: float = 0.0
    setback: bool = False
    waiting_until: datetime | None = None
    finished_at: datetime | None = None
    collected: bool = False
    last_worked: datetime | None = None


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _when(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _job(name: object) -> Job | None:
    return next((job for job in JOBS if job.item == name), None)


def _step(jobs: dict[str, OnTheBench], event: DomainEvent) -> dict[str, OnTheBench]:
    if event.kind not in KINDS:
        return jobs
    p = event.payload
    job_id = str(p.get("job_id"))
    if event.kind == TAKEN:
        job = _job(p.get("item"))
        if job is None:
            return jobs
        owner_id = p.get("owner_id")
        taken = OnTheBench(
            job_id, job, str(p.get("owner", "someone")),
            str(owner_id) if owner_id else None, _when(event),
            needs=float(p.get("needs_hours", job.hours)),
        )  # fmt: skip
        return {**jobs, job_id: taken}
    current = jobs.get(job_id)
    if current is None:
        return jobs
    if event.kind == WORKED:
        changed = replace(
            current, worked=float(p.get("worked_hours", current.worked)), last_worked=_when(event)
        )
    elif event.kind == SETBACK:
        raw = p.get("waiting_until")
        changed = replace(
            current,
            setback=True,
            needs=float(p.get("needs_hours", current.needs)),
            waiting_until=datetime.fromisoformat(str(raw)) if raw else None,
        )
    elif event.kind == FINISHED:
        changed = replace(current, finished_at=_when(event))
    else:
        changed = replace(current, collected=True)
    return {**jobs, job_id: changed}


_JOBS: IncrementalFold[dict[str, OnTheBench]] = IncrementalFold(dict, _step)


def jobs(history: Sequence[DomainEvent]) -> list[OnTheBench]:
    return list(_JOBS(history).values())


def _event(kind: str, job_id: str, at: datetime, **payload: object) -> DomainEvent:
    return DomainEvent(
        kind,
        "pathos",
        {"job_id": job_id, **payload, "simulated_at": at.isoformat()},
        correlation_id=job_id,
    )


def repair_job_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    at_work: bool,
    customers: Mapping[str, str] | None = None,
) -> list[DomainEvent]:
    """An hour at the bench, while he's actually there on a shift."""
    if not at_work:
        return []
    recent = events_of(history, *KINDS)[-1:]
    if recent and at - _when(recent[0]) < timedelta(minutes=55):
        return []
    hour = at.isoformat()[:13]
    everything = jobs(history)
    output: list[DomainEvent] = []
    # Someone comes back for a finished job.
    for done in everything:
        if done.finished_at is None or done.collected:
            continue
        if (
            at - done.finished_at >= timedelta(hours=16)
            and _roll("collect", done.job_id, hour) < 0.3
        ):
            reaction, note, importance, feeling = _REACTIONS[
                int(_roll("reaction", done.job_id) * len(_REACTIONS))
            ]
            collected = _event(
                COLLECTED, done.job_id, at, reaction=reaction, feeling=feeling,
                owner=done.owner, item=done.job.item,
            )  # fmt: skip
            # A stranger comes back as "the woman from Mill Lane".
            article, _, rest = done.owner.partition(" ")
            who = f"The {rest}" if article in {"a", "an"} else done.owner
            output += [
                collected,
                remember(
                    collected, f"{who} came back for {done.job.short} and {note}.", at,
                    importance, origin="lived-work", category="experience",
                    person_id=done.owner_id, location_id="workshop",
                ),
            ]  # fmt: skip
            return output
    open_jobs = [j for j in everything if j.finished_at is None]
    workable = [j for j in open_jobs if j.waiting_until is None or j.waiting_until <= at]
    # Something new comes in when the bench is clear, or now and then anyway.
    if (not workable and len(open_jobs) < 3) or (
        len(open_jobs) < 2 and _roll("walk-in", hour) < 0.12
    ):
        output += _take_in(everything, at, customers or {})
        return output
    if not workable or _roll("bench", hour) >= 0.75:
        return []  # serving, sweeping up, helping Ellis: not every hour is at the bench
    job = min(workable, key=lambda j: j.taken_at)
    worked = job.worked + 1.0
    if job.waiting_until is not None and (
        job.last_worked is None or job.last_worked < job.waiting_until
    ):
        # The part's in: back to it.
        part = _event(WORKED, job.job_id, at, worked_hours=worked, part_arrived=True)
        return [
            part,
            remember(
                part, f"The part came in for {job.job.short}, so I got back to it.", at, 0.35,
                origin="lived-work", category="experience", location_id="workshop",
            ),
        ]  # fmt: skip
    # A setback, once, part way in.
    if (
        not job.setback
        and worked >= 0.4 * job.needs
        and _roll("setback", job.job_id) < job.job.setback_chance
    ):
        needs = job.needs + job.job.extra_hours
        waiting = at + timedelta(days=2) if job.job.needs_part else None
        setback = _event(
            SETBACK, job.job_id, at, needs_hours=needs, item=job.job.item,
            needs_part=job.job.needs_part,
            **({"waiting_until": waiting.isoformat()} if waiting else {}),
        )  # fmt: skip
        return [
            _event(WORKED, job.job_id, at, worked_hours=worked),
            setback,
            remember(
                setback, f"Opened up {job.job.short}: {job.job.setback}.", at, 0.45,
                origin="lived-work", category="experience", location_id="workshop",
            ),
        ]  # fmt: skip
    progressed = _event(WORKED, job.job_id, at, worked_hours=worked)
    if worked < job.needs:
        return [progressed]
    finished = _event(FINISHED, job.job_id, at, item=job.job.item, setback=job.setback)
    return [
        progressed,
        finished,
        remember(
            finished, job.job.fixed, at, 0.5 if job.setback else 0.4,
            origin="lived-work", category="experience", location_id="workshop",
        ),
    ]  # fmt: skip


def _take_in(
    everything: Sequence[OnTheBench], at: datetime, customers: Mapping[str, str]
) -> list[DomainEvent]:
    job_id = f"job-{len(everything) + 1}-{at.date().isoformat()}"
    # Not what's already in, or what's just been through.
    on_bench = {j.job.item for j in everything if not j.collected}
    on_bench |= {j.job.item for j in sorted(everything, key=lambda j: j.taken_at)[-6:]}
    options = [job for job in JOBS if job.item not in on_bench] or list(JOBS)
    job = options[int(_roll("which-job", job_id) * len(options))]
    people = sorted(customers.items())
    if people and _roll("known", job_id) < 0.4:
        owner_id, name = people[int(_roll("who", job_id) * len(people))]
        owner = name.split()[0]
    else:
        owner_id, owner = None, _STRANGERS[int(_roll("stranger", job_id) * len(_STRANGERS))]
    # Practice makes him quicker, up to a point.
    done = sum(1 for j in everything if j.finished_at is not None)
    needs = round(job.hours * max(0.6, 1 - 0.03 * done), 1)
    taken = _event(
        TAKEN, job_id, at, item=job.item, owner=owner, needs_hours=needs,
        **({"owner_id": owner_id} if owner_id else {}),
    )  # fmt: skip
    who = owner[0].upper() + owner[1:]
    return [
        taken,
        remember(
            taken, f"{who} brought in {job.item}: {job.complaint}.", at, 0.35,
            origin="lived-work", category="experience", person_id=owner_id,
            location_id="workshop",
        ),
    ]  # fmt: skip


def bench_view(history: Sequence[DomainEvent], at: datetime) -> list[str]:
    """What's on his bench, as he'd think of it, and what he finished lately."""
    from eidos.application.freelance import self_employed

    if self_employed(history):
        return []  # the bench is Ellis's again; whatever was on it, Ellis finishes
    found: list[str] = []
    for job in jobs(history):
        if job.collected:
            continue
        whose = job.owner
        if job.finished_at is not None:
            if at - job.finished_at < timedelta(days=3):
                found.append(f"finished {job.job.short}, waiting for {whose} to collect it")
            continue
        if job.waiting_until is not None and job.waiting_until > at:
            state = f"{job.job.setback}"
        elif job.setback:
            state = f"turned out {job.job.setback}; getting there"
        elif job.worked == 0:
            state = f"{job.job.complaint}; not started on it yet"
        else:
            share = job.worked / job.needs
            state = (
                f"{job.job.complaint}; just started"
                if share < 0.34
                else f"{job.job.complaint}; about half done"
                if share < 0.7
                else f"{job.job.complaint}; nearly there"
            )
        found.append(f"{job.job.short} for {whose}: {state}")
    return found[:4]
