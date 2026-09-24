"""Deterministic concern and dream-effect projections around generated fiction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of, kind_index
from eidos.domain.state import PathosState


@dataclass(frozen=True, slots=True)
class DreamInspiration:
    source_dream_id: str
    motif: str
    suggestion: str
    expires_at: str


def active_dream_inspirations(
    events: Sequence[DomainEvent], simulated_at: datetime
) -> list[DreamInspiration]:
    """Project unexpired, explicitly non-authoritative ideas from recalled dreams."""

    if simulated_at.utcoffset() is None:
        raise ValueError("Dream inspiration projection requires an aware time")
    inspirations: dict[str, DreamInspiration] = {}
    dismissed: set[str] = set()
    for event in events_of(events, "dream.inspiration_considered", "dream.inspiration_dismissed"):
        if event.kind == "dream.inspiration_considered":
            dream_id = str(event.payload["source_dream_id"])
            if dream_id in inspirations:
                raise ValueError("A dream can create at most one waking inspiration")
            inspirations[dream_id] = DreamInspiration(
                dream_id,
                str(event.payload["motif"]),
                str(event.payload["suggestion"]),
                str(event.payload["expires_at"]),
            )
        elif event.kind == "dream.inspiration_dismissed":
            dismissed.add(str(event.payload["source_dream_id"]))
    return [
        item
        for dream_id, item in inspirations.items()
        if dream_id not in dismissed and datetime.fromisoformat(item.expires_at) > simulated_at
    ]


def active_concerns(events: Sequence[DomainEvent]) -> list[DomainEvent]:
    concerns: dict[str, DomainEvent] = {}
    for event in events_of(events, "concern.opened", "concern.resolved", "concern.receded"):
        if event.aggregate_id != "pathos":
            continue
        if event.kind == "concern.opened":
            concerns[str(event.payload["concern_id"])] = event
        elif event.kind in {"concern.resolved", "concern.receded"}:
            concerns.pop(str(event.payload["concern_id"]), None)
    return list(concerns.values())


def dream_seed_sources(
    recalled_memories: Sequence[DomainEvent], concerns: Sequence[DomainEvent], limit: int = 3
) -> tuple[DomainEvent, ...]:
    """Choose bounded owned waking evidence; dream memories cannot seed themselves."""
    if not 1 <= limit <= 5:
        raise ValueError("Dream seed limit must be between one and five")
    eligible = [
        event
        for event in concerns
        if event.kind == "concern.opened" and isinstance(event.payload.get("concern_id"), str)
    ]
    eligible.extend(
        event
        for event in recalled_memories
        if event.kind == "memory.recorded"
        and event.payload.get("owner", "pathos") == "pathos"
        and event.payload.get("category") != "dream"
    )
    selected = []
    seen = set()
    for event in eligible:
        identity = str(event.event_id)
        if identity in seen:
            continue
        selected.append(event)
        seen.add(identity)
        if len(selected) == limit:
            break
    return tuple(selected)


def record_dream_events(
    text: str,
    seeds: Sequence[DomainEvent],
    simulated_at: str,
    source: str,
    *,
    recent_motifs: Sequence[str] = (),
) -> list[DomainEvent]:
    """Record dream fiction plus one auditable link for every accepted seed."""
    if not text.strip():
        raise ValueError("Dream text must not be empty")
    accepted = dream_seed_sources(
        [seed for seed in seeds if seed.kind == "memory.recorded"],
        [seed for seed in seeds if seed.kind == "concern.opened"],
        limit=min(5, max(1, len(seeds))),
    )
    motif = _motif(accepted, text, recent_motifs)
    dream = DomainEvent(
        "dream.recorded",
        "pathos",
        {
            "text": text.strip(),
            "simulated_at": simulated_at,
            "source": source,
            "role": "oneiros",
            "seed_count": len(accepted),
            "primary_seed_id": str(accepted[0].event_id) if accepted else None,
            "motif": motif,
            "fiction": True,
        },
        correlation_id=f"dream-{simulated_at}",
    )
    events = [dream]
    for position, seed in enumerate(accepted, 1):
        events.append(
            DomainEvent(
                "dream.seed_linked",
                "pathos",
                {
                    "dream_id": str(dream.event_id),
                    "seed_event_id": str(seed.event_id),
                    "seed_kind": "concern" if seed.kind == "concern.opened" else "memory",
                    "position": position,
                    "motif": motif,
                    "simulated_at": simulated_at,
                },
                causation_id=seed.event_id,
                correlation_id=dream.correlation_id,
            )
        )
    return events


def _motif(seeds: Sequence[DomainEvent], dream_text: str, recent_motifs: Sequence[str]) -> str:
    """Name the dream's imagery without letting familiar seeds monopolize it."""
    seed_text = " ".join(str(seed.payload.get("text", "")).lower() for seed in seeds)
    rendered = dream_text.lower()
    catalog = (
        ("light", ("lamp", "light", "moon", "glow", "shadow")),
        ("mending", ("repair", "broken", "workshop", "mend", "stitch")),
        ("growth", ("park", "tree", "garden", "root", "leaf")),
        ("companionship", ("mara", "ellis", "rowan", "cafe", "together", "chair")),
        ("unfinished_time", ("clock", "afternoon", "time", "late", "season")),
        ("weather", ("rain", "water", "storm", "river", "flood")),
        ("thresholds", ("door", "doorway", "window", "threshold", "hallway")),
        ("journey", ("railway", "platform", "road", "map", "street", "destination")),
        ("memory", ("remember", "forget", "forgot", "name", "written")),
        ("silence", ("whisper", "quiet", "sound", "wordless")),
        ("dislocation", ("float", "drift", "ceiling", "floor", "above")),
    )
    recent = set(recent_motifs[-3:])
    scored = []
    for position, (motif, cues) in enumerate(catalog):
        score = 2 * sum(cue in rendered for cue in cues) + sum(cue in seed_text for cue in cues)
        scored.append((score, motif not in recent, -position, motif))
    score, _, _, motif = max(scored)
    return motif if score else "unfinished_time"


