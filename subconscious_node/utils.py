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
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

# Default values for LLM
LLAMA_CPP_SERVER_URL = "http://localhost:8081/v1/chat/completions"
LLAMA_CPP_MAX_TOKENS = 150
LLAMA_CPP_DEFAULT_TEMP = 0.7
# Default value for wildcard path (will be updated from config if available)
WILDCARD_RELATIVE_PATH = "../wildcards/" # Default, assuming 'wildcards' is one level up from 'subconscious_node'

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
      response.raise_for_status()

      response_json = response.json()
      logger.debug(f"Llama.cpp raw response JSON: {json.dumps(response_json, indent=2)[:500]}...")

      if (choices := response_json.get("choices")) and \
         isinstance(choices, list) and len(choices) > 0 and \
         (message := choices[0].get("message")) and \
         isinstance(message, dict) and \
         (content := message.get("content")):
          thought = str(content).strip()
          logger.info(f"Llama.cpp generated thought: {thought[:100]}...")
          return thought
      else:
          logger.error(f"Unexpected JSON structure from llama.cpp: {response_json}")
          return "[Error: Unexpected response structure from LLM]"

  except requests.exceptions.Timeout:
      logger.error(f"API call to llama.cpp server ({LLAMA_CPP_SERVER_URL}) timed out.")
      return "[Error: LLM server request timed out]"
  except requests.exceptions.ConnectionError:
      logger.error(f"API call to llama.cpp server ({LLAMA_CPP_SERVER_URL}) failed due to connection error.")
      return "[Error: Could not connect to LLM server]"
  except requests.exceptions.HTTPError as e:
      logger.error(f"HTTP error from llama.cpp server ({LLAMA_CPP_SERVER_URL}): {e}. Response: {e.response.text[:200] if e.response else 'N/A'}")
      return f"[Error: LLM server returned HTTP {e.response.status_code if e.response else 'error'}]"
  except json.JSONDecodeError:
      logger.error(f"Failed to decode JSON response from llama.cpp server ({LLAMA_CPP_SERVER_URL}). Response: {response.text[:200] if response else 'N/A'}")
      return "[Error: Malformed JSON response from LLM]"
  except Exception as e:
      logger.error(f"An unexpected error occurred while processing llama.cpp response: {e}", exc_info=True)
      return "[Error: Failed to process LLM response due to an unexpected error]"


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
