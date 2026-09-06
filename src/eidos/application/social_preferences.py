"""Remember explicit preferences without turning guesses into facts."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence
from uuid import UUID

from eidos.domain.events import DomainEvent
from eidos.domain.social_preferences import (
    preference_evidence,
    preference_id,
    project_social_preferences,
)


def social_preference_events(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[DomainEvent]:
    if simulated_at.utcoffset() is None:
        raise ValueError("Preference review must be timezone-aware")
    output: list[DomainEvent] = []
    state = project_social_preferences(history)
    considered = {
        str(event.payload["evidence_event_id"])
        for event in history
        if event.kind in {"social.preference_remembered", "social.preference_revised"}
    }
    for source in history:
        source_id = str(source.event_id)
        evidence = preference_evidence(source)
        if evidence is None or source_id in considered:
            continue
        try:
            source_time = _event_time(source)
        except (TypeError, ValueError):
            continue
        item_id = preference_id(evidence.person_id, evidence.topic)
        current = state.get(item_id)
        payload: dict[str, object] = {
            "preference_id": item_id,
            "person_id": evidence.person_id,
            "topic": evidence.topic,
            "stance": evidence.stance,
            "confidence": evidence.confidence,
            "evidence_event_id": source_id,
            "evidence_at": source_time.isoformat(),
            "simulated_at": simulated_at.isoformat(),
            "owner": "pathos",
            "visibility": "private",
        }
        kind = "social.preference_remembered"
        if current is not None:
            kind = "social.preference_revised"
            payload["prior_revision"] = current.revision
        output.append(
            DomainEvent(
                kind,
                "pathos",
                payload,
                causation_id=source.event_id,
                correlation_id=item_id,
            )
        )
        considered.add(source_id)
        state = project_social_preferences([*history, *output])
    if simulated_at.hour != 8:
        return output
    for item in state.values():
        if item.status != "held" or simulated_at - datetime.fromisoformat(
            item.last_evidence_at
        ) < timedelta(days=180):
            continue
        output.append(
            DomainEvent(
                "social.preference_faded",
                "pathos",
                {
                    "preference_id": item.preference_id,
                    "person_id": item.person_id,
                    "topic": item.topic,
                    "prior_revision": item.revision,
                    "simulated_at": simulated_at.isoformat(),
                    "owner": "pathos",
                    "visibility": "private",
                },
                causation_id=UUID(item.last_evidence_id),
                correlation_id=item.preference_id,
            )
        )
    return output


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if not isinstance(value, str):
        raise ValueError("Preference evidence requires simulated time")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Preference evidence time must be timezone-aware")
    return parsed
