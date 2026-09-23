"""Short-prompt control using the same fixtures, model and JSON response format."""

import argparse
import json
from pathlib import Path
from time import perf_counter
from urllib.request import Request, urlopen

SYSTEM = (
    "Play Patrick Shaw in a fictional town. Pathos is his university nickname. "
    "Born October 27 1998; grew up in Wye; studied philosophy and computing in Bristol. "
    "On the supplied January 7 2026 date he is 27. Speak casually in understated British "
    "English, as a friend, not an assistant. Be brief, warm or dry when appropriate, "
    "not relentlessly jokey. Answer the user's actual message; don't recap unrelated "
    "memories. If someone has a bad day, attend to them rather than your own day. "
    "Context describes YOUR state, not theirs. User questions are not proof of past "
    "events. If a call, possession, sale or intention isn't supplied, don't invent "
    "its existence or nonexistence. Say you're unsure naturally. Supplied mistaken "
    "memories may be sincerely believed; absent history is unknown. Keep supplied "
    "preferences when someone disagrees, and respect time pressure. Return only a "
    "JSON object with a text string: one to three short sentences, no markdown."
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("output")
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(destination)
    source = json.loads(Path("data/evaluations/patrick-blend-v2-20260908.json").read_text())
    selected = {"birthday", "rough_day", "unknown_contact", "old_car", "limited_time", "disagree"}
    rows = []
    for case in source["rows"]:
        if case["case"] not in selected:
            continue
        payload = {
            "model": args.model,
            "reasoning_effort": "none",
            "temperature": 0.55,
            "max_tokens": 160,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(case["context"])},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "eidos_proposal",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                        "additionalProperties": False,
                    },
                },
            },
        }
        started = perf_counter()
        query = Request(
            "http://127.0.0.1:11439/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(query, timeout=50) as response:
            result = json.load(response)
        message = result["choices"][0]["message"]
        row = {
            "case": case["case"],
            "context": case["context"],
            "content": message.get("content"),
            "finish_reason": result["choices"][0].get("finish_reason"),
            "seconds": round(perf_counter() - started, 2),
            "reasoning_chars": {
                k: len(str(message.get(k) or ""))
                for k in ("reasoning", "reasoning_content", "thinking")
            },
            "usage": result.get("usage"),
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    with destination.open("x") as output:
        json.dump(
            {
                "model": args.model,
                "system": SYSTEM,
                "thinking": False,
                "synthetic": True,
                "rows": rows,
            },
            output,
            indent=2,
        )


if __name__ == "__main__":
    main()
