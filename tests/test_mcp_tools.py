"""
Unit tests for the MCP tool functions, with the HTTP layer mocked.
We test the underlying functions directly (via `.fn`, the raw Python callable
FastMCP wraps) rather than spinning up the stdio server — that's covered by
the manual end-to-end check in the README.
"""

import httpx
import pytest

from app.mcp_server.server import convert_currency, get_weather


class DummyResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


def test_get_weather_happy_path(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        if "geocoding" in url:
            return DummyResponse({"results": [{"name": "Singapore", "country": "Singapore", "latitude": 1.29, "longitude": 103.85}]})
        return DummyResponse(
            {
                "current": {"temperature_2m": 30, "relative_humidity_2m": 80, "weather_code": 1},
                "daily": {
                    "time": ["2026-01-01"],
                    "weather_code": [1],
                    "temperature_2m_max": [31],
                    "temperature_2m_min": [25],
                    "precipitation_probability_max": [20],
                },
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    result = get_weather("Singapore", forecast_days=1)

    assert "error" not in result
    assert result["location"] == "Singapore, Singapore"
    assert result["current"]["temperature_c"] == 30
    assert len(result["daily_forecast"]) == 1


def test_get_weather_unknown_location(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: DummyResponse({"results": []}))
    result = get_weather("Nowhereland")
    assert "error" in result


def test_get_weather_network_failure(monkeypatch):
    def fake_get(*a, **k):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)
    result = get_weather("Singapore")
    assert "error" in result


def test_convert_currency_happy_path(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: DummyResponse({"amount": 100.0, "rates": {"SGD": 1.75}, "date": "2026-01-01"}),
    )
    result = convert_currency(100, "USD", "SGD")

    assert "error" not in result
    assert result["converted_amount"] == 1.75
    assert result["from_currency"] == "USD"
    assert result["to_currency"] == "SGD"


def test_convert_currency_invalid_code():
    result = convert_currency(100, "US", "SGD")
    assert "error" in result


def test_convert_currency_negative_amount():
    result = convert_currency(-5, "USD", "SGD")
    assert "error" in result


def test_convert_currency_service_failure(monkeypatch):
    def fake_get(*a, **k):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)
    result = convert_currency(100, "USD", "SGD")
    assert "error" in result
