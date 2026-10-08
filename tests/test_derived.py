"""Computed values: the dew point from temperature and humidity, the dew point spread, their channels,
the custom action of ObservingConditions and the two sensors."""

import asyncio
import importlib
import types
from datetime import timedelta

import pytest

from ha_stubs import FakeHass, FakeRegistryEntry

derived = importlib.import_module("ascom_alpaca_server.derived")
ha_bridge = importlib.import_module("ascom_alpaca_server.ha_bridge")
observing_conditions = importlib.import_module("ascom_alpaca_server.alpaca.handlers.observing_conditions")
registry_module = importlib.import_module("ascom_alpaca_server.alpaca.device_registry")
sensor_module = importlib.import_module("ascom_alpaca_server.sensor")
const = importlib.import_module("ascom_alpaca_server.const")


def run(coroutine):
    return asyncio.run(coroutine)


# ---- the formula -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "temperature, humidity, expected",
    [(20, 50, 9.255), (25, 60, 16.693), (10, 80, 6.706), (-10, 70, -14.439), (35, 40, 19.384), (15.4, 69, 9.738)],
)
def test_the_dew_point_follows_the_magnus_formula(temperature, humidity, expected):
    assert derived.dew_point(temperature, humidity) == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize("temperature", [-45, -10, 0, 20, 60])
def test_at_full_humidity_the_dew_point_is_the_temperature(temperature):
    assert derived.dew_point(temperature, 100) == pytest.approx(temperature, abs=1e-9)


def test_the_dew_point_is_never_above_the_temperature():
    for temperature in range(-40, 61, 5):
        for humidity in (1, 20, 50, 99, 100):
            assert derived.dew_point(temperature, humidity) <= temperature + 1e-9


@pytest.mark.parametrize(
    "temperature, humidity",
    [(None, 50), (20, None), (None, None), (20, 0), (20, -5), (20, 101), (-46, 50), (61, 50)],
)
def test_no_dew_point_without_valid_values(temperature, humidity):
    assert derived.dew_point(temperature, humidity) is None


@pytest.mark.parametrize("temperature, humidity", [(-45, 50), (60, 50), (20, 100), (20, 0.5)])
def test_the_limits_of_the_valid_range_still_work(temperature, humidity):
    assert derived.dew_point(temperature, humidity) is not None


def test_the_spread_is_temperature_minus_dew_point():
    assert derived.dew_point_spread(15.4, 9.8) == pytest.approx(5.6)
    assert derived.dew_point_spread(3.0, 4.0) == pytest.approx(-1.0)  # a sensor error stays visible
    assert derived.dew_point_spread(None, 9.8) is None
    assert derived.dew_point_spread(15.4, None) is None


# ---- channels ---------------------------------------------------------------------------------------------------
def make_hass(**sensors):
    """Temperature in sensor.t, humidity in sensor.h, a dew point in sensor.d, each given as a state."""
    hass = FakeHass()
    units = {"t": "°C", "d": "°C", "h": "%"}
    for key, value in sensors.items():
        hass.states.set(f"sensor.{key}", value, {"unit_of_measurement": units[key]})
    return hass


def channels_of(hass, **mapping):
    return ha_bridge._build_oc_channels(hass, {prop: [f"sensor.{key}"] for prop, key in mapping.items()})


def test_the_dew_point_is_computed_when_only_temperature_and_humidity_are_mapped():
    channels = channels_of(make_hass(t="20", h="50"), temperature="t", humidity="h")
    dew = channels["dewpoint"]
    assert dew.computed is True
    assert "Magnus" in dew.description
    assert run(dew.get_value()) == pytest.approx(9.255, abs=0.01)


def test_a_mapped_dew_point_always_wins():
    channels = channels_of(make_hass(t="20", h="50", d="12.5"), temperature="t", humidity="h", dewpoint="d")
    assert channels["dewpoint"].computed is False
    assert run(channels["dewpoint"].get_value()) == 12.5


