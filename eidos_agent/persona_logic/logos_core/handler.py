import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable

from eidos_agent.core.config import Config
from eidos_agent.persona_logic.ethos_core.core import EthosCore
from eidos_agent.llm_integrations.llm_client import LLMClient
# For OpenWeatherMapService, WebSearchService, BookshelfHandler - assuming they might be needed by other tools
# For now, only FirmamentModule is strictly needed for the new tool
# from eidos_agent.services.openweathermap import OpenWeatherMapService
# from eidos_agent.services.web_search import WebSearchService
# from eidos_agent.features.bookshelf.bookshelf_handler import BookshelfHandler

# Import FirmamentModule for NPC interaction
from eidos_agent.features.firmament.module import FirmamentModule

# Schemas for tool call and result
from eidos_agent.schemas.llm_schemas import LLMToolCall
from eidos_agent.schemas.tool_schemas import ToolResult

from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

# Type alias for tool execution functions
ToolExecutor = Callable[..., Awaitable[Dict[str, Any]]]

class LogosCore:
    def __init__(self,
                 config: Config,
                 ethos_core: EthosCore,
                 llm_client: LLMClient, # Standard LLM client for any internal needs
                 # http_client_manager: Any, # For services like WebSearch, OWM that make non-LLM HTTP calls
                 # owm_service: Optional[OpenWeatherMapService] = None,
                 # bookshelf_handler: Optional[BookshelfHandler] = None,
                 firmament_module: Optional[FirmamentModule] = None # Added FirmamentModule
                 ):
        self.config = config
        self.ethos_core = ethos_core
        self.llm_client = llm_client
        # self.http_client_manager = http_client_manager
        # self.owm_service = owm_service
        # self.bookshelf_handler = bookshelf_handler
        self.firmament_module = firmament_module

        # Simplified TOOL_DISPATCH_MAP for now
        self.TOOL_DISPATCH_MAP: Dict[str, ToolExecutor] = {
            "interact_with_npc": self.execute_interact_with_npc,
            # Other tools would be registered here
        }
        logger.info("LogosCore initialized (skeletal).")

    def set_firmament_module(self, firmament_module_instance: FirmamentModule): # Added setter
        """Sets the FirmamentModule instance after LogosCore initialization."""
        self.firmament_module = firmament_module_instance
        logger.info(f"LogosCore: FirmamentModule instance set. Available: {self.firmament_module is not None}")

    async def execute_tools(self, tool_calls: List[LLMToolCall], user_id_context: Optional[str]) -> List[ToolResult]:
        """
        Executes a list of tool calls requested by the LLM.
        """
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments

                if tool_name in self.TOOL_DISPATCH_MAP:
                    executor = self.TOOL_DISPATCH_MAP[tool_name]
                    # Pass user_id_context if the specific tool executor accepts it
                    # This requires checking the signature or using inspect, or a convention.
                    # For now, let's assume execute_interact_with_npc will take it.
                    if tool_name == "interact_with_npc":
                         execution_result_dict = await executor(user_id_context=user_id_context, **arguments)
                    else:
                         execution_result_dict = await executor(**arguments) # Other tools might not need user_id_context

                    if execution_result_dict.get("success", False):
                        results.append(ToolResult(
                            tool_call_id=tool_call.id,
                            tool_name=tool_name,
                            status="success",
                            result_payload=execution_result_dict.get("data"),
                            # result_summary_for_llm=execution_result_dict.get("summary_for_llm") # Optional
                        ))
                    else:
                        results.append(ToolResult(
                            tool_call_id=tool_call.id,
                            tool_name=tool_name,
                            status="error",
                            error_details=execution_result_dict.get("error", "Tool execution failed.")
                        ))
                else:
                    logger.warning(f"Tool '{tool_name}' not found in dispatch map.")
                    results.append(ToolResult(
                        tool_call_id=tool_call.id,
                        tool_name=tool_name,
                        status="error",
                        error_details=f"Tool '{tool_name}' not implemented or recognized."
                    ))
            except json.JSONDecodeError as e_json:
                logger.error(f"Failed to parse arguments for tool '{tool_name}': {e_json}. Arguments: {tool_call.function.arguments}")
                results.append(ToolResult(tool_call_id=tool_call.id, tool_name=tool_name, status="error", error_details=f"Invalid arguments format: {e_json}"))
            except Exception as e:
                logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
                results.append(ToolResult(tool_call_id=tool_call.id, tool_name=tool_name, status="error", error_details=str(e)))
        return results

    async def execute_interact_with_npc(self, npc_id: str, utterance: str, conversation_id: Optional[str] = None, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        """
        Allows Pathos to interact with an NPC in the simulation.
        This method calls FirmamentModule to handle the interaction.
        """
        logger.info(f"LogosCore: Executing 'interact_with_npc'. NPC ID: {npc_id}, Utterance: '{utterance[:50]}...', Conv ID: {conversation_id}")
        if not self.firmament_module:
            logger.error("LogosCore: FirmamentModule not available. Cannot execute 'interact_with_npc'.")
            return {"success": False, "error": "Firmament interaction system is not available."}

        try:
            # Call the new method in FirmamentModule
            # User_id_context is Pathos's ID, important for memory logging context
            interaction_result = await self.firmament_module.handle_pathos_dialogue_with_npc(
                npc_id=npc_id,
                pathos_utterance=utterance,
                conversation_id=conversation_id,
                user_id_context=user_id_context
            )

            # interaction_result from FirmamentModule is expected to be a dict like:
            # {"npc_response_text": "...", "npc_id": "...", "npc_name": "...", "conversation_id": "..."}
            # Or include an "error" key if something went wrong at Firmament/NPCController level.

            if "error" in interaction_result:
                 return {"success": False, "error": interaction_result["error"]}

            # The "data" for ToolResult should contain what PathosInterface needs to inform the LLM
            # This is primarily the NPC's response and any updated conversation_id.
            return {
                "success": True,
                "data": {
                    "npc_response": interaction_result.get("npc_response_text"),
                    "npc_id_responded": interaction_result.get("npc_id"), # For confirmation
                    "npc_name_responded": interaction_result.get("npc_name"), # For context
                    "conversation_id": interaction_result.get("conversation_id") # Pass through
                },
                "summary_for_llm": f"NPC {interaction_result.get('npc_name', npc_id)} responded: {interaction_result.get('npc_response_text', '')[:100]}"
            }
        except Exception as e:
            logger.error(f"LogosCore: Exception during 'interact_with_npc' (NPC: {npc_id}): {e}", exc_info=True)
            return {"success": False, "error": f"An unexpected error occurred while interacting with NPC {npc_id}: {str(e)}"}

    async def close(self):
        logger.info("LogosCore closing. (No specific resources to release in this skeletal version)")
        # If services like WebSearchService were initialized, they would be closed here.
        pass

    # Placeholder for other tool execution methods that might have existed
    # async def execute_web_search(self, query: str, user_id_context: Optional[str] = None) -> Dict[str, Any]: ...
    # async def execute_get_weather(self, location: str, user_id_context: Optional[str] = None) -> Dict[str, Any]: ...
    # ... etc.

# Minimal main.py or test setup would need to instantiate LogosCore with its dependencies,
# including the FirmamentModule.
# e.g., logos_core = LogosCore(config, ethos_core, llm_client, firmament_module_instance)
# And PathosInterface would call logos_core.execute_tools(...)
