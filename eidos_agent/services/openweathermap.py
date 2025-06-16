# eidos_agent/services/openweathermap.py

import httpx
import json
import logging
from typing import Dict, Any, Optional, Literal, List, Tuple
import urllib.parse

from eidos_agent.core.config import Config, OpenWeatherMapConfig
from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

class OpenWeatherMapService:
    def __init__(self, config: Config):
        self.config = config
        self.owm_config: Optional[OpenWeatherMapConfig] = config.get_openweathermap_config()

        if not self.owm_config or not self.owm_config.get('api_key'):
            logger.warning("OpenWeatherMapService initialized BUT API key is not configured. Weather fetches will fail.")
            self.is_available = False
            self.http_client = None
            return

        self.is_available = True
        timeout = self.owm_config.get('timeout', 10)
        self.http_client = httpx.AsyncClient(timeout=timeout)
        self.base_url = self.owm_config['base_url'].rstrip('/')
        self.api_key = self.owm_config['api_key']
        self.units = self.owm_config.get('units', 'imperial')
        logger.info("OpenWeatherMapService initialized.")

    async def _get_coordinates_from_location(self, location: str) -> Optional[Tuple[float, float, str, str]]:
        if not self.is_available or not self.http_client: return None
        if not location or not location.strip(): return None
        encoded_location = urllib.parse.quote_plus(location.strip())
        geo_url = f"{self.base_url}/geo/1.0/direct?q={encoded_location}&limit=1&appid={self.api_key}"
        logger.debug(f"Fetching coordinates from OWM Geocoding for '{location}'. URL: {geo_url}")
        try:
            response = await self.http_client.get(geo_url)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                first_result = data[0]
                if isinstance(first_result, dict) and first_result.get('lat') is not None and first_result.get('lon') is not None:
                    lat = first_result['lat']; lon = first_result['lon']; name = first_result.get('name', location); country = first_result.get('country', 'Unknown')
                    logger.debug(f"Geocoding successful for '{location}': Lat={lat}, Lon={lon}, Name={name}, Country={country}")
                    return (lat, lon, name, country)
                else: logger.warning(f"OWM Geocoding returned unexpected result format for '{location}': {data}"); return None
            elif isinstance(data, list) and len(data) == 0: logger.warning(f"OWM Geocoding found no results for '{location}'."); return None
            else: logger.warning(f"OWM Geocoding returned unexpected top-level format for '{location}': {data}"); return None
        except httpx.HTTPStatusError as e: logger.error(f"OWM Geocoding HTTP error {e.response.status_code} for '{location}': {e.response.text}"); return None
        except httpx.RequestError as e: logger.error(f"Network error fetching coordinates for '{location}': {e}"); return None
        except json.JSONDecodeError as e: logger.error(f"Failed to decode JSON response from OWM Geocoding for '{location}': {e}"); return None
        except Exception as e: logger.error(f"Unexpected error during OWM Geocoding for '{location}': {e}", exc_info=True); return None

    async def get_current_weather(self, location: str) -> Dict[str, Any]:
        if not self.is_available or not self.http_client:
            return {"success": False, "error": "OpenWeatherMap service is not configured or HTTP client not initialized.", "location": location}
        if not location or not location.strip():
            return {"success": False, "error": "No location provided for weather fetch.", "location": location}

        coords_result = await self._get_coordinates_from_location(location)
        if not coords_result:
            return {"success": False, "error": f"Could not find coordinates for location '{location}'. Please try a more specific name (e.g., City, State or City, Country).", "location": location}

        lat, lon, city_name_from_geo, country_from_geo = coords_result
        onecall_url = f"{self.base_url}/data/3.0/onecall?lat={lat}&lon={lon}&exclude=minutely,hourly,daily,alerts&appid={self.api_key}&units={self.units}"
        logger.info(f"Fetching weather from OWM One Call API for Lat={lat}, Lon={lon} (Location: {city_name_from_geo}, Units: {self.units}). URL: {onecall_url}")

        try:
            response = await self.http_client.get(onecall_url)
            response.raise_for_status()
            data = response.json()

            current_data = data.get('current', {})
            iana_timezone_from_owm = data.get('timezone') # Extract IANA timezone

            if current_data:
                temperature = current_data.get('temp')
                weather_desc_list = current_data.get('weather', [])
                description = weather_desc_list[0].get('description') if weather_desc_list and isinstance(weather_desc_list, list) and len(weather_desc_list) > 0 else None
                humidity = current_data.get('humidity')
                wind_speed = current_data.get('wind_speed')
                unit_str = '°'
                if self.units == 'imperial': unit_str += 'F'
                elif self.units == 'metric': unit_str += 'C'
                humidity_str = f"{humidity}%" if humidity is not None else None
                wind_speed_str = f"{wind_speed} m/s" if wind_speed is not None and self.units == 'metric' else f"{wind_speed} mph" if wind_speed is not None and self.units == 'imperial' else None

                weather_data_for_return = {
                    "location": city_name_from_geo,
                    "temperature": temperature,
                    "unit": unit_str,
                    "description": description,
                    "humidity": humidity_str,
                    "wind_speed": wind_speed_str,
                    "source": "OpenWeatherMap",
                    "iana_timezone": iana_timezone_from_owm # Include the IANA timezone
                }
                logger.info(f"OpenWeatherMap One Call fetch successful for '{location}'. Data for return: {weather_data_for_return}")
                return {"success": True, "weather_data": weather_data_for_return}
            else:
                logger.warning(f"OpenWeatherMap One Call returned no 'current' data for '{location}'. Response: {data}")
                return {"success": False, "error": "Could not retrieve current weather data from OpenWeatherMap.", "location": location, "raw_response": data}
        except httpx.HTTPStatusError as e:
            logger.error(f"OWM One Call HTTP error {e.response.status_code} for '{location}': {e.response.text}")
            try: error_details = e.response.json().get('message', e.response.text)
            except: error_details = e.response.text
            return {"success": False, "error": f"OpenWeatherMap API error ({e.response.status_code}): {error_details}", "location": location}
        except httpx.RequestError as e:
            logger.error(f"Network error fetching weather from OWM One Call for '{location}': {e}")
            return {"success": False, "error": f"Network error fetching weather: {str(e)}", "location": location}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response from OWM One Call for '{location}': {e}")
            return {"success": False, "error": f"Invalid JSON response from OpenWeatherMap: {e}", "location": location}
        except Exception as e:
            logger.error(f"Unexpected error during OWM One Call fetch for '{location}': {e}", exc_info=True)
            return {"success": False, "error": f"An unexpected error occurred during weather fetch: {str(e)}", "location": location}

    async def close(self):
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()
            logger.info("OpenWeatherMapService HTTP client closed.")