"""ASCOM Alpaca CoverCalibrator protocol handler.

Creates an action handler for a CoverCalibrator device.
Only the Calibrator function (flat panel) is implemented;
the Cover function reports NotPresent.

All platform-specific I/O is abstracted behind a CalibratorChannel callback.
"""

from __future__ import annotations

from typing import Any

from ..models import ActionHandler, CalibratorChannel
from ._common import (
    ERROR_UNSPECIFIED,
    bad_request,
    common_device_info,
    driver_error,
)

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

        # --- Common device properties (Connected is handled by the server) ---

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
            if brightness is None:
                return driver_error(
                    ERROR_UNSPECIFIED, "The calibrator does not report a brightness"
                )
            return {"Value": brightness}

        if action_lower == "maxbrightness":
            return {"Value": channel.get_max_brightness()}

        # --- Calibrator actions ---

        if action_lower == "calibratoron":
            try:
                brightness = int(params["Brightness"])
            except (KeyError, ValueError, TypeError):
                return bad_request("Parameter 'Brightness' missing or invalid")
            # Clamp to valid range
            brightness = max(0, min(brightness, channel.get_max_brightness()))
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

        return bad_request(f"Action '{action}' not supported for CoverCalibrator")

    return handle_covercalibrator