def waking_dream_events(
    events: list[DomainEvent],
    state: PathosState,
    simulated_at: str,
    *,
    authored_scenario: bool = False,
) -> list[DomainEvent]:
    if not authored_scenario and not state.awake:
        return []
    index = kind_index(events)
    applied = {event.payload["source_dream_id"] for event in index.select("dream.effect_applied")}
    pending_effects = [
        event
        for event in index.select("dream.effect_scheduled")
        if event.payload["source_dream_id"] not in applied
    ]
    if not pending_effects:
        return []
    effect = pending_effects[-1]
    dream_id = effect.payload["source_dream_id"]
    dream = next(
        event for event in index.select("dream.recorded") if str(event.event_id) == dream_id
    )
    delta = max(-0.12, min(0.12, float(effect.payload["valence_delta"])))
    waking_at = datetime.fromisoformat(simulated_at)
    motif = str(dream.payload.get("motif", "unfinished_time"))
    recalled = DomainEvent(
        "dream.recalled",
        "pathos",
        {
            "text": "A dream lingered after waking.",
            "simulated_at": simulated_at,
            "source_dream_id": dream_id,
        },
        causation_id=dream.event_id,
        correlation_id=dream.correlation_id,
    )
    suggestion = {
        "light": "Consider whether something unfinished needs patient attention.",
        "mending": "Consider making time for careful repair or practice.",
        "growth": "Consider spending attentive time outdoors.",
        "companionship": "Consider whether a quiet social follow-up would feel welcome.",
        "weather": "Consider making room for whatever mood the day brings.",
        "thresholds": "Consider one small change of scene without treating it as a demand.",
        "journey": "Consider an unhurried walk or a different familiar route.",
        "memory": "Consider writing down the fragment before it fades.",
        "silence": "Consider leaving a little quiet around the day.",
        "dislocation": "Consider choosing something steady and familiar today.",
    }.get(motif, "Consider leaving a little unscheduled room today.")
    inspiration = DomainEvent(
        "dream.inspiration_considered",
        "pathos",
        {
            "source_dream_id": dream_id,
            "motif": motif,
            "suggestion": suggestion,
            "expires_at": (waking_at + timedelta(hours=12)).isoformat(),
            "fiction_source": True,
            "action_authority": False,
            "simulated_at": simulated_at,
        },
        causation_id=recalled.event_id,
        correlation_id=dream.correlation_id,
    )
    output = [
        recalled,
        DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": f"I remember dreaming: {dream.payload['text']}",
                "simulated_at": simulated_at,
                "source": "dream-recall",
                "source_event_id": dream_id,
                "category": "dream",
                "location_id": state.location_id,
                "owner": "pathos",
                "importance": 0.6,
                "confidence": 1.0,
            },
        ),
        DomainEvent(
            "affect.changed",
            "pathos",
            {
                "valence": max(-1.0, min(1.0, state.valence + delta)),
                "simulated_at": simulated_at,
                "source_dream_id": dream_id,
                "reason": "bounded waking dream residue",
            },
        ),
        DomainEvent(
            "dream.effect_applied",
            "pathos",
            {
                "source_dream_id": dream_id,
                "simulated_at": simulated_at,
                "valence_delta": delta,
            },
        ),
        inspiration,
    ]
    if authored_scenario:
        return output

    # Replay-stable simulation choices, not claims about human recall rates.
    def sample(label: str) -> float:
        return int(sha256(f"{dream_id}:{label}".encode()).hexdigest()[:12], 16) / 16**12

    recall_fragment = sample("recall") < 0.25 + abs(delta)
    retain_memory = recall_fragment and sample("retain") < 0.25
    inspires = recall_fragment and sample("inspire") < 0.2
    selection = DomainEvent(
        "dream.residue_selected",
        "pathos",
        {
            "source_dream_id": dream_id,
            "fragment_recalled": recall_fragment,
            "memory_retained": retain_memory,
            "inspiration_retained": inspires,
            "simulated_at": simulated_at,
            "action_authority": False,
        },
        causation_id=dream.event_id,
        correlation_id=dream.correlation_id,
    )
    result = [selection]
    for event in output:
        if event.kind == "dream.recalled" and not recall_fragment:
            continue
        if event.kind == "memory.recorded":
            if not retain_memory:
                continue
            fragment = str(dream.payload["text"])[:160].rsplit(" ", 1)[0]
            event = DomainEvent(
                event.kind,
                "pathos",
                {
                    **event.payload,
                    "text": f"A fragment of a dream: {fragment}…",
                    "importance": 0.25,
                    "confidence": 0.45,
                    "fiction": True,
                    "factual": False,
                },
                causation_id=recalled.event_id,
                correlation_id=dream.correlation_id,
            )
        if event.kind == "dream.inspiration_considered":
            if not inspires:
                continue
            event = DomainEvent(
                event.kind,
                "pathos",
                {
                    **event.payload,
                    "expires_at": (waking_at + timedelta(minutes=45)).isoformat(),
                    "fleeting": True,
                },
                causation_id=recalled.event_id,
                correlation_id=dream.correlation_id,
            )
        result.append(event)
    if not recall_fragment:
        result.append(
            DomainEvent(
                "dream.forgotten",
                "pathos",
                {
                    "source_dream_id": dream_id,
                    "simulated_at": simulated_at,
                    "reason": "No dream fragment remained on waking; a feeling may linger.",
                },
                causation_id=selection.event_id,
                correlation_id=dream.correlation_id,
            )
        )
    return result
