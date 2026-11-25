"""Wetter über Open-Meteo (kostenlos, ohne API-Key)."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass

API_URL = "https://api.open-meteo.com/v1/forecast"

# WMO-Wettercodes -> (Beschreibung, Symbol)
WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("Klar", "☀️"),
    1: ("Überwiegend klar", "🌤️"),
    2: ("Teilweise bewölkt", "⛅"),
    3: ("Bedeckt", "☁️"),
    45: ("Nebel", "🌫️"),
    48: ("Reifnebel", "🌫️"),
    51: ("Leichter Nieselregen", "🌦️"),
    53: ("Nieselregen", "🌦️"),
    55: ("Starker Nieselregen", "🌧️"),
    56: ("Gefrierender Nieselregen", "🌧️"),
    57: ("Starker gefrierender Nieselregen", "🌧️"),
    61: ("Leichter Regen", "🌦️"),
    63: ("Regen", "🌧️"),
    65: ("Starker Regen", "🌧️"),
    66: ("Gefrierender Regen", "🌧️"),
    67: ("Starker gefrierender Regen", "🌧️"),
    71: ("Leichter Schneefall", "🌨️"),
    73: ("Schneefall", "🌨️"),
    75: ("Starker Schneefall", "❄️"),
    77: ("Schneegriesel", "🌨️"),
    80: ("Leichte Regenschauer", "🌦️"),
    81: ("Regenschauer", "🌧️"),
    82: ("Heftige Regenschauer", "⛈️"),
    85: ("Leichte Schneeschauer", "🌨️"),
    86: ("Schneeschauer", "🌨️"),
    95: ("Gewitter", "⛈️"),
    96: ("Gewitter mit Hagel", "⛈️"),
    99: ("Schweres Gewitter mit Hagel", "⛈️"),
}


@dataclass
class Weather:
    place: str
    temperature: float
    description: str
    icon: str
    wind_kmh: float
    temp_max: float
    temp_min: float
    rain_probability: int | None


def describe(code: int) -> tuple[str, str]:
    return WMO_CODES.get(code, ("Unbekannt", "❔"))


def build_url(latitude: float, longitude: float) -> str:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": 1,
    }
    return f"{API_URL}?{urllib.parse.urlencode(params)}"


def parse(payload: dict, place: str) -> Weather:
    current = payload["current"]
    daily = payload.get("daily", {})
    description, icon = describe(int(current["weather_code"]))
    rain = (daily.get("precipitation_probability_max") or [None])[0]
    return Weather(
        place=place,
        temperature=float(current["temperature_2m"]),
        description=description,
        icon=icon,
        wind_kmh=float(current.get("wind_speed_10m", 0.0)),
        temp_max=float(daily["temperature_2m_max"][0]),
        temp_min=float(daily["temperature_2m_min"][0]),
        rain_probability=None if rain is None else int(rain),
    )


class WeatherError(Exception):
    pass


def fetch(cfg: dict, get_json) -> Weather:
    payload = get_json(build_url(cfg["latitude"], cfg["longitude"]))
    try:
        return parse(payload, cfg.get("place", ""))
    except (KeyError, IndexError, TypeError, ValueError) as err:
        reason = payload.get("reason") if isinstance(payload, dict) else None
        raise WeatherError(f"Unerwartete Antwort von Open-Meteo{f': {reason}' if reason else ''}") from err
