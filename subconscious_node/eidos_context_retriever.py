"""
External Context Retriever for Pathos Subconscious Node

This module connects to the main Eidos system to retrieve external context
for thought generation, replacing the circular feedback loop with fresh
external input.
"""

import json
import logging
import httpx
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class EidosContextRetriever:
    def __init__(self, base_url: str = "http://100.89.52.89:8080", timeout: int = 10):
        """
        Initialize the context retriever.
        
        Args:
            base_url: Base URL of the main Eidos system
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
    
    async def get_external_context(self) -> Dict[str, Any]:
        """
        Retrieve external context from the main Eidos system.
        
        Returns:
            Dictionary containing external context data
        """
        context = {
            "memories": [],
            "conversation": [],
            "mood": None,
            "activity": None,
            "knowledge": [],
            "timestamp": None
        }
        
        try:
            # Get recent memories
            memories = await self._get_recent_memories()
            if memories:
                context["memories"] = memories
            
            # Get current mood
            mood = await self._get_current_mood()
            if mood:
                context["mood"] = mood
            
            # Get current activity
            activity = await self._get_current_activity()
            if activity:
                context["activity"] = activity
            
            # Get conversation context
            conversation = await self._get_conversation_context()
            if conversation:
                context["conversation"] = conversation
            
            logger.debug(f"Retrieved external context: {len(context['memories'])} memories, mood: {context['mood']}")
            
        except Exception as e:
            logger.warning(f"Failed to retrieve external context: {e}")
            # Return fallback context
            context = self._get_fallback_context()
        
        return context
    
    async def _get_recent_memories(self, top_k: int = 5, min_salience: float = 0.3) -> List[Dict]:
        """Retrieve recent memories from main system."""
        try:
            response = await self.client.get(
                f"{self.base_url}/v1/memory/search",
                params={
                    "query": "recent experiences",
                    "top_k": top_k,
                    "min_salience": min_salience
                }
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("memories", [])
        except Exception as e:
            logger.debug(f"Failed to get memories: {e}")
        return []
    
    async def _get_current_mood(self) -> Optional[Dict]:
        """Retrieve current mood from main system."""
        try:
            response = await self.client.get(f"{self.base_url}/v1/status/mood")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.debug(f"Failed to get mood: {e}")
        return None
    
    async def _get_current_activity(self) -> Optional[Dict]:
        """Retrieve current activity from main system."""
        try:
            response = await self.client.get(f"{self.base_url}/v1/status/activity")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.debug(f"Failed to get activity: {e}")
        return None
    
    async def _get_conversation_context(self) -> List[str]:
        """Retrieve recent conversation context from main system."""
        try:
            response = await self.client.get(f"{self.base_url}/v1/conversation/recent")
            if response.status_code == 200:
                data = response.json()
                return data.get("messages", [])
        except Exception as e:
            logger.debug(f"Failed to get conversation: {e}")
        return []
    
    def _get_fallback_context(self) -> Dict[str, Any]:
        """Return fallback context when main system is unavailable."""
        return {
            "memories": ["Reflecting on past experiences", "Considering recent thoughts"],
            "conversation": [],
            "mood": {"energy": 0.5, "focus": 0.6, "social": 0.4},
            "activity": "contemplating",
            "knowledge": ["general observations", "philosophical musings"],
            "timestamp": None,
            "fallback": True
        }
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()


# Synchronous version for compatibility with existing code
def get_external_context(config_data: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Synchronous wrapper for getting external context.
    
    Args:
        config_data: Configuration dictionary containing eidos_api_base_url
    
    Returns:
        External context dictionary
    """
    import asyncio
    
    # Get base URL from config
    base_url = "http://100.89.52.89:8080"  # Default
    if config_data and "eidos_api_base_url" in config_data:
        base_url = config_data["eidos_api_base_url"]
    
    # Create retriever and get context
    retriever = EidosContextRetriever(base_url)
    
    try:
        # Handle both sync and async environments
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, create a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, retriever.get_external_context())
                    context = future.result(timeout=10)
            else:
                context = loop.run_until_complete(retriever.get_external_context())
        except RuntimeError:
            # No event loop, create one
            context = asyncio.run(retriever.get_external_context())
    except Exception as e:
        logger.warning(f"Failed to get external context: {e}")
        context = retriever._get_fallback_context()
    finally:
        retriever.close()
    
    return context
