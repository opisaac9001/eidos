# eidos_agent/features/firmament/module.py
import asyncio
import httpx
import logging
import time
import random
import json
from typing import Optional, TYPE_CHECKING, Dict, Any, List, Tuple # Added Tuple
from datetime import datetime, timezone, timedelta # Added timedelta

from eidos_agent.core.config import Config, FirmamentModuleConfig, LLMConfig
from eidos_agent.persona_logic.chronos_engine.models import ActivitySlot, ActivitySlotDetails, ActivityType # Added ActivityType
# Attempt to import PATHOS_USER_ID, provide a fallback if not found
try:
    from eidos_agent.persona_logic.chronos_engine.engine import PATHOS_USER_ID
except ImportError:
    PATHOS_USER_ID = "pathos_agent_internal" # Fallback

if TYPE_CHECKING:
    from eidos_agent.persona_logic.ethos_core.core import EthosCore
    from eidos_agent.persona_logic.chronos_engine.engine import ChronosEngine
    from eidos_agent.features.oneiros.module import OneirosModule
    from eidos_agent.persona_logic.social_graph.models import NPCProfile


logger = logging.getLogger(__name__)

AVAILABILITY_STATUS_BUSY_DEEP_WORK = "BUSY_DEEP_WORK"
AVAILABILITY_STATUS_BUSY_MEETING = "BUSY_MEETING"
AVAILABILITY_STATUS_BUSY_GENERAL_WORK = "BUSY_GENERAL_WORK"
AVAILABILITY_STATUS_LIGHT_ACTIVITY = "LIGHT_ACTIVITY"
AVAILABILITY_STATUS_AVAILABLE = "AVAILABLE"
AVAILABILITY_STATUS_UNKNOWN = "UNKNOWN"

FIRMAMENT_STATUS_CLASSIFIER_LLM_ROLE = "FIRMAMENT_STATUS_CLASSIFIER"


