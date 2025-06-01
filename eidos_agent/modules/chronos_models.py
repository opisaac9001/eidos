from pydantic import BaseModel, Field, field_validator # Use field_validator for Pydantic v2
from typing import Optional, Dict, Any, Literal, List
from datetime import datetime, date, time, timezone
import uuid

ActivityType = Literal[
    'work', 'intellectual', 'reflective', 'creative', 'leisure', 'maintenance',
    'travel', 'event_related', 'social', 'learning', 'planning', 'other'
]

EventType = Literal[
    'vacation',
    'work_trip',
    'conference',
    'personal_day',
    'appointment',
    'recurring_task',
    'holiday',
    'social_engagement',
    'creative_project',  # Added from broken
    'learning_goal',     # Added from broken
    'health_wellness',   # Added from broken
    'other_event'
]

class ActivitySlotDetails(BaseModel):
    description: str
    mood_influence: Optional[Dict[str, float]] = Field(default=None)
    sub_focus: Optional[str] = Field(default=None)
    location_context: Optional[str] = Field(default=None)

class ActivitySlot(BaseModel):
    id: str = Field(default_factory=lambda: f"slot_{uuid.uuid4().hex}")
    user_id: str
    date: date
    start_time: time
    end_time: time
    slot_name: Optional[str] = Field(default=None)
    activity_title: str
    activity_type: ActivityType
    activity_details: ActivitySlotDetails
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator('date', mode='before')
    @classmethod
    def _parse_date(cls, v):
        if isinstance(v, str): return date.fromisoformat(v)
        if isinstance(v, date): return v
        raise ValueError("Invalid date format")

    @field_validator('start_time', 'end_time', mode='before')
    @classmethod
    def _parse_time(cls, v):
        if isinstance(v, str): return time.fromisoformat(v)
        if isinstance(v, time): return v
        raise ValueError("Invalid time format")

    @field_validator('generated_at', mode='before')
    @classmethod
    def _parse_datetime(cls, v):
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        if isinstance(v, datetime):
            return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
        raise ValueError("Invalid datetime format")

class PathosEventDetails(BaseModel):
    mood_override: Optional[Dict[str, float]] = Field(default=None)
    activity_theme: Optional[str] = Field(default=None)
    planned_sites_or_tasks: Optional[List[str]] = Field(default=None)
    relevant_memory_tags: Optional[List[str]] = Field(default=None)

class PathosEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"event_{uuid.uuid4().hex}")
    user_id: str
    title: str
    start_date: date
    end_date: date
    event_type: EventType # Uses the updated EventType
    description: Optional[str] = Field(default=None)
    location: Optional[str] = Field(default=None)
    details: PathosEventDetails = Field(default_factory=PathosEventDetails) # Ensure default factory
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator('start_date', 'end_date', mode='before')
    @classmethod
    def _parse_event_date(cls, v):
        if isinstance(v, str): return date.fromisoformat(v)
        if isinstance(v, date): return v
        raise ValueError("Invalid date format for event")

    @field_validator('created_at', mode='before')
    @classmethod
    def _parse_event_datetime(cls, v):
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        if isinstance(v, datetime):
            return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
        raise ValueError("Invalid datetime format for event")

    @field_validator('end_date')
    @classmethod
    def _check_end_date(cls, v, info):
        if 'start_date' in info.data and v < info.data['start_date']:
            raise ValueError('end_date must not be before start_date')
        return v

# The AddPathosEventRequest model defined in main.py for the API endpoint
# is sufficient. This internal AddPathosEventRequest can be removed if not used elsewhere.
# class AddPathosEventRequest(BaseModel):
#     title: str
#     description: Optional[str] = None
#     start_time: datetime
#     end_time: datetime
#     location: Optional[str] = None
#     user_id: Optional[str] = None