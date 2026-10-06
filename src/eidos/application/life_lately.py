"""While he sleeps, his sense of his own life is quietly brought up to date.

People wake with an updated sense of what's going on in their lives without having
thought it through: who's been around, what's weighing on them, what's coming up. In the
early hours, while he's asleep and the bigger model has nothing else to do (Letta's
"sleep-time" idea), the day's memories, what's on his mind and the last version are
rewritten into a short first-person "my life lately". His voice draws on it, so he talks
like someone who knows his own life rather than someone recalling scattered moments.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Sequence

from eidos.application.friends_lives import friends_lives_context
from eidos.application.inner_life import active_concerns
from eidos.application.open_loops import loops_view
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest

KIND = "self.consolidated"
HOUR = 5
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {"text": {"type": "string", "maxLength": 1400}},
}


def life_lately(history: Sequence[DomainEvent]) -> str | None:
    found = events_of(history, KIND)
    return str(found[-1].payload["text"]) if found else None


def _when(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


async def life_lately_events(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    *,
    asleep: bool,
    names: dict[str, str],
) -> list[DomainEvent]:
    """Once a night, in the small hours, rewrite his sense of his life lately."""
    if not asleep or at.hour != HOUR:
        return []
    last = events_of(history, KIND)[-1:]
    if last and (when := _when(last[0])) is not None and at - when < timedelta(hours=20):
        return []
    since = at - timedelta(hours=26)
    day: list[tuple[float, str]] = []
    for event in reversed(events_of(history, "memory.recorded")[-400:]):
        when = _when(event)
        if when is None or when < since:
            break
        p = event.payload
        if p.get("owner", "pathos") != "pathos" or p.get("category") == "dream":
            continue
        day.append((float(p.get("importance", 0.3) or 0.3), str(p.get("text", ""))))
    today = [text for _, text in sorted(day, key=lambda item: -item[0])[:10]]
    context = {
        "task": "life lately",
        "time": at.isoformat(),
        "last_version": life_lately(history) or "",
        "the_day_just_gone": today,
        "weighing_on_me": [str(c.payload.get("text")) for c in active_concerns(history)][-4:],
        "meaning_to": [str(loop["text"]) for loop in loops_view(history, at)][:4],
        "friends_news": [
            f"{item['who']}: {item['what']}" for item in friends_lives_context(history, at, names)
        ][:5],
        "permission": (
            "Bring Patrick's own sense of his life up to date, in his voice, first person: a "
            "short paragraph (60 to 140 words) on what's going on in his life lately, who's "
            "been around, what's weighing on him, what he's looking forward to. Keep what "
            "still holds from last_version, change what the day changed, drop what's faded. "
            "Use only what's given; invent nothing. Return only the paragraph."
        ),
    }
    request = ModelRequest(
        capability="pathos_life_summary",
        task_version="1",
        temperature=0.5,
        max_output_tokens=320,
        output_schema=_SCHEMA,
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    try:
        response = await gateway.generate(request)
        raw = json.loads(response.content)
        text = " ".join(str(raw.get("text", "")).split()) if isinstance(raw, dict) else ""
    except (OSError, TimeoutError, TypeError, ValueError, AttributeError):
        return []
    words = len(text.split())
    if (
        not 25 <= words <= 220
        or not re.search(r"\b(I|I'm|I've|my|me)\b", text)
        or re.search(r"\b(as an ai|language model|patrick is)\b", text, re.IGNORECASE)
    ):
        return []
    return [
        DomainEvent(
            KIND,
            "pathos",
            {
                "text": text,
                "model": getattr(response, "resolved_model", "") or "",
                "simulated_at": at.isoformat(),
            },
        )
    ]
