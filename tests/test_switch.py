"""Switch device: reading and setting switches, errors for entities without a value."""

import asyncio
import importlib

import pytest

from ha_stubs import FakeHass

ha_bridge = importlib.import_module("ascom_alpaca_server.ha_bridge")
switch = importlib.import_module("ascom_alpaca_server.alpaca.handlers.switch")

PUMP = "switch.pump"
HEATER = "switch.heater"


def make_hass(pump="off", heater="off"):
    hass = FakeHass()
    hass.states.set(PUMP, pump)
    hass.states.set(HEATER, heater, {"friendly_name": "Dew heater"})
    return hass


def handler_for(hass, names=None):
    channels = ha_bridge._build_switch_channels(hass, [PUMP, HEATER], names or {PUMP: "Pump"})
    return switch.create_switch_handler(channels, device_name="HA Switches")


def call(handler, action, params=None):
    return asyncio.run(handler(action, params or {}))


# ---- information ---------------------------------------------------------------------------------------------
def test_the_names_come_from_the_options_or_from_home_assistant():
    handler = handler_for(make_hass())
    assert call(handler, "maxswitch")["Value"] == 2
    assert call(handler, "getswitchname", {"Id": "0"})["Value"] == "Pump"
    assert call(handler, "getswitchname", {"Id": "1"})["Value"] == "Dew heater"
    assert call(handler, "getswitchdescription", {"Id": "0"})["Value"] == f"HA entity: {PUMP}"


def test_the_value_range_is_off_or_on():
    handler = handler_for(make_hass())
    assert call(handler, "minswitchvalue", {"Id": "0"})["Value"] == 0.0
    assert call(handler, "maxswitchvalue", {"Id": "0"})["Value"] == 1.0
    assert call(handler, "switchstep", {"Id": "0"})["Value"] == 1.0
    assert call(handler, "canwrite", {"Id": "0"})["Value"] is True


# ---- reading --------------------------------------------------------------------------------------------------
def test_a_switch_reports_on_and_off():
    handler = handler_for(make_hass(pump="on", heater="off"))
    assert call(handler, "getswitch", {"Id": "0"})["Value"] is True
    assert call(handler, "getswitch", {"Id": "1"})["Value"] is False
    assert call(handler, "getswitchvalue", {"Id": "0"})["Value"] == 1.0
    assert call(handler, "getswitchvalue", {"Id": "1"})["Value"] == 0.0


@pytest.mark.parametrize("state", ["unavailable", "unknown"])
@pytest.mark.parametrize("action", ["getswitch", "getswitchvalue"])
def test_a_switch_without_a_value_is_an_error_not_off(state, action):
    """An unavailable pump is not "off": the client must not believe it."""
    result = call(handler_for(make_hass(pump=state)), action, {"Id": "0"})
    assert result["ErrorNumber"] == 0x500
    assert "HttpStatus" not in result  # an ASCOM exception: HTTP 200


def test_a_missing_entity_is_an_error_too():
    hass = FakeHass()
    hass.states.set(HEATER, "off")
    channels = ha_bridge._build_switch_channels(hass, [PUMP, HEATER], {PUMP: "Pump", HEATER: "Heater"})
    handler = switch.create_switch_handler(channels)
    assert call(handler, "getswitch", {"Id": "0"})["ErrorNumber"] == 0x500


# ---- setting --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value, service", [("True", "turn_on"), ("true", "turn_on"), ("False", "turn_off")])
def test_setswitch_calls_the_service(value, service):
    hass = make_hass()
    result = call(handler_for(hass), "setswitch", {"Id": "0", "State": value})
    assert result == {"Value": None}
    assert hass.services.calls == [("switch", service, {"entity_id": PUMP})]


def test_setswitchvalue_above_zero_is_on():
    hass = make_hass()
    handler = handler_for(hass)
    call(handler, "setswitchvalue", {"Id": "0", "Value": "0.5"})
    call(handler, "setswitchvalue", {"Id": "0", "Value": "0"})
    assert [service for _, service, _ in hass.services.calls] == ["turn_on", "turn_off"]


@pytest.mark.parametrize(
    "action, params",
    [
        ("setswitch", {"Id": "0"}),  # State missing
        ("setswitch", {"Id": "0", "State": "maybe"}),
        ("setswitchvalue", {"Id": "0"}),
        ("setswitchvalue", {"Id": "0", "Value": "abc"}),
        ("setswitchname", {"Id": "0"}),  # Name missing
        ("getswitch", {}),  # Id missing
        ("getswitch", {"Id": "abc"}),  # Id not a number
        ("nonsense", {}),
    ],
)
def test_a_request_that_is_not_understood_is_a_bad_request(action, params):
    hass = make_hass()
    result = call(handler_for(hass), action, params)
    assert result["HttpStatus"] == 400
    assert hass.services.calls == []


@pytest.mark.parametrize("action", ["getswitch", "getswitchname", "setswitch", "canwrite"])
@pytest.mark.parametrize("switch_id", ["2", "-1"])
def test_an_id_with_no_switch_is_an_invalid_value(action, switch_id):
    """An integer, but there is no such switch: an ASCOM exception (HTTP 200), not a bad request."""
    hass = make_hass()
    result = call(handler_for(hass), action, {"Id": switch_id, "State": "true"})
    assert result["ErrorNumber"] == 0x401
    assert "HttpStatus" not in result
    assert hass.services.calls == []


def test_the_names_cannot_be_changed_over_alpaca():
    result = call(handler_for(make_hass()), "setswitchname", {"Id": "0", "Name": "New"})
    assert result["ErrorNumber"] == 0x400
    assert "HttpStatus" not in result
