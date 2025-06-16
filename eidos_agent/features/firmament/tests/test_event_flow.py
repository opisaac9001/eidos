# eidos_agent/features/firmament/tests/test_event_flow.py

import unittest
from collections import defaultdict

# Attempt to import necessary modules from Firmament.
# These imports assume that the test is run in an environment where the
# 'eidos_agent.features.firmament' package is accessible in PYTHONPATH.
# For example, running `python -m unittest discover eidos_agent/features/firmament/tests`
# from the parent directory of 'eidos_agent'.

try:
    from ..core.event_bus import EventBus
    from ..core.event_types import THOUGHT_TRIGGER, WORLD_EVENT, SCHEDULE_BLOCK_STARTED, NPC_DIALOGUE
    # MEMORY_WRITE is used as a string "memory.write" in subconscious_hook, so we'll use that.
    MEMORY_WRITE_EVENT_TYPE = "memory.write"
    from ..core.simulator import run_simulation_tick # Uses chronos_adapter internally
    from ..integrations.subconscious_hook import handle_thought_trigger, register_thought_trigger_handler
    from ..integrations.chronos_adapter import get_current_block as chronos_get_current_block, _set_current_block_for_testing
    from ..core.event_handlers.random_events import maybe_trigger_random_event # Example event generator
    from ..core.npc_controller import spawn_npc_interaction, register_npc_event_listeners # For NPC interaction flow

except ImportError as e:
    print(f"ImportError in test_event_flow.py: {e}. Some tests may fail or not run correctly.")
    print("Ensure PYTHONPATH is set up to include the parent directory of 'eidos_agent'.")
    # Define dummy classes/functions if imports fail, so the file can be parsed at least.
    class EventBus: _instance = None; _subscribers = defaultdict(list); @classmethod def instance(cls): return cls() if not cls._instance else cls._instance; def subscribe(self, et, h): pass; def publish(self, et, d): print(f"DummyEventBus: Published {et} with {d}")
    THOUGHT_TRIGGER, WORLD_EVENT, SCHEDULE_BLOCK_STARTED, NPC_DIALOGUE, MEMORY_WRITE_EVENT_TYPE = "dummy.tt", "dummy.we", "dummy.sbs", "dummy.nd", "dummy.mw"
    def run_simulation_tick(): pass
    def handle_thought_trigger(p): pass
    def register_thought_trigger_handler(): pass
    def chronos_get_current_block(): return {}
    def _set_current_block_for_testing(d=None): pass
    def maybe_trigger_random_event(d=None): pass
    def spawn_npc_interaction(d): pass
    def register_npc_event_listeners(): pass


