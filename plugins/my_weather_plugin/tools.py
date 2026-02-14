import logging
import requests
import os
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from typing import Dict, Any, List, Optional

from agent_network.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)

# --- Helper Functions and Decorator (from user's implicit snippets) ---

# Placeholder for log_path decorator. In a real scenario, this would handle detailed logging.
def log_path(func):
    def wrapper(*args, **kwargs):
        logger.debug(f"Calling {func.__name__} with args: {args}, kwargs: {kwargs}")
        result = func(*args, **kwargs)
        logger.debug(f"{func.__name__} returned: {result}")
        return result
    return wrapper

def is_within_30_days(date_str: str) -> bool:
    """Checks if a given date string is within the last 30 days or in the future up to 30 days."""
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Check if within past 30 days or future 30 days
        return (today - timedelta(days=30)) <= target_date <= (today + timedelta(days=30))
    except ValueError:
        logger.error(f"Invalid date format: {date_str}. Expected YYYY-MM-DD.")
        return False

# --- Configuration for Weather API ---
# Using Open-Meteo for free weather data.
# Documentation: https://open-meteo.com/en/docs
URLS = {
    "GEOCODING": "https://nominatim.openstreetmap.org/search?", # For Nominatim (geopy default)
    "FORECAST_WEATHER": "https://api.open-meteo.com/v1/forecast?",
    "ARCHIVE_WEATHER": "https://archive-api.open-meteo.com/v1/archive?"
}

class WeatherTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="weather_tool",
            description="Provides various weather-related information, including current temperature, historical temperature, temperature forecast, current rain, historical rain, rain forecast, UV index, and air quality for a given location and date. Requires 'location' as a primary argument. Some functions also require 'date' (YYYY-MM-DD)."
        )
        self.geolocator = Nominatim(user_agent="agent_network_weather_plugin")
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.current_location = "Unknown" # This might be set dynamically by the agent later

    @log_path
    def get_latitude_longitude(self, location: str) -> Optional[Dict[str, float]]:
        try:
            loc = self.geolocator.geocode(location)
            if loc:
                logger.info(f"Geocoded '{location}' to Latitude: {loc.latitude}, Longitude: {loc.longitude}")
                return {"latitude": loc.latitude, "longitude": loc.longitude}
            else:
                logger.warning(f"Could not find coordinates for location: {location}")
                return None
        except Exception as e:
            logger.error(f"Error geocoding location '{location}': {e}")
            return None

    @log_path
    def get_current_temp(self, location: str) -> Optional[float]:
        coords = self.get_latitude_longitude(location)
        if not coords:
            return None
        
        params = {
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "current_weather": True,
            "temperature_unit": "celsius"
        }
        try:
            response = requests.get(URLS["FORECAST_WEATHER"], params=params)
            response.raise_for_status()
            data = response.json()
            if "current_weather" in data:
                logger.info(f"Current temperature for {location}: {data['current_weather']['temperature']}°C")
                return data["current_weather"]["temperature"]
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching current temperature for {location}: {e}")
            return None

    @log_path
    def get_historical_temp(self, location: str, date: str) -> Optional[Dict[str, float]]:
        if not is_within_30_days(date):
            return {"error": "Historical data is limited to the last 30 days and forecast for the next 30 days. Please provide a date within this range."}

        coords = self.get_latitude_longitude(location)
        if not coords:
            return None

        params = {
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "start_date": date,
            "end_date": date,
            "hourly": "temperature_2m",
            "temperature_unit": "celsius"
        }
        try:
            response = requests.get(URLS["ARCHIVE_WEATHER"], params=params)
            response.raise_for_status()
            data = response.json()
            if data and "hourly" in data and "temperature_2m" in data["hourly"] and data["hourly"]["temperature_2m"]:
                avg_temp = sum(data["hourly"]["temperature_2m"]) / len(data["hourly"]["temperature_2m"])
                logger.info(f"Historical average temperature for {location} on {date}: {avg_temp:.2f}°C")
                return {"average_temp": round(avg_temp, 2), "unit": "celsius"}
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching historical temperature for {location} on {date}: {e}")
            return None

    @log_path
    def get_temp_forecast(self, location: str, date: str) -> Optional[Dict[str, Any]]:
        if not is_within_30_days(date):
            return {"error": "Forecast data is limited to the next 30 days. Please provide a date within this range."}

        coords = self.get_latitude_longitude(location)
        if not coords:
            return None

        params = {
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "start_date": date,
            "end_date": date,
            "daily": ["temperature_2m_max", "temperature_2m_min"],
            "temperature_unit": "celsius"
        }
        try:
            response = requests.get(URLS["FORECAST_WEATHER"], params=params)
            response.raise_for_status()
            data = response.json()
            if data and "daily" in data and data["daily"]["time"]:
                max_temp = data["daily"]["temperature_2m_max"][0]
                min_temp = data["daily"]["temperature_2m_min"][0]
                logger.info(f"Temperature forecast for {location} on {date}: Max {max_temp}°C, Min {min_temp}°C")
                return {"max_temp": max_temp, "min_temp": min_temp, "unit": "celsius"}
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching temperature forecast for {location} on {date}: {e}")
            return None
    
    @log_path
    def get_current_rain(self, location: str) -> Optional[float]:
        coords = self.get_latitude_longitude(location)
        if not coords:
            return None
        
        params = {
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "current_weather": True,
            "hourly": "precipitation",
            "past_hours": 1 # Check precipitation in the last hour
        }
        try:
            response = requests.get(URLS["FORECAST_WEATHER"], params=params)
            response.raise_for_status()
            data = response.json()
            if "hourly" in data and "precipitation" in data["hourly"] and data["hourly"]["precipitation"]:
                # Summing precipitation for the last hour
                rain_amount = sum(data["hourly"]["precipitation"])
                logger.info(f"Current rain (last hour) for {location}: {rain_amount} mm")
                return rain_amount
            return 0.0 # No precipitation in the last hour
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching current rain for {location}: {e}")
            return None

    @log_path
    def get_rain_forecast(self, location: str, date: str) -> Optional[Dict[str, Any]]:
        if not is_within_30_days(date):
            return {"error": "Forecast data is limited to the next 30 days. Please provide a date within this range."}

        coords = self.get_latitude_longitude(location)
        if not coords:
            return None

        params = {
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "start_date": date,
            "end_date": date,
            "daily": "precipitation_sum",
        }
        try:
            response = requests.get(URLS["FORECAST_WEATHER"], params=params)
            response.raise_for_status()
            data = response.json()
            if data and "daily" in data and "precipitation_sum" in data["daily"] and data["daily"]["precipitation_sum"]:
                rain_sum = data["daily"]["precipitation_sum"][0]
                logger.info(f"Rain forecast for {location} on {date}: {rain_sum} mm")
                return {"precipitation_sum": rain_sum, "unit": "mm"}
            return 0.0
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching rain forecast for {location} on {date}: {e}")
            return None

    @log_path
    def get_uv_index(self, location: str, date: str = None) -> Optional[float]:
        # Open-Meteo forecast endpoint has daily UV index
        if date and not is_within_30_days(date):
            return {"error": "UV index forecast is limited to the next 30 days. Please provide a date within this range."}
        
        coords = self.get_latitude_longitude(location)
        if not coords:
            return None
        
        # Use current date if no date is provided
        fetch_date = date if date else datetime.now().strftime("%Y-%m-%d")

        params = {
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "start_date": fetch_date,
            "end_date": fetch_date,
            "daily": "uv_index_max",
        }
        try:
            response = requests.get(URLS["FORECAST_WEATHER"], params=params)
            response.raise_for_status()
            data = response.json()
            if data and "daily" in data and "uv_index_max" in data["daily"] and data["daily"]["uv_index_max"]:
                uv_index = data["daily"]["uv_index_max"][0]
                logger.info(f"Max UV Index for {location} on {fetch_date}: {uv_index}")
                return uv_index
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching UV Index for {location} on {fetch_date}: {e}")
            return None

    @log_path
    def get_air_quality(self, location: str, date: str = None) -> Optional[Dict[str, Any]]:
        # Open-Meteo does not provide a direct air quality API in the same way.
        # This would typically require a different API.
        # For demonstration, we'll return a dummy value.
        logger.warning(f"Air quality data for {location} is not available via this tool's configured APIs.")
        return {"error": "Air quality data not available via current API setup. This feature requires a dedicated air quality API."}

    def run(self, **kwargs):
        """
        Executes a weather query based on the action provided in kwargs.
        The 'action' dictionary should contain 'type' (e.g., 'current_temp', 'forecast', 'historical')
        and 'location', and optionally 'date'.
        """
        action = kwargs.get("action", {})
        location = kwargs.get("location") or action.get("location")
        date = kwargs.get("date") or action.get("date") # YYYY-MM-DD

        if not location:
            return {"status": "error", "output": "Location is required for weather queries."}

        # Validate date format if provided
        if date:
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return {"status": "error", "output": "Invalid date format. Expected YYYY-MM-DD."}


        action_type = action.get("type") or kwargs.get("action_type") # Allow action_type to be passed directly


        if action_type == "current_temp":
            temp = self.get_current_temp(location)
            if temp is not None:
                return {"status": "success", "output": f"The current temperature in {location} is {temp}°C."}
            else:
                return {"status": "error", "output": f"Could not retrieve current temperature for {location}."}
        
        elif action_type == "historical_temp":
            if not date:
                return {"status": "error", "output": "Date is required for historical temperature."}
            result = self.get_historical_temp(location, date)
            if result and "error" not in result:
                return {"status": "success", "output": f"The average temperature in {location} on {date} was {result['average_temp']}{result['unit']}."}
            else:
                return {"status": "error", "output": result.get("error", f"Could not retrieve historical temperature for {location} on {date}. Make sure the date is within the last 30 days.")}

        elif action_type == "temp_forecast":
            if not date:
                return {"status": "error", "output": "Date is required for temperature forecast."}
            result = self.get_temp_forecast(location, date)
            if result and "error" not in result:
                return {"status": "success", "output": f"The temperature forecast for {location} on {date}: Max {result['max_temp']}{result['unit']}, Min {result['min_temp']}{result['unit']}."}
            else:
                return {"status": "error", "output": result.get("error", f"Could not retrieve temperature forecast for {location} on {date}. Make sure the date is within the next 30 days.")}

        elif action_type == "current_rain":
            rain = self.get_current_rain(location)
            if rain is not None:
                return {"status": "success", "output": f"The current precipitation (last hour) in {location} is {rain} mm."}
            else:
                return {"status": "error", "output": f"Could not retrieve current rain for {location}."}

        elif action_type == "rain_forecast":
            if not date:
                return {"status": "error", "output": "Date is required for rain forecast."}
            result = self.get_rain_forecast(location, date)
            if result and "error" not in result:
                return {"status": "success", "output": f"The rain forecast for {location} on {date} is {result['precipitation_sum']}{result['unit']}."}
            else:
                return {"status": "error", "output": result.get("error", f"Could not retrieve rain forecast for {location} on {date}. Make sure the date is within the next 30 days.")}
        
        elif action_type == "uv_index":
            result = self.get_uv_index(location, date)
            if result is not None and not isinstance(result, dict): # Check if it's a valid float/int, not an error dict
                return {"status": "success", "output": f"The maximum UV Index for {location} on {date or self.current_date} is {result}."}
            elif isinstance(result, dict) and "error" in result:
                return {"status": "error", "output": result["error"]}
            else:
                return {"status": "error", "output": f"Could not retrieve UV Index for {location} on {date or self.current_date}. Make sure the date is within the next 30 days."}

        elif action_type == "air_quality":
            # This is a placeholder as Open-Meteo doesn't provide air quality directly
            result = self.get_air_quality(location, date)
            return {"status": "error", "output": result["error"]}

        else:
            return {"status": "error", "output": f"Unknown weather action type: {action_type}. Available types: current_temp, historical_temp, temp_forecast, current_rain, rain_forecast, uv_index, air_quality."}


def get_tools():
    """
    Entry point for discovering tools in this plugin.
    Returns a list of BaseTool instances.
    """
    logger.info("Attempting to get tools for My Weather Plugin.")
    try:
        weather_tool_instance = WeatherTool()
        logger.info(f"Successfully created WeatherTool instance: {weather_tool_instance}")
        return [weather_tool_instance]
    except Exception as e:
        logger.error(f"Error creating WeatherTool instance: {e}", exc_info=True)
        return []