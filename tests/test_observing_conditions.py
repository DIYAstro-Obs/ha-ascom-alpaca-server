"""ObservingConditions values must reach Alpaca clients in ASCOM units."""

import asyncio
import importlib

import pytest

from ha_stubs import FakeHass

ha_bridge = importlib.import_module("ascom_alpaca_server.ha_bridge")


def read(hass, prop, entity_ids):
    channels = ha_bridge._build_oc_channels(hass, {prop: entity_ids})
    return asyncio.run(channels[prop].get_value())


@pytest.mark.parametrize(
    "prop,value,unit,expected",
    [
        ("windspeed", "36", "km/h", 10.0),
        ("windgust", "10", "mph", 4.4704),
        ("windspeed", "10", "kn", 5.14444),
        ("temperature", "50", "°F", 10.0),
        ("temperature", "273.15", "K", 0.0),
        ("dewpoint", "32", "°F", 0.0),
        ("pressure", "29.92", "inHg", 1013.2),
        ("pressure", "101325", "Pa", 1013.25),
        ("pressure", "1013", "mbar", 1013.0),
        ("rainrate", "1", "in/h", 25.4),
        ("rainrate", "24", "mm/d", 1.0),
        # no conversion defined / no unit / unknown unit: passed through
        ("humidity", "55", "%", 55.0),
        ("windspeed", "7", None, 7.0),
        ("windspeed", "7", "furlongs/fortnight", 7.0),
    ],
)
def test_unit_conversion(prop, value, unit, expected):
    hass = FakeHass()
    attributes = {"unit_of_measurement": unit} if unit else {}
    hass.states.set("sensor.x", value, attributes)
    assert read(hass, prop, ["sensor.x"]) == pytest.approx(expected, rel=1e-3)


def test_fallback_converts_the_entity_that_answers():
    hass = FakeHass()
    hass.states.set("sensor.a", "unavailable", {"unit_of_measurement": "km/h"})
    hass.states.set("sensor.b", "10", {"unit_of_measurement": "mph"})
    assert read(hass, "windspeed", ["sensor.a", "sensor.b"]) == pytest.approx(4.4704)


def test_all_unavailable_returns_none():
    hass = FakeHass()
    hass.states.set("sensor.a", "unavailable")
    assert read(hass, "windspeed", ["sensor.a"]) is None
