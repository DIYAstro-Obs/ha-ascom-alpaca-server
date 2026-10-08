"""Changing the options: a new mapping must not restart the server, a new port must."""

import asyncio
import importlib
import types

import pytest

from ha_stubs import FakeHass

integration = importlib.import_module("ascom_alpaca_server")
const = importlib.import_module("ascom_alpaca_server.const")


class FakeServer:
    """Stands for the HTTP server: counts how often it was started."""

    starts = 0

    def __init__(self, registry, port, discovery):
        self.port = port
        self.discovery = discovery

    async def start(self):
        FakeServer.starts += 1

    async def stop(self):
        pass


class Setup:
    """A set-up integration with a fake server."""

    def __init__(self, options=None, data=None):
        FakeServer.starts = 0
        self.hass = FakeHass()
        self.hass.states.set("cover.roof", "closed")
        self.hass.states.set("switch.pump", "off")
        self.hass.data = {}
        self.reloads = []

        async def async_reload(entry_id):
            self.reloads.append(entry_id)

        async def async_forward_entry_setups(entry, platforms):
            self.platforms = list(platforms)

        async def async_unload_platforms(entry, platforms):
            return True

        self.platforms = None
        self.hass.config_entries = types.SimpleNamespace(
            async_reload=async_reload,
            async_forward_entry_setups=async_forward_entry_setups,
            async_unload_platforms=async_unload_platforms,
        )
        self.entry = types.SimpleNamespace(
            entry_id="E",
            options=options or {},
            data=data or {"alpaca_port": 5555, "alpaca_discovery": True},
            async_on_unload=lambda cancel: None,
            add_update_listener=lambda listener: (lambda: None),
        )
        asyncio.run(integration.async_setup_entry(self.hass, self.entry))

    @property
    def registry(self):
        return self.hass.data[const.DOMAIN]["E"][const.DATA_REGISTRY]

    def device(self, device_type):
        return self.registry.get_device(device_type, 0)

    def change(self, **options):
        """Save new options and let the update listener react, as Home Assistant does."""
        self.entry.options = {**self.entry.options, **options}
        asyncio.run(integration._async_update_listener(self.hass, self.entry))


@pytest.fixture(autouse=True)
def fake_server(monkeypatch):
    monkeypatch.setattr(integration, "AlpacaServer", FakeServer)


# ---- a new mapping -------------------------------------------------------------------------------------------------
def test_a_new_mapping_builds_the_devices_without_restarting_the_server():
    setup = Setup()
    assert setup.device("dome") is None

    setup.change(dome_cover_entity="cover.roof")

    assert setup.device("dome") is not None
    assert setup.reloads == []
    assert FakeServer.starts == 1


def test_removing_a_mapping_removes_the_device():
    setup = Setup({"dome_cover_entity": "cover.roof"})
    assert setup.device("dome") is not None

    setup.change(dome_cover_entity="")

    assert setup.device("dome") is None
    assert setup.reloads == []


def test_the_clients_stay_connected_when_the_devices_are_built_again():
    setup = Setup({"dome_cover_entity": "cover.roof"})
    setup.device("dome").connected_clients.update({7, 42})
    old_dome = setup.device("dome")

    setup.change(switch_entities=["switch.pump"], switch_names={"switch.pump": "Pump"})

    new_dome = setup.device("dome")
    assert new_dome is not old_dome  # built again ...
    assert new_dome.connected_clients == {7, 42}  # ... but still connected
    assert setup.device("switch").connected_clients == set()  # a new device starts without clients


def test_a_device_that_was_removed_and_comes_back_starts_without_clients():
    setup = Setup({"dome_cover_entity": "cover.roof"})
    setup.device("dome").connected_clients.add(7)

    setup.change(dome_cover_entity="")
    setup.change(dome_cover_entity="cover.roof")

    assert setup.device("dome").connected_clients == set()


def test_external_devices_are_not_touched():
    setup = Setup()

    async def handler(action, params):
        return {"Value": True}

    setup.registry.register_device("SafetyMonitor", "Safety", handler)
    external = setup.registry.get_device("safetymonitor", 0)
    external.connected_clients.add(7)

    setup.change(dome_cover_entity="cover.roof")

    assert setup.registry.get_device("safetymonitor", 0) is external
    assert external.connected_clients == {7}


# ---- port and discovery ---------------------------------------------------------------------------------------------
def test_a_new_port_reloads_the_integration():
    setup = Setup()
    setup.change(alpaca_port=5556)
    assert setup.reloads == ["E"]


def test_a_new_discovery_setting_reloads_the_integration():
    setup = Setup()
    setup.change(alpaca_discovery=False)
    assert setup.reloads == ["E"]


