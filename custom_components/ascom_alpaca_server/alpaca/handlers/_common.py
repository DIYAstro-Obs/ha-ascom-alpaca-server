"""Shared utilities for Alpaca device protocol handlers."""

from __future__ import annotations

from typing import Any

from ..const import SERVER_VERSION


def common_device_info(action: str) -> dict[str, Any]:
    """Return common Alpaca device info responses.

    Shared by all handler types for standard device metadata actions.
    """
    if action == "driverinfo":
        return {"Value": "ASCOM Alpaca Server"}
    if action == "driverversion":
        return {"Value": SERVER_VERSION}
    if action == "interfaceversion":
        return {"Value": 1}
    if action == "supportedactions":
        return {"Value": []}
    return {"Value": None}
