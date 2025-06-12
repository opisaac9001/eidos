"""
Utility functions for the Pathos Subconscious Node.

This module provides implementations for interacting
with a Large Language Model (LLM) via a llama.cpp server,
loading wildcard files, and a placeholder for summarizing thoughts.
"""
import requests
import json
import os
import logging
import glob # For wildcard loading
import random
import time
from typing import Optional, Dict, List # Updated typing imports

# --- Logging Setup ---
logger = logging.getLogger(__name__)
# Basic config if no handlers are present (e.g., when run directly or in simple scripts)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Configuration Loading ---
# Find project root (where .env is located)
def find_project_root():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    while current_dir != os.path.dirname(current_dir):  # Stop at root
        if os.path.exists(os.path.join(current_dir, ".env")):
            return current_dir
        current_dir = os.path.dirname(current_dir)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Fallback

PROJECT_ROOT = find_project_root()
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

# Default values for LLM
LLAMA_CPP_SERVER_URL = "http://localhost:8081/v1/chat/completions"
LLAMA_CPP_MAX_TOKENS = 150
LLAMA_CPP_DEFAULT_TEMP = 0.7
# Default value for wildcard path (will be updated from config if available)
WILDCARD_RELATIVE_PATH = os.path.join(PROJECT_ROOT, "wildcards")

try:
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, 'r') as f:
            config_data = json.load(f)

        llm_settings = config_data.get("llm_settings", {})
        LLAMA_CPP_SERVER_URL = llm_settings.get("llama_cpp_server_url", LLAMA_CPP_SERVER_URL)
        LLAMA_CPP_MAX_TOKENS = llm_settings.get("llama_cpp_max_tokens_thought_gen", LLAMA_CPP_MAX_TOKENS)
        LLAMA_CPP_DEFAULT_TEMP = llm_settings.get("llama_cpp_default_temperature_thought_gen", LLAMA_CPP_DEFAULT_TEMP)
        logger.info(f"Llama.cpp settings loaded: URL='{LLAMA_CPP_SERVER_URL}', MaxTokens={LLAMA_CPP_MAX_TOKENS}, DefaultTemp={LLAMA_CPP_DEFAULT_TEMP}")

        # Load wildcard_folder_path from config
        WILDCARD_RELATIVE_PATH = config_data.get("wildcard_folder_path", WILDCARD_RELATIVE_PATH)
        logger.info(f"Wildcard relative path loaded: '{WILDCARD_RELATIVE_PATH}'")
    else:
        logger.warning(f"Config file not found at {CONFIG_FILE_PATH}. Using default settings for LLM and wildcards.")
except Exception as e:
    logger.error(f"Error loading settings from {CONFIG_FILE_PATH}: {e}. Using defaults.", exc_info=True)


def load_wildcards(config_folder_path: str, relative_wildcard_path: str) -> Dict[str, List[str]]:
    """
    Loads all .txt files from the specified wildcard directory.

    Args:
        config_folder_path: The absolute path to the directory containing this utils.py file.
                            (Typically obtained via os.path.dirname(__file__)).
        relative_wildcard_path: The relative path to the wildcard folder from the config_folder_path.

    Returns:
        A dictionary where keys are filenames (without .txt) and values are lists of strings (lines from the file).
    """
    wildcards_dict: Dict[str, List[str]] = {}
    try:
        abs_wildcard_path = os.path.abspath(os.path.join(config_folder_path, relative_wildcard_path))
        logger.info(f"Scanning for wildcard files in: {abs_wildcard_path}")

        if not os.path.exists(abs_wildcard_path) or not os.path.isdir(abs_wildcard_path):
            logger.error(f"Wildcard directory not found or is not a directory: {abs_wildcard_path}")
            return wildcards_dict

        for filepath in glob.glob(os.path.join(abs_wildcard_path, "*.txt")):
            filename = os.path.basename(filepath)
            category_name = filename[:-4] # Remove .txt
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    wildcards_dict[category_name] = lines
                    logger.debug(f"Loaded {len(lines)} items for wildcard category '{category_name}' from {filename}")
                else:
                    logger.warning(f"Wildcard file {filename} is empty.")
            except Exception as e:
                logger.error(f"Error reading or processing wildcard file {filepath}: {e}", exc_info=True)

        logger.info(f"Loaded {len(wildcards_dict)} wildcard categories.")
    except Exception as e:
        logger.error(f"General error in load_wildcards: {e}", exc_info=True)
    return wildcards_dict

def _get_jittered_temperature(base_temp: float) -> float:
    """Internal function for temperature randomization"""
    jitter = random.random() * 0.2 - 0.1  # Random value between -0.1 and 0.1
    result = base_temp + jitter
    return min(1.0, max(0.1, result))  # Clamp between 0.1 and 1.0

