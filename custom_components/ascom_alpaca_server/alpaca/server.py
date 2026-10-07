"""ASCOM Alpaca HTTP server and UDP discovery.

This module is platform-agnostic — it only depends on aiohttp and the
local ``alpaca`` package.  No Home Assistant imports.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from aiohttp import web

from .const import ALPACA_DISCOVERY_PORT, SERVER_MANUFACTURER, SERVER_NAME, SERVER_VERSION
from .const import COMMAND_ACTIONS
from .device_registry import AlpacaDeviceRegistry
from .handlers._common import (
    ERROR_UNSPECIFIED,
    DeviceError,
    driver_error,
    handle_connected,
)

_LOGGER = logging.getLogger(__name__)

# Canonical Alpaca device type names (multi-word types need special casing)
_DEVICE_TYPE_NAMES: dict[str, str] = {
    "switch": "Switch",
    "safetymonitor": "SafetyMonitor",
    "observingconditions": "ObservingConditions",
    "camera": "Camera",
    "dome": "Dome",
    "filterwheel": "FilterWheel",
    "focuser": "Focuser",
    "rotator": "Rotator",
    "telescope": "Telescope",
    "covercalibrator": "CoverCalibrator",
}


def _format_device_type(device_type: str) -> str:
    """Return the canonical Alpaca device type name."""
    return _DEVICE_TYPE_NAMES.get(device_type.lower(), device_type.capitalize())


class AlpacaServer:
    """ASCOM Alpaca HTTP server with request routing."""

    def __init__(
        self,
        registry: AlpacaDeviceRegistry,
        port: int,
        discovery_enabled: bool = True,
    ) -> None:
        """Initialize the server."""
        self.registry = registry
        self.port = port
        self.discovery_enabled = discovery_enabled
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._server_txn_id: int = 0
        self._discovery_transport: asyncio.DatagramTransport | None = None

    async def start(self) -> None:
        """Start the HTTP server and optional discovery responder."""
        self._app = web.Application()
        self._setup_routes()

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        try:
            self._site = web.TCPSite(self._runner, "0.0.0.0", self.port)
            await self._site.start()
        except OSError:
            # for example the port is in use: do not leave the runner behind
            await self._runner.cleanup()
            self._runner = None
            self._site = None
            raise
        _LOGGER.info("Alpaca server started on port %d", self.port)

        if self.discovery_enabled:
            await self._start_discovery()

    async def stop(self) -> None:
        """Stop the HTTP server and discovery responder."""
        if self._discovery_transport is not None:
            self._discovery_transport.close()
            self._discovery_transport = None

        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()
        _LOGGER.info("Alpaca server stopped")

    # --- Route Setup ---

    def _setup_routes(self) -> None:
        """Set up all API routes."""
        app = self._app
        assert app is not None

        # Management API
        app.router.add_get("/management/apiversions", self._mgmt_api_versions)
        app.router.add_get(
            "/management/v1/configureddevices", self._mgmt_configured_devices
        )
        app.router.add_get(
            "/management/v1/description", self._mgmt_description
        )

        # Catch-all device API: /api/v1/{device_type}/{device_number}/{action}
        app.router.add_route(
            "*",
            "/api/v1/{device_type}/{device_number}/{action}",
            self._handle_device_request,
        )

    # --- Management Endpoints ---

    async def _mgmt_api_versions(self, request: web.Request) -> web.Response:
        params = dict(request.query)
        return self._json_response([1], params)

    async def _mgmt_configured_devices(
        self, request: web.Request
    ) -> web.Response:
        devices = []
        for dev in self.registry.get_all_devices():
            devices.append(
                {
                    "DeviceName": dev.device_name,
                    "DeviceType": _format_device_type(dev.device_type),
                    "DeviceNumber": dev.device_number,
                    "UniqueID": dev.unique_id,
                }
            )
        params = dict(request.query)
        return self._json_response(devices, params)

    async def _mgmt_description(self, request: web.Request) -> web.Response:
        desc = {
            "ServerName": SERVER_NAME,
            "Manufacturer": SERVER_MANUFACTURER,
            "ManufacturerVersion": SERVER_VERSION,
            "Location": "Home Assistant",
        }
        params = dict(request.query)
        return self._json_response(desc, params)

    # --- Device Request Router ---

    async def _handle_device_request(
        self, request: web.Request
    ) -> web.Response:
        """Route /api/v1/{device_type}/{device_number}/{action} to handler."""
        device_type = request.match_info.get("device_type", "")
        action = request.match_info.get("action", "")

        # Collect parameters from query string and/or POST body
        params = dict(request.query)
        if request.method in ("PUT", "POST"):
            try:
                post_data = await request.post()
                params.update(post_data)
            except Exception:
                pass

        if device_type != device_type.lower():
            return self._error_response("Device type must be lowercase")

        try:
            device_number = int(request.match_info.get("device_number", "0"))
        except ValueError:
            return self._error_response("Invalid device number")

        # Look up device
        device = self.registry.get_device(device_type, device_number)
        if device is None:
            return self._error_response(
                f"Device {device_type}/{device_number} not found"
            )

        if action.lower() in COMMAND_ACTIONS and request.method != "PUT":
            return self._error_response(
                f"'{action}' is a command: send it with PUT, not {request.method}"
            )

        if action.lower() == "connected":
            # Kept per client by the server, the same for every device type
            client_id = self._get_client_params(params)["ClientID"]
            result = handle_connected(
                device.connected_clients, request.method, params, client_id
            )
            return self._result_response(result, params)

        # Call the device handler
        try:
            result = await device.handler(action, params)
        except DeviceError as err:
            result = driver_error(ERROR_UNSPECIFIED, str(err))
        except Exception as exc:
            _LOGGER.exception(
                "Error handling %s/%d/%s", device_type, device_number, action
            )
            return self._error_response(f"Handler error: {exc}", status=500)

        return self._result_response(result, params)

    def _result_response(
        self, result: dict[str, Any], params: dict[str, Any]
    ) -> web.Response:
        """Build the HTTP response from the result of a device handler.

        HTTP 200 means the request was understood and the ASCOM method ran: an exception of the
        device (not implemented, invalid value, ...) comes as ``ErrorNumber`` in the JSON body. A handler
        marks a request it did not understand with ``HttpStatus`` (400, see ``bad_request``): that
        is answered with the status and the message as plain text.
        """
        status = result.get("HttpStatus", 200)
        error_message = result.get("ErrorMessage", "")
        if status != 200:
            return self._error_response(error_message, status=status)
        return self._json_response(
            result.get("Value"),
            params,
            error_number=result.get("ErrorNumber", 0),
            error_message=error_message,
        )

    # --- Response Helpers ---

    def _next_txn_id(self) -> int:
        self._server_txn_id += 1
        return self._server_txn_id

    def _get_client_params(self, params: dict[str, Any]) -> dict[str, int]:
        client_id = 0
        client_txn = 0
        for k, v in params.items():
            k_lower = k.lower()
            if k_lower == "clientid":
                try:
                    client_id = int(v)
                    if client_id < 0 or client_id > 4294967295:
                        client_id = 0
                except (ValueError, TypeError):
                    pass
            elif k_lower == "clienttransactionid":
                try:
                    client_txn = int(v)
                    if client_txn < 0 or client_txn > 4294967295:
                        client_txn = 0
                except (ValueError, TypeError):
                    pass
        return {"ClientID": client_id, "ClientTransactionID": client_txn}

    def _json_response(
        self,
        value: Any,
        params: dict[str, Any],
        error_number: int = 0,
        error_message: str = "",
        status: int = 200,
    ) -> web.Response:
        client = self._get_client_params(params)
        body = {
            "Value": value,
            "ClientTransactionID": client["ClientTransactionID"],
            "ServerTransactionID": self._next_txn_id(),
            "ErrorNumber": error_number,
            "ErrorMessage": error_message,
        }
        return web.json_response(body, status=status)

    def _error_response(self, message: str, status: int = 400) -> web.Response:
        """HTTP 400 (request not understood) or 500 (technical error): the message as plain text."""
        return web.Response(status=status, text=message, content_type="text/plain")

    # --- UDP Discovery ---

    async def _start_discovery(self) -> None:
        """Start the Alpaca UDP discovery responder."""
        try:
            loop = asyncio.get_running_loop()
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _DiscoveryProtocol(self.port),
                local_addr=("0.0.0.0", ALPACA_DISCOVERY_PORT),
                allow_broadcast=True,
            )
            self._discovery_transport = transport
            _LOGGER.info(
                "Alpaca discovery responder started on UDP port %d",
                ALPACA_DISCOVERY_PORT,
            )
        except OSError as err:
            _LOGGER.warning(
                "Could not start Alpaca discovery on port %d: %s",
                ALPACA_DISCOVERY_PORT,
                err,
            )


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """UDP protocol for Alpaca device discovery."""

    def __init__(self, alpaca_port: int) -> None:
        self.alpaca_port = alpaca_port
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            message = data.decode("utf-8", errors="ignore").strip()
        except Exception:
            return
        if message.lower().startswith("alpacadiscovery"):
            response = json.dumps({"AlpacaPort": self.alpaca_port})
            if self.transport is not None:
                self.transport.sendto(response.encode("utf-8"), addr)
                _LOGGER.debug("Discovery response sent to %s", addr)
