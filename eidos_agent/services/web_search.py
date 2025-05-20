# eidos_agent/services/web_search.py
import httpx
import json
import logging
from typing import List, Dict, Optional
import urllib.parse # For URL encoding query parameters

# Use the NEW BraveSearchConfig
from eidos_agent.core.config import Config, BraveSearchConfig 
from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

class WebSearchService:
    """
    Service to perform web searches using the Brave Search API.
    """
    BRAVE_API_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, config: Config):
        # Use the Brave config getter
        self.brave_config: Optional[BraveSearchConfig] = config.get_brave_search_config() 
        timeout = self.brave_config['timeout'] if self.brave_config else 15
        self.http_client = httpx.AsyncClient(timeout=timeout)
        if not self.brave_config:
            logger.warning("WebSearchService initialized BUT Brave Search API key is not configured. Searches will fail.")

    async def perform_search(self, query: str) -> Optional[List[Dict[str, str]]]:
        """
        Performs a web search for the given query using Brave Search API.

        Args:
            query: The search query string.

        Returns:
            A list of dictionaries, each containing 'title', 'link', 'snippet',
            or None if the search failed or is not configured.
        """
        if not self.brave_config or not self.brave_config['api_key']:
            logger.error("Brave Search API key not configured. Cannot perform web search.")
            return None
        if not query:
            logger.warning("Web search attempted with empty query.")
            return []

        num_results = self.brave_config.get('max_results_per_query', 3)
        
        # Prepare request parameters and headers for Brave API (typically GET request)
        params = {
            "q": query,
            "count": num_results,
            # Add other params as needed, e.g., "safesearch": "moderate"
        }
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip", # Recommended by Brave docs
            "X-Subscription-Token": self.brave_config['api_key'] 
        }

        logger.info(f"Performing web search via Brave Search API (max {num_results} results) for query: '{query}'")
        try:
            # Use GET request for Brave Search API
            response = await self.http_client.get(self.BRAVE_API_ENDPOINT, headers=headers, params=params)
            response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx
            results_data = response.json()

            processed_results = []
            
            # --- PARSE BRAVE RESPONSE STRUCTURE ---
            # IMPORTANT: Check Brave API docs for the exact structure. 
            # It often has results under keys like 'web' -> 'results'.
            web_results = results_data.get("web", {}).get("results", [])
            
            for item in web_results:
                # Extract relevant fields - field names might differ from Serper!
                # Common possibilities: 'title', 'url', 'description', 'snippet'
                title = item.get("title", "N/A")
                link = item.get("url", "N/A") 
                snippet = item.get("description", item.get("snippet", "N/A")) # Use 'description' or 'snippet'

                processed_results.append({
                    "title": title,
                    "link": link,
                    "snippet": snippet
                })
                if len(processed_results) >= num_results:
                    break 
            
            # Brave might also have sections like 'faq', 'infobox', 'locations' etc.
            # You could add logic here to extract info from those if desired, similar
            # to how we checked for Serper's 'answerBox' or 'knowledgeGraph'.
            # For example, check results_data.get("infobox") 
            
            # --- END BRAVE RESPONSE PARSING ---

            logger.info(f"Brave Search for '{query}' returned {len(processed_results)} processed result(s).")
            return processed_results

        except httpx.HTTPStatusError as e:
            logger.error(f"Brave Search API error searching for '{query}': {e.response.status_code} - {e.response.text}")
            return None # Indicate failure
        except httpx.RequestError as e:
             logger.error(f"Network error during Brave Search for '{query}': {e}")
             return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response from Brave Search for '{query}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during Brave web search for '{query}': {e}", exc_info=True)
            return None

    async def close(self):
        """Closes the underlying HTTP client."""
        await self.http_client.aclose()
        logger.info("WebSearchService (Brave) HTTP client closed.")