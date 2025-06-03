"""
Core thought generation loop for the Pathos Subconscious Node.
"""
import time
import json
import logging
import os
import random # Added import for random
from typing import Dict, List # For type hinting loaded_wildcards

# Assuming utils.py, mood.py, detectors.py, context_store.py are in the same package/directory
from . import utils
from . import mood
from . import detectors
from . import context_store

# --- Logging Setup ---
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Node State Definitions ---
NODE_STATE_AWAKE_THINKING = "AWAKE_THINKING"
NODE_STATE_SLEEPING_DREAMING = "SLEEPING_DREAMING"
current_node_state = NODE_STATE_AWAKE_THINKING

# --- Global Variables ---
monologue_buffer: list[str] = []
CONFIG_FILE_PATH = "subconscious_node/config.json"
loaded_wildcards: Dict[str, List[str]] = {} # Ensure type hint matches load_wildcards return

# --- Configuration Loading ---
DEFAULT_SYSTEM_PROMPT = "You are Pathos, an inner voice..."
DEFAULT_TEMPERATURE = 0.7
DEFAULT_SLEEP_DURATION = 30
DEFAULT_MAX_THOUGHTS = 100
DEFAULT_WILDCARD_PATH = "../wildcards/"

fixed_system_prompt = DEFAULT_SYSTEM_PROMPT
temperature = DEFAULT_TEMPERATURE
sleep_duration_seconds = DEFAULT_SLEEP_DURATION
max_monologue_buffer_thoughts = DEFAULT_MAX_THOUGHTS
wildcard_folder_path = DEFAULT_WILDCARD_PATH

try:
    config_path_abs = os.path.join(os.path.dirname(__file__), 'config.json')
    if not os.path.exists(config_path_abs):
        config_path_abs = CONFIG_FILE_PATH

    with open(config_path_abs, 'r') as f:
        config_data = json.load(f)

        llm_settings = config_data.get("llm_settings", {})
        fixed_system_prompt = llm_settings.get("fixed_system_prompt", DEFAULT_SYSTEM_PROMPT)
        temperature = float(llm_settings.get("temperature", DEFAULT_TEMPERATURE))

        monologue_loop_settings = config_data.get("monologue_loop_settings", {})
        sleep_duration_seconds = int(monologue_loop_settings.get("sleep_duration_seconds", DEFAULT_SLEEP_DURATION))
        max_monologue_buffer_thoughts = int(monologue_loop_settings.get("max_monologue_buffer_thoughts", DEFAULT_MAX_THOUGHTS))

        wildcard_folder_path = config_data.get("wildcard_folder_path", DEFAULT_WILDCARD_PATH)
        logger.info(f"Configuration loaded successfully from {config_path_abs}")
        logger.info(f"Wildcard folder path from config: {wildcard_folder_path}")

except FileNotFoundError:
    logger.warning(f"Config file {CONFIG_FILE_PATH} (or {config_path_abs}) not found. Using default settings.")
except json.JSONDecodeError:
    logger.warning(f"Could not decode JSON from {CONFIG_FILE_PATH} (or {config_path_abs}). Using default settings.")
except ValueError:
    logger.warning(f"Error parsing numeric values from {CONFIG_FILE_PATH} (or {config_path_abs}). Using default settings.")
except Exception as e:
    logger.warning(f"An unexpected error occurred while reading config: {e}. Using default settings.")

# --- Load Wildcards ---
try:
    thinker_script_dir = os.path.dirname(__file__)
    loaded_wildcards = utils.load_wildcards(thinker_script_dir, wildcard_folder_path)
    if loaded_wildcards:
        logger.info(f"Successfully loaded {len(loaded_wildcards)} wildcard categories.")
        for category, items in loaded_wildcards.items():
            logger.debug(f"Wildcard category '{category}' loaded with {len(items)} items.")
    else:
        logger.warning("No wildcard categories were loaded. Dream prompts might be less varied.")
except Exception as e:
    logger.error(f"An error occurred during wildcard loading: {e}", exc_info=True)

# --- Functions ---

def build_prompt() -> str:
    """Constructs the standard prompt for the AWAKE_THINKING state."""
    current_context_data = context_store.get_current_context()
    conversation_context_str = "\n".join(f"- {item}" for item in current_context_data.get("conversation", []))
    action_context_str = "\n".join(f"- {item}" for item in current_context_data.get("action", []))
    recent_thoughts_str = "\n".join(f"- {thought}" for thought in monologue_buffer[-10:])

    prompt_parts = [
        fixed_system_prompt, # This is the general system prompt from config
        "\n--- RECENT THOUGHTS ---",
        recent_thoughts_str if recent_thoughts_str else "No recent thoughts yet.",
        "\n--- CURRENT CONTEXT (from Eidos) ---",
        "Conversation:",
        conversation_context_str if conversation_context_str else "No conversation context.",
        "\nAction:",
        action_context_str if action_context_str else "No action context.",
        "\n--- CURRENT THOUGHT ---",
        "Pathos reflects:"
    ]
    return "\n".join(prompt_parts)

