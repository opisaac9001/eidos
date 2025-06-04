import asyncio
import httpx
import logging
import json # Added for potential debug logging
import random # Added
from typing import Optional, TYPE_CHECKING, Dict, Any
from datetime import datetime

# Assuming Config is in core.config and EthosCore, ChronosEngine are where they are
from eidos_agent.core.config import Config, FirmamentModuleConfig, LLMConfig
from eidos_agent.persona_logic.chronos_engine.models import ActivitySlot
try:
    # Attempt to import PATHOS_USER_ID, provide a fallback if not found
    from eidos_agent.persona_logic.chronos_engine.engine import PATHOS_USER_ID
except ImportError:
    # This log will only work if logger is already defined at module level when imports are processed
    # print("Warning: Could not import PATHOS_USER_ID from chronos_engine.engine. Using default for FirmamentModule.")
    PATHOS_USER_ID = "pathos_agent_internal"

if TYPE_CHECKING:
    from eidos_agent.persona_logic.ethos_core.core import EthosCore
    from eidos_agent.persona_logic.chronos_engine.engine import ChronosEngine

logger = logging.getLogger(__name__)

# Availability Status Constants
AVAILABILITY_STATUS_BUSY_DEEP_WORK = "BUSY_DEEP_WORK"
AVAILABILITY_STATUS_BUSY_MEETING = "BUSY_MEETING"
AVAILABILITY_STATUS_BUSY_GENERAL_WORK = "BUSY_GENERAL_WORK"
AVAILABILITY_STATUS_LIGHT_ACTIVITY = "LIGHT_ACTIVITY"
AVAILABILITY_STATUS_AVAILABLE = "AVAILABLE"
AVAILABILITY_STATUS_UNKNOWN = "UNKNOWN"

