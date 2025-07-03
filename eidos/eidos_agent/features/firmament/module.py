"""
Defines the FirmamentModule class, which acts as an orchestrator and interface
for the Firmament simulation system within the Eidos agent.
"""
import logging
from typing import TYPE_CHECKING, Optional

from ...core.config import Config
# Assuming simulator functions are in core.simulator
from .core import simulator
# Assuming ChronosAdapter, NPCImproviser might be directly under integrations and npcs respectively
# These paths might need adjustment based on actual file locations if they are deeper.
from ..chronos_adapter import ChronosAdapter # Corrected path
from .npcs.npc_improviser import NPCImproviser
from .npcs.npc_controller import NPCController # Import NPCController
from .npcs.npc_registry import NPCRegistry # Import NPCRegistry to get instance

# Import the global accessor for the plugin manager if needed for start/close
from . import get_plugin_manager, get_http_client_manager

if TYPE_CHECKING:
    from ...persona_logic.ethos_core.core import EthosCore
    from ...llm_integrations.llm_client import LLMClient # For type hinting
    from ....schemas.firmament_schemas import SimulationContext, NPCInteractionInput, NPCInteractionOutput, NPCProfile # Schemas
    from ....schemas.llm_schemas import LLMResponsePayload # For process_pathos_utterance_to_npc
    import uuid # For process_pathos_utterance_to_npc if creating default NPCProfile
    from typing import List # For List[NPCProfile] type hint in get_current_simulation_context

logger = logging.getLogger(__name__)

