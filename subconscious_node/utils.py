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
from typing import Optional, Dict, List # Updated typing imports

# --- Logging Setup ---
logger = logging.getLogger(__name__)
# Basic config if no handlers are present (e.g., when run directly or in simple scripts)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Configuration Loading ---
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'config.json') # Path to config.json

# Default values
DEFAULT_LLM_SYSTEM_PROMPT = "You are Pathos, an inner voice..." # Fallback if file not found or key missing
DEFAULT_LLAMA_CPP_SERVER_URL = "http://localhost:8081/v1/chat/completions"
DEFAULT_LLAMA_CPP_MAX_TOKENS = 150
DEFAULT_LLAMA_CPP_TEMP = 0.7
DEFAULT_WILDCARD_RELATIVE_PATH = "../wildcards/"
DEFAULT_SLEEP_DURATION_SECONDS = 30
DEFAULT_MAX_BUFFER_THOUGHTS = 100
DEFAULT_MOOD_IMPULSE_THRESHOLD = 0.7
DEFAULT_EIDOS_API_BASE_URL = "http://localhost:8080"
DEFAULT_MOOD_COMPONENTS = {
    "impulsiveness": 0.3, "laziness": 0.5, "proactivity": 0.4,
    "extroversion": 0.6, "introversion": 0.4
}

# Initialize with hardcoded defaults, which will be updated
LLAMA_CPP_SERVER_URL = DEFAULT_LLAMA_CPP_SERVER_URL
WILDCARD_RELATIVE_PATH = DEFAULT_WILDCARD_RELATIVE_PATH
LLM_TEMPERATURE = DEFAULT_LLAMA_CPP_TEMP # Corresponds to llama_cpp_default_temperature_thought_gen and temperature
LLM_MAX_TOKENS = DEFAULT_LLAMA_CPP_MAX_TOKENS # Corresponds to llama_cpp_max_tokens_thought_gen
FIXED_SYSTEM_PROMPT = DEFAULT_LLM_SYSTEM_PROMPT
SLEEP_DURATION_SECONDS = DEFAULT_SLEEP_DURATION_SECONDS
MAX_MONOLOGUE_BUFFER_THOUGHTS = DEFAULT_MAX_BUFFER_THOUGHTS
MOOD_IMPULSE_THRESHOLD = DEFAULT_MOOD_IMPULSE_THRESHOLD
CURRENT_DEFAULT_MOOD = DEFAULT_MOOD_COMPONENTS.copy()
EIDOS_API_BASE_URL = DEFAULT_EIDOS_API_BASE_URL


config_data = {}
if os.path.exists(CONFIG_FILE_PATH):
    try:
        with open(CONFIG_FILE_PATH, 'r') as f:
            config_data = json.load(f)
        logger.info(f"Successfully loaded configuration from {CONFIG_FILE_PATH}")
    except FileNotFoundError:
        logger.info(f"Config file {CONFIG_FILE_PATH} not found. Using defaults or environment variables.")
    except json.JSONDecodeError:
        logger.error(f"Could not decode JSON from {CONFIG_FILE_PATH}. Will use defaults or environment variables.", exc_info=True)
    except Exception as e: # Catch any other loading errors
        logger.error(f"Unexpected error loading config from {CONFIG_FILE_PATH}: {e}. Using defaults or environment variables.", exc_info=True)
# Ensure config_data is a dict even if loading failed, for safe .get() calls later
if not isinstance(config_data, dict):
    config_data = {}


# --- Apply Overrides: Env Var -> Config File -> Hardcoded Default ---

# LLM Settings
llm_settings = config_data.get("llm_settings", {}) # Safely get llm_settings or empty dict
_json_system_prompt = llm_settings.get("fixed_system_prompt", DEFAULT_LLM_SYSTEM_PROMPT)
_system_prompt_file = os.getenv("SUBPROCESS_LLM_SYSTEM_PROMPT_FILE")

if _system_prompt_file:
    try:
        with open(_system_prompt_file, 'r', encoding='utf-8') as f_prompt: # Added encoding
            FIXED_SYSTEM_PROMPT = f_prompt.read().strip() # Strip whitespace
        logger.info(f"Loaded system prompt from environment variable file: {_system_prompt_file}")
    except FileNotFoundError:
        FIXED_SYSTEM_PROMPT = _json_system_prompt # Fallback to JSON if file not found
        logger.error(f"System prompt file specified in SUBPROCESS_LLM_SYSTEM_PROMPT_FILE ('{_system_prompt_file}') not found. Using JSON config or default.")
    except IOError as e_io:
        FIXED_SYSTEM_PROMPT = _json_system_prompt # Fallback to JSON on other IO errors
        logger.error(f"IOError reading system prompt file '{_system_prompt_file}': {e_io}. Using JSON config or default.")
    except Exception as e_prompt: # Catch any other exception during file read
        FIXED_SYSTEM_PROMPT = _json_system_prompt
        logger.error(f"Failed to load system prompt from file '{_system_prompt_file}': {e_prompt}. Using JSON config or default.", exc_info=True)
