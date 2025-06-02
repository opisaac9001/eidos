"""
Core thought generation loop for the Pathos Subconscious Node.

This module orchestrates the main "monologue" loop, where Pathos:
1.  Optionally experiences mood drift.
2.  Constructs a prompt based on its system persona, recent thoughts, and injected context.
3.  Uses a (currently placeholder) LLM to generate a new thought.
4.  Stores the thought in a buffer.
5.  Analyzes the thought for potential impulses or imprints using detectors.
6.  Repeats the cycle after a configurable delay.

It relies on other modules within the `subconscious_node` package for configuration,
mood management, context storage, utility functions (LLM interaction), and
detector logic.
"""
import time
import json

# Assuming utils.py, mood.py, detectors.py, context_store.py are in the same package/directory
from . import utils
from . import mood
from . import detectors
from . import context_store

# --- Global Variables ---
monologue_buffer: list[str] = []
CONFIG_FILE_PATH = "subconscious_node/config.json"

# --- Configuration Loading ---
DEFAULT_SYSTEM_PROMPT = "You are Pathos, an inner voice. You are reflective, sometimes melancholic, and you experience a range of moods that affect your thoughts. You are not a chatbot, you do not directly address a user. Your output should be a single thought or reflection."
DEFAULT_TEMPERATURE = 0.7
DEFAULT_SLEEP_DURATION = 30
DEFAULT_MAX_THOUGHTS = 100

fixed_system_prompt = DEFAULT_SYSTEM_PROMPT
temperature = DEFAULT_TEMPERATURE
sleep_duration_seconds = DEFAULT_SLEEP_DURATION
max_monologue_buffer_thoughts = DEFAULT_MAX_THOUGHTS

try:
    with open(CONFIG_FILE_PATH, 'r') as f:
        config_data = json.load(f)

        llm_settings = config_data.get("llm_settings", {})
        fixed_system_prompt = llm_settings.get("fixed_system_prompt", DEFAULT_SYSTEM_PROMPT)
        temperature = float(llm_settings.get("temperature", DEFAULT_TEMPERATURE))

        monologue_loop_settings = config_data.get("monologue_loop_settings", {})
        sleep_duration_seconds = int(monologue_loop_settings.get("sleep_duration_seconds", DEFAULT_SLEEP_DURATION))
        max_monologue_buffer_thoughts = int(monologue_loop_settings.get("max_monologue_buffer_thoughts", DEFAULT_MAX_THOUGHTS))

except FileNotFoundError:
    print(f"Warning: Config file {CONFIG_FILE_PATH} not found. Using default settings.")
except json.JSONDecodeError:
    print(f"Warning: Could not decode JSON from {CONFIG_FILE_PATH}. Using default settings.")
except ValueError:
    print(f"Warning: Error parsing numeric values from {CONFIG_FILE_PATH}. Using default settings.")
except Exception as e:
    print(f"Warning: An unexpected error occurred while reading config: {e}. Using default settings.")


# --- Functions ---

def build_prompt() -> str:
    """
    Constructs the full prompt for the LLM based on current context and recent thoughts.

    Returns:
        The complete prompt string.
    """
    current_context_data = context_store.get_current_context()
    conversation_context_str = "\n".join(f"- {item}" for item in current_context_data.get("conversation", []))
    action_context_str = "\n".join(f"- {item}" for item in current_context_data.get("action", []))

    recent_thoughts_str = "\n".join(f"- {thought}" for thought in monologue_buffer[-10:]) # Show last 10 thoughts

    prompt_parts = [
        fixed_system_prompt,
        "\n--- RECENT THOUGHTS ---",
        recent_thoughts_str if recent_thoughts_str else "No recent thoughts yet.",
        "\n--- CURRENT CONTEXT (from Eidos) ---",
        "Conversation:",
        conversation_context_str if conversation_context_str else "No conversation context.",
        "\nAction:",
        action_context_str if action_context_str else "No action context.",
        "\n--- CURRENT THOUGHT ---",
        "Pathos reflects:" # Cue for the LLM
    ]
    return "\n".join(prompt_parts)

def monologue_loop():
    """
    The main loop for Pathos's subconscious thought generation.

    Continuously generates thoughts, checks for impulses/imprints,
    and manages the monologue buffer.
    """
    print("Pathos Subconscious Node: Monologue Loop starting...")
    print(f"Settings: Temp={temperature}, Sleep={sleep_duration_seconds}s, MaxThoughts={max_monologue_buffer_thoughts}")
    
    while True:
        # a. Drift mood
        mood.drift_mood() # Placeholder, might not do much yet

        # b. Get current mood
        current_mood_snapshot = mood.get_current_mood()
        # print(f"Debug: Current Mood: {current_mood_snapshot}") # For verbose debugging

        # c. Build prompt
        prompt_str = build_prompt()
        # print(f"Debug: Built Prompt:\n{prompt_str}\n--------------------") # For verbose debugging

        # d. Run LLM
        new_thought = utils.run_llm(prompt_str, temperature)

        # e. Print new thought
        print(f"\nPathos thinks: \"{new_thought}\" (Mood: {current_mood_snapshot.get('name', 'default') if isinstance(current_mood_snapshot, dict) else 'default'})")


        # f. Append to monologue buffer
        monologue_buffer.append(new_thought)

        # g. Manage buffer size
        if len(monologue_buffer) > max_monologue_buffer_thoughts:
            # print(f"Debug: Monologue buffer full ({len(monologue_buffer)} thoughts). Trimming oldest.")
            num_to_remove = len(monologue_buffer) - max_monologue_buffer_thoughts
            del monologue_buffer[:num_to_remove]

        # h. Check for impulse
        detectors.check_for_impulse(new_thought, current_mood_snapshot)

        # i. Check for imprint
        detectors.check_for_imprint(new_thought, current_mood_snapshot)

        # j. Sleep
        time.sleep(sleep_duration_seconds)

if __name__ == '__main__':
    # Example: Add some initial context before starting the loop
    context_store.add_conversation_context("User: I'm not sure what to do next.")
    context_store.add_action_context("user_hesitated_on_decision_screen")
    
    # Initialize mood with some values if it's empty (e.g. if config load failed)
    if not mood.get_current_mood():
        print("Info: Mood is empty, initializing with a basic mood for testing.")
        mood.update_mood({"name": "Neutral", "impulsiveness": 0.4, "laziness": 0.5})

    monologue_loop()
