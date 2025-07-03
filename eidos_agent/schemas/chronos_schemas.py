from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime, date, time # Ensure all datetime components are available

class Activity(BaseModel):
    """
    Represents a scheduled activity for Pathos.
    """
    activity_id: str = Field(..., description="Unique identifier for the activity.")
    title: str = Field(..., description="Concise title for the activity.")
    description: Optional[str] = Field(default=None, description="More detailed description of the activity.")

    # Using datetime for start and end to be explicit and timezone-aware.
    # ChronosEngine will be responsible for ensuring these are in Pathos's local timezone.
    start_datetime: datetime = Field(..., description="Start date and time of the activity (Pathos's local time, timezone-aware).")
    end_datetime: datetime = Field(..., description="End date and time of the activity (Pathos's local time, timezone-aware).")

    activity_type: str = Field(..., description="Categorical type of activity (e.g., 'work_deep', 'leisure_social', 'learning_online', 'chore_home', 'sleep', 'travel').")
    location_hint: Optional[str] = Field(default=None, description="Suggested or actual location for the activity (e.g., 'Office Building A', 'Home - Study', 'City Park Cafe').")

    # Optional fields for richer activity details:
    # involved_npc_ids_hint: List[str] = Field(default_factory=list, description="Hint of NPC IDs expected to be involved.")
    # required_items_hint: List[str] = Field(default_factory=list, description="Items Pathos might need for this activity.")
    # status: Optional[str] = Field(default="planned", description="Status of the activity, e.g., 'planned', 'in-progress', 'completed', 'cancelled'.")
    # recurrence_rule: Optional[str] = None # For recurring activities (e.g., iCalendar RRULE string)
    # associated_goal_id: Optional[str] = None # If this activity contributes to a larger goal

class ScheduleChangeRequest(BaseModel):
    """
    A request to modify Pathos's schedule, typically originating from Pathos (LLM) or the user.
    """
    request_id: str = Field(..., description="Unique ID for this change request.")
    requester_id: str = Field(..., description="ID of who is making the request (e.g., Pathos's own ID, or a user ID).")
    requested_action: str = Field(..., description="The type of change requested (e.g., 'cancel_activity', 'reschedule_activity', 'add_new_activity', 'find_time_for_activity').")

    target_activity_id: Optional[str] = Field(default=None, description="ID of the activity to be modified or cancelled.")

    # For adding or rescheduling:
    new_activity_details: Optional[Activity] = Field(default=None, description="Full details of the new activity to add, or new details for rescheduling.")
    # For rescheduling, specific fields might be provided instead of a full Activity object:
    # new_start_datetime: Optional[datetime] = None
    # new_end_datetime: Optional[datetime] = None
    # preferred_time_window_start: Optional[datetime] = None # For 'find_time_for_activity'
    # preferred_time_window_end: Optional[datetime] = None   # For 'find_time_for_activity'
    # duration_minutes: Optional[int] = None                # For 'find_time_for_activity'

    reason_for_change: Optional[str] = Field(default=None, description="Reason provided for the schedule change request.")
    # Optional:
    # urgency_level: Optional[str] = Field(default="normal", description="Urgency of the request, e.g., 'low', 'normal', 'high'.")

class ScheduleChangeResponse(BaseModel):
    """
    Response from ChronosEngine after processing a ScheduleChangeRequest.
    """
    request_id: str = Field(..., description="The ID of the original ScheduleChangeRequest.")
    success: bool = Field(..., description="Whether the requested schedule change was successfully applied.")
    message: str = Field(..., description="A human-readable message about the outcome of the request (e.g., 'Activity cancelled.', 'Conflict found, could not reschedule.').")

    # Optionally, return a segment of the updated schedule:
    updated_schedule_overview: List[Activity] = Field(default_factory=list, description="A snapshot of relevant parts of the schedule after the change (e.g., the modified activity, or upcoming activities).")
    # Optional:
    # conflict_details: Optional[str] = None # If not successful due to a conflict
    # suggested_alternatives: Optional[List[Activity]] = None # If rescheduling failed but alternatives were found