class FirmamentModule:
    """
    Orchestrates the Firmament simulation, managing its lifecycle and dependencies.
    """
    def __init__(self,
                 config: Config,
                 ethos_core: 'EthosCore',
                 chronos_adapter: ChronosAdapter,
                 npc_improviser: NPCImproviser,
                 llm_client: 'LLMClient'): # Added llm_client
        """
        Initializes the FirmamentModule.

        Args:
            config: The main application configuration.
            ethos_core: Instance of EthosCore for persona and memory access.
            chronos_adapter: Instance of ChronosAdapter for schedule information.
            npc_improviser: Instance of NPCImproviser for generating NPCs.
            llm_client: Instance of LLMClient for making LLM calls.
        """
        self.config = config
        self.firmament_config = config.get_firmament_module_config()
        self.ethos_core = ethos_core
        self.chronos_adapter = chronos_adapter
        self.npc_improviser = npc_improviser
        self.llm_client = llm_client # Store llm_client
        self.npc_registry = NPCRegistry.instance() # Get NPCRegistry instance

        logger.info("FirmamentModule initializing...")

        # Instantiate NPCController
        self.npc_controller = NPCController(
            firmament_module=self,
            npc_registry=self.npc_registry,
            npc_improviser=self.npc_improviser,
            ethos_core=self.ethos_core,
            llm_client=self.llm_client
        )
        logger.info("NPCController instantiated in FirmamentModule.")

        # Wire up dependencies for the simulator functions
        simulator.set_ethos_core_for_simulator(self.ethos_core)
        simulator.set_chronos_adapter_for_simulator(self.chronos_adapter)
        simulator.set_npc_improviser_for_simulator(self.npc_improviser)
        # No direct setter for NPCController in simulator.py in current plan;
        # simulator calls FirmamentModule if it needs controller actions, or FM calls controller.
        # Let's assume simulator's interaction opportunity assessment will now be handled by FirmamentModule itself
        # after simulator.run_simulation_tick, or simulator directly calls NPCController if set.
        # Plan step 3 for simulator.py mentioned simulator calling NPCController.
        # So, we need a setter for NPCController in simulator.py.
        # For now, assuming simulator.py will be updated to have set_npc_controller.
        if hasattr(simulator, 'set_npc_controller_for_simulator'): # Check if setter exists
            simulator.set_npc_controller_for_simulator(self.npc_controller)
            logger.info("NPCController injected into simulator.")
        else:
            logger.warning("NPCController setter not found in simulator.py. Interaction opportunities might not be processed by NPCController via simulator.")


        logger.info("FirmamentModule initialized and dependencies injected into simulator.")

    async def get_current_simulation_context(self, pathos_user_id: str) -> 'SimulationContext': # Added return type hint
        """
        Provides the current situational context for Pathos from the simulation.
        pathos_user_id is provided to ensure context is Pathos-centric (though Firmament primarily knows about Pathos via Chronos).
        """
        logger.debug(f"FirmamentModule: Getting current simulation context for Pathos (User ID: {pathos_user_id}).")

        # 1. Get current activity/location from ChronosAdapter
        # ChronosAdapter.get_current_block() returns a dict like:
        # {"id": "...", "name": "...", "type": "...", "description": "...", "location_hint": "..."}
        current_block = await self.chronos_adapter.get_current_block() # This is Pathos's current block

        location_name = "Unknown Location"
        location_description = None
        current_event_or_activity = "Idle"
        time_of_day_in_simulation = None # Chronos block doesn't directly give this, Firmament might infer or it comes from EthosCore

        if current_block and isinstance(current_block, dict):
            location_name = current_block.get("location_hint") or current_block.get("name", location_name)
            location_description = current_block.get("description") # Or a specific location description from Firmament's world state
            current_event_or_activity = current_block.get("name", current_event_or_activity)
            # time_of_day_in_simulation could be derived from the block's timing if available, or a general world state.
            # For now, let's assume it's part of general world state or not explicitly set here.

        logger.debug(f"FirmamentModule: Current block for Pathos: {current_event_or_activity} at {location_name}")

        # 2. Get NPCs at the current location
        present_npcs_profiles: List[NPCProfile] = []
        if location_name != "Unknown Location":
            # Assuming NPCRegistry has a method to get NPCs by location.
            # This method would return list of dicts matching NPCProfile structure or NPCProfile objects.
            # For now, let's assume it returns dicts that can be parsed into NPCProfile.

            # npc_data_list = self.npc_registry.get_npcs_in_location(location_name) # This method needs to exist in NPCRegistry
            # Example placeholder if get_npcs_in_location doesn't exist yet:
            npc_data_list = []
            all_npcs_dict_list = self.npc_registry.get_all_npcs() # Returns List[Dict[str,Any]]
            for npc_dict in all_npcs_dict_list:
                # Simplistic: if an NPC has a "current_location" or "home_location" matching, they are present.
                # A real system would have more dynamic NPC presence logic.
                if npc_dict.get("current_location") == location_name or npc_dict.get("home_location") == location_name:
                    npc_data_list.append(npc_dict)

            for npc_data in npc_data_list:
                try:
                    # Ensure all required fields are present or provide defaults
                    profile = NPCProfile(
                        npc_id=npc_data.get("id", "unknown_npc_id_" + str(uuid.uuid4())[:8]),
                        name=npc_data.get("name", "Unknown NPC"),
                        appearance=npc_data.get("appearance"),
                        role_in_scene=npc_data.get("role"), # Map from 'role' in stored data
                        personality_summary=npc_data.get("personality"), # Map
                        relationship_to_pathos=npc_data.get("relationship_to_pathos"),
                        current_disposition_towards_pathos=npc_data.get("disposition_towards_pathos", "neutral") # Default
                    )
                    present_npcs_profiles.append(profile)
                except Exception as e_npc_parse:
                    logger.warning(f"FirmamentModule: Could not parse NPC data into NPCProfile: {npc_data.get('name')}. Error: {e_npc_parse}")

        logger.debug(f"FirmamentModule: Found {len(present_npcs_profiles)} NPCs at '{location_name}'.")

        # 3. Gather other ambient details (placeholder)
        ambient_details = [f"The general ambiance of {location_name} is currently normal."]
        # This could be expanded with dynamic weather, sounds, etc., from Firmament's world state.

        return SimulationContext(
            location_name=location_name,
            location_description=location_description,
            time_of_day_in_simulation=time_of_day_in_simulation, # Could be enhanced
            current_event_or_activity=current_event_or_activity,
            present_npcs=present_npcs_profiles,
            ambient_details=ambient_details
        )

    async def process_pathos_utterance_to_npc(self, interaction_input: NPCInteractionInput) -> NPCInteractionOutput:
        """
        Handles Pathos speaking to an NPC.
        Updates internal NPC state and generates the NPC's response using an LLM.
        """
        logger.info(f"FirmamentModule: Processing Pathos utterance to NPC ID '{interaction_input.npc_id}': '{interaction_input.pathos_utterance[:50]}...'")

        target_npc_profile_dict = self.npc_registry.get_npc_by_id(interaction_input.npc_id)
        if not target_npc_profile_dict:
            logger.warning(f"FirmamentModule: NPC with ID '{interaction_input.npc_id}' not found in registry.")
            return NPCInteractionOutput(
                npc_id=interaction_input.npc_id,
                npc_response_utterance="[The person you were trying to talk to seems to have vanished.]"
            )

        # For now, let's assume NPC response generation is simple and directly uses an LLM.
        # A more complex system might have an NPCController or specific dialogue manager.

        # Construct prompt for NPC's LLM
        # This would use a specific LLM role for NPC dialogue, e.g., "FIRMAMENT_NPC_DIALOGUE"
        npc_llm_role = self.firmament_config.get("npc_dialogue_llm_role", "FIRMAMENT_PRIMARY") # Configurable role
        npc_llm_config = self.config.get_llm_config(npc_llm_role)

        if not npc_llm_config:
            logger.error(f"FirmamentModule: LLM config for NPC dialogue role '{npc_llm_role}' not found.")
            return NPCInteractionOutput(
                npc_id=interaction_input.npc_id,
                npc_response_utterance="[The person seems lost in thought and doesn't respond.]"
            )

        # TODO: Maintain conversation history with this NPC to provide to the NPC's LLM.
        # This could be stored in Firmament's state or fetched from EthosCore memories involving this NPC.
        # For now, a simplified prompt:
        npc_persona_info = f"You are {target_npc_profile_dict.get('name')}. Your personality: {target_npc_profile_dict.get('personality', 'neutral')}. Your current role: {target_npc_profile_dict.get('role', 'passerby')}."
        # Pathos's current mood could also be fetched from EthosCore to inform NPC's reaction.
        # pathos_mood: MoodState = await self.ethos_core.get_current_mood_state()
        # pathos_mood_desc = f"Pathos seems to be feeling {pathos_mood.name}."

        messages = [
            {"role": "system", "content": f"You are playing the role of an NPC in a simulation. {npc_persona_info} Respond naturally to the following statement from Pathos. Keep your response concise, like a normal turn in a conversation."},
            # {"role": "system", "content": f"Context: {pathos_mood_desc}"}, # Example additional context
            {"role": "user", "content": interaction_input.pathos_utterance}
        ]

        llm_response_payload: LLMResponsePayload = await self.llm_client.call_llm_api(
            llm_config=npc_llm_config,
            messages=messages,
            stream=False
        )

        npc_utterance = "[The person nods quietly but doesn't say much.]" # Default
        if llm_response_payload.success() and llm_response_payload.content:
            npc_utterance = llm_response_payload.content.strip()
            # TODO: Update NPC's internal state in Firmament based on this interaction
            # (e.g., memory of conversation, relationship change with Pathos).
            # This might involve self.npc_registry.update_npc_data(interaction_input.npc_id, new_state_data)
        else:
            logger.warning(f"FirmamentModule: LLM call for NPC '{interaction_input.npc_id}' response failed or no content: {llm_response_payload.error_message}")

        logger.info(f"FirmamentModule: NPC '{interaction_input.npc_id}' responds: '{npc_utterance[:50]}...'")

        # TODO: Determine if simulation context changed significantly due to this interaction.
        # For now, no specific summary.
        updated_simulation_context_summary = None

        return NPCInteractionOutput(
            npc_id=interaction_input.npc_id,
            npc_response_utterance=npc_utterance,
            updated_simulation_context_summary=updated_simulation_context_summary
        )


    async def start(self):
        """
        Performs any necessary startup operations for the Firmament simulation.
        This could include initializing plugins or other subsystems if not handled by __init__.py.
        """
        logger.info("FirmamentModule starting...")
        # The HTTPClientManager's startup is async and should ideally be called.
        # The firmament/__init__.py notes that this should be called by the main application.
        # If we want FirmamentModule to manage it, it could be done here.
        # For now, assuming main app handles HTTPClientManager.startup() as per __init__.py's TODO.

        # Plugin loading is handled by firmament/__init__.py when PluginManager is first created.
        # No specific start action needed for plugins here unless they have their own async start methods
        # that the PluginManager needs to trigger.

        # Example: If plugins had an async_init method managed by PluginManager:
        # plugin_manager = get_plugin_manager()
        # if plugin_manager:
        #     await plugin_manager.initialize_active_plugins_async()
        logger.info("FirmamentModule started.")

    async def run_simulation_tick(self):
        """
        Executes a single tick of the Firmament simulation.
        This is intended to be called periodically by an external loop (e.g., in EthosCore).
        """
        try:
            # logger.debug("FirmamentModule: Executing simulation tick.") # Can be too verbose
            await simulator.run_simulation_tick()
        except Exception as e:
            logger.error(f"Error during Firmament simulation tick: {e}", exc_info=True)

    async def close(self):
        """
        Performs cleanup operations for the Firmament simulation.
        """
        logger.info("FirmamentModule closing...")

        # Shutdown plugins if the plugin manager exists and has such a method
        plugin_manager = get_plugin_manager()
        if plugin_manager and hasattr(plugin_manager, 'shutdown_plugins'):
            try:
                logger.info("Shutting down Firmament plugins...")
                await plugin_manager.shutdown_plugins() # Assuming shutdown_plugins might be async
            except Exception as e:
                logger.error(f"Error shutting down Firmament plugins: {e}", exc_info=True)

        # The HTTPClientManager's shutdown is async and should be called.
        # firmament/__init__.py notes this as a TODO for the main application.
        # If FirmamentModule is responsible:
        # http_client_manager = get_http_client_manager()
        # if http_client_manager:
        #     await http_client_manager.shutdown()

        logger.info("FirmamentModule closed.")

# Example of how Config might provide firmament_module_config
# This would typically be in your eidos_agent/core/config.py
# class Config:
#     # ... other config parts ...
#     def get_firmament_module_config(self) -> Dict[str, Any]:
#         return self.FIRMAMENT # Assuming FIRMAMENT is a dict in Config class or instance
```
