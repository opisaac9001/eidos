"""Is he living like a person? Measures of his recent life against how people actually live.

Not a score from a model, but plain measures over the last days compared with human base
rates where research gives one: how much of the time his mind wanders off what he's doing
(about 47% for people, Killingsworth & Gilbert 2010), how much of his thinking looks ahead
(roughly a third), how often intentions truly slip (diary studies put real forgetting at
roughly 10 to 15 percent of missed intentions), how much his days vary, how regular his
sleep is, how much company he keeps, and how wide his feelings range.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

_FUTURE = re.compile(
    r"\b(tomorrow|tonight|later|next|weekend|soon|will|i'll|gonna|going to|should|need to|"
    r"must|plan|planning|hope|maybe i|might|before|after work|this evening)\b",
    re.IGNORECASE,
)
# Thinking about what's in front of him, not wandering.
_ON_TASK = {"here", "doing", "next", "person", "body"}


def _at(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def _within(events: Sequence[DomainEvent], since: datetime) -> list[DomainEvent]:
    return [e for e in events if (when := _at(e)) is not None and when >= since]


def _compare(value: float | None, low: float, high: float) -> str:
    if value is None:
        return "not enough yet"
    return "in the human range" if low <= value <= high else "low" if value < low else "high"


def _clock_spread(times: Sequence[datetime]) -> float | None:
    """Standard deviation, in minutes, of the time of day things happened."""
    if len(times) < 3:
        return None
    minutes = [(t.hour * 60 + t.minute + (1440 if t.hour < 12 else 0)) for t in times]
    return round(statistics.pstdev(minutes), 1)


def believability_report(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    thoughts: Sequence[tuple[str, str]] = (),
    stream_counts: tuple[int, int] | None = None,
    days: int = 7,
) -> dict[str, Any]:
    """Measures over the last ``days``. ``thoughts`` are (cue kind, text) from his inner
    stream; ``stream_counts`` is (kept, turned away) since the stream started."""
    since = at - timedelta(days=days)
    report: dict[str, Any] = {"window_days": days, "until": at.isoformat()}

    if thoughts:
        wandering = sum(kind not in _ON_TASK for kind, _ in thoughts) / len(thoughts)
        ahead = sum(bool(_FUTURE.search(text)) for _, text in thoughts) / len(thoughts)
        report["mind_wandering"] = {
            "value": round(wandering, 2),
            "people": 0.47,
            "verdict": _compare(wandering, 0.3, 0.6),
        }
        report["thinking_ahead"] = {
            "value": round(ahead, 2),
            "people": "about a third",
            "verdict": _compare(ahead, 0.2, 0.5),
        }
        openers = Counter(" ".join(text.lower().split()[:2]) for _, text in thoughts)
        report["most_repeated_opening"] = openers.most_common(1)[0] if openers else None
    if stream_counts is not None and stream_counts[0] + stream_counts[1]:
        kept, turned = stream_counts
        report["thoughts_turned_away"] = {
            "value": round(turned / (kept + turned), 2),
            "aim": "under 0.25",
            "verdict": "fine" if turned / (kept + turned) < 0.25 else "wasteful",
        }

    formed = _within(events_of(history, "intention.formed"), since)
    slipped = _within(events_of(history, "intention.slipped"), since)
    done = _within(events_of(history, "intention.done"), since)
    if formed:
        slip = len(slipped) / len(formed)
        report["intentions"] = {
            "formed": len(formed),
            "done": len(done),
            "slipped": len(slipped),
            "slip_rate": round(slip, 2),
            "people": "about 0.10 to 0.15",
            "verdict": _compare(slip, 0.05, 0.25) if len(formed) >= 5 else "not enough yet",
        }

    promised = [e for e in formed if e.payload.get("source") == "said"]
    if promised:
        ids = {str(e.payload.get("intention_id")) for e in promised}
        kept = sum(str(e.payload.get("intention_id")) in ids for e in done)
        broken = sum(
            str(e.payload.get("intention_id")) in ids
            for e in _within(events_of(history, "intention.slipped", "intention.dropped"), since)
        )
        report["promises_said_aloud"] = {
            "made": len(promised),
            "kept": kept,
            "let_slip": broken,
            "aim": "most kept; some slip, as with anyone",
        }
    by_day: dict[str, set[str]] = {}
    for event in _within(events_of(history, "schedule.created"), since):
        when = _at(event)
        if when is not None and event.payload.get("actor_id") in {None, "pathos"}:
            by_day.setdefault(when.date().isoformat(), set()).add(
                str(event.payload.get("title", "")).casefold()
            )
    ordered = [by_day[day] for day in sorted(by_day)]
    if len(ordered) >= 2:
        overlaps = [len(a & b) / len(a | b) for a, b in zip(ordered, ordered[1:]) if a | b]
        same = statistics.mean(overlaps) if overlaps else 0.0
        report["days_alike"] = {
            "value": round(same, 2),
            "aim": "under 0.5 (0 = every day different, 1 = every day the same)",
            "verdict": "varied" if same < 0.5 else "samey",
        }

    woke = [t for e in _within(events_of(history, "sleep.ended"), since) if (t := _at(e))]
    slept = [t for e in _within(events_of(history, "sleep.started"), since) if (t := _at(e))]
    report["sleep"] = {
        "wake_spread_minutes": _clock_spread(woke),
        "bedtime_spread_minutes": _clock_spread(slept),
        "aim": "some spread, roughly 20 to 90 minutes; 0 means clockwork",
        "verdict": _compare(_clock_spread(woke), 20, 90),
    }

    span = max(1, days)
    report["company_per_day"] = {
        "encounters": round(len(_within(events_of(history, "npc.encountered"), since)) / span, 1),
        "texts_and_calls": round(
            len(_within(events_of(history, "contact.reached_out", "family.contact"), since)) / span,
            1,
        ),
        "group_chat_posts": round(
            sum(
                1
                for e in _within(events_of(history, "chat.message"), since)
                if e.payload.get("speaker_id") == "pathos"
            )
            / span,
            1,
        ),
    }

    samples = _within(events_of(history, "emotion.sampled"), since)
    if samples:
        labels = Counter(str(e.payload.get("label")) for e in samples)
        valences = [float(e.payload.get("valence", 0) or 0) for e in samples]
        report["feelings"] = {
            "distinct": len(labels),
            "most_common": labels.most_common(3),
            "valence_range": [round(min(valences), 2), round(max(valences), 2)],
            "verdict": "varied" if len(labels) >= 4 else "flat",
        }
    report["happenings"] = len(_within(events_of(history, "happening.occurred"), since))
    report["body_noticed"] = len(_within(events_of(history, "body.sensed"), since))
    return report
