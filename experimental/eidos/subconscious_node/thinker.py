"""
Core thought generation loop for the Pathos Subconscious Node.
"""
import time
import json
import logging
import os
import random
from datetime import datetime # Added datetime import
import threading # Added for thread management
from typing import Dict, List, Optional # Added Optional for monologue_thread type hint

# Assuming utils.py, mood.py, detectors.py, context_store.py are in the same package/directory
from . import utils
from . import mood
from .mood import get_brief_mood_description # Added import
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
dream_buffer: list[str] = [] # Buffer for storing dream fragments from Oneiros
max_dream_buffer_fragments: int = 10 # Default, will be overridden by config
current_daily_summary_for_dreaming: str | None = None # Populated by Eidos control command
CONFIG_FILE_PATH = "subconscious_node/config.json"
loaded_wildcards: Dict[str, List[str]] = {} # Ensure type hint matches load_wildcards return

monologue_thread: Optional[threading.Thread] = None
stop_monologue_event = threading.Event()


# --- Configuration Loading ---
DEFAULT_SYSTEM_PROMPT = "You are Pathos, an inner voice..."
DEFAULT_TEMPERATURE = 0.7
DEFAULT_SLEEP_DURATION = 30
DEFAULT_MAX_THOUGHTS = 100
DEFAULT_MAX_DREAM_FRAGMENTS = 10 # Default for new config
DEFAULT_WILDCARD_PATH = "../wildcards/"

