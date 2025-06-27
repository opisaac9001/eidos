# eidos_agent/features/firmament/tests/core/test_scene_narrator.py

import unittest
from collections import defaultdict
from unittest.mock import patch, MagicMock # MagicMock not strictly needed for this version, but good to have
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any, Set # Added for consistency

# Adjust import paths based on actual file structure
# Assuming tests/core is a subdir of tests/, and firmament/ is a sibling of tests/
try:
    # Path assuming tests are run from project root (e.g., python -m unittest discover ...)
    # where eidos_agent is in PYTHONPATH.
    from eidos_agent.features.firmament.core.event_bus import EventBus
    from eidos_agent.features.firmament.core.event_types import NEW_NPC_IMPROVISED
    from eidos_agent.features.firmament.core.scene_narrator import handle_new_npc_improvised_event, register_scene_narrator_handlers, MEMORY_WRITE_EVENT_NAME

except ImportError: # pragma: no cover
    # Fallback for simpler structures or direct execution if path is set
    print("CRITICAL: Could not resolve imports for scene_narrator test. Using dummy versions.")
    class EventBus: #type:ignore
        _instance = None; _subscribers = defaultdict(list)
        @classmethod
        def instance(cls):
            if not cls._instance: cls._instance = cls()
            return cls._instance
        def subscribe(self, event_type, handler): self._subscribers[event_type].append(handler)
        def publish(self, event_type, data):
            # print(f"DummyEventBus (narrator_test): Published {event_type} with {data}")
            # Basic dispatch for testing if handler is subscribed to this dummy bus
            for handler_func in self._subscribers.get(event_type, []):
                handler_func(data)

    NEW_NPC_IMPROVISED = "dummy.firmament.npc.improvised.new" #type:ignore
    MEMORY_WRITE_EVENT_NAME = "dummy.memory.write" #type:ignore
    def handle_new_npc_improvised_event(data: Dict[str, Any]): #type:ignore
        print(f"Dummy handle_new_npc_improvised_event called with {str(data)[:100]}")
        # Simulate publishing a memory write for dummy testing
        if EventBus._instance: # Check if dummy instance exists
             EventBus.instance().publish(MEMORY_WRITE_EVENT_NAME, {"type": "dummy_scene_description", "content": "dummy narrative"})
    def register_scene_narrator_handlers(): #type:ignore
        print("Dummy register_scene_narrator_handlers called.")
        if EventBus._instance: # Check if dummy instance exists
            EventBus.instance().subscribe(NEW_NPC_IMPROVISED, handle_new_npc_improvised_event)


