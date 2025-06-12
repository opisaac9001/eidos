"""
Provides a client for making direct HTTP calls to Large Language Model (LLM) services.
"""
import logging
import json
import uuid
import httpx # For async HTTP requests
from typing import Dict, List, Any, Optional, Union, AsyncGenerator

from eidos_agent.core.config import LLMConfig # For type hinting

logger = logging.getLogger(__name__) # Use standard module logger

class LLMClient:
    """
    A client for making direct HTTP calls to LLM services, handling request
    formatting, streaming, and basic error handling.
    """
    def __init__(self, http_client: httpx.AsyncClient):
        """
        Initializes the LLMClient with an existing httpx.AsyncClient.

        Args:
            http_client: An instance of httpx.AsyncClient. It's assumed that
                         the lifecycle of this client (opening/closing) is managed externally.
        """
        self.http_client = http_client
        logger.info("LLMClient initialized.")

    async def call_llm_api(
        self,
        llm_config: LLMConfig,
        messages: List[Dict[str, Any]],
        tools_definition: Optional[List[Dict[str, Any]]] = None,
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
        llm_provider_url_override: Optional[str] = None,
        model_override: Optional[str] = None,
        stream: bool = False
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        """
        Makes a call to the specified LLM API, handling streaming and tool usage.

        Args:
            llm_config: Configuration for the target LLM.
            messages: The list of messages forming the conversation history and prompt.
            tools_definition: Optional list of tool definitions for the LLM.
            temperature_override: Optional temperature override.
            max_tokens_override: Optional max_tokens override.
            llm_provider_url_override: Optional URL override for the LLM provider.
            model_override: Optional model name override.
            stream: Boolean indicating if streaming response is expected.

        Yields:
            Union[str, Dict[str, Any]]: Text chunks if streaming text, or dictionary
                                        chunks for tool calls, errors, or usage data.
        """
        request_id = str(uuid.uuid4())
        logger.debug(f"LLMClient.call_llm_api [{request_id}]: Initiating. Stream: {stream}")

        if not llm_config: # llm_config_to_use renamed to llm_config
            logger.error(f"LLMClient.call_llm_api [{request_id}]: LLM configuration missing.")
            yield {"type": "error_chunk", "payload": "LLM configuration missing."}; return

        api_key = llm_config.get('api_key')
        # Use overrides first, then llm_config, then specific fields for base_url/url
        base_url_from_config = llm_provider_url_override or llm_config.get('base_url') or llm_config.get('url')
        # Use overrides first, then llm_config, then specific fields for model_name/model
        model_name = model_override or llm_config.get('model_name') or llm_config.get('model')

        if not base_url_from_config or not model_name:
            logger.error(f"LLMClient.call_llm_api [{request_id}]: LLM config incomplete. URL: {base_url_from_config}, Model: {model_name}")
            yield {"type": "error_chunk", "payload": "LLM configuration incomplete (URL or model name)."}; return

        request_url = f"{str(base_url_from_config).rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key and api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']: # Added 'vllm'
            headers["Authorization"] = f"Bearer {api_key}"

        payload: Dict[str, Any] = {"model": model_name, "messages": messages, "stream": stream}
        if tools_definition:
            payload["tools"] = tools_definition
            payload["tool_choice"] = "auto" # Or other strategy if needed

        final_temp_val = temperature_override if temperature_override is not None else llm_config.get('temperature')
        if final_temp_val is not None:
            try: payload["temperature"] = float(final_temp_val)
            except (ValueError, TypeError): logger.warning(f"Invalid temperature value '{final_temp_val}', using LLM default.")
        # If no temp is specified anywhere, we let the LLM use its default.

        top_p_val_from_config = llm_config.get('top_p')
        if top_p_val_from_config is not None:
            try: payload["top_p"] = float(top_p_val_from_config)
            except (ValueError, TypeError): logger.warning(f"Invalid top_p value '{top_p_val_from_config}', omitting from payload.")

        final_max_tokens = max_tokens_override if max_tokens_override is not None else llm_config.get('max_tokens')
        if final_max_tokens is not None:
            try: payload["max_tokens"] = int(final_max_tokens)
            except (ValueError, TypeError): logger.warning(f"Invalid max_tokens value '{final_max_tokens}', omitting from payload.")

        logger.debug(f"LLMClient.call_llm_api [{request_id}]: Payload for {request_url} (Model: {model_name}): {json.dumps(payload, indent=2)}")

        try:
            logger.debug(f"LLMClient.call_llm_api [{request_id}]: Attempting stream POST to {request_url}")
            async with self.http_client.stream("POST", request_url, headers=headers, json=payload) as response:
                logger.debug(f"LLMClient.call_llm_api [{request_id}]: Stream opened. Initial status: {response.status_code}")

                if response.status_code == 200:
                    current_tool_call_parts_by_index: Dict[int, Dict[str, Any]] = {}
                    line_count = 0; yielded_any_content = False

                    async for line_bytes in response.aiter_lines():
                        line = line_bytes.strip(); line_count += 1
                        logger.debug(f"LLMClient.call_llm_api [{request_id}]: Raw stream line {line_count}: '{line[:200]}...'")

                        if not line: continue
                        if line.startswith("data: "):
                            line_content = line[len("data: "):].strip()
                            if line_content == "[DONE]":
                                logger.debug(f"LLMClient.call_llm_api [{request_id}]: Stream [DONE] received.")
                                if current_tool_call_parts_by_index: # Yield any fully formed tool calls before breaking
                                    finalized_tools = [tc for tc in current_tool_call_parts_by_index.values() if tc.get("id") and tc.get("function", {}).get("name")]
                                    if finalized_tools: yield {"type": "tool_calls_chunk", "payload": {"role": "assistant", "tool_calls": finalized_tools}}
                                break
                            try:
                                chunk = json.loads(line_content)
                                logger.debug(f"LLMClient.call_llm_api [{request_id}]: Parsed chunk: {json.dumps(chunk, indent=2)}")
                                if not chunk.get("choices"): continue # Skip empty choices if any
                                choice = chunk.get("choices", [{}])[0]; delta = choice.get("delta", {}); finish_reason = choice.get("finish_reason")

                                if content_delta := delta.get("content"):
                                    if content_delta is not None: yield content_delta; yielded_any_content = True

                                if tool_calls_delta := delta.get("tool_calls"):
                                    yielded_any_content = True
                                    for tc_item_delta in tool_calls_delta:
                                        idx = tc_item_delta.get("index", 0) # Index is important for OpenAI style tool streaming
                                        if idx not in current_tool_call_parts_by_index:
                                            # Initialize with ID if available, otherwise it will be set by the first chunk for this index
                                            current_tool_call_parts_by_index[idx] = {"id": tc_item_delta.get("id"), "type": "function", "function": {"name": "", "arguments": ""}}

                                        current_call = current_tool_call_parts_by_index[idx]
                                        if tc_item_delta.get("id") and not current_call.get("id"): # Set ID if not already set
                                            current_call["id"] = tc_item_delta["id"]

                                        if func_delta := tc_item_delta.get("function"):
                                            if name_part := func_delta.get("name"): current_call["function"]["name"] += name_part
                                            if args_part := func_delta.get("arguments"): current_call["function"]["arguments"] += args_part

                                if finish_reason:
                                    logger.debug(f"LLMClient.call_llm_api [{request_id}]: Finish reason: {finish_reason}")
                                    if finish_reason == "tool_calls" and current_tool_call_parts_by_index: # Ensure there are tools to yield
                                        finalized_tools = [tc for tc in current_tool_call_parts_by_index.values() if tc.get("id") and tc.get("function", {}).get("name")]
                                        if finalized_tools: yield {"type": "tool_calls_chunk", "payload": {"role": "assistant", "tool_calls": finalized_tools}}
                                        current_tool_call_parts_by_index = {} # Clear after yielding
                                    if usage_data := chunk.get("usage"): yield {"type": "usage_chunk", "payload": usage_data}
                            except json.JSONDecodeError as e_json: logger.warning(f"LLMClient.call_llm_api [{request_id}]: Stream JSON decode error for line: '{line_content}'. Error: {e_json}")
                        elif line.startswith('{"error":'):
                            try:
                                error_data = json.loads(line); error_msg = error_data.get('error', {}).get('message', 'Unknown stream error object')
                                yield {"type": "error_chunk", "payload": f"LLM Stream Error Object: {error_msg}"}; return
                            except json.JSONDecodeError: yield {"type": "error_chunk", "payload": "Malformed error from LLM stream."}; return
                        else: logger.debug(f"LLMClient.call_llm_api [{request_id}]: Skipping non-SSE line: {line[:100]}")

                    if not yielded_any_content and not current_tool_call_parts_by_index:
                        logger.warning(f"LLMClient.call_llm_api [{request_id}]: Stream finished but no content or tool calls were yielded.")
                else: # Non-200 status
                    error_content_bytes = await response.aread(); error_content_str = str(error_content_bytes, 'utf-8', errors='replace')
                    logger.error(f"LLMClient.call_llm_api [{request_id}]: LLM API Error {response.status_code}: {error_content_str[:500]}")
                    yield {"type": "error_chunk", "payload": f"LLM API Error {response.status_code}: {error_content_str[:200]}"}

        except httpx.ReadTimeout:
            logger.error(f"LLMClient.call_llm_api [{request_id}]: LLM API request to {request_url} timed out.");
            yield {"type": "error_chunk", "payload": "LLM API request timed out."}
        except httpx.RequestError as e_req:
            logger.error(f"LLMClient.call_llm_api [{request_id}]: LLM request error to {request_url}: {str(e_req)}");
            yield {"type": "error_chunk", "payload": f"LLM request error: {str(e_req)}"}
        except Exception as e:
            logger.error(f"LLMClient.call_llm_api [{request_id}]: Unexpected error in LLM call to {request_url}: {str(e)}", exc_info=True);
            yield {"type": "error_chunk", "payload": f"Unexpected error in LLM call: {str(e)}"}

        logger.debug(f"LLMClient.call_llm_api [{request_id}]: Call finished.")
