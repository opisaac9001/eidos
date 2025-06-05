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

    ACTIVITY_TYPE_TO_IMPORTANCE = {
        'work': 'high', 'intellectual': 'high',
        'event_related': 'high',
        'social': 'medium', 'learning': 'medium', 'creative': 'medium',
        'planning': 'medium', 'travel': 'medium',
        'reflective': 'low', 'leisure': 'low', 'maintenance': 'low', 'other': 'low'
    }

    def _get_slot_duration(self, slot: ActivitySlot, slot_date: Optional[date] = None) -> timedelta:
        d = slot_date or slot.date
        # Ensure start_time and end_time are valid time objects
        if not isinstance(slot.start_time, time) or not isinstance(slot.end_time, time):
            logger.error(f"Slot {slot.id} has invalid time types for duration calculation. Start: {slot.start_time}, End: {slot.end_time}")
            # Fallback to a zero duration to prevent crashes, though this indicates a data issue.
            return timedelta(0)
        return datetime.combine(d, slot.end_time) - datetime.combine(d, slot.start_time)

    def _get_slot_importance(self, slot: ActivitySlot, event_map: Dict[str, PathosEvent]) -> Literal['critical', 'high', 'medium', 'low']:
        if slot.activity_details and slot.activity_details.metadata:
            source_event_id = slot.activity_details.metadata.get('source_event_id')
            if source_event_id and source_event_id in event_map:
                event = event_map[source_event_id]
                if event.details and event.details.importance:
                    return event.details.importance # 'critical', 'high', 'medium', 'low'

        # Fallback to activity type based importance
        importance_val = self.ACTIVITY_TYPE_TO_IMPORTANCE.get(slot.activity_type, 'medium')
        if importance_val == 'critical': return 'critical' # Should not happen from this map but for type safety
        if importance_val == 'high': return 'high'
        if importance_val == 'medium': return 'medium'
        return 'low' # Default for 'low' or unknown

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
            recent_memories = await self.ethos_core.retrieve_relevant_memories("recent user interactions or Pathos's recent thoughts", 1, PATHOS_USER_ID, ['interaction', 'queued_discussion_point'])
            context_str = f"- {recent_memories[0].get('content', '')[:100]}..." if recent_memories else "No specific recent context."
            valid_types_str = ", ".join(ActivityType.__args__) # type: ignore

            system_prompt = "You are planning a segment of Pathos's day. Pathos is a 47-year-old British tech consultant. Respond ONLY with the requested JSON object."
            user_prompt_parts = [
                f"Date: {target_date.isoformat()}, Slot: "{slot_name}" ({slot_start_time.isoformat(timespec='minutes')} - {slot_end_time.isoformat(timespec='minutes')})",
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

                activity_metadata_payload = {}
                if current_event_context:
                    activity_metadata_payload["source_event_id"] = current_event_context.id

                activity_details = ActivitySlotDetails(
                    description=llm_desc,
                    mood_influence=details_data.get('mood_influence'),
                    sub_focus=current_sub_focus,
                    location_context=current_location_context,
                    flexibility_score=details_data.get('flexibility_score', 0.5), # LLM can suggest or use default
                    metadata=activity_metadata_payload
                )
                return ActivitySlot(user_id=PATHOS_USER_ID, date=target_date, start_time=slot_start_time, end_time=slot_end_time, slot_name=slot_name, activity_title=llm_title, activity_type=final_activity_type, activity_details=activity_details)
            except Exception as e: logger.error(f"Error parsing LLM output for slot '{slot_name}': {e}. LLM Output: {llm_generated_data}", exc_info=True)

        # Fallback if LLM fails or no LLM config
        activity_metadata_payload_fallback = {}
        if current_event_context:
            activity_metadata_payload_fallback["source_event_id"] = current_event_context.id

        fallback_details = ActivitySlotDetails(
            description=fallback_desc,
            sub_focus=final_sub_focus,
            location_context=final_location_context,
            metadata=activity_metadata_payload_fallback # Add metadata here too
        )
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
                logger.debug(f"Loaded schedule from cache for {target_date}")
            else:
                logger.debug(f"Cache miss for {target_date}. Loading from DB or generating.")
                schedule_to_check = await self.memory_storage.load_schedule_from_db(target_date, PATHOS_USER_ID)
                if not schedule_to_check:
                    logger.info(f"No schedule in DB for {target_date}, generating new one.")
                    schedule_to_check = await self.generate_schedule_for_date(target_date)

                if schedule_to_check:
                    self._todays_schedule_cache[PATHOS_USER_ID] = schedule_to_check
                    self._cache_date = target_date
                    logger.info(f"Populated cache for {target_date} with {len(schedule_to_check)} activities.")
                else:
                    logger.warning(f"Failed to load or generate schedule for {target_date}.")
                    return None

        current_mood = self.ethos_core.get_current_mood() # Synchronous call

        processed_schedule_for_saving = False # Flag to indicate if schedule needs re-saving

        for activity_index, activity in enumerate(schedule_to_check):
            if activity.start_time <= current_time_val < activity.end_time:
                if activity.status in ['completed', 'skipped']:
                    logger.debug(f"Activity '{activity.activity_title}' already {activity.status}. Skipping.")
                    continue # Already processed

                if activity.status == 'pending': # Check if it's actionable
                    flexibility_score_val = activity.activity_details.flexibility_score if activity.activity_details.flexibility_score is not None else 0.5
                    mood_valence_val = current_mood.get('valence', 0.0)

                    # Thresholds and Delay Duration
                    MODERATE_MOOD_VALENCE_MIN = -0.5
                    MODERATE_MOOD_VALENCE_MAX = -0.2
                    MODERATE_FLEXIBILITY_MIN = 0.4
                    MODERATE_FLEXIBILITY_MAX = 0.7
                    DELAY_DURATION = timedelta(minutes=30)

                    # New Delay Logic
                    if MODERATE_MOOD_VALENCE_MIN <= mood_valence_val < MODERATE_MOOD_VALENCE_MAX and \
                       MODERATE_FLEXIBILITY_MIN <= flexibility_score_val < MODERATE_FLEXIBILITY_MAX:

                        logger.info(f"Pathos (mood: {mood_valence_val:.2f}) is delaying moderately flexible activity '{activity.activity_title}' (flex: {flexibility_score_val:.2f}) by {DELAY_DURATION}.")

                        if activity.original_scheduled_start_time is None:
                            activity.original_scheduled_start_time = activity.start_time
                        if activity.original_scheduled_end_time is None:
                            activity.original_scheduled_end_time = activity.end_time

                        current_slot_date_for_calc = activity.date # or target_date from method params

                        new_start_dt = datetime.combine(current_slot_date_for_calc, activity.start_time) + DELAY_DURATION
                        new_end_dt = datetime.combine(current_slot_date_for_calc, activity.end_time) + DELAY_DURATION

                        activity.start_time = new_start_dt.time()
                        activity.end_time = new_end_dt.time()
                        activity.status = 'delayed'
                        activity.deviation_reason = f"mood_delay_moderate_flex_valence_{mood_valence_val:.2f}"

                        schedule_to_check[activity_index] = activity # Update in the list
                        processed_schedule_for_saving = True
                        continue # Move to the next activity in schedule_to_check

                    # Existing Skip Logic (ensure different thresholds if necessary)
                    SEVERE_NEGATIVE_MOOD_THRESHOLD = -0.5 # Assuming NEGATIVE_MOOD_THRESHOLD was for severe cases
                    HIGH_FLEXIBILITY_THRESHOLD = 0.7       # Re-affirm or use a distinct variable

                    if mood_valence_val < SEVERE_NEGATIVE_MOOD_THRESHOLD and flexibility_score_val >= HIGH_FLEXIBILITY_THRESHOLD:
                        logger.info(f"Pathos (mood: {mood_valence_val:.2f}) is skipping flexible activity '{activity.activity_title}' (flex: {flexibility_score_val:.2f}, status: {activity.status}).")
                        activity.status = 'skipped'
                        activity.deviation_reason = "mood_avoidance_low_valence_high_flexibility"
                        activity.actual_start_time = None
                        activity.actual_end_time = None
                        schedule_to_check[activity_index] = activity # Update in list
                        processed_schedule_for_saving = True
                        continue

                    # New Shorten Logic (if not delayed and not skipped by severe mood)
                    mood_arousal_val = current_mood.get('arousal', 0.0)
                    MIN_DURATION_FOR_SHORTENING = timedelta(minutes=60)
                    SHORTEN_PERCENTAGE = 0.25
                    MIN_ACTIVITY_DURATION = timedelta(minutes=15)
                    MODERATE_FLEXIBILITY_FOR_SHORTENING = 0.3

                    original_start_dt = datetime.combine(activity.date, activity.start_time)
                    original_end_dt = datetime.combine(activity.date, activity.end_time)
                    original_duration = original_end_dt - original_start_dt

                    if mood_arousal_val < current_mood.get('arousal_thresholds', {}).get('low_engagement', -0.3) and \
                       original_duration >= MIN_DURATION_FOR_SHORTENING and \
                       flexibility_score_val >= MODERATE_FLEXIBILITY_FOR_SHORTENING:

                        reduction_amount = original_duration * SHORTEN_PERCENTAGE
                        new_duration = original_duration - reduction_amount

                        if new_duration < MIN_ACTIVITY_DURATION:
                            new_duration = MIN_ACTIVITY_DURATION

                        new_end_time_dt = original_start_dt + new_duration

                        if new_end_time_dt.time() > activity.start_time and new_duration >= MIN_ACTIVITY_DURATION:
                            logger.info(f"Pathos (mood arousal: {mood_arousal_val:.2f}) is shortening activity '{activity.activity_title}' (flex: {flexibility_score_val:.2f}) from {original_duration} to {new_duration}.")

                            if activity.original_scheduled_end_time is None:
                                activity.original_scheduled_end_time = activity.end_time

                            activity.end_time = new_end_time_dt.time()
                            shorten_reason = f"mood_shorten_low_arousal_{mood_arousal_val:.2f}"
                            if activity.deviation_reason:
                                activity.deviation_reason += "; " + shorten_reason
                            else:
                                activity.deviation_reason = shorten_reason

                            schedule_to_check[activity_index] = activity
                            processed_schedule_for_saving = True

                    # Logic to set to 'in_progress' and return (this will execute if not delayed or skipped)
                    logger.info(f"Activity '{activity.activity_title}' changing status from {activity.status} to in_progress.")
                    activity.status = 'in_progress'
                    if activity.actual_start_time is None:
                        activity.actual_start_time = current_time_val
                    schedule_to_check[activity_index] = activity
                    processed_schedule_for_saving = True

                    if processed_schedule_for_saving: # This flag would be true if shortened or just started
                        async with self._schedule_generation_lock:
                            self._todays_schedule_cache[PATHOS_USER_ID] = schedule_to_check
                            await self.memory_storage.save_schedule_to_db(schedule_to_check, PATHOS_USER_ID)
                            logger.debug(f"Saved updated schedule to DB due to status/time change in get_current_activity for slot {activity.id}")
                    return activity
                elif activity.status == 'in_progress':
                    # If it was already in_progress, just return it
                    logger.debug(f"Activity '{activity.activity_title}' is already in_progress. Returning.")
                    return activity
                # Potentially handle other statuses like 'delayed' if current_time_val has caught up

        # If loop completes, no suitable activity found
        # Save the schedule if any items were skipped and no other activity was chosen
        if processed_schedule_for_saving:
            async with self._schedule_generation_lock:
                self._todays_schedule_cache[PATHOS_USER_ID] = schedule_to_check
                await self.memory_storage.save_schedule_to_db(schedule_to_check, PATHOS_USER_ID)
                logger.debug("Saved updated schedule to DB due to skipped items at end of get_current_activity.")
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

        if outcome_metadata:
            logger.debug(f"Outcome metadata received for slot {slot_id}: {outcome_metadata}")
            # Example for future: if 'deviation_reason' in outcome_metadata and not slot_to_update.deviation_reason:
            # slot_to_update.deviation_reason = outcome_metadata["deviation_reason"]
            # Or store notes in activity_details if a field like 'outcome_notes' is added to ActivitySlotDetails:
            # if hasattr(slot_to_update.activity_details, 'outcome_notes') and outcome_metadata.get("notes"):
            #    slot_to_update.activity_details.outcome_notes = outcome_metadata.get("notes")

        target_date = slot_to_update.date
        user_id = slot_to_update.user_id

        async with self._schedule_generation_lock:
            todays_schedule: List[ActivitySlot] = []
            if self._cache_date == target_date and user_id in self._todays_schedule_cache:
                todays_schedule = self._todays_schedule_cache[user_id]
                logger.debug(f"report_activity_outcome: Loaded schedule for {target_date} from cache.")
            else:
                logger.debug(f"report_activity_outcome: Cache miss for {target_date}. Loading schedule from DB to update slot {slot_id}.")
                todays_schedule = await self.memory_storage.load_schedule_from_db(target_date, user_id)

            if not todays_schedule:
                logger.warning(f"report_activity_outcome: Could not load schedule for date {target_date} to update slot {slot_id}. Attempting to save the single updated slot. This might lead to data loss for other slots on this day if they existed.")
                await self.memory_storage.save_schedule_to_db([slot_to_update], user_id)
                if self._cache_date == target_date and user_id in self._todays_schedule_cache:
                     self._todays_schedule_cache[user_id] = [slot_to_update]
                logger.info(f"Force-saved updated slot {slot_id} as single-item schedule for {target_date} due to prior load failure.")
                return

            # --- Start of Rescheduling Logic ---
            deviation = timedelta(0)
            if slot_to_update.actual_end_time and slot_to_update.end_time:
                current_slot_date = slot_to_update.date
                actual_end_datetime = datetime.combine(current_slot_date, slot_to_update.actual_end_time)
                scheduled_end_datetime = datetime.combine(current_slot_date, slot_to_update.end_time)
                deviation = actual_end_datetime - scheduled_end_datetime

            SIGNIFICANT_DEVIATION_THRESHOLD = timedelta(minutes=5)
            schedule_changed_due_to_absorption = False
            schedule_modified_by_final_shift = False
            slot_updated_in_list = False
            current_slot_index = -1

            for i, existing_slot in enumerate(todays_schedule):
                if existing_slot.id == slot_id:
                    todays_schedule[i] = slot_to_update
                    slot_updated_in_list = True
                    current_slot_index = i
                    break

            overall_schedule_has_changed = slot_updated_in_list

            if current_slot_index != -1 and abs(deviation) > SIGNIFICANT_DEVIATION_THRESHOLD:
                # Fetch event details for importance mapping if we are going to reschedule
                event_id_to_event_map: Dict[str, PathosEvent] = {}
                slot_ids_with_events = [
                    s.activity_details.metadata.get('source_event_id')
                    for s in todays_schedule
                    if s.activity_details and s.activity_details.metadata and s.activity_details.metadata.get('source_event_id')
                ]
                if slot_ids_with_events:
                    try:
                        # This assumes memory_storage can fetch multiple events by ID efficiently if such a method exists.
                        # For now, we'll fetch one by one if needed inside _get_slot_importance or pre-fetch if only a few.
                        # For simplicity, _get_slot_importance will handle individual fetches if event_map is not pre-populated.
                        # However, the provided _get_slot_importance expects event_map. So, let's build it.
                        unique_event_ids = list(set(slot_ids_with_events))
                        for event_id_to_fetch in unique_event_ids:
                            event = await self.memory_storage.get_event_by_id(event_id_to_fetch)
                            if event:
                                event_id_to_event_map[event_id_to_fetch] = event
                    except Exception as e_fetch_events:
                        logger.error(f"Error fetching event details for rescheduling logic: {e_fetch_events}")


                if deviation > timedelta(0): # Lost time
                    time_to_absorb = deviation
                    logger.info(f"Slot {slot_id} created positive deviation: {time_to_absorb}. Attempting absorption.")

                    HIGH_FLEXIBILITY_THRESHOLD = 0.8
                    MIN_SLOT_DURATION_AFTER_SHORTEN = timedelta(minutes=15)

                    for i in range(current_slot_index + 1, len(todays_schedule)):
                        slot_eval = todays_schedule[i]
                        if time_to_absorb <= timedelta(0): break
                        if not (slot_eval.status == 'pending' or slot_eval.status == 'delayed'): continue

                        importance = self._get_slot_importance(slot_eval, event_id_to_event_map)
                        flexibility = slot_eval.activity_details.flexibility_score if slot_eval.activity_details.flexibility_score is not None else 0.5

                        if importance == 'low' and flexibility >= HIGH_FLEXIBILITY_THRESHOLD:
                            slot_duration = self._get_slot_duration(slot_eval)
                            if time_to_absorb >= slot_duration: # Skip
                                logger.info(f"Skipping low-importance, high-flex slot '{slot_eval.activity_title}' (duration: {slot_duration}) to absorb delay.")
                                time_to_absorb -= slot_duration
                                slot_eval.status = 'skipped'
                                slot_eval.deviation_reason = (slot_eval.deviation_reason or "") + f";skipped_to_absorb_delay_from_{slot_id}"
                                slot_eval.actual_start_time = None; slot_eval.actual_end_time = None
                                schedule_changed_due_to_absorption = True
                            else: # Shorten
                                original_end_t = slot_eval.end_time
                                new_end_dt_abs = datetime.combine(slot_eval.date, slot_eval.end_time) - time_to_absorb
                                if (datetime.combine(slot_eval.date, slot_eval.start_time) + MIN_SLOT_DURATION_AFTER_SHORTEN) <= new_end_dt_abs:
                                    logger.info(f"Shortening low-importance, high-flex slot '{slot_eval.activity_title}' by {time_to_absorb}.")
                                    if slot_eval.original_scheduled_end_time is None: slot_eval.original_scheduled_end_time = original_end_t
                                    slot_eval.end_time = new_end_dt_abs.time()
                                    slot_eval.deviation_reason = (slot_eval.deviation_reason or "") + f";shortened_to_absorb_delay_from_{slot_id}"
                                    time_to_absorb = timedelta(0)
                                    schedule_changed_due_to_absorption = True

                    if schedule_changed_due_to_absorption: overall_schedule_has_changed = True

                    final_shift_deviation = time_to_absorb
                    if final_shift_deviation > timedelta(0): # If still time to push
                        logger.info(f"Remaining deviation after absorption: {final_shift_deviation}. Applying as cascading shift.")
                        last_known_end_dt = datetime.combine(slot_to_update.date, slot_to_update.actual_end_time) if slot_to_update.actual_end_time else None
                        for i in range(current_slot_index + 1, len(todays_schedule)):
                            slot_to_shift = todays_schedule[i]
                            if slot_to_shift.status == 'skipped': continue

                            orig_start_t = slot_to_shift.original_scheduled_start_time or slot_to_shift.start_time
                            orig_end_t = slot_to_shift.original_scheduled_end_time or slot_to_shift.end_time
                            current_duration = self._get_slot_duration(slot_to_shift) # Use current duration in case it was shortened

                            if slot_to_shift.original_scheduled_start_time is None: slot_to_shift.original_scheduled_start_time = slot_to_shift.start_time
                            if slot_to_shift.original_scheduled_end_time is None: slot_to_shift.original_scheduled_end_time = slot_to_shift.end_time

                            effective_start_dt = datetime.combine(slot_to_shift.date, orig_start_t)
                            if last_known_end_dt and effective_start_dt < last_known_end_dt: # If original start is now before prev slot's actual end
                                effective_start_dt = last_known_end_dt # Start immediately after

                            effective_start_dt += final_shift_deviation # Apply remaining deviation

                            slot_to_shift.start_time = effective_start_dt.time()
                            slot_to_shift.end_time = (effective_start_dt + current_duration).time()
                            if slot_to_shift.status == 'pending': slot_to_shift.status = 'delayed'
                            slot_to_shift.deviation_reason = (slot_to_shift.deviation_reason or "") + f";shifted_late_due_to_{slot_id}"
                            schedule_modified_by_final_shift = True
                            last_known_end_dt = datetime.combine(slot_to_shift.date, slot_to_shift.end_time)

                elif deviation < timedelta(0): # Gained time
                    logger.info(f"Slot {slot_id} finished {abs(deviation)} early. Shifting subsequent slots earlier.")
                    last_known_end_dt = datetime.combine(slot_to_update.date, slot_to_update.actual_end_time) if slot_to_update.actual_end_time else None
                    for i in range(current_slot_index + 1, len(todays_schedule)):
                        next_slot = todays_schedule[i]
                        if next_slot.status in ['pending', 'delayed']:
                            orig_start_t = next_slot.original_scheduled_start_time or next_slot.start_time
                            orig_end_t = next_slot.original_scheduled_end_time or next_slot.end_time
                            current_duration = datetime.combine(next_slot.date, orig_end_t) - datetime.combine(next_slot.date, orig_start_t)

                            if next_slot.original_scheduled_start_time is None: next_slot.original_scheduled_start_time = next_slot.start_time
                            if next_slot.original_scheduled_end_time is None: next_slot.original_scheduled_end_time = next_slot.end_time

                            new_start_dt = datetime.combine(next_slot.date, orig_start_t) + deviation
                            if last_known_end_dt and new_start_dt < last_known_end_dt:
                                new_start_dt = last_known_end_dt

                            next_slot.start_time = new_start_dt.time()
                            next_slot.end_time = (new_start_dt + current_duration).time()
                            if next_slot.status == 'pending': next_slot.status = 'delayed'
                            next_slot.deviation_reason = (next_slot.deviation_reason or "") + f";shifted_early_due_to_{slot_id}"
                            schedule_modified_by_final_shift = True
                            last_known_end_dt = datetime.combine(next_slot.date, next_slot.end_time)

                if schedule_modified_by_final_shift: overall_schedule_has_changed = True

            # New Event Completion Logic (placed after all schedule adjustments, before save)
            if slot_to_update.status == 'completed':
                # Ensure activity_details and metadata exist before trying to access them
                if slot_to_update.activity_details and slot_to_update.activity_details.metadata:
                    source_event_id = slot_to_update.activity_details.metadata.get('source_event_id')
                    if source_event_id and isinstance(source_event_id, str):
                        logger.debug(f"Slot {slot_to_update.id} completed, checking linked event {source_event_id} for completion.")
                        event_to_update = await self.memory_storage.get_event_by_id(source_event_id)

                        if event_to_update:
                            is_specific_timed_single_day_event = (
                                event_to_update.specific_time is not None and
                                event_to_update.start_date == slot_to_update.date and
                                event_to_update.end_date == slot_to_update.date
                            )

                            if is_specific_timed_single_day_event:
                                if event_to_update.status != 'completed':
                                    event_to_update.status = 'completed'
                                    if slot_to_update.actual_end_time:
                                        pathos_local_dt_at_event_end = datetime.combine(slot_to_update.date, slot_to_update.actual_end_time)
                                        pathos_tz_str = self.ethos_core.ethos_config.get('pathos_home_timezone', "UTC")
                                        pathos_tz = timezone.utc
                                        if ZoneInfo and pathos_tz_str.lower() != "utc":
                                            try: pathos_tz = ZoneInfo(pathos_tz_str)
                                            except Exception as e_tz: logger.warning(f"Could not resolve Pathos home timezone '{pathos_tz_str}': {e_tz}. Using UTC.")

                                        pathos_local_dt_at_event_end = pathos_local_dt_at_event_end.replace(tzinfo=pathos_tz)
                                        event_to_update.actual_end_datetime = pathos_local_dt_at_event_end.astimezone(timezone.utc)
                                        logger.info(f"Marking event {event_to_update.id} ('{event_to_update.title}') as 'completed'. Actual end UTC: {event_to_update.actual_end_datetime.isoformat()}")
                                    else:
                                        logger.warning(f"Cannot set actual_end_datetime for event {event_to_update.id}, slot's actual_end_time is None.")

                                    await self.memory_storage.add_event_to_db(event_to_update)
                        else:
                            logger.warning(f"Source event ID {source_event_id} from slot {slot_to_update.id} not found.")
                else:
                    logger.debug(f"Slot {slot_to_update.id} completed, but no activity_details.metadata or source_event_id found to link to an event.")


            # --- End of Rescheduling Logic / Event Completion ---

            if overall_schedule_has_changed: # Consolidated save condition
                await self.memory_storage.save_schedule_to_db(todays_schedule, user_id)
                logger.info(f"Saved updates for slot {slot_id} (and potentially subsequent slots/event) to DB for {target_date}.")
                if self._cache_date == target_date and user_id in self._todays_schedule_cache:
                    self._todays_schedule_cache[user_id] = todays_schedule
                    logger.debug(f"Cache updated for {target_date} after reporting outcome for slot {slot_id}.")
            else:
                # This case implies the slot_id was found by get_schedule_item_by_id, but not in the list loaded by load_schedule_from_db.
                # (and no rescheduling occurred as a consequence)
                logger.warning(f"report_activity_outcome: Slot {slot_id} was found by ID but not in its day's loaded schedule for {target_date} AND no rescheduling occurred. Attempting to save as single-item schedule.")
                await self.memory_storage.save_schedule_to_db([slot_to_update], user_id)
                if self._cache_date == target_date and user_id in self._todays_schedule_cache:
                     self._todays_schedule_cache[user_id] = [slot_to_update]
                     logger.debug(f"Cache updated after saving single slot {slot_id}.")