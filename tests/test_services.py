"""Commands wait for their Home Assistant service; a failure reaches the Alpaca client."""

import asyncio
import importlib

import pytest

from ha_stubs import FakeHass, HomeAssistantError

ha_bridge = importlib.import_module("ascom_alpaca_server.ha_bridge")
common = importlib.import_module("ascom_alpaca_server.alpaca.handlers._common")
dome = importlib.import_module("ascom_alpaca_server.alpaca.handlers.dome")
switch = importlib.import_module("ascom_alpaca_server.alpaca.handlers.switch")
covercalibrator = importlib.import_module("ascom_alpaca_server.alpaca.handlers.covercalibrator")


def run(coroutine):
    return asyncio.run(coroutine)


def dome_handler(hass):
    return dome.create_dome_handler(ha_bridge._build_dome_channel(hass, "cover.roof"))


def switch_handler(hass, *entities):
    channels = ha_bridge._build_switch_channels(hass, list(entities), {e: e for e in entities})
    return switch.create_switch_handler(channels)


def panel_handler(hass, onoff="", brightness=""):
    channel = ha_bridge._build_calibrator_channel(hass, onoff, brightness)
    return covercalibrator.create_covercalibrator_handler(channel)


# ---- the call waits ------------------------------------------------------------------------------------------------
def test_every_command_waits_for_its_service():
    hass = FakeHass()
    hass.states.set("cover.roof", "closed")
    hass.states.set("switch.pump", "off")
    hass.states.set("light.panel", "off")
    hass.states.set("number.level", "0", {"max": 100})

    run(dome_handler(hass)("openshutter", {}))
    run(switch_handler(hass, "switch.pump")("setswitch", {"Id": "0", "State": "true"}))
    run(panel_handler(hass, "light.panel", "number.level")("calibratoron", {"Brightness": "10"}))
    run(panel_handler(hass, "light.panel", "number.level")("calibratoroff", {}))

    assert hass.services.blocking
    assert all(hass.services.blocking)


# ---- a failing service is an error for the client -----------------------------------------------------------------
def test_a_service_that_fails_is_a_device_error_with_the_reason():
    hass = FakeHass()
    hass.services.error = HomeAssistantError("E-STOP is locked")
    with pytest.raises(common.DeviceError) as error:
        run(dome_handler(hass)("openshutter", {}))
    assert "cover.open_cover" in str(error.value)
    assert "E-STOP is locked" in str(error.value)


@pytest.mark.parametrize(
    "build, action, params",
    [
        (lambda hass: switch_handler(hass, "switch.pump"), "setswitch", {"Id": "0", "State": "true"}),
        (lambda hass: panel_handler(hass, "switch.panel"), "calibratoron", {"Brightness": "10"}),
        (lambda hass: panel_handler(hass, "switch.panel"), "calibratoroff", {}),
        (dome_handler, "closeshutter", {}),
        (dome_handler, "abortslew", {}),
    ],
)
def test_every_command_passes_the_failure_on(build, action, params):
    hass = FakeHass()
    hass.services.error = HomeAssistantError("no")
    with pytest.raises(common.DeviceError):
        run(build(hass)(action, params))


def test_a_service_that_hangs_is_a_device_error_after_the_timeout(monkeypatch):
    monkeypatch.setattr(ha_bridge, "_SERVICE_TIMEOUT", 0.05)
    hass = FakeHass()
    hass.services.delay = 5
    with pytest.raises(common.DeviceError) as error:
        run(dome_handler(hass)("openshutter", {}))
    assert "did not finish" in str(error.value)


def test_a_failure_that_is_not_a_home_assistant_error_stays_a_crash():
    hass = FakeHass()
    hass.services.error = ValueError("a bug")
    with pytest.raises(ValueError):
        run(dome_handler(hass)("openshutter", {}))


# ---- switches from more domains -------------------------------------------------------------------------------------
@pytest.mark.parametrize("entity", ["switch.pump", "input_boolean.heater", "light.lamp", "fan.vent"])
def test_a_switch_uses_the_service_of_its_own_domain(entity):
    hass = FakeHass()
    hass.states.set(entity, "off")
    handler = switch_handler(hass, entity)

    run(handler("setswitch", {"Id": "0", "State": "true"}))
    run(handler("setswitch", {"Id": "0", "State": "false"}))
    domain = entity.split(".")[0]
    assert hass.services.calls == [
        (domain, "turn_on", {"entity_id": entity}),
        (domain, "turn_off", {"entity_id": entity}),
    ]


def test_the_domains_for_switches():
    const = importlib.import_module("ascom_alpaca_server.const")
    assert set(const.SWITCH_DOMAINS) == {"switch", "input_boolean", "light", "fan"}
