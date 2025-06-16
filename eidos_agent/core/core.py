from __future__ import annotations
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import sqlite3
import logging

from .memory_storage import MemoryStorage, MemoryEntry
from .chronos_engine import ChronosEngine
from .logos_core import LogosCore

logger = logging.getLogger(__name__)

PATHOS_USER_ID = "pathos_user_id"  # This should be the actual user ID for Pathos


class EthosCore:
    def __init__(self, memory_storage: MemoryStorage, chronos_engine: ChronosEngine, logos_core: LogosCore, ethos_config: dict):
        self.memory_storage = memory_storage
        self.chronos_engine = chronos_engine
        self.logos_core = logos_core
        self.ethos_config = ethos_config
        self.system_user_ids = [PATHOS_USER_ID]  # Add any other system user IDs here

    async def get_last_proactive_action_time(self, user_id: str, action_type: str) -> Optional[datetime]:
        if not user_id or not action_type: return None
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        can_use_json_extract = True
        try:
            cursor.execute("""SELECT json_extract('{"key":"value"}', '$.key')"""); result = cursor.fetchone()
            if result is None or result[0] != 'value': can_use_json_extract = False
        except sqlite3.OperationalError as oe_test:
            if "no such function: json_extract" in str(oe_test).lower(): can_use_json_extract = False
            else: logger.error(f"Unexpected SQLite error checking json_extract: {oe_test}", exc_info=True); can_use_json_extract = False
        except Exception as e_test_other: logger.error(f"General error checking json_extract: {e_test_other}", exc_info=True); can_use_json_extract = False
        
        sql_query, params_list = "", [] 
        if can_use_json_extract:
            sql_query = "SELECT timestamp FROM memories WHERE type = 'proactive_action_record' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.action_type') = ? ORDER BY timestamp DESC LIMIT 1"
            params_list = [user_id, action_type]
        else:
            logger.warning(f"json_extract not available for get_last_proactive_action_time (user: {user_id}, action: {action_type}).")
            sql_query = "SELECT timestamp, metadata FROM memories WHERE type = 'proactive_action_record' ORDER BY timestamp DESC LIMIT 100" 
        try:
            cursor.execute(sql_query, tuple(params_list)) 
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

    async def get_queued_discussion_points(self, user_id: str, limit: int = 1) -> List[MemoryEntry]:
        if not user_id: return []
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        can_use_json_extract = True
        try:
            cursor.execute("""SELECT json_extract('{"key":"value"}', '$.key')"""); result = cursor.fetchone()
            if result is None or result[0] != 'value': can_use_json_extract = False
        except Exception: can_use_json_extract = False
        
        queued_points: List[MemoryEntry] = []; fetch_limit = limit * 2 if limit > 0 else 10
        sql_query_str, params_list = "", [] 
        if can_use_json_extract:
            sql_query_str = "SELECT * FROM memories WHERE type = 'queued_discussion_point' AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') IS NULL) AND (json_extract(metadata, '$.status') IS NULL OR json_extract(metadata, '$.status') = 'pending') ORDER BY salience DESC, timestamp ASC LIMIT ?"
            params_list = [user_id, "system_oneiros", fetch_limit] 
        else:
            logger.warning("json_extract not available for get_queued_discussion_points. Querying all and filtering in Python.")
            sql_query_str = "SELECT * FROM memories WHERE type = 'queued_discussion_point' ORDER BY timestamp DESC LIMIT ?"
            params_list = [fetch_limit * 5] 
        
        cursor.execute(sql_query_str, tuple(params_list)); rows_raw = cursor.fetchall() 
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
        final_limit_list = queued_points[:limit] 
        logger.info(f"Retrieved {len(final_limit_list)} queued discussion points for user_id: {user_id} (Limit: {limit}, Fetched before sort/filter: {len(rows_raw)}, After initial filter: {len(queued_points)})")
        return final_limit_list

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

    async def get_all_user_facts(self, user_id: str) -> List[MemoryEntry]:
        if not user_id or user_id in self.system_user_ids:
            logger.debug(f"get_all_user_facts called for system/invalid user '{user_id}', returning empty list.")
            return []
        
        logger.debug(f"EthosCore: Fetching all user facts for user_id: {user_id}")
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        can_use_json_extract = True
        try:
            cursor.execute("""SELECT json_extract('{"key":"value"}', '$.key')"""); result = cursor.fetchone()
            if result is None or result[0] != 'value': can_use_json_extract = False
        except sqlite3.OperationalError as oe_test:
            if "no such function: json_extract" in str(oe_test).lower(): can_use_json_extract = False
            else: logger.error(f"Unexpected SQLite error checking json_extract: {oe_test}", exc_info=True); can_use_json_extract = False
        except Exception as e_test_other: logger.error(f"General error checking json_extract: {e_test_other}", exc_info=True); can_use_json_extract = False

        facts_entries: List[MemoryEntry] = []
        sql_query_str, params_list = "", [] 
        if can_use_json_extract:
            sql_query_str = "SELECT * FROM memories WHERE type = 'user_fact' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.fact_attribute_key') IS NOT NULL ORDER BY timestamp DESC"
            params_list = [user_id]
        else:
            logger.warning(f"json_extract not available for get_all_user_facts (user: {user_id}). This will be less efficient.")
            sql_query_str = "SELECT * FROM memories WHERE type = 'user_fact' ORDER BY timestamp DESC"
        try:
            cursor.execute(sql_query_str, tuple(params_list)); rows_raw = cursor.fetchall() 
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
            return "\\n".join(lines)
        except Exception as e:
            logger.error(f"Error getting Pathos schedule context for prompt: {e}", exc_info=True)
            return "Schedule information for Pathos is temporarily unavailable (error)"

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
            return "\\n".join(lines)
        except Exception as e: logger.error(f"Error getting Pathos aspirations context: {e}", exc_info=True); return "Aspirations information for Pathos is temporarily unavailable (error)"

    async def get_todays_briefing_context_for_prompt(self, user_id: str) -> str:
        try:
            if not self.logos_core: return "Briefing service unavailable (LogosCore missing)."
            briefing_data = await self.logos_core.get_or_generate_daily_briefing(user_id_context=user_id) 
            if briefing_data and briefing_data.get('success') and briefing_data.get('briefing_content'):
                content = str(briefing_data['briefing_content'])
                max_len = self.ethos_config.get('briefing_context_max_length_for_prompt', 1500)
                return f"Today's Briefing Highlights (Pathos's context, shared with user '{user_id}'):\\n{content[:max_len] + '...' if len(content) > max_len else content}"
            return "No briefing available for Pathos today."
        except Exception as e: logger.error(f"Error getting briefing context for prompt: {e}", exc_info=True); return "Briefing information temporarily unavailable (error)"