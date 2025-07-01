"""
Manages in-memory context buffers for the Pathos Subconscious Node.

This module provides fixed-size buffers for storing recent conversation
and action context items. This context can be used by other components,
such as the `thinker` module, to inform thought generation.
"""

import logging # For logging body state updates

# --- Global Variables ---
conversation_context_buffer: list[str] = []
action_context_buffer: list[str] = []
fixation_buffer: list[str] = [] # Buffer for ongoing fixations

# Initial default body state
INITIAL_BODY_STATE = {
    "hunger_level": "Normal", # e.g., Normal, Peckish, Hungry, Full
    "energy_level": "Medium", # e.g., High, Medium, Low, Drained
    "is_tired": False         # Boolean
}
body_state: dict = INITIAL_BODY_STATE.copy()


# --- Constants ---
MAX_CONTEXT_ITEMS: int = 10
MAX_FIXATIONS: int = 3 # Max number of fixations to keep

# --- Logging Setup (basic if not already configured elsewhere) ---
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


# --- Context Management Functions ---

def add_conversation_context(context: str):
  """
  Adds a new conversation context item to the buffer.

  If the buffer size exceeds MAX_CONTEXT_ITEMS,
  the oldest items are removed to maintain the maximum size.

  Args:
    context: The string context to add.
  """
  global conversation_context_buffer
  conversation_context_buffer.append(context)
  # Maintain buffer size
  if len(conversation_context_buffer) > MAX_CONTEXT_ITEMS:
    conversation_context_buffer = conversation_context_buffer[-MAX_CONTEXT_ITEMS:]

def add_action_context(context: str):
  """
  Adds a new action context item to the buffer.

  If the buffer size exceeds MAX_CONTEXT_ITEMS,
  the oldest items are removed to maintain the maximum size.

  Args:
    context: The string context to add.
  """
  global action_context_buffer
  action_context_buffer.append(context)
  # Maintain buffer size
  if len(action_context_buffer) > MAX_CONTEXT_ITEMS:
    action_context_buffer = action_context_buffer[-MAX_CONTEXT_ITEMS:]

def get_current_context() -> dict:
  """
  Retrieves the current conversation and action contexts.

  Returns:
    A dictionary containing 'conversation' and 'action' context buffers.
    Example: {"conversation": ["user: hello", "bot: hi"], "action": ["clicked_button_A"]}
  """
  return {
    "conversation": conversation_context_buffer.copy(), # Return copies
    "action": action_context_buffer.copy(),
    "fixations": fixation_buffer.copy(), # Also include fixations
    "body_state": body_state.copy() # Include body state
  }

# --- Body State Management Functions ---

def update_body_state(new_state: dict):
  """
  Updates the current body state with new values.

  Args:
    new_state: A dictionary containing body state aspects to update.
               Example: {"energy_level": "Low", "is_tired": True}
  """
  global body_state
  body_state.update(new_state)
  logger.debug(f"Body state updated: {body_state}")

def get_body_state() -> dict:
  """
  Retrieves the current body state.

  Returns:
    A copy of the body_state dictionary.
  """
  return body_state.copy()

# --- Fixation Management Functions ---

def add_fixation(fixation: str):
  """
  Adds a new fixation to the buffer.

  Avoids adding duplicates. If the buffer size exceeds MAX_FIXATIONS,
  the oldest fixations are removed.

  Args:
    fixation: The string fixation to add.
  """
  global fixation_buffer
  if fixation not in fixation_buffer: # Avoid duplicates
    fixation_buffer.append(fixation)
    # Maintain buffer size
    if len(fixation_buffer) > MAX_FIXATIONS:
      fixation_buffer = fixation_buffer[-MAX_FIXATIONS:]

def get_current_fixations() -> list[str]:
  """
  Retrieves the current list of fixations.

  Returns:
    A copy of the fixation_buffer.
  """
  return fixation_buffer.copy()

def remove_fixation(fixation: str):
  """
  Removes a specific fixation from the buffer.

  Args:
    fixation: The string fixation to remove.
  """
  global fixation_buffer
  if fixation in fixation_buffer:
    fixation_buffer.remove(fixation)