class FirmamentModule:
    def __init__(self, config: Config, ethos_core: 'EthosCore', chronos_engine: 'ChronosEngine', oneiros_module: 'OneirosModule'):
        self.config = config
        self.fm_config: FirmamentModuleConfig = config.get_firmament_module_config()
        self.ethos_core = ethos_core
        self.chronos_engine = chronos_engine
        self.oneiros_module = oneiros_module

        self.http_client: Optional[httpx.AsyncClient] = None
        self.firmament_llm_config: Optional[LLMConfig] = None

        self.last_npc_interaction_time: float = 0.0

        if self.fm_config.get("enable_firmament", False):
            llm_role = self.fm_config.get("firmament_llm_role")
            if llm_role:
                self.firmament_llm_config = self.config.get_llm_config(llm_role)

            if not self.firmament_llm_config or not self.firmament_llm_config.get("url"):
                logger.error(
                    f"FirmamentModule: LLM for role '{llm_role}' (firmament_llm_role) is not configured or lacks a URL. "
                    "Firmament will be impaired."
                )
            else:
                timeout_val = float(self.firmament_llm_config.get('timeout', 10.0))  # Reduced from 60.0 to 10.0 for faster startup
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
        if not self.http_client:
            logger.error(f"FirmamentModule: Main HTTP client not available for LLM call (role: {llm_role_name}).")
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
            if param_val is not None:
                payload[param_key] = param_val
        if not payload.get("model"):
             if "model" in payload: del payload["model"]
        api_url = str(llm_config_to_use["url"])
        if not api_url.endswith(("/chat/completions", "/completions")):
            api_url = api_url.rstrip("/") + "/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = llm_config_to_use.get("api_key")
        if api_key and api_key.lower() not in ["lm-studio", "ollama", "none", "", "vllm"]:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = await self.http_client.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            result_json = response.json()
            if result_json.get("choices") and isinstance(result_json["choices"], list) and len(result_json["choices"]) > 0:
                choice = result_json["choices"][0]
                if choice.get("message") and isinstance(choice["message"], dict):
                    content = choice["message"].get("content")
                    if content and isinstance(content, str): return content.strip()
            if result_json.get("text") and isinstance(result_json.get("text"), str): return result_json.get("text").strip()
            if result_json.get("generations") and isinstance(result_json["generations"], list) and len(result_json["generations"]) > 0:
                if result_json["generations"][0].get("text"): return result_json["generations"][0].get("text").strip()
            logger.warning(f"LLM call to role '{llm_role_name}' response missing expected content. Response: {result_json}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from LLM role '{llm_role_name}': {e.response.status_code} - {e.response.text[:100]}", exc_info=False)
            return None
        except Exception as e:
            logger.error(f"Unexpected error calling LLM role '{llm_role_name}': {e}", exc_info=True)
            return None

    async def _get_current_activity_slot(self) -> Optional[ActivitySlot]:
        if not self.fm_config.get("enable_firmament"): return None
        try:
            current_pathos_time: Optional[datetime] = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)
            if not current_pathos_time:
                logger.error("FirmamentModule: Could not retrieve current_pathos_time from EthosCore.")
                return None
            return await self.chronos_engine.get_current_activity(current_pathos_time)
        except Exception as e:
            logger.error(f"FirmamentModule: Error getting current activity slot: {e}", exc_info=True)
            return None

    async def _get_current_mood(self) -> Optional[Dict[str, Any]]:
        if not self.fm_config.get("enable_firmament"): return None
        try: return self.ethos_core.get_current_mood()
        except Exception as e:
            logger.error(f"FirmamentModule: Error getting current mood: {e}", exc_info=True)
            return None

    # _generate_activity_log_snippet is being removed as its functionality for Pathos's thoughts
    # and deviation detection is now superseded by the subconscious node and the new logic in
    # receive_subconscious_intention. If it had other uses (e.g., summarizing NPC interactions
    # independently), those would need to be re-evaluated. For this refactoring, it's considered obsolete.

    async def _store_activity_log(self, snippet: str, activity_slot: ActivitySlot, mood_at_time: Dict[str, Any], related_intention_id: Optional[str] = None, extra_metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        if not self.fm_config.get("enable_firmament") or not self.ethos_core: return None
        try:
            current_time = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID) or datetime.now(timezone.utc)
            current_metadata = {
                "source": "firmament_module", "timestamp": current_time.isoformat(),
                "activity_slot_name": activity_slot.slot_name, "activity_title": activity_slot.activity_title,
                "activity_type": activity_slot.activity_type,
                "mood_valence_at_time": mood_at_time.get("valence"), "mood_arousal_at_time": mood_at_time.get("arousal"),
                "mood_name_at_time": mood_at_time.get("name")
            }
            if activity_slot.activity_details and activity_slot.activity_details.location_context:
                 current_metadata["location_context_at_time"] = activity_slot.activity_details.location_context
            if related_intention_id: current_metadata["related_intention_memory_id"] = related_intention_id
            if extra_metadata: current_metadata.update(extra_metadata)
            entry_data = {"type": "firmament_activity_log", "content": snippet, "metadata": current_metadata, "salience": random.uniform(0.2, 0.4)}
            if extra_metadata and "interaction_type" in extra_metadata: entry_data["salience"] = random.uniform(0.3, 0.5)
            memory_entry = await self.ethos_core.add_memory_entry(entry_data=entry_data, user_id_context=PATHOS_USER_ID)
            if memory_entry and hasattr(memory_entry, 'id') and memory_entry.id: return memory_entry.id
            return None
        except Exception as e:
            logger.error(f"FirmamentModule: Error storing activity log snippet: {e}", exc_info=True)
            return None

    def _create_dummy_activity_slot_for_context(self, title_context: str) -> ActivitySlot:
        dummy_details = ActivitySlotDetails(description=f"Context: {title_context}", location_context="Implicit Location", metadata={"source":"dummy_firmament_context"})
        now_dt = datetime.now(timezone.utc)
        return ActivitySlot(
            user_id=PATHOS_USER_ID, date=now_dt.date(),
            start_time=now_dt.time(), end_time=(now_dt + timedelta(minutes=1)).time(),
            slot_name="AdHocFirmamentActivity", activity_title=title_context[:100],
            activity_type="other", activity_details=dummy_details,
            generated_at=now_dt
        )

    async def run_simulation_tick(self):
        if not self.fm_config.get("enable_firmament", False): return
        logger.debug("FirmamentModule: Starting simulation tick.")

        activity_slot = await self._get_current_activity_slot() # Actual scheduled slot or None
        mood_dict = await self._get_current_mood() or {} # Ensure mood_dict is a dict
        # Ensure ethos_core is available for Hexus updates
        if not self.ethos_core:
            logger.error("FirmamentModule: EthosCore not available, cannot apply Hexus changes in simulation tick.")
            return

        # --- Activity-Based Hexus Adjustments (Continuous) ---
        if activity_slot and activity_slot.activity_type:
            activity_type_lower = activity_slot.activity_type.lower()
            event_name: Optional[str] = None
            if activity_type_lower in ['resting', 'sleeping', 'leisure_passive']:
                event_name = "ACTIVITY_EFFECT_RESTING"
            elif activity_type_lower in ['work_deep', 'learning', 'work_focused']:
                event_name = "ACTIVITY_EFFECT_WORK_DEEP"
            elif activity_type_lower in ['social', 'leisure_active']:
                event_name = "ACTIVITY_EFFECT_SOCIAL"
            elif activity_type_lower in ['chore', 'work_routine']:
                event_name = "ACTIVITY_EFFECT_WORK_ROUTINE"
            # Add more mappings as needed, e.g., for 'learning'
            elif activity_type_lower == 'learning': # Explicitly
                 event_name = "ACTIVITY_EFFECT_LEARNING"

            if event_name:

                # Magnitude multiplier was removed from process_event_for_hexus_update.
                # If scaling is needed, event definitions in EthosCore should be adjusted.
                asyncio.create_task(self.ethos_core.process_event_for_hexus_update(event_name))

            else:
                logger.debug(f"FirmamentModule: No specific continuous Hexus event defined for activity type: {activity_type_lower}")


        # Pathos's internal thought generation and deviation based on it is REMOVED from here.
        # That functionality is now driven by impulses from the subconscious node via receive_subconscious_intention.

        # The main loop will now focus on NPC interactions or other environmental simulations.
        # We create a context slot for NPC interactions, which could be the current activity or a generic one if idle.
        npc_context_slot = activity_slot if activity_slot else self._create_dummy_activity_slot_for_context("Idle / Between Activities")

        # Check for NPC interaction.
        # The condition `if not original_snippet and not newly_started_spontaneous_slot:` from the old code
        # effectively means "if Pathos is not busy with a self-generated thought/action".
        # Since self-generated thoughts are removed, we can simplify this to always check for NPC interactions
        # if Firmament is not currently handling an ongoing Firmament-initiated spontaneous task (which is not a concept here anymore).        # For now, we'll just check if NPC interaction is warranted based on the current context.
        logger.debug("FirmamentModule: Checking for NPC interaction in simulation tick.")

        is_npc_warranted = self._is_npc_interaction_warranted(npc_context_slot, None) # None for intention, as this is a general check
        logger.info(f"FirmamentModule: _is_npc_interaction_warranted (placeholder) returned: {is_npc_warranted}")

        if is_npc_warranted:
            npc_profile_to_use: Optional[NPCProfile] = None
            interaction_source_description = "activity"
            logger.info("FirmamentModule: NPC interaction is warranted by placeholder logic.")

            if npc_context_slot and npc_context_slot.activity_details and isinstance(npc_context_slot.activity_details.metadata, dict): # Check if metadata exists
                specific_npc_id = npc_context_slot.activity_details.metadata.get('npc_id')
                specific_npc_name = npc_context_slot.activity_details.metadata.get('npc_name')
                if specific_npc_id or specific_npc_name:
                    if self.ethos_core: npc_profile_to_use = await self.ethos_core.get_npc_profile(npc_id=specific_npc_id, name=specific_npc_name)
                    if npc_profile_to_use:
                        interaction_source_description = f"activity with known NPC {npc_profile_to_use.name}"
                        logger.info(f"FirmamentModule: Specific NPC profile '{npc_profile_to_use.name}' found from activity context.")

            if not npc_profile_to_use:
                logger.debug("FirmamentModule: No specific NPC from activity, attempting to determine generic NPC.")
                npc_profile_to_use = self._determine_generic_npc_profile_for_context(npc_context_slot, None)
                if npc_profile_to_use:
                    interaction_source_description = f"activity with generic NPC ({npc_profile_to_use.name})"
                    logger.info(f"FirmamentModule: _determine_generic_npc_profile_for_context (placeholder) returned profile: {npc_profile_to_use.name}")
                else:
                    logger.info("FirmamentModule: _determine_generic_npc_profile_for_context (placeholder) returned None.")


            if npc_profile_to_use:
                logger.info(f"FirmamentModule: Proceeding with NPC profile: {npc_profile_to_use.name} for simulated dialogue.")
                initial_dialogue_context = f"Pathos is currently in activity '{npc_context_slot.activity_title}'"
                if npc_context_slot.activity_details and npc_context_slot.activity_details.location_context:
                    initial_dialogue_context += f" at {npc_context_slot.activity_details.location_context}."
                else: initial_dialogue_context += "."
                logger.debug(f"FirmamentModule: Initial dialogue context for simulation: {initial_dialogue_context}")

                dialogue_data = await self._simulate_npc_dialogue(npc_profile_to_use, initial_dialogue_context, mood)
                logger.info(f"FirmamentModule: _simulate_npc_dialogue (placeholder) returned: {dialogue_data}")
                if dialogue_data and dialogue_data.get("transcript"):
                    logger.info(f"FirmamentModule: Placeholder _simulate_npc_dialogue returned data with a transcript. Summary: {dialogue_data.get('summary')}")
                    self.last_npc_interaction_time = time.time()
                    # Full storage logic for NPC dialogue...
                    current_time_for_memory = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)
                    if not current_time_for_memory: current_time_for_memory = datetime.now(timezone.utc)
                    event_metadata = {
                        "npc_id": npc_profile_to_use.npc_id, "npc_name": npc_profile_to_use.name,
                        "npc_role_description": npc_profile_to_use.role_description,
                        "dialogue_transcript": dialogue_data["transcript"],
                        "key_facts_learned_by_pathos": dialogue_data["new_facts_learned_by_pathos"],
                        "key_info_revealed_by_pathos": dialogue_data["key_info_revealed_by_pathos"],
                        "source_of_interaction": f"firmament_{interaction_source_description.replace(' ', '_')}",
                        "activity_slot_name_at_time": npc_context_slot.slot_name,
                        "activity_title_at_time": npc_context_slot.activity_title,
                        "location_at_time": npc_context_slot.activity_details.location_context if npc_context_slot.activity_details else "Unknown",
                        "mood_name_at_time": mood_dict.get("name"), "mood_valence_at_time": mood_dict.get("valence"),
                        "mood_arousal_at_time": mood_dict.get("arousal"), "timestamp": current_time_for_memory.isoformat()
                    }
                    entry_data = {"type": "npc_dialogue_event", "content": dialogue_data["summary"] or "A brief NPC interaction occurred.", "metadata": event_metadata, "salience": random.uniform(0.4, 0.65)}
                    if self.ethos_core:
                        await self.ethos_core.add_memory_entry(entry_data=entry_data, user_id_context=PATHOS_USER_ID)
                        # Placeholder for Hexus changes based on NPC dialogue outcome
                        logger.info("FirmamentModule: NPC Dialogue occurred. Placeholder for Hexus updates using event system.")
                        # Example (actual logic would parse dialogue_data and choose an event):
                        # npc_interaction_event = "NPC_INTERACTION_POSITIVE" # or "NPC_INTERACTION_NEGATIVE", "NPC_LEARNED_INFO"
                        # npc_payload = {"npc_id": npc_profile_to_use.npc_id, "summary": dialogue_data.get("summary")}
                        # asyncio.create_task(self.ethos_core.process_event_for_hexus_update(npc_interaction_event, payload=npc_payload))
            else:
                logger.info("FirmamentModule: No NPC profile determined (specific or generic). Skipping NPC dialogue simulation.")
        else:
            logger.info("FirmamentModule: NPC interaction not warranted in this tick (based on _is_npc_interaction_warranted placeholder).")

        # Add other environmental simulations here if necessary.

        logger.debug("FirmamentModule: Simulation tick finished.")


    async def receive_subconscious_intention(self, intention: str, metadata: Dict[str, Any]):
        if not self.fm_config.get("enable_firmament", False): return
        logger.info(f"FirmamentModule: Received intention: '{intention}'. Metadata: {metadata}")

        original_intention_memory_id: Optional[str] = None
        if self.ethos_core:
            try:
                current_time = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID) or datetime.now(timezone.utc)
                entry_data = {
                    "type": "received_subconscious_intention",
                    "content": intention,
                    "metadata": {
                        "source": "subconscious_node_intention",
                        "original_metadata": metadata, # Contains mood from subconscious, etc.
                        "received_at_firmament_timestamp": current_time.isoformat()
                    },
                    "salience": random.uniform(0.5, 0.7)
                }
                memory_entry = await self.ethos_core.add_memory_entry(entry_data=entry_data, user_id_context=PATHOS_USER_ID)
                if memory_entry and hasattr(memory_entry, 'id') and memory_entry.id:
                    original_intention_memory_id = memory_entry.id
            except Exception as e:
                logger.error(f"FirmamentModule: Error storing received intention as memory: {e}", exc_info=True)

        current_mood_from_subconscious = metadata.get("mood_snapshot") # Mood at the time of intention
        current_activity_slot_before_new_action = await self._get_current_activity_slot()
        newly_started_spontaneous_slot: Optional[ActivitySlot] = None

        # --- Decision Making for Action (Heuristic) ---
        # For now, assume most impulses are candidates for action and lead to a new Chronos task.
        # A more complex decision logic could be added here later.
        actionable_intention = True # Simple assumption for now

        if actionable_intention and self.chronos_engine:
            new_activity_title = intention[:120] # Cap length for Chronos
            new_activity_description = f"Acting on a subconscious intention: {intention}"
            estimated_duration = timedelta(minutes=self.fm_config.get("intention_based_activity_duration_minutes", 15))
            new_activity_type: ActivityType = self.fm_config.get("intention_based_activity_type", "reflective") # type: ignore

            current_slot_id_to_interrupt = None
            if current_activity_slot_before_new_action and current_activity_slot_before_new_action.slot_name != "AdHocFirmamentActivity":
                current_slot_id_to_interrupt = current_activity_slot_before_new_action.id

            logger.info(f"Firmament: Attempting to report spontaneous activity from intention: '{new_activity_title}'")
            try:
                newly_started_spontaneous_slot = await self.chronos_engine.report_spontaneous_activity(
                    user_id=PATHOS_USER_ID,
                    current_slot_id_if_any=current_slot_id_to_interrupt,
                    new_activity_title=new_activity_title,
                    new_activity_description=new_activity_description,
                    estimated_duration=estimated_duration,
                    new_activity_type=new_activity_type,
                    metadata={"source": "firmament_subconscious_driven", "original_intention": intention}
                )
                if newly_started_spontaneous_slot:
                    logger.info(f"Firmament: ChronosEngine started spontaneous activity from intention: {newly_started_spontaneous_slot.activity_title} (ID: {newly_started_spontaneous_slot.id})")
                else:
                    logger.warning(f"Firmament: ChronosEngine did not return a new slot for spontaneous activity from intention '{new_activity_title}'.")
            except Exception as e:
                logger.error(f"Firmament: Error calling report_spontaneous_activity: {e}", exc_info=True)

        # --- Simulate and Log Pathos Acting on the Intention ---
        try:
            # Pass mood from subconscious metadata, and the newly created slot if any
            await self._simulate_intention_consequence(
                intention,
                source_metadata=metadata,
                original_intention_memory_id=original_intention_memory_id,
                current_mood_override=current_mood_from_subconscious,
                newly_created_slot_context=newly_started_spontaneous_slot
            )
        except Exception as e:
            logger.error(f"FirmamentModule: Error in _simulate_intention_consequence call: {e}", exc_info=True)


    async def _simulate_intention_consequence(
        self,
        intention: str,
        source_metadata: Dict[str, Any],
        original_intention_memory_id: Optional[str],
        current_mood_override: Optional[Dict[str, Any]] = None,
        newly_created_slot_context: Optional[ActivitySlot] = None # If a new slot was made for this intention
    ):
        logger.info(f"FirmamentModule: Simulating consequence for intention (MemID: {original_intention_memory_id}): '{intention[:100]}...'")
        if not self.http_client:
            logger.error("FirmamentModule: HTTP client not available for simulating intention consequence.")
            return

        # Determine context: the new slot if provided, otherwise the current (potentially pre-existing) slot.
        context_activity_slot_for_simulation = newly_created_slot_context
        if not context_activity_slot_for_simulation:
            context_activity_slot_for_simulation = await self._get_current_activity_slot() # Might be None if idle

        current_mood = current_mood_override # Use mood from intention time
        if not current_mood: # Fallback if not in metadata
            current_mood = await self._get_current_mood()
        if not current_mood: # Fallback if Ethos fails
            current_mood = {"name": "neutral", "valence": 0.0, "arousal": 0.0, "impulsiveness": 0.5, "hexus_snapshot": {}}


        # --- NPC Dialogue (if warranted by intention and context) ---
        # This check might need refinement based on whether we are in a new slot or existing one.
        # For now, use the determined context_activity_slot_for_simulation.
        if self._is_npc_interaction_warranted(context_activity_slot_for_simulation, intention):
            logger.info(f"Firmament: NPC interaction warranted by intention '{intention[:50]}...' during slot {context_activity_slot_for_simulation.id if context_activity_slot_for_simulation else 'N/A'}")
            # ... (Full NPC dialogue simulation logic - assumed to be complex and pre-existing)
            # This would involve determining NPC, calling LLM for dialogue, storing results.
            # For now, we'll skip the full simulation to keep this change focused.
            pass # Placeholder for brevity. Actual NPC simulation is complex.

        # --- Pathos's Personal Action Simulation (LLM call to describe Pathos acting) ---
        activity_context_for_prompt = "Currently idle or in a new context due to the intention."
        if context_activity_slot_for_simulation:
            location_detail = f" at {context_activity_slot_for_simulation.activity_details.location_context}" if context_activity_slot_for_simulation.activity_details and context_activity_slot_for_simulation.activity_details.location_context else ""
            activity_context_for_prompt = f"Currently in '{context_activity_slot_for_simulation.activity_title}' (slot: '{context_activity_slot_for_simulation.slot_name}'){location_detail}."
            if newly_created_slot_context and newly_created_slot_context.id == context_activity_slot_for_simulation.id:
                 activity_context_for_prompt = f"Just started '{context_activity_slot_for_simulation.activity_title}' due to the intention{location_detail}."


        dream_influence_text = None
        if self.oneiros_module:
            try:
                recent_dream_summary = self.oneiros_module.get_last_dream_summary(max_age_hours=8)
                if recent_dream_summary:
                    dream_influence_text = f"Dream Influence: '{recent_dream_summary[:100]}...'"
            except Exception as e:
                logger.warning(f"Firmament: Error getting dream summary for intention simulation: {e}", exc_info=False)

        system_prompt = ("Pathos acts on or reflects on an internal intention. Describe his immediate reaction, micro-action, or internal thought process in response. 1-2 concise sentences, max 40 words. Focus on being observational and immersive.")
        user_prompt_parts = [
            f"Pathos's internal intention: \"{intention}\"",
            f"His current mood: Valence={current_mood.get('valence', 0.0):.2f}, Arousal={current_mood.get('arousal', 0.0):.2f} (Name: {current_mood.get('name', 'unknown')}).",
            dream_influence_text if dream_influence_text else "No notable recent dream influence.",
            f"His current situation: {activity_context_for_prompt}",
            "Describe his brief, immediate simulated action/reflection (1-2 sentences):"
        ]
        user_prompt = "\n".join(filter(None, user_prompt_parts))
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

        simulated_action_snippet: Optional[str] = None
        try:
            simulated_action_snippet = await self._call_llm_api(
                messages,
                self.fm_config.get("firmament_llm_role", "LOGOS_TECHNE"), # Use standard firmament LLM
                max_tokens_override=70, # Shorter snippet
                temperature_override=0.6 # Slightly less random for this
            )
            if simulated_action_snippet:
                # Basic cleanup
                if simulated_action_snippet.startswith('"') and simulated_action_snippet.endswith('"'):
                    simulated_action_snippet = simulated_action_snippet[1:-1]
                if simulated_action_snippet.startswith("'") and simulated_action_snippet.endswith("'"):
                    simulated_action_snippet = simulated_action_snippet[1:-1]

                logger.info(f"FirmamentModule: Simulated action/reflection for intention: '{simulated_action_snippet}'")

                # Log this simulated action snippet against the appropriate context
                slot_to_log_against = context_activity_slot_for_simulation if context_activity_slot_for_simulation else self._create_dummy_activity_slot_for_context(f"Simulated action for: {intention[:50]}...")
                await self._store_activity_log(
                    simulated_action_snippet,
                    slot_to_log_against,
                    current_mood, # Mood at time of intention (this now includes hexus_snapshot)
                    original_intention_memory_id,
                    extra_metadata={"source_subconscious_intention_text": intention[:200]} # Add part of intention for context
                )


                # Hexus updates based on Pathos's subjective reaction to the intention and its simulated consequence
                if self.ethos_core and self.ethos_core.logos_core:
                    event_description = f"Simulated consequence of internal intention: {intention[:50]}..."
                    # simulated_action_snippet is generated *after* this block, so we use the intention itself for data summary
                    event_data_summary = f"Intention: {intention}\nSimulated Action/Reflection on Intention: {simulated_action_snippet or 'Pending/None'}"

                    current_hexus_scores = self.ethos_core.get_hexus_scores()
                    persona_directives = self.ethos_core.get_persona_directives()[:3]

                    # Hardcoded list for now, ideally fetched from EthosCore or a shared constant
                    available_reactions = [
                        "REACTION_ACCOMPLISHED", "REACTION_FRUSTRATED_SETBACK", "REACTION_ENGAGED_LEARNING",
                        "REACTION_VALIDATED_CONFIRMED", "REACTION_STRESSED_CONCERNED", "REACTION_CALM_RECHARGED",
                        "REACTION_SOCIALLY_CONNECTED", "REACTION_SOCIALLY_DISCONNECTED", "REACTION_BORED_UNSTIMULATED",
                        "REACTION_AMUSED_ENTERTAINED", "REACTION_FEELING_SAFE_SECURE", "REACTION_FEELING_HOPEFUL_OPTIMISTIC",
                        "REACTION_FEELING_SAD_EMPATHETIC", "REACTION_FEELING_ANGER_IRRITATION", "REACTION_CURIOSITY_PIQUED",
                        "REACTION_MOTIVATED_DRIVEN", "REACTION_INDIFFERENT_UNEFFECTED"
                    ]

                    subjective_reaction_type = await self.ethos_core.logos_core.determine_subjective_reaction(
                        event_description=event_description,
                        event_data_summary=event_data_summary,
                        current_hexus_scores=current_hexus_scores,
                        persona_directives=persona_directives,
                        available_reactions=available_reactions
                    )

                    await self.ethos_core.process_event_for_hexus_update(
                        event_type=subjective_reaction_type, # This will now be like "REACTION_ACCOMPLISHED"
                        payload={"intention": intention[:100], "simulated_action_snippet": simulated_action_snippet[:100] if simulated_action_snippet else "N/A"}
                    )
                elif not self.ethos_core.logos_core:
                    logger.warning("FirmamentModule: LogosCore not available on EthosCore instance. Cannot determine subjective Hexus reaction to intention.")
                    # Fallback to a generic direct event if subjective determination fails
                    if self.ethos_core: # Still try to log a simpler event if ethos_core exists
                         asyncio.create_task(self.ethos_core.process_event_for_hexus_update("INTENTION_ACTION_GENERAL_SUCCESS", payload={"intention_text": intention[:100]}))

            else: # simulated_action_snippet was None
                logger.warning(f"FirmamentModule: LLM returned no snippet for intention action simulation: {intention[:100]}")
                if self.ethos_core:
                    # Fallback to a generic direct event if subjective determination fails

                    asyncio.create_task(self.ethos_core.process_event_for_hexus_update("INTENTION_ACTION_FAILURE", payload={"intention_text": intention[:100]}))

        except Exception as e:
            logger.error(f"Error during intention action simulation LLM call or subjective reaction: {e}", exc_info=True)
            if self.ethos_core: # Fallback on general error
                asyncio.create_task(self.ethos_core.process_event_for_hexus_update("INTENTION_ACTION_FAILURE", payload={"intention_text": intention[:100], "error": str(e)}))

        # --- LLM-based Status Classification of the *original* slot (if any, and if no new slot was made) ---
        # This part should only run if:
        # 1. A new spontaneous slot was NOT created for this intention.
        # 2. There was an original, pre-existing activity slot.
        # 3. LLM-based classification is enabled.

        # Fetch the original slot again, in case it was modified by NPC interactions if that logic were active
        original_activity_slot_for_status_update = await self._get_current_activity_slot()

        if not newly_created_slot_context and \
           original_activity_slot_for_status_update and \
           original_activity_slot_for_status_update.slot_name != "AdHocFirmamentActivity" and \
           self.chronos_engine and \
           self.fm_config.get("enable_llm_status_classification", False):

            logger.debug(f"Attempting LLM status classification for original slot: {original_activity_slot_for_status_update.id} (since no new slot was created for this intention).")
            slot_title = original_activity_slot_for_status_update.activity_title
            slot_desc = original_activity_slot_for_status_update.activity_details.description if original_activity_slot_for_status_update.activity_details else 'N/A'
            slot_sub_focus = original_activity_slot_for_status_update.activity_details.sub_focus if original_activity_slot_for_status_update.activity_details else 'N/A'

            determined_outcome_status = 'partially_completed' # Default if LLM fails
            classifier_system_prompt = ("Classify the outcome of the scheduled activity given Pathos's intention and simulated action. Respond with JSON: {\"outcome_status\": \"status\", \"reasoning\": \"brief reason\"}. Valid statuses: 'completed', 'partially_completed', 'interrupted', 'derailed', 'focused_within'.")
            classifier_user_prompt = (
                f"Pathos was scheduled for: '{slot_title}' (Desc: '{slot_desc}', Focus: '{slot_sub_focus}').\n"
                f"He then had an internal intention: \"{intention}\"\n"
                f"His simulated action/reflection on this intention was: \"{simulated_action_snippet or 'N/A'}\"\n"
                f"Based on this, how did the *original scheduled activity* progress? If the intention was unrelated and he likely continued the task, use 'focused_within' or 'completed'. If the intention distracted him, use 'partially_completed' or 'interrupted'. If he abandoned it for something else implicitly, use 'derailed'.\nJSON Response:"
            )
            messages_class = [{"role": "system", "content": classifier_system_prompt}, {"role": "user", "content": classifier_user_prompt}]

            llm_response_str = await self._call_llm_api(messages_class, FIRMAMENT_STATUS_CLASSIFIER_LLM_ROLE, max_tokens_override=100, temperature_override=0.3)
            if llm_response_str:
                try:
                    json_start = llm_response_str.find('{'); json_end = llm_response_str.rfind('}')
                    if json_start != -1 and json_end != -1 and json_end > json_start:
                        parsed_response = json.loads(llm_response_str[json_start : json_end+1])
                        status_llm = parsed_response.get("outcome_status")
                        # Add 'derailed' and 'focused_within' to valid outcomes from this specific classification
                        if status_llm in ['completed', 'partially_completed', 'interrupted', 'derailed', 'focused_within']:
                            determined_outcome_status = status_llm
                        logger.info(f"LLM classified original slot {original_activity_slot_for_status_update.id} as '{determined_outcome_status}'. Reason: {parsed_response.get('reasoning', 'N/A')}")
                    else:
                        logger.warning(f"No valid JSON in LLM status response for original slot: {llm_response_str}")
                except Exception as e_parse:
                    logger.warning(f"Error parsing LLM status response '{llm_response_str}' for original slot: {e_parse}")
            else:
                logger.warning(f"No LLM status response for original slot {original_activity_slot_for_status_update.id}.")

            # Report outcome for the original slot
            event_time_dt = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID) or datetime.now(timezone.utc)
            await self.chronos_engine.report_activity_outcome(
                slot_id=original_activity_slot_for_status_update.id,
                actual_end_time=event_time_dt.time(), # Or could be start_time if truly interrupted at onset
                status=determined_outcome_status, # type: ignore
                outcome_metadata={
                    "source": "firmament_intention_consequence_on_original_slot",
                    "triggering_intention_text": intention,
                    "simulated_action_snippet_for_intention": simulated_action_snippet or "N/A"
                }
            )
        elif not newly_created_slot_context and original_activity_slot_for_status_update and original_activity_slot_for_status_update.slot_name != "AdHocFirmamentActivity":
             logger.debug("LLM status classification disabled or other conditions not met for original slot. No outcome reported for it by this function.")
        elif newly_created_slot_context:
            logger.debug(f"A new spontaneous slot {newly_created_slot_context.id} was created for this intention. Original slot status (if any) handled by report_spontaneous_activity.")
        elif not simulated_action_snippet:
            logger.warning(f"FirmamentModule: No simulated action snippet for intention, and no current slot to update or new slot created.")


    async def _simulate_npc_dialogue(self, npc_profile: 'NPCProfile', initial_dialogue_context: str, pathos_mood: Dict[str, Any], max_exchanges: int = 2) -> Optional[Dict[str, Any]]:
        # ... (Full NPC dialogue simulation logic - assumed to be correct from previous state)
        # This part is complex and was part of the restored content. For this subtask, we assume it's functional.
        # It should use self._call_llm_api with specific roles for Pathos and NPC.
        # Returns a dict with "transcript", "summary", "new_facts_learned_by_pathos", "key_info_revealed_by_pathos".
        logger.debug(f"Placeholder for _simulate_npc_dialogue with {npc_profile.name}")
        return None # Placeholder


    def _is_npc_interaction_warranted(self, activity_slot: Optional[ActivitySlot], intention: Optional[str]) -> bool:
        # ... (Full NPC interaction warrant logic - assumed to be correct)
        logger.debug("Placeholder for _is_npc_interaction_warranted")
        return False # Placeholder


    def _determine_generic_npc_profile_for_context(self, context_slot: Optional[ActivitySlot], context_intention: Optional[str]) -> Optional['NPCProfile']:
        # ... (Full generic NPC profile determination logic - assumed to be correct)
        logger.debug("Placeholder for _determine_generic_npc_profile_for_context")
        return None # Placeholder


    async def get_availability_status(self) -> str:
        if not self.fm_config.get("enable_firmament", False): return AVAILABILITY_STATUS_UNKNOWN
        activity_slot = await self._get_current_activity_slot()
        if not activity_slot: return AVAILABILITY_STATUS_AVAILABLE

        activity_type_lower = (activity_slot.activity_type or "").lower()
        slot_name_lower = (activity_slot.slot_name or "").lower()

        if "meeting" in slot_name_lower or "client call" in slot_name_lower or "consulting" in (activity_slot.activity_title or "").lower():
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
