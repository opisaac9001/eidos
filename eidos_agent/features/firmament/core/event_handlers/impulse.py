# Adjust import paths as necessary for the Eidos project structure
from ..event_bus import EventBus
from ..event_types import IMPULSE, SLEEP_REQUESTED
from datetime import datetime, timedelta

def handle_impulse(data: dict):
    """
    Handles impulse events from the subconscious.
    Example: if the impulse is 'tired', it might request sleep.
    """
    print(f"Handling impulse: {data}") # Added for logging/visibility
    impulse_type = data.get("type")

    if impulse_type == "tired":
        # Calculate a hypothetical sleep time (e.g., 30 minutes from now)
        # In a real scenario, this might involve more complex logic or configuration.
        sleep_start_time = datetime.utcnow() + timedelta(minutes=30)

        event_data = {
            "reason": "tired_impulse",
            "requester": "firmament.impulse_handler",
            "start_time_utc": sleep_start_time.isoformat()
        }
        EventBus.instance().publish(SLEEP_REQUESTED, event_data)
        print(f"Published {SLEEP_REQUESTED} due to '{impulse_type}' impulse. Sleep requested for {sleep_start_time.isoformat()} UTC.")
    elif impulse_type:
        # Handle other impulse types or log them if not specifically handled
        print(f"Received unhandled impulse type: {impulse_type} with data: {data}")
    else:
        # Log if impulse type is missing
        print(f"Received impulse with no type: {data}")

    # Add more impulse handling logic here as needed
    # For example:
    # if impulse_type == "hungry":
    #     EventBus.instance().publish(FOOD_REQUESTED, {"intensity": data.get("intensity", "normal")})
    #     print("Published FOOD_REQUESTED event due to 'hungry' impulse.")

# Example of how this handler might be registered and tested (optional)
if __name__ == '__main__':
    # This block is for direct testing of the handler.
    # It requires setting up a mock EventBus or a real one and manually publishing events.

    # Using the actual EventBus for this test.
    # Ensure EventBus is accessible. If run from eidos_agent/features/firmament/core/event_handlers,
    # relative imports like `from ..event_bus import EventBus` should work if Python is invoked
    # as a module (e.g., python -m eidos_agent.features.firmament.core.event_handlers.impulse)
    # or if the PYTHONPATH is set up appropriately.

    # For simplicity in direct script execution (python impulse.py),
    # we might need to adjust sys.path or use a test harness.
    # Let's assume for now this script is part of a larger system where imports resolve correctly.

    # Mock subscriber for SLEEP_REQUESTED to see if it's published
    def mock_sleep_requested_handler(data):
        print(f"[Test SLEEP_REQUESTED Handler] Event received: {data}")

    # Get EventBus instance (it's a singleton)
    bus = EventBus.instance()
    bus.subscribe(SLEEP_REQUESTED, mock_sleep_requested_handler)
    bus.subscribe(IMPULSE, handle_impulse) # Subscribing self for chained impulses if any, or just to log

    print("Testing impulse handler...")

    # Test case 1: Tired impulse
    print("\nTest Case 1: Tired Impulse")
    tired_impulse_data = {"type": "tired", "intensity": "high"}
    # Publishing IMPULSE event, which should trigger handle_impulse, then SLEEP_REQUESTED
    bus.publish(IMPULSE, tired_impulse_data)

    # Test case 2: Another impulse type (e.g., hungry - not implemented yet but for demonstration)
    print("\nTest Case 2: Hungry Impulse (Not implemented)")
    hungry_impulse_data = {"type": "hungry", "urgency": "moderate"}
    bus.publish(IMPULSE, hungry_impulse_data)

    # Test case 3: Impulse with no type
    print("\nTest Case 3: Impulse with no type")
    no_type_impulse_data = {"intensity": "low"}
    bus.publish(IMPULSE, no_type_impulse_data)

    print("\nImpulse handler testing finished.")
