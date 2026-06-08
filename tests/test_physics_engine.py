import unittest
import asyncio
import os
from unittest.mock import patch
from stadium_data import STADIUM_DATA
from predictor import calculate_thermal_factor, predict_single_match, CONSTANTS, DEFAULT_CONSTANTS
from utils.weather_client import WeatherClient

class TestRetractableRoofOverrides(unittest.TestCase):
    def test_calculate_thermal_factor_roof_override(self):
        # Without retractable roof, extreme heat/humidity: 38C, 75% humidity
        # WBGT is very high (around 35C)
        factor_standard = calculate_thermal_factor(
            temperature=38.0,
            humidity=75.0,
            heat_acclimation_days=0.0,
            is_retractable_roof=False
        )
        
        # With retractable roof, WBGT is overriden to 21.0C
        factor_roof = calculate_thermal_factor(
            temperature=38.0,
            humidity=75.0,
            heat_acclimation_days=0.0,
            is_retractable_roof=True
        )
        
        # Factor with retractable roof should be much higher (closer to 1.0) than standard open-air
        self.assertTrue(factor_roof > factor_standard)
        # Specifically, at 21C, base loss is 0.015 * (21 - 20) = 0.015 -> factor = 0.985
        self.assertAlmostEqual(factor_roof, 0.985, places=4)

    def test_predict_single_match_venue_override(self):
        # Test that Dallas AT&T Stadium (retractable) overrides WBGT to 21.0C,
        # resulting in lambda_adj being close to baseline (minimal heat penalty),
        # while Miami (open-air) under the same high heat has a noticeable penalty.
        # Note: Under extreme heat, the model's defensive organization penalty (-0.8 coefficient)
        # outweighs the attack penalty (0.5 coefficient), causing adjusted lambdas to inflate.
        # Therefore, Miami (more extreme heat) should have higher adjusted lambdas than Dallas (indoor).
        row_dallas = {
            "team_a": "Spain",
            "team_b": "Germany",
            "venue": "Dallas",
            "temp": 38.0,
            "humidity": 75.0,
        }
        
        row_miami = {
            "team_a": "Spain",
            "team_b": "Germany",
            "venue": "Miami",
            "temp": 38.0,
            "humidity": 75.0,
        }
        
        res_dallas = predict_single_match(row_dallas)
        res_miami = predict_single_match(row_miami)
        
        # Miami (open-air heat) has more defensive organization decay, inflating its lambdas above Dallas (indoor)
        self.assertTrue(res_miami["lambda_a_adj"] > res_dallas["lambda_a_adj"])
        self.assertTrue(res_miami["lambda_b_adj"] > res_dallas["lambda_b_adj"])


class TestPPDATacticalScaling(unittest.TestCase):
    def test_ppda_thermal_scaling_comparison(self):
        # Spain (PPDA = 8.2, intense pressing) should have higher thermal loss (lower thermal factor)
        # than Qatar (PPDA = 15.2, passive low block) under hot/humid weather.
        # Heat parameters: 30C, 60% humidity -> WBGT ~ 24.3C
        
        # Spain: low PPDA -> high multiplier
        factor_spain = calculate_thermal_factor(
            temperature=30.0,
            humidity=60.0,
            heat_acclimation_days=0.0,
            is_retractable_roof=False,
            ppda=8.2
        )
        
        # Qatar: high PPDA -> low multiplier
        factor_qatar = calculate_thermal_factor(
            temperature=30.0,
            humidity=60.0,
            heat_acclimation_days=0.0,
            is_retractable_roof=False,
            ppda=15.2
        )
        
        # Spain is more vulnerable to heat, so their thermal factor is lower
        self.assertTrue(factor_spain < factor_qatar)
        self.assertTrue(factor_spain < 1.0)
        self.assertTrue(factor_qatar < 1.0)


class TestWeatherClient(unittest.TestCase):
    @patch("utils.weather_client.WeatherClient._fetch_url_json")
    def test_weather_client_parsing(self, mock_fetch):
        # Mock Open-Meteo forecast API response
        mock_fetch.return_value = {
            "hourly": {
                "time": ["2026-06-11T19:00", "2026-06-11T20:00", "2026-06-11T21:00"],
                "temperature_2m": [26.5, 27.5, 25.5],
                "relative_humidity_2m": [60.0, 65.0, 70.0]
            }
        }
        
        client = WeatherClient(cache_path="data/test_weather_cache.json")
        
        # Run async call using asyncio.run
        temp, humidity = asyncio.run(
            client.get_weather_async(city="Miami", date_str="2026-06-11", time_str="20:00")
        )
        
        # Should match exact hour index (index 1 -> temp 27.5, hum 65.0)
        self.assertEqual(temp, 27.5)
        self.assertEqual(humidity, 65.0)
        
        # Clean up test cache file
        if os.path.exists("data/test_weather_cache.json"):
            try:
                os.remove("data/test_weather_cache.json")
            except Exception:
                pass
