"""ASCOM Alpaca Dome protocol handler (roll-off roof).

Creates an action handler for a Dome device that only has a shutter: open,
close, abort and the shutter status. Azimuth, altitude, slaving, parking and
homing are not present (the Can* flags are false, the movements report
"not implemented").

All platform-specific I/O is abstracted behind a DomeChannel callback.
"""

from __future__ import annotations

from typing import Any

from ..models import ActionHandler, DomeChannel
from ._common import common_device_info

# ShutterStatus enum values (ASCOM spec)
SHUTTER_OPEN = 0
SHUTTER_CLOSED = 1
SHUTTER_OPENING = 2
SHUTTER_CLOSING = 3
SHUTTER_ERROR = 4

# IDomeV2
_INTERFACE_VERSION = 2

# Boolean capabilities of a shutter-only dome
_CAPABILITIES: dict[str, bool] = {
    "cansetshutter": True,
    "canfindhome": False,
    "canpark": False,
    "cansetpark": False,
    "cansetaltitude": False,
    "cansetazimuth": False,
    "canslave": False,
    "cansyncazimuth": False,
    # state of the functions that are not present
    "athome": False,
    "atpark": False,
    "slewing": False,
}

# Properties and methods that need azimuth, altitude, home or park
_NOT_IMPLEMENTED = (
    "altitude",
    "azimuth",
    "findhome",
    "park",
    "setpark",
    "slewtoaltitude",
    "slewtoazimuth",
    "synctoazimuth",
)


def _not_implemented(action: str) -> dict[str, Any]:
    return {
        "Value": None,
        "ErrorNumber": 0x400,
        "ErrorMessage": f"'{action}' is not implemented: this dome only has a shutter",
    }


def create_dome_handler(
    channel: DomeChannel,
    device_name: str = "Dome",
) -> ActionHandler:
    """Create an Alpaca Dome action handler.

    Args:
        channel: Abstract shutter channel (roll-off roof).
        device_name: Name reported by the Alpaca ``name`` property.

    Returns:
        An async action handler suitable for ``AlpacaDevice.handler``.
    """

    device_state = {"is_connected": False}

    async def handle_dome(
        action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle Alpaca Dome requests."""
        action_lower = action.lower()

        # --- Common device properties ---

        if action_lower == "connected":
            # Handle PUT/POST to connected=True/False
            put_key = next(
                (k for k in (params or {}) if k.lower() == "connected"), None
            )
            if put_key is not None:
                # Strict case matching for the Alpaca Compliance Tool
                if put_key != "Connected":
                    return {
                        "Value": False,
                        "ErrorNumber": 0x400,
                        "ErrorMessage": "Parameter 'Connected' missing or bad casing",
                    }
                v = params["Connected"]
                if isinstance(v, str):
                    v_lower = v.lower()
                    if v_lower == "true":
                        device_state["is_connected"] = True
                    elif v_lower == "false":
                        device_state["is_connected"] = False
                    else:
                        return {
                            "Value": False,
                            "ErrorNumber": 0x400,
                            "ErrorMessage": f"Invalid boolean value: {v}",
                        }
                else:
                    device_state["is_connected"] = bool(v)
            return {"Value": device_state["is_connected"]}

        if action_lower == "name":
            return {"Value": device_name}

        if action_lower == "description":
            return {"Value": channel.description}

        if action_lower in (
            "driverinfo",
            "driverversion",
            "interfaceversion",
            "supportedactions",
        ):
            return common_device_info(action_lower, _INTERFACE_VERSION)

        # --- Shutter ---

        if action_lower == "shutterstatus":
            return {"Value": await channel.get_shutter_status()}

        if action_lower == "openshutter":
            await channel.open_shutter()
            return {"Value": None}

        if action_lower == "closeshutter":
            await channel.close_shutter()
            return {"Value": None}

        if action_lower == "abortslew":
            await channel.stop()
            return {"Value": None}

        # --- Capabilities and the state of what is not present ---

        if action_lower in _CAPABILITIES:
            return {"Value": _CAPABILITIES[action_lower]}

        if action_lower == "slaved":
            put_key = next(
                (k for k in (params or {}) if k.lower() == "slaved"), None
            )
            if put_key is not None and str(params[put_key]).lower() != "false":
                return _not_implemented("Slaved")
            return {"Value": False}

        if action_lower in _NOT_IMPLEMENTED:
            return _not_implemented(action)

        return {
            "Value": None,
            "ErrorNumber": 0x400,
            "ErrorMessage": f"Action '{action}' not supported for Dome",
        }

    return handle_dome
