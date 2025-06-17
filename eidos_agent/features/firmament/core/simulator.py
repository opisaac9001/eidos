# eidos_agent/features/firmament/core/simulator.py

from .event_bus import EventBus
from .event_types import SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED

try:
    from ..integrations.chronos_adapter import get_current_block
    from ..integrations.chronos_adapter import _set_current_block_for_testing # For __main__
except ImportError: # pragma: no cover
    print("CRITICAL: Could not import from chronos_adapter. Simulator will not function correctly.")
    def get_current_block(): return {"id": "dummy_block_import_error", "name": "Dummy Block", "type": "error"} # type: ignore
    def _set_current_block_for_testing(data=None): pass # type: ignore

# Import for random event triggering
try:
    from ..core.event_handlers.random_events import maybe_trigger_random_event
except ImportError: # pragma: no cover
    print("CRITICAL: Could not import from random_events. Simulator will not trigger random events.")
    def maybe_trigger_random_event(): # type: ignore
        print("Warning: Using dummy maybe_trigger_random_event due to ImportError.")
        pass


_current_active_block_data: dict | None = None

def run_simulation_tick():
    """
    Runs a single tick of the simulation.
    Handles schedule block transitions and may trigger random world events.
    """
    global _current_active_block_data

    # print(f"Simulator: Tick. Prev active block ID: {_current_active_block_data.get('id') if _current_active_block_data else 'None'}")

    # --- Schedule Block Transition Logic ---
    new_block_data = get_current_block()

    # Validate the structure of the new_block_data. Minimally, it needs an 'id'.
    if not isinstance(new_block_data, dict) or not new_block_data.get("id"):
        # print(f"Simulator: Invalid or missing block data from Chronos adapter (received: {new_block_data}).")
        if _current_active_block_data:
            # print(f"Simulator: Current block data from Chronos is invalid/None. Ending previous block '{_current_active_block_data.get('id')}'.")
            EventBus.instance().publish(SCHEDULE_BLOCK_ENDED, {"block": _current_active_block_data, "reason": "new_block_data_invalid_or_none"})
            _current_active_block_data = None
        # Even if block data is invalid, random events can still occur.
    else: # New block data is valid
        new_block_id = new_block_data.get("id")
        previous_block_id = _current_active_block_data.get("id") if _current_active_block_data else None

        if new_block_id != previous_block_id:
            # print(f"Simulator: Block change detected. New ID: {new_block_id}, Previous ID: {previous_block_id}")
            if _current_active_block_data:
                EventBus.instance().publish(SCHEDULE_BLOCK_ENDED, {"block": _current_active_block_data, "reason": "block_changed"})

            EventBus.instance().publish(SCHEDULE_BLOCK_STARTED, {"block": new_block_data})
            _current_active_block_data = new_block_data

    # --- Random World Event Triggering ---
    # This is called on every tick. maybe_trigger_random_event has its own internal probability logic.
    # print("Simulator: Considering random world event...") # Optional debug print
    if 'maybe_trigger_random_event' in globals() and callable(globals()['maybe_trigger_random_event']):
        maybe_trigger_random_event()
    # print("Simulator: Tick finished.")