@pytest.mark.parametrize(
    "mapping",
    [{"temperature": "t"}, {"humidity": "h"}, {"temperature": "t", "windspeed": "h"}, {}],
)
def test_no_dew_point_is_computed_without_both_temperature_and_humidity(mapping):
    assert "dewpoint" not in channels_of(make_hass(t="20", h="50"), **mapping)


def test_a_source_without_a_value_gives_no_dew_point_and_no_age():
    channels = channels_of(make_hass(t="20", h="unavailable"), temperature="t", humidity="h")
    assert run(channels["dewpoint"].get_value()) is None
    assert run(channels["dewpoint"].get_seconds_since_update()) is None


def test_the_age_of_a_computed_value_is_the_older_one_of_its_sources():
    hass = make_hass(t="20", h="50")
    hass.states.get("sensor.t").last_reported -= timedelta(seconds=100)
    hass.states.get("sensor.h").last_reported -= timedelta(seconds=30)
    channels = channels_of(hass, temperature="t", humidity="h")
    assert run(channels["dewpoint"].get_seconds_since_update()) == pytest.approx(100, abs=3)


def test_the_temperature_is_converted_before_the_dew_point_is_computed():
    hass = FakeHass()
    hass.states.set("sensor.t", "68", {"unit_of_measurement": "°F"})  # 20 °C
    hass.states.set("sensor.h", "50", {"unit_of_measurement": "%"})
    channels = ha_bridge._build_oc_channels(
        hass, {"temperature": ["sensor.t"], "humidity": ["sensor.h"]}
    )
    assert run(channels["dewpoint"].get_value()) == pytest.approx(9.255, abs=0.01)


def test_the_sources_may_be_a_weather_entity():
    hass = FakeHass()
    hass.states.set("weather.home", "cloudy", {"temperature": 20, "temperature_unit": "°C", "humidity": 50})
    channels = ha_bridge._build_oc_channels(
        hass, {"temperature": ["weather.home"], "humidity": ["weather.home"]}
    )
    assert run(channels["dewpoint"].get_value()) == pytest.approx(9.255, abs=0.01)


# ---- the spread -----------------------------------------------------------------------------------------------------
def test_the_spread_needs_temperature_and_a_dew_point_mapped_or_computed():
    hass = make_hass(t="20", h="50", d="12.5")

    mapped = ha_bridge.build_oc_extras(channels_of(hass, temperature="t", dewpoint="d"))
    assert run(mapped["DewPointSpread"].get_value()) == pytest.approx(7.5)

    computed = ha_bridge.build_oc_extras(channels_of(hass, temperature="t", humidity="h"))
    assert run(computed["DewPointSpread"].get_value()) == pytest.approx(20 - 9.255, abs=0.01)

    assert ha_bridge.build_oc_extras(channels_of(hass, dewpoint="d")) == {}  # no temperature
    assert ha_bridge.build_oc_extras(channels_of(hass, temperature="t")) == {}  # no dew point
    assert ha_bridge.build_oc_extras(channels_of(hass, humidity="h")) == {}


def test_the_spread_has_no_value_while_a_source_has_none():
    extras = ha_bridge.build_oc_extras(channels_of(make_hass(t="unavailable", d="5"), temperature="t", dewpoint="d"))
    assert run(extras["DewPointSpread"].get_value()) is None
    assert run(extras["DewPointSpread"].get_seconds_since_update()) is None


# ---- which sensors exist ----------------------------------------------------------------------------------------------
def flags_of(mapping):
    registry = registry_module.AlpacaDeviceRegistry("test")
    options = {"observing_conditions": {prop: [f"sensor.{key}"] for prop, key in mapping.items()}}
    return ha_bridge.rebuild_devices(registry, make_hass(t="20", h="50", d="12"), options).flags


@pytest.mark.parametrize(
    "mapping, expected",
    [
        ({"temperature": "t", "humidity": "h"}, (True, True)),  # case A: both are computed
        ({"temperature": "t", "dewpoint": "d"}, (False, True)),  # case B: only the spread is computed
        ({"temperature": "t", "humidity": "h", "dewpoint": "d"}, (False, True)),  # the mapped one wins
        ({"temperature": "t"}, (False, False)),  # case C
        ({"humidity": "h"}, (False, False)),
        ({"dewpoint": "d"}, (False, False)),
        ({}, (False, False)),
    ],
)
def test_which_values_are_computed(mapping, expected):
    assert flags_of(mapping) == expected


