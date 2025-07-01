import logging
from typing import Dict, Any, Optional, List, Tuple # Added Tuple

# Attempt to import EthosCore and MemoryEntry for type hinting
try:
    from .core import EthosCore
    from .memory_storage import MemoryEntry
    # If LLMClient is used directly, import it here too.
    # from ...llm_integrations.llm_client import LLMClient
    # from ...core.config import LLMConfig
except ImportError:
    # Define minimal dummy classes for type hinting if imports fail
    class MemoryEntry(Dict[str, Any]): # type: ignore
        pass

    class EthosCore: # type: ignore
        def __init__(self, config: Any = None): # Dummy config
            self.config = config
            # Mock methods that might be called by ReflectionEngine or its helpers
            async def add_memory_entry(self, entry_data: Dict, user_id_context: Optional[str] = None) -> MemoryEntry:
                return MemoryEntry(id="dummy_insight_id", **entry_data)

            # Mock for _call_llm_for_insights if it uses a generic call method from ethos_core
            async def _call_llm_for_internal_task(self, messages: List[Dict[str, Any]], llm_role_to_use: str) -> Optional[str]:
                return json.dumps({"insights": ["Dummy insight 1", "Dummy insight 2"]})

            # Mock for memory fetching
            async def get_memories_for_summary(self, user_id: str, start_time_utc: Any, end_time_utc: Any, types: List[str], limit: int) -> List[MemoryEntry]:
                return [MemoryEntry(content="dummy memory", type="interaction", salience=0.5, timestamp="dummy_ts")]

        # Mock config access if ReflectionEngine needs it (e.g., for LLM roles)
        def get_llm_config(self, role: str) -> Optional[Dict[str, Any]]:
            return {"url": "dummy_url", "model": "dummy_model"} if role == "LOGOS_TECHNE" else None

        # Mock PATHOS_USER_ID if needed directly by ReflectionEngine
        PATHOS_USER_ID = "pathos_dummy_user"

    # Dummy LLMConfig if needed by dummy EthosCore or ReflectionEngine directly
    # LLMConfig = Dict[str, Any] # type: ignore

import json
import re # For parsing LLM JSON
from datetime import datetime, timedelta, timezone
import asyncio

logger = logging.getLogger(__name__)

