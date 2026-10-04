"""ASCOM Alpaca CoverCalibrator protocol handler.

Creates an action handler for a CoverCalibrator device.
Only the Calibrator function (flat panel) is implemented;
the Cover function reports NotPresent.

All platform-specific I/O is abstracted behind a CalibratorChannel callback.
"""

from __future__ import annotations

from typing import Any

from ..models import ActionHandler, CalibratorChannel
from ._common import common_device_info

# CalibratorStatus enum values (ASCOM spec)
_CALIBRATOR_NOT_PRESENT = 0
_CALIBRATOR_OFF = 1
_CALIBRATOR_NOT_READY = 2
_CALIBRATOR_READY = 3
_CALIBRATOR_UNKNOWN = 4
_CALIBRATOR_ERROR = 5

# CoverStatus enum values (ASCOM spec)
_COVER_NOT_PRESENT = 0


def create_covercalibrator_handler(
    channel: CalibratorChannel,
    device_name: str = "CoverCalibrator",
) -> ActionHandler:
    """Create an Alpaca CoverCalibrator action handler.

    Args:
        channel: Abstract calibrator channel (flat panel light).
        device_name: Name reported by the Alpaca ``name`` property.

    Returns:
        An async action handler suitable for ``AlpacaDevice.handler``.
    """

    async def handle_covercalibrator(
        action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle Alpaca CoverCalibrator requests."""
        action_lower = action.lower()

        # --- Common device properties ---

        if action_lower == "connected":
            return {"Value": True}

        if action_lower == "name":
            return {"Value": device_name}

        if action_lower == "description":
            return {"Value": channel.description}

        # --- Cover state (not present) ---

        if action_lower == "coverstate":
            return {"Value": _COVER_NOT_PRESENT}

        if action_lower in ("opencover", "closecover", "haltcover"):
            return {
                "Value": None,
                "ErrorNumber": 0x400,
                "ErrorMessage": "Cover is not present on this device",
            }

        # --- Calibrator state ---

        if action_lower == "calibratorstate":
            is_on = await channel.get_is_on()
            if is_on is None:
                return {"Value": _CALIBRATOR_UNKNOWN}
            return {
                "Value": _CALIBRATOR_READY if is_on else _CALIBRATOR_OFF
            }

        if action_lower == "brightness":
            brightness = await channel.get_brightness()
            return {"Value": brightness if brightness is not None else 0}

        if action_lower == "maxbrightness":
            return {"Value": channel.max_brightness}

        # --- Calibrator actions ---

        if action_lower == "calibratoron":
            try:
                brightness = int(params.get("Brightness", channel.max_brightness))
            except (ValueError, TypeError):
                brightness = channel.max_brightness
            # Clamp to valid range
            brightness = max(0, min(brightness, channel.max_brightness))
            await channel.turn_on(brightness)
            return {"Value": None}

        if action_lower == "calibratoroff":
            await channel.turn_off()
            return {"Value": None}

        # --- Standard device info ---

        if action_lower in (
            "driverinfo",
            "driverversion",
            "interfaceversion",
            "supportedactions",
        ):
            return common_device_info(action_lower)

        return {
            "Value": None,
            "ErrorNumber": 0x400,
            "ErrorMessage": (
                f"Action '{action}' not supported for CoverCalibrator"
            ),
        }

    return handle_covercalibrator
