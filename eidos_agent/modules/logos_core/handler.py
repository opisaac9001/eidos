# eidos_agent/modules/logos_core/handler.py

import asyncio
import logging
import json
import httpx
import urllib.parse
import os
import re 
import base64
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Use standard logging if get_logger not yet available or if this is an early import
    logger_init = logging.getLogger(__name__) 
    logger_init.warning("zoneinfo module not found. Timezone features relying on IANA names might be limited if Wolfram Alpha is unavailable.")
    ZoneInfo = None # type: ignore

from eidos_agent.core.config import Config, LLMConfig, WolframAlphaConfig, NewsApiConfig, OpenWeatherMapConfig
from eidos_agent.modules.ethos_core.core import EthosCore # EthosCore import for type hint
from eidos_agent.services.web_search import WebSearchService
from eidos_agent.services.home_assistant import HomeAssistantService
from eidos_agent.services.openweathermap import OpenWeatherMapService
from eidos_agent.utils.document_parser import parse_document, SUPPORTED_EXTENSIONS
from eidos_agent.utils.text_splitter import chunk_text_by_char
from eidos_agent.utils.logger import get_logger
from eidos_agent.modules.ethos_core.memory_storage import MemoryEntry # Import MemoryEntry

logger = get_logger(__name__)

class LogosCore:
    def __init__(self, config: Config, ethos_core: EthosCore, ha_service: Optional[HomeAssistantService] = None, owm_service: Optional[OpenWeatherMapService] = None):
        self.config = config
        self.ethos_core = ethos_core 
        self.ha_service = ha_service
        self.owm_service = owm_service

        self.logos_techne_config: Optional[LLMConfig] = config.get_llm_config('LOGOS_TECHNE')
        self.logos_vision_config: Optional[LLMConfig] = config.get_llm_config('LOGOS_VISION_CONTEXT')
        self.logos_research_config: Optional[LLMConfig] = config.get_llm_config('LOGOS_DEEP_RESEARCH')
        
        # Get LLM config for knowledge upkeep, defaulting to LOGOS_TECHNE if not specified
        knowledge_upkeep_llm_role = config.ETHOS.get('knowledge_upkeep_llm_role', 'LOGOS_TECHNE')
        self.knowledge_upkeep_llm_config: Optional[LLMConfig] = config.get_llm_config(knowledge_upkeep_llm_role) # type: ignore


        timeout = 60.0 # Default timeout
        all_llm_timeouts = []
        # Collect timeouts from all configured LLM roles
        for role_key in Config.LLM.keys(): # Iterate through defined LLM roles
            role_config = config.get_llm_config(role_key) # type: ignore
            if role_config and role_config.get('timeout'):
                try:
                    all_llm_timeouts.append(float(role_config['timeout']))
                except ValueError:
                    logger.warning(f"Invalid timeout value for LLM role '{role_key}': {role_config['timeout']}")
        
        if all_llm_timeouts:
            timeout = max(all_llm_timeouts)
        
        self.http_client = httpx.AsyncClient(timeout=timeout + 10.0) # Add a small buffer

        self.web_search_service: Optional[WebSearchService] = None
        if config.ENABLE_WEB_SEARCH:
             brave_config = config.get_brave_search_config()
             if brave_config and brave_config.get('api_key'):
                 self.web_search_service = WebSearchService(config)
                 logger.info("WebSearchService (Brave Search) initialized for LogosCore.")
             else:
                 logger.error("Web Search is ENABLED but Brave Search API key or config is missing. Web search tool will not function.")
                 # self.config.ENABLE_WEB_SEARCH = False # Avoid modifying global config instance here
        else:
             logger.info("Web Search integration disabled in LogosCore.")

        self.wolfram_alpha_config: Optional[WolframAlphaConfig] = config.get_wolfram_alpha_config()
        if self.config.ENABLE_WOLFRAM_ALPHA and not self.wolfram_alpha_config:
             logger.warning("Wolfram Alpha is ENABLED but WOLFRAM_ALPHA_APP_ID is not configured. Math/Weather/Time tools relying on it will fail.")

        self.news_config: Optional[NewsApiConfig] = config.get_news_api_config()
        if self.news_config and self.news_config.get('enabled', False): # Check 'enabled' from the loaded config
            if not self.news_config.get('api_key'):
                logger.warning("News API is configured as ENABLED but API key is missing. News features for daily briefing will be disabled.")
                # Avoid modifying self.news_config['enabled'] directly here if it's from a shared Config instance
            else:
                logger.info("News API integration enabled for LogosCore (Daily Briefing).")
        else:
            logger.info("News API integration disabled or not configured in LogosCore.")

        logger.info("LogosCore initialized with tool dependencies.")
        if self.ha_service and self.ha_service.is_available():
             logger.info("LogosCore has access to an initialized HomeAssistantService.")
        else:
             logger.warning("LogosCore does NOT have access to an initialized HomeAssistantService.")

        if self.owm_service and self.owm_service.is_available:
             logger.info("LogosCore has access to an initialized OpenWeatherMapService.")
        else:
             logger.warning("LogosCore does NOT have access to an initialized OpenWeatherMapService.")


    async def initialize_services(self):
        logger.info("LogosCore initialize_services called (no active async init required currently).")

    async def process_uploaded_document(self, file_content: bytes, filename: str, user_id: Optional[str] = None) -> Dict[str, Any]:
         logger.info(f"LogosCore processing uploaded document: '{filename}' ({len(file_content)} bytes) for user '{user_id or 'unknown'}'.")
         file_extension = Path(filename).suffix.lower()
         if file_extension not in SUPPORTED_EXTENSIONS:
              msg = f"Unsupported file type: '{file_extension}'. Supported: {list(SUPPORTED_EXTENSIONS)}"
              logger.warning(msg)
              return {"success": False, "message": msg}
         try:
             extracted_text = await parse_document(filename, file_content)
             if not extracted_text or not extracted_text.strip():
                  msg = f"No text content could be extracted from '{filename}'."
                  logger.warning(msg)
                  return {"success": False, "message": msg}
             msg = f"Successfully extracted text from document '{filename}'."
             logger.info(msg)
             return {"success": True, "message": msg, "extracted_text": extracted_text}
         except ValueError as e:
              logger.error(f"ValueError processing document '{filename}' for user '{user_id or 'unknown'}': {e}", exc_info=True)
              return {"success": False, "message": f"Error processing '{filename}': {str(e)}"}
         except ImportError as e:
              logger.error(f"ImportError processing document '{filename}' for user '{user_id or 'unknown'}': {e.name}", exc_info=True)
              return {"success": False, "message": f"Cannot process '{filename}': A required library ('{e.name}') is missing. Please install it."}
         except Exception as e:
              logger.error(f"Unexpected error processing document '{filename}' for user '{user_id or 'unknown'}': {e}", exc_info=True)
              return {"success": False, "message": f"An unexpected system error occurred while processing '{filename}'."}

    async def add_document_to_rag(self, extracted_text: str, filename: str = "uploaded_document", user_id: Optional[str] = None, doc_id: Optional[str] = None):
         if not extracted_text or not extracted_text.strip():
              logger.warning(f"No text content provided to add document '{filename}' to RAG.")
              return {"success": False, "message": "No text content to add to RAG."}

         final_doc_id = doc_id or str(uuid.uuid4())
         logger.info(f"LogosCore adding document '{filename}' (ID: {final_doc_id}) to RAG system for user '{user_id or 'unknown'}'.")

         try:
             chunk_size = self.config.ETHOS.get('text_chunk_size', 1000)
             chunk_overlap = self.config.ETHOS.get('text_chunk_overlap', 150)
             text_chunks = chunk_text_by_char(extracted_text, chunk_size, chunk_overlap)
             if not text_chunks:
                  msg = f"Failed to split document '{filename}' into processable chunks for RAG."
                  logger.warning(msg)
                  return {"success": False, "message": msg}

             await self.ethos_core.add_document_chunks(final_doc_id, filename, text_chunks)
             msg = f"Successfully chunked and initiated storage for document '{filename}' ({len(text_chunks)} chunks) for RAG."
             logger.info(msg)
             return {"success": True, "message": msg, "doc_id": final_doc_id, "num_chunks": len(text_chunks)}
         except Exception as e:
              logger.error(f"Unexpected error adding document '{filename}' to RAG for user '{user_id or 'unknown'}': {e}", exc_info=True)
              return {"success": False, "message": f"An unexpected system error occurred while adding '{filename}' to RAG."}

    async def execute_get_time(self, location: Optional[str] = None) -> str:
        try:
            final_time_str = ""
            current_datetime_utc = datetime.now(timezone.utc)
            utc_time_formatted_for_fallback = current_datetime_utc.strftime('%A, %B %d, %Y at %I:%M:%S %p %Z (%z)')

            if location:
                logger.info(f"Get_current_time tool called with location/timezone: '{location}'")
                target_tz_obj = None
                if ZoneInfo:
                    try:
                        target_tz_obj = ZoneInfo(location)
                        now_localized = datetime.now(target_tz_obj)
                        final_time_str = f"The current time in {location} is {now_localized.strftime('%A, %B %d, %Y at %I:%M:%S %p %Z (%z)')}."
                        logger.info(f"Resolved '{location}' directly as IANA timezone. Time: {final_time_str}")
                    except Exception:
                        logger.debug(f"Could not directly interpret '{location}' as an IANA timezone. Will attempt lookup via Wolfram Alpha if enabled.")
                else:
                    logger.warning("zoneinfo module not available. Cannot parse location as IANA timezone directly. Will attempt lookup via Wolfram Alpha if enabled.")

                if not final_time_str:
                    if self.config.ENABLE_WOLFRAM_ALPHA and self.wolfram_alpha_config:
                        logger.debug(f"Attempting to get time for '{location}' via Wolfram Alpha.")
                        wa_query = f"current time in {location}"
                        wa_result = await self.query_wolfram_alpha(wa_query)
                        if wa_result.get('success') and wa_result.get('result'):
                            final_time_str = f"For {location}, Wolfram Alpha reports the current time as: {wa_result['result']}."
                            logger.info(f"Successfully retrieved time from Wolfram Alpha for '{location}': {wa_result['result']}")
                        else:
                            logger.warning(f"Wolfram Alpha failed to provide time for '{location}'. WA message: {wa_result.get('message')}")
                    else:
                        logger.warning("Wolfram Alpha not available or not enabled. Cannot look up time for '{location}'.")

                if not final_time_str:
                    final_time_str = (
                        f"I wasn't able to determine the specific local time for '{location}'. "
                        f"The current Coordinated Universal Time (UTC) is {utc_time_formatted_for_fallback}."
                    )
                    logger.info(f"Failed to resolve specific time for '{location}', providing UTC with explanation.")
            else:
                final_time_str = (
                    f"The current Coordinated Universal Time (UTC) is {utc_time_formatted_for_fallback}. "
                    "If you'd like the time for a specific place, just let me know!"
                )
                logger.info("No location provided for get_current_time, providing UTC and inviting user to specify.")

            logger.debug(f"Final result for get_current_time tool: {final_time_str}")
            return final_time_str
        except Exception as e:
            logger.error(f"Unexpected error in execute_get_time: {e}", exc_info=True)
            return json.dumps({"error": f"An unexpected error occurred while trying to determine the time: {str(e)}"})

    async def execute_describe_image(self, image_data_b64: str, prompt_from_llm: str) -> str:
        logger.info(f"LogosCore: Describing image. User prompt for image: '{prompt_from_llm[:50]}...' Image data length: {len(image_data_b64)}")
        if not self.config.ENABLE_VISION_PROCESSING:
            logger.warning("Vision processing is disabled in config.")
            return json.dumps({"error": "Vision processing feature is currently disabled."})
        if not self.logos_vision_config or not self.logos_vision_config.get('url'):
            logger.error("LOGOS_VISION_CONTEXT LLM is not configured with a URL. Cannot describe image.")
            return json.dumps({"error": "Vision model (LOGOS_VISION_CONTEXT) is not configured."})

        vision_llm_config = self.logos_vision_config
        api_url = f"{vision_llm_config['url']}/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = vision_llm_config.get('api_key')
        if api_key and api_key.lower() not in ['lm-studio', 'ollama', '']:
            headers["Authorization"] = f"Bearer {api_key}"
        messages_payload = [{"role": "user", "content": [{"type": "text", "text": prompt_from_llm},{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data_b64}"}}]}]
        llm_payload: Dict[str, Any] = {"model": vision_llm_config.get('model'), "messages": messages_payload, "temperature": vision_llm_config.get('temperature', 0.2), "max_tokens": vision_llm_config.get('max_tokens', 1024)}
        if not llm_payload.get('model'): del llm_payload['model']
        llm_name_for_log = vision_llm_config.get('model', 'Logos Vision LLM')
        logger.debug(f"Calling Vision LLM '{llm_name_for_log}' at {api_url} for image description.")
        try:
            timeout_config = vision_llm_config.get('timeout', 60)
            try: timeout_seconds = float(timeout_config)
            except (ValueError, TypeError): timeout_seconds = 60.0; logger.warning(f"Invalid Vision LLM timeout '{timeout_config}', defaulting to {timeout_seconds}s.")
            response = await self.http_client.post(api_url, headers=headers, json=llm_payload, timeout=timeout_seconds)
            response.raise_for_status()
            result_json = response.json()
            if result_json.get("choices") and len(result_json["choices"]) > 0:
                message = result_json["choices"][0].get("message")
                if message and isinstance(message.get("content"), str):
                    description = message["content"].strip()
                    logger.info(f"Vision LLM '{llm_name_for_log}' provided description: {description[:100]}...")
                    return description
            logger.warning(f"Unexpected response format from Vision LLM '{llm_name_for_log}': {result_json}")
            return json.dumps({"error": "Received unexpected response format from the vision model."})
        except httpx.TimeoutException as e:
            logger.error(f"Timeout calling Vision LLM '{llm_name_for_log}' at {api_url}: {e}")
            return json.dumps({"error": f"Timeout connecting to vision model: {str(e)}"})
        except httpx.RequestError as e:
            logger.error(f"HTTP request failed calling Vision LLM '{llm_name_for_log}' at {api_url}: {e}")
            return json.dumps({"error": f"Connection error with vision model: {str(e)}"})
        except httpx.HTTPStatusError as e:
            logger.error(f"Vision LLM '{llm_name_for_log}' returned error {e.response.status_code} from {api_url}: {e.response.text[:500]}")
            try: error_details = e.response.json().get('message', e.response.text)
            except: error_details = e.response.text
            return json.dumps({"error": f"Vision model API error ({e.response.status_code})", "detail": error_details[:200]})
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response from Vision LLM '{llm_name_for_log}'. Response text: {response.text[:500] if 'response' in locals() else 'N/A'}. Error: {e}")
            return json.dumps({"error": f"Invalid JSON response from vision model: {e}"})
        except Exception as e:
            logger.error(f"Error processing Vision LLM '{llm_name_for_log}' response: {e}", exc_info=True)
            return json.dumps({"error": f"Failed to process vision model response: {str(e)}"})

    async def execute_web_search(self, query: str) -> Optional[List[Dict[str, str]]]:
        if not self.config.ENABLE_WEB_SEARCH or not self.web_search_service:
            logger.error("Web search requested, but WebSearchService is not available or web search is disabled.")
            return None
        if not query or not isinstance(query, str) or not query.strip():
            logger.warning("Web search attempted with empty or invalid query.")
            return []
        return await self.web_search_service.perform_search(query)

    async def execute_math_calculation(self, expression: str) -> str:
        logger.info(f"Executing math calculation for: '{expression}'")
        if not self.config.ENABLE_WOLFRAM_ALPHA or not self.wolfram_alpha_config:
            return json.dumps({"error": "Calculation service (Wolfram Alpha) is not available or not configured."})
        if not expression or not isinstance(expression, str) or not expression.strip():
             return json.dumps({"error": "No valid mathematical expression was provided."})
        wa_result = await self.query_wolfram_alpha(expression)
        if wa_result.get('success') and wa_result.get('result'):
            result_lines = wa_result['result'].splitlines()
            cleaned_result = " | ".join(line.strip() for line in result_lines if line.strip())
            logger.info(f"Math calculation result: {cleaned_result}")
            return cleaned_result if cleaned_result else "[Calculation resulted in empty response from Wolfram Alpha]"
        else:
            error_message = wa_result.get('message', 'Wolfram Alpha calculation failed or could not interpret the expression.')
            logger.warning(f"Math calculation failed for '{expression}': {error_message}")
            return json.dumps({"error": error_message})

    async def execute_get_weather(self, location: str, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        logger.info(f"Executing weather query for: '{location}' (User context: {user_id_context})")
        if not location or not location.strip():
             return {"success": False, "error": "No valid location was provided for the weather query.", "location": location}

        if self.owm_service and self.owm_service.is_available:
             logger.debug(f"Attempting to get weather from OpenWeatherMap for: '{location}'")
             owm_result = await self.owm_service.get_current_weather(location)
             if owm_result.get("success"):
                  logger.info(f"Successfully retrieved weather from OpenWeatherMap for '{location}'.")
                  if self.ethos_core and user_id_context and user_id_context not in ["system_briefing", "unknown_user", "api_guest_user", None, "system_oneiros", "system_document", "world_knowledge_store", "system_reflection"]:
                      weather_data_from_owm = owm_result.get("weather_data", {})
                      derived_iana_tz = weather_data_from_owm.get("iana_timezone")
                      if derived_iana_tz:
                          logger.debug(f"OWM provided IANA timezone '{derived_iana_tz}' for location '{location}'. Storing for user '{user_id_context}'.")
                          await self.execute_store_user_fact(
                              attribute_name="derived_iana_timezone",
                              attribute_value=derived_iana_tz,
                              user_statement_context=f"IANA timezone derived from OWM for location '{location}'.",
                              user_id=user_id_context
                          )
                  return owm_result
             else:
                  logger.warning(f"OpenWeatherMap fetch failed for '{location}': {owm_result.get('error')}. Falling back.")
        else:
             logger.debug("OpenWeatherMap not configured or service not available. Proceeding to next source.")

        ha_weather_entity_id = self.config.HOME_ASSISTANT.get('ha_weather_entity_id') if self.config.HOME_ASSISTANT else None
        if self.ha_service and self.ha_service.is_available() and ha_weather_entity_id:
             logger.debug(f"Attempting to get weather from Home Assistant entity: {ha_weather_entity_id}")
             try:
                 ha_state = await self.ha_service._get_entity_state_full(ha_weather_entity_id)
                 if ha_state and isinstance(ha_state, dict):
                      logger.info(f"Successfully retrieved state for HA weather entity {ha_weather_entity_id}.")
                      ha_attributes = ha_state.get('attributes', {})
                      ha_weather_data: Dict[str, Any] = {"location": location, "description": ha_state.get('state'), "temperature": ha_attributes.get('temperature'), "unit": ha_attributes.get('temperature_unit'), "humidity": ha_attributes.get('humidity'), "wind_speed": ha_attributes.get('wind_speed'), "source": f"Home Assistant ({ha_weather_entity_id})"}
                      ha_weather_data = {k: v for k, v in ha_weather_data.items() if v is not None}
                      return {"success": True, "weather_data": ha_weather_data}
                 else:
                      logger.warning(f"HA weather entity {ha_weather_entity_id} state not found or invalid format.")
             except Exception as ha_e:
                  logger.error(f"Error fetching state for HA weather entity {ha_weather_entity_id}: {ha_e}", exc_info=True)
             logger.info("Falling back to Wolfram Alpha for weather.")
        else:
             logger.debug("Home Assistant weather not configured or HA service not available. Proceeding with Wolfram Alpha.")

        if not self.config.ENABLE_WOLFRAM_ALPHA or not self.wolfram_alpha_config:
            return {"success": False, "error": "No weather service (OWM, HA, WA) is available or configured.", "location": location}
        logger.debug(f"Attempting to get weather from Wolfram Alpha for: '{location}'")
        query = f"weather in {location}"
        wa_result = await self.query_wolfram_alpha(query)
        extracted_data: Dict[str, Any] = {"location": location}
        success = False
        error_message: Optional[str] = None
        if wa_result.get('success') and wa_result.get('raw_response'):
             query_result = wa_result['raw_response'].get('queryresult', {})
             if isinstance(query_result, dict) and query_result.get('success'):
                  pods = query_result.get('pods', [])
                  if isinstance(pods, list):
                       for pod in pods:
                            if isinstance(pod, dict) and pod.get('id') in ["InstantaneousWeather:WeatherData", "CurrentLocationWeather:WeatherData", "WeatherForecast:WeatherData", "LatestRecordedWeather:WeatherData"] and not pod.get('error', False):
                                 subpods = pod.get('subpods', [])
                                 if isinstance(subpods, list):
                                     for subpod in subpods:
                                              if isinstance(subpod, dict) and subpod.get('plaintext'):
                                                  text = subpod['plaintext'].strip()
                                                  logger.debug(f"Parsing weather text from pod '{pod.get('id')}': {text}")
                                                  lines = text.split('\n')
                                                  for line in lines:
                                                      parts = line.split('|', 1)
                                                      if len(parts) == 2:
                                                          key = parts[0].strip().lower().replace(' ', '_')
                                                          value = parts[1].strip()
                                                          if key == 'temperature':
                                                              temp_match = re.match(r'(-?\d+(\.\d+)?)\s*(°?[FC])?', value, re.IGNORECASE)
                                                              if temp_match:
                                                                  extracted_data['temperature'] = float(temp_match.group(1))
                                                                  extracted_data['unit'] = temp_match.group(3) or '°'
                                                                  celsius_match = re.search(r'\((\d+(\.\d+)?)°?C\)', value, re.IGNORECASE)
                                                                  if celsius_match: extracted_data['temperature_celsius'] = float(celsius_match.group(1))
                                                          elif key == 'conditions': extracted_data['description'] = value
                                                          elif key == 'relative_humidity':
                                                              humidity_match = re.match(r'(\d+%)', value)
                                                              if humidity_match: extracted_data['humidity'] = humidity_match.group(1)
                                                          elif key == 'wind_speed': extracted_data['wind_speed'] = value
                                                  if 'temperature' in extracted_data or 'description' in extracted_data:
                                                       success = True
                                                       logger.debug(f"Successfully parsed weather data from pod '{pod.get('id')}'. Extracted: {extracted_data}")
                                                       break
                                     if success: break
                            if not success: # Check if any success was found in weather-specific pods
                                logger.debug("No weather-specific pods found in WA response. Checking 'Result' pod as fallback.")
                                for pod_alt in pods: 
                                     if isinstance(pod_alt, dict) and pod_alt.get('id') == 'Result' and not pod_alt.get('error', False):
                                          subpods_alt = pod_alt.get('subpods', [])
                                          if isinstance(subpods_alt, list) and subpods_alt:
                                               if isinstance(subpods_alt[0], dict) and subpods_alt[0].get('plaintext'):
                                                    fallback_text = subpods_alt[0]['plaintext'].strip()
                                                    logger.debug(f"Using 'Result' pod as fallback: {fallback_text}")
                                                    extracted_data['description'] = fallback_text # Store the general result as description
                                                    success = True # Mark as success even if it's just a general string
                                                    break
                       if not success: # If still no success after checking all pods
                           error_message = "Specific weather data pods not found in Wolfram Alpha response, and no fallback 'Result' pod was usable."
                           success = False # Ensure success is false
                  else: # pods is not a list
                      error_message = "Wolfram Alpha response has invalid 'pods' format."
                      success = False
             else: # query_result was not successful or not a dict
                 error_message = wa_result.get('message', 'Wolfram Alpha weather query failed or could not interpret the location.')
                 raw_response = wa_result.get('raw_response', {})
                 if isinstance(raw_response, dict) and (raw_response.get('queryresult', {}).get('error') or not raw_response.get('queryresult', {}).get('success', True)):
                     error_message = f"Wolfram Alpha could not interpret the location '{location}' or no weather data was found."
                 success = False # Ensure success is false
        else: # wa_result was not successful or no raw_response
            error_message = wa_result.get('message', "Failed to get a successful response from Wolfram Alpha.")
            success = False

        if success:
            extracted_data.setdefault('temperature', None)
            extracted_data.setdefault('unit', None)
            extracted_data.setdefault('description', extracted_data.get('description', 'Weather information retrieved.')) # Default description if only fallback was used
            extracted_data.setdefault('humidity', None)
            extracted_data.setdefault('wind_speed', None)
            extracted_data['location'] = location # Ensure location is always present
            extracted_data['source'] = "Wolfram Alpha"
            return {"success": True, "weather_data": extracted_data}
        else:
             return {"success": False, "error": error_message or "Unknown error processing Wolfram Alpha weather response.", "location": location, "message": wa_result.get('message')}


    async def execute_store_user_fact(self, attribute_name: str, attribute_value: str, user_statement_context: str, user_id: str) -> str:
        logger.info(f"LogosCore attempting to store user fact for user '{user_id}': {attribute_name} = {attribute_value[:50]}...")
        try:
            normalized_attr_name = attribute_name.lower().replace(" ", "_").strip()
            if not normalized_attr_name:
                logger.warning("Attempted to store user fact with empty or whitespace-only attribute name.")
                return json.dumps({"error": "Attribute name for user fact cannot be empty."})

            fact_content_structured = {
                "attribute": normalized_attr_name,
                "value": attribute_value,
                "original_user_statement": user_statement_context,
                "stored_by_tool_timestamp": datetime.now(timezone.utc).isoformat()
            }

            entry_data = {
                "type": "user_fact",
                "content": json.dumps(fact_content_structured), 
                "salience": 1.5, 
                "metadata": {
                    "user_id": user_id, 
                    "fact_attribute_key": normalized_attr_name, 
                    "source": "pathos_tool_store_user_fact" 
                }
            }
            await self.ethos_core.add_memory_entry(entry_data, user_id_context=user_id) 

            logger.info(f"Successfully stored user fact for user '{user_id}': {normalized_attr_name} = {attribute_value[:50]}...")
            return json.dumps({"status": "success", "message": f"Okay, I've noted that your {attribute_name} is {attribute_value}."})
        except Exception as e:
            logger.error(f"Error in execute_store_user_fact for user '{user_id}', attribute '{attribute_name}': {e}", exc_info=True)
            return json.dumps({"error": f"Failed to store user fact due to an internal error: {str(e)}"})

    async def execute_store_world_fact(self, fact_statement: str, source_description: str, topic_tags: Optional[List[str]] = None, confidence_level: float = 0.8) -> str:
        logger.info(f"LogosCore attempting to store world fact: '{fact_statement[:100]}...'")
        if topic_tags is None: topic_tags = []
        try:
            try: confidence_level = float(confidence_level)
            except (ValueError, TypeError): confidence_level = 0.8
            confidence_level = max(0.0, min(1.0, confidence_level))
            entry_data: Dict[str, Any] = {"type": "world_knowledge", "content": fact_statement, "salience": 0.7 + (confidence_level * 0.3), "metadata": {"stored_by_user_id": "system_or_current_user", "source_description": source_description, "topic_tags": sorted(list(set(tag.lower().strip() for tag in topic_tags if isinstance(tag, str) and tag.strip()))), "confidence_level": confidence_level, "stored_by_tool_timestamp": datetime.now(timezone.utc).isoformat()}}
            await self.ethos_core.add_memory_entry(entry_data, user_id_context="world_knowledge_store")
            logger.info(f"Successfully stored world fact: '{fact_statement[:100]}...' with tags {entry_data['metadata']['topic_tags']}")
            return json.dumps({"status": "success", "message": f"Okay, I've noted the fact: '{fact_statement[:70]}...'."})
        except Exception as e:
            logger.error(f"Error in execute_store_world_fact for fact '{fact_statement[:50]}...': {e}", exc_info=True)
            return json.dumps({"error": f"Failed to store world fact due to an internal error: {str(e)}"})

    async def execute_deep_research(self, research_query: str, num_searches_to_perform: int = 3) -> str:
           logger.info(f"Executing deep research for query: '{research_query}' (will perform up to {num_searches_to_perform} web searches).")
           if not self.config.ENABLE_WEB_SEARCH or not self.web_search_service:
               logger.error("Deep research requires web search capability, which is disabled or not configured.")
               return json.dumps({"error": "Web search capability is required for deep research and is currently unavailable."})
           research_llm_config = self.logos_research_config
           if not research_llm_config or not research_llm_config.get('url'):
               logger.error("LOGOS_DEEP_RESEARCH LLM is not configured. Cannot synthesize research.")
               return json.dumps({"error": "Deep research synthesis LLM (LOGOS_DEEP_RESEARCH) is not configured."})
           search_queries = [research_query]
           if num_searches_to_perform > 1: search_queries.append(f"overview of benefits and drawbacks of {research_query}")
           if num_searches_to_perform > 2: search_queries.append(f"key aspects and components of {research_query}")
           if num_searches_to_perform > 3: search_queries.append(f"future trends related to {research_query}")
           search_queries = search_queries[:num_searches_to_perform]
           logger.debug(f"Generated {len(search_queries)} search queries for deep research: {search_queries}")
           aggregated_search_text = ""; search_results_count = 0
           max_snippet_length = 700
           for i, sq in enumerate(search_queries):
               logger.info(f"Deep research: Performing web search {i+1}/{len(search_queries)} for sub-query: '{sq}'")
               results = await self.web_search_service.perform_search(sq)
               if results:
                   for res_idx, res in enumerate(results):
                       title = res.get("title", "N/A"); snippet = res.get("snippet", ""); link = res.get("link", "#")
                       aggregated_search_text += f"--- Result {search_results_count + 1} (from query: '{sq}') ---\nTitle: {title}\nLink: {link}\nSnippet: {snippet[:max_snippet_length]}\n\n"; search_results_count +=1
               await asyncio.sleep(0.3) # Be nice to the search API
           if not aggregated_search_text:
               logger.warning(f"No web search results found for any sub-queries of deep research topic: '{research_query}'.")
               return json.dumps({"error": "No information was found during web searches for the deep research query."})
           logger.info(f"Aggregated {search_results_count} search result snippets. Total length of aggregated text: {len(aggregated_search_text)} chars.")
           
           # Estimate max input tokens for synthesis LLM (conservative estimate)
           # Assuming average 3-4 chars per token for English text
           llm_max_tokens_for_synthesis = research_llm_config.get('max_tokens', 4096)
           # Reserve some tokens for the prompt itself and the LLM's output
           reserved_tokens_for_prompt_and_output = 1024 
           max_input_chars_for_synthesis_llm = (llm_max_tokens_for_synthesis - reserved_tokens_for_prompt_and_output) * 3 


           if len(aggregated_search_text) > max_input_chars_for_synthesis_llm:
               logger.warning(f"Aggregated search text ({len(aggregated_search_text)} chars) is too long for synthesis LLM (approx limit {max_input_chars_for_synthesis_llm} chars), truncating.")
               aggregated_search_text = aggregated_search_text[:max_input_chars_for_synthesis_llm]
           
           synthesis_system_prompt = (
                "You are a highly skilled research assistant. Your task is to synthesize the provided information snippets "
                "into a comprehensive, well-structured, and coherent report on the given research query. "
                "Focus on extracting key facts, main arguments, different perspectives, and any notable conclusions. "
                "Organize the information logically. Avoid simply copying the snippets; instead, integrate and rephrase the information. "
                "The report should be informative and easy to understand. Do not include any preamble like 'Here is your report'."
            )
           synthesis_user_prompt = (
                f"Research Query: '{research_query}'\n\n"
                f"Collected Information Snippets:\n"
                f"--- START COLLECTED INFORMATION ---\n"
                f"{aggregated_search_text}\n"
                f"--- END COLLECTED INFORMATION ---\n\n"
                f"Please provide your synthesized report on '{research_query}':"
            )
           
           synthesis_prompt_messages = [
               {"role": "system", "content": synthesis_system_prompt},
               {"role": "user", "content": synthesis_user_prompt}
            ]

           try:
               logger.info(f"Calling LOGOS_DEEP_RESEARCH LLM ({research_llm_config.get('model')}) for synthesis of '{research_query}'.")
               # Use _call_logos_llm with full messages structure
               synthesized_report_str = await self._call_logos_llm(research_llm_config, llm_messages_for_synthesis=synthesis_prompt_messages)
               
               if not synthesized_report_str or synthesized_report_str.startswith("["): # Check for error strings
                   logger.error(f"LOGOS_DEEP_RESEARCH LLM returned an empty or error response for research synthesis: {synthesized_report_str}")
                   return json.dumps({"error": "Failed to synthesize the research findings due to an LLM error or empty response."})
               
               logger.info(f"Successfully synthesized deep research report for '{research_query}'. Length: {len(synthesized_report_str)}")
               return synthesized_report_str
           except Exception as e:
               logger.error(f"Error during deep research synthesis LLM call for '{research_query}': {e}", exc_info=True)
               return json.dumps({"error": f"An unexpected error occurred during research synthesis: {str(e)}"})

    async def execute_get_news_headlines(self) -> str:
        logger.info("Executing get_news_headlines tool.")
        if not self.news_config or not self.news_config.get('enabled') or not self.news_config.get('api_key'):
            logger.warning("News API requested by tool, but not enabled or configured.")
            return json.dumps({"error": "News headlines service is not available or not configured."})
        try:
            # Use _fetch_news_headlines_with_details to get structured data
            detailed_headlines = await self._fetch_news_headlines_with_details(news_api_config=self.news_config)
            if detailed_headlines:
                # Format for LLM consumption (simple list of titles, or title + snippet)
                formatted_headlines_parts = ["Top News Headlines:"]
                for item in detailed_headlines:
                    title = item.get('title', 'No Title')
                    snippet = item.get('snippet', '')
                    url = item.get('url', '#')
                    # For LLM, a concise format is often better
                    formatted_headlines_parts.append(f"- {title}{f' (Snippet: {snippet[:50]}...)' if snippet else ''}")
                
                formatted_headlines_str = "\n".join(formatted_headlines_parts)
                logger.info(f"News headlines fetched successfully. Returning {len(detailed_headlines)} headlines (formatted for LLM).")
                return formatted_headlines_str
            else:
                logger.warning("News API fetch returned no headlines.")
                return json.dumps({"status": "success", "message": "No recent news headlines found."}) # Informative for LLM
        except Exception as e:
            logger.error(f"Error executing get_news_headlines tool: {e}", exc_info=True)
            return json.dumps({"error": f"An unexpected error occurred while fetching news headlines: {str(e)}"})

    async def _fetch_news_headlines_with_details(self, news_api_config: NewsApiConfig) -> List[Dict[str, str]]:
        if not news_api_config or not news_api_config.get('enabled') or not news_api_config.get('api_key'):
            logger.info("News API fetch with details skipped: not enabled or API key missing.")
            return []
        api_key = news_api_config['api_key']
        base_url = news_api_config['base_url'].rstrip('/')
        
        params: Dict[str, Any] = { # Ensure params is typed
            "api_token": api_key, 
            "locale": news_api_config.get('default_locale', 'us'), 
            "language": news_api_config.get('default_language', 'en'), 
            "limit": news_api_config.get('limit', 5), 
            "snippet_len": 150 
        }
        timeout_seconds = news_api_config.get('timeout', 15)
        
        api_endpoint_to_use = f"{base_url}/v1/news/top" # Default to top news
        
        # Check for specific search parameters that might change the endpoint or add query params
        if search_keywords := news_api_config.get('search_keywords'):
            params['search'] = search_keywords
            api_endpoint_to_use = f"{base_url}/v1/news/all" # Use /all endpoint for keyword search
        elif categories := news_api_config.get('categories'): # Use categories if no keywords
            params['categories'] = categories
            # /top endpoint usually supports categories
        
        if include_sources := news_api_config.get('include_source_ids'):
            params['source_ids'] = include_sources
            api_endpoint_to_use = f"{base_url}/v1/news/all" # /all endpoint for source filtering
        
        if exclude_sources := news_api_config.get('exclude_source_ids'): # TheNewsAPI uses 'exclude_domains'
            params['exclude_domains'] = exclude_sources
            # This might also imply /all endpoint depending on API, but often works with /top too

        logger.debug(f"Fetching news details from TheNewsAPI: {api_endpoint_to_use} with params: {params}")
        detailed_articles: List[Dict[str, str]] = []
        try:
            response = await self.http_client.get(api_endpoint_to_use, params=params, timeout=float(timeout_seconds))
            response.raise_for_status()
            data = response.json()
            articles = data.get("data", []) # TheNewsAPI uses "data" field for articles
            for article_data in articles:
                if isinstance(article_data, dict):
                    title = article_data.get("title", "").strip()
                    url = article_data.get("url", "#").strip()
                    # TheNewsAPI uses "snippet" or "description"
                    snippet = article_data.get("snippet", article_data.get("description", "")).strip() 
                    if title and url: detailed_articles.append({"title": title, "url": url, "snippet": snippet})
            logger.info(f"Fetched {len(detailed_articles)} detailed articles from TheNewsAPI.")
            return detailed_articles
        except Exception as e: 
            logger.error(f"Error fetching detailed news from TheNewsAPI: {e}", exc_info=True)
            return []

    async def generate_daily_briefing(self, user_id_context: Optional[str] = None) -> Optional[str]:
        logger.info(f"LogosCore attempting to generate daily briefing for panel (context: {user_id_context or 'system'})...")
        now_utc = datetime.now(timezone.utc)
        today_date_str = now_utc.strftime('%Y-%m-%d')
        local_time_for_display_str = now_utc.strftime('%A, %B %d, %Y, %I:%M %p %Z')
        if self.ethos_core and user_id_context and user_id_context not in ["system_briefing", "unknown_user", "api_guest_user", "system_oneiros", "system_document", "world_knowledge_store", "system_reflection", None]:
            local_dt = await self.ethos_core.get_local_datetime_for_user(user_id_context)
            local_time_for_display_str = local_dt.strftime('%A, %B %d, %Y, %I:%M %p %Z')

        weather_info_parts = ["**Weather:**"]
        news_info_parts = ["**Top News:**"]
        briefing_weather_location = os.getenv("BRIEFING_WEATHER_LOCATION_FALLBACK", "New York, NY")
        user_location_used_for_weather = False
        if self.ethos_core and user_id_context and user_id_context not in ["system_briefing", "unknown_user", "api_guest_user", "system_oneiros", "system_document", "world_knowledge_store", "system_reflection", None]:
            logger.debug(f"DEBUG: generate_daily_briefing attempting to fetch preferred_location for user '{user_id_context}'")
            location_fact = await self.ethos_core.get_user_fact('preferred_location', user_id_context)
            if location_fact: logger.debug(f"DEBUG: Found preferred_location fact for '{user_id_context}': {location_fact.get('content')}")
            else: logger.debug(f"DEBUG: No preferred_location fact found for '{user_id_context}'.")
            if location_fact and location_fact.get('content'):
                try:
                    fact_content = json.loads(location_fact['content'])
                    user_pref_loc = fact_content.get('value')
                    if user_pref_loc and user_pref_loc.strip():
                        briefing_weather_location = user_pref_loc
                        user_location_used_for_weather = True
                        logger.info(f"Using user '{user_id_context}' preferred location for briefing weather: '{briefing_weather_location}'")
                    else: logger.debug(f"User '{user_id_context}' preferred location is empty. Using fallback: '{briefing_weather_location}'")
                except json.JSONDecodeError: logger.warning(f"Could not parse preferred_location for user '{user_id_context}'. Using fallback: '{briefing_weather_location}'")
        else:
            if not self.ethos_core: logger.warning("EthosCore not available in LogosCore to fetch user's preferred location for briefing. Using fallback.")
            elif not user_id_context or user_id_context in ["system_briefing", "unknown_user", "api_guest_user", "system_oneiros", "system_document", "world_knowledge_store", "system_reflection", None]:
                 logger.debug(f"No specific user context ('{user_id_context}') for briefing weather. Using fallback: '{briefing_weather_location}'")
        logger.debug(f"DEBUG: Final briefing_weather_location for weather fetch: '{briefing_weather_location}'. User location used: {user_location_used_for_weather}")
        weather_result = await self.execute_get_weather(briefing_weather_location, user_id_context=user_id_context) 
        if weather_result.get('success') and weather_result.get('weather_data'):
            wd = weather_result['weather_data']
            weather_info_parts.append(f"- Location: {wd.get('location', briefing_weather_location)}")
            temp_str = str(wd.get('temperature', '--'))
            unit_str = str(wd.get('unit', ''))
            desc_str = str(wd.get('description', 'N/A'))
            weather_info_parts.append(f"- Conditions: {temp_str}{unit_str}, {desc_str}")
            if wd.get('humidity'): weather_info_parts.append(f"- Humidity: {wd.get('humidity')}")
            if wd.get('wind_speed'): weather_info_parts.append(f"- Wind: {wd.get('wind_speed')}")
        else: weather_info_parts.append(f"- Weather for {briefing_weather_location}: {weather_result.get('error', 'Unavailable')}")

        if self.news_config and self.news_config.get('enabled'):
            detailed_headlines = await self._fetch_news_headlines_with_details(news_api_config=self.news_config)
            if detailed_headlines:
                for item in detailed_headlines:
                    short_snippet = item.get('snippet', '')
                    if len(short_snippet) > 100: short_snippet = short_snippet[:97] + "..."
                    news_info_parts.append(f"- [{item['title']}]({item['url']})")
                    if short_snippet: news_info_parts.append(f"  - _{short_snippet}_")
            else: news_info_parts.append("- No top headlines found or fetch failed.")
        else: news_info_parts.append("- News service disabled.")

        panel_briefing_content = f"### Daily Briefing ({local_time_for_display_str})\n\n"
        panel_briefing_content += "\n".join(weather_info_parts) + "\n\n" + "\n".join(news_info_parts)
        logger.info(f"Generated panel-formatted daily briefing. Length: {len(panel_briefing_content)}")
        await self.ethos_core.add_memory_entry({"type": "daily_briefing", "content": panel_briefing_content, "metadata": {"generation_timestamp_utc": now_utc.isoformat(), "briefing_date": today_date_str, "briefing_format_version": "panel_v1", "generated_for_user_context": user_id_context or "system"}}, user_id_context="system_briefing")
        return panel_briefing_content

    async def get_or_generate_daily_briefing(self, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        logger.info(f"DEBUG: get_or_generate_daily_briefing called with user_id_context: '{user_id_context}'")
        logger.info(f"LogosCore: get_or_generate_daily_briefing called by user '{user_id_context or 'unknown'}'.")
        if not self.ethos_core:
            logger.error("EthosCore not available in LogosCore for get_or_generate_daily_briefing.")
            return {"success": False, "message": "Internal system error: EthosCore not accessible."}
        try:
            existing_briefing = await self.ethos_core.get_todays_briefing()
            if existing_briefing:
                logger.info(f"Found existing daily briefing for user '{user_id_context or 'unknown'}'.")
                return {"success": True, "briefing_content": existing_briefing, "message": "Daily briefing retrieved."}
        except Exception as e: logger.error(f"Error checking for existing daily briefing: {e}", exc_info=True)
        logger.info(f"No existing daily briefing for today. Attempting to generate new one for user '{user_id_context or 'unknown'}'.")
        try:
            new_briefing_content = await self.generate_daily_briefing(user_id_context=user_id_context)
            if new_briefing_content:
                logger.info(f"Successfully generated and stored new daily briefing for user '{user_id_context or 'unknown'}'.")
                return {"success": True, "briefing_content": new_briefing_content, "message": "Daily briefing generated."}
            else:
                logger.error(f"Failed to generate new daily briefing for user '{user_id_context or 'unknown'}'.")
                return {"success": False, "message": "Failed to generate the daily briefing. Please try again later."}
        except Exception as e:
            logger.error(f"Unexpected error during new daily briefing generation for user '{user_id_context or 'unknown'}': {e}", exc_info=True)
            return {"success": False, "message": f"An unexpected error occurred: {str(e)}"}

    async def _call_logos_llm(self, llm_config: LLMConfig, prompt_text: Optional[str] = None, llm_messages_for_synthesis: Optional[List[Dict[str,Any]]] = None) -> str:
         if not llm_config or not llm_config.get('url'):
             logger.error(f"LLM call attempted but configuration (URL) is missing for role requiring LLM.")
             raise ValueError("LLM configuration (URL) is missing for an internal LogosCore operation.")
         
         if not prompt_text and not llm_messages_for_synthesis:
             logger.error("LLM call attempted with no prompt_text and no llm_messages_for_synthesis.")
             raise ValueError("Either prompt_text or llm_messages_for_synthesis must be provided for LLM call.")

         api_url = f"{llm_config['url']}/chat/completions"
         headers = {"Content-Type": "application/json"}
         api_key = llm_config.get('api_key')
         if api_key and api_key.lower() not in ['lm-studio', 'ollama', '']: headers["Authorization"] = f"Bearer {api_key}"
         
         try: max_tokens_val = int(llm_config.get('max_tokens', 1024))
         except (ValueError, TypeError): max_tokens_val = 1024; logger.warning(f"Invalid max_tokens for Logos LLM, using {max_tokens_val}.")
         
         messages_to_send = []
         if llm_messages_for_synthesis:
             messages_to_send = llm_messages_for_synthesis
         elif prompt_text: # Fallback to simple user prompt if full messages not provided
             messages_to_send = [{"role": "user", "content": prompt_text}]

         payload: Dict[str, Any] = {
             "model": llm_config.get('model'), 
             "messages": messages_to_send, 
             "temperature": llm_config.get('temperature', 0.1), 
             "max_tokens": max_tokens_val
            }
         if not payload.get('model'): del payload['model']
         
         llm_name_for_log = llm_config.get('model', 'Logos LLM (role-specific)')
         logger.debug(f"Calling LLM '{llm_name_for_log}' at {api_url} for internal task. Prompt length: {len(json.dumps(payload['messages']))}")
         
         try:
             timeout_config = llm_config.get('timeout', 30)
             try: timeout_seconds = float(timeout_config)
             except(ValueError, TypeError): timeout_seconds = 30.0; logger.warning(f"Invalid Logos LLM timeout '{timeout_config}', defaulting to {timeout_seconds}s.")
             
             response = await self.http_client.post(api_url, headers=headers, json=payload, timeout=timeout_seconds)
             response.raise_for_status()
             result_json = response.json()
             
             if result_json.get("choices") and len(result_json["choices"]) > 0:
                 if message := result_json["choices"][0].get("message"):
                     if llm_response_content := message.get("content"):
                         if isinstance(llm_response_content, str):
                             logger.debug(f"LLM '{llm_name_for_log}' raw response: {llm_response_content[:100]}...")
                             return llm_response_content.strip()
             logger.warning(f"Unexpected LLM response format from '{llm_name_for_log}': {result_json}")
             return f"[Received unexpected response format from {llm_name_for_log}]"
         except httpx.TimeoutException as e: logger.error(f"Timeout calling LLM '{llm_name_for_log}' for internal task: {e}"); raise ConnectionError(f"Timeout connecting to LLM '{llm_name_for_log}': {e}") from e
         except httpx.RequestError as e: logger.error(f"HTTP request failed calling LLM '{llm_name_for_log}' for internal task: {e}"); raise ConnectionError(f"Failed to connect to LLM '{llm_name_for_log}': {e}") from e
         except httpx.HTTPStatusError as e: logger.error(f"LLM '{llm_name_for_log}' error ({e.response.status_code}) for internal task: {e.response.text[:500]}"); raise ValueError(f"LLM '{llm_name_for_log}' API error ({e.response.status_code}): {e.response.text[:200]}") from e
         except json.JSONDecodeError as e: logger.error(f"Failed to decode JSON response from LLM '{llm_name_for_log}'. Response: {response.text[:500] if 'response' in locals() else 'N/A'}. Error: {e}"); raise ValueError(f"Invalid JSON response from LLM '{llm_name_for_log}': {e}") 
         except Exception as e: logger.error(f"Error processing response from LLM '{llm_name_for_log}' for internal task: {e}", exc_info=True); raise RuntimeError(f"Failed to process response from LLM '{llm_name_for_log}': {e}") from e

    async def query_wolfram_alpha(self, query: str) -> Dict[str, Any]:
        if not self.config.ENABLE_WOLFRAM_ALPHA or not self.wolfram_alpha_config:
            return {"success": False, "message": "Wolfram Alpha service is not available or not configured.", "raw_response": None}
        logger.info(f"Querying Wolfram Alpha with: '{query[:100]}...'")
        encoded_query = urllib.parse.quote_plus(query)
        pod_ids_to_include: List[str] = []; primary_pods_titles: List[str] = []
        query_lower = query.lower()
        if "time in" in query_lower or "current time" in query_lower: pod_ids_to_include = ["CurrentTimeInLocation:CurrentTime", "Input"]; primary_pods_titles = ["Current time"]
        elif "weather in" in query_lower or "weather for" in query_lower: pod_ids_to_include = ["InstantaneousWeather:WeatherData", "WeatherForecast:WeatherData", "CurrentLocationWeather:WeatherData", "LatestRecordedWeather:WeatherData", "Input"]; primary_pods_titles = ["Instantaneous weather", "Weather forecast", "Current location weather", "Latest recorded weather"]
        else: pod_ids_to_include = ["Result", "DecimalApproximation", "Plot", "Definition:WordData", "WikipediaSummary:Pod", "BasicInformation:PeopleData", "Input"]; primary_pods_titles = ["Result", "Decimal approximation", "Definition", "Wikipedia summary", "Basic information"]
        pod_query_string = "&includepodid=" + "&includepodid=".join(pod_ids_to_include) if pod_ids_to_include else ""
        api_url = (f"{self.wolfram_alpha_config['api_url']}?appid={self.wolfram_alpha_config['app_id']}&input={encoded_query}&output=json{pod_query_string}&format=plaintext")
        logger.debug(f"Wolfram Alpha API URL: {api_url}")
        try:
            timeout_val = self.wolfram_alpha_config.get('timeout', 20)
            response = await self.http_client.get(api_url, timeout=float(timeout_val))
            response.raise_for_status(); wa_result_json = response.json()
            if logger.isEnabledFor(logging.DEBUG): logger.debug(f"Wolfram Alpha FULL JSON response for query '{query}': {json.dumps(wa_result_json, indent=2)}")
            extracted_answer_text: Optional[str] = None; query_result_data = wa_result_json.get('queryresult', {})
            if isinstance(query_result_data, dict) and query_result_data.get('success'):
                 pods = query_result_data.get('pods', [])
                 if isinstance(pods, list):
                     for target_title in primary_pods_titles:
                         for pod in pods:
                              if isinstance(pod, dict) and pod.get('title', '').lower() == target_title.lower() and not pod.get('error', False):
                                  subpods = pod.get('subpods', [])
                                  if isinstance(subpods, list):
                                      for subpod in subpods:
                                           if isinstance(subpod, dict) and subpod.get('plaintext'): extracted_answer_text = subpod['plaintext'].strip(); logger.debug(f"Extracted answer from WA pod '{pod.get('title')}': {extracted_answer_text[:100]}..."); break
                                  if extracted_answer_text: break
                         if extracted_answer_text: break
                     if not extracted_answer_text and pods:
                         logger.debug("No answer from primary WA pods, checking fallback pods...")
                         for pod in pods:
                             if isinstance(pod, dict) and pod.get('id', '').lower() != 'input' and not pod.get('error', False):
                                 subpods = pod.get('subpods', [])
                                 if isinstance(subpods, list):
                                     for subpod in subpods:
                                         if isinstance(subpod, dict) and subpod.get('plaintext'): extracted_answer_text = subpod['plaintext'].strip(); logger.debug(f"Extracted answer from WA fallback pod '{pod.get('title')}': {extracted_answer_text[:100]}..."); break
                                 if extracted_answer_text: break
            final_message_for_tool: str; wa_call_successful_flag = False
            if extracted_answer_text: final_message_for_tool = extracted_answer_text; wa_call_successful_flag = True
            elif isinstance(query_result_data, dict):
                error_info = query_result_data.get('error'); didyoumeans = query_result_data.get('didyoumeans'); tips = query_result_data.get('tips')
                if error_info and isinstance(error_info, dict): final_message_for_tool = f"Wolfram Alpha API error ({error_info.get('code')}): {error_info.get('msg')}"
                elif didyoumeans: suggestions = [m.get('val') for m in (didyoumeans if isinstance(didyoumeans, list) else [didyoumeans] if isinstance(didyoumeans, dict) else []) if isinstance(m, dict) and m.get('val')]; final_message_for_tool = f"Did you mean: {', '.join(filter(None, suggestions))}?" if suggestions else "Wolfram Alpha could not interpret the query and had no suggestions."
                elif tips: tip_text = (tips[0].get('text', '') if isinstance(tips, list) and tips and isinstance(tips[0], dict) else tips.get('text', '') if isinstance(tips, dict) else ''); final_message_for_tool = f"Tip from Wolfram Alpha: {tip_text}" if tip_text else "Wolfram Alpha provided no specific answer or tips."
                elif not query_result_data.get('success', True): final_message_for_tool = "Wolfram Alpha indicated it could not successfully process the query."
                else: final_message_for_tool = "Wolfram Alpha did not provide a specific answer for the requested format/pods."
            else: final_message_for_tool = "Invalid or empty response structure from Wolfram Alpha."
            logger.info(f"Wolfram Alpha final processed result for '{query[:50]}...': {final_message_for_tool[:200]}...")
            return {"success": wa_call_successful_flag, "result": final_message_for_tool, "message": final_message_for_tool, "raw_response": wa_result_json}
        except httpx.TimeoutException as e: logger.warning(f"Timeout querying Wolfram Alpha for '{query[:50]}...': {e}"); return {"success": False, "message": "Timeout connecting to Wolfram Alpha service.", "raw_response": None}
        except httpx.RequestError as e: logger.warning(f"HTTP request failed querying Wolfram Alpha for '{query[:50]}...': {e}"); return {"success": False, "message": f"Connection error querying Wolfram Alpha: {str(e)}", "raw_response": None}
        except json.JSONDecodeError as e: logger.error(f"Failed to decode Wolfram Alpha JSON for '{query[:50]}...'. Response: {response.text[:500] if 'response' in locals() else 'N/A'}. Error: {e}"); return {"success": False, "message": f"Invalid JSON response from Wolfram Alpha: {str(e)}", "raw_response": None}
        except Exception as e: logger.error(f"Error processing Wolfram Alpha response for '{query[:50]}...': {e}", exc_info=True); return {"success": False, "message": f"Error processing Wolfram Alpha data: {str(e)}", "raw_response": None}

    async def verify_world_fact(self, fact_entry: MemoryEntry) -> Dict[str, Any]:
        fact_id = fact_entry.get('id', 'unknown_id')
        original_fact_statement = fact_entry.get('content')

        if not original_fact_statement:
            return {"status": "unverifiable", "reason": "Original fact content is empty."}

        logger.info(f"LogosCore: Verifying world fact ID {fact_id}: '{original_fact_statement[:100]}...'")

        if not self.config.ENABLE_WEB_SEARCH or not self.web_search_service:
            logger.warning("Knowledge Upkeep: Web search is disabled or not configured. Cannot verify fact.")
            return {"status": "unverifiable", "reason": "Web search capability unavailable."}

        if not self.knowledge_upkeep_llm_config or not self.knowledge_upkeep_llm_config.get('url'):
            upkeep_llm_role = self.config.ETHOS.get('knowledge_upkeep_llm_role', 'LOGOS_TECHNE')
            logger.error(f"Knowledge Upkeep: LLM for role '{upkeep_llm_role}' is not configured with a URL. Cannot verify fact with LLM.")
            return {"status": "unverifiable", "reason": f"LLM for role {upkeep_llm_role} not configured."}

        search_query = f"Verify fact: {original_fact_statement}"
        if len(search_query) > 250: 
            search_query = f"Current information regarding: {original_fact_statement[:200]}"
        
        logger.debug(f"Knowledge Upkeep: Web search query for fact ID {fact_id}: '{search_query}'")
        search_results = await self.web_search_service.perform_search(search_query)

        if not search_results:
            logger.warning(f"Knowledge Upkeep: No web search results for fact ID {fact_id} query '{search_query}'.")
            return {"status": "unverifiable", "reason": "No web search results found for verification query."}

        search_context_parts = []
        for i, res in enumerate(search_results[:3]): 
            title = res.get('title', 'N/A')
            snippet = res.get('snippet', 'N/A')
            link = res.get('link', '#')
            search_context_parts.append(f"Source {i+1} (Title: {title}, URL: {link}):\n{snippet}")
        search_context = "\n\n---\n\n".join(search_context_parts)


        verification_prompt_system = (
            f"You are an AI assistant specialized in fact verification. Your task is to analyze the 'Original Stored Fact' "
            f"against the provided 'Current Web Search Snippets'. Determine if the original fact remains accurate, "
            f"if it has been updated or superseded by new information, or if the snippets are insufficient for a clear judgment. "
            f"If the fact is updated, you MUST provide the new, complete, and corrected factual statement. "
            f"If it's still accurate, confirm this. If uncertain, explain why."
        )
        verification_prompt_user = f"""
Original Stored Fact:
"{original_fact_statement}"

Current Web Search Snippets:
---
{search_context}
---

Based *only* on the information in the 'Current Web Search Snippets', perform the following analysis:
1.  Assessment: Is the 'Original Stored Fact' still accurate? 
    Choose ONE: ACCURATE, UPDATED, or UNCERTAIN.
2.  Corrected Statement: If your assessment is UPDATED, provide the full, corrected factual statement based on the snippets. If not UPDATED, this should be null.
3.  Reasoning: Briefly explain your assessment. If UNCERTAIN, specify what information is missing or ambiguous.

Respond strictly in the following JSON format:
{{
  "assessment": "ACCURATE | UPDATED | UNCERTAIN",
  "corrected_statement": "The full corrected factual statement if assessment is UPDATED, otherwise null.",
  "reasoning": "Your brief explanation."
}}
"""
        llm_messages_for_verification = [
            {"role": "system", "content": verification_prompt_system},
            {"role": "user", "content": verification_prompt_user}
        ]

        try:
            logger.debug(f"Knowledge Upkeep: Calling LLM '{self.knowledge_upkeep_llm_config.get('model')}' for fact verification ID {fact_id}.")
            
            api_url = f"{self.knowledge_upkeep_llm_config['url']}/chat/completions"
            headers = {"Content-Type": "application/json"}
            api_key = self.knowledge_upkeep_llm_config.get('api_key')
            if api_key and api_key.lower() not in ['lm-studio', 'ollama', '']:
                headers["Authorization"] = f"Bearer {api_key}"

            payload: Dict[str, Any] = {
                "model": self.knowledge_upkeep_llm_config.get('model'),
                "messages": llm_messages_for_verification,
                "temperature": self.knowledge_upkeep_llm_config.get('temperature', 0.1), 
                "max_tokens": self.knowledge_upkeep_llm_config.get('max_tokens', 512) 
            }
            if not payload.get('model'): del payload['model']

            timeout_val = float(self.knowledge_upkeep_llm_config.get('timeout', 60))
            response = await self.http_client.post(api_url, headers=headers, json=payload, timeout=timeout_val)
            response.raise_for_status()
            llm_response_json = response.json()

            if llm_response_json.get("choices") and len(llm_response_json["choices"]) > 0:
                message_content_str = llm_response_json["choices"][0].get("message", {}).get("content")
                if message_content_str:
                    cleaned_llm_response_str = re.sub(r"```json\s*|\s*```", "", message_content_str).strip()
                    try:
                        analysis_result = json.loads(cleaned_llm_response_str)
                        assessment = analysis_result.get("assessment", "").upper()
                        corrected_statement = analysis_result.get("corrected_statement")
                        reasoning = analysis_result.get("reasoning", "")

                        if assessment == "ACCURATE":
                            return {"status": "accurate", "reason": reasoning}
                        elif assessment == "UPDATED" and corrected_statement:
                            return {"status": "updated", "new_fact_statement": corrected_statement, "confidence": 0.9, "reason": reasoning}
                        elif assessment == "UNCERTAIN":
                            return {"status": "unverifiable", "reason": f"LLM uncertain: {reasoning}"}
                        else:
                            logger.warning(f"Knowledge Upkeep: LLM returned unexpected assessment '{assessment}' for fact ID {fact_id}. Raw content: {message_content_str}")
                            return {"status": "unverifiable", "reason": f"LLM returned unexpected assessment: {assessment}. Reasoning: {reasoning}. Raw: {message_content_str[:100]}"}
                    except json.JSONDecodeError:
                        logger.error(f"Knowledge Upkeep: Failed to parse JSON response from LLM for fact ID {fact_id}. Raw content: {message_content_str}")
                        if "ACCURATE" in message_content_str.upper():
                             return {"status": "accurate", "reason": "LLM response indicated accuracy, but JSON parsing failed."}
                        return {"status": "unverifiable", "reason": f"LLM response was not valid JSON. Content: {message_content_str[:100]}"}
            
            logger.error(f"Knowledge Upkeep: LLM call for fact verification ID {fact_id} did not yield usable content. Full response: {llm_response_json}")
            return {"status": "unverifiable", "reason": "LLM response structure was invalid or empty."}

        except httpx.HTTPStatusError as e:
            logger.error(f"Knowledge Upkeep: HTTP error {e.response.status_code} during LLM fact verification for ID {fact_id}: {e.response.text[:200]}")
            return {"status": "unverifiable", "reason": f"LLM API error ({e.response.status_code})"}
        except Exception as e:
            logger.error(f"Knowledge Upkeep: Unexpected error during LLM fact verification for ID {fact_id}: {e}", exc_info=True)
            return {"status": "unverifiable", "reason": f"Unexpected error during verification: {str(e)}"}


    async def close(self):
        await self.http_client.aclose()
        if self.web_search_service:
            await self.web_search_service.close()
        logger.info("LogosCore resources (HTTP client, WebSearchService) closed.")