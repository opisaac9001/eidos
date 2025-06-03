"""
Utility functions for the Pathos Subconscious Node.

This module provides implementations for interacting
with a Large Language Model (LLM) via a llama.cpp server
and a placeholder for summarizing thoughts.
"""
import requests
import json
import os
import logging
from typing import Optional # Added for Optional type hint

# --- Logging Setup ---
logger = logging.getLogger(__name__)
# Basic config if no handlers are present (e.g., when run directly or in simple scripts)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Configuration Loading ---
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

# Default values
LLAMA_CPP_SERVER_URL = "http://localhost:8081/v1/chat/completions" # Default if not in config
LLAMA_CPP_MAX_TOKENS = 150
LLAMA_CPP_DEFAULT_TEMP = 0.7

try:
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, 'r') as f:
            config_data = json.load(f)

        llm_settings = config_data.get("llm_settings", {})
        LLAMA_CPP_SERVER_URL = llm_settings.get("llama_cpp_server_url", LLAMA_CPP_SERVER_URL)
        LLAMA_CPP_MAX_TOKENS = llm_settings.get("llama_cpp_max_tokens_thought_gen", LLAMA_CPP_MAX_TOKENS)
        LLAMA_CPP_DEFAULT_TEMP = llm_settings.get("llama_cpp_default_temperature_thought_gen", LLAMA_CPP_DEFAULT_TEMP)
        logger.info(f"Llama.cpp settings loaded: URL='{LLAMA_CPP_SERVER_URL}', MaxTokens={LLAMA_CPP_MAX_TOKENS}, DefaultTemp={LLAMA_CPP_DEFAULT_TEMP}")
    else:
        logger.warning(f"Config file not found at {CONFIG_FILE_PATH}. Using default Llama.cpp settings.")
except Exception as e:
    logger.error(f"Error loading llama.cpp settings from {CONFIG_FILE_PATH}: {e}. Using defaults.", exc_info=True)


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
          # The prompt from thinker.py is a fully formed prompt.
          # Sending as a single "user" message is common for llama.cpp server.
          {"role": "user", "content": prompt}
      ],
      "temperature": final_temperature,
      "max_tokens": LLAMA_CPP_MAX_TOKENS,
      "n_predict": LLAMA_CPP_MAX_TOKENS, # Some llama.cpp versions use n_predict
      # "stop": ["\n", "User:", "Assistant:"] # Optional: Add stop tokens if desired
  }

  logger.debug(f"Sending payload to Llama.cpp: {json.dumps(payload, indent=2)[:500]}...")

  try:
      response = requests.post(LLAMA_CPP_SERVER_URL, json=payload, timeout=60) # Increased timeout
      response.raise_for_status() # Check for HTTP errors (4xx or 5xx)

      response_json = response.json()
      logger.debug(f"Llama.cpp raw response JSON: {json.dumps(response_json, indent=2)[:500]}...")

      # Extract content (common paths, may need adjustment based on actual llama.cpp server response)
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
  Simulates summarizing a list of thoughts.

  This is a placeholder function and does not actually summarize thoughts.
  It returns a fixed example summary.

  Args:
    thoughts: A list of thoughts to summarize.

  Returns:
    A fixed example summary.
  """
  # In a real implementation, this would involve an LLM call or other summarization logic.
  logger.info(f"Summarizing {len(thoughts)} thoughts (placeholder implementation).")
  return "Lately, Pathos has been thinking about the past, loneliness, and connection."

if __name__ == '__main__':
    # Test configuration loading
    print("--- Configuration Test ---")
    print(f"LLAMA_CPP_SERVER_URL: {LLAMA_CPP_SERVER_URL}")
    print(f"LLAMA_CPP_MAX_TOKENS: {LLAMA_CPP_MAX_TOKENS}")
    print(f"LLAMA_CPP_DEFAULT_TEMP: {LLAMA_CPP_DEFAULT_TEMP}")
    print("Ensure config.json has these values under llm_settings if you want to override defaults.")

    # Test LLM call (requires a running llama.cpp server at the configured URL)
    print("\n--- LLM Call Test ---")
    test_prompt = "System: You are an inner voice. Be reflective.\nUser: What is the meaning of all this?"

    # Test with default temperature
    print(f"\nCalling with default temperature ({LLAMA_CPP_DEFAULT_TEMP}):")
    thought1 = run_llm(test_prompt)
    print(f"Generated thought 1: {thought1}")

    # Test with a specified temperature
    custom_temp = 0.5
    print(f"\nCalling with custom temperature ({custom_temp}):")
    thought2 = run_llm(test_prompt, temperature=custom_temp)
    print(f"Generated thought 2: {thought2}")

    # Test with None temperature (should use default)
    print(f"\nCalling with None temperature (should use default {LLAMA_CPP_DEFAULT_TEMP}):")
    thought3 = run_llm(test_prompt, temperature=None)
    print(f"Generated thought 3: {thought3}")

    # Test summarize_thoughts (placeholder)
    print("\n--- Summarize Thoughts Test ---")
    summary = summarize_thoughts(["Thought 1", "Thought 2", "A longer thought about the universe."])
    print(f"Summary: {summary}")

    print("\n--- Testing Error Handling (No server running at http://localhost:12345) ---")
    original_url = LLAMA_CPP_SERVER_URL
    LLAMA_CPP_SERVER_URL = "http://localhost:12345/v1/chat/completions" # Non-existent server
    error_thought = run_llm("Test prompt to non-existent server")
    print(f"Error thought: {error_thought}")
    assert "[Error:" in error_thought # Basic check for error message
    LLAMA_CPP_SERVER_URL = original_url # Restore for any further tests
    print("Error handling test complete.")

    print("\nUtils test run finished.")
