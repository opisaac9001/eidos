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
  Provides a brief textual description of the current mood.

  Checks for a 'name' in the mood dictionary, otherwise provides a generic description.
  """
  if "name" in current_mood and current_mood["name"]:
    return str(current_mood["name"])
  # Example of summarizing based on dominant values (can be expanded)
  if current_mood.get("laziness", 0) > 0.7:
    return "Feeling quite lazy"
  if current_mood.get("proactivity", 0) > 0.7:
    return "Feeling proactive"
  return "Feeling thoughtful"

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
