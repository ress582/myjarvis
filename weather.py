import requests
import json
import os
from datetime import datetime
from config import config

class WeatherService:
    """Service for fetching weather data from OpenWeatherMap API"""
    
    def __init__(self, api_key=None):
        # Use config for API key, with fallback to parameter or environment variable
        self.api_key = api_key or config.openweather_api_key or os.environ.get('OPENWEATHER_API_KEY', '')
        self.base_url = "https://api.openweathermap.org/data/2.5/"
        
    def get_current_weather(self, city, units="metric"):
        """Get current weather for a city
        
        Args:
            city (str): City name (and optionally country code, e.g., 'London,uk')
            units (str): Units of measurement. Options: 'standard', 'metric', 'imperial'
            
        Returns:
            dict: Weather data or error message
        """
        if not self.api_key:
            return {"error": "No API key configured for weather service"}
            
        try:
            url = f"{self.base_url}weather"
            params = {
                "q": city,
                "appid": self.api_key,
                "units": units
            }
            
            response = requests.get(url, params=params)
            
            # Print response for debugging
            print(f"API Response Status: {response.status_code}")
            print(f"API Response: {response.text[:200]}...")  # Print first 200 chars
            
            response.raise_for_status()
            
            data = response.json()
            
            # Format the response for easier consumption
            weather_data = {
                "location": {
                    "city": data["name"],
                    "country": data["sys"]["country"]
                },
                "temperature": {
                    "current": round(data["main"]["temp"]),
                    "feels_like": round(data["main"]["feels_like"]),
                    "min": round(data["main"]["temp_min"]),
                    "max": round(data["main"]["temp_max"])
                },
                "weather": {
                    "main": data["weather"][0]["main"],
                    "description": data["weather"][0]["description"],
                    "icon": data["weather"][0]["icon"]
                },
                "wind": {
                    "speed": data["wind"]["speed"],
                    "direction": data["wind"].get("deg", 0)
                },
                "humidity": data["main"]["humidity"],
                "pressure": data["main"]["pressure"],
                "visibility": data.get("visibility", 0) / 1000,  # Convert to km
                "sunrise": datetime.fromtimestamp(data["sys"]["sunrise"]).strftime("%H:%M"),
                "sunset": datetime.fromtimestamp(data["sys"]["sunset"]).strftime("%H:%M"),
                "timezone": data["timezone"] / 3600,  # Convert to hours
                "dt": datetime.fromtimestamp(data["dt"]).strftime("%Y-%m-%d %H:%M:%S")
            }
            
            return weather_data
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return {"error": f"City '{city}' not found"}
            elif e.response.status_code == 401:
                return {"error": "Invalid API key"}
            else:
                return {"error": f"HTTP error: {e}"}
        except requests.exceptions.RequestException as e:
            return {"error": f"Request error: {e}"}
        except (KeyError, ValueError, TypeError) as e:
            return {"error": f"Data processing error: {e}"}
    
    def get_forecast(self, city, days=5, units="metric"):
        """Get weather forecast for a city
        
        Args:
            city (str): City name (and optionally country code, e.g., 'London,uk')
            days (int): Number of days for forecast (max 5)
            units (str): Units of measurement. Options: 'standard', 'metric', 'imperial'
            
        Returns:
            dict: Forecast data or error message
        """
        if not self.api_key:
            return {"error": "No API key configured for weather service"}
            
        try:
            url = f"{self.base_url}forecast"
            params = {
                "q": city,
                "appid": self.api_key,
                "units": units,
                "cnt": min(days * 8, 40)  # API returns data in 3-hour steps, 8 per day
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Process and organize forecast data by day
            forecasts = {}
            for item in data["list"]:
                # Get date without time
                date = datetime.fromtimestamp(item["dt"]).strftime("%Y-%m-%d")
                
                if date not in forecasts:
                    forecasts[date] = {
                        "date": date,
                        "day_name": datetime.fromtimestamp(item["dt"]).strftime("%A"),
                        "temperatures": [],
                        "weather_descriptions": [],
                        "weather_icons": [],
                        "precipitation_probability": []
                    }
                
                forecasts[date]["temperatures"].append(item["main"]["temp"])
                forecasts[date]["weather_descriptions"].append(item["weather"][0]["description"])
                forecasts[date]["weather_icons"].append(item["weather"][0]["icon"])
                forecasts[date]["precipitation_probability"].append(item.get("pop", 0) * 100)  # Convert to percentage
            
            # Calculate daily averages and most common weather
            result = []
            for date, forecast in forecasts.items():
                # Get most common weather description and icon
                from collections import Counter
                descriptions_counter = Counter(forecast["weather_descriptions"])
                icons_counter = Counter(forecast["weather_icons"])
                
                daily_summary = {
                    "date": forecast["date"],
                    "day_name": forecast["day_name"],
                    "temperature": {
                        "avg": round(sum(forecast["temperatures"]) / len(forecast["temperatures"])),
                        "min": round(min(forecast["temperatures"])),
                        "max": round(max(forecast["temperatures"]))
                    },
                    "weather": {
                        "description": descriptions_counter.most_common(1)[0][0],
                        "icon": icons_counter.most_common(1)[0][0]
                    },
                    "precipitation_probability": round(max(forecast["precipitation_probability"]))
                }
                
                result.append(daily_summary)
            
            return {
                "location": {
                    "city": data["city"]["name"],
                    "country": data["city"]["country"]
                },
                "forecast": result
            }
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return {"error": f"City '{city}' not found"}
            elif e.response.status_code == 401:
                return {"error": "Invalid API key"}
            else:
                return {"error": f"HTTP error: {e}"}
        except requests.exceptions.RequestException as e:
            return {"error": f"Request error: {e}"}
        except (KeyError, ValueError, TypeError) as e:
            return {"error": f"Data processing error: {e}"}