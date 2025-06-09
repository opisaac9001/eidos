"""
Core thought generation loop for the Pathos Subconscious Node.
"""
import time
import json
import logging
import os
import random
import threading # Added for thread management
from typing import Dict, List, Optional # Added Optional for monologue_thread type hint

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
NODE_STATE_IDLE = "IDLE" # A state where the loop is not actively running thoughts
current_node_state = NODE_STATE_IDLE # Start in IDLE, loop started by API call

# --- Global Variables & Thread Management ---
monologue_buffer: list[str] = []
dream_buffer: list[str] = [] # Buffer for storing dream fragments
current_daily_summary_for_dreaming: str | None = None # Populated by Eidos control command
CONFIG_FILE_PATH = "subconscious_node/config.json"
loaded_wildcards: Dict[str, List[str]] = {} # Ensure type hint matches load_wildcards return

monologue_thread: Optional[threading.Thread] = None
stop_monologue_event = threading.Event()


# --- Configuration Loading (Mirrors logic in utils.py for now) ---
# TODO: Centralize config loading in a shared module/function.

# Default values used if not found in config.json or environment variables
DEFAULT_SYSTEM_PROMPT = "You are Pathos, an inner voice..."
DEFAULT_TEMPERATURE = 0.75 # Aligned with last config update
DEFAULT_SLEEP_DURATION = 30
DEFAULT_MAX_THOUGHTS = 100
DEFAULT_WILDCARD_PATH = "../wildcards/" # Should match utils.py default

# Initialize with hardcoded defaults
fixed_system_prompt = DEFAULT_SYSTEM_PROMPT
temperature = DEFAULT_TEMPERATURE
sleep_duration_seconds = DEFAULT_SLEEP_DURATION
max_monologue_buffer_thoughts = DEFAULT_MAX_THOUGHTS
wildcard_folder_path = DEFAULT_WILDCARD_PATH # This specific var is for wildcard loading path

# Load from config.json
config_data_thinker = {}
config_file_path_thinker = os.path.join(os.path.dirname(__file__), 'config.json') # Consistent with CONFIG_FILE_PATH global

if os.path.exists(config_file_path_thinker):
    try:
        with open(config_file_path_thinker, 'r') as f:
            config_data_thinker = json.load(f)
        logger.info(f"Thinker: Successfully loaded configuration from {config_file_path_thinker}")
    except Exception as e:
        logger.error(f"Thinker: Error loading config from {config_file_path_thinker}: {e}. Using defaults or env vars.", exc_info=True)
else:
    logger.info(f"Thinker: Config file {config_file_path_thinker} not found. Using defaults or env vars.")

# Apply overrides: Env Var -> Config File -> Hardcoded Default
# LLM Settings
_llm_settings = config_data_thinker.get("llm_settings", {})
_json_system_prompt = _llm_settings.get("fixed_system_prompt", DEFAULT_SYSTEM_PROMPT)
_system_prompt_file = os.getenv("SUBPROCESS_LLM_SYSTEM_PROMPT_FILE")
if _system_prompt_file:
    try:
        with open(_system_prompt_file, 'r') as f_prompt:
            fixed_system_prompt = f_prompt.read()
            logger.info(f"Thinker: Loaded system prompt from file: {_system_prompt_file}")
    except Exception as e_prompt:
        fixed_system_prompt = _json_system_prompt
        logger.error(f"Thinker: Failed to load system prompt from file '{_system_prompt_file}': {e_prompt}. Using JSON or default.")
else:
    fixed_system_prompt = _json_system_prompt

_json_temp = _llm_settings.get("temperature", DEFAULT_TEMPERATURE)
temperature = float(os.getenv("SUBPROCESS_LLM_TEMPERATURE", _json_temp))

# Monologue Loop Settings
_monologue_loop_settings = config_data_thinker.get("monologue_loop_settings", {})
_json_sleep_duration = _monologue_loop_settings.get("sleep_duration_seconds", DEFAULT_SLEEP_DURATION)
sleep_duration_seconds = int(os.getenv("SUBPROCESS_SLEEP_DURATION_SECONDS", _json_sleep_duration))

_json_max_buffer_thoughts = _monologue_loop_settings.get("max_monologue_buffer_thoughts", DEFAULT_MAX_THOUGHTS)
max_monologue_buffer_thoughts = int(os.getenv("SUBPROCESS_MAX_BUFFER_THOUGHTS", _json_max_buffer_thoughts))

# Wildcard path (used for loading wildcards)
_json_wildcard_path = config_data_thinker.get("wildcard_folder_path", DEFAULT_WILDCARD_PATH)
wildcard_folder_path = os.getenv("SUBPROCESS_WILDCARD_RELATIVE_PATH", _json_wildcard_path)


