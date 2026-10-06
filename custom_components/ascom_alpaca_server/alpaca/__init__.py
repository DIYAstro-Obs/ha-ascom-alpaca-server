"""ASCOM Alpaca protocol library — standalone, no Home Assistant dependency.

This package contains all Alpaca protocol logic:
- ``models``   — data classes (AlpacaDevice, SwitchChannel, OCSensorChannel, CalibratorChannel, DomeChannel)
- ``device_registry`` — generic device registration and lookup
- ``server``   — aiohttp-based HTTP server and UDP discovery
- ``handlers`` — protocol handler factories for Switch, ObservingConditions, CoverCalibrator, Dome
- ``const``    — protocol-level constants
"""

from __future__ import annotations

from .const import (
    ALPACA_DISCOVERY_PORT,
    DEVICE_TYPE_COVERCALIBRATOR,
    DEVICE_TYPE_DOME,
    DEVICE_TYPE_OBSERVINGCONDITIONS,
    DEVICE_TYPE_SAFETYMONITOR,
    DEVICE_TYPE_SWITCH,
    OC_PROPERTIES,
)
from .device_registry import AlpacaDeviceRegistry
from .models import (
    ActionHandler,
    AlpacaDevice,
    CalibratorChannel,
    DomeChannel,
    OCSensorChannel,
    SwitchChannel,
)
from .server import AlpacaServer

__all__ = [
    "ActionHandler",
    "AlpacaDevice",
    "AlpacaDeviceRegistry",
    "AlpacaServer",
    "ALPACA_DISCOVERY_PORT",
    "CalibratorChannel",
    "DEVICE_TYPE_COVERCALIBRATOR",
    "DEVICE_TYPE_DOME",
    "DEVICE_TYPE_OBSERVINGCONDITIONS",
    "DEVICE_TYPE_SAFETYMONITOR",
    "DEVICE_TYPE_SWITCH",
    "DomeChannel",
    "OC_PROPERTIES",
    "OCSensorChannel",
    "SwitchChannel",
]
