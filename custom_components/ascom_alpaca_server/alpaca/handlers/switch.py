"""ASCOM Alpaca Switch protocol handler.

Creates an action handler for a multi-switch container device.
All platform-specific I/O is abstracted behind SwitchChannel callbacks.
"""

from __future__ import annotations

from typing import Any

from ..models import ActionHandler, SwitchChannel
from ._common import bad_request, common_device_info


def create_switch_handler(
    channels: list[SwitchChannel],
    device_name: str = "Switches",
) -> ActionHandler:
    """Create an Alpaca Switch action handler for the given channels.

    Args:
        channels: List of abstract switch channels (index = Alpaca switch Id).
        device_name: Name reported by the Alpaca ``name`` property.

    Returns:
        An async action handler suitable for ``AlpacaDevice.handler``.
    """

    def _get_param(params: dict[str, Any], name: str) -> Any:
        name_lower = name.lower()
        for k, v in params.items():
            if k.lower() == name_lower:
                return v
        return None

    def _resolve_id(params: dict[str, Any]) -> int | None:
        """Return the switch index from params, or None if invalid."""
        val = _get_param(params, "id")
        if val is None:
            return None
        try:
            idx = int(val)
        except (ValueError, TypeError):
            return None
        if idx < 0 or idx >= len(channels):
            return None
        return idx

    def _id_error(
        params: dict[str, Any], default_value: Any = None
    ) -> dict[str, Any]:
        """Build an error response for an invalid switch Id."""
        try:
            int(_get_param(params, "id"))
        except (ValueError, TypeError):
            return bad_request("Parameter 'Id' missing or not an integer")
        # an integer, but there is no such switch: an ASCOM InvalidValue exception
        return {
            "Value": default_value,
            "ErrorNumber": 0x401,
            "ErrorMessage": f"Invalid switch Id: {_get_param(params, 'id')}",
        }

    async def handle_switch(
        action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle Alpaca switch requests."""
        action_lower = action.lower()

        # --- Common device properties (Connected is handled by the server) ---

        if action_lower == "name":
            return {"Value": device_name}

        if action_lower == "description":
            return {
                "Value": f"Switch container ({len(channels)} switch(es))"
            }

        if action_lower == "maxswitch":
            return {"Value": len(channels)}

        if action_lower == "canwrite":
            idx = _resolve_id(params)
            if idx is None:
                return _id_error(params, default_value=True)
            return {"Value": True}

        # --- Per-switch read operations ---

        if action_lower == "getswitch":
            idx = _resolve_id(params)
            if idx is None:
                return _id_error(params, default_value=False)
            state = await channels[idx].get_state()
            if state is None:
                return {
                    "Value": False,
                    "ErrorNumber": 0x400,
                    "ErrorMessage": f"Switch '{channels[idx].name}' unavailable",
                }
            return {"Value": state}

        if action_lower == "getswitchname":
            idx = _resolve_id(params)
            if idx is None:
                return _id_error(params, default_value="")
            return {"Value": channels[idx].name}

        if action_lower == "getswitchdescription":
            idx = _resolve_id(params)
            if idx is None:
                return _id_error(params, default_value="")
            return {"Value": channels[idx].description}

        if action_lower == "getswitchvalue":
            idx = _resolve_id(params)
            if idx is None:
                return _id_error(params, default_value=0.0)
            state = await channels[idx].get_state()
            return {"Value": 1.0 if state else 0.0}

        # --- Switch value range ---

        if action_lower == "minswitchvalue":
            idx = _resolve_id(params)
            if idx is None:
                return _id_error(params, default_value=0.0)
            return {"Value": 0.0}

        if action_lower == "maxswitchvalue":
            idx = _resolve_id(params)
            if idx is None:
                return _id_error(params, default_value=0.0)
            return {"Value": 1.0}

        if action_lower == "switchstep":
            idx = _resolve_id(params)
            if idx is None:
                return _id_error(params, default_value=0.0)
            return {"Value": 1.0}

        # --- Per-switch write operations ---

        if action_lower == "setswitch":
            idx = _resolve_id(params)
            if idx is None:
                return _id_error(params)
            
            target_state = _get_param(params, "state")
            if target_state is None:
                return bad_request("Parameter 'State' missing")
            if isinstance(target_state, str):
                v_lower = target_state.lower()
                if v_lower not in ("true", "false"):
                    return bad_request(f"Invalid boolean value: {target_state}")
                target_state = v_lower == "true"
            elif not isinstance(target_state, bool):
                return bad_request(
                    f"Invalid parameter type for State: {type(target_state)}"
                )
            
            await channels[idx].set_state(bool(target_state))
            return {"Value": None}

        if action_lower == "setswitchvalue":
            idx = _resolve_id(params)
            if idx is None:
                return _id_error(params)
            
            val = _get_param(params, "value")
            if val is None:
                return bad_request("Parameter 'Value' missing")

            try:
                value = float(val)
            except (ValueError, TypeError):
                return bad_request(f"Invalid float value: {val}")
            
            await channels[idx].set_state(value > 0)
            return {"Value": None}

        if action_lower == "setswitchname":
            idx = _resolve_id(params)
            if idx is None:
                return _id_error(params)
            
            name = _get_param(params, "name")
            if name is None:
                return bad_request("Parameter 'Name' missing")
            return {"Value": None}  # read-only names

        # --- Standard device info ---

        if action_lower in (
            "driverinfo",
            "driverversion",
            "interfaceversion",
            "supportedactions",
        ):
            return common_device_info(action_lower)

        return bad_request(f"Action '{action}' not supported for Switch")

    return handle_switch