else:
    FIXED_SYSTEM_PROMPT = _json_system_prompt

_json_temp = llm_settings.get("temperature", DEFAULT_LLAMA_CPP_TEMP)
LLM_TEMPERATURE = float(os.getenv("SUBPROCESS_LLM_TEMPERATURE", _json_temp))

_json_max_tokens = llm_settings.get("llama_cpp_max_tokens_thought_gen", DEFAULT_LLAMA_CPP_MAX_TOKENS)
LLM_MAX_TOKENS = int(os.getenv("SUBPROCESS_LLM_MAX_TOKENS", _json_max_tokens))

# llama_cpp_default_temperature_thought_gen in config.json corresponds to LLM_TEMPERATURE
# It was set to the same as "temperature" in the previous subtask.
# If it needs to be distinct, it needs its own env var. For now, it uses LLM_TEMPERATURE.
LLAMA_CPP_DEFAULT_TEMP = LLM_TEMPERATURE # Keep them linked as per previous step

_json_llama_url = llm_settings.get("llama_cpp_server_url", DEFAULT_LLAMA_CPP_SERVER_URL)
LLAMA_CPP_SERVER_URL = os.getenv("SUBPROCESS_LLAMA_CPP_SERVER_URL", _json_llama_url)


# Monologue Loop Settings
monologue_loop_settings = config_data.get("monologue_loop_settings", {})
_json_sleep_duration = monologue_loop_settings.get("sleep_duration_seconds", DEFAULT_SLEEP_DURATION_SECONDS)
SLEEP_DURATION_SECONDS = int(os.getenv("SUBPROCESS_SLEEP_DURATION_SECONDS", _json_sleep_duration))

_json_max_buffer_thoughts = monologue_loop_settings.get("max_monologue_buffer_thoughts", DEFAULT_MAX_BUFFER_THOUGHTS)
MAX_MONOLOGUE_BUFFER_THOUGHTS = int(os.getenv("SUBPROCESS_MAX_BUFFER_THOUGHTS", _json_max_buffer_thoughts))


# Mood Settings
mood_settings_json = config_data.get("mood_settings", {})
_json_impulse_threshold = mood_settings_json.get("impulse_threshold", DEFAULT_MOOD_IMPULSE_THRESHOLD)
MOOD_IMPULSE_THRESHOLD = float(os.getenv("SUBPROCESS_MOOD_IMPULSE_THRESHOLD", _json_impulse_threshold))

_json_default_mood = mood_settings_json.get("default_mood", DEFAULT_MOOD_COMPONENTS)
CURRENT_DEFAULT_MOOD = {
    "impulsiveness": float(os.getenv("SUBPROCESS_DEFAULT_MOOD_IMPULSIVENESS", _json_default_mood.get("impulsiveness", DEFAULT_MOOD_COMPONENTS["impulsiveness"]))),
    "laziness": float(os.getenv("SUBPROCESS_DEFAULT_MOOD_LAZINESS", _json_default_mood.get("laziness", DEFAULT_MOOD_COMPONENTS["laziness"]))),
    "proactivity": float(os.getenv("SUBPROCESS_DEFAULT_MOOD_PROACTIVITY", _json_default_mood.get("proactivity", DEFAULT_MOOD_COMPONENTS["proactivity"]))),
    "extroversion": float(os.getenv("SUBPROCESS_DEFAULT_MOOD_EXTROVERSION", _json_default_mood.get("extroversion", DEFAULT_MOOD_COMPONENTS["extroversion"]))),
    "introversion": float(os.getenv("SUBPROCESS_DEFAULT_MOOD_INTROVERSION", _json_default_mood.get("introversion", DEFAULT_MOOD_COMPONENTS["introversion"]))),
}

# Wildcard path
_json_wildcard_path = config_data.get("wildcard_folder_path", DEFAULT_WILDCARD_RELATIVE_PATH)
WILDCARD_RELATIVE_PATH = os.getenv("SUBPROCESS_WILDCARD_RELATIVE_PATH", _json_wildcard_path)

# Eidos API Base URL (for detectors.py, though it loads its own config)
_json_eidos_api_url = config_data.get("eidos_api_base_url", DEFAULT_EIDOS_API_BASE_URL)
EIDOS_API_BASE_URL = os.getenv("SUBPROCESS_EIDOS_API_BASE_URL", _json_eidos_api_url)


