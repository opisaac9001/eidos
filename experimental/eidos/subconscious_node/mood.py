"""
Manages the mood state of the Pathos Subconscious Node.

This module is responsible for:
- Initializing the mood from a configuration file.
- Providing functions to get and update the current mood.
- Simulating mood changes over time (currently a placeholder).
"""
import json

# --- Global Variables ---
current_mood = {}
CONFIG_FILE_PATH = "subconscious_node/config.json"

# --- Initialization ---
def _load_default_mood():
  """Loads the default mood from the config file."""
  global current_mood
  try:
    with open(CONFIG_FILE_PATH, 'r') as f:
      config_data = json.load(f)
      current_mood = config_data.get("mood_settings", {}).get("default_mood", {}).copy()
      if not current_mood:
        print(f"Warning: 'default_mood' not found or empty in {CONFIG_FILE_PATH}. Initializing with an empty mood.")
  except FileNotFoundError:
    print(f"Error: Config file {CONFIG_FILE_PATH} not found. Initializing with an empty mood.")
    current_mood = {} # Initialize with empty dict if file not found
  except json.JSONDecodeError:
    print(f"Error: Could not decode JSON from {CONFIG_FILE_PATH}. Initializing with an empty mood.")
    current_mood = {} # Initialize with empty dict if JSON is invalid

_load_default_mood()

# --- Mood Management Functions ---
def get_current_mood() -> dict:
  """
  Returns the current mood of the system.

  Returns:
    A dictionary representing the current mood.
  """
  return current_mood.copy() # Return a copy to prevent direct modification

def get_brief_mood_description() -> str:
  """
  Provides a brief textual description of the current mood based on various dimensions.
  """
  # Use .get(key, 0.0) to safely access mood dimensions, defaulting to neutral if key is missing.
  mood_name = current_mood.get("name")
  if mood_name and isinstance(mood_name, str) and mood_name.strip():
    return mood_name.strip()

  impulsiveness = current_mood.get("impulsiveness", 0.0)
  laziness = current_mood.get("laziness", 0.0)
  proactivity = current_mood.get("proactivity", 0.0)
  extroversion = current_mood.get("extroversion", 0.0)
  introversion = current_mood.get("introversion", 0.0)
  # Define thresholds (these could be constants if used elsewhere)
  HIGH = 0.7
  LOW = 0.3
  MID = 0.5 # For general states

  # 1. Single dimension checks (prioritized)
  if proactivity > HIGH and laziness < LOW:
    return "Feeling productive and energetic."
  elif laziness > HIGH and proactivity < LOW:
    return "Feeling pretty sluggish and unmotivated."
  elif extroversion > HIGH and introversion < LOW:
    return "Feeling outgoing and sociable."
  elif introversion > HIGH and extroversion < LOW:
    return "Feeling quiet and introspective."
  elif impulsiveness > HIGH: # This is a standalone check as per requirements
    return "Feeling a bit impulsive today."

  # 2. Combination checks (if no strong single dimension dominates)
  # These are for when one dimension is high but its counterpart isn't necessarily low.
  elif proactivity > HIGH:
    return "Motivated to do something."
  elif laziness > HIGH:
    return "Feeling quite lazy."
  elif extroversion > HIGH:
    return "Leaning towards being sociable."
  elif introversion > HIGH:
    return "Feeling like keeping to myself."

  # 3. General states (if specific thresholds not met clearly but still leaning one way)
  elif impulsiveness > MID: # Using MID for "a bit restless"
    return "A bit restless."
  elif proactivity > MID:
    return "Generally feeling capable."
  # For extroversion/introversion, it's tricky if both are mid.
  # Let's consider if one is notably higher than the other, even if not > HIGH.
  # Or if one is mid and the other is low.
  elif extroversion > MID and introversion < MID: # More extroverted than introverted
      return "Open to interaction."
  elif introversion > MID and extroversion < MID: # More introverted than extroverted
      return "Content with my own thoughts."
  # If both are around mid, or both high/low without clear dominance from above rules,
  # it might be a mixed state or closer to neutral.

  # Fallback default
  return "Feeling thoughtful" # Default if no specific strong moods detected by above heuristics

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
  # current_laziness = current_mood.get("laziness", 0.5)
  # new_laziness = round(max(0, min(1, current_laziness + 0.01)), 2) # Ensure it stays between 0 and 1
  # if new_laziness != current_laziness:
  #   update_mood({"laziness": new_laziness})
  #   print(f"Laziness drifted to: {new_laziness}")

if __name__ == '__main__':
  # Example usage (for testing purposes)
  print(f"Initial mood: {get_current_mood()}")
  update_mood({"impulsiveness": 0.8, "proactivity": 0.2})
  print(f"Updated mood: {get_current_mood()}")
  drift_mood()
  print(f"Mood after drifting: {get_current_mood()}")

  # Test error case: config file missing (requires renaming the file temporarily)
  # _load_default_mood() # This would now print an error and initialize an empty mood
  # print(f"Mood after trying to load missing config: {get_current_mood()}")
