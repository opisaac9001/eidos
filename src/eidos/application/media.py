"""The book on his bedside table, the series he's halfway through, the album on repeat.

Real lives carry things across weeks. Patrick is usually partway through a book (a chapter
or two before bed), a series (an episode on a free evening) and an album (on repeat for a
week or two). New books come off his own shelf, or from the library and second-hand shops
once he knows them. How much he likes a work is a mix of a hidden temperament for that
particular work and how well it fits him, so he can love one and give up on another halfway
("life's too short"). Loving a couple of works of the same kind becomes a taste.

The works are real titles that fit his authored interests; only titles and creators are
used. Everything is decided by rules and replay-stable; models voice his opinions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of


@dataclass(frozen=True, slots=True)
class Work:
    media_id: str
    kind: str  # book, series, album
    title: str
    creator: str
    genre: str
    units: int  # chapters, episodes, or plays until it has run its course


WORKS: tuple[Work, ...] = (
    # Books: his shelf first, then what turns up in libraries and second-hand shops.
    Work("piranesi", "book", "Piranesi", "Susanna Clarke", "strange fiction", 12),
    Work(
        "station-eleven", "book", "Station Eleven", "Emily St. John Mandel", "science fiction", 18
    ),
    Work(
        "left-hand", "book", "The Left Hand of Darkness", "Ursula K. Le Guin", "science fiction", 20
    ),
    Work("remains", "book", "The Remains of the Day", "Kazuo Ishiguro", "literary fiction", 14),
    Work("psalm", "book", "A Psalm for the Wild-Built", "Becky Chambers", "science fiction", 8),
    Work(
        "roadside", "book", "Roadside Picnic", "Arkady and Boris Strugatsky", "science fiction", 10
    ),
    Work("h-is-for-hawk", "book", "H is for Hawk", "Helen Macdonald", "nature writing", 16),
    Work("ways-of-seeing", "book", "Ways of Seeing", "John Berger", "photography and art", 7),
    Work("stoner", "book", "Stoner", "John Williams", "literary fiction", 16),
    Work("dispossessed", "book", "The Dispossessed", "Ursula K. Le Guin", "science fiction", 22),
    Work("klara", "book", "Klara and the Sun", "Kazuo Ishiguro", "literary fiction", 15),
    Work(
        "shop-class",
        "book",
        "The Case for Working with Your Hands",
        "Matthew Crawford",
        "making things",
        12,
    ),
    Work("overstory", "book", "The Overstory", "Richard Powers", "nature writing", 28),
    Work("never-let-me-go", "book", "Never Let Me Go", "Kazuo Ishiguro", "literary fiction", 16),
    # Series.
    Work("detectorists", "series", "Detectorists", "Mackenzie Crook", "gentle comedy", 19),
    Work("severance", "series", "Severance", "Dan Erickson", "science fiction", 19),
    Work("slow-horses", "series", "Slow Horses", "Will Smith", "spy drama", 24),
    Work("the-bear", "series", "The Bear", "Christopher Storer", "kitchen drama", 28),
    Work("repair-shop", "series", "The Repair Shop", "BBC", "making things", 20),
    Work(
        "station-eleven-tv", "series", "Station Eleven", "Patrick Somerville", "science fiction", 10
    ),
    # Albums: played until he's had his fill.
    Work("airports", "album", "Music for Airports", "Brian Eno", "ambient", 10),
    Work("young-team", "album", "Young Team", "Mogwai", "post-rock", 9),
    Work(
        "earth-not-cold",
        "album",
        "The Earth Is Not a Cold Dead Place",
        "Explosions in the Sky",
        "post-rock",
        9,
    ),
    Work("takk", "album", "Takk...", "Sigur Rós", "post-rock", 10),
    Work(
        "music-has-the-right",
        "album",
        "Music Has the Right to Children",
        "Boards of Canada",
        "electronic",
        10,
    ),
    Work("spaces", "album", "Spaces", "Nils Frahm", "ambient", 8),
    Work("for-emma", "album", "For Emma, Forever Ago", "Bon Iver", "folk", 8),
    Work("in-rainbows", "album", "In Rainbows", "Radiohead", "indie", 10),
)
BY_ID = {work.media_id: work for work in WORKS}
ON_HIS_SHELF = ("piranesi", "station-eleven", "remains")
FROM_THE_LIBRARY = frozenset({"library", "reading-room"})
FROM_SECOND_HAND = frozenset({"secondhand", "charity-shop"})
# The genres his authored interests lean toward; they tilt, never decide.
LEANS_TOWARD = {
    "science fiction": 0.15,
    "strange fiction": 0.12,
    "post-rock": 0.15,
    "ambient": 0.12,
    "making things": 0.12,
    "photography and art": 0.08,
}
GENRE_VALUE = {
    "science fiction": "curiosity",
    "strange fiction": "curiosity",
    "literary fiction": "care",
    "nature writing": "autonomy",
    "making things": "craft",
    "post-rock": "autonomy",
    "ambient": "autonomy",
}
GENRE_LABELS = {
    "ambient": "ambient music",
    "electronic": "electronic music",
    "folk": "folk music",
    "indie": "indie music",
    "making things": "books and shows about making things",
    "gentle comedy": "gentle comedy",
}
VERBS = {"book": "reading", "series": "watching", "album": "listening to"}


def liking(work: Work) -> float:
    """How much he'll like it, from -1 to 1: his temperament for it, and how it fits him."""
    digest = sha256(f"media-affinity:{work.media_id}".encode()).digest()
    temperament = int.from_bytes(digest[:6], "big") / float(1 << 48) - 0.5
    return max(-1.0, min(1.0, round(0.1 + temperament * 1.1 + LEANS_TOWARD.get(work.genre, 0), 2)))


