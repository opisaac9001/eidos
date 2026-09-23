"""Exercise each real model worker concurrently and report measured throughput.

Run on the server after the configured models have been downloaded. This uses
synthetic prompts only and does not modify Pathos's world or memories.
"""

import concurrent.futures
import json
import time
import urllib.request

WORKERS = (
    ("pathos", 11434, "qwen2.5:14b"),
    ("world", 11435, "qwen2.5:14b"),
    ("cognition", 11436, "qwen2.5:7b"),
)


def probe(worker: tuple[str, int, str]) -> dict[str, object]:
    name, port, model = worker
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/generate",
        data=json.dumps(
            {
                "model": model,
                "prompt": "Describe a quiet walk through a small British town in about 150 words.",
                "stream": False,
                "options": {"num_predict": 256, "temperature": 0.5, "num_ctx": 8192},
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=300) as response:
        result = json.load(response)
    seconds = result.get("eval_duration", 0) / 1e9
    if not result.get("done") or not result.get("response", "").strip():
        raise RuntimeError(f"{name} did not return a completed, nonempty response")
    return {
        "worker": name,
        "model": model,
        "wall_seconds": round(time.monotonic() - started, 2),
        "output_tokens": result.get("eval_count"),
        "tokens_per_second": round(result["eval_count"] / seconds, 2) if seconds else None,
        "response": result["response"],
    }


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        print(json.dumps(list(pool.map(probe, WORKERS)), indent=2))
