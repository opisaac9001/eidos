from pydantic import BaseModel, Field
from typing import Optional, Literal

class FeedbackRequest(BaseModel):
    """
    Schema for submitting feedback about an interaction with Pathos.
    """
    interaction_id: Optional[str] = Field(default=None, description="Optional ID of the specific interaction this feedback refers to.")
    user_id: str = Field(..., description="ID of the user providing the feedback.")

    last_user_input: str = Field(..., description="The last input the user provided before Pathos's response.")
    last_pathos_response: str = Field(..., description="Pathos's response that this feedback is about.")

    feedback_type: Literal["positive", "negative", "correction", "suggestion", "other"] = Field(..., description="The general type of feedback.")
    rating: Optional[int] = Field(default=None, description="Optional numerical rating (e.g., 1-5).")
    feedback_text: Optional[str] = Field(default=None, description="Free-form textual feedback from the user.")
    suggested_response: Optional[str] = Field(default=None, description="If the user offers a better response Pathos could have given.")
    # Optional:
    # timestamp: Optional[str] = None # ISO Format, when feedback was submitted
    # client_context: Optional[Dict[str, Any]] = None # Info about client version, platform etc.
