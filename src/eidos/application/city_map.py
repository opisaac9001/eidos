"""An event-sourced travel atlas; registration is not a fabricated visit."""

from collections import Counter


def city_map(history, catalog, current_location_id):
    visits = Counter()
    last_visit = {}
    for event in history:
        if event.kind == "pathos.moved":
            place = event.payload.get("location_id")
            if place in catalog.places:
                visits[place] += 1
                last_visit[place] = event.payload.get("simulated_at")
    return {
        "places": {
            place_id: {
                "experience": "here"
                if place_id == current_location_id
                else "visited"
                if visits[place_id]
                else "known_not_visited",
                "visits": visits[place_id],
                "last_visit": last_visit.get(place_id),
            }
            for place_id in catalog.places
        },
        "routes": [
            {"from": sorted(edge)[0], "to": sorted(edge)[1], "minutes": minutes}
            for edge, minutes in sorted(
                catalog.route_minutes.items(), key=lambda item: sorted(item[0])
            )
        ],
    }
