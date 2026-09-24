"""Patrick's developing sense of who he is, grounded only in how he has actually lived.

Identity here is not a biography recited from a character pack. It is a slow loop:

1. Lived events are *felt* as honouring or neglecting something he cares about.
2. Sustained tension between a held value and his own conduct, a long low stretch, or a
   value he has stopped living at all, opens a private *inquiry*: a question about himself.
3. Evening reflections revisit the question. Only after several revisits on different days
   may he reach an *insight*, which he proposes in his own words and the rules validate.
4. An insight can nudge a value (tiny, rate-limited, bounded drift) and can crystallise a
   hoped-for or feared *possible self* that later colours what he chooses to do.
5. Turning points accumulate into *life chapters*: an autobiography he can actually cite.

Models propose wording; this module decides what is true. Every change cites evidence that
Pathos could have experienced, and replay re-validates it. None of this is ever a diagnosis.

The constants below are part of the replay contract: a recorded life is re-validated against
them on every restart. Loosening a bound is safe; tightening one can make an existing history
unreplayable, so it needs a versioned rule (select limits by the event's schema_version)
rather than an edit in place.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold

STARTING_VALUES: Mapping[str, float] = MappingProxyType(
    {
        "care": 0.78,
        "curiosity": 0.84,
        "reliability": 0.74,
        "autonomy": 0.68,
        "craft": 0.72,
    }
)
VALUE_IDS = tuple(STARTING_VALUES)
VALUE_FLOOR = 0.05
VALUE_CEILING = 0.98
THEMES = (*VALUE_IDS, "mood")
MAX_OPEN_INQUIRIES = 3
MAX_ACTIVE_ASPIRATIONS = 4
EVIDENCE_WINDOW = timedelta(days=21)
INQUIRY_SPACING = timedelta(days=2)
THEME_COOLDOWN = timedelta(days=30)
INSIGHT_MIN_REVISITS = 3
INSIGHT_MIN_SPAN = timedelta(days=4)
FIRST_VALUE_SHIFT_AFTER = timedelta(days=14)
INQUIRY_FADE_AFTER = timedelta(days=21)
INQUIRY_MAX_REVISITS = 6
VALUE_STEP = 0.03
VALUE_MAX_DRIFT = 0.24
VALUE_SPACING = timedelta(days=21)
ASPIRATION_FADE_AFTER = timedelta(days=90)
CHAPTER_MIN_LENGTH = timedelta(days=42)


@dataclass(frozen=True, slots=True)
class Evidence:
    """One lived moment felt as honouring (+1) or neglecting (-1) a value."""

    event_id: str
    value_id: str
    direction: int
    label: str
    at: datetime


@dataclass(frozen=True, slots=True)
class Inquiry:
    inquiry_id: str
    theme: str
    question: str
    opened_at: datetime
    status: str
    revisits: tuple[tuple[str, datetime], ...]
    source_event_ids: tuple[str, ...]
    closed_at: datetime | None = None
    insight_id: str | None = None
    kind: str = "tension"

    @property
    def last_touched(self) -> datetime:
        return self.revisits[-1][1] if self.revisits else self.opened_at


@dataclass(frozen=True, slots=True)
class Insight:
    insight_id: str
    inquiry_id: str
    text: str
    value_id: str | None
    direction: int
    formed_at: datetime


@dataclass(frozen=True, slots=True)
class ValueShift:
    value_id: str
    prior: float
    next: float
    insight_id: str
    shifted_at: datetime


@dataclass(frozen=True, slots=True)
class Aspiration:
    aspiration_id: str
    kind: str
    text: str
    value_id: str
    formed_at: datetime
    insight_id: str
    status: str = "active"
    lived: int = 0
    strayed: int = 0
    last_evidence_at: datetime | None = None
    released_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Chapter:
    chapter_id: str
    number: int
    title: str
    summary: str
    opened_at: datetime
    source_event_ids: tuple[str, ...]
    closed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SelfhoodState:
    evidence: tuple[Evidence, ...] = ()
    inquiries: Mapping[str, Inquiry] = field(default_factory=dict)
    insights: Mapping[str, Insight] = field(default_factory=dict)
    aspirations: Mapping[str, Aspiration] = field(default_factory=dict)
    chapters: tuple[Chapter, ...] = ()
    value_shifts: tuple[ValueShift, ...] = ()
    reflection_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("inquiries", "insights", "aspirations"):
            value = getattr(self, name)
            if not isinstance(value, MappingProxyType):
                object.__setattr__(self, name, MappingProxyType(dict(value)))

    # -- read helpers -------------------------------------------------------------------

    def open_inquiries(self) -> list[Inquiry]:
        return [item for item in self.inquiries.values() if item.status == "open"]

    def active_aspirations(self) -> list[Aspiration]:
        return [item for item in self.aspirations.values() if item.status == "active"]

    @property
    def current_chapter(self) -> Chapter | None:
        return self.chapters[-1] if self.chapters else None

    def value_drift(self, value_id: str) -> float:
        return round(
            sum(
                shift.next - shift.prior
                for shift in self.value_shifts
                if shift.value_id == value_id
            ),
            6,
        )

    def last_value_shift(self, value_id: str) -> datetime | None:
        times = [shift.shifted_at for shift in self.value_shifts if shift.value_id == value_id]
        return max(times) if times else None

    def recent_evidence(self, now: datetime, value_id: str | None = None) -> list[Evidence]:
        return [
            item
            for item in self.evidence
            if now - EVIDENCE_WINDOW <= item.at <= now
            and (value_id is None or item.value_id == value_id)
        ]

    # -- fold ---------------------------------------------------------------------------

    def cites_lived_evidence(self, source_id: str) -> bool:
        return any(item.event_id == source_id for item in self.evidence) or (
            source_id in self.reflection_ids
        )

    def apply(self, event: DomainEvent) -> SelfhoodState:
        # Most events are irrelevant; return self untouched so the fold stays linear.
        if event.kind.startswith("self."):
            return _apply_self_event(self, event)
        if event.aggregate_id != "pathos":
            return self
        if event.kind == "reflection.recorded":
            return replace(self, reflection_ids=(*self.reflection_ids, str(event.event_id)))
        felt = value_evidence(event)
        if not felt:
            return self
        at = event_time(event)
        if at is None:
            return self
        event_id = str(event.event_id)
        fresh = [
            Evidence(event_id, value, sign, label, at)
            for value, sign, label in felt
            if not self._felt_today(value, label, at)
        ]
        if not fresh:
            return self
        return replace(self, evidence=(*self.evidence, *fresh))

    def _felt_today(self, value_id: str, label: str, at: datetime) -> bool:
        """One lived moment often lands as several events; feel each kind once a day."""
        for item in reversed(self.evidence):
            if item.at.date() != at.date():
                return False
            if item.value_id == value_id and item.label == label:
                return True
        return False


def _apply_self_event(state: SelfhoodState, event: DomainEvent) -> SelfhoodState:
    p = event.payload
    at = _required_time(event)
    kind = event.kind
    if kind == "self.inquiry_opened":
        inquiry_id = _text(p, "inquiry_id")
        theme = _text(p, "theme")
        if inquiry_id in state.inquiries or theme not in THEMES:
            raise ValueError("Inquiry must be new and concern a known theme")
        if len(state.open_inquiries()) >= MAX_OPEN_INQUIRIES:
            raise ValueError("Too many open inquiries")
        if any(item.theme == theme for item in state.open_inquiries()):
            raise ValueError("A question about this theme is already open")
        sources = _sources(p)
        if not all(state.cites_lived_evidence(source) for source in sources):
            raise ValueError("Inquiry cites evidence Pathos never lived")
        question = _text(p, "question")
        return replace(
            state,
            inquiries={
                **state.inquiries,
                inquiry_id: Inquiry(
                    inquiry_id,
                    theme,
                    question,
                    at,
                    "open",
                    (),
                    sources,
                    kind=str(p.get("kind", "tension")),
                ),
            },
        )
    if kind == "self.inquiry_revisited":
        inquiry = _open_inquiry(state, p)
        reflection_id = _text(p, "reflection_id")
        if reflection_id not in state.reflection_ids:
            raise ValueError("A revisit must cite Pathos's own reflection")
        return replace(
            state,
            inquiries={
                **state.inquiries,
                inquiry.inquiry_id: replace(
                    inquiry, revisits=(*inquiry.revisits, (reflection_id, at))
                ),
            },
        )
    if kind == "self.inquiry_faded":
        inquiry = _open_inquiry(state, p)
        return replace(
            state,
            inquiries={
                **state.inquiries,
                inquiry.inquiry_id: replace(inquiry, status="faded", closed_at=at),
            },
        )
    if kind == "self.insight_formed":
        inquiry = _open_inquiry(state, p)
        insight_id = _text(p, "insight_id")
        if insight_id in state.insights:
            raise ValueError("Insight already exists")
        if not insight_ready(inquiry, at):
            raise ValueError("An insight needs repeated reflection across days")
        value_id = p.get("value_id")
        if value_id is not None and value_id not in VALUE_IDS:
            raise ValueError("Insight names an unknown value")
        direction = p.get("direction")
        if direction not in (-1, 0, 1) or (value_id is None and direction != 0):
            raise ValueError("Insight direction is invalid")
        insight = Insight(
            insight_id,
            inquiry.inquiry_id,
            _text(p, "text"),
            value_id if isinstance(value_id, str) else None,
            int(direction),
            at,
        )
        return replace(
            state,
            insights={**state.insights, insight_id: insight},
            inquiries={
                **state.inquiries,
                inquiry.inquiry_id: replace(
                    inquiry, status="resolved", closed_at=at, insight_id=insight_id
                ),
            },
        )
    if kind == "self.value_shifted":
        value_id = _text(p, "value_id")
        shifted_by = state.insights.get(_text(p, "insight_id"))
        if value_id not in VALUE_IDS or shifted_by is None or shifted_by.value_id != value_id:
            raise ValueError("A value can only shift through an insight about it")
        prior, nxt = _number(p, "prior"), _number(p, "next")
        held = developed_values(STARTING_VALUES, state)[value_id]
        if abs(prior - held) > 1e-6 or not VALUE_FLOOR <= nxt <= VALUE_CEILING:
            raise ValueError("Value shift must start from the value as he currently holds it")
        if abs(abs(nxt - prior) - VALUE_STEP) > 1e-9 or (nxt - prior) * shifted_by.direction <= 0:
            raise ValueError("Value shift must be one small step in the insight's direction")
        last = state.last_value_shift(value_id)
        if last is not None and at - last < VALUE_SPACING:
            raise ValueError("Values change too quickly")
        if not state.evidence or at - state.evidence[0].at < FIRST_VALUE_SHIFT_AFTER:
            raise ValueError("Values cannot move before he has lived a while")
        if abs(state.value_drift(value_id) + nxt - prior) > VALUE_MAX_DRIFT + 1e-9:
            raise ValueError("Value drift exceeds its lifetime bound")
        return replace(
            state,
            value_shifts=(
                *state.value_shifts,
                ValueShift(value_id, prior, nxt, shifted_by.insight_id, at),
            ),
        )
    if kind == "self.aspiration_formed":
        aspiration_id = _text(p, "aspiration_id")
        kind_value = _text(p, "kind")
        value_id = _text(p, "value_id")
        insight_id = _text(p, "insight_id")
        if (
            aspiration_id in state.aspirations
            or kind_value not in {"hoped", "feared"}
            or value_id not in VALUE_IDS
            or insight_id not in state.insights
        ):
            raise ValueError("Aspiration must be new, typed, valued and born of an insight")
        if len(state.active_aspirations()) >= MAX_ACTIVE_ASPIRATIONS:
            raise ValueError("Too many active aspirations")
        if any(item.value_id == value_id for item in state.active_aspirations()):
            raise ValueError("Only one living hope or fear per value")
        aspiration = Aspiration(
            aspiration_id, kind_value, _text(p, "text"), value_id, at, insight_id
        )
        return replace(state, aspirations={**state.aspirations, aspiration_id: aspiration})
    if kind == "self.aspiration_progressed":
        # Counts are derived from the cited evidence, never trusted from the payload.
        aspiration = _active_aspiration(state, p)
        cited = set(_sources(p))
        felt = [
            item
            for item in state.evidence
            if item.event_id in cited and item.value_id == aspiration.value_id
        ]
        if {item.event_id for item in felt} != cited:
            raise ValueError("Aspiration progress must cite lived evidence about its value")
        toward = sum(1 for item in felt if (item.direction > 0) == (aspiration.kind == "hoped"))
        return replace(
            state,
            aspirations={
                **state.aspirations,
                aspiration.aspiration_id: replace(
                    aspiration,
                    lived=aspiration.lived + toward,
                    strayed=aspiration.strayed + len(felt) - toward,
                    last_evidence_at=at,
                ),
            },
        )
    if kind == "self.aspiration_released":
        aspiration = _active_aspiration(state, p)
        return replace(
            state,
            aspirations={
                **state.aspirations,
                aspiration.aspiration_id: replace(aspiration, status="released", released_at=at),
            },
        )
    if kind == "self.chapter_opened":
        chapter_id = _text(p, "chapter_id")
        number = p.get("number")
        current = state.current_chapter
        if not isinstance(number, int) or isinstance(number, bool):
            raise ValueError("Chapter number must be an integer")
        if number != len(state.chapters) + 1 or any(
            c.chapter_id == chapter_id for c in state.chapters
        ):
            raise ValueError("Chapters must be opened in order")
        if current is not None and at - current.opened_at < CHAPTER_MIN_LENGTH:
            raise ValueError("A life chapter cannot be that short")
        sources = _sources(p)
        if not all(
            state.cites_lived_evidence(source) or source in state.insights for source in sources
        ):
            raise ValueError("Chapter cites events Pathos never lived")
        title = _text(p, "title")
        if any(item.title.casefold() == title.casefold() for item in state.chapters):
            raise ValueError("A new chapter needs its own name")
        chapters = state.chapters
        if current is not None:
            chapters = (*chapters[:-1], replace(current, closed_at=at))
        chapter = Chapter(chapter_id, number, title, _text(p, "summary"), at, sources)
        return replace(state, chapters=(*chapters, chapter))
    return state


_SELFHOOD_FOLD: IncrementalFold[SelfhoodState] = IncrementalFold(
    SelfhoodState, lambda state, event: state.apply(event)
)


def project_selfhood(events: Sequence[DomainEvent]) -> SelfhoodState:
    return _SELFHOOD_FOLD(events)


def insight_ready(inquiry: Inquiry, now: datetime) -> bool:
    if inquiry.status != "open" or len(inquiry.revisits) < INSIGHT_MIN_REVISITS:
        return False
    first = inquiry.revisits[0][1]
    return now - first >= INSIGHT_MIN_SPAN - timedelta(hours=1)


def developed_values(base: Mapping[str, float], state: SelfhoodState) -> dict[str, float]:
    """Authored starting values plus every validated shift, clamped to sane bounds."""
    values = dict(base)
    for shift in state.value_shifts:
        if shift.value_id in values:
            values[shift.value_id] = round(
                max(
                    VALUE_FLOOR,
                    min(VALUE_CEILING, values[shift.value_id] + shift.next - shift.prior),
                ),
                4,
            )
    return values


# -- evidence -------------------------------------------------------------------------------


def value_evidence(event: DomainEvent) -> tuple[tuple[str, int, str], ...]:
    """How an event is *felt* in terms of Patrick's values: (value, ±1, short label).

    Only Pathos-owned experience counts. Neglect need not be chosen to be felt: missing a
    friend's call still reads, to him, as having let care slip.
    """
    p = event.payload
    kind = event.kind
    if event.aggregate_id != "pathos" or p.get("owner") not in (None, "pathos"):
        return ()
    if kind == "emotion.sampled":
        low_hours = p.get("sustained_low_hours")
        # One felt mark per twelve heavy hours, not one per hourly sample.
        if isinstance(low_hours, int) and low_hours >= 12 and low_hours % 12 == 0:
            return (("mood", -1, "another heavy stretch"),)
        return ()
    if kind in {"commitment.fulfilled", "schedule.completed"}:
        return (("reliability", 1, "kept to something I'd planned"),)
    if kind in {
        "commitment.missed",
        "schedule.failed",
        "prospective_memory.lapsed",
    }:
        return (("reliability", -1, "let something I'd planned slip"),)
    if kind == "meal.unavailable" and p.get("location_id") == "home":
        return (("reliability", -1, "found the cupboards empty again"),)
    if kind in {"follow_up.completed", "phone.callback_completed", "incident.response_completed"}:
        return (("care", 1, "showed up for someone"),)
    if kind == "apology.offered" and p.get("actor_id") == "pathos":
        return (("care", 1, "owned something I'd got wrong"),)
    if kind == "setback.occurred":
        setback = p.get("kind")
        if setback == "work_friction":
            return (("craft", -1, "got called on a rushed job"),)
        if setback == "friendship_drift":
            return (("care", -1, "let a friendship go quiet"),)
        return ()
    if kind == "setback.resolved" and p.get("outcome") == "cleared":
        return (("care", 1, "cleared the air with someone"),)
    if kind == "place.discovered":
        return (("curiosity", 1, "noticed somewhere new"),)
    if kind in {"taste.formed", "taste.revised"} and p.get("stance") == "likes":
        value = p.get("value_id")
        if value in STARTING_VALUES:
            return ((str(value), 1, "found something I love"),)
        return ()
    if kind == "want.purchased":
        value = p.get("value_id")
        if value in STARTING_VALUES:
            return ((str(value), 1, "put money toward something that matters to me"),)
        return ()
    if kind == "social.activity_completed":
        return (("care", 1, "spent real time with someone"),)
    if kind == "scene.started" and "pathos" in {p.get("initiator_id"), p.get("partner_id")}:
        if "user" not in {p.get("initiator_id"), p.get("partner_id")}:
            return (("care", 1, "stopped for a proper conversation with a neighbour"),)
    if kind == "conversation.message" and p.get("speaker") == "pathos":
        # Talking with the person who keeps coming back is part of his life too; at most
        # one such moment a day is felt, so conversation cannot swamp everything else.
        return (("care", 1, "made time for a real conversation"),)
    if kind in {"phone.call_missed", "visitor.missed"}:
        return (("care", -1, "wasn't there when someone reached out"),)
    if kind == "incident.response_declined":
        return (("care", -1, "stayed out of it when someone needed a hand"),)
    if kind == "activity.completed":
        action = p.get("activity")
        if action in {"learn", "attend"}:
            return (("curiosity", 1, "went and learned something"),)
        if action in {"work", "repair"}:
            return (("craft", 1, "finished a piece of real work"),)
    if kind == "activity.stage_completed" and p.get("action") in {"work", "repair", "learn"}:
        return (("craft", 1, "made steady progress on something"),)
    if kind == "action.accepted" and p.get("action") == "repair":
        return (("craft", 1, "mended something with my own hands"),)
    if kind == "self_project.completed":
        return (("craft", 1, "saw a project through"), ("reliability", 1, "finished what I began"))
    if kind in {"self_project.failed", "activity.execution_unfinished"}:
        return (("craft", -1, "left work unfinished"),)
    if kind == "opportunity.noticed" or kind == "dream.inspiration_considered":
        return (("curiosity", 1, "let something new catch my attention"),)
    if kind == "agency.activity_realized" and not isinstance(p.get("companion_id"), str):
        return (("autonomy", 1, "did something purely on my own terms"),)
    if kind == "agency.choice_made" and p.get("decision") in {
        "wait",
        "do_nothing",
        "defer",
        "continue_or_wait",
    }:
        return (("autonomy", 1, "gave myself permission not to do anything"),)
    if kind == "boundary.stated" and p.get("actor_id") == "pathos":
        return (("autonomy", 1, "said where my limit was"),)
    return ()


def event_time(event: DomainEvent) -> datetime | None:
    raw = event.payload.get("simulated_at")
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return parsed if parsed.utcoffset() is not None else None
    return None


# -- payload helpers -------------------------------------------------------------------------


def _required_time(event: DomainEvent) -> datetime:
    at = event_time(event)
    if at is None:
        raise ValueError("Self events need a timezone-aware simulated_at")
    return at


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _number(payload: Mapping[str, object], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _sources(payload: Mapping[str, object]) -> tuple[str, ...]:
    sources = tuple(
        str(payload[key]) for key in (f"source_event_{i}" for i in range(1, 6)) if key in payload
    )
    if not sources or len(set(sources)) != len(sources):
        raise ValueError("Self events need distinct source evidence")
    return sources


def _open_inquiry(state: SelfhoodState, payload: Mapping[str, object]) -> Inquiry:
    inquiry = state.inquiries.get(_text(payload, "inquiry_id"))
    if inquiry is None or inquiry.status != "open":
        raise ValueError("Inquiry is not open")
    return inquiry


def _active_aspiration(state: SelfhoodState, payload: Mapping[str, object]) -> Aspiration:
    aspiration = state.aspirations.get(_text(payload, "aspiration_id"))
    if aspiration is None or aspiration.status != "active":
        raise ValueError("Aspiration is not active")
    return aspiration


def source_payload(source_ids: Sequence[str]) -> dict[str, str]:
    return {f"source_event_{i}": source for i, source in enumerate(source_ids[:5], 1)}
