"""ObservingConditions values must reach Alpaca clients in ASCOM units."""

import asyncio
import importlib
from datetime import timedelta

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


# ---- the handler: errors, ages and names -----------------------------------------------------------------------------
observing_conditions = importlib.import_module(
    "ascom_alpaca_server.alpaca.handlers.observing_conditions"
)


def oc_handler(hass, mapping):
    channels = ha_bridge._build_oc_channels(hass, mapping)
    return observing_conditions.create_oc_handler(channels)


def call(handler, action, params=None):
    return asyncio.run(handler(action, params or {}))


def test_a_mapped_sensor_without_a_value_is_value_not_set_not_not_implemented():
    """NotImplemented makes clients hide the property: the sensor is there, it has no value now."""
    hass = FakeHass()
    hass.states.set("sensor.t", "unavailable")
    result = call(oc_handler(hass, {"temperature": ["sensor.t"]}), "temperature")
    assert result["ErrorNumber"] == 0x402
    assert "HttpStatus" not in result


def test_a_property_without_a_sensor_is_not_implemented():
    hass = FakeHass()
    hass.states.set("sensor.t", "5")
    result = call(oc_handler(hass, {"temperature": ["sensor.t"]}), "humidity")
    assert result["ErrorNumber"] == 0x400


def test_the_age_of_a_sensor_follows_its_reports_not_its_changes():
    """A sensor that keeps reporting the same value is not old (last_updated only moves on a change)."""
    hass = FakeHass()
    hass.states.set("sensor.t", "5")
    state = hass.states.get("sensor.t")
    state.last_updated = state.last_updated - timedelta(hours=1)  # the value has not changed for an hour
    handler = oc_handler(hass, {"temperature": ["sensor.t"]})

    assert call(handler, "timesincelastupdate", {"SensorName": "temperature"})["Value"] < 5
    assert call(handler, "timesincelastupdate")["Value"] < 5

    state.last_reported = state.last_reported - timedelta(seconds=90)  # no report for 90 s
    assert call(handler, "timesincelastupdate", {"SensorName": "temperature"})["Value"] == pytest.approx(90, abs=3)


def test_the_age_of_the_freshest_available_sensor_counts():
    hass = FakeHass()
    hass.states.set("sensor.t", "5")
    hass.states.set("sensor.h", "50")
    hass.states.set("sensor.p", "unavailable")
    hass.states.get("sensor.t").last_reported -= timedelta(seconds=300)
    handler = oc_handler(
        hass, {"temperature": ["sensor.t"], "humidity": ["sensor.h"], "pressure": ["sensor.p"]}
    )
    assert call(handler, "timesincelastupdate")["Value"] < 5  # humidity


def test_without_any_sensor_value_the_age_is_value_not_set_not_zero():
    """0 seconds would make a dead sensor look fresh."""
    hass = FakeHass()
    hass.states.set("sensor.t", "unavailable")
    handler = oc_handler(hass, {"temperature": ["sensor.t"]})
    assert call(handler, "timesincelastupdate")["ErrorNumber"] == 0x402
    assert call(handler, "timesincelastupdate", {"SensorName": "temperature"})["ErrorNumber"] == 0x402


@pytest.mark.parametrize("action", ["timesincelastupdate", "sensordescription"])
def test_an_unknown_sensor_name_is_an_invalid_value(action):
    hass = FakeHass()
    hass.states.set("sensor.t", "5")
    result = call(oc_handler(hass, {"temperature": ["sensor.t"]}), action, {"SensorName": "weather"})
    assert result["ErrorNumber"] == 0x401


@pytest.mark.parametrize("action", ["timesincelastupdate", "sensordescription"])
def test_a_known_sensor_that_is_not_mapped_is_not_implemented(action):
    hass = FakeHass()
    hass.states.set("sensor.t", "5")
    result = call(oc_handler(hass, {"temperature": ["sensor.t"]}), action, {"SensorName": "humidity"})
    assert result["ErrorNumber"] == 0x400


def test_the_description_of_a_mapped_sensor():
    hass = FakeHass()
    hass.states.set("sensor.t", "5")
    result = call(oc_handler(hass, {"temperature": ["sensor.t"]}), "sensordescription", {"SensorName": "Temperature"})
    assert "sensor.t" in result["Value"]


# ---- values from a weather entity -------------------------------------------------------------------------------------
unit_conversion = importlib.import_module("ascom_alpaca_server.unit_conversion")

