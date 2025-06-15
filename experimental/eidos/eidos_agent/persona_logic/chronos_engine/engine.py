import asyncio
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Optional, Dict, Any, Literal
import uuid
import json
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None # type: ignore
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

    ACTIVITY_TYPE_TO_IMPORTANCE: Dict[ActivityType, Literal['high', 'medium', 'low']] = {
        'work': 'high', 'intellectual': 'high',
        'event_related': 'high',
        'social': 'medium', 'learning': 'medium', 'creative': 'medium',
        'planning': 'medium', 'travel': 'medium',
        'reflective': 'low', 'leisure': 'low', 'maintenance': 'low', 'other': 'low'
    }

    def _get_slot_duration(self, slot: ActivitySlot) -> timedelta:
        # Ensure start_time and end_time are valid time objects
        if not isinstance(slot.start_time, time) or not isinstance(slot.end_time, time):
            logger.error(f"Slot {slot.id} has invalid time types for duration calculation. Start: {type(slot.start_time)}, End: {type(slot.end_time)}")
            return timedelta(0)
        return datetime.combine(slot.date, slot.end_time) - datetime.combine(slot.date, slot.start_time)

    def _get_slot_importance(self, slot: ActivitySlot, event_map: Dict[str, PathosEvent]) -> Literal['critical', 'high', 'medium', 'low']:
        if slot.activity_details and slot.activity_details.metadata:
            source_event_id = slot.activity_details.metadata.get('source_event_id')
            if source_event_id and source_event_id in event_map:
                event = event_map[source_event_id]
                if event.details and event.details.importance:
                    # Ensure the value is one of the allowed Literal strings
                    if event.details.importance in ['critical', 'high', 'medium', 'low']:
                        return event.details.importance
                    else:
                        logger.warning(f"Event {event.id} has invalid importance '{event.details.importance}'. Defaulting for slot {slot.id}.")

        importance_val_str = self.ACTIVITY_TYPE_TO_IMPORTANCE.get(slot.activity_type, 'medium')
        # Cast to Literal type
        if importance_val_str == 'critical': return 'critical' # Should not happen from this map
        if importance_val_str == 'high': return 'high'
        if importance_val_str == 'low': return 'low'
        return 'medium'

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
        target_date: date, default_activity_type: ActivityType,
        default_slot_location: Optional[str], # Added default_slot_location
        current_event_context: Optional[PathosEvent] # Renamed from current_event
    ) -> ActivitySlot:
        llm_config = self._get_llm_for_activity_generation()

        # Default fallback values
        fallback_title = f"Engaging in {slot_name}"
        fallback_type = default_activity_type
        fallback_desc = f"Pathos is occupied with {slot_name.lower()}."
        final_sub_focus = None
        final_location_context = default_slot_location

        if current_event_context:
            event_title = current_event_context.title
            event_subtype = current_event_context.details.event_subtype
            event_type = current_event_context.event_type

            if current_event_context.specific_time: # This is a specific timed event
                fallback_title = f"{event_title}"
                if event_subtype: fallback_title += f" ({event_subtype})"

                fallback_desc_parts = [f"Pathos is focused on the event: '{event_title}'"]
                if event_subtype: fallback_desc_parts.append(f"(Type: {event_subtype})")
                fallback_desc_parts.append(f"scheduled around {current_event_context.specific_time.strftime('%H:%M')}.")
                if current_event_context.location: fallback_desc_parts.append(f"Location: {current_event_context.location}.")
                if current_event_context.details.event_specific_data:
                    data_preview = str(current_event_context.details.event_specific_data)[:100]
                    fallback_desc_parts.append(f"Details: {data_preview}...")
                fallback_desc = " ".join(fallback_desc_parts)
                final_sub_focus = f"Event: {event_title} ({event_subtype or event_type})"
                if current_event_context.location: final_location_context = current_event_context.location

            else: # This is an all-day or multi-day event without specific time for this slot
                fallback_title = f"{event_title} - {slot_name}"
                fallback_desc = f"Participating in '{event_title}'. Focus for this slot: {slot_name}."
                if current_event_context.location: fallback_desc += f" Overall event location: {current_event_context.location}."
                if current_event_context.details.activity_theme: fallback_desc += f" Theme: {current_event_context.details.activity_theme}."
                # For all-day events, the slot's default location might be more relevant if not specified by event
                if current_event_context.location: final_location_context = current_event_context.location


        llm_generated_data: Optional[Dict[str, Any]] = None
        if llm_config:
            current_mood = self.ethos_core.get_current_mood()
            recent_memories = await self.ethos_core.retrieve_relevant_memories(query="recent user interactions or Pathos's recent thoughts", top_k=1, allowed_types=['interaction', 'queued_discussion_point'], user_id_context=PATHOS_USER_ID)
            context_str = f"- {recent_memories[0].get('content', '')[:100]}..." if recent_memories else "No specific recent context."
            valid_types_str = ", ".join(ActivityType.__args__) # type: ignore

            system_prompt = "You are planning a segment of Pathos's day. Pathos is a 47-year-old British tech consultant. Respond ONLY with the requested JSON object."
            user_prompt_parts = [
                f"Date: {target_date.isoformat()}, Slot: \"{slot_name}\" ({slot_start_time.isoformat(timespec='minutes')} - {slot_end_time.isoformat(timespec='minutes')})",
                f"Pathos Mood: Valence {current_mood['valence']:.2f}, Arousal {current_mood['arousal']:.2f}."
            ]
            if default_slot_location: user_prompt_parts.append(f"Default location for this slot: {default_slot_location}.")

            if current_event_context and current_event_context.specific_time:
                user_prompt_parts.append(f"A specific event is scheduled: '{current_event_context.title}' (Type: {current_event_context.details.event_subtype or current_event_context.event_type}) around {current_event_context.specific_time.strftime('%H:%M')}.")
                if current_event_context.location: user_prompt_parts.append(f"Event Location: {current_event_context.location}.")
                if current_event_context.details.event_specific_data:
                    user_prompt_parts.append(f"Event Details: {str(current_event_context.details.event_specific_data)[:150]}.")
                user_prompt_parts.append(f"Generate an activity title and description for the slot '{slot_name}' that aligns with or acknowledges this specific event.")
            elif current_event_context: # General event context
                user_prompt_parts.append(f"This slot falls within a general event: '{current_event_context.title}' (Type: {current_event_context.event_type}, Dates: {current_event_context.start_date} to {current_event_context.end_date}).")
                if current_event_context.location: user_prompt_parts.append(f"Overall Event Location: {current_event_context.location or 'N/A'}.")
                if current_event_context.details.model_dump_json(exclude_none=True) != '{}': user_prompt_parts.append(f"Event Details: {current_event_context.details.model_dump_json(exclude_none=True)}.")
                user_prompt_parts.append(f"Generate an activity for this slot, considering it's part of the event. Focus: {slot_name}.")
            else: # No event context
                user_prompt_parts.append(f"Recent Context: {context_str}.")
                user_prompt_parts.append("Generate a suitable activity for this time slot.")

            user_prompt_parts.append(f"Valid Activity Types: {valid_types_str}.")
            user_prompt_parts.append(f"JSON Output: {{\"activity_title\": \"Concise title (max 10 words).\", \"activity_type\": \"chosen_type\", \"activity_details\": {{\"description\": \"Evocative sentence (max 25 words).\", \"mood_influence\": {{\"valence_shift\": 0.X, \"arousal_shift\": 0.Y}}, \"sub_focus\": \"Optional: specific focus\", \"location_context\": \"Optional: specific location if different from slot default or event's\"}}}}")
            user_prompt_parts.append("Your JSON response:")
            user_prompt = "\n".join(user_prompt_parts)

            llm_generated_data = await self._call_scheduler_llm([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], llm_config)

        if llm_generated_data and isinstance(llm_generated_data, dict):
            try:
                details_data = llm_generated_data.get('activity_details', {})

                llm_title = llm_generated_data.get('activity_title', fallback_title)
                llm_desc = details_data.get('description', fallback_desc)
                llm_activity_type = llm_generated_data.get('activity_type', fallback_type)
                final_activity_type: ActivityType = llm_activity_type if llm_activity_type in ActivityType.__args__ else fallback_type # type: ignore

                llm_sub_focus = details_data.get('sub_focus')
                # Prioritize event-derived sub_focus if a specific event is active for the slot
                current_sub_focus = final_sub_focus if final_sub_focus else llm_sub_focus

                # Location logic: LLM provided > specific event location > default slot location
                llm_location_context = details_data.get('location_context')
                current_location_context = final_location_context # from event or default slot
                if llm_location_context: current_location_context = llm_location_context # LLM overrides

                activity_details = ActivitySlotDetails(
                    description=llm_desc,
                    mood_influence=details_data.get('mood_influence'),
                    sub_focus=current_sub_focus,
                    location_context=current_location_context
                )
                return ActivitySlot(user_id=PATHOS_USER_ID, date=target_date, start_time=slot_start_time, end_time=slot_end_time, slot_name=slot_name, activity_title=llm_title, activity_type=final_activity_type, activity_details=activity_details)
            except Exception as e: logger.error(f"Error parsing LLM output for slot '{slot_name}': {e}. LLM Output: {llm_generated_data}", exc_info=True)

        # Fallback if LLM fails or no LLM config
        fallback_details = ActivitySlotDetails(description=fallback_desc, sub_focus=final_sub_focus, location_context=final_location_context)
        return ActivitySlot(user_id=PATHOS_USER_ID, date=target_date, start_time=slot_start_time, end_time=slot_end_time, slot_name=slot_name, activity_title=fallback_title, activity_type=fallback_type, activity_details=fallback_details)

    async def generate_schedule_for_date(self, target_date: date) -> List[ActivitySlot]:
        new_schedule: List[ActivitySlot] = []
        active_events: List[PathosEvent] = []
        try:
            active_events = await self.memory_storage.get_events_for_date_range(PATHOS_USER_ID, target_date, target_date)
        except Exception as e: logger.error(f"Error fetching events for {target_date}: {e}", exc_info=True)

        all_day_or_multi_day_events: List[PathosEvent] = []
        timed_events_on_target_date: List[PathosEvent] = []

        for event in active_events:
            if event.specific_time and event.start_date == target_date: # Timed event for the target date
                timed_events_on_target_date.append(event)
            elif event.start_date == target_date and event.end_date == target_date and not event.specific_time: # All-day single day event
                all_day_or_multi_day_events.append(event)
            elif event.start_date != event.end_date: # Multi-day event
                 all_day_or_multi_day_events.append(event)

        timed_events_on_target_date.sort(key=lambda e: e.specific_time if e.specific_time else time.min)

        primary_event_for_template_selection = next(iter(all_day_or_multi_day_events), None)
        if not primary_event_for_template_selection: # If no all-day events, first timed event can also dictate event day
            primary_event_for_template_selection = next(iter(timed_events_on_target_date), None)

        slots_template_config_to_use = self.event_day_slots_template_config if primary_event_for_template_selection else self.default_daily_slots_config

        # Convert template config to (name, start_time, end_time, type, location_str)
        # Assuming location might be added to config or use a default like None
        # For now, I'll use a placeholder for default_slot_location_str if not in your config tuple.
        # This needs to align with your actual slots_template_config structure.
        # Let's assume your config tuples are (name, (sh,sm), (eh,em), type_val, optional_location_str)
        # If location is not there, I'll use None.

        processed_slots_template = []
        for tpl_item in slots_template_config_to_use:
            name, (sh, sm), (eh, em), type_val = tpl_item[0], tpl_item[1], tpl_item[2], tpl_item[3]
            # Placeholder: Assuming your config might not have location yet.
            # default_loc = tpl_item[4] if len(tpl_item) > 4 else None
            # The prompt example shows `default_slot_location_str` being passed, so I'll use a placeholder for it.
            # This should ideally come from your config or a sensible default.
            default_loc_placeholder = "Pathos's Home Office" if "work" in name.lower() or "office" in name.lower() else "Pathos's Home"
            if primary_event_for_template_selection and primary_event_for_template_selection.location:
                default_loc_placeholder = primary_event_for_template_selection.location # Event location overrides default

            processed_slots_template.append((name, time(sh,sm), time(eh,em), type_val, default_loc_placeholder))


        for slot_name, start_t, end_t, default_type_val_str, default_slot_location_str in processed_slots_template:
            specific_event_for_this_slot: Optional[PathosEvent] = None
            for timed_event in timed_events_on_target_date:
                if timed_event.specific_time and start_t <= timed_event.specific_time < end_t:
                    specific_event_for_this_slot = timed_event
                    # Remove the event so it's not considered for subsequent slots if it's short.
                    # Or handle this by ensuring events are only matched once / most relevantly.
                    # For now, first match wins for the slot.
                    break

            event_context_to_pass = specific_event_for_this_slot if specific_event_for_this_slot else primary_event_for_template_selection

            default_type: ActivityType = default_type_val_str # type: ignore
            activity = await self.generate_activity_for_slot(
                slot_name=slot_name, slot_start_time=start_t, slot_end_time=end_t,
                target_date=target_date, default_activity_type=default_type,
                default_slot_location=default_slot_location_str, # Pass it here
                current_event_context=event_context_to_pass
            )
            if activity: new_schedule.append(activity)
            else:
                logger.error(f"generate_activity_for_slot returned None for '{slot_name}'. This is unexpected.")
                # Simplified fallback, ensure ActivitySlotDetails is always created
                fallback_details_desc = f"Scheduled: {slot_name}"
                if event_context_to_pass: fallback_details_desc = f"{event_context_to_pass.title} - {slot_name}"

                final_fallback_location = default_slot_location_str
                if event_context_to_pass and event_context_to_pass.location:
                    final_fallback_location = event_context_to_pass.location

                fallback_details = ActivitySlotDetails(description=fallback_details_desc, location_context=final_fallback_location)
                new_schedule.append(ActivitySlot(user_id=PATHOS_USER_ID, date=target_date, start_time=start_t, end_time=end_t, slot_name=slot_name, activity_title=f"Fallback: {slot_name}", activity_type=default_type, activity_details=fallback_details))

        if new_schedule:
            new_schedule.sort(key=lambda x: x.start_time)
            try: await asyncio.to_thread(self.memory_storage.save_schedule_to_db, new_schedule, PATHOS_USER_ID)
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
                schedule_to_check = await asyncio.to_thread(self.memory_storage.load_schedule_from_db, target_date, PATHOS_USER_ID)
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
            schedule = await asyncio.to_thread(self.memory_storage.load_schedule_from_db, today, PATHOS_USER_ID)
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

    async def report_activity_outcome(self,
                                    slot_id: str,
                                    actual_end_time: time,
                                    status: Literal['completed', 'partially_completed', 'interrupted'],
                                    outcome_metadata: Optional[Dict[str, Any]] = None):
        logger.info(f"Reporting outcome for slot_id: {slot_id}. Status: {status}, Actual End Time: {actual_end_time.isoformat() if actual_end_time else 'N/A'}. Outcome Metadata: {outcome_metadata}")

        slot_to_update = await self.memory_storage.get_schedule_item_by_id(slot_id)

        if not slot_to_update:
            logger.warning(f"report_activity_outcome: ActivitySlot with ID '{slot_id}' not found. Cannot update outcome.")
            return

        slot_to_update.actual_end_time = actual_end_time
        slot_to_update.status = status

        if outcome_metadata and isinstance(outcome_metadata, dict):
            if "deviation_reason" in outcome_metadata and outcome_metadata["deviation_reason"]:
                slot_to_update.deviation_reason = (slot_to_update.deviation_reason + "; " if slot_to_update.deviation_reason else "") + str(outcome_metadata["deviation_reason"])
            logger.debug(f"Outcome metadata processed for slot {slot_id}: {outcome_metadata}")

        target_date = slot_to_update.date
        user_id = slot_to_update.user_id

        async with self._schedule_generation_lock:
            todays_schedule: List[ActivitySlot] = await self.memory_storage.load_schedule_from_db(target_date, user_id)

            if not todays_schedule:
                logger.warning(f"report_activity_outcome: Could not load schedule for date {target_date} to update slot {slot_id}. Saving only the updated slot.")
                await asyncio.to_thread(self.memory_storage.save_schedule_to_db, [slot_to_update], user_id)
                if self._cache_date == target_date and user_id in self._todays_schedule_cache:
                     self._todays_schedule_cache[user_id] = [slot_to_update]
                return

            current_slot_index = -1
            slot_updated_in_list = False
            for i, s in enumerate(todays_schedule):
                if s.id == slot_id:
                    todays_schedule[i] = slot_to_update
                    current_slot_index = i
                    slot_updated_in_list = True
                    break

            if not slot_updated_in_list:
                 logger.error(f"report_activity_outcome: Slot {slot_id} found by ID but not in loaded daily schedule for {target_date}. Appending and saving.")
                 todays_schedule.append(slot_to_update)
                 todays_schedule.sort(key=lambda s: s.start_time) # Ensure order

            overall_schedule_has_changed = slot_updated_in_list

            deviation = timedelta(0)
            if slot_to_update.actual_end_time and slot_to_update.end_time:
                actual_end_dt = datetime.combine(slot_to_update.date, slot_to_update.actual_end_time)
                scheduled_end_dt = datetime.combine(slot_to_update.date, slot_to_update.end_time)
                deviation = actual_end_dt - scheduled_end_dt

            SIGNIFICANT_DEVIATION_THRESHOLD = timedelta(minutes=5)
            final_processing_shift_needed = deviation # Initialize with original deviation

            if current_slot_index != -1 and abs(deviation) > SIGNIFICANT_DEVIATION_THRESHOLD:
                event_id_to_event_map: Dict[str, PathosEvent] = {}
                source_event_ids = list(set(
                    s.activity_details.metadata.get('source_event_id')
                    for s in todays_schedule
                    if s.activity_details and s.activity_details.metadata and s.activity_details.metadata.get('source_event_id')
                ))
                for event_id_str in source_event_ids:
                    if event_id_str:
                        event = await self.memory_storage.get_event_by_id(event_id_str)
                        if event: event_id_to_event_map[event_id_str] = event

                if deviation > timedelta(0): # Lost time
                    time_to_absorb = deviation
                    logger.info(f"Slot {slot_id} created positive deviation: {time_to_absorb}. Attempting absorption based on importance.")
                    HIGH_FLEXIBILITY_THRESHOLD_ABSORB = 0.8
                    MIN_SLOT_DURATION_AFTER_SHORTEN = timedelta(minutes=15)
                    schedule_changed_due_to_absorption = False

                    for i in range(current_slot_index + 1, len(todays_schedule)):
                        slot_eval = todays_schedule[i]
                        if time_to_absorb <= timedelta(0): break
                        if not (slot_eval.status == 'pending' or slot_eval.status == 'delayed'): continue

                        importance = self._get_slot_importance(slot_eval, event_id_to_event_map)
                        flexibility = slot_eval.activity_details.flexibility_score if slot_eval.activity_details.flexibility_score is not None else 0.5

                        if importance == 'low' and flexibility >= HIGH_FLEXIBILITY_THRESHOLD_ABSORB:
                            slot_duration_val = self._get_slot_duration(slot_eval)
                            if time_to_absorb >= slot_duration_val:
                                logger.info(f"Skipping low-importance, high-flex slot '{slot_eval.activity_title}' (duration: {slot_duration_val}) to absorb delay from {slot_id}.")
                                time_to_absorb -= slot_duration_val
                                slot_eval.status = 'skipped'; slot_eval.deviation_reason = (slot_eval.deviation_reason or "") + f";skipped_to_absorb_from_{slot_id}"
                                slot_eval.actual_start_time = None; slot_eval.actual_end_time = None
                                schedule_changed_due_to_absorption = True
                            else:
                                original_end_t = slot_eval.end_time
                                new_end_dt_abs = datetime.combine(slot_eval.date, slot_eval.end_time) - time_to_absorb
                                if (datetime.combine(slot_eval.date, slot_eval.start_time) + MIN_SLOT_DURATION_AFTER_SHORTEN) <= new_end_dt_abs:
                                    logger.info(f"Shortening low-importance, high-flex slot '{slot_eval.activity_title}' by {time_to_absorb} from {slot_id}.")
                                    if slot_eval.original_scheduled_end_time is None: slot_eval.original_scheduled_end_time = original_end_t
                                    slot_eval.end_time = new_end_dt_abs.time()
                                    slot_eval.deviation_reason = (slot_eval.deviation_reason or "") + f";shortened_to_absorb_from_{slot_id}"
                                    time_to_absorb = timedelta(0)
                                    schedule_changed_due_to_absorption = True
                    if schedule_changed_due_to_absorption: overall_schedule_has_changed = True
                    final_processing_shift_needed = time_to_absorb # Update shift needed with remaining time_to_absorb

                elif deviation < timedelta(0): # Time was gained
                    gained_time = abs(deviation)
                    POSITIVE_MOOD_VALENCE_THRESHOLD = 0.3
                    EXTENDABLE_ACTIVITY_TYPES = {'leisure', 'creative', 'reflective', 'learning'}
                    HIGH_FLEXIBILITY_FOR_EXTENSION = 0.6
                    MAX_EXTENSION_MINUTES_PER_SLOT = 30
                    MAX_TOTAL_GAINED_TIME_FOR_EXTENSIONS_PERCENTAGE = 0.75
                    MIN_EXTENSION_DURATION = timedelta(minutes=5)

                    time_allocatable_for_extensions = gained_time * MAX_TOTAL_GAINED_TIME_FOR_EXTENSIONS_PERCENTAGE
                    time_used_for_extensions = timedelta(0)
                    schedule_modified_by_extensions = False

                    current_mood = self.ethos_core.get_current_mood()
                    logger.info(f"Time gained: {gained_time}. Mood valence: {current_mood.get('valence',0.0):.2f}. Max allocatable for extensions: {time_allocatable_for_extensions}.")

                    if current_mood.get('valence', 0.0) > POSITIVE_MOOD_VALENCE_THRESHOLD:
                        for i_ext in range(current_slot_index + 1, len(todays_schedule)):
                            next_slot_to_extend = todays_schedule[i_ext]
                            if time_used_for_extensions >= time_allocatable_for_extensions or \
                               (time_allocatable_for_extensions - time_used_for_extensions) < MIN_EXTENSION_DURATION:
                                break
                            if next_slot_to_extend.status in ['pending', 'delayed']:
                                flexibility = next_slot_to_extend.activity_details.flexibility_score if next_slot_to_extend.activity_details.flexibility_score is not None else 0.5
                                is_extendable_type = next_slot_to_extend.activity_type in EXTENDABLE_ACTIVITY_TYPES
                                if is_extendable_type or flexibility >= HIGH_FLEXIBILITY_FOR_EXTENSION:
                                    potential_extension = min(
                                        time_allocatable_for_extensions - time_used_for_extensions,
                                        timedelta(minutes=MAX_EXTENSION_MINUTES_PER_SLOT)
                                    )
                                    if potential_extension >= MIN_EXTENSION_DURATION:
                                        logger.info(f"Extending slot '{next_slot_to_extend.activity_title}' (ID: {next_slot_to_extend.id}) by {potential_extension}.")
                                        if next_slot_to_extend.original_scheduled_end_time is None:
                                            next_slot_to_extend.original_scheduled_end_time = next_slot_to_extend.end_time
                                        new_end_dt = datetime.combine(next_slot_to_extend.date, next_slot_to_extend.end_time) + potential_extension
                                        next_slot_to_extend.end_time = new_end_dt.time()
                                        ext_reason = f"extended_mood_gain_{int(potential_extension.total_seconds()//60)}m"
                                        next_slot_to_extend.deviation_reason = (next_slot_to_extend.deviation_reason or "") + ("; " if next_slot_to_extend.deviation_reason else "") + ext_reason
                                        schedule_modified_by_extensions = True
                                        time_used_for_extensions += potential_extension
                        if schedule_modified_by_extensions: overall_schedule_has_changed = True
                    final_processing_shift_needed = deviation + time_used_for_extensions
                    logger.info(f"Original gained time: {deviation}. Time used for extensions: {time_used_for_extensions}. Final shift for subsequent tasks: {final_processing_shift_needed}")

                # Final Cascading Shift Logic
                if abs(final_processing_shift_needed) > timedelta(microseconds=1):
                    logger.info(f"Applying final shift of {final_processing_shift_needed} to subsequent slots after slot {slot_id}.")
                    last_effective_end_dt = datetime.combine(slot_to_update.date, slot_to_update.actual_end_time) if slot_to_update.actual_end_time else None

                    for i in range(current_slot_index + 1, len(todays_schedule)):
                        slot_to_shift = todays_schedule[i]
                        if slot_to_shift.status == 'skipped': continue

                        original_start_t = slot_to_shift.original_scheduled_start_time or slot_to_shift.start_time
                        # Use current duration, as it might have been extended or shortened already
                        slot_duration = self._get_slot_duration(slot_to_shift)

                        if slot_to_shift.original_scheduled_start_time is None: slot_to_shift.original_scheduled_start_time = slot_to_shift.start_time
                        if slot_to_shift.original_scheduled_end_time is None: slot_to_shift.original_scheduled_end_time = slot_to_shift.end_time

                        new_start_dt = datetime.combine(slot_to_shift.date, original_start_t) + final_processing_shift_needed

                        if last_effective_end_dt and new_start_dt < last_effective_end_dt :
                             new_start_dt = last_effective_end_dt

                        slot_to_shift.start_time = new_start_dt.time()
                        slot_to_shift.end_time = (new_start_dt + slot_duration).time()

                        if slot_to_shift.status == 'pending': slot_to_shift.status = 'delayed'
                        shift_type = 'late' if final_processing_shift_needed > timedelta(0) else 'early'
                        slot_to_shift.deviation_reason = (slot_to_shift.deviation_reason or "") + f";shifted_{shift_type}_due_to_{slot_id}"
                        overall_schedule_has_changed = True
                        last_effective_end_dt = datetime.combine(slot_to_shift.date, slot_to_shift.end_time)

            # Event Completion Logic
            if slot_to_update.status == 'completed':
                if slot_to_update.activity_details and slot_to_update.activity_details.metadata:
                    source_event_id = slot_to_update.activity_details.metadata.get('source_event_id')
                    if source_event_id and isinstance(source_event_id, str):
                        event_to_update = await self.memory_storage.get_event_by_id(source_event_id)
                        if event_to_update and event_to_update.status != 'completed':
                            is_specific_timed_single_day_event = (
                                event_to_update.specific_time is not None and
                                event_to_update.start_date == slot_to_update.date and
                                event_to_update.end_date == slot_to_update.date
                            )
                            if is_specific_timed_single_day_event:
                                logger.info(f"Marking specific timed event {event_to_update.id} ('{event_to_update.title}') as 'completed'.")
                                event_to_update.status = 'completed'
                                if slot_to_update.actual_end_time:
                                    pathos_local_dt_at_event_end = datetime.combine(slot_to_update.date, slot_to_update.actual_end_time)
                                    pathos_tz_str = self.ethos_core.ethos_config.get('pathos_home_timezone', "UTC")
                                    pathos_tz = timezone.utc
                                    if ZoneInfo and pathos_tz_str.lower() != "utc":
                                        try: pathos_tz = ZoneInfo(pathos_tz_str)
                                        except Exception as e_tz: logger.warning(f"Could not resolve TZ '{pathos_tz_str}': {e_tz}. Using UTC.")
                                    pathos_local_dt_at_event_end = pathos_local_dt_at_event_end.replace(tzinfo=pathos_tz)
                                    event_to_update.actual_end_datetime = pathos_local_dt_at_event_end.astimezone(timezone.utc)
                                await self.memory_storage.add_event_to_db(event_to_update)
                            else:
                                logger.debug(f"Checking complex event {event_to_update.id} ('{event_to_update.title}') for completion.")
                                related_slots = await asyncio.to_thread(
                                    self.memory_storage.get_slots_for_event,
                                    event_id=event_to_update.id,
                                    user_id=event_to_update.user_id,
                                    event_start_date=event_to_update.start_date,
                                    event_end_date=event_to_update.end_date
                                )
                                if related_slots:
                                    all_relevant_slots_done = True
                                    latest_completion_datetime_utc = None
                                    found_current_in_related = False
                                    for i, rs in enumerate(related_slots):
                                        if rs.id == slot_to_update.id:
                                            related_slots[i] = slot_to_update; found_current_in_related = True
                                    if not found_current_in_related: related_slots.append(slot_to_update)

                                    for r_slot in related_slots:
                                        if r_slot.status not in ['completed', 'skipped']:
                                            all_relevant_slots_done = False; break
                                        if r_slot.status == 'completed' and r_slot.actual_end_time:
                                            slot_end_dt_local = datetime.combine(r_slot.date, r_slot.actual_end_time)
                                            pathos_tz_str = self.ethos_core.ethos_config.get('pathos_home_timezone', "UTC")
                                            pathos_tz = timezone.utc
                                            if ZoneInfo and pathos_tz_str.lower() != "utc":
                                                try: pathos_tz = ZoneInfo(pathos_tz_str)
                                                except Exception: pass
                                            slot_end_dt_aware_local = slot_end_dt_local.replace(tzinfo=pathos_tz)
                                            slot_end_dt_utc = slot_end_dt_aware_local.astimezone(timezone.utc)
                                            if latest_completion_datetime_utc is None or slot_end_dt_utc > latest_completion_datetime_utc:
                                                latest_completion_datetime_utc = slot_end_dt_utc

                                    if all_relevant_slots_done:
                                        logger.info(f"All slots for complex event {event_to_update.id} done. Marking event 'completed'.")
                                        event_to_update.status = 'completed'
                                        if latest_completion_datetime_utc:
                                            event_to_update.actual_end_datetime = latest_completion_datetime_utc
                                        elif slot_to_update.actual_end_time:
                                            fallback_end_dt_local = datetime.combine(slot_to_update.date, slot_to_update.actual_end_time)
                                            pathos_tz_str = self.ethos_core.ethos_config.get('pathos_home_timezone', "UTC")
                                            pathos_tz = timezone.utc
                                            if ZoneInfo and pathos_tz_str.lower() != "utc":
                                                try: pathos_tz = ZoneInfo(pathos_tz_str)
                                                except Exception: pass
                                            fallback_end_dt_aware_local = fallback_end_dt_local.replace(tzinfo=pathos_tz)
                                            event_to_update.actual_end_datetime = fallback_end_dt_aware_local.astimezone(timezone.utc)
                                        await self.memory_storage.add_event_to_db(event_to_update)
                        elif event_to_update is None: logger.warning(f"Source event {source_event_id} not found.")
                else: logger.debug(f"Slot {slot_to_update.id} completed, but no source_event_id in metadata.")

            if overall_schedule_has_changed:
                await asyncio.to_thread(self.memory_storage.save_schedule_to_db, todays_schedule, user_id)
                logger.info(f"Saved updates for slot {slot_id} (and potentially subsequent slots/event) to DB for {target_date}.")
                if self._cache_date == target_date and user_id in self._todays_schedule_cache:
                    self._todays_schedule_cache[user_id] = todays_schedule
                    logger.debug(f"Cache updated for {target_date} after reporting outcome for slot {slot_id}.")
            else:
                logger.warning(f"report_activity_outcome: No changes made to schedule for slot {slot_id} on {target_date}.")


    async def report_spontaneous_activity(self,
                                        user_id: str,
                                        current_slot_id_if_any: Optional[str],
                                        new_activity_title: str,
                                        new_activity_description: str,
                                        estimated_duration: timedelta,
                                        new_activity_type: ActivityType = 'other',
                                        new_activity_location: Optional[str] = None) -> Optional[ActivitySlot]:

        now_local_dt = await self.ethos_core.get_local_datetime_for_user(user_id)
        current_date_val = now_local_dt.date()
        current_time_val = now_local_dt.time()

        if current_slot_id_if_any:
            logger.info(f"Spontaneous activity '{new_activity_title}' is interrupting current slot {current_slot_id_if_any}.")
            await self.report_activity_outcome(
                slot_id=current_slot_id_if_any,
                actual_end_time=current_time_val,
                status='interrupted',
                outcome_metadata={"reason": f"interrupted_by_spontaneous: {new_activity_title[:50]}"}
            )

        new_slot_start_time = current_time_val
        new_slot_start_datetime = datetime.combine(current_date_val, new_slot_start_time)
        new_slot_end_datetime = new_slot_start_datetime + estimated_duration
        new_slot_end_time = new_slot_end_datetime.time()

        spontaneous_slot_details = ActivitySlotDetails(
            description=new_activity_description,
            location_context=new_activity_location,
            flexibility_score=0.6, # Default moderate flexibility
            metadata={"source": "spontaneous_firmament", "original_title_request": new_activity_title}
        )

        new_spontaneous_slot = ActivitySlot(
            id=f"slot_{uuid.uuid4().hex}",
            user_id=user_id, date=current_date_val,
            start_time=new_slot_start_time, end_time=new_slot_end_time,
            slot_name=f"Spontaneous: {new_activity_title[:30]}",
            activity_title=new_activity_title, activity_type=new_activity_type,
            activity_details=spontaneous_slot_details,
            status='in_progress', actual_start_time=new_slot_start_time,
            deviation_reason='spontaneous_activity'
        )
        logger.info(f"Created new spontaneous slot: {new_spontaneous_slot.id} ('{new_spontaneous_slot.activity_title}') from {new_spontaneous_slot.start_time} to {new_spontaneous_slot.end_time}")

        async with self._schedule_generation_lock:
            todays_schedule = await self.memory_storage.load_schedule_from_db(current_date_val, user_id)

            final_schedule_for_day: List[ActivitySlot] = []
            spontaneous_slot_inserted = False

            for existing_slot in todays_schedule:
                overlap = (existing_slot.start_time < new_spontaneous_slot.end_time and
                           existing_slot.end_time > new_spontaneous_slot.start_time)

                if overlap:
                    logger.info(f"Spontaneous slot {new_spontaneous_slot.id} conflicts with existing slot {existing_slot.id} ('{existing_slot.activity_title}'). Marking existing as 'skipped'.")
                    existing_slot.status = 'skipped'
                    existing_slot.deviation_reason = (existing_slot.deviation_reason + "; " if existing_slot.deviation_reason else "") + f"superseded_by_spontaneous_{new_spontaneous_slot.id}"
                    existing_slot.actual_start_time = None
                    existing_slot.actual_end_time = None
                    final_schedule_for_day.append(existing_slot)
                else:
                    if existing_slot.end_time <= new_spontaneous_slot.start_time:
                        final_schedule_for_day.append(existing_slot)
                    elif existing_slot.start_time >= new_spontaneous_slot.end_time:
                        if not spontaneous_slot_inserted:
                            final_schedule_for_day.append(new_spontaneous_slot)
                            spontaneous_slot_inserted = True
                        final_schedule_for_day.append(existing_slot)
                    else:
                        final_schedule_for_day.append(existing_slot)


            if not spontaneous_slot_inserted:
                final_schedule_for_day.append(new_spontaneous_slot)

            final_schedule_for_day.sort(key=lambda s: s.start_time)

            await asyncio.to_thread(self.memory_storage.save_schedule_to_db, final_schedule_for_day, user_id)
            self._todays_schedule_cache[user_id] = final_schedule_for_day
            self._cache_date = current_date_val
            logger.info(f"Integrated spontaneous slot {new_spontaneous_slot.id} into schedule for {current_date_val} and saved.")

        return new_spontaneous_slot