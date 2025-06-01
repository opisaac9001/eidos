import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
import re
import math
import json
from pathlib import Path
import uuid
import sqlite3
import random
import httpx # Not directly used here, but often in LLM calls if not delegated
from eidos_agent.utils.prompt_loader import load_system_prompt

from eidos_agent.core.config import Config, EthosConfig, PROJECT_ROOT, LLMConfig
from eidos_agent.modules.ethos_core.memory_storage import MemoryStorage, MemoryEntry
from eidos_agent.utils.logger import get_logger

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from eidos_agent.modules.oneiros_module import OneirosModule
    from eidos_agent.core.connection_manager import ConnectionManager
    from eidos_agent.modules.pathos_interface import PathosInterface
    from eidos_agent.modules.logos_core.handler import LogosCore
    from eidos_agent.modules.chronos_engine import ChronosEngine, ActivitySlot # ActivitySlot for type hint

from eidos_agent.modules.chronos_engine import PATHOS_USER_ID # For Chronos bridge

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

logger = get_logger(__name__)

PERSONA_FILE_PATH = PROJECT_ROOT / "persona" / "pathos_directives.txt"
HEXUS_STATE_FILENAME = "hexus_state.json"
TASK_LAST_RUN_TIMES_FILENAME = "task_last_run_times.json" # From broken

MOOD_VALENCE_BASELINE = 0.0; MOOD_AROUSAL_BASELINE = 0.0
MOOD_MIN = -1.0; MOOD_MAX = 1.0
MOOD_SHIFT_VALENCE_SUCCESS = 0.15; MOOD_SHIFT_AROUSAL_SUCCESS = 0.05
MOOD_SHIFT_VALENCE_FAILURE = -0.2; MOOD_SHIFT_AROUSAL_FAILURE = 0.1
MOOD_SHIFT_VALENCE_FEEDBACK_POSITIVE = 0.1; MOOD_SHIFT_AROUSAL_FEEDBACK_POSITIVE = 0.05
MOOD_SHIFT_VALENCE_FEEDBACK_NEGATIVE = -0.15; MOOD_SHIFT_AROUSAL_FEEDBACK_NEGATIVE = 0.05
HEXUS_MIN = -1.0; HEXUS_MAX = 1.0
DEFAULT_HEXUS_SCORES = {"general_caution": 0.0, "user_engagement_proactivity": 0.0, "brevity_preference": 0.0}

