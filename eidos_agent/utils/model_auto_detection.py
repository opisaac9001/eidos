"""
Enhanced Model Auto-Detection Utility
This module provides automatic model detection and configuration for LLM endpoints.
When a model is set to "auto", it will attempt to detect and use the first available model
from the configured endpoint.
"""

import httpx
import asyncio
import logging # Using standard logging
from typing import Dict, List, Optional, Tuple
from ..core.config import Config, LLMConfig # Relative import for Config

# Use standard logging for this utility module
logger = logging.getLogger(__name__)

class ModelAutoDetector:
    """Handles automatic model detection for LLM configurations."""

    def __init__(self):
        self._model_cache: Dict[str, Tuple[str, float]] = {}  # url -> (model_name, timestamp)
        self._cache_ttl_seconds = 300  # Cache model detection results for 5 minutes

    async def get_available_models(self, base_url: str, api_key: Optional[str] = "lm-studio", timeout: float = 10.0) -> List[str]:
        """Get available models from an OpenAI-compatible API endpoint."""
        if not base_url:
            logger.warning("get_available_models: base_url is empty, cannot fetch models.")
            return []
        try:
            models_url = f"{base_url.rstrip('/')}/models"
            headers = {"Content-Type": "application/json"}

            if api_key and api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']:
                headers["Authorization"] = f"Bearer {api_key}"

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(models_url, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    models_list: List[str] = []
                    if "data" in data and isinstance(data["data"], list):
                        models_list = [model.get("id", "") for model in data["data"] if model.get("id")]
                    elif isinstance(data, list): # Some endpoints return a direct list
                        models_list = [model.get("id", "") for model in data if model.get("id")]
                    elif "models" in data and isinstance(data["models"], list): # Ollama format
                        models_list = [model.get("name", model.get("id", "")) for model in data["models"] if model.get("name") or model.get("id")]
                    
                    # Filter out empty or whitespace-only model names
                    valid_models = [m for m in models_list if m and m.strip()]
                    logger.debug(f"Found {len(valid_models)} models at {base_url}: {valid_models[:3]}{'...' if len(valid_models) > 3 else ''}")
                    return valid_models
                else:
                    logger.warning(f"Failed to get models from {base_url}: HTTP {response.status_code} - {response.text[:200]}")
                    return []
        except httpx.ConnectError:
            logger.warning(f"Connection refused when trying to get models from {base_url}.")
            return []
        except Exception as e:
            logger.warning(f"Error connecting to {base_url} for model detection: {e}", exc_info=False) # Keep exc_info False for less noise on common connection issues
            return []

    async def detect_model_for_config(self, llm_config: LLMConfig) -> Optional[str]:
        """Detect the first available model for a given LLM configuration if model is 'auto'."""
        if not llm_config or not llm_config.get("url"):
            logger.debug("detect_model_for_config: LLM config or URL missing.")
            return None

        url = llm_config["url"]
        configured_model = llm_config.get("model")

        # If model is not "auto" or not set, return the configured model (or None if not set)
        if configured_model and configured_model.lower() != "auto":
            return configured_model
        if not configured_model: # If model is None or empty string, and not "auto"
             logger.debug(f"No model specified for {url} and not set to 'auto'. Server will choose or fail.")
             return None


        # Check cache first for "auto" detection
        current_time = asyncio.get_event_loop().time()
        if url in self._model_cache:
            cached_model, timestamp = self._model_cache[url]
            if current_time - timestamp < self._cache_ttl_seconds:
                logger.debug(f"Using cached auto-detected model for {url}: {cached_model}")
                return cached_model
            else:
                logger.debug(f"Cache expired for {url}. Re-detecting.")
                del self._model_cache[url] # Remove expired entry

        api_key = llm_config.get("api_key", "lm-studio") # Default to lm-studio style if no key
        timeout = float(llm_config.get("timeout", 10.0))

        models = await self.get_available_models(url, api_key, timeout)
        if models:
            first_model = models[0]
            self._model_cache[url] = (first_model, current_time) # Cache the detected model
            logger.info(f"Auto-detected and cached model for {url}: {first_model}")
            return first_model

        logger.warning(f"No models auto-detected for {url}. Server will choose or fail.")
        return None # Fallback to server default if no models detected

    async def resolve_model_for_role(self, role: str) -> Optional[str]:
        """Resolve the actual model name for a given LLM role, using auto-detection if needed."""
        llm_config = Config.get_llm_config(role) # Static call to Config
        if not llm_config:
            logger.warning(f"No LLM configuration found for role '{role}'.")
            return None
        
        # This will return the configured model, or the auto-detected one if model is "auto"
        return await self.detect_model_for_config(llm_config)

    def clear_cache(self):
        """Clear the model detection cache."""
        self._model_cache.clear()
        logger.info("Model auto-detection cache cleared.")

# Global instance of the detector
_auto_detector_instance = ModelAutoDetector()

async def resolve_model_for_role(role: str) -> Optional[str]:
    """Convenience function to resolve model for a role using the global detector instance."""
    return await _auto_detector_instance.resolve_model_for_role(role)

async def get_available_models_for_url(url: str, api_key: Optional[str] = "lm-studio", timeout: float = 10.0) -> List[str]:
    """Convenience function to get available models for a URL using the global detector instance."""
    return await _auto_detector_instance.get_available_models(url, api_key, timeout)

def clear_model_cache():
    """Convenience function to clear the global model cache."""
    _auto_detector_instance.clear_cache()