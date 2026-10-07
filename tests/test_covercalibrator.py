"""Flat panel (CoverCalibrator): brightness range and entity combinations."""

import asyncio
import importlib

import pytest

from ha_stubs import FakeHass

ha_bridge = importlib.import_module("ascom_alpaca_server.ha_bridge")
covercalibrator = importlib.import_module(
    "ascom_alpaca_server.alpaca.handlers.covercalibrator"
)


def handler_for(hass, onoff, brightness):
    channel = ha_bridge._build_calibrator_channel(hass, onoff, brightness)
    return covercalibrator.create_covercalibrator_handler(channel)


def call(handler, action, params=None):
    return asyncio.run(handler(action, params or {}))


def test_number_entity_range_comes_from_max_attribute():
    hass = FakeHass()
    hass.states.set("number.panel", "0", {"max": 100.0, "min": 0.0})
    handler = handler_for(hass, "", "number.panel")
    assert call(handler, "maxbrightness")["Value"] == 100
    assert call(handler, "calibratoron", {"Brightness": "50"})["Value"] is None
    assert hass.services.calls == [
        ("number", "set_value", {"entity_id": "number.panel", "value": 50})
    ]


def test_brightness_is_clamped_to_entity_range():
    hass = FakeHass()
    hass.states.set("number.panel", "0", {"max": 100})
    handler = handler_for(hass, "", "number.panel")
    call(handler, "calibratoron", {"Brightness": "500"})
    assert hass.services.calls[-1][2]["value"] == 100


@pytest.mark.parametrize("params", [{}, {"Brightness": "abc"}, {"brightness": "50"}])
def test_missing_or_invalid_brightness_is_a_bad_request_not_full_power(params):
    hass = FakeHass()
    hass.states.set("number.panel", "0", {"max": 100})
    handler = handler_for(hass, "", "number.panel")
    result = call(handler, "calibratoron", params)
    assert result["HttpStatus"] == 400
    assert hass.services.calls == []


def test_number_without_max_attribute_falls_back_to_255():
    hass = FakeHass()
    hass.states.set("number.panel", "0", {})
    assert call(handler_for(hass, "", "number.panel"), "maxbrightness")["Value"] == 255


def test_light_and_switch_use_255():
    hass = FakeHass()
    hass.states.set("light.panel", "off", {})
    hass.states.set("switch.panel", "off", {})
    assert call(handler_for(hass, "light.panel", ""), "maxbrightness")["Value"] == 255
    assert call(handler_for(hass, "switch.panel", ""), "maxbrightness")["Value"] == 255


def test_light_only_sends_brightness_to_the_light():
    hass = FakeHass()
    hass.states.set("light.panel", "off", {})
    call(handler_for(hass, "light.panel", ""), "calibratoron", {"Brightness": "128"})
    assert hass.services.calls == [
        ("light", "turn_on", {"entity_id": "light.panel", "brightness": 128})
    ]


def test_switch_plus_separate_light():
    hass = FakeHass()
    hass.states.set("switch.panel", "off", {})
    hass.states.set("light.dim", "off", {})
    handler = handler_for(hass, "switch.panel", "light.dim")

    call(handler, "calibratoron", {"Brightness": "128"})
    assert ("light", "turn_on", {"entity_id": "light.dim", "brightness": 128}) in hass.services.calls
    assert ("switch", "turn_on", {"entity_id": "switch.panel"}) in hass.services.calls

    hass.services.calls.clear()
    call(handler, "calibratoroff")
    assert ("light", "turn_off", {"entity_id": "light.dim"}) in hass.services.calls
    assert ("switch", "turn_off", {"entity_id": "switch.panel"}) in hass.services.calls


def test_light_plus_number_sets_the_number_not_the_light_brightness():
    hass = FakeHass()
    hass.states.set("light.panel", "off", {})
    hass.states.set("number.level", "0", {"max": 100})
    handler = handler_for(hass, "light.panel", "number.level")
    call(handler, "calibratoron", {"Brightness": "40"})
    assert ("number", "set_value", {"entity_id": "number.level", "value": 40}) in hass.services.calls
    assert ("light", "turn_on", {"entity_id": "light.panel"}) in hass.services.calls
