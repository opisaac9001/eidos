# eidos_agent/features/firmament/core/scene_narrator.py
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional # Added Optional

# Attempt to import EventBus and NEW_NPC_IMPROVISED.
# Also attempt to import EVENT_MEMORY_WRITE if it's defined centrally.
try:
    from .event_bus import EventBus
    from .event_types import NEW_NPC_IMPROVISED

    # Attempt to import a centrally defined EVENT_MEMORY_WRITE
    try:
        from .event_types import MEMORY_WRITE as MEMORY_WRITE_EVENT_NAME
        # Assuming it might be named MEMORY_WRITE in event_types.py
        # If it's literally EVENT_MEMORY_WRITE, then:
        # from .event_types import EVENT_MEMORY_WRITE as MEMORY_WRITE_EVENT_NAME
    except ImportError:
        # Fallback to local definition if not found in event_types.py
        MEMORY_WRITE_EVENT_NAME = "memory.write"
        logger = logging.getLogger(__name__) # Initialize logger here if not top-level due to try/except
        logger.info("SceneNarrator: MEMORY_WRITE_EVENT_NAME not found in event_types, using local definition 'memory.write'.")


except ImportError: # pragma: no cover
    # This block executes if core EventBus or NEW_NPC_IMPROVISED cannot be imported.
    # This indicates a severe setup issue or that the file is being parsed in isolation without correct paths.
    print("CRITICAL IMPORT ERROR in scene_narrator.py. Scene narration will not function. Using dummy versions.")
    class EventBus: #type:ignore
        @staticmethod
        def instance(): return EventBus()
        def publish(self, event_type: str, data: Dict[str, Any]):
            print(f"DummyEventBus (SceneNarrator): Suppressed publish of {event_type} with data {str(data)[:100]}...")
        def subscribe(self, event_type: str, handler: Any): pass

    NEW_NPC_IMPROVISED = "dummy.firmament.npc.improvised.new" #type:ignore
    MEMORY_WRITE_EVENT_NAME = "dummy.memory.write" #type:ignore
    # Initialize logger here as well if it wasn't initialized due to other import error paths
    if 'logger' not in globals():
        logger = logging.getLogger(__name__) # type: ignore


logger = logging.getLogger(__name__)

def handle_new_npc_improvised_event(data: Dict[str, Any]):
    """
    Handles the NEW_NPC_IMPROVISED event by generating a narrative description
    of the NPC's appearance and interaction context, then logging it to memory.
    """
    # logger.debug(f"SceneNarrator: Received NEW_NPC_IMPROVISED event. Data keys: {list(data.keys()) if isinstance(data,dict) else 'Invalid data type'}")

    npc_profile = data.get("improvised_npc_profile")
    # The full original thought payload is in "original_subconscious_thought_payload"
    # The "triggering_thought_content" is just the text content of that thought.
    triggering_thought_content = data.get("triggering_thought_content", "an unspecified earlier thought")
    scene_context = data.get("scene_context_at_improvisation")

    if not isinstance(npc_profile, dict) or not npc_profile.get("id") or not npc_profile.get("name"):
        logger.error(f"SceneNarrator: Invalid or critically incomplete npc_profile in NEW_NPC_IMPROVISED event data: {str(npc_profile)[:200]}")
        return
    if not isinstance(scene_context, dict): # scene_context can be empty but must be a dict
        logger.warning(f"SceneNarrator: Missing or invalid scene_context in NEW_NPC_IMPROVISED event data. Proceeding with minimal scene info. Data: {str(data)[:200]}")
        scene_context = {} # Ensure it's a dict to allow .get() calls

    npc_id = npc_profile.get("id")
    npc_name = npc_profile.get("name", "An unnamed individual")
    appearance = npc_profile.get("appearance", "of nondescript appearance")
    role = npc_profile.get("role", "playing an unknown role")
    initial_dialogue = npc_profile.get("initial_dialogue", "") # May be empty

    location = scene_context.get("location_description", "an unspecified location")
    pathos_activity = scene_context.get("current_activity_name", "some activity")
    # pathos_mood = scene_context.get("pathos_mood_state", "a neutral mood") # Could be added to narrative

    # Construct the narrative
    narrative_parts = [
        f"Pathos became aware of {npc_name} (ID: {npc_id}) at {location} while Pathos was engaged in '{pathos_activity}'."
        f" This individual appears as '{appearance}' and seems to be {role}."
    ]

    if initial_dialogue:
        narrative_parts.append(f" They made their presence known, perhaps by saying, \"{initial_dialogue}\"")
    else:
        narrative_parts.append(f" They didn't say anything immediately, but their presence was noted.")

    if triggering_thought_content and triggering_thought_content != "an unspecified earlier thought":
        thought_snippet = triggering_thought_content
        if len(thought_snippet) > 120: # Truncate long thoughts for this narrative
            thought_snippet = thought_snippet[:117] + "..."
        narrative_parts.append(f" This encounter might have been seeded by Pathos's earlier thought: \"{thought_snippet}\".")

    narrative = " ".join(narrative_parts)
    # logger.info(f"SceneNarrator: Generated NPC entry narrative: {narrative}")

    # Prepare payload for memory system
    memory_payload = {
        "type": "scene_description_npc_entry", # Specific type for this kind of memory log
        "content": narrative,
        "metadata": {
            "npc_id": npc_id,
            "npc_name": npc_name,
            "npc_role_in_scene": role, # Role specific to this scene/context
            "npc_appearance_summary": appearance,
            "triggering_event_type": str(NEW_NPC_IMPROVISED),
            "original_thought_content_snippet": triggering_thought_content[:150] if triggering_thought_content else None,
            "scene_location": location,
            "pathos_activity_at_entry": pathos_activity,
            "timestamp_event_logged_utc": datetime.now(timezone.utc).isoformat() # Timestamp of this log
        }
    }
    EventBus.instance().publish(MEMORY_WRITE_EVENT_NAME, memory_payload)
    # logger.debug(f"SceneNarrator: Published memory entry for new NPC scene description (Type: {memory_payload.get('type')})")


