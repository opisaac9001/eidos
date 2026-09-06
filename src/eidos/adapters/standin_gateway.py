"""Deterministic development performers. These are templates, not language models."""

import hashlib
import json
from datetime import datetime

from eidos.ports.model_gateway import ModelGateway, ModelRequest, ModelResponse


class StandInGateway(ModelGateway):
    async def generate(self, request: ModelRequest) -> ModelResponse:
        context = json.loads(request.messages[-1].content)
        role = request.capability
        location = context.get("location", "home")
        memories = context.get("memories", [])
        last_memory = memories[-1] if memories else "The day is still beginning."
        key = f"{role}:{context.get('time', '')}:{context.get('message', '')}"
        choice = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
        if role == "pathos":
            message = context.get("message", "").lower()
            if any(word in message for word in ("remember", "yesterday", "today", "day")):
                text = f"I've been thinking back over the day. {last_memory} I'm at {location} now."
            elif any(word in message for word in ("feel", "mood", "how are")):
                text = f"{context.get('mood', 'Quiet')} is probably the word. Being at {location} suits me right now."
            elif any(word in message for word in ("where", "doing")):
                text = f"I'm at {location}. {last_memory} What's happening where you are?"
            else:
                text = (
                    f"It's good to hear from you. I'm at {location}; there's a little room to think here.",
                    f"You caught me thinking about something from earlier. {last_memory} How has your day been?",
                    "I'm glad you stopped by. Tell me a little more; I'd like to hear what's on your mind.",
                )[choice % 3]
        elif role == "murmur":
            text = (
                f"There's something comforting about the familiar rhythm of {location}.",
                f"A fragment from earlier comes back: {last_memory}",
                "I should leave a little space in the day for something unplanned.",
                "Some days are held together by very small things.",
            )[choice % 4]
        elif role == "firmament":
            if context.get("scene_mode") is True:
                text = (
                    "The weathering is part of why the old bench belongs here."
                    if context.get("scene_speaker") == "rowan"
                    else "I can see why replacing it outright would feel like losing something."
                )
            else:
                person = context["person"]
                lines = {
                    "Mara": "Mara asks whether the little lamp at the workshop is working yet.",
                    "Ellis": "Ellis holds up a repaired wooden joint, pleased with how neatly it fits.",
                    "Rowan": "Rowan shares a sketch of the square and points out a detail Pathos missed.",
                }
                text = lines.get(
                    person,
                    f"{person} pauses nearby and mentions a small detail from their day.",
                )
        elif role == "reflection":
            text = f"Looking back, this is the moment that stays with me: {last_memory}"
        elif role == "oneiros":
            text = f"In a dream, {location} opens into a room full of unfinished clocks. Each one keeps a different afternoon."
        elif role == "chronicler":
            text = " ".join(memories[-7:]) or "A quiet day, with no recorded encounters yet."
        elif role == "mnemosyne":
            text = context["experience"]
        elif role == "moira":
            text = ("Clear", "Cloudy", "Light rain", "Breezy")[choice % 4]
        elif role == "moira_event":
            palette = (
                (
                    "wandering_mender",
                    "A bicycle mender sets up a folding repair stand beside the park gate after a touring strap snaps.",
                    "park",
                    "a broken touring strap",
                    "usefulness",
                    "offer help",
                    2,
                    0.28,
                    5,
                ),
                (
                    "misdirected_delivery",
                    "A crate of hand-painted theatre masks is delivered to the cafe while the touring company searches the neighborhood.",
                    "cafe",
                    "a rain-smeared address label",
                    "mistaken identity",
                    "trace the owner",
                    3,
                    0.34,
                    7,
                ),
                (
                    "brief_power_fault",
                    "The workshop lights begin pulsing unevenly as an old junction box warms beneath the stairwell.",
                    "workshop",
                    "a loose aging connection",
                    "fragility",
                    "investigate safely",
                    1,
                    0.43,
                    4,
                ),
                (
                    "injured_migrating_bird",
                    "A tired ringed swift settles beneath the park noticeboard after being driven inland by the wind.",
                    "park",
                    "an unexpected coastal wind",
                    "care",
                    "find local expertise",
                    4,
                    0.31,
                    6,
                ),
                (
                    "forgotten_recording",
                    "A pocket recorder found behind a cafe radiator plays fragments of an unfinished oral-history interview.",
                    "cafe",
                    "spring cleaning dislodged it",
                    "unfinished stories",
                    "identify the voices",
                    2,
                    0.37,
                    12,
                ),
                (
                    "water_main_markings",
                    "Fresh survey marks appear outside the workshop before anyone nearby has heard about planned street work.",
                    "workshop",
                    "a contractor's early survey",
                    "change",
                    "ask what is planned",
                    5,
                    0.26,
                    18,
                ),
                (
                    "seedling_gift",
                    "Someone leaves six carefully labelled tomato seedlings on the park bench with a note inviting strangers to adopt them.",
                    "park",
                    "a gardener raised too many",
                    "generosity",
                    "care for something",
                    3,
                    0.22,
                    8,
                ),
                (
                    "after_hours_rehearsal",
                    "A lone cellist asks to rehearse quietly in the closed cafe because the community hall has flooded.",
                    "cafe",
                    "a burst pipe at the hall",
                    "hospitality",
                    "listen or assist",
                    6,
                    0.35,
                    3,
                ),
            )
            item = palette[choice % len(palette)]
            resource_id = next(
                object_id
                for object_id, resource_location in context["known_resources"].items()
                if resource_location == item[2]
            )
            return ModelResponse(
                content=json.dumps(
                    {
                        "event_type": item[0],
                        "description": item[1],
                        "location_id": item[2],
                        "cause": item[3],
                        "theme": item[4],
                        "opportunity": item[5],
                        "participation": f"A present neighbor may {item[5]} without a guaranteed outcome.",
                        "stakes": "The event may change an ordinary plan or relationship, but need not.",
                        "resource_id": resource_id,
                        "starts_in_hours": item[6],
                        "intensity": item[7],
                        "duration_hours": item[8],
                    }
                ),
                resolved_model="authored-stand-in-v1",
                backend="deterministic",
                finish_reason="stop",
            )
        elif role == "moira_expansion":
            simulated_at = datetime.fromisoformat(context["time"])
            occurrence = ((simulated_at.date() - datetime(2026, 1, 14).date()).days // 7) % 3
            expansion = (
                {
                    "entity_kind": "person",
                    "entity_id": "nina-vale",
                    "name": "Nina Vale",
                    "description": "A traveling bookbinder staying nearby while cataloguing family papers.",
                    "location_id": "cafe",
                    "purpose": "Independent book conservator",
                    "color": "#a68fc2",
                    "label": "Nina",
                    "x": 50,
                    "y": 50,
                    "opens_hour": 8,
                    "closes_hour": 18,
                    "travel_minutes": 10,
                },
                {
                    "entity_kind": "place",
                    "entity_id": "old-glasshouse",
                    "name": "The old glasshouse",
                    "description": "A repaired municipal glasshouse used for seedlings, workshops, and quiet shelter.",
                    "location_id": "park",
                    "purpose": "Shared growing and gathering space",
                    "color": "#91ad91",
                    "label": "Glasshouse",
                    "x": 39,
                    "y": 84,
                    "opens_hour": 8,
                    "closes_hour": 19,
                    "travel_minutes": 8,
                },
                {
                    "entity_kind": "object",
                    "entity_id": "blue-handcart",
                    "name": "The blue handcart",
                    "description": "A sturdy shared cart with one newly replaced wheel and many old paint marks.",
                    "location_id": "workshop",
                    "purpose": "Moving awkward repairs and neighborhood supplies",
                    "color": "#6689a6",
                    "label": "Handcart",
                    "x": 50,
                    "y": 50,
                    "opens_hour": 8,
                    "closes_hour": 18,
                    "travel_minutes": 10,
                },
            )[occurrence]
            return ModelResponse(
                content=json.dumps(expansion),
                resolved_model="authored-stand-in-v1",
                backend="deterministic",
                finish_reason="stop",
            )
        else:
            raise ValueError(f"Unknown stand-in capability: {role}")
        return ModelResponse(
            content=json.dumps({"text": text}),
            resolved_model="authored-stand-in-v1",
            backend="deterministic",
            finish_reason="stop",
        )
