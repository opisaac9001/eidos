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

# NOTE: The FirmamentModule instance would typically be accessed via
# a dependency injection mechanism or a global application context in a FastAPI app.
# For this example, we'll assume it's made available somehow.
# from eidos_agent.main import get_firmament_module # Hypothetical access
FIRMAMENT_MODULE_INSTANCE = None # Placeholder

def set_firmament_module_instance(instance): # Helper for testing or app setup
    global FIRMAMENT_MODULE_INSTANCE
    FIRMAMENT_MODULE_INSTANCE = instance

async def handle_external_impulse(thought: str, timestamp: str, mood: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handles an external impulse received from the subconscious node by passing it
    to the FirmamentModule for processing and potential action.

    Args:
        thought: The content of the impulsive thought (becomes 'intention').
        timestamp: The ISO 8601 timestamp of when the impulse occurred.
        mood: A dictionary representing the mood snapshot at the time of the impulse.

    Returns:
        A dictionary indicating the status of processing the impulse.
    """
    logger.info(f"FIRMAMENT HANDLER: Received external impulse: '{thought}'")

    if not FIRMAMENT_MODULE_INSTANCE:
        logger.error("FIRMAMENT HANDLER: FirmamentModule instance not available. Cannot process impulse.")
        # In a real app, this might raise an HTTPException or return a specific error response.
        return {"status": "error", "detail": "FirmamentModule not configured"}

    # Construct metadata for FirmamentModule.receive_subconscious_intention
    # The 'mood' parameter from the router is already the mood_snapshot.
    metadata = {
        "timestamp": timestamp,
        "mood_snapshot": mood, # This is data.mood_snapshot from the router
        "source_component": "subconscious_node_hook"
        # Add any other relevant metadata if available or needed
    }

    try:
        # Call the FirmamentModule method
        # Note: FirmamentModule.receive_subconscious_intention is an async method
        await FIRMAMENT_MODULE_INSTANCE.receive_subconscious_intention(
            intention=thought, # 'thought' from ImpulseData maps to 'intention'
            metadata=metadata
        )
        logger.info(f"FIRMAMENT HANDLER: Impulse '{thought[:50]}...' successfully passed to FirmamentModule.")
        return {"status": "impulse_processed_by_firmament", "intention": thought}
    except Exception as e:
        logger.exception(f"FIRMAMENT HANDLER: Error calling FirmamentModule.receive_subconscious_intention for thought '{thought[:50]}...'")
        # In a real app, this might raise an HTTPException
        return {"status": "error_processing_impulse", "detail": str(e)}

# The get_pending_impulses function and associated buffer are removed as impulses
# are now intended to be processed directly by FirmamentModule.
# If buffering is needed, it should be part of FirmamentModule's internal logic.

if __name__ == '__main__':
    print("--- Testing firmament.handle_external_impulse (mocked FirmamentModule) ---")

    # Mock FirmamentModule and its method for testing
    class MockFirmamentModule:
        async def receive_subconscious_intention(self, intention: str, metadata: Dict[str, Any]):
            print(f"MockFirmamentModule.receive_subconscious_intention called:")
            print(f"  Intention: {intention}")
            print(f"  Metadata: {metadata}")
            if "error" in intention.lower():
                raise ValueError("Simulated processing error in FirmamentModule")
            return {"status": "mock_firmament_processed", "intention": intention}

    # Set the mock instance for the handler to use
    mock_fm_instance = MockFirmamentModule()
    set_firmament_module_instance(mock_fm_instance)
    print("MockFirmamentModule instance set.")

    import asyncio

    async def run_tests():
        sample_impulses = [
            {"thought": "I should check the door locks again!", "timestamp": "2023-10-27T10:30:00Z", "mood": {"name": "Anxious", "valence": -0.5, "arousal": 0.6}},
            {"thought": "Maybe I can learn a new skill today.", "timestamp": "2023-10-27T10:35:00Z", "mood": {"name": "Inspired", "valence": 0.7, "arousal": 0.5}},
            {"thought": "I need to call Sarah.", "timestamp": "2023-10-27T10:40:00Z", "mood": {"name": "Neutral", "valence": 0.0, "arousal": 0.2}},
            {"thought": "Test for error simulation", "timestamp": "2023-10-27T10:45:00Z", "mood": {"name": "Problematic", "valence": -0.2, "arousal": 0.1}},
        ]

        for i, impulse_args in enumerate(sample_impulses):
            print(f"\nHandling impulse {i+1}...")
            result = await handle_external_impulse(**impulse_args)
            print(f"Result from handler: {result}")
            if "error" in impulse_args["thought"].lower():
                assert result["status"] == "error_processing_impulse"
            else:
                assert result["status"] == "impulse_processed_by_firmament"
                assert result["intention"] == impulse_args["thought"]

        # Test case where FirmamentModule is not set
        set_firmament_module_instance(None)
        print("\nFirmamentModule instance unset for next test.")
        result_no_fm = await handle_external_impulse(**sample_impulses[0])
        print(f"Result with no FirmamentModule: {result_no_fm}")
        assert result_no_fm["status"] == "error"
        assert result_no_fm["detail"] == "FirmamentModule not configured"


    asyncio.run(run_tests())
    print("\nFirmament handler tests finished.")

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
