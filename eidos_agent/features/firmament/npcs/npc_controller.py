import logging
from typing import TYPE_CHECKING, Optional, Dict, Any, List

# To avoid circular imports, use TYPE_CHECKING for full module imports
if TYPE_CHECKING:
    from ..module import FirmamentModule # Parent module
    from ....persona_logic.ethos_core.core import EthosCore
    from ....persona_logic.ethos_core.core import EthosCore
    from ....llm_integrations.llm_client import LLMClient
    from .npc_registry import NPCRegistry
    from .npc_improviser import NPCImproviser
    # from ....schemas.interaction_log_schemas import InteractionLog # Not used directly here yet
    from ....persona_logic.chronos_engine.models import ActivityType as ChronosActivityTypeEnum # For activity type checking
    from datetime import datetime, timezone, timedelta # For cooldown
    import random # For random chance
    import uuid # For memory ID

from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

class NPCController:
    def __init__(self,
                 firmament_module: 'FirmamentModule',
                 npc_registry: 'NPCRegistry',
                 npc_improviser: 'NPCImproviser',
                 ethos_core: 'EthosCore',
                 llm_client: 'LLMClient'): # LLMClient might be needed for direct NPC LLM calls if not through improviser
        self.firmament_module = firmament_module # Provides access to config, other parts of Firmament
        self.npc_registry = npc_registry
        self.npc_improviser = npc_improviser
        self.ethos_core = ethos_core
        self.llm_client = llm_client # May or may not be used directly if improviser handles all LLM

        # State for active conversations, e.g., Dict[conversation_id, List[turn_dict]]
        self.active_conversations: Dict[str, List[Dict[str, str]]] = {}
        self.npc_last_initiated_time: Dict[str, datetime] = {} # For cooldown
        # Ensure EthosCore type is available for EthosMemory hint
        if TYPE_CHECKING:
            from ....persona_logic.ethos_core.memory_storage import MemoryEntry as EthosMemory # Or the Pydantic model if preferred

        self.npc_initiation_cooldown_seconds = self.firmament_module.firmament_config.get("npc_initiation_cooldown_seconds", 300) # 5 mins default
        self.npc_initiation_base_chance = self.firmament_module.firmament_config.get("npc_initiation_base_chance", 0.05) # 5% chance per opportunity

        logger.info(f"NPCController initialized. Cooldown: {self.npc_initiation_cooldown_seconds}s, Base Chance: {self.npc_initiation_base_chance}")

    def _format_dialogue_history_for_prompt(self, history_mems: List['EthosMemory'], npc_name: str, pathos_user_id: str, num_turns_to_include: int) -> Optional[str]:
        """
        Formats a list of npc_dialogue_event memories into a string for an LLM prompt.
        Orders from oldest to newest of the selected turns.
        """
        if not history_mems:
            return None

        formatted_turns = []
        # Memories are typically newest first from get_relevant_memories
        # We want the last N exchanges, so we take the first N memories, then reverse for chronological order in prompt.
        selected_mems = history_mems[:num_turns_to_include]

        for mem in reversed(selected_mems): # Iterate from oldest of the selection to newest
            pathos_utterance = mem.metadata.get("pathos_utterance")
            npc_response = mem.metadata.get("npc_response")

            # Determine who spoke first in the memory's content if not using metadata directly
            # This is a fallback if direct metadata fields aren't populated as expected.
            # For now, relying on metadata.
            if pathos_utterance:
                formatted_turns.append(f"Pathos: \"{pathos_utterance}\"")
            if npc_response:
                formatted_turns.append(f"{npc_name}: \"{npc_response}\"")

        if not formatted_turns:
            return None

        return "Previous conversation context with Pathos:\n" + "\n".join(formatted_turns)

    def _is_npc_on_cooldown(self, npc_id: str) -> bool:
        """Checks if the NPC is currently on cooldown for initiating dialogue."""
        if npc_id in self.npc_last_initiated_time:
            time_since_last = datetime.now(timezone.utc) - self.npc_last_initiated_time[npc_id]
            if time_since_last.total_seconds() < self.npc_initiation_cooldown_seconds:
                logger.debug(f"NPC {npc_id} is on initiation cooldown. Time remaining: {self.npc_initiation_cooldown_seconds - time_since_last.total_seconds():.0f}s")
                return True
        return False

    def _update_npc_initiation_cooldown(self, npc_id: str):
        """Updates the last initiation time for the NPC."""
        self.npc_last_initiated_time[npc_id] = datetime.now(timezone.utc)

    def _does_npc_decide_to_initiate(self, npc_profile: Dict[str, Any], current_block_data: Dict[str, Any]) -> bool:
        """Determines if an NPC should initiate dialogue based on various factors."""
        activity_type_str = current_block_data.get('activity_type')

        # Higher chance during social or active leisure in public-like places
        conducive_activity = False
        if activity_type_str == ChronosActivityTypeEnum.SOCIAL.value:
            conducive_activity = True
        elif activity_type_str == ChronosActivityTypeEnum.LEISURE_ACTIVE.value and "park" in current_block_data.get('location_hint', '').lower(): # Example
            conducive_activity = True

        if not conducive_activity:
            # Lower chance for other non-focused activities if desired, or just return False
            if random.random() < (self.npc_initiation_base_chance / 5): # Much lower chance
                 logger.debug(f"NPC {npc_profile.get('name')} considering initiation during non-highly-social activity '{activity_type_str}' (low chance).")
                 # Allow a small chance even for non-ideal activities, but don't make it the norm.
            else:
                return False

        # TODO: Incorporate NPC traits (extroversion, etc.) from npc_profile if available
        # For now, using base random chance
        if random.random() < self.npc_initiation_base_chance:
            logger.info(f"NPC {npc_profile.get('name')} passed random chance to initiate.")
            return True

        logger.debug(f"NPC {npc_profile.get('name')} did not pass random chance to initiate.")
        return False

    async def assess_interaction_opportunity(self,
                                           current_block_data: Dict[str, Any],
                                           active_npcs_in_location: List[Dict[str, Any]]) -> None:
        """
        Called by the simulator when an activity block suggests an NPC interaction.
        For MVP, this might just log the opportunity or create a simple environmental cue for Pathos.
        """
        activity_title = current_block_data.get('activity_title', 'Unknown Activity')
        location = current_block_data.get('location_hint', 'Unknown Location')

        if not active_npcs_in_location:
            logger.debug(f"NPCController: Interaction opportunity during '{activity_title}' at '{location}', but no active NPCs found.")
            return

        # Example: Pick one NPC if multiple are present and hints are not specific
        npc_to_focus_on = None
        specific_npc_hints = current_block_data.get('specific_npc_hints')

        if specific_npc_hints and isinstance(specific_npc_hints, list) and specific_npc_hints:
            # Try to find the hinted NPC among those active in location
            for npc_profile in active_npcs_in_location:
                if npc_profile.get('id') in specific_npc_hints or npc_profile.get('name') in specific_npc_hints:
                    npc_to_focus_on = npc_profile
                    break
            if npc_to_focus_on:
                 logger.info(f"NPCController: Interaction opportunity with hinted NPC '{npc_to_focus_on.get('name')}' during '{activity_title}'.")
            else:
                 logger.warning(f"NPCController: Hinted NPCs {specific_npc_hints} not found in active NPCs at '{location}'.")
                 # Fallback to picking any available NPC if hints not matched
                 npc_to_focus_on = active_npcs_in_location[0] # Simplistic fallback
                 logger.info(f"NPCController: Falling back to interaction opportunity with '{npc_to_focus_on.get('name')}' during '{activity_title}'.")

        elif active_npcs_in_location: # No specific hints, but NPCs are present
            npc_to_focus_on = active_npcs_in_location[0] # Simplistic: pick the first one
            logger.info(f"NPCController: Interaction opportunity with '{npc_to_focus_on.get('name')}' during '{activity_title}'.")

        if npc_to_focus_on:
            # For MVP: Create an environmental cue memory for Pathos
            # This memory will be picked up by PathosInterface when gathering context
            cue_content = f"You notice {npc_to_focus_on.get('name', 'someone')} at {location} during your '{activity_title}'. They seem open to interaction."

            # Safely get PATHOS_USER_ID
            pathos_user_id = getattr(self.ethos_core, 'PATHOS_USER_ID', 'pathos_internal_user')

            memory_data = {
                "type": "environmental_cue", # Or "interaction_prompt"
                "content": cue_content,
                "metadata": {
                    "npc_id": npc_to_focus_on.get('id'),
                    "npc_name": npc_to_focus_on.get('name'),
                    "activity_title": activity_title,
                    "location": location,
                    "user_id": pathos_user_id,
                    "source": "firmament_npc_controller"
                },
                "salience": 0.5 # Moderately salient
            }
            try:
                await self.ethos_core.add_memory_entry(memory_data, user_id_context=pathos_user_id)
                logger.info(f"NPCController: Created environmental cue for Pathos about NPC '{npc_to_focus_on.get('name')}'.")
            except Exception as e:
                logger.error(f"NPCController: Failed to add environmental cue memory: {e}", exc_info=True)

        # (Future) More advanced: Could trigger an NPC to say something first.
        # For that, this method would need to return data that FirmamentModule then passes to PathosInterface,
        # or it directly uses an LLM to generate NPC's first line and logs it.

    async def manage_npc_dialogue_turn(self,
                                     pathos_utterance: str,
                                     npc_id: str,
                                     conversation_id: Optional[str] = None, # For tracking multi-turn context
                                     current_block_data: Optional[Dict[str, Any]] = None # For scene context
                                     ) -> Dict[str, Any]: # Returns dict with npc_response_text and other info
        """
        Manages a single turn of dialogue: Pathos speaks, NPC responds.
        Logs the interaction to EthosCore.
        """
        logger.info(f"NPCController: Managing dialogue turn. Pathos to NPC '{npc_id}': '{pathos_utterance[:50]}...'")

        npc_profile_dict = self.npc_registry.get_npc_by_id(npc_id)
        if not npc_profile_dict:
            logger.warning(f"NPCController: NPC with ID '{npc_id}' not found.")
            return {"npc_response_text": "[The person you were addressing seems to have disappeared.]", "error": "NPC not found"}

        npc_name = npc_profile_dict.get("name", "the NPC")

        # Prepare input for FirmamentModule's NPC response generation
        # This method already exists and uses NPCImproviser or a direct LLM call
        interaction_input_for_fm = {
            "npc_id": npc_id,
            "pathos_utterance": pathos_utterance,
            # We might need to pass more scene_context here if process_pathos_utterance_to_npc needs it
            # e.g., current_block_data.get('location_hint')
        }

        # Call FirmamentModule's method to get NPC response (it handles LLM call)
        # Assuming FirmamentModule has a method like this that returns a simple string or a structured response
        # The existing `self.firmament_module.process_pathos_utterance_to_npc` seems to be the target.
        # It returns an NPCInteractionOutput Pydantic model.

        # For now, let's assume we call a method that returns a simple text response for simplicity here,
        # or we adapt to use the NPCInteractionOutput.
        # The plan was to use `FirmamentModule.process_pathos_utterance_to_npc`.
        # Let's assume that method is adapted or we call it correctly.
        # For this step, we'll mock the direct LLM call part for simplicity or assume
        # FirmamentModule.process_pathos_utterance_to_npc is what we need.

        # Simplified: Directly use NPCImproviser here for now, or route through FirmamentModule
        # For cleaner separation, FirmamentModule should expose the primary interface.
        # Let's assume FirmamentModule.process_pathos_utterance_to_npc is called by LogosCore's tool handler.
        # This NPCController method might be more about managing state around the interaction
        # if `handle_pathos_npc_speech` in FirmamentModule calls this.

        # Let's refine: This method is called by FirmamentModule.handle_pathos_npc_speech
        # It gets Pathos's utterance and needs to orchestrate NPC's response and logging.

        # 1. Get NPC Response (using NPCImproviser for now, this might be refactored to use a dedicated NPC LLM call)

        # Fetch and format dialogue history
        pathos_user_id = getattr(self.ethos_core, 'PATHOS_USER_ID', 'pathos_internal_user')
        formatted_history_str: Optional[str] = None
        try:
            history_mems = await self.ethos_core.get_relevant_memories(
                query=f"dialogue with {npc_name} {npc_id}",
                user_id_context=pathos_user_id,
                allowed_types=["npc_dialogue_event"],
                limit=5 # Fetch a few recent memories to select turns from
            )
            if history_mems:
                formatted_history_str = self._format_dialogue_history_for_prompt(history_mems, npc_name, pathos_user_id, num_turns_to_include=3)
        except Exception as e_hist:
            logger.error(f"Error fetching/formatting dialogue history for NPC {npc_id} in manage_npc_dialogue_turn: {e_hist}", exc_info=True)

        # Scene context for NPC improviser:
        scene_context_for_improviser = {
            "location_description": current_block_data.get('location_hint', 'an unknown place') if current_block_data else 'an unknown place',
            "pathos_mood_state": (await self.ethos_core.get_current_mood_state()).name if self.ethos_core else "neutral",
            "current_activity_name": current_block_data.get('activity_title', 'an ongoing activity') if current_block_data else 'an ongoing activity',
            "time_of_day": datetime.now(timezone.utc).isoformat(),
            # "conversation_history_summary": self._get_conversation_history_summary(conversation_id, last_n=3) # Replaced by direct history injection
        }

        npc_response_text = await self.npc_improviser.generate_npc_dialogue_response(
            npc_profile=npc_profile_dict,
            pathos_utterance=pathos_utterance,
            scene_context=scene_context_for_improviser,
            conversation_history_summary=formatted_history_str # Pass the formatted history
        )

        if not npc_response_text:
            npc_response_text = "[The person seems lost in thought and doesn't respond clearly.]"
            logger.warning(f"NPCImproviser failed to generate response for NPC {npc_id}.")

        # 2. Log interaction to EthosCore
        # Safely get PATHOS_USER_ID
        pathos_user_id = getattr(self.ethos_core, 'PATHOS_USER_ID', 'pathos_internal_user')

        interaction_log_payload = {
            "interaction_id": str(uuid.uuid4()), # New ID for this exchange
            "user_id": pathos_user_id, # Pathos is always one party
            "npc_id": npc_id,
            "npc_name": npc_name,
            "conversation_turns": [
                {"speaker": "PATHOS", "utterance": pathos_utterance},
                {"speaker": npc_name.upper(), "utterance": npc_response_text} # Use NPC name as speaker
            ],
            "timestamp": datetime.now(timezone.utc), # Use current time for log
            "location_hint": current_block_data.get('location_hint') if current_block_data else None,
            "activity_context": current_block_data.get('activity_title') if current_block_data else None,
            # "pathos_mood_at_interaction": await self.ethos_core.get_current_mood_state() # Could be too much for every turn
        }

        # Convert to InteractionLog Pydantic model if EthosCore expects it
        # For now, assuming EthosCore.record_interaction_event can take a dict that maps to its InteractionLog schema
        # This part needs to align with the actual signature of record_interaction_event
        # For simplicity, let's assume we need to create a memory entry directly here.
        memory_data_for_ethos = {
            "type": "npc_dialogue_event",
            "content": f"Pathos to {npc_name}: \"{pathos_utterance}\"\n{npc_name} to Pathos: \"{npc_response_text}\"",
            "metadata": {
                "npc_id": npc_id, "npc_name": npc_name,
                "pathos_utterance": pathos_utterance, "npc_response": npc_response_text,
                "location": current_block_data.get('location_hint') if current_block_data else None,
                "activity_title": current_block_data.get('activity_title') if current_block_data else None,
                "user_id": pathos_user_id, # Logged under Pathos's user_id
                "source": "firmament_npc_interaction"
            },
            "salience": 0.7 # Dialogue is fairly salient
        }
        try:
            await self.ethos_core.add_memory_entry(memory_data_for_ethos, user_id_context=pathos_user_id)
            logger.info(f"Logged NPC dialogue with {npc_name} to EthosCore.")

            # Hexus update logic will be moved to FirmamentModule.handle_pathos_dialogue_with_npc
            # No Hexus update call directly from here anymore.

        except Exception as e: # Catching broader errors during memory logging
            logger.error(f"NPCController: Failed to log NPC dialogue to EthosCore: {e}", exc_info=True)
            # If memory logging fails, we might still want to return the NPC response,
            # or indicate an error in the return dict. For now, it proceeds.

        # Update active conversation history
        if conversation_id:
            if conversation_id not in self.active_conversations:
                self.active_conversations[conversation_id] = []
            self.active_conversations[conversation_id].append({"speaker": "PATHOS", "utterance": pathos_utterance})
            self.active_conversations[conversation_id].append({"speaker": npc_name.upper(), "utterance": npc_response_text})
            # Trim history if it gets too long
            if len(self.active_conversations[conversation_id]) > 10: # Keep last 5 exchanges (10 turns)
                self.active_conversations[conversation_id] = self.active_conversations[conversation_id][-10:]


        return {"npc_response_text": npc_response_text, "npc_id": npc_id, "npc_name": npc_name}

    def _get_conversation_history_summary(self, conversation_id: Optional[str], last_n: int = 3) -> Optional[str]:
        if not conversation_id or conversation_id not in self.active_conversations:
            return None

        history = self.active_conversations[conversation_id]
        relevant_turns = history[-(last_n * 2):] # Get last N exchanges

        summary_lines = []
        for turn in relevant_turns:
            summary_lines.append(f"{turn['speaker']}: {turn['utterance']}")
        return "\n".join(summary_lines) if summary_lines else None

    def end_conversation(self, conversation_id: str):
        if conversation_id in self.active_conversations:
            del self.active_conversations[conversation_id]
            logger.info(f"NPCController: Ended and cleared active conversation ID: {conversation_id}")

    # (Future) Method: async def trigger_ambient_npc_action_or_speech(...)
    # This would be called by simulator if no Pathos action, but NPCs might act.
    # It would use NPCImproviser to generate an action or dialogue for an NPC.
    # The result would need to be fed back to Pathos's main LLM context.
    # For example, an NPC might say something to Pathos, or perform an action Pathos observes.
    # This requires a way to inject this "event" into PathosInterface's context gathering.

    async def generate_npc_initiated_utterance(self,
                                             npc_profile: Dict[str, Any],
                                             scene_context: Dict[str, Any]) -> Optional[str]:
        """
        Generates an opening line an NPC might say to Pathos to initiate a conversation.
        Uses NPCImproviser.
        """
        npc_name = npc_profile.get("name", "An NPC")
        logger.info(f"NPCController: Generating initiated utterance for NPC '{npc_name}'. Scene: {scene_context.get('location_description')}, Pathos activity: {scene_context.get('current_activity_name')}")

        if not self.npc_improviser:
            logger.error(f"NPCController: NPCImproviser not available. Cannot generate initiated utterance for {npc_name}.")
            return None

        # Craft a conceptual "Pathos utterance" that signals the NPC should initiate.
        # The NPCImproviser's prompt needs to be flexible enough to handle this.
        # Option 1: Specific prompt guidance within scene_context for NPCImproviser to generate an opener.
        # Option 2: A specific method in NPCImproviser for initiations.
        # For now, let's adapt the existing generate_npc_dialogue_response by modifying its inputs.

        # We're telling the NPCImproviser that Pathos hasn't said anything yet, but the NPC should speak.
        # The prompt used by NPCImproviser will be key.
        # The `pathos_utterance` here is more of a directive to the NPC's "mind" (the LLM).
        directive_for_npc_llm = f"[You, {npc_name}, decide to initiate a conversation with Pathos. Pathos is currently {scene_context.get('current_activity_name', 'nearby')} at {scene_context.get('location_description', 'this location')}. Pathos's mood seems to be {scene_context.get('pathos_mood_state', 'neutral')}. What do you say to start the conversation? Keep it natural and brief.]"

        try:
            # Fetch brief history for NPC initiation context
            pathos_user_id = getattr(self.ethos_core, 'PATHOS_USER_ID', 'pathos_internal_user')
            brief_history_summary: Optional[str] = None
            npc_id_for_history = npc_profile.get("id")
            if npc_id_for_history:
                try:
                    last_interaction_mems = await self.ethos_core.get_relevant_memories(
                        query=f"last interaction with {npc_name} {npc_id_for_history}",
                        user_id_context=pathos_user_id,
                        allowed_types=["npc_dialogue_event"],
                        limit=1 # Fetch only the very last interaction memory
                    )
                    if last_interaction_mems:
                        # Use num_turns_to_include=1 for a very brief summary
                        brief_history_summary = self._format_dialogue_history_for_prompt(
                            last_interaction_mems, npc_name, pathos_user_id, num_turns_to_include=1
                        )
                        logger.debug(f"Retrieved brief history summary for {npc_name}'s initiation: {brief_history_summary[:100] if brief_history_summary else 'None'}")
                except Exception as e_hist_init:
                    logger.error(f"Error fetching brief history for NPC {npc_id_for_history} initiation: {e_hist_init}", exc_info=True)

            # generate_npc_dialogue_response expects npc_profile, pathos_utterance, scene_context, and now conversation_history_summary
            initiated_utterance = await self.npc_improviser.generate_npc_dialogue_response(
                npc_profile=npc_profile,
                pathos_utterance=directive_for_npc_llm, # This guides the NPC's LLM
                scene_context=scene_context,
                conversation_history_summary=brief_history_summary # Pass the brief history
            )

            if initiated_utterance and initiated_utterance.strip():
                logger.info(f"NPCController: Generated initiated utterance for '{npc_name}': '{initiated_utterance[:75]}...'")
                return initiated_utterance.strip()
            else:
                logger.warning(f"NPCController: NPCImproviser returned empty or None for initiated utterance for '{npc_name}'.")
                return None
        except Exception as e:
            logger.error(f"NPCController: Error generating initiated utterance for '{npc_name}': {e}", exc_info=True)
            return None

```
