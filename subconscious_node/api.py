"""
Exposes the Pathos Subconscious Node functionalities via a FastAPI application.

This API allows external systems to:
- Inject conversation and action context into the node.
- Observe the current thoughts, mood, and a summary of recent activity.
- (Placeholder) Receive impulses and memory imprints detected by the node.

The API relies on other modules within the `subconscious_node` package for
core logic such as context management, mood tracking, thought generation (via thinker),
and utility functions.
"""
from fastapi import FastAPI
import uvicorn # For running the app with Uvicorn
from pydantic import BaseModel
from typing import List, Dict, Optional # Added Optional

# Assuming context_store.py, mood.py, utils.py, thinker.py are in the same package/directory
from . import context_store
from . import mood
from . import utils
from . import thinker # To access monologue_buffer
from .thinker import set_node_state, set_daily_summary, NODE_STATE_AWAKE_THINKING, NODE_STATE_SLEEPING_DREAMING # Added imports

# --- FastAPI App Instance ---
app = FastAPI(
    title="Pathos Subconscious Node API",
    description="API for interacting with the Pathos Subconscious Node, injecting context, and observing thoughts.",
    version="0.1.0"
)

# --- Pydantic Models for Request/Response Bodies ---
class ContextInject(BaseModel):
    content: str

class ImpulsePayload(BaseModel):
    thought: str
    mood_snapshot: Dict
    timestamp: str

class MemoryImprintPayload(BaseModel):
    content: str
    mood: Dict
    topics: List[str]
    timestamp: str

class CurrentThoughtsResponse(BaseModel):
    recent_thoughts: List[str]
    mood: Dict
    summary: str

class MessageResponse(BaseModel):
    message: str
    context: str | None = None
    data: Dict | None = None

class NodeControlStatePayload(BaseModel):
    node_state: Optional[str] = None
    daily_summary: Optional[str] = None


# --- API Endpoints ---

@app.post("/node/control-state", response_model=MessageResponse, tags=["Node Control"])
async def control_node_state(payload: NodeControlStatePayload):
    actions_taken = []
    if payload.node_state is not None:
        if payload.node_state in [NODE_STATE_AWAKE_THINKING, NODE_STATE_SLEEPING_DREAMING]:
            set_node_state(payload.node_state)
            actions_taken.append(f"Node state set to {payload.node_state}")
        else:
            # Setter function in thinker.py handles logging the warning
            actions_taken.append(f"Invalid node_state '{payload.node_state}' ignored.")

    if payload.daily_summary is not None:
        set_daily_summary(payload.daily_summary)
        actions_taken.append("Daily summary updated.")

    if not actions_taken:
        return {"message": "No control actions taken. Provide 'node_state' or 'daily_summary'."}

    return {"message": "Node control actions processed.", "context": ", ".join(actions_taken)}

@app.post("/inject/conversation", response_model=MessageResponse, tags=["Context Injection"])
async def inject_conversation(data: ContextInject):
    """
    Injects a piece of conversation context into the subconscious node.
    This context will be used in subsequent thought generation prompts.
    """
    context_store.add_conversation_context(data.content)
    return {"message": "Conversation context injected", "context": data.content}

@app.post("/inject/action", response_model=MessageResponse, tags=["Context Injection"])
async def inject_action(data: ContextInject):
    """
    Injects an action context (e.g., user performed an action) into the subconscious node.
    This context will be used in subsequent thought generation prompts.
    """
    context_store.add_action_context(data.content)
    return {"message": "Action context injected", "context": data.content}

@app.get("/current_thoughts", response_model=CurrentThoughtsResponse, tags=["Observation"])
async def get_thoughts():
    """
    Retrieves the most recent thoughts from the monologue buffer,
    the current mood, and a summary of recent thoughts.
    """
    # Access monologue_buffer safely, ensuring we don't go out of bounds
    buffer_len = len(thinker.monologue_buffer)
    num_thoughts_to_fetch = min(buffer_len, 5)
    recent_thoughts = thinker.monologue_buffer[-num_thoughts_to_fetch:]

    current_mood_snapshot = mood.get_current_mood()
    # The summarize_thoughts function is a placeholder, so its output will be fixed
    summary = utils.summarize_thoughts(recent_thoughts)

    return {
        "recent_thoughts": recent_thoughts,
        "mood": current_mood_snapshot,
        "summary": summary
    }

@app.post("/v1/pathos/impulse", response_model=MessageResponse, tags=["External Integration (Placeholder)"])
async def receive_impulse(payload: ImpulsePayload):
    """
    Placeholder endpoint for receiving impulses detected by the subconscious node.
    In a real system, this might trigger external actions or logging.
    """
    print(f"Subconscious node API received impulse: {payload.dict()}")
    return {"message": "Impulse received by subconscious node (placeholder)", "data": payload.dict()}

@app.post("/v1/pathos/memory/imprint", response_model=MessageResponse, tags=["External Integration (Placeholder)"])
async def receive_memory_imprint(payload: MemoryImprintPayload):
    """
    Placeholder endpoint for receiving memory imprints generated by the subconscious node.
    In a real system, this would integrate with a long-term memory storage.
    """
    print(f"Subconscious node API received memory imprint: {payload.dict()}")
    return {"message": "Memory imprint received by subconscious node (placeholder)", "data": payload.dict()}

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Pathos Subconscious Node is active. See /docs for API details."}

# --- Main Block to Run the App ---
if __name__ == '__main__':
    print("Starting Pathos Subconscious Node API server...")
    # It's generally recommended to run thinker.py (monologue_loop) in a separate process.
    # For simplicity in this single-file setup, we acknowledge it would run concurrently.
    # If thinker.py is not running, /current_thoughts will show an empty buffer.
    print("Note: The monologue_loop in thinker.py should be running in a separate process for the API to reflect live thoughts.")
    uvicorn.run(app, host="0.0.0.0", port=8000)
