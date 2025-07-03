from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from pydantic import BaseModel, Field

# Constant for Pathos's internal user ID
PATHOS_USER_ID: str = "pathos_internal_user"

class ActivityType(str, Enum):
    WORK = "work"
    LEARNING = "learning"
    LEISURE_PASSIVE = "leisure_passive"
    LEISURE_ACTIVE = "leisure_active"
    CHORE = "chore"
    SOCIAL = "social"
    SLEEP = "sleep"
    REFLECTIVE = "reflective" # e.g., journaling, planning
    TRAVEL = "travel"
    ERRAND = "errand"
    PERSONAL_CARE = "personal_care" # e.g., hygiene, grooming
    MEAL = "meal"
    EXERCISE = "exercise"
    OTHER = "other"

class RecurrenceRule(BaseModel): # Simplified for now
    # Example: "daily", "weekly_mon_wed_fri", "monthly_15th"
    # For MVP, might just be a descriptive string or not used extensively.
    rule_type: str # e.g., "none", "daily", "weekly"
    days_of_week: Optional[List[int]] = None # 0=Mon, 6=Sun, if rule_type is weekly
    # Further details like interval, end_date can be added later.

class ActivityDetails(BaseModel):
    description: Optional[str] = None
    location_hint: Optional[str] = None # e.g., "office", "home_study", "park"
    specific_npc_hints: Optional[List[str]] = None # IDs or names of NPCs expected
    activity_theme: Optional[str] = None # e.g., "focused_work", "casual_chat", "skill_development"
    planned_sites_or_tasks: Optional[List[str]] = None # For web research, specific task items

class ActivitySlot(BaseModel): # This is the 'Activity' referred to in the plan for this file
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = PATHOS_USER_ID
    activity_title: str
    activity_type: ActivityType
    start_time: datetime # Timezone-aware
    end_time: datetime # Timezone-aware
    activity_details: Optional[ActivityDetails] = None
    is_completed: bool = False
    recurrence_rule: Optional[RecurrenceRule] = None # Simplified
    parent_event_id: Optional[str] = None # If generated from a larger user-defined event

    class Config:
        use_enum_values = True # Ensure ActivityType enum values are used

# Schemas for schedule change requests - these are also defined in eidos_agent/schemas/chronos_schemas.py
# For internal ChronosEngine use, we can reference them here or assume they will be imported.
# To avoid circular dependencies if chronos_schemas.py imports from here,
# it's often better to define them once in a central schema location.
# However, for self-containment of the engine's direct models, they are mirrored/redefined here.
# If eidos_agent.schemas.chronos_schemas.py is the source of truth, these should be imported.
# For now, let's assume these are the definitions ChronosEngine will internally work with.

class ScheduleChangeRequest(BaseModel):
    user_id: str
    request_type: str # e.g., "add", "remove_occurrence", "modify_occurrence", "cancel_series"
    activity_id_to_modify: Optional[str] = None

    # For 'add' or 'modify_occurrence'
    new_activity_title: Optional[str] = None
    new_activity_type: Optional[ActivityType] = None
    new_start_time: Optional[datetime] = None # Timezone-aware
    new_end_time: Optional[datetime] = None   # Timezone-aware
    new_activity_details: Optional[ActivityDetails] = None
    # Add other fields as needed for modification, e.g., new_recurrence_rule

    reason: Optional[str] = None

class ScheduleChangeResponse(BaseModel):
    success: bool
    message: str
    updated_activity_id: Optional[str] = None
    modified_occurrence_original_start_time: Optional[datetime] = None # If an occurrence was modified

# Example of a more detailed planned event that could generate multiple ActivitySlots
class PlannedEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = PATHOS_USER_ID
    title: str
    # e.g., "Work on Project Eidos documentation"
    # Could be a more general theme like "Weekend Trip to Mountains"
    overall_start_time: datetime # Timezone-aware
    overall_end_time: datetime   # Timezone-aware
    default_activity_type: ActivityType = ActivityType.OTHER
    default_location_hint: Optional[str] = None
    notes: Optional[str] = None
    # This event might be broken down into several ActivitySlots by ChronosEngine
    # For example, a "Work on Project" event could become several 2-hour work blocks.
    # A "Weekend Trip" could become travel, leisure, sleep slots.
    # For now, ChronosEngine will primarily deal with ActivitySlots directly.
    # LogosCore might create a PlannedEvent, then ChronosEngine adds specific ActivitySlots.

    class Config:
        use_enum_values = True
