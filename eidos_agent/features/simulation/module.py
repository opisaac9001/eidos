"""
Handles the logic for Pathos to simulate interactions with NPCs.
Manages the state of active simulations and interfaces with the NPC LLM.
"""
from typing import Optional, Dict, Any, List
import httpx
import json
import logging # Standard logging
from eidos_agent.core.config import Config # Assuming Config is accessible

# Use standard logging for this module as it's more of a utility/service
logger = logging.getLogger(__name__)

# In-memory store for active simulation state
_active_simulation_state: Optional[Dict[str, Any]] = None
NPC_LLM_ROLE = "LOGOS_TECHNE" # As per roadmap for MVP

# Path to the NPC system prompt template - This needs to be correct
# The roadmap specified: "c:\\Users\\Isaac\\Desktop\\Eidos\\eidos_project\\maybe\\eidos_agent\\system_prompts\\npc_simulation_prompt_template.txt"
# For portability, let's make this relative to the project root if possible, or ensure it's configurable.
# For now, I'll use the hardcoded path from the roadmap, but this is a point for future improvement.
NPC_PROMPT_TEMPLATE_PATH = Config.get_nested_value(Config.ONEIROS, ['npc_prompt_template_path'], "system_prompts/npc_simulation_prompt_template.txt")
# If NPC_PROMPT_TEMPLATE_PATH is intended to be relative to PROJECT_ROOT:
# from eidos_agent.core.config import PROJECT_ROOT
# NPC_PROMPT_TEMPLATE_PATH_ABS = PROJECT_ROOT / NPC_PROMPT_TEMPLATE_PATH


def _load_npc_prompt_template() -> str:
    """Loads the NPC prompt template from file."""
    # Determine absolute path if relative
    from eidos_agent.core.config import PROJECT_ROOT # Local import for clarity
    
    # Check if NPC_PROMPT_TEMPLATE_PATH is already absolute
    path_to_load = Path(NPC_PROMPT_TEMPLATE_PATH)
    if not path_to_load.is_absolute():
        path_to_load = PROJECT_ROOT / NPC_PROMPT_TEMPLATE_PATH

    try:
        if not path_to_load.exists():
            logger.error(f"NPC prompt template not found at {path_to_load}. Please check path: {NPC_PROMPT_TEMPLATE_PATH}")
            return "ERROR: NPC prompt template file not found. Cannot initiate simulation."
        with open(path_to_load, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"NPC prompt template not found at {path_to_load} (FileNotFoundError). Path was: {NPC_PROMPT_TEMPLATE_PATH}")
        return "ERROR: NPC prompt template file not found. Cannot initiate simulation."
    except Exception as e:
        logger.error(f"Error loading NPC prompt template from {path_to_load}: {e}", exc_info=True)
        return f"ERROR: Could not load NPC prompt template due to: {e}"


async def _call_npc_llm(messages: List[Dict[str, Any]]) -> Optional[str]:
    """
    Calls the NPC LLM with the provided messages and returns the response content.
    Uses the configured LLM for NPC_LLM_ROLE.
    """
    llm_config = Config.get_llm_config(NPC_LLM_ROLE)
    if not llm_config or not llm_config.get('url'):
        logger.error(f"NPC LLM call failed: No configuration found for role '{NPC_LLM_ROLE}' or URL missing.")
        return f"[NPC LLM configuration for '{NPC_LLM_ROLE}' not found or URL missing]"

    api_url = f"{llm_config['url'].rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    api_key = llm_config.get('api_key')
    if api_key and api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']:
        headers["Authorization"] = f"Bearer {api_key}"

    try: max_tokens_val = int(llm_config.get('max_tokens', 512))
    except (ValueError, TypeError): max_tokens_val = 512
    
    payload = {
        "model": llm_config.get('model'),
        "messages": messages,
        "temperature": llm_config.get('temperature', 0.7),
        "max_tokens": max_tokens_val
    }
    for param in ['top_p', 'presence_penalty', 'frequency_penalty']:
        if param_val := llm_config.get(param): payload[param] = param_val
    if not payload.get('model'):
        logger.warning(f"NPC LLM call for role '{NPC_LLM_ROLE}' has no model specified. Provider might use default.")
        if 'model' in payload: del payload['model']

    llm_name_for_log = llm_config.get('model', f'NPC LLM ({NPC_LLM_ROLE})')
    logger.debug(f"Calling NPC LLM '{llm_name_for_log}' at {api_url} with {len(messages)} messages.")

    try:
        timeout_seconds = float(llm_config.get('timeout', 10.0))  # Reduced from 60.0 to 10.0 for faster startup
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            result_json = response.json()
            if choices := result_json.get("choices"):
                if choices and isinstance(choices, list) and len(choices) > 0:
                    if message_data := choices[0].get("message"):
                        if content := message_data.get("content"):
                            if isinstance(content, str): return content.strip()
            logger.warning(f"Unexpected NPC LLM response format from '{llm_name_for_log}': {result_json}")
            return f"[Received unexpected response format from NPC LLM '{llm_name_for_log}']"
    except httpx.TimeoutException: logger.error(f"NPC LLM '{llm_name_for_log}' request timed out"); return f"[NPC LLM '{llm_name_for_log}' request timed out]"
    except httpx.HTTPStatusError as e: logger.error(f"NPC LLM '{llm_name_for_log}' API error ({e.response.status_code}): {e.response.text[:500]}"); return f"[NPC LLM '{llm_name_for_log}' API error ({e.response.status_code})]"
    except Exception as e: logger.error(f"Unexpected error calling NPC LLM '{llm_name_for_log}': {e}", exc_info=True); return f"[Unexpected error calling NPC LLM '{llm_name_for_log}': {str(e)}]"

