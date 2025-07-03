from pydantic import BaseModel, Field
from typing import List, Any, Optional

class UserSettingItem(BaseModel):
    """Represents a single user setting or preference."""
    attribute_name: str = Field(..., description="The name of the setting/preference (e.g., 'preferred_name', 'timezone', 'communication_style').")
    attribute_value: Any = Field(..., description="The value of the setting.")
    user_statement_context: Optional[str] = Field(default="User updated setting.", description="Context or source of this setting update (e.g., 'User stated: My name is John', 'GUI update').")
    # Optional:
    # last_updated_timestamp: Optional[str] = None # ISO Format

class UserSettingsRequest(BaseModel):
    """Request model for updating a user's settings."""
    user_id: str = Field(..., description="The ID of the user whose settings are being updated.")
    settings: List[UserSettingItem] = Field(..., description="A list of settings to update.")
