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
    def __init__(self, http_client_manager: Any): # Use Any for now, will be HTTPClientManager
        """
        Initializes the LLMClient with an HTTPClientManager.

        Args:
            http_client_manager: An instance of HTTPClientManager to obtain a shared httpx.AsyncClient.
        """
        # Delayed import to avoid circular dependency if HTTPClientManager moves to core later
        # and core also imports things from llm_integrations.
        # For now, direct import is fine as per current file locations.
        from eidos_agent.features.firmament.core.http_client_manager import HTTPClientManager

        if not isinstance(http_client_manager, HTTPClientManager):
            raise TypeError("LLMClient must be initialized with an HTTPClientManager instance.")

        self.http_client_manager = http_client_manager
        self.http_client = self.http_client_manager.get_client()
        if not self.http_client:
            logger.error("LLMClient: Failed to get HTTP client from HTTPClientManager during initialization.")
            # Optionally raise an error or allow it to fail later during call_llm_api
            # For now, it will fail in call_llm_api if http_client is None
        logger.info("LLMClient initialized with HTTPClientManager.")

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
    ) -> Union[LLMResponsePayload, AsyncGenerator[Union[str, Dict[str, Any]], None]]:
        """
        Makes a call to the specified LLM API.
        If stream=False, aggregates the response and returns a single LLMResponsePayload.
        If stream=True, yields chunks (text or dicts for tool_calls/errors/usage).

        Args:
            llm_config: Configuration for the target LLM.
            messages: The list of messages forming the conversation history and prompt.
            tools_definition: Optional list of tool definitions for the LLM.
            temperature_override: Optional temperature override.
            max_tokens_override: Optional max_tokens override.
            llm_provider_url_override: Optional URL override for the LLM provider.
            model_override: Optional model name override.
            stream: Boolean indicating if streaming response is expected.

        Returns or Yields:
            If stream=False: LLMResponsePayload object.
            If stream=True: Text chunks (str) or dictionary chunks for tool calls, errors, or usage data.
        """
        request_id = str(uuid.uuid4())
        logger.debug(f"LLMClient.call_llm_api [{request_id}]: Initiating. Stream: {stream}")

        if not self.http_client:
            logger.error(f"LLMClient.call_llm_api [{request_id}]: HTTP client not available.")
            if stream:
                yield {"type": "error_chunk", "payload": "HTTP client not available."}; return
            else:
                return LLMResponsePayload(error_message="HTTP client not available.", status_code=503)

        if not llm_config:
            logger.error(f"LLMClient.call_llm_api [{request_id}]: LLM configuration missing.")
            if stream:
                yield {"type": "error_chunk", "payload": "LLM configuration missing."}; return
            else:
                return LLMResponsePayload(error_message="LLM configuration missing.", status_code=500)

        api_key = llm_config.get('api_key')
        base_url_from_config = llm_provider_url_override or llm_config.get('base_url') or llm_config.get('url')
        model_name = model_override or llm_config.get('model_name') or llm_config.get('model')

        if not base_url_from_config or not model_name:
            err_msg = f"LLM config incomplete. URL: {base_url_from_config}, Model: {model_name}"
            logger.error(f"LLMClient.call_llm_api [{request_id}]: {err_msg}")
            if stream:
                yield {"type": "error_chunk", "payload": err_msg}; return
            else:
                return LLMResponsePayload(error_message=err_msg, status_code=500)

        request_url = f"{str(base_url_from_config).rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key and api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']:
            headers["Authorization"] = f"Bearer {api_key}"

        payload: Dict[str, Any] = {"model": model_name, "messages": messages, "stream": stream}
        if tools_definition:
            payload["tools"] = tools_definition
            payload["tool_choice"] = "auto"

        final_temp_val = temperature_override if temperature_override is not None else llm_config.get('temperature')
        if final_temp_val is not None:
            try: payload["temperature"] = float(final_temp_val)
            except (ValueError, TypeError): logger.warning(f"Invalid temperature value '{final_temp_val}', using LLM default.")

        top_p_val_from_config = llm_config.get('top_p')
        if top_p_val_from_config is not None:
            try: payload["top_p"] = float(top_p_val_from_config)
            except (ValueError, TypeError): logger.warning(f"Invalid top_p value '{top_p_val_from_config}', omitting from payload.")

        final_max_tokens = max_tokens_override if max_tokens_override is not None else llm_config.get('max_tokens')
        if final_max_tokens is not None:
            try: payload["max_tokens"] = int(final_max_tokens)
            except (ValueError, TypeError): logger.warning(f"Invalid max_tokens value '{final_max_tokens}', omitting from payload.")

        logger.debug(f"LLMClient.call_llm_api [{request_id}]: Payload for {request_url} (Model: {model_name}): {json.dumps(payload, indent=2)}")

        # Non-streaming path
        if not stream:
            try:
                response = await self.http_client.post(request_url, headers=headers, json=payload)
                response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
                response_data = response.json()
                logger.debug(f"LLMClient.call_llm_api [{request_id}] (non-stream): Response data: {json.dumps(response_data, indent=2)}")

                # Assuming the response structure for non-streaming is like OpenAI's
                # e.g., {"choices": [{"message": {"content": "...", "tool_calls": [...]}}], "usage": {...}}
                content_to_return = None
                if response_data.get("choices") and isinstance(response_data["choices"], list) and len(response_data["choices"]) > 0:
                    first_choice = response_data["choices"][0]
                    if isinstance(first_choice, dict) and first_choice.get("message"):
                        message_data = first_choice["message"]
                        # We need to return the full message content, which might include text and tool_calls.
                        # The LLMResponsePayload is designed for the *textual* content primarily.
                        # This part needs careful thought on how to represent a response that might be *only* tool_calls.
                        # For now, let's assume 'content' in LLMResponsePayload refers to textual content.
                        # The full structured message (including tool_calls) would be part of a higher-level object like LLMOutput.

                        # Let's simplify: LLMResponsePayload.content will be the text part of assistant's message.
                        # Tool calls would be handled by the caller by inspecting the raw response_data if needed,
                        # or we enhance LLMResponsePayload to include them.
                        # For this iteration, let's focus on text content.
                        if isinstance(message_data, dict):
                            content_to_return = message_data.get("content") # This should be a string or None
                            # TODO: How to robustly include tool_calls in LLMResponsePayload if stream=False?
                            # For now, the caller (like PathosInterface) would parse this from the raw JSON
                            # or we modify LLMResponsePayload to carry structured tool_calls.
                            # Let's assume for now that if stream=False, the primary output is text content.

                return LLMResponsePayload(
                    content=content_to_return if isinstance(content_to_return, str) else json.dumps(content_to_return) if content_to_return is not None else None,
                    status_code=response.status_code,
                    # raw_response_data=response_data # Potentially include for caller to parse tools
                )
            except httpx.HTTPStatusError as e_http:
                logger.error(f"LLMClient.call_llm_api [{request_id}] (non-stream): HTTP error {e_http.response.status_code}: {e_http.response.text[:500]}")
                return LLMResponsePayload(error_message=e_http.response.text[:200], status_code=e_http.response.status_code)
            except httpx.ReadTimeout:
                logger.error(f"LLMClient.call_llm_api [{request_id}] (non-stream): Request to {request_url} timed out.")
                return LLMResponsePayload(error_message="LLM API request timed out.", status_code=408)
            except httpx.RequestError as e_req:
                logger.error(f"LLMClient.call_llm_api [{request_id}] (non-stream): Request error to {request_url}: {e_req}")
                return LLMResponsePayload(error_message=f"LLM request error: {e_req}", status_code=503)
            except json.JSONDecodeError as e_json_resp:
                logger.error(f"LLMClient.call_llm_api [{request_id}] (non-stream): JSON decode error from response. {e_json_resp}")
                return LLMResponsePayload(error_message=f"JSON decode error: {e_json_resp}", status_code=500)
            except Exception as e:
                logger.error(f"LLMClient.call_llm_api [{request_id}] (non-stream): Unexpected error: {e}", exc_info=True)
                return LLMResponsePayload(error_message=f"Unexpected error: {e}", status_code=500)

        # Streaming Path (remains an async generator)
        # This part needs to be an actual async generator function if called with stream=True
        # So, we define a sub-function for it.
        async def _stream_response():
            try:
                logger.debug(f"LLMClient.call_llm_api [{request_id}] (stream): Attempting stream POST to {request_url}")
                async with self.http_client.stream("POST", request_url, headers=headers, json=payload) as response:
                    logger.debug(f"LLMClient.call_llm_api [{request_id}] (stream): Stream opened. Initial status: {response.status_code}")

                    if response.status_code == 200:
                        current_tool_call_parts_by_index: Dict[int, Dict[str, Any]] = {}
                        line_count = 0; yielded_any_content = False

                        async for line_bytes in response.aiter_lines():
                            line = line_bytes.strip(); line_count += 1
                            logger.debug(f"LLMClient.call_llm_api [{request_id}] (stream): Raw stream line {line_count}: '{line[:200]}...'")

                            if not line: continue
                            if line.startswith("data: "):
                                line_content = line[len("data: "):].strip()
                                if line_content == "[DONE]":
                                    logger.debug(f"LLMClient.call_llm_api [{request_id}] (stream): Stream [DONE] received.")
                                    if current_tool_call_parts_by_index:
                                        finalized_tools = [tc for tc in current_tool_call_parts_by_index.values() if tc.get("id") and tc.get("function", {}).get("name")]
                                        if finalized_tools: yield {"type": "tool_calls_chunk", "payload": {"role": "assistant", "tool_calls": finalized_tools}}
                                    break
                                try:
                                    chunk = json.loads(line_content)
                                    logger.debug(f"LLMClient.call_llm_api [{request_id}] (stream): Parsed chunk: {json.dumps(chunk, indent=2)}")
                                    if not chunk.get("choices"): continue
                                    choice = chunk.get("choices", [{}])[0]; delta = choice.get("delta", {}); finish_reason = choice.get("finish_reason")

                                    if content_delta := delta.get("content"):
                                        if content_delta is not None: yield content_delta; yielded_any_content = True

                                    if tool_calls_delta := delta.get("tool_calls"):
                                        yielded_any_content = True
                                        for tc_item_delta in tool_calls_delta:
                                            idx = tc_item_delta.get("index", 0)
                                            if idx not in current_tool_call_parts_by_index:
                                                current_tool_call_parts_by_index[idx] = {"id": tc_item_delta.get("id"), "type": "function", "function": {"name": "", "arguments": ""}}
                                            current_call = current_tool_call_parts_by_index[idx]
                                            if tc_item_delta.get("id") and not current_call.get("id"): current_call["id"] = tc_item_delta["id"]
                                            if func_delta := tc_item_delta.get("function"):
                                                if name_part := func_delta.get("name"): current_call["function"]["name"] += name_part
                                                if args_part := func_delta.get("arguments"): current_call["function"]["arguments"] += args_part

                                    if finish_reason:
                                        logger.debug(f"LLMClient.call_llm_api [{request_id}] (stream): Finish reason: {finish_reason}")
                                        if finish_reason == "tool_calls" and current_tool_call_parts_by_index:
                                            finalized_tools = [tc for tc in current_tool_call_parts_by_index.values() if tc.get("id") and tc.get("function", {}).get("name")]
                                            if finalized_tools: yield {"type": "tool_calls_chunk", "payload": {"role": "assistant", "tool_calls": finalized_tools}}
                                            current_tool_call_parts_by_index = {}
                                        if usage_data := chunk.get("usage"): yield {"type": "usage_chunk", "payload": usage_data}
                                except json.JSONDecodeError as e_json: logger.warning(f"LLMClient.call_llm_api [{request_id}] (stream): JSON decode error for line: '{line_content}'. Error: {e_json}")
                            elif line.startswith('{"error":'):
                                try:
                                    error_data = json.loads(line); error_msg = error_data.get('error', {}).get('message', 'Unknown stream error object')
                                    yield {"type": "error_chunk", "payload": f"LLM Stream Error Object: {error_msg}"}; return
                                except json.JSONDecodeError: yield {"type": "error_chunk", "payload": "Malformed error from LLM stream."}; return
                            else: logger.debug(f"LLMClient.call_llm_api [{request_id}] (stream): Skipping non-SSE line: {line[:100]}")
                        if not yielded_any_content and not current_tool_call_parts_by_index:
                            logger.warning(f"LLMClient.call_llm_api [{request_id}] (stream): Stream finished but no content or tool calls were yielded.")
                    else: # Non-200 status for stream
                        error_content_bytes = await response.aread(); error_content_str = str(error_content_bytes, 'utf-8', errors='replace')
                        logger.error(f"LLMClient.call_llm_api [{request_id}] (stream): LLM API Error {response.status_code}: {error_content_str[:500]}")
                        yield {"type": "error_chunk", "payload": f"LLM API Error {response.status_code}: {error_content_str[:200]}"}
            except httpx.ReadTimeout:
                logger.error(f"LLMClient.call_llm_api [{request_id}] (stream): LLM API request to {request_url} timed out.");
                yield {"type": "error_chunk", "payload": "LLM API request timed out."}
            except httpx.RequestError as e_req:
                logger.error(f"LLMClient.call_llm_api [{request_id}] (stream): LLM request error to {request_url}: {str(e_req)}");
                yield {"type": "error_chunk", "payload": f"LLM request error: {str(e_req)}"}
            except Exception as e:
                logger.error(f"LLMClient.call_llm_api [{request_id}] (stream): Unexpected error in LLM call to {request_url}: {str(e)}", exc_info=True);
                yield {"type": "error_chunk", "payload": f"Unexpected error in LLM call: {str(e)}"}
            logger.debug(f"LLMClient.call_llm_api [{request_id}] (stream): Call finished.")

        if stream:
            return _stream_response()
        else:
            # This else block for non-streaming path is already handled above.
            # The structure of the function needs to be:
            # if stream: return _stream_response()
            # else: [non-streaming logic directly returning LLMResponsePayload]
            # This means the non-streaming logic should not be inside the _stream_response generator.
            # The current diff puts the non-streaming logic *outside* any generator.
            pass # Non-streaming logic is already above.

        # Fallback if stream is True but somehow not returned via _stream_response() - should not happen.
        # Or if stream is False and the logic above didn't return.
        # This part of the code should ideally be unreachable if the if/else for stream is correct.
        logger.error(f"LLMClient.call_llm_api [{request_id}]: Reached unexpected end of function. Stream: {stream}")
        if stream:
            # This is to satisfy the AsyncGenerator return type if logic is flawed, but it's an error state.
            yield {"type": "error_chunk", "payload": "Internal LLMClient logic error."}
            return
        else:
            return LLMResponsePayload(error_message="Internal LLMClient logic error.", status_code=500)
