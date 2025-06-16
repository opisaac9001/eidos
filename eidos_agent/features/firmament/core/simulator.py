# eidos_agent/features/firmament/core/simulator.py

# Import EventBus and relevant event types
from .event_bus import EventBus
from .event_types import SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED # Added SCHEDULE_BLOCK_ENDED

# Import the actual get_current_block from chronos_adapter
# This makes the simulator dependent on the integrations layer.
try:
    from ..integrations.chronos_adapter import get_current_block
    # Import the testing utility from chronos_adapter for the __main__ block
    from ..integrations.chronos_adapter import _set_current_block_for_testing
except ImportError: # pragma: no cover
    print("CRITICAL: Could not import from chronos_adapter. Simulator will not function correctly.")
    # Define placeholders if import fails, to allow parsing but highlight issues.
    def get_current_block():
        print("Warning: Using dummy get_current_block due to ImportError.")
        return {"id": "dummy_block_import_error", "name": "Dummy Block", "type": "error"}
    def _set_current_block_for_testing(data=None): # type: ignore
        print("Warning: Dummy _set_current_block_for_testing due to ImportError.")
        pass


# Module-level variable to store the data of the currently active schedule block
# Its 'id' field is primarily used for comparison.
_current_active_block_data: dict | None = None

def run_simulation_tick():
    """
    Runs a single tick of the simulation.
    Fetches the current schedule block from Chronos, compares it with the previously
    active block, and publishes SCHEDULE_BLOCK_ENDED and/or SCHEDULE_BLOCK_STARTED
    events if the block has changed.
    """
    global _current_active_block_data

    # print(f"Simulator: Tick. Prev active block ID: {_current_active_block_data.get('id') if _current_active_block_data else 'None'}")

    new_block_data = get_current_block() # Uses the imported chronos_adapter function

    # Validate the structure of the new_block_data. Minimally, it needs an 'id'.
    if not isinstance(new_block_data, dict) or not new_block_data.get("id"):
        # print(f"Simulator: Invalid or missing block data from Chronos adapter (received: {new_block_data}).")
        # If there was an active block, and now the new block data is invalid/None,
        # it implies the previously active block might have ended without a new one starting.
        if _current_active_block_data:
            # print(f"Simulator: Current block data from Chronos is invalid/None. Ending previous block '{_current_active_block_data.get('id')}'.")
            EventBus.instance().publish(SCHEDULE_BLOCK_ENDED, {"block": _current_active_block_data, "reason": "new_block_data_invalid_or_none"})
            _current_active_block_data = None # Clear current block as its status is unknown
        return

    new_block_id = new_block_data.get("id") # Already checked new_block_data.get("id") is not None
    previous_block_id = _current_active_block_data.get("id") if _current_active_block_data else None

    if new_block_id != previous_block_id:
        # print(f"Simulator: Block change detected. New ID: {new_block_id}, Previous ID: {previous_block_id}")
        if _current_active_block_data: # If there was a previous block active
            # print(f"Simulator: Publishing {SCHEDULE_BLOCK_ENDED} for old block: ID {_current_active_block_data.get('id')}, Name '{_current_active_block_data.get('name', 'N/A')}'")
            EventBus.instance().publish(SCHEDULE_BLOCK_ENDED, {"block": _current_active_block_data, "reason": "block_changed"})

        # print(f"Simulator: Publishing {SCHEDULE_BLOCK_STARTED} for new block: ID {new_block_id}, Name '{new_block_data.get('name', 'N/A')}'")
        EventBus.instance().publish(SCHEDULE_BLOCK_STARTED, {"block": new_block_data})
        _current_active_block_data = new_block_data # Update the current active block
    # else:
        # print(f"Simulator: Block {new_block_id} is the same as previous. No start/end events needed.")
        # Optionally, publish a SCHEDULE_BLOCK_CONTINUING event here if needed for some logic
        pass


