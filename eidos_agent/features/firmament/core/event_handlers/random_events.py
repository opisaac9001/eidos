# eidos_agent/features/firmament/core/event_handlers/random_events.py
from ..event_bus import EventBus
from ..event_types import WORLD_EVENT, THOUGHT_TRIGGER
import random
from datetime import datetime, timezone # Added for timestamping

# Define event type strings used by this module
EVENT_MEMORY_WRITE = "memory.write" # Assuming this is the event type listened to by memory_writer

EVENT_POOL = [
    "car_driveby", "mail_delivery", "stranger_dog_barks", "birds_chirping", "distant_siren",
    # New events:
    "power_flickers_briefly",
    "cat_walks_by_window",
    "phone_buzzes_on_table",
    "sudden_gust_of_wind",
    "kitchen_tap_dripping",
    "distant_music_heard"
]

# For the "distant_music_heard" event's thought trigger
MUSIC_GENRES = ["jazz", "classical", "pop", "rock", "electronic", "folk", "blues", "country", "hip-hop"]
PROBABILITY_OF_RANDOM_EVENT = 0.2 # Defined at module level

def maybe_trigger_random_event(data=None): # data arg is for consistency, not used by this random trigger
    """
    May trigger a random world event based on a probability.
    If an event is triggered, it's published on the EventBus as a WORLD_EVENT.
    Some of these world events might also trigger secondary THOUGHT_TRIGGER events.
    """
    # if data:
    #     print(f"maybe_trigger_random_event called with data: {data}")
    # else:
    #     print("maybe_trigger_random_event called without data (as expected for random trigger).")

    if random.random() < PROBABILITY_OF_RANDOM_EVENT:
        selected_event_name = random.choice(EVENT_POOL)

        world_event_payload = {
            "type": "random_world_event",
            "event_name": selected_event_name,
            "source": "firmament.random_events_generator",
            "timestamp_event_creation_utc": datetime.now(timezone.utc).isoformat() # Timestamp of event creation
        }
        EventBus.instance().publish(WORLD_EVENT, world_event_payload)
        # print(f"RandomEvents: Published {WORLD_EVENT}: {world_event_payload}") # For debugging

        thought_content = None
        thought_mood = "neutral"
        thought_urgency = "low"

        if selected_event_name == "car_driveby":
            thought_content = "A car pulled into the driveway then reversed. That was a bit weird. Who could that be?"
            thought_mood = "confused"
        elif selected_event_name == "mail_delivery":
            thought_content = "Oh, the mail is here! I wonder if there's anything interesting today."
            thought_mood = "curious"
        elif selected_event_name == "stranger_dog_barks":
            thought_content = "Was that a dog barking nearby? Hope it's okay and not in distress."
            thought_mood = "slightly_concerned"
        elif selected_event_name == "power_flickers_briefly":
            thought_content = "Did the lights just flicker? Strange. Hope the power stays on. Maybe I should save my work."
            thought_mood = "surprised"
        elif selected_event_name == "cat_walks_by_window":
            cat_appearance = random.choice(['fluffy white', 'sleek black', 'ginger tabby', 'calico', 'grey striped'])
            thought_content = f"A {cat_appearance} cat just walked past the window. Looked like it was on a mission."
            thought_mood = random.choice(["neutral", "pleased", "distracted_momentarily"])
        elif selected_event_name == "phone_buzzes_on_table":
            thought_content = "My phone just buzzed on the table. I wonder who it is or what the notification is about. Should I check it now?"
            thought_mood = "curious"
            thought_urgency = "medium"
        elif selected_event_name == "distant_music_heard":
            chosen_genre = random.choice(MUSIC_GENRES)
            thought_content = f"Is that music I hear in the distance? Sounds a bit like {chosen_genre}. Makes me wonder where it's coming from."
            thought_mood = random.choice(["nostalgic", "intrigued", "curious", "pensive"])
        elif selected_event_name == "kitchen_tap_dripping":
            thought_content = "Is that the kitchen tap dripping again? That sound is a bit annoying. I should probably check on that later."
            thought_mood = "slightly_annoyed"

        if thought_content:
            thought_trigger_payload = {
                "trigger_event_name": selected_event_name,
                "content": thought_content,
                "mood": thought_mood,
                "urgency": thought_urgency,
                "source": "firmament.random_event_observer"
            }
            EventBus.instance().publish(THOUGHT_TRIGGER, thought_trigger_payload)
            # print(f"RandomEvents: Published {THOUGHT_TRIGGER} for '{selected_event_name}'") # For debugging
    # else:
        # print("RandomEvents: No random event triggered this time.")


# --- New functions for WORLD_EVENT logging ---
def handle_world_event_logging(data: dict):
    """
    Handles WORLD_EVENT by formatting its details and publishing them
    as a new event to be written to memory.
    """
    event_name = data.get("event_name", "unknown_world_event")
    source_of_event = data.get("source", "unknown_source")
    original_event_timestamp = data.get("timestamp_event_creation_utc", datetime.now(timezone.utc).isoformat())

    # print(f"WorldEventLogger: Received {WORLD_EVENT} - Name: {event_name}, Source: {source_of_event}")

    # Create a descriptive content string for the memory entry
    memory_content = f"Pathos observed a world event: '{event_name}' (Source: {source_of_event})."

    # Prepare the payload for the memory.write event
    memory_payload = {
        "type": "observed_world_event", # Specific type for this kind of memory
        "content": memory_content,
        "metadata": {
            "original_world_event_name": event_name,
            "original_world_event_source": source_of_event,
            "original_world_event_timestamp": original_event_timestamp, # Timestamp of the world event itself
            "log_timestamp_utc": datetime.now(timezone.utc).isoformat() # Timestamp of this logging action
            # Optionally, include the full original 'data' if needed, but can be large:
            # "original_world_event_payload": data
        }
    }
    EventBus.instance().publish(EVENT_MEMORY_WRITE, memory_payload)
    # print(f"WorldEventLogger: Published memory entry for '{event_name}'.")

