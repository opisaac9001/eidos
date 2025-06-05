import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Union
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
from .memory_storage import MemoryStorage, MemoryEntry # Updated to relative import
from eidos_agent.utils.logger import get_logger
import pytz # Added import


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from eidos_agent.features.oneiros import OneirosModule # Updated import
    from eidos_agent.core.connection_manager import ConnectionManager
    from eidos_agent.modules.pathos_interface import PathosInterface # This will be updated in a later task
    from eidos_agent.persona_logic.logos_core.handler import LogosCore # Updated import
    # Updated import for ChronosEngine and related types
experimental/eidos-subconscious-integration
    from eidos_agent.persona_logic.chronos_engine import ChronosEngine, ActivitySlot, PATHOS_USER_ID

# PATHOS_USER_ID is now imported via TYPE_CHECKING block or directly if not under TYPE_CHECKING
# from eidos_agent.modules.chronos_engine import PATHOS_USER_ID # This line is removed

    from eidos_agent.persona_logic.chronos_engine import ChronosEngine, ActivitySlot
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

logger = get_logger(__name__)

PERSONA_FILE_PATH = PROJECT_ROOT / "persona" / "pathos_directives.txt"
HEXUS_STATE_FILENAME = "hexus_state.json"
TASK_LAST_RUN_TIMES_FILENAME = "task_last_run_times.json"

MOOD_VALENCE_BASELINE = 0.0
MOOD_AROUSAL_BASELINE = 0.0
MOOD_MIN = -1.0
MOOD_MAX = 1.0
MOOD_SHIFT_VALENCE_SUCCESS = 0.15
MOOD_SHIFT_AROUSAL_SUCCESS = 0.05
MOOD_SHIFT_VALENCE_FAILURE = -0.2
MOOD_SHIFT_AROUSAL_FAILURE = 0.1
MOOD_SHIFT_VALENCE_FEEDBACK_POSITIVE = 0.1
MOOD_SHIFT_AROUSAL_FEEDBACK_POSITIVE = 0.05
MOOD_SHIFT_VALENCE_FEEDBACK_NEGATIVE = -0.15
MOOD_SHIFT_AROUSAL_FEEDBACK_NEGATIVE = 0.05
HEXUS_MIN = -1.0
HEXUS_MAX = 1.0
DEFAULT_HEXUS_SCORES = {
    "general_caution": 0.0,
    "user_engagement_proactivity": 0.0,
    "brevity_preference": 0.0
}

