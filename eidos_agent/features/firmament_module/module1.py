# eidos_agent/features/firmament_module/module1.py
import asyncio
import httpx
import logging
import time
import random
import json # Added for potential debug logging of JSON payloads
from typing import Optional, TYPE_CHECKING, Dict, Any, List, Tuple
from datetime import datetime, timezone # Ensure timezone is imported

from eidos_agent.core.config import Config, FirmamentModuleConfig, LLMConfig
from eidos_agent.persona_logic.chronos_engine.models import ActivitySlot, ActivitySlotDetails
# Attempt to import PATHOS_USER_ID, provide a fallback if not found
try:
    from eidos_agent.persona_logic.chronos_engine.engine import PATHOS_USER_ID
except ImportError:
    # This print will only show if logger is not yet configured during import time
    # print("Warning: Could not import PATHOS_USER_ID from chronos_engine.engine. Using default for FirmamentModule.")
    PATHOS_USER_ID = "pathos_agent_internal"

if TYPE_CHECKING:
    from eidos_agent.persona_logic.ethos_core.core import EthosCore
    from eidos_agent.persona_logic.chronos_engine.engine import ChronosEngine
    from eidos_agent.features.oneiros.module import OneirosModule
    # This import is needed for NPCProfile type hint if _simulate_npc_dialogue uses it.
    # For this reconstruction, _generate_npc_interaction_snippet doesn't strictly need it yet.
    from eidos_agent.persona_logic.social_graph.models import NPCProfile


logger = logging.getLogger(__name__)

# Availability Status Constants
AVAILABILITY_STATUS_BUSY_DEEP_WORK = "BUSY_DEEP_WORK"
AVAILABILITY_STATUS_BUSY_MEETING = "BUSY_MEETING"
AVAILABILITY_STATUS_BUSY_GENERAL_WORK = "BUSY_GENERAL_WORK"
AVAILABILITY_STATUS_LIGHT_ACTIVITY = "LIGHT_ACTIVITY"
AVAILABILITY_STATUS_AVAILABLE = "AVAILABLE"
AVAILABILITY_STATUS_UNKNOWN = "UNKNOWN"