def register_scene_narrator_handlers():
    """Subscribes scene narrator event handlers to the EventBus."""
    if 'EventBus' not in globals() or not callable(EventBus.instance): # pragma: no cover
        logger.critical("SceneNarrator: EventBus is not available (likely critical import error). Cannot register handlers.")
        return

    try:
        event_bus = EventBus.instance()
        event_bus.subscribe(NEW_NPC_IMPROVISED, handle_new_npc_improvised_event)
        logger.info("SceneNarrator: Registered 'handle_new_npc_improvised_event' for NEW_NPC_IMPROVISED events.")
    except Exception as e: # pragma: no cover
        logger.error(f"SceneNarrator: Error during event handler registration: {e}", exc_info=True)


if __name__ == '__main__': # pragma: no cover
    from collections import defaultdict # For MockEventBus in test

    logging.basicConfig(level=logging.INFO)
    # Configure logger for this module to DEBUG to see its specific logs if any were un-commented
    # logging.getLogger('eidos_agent.features.firmament.core.scene_narrator').setLevel(logging.DEBUG)

    _test_events_captured_narrator = []
    def capture_narrator_events_for_test(event_type_captured, data_captured): # Unique name for test handler
        print(f"    [NarratorTest Capture] Event: {event_type_captured}, "
              f"Type in Data: {data_captured.get('type')}, "
              f"Content: {str(data_captured.get('content'))[:100]}...")
        _test_events_captured_narrator.append({"type": event_type_captured, "data": data_captured})

    # Mock EventBus for isolated testing of this module's handlers
    class MockEventBusForNarrator(EventBus):
        def __init__(self):
            self._subscribers = defaultdict(list) # Ensure subscribers dict is initialized
            print("MockEventBusForNarrator initialized.")

        def publish(self, event_type: str, data: dict):
            # print(f"MockEventBusForNarrator: Publishing {event_type}...")
            # Crucially, call the capture function to log what this handler would publish
            capture_narrator_events_for_test(event_type, data)

            # Then, simulate dispatch to actual subscribers that were registered on this mock instance
            # This is important for testing if the handler *itself* works when an event comes in.
            for handler in self._subscribers.get(event_type, []):
                handler(data)
            for handler in self._subscribers.get("*", []): # Wildcard if used
                 handler(event_type, data)

    # Monkey patch EventBus.instance() for this test run
    original_event_bus_instance_method = EventBus.instance
    mock_bus_instance_narrator_test = MockEventBusForNarrator() # Unique instance name
    EventBus.instance = lambda: mock_bus_instance_narrator_test

    # Register handlers ON THE MOCK BUS
    register_scene_narrator_handlers()

    print("\n--- Testing Scene Narrator: handle_new_npc_improvised_event ---")

    sample_improvised_profile_for_test = {
        "id": "improv_npc_test_001",
        "name": "Mysterious Stranger",
        "appearance": "a cloaked figure with piercing, observant eyes",
        "role": "an enigmatic observer of city life",
        "personality": "quiet, intense, and perhaps a little melancholic",
        "relationship_to_pathos": "completely unknown, a first encounter",
        "initial_dialogue": "We meet at a curious juncture, don't we? The city breathes secrets tonight."
    }
    sample_thought_for_test = "I feel like someone is watching me from the shadows again."
    sample_scene_context_for_test = {
        "location_description": "a rain-slicked, foggy street corner near the old wharf",
        "pathos_mood_state": "apprehensive and introspective",
        "current_activity_name": "walking home late after a disquieting phone call",
        "time_of_day": "2023-11-01T02:30:00Z"
    }

    # This is the payload that `simulator.py` would publish for NEW_NPC_IMPROVISED
    new_npc_event_payload_for_test = {
        "improvised_npc_profile": sample_improvised_profile_for_test,
        "triggering_thought_content": sample_thought_for_test,
        "original_subconscious_thought_payload": {"content": sample_thought_for_test, "timestamp": "2023-11-01T02:29:00Z", "mood_at_thought": {"name":"uneasy"}},
        "scene_context_at_improvisation": sample_scene_context_for_test
    }

    # Directly publish the NEW_NPC_IMPROVISED event to trigger the handler registered on the mock bus.
    # The mock bus's publish will first call `capture_narrator_events_for_test` for NEW_NPC_IMPROVISED itself,
    # then dispatch to `handle_new_npc_improvised_event`.
    # `handle_new_npc_improvised_event` will then call publish for MEMORY_WRITE_EVENT_NAME,
    # which will again be captured by `capture_narrator_events_for_test`.
    mock_bus_instance_narrator_test.publish(NEW_NPC_IMPROVISED, new_npc_event_payload_for_test)

    # Assertions
    # We expect two events captured: NEW_NPC_IMPROVISED (input) and MEMORY_WRITE_EVENT_NAME (output)
    assert len(_test_events_captured_narrator) == 2, f"Expected 2 captured events (input NEW_NPC & output MEMORY_WRITE), got {len(_test_events_captured_narrator)}"

    published_memory_events = [e for e in _test_events_captured_narrator if e["type"] == MEMORY_WRITE_EVENT_NAME]
    assert len(published_memory_events) == 1, "Expected exactly one memory.write event from scene_narrator."

    if published_memory_events:
        log_entry = published_memory_events[0]["data"]
        assert log_entry.get("type") == "scene_description_npc_entry", "Memory log type mismatch."
        # Check for key elements in the narrative content
        assert "Mysterious Stranger" in log_entry.get("content", ""), "NPC name missing in narrative."
        assert "cloaked figure" in log_entry.get("content", ""), "NPC appearance missing in narrative."
        assert "foggy street corner" in log_entry.get("content", ""), "Location missing in narrative."
        assert "We meet at a curious juncture" in log_entry.get("content", ""), "Initial dialogue missing."
        assert "someone is watching me" in log_entry.get("content", ""), "Triggering thought missing."

        # Check metadata
        metadata = log_entry.get("metadata", {})
        assert metadata.get("npc_id") == "improv_npc_test_001", "NPC ID missing/mismatch in metadata."
        assert metadata.get("original_thought_content_snippet") == sample_thought_for_test, "Thought snippet mismatch."
        assert metadata.get("scene_location") == "a rain-slicked, foggy street corner near the old wharf"

    print("\nScene Narrator's handle_new_npc_improvised_event test completed. Check logged events.")

    # Restore original EventBus class method
    EventBus.instance = original_event_bus_instance_method
    print("\n--- Scene Narrator __main__ testing finished ---")
