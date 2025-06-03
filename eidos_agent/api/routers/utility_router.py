import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse

# Core Eidos components (to be injected)
# from eidos_agent.core.config import Config # Config might not be directly needed here
from eidos_agent.core.input_router import InputRouter
from eidos_agent.persona_logic.ethos_core.core import EthosCore # Path is already correct
from eidos_agent.persona_logic.logos_core.handler import LogosCore # Updated import
from eidos_agent.modules.pathos_interface import PathosInterface
from eidos_agent.core.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Utilities"])

# Module-level globals for dependencies
_logos_core: Optional[LogosCore] = None
_ethos_core: Optional[EthosCore] = None
_pathos_interface: Optional[PathosInterface] = None
_input_router_instance: Optional[InputRouter] = None
_connection_manager_instance: Optional[ConnectionManager] = None

def init_utility_router(
    logos: LogosCore,
    ethos: EthosCore,
    pathos: PathosInterface,
    input_router: InputRouter,
    conn_manager: ConnectionManager
):
    """Initializes the Utility router with necessary Eidos core components."""
    global _logos_core, _ethos_core, _pathos_interface, _input_router_instance, _connection_manager_instance

    _logos_core = logos
    _ethos_core = ethos
    _pathos_interface = pathos
    _input_router_instance = input_router
    _connection_manager_instance = conn_manager

    logger.info("Utility Router initialized with Eidos core components.")

@router.get("/v1/weather", status_code=200)
async def get_weather_endpoint(location: str, x_user_id: Optional[str] = Header(None, alias="X-User-Id")): # pragma: no cover
    if not _logos_core:
        logger.error(f"Weather request but LogosCore (via _logos_core) not available. User: {x_user_id or 'unknown'}")
        raise HTTPException(status_code=503, detail="Eidos system (LogosCore) not ready.")
    if not location or not location.strip():
        logger.warning(f"Weather request with no location. User: {x_user_id or 'unknown'}")
        raise HTTPException(status_code=400, detail="'location' query parameter is required.")

    logger.info(f"Weather request for location '{location}'. User: {x_user_id or 'unknown'}")
    try:
        weather_result = await _logos_core.execute_get_weather(location, user_id_context=x_user_id)
        if isinstance(weather_result, dict) and weather_result.get("success"):
             if weather_data := weather_result.get('weather_data'):
                 return JSONResponse(content={"success": True, "location": location, "weather_data": weather_data})
             else:
                 logger.error(f"LogosCore reported success but no 'weather_data' for location '{location}': {weather_result}")
                 raise HTTPException(status_code=500, detail="Weather data missing despite success from service.")
        elif isinstance(weather_result, dict) and weather_result.get("error"):
            error_detail = weather_result.get("error", "Internal weather service error")
            service_msg = weather_result.get("message", "")
            logger.error(f"LogosCore reported an error for weather request at '{location}': {error_detail} - {service_msg}")
            raise HTTPException(status_code=500, detail=error_detail, headers={"X-Weather-Service-Message": service_msg})
        else:
            logger.error(f"LogosCore returned an unexpected response format for weather request at '{location}': {weather_result}")
            raise HTTPException(status_code=500, detail="Weather service returned an unexpected response format.")
    except HTTPException as http_exc:
        raise http_exc # Re-raise known HTTPExceptions
    except Exception as e:
        logger.error(f"Unexpected error in /v1/weather endpoint for location '{location}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected internal server error occurred.")

@router.get("/health")
async def health_check():
    # Use injected dependencies: _ethos_core, _logos_core, _pathos_interface, _input_router_instance, _connection_manager_instance
    core_ok = all([
        _ethos_core,
        _logos_core,
        _pathos_interface,
        _input_router_instance,
        _connection_manager_instance
    ])

    mem_ok = False
    if _ethos_core and hasattr(_ethos_core, 'memory_storage') and hasattr(_ethos_core.memory_storage, '_conn'):
        mem_ok = _ethos_core.memory_storage._conn is not None

    logos_http_ok = False
    if _logos_core and hasattr(_logos_core, 'http_client'):
        logos_http_ok = _logos_core.http_client is not None and not _logos_core.http_client.is_closed

    pathos_http_ok = False
    if _pathos_interface and hasattr(_pathos_interface, 'http_client'):
        pathos_http_ok = _pathos_interface.http_client is not None and not _pathos_interface.http_client.is_closed

    mgr_ok = _connection_manager_instance is not None # Basic check for the manager itself

    status = "ok" if core_ok and mem_ok and logos_http_ok and pathos_http_ok and mgr_ok else "error"
    msg = "Eidos healthy." if status == "ok" else "Eidos core components or dependencies unhealthy."

    if status == "error": # pragma: no cover
        logger.error(
            f"Health check failed. Core Components Initialized: {core_ok}, DB Connection OK: {mem_ok}, "
            f"Logos HTTP Client OK: {logos_http_ok}, Pathos HTTP Client OK: {pathos_http_ok}, "
            f"Connection Manager Initialized: {mgr_ok}"
        )

    return JSONResponse(content={"status": status, "message": msg})
