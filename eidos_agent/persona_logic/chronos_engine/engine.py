import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Union
import uuid
import json
from pathlib import Path

from eidos_agent.core.config import Config
from eidos_agent.persona_logic.chronos_engine.models import (
    ActivitySlot, ActivityType, ActivityDetails, RecurrenceRule,
    ScheduleChangeRequest, ScheduleChangeResponse, PATHOS_USER_ID
)
# Assuming EthosCore might be needed for time zone conversion or schedule persistence
# from eidos_agent.persona_logic.ethos_core.core import EthosCore # Avoid direct import if possible, pass as dependency

from eidos_agent.utils.logger import get_logger

# Attempt to use zoneinfo for timezone handling if available
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None # type: ignore
    # Fallback to pytz or handle timezone naively if zoneinfo is not available
    try:
        import pytz
    except ImportError:
        pytz = None # type: ignore

logger = get_logger(__name__)

# Define the path for persisting the schedule (example)
SCHEDULE_FILE_DIR = Path.home() / ".eidos_agent" / "data"
SCHEDULE_FILE_PATH = SCHEDULE_FILE_DIR / "pathos_schedule.json"


class ChronosEngine:
    def __init__(self, config: Config, ethos_core): # ethos_core type hint 'EthosCore'
        self.config = config
        self.ethos_core = ethos_core # Store EthosCore for timezone and potentially memory storage

        # In-memory schedule storage: Dict[user_id, List[ActivitySlot]]
        self._schedule: Dict[str, List[ActivitySlot]] = {}

        # Ensure the directory for the schedule file exists
        SCHEDULE_FILE_DIR.mkdir(parents=True, exist_ok=True)

        self._load_schedule_from_file()
        logger.info("ChronosEngine initialized.")

    def _get_pathos_home_timezone_str(self) -> str:
        """Gets Pathos's home timezone string from EthosCore's config."""
        if self.ethos_core and hasattr(self.ethos_core, 'ethos_config'):
            return self.ethos_core.ethos_config.get('pathos_home_timezone', "UTC")
        return "UTC"

    async def _get_pathos_local_datetime(self, dt_utc: Optional[datetime] = None) -> datetime:
        """Converts a UTC datetime to Pathos's local time, or gets current local time."""
        if not self.ethos_core:
            logger.warning("ChronosEngine: EthosCore not available for timezone conversion. Defaulting to UTC.")
            return dt_utc if dt_utc else datetime.now(timezone.utc)

        # This relies on EthosCore.get_local_datetime_for_user which itself handles Pathos's timezone
        # If dt_utc is provided, we need a way to convert it.
        # EthosCore.get_local_datetime_for_user(PATHOS_USER_ID) returns *current* local time.
        # We need a utility that converts a given UTC time to Pathos's local time.

        pathos_tz_str = self._get_pathos_home_timezone_str()

        if not dt_utc:
            dt_utc = datetime.now(timezone.utc)

        if pathos_tz_str.lower() == "utc":
            return dt_utc

        target_tz = None
        if ZoneInfo:
            try:
                target_tz = ZoneInfo(pathos_tz_str)
            except Exception:
                logger.warning(f"ChronosEngine: Could not load ZoneInfo for '{pathos_tz_str}'. Using UTC.")
                return dt_utc
        elif pytz:
            try:
                target_tz = pytz.timezone(pathos_tz_str)
            except Exception:
                logger.warning(f"ChronosEngine: Could not load pytz timezone for '{pathos_tz_str}'. Using UTC.")
                return dt_utc
        else:
            logger.warning("ChronosEngine: No timezone library (ZoneInfo or pytz) available. Using UTC.")
            return dt_utc

        return dt_utc.astimezone(target_tz)

    def _save_schedule_to_file(self):
        """Saves the current in-memory schedule to a JSON file."""
        logger.debug(f"ChronosEngine: Saving schedule to {SCHEDULE_FILE_PATH}")
        try:
            # Pydantic models need to be converted to dicts for JSON serialization,
            # especially datetime objects.
            schedule_to_save = {}
            for user_id, activities in self._schedule.items():
                schedule_to_save[user_id] = [activity.model_dump(mode='json') for activity in activities]

            with open(SCHEDULE_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(schedule_to_save, f, indent=4)
            logger.info(f"ChronosEngine: Schedule saved successfully to {SCHEDULE_FILE_PATH}.")
        except IOError as e:
            logger.error(f"ChronosEngine: Error saving schedule to file {SCHEDULE_FILE_PATH}: {e}", exc_info=True)
        except TypeError as e:
            logger.error(f"ChronosEngine: Error serializing schedule for saving: {e}", exc_info=True)


    def _load_schedule_from_file(self):
        """Loads the schedule from a JSON file into memory."""
        if not SCHEDULE_FILE_PATH.is_file():
            logger.info(f"ChronosEngine: Schedule file {SCHEDULE_FILE_PATH} not found. Starting with an empty schedule.")
            # Create a default schedule for Pathos if none exists
            self._create_default_pathos_schedule()
            self._save_schedule_to_file() # Save the default schedule
            return

        logger.debug(f"ChronosEngine: Loading schedule from {SCHEDULE_FILE_PATH}")
        try:
            with open(SCHEDULE_FILE_PATH, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)

            self._schedule.clear() # Clear current in-memory schedule
            for user_id, activities_data in loaded_data.items():
                self._schedule[user_id] = []
                for activity_dict in activities_data:
                    try:
                        # Ensure datetime fields are parsed correctly from ISO strings
                        # Pydantic should handle this if mode='json' was used for dumping
                        # and models have datetime types.
                        activity_slot = ActivitySlot(**activity_dict)
                        self._schedule[user_id].append(activity_slot)
                    except Exception as e_parse: # Catch Pydantic validation errors or other issues
                        logger.warning(f"ChronosEngine: Error parsing activity slot for user '{user_id}' from file: {e_parse}. Data: {activity_dict}")

            logger.info(f"ChronosEngine: Schedule loaded successfully from {SCHEDULE_FILE_PATH}. Loaded for {len(self._schedule)} users.")

            # If Pathos's schedule is missing after load, create default one
            if PATHOS_USER_ID not in self._schedule or not self._schedule[PATHOS_USER_ID]:
                logger.info(f"ChronosEngine: Pathos's schedule not found or empty after loading. Creating default schedule.")
                self._create_default_pathos_schedule()
                self._save_schedule_to_file()

        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"ChronosEngine: Error loading schedule from file {SCHEDULE_FILE_PATH}: {e}. Starting with empty schedule.", exc_info=True)
            self._schedule = {} # Reset to empty on error
            self._create_default_pathos_schedule() # Attempt to create default after error
            self._save_schedule_to_file()


    def _create_default_pathos_schedule(self):
        """Creates a basic default schedule for Pathos if none exists."""
        logger.info("ChronosEngine: Creating a default schedule for Pathos.")
        if PATHOS_USER_ID not in self._schedule:
            self._schedule[PATHOS_USER_ID] = []

        # Get Pathos's current local "today" to base the schedule on
        # This needs to be careful if EthosCore isn't fully ready during init.
        # For default schedule, we might assume UTC for simplicity or make it relative.

        # For simplicity, let's make default times relative to a generic day,
        # assuming ChronosEngine will interpret them for the *actual* current day
        # when get_todays_schedule_for_user is called.
        # The datetimes stored should be full datetime objects for a reference date.

        # Let's use today UTC as the reference for creating default schedule slots.
        # When get_todays_schedule is called, it will adjust these to the target day.

        today_ref_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        default_activities = [
            {"title": "Morning Routine & Breakfast", "type": ActivityType.PERSONAL_CARE, "start_hour": 7, "end_hour": 8, "details": {"description": "Hygiene, get dressed, prepare and eat breakfast."}},
            {"title": "Focused Work Block 1", "type": ActivityType.WORK, "start_hour": 9, "end_hour": 12, "details": {"description": "Deep work on primary tasks.", "location_hint": "PathosOffice"}},
            {"title": "Lunch Break", "type": ActivityType.MEAL, "start_hour": 12, "end_hour": 13, "details": {"description": "Prepare and eat lunch, short break."}},
            {"title": "Focused Work Block 2", "type": ActivityType.WORK, "start_hour": 13, "end_hour": 16, "details": {"description": "Continue work tasks, meetings.", "location_hint": "PathosOffice"}},
            {"title": "Learning & Skill Development", "type": ActivityType.LEARNING, "start_hour": 16, "end_hour": 17, "details": {"description": "Reading articles, online courses, or practicing a skill."}},
            {"title": "Leisure / Social Time", "type": ActivityType.LEISURE_ACTIVE, "start_hour": 18, "end_hour": 20, "details": {"description": "Engage in hobbies, social interactions, or relaxation.", "location_hint": "PathosHomeLivingRoom"}},
            {"title": "Dinner", "type": ActivityType.MEAL, "start_hour": 20, "end_hour": 21},
            {"title": "Evening Wind-down & Reflection", "type": ActivityType.REFLECTIVE, "start_hour": 21, "end_hour": 22, "details": {"description": "Journaling, planning for tomorrow, light reading."}},
            {"title": "Sleep", "type": ActivityType.SLEEP, "start_hour": 22, "end_hour": 7, "next_day": True, "details": {"location_hint": "PathosHomeBedroom"}} # Spans midnight
        ]

        current_pathos_schedule = self._schedule.get(PATHOS_USER_ID, [])
        if not any(act.activity_type == ActivityType.SLEEP for act in current_pathos_schedule): # Add default if no sleep entry exists
            for act_def in default_activities:
                start_dt_utc = today_ref_utc.replace(hour=act_def["start_hour"])
                end_dt_utc = today_ref_utc.replace(hour=act_def["end_hour"])

                if act_def.get("next_day"):
                    end_dt_utc += timedelta(days=1)

                # Ensure end time is after start time for same-day activities
                if not act_def.get("next_day") and end_dt_utc <= start_dt_utc:
                    logger.warning(f"Default schedule item '{act_def['title']}' has end time before or same as start time. Adjusting end_hour or skipping if invalid logic.")
                    # Potentially adjust or skip, for now, let it be if it's e.g. 22:00 to 07:00 (handled by next_day)
                    # If it was e.g. 10:00 to 09:00 on same day, that's an issue.
                    # The check `end_dt_utc <= start_dt_utc` without `next_day` handles this.

                activity_slot = ActivitySlot(
                    user_id=PATHOS_USER_ID,
                    activity_title=act_def["title"],
                    activity_type=act_def["type"],
                    start_time=start_dt_utc,
                    end_time=end_dt_utc,
                    activity_details=ActivityDetails(**act_def.get("details", {})) if act_def.get("details") else None
                    # Recurrence can be added later if needed for defaults
                )
                self._schedule[PATHOS_USER_ID].append(activity_slot)
            logger.info(f"ChronosEngine: Added {len(default_activities)} default activities to Pathos's schedule.")
        else:
            logger.info("ChronosEngine: Pathos's schedule already contains entries (e.g. sleep). Default schedule not re-added.")


    async def add_planned_event(self, event_data: Dict[str, Any]) -> Optional[ActivitySlot]:
        """
        Adds a new activity (ActivitySlot) to the schedule.
        event_data should conform to fields of ActivitySlot or be adaptable.
        """
        logger.debug(f"ChronosEngine: Attempting to add planned event: {event_data.get('activity_title', 'Unknown Title')}")
        try:
            # If event_data is already an ActivitySlot model, use it.
            # Otherwise, try to create one. This allows flexibility.
            if isinstance(event_data, ActivitySlot):
                new_activity = event_data
            else:
                # Ensure datetime strings are converted to datetime objects
                if 'start_time' in event_data and isinstance(event_data['start_time'], str):
                    event_data['start_time'] = datetime.fromisoformat(event_data['start_time'])
                if 'end_time' in event_data and isinstance(event_data['end_time'], str):
                    event_data['end_time'] = datetime.fromisoformat(event_data['end_time'])

                # Ensure timezones if naive
                if event_data.get('start_time') and event_data['start_time'].tzinfo is None:
                    event_data['start_time'] = event_data['start_time'].replace(tzinfo=timezone.utc)
                if event_data.get('end_time') and event_data['end_time'].tzinfo is None:
                    event_data['end_time'] = event_data['end_time'].replace(tzinfo=timezone.utc)

                new_activity = ActivitySlot(**event_data)

            user_id = new_activity.user_id
            if user_id not in self._schedule:
                self._schedule[user_id] = []

            self._schedule[user_id].append(new_activity)
            # Sort schedule by start_time after adding
            self._schedule[user_id].sort(key=lambda act: act.start_time)

            self._save_schedule_to_file() # Persist change
            logger.info(f"ChronosEngine: Added event '{new_activity.activity_title}' (ID: {new_activity.id}) for user '{user_id}'.")
            return new_activity
        except Exception as e: # Catch Pydantic validation errors or other issues
            logger.error(f"ChronosEngine: Error adding planned event: {e}. Data: {event_data}", exc_info=True)
            return None

    async def get_current_activity(self, current_time_utc: datetime, user_id: str = PATHOS_USER_ID) -> Optional[ActivitySlot]:
        """
        Returns the current activity for the given user_id based on the provided UTC time.
        It converts current_time_utc to the user's local time for schedule checking.
        """
        if not self.ethos_core:
            logger.warning("ChronosEngine.get_current_activity: EthosCore not available for timezone conversion. Cannot accurately get current activity.")
            # Fallback: iterate through UTC schedule if ethos_core is missing
            user_schedule = self._schedule.get(user_id, [])
            for activity in user_schedule:
                # Naive comparison if EthosCore is missing, assuming schedule times are UTC
                if activity.start_time <= current_time_utc < activity.end_time:
                    return activity
            return None

        # Convert the provided current_time_utc to the user's local time
        # This should use a utility within EthosCore or ChronosEngine that takes a specific UTC time
        # and converts it to user's local, not just gets *current* local time.

        # For now, we'll get user's current local time and check against schedule stored in UTC.
        # This means the schedule times (start_time, end_time in ActivitySlot) MUST be stored as UTC.

        user_schedule_utc = self._schedule.get(user_id, [])
        if not user_schedule_utc:
            return None

        for activity in user_schedule_utc:
            # Ensure activity times are UTC for comparison
            act_start_utc = activity.start_time
            act_end_utc = activity.end_time
            if act_start_utc.tzinfo is None: act_start_utc = act_start_utc.replace(tzinfo=timezone.utc)
            if act_end_utc.tzinfo is None: act_end_utc = act_end_utc.replace(tzinfo=timezone.utc)

            if act_start_utc <= current_time_utc < act_end_utc:
                logger.debug(f"ChronosEngine: Current activity for user '{user_id}' at UTC {current_time_utc.isoformat()} is '{activity.activity_title}'.")
                return activity

        logger.debug(f"ChronosEngine: No current activity found for user '{user_id}' at UTC {current_time_utc.isoformat()}.")
        return None

    async def get_todays_schedule_for_user(self, user_id: str = PATHOS_USER_ID, target_date_utc: Optional[datetime] = None) -> List[ActivitySlot]:
        """
        Returns all activities for a given UTC date for the specified user.
        If target_date_utc is None, uses the current UTC date.
        Activities that span across midnight into the target date are included.
        """
        if not self.ethos_core:
            logger.warning("ChronosEngine.get_todays_schedule_for_user: EthosCore not available. Cannot accurately determine user's local day. Using UTC day.")
            # If EthosCore is not available, we proceed with UTC date logic
            if target_date_utc is None:
                target_date_utc = datetime.now(timezone.utc)
            start_of_day_utc = target_date_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day_utc = start_of_day_utc + timedelta(days=1)
        else:
            # Get the user's local start and end of the target day, then convert to UTC
            # This ensures we capture the full local day.
            user_local_target_date: datetime
            if target_date_utc: # If a specific UTC date is given, convert it to user's local for "today" reference
                # This requires a robust way to get user's local time for a *specific* UTC instant,
                # not just their *current* local time.
                # For now, we'll use the target_date_utc to define Pathos's "today" in his timezone
                pathos_home_tz_str = self._get_pathos_home_timezone_str()
                pathos_tz = timezone.utc # Default
                if pathos_home_tz_str.lower() != 'utc':
                    if ZoneInfo:
                        try:
                            pathos_tz = ZoneInfo(pathos_home_tz_str)
                        except:
                            pass
                    elif pytz:
                        try:
                            pathos_tz = pytz.timezone(pathos_home_tz_str)
                        except:
                            pass

                # Convert target_date_utc (which is a specific point in time) to Pathos's local time
                user_local_target_date = target_date_utc.astimezone(pathos_tz)
            else: # No specific target date, use Pathos's current local "now"
                user_local_target_date = await self._get_pathos_local_datetime()

            # Determine start and end of the user's local day
            start_of_user_local_day = user_local_target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_user_local_day = start_of_user_local_day + timedelta(days=1)

            # Convert these local day boundaries back to UTC for querying the schedule (which is stored in UTC)
            start_of_day_utc = start_of_user_local_day.astimezone(timezone.utc)
            end_of_day_utc = end_of_user_local_day.astimezone(timezone.utc)

        logger.debug(f"ChronosEngine: Fetching schedule for user '{user_id}' for local day corresponding to UTC range: {start_of_day_utc.isoformat()} to {end_of_day_utc.isoformat()}")

        user_schedule_utc = self._schedule.get(user_id, [])
        activities_for_day: List[ActivitySlot] = []

        for activity in user_schedule_utc:
            act_start_utc = activity.start_time
            act_end_utc = activity.end_time
            if act_start_utc.tzinfo is None: act_start_utc = act_start_utc.replace(tzinfo=timezone.utc)
            if act_end_utc.tzinfo is None: act_end_utc = act_end_utc.replace(tzinfo=timezone.utc)

            # Check if the activity overlaps with the target day [start_of_day_utc, end_of_day_utc)
            # Overlap condition: (ActivityStart < DayEnd) and (ActivityEnd > DayStart)
            if act_start_utc < end_of_day_utc and act_end_utc > start_of_day_utc:
                activities_for_day.append(activity)

        # Sort by start time just in case
        activities_for_day.sort(key=lambda act: act.start_time)
        logger.info(f"ChronosEngine: Found {len(activities_for_day)} activities for user '{user_id}' for the target day.")
        return activities_for_day

    async def request_schedule_change(self, change_request: ScheduleChangeRequest) -> ScheduleChangeResponse:
        """
        Handles requests to modify the schedule. (Basic implementation for now)
        This is a simplified version. A full implementation would handle various
        request_types, recurrence, conflicts, etc.
        """
        logger.info(f"ChronosEngine: Received schedule change request for user '{change_request.user_id}': Type '{change_request.request_type}', Activity ID '{change_request.activity_id_to_modify}'.")

        user_id = change_request.user_id
        if user_id not in self._schedule:
            return ScheduleChangeResponse(success=False, message=f"No schedule found for user '{user_id}'.")

        if change_request.request_type == "add":
            if not all([change_request.new_activity_title, change_request.new_activity_type, change_request.new_start_time, change_request.new_end_time]):
                return ScheduleChangeResponse(success=False, message="Missing required fields for adding new activity (title, type, start_time, end_time).")

            # Construct activity data from request
            activity_data_to_add = {
                "user_id": user_id,
                "activity_title": change_request.new_activity_title,
                "activity_type": change_request.new_activity_type,
                "start_time": change_request.new_start_time,
                "end_time": change_request.new_end_time,
                "activity_details": change_request.new_activity_details,
                # id will be generated by ActivitySlot model
            }
            added_activity = await self.add_planned_event(activity_data_to_add)
            if added_activity:
                return ScheduleChangeResponse(success=True, message=f"Activity '{added_activity.activity_title}' added successfully.", updated_activity_id=added_activity.id)
            else:
                return ScheduleChangeResponse(success=False, message="Failed to add new activity.")

        elif change_request.request_type == "remove_occurrence":
            if not change_request.activity_id_to_modify:
                return ScheduleChangeResponse(success=False, message="Activity ID to modify is required for removal.")

            activity_id_to_remove = change_request.activity_id_to_modify
            original_length = len(self._schedule[user_id])
            self._schedule[user_id] = [act for act in self._schedule[user_id] if act.id != activity_id_to_remove]

            if len(self._schedule[user_id]) < original_length:
                self._save_schedule_to_file()
                logger.info(f"ChronosEngine: Removed activity ID '{activity_id_to_remove}' for user '{user_id}'.")
                return ScheduleChangeResponse(success=True, message=f"Activity ID '{activity_id_to_remove}' removed successfully.", updated_activity_id=activity_id_to_remove)
            else:
                logger.warning(f"ChronosEngine: Activity ID '{activity_id_to_remove}' not found for user '{user_id}' for removal.")
                return ScheduleChangeResponse(success=False, message=f"Activity ID '{activity_id_to_remove}' not found.")

        # TODO: Implement other request_types like "modify_occurrence", "cancel_series"
        else:
            logger.warning(f"ChronosEngine: Unsupported schedule change request type: '{change_request.request_type}'.")
            return ScheduleChangeResponse(success=False, message=f"Unsupported request type: {change_request.request_type}")

        return ScheduleChangeResponse(success=False, message="Schedule change request not fully processed.")