# Log effective settings
logger.info(f"Effective FIXED_SYSTEM_PROMPT: '{FIXED_SYSTEM_PROMPT[:100]}...' (Env File > JSON > Default)")
logger.info(f"Effective LLM_TEMPERATURE: {LLM_TEMPERATURE} (Env > JSON > Default)")
logger.info(f"Effective LLM_MAX_TOKENS: {LLM_MAX_TOKENS} (Env > JSON > Default)")
logger.info(f"Effective LLAMA_CPP_SERVER_URL: '{LLAMA_CPP_SERVER_URL}' (Env > JSON > Default)")
logger.info(f"Effective SLEEP_DURATION_SECONDS: {SLEEP_DURATION_SECONDS} (Env > JSON > Default)")
logger.info(f"Effective MAX_MONOLOGUE_BUFFER_THOUGHTS: {MAX_MONOLOGUE_BUFFER_THOUGHTS} (Env > JSON > Default)")
logger.info(f"Effective MOOD_IMPULSE_THRESHOLD: {MOOD_IMPULSE_THRESHOLD} (Env > JSON > Default)")
logger.info(f"Effective CURRENT_DEFAULT_MOOD: {CURRENT_DEFAULT_MOOD} (Env > JSON > Default)")
logger.info(f"Effective WILDCARD_RELATIVE_PATH: '{WILDCARD_RELATIVE_PATH}' (Env > JSON > Default)")
logger.info(f"Effective EIDOS_API_BASE_URL (for utils context): '{EIDOS_API_BASE_URL}' (Env > JSON > Default)")


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

def run_llm(prompt: str, temperature: Optional[float] = None) -> str:
  """
  Calls an external LLM server (compatible with llama.cpp's OpenAI API-like endpoint)
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

  final_temperature = temperature if temperature is not None else LLAMA_CPP_DEFAULT_TEMP

  payload = {
      "messages": [
          {"role": "user", "content": prompt}
      ],
      "temperature": final_temperature,
      "max_tokens": LLAMA_CPP_MAX_TOKENS,
      "n_predict": LLAMA_CPP_MAX_TOKENS,
  }

  logger.debug(f"Sending payload to Llama.cpp: {json.dumps(payload, indent=2)[:500]}...")

  try:
      response = requests.post(LLAMA_CPP_SERVER_URL, json=payload, timeout=60)
      response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)

      response_json = response.json()
      # Enhanced logging for debugging the raw response
      logger.debug(f"Llama.cpp raw response JSON: {json.dumps(response_json, indent=2)}")

      choices = response_json.get("choices")
      if not choices or not isinstance(choices, list) or len(choices) == 0:
          logger.error(f"LLM response missing 'choices' list or 'choices' is empty. Full response: {response_json}")
          return "[Error: LLM response missing or empty choices]"

      message = choices[0].get("message")
      if not message or not isinstance(message, dict):
          logger.error(f"First choice in LLM response missing 'message' dict. Full response: {response_json}")
          return "[Error: LLM response choice missing message]"

      content = message.get("content")
      if content is None: # Allow empty string, but not None
          logger.error(f"Message in LLM response choice missing 'content'. Full response: {response_json}")
          return "[Error: LLM response message missing content]"

      thought = str(content).strip()
      if not thought: # Handle if content is an empty string after stripping
          logger.warning(f"LLM generated an empty thought. Prompt: '{prompt[:200]}...'")
          return "[Warning: LLM generated empty thought]"

      logger.info(f"Llama.cpp generated thought: {thought[:100]}...")
      return thought

  except requests.exceptions.Timeout as e_timeout:
      logger.error(f"API call to LLM server ({LLAMA_CPP_SERVER_URL}) timed out after {payload.get('timeout', 'default')}s. Error: {e_timeout}", exc_info=True)
      return "[Error: LLM server request timed out]"
  except requests.exceptions.ConnectionError as e_conn:
      logger.error(f"API call to LLM server ({LLAMA_CPP_SERVER_URL}) failed due to connection error. Ensure server is running. Error: {e_conn}", exc_info=True)
      return "[Error: Could not connect to LLM server]"
  except requests.exceptions.HTTPError as e_http:
      error_detail = "Unknown HTTP error"
      if e_http.response is not None:
          error_detail = f"HTTP {e_http.response.status_code}. Response: {e_http.response.text[:200]}"
      logger.error(f"HTTP error from LLM server ({LLAMA_CPP_SERVER_URL}): {error_detail}", exc_info=True)
      return f"[Error: LLM server returned {error_detail}]"
  except json.JSONDecodeError as e_json:
      response_text_snippet = response.text[:200] if 'response' in locals() and hasattr(response, 'text') else "N/A"
      logger.error(f"Failed to decode JSON response from LLM server ({LLAMA_CPP_SERVER_URL}). Response snippet: {response_text_snippet}. Error: {e_json}", exc_info=True)
      return "[Error: Malformed JSON response from LLM]"
  except Exception as e_unexpected: # Catch-all for other unexpected errors
      logger.error(f"An unexpected error occurred while processing LLM response from {LLAMA_CPP_SERVER_URL}: {e_unexpected}", exc_info=True)
      return "[Error: Unexpected error processing LLM response]"


def summarize_thoughts(thoughts: list[str]) -> str:
  """
  Simulates summarizing a list of thoughts. Placeholder.
  """
  logger.info(f"Summarizing {len(thoughts)} thoughts (placeholder implementation).")
  return "Lately, Pathos has been thinking about the past, loneliness, and connection."

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
    # ... (rest of __main__ from previous version) ...
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
