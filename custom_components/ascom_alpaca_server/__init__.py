"""Integration setup for ASCOM Alpaca Server."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import instance_id

from .alpaca import AlpacaDeviceRegistry, AlpacaServer
from .const import (
    ALPACA_SERVER_API_KEY,
    CONF_ALPACA_DISCOVERY,
    CONF_ALPACA_PORT,
    DATA_DERIVED,
    DATA_FLAGS,
    DATA_LISTEN,
    DATA_REGISTRY,
    DATA_SERVER,
    DEFAULT_ALPACA_DISCOVERY,
    DEFAULT_ALPACA_PORT,
    DOMAIN,
    PLATFORMS,
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
        # the instance id keeps the UniqueIDs of the devices unique across Home Assistant servers
        registry = AlpacaDeviceRegistry(await instance_id.async_get(hass))
        hass.data[ALPACA_SERVER_API_KEY]["registry"] = registry

    # Build internal devices via the HA bridge
    derived = rebuild_devices(registry, hass, entry.options)

    port, discovery = _listen_settings(entry)

    # Create and start the Alpaca server
    server = AlpacaServer(registry, port, discovery)
    try:
        await server.start()
    except OSError as err:
        # Home Assistant shows the message and tries again later
        raise ConfigEntryNotReady(
            f"The Alpaca server cannot listen on port {port}: {err}"
        ) from err

    # Store internal references
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_REGISTRY: registry,
        DATA_SERVER: server,
        DATA_LISTEN: (port, discovery),
        DATA_DERIVED: derived,
        DATA_FLAGS: derived.flags,
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

    # The sensors of the computed values (dew point, dew point spread)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    data = hass.data[DOMAIN].pop(entry.entry_id, {})
    server: AlpacaServer | None = data.get(DATA_SERVER)

    if server:
        await server.stop()

    # DO NOT remove the ALPACA_SERVER_API_KEY so that external integrations
    # don't lose their registration during a config reload.

    _LOGGER.info("ASCOM Alpaca Server unloaded")
    return True


def _listen_settings(entry: ConfigEntry) -> tuple[int, bool]:
    """Port and discovery of the server (the options override the data of the setup)."""
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
    return port, bool(discovery)


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle an options update.

    Only the port and the discovery need a restart of the server. A new mapping just builds the devices
    again: the listener keeps running and the clients stay connected. The one exception is a mapping that
    makes a computed value appear or disappear (dew point, dew point spread): its sensor is created or
    removed by a reload.
    """
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data is not None and _listen_settings(entry) == data[DATA_LISTEN]:
        derived = rebuild_devices(data[DATA_REGISTRY], hass, entry.options)
        if derived.flags == data[DATA_FLAGS]:
            _LOGGER.info("Mappings changed, rebuilt the devices")
            data[DATA_DERIVED] = derived
            return
        _LOGGER.info("The computed dew point values changed, reloading ASCOM Alpaca Server")
    else:
        _LOGGER.info("Port or discovery changed, reloading ASCOM Alpaca Server")
    await hass.config_entries.async_reload(entry.entry_id)