logger.info(f"Thinker Effective fixed_system_prompt: '{fixed_system_prompt[:100]}...'")
logger.info(f"Thinker Effective temperature: {temperature}")
logger.info(f"Thinker Effective sleep_duration_seconds: {sleep_duration_seconds}")
logger.info(f"Thinker Effective max_monologue_buffer_thoughts: {max_monologue_buffer_thoughts}")
logger.info(f"Thinker Effective wildcard_folder_path (for loading): '{wildcard_folder_path}'")


# --- Load Wildcards ---
# This uses the `wildcard_folder_path` determined above.
try:
    thinker_script_dir = os.path.dirname(__file__) # directory of thinker.py
    # utils.load_wildcards expects the path from where utils.py is, to the wildcards folder.
    # If wildcard_folder_path is absolute, os.path.join might not behave as expected.
    # The WILDCARD_RELATIVE_PATH in utils.py is relative to utils.py itself.
    # Here, wildcard_folder_path is directly used by utils.load_wildcards, assuming it's correctly relative or absolute.
    # For consistency, we pass `thinker_script_dir` and `wildcard_folder_path` (which might be `../wildcards` or an absolute path from env).
    loaded_wildcards = utils.load_wildcards(thinker_script_dir, wildcard_folder_path)
    if loaded_wildcards:
        logger.info(f"Thinker: Successfully loaded {len(loaded_wildcards)} wildcard categories using path: {wildcard_folder_path}.")
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
    ]

    # Add significant memories to the prompt
    significant_memories_list = current_context_data.get("significant_memories", [])
    significant_memories_str = "\n".join(f"- {mem}" for mem in significant_memories_list) if significant_memories_list else "No specific long-term memories are at the forefront of Pathos's mind right now."

    prompt_parts.extend([
        "\n--- RECENT SIGNIFICANT MEMORIES (from Eidos) ---",
        significant_memories_str,
        "\n--- CURRENT THOUGHT ---",
        "Pathos reflects:"
    ])
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
    # Max dream fragments can be configured separately if needed, using max_monologue_buffer_thoughts for now.
    max_dream_buffer_fragments = max_monologue_buffer_thoughts

    while not stop_monologue_event.is_set():
        if current_node_state == NODE_STATE_AWAKE_THINKING:
            # Check event again before potentially long operation
            if stop_monologue_event.is_set(): break
            logger.info(f"Node state: {current_node_state}. Generating standard thought.")
            mood.drift_mood()
            current_mood_snapshot = mood.get_current_mood()
            logger.debug(f"Debug: Current Mood: {current_mood_snapshot}")
            prompt_str = build_prompt()
            logger.debug(f"Debug: Built Prompt (first 200 chars):\n{prompt_str[:200]}\n--------------------")
            new_thought = utils.run_llm(prompt_str, temperature) # This can return error strings

            if new_thought and not new_thought.startswith(("[Error:", "[Warning:")):
                mood_name = current_mood_snapshot.get('name', 'default') if isinstance(current_mood_snapshot, dict) else 'default'
                logger.info(f"Pathos thinks: \"{new_thought}\" (Mood: {mood_name})")
                monologue_buffer.append(new_thought)
                if len(monologue_buffer) > max_monologue_buffer_thoughts:
                    logger.debug(f"Monologue buffer full ({len(monologue_buffer)} thoughts). Trimming oldest.")
                    num_to_remove = len(monologue_buffer) - max_monologue_buffer_thoughts
                    del monologue_buffer[:num_to_remove]
                detectors.check_for_impulse(new_thought, current_mood_snapshot)
                detectors.check_for_imprint(new_thought, current_mood_snapshot)
            elif new_thought: # It's an error or warning string from run_llm
                logger.warning(f"LLM generation issue for standard thought: {new_thought}")
            else: # Empty or None result, also an issue
                logger.error("LLM generation returned empty or None for standard thought.")

            # Use event.wait for stoppable sleep
            if stop_monologue_event.is_set(): break
            stop_monologue_event.wait(timeout=sleep_duration_seconds)

        elif current_node_state == NODE_STATE_SLEEPING_DREAMING:
            if stop_monologue_event.is_set(): break
            logger.info(f"Node state: {current_node_state}. Constructing dream prompt.")
            mood.drift_mood() # Mood can also drift during sleep, perhaps more erratically

            summary_for_prompt = current_daily_summary_for_dreaming
            if summary_for_prompt is None:
                logger.warning("Daily summary for dreaming is None. Using a fallback message for dream prompt.")
                summary_for_prompt = "The day's events are a blur, like faded photographs."

            dream_prompt = construct_dream_prompt(summary_for_prompt, loaded_wildcards)
            logger.debug(f"Constructed Dream Prompt (first 300 chars):\n{dream_prompt[:300]}\n--------------------")

            # Use a slightly higher temperature for dreaming, capped at a reasonable value (e.g., 1.0 or 1.1)
            dream_temperature = min(temperature + 0.15, 1.1) # Ensure temperature is the global thinker var
            logger.debug(f"Using temperature {dream_temperature} for dream generation.")

            dream_fragment = utils.run_llm(dream_prompt, dream_temperature) # This can return error strings

            if dream_fragment and not dream_fragment.startswith(("[Error:", "[Warning:")):
                logger.info(f"Pathos dreams: \"{dream_fragment}\"")
                dream_buffer.append(dream_fragment)
                if len(dream_buffer) > max_dream_buffer_fragments:
                    logger.debug(f"Dream buffer full ({len(dream_buffer)} fragments). Trimming oldest.")
                    num_to_remove_dreams = len(dream_buffer) - max_dream_buffer_fragments
                    del dream_buffer[:num_to_remove_dreams]
                # Optionally, pass to a specialized detector for dream content later
                # detectors.check_for_dream_imprint(dream_fragment, mood.get_current_mood()) # Assuming mood is still relevant
            elif dream_fragment: # It's an error or warning string
                logger.warning(f"LLM generation issue for dream fragment: {dream_fragment}")
            else: # Empty or None result
                logger.error("LLM generation returned empty or None for dream fragment.")

            # Dreams might occur more rapidly or with different pacing than thoughts
            dream_mode_sleep_duration = int(sleep_duration_seconds / 1.5) if sleep_duration_seconds > 3 else 2
            logger.debug(f"Dreaming state: sleeping for {dream_mode_sleep_duration}s.")

            if stop_monologue_event.is_set(): break
            stop_monologue_event.wait(timeout=dream_mode_sleep_duration)

        elif current_node_state == NODE_STATE_IDLE:
            logger.debug(f"Node state is {NODE_STATE_IDLE}. Monologue loop is quiet, checking event.")
            # Sleep for a short duration to prevent busy-waiting if in IDLE but thread not stopped.
            # This allows the loop to naturally exit if stop_monologue_event gets set.
            if stop_monologue_event.is_set(): break
            stop_monologue_event.wait(timeout=1.0) # Check every second

        else: # Unknown state
            logger.error(f"Unknown node state: {current_node_state}. Monologue loop pausing. Please set to known state (AWAKE_THINKING, SLEEPING_DREAMING, IDLE).")
            if stop_monologue_event.is_set(): break
            stop_monologue_event.wait(timeout=sleep_duration_seconds) # Wait before re-checking state or stop event

    logger.info("Monologue loop has stopped.")