def register_world_event_logging_handler():
    """Subscribes the world event logger (handle_world_event_logging) to WORLD_EVENTs on the EventBus."""
    try:
        event_bus = EventBus.instance()
        event_bus.subscribe(WORLD_EVENT, handle_world_event_logging)
        # print("WorldEventLogger: Successfully registered 'handle_world_event_logging' for WORLD_EVENTs.")
    except Exception as e: # pragma: no cover
        print(f"WorldEventLogger Error: Failed to register event handler. Exception: {e}")


if __name__ == '__main__':
    import unittest.mock # For patching random calls in test
    from collections import defaultdict

    _test_events_captured_random = []
    def generic_event_capture_handler_random(event_type, data):
        print(f"    [Capture - Random Test] Event: {event_type}, "
              f"Name: {data.get('event_name', data.get('trigger_event_name', data.get('metadata', {}).get('original_world_event_name', 'N/A')))}, "
              f"Content: {str(data.get('content', 'N/A'))[:60]}")
        _test_events_captured_random.append({"type": event_type, "data": data})

    class MockEventBusRandom(EventBus):
        def __init__(self):
            self._subscribers = defaultdict(list)
            print("MockEventBusRandom (random_events_test with logging) initialized.")

        def publish(self, event_type: str, data: dict):
            # print(f"MockEventBusRandom: Publishing {event_type}...")
            # Call the generic capture for ALL events passing through the mock bus
            generic_event_capture_handler_random(event_type, data)
            # Then, also dispatch to actual subscribers registered on this mock bus instance
            # This allows testing the interaction between maybe_trigger_random_event and handle_world_event_logging
            for handler in self._subscribers.get(event_type, []):
                handler(data)
            for handler in self._subscribers.get("*", []): # Wildcard if used
                 handler(event_type, data)


    original_event_bus_instance_method = EventBus.instance
    mock_bus_instance_random = MockEventBusRandom()
    EventBus.instance = lambda: mock_bus_instance_random

    # Register the new world event logger ON THE MOCK BUS
    register_world_event_logging_handler()

    # If we want to test the THOUGHT_TRIGGER -> memory.write flow as well,
    # subconscious_hook's handler would need to be registered here too.
    # For this test, we are primarily focused on:
    # maybe_trigger_random_event -> WORLD_EVENT -> handle_world_event_logging -> MEMORY_WRITE

    print("\n--- Testing maybe_trigger_random_event with WORLD_EVENT logging ---")

    # Force a specific event to trigger for deterministic testing of the logger
    forced_event_name = "phone_buzzes_on_table"
    # Patch random.random to ensure event probability is met,
    # and random.choice to select our forced_event_name from the EVENT_POOL.
    # The side_effect for random.choice ensures it only returns our forced event when choosing from EVENT_POOL.
    with unittest.mock.patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.random', return_value=0.05) as mock_rand_val, \
         unittest.mock.patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.choice',
                              side_effect=lambda L: forced_event_name if L == EVENT_POOL else random.choice(L)) as mock_rand_choice:
        print(f"\nAttempting a forced event trigger for '{forced_event_name}':")
        maybe_trigger_random_event()

    # Analyze captured events
    triggered_world_event = None
    observed_world_event_log = None
    associated_thought_trigger = None

    for evt in _test_events_captured_random:
        if evt["type"] == WORLD_EVENT and evt["data"].get("event_name") == forced_event_name:
            triggered_world_event = evt["data"]
        elif evt["type"] == EVENT_MEMORY_WRITE and evt["data"].get("type") == "observed_world_event" and \
             evt["data"].get("metadata", {}).get("original_world_event_name") == forced_event_name:
            observed_world_event_log = evt["data"]
        elif evt["type"] == THOUGHT_TRIGGER and evt["data"].get("trigger_event_name") == forced_event_name:
            associated_thought_trigger = evt["data"]

    assert triggered_world_event is not None, f"Forced WORLD_EVENT ('{forced_event_name}') was not triggered."
    print(f"  Successfully triggered WORLD_EVENT: {triggered_world_event.get('event_name')}")

    assert observed_world_event_log is not None, f"Memory log for observed_world_event ('{forced_event_name}') was not created."
    print(f"  Successfully logged observed WORLD_EVENT to memory: {observed_world_event_log.get('content')}")
    assert observed_world_event_log["metadata"]["original_world_event_source"] == "firmament.random_events_generator"

    if associated_thought_trigger: # This event also triggers a thought
        print(f"  Associated THOUGHT_TRIGGER was also generated: {associated_thought_trigger.get('content')}")
    else:
        print(f"  No specific THOUGHT_TRIGGER was expected or generated for '{forced_event_name}' by maybe_trigger_random_event directly (this is fine).")
        # Note: "phone_buzzes_on_table" *does* create a thought, so this else branch shouldn't be hit for it.

    EventBus.instance = original_event_bus_instance_method
    print("\n--- Random event logging local testing finished ---")