class EthosCore:
    def __init__(self, config: Config):
        self.config = config
        self.ethos_config: EthosConfig = config.get_ethos_config()
        self.memory_storage = MemoryStorage(config)
        self.hexus_state_file_path = self.memory_storage.memory_db_path.parent / HEXUS_STATE_FILENAME
        self.task_last_run_times_file_path = self.memory_storage.memory_db_path.parent / TASK_LAST_RUN_TIMES_FILENAME
        self._task_last_run_times_cache: Dict[str, datetime] = self._load_task_last_run_times()

        self.current_mood: Dict[str, float] = {"valence": MOOD_VALENCE_BASELINE, "arousal": MOOD_AROUSAL_BASELINE}
        self.last_mood_update_time: datetime = datetime.now(timezone.utc)
        self.persona_directives: List[str] = self._load_persona_from_file()
        self.hexus_scores: Dict[str, float] = self._load_hexus_scores()

        now_utc_init = datetime.now(timezone.utc)
        reflection_interval = self.ethos_config.get('reflection_interval_seconds', 86400.0)
        self.last_reflection_time = self._get_initial_last_run_time("EthosReflection", float(reflection_interval), now_utc_init)
        
        forgetting_interval_default = float(reflection_interval) * 0.5 if reflection_interval > 0 else 43200.0
        forgetting_interval = self.ethos_config.get('forgetting_interval_seconds', forgetting_interval_default)
        self.last_forgetting_time = self._get_initial_last_run_time("EthosForgetting", float(forgetting_interval), now_utc_init)
        
        hexus_decay_interval = self.ethos_config.get('hexus_decay_interval_seconds', 3600.0)
        self.last_hexus_decay_time = self._get_initial_last_run_time("HexusDecay", float(hexus_decay_interval), now_utc_init)
        
        knowledge_upkeep_interval = self.ethos_config.get('knowledge_upkeep_interval_seconds', 86400.0)
        self.last_knowledge_upkeep_time = self._get_initial_last_run_time("KnowledgeUpkeep", float(knowledge_upkeep_interval), now_utc_init)
        
        interaction_log_analysis_interval = self.ethos_config.get('interaction_log_analysis_interval_seconds', 86400.0)
        self.last_interaction_log_analysis_time = self._get_initial_last_run_time("InteractionLogAnalysis", float(interaction_log_analysis_interval), now_utc_init)
        
        long_term_planning_interval = self.ethos_config.get('long_term_planning_interval_seconds', 86400.0 * 3)
        self.last_long_term_planning_time = self._get_initial_last_run_time("PathosLongTermPlanning", float(long_term_planning_interval), now_utc_init)

        # For Oneiros dream cycle timing (if Oneiros is enabled)
        oneiros_interval = self.config.ONEIROS.get('dream_interval_seconds', 21600.0) if self.config.ONEIROS else 21600.0
        self.last_dream_time = self._get_initial_last_run_time("OneirosDreamCycle", float(oneiros_interval), now_utc_init)


        self.oneiros_module: Optional['OneirosModule'] = None
        self.connection_manager: Optional['ConnectionManager'] = None
        self.pathos_interface: Optional['PathosInterface'] = None
        self.logos_core: Optional['LogosCore'] = None
        self.chronos_engine: Optional['ChronosEngine'] = None

        self.system_user_ids: List[Optional[str]] = [
            "unknown_user", "api_guest_user", "system_oneiros", "system_document", "system_briefing",
            "system_reflection", "world_knowledge_store", "system_knowledge_upkeep", "system_curiosity",
            "system_admin", PATHOS_USER_ID, None, "default_user"
        ]
        self.hexus_scores_changed_during_reflection = False
        logger.info("EthosCore initialized with persistent task timing.")

    def _load_task_last_run_times(self) -> Dict[str, datetime]:
        loaded_times: Dict[str, datetime] = {}
        if self.task_last_run_times_file_path.is_file():
            try:
                with open(self.task_last_run_times_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for task_name, ts_str in data.items():
                    try:
                        # Ensure timestamps are timezone-aware (UTC) if they are naive
                        dt_obj = datetime.fromisoformat(ts_str)
                        if dt_obj.tzinfo is None:
                            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
                        loaded_times[task_name] = dt_obj
                    except ValueError:
                        logger.warning(f"Invalid timestamp for task '{task_name}': {ts_str}")
                logger.info(f"Loaded task last run times from {self.task_last_run_times_file_path}")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading task times: {e}", exc_info=True)
        else:
            logger.info(f"Task last run times file not found at {self.task_last_run_times_file_path}. Tasks will run based on defaults.")
        return loaded_times

    def _save_task_last_run_time(self, task_name: str, timestamp: datetime):
        # Ensure timestamp is UTC and naive for ISO format consistency if desired, or store with tz
        if timestamp.tzinfo is None:
            aware_timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            aware_timestamp = timestamp.astimezone(timezone.utc)
        
        self._task_last_run_times_cache[task_name] = aware_timestamp
        try:
            self.task_last_run_times_file_path.parent.mkdir(parents=True, exist_ok=True)
            data_to_save = {name: dt.isoformat() for name, dt in self._task_last_run_times_cache.items()}
            with open(self.task_last_run_times_file_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4)
            logger.debug(f"Saved last run time for '{task_name}' ({aware_timestamp.isoformat()})")
        except (IOError, TypeError) as e:
            logger.error(f"Failed to save task times: {e}", exc_info=True)

    def _get_initial_last_run_time(self, task_name: str, interval_seconds: float, current_time_utc: datetime) -> datetime:
        if task_name in self._task_last_run_times_cache:
            # Ensure cached time is UTC aware
            cached_time = self._task_last_run_times_cache[task_name]
            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=timezone.utc)
            logger.debug(f"Using persisted last run time for '{task_name}': {cached_time.isoformat()}")
            return cached_time
        else:
            splay_offset = random.uniform(0, interval_seconds * 0.1) if interval_seconds > 0 else 0
            default_last_run = current_time_utc - timedelta(seconds=max(interval_seconds + 60.0 - splay_offset, 60.0))
            logger.debug(f"No persisted last run time for '{task_name}'. Setting initial to: {default_last_run.isoformat()}")
            return default_last_run

    def set_connection_manager(self, manager: 'ConnectionManager'):
        self.connection_manager = manager

    def set_pathos_interface(self, pathos_interface: 'PathosInterface'):
        self.pathos_interface = pathos_interface

    def set_logos_core(self, logos_core_instance: 'LogosCore'):
        self.logos_core = logos_core_instance

    def set_chronos_engine(self, chronos_engine_instance: 'ChronosEngine'):
        self.chronos_engine = chronos_engine_instance

    async def close(self):
        logger.info("EthosCore close called. Saving Hexus scores and closing memory connection.")
        self._save_hexus_scores()
        if self.memory_storage:
            self.memory_storage.close_connection()
        logger.info("EthosCore resources released.")

    def _load_persona_from_file(self) -> List[str]:
        logger.info(f"Loading persona directives from: {PERSONA_FILE_PATH}")
        default_content = load_system_prompt("pathos_directives", "Default persona: You are Pathos, a 26-year-old human.")
        try:
            if not PERSONA_FILE_PATH.is_file():
                logger.warning(f"Persona file not found at {PERSONA_FILE_PATH}. Creating with default content.")
                PERSONA_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(PERSONA_FILE_PATH, 'w', encoding='utf-8') as f:
                    f.write(default_content)
                return [line.strip() for line in default_content.splitlines() if line.strip() and not line.strip().startswith('#')]
            
            persona_text = PERSONA_FILE_PATH.read_text(encoding='utf-8')
            if not persona_text.strip():
                logger.warning(f"Persona file {PERSONA_FILE_PATH} is empty. Using default content.")
                return [line.strip() for line in default_content.splitlines() if line.strip() and not line.strip().startswith('#')]
            
            directives = [line.strip() for line in persona_text.splitlines() if line.strip() and not line.strip().startswith('#')]
            logger.info(f"Successfully loaded {len(directives)} persona directives.")
            return directives
        except Exception as e:
            logger.error(f"Error loading persona file {PERSONA_FILE_PATH}: {e}", exc_info=True)
            logger.warning("Using default persona content due to error.")
            return [line.strip() for line in default_content.splitlines() if line.strip() and not line.strip().startswith('#')]

    def _load_hexus_scores(self) -> Dict[str, float]:
        defaults = DEFAULT_HEXUS_SCORES.copy()
        if self.hexus_state_file_path.is_file():
            try:
                with open(self.hexus_state_file_path, 'r', encoding='utf-8') as f:
                    loaded_scores = json.load(f)
                
                if isinstance(loaded_scores, dict):
                    final_scores = defaults.copy()
                    for key, default_val in defaults.items():
                        if key in loaded_scores and isinstance(loaded_scores[key], (int, float)):
                            final_scores[key] = float(loaded_scores[key])
                        elif key in loaded_scores:
                            logger.warning(f"Hexus score for '{key}' has invalid type '{type(loaded_scores[key])}' in state file. Using default.")
                    logger.info(f"Successfully loaded and validated Hexus scores from {self.hexus_state_file_path}")
                    return final_scores
                else:
                    logger.warning(f"Hexus state file {self.hexus_state_file_path} content is not a dictionary. Using defaults.")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading Hexus state: {e}. Using defaults.", exc_info=True)
        else:
            logger.info(f"Hexus state file not found at {self.hexus_state_file_path}. Using default scores and creating file.")
        
        try:
            self._save_hexus_scores(defaults)
        except Exception as e_save:
            logger.error(f"Failed to save initial Hexus scores: {e_save}", exc_info=True)
        return defaults

    def _save_hexus_scores(self, scores_to_save: Optional[Dict[str, float]] = None):
        scores = scores_to_save if scores_to_save is not None else self.hexus_scores
        try:
            self.hexus_state_file_path.parent.mkdir(parents=True, exist_ok=True)
            final_scores_to_save = DEFAULT_HEXUS_SCORES.copy()
            final_scores_to_save.update({k: float(v) for k, v in scores.items() if k in DEFAULT_HEXUS_SCORES})

            with open(self.hexus_state_file_path, 'w', encoding='utf-8') as f:
                json.dump(final_scores_to_save, f, indent=4)
            logger.info(f"Hexus scores saved to {self.hexus_state_file_path}")
        except (IOError, TypeError) as e:
            logger.error(f"Failed to save Hexus scores: {e}", exc_info=True)

    async def add_memory_entry(self, entry_data: Dict, user_id_context: Optional[str] = None) -> MemoryEntry:
        if 'content' not in entry_data or 'type' not in entry_data:
            raise ValueError("Memory entry must contain 'content' and 'type'")

        entry_type = str(entry_data['type'])
        # Start with a fresh metadata dict or a copy from entry_data
        metadata: Dict[str, Any] = entry_data.get('metadata', {}).copy()

        # Determine the effective user_id for this memory entry's metadata
        effective_user_id_for_metadata: Optional[str] = metadata.get('user_id')

        if user_id_context is not None:
            # If user_id_context is a "real" user (not system/guest)
            if user_id_context not in self.system_user_ids:
                # And current metadata user_id is system/guest, or None, or different from context, then update it.
                if effective_user_id_for_metadata is None or \
                   effective_user_id_for_metadata in self.system_user_ids or \
                   effective_user_id_for_metadata != user_id_context:
                    effective_user_id_for_metadata = user_id_context
            # Else if user_id_context is a system/guest user, only apply it if metadata has no user_id yet
            elif effective_user_id_for_metadata is None:
                effective_user_id_for_metadata = user_id_context
        
        # If after all checks, we have an effective_user_id, ensure it's in metadata
        if effective_user_id_for_metadata is not None:
            metadata['user_id'] = effective_user_id_for_metadata
        # Optional: If still no user_id, and it's not a type that can be anonymous, log or assign a default
        elif 'user_id' not in metadata and entry_type not in ['world_knowledge', 'system_reflection', 'dream']:
            logger.warning(f"Memory entry of type '{entry_type}' has no user_id after context processing. Content: {str(entry_data.get('content',''))[:50]}...")
            # metadata['user_id'] = "unknown_context_ethos" # Or handle as error if user_id is strictly required

        entry_data['metadata'] = metadata # Assign the processed metadata back to entry_data for MemoryStorage

        # Handle upsert logic for user_facts
        if entry_type == 'user_fact':
            fact_owner_user_id = metadata.get('user_id') 
            fact_attribute_key = metadata.get('fact_attribute_key')

            if fact_owner_user_id and fact_owner_user_id not in self.system_user_ids and fact_attribute_key:
                target_user_id_for_upsert = fact_owner_user_id 
                attribute_key_for_upsert = fact_attribute_key
                
                new_content_str = str(entry_data['content'])
                new_value_parsed = None
                try:
                    new_content_data = json.loads(new_content_str)
                    new_value_parsed = new_content_data.get('value')
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse new user_fact content as JSON: {new_content_str[:100]}...")
                
                existing_fact_entry = await self.get_user_fact(attribute_key_for_upsert, target_user_id_for_upsert)
                
                if existing_fact_entry:
                    try:
                        existing_content_data = json.loads(existing_fact_entry['content'])
                        existing_value = existing_content_data.get('value')
                        
                        if new_value_parsed is not None and new_value_parsed != existing_value:
                            logger.info(f"Updating existing user_fact '{attribute_key_for_upsert}' for user '{target_user_id_for_upsert}'. Old: '{existing_value}', New: '{new_value_parsed}'.")
                            updated_data_payload = {
                                'content': new_content_str,
                                'timestamp': entry_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                                'metadata': metadata, # Use the already processed metadata
                                'salience': entry_data.get('salience', 1.5)
                            }
                            # Update the entry in the database
                            self.memory_storage.update_entry(existing_fact_entry['id'], updated_data_payload)
                            
                            # Construct the full entry object to return
                            updated_entry_dict = existing_fact_entry.copy() # Start with existing
                            updated_entry_dict.update(updated_data_payload) # Apply updates
                            if self.memory_storage.embedder: # Re-embed if content changed
                                max_len = self.ethos_config.get('embedding_max_text_length', 2560)
                                updated_entry_dict['embedding'] = self.memory_storage.embedder.encode(new_content_str[:max_len]).tolist()
                            return MemoryEntry(**updated_entry_dict) # type: ignore
                        else:
                            logger.debug(f"User_fact '{attribute_key_for_upsert}' for user '{target_user_id_for_upsert}' already exists with the same value. Not updating.")
                            return existing_fact_entry # Return the existing entry
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse existing user_fact content as JSON: {existing_fact_entry['content'][:100]}... Will proceed to add as new if ID is different, or rely on MemoryStorage.add_entry's upsert.")
                        # Fall through to MemoryStorage.add_entry which handles INSERT OR REPLACE
        
        # If not a user_fact that was updated, or if it's a new user_fact, proceed to normal add
        # MemoryStorage.add_entry itself handles INSERT OR REPLACE based on primary key (id)
        return self.memory_storage.add_entry(entry_data)

    async def get_todays_briefing(self) -> Optional[str]:
        """
        Retrieves the content of the daily briefing for the current UTC date, if one exists.
        """
        today_date_utc_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        logger.debug(f"EthosCore: Attempting to retrieve briefing for UTC date: {today_date_utc_str}")
        try:
            conn = self.memory_storage._get_connection()
            cursor = conn.cursor()
            
            # We need to query based on the date part of the timestamp.
            # SQLite's date() function works on ISO8601 strings.
            sql = """
                SELECT content FROM memories 
                WHERE type = 'daily_briefing' 
                AND date(timestamp) = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            """
            cursor.execute(sql, (today_date_utc_str,))
            row = cursor.fetchone()
            
            if row:
                logger.info(f"Found existing daily briefing for UTC date: {today_date_utc_str}.")
                return str(row['content'])
            
            logger.info(f"No existing daily briefing found in memory for UTC date: {today_date_utc_str}.")
            return None
        except Exception as e:
            logger.error(f"Error retrieving today's briefing from memory: {e}", exc_info=True)
            return None
    
    async def get_local_datetime_for_user(self, user_id: str, location_override: Optional[str] = None) -> datetime:
        if user_id == PATHOS_USER_ID:
            pathos_home_tz_str = self.ethos_config.get('pathos_home_timezone', "UTC")
            if ZoneInfo and pathos_home_tz_str and pathos_home_tz_str.lower() != 'utc':
                try:
                    return datetime.now(ZoneInfo(pathos_home_tz_str))
                except Exception as e_tz:
                    logger.warning(f"Could not resolve Pathos home timezone '{pathos_home_tz_str}': {e_tz}. Defaulting to UTC.")
                    return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)

        if not user_id or user_id in self.system_user_ids:
            return datetime.now(timezone.utc)

        iana_timezone_str: Optional[str] = None
        
        # Try to get IANA timezone directly if stored
        if derived_tz_fact := await self.get_user_fact('derived_iana_timezone', user_id): # Ensure get_user_fact is async
            if content_str := derived_tz_fact.get('content'):
                try:
                    content_data = json.loads(content_str)
                    iana_timezone_str = content_data.get('value')
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse 'derived_iana_timezone' content for user '{user_id}'.")

        # If not found, try to use preferred_location
        if not iana_timezone_str:
            location_input_str = location_override
            if not location_input_str:
                if location_fact := await self.get_user_fact('preferred_location', user_id): # Ensure get_user_fact is async
                    if content_str := location_fact.get('content'):
                        try:
                            content_data = json.loads(content_str)
                            location_input_str = content_data.get('value')
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse 'preferred_location' content for user '{user_id}'.")
            
            if location_input_str:
                # This is a simplification. A robust solution would use a geocoding service
                # to get IANA timezone from a location string. For now, we assume if a location
                # string is provided, it *might* be an IANA timezone string itself.
                iana_timezone_str = location_input_str 

        if iana_timezone_str and ZoneInfo:
            try:
                return datetime.now(ZoneInfo(iana_timezone_str))
            except Exception as e:
                logger.warning(f"Could not resolve timezone string '{iana_timezone_str}' for user '{user_id}' (Error: {e}). Falling back to UTC.")
        elif not ZoneInfo and iana_timezone_str: # Log only if we had a string but no ZoneInfo
            logger.warning("ZoneInfo module not available (pip install tzdata). Falling back to UTC for user time.")
        
        return datetime.now(timezone.utc)
    
    def update_mood_on_interaction(self, user_input_text: str, pathos_response_text: Optional[str], image_provided: bool, document_provided: bool):
        if not self.config.ENABLE_MOOD_SIMULATION:
            return
        
        try:
            valence_shift, arousal_shift = 0.0, 0.0
            
            # Base shift for successful interaction (assuming if this is called, interaction was somewhat successful)
            valence_shift += MOOD_SHIFT_VALENCE_SUCCESS
            arousal_shift += MOOD_SHIFT_AROUSAL_SUCCESS

            if image_provided:
                valence_shift += 0.05  # Slightly more positive for engaging with an image
                arousal_shift += 0.02
            if document_provided:
                valence_shift += 0.03
                arousal_shift += 0.01
            
            input_lower = (user_input_text or "").lower()
            # More nuanced keyword lists
            positive_keywords = ['thank', 'thanks', 'good', 'great', 'awesome', 'helpful', 'nice', 'love', 'like', 'excellent', 'perfect', 'wonderful', 'amazing', 'fantastic', 'cool', 'brilliant']
            negative_keywords = ['bad', 'wrong', 'terrible', 'awful', 'hate', 'dislike', 'stupid', 'useless', 'annoying', 'incorrect', 'fail', 'sucks', 'not good']
            question_keywords = ['?', 'what', 'who', 'where', 'when', 'why', 'how', 'explain', 'tell me']


            if any(kw in input_lower for kw in positive_keywords):
                valence_shift += MOOD_SHIFT_VALENCE_FEEDBACK_POSITIVE
                arousal_shift += MOOD_SHIFT_AROUSAL_FEEDBACK_POSITIVE
            
            if any(kw in input_lower for kw in negative_keywords):
                valence_shift += MOOD_SHIFT_VALENCE_FEEDBACK_NEGATIVE # This is additive, so a negative value
                arousal_shift += MOOD_SHIFT_AROUSAL_FEEDBACK_NEGATIVE
            
            if any(kw in input_lower for kw in question_keywords) or (user_input_text and user_input_text.strip().endswith('?')):
                arousal_shift += 0.03 # Questions increase arousal
                valence_shift += 0.01 # Mildly positive due to engagement

            # Update current_mood (ensure it's clamped)
            self.current_mood['valence'] = max(MOOD_MIN, min(MOOD_MAX, self.current_mood.get('valence', MOOD_VALENCE_BASELINE) + valence_shift))
            self.current_mood['arousal'] = max(MOOD_MIN, min(MOOD_MAX, self.current_mood.get('arousal', MOOD_AROUSAL_BASELINE) + arousal_shift))
            
            self.last_mood_update_time = datetime.now(timezone.utc) # Update timestamp
            
            logger.debug(f"Mood updated after interaction: V={self.current_mood['valence']:.3f}, A={self.current_mood['arousal']:.3f} (Shifts: v={valence_shift:+.3f}, a={arousal_shift:+.3f})")

        except Exception as e:
            logger.error(f"Error updating mood on interaction: {e}", exc_info=True)    
    
    async def get_recent_dreams(self, user_id_context: Optional[str], limit: int) -> List[MemoryEntry]:
        dream_type = "queued_discussion_point" # Dreams are stored as queued points
        dream_source_filter = "oneiros_dream_cycle" # Filter by source metadata
        
        logger.debug(f"EthosCore: Fetching recent dreams. User context: {user_id_context}, Limit: {limit}")
        try:
            conn = self.memory_storage._get_connection()
            cursor = conn.cursor()
            
            can_use_json_extract = True
            try:
                cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')")
                result = cursor.fetchone()
                if result is None or result[0] != 'value':
                    can_use_json_extract = False
            except sqlite3.OperationalError as oe_test:
                if "no such function: json_extract" in str(oe_test).lower():
                    can_use_json_extract = False
                else:
                    logger.error(f"Unexpected SQLite error checking json_extract for get_recent_dreams: {oe_test}", exc_info=True)
                    can_use_json_extract = False # Safer assumption
            except Exception as e_test_other:
                 logger.error(f"General error checking json_extract for get_recent_dreams: {e_test_other}", exc_info=True)
                 can_use_json_extract = False


            sql_query = f"SELECT * FROM memories WHERE type = ?"
            params: List[Any] = [dream_type]

            if can_use_json_extract:
                sql_query += f" AND json_extract(metadata, '$.source') = ?"
                params.append(dream_source_filter)
                
                # Filter by user_id_context if provided and not a system-wide request
                # A dream belongs to a user if its metadata.user_id matches, OR if it's a system_oneiros dream (global)
                if user_id_context and user_id_context not in self.system_user_ids:
                    sql_query += " AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') = 'system_oneiros')"
                    params.extend([user_id_context]) # Only user_id_context here, system_oneiros is already in the OR
                elif user_id_context in ["system_oneiros", None] or (user_id_context and user_id_context in self.system_user_ids):
                    # If system context, or no specific user context, or a generic system user, fetch only 'system_oneiros' dreams
                    sql_query += " AND json_extract(metadata, '$.user_id') = 'system_oneiros'"
            
            sql_query += " ORDER BY timestamp DESC LIMIT ?"
            # Fetch more if filtering in Python is needed due to lack of json_extract
            fetch_limit = limit * 5 if not can_use_json_extract else limit 
            params.append(fetch_limit)

            cursor.execute(sql_query, tuple(params))
            rows = cursor.fetchall()
            
            dreams: List[MemoryEntry] = []
            for row_data in rows:
                entry = self.memory_storage._row_to_entry(row_data)
                meta = entry.get('metadata', {})
                
                if not can_use_json_extract: # Python-side filtering if json_extract was not used
                    if meta.get('source') != dream_source_filter:
                        continue
                    entry_uid = meta.get('user_id')
                    if user_id_context and user_id_context not in self.system_user_ids:
                        if not (entry_uid == user_id_context or entry_uid == "system_oneiros"):
                            continue
                    elif user_id_context in ["system_oneiros", None] or (user_id_context and user_id_context in self.system_user_ids):
                        if entry_uid != "system_oneiros":
                            continue
                
                dreams.append(entry)
            
            # If Python filtering was done, re-sort and limit (SQL sort is primary if json_extract used)
            if not can_use_json_extract:
                dreams.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            final_dreams = dreams[:limit]
            logger.info(f"Retrieved {len(final_dreams)} recent dreams (user_context: {user_id_context}, limit: {limit}).")
            return final_dreams
        except Exception as e:
            logger.error(f"Error retrieving recent dreams: {e}", exc_info=True)
            return []
    
    def get_hexus_scores(self) -> Dict[str, float]:
        """Returns a copy of the current Hexus scores."""
        return self.hexus_scores.copy()
    
    async def retrieve_relevant_memories(self, query: str, top_k: int = 5, min_salience: float = 0.1, allowed_types: Optional[List[str]] = None, user_id_context: Optional[str] = None) -> List[MemoryEntry]:
        if not query.strip() and not allowed_types:
            return []
        try:
            min_salience = float(min_salience) # Ensure it's float
            # Fetch more candidates initially for better filtering and sorting
            similar_results = self.memory_storage.find_similar(query, top_k * 5, allowed_types, 0.3) # threshold 0.3 is example
            
            all_candidates = [entry for _, entry in similar_results]
            
            # Filter by user_id_context if provided
            if user_id_context and user_id_context not in ["default_user"] + self.system_user_ids:
                user_specific_candidates = []
                other_candidates = []
                for entry in all_candidates:
                    entry_uid = entry.get('metadata', {}).get('user_id')
                    if entry_uid == user_id_context or entry_uid in self.system_user_ids or entry_uid == PATHOS_USER_ID:
                        user_specific_candidates.append(entry)
                    else:
                        other_candidates.append(entry)
                # Prioritize user-specific and system/Pathos memories
                combined_candidates = user_specific_candidates + other_candidates
            else: # If no specific user context, or system context, consider all
                combined_candidates = all_candidates

            # Filter by salience
            filtered_by_salience = [e for e in combined_candidates if (e.get('salience') is not None and float(e['salience']) >= min_salience)]

            # Define sort key for prioritization
            def sort_key_func(entry: MemoryEntry):
                entry_type = entry.get('type')
                entry_uid = entry.get('metadata', {}).get('user_id')
                priority_score = 0
                
                if entry_type == 'user_fact' and entry_uid == user_id_context: priority_score = 8
                elif entry_type == 'aspiration' and entry_uid == PATHOS_USER_ID: priority_score = 7
                elif entry_type in ['learned_correction', 'learned_feedback_insight', 'suggestion_reflection']: priority_score = 6
                elif entry_type == 'feedback': priority_score = 5
                elif entry_type == 'context_summary' and (entry_uid == user_id_context or entry_uid in ["system_oneiros", "system_reflection", PATHOS_USER_ID]): priority_score = 4
                elif entry_type == 'world_knowledge': priority_score = 3
                elif entry_type == 'document_chunk': priority_score = 2
                elif entry_uid == user_id_context and entry_type != 'user_fact': priority_score = 1
                
                # Ensure salience is float for sorting, default to 0 if None or invalid
                salience_val = 0.0
                try: salience_val = float(entry.get('salience', 0.0)) if entry.get('salience') is not None else 0.0
                except (ValueError, TypeError): pass

                return (priority_score, salience_val, entry.get('timestamp', ''))

            # Sort and take top_k
            final_results = sorted(filtered_by_salience, key=sort_key_func, reverse=True)[:top_k]
            logger.debug(f"Retrieved {len(final_results)} relevant memories for query '{query[:50]}...' (user: {user_id_context})")
            return final_results
            
        except Exception as e:
            logger.error(f"Error retrieving relevant memories: {e}", exc_info=True)
            return []

    async def get_user_fact(self, attribute_key: str, user_id: str) -> Optional[MemoryEntry]:
        normalized_key = attribute_key.lower().replace(" ", "_").strip()
        if not user_id or user_id in self.system_user_ids or not normalized_key:
            return None
        
        try:
            conn = self.memory_storage._get_connection()
            cursor = conn.cursor()
            
            can_use_json_extract = True
            try: cursor.execute("SELECT json_extract('{\"k\":\"v\"}', '$.k')")
            except sqlite3.OperationalError: can_use_json_extract = False

            if can_use_json_extract:
                sql = "SELECT * FROM memories WHERE type = 'user_fact' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.fact_attribute_key') = ? ORDER BY timestamp DESC LIMIT 1"
                cursor.execute(sql, (user_id, normalized_key))
                row = cursor.fetchone()
                if row:
                    return self.memory_storage._row_to_entry(row)
            else:
                logger.warning("json_extract not available. Falling back for get_user_fact. This may be slow.")
                cursor.execute("SELECT * FROM memories WHERE type = 'user_fact' ORDER BY timestamp DESC")
                for r_row_data in cursor.fetchall():
                    r_row = dict(r_row_data) # Convert sqlite3.Row to dict
                    entry = self.memory_storage._row_to_entry(r_row)
                    meta = entry.get('metadata', {})
                    if meta.get('user_id') == user_id and meta.get('fact_attribute_key') == normalized_key:
                        return entry
            return None
        except Exception as e:
            logger.error(f"Error in get_user_fact (key: {attribute_key}, user: {user_id}): {e}", exc_info=True)
            return None

    async def add_document_chunks(self, doc_id: str, filename: str, chunks: List[str]):
        if not chunks:
            return
        user_id_ctx = "system_document" # Or derive from context if available
        for i, chunk_text in enumerate(chunks):
            if not chunk_text or not chunk_text.strip():
                continue
            await self.add_memory_entry(
                entry_data={
                    "type": "document_chunk",
                    "content": chunk_text,
                    "id": f"{doc_id}_chunk_{i}", # Ensure unique ID for each chunk
                    "metadata": {
                        "source_document_id": doc_id,
                        "source_document_name": filename,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "user_id": user_id_ctx # Associate with system or a specific user context
                    },
                    "salience": 0.4 # Default salience for document chunks
                },
                user_id_context=user_id_ctx
            )

    async def _call_llm_for_internal_task(self, messages: List[Dict[str, Any]], llm_role_to_use: str) -> Optional[str]:
        llm_config = self.config.get_llm_config(llm_role_to_use)
        if not llm_config or not llm_config.get('url'):
            logger.error(f"LLM URL for role '{llm_role_to_use}' not configured.")
            return f"[LLM URL for role '{llm_role_to_use}' not configured]"

        api_url = f"{llm_config['url'].rstrip('/')}/chat/completions"
        response_obj = None # To store response for logging in case of JSONDecodeError

        try:
            timeout_seconds = float(llm_config.get('timeout', 120.0))
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                headers = {"Content-Type": "application/json"}
                if api_key := llm_config.get('api_key'):
                    if api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']:
                        headers["Authorization"] = f"Bearer {api_key}"
                
                # Determine max_tokens: if "summarize" is in the first message content, use a larger default.
                default_max_tokens = 512
                if messages and isinstance(messages[0].get("content"), str) and "summarize" in messages[0].get("content","").lower():
                    default_max_tokens = 1024 
                
                max_tokens_val = int(llm_config.get('max_tokens', default_max_tokens))
                
                payload: Dict[str, Any] = {
                    "model": llm_config.get('model'),
                    "messages": messages,
                    "temperature": float(llm_config.get('temperature', 0.3)), # Ensure float
                    "max_tokens": max_tokens_val
                }
                for param in ['top_p', 'presence_penalty', 'frequency_penalty']:
                    if param_val := llm_config.get(param):
                        payload[param] = float(param_val) # Ensure float
                
                if not payload.get('model'): # If model is None or empty string
                    logger.warning(f"LLM call for role '{llm_role_to_use}' has no model specified. Provider might use default or fail.")
                    if 'model' in payload: del payload['model'] # Remove if empty, some servers might infer

                response_obj = await client.post(api_url, headers=headers, json=payload)
                response_obj.raise_for_status()
                result_json = response_obj.json()
                
                if choices := result_json.get("choices"):
                    if choices and isinstance(choices, list) and len(choices) > 0:
                        if message := choices[0].get("message"):
                            if content := message.get("content"):
                                if isinstance(content, str):
                                    return content.strip()
                logger.warning(f"Unexpected LLM response format from {llm_config.get('model', llm_role_to_use)}: {result_json}")
                return f"[Unexpected LLM response format from {llm_config.get('model', llm_role_to_use)}]"
        except httpx.TimeoutException as e:
            logger.error(f"Timeout connecting to LLM '{llm_config.get('model', llm_role_to_use)}': {e}")
            return f"[Timeout connecting to LLM '{llm_config.get('model', llm_role_to_use)}': {e}]"
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to LLM '{llm_config.get('model', llm_role_to_use)}': {e}")
            return f"[Failed to connect to LLM '{llm_config.get('model', llm_role_to_use)}': {e}]"
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM '{llm_config.get('model', llm_role_to_use)}' API error ({e.response.status_code}): {e.response.text[:200]}")
            return f"[LLM '{llm_config.get('model', llm_role_to_use)}' API error ({e.response.status_code})]"
        except json.JSONDecodeError as e_json:
            response_text_for_log = response_obj.text[:500] if response_obj and hasattr(response_obj, 'text') else 'N/A'
            logger.error(f"Invalid JSON from LLM '{llm_config.get('model', llm_role_to_use)}': {e_json}. Response: {response_text_for_log}")
            return f"[Invalid JSON from LLM '{llm_config.get('model', llm_role_to_use)}']"
        except Exception as e_gen:
            logger.error(f"Failed to process response from LLM '{llm_config.get('model', llm_role_to_use)}': {e_gen}", exc_info=True)
            return f"[Failed to process response from LLM '{llm_config.get('model', llm_role_to_use)}': {e_gen}]"

    # ... (rest of the EthosCore methods: _run_memory_summarization, get_recent_dreams, etc.)
    # Ensure all methods from the "broken" file that are still relevant are included and corrected.

    async def get_last_proactive_action_time(self, user_id: str, action_type: str) -> Optional[datetime]:
        if not user_id or not action_type: return None
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        can_use_json_extract = True
        try:
            cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')"); result = cursor.fetchone()
            if result is None or result[0] != 'value': can_use_json_extract = False
        except sqlite3.OperationalError as oe_test:
            if "no such function: json_extract" in str(oe_test).lower(): can_use_json_extract = False
            else: logger.error(f"Unexpected SQLite error checking json_extract: {oe_test}", exc_info=True); can_use_json_extract = False
        except Exception as e_test_other: logger.error(f"General error checking json_extract: {e_test_other}", exc_info=True); can_use_json_extract = False
        
        sql_query, params_list = "", [] # Renamed params to params_list to avoid conflict
        if can_use_json_extract:
            sql_query = "SELECT timestamp FROM memories WHERE type = 'proactive_action_record' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.action_type') = ? ORDER BY timestamp DESC LIMIT 1"
            params_list = [user_id, action_type]
        else:
            logger.warning(f"json_extract not available for get_last_proactive_action_time (user: {user_id}, action: {action_type}).")
            sql_query = "SELECT timestamp, metadata FROM memories WHERE type = 'proactive_action_record' ORDER BY timestamp DESC LIMIT 100" 
        try:
            cursor.execute(sql_query, tuple(params_list)) # Use params_list
            if not can_use_json_extract:
                for row_data_raw in cursor.fetchall():
                    row_dict = dict(row_data_raw); metadata_str = row_dict.get('metadata')
                    if metadata_str and isinstance(metadata_str, str):
                        try:
                            metadata = json.loads(metadata_str)
                            if isinstance(metadata, dict) and metadata.get('user_id') == user_id and metadata.get('action_type') == action_type:
                                if ts_str := row_dict.get('timestamp'): return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        except (json.JSONDecodeError, ValueError, TypeError): continue
                return None
            else:
                if row := cursor.fetchone():
                    if ts_str := row['timestamp']: return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                return None
        except Exception as e: logger.error(f"Error retrieving last proactive action time for user '{user_id}', action '{action_type}': {e}", exc_info=True); return None


    async def get_todays_briefing_context_for_prompt(self, user_id: str) -> str:
        try:
            if not self.logos_core: return "Briefing service unavailable (LogosCore missing)."
            briefing_data = await self.logos_core.get_or_generate_daily_briefing(user_id_context=user_id) 
            if briefing_data and briefing_data.get('success') and briefing_data.get('briefing_content'):
                content = str(briefing_data['briefing_content'])
                max_len = self.ethos_config.get('briefing_context_max_length_for_prompt', 1500)
                return f"Today's Briefing Highlights (Pathos's context, shared with user '{user_id}'):\n{content[:max_len] + '...' if len(content) > max_len else content}"
            return "No briefing available for Pathos today."
        except Exception as e: logger.error(f"Error getting briefing context for prompt: {e}", exc_info=True); return "Briefing information temporarily unavailable (error)"    
    
    async def get_pathos_aspirations_context_for_prompt(self) -> str:
        try:
            max_items = self.ethos_config.get('aspiration_context_max_items_for_prompt', 5)
            aspirations = await self.memory_storage.get_entries_by_type_and_user("aspiration", PATHOS_USER_ID, max_items)
            if not aspirations: return "Pathos has no current aspirations defined."
            lines = ["Pathos's Current Aspirations:"]
            for entry in aspirations:
                if content_str := entry.get('content'):
                    try:
                        content_data = json.loads(content_str)
                        title = content_data.get('title', str(content_data)) if isinstance(content_data, dict) else str(content_data)
                        status = content_data.get('status', 'unknown')
                        lines.append(f"- {title} (Status: {status})")
                    except json.JSONDecodeError: lines.append(f"- {content_str[:100]}...")
            return "\n".join(lines)
        except Exception as e: logger.error(f"Error getting Pathos aspirations context: {e}", exc_info=True); return "Aspirations information for Pathos is temporarily unavailable (error)"    
    
    async def get_pathos_schedule_context_for_prompt(self) -> str:
        try:
            if not self.chronos_engine:
                logger.warning("EthosCore.get_pathos_schedule_context_for_prompt: ChronosEngine not available.")
                return "Schedule information for Pathos is temporarily unavailable (system component missing)."
            schedule: List['ActivitySlot'] = await self.chronos_engine.get_todays_schedule_for_user() 
            if not schedule: return "Pathos has no scheduled activities for today."
            lines = ["Pathos's Schedule for Today:"]
            max_items = self.ethos_config.get('schedule_context_max_items_for_prompt', 5)
            desc_snippet_len = self.ethos_config.get('schedule_context_desc_snippet_len', 50)
            for activity in schedule[:max_items]:
                time_str = f"{activity.start_time.strftime('%H:%M')}-{activity.end_time.strftime('%H:%M')}"
                line = f"- {time_str}: {activity.activity_title}"
                if activity.activity_details and activity.activity_details.description:
                    desc_snippet = activity.activity_details.description[:desc_snippet_len]
                    line += f" (Focus: {desc_snippet}{'...' if len(activity.activity_details.description) > desc_snippet_len else ''})"
                lines.append(line)
            if len(schedule) > max_items: lines.append(f"- ...and {len(schedule) - max_items} more activities.")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error getting Pathos schedule context for prompt: {e}", exc_info=True)
            return "Schedule information for Pathos is temporarily unavailable (error)"    
    
    async def get_user_profile_summary(self, user_id: str) -> str:
        if not user_id or user_id in self.system_user_ids:
            return "No specific profile information available for this user yet."
        facts = await self.get_all_user_facts(user_id)
        if not facts: return "No specific profile information available for this user yet."
        parts = []
        for fact_entry in facts[:5]: 
            try:
                content_str = fact_entry.get('content')
                if content_str and isinstance(content_str, str):
                    content_data = json.loads(content_str)
                    attribute_name = content_data.get('attribute', 'unknown_attribute')
                    attribute_value = content_data.get('value', 'unknown_value')
                    display_key = attribute_name.replace('_', ' ').title()
                    display_value = str(attribute_value)
                    if len(display_value) > 70: display_value = display_value[:67] + "..."
                    if display_key.lower() == 'name': parts.insert(0, f"Name: {display_value}")
                    elif display_key.lower() == 'preferred location': parts.append(f"Location: {display_value}")
                    else: parts.append(f"{display_key}: {display_value}")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Could not parse user fact for profile summary (user: {user_id}, fact_id: {fact_entry.get('id')}): {e}")
                continue
        if not parts: return "No specific profile information available for this user yet."
        return f"User profile for '{user_id}': {'; '.join(parts)}."    
    
    async def get_all_user_facts(self, user_id: str) -> List[MemoryEntry]:
        if not user_id or user_id in self.system_user_ids:
            logger.debug(f"get_all_user_facts called for system/invalid user '{user_id}', returning empty list.")
            return []
        
        logger.debug(f"EthosCore: Fetching all user facts for user_id: {user_id}")
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        can_use_json_extract = True
        try:
            cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')"); result = cursor.fetchone()
            if result is None or result[0] != 'value': can_use_json_extract = False
        except sqlite3.OperationalError as oe_test:
            if "no such function: json_extract" in str(oe_test).lower(): can_use_json_extract = False
            else: logger.error(f"Unexpected SQLite error checking json_extract: {oe_test}", exc_info=True); can_use_json_extract = False
        except Exception as e_test_other: logger.error(f"General error checking json_extract: {e_test_other}", exc_info=True); can_use_json_extract = False

        facts_entries: List[MemoryEntry] = []
        sql_query_str, params_list = "", [] # Renamed params to params_list
        if can_use_json_extract:
            sql_query_str = "SELECT * FROM memories WHERE type = 'user_fact' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.fact_attribute_key') IS NOT NULL ORDER BY timestamp DESC"
            params_list = [user_id]
        else:
            logger.warning(f"json_extract not available for get_all_user_facts (user: {user_id}). This will be less efficient.")
            sql_query_str = "SELECT * FROM memories WHERE type = 'user_fact' ORDER BY timestamp DESC"
            # params_list remains empty
        try:
            cursor.execute(sql_query_str, tuple(params_list)); rows_raw = cursor.fetchall() # Use params_list
            latest_facts_by_attribute: Dict[str, MemoryEntry] = {}
            for row_data_raw in rows_raw:
                entry = self.memory_storage._row_to_entry(dict(row_data_raw))
                metadata = entry.get('metadata', {}); entry_user_id = metadata.get('user_id'); attribute_key = metadata.get('fact_attribute_key')
                if not can_use_json_extract:
                    if entry_user_id != user_id or not attribute_key: continue
                if attribute_key and attribute_key not in latest_facts_by_attribute:
                    latest_facts_by_attribute[attribute_key] = entry
            facts_entries = list(latest_facts_by_attribute.values())
            facts_entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            logger.info(f"Retrieved {len(facts_entries)} unique user facts for user '{user_id}'.")
            return facts_entries
        except Exception as e: logger.error(f"Error retrieving all user facts for user '{user_id}': {e}", exc_info=True); return []
    
    async def get_current_activity_description(self) -> str:
        try:
            if not self.chronos_engine:
                logger.warning("EthosCore.get_current_activity_description: ChronosEngine not available.")
                return "Activity information temporarily unavailable (system component missing)."
            pathos_local_now = await self.get_local_datetime_for_user(PATHOS_USER_ID) 
            current_activity: Optional['ActivitySlot'] = await self.chronos_engine.get_current_activity(pathos_local_now)
            if current_activity:
                desc = f"Currently: {current_activity.activity_title}"
                if current_activity.activity_details and current_activity.activity_details.description:
                    desc += f" - {current_activity.activity_details.description}"
                if current_activity.activity_details and current_activity.activity_details.location_context:
                    desc += f" (Location: {current_activity.activity_details.location_context})"
                return desc
            return "No scheduled activity for Pathos at the moment."
        except Exception as e:
            logger.error(f"Error getting current activity description: {e}", exc_info=True)
            return "Activity information temporarily unavailable (error)"
    
    async def get_queued_discussion_points(self, user_id: str, limit: int = 1) -> List[MemoryEntry]:
        if not user_id: return []
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        can_use_json_extract = True
        try:
            cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')"); result = cursor.fetchone()
            if result is None or result[0] != 'value': can_use_json_extract = False
        except Exception: can_use_json_extract = False
        
        queued_points: List[MemoryEntry] = []; fetch_limit = limit * 2 if limit > 0 else 10
        sql_query_str, params_list = "", [] # Renamed params to params_list
        if can_use_json_extract:
            sql_query_str = "SELECT * FROM memories WHERE type = 'queued_discussion_point' AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') IS NULL) AND (json_extract(metadata, '$.status') IS NULL OR json_extract(metadata, '$.status') = 'pending') ORDER BY salience DESC, timestamp ASC LIMIT ?"
            params_list = [user_id, "system_oneiros", fetch_limit] 
        else:
            logger.warning("json_extract not available for get_queued_discussion_points. Querying all and filtering in Python.")
            sql_query_str = "SELECT * FROM memories WHERE type = 'queued_discussion_point' ORDER BY timestamp DESC LIMIT ?"
            params_list = [fetch_limit * 5] 
        
        cursor.execute(sql_query_str, tuple(params_list)); rows_raw = cursor.fetchall() # Use params_list
        for row_data_raw in rows_raw:
            try:
                entry = self.memory_storage._row_to_entry(dict(row_data_raw)); metadata = entry.get('metadata', {})
                entry_user_id = metadata.get('user_id'); status = metadata.get('status', 'pending')
                if not can_use_json_extract:
                    if status != 'pending': continue
                    if not (entry_user_id == user_id or entry_user_id == "system_oneiros" or entry_user_id is None or entry_user_id == PATHOS_USER_ID): continue
                queued_points.append(entry)
            except Exception as e_entry: logger.error(f"Error processing queued point entry: {e_entry}", exc_info=True)
        
        queued_points.sort(key=lambda x: (-(float(x.get('salience', 0.0)) if x.get('salience') is not None else 0.0), x.get('timestamp', '') or ''), reverse=False)
        final_limit_list = queued_points[:limit] # Renamed final_limit to avoid conflict
        logger.info(f"Retrieved {len(final_limit_list)} queued discussion points for user_id: {user_id} (Limit: {limit}, Fetched before sort/filter: {len(rows_raw)}, After initial filter: {len(queued_points)})")
        return final_limit_list
    
    async def get_all_user_facts(self, user_id: str) -> List[MemoryEntry]:
        if not user_id or user_id in self.system_user_ids:
            logger.debug(f"get_all_user_facts called for system/invalid user '{user_id}', returning empty list.")
            return []
        
        logger.debug(f"EthosCore: Fetching all user facts for user_id: {user_id}")
        conn = self.memory_storage._get_connection()
        cursor = conn.cursor()
        
        can_use_json_extract = True
        try:
            cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')")
            result = cursor.fetchone()
            if result is None or result[0] != 'value': can_use_json_extract = False
        except sqlite3.OperationalError as oe_test:
            if "no such function: json_extract" in str(oe_test).lower(): can_use_json_extract = False
            else: logger.error(f"Unexpected SQLite error checking json_extract: {oe_test}", exc_info=True); can_use_json_extract = False
        except Exception as e_test_other: logger.error(f"General error checking json_extract: {e_test_other}", exc_info=True); can_use_json_extract = False

        facts_entries: List[MemoryEntry] = []
        
        if can_use_json_extract:
            sql_query = """
                SELECT * FROM memories
                WHERE type = 'user_fact'
                  AND json_extract(metadata, '$.user_id') = ?
                  AND json_extract(metadata, '$.fact_attribute_key') IS NOT NULL
                ORDER BY timestamp DESC 
            """ # No LIMIT here, we want all unique facts
            params = (user_id,)
        else:
            logger.warning(f"json_extract not available for get_all_user_facts (user: {user_id}). This will be less efficient.")
            sql_query = "SELECT * FROM memories WHERE type = 'user_fact' ORDER BY timestamp DESC"
            params = ()

        try:
            cursor.execute(sql_query, params)
            rows_raw = cursor.fetchall()
            
            # To get only the latest fact for each attribute key
            latest_facts_by_attribute: Dict[str, MemoryEntry] = {}

            for row_data_raw in rows_raw:
                entry = self.memory_storage._row_to_entry(dict(row_data_raw))
                metadata = entry.get('metadata', {})
                entry_user_id = metadata.get('user_id')
                attribute_key = metadata.get('fact_attribute_key')

                if not can_use_json_extract: # Python-side filtering for user_id
                    if entry_user_id != user_id or not attribute_key:
                        continue
                
                if attribute_key:
                    # If we haven't seen this attribute yet, or if this entry is newer
                    # (SQL already sorts by timestamp DESC, so first encountered is latest)
                    if attribute_key not in latest_facts_by_attribute:
                        latest_facts_by_attribute[attribute_key] = entry
            
            facts_entries = list(latest_facts_by_attribute.values())
            # Optionally re-sort if needed, though SQL order should be fine for latest
            facts_entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

            logger.info(f"Retrieved {len(facts_entries)} unique user facts for user '{user_id}'.")
            return facts_entries
        except Exception as e:
            logger.error(f"Error retrieving all user facts for user '{user_id}': {e}", exc_info=True)
            return []

    async def update_persona_directives(self, new_directives: List[str]):
        self.persona_directives = [d.strip() for d in new_directives if d.strip()]
        try:
            PERSONA_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(PERSONA_FILE_PATH, 'w', encoding='utf-8') as f:
                f.write("\n".join(self.persona_directives))
            logger.info(f"Persona directives updated and saved to {PERSONA_FILE_PATH}.")
        except Exception as e:
            logger.error(f"Failed to save updated persona directives: {e}", exc_info=True)

    async def run_knowledge_upkeep_cycle(self):
        if not self.config.ENABLE_KNOWLEDGE_UPKEEP: return
        interval = self.ethos_config.get('knowledge_upkeep_interval_seconds', 0.0)
        now = datetime.now(timezone.utc)
        if interval <= 0 or now - self.last_knowledge_upkeep_time < timedelta(seconds=interval):
            return
        
        logger.info("--- Ethos: Starting Knowledge Upkeep Cycle ---")
        self.last_knowledge_upkeep_time = now
        self._save_task_last_run_time("KnowledgeUpkeep", now)
        
        volatile_tags_cfg = self.ethos_config.get('knowledge_upkeep_volatile_tags', [])
        if not isinstance(volatile_tags_cfg, list) or not volatile_tags_cfg:
            logger.info("--- Ethos: Knowledge Upkeep Cycle Finished (No volatile tags configured) ---")
            return

        volatile_tags_lower = [str(tag).lower() for tag in volatile_tags_cfg]

        try:
            conn = self.memory_storage._get_connection()
            cursor = conn.cursor()
            # Fetch a limited number of world_knowledge entries to check
            # Prioritize older or less recently verified ones if possible (not easily done with current schema)
            # For now, random sample is okay for MVP.
            cursor.execute("SELECT * FROM memories WHERE type = 'world_knowledge' AND metadata IS NOT NULL ORDER BY RANDOM() LIMIT 50")
            rows = cursor.fetchall()
            
            facts_to_verify: List[MemoryEntry] = []
            for row_data in rows:
                entry = self.memory_storage._row_to_entry(row_data)
                entry_tags_meta = entry.get('metadata', {}).get('topic_tags', [])
                if not isinstance(entry_tags_meta, list): continue # Skip if not a list

                entry_tags_lower = [str(t).lower() for t in entry_tags_meta if isinstance(t, str)]
                
                if any(tag_l in volatile_tags_lower for tag_l in entry_tags_lower):
                    facts_to_verify.append(entry)
                    if len(facts_to_verify) >= self.ethos_config.get('knowledge_upkeep_max_facts_to_verify_per_cycle', 5):
                        break
            
            if not facts_to_verify:
                logger.info("--- Ethos: Knowledge Upkeep Cycle Finished (No facts matching volatile tags found to verify) ---")
                return

            if not self.logos_core:
                logger.error("LogosCore not available for knowledge upkeep.")
                logger.info("--- Ethos: Knowledge Upkeep Cycle Finished (LogosCore missing) ---")
                return

            for fact_entry in facts_to_verify:
                fact_id = fact_entry.get('id')
                logger.info(f"Knowledge Upkeep: Verifying fact ID {fact_id} - '{fact_entry.get('content', '')[:70]}...'")
                verification_result = await self.logos_core.verify_world_fact(fact_entry)
                
                updated_metadata = fact_entry.get('metadata', {}).copy()
                updated_metadata['last_verified_timestamp'] = now.isoformat()
                updated_metadata['verification_reason'] = verification_result.get('reason', 'N/A')
                updated_metadata['status'] = verification_result.get("status", "unknown") # Store status

                if verification_result.get("status") == "updated":
                    new_statement = verification_result.get("new_fact_statement")
                    new_confidence = verification_result.get("confidence", 0.85)
                    if new_statement:
                        new_fact_id = str(uuid.uuid4())
                        await self.add_memory_entry(
                            entry_data={
                                "id": new_fact_id,
                                "type": "world_knowledge",
                                "content": new_statement,
                                "metadata": {
                                    "user_id": "system_knowledge_upkeep", # Or original user if appropriate
                                    "source_description": f"Auto-updated from fact ID {fact_id} during knowledge upkeep.",
                                    "topic_tags": updated_metadata.get('topic_tags', []),
                                    "confidence_level": new_confidence,
                                    "original_fact_id_verified": fact_id,
                                    "last_verified_timestamp": now.isoformat() # Also mark new fact as verified now
                                },
                                "salience": max(0.1, (fact_entry.get('salience') or 0.7) + 0.1) # Slightly boost salience
                            },
                            user_id_context="world_knowledge_store"
                        )
                        updated_metadata['superseded_by_fact_id'] = new_fact_id
                        # Optionally reduce salience of old fact
                        self.memory_storage.update_entry(fact_id, {"metadata": updated_metadata, "salience": max(0.05, (fact_entry.get('salience') or 0.5) * 0.5)})
                        logger.info(f"Fact ID {fact_id} updated. New fact ID: {new_fact_id}. Statement: '{new_statement[:70]}...'")
                    else:
                        logger.warning(f"Fact ID {fact_id} marked as 'updated' but no new statement provided.")
                        updated_metadata['verification_attempt_failed'] = True # Treat as failed if no new statement
                        self.memory_storage.update_entry(fact_id, {"metadata": updated_metadata})

                elif verification_result.get("status") == "accurate":
                    updated_metadata.pop('verification_attempt_failed', None) # Clear previous failure if any
                    self.memory_storage.update_entry(fact_id, {"metadata": updated_metadata})
                    logger.info(f"Fact ID {fact_id} confirmed accurate.")
                
                elif verification_result.get("status") == "unverifiable":
                    updated_metadata['verification_attempt_failed'] = True
                    self.memory_storage.update_entry(fact_id, {"metadata": updated_metadata})
                    logger.info(f"Fact ID {fact_id} remains unverifiable. Reason: {verification_result.get('reason')}")
                else: # Unknown status
                    logger.warning(f"Unknown verification status for fact ID {fact_id}: {verification_result.get('status')}")
                    updated_metadata['verification_attempt_failed'] = True
                    self.memory_storage.update_entry(fact_id, {"metadata": updated_metadata})

                await asyncio.sleep(random.uniform(self.ethos_config.get('knowledge_upkeep_delay_between_verifications_min', 5.0), 
                                                  self.ethos_config.get('knowledge_upkeep_delay_between_verifications_max', 10.0)))
        except Exception as e:
            logger.error(f"Error in Knowledge Upkeep Cycle: {e}", exc_info=True)
        logger.info("--- Ethos: Knowledge Upkeep Cycle Finished ---")

    async def run_interaction_log_analysis(self):
        if not self.ethos_config.get('enable_interaction_log_analysis', False): return
        interval = self.ethos_config.get('interaction_log_analysis_interval_seconds', 0.0)
        now = datetime.now(timezone.utc)
        if interval <= 0 or now - self.last_interaction_log_analysis_time < timedelta(seconds=interval):
            return
        
        logger.info("--- Ethos: Starting Interaction Log Analysis ---")
        self.last_interaction_log_analysis_time = now
        self._save_task_last_run_time("InteractionLogAnalysis", now)
        
        llm_role = self.ethos_config.get('interaction_log_analysis_llm_role', 'LOGOS_TECHNE')
        llm_config = self.config.get_llm_config(llm_role)
        if not llm_config or not llm_config.get('url'):
            logger.error(f"Interaction Log Analysis LLM '{llm_role}' not configured.")
            logger.info("--- Ethos: Interaction Log Analysis Finished (LLM Misconfig) ---")
            return

        batch_size = self.ethos_config.get('interaction_log_analysis_batch_size', 20)
        max_days_lookback = self.ethos_config.get('interaction_log_analysis_max_days_lookback', 7)
        since_ts = (now - timedelta(days=max_days_lookback)).isoformat()

        try:
            conn = self.memory_storage._get_connection()
            cursor = conn.cursor()
            
            can_use_json_extract = True
            try: cursor.execute("SELECT json_extract('{\"k\":\"v\"}', '$.k')")
            except sqlite3.OperationalError: can_use_json_extract = False

            sql_query = ""
            params: List[Any] = []
            if can_use_json_extract:
                sql_query = """
                    SELECT * FROM memories 
                    WHERE type = 'interaction' AND timestamp >= ? 
                      AND (json_extract(metadata, '$.analyzed_for_facts') IS NULL OR json_extract(metadata, '$.analyzed_for_facts') = 0)
                    ORDER BY json_extract(metadata, '$.user_id'), timestamp ASC 
                    LIMIT ?
                """
                params = [since_ts, batch_size * 5] # Fetch more to group by user
            else:
                logger.warning("json_extract not available for interaction log analysis. This will be less efficient.")
                sql_query = "SELECT * FROM memories WHERE type = 'interaction' AND timestamp >= ? ORDER BY timestamp ASC LIMIT ?"
                params = [since_ts, batch_size * 10] # Fetch even more for Python filtering

            cursor.execute(sql_query, tuple(params))
            rows = cursor.fetchall()
            
            interactions_by_user: Dict[str, List[MemoryEntry]] = {}
            for row_data in rows:
                entry = self.memory_storage._row_to_entry(row_data)
                meta = entry.get('metadata', {})
                if not can_use_json_extract and meta.get('analyzed_for_facts') is True:
                    continue # Skip if already analyzed (Python filter)
                
                user_id = meta.get('user_id')
                if user_id and user_id not in self.system_user_ids:
                    if user_id not in interactions_by_user:
                        interactions_by_user[user_id] = []
                    if len(interactions_by_user[user_id]) < batch_size:
                        interactions_by_user[user_id].append(entry)
            
            if not interactions_by_user:
                logger.info("--- Ethos: Interaction Log Analysis Finished (No new interactions to analyze) ---")
                return

            for user_id, interactions in interactions_by_user.items():
                if not interactions: continue
                
                transcript_parts = []
                for i_entry in interactions:
                    # Reconstruct a simplified turn for the LLM
                    interaction_content = i_entry.get('content', '')
                    # Try to find User: and Pathos: parts if they exist
                    user_part_match = re.search(r"User(?: \([^)]+\))?: (.*?)(?=\nPathos:|\Z)", interaction_content, re.DOTALL)
                    pathos_part_match = re.search(r"Pathos: (.*?)(?=\nTools Used by Pathos:|\Z)", interaction_content, re.DOTALL)
                    
                    user_text = user_part_match.group(1).strip() if user_part_match else "[User input not clearly parsed]"
                    pathos_text = pathos_part_match.group(1).strip() if pathos_part_match else "[Pathos response not clearly parsed]"
                    
                    transcript_parts.append(f"User: {user_text}\nPathos: {pathos_text}")

                transcript = "\n---\n".join(transcript_parts)
                
                max_len_transcript = (llm_config.get('max_tokens', 4096) - 512) * 2 # Rough estimate for context window
                if len(transcript) > max_len_transcript:
                    transcript = transcript[:max_len_transcript] + "\n[Transcript Truncated]"

                sys_prompt = load_system_prompt("fact_extraction_llm_system_prompt", "Extract user facts, world facts, and AI learnings from transcript.")
                user_prompt = f"Analyze this conversation transcript involving User '{user_id}' and Pathos. Extract any specific user facts (things the user explicitly states about themselves like preferences, personal details), general world facts Pathos might have learned, or key learnings/corrections for Pathos. Format each extracted item as a JSON object with keys: 'type' (user_fact, world_fact, ai_learning), 'attribute_name' (for user_fact, e.g., 'favorite_color'; for world_fact, a concise title/topic; for ai_learning, the topic of learning), 'attribute_value' (the fact/learning itself), and 'supporting_statement' (the sentence(s) from the transcript supporting this extraction). If multiple items, return a JSON list of these objects. If nothing notable, return an empty list [].\n\nTranscript:\n{transcript}\n\nYour JSON output:"
                
                llm_resp = await self._call_llm_for_internal_task([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}], llm_role)
                
                parsed_successfully = False
                if llm_resp and not llm_resp.startswith("[LLM"): # Check for LLM call errors
                    try:
                        # Attempt to clean and parse the JSON (might be a list or a single object)
                        cleaned_resp = re.sub(r"```json\s*|\s*```", "", llm_resp).strip()
                        if not cleaned_resp: # Handle empty string after cleaning
                            items_data = []
                        elif cleaned_resp.startswith("[") and cleaned_resp.endswith("]"):
                            items_data = json.loads(cleaned_resp)
                        elif cleaned_resp.startswith("{") and cleaned_resp.endswith("}"):
                            items_data = [json.loads(cleaned_resp)] # Wrap single object in a list
                        else: # If it's not clearly a list or object, log and treat as no items
                            logger.warning(f"Fact extraction LLM response for user '{user_id}' was not a clear JSON list/object: {cleaned_resp[:200]}")
                            items_data = []
                        
                        parsed_successfully = True
                        
                        if not isinstance(items_data, list):
                            logger.warning(f"Fact extraction LLM response for user '{user_id}' was not a list after parsing: {type(items_data)}. Data: {str(items_data)[:200]}")
                            items_data = []

                        stored_count = 0
                        for item in items_data:
                            if not isinstance(item, dict): continue
                            item_type = str(item.get('type', '')).strip().lower()
                            attr_name = str(item.get('attribute_name', '')).strip()
                            attr_val = str(item.get('attribute_value', '')).strip()
                            support = str(item.get('supporting_statement', 'From conversation analysis.')).strip()

                            if not item_type or not attr_name or not attr_val: continue
                            
                            norm_key = attr_name.lower().replace(" ", "_").replace("/", "_").strip()
                            if not norm_key: continue

                            if item_type in ['user_fact', 'strongly_implied_user_fact']:
                                fact_content = {"attribute": attr_name, "value": attr_val, "original_user_statement": support}
                                await self.add_memory_entry(
                                    entry_data={"type": 'user_fact', "content": json.dumps(fact_content), 
                                          "metadata": {"user_id": user_id, "fact_attribute_key": norm_key, 
                                                       "source": f"interaction_log_analysis{'_inferred' if item_type == 'strongly_implied_user_fact' else ''}"}, 
                                          "salience": 1.3 if item_type == 'user_fact' else 1.1},
                                    user_id_context=user_id
                                )
                                stored_count += 1
                            elif item_type == 'world_fact':
                                await self.add_memory_entry(
                                    entry_data={"type": "world_knowledge", "content": f"{attr_name}: {attr_val}", 
                                          "metadata": {"user_id": "system_reflection", # Or user_id if fact is user-specific general knowledge
                                                       "source_description": f"Learned from conversation with {user_id}: {support}", 
                                                       "topic_tags": [norm_key], "source": "interaction_log_analysis"}, 
                                          "salience": 0.75},
                                    user_id_context="world_knowledge_store"
                                )
                                stored_count += 1
                            elif item_type == 'ai_learning': # Pathos's learning
                                await self.add_memory_entry(
                                    entry_data={"type": "learned_correction", # Or a more general "pathos_learning" type
                                          "content": f"Pathos learning point regarding '{attr_name}': {attr_val}", 
                                          "metadata": {"user_id": PATHOS_USER_ID, # Learning is for Pathos
                                                       "source_interaction_user_id": user_id,
                                                       "source_interaction_snippet": support, 
                                                       "source": "interaction_log_analysis"}, 
                                          "salience": 1.1},
                                    user_id_context=PATHOS_USER_ID
                                )
                                stored_count += 1
                        if stored_count > 0:
                            logger.info(f"Stored {stored_count} facts/learnings from interaction analysis for user '{user_id}'.")
                    except json.JSONDecodeError as e_json_parse:
                        logger.error(f"Failed to parse fact extraction JSON for user '{user_id}'. Error: {e_json_parse}. Response: {cleaned_resp[:500]}")
                    except Exception as e_store:
                        logger.error(f"Error storing extracted facts for user '{user_id}': {e_store}", exc_info=True)
                
                # Mark original interactions as analyzed, regardless of successful extraction, if LLM call was made
                if llm_resp and not llm_resp.startswith("[LLM"): # Indicates LLM call was attempted
                    for entry_to_mark in interactions:
                        if entry_id_to_mark := entry_to_mark.get('id'):
                            if original_entry := self.memory_storage.get_entry(entry_id_to_mark):
                                meta_to_update = original_entry.get('metadata', {}).copy()
                                meta_to_update['analyzed_for_facts'] = True
                                meta_to_update['analyzed_for_facts_timestamp'] = now.isoformat()
                                if not parsed_successfully:
                                    meta_to_update['analyzed_for_facts_error'] = "LLM_response_parsing_failed"
                                self.memory_storage.update_entry(entry_id_to_mark, {'metadata': meta_to_update})
                
                await asyncio.sleep(random.uniform(self.ethos_config.get('interaction_log_analysis_delay_min', 2.0), 
                                                  self.ethos_config.get('interaction_log_analysis_delay_max', 5.0)))
        except Exception as e:
            logger.error(f"Error in Interaction Log Analysis cycle: {e}", exc_info=True)
        logger.info("--- Ethos: Interaction Log Analysis Finished ---")

    async def autonomous_long_term_planning_cycle(self):
        if not self.config.ENABLE_PROACTIVE_BEHAVIOR: return
        if not self.logos_core or not self.chronos_engine:
            logger.error("LogosCore or ChronosEngine not available for long-term planning.")
            return
        
        interval = self.ethos_config.get('long_term_planning_interval_seconds', 86400.0 * 3)
        now = datetime.now(timezone.utc)
        if interval <= 0 or now - self.last_long_term_planning_time < timedelta(seconds=interval):
            return
            
        logger.info("--- EthosCore: Starting Autonomous Long-Term Planning Cycle ---")
        self.last_long_term_planning_time = now
        self._save_task_last_run_time("PathosLongTermPlanning", now)

        try:
            max_aspirations_to_plan = self.ethos_config.get('long_term_planning_max_aspirations', 2)
            aspirations = await self.memory_storage.get_entries_by_type_and_user("aspiration", PATHOS_USER_ID, max_aspirations_to_plan * 2) # Fetch more to filter
            
            pending_aspirations = []
            for asp_entry in aspirations:
                if isinstance(asp_entry.get('content'), str):
                    try:
                        asp_data_check = json.loads(asp_entry['content'])
                        if asp_data_check.get('status') == 'pending':
                            pending_aspirations.append(asp_entry)
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse aspiration content for ID {asp_entry.get('id')}")
            
            if not pending_aspirations:
                logger.info("No pending aspirations for Pathos to plan.")
                logger.info("--- EthosCore: Autonomous Long-Term Planning Cycle Finished (No pending aspirations) ---")
                return
            
            # Limit to max_aspirations_to_plan
            aspirations_to_process = pending_aspirations[:max_aspirations_to_plan]

            planning_llm_role = self.ethos_config.get('long_term_planning_llm_role', 'LOGOS_TECHNE')
            planning_llm_config = self.config.get_llm_config(planning_llm_role)
            if not planning_llm_config or not planning_llm_config.get('url'):
                logger.error(f"Planning LLM '{planning_llm_role}' not configured.")
                logger.info("--- EthosCore: Autonomous Long-Term Planning Cycle Finished (LLM Misconfig) ---")
                return

            for asp_entry in aspirations_to_process:
                asp_id = asp_entry.get('id')
                asp_content_str = asp_entry.get('content')
                if not isinstance(asp_content_str, str): continue
                
                try:
                    asp_data = json.loads(asp_content_str)
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse aspiration content for ID {asp_id} during planning.")
                    continue
                
                research_notes = asp_data.get('research_notes', "")
                # Trigger research if notes are short or non-existent
                if not research_notes or len(research_notes) < self.ethos_config.get('long_term_planning_min_research_length_before_new', 200):
                    research_depth = self.ethos_config.get('long_term_planning_research_depth', 2)
                    research_query_parts = [f"Practical steps and considerations for {asp_data.get('title', 'this aspiration')}",
                                            f"focusing on {asp_data.get('type', 'general planning')}"]
                    if asp_data.get('potential_location'): research_query_parts.append(f"in {asp_data['potential_location']}")
                    if asp_data.get('potential_timeframe'): research_query_parts.append(f"around {asp_data['potential_timeframe']}")
                    research_query = ", ".join(research_query_parts)
                    
                    logger.info(f"Planning: Researching aspiration '{asp_data.get('title')}' (ID: {asp_id}). Query: {research_query[:200]}")
                    new_research = await self.logos_core.execute_deep_research(research_query, research_depth)
                    
                    if new_research and not new_research.startswith('{"error":'):
                        research_notes = (research_notes + "\n\n--- Additional Research (" + now.strftime("%Y-%m-%d") + ") ---\n" + new_research).strip()
                        asp_data['research_notes'] = research_notes
                        self.memory_storage.update_entry(asp_id, {'content': json.dumps(asp_data)})
                        logger.info(f"Updated aspiration {asp_id} with new research notes.")
                    else:
                        logger.warning(f"Research for aspiration {asp_id} yielded no new results or an error: {new_research}")

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
Respond ONLY with JSON: {{"decision": "SCHEDULE" | "POSTPONE", "reasoning": "brief explanation", "event_title": "if SCHEDULE", "start_date": "YYYY-MM-DD if SCHEDULE", "end_date": "YYYY-MM-DD if SCHEDULE", "event_type": "from aspiration_type if SCHEDULE, must be valid EventType"}}
""" # Added EventType constraint
                decision_resp = await self._call_llm_for_internal_task([{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}], planning_llm_role)
                
                if decision_resp and not decision_resp.startswith("[LLM"):
                    try:
                        decision_data = json.loads(re.sub(r"```json\s*|\s*```", "", decision_resp).strip())
                        if decision_data.get("decision") == "SCHEDULE" and \
                           all(k in decision_data for k in ["event_title", "start_date", "end_date", "event_type"]):
                            
                            # Validate event_type from LLM
                            llm_event_type = decision_data["event_type"]
                            from eidos_agent.modules.chronos_models import EventType as ChronosEventType # Local import for enum
                            if llm_event_type not in ChronosEventType.__args__: # type: ignore
                                logger.warning(f"LLM suggested invalid event_type '{llm_event_type}' for aspiration {asp_id}. Defaulting to 'other_event'.")
                                llm_event_type = "other_event"

                            event_payload = {
                                "title": decision_data["event_title"], 
                                "start_date": decision_data["start_date"], 
                                "end_date": decision_data["end_date"], 
                                "event_type": llm_event_type, # Use validated type
                                "description": f"Scheduled event for aspiration: {asp_data.get('title')}. Reasoning: {decision_data.get('reasoning')}", 
                                "location": asp_data.get('potential_location'), 
                                "details": {
                                    "activity_theme": asp_data.get('type'), # Use aspiration type as theme
                                    "planned_sites_or_tasks": asp_data.get('initial_thoughts_or_steps') if isinstance(asp_data.get('initial_thoughts_or_steps'), list) else [asp_data.get('initial_thoughts_or_steps')] if asp_data.get('initial_thoughts_or_steps') else None,
                                    "related_aspiration_id": asp_id
                                },
                                "user_id": PATHOS_USER_ID
                            }
                            added_event = await self.chronos_engine.add_planned_event(event_payload)
                            if added_event:
                                asp_data['status'] = 'scheduled'
                                asp_data['scheduled_event_id'] = added_event.id
                                self.memory_storage.update_entry(asp_id, {'content': json.dumps(asp_data)})
                                logger.info(f"Scheduled event '{added_event.title}' (ID: {added_event.id}) for aspiration {asp_id}.")
                        elif decision_data.get("decision") == "POSTPONE":
                            asp_data['status'] = 'pending_more_info'
                            asp_data['last_postponed_reason'] = decision_data.get('reasoning')
                            self.memory_storage.update_entry(asp_id, {'content': json.dumps(asp_data)})
                            logger.info(f"Postponed aspiration {asp_id}. Reason: {decision_data.get('reasoning')}")
                        else:
                            logger.warning(f"Planning LLM decision for aspiration {asp_id} was not 'SCHEDULE' or 'POSTPONE', or missing fields: {decision_data}")
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse planning decision JSON for aspiration {asp_id}: {decision_resp[:500]}")
                elif decision_resp: # LLM call itself had an error string
                    logger.error(f"Planning LLM call failed for aspiration {asp_id}: {decision_resp}")
                
                await asyncio.sleep(random.uniform(self.ethos_config.get('long_term_planning_delay_min', 3.0), 
                                                  self.ethos_config.get('long_term_planning_delay_max', 7.0)))
        except Exception as e:
            logger.error(f"Error in Autonomous Long-Term Planning Cycle: {e}", exc_info=True)
        logger.info("--- EthosCore: Autonomous Long-Term Planning Cycle Finished ---")

    async def get_background_tasks(self) -> List[asyncio.Task]:
        tasks = []
        async def _run_periodically(coro_func: Any, interval_seconds: float, task_name: str, initial_last_run_time: datetime):
            if interval_seconds <= 0:
                logger.debug(f"Task '{task_name}' disabled (interval <= 0).")
                return
            
            # Calculate initial wait time
            now = datetime.now(timezone.utc)
            time_since_last = now - initial_last_run_time
            wait_time = interval_seconds - time_since_last.total_seconds()
            
            if wait_time > 0:
                logger.debug(f"Task '{task_name}': Initial wait: {wait_time:.2f}s (Interval: {interval_seconds}s, Last run: {initial_last_run_time.isoformat()})")
                await asyncio.sleep(wait_time)
            else:
                logger.debug(f"Task '{task_name}': Running immediately (Interval: {interval_seconds}s, Last run: {initial_last_run_time.isoformat()}, Overdue by: {-wait_time:.2f}s)")

            while True:
                try:
                    logger.debug(f"Task '{task_name}': Executing...")
                    await coro_func()
                    logger.debug(f"Task '{task_name}': Execution finished.")
                except asyncio.CancelledError:
                    logger.info(f"Task '{task_name}' cancelled.")
                    break
                except Exception as e:
                    logger.error(f"Error in background task '{task_name}': {e}", exc_info=True)
                
                # Save last run time *after* successful execution or error handling
                # This is handled by the coro_func itself (e.g., run_reflection_cycle saves its own last_run_time)
                
                logger.debug(f"Task '{task_name}': Sleeping for {interval_seconds:.2f}s.")
                await asyncio.sleep(interval_seconds)

        now_utc = datetime.now(timezone.utc)
        task_configs = [
            (self.run_reflection_cycle, self.ethos_config.get('reflection_interval_seconds', 86400.0), "EthosReflection", any([self.config.ENABLE_LEARNING_FROM_FEEDBACK, self.config.ENABLE_CURIOUSITY, self.ethos_config.get('enable_memory_summarization', False), self.config.ENABLE_PROACTIVE_BEHAVIOR])),
            (self.run_managed_forgetting, self.ethos_config.get('forgetting_interval_seconds', 43200.0), "EthosForgetting", self.config.ENABLE_MANAGED_FORGETTING),
            (self.run_hexus_decay, self.ethos_config.get('hexus_decay_interval_seconds', 3600.0), "HexusDecay", True), # Assuming Hexus decay always runs if mood is enabled
            (self.oneiros_module.run_dream_cycle if self.oneiros_module else None, self.config.ONEIROS.get('dream_interval_seconds', 21600.0), "OneirosDreamCycle", self.config.ENABLE_ONEIROS and self.oneiros_module is not None),
            (self.run_knowledge_upkeep_cycle, self.ethos_config.get('knowledge_upkeep_interval_seconds', 86400.0), "KnowledgeUpkeep", self.config.ENABLE_KNOWLEDGE_UPKEEP),
            (self.run_interaction_log_analysis, self.ethos_config.get('interaction_log_analysis_interval_seconds', 86400.0), "InteractionLogAnalysis", self.ethos_config.get('enable_interaction_log_analysis', False)),
            (self.run_proactive_check, self.ethos_config.get('proactive_check_interval_seconds', 60.0), "ProactiveCheck", self.config.ENABLE_PROACTIVE_BEHAVIOR),
            (self.chronos_engine.daily_schedule_maintenance_task if self.chronos_engine else None, self.ethos_config.get('chronos_maintenance_interval_seconds', 21600.0), "ChronosDailyScheduleMaintenance", self.chronos_engine is not None),
            (self.autonomous_long_term_planning_cycle, self.ethos_config.get('long_term_planning_interval_seconds', 86400.0 * 3), "PathosLongTermPlanning", self.config.ENABLE_PROACTIVE_BEHAVIOR and self.chronos_engine is not None)
        ]

        for coro, interval_cfg, name, enabled_flag in task_configs:
            interval = float(interval_cfg) # Ensure interval is float
            if coro and enabled_flag and interval > 0:
                last_run_time_for_task = self._get_initial_last_run_time(name, interval, now_utc)
                tasks.append(asyncio.create_task(_run_periodically(coro, interval, name, last_run_time_for_task), name=name))
            elif not enabled_flag:
                logger.debug(f"Background task '{name}' disabled by its feature flag.")
            elif not coro:
                 logger.debug(f"Background task '{name}' disabled (coroutine not available - likely module not initialized).")
            elif interval <= 0:
                 logger.debug(f"Background task '{name}' disabled (interval <= 0).")


        logger.info(f"Background tasks initialized: {[task.get_name() for task in tasks if task is not None]}")
        return [task for task in tasks if task is not None] # Filter out None tasks if any

    async def run_proactive_check(self, trigger_source: str = "Timer"):
        if not self.config.ENABLE_PROACTIVE_BEHAVIOR or not self.connection_manager or not self.pathos_interface:
            logger.debug(f"Proactive check skipped (disabled or core components missing). Trigger: {trigger_source}")
            return

        now_utc = datetime.now(timezone.utc)
        logger.debug(f"Running proactive check for all connected users. Trigger: {trigger_source}")

        active_user_ids = list(self.connection_manager.active_connections.keys())
        if not active_user_ids:
            logger.debug("No active users for proactive check.")
            return

        for user_id in active_user_ids:
            logger.debug(f"Proactive check for user: {user_id}")
            now_local_for_user = await self.get_local_datetime_for_user(user_id)
            current_hod = "morning" if 5 <= now_local_for_user.hour < 12 else \
                          "afternoon" if 12 <= now_local_for_user.hour < 18 else "evening"
            
            opportunity: Optional[str] = None
            details: Optional[Dict[str, Any]] = None

            # 1. Check for queued discussion points
            queued_points = await self.get_queued_discussion_points(user_id, 1)
            if queued_points:
                point = queued_points[0]
                point_id = point.get('id')
                point_content = point.get('content')
                point_reason = point.get('metadata', {}).get('reason_for_queueing', 'earlier thoughts')
                
                action_type_queued = f"offered_queued_discussion_{point_id}"
                last_offer_queued = await self.get_last_proactive_action_time(user_id, action_type_queued)
                offer_interval_queued = timedelta(hours=self.ethos_config.get('proactive_queued_point_offer_interval_hours', 24))
                
                if not last_offer_queued or (now_utc - last_offer_queued > offer_interval_queued):
                    if random.random() < float(self.ethos_config.get('proactive_queued_point_chance', 0.5)):
                        opportunity = "queued_discussion"
                        details = {"point_id": point_id, "topic_content": point_content, "reason": point_reason}
                        logger.debug(f"Proactive opportunity for {user_id}: Queued discussion point '{point_id}'.")

            # 2. Check for greeting if no queued point taken
            if not opportunity:
                action_type_greeting = f"greeting_{current_hod}" # Hour of Day specific greeting
                last_greet = await self.get_last_proactive_action_time(user_id, action_type_greeting)
                greeting_interval = timedelta(hours=self.ethos_config.get('proactive_greeting_interval_hours', 4))
                
                # Check if it's a new session (immediate greeting)
                grace_minutes = self.ethos_config.get('proactive_immediate_greeting_grace_minutes', 15)
                # This needs a way to know when a user *just* connected.
                # For now, assume if no greeting for current HOD, it's a candidate.
                
                needs_greeting = not last_greet or (now_utc - last_greet > greeting_interval)
                
                if needs_greeting and random.random() < float(self.ethos_config.get('proactive_greeting_chance', 0.3)):
                    opportunity = "greeting"
                    details = {"time_of_day": current_hod}
                    logger.debug(f"Proactive opportunity for {user_id}: Greeting for {current_hod}.")
            
            # 3. Offer briefing discussion if no other opportunity taken
            if not opportunity and self.config.ENABLE_DAILY_CONTEXT:
                briefing_content = await self.get_todays_briefing() # Pathos's internal briefing
                if briefing_content is None and self.logos_core: # If no briefing, try to generate one
                    logger.info(f"No briefing found for {now_utc.date()}, attempting to generate for user context {user_id}.")
                    asyncio.create_task(self.logos_core.generate_daily_briefing(user_id_context=user_id), name=f"GenBriefingProactive_{now_utc.strftime('%Y%m%d')}_{user_id}")
                    # Don't offer it this cycle, let it generate first
                elif briefing_content:
                    action_type_briefing = "offer_briefing_discussion"
                    last_offer_briefing = await self.get_last_proactive_action_time(user_id, action_type_briefing)
                    # Offer briefing once per day
                    if not last_offer_briefing or last_offer_briefing.date() < now_utc.date():
                        if random.random() < float(self.ethos_config.get('proactive_briefing_chance', 0.2)): # Lower chance
                            opportunity = "offer_briefing_discussion"
                            details = {"briefing_date": now_utc.strftime('%Y-%m-%d'), "full_briefing_content_snippet": briefing_content[:300]+"..."}
                            logger.debug(f"Proactive opportunity for {user_id}: Offer briefing discussion.")
            
            # 4. Offer topic continuation (Lower priority)
            if not opportunity:
                # This needs a method to get recent interaction topics, e.g., from context_summary memories
                # For now, this part is conceptual.
                # recent_topics = await self.get_recent_interaction_topics(user_id, 1) 
                # if recent_topics: ...
                pass

            if opportunity and self.pathos_interface:
                logger.info(f"Generating proactive message for user '{user_id}', type '{opportunity}'.")
                proactive_msg_text, proactive_audio_chunks = await self.pathos_interface._generate_proactive_message(user_id, opportunity, details)
                
                if proactive_msg_text:
                    proactive_utterance_id = str(uuid.uuid4())
                    # Construct metadata for the proactive message
                    proactive_metadata = {
                        "proactive_type": opportunity,
                        "proactive_utterance_id": proactive_utterance_id,
                        "timestamp": now_utc.isoformat(),
                        "mood_at_generation": self.get_current_mood(), # Pathos's mood
                        "hexus_at_generation": self.get_hexus_scores() # Pathos's hexus
                    }
                    if details: proactive_metadata.update(details) # Add specific details of the opportunity

                    ws_payload = {
                        "type": "unsolicited_message",
                        "payload": {
                            "content": [proactive_msg_text, proactive_audio_chunks], # Send text and audio info
                            "metadata": proactive_metadata
                        }
                    }
                    await self.connection_manager.send_personal_message(ws_payload, user_id)
                    
                    # Record the specific action taken
                    action_type_to_record = opportunity
                    if opportunity == "greeting": action_type_to_record = f"greeting_{current_hod}"
                    elif opportunity == "queued_discussion" and details and "point_id" in details:
                        action_type_to_record = f"offered_queued_discussion_{details['point_id']}"
                        await self.mark_queued_point_offered(details['point_id'], user_id)
                    
                    await self.record_proactive_action(user_id, action_type_to_record, details)
                else:
                    logger.warning(f"Proactive message generation failed for user '{user_id}', type '{opportunity}'.")
            elif opportunity:
                logger.warning(f"Proactive opportunity '{opportunity}' for user '{user_id}' but PathosInterface not available.")
            
            await asyncio.sleep(random.uniform(0.5, 1.5)) # Stagger checks for different users slightly

    async def get_last_proactive_action_time(self, user_id: str, action_type: str) -> Optional[datetime]:
        if not user_id or not action_type: return None
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        can_use_json_extract = True
        try:
            cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')"); result = cursor.fetchone()
            if result is None or result[0] != 'value': can_use_json_extract = False
        except sqlite3.OperationalError as oe_test:
            if "no such function: json_extract" in str(oe_test).lower(): can_use_json_extract = False
            else: logger.error(f"Unexpected SQLite error checking json_extract: {oe_test}", exc_info=True); can_use_json_extract = False
        except Exception as e_test_other: logger.error(f"General error checking json_extract: {e_test_other}", exc_info=True); can_use_json_extract = False
        
        sql_query, params = "", []
        if can_use_json_extract:
            sql_query = "SELECT timestamp FROM memories WHERE type = 'proactive_action_record' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.action_type') = ? ORDER BY timestamp DESC LIMIT 1"
            params = [user_id, action_type]
        else:
            logger.warning(f"json_extract not available for get_last_proactive_action_time (user: {user_id}, action: {action_type}).")
            sql_query = "SELECT timestamp, metadata FROM memories WHERE type = 'proactive_action_record' ORDER BY timestamp DESC LIMIT 100" # Fetch more for Python filter
        try:
            cursor.execute(sql_query, tuple(params))
            if not can_use_json_extract:
                for row_data_raw in cursor.fetchall():
                    row_dict = dict(row_data_raw); metadata_str = row_dict.get('metadata')
                    if metadata_str and isinstance(metadata_str, str):
                        try:
                            metadata = json.loads(metadata_str)
                            if isinstance(metadata, dict) and metadata.get('user_id') == user_id and metadata.get('action_type') == action_type:
                                if ts_str := row_dict.get('timestamp'): return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        except (json.JSONDecodeError, ValueError, TypeError): continue
                return None
            else:
                if row := cursor.fetchone():
                    if ts_str := row['timestamp']: return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                return None
        except Exception as e: logger.error(f"Error retrieving last proactive action time for user '{user_id}', action '{action_type}': {e}", exc_info=True); return None

    async def record_proactive_action(self, user_id: str, action_type: str, details: Optional[Dict[str, Any]] = None):
        if not user_id or not action_type: logger.warning("Cannot record proactive action: user_id or action_type missing."); return
        metadata = {"user_id": user_id, "action_type": action_type, "action_details": details or {}}
        await self.add_memory_entry(
            entry_data={"type": "proactive_action_record", "content": f"Proactive action '{action_type}' taken for user '{user_id}'. Details: {json.dumps(details)}", "metadata": metadata, "salience": 0.1},
            user_id_context=user_id
        )
        logger.info(f"Recorded proactive action '{action_type}' for user '{user_id}'.")

    async def get_current_activity_description(self) -> str: # ADDED METHOD
        """Returns a brief description of Pathos's current internal activity."""
        # This is a placeholder. A more sophisticated implementation might
        # check active background tasks, recent internal states, etc.
        # For now, we'll check if any major async tasks are running or recently ran.
        # This is a simplified check.
        if self.last_reflection_time and (datetime.now(timezone.utc) - self.last_reflection_time) < timedelta(minutes=5):
            return "Currently reflecting on recent events."
        if self.last_dream_time and (datetime.now(timezone.utc) - self.last_dream_time) < timedelta(minutes=5) and self.oneiros_module:
            return "Currently processing recent dream experiences."
        if self.last_long_term_planning_time and (datetime.now(timezone.utc) - self.last_long_term_planning_time) < timedelta(minutes=15):
            return "Currently considering long-term plans and aspirations."
        # Add more checks for other significant activities if needed
        return "Currently idle or engaged in routine background processing."

    async def mark_queued_point_offered(self, point_id: str, user_id: str):
        if not point_id: return
        entry = self.memory_storage.get_entry(point_id)
        if entry and entry.get('type') == 'queued_discussion_point':
            metadata = entry.get('metadata', {}).copy()
            metadata['status'] = 'offered'
            metadata['offered_to_user_id'] = user_id
            metadata['offered_timestamp'] = datetime.now(timezone.utc).isoformat()
            self.memory_storage.update_entry(point_id, {'metadata': metadata})
            logger.info(f"Marked queued discussion point '{point_id}' as offered to user '{user_id}'.")

    async def get_queued_discussion_points(self, user_id: str, limit: int = 1) -> List[MemoryEntry]:
        if not user_id: return []
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        can_use_json_extract = True
        try:
            cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')"); result = cursor.fetchone()
            if result is None or result[0] != 'value': can_use_json_extract = False
        except Exception: can_use_json_extract = False
        
        queued_points: List[MemoryEntry] = []; fetch_limit = limit * 2 if limit > 0 else 10
        if can_use_json_extract:
            sql = "SELECT * FROM memories WHERE type = 'queued_discussion_point' AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') IS NULL) AND (json_extract(metadata, '$.status') IS NULL OR json_extract(metadata, '$.status') = 'pending') ORDER BY salience DESC, timestamp ASC LIMIT ?"
            params = (user_id, "system_oneiros", fetch_limit) # Allow points for specific user, system_oneiros (global dreams), or NULL user_id (Pathos's own thoughts)
        else:
            logger.warning("json_extract not available for get_queued_discussion_points. Querying all and filtering in Python.")
            sql = "SELECT * FROM memories WHERE type = 'queued_discussion_point' ORDER BY timestamp DESC LIMIT ?"
            params = (fetch_limit * 5,) # Fetch more for Python filtering
        
        cursor.execute(sql, params); rows_raw = cursor.fetchall()
        for row_data_raw in rows_raw:
            try:
                entry = self.memory_storage._row_to_entry(dict(row_data_raw)); metadata = entry.get('metadata', {})
                entry_user_id = metadata.get('user_id'); status = metadata.get('status', 'pending')
                if not can_use_json_extract:
                    if status != 'pending': continue
                    if not (entry_user_id == user_id or entry_user_id == "system_oneiros" or entry_user_id is None or entry_user_id == PATHOS_USER_ID): continue
                queued_points.append(entry)
            except Exception as e_entry: logger.error(f"Error processing queued point entry: {e_entry}", exc_info=True)
        
        queued_points.sort(key=lambda x: (-(float(x.get('salience', 0.0)) if x.get('salience') is not None else 0.0), x.get('timestamp', '') or ''), reverse=False)
        final_limit = queued_points[:limit]
        logger.info(f"Retrieved {len(final_limit)} queued discussion points for user_id: {user_id} (Limit: {limit}, Fetched before sort/filter: {len(rows_raw)}, After initial filter: {len(queued_points)})")
        return final_limit

    async def clear_memory_for_user(self, user_id: str) -> bool:
        if not user_id or not user_id.strip(): return False
        try: return self.memory_storage.delete_entries_by_user_id(user_id)
        except Exception as e: logger.error(f"Error clearing memory for user '{user_id}': {e}", exc_info=True); return False

    async def get_recent_learnings(self, learning_types: List[str], user_id_context: Optional[str], limit: int) -> List[MemoryEntry]:
        if not learning_types or limit <= 0: return []
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        placeholders = ','.join('?' * len(learning_types)); sql = f"SELECT * FROM memories WHERE type IN ({placeholders})"
        params: List[Any] = list(learning_types)
        can_use_json = True
        try: cursor.execute("SELECT json_extract('{\"k\":\"v\"}', '$.k')")
        except sqlite3.OperationalError: can_use_json = False
        
        if can_use_json:
            if user_id_context and user_id_context not in self.system_user_ids:
                sql += " AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') = ?)"
                params.extend([user_id_context, PATHOS_USER_ID]) # Pathos's own learnings are relevant too
            elif user_id_context in self.system_user_ids or not user_id_context: # For system or no specific user, get Pathos's learnings
                sql += " AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') IS NULL)"
                params.append(PATHOS_USER_ID)
        sql += " ORDER BY timestamp DESC LIMIT ?"; params.append(limit * 5 if not can_use_json else limit)
        
        try:
            cursor.execute(sql, tuple(params)); rows = cursor.fetchall(); learnings: List[MemoryEntry] = []
            for row_data in rows:
                entry = self.memory_storage._row_to_entry(dict(row_data)); entry_uid = entry.get('metadata', {}).get('user_id')
                if not can_use_json: # Python-side filtering if json_extract not available
                    if user_id_context and user_id_context not in self.system_user_ids:
                        if entry_uid != user_id_context and entry_uid != PATHOS_USER_ID: continue
                    elif user_id_context in self.system_user_ids or not user_id_context:
                        if entry_uid != PATHOS_USER_ID and entry_uid is not None: continue # Allow NULL user_id for Pathos's general learnings
                learnings.append(entry)
            if not can_use_json: learnings.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            return learnings[:limit]
        except Exception as e: logger.error(f"Error retrieving learnings: {e}", exc_info=True); return []

    async def get_recent_knowledge_verifications(self, limit: int = 20) -> List[MemoryEntry]:
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        sql = "SELECT * FROM memories WHERE type = 'world_knowledge' AND json_extract(metadata, '$.last_verified_timestamp') IS NOT NULL ORDER BY json_extract(metadata, '$.last_verified_timestamp') DESC LIMIT ?"
        oe_msg = ""
        try: cursor.execute(sql, (limit,))
        except sqlite3.OperationalError as oe:
            oe_msg = str(oe).lower()
            if "no such function: json_extract" in oe_msg:
                sql_fb = "SELECT * FROM memories WHERE type = 'world_knowledge' ORDER BY timestamp DESC LIMIT ?" # Less ideal sort
                cursor.execute(sql_fb, (limit * 5,)) # Fetch more for Python filtering
            else: raise
        
        rows = cursor.fetchall(); verifications: List[MemoryEntry] = []
        for row_data in rows:
            entry = self.memory_storage._row_to_entry(dict(row_data))
            if "no such function: json_extract" in oe_msg and entry.get('metadata', {}).get('last_verified_timestamp') is None:
                continue # Python filter if json_extract failed
            verifications.append(entry)
        
        if "no such function: json_extract" in oe_msg: # Re-sort if we had to Python filter
            verifications.sort(key=lambda x: x.get('metadata', {}).get('last_verified_timestamp', '0000-00-00T00:00:00Z'), reverse=True)
        
        return verifications[:limit]

    async def get_user_profile_summary(self, user_id: str) -> str:
        if not user_id or user_id in self.system_user_ids:
            return "No specific profile information available for this user yet."
        
        facts = await self.get_all_user_facts(user_id)
        if not facts:
            return "No specific profile information available for this user yet."
        
        parts = []
        for fact_entry in facts[:5]: # Limit for brevity
            try:
                content_str = fact_entry.get('content')
                if content_str and isinstance(content_str, str):
                    content_data = json.loads(content_str)
                    attribute_name = content_data.get('attribute', 'unknown_attribute')
                    attribute_value = content_data.get('value', 'unknown_value')
                    display_key = attribute_name.replace('_', ' ').title()
                    display_value = str(attribute_value)
                    if len(display_value) > 70: display_value = display_value[:67] + "..."
                    if display_key.lower() == 'name': parts.insert(0, f"Name: {display_value}")
                    elif display_key.lower() == 'preferred location': parts.append(f"Location: {display_value}")
                    else: parts.append(f"{display_key}: {display_value}")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Could not parse user fact for profile summary (user: {user_id}, fact_id: {fact_entry.get('id')}): {e}")
                continue
        
        if not parts: return "No specific profile information available for this user yet."
        return f"User profile for '{user_id}': {'; '.join(parts)}."

    def get_persona_directives(self) -> List[str]: # ADDED METHOD
        """Returns the loaded persona directives for Pathos."""
        return self.persona_directives

    async def get_pathos_aspirations_context_for_prompt(self) -> str:
        try:
            aspirations = await self.memory_storage.get_entries_by_type_and_user("aspiration", PATHOS_USER_ID, 5) # Limit for prompt
            if not aspirations: return "Pathos has no current aspirations defined."
            
            lines = ["Pathos's Current Aspirations:"]
            for entry in aspirations:
                if content_str := entry.get('content'):
                    try:
                        content_data = json.loads(content_str)
                        title = content_data.get('title', str(content_data)) if isinstance(content_data, dict) else str(content_data)
                        status = content_data.get('status', 'unknown')
                        lines.append(f"- {title} (Status: {status})")
                    except json.JSONDecodeError:
                        lines.append(f"- {content_str[:100]}...") # Fallback for unparsable content
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error getting Pathos aspirations context: {e}", exc_info=True)
            return "Aspirations information temporarily unavailable (error)"

    async def get_todays_briefing_context_for_prompt(self, user_id: str) -> str:
        try:
            if not self.logos_core:
                return "Briefing service unavailable (LogosCore missing)."
            
            briefing_data = await self.logos_core.get_or_generate_daily_briefing(user_id_context=user_id)
            if briefing_data and briefing_data.get('success') and briefing_data.get('briefing_content'):
                content = str(briefing_data['briefing_content'])
                max_len = self.ethos_config.get('briefing_context_max_length_for_prompt', 1500)
                return f"Today's Briefing Highlights for Pathos (and user '{user_id}'):\n{content[:max_len] + '...' if len(content) > max_len else content}"
            return "No briefing available for Pathos today."
        except Exception as e:
            logger.error(f"Error getting briefing context for prompt: {e}", exc_info=True)
            return "Briefing information temporarily unavailable (error)"

    async def run_reflection_cycle(self): # ADDED METHOD (Placeholder)
        """
        Placeholder for the Ethos Reflection Cycle.
        This cycle is intended for deeper analysis of recent interactions,
        memory consolidation, insight generation, and self-correction.
        """
        if not any([self.config.ENABLE_LEARNING_FROM_FEEDBACK, self.config.ENABLE_CURIOUSITY, self.ethos_config.get('enable_memory_summarization', False), self.config.ENABLE_PROACTIVE_BEHAVIOR]):
            logger.debug("EthosReflection cycle skipped as all related features are disabled.")
            return

        now = datetime.now(timezone.utc)
        logger.info(f"--- Ethos: Starting Reflection Cycle (Placeholder) ---")
        # Actual reflection logic would go here.
        # For example:
        # 1. Retrieve recent interactions and feedback.
        # 2. Analyze for patterns, successes, failures.
        # 3. Generate insights or new knowledge (e.g., world_knowledge, learned_correction).
        # 4. Update Hexus scores based on reflection.
        # 5. Queue discussion points for Pathos or user.
        await asyncio.sleep(10) # Simulate work

        self.last_reflection_time = now
        self._save_task_last_run_time("EthosReflection", now)
        logger.info(f"--- Ethos: Reflection Cycle Finished (Placeholder) ---")

    async def run_managed_forgetting(self): # ADDED METHOD (Placeholder)
        """Placeholder for the managed forgetting process."""
        if not self.config.ENABLE_MANAGED_FORGETTING:
            logger.debug("Managed forgetting cycle skipped as feature is disabled.")
            return
        now = datetime.now(timezone.utc)
        logger.info("--- Ethos: Starting Managed Forgetting Cycle (Placeholder) ---")
        # Actual forgetting logic would go here.
        await asyncio.sleep(5) # Simulate work
        self.last_forgetting_time = now
        self._save_task_last_run_time("EthosForgetting", now)
        logger.info("--- Ethos: Managed Forgetting Cycle Finished (Placeholder) ---")

    async def run_hexus_decay(self): # ADDED METHOD (Placeholder)
        """Placeholder for Hexus score decay over time."""
        now = datetime.now(timezone.utc)
        logger.debug("--- Ethos: Running Hexus Decay (Placeholder) ---")
        # Actual Hexus decay logic would go here.
        # For example, scores might slowly revert to a baseline.
        decay_factor = 0.99 # Example
        for key in self.hexus_scores:
            self.hexus_scores[key] *= decay_factor
        self._save_hexus_scores()
        self.last_hexus_decay_time = now
        self._save_task_last_run_time("HexusDecay", now)
        logger.debug(f"--- Ethos: Hexus Decay Finished (Placeholder). Scores: {self.hexus_scores} ---")

    async def generate_daily_experiential_summary(self, user_id: str = PATHOS_USER_ID) -> str:
        '''
        Generates a narrative summary of Pathos's experiences over the lookback period,
        suitable for seeding dreams in the subconscious_node.
        '''
        default_summary = "Pathos experienced a day of various activities and thoughts."
        if not self.ethos_config.get("enable_memory_summarization", True): # Default to True if not specified
            logger.info("EthosCore: Memory summarization for daily dream seed is disabled by EthosConfig.enable_memory_summarization.")
            return default_summary

        summarization_llm_role = self.ethos_config.get("summarization_llm_role", "LOGOS_TECHNE")
        llm_config = self.config.get_llm_config(summarization_llm_role)

        if not llm_config or not llm_config.get("url"):
            logger.error(f"EthosCore: Summarization LLM role '{summarization_llm_role}' not configured or URL missing. Cannot generate daily summary.")
            return default_summary

        if not self.logos_core: # LogosCore is used for the actual LLM call
            logger.error("EthosCore: LogosCore not available. Cannot make LLM call for daily summary.")
            return default_summary

        try:
            # Get parameters from config
            lookback_hours = self.ethos_config.get("daily_summary_lookback_hours", 18)
            max_memories_to_fetch = self.ethos_config.get("daily_summary_max_memories", 30)

            # 1. Determine Time Range
            pathos_home_tz_str = self.ethos_config.get("pathos_home_timezone", "UTC")
            try:
                pathos_home_tz = pytz.timezone(pathos_home_tz_str)
            except pytz.UnknownTimeZoneError:
                logger.warning(f"EthosCore: Unknown timezone '{pathos_home_tz_str}' in config. Defaulting to UTC for daily summary.")
                pathos_home_tz = pytz.utc

            # Get Pathos's current local time via the existing EthosCore method
            # This method already handles timezone conversion.
            end_dt_pathos_local = await self.get_local_datetime_for_user(user_id)
            if not end_dt_pathos_local:
                logger.error("EthosCore: Could not determine Pathos's current local time for daily summary. Using UTC now.")
                end_dt_pathos_local = datetime.now(timezone.utc) # Fallback to UTC now

            start_dt_pathos_local = end_dt_pathos_local - timedelta(hours=lookback_hours)

            logger.info(f"EthosCore: Generating daily summary for period: {start_dt_pathos_local.isoformat()} to {end_dt_pathos_local.isoformat()} (Pathos Local Time)")

            # 2. Retrieve Memories
            memory_types_for_summary = [
                'interaction', 'firmament_activity_log', 'received_subconscious_intention',
                'npc_dialogue_event', 'dream_narrative_from_node', # include last night's dream
                'user_fact', 'world_knowledge' # recently learned things
            ]
            # get_memories_by_time_range_and_types needs start/end in UTC if DB stores UTC
            # Assuming get_local_datetime_for_user returns tz-aware, convert to UTC for DB query
            start_dt_utc = start_dt_pathos_local.astimezone(timezone.utc)
            end_dt_utc = end_dt_pathos_local.astimezone(timezone.utc)

            # Assuming MemoryStorage will have this method or an equivalent that can handle datetime objects
            # and type filtering. If it expects strings, isoformat() conversion will be needed here.
            # For now, coding as per the assumption it can handle datetime objects.
            recent_memories = await self.memory_storage.get_memories_by_time_range_and_types(
                user_id=user_id,
                start_time=start_dt_utc,
                end_time=end_dt_utc,
                types=memory_types_for_summary,
                limit=max_memories_to_fetch,
                sort_by_salience_then_recency=True # Assumes MemoryStorage method supports this
            )

            if not recent_memories:
                logger.info("EthosCore: No significant memories found in the lookback period for daily summary.")
                return "Pathos's day seemed quiet, with few distinct events or thoughts recorded."

            # 3. Format Memories for Prompt
            formatted_memories_for_prompt = []
            for mem in recent_memories:
                try:
                    # Convert UTC timestamp from memory back to Pathos's local time for display in prompt
                    mem_ts_utc = datetime.fromisoformat(mem.get('timestamp', '').replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                    mem_ts_local = mem_ts_utc.astimezone(pathos_home_tz)
                    time_str = mem_ts_local.strftime("%H:%M")
                    # Shorten content, especially for logs or long interactions
                    content_snippet = mem.get('content', '')
                    if len(content_snippet) > 100: content_snippet = content_snippet[:97] + "..."
                    formatted_memories_for_prompt.append(f"- {time_str} ({mem.get('type')}): {content_snippet}")
                except ValueError: # Catch errors from fromisoformat or strftime
                    formatted_memories_for_prompt.append(f"- ({mem.get('type')}): {mem.get('content', '')[:100]}...")

            memory_text_for_prompt = "\n".join(formatted_memories_for_prompt)

            # 4. Fetch Current Mood
            current_mood = self.get_current_mood() # This is synchronous
            mood_summary_for_prompt = f"His overall mood state towards the end of this period was: {current_mood.get('name', 'neutral')} (Valence: {current_mood.get('valence',0):.2f}, Arousal: {current_mood.get('arousal',0):.2f})."

            # 5. Construct LLM Prompt
            system_prompt = (
                "You are tasked with creating a brief, narrative summary of Pathos's day based on selected memories and his mood. "
                "This summary will be used to seed his subconscious dream engine. Focus on key events, significant interactions, "
                "strong emotional shifts, important thoughts, or new learnings. "
                "Weave these elements into a short story (1-2 paragraphs, max 150-200 words). "
                "Be evocative and reflective, capturing the essence of his experiences. Do not just list memories."
            )
            user_prompt = (
                f"Here are selected memories from Pathos's experiences over the last {lookback_hours} hours (times are Pathos's local time {pathos_home_tz_str}):\n"
                f"{memory_text_for_prompt}\n\n"
                f"{mood_summary_for_prompt}\n\n"
                "Please provide the narrative summary of Pathos's day:"
            )
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

            # 6. LLM Call via LogosCore (assuming _call_llm_client_directly exists and is suitable)
            # The _call_llm_client_directly method in LogosCore returns a Dict, we need the text content.
            llm_response_dict = await self.logos_core._call_llm_client_directly(
                llm_config=llm_config,
                messages=messages,
                max_tokens_override=300 # Allow enough tokens for a couple of paragraphs
            )

            if llm_response_dict and llm_response_dict.get("content"):
                summary_text = str(llm_response_dict["content"]).strip()
                logger.info(f"EthosCore: Successfully generated daily summary: '{summary_text[:100]}...'")
                return summary_text
            else:
                logger.error(f"EthosCore: Daily summary generation LLM call did not return valid content. Response: {llm_response_dict}")
                return default_summary

        except Exception as e:
            logger.error(f"EthosCore: Error generating daily experiential summary: {e}", exc_info=True)
            return default_summary

    async def chronos_bridge_add_event(self, title: str, start_date_str: str, end_date_str: str, event_type_str: str, description: Optional[str], location: Optional[str], activity_theme: Optional[str], planned_sites_or_tasks: Optional[List[str]], user_id_for_event: str) -> Optional[str]:
        if not self.chronos_engine:
            logger.error("ChronosEngine not available in EthosCore to add event.")
            return None
        try:
            event_data = {
                "title": title, "start_date": start_date_str, "end_date": end_date_str,
                "event_type": event_type_str, "description": description, "location": location,
                "details": {"activity_theme": activity_theme, "planned_sites_or_tasks": planned_sites_or_tasks},
                "user_id": user_id_for_event # This should be PATHOS_USER_ID if Pathos is scheduling for himself
            }
            added_event = await self.chronos_engine.add_planned_event(event_data)
            return added_event.id if added_event else None
        except Exception as e:
            logger.error(f"Error in chronos_bridge_add_event: {e}", exc_info=True)
            return None
            
    def get_current_mood(self) -> Dict[str, float]: # ADDED METHOD
        """Returns the current mood state of Pathos."""
        if not self.config.ENABLE_MOOD_SIMULATION:
            return {"valence": 0.0, "arousal": 0.0, "simulation_disabled": True}
        return self.current_mood

    async def update_mood_state(self, event_type: str, payload: Optional[Dict[str, Any]] = None):
        """
        Updates Pathos's mood based on an event.
        This is a simplified placeholder. A more complex MoodEngine would live here.
        """
        if not self.config.ENABLE_MOOD_SIMULATION:
            return

        valence_shift, arousal_shift = 0.0, 0.0

        if event_type == 'feedback':
            fb_type = payload.get('feedback_type') if payload else None
            rating = payload.get('rating') if payload else None
            if fb_type == 'positive' or (rating is not None and rating > 0):
                valence_shift += MOOD_SHIFT_VALENCE_FEEDBACK_POSITIVE
                arousal_shift += MOOD_SHIFT_AROUSAL_FEEDBACK_POSITIVE
            elif fb_type == 'negative' or (rating is not None and rating < 0):
                valence_shift += MOOD_SHIFT_VALENCE_FEEDBACK_NEGATIVE
                arousal_shift += MOOD_SHIFT_AROUSAL_FEEDBACK_NEGATIVE
            elif fb_type == 'correction': # Corrections might be slightly negative initially but lead to positive if learned
                valence_shift -= 0.05 
                arousal_shift += 0.03
        # Add other event_types: 'successful_tool_use', 'failed_tool_use', 'new_learning', 'dream_recalled' etc.
        
        self.current_mood['valence'] = max(MOOD_MIN, min(MOOD_MAX, self.current_mood['valence'] + valence_shift))
        self.current_mood['arousal'] = max(MOOD_MIN, min(MOOD_MAX, self.current_mood['arousal'] + arousal_shift))
        self.last_mood_update_time = datetime.now(timezone.utc)
        logger.debug(f"Mood updated due to '{event_type}'. New mood: V={self.current_mood['valence']:.3f}, A={self.current_mood['arousal']:.3f}")

    async def retrieve_relevant_past_interactions(
        self,
        query_text: str,
        user_id: str,
        current_history_entry_ids: List[str], # IDs of MemoryEntry objects already in the standard recent history
        top_k: int,
        similarity_threshold: float
    ) -> List[MemoryEntry]:
        """
        Retrieves relevant past chat interactions based on similarity to the query_text,
        excluding entries already present in the current recent history.
        """
        logger.info(f"Retrieving relevant past interactions for user '{user_id}' with query '{query_text[:50]}...'. Excluding {len(current_history_entry_ids)} current IDs. Top_k={top_k}, Threshold={similarity_threshold}")

        if not query_text or not user_id:
            return []

        # Fetch more candidates than top_k to allow for filtering
        # The +5 is a small buffer. Consider if memory_storage.find_similar's internal limit (e.g. 500) is sufficient.
        fetch_k = top_k + len(current_history_entry_ids) + 10

        # Call memory_storage.find_similar()
        # Assuming 'interaction' is the correct type for past conversation turns.
        # The find_similar method in MemoryStorage already filters out 'pending_context_document' and 'chat_storage'.
        try:
            # find_similar returns List[Tuple[float, MemoryEntry]]
            similar_results_with_scores = self.memory_storage.find_similar(
                query_text=query_text,
                top_k=fetch_k, # Fetch more to filter
                allowed_types=['interaction'], # Specify that we only want 'interaction' type memories
                threshold=similarity_threshold # Use the provided threshold
            )
        except Exception as e:
            logger.error(f"Error calling memory_storage.find_similar: {e}", exc_info=True)
            return []

        if not similar_results_with_scores:
            logger.debug(f"No similar past interactions found by memory_storage.find_similar for user '{user_id}'.")
            return []

        # Filter results in Python
        valid_candidates: List[MemoryEntry] = []
        processed_ids = set(current_history_entry_ids) # Keep track of IDs to ensure uniqueness after filtering

        for score, mem_entry in similar_results_with_scores:
            entry_id = mem_entry.get('id')
            if not entry_id or entry_id in processed_ids:
                logger.debug(f"Skipping entry ID {entry_id}: already processed or in current history.")
                continue

            # Ensure the user_id in the metadata matches the input user_id
            # This is crucial if find_similar doesn't filter by user_id in its SQL for 'interaction' type.
            # MemoryStorage.find_similar has a user_id_context param but it's for prioritizing, not strict filtering for all types.
            metadata_user_id = mem_entry.get('metadata', {}).get('user_id')
            if metadata_user_id != user_id:
                logger.debug(f"Skipping entry ID {entry_id}: metadata user_id '{metadata_user_id}' does not match requested user_id '{user_id}'.")
                continue

            # Add score to metadata if not already there, for potential later use, though not strictly needed by PromptBuilder currently
            if 'similarity_score' not in mem_entry.get('metadata', {}): # Avoid overwriting if somehow already there
                 mem_entry.setdefault('metadata', {})['similarity_score'] = score

            valid_candidates.append(mem_entry)
            processed_ids.add(entry_id) # Add to processed to ensure it's not picked again if somehow duplicated in find_similar results

        # Sort by similarity score (descending) - find_similar already does this, but if we combined lists, re-sorting might be needed.
        # Here, find_similar already sorts, so this is more for ensuring contract if logic changed.
        # valid_candidates.sort(key=lambda x: x.get('metadata', {}).get('similarity_score', 0.0), reverse=True)
        # No need to re-sort if find_similar's output order is trusted for the filtered set.

        final_selection = valid_candidates[:top_k]

        logger.info(f"Retrieved {len(final_selection)} relevant past interactions for user '{user_id}' after filtering. (Initial candidates: {len(similar_results_with_scores)}, Valid after filters: {len(valid_candidates)})")
        return final_selection