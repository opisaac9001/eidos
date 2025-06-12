"""
Core thought generation loop for the Pathos Subconscious Node.
"""
import time
import json
import logging
import os
import random 
from datetime import datetime
from typing import Dict, List

# Import local modules using absolute imports
import utils
import mood
import detectors
import context_store

# Set up random seed based on current time
def reset_random_seed():
    """Reset the random seed based on current time for unpredictable generation"""
    current_time = datetime.now().timestamp()
    random.seed(int(current_time * 1000))

# --- Logging Setup ---
logger = logging.getLogger(__name__)
if not logger.handlers:
    # Create a custom formatter with colors and symbols
    class ColoredFormatter(logging.Formatter):
        def format(self, record):
            # Add color codes and symbols based on level
            if record.levelno == logging.INFO:
                if "thinks:" in record.msg:
                    # Special formatting for thoughts
                    record.msg = f"\n{'='*80}\n💭 THOUGHT: {record.msg}\n{'='*80}"
                elif "dreams:" in record.msg:
                    # Special formatting for dreams
                    record.msg = f"\n{'*'*80}\n💫 DREAM: {record.msg}\n{'*'*80}"
            return super().format(record)

    handler = logging.StreamHandler()
    handler.setFormatter(ColoredFormatter('%(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

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
    """Constructs a natural prompt for stream of consciousness thought generation."""
    # Get context data
    current_context_data = context_store.get_current_context()
    
    # Build context strings as natural thought triggers
    conversation_context = " ".join(current_context_data.get("conversation", []))
    action_context = " ".join(current_context_data.get("action", []))    # Get recent thoughts but avoid too much repetition
    recent_thoughts = []
    seen_themes = set()
    
    # Common filler words to ignore when analyzing themes
    filler_words = {
        'about', 'after', 'again', 'think', 'maybe', 'should', 'would', 'could',
        'have', 'like', 'just', 'that', 'this', 'what', 'when', 'where', 'been',
        'from', 'with', 'your', 'going', 'gets', 'want', 'back', 'into'
    }
    
    # Extract meaningful phrases (bigrams and trigrams) as themes
    def extract_themes(text):
        words = [w.lower() for w in text.split() if len(w) > 3 and w.lower() not in filler_words]
        themes = set(words)  # individual words
        # Add bigrams and trigrams
        for i in range(len(words) - 1):
            themes.add(f"{words[i]} {words[i+1]}")
        for i in range(len(words) - 2):
            themes.add(f"{words[i]} {words[i+1]} {words[i+2]}")
        return themes
    
    # Only use thoughts that introduce sufficient new themes
    for thought in reversed(monologue_buffer[-10:]):
        thought_themes = extract_themes(thought)
        
        # Calculate theme novelty (percentage of new themes)
        if not seen_themes:
            theme_novelty = 1.0
        else:
            overlap = len(thought_themes & seen_themes)
            theme_novelty = 1 - (overlap / len(thought_themes) if thought_themes else 0)
        
        # Include thought if it's novel enough (less than 30% theme overlap)
        if theme_novelty > 0.7:
            recent_thoughts.append(thought)
            seen_themes.update(thought_themes)
        
        if len(recent_thoughts) >= 2:  # Limit to 2 most recent unique thoughts to reduce repetition
            break
    
    recent_thoughts_str = " ".join(recent_thoughts) if recent_thoughts else ""

    # Assemble the prompt in a way that encourages natural but varied thought flow
    prompt_parts = [
        fixed_system_prompt,
        "\nRecent echoes in your mind (letting thoughts drift and transform):",
        recent_thoughts_str if recent_thoughts_str else "Your mind feels clear, ready for new thoughts...",
        "\nSensory impressions and fresh memories drifting in:",
        conversation_context if conversation_context else "",
        action_context if action_context else "",
        "\nLet your thoughts wander to new unexplored directions..."
    ]
    
    return "\n".join(part for part in prompt_parts if part)

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


def detect_thought_loop(new_thought: str, recent_thoughts: list[str], threshold: float = 0.4) -> bool:
    """
    Detects if a new thought is too similar to recent thoughts, indicating a potential thought loop.
    Uses multiple similarity measures to catch different types of repetition.
    
    Args:
        new_thought: The thought to check
        recent_thoughts: List of recent thoughts to compare against
        threshold: Similarity threshold above which we consider it a loop
        
    Returns:
        bool: True if a thought loop is detected
    """
    def get_ngrams(text: str, n: int = 3) -> set:
        """Get character n-grams from text for fuzzy matching"""
        text = text.lower()
        return {text[i:i+n] for i in range(len(text)-n+1)}
    
    def get_word_ngrams(text: str, n: int = 2) -> set:
        """Get word n-grams for phrase matching"""
        words = text.lower().split()
        return {' '.join(words[i:i+n]) for i in range(len(words)-n+1)}
    
    def contains_repeated_phrases(text: str, min_length: int = 4) -> bool:
        """Check for phrases that repeat within the same thought"""
        words = text.lower().split()
        phrases = [' '.join(words[i:i+min_length]) for i in range(len(words)-min_length+1)]
        return len(phrases) != len(set(phrases))
    
    # Check for immediate phrase repetition within the thought
    if contains_repeated_phrases(new_thought):
        return True
    
    # Convert thoughts to different types of ngrams for comparison
    new_char_ngrams = get_ngrams(new_thought)
    new_word_ngrams = get_word_ngrams(new_thought)
    
    # Check similarity with recent thoughts
    for old_thought in recent_thoughts[-5:]:
        # Character-level similarity (for overall content)
        old_char_ngrams = get_ngrams(old_thought)
        char_intersection = len(new_char_ngrams & old_char_ngrams)
        char_union = len(new_char_ngrams | old_char_ngrams)
        char_similarity = char_intersection / char_union if char_union > 0 else 0
        
        # Word-level similarity (for phrases and concepts)
        old_word_ngrams = get_word_ngrams(old_thought)
        word_intersection = len(new_word_ngrams & old_word_ngrams)
        word_union = len(new_word_ngrams | old_word_ngrams)
        word_similarity = word_intersection / word_union if word_union > 0 else 0
        
        # Combine similarities with more weight on word-level matches
        combined_similarity = (char_similarity + 2 * word_similarity) / 3
        
        if combined_similarity > threshold:
            return True
            
    return False

def monologue_loop():
    """
    The main loop for Pathos's subconscious thought generation.
    """
    global current_node_state
    logger.info("Pathos Subconscious Node: Monologue Loop starting...")
    logger.info(f"Initial Node State: {current_node_state}")
    logger.info(f"Settings: Temp={temperature}, Sleep={sleep_duration_seconds}s, MaxThoughts={max_monologue_buffer_thoughts}")

    while True:
        # Reset random seed on each iteration for unpredictability
        reset_random_seed()
        
        if current_node_state == NODE_STATE_AWAKE_THINKING:
            logger.debug(f"Node state: {current_node_state}")
            mood.drift_mood()
            current_mood_snapshot = mood.get_current_mood()
            
            # Try generating a non-repetitive thought up to 3 times
            max_attempts = 3
            for attempt in range(max_attempts):
                prompt_str = build_prompt()
                logger.debug(f"Debug: Built Prompt (first 200 chars):\n{prompt_str[:200]}\n--------------------")
                
                # Increase temperature slightly with each retry to encourage variation
                current_temp = temperature * (1 + attempt * 0.1)
                new_thought = utils.run_llm(prompt_str, current_temp)
                
                # Check if we're in a thought loop
                if not detect_thought_loop(new_thought, monologue_buffer):
                    break
                    
                if attempt < max_attempts - 1:
                    logger.debug("Thought seems repetitive, trying again with higher temperature...")
                    time.sleep(1)  # Brief pause before retry
            
            mood_name = current_mood_snapshot.get('name', 'default') if isinstance(current_mood_snapshot, dict) else 'default'
            logger.info(f"Pathos thinks: {new_thought}\n\nCurrent Mood: {mood_name}")
            monologue_buffer.append(new_thought)
            
            if len(monologue_buffer) > max_monologue_buffer_thoughts:
                logger.debug(f"Monologue buffer full ({len(monologue_buffer)} thoughts). Trimming oldest.")
                num_to_remove = len(monologue_buffer) - max_monologue_buffer_thoughts
                del monologue_buffer[:num_to_remove]
            
            detectors.check_for_impulse(new_thought, current_mood_snapshot)
            detectors.check_for_imprint(new_thought, current_mood_snapshot)
            time.sleep(sleep_duration_seconds)

        elif current_node_state == NODE_STATE_SLEEPING_DREAMING:
            logger.debug(f"Node state: {current_node_state}")
            
            # For now, using a simulated dream
            simulated_dream = f"A fleeting image of {random.choice(loaded_wildcards.get('animals', ['something'])) if loaded_wildcards else 'something'} in a field of {random.choice(loaded_wildcards.get('colors', ['strange'])) if loaded_wildcards else 'strange'} light."
            logger.info(f"Pathos dreams: {simulated_dream}")

            dream_mode_sleep_duration = int(sleep_duration_seconds / 2) if sleep_duration_seconds > 2 else 1
            time.sleep(dream_mode_sleep_duration)

        else:
            logger.error(f"Unknown node state: {current_node_state}. Defaulting to AWAKE_THINKING.")
            time.sleep(sleep_duration_seconds)
            current_node_state = NODE_STATE_AWAKE_THINKING
