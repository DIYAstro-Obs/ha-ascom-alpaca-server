"""Generic device registry for the ASCOM Alpaca protocol layer."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from .models import ActionHandler, AlpacaDevice

_LOGGER = logging.getLogger(__name__)


class AlpacaDeviceRegistry:
    """Central registry of all Alpaca devices (internal + external).

    This class is platform-agnostic — it manages device entries and number
    allocation without any Home Assistant dependency.
    """

    def __init__(self) -> None:
        """Initialize the device registry."""
        self._devices: list[AlpacaDevice] = []
        self._next_numbers: dict[str, int] = {}
        # Track freed device numbers for reuse
        self._freed_numbers: dict[str, list[int]] = {}
        # Remember last-known number for name-based stability
        self._name_number_map: dict[str, int] = {}

    # --- Public API ---

    def get_all_devices(self) -> list[AlpacaDevice]:
        """Return all registered devices."""
        return list(self._devices)

    def get_device(
        self, device_type: str, device_number: int
    ) -> AlpacaDevice | None:
        """Look up a device by type and number."""
        dt_lower = device_type.lower()
        for dev in self._devices:
            if (
                dev.device_type.lower() == dt_lower
                and dev.device_number == device_number
            ):
                return dev
        return None

    # --- Device Management ---

    def add_device(self, device: AlpacaDevice) -> None:
        """Add a pre-built device to the registry."""
        self._devices.append(device)
        _LOGGER.debug(
            "Device added: %s/%d '%s'",
            device.device_type,
            device.device_number,
            device.device_name,
        )

    def remove_internal_devices(self) -> None:
        """Remove all internal (non-external) devices.

        Preserves external devices and re-counts their numbers so that new
        internal devices are allocated above existing external ones.
        """
        self._devices = [d for d in self._devices if d.is_external]
        self._next_numbers.clear()
        # Re-count existing external device numbers
        for dev in self._devices:
            dt = dev.device_type.lower()
            current = self._next_numbers.get(dt, 0)
            if dev.device_number >= current:
                self._next_numbers[dt] = dev.device_number + 1

    # --- External Registration ---

    def register_device(
        self,
        device_type: str,
        device_name: str,
        handler: ActionHandler,
    ) -> Callable[[], None]:
        """Register an external device. Returns an unregister callback.

        If a device with the same type+name was previously registered,
        it will receive the same device number for connection stability.
        """
        dt_lower = device_type.lower()
        stable_key = f"{dt_lower}:{device_name}"

        # Reuse previous device number if this name was registered before
        if stable_key in self._name_number_map:
            device_number = self._name_number_map[stable_key]
            # Remove from freed list if present
            freed = self._freed_numbers.get(dt_lower, [])
            if device_number in freed:
                freed.remove(device_number)
        else:
            device_number = self.allocate_number(dt_lower)
            self._name_number_map[stable_key] = device_number

        unique_id = f"ext_{dt_lower}_{device_number}"

        device = AlpacaDevice(
            device_type=dt_lower,
            device_number=device_number,
            device_name=device_name,
            unique_id=unique_id,
            handler=handler,
            is_external=True,
        )
        self._devices.append(device)

        _LOGGER.info(
            "External device registered: %s/%d '%s'",
            device_type,
            device_number,
            device_name,
        )

        def _unregister() -> None:
            if device in self._devices:
                self._devices.remove(device)
                self._freed_numbers.setdefault(dt_lower, []).append(
                    device_number
                )
                _LOGGER.info(
                    "External device unregistered: %s/%d '%s'",
                    device_type,
                    device_number,
                    device_name,
                )

        return _unregister

    # --- Number Allocation ---

    def allocate_number(self, device_type: str) -> int:
        """Allocate the next device number for a device type.

        Reuses freed numbers before allocating new ones.
        """
        dt = device_type.lower()
        freed = self._freed_numbers.get(dt, [])
        if freed:
            return freed.pop(0)
        num = self._next_numbers.get(dt, 0)
        self._next_numbers[dt] = num + 1
        return num
