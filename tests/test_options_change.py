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

        self.hass.config_entries = types.SimpleNamespace(async_reload=async_reload)
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
