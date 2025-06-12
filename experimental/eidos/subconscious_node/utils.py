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
import glob
import random
import time
from typing import Optional, Dict, List

# --- Logging Setup ---
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Configuration Loading ---
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

# Default values for LLM
LLAMA_CPP_SERVER_URL = "http://localhost:8081/v1/chat/completions"
LLAMA_CPP_MAX_TOKENS = 150
LLAMA_CPP_DEFAULT_TEMP = 0.7
DEMO_MODE = False
WILDCARD_RELATIVE_PATH = "../wildcards/"

try:
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, 'r') as f:
            config_data = json.load(f)
        llm_settings = config_data.get("llm_settings", {})
        LLAMA_CPP_SERVER_URL = llm_settings.get("llama_cpp_server_url", LLAMA_CPP_SERVER_URL)
        LLAMA_CPP_MAX_TOKENS = llm_settings.get("llama_cpp_max_tokens_thought_gen", LLAMA_CPP_MAX_TOKENS)
        LLAMA_CPP_DEFAULT_TEMP = llm_settings.get("llama_cpp_default_temperature_thought_gen", LLAMA_CPP_DEFAULT_TEMP)
        
        DEMO_MODE = config_data.get("demo_mode", DEMO_MODE)
        WILDCARD_RELATIVE_PATH = config_data.get("wildcard_folder_path", WILDCARD_RELATIVE_PATH)
        
        logger.info(f"Llama.cpp settings loaded: URL='{LLAMA_CPP_SERVER_URL}', MaxTokens={LLAMA_CPP_MAX_TOKENS}, DefaultTemp={LLAMA_CPP_DEFAULT_TEMP}, DemoMode={DEMO_MODE}")
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
        relative_wildcard_path: The relative path to the wildcard folder from the config_folder_path.

    Returns:
        A dictionary where keys are filenames (without .txt) and values are lists of strings (lines from the file).
    """
    wildcards_dict: Dict[str, List[str]] = {}
    try:
        abs_wildcard_path = os.path.abspath(os.path.join(config_folder_path, relative_wildcard_path))
        logger.info(f"Scanning for wildcard files in: {abs_wildcard_path}")

        if not os.path.exists(abs_wildcard_path) or not os.path.isdir(abs_wildcard_path):
            logger.warning(f"Wildcard directory not found: {abs_wildcard_path}. Continuing without wildcards.")
            return wildcards_dict

        for filepath in glob.glob(os.path.join(abs_wildcard_path, "*.txt")):
            filename = os.path.basename(filepath)
            category_name = filename[:-4]  # Remove .txt
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    wildcards_dict[category_name] = lines
                    logger.debug(f"Loaded {len(lines)} items for wildcard category '{category_name}' from {filename}")
                else:
                    logger.warning(f"Wildcard file {filename} is empty.")
            except Exception as e:
                logger.error(f"Error reading wildcard file {filepath}: {e}", exc_info=True)

        logger.info(f"Loaded {len(wildcards_dict)} wildcard categories.")
    except Exception as e:
        logger.error(f"General error in load_wildcards: {e}", exc_info=True)
    return wildcards_dict


def run_llm(prompt: str, temperature: Optional[float] = None) -> str:
    """
    Calls an external LLM server to generate a thought based on the provided prompt.
    If demo mode is enabled, returns simulated thoughts instead.
    """
    if DEMO_MODE:
        return _generate_demo_thought(temperature)
    
    temp = temperature if temperature is not None else LLAMA_CPP_DEFAULT_TEMP
    
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temp,
        "max_tokens": LLAMA_CPP_MAX_TOKENS,
        "stream": False
    }
    
    try:
        response = requests.post(LLAMA_CPP_SERVER_URL, json=payload, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data.get("choices") and len(data["choices"]) > 0:
            content = data["choices"][0].get("message", {}).get("content", "")
            if content:
                return content.strip()
        
        logger.warning(f"Unexpected LLM response format: {data}")
        return "A quiet moment of reflection passes through the mind."
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling LLM server: {e}")
        return "The connection to deeper thoughts seems momentarily interrupted."
    except Exception as e:
        logger.error(f"Unexpected error in run_llm: {e}", exc_info=True)
        return "An unexpected pause in the stream of consciousness."


def _generate_demo_thought(temperature: Optional[float] = None) -> str:
    """Generate demo thoughts when demo mode is enabled."""
    demo_thoughts = [
        "The morning light filters through the window differently today - softer somehow, like consciousness gradually awakening.",
        "Another commit pushed to GitHub - small progress, but progress nonetheless. Rome wasn't built in a day.",
        "Indie games understand something about human nature that bigger productions often miss entirely.",
        "Bristol feels like a lifetime ago, yet somehow yesterday. Geography shapes us more than we realize.",
        "The absurdity of explaining complex technical concepts to clients who just want 'the thing to work better'.",
        "Filter coffee brewing downstairs - ritual as much as caffeine, marking the transition from sleep to consciousness.",
        "Late night coding sessions blur the line between productivity and procrastination in fascinating ways.",
        "Post-rock instrumentals capture emotions that words somehow fail to reach.",
        "The philosophy degree feels simultaneously useless and invaluable - like a lens that can't be removed.",
        "Freelance life: the freedom to work whenever you want, as long as it's all the time."
    ]
    
    temp = temperature if temperature is not None else LLAMA_CPP_DEFAULT_TEMP
    
    if temp > 0.8:
        thought = random.choice(demo_thoughts)
    elif temp > 0.5:
        thought = random.choice(demo_thoughts)
    else:
        index = int(time.time()) % len(demo_thoughts)
        thought = demo_thoughts[index]
    
    logger.info(f"Demo mode: Generated thought with temp {temp}: {thought[:50]}...")
    return thought


def summarize_thoughts(thoughts: List[str], max_length: int = 200) -> str:
    """
    Placeholder function to summarize a list of thoughts.
    In a full implementation, this could use another LLM call or more sophisticated logic.
    """
    if not thoughts:
        return "No thoughts to summarize."
    
    if len(thoughts) == 1:
        return thoughts[0][:max_length]
    
    # Simple concatenation with ellipsis for now
    combined = " | ".join(thoughts)
    if len(combined) <= max_length:
        return combined
    else:
        return combined[:max_length-3] + "..."


if __name__ == '__main__':
    print("--- Configuration Test ---")
    print(f"LLAMA_CPP_SERVER_URL: {LLAMA_CPP_SERVER_URL}")
    print(f"LLAMA_CPP_MAX_TOKENS: {LLAMA_CPP_MAX_TOKENS}")
    print(f"LLAMA_CPP_DEFAULT_TEMP: {LLAMA_CPP_DEFAULT_TEMP}")
    print(f"DEMO_MODE: {DEMO_MODE}")
    print(f"WILDCARD_RELATIVE_PATH: {WILDCARD_RELATIVE_PATH}")

    print("\n--- Demo Mode Test ---")
    test_prompt = "System: You are an inner voice. Be reflective.\nUser: What is the meaning of all this?"
    thought1 = run_llm(test_prompt)
    print(f"Generated thought: {thought1}")
    
    print("\nSubconscious node utils ready for deployment.")