def start_monologue_loop_thread():
    global monologue_thread, stop_monologue_event
    if monologue_thread is None or not monologue_thread.is_alive():
        stop_monologue_event.clear()
        monologue_thread = threading.Thread(target=monologue_loop, daemon=True)
        monologue_thread.start()
        logger.info("Monologue loop thread started.")
    else:
        logger.info("Monologue loop thread is already running.")

def stop_monologue_loop_thread():
    global monologue_thread, stop_monologue_event
    if monologue_thread is not None and monologue_thread.is_alive():
        logger.info("Stopping monologue loop thread...")
        stop_monologue_event.set()
        # Use a timeout slightly longer than the typical loop sleep times to allow graceful exit.
        # The monologue_loop's use of stop_monologue_event.wait() should make it responsive.
        join_timeout = max(sleep_duration_seconds, int(sleep_duration_seconds / 1.5) if sleep_duration_seconds > 3 else 2) + 2
        monologue_thread.join(timeout=join_timeout)
        if monologue_thread.is_alive():
            logger.warning("Monologue loop thread did not stop in time.")
        else:
            logger.info("Monologue loop thread stopped.")
        monologue_thread = None # Clear the thread object after stopping
    else:
        logger.info("Monologue loop thread is not running or already stopped.")


if __name__ == '__main__':
    context_store.add_conversation_context("User: I'm not sure what to do next.")
    context_store.add_action_context("user_hesitated_on_decision_screen")
    if not mood.get_current_mood():
        logger.info("Info: Mood is empty, initializing with a basic mood for testing.")
        mood.update_mood({"name": "Neutral", "impulsiveness": 0.4, "laziness": 0.5})

    # Example to test dreaming state for a few cycles if needed:
    # current_node_state = NODE_STATE_SLEEPING_DREAMING # Set initial state for testing
    # start_monologue_loop_thread() # Start the loop in a thread
    # logger.info(f"--- Main thread: monologue_loop started for testing {current_node_state} ---")
    #
    # # Let it run for a bit
    # time.sleep(15) # e.g., run for 15 seconds
    #
    # logger.info("--- Main thread: attempting to switch to AWAKE_THINKING ---")
    # current_node_state = NODE_STATE_AWAKE_THINKING # Switch state
    # time.sleep(15)
    #
    # logger.info("--- Main thread: attempting to stop monologue_loop ---")
    # stop_monologue_loop_thread()
    # logger.info("--- Main thread: monologue_loop hopefully stopped ---")

    # Default behavior for __main__ could be to start it if not auto-started by FastAPI.
    # However, with FastAPI startup/shutdown events, direct __main__ execution of monologue_loop
    # is less relevant unless for specific standalone testing.
    logger.info("Thinker module __main__ finished. Loop is not started by default here; use API or test functions.")
