"""Bounded Pi-only inference probe; no live simulation, routing or saved-world writes.

Run over SSH with Python on stdin. Uses two CPU threads and one request at a time.
Stops Ollama on a power/thermal alarm; normal completion only unloads the test model.
"""

import concurrent.futures
import json
import subprocess
import time
import urllib.request

DURATION = 300
MODEL = "qwen2.5:1.5b"
CONTEXTS = [
    "You are a fictional person thinking privately. You have just made tea and have twenty minutes before leaving for work. Write a casual thought in under 45 words, not advice or a plan checklist.",
    "You are a fictional person thinking privately. You were writing a letter when a friend called. The letter is unfinished. Write a casual thought in under 45 words. Do not claim to have finished it.",
    "You are a fictional person thinking privately. You missed a call from Rowan. You do not know why they called or how they feel. Write an ordinary thought in under 45 words without inventing their feelings.",
    "You are a fictional person thinking privately. There is nothing urgent this afternoon. You are sitting by the window. Write an ordinary thought in under 45 words; no insight, new event or grand plan is required.",
]


def emit(**values):
    print(json.dumps(values), flush=True)


def health():
    flags = subprocess.check_output(["vcgencmd", "get_throttled"], text=True, timeout=5).strip()
    temp = subprocess.check_output(["vcgencmd", "measure_temp"], text=True, timeout=5).strip()
    return flags, float(temp.split("=")[1].split("'")[0])


def generate(prompt):
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(
            {
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "keep_alive": "2m",
                "options": {
                    "num_predict": 80,
                    "num_ctx": 2048,
                    "num_thread": 2,
                    "temperature": 0.65,
                },
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def run():
    started = time.monotonic()
    maximum_temp = 0.0
    results = []
    aborted = None
    next_report = started
    flags, temp = health()
    emit(stage="baseline", flags=flags, temperature=temp, duration_limit_seconds=DURATION)
    if flags != "throttled=0x0" or temp >= 75:
        emit(stage="not_started", reason="Baseline power or temperature check failed")
        return 2
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        while time.monotonic() - started < DURATION - 60:
            request_start = time.monotonic()
            future = pool.submit(generate, CONTEXTS[len(results) % len(CONTEXTS)])
            while not future.done():
                flags, temp = health()
                maximum_temp = max(maximum_temp, temp)
                if flags != "throttled=0x0" or temp >= 75:
                    aborted = "Power/throttle flag or conservative 75 C thermal limit"
                    stopped = subprocess.run(
                        ["sudo", "-n", "systemctl", "stop", "ollama"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    emit(
                        stage="safety_stop",
                        flags=flags,
                        temperature=temp,
                        service_stopped=stopped.returncode == 0,
                        detail=stopped.stderr.strip(),
                    )
                    break
                if time.monotonic() >= next_report:
                    emit(
                        stage="health",
                        elapsed_seconds=round(time.monotonic() - started, 1),
                        flags=flags,
                        temperature=temp,
                        completed=len(results),
                    )
                    next_report = time.monotonic() + 20
                time.sleep(2)
            if aborted:
                break
            result = future.result()
            seconds = result.get("eval_duration", 0) / 1e9
            record = {
                "number": len(results) + 1,
                "seconds": round(time.monotonic() - request_start, 2),
                "output_tokens": result.get("eval_count"),
                "tokens_per_second": round(result.get("eval_count", 0) / seconds, 2)
                if seconds
                else None,
                "done_reason": result.get("done_reason"),
                "text": result.get("response", ""),
            }
            results.append(record)
            emit(stage="generation", **record)
    except Exception as exc:
        aborted = f"{type(exc).__name__}: {exc}"
        emit(stage="error", reason=aborted)
    finally:
        pool.shutdown(wait=True)
        if not aborted:
            try:
                request = urllib.request.Request(
                    "http://127.0.0.1:11434/api/generate",
                    data=json.dumps({"model": MODEL, "keep_alive": 0}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    response.read()
            except Exception as exc:
                emit(stage="unload_warning", reason=str(exc))
        flags, temp = health()
        emit(
            stage="summary",
            completed=len(results),
            aborted=aborted,
            elapsed_seconds=round(time.monotonic() - started, 1),
            final_flags=flags,
            final_temperature=temp,
            maximum_temperature=max(maximum_temp, temp),
            total_output_tokens=sum(r["output_tokens"] or 0 for r in results),
        )
    return 1 if aborted else 0


if __name__ == "__main__":
    raise SystemExit(run())
