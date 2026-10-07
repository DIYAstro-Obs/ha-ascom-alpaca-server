"""Minimal stand-ins for the Home Assistant modules the integration imports.

The tests exercise the Alpaca logic without a Home Assistant installation:
only ``pytest`` is needed. Importing this module installs the stubs and puts
``custom_components`` on ``sys.path``.
"""

from __future__ import annotations

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


class FakeServices:
    """Records service calls instead of executing them."""

    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data=None, **kwargs):
        self.calls.append((domain, service, dict(data or {})))


class FakeHass:
    def __init__(self):
        self.states = FakeStates()
        self.services = FakeServices()


def install() -> None:
    if "homeassistant" in sys.modules:
        return

    ha = _mod("homeassistant")
    _mod("homeassistant.config_entries", ConfigEntry=object)
    _mod("homeassistant.core", HomeAssistant=object)
    util = _mod("homeassistant.util")
    util.dt = _mod(
        "homeassistant.util.dt", utcnow=lambda: datetime.now(timezone.utc)
    )
    ha.util = util
    _mod("aiohttp", web=MagicMock())

    sys.path.insert(0, str(CUSTOM_COMPONENTS))


install()