if __name__ == '__main__':
    import unittest.mock # For patching random calls in test
    from collections import defaultdict # For EventBus mock subscribers

    # Test setup
    _test_events_captured = []
    def test_event_handler(event_type_arg, data_arg):
        # Simplified print for this combined test
        # print(f"    [TestEventHandler] Event: {event_type_arg}, Data: {str(data_arg)[:100]}")
        _test_events_captured.append({"type": event_type_arg, "data": data_arg})

    # Ensure EventBus is reset for testing
    if hasattr(EventBus, '_instance'):
        EventBus._instance = None
    test_bus = EventBus.instance()
    # Clear subscribers just in case, though new instance should be clean
    if hasattr(test_bus, '_subscribers'):
         test_bus._subscribers = defaultdict(list)


    def create_handler_for_test(event_type_to_capture):
        return lambda data: test_event_handler(event_type_to_capture, data)

    # Subscribe to events relevant for these tests
    test_bus.subscribe(SCHEDULE_BLOCK_STARTED, create_handler_for_test(SCHEDULE_BLOCK_STARTED))
    test_bus.subscribe(SCHEDULE_BLOCK_ENDED, create_handler_for_test(SCHEDULE_BLOCK_ENDED))

    # For random event part, need WORLD_EVENT and THOUGHT_TRIGGER
    # Assuming these are defined in .event_types correctly
    try:
        from .event_types import WORLD_EVENT, THOUGHT_TRIGGER
        test_bus.subscribe(WORLD_EVENT, create_handler_for_test(WORLD_EVENT))
        test_bus.subscribe(THOUGHT_TRIGGER, create_handler_for_test(THOUGHT_TRIGGER))
    except ImportError: # pragma: no cover
        print("Warning: Could not import WORLD_EVENT, THOUGHT_TRIGGER for __main__ test capture.")
        WORLD_EVENT, THOUGHT_TRIGGER = "dummy.world", "dummy.thought" # Define dummies if import fails

    # For memory writes resulting from thoughts (from subconscious_hook)
    try:
        from ..core.event_handlers.impulse import EVENT_MEMORY_WRITE
        test_bus.subscribe(EVENT_MEMORY_WRITE, create_handler_for_test(EVENT_MEMORY_WRITE))
    except ImportError: # pragma: no cover
        print("Warning: Could not import EVENT_MEMORY_WRITE for __main__ test capture.")
        EVENT_MEMORY_WRITE = "dummy.memory_write"


    # Register subconscious_hook.handle_thought_trigger to process THOUGHT_TRIGGER events
    # This is needed to see the memory.write events resulting from random thoughts
    try:
        from ..integrations.subconscious_hook import register_thought_trigger_handler
        if 'register_thought_trigger_handler' in globals() and callable(globals()['register_thought_trigger_handler']):
            register_thought_trigger_handler()
    except ImportError: # pragma: no cover
        print("Warning: Could not import/register subconscious_hook for __main__ test.")


    print("--- Testing Simulator run_simulation_tick() with schedule AND random events ---")
    _current_active_block_data = None # Reset global state for this test run

    # --- Tick 1: Start Block A, and force a random event ---
    _test_events_captured.clear()
    block1_data = {"id": "block_morning_001", "name": "Morning Routine", "type": "routine"}
    _set_current_block_for_testing(block1_data)
    print("\nTick 1 (Morning Routine start + specific random event 'phone_buzzes_on_table'):")

    # Patch random.random to ensure event triggers, and random.choice to pick a specific event
    with unittest.mock.patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.random', return_value=0.05) as mock_rand_val, \
         unittest.mock.patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.choice', side_effect=lambda pool: "phone_buzzes_on_table" if pool[0] == "car_driveby" else random.choice(pool)) as mock_rand_choice:
        run_simulation_tick()

    # Check for SCHEDULE_BLOCK_STARTED
    sbs_events = [e for e in _test_events_captured if e["type"] == SCHEDULE_BLOCK_STARTED]
    assert len(sbs_events) == 1, f"Tick 1: SCHEDULE_BLOCK_STARTED for Morning Routine missing. Events: {_test_events_captured}"
    assert sbs_events[0]["data"]["block"]["id"] == "block_morning_001"

    # Check for random event (phone_buzzes_on_table was chosen by mock)
    world_events = [e for e in _test_events_captured if e["type"] == WORLD_EVENT]
    assert len(world_events) == 1, f"Tick 1: WORLD_EVENT (phone_buzzes) missing. Events: {_test_events_captured}"
    assert world_events[0]["data"]["event_name"] == "phone_buzzes_on_table"

    thought_events = [e for e in _test_events_captured if e["type"] == THOUGHT_TRIGGER]
    assert len(thought_events) == 1, f"Tick 1: THOUGHT_TRIGGER for phone_buzzes missing. Events: {_test_events_captured}"
    assert "phone just buzzed" in thought_events[0]["data"]["content"].lower()
    print("Tick 1: Morning Routine started, 'phone_buzzes_on_table' random event triggered with thought.")


    # --- Tick 2: Transition to Block B, and force NO random event ---
    _test_events_captured.clear()
    block2_data = {"id": "block_work_002", "name": "Work Focus Session", "type": "work"}
    _set_current_block_for_testing(block2_data)
    print("\nTick 2 (Work Focus start + NO random event):")
    # This time, let random event not fire by making random.random return > probability
    with unittest.mock.patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.random', return_value=0.5) as mock_rand_val:
        run_simulation_tick()

    sbe_events = [e for e in _test_events_captured if e["type"] == SCHEDULE_BLOCK_ENDED]
    sbs_events = [e for e in _test_events_captured if e["type"] == SCHEDULE_BLOCK_STARTED]
    world_events = [e for e in _test_events_captured if e["type"] == WORLD_EVENT]

    assert len(sbe_events) == 1 and sbe_events[0]["data"]["block"]["id"] == "block_morning_001", f"Tick 2: Morning Routine ENDED event missing. Events: {_test_events_captured}"
    assert len(sbs_events) == 1 and sbs_events[0]["data"]["block"]["id"] == "block_work_002", f"Tick 2: Work Focus STARTED event missing. Events: {_test_events_captured}"
    assert len(world_events) == 0, f"Tick 2: WORLD_EVENT should NOT have been triggered. Events: {_test_events_captured}"
    print("Tick 2: Transitioned to Work Focus, no random event occurred as expected.")

    # Clean up global state for subsequent tests if any were part of a larger suite
    _set_current_block_for_testing(None)
    _current_active_block_data = None
    print("\n--- Simulator with random events testing finished ---")
