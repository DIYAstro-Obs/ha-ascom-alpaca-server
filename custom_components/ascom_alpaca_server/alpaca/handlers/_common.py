"""Shared utilities for Alpaca device protocol handlers."""

from __future__ import annotations

from typing import Any

from ..const import SERVER_VERSION

# ASCOM error numbers
ERROR_NOT_IMPLEMENTED = 0x400
ERROR_INVALID_VALUE = 0x401
ERROR_VALUE_NOT_SET = 0x402  # the property is there, but has no value (now)
ERROR_UNSPECIFIED = 0x500  # the device does not answer


class DeviceError(Exception):
    """The device could not do what the request asked (a Home Assistant service failed).

    The server answers with an ASCOM exception (HTTP 200, ``ErrorNumber`` 0x500) and the message,
    not with a technical error: the request was fine, the device did not do it.
    """


def get_param(params: dict[str, Any], name: str) -> Any:
    """The value of a request parameter, found without regard to the case of its name (None: missing)."""
    name = name.lower()
    for key, value in params.items():
        if key.lower() == name:
            return value
    return None


def driver_error(number: int, message: str) -> dict[str, Any]:
    """An exception of the device. The server answers HTTP 200 with the number in the body."""
    return {"Value": None, "ErrorNumber": number, "ErrorMessage": message}


def bad_request(message: str) -> dict[str, Any]:
    """A request the device does not understand: unknown action, missing or malformed parameter.

    The server answers with HTTP 400 and the message as plain text. A device that understands the
    request but cannot do it (not implemented, invalid value) returns ``ErrorNumber`` instead: that
    is an ASCOM exception and the server answers with HTTP 200.
    """
    return {
        "Value": None,
        "ErrorNumber": ERROR_NOT_IMPLEMENTED,
        "ErrorMessage": message,
        "HttpStatus": 400,
    }


def handle_connected(
    connected_clients: set[int],
    method: str,
    params: dict[str, Any],
    client_id: int,
) -> dict[str, Any]:
    """The ``Connected`` property of a device, kept per client.

    A GET tells whether the client of the request is connected, a PUT connects or disconnects it. The
    server calls this for every device type before the device handler, so the handlers know nothing
    about connections: a second client that disconnects does not disconnect the first one.
    """
    if method.upper() not in ("PUT", "POST"):
        return {"Value": client_id in connected_clients}

    # Strict parameter name: the Alpaca compliance tests check the casing
    key = next((k for k in params if k.lower() == "connected"), None)
    if key != "Connected":
        return bad_request("Parameter 'Connected' missing or bad casing")
    value = str(params[key]).lower()
    if value not in ("true", "false"):
        return bad_request(f"Invalid boolean value: {params[key]}")

    if value == "true":
        connected_clients.add(client_id)
    else:
        connected_clients.discard(client_id)
    return {"Value": client_id in connected_clients}


def common_device_info(action: str, interface_version: int = 1) -> dict[str, Any]:
    """Return common Alpaca device info responses.

    Shared by all handler types for standard device metadata actions.
    ``interface_version`` is the ASCOM interface version of the device type
    (e.g. 2 for IDomeV2).
    """
    if action == "driverinfo":
        return {"Value": "ASCOM Alpaca Server"}
    if action == "driverversion":
        return {"Value": SERVER_VERSION}
    if action == "interfaceversion":
        return {"Value": interface_version}
    if action == "supportedactions":
        return {"Value": []}
    return {"Value": None}
