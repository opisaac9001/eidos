"""What the town says: news that travels between residents, changing a little as it goes.

After Talk of the Town (Ryan et al.): every piece of news a resident holds keeps who they
heard it from, how strongly they believe it and which version of the story it is. News
starts with the person it's about (Rowan's own news) or with someone who saw it happen
(Patrick not turning up), passes between residents who are in the same place, weakens as
it travels, and now and then drifts in the retelling ("Rowan's mum isn't well" becomes
"Rowan's mum's in hospital, apparently"). Patrick hears it second-hand when he runs into
someone, credited to whoever told them, so what he knows of the town is what he's been told.
The rules are code; the models only voice it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, events_of

HEARD = "gossip.heard"
PATRICK = "pathos"
FADES_BELOW = 0.25
SPREAD_CHANCE = 0.25
DRIFT_CHANCE = 0.3
PER_HOUR = 4
# The story first told, and how it tends to drift in the retelling.
_STORIES: Mapping[str, tuple[str, str]] = {
    "family_worry": ("{n}'s family's going through it; a parent's not well.",
                     "{n}'s mum's in hospital, apparently."),
    "moving_announced": ("{n}'s moving away for a job.", "{n}'s leaving town for good, I heard."),
    "new_partner": ("{n}'s seeing someone.", "{n}'s got serious with someone, apparently."),
    "engaged": ("{n}'s engaged.", "{n}'s getting married any minute, I heard."),
    "expecting": ("{n}'s expecting a baby.", "{n}'s having a baby, due any day now."),
    "baby_born": ("{n}'s had the baby.", "{n}'s had the baby; not sleeping at all, apparently."),
    "new_job": ("{n}'s got a new job.", "{n}'s jacked in their job, someone said."),
    "no_show": ("Patrick didn't turn up when he said he would.",
                "Patrick's been letting people down lately, apparently."),
}  # fmt: skip


# Stories that start with his friends' own news, which he heard first-hand.
_FRIEND_NEWS = frozenset(_STORIES) - {"no_show"}


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    subject_id: str
    holder_id: str
    teller_id: str
    text: str
    version: int
    strength: float
    heard_at: datetime
    story: str = ""
    started_at: datetime | None = None


def _at(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _step(held: dict[tuple[str, str], Claim], event: DomainEvent) -> dict[tuple[str, str], Claim]:
    if event.kind != HEARD:
        return held
    p = event.payload
    claim_id = str(p["claim_id"])
    # The story and when it started are the claim's, whoever's version this is.
    earlier = next((c for (cid, _), c in held.items() if cid == claim_id), None)
    claim = Claim(
        claim_id,
        str(p["subject_id"]),
        str(p["holder_id"]),
        str(p.get("teller_id") or ""),
        str(p["text"]),
        int(p.get("version", 0) or 0),
        float(p.get("strength", 1.0) or 1.0),
        _at(event),
        str(p.get("story") or (earlier.story if earlier else "")),
        earlier.started_at if earlier is not None else _at(event),
    )
    return {**held, (claim.claim_id, claim.holder_id): claim}


_HELD: IncrementalFold[dict[tuple[str, str], Claim]] = IncrementalFold(dict, _step)


def held(history: Sequence[DomainEvent]) -> dict[tuple[str, str], Claim]:
    """Every (claim, holder) the town has, with the version each holder believes."""
    return dict(_HELD(history))


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _heard(claim_id: str, subject: str, holder: str, teller: str, text: str, version: int,
           strength: float, at: datetime, kind: str, cause: DomainEvent | None) -> DomainEvent:  # fmt: skip
    return DomainEvent(
        HEARD,
        "pathos",
        {
            "claim_id": claim_id,
            "story": kind,
            "subject_id": subject,
            "holder_id": holder,
            "teller_id": teller,
            "text": text,
            "version": version,
            "strength": round(strength, 3),
            "owner": holder,
            "visibility": "private" if holder != PATRICK else "pathos",
            "simulated_at": at.isoformat(),
        },
        causation_id=cause.event_id if cause is not None else None,
        correlation_id=claim_id,
    )


def gossip_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    names: Mapping[str, str],
    locations: Mapping[str, str],
    residents: frozenset[str],
) -> list[DomainEvent]:
    """This hour: new stories start with the people they're about, and spread between
    residents who are together."""
    output: list[DomainEvent] = []
    known = held(history)
    started = {claim_id for claim_id, _ in known}
    for event in events_of(history, "friend.life_event", "commitment.missed")[-20:]:
        try:
            # A friend's news is still worth passing on for a few weeks.
            window = timedelta(days=21) if event.kind == "friend.life_event" else timedelta(hours=2)
            if _at(event) < at - window:
                continue
        except (KeyError, ValueError):
            continue
        claim_id = f"news:{event.event_id}"
        if claim_id in started:
            continue
        if event.kind == "friend.life_event":
            kind = str(event.payload.get("kind"))
            subject = str(event.payload.get("person_id"))
            if kind not in _STORIES or subject not in residents:
                continue
            holder = subject
        else:
            creditor = _creditor(history, str(event.payload.get("commitment_id")))
            if creditor is None or creditor not in residents:
                continue
            kind, subject, holder = "no_show", PATRICK, creditor
        name = names.get(subject, "Patrick").split()[0]
        text = _STORIES[kind][0].format(n=name)
        output.append(_heard(claim_id, subject, holder, "", text, 0, 1.0, at, kind, event))
    # Spreading: residents together pass on what they've heard.
    together: dict[str, list[str]] = {}
    for person, place in locations.items():
        if person in residents and place not in {"home", "in-transit", "in_transit"}:
            together.setdefault(place, []).append(person)
    claims = {**known, **held(output)}
    stories: dict[str, str] = {}
    for e in [*events_of(history, HEARD), *output]:
        if e.payload.get("story"):
            stories.setdefault(str(e.payload["claim_id"]), str(e.payload["story"]))
    spread = 0
    for place, people in sorted(together.items()):
        for teller in sorted(people):
            for (claim_id, holder), claim in sorted(claims.items()):
                if holder != teller or claim.strength < FADES_BELOW or spread >= PER_HOUR:
                    continue
                for listener in sorted(people):
                    if listener == teller or (claim_id, listener) in claims:
                        continue
                    if claim.subject_id == listener:
                        continue  # nobody tells you your own news
                    if (
                        _roll(claim_id, teller, listener, at.isoformat())
                        >= SPREAD_CHANCE * claim.strength
                    ):
                        continue
                    story = stories.get(claim_id, "")
                    drifted = (
                        story in _STORIES
                        and claim.version == 0
                        and _roll(claim_id, listener, "drift") < DRIFT_CHANCE
                    )
                    name = names.get(claim.subject_id, "Patrick").split()[0]
                    text = _STORIES[story][1].format(n=name) if drifted else claim.text
                    heard = _heard(
                        claim_id,
                        claim.subject_id,
                        listener,
                        teller,
                        text,
                        claim.version + (1 if drifted else 0),
                        claim.strength * 0.85,
                        at,
                        story,
                        None,
                    )
                    output.append(heard)
                    claims[(claim_id, listener)] = Claim(
                        claim_id, claim.subject_id, listener, teller, text,
                        claim.version + (1 if drifted else 0), claim.strength * 0.85, at,
                    )  # fmt: skip
                    spread += 1
    return output


def _creditor(history: Sequence[DomainEvent], commitment_id: str) -> str | None:
    for event in reversed(events_of(history, "commitment.created")):
        if str(event.payload.get("commitment_id")) == commitment_id:
            if event.payload.get("debtor_id") == PATRICK:
                return str(event.payload.get("creditor_id"))
            return None
    return None


def worth_mentioning(history: Sequence[DomainEvent], person_id: str, at: datetime) -> Claim | None:
    """Something this resident has heard about someone else that Patrick hasn't heard
    from anyone, fresh enough to bring up."""
    claims = held(history)
    patrick_has = {claim_id for claim_id, holder in claims if holder == PATRICK}
    found = [
        claim
        for (claim_id, holder), claim in claims.items()
        if holder == person_id
        and claim_id not in patrick_has
        and claim.subject_id not in {person_id, PATRICK}
        and claim.strength >= FADES_BELOW
        and at - (claim.started_at or claim.heard_at) <= timedelta(days=10)
        # His friends told him their own news; only a version that's drifted is news to him.
        and not (claim.story in _FRIEND_NEWS and claim.version == 0)
    ]
    return max(found, key=lambda claim: (claim.strength, claim.heard_at), default=None)


def patrick_heard(
    claim: Claim, teller_id: str, teller_name: str, at: datetime, cause: DomainEvent
) -> list[DomainEvent]:
    """He's been told: he now holds this version, and remembers who told him."""
    from eidos.application.bookings import remember

    heard = _heard(
        claim.claim_id,
        claim.subject_id,
        PATRICK,
        teller_id,
        claim.text,
        claim.version,
        claim.strength * 0.85,
        at,
        claim.story,
        cause,
    )
    return [
        heard,
        remember(
            heard,
            f"{teller_name} told me they'd heard: {claim.text}",
            at,
            0.4,
            origin="lived-gossip",
            person_id=teller_id,
        ),
    ]


def they_remember(
    history: Sequence[DomainEvent], person_id: str, at: datetime, limit: int = 3
) -> list[str]:
    """What this resident remembers of their recent moments with Patrick."""
    found: list[str] = []
    for event in reversed(events_of(history, "npc.encountered", "contact.reached_out")[-60:]):
        if event.payload.get("person_id") != person_id:
            continue
        try:
            days = (at - _at(event)).days
        except (KeyError, ValueError):
            continue
        if days > 21:
            break
        when = "earlier today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"
        if event.kind == "contact.reached_out":
            if event.payload.get("text"):
                found.append(f"{when}, he texted them: {event.payload['text']}")
        else:
            found.append(f"{when}: {event.payload.get('text')}")
        if len(found) >= limit:
            break
    return found