class ReflectionEngine:
    def __init__(self, ethos_core: EthosCore):
        """
        Initializes the ReflectionEngine.

        Args:
            ethos_core: An instance of EthosCore to access memories, config, and other services.
        """
        self.ethos_core = ethos_core
        # TODO: Initialize any specific LLM clients or configurations if not using ethos_core's generic methods
        logger.info("ReflectionEngine initialized.")

    async def _get_memories_for_reflection(self, lookback_days: int, query_limit: int) -> List[MemoryEntry]:
        """
        Fetches a broad range of memories within a given lookback period for reflection.
        """
        if not self.ethos_core.memory_storage:
            logger.error("ReflectionEngine: EthosCore.memory_storage not available. Cannot fetch memories.")
            return []

        now_utc = datetime.now(timezone.utc)
        start_time_dt = now_utc - timedelta(days=lookback_days)

        # Define memory types relevant for reflection (can be made configurable)
        relevant_memory_types = [
            'chat_interaction', 'interaction', # chat_interaction is more specific if available
            'firmament_activity_log',
            'feedback',
            'received_subconscious_intention',
            'npc_dialogue_event',
            'learned_correction',
            'reflection_insight', # Include past insights
            'aspiration',
            'world_knowledge',
            'thought' # General thoughts
        ]
        # Remove duplicates just in case
        relevant_memory_types = sorted(list(set(relevant_memory_types)))


        logger.debug(f"ReflectionEngine: Fetching memories for reflection. Lookback: {lookback_days} days (from {start_time_dt.isoformat()}), Limit: {query_limit}, Types: {relevant_memory_types}")

        try:
            fetched_memories = await asyncio.to_thread(
                self.ethos_core.memory_storage.get_memories_for_summary,
                user_id=self.ethos_core.PATHOS_USER_ID,
                start_time_utc=start_time_dt,
                end_time_utc=now_utc,
                types=relevant_memory_types,
                limit=query_limit
            )
            logger.info(f"ReflectionEngine: Fetched {len(fetched_memories)} memories for reflection period.")
            return fetched_memories
        except Exception as e:
            logger.error(f"ReflectionEngine: Error fetching memories for reflection: {e}", exc_info=True)
            return []

    def _filter_and_select_memories(
        self,
        memories: List[MemoryEntry],
        max_memories_for_llm: int,
        min_salience: float,
        significant_event_threshold: float
    ) -> List[MemoryEntry]:
        logger.debug(f"ReflectionEngine: Filtering {len(memories)} memories. Max for LLM: {max_memories_for_llm}, Min Salience: {min_salience}")

        considered_memories = [
            mem for mem in memories
            if mem.get('salience', 0.0) >= min_salience
        ]

        if not considered_memories:
            logger.info("ReflectionEngine: No memories met minimum salience for selection.")
            return []

        def get_priority_score(memory: MemoryEntry) -> float:
            score = memory.get('salience', 0.0)
            # Example: Boost feedback, significant events
            if memory.get('type') == 'feedback':
                score += 0.5
            if memory.get('salience', 0.0) >= significant_event_threshold:
                score += 0.3
            # Future: Consider recency as a tie-breaker or factor
            # For example, add a small fraction based on how recent the memory is.
            # ts = memory.get('timestamp')
            # if ts:
            #     try:
            #         mem_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            #         recency_bonus = max(0, (mem_dt - (datetime.now(timezone.utc) - timedelta(days=7))).total_seconds() / (7 * 24 * 3600)) # Normalize over last 7 days
            #         score += recency_bonus * 0.1 # Small bonus for recency
            #     except ValueError:
            #         pass # Ignore if timestamp is invalid
            return score

        considered_memories.sort(key=get_priority_score, reverse=True)
        selected = considered_memories[:max_memories_for_llm]
        logger.info(f"ReflectionEngine: Selected {len(selected)} memories for LLM prompt after filtering and prioritization.")
        return selected

    def _format_memories_for_prompt(self, memories: List[MemoryEntry]) -> str:
        if not memories:
            return "No specific memories selected for reflection."

        formatted_memory_strings = []
        for mem in memories:
            ts_str = mem.get('timestamp', "Unknown time")
            try:
                ts_dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")) # Ensure ts_str is string
                # Format for better readability in prompt if needed, e.g. relative time or just date/time
                formatted_ts = ts_dt.strftime("%Y-%m-%d %H:%M UTC")
            except ValueError:
                formatted_ts = str(ts_str) # Fallback to original string if parsing fails

            content_snippet = (str(mem.get('content', '')) or "")[:150] # Truncate for prompt, ensure string
            content_snippet += "..." if len(str(mem.get('content', '')) or "") > 150 else ""

            # Optional: Include mood if available and relevant for reflection context
            mood_info_str = ""
            # metadata = mem.get('metadata', {}) # This is already a dict or None
            # if metadata and (mood_at_gen := metadata.get('mood_at_generation')): # Example key
            #    if isinstance(mood_at_gen, dict) and 'name' in mood_at_gen:
            #        mood_info_str = f" (Mood當時: {mood_at_gen['name']})"
            #    elif isinstance(mood_at_gen, str):
            #        mood_info_str = f" (Mood當時: {mood_at_gen})"


            formatted_memory_strings.append(
                f"- Timestamp: {formatted_ts}, Type: {mem.get('type')}, Salience: {mem.get('salience', 0.0):.2f}{mood_info_str}\n  Content: {content_snippet}"
            )
        return "\n".join(formatted_memory_strings)


    async def _call_llm_for_insights(self, system_prompt_text: str, user_prompt_text: str, llm_role: str) -> Optional[List[str]]:
        """
        Calls an LLM to generate insights based on the provided system and user prompts.
        Parses the expected JSON response to extract a list of insight strings.
        """
        logger.debug(f"ReflectionEngine: Calling LLM for insights. Role: {llm_role}.")

        if not hasattr(self.ethos_core, '_call_llm_for_internal_task'):
            logger.error("ReflectionEngine: EthosCore does not have '_call_llm_for_internal_task' method. Cannot call LLM.")
            # Fallback for testing if _call_llm_for_internal_task is missing on a mock
            if hasattr(self.ethos_core, 'config') and self.ethos_core.config is None: # Simple check if it's a basic mock
                 return ["Dummy insight from LLM (EthosCore._call_llm_for_internal_task missing on mock)."]
            return None

        messages = [
            {"role": "system", "content": system_prompt_text},
            {"role": "user", "content": user_prompt_text}
        ]

        try:
            response_str = await self.ethos_core._call_llm_for_internal_task(messages, llm_role)

            if not response_str or not response_str.strip():
                logger.warning("ReflectionEngine: LLM call returned no content for insights.")
                return None

            # Attempt to find JSON block within potentially messy LLM output
            # Regex to find content between the first '{' and the last '}'
            json_match = re.search(r'\{[\s\S]*\}', response_str)
            if not json_match:
                logger.error(f"ReflectionEngine: No JSON object found in LLM response for insights. Raw response: {response_str[:500]}")
                # Attempt to extract insights if it's a simple list in a common non-JSON format (e.g. numbered list)
                # This is a basic fallback, more sophisticated parsing can be added if LLMs are consistently failing JSON.
                potential_insights = []
                for line in response_str.splitlines():
                    line = line.strip()
                    # Check for lines starting with common list markers like -, *, or number.
                    if re.match(r'^(\*|-|\d+\.?)\s+', line):
                        insight_text = re.sub(r'^(\*|-|\d+\.?)\s+', '', line).strip()
                        if insight_text:
                            potential_insights.append(insight_text)
                if potential_insights:
                    logger.warning(f"ReflectionEngine: Parsed {len(potential_insights)} potential insights from non-JSON response.")
                    return potential_insights
                return None


            cleaned_json_str = json_match.group(0)

            try:
                parsed_response = json.loads(cleaned_json_str)
                if isinstance(parsed_response, dict) and "insights" in parsed_response and isinstance(parsed_response["insights"], list):
                    insights = [str(i) for i in parsed_response["insights"] if isinstance(i, str) and i.strip()]
                    if not insights and parsed_response["insights"]: # List exists but all items were non-string or empty
                         logger.warning(f"ReflectionEngine: LLM insights list was present but contained no valid strings. Original list: {parsed_response['insights']}")
                         return None
                    logger.info(f"ReflectionEngine: Successfully parsed {len(insights)} insights from LLM JSON.")
                    return insights
                else:
                    logger.error(f"ReflectionEngine: LLM response JSON does not match expected structure ('insights' list). Parsed JSON: {parsed_response}")
                    return None
            except json.JSONDecodeError as e_json:
                logger.error(f"ReflectionEngine: Failed to parse LLM JSON response for insights: {e_json}. Cleaned JSON string was: {cleaned_json_str[:500]}")
                return None

        except Exception as e:
            logger.error(f"ReflectionEngine: Error calling LLM or processing insights: {e}", exc_info=True)
            return None


    async def _store_insights(self, insights: List[str], source_memory_ids: List[str], hexus_at_reflection: Dict[str, float]) -> List[str]:
        """
        Stores the generated insights as new memory entries in EthosCore.

        Args:
            insights: A list of insight strings generated by the LLM.
            source_memory_ids: A list of IDs of the memories that were used to generate these insights.
            hexus_at_reflection: A snapshot of Hexus scores at the time of reflection.

        Returns:
            A list of IDs of the newly created insight memory entries.
        """
        if not self.ethos_core:
            logger.error("ReflectionEngine: EthosCore not available. Cannot store insights.")
            return []

        if not insights:
            logger.info("ReflectionEngine: No insights provided to store.")
            return []

        stored_insight_ids: List[str] = []
        reflection_cycle_timestamp = datetime.now(timezone.utc).isoformat()

        for insight_text in insights:
            if not insight_text.strip():
                logger.warning("ReflectionEngine: Skipping empty insight string.")
                continue

            pathos_user_id_for_insight = "pathos_agent_internal" # Default/fallback
            if hasattr(self.ethos_core, 'PATHOS_USER_ID'):
                pathos_user_id_for_insight = self.ethos_core.PATHOS_USER_ID
            else:
                try:
                    from .....persona_logic.chronos_engine import PATHOS_USER_ID as REFLECTION_PATHOS_ID
                    pathos_user_id_for_insight = REFLECTION_PATHOS_ID
                except ImportError:
                    logger.warning("ReflectionEngine: Could not determine PATHOS_USER_ID for insight metadata. Defaulting.")


            insight_memory_data = {
                "type": "reflection_insight",
                "content": insight_text.strip(),
                "metadata": {
                    "source_reflection_cycle_timestamp": reflection_cycle_timestamp,
                    "source_memory_ids": source_memory_ids,
                    "hexus_at_reflection": hexus_at_reflection,
                    "user_id": pathos_user_id_for_insight
                },
                "salience": 0.85,
            }

            try:
                stored_entry = await self.ethos_core.add_memory_entry(
                    entry_data=insight_memory_data,
                    user_id_context=pathos_user_id_for_insight
                )
                if stored_entry and stored_entry.get('id'):
                    stored_insight_ids.append(stored_entry['id'])
                    logger.info(f"ReflectionEngine: Stored insight (ID: {stored_entry['id']}): '{insight_text[:100]}...'")
                else:
                    logger.error(f"ReflectionEngine: Failed to store insight or get ID back: '{insight_text[:100]}...'. Response from add_memory_entry: {stored_entry}")
            except Exception as e_store:
                logger.error(f"ReflectionEngine: Error storing insight '{insight_text[:100]}...': {e_store}", exc_info=True)

        return stored_insight_ids

    async def perform_reflection(self) -> List[str]:
        """
        Orchestrates the reflection process: fetches memories, selects salient ones,
        prompts an LLM for insights, and stores these insights.
        Returns a list of generated insight strings.
        """
        logger.info("ReflectionEngine: Starting reflection process...")

        # Configuration (these would ideally come from self.ethos_core.ethos_config)
        # Using placeholder values for now.
        lookback_days = 3
        query_limit = 50
        max_memories_for_llm = 15 # Max memories to pass to LLM after filtering
        min_salience = 0.3 # Min salience for a memory to be considered for reflection
        significant_event_threshold = 0.7 # Salience threshold to boost priority
        # reflection_llm_role = "LOGOS_TECHNE" # Default, will be fetched from config

        # 1. Fetch Memories
        raw_memories = await self._get_memories_for_reflection(lookback_days, query_limit)
        if not raw_memories:
            logger.info("ReflectionEngine: No memories found for reflection period.")
            return []

        # 2. Filter and Select
        selected_memories = self._filter_and_select_memories( # Made synchronous
            raw_memories, max_memories_for_llm, min_salience, significant_event_threshold
        )
        if not selected_memories:
            logger.info("ReflectionEngine: No memories selected for LLM after filtering.")
            return []

        source_ids = [str(mem.get("id","unknown")) for mem in selected_memories] # Ensure IDs are strings

        # 3. Format for Prompt
        formatted_memories_for_llm = self._format_memories_for_prompt(selected_memories)

        system_prompt_text = (
            "You are a reflective journaling assistant for an AI named Pathos. "
            "Review the following list of recent experiences, thoughts, and feedback. "
            "Identify 2-3 key insights, self-observations, or lessons learned from these memories. "
            "Focus on patterns, significant events, or areas for growth or understanding. "
            "Insights should be concise and actionable or thought-provoking for Pathos. "
            "Your output MUST be a JSON object containing a single key \"insights\" which is a list of strings. "
            "Example: {\"insights\": [\"Insight text 1.\", \"Insight text 2.\"]}"
        )
        user_prompt_text_content_for_llm = (
            "Here is a selection of Pathos's recent memories for reflection:\n\n"
            f"{formatted_memories_for_llm}\n\n"
            "Please generate 2-3 concise insights based on these memories, in the specified JSON format."
        )

        # 4. Call LLM
        # Get LLM role from config (ensure ethos_core and config are accessible)
        reflection_llm_role = "LOGOS_TECHNE" # Default
        # Check if ethos_core and its config attribute exist, then ETHOS sub-dict, then the key
        if self.ethos_core and hasattr(self.ethos_core, 'config') and self.ethos_core.config and \
           hasattr(self.ethos_core.config, 'ETHOS') and isinstance(self.ethos_core.config.ETHOS, dict):
            reflection_llm_role = self.ethos_core.config.ETHOS.get('reflection_llm_role', "LOGOS_TECHNE")
        # Fallback to checking ethos_config if it's a direct attribute and a dict
        elif self.ethos_core and hasattr(self.ethos_core, 'ethos_config') and isinstance(self.ethos_core.ethos_config, dict):
             reflection_llm_role = self.ethos_core.ethos_config.get('reflection_llm_role', "LOGOS_TECHNE")


        generated_insights = await self._call_llm_for_insights(
            system_prompt_text=system_prompt_text,
            user_prompt_text=user_prompt_text_content_for_llm,
            llm_role=reflection_llm_role
        )
        if not generated_insights:
            logger.warning("ReflectionEngine: LLM call did not yield any insights.")
            return []

        logger.info(f"ReflectionEngine: LLM generated {len(generated_insights)} insights.")

        # 5. Store Insights
        # Get current Hexus for metadata (placeholder - real EthosCore would provide this)
        current_hexus_snapshot = self.ethos_core.get_hexus_scores() if hasattr(self.ethos_core, 'get_hexus_scores') else {}

        await self._store_insights(generated_insights, source_ids, current_hexus_snapshot)

        logger.info("ReflectionEngine: Reflection process completed.")
        return generated_insights

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logger_main = logging.getLogger(__name__ + ".__main__")
    logger_main.info("--- Testing ReflectionEngine ---")

    # Setup mock EthosCore for testing
    class TestMockEthosCore(EthosCore): # Inherit from dummy if not fully mocked
        PATHOS_USER_ID = "test_pathos_user_reflection"

        def __init__(self):
            super().__init__(config=None) # type: ignore
            self.test_memories_store: List[MemoryEntry] = [] # For _store_insights to "save" to
            self.memory_storage = self # Mock memory_storage to be self for get_memories_for_summary

            # Mock ethos_config as a dictionary for direct attribute access
            self.ethos_config: Dict[str, Any] = {
                'reflection_llm_role': "LOGOS_TECHNE_TEST_MOCK",
                # Add other EthosConfig keys if ReflectionEngine starts using them
            }
            # Also mock the .config.ETHOS structure if that's preferred by some parts of code
            self.config = type('Config', (), {})() # type: ignore
            self.config.ETHOS = self.ethos_config # type: ignore


        async def get_memories_for_summary(self, user_id: str, start_time_utc: Any, end_time_utc: Any, types: List[str], limit: int) -> List[MemoryEntry]:
            logger_main.info(f"TestMockEthosCore.get_memories_for_summary called for {user_id}, limit {limit}")
            # Ensure returned items are MemoryEntry (or dicts that can be cast)
            # Using actual MemoryEntry for better type consistency in tests.
            sample_mem_data = [
                {"id":"mem1", "content":"Test memory 1 about learning.", "type":"learning", "salience":0.8, "timestamp":"2023-01-01T10:00:00Z"},
                {"id":"mem2", "content":"Another test memory about a challenge.", "type":"interaction", "salience":0.6, "timestamp":"2023-01-01T12:00:00Z"},
                {"id":"mem3", "content":"A less important memory.", "type":"thought", "salience":0.2, "timestamp":"2023-01-01T14:00:00Z"},
                {"id":"mem4", "content":"Memory with high salience but no specific type for boosting.", "type":"generic", "salience":0.9, "timestamp":"2023-01-01T15:00:00Z"},
                {"id":"mem5", "content":"Feedback memory to test boosting.", "type":"feedback", "salience":0.5, "timestamp":"2023-01-01T16:00:00Z"},
            ]
            return [MemoryEntry(**data) for data in sample_mem_data * (limit // len(sample_mem_data) + 1)][:limit]

        async def _call_llm_for_internal_task(self, messages: List[Dict[str, Any]], llm_role_to_use: str) -> Optional[str]:
            logger_main.info(f"TestMockEthosCore._call_llm_for_internal_task for role {llm_role_to_use} with prompt: {messages[-1]['content'][:100]}...")
            # Check that system and user prompt parts are present
            assert any(msg["role"] == "system" for msg in messages), "System prompt missing in LLM call"
            assert any(msg["role"] == "user" for msg in messages), "User prompt missing in LLM call"
            return json.dumps({"insights": ["Mock insight: Always learn from experiences.", "Mock insight: Challenges are opportunities."]})

        async def add_memory_entry(self, entry_data: Dict, user_id_context: Optional[str] = None) -> MemoryEntry: # Mock needs to be async
            logger_main.info(f"TestMockEthosCore.add_memory_entry called for type '{entry_data.get('type')}' by user '{user_id_context}': {str(entry_data.get('content'))[:50]}...")
            # Simulate adding to a list for verification and return a MemoryEntry like dict with an ID
            new_id = f"insight_id_{len(self.test_memories_store)}_{datetime.now().microsecond}"
            # Ensure the mock returns something that behaves like MemoryEntry for .get('id')
            new_entry_dict = entry_data.copy()
            new_entry_dict["id"] = new_id
            new_memory_entry = MemoryEntry(**new_entry_dict)
            self.test_memories_store.append(new_memory_entry)
            return new_memory_entry

        def get_hexus_scores(self) -> Dict[str, float]:
            return {"joy": 0.5, "stress": 0.2} # Sample Hexus for metadata


    async def run_reflection_test():
        mock_ethos_instance = TestMockEthosCore()
        reflection_engine_test = ReflectionEngine(ethos_core=mock_ethos_instance) # type: ignore

        # Test _get_memories_for_reflection
        logger_main.info("Testing _get_memories_for_reflection...")
        memories = await reflection_engine_test._get_memories_for_reflection(lookback_days=3, query_limit=10)
        assert len(memories) <= 10
        logger_main.info(f"Fetched {len(memories)} for reflection.")

        # Test _filter_and_select_memories
        logger_main.info("Testing _filter_and_select_memories...")
        if memories: # Only test if previous step returned memories
            selected = reflection_engine_test._filter_and_select_memories(memories, max_memories_for_llm=5, min_salience=0.5, significant_event_threshold=0.75)
            logger_main.info(f"Selected {len(selected)} memories after filtering. First one: {selected[0] if selected else 'None'}")
            assert len(selected) <= 5
            for mem in selected:
                assert mem.get('salience', 0.0) >= 0.5
            # Check if feedback memory was prioritized (if present and selected)
            feedback_mem_present_and_selected = any(mem.get('type') == 'feedback' for mem in selected)
            original_feedback_mem = any(mem.get('type') == 'feedback' and mem.get('salience',0.0) >=0.5 for mem in memories)
            if original_feedback_mem:
                 assert feedback_mem_present_and_selected, "Feedback memory with sufficient salience should be selected due to boost"


        # Test _format_memories_for_prompt
        logger_main.info("Testing _format_memories_for_prompt...")
        # Use a small, controlled list for formatting test
        test_format_memories = [
            MemoryEntry(id="fmt_mem1", content="Memory for formatting.", type="format_test", salience=0.9, timestamp="2023-01-02T10:00:00Z"),
            MemoryEntry(id="fmt_mem2", content="Another memory, very long content that should be truncated properly to see the effect of the truncation logic we implemented earlier in the day.", type="format_test_long", salience=0.8, timestamp="2023-01-02T11:00:00Z")
        ]
        prompt_str = reflection_engine_test._format_memories_for_prompt(test_format_memories)
        logger_main.info(f"Formatted prompt string:\n{prompt_str}")
        assert "Memory for formatting." in prompt_str
        assert "Another memory, very long content that should be truncated properly to see the effect of the truncation logic we implemented earlier in the day."[:150] + "..." in prompt_str
        assert "2023-01-02 10:00 UTC" in prompt_str

        logger_main.info("Starting ReflectionEngine.perform_reflection()...")
        insights = await reflection_engine_test.perform_reflection()

        logger_main.info(f"Reflection generated {len(insights)} insights:")
        for i, insight_text in enumerate(insights):
            logger_main.info(f"  Insight {i+1}: {insight_text}")

        assert len(insights) > 0, "Expected perform_reflection to generate insights."
        assert len(mock_ethos_instance.test_memories_store) == len(insights), "Number of stored insights should match generated insights."
        if mock_ethos_instance.test_memories_store:
            assert mock_ethos_instance.test_memories_store[0].get("type") == "reflection_insight"

        logger_main.info("ReflectionEngine perform_reflection test finished.")

    asyncio.run(run_reflection_test())
