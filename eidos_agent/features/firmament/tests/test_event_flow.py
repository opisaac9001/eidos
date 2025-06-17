# eidos_agent/features/firmament/tests/test_event_flow.py

import unittest
from collections import defaultdict
from unittest.mock import patch

# Attempt to import necessary modules from Firmament.
try:
    from ..core.event_bus import EventBus
    from ..core import event_types as fevent_types
    from ..core.simulator import run_simulation_tick
    import eidos_agent.features.firmament.core.simulator as sim_module
    from ..integrations.subconscious_hook import handle_thought_trigger, register_thought_trigger_handler
    from ..integrations.chronos_adapter import _set_current_block_for_testing
    from ..core.event_handlers.impulse import handle_impulse, EVENT_MEMORY_WRITE, EVENT_REQUEST_FOOD_PREP, EVENT_LOGOS_RESEARCH_REQUEST
    from ..core.event_handlers.schedule import register_schedule_event_handlers
    from ..integrations.oneiros_adapter import OneirosAdapter, register_oneiros_event_handlers, EVENT_ONEIROS_START_DREAM
    # New imports for random event tests
    from ..core.event_handlers.random_events import maybe_trigger_random_event, register_world_event_logging_handler, EVENT_POOL

except ImportError as e: # pragma: no cover
    print(f"ImportError in test_event_flow.py: {e}.")
    # Dummy definitions
    class EventBus: _instance = None; _subscribers = defaultdict(list); @classmethod def instance(cls): return cls() if not cls._instance else cls._instance; def subscribe(self, et, h): pass; def publish(self, et, d): print(f"DummyEventBus: Published {et} with {d}") # type: ignore
    class fevent_types: THOUGHT_TRIGGER, WORLD_EVENT, SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, NPC_DIALOGUE, IMPULSE, SLEEP_REQUESTED = "dummy.tt", "dummy.we", "dummy.sbs", "dummy.sbe", "dummy.nd", "dummy.imp", "dummy.sr" # type: ignore
    EVENT_MEMORY_WRITE, EVENT_REQUEST_FOOD_PREP, EVENT_LOGOS_RESEARCH_REQUEST, EVENT_ONEIROS_START_DREAM = "dummy.mw", "dummy.rfp", "dummy.lrr", "dummy.osds" # type: ignore
    def run_simulation_tick(): pass; class sim_module: _current_active_block_data = None # type: ignore
    def handle_thought_trigger(p): pass; def register_thought_trigger_handler(): pass # type: ignore
    def _set_current_block_for_testing(d=None): pass; def handle_impulse(d): pass # type: ignore
    def register_schedule_event_handlers(): pass; # type: ignore
    class OneirosAdapter: def generate_dream(self,c=None): return "dummy dream"; def handle_start_dream_request(self,d):pass # type: ignore
    def register_oneiros_event_handlers(a): pass # type: ignore
    def maybe_trigger_random_event(d=None): pass; register_world_event_logging_handler = lambda: None; EVENT_POOL = [] # type: ignore


