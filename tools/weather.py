import httpx
from os import getenv
from pydantic import BaseModel

class WeatherAPI:
    def __init__(self, api_key: str, zip_code: str = "68106"):
        self.ZIP_CODE = zip_code
        self.API_KEY = api_key
        self.BASE_URL = "http://api.weatherapi.com/v1"

    async def get_current_weather(self) -> str | None:
        async with httpx.AsyncClient() as client:
            try:
                params = {"key": self.API_KEY, "q": self.ZIP_CODE}
                response = await client.get(
                    f"{self.BASE_URL}/current.json", params=params
                )
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                return f"Failed to fetch weather data: {e}"

            current = data.get("current", {})
            temp_f = current.get("temp_f", "N/A")
            wind_mph = current.get("wind_mph", "N/A")
            feels_like = current.get("feelslike_f", "N/A")
            conditions = current.get("condition", {}).get("text", "N/A")
            return (
                f"temp_fahrenheit = {temp_f}, "
                f"feels_like_fahrenheit = {feels_like}, "
                f"wind_mph = {wind_mph}, "
                f"conditions = {conditions}"
            )

_weather = WeatherAPI(api_key=getenv("WEATHER_API") or "", zip_code=68106)

class CallWeatherArgs(BaseModel):
    pass

async def call_weather_api(args: CallWeatherArgs):
    """Gets the current weather at the user's location / USE ANYTIME USER ASKS FOR WEATHER"""
    return await _weather.get_current_weather()
