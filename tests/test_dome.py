"""Dome (roll-off roof from a cover entity): shutter status, commands, capabilities."""

import asyncio
import importlib

import pytest

from ha_stubs import FakeHass

ha_bridge = importlib.import_module("ascom_alpaca_server.ha_bridge")
dome = importlib.import_module("ascom_alpaca_server.alpaca.handlers.dome")
registry_module = importlib.import_module("ascom_alpaca_server.alpaca.device_registry")

COVER = "cover.observatory_roof"


def handler_for(hass, entity=COVER):
    channel = ha_bridge._build_dome_channel(hass, entity)
    return dome.create_dome_handler(channel, device_name="HA Dome")


def call(handler, action, params=None):
    return asyncio.run(handler(action, params or {}))


def status_of(state, attributes=None):
    hass = FakeHass()
    if state is not None:
        hass.states.set(COVER, state, attributes or {})
    return call(handler_for(hass), "shutterstatus")["Value"]


# --- ShutterStatus from the cover state ---------------------------------------------------------
@pytest.mark.parametrize(
    "state, attributes, expected",
    [
        ("open", {"current_position": 100}, dome.SHUTTER_OPEN),
        ("closed", {"current_position": 0}, dome.SHUTTER_CLOSED),
        ("opening", {"current_position": 0}, dome.SHUTTER_OPENING),
        ("closing", {"current_position": 100}, dome.SHUTTER_CLOSING),
        # idle halfway: HA says "open", but the roof is neither open nor closed
        ("open", {"current_position": 50}, dome.SHUTTER_ERROR),
        ("open", {"current_position": 99}, dome.SHUTTER_ERROR),
        ("open", {"current_position": 100.0}, dome.SHUTTER_OPEN),
        ("closed", {"current_position": 0.0}, dome.SHUTTER_CLOSED),
        # a cover without a position knows open / closed only
        ("open", {}, dome.SHUTTER_OPEN),
        ("closed", {}, dome.SHUTTER_CLOSED),
        ("opening", {}, dome.SHUTTER_OPENING),
        ("closing", {}, dome.SHUTTER_CLOSING),
        # not reachable or not known
        ("unavailable", {}, dome.SHUTTER_ERROR),
        ("unknown", {}, dome.SHUTTER_ERROR),
        ("open", {"current_position": "abc"}, dome.SHUTTER_ERROR),
        ("stopped", {}, dome.SHUTTER_ERROR),
    ],
)
def test_shutter_status_follows_the_cover(state, attributes, expected):
    assert status_of(state, attributes) == expected


def test_a_missing_cover_entity_is_an_error():
    assert status_of(None) == dome.SHUTTER_ERROR


def test_the_status_follows_changes_of_the_cover():
    hass = FakeHass()
    handler = handler_for(hass)
    hass.states.set(COVER, "closed", {"current_position": 0})
    assert call(handler, "shutterstatus")["Value"] == dome.SHUTTER_CLOSED
    hass.states.set(COVER, "opening", {"current_position": 0})
    assert call(handler, "shutterstatus")["Value"] == dome.SHUTTER_OPENING
    hass.states.set(COVER, "open", {"current_position": 100})
    assert call(handler, "shutterstatus")["Value"] == dome.SHUTTER_OPEN


# --- commands -----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "action, service",
    [("openshutter", "open_cover"), ("closeshutter", "close_cover"), ("abortslew", "stop_cover")],
)
def test_commands_call_exactly_one_cover_service(action, service):
    hass = FakeHass()
    hass.states.set(COVER, "closed", {"current_position": 0})
    result = call(handler_for(hass), action)
    assert result == {"Value": None}
    assert hass.services.calls == [("cover", service, {"entity_id": COVER})]


def test_action_names_are_case_insensitive():
    hass = FakeHass()
    hass.states.set(COVER, "closed", {"current_position": 0})
    handler = handler_for(hass)
    assert call(handler, "ShutterStatus")["Value"] == dome.SHUTTER_CLOSED
    call(handler, "OpenShutter")
    assert hass.services.calls == [("cover", "open_cover", {"entity_id": COVER})]


# --- capabilities: a shutter and nothing else ------------------------------------------------------
def test_only_the_shutter_can_be_set():
    handler = handler_for(FakeHass())
    assert call(handler, "cansetshutter")["Value"] is True
    for action in (
        "canfindhome",
        "canpark",
        "cansetpark",
        "cansetaltitude",
        "cansetazimuth",
        "canslave",
        "cansyncazimuth",
        "athome",
        "atpark",
        "slewing",
        "slaved",
    ):
        assert call(handler, action) == {"Value": False}, action


@pytest.mark.parametrize(
    "action",
    ["altitude", "azimuth", "findhome", "park", "setpark", "slewtoaltitude", "slewtoazimuth", "synctoazimuth"],
)
def test_azimuth_altitude_home_and_park_are_not_implemented(action):
    hass = FakeHass()
    result = call(handler_for(hass), action, {"Azimuth": "10"})
    assert result["ErrorNumber"] == 0x400
    assert hass.services.calls == []


def test_slaving_cannot_be_switched_on_but_off_is_fine():
    handler = handler_for(FakeHass())
    assert call(handler, "slaved", {"Slaved": "false"}) == {"Value": False}
    assert call(handler, "slaved", {"Slaved": "true"})["ErrorNumber"] == 0x400


def test_an_unknown_action_is_an_error():
    assert call(handler_for(FakeHass()), "unknownaction")["ErrorNumber"] == 0x400


# --- common device properties --------------------------------------------------------------------
def test_device_information():
    handler = handler_for(FakeHass())
    assert call(handler, "name")["Value"] == "HA Dome"
    assert COVER in call(handler, "description")["Value"]
    assert call(handler, "interfaceversion")["Value"] == 2
    assert call(handler, "supportedactions")["Value"] == []
    assert call(handler, "driverinfo")["Value"]
    assert call(handler, "driverversion")["Value"]


def test_an_unknown_action_is_a_bad_request():
    assert call(handler_for(FakeHass()), "nonsense")["HttpStatus"] == 400


def test_other_device_types_keep_interface_version_1():
    """common_device_info only changes the version for the handler that asks for it."""
    common = importlib.import_module("ascom_alpaca_server.alpaca.handlers._common")
    assert common.common_device_info("interfaceversion") == {"Value": 1}
    assert common.common_device_info("interfaceversion", 2) == {"Value": 2}


# --- the device in the registry -----------------------------------------------------------------
def devices(options):
    registry = registry_module.AlpacaDeviceRegistry()
    ha_bridge.rebuild_devices(registry, FakeHass(), options)
    return registry


def test_the_dome_exists_only_with_a_cover_entity():
    assert devices({}).get_all_devices() == []
    assert devices({"dome_cover_entity": ""}).get_all_devices() == []

    registry = devices({"dome_cover_entity": COVER})
    [device] = registry.get_all_devices()
    assert (device.device_type, device.device_number, device.device_name) == ("dome", 0, "HA Dome")
    assert device.unique_id == registry.unique_id_for("internal:dome")
    assert device.is_external is False
    assert registry.get_device("dome", 0) is device
