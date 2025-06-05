import asyncio
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Optional, Dict, Any
import uuid
import json
import random

from eidos_agent.core.config import Config, LLMConfig
# Relative import for models within the same package
from .models import (
    ActivitySlot, PathosEvent,
    ActivitySlotDetails, PathosEventDetails, ActivityType, EventType
)
# EthosCore imports are already updated to persona_logic in this file
from eidos_agent.persona_logic.ethos_core.memory_storage import MemoryStorage
from eidos_agent.utils.logger import get_logger
import httpx

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from eidos_agent.persona_logic.ethos_core.core import EthosCore
    from eidos_agent.persona_logic.logos_core.handler import LogosCore # Updated import

logger = get_logger(__name__)

PATHOS_USER_ID = "pathos_agent_internal"

class ChronosEngine:
    def __init__(self, config: Config, memory_storage: MemoryStorage, ethos_core: 'EthosCore', logos_core: 'LogosCore'):
        self.config = config
        self.memory_storage = memory_storage
        self.ethos_core = ethos_core
        self.logos_core = logos_core

        self._todays_schedule_cache: Dict[str, List[ActivitySlot]] = {}
        self._cache_date: Optional[date] = None
        self._schedule_generation_lock = asyncio.Lock()

        self.default_daily_slots_config = [
            ("Early Morning Routine & Light Reading", (7,30), (8,30), "reflective"),
            ("Morning Work Block 1 (Client/Consulting)", (8,30), (10,30), "work"),
            ("Short Break / Tech News & Coffee", (10,30), (11,0), "leisure"),
            ("Morning Work Block 2 (Documentation/Admin)", (11,0), (13,0), "work"),
            ("Lunch & Fantasy Novel Chapter", (13,0), (14,30), "leisure"),
            ("Afternoon Focus Session (Deep Work/Learning)", (14,30), (17,0), "intellectual"),
            ("Creative Hour / Personal Project", (17,0), (18,30), "creative"),
            ("Evening Reflection / Planning / Leisure", (20,0), (22,0), "reflective"),
        ]
        self.daily_slots = [(name, time(sh, sm), time(eh, em), type_val) for name, (sh, sm), (eh, em), type_val in self.default_daily_slots_config]

        self.event_day_slots_template_config = [
            ("Morning Event Focus", (9, 0), (12, 0), "event_related"),
            ("Midday Event Activity / Break", (12, 0), (14, 0), "event_related"),
            ("Afternoon Event Focus", (14, 0), (17, 0), "event_related"),
            ("Evening Event Wind-down / Reflection", (19,0), (21,0), "reflective")
        ]
        self.event_day_slots = [(name, time(sh, sm), time(eh, em), type_val) for name, (sh, sm), (eh, em), type_val in self.event_day_slots_template_config]

        logger.info("ChronosEngine initialized.")

    def _get_llm_for_activity_generation(self) -> Optional[LLMConfig]:
        scheduler_llm_role = self.config.ETHOS.get('scheduler_llm_role', 'LOGOS_TECHNE')
        llm_config = self.config.get_llm_config(scheduler_llm_role) # type: ignore
        if not llm_config or not llm_config.get("url"):
            logger.error(f"Chronos LLM config for role '{scheduler_llm_role}' is missing or lacks URL.")
            return None
        return llm_config

    async def _call_scheduler_llm(self, messages: List[Dict[str, Any]], llm_config: LLMConfig) -> Optional[Dict[str, Any]]:
        if not self.logos_core or not self.logos_core.http_client:
            logger.error("Chronos LLM call failed: LogosCore or its HTTP client not available.")
            return None

        api_url = f"{llm_config['url'].rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = llm_config.get('api_key')
        if api_key and api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": llm_config.get('model'),
            "messages": messages,
            "temperature": llm_config.get('temperature', 0.7),
            "max_tokens": llm_config.get('max_tokens', 350),
        }
        if not payload.get("model"):
            logger.warning(f"Chronos LLM call: 'model' key missing. Provider: {api_key}. Payload: {payload}")
            if 'model' in payload: del payload['model'] # Remove if empty, some servers might infer

        response_text_for_debug = ""
        try:
            timeout_val = float(llm_config.get('timeout', 60.0))
            response = await self.logos_core.http_client.post(api_url, headers=headers, json=payload, timeout=timeout_val)
            response_content_bytes = await response.aread()
            response_text_for_debug = response_content_bytes.decode('utf-8', errors='replace')
            response.raise_for_status()
            result_json = json.loads(response_text_for_debug)
            content_str = result_json.get("choices", [{}])[0].get("message", {}).get("content")
            if content_str:
                try:
                    cleaned_content_str = content_str.strip()
                    if cleaned_content_str.startswith("```json"): cleaned_content_str = cleaned_content_str[len("```json"):].strip()
                    if cleaned_content_str.endswith("```"): cleaned_content_str = cleaned_content_str[:-len("```")].strip()
                    parsed_json = json.loads(cleaned_content_str)
                    if isinstance(parsed_json, dict): return parsed_json
                    else: logger.warning(f"Chronos LLM returned JSON but not an object: {parsed_json}")
                except json.JSONDecodeError as e: logger.error(f"Failed to decode JSON from Chronos LLM: {e}. Cleaned: {cleaned_content_str[:500]}")
            else: logger.warning(f"Chronos LLM response content empty. Full JSON: {result_json}")
            return None
        except httpx.TimeoutException as e: logger.error(f"Chronos LLM timeout ({timeout_val}s) for {api_url}: {e}", exc_info=True); return None
        except httpx.HTTPStatusError as e: logger.error(f"Chronos LLM HTTP Error {e.response.status_code} for {api_url}. Response: {response_text_for_debug[:500]}. Error: {e}", exc_info=True); return None
        except json.JSONDecodeError as e: logger.error(f"Failed to parse initial Chronos LLM response as JSON. URL: {api_url}. Response: {response_text_for_debug[:500]}. Error: {e}", exc_info=True); return None
        except Exception as e: logger.error(f"Uncaught error in Chronos LLM call to {api_url}: {e}", exc_info=True); return None

    async def generate_activity_for_slot(
        self, slot_name: str, slot_start_time: time, slot_end_time: time,
        target_date: date, default_activity_type: ActivityType, current_event: Optional[PathosEvent]
    ) -> ActivitySlot:
        llm_config = self._get_llm_for_activity_generation()
        fallback_title = f"Engaging in {slot_name}"
        fallback_type = default_activity_type
        fallback_desc = f"Pathos is occupied with {slot_name.lower()}."

        if current_event:
            fallback_title = f"{current_event.title} - {slot_name}"
            fallback_desc = f"Participating in '{current_event.title}'. Focus: {slot_name}."
            if current_event.location: fallback_desc += f" Location: {current_event.location}."
            if current_event.details and current_event.details.activity_theme: fallback_desc += f" Theme: {current_event.details.activity_theme}."

        llm_generated_data: Optional[Dict[str, Any]] = None
        if llm_config:
            current_mood = self.ethos_core.get_current_mood()
            recent_memories = await self.ethos_core.retrieve_relevant_memories("recent user interactions or Pathos's recent thoughts", 1, PATHOS_USER_ID, ['interaction', 'queued_discussion_point'])
            context_str = f"- {recent_memories[0].get('content', '')[:100]}..." if recent_memories else "No specific recent context."
            valid_types_str = ", ".join(ActivityType.__args__) # type: ignore

            system_prompt, user_prompt = "", ""
            if current_event:
                system_prompt = "You are planning a segment of Pathos's day during a planned event. Pathos is a 47-year-old British tech consultant. Respond ONLY with the requested JSON object."
                user_prompt = f"""
Date: {target_date.isoformat()}, Slot: "{slot_name}" ({slot_start_time.isoformat(timespec='minutes')} - {slot_end_time.isoformat(timespec='minutes')})
Event: "{current_event.title}" (Type: {current_event.event_type}, Dates: {current_event.start_date} to {current_event.end_date})
Location: {current_event.location or 'N/A'}, Details: {current_event.details.model_dump_json()}
Pathos Mood: Valence {current_event.details.mood_override.get('valence', current_mood['valence']):.2f}, Arousal {current_event.details.mood_override.get('arousal', current_mood['arousal']):.2f}
Generate an activity for this slot aligning with the event. Valid Types: {valid_types_str}.
JSON Output: {{"activity_title": "Event-related title (max 10 words).", "activity_type": "chosen_type", "activity_details": {{"description": "Evocative sentence (max 25 words).", "mood_influence": {{"valence_shift": 0.X, "arousal_shift": 0.Y}}, "sub_focus": "Optional: specific event aspect", "location_context": "Optional: micro-location"}}}}
Your JSON response:"""
            else:
                system_prompt = "You are planning a segment of Pathos's day. Pathos is a 47-year-old British tech consultant (WFH). Respond ONLY with the requested JSON object."
                user_prompt = f"""
Date: {target_date.isoformat()}, Slot: "{slot_name}" ({slot_start_time.isoformat(timespec='minutes')} - {slot_end_time.isoformat(timespec='minutes')})
Pathos Mood: Valence {current_mood['valence']:.2f}, Arousal {current_mood['arousal']:.2f}, Recent Context: {context_str}
Generate an activity. Valid Types: {valid_types_str}.
JSON Output: {{"activity_title": "Engaging title (max 10 words).", "activity_type": "chosen_type", "activity_details": {{"description": "Evocative sentence (max 25 words).", "mood_influence": {{"valence_shift": 0.X, "arousal_shift": 0.Y}}, "sub_focus": "Optional: specific focus"}}}}
Your JSON response:"""
            llm_generated_data = await self._call_scheduler_llm([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], llm_config)

        if llm_generated_data and isinstance(llm_generated_data, dict):
            try:
                details_data = llm_generated_data.get('activity_details', {})
                activity_details = ActivitySlotDetails(description=details_data.get('description', fallback_desc), mood_influence=details_data.get('mood_influence'), sub_focus=details_data.get('sub_focus'), location_context=details_data.get('location_context'))
                llm_activity_type = llm_generated_data.get('activity_type', fallback_type)
                final_activity_type: ActivityType = llm_activity_type if llm_activity_type in ActivityType.__args__ else fallback_type # type: ignore
                return ActivitySlot(user_id=PATHOS_USER_ID, date=target_date, start_time=slot_start_time, end_time=slot_end_time, slot_name=slot_name, activity_title=llm_generated_data.get('activity_title', fallback_title), activity_type=final_activity_type, activity_details=activity_details)
            except Exception as e: logger.error(f"Error parsing LLM output for slot '{slot_name}': {e}. LLM Output: {llm_generated_data}", exc_info=True)

        fallback_details = ActivitySlotDetails(description=fallback_desc)
        if current_event and current_event.location: fallback_details.location_context = current_event.location
        return ActivitySlot(user_id=PATHOS_USER_ID, date=target_date, start_time=slot_start_time, end_time=slot_end_time, slot_name=slot_name, activity_title=fallback_title, activity_type=fallback_type, activity_details=fallback_details)

    async def generate_schedule_for_date(self, target_date: date) -> List[ActivitySlot]:
        new_schedule: List[ActivitySlot] = []
        current_event: Optional[PathosEvent] = None
        try:
            active_events = await self.memory_storage.get_events_for_date_range(PATHOS_USER_ID, target_date, target_date)
            current_event = active_events[0] if active_events else None
        except Exception as e: logger.error(f"Error checking events for {target_date}: {e}", exc_info=True)

        slots_template = self.event_day_slots if current_event else self.daily_slots
        default_type_prefix = "event_related" if current_event else "other"

        for slot_name, start_t, end_t, default_type_val_str in slots_template:
            default_type: ActivityType = default_type_val_str # type: ignore
            activity = await self.generate_activity_for_slot(slot_name, start_t, end_t, target_date, default_type, current_event)
            if activity: new_schedule.append(activity)
            else: # Should not happen if generate_activity_for_slot always returns a fallback
                logger.error(f"generate_activity_for_slot returned None for '{slot_name}'. This is unexpected.")
                fallback_details = ActivitySlotDetails(description=f"Fallback for {slot_name}")
                if current_event and current_event.location: fallback_details.location_context = current_event.location
                new_schedule.append(ActivitySlot(user_id=PATHOS_USER_ID, date=target_date, start_time=start_t, end_time=end_t, slot_name=slot_name, activity_title=f"Fallback: {slot_name}", activity_type=default_type, activity_details=fallback_details))

        if new_schedule:
            new_schedule.sort(key=lambda x: x.start_time)
            try: await self.memory_storage.save_schedule_to_db(new_schedule, PATHOS_USER_ID)
            except Exception as e: logger.error(f"Error saving schedule to DB for {target_date}: {e}", exc_info=True); new_schedule = []
        else: logger.warning(f"No activities generated for schedule on {target_date}.")
        return new_schedule

    async def get_current_activity(self, current_datetime: datetime) -> Optional[ActivitySlot]:
        target_date, current_time_val = current_datetime.date(), current_datetime.time()
        schedule_to_check: List[ActivitySlot] = []
        async with self._schedule_generation_lock:
            if self._cache_date == target_date and PATHOS_USER_ID in self._todays_schedule_cache and self._todays_schedule_cache[PATHOS_USER_ID]:
                schedule_to_check = self._todays_schedule_cache[PATHOS_USER_ID]
            else:
                schedule_to_check = await self.memory_storage.load_schedule_from_db(target_date, PATHOS_USER_ID)
                if not schedule_to_check: schedule_to_check = await self.generate_schedule_for_date(target_date)
                if schedule_to_check: self._todays_schedule_cache[PATHOS_USER_ID] = schedule_to_check; self._cache_date = target_date
                else: return None
        for activity in schedule_to_check:
            if activity.start_time <= current_time_val < activity.end_time: return activity
        return None

    async def get_todays_schedule_for_user(self) -> List[ActivitySlot]:
        pathos_local_now = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)
        today = pathos_local_now.date()
        async with self._schedule_generation_lock:
            if self._cache_date == today and PATHOS_USER_ID in self._todays_schedule_cache and self._todays_schedule_cache[PATHOS_USER_ID]:
                return self._todays_schedule_cache[PATHOS_USER_ID]
            schedule = await self.memory_storage.load_schedule_from_db(today, PATHOS_USER_ID)
            if not schedule: schedule = await self.generate_schedule_for_date(today)
            self._todays_schedule_cache[PATHOS_USER_ID] = schedule if schedule else []
            self._cache_date = today
            return self._todays_schedule_cache.get(PATHOS_USER_ID, [])


    async def get_upcoming_events(self, user_id: str = PATHOS_USER_ID, days_ahead: int = 7) -> List[PathosEvent]:
        pathos_local_now = await self.ethos_core.get_local_datetime_for_user(user_id)
        start_date_val, end_date_val = pathos_local_now.date(), pathos_local_now.date() + timedelta(days=days_ahead)
        return await self.memory_storage.get_events_for_date_range(user_id, start_date_val, end_date_val)

    async def add_planned_event(self, event_data: Dict[str, Any]) -> Optional[PathosEvent]:
        try:
            event_data.setdefault('user_id', PATHOS_USER_ID)
            if 'details' not in event_data or not isinstance(event_data['details'], dict): event_data['details'] = {}
            event = PathosEvent(**event_data)
            if await self.memory_storage.add_event_to_db(event):
                logger.info(f"Added planned event '{event.title}' for Pathos.")
                async with self._schedule_generation_lock:
                    current_affected_date = event.start_date
                    while current_affected_date <= event.end_date:
                        if self._cache_date == current_affected_date and PATHOS_USER_ID in self._todays_schedule_cache:
                            self._todays_schedule_cache[PATHOS_USER_ID] = [] # Invalidate by emptying
                            if self._cache_date == current_affected_date: self._cache_date = None
                        current_affected_date += timedelta(days=1)
                return event
            else: logger.error(f"Failed to add planned event '{event.title}' to DB."); return None
        except Exception as e: logger.error(f"Error adding planned event: {e}", exc_info=True); return None

    async def daily_schedule_maintenance_task(self):
        logger.debug("Chronos: Daily schedule maintenance task running.")
        pathos_local_now = await self.ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)
        today = pathos_local_now.date()
        current_schedule = await self.get_todays_schedule_for_user()
        if current_schedule: logger.info(f"Chronos: Today's ({today}) schedule for Pathos available ({len(current_schedule)} activities).")
        else: logger.warning(f"Chronos: Failed to ensure today's ({today}) schedule for Pathos is available.")