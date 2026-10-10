"""Lay Alderwick onto Frome's real streets: real positions and walking times.

Reads OpenStreetMap data (© OpenStreetMap contributors, ODbL) downloaded with Overpass for
Frome's centre, snaps each Alderwick place to its real counterpart's spot, and computes
walking minutes along the street network (75 m a minute, plus a minute for doors and
crossings). Each place is linked to its nearest few by walking time, so his map stays a map
of neighbours rather than everywhere next to everywhere; routes between the rest follow the
real streets through them. Writes src/eidos/application/frome_v1.json.

Run: python tools/build_real_town.py STREETS_JSON
"""

from __future__ import annotations

import heapq
import json
import math
import sys
from pathlib import Path

WALK_M_PER_MIN = 75
NEIGHBOURS = 3
# Alderwick's places at their real Frome counterparts' spots (lat, lon). Businesses keep
# Alderwick's own names; only where they are is real.
PLACES = {
    "home": (51.23176, -2.32610, "a quiet terrace up the hill behind the town centre"),
    "cafe": (51.23070, -2.32098, "off the Market Place, where the town centre slopes down"),
    "workshop": (
        51.22960,
        -2.32330,
        "on the steep old shopping street climbing up from the centre",
    ),
    "park": (51.22796, -2.32815, "the big Victorian park with the bandstand and the ponds"),
    "market-hall": (51.23362, -2.31997, "the big hall by the river where the markets and gigs are"),
    "station": (51.22723, -2.31003, "the little station down the hill on the edge of town"),
    "library": (51.23244, -2.32072, "by the river crossing in the middle of town"),
    "riverside": (51.23318, -2.31930, "the path along the river below the market hall"),
    "cinema": (51.23158, -2.32208, "a small old cinema just off the main street"),
    "grocer": (51.23193, -2.32094, "the greengrocer's on the main street"),
    "allotments": (51.23565, -2.32134, "allotments in the dip by the river on the north side"),
    "community-hall": (51.23432, -2.33194, "the community centre on the west side of town"),
    "bakery": (51.23176, -2.32394, "on the street of independent shops up from the centre"),
    "secondhand": (51.23146, -2.32134, "among the charity shops on the main street"),
    "sports-ground": (51.24093, -2.31072, "the leisure centre and pitches on the northern edge"),
    "music-room": (51.23062, -2.32172, "in the old vaulted cellars under the town centre"),
}


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat = math.radians((a[0] + b[0]) / 2)
    dy = (a[0] - b[0]) * 111_320
    dx = (a[1] - b[1]) * 111_320 * math.cos(lat)
    return math.hypot(dx, dy)


def main(streets_path: str) -> None:
    data = json.load(open(streets_path))
    nodes = {e["id"]: (e["lat"], e["lon"]) for e in data["elements"] if e["type"] == "node"}
    graph: dict[int, list[tuple[int, float]]] = {}
    for way in (e for e in data["elements"] if e["type"] == "way"):
        refs = [n for n in way["nodes"] if n in nodes]
        for a, b in zip(refs, refs[1:]):
            d = metres(nodes[a], nodes[b])
            graph.setdefault(a, []).append((b, d))
            graph.setdefault(b, []).append((a, d))
    # Only the connected network the town centre is on.
    centre = min(graph, key=lambda n: metres(nodes[n], PLACES["cafe"][:2]))
    seen, stack = {centre}, [centre]
    while stack:
        for nxt, _ in graph[stack.pop()]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    snapped = {
        pid: min(seen, key=lambda n: metres(nodes[n], spot[:2])) for pid, spot in PLACES.items()
    }

    def walk(start: int) -> dict[int, float]:
        dist = {start: 0.0}
        queue = [(0.0, start)]
        while queue:
            d, node = heapq.heappop(queue)
            if d > dist.get(node, math.inf):
                continue
            for nxt, step in graph[node]:
                if d + step < dist.get(nxt, math.inf):
                    dist[nxt] = d + step
                    heapq.heappush(queue, (d + step, nxt))
        return dist

    minutes: dict[tuple[str, str], int] = {}
    for a in PLACES:
        reach = walk(snapped[a])
        for b in PLACES:
            if a < b:
                m = (
                    reach[snapped[b]]
                    + metres(nodes[snapped[a]], PLACES[a][:2])
                    + metres(nodes[snapped[b]], PLACES[b][:2])
                )
                minutes[(a, b)] = max(2, math.ceil(m / WALK_M_PER_MIN) + 1)
    edges: set[tuple[str, str]] = set()
    for a in PLACES:
        nearest = sorted((minutes[tuple(sorted((a, b)))], b) for b in PLACES if b != a)[:NEIGHBOURS]  # type: ignore[index]
        edges |= {tuple(sorted((a, b))) for _, b in nearest}  # type: ignore[misc]
    lats = [p[0] for p in PLACES.values()]
    lons = [p[1] for p in PLACES.values()]

    def scale(value: float, low: float, high: float, flip: bool = False) -> int:
        share = (value - low) / (high - low)
        return round(8 + (1 - share if flip else share) * 84)

    plan = {
        "plan_id": "frome-v1",
        "source": "OpenStreetMap contributors (ODbL), Overpass extract of Frome, Somerset",
        "walking_metres_per_minute": WALK_M_PER_MIN,
        "places": {
            pid: {
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "where": where,
                "x": scale(lon, min(lons), max(lons)),
                "y": scale(lat, min(lats), max(lats), flip=True),
            }
            for pid, (lat, lon, where) in PLACES.items()
        },
        "routes": sorted([a, b, minutes[(a, b)]] for a, b in edges),
        "all_pairs": {f"{a}|{b}": m for (a, b), m in sorted(minutes.items())},
    }
    out = Path(__file__).resolve().parents[1] / "src/eidos/application/frome_v1.json"
    out.write_text(json.dumps(plan, indent=1) + "\n")
    print(
        f"{len(plan['routes'])} routes; e.g.",
        {k: v for k, v in list(plan["all_pairs"].items())[:8]},
    )
    for a, b, m in plan["routes"]:
        print(f"  {a:15s} {b:15s} {m:3d} min")


if __name__ == "__main__":
    main(sys.argv[1])
