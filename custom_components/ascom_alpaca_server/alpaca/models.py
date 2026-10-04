"""Data models for the ASCOM Alpaca protocol layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

# Type alias for an Alpaca device action handler.
# Signature: async (action: str, params: dict) -> dict with Value/Error keys.
ActionHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class AlpacaDevice:
    """A registered Alpaca device."""

    device_type: str
    device_number: int
    device_name: str
    unique_id: str
    handler: ActionHandler
    is_external: bool = False


@dataclass
class SwitchChannel:
    """Abstract switch channel for the Alpaca Switch handler.

    Provides platform-agnostic access to a single on/off switch.
    The callbacks are injected by the host application (e.g. Home Assistant).
    """

    name: str
    description: str
    get_state: Callable[[], Awaitable[bool | None]]
    set_state: Callable[[bool], Awaitable[None]]


@dataclass
class OCSensorChannel:
    """Abstract sensor channel for the Alpaca ObservingConditions handler.

    Provides platform-agnostic access to a single numeric sensor reading.
    The callbacks are injected by the host application (e.g. Home Assistant).
    """

    property_name: str
    description: str
    get_value: Callable[[], Awaitable[float | None]]
    get_seconds_since_update: Callable[[], Awaitable[float]]


@dataclass
class CalibratorChannel:
    """Abstract calibrator channel for the Alpaca CoverCalibrator handler.

    Provides platform-agnostic access to a flat panel / calibrator light.
    The callbacks are injected by the host application (e.g. Home Assistant).
    """

    name: str
    description: str
    get_max_brightness: Callable[[], int]
    get_brightness: Callable[[], Awaitable[int | None]]
    get_is_on: Callable[[], Awaitable[bool | None]]
    turn_on: Callable[[int], Awaitable[None]]
    turn_off: Callable[[], Awaitable[None]]
