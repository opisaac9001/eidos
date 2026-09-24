"""Saying he's fine when he isn't, and owning up later.

When you ask how he is and something is weighing on him (Dad in hospital, a falling-out, a
break-up, a friend just moved away, or simply a low patch he can't explain), he doesn't
always say. How likely he is to be honest depends on how close you are: with a close friend
he mostly tells you; with someone he's still getting to know, it's "fine, yeah, you?"

If he brushed it off, then the next time you talk, a day or more later, he may own up: "The
other day, when you asked, I said I was fine. I wasn't really." That honesty, either time,
is the kind of moment friendships deepen on.

The conversation context carries what he's really feeling and whether he'll say
(``how_he_really_is``), or what he owes you honesty about (``owes_honesty``). The reply is
still his, whether from the stand-in or a model.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

ASKED = re.compile(
    r"\b(how are you|how're you|how are things|how's it going|how you doing|how are you doing|"
    r"you ok|you okay|you alright|are you ok|are you okay|how have you been|how've you been)\b",
    re.IGNORECASE,
)
LOW = -0.3
WEIGHS_FOR = timedelta(days=5)
OWN_UP_WITHIN = timedelta(days=4)
HONESTY = {"closest": 0.95, "close": 0.7, "friend": 0.4}
STRANGER_HONESTY = 0.12

# (event kind, payload test, what's weighing on him)
_WEIGHTS = (
    (
        "family.contact",
        lambda p: (
            str(p.get("contact_id", "")).endswith("-call")
            and str(p.get("contact_id", "")).startswith("dad-scare")
        ),
        "Dad's in hospital. A heart thing.",
    ),
    ("friend.falling_out", lambda p: p.get("stage") == "fell_out", "I fell out with a friend."),
    (
        "romance.stage",
        lambda p: p.get("stage") == "broke_up",
        "I've just come out of a relationship.",
    ),
    (
        "romance.stage",
        lambda p: p.get("stage") == "declined",
        "I asked someone out and they said no.",
    ),
    (
        "friend.life_event",
        lambda p: p.get("kind") == "moved_away",
        "One of my closest mates just moved away.",
    ),
    (
        "friend.life_event",
        lambda p: p.get("kind") == "family_worry",
        "A friend's going through a rough time and I'm worried.",
    ),
)


def what_is_weighing(history: Sequence[DomainEvent], at: datetime, valence: float) -> str | None:
    """Something real that's getting to him right now, in his words, if anything is."""
    since = at - WEIGHS_FOR
    for kind, test, words in _WEIGHTS:
        for event in reversed(events_of(history, kind)):
            when = datetime.fromisoformat(str(event.payload["simulated_at"]))
            if when < since:
                break
            if test(event.payload):
                return words
    if valence <= LOW:
        return "I'm just a bit flat. No reason I can name, which is almost worse."
    return None


def masking_context(
    history: Sequence[DomainEvent],
    at: datetime,
    message: str,
    valence: float,
    bond: str | None,
    request_id: str,
) -> tuple[dict[str, object], list[DomainEvent]]:
    """What to put in the conversation context about how he really is, and what it records."""
    owed = _owed(history, at)
    if owed is not None and bond in HONESTY:
        admitted = DomainEvent(
            "feeling.admitted",
            "pathos",
            {
                "person_id": "user",
                "masked_id": str(owed.event_id),
                "what": owed.payload["what"],
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            causation_id=owed.event_id,
        )
        return {
            "owes_honesty": (
                "Last time the user asked how he was, he said he was fine. He wasn't: "
                f"{owed.payload['what']} He wants to own up now, briefly and without drama."
            )
        }, [admitted]
    if not ASKED.search(message):
        return {}, []
    weighing = what_is_weighing(history, at, valence)
    if weighing is None:
        return {}, []
    honest = _roll("honest", request_id) < HONESTY.get(bond or "", STRANGER_HONESTY)
    event = DomainEvent(
        "feeling.shared" if honest else "feeling.masked",
        "pathos",
        {
            "person_id": "user",
            "what": weighing,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
    )
    context: dict[str, object] = {
        "how_he_really_is": {
            "whats_weighing_on_him": weighing,
            "does_he_say": "yes, honestly and briefly"
            if honest
            else "no: he says he's fine and moves the conversation on, the way people do",
        }
    }
    return context, [event]


def _owed(history: Sequence[DomainEvent], at: datetime) -> DomainEvent | None:
    """A recent 'I'm fine' he hasn't owned up to, from an earlier day."""
    admitted = {str(e.payload.get("masked_id")) for e in events_of(history, "feeling.admitted")}
    for event in reversed(events_of(history, "feeling.masked")):
        when = datetime.fromisoformat(str(event.payload["simulated_at"]))
        if at - when > OWN_UP_WITHIN:
            return None
        if str(event.event_id) in admitted:
            return None
        if when.date() < at.date():
            return event
    return None


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
