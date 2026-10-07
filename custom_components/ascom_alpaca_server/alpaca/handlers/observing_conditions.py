"""ASCOM Alpaca ObservingConditions protocol handler.

Creates an action handler for an ObservingConditions device.
All platform-specific I/O is abstracted behind OCSensorChannel callbacks.
"""

from __future__ import annotations

from typing import Any

from ..const import OC_PROPERTIES
from ..models import ActionHandler, OCSensorChannel
from ._common import (
    ERROR_INVALID_VALUE,
    ERROR_NOT_IMPLEMENTED,
    ERROR_VALUE_NOT_SET,
    bad_request,
    common_device_info,
    driver_error,
    get_param,
)


def create_oc_handler(
    channels: dict[str, OCSensorChannel],
    device_name: str = "ObservingConditions",
) -> ActionHandler:
    """Create an Alpaca ObservingConditions action handler.

    Args:
        channels: Mapping of property name (lowercase) to sensor channel.
        device_name: Name reported by the Alpaca ``name`` property.

    Returns:
        An async action handler suitable for ``AlpacaDevice.handler``.
    """

    device_state = {
        "average_period": 0.0,
    }

    async def handle_oc(
        action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle Alpaca ObservingConditions requests."""
        action_lower = action.lower()

        # Connected is handled by the server

        if action_lower == "name":
            return {"Value": device_name}

        if action_lower == "description":
            mapped = [k for k in channels if channels[k] is not None]
            return {
                "Value": (
                    f"Sensors mapped to: "
                    f"{', '.join(mapped) if mapped else 'none'}"
                )
            }

        if action_lower == "averageperiod":
            put_key = next((k for k in (params or {}) if k.lower() == "averageperiod"), None)
            if put_key is not None:
                # Strict parameter matching. Alpaca explicitly tests bad casing
                if put_key != "AveragePeriod":
                    return bad_request(
                        "Parameter 'AveragePeriod' missing or bad casing"
                    )
                v = params["AveragePeriod"]
                try:
                    # Note: Conform can pass floats, check them
                    val = float(v)
                except (ValueError, TypeError):
                    return bad_request(f"Invalid average period: {v}")
                if val < 0.0:
                    return {
                        "Value": 0.0,
                        "ErrorNumber": 0x401,
                        "ErrorMessage": f"Invalid average period: {v}",
                    }
                device_state["average_period"] = val
            return {"Value": device_state["average_period"]}

        if action_lower == "refresh":
            return {"Value": None}

        # --- Property reads ---

        if action_lower in OC_PROPERTIES:
            if action_lower not in channels:
                return {
                    "Value": 0.0,
                    "ErrorNumber": 0x400,
                    "ErrorMessage": f"No sensor mapped for '{action}'",
                }
            channel = channels[action_lower]
            value = await channel.get_value()
            if value is None:
                # mapped, but no value now: not "not implemented", clients would hide the property
                return driver_error(
                    ERROR_VALUE_NOT_SET,
                    f"Sensor '{channel.description}' unavailable or invalid",
                )
            return {"Value": value}

        # --- Time since last update ---

        if action_lower == "timesincelastupdate":
            sensor_name = str(get_param(params, "sensorname") or "").lower()

            if not sensor_name:
                times = []
                for ch in channels.values():
                    if ch is not None:
                        t = await ch.get_seconds_since_update()
                        if t is not None:
                            times.append(t)
                if not times:
                    return driver_error(ERROR_VALUE_NOT_SET, "No sensor has a value")
                return {"Value": min(times)}

            if sensor_name not in OC_PROPERTIES:
                return driver_error(
                    ERROR_INVALID_VALUE, f"Unknown sensor name '{sensor_name}'"
                )
            channel = channels.get(sensor_name)
            if not channel:
                return driver_error(
                    ERROR_NOT_IMPLEMENTED, f"Sensor '{sensor_name}' not mapped"
                )
            seconds = await channel.get_seconds_since_update()
            if seconds is None:
                return driver_error(
                    ERROR_VALUE_NOT_SET, f"Sensor '{sensor_name}' has no value"
                )
            return {"Value": seconds}

        # --- Sensor description ---

        if action_lower == "sensordescription":
            sensor_name = str(get_param(params, "sensorname") or "").lower()

            if not sensor_name:
                return {
                    "Value": "",
                    "ErrorNumber": 0x401,
                    "ErrorMessage": "SensorName parameter missing or empty",
                }
            if sensor_name not in OC_PROPERTIES:
                return driver_error(
                    ERROR_INVALID_VALUE, f"Unknown sensor name '{sensor_name}'"
                )
            channel = channels.get(sensor_name)
            if not channel:
                return driver_error(
                    ERROR_NOT_IMPLEMENTED, f"Sensor '{sensor_name}' not mapped"
                )
            return {"Value": channel.description}

        # --- Standard device info ---

        if action_lower in (
            "driverinfo",
            "driverversion",
            "interfaceversion",
            "supportedactions",
        ):
            return common_device_info(action_lower)

        return bad_request(f"Action '{action}' not supported")

    return handle_oc
