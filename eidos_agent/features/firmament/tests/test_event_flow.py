# eidos_agent/features/firmament/tests/test_event_flow.py

import unittest
from collections import defaultdict
from unittest.mock import patch # Added for mocking

# Attempt to import necessary modules from Firmament.
try:
    from ..core.event_bus import EventBus
    from ..core import event_types as fevent_types
    from ..core.simulator import run_simulation_tick
    # Import the actual global variable to reset it in tests
    import eidos_agent.features.firmament.core.simulator as sim_module
    from ..integrations.subconscious_hook import handle_thought_trigger, register_thought_trigger_handler
    from ..integrations.chronos_adapter import _set_current_block_for_testing
    from ..core.event_handlers.impulse import handle_impulse, EVENT_MEMORY_WRITE, EVENT_REQUEST_FOOD_PREP, EVENT_LOGOS_RESEARCH_REQUEST

    # New imports for this step
    from ..core.event_handlers.schedule import register_schedule_event_handlers
    from ..integrations.oneiros_adapter import OneirosAdapter, register_oneiros_event_handlers, EVENT_ONEIROS_START_DREAM

except ImportError as e: # pragma: no cover
    print(f"ImportError in test_event_flow.py: {e}. Some tests may fail or not run correctly.")
    # Dummy definitions
    class EventBus: _instance = None; _subscribers = defaultdict(list); @classmethod def instance(cls): return cls() if not cls._instance else cls._instance; def subscribe(self, et, h): pass; def publish(self, et, d): print(f"DummyEventBus: Published {et} with {d}") # type: ignore
    class fevent_types: THOUGHT_TRIGGER, WORLD_EVENT, SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, NPC_DIALOGUE, IMPULSE, SLEEP_REQUESTED = "dummy.tt", "dummy.we", "dummy.sbs", "dummy.sbe", "dummy.nd", "dummy.imp", "dummy.sr" # type: ignore
    EVENT_MEMORY_WRITE, EVENT_REQUEST_FOOD_PREP, EVENT_LOGOS_RESEARCH_REQUEST, EVENT_ONEIROS_START_DREAM = "dummy.mw", "dummy.rfp", "dummy.lrr", "dummy.osds" # type: ignore
    def run_simulation_tick(): pass; # type: ignore
    class sim_module: _current_active_block_data = None # type: ignore
    def handle_thought_trigger(p): pass; def register_thought_trigger_handler(): pass # type: ignore
    def _set_current_block_for_testing(d=None): pass; def handle_impulse(d): pass # type: ignore
    def register_schedule_event_handlers(): pass; # type: ignore
    class OneirosAdapter: def generate_dream(self,c=None): return "dummy dream"; def handle_start_dream_request(self,d):pass # type: ignore
    def register_oneiros_event_handlers(a): pass # type: ignore