def media_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    location_id: str,
    free: bool,
    known_places: frozenset[str],
) -> list[DomainEvent]:
    """A little of whatever he's into, and picking up the next thing when one finishes."""
    if not awake:
        return []
    return (
        _acquire(history, at, location_id, known_places)
        or _start_next(history, at, location_id)
        or _session(history, at, location_id, free)
    )


def current(history: Sequence[DomainEvent]) -> dict[str, tuple[Work, int]]:
    """kind -> (work, units so far) for each thing he's partway through."""
    under_way: dict[str, tuple[Work, int]] = {}
    for event in events_of(
        history, "media.started", "media.progressed", "media.finished", "media.abandoned"
    ):
        work = BY_ID.get(str(event.payload.get("media_id")))
        if work is None:
            continue
        if event.kind == "media.started":
            under_way[work.kind] = (work, 0)
        elif event.kind == "media.progressed" and work.kind in under_way:
            under_way[work.kind] = (work, int(event.payload.get("done", 0)))
        elif event.kind in {"media.finished", "media.abandoned"}:
            under_way.pop(work.kind, None)
    return under_way


def media_context(history: Sequence[DomainEvent]) -> dict[str, object]:
    """What he's into at the moment and what he made of the last few, for his own voice."""
    now = current(history)
    finished = [
        {
            "title": str(e.payload["title"]),
            "by": str(e.payload["creator"]),
            "what_he_thought": str(e.payload["verdict"]),
            "gave_up": e.kind == "media.abandoned",
        }
        for e in events_of(history, "media.finished", "media.abandoned")
    ][-5:]
    return {
        "currently": [
            {
                "kind": work.kind,
                "title": work.title,
                "by": work.creator,
                "how_far": f"{round(100 * done / work.units)}%",
            }
            for work, done in now.values()
        ],
        "recently_finished": finished,
    }


# -- rules -----------------------------------------------------------------------------


