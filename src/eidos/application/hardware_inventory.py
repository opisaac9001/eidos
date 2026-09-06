"""Bounded read-only discovery of server resources through Redfish."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Mapping

JsonObject = Mapping[str, Any]
Fetcher = Callable[[str], JsonObject]


def collect_redfish_inventory(fetch: Fetcher, endpoint_host: str) -> dict[str, Any]:
    """Collect known inventory surfaces without issuing any mutating request."""

    resources: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}

    def read(path: str, required: bool = False) -> JsonObject | None:
        if path in resources:
            return resources[path]
        if len(resources) >= 500:
            raise ValueError("Redfish inventory exceeded the 500-resource safety bound")
        try:
            value = dict(fetch(path))
        except (OSError, ValueError, KeyError, TypeError) as error:
            if required:
                raise ValueError(f"Required Redfish resource failed: {path}: {error}") from None
            errors[path] = type(error).__name__
            return None
        resources[path] = _sanitize(value)
        return value

    def links(value: JsonObject, key: str) -> list[str]:
        candidate = value.get(key)
        candidates = candidate if isinstance(candidate, list) else [candidate]
        paths: list[str] = []
        for item in candidates:
            if not isinstance(item, Mapping):
                continue
            path = item.get("@odata.id")
            if isinstance(path, str) and path.startswith("/redfish/"):
                paths.append(path)
        return paths

    def collection(path: str) -> list[JsonObject]:
        value = read(path)
        if value is None:
            return []
        members = value.get("Members", [])
        if not isinstance(members, list):
            errors[path] = "InvalidMembers"
            return []
        output: list[JsonObject] = []
        for member in members[:256]:
            if not isinstance(member, Mapping):
                continue
            member_path = member.get("@odata.id")
            if not isinstance(member_path, str) or not member_path.startswith("/redfish/"):
                continue
            resolved = read(member_path)
            if resolved is not None:
                output.append(resolved)
        return output

    root = read("/redfish/v1", required=True)
    assert root is not None
    top_level = ("Systems", "Chassis", "Managers", "UpdateService")
    discovered: dict[str, list[JsonObject]] = {}
    for key in top_level:
        paths = links(root, key)
        if not paths:
            continue
        path = paths[0]
        discovered[key] = collection(path) if key != "UpdateService" else []
        if key == "UpdateService":
            service = read(path)
            if service is not None:
                for firmware in links(service, "FirmwareInventory"):
                    collection(firmware)

    child_keys = {
        "Systems": (
            "Processors",
            "Memory",
            "Storage",
            "EthernetInterfaces",
            "NetworkInterfaces",
            "PCIeDevices",
            "PCIeFunctions",
            "SimpleStorage",
        ),
        "Chassis": ("Power", "Thermal", "PowerSubsystem", "ThermalSubsystem"),
        "Managers": ("EthernetInterfaces", "NetworkProtocol", "LogServices"),
    }
    for group, items in discovered.items():
        for item in items:
            for key in child_keys.get(group, ()):
                for path in links(item, key):
                    child = read(path)
                    children = (
                        collection(path)
                        if child is not None and isinstance(child.get("Members"), list)
                        else [child]
                        if child is not None
                        else []
                    )
                    if key == "Storage":
                        for controller in children:
                            for nested in ("Drives", "Volumes"):
                                for nested_path in links(controller, nested):
                                    nested_value = read(nested_path)
                                    if nested_value is not None and isinstance(
                                        nested_value.get("Members"), list
                                    ):
                                        collection(nested_path)
    return {
        "schema": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "endpoint_host": endpoint_host,
        "read_only": True,
        "resource_count": len(resources),
        "resources": resources,
        "errors": errors,
    }


def _sanitize(value: Any) -> Any:
    sensitive = {"authorization", "password", "secret", "token", "sessionkey"}
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if str(key).lower() not in sensitive
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)
