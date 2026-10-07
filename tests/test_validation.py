"""Checks of the options flow and the start of the server."""

import asyncio
import importlib
import socket
import types

import pytest

import ha_stubs

validation = importlib.import_module("ascom_alpaca_server.validation")
server_module = importlib.import_module("ascom_alpaca_server.alpaca.server")
integration = importlib.import_module("ascom_alpaca_server")
registry_module = importlib.import_module("ascom_alpaca_server.alpaca.device_registry")


# ---- the port -------------------------------------------------------------------------------------------------------
def test_a_port_that_is_listened_on_is_not_free():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("0.0.0.0", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert validation.port_is_free(port) is False
    assert validation.port_is_free(port) is True  # free again once the listener is gone


# ---- names of the switches ------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "names, expected",
    [
        ({"switch.a": "Pump", "switch.b": "Heater"}, {}),
        ({"switch.a": "Pump", "switch.b": "pump"}, {"switch.a": "name_duplicate", "switch.b": "name_duplicate"}),
        (
            {"switch.a": " Pump ", "switch.b": "Pump", "switch.c": "Fan"},
            {"switch.a": "name_duplicate", "switch.b": "name_duplicate"},
        ),
        ({"switch.a": "", "switch.b": "Heater"}, {"switch.a": "name_empty"}),
        ({"switch.a": "   ", "switch.b": "  "}, {"switch.a": "name_empty", "switch.b": "name_empty"}),
        ({}, {}),
    ],
)
def test_switch_name_errors(names, expected):
    assert validation.switch_name_errors(names) == expected


# ---- the server does not start: the port is in use -------------------------------------------------------------------
class FakeRunner:
    instances = []

    def __init__(self, app):
        self.cleaned = False
        FakeRunner.instances.append(self)

    async def setup(self):
        pass

    async def cleanup(self):
        self.cleaned = True


class BusySite:
    def __init__(self, runner, host, port):
        pass

    async def start(self):
        raise OSError(98, "address already in use")


def fake_web(monkeypatch, site):
    FakeRunner.instances.clear()
    app = types.SimpleNamespace(
        router=types.SimpleNamespace(add_get=lambda *a: None, add_route=lambda *a: None)
    )
    monkeypatch.setattr(
        server_module,
        "web",
        types.SimpleNamespace(Application=lambda: app, AppRunner=FakeRunner, TCPSite=site),
    )


def test_a_failed_start_cleans_the_runner_up(monkeypatch):
    fake_web(monkeypatch, BusySite)
    server = server_module.AlpacaServer(registry_module.AlpacaDeviceRegistry(), 5555, discovery_enabled=False)

    with pytest.raises(OSError):
        asyncio.run(server.start())
    assert [runner.cleaned for runner in FakeRunner.instances] == [True]


def test_the_setup_waits_and_retries_when_the_port_is_in_use(monkeypatch):
    """Home Assistant shows the reason and tries again later instead of giving up."""

    class BusyServer:
        def __init__(self, registry, port, discovery):
            pass

        async def start(self):
            raise OSError(98, "address already in use")

    monkeypatch.setattr(integration, "AlpacaServer", BusyServer)
    hass = types.SimpleNamespace(data={})
    entry = types.SimpleNamespace(
        entry_id="E", options={}, data={"alpaca_port": 5555, "alpaca_discovery": False}
    )

    with pytest.raises(ha_stubs.ConfigEntryNotReady) as error:
        asyncio.run(integration.async_setup_entry(hass, entry))
    assert "5555" in str(error.value)