# ---- the custom action -----------------------------------------------------------------------------------------------------
def oc_handler(hass, **mapping):
    channels = channels_of(hass, **mapping)
    return observing_conditions.create_oc_handler(channels, actions=ha_bridge.build_oc_extras(channels))


def call(handler, action, params=None):
    return run(handler(action, params or {}))


def test_supported_actions_list_the_spread_when_it_exists():
    hass = make_hass(t="20", h="50")
    assert call(oc_handler(hass, temperature="t", humidity="h"), "supportedactions")["Value"] == ["DewPointSpread"]
    assert call(oc_handler(hass, temperature="t"), "supportedactions")["Value"] == []


def test_the_action_returns_the_spread_as_text_with_one_decimal():
    handler = oc_handler(make_hass(t="20", h="50"), temperature="t", humidity="h")
    assert call(handler, "action", {"Action": "DewPointSpread", "Parameters": ""}) == {"Value": "10.7"}


def test_the_action_name_is_not_case_sensitive_and_the_parameters_are_optional():
    handler = oc_handler(make_hass(t="20", d="12.5"), temperature="t", dewpoint="d")
    assert call(handler, "action", {"Action": "dewpointspread"}) == {"Value": "7.5"}


def test_an_unknown_action_is_action_not_implemented():
    handler = oc_handler(make_hass(t="20", h="50"), temperature="t", humidity="h")
    result = call(handler, "action", {"Action": "Nonsense", "Parameters": ""})
    assert result["ErrorNumber"] == 0x40C
    assert "HttpStatus" not in result  # an ASCOM exception, HTTP 200


def test_without_a_spread_every_action_is_not_implemented():
    handler = oc_handler(make_hass(t="20"), temperature="t")
    assert call(handler, "action", {"Action": "DewPointSpread"})["ErrorNumber"] == 0x40C


def test_the_action_without_a_value_is_value_not_set():
    handler = oc_handler(make_hass(t="20", h="unavailable"), temperature="t", humidity="h")
    result = call(handler, "action", {"Action": "DewPointSpread"})
    assert result["ErrorNumber"] == 0x402


@pytest.mark.parametrize("params", [{}, {"action": "DewPointSpread"}, {"ACTION": "DewPointSpread"}])
def test_the_action_field_has_to_be_there_and_exactly_spelled(params):
    handler = oc_handler(make_hass(t="20", h="50"), temperature="t", humidity="h")
    assert call(handler, "action", params)["HttpStatus"] == 400


def test_the_computed_dew_point_is_a_normal_property_of_the_device():
    handler = oc_handler(make_hass(t="20", h="50"), temperature="t", humidity="h")
    assert call(handler, "dewpoint")["Value"] == pytest.approx(9.255, abs=0.01)
    assert "Magnus" in call(handler, "sensordescription", {"SensorName": "DewPoint"})["Value"]
    assert call(handler, "timesincelastupdate", {"SensorName": "DewPoint"})["Value"] < 5
    assert "dewpoint (computed)" in call(handler, "description")["Value"]


# ---- the sensors ---------------------------------------------------------------------------------------------------------------
ENTRY = types.SimpleNamespace(entry_id="E")


def data_for(hass, **mapping):
    registry = registry_module.AlpacaDeviceRegistry("test")
    options = {"observing_conditions": {prop: [f"sensor.{key}"] for prop, key in mapping.items()}}
    return {const.DATA_DERIVED: ha_bridge.rebuild_devices(registry, hass, options)}


