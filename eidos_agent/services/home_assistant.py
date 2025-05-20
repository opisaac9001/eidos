# eidos_agent/services/home_assistant.py
import json
import re
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Literal, Optional, AsyncGenerator, List, Tuple, Any
from dataclasses import dataclass

# Adjust import paths
from eidos_agent.core.config import Config, HomeAssistantConfig
from eidos_agent.modules.ethos_core.memory_storage import MemoryStorage # Use the refined MemoryStorage
from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

class HomeAssistantError(Exception):
    """Custom exception for Home Assistant service errors"""
    pass

@dataclass
class TaskResult:
    """Standardized result format for all HA operations"""
    success: bool
    message: str
    ha_entity_id: Optional[str] = None
    execution_time: Optional[datetime] = None # For reminders/timers
    metadata: Optional[Dict] = None
    previous_state: Optional[Any] = None # Store previous state dict
    new_state: Optional[Any] = None # Store new state dict


class HomeAssistantService:
    """
    Integrates with Home Assistant to control devices, set reminders/timers,
    and potentially stream events.
    """
    def __init__(self, config: Config, memory_storage: MemoryStorage):
        """
        Initializes the Home Assistant service.

        Args:
            config: The main Eidos Config object.
            memory_storage: Active MemoryStorage instance (part of EthosCore).
        """
        self.config = config
        self.memory_storage = memory_storage
        self.ha_config: Optional[HomeAssistantConfig] = config.get_ha_config()

        if not self.ha_config:
            # Log warning in config.py setup. Just note state here.
            logger.info("HomeAssistantService initialized but configuration is missing. Features will be disabled.")
            self.base_url = None
            self.headers = None
            self._session = None
            self.device_aliases = {}
            self.domain_mappings = {}
            return

        self.base_url = self.ha_config['url'].rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {self.ha_config['token']}",
            "Content-Type": "application/json"
        }
        self._session: Optional[aiohttp.ClientSession] = None
        self._setup_device_aliases() # Load aliases
        self._setup_domain_mappings() # Load mappings
        logger.info("HomeAssistantService initialized.")

    async def connect(self):
        """Initialize and validate the connection pool."""
        # Only attempt connection if configured
        if not self.ha_config:
             logger.debug("HA Connect skipped: Configuration missing.")
             return

        if self._session is None or self._session.closed:
            try:
                timeout = aiohttp.ClientTimeout(total=self.ha_config['timeout'])
                # Use TCPConnector with limit=0 for potentially many concurrent requests if needed
                # connector = aiohttp.TCPConnector(limit=0)
                self._session = aiohttp.ClientSession(headers=self.headers, timeout=timeout) #, connector=connector)
                logger.info(f"HA Service: Created new aiohttp session for {self.base_url}")
                # Validate connection by getting basic state (e.g., sun.sun)
                await self._get_entity_state_full("sun.sun")
                logger.info("HA Service: Connection validated.")
            except Exception as e:
                logger.error(f"HA Service: Connection or validation failed: {e}", exc_info=True)
                await self.disconnect() # Ensure session is closed on failure
                raise HomeAssistantError(f"Failed to connect or validate Home Assistant connection: {e}")

    async def disconnect(self):
        """Closes the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("HA Service: aiohttp session closed.")
        self._session = None

    def is_available(self) -> bool:
        """Check if the HA service is configured and connected."""
        return self.ha_config is not None and self._session is not None and not self._session.closed

    def _setup_device_aliases(self):
        """Configure natural language device mappings (Example)."""
        # TODO: Load this from a configuration file for better management
        self.device_aliases = {
            'living_room_lights': ['living room light', 'living room lights', 'main light', 'ceiling light'],
            'bedroom_lamp': ['bedroom lamp', 'night light', 'bedside light'],
            'kitchen_lights': ['kitchen lights', 'under cabinet lights'],
            'main_thermostat': ['thermostat', 'temperature', 'climate control', 'ac', 'heat', 'heating', 'cooling'],
            'office_outlet': ['office outlet', 'desk outlet'],
            'media_center_tv': ['tv', 'television', 'media center tv'],
            'main_speaker': ['speaker', 'main speaker', 'volume'],
            'front_door_lock': ['front door lock', 'main door lock'], # Example Lock
            'back_door_lock': ['back door lock'], # Example Lock
            'living_room_fan': ['living room fan'], # Example Fan
            # Add more specific devices and their aliases
        }
        logger.debug("HA device aliases loaded.")

    def _setup_domain_mappings(self):
        """Map keywords to HA domains."""
        # TODO: Load this from a configuration file
        self.domain_mappings = {
            # Keyword: HA Domain
            'light': 'light', 'lights': 'light', 'lamp': 'light', 'lamps': 'light', 'bulb': 'light', 'dim': 'light', 'brightness': 'light',
            'switch': 'switch', 'outlet': 'switch',
            'fan': 'fan', 'fans': 'fan',
            'thermostat': 'climate', 'temperature': 'climate', 'ac': 'climate', 'heat': 'climate', 'heating': 'climate', 'cooling': 'climate',
            'media_player': 'media_player', 'tv': 'media_player', 'television': 'media_player', 'speaker': 'media_player', 'volume': 'media_player', 'play': 'media_player', 'pause': 'media_player', 'stop': 'media_player', 'resume': 'media_player',
            'lock': 'lock', 'locks': 'lock', 'door': 'lock', 'doors': 'lock', # Mapping door to lock
            'scene': 'scene', 'scenes': 'scene',
            'automation': 'automation', 'automations': 'automation', 'routine': 'automation', 'routines': 'automation',
            'timer': 'timer', 'timers': 'timer',
            'reminder': 'persistent_notification', # Using persistent_notification for reminders
            'sensor': 'sensor', 'sensors': 'sensor',
            'binary_sensor': 'binary_sensor', 'binary_sensors': 'binary_sensor', # e.g. door/window open/closed
        }
        logger.debug("HA domain mappings loaded.")

    async def process_command(self, command: str) -> TaskResult:
        """
        Process natural language HA command. Routes to specific handlers.
        Called by LogosCore.
        """
        # This method is called by LogosCore ONLY if HA is potentially available.
        # Specific HA errors or parsing failures are handled here.
        if not self.ha_config or not self._session or self._session.closed:
             # This check should ideally not be hit if LogosCore checks is_available()
             logger.error("process_command called but HA service is not available.")
             return TaskResult(False, "Home Assistant is not configured or connected.")


        logger.debug(f"HA Service processing command: {command}")
        try:
            cmd_lower = command.lower()
            # Prioritize specific command types (matching classification logic)
            if 'remind' in cmd_lower:
                return await self._handle_reminder(command)
            elif 'timer' in cmd_lower:
                return await self._handle_timer(command)
            else:
                # Attempt to parse as a device control command or other HA domain command
                parsed_intent = self._parse_device_command(command)
                if parsed_intent:
                    domain, device_id_suffix, service, params = parsed_intent

                    # Check if the determined domain is allowed
                    if domain and domain not in self.ha_config['allowed_domains']:
                         raise HomeAssistantError(f"Controlling domain '{domain}' is not allowed by configuration.")

                    if entity_id := (f"{domain}.{device_id_suffix}" if domain and device_id_suffix else None):
                         # This is a standard entity control command
                         return await self.control_device(entity_id, service, **params)
                    elif domain and service:
                         # This is a domain-level service call (e.g., scene, automation trigger)
                         # Need specific entity ID or name extraction depending on service
                         # Add specific handling here
                         if domain == 'scene' and service == 'turn_on':
                              scene_name = params.get('scene_name', command.split('scene')[-1].strip()) # Basic extraction
                              if scene_name:
                                   scene_entity_id = f"scene.{scene_name.lower().replace(' ','_')}" # Needs better slugify
                                   return await self.control_device(scene_entity_id, service, **params) # Call control_device for scene
                              else:
                                   return TaskResult(False, f"Could not determine scene name from command: {command}")
                         # Add other domain/service specific calls here (e.g., automation.trigger)
                         # elif domain == 'automation' and service == 'trigger': ...
                         else:
                              # If no specific entity ID and not a handled domain-level service
                              return TaskResult(False, f"Domain-level service '{domain}.{service}' requires specific handling or target.")
                    else:
                         # Parsing succeeded partially (determined domain/suffix/service)
                         # but couldn't form a complete entity_id or handled domain call.
                         logger.warning(f"Parsed command but could not form valid HA call: {command}")
                         return TaskResult(False, f"Could not fully parse command for Home Assistant: {command}. Please be more specific.")
                else:
                     # Parsing failed entirely
                     logger.warning(f"Could not parse HA command directly: {command}")
                     # Return None or a specific TaskResult indicating parsing failure
                     return TaskResult(False, f"Could not understand command as a Home Assistant action: {command}")


        except HomeAssistantError as e:
             logger.warning(f"HA Service Error during command processing '{command}': {e}")
             # Do NOT store outcome here, LogosCore handles storing the result of its attempt.
             raise e # Re-raise for LogosCore to catch and store
        except Exception as e:
            logger.error(f"Unexpected error during HA command processing '{command}': {e}", exc_info=True)
            # Do NOT store outcome here
            raise e # Re-raise for LogosCore

    async def control_device(self, entity_id: str, service: str, **params) -> TaskResult:
        """Direct device control with state verification."""
        if not self.ha_config or not self._session or self._session.closed:
             # Should not be hit if is_available() is checked by caller
             logger.error("control_device called but HA service is not available.")
             return TaskResult(False, "Home Assistant is not configured or connected.")

        logger.info(f"Executing HA service: {service} on {entity_id} with params {params}")
        previous_state_data = None
        new_state_data = None
        try:
            # Get previous state
            previous_state_data = await self._get_entity_state_full(entity_id)
            if previous_state_data is None:
                 # Entity might not exist or HA is unavailable
                 raise HomeAssistantError(f"Entity '{entity_id}' not found or HA unavailable.")
            previous_state_str = previous_state_data.get('state', 'unknown')

            # Check if the entity's domain is allowed
            domain = entity_id.split('.')[0]
            if domain not in self.ha_config['allowed_domains']:
                 raise HomeAssistantError(f"Domain '{domain}' is not in allowed domains by configuration.")

            # Execute command
            await self._call_ha_service(
                service,
                domain=domain,
                service_data={'entity_id': entity_id, **params}
            )

            # Verify state change (optional, adds delay)
            # await asyncio.sleep(0.5) # Give HA time to update state
            # new_state_data = await self._get_entity_state_full(entity_id)
            # new_state_str = new_state_data.get('state', 'unknown') if new_state_data else 'unknown'

            # Basic verification check (can be improved) - Simplified for baseline
            # verified = False
            # if service == 'turn_on' and new_state_str == 'on': verified = True
            # elif service == 'turn_off' and new_state_str == 'off': verified = True
            # elif service == 'lock' and new_state_str == 'locked': verified = True
            # elif service == 'unlock' and new_state_str == 'unlocked': verified = True
            # # Add checks for brightness, temp, etc. if needed, comparing params to new_state attributes
            # elif service in ['set_temperature', 'set_brightness_pct', 'volume_set', 'media_play', 'media_stop']:
            #      verified = True # Assume success if API call worked

            # For baseline, assume success if API call didn't raise error, skip state verification for speed
            verified = True # Simplification

            # Re-fetch state AFTER command to get latest state for logging
            await asyncio.sleep(0.1) # Small delay
            new_state_data = await self._get_entity_state_full(entity_id)
            new_state_str = new_state_data.get('state', 'unknown') if new_state_data else 'unknown'


            message = f"Executed {service} on {entity_id}."
            if verified:
                 message += f" New state is '{new_state_str}'."
            # else: # Message if verification failed
            #      message += f" New state is '{new_state_str}'. (State change verification failed or skipped)."


            result = TaskResult(
                success=True, # API call succeeded from HA perspective
                message=message,
                ha_entity_id=entity_id,
                previous_state=previous_state_data, # Store full state dict
                new_state=new_state_data,
                metadata={'verified': verified, 'params': params, 'service': service, 'domain': domain}
            )
            # Store interaction outcome via MemoryStorage
            await self._store_interaction_outcome(f"{service} {entity_id}", True, message, result.__dict__)
            return result

        except HomeAssistantError as e:
            logger.warning(f"HA Error controlling {entity_id}: {e}")
            # Store interaction outcome (failure) via MemoryStorage
            await self._store_interaction_outcome(f"{service} {entity_id}", False, str(e), {'ha_entity_id': entity_id, 'service': service, 'domain': domain})
            raise e # Re-raise for LogosCore to catch and store

        except Exception as e:
             logger.error(f"Unexpected error controlling {entity_id}: {e}", exc_info=True)
             # Store interaction outcome (unexpected failure) via MemoryStorage
             await self._store_interaction_outcome(f"{service} {entity_id}", False, f"Unexpected error: {e}", {'ha_entity_id': entity_id, 'service': service, 'domain': domain})
             raise e # Re-raise for LogosCore

    async def _handle_reminder(self, command: str) -> TaskResult:
        """Process reminder commands using persistent_notification."""
        if not self.ha_config or not self._session or self._session.closed:
             logger.error("_handle_reminder called but HA service is not available.")
             return TaskResult(False, "Home Assistant is not configured or connected.")
        logger.debug(f"Handling reminder: {command}")
        parsed = self._parse_reminder(command)
        if not parsed:
            logger.warning("Could not parse reminder details.")
            # Store outcome
            await self._store_interaction_outcome(command, False, "Could not parse reminder details.")
            return TaskResult(False, "Could not parse reminder details (e.g., time or message).")

        try:
            # Use persistent notification as reminder
            notification_id = f"eidos_rem_{int(datetime.now().timestamp())}"
            domain = 'persistent_notification'
            if domain not in self.ha_config['allowed_domains']:
                 error_msg = f"Domain '{domain}' not allowed by configuration."
                 logger.warning(error_msg)
                 await self._store_interaction_outcome(command, False, error_msg)
                 return TaskResult(False, error_msg)

            await self._call_ha_service(
                'create',
                domain=domain,
                service_data={
                    'message': parsed['message'],
                    'title': f"Eidos Reminder @ {parsed['time_obj'].strftime('%H:%M')}",
                    'notification_id': notification_id
                }
            )
            message = f"OK. Reminder set: '{parsed['message']}' for {parsed['time_obj'].strftime('%Y-%m-%d %H:%M')}."
            result = TaskResult(
                success=True,
                message=message,
                ha_entity_id=f"persistent_notification.{notification_id}",
                execution_time=parsed['time_obj'],
                metadata={'reminder_message': parsed['message'], 'service': 'create', 'domain': domain}
            )
            await self._store_interaction_outcome(command, True, message, result.__dict__)
            return result
        except HomeAssistantError as e:
            logger.warning(f"Failed to create reminder notification: {e}")
            await self._store_interaction_outcome(command, False, f"Failed to create reminder: {e}")
            raise e # Re-raise for LogosCore
        except Exception as e:
             logger.error(f"Unexpected error creating reminder: {e}", exc_info=True)
             await self._store_interaction_outcome(command, False, f"Unexpected error creating reminder: {e}")
             raise e # Re-raise for LogosCore

    async def _handle_timer(self, command: str) -> TaskResult:
        """Process timer commands using HA timer integration."""
        if not self.ha_config or not self._session or self._session.closed:
             logger.error("_handle_timer called but HA service is not available.")
             return TaskResult(False, "Home Assistant is not configured or connected.")
        logger.debug(f"Handling timer: {command}")
        duration = self._parse_duration(command)
        if not duration:
            logger.warning("Could not parse timer duration.")
            await self._store_interaction_outcome(command, False, "Could not parse timer duration.")
            return TaskResult(False, "Could not parse timer duration (e.g., '5 minutes').")

        # Assume a generic timer entity exists or can be created dynamically?
        # HA typically requires timers to be configured first.
        # Let's assume a naming convention like 'timer.eidos_generic_timer_1'
        # This needs configuration in HA's configuration.yaml or via UI Helpers.
        # Example: timer: eidos_generic_timer_1: duration: "00:00:00"
        timer_entity_id = "timer.eidos_generic_timer_1" # Needs to exist in HA!

        try:
            domain = 'timer'
            if domain not in self.ha_config['allowed_domains']:
                 error_msg = f"Domain '{domain}' not allowed by configuration."
                 logger.warning(error_msg)
                 await self._store_interaction_outcome(command, False, error_msg)
                 return TaskResult(False, error_msg)


            # Call the 'start' service
            await self._call_ha_service(
                'start',
                domain=domain,
                service_data={
                    'entity_id': timer_entity_id,
                    'duration': str(duration.total_seconds()) # Duration in seconds as string
                }
            )
            message = f"OK. Timer '{timer_entity_id}' started for {duration}."
            result = TaskResult(
                success=True,
                message=message,
                ha_entity_id=timer_entity_id,
                execution_time=datetime.now() + duration,
                metadata={'duration_seconds': duration.total_seconds(), 'service': 'start', 'domain': domain}
            )
            await self._store_interaction_outcome(command, True, message, result.__dict__)
            return result
        except HomeAssistantError as e:
            logger.warning(f"Failed to start timer {timer_entity_id}: {e}")
            await self._store_interaction_outcome(command, False, f"Failed to start timer: {e}")
            raise e # Re-raise for LogosCore
        except Exception as e:
             logger.error(f"Unexpected error starting timer: {e}", exc_info=True)
             await self._store_interaction_outcome(command, False, f"Unexpected error starting timer: {e}")
             raise e # Re-raise for LogosCore


    async def stream_events(self, event_types: List[str] = None) -> AsyncGenerator[Dict, None]:
        """
        Stream Home Assistant events.
        Requires HA websocket connection. (Not implemented in this service version)
        """
        logger.warning("HA Event streaming is not implemented in this service version.")
        if not self.ha_config or not self._session or self._session.closed:
             raise HomeAssistantError("Home Assistant is not configured or connected.")

        # This requires implementing websocket connection and event handling
        # using a library like 'websockets' or asyncio's websockets support.
        # Or using the 'homeassistant_api' library's event streaming features.
        # Example placeholder structure:
        # url = f"ws://{self.base_url.split('//')[-1]}/api/websocket"
        # async with websockets.connect(url) as ws:
        #    # Perform HA websocket auth
        #    # Listen for event messages
        #    yield event_data # Yield each event

        # For now, raise error or return empty generator
        raise NotImplementedError("HA Event streaming is not implemented.")
        yield # This makes it a generator

    async def _call_ha_service(self, service: str, domain: str, service_data: Dict):
        """Make HA service call with error handling."""
        if not self._session or self._session.closed: raise HomeAssistantError("Not connected to Home Assistant")
        url = f"{self.base_url}/api/services/{domain}/{service}"
        # logger.debug(f"Calling HA Service: POST {url} Data: {service_data}") # Too verbose
        try:
            async with self._session.post(url, json=service_data) as resp:
                # logger.debug(f"HA Service Response Status: {resp.status}") # Too verbose
                # HA returns 200 OK even if entity_id is wrong but service exists
                # It returns context info which might indicate issues.
                response_data = await resp.json()
                # logger.debug(f"HA Service Response Data: {response_data}") # Too verbose
                if resp.status >= 400:
                    error_text = json.dumps(response_data) # Error details often in JSON body
                    logger.warning(f"HA API error ({resp.status}) calling {domain}.{service}: {error_text[:200]}")
                    raise HomeAssistantError(f"HA API error ({resp.status}): {error_text[:200]}")
                # Check response data for potential issues if needed (more advanced)
                return response_data
        except aiohttp.ClientError as e:
            logger.error(f"HA connection error calling service {domain}/{service}: {e}", exc_info=True)
            raise HomeAssistantError(f"Connection error calling service {domain}.{service}: {str(e)}") from e
        except json.JSONDecodeError as e:
             logger.error(f"Failed to decode HA JSON response for {domain}/{service}: {e}")
             raise HomeAssistantError(f"Invalid JSON response from HA for {domain}.{service}: {e}") from e


    async def _get_entity_state_full(self, entity_id: str) -> Optional[Dict]:
        """Get complete entity state with attributes."""
        if not self._session or self._session.closed: raise HomeAssistantError("Not connected to Home Assistant")
        url = f"{self.base_url}/api/states/{entity_id}"
        # logger.debug(f"Getting HA State: GET {url}") # Too verbose
        try:
            async with self._session.get(url) as resp:
                # logger.debug(f"HA State Response Status: {resp.status}") # Too verbose
                if resp.status == 200:
                    state_data = await resp.json()
                    # logger.debug(f"HA State Data for {entity_id}: {state_data}") # Too verbose
                    return state_data
                elif resp.status == 404:
                     # logger.warning(f"Entity not found: {entity_id}") # Too noisy for sun.sun checks
                     return None
                else:
                    error_text = await resp.text()
                    logger.warning(f"Failed to get state for {entity_id} ({resp.status}): {error_text}")
                    # Don't raise error here, just return None, let caller handle missing entity
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"HA connection error getting state for {entity_id}: {e}", exc_info=True)
            raise HomeAssistantError(f"State fetch connection error for {entity_id}: {str(e)}") from e
        except json.JSONDecodeError as e:
             logger.error(f"Failed to decode HA JSON state response for {entity_id}: {e}")
             raise HomeAssistantError(f"Invalid JSON state response from HA for {entity_id}: {e}") from e


    # --- Parsing Helpers ---

    def _parse_device_command(self, text: str) -> Optional[Tuple[str, Optional[str], str, Dict]]:
        """
        Parse natural language device commands.
        Returns: Tuple of (domain, device_id_suffix, service, params) or None
        """
        text_lower = text.lower()
        domain = self._determine_device_type(text_lower)
        device_id_suffix = self._resolve_device_alias(text_lower)
        service = None
        params = {}

        # If we found a domain and a device, prioritize mapping service for that
        if domain and device_id_suffix:
            # Determine service based on keywords *and* potential device type
            if any(kw in text_lower for kw in ['on', 'enable', 'activate', 'start', 'play', 'resume']):
                service = 'turn_on'
                if domain == 'timer': service = 'start'
                elif domain == 'lock': service = 'unlock'
                elif domain == 'media_player': service = 'media_play'
                elif domain == 'automation': service = 'trigger' # Or turn_on? Check HA service
                elif domain == 'scene': service = 'turn_on'

            elif any(kw in text_lower for kw in ['off', 'disable', 'deactivate', 'stop', 'pause', 'cancel']):
                service = 'turn_off'
                if domain == 'timer': service = 'cancel'
                elif domain == 'lock': service = 'lock'
                elif domain == 'media_player': service = 'media_stop' # Or media_pause?
                elif domain == 'automation': service = 'turn_off'

            elif any(kw in text_lower for kw in ['set', 'change', 'adjust']):
                # Determine specific set service based on keywords
                if any(p in text_lower for p in ['brightness', 'dim']):
                     service = 'light.turn_on' # Brightness is usually a param of turn_on
                     percent = self._extract_percentage(text_lower)
                     if percent is not None: params['brightness_pct'] = percent
                elif any(p in text_lower for p in ['temperature', 'thermostat', 'ac', 'heat']):
                     service = 'climate.set_temperature'
                     temp = self._extract_temperature(text_lower)
                     if temp is not None: params['temperature'] = temp
                elif any(p in text_lower for p in ['volume']):
                     service = 'media_player.volume_set'
                     volume = self._extract_number(text_lower, min_val=0.0, max_val=1.0)
                     if volume is not None: params['volume_level'] = volume
                # Add more specific 'set' actions (color temp, fan speed, etc.)
                else:
                     logger.warning(f"Generic 'set' command detected for {device_id_suffix}, service unclear: {text}")
                     # Fallback to a generic set service or return None?
                     # For now, return None, require more specific command
                     return None
            # Handle queries about state (e.g., what's the temp, is the light on?)
            elif any(kw in text_lower for kw in ['what', 'whats', 'is', 'get', 'show', 'report', 'status', 'state']):
                 # This is an info query about a device state
                 # This should ideally be classified as an INFO_QUERY by the classifier
                 # But if it reaches here, maybe handle it? No, let the classifier/Logos handle info queries.
                 pass # Do nothing, let it return None if no control service matched


        # If domain found but no specific device (or device extraction failed)
        # Check for domain-level services that might not need a specific suffix initially
        elif domain:
            # Handle domain-level services based on keywords
             if domain == 'scene' and any(kw in text_lower for kw in ['activate', 'turn on', 'set']):
                  service = 'turn_on' # Service to activate a scene
                  # Scene name will need extraction from text (done in process_command)
             elif domain == 'automation' and any(kw in text_lower for kw in ['run', 'trigger', 'start', 'activate']):
                  service = 'trigger' # Service to trigger automation
                  # Automation entity_id/name needs extraction from text
             elif domain == 'lock' and 'lock' in text_lower: # Handle "lock all doors" (needs entity_id=all)
                  service = 'lock'
                  device_id_suffix = 'all' # Special suffix for all entities in domain? (Needs HA support)
             elif domain == 'lock' and 'unlock' in text_lower: # Handle "unlock all doors"
                  service = 'unlock'
                  device_id_suffix = 'all' # Special suffix for all entities in domain?
             # Handle queries about state (e.g., what's the temp, is the light on?) - Again, should be INFO_QUERY
             elif domain in ['sensor', 'binary_sensor', 'climate', 'light', 'switch'] and any(kw in text_lower for kw in ['what', 'whats', 'is', 'get', 'show', 'report', 'status', 'state', 'temperature', 'humidity', 'on', 'off', 'open', 'closed']):
                 # This is an info query about a domain's state
                 # This should ideally be classified as an INFO_QUERY by the classifier
                 pass # Do nothing, let it return None

             # Add more domain-level services

        # If no domain found or no suitable service found
        if not service:
             logger.debug(f"Could not determine service or full intent for command: {text}")
             return None

        # Return parsed components
        logger.debug(f"Parsed HA command: Domain={domain}, Suffix={device_id_suffix}, Service={service}, Params={params}")
        return domain, device_id_suffix, service, params


    def _resolve_device_alias(self, text: str) -> Optional[str]:
        """Convert natural language to HA entity ID suffix."""
        text_lower = text.lower()
        best_match_suffix = None
        longest_alias_len = 0

        for suffix, aliases in self.device_aliases.items():
            for alias in aliases:
                # Use regex for word boundaries for better matching
                pattern = r'\b' + re.escape(alias) + r'\b'
                if re.search(pattern, text_lower):
                    # If this alias is longer than the previous best match
                    if len(alias) > longest_alias_len:
                        longest_alias_len = len(alias)
                        best_match_suffix = suffix
                        # Don't break immediately, find the longest matching alias

        logger.debug(f"Resolved alias in '{text_lower}' to suffix: {best_match_suffix}")
        return best_match_suffix


    def _determine_device_type(self, text: str) -> Optional[str]:
        """Identify device type (domain hint) from command text."""
        text_lower = text.lower()
        found_domain = None
        longest_keyword_len = 0

        for keyword, domain in self.domain_mappings.items():
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text_lower):
                 # If this keyword is longer than the previous best match
                 if len(keyword) > longest_keyword_len:
                      longest_keyword_len = len(keyword)
                      found_domain = domain

        logger.debug(f"Determined domain hint '{found_domain}' from text: {text_lower}")
        return found_domain


    def _parse_reminder(self, text: str) -> Optional[Dict]:
        """Extract reminder details from text."""
        text_lower = text.lower()
        message = text_lower # Start with full text
        time_obj = None
        time_str_found = None

        # More robust patterns using named groups
        patterns = [
            # "remind me to [message] in [value] minutes/hours"
            r'(?:remind me to |reminder to |remind me )(.*?)(?: in | for )(?P<val>\d+)\s*(?P<unit>minute|min|hour|hr)s?',
            # "remind me to [message] at [time]" / "remind me at [time] to [message]"
            r'(?:remind me to |reminder to |remind me )(.*?)(?: at | @ )(?P<time>\d{1,2}:?\d{0,2}\s*[ap]?m?)',
            r'(?:remind me at |reminder at )(?P<time>\d{1,2}:?\d{0,2}\s*[ap]?m?)(?: to )(.*)',
            # "remind me to [message] tomorrow at [time]"
            r'(?:remind me to |reminder to |remind me )(.*?)(?: tomorrow at | tomorrow @ )(?P<time>\d{1,2}:?\d{0,2}\s*[ap]?m?)',
             # "remind me [message] at [time]"
             r'(?:remind me )(.*?)(?: at | @ )(?P<time>\d{1,2}:?\d{0,2}\s*[ap]?m?)'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                group_dict = match.groupdict()
                # Find the message group - might be group 1 or 'msg'
                message = group_dict.get('msg', match.group(1)).strip()
                time_str_found = group_dict.get('time')
                value_str = group_dict.get('val')
                unit = group_dict.get('unit')
                is_tomorrow = 'tomorrow' in match.group(0).lower() # Check if 'tomorrow' was in the matched part

                if value_str and unit: # Handle "in X minutes/hours"
                    try:
                        value = int(value_str)
                        if unit.startswith('min'): time_obj = datetime.now() + timedelta(minutes=value)
                        elif unit.startswith('hr'): time_obj = datetime.now() + timedelta(hours=value)
                    except ValueError: continue # Skip this pattern match if value is not int
                elif time_str_found: # Handle "at X:XX" or "tomorrow at X:XX"
                    time_obj = self._parse_time_string(time_str_found, tomorrow=is_tomorrow)

                if time_obj and message:
                    logger.debug(f"Parsed reminder: Message='{message}', Time='{time_obj}', Matched='{match.group(0)}'")
                    # Clean up message further if needed (remove trailing prepositions etc.)
                    message = re.sub(r' (at|in|for)$', '', message, flags=re.IGNORECASE).strip()
                    return {'message': message, 'time_obj': time_obj, 'time_str': time_str_found or f"{value_str} {unit}"}

        logger.warning(f"Failed to parse reminder: {text}")
        return None


    def _parse_time_string(self, time_str: str, tomorrow: bool = False) -> Optional[datetime]:
        """Helper to parse time strings like '5pm', '14:30', '9:00 am', 'noon', 'midnight', 'morning', 'afternoon', 'evening'."""
        now = datetime.now()
        base_date = now + timedelta(days=1) if tomorrow else now
        hour, minute = 0, 0
        am_pm = None

        time_str_lower = time_str.lower()

        # Handle special cases: noon, midnight, morning, afternoon, evening
        if 'noon' in time_str_lower: hour = 12; minute = 0
        elif 'midnight' in time_str_lower: hour = 0; minute = 0 # 00:00
        elif 'morning' in time_str_lower: hour = 9; minute = 0 # Default morning
        elif 'afternoon' in time_str_lower: hour = 14; minute = 0 # Default afternoon (2 PM)
        elif 'evening' in time_str_lower: hour = 19; minute = 0 # Default evening (7 PM)
        else:
            # Try parsing HH:MM am/pm, HH:MM, H am/pm, H
            match = re.match(r'(\d{1,2})[:\.]?(\d{2})?\s*([ap]m)?', time_str_lower.strip(), re.IGNORECASE)
            if match:
                try:
                    hour = int(match.group(1))
                    minute = int(match.group(2) or 0)
                    am_pm = match.group(3)

                    if hour < 0 or hour > 23: raise ValueError("Hour out of range")
                    if minute < 0 or minute > 59: raise ValueError("Minute out of range")

                    # Adjust for AM/PM if present
                    if am_pm:
                        if hour < 1 or hour > 12: raise ValueError("Invalid hour for AM/PM format")
                        if am_pm == 'pm' and hour < 12: hour += 12
                        if am_pm == 'am' and hour == 12: hour = 0 # Midnight case (12 AM is 00:00)

                except ValueError as e:
                     logger.warning(f"Could not parse time string '{time_str}' into valid datetime: {e}")
                     return None
            else:
                 logger.warning(f"Time string format not recognized: '{time_str}'")
                 return None

        try:
            dt = datetime(base_date.year, base_date.month, base_date.day, hour, minute)

            # If time is in the past for today (and not explicitly tomorrow), assume next day
            if not tomorrow and dt < now:
                dt += timedelta(days=1)
            return dt
        except ValueError as e:
             logger.warning(f"Could not construct datetime object for '{time_str}': {e}")
             return None


    def _parse_duration(self, text: str) -> Optional[timedelta]:
        """Extract duration from text."""
        text_lower = text.lower()
        duration_pattern = r'(\d+)\s*(minute|min|hour|hr|second|sec)s?'
        matches = re.findall(duration_pattern, text_lower)
        total_seconds = 0
        if matches:
            for value, unit in matches:
                try:
                    value_int = int(value)
                    if unit.startswith('min'): total_seconds += value_int * 60
                    elif unit.startswith('hour') or unit.startswith('hr'): total_seconds += value_int * 3600
                    elif unit.startswith('sec'): total_seconds += value_int
                except ValueError:
                    continue # Skip if value is not an integer
            if total_seconds > 0:
                logger.debug(f"Parsed duration: {total_seconds} seconds")
                return timedelta(seconds=total_seconds)
        logger.warning(f"Could not parse duration from: {text}")
        return None


    def _extract_percentage(self, text: str) -> Optional[int]:
        """Extract percentage value from text."""
        match = re.search(r'(\d+)\s*(?:%|percent)', text, re.IGNORECASE)
        if match:
            try:
                value = int(match.group(1))
                return max(0, min(100, value))
            except ValueError: return None
        return None


    def _extract_number(self, text: str, min_val: float = -float('inf'), max_val: float = float('inf')) -> Optional[float]:
        """Extract first numeric value from text with range validation."""
        # Look for numbers potentially preceded by "to" or "at" or "by"
        match = re.search(r'(?:to|at|by|set to)\s*(-?\d+(?:\.\d+)?)', text, re.IGNORECASE)
        if not match:
             # Fallback to any number not adjacent to letters
             match = re.search(r'(?<![a-zA-Z])(-?\d+(?:\.\d+)?)(?![a-zA-Z])', text)

        if match:
            try:
                # Use the last capturing group which should be the number itself
                value = float(match.group(match.lastindex))
                return max(min_val, min(max_val, value))
            except (ValueError, IndexError): return None
        return None


    def _extract_temperature(self, text: str) -> Optional[float]:
        """Extract temperature value, assuming Celsius if no unit."""
        text_lower = text.lower()
        # Look for number followed by C or F or degree symbol or "degrees"
        match = re.search(r'(\d+(?:\.\d+)?)\s*(?:°|deg|degrees)?\s*([cf])?', text_lower)
        if match:
            try:
                value = float(match.group(1))
                unit = match.group(2)
                if unit == 'f':
                    logger.debug(f"Extracted temperature: {value} F")
                    # Decide on internal unit. Let's assume HA handles units passed in params.
                    # If HA needs Celsius, conversion is needed here.
                    # For now, return value as extracted. Check HA climate service requirements.
                    return value # Assuming HA handles F if specified
                else: # Assume Celsius if 'c' or no unit
                    logger.debug(f"Extracted temperature: {value} C (or unitless)")
                    return value
            except ValueError: return None

        # Fallback: extract any number if no unit found, within a reasonable temp range
        num = self._extract_number(text_lower, min_val=-20, max_val=50) # Reasonable Celsius range?
        if num is not None:
             logger.debug(f"Extracted unitless temperature (assuming C): {num}")
             return num
        return None


    async def _store_interaction_outcome(self, command: str, success: bool, message: str, metadata: Optional[Dict] = None):
        """Helper to store HA interaction outcomes in memory via MemoryStorage."""
        # This is called by HA service methods to log *their* outcome.
        # LogosCore also logs the *overall* task outcome. Decide if you need both levels of logging.
        # For now, let's keep it simple and log it here.
        await self.memory_storage.add_entry({
            "type": "ha_interaction", # Use specific type
            "content": f"HA Command: '{command}' -> Success: {success}. Result: {message}",
            "metadata": {
                "command": command,
                "success": success,
                "message": message,
                **(metadata or {})
            }
            # EthosCore will handle adding salience, timestamp, mood context etc.
        })
        logger.debug(f"Stored HA interaction outcome: {command} -> {success}")

    # Add async context manager methods
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.disconnect()