"""Read-only HTTPS client for an iDRAC Redfish service."""

from __future__ import annotations

import base64
import json
import ssl
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class RedfishClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        ca_file: Path | None = None,
        timeout: float = 20,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("iDRAC URL must be a bare HTTPS origin without credentials")
        if not username.strip() or not password:
            raise ValueError("iDRAC username and password are required")
        if not 1 <= timeout <= 120:
            raise ValueError("Redfish timeout must be between 1 and 120 seconds")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Basic {credentials}",
        }
        self.context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)

    def get_json(self, path: str) -> Mapping[str, Any]:
        if not path.startswith("/redfish/") or "?" in path or "#" in path:
            raise ValueError("Only absolute Redfish resource paths are allowed")
        request = Request(self.base_url + path, headers=self.headers, method="GET")
        with urlopen(request, timeout=self.timeout, context=self.context) as response:
            body = response.read(5_000_001)
        if len(body) > 5_000_000:
            raise ValueError("Redfish response exceeds the 5 MB safety limit")
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError("Redfish resource must be a JSON object")
        return value
