"""
Manages in-memory context buffers for the Pathos Subconscious Node.

This module provides fixed-size buffers for storing recent conversation
and action context items. This context can be used by other components,
such as the `thinker` module, to inform thought generation.
"""

# --- Global Variables ---
conversation_context_buffer: list[str] = []
action_context_buffer: list[str] = []

# --- Constants ---
MAX_CONTEXT_ITEMS: int = 10

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
    "action": action_context_buffer.copy()
  }

def clear_all_context():
  """
  Clears all items from both conversation and action context buffers.
  """
  global conversation_context_buffer
  global action_context_buffer
  conversation_context_buffer = []
  action_context_buffer = []

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