HOME = {
    "temperature": 50,
    "temperature_unit": "°F",
    "dew_point": 32,
    "humidity": 80,
    "pressure": 29.92,
    "pressure_unit": "inHg",
    "wind_speed": 36,
    "wind_gust_speed": 10,
    "wind_speed_unit": "km/h",
    "wind_bearing": 225,
    "cloud_coverage": 40,
}


@pytest.mark.parametrize(
    "prop, expected",
    [
        ("temperature", 10.0),  # 50 °F
        ("dewpoint", 0.0),  # 32 °F, the unit of the temperature
        ("humidity", 80.0),
        ("pressure", 1013.2),  # 29.92 inHg
        ("windspeed", 10.0),  # 36 km/h
        ("windgust", 10 / 3.6),
        ("winddirection", 225.0),
        ("cloudcover", 40.0),
    ],
)
def test_a_weather_entity_provides_the_values_in_alpaca_units(prop, expected):
    assert unit_conversion.weather_value(prop, HOME) == pytest.approx(expected, rel=1e-3)


@pytest.mark.parametrize("prop", ["rainrate", "skybrightness", "skyquality", "skytemperature", "starfwhm", "nonsense"])
def test_a_weather_entity_has_no_value_for_the_other_properties(prop):
    assert unit_conversion.weather_value(prop, HOME) is None


@pytest.mark.parametrize(
    "bearing, degrees",
    [("N", 0), ("nne", 22.5), ("E", 90), ("SW", 225), ("WNW", 292.5), ("NNW", 337.5), (" s ", 180), ("90", 90.0), (45.5, 45.5)],
)
def test_the_wind_direction_may_be_a_compass_point(bearing, degrees):
    assert unit_conversion.weather_value("winddirection", {"wind_bearing": bearing}) == degrees


@pytest.mark.parametrize(
    "attributes",
    [{}, {"temperature": None}, {"temperature": "warm"}, {"wind_bearing": "somewhere"}],
)
def test_a_weather_entity_without_a_usable_value_has_none(attributes):
    assert unit_conversion.weather_value("temperature", attributes) is None
    assert unit_conversion.weather_value("winddirection", attributes) is None


def test_without_a_unit_attribute_the_value_is_passed_through():
    assert unit_conversion.weather_value("temperature", {"temperature": 7}) == 7.0


def weather_hass(**attributes):
    hass = FakeHass()
    hass.states.set("weather.home", "sunny", attributes or HOME)
    return hass


def test_an_observing_conditions_value_can_come_from_a_weather_entity():
    hass = weather_hass()
    assert read(hass, "temperature", ["weather.home"]) == pytest.approx(10.0)
    assert read(hass, "windspeed", ["weather.home"]) == pytest.approx(10.0)
    assert read(hass, "winddirection", ["weather.home"]) == 225.0


def test_a_property_the_weather_entity_does_not_have_has_no_value():
    assert read(weather_hass(), "rainrate", ["weather.home"]) is None


def test_the_fallback_goes_from_a_sensor_to_a_weather_entity_and_back():
    hass = weather_hass()
    hass.states.set("sensor.station", "unavailable", {"unit_of_measurement": "°C"})
    assert read(hass, "temperature", ["sensor.station", "weather.home"]) == pytest.approx(10.0)

    hass.states.set("sensor.station", "3", {"unit_of_measurement": "°C"})
    assert read(hass, "temperature", ["sensor.station", "weather.home"]) == 3.0  # the sensor first
    assert read(hass, "temperature", ["weather.home", "sensor.station"]) == pytest.approx(10.0)


def test_a_weather_entity_that_cannot_answer_falls_back_to_the_next_entity():
    hass = weather_hass()
    hass.states.set("sensor.rain", "2.5", {"unit_of_measurement": "mm/h"})
    assert read(hass, "rainrate", ["weather.home", "sensor.rain"]) == 2.5


def test_an_unavailable_weather_entity_is_skipped():
    hass = FakeHass()
    hass.states.set("weather.home", "unavailable", HOME)
    assert read(hass, "temperature", ["weather.home"]) is None


def test_the_handler_answers_from_a_weather_entity():
    hass = weather_hass()
    handler = oc_handler(hass, {"temperature": ["weather.home"], "humidity": ["weather.home"]})
    assert call(handler, "temperature")["Value"] == pytest.approx(10.0)
    assert call(handler, "humidity")["Value"] == 80.0
    assert call(handler, "timesincelastupdate", {"SensorName": "temperature"})["Value"] < 5