def _owned_unstarted(history: Sequence[DomainEvent]) -> list[Work]:
    started = {str(e.payload.get("media_id")) for e in events_of(history, "media.started")}
    acquired = [str(e.payload.get("media_id")) for e in events_of(history, "media.acquired")]
    return [
        BY_ID[media_id]
        for media_id in (*ON_HIS_SHELF, *acquired)
        if media_id not in started and media_id in BY_ID
    ]


def _acquire(
    history: Sequence[DomainEvent], at: datetime, location_id: str, known_places: frozenset[str]
) -> list[DomainEvent]:
    """Browsing the library or a second-hand shop, he comes away with the next book."""
    if location_id not in (FROM_THE_LIBRARY | FROM_SECOND_HAND) or location_id not in known_places:
        return []
    if len(_owned_unstarted(history)) >= 2:
        return []
    today = at.date().isoformat()
    if any(
        str(e.payload.get("simulated_at", ""))[:10] == today
        for e in events_of(history, "media.acquired")
    ):
        return []
    have = {
        str(e.payload.get("media_id"))
        for e in events_of(history, "media.acquired", "media.started")
    }
    candidates = [
        w
        for w in WORKS
        if w.kind == "book" and w.media_id not in have and w.media_id not in ON_HIS_SHELF
    ]
    if not candidates or _roll("browse", location_id, today) >= 0.6:
        return []
    work = candidates[int(_roll("pick", today) * len(candidates))]
    how = "Borrowed" if location_id in FROM_THE_LIBRARY else "Picked up a second-hand copy of"
    acquired = DomainEvent(
        "media.acquired",
        "pathos",
        {
            "media_id": work.media_id,
            "title": work.title,
            "creator": work.creator,
            "from": location_id,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"media-{work.media_id}",
    )
    return [
        acquired,
        _memory(acquired, f"{how} {work.title} by {work.creator}.", at, 0.3, location_id),
    ]


def _start_next(
    history: Sequence[DomainEvent], at: datetime, location_id: str
) -> list[DomainEvent]:
    """When he finishes something, the next thing starts on a later evening at home."""
    if location_id != "home" or at.hour != 20:
        return []
    now = current(history)
    last_end = {
        str(BY_ID[str(e.payload["media_id"])].kind): _time(e)
        for e in events_of(history, "media.finished", "media.abandoned")
        if str(e.payload.get("media_id")) in BY_ID
    }
    for kind in ("book", "series", "album"):
        if kind in now or at - last_end.get(kind, at - timedelta(days=30)) < timedelta(days=2):
            continue
        if kind == "book":
            options = _owned_unstarted(history)
        else:
            started = {str(e.payload.get("media_id")) for e in events_of(history, "media.started")}
            options = [w for w in WORKS if w.kind == kind and w.media_id not in started]
        if not options:
            continue
        work = (
            options[0]
            if kind == "book"
            else options[int(_roll("start", kind, at.date()) * len(options))]
        )
        started_event = DomainEvent(
            "media.started",
            "pathos",
            {
                "media_id": work.media_id,
                "kind": work.kind,
                "title": work.title,
                "creator": work.creator,
                "genre": work.genre,
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            correlation_id=f"media-{work.media_id}",
        )
        text = {
            "book": f"Started {work.title} by {work.creator}.",
            "series": f"Started watching {work.title}. One episode turned into two.",
            "album": f"Can't stop playing {work.title} by {work.creator}.",
        }[kind]
        return [started_event, _memory(started_event, text, at, 0.3)]
    return []


_SESSION_HOURS = {"book": (21, 22), "series": (19, 21), "album": (8, 21)}
_SESSION_CHANCE = {"book": 0.45, "series": 0.3, "album": 0.12}


def _session(
    history: Sequence[DomainEvent], at: datetime, location_id: str, free: bool
) -> list[DomainEvent]:
    """A chapter before bed, an episode on a free evening, the album on in the background."""
    if location_id != "home" or not free:
        return []
    today = at.date().isoformat()
    progressed_today = {
        str(e.payload.get("media_id"))
        for e in events_of(history, "media.progressed")
        if str(e.payload.get("simulated_at", ""))[:10] == today
    }
    for kind, (work, done) in current(history).items():
        first, last = _SESSION_HOURS[kind]
        if not first <= at.hour <= last or work.media_id in progressed_today:
            continue
        if _roll("session", work.media_id, today) >= _SESSION_CHANCE[kind]:
            continue
        step = 1 + int(_roll("how much", work.media_id, today) * (2 if kind != "album" else 1))
        done = min(work.units, done + step)
        progressed = DomainEvent(
            "media.progressed",
            "pathos",
            {
                "media_id": work.media_id,
                "done": done,
                "of": work.units,
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            correlation_id=f"media-{work.media_id}",
        )
        feeling = liking(work)
        # Something he really isn't getting on with gets dropped, a third of the way in.
        if kind != "album" and feeling <= -0.3 and done >= work.units // 3:
            return [progressed, *_ended(work, at, feeling, gave_up=True)]
        if done >= work.units:
            return [
                progressed,
                *_ended(work, at, feeling, gave_up=False),
                *_taste(history, work, feeling, at),
            ]
        return [progressed]
    return []


def _ended(work: Work, at: datetime, feeling: float, *, gave_up: bool) -> list[DomainEvent]:
    verdict = (
        "gave up on it; life's too short"
        if gave_up
        else "loved it"
        if feeling >= 0.45
        else "really liked it"
        if feeling >= 0.2
        else "it was alright"
        if feeling > -0.1
        else "didn't really get on with it"
    )
    ended = DomainEvent(
        "media.abandoned" if gave_up else "media.finished",
        "pathos",
        {
            "media_id": work.media_id,
            "title": work.title,
            "creator": work.creator,
            "genre": work.genre,
            "verdict": verdict,
            "liking": feeling,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"media-{work.media_id}",
    )
    text = (
        f"Gave up on {work.title} a third of the way in. Life's too short."
        if gave_up
        else {
            "book": f"Finished {work.title}. {verdict[0].upper()}{verdict[1:]}.",
            "series": f"Watched the last episode of {work.title}. {verdict[0].upper()}{verdict[1:]}.",
            "album": f"I think I've finally worn out {work.title}. {verdict[0].upper()}{verdict[1:]}.",
        }[work.kind]
    )
    return [ended, _memory(ended, text, at, 0.4 + 0.3 * abs(feeling))]


def _taste(
    history: Sequence[DomainEvent], work: Work, feeling: float, at: datetime
) -> list[DomainEvent]:
    """Loving a second work of the same kind is how you find out you love the kind."""
    if feeling < 0.45:
        return []
    subject = f"genre:{work.genre}"
    if any(
        e.payload.get("subject") == subject
        for e in events_of(history, "taste.formed", "taste.revised")
    ):
        return []
    loved_before = [
        e
        for e in events_of(history, "media.finished")
        if e.payload.get("genre") == work.genre and float(e.payload.get("liking", 0)) >= 0.45
    ]
    if not loved_before:
        return []
    label = GENRE_LABELS.get(work.genre, work.genre)
    text = f"I think I've found something I love: {label}."
    formed = DomainEvent(
        "taste.formed",
        "pathos",
        {
            "subject": subject,
            "label": label,
            "stance": "likes",
            "value_id": GENRE_VALUE.get(work.genre),
            "evidence_count": len(loved_before) + 1,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"taste-{subject}",
    )
    return [formed, _memory(formed, text, at, 0.5)]


def _memory(
    source: DomainEvent, text: str, at: datetime, importance: float, location_id: str = "home"
) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "experience",
            "source": "lived-media",
            "source_event_id": str(source.event_id),
            "location_id": location_id,
            "owner": "pathos",
            "importance": round(min(0.9, importance), 2),
            "confidence": 1.0,
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))
