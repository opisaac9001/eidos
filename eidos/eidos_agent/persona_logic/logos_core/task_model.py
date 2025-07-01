import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Literal, List
from pydantic import BaseModel, Field

class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex}")
    name: str  # A short, human-readable name or the command that initiated the task
    type: str  # E.g., "web_search", "calculation", "event_creation", "image_generation", "custom_llm_query", "multi_step_project"

    status: Literal["pending", "in_progress", "success", "failure", "cancelled", "paused"] = "pending"

    input_params: Dict[str, Any] = Field(default_factory=dict) # Parameters needed to execute the task

    # For tasks that are part of a larger project or have sub-tasks
    parent_task_id: Optional[str] = None
    sub_task_ids: List[str] = Field(default_factory=list)

    # Execution results
    result: Optional[Any] = None # Can store complex objects or simple strings
    result_summary: Optional[str] = None # A brief textual summary of the result
    error_message: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None # For any update to the task state

    # Context and Metadata
    user_id: Optional[str] = None # User who requested or is associated with the task
    priority: int = 0 # 0 = normal, higher = more important
    metadata: Dict[str, Any] = Field(default_factory=dict) # For any other relevant info

    def update_status(self, new_status: Literal["pending", "in_progress", "success", "failure", "cancelled", "paused"]):
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        if new_status in ["success", "failure", "cancelled"]:
            if not self.completed_at: # Only set if not already completed/cancelled
                self.completed_at = self.updated_at
        elif new_status == "in_progress" and not self.started_at:
            self.started_at = self.updated_at
        # To handle un-cancelling or un-failing, completed_at might need to be reset explicitly.
        # For now, once completed_at is set, it stays.

if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    logger.info("--- Testing Task Model ---")

    # Test 1: Basic task creation
    task1_data = {
        "name": "Perform Web Search for AI Ethics",
        "type": "web_search",
        "input_params": {"query": "AI ethics current trends"},
        "user_id": "user123",
        "priority": 1
    }
    task1 = Task(**task1_data)
    logger.info(f"Task 1 Created: {task1.model_dump_json(indent=2)}")
    assert task1.task_id.startswith("task_")
    assert task1.status == "pending"
    assert task1.input_params["query"] == "AI ethics current trends"
    assert task1.created_at <= datetime.now(timezone.utc)

    # Test 2: Status updates
    task1.update_status("in_progress")
    logger.info(f"Task 1 In Progress: {task1.model_dump_json(indent=2)}")
    assert task1.status == "in_progress"
    assert task1.started_at is not None
    assert task1.updated_at is not None
    original_updated_at = task1.updated_at

    # Simulate some time passing
    import time as py_time
    py_time.sleep(0.01)

    task1.update_status("success")
    task1.result = {"summary": "AI ethics is important.", "num_sources": 5}
    task1.result_summary = "Found 5 relevant sources on AI ethics."
    logger.info(f"Task 1 Success: {task1.model_dump_json(indent=2)}")
    assert task1.status == "success"
    assert task1.completed_at is not None
    assert task1.updated_at is not None
    assert task1.updated_at > original_updated_at
    assert task1.result["num_sources"] == 5

    # Test 3: Task with parent and sub-tasks
    task2_data = {
        "name": "Main Project: Develop Eidos",
        "type": "multi_step_project",
        "user_id": "dev_team",
        "parent_task_id": "project_alpha" # Example
    }
    task2 = Task(**task2_data)
    task2.sub_task_ids.append("subtask_feature_A")
    task2.sub_task_ids.append("subtask_testing_B")
    logger.info(f"Task 2 (Project): {task2.model_dump_json(indent=2)}")
    assert task2.parent_task_id == "project_alpha"
    assert len(task2.sub_task_ids) == 2

    logger.info("Task Model basic tests passed.")