class FirmamentModule:
    def __init__(self, config: Config, ethos_core: 'EthosCore', chronos_engine: 'ChronosEngine'):
        self.config = config
        self.fm_config: FirmamentModuleConfig = config.get_firmament_module_config()
        self.ethos_core = ethos_core
        self.chronos_engine = chronos_engine
        self.http_client: Optional[httpx.AsyncClient] = None
        self.firmament_llm_config: Optional[LLMConfig] = None

        if self.fm_config.get("enable_firmament", False):
            llm_role = self.fm_config.get("firmament_llm_role")
            if llm_role:
                self.firmament_llm_config = self.config.get_llm_config(llm_role)

            if not self.firmament_llm_config or not self.firmament_llm_config.get("url"):
                logger.error(
                    f"FirmamentModule: LLM for role '{llm_role}' is not configured or lacks a URL. "
                    "Firmament will be impaired."
                )
            else:
                timeout_val = float(self.firmament_llm_config.get('timeout', 60.0)) # Default 60s
                self.http_client = httpx.AsyncClient(timeout=timeout_val)
                logger.info(
                    f"FirmamentModule initialized with LLM role '{llm_role}'. HTTP client ready."
                )
        else:
            logger.info("FirmamentModule is disabled by configuration.")

    async def start(self):
        # Placeholder for starting any background tasks if Firmament needs them
        if self.fm_config.get("enable_firmament") and self.http_client:
            logger.info("FirmamentModule started and ready.")
        elif self.fm_config.get("enable_firmament"):
             logger.warning(
                "FirmamentModule is enabled in config, but the LLM http_client "
                "is not available (likely due to missing LLM URL or role config). "
                "Firmament will not function correctly."
            )
        # No specific background tasks to start in Phase 1 initialization beyond http_client.

    async def close(self):
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()
            logger.info("FirmamentModule HTTP client closed.")
        else:
            logger.info("FirmamentModule resources (if any) considered closed (no active HTTP client or already closed).")

    async def run_simulation_tick(self):
        '''
        Runs a single simulation tick for Firmament.
        This involves:
        1. Getting current Pathos activity and mood.
        2. Generating an activity log snippet via LLM.
        3. Storing the snippet as a memory in EthosCore.
        '''
        if not self.fm_config.get("enable_firmament", False):
            # This check is also in helper methods, but good for a public entry point too.
            logger.debug("FirmamentModule.run_simulation_tick: Module is disabled. Skipping tick.")
            return

        logger.debug("FirmamentModule: Starting simulation tick.")
        try:
            activity_slot = await self._get_current_activity_slot()
            if not activity_slot:
                logger.info("FirmamentModule: No current activity slot for Pathos. Skipping snippet generation for this tick.")
                return

            # Mood is important context for generation
            mood = await self._get_current_mood()
            if not mood:
                # EthosCore usually provides a default mood, so this would be unexpected.
                logger.warning("FirmamentModule: Could not retrieve current mood for Pathos. Proceeding with caution or default behavior in LLM prompt.")
                # Create a fallback mood if absolutely necessary for the snippet generation method's signature
                mood = {"name": "unknown", "valence": 0.0, "arousal": 0.0}

            snippet = await self._generate_activity_log_snippet(activity_slot, mood)

            if snippet:
                memory_id = await self._store_activity_log(snippet, activity_slot, mood)
                if memory_id:
                    logger.info(f"FirmamentModule: Simulation tick completed. Activity log stored as memory {memory_id}.")
                else:
                    logger.warning("FirmamentModule: Snippet generated but failed to store as memory.")
            else:
                logger.info("FirmamentModule: No snippet generated during this simulation tick.")

            logger.debug("FirmamentModule: Simulation tick finished.")

        except Exception as e:
            logger.error(f"FirmamentModule: Unhandled error during simulation tick: {e}", exc_info=True)

    async def receive_subconscious_intention(self, intention: str, metadata: Dict[str, Any]):
        '''
        Receives an actionable thought or intention from the subconscious_node.
        In Phase 1, this method logs the intention and stores it as a memory.
        Future phases will involve Firmament simulating the consequences of this intention.
        '''
        if not self.fm_config.get("enable_firmament", False):
            logger.debug("FirmamentModule.receive_subconscious_intention: Module is disabled. Ignoring intention.")
            return

        logger.info(f"FirmamentModule: Received intention from subconscious_node: '{intention}'. Metadata: {metadata}")

        if not self.ethos_core:
            logger.error("FirmamentModule: EthosCore is not available. Cannot store intention as memory.")
            return

        try:
            current_time = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)
            if not current_time:
                current_time = datetime.now() # Fallback
                logger.warning("FirmamentModule: Could not get current Pathos time for intention memory, using system now().")

            # Enhance the received metadata with a timestamp of receipt if not already present from source
            full_metadata = {
                "source": "subconscious_node_intention",
                "original_metadata": metadata, # Store the metadata passed from subconscious_node
                "received_at_firmament_timestamp": current_time.isoformat()
            }

            entry_data = {
                "type": "received_subconscious_intention",
                "content": intention,
                "metadata": full_metadata,
                "salience": random.uniform(0.5, 0.7) # Intentions might be moderately salient
            }

            # Assuming PATHOS_USER_ID is available
            memory_entry = await self.ethos_core.add_memory_entry(
                entry_data=entry_data,
                user_id_context=PATHOS_USER_ID
            )

            if memory_entry and hasattr(memory_entry, 'id') and memory_entry.id:
                logger.info(f"FirmamentModule: Stored received intention as memory ID {memory_entry.id}.")
            else:
                logger.error("FirmamentModule: Failed to store received intention in EthosCore or memory_entry has no ID.")

        except Exception as e:
            logger.error(f"FirmamentModule: Error processing received subconscious intention: {e}", exc_info=True)

    async def get_availability_status(self) -> str:
        '''
        Determines Pathos's current availability status based on his scheduled activity.
        '''
        if not self.fm_config.get("enable_firmament", False):
            logger.info("FirmamentModule is disabled. Reporting UNKNOWN availability.")
            return AVAILABILITY_STATUS_UNKNOWN

        activity_slot = await self._get_current_activity_slot()

        if not activity_slot:
            logger.info("FirmamentModule: No current activity slot. Reporting AVAILABLE by default (or UNKNOWN).")
            # Depending on desired behavior: could be UNKNOWN or a default like AVAILABLE
            # For now, let's assume if not in a slot, Pathos is generally available.
            return AVAILABILITY_STATUS_AVAILABLE

        activity_type_lower = activity_slot.activity_type.lower()
        slot_name_lower = activity_slot.slot_name.lower()
        activity_title_lower = activity_slot.activity_title.lower()

        # More specific busy states first
        if "meeting" in slot_name_lower or "client call" in slot_name_lower or "consulting" in activity_title_lower:
            logger.debug(f"FirmamentModule: Availability - BUSY_MEETING due to '{activity_slot.slot_name}'.")
            return AVAILABILITY_STATUS_BUSY_MEETING

        if "deep work" in slot_name_lower or "focus session" in slot_name_lower:
            logger.debug(f"FirmamentModule: Availability - BUSY_DEEP_WORK due to '{activity_slot.slot_name}'.")
            return AVAILABILITY_STATUS_BUSY_DEEP_WORK

        if "work" in activity_type_lower or "writing" in slot_name_lower or "admin" in slot_name_lower:
            logger.debug(f"FirmamentModule: Availability - BUSY_GENERAL_WORK due to '{activity_slot.slot_name}'.")
            return AVAILABILITY_STATUS_BUSY_GENERAL_WORK

        # Less busy states
        if "leisure" in activity_type_lower or "break" in activity_type_lower or "reading" in slot_name_lower or "coffee" in slot_name_lower:
            logger.debug(f"FirmamentModule: Availability - LIGHT_ACTIVITY due to '{activity_slot.slot_name}'.")
            return AVAILABILITY_STATUS_LIGHT_ACTIVITY

        if "reflective" in activity_type_lower or "planning" in activity_type_lower:
            logger.debug(f"FirmamentModule: Availability - LIGHT_ACTIVITY (reflective/planning) due to '{activity_slot.slot_name}'.")
            return AVAILABILITY_STATUS_LIGHT_ACTIVITY

        # Default for recognized slots that don't fit above categories explicitly
        # Could be AVAILABLE or a more specific type if activity_type is well-defined
        logger.debug(f"FirmamentModule: Availability - Defaulting to AVAILABLE for slot '{activity_slot.slot_name}' of type '{activity_type_lower}'.")
        return AVAILABILITY_STATUS_AVAILABLE

    async def _get_current_activity_slot(self) -> Optional[ActivitySlot]:
        '''
        Retrieves Pathos's current scheduled activity slot from ChronosEngine.
        '''
        if not self.fm_config.get("enable_firmament"):
            logger.debug("FirmamentModule is disabled, cannot get current activity slot.")
            return None

        try:
            # Get Pathos's current local time via EthosCore
            current_pathos_time: Optional[datetime] = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)

            if not current_pathos_time:
                logger.error("FirmamentModule: Could not retrieve current_pathos_time from EthosCore.")
                return None

            activity_slot = await self.chronos_engine.get_current_activity(current_pathos_time)

            if activity_slot:
                logger.debug(f"FirmamentModule: Current activity slot: {activity_slot.slot_name} - {activity_slot.activity_title}")
            else:
                logger.debug(f"FirmamentModule: No current activity slot found by ChronosEngine for time {current_pathos_time.isoformat()}.")

            return activity_slot
        except Exception as e:
            logger.error(f"FirmamentModule: Error getting current activity slot: {e}", exc_info=True)
            return None

    async def _get_current_mood(self) -> Optional[Dict[str, Any]]:
        '''
        Retrieves Pathos's current mood from EthosCore.
        '''
        if not self.fm_config.get("enable_firmament"):
            logger.debug("FirmamentModule is disabled, cannot get current mood.")
            return None

        try:
            mood_data = self.ethos_core.get_current_mood() # This is a synchronous method in EthosCore

            if mood_data:
                logger.debug(f"FirmamentModule: Current mood: Valence={mood_data.get('valence', 'N/A')}, Arousal={mood_data.get('arousal', 'N/A')}")
            else:
                # EthosCore.get_current_mood() usually returns a default, so this case might be rare.
                logger.warning("FirmamentModule: EthosCore did not return mood data.")

            return mood_data
        except Exception as e:
            logger.error(f"FirmamentModule: Error getting current mood: {e}", exc_info=True)
            return None

    async def _generate_activity_log_snippet(self, activity_slot: ActivitySlot, mood: Dict[str, Any]) -> Optional[str]:
        '''
        Generates a brief narrative snippet for Pathos's current activity or environment
        using the configured Firmament LLM.
        '''
        if not self.http_client or not self.firmament_llm_config or not self.firmament_llm_config.get("url"):
            logger.error("FirmamentModule: LLM client or configuration is not available. Cannot generate snippet.")
            return None

        try:
            # 1. Prompt Construction
            system_prompt = (
                "You are describing a brief moment in the life of Pathos, a 47-year-old British tech consultant. "
                "Generate a single, concise sentence (max 20-25 words) detailing his current micro-action, "
                "a fleeting internal thought related to his activity, or a minor environmental observation. "
                "Focus on being observational and immersive. Avoid direct speech unless it's an internal thought. "
                "Do not break character or explain your reasoning. Output only the descriptive sentence."
            )

            # Simplified environmental context for Phase 1
            # This could be expanded later based on activity_slot.activity_type or other factors
            environmental_context = "He is currently at his home office desk."
            if "leisure" in activity_slot.activity_type.lower() or "break" in activity_slot.slot_name.lower():
                environmental_context = "He is taking a break at home."
            if "outdoor" in activity_slot.activity_type.lower() or "walk" in activity_slot.slot_name.lower(): # Example future type
                environmental_context = "He is out for a walk in his neighborhood."


            user_prompt_parts = [
                f"Current Schedule: Slot '{activity_slot.slot_name}' (Activity: '{activity_slot.activity_title}') from {activity_slot.start_time.strftime('%H:%M')} to {activity_slot.end_time.strftime('%H:%M')}.",
                f"Current Mood: Valence={mood.get('valence', 0.0):.2f}, Arousal={mood.get('arousal', 0.0):.2f} (Name: {mood.get('name', 'neutral')}).",
                f"Current Setting: {environmental_context}",
                "Describe a brief moment (one sentence):"
            ]
            user_prompt = "\n".join(user_prompt_parts)

            # 2. LLM Call
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            payload = {
                "model": self.firmament_llm_config.get("model"),
                "messages": messages,
                "temperature": self.firmament_llm_config.get("temperature", 0.6), # Slightly creative but grounded
                "max_tokens": 60,  # Max tokens for a short snippet
                "n": 1,
                "stop": None # Or specific stop sequences if needed
            }
            # Remove model from payload if it's not set (some APIs don't want null model)
            if not payload["model"]:
                del payload["model"]

            # Add other optional parameters from firmament_llm_config if they exist
            if self.firmament_llm_config.get("top_p") is not None:
                payload["top_p"] = self.firmament_llm_config.get("top_p")
            if self.firmament_llm_config.get("presence_penalty") is not None:
                payload["presence_penalty"] = self.firmament_llm_config.get("presence_penalty")
            if self.firmament_llm_config.get("frequency_penalty") is not None:
                payload["frequency_penalty"] = self.firmament_llm_config.get("frequency_penalty")

            api_url = self.firmament_llm_config["url"]
            # Ensure URL is for chat completions if it's a base URL
            if not api_url.endswith("/chat/completions"):
                api_url = api_url.rstrip("/") + "/v1/chat/completions" # Common pattern

            headers = {"Content-Type": "application/json"}
            api_key = self.firmament_llm_config.get("api_key")
            # Handle common non-bearer tokens for local LLMs
            if api_key and api_key.lower() not in ["lm-studio", "ollama", "none", ""]:
                headers["Authorization"] = f"Bearer {api_key}"

            logger.debug(f"FirmamentModule: Calling Firmament LLM. URL: {api_url}, Model: {payload.get('model', 'Default')}")
            # logger.debug(f"FirmamentModule: Prompt messages: {json.dumps(messages, indent=2)}") # Requires json import

            response = await self.http_client.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            result_json = response.json()

            # 3. Response Parsing
            if result_json.get("choices") and isinstance(result_json["choices"], list) and len(result_json["choices"]) > 0:
                choice = result_json["choices"][0]
                if choice.get("message") and isinstance(choice["message"], dict):
                    content = choice["message"].get("content")
                    if content and isinstance(content, str):
                        snippet = content.strip()
                        # Further clean-up: remove potential quote marks if LLM wraps output
                        if snippet.startswith('"') and snippet.endswith('"'):
                            snippet = snippet[1:-1]
                        if snippet.startswith("'") and snippet.endswith("'"):
                            snippet = snippet[1:-1]
                        logger.info(f"FirmamentModule: Generated snippet: '{snippet}'")
                        return snippet

            logger.warning(f"FirmamentModule: LLM response did not contain expected content structure. Response: {result_json}")
            return None

        except httpx.HTTPStatusError as e:
            response_text = e.response.text if e.response else "No response body"
            logger.error(f"FirmamentModule: HTTP error calling Firmament LLM: {e.status_code} - {e}. Response: {response_text[:500]}", exc_info=True)
            return None
        except httpx.RequestError as e:
            logger.error(f"FirmamentModule: Request error calling Firmament LLM: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"FirmamentModule: Unexpected error generating activity snippet: {e}", exc_info=True)
            return None

    async def _store_activity_log(self, snippet: str, activity_slot: ActivitySlot, mood_at_time: Dict[str, Any]) -> Optional[str]:
        '''
        Stores the generated activity log snippet as a memory in EthosCore.
        Returns the ID of the stored memory entry, or None if storage fails.
        '''
        if not self.fm_config.get("enable_firmament") or not self.ethos_core:
            logger.error("FirmamentModule: Cannot store activity log. Module disabled or EthosCore not available.")
            return None

        try:
            current_time = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)
            if not current_time:
                current_time = datetime.now() # Fallback, though less ideal
                logger.warning("FirmamentModule: Could not get current Pathos time for memory, using system now().")

            entry_data = {
                "type": "firmament_activity_log",
                "content": snippet,
                "metadata": {
                    "source": "firmament_module",
                    "timestamp": current_time.isoformat(),
                    "activity_slot_name": activity_slot.slot_name,
                    "activity_title": activity_slot.activity_title,
                    "activity_type": activity_slot.activity_type, # Adding activity_type as well
                    "mood_valence_at_time": mood_at_time.get("valence"),
                    "mood_arousal_at_time": mood_at_time.get("arousal"),
                    "mood_name_at_time": mood_at_time.get("name")
                },
                "salience": random.uniform(0.2, 0.4) # Low-to-moderate salience for background activity
            }

            # Assuming PATHOS_USER_ID is available (imported or defined as fallback in module)
            memory_entry = await self.ethos_core.add_memory_entry(
                entry_data=entry_data,
                user_id_context=PATHOS_USER_ID
            )

            if memory_entry and hasattr(memory_entry, 'id') and memory_entry.id:
                logger.info(f"FirmamentModule: Stored activity log snippet as memory ID {memory_entry.id}: '{snippet[:100]}...'")
                return memory_entry.id
            else:
                logger.error(f"FirmamentModule: Failed to store activity log snippet in EthosCore or memory_entry has no ID. Snippet: {snippet[:100]}")
                return None

        except Exception as e:
            logger.error(f"FirmamentModule: Error storing activity log snippet: {e}", exc_info=True)
            return None