def construct_dream_prompt(daily_summary_text: str, wildcards_dict: Dict[str, List[str]]) -> str:
    """
    Constructs a prompt for the LLM for dream generation.
    """
    dream_system_prompt = (
        "You are Pathos, deeply asleep and dreaming. Weave a surreal, associative, and "
        "fragmented narrative based on the following themes and ideas. Let connections be "
        "loose and imagery vivid. Do not be coherent. Embrace the bizarre. Focus on "
        "generating a stream of dream content. Output only the dream content itself, "
        "without any preamble or self-reference like 'I dreamt' or 'My dream was'. "
        "Keep dream fragments relatively short, 1-3 sentences."
    )
    prompt_segments = [dream_system_prompt]

    if daily_summary_text:
        prompt_segments.append(f"\n\nEchoes from the waking world (recent experiences and data points):\n{daily_summary_text}\n")

    if wildcards_dict:
        prompt_segments.append("\nFleeting images, concepts, and sensations drift by:\n")
        num_wildcard_grabs = random.randint(3, 7)
        grabbed_items = []
        for _ in range(num_wildcard_grabs):
            if not wildcards_dict: break
            random_category_key = random.choice(list(wildcards_dict.keys()))
            if wildcards_dict[random_category_key]:
                random_item = random.choice(wildcards_dict[random_category_key])
                grabbed_items.append(random_item)

        # Mix them a bit, or just list them
        if grabbed_items:
            # Simple list:
            for item in grabbed_items:
                prompt_segments.append(f"- {item}\n")
            # Could also try a more narrative injection later, e.g.,
            # "A sense of {emotion}, the color {color}, the sound of {sound_object}..."

    prompt_segments.append("\nPathos dreams:")
    return "".join(prompt_segments)


def monologue_loop():
    """
    The main loop for Pathos's subconscious thought generation.
    """
    global current_node_state
    logger.info("Pathos Subconscious Node: Monologue Loop starting...")
    logger.info(f"Initial Node State: {current_node_state}")
    logger.info(f"Settings: Temp={temperature}, Sleep={sleep_duration_seconds}s, MaxThoughts={max_monologue_buffer_thoughts}")

    while True:
        if current_node_state == NODE_STATE_AWAKE_THINKING:
            logger.info(f"Node state: {current_node_state}. Generating standard thought.")
            mood.drift_mood()
            current_mood_snapshot = mood.get_current_mood()
            logger.debug(f"Debug: Current Mood: {current_mood_snapshot}")
            prompt_str = build_prompt()
            logger.debug(f"Debug: Built Prompt (first 200 chars):\n{prompt_str[:200]}\n--------------------")
            new_thought = utils.run_llm(prompt_str, temperature)
            mood_name = current_mood_snapshot.get('name', 'default') if isinstance(current_mood_snapshot, dict) else 'default'
            logger.info(f"Pathos thinks: \"{new_thought}\" (Mood: {mood_name})")
            monologue_buffer.append(new_thought)
            if len(monologue_buffer) > max_monologue_buffer_thoughts:
                logger.debug(f"Monologue buffer full ({len(monologue_buffer)} thoughts). Trimming oldest.")
                num_to_remove = len(monologue_buffer) - max_monologue_buffer_thoughts
                del monologue_buffer[:num_to_remove]
            detectors.check_for_impulse(new_thought, current_mood_snapshot)
            detectors.check_for_imprint(new_thought, current_mood_snapshot)
            time.sleep(sleep_duration_seconds)

        elif current_node_state == NODE_STATE_SLEEPING_DREAMING:
            logger.info(f"Node state: {current_node_state}. Constructing dream prompt.")

            # Placeholder for daily summary - this will be replaced by actual data from Eidos.
            placeholder_daily_summary = (
                "User interactions involved planning a trip and discussing a difficult decision. "
                "Pathos experienced a brief moment of joy followed by a period of intense focus. "
                "Some system errors were noted internally. The concept of 'freedom' was mentioned by the user."
            )

            dream_prompt = construct_dream_prompt(placeholder_daily_summary, loaded_wildcards)
            logger.debug(f"Constructed Dream Prompt (first 300 chars):\n{dream_prompt[:300]}\n--------------------")

            # The actual LLM call for dream generation and snippet processing will be in the next step.
            # For now, we just log that we would be generating a dream.
            logger.info("Dream prompt constructed. (LLM call for dream generation will be implemented next).")
            # Simulating a dream being generated and processed without actual LLM call for this step:
            simulated_dream_fragment = f"A fleeting image of {random.choice(loaded_wildcards.get('animals', ['something'])) if loaded_wildcards else 'something'} in a field of {random.choice(loaded_wildcards.get('colors', ['strange'])) if loaded_wildcards else 'strange'} light."
            logger.info(f"Pathos (simulated) dreams: \"{simulated_dream_fragment}\"")

            dream_mode_sleep_duration = int(sleep_duration_seconds / 2) if sleep_duration_seconds > 2 else 1
            logger.debug(f"Dreaming state: sleeping for {dream_mode_sleep_duration}s.")
            time.sleep(dream_mode_sleep_duration)

        else:
            logger.error(f"Unknown node state: {current_node_state}. Defaulting to AWAKE_THINKING behavior for this cycle.")
            time.sleep(sleep_duration_seconds)
            current_node_state = NODE_STATE_AWAKE_THINKING
            logger.warning("Node state reset to AWAKE_THINKING due to unknown prior state.")

if __name__ == '__main__':
    context_store.add_conversation_context("User: I'm not sure what to do next.")
    context_store.add_action_context("user_hesitated_on_decision_screen")
    if not mood.get_current_mood():
        logger.info("Info: Mood is empty, initializing with a basic mood for testing.")
        mood.update_mood({"name": "Neutral", "impulsiveness": 0.4, "laziness": 0.5})

    # Example to test dreaming state for a few cycles if needed:
    # current_node_state = NODE_STATE_SLEEPING_DREAMING
    # logger.info(f"--- Overriding initial state for testing: {current_node_state} ---")
    # for _ in range(5): # Simulate a few dream cycles
    #     monologue_loop() # Call directly if you want to step through for interactive testing
    # current_node_state = NODE_STATE_AWAKE_THINKING

    monologue_loop()