if __name__ == '__main__':
    # Test setup
    _test_events_captured = [] # Stores {"type": event_type, "data": data_arg}
    def test_event_handler(event_type_arg, data_arg): # Renamed for clarity
        block_info = data_arg.get('block', {})
        print(f"    [TestEventHandler] Event: {event_type_arg}, "
              f"Block ID: {block_info.get('id', 'N/A')}, "
              f"Block Name: {block_info.get('name', 'N/A')}, "
              f"Reason: {data_arg.get('reason', 'N/A')}")
        _test_events_captured.append({"type": event_type_arg, "data": data_arg})

    # Reset and get a fresh EventBus instance for testing
    if hasattr(EventBus, '_instance'): # Check if singleton attribute exists
        EventBus._instance = None # Reset singleton
    test_bus = EventBus.instance()
    # Using a factory to ensure event_type_arg is captured correctly by the lambda
    def create_handler_for_test(event_type_to_capture):
        return lambda data: test_event_handler(event_type_to_capture, data)

    test_bus.subscribe(SCHEDULE_BLOCK_STARTED, create_handler_for_test(SCHEDULE_BLOCK_STARTED))
    test_bus.subscribe(SCHEDULE_BLOCK_ENDED, create_handler_for_test(SCHEDULE_BLOCK_ENDED))

    print("--- Testing Simulator run_simulation_tick() with block transitions ---")

    # --- Tick 1: First block (e.g., Morning Routine) ---
    _current_active_block_data = None # Reset simulator's internal state for test consistency
    _test_events_captured.clear()
    block1_data = {"id": "block_morning_001", "name": "Morning Routine", "type": "routine"}
    _set_current_block_for_testing(block1_data) # Configure chronos_adapter mock
    print("\nTick 1: Expect SCHEDULE_BLOCK_STARTED for Morning Routine")
    run_simulation_tick()
    assert len(_test_events_captured) == 1, f"Tick 1: Expected 1 event, got {len(_test_events_captured)}"
    assert _test_events_captured[0]["type"] == SCHEDULE_BLOCK_STARTED, "Tick 1: Event should be SCHEDULE_BLOCK_STARTED"
    assert _test_events_captured[0]["data"]["block"]["id"] == "block_morning_001", "Tick 1: Incorrect block ID"
    print("Tick 1: Correctly started 'Morning Routine'.")

    # --- Tick 2: Same block, no new events expected ---
    _test_events_captured.clear()
    # chronos_adapter still returns block1_data (no change to _set_current_block_for_testing)
    print("\nTick 2: Expect no new start/end events (Morning Routine continues)")
    run_simulation_tick()
    assert len(_test_events_captured) == 0, f"Tick 2: Expected 0 events for same block, got {len(_test_events_captured)}"
    print("Tick 2: Correctly no new events for same block.")

    # --- Tick 3: New block (e.g., Work Focus) ---
    _test_events_captured.clear()
    block2_data = {"id": "block_work_002", "name": "Work Focus Session", "type": "work"}
    _set_current_block_for_testing(block2_data)
    print("\nTick 3: Expect ENDED for Morning Routine, STARTED for Work Focus")
    run_simulation_tick()
    assert len(_test_events_captured) == 2, f"Tick 3: Expected 2 events, got {len(_test_events_captured)}"
    assert _test_events_captured[0]["type"] == SCHEDULE_BLOCK_ENDED, "Tick 3: First event should be SCHEDULE_BLOCK_ENDED"
    assert _test_events_captured[0]["data"]["block"]["id"] == "block_morning_001", "Tick 3: Ended wrong block"
    assert _test_events_captured[0]["data"]["reason"] == "block_changed", "Tick 3: Incorrect reason for block end"
    assert _test_events_captured[1]["type"] == SCHEDULE_BLOCK_STARTED, "Tick 3: Second event should be SCHEDULE_BLOCK_STARTED"
    assert _test_events_captured[1]["data"]["block"]["id"] == "block_work_002", "Tick 3: Started wrong block"
    print("Tick 3: Correctly transitioned from 'Morning Routine' to 'Work Focus Session'.")

    # --- Tick 4: Chronos returns invalid data (None) ---
    _test_events_captured.clear()
    _set_current_block_for_testing(None) # Simulate Chronos returning None
    print("\nTick 4: Expect ENDED for Work Focus (due to invalid new block), no new STARTED")
    run_simulation_tick()
    assert len(_test_events_captured) == 1, f"Tick 4: Expected 1 event (ended), got {len(_test_events_captured)}"
    assert _test_events_captured[0]["type"] == SCHEDULE_BLOCK_ENDED, "Tick 4: Event should be SCHEDULE_BLOCK_ENDED"
    assert _test_events_captured[0]["data"]["block"]["id"] == "block_work_002", "Tick 4: Ended wrong block"
    assert _test_events_captured[0]["data"]["reason"] == "new_block_data_invalid_or_none", "Tick 4: Incorrect reason for block end"
    assert _current_active_block_data is None, "Tick 4: _current_active_block_data should be None after invalid new block"
    print("Tick 4: Correctly ended 'Work Focus' when Chronos returned invalid data.")

    # --- Tick 5: Chronos returns a new block after being None ---
    _test_events_captured.clear()
    block3_data = {"id": "block_evening_003", "name": "Evening Relaxation", "type": "leisure"}
    _set_current_block_for_testing(block3_data)
    print("\nTick 5: Expect STARTED for Evening Relaxation (no previous block was active)")
    run_simulation_tick()
    assert len(_test_events_captured) == 1, f"Tick 5: Expected 1 event, got {len(_test_events_captured)}"
    assert _test_events_captured[0]["type"] == SCHEDULE_BLOCK_STARTED, "Tick 5: Event should be SCHEDULE_BLOCK_STARTED"
    assert _test_events_captured[0]["data"]["block"]["id"] == "block_evening_003", "Tick 5: Started wrong block"
    assert _current_active_block_data["id"] == "block_evening_003", "Tick 5: _current_active_block_data not updated"
    print("Tick 5: Correctly started 'Evening Relaxation' after a period of no valid block.")

    # --- Tick 6: Chronos returns invalid data (empty dict) ---
    _test_events_captured.clear()
    _set_current_block_for_testing({}) # Simulate Chronos returning {}
    print("\nTick 6: Expect ENDED for Evening Relaxation (due to invalid new block), no new STARTED")
    run_simulation_tick()
    assert len(_test_events_captured) == 1, f"Tick 6: Expected 1 event (ended), got {len(_test_events_captured)}"
    assert _test_events_captured[0]["type"] == SCHEDULE_BLOCK_ENDED, "Tick 6: Event should be SCHEDULE_BLOCK_ENDED"
    assert _test_events_captured[0]["data"]["block"]["id"] == "block_evening_003", "Tick 6: Ended wrong block"
    assert _test_events_captured[0]["data"]["reason"] == "new_block_data_invalid_or_none", "Tick 6: Incorrect reason for block end"
    assert _current_active_block_data is None, "Tick 6: _current_active_block_data should be None after invalid new block"
    print("Tick 6: Correctly ended 'Evening Relaxation' when Chronos returned empty dict.")


    # Final reset of chronos_adapter mock and simulator state
    _set_current_block_for_testing(None)
    _current_active_block_data = None
    print("\n--- Simulator testing finished ---")
