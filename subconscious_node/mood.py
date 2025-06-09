"""
Manages the mood state of the Pathos Subconscious Node.

This module is responsible for:
- Initializing the mood from a configuration file.
- Providing functions to get and update the current mood.
- Simulating mood changes over time (currently a placeholder).
"""
import json
import os # Added for environment variable access
import logging # Added for logging

# --- Logging Setup ---
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Global Variables ---
current_mood = {} # Will be populated by _load_and_initialize_mood
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'config.json') # Define once

# --- Default Mood Components (Hardcoded Fallbacks) ---
DEFAULT_MOOD_COMPONENTS = {
    "impulsiveness": 0.3, "laziness": 0.5, "proactivity": 0.4,
    "extroversion": 0.6, "introversion": 0.4
}

# --- Initialization ---
def _load_and_initialize_mood():
    """
    Loads the default mood, applying overrides from config file and environment variables.
    Precedence: Env Var -> Config File -> Hardcoded Default.
    """
    global current_mood

    # Start with hardcoded defaults
    effective_mood = DEFAULT_MOOD_COMPONENTS.copy()

    # Load from config.json
    config_data_mood = {}
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, 'r') as f:
                config_data_mood = json.load(f)
            logger.info(f"Mood: Successfully loaded configuration from {CONFIG_FILE_PATH}")
        except Exception as e:
            logger.error(f"Mood: Error loading config from {CONFIG_FILE_PATH}: {e}. Using defaults or env vars.", exc_info=True)
    else:
        logger.info(f"Mood: Config file {CONFIG_FILE_PATH} not found. Using defaults or env vars.")

    # Get 'default_mood' from config.json, or use hardcoded if not found
    json_default_mood = config_data_mood.get("mood_settings", {}).get("default_mood", DEFAULT_MOOD_COMPONENTS)

    # Override with values from config.json if they exist, over hardcoded defaults
    for key in effective_mood:
        if key in json_default_mood:
            effective_mood[key] = json_default_mood[key]

    # Override with environment variables
    effective_mood["impulsiveness"] = float(os.getenv("SUBPROCESS_DEFAULT_MOOD_IMPULSIVENESS", effective_mood["impulsiveness"]))
    effective_mood["laziness"] = float(os.getenv("SUBPROCESS_DEFAULT_MOOD_LAZINESS", effective_mood["laziness"]))
    effective_mood["proactivity"] = float(os.getenv("SUBPROCESS_DEFAULT_MOOD_PROACTIVITY", effective_mood["proactivity"]))
    effective_mood["extroversion"] = float(os.getenv("SUBPROCESS_DEFAULT_MOOD_EXTROVERSION", effective_mood["extroversion"]))
    effective_mood["introversion"] = float(os.getenv("SUBPROCESS_DEFAULT_MOOD_INTROVERSION", effective_mood["introversion"]))

    current_mood = effective_mood
    logger.info(f"Mood: Effective default_mood initialized: {current_mood} (Env > JSON > Default)")

_load_and_initialize_mood()

# --- Mood Management Functions ---
def get_current_mood() -> dict:
  """
  Returns the current mood of the system.

  Returns:
    A dictionary representing the current mood.
  """
  return current_mood.copy() # Return a copy to prevent direct modification

def update_mood(new_mood_aspects: dict) -> dict:
  """
  Updates the current mood with new aspects.

  Args:
    new_mood_aspects: A dictionary containing mood aspects to update.
                      Example: {"impulsiveness": 0.7, "laziness": 0.2}

  Returns:
    The updated current_mood dictionary.
  """
  global current_mood
  current_mood.update(new_mood_aspects)
  return current_mood.copy()

def drift_mood():
  """
  Simulates the gradual drifting of mood over time.

  This is a placeholder function. In a real implementation, this would
  involve more complex logic to simulate natural mood changes.
  For now, it makes a minor predefined change to 'laziness' or prints a message.
  """
  print("Mood drifting...")
  # Example of a minor predefined change:
  # current_laziness = current_mood.get("laziness", 0.5) # Use current_mood.get for safety
  # new_laziness = round(max(0, min(1, current_laziness + 0.01)), 2)
  # if new_laziness != current_laziness:
  #   update_mood({"laziness": new_laziness})
  #   logger.info(f"Laziness drifted to: {new_laziness}") # Use logger
  pass # No actual drift implemented for now, just logging

if __name__ == '__main__':
  # Example usage (for testing purposes)
  logger.info(f"Initial mood: {get_current_mood()}") # Use logger
  update_mood({"impulsiveness": 0.8, "proactivity": 0.2, "name": "Focused Test"}) # Added name for clarity
  logger.info(f"Updated mood: {get_current_mood()}")
  drift_mood()
  logger.info(f"Mood after drifting: {get_current_mood()}")

  # Test with environment variables (conceptual, requires setting them before running)
  # For example, if SUBPROCESS_DEFAULT_MOOD_IMPULSIVENESS=0.99 is set:
  # _load_and_initialize_mood() # Reload to see effect (if testing standalone)
  # logger.info(f"Mood after potential env var override: {get_current_mood()}")
  logger.info("Mood module test run finished.")
