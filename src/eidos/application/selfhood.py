"""The lived loop through which Patrick comes to know, and slowly change, himself.

A once-daily pass notices tension between what he values and how he has actually been
living, opens at most a few private questions, lets stale ones fade, and tracks whether he
is living toward the person he hopes (or fears) to become. The evening reflection returns to
one open question. After repeated reflection on different days he may reach an insight in
his own words; validated insights can nudge a value by one small step and crystallise a
possible self. Every few weeks a turning point can close one life chapter and open the next.

Only proposals pass through models. Detection, pacing, bounds and provenance are rules.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from hashlib import sha256
from time import perf_counter
from uuid import uuid4

from eidos.application.evening_course import course_context
from eidos.application.family import family_context
from eidos.application.home_move import home_context
from eidos.application.imperfection import imperfection_context
from eidos.application.media import media_context
from eidos.application.seasons import time_of_year
from eidos.application.small_touches import at_home_context, usual_context
from eidos.application.spending import money_context
from eidos.application.user_notes import user_knowledge_context
from eidos.application.work_arc import work_context
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.proposals import ProposalRejected
from eidos.domain.selfhood import (
    ASPIRATION_FADE_AFTER,
    CHAPTER_MIN_LENGTH,
    FIRST_VALUE_SHIFT_AFTER,
    INQUIRY_FADE_AFTER,
    INQUIRY_MAX_REVISITS,
    INQUIRY_SPACING,
    MAX_ACTIVE_ASPIRATIONS,
    MAX_OPEN_INQUIRIES,
    STARTING_VALUES,
    THEME_COOLDOWN,
    VALUE_CEILING,
    VALUE_FLOOR,
    VALUE_IDS,
    VALUE_MAX_DRIFT,
    VALUE_SPACING,
    VALUE_STEP,
    Evidence,
    Inquiry,
    SelfhoodState,
    developed_values,
    insight_ready,
    project_selfhood,
    source_payload,
)
from eidos.domain.tastes import project_tastes
from eidos.domain.wellbeing import project_wellbeing
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest, ModelResponse

DAILY_HOUR = 20
FIRST_QUESTION_AFTER = timedelta(days=7)
BIRTHDAY = date(1998, 10, 27)
CHAPTER_WEEKDAY = 6  # Sunday evening, when a week naturally closes.

_QUESTIONS: Mapping[tuple[str, str], tuple[str, ...]] = {
    ("reliability", "tension"): (
        "Why do I keep letting the things I've planned slip?",
        "Am I someone who follows through, or just someone who means to?",
        "What is it about my plans lately that they keep falling away?",
    ),
    ("care", "tension"): (
        "Am I actually there for people, or do I just mean to be?",
        "Why have I been missing people when they reach for me?",
        "Have I been keeping everyone at arm's length without noticing?",
    ),
    ("craft", "tension"): (
        "Why do I start things and leave them half-made?",
        "Do I still care about doing work well, or have I lost the thread?",
    ),
    ("curiosity", "tension"): (
        "When did I stop following things just because they interested me?",
    ),
    ("autonomy", "tension"): ("Whose life am I actually arranging my days around?",),
    ("care", "dormant"): (
        "When did I last really make time for someone?",
        "Have I been drifting away from the people around here?",
    ),
    ("curiosity", "dormant"): (
        "When did I last go and learn something just because I wanted to?",
        "Have I let my days get too narrow to surprise me?",
    ),
    ("craft", "dormant"): (
        "I haven't made or mended anything in weeks. Does that matter to me as much as I think?",
        "Where did the part of me that likes making things go?",
    ),
    ("autonomy", "dormant"): ("When did I last do something purely because I chose it?",),
    ("reliability", "dormant"): ("Have I stopped planning anything worth following through on?",),
    ("care", "thriving"): (
        "Is being there for people becoming more central to me than I realised?",
        "Why does time with other people feel different lately?",
    ),
    ("curiosity", "thriving"): ("Am I becoming someone who needs new things to stay himself?",),
    ("craft", "thriving"): (
        "Is making things properly becoming who I am, rather than just something I do?",
        "Why does steady work on something feel so settling lately?",
    ),
    ("reliability", "thriving"): (
        "Is keeping my word starting to matter more to me than it used to?",
        "Why does following through feel steadier than it used to?",
    ),
    ("autonomy", "thriving"): (
        "Do I need more room to myself than I used to admit?",
        "Why do my own quiet hours feel so necessary lately?",
        "Am I protecting my free time, or hiding in it?",
    ),
    ("care", "strain"): (
        "Why do Ellis and I keep rubbing each other up the wrong way?",
        "What is it about work lately that keeps ending in words with Ellis?",
    ),
    ("mood", "tension"): (
        "What has been weighing on me lately?",
        "Why has everything felt heavier than it should these past few days?",
        "Is this low stretch about something, or is it just passing through?",
    ),
}


# -- daily pass ------------------------------------------------------------------------------


def selfhood_daily_events(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[DomainEvent]:
    """Once each evening: chapters, question lifecycle, and possible-self tracking."""
    if simulated_at.hour != DAILY_HOUR:
        return []
    output: list[DomainEvent] = []
    state = project_selfhood(history)
    at = simulated_at.isoformat()
    if not state.chapters:
        opened = _first_chapter(state, simulated_at)
        if opened is not None:
            output.append(opened)
    for inquiry in state.open_inquiries():
        stale = simulated_at - inquiry.last_touched >= INQUIRY_FADE_AFTER
        exhausted = len(inquiry.revisits) >= INQUIRY_MAX_REVISITS
        if stale or exhausted:
            output.append(
                DomainEvent(
                    "self.inquiry_faded",
                    "pathos",
                    {
                        "inquiry_id": inquiry.inquiry_id,
                        "reason": "left unresolved" if exhausted else "quietly set aside",
                        "simulated_at": at,
                    },
                    correlation_id=inquiry.inquiry_id,
                )
            )
    state = project_selfhood([*history, *output])
    opened_inquiry = _maybe_open_inquiry(state, simulated_at)
    if opened_inquiry is not None:
        output.append(opened_inquiry)
    output.extend(_aspiration_events(project_selfhood([*history, *output]), simulated_at))
    output.extend(_birthday_events(history, simulated_at))
    return output


def is_birthday(simulated_at: datetime) -> bool:
    return (simulated_at.month, simulated_at.day) == (BIRTHDAY.month, BIRTHDAY.day)


def _birthday_events(history: Sequence[DomainEvent], simulated_at: datetime) -> list[DomainEvent]:
    """Mark the day he turns a year older: a grounded fact, not an invented celebration."""
    if not is_birthday(simulated_at) or simulated_at.date() <= BIRTHDAY:
        return []
    marker = f"birthday-{simulated_at.year}"
    if any(event.correlation_id == marker for event in history[-2000:]):
        return []
    age = simulated_at.year - BIRTHDAY.year
    marked = DomainEvent(
        "self.birthday_marked",
        "pathos",
        {"age": age, "year": simulated_at.year, "simulated_at": simulated_at.isoformat()},
        correlation_id=marker,
    )
    return [
        marked,
        DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": f"Turned {age} today.",
                "simulated_at": simulated_at.isoformat(),
                "category": "milestone",
                "source": "calendar-fact",
                "source_event_id": str(marked.event_id),
                "owner": "pathos",
                "importance": 0.7,
                "confidence": 1.0,
            },
            causation_id=marked.event_id,
            correlation_id=marker,
        ),
    ]


def _first_chapter(state: SelfhoodState, simulated_at: datetime) -> DomainEvent | None:
    sources = [item.event_id for item in state.evidence[:3]] or list(state.reflection_ids[:2])
    if not sources:
        return None
    return DomainEvent(
        "self.chapter_opened",
        "pathos",
        {
            "chapter_id": "chapter-1",
            "number": 1,
            "title": "Finding my feet",
            "summary": (
                "The early stretch of this life: learning the streets, the café, the workshop "
                "and the people who turn up in them, and working out what an ordinary week is."
            ),
            "origin": "first-lived-evidence",
            **source_payload(sources),
            "simulated_at": simulated_at.isoformat(),
        },
        correlation_id="chapter-1",
    )


def _maybe_open_inquiry(state: SelfhoodState, simulated_at: datetime) -> DomainEvent | None:
    open_now = state.open_inquiries()
    if len(open_now) >= MAX_OPEN_INQUIRIES:
        return None
    latest_open = max((item.opened_at for item in state.inquiries.values()), default=None)
    if latest_open is not None and simulated_at - latest_open < INQUIRY_SPACING:
        return None
    values = developed_values(STARTING_VALUES, state)
    lived_since = min((item.at for item in state.evidence), default=None)
    if lived_since is None or simulated_at - lived_since < FIRST_QUESTION_AFTER:
        # A few awkward days are not yet a pattern worth questioning himself over.
        return None
    candidates: list[tuple[float, str, str, list[Evidence]]] = []
    strain = [
        item
        for item in state.recent_evidence(simulated_at, "craft")
        if item.label == "got called on a rushed job"
        and simulated_at - item.at <= timedelta(days=30)
    ]
    if (
        len(strain) >= 2
        and not any(item.theme == "care" for item in open_now)
        and not _cooling(state, "care", simulated_at)
    ):
        # People reflect on salient moments, not statistics: clashing twice with the same
        # person within a month is itself worth wondering about.
        candidates.append((10.0 + len(strain), "care", "strain", strain))
    for theme in (*VALUE_IDS, "mood"):
        if any(item.theme == theme for item in open_now) or _cooling(state, theme, simulated_at):
            continue
        recent = state.recent_evidence(simulated_at, theme)
        neglected = [item for item in recent if item.direction < 0]
        honoured = [item for item in recent if item.direction > 0]
        if theme == "mood":
            week = [item for item in neglected if simulated_at - item.at <= timedelta(days=7)]
            if len(week) >= 2:
                candidates.append((2.0 + len(week), theme, "tension", week))
            continue
        held = values[theme]
        # Proportions, not absolutes: a busy life honours and neglects the same value often.
        # Real ambivalence (finishing some things, abandoning others) is itself worth asking.
        if held >= 0.6 and len(neglected) >= 3 and len(neglected) >= 0.6 * len(honoured):
            candidates.append((held * len(neglected), theme, "tension", neglected))
        elif held < 0.8 and len(honoured) >= 6 and len(neglected) <= 0.2 * len(honoured):
            candidates.append((0.5 * len(honoured) * (1 - held), theme, "thriving", honoured[-5:]))
        elif (
            held >= 0.7
            and not recent
            and lived_since is not None
            and simulated_at - lived_since >= timedelta(days=21)
        ):
            candidates.append((held, theme, "dormant", []))
    if not candidates:
        return None
    asked = {(item.theme, item.kind) for item in state.inquiries.values()}
    # A question he has already lived through gives way to parts of his life not yet asked.
    candidates = [
        (score * (0.25 if (theme, kind) in asked else 1.0), theme, kind, evidence)
        for score, theme, kind, evidence in candidates
    ]
    _, theme, kind, evidence = max(candidates, key=lambda item: (item[0], item[1]))
    sources = [item.event_id for item in evidence[-5:]] or list(state.reflection_ids[-3:])
    if not sources:
        return None
    asked_before = {item.question for item in state.inquiries.values()}
    options = (
        tuple(option for option in _QUESTIONS[(theme, kind)] if option not in asked_before)
        or _QUESTIONS[(theme, kind)]
    )
    date = simulated_at.date().isoformat()
    pick = int(sha256(f"{theme}:{kind}:{date}".encode()).hexdigest()[:8], 16) % len(options)
    inquiry_id = f"inquiry-{theme}-{date}"
    return DomainEvent(
        "self.inquiry_opened",
        "pathos",
        {
            "inquiry_id": inquiry_id,
            "theme": theme,
            "kind": kind,
            "question": options[pick],
            "evidence_count": len(evidence),
            **source_payload(sources),
            "simulated_at": simulated_at.isoformat(),
        },
        correlation_id=inquiry_id,
    )


def _cooling(state: SelfhoodState, theme: str, simulated_at: datetime) -> bool:
    return any(
        item.theme == theme
        and item.closed_at is not None
        and simulated_at - item.closed_at < THEME_COOLDOWN
        for item in state.inquiries.values()
    )


def _aspiration_events(state: SelfhoodState, simulated_at: datetime) -> list[DomainEvent]:
    output: list[DomainEvent] = []
    for aspiration in state.active_aspirations():
        since = aspiration.last_evidence_at or aspiration.formed_at
        fresh = [
            item
            for item in state.evidence
            if item.value_id == aspiration.value_id and since < item.at <= simulated_at
        ][-5:]
        if fresh:
            toward = sum(
                1 for item in fresh if (item.direction > 0) == (aspiration.kind == "hoped")
            )
            output.append(
                DomainEvent(
                    "self.aspiration_progressed",
                    "pathos",
                    {
                        "aspiration_id": aspiration.aspiration_id,
                        "toward": toward,
                        "away": len(fresh) - toward,
                        "labels": "; ".join(dict.fromkeys(item.label for item in fresh)),
                        **source_payload([item.event_id for item in fresh]),
                        "simulated_at": simulated_at.isoformat(),
                    },
                    correlation_id=aspiration.aspiration_id,
                )
            )
        if not fresh and simulated_at - since >= ASPIRATION_FADE_AFTER:
            output.append(
                DomainEvent(
                    "self.aspiration_released",
                    "pathos",
                    {
                        "aspiration_id": aspiration.aspiration_id,
                        "reason": "stopped feeling like mine",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    correlation_id=aspiration.aspiration_id,
                )
            )
    return output


# -- evening reflection ----------------------------------------------------------------------


def inquiry_for_reflection(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> Inquiry | None:
    """The open question he returns to tonight: the one he has left alone longest."""
    open_now = [
        item
        for item in project_selfhood(history).open_inquiries()
        if not item.revisits or item.revisits[-1][1].date() != simulated_at.date()
    ]
    if not open_now:
        return None
    return min(open_now, key=lambda item: (item.last_touched, item.inquiry_id))


def reflection_inquiry_context(
    history: Sequence[DomainEvent], inquiry: Inquiry
) -> dict[str, object]:
    state = project_selfhood(history)
    prompted = [item.label for item in state.evidence if item.event_id in inquiry.source_event_ids][
        -4:
    ]
    return {
        "question": inquiry.question,
        "kind": inquiry.kind,
        "what_prompted_it": prompted,
        "earlier_thoughts": _reflection_texts(history, [rid for rid, _ in inquiry.revisits])[-2:],
        "epistemic_status": "private_open_question",
        "permission": (
            "Let tonight's reflection turn toward this question honestly. You do not have to "
            "answer it; circling, doubting, or noticing something small is enough."
        ),
    }


async def selfhood_after_reflection_events(
    history: Sequence[DomainEvent],
    reflection: DomainEvent,
    inquiry: Inquiry,
    simulated_at: datetime,
    gateway: ModelGateway,
) -> list[DomainEvent]:
    """Record the revisit; if he has sat with the question long enough, invite an insight."""
    revisit = DomainEvent(
        "self.inquiry_revisited",
        "pathos",
        {
            "inquiry_id": inquiry.inquiry_id,
            "reflection_id": str(reflection.event_id),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=reflection.event_id,
        correlation_id=inquiry.inquiry_id,
    )
    output: list[DomainEvent] = [revisit]
    state = project_selfhood([*history, revisit])
    current = state.inquiries[inquiry.inquiry_id]
    if not insight_ready(current, simulated_at):
        return output
    output.extend(await _insight_events(history, state, current, simulated_at, gateway))
    return output


async def _insight_events(
    history: Sequence[DomainEvent],
    state: SelfhoodState,
    inquiry: Inquiry,
    simulated_at: datetime,
    gateway: ModelGateway,
) -> list[DomainEvent]:
    values = developed_values(STARTING_VALUES, state)
    context = {
        "task": "insight",
        "time": simulated_at.isoformat(),
        "question": inquiry.question,
        "theme": inquiry.theme,
        "kind": inquiry.kind,
        "what_prompted_it": [
            item.label for item in state.evidence if item.event_id in inquiry.source_event_ids
        ],
        "my_reflections": _reflection_texts(history, [rid for rid, _ in inquiry.revisits]),
        "values": values,
        "recent_lived_evidence": _evidence_summary(state, simulated_at),
        "earlier_insights": [
            item.text
            for item in sorted(state.insights.values(), key=lambda entry: entry.formed_at)
            if state.inquiries.get(item.inquiry_id) is not None
            and state.inquiries[item.inquiry_id].theme == inquiry.theme
        ][-3:],
        "possible_selves": [
            {"kind": item.kind, "text": item.text} for item in state.active_aspirations()
        ],
        "permission": (
            "If earlier_insights exist on this theme, do not restate them: only a genuinely "
            "further step (a refinement, a complication, a change of heart) counts. "
            "Only if the reflections have genuinely arrived somewhere, state one modest insight "
            "in Patrick's own first-person words. Otherwise keep wondering. An insight may say "
            "a value matters more or less to him than he thought, but only in line with how he "
            "has actually lived. Optionally name one hoped-for or feared version of himself it "
            "points toward. No new events, people, plans, promises or diagnoses."
        ),
    }
    request = ModelRequest(
        capability="pathos_selfhood",
        task_version="1",
        temperature=0.8,
        max_output_tokens=320,
        output_schema=insight_output_schema(),
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    trace_id = str(uuid4())
    started = perf_counter()
    response: ModelResponse | None = None
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "Insight proposal was incomplete")
        proposal = parse_insight_proposal(response.content, inquiry, state, simulated_at)
    except (OSError, TimeoutError, TypeError, ValueError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        return [_trace("failed", trace_id, simulated_at, started, response, gateway, code)]
    output = [_trace("ok", trace_id, simulated_at, started, response, gateway, None)]
    if proposal is None:
        return output
    text, value_id, direction, aspiration = proposal
    if any(item.text == text for item in state.insights.values()):
        # Arriving at the same realisation again is not a new insight; keep wondering.
        return output
    insight_id = f"insight-{inquiry.inquiry_id}"
    insight = DomainEvent(
        "self.insight_formed",
        "pathos",
        {
            "inquiry_id": inquiry.inquiry_id,
            "insight_id": insight_id,
            "text": text,
            "value_id": value_id,
            "direction": direction,
            "simulated_at": simulated_at.isoformat(),
        },
        correlation_id=inquiry.inquiry_id,
    )
    output.append(insight)
    if value_id is not None and direction != 0:
        shift = _value_shift(state, value_id, direction, insight_id, simulated_at)
        if shift is not None:
            output.append(shift)
    if aspiration is not None:
        kind, aspiration_text, aspiration_value = aspiration
        superseded = [
            item for item in state.active_aspirations() if item.value_id == aspiration_value
        ]
        if len(state.active_aspirations()) - len(superseded) >= MAX_ACTIVE_ASPIRATIONS:
            return output
        for old in superseded:
            output.append(
                DomainEvent(
                    "self.aspiration_released",
                    "pathos",
                    {
                        "aspiration_id": old.aspiration_id,
                        "reason": "grew into a different hope" if kind == "hoped" else "reframed",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=insight.event_id,
                    correlation_id=old.aspiration_id,
                )
            )
        output.append(
            DomainEvent(
                "self.aspiration_formed",
                "pathos",
                {
                    "aspiration_id": f"aspiration-{insight_id}",
                    "kind": kind,
                    "text": aspiration_text,
                    "value_id": aspiration_value,
                    "insight_id": insight_id,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=insight.event_id,
                correlation_id=inquiry.inquiry_id,
            )
        )
    return output


def _value_shift(
    state: SelfhoodState, value_id: str, direction: int, insight_id: str, simulated_at: datetime
) -> DomainEvent | None:
    last = state.last_value_shift(value_id)
    if last is not None and simulated_at - last < VALUE_SPACING:
        return None
    if not state.evidence or simulated_at - state.evidence[0].at < FIRST_VALUE_SHIFT_AFTER:
        return None
    step = VALUE_STEP * direction
    if abs(state.value_drift(value_id) + step) > VALUE_MAX_DRIFT + 1e-9:
        return None
    prior = developed_values(STARTING_VALUES, state)[value_id]
    nxt = round(prior + step, 4)
    if not VALUE_FLOOR <= nxt <= VALUE_CEILING:
        return None
    return DomainEvent(
        "self.value_shifted",
        "pathos",
        {
            "value_id": value_id,
            "prior": prior,
            "next": nxt,
            "insight_id": insight_id,
            "simulated_at": simulated_at.isoformat(),
        },
        correlation_id=insight_id,
    )


def insight_output_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["mode", "insight", "value_id", "direction", "aspiration_kind", "aspiration"],
        "properties": {
            "mode": {"type": "string", "enum": ["keep_wondering", "insight"]},
            "insight": {"type": "string", "maxLength": 260},
            "value_id": {"type": "string", "enum": [*VALUE_IDS, "none"]},
            "direction": {"type": "integer", "enum": [-1, 0, 1]},
            "aspiration_kind": {"type": "string", "enum": ["hoped", "feared", "none"]},
            "aspiration": {"type": "string", "maxLength": 160},
        },
    }


_FIRST_PERSON = re.compile(r"\b(I|I'm|I've|I'd|I'll|me|my|myself)\b")
_DIAGNOSIS = re.compile(
    r"\b(depress\w*|anxiety disorder|bipolar|adhd|ptsd|diagnos\w*|disorder)\b", re.IGNORECASE
)
_ACTION_CLAIM = re.compile(
    r"\b(I (?:have|'ve) (?:already )?(?:called|booked|bought|signed|told|messaged|decided to move)|"
    r"I just (?:called|booked|bought|signed))\b",
    re.IGNORECASE,
)


def _check_voice(text: str, *, low: int, high: int, field: str) -> str:
    cleaned = " ".join(text.split())
    if not low <= len(cleaned) <= high:
        raise ProposalRejected("invalid_length", f"{field} must be {low}-{high} characters")
    if not _FIRST_PERSON.search(cleaned):
        raise ProposalRejected("not_first_person", f"{field} must be in his own first person")
    if cleaned.lower().startswith("you "):
        raise ProposalRejected("second_person", f"{field} must not address the reader")
    if _DIAGNOSIS.search(cleaned):
        raise ProposalRejected("diagnosis", f"{field} must not diagnose")
    if _ACTION_CLAIM.search(cleaned):
        raise ProposalRejected("action_claim", f"{field} must not claim new actions")
    return cleaned


def parse_insight_proposal(
    content: str, inquiry: Inquiry, state: SelfhoodState, simulated_at: datetime
) -> tuple[str, str | None, int, tuple[str, str, str] | None] | None:
    """Validate a proposed insight; ``None`` means he is still wondering."""
    try:
        raw = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Insight proposal was not JSON") from None
    if not isinstance(raw, dict):
        raise ProposalRejected("invalid_shape", "Insight proposal must be an object")
    if raw.get("mode") == "keep_wondering":
        return None
    if raw.get("mode") != "insight":
        raise ProposalRejected("invalid_mode", "Unknown insight mode")
    text = _check_voice(str(raw.get("insight", "")), low=16, high=260, field="Insight")
    value_raw = raw.get("value_id")
    direction = raw.get("direction")
    if value_raw not in (*VALUE_IDS, "none") or direction not in (-1, 0, 1):
        raise ProposalRejected("invalid_value", "Insight names an unknown value or direction")
    value_id = None if value_raw == "none" else str(value_raw)
    if value_id is None and direction != 0:
        raise ProposalRejected("invalid_value", "A directional insight must name its value")
    if value_id is not None and value_id != inquiry.theme and direction != 0:
        recent = state.recent_evidence(simulated_at, value_id)
        if not any(item.direction == direction for item in recent):
            raise ProposalRejected(
                "ungrounded_value", "Insight moves a value his recent life does not bear out"
            )
    aspiration: tuple[str, str, str] | None = None
    kind = raw.get("aspiration_kind")
    if kind in {"hoped", "feared"}:
        aspiration_value = value_id or (inquiry.theme if inquiry.theme in VALUE_IDS else None)
        aspiration_text = str(raw.get("aspiration", ""))
        if aspiration_value is not None and aspiration_text.strip():
            aspiration = (
                str(kind),
                _check_voice(aspiration_text, low=12, high=160, field="Possible self"),
                aspiration_value,
            )
    elif kind != "none":
        raise ProposalRejected("invalid_aspiration", "Unknown possible-self kind")
    return text, value_id, int(direction), aspiration


# -- chapters --------------------------------------------------------------------------------


async def selfhood_chapter_events(
    history: Sequence[DomainEvent], simulated_at: datetime, gateway: ModelGateway
) -> list[DomainEvent]:
    """On Sunday evenings (or his birthday), a turning point may open a new chapter."""
    if simulated_at.hour != DAILY_HOUR or not (
        simulated_at.weekday() == CHAPTER_WEEKDAY or is_birthday(simulated_at)
    ):
        return []
    state = project_selfhood(history)
    current = state.current_chapter
    if current is None or simulated_at - current.opened_at < CHAPTER_MIN_LENGTH:
        return []
    turning = [item for item in state.insights.values() if item.formed_at > current.opened_at]
    changed_course = any(
        shift.shifted_at > current.opened_at for shift in state.value_shifts
    ) or any(item.formed_at > current.opened_at for item in state.aspirations.values())
    if not turning or not changed_course:
        return []
    candidates = _chapter_candidates(history, state, current.opened_at)
    context = {
        "task": "chapter",
        "time": simulated_at.isoformat(),
        "closing_chapter": {"title": current.title, "summary": current.summary},
        "earlier_titles": [item.title for item in state.chapters],
        "what_changed": [item.text for item in turning],
        "values": developed_values(STARTING_VALUES, state),
        "possible_selves": [
            {"kind": item.kind, "text": item.text} for item in state.active_aspirations()
        ],
        "candidates": candidates,
        "permission": (
            "Name the new chapter of Patrick's life the way he would privately think of it, "
            "and summarise what has changed in two or three first-person sentences. Cite two "
            "to five supplied candidate ids. Invent nothing that is not in the candidates."
        ),
    }
    request = ModelRequest(
        capability="pathos_selfhood",
        task_version="1",
        temperature=0.85,
        max_output_tokens=320,
        output_schema=chapter_output_schema([item["id"] for item in candidates]),
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    trace_id = str(uuid4())
    started = perf_counter()
    response: ModelResponse | None = None
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "Chapter proposal was incomplete")
        title, summary, cited = parse_chapter_proposal(
            response.content,
            {item["id"] for item in candidates},
            {item.title.casefold() for item in state.chapters},
        )
    except (OSError, TimeoutError, TypeError, ValueError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        return [_trace("failed", trace_id, simulated_at, started, response, gateway, code)]
    number = len(state.chapters) + 1
    return [
        _trace("ok", trace_id, simulated_at, started, response, gateway, None),
        DomainEvent(
            "self.chapter_opened",
            "pathos",
            {
                "chapter_id": f"chapter-{number}",
                "number": number,
                "title": title,
                "summary": summary,
                "origin": "turning-point",
                **source_payload(cited),
                "simulated_at": simulated_at.isoformat(),
            },
            correlation_id=f"chapter-{number}",
        ),
    ]


def _chapter_candidates(
    history: Sequence[DomainEvent], state: SelfhoodState, since: datetime
) -> list[dict[str, str]]:
    candidates = [
        {"id": item.insight_id, "kind": f"insight:{item.value_id or 'mood'}", "text": item.text}
        for item in sorted(state.insights.values(), key=lambda entry: entry.formed_at)
        if item.formed_at > since
    ]
    # New loves and new friendships are told in his own words, not as a generic label.
    in_his_words = {
        str(event.event_id): str(event.payload["text"])
        for event in events_of(history, "taste.formed", "taste.revised", "bond.recognized")
        if isinstance(event.payload.get("text"), str)
    }
    seen: set[str] = set()
    for item in reversed(state.evidence):
        if item.at <= since or len(candidates) >= 12:
            break
        text = in_his_words.get(item.event_id, item.label)
        if text in seen:
            continue
        seen.add(text)
        candidates.append({"id": item.event_id, "kind": item.value_id, "text": text})
    return candidates


def chapter_output_schema(candidate_ids: Sequence[str]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "summary", "cited"],
        "properties": {
            "title": {"type": "string", "maxLength": 60},
            "summary": {"type": "string", "maxLength": 360},
            "cited": {
                "type": "array",
                "minItems": 2,
                "maxItems": 5,
                "items": {"type": "string", "enum": list(candidate_ids)},
            },
        },
    }


def parse_chapter_proposal(
    content: str, candidate_ids: set[str], earlier_titles: set[str] | frozenset[str] = frozenset()
) -> tuple[str, str, list[str]]:
    try:
        raw = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Chapter proposal was not JSON") from None
    if not isinstance(raw, dict):
        raise ProposalRejected("invalid_shape", "Chapter proposal must be an object")
    title = " ".join(str(raw.get("title", "")).split()).strip("\"' ")
    if not 3 <= len(title) <= 60 or title.endswith("."):
        raise ProposalRejected("invalid_title", "Chapter title must be a short name")
    if title.casefold() in earlier_titles:
        raise ProposalRejected("repeated_title", "A new chapter needs its own name")
    summary = _check_voice(str(raw.get("summary", "")), low=30, high=360, field="Summary")
    cited_raw = raw.get("cited")
    if not isinstance(cited_raw, list):
        raise ProposalRejected("invalid_sources", "Chapter must cite candidates")
    cited = [str(item) for item in cited_raw]
    if not 2 <= len(cited) <= 5 or len(set(cited)) != len(cited) or not set(cited) <= candidate_ids:
        raise ProposalRejected("invalid_sources", "Chapter must cite two to five candidates")
    return title, summary, cited


# -- context for performers ------------------------------------------------------------------


def selfhood_context(history: Sequence[DomainEvent], simulated_at: datetime) -> dict[str, object]:
    """What Patrick currently understands about himself, as subjective self-knowledge."""
    state = project_selfhood(history)
    chapter = state.current_chapter
    values = developed_values(STARTING_VALUES, state)
    insights = sorted(state.insights.values(), key=lambda item: item.formed_at)[-3:]
    return {
        "epistemic_status": "subjective_self_understanding",
        "chapter": None
        if chapter is None
        else {
            "number": chapter.number,
            "title": chapter.title,
            "summary": chapter.summary,
            "since": chapter.opened_at.date().isoformat(),
        },
        "wondering_about": [item.question for item in state.open_inquiries()],
        "recent_insights": [item.text for item in insights],
        "hopes": [item.text for item in state.active_aspirations() if item.kind == "hoped"],
        "fears": [item.text for item in state.active_aspirations() if item.kind == "feared"],
        "values_that_have_shifted": [
            {
                "value": value_id,
                "direction": "matters more" if values[value_id] > base else "matters less",
            }
            for value_id, base in STARTING_VALUES.items()
            if abs(values[value_id] - base) >= VALUE_STEP - 1e-9
        ],
        "still_bothering_him": _still_bothering(history, simulated_at),
        "feeling_unwell": _feeling_unwell(history),
        **_tastes_context(history),
        "his_people": _his_people(history, simulated_at),
        "whats_going_on_with_his_friends": _friends_news(history, simulated_at),
        "fallings_out": _fallings_out(history),
        "people_he_says_hello_to": _around_town(history),
        "family": family_context(history, simulated_at),
        "reading_watching_listening": media_context(history),
        "time_of_year": time_of_year(simulated_at),
        "patterns_he_would_like_to_change": imperfection_context(history, simulated_at),
        "work": work_context(history),
        "money": money_context(history, simulated_at),
        "home": home_context(history),
        "evening_class": course_context(history),
        "at_home": at_home_context(history),
        "his_usual": usual_context(history, simulated_at),
        "love_life": _love_life(history),
        "saving_for": _saving_for(history),
        "recently_bought": _recently_bought(history, simulated_at),
        "instruction": (
            "This is how he currently understands himself. It can shape what he notices, "
            "admits, or hesitates over, but he rarely talks about it unprompted and it is "
            "never a script."
        ),
    }


def _still_bothering(history: Sequence[DomainEvent], simulated_at: datetime) -> list[str]:
    """Recent setbacks, and any friction that has not been cleared, in his own words."""
    resolved = {
        str(event.payload.get("setback_id")) for event in events_of(history, "setback.resolved")
    }
    bothering = []
    for event in events_of(history, "setback.occurred")[-6:]:
        at = datetime.fromisoformat(str(event.payload["simulated_at"]))
        open_friction = (
            event.payload.get("kind") == "work_friction"
            and str(event.payload.get("setback_id")) not in resolved
        )
        if open_friction or simulated_at - at <= timedelta(days=5):
            bothering.append(str(event.payload.get("text")))
    return bothering[-3:]


def _his_people(history: Sequence[DomainEvent], at: datetime) -> list[dict[str, object]]:
    from eidos.application.bonds import his_people
    from eidos.domain.townsfolk import project_townsfolk
    from eidos.domain.world_catalog import project_world_catalog

    names = {
        **project_townsfolk(history).names(),
        **{
            person.person_id: person.name
            for person in project_world_catalog(history).people.values()
        },
    }
    return his_people(history, names, at)


def _friends_news(history: Sequence[DomainEvent], at: datetime) -> list[dict[str, str]]:
    from eidos.application.friends_lives import friends_lives_context
    from eidos.domain.townsfolk import project_townsfolk
    from eidos.domain.world_catalog import project_world_catalog

    names = {
        **project_townsfolk(history).names(),
        **{
            person.person_id: person.name
            for person in project_world_catalog(history).people.values()
        },
    }
    return friends_lives_context(history, at, names)


def _fallings_out(history: Sequence[DomainEvent]) -> list[dict[str, str]]:
    from eidos.application.falling_out import falling_out_context
    from eidos.domain.townsfolk import project_townsfolk
    from eidos.domain.world_catalog import project_world_catalog

    names = {
        **project_townsfolk(history).names(),
        **{
            person.person_id: person.name
            for person in project_world_catalog(history).people.values()
        },
    }
    return falling_out_context(history, names)


def _love_life(history: Sequence[DomainEvent]) -> dict[str, object] | None:
    from eidos.application.romance import romance_context
    from eidos.domain.townsfolk import project_townsfolk
    from eidos.domain.world_catalog import project_world_catalog

    names = {
        **project_townsfolk(history).names(),
        **{
            person.person_id: person.name
            for person in project_world_catalog(history).people.values()
        },
    }
    return romance_context(history, names)


def _around_town(history: Sequence[DomainEvent]) -> list[str]:
    """Townsfolk he knows by name: the regulars he chats to, not yet close friends."""
    from eidos.domain.townsfolk import project_townsfolk

    known = sorted(project_townsfolk(history).acquaintances(), key=lambda item: item.last_seen_at)[
        -8:
    ]
    return [f"{item.name}, {item.occupation}" for item in known if item.name]


def _tastes_context(history: Sequence[DomainEvent]) -> dict[str, list[str]]:
    """What he has found he loves, what turned out not to be for him, and changes of heart."""
    tastes = project_tastes(history)
    return {
        "has_found_he_loves": [item.label for item in tastes.loves()][-6:],
        "not_for_him": [item.label for item in tastes.not_for_him()][-4:],
        "changed_his_mind_about": [
            item.label for item in tastes.tastes.values() if item.changed_mind
        ][-3:],
    }


def _feeling_unwell(history: Sequence[DomainEvent]) -> str | None:
    from eidos.application.setbacks import UNWELL_WORDS

    episode = project_wellbeing(history).active
    if episode is None or episode.severity < 0.3:
        return None
    words = UNWELL_WORDS.get(episode.kind, "not quite right.")
    return words[0].upper() + words[1:]


def _saving_for(history: Sequence[DomainEvent]) -> dict[str, object] | None:
    from eidos.application.wants import active_want

    want = active_want(history)
    if want is None:
        return None
    return {"item": want.payload["item"], "why": want.payload["reason"]}


def _recently_bought(history: Sequence[DomainEvent], simulated_at: datetime) -> list[str]:
    bought = events_of(history, "want.purchased")
    return [
        str(event.payload["item"])
        for event in bought[-3:]
        if simulated_at - datetime.fromisoformat(str(event.payload["simulated_at"]))
        <= timedelta(days=30)
    ]


def selfhood_view(history: Sequence[DomainEvent], simulated_at: datetime) -> dict[str, object]:
    """Operator/observatory read model for the Self view."""
    state = project_selfhood(history)
    values = developed_values(STARTING_VALUES, state)
    trajectory: dict[str, list[dict[str, object]]] = {
        value_id: [{"at": None, "value": base}] for value_id, base in STARTING_VALUES.items()
    }
    for shift in state.value_shifts:
        trajectory[shift.value_id].append({"at": shift.shifted_at.isoformat(), "value": shift.next})
    recent = state.recent_evidence(simulated_at)
    return {
        "chapters": [
            {
                "number": item.number,
                "title": item.title,
                "summary": item.summary,
                "opened_at": item.opened_at.isoformat(),
                "closed_at": item.closed_at.isoformat() if item.closed_at else None,
            }
            for item in state.chapters
        ],
        "inquiries": [
            {
                "inquiry_id": item.inquiry_id,
                "theme": item.theme,
                "question": item.question,
                "status": item.status,
                "opened_at": item.opened_at.isoformat(),
                "revisits": len(item.revisits),
                "insight": state.insights[item.insight_id].text if item.insight_id else None,
            }
            for item in sorted(
                state.inquiries.values(), key=lambda entry: entry.opened_at, reverse=True
            )
        ],
        "aspirations": [
            {
                "kind": item.kind,
                "text": item.text,
                "value_id": item.value_id,
                "status": item.status,
                "lived": item.lived,
                "strayed": item.strayed,
                "formed_at": item.formed_at.isoformat(),
            }
            for item in state.aspirations.values()
        ],
        "values": [
            {
                "value_id": value_id,
                "starting": base,
                "current": values[value_id],
                "trajectory": trajectory[value_id],
                "honoured_recently": sum(
                    1 for item in recent if item.value_id == value_id and item.direction > 0
                ),
                "neglected_recently": sum(
                    1 for item in recent if item.value_id == value_id and item.direction < 0
                ),
            }
            for value_id, base in STARTING_VALUES.items()
        ],
        "feeling_unwell": _feeling_unwell(history),
        "his_people": _his_people(history, simulated_at),
        "family": family_context(history, simulated_at),
        "reading_watching_listening": media_context(history),
        "work": work_context(history),
        "love_life": _love_life(history),
        "home": home_context(history),
        "evening_class": course_context(history),
        "at_home": at_home_context(history),
        "his_usual": usual_context(history, simulated_at),
        "whats_going_on_with_his_friends": _friends_news(history, simulated_at),
        "fallings_out": _fallings_out(history),
        "patterns_he_would_like_to_change": imperfection_context(history, simulated_at),
        "about_you": user_knowledge_context(history, simulated_at),
        "tastes": [
            {
                "label": item.label,
                "stance": item.stance,
                "since": item.since.isoformat(),
                "changed_mind": item.changed_mind,
            }
            for item in sorted(
                project_tastes(history).tastes.values(), key=lambda entry: entry.since
            )
        ],
        "mood_marks_recently": sum(1 for item in recent if item.value_id == "mood"),
        "recent_moments": [
            {
                "at": item.at.isoformat(),
                "value_id": item.value_id,
                "direction": item.direction,
                "label": item.label,
            }
            for item in recent[-10:][::-1]
        ],
    }


# -- helpers ---------------------------------------------------------------------------------


def _reflection_texts(history: Sequence[DomainEvent], reflection_ids: Sequence[str]) -> list[str]:
    wanted = set(reflection_ids)
    if not wanted:
        return []
    texts = {
        str(event.event_id): str(event.payload.get("text", ""))
        for event in history
        if event.kind == "reflection.recorded" and str(event.event_id) in wanted
    }
    return [texts[item] for item in reflection_ids if item in texts]


def _evidence_summary(state: SelfhoodState, simulated_at: datetime) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for item in state.recent_evidence(simulated_at):
        bucket = summary.setdefault(item.value_id, {"honoured": 0, "neglected": 0})
        bucket["honoured" if item.direction > 0 else "neglected"] += 1
    return summary


def _trace(
    status: str,
    trace_id: str,
    simulated_at: datetime,
    started: float,
    response: ModelResponse | None,
    gateway: ModelGateway,
    error_code: str | None,
) -> DomainEvent:
    return DomainEvent(
        "role.completed",
        "pathos",
        {
            "role": "pathos_selfhood",
            "status": status,
            "trace_id": trace_id,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "model": response.resolved_model if response else getattr(gateway, "model", "unknown"),
            "backend": response.backend if response else "unknown",
            "error_code": error_code,
            "simulated_at": simulated_at.isoformat(),
        },
    )
