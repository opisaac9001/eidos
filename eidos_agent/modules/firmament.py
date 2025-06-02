"""
Eidos Agent Firmament Module.

This module is responsible for handling "impulses" received from the
Pathos Subconscious Node. Impulses are thoughts or urges that might
require further consideration or trigger actions within Eidos.

Currently, impulses are stored in an in-memory buffer for pending review.
Future enhancements could involve more sophisticated processing, prioritization,
or decision-making logic based on these impulses.
"""
import logging
import collections
from typing import Dict, Any, List

# Configure basic logging if not already configured by Eidos
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Define In-Memory Buffer
MAX_PENDING_IMPULSES = 50
pending_impulses_buffer = collections.deque(maxlen=MAX_PENDING_IMPULSES)

def handle_external_impulse(thought: str, timestamp: str, mood: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handles an external impulse received from the subconscious node by adding it
    to an in-memory buffer for pending review.

    This function processes the impulse, logs relevant details, and stores it
    for potential later processing or decision-making within the Eidos agent.

    Args:
        thought: The content of the impulsive thought.
        timestamp: The ISO 8601 timestamp of when the impulse occurred.
        mood: A dictionary representing the mood snapshot at the time of the impulse.

    Returns:
        A dictionary indicating the status of handling the impulse and the impulse details.
    """
    logger.info(f"FIRMAMENT: Received external impulse from subconscious: '{thought}'") # FERMENT -> FIRMAMENT

    impulse_data = {
        "timestamp": timestamp,
        "thought": thought,
        "mood_snapshot": mood,
        "status": "pending_review", # New field to track status
        "triggered_by": "subconscious"
    }
    
    pending_impulses_buffer.append(impulse_data)
    
    logger.info(f"FIRMAMENT: Impulse added to pending buffer. Current buffer size: {len(pending_impulses_buffer)}") # FERMENT -> FIRMAMENT
    logger.debug(f"FIRMAMENT: Impulse details: {impulse_data}") # More detailed log at debug level # FERMENT -> FIRMAMENT

    return {"status": "impulse added to pending buffer", "impulse_details": impulse_data}

def get_pending_impulses() -> List[Dict[str, Any]]:
    """
    Retrieves the current list of pending impulses from the in-memory buffer.

    Returns:
        A list of dictionaries, where each dictionary is an impulse_data object.
    """
    return list(pending_impulses_buffer)

if __name__ == '__main__':
    print("--- Testing firmament.handle_external_impulse and get_pending_impulses ---") # ferment -> firmament
    
    # Initial state
    print(f"Initial pending impulses: {get_pending_impulses()}")
    assert len(get_pending_impulses()) == 0

    sample_impulses = [
        {"thought": "I should check the door locks again!", "timestamp": "2023-10-27T10:30:00Z", "mood": {"name": "Anxious"}},
        {"thought": "Maybe I can learn a new skill today.", "timestamp": "2023-10-27T10:35:00Z", "mood": {"name": "Inspired"}},
        {"thought": "I need to call Sarah.", "timestamp": "2023-10-27T10:40:00Z", "mood": {"name": "Neutral"}},
    ]

    for i, impulse_args in enumerate(sample_impulses):
        print(f"\nHandling impulse {i+1}...")
        result = handle_external_impulse(**impulse_args)
        print(f"Result: {result}")
        assert result["status"] == "impulse added to pending buffer"
        assert result["impulse_details"]["thought"] == impulse_args["thought"]
        assert result["impulse_details"]["status"] == "pending_review"

    print(f"\nPending impulses after additions: {get_pending_impulses()}")
    assert len(get_pending_impulses()) == len(sample_impulses)
    assert get_pending_impulses()[-1]["thought"] == sample_impulses[-1]["thought"]

    print("\n--- Testing maxlen behavior ---")
    # Reduce MAX_PENDING_IMPULSES for this test block if it's too high for quick testing
    # Or simulate by directly manipulating a local deque for this test part
    
    # For this test, let's assume MAX_PENDING_IMPULSES is small, e.g., 3 for demo.
    # We'll clear the global one and use a local one for this specific test part
    # to avoid affecting other tests if MAX_PENDING_IMPULSES is large.
    
    # If we want to test the global buffer's maxlen directly, we'd need to set MAX_PENDING_IMPULSES low.
    # The current MAX_PENDING_IMPULSES is 50, so filling it would take many iterations.
    # Instead, we'll demonstrate the deque's behavior locally.
    
    local_test_buffer = collections.deque(maxlen=3)
    print(f"Local test buffer (maxlen=3) initial: {list(local_test_buffer)}")
    for i in range(5):
        imp_data = {"thought": f"Test thought {i+1}", "timestamp": f"ts{i+1}", "mood": {}, "status": "pending_review", "triggered_by": "subconscious"}
        local_test_buffer.append(imp_data)
        print(f"Added 'Test thought {i+1}'. Local buffer: {list(local_test_buffer)}")
    
    assert len(local_test_buffer) == 3
    assert local_test_buffer[0]["thought"] == "Test thought 3" # Oldest (0,1,2) were pushed out
    assert local_test_buffer[-1]["thought"] == "Test thought 5" # Newest
    print("Maxlen behavior demonstrated with local deque.")

    # To truly test the global buffer's maxlen, you'd need to set MAX_PENDING_IMPULSES to a small number
    # before running this __main__ block, or add many items.
    # Example:
    # original_maxlen = MAX_PENDING_IMPULSES
    # MAX_PENDING_IMPULSES = 3 # Temporarily change for test
    # pending_impulses_buffer.clear() # Clear global buffer
    # pending_impulses_buffer = collections.deque(maxlen=MAX_PENDING_IMPULSES) # Reinitialize with new maxlen
    # for i in range(5):
    #     handle_external_impulse(f"Global test {i}", f"ts_global_{i}", {})
    # print(f"Global pending impulses (maxlen={MAX_PENDING_IMPULSES}): {get_pending_impulses()}")
    # assert len(get_pending_impulses()) == 3
    # assert get_pending_impulses()[0]["thought"] == "Global test 2"
    # MAX_PENDING_IMPULSES = original_maxlen # Restore
    # pending_impulses_buffer = collections.deque(maxlen=MAX_PENDING_IMPULSES) # Reinitialize
    # print("Global buffer maxlen test would require actual modification or many additions.")


    print("\nAll tests completed. Verify logs for detailed output.")
