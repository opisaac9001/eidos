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
    ZoneInfo = None

from eidos_agent.core.config import Config, LLMConfig, WolframAlphaConfig, NewsApiConfig
# EthosCore imports are already updated to persona_logic in this file
from eidos_agent.persona_logic.ethos_core.core import EthosCore
from eidos_agent.services.web_search import WebSearchService
# Removed HomeAssistantService import
from eidos_agent.services.openweathermap import OpenWeatherMapService
from eidos_agent.utils.document_parser import parse_document, SUPPORTED_EXTENSIONS
from eidos_agent.utils.text_splitter import chunk_text_by_char
from eidos_agent.utils.logger import get_logger
from eidos_agent.persona_logic.ethos_core.memory_storage import MemoryEntry
from eidos_agent.utils.prompt_loader import load_system_prompt

from eidos_agent.features.simulation.module import initiate_simulated_interaction, send_message_to_simulated_npc, end_simulated_interaction

logger = get_logger(__name__)

class LogosCore:
    def __init__(self, config: Config, ethos_core: EthosCore, owm_service: Optional[OpenWeatherMapService] = None): # Removed ha_service
        self.config = config
        self.ethos_core = ethos_core
        # self.ha_service = ha_service # Removed
        self.owm_service = owm_service

        self.logos_techne_config: Optional[LLMConfig] = config.get_llm_config('LOGOS_TECHNE')
        self.logos_vision_config: Optional[LLMConfig] = config.get_llm_config('LOGOS_VISION_CONTEXT') # For image description fallback
        self.logos_research_config: Optional[LLMConfig] = config.get_llm_config('LOGOS_DEEP_RESEARCH')
        
        knowledge_upkeep_llm_role = config.ETHOS.get('knowledge_upkeep_llm_role', 'LOGOS_TECHNE')
        self.knowledge_upkeep_llm_config: Optional[LLMConfig] = config.get_llm_config(knowledge_upkeep_llm_role)

        timeout = 60.0; all_llm_timeouts = []
        for role_key in Config.LLM.keys():
            if role_config := config.get_llm_config(role_key): # type: ignore
                if timeout_str := role_config.get('timeout'):
                    try: all_llm_timeouts.append(float(timeout_str))
                    except ValueError: logger.warning(f"Invalid timeout for LLM role '{role_key}': {timeout_str}")
        if all_llm_timeouts: timeout = max(all_llm_timeouts)
        self.http_client = httpx.AsyncClient(timeout=timeout + 10.0)

        self.web_search_service: Optional[WebSearchService] = None
        if config.ENABLE_WEB_SEARCH:
             if brave_config := config.get_brave_search_config():
                 if brave_config.get('api_key'): self.web_search_service = WebSearchService(config)
                 else: logger.error("Brave Search API key missing. Web search disabled.")
             else: logger.error("Brave Search config missing. Web search disabled.")
        else: logger.info("Web Search disabled in LogosCore.")

        self.wolfram_alpha_config: Optional[WolframAlphaConfig] = config.get_wolfram_alpha_config()
        if self.config.ENABLE_WOLFRAM_ALPHA and not self.wolfram_alpha_config:
             logger.warning("Wolfram Alpha enabled but APP_ID missing. Math/Weather/Time tools may fail.")

        self.news_config: Optional[NewsApiConfig] = config.get_news_api_config()
        if self.news_config and self.news_config.get('enabled', False):
            if not self.news_config.get('api_key'): logger.warning("News API enabled but key missing. Briefing news disabled.")
            else: logger.info("News API enabled for LogosCore (Daily Briefing).")
        else: logger.info("News API disabled or not configured in LogosCore.")

        logger.info("LogosCore initialized.")
        # Removed HomeAssistantService check log
        if self.owm_service and self.owm_service.is_available: logger.info("LogosCore has OpenWeatherMapService.")
        else: logger.warning("LogosCore does NOT have OpenWeatherMapService.")

    async def close(self):
        if self.http_client and not self.http_client.is_closed: await self.http_client.aclose()
        if self.web_search_service: await self.web_search_service.close()
        # No ha_service.close() needed
        logger.info("LogosCore resources closed.")

    async def initialize_services(self):
        logger.info("LogosCore initialize_services called.")
        # No ha_service.connect() needed

    async def process_uploaded_document(self, file_content: bytes, filename: str, user_id: Optional[str] = None) -> Dict[str, Any]:
         logger.info(f"LogosCore processing doc: '{filename}' ({len(file_content)} bytes) for user '{user_id or 'unknown'}'.")
         file_ext = Path(filename).suffix.lower()
         if file_ext not in SUPPORTED_EXTENSIONS: return {"success": False, "message": f"Unsupported file type: '{file_ext}'."}
         try:
             text = await parse_document(filename, file_content)
             if not text or not text.strip(): return {"success": False, "message": f"No text extracted from '{filename}'."}
             return {"success": True, "message": f"Extracted text from '{filename}'.", "extracted_text": text}
         except ValueError as e: return {"success": False, "message": f"Error processing '{filename}': {e}"}
         except ImportError as e: return {"success": False, "message": f"Cannot process '{filename}': Missing library '{e.name}'."}
         except Exception as e: logger.error(f"Error processing doc '{filename}': {e}", exc_info=True); return {"success": False, "message": "System error processing document."}

    async def add_document_to_rag(self, extracted_text: str, filename: str = "uploaded_document", user_id: Optional[str] = None, doc_id: Optional[str] = None):
         if not extracted_text or not extracted_text.strip(): return {"success": False, "message": "No text to add to RAG."}
         final_doc_id = doc_id or str(uuid.uuid4())
         logger.info(f"LogosCore adding doc '{filename}' (ID: {final_doc_id}) to RAG for user '{user_id or 'unknown'}'.")
         try:
             chunk_size = self.config.ETHOS.get('text_chunk_size', 1000)
             chunk_overlap = self.config.ETHOS.get('text_chunk_overlap', 150)
             chunks = chunk_text_by_char(extracted_text, chunk_size, chunk_overlap)
             if not chunks: return {"success": False, "message": f"Failed to split '{filename}' into chunks."}
             await self.ethos_core.add_document_chunks(final_doc_id, filename, chunks)
             return {"success": True, "message": f"Stored '{filename}' ({len(chunks)} chunks) for RAG.", "doc_id": final_doc_id, "num_chunks": len(chunks)}
         except Exception as e: logger.error(f"Error adding doc '{filename}' to RAG: {e}", exc_info=True); return {"success": False, "message": "System error adding document to RAG."}

    async def execute_get_time(self, location: Optional[str] = None) -> str: # From broken (more robust)
        try:
            final_time_str = ""; utc_now = datetime.now(timezone.utc); utc_fallback = utc_now.strftime('%A, %B %d, %Y at %I:%M:%S %p %Z (%z)')
            if location:
                target_tz_obj = None
                if ZoneInfo:
                    try: target_tz_obj = ZoneInfo(location); final_time_str = f"The current time in {location} is {datetime.now(target_tz_obj).strftime('%A, %B %d, %Y at %I:%M:%S %p %Z (%z)')}."
                    except Exception: logger.debug(f"Could not interpret '{location}' as IANA timezone.")
                if not final_time_str and self.config.ENABLE_WOLFRAM_ALPHA and self.wolfram_alpha_config:
                    wa_res = await self.query_wolfram_alpha(f"current time in {location}")
                    if wa_res.get('success') and wa_res.get('result'): final_time_str = f"For {location}, Wolfram Alpha reports: {wa_res['result']}."
                if not final_time_str: final_time_str = f"I couldn't determine local time for '{location}'. UTC is {utc_fallback}."
            else: final_time_str = f"Current UTC is {utc_fallback}. Specify a location for local time."
            return final_time_str
        except Exception as e: logger.error(f"Error in execute_get_time: {e}", exc_info=True); return json.dumps({"error": f"Error determining time: {e}"})

    async def execute_describe_image(self, image_data_b64: str, prompt_from_llm: str) -> str: # Kept for fallback
        logger.info(f"LogosCore: Describing image. User prompt: '{prompt_from_llm[:50]}...'")
        if not self.config.ENABLE_VISION_PROCESSING: return json.dumps({"error": "Vision processing disabled."})
        
        # This method should use LOGOS_VISION_CONTEXT if the main Pathos LLM is not multimodal.
        # If Pathos LLM is multimodal, this method might not be called by PathosInterface.
        vision_llm_config = self.logos_vision_config # Use the dedicated vision LLM config
        if not vision_llm_config or not vision_llm_config.get('url'):
            return json.dumps({"error": "LOGOS_VISION_CONTEXT LLM not configured."})

        messages_payload = [{"role": "user", "content": [{"type": "text", "text": prompt_from_llm},{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data_b64}"}}]}]
        
        # Use the _call_logos_llm helper, ensuring it uses the vision_llm_config
        description = await self._call_logos_llm(vision_llm_config, llm_messages_for_synthesis=messages_payload)
        
        if description and not description.startswith("["):
            logger.info(f"Vision LLM provided description: {description[:100]}...")
            return description
        else:
            logger.warning(f"Vision LLM description failed or returned error: {description}")
            return json.dumps({"error": description or "Failed to get description from vision model."})

    async def execute_web_search(self, query: str) -> Optional[List[Dict[str, str]]]: # From broken
        if not self.config.ENABLE_WEB_SEARCH or not self.web_search_service: return None
        if not query or not isinstance(query, str) or not query.strip(): return []
        return await self.web_search_service.perform_search(query)

    async def execute_math_calculation(self, expression: str) -> str: # From broken
        if not self.config.ENABLE_WOLFRAM_ALPHA or not self.wolfram_alpha_config: return json.dumps({"error": "Calculation service (Wolfram Alpha) unavailable."})
        if not expression or not isinstance(expression, str) or not expression.strip(): return json.dumps({"error": "No valid expression provided."})
        wa_res = await self.query_wolfram_alpha(expression)
        if wa_res.get('success') and wa_res.get('result'):
            cleaned = " | ".join(line.strip() for line in wa_res['result'].splitlines() if line.strip())
            return cleaned if cleaned else "[Calculation resulted in empty response]"
        return json.dumps({"error": wa_res.get('message', 'Calculation failed.')})

    async def execute_get_weather(self, location: str, user_id_context: Optional[str] = None) -> Dict[str, Any]: # From broken (more robust)
        if not location or not location.strip(): return {"success": False, "error": "No valid location provided.", "location": location}
        if self.owm_service and self.owm_service.is_available:
            owm_res = await self.owm_service.get_current_weather(location)
            if owm_res.get("success"):
                if self.ethos_core and user_id_context and user_id_context not in ["system_briefing", "unknown_user", "api_guest_user", None, "system_oneiros", "system_document", "world_knowledge_store", "system_reflection"]:
                    if iana_tz := owm_res.get("weather_data", {}).get("iana_timezone"):
                        existing_tz = await self.ethos_core.get_user_fact('derived_iana_timezone', user_id_context)
                        should_store = True
                        if existing_tz and (content := existing_tz.get('content')):
                            try:
                                if json.loads(content).get('value') == iana_tz: should_store = False
                            except json.JSONDecodeError: pass
                        if should_store: await self.execute_store_user_fact("derived_iana_timezone", iana_tz, f"IANA timezone from OWM for '{location}'.", user_id_context)
                return owm_res
        # Removed Home Assistant weather fetching block
        if not self.config.ENABLE_WOLFRAM_ALPHA or not self.wolfram_alpha_config: return {"success": False, "error": "No weather service available (excluding HA).", "location": location} # Modified error message slightly
        wa_res = await self.query_wolfram_alpha(f"weather in {location}"); data = {"location": location}; success = False; err_msg = None
        if wa_res.get('success') and (raw_resp := wa_res.get('raw_response')):
            query_res = raw_resp.get('queryresult', {})
            if isinstance(query_res, dict) and query_res.get('success'):
                pods = query_res.get('pods', [])
                if isinstance(pods, list):
                    for pod in pods:
                        if isinstance(pod, dict) and pod.get('id') in ["InstantaneousWeather:WeatherData", "CurrentLocationWeather:WeatherData", "WeatherForecast:WeatherData", "LatestRecordedWeather:WeatherData"] and not pod.get('error', False):
                            if subpods := pod.get('subpods', []):
                                if isinstance(subpods, list):
                                    for subpod in subpods:
                                        if isinstance(subpod, dict) and (text := subpod.get('plaintext')):
                                            for line in text.strip().split('\n'):
                                                parts = line.split('|', 1)
                                                if len(parts) == 2:
                                                    key, val = parts[0].strip().lower().replace(' ', '_'), parts[1].strip()
                                                    if key == 'temperature':
                                                        if m := re.match(r'(-?\d+(\.\d+)?)\s*(°?[FC])?', val, re.I): data['temperature'], data['unit'] = float(m.group(1)), m.group(3) or '°'
                                                    elif key == 'conditions': data['description'] = val
                                                    elif key == 'relative_humidity': data['humidity'] = val
                                                    elif key == 'wind_speed': data['wind_speed'] = val
                                            if 'temperature' in data or 'description' in data: success = True; break
                                    if success: break
                    if not success:
                        for pod_alt in pods:
                            if isinstance(pod_alt, dict) and pod_alt.get('id') == 'Result' and not pod_alt.get('error', False):
                                if subpods_alt := pod_alt.get('subpods', []):
                                    if isinstance(subpods_alt, list) and subpods_alt and isinstance(subpods_alt[0], dict) and (fb_text := subpods_alt[0].get('plaintext')):
                                        data['description'] = fb_text.strip(); success = True; break
                    if not success: err_msg = "Specific weather pods not found in Wolfram Alpha response."
                else: err_msg = "Wolfram Alpha response has invalid 'pods' format."
            else: err_msg = wa_res.get('message', 'Wolfram Alpha weather query failed.')
        else: err_msg = wa_res.get('message', "Failed to get successful response from Wolfram Alpha.")
        if success: data.setdefault('source', "Wolfram Alpha"); return {"success": True, "weather_data": data}
        else: return {"success": False, "error": err_msg or "Unknown error processing Wolfram Alpha weather.", "location": location, "message": wa_res.get('message')}

    async def execute_store_user_fact(self, attribute_name: str, attribute_value: str, user_statement_context: str, user_id: str) -> str: # From broken
        norm_attr_name = attribute_name.lower().replace(" ", "_").strip()
        if not norm_attr_name: return json.dumps({"error": "Attribute name cannot be empty."})
        content = {"attribute": norm_attr_name, "value": attribute_value, "original_user_statement": user_statement_context, "stored_by_tool_timestamp": datetime.now(timezone.utc).isoformat()}
        entry_data = {"type": "user_fact", "content": json.dumps(content), "salience": 1.5, "metadata": {"user_id": user_id, "fact_attribute_key": norm_attr_name, "source": "pathos_tool_store_user_fact"}}
        try: await self.ethos_core.add_memory_entry(entry_data, user_id_context=user_id); return json.dumps({"status": "success", "message": f"Noted: your {attribute_name} is {attribute_value}."})
        except Exception as e: logger.error(f"Error storing user fact for '{user_id}': {e}", exc_info=True); return json.dumps({"error": f"Failed to store user fact: {e}"})

    async def execute_store_world_fact(self, fact_statement: str, source_description: str, topic_tags: Optional[List[str]] = None, confidence_level: float = 0.8) -> str: # From broken
        if topic_tags is None: topic_tags = []
        try: confidence = max(0.0, min(1.0, float(confidence_level)))
        except (ValueError, TypeError): confidence = 0.8
        tags = sorted(list(set(tag.lower().strip() for tag in topic_tags if isinstance(tag, str) and tag.strip())))
        entry_data = {"type": "world_knowledge", "content": fact_statement, "salience": 0.7 + (confidence * 0.3), "metadata": {"stored_by_user_id": "system_or_current_user", "source_description": source_description, "topic_tags": tags, "confidence_level": confidence, "stored_by_tool_timestamp": datetime.now(timezone.utc).isoformat()}}
        try: await self.ethos_core.add_memory_entry(entry_data, user_id_context="world_knowledge_store"); return json.dumps({"status": "success", "message": f"Noted fact: '{fact_statement[:70]}...'."})
        except Exception as e: logger.error(f"Error storing world fact: {e}", exc_info=True); return json.dumps({"error": f"Failed to store world fact: {e}"})

    async def execute_deep_research(self, research_query: str, num_searches_to_perform: int = 3) -> str: # From broken
        if not self.config.ENABLE_WEB_SEARCH or not self.web_search_service: return json.dumps({"error": "Web search unavailable for deep research."})
        llm_config = self.logos_research_config
        if not llm_config or not llm_config.get('url'): return json.dumps({"error": "Deep research LLM (LOGOS_DEEP_RESEARCH) not configured."})
        queries = [research_query]
        if num_searches_to_perform > 1: queries.append(f"benefits and drawbacks of {research_query}")
        if num_searches_to_perform > 2: queries.append(f"key aspects of {research_query}")
        if num_searches_to_perform > 3: queries.append(f"future trends for {research_query}")
        queries = queries[:num_searches_to_perform]; aggregated_text = ""; count = 0
        for i, sq in enumerate(queries):
            if results := await self.web_search_service.perform_search(sq):
                for res in results: aggregated_text += f"--- Result {count+1} (Query: '{sq}') ---\nTitle: {res.get('title', 'N/A')}\nLink: {res.get('link', '#')}\nSnippet: {res.get('snippet', '')[:700]}\n\n"; count +=1
            await asyncio.sleep(0.3)
        if not aggregated_text: return json.dumps({"error": "No web search results for deep research query."})
        max_input_chars = ((llm_config.get('max_tokens', 4096) - 1024) * 3)
        if len(aggregated_text) > max_input_chars: aggregated_text = aggregated_text[:max_input_chars]
        sys_prompt = load_system_prompt("deep_research_llm_system_prompt", "Synthesize provided info into a report.")
        user_prompt = f"Query: '{research_query}'\nCollected Info:\n{aggregated_text}\n\nSynthesized report:"
        try:
            report = await self._call_logos_llm(llm_config, llm_messages_for_synthesis=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}])
            if not report or report.startswith("["): return json.dumps({"error": f"LLM synthesis error: {report}"})
            return report
        except Exception as e: logger.error(f"Error in deep research synthesis: {e}", exc_info=True); return json.dumps({"error": f"Synthesis error: {e}"})

    async def execute_get_news_headlines(self) -> str: # From broken
        if not self.news_config or not self.news_config.get('enabled') or not self.news_config.get('api_key'):
            logger.warning("News API not configured or enabled for execute_get_news_headlines.") # Added logger
            return json.dumps({"error": "News service unavailable."})
        try:
            headlines = await self._fetch_news_headlines_with_details(self.news_config)
            if headlines:
                parts = ["Top News Headlines:"]
                for item in headlines:
                    title = item.get('title', 'N/A')
                    snippet_content = item.get('snippet', '')
                    # Create snippet_text separately
                    snippet_text = f" (Snippet: {snippet_content[:50]}...)" if snippet_content else ""
                    parts.append(f"- {title}{snippet_text}")
                
                logger.info(f"Successfully fetched and formatted {len(headlines)} news headlines.") # Added logger
                return "\n".join(parts)
            
            logger.info("No news headlines found by _fetch_news_headlines_with_details.") # Added logger
            return json.dumps({"status": "success", "message": "No recent news headlines found."})
        except Exception as e:
            logger.error(f"Error getting news headlines: {e}", exc_info=True)
            return json.dumps({"error": f"Error fetching news: {str(e)}"})
    async def _fetch_news_headlines_with_details(self, news_api_config: NewsApiConfig) -> List[Dict[str, str]]: # From broken
        if not news_api_config or not news_api_config.get('enabled') or not news_api_config.get('api_key'): return []
        params: Dict[str, Any] = {"api_token": news_api_config['api_key'], "locale": news_api_config.get('default_locale', 'us'), "language": news_api_config.get('default_language', 'en'), "limit": news_api_config.get('limit', 5), "snippet_len": 150}
        endpoint = f"{news_api_config['base_url'].rstrip('/')}/v1/news/top"
        if kw := news_api_config.get('search_keywords'): params['search'] = kw; endpoint = f"{news_api_config['base_url'].rstrip('/')}/v1/news/all"
        elif cat := news_api_config.get('categories'): params['categories'] = cat
        if src_ids := news_api_config.get('include_source_ids'): params['source_ids'] = src_ids; endpoint = f"{news_api_config['base_url'].rstrip('/')}/v1/news/all"
        if excl_doms := news_api_config.get('exclude_source_ids'): params['exclude_domains'] = excl_doms
        articles: List[Dict[str, str]] = []
        try:
            resp = await self.http_client.get(endpoint, params=params, timeout=float(news_api_config.get('timeout', 15)))
            resp.raise_for_status(); data = resp.json()
            for article in data.get("data", []):
                if isinstance(article, dict) and (title := article.get("title", "").strip()) and (url := article.get("url", "#").strip()):
                    articles.append({"title": title, "url": url, "snippet": (article.get("snippet", article.get("description", ""))).strip()})
            return articles
        except Exception as e: logger.error(f"Error fetching news from TheNewsAPI: {e}", exc_info=True); return []

    async def generate_daily_briefing(self, user_id_context: Optional[str] = None) -> Optional[str]: # From broken (more robust)
        now_utc = datetime.now(timezone.utc); today_date = now_utc.strftime('%Y-%m-%d')
        local_time_display = now_utc.strftime('%A, %B %d, %Y, %I:%M %p %Z')
        if self.ethos_core and user_id_context and user_id_context not in ["system_briefing", "unknown_user", "api_guest_user", None, "system_oneiros", "system_document", "world_knowledge_store", "system_reflection"]:
            local_dt = await self.ethos_core.get_local_datetime_for_user(user_id_context)
            local_time_display = local_dt.strftime('%A, %B %d, %Y, %I:%M %p %Z')
        weather_parts, news_parts = ["**Weather:**"], ["**Top News:**"]
        weather_loc = os.getenv("BRIEFING_WEATHER_LOCATION_FALLBACK", "New York, NY")
        if self.ethos_core and user_id_context and user_id_context not in ["system_briefing", "unknown_user", "api_guest_user", None, "system_oneiros", "system_document", "world_knowledge_store", "system_reflection"]:
            if loc_fact := await self.ethos_core.get_user_fact('preferred_location', user_id_context):
                if content := loc_fact.get('content'):
                    try:
                        if user_pref_loc := json.loads(content).get('value'): weather_loc = user_pref_loc
                    except json.JSONDecodeError: pass
        weather_res = await self.execute_get_weather(weather_loc, user_id_context=user_id_context)
        if weather_res.get('success') and (wd := weather_res.get('weather_data')):
            weather_parts.extend([f"- Location: {wd.get('location', weather_loc)}", f"- Conditions: {wd.get('temperature', '--')}{wd.get('unit', '')}, {wd.get('description', 'N/A')}"])
            if wd.get('humidity'): weather_parts.append(f"- Humidity: {wd.get('humidity')}")
            if wd.get('wind_speed'): weather_parts.append(f"- Wind: {wd.get('wind_speed')}")
        else: weather_parts.append(f"- Weather for {weather_loc}: {weather_res.get('error', 'Unavailable')}")
        if self.news_config and self.news_config.get('enabled'):
            if headlines := await self._fetch_news_headlines_with_details(self.news_config):
                for item in headlines:
                    snippet = item.get('snippet', ''); news_parts.append(f"- [{item['title']}]({item['url']})")
                    if snippet: news_parts.append(f"  - _{snippet[:97] + '...' if len(snippet) > 100 else snippet}_")
            else: news_parts.append("- No top headlines found.")
        else: news_parts.append("- News service disabled.")
        briefing = f"### Daily Briefing ({local_time_display})\n\n" + "\n".join(weather_parts) + "\n\n" + "\n".join(news_parts)
        await self.ethos_core.add_memory_entry({"type": "daily_briefing", "content": briefing, "metadata": {"generation_timestamp_utc": now_utc.isoformat(), "briefing_date": today_date, "briefing_format_version": "panel_v1", "generated_for_user_context": user_id_context or "system"}}, user_id_context="system_briefing")
        return briefing

    async def get_or_generate_daily_briefing(self, user_id_context: Optional[str] = None) -> Dict[str, Any]: # From broken
        if not self.ethos_core: return {"success": False, "message": "EthosCore not accessible."}
        try:
            if existing := await self.ethos_core.get_todays_briefing(): return {"success": True, "briefing_content": existing, "message": "Briefing retrieved."}
        except Exception as e: logger.error(f"Error checking existing briefing: {e}", exc_info=True)
        try:
            if new_briefing := await self.generate_daily_briefing(user_id_context=user_id_context): return {"success": True, "briefing_content": new_briefing, "message": "Briefing generated."}
            return {"success": False, "message": "Failed to generate briefing."}
        except Exception as e: logger.error(f"Error generating new briefing: {e}", exc_info=True); return {"success": False, "message": f"Error: {e}"}

    async def _call_logos_llm(self, llm_config: LLMConfig, prompt_text: Optional[str] = None, llm_messages_for_synthesis: Optional[List[Dict[str,Any]]] = None) -> str: # From broken
        if not llm_config or not llm_config.get('url'): raise ValueError("LLM config (URL) missing for LogosCore.")
        if not prompt_text and not llm_messages_for_synthesis: raise ValueError("prompt_text or llm_messages_for_synthesis required.")
        api_url = f"{llm_config['url']}/chat/completions"; response = None
        try:
            headers = {"Content-Type": "application/json"}
            if api_key := llm_config.get('api_key'):
                if api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']: headers["Authorization"] = f"Bearer {api_key}"
            max_tokens = int(llm_config.get('max_tokens', 1024))
            messages = llm_messages_for_synthesis if llm_messages_for_synthesis else [{"role": "user", "content": prompt_text}]
            payload: Dict[str, Any] = {"model": llm_config.get('model'), "messages": messages, "temperature": llm_config.get('temperature', 0.1), "max_tokens": max_tokens}
            if not payload.get('model'): del payload['model']
            timeout = float(llm_config.get('timeout', 30.0))
            response = await self.http_client.post(api_url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status(); result_json = response.json()
            if choices := result_json.get("choices"):
                if choices and isinstance(choices, list) and len(choices) > 0:
                    if message := choices[0].get("message"):
                        if content := message.get("content"):
                            if isinstance(content, str): return content.strip()
            return f"[Unexpected LLM response format from {llm_config.get('model', 'Logos LLM')}]"
        except httpx.TimeoutException as e: raise ConnectionError(f"Timeout connecting to LLM: {e}") from e
        except httpx.RequestError as e: raise ConnectionError(f"Failed to connect to LLM: {e}") from e
        except httpx.HTTPStatusError as e: raise ValueError(f"LLM API error ({e.response.status_code}): {e.response.text[:200]}") from e
        except json.JSONDecodeError as e: response_text = response.text[:500] if response and hasattr(response, 'text') else 'N/A'; raise ValueError(f"Invalid JSON from LLM: {e}. Response: {response_text}") from e
        except Exception as e: logger.error(f"Error processing LLM response: {e}", exc_info=True); raise RuntimeError(f"Failed to process LLM response: {e}") from e

    async def query_wolfram_alpha(self, query: str) -> Dict[str, Any]: # From broken (more robust parsing)
        if not self.config.ENABLE_WOLFRAM_ALPHA or not self.wolfram_alpha_config: return {"success": False, "message": "Wolfram Alpha unavailable."}
        encoded_query = urllib.parse.quote_plus(query); pod_ids, primary_titles = [], []
        if "time in" in query.lower() or "current time" in query.lower(): pod_ids, primary_titles = ["CurrentTimeInLocation:CurrentTime", "Input"], ["Current time"]
        elif "weather in" in query.lower() or "weather for" in query.lower(): pod_ids = ["InstantaneousWeather:WeatherData", "WeatherForecast:WeatherData", "CurrentLocationWeather:WeatherData", "LatestRecordedWeather:WeatherData", "Input"]; primary_titles = ["Instantaneous weather", "Weather forecast", "Current location weather", "Latest recorded weather"]
        else: pod_ids, primary_titles = ["Result", "DecimalApproximation", "Plot", "Definition:WordData", "WikipediaSummary:Pod", "BasicInformation:PeopleData", "Input"], ["Result", "Decimal approximation", "Definition", "Wikipedia summary", "Basic information"]
        pod_q_str = "&includepodid=" + "&includepodid=".join(pod_ids) if pod_ids else ""
        api_url = f"{self.wolfram_alpha_config['api_url']}?appid={self.wolfram_alpha_config['app_id']}&input={encoded_query}&output=json{pod_q_str}&format=plaintext"
        try:
            resp = await self.http_client.get(api_url, timeout=float(self.wolfram_alpha_config.get('timeout', 20)))
            resp.raise_for_status(); wa_json = resp.json()
            answer_text: Optional[str] = None; query_res_data = wa_json.get('queryresult', {})
            if isinstance(query_res_data, dict) and query_res_data.get('success'):
                pods = query_res_data.get('pods', [])
                if isinstance(pods, list):
                    for title in primary_titles:
                        for pod in pods:
                            if isinstance(pod, dict) and pod.get('title', '').lower() == title.lower() and not pod.get('error', False):
                                if subpods := pod.get('subpods', []):
                                    if isinstance(subpods, list):
                                        for subpod in subpods:
                                            if isinstance(subpod, dict) and (pt := subpod.get('plaintext')): answer_text = pt.strip(); break
                                if answer_text: break
                        if answer_text: break
                    if not answer_text and pods:
                        for pod in pods:
                            if isinstance(pod, dict) and pod.get('id', '').lower() != 'input' and not pod.get('error', False):
                                if subpods := pod.get('subpods', []):
                                    if isinstance(subpods, list):
                                        for subpod in subpods:
                                            if isinstance(subpod, dict) and (pt := subpod.get('plaintext')): answer_text = pt.strip(); break
                                if answer_text: break
            final_msg, success_flag = "", False
            if answer_text: final_msg, success_flag = answer_text, True
            elif isinstance(query_res_data, dict):
                if err_info := query_res_data.get('error'): final_msg = f"WA API error ({err_info.get('code')}): {err_info.get('msg')}"
                elif dym := query_res_data.get('didyoumeans'): suggs = [m.get('val') for m in (dym if isinstance(dym, list) else [dym] if isinstance(dym, dict) else []) if isinstance(m, dict) and m.get('val')]; final_msg = f"Did you mean: {', '.join(filter(None, suggs))}?" if suggs else "WA could not interpret query."
                elif tips := query_res_data.get('tips'): tip_txt = (tips[0].get('text', '') if isinstance(tips, list) and tips and isinstance(tips[0], dict) else tips.get('text', '') if isinstance(tips, dict) else ''); final_msg = f"Tip from WA: {tip_txt}" if tip_txt else "WA provided no answer/tips."
                elif not query_res_data.get('success', True): final_msg = "WA indicated query failure."
                else: final_msg = "WA provided no specific answer for format/pods."
            else: final_msg = "Invalid/empty response from WA."
            return {"success": success_flag, "result": final_msg, "message": final_msg, "raw_response": wa_json}
        except httpx.TimeoutException as e: return {"success": False, "message": "Timeout connecting to Wolfram Alpha.", "raw_response": None}
        except httpx.RequestError as e: return {"success": False, "message": f"Connection error querying Wolfram Alpha: {e}", "raw_response": None}
        except json.JSONDecodeError as e: response_text = resp.text[:500] if 'resp' in locals() and hasattr(resp, 'text') else 'N/A'; return {"success": False, "message": f"Invalid JSON from Wolfram Alpha: {e}. Response: {response_text}", "raw_response": None}
        except Exception as e: logger.error(f"Error processing Wolfram Alpha response: {e}", exc_info=True); return {"success": False, "message": f"Error processing Wolfram Alpha data: {e}", "raw_response": None}

    async def verify_world_fact(self, fact_entry: MemoryEntry) -> Dict[str, Any]: # From broken
        fact_id, original_statement = fact_entry.get('id', 'unknown'), fact_entry.get('content')
        if not original_statement: return {"status": "unverifiable", "reason": "Original fact content empty."}
        if not self.config.ENABLE_WEB_SEARCH or not self.web_search_service: return {"status": "unverifiable", "reason": "Web search unavailable."}
        llm_config = self.knowledge_upkeep_llm_config
        if not llm_config or not llm_config.get('url'): upkeep_role = self.config.ETHOS.get('knowledge_upkeep_llm_role', 'LOGOS_TECHNE'); return {"status": "unverifiable", "reason": f"LLM for role {upkeep_role} not configured."}
        query = f"Verify fact: {original_statement}"[:250]
        results = await self.web_search_service.perform_search(query)
        if not results: return {"status": "unverifiable", "reason": "No web search results for verification."}
        context_parts = [f"Source {i+1} (Title: {r.get('title', 'N/A')}, URL: {r.get('link', '#')}):\n{r.get('snippet', 'N/A')}" for i, r in enumerate(results[:3])]
        context = "\n\n---\n\n".join(context_parts)
        sys_prompt = "You are a fact verification AI. Analyze 'Original Fact' against 'Web Snippets'. Determine accuracy, provide corrected statement if UPDATED, or explain if UNCERTAIN."
        user_prompt = f"Original Fact:\n\"{original_statement}\"\n\nWeb Snippets:\n---\n{context}\n---\n\nJSON Response (assessment: ACCURATE|UPDATED|UNCERTAIN, corrected_statement: if UPDATED else null, reasoning: brief explanation):"
        try:
            llm_resp_str = await self._call_logos_llm(llm_config, llm_messages_for_synthesis=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}])
            if llm_resp_str and not llm_resp_str.startswith("["):
                cleaned = re.sub(r"```json\s*|\s*```", "", llm_resp_str).strip()
                try:
                    analysis = json.loads(cleaned); assessment, corrected, reasoning = analysis.get("assessment", "").upper(), analysis.get("corrected_statement"), analysis.get("reasoning", "")
                    if assessment == "ACCURATE": return {"status": "accurate", "reason": reasoning}
                    elif assessment == "UPDATED" and corrected: return {"status": "updated", "new_fact_statement": corrected, "confidence": 0.9, "reason": reasoning}
                    elif assessment == "UNCERTAIN": return {"status": "unverifiable", "reason": f"LLM uncertain: {reasoning}"}
                    else: return {"status": "unverifiable", "reason": f"LLM unexpected assessment: {assessment}. Raw: {llm_resp_str[:100]}"}
                except json.JSONDecodeError:
                    if "ACCURATE" in llm_resp_str.upper(): return {"status": "accurate", "reason": "LLM indicated accuracy, JSON parse failed."}
                    return {"status": "unverifiable", "reason": f"LLM response not valid JSON: {llm_resp_str[:100]}"}
            return {"status": "unverifiable", "reason": "LLM response invalid or empty."}
        except Exception as e: logger.error(f"Error in LLM fact verification for ID {fact_id}: {e}", exc_info=True); return {"status": "unverifiable", "reason": f"Verification error: {e}"}

    # --- NPC Simulation Tool Execution Stubs ---
    async def execute_initiate_simulated_interaction(self, npc_name: Optional[str], npc_role: str, npc_description: str, initial_context: str, pathos_opening_statement: str) -> str:
        logger.info(f"LogosCore: Initiating simulated interaction. Role: {npc_role}, Context: {initial_context}")
        result = await simulation_module.initiate_simulated_interaction(npc_name, npc_role, npc_description, initial_context, pathos_opening_statement)
        return json.dumps(result)

    async def execute_send_message_to_simulated_npc(self, message_to_npc: str) -> str:
        logger.info(f"LogosCore: Sending message to simulated NPC: '{message_to_npc[:50]}...'")
        result = await simulation_module.send_message_to_simulated_npc(message_to_npc)
        return json.dumps(result)

    async def execute_end_simulated_interaction(self) -> str:
        logger.info("LogosCore: Ending simulated interaction.")
        result = await simulation_module.end_simulated_interaction()
        return json.dumps(result)