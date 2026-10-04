"""Integration setup for ASCOM Alpaca Server."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .alpaca import AlpacaDeviceRegistry, AlpacaServer
from .const import (
    ALPACA_SERVER_API_KEY,
    CONF_ALPACA_DISCOVERY,
    CONF_ALPACA_PORT,
    DATA_REGISTRY,
    DATA_SERVER,
    DEFAULT_ALPACA_DISCOVERY,
    DEFAULT_ALPACA_PORT,
    DOMAIN,
)
from .ha_bridge import rebuild_devices

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ASCOM Alpaca Server from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data.setdefault(ALPACA_SERVER_API_KEY, {})

    # Use existing registry if available (survives integration reload),
    # otherwise create a new one. This keeps external devices registered.
    registry = hass.data[ALPACA_SERVER_API_KEY].get("registry")
    if registry is None:
        registry = AlpacaDeviceRegistry()
        hass.data[ALPACA_SERVER_API_KEY]["registry"] = registry

    # Build internal devices via the HA bridge
    rebuild_devices(registry, hass, entry.options)

    # Determine port (options override data)
    port = int(
        entry.options.get(
            CONF_ALPACA_PORT,
            entry.data.get(CONF_ALPACA_PORT, DEFAULT_ALPACA_PORT),
        )
    )
    discovery = entry.options.get(
        CONF_ALPACA_DISCOVERY,
        entry.data.get(CONF_ALPACA_DISCOVERY, DEFAULT_ALPACA_DISCOVERY),
    )

    # Create and start the Alpaca server
    server = AlpacaServer(registry, port, discovery)
    await server.start()

    # Store internal references
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_REGISTRY: registry,
        DATA_SERVER: server,
    }

    # Expose the external registration API for client integrations.
    # ASCOM Alpaca Safety (and others) look for hass.data[ALPACA_SERVER_API_KEY].
    async def _async_register_device(
        device_type: str,
        device_name: str,
        handler: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> Callable[[], None]:
        """Async wrapper around the sync registry method."""
        return registry.register_device(device_type, device_name, handler)

    hass.data[ALPACA_SERVER_API_KEY]["async_register_device"] = _async_register_device

    # Listen for options changes
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.info(
        "ASCOM Alpaca Server started on port %d (discovery: %s)",
        port,
        discovery,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload ASCOM Alpaca Server."""
    data = hass.data[DOMAIN].pop(entry.entry_id, {})
    server: AlpacaServer | None = data.get(DATA_SERVER)

    if server:
        await server.stop()

    # DO NOT remove the ALPACA_SERVER_API_KEY so that external integrations
    # don't lose their registration during a config reload.

    _LOGGER.info("ASCOM Alpaca Server unloaded")
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update — reload the integration."""
    _LOGGER.info("Options changed, reloading ASCOM Alpaca Server")
    await hass.config_entries.async_reload(entry.entry_id)
