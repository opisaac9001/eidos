import logging
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .core import EthosCore # For type hinting EthosCore instance

logger = logging.getLogger(__name__)

class MoodEngine:
    def __init__(self, ethos_core_instance: Optional['EthosCore'] = None):
        """
        Initializes the MoodEngine.

        Args:
            ethos_core_instance: An optional reference to the parent EthosCore instance.
                                 Used for accessing configuration or other components if needed.
        """
        self.ethos_core = ethos_core_instance # Store if needed later

        # These could later come from Eidos config via ethos_core_instance
        self.baseline_mood: Dict[str, float] = {
            "valence": 0.0,       # Neutral
            "arousal": 0.0,       # Calm
            "proactivity": 0.4,   # Moderately proactive
            "impulsiveness": 0.3, # Moderately controlled
            "extroversion": 0.5,  # Balanced
            # Additional dimensions that subconscious_node.mood might use or be influenced by
            "focus": 0.5,         # Baseline focus level
            "laziness": 0.5,      # Baseline for laziness (from subconscious_node default)
        }
        self.current_mood: Dict[str, float] = self.baseline_mood.copy()

        self.mood_value_bounds: Dict[str, tuple[float, float]] = {
            "valence": (-1.0, 1.0),
            "arousal": (-1.0, 1.0), # Using -1 to 1 for bipolar arousal (e.g. sleepy vs agitated)
            "proactivity": (0.0, 1.0),
            "impulsiveness": (0.0, 1.0),
            "extroversion": (0.0, 1.0),
            "focus": (0.0, 1.0),
            "laziness": (0.0, 1.0),
        }
        logger.info(f"MoodEngine initialized. Baseline mood: {self.baseline_mood}")

    def get_current_mood_snapshot(self) -> Dict[str, float]:
        """
        Returns a copy of the current mood state.
        """
        logger.debug(f"Getting current mood snapshot: {self.current_mood}")
        return self.current_mood.copy()

    def _apply_mood_delta(self, dimension: str, delta: float):
        """
        Helper function to update a mood dimension by a delta, ensuring it stays within predefined bounds.
        If the dimension is not currently in current_mood, it's initialized from baseline_mood first.
        """
        current_value = self.current_mood.get(dimension, self.baseline_mood.get(dimension, 0.0))
        new_value = current_value + delta

        min_val, max_val = self.mood_value_bounds.get(dimension, (0.0, 1.0)) # Default bounds if not specified

        clamped_value = max(min_val, min(new_value, max_val))

        if self.current_mood.get(dimension) != clamped_value: # Log only if there's a change
            self.current_mood[dimension] = clamped_value
            logger.info(f"Mood dimension '{dimension}' changed by {delta:.3f} to {clamped_value:.3f} (from {current_value:.3f}).")
        else:
            logger.debug(f"Mood dimension '{dimension}' delta {delta:.3f} resulted in no change from {current_value:.3f} (already at bounds or delta too small).")


    def process_event(self, event_type: str, event_data: Optional[Dict] = None):
        """
        Updates mood based on system events using simple rule-based logic.

        Args:
            event_type: A string identifying the type of event.
            event_data: An optional dictionary containing data related to the event.
        """
        logger.info(f"Processing mood event: {event_type}, Data: {event_data if event_data else 'N/A'}")

        # Example rules - these would be expanded significantly
        if event_type == "USER_INTERACTION_POSITIVE":
            self._apply_mood_delta("valence", 0.1)
            self._apply_mood_delta("arousal", 0.05) # Slight increase in arousal for positive interaction
        elif event_type == "USER_INTERACTION_NEGATIVE":
            self._apply_mood_delta("valence", -0.15) # Larger impact for negative
            self._apply_mood_delta("arousal", 0.1)   # Negative interaction can also increase arousal (stress)
        elif event_type == "COMPLETED_WORK_TASK":
            self._apply_mood_delta("proactivity", 0.05) # Sense of accomplishment
            self._apply_mood_delta("valence", 0.05)     # Positive feeling
            self._apply_mood_delta("focus", 0.1)        # Increased focus after completing work
            self._apply_mood_delta("arousal", -0.05)    # Can be calming to finish work
        elif event_type == "COMPLETED_LEISURE_ACTIVITY":
            self._apply_mood_delta("valence", 0.15)
            self._apply_mood_delta("arousal", 0.05)
            self._apply_mood_delta("laziness", -0.05) # Less lazy after leisure
        elif event_type == "RECEIVED_SUBPROCESS_IMPRINT": # e.g., a realization from subconscious
            self._apply_mood_delta("valence", 0.05)     # Assuming imprints are generally positive/insightful
            self._apply_mood_delta("arousal", 0.02)
            # Could also affect 'focus' if the imprint is profound
        elif event_type == "PROLONGED_IDLENESS": # A hypothetical event Eidos might generate
            self._apply_mood_delta("valence", -0.05)
            self._apply_mood_delta("arousal", -0.1)
            self._apply_mood_delta("proactivity", -0.05)
            self._apply_mood_delta("laziness", 0.05)
        else:
            logger.debug(f"No specific mood rule for event_type: {event_type}")

    def decay_mood(self, decay_factor: float = 0.05):
        """
        Periodically called to make mood dimensions drift towards their baseline values.

        Args:
            decay_factor: The fraction of the difference to baseline to decay by.
                          Example: 0.05 means 5% of the way towards baseline.
        """
        logger.info("Applying mood decay...")
        changed_any = False
        for dimension, current_value in list(self.current_mood.items()): # list() for safe iteration if _apply_mood_delta modifies dict
            baseline_value = self.baseline_mood.get(dimension, 0.0) # Default to 0.0 if not in baseline
            delta_to_baseline = baseline_value - current_value

            if abs(delta_to_baseline) > 0.001: # Only apply if there's a notable difference
                decay_amount = delta_to_baseline * decay_factor
                self._apply_mood_delta(dimension, decay_amount)
                changed_any = True

        if changed_any:
            logger.info(f"Mood after decay: {self.current_mood}")
        else:
            logger.info("Mood decay applied, but no significant changes as values are close to baseline.")

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG) # Enable debug for testing

    mood_engine = MoodEngine()
    logger.info("--- MoodEngine Test ---")

    logger.info(f"Initial mood: {mood_engine.get_current_mood_snapshot()}")

    mood_engine.process_event("USER_INTERACTION_POSITIVE")
    logger.info(f"Mood after positive interaction: {mood_engine.get_current_mood_snapshot()}")

    mood_engine.process_event("COMPLETED_WORK_TASK")
    logger.info(f"Mood after completed work: {mood_engine.get_current_mood_snapshot()}")

    mood_engine.current_mood["valence"] = 0.8 # Manually set for decay test
    mood_engine.current_mood["proactivity"] = 0.9
    logger.info(f"Mood before decay (manual set): {mood_engine.get_current_mood_snapshot()}")
    mood_engine.decay_mood(decay_factor=0.1) # Stronger decay for test
    logger.info(f"Mood after 1st decay: {mood_engine.get_current_mood_snapshot()}")
    mood_engine.decay_mood(decay_factor=0.1)
    logger.info(f"Mood after 2nd decay: {mood_engine.get_current_mood_snapshot()}")

    mood_engine.process_event("USER_INTERACTION_NEGATIVE")
    logger.info(f"Mood after negative interaction: {mood_engine.get_current_mood_snapshot()}")

    # Test bounds
    mood_engine.current_mood["valence"] = 0.95
    mood_engine._apply_mood_delta("valence", 0.2) # Should clamp to 1.0
    assert mood_engine.current_mood["valence"] == 1.0
    logger.info(f"Mood after clamping high: {mood_engine.get_current_mood_snapshot()}")

    mood_engine.current_mood["valence"] = -0.95
    mood_engine._apply_mood_delta("valence", -0.2) # Should clamp to -1.0
    assert mood_engine.current_mood["valence"] == -1.0
    logger.info(f"Mood after clamping low: {mood_engine.get_current_mood_snapshot()}")

    logger.info("--- MoodEngine Test Finished ---")

```