def test_the_same_port_and_discovery_in_the_options_do_not_reload():
    """The dialog saves port and discovery together with every mapping: only a change counts."""
    setup = Setup()
    setup.change(alpaca_port=5555, alpaca_discovery=True, dome_cover_entity="cover.roof")
    assert setup.reloads == []


def test_the_options_override_the_data_of_the_setup():
    setup = Setup(options={"alpaca_port": 6000, "alpaca_discovery": False})
    assert setup.hass.data[const.DOMAIN]["E"][const.DATA_LISTEN] == (6000, False)

    setup.change(dome_cover_entity="cover.roof")
    assert setup.reloads == []


def test_an_update_before_the_setup_is_done_reloads():
    hass = FakeHass()
    hass.data = {const.DOMAIN: {}}
    reloads = []

    async def async_reload(entry_id):
        reloads.append(entry_id)

    hass.config_entries = types.SimpleNamespace(async_reload=async_reload)
    entry = types.SimpleNamespace(entry_id="E", options={}, data={})

    asyncio.run(integration._async_update_listener(hass, entry))
    assert reloads == ["E"]


# ---- removing the integration -------------------------------------------------------------------------------------
def test_unloading_keeps_the_api_for_other_integrations_so_that_a_reload_works():
    setup = Setup()
    assert asyncio.run(integration.async_unload_entry(setup.hass, setup.entry)) is True
    assert const.ALPACA_SERVER_API_KEY in setup.hass.data


def test_a_removed_and_added_again_server_keeps_the_registered_devices():
    """Safety registers when it sets up and when the Server loads for the first time, not when the Server
    is added again: after "remove the Server, add it again" the registry has to survive, with Safety in it."""
    setup = Setup()

    async def handler(action, params):
        return {"Value": True}

    setup.registry.register_device("SafetyMonitor", "Safety", handler)
    registry = setup.registry
    external = registry.get_device("safetymonitor", 0)

    asyncio.run(integration.async_unload_entry(setup.hass, setup.entry))
    # Home Assistant calls async_remove_entry when the integration is deleted, but only if there is one:
    # nothing may throw the API away
    assert not hasattr(integration, "async_remove_entry")
    asyncio.run(integration.async_setup_entry(setup.hass, setup.entry))  # added again

    assert setup.registry is registry
    assert setup.registry.get_device("safetymonitor", 0) is external
    assert asyncio.run(external.handler("issafe", {})) == {"Value": True}


# ---- computed values: sensors that appear or disappear ----------------------------------------------------------------
OC_T_H = {"temperature": ["sensor.t"], "humidity": ["sensor.h"]}  # the dew point and the spread are computed


def derived_of(setup):
    return setup.hass.data[const.DOMAIN]["E"][const.DATA_DERIVED]


def test_the_sensor_platform_is_set_up_with_the_integration():
    assert Setup().platforms == ["sensor"]


def test_the_platforms_are_unloaded_with_the_integration_and_a_refusal_keeps_it_loaded():
    setup = Setup()

    async def refuse(entry, platforms):
        return False

    setup.hass.config_entries.async_unload_platforms = refuse
    assert asyncio.run(integration.async_unload_entry(setup.hass, setup.entry)) is False
    assert "E" in setup.hass.data[const.DOMAIN]  # still there


def test_a_mapping_that_keeps_the_computed_values_is_rebuilt_in_place():
    setup = Setup({"observing_conditions": OC_T_H})
    before = derived_of(setup)
    assert before.flags == (True, True)

    setup.change(observing_conditions={"temperature": ["sensor.t2"], "humidity": ["sensor.h2"]})

    assert setup.reloads == []
    assert derived_of(setup) is not before  # the sensors read the new channels at their next update
    assert FakeServer.starts == 1


def test_mapping_a_dew_point_makes_the_computed_dew_point_disappear_by_a_reload():
    setup = Setup({"observing_conditions": OC_T_H})
    setup.change(observing_conditions={**OC_T_H, "dewpoint": ["sensor.d"]})
    assert setup.reloads == ["E"]  # (True, True) -> (False, True)


def test_a_mapping_without_humidity_makes_both_disappear_by_a_reload():
    setup = Setup({"observing_conditions": OC_T_H})
    setup.change(observing_conditions={"temperature": ["sensor.t"]})
    assert setup.reloads == ["E"]  # (True, True) -> (False, False)


def test_the_first_mapping_with_temperature_and_humidity_makes_the_sensors_appear_by_a_reload():
    setup = Setup()
    setup.change(observing_conditions=OC_T_H)
    assert setup.reloads == ["E"]  # (False, False) -> (True, True)


def test_a_mapping_that_computes_nothing_before_and_after_does_not_reload():
    setup = Setup({"observing_conditions": {"temperature": ["sensor.t"]}})
    setup.change(observing_conditions={"temperature": ["sensor.t"], "windspeed": ["sensor.w"]})
    assert setup.reloads == []
