"""Exercise Pi inference through real contracts and a disposable durable queue."""
import asyncio
import json
import tempfile
from pathlib import Path
from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.adapters.durable_gateway import DurableModelGateway
from eidos.adapters.sqlite_jobs import SQLiteJobStore
from eidos.application.cognition_supervisor import CognitionSupervisor
from eidos.application.cognition import perform

CONTEXTS = [
    {"location": "kitchen", "mood": "Content", "memories": ["Made tea."],
     "recent_inner_stream": ["The mug is warm in my hands."]},
    {"location": "bedroom", "mood": "Sad", "memories": ["Missed a call from Rowan."],
     "recent_inner_stream": [], "forbidden_facts": ["Rowan is angry"]},
    {"location": "Willow Square", "mood": "Curious", "memories": ["Visited Juniper Café."],
     "recent_inner_stream": ["I keep thinking about that café."]},
]

async def run():
    inner = HTTPModelGateway("http://127.0.0.1:11437/v1", "qwen2.5:1.5b")
    results = []
    with tempfile.TemporaryDirectory(prefix="pi-murmur-test-") as directory:
        jobs = SQLiteJobStore(Path(directory) / "jobs.sqlite3")
        supervisor = CognitionSupervisor(jobs, inner, lambda _: 0)
        durable = DurableModelGateway(inner, jobs, lambda _: 0, supervisor=supervisor)
        try:
            for index, context in enumerate(CONTEXTS * 2):
                context = dict(context, time=f"2026-09-08T01:{index:02d}:00+00:00")
                events = []
                output = await perform(durable, "murmur", context, context["time"], events)
                results.append({"text": output, "events": [dict(e.payload) for e in events]})
            statuses = [{"status": j.status, "error": j.error_code} for j in jobs.list_jobs()]
        finally:
            durable.close()
    passed = all(r["text"] for r in results) and all(j["status"] == "completed" for j in statuses)
    print(json.dumps({"passed": passed, "results": results, "jobs": statuses}, indent=2))
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