class FirmamentModule:
    def __init__(self, config: Config, ethos_core: 'EthosCore', chronos_engine: 'ChronosEngine', oneiros_module: 'OneirosModule'):
        self.config = config
        self.fm_config: FirmamentModuleConfig = config.get_firmament_module_config()
        self.ethos_core = ethos_core
        self.chronos_engine = chronos_engine
        self.oneiros_module = oneiros_module # Added in P3

        self.http_client: Optional[httpx.AsyncClient] = None
        self.firmament_llm_config: Optional[LLMConfig] = None # For the primary Firmament LLM

        self.last_npc_interaction_time: float = 0.0 # Added in P3
        # self.received_dream_fragments is in OneirosModule

        if self.fm_config.get("enable_firmament", False):
            llm_role = self.fm_config.get("firmament_llm_role") # This is for the main Firmament LLM
            if llm_role:
                self.firmament_llm_config = self.config.get_llm_config(llm_role)

            if not self.firmament_llm_config or not self.firmament_llm_config.get("url"):
                logger.error(
                    f"FirmamentModule: LLM for role '{llm_role}' (firmament_llm_role) is not configured or lacks a URL. "
                    "Firmament will be impaired."
                )
            else:
                timeout_val = float(self.firmament_llm_config.get('timeout', 60.0))
                self.http_client = httpx.AsyncClient(timeout=timeout_val)
                logger.info(
                    f"FirmamentModule initialized with Firmament LLM role '{llm_role}'. HTTP client ready."
                )
        else:
            logger.info("FirmamentModule is disabled by configuration.")

    async def start(self):
        if self.fm_config.get("enable_firmament") and self.http_client:
            logger.info("FirmamentModule started and ready.")
        elif self.fm_config.get("enable_firmament"):
             logger.warning(
                "FirmamentModule is enabled in config, but the Firmament LLM http_client "
                "is not available. Firmament will not function correctly."
            )

    async def close(self):
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()
            logger.info("FirmamentModule HTTP client closed.")
        else:
            logger.info("FirmamentModule resources (if any) considered closed.")

    async def _call_llm_api(self,
                            messages: List[Dict[str, str]],
                            llm_role_name: str,
                            max_tokens_override: Optional[int] = None,
                            temperature_override: Optional[float] = None,
                            top_p_override: Optional[float] = None,
                            presence_penalty_override: Optional[float] = None,
                            frequency_penalty_override: Optional[float] = None
                            ) -> Optional[str]:
        '''
        A generic helper to call a configured LLM API (OpenAI compatible).
        '''
        if not self.http_client: # self.http_client is the general client for Firmament LLM
            logger.error(f"FirmamentModule: Main HTTP client not available for LLM call (role: {llm_role_name}).")
            # In a multi-LLM client scenario, this might select a client based on llm_role_name
            return None

        llm_config_to_use = self.config.get_llm_config(llm_role_name)
        if not llm_config_to_use or not llm_config_to_use.get("url"):
            logger.error(f"FirmamentModule: LLM config for role '{llm_role_name}' not found or URL missing.")
            return None

        payload: Dict[str, Any] = {
            "model": llm_config_to_use.get("model"),
            "messages": messages,
            "temperature": temperature_override if temperature_override is not None else llm_config_to_use.get("temperature", 0.7),
            "max_tokens": max_tokens_override if max_tokens_override is not None else llm_config_to_use.get("max_tokens", 150),
        }

        optional_params = {
            "top_p": top_p_override if top_p_override is not None else llm_config_to_use.get("top_p"),
            "presence_penalty": presence_penalty_override if presence_penalty_override is not None else llm_config_to_use.get("presence_penalty"),
            "frequency_penalty": frequency_penalty_override if frequency_penalty_override is not None else llm_config_to_use.get("frequency_penalty"),
        }
        for param_key, param_val in optional_params.items():
            if param_val is not None: # Only add if a value is actually defined
                payload[param_key] = param_val

        if not payload.get("model"):
             if "model" in payload: del payload["model"]

        api_url = str(llm_config_to_use["url"])
        if not api_url.endswith(("/chat/completions", "/completions")): # Allow for non-chat if needed later
            # Defaulting to chat completions, common for instruct models too
            api_url = api_url.rstrip("/") + "/v1/chat/completions"

        headers = {"Content-Type": "application/json"}
        api_key = llm_config_to_use.get("api_key")
        # Added "vllm" to the list of common local/no-bearer keys
        if api_key and api_key.lower() not in ["lm-studio", "ollama", "none", "", "vllm"]:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            logger.debug(f"FirmamentModule: Calling LLM role '{llm_role_name}'. URL: {api_url}, Model: {payload.get('model', 'Default')}, Temp: {payload['temperature']:.2f}, MaxTokens: {payload['max_tokens']}")
            response = await self.http_client.post(api_url, headers=headers, json=payload)
            response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx responses
            result_json = response.json()

            # Standard OpenAI-like response structure
            if result_json.get("choices") and isinstance(result_json["choices"], list) and len(result_json["choices"]) > 0:
                choice = result_json["choices"][0]
                if choice.get("message") and isinstance(choice["message"], dict):
                    content = choice["message"].get("content")
                    if content and isinstance(content, str):
                        return content.strip() # Return the actual text content

            # Fallback for some non-chat/streaming or slightly different structures (e.g. some Cohere, older models)
            # This part might need adjustment based on actual non-OpenAI-chat models if used.
            if result_json.get("text") and isinstance(result_json.get("text"), str): # e.g. some completion models
                 return result_json.get("text").strip()
            if result_json.get("generations") and isinstance(result_json["generations"], list) and len(result_json["generations"]) > 0: # e.g. Cohere
                if result_json["generations"][0].get("text"):
                    return result_json["generations"][0].get("text").strip()

            logger.warning(f"LLM call to role '{llm_role_name}' response missing expected content structure (choices[0].message.content, text, or generations[0].text). Response: {result_json}")
            return None
        except httpx.HTTPStatusError as e:
            response_text = e.response.text if e.response else "No response body"
            logger.error(f"HTTP error from LLM role '{llm_role_name}': {e.response.status_code} - {e}. Response: {response_text[:500]}", exc_info=False) # exc_info=False to reduce noise for common HTTP errors
            return None
        except httpx.TimeoutException as e: # Specific catch for timeouts
            logger.error(f"Timeout error calling LLM role '{llm_role_name}': {e}", exc_info=False)
            return None
        except httpx.RequestError as e: # Catch other httpx request errors (network, connection, etc.)
            logger.error(f"Request error calling LLM role '{llm_role_name}': {e}", exc_info=False)
            return None
        except json.JSONDecodeError as e: # If response is not valid JSON
            logger.error(f"JSON decode error from LLM role '{llm_role_name}': {e}. Response text: {response.text[:500] if 'response' in locals() else 'N/A'}", exc_info=False)
            return None
        except Exception as e: # Generic catch-all for unexpected errors
            logger.error(f"Unexpected error calling LLM role '{llm_role_name}': {e}", exc_info=True)
            return None

    async def _get_current_activity_slot(self) -> Optional[ActivitySlot]:
        if not self.fm_config.get("enable_firmament"):
            logger.debug("FirmamentModule is disabled, cannot get current activity slot.")
            return None
        try:
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
        if not self.fm_config.get("enable_firmament"):
            logger.debug("FirmamentModule is disabled, cannot get current mood.")
            return None
        try:
            mood_data = self.ethos_core.get_current_mood()
            if mood_data:
                logger.debug(f"FirmamentModule: Current mood: Valence={mood_data.get('valence', 'N/A')}, Arousal={mood_data.get('arousal', 'N/A')}")
            else:
                logger.warning("FirmamentModule: EthosCore did not return mood data.")
            return mood_data
        except Exception as e:
            logger.error(f"FirmamentModule: Error getting current mood: {e}", exc_info=True)
            return None

    async def _generate_activity_log_snippet(self, activity_slot: ActivitySlot, mood: Dict[str, Any]) -> Optional[str]:
        if not self.http_client or not self.firmament_llm_config or not self.firmament_llm_config.get("url"):
            logger.error("FirmamentModule: Firmament LLM client or configuration is not available. Cannot generate snippet.")
            return None

        firmament_llm_role = self.fm_config.get("firmament_llm_role", "LOGOS_TECHNE") # Fallback role

        try:
            # Dream Influence
            dream_influence_text = None
            if self.oneiros_module:
                try:
                    recent_dream_summary = self.oneiros_module.get_last_dream_summary(max_age_hours=8)
                    if recent_dream_summary:
                        dream_influence_text = f"A recent dream had themes of: '{recent_dream_summary[:150].replace('\n', ' ')}...'"
                        logger.debug(f"FirmamentModule: Adding dream influence to prompt: {dream_influence_text}")
                except Exception as e:
                    logger.error(f"FirmamentModule: Error getting dream summary from OneirosModule: {e}", exc_info=False)

            # Environmental context determination (with location from P3)
            environmental_context = "He is currently at his home."
            if activity_slot.activity_details and activity_slot.activity_details.location_context:
                environmental_context = f"He is at {activity_slot.activity_details.location_context}."
            elif "leisure" in activity_slot.activity_type.lower() or "break" in activity_slot.slot_name.lower():
                environmental_context = "He is taking a break at home."
            elif "work" in activity_slot.activity_type.lower() or "office" in activity_slot.slot_name.lower(): # Ensure slot_name is checked
                 environmental_context = "He is at his home office desk."

            system_prompt = (
                "You are describing a brief moment in the life of Pathos, a 47-year-old British tech consultant. "
                "Generate a single, concise sentence (max 20-25 words) detailing his current micro-action, "
                "a fleeting internal thought related to his activity, or a minor environmental observation. "
                "Focus on being observational and immersive. Avoid direct speech unless it's an internal thought. "
                "Do not break character or explain your reasoning. Output only the descriptive sentence."
            )
            user_prompt_parts = [
                f"Current Schedule: Slot '{activity_slot.slot_name}' (Activity: '{activity_slot.activity_title}') from {activity_slot.start_time.strftime('%H:%M')} to {activity_slot.end_time.strftime('%H:%M')}.",
                f"Current Mood: Valence={mood.get('valence', 0.0):.2f}, Arousal={mood.get('arousal', 0.0):.2f} (Name: {mood.get('name', 'neutral')})."
            ]
            if dream_influence_text:
                user_prompt_parts.append(f"Subtle Influence from Recent Dream: {dream_influence_text}")
            user_prompt_parts.append(f"Current Setting: {environmental_context}")
            user_prompt_parts.append("Describe a brief moment (one sentence):")
            user_prompt = "\n".join(user_prompt_parts)

            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

            firmament_llm_role = self.fm_config.get("firmament_llm_role", "LOGOS_TECHNE") # Ensure consistent role usage
            snippet_text = await self._call_llm_api(
                messages=messages,
                llm_role_name=firmament_llm_role,
                max_tokens_override=60,
                temperature_override=self.firmament_llm_config.get("temperature", 0.6) if self.firmament_llm_config else 0.6
            )

            if snippet_text:
                # Further clean-up: remove potential quote marks if LLM wraps output
                # This specific cleaning can remain here if needed.
                if snippet_text.startswith('"') and snippet_text.endswith('"'):
                    snippet_text = snippet_text[1:-1]
                if snippet_text.startswith("'") and snippet_text.endswith("'"):
                    snippet_text = snippet_text[1:-1]
                logger.info(f"FirmamentModule: Generated snippet: '{snippet_text}'")
                return snippet_text

            logger.warning(f"FirmamentModule: _call_llm_api for snippet generation returned None or empty. Role: {firmament_llm_role}")
            return None
        except Exception as e: # General exception handling for the logic within this method
            logger.error(f"FirmamentModule: Unexpected error in _generate_activity_log_snippet logic: {e}", exc_info=True)
            return None

    async def _store_activity_log(self, snippet: str, activity_slot: ActivitySlot, mood_at_time: Dict[str, Any], related_intention_id: Optional[str] = None, extra_metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        if not self.fm_config.get("enable_firmament") or not self.ethos_core:
            logger.error("FirmamentModule: Cannot store activity log. Module disabled or EthosCore not available.")
            return None
        try:
            current_time = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)
            if not current_time:
                current_time = datetime.now(timezone.utc)
                logger.warning("FirmamentModule: Could not get current Pathos time for memory, using system now().")

            current_metadata = {
                "source": "firmament_module", "timestamp": current_time.isoformat(),
                "activity_slot_name": activity_slot.slot_name, "activity_title": activity_slot.activity_title,
                "activity_type": activity_slot.activity_type,
                "mood_valence_at_time": mood_at_time.get("valence"),
                "mood_arousal_at_time": mood_at_time.get("arousal"),
                "mood_name_at_time": mood_at_time.get("name")
            }
            if activity_slot.activity_details and activity_slot.activity_details.location_context: # Store location if available
                 current_metadata["location_context_at_time"] = activity_slot.activity_details.location_context

            if related_intention_id:
                current_metadata["related_intention_memory_id"] = related_intention_id
            if extra_metadata:
                current_metadata.update(extra_metadata)

            entry_data = {
                "type": "firmament_activity_log", "content": snippet,
                "metadata": current_metadata, "salience": random.uniform(0.2, 0.4)
            }
            if extra_metadata and "interaction_type" in extra_metadata:
                entry_data["salience"] = random.uniform(0.3, 0.5)

            memory_entry = await self.ethos_core.add_memory_entry(entry_data=entry_data, user_id_context=PATHOS_USER_ID)
            if memory_entry and hasattr(memory_entry, 'id') and memory_entry.id:
                logger.info(f"FirmamentModule: Stored activity log snippet as memory ID {memory_entry.id}: '{snippet[:100]}...'")
                return memory_entry.id
            else:
                logger.error(f"FirmamentModule: Failed to store activity log snippet in EthosCore. Snippet: {snippet[:100]}")
                return None
        except Exception as e:
            logger.error(f"FirmamentModule: Error storing activity log snippet: {e}", exc_info=True)
            return None

    def _create_dummy_activity_slot_for_context(self, title_context: str) -> ActivitySlot:
        dummy_details = ActivitySlotDetails(description=f"Context: {title_context}", location_context="Implicit Location")
        # Get current time for the dummy slot, ideally Pathos's local time
        # This is a sync method, but usually EthosCore.get_local_datetime_for_user is async.
        # For a sync helper, we might have to use datetime.now(timezone.utc)
        # Or make this helper async if it needs to await ethos_core call.
        # For reconstruction, assuming it can use datetime.now() for simplicity if not in async context.
        now_dt = datetime.now(timezone.utc)
        return ActivitySlot(
            user_id=PATHOS_USER_ID, date=now_dt.date(),
            start_time=now_dt.time(), end_time=now_dt.time(),
            slot_name="AdHocFirmamentActivity", activity_title=title_context[:100],
            activity_type="internal_processing", activity_details=dummy_details,
            generated_at=now_dt # ensure generated_at is set
        )

    async def run_simulation_tick(self):
        if not self.fm_config.get("enable_firmament", False):
            logger.debug("FirmamentModule.run_simulation_tick: Module is disabled. Skipping tick.")
            return
        logger.debug("FirmamentModule: Starting simulation tick.")
        try:
            activity_slot = await self._get_current_activity_slot()
            if not activity_slot:
                logger.info("FirmamentModule: No current activity slot for Pathos. Skipping snippet generation for this tick.")
                return

            mood = await self._get_current_mood()
            if not mood:
                mood = {"name": "unknown", "valence": 0.0, "arousal": 0.0}
                logger.warning("FirmamentModule: Could not retrieve current mood. Using default for tick.")

            snippet = await self._generate_activity_log_snippet(activity_slot, mood)
            if snippet:
                await self._store_activity_log(snippet, activity_slot, mood)
            else:
                logger.info("FirmamentModule: No activity log snippet generated during this simulation tick.")

            # NPC Interaction part
            if self._is_npc_interaction_warranted(activity_slot, None):
                npc_profile_to_use: Optional[NPCProfile] = None
                interaction_source_description = "activity"

                if activity_slot and activity_slot.activity_details and isinstance(activity_slot.activity_details.metadata, dict):
                    specific_npc_id = activity_slot.activity_details.metadata.get('npc_id')
                    specific_npc_name = activity_slot.activity_details.metadata.get('npc_name')
                    if specific_npc_id or specific_npc_name:
                        logger.info(f"FirmamentModule: Attempting to fetch persistent NPC for activity. ID: {specific_npc_id}, Name: {specific_npc_name}")
                        if self.ethos_core: # Ensure ethos_core is available
                            npc_profile_to_use = await self.ethos_core.get_npc_profile(npc_id=specific_npc_id, name=specific_npc_name)
                        if npc_profile_to_use:
                            logger.info(f"FirmamentModule: Using persistent NPC profile: {npc_profile_to_use.name} (ID: {npc_profile_to_use.npc_id}) for activity-driven interaction.")
                            interaction_source_description = f"activity with known NPC {npc_profile_to_use.name}"
                        else:
                            logger.warning(f"FirmamentModule: Persistent NPC not found for ID '{specific_npc_id}' or name '{specific_npc_name}'. Falling back to generic for activity.")

                if not npc_profile_to_use: # If no specific NPC from activity, or not found, or ethos_core missing
                    logger.debug("FirmamentModule: Determining generic NPC profile for activity context.")
                    npc_profile_to_use = self._determine_generic_npc_profile_for_context(activity_slot, None)
                    if npc_profile_to_use:
                        interaction_source_description = f"activity with generic NPC ({npc_profile_to_use.name})"

                if npc_profile_to_use:
                    initial_dialogue_context = f"Pathos is currently in activity '{activity_slot.activity_title if activity_slot else 'an unspecified activity'}'"
                    if activity_slot and activity_slot.activity_details and activity_slot.activity_details.location_context:
                        initial_dialogue_context += f" at {activity_slot.activity_details.location_context}."
                    else:
                        initial_dialogue_context += "."

                    logger.info(f"FirmamentModule: Attempting to simulate NPC dialogue with '{npc_profile_to_use.name}' for {interaction_source_description}.")
                    dialogue_data = await self._simulate_npc_dialogue(npc_profile_to_use, initial_dialogue_context, mood)

                    if dialogue_data and dialogue_data.get("transcript"):
                        logger.info(f"FirmamentModule: Simulated NPC dialogue ({interaction_source_description}): {dialogue_data.get('summary')}")
                        self.last_npc_interaction_time = time.time()

                        current_time_for_memory = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)
                        if not current_time_for_memory: current_time_for_memory = datetime.now(timezone.utc)

                        event_metadata = {
                            "npc_id": npc_profile_to_use.npc_id,
                            "npc_name": npc_profile_to_use.name,
                            "npc_role_description": npc_profile_to_use.role_description,
                            "dialogue_transcript": dialogue_data["transcript"],
                            "key_facts_learned_by_pathos": dialogue_data["new_facts_learned_by_pathos"],
                            "key_info_revealed_by_pathos": dialogue_data["key_info_revealed_by_pathos"],
                            "source_of_interaction": f"firmament_{interaction_source_description.replace(' ', '_')}",
                            "activity_slot_name_at_time": activity_slot.slot_name if activity_slot else "N/A",
                            "activity_title_at_time": activity_slot.activity_title if activity_slot else "N/A",
                            "location_at_time": activity_slot.activity_details.location_context if activity_slot and activity_slot.activity_details else "Unknown",
                            "mood_name_at_time": mood.get("name"),
                            "mood_valence_at_time": mood.get("valence"),
                            "mood_arousal_at_time": mood.get("arousal"),
                            "timestamp": current_time_for_memory.isoformat()
                        }
                        entry_data = {
                            "type": "npc_dialogue_event",
                            "content": dialogue_data["summary"] or "A brief NPC interaction occurred.",
                            "metadata": event_metadata,
                            "salience": random.uniform(0.4, 0.65)
                        }
                        try:
                            if self.ethos_core: # Ensure ethos_core is available before calling
                                memory_entry = await self.ethos_core.add_memory_entry(entry_data=entry_data, user_id_context=PATHOS_USER_ID)
                                if memory_entry and hasattr(memory_entry, 'id') and memory_entry.id:
                                    logger.info(f"FirmamentModule: Stored NPC dialogue event ({interaction_source_description}) as memory ID {memory_entry.id}.")
                                else:
                                    logger.warning(f"FirmamentModule: Failed to store NPC dialogue event ({interaction_source_description}) or no ID returned.")
                            else:
                                logger.error("FirmamentModule: EthosCore not available, cannot store NPC dialogue event.")
                        except Exception as e_mem_store:
                            logger.error(f"FirmamentModule: Error storing NPC dialogue event ({interaction_source_description}): {e_mem_store}", exc_info=True)
                    elif dialogue_data:
                         logger.warning(f"FirmamentModule: NPC dialogue simulation ({interaction_source_description}) produced data but no transcript. Summary: {dialogue_data.get('summary')}")
                    else:
                        logger.debug(f"FirmamentModule: NPC dialogue simulation ({interaction_source_description}) did not produce data.")
                else:
                    logger.debug("FirmamentModule: No specific or generic NPC profile determined for activity-driven interaction. Skipping dialogue.")
            logger.debug("FirmamentModule: Simulation tick finished.")
        except Exception as e:
            logger.error(f"FirmamentModule: Unhandled error during simulation tick: {e}", exc_info=True)

    async def receive_subconscious_intention(self, intention: str, metadata: Dict[str, Any]):
        if not self.fm_config.get("enable_firmament", False):
            logger.debug("FirmamentModule.receive_subconscious_intention: Module is disabled. Ignoring intention.")
            return
        logger.info(f"FirmamentModule: Received intention from subconscious_node: '{intention}'. Metadata: {metadata}")
        original_intention_memory_id: Optional[str] = None
        if self.ethos_core:
            try:
                current_time = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)
                if not current_time: current_time = datetime.now(timezone.utc)

                full_metadata = {
                    "source": "subconscious_node_intention", "original_metadata": metadata,
                    "received_at_firmament_timestamp": current_time.isoformat()
                }
                entry_data = {
                    "type": "received_subconscious_intention", "content": intention,
                    "metadata": full_metadata, "salience": random.uniform(0.5, 0.7)
                }
                memory_entry = await self.ethos_core.add_memory_entry(entry_data=entry_data, user_id_context=PATHOS_USER_ID)
                if memory_entry and hasattr(memory_entry, 'id') and memory_entry.id:
                    original_intention_memory_id = memory_entry.id
                    logger.info(f"FirmamentModule: Stored received intention as memory ID {original_intention_memory_id}.")
                else:
                    logger.error("FirmamentModule: Failed to store received intention in EthosCore.")
            except Exception as e:
                logger.error(f"FirmamentModule: Error storing original subconscious intention: {e}", exc_info=True)
        else:
            logger.error("FirmamentModule: EthosCore not available. Cannot store original intention.")

        logger.info(f"FirmamentModule: Triggering simulation for intention: '{intention[:100]}...'")
        try:
            await self._simulate_intention_consequence(intention, metadata, original_intention_memory_id, current_mood_override=None)
        except Exception as e:
            logger.error(f"FirmamentModule: Error calling _simulate_intention_consequence for intention '{intention[:100]}...': {e}", exc_info=True)

    async def _simulate_intention_consequence(self, intention: str, source_metadata: Dict[str, Any], original_intention_memory_id: Optional[str], current_mood_override: Optional[Dict[str,Any]] = None):
        logger.info(f"FirmamentModule: Simulating consequence for intention (ID: {original_intention_memory_id}): '{intention[:100]}...'")
        if not self.http_client : # Check generic http_client, _call_llm_api will check specific role config
            logger.error("FirmamentModule: HTTP client not available for simulating intention consequence.")
            return

        current_activity_slot = await self._get_current_activity_slot()
        # Use provided mood if available (e.g., passed from a context where mood was already fetched)
        current_mood = current_mood_override if current_mood_override else await self._get_current_mood()
        if not current_mood: current_mood = {"name": "neutral", "valence": 0.0, "arousal": 0.0}

        # NPC dialogue simulation part, if warranted by intention
        if self._is_npc_interaction_warranted(current_activity_slot, intention):
            npc_profile_to_use: Optional[NPCProfile] = None
            interaction_source_description = "intention"

            # Check activity metadata first for a specific NPC, even if intention-driven
            if current_activity_slot and current_activity_slot.activity_details and isinstance(current_activity_slot.activity_details.metadata, dict):
                specific_npc_id = current_activity_slot.activity_details.metadata.get('npc_id')
                specific_npc_name = current_activity_slot.activity_details.metadata.get('npc_name')
                if specific_npc_id or specific_npc_name:
                    logger.info(f"FirmamentModule: Attempting to fetch persistent NPC for intention context (from activity metadata). ID: {specific_npc_id}, Name: {specific_npc_name}")
                    if self.ethos_core:
                        npc_profile_to_use = await self.ethos_core.get_npc_profile(npc_id=specific_npc_id, name=specific_npc_name)
                    if npc_profile_to_use:
                        logger.info(f"FirmamentModule: Using persistent NPC profile: {npc_profile_to_use.name} (ID: {npc_profile_to_use.npc_id}) for intention-driven interaction.")
                        interaction_source_description = f"intention with known NPC {npc_profile_to_use.name}"
                    else:
                        logger.warning(f"FirmamentModule: Persistent NPC (from activity metadata) not found for ID '{specific_npc_id}' or name '{specific_npc_name}'. Falling back to generic for intention.")

            if not npc_profile_to_use: # Fallback to generic if no specific NPC from activity or not found
                logger.debug("FirmamentModule: Determining generic NPC profile for intention context.")
                npc_profile_to_use = self._determine_generic_npc_profile_for_context(current_activity_slot, intention)
                if npc_profile_to_use:
                     interaction_source_description = f"intention with generic NPC ({npc_profile_to_use.name})"

            if npc_profile_to_use:
                initial_dialogue_context = f"Pathos is considering the intention: '{intention}'."
                if current_activity_slot and current_activity_slot.activity_details and current_activity_slot.activity_details.location_context:
                    initial_dialogue_context += f" He is currently at {current_activity_slot.activity_details.location_context} during activity '{current_activity_slot.activity_title}'."
                elif current_activity_slot:
                    initial_dialogue_context += f" He is currently in activity '{current_activity_slot.activity_title}'."

                logger.info(f"FirmamentModule: Attempting to simulate NPC dialogue with '{npc_profile_to_use.name}' for {interaction_source_description}: {intention}")
                dialogue_data = await self._simulate_npc_dialogue(npc_profile_to_use, initial_dialogue_context, current_mood)

                if dialogue_data and dialogue_data.get("transcript"):
                    logger.info(f"FirmamentModule: Simulated NPC dialogue ({interaction_source_description}): {dialogue_data.get('summary')}")
                    self.last_npc_interaction_time = time.time()

                    current_time_for_memory = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)
                    if not current_time_for_memory: current_time_for_memory = datetime.now(timezone.utc)

                    activity_slot_name = current_activity_slot.slot_name if current_activity_slot else "N/A"
                    activity_title = current_activity_slot.activity_title if current_activity_slot else "N/A"
                    location = current_activity_slot.activity_details.location_context if current_activity_slot and current_activity_slot.activity_details else "Unknown"

                    event_metadata = {
                        "npc_id": npc_profile_to_use.npc_id,
                        "npc_name": npc_profile_to_use.name,
                        "npc_role_description": npc_profile_to_use.role_description,
                        "dialogue_transcript": dialogue_data["transcript"],
                        "key_facts_learned_by_pathos": dialogue_data["new_facts_learned_by_pathos"],
                        "key_info_revealed_by_pathos": dialogue_data["key_info_revealed_by_pathos"],
                        "source_of_interaction": f"firmament_{interaction_source_description.replace(' ', '_')}_simulation",
                        "triggered_by_intention_id": original_intention_memory_id,
                        "triggering_intention_text": intention,
                        "activity_slot_name_at_time": activity_slot_name,
                        "activity_title_at_time": activity_title,
                        "location_at_time": location,
                        "mood_name_at_time": current_mood.get("name"),
                        "mood_valence_at_time": current_mood.get("valence"),
                        "mood_arousal_at_time": current_mood.get("arousal"),
                        "timestamp": current_time_for_memory.isoformat()
                    }
                    entry_data = {
                        "type": "npc_dialogue_event",
                        "content": dialogue_data["summary"] or "A brief interaction occurred regarding an intention.",
                        "metadata": event_metadata,
                        "salience": random.uniform(0.45, 0.7)
                    }
                    try:
                        if self.ethos_core:
                            memory_entry = await self.ethos_core.add_memory_entry(entry_data=entry_data, user_id_context=PATHOS_USER_ID)
                            if memory_entry and hasattr(memory_entry, 'id') and memory_entry.id:
                                logger.info(f"FirmamentModule: Stored NPC dialogue event ({interaction_source_description}) as memory ID {memory_entry.id}.")
                            else:
                                logger.warning(f"FirmamentModule: Failed to store NPC dialogue event ({interaction_source_description}) or no ID returned.")
                        else:
                             logger.error("FirmamentModule: EthosCore not available, cannot store intention-driven NPC dialogue event.")
                    except Exception as e_mem_store:
                        logger.error(f"FirmamentModule: Error storing NPC dialogue event ({interaction_source_description}): {e_mem_store}", exc_info=True)
                elif dialogue_data:
                    logger.warning(f"FirmamentModule: NPC dialogue simulation ({interaction_source_description}) produced data but no transcript. Summary: {dialogue_data.get('summary')}")
                else:
                    logger.debug(f"FirmamentModule: NPC dialogue simulation ({interaction_source_description}) did not produce data.")
            else:
                logger.debug("FirmamentModule: No specific or generic NPC profile determined for intention-driven interaction. Skipping dialogue.")

        # Pathos's personal action simulation (original part of the method)
        activity_context_for_prompt = "Currently idle or between scheduled activities."
        if current_activity_slot:
            location_detail = ""
            if current_activity_slot.activity_details and current_activity_slot.activity_details.location_context:
                location_detail = f" at {current_activity_slot.activity_details.location_context}"
            activity_context_for_prompt = f"Currently engaged in '{current_activity_slot.activity_title}' (schedule slot: '{current_activity_slot.slot_name}'){location_detail}."

        # Dream influence (from P3)
        dream_influence_text = None
        if self.oneiros_module:
            try:
                recent_dream_summary = self.oneiros_module.get_last_dream_summary(max_age_hours=8)
                if recent_dream_summary: dream_influence_text = f"A recent dream had themes of: '{recent_dream_summary[:150].replace('\n', ' ')}...'"
            except Exception: pass # Error already logged by get_last_dream_summary or here

        system_prompt = ("Pathos has just decided to act on an internal intention. Describe his immediate reaction or first small steps. 1-3 sentences, max 50 words. Observational.")
        user_prompt_parts = [
            f"Pathos's Internal Intention: "{intention}"",
            f"His Current Mood: Valence={current_mood.get('valence', 0.0):.2f}, Arousal={current_mood.get('arousal', 0.0):.2f} (Name: {current_mood.get('name', 'unknown')})."
        ]
        if dream_influence_text: user_prompt_parts.append(f"Subtle Influence from Recent Dream: {dream_influence_text}")
        user_prompt_parts.append(f"His Current Scheduled Context: {activity_context_for_prompt}")
        user_prompt_parts.append("Describe his simulated short action or reaction sequence (1-3 sentences):")
        user_prompt = "\n".join(user_prompt_parts)

        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        firmament_llm_role = self.fm_config.get("firmament_llm_role", "LOGOS_TECHNE")
        try:
            simulated_action_snippet = await self._call_llm_api(
                messages=messages,
                llm_role_name=firmament_llm_role,
                max_tokens_override=100,
                temperature_override=self.firmament_llm_config.get("temperature", 0.5) if self.firmament_llm_config else 0.5
            )

            if simulated_action_snippet:
                # Clean up quotes if necessary (specific cleaning can remain)
                if simulated_action_snippet.startswith('"') and simulated_action_snippet.endswith('"'):
                    simulated_action_snippet = simulated_action_snippet[1:-1]
                if simulated_action_snippet.startswith("'") and simulated_action_snippet.endswith("'"):
                    simulated_action_snippet = simulated_action_snippet[1:-1]

                logger.info(f"FirmamentModule: Simulated action for intention (P2 style): '{simulated_action_snippet}'")

                activity_slot_for_storage = current_activity_slot if current_activity_slot else self._create_dummy_activity_slot_for_context(f"Simulated: {intention[:50]}...")

                await self._store_activity_log(
                    snippet=simulated_action_snippet, activity_slot=activity_slot_for_storage,
                    mood_at_time=current_mood, related_intention_id=original_intention_memory_id
                )
            else:
                logger.warning(f"FirmamentModule: _call_llm_api for P2 intention simulation returned None. Role: {firmament_llm_role}")
                # Removed 'return' here to allow flow to continue even if snippet is None,
                # consistent with original behavior where LLM failure didn't stop the method.
        except Exception as e: # Catchall for the logic within this method, including storage
            logger.error(f"Error in _simulate_intention_consequence logic: {e}", exc_info=True)

    async def _simulate_npc_dialogue(self,
                                   npc_profile: NPCProfile,
                                   initial_dialogue_context: str,
                                   pathos_mood: Dict[str, Any],
                                   max_exchanges: int = 2) -> Optional[Dict[str, Any]]:
        '''
        Simulates a multi-turn dialogue between Pathos (using PATHOS_SIM_LLM)
        and an NPC (using GENERIC_NPC_LLM and NPCProfile).
        Returns a dictionary with the transcript, summary, and extracted facts.
        '''

        pathos_sim_role = self.fm_config.get("pathos_sim_llm_role")
        npc_llm_role = self.fm_config.get("generic_npc_llm_role")
        dialogue_summary_role = self.fm_config.get("dialogue_summary_llm_role",
                                               self.fm_config.get("firmament_llm_role", "LOGOS_TECHNE")) # Fallback chain

        if not pathos_sim_role or not npc_llm_role or not dialogue_summary_role:
            logger.error("FirmamentModule: Missing LLM role configuration for dialogue simulation (pathos_sim, npc_llm, or summary_llm). Dialogue aborted.")
            return None

        # Verify that LLM configurations for these roles exist and are valid (have URLs)
        if not (self.config.get_llm_config(pathos_sim_role) and self.config.get_llm_config(pathos_sim_role).get("url")) or \
           not (self.config.get_llm_config(npc_llm_role) and self.config.get_llm_config(npc_llm_role).get("url")) or \
           not (self.config.get_llm_config(dialogue_summary_role) and self.config.get_llm_config(dialogue_summary_role).get("url")):
            logger.error(f"FirmamentModule: One or more LLM configurations for dialogue roles ('{pathos_sim_role}', '{npc_llm_role}', '{dialogue_summary_role}') are invalid or missing a URL. Dialogue aborted.")
            return None

        full_transcript: List[Dict[str, str]] = []
        # current_dialogue_context accumulates the conversation for prompts.
        # It's different from full_transcript which is for final storage.
        current_dialogue_context_for_prompts = initial_dialogue_context

        pathos_line = "" # Stores the last line from Pathos for NPC context
        npc_line = ""    # Stores the last line from NPC for Pathos context

        for i in range(max_exchanges):
            # Pathos's Turn
            pathos_system_prompt = (
                f"You are Pathos, a 47-year-old British tech consultant. Your current mood is {pathos_mood.get('name', 'neutral')} "
                f"(Valence: {pathos_mood.get('valence',0):.2f}, Arousal: {pathos_mood.get('arousal',0):.2f}). "
                f"You are interacting with {npc_profile.name} ({npc_profile.role_description or 'a person'}). "
                f"The ongoing situation/context: {current_dialogue_context_for_prompts}. "
                f"{npc_profile.name} last said: '{npc_line if npc_line else 'This is the start of your exchange or your turn to initiate.'}' " # Provide NPC's last line
                "Generate your brief, natural next conversational line (max 1-2 short sentences, around 15-25 words). Focus on this immediate turn. Do not refuse to speak or end the conversation prematurely unless it's a natural closing."
            )
            pathos_messages = [{"role": "system", "content": pathos_system_prompt}, {"role": "user", "content": "Your line:"}]

            pathos_line_raw = await self._call_llm_api(pathos_messages, pathos_sim_role, max_tokens_override=70, temperature_override=0.7)
            if not pathos_line_raw or pathos_line_raw.lower().strip() in ["[end]", "<end>", "nothing further.", "goodbye."]:
                logger.debug(f"Pathos ended dialogue or LLM returned empty/end marker. Line: '{pathos_line_raw}'")
                break
            pathos_line = pathos_line_raw # Keep the cleaned one for next turn's context
            full_transcript.append({"speaker": "Pathos", "line": pathos_line})
            current_dialogue_context_for_prompts += f" Pathos: "{pathos_line}""

            # NPC's Turn
            npc_persona = npc_profile.persona_summary_prompt if npc_profile.persona_summary_prompt else f"You are {npc_profile.name}, {npc_profile.role_description or 'a person'}."
            npc_system_prompt = (
                f"{npc_persona} "
                f"You are speaking with Pathos. The ongoing situation/context: {current_dialogue_context_for_prompts}. " # This now includes Pathos's latest line.
                "Generate your brief, natural next conversational line in character (max 1-2 short sentences, around 15-25 words). Do not refuse to speak or end the conversation prematurely unless it's a natural closing."
            )
            npc_messages = [{"role": "system", "content": npc_system_prompt}, {"role": "user", "content": "Your line:"}]

            npc_line_raw = await self._call_llm_api(npc_messages, npc_llm_role, max_tokens_override=70, temperature_override=0.75)
            if not npc_line_raw or npc_line_raw.lower().strip() in ["[end]", "<end>", "nothing further.", "goodbye."]:
                logger.debug(f"NPC {npc_profile.name} ended dialogue or LLM returned empty/end marker. Line: '{npc_line_raw}'")
                break
            npc_line = npc_line_raw # Keep the cleaned one for next turn's context
            full_transcript.append({"speaker": npc_profile.name, "line": npc_line})
            current_dialogue_context_for_prompts += f" {npc_profile.name}: "{npc_line}""


        if not full_transcript:
            logger.info("FirmamentModule: No dialogue turns were generated for NPC interaction.")
            return None

        # Dialogue Summarization & Fact Extraction
        transcript_str = "\n".join([f"{turn['speaker']}: {turn['line']}" for turn in full_transcript])
        summary_system_prompt = (
            "You are an analytical assistant. Based on the following dialogue involving Pathos, provide a concise one-sentence summary from Pathos's perspective. "
            "Also, list any new, concrete facts Pathos might have learned about the other person involved OR any significant information Pathos revealed about himself. "
            "Output ONLY a valid JSON object with three keys: 'summary' (string), 'new_facts_learned_by_pathos' (list of strings), and 'key_info_revealed_by_pathos' (list of strings). "
            "If no new facts were learned or no key info revealed, use an empty list for the respective key. Ensure the output is a single, valid JSON object and nothing else."
        )
        summary_user_prompt = f"Dialogue Transcript:\n{transcript_str}"
        summary_messages = [{"role": "system", "content": summary_system_prompt}, {"role": "user", "content": summary_user_prompt}]

        summary_result_str = await self._call_llm_api(summary_messages, dialogue_summary_role, max_tokens_override=250, temperature_override=0.3)

        summary_data = {"summary": "Pathos had a brief interaction.", "new_facts_learned_by_pathos": [], "key_info_revealed_by_pathos": []}
        if summary_result_str:
            try:
                clean_summary_str = summary_result_str
                # Find the start and end of the JSON object if it's embedded
                json_start = clean_summary_str.find('{')
                json_end = clean_summary_str.rfind('}')
                if json_start != -1 and json_end != -1 and json_end > json_start:
                    clean_summary_str = clean_summary_str[json_start : json_end+1]

                parsed_summary = json.loads(clean_summary_str)
                summary_data["summary"] = parsed_summary.get("summary", summary_data["summary"])

                facts_learned = parsed_summary.get("new_facts_learned_by_pathos", [])
                summary_data["new_facts_learned_by_pathos"] = [str(f) for f in facts_learned if isinstance(f, (str, int, float))] if isinstance(facts_learned, list) else []

                info_revealed = parsed_summary.get("key_info_revealed_by_pathos", [])
                summary_data["key_info_revealed_by_pathos"] = [str(i) for i in info_revealed if isinstance(i, (str, int, float))] if isinstance(info_revealed, list) else []

            except json.JSONDecodeError:
                logger.warning(f"Failed to parse dialogue summary JSON from LLM. Raw: '{summary_result_str}'. Using transcript snippet as fallback summary.")
                summary_data["summary"] = ("Pathos interacted with " + npc_profile.name + ". " + transcript_str[:150] + ("..." if len(transcript_str) > 150 else "")).strip()
            except Exception as e_parse:
                 logger.error(f"Unexpected error parsing dialogue summary JSON: {e_parse}. Raw: '{summary_result_str}'", exc_info=True)
                 summary_data["summary"] = ("Pathos interacted with " + npc_profile.name + ". " + transcript_str[:150] + ("..." if len(transcript_str) > 150 else "")).strip()
        else:
            logger.warning("Dialogue summary LLM call returned no result. Using transcript snippet as fallback summary.")
            summary_data["summary"] = ("Pathos interacted with " + npc_profile.name + ". " + transcript_str[:150] + ("..." if len(transcript_str) > 150 else "")).strip()


        logger.info(f"FirmamentModule: NPC dialogue simulation complete with {npc_profile.name}. Summary: {summary_data['summary']}")
        return {"transcript": full_transcript, **summary_data} # Spread summary_data keys into the return

    def _is_npc_interaction_warranted(self, activity_slot: Optional[ActivitySlot], intention: Optional[str]) -> bool:
        if not self.fm_config.get("enable_firmament"): return False
        cooldown_seconds = self.fm_config.get("npc_interaction_cooldown_seconds", 1800)
        current_time = time.time()
        if (current_time - self.last_npc_interaction_time) < cooldown_seconds:
            logger.debug("FirmamentModule: NPC interaction opportunity, but cooldown active.")
            return False
        location_keywords = ["cafe", "shop", "store", "reception", "counter", "market", "bar ", "restaurant"]
        activity_keywords = ["meeting", "appointment", "errand", "social", "ordering", "buying", "check out", "service"]
        intention_keywords = ["ask ", "talk to", "order from", "buy from", "meet with", "speak to", "get help from"]
        if activity_slot:
            loc_lower = (activity_slot.activity_details.location_context or "").lower()
            if any(keyword in loc_lower for keyword in location_keywords):
                logger.debug(f"NPC interaction warranted by location: {loc_lower}"); return True
            act_text = f"{(activity_slot.slot_name or '').lower()} {(activity_slot.activity_title or '').lower()} {(activity_slot.activity_type or '').lower()}"
            if any(keyword in act_text for keyword in activity_keywords):
                logger.debug(f"NPC interaction warranted by activity: {act_text}"); return True
        if intention:
            if any(keyword in intention.lower() for keyword in intention_keywords):
                logger.debug(f"NPC interaction warranted by intention: {intention.lower()}"); return True
        return False

    def _determine_generic_npc_profile_for_context(self, context_slot: Optional[ActivitySlot], context_intention: Optional[str]) -> Optional[NPCProfile]:
        '''
        Determines a generic NPC role and profile based on the current activity or intention context.
        This version does not call an LLM.
        '''
        npc_role_name = "person" # Default
        interaction_description = "a general interaction"

        # Try to determine role from activity slot
        if context_slot:
            loc = (context_slot.activity_details.location_context or "").lower()
            act_title = (context_slot.activity_title or "").lower()
            # More specific roles based on keywords
            if "cafe" in loc or "coffee" in act_title: npc_role_name = "barista"; interaction_description = "ordering or being at a cafe"
            elif "shop" in loc or "store" in loc or "market" in loc : npc_role_name = "shopkeeper"; interaction_description = "shopping or browsing"
            elif "reception" in loc or "front desk" in loc : npc_role_name = "receptionist"; interaction_description = "an inquiry at a reception"
            elif "library" in loc: npc_role_name = "librarian"; interaction_description = "being at the library"
            elif "restaurant" in loc or "diner" in loc: npc_role_name = "waiter"; interaction_description = "dining at a restaurant"
            elif "bar" in loc or "pub" in loc: npc_role_name = "bartender"; interaction_description = "at a bar"
            elif "meeting" in act_title: npc_role_name = "colleague" if "client" not in act_title else "client contact"; interaction_description = f"a brief exchange during a {act_title}"
            elif "social" in (context_slot.activity_type or "").lower(): npc_role_name = "acquaintance"; interaction_description = "a casual social exchange"
            # Add more role detection logic as needed

        # Try to determine/refine role from intention if context_slot didn't yield a specific role or to refine it
        if context_intention:
            intention_lower = context_intention.lower()
            if "ask" in intention_lower and "librarian" in intention_lower: npc_role_name = "librarian"
            elif "order" in intention_lower and ("food" in intention_lower or "drink" in intention_lower or "coffee" in intention_lower):
                npc_role_name = "barista" if "coffee" in intention_lower else "waiter"
            elif "buy" in intention_lower: npc_role_name = "shopkeeper"
            elif "talk to doctor" in intention_lower or "see nurse" in intention_lower : npc_role_name = "medical staff"
            # If intention exists, it often gives a better interaction_description
            interaction_description = f"acting on intention: {context_intention}"

        if npc_role_name == "person" and not context_intention: # If still default and no clear intention
            logger.debug("Could not determine a sufficiently specific NPC role for context, skipping generic profile creation.")
            return None # Avoid overly generic interactions unless intention provides specific context

        npc_profile_name_for_prompt = npc_role_name.replace("_", " ").title()
        npc_role_description_for_prompt = f"a {npc_role_name.replace('_', ' ')}" # Simpler description

        generic_persona_prompt = (
            f"You are {npc_profile_name_for_prompt}, {npc_role_description_for_prompt}. "
            f"You are currently interacting with Pathos regarding: {interaction_description}. "
            "Respond briefly and naturally in character, fitting the situation."
        )

        # from eidos_agent.persona_logic.social_graph.models import NPCProfile # Ensure imported
        return NPCProfile(
            name=npc_profile_name_for_prompt, # Use the determined role as a name for simplicity
            role_description=npc_role_description_for_prompt,
            persona_summary_prompt=generic_persona_prompt
            # npc_id will be auto-generated by Pydantic if not provided
        )

    async def get_availability_status(self) -> str:
        if not self.fm_config.get("enable_firmament", False):
            logger.info("FirmamentModule disabled. Reporting UNKNOWN availability.")
            return AVAILABILITY_STATUS_UNKNOWN
        activity_slot = await self._get_current_activity_slot()
        if not activity_slot:
            logger.info("FirmamentModule: No current activity slot. Reporting AVAILABLE.")
            return AVAILABILITY_STATUS_AVAILABLE
        # ... (rest of availability logic from P3 Step 10) ...
        activity_type_lower = (activity_slot.activity_type or "").lower()
        slot_name_lower = (activity_slot.slot_name or "").lower()
        activity_title_lower = (activity_slot.activity_title or "").lower()
        if "meeting" in slot_name_lower or "client call" in slot_name_lower or "consulting" in activity_title_lower:
            return AVAILABILITY_STATUS_BUSY_MEETING
        if "deep work" in slot_name_lower or "focus session" in slot_name_lower:
            return AVAILABILITY_STATUS_BUSY_DEEP_WORK
        if "work" in activity_type_lower or "writing" in slot_name_lower or "admin" in slot_name_lower:
            return AVAILABILITY_STATUS_BUSY_GENERAL_WORK
        if "leisure" in activity_type_lower or "break" in activity_type_lower or "reading" in slot_name_lower or "coffee" in slot_name_lower:
            return AVAILABILITY_STATUS_LIGHT_ACTIVITY
        if "reflective" in activity_type_lower or "planning" in activity_type_lower:
            return AVAILABILITY_STATUS_LIGHT_ACTIVITY
        return AVAILABILITY_STATUS_AVAILABLE

# End of FirmamentModule class