def clear_all_context():
  """
  Clears all items from conversation, action, and fixation context buffers.
  Resets body_state to its initial default values.
  """
  global conversation_context_buffer, action_context_buffer, fixation_buffer, body_state
  conversation_context_buffer = []
  action_context_buffer = []
  fixation_buffer = [] # Clear fixations as well
  body_state = INITIAL_BODY_STATE.copy() # Reset body state to defaults
  logger.info("All context cleared, body state reset to defaults.")

if __name__ == '__main__':
  # Example Usage (for testing purposes)
  print("Initial context:", get_current_context())

  add_conversation_context("User: Hello there!")
  add_conversation_context("Pathos: (Thinking about the greeting)")
  add_action_context("user_opened_chat_window")

  print("Context after additions:", get_current_context())

  for i in range(12):
    add_conversation_context(f"Conversation line {i+1}")
    add_action_context(f"Action event {i+1}")

  print(f"Context after exceeding MAX_CONTEXT_ITEMS ({MAX_CONTEXT_ITEMS}):")
  print("Conversation length:", len(get_current_context()["conversation"]))
  print("Action length:", len(get_current_context()["action"]))
  assert len(get_current_context()["conversation"]) == MAX_CONTEXT_ITEMS
  assert len(get_current_context()["action"]) == MAX_CONTEXT_ITEMS

  print("Last conversation item:", get_current_context()["conversation"][-1])
  print("Last action item:", get_current_context()["action"][-1])

  clear_all_context()
  print("Context after clearing:", get_current_context())
  assert len(get_current_context()["conversation"]) == 0
  assert len(get_current_context()["action"]) == 0
  assert len(get_current_fixations()) == 0

  print("\n--- Testing Fixations ---")
  add_fixation("That catchy tune from the cafe")
  add_fixation("The weird dream from last night")
  print("Fixations after 2 adds:", get_current_fixations())
  assert len(get_current_fixations()) == 2

  add_fixation("That catchy tune from the cafe") # Duplicate, should not add
  print("Fixations after duplicate add:", get_current_fixations())
  assert len(get_current_fixations()) == 2

  add_fixation("The deadline for the tech report")
  print(f"Fixations after 3rd add (should be {MAX_FIXATIONS}):", get_current_fixations())
  assert len(get_current_fixations()) == MAX_FIXATIONS

  add_fixation("What to have for dinner") # Exceeds MAX_FIXATIONS
  print(f"Fixations after 4th add (should still be {MAX_FIXATIONS}):", get_current_fixations())
  assert len(get_current_fixations()) == MAX_FIXATIONS
  assert "That catchy tune from the cafe" not in get_current_fixations() # Oldest should be gone
  assert "What to have for dinner" in get_current_fixations()

  remove_fixation("The weird dream from last night")
  print("Fixations after removing 'The weird dream':", get_current_fixations())
  assert len(get_current_fixations()) == MAX_FIXATIONS - 1
  assert "The weird dream from last night" not in get_current_fixations()

  remove_fixation("Non-existent fixation") # Should not error
  print("Fixations after removing non-existent:", get_current_fixations())
  assert len(get_current_fixations()) == MAX_FIXATIONS - 1

  clear_all_context()
  print("Fixations after clearing context again:", get_current_fixations())
  assert len(get_current_fixations()) == 0
  print("Body state after clearing context:", get_body_state())
  assert get_body_state()["energy_level"] == "Medium"


  print("\n--- Testing Body State ---")
  print("Initial body state:", get_body_state())
  update_body_state({"energy_level": "Low", "is_tired": True, "hunger_level": "Peckish"})
  print("Body state after update:", get_body_state())
  assert get_body_state()["energy_level"] == "Low"
  assert get_body_state()["is_tired"] is True

  update_body_state({"energy_level": "High", "new_custom_feeling": "Rested"}) # Test adding a new key
  print("Body state after adding custom key:", get_body_state())
  assert get_body_state()["new_custom_feeling"] == "Rested"


  clear_all_context()
  print("Body state after second clearing:", get_body_state())
  assert get_body_state()["energy_level"] == "Medium" # Should be reset
  assert "new_custom_feeling" not in get_body_state() # Custom key should be gone
