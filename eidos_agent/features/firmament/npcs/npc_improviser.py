import logging
from typing import Optional, Dict, Any, List
import httpx
import json
import asyncio
import re

try:
    from ....core.config import LLMConfig, Config
    from ....llm_integrations.llm_client import LLMClient
    from ....core.http_client_manager import HTTPClientManager
except ImportError:  # pragma: no cover
    # Dummies for standalone testing or if core components are not yet available
    print("NPCImproviser: Could not import core components. Using dummy types for testing.")
    LLMConfig = Dict[str, Any]  # type:ignore
    class Config:  # type:ignore
        @staticmethod
        def get_firmament_module_config():
            return {"firmament_llm_role": "FIRMAMENT_PRIMARY_DUMMY"}
        @staticmethod
        def get_llm_config(role_name: str):
            if role_name == "FIRMAMENT_PRIMARY_DUMMY":
                return {"role": role_name, "model": "dummy_model", "url": "http://dummy_url.test", "timeout": 10.0}
            return None
    class LLMClient:  # type:ignore
        def __init__(self, http_client):
            self.http_client = http_client
        async def call_llm_api(self, llm_config: LLMConfig, messages: List[Dict[str, str]], stream: bool = False, **kwargs: Any):
            name_hint = "UnknownNPC"
            for msg in messages:
                if msg["role"] == "user":
                    match = re.search(r"Name Hint: ([^\n]+)", msg["content"])
                    if match:
                        name_hint = match.group(1).strip()
                        break

            # Generate a plausible dummy ID from name_hint
            dummy_id = name_hint.lower().replace(" ", "_").replace("(", "").replace(")", "")
            dummy_id = re.sub(r'[^a-z0-9_]', '', dummy_id) # Sanitize
            if not dummy_id: dummy_id = "generic_dummy_id"
            else: dummy_id += "_dummy_id"

            dummy_profile = {
                "id": dummy_id,
                "name": f"{name_hint} (Dummy)",
                "appearance": "A standard dummy appearance, quite unremarkable.",
                "role": "Plays a dummy role in this dummy context.",
                "personality": "Typically bland, but tries its best.",
                "relationship_to_pathos": "Pathos vaguely recalls this dummy from a unit test.",
                "initial_dialogue": "Hello, I am but a humble dummy. How may I assist your testing?"
            }
            yield json.dumps(dummy_profile) # Ensure it yields a string, not the dict itself
            if False: yield # To make it a generator type

    from unittest.mock import MagicMock # For dummy HTTPClientManager
    class HTTPClientManager:  # type:ignore
        _instance = None
        @classmethod
        def instance(cls):
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
        def get_client(self) -> Optional[httpx.AsyncClient]:
            # Return a MagicMock that simulates an AsyncClient for dummy purposes
            mock_client = MagicMock(spec=httpx.AsyncClient)
            # If you need to mock specific methods on the client, do it here.
            # For example, mock_client.post = AsyncMock(...)
            return mock_client
        async def startup(self): pass # Dummy startup
        async def shutdown(self): pass # Dummy shutdown


logger = logging.getLogger(__name__)

