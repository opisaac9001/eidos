"""Synthetic voice checks; never reads or advances the live world."""
import asyncio
import json
from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.application.cognition import perform

CASES = [
    ("greeting", "hey hows it going", []),
    ("vulnerable", "honestly its been a pretty rough day", []),
    ("no_advice", "i dont want advice just wanted to say that", [
        {"speaker": "you", "text": "Work was awful today."},
        {"speaker": "pathos", "text": "Oh, what happened?"}]),
    ("story", "what have you been up to today", []),
    ("disagree", "tea is awful honestly", []),
    ("continuity", "did it work eventually", [
        {"speaker": "pathos", "text": "The kettle kept switching itself off."}]),
]

async def main():
    gateway = HTTPModelGateway("http://127.0.0.1:11434/v1", "qwen2.5:14b")
    rows = []
    for label, message, dialogue in CASES:
        context = {
            "message": message, "recent_dialogue": dialogue,
            "time": "2026-09-07T15:00:00+00:00", "location": "Kitchen",
            "mood": "Content", "identity": {"name": "Pathos"},
            "memories": ["The kettle switched itself off twice. It boiled on the third try.",
                         "I made tea and read for a while."],
            "remembered_preferences": [{"topic": "tea", "stance": "likes"}],
        }
        events = []
        output = await perform(gateway, "pathos", context, context["time"], events)
        row = {"case": label, "message": message, "text": output,
               "traces": [dict(e.payload) for e in events if e.kind == "role.completed"]}
        rows.append(row)
        print(json.dumps(row), flush=True)
    raise SystemExit(0 if all(r["text"] for r in rows) else 1)

if __name__ == "__main__":
    asyncio.run(main())