def run_llm(prompt: str, temperature: Optional[float] = None) -> str:
    """
    Calls an external LLM server (compatible with Ollama or OpenAI API)
    to generate a thought based on the provided prompt.

    Args:
        prompt: The full prompt string to send to the LLM. This should include any
                system instructions, mood context, and recent thoughts.
        temperature: The temperature setting for the LLM. If None, the default
                     from config or the hardcoded default will be used.

    Returns:
        A string containing the LLM's generated thought, or an error message string
        if the call fails or the response is malformed.
    """
    logger.debug(f"run_llm called. Prompt: '{prompt[:200]}...', Temp: {temperature}")

    base_temp = temperature if temperature is not None else LLAMA_CPP_DEFAULT_TEMP
    random.seed(int(time.time() * 1000))  # Reset seed for unpredictability
    final_temperature = _get_jittered_temperature(base_temp)

    # Get model name from config or use default
    try:
        model = config_data.get("llm_settings", {}).get("model", "mistral")
    except NameError:
        logger.warning("config_data not found, using default model")
        model = "mistral"
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": final_temperature,
        "max_tokens": LLAMA_CPP_MAX_TOKENS,
        "stream": True  # Enable streaming
    }

    logger.debug(f"Sending payload to LLM: {json.dumps(payload, indent=2)[:500]}...")

    # Use a session for persistent connection
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json"
    })

    try:
        # Stream the response
        response = session.post(LLAMA_CPP_SERVER_URL, json=payload, timeout=180, stream=True)
        response.raise_for_status()

        # Initialize variables for streaming
        full_content = ""
        printed_header = False
        is_first_token = True

        # Process the stream
        for line in response.iter_lines():
            if line:
                try:
                    # Skip empty lines and [DONE] messages
                    if line.strip() == b"" or line.strip() == b"data: [DONE]":
                        continue
                        
                    # Clean up the line if it starts with "data: "
                    if line.startswith(b"data: "):
                        line = line[6:]
                        
                    json_line = json.loads(line.decode('utf-8'))
                    
                    # Handle different API formats
                    content = None
                    if "message" in json_line:  # Ollama format
                        content = json_line["message"].get("content", "")
                    elif "choices" in json_line:  # OpenAI format
                        choices = json_line["choices"]
                        if choices and len(choices) > 0:
                            delta = choices[0].get("delta", {})
                            # Skip role markers in the stream
                            if delta.get("role"):
                                continue
                            content = delta.get("content", "")
                            # Check for stream end
                            if choices[0].get("finish_reason"):
                                break

                    if content:
                        # Print header only on first actual content
                        if is_first_token:
                            print("\n" + "="*40 + " THINKING " + "="*40)
                            is_first_token = False
                        
                        # Print each chunk of text
                        print(content, end="", flush=True)
                        full_content += content

                except json.JSONDecodeError:
                    if line.strip() and line.strip() != b"data: [DONE]":
                        logger.debug(f"Skipping invalid JSON line: {line}")
                    continue
                except Exception as e:
                    logger.debug(f"Error processing stream line: {e}")
                    continue

        # Print footer and return
        if full_content:
            print("\n" + "="*80)
            logger.debug("Thought generation complete")
            return full_content.strip()
        else:
            logger.warning("No content generated from stream")
            return "[Error: No content generated from stream]"

    except requests.exceptions.Timeout:
        logger.error(f"API call to LLM server ({LLAMA_CPP_SERVER_URL}) timed out after 180 seconds.")
        return "[Error: LLM server request timed out]"
    except requests.exceptions.ConnectionError:
        logger.error(f"API call to LLM server ({LLAMA_CPP_SERVER_URL}) failed due to connection error.")
        return "[Error: Could not connect to LLM server]"
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error from LLM server ({LLAMA_CPP_SERVER_URL}): {e}. Response: {e.response.text[:200] if e.response else 'N/A'}")
        return f"[Error: LLM server returned HTTP {e.response.status_code if e.response else 'error'}]"
    except Exception as e:
        logger.error(f"An unexpected error occurred while processing LLM response: {e}", exc_info=True)
        return "[Error: Failed to process LLM response due to an unexpected error]"
    finally:
        session.close()


def summarize_thoughts(thoughts: list[str]) -> str:
  """
  Simulates summarizing a list of thoughts. Placeholder.
  """
  logger.info(f"Summarizing {len(thoughts)} thoughts (placeholder implementation).")
  return "Lately, Pathos has been thinking about the past, loneliness, and connection."

