import logging
from typing import Dict, Any, Optional

# Attempt to import EthosCore for type hinting, define a dummy if import fails
try:
    # Adjust path if EthosCore is not directly in .core or if this file moves
    from .core import EthosCore
except ImportError:
    # Define a minimal dummy EthosCore for type hinting if standalone or import issues
    class EthosCore: # type: ignore
        def get_hexus_scores(self) -> Dict[str, float]: # Method used by MoodEngine if it were to call it
            return {}
        # Add other methods/attributes if MoodEngine's __init__ needs more from ethos_core
        pass

logger = logging.getLogger(__name__)

class MoodEngine:
    def __init__(self, ethos_core: Optional[EthosCore] = None):
        """
        Initializes the MoodEngine.

        Args:
            ethos_core (Optional[EthosCore]): An instance of EthosCore, primarily to access
                                             Hexus scores or other mood-relevant context in the future.
                                             Can be None for basic instantiation or if Hexus scores
                                             are passed directly to calculation methods.
        """
        self.ethos_core = ethos_core
        # Future: Initialize any mood-specific parameters, models, or history tracking here.
        logger.info("MoodEngine initialized.")

    def calculate_current_mood(self, hexus_scores: Dict[str, float]) -> Dict[str, Any]:
        """
        Derives a simplified valence/arousal representation and a mood name from Hexus scores.

        Args:
            hexus_scores (Dict[str, float]): A dictionary of current Hexus scores.

        Returns:
            Dict[str, Any]: A dictionary containing 'valence', 'arousal', and 'name'.
                            Example: {"valence": 0.5, "arousal": 0.2, "name": "pleased"}
        """
        if not hexus_scores:
            logger.warning("MoodEngine: Hexus scores not provided for mood calculation. Returning neutral.")
            return {"valence": 0.0, "arousal": 0.0, "name": "neutral"}

        # Logic moved from EthosCore.get_current_mood()
        joy_val = hexus_scores.get("joy", 0.0)
        contentment_val = hexus_scores.get("contentment", 0.0)
        stress_val = hexus_scores.get("stress", 0.0)
        resentment_val = hexus_scores.get("resentment", 0.0)
        melancholy_val = hexus_scores.get("melancholy", 0.0)

        curiosity_val = hexus_scores.get("curiosity", 0.0)
        focus_val = hexus_scores.get("focus", 0.0)
        ambition_val = hexus_scores.get("ambition", 0.0)
        impulsiveness_val = hexus_scores.get("impulsiveness", 0.0)
        tiredness_val = hexus_scores.get("tiredness", 0.0)

        # Simplified valence/arousal calculation based on Hexus scores
        # These weights/combinations can be refined
        derived_valence = (joy_val * 0.4 + contentment_val * 0.3) - \
                          (stress_val * 0.5 + resentment_val * 0.3 + melancholy_val * 0.2)

        derived_arousal = (curiosity_val * 0.2 + focus_val * 0.2 + ambition_val * 0.1 + impulsiveness_val * 0.1) - \
                          (tiredness_val * 0.3)

        # Clamp derived valence/arousal to -1.0 to 1.0
        derived_valence = max(-1.0, min(1.0, derived_valence))
        derived_arousal = max(-1.0, min(1.0, derived_arousal))

        # Determine a qualitative mood name based on valence and arousal
        mood_name = "neutral"
        if derived_valence > 0.5: # Significantly positive valence
            if derived_arousal > 0.5: mood_name = "elated"
            elif derived_arousal > 0.1: mood_name = "happy"
            else: mood_name = "content"
        elif derived_valence > 0.1: # Mildly positive valence
            if derived_arousal > 0.5: mood_name = "excited"
            elif derived_arousal > 0.1: mood_name = "pleased"
            else: mood_name = "calm"
        elif derived_valence < -0.5: # Significantly negative valence
            if derived_arousal > 0.5: mood_name = "distressed"
            elif derived_arousal > 0.1: mood_name = "unhappy"
            else: mood_name = "sad"
        elif derived_valence < -0.1: # Mildly negative valence
            if derived_arousal > 0.5: mood_name = "agitated"
            elif derived_arousal > 0.1: mood_name = "tense"
            else: mood_name = "subdued"
        elif derived_arousal > 0.6: mood_name = "alert" # High arousal, neutral valence
        elif derived_arousal < -0.6: mood_name = "relaxed" # Low arousal, neutral valence
        # Default is "neutral"

        logger.debug(f"MoodEngine calculated mood: Name='{mood_name}', Valence={derived_valence:.2f}, Arousal={derived_arousal:.2f} from Hexus input.")

        return {
            "valence": derived_valence,
            "arousal": derived_arousal,
            "name": mood_name
        }

if __name__ == '__main__':
    # Basic Test for MoodEngine
    logging.basicConfig(level=logging.DEBUG)

    # Mock EthosCore for testing MoodEngine initialization (if it expects one)
    class MockEthosCore:
        pass # No methods needed if MoodEngine doesn't call EthosCore in __init__

    mock_ethos = MockEthosCore()
    mood_engine_test = MoodEngine(ethos_core=mock_ethos) # type: ignore

    sample_hexus_scores = {
        "joy": 0.7, "contentment": 0.6, "stress": 0.1, "resentment": 0.0, "melancholy": 0.1,
        "curiosity": 0.8, "focus": 0.7, "ambition": 0.5, "impulsiveness": 0.2, "tiredness": 0.1
    }
    calculated_mood = mood_engine_test.calculate_current_mood(sample_hexus_scores)
    logger.info(f"Test 1 - Calculated Mood: {calculated_mood}")
    assert "name" in calculated_mood
    assert calculated_mood["name"] == "elated" # Based on sample scores and new logic

    sample_hexus_scores_2 = {
        "joy": 0.1, "contentment": 0.2, "stress": 0.8, "resentment": 0.5, "melancholy": 0.6,
        "curiosity": 0.2, "focus": 0.1, "ambition": 0.1, "impulsiveness": 0.7, "tiredness": 0.7
    }
    calculated_mood_2 = mood_engine_test.calculate_current_mood(sample_hexus_scores_2)
    logger.info(f"Test 2 - Calculated Mood: {calculated_mood_2}")
    assert calculated_mood_2["name"] == "distressed" # Based on sample scores and new logic

    calculated_mood_3 = mood_engine_test.calculate_current_mood({}) # Empty Hexus
    logger.info(f"Test 3 - Calculated Mood (empty Hexus): {calculated_mood_3}")
    assert calculated_mood_3["name"] == "neutral"

    logger.info("MoodEngine basic tests passed.")
