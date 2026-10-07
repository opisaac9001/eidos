"""When you come to visit, his voice's model is woken in the background, so a model that
unloads when idle doesn't keep his first reply waiting."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.adapters.web_server import Runtime
from eidos.application.life import Life


def test_a_visit_wakes_his_voice_model(tmp_path) -> None:
    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            seen.append(
                {
                    "path": self.path,
                    **json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                }
            )
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"done": true}')

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    settings = {
        "providers": {
            "dell": {"kind": "ollama", "base_url": f"http://127.0.0.1:{server.server_port}/v1"}
        },
        "models": {"voice-35b": {"provider": "dell", "model": "qwen3.5:35b"}},
        "roles": {"voice": ["voice-35b"]},
    }
    runtime = Runtime(Life(SQLiteEventStore(tmp_path / "w.sqlite3"), StandInGateway()), interval=60)
    runtime.models = SimpleNamespace(configured=SimpleNamespace(settings=lambda: settings))
    runtime.warm_voice()
    for _ in range(50):
        if seen:
            break
        time.sleep(0.05)
    server.shutdown()
    assert seen and seen[0]["path"] == "/api/generate" and seen[0]["model"] == "qwen3.5:35b"
    assert "keep_alive" not in seen[0]  # the server's own idle policy decides