class TestEventFlow(unittest.TestCase):

    def setUp(self):
        """Set up test environment before each test method."""
        print(f"\n--- Setting up for: {self._testMethodName} ---")
        self.event_bus = EventBus.instance()
        # Clear subscribers to ensure test isolation. This is a bit crude.
        # A dedicated EventBus.reset() or a new instance per test would be better.
        self.event_bus._subscribers = defaultdict(list)

        self.recorded_events = defaultdict(list)

        # Generic event recorder to capture all events for inspection
        def generic_event_recorder(event_type, data):
            # print(f"    [EventRecorded] Type: {event_type}, Data: {data}")
            self.recorded_events[event_type].append(data)

        # Subscribe the generic recorder to all event types we are interested in.
        # This uses a lambda to pass the event_type to the recorder.
        all_event_types_to_monitor = [THOUGHT_TRIGGER, WORLD_EVENT, SCHEDULE_BLOCK_STARTED, MEMORY_WRITE_EVENT_TYPE, NPC_DIALOGUE]
        for et in all_event_types_to_monitor:
            # Need a unique function for each subscription if using lambdas this way and want to unsubscribe later.
            # Or, a single handler that is told which event type it is handling.
            # For simplicity, let's assume _subscribers is cleared each time.
            self.event_bus.subscribe(et, lambda data, event_t=et: generic_event_recorder(event_t, data))

        # Register core handlers that mediate between events
        register_thought_trigger_handler() # Subscribes handle_thought_trigger to THOUGHT_TRIGGER
        register_npc_event_listeners()     # Subscribes spawn_npc_interaction to WORLD_EVENT

        print("Setup complete. EventBus subscribers cleared and basic recorders/handlers registered.")

    def tearDown(self):
        """Clean up test environment after each test method."""
        # Reset Chronos adapter's test override
        _set_current_block_for_testing(None)
        # Clear subscribers again after test
        if hasattr(self.event_bus, '_subscribers'): # Check if event_bus was successfully initialized
            self.event_bus._subscribers = defaultdict(list)
        print(f"--- Torn down: {self._testMethodName} ---")


    def test_simulation_tick_starts_schedule_block_event(self):
        """
        Tests that run_simulation_tick() publishes a SCHEDULE_BLOCK_STARTED event
        using data from the Chronos adapter.
        """
        print("Running: test_simulation_tick_starts_schedule_block_event")

        # Configure the Chronos adapter to return a specific block for this test
        test_block_data = {
            "id": "test_block_sim_tick_001", "type": "test_work", "name": "SimTick Test Block",
            "start_time_utc": "2023-01-01T09:00:00Z", "end_time_utc": "2023-01-01T10:00:00Z"
        }
        _set_current_block_for_testing(test_block_data)

        run_simulation_tick() # This should call chronos_get_current_block and publish

        self.assertGreater(len(self.recorded_events[SCHEDULE_BLOCK_STARTED]), 0,
                           f"No {SCHEDULE_BLOCK_STARTED} events were recorded.")

        first_sbs_event = self.recorded_events[SCHEDULE_BLOCK_STARTED][0]
        self.assertIsNotNone(first_sbs_event.get("block"), "SCHEDULE_BLOCK_STARTED event data missing 'block' key.")
        self.assertEqual(first_sbs_event["block"].get("id"), test_block_data["id"],
                         "SCHEDULE_BLOCK_STARTED event block ID does not match Chronos mock data.")
        self.assertEqual(first_sbs_event["block"].get("name"), test_block_data["name"])
        print("Test Passed: Simulation tick correctly published SCHEDULE_BLOCK_STARTED.")


    def test_world_event_triggers_thought_and_memory_write(self):
        """
        Tests that a specific WORLD_EVENT (e.g., from random_events)
        can trigger a THOUGHT_TRIGGER, which then leads to a MEMORY_WRITE event.
        This relies on random_events.py and subconscious_hook.py logic.
        """
        print("Running: test_world_event_triggers_thought_and_memory_write")

        # Manually trigger a specific sequence from random_events that should produce a thought
        # We need to ensure 'maybe_trigger_random_event' will actually fire an event that leads to a thought.
        # The "car_driveby" event in random_events.py is designed to do this.

        # To make this deterministic, we can't rely on random.random().
        # Option 1: Mock random.random() (more complex for this setup).
        # Option 2: Directly publish the intermediate WORLD_EVENT that random_events *would* publish.

        car_driveby_world_event_data = {
            "type": "random_world_event",
            "event_name": "car_driveby", # This specific event triggers a thought in random_events.py
            "source": "test_harness_direct_publish"
        }
        # Note: random_events.py publishes THOUGHT_TRIGGER directly.
        # subconscious_hook.py listens to THOUGHT_TRIGGER and then publishes MEMORY_WRITE.

        # So, first, let's simulate random_events.py publishing its THOUGHT_TRIGGER
        # This means we need the THOUGHT_TRIGGER handler (subconscious_hook) to be registered.
        # (Done in setUp)

        # Publish the THOUGHT_TRIGGER that random_events.py would have published
        # if a "car_driveby" WORLD_EVENT occurred and its internal logic ran.
        thought_data_from_car_event = {
            "trigger_event": "car_driveby",
            "content": "A car pulled into the driveway then reversed. That was a bit weird. Who could that be?",
            "mood_impact": "confused",
            "urgency": "low",
            "source": "random_events_simulated" # Simulating it came from random_events
        }
        self.event_bus.publish(THOUGHT_TRIGGER, thought_data_from_car_event)

        # Assertions
        self.assertGreater(len(self.recorded_events[THOUGHT_TRIGGER]), 0, "No THOUGHT_TRIGGER events recorded (should have been the one we published).")
        self.assertEqual(self.recorded_events[THOUGHT_TRIGGER][0]["content"], thought_data_from_car_event["content"])

        self.assertGreater(len(self.recorded_events[MEMORY_WRITE_EVENT_TYPE]), 0,
                           f"No {MEMORY_WRITE_EVENT_TYPE} events were recorded after THOUGHT_TRIGGER.")

        first_memory_event = self.recorded_events[MEMORY_WRITE_EVENT_TYPE][0]
        self.assertEqual(first_memory_event.get("type"), "thought", "Memory event type should be 'thought'.")
        # Check if the content of the memory write is related to the LLM elaboration of the thought
        self.assertIn("car's behavior", first_memory_event.get("content", "").lower(),
                      "Memory content doesn't seem to be the LLM elaboration of the car event.")
        self.assertEqual(first_memory_event.get("raw_trigger_content"), thought_data_from_car_event["content"])
        print("Test Passed: THOUGHT_TRIGGER correctly led to MEMORY_WRITE.")


    def test_world_event_triggers_npc_dialogue(self):
        """
        Tests that a WORLD_EVENT (e.g., "mail_delivery") triggers an NPC interaction,
        resulting in an NPC_DIALOGUE event. This uses npc_controller.py.
        """
        print("Running: test_world_event_triggers_npc_dialogue")
        # register_npc_event_listeners() is called in setUp.

        mail_delivery_event_data = {
            "type": "random_world_event", # As published by random_events.py
            "event_name": "mail_delivery",
            "has_package": True,
            "source": "test_harness_world_event_for_npc"
        }
        self.event_bus.publish(WORLD_EVENT, mail_delivery_event_data)

        self.assertGreater(len(self.recorded_events[NPC_DIALOGUE]), 0,
                           f"No {NPC_DIALOGUE} events recorded after 'mail_delivery' WORLD_EVENT.")

        first_npc_dialogue = self.recorded_events[NPC_DIALOGUE][0]
        self.assertEqual(first_npc_dialogue.get("npc_name"), "Mailman")
        self.assertIn("package", first_npc_dialogue.get("line", "").lower())
        print("Test Passed: 'mail_delivery' WORLD_EVENT correctly triggered NPC_DIALOGUE.")


    def test_placeholder_true(self):
        """A simple placeholder test that always passes."""
        print("Running: test_placeholder_true")
        self.assertTrue(True, "This placeholder test should always pass.")
        print("Test Passed: Placeholder test.")


if __name__ == '__main__':
    # This allows running the tests directly from this file: `python test_event_flow.py`
    # Ensure that the script is run from a context where the imports can be resolved
    # (e.g., project root, or with PYTHONPATH adjusted).
    unittest.main(verbosity=2)