class TestSceneNarrator(unittest.TestCase):

    def setUp(self):
        # print(f"\n--- Setting up for SceneNarrator Test: {self._testMethodName} ---")
        # Use a fresh EventBus instance for each test by resetting the singleton
        if hasattr(EventBus, '_instance') and EventBus._instance is not None:
            EventBus._instance = None
        self.event_bus = EventBus.instance()
        # Clear subscribers directly on the instance for this test
        self.event_bus._subscribers = defaultdict(list)

        self.recorded_events = defaultdict(list)

        # This recorder will capture events published ON THE TEST BUS by the handler
        def generic_event_recorder(event_type_arg, data_arg):
            # print(f"    [NarratorTestRecorder] Event: {event_type_arg}, Data: {str(data_arg)[:150]}...")
            self.recorded_events[event_type_arg].append(data_arg)

        # Subscribe the recorder to memory.write events, as that's what the handler should publish
        self.event_bus.subscribe(MEMORY_WRITE_EVENT_NAME,
                                 lambda data: generic_event_recorder(MEMORY_WRITE_EVENT_NAME, data))

        # Register the actual handler we are testing onto this test bus instance
        if callable(register_scene_narrator_handlers):
            register_scene_narrator_handlers()
        else: # pragma: no cover
            print("WARNING: register_scene_narrator_handlers not callable in TestSceneNarrator.setUp. Using direct call fallback.")


    def tearDown(self):
        if hasattr(EventBus, '_instance') and EventBus._instance is not None:
            EventBus._instance._subscribers = defaultdict(list)
            EventBus._instance = None # Ensure full reset for next test's setUp
        # print(f"--- Torn down SceneNarrator Test: {self._testMethodName} ---")

    def _create_sample_new_npc_event_payload(self, include_dialogue=True, include_thought=True, minimal_profile=False) -> Dict[str, Any]:
        profile = {
            "id": "npc_narr_test_001", "name": "Narrator Test NPC",
            "appearance": "wearing a bright yellow hat", "role": "a storyteller",
        }
        if include_dialogue:
            profile["initial_dialogue"] = "And so the story begins..."
        if minimal_profile:
            profile = {"id": "npc_min_002", "name": "Minimal NPC"} # Overwrite with minimal

        thought_content = "Perhaps a narrator is needed for this scene." if include_thought else None

        scene = {
            "location_description": "a cozy library",
            "current_activity_name": "reading ancient tomes",
            "time_of_day": datetime.now(timezone.utc).isoformat()
        }
        return {
            "improvised_npc_profile": profile,
            "triggering_thought_content": thought_content,
            "original_subconscious_thought_payload": {"content": thought_content, "source": "test_narrator"} if thought_content else {},
            "scene_context_at_improvisation": scene
        }

    def test_handle_new_npc_improvised_event_publishes_memory_write(self):
        print("Running: test_handle_new_npc_improvised_event_publishes_memory_write")
        sample_payload = self._create_sample_new_npc_event_payload()

        # Publish the event to the test bus, which should trigger the registered handler
        self.event_bus.publish(NEW_NPC_IMPROVISED, sample_payload)

        memory_writes = self.recorded_events.get(MEMORY_WRITE_EVENT_NAME, [])
        self.assertEqual(len(memory_writes), 1, "Expected one memory.write event.")

        if memory_writes:
            log_entry = memory_writes[0]
            self.assertEqual(log_entry.get("type"), "scene_description_npc_entry")

            content = log_entry.get("content", "")
            profile_data = sample_payload["improvised_npc_profile"]
            scene_data = sample_payload["scene_context_at_improvisation"]

            self.assertIn(profile_data["name"], content)
            self.assertIn(profile_data["appearance"], content)
            self.assertIn(profile_data["role"], content)
            self.assertIn(scene_data["location_description"], content)
            self.assertIn(profile_data["initial_dialogue"], content)
            if sample_payload["triggering_thought_content"]:
                 self.assertIn(sample_payload["triggering_thought_content"][:97], content) # Snippet check

            metadata = log_entry.get("metadata", {})
            self.assertEqual(metadata.get("npc_id"), profile_data["id"])
            self.assertEqual(metadata.get("triggering_event_type"), str(NEW_NPC_IMPROVISED)) # Ensure string form
            self.assertTrue("timestamp_event_logged_utc" in metadata) # Changed from "timestamp"
        print("Test Passed: Scene narrator logged NPC entry to memory.")

    def test_handle_new_npc_event_with_missing_initial_dialogue(self):
        print("Running: test_handle_new_npc_event_with_missing_initial_dialogue")
        sample_payload = self._create_sample_new_npc_event_payload(include_dialogue=False)

        self.event_bus.publish(NEW_NPC_IMPROVISED, sample_payload)

        memory_writes = self.recorded_events.get(MEMORY_WRITE_EVENT_NAME, [])
        self.assertEqual(len(memory_writes), 1)
        log_entry = memory_writes[0]
        self.assertEqual(log_entry.get("type"), "scene_description_npc_entry")
        content = log_entry.get("content", "")
        self.assertIn("They didn't say anything immediately", content)
        self.assertNotIn("They made their presence known, perhaps by saying, \"\"", content) # Check for empty quote
        print("Test Passed: Scene narrator handled missing initial dialogue gracefully.")

    def test_handle_new_npc_event_with_minimal_profile_data(self):
        print("Running: test_handle_new_npc_event_with_minimal_profile_data")
        sample_payload = self._create_sample_new_npc_event_payload(minimal_profile=True, include_thought=False)

        self.event_bus.publish(NEW_NPC_IMPROVISED, sample_payload)
        memory_writes = self.recorded_events.get(MEMORY_WRITE_EVENT_NAME, [])
        self.assertEqual(len(memory_writes), 1)
        log_entry = memory_writes[0]
        self.assertEqual(log_entry.get("type"), "scene_description_npc_entry")
        content = log_entry.get("content", "")
        self.assertIn("Minimal NPC", content)
        self.assertIn("of nondescript appearance", content)
        self.assertIn("playing an unknown role", content)
        self.assertNotIn("This encounter seems to have stemmed from Pathos's earlier thought", content)
        print("Test Passed: Scene narrator handled minimal profile data correctly.")

    def test_handle_new_npc_event_invalid_payload_profile(self):
        print("Running: test_handle_new_npc_event_invalid_payload_profile")
        # Test with npc_profile missing or not a dict
        with self.assertLogs(logger='eidos_agent.features.firmament.core.scene_narrator', level='ERROR') as log_cm:
            handle_new_npc_improvised_event({"improvised_npc_profile": None, "scene_context_at_improvisation": {}})
        self.assertTrue(any("Invalid or critically incomplete npc_profile" in msg for msg in log_cm.output))

        with self.assertLogs(logger='eidos_agent.features.firmament.core.scene_narrator', level='ERROR') as log_cm_2:
            handle_new_npc_improvised_event({"improvised_npc_profile": {"id":"bad", "name":None}, "scene_context_at_improvisation": {}}) # name is None
        self.assertTrue(any("Invalid or critically incomplete npc_profile" in msg for msg in log_cm_2.output))

        memory_writes = self.recorded_events.get(MEMORY_WRITE_EVENT_NAME, [])
        self.assertEqual(len(memory_writes), 0, "No memory write should occur for invalid profile in payload.")
        print("Test Passed: Scene narrator handled invalid profile in payload with error log.")

    def test_handle_new_npc_event_invalid_payload_scene_context(self):
        print("Running: test_handle_new_npc_event_invalid_payload_scene_context")
        # Test with scene_context missing or not a dict
        profile = {"id": "npc_valid", "name": "Valid NPC"}
        with self.assertLogs(logger='eidos_agent.features.firmament.core.scene_narrator', level='WARNING') as log_cm: # Now a warning
            handle_new_npc_improvised_event({"improvised_npc_profile": profile, "scene_context_at_improvisation": None})
        self.assertTrue(any("Missing or invalid scene_context" in msg for msg in log_cm.output))

        # Should still produce a memory write, but with minimal scene info
        memory_writes = self.recorded_events.get(MEMORY_WRITE_EVENT_NAME, [])
        self.assertEqual(len(memory_writes), 1, "Memory write should occur even with missing scene_context (using defaults).")
        if memory_writes:
            self.assertIn("an unspecified location", memory_writes[0].get("content",""))
            self.assertIn("some activity", memory_writes[0].get("content",""))
        print("Test Passed: Scene narrator handled invalid scene_context with warning and default narrative.")


if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.DEBUG)
    # logging.getLogger('eidos_agent.features.firmament.core.scene_narrator').setLevel(logging.DEBUG)
    unittest.main(verbosity=2)
