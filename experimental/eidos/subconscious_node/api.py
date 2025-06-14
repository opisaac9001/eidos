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
from typing import List, Dict

# Flexible imports - work both as standalone script and as package module
try:
    # Try relative imports first (when run as part of package)
    from . import context_store
    from . import mood
    from . import utils
    from . import thinker # To access monologue_buffer
except ImportError:
    # Fall back to direct imports (when run as standalone script)
    import context_store
    import mood
    import utils
    import thinker

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

class DreamFragmentInject(BaseModel):
    content: str


# --- API Endpoints ---

@app.post("/inject/dream_fragment", response_model=MessageResponse, tags=["Context Injection"])
async def inject_dream_fragment(data: DreamFragmentInject):
    """
    Injects a dream fragment from Eidos (Oneiros) into the subconscious node's dream buffer.
    """
    # Access global dream_buffer and max_dream_buffer_fragments from thinker module
    # This requires thinker's globals to be accessible here.
    # Ensure thinker is imported or its state is managed in a shared way if this becomes complex.
    from . import thinker

    thinker.dream_buffer.append(data.content)
    logger.info(f"Received dream fragment: '{data.content[:100]}...'. Dream buffer size: {len(thinker.dream_buffer)}")

    if len(thinker.dream_buffer) > thinker.max_dream_buffer_fragments:
        num_to_remove = len(thinker.dream_buffer) - thinker.max_dream_buffer_fragments
        del thinker.dream_buffer[:num_to_remove]
        logger.info(f"Trimmed {num_to_remove} oldest dream fragments. Dream buffer size now: {len(thinker.dream_buffer)}")

    return {"message": "Dream fragment injected successfully."}


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

class NodeControlStatePayload(BaseModel):
    node_state: str
    daily_summary: Optional[str] = None

class MoodSyncPayload(BaseModel):
    mood_aspects: Dict[str, float]

@app.post("/control/state", response_model=MessageResponse, tags=["Node Control"])
async def set_node_state(payload: NodeControlStatePayload):
    """
    Sets the operational state of the subconscious node.
    Optionally accepts a daily summary when transitioning to a sleeping state.
    """

    # Directly update thinker's state variables
    logger.info(f"Received request to change node state to: {payload.node_state}")

    # Ensure thinker module is accessible. It's imported at the top level of api.py
    # so it should be fine, but direct access to module globals like this can sometimes be tricky
    # if not managed carefully (e.g. if thinker itself reloads its state from somewhere else).
    # For this structure, thinker.py defines current_node_state as a global.
    from . import thinker # Ensure thinker module is loaded/referenced correctly.

    thinker.current_node_state = payload.node_state
    logger.info(f"Node state in thinker module updated to: {thinker.current_node_state}")

    if payload.daily_summary is not None: # Check for None explicitly if it's Optional
        logger.info(f"Received daily summary for dreaming: {payload.daily_summary[:100]}...")
        thinker.current_daily_summary_for_dreaming = payload.daily_summary
        logger.info(f"Daily summary in thinker module updated.")
    else:
        # If daily_summary is not provided, and the state is not SLEEPING_DREAMING,
        # it might be appropriate to clear any existing summary.
        # However, if state is changing TO SLEEPING_DREAMING and no summary is provided,
        # thinker.py's dream prompt construction already has a fallback.
        # For simplicity, only update if provided. If state changes away from dreaming,
        # thinker loop should ideally handle not using an old summary.
        pass

    return {"message": f"Node state set to {payload.node_state}", "context": payload.node_state}


@app.post("/control/mood", response_model=MessageResponse, tags=["Node Control"])
async def sync_external_mood(payload: MoodSyncPayload):
    """
    Receives a mood snapshot from an external source (e.g., Eidos main agent)
    and updates the subconscious node's internal mood.
    """
    logger.info(f"Received mood sync data: {payload.mood_aspects}")
    # Update the internal mood state of the subconscious node
    mood.update_mood_from_snapshot(payload.mood_aspects) # Assuming mood.py has such a function
    return {"message": "Mood snapshot synced with subconscious node", "data": payload.mood_aspects}

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