class TestEventFlow(unittest.TestCase):

    def setUp(self):
        print(f"\n--- Setting up for: {self._testMethodName} ---")
        if hasattr(EventBus, '_instance'): EventBus._instance = None
        self.event_bus = EventBus.instance()
        self.event_bus._subscribers = defaultdict(list)

        self.recorded_events = defaultdict(list)

        # Reset simulator's active block state before each test
        sim_module._current_active_block_data = None


        def generic_event_recorder(event_type_arg, data_arg):
            # print(f"    [EventRecorded] Type: {event_type_arg}, Data: {str(data_arg)[:120]}...")
            self.recorded_events[event_type_arg].append(data_arg)

        self.event_types_to_monitor = [
            fevent_types.THOUGHT_TRIGGER, fevent_types.WORLD_EVENT,
            fevent_types.SCHEDULE_BLOCK_STARTED, fevent_types.SCHEDULE_BLOCK_ENDED,
            EVENT_MEMORY_WRITE, fevent_types.NPC_DIALOGUE, fevent_types.IMPULSE,
            fevent_types.SLEEP_REQUESTED, EVENT_REQUEST_FOOD_PREP, EVENT_LOGOS_RESEARCH_REQUEST,
            EVENT_ONEIROS_START_DREAM
        ]
        for et in self.event_types_to_monitor:
            def create_handler(event_t_captured):
                return lambda data: generic_event_recorder(event_t_captured, data)
            self.event_bus.subscribe(et, create_handler(et))

        # Register handlers from various modules
        register_thought_trigger_handler()
        self.event_bus.subscribe(fevent_types.IMPULSE, handle_impulse)
        register_schedule_event_handlers()

        # Instantiate OneirosAdapter and register its handlers
        # We create a new instance for each test to ensure isolation if adapter has state
        self.oneiros_adapter = OneirosAdapter(oneiros_config={"test_mode": True})
        register_oneiros_event_handlers(self.oneiros_adapter)

        print("Setup complete. EventBus ready and handlers registered.")

    def tearDown(self):
        _set_current_block_for_testing(None) # Reset Chronos adapter mock
        sim_module._current_active_block_data = None # Reset simulator state
        if hasattr(EventBus, '_instance') and EventBus._instance is not None:
            EventBus._instance._subscribers = defaultdict(list)
        print(f"--- Torn down: {self._testMethodName} ---")

    # --- Schedule Logic Tests ---
    def test_simulation_tick_block_transition(self):
        print("Running: test_simulation_tick_block_transition")
        # This test now relies on setUp to reset sim_module._current_active_block_data

        block_a_data = {"id": "blockA", "name": "Phase A", "type": "research"}
        block_b_data = {"id": "blockB", "name": "Phase B", "type": "writing"}

        # Tick 1: Start Block A
        _set_current_block_for_testing(block_a_data)
        run_simulation_tick()
        self.assertEqual(len(self.recorded_events.get(fevent_types.SCHEDULE_BLOCK_STARTED, [])), 1, "Tick 1 SBS count")
        self.assertEqual(self.recorded_events[fevent_types.SCHEDULE_BLOCK_STARTED][0]['block']['id'], "blockA", "Tick 1 SBS block ID")
        self.assertEqual(len(self.recorded_events.get(fevent_types.SCHEDULE_BLOCK_ENDED, [])), 0, "Tick 1 SBE count")
        self.recorded_events.clear()

        # Tick 2: Still Block A
        run_simulation_tick()
        self.assertEqual(len(self.recorded_events.get(fevent_types.SCHEDULE_BLOCK_STARTED, [])), 0, "Tick 2 SBS count")
        self.assertEqual(len(self.recorded_events.get(fevent_types.SCHEDULE_BLOCK_ENDED, [])), 0, "Tick 2 SBE count")
        self.recorded_events.clear()

        # Tick 3: Transition to Block B
        _set_current_block_for_testing(block_b_data)
        run_simulation_tick()
        self.assertEqual(len(self.recorded_events.get(fevent_types.SCHEDULE_BLOCK_ENDED, [])), 1, "Tick 3 SBE count")
        self.assertEqual(self.recorded_events[fevent_types.SCHEDULE_BLOCK_ENDED][0]['block']['id'], "blockA", "Tick 3 SBE block ID")
        self.assertEqual(len(self.recorded_events.get(fevent_types.SCHEDULE_BLOCK_STARTED, [])), 1, "Tick 3 SBS count")
        self.assertEqual(self.recorded_events[fevent_types.SCHEDULE_BLOCK_STARTED][0]['block']['id'], "blockB", "Tick 3 SBS block ID")
        print("Test Passed: Simulation tick block transitions.")

    def test_schedule_block_started_logs_to_memory(self):
        print("Running: test_schedule_block_started_logs_to_memory")
        test_block = {"id": "memlog_start_001", "name": "Memory Logging Test Start", "type": "admin",
                      "start_time_utc": "T09:00", "end_time_utc": "T10:00"}
        # Directly publish SCHEDULE_BLOCK_STARTED to test schedule_handler's reaction
        self.event_bus.publish(fevent_types.SCHEDULE_BLOCK_STARTED, {"block": test_block})

        memory_writes = self.recorded_events.get(EVENT_MEMORY_WRITE, [])
        self.assertTrue(
            any(evt_data.get("type") == "activity_log_start" and
                "Memory Logging Test Start" in evt_data.get("content", "")
                for evt_data in memory_writes),
            "Memory write for block start not found or content incorrect."
        )
        print("Test Passed: Schedule block started logs to memory.")

    def test_schedule_block_ended_logs_to_memory(self):
        print("Running: test_schedule_block_ended_logs_to_memory")
        test_block = {"id": "memlog_end_002", "name": "Memory Logging Test End", "type": "review"}
        self.event_bus.publish(fevent_types.SCHEDULE_BLOCK_ENDED, {"block": test_block, "reason": "test_reason_completed"})

        memory_writes = self.recorded_events.get(EVENT_MEMORY_WRITE, [])
        self.assertTrue(
            any(evt_data.get("type") == "activity_log_end" and
                "Memory Logging Test End" in evt_data.get("content", "") and
                "test_reason_completed" in evt_data.get("content", "") # Check reason is logged
                for evt_data in memory_writes),
            "Memory write for block end not found or content/reason incorrect."
        )
        print("Test Passed: Schedule block ended logs to memory.")

    # --- Sleep Block and Dream Flow Test ---
    @patch.object(OneirosAdapter, 'generate_dream', return_value="A mock dream about lucid coding.")
    def test_sleep_block_triggers_dream_sequence_and_logs_dream(self, mock_generate_dream_method):
        print("Running: test_sleep_block_triggers_dream_sequence_and_logs_dream")
        # Ensure simulator's internal state for current block is fresh for this test
        sim_module._current_active_block_data = None

        sleep_block_details = {
            "id": "sleep_dream_test_003", "name": "REM Sleep Cycle", "type": "sleep",
            "start_time_utc": "T23:00", "end_time_utc": "T01:00"
        }
        _set_current_block_for_testing(sleep_block_details)

        # This tick will trigger SCHEDULE_BLOCK_STARTED for the sleep_block.
        # The schedule_handler, listening to this, should then publish EVENT_ONEIROS_START_DREAM.
        # The oneiros_adapter, listening to that, should call generate_dream and publish EVENT_MEMORY_WRITE.
        run_simulation_tick()

        # 1. Assert SCHEDULE_BLOCK_STARTED for sleep_block was published by simulator
        sbs_events = self.recorded_events.get(fevent_types.SCHEDULE_BLOCK_STARTED, [])
        self.assertTrue(any(evt['block']['id'] == sleep_block_details["id"] for evt in sbs_events),
                        "SCHEDULE_BLOCK_STARTED for sleep block not found.")

        # 2. Assert EVENT_ONEIROS_START_DREAM was published by schedule_handler
        dream_trigger_events = self.recorded_events.get(EVENT_ONEIROS_START_DREAM, [])
        self.assertGreater(len(dream_trigger_events), 0, "EVENT_ONEIROS_START_DREAM not published by schedule_handler.")
        self.assertEqual(dream_trigger_events[0]['block_data']['id'], sleep_block_details["id"],
                         "Block ID in EVENT_ONEIROS_START_DREAM data mismatch.")

        # 3. Assert mocked OneirosAdapter.generate_dream was called by oneiros_adapter.handle_start_dream_request
        mock_generate_dream_method.assert_called_once()
        # Check the context passed to generate_dream
        call_context = mock_generate_dream_method.call_args[1]['context']
        self.assertEqual(call_context['id'], sleep_block_details['id'], "Context ID for generate_dream mismatch.")

        # 4. Assert EVENT_MEMORY_WRITE (type: "dream") was published by oneiros_adapter
        dream_memory_events = [
            e_data for e_data in self.recorded_events.get(EVENT_MEMORY_WRITE, [])
            if e_data.get("type") == "dream"
        ]
        self.assertGreater(len(dream_memory_events), 0, "No 'dream' type memory write event found.")
        self.assertEqual(dream_memory_events[0]["content"], "A mock dream about lucid coding.",
                         "Dream content in memory mismatch.")
        self.assertEqual(dream_memory_events[0]["metadata"]["sleep_block_id"], sleep_block_details["id"],
                         "Sleep block ID in dream memory metadata mismatch.")
        print("Test Passed: Sleep block correctly triggered dream sequence and dream logging.")

    # --- Existing Impulse Tests (abridged for focus, ensure they are still present) ---
    def test_subconscious_thought_triggers_impulse_and_sleep_action(self):
        print("Running: test_subconscious_thought_triggers_impulse_and_sleep_action (abridged)")
        tired_payload = {"content": "I'm feeling incredibly tired and should sleep.", "mood": "exhausted", "urgency": "high", "impulse_type": "tired"}
        handle_thought_trigger(tired_payload) # Directly call, as this is about subconscious_hook + impulse_handler
        self.assertIn(fevent_types.IMPULSE, self.recorded_events, "IMPULSE for tired not found.")
        self.assertIn(fevent_types.SLEEP_REQUESTED, self.recorded_events, "SLEEP_REQUESTED for tired not found.")
        # Ensure two memory writes: 1 for thought, 1 for action
        self.assertEqual(len(self.recorded_events.get(EVENT_MEMORY_WRITE, [])), 2, "Expected two memory writes for tired flow.")
        print("Test Passed: Tired impulse (abridged).")


if __name__ == '__main__':
    unittest.main(verbosity=2)