def test_the_computed_dew_point_sensor():
    data = data_for(make_hass(t="20", h="50"), temperature="t", humidity="h")
    sensor = sensor_module.ComputedDewPointSensor(ENTRY, data)

    assert sensor.available is False  # nothing read yet
    run(sensor.async_update())

    assert sensor.available is True
    assert sensor._attr_native_value == 9.3
    assert sensor._attr_name == "Dew Point"
    assert sensor._attr_unique_id == "E_dew_point"
    assert sensor._attr_native_unit_of_measurement == "°C"
    assert sensor._attr_device_class == "temperature"
    assert "Magnus" in sensor._attr_extra_state_attributes["method"]


def test_the_spread_sensor_is_no_temperature_to_convert():
    data = data_for(make_hass(t="20", h="50"), temperature="t", humidity="h")
    sensor = sensor_module.DewPointSpreadSensor(ENTRY, data)
    run(sensor.async_update())

    assert sensor._attr_native_value == 10.7
    assert sensor._attr_name == "Dew Point Spread"
    assert sensor._attr_unique_id == "E_dew_point_spread"
    assert sensor._attr_native_unit_of_measurement == "°C"
    # a difference: with the device class "temperature" Home Assistant would convert it like a temperature
    assert getattr(sensor, "_attr_device_class", None) is None


def test_a_sensor_is_unavailable_while_a_source_has_no_value():
    hass = make_hass(t="20", h="50")
    data = data_for(hass, temperature="t", humidity="h")
    sensor = sensor_module.ComputedDewPointSensor(ENTRY, data)
    run(sensor.async_update())
    assert sensor.available is True

    hass.states.set("sensor.h", "unavailable")
    run(sensor.async_update())
    assert sensor.available is False
    assert sensor._attr_native_value is None


def test_a_sensor_follows_a_new_mapping_without_being_created_again():
    hass = make_hass(t="20", h="50", d="10")
    data = data_for(hass, temperature="t", humidity="h")
    sensor = sensor_module.DewPointSpreadSensor(ENTRY, data)
    run(sensor.async_update())
    assert sensor._attr_native_value == 10.7  # with the computed dew point 9.3

    # the dew point is mapped now: the options flow rebuilds the devices and replaces the channels
    registry = registry_module.AlpacaDeviceRegistry("test")
    options = {"observing_conditions": {"temperature": ["sensor.t"], "dewpoint": ["sensor.d"]}}
    data[const.DATA_DERIVED] = ha_bridge.rebuild_devices(registry, hass, options)
    run(sensor.async_update())
    assert sensor._attr_native_value == 10.0


def test_the_sensors_are_polled_once_a_minute():
    assert sensor_module.SCAN_INTERVAL == timedelta(seconds=60)


# ---- the sensor platform ------------------------------------------------------------------------------------------------
def set_up_platform(hass, **mapping):
    hass.data = {const.DOMAIN: {"E": data_for(hass, **mapping)}}
    added = []
    run(sensor_module.async_setup_entry(hass, ENTRY, lambda entities, update=False: added.extend(entities)))
    return added


@pytest.mark.parametrize(
    "mapping, names",
    [
        ({"temperature": "t", "humidity": "h"}, ["Dew Point", "Dew Point Spread"]),  # case A
        ({"temperature": "t", "dewpoint": "d"}, ["Dew Point Spread"]),  # case B
        ({"temperature": "t"}, []),  # case C
    ],
)
def test_only_the_sensors_of_computed_values_are_created(mapping, names):
    added = set_up_platform(make_hass(t="20", h="50", d="12"), **mapping)
    assert [entity._attr_name for entity in added] == names


def test_a_sensor_of_a_value_that_is_not_computed_any_more_is_removed_from_the_registry():
    hass = make_hass(t="20", h="50", d="12")
    hass.entity_registry.entries = [
        FakeRegistryEntry("sensor.server_dew_point", "E_dew_point"),
        FakeRegistryEntry("sensor.server_dew_point_spread", "E_dew_point_spread"),
        FakeRegistryEntry("sensor.somebody_else", "other_unique_id"),
    ]
    set_up_platform(hass, temperature="t", dewpoint="d")  # the dew point is mapped now

    assert hass.entity_registry.removed == ["sensor.server_dew_point"]
