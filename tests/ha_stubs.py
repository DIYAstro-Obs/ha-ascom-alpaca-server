"""Minimal stand-ins for the Home Assistant modules the integration imports.

The tests exercise the Alpaca logic without a Home Assistant installation:
only ``pytest`` is needed. Importing this module installs the stubs and puts
``custom_components`` on ``sys.path``.
"""

from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

CUSTOM_COMPONENTS = Path(__file__).resolve().parents[1] / "custom_components"


def _mod(name: str, **attrs) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module
    return module


class FakeState:
    def __init__(self, entity_id, state, attributes=None):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}
        self.name = self.attributes.get("friendly_name") or entity_id
        self.last_updated = datetime.now(timezone.utc)
        self.last_reported = self.last_updated


class FakeStates:
    def __init__(self):
        self._states = {}

    def set(self, entity_id, state, attributes=None):
        self._states[entity_id] = FakeState(entity_id, state, attributes)

    def get(self, entity_id):
        return self._states.get(entity_id)


class HomeAssistantError(Exception):
    pass


class ConfigEntryNotReady(Exception):
    pass


class FakeServices:
    """Records service calls instead of executing them (or fails, or hangs, on request)."""

    def __init__(self):
        self.calls = []
        self.error = None  # raised by every call
        self.delay = 0  # seconds every call takes
        self.blocking = []  # the blocking argument of every call

    async def async_call(self, domain, service, data=None, blocking=False, **kwargs):
        self.blocking.append(blocking)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        self.calls.append((domain, service, dict(data or {})))


class FakeRegistryEntry:
    def __init__(self, entity_id, unique_id):
        self.entity_id = entity_id
        self.unique_id = unique_id


class FakeEntityRegistry:
    """The entity registry: a list of entries of one config entry."""

    def __init__(self):
        self.entries = []
        self.removed = []

    def async_remove(self, entity_id):
        self.removed.append(entity_id)
        self.entries = [e for e in self.entries if e.entity_id != entity_id]


class FakeHass:
    def __init__(self):
        self.states = FakeStates()
        self.services = FakeServices()
        self.entity_registry = FakeEntityRegistry()


def install() -> None:
    if "homeassistant" in sys.modules:
        return

    ha = _mod("homeassistant")
    _mod("homeassistant.config_entries", ConfigEntry=object)
    _mod("homeassistant.core", HomeAssistant=object)

    async def async_get_instance_id(hass):
        return "test-instance"

    helpers = _mod("homeassistant.helpers")
    helpers.instance_id = _mod("homeassistant.helpers.instance_id", async_get=async_get_instance_id)
    helpers.entity = _mod("homeassistant.helpers.entity", DeviceInfo=dict)
    helpers.entity_platform = _mod("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    helpers.entity_registry = _mod(
        "homeassistant.helpers.entity_registry",
        async_get=lambda hass: hass.entity_registry,
        async_entries_for_config_entry=lambda registry, entry_id: list(registry.entries),
    )

    class SensorEntity:
        @property
        def unique_id(self):  # like Home Assistant's Entity
            return getattr(self, "_attr_unique_id", None)

    components = _mod("homeassistant.components")
    components.sensor = _mod(
        "homeassistant.components.sensor",
        SensorEntity=SensorEntity,
        SensorDeviceClass=types.SimpleNamespace(TEMPERATURE="temperature"),
        SensorStateClass=types.SimpleNamespace(MEASUREMENT="measurement"),
    )
    ha.components = components
    _mod(
        "homeassistant.exceptions",
        HomeAssistantError=HomeAssistantError,
        ConfigEntryNotReady=ConfigEntryNotReady,
    )
    util = _mod("homeassistant.util")
    util.dt = _mod(
        "homeassistant.util.dt", utcnow=lambda: datetime.now(timezone.utc)
    )
    ha.util = util
    _mod("aiohttp", web=MagicMock())

    sys.path.insert(0, str(CUSTOM_COMPONENTS))


install()
