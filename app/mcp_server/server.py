import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("travel-live-data")

HTTP_TIMEOUT = 10.0
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
EXCHANGE_URL = "https://api.frankfurter.dev/v1/latest"

WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    95: "thunderstorm", 96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
}


@mcp.tool()
def get_weather(location: str, forecast_days: int = 3) -> dict:
    """Get current conditions and a daily forecast for a location.

    Args:
        location: City or place name, e.g. "Singapore".
        forecast_days: Number of forecast days to return (1-7).
    """
    forecast_days = max(1, min(forecast_days, 7))

    try:
        geo_resp = httpx.get(
            GEOCODE_URL,
            params={"name": location, "count": 1},
            timeout=HTTP_TIMEOUT,
        )
        geo_resp.raise_for_status()
        geo_results = geo_resp.json().get("results")
        if not geo_results:
            return {"error": f"Could not find a location matching '{location}'."}

        place = geo_results[0]
        lat, lon = place["latitude"], place["longitude"]

        forecast_resp = httpx.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,relative_humidity_2m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": forecast_days,
                "timezone": "auto",
            },
            timeout=HTTP_TIMEOUT,
        )
        forecast_resp.raise_for_status()
        data = forecast_resp.json()
    except httpx.HTTPError as exc:
        return {"error": f"Weather service unavailable: {exc}"}

    current = data.get("current", {})
    daily = data.get("daily", {})

    return {
        "location": f"{place.get('name')}, {place.get('country', '')}".strip(", "),
        "current": {
            "temperature_c": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "condition": WEATHER_CODES.get(current.get("weather_code"), "unknown"),
        },
        "daily_forecast": [
            {
                "date": daily["time"][i],
                "condition": WEATHER_CODES.get(daily["weather_code"][i], "unknown"),
                "max_temp_c": daily["temperature_2m_max"][i],
                "min_temp_c": daily["temperature_2m_min"][i],
                "rain_chance_pct": daily["precipitation_probability_max"][i],
            }
            for i in range(len(daily.get("time", [])))
        ],
        "source": "Open-Meteo",
    }


@mcp.tool()
def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert an amount from one currency to another using current reference rates.

    Args:
        amount: Amount to convert.
        from_currency: 3-letter ISO 4217 code, e.g. "USD".
        to_currency: 3-letter ISO 4217 code, e.g. "SGD".
    """
    from_currency = from_currency.strip().upper()
    to_currency = to_currency.strip().upper()

    if len(from_currency) != 3 or len(to_currency) != 3:
        return {"error": "Currency codes must be 3-letter ISO codes, e.g. USD, SGD, INR."}
    if amount < 0:
        return {"error": "Amount must be non-negative."}

    try:
        resp = httpx.get(
            EXCHANGE_URL,
            params={"amount": amount, "from": from_currency, "to": to_currency},
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        return {"error": f"Currency service unavailable: {exc}"}

    rates = data.get("rates", {})
    if to_currency not in rates:
        return {"error": f"Could not get a rate from {from_currency} to {to_currency}."}

    converted = rates[to_currency]
    return {
        "amount": amount,
        "from_currency": from_currency,
        "to_currency": to_currency,
        "converted_amount": converted,
        "rate": converted / amount if amount else None,
        "rate_date": data.get("date"),
        "source": "Frankfurter (ECB reference rates)",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
