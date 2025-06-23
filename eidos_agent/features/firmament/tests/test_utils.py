# eidos_agent/features/firmament/tests/test_utils.py
import unittest
from typing import Dict, List, Optional, Any

# Assuming EVENT_MEMORY_WRITE is consistently "memory.write"
# If it's an enum or constant from event_types, it should ideally be imported.
# For now, using the string directly as it's often done in handlers and tests.
DEFAULT_MEMORY_WRITE_EVENT_NAME = "memory.write"

def find_events(
    recorded_events: Dict[str, List[Dict[str, Any]]],
    event_type: str
) -> List[Dict[str, Any]]:
    """
    Retrieves all recorded events of a specific type.

    Args:
        recorded_events: The dictionary captured by the test's event recorder,
                         mapping event type strings to lists of event data dictionaries.
        event_type: The string name of the event type to find.

    Returns:
        A list of event data dictionaries for the given event type, or an empty list if none found.
    """
    return recorded_events.get(event_type, [])

def find_memory_events_by_type(
    recorded_events: Dict[str, List[Dict[str, Any]]],
    memory_event_data_type: str,
    memory_write_event_name: str = DEFAULT_MEMORY_WRITE_EVENT_NAME
) -> List[Dict[str, Any]]:
    """
    Finds all 'memory.write' events (or custom memory_write_event_name) and
    filters them by the 'type' field in their 'data' payload (the event's main content).

    Args:
        recorded_events: Captured events from the event bus.
        memory_event_data_type: The value of the 'type' key within the
                                'memory.write' event's data payload
                                (e.g., "thought", "observed_world_event", "npc_presence").
        memory_write_event_name: The actual name of the memory write event
                                 (defaults to "memory.write").
    Returns:
        A list of 'memory.write' event data dictionaries that match the criteria.
    """
    all_memory_write_events_data = recorded_events.get(memory_write_event_name, [])

    matching_events_data = []
    for event_data_item in all_memory_write_events_data:
        if isinstance(event_data_item, dict) and event_data_item.get("type") == memory_event_data_type:
            matching_events_data.append(event_data_item)

    return matching_events_data

def assert_event_published(
    test_case: unittest.TestCase,
    recorded_events: Dict[str, List[Dict[str, Any]]],
    event_type: str,
    expected_count: Optional[int] = 1,
    msg_prefix: str = ""
) -> List[Dict[str, Any]]:
    """
    Asserts that a specific type of event was published an expected number of times.

    Args:
        test_case: The unittest.TestCase instance (for using its assert methods).
        recorded_events: Captured events from the event recorder.
        event_type: The event type string to check.
        expected_count: The expected number of times this event was published.
                        If None, asserts at least one was published.
                        If 0, asserts none were published.
        msg_prefix: Optional prefix for assertion messages for better context.

    Returns:
        The list of found event data dictionaries for the specified event_type,
        allowing further inspection by the caller if needed.

    Raises:
        AssertionError: If the event count does not match expected_count.
    """
    effective_msg_prefix = f"{msg_prefix}[Event: {event_type}] " if msg_prefix else f"[Event: {event_type}] "
    events_found_data_list = recorded_events.get(event_type, [])

    if expected_count is not None:
        test_case.assertEqual(len(events_found_data_list), expected_count,
                              f"{effective_msg_prefix}Expected {expected_count} event(s), but found {len(events_found_data_list)}. "
                              f"Events found: {events_found_data_list[:3]}") # Show first few if many
    else: # expected_count is None, means assert at least one was published
        test_case.assertTrue(len(events_found_data_list) > 0,
                             f"{effective_msg_prefix}Expected at least one event, but found none.")

    return events_found_data_list


def _get_nested_value(data_dict: Dict[str, Any], key_path: str) -> Tuple[Any, bool]:
    """Helper to get a value from a nested dictionary using a dot-separated path."""
    keys = key_path.split('.')
    current_val = data_dict
    found = True
    for k in keys:
        if isinstance(current_val, dict) and k in current_val:
            current_val = current_val[k]
        else:
            found = False
            break
    return current_val, found

