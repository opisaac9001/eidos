# eidos_agent/features/firmament/core/availability.py

# This module will compute Pathos's current availability, focus level,
# or readiness for interaction, based on mood, energy, stress, etc.
# These states could be used by other systems to decide if Pathos can
# take on new tasks, engage in complex interactions, or needs rest/recovery.

# Define state constants for clarity and maintainability
AVAILABILITY_STATE_AVAILABLE = "AVAILABLE"
AVAILABILITY_STATE_BUSY_RECOVERY = "BUSY_RECOVERY" # Low energy
AVAILABILITY_STATE_DISTRACTED = "DISTRACTED"     # High stress
AVAILABILITY_STATE_LOW_FOCUS = "LOW_FOCUS"       # Low focus (example)
AVAILABILITY_STATE_UNKNOWN_INVALID_INPUT = "UNKNOWN_STATE_INVALID_INPUT"
AVAILABILITY_STATE_UNKNOWN_MISSING_ENERGY = "UNKNOWN_AVAILABILITY_NO_ENERGY_SCORE"
AVAILABILITY_STATE_UNKNOWN_MISSING_STRESS = "UNKNOWN_AVAILABILITY_NO_STRESS_SCORE"
AVAILABILITY_STATE_UNKNOWN_MISSING_FOCUS = "UNKNOWN_AVAILABILITY_NO_FOCUS_SCORE" # Example

def get_availability_state(mood_scores: dict) -> str:
    """
    Computes the current availability state based on mood scores.

    Args:
        mood_scores: A dictionary with keys like 'energy', 'stress', 'focus'.
                     Values are typically floats (e.g., 0.0 to 1.0).

    Returns:
        A string constant representing the availability state.
    """
    if not isinstance(mood_scores, dict):
        print("Warning: get_availability_state called with invalid mood_scores type.")
        return AVAILABILITY_STATE_UNKNOWN_INVALID_INPUT

    energy = mood_scores.get("energy")
    stress = mood_scores.get("stress")
    focus = mood_scores.get("focus") # Example: adding focus check

    # Validate presence and type of critical mood scores
    if energy is None or not isinstance(energy, (int, float)):
        print("Warning: 'energy' score is missing or invalid in mood_scores.")
        return AVAILABILITY_STATE_UNKNOWN_MISSING_ENERGY

    if stress is None or not isinstance(stress, (int, float)):
        print("Warning: 'stress' score is missing or invalid in mood_scores.")
        return AVAILABILITY_STATE_UNKNOWN_MISSING_STRESS

    # Availability logic based on scores
    # Order of checks can be important depending on desired priority
    if energy < 0.3:
        return AVAILABILITY_STATE_BUSY_RECOVERY
    elif stress > 0.8:
        return AVAILABILITY_STATE_DISTRACTED

    # Example of incorporating another factor like 'focus'
    # This assumes 'focus' is also a score from 0.0 to 1.0 (lower is less focused)
    if focus is not None and isinstance(focus, (int, float)):
        if focus < 0.5:
            return AVAILABILITY_STATE_LOW_FOCUS
    # If focus is critical and missing, could return a specific state:
    # elif focus is None:
    #     print("Warning: 'focus' score is missing, affecting availability assessment.")
    #     return AVAILABILITY_STATE_UNKNOWN_MISSING_FOCUS

    # Default state if no other conditions met
    return AVAILABILITY_STATE_AVAILABLE

# Example usage (optional, for testing or demonstration)
if __name__ == '__main__':
    print("Testing get_availability_state function:")

    test_cases = [
        ({"energy": 0.2, "stress": 0.5, "focus": 0.8}, AVAILABILITY_STATE_BUSY_RECOVERY),
        ({"energy": 0.8, "stress": 0.9, "focus": 0.4}, AVAILABILITY_STATE_DISTRACTED),
        ({"energy": 0.7, "stress": 0.4, "focus": 0.3}, AVAILABILITY_STATE_LOW_FOCUS), # Test LOW_FOCUS
        ({"energy": 0.7, "stress": 0.4, "focus": 0.9}, AVAILABILITY_STATE_AVAILABLE),
        ({"energy": 0.6, "stress": 0.5}, AVAILABILITY_STATE_AVAILABLE), # Focus missing, but not critical for AVAILABLE here
        ({"energy": 0.4, "stress": None}, AVAILABILITY_STATE_UNKNOWN_MISSING_STRESS), # Missing stress
        ({"stress": 0.5}, AVAILABILITY_STATE_UNKNOWN_MISSING_ENERGY), # Missing energy
        ({}, AVAILABILITY_STATE_UNKNOWN_MISSING_ENERGY), # Empty dict, energy check comes first
        ("not a dict", AVAILABILITY_STATE_UNKNOWN_INVALID_INPUT),
        ({"energy": "low", "stress": 0.5}, AVAILABILITY_STATE_UNKNOWN_MISSING_ENERGY) # Invalid type for energy
    ]

    for i, (moods, expected_state) in enumerate(test_cases):
        actual_state = get_availability_state(moods)
        print(f"\nTest Case {i+1}:")
        print(f"  Mood scores: {moods}")
        print(f"  Expected: {expected_state}")
        print(f"  Actual:   {actual_state}")
        assert actual_state == expected_state, f"Test Case {i+1} Failed: Expected {expected_state}, got {actual_state}"
        print(f"  Result: {'PASSED' if actual_state == expected_state else 'FAILED'}")

    print("\nAll test cases for get_availability_state processed.")