if __name__ == '__main__':
    # Basic test and usage example
    async def main_test():
        logger_main = get_logger("chronos_engine_test")
        logger_main.info("--- Testing ChronosEngine ---")

        # Mock Config and EthosCore for testing ChronosEngine in isolation
        class MockEthosCoreForChronos:
            def __init__(self):
                self.ethos_config = {"pathos_home_timezone": "America/New_York"} # Example
                logger_main.info("MockEthosCoreForChronos initialized with NY timezone.")

            async def get_local_datetime_for_user(self, user_id: str) -> datetime:
                # This is a simplified mock. A real one would use the user_id.
                if user_id == PATHOS_USER_ID:
                    tz_str = self.ethos_config.get('pathos_home_timezone', "UTC")
                    if ZoneInfo: try: tz = ZoneInfo(tz_str)
                    except: tz = timezone.utc
                    elif pytz: try: tz = pytz.timezone(tz_str)
                    except: tz = timezone.utc
                    else: tz = timezone.utc
                    return datetime.now(tz)
                return datetime.now(timezone.utc) # Default for others

        mock_config = Config() # Assuming Config can be instantiated simply for this test
        mock_ethos = MockEthosCoreForChronos()

        engine = ChronosEngine(config=mock_config, ethos_core=mock_ethos) # type: ignore

        # Test adding an event for Pathos
        now_utc_test = datetime.now(timezone.utc)
        event_start_utc = now_utc_test.replace(hour=14, minute=0, second=0, microsecond=0)
        event_end_utc = now_utc_test.replace(hour=15, minute=0, second=0, microsecond=0)

        pathos_event_data = {
            "user_id": PATHOS_USER_ID,
            "activity_title": "Test Event for Pathos",
            "activity_type": ActivityType.LEARNING,
            "start_time": event_start_utc.isoformat(), # Pass as ISO string
            "end_time": event_end_utc.isoformat(),   # Pass as ISO string
            "activity_details": {"description": "Learning about Chronos testing."}
        }
        added_event = await engine.add_planned_event(pathos_event_data)
        assert added_event is not None, "Failed to add Pathos event"
        logger_main.info(f"Added event for Pathos: {added_event.activity_title} (ID: {added_event.id}) from {added_event.start_time.isoformat()} to {added_event.end_time.isoformat()}")

        # Test getting Pathos's current activity
        # Adjust current_test_time_utc to be within the event if needed for this part of test
        current_test_time_utc = event_start_utc + timedelta(minutes=30)
        pathos_current_activity = await engine.get_current_activity(current_test_time_utc, PATHOS_USER_ID)

        if pathos_current_activity:
            logger_main.info(f"Pathos's current activity at {current_test_time_utc.isoformat()} (UTC): {pathos_current_activity.activity_title}")
            assert pathos_current_activity.id == added_event.id
        else:
            logger_main.warning(f"No current activity found for Pathos at {current_test_time_utc.isoformat()} (UTC). This might be due to timezone differences if test time is not correctly within the event in Pathos's local time.")
            # This part of the test can be tricky due to timezone handling.
            # The key is that `get_current_activity` compares against schedule stored in UTC.

        # Test getting today's schedule for Pathos
        logger_main.info(f"\nFetching Pathos's schedule for today ({now_utc_test.strftime('%Y-%m-%d')} UTC as reference):")
        pathos_today_schedule = await engine.get_todays_schedule_for_user(PATHOS_USER_ID, target_date_utc=now_utc_test)
        if pathos_today_schedule:
            logger_main.info(f"Pathos has {len(pathos_today_schedule)} activities scheduled for today:")
            for act in pathos_today_schedule:
                # Convert activity times to Pathos's local for display
                act_start_local = await engine._get_pathos_local_datetime(act.start_time)
                act_end_local = await engine._get_pathos_local_datetime(act.end_time)
                logger_main.info(f"  - {act.activity_title} from {act_start_local.strftime('%H:%M')} to {act_end_local.strftime('%H:%M')} (Local: {engine._get_pathos_home_timezone_str()})")
        else:
            logger_main.info("Pathos has no activities scheduled for today.")

        # Clean up schedule file if created by this test
        if SCHEDULE_FILE_PATH.exists() and "pathos_schedule.json" in str(SCHEDULE_FILE_PATH): # Safety check
            logger_main.info(f"Cleaning up test schedule file: {SCHEDULE_FILE_PATH}")
            # SCHEDULE_FILE_PATH.unlink() # Comment out to inspect file after test
        logger_main.info("--- ChronosEngine testing finished ---")

    if __name__ == "__main__":
        logging.basicConfig(level=logging.INFO) # Set root logger level
        # Override specific loggers if needed, e.g. eidos_agent.utils.logger to DEBUG
        # get_logger("eidos_agent.persona_logic.chronos_engine.engine").setLevel(logging.DEBUG)
        asyncio.run(main_test())
