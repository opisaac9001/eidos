import logging
from typing import Dict, Any # Added for type hints

# Configure basic logging if not already configured by Eidos
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def handle_external_impulse(thought: str, timestamp: str, mood: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handles an external impulse received from the subconscious node.

    This function processes the impulse, logs relevant details, and would typically
    trigger further decision-making or actions within the Eidos agent based on
    the nature of the impulse.

    Args:
        thought: The content of the impulsive thought.
        timestamp: The ISO 8601 timestamp of when the impulse occurred.
        mood: A dictionary representing the mood snapshot at the time of the impulse.

    Returns:
        A dictionary indicating the status of handling the impulse and the action details.
    """
    logger.info(f"FERMENT: Received external impulse from subconscious.")
    logger.info(f"FERMENT: Action triggered by subconscious: '{thought}'. Mood context: {mood}")

    action_details = {
        "thought": thought,
        "timestamp": timestamp,
        "mood": mood,
        "triggered_by": "subconscious"
    }
    logger.info(f"FERMENT: Action details: {action_details}")

    # In a real implementation, this would trigger further action/decision making.
    return {"status": "impulse processed by ferment", "action_details": action_details}

if __name__ == '__main__':
    print("--- Testing ferment.handle_external_impulse ---")
    sample_mood = {"name": "Anxious", "intensity": 0.7, "impulsiveness": 0.8}
    sample_thought = "I should check the door locks again!"
    sample_timestamp = "2023-10-27T10:30:00Z"

    result = handle_external_impulse(
        thought=sample_thought,
        timestamp=sample_timestamp,
        mood=sample_mood
    )
    print(f"Result from handle_external_impulse: {result}")
    assert result["status"] == "impulse processed by ferment"
    assert result["action_details"]["thought"] == sample_thought
    assert result["action_details"]["triggered_by"] == "subconscious"
    print("Test completed. Verify logs for detailed output.")
