import logging
from typing import Optional, List
import secrets

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from eidos_agent.persona_logic.ethos_core.core import EthosCore # Path is already correct
from eidos_agent.core.config import Config
# Updated imports for Chronos models and PATHOS_USER_ID from the new location
from eidos_agent.persona_logic.chronos_engine import (
    ActivitySlot,
    PathosEvent,
    EventType,
    PathosEventDetails,
    PATHOS_USER_ID
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/pathos", tags=["Pathos Chronos"])

_ethos_core: Optional[EthosCore] = None
_config: Optional[Config] = None

def init_pathos_chronos_router(
    ethos: EthosCore,
    config_instance: Config
):
    global _ethos_core, _config
    _ethos_core = ethos
    _config = config_instance
    logger.info("Pathos Chronos Router initialized with Eidos core components.")

# Moved Pydantic model
class AddPathosEventRequestAPI(BaseModel):
    title: str
    start_date: str  # Expecting ISO format string, will be parsed by Pydantic/datetime
    end_date: str    # Expecting ISO format string
    event_type: EventType
    description: Optional[str] = None
    location: Optional[str] = None
    details: Optional[PathosEventDetails] = None


@router.get("/schedule/today", response_model=List[ActivitySlot])
async def get_pathos_todays_schedule(): # pragma: no cover
    if not _ethos_core or not _ethos_core.chronos_engine:
        logger.error("Pathos Chronos Router: EthosCore or ChronosEngine not initialized for /schedule/today.")
        raise HTTPException(status_code=503, detail="Schedule system not ready.")
    try:
        return await _ethos_core.chronos_engine.get_todays_schedule_for_user() # Default user is Pathos
    except Exception as e:
        logger.error(f"Error retrieving Pathos daily schedule: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error retrieving schedule: {str(e)}")

@router.get("/events/upcoming", response_model=List[PathosEvent])
async def get_pathos_upcoming_events(days_ahead: int = 7):
    if not _ethos_core or not _ethos_core.chronos_engine:
        logger.error("Pathos Chronos Router: EthosCore or ChronosEngine not initialized for /events/upcoming.")
        raise HTTPException(status_code=503, detail="Event system not ready.")
    if not (1 <= days_ahead <= 90): # Keep reasonable limits
        raise HTTPException(status_code=400, detail="days_ahead parameter must be between 1 and 90.")
    try:
        return await _ethos_core.chronos_engine.get_upcoming_events(user_id=PATHOS_USER_ID, days_ahead=days_ahead)
    except Exception as e: # pragma: no cover
        logger.error(f"Error retrieving Pathos upcoming events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error retrieving upcoming events: {str(e)}")

@router.post("/events/add", response_model=PathosEvent, status_code=201)
async def add_pathos_planned_event_api(event_request: AddPathosEventRequestAPI, x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password")):
    if not _ethos_core or not _ethos_core.chronos_engine or not _config:
        logger.error("Pathos Chronos Router: Core components (Ethos, ChronosEngine, Config) not initialized for /events/add.")
        raise HTTPException(status_code=503, detail="Event system or configuration not ready.")

    admin_pw_cfg = _config.get_admin_password()
    if admin_pw_cfg: # Password check is only enforced if EIDOS_ADMIN_PASSWORD is set
        if not x_admin_password: # pragma: no cover
            logger.warning("Attempt to add Pathos event without admin password when one is configured.")
            raise HTTPException(status_code=401, detail="Unauthorized: Admin password required to add Pathos events.")
        if not secrets.compare_digest(x_admin_password, admin_pw_cfg): # pragma: no cover
            logger.warning("Incorrect admin password provided for adding Pathos event.")
            raise HTTPException(status_code=403, detail="Forbidden: Incorrect admin password.")
    # If admin_pw_cfg is not set, the request proceeds without password check (logged by ChronosEngine if necessary)

    try:
        event_data_for_storage = event_request.model_dump(exclude_unset=True)
        # Ensure the event is for Pathos, overriding any user_id that might be in details by mistake
        event_data_for_storage['user_id'] = PATHOS_USER_ID

        added_event = await _ethos_core.chronos_engine.add_planned_event(event_data_for_storage)

        if added_event:
            return added_event
        else: # pragma: no cover
            logger.error("Failed to add Pathos event, add_planned_event returned None or False.")
            raise HTTPException(status_code=500, detail="Failed to add event to ChronosEngine.")

    except ValueError as ve: # Catches Pydantic validation errors or other ValueErrors
        logger.error(f"Validation error adding Pathos event: {ve}", exc_info=True)
        raise HTTPException(status_code=422, detail=f"Invalid event data: {str(ve)}")
    except Exception as e: # pragma: no cover
        logger.error(f"Unexpected error adding Pathos event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error adding event: {str(e)}")