class NPCImproviser:
    def __init__(self, firmament_llm_role_name: Optional[str] = None):
        if firmament_llm_role_name:
            self.llm_role_name = firmament_llm_role_name
        else:
            fm_module_cfg = Config.get_firmament_module_config() if callable(getattr(Config, 'get_firmament_module_config', None)) else {}
            self.llm_role_name = fm_module_cfg.get("firmament_llm_role", "FIRMAMENT_PRIMARY")

        self.llm_config: Optional[LLMConfig] = Config.get_llm_config(self.llm_role_name) if callable(getattr(Config, 'get_llm_config', None)) else None
        if not self.llm_config:
            logger.error(f"NPCImproviser: LLM config for role '{self.llm_role_name}' not found.")
        else:
            logger.info(f"NPCImproviser initialized for LLM role '{self.llm_role_name}'. Model: {self.llm_config.get('model')}")

        self.http_client_manager = HTTPClientManager.instance()
        if not (hasattr(self.http_client_manager, 'get_client') and callable(self.http_client_manager.get_client)):
            logger.error("NPCImproviser: Failed to get valid HTTPClientManager instance.") # Should not occur with dummy

    # Note: _normalize_id might still be useful if an ID is provided but needs cleaning,
    # but it should not be used to generate an ID if the LLM fails to provide one,
    # as per the new requirements. The subtask implies stricter adherence from the LLM.
    def _normalize_id(self, text: str, suffix: str = "_improv_id") -> str:
        """Normalizes a string to be a valid snake_case ID."""
        if not text or not isinstance(text, str):
            return f"invalid_name_for{suffix}"
        normalized = text.strip().lower()
        normalized = re.sub(r'\s+', '_', normalized)  # Replace spaces with underscores
        normalized = re.sub(r'[^a-z0-9_]', '', normalized)  # Remove non-alphanumeric (excluding underscore)
        normalized = re.sub(r'_+', '_', normalized) # Collapse multiple underscores
        normalized = normalized.strip('_') # Ensure no leading/trailing underscores
        if not normalized: # Handle cases where all chars were invalid
             return f"sanitized_empty_name{suffix}"
        return normalized + suffix if suffix else normalized

    def _build_improvisation_prompt(
        self,
        name_hint: Optional[str],
        subconscious_thought_context: Optional[str],
        scene_context: Dict[str, Any]
    ) -> str:
        location = scene_context.get("location_description", "an unspecified place")
        pathos_mood = scene_context.get("pathos_mood_state", "neutral")
        activity = scene_context.get("current_activity_name", "not specified")
        time = scene_context.get("time_of_day", "not specified")

        prompt_parts = ["Generate a detailed JSON profile for an NPC."]
        prompt_parts.append(f"SCENE CONTEXT: Location: {location}. Pathos's Mood: {pathos_mood}. Pathos's Activity: {activity}. Time: {time}.")
        if name_hint:
            prompt_parts.append(f"NAME HINT: '{name_hint}'.")
        if subconscious_thought_context:
            prompt_parts.append(f"PATHOS'S RELATED THOUGHT: \"{subconscious_thought_context}\" (Consider emotional tone).")

        prompt_parts.append("\nREQUIRED JSON STRUCTURE AND FIELDS:")
        prompt_parts.append("- id: (string) Unique, lowercase, snake_case ID. The 'id' should be a unique, lowercase, snake_case string derived from the 'name' or `name_hint`.")
        prompt_parts.append("- name: (string) Full NPC name (use/adapt hint if given, else invent).")
        prompt_parts.append("- appearance: (string) Evocative physical description.")
        prompt_parts.append("- role: (string) NPC's role/reason for being in this scene.")
        prompt_parts.append("- personality: (string) Key traits or demeanor summary.")
        prompt_parts.append("- relationship_to_pathos: (string) Connection to Pathos (e.g., 'stranger', 'old friend').")
        prompt_parts.append("- initial_dialogue: (string) A characteristic single opening line.")

        prompt_parts.append("\nEXAMPLE OF DESIRED JSON OUTPUT:")
        prompt_parts.append("```json")
        prompt_parts.append(json.dumps({
              "id": "example_npc_id",
              "name": "Example NPC Name",
              "appearance": "A detailed and evocative physical description.",
              "role": "Their function or reason for being in the current scene.",
              "personality": "A few key traits or a short summary of their demeanor.",
              "relationship_to_pathos": "How they know or perceive Pathos, or 'stranger'.",
              "initial_dialogue": "A characteristic first line they might say."
        }, indent=2))
        prompt_parts.append("```")
        return "\n".join(prompt_parts)

    async def improvise_npc(
        self, name_hint: Optional[str] = None,
        subconscious_thought_context: Optional[str] = None,
        scene_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        if scene_context is None: scene_context = {}
        if not self.llm_config or not self.llm_config.get("url"):
            logger.error(f"NPCImproviser: LLM URL for role '{self.llm_role_name}' missing."); return None

        shared_httpx_client = self.http_client_manager.get_client()
        if not shared_httpx_client:
            logger.error(f"NPCImproviser: Could not obtain shared HTTP client."); return None

        user_prompt_str = self._build_improvisation_prompt(name_hint, subconscious_thought_context, scene_context)
        system_message = "You are an expert character creator. Your sole output MUST be a single, valid JSON object. Do not include any explanatory text, markdown formatting, or anything outside of the JSON structure."
        messages = [{"role": "system", "content": system_message}, {"role": "user", "content": user_prompt_str}]

        logger.info(f"NPCImproviser: Initiating LLM call (Role: '{self.llm_role_name}') for NPC improvisation.")
        # logger.debug(f"NPCImproviser Full Prompt (User part):\n{user_prompt_str}") # Can be very verbose

        full_response_content = ""
        llm_error = None
        try:
            llm_api_client = LLMClient(http_client=shared_httpx_client)
            response_generator = llm_api_client.call_llm_api(
                llm_config=self.llm_config, messages=messages, stream=False
            )
            # Handle response (assuming non-streaming, or aggregating stream if necessary)
            if hasattr(response_generator, '__aiter__'): # Async generator
                async for chunk in response_generator:
                    if isinstance(chunk, str): full_response_content += chunk
                    elif isinstance(chunk, dict) and chunk.get("type") == "error_chunk": llm_error = chunk.get("payload"); break
            elif isinstance(response_generator, str): # Direct string response
                 full_response_content = response_generator
            elif isinstance(response_generator, dict) and response_generator.get("type") == "error_chunk": # Direct error dict
                 llm_error = response_generator.get("payload")
            else: # Unexpected response type
                logger.error(f"NPCImproviser: Unexpected response type from LLM client: {type(response_generator)}")
                return None

            if llm_error: logger.error(f"NPCImproviser LLM Error: {llm_error}"); return None
            if not full_response_content.strip(): logger.warning("NPCImproviser: LLM returned empty content."); return None

            logger.debug(f"NPCImproviser Raw LLM response: {full_response_content[:500]}")
            # Use regex for balanced braces to find JSON object
            json_match = re.search(r'\{(?:[^{}]|(?R))*\}', full_response_content, re.DOTALL)
            if not json_match:
                logger.error(f"NPCImproviser: No JSON object found in LLM response: {full_response_content[:300]}"); return None

            json_str = json_match.group(0)
            parsed_npc_profile = json.loads(json_str)

            if not isinstance(parsed_npc_profile, dict):
                logger.error(f"NPCImproviser: Parsed LLM response is not a dict. Type: {type(parsed_npc_profile)}"); return None

            required_keys = ["id", "name", "appearance", "role", "personality", "relationship_to_pathos", "initial_dialogue"]
            for key in required_keys:
                if not (key in parsed_npc_profile and
                        isinstance(parsed_npc_profile[key], str) and
                        parsed_npc_profile[key].strip()):
                    logger.error(f"NPCImproviser: LLM response JSON missing required key: '{key}' or value is not a non-empty string. Profile: {str(parsed_npc_profile)[:500]}")
                    return None # Strict validation as per new requirements

            # Optional: If ID needs normalization (e.g. LLM provides "Example ID" instead of "example_id")
            # This part can be kept if we want to enforce snake_case for an otherwise valid ID.
            # However, the LLM is now explicitly prompted for snake_case.
            # If the ID is present and a string, but not snake_case, we could normalize it here or reject.
            # For now, let's assume the prompt is enough, or add normalization as a separate step if needed.
            # current_id = parsed_npc_profile["id"]
            # if not re.match(r'^[a-z0-9_]+$', current_id) or "__" in current_id or current_id.startswith("_") or current_id.endswith("_"):
            #    logger.warning(f"NPCImproviser: ID '{current_id}' from LLM is not perfectly snake_case. Attempting normalization.")
            #    normalized_id = self._normalize_id(current_id, suffix="") # suffix is empty as id is already there
            #    if normalized_id != current_id:
            #        logger.info(f"NPCImproviser: ID normalized from '{current_id}' to '{normalized_id}'.")
            #        parsed_npc_profile["id"] = normalized_id
            #    else: # Normalization didn't change it, but it's still not matching regex (e.g. empty after normalize)
            #        logger.error(f"NPCImproviser: Failed to normalize ID '{current_id}' to valid snake_case. Profile discarded.")
            #        return None


            logger.info(f"NPCImproviser: Successfully improvised & validated NPC '{parsed_npc_profile.get('name')}'.")
            return parsed_npc_profile

        except httpx.RequestError as e: # Handle potential HTTP errors during the call
            logger.error(f"NPCImproviser: HTTP request error during LLM call: {e}", exc_info=True); return None
        except Exception as e: # Catch-all for other unexpected errors
            logger.error(f"NPCImproviser: Unexpected error during NPC improvisation: {e}", exc_info=True); return None


if __name__ == '__main__':  # pragma: no cover
    import random # For dummy LLMClient if used
    # Need to import datetime, timezone for the test cases
    from datetime import datetime, timezone

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # Set specific loggers to DEBUG if more detail is needed from them
    logging.getLogger('eidos_agent.features.firmament.npcs.npc_improviser').setLevel(logging.DEBUG)
    # logging.getLogger('eidos_agent.llm_integrations.llm_client').setLevel(logging.DEBUG) # If testing real calls

    async def main_test_improv_llm_guidance():
        print("\n" + "="*80)
        print("NPC Improviser Standalone Test Script")
        print("="*80)
        print("This script will attempt to use the configured Firmament LLM to generate NPC profiles.")
        print("Please ensure your .env file has the following variables correctly set for the")
        print("'FIRMAMENT_PRIMARY' LLM role (or the role specified in FIRMAMENT_LLM_ROLE):")
        print("  - LLM_FIRMAMENT_PRIMARY_URL:     (e.g., http://localhost:11434/v1 for Ollama)")
        print("  - LLM_FIRMAMENT_PRIMARY_MODEL:   (e.g., llama3:8b-instruct, mistral, phi3)")
        print("  - LLM_FIRMAMENT_PRIMARY_API_KEY: (e.g., 'ollama', 'lm-studio', or your actual key if required)")
        print("If these are not set, or if core Eidos components cannot be imported, this script")
        print("will fall back to using a DUMMY LLMClient that returns placeholder data.")
        print("Set logging level to DEBUG to see full prompts sent to the LLM.")
        print("="*80 + "\n")

        improviser = NPCImproviser()

        # Enhanced check for dummy client usage
        is_dummy_client = False
        if "dummy" in LLMClient.__name__.lower() or "dummy" in str(type(LLMClient)).lower(): # Check if LLMClient class itself is a dummy
            is_dummy_client = True

        if not improviser.llm_config or not improviser.llm_config.get("url") or \
           "dummy" in improviser.llm_config.get("url", "").lower() or is_dummy_client:
            logger.warning("Running with DUMMY LLM configuration or DUMMY LLMClient. Output will be template-based.\n")
        else:
            logger.info(f"Attempting REAL LLM calls using role: '{improviser.llm_role_name}', model: '{improviser.llm_config.get('model')}', URL: '{improviser.llm_config.get('url')}'.\n")

        test_cases = [
            {
                "name_hint": "Mysterious Stranger",
                "subconscious_thought": "Who was that person I saw lurking in the alley earlier? They seemed familiar but I can't place them.",
                "scene_context": {
                    "location_description": "a dimly lit, old library, late at night",
                    "pathos_mood_state": "curious and slightly apprehensive",
                    "current_activity_name": "researching ancient texts",
                    "time_of_day": datetime.now(timezone.utc).strftime('%I:%M %p, %A'), # More human readable
                    "recent_world_events_summary": "A rare celestial event is predicted for tonight.",
                    "pathos_current_intention": "Find a specific ritual in a grimoire."
                }
            },
            {
                "name_hint": "Old Man Fitzwilliam",
                "subconscious_thought": "I wonder if Fitzwilliam still tends his prize-winning roses. Such dedication.",
                "scene_context": {
                    "location_description": "a sunny community garden filled with blooming flowers",
                    "pathos_mood_state": "nostalgic and calm",
                    "current_activity_name": "strolling and observing nature",
                    "time_of_day": "Mid-afternoon on a spring day"
                }
            },
            {
                "name_hint": None, # No name hint, LLM should invent
                "subconscious_thought": "This old bookstore feels like it has a thousand untold stories. Someone must know them.",
                "scene_context": {
                    "location_description": "a cramped, dusty second-hand bookstore",
                    "pathos_mood_state": "intrigued and exploratory",
                    "current_activity_name": "browsing for rare editions"
                }
            }
        ]

        for i, tc in enumerate(test_cases):
            print(f"\n--- Test Case {i+1}: Name Hint = '{tc['name_hint']}' ---")
            # The _build_improvisation_prompt is internal, but its effects are seen in the LLM call log
            # if logger level is DEBUG for 'eidos_agent.features.firmament.npcs.npc_improviser'

            profile = await improviser.improvise_npc(
                name_hint=tc["name_hint"],
                subconscious_thought_context=tc.get("subconscious_thought"),
                scene_context=tc["scene_context"]
            )
            if profile:
                print(f"Successfully Generated NPC Profile:\n{json.dumps(profile, indent=2)}")
            else:
                print("Failed to generate NPC profile for this case. Check DEBUG logs for LLM prompt and errors.")

        print("\n--- NPCImproviser __main__ Test Run Completed ---")
        print("If using a real LLM, review the generated profiles for quality and adherence to the JSON schema.")
        print("If DUMMY LLMClient was used, profiles will be placeholders.")

    asyncio.run(main_test_improv_llm_guidance())
    print("\nConsider running `python -m eidos_agent.features.firmament.npcs.npc_improviser` directly for testing.")