async def initiate_simulated_interaction(
    npc_name: Optional[str], npc_role: str, npc_description: str,
    initial_context: str, pathos_opening_statement: str
) -> Dict[str, Any]:
    global _active_simulation_state
    if _active_simulation_state is not None:
        return {"error": "Another simulation is already active. Please end it before starting a new one."}

    template = _load_npc_prompt_template()
    if template.startswith("ERROR:"): return {"error": template}

    npc_system_prompt = template.format(
        NPC_NAME=npc_name if npc_name else "N/A", NPC_ROLE=npc_role,
        NPC_DESCRIPTION=npc_description, INITIAL_CONTEXT=initial_context,
        PATHOS_OPENING_STATEMENT=pathos_opening_statement
    )
    _active_simulation_state = {
        "npc_system_prompt": npc_system_prompt, "npc_name": npc_name, "npc_role": npc_role,
        "npc_description": npc_description, "initial_context": initial_context,
        "conversation_history": [{"role": "user", "content": pathos_opening_statement}]
    }
    npc_llm_messages = [{"role": "system", "content": npc_system_prompt}, {"role": "user", "content": pathos_opening_statement}]
    npc_response_content = await _call_npc_llm(npc_llm_messages)
    if not npc_response_content or npc_response_content.startswith("["):
        npc_response_content = f"Ah, Pathos, you said '{pathos_opening_statement}'. Interesting. I am {npc_name if npc_name else 'a ' + npc_role}. How can I help you with {initial_context}?"
        logger.warning(f"NPC LLM call failed for initiation, using fallback. Original LLM response: {npc_response_content if npc_response_content else 'None'}")
    
    _active_simulation_state["conversation_history"].append({"role": "assistant", "content": npc_response_content})
    logger.info(f"Simulation initiated. NPC first response: '{npc_response_content[:100]}...'")
    return {"npc_response": npc_response_content}

async def send_message_to_simulated_npc(message_to_npc: str) -> Dict[str, Any]:
    global _active_simulation_state
    if _active_simulation_state is None: return {"error": "No active simulation."}
    _active_simulation_state["conversation_history"].append({"role": "user", "content": message_to_npc})
    npc_llm_messages = [{"role": "system", "content": _active_simulation_state["npc_system_prompt"]}] + _active_simulation_state["conversation_history"]
    npc_response_content = await _call_npc_llm(npc_llm_messages)
    if not npc_response_content or npc_response_content.startswith("["):
        npc_response_content = f"That's an interesting point, Pathos, about '{message_to_npc}'. I'll have to think on that."
        logger.warning(f"NPC LLM call failed for send_message, using fallback. Original LLM response: {npc_response_content if npc_response_content else 'None'}")
    _active_simulation_state["conversation_history"].append({"role": "assistant", "content": npc_response_content})
    logger.info(f"NPC response in active simulation: '{npc_response_content[:100]}...'")
    return {"npc_response": npc_response_content}

async def end_simulated_interaction() -> Dict[str, str]:
    global _active_simulation_state
    if _active_simulation_state is None: return {"error": "No active simulation to end."}
    _active_simulation_state = None
    logger.info("Simulated interaction ended.")
    return {"status": "Simulation ended successfully."}