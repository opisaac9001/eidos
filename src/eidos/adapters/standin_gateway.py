"""Deterministic development performers. These are templates, not language models."""

import hashlib
import json

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
            person = context["person"]
            lines = {
                "Mara": "Mara asks whether the little lamp at the workshop is working yet.",
                "Ellis": "Ellis holds up a repaired wooden joint, pleased with how neatly it fits.",
                "Rowan": "Rowan shares a sketch of the square and points out a detail Pathos missed.",
            }
            text = lines[person]
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
        else:
            raise ValueError(f"Unknown stand-in capability: {role}")
        return ModelResponse(
            content=json.dumps({"text": text}),
            resolved_model="authored-stand-in-v1",
            backend="deterministic",
            finish_reason="stop",
        )
