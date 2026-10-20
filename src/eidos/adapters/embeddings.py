"""Text embeddings from an Ollama server (``/api/embed``), for recall by meaning.

A small local model (``nomic-embed-text``) turns a memory or a cue into a vector, so "the
light fitting" can bring back the lamp. No key, no cost; if the server isn't there, recall
simply goes without meaning.
"""

from __future__ import annotations

import json
import logging
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:11436"
DEFAULT_MODEL = "nomic-embed-text"
BATCH = 64


class OllamaEmbedder:
    def __init__(
        self, base_url: str = DEFAULT_URL, model: str = DEFAULT_MODEL, timeout: float = 60.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.failures = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        """One vector per text, or None if the server couldn't answer."""
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH):
            batch = list(texts[start : start + BATCH])
            request = Request(
                f"{self.base_url}/api/embed",
                data=json.dumps({"model": self.model, "input": batch}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    raw = json.loads(response.read().decode())
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
                self.failures += 1
                if self.failures in (1, 10, 100):
                    logger.warning("Embeddings unavailable (%s): %s", self.model, error)
                return None
            found = raw.get("embeddings") if isinstance(raw, dict) else None
            if not isinstance(found, list) or len(found) != len(batch):
                self.failures += 1
                return None
            vectors.extend([float(x) for x in vector] for vector in found)
        self.failures = 0
        return vectors