class TestEventFlow(unittest.TestCase):

    def setUp(self):
        # print(f"\n--- Setting up for: {self._testMethodName} ---")
        if hasattr(EventBus, '_instance'): EventBus._instance = None
        self.event_bus = EventBus.instance()
        self.event_bus._subscribers = defaultdict(list)
        self.recorded_events = defaultdict(list)
        if hasattr(sim_module, '_current_active_block_data'):
            sim_module._current_active_block_data = None

        def generic_event_recorder(event_type_arg, data_arg):
            self.recorded_events[event_type_arg].append(data_arg)

        self.event_types_to_monitor = [
            fevent_types.THOUGHT_TRIGGER, fevent_types.WORLD_EVENT,
            fevent_types.SCHEDULE_BLOCK_STARTED, fevent_types.SCHEDULE_BLOCK_ENDED,
            EVENT_MEMORY_WRITE, fevent_types.NPC_DIALOGUE, fevent_types.IMPULSE,
            fevent_types.SLEEP_REQUESTED, EVENT_REQUEST_FOOD_PREP, EVENT_LOGOS_RESEARCH_REQUEST,
            EVENT_ONEIROS_START_DREAM
        ]
        for et in self.event_types_to_monitor:
            def create_handler(event_t_captured): return lambda data: generic_event_recorder(event_t_captured, data)
            self.event_bus.subscribe(et, create_handler(et))

        register_thought_trigger_handler()
        self.event_bus.subscribe(fevent_types.IMPULSE, handle_impulse)
        register_schedule_event_handlers()
        self.oneiros_adapter = OneirosAdapter(oneiros_config={"test_mode": True})
        register_oneiros_event_handlers(self.oneiros_adapter)
        register_world_event_logging_handler() # Register the new world event logger
        # print("Setup complete.")

    def tearDown(self):
        _set_current_block_for_testing(None)
        if hasattr(sim_module, '_current_active_block_data'):
             sim_module._current_active_block_data = None
        if hasattr(EventBus, '_instance') and EventBus._instance is not None:
            EventBus._instance._subscribers = defaultdict(list)
        # print(f"--- Torn down: {self._testMethodName} ---")

    # --- Existing tests (ensure they are present and pass) ---
    def test_simulation_tick_block_transition(self):
        print("Running: test_simulation_tick_block_transition")
        sim_module._current_active_block_data = None
        block_a_data = {"id": "blockA", "name": "Phase A", "type": "research"}
        _set_current_block_for_testing(block_a_data)
        run_simulation_tick()
        self.assertGreaterEqual(len(self.recorded_events.get(fevent_types.SCHEDULE_BLOCK_STARTED, [])), 1)
        sim_module._current_active_block_data = None # Explicit reset for test isolation
        print("Test Passed: Simulation tick block transitions (basic check).")


    def test_schedule_block_started_logs_to_memory(self):
        print("Running: test_schedule_block_started_logs_to_memory")
        test_block = {"id": "memlog_start_001", "name": "Logging Test Start", "type": "admin", "start_time_utc": "T09:00", "end_time_utc": "T10:00"}
        self.event_bus.publish(fevent_types.SCHEDULE_BLOCK_STARTED, {"block": test_block})
        self.assertTrue(any(e["type"] == "activity_log_start" for e in self.recorded_events.get(EVENT_MEMORY_WRITE, [])))
        print("Test Passed: Schedule block started logs to memory.")

    def test_schedule_block_ended_logs_to_memory(self):
        print("Running: test_schedule_block_ended_logs_to_memory")
        test_block = {"id": "memlog_end_002", "name": "Memory Logging Test End", "type": "review"}
        self.event_bus.publish(fevent_types.SCHEDULE_BLOCK_ENDED, {"block": test_block, "reason": "test_reason_completed"})
        self.assertTrue(any(e["type"] == "activity_log_end" for e in self.recorded_events.get(EVENT_MEMORY_WRITE, [])))
        print("Test Passed: Schedule block ended logs to memory.")


    @patch.object(OneirosAdapter, 'generate_dream', return_value="A mock dream about lucid coding.")
    def test_sleep_block_triggers_dream_sequence_and_logs_dream(self, mock_g):
        print("Running: test_sleep_block_triggers_dream_sequence_and_logs_dream")
        sim_module._current_active_block_data = None
        sleep_block = {"id": "sleep_test_001", "name": "Nightly Rest", "type": "sleep"}
        _set_current_block_for_testing(sleep_block)
        run_simulation_tick()
        self.assertIn(EVENT_ONEIROS_START_DREAM, self.recorded_events)
        self.assertTrue(any(e["type"] == "dream" for e in self.recorded_events.get(EVENT_MEMORY_WRITE, [])))
        mock_g.assert_called_once()
        sim_module._current_active_block_data = None
        print("Test Passed: Sleep block triggers dream and logs dream.")


    def test_subconscious_thought_triggers_impulse_and_sleep_action(self):
        print("Running: test_subconscious_thought_triggers_impulse_and_sleep_action")
        tired_payload = {"content": "I should sleep.", "mood": "exhausted", "urgency": "high", "impulse_type": "tired"}
        handle_thought_trigger(tired_payload)
        self.assertIn(fevent_types.IMPULSE, self.recorded_events)
        self.assertIn(fevent_types.SLEEP_REQUESTED, self.recorded_events)
        print("Test Passed: Subconscious thought triggers impulse and sleep action.")


    # --- New Tests for Random World Events ---
    @patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.random', return_value=0.5) # Ensures event does NOT fire (threshold is < 0.2)
    def test_maybe_trigger_random_event_does_not_fire(self, mock_random_val):
        print("Running: test_maybe_trigger_random_event_does_not_fire")
        maybe_trigger_random_event()
        self.assertEqual(len(self.recorded_events.get(fevent_types.WORLD_EVENT, [])), 0, "WORLD_EVENT should not have fired.")
        self.assertEqual(len(self.recorded_events.get(fevent_types.THOUGHT_TRIGGER, [])), 0, "THOUGHT_TRIGGER should not have fired.")
        # Also, no memory log for a world event should occur
        memory_writes = self.recorded_events.get(EVENT_MEMORY_WRITE, [])
        self.assertFalse(any(mw.get("type") == "observed_world_event" for mw in memory_writes), "No observed_world_event memory log should occur.")
        print("Test Passed: Random event correctly did not fire, no world event logged.")

    @patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.choice', return_value="sudden_gust_of_wind") # Event that doesn't trigger thought
    @patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.random', return_value=0.05) # Ensures event fires
    def test_maybe_trigger_random_event_fires_world_event_only_and_logs_it(self, mock_random_val, mock_random_choice):
        print("Running: test_maybe_trigger_random_event_fires_world_event_only_and_logs_it")
        # "sudden_gust_of_wind" is configured in random_events.py not to create a THOUGHT_TRIGGER directly.

        maybe_trigger_random_event()

        world_events = self.recorded_events.get(fevent_types.WORLD_EVENT, [])
        self.assertEqual(len(world_events), 1, "Exactly one WORLD_EVENT should have fired.")
        self.assertEqual(world_events[0]["event_name"], "sudden_gust_of_wind")

        thought_triggers = self.recorded_events.get(fevent_types.THOUGHT_TRIGGER, [])
        self.assertEqual(len(thought_triggers), 0, "Should not have triggered a THOUGHT_TRIGGER for 'sudden_gust_of_wind'.")

        # Check for memory log of the world event
        memory_writes = self.recorded_events.get(EVENT_MEMORY_WRITE, [])
        observed_event_logs = [mw for mw in memory_writes if mw.get("type") == "observed_world_event"]
        self.assertEqual(len(observed_event_logs), 1, "Expected one 'observed_world_event' memory entry.")
        self.assertIn("sudden_gust_of_wind", observed_event_logs[0]["content"])
        print("Test Passed: Random event fired WORLD_EVENT only and it was logged.")

    @patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.choice', return_value="phone_buzzes_on_table") # Event that DOES trigger thought
    @patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.random', return_value=0.05) # Ensures event fires
    def test_maybe_trigger_random_event_fires_world_event_and_thought_and_logs_world_event(self, mock_random_val, mock_random_choice):
        print("Running: test_maybe_trigger_random_event_fires_world_event_and_thought_and_logs_world_event")
        maybe_trigger_random_event()

        world_events = self.recorded_events.get(fevent_types.WORLD_EVENT, [])
        self.assertEqual(len(world_events), 1, "Exactly one WORLD_EVENT should have fired.")
        self.assertEqual(world_events[0]["event_name"], "phone_buzzes_on_table")

        thought_triggers = self.recorded_events.get(fevent_types.THOUGHT_TRIGGER, [])
        self.assertEqual(len(thought_triggers), 1, "Exactly one THOUGHT_TRIGGER should have fired.")
        self.assertEqual(thought_triggers[0]["trigger_event_name"], "phone_buzzes_on_table")
        self.assertIn("phone just buzzed", thought_triggers[0]["content"].lower())

        # Check for memory log of the world event
        memory_writes = self.recorded_events.get(EVENT_MEMORY_WRITE, [])
        observed_event_logs = [mw for mw in memory_writes if mw.get("type") == "observed_world_event"]
        self.assertEqual(len(observed_event_logs), 1, "Expected one 'observed_world_event' memory entry for the world event itself.")
        self.assertIn("phone_buzzes_on_table", observed_event_logs[0]["content"])
        # Note: The THOUGHT_TRIGGER will also cause a memory write via subconscious_hook, so more than one memory_write event is expected overall.
        self.assertGreaterEqual(len(memory_writes), 2, "Expected at least two memory_writes (one for world event, one for thought).")
        print("Test Passed: Random event fired WORLD_EVENT, THOUGHT_TRIGGER, and world event was logged.")

    def test_handle_world_event_logging_creates_memory_entry_directly(self): # Renamed for clarity
        print("Running: test_handle_world_event_logging_creates_memory_entry_directly")
        world_event_data = {
            "event_name": "direct_log_test_event",
            "source": "test_suite_direct_publish_for_logging",
            "timestamp_event_creation_utc": "2023-01-01T00:00:00Z"
        }
        # Directly publish WORLD_EVENT to specifically test the handle_world_event_logging handler
        self.event_bus.publish(fevent_types.WORLD_EVENT, world_event_data)

        memory_writes = self.recorded_events.get(EVENT_MEMORY_WRITE, [])
        observed_event_logs = [
            mw for mw in memory_writes
            if mw.get("type") == "observed_world_event" and
               mw["metadata"].get("original_world_event_name") == "direct_log_test_event"
        ]
        self.assertEqual(len(observed_event_logs), 1, "Expected one 'observed_world_event' memory entry from direct publish.")
        self.assertIn("Pathos observed: direct_log_test_event", observed_event_logs[0]["content"])
        self.assertEqual(observed_event_logs[0]["metadata"]["original_world_event_source"], "test_suite_direct_publish_for_logging")
        print("Test Passed: Direct world event logging correctly created memory entry.")


if __name__ == '__main__':
    unittest.main(verbosity=2)