def assert_memory_event_present(
    test_case: unittest.TestCase,
    recorded_events: Dict[str, List[Dict[str, Any]]],
    expected_memory_type: str,
    expected_content_substrings: Optional[List[str]] = None,
    expected_metadata_conditions: Optional[Dict[str, Any]] = None,
    min_count: int = 1,
    memory_write_event_name: str = DEFAULT_MEMORY_WRITE_EVENT_NAME,
    msg_prefix: str = ""
) -> List[Dict[str, Any]]:
    """
    Asserts that at least `min_count` memory.write events of a specific `expected_memory_type`
    exist and optionally match all specified content substrings and metadata conditions.

    Args:
        test_case: The unittest.TestCase instance.
        recorded_events: Captured events.
        expected_memory_type: The 'type' field within the memory.write event's data payload.
        expected_content_substrings: Optional list of substrings. All must be present in the 'content' field.
        expected_metadata_conditions: Optional dict where keys are dot-separated paths to metadata fields
                                      (e.g., "npc_id", "details.source_event_type") and values are
                                      the expected values for those fields in the memory event's 'metadata'.
        min_count: The minimum number of matching memory events to find.
        memory_write_event_name: The name of the memory write event (e.g., "memory.write").
        msg_prefix: Optional prefix for assertion messages.

    Returns:
        A list of all matching memory event data dictionaries.

    Raises:
        AssertionError if conditions are not met.
    """
    effective_msg_prefix = f"{msg_prefix}[Memory Type: {expected_memory_type}] " if msg_prefix else f"[Memory Type: {expected_memory_type}] "

    matching_events_data = []
    all_memory_write_events_data = recorded_events.get(memory_write_event_name, [])

    for mem_event_data_item in all_memory_write_events_data:
        if not isinstance(mem_event_data_item, dict) or mem_event_data_item.get("type") != expected_memory_type:
            continue # Not the right memory.write sub-type

        # Check content substrings
        content_match = True
        if expected_content_substrings:
            actual_content = mem_event_data_item.get("content", "")
            if not isinstance(actual_content, str):
                content_match = False
            else:
                for substring in expected_content_substrings:
                    if substring not in actual_content:
                        content_match = False
                        break
        if not content_match:
            continue # Move to next memory event if content doesn't match

        # Check metadata conditions
        metadata_match = True
        if expected_metadata_conditions:
            actual_metadata = mem_event_data_item.get("metadata", {})
            if not isinstance(actual_metadata, dict):
                 metadata_match = False
            else:
                for key_path, expected_val in expected_metadata_conditions.items():
                    current_val, found = _get_nested_value(actual_metadata, key_path)
                    if not found or current_val != expected_val:
                        metadata_match = False
                        break
        if not metadata_match:
            continue # Move to next memory event if metadata doesn't match

        # If all checks passed, this event is a match
        matching_events_data.append(mem_event_data_item)

    test_case.assertGreaterEqual(len(matching_events_data), min_count,
                                 f"{effective_msg_prefix}Expected at least {min_count} matching event(s), "
                                 f"found {len(matching_events_data)}. "
                                 f"All '{memory_write_event_name}' events of type '{expected_memory_type}' inspected: "
                                 f"{[e for e in all_memory_write_events_data if isinstance(e, dict) and e.get('type') == expected_memory_type][:5]}") # Show first few for context
    return matching_events_data

