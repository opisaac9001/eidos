# eidos_agent/features/firmament/core/event_handlers/schedule.py

from ..event_bus import EventBus
from ..event_types import SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED
from datetime import datetime, timezone # For timestamp in memory log

# Define event type strings used by this handler
# These could be moved to a central event_types.py if they are published by other modules too,
# or if other modules need to subscribe to them. For now, local definition is fine if
# these are primarily conceptual events published *by* this handler for other systems to consume.
EVENT_MEMORY_WRITE = "memory.write" # Assuming this is a globally known event type for memory system
EVENT_ONEIROS_START_DREAM = "oneiros.start_dream_sequence" # For Oneiros dream module

def handle_schedule_block_started(data: dict):
    """Handles the SCHEDULE_BLOCK_STARTED event."""
    block_data = data.get("block")
    if not isinstance(block_data, dict):
        # print(f"ScheduleHandler Error: Invalid or missing block data in SCHEDULE_BLOCK_STARTED event: {data}")
        return

    block_id = block_data.get("id", "UnknownID")
    block_name = block_data.get("name", "Unknown Activity")
    block_type = block_data.get("type", "unknown")
    # Use _utc versions if available, otherwise fallback to non-suffixed, then N/A
    start_time = block_data.get("start_time_utc", block_data.get("start_time", "N/A"))
    end_time = block_data.get("end_time_utc", block_data.get("end_time", "N/A"))

    # print(f"ScheduleHandler: Block '{block_name}' (Type: {block_type}, ID: {block_id}) started. Scheduled: {start_time} to {end_time}.")

    # Log to memory that the activity has started
    memory_content = f"Pathos started activity: '{block_name}' (Type: {block_type}). Scheduled from {start_time} to {end_time}."
    memory_payload = {
        "type": "activity_log_start", # More specific type for memory
        "content": memory_content,
        "metadata": {
            "event_source_type": SCHEDULE_BLOCK_STARTED, # Original event that triggered this log
            "block_id": block_id,
            "block_name": block_name,
            "block_type": block_type,
            "scheduled_start_time": start_time,
            "scheduled_end_time": end_time,
            "log_timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
    }
    EventBus.instance().publish(EVENT_MEMORY_WRITE, memory_payload)

    # If it's a sleep block, also trigger the Oneiros dream sequence
    if block_type.lower() == 'sleep':
        # print(f"ScheduleHandler: Sleep block '{block_name}' detected. Publishing {EVENT_ONEIROS_START_DREAM}.")
        oneiros_payload = {
            "reason": "scheduled_sleep_block_started",
            "block_data": block_data, # Pass the full block data for context to Oneiros
            "trigger_timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
        EventBus.instance().publish(EVENT_ONEIROS_START_DREAM, oneiros_payload)

def handle_schedule_block_ended(data: dict):
    """Handles the SCHEDULE_BLOCK_ENDED event."""
    block_data = data.get("block")
    if not isinstance(block_data, dict):
        # print(f"ScheduleHandler Error: Invalid or missing block data in SCHEDULE_BLOCK_ENDED event: {data}")
        return

    block_id = block_data.get("id", "UnknownID")
    block_name = block_data.get("name", "Unknown Activity")
    block_type = block_data.get("type", "unknown")
    reason = data.get("reason", "scheduled_completion") # Reason from simulator.py (e.g., "block_changed")

    # print(f"ScheduleHandler: Block '{block_name}' (Type: {block_type}, ID: {block_id}) ended. Reason: {reason}.")

    # Log to memory that the activity has ended
    memory_content = f"Pathos ended activity: '{block_name}' (Type: {block_type}). Reason: {reason}."
    memory_payload = {
        "type": "activity_log_end", # More specific type for memory
        "content": memory_content,
        "metadata": {
            "event_source_type": SCHEDULE_BLOCK_ENDED, # Original event
            "block_id": block_id,
            "block_name": block_name,
            "block_type": block_type,
            "reason_for_end": reason,
            "log_timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
    }
    EventBus.instance().publish(EVENT_MEMORY_WRITE, memory_payload)

def register_schedule_event_handlers():
    """Subscribes schedule event handlers to the EventBus."""
    event_bus = EventBus.instance()
    event_bus.subscribe(SCHEDULE_BLOCK_STARTED, handle_schedule_block_started)
    event_bus.subscribe(SCHEDULE_BLOCK_ENDED, handle_schedule_block_ended)
    # print("ScheduleHandler: Registered handlers for SCHEDULE_BLOCK_STARTED and SCHEDULE_BLOCK_ENDED.")


if __name__ == '__main__':
    from collections import defaultdict # Needed for MockEventBus if it clears subscribers

    # Basic test setup for schedule handlers
    _test_events_captured_schedule = [] # Using a unique name for the list
    def capture_event_for_schedule_test(event_type, data): # Unique function name
        print(f"    [CaptureScheduleTest] Event: {event_type}, Relevant Data: {str(data.get('content', data.get('reason', data)))[:100]}")
        _test_events_captured_schedule.append({"type": event_type, "data": data})

    # Mock EventBus for isolated testing
    class MockEventBusForSchedule(EventBus):
        def __init__(self):
            # super().__init__() # EventBus itself does not have subscribers in its __init__
            self._subscribers = defaultdict(list) # Initialize subscribers here
            print("MockEventBusForSchedule initialized.")

        def publish(self, event_type: str, data: dict):
            # print(f"MockEventBusForSchedule: Publishing {event_type}...")
            # Directly call capture_event for testing purposes to see what would be published
            capture_event_for_schedule_test(event_type, data)
            # Also call actual subscribers that were registered on this mock instance
            for handler in self._subscribers.get(event_type, []):
                handler(data)
            for handler in self._subscribers.get("*", []): # Wildcard listeners
                handler(event_type, data)


    # Monkey patch EventBus.instance() for this test
    original_event_bus_instance_method = EventBus.instance
    mock_bus_instance_schedule = MockEventBusForSchedule() # Unique instance name
    EventBus.instance = lambda: mock_bus_instance_schedule

    # Register handlers onto the mock bus instance
    register_schedule_event_handlers()

    print("\n--- Testing handle_schedule_block_started (Normal Block) ---")
    _test_events_captured_schedule.clear()
    normal_block_data = {
        "id": "block001", "name": "Work on Project X", "type": "work",
        "start_time_utc": "2023-01-01T09:00:00Z", "end_time_utc": "2023-01-01T17:00:00Z"
    }
    # Simulate the event that the handler would receive
    mock_bus_instance_schedule.publish(SCHEDULE_BLOCK_STARTED, {"block": normal_block_data})
    assert any(e["type"] == EVENT_MEMORY_WRITE and "Work on Project X" in e["data"]["content"] and "started activity" in e["data"]["content"] for e in _test_events_captured_schedule), "Memory log for normal block start missing."
    assert not any(e["type"] == EVENT_ONEIROS_START_DREAM for e in _test_events_captured_schedule), "Oneiros event should not fire for non-sleep block."

    print("\n--- Testing handle_schedule_block_started (Sleep Block) ---")
    _test_events_captured_schedule.clear()
    sleep_block_data = {
        "id": "block002", "name": "Nightly Sleep", "type": "sleep",
        "start_time_utc": "2023-01-01T22:00:00Z", "end_time_utc": "2023-01-02T06:00:00Z"
    }
    mock_bus_instance_schedule.publish(SCHEDULE_BLOCK_STARTED, {"block": sleep_block_data})
    assert any(e["type"] == EVENT_MEMORY_WRITE and "Nightly Sleep" in e["data"]["content"] and "started activity" in e["data"]["content"] for e in _test_events_captured_schedule), "Memory log for sleep block start missing."
    assert any(e["type"] == EVENT_ONEIROS_START_DREAM for e in _test_events_captured_schedule), "EVENT_ONEIROS_START_DREAM not published for sleep block."

    print("\n--- Testing handle_schedule_block_ended ---")
    _test_events_captured_schedule.clear()
    ended_block_data = {
        "id": "block001", "name": "Work on Project X", "type": "work"
    }
    mock_bus_instance_schedule.publish(SCHEDULE_BLOCK_ENDED, {"block": ended_block_data, "reason": "scheduled_completion"})
    assert any(e["type"] == EVENT_MEMORY_WRITE and "ended activity: 'Work on Project X'" in e["data"]["content"] for e in _test_events_captured_schedule), "Memory log for block end missing."

    # Restore original EventBus class method
    EventBus.instance = original_event_bus_instance_method
    print("\n--- Schedule Handler testing finished ---")