def modify_thought_to_break_loop(thought: str, recent_thoughts: list[str]) -> str:
    """Modifies a thought to introduce variability when caught in a loop.
    
    This function takes a thought that's been detected as too similar to recent ones
    and makes it more unique by:
    1. Extracting key concepts but changing perspective
    2. Introducing contrasting elements
    3. Using associative leaps to new topics
    4. Adding emotional depth or philosophical reflection
    """
    from random import choice, random
    
    # Diverse thought-breaking patterns
    perspective_shifts = [
        # Contrasts and Reversals
        "But what if I've been looking at this all wrong?",
        "That's what I used to think, but now...",
        "The opposite could be true though...",
        
        # Associative Leaps
        "This connects strangely to something completely different...",
        "Speaking of which, it reminds me of...",
        "That's similar to, yet totally different from...",
        
        # Emotional Depth
        "The feeling behind this runs deeper...",
        "Something about this touches an old memory...",
        "There's an underlying emotion here...",
        
        # Philosophical Turns
        "Beyond the surface, there's a deeper question...",
        "This makes me wonder about the bigger picture...",
        "Perhaps there's a universal truth hidden in...",
        
        # Pattern Breaks
        "Breaking away from this loop of thinking...",
        "Let me step back and see this differently...",
        "Instead of circling this thought..."
    ]
    
    # Extract key concepts (nouns and main ideas)
    words = thought.lower().split()
    key_concepts = [w for w in words if len(w) > 4 and w not in {
        'about', 'after', 'again', 'think', 'maybe', 'should', 'would', 'could',
        'have', 'like', 'just', 'that', 'this', 'what', 'when', 'where', 'been'
    }]
    
    # Take a small random selection of key concepts (1-2) to maintain some continuity
    # while breaking the thought pattern
    selected_concepts = []
    if key_concepts:
        num_concepts = min(2, len(key_concepts))
        selected_concepts = [choice(key_concepts) for _ in range(num_concepts)]
    
    # Create a new prompt that maintains some concepts but breaks the pattern
    shift = choice(perspective_shifts)
    concept_str = ''
    if selected_concepts:
        concept_str = f" Considering '{', '.join(selected_concepts)}' but in a new context..."
    
    modified_prompt = f"{shift}{concept_str}\n\nLet your mind wander freely, exploring new directions..."
    
    # Use the LLM with high temperature and no context from previous thoughts
    completion = run_llm(modified_prompt, temperature=1.2)
    
    return completion if completion else thought  # Fallback to original if modification fails

if __name__ == '__main__':
    print("--- Configuration Test ---")
    print(f"LLAMA_CPP_SERVER_URL: {LLAMA_CPP_SERVER_URL}")
    print(f"LLAMA_CPP_MAX_TOKENS: {LLAMA_CPP_MAX_TOKENS}")
    print(f"LLAMA_CPP_DEFAULT_TEMP: {LLAMA_CPP_DEFAULT_TEMP}")
    print(f"WILDCARD_RELATIVE_PATH: {WILDCARD_RELATIVE_PATH}")

    print("\n--- Wildcard Loading Test ---")
    # utils.py is in subconscious_node, so __file__ is subconscious_node/utils.py
    # config_folder_path for load_wildcards will be subconscious_node/
    # WILDCARD_RELATIVE_PATH is ../wildcards/
    # So, os.path.join(os.path.dirname(__file__), WILDCARD_RELATIVE_PATH) should correctly resolve to project_root/wildcards/
    wildcards = load_wildcards(os.path.dirname(__file__), WILDCARD_RELATIVE_PATH)
    if wildcards:
        print(f"Loaded {len(wildcards)} wildcard categories:")
        for category, items in wildcards.items():
            print(f"  Category '{category}': {len(items)} items. Example: {items[0] if items else 'N/A'}")
    else:
        print("No wildcards loaded. Check path and ensure .txt files exist in the wildcards folder.")

    print("\n--- LLM Call Test ---")
    test_prompt = "System: You are an inner voice. Be reflective.\nUser: What is the meaning of all this?"
    print(f"\nCalling with default temperature ({LLAMA_CPP_DEFAULT_TEMP}):")
    thought1 = run_llm(test_prompt)
    print(f"Generated thought 1: {thought1}")
    custom_temp = 0.5
    print(f"\nCalling with custom temperature ({custom_temp}):")
    thought2 = run_llm(test_prompt, temperature=custom_temp)
    print(f"Generated thought 2: {thought2}")
    print(f"\nCalling with None temperature (should use default {LLAMA_CPP_DEFAULT_TEMP}):")
    thought3 = run_llm(test_prompt, temperature=None)
    print(f"Generated thought 3: {thought3}")
    print("\n--- Summarize Thoughts Test ---")
    summary = summarize_thoughts(["Thought 1", "Thought 2", "A longer thought about the universe."])
    print(f"Summary: {summary}")
    print("\n--- Testing Error Handling (No server running at http://localhost:12345) ---")
    original_url = LLAMA_CPP_SERVER_URL
    LLAMA_CPP_SERVER_URL = "http://localhost:12345/v1/chat/completions"
    error_thought = run_llm("Test prompt to non-existent server")
    print(f"Error thought: {error_thought}")
    assert "[Error:" in error_thought
    LLAMA_CPP_SERVER_URL = original_url
    print("Error handling test complete.")
    print("\nUtils test run finished.")
