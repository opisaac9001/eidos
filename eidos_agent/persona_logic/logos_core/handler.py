import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable

from eidos_agent.core.config import Config
from eidos_agent.persona_logic.ethos_core.core import EthosCore
from eidos_agent.llm_integrations.llm_client import LLMClient
from eidos_agent.services.openweathermap import OpenWeatherMapService
from eidos_agent.services.web_search import WebSearchService
from eidos_agent.features.bookshelf.bookshelf_handler import BookshelfHandler

# Import FirmamentModule for NPC interaction
from eidos_agent.features.firmament.module import FirmamentModule # Corrected path from relative

# Schemas for tool call and result
from eidos_agent.schemas.llm_schemas import LLMToolCall # Corrected path from relative
from eidos_agent.schemas.tool_schemas import ToolResult # Corrected path from relative

from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

# Type alias for tool execution functions
ToolExecutor = Callable[..., Awaitable[Dict[str, Any]]]

class LogosCore:
    def __init__(self,
                 config: Config,
                 ethos_core: EthosCore,
                 llm_client: LLMClient,
                 http_client_manager: HTTPClientManager, # Added
                 bookshelf_handler: Optional[BookshelfHandler] = None, # Added
                 owm_service: Optional[OpenWeatherMapService] = None, # Added
                 firmament_module: Optional[FirmamentModule] = None
                 ):
        self.config = config
        self.ethos_core = ethos_core
        self.llm_client = llm_client
        self.http_client_manager = http_client_manager # Store
        self.bookshelf_handler = bookshelf_handler # Store
        self.owm_service = owm_service # Store
        self.firmament_module = firmament_module

        self.logos_techne_config: Optional[LLMConfig] = config.get_llm_config('LOGOS_TECHNE')
        self.logos_research_config: Optional[LLMConfig] = config.get_llm_config('LOGOS_DEEP_RESEARCH')

        knowledge_upkeep_llm_role = config.ETHOS.get('knowledge_upkeep_llm_role', 'LOGOS_TECHNE')
        self.knowledge_upkeep_llm_config: Optional[LLMConfig] = config.get_llm_config(knowledge_upkeep_llm_role)

        self.web_search_service: Optional[WebSearchService] = None
        if config.ENABLE_WEB_SEARCH:
            if brave_config := config.get_brave_search_config():
                if brave_config.get('api_key'):
                    self.web_search_service = WebSearchService(config, self.http_client_manager.get_client())
                else: logger.error("Brave Search API key missing. Web search disabled.")
            else: logger.error("Brave Search config missing. Web search disabled.")
        else: logger.info("Web Search disabled in LogosCore.")

        self.wolfram_alpha_config: Optional[Dict[str, Any]] = config.get_wolfram_alpha_config()
        if self.config.ENABLE_WOLFRAM_ALPHA and not self.wolfram_alpha_config:
             logger.warning("Wolfram Alpha enabled but APP_ID missing. Math/Weather/Time tools may fail.")

        self.news_config: Optional[Dict[str, Any]] = config.get_news_api_config()
        if self.news_config and self.news_config.get('enabled', False):
            if not self.news_config.get('api_key'): logger.warning("News API enabled but key missing. Briefing news disabled.")
            else: logger.info("News API enabled for LogosCore (Daily Briefing).")
        else: logger.info("News API disabled or not configured in LogosCore.")

        # TOOL_DISPATCH_MAP will be populated as methods are re-implemented
        self.TOOL_DISPATCH_MAP: Dict[str, ToolExecutor] = {
            "interact_with_npc": self.execute_interact_with_npc,
            "get_current_time": self.execute_get_current_time,
            "web_search": self.execute_web_search,
            "math_calculator": self.execute_math_calculation, # Tool name in definitions
            "get_weather": self.execute_get_weather,
            "store_user_fact": self.execute_store_user_fact,
            "store_world_fact": self.execute_store_world_fact,
            "perform_deep_research": self.execute_deep_research,
            "get_news_headlines": self.execute_get_news_headlines,
            "add_pathos_event": self.execute_add_pathos_event_to_calendar,
            "bookshelf_add_document": self.execute_bookshelf_add_document,
            "bookshelf_query": self.execute_bookshelf_query,
            "bookshelf_list_documents": self.execute_bookshelf_list_documents,
            "bookshelf_get_document_raw_text": self.execute_bookshelf_get_document_raw_text,
            "bookshelf_remove_document": self.execute_bookshelf_remove_document,
            "process_document_for_rag": self.execute_process_document_for_rag,
        }
        logger.info("LogosCore initialized with full dependencies and service setup.")

    async def initialize_services(self): # Re-implementing this method
        """Logs the status of configured services and LLM roles for LogosCore."""
        logger.info("LogosCore: Service initialization/status check started.")

        # Web Search
        web_search_enabled = self.config.ENABLE_WEB_SEARCH
        web_search_service_init = self.web_search_service is not None
        logger.info(f"LogosCore: Web Search: {'ENABLED' if web_search_enabled else 'DISABLED'}, Service Initialized: {web_search_service_init}")

        # Wolfram Alpha
        wolfram_enabled = self.config.ENABLE_WOLFRAM_ALPHA
        wolfram_configured = bool(self.wolfram_alpha_config and self.wolfram_alpha_config.get('app_id'))
        logger.info(f"LogosCore: Wolfram Alpha: {'ENABLED' if wolfram_enabled else 'DISABLED'}, App ID Configured: {wolfram_configured}")

        # News API
        news_api_enabled = bool(self.news_config and self.news_config.get('enabled'))
        news_api_key_present = bool(self.news_config and self.news_config.get('api_key'))
        if news_api_enabled:
            logger.info(f"LogosCore: News API: ENABLED, API Key Present: {news_api_key_present}")
        else:
            logger.info("LogosCore: News API: DISABLED")

        # OpenWeatherMap Service
        owm_available = self.owm_service is not None and self.owm_service.is_available
        if owm_available:
            logger.info("LogosCore: OpenWeatherMap Service: AVAILABLE")
        else:
            logger.warning("LogosCore: OpenWeatherMap Service: UNAVAILABLE or not configured.")

        # Bookshelf Handler
        if self.bookshelf_handler:
            logger.info("LogosCore: BookshelfHandler: AVAILABLE")
        else:
            logger.info("LogosCore: BookshelfHandler: NOT AVAILABLE (not passed during init or disabled).")


        # LLM Configurations specific to LogosCore tasks
        llm_roles_to_check = {
            "LOGOS_TECHNE (Summarization/Sentiment/Briefing Synthesis)": self.logos_techne_config,
            "LOGOS_DEEP_RESEARCH (Report Synthesis)": self.logos_research_config,
            "KNOWLEDGE_UPKEEP_LLM (Fact Verification)": self.knowledge_upkeep_llm_config
        }

        for role_description, llm_config_obj in llm_roles_to_check.items():
            if llm_config_obj and llm_config_obj.get('url'): # Basic check for configuration
                logger.info(f"LogosCore: LLM Role '{role_description}': CONFIGURED (URL: {llm_config_obj.get('url')}, Model: {llm_config_obj.get('model', 'N/A')})")
            else:
                logger.warning(f"LogosCore: LLM Role '{role_description}': NOT CONFIGURED or URL missing.")

        logger.info("LogosCore: Service initialization/status check completed.")

    async def _call_logos_llm(self, llm_config: LLMConfig, llm_messages_for_synthesis: List[Dict[str, Any]], prompt_text: Optional[str] = None) -> Optional[str]: # Ensure prompt_text is optional if messages are primary
        """
        Internal helper to call an LLM for LogosCore's own tasks (summarization, classification, synthesis).
        Uses the standardized self.llm_client.
        Returns the text content of the LLM's response or an error message string (wrapped in brackets).
        """
        if not self.llm_client:
            logger.error("LLMClient not available in LogosCore for internal LLM call.")
            return "[LLMClient not available in LogosCore]"

        if not llm_config: # Should be passed by caller with specific role config
            logger.error("LLM configuration missing for _call_logos_llm.")
            return "[LLM configuration missing for _call_logos_llm]"

        messages_to_send = llm_messages_for_synthesis
        if not messages_to_send and prompt_text: # Fallback if only prompt_text was given (legacy)
            messages_to_send = [{"role": "user", "content": prompt_text}]

        if not messages_to_send:
            logger.error("_call_logos_llm: No messages provided.")
            return "[No messages provided for _call_logos_llm]"

        try:
            # Determine max_tokens based on task type if not specified in llm_config
            # This logic can be enhanced or made part of the llm_config itself.
            max_tokens_override = llm_config.get('max_tokens')
            # Example: if a message contains "summarize", allow more tokens.
            # This is a heuristic and might need refinement.
            if max_tokens_override is None: # Only if not explicitly set in the role's config
                if any("summarize" in msg.get("content","").lower() for msg in messages_to_send if isinstance(msg.get("content"), str)):
                    max_tokens_override = 1024
                elif any("sentiment" in msg.get("content","").lower() for msg in messages_to_send if isinstance(msg.get("content"), str)):
                    max_tokens_override = 128 # Sentiment usually short
                else:
                    max_tokens_override = 512 # Default for other internal tasks

            response_payload: LLMResponsePayload = await self.llm_client.call_llm_api(
                llm_config=llm_config,
                messages=messages_to_send,
                stream=False, # Internal LogosCore tasks typically don't need streaming text back
                max_tokens_override=max_tokens_override
            )

            if response_payload.success() and response_payload.content is not None:
                return str(response_payload.content).strip()
            else:
                error_message = response_payload.error_message or f"LogosCore LLM call (model: {llm_config.get('model')}) failed with no content."
                logger.warning(f"{error_message} (Status: {response_payload.status_code})")
                return f"[{error_message}]" # Return error message wrapped in brackets
        except Exception as e_call:
            logger.error(f"Unexpected error in _call_logos_llm (model: {llm_config.get('model')}): {e_call}", exc_info=True)
            return f"[Unexpected error during LogosCore LLM call: {str(e_call)}]"

    async def _fetch_news_headlines_with_details(self, news_api_config_override: Optional[Dict[str,Any]] = None) -> List[Dict[str, str]]:
        """Fetches news headlines using TheNewsAPI and returns a list of article data dicts."""

        # Use override config if provided, otherwise use instance's default news_config
        current_news_config = news_api_config_override if news_api_config_override else self.news_config

        if not current_news_config or not current_news_config.get('enabled') or not current_news_config.get('api_key'):
            logger.info("News fetching skipped: News API not configured or enabled.")
            return []

        api_key = current_news_config['api_key']
        base_url = current_news_config.get('base_url', 'https://api.thenewsapi.com/v1').rstrip('/')

        params: Dict[str, Any] = {
            "api_token": api_key,
            "locale": current_news_config.get('default_locale', 'us'),
            "language": current_news_config.get('default_language', 'en'),
            "limit": current_news_config.get('limit', 5), # Max articles to fetch from API
            "snippet_len": current_news_config.get('snippet_max_length', 250) # Max length for snippet from API
        }

        endpoint = f"{base_url}/news/top" # Default to top headlines

        if search_keywords := current_news_config.get('search_keywords'):
            params['search'] = search_keywords
            endpoint = f"{base_url}/news/all" # Switch to 'all' endpoint for keyword search
        elif categories := current_news_config.get('categories'): # Categories only used if no search_keywords
            params['categories'] = categories

        if include_source_ids := current_news_config.get('include_source_ids'):
            params['source_ids'] = include_source_ids
            if endpoint.endswith('/news/top'): # If categories were also set, 'all' endpoint is better for source filtering
                endpoint = f"{base_url}/news/all"
        if exclude_domains := current_news_config.get('exclude_domains'): # Mapped from exclude_source_ids in original
            params['exclude_domains'] = exclude_domains

        # Add other params like published_before/after, found_before/after if needed from config

        articles_to_return: List[Dict[str, str]] = []
        try:
            async with self.http_client_manager.get_client() as client:
                timeout_val = float(current_news_config.get('timeout', 15.0))
                logger.debug(f"Fetching news from {endpoint} with params: {params}")
                response = await client.get(endpoint, params=params, timeout=timeout_val)
                response.raise_for_status()
                data = response.json()

            api_articles_data = data.get("data", [])
            if not isinstance(api_articles_data, list):
                logger.warning(f"News API returned 'data' not as a list: {type(api_articles_data)}. Full response: {data}")
                return []

            for article_data in api_articles_data:
                if isinstance(article_data, dict):
                    title = str(article_data.get("title", "")).strip()
                    url = str(article_data.get("url", "#")).strip()
                    if title and url != "#": # Basic validation
                        articles_to_return.append({
                            "title": title,
                            "url": url,
                            "original_description": str(article_data.get("description", "") or article_data.get("snippet", "")).strip(),
                            "content_for_summary": str(article_data.get("snippet", "") or article_data.get("description", "")).strip(), # Prefer snippet if available
                            "published_at": str(article_data.get("published_at", "")),
                            "source_name": str(article_data.get("source", "unknown_source")) # API uses "source" for domain
                        })
            logger.info(f"Fetched {len(articles_to_return)} news articles from TheNewsAPI.")
            return articles_to_return

        except httpx.HTTPStatusError as e_http:
            logger.error(f"HTTP error fetching news from TheNewsAPI ({endpoint}): {e_http.response.status_code} - {e_http.response.text[:200]}", exc_info=True)
        except httpx.RequestError as e_req:
            logger.error(f"Request error fetching news from TheNewsAPI ({endpoint}): {e_req}", exc_info=True)
        except json.JSONDecodeError as e_json:
            logger.error(f"JSON decode error processing news response from TheNewsAPI ({endpoint}): {e_json}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error fetching news from TheNewsAPI ({endpoint}): {e}", exc_info=True)
        return [] # Return empty list on any error

    async def generate_daily_briefing(self, user_id_context: Optional[str] = None) -> Optional[str]:
        """Generates the daily briefing content string."""
        logger.info(f"Generating new daily briefing for user_id_context: {user_id_context}")
        now_utc = datetime.now(timezone.utc)
        today_date_str = now_utc.strftime('%Y-%m-%d')

        # Determine local time display for the user
        local_time_display = now_utc.strftime('%A, %B %d, %Y, %I:%M %p %Z') # Default to UTC display
        pathos_default_user_id = getattr(self.ethos_core, 'PATHOS_USER_ID', 'pathos_internal_user')
        target_user_for_time = user_id_context if user_id_context and user_id_context not in getattr(self.ethos_core, 'system_user_ids', []) else pathos_default_user_id

        if self.ethos_core:
            try:
                user_local_dt = await self.ethos_core.get_local_datetime_for_user(target_user_for_time)
                local_time_display = user_local_dt.strftime('%A, %B %d, %Y, %I:%M %p %Z (%z)')
            except Exception as e_time:
                logger.warning(f"Could not get local time for user '{target_user_for_time}' for briefing: {e_time}")

        # --- Weather Section ---
        weather_parts = ["**Weather:**"]
        weather_loc = os.getenv("BRIEFING_WEATHER_LOCATION_FALLBACK", "New York, NY") # Default location
        if self.ethos_core: # Try to get user's preferred location
            if loc_fact_entry := await self.ethos_core.get_user_fact('preferred_location', target_user_for_time):
                if isinstance(loc_fact_entry, dict) and (content := loc_fact_entry.get('content')): # Check if it's a dict (MemoryEntry)
                    try:
                        if user_pref_loc := json.loads(content).get('value'):
                            weather_loc = user_pref_loc
                    except json.JSONDecodeError: pass

        weather_tool_result = await self.execute_get_weather(weather_loc, user_id_context=target_user_for_time)
        if weather_tool_result.get('success') and (wd := weather_tool_result.get('data')): # data from tool result
            weather_parts.append(f"- Location: {wd.get('location', weather_loc)}") # wd.location from OWM, or raw_wolfram_weather.location_queried
            conditions = wd.get('description', 'N/A')
            temp = wd.get('temperature', '--')
            unit = wd.get('unit', '')
            weather_parts.append(f"- Conditions: {temp}{unit}, {conditions}")
            if wd.get('humidity'): weather_parts.append(f"- Humidity: {wd.get('humidity')}")
            if wd.get('wind_speed'): weather_parts.append(f"- Wind: {wd.get('wind_speed')}")
        else:
            weather_parts.append(f"- Weather for {weather_loc}: {weather_tool_result.get('error', 'Currently unavailable')}")

        # --- News Section ---
        news_parts = ["**Top News:**"]
        if self.news_config and self.news_config.get('enabled'):
            # Use default news config, but ensure no keyword search for top headlines for briefing
            briefing_news_api_conf = self.news_config.copy()
            briefing_news_api_conf.pop('search_keywords', None)
            briefing_news_api_conf['categories'] = briefing_news_api_conf.get('categories', 'general') # Default category
            briefing_news_api_conf['limit'] = self.news_config.get('briefing_article_limit', 3) # Configurable limit for briefing

            headlines_data = await self._fetch_news_headlines_with_details(briefing_news_api_conf)
            if headlines_data:
                for item_idx, item in enumerate(headlines_data[:briefing_news_api_conf['limit']]): # Limit to 3-5 for briefing
                    news_parts.append(f"- [{item['title']}]({item['url']})")
                    if snippet := item.get('original_description', ''): # Use original_description as snippet
                        news_parts.append(f"  - _{snippet[:120] + '...' if len(snippet) > 120 else snippet}_")
            else:
                news_parts.append("- No top headlines found for your region/preferences at this moment.")
        else:
            news_parts.append("- News service is currently disabled.")

        briefing_content = f"### Daily Briefing ({local_time_display})\n\n" + "\n".join(weather_parts) + "\n\n" + "\n".join(news_parts)

        # Store the generated briefing in EthosCore memory
        if self.ethos_core:
            memory_metadata = {
                "generation_timestamp_utc": now_utc.isoformat(),
                "briefing_date_utc": today_date_str, # UTC date for which briefing was generated
                "briefing_format_version": "panel_v1.1", # Versioning for format
                "generated_for_user_context": user_id_context or "system_pathos_default",
                "weather_location_used": weather_loc,
                "news_categories_used": briefing_news_api_conf.get('categories') if 'briefing_news_api_conf' in locals() else 'N/A'
            }
            try:
                await self.ethos_core.add_memory_entry(
                    {"type": "daily_briefing", "content": briefing_content, "metadata": memory_metadata},
                    user_id_context="system_briefing" # Stored under a system context
                )
                logger.info(f"Stored newly generated daily briefing for date {today_date_str}.")
            except Exception as e_mem:
                logger.error(f"Failed to store generated daily briefing: {e_mem}", exc_info=True)

        return briefing_content

    async def get_or_generate_daily_briefing(self, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        """Gets existing briefing for today or generates a new one. Includes sentiment."""
        if not self.ethos_core:
            logger.warning("LogosCore: EthosCore not accessible for get_or_generate_daily_briefing.")
            return {"success": False, "briefing_content": None, "message": "Memory system (EthosCore) not accessible.", "classified_sentiment": "neutral"}

        briefing_content_str: Optional[str] = None
        source_message: str = "Unknown"
        classified_sentiment: str = "neutral" # Default sentiment

        try:
            existing_briefing_content = await self.ethos_core.get_todays_briefing() # Fetches for current UTC date
            if existing_briefing_content:
                briefing_content_str = existing_briefing_content
                source_message = "Briefing retrieved from memory."
                logger.info(f"LogosCore: Retrieved existing daily briefing for user '{user_id_context}'.")
            else:
                logger.info(f"LogosCore: No existing briefing found. Generating new briefing for user '{user_id_context}'.")
                briefing_content_str = await self.generate_daily_briefing(user_id_context=user_id_context)
                if briefing_content_str:
                    source_message = "Briefing newly generated."
                    logger.info(f"LogosCore: Successfully generated new daily briefing for user '{user_id_context}'.")
                else: # Generation failed
                    logger.error(f"LogosCore: Failed to generate new briefing for user '{user_id_context}'.")
                    return {"success": False, "briefing_content": None, "message": "Failed to generate new briefing.", "classified_sentiment": "neutral"}

        except Exception as e_brief:
            logger.error(f"LogosCore: Error in briefing retrieval or generation phase for user '{user_id_context}': {e_brief}", exc_info=True)
            return {"success": False, "briefing_content": None, "message": f"Error in briefing process: {str(e_brief)}", "classified_sentiment": "neutral"}

        # Perform sentiment classification on the obtained briefing_content_str
        if briefing_content_str and self.logos_techne_config: # Ensure LLM config for Techne is available
            try:
                sentiment_prompt_text = f"Classify the overall sentiment of the following daily briefing text as 'positive', 'negative', or 'neutral'. Respond with only one of these three labels. Briefing: {briefing_content_str[:1500]}"
                llm_sentiment_label = await self._call_logos_llm(
                    llm_config=self.logos_techne_config,
                    llm_messages_for_synthesis=[{"role": "user", "content": sentiment_prompt_text}]
                )
                if llm_sentiment_label and not llm_sentiment_label.startswith("["):
                    cleaned_label = llm_sentiment_label.lower().strip().replace("'", "").replace('"',"")
                    # More robustly check if the label is one of the expected ones
                    first_word_match = re.match(r"^(positive|negative|neutral)\b", cleaned_label)
                    if first_word_match:
                        classified_sentiment = first_word_match.group(1)
                        logger.info(f"LogosCore: Classified briefing sentiment for user '{user_id_context}' as '{classified_sentiment}'.")
                    else:
                        logger.warning(f"LogosCore: Briefing sentiment for user '{user_id_context}' returned non-standard label: '{llm_sentiment_label}'. Defaulting to neutral.")
                else: # LLM call failed or returned error string
                    logger.warning(f"LogosCore: Briefing sentiment classification for user '{user_id_context}' failed or no label. LLM response: {llm_sentiment_label}. Defaulting to neutral.")
            except Exception as e_sent:
                logger.error(f"LogosCore: Error during briefing sentiment classification for user '{user_id_context}': {e_sent}", exc_info=True)
        elif not briefing_content_str:
             logger.info("LogosCore: No briefing content to classify sentiment for.")
        elif not self.logos_techne_config:
            logger.warning("LogosCore: LOGOS_TECHNE LLM not configured. Cannot classify briefing sentiment. Defaulting to neutral.")

        return {
            "success": True,
            "briefing_content": briefing_content_str,
            "message": source_message, # Provides info on whether it was retrieved or generated
            "source": source_message, # Compatibility with some old uses of this key
            "classified_sentiment": classified_sentiment
        }

    async def determine_subjective_reaction(
        self,
        event_description: str,
        event_data_summary: Optional[str], # Summary of the event data (e.g., user input, tool output)
        current_hexus_scores: Dict[str, float], # Pathos's current Hexus state
        persona_directives: List[str], # Key persona directives for Pathos
        available_reactions: List[str] # List of valid reaction strings (e.g., "REACTION_HAPPY", "REACTION_FRUSTRATED")
    ) -> str: # Returns one of the available_reactions strings
        """
        Determines Pathos's subjective, personal reaction to an event using an LLM.
        """
        default_reaction = "REACTION_INDIFFERENT_UNEFFECTED" # Ensure this is in available_reactions

        if not self.logos_techne_config: # Using LOGOS_TECHNE for this classification task
            logger.error("LogosCore: LOGOS_TECHNE LLM not configured. Cannot determine subjective reaction.")
            return default_reaction
        if not available_reactions:
            logger.error("LogosCore: No available_reactions provided for determine_subjective_reaction.")
            return default_reaction # Or a generic non-reaction

        # Construct Persona Directives string for prompt (first 3-5 for brevity)
        persona_directives_str_parts = []
        for i, directive in enumerate(persona_directives[:3]): # Using first 3 for brevity
            persona_directives_str_parts.append(f"- {directive}")
        if not persona_directives_str_parts:
            persona_directives_str_parts.append("- Pathos aims to be helpful and understanding.") # Fallback directive

        persona_directives_for_prompt = "\n".join(persona_directives_str_parts)

        # Prepare Hexus scores string for prompt
        hexus_scores_str_parts = [f"  - {dim}: {score:.2f}" for dim, score in current_hexus_scores.items()]
        hexus_scores_for_prompt = "\n".join(hexus_scores_str_parts)

        system_prompt = (
            "You are an AI assistant specialized in empathic reasoning to determine an AI's (Pathos) subjective emotional reaction to events. "
            "Pathos has a defined persona and current internal emotional state (Hexus scores from 0.0 to 1.0). "
            "Your goal is to select the *single most fitting* subjective reaction from a provided list, based on all context."
        )

        user_prompt_parts = [
            "An event has occurred that Pathos needs to react to:\n"
            f"Event Description: **{event_description}**\n",
            f"Details/Data for this event: **{event_data_summary if event_data_summary else 'N/A'}**\n\n",
            "Pathos's Core Persona Directives include:\n"
            f"{persona_directives_for_prompt}\n\n",
            "Pathos's Current Internal Hexus State (Emotional/Cognitive Indicators):\n"
            f"{hexus_scores_for_prompt}\n\n",
            "Considering Pathos's persona, current state, and the event details, what is his single most fitting *subjective and personal* reaction? "
            "This reaction should reflect how Pathos *feels* or *perceives* the event internally.\n",
            f"Choose ONLY ONE reaction type from the following list. Respond with only the chosen reaction string (e.g., REACTION_VALIDATED_CONFIRMED):\n",
            f"{', '.join(available_reactions)}"
        ]
        user_prompt = "".join(user_prompt_parts)

        messages_for_llm = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        logger.debug(f"LogosCore: Determining subjective reaction. Event: '{event_description}'. Data: '{str(event_data_summary)[:100]}...'. Hexus: {current_hexus_scores}. Persona Directives (sample): {persona_directives[:1]}. Available Reactions: {len(available_reactions)}")

        raw_llm_response: Optional[str] = None
        try:
            raw_llm_response = await self._call_logos_llm( # Uses self.llm_client
                llm_config=self.logos_techne_config,
                llm_messages_for_synthesis=messages_for_llm,
            )

            if raw_llm_response and not raw_llm_response.startswith("["): # Check for error string from _call_logos_llm
                logger.debug(f"LogosCore: Raw LLM response for subjective reaction: '{raw_llm_response}'")
                # Parse the LLM response - it should be one of the available_reactions strings
                parsed_reaction = raw_llm_response.strip().replace('"', '').replace("'", "").splitlines()[0].strip()

                if parsed_reaction in available_reactions:
                    logger.info(f"LogosCore: Determined subjective reaction: '{parsed_reaction}' for event: '{event_description}'")
                    return parsed_reaction
                else:
                    logger.warning(f"LogosCore: LLM returned an invalid or unexpected reaction: '{parsed_reaction}'. Not in available_reactions. Falling back. Raw response: '{raw_llm_response}'")
                    return default_reaction if default_reaction in available_reactions else available_reactions[0] if available_reactions else "REACTION_INDIFFERENT_UNEFFECTED"
            else:
                logger.warning(f"LogosCore: LLM returned no valid response or an error string for subjective reaction: {raw_llm_response}. Falling back. Event: '{event_description}'")
                return default_reaction if default_reaction in available_reactions else available_reactions[0] if available_reactions else "REACTION_INDIFFERENT_UNEFFECTED"

        except Exception as e_react:
            logger.error(f"LogosCore: Error during LLM call for subjective reaction determination: {e_react}", exc_info=True)
            return default_reaction if default_reaction in available_reactions else available_reactions[0] if available_reactions else "REACTION_INDIFFERENT_UNEFFECTED"

    async def verify_world_fact(self, fact_entry_content: str, fact_id_for_log: Optional[str]="adhoc") -> Dict[str, Any]: # Takes content directly
        """
        Verifies a given fact statement using web search and LLM analysis.
        Returns a dictionary with verification status and details.
        """
        original_statement = fact_entry_content
        if not original_statement:
            return {"success": False, "error": "Original fact content empty.", "data": {"verification_status": "unverifiable", "reason": "Fact content was empty."}}

        if not self.config.ENABLE_WEB_SEARCH or not self.web_search_service:
            return {"success": False, "error": "Web search unavailable for verification.", "data": {"verification_status": "unverifiable", "reason": "Web search service is unavailable."}}

        llm_config_for_verification = self.knowledge_upkeep_llm_config # Specific LLM for this
        if not llm_config_for_verification or not llm_config_for_verification.get('url'):
            upkeep_role_name = self.config.ETHOS.get('knowledge_upkeep_llm_role', 'LOGOS_TECHNE')
            return {"success": False, "error": f"LLM for fact verification (role: {upkeep_role_name}) not configured.", "data": {"verification_status": "unverifiable", "reason": "Verification LLM not configured."}}

        # Construct search query
        verification_query = f"Verify fact: {original_statement}"[:250] # Limit query length

        try:
            search_results = await self.web_search_service.perform_search(verification_query)
            if not search_results:
                return {"success": False, "error": "No web search results found for fact verification.", "data": {"verification_status": "unverifiable", "reason": "No supporting information found in web search."}}

            # Prepare context from search results for the LLM
            context_parts = []
            for i, res_data in enumerate(search_results[:3]): # Use top 3 results
                context_parts.append(f"Source {i+1} (Title: {res_data.get('title', 'N/A')}, URL: {res_data.get('link', '#')}):\n{res_data.get('snippet', 'N/A')}")
            search_context_for_llm = "\n\n---\n\n".join(context_parts)

            system_prompt = load_system_prompt(
                "fact_verification_llm_system_prompt", # Assuming a prompt file for this
                default_content=(
                    "You are a meticulous fact verification AI. Your task is to analyze an 'Original Fact' "
                    "against several 'Web Search Snippets'. Based *only* on the provided snippets, determine if the Original Fact is ACCURATE, "
                    "if it needs to be UPDATED (provide the corrected statement), or if its accuracy is UNCERTAIN based on the snippets. "
                    "Provide a brief reasoning for your assessment. Your response MUST be a single JSON object with the following keys: "
                    "\"assessment\" (string: \"ACCURATE\", \"UPDATED\", or \"UNCERTAIN\"), "
                    "\"corrected_statement\" (string: the updated fact if assessment is UPDATED, otherwise null), "
                    "and \"reasoning\" (string: your brief explanation)."
                )
            )

            user_prompt_content = (
                f"Original Fact Statement to Verify:\n\"{original_statement}\"\n\n"
                "Relevant Web Search Snippets for Verification:\n"
                "---\n"
                f"{search_context_for_llm}\n"
                "---\n\n"
                "Based *only* on the provided snippets, please provide your verification assessment in the specified JSON format:"
            )

            messages_for_llm = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt_content}]

            llm_response_str = await self._call_logos_llm(
                llm_config=llm_config_for_verification,
                llm_messages_for_synthesis=messages_for_llm
            )

            if not llm_response_str or llm_response_str.startswith("["): # Error from _call_logos_llm
                 return {"success": False, "error": f"LLM response invalid or empty during fact verification: {llm_response_str}", "data": {"verification_status": "unverifiable", "reason": f"LLM error: {llm_response_str}"}}

            # Attempt to parse the JSON response from LLM
            try:
                # Remove potential markdown backticks if LLM wraps JSON in them
                cleaned_llm_response_str = re.sub(r"```json\s*|\s*```", "", llm_response_str).strip()
                analysis_result = json.loads(cleaned_llm_response_str)

                assessment = str(analysis_result.get("assessment", "")).upper()
                corrected_statement = analysis_result.get("corrected_statement")
                reasoning = analysis_result.get("reasoning", "No reasoning provided by LLM.")

                verification_data = {
                    "original_statement": original_statement,
                    "reasoning": reasoning,
                    "web_search_query_used": verification_query,
                    "top_snippets_consulted": [res.get('snippet') for res in search_results[:3] if res.get('snippet')]
                }

                if assessment == "ACCURATE":
                    return {"success": True, "data": {"verification_status": "accurate", **verification_data}}
                elif assessment == "UPDATED" and corrected_statement and isinstance(corrected_statement, str):
                    return {"success": True, "data": {"verification_status": "updated", "new_statement": corrected_statement, **verification_data}}
                elif assessment == "UNCERTAIN":
                     # Success is False because we couldn't verify, but tool ran.
                    return {"success": False, "error": f"LLM assessment uncertain: {reasoning}", "data": {"verification_status": "unverifiable", **verification_data}}
                else: # Unexpected assessment value
                    return {"success": False, "error": f"LLM returned an unexpected assessment value: '{assessment}'. Raw: {llm_response_str[:150]}", "data": {"verification_status": "unverifiable", "reason": "LLM bad assessment format.", **verification_data}}

            except json.JSONDecodeError:
                # Fallback for non-JSON LLM responses that might still indicate accuracy if LLM doesn't follow JSON instruction
                if "ACCURATE" in llm_response_str.upper():
                    return {"success": True, "data": {"verification_status": "accurate", "original_statement": original_statement, "reasoning": "LLM indicated accuracy, but JSON parsing of full response failed.", "raw_llm_output": llm_response_str[:200]}}
                logger.error(f"Failed to parse LLM JSON response for fact verification (ID: {fact_id_for_log}): {llm_response_str[:200]}", exc_info=True)
                return {"success": False, "error": f"LLM response for fact verification was not valid JSON: {llm_response_str[:150]}", "data": {"verification_status": "unverifiable", "reason": "LLM bad JSON format."}}

        except Exception as e_verify:
            logger.error(f"Error during 'verify_world_fact' for fact ID '{fact_id_for_log}': {e_verify}", exc_info=True)
            return {"success": False, "error": f"Fact verification process failed: {str(e_verify)}", "data": {"verification_status": "unverifiable", "reason": f"System error: {str(e_verify)}"}}


    async def query_wolfram_alpha(self, query: str) -> Dict[str, Any]:
        """Queries Wolfram Alpha and returns a structured response."""
        if not self.config.ENABLE_WOLFRAM_ALPHA or not self.wolfram_alpha_config or not self.wolfram_alpha_config.get('app_id'):
            return {"success": False, "message": "Wolfram Alpha service not available or not configured.", "result": None, "raw_response": None}

        encoded_query = urllib.parse.quote_plus(query)
        app_id = self.wolfram_alpha_config['app_id']
        api_url_base = self.wolfram_alpha_config.get('api_url', 'http://api.wolframalpha.com/v2/query')

        # Define pod IDs and titles to prioritize for different query types
        pod_ids_general = ["Result", "DecimalApproximation", "Plot", "Definition:WordData", "WikipediaSummary:Pod", "BasicInformation:PeopleData", "Input"]
        primary_titles_general = ["Result", "Decimal approximation", "Definition", "Wikipedia summary", "Basic information"]

        pod_ids_time = ["CurrentTimeInLocation:CurrentTime", "Input"]
        primary_titles_time = ["Current time"]

        pod_ids_weather = ["InstantaneousWeather:WeatherData", "WeatherForecast:WeatherData", "CurrentLocationWeather:WeatherData", "LatestRecordedWeather:WeatherData", "Input"]
        primary_titles_weather = ["Instantaneous weather", "Weather forecast", "Current location weather", "Latest recorded weather"]

        pod_ids_to_include, primary_titles_to_check = pod_ids_general, primary_titles_general
        if "time in" in query.lower() or "current time" in query.lower():
            pod_ids_to_include, primary_titles_to_check = pod_ids_time, primary_titles_time
        elif "weather in" in query.lower() or "weather for" in query.lower():
            pod_ids_to_include, primary_titles_to_check = pod_ids_weather, primary_titles_weather

        pod_query_string = "&includepodid=" + "&includepodid=".join(pod_ids_to_include) if pod_ids_to_include else ""
        api_url = f"{api_url_base}?appid={app_id}&input={encoded_query}&output=json{pod_query_string}&format=plaintext"

        raw_response_json = None # To store the full JSON response for debugging or more detailed parsing
        try:
            async with self.http_client_manager.get_client() as client: # Get client from manager
                timeout_val = float(self.wolfram_alpha_config.get('timeout', 20.0))
                response = await client.get(api_url, timeout=timeout_val)
                response.raise_for_status()
                raw_response_json = response.json()

            answer_text: Optional[str] = None
            query_result_data = raw_response_json.get('queryresult', {})

            if isinstance(query_result_data, dict) and query_result_data.get('success'):
                pods = query_result_data.get('pods', [])
                if isinstance(pods, list):
                    # First pass: check primary titles
                    for title_to_check in primary_titles_to_check:
                        for pod in pods:
                            if isinstance(pod, dict) and pod.get('title', '').lower() == title_to_check.lower() and not pod.get('error', False):
                                if subpods := pod.get('subpods', []):
                                    if isinstance(subpods, list):
                                        for subpod in subpods: # Often the first subpod has the main answer
                                            if isinstance(subpod, dict) and (pt := subpod.get('plaintext')):
                                                answer_text = pt.strip()
                                                break
                                if answer_text: break
                        if answer_text: break

                    # Second pass: if no answer from primary titles, check any pod that's not 'Input'
                    if not answer_text and pods:
                        for pod in pods:
                            if isinstance(pod, dict) and pod.get('id', '').lower() != 'input' and not pod.get('error', False):
                                if subpods := pod.get('subpods', []):
                                    if isinstance(subpods, list):
                                        for subpod in subpods:
                                            if isinstance(subpod, dict) and (pt := subpod.get('plaintext')):
                                                answer_text = pt.strip()
                                                break
                                if answer_text: break

            final_message: str = ""
            success_flag: bool = False

            if answer_text:
                final_message = answer_text
                success_flag = True
            elif isinstance(query_result_data, dict): # No direct answer, but queryresult might have info
                if err_info := query_result_data.get('error'):
                    final_message = f"Wolfram Alpha API error ({err_info.get('code')}): {err_info.get('msg')}"
                elif didyoumeans := query_result_data.get('didyoumeans'):
                    suggestions = [m.get('val') for m in (didyoumeans if isinstance(didyoumeans, list) else [didyoumeans] if isinstance(didyoumeans, dict) else []) if isinstance(m, dict) and m.get('val')]
                    final_message = f"Did you mean: {', '.join(filter(None, suggestions))}?" if suggestions else "Wolfram Alpha could not interpret the query."
                elif tips := query_result_data.get('tips'):
                    tip_text_val = (tips[0].get('text', '') if isinstance(tips, list) and tips and isinstance(tips[0], dict) else tips.get('text', '') if isinstance(tips, dict) else '')
                    final_message = f"Tip from Wolfram Alpha: {tip_text_val}" if tip_text_val else "Wolfram Alpha provided no specific answer but gave some tips."
                elif not query_result_data.get('success', True): # Explicit failure from WA
                    final_message = "Wolfram Alpha indicated the query failed."
                else:
                    final_message = "Wolfram Alpha provided no specific answer for the requested format/pods."
            else: # queryresult itself was not a dict or was missing
                final_message = "Invalid or empty response structure from Wolfram Alpha."

            return {"success": success_flag, "result": final_message if success_flag else None, "message": final_message, "raw_response": raw_response_json}

        except httpx.TimeoutException:
            return {"success": False, "message": "Timeout connecting to Wolfram Alpha.", "result": None, "raw_response": raw_response_json}
        except httpx.RequestError as e_req:
            return {"success": False, "message": f"Connection error querying Wolfram Alpha: {e_req}", "result": None, "raw_response": raw_response_json}
        except httpx.HTTPStatusError as e_http:
            return {"success": False, "message": f"Wolfram Alpha API error ({e_http.response.status_code}): {e_http.response.text[:200]}", "result": None, "raw_response": raw_response_json}
        except json.JSONDecodeError:
            resp_text = response.text[:500] if 'response' in locals() and hasattr(response, 'text') else 'N/A'
            return {"success": False, "message": f"Invalid JSON response from Wolfram Alpha. Response: {resp_text}", "result": None, "raw_response": raw_response_json}
        except Exception as e_generic:
            logger.error(f"Unexpected error processing Wolfram Alpha response for query '{query}': {e_generic}", exc_info=True)
            return {"success": False, "message": f"Error processing Wolfram Alpha data: {str(e_generic)}", "result": None, "raw_response": raw_response_json}


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
        logger.info("LogosCore closing...")
        if self.web_search_service and hasattr(self.web_search_service, 'close'):
            await self.web_search_service.close()
        # Other services like OWMService might not have explicit close if they use shared HTTPClientManager
        logger.info("LogosCore resources (like WebSearchService client) closed.")
        pass

    async def execute_get_current_time(self, location: Optional[str] = None, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        """Gets the current time, optionally for a specific location."""
        logger.debug(f"Executing get_current_time for location: {location}, user_id_context: {user_id_context}")
        try:
            final_time_str = ""
            location_used = location if location else "UTC (Pathos's default)"

            # Determine target timezone
            target_tz = timezone.utc # Default to UTC

            if location: # User specified a location string
                # Attempt to interpret location as an IANA timezone string first
                if ZoneInfo:
                    try:
                        target_tz = ZoneInfo(location)
                        location_used = location # Successfully interpreted as IANA
                    except Exception: # zoneinfo.ZoneInfoNotFoundError or similar
                        logger.debug(f"Could not interpret '{location}' as IANA timezone directly for get_current_time.")
                        # If not an IANA string, could try WolframAlpha if enabled for location-based time
                        # For now, we'll proceed and might fall back to user's default or UTC.
                        pass # Fall through to try user's preferred or Wolfram
                elif pytz: # Fallback to pytz if ZoneInfo not available
                    try:
                        target_tz = pytz.timezone(location)
                        location_used = location
                    except Exception: # pytz.UnknownTimeZoneError
                        logger.debug(f"Could not interpret '{location}' as pytz timezone for get_current_time.")
                        pass # Fall through

            elif user_id_context and self.ethos_core: # No location, but have user context
                # Get user's local time via EthosCore
                user_local_dt = await self.ethos_core.get_local_datetime_for_user(user_id_context)
                final_time_str = user_local_dt.strftime('%A, %B %d, %Y at %I:%M:%S %p %Z (%z)')
                location_used = f"User's default location ({user_local_dt.tzname()})"

            # If still no final_time_str, and location was provided (but not parsed as IANA)
            # or if no user_id_context to get default.
            if not final_time_str:
                if location: # Location was given, but not an IANA timezone. Try WolframAlpha if available.
                    if self.config.ENABLE_WOLFRAM_ALPHA and self.wolfram_alpha_config:
                        logger.debug(f"Attempting WolframAlpha for time in '{location}'")
                        wa_res = await self.query_wolfram_alpha(f"current time in {location}")
                        if wa_res.get('success') and wa_res.get('result'):
                            final_time_str = f"For {location}, Wolfram Alpha reports: {wa_res['result']}."
                            location_used = f"{location} (via Wolfram Alpha)"
                        else:
                            logger.warning(f"WolframAlpha query for time in '{location}' failed or no result: {wa_res.get('message')}")
                            # Fallback to Pathos's local time if Wolfram fails for specific location
                            pathos_local_dt = await self.ethos_core.get_local_datetime_for_user(self.config.ETHOS.get("pathos_user_id", "pathos"))
                            final_time_str = pathos_local_dt.strftime('%A, %B %d, %Y at %I:%M:%S %p %Z (%z)')
                            location_used = f"Pathos's default location ({pathos_local_dt.tzname()}) (fallback)"
                    else: # No Wolfram, just use Pathos's local time as best guess
                        pathos_local_dt = await self.ethos_core.get_local_datetime_for_user(self.config.ETHOS.get("pathos_user_id", "pathos"))
                        final_time_str = pathos_local_dt.strftime('%A, %B %d, %Y at %I:%M:%S %p %Z (%z)')
                        location_used = f"Pathos's default location ({pathos_local_dt.tzname()}) (location '{location}' not resolved)"
                else: # No location provided, and no user_id_context path taken, use Pathos's default
                    pathos_local_dt = await self.ethos_core.get_local_datetime_for_user(self.config.ETHOS.get("pathos_user_id", "pathos"))
                    final_time_str = pathos_local_dt.strftime('%A, %B %d, %Y at %I:%M:%S %p %Z (%z)')
                    location_used = f"Pathos's default location ({pathos_local_dt.tzname()})"

            # If target_tz was successfully set from an IANA location string
            if target_tz != timezone.utc and not final_time_str: # Ensure we haven't already set it via user_id_context
                 current_time_in_tz = datetime.now(target_tz)
                 final_time_str = current_time_in_tz.strftime('%A, %B %d, %Y at %I:%M:%S %p %Z (%z)')

            return {"success": True, "data": {"time_string": final_time_str, "location_used": location_used}, "message": final_time_str}
        except Exception as e:
            logger.error(f"Error in execute_get_current_time: {e}", exc_info=True)
            utc_now_fallback = datetime.now(timezone.utc).strftime('%A, %B %d, %Y at %I:%M:%S %p UTC')
            error_msg = f"Error determining time for '{location}': {str(e)}. Current UTC is {utc_now_fallback}."
            return {"success": False, "error": error_msg, "message": error_msg}

    async def execute_web_search(self, query: str, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        """Performs a web search using the configured WebSearchService."""
        logger.debug(f"Executing web_search for query: '{query}', user_id_context: {user_id_context}")
        if not self.config.ENABLE_WEB_SEARCH or not self.web_search_service:
            return {"success": False, "error": "Web search service is not enabled or available.", "message": "Web search is currently offline."}
        if not query or not isinstance(query, str) or not query.strip():
            return {"success": False, "error": "Missing or invalid query for web search.", "message": "I need a query to search for."}

        try:
            results = await self.web_search_service.perform_search(query)
            if results is not None: # perform_search can return None on internal error
                # Format results for LLM consumption if necessary, or return raw
                # For now, returning the list of result dicts
                message = f"Found {len(results)} results for '{query}'." if results else f"No direct results found for '{query}'."
                return {"success": True, "data": {"search_results": results if results else []}, "message": message}
            else:
                # This case implies an error within perform_search that didn't raise an exception but returned None
                error_msg = f"Web search for '{query}' failed to return results (internal service error)."
                return {"success": False, "error": error_msg, "message": error_msg}
        except Exception as e:
            logger.error(f"Error during web search execution for query '{query}': {e}", exc_info=True)
            error_msg = f"An unexpected error occurred during web search: {str(e)}"
            return {"success": False, "error": error_msg, "message": error_msg}

    async def execute_math_calculation(self, expression: str, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        """Calculates mathematical expressions, preferably using WolframAlpha."""
        logger.debug(f"Executing math_calculation for expression: '{expression}', user_id_context: {user_id_context}")
        if not expression or not isinstance(expression, str) or not expression.strip():
            return {"success": False, "error": "No valid mathematical expression provided.", "message": "I need an expression to calculate."}

        if self.config.ENABLE_WOLFRAM_ALPHA and self.wolfram_alpha_config and self.wolfram_alpha_config.get('app_id'):
            try:
                wa_res = await self.query_wolfram_alpha(expression) # query_wolfram_alpha needs to be implemented
                if wa_res.get('success') and wa_res.get('result'):
                    # Clean up Wolfram Alpha result if it's too verbose or has extra text
                    cleaned_result = " | ".join(line.strip() for line in wa_res['result'].splitlines() if line.strip())
                    final_result = cleaned_result if cleaned_result else "[Calculation resulted in empty response from Wolfram Alpha]"
                    return {"success": True, "data": {"result": final_result}, "message": f"The result of '{expression}' is {final_result}."}
                else:
                    error_msg = wa_res.get('message', f"Calculation of '{expression}' failed using Wolfram Alpha.")
                    return {"success": False, "error": error_msg, "message": error_msg}
            except Exception as e:
                logger.error(f"Error during math calculation via Wolfram Alpha for '{expression}': {e}", exc_info=True)
                # Fall through to basic eval if Wolfram fails, or return error
                error_msg = f"Error performing calculation for '{expression}' with Wolfram Alpha: {str(e)}."
                # For now, let's not fall back to eval for safety, just return error.
                return {"success": False, "error": error_msg, "message": error_msg}
        else:
            # Basic fallback (limited and potentially unsafe, consider removing or using a safer math parsing library)
            # For now, returning an error if WolframAlpha is not available.
            logger.warning("Wolfram Alpha not available for math calculation. No fallback implemented.")
            return {"success": False, "error": "Advanced calculation service is not available.", "message": "I can't perform that calculation right now."}

    async def execute_get_weather(self, location: str, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        """Fetches weather for a location, trying OWM then WolframAlpha."""
        logger.debug(f"Executing get_weather for location: '{location}', user_id_context: {user_id_context}")
        if not location or not isinstance(location, str) or not location.strip():
            return {"success": False, "error": "No valid location provided for weather.", "message": "I need a location to get the weather for."}

        # Try OpenWeatherMapService first
        if self.owm_service and self.owm_service.is_available:
            logger.debug(f"Attempting weather lookup for '{location}' via OpenWeatherMapService.")
            owm_res = await self.owm_service.get_current_weather(location)
            if owm_res.get("success"):
                weather_data = owm_res.get("weather_data", {})
                # Store derived IANA timezone if available and applicable
                if self.ethos_core and user_id_context and user_id_context not in getattr(self.ethos_core, 'system_user_ids', []):
                    if iana_tz := weather_data.get("iana_timezone"):
                        # This logic for storing derived_iana_timezone should ideally be a reusable part or inside EthosCore
                        existing_tz_fact = await self.ethos_core.get_user_fact('derived_iana_timezone', user_id_context)
                        should_store_tz = True
                        if existing_tz_fact and (content := existing_tz_fact.get('content')):
                            try:
                                if json.loads(content).get('value') == iana_tz:
                                    should_store_tz = False
                            except json.JSONDecodeError: pass # Problem parsing existing, better to overwrite
                        if should_store_tz:
                            logger.info(f"Storing derived IANA timezone '{iana_tz}' for user '{user_id_context}' from OWM weather for '{location}'.")
                            # Calling another tool's execute method internally is okay if it's a utility.
                            await self.execute_store_user_fact(
                                attribute_name="derived_iana_timezone",
                                attribute_value=iana_tz,
                                user_statement_context=f"Derived IANA timezone from OpenWeatherMap for location query '{location}'.",
                                user_id=user_id_context
                            )

                # Construct message for LLM
                conditions = weather_data.get('description', 'N/A')
                temp = weather_data.get('temperature', '--')
                unit = weather_data.get('unit', '')
                humidity = weather_data.get('humidity', 'N/A')
                wind = weather_data.get('wind_speed', 'N/A')
                message = f"Weather in {weather_data.get('location', location)}: {conditions}, Temperature: {temp}{unit}. Humidity: {humidity}. Wind: {wind}. (Source: OpenWeatherMap)"
                return {"success": True, "data": weather_data, "message": message}
            else:
                logger.warning(f"OpenWeatherMapService failed for '{location}': {owm_res.get('error')}")

        # Fallback to WolframAlpha if OWM failed or not available
        if self.config.ENABLE_WOLFRAM_ALPHA and self.wolfram_alpha_config and self.wolfram_alpha_config.get('app_id'):
            logger.debug(f"Falling back to WolframAlpha for weather in '{location}'.")
            wa_query = f"weather in {location}"
            wa_res = await self.query_wolfram_alpha(wa_query)
            if wa_res.get('success') and wa_res.get('result'):
                # Try to parse detailed weather from WolframAlpha's typical response structure if possible
                # This is a simplified version; a more robust parser might be needed for Wolfram's varied output.
                # For now, just returning the primary result text.
                weather_text = wa_res['result']
                message = f"Weather for {location} (via Wolfram Alpha): {weather_text}"
                return {"success": True, "data": {"raw_wolfram_weather": weather_text, "location_queried": location}, "message": message}
            else:
                error_msg = wa_res.get('message', f"Weather lookup for '{location}' failed using Wolfram Alpha.")
                logger.warning(error_msg)
                return {"success": False, "error": error_msg, "message": error_msg}

        final_error = "No weather services available or all services failed."
        logger.error(final_error + f" Location: {location}")
        return {"success": False, "error": final_error, "message": final_error}

    async def execute_store_user_fact(self, attribute_name: str, attribute_value: str, user_statement_context: str, user_id: str) -> Dict[str, Any]:
        """Stores a fact about a specific user in EthosCore memories."""
        logger.debug(f"Executing store_user_fact for user '{user_id}', attribute: '{attribute_name}', value: '{attribute_value}'")
        if not all([attribute_name, attribute_value, user_statement_context, user_id]):
            return {"success": False, "error": "Missing required parameters for storing user fact.", "message": "I need all details to store that fact."}
        if not self.ethos_core:
            return {"success": False, "error": "Memory system (EthosCore) not available.", "message": "I can't remember that right now, my memory system is offline."}

        norm_attr_name = attribute_name.lower().replace(" ", "_").strip()
        if not norm_attr_name:
            return {"success": False, "error": "Attribute name cannot be empty.", "message": "The fact needs a valid name."}

        # Content for the memory will be a JSON string containing attribute, value, and original context
        content_payload = {
            "attribute": norm_attr_name,
            "value": attribute_value,
            "original_user_statement": user_statement_context,
            "stored_by_tool_timestamp": datetime.now(timezone.utc).isoformat()
        }

        entry_data = {
            "type": "user_fact", # Specific memory type for user facts
            "content": json.dumps(content_payload),
            "salience": 1.5, # User facts are generally highly salient
            "metadata": {
                "user_id": user_id, # The user this fact is about
                "fact_attribute_key": norm_attr_name, # Normalized key for easier lookup
                "source": "pathos_tool_store_user_fact"
                # Optionally add user_id_context if it's different from user_id (e.g. Pathos storing fact about another user)
            }
        }

        try:
            # EthosCore's add_memory_entry also needs user_id_context for memory ownership/attribution
            # If user_id_context is Pathos storing a fact about 'user_id', then user_id_context is Pathos's ID.
            # For now, assuming the 'user_id' in entry_data.metadata is the primary subject.
            # The user_id_context for add_memory_entry might be the same as user_id here.
            await self.ethos_core.add_memory_entry(entry_data, user_id_context=user_id)
            message = f"Okay, I've noted that your {attribute_name} is {attribute_value}."
            if user_id != getattr(self.ethos_core, 'PATHOS_USER_ID', 'pathos_internal_user') and user_id != self.ethos_core.current_active_user_id: # A bit complex check
                 message = f"Okay, I've noted that {user_id}'s {attribute_name} is {attribute_value}."

            return {"success": True, "data": {"stored_fact": content_payload}, "message": message}
        except Exception as e:
            logger.error(f"Error storing user fact for '{user_id}', attribute '{attribute_name}': {e}", exc_info=True)
            error_msg = f"Failed to store user fact: {str(e)}"
            return {"success": False, "error": error_msg, "message": error_msg}

    async def execute_store_world_fact(self, fact_statement: str, source_description: str, topic_tags: Optional[List[str]] = None, confidence_level: float = 0.8, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        """Stores a general world fact in EthosCore memories."""
        logger.debug(f"Executing store_world_fact: '{fact_statement[:50]}...', source: '{source_description}', user_id_context: {user_id_context}")
        if not all([fact_statement, source_description]):
            return {"success": False, "error": "Missing required parameters (fact_statement, source_description).", "message": "I need the fact and its source to store it."}
        if not self.ethos_core:
            return {"success": False, "error": "Memory system (EthosCore) not available.", "message": "I can't remember that right now, my memory system is offline."}

        try:
            confidence = max(0.0, min(1.0, float(confidence_level)))
        except (ValueError, TypeError):
            confidence = 0.8 # Default confidence

        tags = sorted(list(set(tag.lower().strip() for tag in (topic_tags or []) if isinstance(tag, str) and tag.strip())))

        # Determine the user_id for metadata: if Pathos is storing it based on his own action/research,
        # it might be Pathos's ID. If it's from a user interaction, it might be that user's ID or a system ID.
        # For now, let's use a generic system ID or the provided user_id_context if available.
        metadata_user_id = user_id_context or getattr(self.ethos_core, 'PATHOS_USER_ID', 'pathos_internal_user')

        entry_data = {
            "type": "world_knowledge",
            "content": fact_statement,
            "salience": 0.7 + (confidence * 0.3), # Base salience plus confidence factor
            "metadata": {
                "user_id": metadata_user_id, # The user context under which this fact is being stored
                "source_description": source_description,
                "topic_tags": tags,
                "confidence_level": confidence,
                "stored_by_tool_timestamp": datetime.now(timezone.utc).isoformat(),
                "verification_status": "unverified" # New facts start as unverified
            }
        }

        try:
            # The user_id_context for add_memory_entry should be who is performing the action of storing.
            # If Pathos is doing it for general knowledge, it's Pathos's ID.
            # If a specific user asked Pathos to remember this, user_id_context might be that user's ID.
            # For "world_knowledge", it often makes sense for it to be under a general system context or Pathos.
            context_for_storage = user_id_context or getattr(self.ethos_core, 'PATHOS_USER_ID', 'world_knowledge_store')
            await self.ethos_core.add_memory_entry(entry_data, user_id_context=context_for_storage)
            message = f"Okay, I've noted the fact: '{fact_statement[:70]}...' from source '{source_description}'."
            return {"success": True, "data": {"stored_fact_statement": fact_statement}, "message": message}
        except Exception as e:
            logger.error(f"Error storing world fact '{fact_statement[:50]}...': {e}", exc_info=True)
            error_msg = f"Failed to store world fact: {str(e)}"
            return {"success": False, "error": error_msg, "message": error_msg}

    async def execute_deep_research(self, research_query: str, num_searches_to_perform: int = 3, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        """Performs multiple web searches and synthesizes results into a report using an LLM."""
        logger.debug(f"Executing deep_research for query: '{research_query}', num_searches: {num_searches_to_perform}, user: {user_id_context}")
        if not self.config.ENABLE_WEB_SEARCH or not self.web_search_service:
            return {"success": False, "error": "Web search service is not enabled or available for deep research.", "message": "Web search is currently offline, so I can't do deep research."}

        llm_config_for_synthesis = self.logos_research_config # Specific LLM role for this
        if not llm_config_for_synthesis or not llm_config_for_synthesis.get('url'): # Check URL as an indicator of config presence
            return {"success": False, "error": "Deep research LLM (LOGOS_DEEP_RESEARCH) not configured.", "message": "My deep research capabilities are not configured right now."}

        if not research_query or not isinstance(research_query, str) or not research_query.strip():
            return {"success": False, "error": "Missing or invalid research_query for deep research.", "message": "I need a query to research."}

        try:
            # Generate multiple search queries based on the initial research_query
            queries = [research_query]
            if num_searches_to_perform > 1: queries.append(f"different perspectives on {research_query}")
            if num_searches_to_perform > 2: queries.append(f"key aspects and details about {research_query}")
            if num_searches_to_perform > 3: queries.append(f"criticisms or challenges related to {research_query}")
            queries_to_run = queries[:max(1, num_searches_to_perform)] # Ensure at least one query

            aggregated_search_text = ""
            total_snippets_collected = 0
            max_snippets_per_sub_query = 3 # Limit snippets from each sub-query

            for i, sub_query in enumerate(queries_to_run):
                logger.debug(f"Deep research sub-query {i+1}: '{sub_query}'")
                search_results = await self.web_search_service.perform_search(sub_query)
                if search_results:
                    for res_idx, res_data in enumerate(search_results[:max_snippets_per_sub_query]):
                        aggregated_search_text += f"--- Source {total_snippets_collected+1} (Sub-query: '{sub_query}') ---\n"
                        aggregated_search_text += f"Title: {res_data.get('title', 'N/A')}\n"
                        aggregated_search_text += f"Link: {res_data.get('link', '#')}\n"
                        # Limit snippet length for LLM context
                        snippet_text = res_data.get('snippet', '')[:700] # Increased snippet length slightly
                        aggregated_search_text += f"Snippet: {snippet_text}\n\n"
                        total_snippets_collected +=1
                await asyncio.sleep(0.2) # Small delay between search API calls

            if not aggregated_search_text:
                message = "No web search results found for the deep research query."
                return {"success": True, "data": {"report": "No information found from web searches.", "source_snippets_count": 0}, "message": message} # Success=True as tool ran, but no data

            # Limit overall text size for LLM prompt
            # Max tokens for LLM minus some buffer for the prompt and response. Assume 3 chars/token.
            max_llm_input_chars = ((llm_config_for_synthesis.get('max_tokens', 4096) - 1024) * 3)
            if len(aggregated_search_text) > max_llm_input_chars:
                aggregated_search_text = aggregated_search_text[:max_llm_input_chars] + "\n[...content truncated...]"
                logger.info(f"Deep research aggregated text truncated to {max_llm_input_chars} chars for LLM.")

            system_prompt_template = load_system_prompt("deep_research_llm_system_prompt",
                                                       "You are a research assistant. Synthesize the provided web search snippets into a comprehensive and neutral report on the given query. Focus on facts and key information. Structure your report clearly.")

            user_prompt_content = (
                f"Research Query: '{research_query}'\n\n"
                "Collected Information from Web Searches:\n"
                "---------------------------------------\n"
                f"{aggregated_search_text}\n"
                "---------------------------------------\n\n"
                "Please synthesize this information into a concise and informative report about the research query."
            )

            # Use _call_logos_llm which now uses self.llm_client
            report_text = await self._call_logos_llm(
                llm_config=llm_config_for_synthesis,
                llm_messages_for_synthesis=[
                    {"role": "system", "content": system_prompt_template},
                    {"role": "user", "content": user_prompt_content}
                ]
            )

            if not report_text or report_text.startswith("["): # Check for error string from _call_logos_llm
                error_msg = f"LLM synthesis for deep research failed or returned an error: {report_text}"
                return {"success": False, "error": error_msg, "message": error_msg}

            message = f"Deep research report generated for '{research_query}' based on {total_snippets_collected} snippets."
            return {"success": True, "data": {"report": report_text, "source_snippets_count": total_snippets_collected}, "message": message}

        except Exception as e:
            logger.error(f"Error during deep research execution for query '{research_query}': {e}", exc_info=True)
            error_msg = f"An unexpected error occurred during deep research: {str(e)}"
            return {"success": False, "error": error_msg, "message": error_msg}

    async def execute_get_news_headlines(self, query: Optional[str] = None, category: Optional[str] = None, max_articles_to_process: int = 3, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        """Fetches news headlines, optionally summarized and sentiment-analyzed."""
        logger.debug(f"Executing get_news_headlines. Query: '{query}', Category: '{category}', MaxProcess: {max_articles_to_process}, User: {user_id_context}")
        if not self.news_config or not self.news_config.get('enabled') or not self.news_config.get('api_key'):
            logger.warning("News API not configured or enabled for execute_get_news_headlines.")
            return {"success": False, "error": "News API not configured or enabled.", "message": "I can't fetch news right now as the service isn't set up."}

        # Create a temporary config for this specific call, allowing overrides
        call_specific_news_config = self.news_config.copy()
        if query:
            call_specific_news_config['search_keywords'] = query
            call_specific_news_config.pop('categories', None) # Search overrides category
        elif category:
            call_specific_news_config['categories'] = category
            call_specific_news_config.pop('search_keywords', None)
        else: # Neither query nor category, use default category from main config or 'general'
            call_specific_news_config['categories'] = self.news_config.get('categories', 'general')
            call_specific_news_config.pop('search_keywords', None)

        call_specific_news_config['limit'] = max(5, max_articles_to_process * 2) # Fetch more to have choice, ensure at least 5 for some variety

        fetched_articles: List[Dict[str, str]] = await self._fetch_news_headlines_with_details(call_specific_news_config)

        if not fetched_articles:
            message = "No news articles found for the given criteria."
            logger.info(message)
            return {"success": True, "data": {"articles": []}, "message": message}

        processed_articles: List[Dict[str, Any]] = []
        num_to_fully_process = min(len(fetched_articles), max_articles_to_process)
        articles_to_process_fully = fetched_articles[:num_to_fully_process]

        techne_llm_config = self.logos_techne_config # For summarization and sentiment

        for article_data in articles_to_process_fully:
            title = article_data.get("title", "N/A")
            content_for_summary = article_data.get("content_for_summary", "") # This is usually snippet or description
            original_description = article_data.get("original_description", "") # Could be same as content_for_summary
            source_name = article_data.get("source_name", "Unknown Source")
            url = article_data.get("url", "#")
            published_at = article_data.get("published_at", "")

            summary = original_description # Default summary is the original description/snippet
            if content_for_summary.strip() and techne_llm_config:
                try:
                    summarize_prompt = f"Summarize the following news article content in 1-2 concise sentences: {content_for_summary}"
                    llm_summary = await self._call_logos_llm( # _call_logos_llm uses self.llm_client
                        llm_config=techne_llm_config,
                        llm_messages_for_synthesis=[{"role": "user", "content": summarize_prompt}] # Pass as messages
                    )
                    if llm_summary and not llm_summary.startswith("["): # Check for error string
                        summary = llm_summary
                    else:
                        logger.warning(f"Summarization failed for article '{title}'. Using original. LLM output: {llm_summary}")
                except Exception as e_summ:
                    logger.error(f"Error during summarization for article '{title}': {e_summ}", exc_info=True)

            text_for_sentiment = summary if summary != original_description and summary.strip() else content_for_summary
            classified_sentiment = "neutral_interesting" # Default

            if text_for_sentiment.strip() and techne_llm_config:
                try:
                    sentiment_prompt = f"Classify the sentiment of the following news text as 'positive', 'negative', 'neutral_interesting', or 'concerning'. Respond with only one of these four labels. News: {text_for_sentiment}"
                    llm_sentiment_label = await self._call_logos_llm(
                        llm_config=techne_llm_config,
                        llm_messages_for_synthesis=[{"role": "user", "content": sentiment_prompt}]
                    )
                    if llm_sentiment_label:
                        cleaned_label = llm_sentiment_label.lower().strip().replace("'", "").replace('"',"").splitlines()[0]
                        valid_sentiments = ['positive', 'negative', 'neutral_interesting', 'concerning']
                        if cleaned_label in valid_sentiments:
                            classified_sentiment = cleaned_label
                        else:
                            logger.warning(f"Sentiment classification for article '{title}' returned invalid label: '{llm_sentiment_label}'. Defaulting.")
                    else:
                        logger.warning(f"Sentiment classification for article '{title}' returned no label. Defaulting.")
                except Exception as e_sent:
                    logger.error(f"Error during sentiment classification for article '{title}': {e_sent}", exc_info=True)

            processed_articles.append({
                "title": title, "summary": summary, "source_name": source_name, "url": url,
                "published_at": published_at, "classified_sentiment": classified_sentiment,
                "original_description": original_description
            })

        # Add remaining fetched articles with basic info if more were fetched than processed fully
        if len(fetched_articles) > num_to_fully_process:
            for article_data in fetched_articles[num_to_fully_process:]:
                 processed_articles.append({
                    "title": article_data.get("title", "N/A"),
                    "summary": article_data.get("original_description", ""), # Use original desc as summary
                    "source_name": article_data.get("source_name", "Unknown Source"),
                    "url": article_data.get("url", "#"),
                    "published_at": article_data.get("published_at", ""),
                    "classified_sentiment": "neutral_interesting", # Default for non-fully-processed
                    "original_description": article_data.get("original_description", "")
                })

        final_message = f"Processed {len(articles_to_process_fully)} news articles fully. Total articles returned: {len(processed_articles)}."
        logger.info(f"LogosCore execute_get_news_headlines: {final_message}")
        return {"success": True, "data": {"articles": processed_articles}, "message": final_message}

    async def execute_add_pathos_event_to_calendar(self, title: str, start_date_str: str, end_date_str: str, event_type: str, description: Optional[str] = None, location: Optional[str] = None, activity_theme: Optional[str] = None, planned_sites_or_tasks: Optional[List[str]] = None, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        """Adds an event to Pathos's schedule via EthosCore's Chronos bridge."""
        logger.debug(f"Executing add_pathos_event_to_calendar: '{title}' from {start_date_str} to {end_date_str}, user: {user_id_context}")
        if not all([title, start_date_str, end_date_str, event_type]):
            return {"success": False, "error": "Missing required parameters (title, start_date_str, end_date_str, event_type).", "message": "I need all the event details to schedule it."}
        if not self.ethos_core or not hasattr(self.ethos_core, 'chronos_bridge_add_event'):
            return {"success": False, "error": "Calendar scheduling system (EthosCore/Chronos) not available.", "message": "I can't access the calendar right now."}

        try:
            # user_id_for_event should be Pathos's ID if Pathos is scheduling for himself.
            # The tool is 'add_pathos_event', so it's for Pathos.
            pathos_user_id = getattr(self.ethos_core, 'PATHOS_USER_ID', 'pathos_internal_user') # Get Pathos's ID

            event_id = await self.ethos_core.chronos_bridge_add_event(
                title=title,
                start_date_str=start_date_str,
                end_date_str=end_date_str,
                event_type_str=event_type, # Assuming event_type is string here, ChronosEngine will handle enum.
                description=description,
                location=location,
                activity_theme=activity_theme,
                planned_sites_or_tasks=planned_sites_or_tasks,
                user_id_for_event=pathos_user_id
            )
            if event_id:
                message = f"Successfully scheduled '{title}' on {start_date_str}."
                return {"success": True, "data": {"event_id": event_id, "title": title, "start_date": start_date_str}, "message": message}
            else:
                error_msg = f"Failed to schedule '{title}'. The calendar system might have rejected it."
                return {"success": False, "error": error_msg, "message": error_msg}
        except Exception as e:
            logger.error(f"Error executing add_pathos_event_to_calendar for '{title}': {e}", exc_info=True)
            error_msg = f"An unexpected error occurred while scheduling '{title}': {str(e)}"
            return {"success": False, "error": error_msg, "message": error_msg}

    # --- Bookshelf Tool Execution Methods ---
    async def execute_bookshelf_add_document(self, document_name: str, document_content: str, document_source: Optional[str] = "unknown", topics: Optional[List[str]] = None, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        logger.debug(f"Executing bookshelf_add_document: '{document_name}', user: {user_id_context}")
        if not self.bookshelf_handler:
            return {"success": False, "error": "Bookshelf service not available.", "message": "My bookshelf is currently unavailable."}
        if not document_name or not document_content:
            return {"success": False, "error": "Document name and content are required.", "message": "I need both a name and content for the document."}

        try:
            result = await self.bookshelf_handler.add_document_to_ragbits(
                document_name=document_name,
                document_content=document_content,
                document_source=document_source or "unknown",
                topics=topics or []
            )
            # Assuming result is like: {'success': bool, 'message': str, 'doc_id': str, 'num_chunks': int}
            if isinstance(result, dict) and result.get("success"):
                return {"success": True, "data": result, "message": result.get("message", "Document added to bookshelf.")}
            elif isinstance(result, dict):
                return {"success": False, "error": result.get("message", "Failed to add document."), "data": result, "message": result.get("message", "Failed to add document.")}
            else:
                return {"success": False, "error": "Bookshelf handler returned an unexpected response.", "message": "There was an issue adding the document."}
        except Exception as e:
            logger.error(f"Error in execute_bookshelf_add_document for '{document_name}': {e}", exc_info=True)
            return {"success": False, "error": f"System error adding document: {str(e)}", "message": "A system error occurred while adding the document."}

    async def execute_bookshelf_query(self, query_text: str, document_name: Optional[str] = None, topics_filter: Optional[List[str]] = None, top_k: Optional[int] = 3, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        logger.debug(f"Executing bookshelf_query: '{query_text[:50]}...', user: {user_id_context}")
        if not self.bookshelf_handler:
            return {"success": False, "error": "Bookshelf service not available.", "message": "My bookshelf is currently unavailable."}
        if not query_text:
            return {"success": False, "error": "Query text is required.", "message": "I need something to search for in the bookshelf."}

        try:
            results = await self.bookshelf_handler.query_ragbits(
                query_text=query_text,
                document_name=document_name,
                topics_filter=topics_filter,
                top_k=top_k or 3
            )
            # results expected to be List[Dict[str, Any]] (chunks with metadata and score)
            message = f"Bookshelf query returned {len(results)} relevant chunks."
            return {"success": True, "data": {"query_results": results}, "message": message}
        except Exception as e:
            logger.error(f"Error in execute_bookshelf_query: {e}", exc_info=True)
            return {"success": False, "error": f"System error querying bookshelf: {str(e)}", "message": "A system error occurred while searching the bookshelf."}

    async def execute_bookshelf_list_documents(self, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        logger.debug(f"Executing bookshelf_list_documents, user: {user_id_context}")
        if not self.bookshelf_handler:
            return {"success": False, "error": "Bookshelf service not available.", "message": "My bookshelf is currently unavailable."}
        try:
            documents = await self.bookshelf_handler.list_all_documents()
            # documents expected to be List[Dict[str, Any]] with doc summaries
            message = f"Found {len(documents)} documents in the bookshelf."
            return {"success": True, "data": {"documents": documents}, "message": message}
        except Exception as e:
            logger.error(f"Error in execute_bookshelf_list_documents: {e}", exc_info=True)
            return {"success": False, "error": f"System error listing bookshelf documents: {str(e)}", "message": "A system error occurred while listing documents."}

    async def execute_bookshelf_get_document_raw_text(self, document_name: str, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        logger.debug(f"Executing bookshelf_get_document_raw_text for: '{document_name}', user: {user_id_context}")
        if not self.bookshelf_handler:
            return {"success": False, "error": "Bookshelf service not available.", "message": "My bookshelf is currently unavailable."}
        if not document_name:
            return {"success": False, "error": "Document name is required.", "message": "I need the name of the document to retrieve its text."}
        try:
            doc_data = await self.bookshelf_handler.get_document_by_name(document_name)
            if doc_data and doc_data.get("content_full"):
                message = f"Retrieved raw text for document '{document_name}'."
                return {"success": True, "data": {"document_name": document_name, "raw_text": doc_data["content_full"]}, "message": message}
            else:
                error_msg = f"Document '{document_name}' not found in bookshelf or has no raw text content."
                return {"success": False, "error": error_msg, "data": None, "message": error_msg}
        except Exception as e:
            logger.error(f"Error in execute_bookshelf_get_document_raw_text for '{document_name}': {e}", exc_info=True)
            return {"success": False, "error": f"System error retrieving document raw text: {str(e)}", "message": "A system error occurred."}

    async def execute_bookshelf_remove_document(self, document_name: str, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        logger.debug(f"Executing bookshelf_remove_document for: '{document_name}', user: {user_id_context}")
        if not self.bookshelf_handler:
            return {"success": False, "error": "Bookshelf service not available.", "message": "My bookshelf is currently unavailable."}
        if not document_name:
            return {"success": False, "error": "Document name is required for removal.", "message": "I need the name of the document to remove."}
        try:
            result = await self.bookshelf_handler.delete_document_from_ragbits(document_name)
            # result expected: {'success': bool, 'message': str}
            if isinstance(result, dict) and result.get("success"):
                return {"success": True, "message": result.get("message", f"Document '{document_name}' removed from bookshelf.")}
            elif isinstance(result, dict):
                 return {"success": False, "error": result.get("message", f"Failed to remove document '{document_name}' from bookshelf."), "message": result.get("message")}
            else:
                return {"success": False, "error": "Bookshelf handler returned an unexpected response for remove document.", "message": "Issue removing document."}
        except Exception as e:
            logger.error(f"Error executing bookshelf_remove_document for '{document_name}': {e}", exc_info=True)
            return {"success": False, "error": f"System error removing document: {str(e)}", "message": "A system error occurred."}

    async def process_uploaded_document(self, file_content_bytes: bytes, filename: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Parses a document from bytes and returns extracted text."""
        logger.info(f"LogosCore: Processing uploaded document '{filename}' for text extraction, user: {user_id}.")
        file_ext = Path(filename).suffix.lower()
        if file_ext not in SUPPORTED_EXTENSIONS:
            return {"success": False, "message": f"Unsupported file type: '{file_ext}'. Supported: {SUPPORTED_EXTENSIONS}"}

        try:
            text = await parse_document(filename, file_content_bytes) # parse_document is from utils
            if not text or not text.strip():
                return {"success": False, "message": f"No text could be extracted from document '{filename}'."}
            return {"success": True, "extracted_text": text, "message": f"Successfully extracted text from '{filename}'."}
        except ValueError as e_val: # Specific error from parse_document for bad format
            logger.warning(f"ValueError processing document '{filename}': {e_val}")
            return {"success": False, "message": str(e_val)}
        except ImportError as e_imp: # Missing dependency for a file type
            logger.error(f"ImportError processing document '{filename}': {e_imp.name} library is missing.", exc_info=True)
            return {"success": False, "message": f"Cannot process '{filename}': Required library '{e_imp.name}' is not installed."}
        except Exception as e:
            logger.error(f"Unexpected error processing document '{filename}': {e}", exc_info=True)
            return {"success": False, "message": f"A system error occurred while processing the document '{filename}'."}

    async def add_document_to_rag(self, extracted_text: str, filename: str, user_id: Optional[str] = None, doc_id: Optional[str] = None) -> Dict[str, Any]:
        """Chunks text and adds it to EthosCore document chunks storage."""
        logger.info(f"LogosCore: Adding extracted text from '{filename}' to RAG system, user: {user_id}, doc_id: {doc_id}.")
        if not extracted_text or not extracted_text.strip():
            return {"success": False, "message": "No text provided to add to RAG."}
        if not self.ethos_core:
             return {"success": False, "error": "EthosCore (memory system) not available for RAG.", "message": "Memory system is offline."}

        final_doc_id = doc_id or str(uuid.uuid4())
        try:
            # Get chunking parameters from config (ETHOS section)
            chunk_size = self.config.ETHOS.get('text_chunk_size', 1000)
            chunk_overlap = self.config.ETHOS.get('text_chunk_overlap', 150)

            chunks = chunk_text_by_char(extracted_text, chunk_size, chunk_overlap)
            if not chunks:
                return {"success": False, "message": f"Failed to split document '{filename}' into manageable text chunks."}

            await self.ethos_core.add_document_chunks(final_doc_id, filename, chunks)
            message = f"Document '{filename}' (ID: {final_doc_id}) successfully processed and stored as {len(chunks)} chunks for RAG."
            return {"success": True, "doc_id": final_doc_id, "num_chunks": len(chunks), "message": message}
        except Exception as e:
            logger.error(f"Error adding document '{filename}' (ID: {final_doc_id}) to RAG via EthosCore: {e}", exc_info=True)
            return {"success": False, "error": f"System error adding document to RAG: {str(e)}", "message": "A system error occurred."}

    async def execute_process_document_for_rag(self, file_content_b64: str, filename: str, user_id: Optional[str] = None, doc_id: Optional[str] = None, user_id_context: Optional[str] = None) -> Dict[str, Any]:
        """
        Decodes a base64 file, extracts text, and adds it to the RAG system (via EthosCore document chunks).
        This is a higher-level tool that combines parsing and RAG ingestion.
        """
        logger.info(f"Executing process_document_for_rag: '{filename}', user: {user_id_context or user_id}")
        try:
            file_content_bytes = base64.b64decode(file_content_b64)
        except Exception as e_decode:
            logger.error(f"Base64 decoding failed for {filename}: {e_decode}", exc_info=True)
            return {"success": False, "error": f"Invalid base64 content for file {filename}.", "message": "The file content doesn't seem to be encoded correctly."}

        # Step 1: Process (parse) the document to extract text
        parse_result = await self.process_uploaded_document(file_content_bytes, filename, user_id_context or user_id)
        if not parse_result.get("success"):
            return {"success": False, "error": parse_result.get("message", "Failed to parse document."), "message": parse_result.get("message", "Could not read the document text.")}

        extracted_text = parse_result.get("extracted_text")
        if not extracted_text: # Should be caught by process_uploaded_document, but double check
            return {"success": False, "error": f"No text could be extracted from document '{filename}'.", "message": "The document seems to be empty or unreadable."}

        # Step 2: Add the extracted text to RAG (via EthosCore document chunks)
        # The user_id here is for attributing who uploaded/initiated this.
        # The actual document chunks in EthosCore might have a system user_id.
        rag_add_result = await self.add_document_to_rag(
            extracted_text=extracted_text,
            filename=filename,
            user_id=user_id_context or user_id, # For logging/attribution of the RAG process
            doc_id=doc_id # Optional pre-defined document ID
        )

        if rag_add_result.get("success"):
            message = f"Document '{filename}' has been processed and its content is now available for me to reference. {rag_add_result.get('message', '')}"
            return {"success": True, "data": rag_add_result, "message": message}
        else:
            error_msg = rag_add_result.get("error", "Failed to add document content to my knowledge base.")
            return {"success": False, "error": error_msg, "message": error_msg}

    # Placeholder for other tool execution methods that might have existed
    # ... etc.

    async def execute_task(self, task: Task) -> Task: # Task from .task_model
        """
        Executes a Task object by dispatching to the appropriate tool execution method
        based on task.type. This adapts the older Task model to the new execute_X_tool methods.
        """
        logger.info(f"LogosCore: execute_task received Task ID {task.task_id} of type '{task.type}' for user '{task.user_id}'. Current status: {task.status}")

        if task.status not in ["pending", "retry", "in_progress"]: # Allow in_progress to be picked up if somehow stuck
            logger.warning(f"LogosCore: Task {task.task_id} (type: {task.type}) has status '{task.status}' and will not be executed by execute_task dispatcher.")
            return task

        if task.status != "in_progress": # Only update to in_progress if it wasn't already
            task.update_status("in_progress")

        args_for_executor = task.input_params.copy() if task.input_params else {}
        # Ensure user_id_context is passed if the task has a user_id
        if task.user_id:
            args_for_executor["user_id_context"] = task.user_id
            # Some tools might expect 'user_id' as a kwarg, ensure it's there if not user_id_context
            if "user_id" not in args_for_executor and "user_id" in (getattr(self.TOOL_DISPATCH_MAP.get(task.type), '__code__', None) or {}).co_varnames:
                 args_for_executor["user_id"] = task.user_id


        tool_executor: Optional[ToolExecutor] = self.TOOL_DISPATCH_MAP.get(task.type)

        if tool_executor:
            try:
                logger.debug(f"execute_task: Calling tool '{task.type}' with derived args: {args_for_executor}")
                tool_output_dict = await tool_executor(**args_for_executor)

                task.result = tool_output_dict # Store the entire dict
                task.result_summary = tool_output_dict.get("message") # Use 'message' as summary

                if tool_output_dict.get("success"):
                    task.update_status("success")
                    logger.info(f"Task {task.task_id} (type: {task.type}) completed successfully via execute_task.")
                else:
                    task.error_message = tool_output_dict.get("error", "Tool execution failed via execute_task.")
                    task.update_status("failure")
                    logger.warning(f"Task {task.task_id} (type: {task.type}) failed via execute_task. Error: {task.error_message}")

            except TypeError as te:
                logger.error(f"LogosCore: TypeError in execute_task for {task.task_id} (type: {task.type}). Args: {args_for_executor}. Error: {te}", exc_info=True)
                task.error_message = f"Tool argument mismatch for '{task.type}': {str(te)}"
                task.update_status("failure")
            except Exception as e:
                logger.error(f"LogosCore: Unhandled error in execute_task for {task.task_id} (type: {task.type}): {e}", exc_info=True)
                task.error_message = f"Unhandled execution error: {str(e)}"
                task.update_status("failure")
        else:
            logger.warning(f"LogosCore: execute_task - Unsupported task type '{task.type}' for task ID {task.task_id}.")
            task.error_message = f"Unsupported task type in execute_task: {task.type}"
            task.update_status("failure")

        if task.status in ["success", "failure", "cancelled"] and not task.completed_at:
            task.completed_at = task.updated_at if task.updated_at else datetime.now(timezone.utc)

        return task

# Minimal main.py or test setup would need to instantiate LogosCore with its dependencies,
# including the FirmamentModule.
# e.g., logos_core = LogosCore(config, ethos_core, llm_client, firmament_module_instance)
# And PathosInterface would call logos_core.execute_tools(...)