class EthosCore:
    def __init__(self, config: Config):
        self.config = config
        self.ethos_config: EthosConfig = config.get_ethos_config()
        self.memory_storage = MemoryStorage(config)
        self.hexus_state_file_path = self.memory_storage.memory_db_path.parent / HEXUS_STATE_FILENAME
        self.task_last_run_times_file_path = self.memory_storage.memory_db_path.parent / TASK_LAST_RUN_TIMES_FILENAME # From broken
        self._task_last_run_times_cache: Dict[str, datetime] = self._load_task_last_run_times() # From broken

        self.current_mood: Dict[str, float] = {"valence": MOOD_VALENCE_BASELINE, "arousal": MOOD_AROUSAL_BASELINE}
        self.last_mood_update_time: datetime = datetime.now(timezone.utc)
        self.persona_directives: List[str] = self._load_persona_from_file()
        self.hexus_scores: Dict[str, float] = self._load_hexus_scores()

        now_utc_init = datetime.now(timezone.utc)
        reflection_interval = self.ethos_config.get('reflection_interval_seconds', 86400.0)
        self.last_reflection_time = self._get_initial_last_run_time("EthosReflection", float(reflection_interval), now_utc_init)
        forgetting_interval = self.ethos_config.get('forgetting_interval_seconds', float(reflection_interval) * 0.5 if reflection_interval > 0 else 0.0)
        self.last_forgetting_time = self._get_initial_last_run_time("EthosForgetting", float(forgetting_interval), now_utc_init)
        hexus_decay_interval = self.ethos_config.get('hexus_decay_interval_seconds', 3600.0)
        self.last_hexus_decay_time = self._get_initial_last_run_time("HexusDecay", float(hexus_decay_interval), now_utc_init)
        knowledge_upkeep_interval = self.ethos_config.get('knowledge_upkeep_interval_seconds', 86400.0)
        self.last_knowledge_upkeep_time = self._get_initial_last_run_time("KnowledgeUpkeep", float(knowledge_upkeep_interval), now_utc_init)
        interaction_log_analysis_interval = self.ethos_config.get('interaction_log_analysis_interval_seconds', 86400.0)
        self.last_interaction_log_analysis_time = self._get_initial_last_run_time("InteractionLogAnalysis", float(interaction_log_analysis_interval), now_utc_init)
        long_term_planning_interval = self.ethos_config.get('long_term_planning_interval_seconds', 86400.0 * 3)
        self.last_long_term_planning_time = self._get_initial_last_run_time("PathosLongTermPlanning", float(long_term_planning_interval), now_utc_init)

        self.oneiros_module: Optional['OneirosModule'] = None
        self.connection_manager: Optional['ConnectionManager'] = None
        self.pathos_interface: Optional['PathosInterface'] = None
        self.logos_core: Optional['LogosCore'] = None
        self.chronos_engine: Optional['ChronosEngine'] = None

        self.system_user_ids: List[Optional[str]] = [
            "unknown_user", "api_guest_user", "system_oneiros", "system_document", "system_briefing",
            "system_reflection", "world_knowledge_store", "system_knowledge_upkeep", "system_curiosity",
            "system_admin", PATHOS_USER_ID, None
        ]
        self.hexus_scores_changed_during_reflection = False
        logger.info("EthosCore initialized with persistent task timing.")

    def _load_task_last_run_times(self) -> Dict[str, datetime]: # From broken
        loaded_times: Dict[str, datetime] = {}
        if self.task_last_run_times_file_path.is_file():
            try:
                with open(self.task_last_run_times_file_path, 'r', encoding='utf-8') as f: data = json.load(f)
                for task_name, ts_str in data.items():
                    try: loaded_times[task_name] = datetime.fromisoformat(ts_str)
                    except ValueError: logger.warning(f"Invalid timestamp for task '{task_name}': {ts_str}")
                logger.info(f"Loaded task last run times from {self.task_last_run_times_file_path}")
            except (json.JSONDecodeError, IOError) as e: logger.error(f"Error loading task times: {e}", exc_info=True)
        else: logger.info(f"Task last run times file not found. Tasks will run based on defaults.")
        return loaded_times

    def _save_task_last_run_time(self, task_name: str, timestamp: datetime): # From broken
        self._task_last_run_times_cache[task_name] = timestamp
        try:
            self.task_last_run_times_file_path.parent.mkdir(parents=True, exist_ok=True)
            data_to_save = {name: dt.isoformat() for name, dt in self._task_last_run_times_cache.items()}
            with open(self.task_last_run_times_file_path, 'w', encoding='utf-8') as f: json.dump(data_to_save, f, indent=4)
            logger.debug(f"Saved last run time for '{task_name}' ({timestamp.isoformat()})")
        except (IOError, TypeError) as e: logger.error(f"Failed to save task times: {e}", exc_info=True)

    def _get_initial_last_run_time(self, task_name: str, interval_seconds: float, current_time_utc: datetime) -> datetime: # From broken
        if task_name in self._task_last_run_times_cache:
            logger.debug(f"Using persisted last run time for '{task_name}': {self._task_last_run_times_cache[task_name].isoformat()}")
            return self._task_last_run_times_cache[task_name]
        else:
            splay_offset = random.uniform(0, interval_seconds * 0.1) if interval_seconds > 0 else 0
            default_last_run = current_time_utc - timedelta(seconds=max(interval_seconds + 60 - splay_offset, 60.0))
            logger.debug(f"No persisted last run time for '{task_name}'. Setting initial to: {default_last_run.isoformat()}")
            return default_last_run

    def set_connection_manager(self, manager: 'ConnectionManager'): self.connection_manager = manager
    def set_pathos_interface(self, pathos_interface: 'PathosInterface'): self.pathos_interface = pathos_interface
    def set_logos_core(self, logos_core_instance: 'LogosCore'): self.logos_core = logos_core_instance
    def set_chronos_engine(self, chronos_engine_instance: 'ChronosEngine'): self.chronos_engine = chronos_engine_instance # New

    async def close(self): # From broken (uses self.memory_storage.close_connection())
        logger.info("EthosCore close called. Saving Hexus scores and closing memory connection.")
        self._save_hexus_scores()
        self.memory_storage.close_connection()
        logger.info("EthosCore resources released.")

    def _load_persona_from_file(self) -> List[str]: # From broken (more robust)
        logger.info(f"Loading persona directives from: {PERSONA_FILE_PATH}")
        default_content = load_system_prompt("pathos_directives", "Default persona: You are Pathos.") # Fallback to a simpler default if pathos_directives itself fails
        try:
            if not PERSONA_FILE_PATH.is_file():
                logger.warning(f"Persona file not found at {PERSONA_FILE_PATH}. Creating with default content.")
                PERSONA_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(PERSONA_FILE_PATH, 'w', encoding='utf-8') as f: f.write(default_content)
                return [line for line in default_content.splitlines()]
            persona_text = PERSONA_FILE_PATH.read_text(encoding='utf-8')
            if not persona_text.strip():
                logger.warning(f"Persona file {PERSONA_FILE_PATH} is empty. Using default content.")
                return [line for line in default_content.splitlines()]
            directives = [line.strip() for line in persona_text.splitlines() if line.strip() and not line.strip().startswith('#')]
            logger.info(f"Successfully loaded {len(directives)} persona directives.")
            return directives
        except Exception as e:
            logger.error(f"Error loading persona file {PERSONA_FILE_PATH}: {e}", exc_info=True)
            logger.warning("Using default persona content due to error.")
            return [line for line in default_content.splitlines()]

    def _load_hexus_scores(self) -> Dict[str, float]: # From broken (more robust)
        defaults = DEFAULT_HEXUS_SCORES.copy()
        if self.hexus_state_file_path.is_file():
            try:
                with open(self.hexus_state_file_path, 'r', encoding='utf-8') as f: loaded_scores = json.load(f)
                if isinstance(loaded_scores, dict) and all(key in defaults for key in loaded_scores) and all(isinstance(value, (int, float)) for value in loaded_scores.values()):
                    for key, value in loaded_scores.items():
                        if key in defaults: defaults[key] = float(value)
                    logger.info(f"Successfully loaded Hexus scores from {self.hexus_state_file_path}")
                    return defaults
                else:
                    logger.warning(f"Hexus state file {self.hexus_state_file_path} has invalid format. Using defaults/valid values.")
                    final_scores = defaults.copy()
                    if isinstance(loaded_scores, dict):
                        for key in final_scores:
                            if key in loaded_scores and isinstance(loaded_scores[key], (int, float)): final_scores[key] = float(loaded_scores[key])
                    return final_scores
            except (json.JSONDecodeError, IOError) as e: logger.error(f"Error loading Hexus state: {e}. Using defaults.", exc_info=True)
        else: logger.info(f"Hexus state file not found. Using default scores and creating file.")
        try: self._save_hexus_scores(defaults)
        except Exception as e_save: logger.error(f"Failed to save initial Hexus scores: {e_save}", exc_info=True)
        return defaults

    def _save_hexus_scores(self, scores_to_save: Optional[Dict[str, float]] = None): # From broken
        scores = scores_to_save if scores_to_save is not None else self.hexus_scores
        try:
            self.hexus_state_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.hexus_state_file_path, 'w', encoding='utf-8') as f:
                json.dump({k: float(v) for k, v in scores.items()}, f, indent=4)
            logger.info(f"Hexus scores saved to {self.hexus_state_file_path}")
        except (IOError, TypeError) as e: logger.error(f"Failed to save Hexus scores: {e}", exc_info=True)

    async def get_user_fact_by_key(self, user_id: str, attribute_key: str) -> Optional[MemoryEntry]: # From broken (more robust)
        if not user_id or not attribute_key: return None
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        sql = "SELECT * FROM memories WHERE type = 'user_fact' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.fact_attribute_key') = ? ORDER BY timestamp DESC LIMIT 1"
        try:
            cursor.execute(sql, (user_id, attribute_key)); row = cursor.fetchone()
            return self.memory_storage._row_to_entry(row) if row else None
        except sqlite3.OperationalError as oe:
            if "no such function: json_extract" in str(oe).lower():
                logger.warning("json_extract not available for get_user_fact_by_key. Falling back."); cursor.execute("SELECT * FROM memories WHERE type = 'user_fact' ORDER BY timestamp DESC")
                for r_row in cursor.fetchall():
                    try:
                        entry = self.memory_storage._row_to_entry(r_row); meta = entry.get('metadata', {})
                        if meta.get('user_id') == user_id and meta.get('fact_attribute_key') == attribute_key: return entry
                    except (json.JSONDecodeError, TypeError): continue
            else: logger.error(f"SQLite Error in get_user_fact_by_key: {oe}", exc_info=True); raise
        except Exception as e: logger.error(f"Error in get_user_fact_by_key: {e}", exc_info=True)
        return None

    async def add_memory_entry(self, entry_data: Dict, user_id_context: Optional[str] = None) -> MemoryEntry: # From broken (more robust user_id handling)
        if 'content' not in entry_data or 'type' not in entry_data: raise ValueError("Memory entry must contain 'content' and 'type'")
        entry_type = str(entry_data['type']); metadata = entry_data.get('metadata', {}).copy()
        if user_id_context is not None:
            current_meta_user_id = metadata.get('user_id')
            if user_id_context not in self.system_user_ids:
                if current_meta_user_id in self.system_user_ids or current_meta_user_id is None or current_meta_user_id != user_id_context:
                    metadata['user_id'] = user_id_context
            elif current_meta_user_id is None: metadata['user_id'] = user_id_context
        entry_data['metadata'] = metadata
        if entry_type == 'user_fact' and metadata.get('user_id') and metadata.get('user_id') not in self.system_user_ids and metadata.get('fact_attribute_key'):
            target_user_id = metadata['user_id']; attribute_key = metadata['fact_attribute_key']; new_content_str = str(entry_data['content']); new_value_parsed = None
            try: new_content_data = json.loads(new_content_str); new_value_parsed = new_content_data.get('value')
            except json.JSONDecodeError: logger.warning(f"Could not parse new user_fact content: {new_content_str}")
            existing_fact_entry = await self.get_user_fact_by_key(target_user_id, attribute_key)
            if existing_fact_entry:
                try:
                    existing_content_data = json.loads(existing_fact_entry['content']); existing_value = existing_content_data.get('value')
                    if new_value_parsed is not None and new_value_parsed != existing_value:
                        updated_data = {'content': new_content_str, 'timestamp': entry_data.get('timestamp', datetime.now(timezone.utc).isoformat()), 'metadata': metadata, 'salience': entry_data.get('salience', 1.5)}
                        self.memory_storage.update_entry(existing_fact_entry['id'], updated_data)
                        updated_entry = existing_fact_entry.copy(); updated_entry.update(updated_data)
                        if self.memory_storage.embedder: updated_entry['embedding'] = self.memory_storage.embedder.encode(new_content_str[:self.ethos_config.get('embedding_max_text_length', 2560)]).tolist()
                        return updated_entry # type: ignore
                    else: return existing_fact_entry
                except json.JSONDecodeError: logger.warning(f"Could not parse existing user_fact content: {existing_fact_entry['content']}. Will insert new.")
        return self.memory_storage.add_entry(entry_data)

    async def get_local_datetime_for_user(self, user_id: str, location_override: Optional[str] = None) -> datetime: # From broken (more robust)
        if user_id == PATHOS_USER_ID:
            pathos_home_tz_str = self.ethos_config.get('pathos_home_timezone', "UTC")
            if ZoneInfo and pathos_home_tz_str and pathos_home_tz_str.lower() != 'utc':
                try: return datetime.now(ZoneInfo(pathos_home_tz_str))
                except Exception as e_tz: logger.warning(f"Could not resolve Pathos home timezone '{pathos_home_tz_str}': {e_tz}. Defaulting to UTC."); return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)
        if not user_id or user_id in self.system_user_ids: return datetime.now(timezone.utc)
        iana_timezone_str: Optional[str] = None
        if derived_tz_fact := await self.get_user_fact('derived_iana_timezone', user_id):
            if content := derived_tz_fact.get('content'):
                try: iana_timezone_str = json.loads(content).get('value')
                except json.JSONDecodeError: logger.warning(f"Failed to parse 'derived_iana_timezone' for user '{user_id}'.")
        if not iana_timezone_str:
            location_input_str = location_override
            if not location_input_str:
                if location_fact := await self.get_user_fact('preferred_location', user_id):
                    if content := location_fact.get('content'):
                        try: location_input_str = json.loads(content).get('value')
                        except json.JSONDecodeError: pass
            if location_input_str: iana_timezone_str = location_input_str
        if iana_timezone_str and ZoneInfo:
            try: return datetime.now(ZoneInfo(iana_timezone_str))
            except Exception as e: logger.warning(f"Could not resolve '{iana_timezone_str}' for user '{user_id}' (Error: {e}). Falling back to UTC.")
        elif not ZoneInfo: logger.warning("ZoneInfo module not available. Falling back to UTC.")
        return datetime.now(timezone.utc)
    
    async def retrieve_relevant_memories(self, query: str, top_k: int = 5, min_salience: float = 0.1, allowed_types: Optional[List[str]] = None, user_id_context: Optional[str] = None) -> List[MemoryEntry]: # From broken (more robust filtering)
        if not query.strip() and not allowed_types: return []
        try:
            # Ensure min_salience is a float to prevent TypeError when comparing with entry salience values
            min_salience = float(min_salience)
            similar_results = self.memory_storage.find_similar(query, top_k * 5, allowed_types, 0.3)
            all_candidates = [entry for _, entry in similar_results]
            if user_id_context and user_id_context not in ["default_user"] + self.system_user_ids:
                user_cands, other_cands = [], []
                for entry in all_candidates:
                    entry_uid = entry.get('metadata', {}).get('user_id')
                    if entry_uid == user_id_context or entry_uid in self.system_user_ids: user_cands.append(entry)
                    else: other_cands.append(entry)
                combined_candidates = user_cands + other_cands
            else: combined_candidates = all_candidates
            filtered_salience = [e for e in combined_candidates if (e.get('salience') or 0.0) >= min_salience]
            def sort_key(entry: MemoryEntry):
                entry_type = entry.get('type'); entry_uid = entry.get('metadata', {}).get('user_id')
                p_score = 0
                if entry_type == 'user_fact' and entry_uid == user_id_context: p_score = 8
                elif entry_type == 'aspiration' and entry_uid == PATHOS_USER_ID: p_score = 7 # From broken
                elif entry_type in ['learned_correction', 'learned_feedback_insight', 'suggestion_reflection']: p_score = 6
                elif entry_type == 'feedback': p_score = 5
                elif entry_type == 'context_summary' and (entry_uid == user_id_context or entry_uid in ["system_oneiros", "system_reflection", PATHOS_USER_ID]): p_score = 4
                elif entry_type == 'world_knowledge': p_score = 3
                elif entry_type == 'document_chunk': p_score = 2
                elif entry_uid == user_id_context and entry_type != 'user_fact': p_score = 1
                return (p_score, entry.get('salience') or 0.0, entry.get('timestamp', ''))
            return sorted(filtered_salience, key=sort_key, reverse=True)[:top_k]
        except Exception as e: logger.error(f"Error retrieving memories: {e}", exc_info=True); return []

    async def get_user_fact(self, attribute_key: str, user_id: str) -> Optional[MemoryEntry]: # From broken (more robust)
        normalized_key = attribute_key.lower().replace(" ", "_").strip()
        if not user_id or user_id in self.system_user_ids or not normalized_key: return None
        try:
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            sql = "SELECT * FROM memories WHERE type = 'user_fact' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.fact_attribute_key') = ? ORDER BY timestamp DESC LIMIT 1"
            try:
                cursor.execute(sql, (user_id, normalized_key)); row = cursor.fetchone()
                if row: return self.memory_storage._row_to_entry(row)
            except sqlite3.OperationalError as oe:
                if "no such function: json_extract" in str(oe).lower():
                    logger.warning("json_extract not available. Falling back for get_user_fact."); cursor.execute("SELECT * FROM memories WHERE type = 'user_fact' ORDER BY timestamp DESC")
                    for r_row in cursor.fetchall():
                        entry = self.memory_storage._row_to_entry(r_row); meta = entry.get('metadata', {})
                        if meta.get('user_id') == user_id and meta.get('fact_attribute_key') == normalized_key: return entry
                else: logger.error(f"SQLite Error in get_user_fact: {oe}", exc_info=True); return None
            return None
        except Exception as e: logger.error(f"Error in get_user_fact: {e}", exc_info=True); return None

    async def add_document_chunks(self, doc_id: str, filename: str, chunks: List[str]): # From broken
        if not chunks: return
        user_id_ctx = "system_document"
        for i, chunk_text in enumerate(chunks):
            if not chunk_text or not chunk_text.strip(): continue
            await self.add_memory_entry({"type": "document_chunk", "content": chunk_text, "id": f"{doc_id}_chunk_{i}", "metadata": {"source_document_id": doc_id, "source_document_name": filename, "chunk_index": i, "total_chunks": len(chunks), "user_id": user_id_ctx}, "salience": 0.4}, user_id_context=user_id_ctx)

    async def _call_llm_for_internal_task(self, messages: List[Dict[str, Any]], llm_role_to_use: str) -> Optional[str]: # From broken (more robust)
        llm_config = self.config.get_llm_config(llm_role_to_use)
        if not llm_config or not llm_config.get('url'): return f"[LLM URL for role '{llm_role_to_use}' not configured]"
        api_url = f"{llm_config['url']}/chat/completions"; response = None
        try:
            timeout_s = llm_config.get('timeout', 120.0)
            async with httpx.AsyncClient(timeout=float(timeout_s)) as client:
                headers = {"Content-Type": "application/json"}
                if api_key := llm_config.get('api_key'):
                    if api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']: headers["Authorization"] = f"Bearer {api_key}"
                default_max_tokens = 512 if messages and "summarize" in messages[0].get("content","").lower() else 256
                max_tokens_val = int(llm_config.get('max_tokens', default_max_tokens))
                payload: Dict[str, Any] = {"model": llm_config.get('model'), "messages": messages, "temperature": llm_config.get('temperature', 0.3), "max_tokens": max_tokens_val}
                for param in ['top_p', 'presence_penalty', 'frequency_penalty']:
                    if param_val := llm_config.get(param): payload[param] = param_val
                if not payload.get('model'):
                    if 'model' in payload: del payload['model']
                response = await client.post(api_url, headers=headers, json=payload)
                response.raise_for_status(); result_json = response.json()
                if choices := result_json.get("choices"):
                    if choices and isinstance(choices, list) and len(choices) > 0:
                        if message := choices[0].get("message"):
                            if content := message.get("content"):
                                if isinstance(content, str): return content.strip()
                return f"[Unexpected LLM response format from {llm_config.get('model', llm_role_to_use)}]"
        except httpx.TimeoutException as e: return f"[Timeout connecting to LLM '{llm_config.get('model', llm_role_to_use)}': {e}]"
        except httpx.RequestError as e: return f"[Failed to connect to LLM '{llm_config.get('model', llm_role_to_use)}': {e}]"
        except httpx.HTTPStatusError as e: return f"[LLM '{llm_config.get('model', llm_role_to_use)}' API error ({e.response.status_code}): {e.response.text[:200]}]"
        except json.JSONDecodeError as e_json: response_text = response.text[:500] if response and hasattr(response, 'text') else 'N/A'; return f"[Invalid JSON from LLM '{llm_config.get('model', llm_role_to_use)}': {e_json}. Response: {response_text}]"
        except Exception as e_gen: return f"[Failed to process response from LLM '{llm_config.get('model', llm_role_to_use)}': {e_gen}]"

    async def _run_memory_summarization(self): # From broken (more robust)
        if not self.ethos_config.get('enable_memory_summarization', False): return
        logger.info("Reflection: Starting memory summarization...")
        try:
            min_cluster, max_cluster, max_text_len, max_days = (self.ethos_config.get(k, v) for k, v in [('summarization_cluster_min_memories', 5), ('summarization_max_memories_per_cluster', 15), ('summarization_max_text_length_for_prompt', 10000), ('summarization_max_days_to_consider', 30)])
            conn = self.memory_storage._get_connection(); cursor = conn.cursor(); since_ts = (datetime.now(timezone.utc) - timedelta(days=max_days)).isoformat()
            types = ['interaction', 'world_knowledge', 'document_chunk', 'user_fact', 'learned_correction', 'feedback', 'learned_feedback_insight', 'suggestion_reflection']
            sql = f"SELECT * FROM memories WHERE type IN ({','.join('?' for _ in types)}) AND timestamp >= ? AND (json_extract(metadata, '$.summarized_by_reflection') IS NULL OR json_extract(metadata, '$.summarized_by_reflection') = 0) ORDER BY json_extract(metadata, '$.user_id'), timestamp ASC"
            try: cursor.execute(sql, tuple(types + [since_ts]))
            except sqlite3.OperationalError: sql_fb = f"SELECT * FROM memories WHERE type IN ({','.join('?' for _ in types)}) AND timestamp >= ? ORDER BY timestamp ASC LIMIT 1000"; cursor.execute(sql_fb, tuple(types + [since_ts]))
            rows = cursor.fetchall(); memories_by_key: Dict[str, List[MemoryEntry]] = {}
            for row_data in rows:
                entry = self.memory_storage._row_to_entry(row_data)
                if entry.get('metadata',{}).get('summarized_by_reflection'): continue
                key = "general_knowledge"; entry_type = entry.get('type')
                if entry_type in ['interaction', 'user_fact', 'feedback', 'learned_correction', 'learned_feedback_insight', 'suggestion_reflection']:
                    user_id = entry.get('metadata', {}).get('user_id')
                    if user_id and user_id not in self.system_user_ids: key = f"user_{user_id}"
                    elif user_id in self.system_user_ids and user_id != PATHOS_USER_ID: key = "general_knowledge" # Ensure system interactions go to general
                if key not in memories_by_key: memories_by_key[key] = []
                memories_by_key[key].append(entry)
            for key, mem_list in memories_by_key.items():
                if len(mem_list) < min_cluster: continue
                mem_list.sort(key=lambda x: x.get('timestamp', ''))
                for i in range(0, len(mem_list), max_cluster):
                    chunk = mem_list[i:i+max_cluster]
                    if len(chunk) < min_cluster: continue
                    prompt_content, ids_chunk, current_len = "", [], 0
                    for mem in chunk:
                        content_add = mem.get('content', '')
                        if mem.get('type') in ['feedback', 'learned_correction', 'learned_feedback_insight', 'suggestion_reflection']:
                            try:
                                fb_payload = json.loads(content_add)
                                if isinstance(fb_payload, dict): content_add = f"Feedback Type: {fb_payload.get('feedback_type', fb_payload.get('original_feedback_type', 'N/A'))}, Rating: {fb_payload.get('rating', fb_payload.get('original_feedback_rating', 'N/A'))}, Text: '{fb_payload.get('feedback_text', fb_payload.get('user_suggestion_or_feedback_text', 'N/A'))[:100]}'"
                            except json.JSONDecodeError: pass
                        part = f"Type: {mem.get('type')}, Time: {mem.get('timestamp')}, User: {mem.get('metadata',{}).get('user_id','unknown')}\nContent: {content_add}\n---\n"
                        if current_len + len(part) > max_text_len: break
                        prompt_content += part; current_len += len(part)
                        if mem_id := mem.get('id'): ids_chunk.append(mem_id)
                    if not prompt_content: continue
                    sys_prompt = load_system_prompt("summarization_llm_system_prompt", "Summarize these memories.")
                    user_prompt = f"Please summarize these memories related to '{key}':\n\n{prompt_content}"
                    summary = await self._call_llm_for_internal_task([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}], self.ethos_config.get('summarization_llm_role', 'LOGOS_TECHNE'))
                    if summary and not summary.startswith("["):
                        summary_uid = key.split("user_")[-1] if key.startswith("user_") else "system_reflection"
                        await self.add_memory_entry({"type": "context_summary", "content": summary, "metadata": {"user_id": summary_uid, "source": "ethos_reflection_summarization", "summarized_memory_ids": ids_chunk, "summarization_key": key, "summarization_timestamp": datetime.now(timezone.utc).isoformat()}, "salience": 0.85}, user_id_context=summary_uid)
                        for mem_id in ids_chunk:
                            if orig_entry := self.memory_storage.get_entry(mem_id):
                                meta_upd = orig_entry.get('metadata', {}).copy(); meta_upd['summarized_by_reflection'] = True
                                self.memory_storage.update_entry(mem_id, {'metadata': meta_upd})
                    elif summary: logger.warning(f"Summarization LLM error for '{key}': {summary}")
                    else: logger.warning(f"Failed to generate summary for '{key}', chunk ID {ids_chunk[0] if ids_chunk else 'N/A'}.")
        except Exception as e: logger.error(f"Error in memory summarization: {e}", exc_info=True)

    async def get_recent_dreams(self, user_id_context: Optional[str], limit: int) -> List[MemoryEntry]: # From broken (more robust filtering)
        dream_type, dream_source = "queued_discussion_point", "oneiros_dream_cycle"
        try:
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            sql = "SELECT * FROM memories WHERE type = ? AND json_extract(metadata, '$.source') = ? ORDER BY timestamp DESC LIMIT ?"
            fetch_lim = limit * 3 if user_id_context and user_id_context not in ["system_oneiros", None, PATHOS_USER_ID] else limit * 5
            oe_msg = ""
            try: cursor.execute(sql, (dream_type, dream_source, fetch_lim))
            except sqlite3.OperationalError as oe:
                oe_msg = str(oe).lower()
                if "no such function: json_extract" in oe_msg:
                    sql_fb = "SELECT * FROM memories WHERE type = ? ORDER BY timestamp DESC LIMIT ?"; cursor.execute(sql_fb, (dream_type, fetch_lim * 2))
                else: raise
            rows = cursor.fetchall(); dreams: List[MemoryEntry] = []
            for row_data in rows:
                entry = self.memory_storage._row_to_entry(row_data); meta = entry.get('metadata', {})
                if "no such function: json_extract" in oe_msg:
                    if 'source' not in meta or meta.get('source') != dream_source: continue
                entry_uid = meta.get('user_id')
                if user_id_context and user_id_context not in ["unknown_user", "api_guest_user", "system_oneiros", None, PATHOS_USER_ID]:
                    if entry_uid == user_id_context or entry_uid == "system_oneiros": dreams.append(entry)
                elif user_id_context is None or user_id_context in ["unknown_user", "api_guest_user", "system_oneiros", PATHOS_USER_ID]:
                    if entry_uid == "system_oneiros" or entry_uid == user_id_context: dreams.append(entry)
            if "no such function: json_extract" in oe_msg: dreams.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            return dreams[:limit]
        except Exception as e: logger.error(f"Error retrieving recent dreams: {e}", exc_info=True); return []

    async def _generate_new_aspirations_from_reflection(self): # From broken
        if not self.config.ENABLE_PROACTIVE_BEHAVIOR: return
        asp_llm_role = self.ethos_config.get('aspiration_generation_llm_role', 'LOGOS_TECHNE')
        asp_llm_config = self.config.get_llm_config(asp_llm_role)
        if not asp_llm_config or not asp_llm_config.get('url'): logger.error(f"Aspiration LLM '{asp_llm_role}' not configured."); return
        num_seeds = self.ethos_config.get('aspiration_num_seed_memories', 5)
        min_salience = self.ethos_config.get('aspiration_min_salience_seed', 0.6)
        seeds_raw = await self.retrieve_relevant_memories("Pathos's recent experiences, learnings, future discussions, dreams, desires", num_seeds * 3, min_salience, PATHOS_USER_ID, ['queued_discussion_point', 'learned_feedback_insight', 'suggestion_reflection', 'interaction', 'world_knowledge', 'context_summary'])
        seeds = [m for m in seeds_raw if m.get('type') != 'aspiration']
        if len(seeds) > num_seeds: seeds = random.sample(seeds, num_seeds)
        if not seeds: logger.info("No salient seeds for aspiration generation."); return
        seed_text = "\n\n---\n\n".join([f"Seed {i+1} (Type: {m.get('type', 'N/A')}, Salience: {m.get('salience', 0.0):.2f}):\n{m.get('content', '')[:250]}..." for i, m in enumerate(seeds)])
        sys_prompt = load_system_prompt("aspiration_generation_llm_system_prompt", "Generate aspiration or NO_ASPIRATION_GENERATED.")
        user_prompt = f"Seeds:\n{seed_text}\n\nBased on these, if a new aspiration is sparked, formulate it as JSON (title, aspiration_type, reasoning, potential_timeframe, potential_location, initial_thoughts_or_steps). If not, respond ONLY with: NO_ASPIRATION_GENERATED"
        llm_resp = await self._call_llm_for_internal_task([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}], asp_llm_role)
        if llm_resp and llm_resp.strip().upper() == "NO_ASPIRATION_GENERATED": return
        if llm_resp and not llm_resp.startswith("[LLM"):
            try:
                cleaned = re.sub(r"```json\s*|\s*```", "", llm_resp).strip(); asp_data = json.loads(cleaned)
                if isinstance(asp_data, dict) and all(k in asp_data for k in ["aspiration_title", "aspiration_type", "reasoning"]):
                    existing = await self.memory_storage.get_entries_by_type_and_user("aspiration", PATHOS_USER_ID, 50)
                    if any(json.loads(e['content']).get('title', '').strip().lower() == asp_data['aspiration_title'].strip().lower() for e in existing if isinstance(e.get('content'), str)): return
                    content = {"title": asp_data["aspiration_title"], "type": asp_data["aspiration_type"], "reasoning": asp_data["reasoning"], "status": "pending", "potential_timeframe": asp_data.get("potential_timeframe"), "potential_location": asp_data.get("potential_location"), "initial_thoughts_or_steps": asp_data.get("initial_thoughts_or_steps"), "triggering_memory_ids": [m.get('id') for m in seeds if m.get('id')]}
                    await self.add_memory_entry({"type": "aspiration", "content": json.dumps(content), "metadata": {"user_id": PATHOS_USER_ID, "status": "pending", "aspiration_type_tag": asp_data["aspiration_type"].lower().replace(" ", "_")}, "salience": random.uniform(0.7, 0.9)}, user_id_context=PATHOS_USER_ID)
                    logger.info(f"Generated new aspiration: '{asp_data['aspiration_title']}'")
                else: logger.warning(f"Aspiration LLM JSON missing fields: {asp_data}")
            except json.JSONDecodeError: logger.error(f"Failed to parse aspiration JSON: {llm_resp[:500]}")
        elif llm_resp: logger.error(f"Aspiration LLM call failed: {llm_resp}")

    async def run_reflection_cycle(self): # From broken (more robust)
        if not any([self.config.ENABLE_LEARNING_FROM_FEEDBACK, self.config.ENABLE_CURIOUSITY, self.ethos_config.get('enable_memory_summarization', False), self.config.ENABLE_PROACTIVE_BEHAVIOR]): return
        interval = self.ethos_config.get('reflection_interval_seconds', 86400.0); now = datetime.now(timezone.utc)
        if interval <= 0 or now - self.last_reflection_time < timedelta(seconds=interval): return
        logger.info("--- Ethos: Starting Reflection Cycle ---"); self.hexus_scores_changed_during_reflection = False
        try:
            if self.config.ENABLE_LEARNING_FROM_FEEDBACK:
                logger.info("Reflection: Processing user feedback...")
                try:
                    conn = self.memory_storage._get_connection(); cursor = conn.cursor()
                    sql = "SELECT * FROM memories WHERE type = 'feedback' AND (json_extract(metadata, '$.processed_by_reflection') IS NULL OR json_extract(metadata, '$.processed_by_reflection') = 0) ORDER BY timestamp DESC LIMIT 100"
                    rows_raw = []
                    try: cursor.execute(sql); rows_raw = cursor.fetchall()
                    except sqlite3.OperationalError as oe:
                        if "no such function: json_extract" in str(oe).lower():
                            cursor.execute("SELECT * FROM memories WHERE type = 'feedback' ORDER BY timestamp DESC"); all_fb = cursor.fetchall()
                            rows_raw = [r for r in all_fb if not (json.loads(r['metadata']).get('processed_by_reflection') if r['metadata'] else False)][:100]
                        else: raise
                    entries = [self.memory_storage._row_to_entry(dict(r)) for r in rows_raw]
                    HEXUS_STEP = self.ethos_config.get('hexus_feedback_adjustment_step', 0.05)
                    keywords = {'brevity_inc': [r'too\s+long', r'shorter'], 'brevity_dec': [r'too\s+short', r'more\s+detail'], 'caution_inc': [r'incorrect', r'wrong'], 'caution_dec': [r'confident', r'accurate'], 'proactivity_inc': [r'good\s+idea', r'proactive'], 'proactivity_dec': [r'stop\s+asking', r'annoying'], 'positive_sentiment': [r'helpful', r'good\s+job'], 'negative_sentiment': [r'fail(ed)?', r'error']}
                    for fb_entry in entries:
                        fb_id = fb_entry['id']; meta_upd = fb_entry.get('metadata', {}).copy()
                        try:
                            payload = json.loads(fb_entry['content']); fb_uid = meta_upd.get('user_id', payload.get('user_id', 'unknown')); fb_text = (payload.get('feedback_text') or "").strip().lower(); sugg_resp = (payload.get('suggested_response') or "").strip().lower(); fb_type = payload.get('feedback_type'); fb_rating = payload.get('rating')
                            analysis_text = (fb_text + " " + sugg_resp).strip() or None
                            adj_b, adj_c, adj_p = 0.0, 0.0, 0.0
                            if fb_type == 'positive' or (fb_rating is not None and fb_rating > 0): adj_c -= HEXUS_STEP * 0.5; adj_p += HEXUS_STEP * 0.5
                            elif fb_type == 'negative' or (fb_rating is not None and fb_rating < 0): adj_c += HEXUS_STEP * 0.7; adj_p -= HEXUS_STEP * 0.5
                            elif fb_type == 'correction': adj_c += HEXUS_STEP * 1.0
                            if analysis_text:
                                if any(re.search(p, analysis_text) for p in keywords['brevity_inc']): adj_b += HEXUS_STEP * 1.5
                                elif any(re.search(p, analysis_text) for p in keywords['brevity_dec']): adj_b -= HEXUS_STEP * 1.5
                                if any(re.search(p, analysis_text) for p in keywords['caution_inc']): adj_c += HEXUS_STEP * 1.5
                                elif any(re.search(p, analysis_text) for p in keywords['caution_dec']): adj_c -= HEXUS_STEP * 1.0
                                if any(re.search(p, analysis_text) for p in keywords['proactivity_inc']): adj_p += HEXUS_STEP * 1.0
                                elif any(re.search(p, analysis_text) for p in keywords['proactivity_dec']): adj_p -= HEXUS_STEP * 2.0
                                if adj_b == 0 and adj_c == 0 and adj_p == 0:
                                    if any(re.search(p, analysis_text) for p in keywords['positive_sentiment']): adj_c -= HEXUS_STEP * 0.3; adj_p += HEXUS_STEP * 0.3
                                    elif any(re.search(p, analysis_text) for p in keywords['negative_sentiment']): adj_c += HEXUS_STEP * 0.5; adj_p -= HEXUS_STEP * 0.3
                            init_hexus = self.hexus_scores.copy()
                            self.hexus_scores['brevity_preference'] = max(HEXUS_MIN, min(HEXUS_MAX, self.hexus_scores.get('brevity_preference', 0.0) + adj_b))
                            self.hexus_scores['general_caution'] = max(HEXUS_MIN, min(HEXUS_MAX, self.hexus_scores.get('general_caution', 0.0) + adj_c))
                            self.hexus_scores['user_engagement_proactivity'] = max(HEXUS_MIN, min(HEXUS_MAX, self.hexus_scores.get('user_engagement_proactivity', 0.0) + adj_p))
                            if any(abs(self.hexus_scores[k] - init_hexus[k]) > 1e-5 for k in init_hexus): self.hexus_scores_changed_during_reflection = True
                            
                            should_gen_mono, mono_ctx, mem_type = False, "", "learned_feedback_insight"
                            if fb_type == 'correction': should_gen_mono, mem_type, mono_ctx = True, "learned_correction", f"Original: \"{payload.get('last_user_input','N/A')}\"\nMy Response: \"{payload.get('last_pathos_response','N/A')}\"\nCorrection: \"{sugg_resp or fb_text}\"\n\nLesson learned:"
                            elif fb_type == 'negative' and fb_text: should_gen_mono, mono_ctx = True, f"Original: \"{payload.get('last_user_input','N/A')}\"\nMy Response: \"{payload.get('last_pathos_response','N/A')}\"\nNegative Feedback: \"{fb_text}\"\n\nNote to self:"
                            elif fb_type == 'suggestion' and (fb_text or sugg_resp): should_gen_mono, mem_type, mono_ctx = True, "suggestion_reflection", f"Suggestion: \"{sugg_resp or fb_text}\"\n\nNote to self:"
                            if should_gen_mono:
                                sys_prompt = load_system_prompt("reflection_on_feedback_llm_system_prompt", "Reflect on feedback.")
                                llm_reflect = await self._call_llm_for_internal_task([{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"Context:\n{mono_ctx}\n\nYour concise reflection:"}], self.ethos_config.get('reflection_feedback_llm_role', 'LOGOS_TECHNE'))
                                final_reflect = llm_reflect if llm_reflect and not llm_reflect.startswith("[") else f"Reflection on feedback (type: {fb_type}): User provided: '{fb_text}'. Suggestion: '{sugg_resp}'."
                                reflect_meta = {"source_feedback_id": fb_id, "user_id": fb_uid, "reflection_timestamp": now.isoformat(), "original_feedback_type": fb_type, "original_feedback_rating": fb_rating, "original_user_input": payload.get('last_user_input','N/A'), "original_pathos_response": payload.get('last_pathos_response','N/A'), "user_suggestion_or_feedback_text": sugg_resp or fb_text, "llm_generated_reflection_attempted": bool(llm_reflect and not llm_reflect.startswith("["))}
                                await self.add_memory_entry({"type": mem_type, "content": final_reflect, "salience": 1.25, "metadata": reflect_meta}, user_id_context=fb_uid) # type: ignore
                            meta_upd['processed_by_reflection'] = True; meta_upd['reflection_processing_timestamp'] = now.isoformat()
                            self.memory_storage.update_entry(fb_id, {'metadata': meta_upd})
                        except json.JSONDecodeError: meta_upd['processed_by_reflection'] = True; meta_upd['reflection_error'] = "JSONDecodeError"; self.memory_storage.update_entry(fb_id, {'metadata': meta_upd})
                        except Exception as e_fb_proc: meta_upd['processed_by_reflection'] = True; meta_upd['reflection_error'] = str(e_fb_proc)[:100]; self.memory_storage.update_entry(fb_id, {'metadata': meta_upd})
                except Exception as e_cycle_fb: logger.error(f"Error in feedback processing: {e_cycle_fb}", exc_info=True)
            if self.ethos_config.get('enable_memory_summarization', False): await self._run_memory_summarization()
            if self.config.ENABLE_PROACTIVE_BEHAVIOR: await self._generate_new_aspirations_from_reflection()
            if self.config.ENABLE_CURIOUSITY and self.config.ENABLE_ONEIROS: await self._run_curiosity_on_dreams_cycle(now)
            if self.hexus_scores_changed_during_reflection: self._save_hexus_scores()
        finally:
            self.last_reflection_time = datetime.now(timezone.utc); self._save_task_last_run_time("EthosReflection", self.last_reflection_time)
            logger.info("--- Ethos: Reflection Cycle Finished ---")
            if self.config.ENABLE_PROACTIVE_BEHAVIOR: asyncio.create_task(self.run_proactive_check(trigger_source="Reflection"), name=f"ProactiveCheckAfterReflection_{uuid.uuid4().hex[:8]}")

    async def _run_curiosity_on_dreams_cycle(self, current_cycle_time: datetime): # From broken (more robust)
        logger.info("Reflection: Pathos reflecting on recent dreams for curiosity...")
        try:
            dreams_to_reflect = await self.get_recent_dreams(user_id_context=None, limit=5) # Get system_oneiros dreams
            if not dreams_to_reflect: logger.info("No new dreams to reflect on for curiosity."); return
            for dream_entry in dreams_to_reflect:
                dream_id, dream_content, dream_img_path = dream_entry.get('id'), dream_entry.get('content', "Abstract dream."), dream_entry.get('metadata', {}).get('dream_image_path')
                sys_prompt = load_system_prompt("curiosity_from_dream_llm_system_prompt", "Reflect on dream, formulate research query or state no inquiry.")
                user_prompt_parts = [f"Dream Content: \"{dream_content}\""]
                if dream_img_path: user_prompt_parts.append(f"(Image at: {dream_img_path})")
                user_prompt_parts.append("\n\nDoes this spark curiosity? If yes, formulate a research question/topic. If no, respond ONLY with: 'No further inquiry needed for this insight.'\n\nYour research question/topic (or 'No further inquiry needed for this insight.'):")
                llm_resp = await self._call_llm_for_internal_task([{"role": "system", "content": sys_prompt}, {"role": "user", "content": "\n".join(user_prompt_parts)}], self.ethos_config.get('dream_curiosity_llm_role', 'LOGOS_TECHNE'))
                phil_q, web_q = None, None
                if llm_resp and not llm_resp.startswith("[") and llm_resp.strip().lower() != "no further inquiry needed for this insight.":
                    parsed_json = None
                    try: cleaned = re.sub(r"```json\s*|\s*```", "", llm_resp).strip(); parsed_json = json.loads(cleaned)
                    except json.JSONDecodeError: web_q = llm_resp.strip()
                    if isinstance(parsed_json, dict):
                        phil_q = parsed_json.get("philosophical_research_question")
                        web_q_llm = parsed_json.get("concise_web_search_query")
                        if not web_q_llm and phil_q: web_q = phil_q[:350] if len(phil_q) > 350 else phil_q
                        elif web_q_llm: web_q = web_q_llm.strip()
                    if web_q and self.config.ENABLE_AUTONOMOUS_CURIOSITY_RESEARCH and self.logos_core and self.config.ENABLE_WEB_SEARCH:
                        try:
                            research_res = await self.logos_core.execute_deep_research(web_q)
                            if research_res and not research_res.startswith('{"error":'):
                                knowledge_id = str(uuid.uuid4()); orig_dream_uid = dream_entry.get('metadata', {}).get('user_id', 'system_oneiros')
                                new_knowledge = f"From dream ID {dream_id[:8] if dream_id else 'N/A'}, researched '{web_q}'.\nSummary: {research_res}"
                                await self.add_memory_entry({"id": knowledge_id, "type": "world_knowledge", "content": new_knowledge, "metadata": {"user_id": "system_curiosity", "source": "curiosity_driven_research", "original_dream_id": dream_id, "original_dream_user_id_context": orig_dream_uid, "dream_content_seed": dream_content[:200] + "...", "research_query_philosophical": phil_q, "research_query_web_actual": web_q, "timestamp": current_cycle_time.isoformat()}, "salience": 0.8}, user_id_context="world_knowledge_store")
                                user_to_notify = orig_dream_uid if orig_dream_uid and orig_dream_uid not in self.system_user_ids else None
                                if user_to_notify and self.connection_manager and self.pathos_interface:
                                    notif_sys = "You are Pathos. Share a new insight from a dream reflection."; notif_user = f"Learned from '{web_q}': \"{research_res[:300]}...\"\nCraft a short, proactive message for user '{user_to_notify}'."
                                    notif_content = await self._call_llm_for_internal_task([{"role": "system", "content": notif_sys}, {"role": "user", "content": notif_user}], self.ethos_config.get('curiosity_notification_llm_role', 'LOGOS_TECHNE'))
                                    if notif_content and not notif_content.startswith("["):
                                        ws_payload = {"type": "ethos_event", "event": "newly_learned_knowledge", "payload": {"user_id": user_to_notify, "knowledge_snippet": research_res[:150] + "...", "research_query": web_q, "detailed_summary": research_res, "timestamp": current_cycle_time.isoformat()}}
                                        await self.connection_manager.send_personal_message(ws_payload, user_to_notify)
                                        await self.record_proactive_action(user_to_notify, "shared_newly_learned_knowledge", {"dream_id": dream_id, "query": web_q})
                            elif research_res: logger.warning(f"Deep research for '{web_q}' (dream {dream_id}) error: {research_res}")
                        except Exception as e_res: logger.error(f"Error in autonomous research for '{web_q}': {e_res}", exc_info=True)
                dream_meta_upd = dream_entry.get('metadata', {}).copy(); dream_meta_upd['reflected_for_curiosity'] = True; dream_meta_upd['curiosity_reflection_timestamp'] = current_cycle_time.isoformat()
                if phil_q: dream_meta_upd['philosophical_question_generated'] = phil_q
                if web_q: dream_meta_upd['web_search_query_generated'] = web_q
                self.memory_storage.update_entry(dream_id, {'metadata': dream_meta_upd})
                await asyncio.sleep(random.uniform(2,5))
            if self.config.ENABLE_AUTONOMOUS_CURIOSITY_RESEARCH:
                try:
                    learnings = await self.get_recent_learnings(['learned_feedback_insight', 'suggestion_reflection'], PATHOS_USER_ID, self.ethos_config.get('curiosity_research_on_learnings_limit', 2))
                    for entry in learnings:
                        learn_id, learn_content, learn_meta = entry.get('id'), entry.get('content', "N/A"), entry.get('metadata', {}).copy()
                        action_type = f"autonomous_curiosity_research_learning_{learn_id}"
                        if last_run := await self.get_last_proactive_action_time(PATHOS_USER_ID, action_type):
                            if current_cycle_time - last_run < timedelta(hours=self.ethos_config.get('curiosity_research_on_learnings_interval_hours', 24)): continue
                        query = f"Explore implications of: \"{learn_content}\""[:350]
                        if self.logos_core and self.config.ENABLE_WEB_SEARCH:
                            try:
                                res_content = await self.logos_core.execute_deep_research(query)
                                if res_content and not res_content.startswith('{"error":'):
                                    knowledge_id = str(uuid.uuid4()); new_knowledge = f"Insights from learning (ID: {learn_id[:8] if learn_id else 'N/A'}): '{query}'.\nFindings: {res_content}"
                                    await self.add_memory_entry({"id": knowledge_id, "type": "world_knowledge", "content": new_knowledge, "metadata": {"user_id": "system_curiosity", "source": "curiosity_driven_research_on_learning", "related_learning_id": learn_id, "original_learning_content": learn_content[:200] + "...", "research_query_actual": query, "timestamp": current_cycle_time.isoformat()}, "salience": 0.75}, user_id_context="world_knowledge_store")
                                    await self.record_proactive_action(PATHOS_USER_ID, action_type, {"learning_id": learn_id})
                            except Exception as e_res_learn: logger.error(f"Error in research for learning ID {learn_id}: {e_res_learn}", exc_info=True)
                        await asyncio.sleep(random.uniform(1,3))
                except Exception as e_learn_cur: logger.error(f"Error in Pathos reflects on learnings (curiosity): {e_learn_cur}", exc_info=True)
        except Exception as e_cur_cycle: logger.error(f"Error in curiosity on dreams cycle: {e_cur_cycle}", exc_info=True)

    async def run_managed_forgetting(self): # From broken (more robust)
        if not self.config.ENABLE_MANAGED_FORGETTING: return
        interval = self.ethos_config.get('forgetting_interval_seconds', 0.0); now = datetime.now(timezone.utc)
        if interval <= 0 or now - self.last_forgetting_time < timedelta(seconds=interval): return
        logger.info("Starting Managed Forgetting..."); self.last_forgetting_time = now; self._save_task_last_run_time("EthosForgetting", now)
        try:
            decay_rate, min_salience, user_fact_floor = self.ethos_config.get('salience_decay_rate_per_day', 0.01), self.ethos_config.get('min_salience_for_decay', 0.01), self.ethos_config.get('user_fact_salience_floor', 1.0)
            if not (0 < decay_rate < 1): decay_rate = 0.0
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            cursor.execute("SELECT id, timestamp, salience, type FROM memories WHERE salience IS NOT NULL AND salience > ? AND type != 'user_fact'", (min_salience,))
            entries_check = cursor.fetchall()
            cursor.execute("SELECT id, timestamp, salience, type FROM memories WHERE type = 'user_fact' AND salience IS NOT NULL AND salience > ?", (user_fact_floor,))
            user_facts_check = cursor.fetchall()
            if not entries_check and not user_facts_check: return
            updates = []
            for row in entries_check:
                entry_id, ts_str, cur_s, _ = row['id'], row['timestamp'], row['salience'], row['type']
                try: entry_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                except ValueError: continue
                days_elapsed = (now - entry_time).total_seconds() / 86400.0
                if days_elapsed <= 0: continue
                new_s = cur_s * (math.pow(1.0 - decay_rate, days_elapsed)) if decay_rate > 0 else cur_s
                new_s = max(min_salience, new_s)
                if new_s < cur_s and not math.isclose(new_s, cur_s, rel_tol=1e-5): updates.append((new_s, entry_id))
            for row in user_facts_check:
                entry_id, _, cur_s, _ = row['id'], row['timestamp'], row['salience'], row['type']
                if cur_s > user_fact_floor and not math.isclose(cur_s, user_fact_floor, rel_tol=1e-5): updates.append((user_fact_floor, entry_id))
            if updates: cursor.executemany("UPDATE memories SET salience = ? WHERE id = ?", updates); conn.commit()
        except Exception as e: logger.error(f"Error in Managed Forgetting: {e}", exc_info=True)
        logger.info("Managed Forgetting finished.")

    async def run_hexus_decay(self): # From broken (more robust)
        if not self.hexus_scores: return
        interval = self.ethos_config.get('hexus_decay_interval_seconds', 3600.0); now = datetime.now(timezone.utc)
        if interval <= 0 or now - self.last_hexus_decay_time < timedelta(seconds=interval): return
        logger.info("Running Hexus Score Decay..."); self.last_hexus_decay_time = now; self._save_task_last_run_time("HexusDecay", now)
        decay_rate = self.ethos_config.get('hexus_decay_rate_per_cycle', 0.005)
        if not isinstance(decay_rate, (int, float)) or not (0 <= decay_rate < 1): decay_rate = 0.005
        updated = False; init_hexus = self.hexus_scores.copy()
        for key in DEFAULT_HEXUS_SCORES:
            cur_val = self.hexus_scores.get(key, 0.0)
            new_val = max(HEXUS_MIN, min(HEXUS_MAX, cur_val - (cur_val * decay_rate)))
            if not math.isclose(new_val, cur_val, rel_tol=1e-5): self.hexus_scores[key] = new_val; updated = True
        if updated: self._save_hexus_scores(); logger.info(f"Hexus scores decayed. Initial: {init_hexus}, New: {self.hexus_scores}")

    def update_mood_on_interaction(self, user_input_text: str, pathos_response_text: str, image_provided: bool, document_provided: bool): # From broken
        if not self.config.ENABLE_MOOD_SIMULATION: return
        try:
            valence_shift, arousal_shift = 0.0, 0.0
            valence_shift += MOOD_SHIFT_VALENCE_SUCCESS; arousal_shift += MOOD_SHIFT_AROUSAL_SUCCESS
            if image_provided: valence_shift += 0.05; arousal_shift += 0.02
            if document_provided: valence_shift += 0.03; arousal_shift += 0.01
            user_input_lower = (user_input_text or "").lower()
            positive_indicators = ['thank', 'good', 'great', 'awesome', 'helpful', 'nice', 'love', 'like', 'excellent']
            negative_indicators = ['bad', 'wrong', 'terrible', 'awful', 'hate', 'dislike', 'stupid', 'useless', 'annoying']
            if any(ind in user_input_lower for ind in positive_indicators): valence_shift += MOOD_SHIFT_VALENCE_FEEDBACK_POSITIVE; arousal_shift += MOOD_SHIFT_AROUSAL_FEEDBACK_POSITIVE
            if any(ind in user_input_lower for ind in negative_indicators): valence_shift += MOOD_SHIFT_VALENCE_FEEDBACK_NEGATIVE; arousal_shift += MOOD_SHIFT_AROUSAL_FEEDBACK_NEGATIVE
            if '?' in user_input_text: arousal_shift += 0.02; valence_shift += 0.01
            self.current_mood['valence'] = max(MOOD_MIN, min(MOOD_MAX, self.current_mood['valence'] + valence_shift))
            self.current_mood['arousal'] = max(MOOD_MIN, min(MOOD_MAX, self.current_mood['arousal'] + arousal_shift))
            self.last_mood_update_time = datetime.now(timezone.utc)
            logger.debug(f"Mood updated: V={self.current_mood['valence']:.3f}, A={self.current_mood['arousal']:.3f} (Shifts: v={valence_shift:+.3f}, a={arousal_shift:+.3f})")
        except Exception as e: logger.error(f"Error updating mood: {e}", exc_info=True)

    def get_current_mood(self) -> Dict[str, float]: # From broken (more robust)
        if not self.config.ENABLE_MOOD_SIMULATION: return {"valence": MOOD_VALENCE_BASELINE, "arousal": MOOD_AROUSAL_BASELINE}.copy()
        now = datetime.now(timezone.utc); hours_elapsed = (now - self.last_mood_update_time).total_seconds() / 3600.0
        decay_rate = self.ethos_config.get('mood_decay_rate_per_hour', 0.05)
        if not isinstance(decay_rate, (int, float)) or not (0 <= decay_rate < 1): decay_rate = 0.05
        multiplier = math.pow(1.0 - decay_rate, max(0, hours_elapsed))
        v_offset = self.current_mood['valence'] - MOOD_VALENCE_BASELINE; a_offset = self.current_mood['arousal'] - MOOD_AROUSAL_BASELINE
        return {"valence": max(MOOD_MIN, min(MOOD_MAX, MOOD_VALENCE_BASELINE + (v_offset * multiplier))), "arousal": max(MOOD_MIN, min(MOOD_MAX, MOOD_AROUSAL_BASELINE + (a_offset * multiplier)))}

    def get_persona_directives(self) -> List[str]: return self.persona_directives[:]
    def get_hexus_scores(self) -> Dict[str, float]: return self.hexus_scores.copy()

    async def get_todays_briefing(self) -> Optional[str]: # From broken (more robust)
        today_date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        try:
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            sql = "SELECT content, timestamp FROM memories WHERE type = 'daily_briefing' AND date(timestamp) = date(?) ORDER BY timestamp DESC LIMIT 1"
            cursor.execute(sql, (today_date_str,)); row = cursor.fetchone()
            if row: return row['content']
            return None
        except Exception as e: logger.error(f"Error retrieving briefing: {e}", exc_info=True); return None

    async def update_persona_directives(self, new_directives: List[str]): # From broken
        self.persona_directives = new_directives
        try:
            PERSONA_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(PERSONA_FILE_PATH, 'w', encoding='utf-8') as f: f.write("\n".join(new_directives))
        except Exception as e: logger.error(f"Failed to save persona directives: {e}", exc_info=True)

    async def run_knowledge_upkeep_cycle(self): # From broken (more robust)
        if not self.config.ENABLE_KNOWLEDGE_UPKEEP: return
        interval = self.ethos_config.get('knowledge_upkeep_interval_seconds', 0.0); now = datetime.now(timezone.utc)
        if interval <= 0 or now - self.last_knowledge_upkeep_time < timedelta(seconds=interval): return
        logger.info("--- Ethos: Starting Knowledge Upkeep Cycle ---"); self.last_knowledge_upkeep_time = now; self._save_task_last_run_time("KnowledgeUpkeep", now)
        volatile_tags = self.ethos_config.get('knowledge_upkeep_volatile_tags', [])
        if not volatile_tags: logger.info("--- Ethos: Knowledge Upkeep Cycle Finished (No volatile tags) ---"); return
        try:
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            cursor.execute("SELECT * FROM memories WHERE type = 'world_knowledge' AND metadata IS NOT NULL ORDER BY RANDOM() LIMIT 50"); rows = cursor.fetchall()
            facts_to_verify: List[MemoryEntry] = []
            for row_data in rows:
                entry = self.memory_storage._row_to_entry(row_data)
                entry_tags = [str(t).lower() for t in entry.get('metadata', {}).get('topic_tags', []) if isinstance(t, str)]
                if any(tag_l in [vt.lower() for vt in volatile_tags] for tag_l in entry_tags):
                    facts_to_verify.append(entry)
                    if len(facts_to_verify) >= 5: break
            if not facts_to_verify: logger.info("--- Ethos: Knowledge Upkeep Cycle Finished (No facts to verify) ---"); return
            if not self.logos_core: logger.error("LogosCore not available for knowledge upkeep."); logger.info("--- Ethos: Knowledge Upkeep Cycle Finished (LogosCore missing) ---"); return
            for fact_entry in facts_to_verify:
                fact_id, fact_content = fact_entry.get('id'), fact_entry.get('content')
                res = await self.logos_core.verify_world_fact(fact_entry)
                meta = fact_entry.get('metadata', {}).copy(); meta['last_verified_timestamp'] = now.isoformat(); meta['verification_reason'] = res.get('reason', 'N/A')
                if res.get("status") == "updated":
                    new_content, new_conf = res.get("new_fact_statement"), res.get("confidence", 0.85)
                    new_id = str(uuid.uuid4())
                    await self.add_memory_entry({"id": new_id, "type": "world_knowledge", "content": new_content, "metadata": {"user_id": "system_knowledge_upkeep", "source_description": f"Auto-updated from fact ID {fact_id}", "topic_tags": meta.get('topic_tags',[]), "confidence_level": new_conf, "original_fact_id_verified": fact_id, "last_verified_timestamp": now.isoformat()}, "salience": (fact_entry.get('salience') or 0.7) + 0.1}, user_id_context="world_knowledge_store")
                    meta['status'] = 'outdated_by_upkeep'; meta['superseded_by_fact_id'] = new_id
                    self.memory_storage.update_entry(fact_id, {"metadata": meta, "salience": (fact_entry.get('salience') or 0.5) * 0.5})
                elif res.get("status") == "accurate": meta.pop('verification_attempt_failed', None); self.memory_storage.update_entry(fact_id, {"metadata": meta})
                elif res.get("status") == "unverifiable": meta['verification_attempt_failed'] = True; self.memory_storage.update_entry(fact_id, {"metadata": meta})
                await asyncio.sleep(random.uniform(5, 10))
        except Exception as e: logger.error(f"Error in Knowledge Upkeep: {e}", exc_info=True)
        logger.info("--- Ethos: Knowledge Upkeep Cycle Finished ---")

    async def run_interaction_log_analysis(self): # From broken (more robust)
        if not self.ethos_config.get('enable_interaction_log_analysis', False): return
        interval = self.ethos_config.get('interaction_log_analysis_interval_seconds', 0.0); now = datetime.now(timezone.utc)
        if interval <= 0 or now - self.last_interaction_log_analysis_time < timedelta(seconds=interval): return
        logger.info("--- Ethos: Starting Interaction Log Analysis ---"); self.last_interaction_log_analysis_time = now; self._save_task_last_run_time("InteractionLogAnalysis", now)
        llm_role = self.ethos_config.get('interaction_log_analysis_llm_role', 'LOGOS_TECHNE')
        llm_config = self.config.get_llm_config(llm_role)
        if not llm_config or not llm_config.get('url'): logger.error(f"Interaction Log Analysis LLM '{llm_role}' not configured."); logger.info("--- Ethos: Interaction Log Analysis Finished (LLM Misconfig) ---"); return
        batch_size, max_days = self.ethos_config.get('interaction_log_analysis_batch_size', 20), self.ethos_config.get('interaction_log_analysis_max_days_lookback', 7)
        since_ts = (now - timedelta(days=max_days)).isoformat()
        try:
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            sql = "SELECT * FROM memories WHERE type = 'interaction' AND timestamp >= ? AND (json_extract(metadata, '$.analyzed_for_facts') IS NULL OR json_extract(metadata, '$.analyzed_for_facts') = 0) ORDER BY json_extract(metadata, '$.user_id'), timestamp ASC LIMIT ?"
            oe_msg = ""
            try: cursor.execute(sql, (since_ts, batch_size * 5))
            except sqlite3.OperationalError as oe:
                oe_msg = str(oe).lower()
                if "no such function: json_extract" in oe_msg: sql_fb = "SELECT * FROM memories WHERE type = 'interaction' AND timestamp >= ? ORDER BY timestamp ASC LIMIT ?"; cursor.execute(sql_fb, (since_ts, batch_size * 10))
                else: raise
            rows = cursor.fetchall(); interactions_by_user: Dict[str, List[MemoryEntry]] = {}
            for row_data in rows:
                entry = self.memory_storage._row_to_entry(row_data); meta = entry.get('metadata', {})
                if "no such function: json_extract" in oe_msg and meta.get('analyzed_for_facts') == True: continue
                user_id = meta.get('user_id')
                if user_id and user_id not in self.system_user_ids:
                    if user_id not in interactions_by_user: interactions_by_user[user_id] = []
                    if len(interactions_by_user[user_id]) < batch_size: interactions_by_user[user_id].append(entry)
            if not interactions_by_user: logger.info("--- Ethos: Interaction Log Analysis Finished (No interactions) ---"); return
            for user_id, interactions in interactions_by_user.items():
                if not interactions: continue
                transcript = "\\n".join([f"Timestamp: {i.get('timestamp')}\\n{i.get('content')}\\n---" for i in interactions])
                max_len = (llm_config.get('max_tokens', 4096) if llm_config else 4096) * 2
                if len(transcript) > max_len: transcript = transcript[:max_len] + "\\n[Transcript Truncated]"
                sys_prompt = load_system_prompt("fact_extraction_llm_system_prompt", "Extract user facts, world facts, and AI learnings from transcript.") # Using new prompt
                user_prompt = f"Transcript for User '{user_id}':\\n{transcript}\\n\\nExtract facts/learnings as JSON list (type, attribute_name, attribute_value, supporting_statement):"
                llm_resp = await self._call_llm_for_internal_task([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}], llm_role)
                parsed_ok = False
                if llm_resp and not llm_resp.startswith("[LLM"):
                    try:
                        cleaned = re.sub(r"```json\\s*|\\s*```", "", llm_resp).strip(); items = json.loads(cleaned); parsed_ok = True
                        if not isinstance(items, list): items = []
                        stored_count = 0
                        for item in items:
                            if not isinstance(item, dict): continue
                            item_type, attr_name, attr_val, support = item.get('type'), item.get('attribute_name'), item.get('attribute_value'), item.get('supporting_statement', 'From conversation.')
                            if not item_type or not attr_name or not attr_val: continue
                            norm_key = attr_name.lower().replace(" ", "_").replace("/", "_").strip()
                            if not norm_key: continue
                            if item_type in ['user_fact', 'strongly_implied_user_fact']:
                                await self.add_memory_entry({"type": 'user_fact', "content": json.dumps({"attribute": attr_name, "value": attr_val, "original_user_statement": support}), "metadata": {"user_id": user_id, "fact_attribute_key": norm_key, "source": f"interaction_log_analysis{'_inferred' if item_type == 'strongly_implied_user_fact' else ''}"}, "salience": 1.3}, user_id_context=user_id); stored_count += 1
                            elif item_type == 'world_fact':
                                await self.add_memory_entry({"type": "world_knowledge", "content": f"{attr_name}: {attr_val}", "metadata": {"user_id": "system_reflection", "source_description": f"From conversation with {user_id}: {support}", "topic_tags": [norm_key], "source": "interaction_log_analysis"}, "salience": 0.75}, user_id_context="world_knowledge_store"); stored_count += 1
                            elif item_type == 'ai_learning':
                                await self.add_memory_entry({"type": "learned_correction", "content": f"Learning point regarding '{attr_name}': {attr_val}", "metadata": {"user_id": user_id, "source_interaction_snippet": support, "source": "interaction_log_analysis"}, "salience": 1.1}, user_id_context=user_id); stored_count += 1
                        if stored_count > 0: logger.info(f"Stored {stored_count} facts/learnings for user '{user_id}'.")
                    except json.JSONDecodeError: logger.error(f"Failed to parse fact extraction JSON for user '{user_id}'. Response: {cleaned}")
                    except Exception as e_store: logger.error(f"Error storing extracted facts for user '{user_id}': {e_store}", exc_info=True)
                if llm_resp and not llm_resp.startswith("[LLM"):
                    for entry in interactions:
                        if entry_id := entry.get('id'):
                            if orig_entry := self.memory_storage.get_entry(entry_id):
                                meta_upd = orig_entry.get('metadata', {}).copy(); meta_upd['analyzed_for_facts'] = True; meta_upd['analyzed_for_facts_timestamp'] = now.isoformat()
                                if not parsed_ok: meta_upd['analyzed_for_facts_error'] = "LLM_response_parsing_failed"
                                self.memory_storage.update_entry(entry_id, {'metadata': meta_upd})
                await asyncio.sleep(random.uniform(2,5))
        except Exception as e: logger.error(f"Error in Interaction Log Analysis: {e}", exc_info=True)
        logger.info("--- Ethos: Interaction Log Analysis Finished ---")

    async def get_recent_interaction_topics(self, user_id: str, limit: int = 1) -> List[str]:
        """
        Retrieves potential recent interaction topics for a user.
        MVP: Returns a snippet of the last user input or Pathos response.
        Future: Could use LLM to summarize topics.
        """
        if not user_id or limit <= 0:
            return []

        logger.debug(f"EthosCore: Getting recent interaction topics for user '{user_id}', limit {limit}.")
        
        # Fetch recent interactions
        # We need to ensure 'interaction' type memories are correctly stored with user_id in metadata
        recent_interactions = await self.memory_storage.get_entries_by_type_and_user(
            entry_type='interaction', 
            user_id=user_id, 
            limit=limit * 2 # Fetch a bit more to find distinct topics
        )

        if not recent_interactions:
            logger.debug(f"No recent interactions found for user '{user_id}' to extract topics.")
            return []

        topics: List[str] = []
        seen_content_snippets = set()

        for entry in recent_interactions:
            content = entry.get('content', "")
            if not content:
                continue

            # Simple heuristic: try to get the user's part or Pathos's part
            # Content format is "User (user_id): User input\\nPathos: Pathos response"
            topic_candidate = ""
            user_match = re.search(r"User \\([^)]+\\): (.*?)\\nPathos:", content, re.DOTALL | re.IGNORECASE)
            if user_match and user_match.group(1).strip():
                topic_candidate = user_match.group(1).strip()
            else:
                pathos_match = re.search(r"Pathos: (.*)", content, re.DOTALL | re.IGNORECASE)
                if pathos_match and pathos_match.group(1).strip():
                    topic_candidate = pathos_match.group(1).strip()
            
            if topic_candidate:
                # Take a snippet as the "topic"
                snippet = topic_candidate[:150] # Max 150 chars for a topic snippet
                if snippet not in seen_content_snippets:
                    topics.append(snippet)
                    seen_content_snippets.add(snippet)
                    if len(topics) >= limit:
                        break
        
        logger.debug(f"Extracted topics for user '{user_id}': {topics}")
        return topics

    async def autonomous_long_term_planning_cycle(self): # From broken
        if not self.config.ENABLE_PROACTIVE_BEHAVIOR: return
        if not self.logos_core or not self.chronos_engine: logger.error("LogosCore or ChronosEngine not available for long-term planning."); return
        interval = self.ethos_config.get('long_term_planning_interval_seconds', 86400.0 * 3); now = datetime.now(timezone.utc)
        if interval <= 0 or now - self.last_long_term_planning_time < timedelta(seconds=interval): return
        logger.info("--- EthosCore: Starting Autonomous Long-Term Planning Cycle ---"); self.last_long_term_planning_time = now; self._save_task_last_run_time("PathosLongTermPlanning", now)
        try:
            aspirations = await self.memory_storage.get_entries_by_type_and_user("aspiration", PATHOS_USER_ID, self.ethos_config.get('long_term_planning_max_aspirations', 2))
            aspirations_pending = [a for a in aspirations if isinstance(a.get('content'), str) and json.loads(a['content']).get('status') == 'pending']
            if not aspirations_pending: logger.info("No pending aspirations for Pathos to plan."); logger.info("--- EthosCore: Autonomous Long-Term Planning Cycle Finished (No pending aspirations) ---"); return
            
            planning_llm_role = self.ethos_config.get('long_term_planning_llm_role', 'LOGOS_TECHNE')
            planning_llm_config = self.config.get_llm_config(planning_llm_role)
            if not planning_llm_config or not planning_llm_config.get('url'): logger.error(f"Planning LLM '{planning_llm_role}' not configured."); logger.info("--- EthosCore: Autonomous Long-Term Planning Cycle Finished (LLM Misconfig) ---"); return

            for asp_entry in aspirations_pending:
                asp_id, asp_content_str = asp_entry.get('id'), asp_entry.get('content')
                if not isinstance(asp_content_str, str): continue
                try: asp_data = json.loads(asp_content_str)
                except json.JSONDecodeError: continue
                
                research_notes = asp_data.get('research_notes', "")
                if not research_notes or len(research_notes) < 200: # Arbitrary length to trigger more research
                    research_depth = self.ethos_config.get('long_term_planning_research_depth', 2)
                    research_query = f"Practical steps and considerations for {asp_data.get('title', 'this aspiration')}, focusing on {asp_data.get('type', 'general planning')}"
                    if asp_data.get('potential_location'): research_query += f" in {asp_data['potential_location']}"
                    if asp_data.get('potential_timeframe'): research_query += f" around {asp_data['potential_timeframe']}"
                    
                    logger.info(f"Planning: Researching aspiration '{asp_data.get('title')}' (ID: {asp_id}). Query: {research_query}")
                    new_research = await self.logos_core.execute_deep_research(research_query, research_depth)
                    if new_research and not new_research.startswith('{"error":'):
                        research_notes = (research_notes + "\n\n--- Additional Research (" + now.strftime("%Y-%m-%d") + ") ---\n" + new_research).strip()
                        asp_data['research_notes'] = research_notes
                        self.memory_storage.update_entry(asp_id, {'content': json.dumps(asp_data)})
                        logger.info(f"Updated aspiration {asp_id} with new research notes.")
                    else: logger.warning(f"Research for aspiration {asp_id} yielded no new results or an error.")

                sys_prompt = load_system_prompt("long_term_planning_decision_llm_system_prompt", "You are Pathos, making a decision about an aspiration. Decide to schedule or postpone.")
                user_prompt = f"""Aspiration: "{asp_data.get('title')}" (Type: {asp_data.get('type')})
Reasoning: {asp_data.get('reasoning')}
Potential Timeframe: {asp_data.get('potential_timeframe', 'Not specified')}
Potential Location: {asp_data.get('potential_location', 'Not specified')}
Initial Thoughts/Steps: {asp_data.get('initial_thoughts_or_steps', 'None')}
Research Notes:
{research_notes[:2000] + '...' if research_notes and len(research_notes) > 2000 else research_notes or 'No research notes yet.'}

Based on this, decide if this aspiration is concrete enough to schedule as an event now, or if it needs more thought/research (postpone).
If scheduling, suggest a specific start_date (YYYY-MM-DD), end_date (YYYY-MM-DD), and a refined title.
Respond ONLY with JSON: {{"decision": "SCHEDULE" | "POSTPONE", "reasoning": "brief explanation", "event_title": "if SCHEDULE", "start_date": "YYYY-MM-DD if SCHEDULE", "end_date": "YYYY-MM-DD if SCHEDULE", "event_type": "from aspiration_type if SCHEDULE"}}
"""
                decision_resp = await self._call_llm_for_internal_task([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}], planning_llm_role)
                if decision_resp and not decision_resp.startswith("[LLM"):
                    try:
                        decision_data = json.loads(re.sub(r"```json\s*|\s*```", "", decision_resp).strip())
                        if decision_data.get("decision") == "SCHEDULE" and all(k in decision_data for k in ["event_title", "start_date", "end_date", "event_type"]):
                            event_payload = {"title": decision_data["event_title"], "start_date": decision_data["start_date"], "end_date": decision_data["end_date"], "event_type": decision_data["event_type"], "description": f"Scheduled event for aspiration: {asp_data.get('title')}. Reasoning: {decision_data.get('reasoning')}", "location": asp_data.get('potential_location'), "details": {"activity_theme": asp_data.get('type'), "planned_sites_or_tasks": asp_data.get('initial_thoughts_or_steps') if isinstance(asp_data.get('initial_thoughts_or_steps'), list) else [asp_data.get('initial_thoughts_or_steps')] if asp_data.get('initial_thoughts_or_steps') else None, "related_aspiration_id": asp_id}, "user_id": PATHOS_USER_ID}
                            added_event = await self.chronos_engine.add_planned_event(event_payload)
                            if added_event:
                                asp_data['status'] = 'scheduled'; asp_data['scheduled_event_id'] = added_event.id
                                self.memory_storage.update_entry(asp_id, {'content': json.dumps(asp_data)})
                                logger.info(f"Scheduled event '{added_event.title}' for aspiration {asp_id}.")
                        elif decision_data.get("decision") == "POSTPONE":
                            asp_data['status'] = 'pending_more_info'; asp_data['last_postponed_reason'] = decision_data.get('reasoning')
                            self.memory_storage.update_entry(asp_id, {'content': json.dumps(asp_data)})
                            logger.info(f"Postponed aspiration {asp_id}. Reason: {decision_data.get('reasoning')}")
                    except json.JSONDecodeError: logger.error(f"Failed to parse planning decision JSON: {decision_resp[:500]}")
                elif decision_resp: logger.error(f"Planning LLM call failed: {decision_resp}")
                await asyncio.sleep(random.uniform(3,7))
        except Exception as e: logger.error(f"Error in Autonomous Long-Term Planning: {e}", exc_info=True)
        logger.info("--- EthosCore: Autonomous Long-Term Planning Cycle Finished ---")

    async def get_background_tasks(self) -> List[asyncio.Task]: # From broken (more robust task scheduling)
        tasks = []
        async def _run_periodically(coro_func: Any, interval_seconds: float, task_name: str, initial_last_run_time: datetime):
            if interval_seconds <= 0: return
            now = datetime.now(timezone.utc); time_since_last = now - initial_last_run_time
            wait_time = interval_seconds - time_since_last.total_seconds()
            if wait_time > 0: await asyncio.sleep(wait_time)
            while True:
                try: await coro_func()
                except asyncio.CancelledError: logger.info(f"Task '{task_name}' cancelled."); break
                except Exception as e: logger.error(f"Error in task '{task_name}': {e}", exc_info=True)
                await asyncio.sleep(interval_seconds)

        now_utc = datetime.now(timezone.utc)
        task_configs = [
            (self.run_reflection_cycle, self.ethos_config.get('reflection_interval_seconds', 86400.0), "EthosReflection", any([self.config.ENABLE_LEARNING_FROM_FEEDBACK, self.config.ENABLE_CURIOUSITY, self.ethos_config.get('enable_memory_summarization', False), self.config.ENABLE_PROACTIVE_BEHAVIOR])),
            (self.run_managed_forgetting, self.ethos_config.get('forgetting_interval_seconds', 43200.0), "EthosForgetting", self.config.ENABLE_MANAGED_FORGETTING),
            (self.run_hexus_decay, self.ethos_config.get('hexus_decay_interval_seconds', 3600.0), "HexusDecay", True),
            (self.oneiros_module.run_dream_cycle if self.oneiros_module else None, self.config.ONEIROS.get('dream_interval_seconds', 21600.0), "OneirosDreamCycle", self.config.ENABLE_ONEIROS and self.oneiros_module),
            (self.run_knowledge_upkeep_cycle, self.ethos_config.get('knowledge_upkeep_interval_seconds', 86400.0), "KnowledgeUpkeep", self.config.ENABLE_KNOWLEDGE_UPKEEP),
            (self.run_interaction_log_analysis, self.ethos_config.get('interaction_log_analysis_interval_seconds', 86400.0), "InteractionLogAnalysis", self.ethos_config.get('enable_interaction_log_analysis', False)),
            (self.run_proactive_check, self.ethos_config.get('proactive_check_interval_seconds', 60.0), "ProactiveCheck", self.config.ENABLE_PROACTIVE_BEHAVIOR),
            (self.chronos_engine.daily_schedule_maintenance_task if self.chronos_engine else None, self.ethos_config.get('chronos_maintenance_interval_seconds', 21600.0), "ChronosDailyScheduleMaintenance", self.chronos_engine is not None), # New
            (self.autonomous_long_term_planning_cycle, self.ethos_config.get('long_term_planning_interval_seconds', 86400.0 * 3), "PathosLongTermPlanning", self.config.ENABLE_PROACTIVE_BEHAVIOR and self.chronos_engine is not None) # New
        ]
        for coro, interval, name, enabled_flag in task_configs:
            if coro and enabled_flag and interval > 0:
                last_run = self._get_initial_last_run_time(name, float(interval), now_utc)
                tasks.append(asyncio.create_task(_run_periodically(coro, float(interval), name, last_run), name=name))
        logger.info(f"Background tasks initialized: {[task.get_name() for task in tasks]}")
        return tasks

    async def trigger_proactive_check_after_event(self, event_name: str):
        """
        A wrapper to trigger a proactive check, typically after a significant system event.
        """
        if not self.config.ENABLE_PROACTIVE_BEHAVIOR:
            logger.debug(f"Proactive behavior disabled, skipping proactive check triggered by '{event_name}'.")
            return

        logger.info(f"Proactive check triggered by system event: '{event_name}'.")
        # Create a task to run the proactive check without blocking the caller
        asyncio.create_task(self.run_proactive_check(trigger_source=f"SystemEvent_{event_name}"), name=f"ProactiveCheck_Event_{event_name}")

    async def run_proactive_check(self, trigger_source: str = "Manual"): # From broken (more robust)
        if not self.config.ENABLE_PROACTIVE_BEHAVIOR or not self.connection_manager or not self.pathos_interface: return
        now_utc = datetime.now(timezone.utc)
        for user_id in list(self.connection_manager.active_connections.keys()):
            now_local = await self.get_local_datetime_for_user(user_id)
            current_hod = "morning" if 5 <= now_local.hour < 12 else "afternoon" if 12 <= now_local.hour < 18 else "evening"
            opportunity, details = None, None
            queued_points = await self.get_queued_discussion_points(user_id, 1)
            if queued_points:
                pt = queued_points[0]; pt_id, pt_content, pt_reason = pt.get('id'), pt.get('content'), pt.get('metadata', {}).get('reason_for_queueing', 'earlier thoughts')
                action_type = f"offered_queued_discussion_{pt_id}"
                if not (last_offer := await self.get_last_proactive_action_time(user_id, action_type)) or (now_utc - last_offer > timedelta(hours=self.ethos_config.get('proactive_queued_point_offer_interval_hours', 24))):
                    if random.random() < float(self.ethos_config.get('proactive_queued_point_chance', 0.5)): # type: ignore
                        opportunity, details = "queued_discussion", {"point_id": pt_id, "topic_content": pt_content, "reason": pt_reason}
            if not opportunity:
                last_greet = await self.get_last_proactive_action_time(user_id, "greeting")
                greet_interval = self.ethos_config.get('proactive_greeting_interval_hours', 4)
                last_greet_hod = ("morning" if 5 <= last_greet.hour < 12 else "afternoon" if 12 <= last_greet.hour < 18 else "evening") if last_greet else "none"
                needs_greet = not last_greet or (last_greet_hod != current_hod) or (now_utc - last_greet > timedelta(hours=greet_interval))
                if needs_greet and random.random() < float(self.ethos_config.get('proactive_greeting_chance', 0.3)): # type: ignore
                    opportunity, details = "greeting", {"time_of_day": current_hod}
            if not opportunity and self.config.ENABLE_DAILY_CONTEXT:
                briefing = await self.get_todays_briefing()
                if briefing is None and self.logos_core: asyncio.create_task(self.logos_core.generate_daily_briefing(user_id_context=user_id), name=f"GenBriefing_{now_utc.strftime('%Y%m%d')}_{user_id}")
                elif briefing:
                    if not (last_offer := await self.get_last_proactive_action_time(user_id, "offer_briefing_discussion")) or last_offer.date() < now_utc.date():
                        if random.random() < float(self.ethos_config.get('proactive_briefing_chance', 0.4)): # type: ignore
                            opportunity, details = "offer_briefing_discussion", {"briefing_date": now_utc.strftime('%Y%m%d'), "full_briefing_content": briefing}
            if not opportunity:
                if topics := await self.get_recent_interaction_topics(user_id, 1):
                    topic = topics[0]; topic_key = re.sub(r'\W+', '_', topic[:50].lower()).strip('_') or "generic"
                    action_type = f"offer_topic_continuation_{topic_key}"
                    if not (last_offer := await self.get_last_proactive_action_time(user_id, action_type)) or (now_utc - last_offer > timedelta(hours=self.ethos_config.get('proactive_topic_interval_hours', 12))):
                        if random.random() < float(self.ethos_config.get('proactive_topic_chance', 0.2)): # type: ignore
                            opportunity, details = "offer_topic_continuation", {"topic": topic}
            if opportunity and self.pathos_interface:
                proactive_msg_tuple = await self.pathos_interface._generate_proactive_message(user_id, opportunity, details)
                proactive_text, proactive_audio_chunks = proactive_msg_tuple
                if proactive_text:
                    proactive_id = str(uuid.uuid4())
                    ws_payload = {"type": "unsolicited_message", "payload": {"content": [proactive_text, proactive_audio_chunks], "metadata": {"proactive_type": opportunity, "proactive_utterance_id": proactive_id, "timestamp": now_utc.isoformat(), "mood_at_generation": self.get_current_mood(), "hexus_at_generation": self.get_hexus_scores()}}}
                    await self.connection_manager.send_personal_message(ws_payload, user_id)
                    action_to_rec = f"offered_queued_discussion_{details['point_id']}" if opportunity == "queued_discussion" and details and "point_id" in details else opportunity
                    await self.record_proactive_action(user_id, action_to_rec, details)
                    if opportunity == "queued_discussion" and details and "point_id" in details: await self.mark_queued_point_offered(details["point_id"], user_id)

    async def get_all_user_facts(self, user_id: str) -> List[MemoryEntry]: # From broken (more robust)
        if not user_id or user_id in self.system_user_ids: return []
        try:
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            sql = "SELECT * FROM memories WHERE type = 'user_fact' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.fact_attribute_key') IS NOT NULL ORDER BY timestamp DESC"
            oe_msg = ""
            try: cursor.execute(sql, (user_id,))
            except sqlite3.OperationalError as oe:
                oe_msg = str(oe).lower()
                if "no such function: json_extract" in oe_msg: sql_fb = "SELECT * FROM memories WHERE type = 'user_fact' ORDER BY timestamp DESC"; cursor.execute(sql_fb)
                else: raise
            rows_raw = cursor.fetchall(); facts_rows = []
            if "no such function: json_extract" in oe_msg:
                for row_data in rows_raw:
                    try:
                        meta = json.loads(dict(row_data)['metadata'])
                        if meta.get('user_id') == user_id and meta.get('fact_attribute_key') is not None: facts_rows.append(row_data)
                    except (json.JSONDecodeError, ValueError, TypeError): continue
            else: facts_rows = rows_raw
            return [self.memory_storage._row_to_entry(dict(r)) for r in facts_rows]
        except Exception as e: logger.error(f"Error retrieving user_facts for '{user_id}': {e}", exc_info=True); return []

    async def clear_memory_for_user(self, user_id: str) -> bool: # From broken
        if not user_id or not user_id.strip(): return False
        try: return self.memory_storage.delete_entries_by_user_id(user_id)
        except Exception as e: logger.error(f"Error clearing memory for user '{user_id}': {e}", exc_info=True); return False

    async def get_recent_learnings(self, learning_types: List[str], user_id_context: Optional[str], limit: int) -> List[MemoryEntry]: # From broken (more robust)
        if not learning_types or limit <= 0: return []
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        placeholders = ','.join('?' * len(learning_types)); sql = f"SELECT * FROM memories WHERE type IN ({placeholders})"
        params: List[Any] = list(learning_types)
        can_use_json = True
        try: cursor.execute("SELECT json_extract('{\"k\":\"v\"}', '$.k')")
        except sqlite3.OperationalError: can_use_json = False
        if can_use_json:
            if user_id_context and user_id_context not in self.system_user_ids: sql += " AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') = ?)"; params.extend([user_id_context, PATHOS_USER_ID])
            elif user_id_context in self.system_user_ids or not user_id_context: sql += " AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') IS NULL)"; params.append(PATHOS_USER_ID)
        sql += " ORDER BY timestamp DESC LIMIT ?"; params.append(limit * 5 if not can_use_json else limit)
        try:
            cursor.execute(sql, tuple(params)); rows = cursor.fetchall(); learnings: List[MemoryEntry] = []
            for row_data in rows:
                entry = self.memory_storage._row_to_entry(dict(row_data)); entry_uid = entry.get('metadata', {}).get('user_id')
                if not can_use_json:
                    if user_id_context and user_id_context not in self.system_user_ids:
                        if entry_uid != user_id_context and entry_uid != PATHOS_USER_ID: continue
                    elif user_id_context in self.system_user_ids or not user_id_context:
                        if entry_uid != PATHOS_USER_ID and entry_uid is not None: continue
                learnings.append(entry)
            if not can_use_json: learnings.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            return learnings[:limit]
        except Exception as e: logger.error(f"Error retrieving learnings: {e}", exc_info=True); return []

    async def get_recent_knowledge_verifications(self, limit: int = 20) -> List[MemoryEntry]: # From broken (more robust)
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        sql = "SELECT * FROM memories WHERE type = 'world_knowledge' AND json_extract(metadata, '$.last_verified_timestamp') IS NOT NULL ORDER BY json_extract(metadata, '$.last_verified_timestamp') DESC LIMIT ?"
        oe_msg = ""
        try: cursor.execute(sql, (limit,))
        except sqlite3.OperationalError as oe:
            oe_msg = str(oe).lower()
            if "no such function: json_extract" in oe_msg: sql_fb = "SELECT * FROM memories WHERE type = 'world_knowledge' ORDER BY timestamp DESC LIMIT ?"; cursor.execute(sql_fb, (limit * 5,))
            else: raise
        rows = cursor.fetchall(); verifications: List[MemoryEntry] = []
        for row_data in rows:
            entry = self.memory_storage._row_to_entry(dict(row_data))
            if "no such function: json_extract" in oe_msg and entry.get('metadata', {}).get('last_verified_timestamp') is None: continue
            verifications.append(entry)
        if "no such function: json_extract" in oe_msg: verifications.sort(key=lambda x: x.get('metadata', {}).get('last_verified_timestamp', ''), reverse=True)
        return verifications[:limit]

    async def get_user_profile_summary(self, user_id: str) -> str: # From broken
        if not user_id or user_id in self.system_user_ids: return "No specific profile information available for this user yet."
        facts = await self.get_all_user_facts(user_id)
        if not facts: return "No specific profile information available for this user yet."
        parts = []
        for fact in facts[:10]:
            try:
                if content_str := fact.get('content'):
                    content_data = json.loads(content_str)
                    key, val = content_data.get('attribute', 'unknown'), content_data.get('value', 'unknown')
                    if key == 'name': parts.append(f"Name: {val}")
                    elif key == 'preferred_location': parts.append(f"Location: {val}")
                    else: parts.append(f"{key.replace('_', ' ').title()}: {val}")
            except (json.JSONDecodeError, KeyError): continue
        return f"User profile: {'; '.join(parts[:5])}" if parts else "No specific profile information available for this user yet."

    async def get_current_activity_description(self) -> str: # From broken (uses Chronos)
        try:
            if not self.chronos_engine: return "Activity information temporarily unavailable (system error)."
            now_local = await self.get_local_datetime_for_user(PATHOS_USER_ID)
            current_activity: Optional['ActivitySlot'] = await self.chronos_engine.get_current_activity(now_local)
            if current_activity:
                desc = f"Currently: {current_activity.activity_title}"
                if current_activity.activity_details and current_activity.activity_details.description: desc += f" - {current_activity.activity_details.description}"
                return desc
            return "No scheduled activity at the moment"
        except Exception as e: logger.error(f"Error getting current activity: {e}", exc_info=True); return "Activity information temporarily unavailable"

    async def get_pathos_schedule_context_for_prompt(self) -> str: # From broken (uses Chronos)
        try:
            if not self.chronos_engine: return "Schedule information temporarily unavailable (system error)."
            schedule = await self.chronos_engine.get_todays_schedule_for_user() # Assumes this gets Pathos's schedule
            if not schedule: return "No scheduled activities for today"
            lines = ["Today's Schedule:"]
            for activity in schedule:
                time_str = f"{activity.start_time.strftime('%H:%M')}-{activity.end_time.strftime('%H:%M')}"
                line = f"• {time_str}: {activity.activity_title}"
                if activity.activity_details and activity.activity_details.description: line += f" - {activity.activity_details.description}"
                lines.append(line)
            return "\n".join(lines)
        except Exception as e: logger.error(f"Error getting schedule context: {e}", exc_info=True); return "Schedule information temporarily unavailable"

    async def get_pathos_aspirations_context_for_prompt(self) -> str: # From broken
        try:
            aspirations = await self.memory_storage.get_entries_by_type_and_user("aspiration", PATHOS_USER_ID, 10)
            if not aspirations: return "No current aspirations defined"
            lines = ["Current Aspirations:"]
            for entry in aspirations:
                if content_str := entry.content:
                    try:
                        content_data = json.loads(content_str)
                        text = content_data.get('title', str(content_data)) if isinstance(content_data, dict) else str(content_data)
                    except json.JSONDecodeError: text = content_str
                    lines.append(f"• {text}")
            return "\n".join(lines)
        except Exception as e: logger.error(f"Error getting aspirations context: {e}", exc_info=True); return "Aspirations information temporarily unavailable"

    async def get_todays_briefing_context_for_prompt(self, user_id: str) -> str: # From broken
        try:
            if not self.logos_core: return "Briefing service unavailable."
            briefing_data = await self.logos_core.get_or_generate_daily_briefing(user_id)
            if briefing_data and briefing_data.get('success') and briefing_data.get('briefing_content'):
                # Truncate for prompt if too long
                content = briefing_data['briefing_content']
                max_len = 1500 # Example limit
                return f"Today's Briefing Highlights:\n{content[:max_len] + '...' if len(content) > max_len else content}"
            return "No briefing available for today"
        except Exception as e: logger.error(f"Error getting briefing context: {e}", exc_info=True); return "Briefing information temporarily unavailable"

    async def chronos_bridge_add_event(self, title: str, start_date_str: str, end_date_str: str, event_type_str: str, description: Optional[str], location: Optional[str], activity_theme: Optional[str], planned_sites_or_tasks: Optional[List[str]], user_id_for_event: str) -> Optional[str]: # New
        if not self.chronos_engine:
            logger.error("ChronosEngine not available in EthosCore to add event.")
            return None
        try:
            event_data = {
                "title": title, "start_date": start_date_str, "end_date": end_date_str,
                "event_type": event_type_str, "description": description, "location": location,
                "details": {"activity_theme": activity_theme, "planned_sites_or_tasks": planned_sites_or_tasks},
                "user_id": user_id_for_event
            }
            added_event = await self.chronos_engine.add_planned_event(event_data)
            return added_event.id if added_event else None
        except Exception as e:
            logger.error(f"Error in chronos_bridge_add_event: {e}", exc_info=True)
            return None

    async def get_queued_discussion_points(self, user_id: str, limit: int = 1) -> List[MemoryEntry]:
        if not user_id: return []
        logger.debug(f"EthosCore: Fetching queued discussion points for user_id: {user_id}, limit: {limit}")
        conn = self.memory_storage._get_connection()
        cursor = conn.cursor()
        
        # Determine if json_extract is available
        can_use_json_extract = True
        try:
            # Use a simple query that should work if json_extract exists
            cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')")
            # Check if the result is what we expect (e.g., a single row with 'value')
            result = cursor.fetchone()
            if result is None or result[0] != 'value':
                 # json_extract might exist but not work as expected, treat as unavailable
                 can_use_json_extract = False
        except Exception as e_test: # Catch broader exceptions for robustness
            logger.debug(f"json_extract test failed: {e_test}")
            can_use_json_extract = False
        
        queued_points: List[MemoryEntry] = []
        
        if can_use_json_extract:
            sql_query = """
                SELECT * FROM memories
                WHERE type = 'queued_discussion_point'
                  AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') IS NULL)
                  AND (json_extract(metadata, '$.status') IS NULL OR json_extract(metadata, '$.status') = 'pending')
                ORDER BY salience DESC, timestamp DESC
                LIMIT ?
            """
            # User specific points, system_oneiros points, or points with no user_id (considered global for Pathos)
            # PATHOS_USER_ID is for Pathos's own scheduled events/aspirations that might become discussion points
            # Fetch a bit more than limit to ensure we have enough after potential filtering/sorting
            fetch_limit = limit * 2 if limit > 0 else 10 # Ensure fetch_limit is positive
            cursor.execute(sql_query, (user_id, "system_oneiros", fetch_limit))
        else:
            logger.warning("json_extract not available for get_queued_discussion_points. Querying all and filtering in Python.")
            sql_query_fallback = "SELECT * FROM memories WHERE type = 'queued_discussion_point' ORDER BY timestamp DESC LIMIT ?"
            fetch_limit = limit * 10 if limit > 0 else 100 # Fetch more for Python filtering
            cursor.execute(sql_query_fallback, (fetch_limit,))

        rows_raw = cursor.fetchall()
        
        for row_data_raw in rows_raw:
            try:
                entry = self.memory_storage._row_to_entry(dict(row_data_raw))
                metadata = entry.get('metadata', {})
                entry_user_id = metadata.get('user_id')
                status = metadata.get('status', 'pending')

                if not can_use_json_extract: # Python-side filtering
                    if status != 'pending': continue
                    if not (entry_user_id == user_id or entry_user_id == "system_oneiros" or entry_user_id is None):
                        continue
                
                # Additional filter: Ensure it hasn't been offered too recently if that logic is elsewhere
                # For now, just return based on status and user_id match
                queued_points.append(entry)
            except Exception as e_entry:
                 logger.error(f"Error processing queued discussion point entry: {e_entry}", exc_info=True)
                 # Continue processing other entries

        # Sort again if Python filtering was used, or just to be sure if SQL sort wasn't perfect
        # Higher salience first, then older first
        queued_points.sort(key=lambda x: (-(float(x.get('salience', 0.0)) if x.get('salience') is not None else 0.0), x.get('timestamp', '') or ''), reverse=False)

        logger.info(f"Retrieved {len(queued_points[:limit])} queued discussion points for user_id: {user_id}")
        return queued_points[:limit]

    async def get_last_proactive_action_time(self, user_id: str, action_type: str) -> Optional[datetime]: # From broken
        """
        Retrieves the timestamp of the last time a specific proactive action was taken for a user.
        """
        if not user_id or not action_type:
            return None
        
        conn = self.memory_storage._get_connection()
        cursor = conn.cursor()
        
        # Determine if json_extract is available
        can_use_json_extract = True
        try:
            cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')")
        except sqlite3.OperationalError as oe_test:
            if "no such function: json_extract" in str(oe_test).lower():
                can_use_json_extract = False
            else:
                # Log other operational errors but assume json_extract is not available to be safe
                logger.error(f"Unexpected SQLite error checking json_extract for get_last_proactive_action_time: {oe_test}", exc_info=True)
                can_use_json_extract = False
        
        sql_query = ""
        params: List[Any] = []

        if can_use_json_extract:
            sql_query = """
                SELECT timestamp FROM memories
                WHERE type = 'proactive_action_record'
                  AND json_extract(metadata, '$.user_id') = ?
                  AND json_extract(metadata, '$.action_type') = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """
            params = [user_id, action_type]
        else:
            logger.warning(f"json_extract not available for get_last_proactive_action_time (user: {user_id}, action: {action_type}). This will be less efficient.")
            # Fallback: Fetch more and filter in Python (less efficient)
            sql_query = """
                SELECT timestamp, metadata FROM memories
                WHERE type = 'proactive_action_record'
                ORDER BY timestamp DESC
                LIMIT 50 
            """ # Limit to avoid fetching too many if json_extract is missing

        try:
            cursor.execute(sql_query, tuple(params))
            if not can_use_json_extract:
                # Python-side filtering
                for row_data_raw in cursor.fetchall():
                    row_dict = dict(row_data_raw)
                    metadata_str = row_dict.get('metadata')
                    if metadata_str:
                        try:
                            metadata = json.loads(metadata_str)
                            if metadata.get('user_id') == user_id and metadata.get('action_type') == action_type:
                                return datetime.fromisoformat(row_dict['timestamp'].replace("Z", "+00:00"))
                        except (json.JSONDecodeError, ValueError, TypeError):
                            continue # Skip malformed entries
                return None # Not found after Python filtering
            else:
                # Direct SQL query result
                row = cursor.fetchone()
                if row:
                    return datetime.fromisoformat(row['timestamp'].replace("Z", "+00:00"))
                return None
        except Exception as e:
            logger.error(f"Error retrieving last proactive action time for user '{user_id}', action '{action_type}': {e}", exc_info=True)
            return None

    async def record_proactive_action(self, user_id: str, action_type: str, details: Optional[Dict[str, Any]] = None): # From broken
        """Records that a proactive action was taken."""
        if not user_id or not action_type:
            logger.warning("Cannot record proactive action: user_id or action_type missing.")
            return

        metadata = {
            "user_id": user_id,
            "action_type": action_type,
            "action_details": details or {}
        }
        await self.add_memory_entry(
            entry_data={
                "type": "proactive_action_record",
                "content": f"Proactive action '{action_type}' taken for user '{user_id}'. Details: {json.dumps(details)}",
                "metadata": metadata,
                "salience": 0.1 # Low salience, just a record
            },
            user_id_context=user_id # Or system if it's a system-wide proactive thing
        )
        logger.info(f"Recorded proactive action '{action_type}' for user '{user_id}'.")

    async def mark_queued_point_offered(self, point_id: str, user_id: str): # From broken
        """Marks a queued discussion point as 'offered'."""
        if not point_id: return
        entry = self.memory_storage.get_entry(point_id)
        if entry and entry.get('type') == 'queued_discussion_point':
            metadata = entry.get('metadata', {}).copy()
            metadata['status'] = 'offered'
            metadata['offered_to_user_id'] = user_id
            metadata['offered_timestamp'] = datetime.now(timezone.utc).isoformat()
            self.memory_storage.update_entry(point_id, {'metadata': metadata})
            logger.info(f"Marked queued discussion point '{point_id}' as offered to user '{user_id}'.")