fixed_system_prompt = DEFAULT_SYSTEM_PROMPT
temperature = DEFAULT_TEMPERATURE
sleep_duration_seconds = DEFAULT_SLEEP_DURATION
max_monologue_buffer_thoughts = DEFAULT_MAX_THOUGHTS
# max_dream_buffer_fragments is initialized above and loaded from config below
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
        # Load max_dream_buffer_fragments
        max_dream_buffer_fragments = int(monologue_loop_settings.get("max_dream_buffer_fragments", DEFAULT_MAX_DREAM_FRAGMENTS))


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
    """Constructs the prompt for the AWAKE_THINKING state using new context variables."""
    current_context_data = context_store.get_current_context()

    # Fetch brief mood description
    brief_mood_description = get_brief_mood_description() # Use the new function from mood.py

    # Determine brief_activity
    action_context = current_context_data.get("action", [])
    if action_context:
        brief_activity = str(action_context[-1]) # Get the last action
    else:
        brief_activity = "Idle" # Default if no action context

    # Determine short_trigger_or_event
    conversation_context = current_context_data.get("conversation", [])
    if conversation_context:
        short_trigger_or_event = str(conversation_context[-1]) # Last conversation item
    elif action_context:
        short_trigger_or_event = str(action_context[-1]) # Last action item if no conversation
    else:
        short_trigger_or_event = "A quiet moment" # Default

    # Determine time_of_day
    time_of_day = datetime.now().strftime("%I:%M %p") # e.g., "03:45 PM"

    # The fixed_system_prompt is loaded from config and contains the placeholders
    # {{brief_activity}}, {{short_trigger_or_event}}, {{brief_mood_description}}, {{time_of_day}}

    prompt = fixed_system_prompt # Start with the base prompt from config
    prompt = prompt.replace("{{brief_activity}}", brief_activity)
    prompt = prompt.replace("{{short_trigger_or_event}}", short_trigger_or_event)
    prompt = prompt.replace("{{brief_mood_description}}", brief_mood_description)
    prompt = prompt.replace("{{time_of_day}}", time_of_day)

    # Append recent thoughts if any, or a placeholder
    recent_thoughts_str = "\n".join(f"- {thought}" for thought in monologue_buffer[-10:])
    if not recent_thoughts_str:
        recent_thoughts_str = "No recent thoughts to reflect on."

    # Append a section for recent thoughts and a final prompt for the LLM to continue.
    # This part can be adjusted based on how the LLM is expected to use the recent thoughts.
    # For now, let's just ensure the core prompt is populated and add a simple continuation.
    # The original prompt structure had "Pathos reflects:", which is a good continuation.
    # The new system prompt is a complete entity, so we might not need to append much more *to* it,
    # but rather ensure it's correctly formatted and the LLM knows where to start its generation.
    # The system prompt itself should guide the LLM. If the LLM needs explicit recent thoughts *after* the system prompt,
    # that structure would need to be defined. Given the new system prompt is quite comprehensive,
    # let's assume it's enough and the LLM will generate based on it.
    # However, including recent thoughts for context is often useful.
    # Let's add a small section for recent thoughts after the main system prompt.

    # Pathos's internal monologue often loops or refers to recent mental states.
    # So, providing a few recent thoughts can be beneficial.
    # The new system prompt is quite long, so we need to be careful about total prompt length.
    # Let's integrate recent thoughts more subtly if the system prompt is meant to be all-encompassing.
    # The prompt asks the LLM to "think about ... conversations he had... problems he's stuck on... ongoing fixations"
    # Recent thoughts are a direct example of these.
    # For now, let's return the populated system prompt. If testing reveals the LLM needs more direct
    # priming for *what to say next*, we can add a "Pathos reflects:" or similar,
    # and potentially a concise list of very recent thoughts.
    # The new prompt ends with "Time: {{time_of_day}}". The LLM should take it from there.

    # Let's append a very brief "Recent internal chatter:" section for the LLM to pick up on.
    # This is somewhat redundant with "Recent memory" in the prompt but more direct.
    # Keeping it concise.

    # Final check on prompt structure: The new system prompt is designed to BE the prompt.
    # It includes "You are the internal monologue... You think about: ... Context: ..."
    # So, the output of this function should be JUST that prompt, filled in.
    # No need for "Pathos reflects:" or "--- RECENT THOUGHTS ---" if the system prompt is self-contained.
    # The prompt itself asks the LLM to generate the thoughts.

    # Let's assume the `fixed_system_prompt` is the entire structure.
    return prompt

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
    # max_dream_buffer_fragments is now loaded from config

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

            # Use event.wait for stoppable sleep
            if stop_monologue_event.is_set(): break
            stop_monologue_event.wait(timeout=sleep_duration_seconds)

        elif current_node_state == NODE_STATE_SLEEPING_DREAMING:
            if stop_monologue_event.is_set(): break
            logger.info(f"Node state: {current_node_state}. Constructing dream prompt.")
            mood.drift_mood() # Mood can also drift during sleep, perhaps more erratically
            dream_fragment = None

            if dream_buffer: # Check if Oneiros has supplied any dreams
                dream_fragment = dream_buffer.pop(0) # Get the oldest Oneiros dream
                logger.info(f"Pathos (from Oneiros dream_buffer) dreams: \"{dream_fragment}\"")
                # No need to append to dream_buffer here as it's already from there.
                # Also, no need to call LLM.
            else:
                logger.info("Oneiros dream_buffer is empty. Generating fallback dream internally.")
                summary_for_prompt = current_daily_summary_for_dreaming
                if summary_for_prompt is None:
                    logger.warning("Daily summary for dreaming is None. Using a fallback message for dream prompt.")
                    summary_for_prompt = "The day's events are a blur, like faded photographs."

                dream_prompt = construct_dream_prompt(summary_for_prompt, loaded_wildcards)
                logger.debug(f"Constructed Fallback Dream Prompt (first 300 chars):\n{dream_prompt[:300]}\n--------------------")

                dream_temperature = min(temperature + 0.15, 1.1)
                logger.debug(f"Using temperature {dream_temperature} for fallback dream generation.")

                dream_fragment = utils.run_llm(dream_prompt, dream_temperature)

                if dream_fragment:
                    logger.info(f"Pathos (fallback internal generation) dreams: \"{dream_fragment}\"")
                    # Note: We are not adding internally generated dreams to the dream_buffer,
                    # as dream_buffer is for Oneiros-provided dreams.
                    # If thinker's own dreams should also be potentially re-accessible or detected,
                    # they could be added to monologue_buffer or a different buffer.
                    # For now, they are just logged.
                else:
                    logger.warning("LLM returned empty dream fragment for fallback.")

            # Common logic for any dream generated (Oneiros or fallback)
            if dream_fragment:
                # Optionally, pass to a specialized detector for dream content later
                # detectors.check_for_dream_imprint(dream_fragment, mood.get_current_mood())
                pass


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