if __name__ == '__main__': # pragma: no cover
    # Example usage (would typically be in a unittest.TestCase method)

    # Dummy TestCase for example execution
    class MyExampleTests(unittest.TestCase):
        def runTest(self): pass # Needed for TestCase to be instantiable

    example_tc_instance = MyExampleTests()

    sample_events_for_util_test = {
        DEFAULT_MEMORY_WRITE_EVENT_NAME: [
            {"type": "thought", "content": "I think I saw a cat today.", "metadata": {"source": "self", "timestamp": "T1"}},
            {"type": "observed_world_event", "content": "Pathos observed: mail_delivery at the front door.", "metadata": {"event_name": "mail_delivery", "id":"evt123", "location": "front_door"}},
            {"type": "thought", "content": "The cat was fluffy and black.", "metadata": {"source": "self", "related_to": "cat_observation_1", "timestamp": "T2"}},
            {"type": "npc_presence", "content": "Mailman Bob is here with a package.", "metadata": {"npc_id": "mailman_bob", "triggering_event_name": "mail_delivery", "dialogue_spoken": "Package!"}}
        ],
        "world.event": [ # Note: This key should match fevent_types.WORLD_EVENT string value
            {"event_name": "mail_delivery", "source": "simulator"}
        ]
    }

    print("--- Testing find_events utility ---")
    world_event_list_found = find_events(sample_events_for_util_test, "world.event")
    print(f"Found world.event(s): {world_event_list_found}")
    assert len(world_event_list_found) == 1, "find_events failed for world.event"

    print("\n--- Testing find_memory_events_by_type utility ---")
    thoughts_found = find_memory_events_by_type(sample_events_for_util_test, "thought")
    print(f"Found 'thought' memory events: {thoughts_found}")
    assert len(thoughts_found) == 2, "find_memory_events_by_type failed for 'thought'"
    assert thoughts_found[0]["content"] == "I think I saw a cat today."

    npc_presence_logs_found = find_memory_events_by_type(sample_events_for_util_test, "npc_presence")
    print(f"Found 'npc_presence' memory events: {npc_presence_logs_found}")
    assert len(npc_presence_logs_found) == 1, "find_memory_events_by_type failed for 'npc_presence'"


    print("\n--- Testing assert_event_published utility ---")
    # This would use self.assert... inside a real test method (e.g., self.assertEqual)
    # Here, we just call it with our dummy TestCase instance.
    assert_event_published(example_tc_instance, sample_events_for_util_test, "world.event", expected_count=1, msg_prefix="TestUtilMain")
    print("assert_event_published for world.event (count=1) seemed to pass.")
    try:
        assert_event_published(example_tc_instance, sample_events_for_util_test, "non_existent_event_type", expected_count=1, msg_prefix="TestUtilMain")
    except AssertionError as e_assert:
        print(f"Caught expected assertion error for non_existent_event_type: {e_assert}")

    print("\n--- Testing assert_memory_event_present utility ---")
    found_mail_observation_events = assert_memory_event_present(
        example_tc_instance, sample_events_for_util_test, "observed_world_event",
        content_substrings=["Pathos observed", "mail_delivery", "front door"],
        expected_metadata_conditions={"event_name": "mail_delivery", "id": "evt123", "location": "front_door"},
        msg_prefix="TestUtilMain"
    )
    print(f"Found mail observation event(s) via assert_memory_event_present: {found_mail_observation_events}")
    assert len(found_mail_observation_events) == 1

    try:
        assert_memory_event_present(
            example_tc_instance, sample_events_for_util_test, "thought",
            content_substrings=["dog"] # This substring won't be found in any thought
        )
    except AssertionError as e_assert_2:
        print(f"Caught expected assertion error for thought with 'dog': {e_assert_2}")

    found_specific_thought = assert_memory_event_present(
        example_tc_instance, sample_events_for_util_test, "thought",
        content_substrings=["cat", "fluffy"],
        expected_metadata_conditions={"source": "self", "related_to": "cat_observation_1"}
    )
    assert len(found_specific_thought) == 1
    print(f"Found specific fluffy cat thought: {found_specific_thought[0]['content']}")

    print("\nTest utilities __main__ example finished successfully.")
