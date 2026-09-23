"""Synthetic capacity check: a dual-P40 model beside the existing 3060 worker.

This is an endpoint/concurrency smoke test, not a world-engine acceptance test.
Requires local 11439 -> temporary dual worker and 11440 -> cognition worker.
Never writes to the application or its history.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from urllib.request import Request, urlopen


def probe(job):
    label, port, model, prompt = job
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "reasoning_effort": "none",
        "max_tokens": 100,
        "temperature": 0.55,
        "stream": False,
    }
    request = Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = perf_counter()
    with urlopen(request, timeout=60) as response:
        result = json.load(response)
    choice = result["choices"][0]
    message = choice["message"]
    return {
        "worker": label,
        "model": model,
        "seconds": round(perf_counter() - started, 2),
        "text": message.get("content"),
        "finish_reason": choice.get("finish_reason"),
        "reasoning_characters": {
            key: len(message.get(key) or "")
            for key in ("reasoning", "reasoning_content", "thinking")
        },
        "usage": result.get("usage"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    with urlopen("http://127.0.0.1:8767/api/state", timeout=15) as response:
        state = json.load(response)
    if state["config"]["running"] or state["runtime"]["working"]:
        raise RuntimeError("Life must remain paused")
    jobs = [
        (
            "dual_p40",
            11439,
            args.model,
            "You are Patrick, a fictional person. A friend says: rough day, "
            "just wanted to say it, dont need advice. Reply casually in one sentence.",
        ),
        (
            "rtx3060",
            11440,
            "qwen2.5:7b",
            "Suggest one fictional everyday incident on a small town high street. "
            "No disaster. Describe only what a passerby could see, in two sentences.",
        ),
    ]
    rows = []
    for mode in ("serial", "concurrent"):
        for repeat in range(3):
            started = perf_counter()
            if mode == "serial":
                results = [probe(job) for job in jobs]
            else:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(probe, jobs))
            row = {
                "mode": mode,
                "repeat": repeat,
                "pair_seconds": round(perf_counter() - started, 2),
                "results": results,
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
    with args.output.open("x") as output:
        json.dump(
            {"synthetic": True, "revision": state["revision"], "rows": rows}, output, indent=2
        )


if __name__ == "__main__":
    main()
