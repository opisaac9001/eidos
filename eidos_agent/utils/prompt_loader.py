# eidos_agent/utils/prompt_loader.py
from pathlib import Path
from typing import Dict, Optional
import logging # Use standard logging here as it's a basic utility

logger = logging.getLogger(__name__) # Use standard logger for this utility
PROMPT_DIR = Path(__file__).resolve().parent.parent / "system_prompts"

_prompt_cache: Dict[str, str] = {}

def load_system_prompt(prompt_name: str, default_content: Optional[str] = "You are a helpful AI.") -> str:
    """
    Loads a system prompt from a .txt file in the system_prompts directory.
    Caches loaded prompts for efficiency.
    Creates the prompt file with default content if it doesn't exist.

    Args:
        prompt_name: The base name of the prompt file (e.g., "main_pathos_llm_system_prompt").
        default_content: The default content to use if the file is not found or is empty.
                         Also used to create the file if it doesn't exist.

    Returns:
        The content of the system prompt as a string.
    """
    if prompt_name in _prompt_cache:
        return _prompt_cache[prompt_name]

    file_path = PROMPT_DIR / f"{prompt_name}.txt"
    content = default_content

    try:
        if file_path.is_file():
            content = file_path.read_text(encoding='utf-8').strip()
            if not content: # If file is empty
                logger.warning(f"Prompt file {file_path} is empty. Using default content for '{prompt_name}'.")
                content = default_content
            # No need for an else here, content is already set to file_path.read_text
            logger.info(f"Successfully loaded system prompt '{prompt_name}' from {file_path}")
        else:
            logger.warning(f"Prompt file {file_path} not found. Using default content for '{prompt_name}'.")
            # Optionally create it with default content if it doesn't exist
            try:
                PROMPT_DIR.mkdir(parents=True, exist_ok=True) # Ensure the prompt directory exists
                file_path.write_text(default_content or "", encoding='utf-8') # Write default content
                logger.info(f"Created default prompt file at {file_path} for '{prompt_name}'.")
            except Exception as e_create:
                logger.error(f"Could not create default prompt file for '{prompt_name}' at {file_path}: {e_create}")
                # Content remains default_content in this case
    except Exception as e:
        logger.error(f"Error loading system prompt '{prompt_name}' from {file_path}: {e}. Using default.", exc_info=True)
        content = default_content # Ensure content is default on any error
    
    _prompt_cache[prompt_name] = content
    return content