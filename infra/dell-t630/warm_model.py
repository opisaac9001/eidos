"""Wait for a loopback model worker and load its assigned model before readiness."""

import json
import os
import time
import urllib.error
import urllib.request

base = "http://" + os.environ["OLLAMA_HOST"]
for attempt in range(60):
    try:
        with urllib.request.urlopen(base + "/api/version", timeout=2):
            break
    except (urllib.error.URLError, TimeoutError):
        if attempt == 59:
            raise
        time.sleep(1)

request = urllib.request.Request(
    base + "/api/generate",
    data=json.dumps(
        {
            "model": os.environ["OLLAMA_BOOT_MODEL"],
            "prompt": "",
            "stream": False,
            "keep_alive": -1,
        }
    ).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=300) as response:
    result = json.load(response)
if not result.get("done"):
    raise RuntimeError("Model warmup did not complete")
print("Model loaded: " + os.environ["OLLAMA_BOOT_MODEL"], flush=True)
