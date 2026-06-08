import asyncio
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional
from stadium_data import STADIUM_DATA

CACHE_PATH = "data/weather_cache.json"

class WeatherClient:
    """
    Asynchronous weather client for fetching 14-day forecasts and historical baselines 
    from Open-Meteo (ERA5) for the 16 World Cup 2026 stadiums.
    Uses pure standard library.
    """
    def __init__(self, cache_path: str = CACHE_PATH):
        self.cache_path = cache_path
        self.cache = self._load_cache()
        self.lock = asyncio.Lock()

    def _load_cache(self) -> dict:
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception:
            pass

    async def _fetch_url_json(self, url: str) -> dict:
        """Helper to fetch JSON asynchronously using standard library urllib in an executor."""
        loop = asyncio.get_event_loop()
        def _fetch():
            headers = {"User-Agent": "WM2026-Predictor-Weather-Client/1.0"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        return await loop.run_in_executor(None, _fetch)

    async def get_weather_async(self, city: str, date_str: str, time_str: str) -> Tuple[float, float]:
        """
        Retrieves temperature (C) and relative humidity (%) for a stadium.
        Uses cached values first, then live forecast (if within 14 days), 
        otherwise falls back to a 5-year historical average (2021-2025).
        """
        if city not in STADIUM_DATA:
            # Fallback to standard baseline values if city is unknown
            return 20.0, 50.0

        lat = STADIUM_DATA[city]["lat"]
        lon = STADIUM_DATA[city]["lon"]
        
        # Round time to nearest hour
        try:
            match_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            # Default fallback if time is malformed
            return 20.0, 50.0

        cache_key = f"{city}_{match_dt.strftime('%Y%m%d_%H00')}"
        
        async with self.lock:
            if cache_key in self.cache:
                entry = self.cache[cache_key]
                return entry["temp"], entry["humidity"]

        # Determine if the date is within the 14-day forecast window from today (June 8, 2026)
        # We assume simulation run date is June 8, 2026 for World Cup kickoff prep
        sim_today = datetime(2026, 6, 8)
        days_diff = (match_dt - sim_today).days

        temp, humidity = 20.0, 50.0
        source = "fallback"

        if 0 <= days_diff <= 14:
            try:
                # Fetch 14-day forecast
                url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relative_humidity_2m&timezone=GMT"
                data = await self._fetch_url_json(url)
                temp, humidity = self._parse_hourly_data(data, match_dt)
                source = "forecast"
            except Exception:
                # Fallback to historical if forecast call fails
                days_diff = -1 

        if days_diff < 0 or days_diff > 14:
            try:
                # Fetch 5-year historical baseline (2021-2025)
                temps, humidities = [], []
                for year in range(2021, 2026):
                    hist_date = match_dt.replace(year=year)
                    date_iso = hist_date.strftime("%Y-%m-%d")
                    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={date_iso}&end_date={date_iso}&hourly=temperature_2m,relative_humidity_2m&timezone=GMT"
                    try:
                        data = await self._fetch_url_json(url)
                        t, h = self._parse_hourly_data(data, hist_date)
                        temps.append(t)
                        humidities.append(h)
                    except Exception:
                        continue
                if temps and humidities:
                    temp = sum(temps) / len(temps)
                    humidity = sum(humidities) / len(humidities)
                    source = "historical_baseline"
            except Exception:
                # Keep defaults
                pass

        async with self.lock:
            self.cache[cache_key] = {
                "temp": round(temp, 2),
                "humidity": round(humidity, 2),
                "source": source,
                "fetched_at": datetime.utcnow().isoformat()
            }
            self._save_cache()

        return round(temp, 2), round(humidity, 2)

    def _parse_hourly_data(self, data: dict, target_dt: datetime) -> Tuple[float, float]:
        """Parses hourly temperature and humidity arrays to match the target hour (GMT)."""
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        hums = hourly.get("relative_humidity_2m", [])
        
        target_str = target_dt.strftime("%Y-%m-%dT%H:00")
        
        if target_str in times:
            idx = times.index(target_str)
            return temps[idx], hums[idx]
            
        # If exact GMT hour match is not found, fallback to closest hour index
        if times:
            # Match by hour
            target_hour = target_dt.hour
            closest_idx = 0
            min_diff = 24
            for idx, t_str in enumerate(times):
                try:
                    dt = datetime.strptime(t_str, "%Y-%m-%dT%H:%M")
                    diff = abs((dt - target_dt).total_seconds()) / 3600.0
                    if diff < min_diff:
                        min_diff = diff
                        closest_idx = idx
                except ValueError:
                    continue
            return temps[closest_idx], hums[closest_idx]
            
        return 20.0, 50.0
