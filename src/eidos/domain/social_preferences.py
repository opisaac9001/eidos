"""Evidence-bound memories of another person's stated preferences."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class RememberedPreference:
    preference_id: str
    person_id: str
    topic: str
    stance: str
    confidence: float
    status: str
    revision: int
    evidence_count: int
    last_evidence_id: str
    last_evidence_at: str


@dataclass(frozen=True, slots=True)
class PreferenceEvidence:
    person_id: str
    topic: str
    stance: str
    confidence: float


def preference_evidence(event: DomainEvent) -> PreferenceEvidence | None:
    if event.kind == "conversation.message" and event.payload.get("speaker") == "you":
        text = event.payload.get("text")
        if not isinstance(text, str):
            return None
        match = re.fullmatch(
            r"\s*i\s+(?:(?:really|especially)\s+)?"
            r"(don't like|do not like|dislike|hate|avoid|love|like|enjoy|prefer)\s+"
            r"(.{2,80}?)\s*[.!]?\s*",
            text,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None
        verb, raw_topic = match.groups()
        topic = _topic(raw_topic)
        if topic is None:
            return None
        stance = (
            "avoids"
            if verb.lower() in {"don't like", "do not like", "dislike", "hate", "avoid"}
            else "likes"
        )
        return PreferenceEvidence("user", topic, stance, 0.98)
    if event.kind != "perception.recorded" or event.payload.get("owner") != "pathos":
        return None
    speaker = event.payload.get("speaker_id")
    subject = event.payload.get("claim_subject_id")
    predicate = event.payload.get("claim_predicate")
    value = event.payload.get("claim_value")
    confidence = event.payload.get("claim_confidence")
    if (
        not isinstance(speaker, str)
        or subject != speaker
        or predicate not in {"likes", "prefers", "avoids", "dislikes"}
        or not isinstance(value, str)
        or isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        return None
    topic = _topic(value)
    if topic is None:
        return None
    stance = "avoids" if predicate in {"avoids", "dislikes"} else "likes"
    return PreferenceEvidence(speaker, topic, stance, max(0.1, float(confidence)))


def project_social_preferences(
    history: Sequence[DomainEvent],
) -> dict[str, RememberedPreference]:
    preferences: dict[str, RememberedPreference] = {}
    seen: dict[str, DomainEvent] = {}
    for event in history:
        if event.kind in {"social.preference_remembered", "social.preference_revised"}:
            preference_id = _required(event, "preference_id")
            person_id = _required(event, "person_id")
            topic = _required(event, "topic")
            stance = _required(event, "stance")
            evidence_id = _required(event, "evidence_event_id")
            evidence_event = seen.get(evidence_id)
            evidence = preference_evidence(evidence_event) if evidence_event is not None else None
            confidence = _confidence(event)
            evidence_time = _event_time(evidence_event) if evidence_event is not None else None
            if (
                evidence_event is None
                or evidence is None
                or evidence.person_id != person_id
                or evidence.topic != topic
                or evidence.stance != stance
                or confidence != evidence.confidence
                or evidence_time is None
                or event.causation_id != evidence_event.event_id
            ):
                raise ValueError("Remembered preference must match accessible direct evidence")
            current = preferences.get(preference_id)
            if event.kind == "social.preference_remembered":
                if current is not None or any(
                    item.person_id == person_id and item.topic == topic
                    for item in preferences.values()
                ):
                    raise ValueError("Preference identity already exists")
                preferences[preference_id] = RememberedPreference(
                    preference_id,
                    person_id,
                    topic,
                    stance,
                    confidence,
                    "held",
                    1,
                    1,
                    evidence_id,
                    evidence_time.isoformat(),
                )
            else:
                if (
                    current is None
                    or (current.person_id, current.topic) != (person_id, topic)
                    or event.payload.get("prior_revision") != current.revision
                ):
                    raise ValueError("Preference revision is stale or unknown")
                if evidence_id == current.last_evidence_id:
                    raise ValueError("Preference evidence cannot be reused")
                preferences[preference_id] = replace(
                    current,
                    stance=stance,
                    confidence=confidence,
                    status="held",
                    revision=current.revision + 1,
                    evidence_count=current.evidence_count + 1,
                    last_evidence_id=evidence_id,
                    last_evidence_at=evidence_time.isoformat(),
                )
        elif event.kind == "social.preference_faded":
            preference_id = _required(event, "preference_id")
            current = preferences.get(preference_id)
            if (
                current is None
                or current.status != "held"
                or event.payload.get("prior_revision") != current.revision
                or event.causation_id is None
                or str(event.causation_id) != current.last_evidence_id
                or _event_time(event) - datetime.fromisoformat(current.last_evidence_at)
                < timedelta(days=180)
            ):
                raise ValueError("Only an old, held preference can fade")
            preferences[preference_id] = replace(
                current,
                confidence=min(current.confidence, 0.25),
                status="uncertain",
                revision=current.revision + 1,
            )
        seen[str(event.event_id)] = event
    return preferences


def preference_id(person_id: str, topic: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "-", topic).strip("-")[:48]
    digest = sha256(topic.encode()).hexdigest()[:8]
    return f"social-preference-{person_id}-{safe}-{digest}"


def _topic(value: str) -> str | None:
    topic = " ".join(value.lower().strip().split()).strip(" .!?\"'")
    if (
        not 2 <= len(topic) <= 80
        or any(mark in topic for mark in ("\n", ";"))
        or re.search(r"\bbut\b", topic)
    ):
        return None
    return topic


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _confidence(event: DomainEvent) -> float:
    value = event.payload.get("confidence")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError("confidence must be between zero and one")
    return float(value)


def _event_time(event: DomainEvent | None) -> datetime:
    if event is None:
        raise ValueError("Preference evidence is missing")
    value = _required(event, "simulated_at")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Preference evidence time must be timezone-aware")
    return parsed
