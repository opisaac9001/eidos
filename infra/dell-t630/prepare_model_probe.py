"""Warm one downloaded candidate on a paused application's forwarded test worker.

Never changes model routes, weights or live state. Refuses to operate while life
is running. Restoring qwen2.5:14b uses the same command after testing.
"""

import argparse
import json
from urllib.request import Request, urlopen


def api(base, path, payload=None, timeout=15):
    query = Request(
        base + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(query, timeout=timeout) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "model",
        choices=[
            "ministral-3:14b",
            "gemma4:12b",
            "gemma4:31b",
            "qwen3.5:2b",
            "qwen3.5:4b",
            "qwen3.5:27b",
            "qwen3.5:35b",
            "qwen2.5:14b",
            "qwen2.5:7b",
        ],
    )
    parser.add_argument(
        "--worker-url",
        choices=["http://127.0.0.1:11439", "http://127.0.0.1:11440"],
        default="http://127.0.0.1:11439",
        help="11439 is the forwarded test worker; 11440 is the independent 3060 worker",
    )
    args = parser.parse_args()
    state = api("http://127.0.0.1:8767", "/api/state")
    if state["config"]["running"] or state["runtime"]["working"]:
        raise RuntimeError("Life must remain paused for this isolated worker test")
    print(
        json.dumps(
            {
                "revision": state["revision"],
                "time": state["time"],
                "running": state["config"]["running"],
            }
        ),
        flush=True,
    )
    worker = args.worker_url
    tags = api(worker, "/api/tags")
    if args.model not in {item["name"] for item in tags["models"]}:
        raise RuntimeError("Candidate download is not complete")
    for loaded in api(worker, "/api/ps")["models"]:
        print("Unloading worker cache: " + loaded["name"], flush=True)
        api(worker, "/api/generate", {"model": loaded["name"], "keep_alive": 0}, 120)
    print("Warming " + args.model + " with thinking off and 8192 context", flush=True)
    result = api(
        worker,
        "/api/chat",
        {
            "model": args.model,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "think": False,
            "stream": False,
            "keep_alive": -1 if args.model in {"qwen2.5:14b", "qwen2.5:7b"} else "10m",
            "options": {"num_ctx": 8192, "num_predict": 8},
        },
        300,
    )
    print(
        json.dumps(
            {
                "model": result.get("model"),
                "done": result.get("done"),
                "reasoning_chars": len(result.get("message", {}).get("thinking", "")),
                "message": result.get("message", {}).get("content"),
                "loaded": api(worker, "/api/ps"),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
