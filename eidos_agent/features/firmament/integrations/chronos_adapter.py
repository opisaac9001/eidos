# eidos_agent/features/firmament/integrations/chronos_adapter.py

# This module serves as an adapter to interface with the Chronos schedule engine.
# It will be responsible for fetching schedule information, such as current
# or upcoming blocks, and potentially for triggering or reacting to schedule changes.

# In a real system, this might involve API calls, database queries, or direct library usage
# to interact with the Chronos component.

_current_block_override = None # For testing purposes

def get_current_block() -> dict:
    """
    Fetches the current schedule block from the Chronos schedule engine.

    This is a placeholder implementation. In a real scenario, this function
    would query Chronos to get the currently active scheduled block for Pathos.
    The structure of the returned dictionary should be what Firmament's
    core logic (e.g., the simulator) expects.
    """
    global _current_block_override
    if _current_block_override:
        print("ChronosAdapter: get_current_block() called (returning overridden block for testing)")
        return _current_block_override

    # print("ChronosAdapter: get_current_block() called (placeholder)")
    # Simulate returning a schedule block.
    # The details here (id, type, name, times, etc.) are examples.
    # The actual fields will depend on what Chronos provides and what Firmament needs.
    return {
        "id": "chronos_block_001",
        "type": "learning",  # Example types: work, sleep, leisure, learning, chore, etc.
        "name": "Deep Dive into Python Async",
        "start_time_utc": "2023-10-27T14:00:00Z", # ISO 8601 format for UTC time
        "end_time_utc": "2023-10-27T16:00:00Z",   # ISO 8601 format for UTC time
        "description": "Studying advanced concepts in Python's asyncio library.",
        "location_hint": "study_desk", # Optional: suggestion for where this block occurs
        "associated_tasks": ["task_read_docs", "task_code_examples"] # Optional
    }

# --- Other potential Chronos interactions (placeholders) ---

def get_upcoming_blocks(count: int = 3) -> list:
    """
    Placeholder to fetch a list of upcoming schedule blocks.
    """
    print(f"ChronosAdapter: get_upcoming_blocks(count={count}) called (placeholder)")
    # Simulate returning a list of blocks
    upcoming = []
    for i in range(count):
        upcoming.append({
            "id": f"chronos_block_upcoming_00{i+2}",
            "type": "leisure" if i % 2 == 0 else "work",
            "name": f"Upcoming Block {i+1}",
            "start_time_utc": f"2023-10-27T{16+i}:00:00Z",
            "end_time_utc": f"2023-10-27T{17+i}:00:00Z",
        })
    return upcoming

def on_schedule_updated(handler_callback: callable):
    """
    Placeholder to register a callback for when the schedule is updated in Chronos.
    This would be used if Chronos supports a push mechanism for updates.
    """
    print(f"ChronosAdapter: on_schedule_updated registered callback {handler_callback.__name__} (placeholder)")
    # In a real system, this might add the callback to a list of listeners
    # that Chronos invokes when changes occur.
    pass

# --- Test Utilities ---
def _set_current_block_for_testing(block_data: dict = None):
    """
    Allows tests to override the block returned by get_current_block.
    Pass None to reset to default behavior.
    """
    global _current_block_override
    _current_block_override = block_data
    if block_data:
        print(f"ChronosAdapter Test Util: Current block is NOW OVERRIDDEN for get_current_block().")
    else:
        print(f"ChronosAdapter Test Util: Current block override REMOVED for get_current_block().")


if __name__ == '__main__':
    print("--- Testing Chronos Adapter ---")

    print("\n1. Default get_current_block():")
    current_block_default = get_current_block()
    print("   Current Schedule Block (from Chronos Adapter placeholder):")
    for key, value in current_block_default.items():
        print(f"     {key}: {value}")

    print("\n2. Overriding current block for testing:")
    test_override_block = {
        "id": "test_block_override_789",
        "type": "testing",
        "name": "Chronos Adapter Test Block",
        "start_time_utc": "2023-10-27T10:00:00Z",
        "end_time_utc": "2023-10-27T10:30:00Z",
        "details": "This block is returned due to an override for testing."
    }
    _set_current_block_for_testing(test_override_block)
    current_block_overridden = get_current_block()
    print("   Current Schedule Block (Overridden for Test):")
    for key, value in current_block_overridden.items():
        print(f"     {key}: {value}")
    assert current_block_overridden["id"] == "test_block_override_789"
    _set_current_block_for_testing(None) # Reset override

    print("\n3. Default get_upcoming_blocks():")
    upcoming = get_upcoming_blocks(2)
    print("   Upcoming Schedule Blocks (from Chronos Adapter placeholder):")
    for i, block in enumerate(upcoming):
        print(f"     Block {i+1}: {block.get('name')} ({block.get('type')})")

    print("\n4. Registering a dummy schedule update handler:")
    def my_dummy_handler(schedule_data): print(f"my_dummy_handler called with {schedule_data}")
    on_schedule_updated(my_dummy_handler)

    # Example of how simulator.py might use this (requires EventBus and event types)
    # print("\n--- Simulating Firmament Simulator Usage ---")
    # try:
    #     from ..core.event_bus import EventBus
    #     from ..core.event_types import SCHEDULE_BLOCK_STARTED
    #     block_for_simulator = get_current_block()
    #     EventBus.instance().publish(SCHEDULE_BLOCK_STARTED, {"block": block_for_simulator, "source": "chronos_adapter_test"})
    #     print("Successfully published SCHEDULE_BLOCK_STARTED event using current block.")
    # except ImportError:
    #     print("Could not run simulator usage example due to ImportError (core modules not found from this context).")
    # except Exception as e:
    #     print(f"Error during simulator usage example: {e}")

    print("\n--- Chronos Adapter testing finished ---")
