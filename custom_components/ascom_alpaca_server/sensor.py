"""Sensor platform of ASCOM Alpaca Server: the dew point and the dew point spread, computed from the
ObservingConditions mapping.

The entities exist only while the value can be computed (see ``DerivedChannels`` in ``ha_bridge``).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_DERIVED, DOMAIN, INTEGRATION_NAME

_LOGGER = logging.getLogger(__name__)

# The values are read from the mapped sensors: no subscription that would have to follow a new mapping
SCAN_INTERVAL = timedelta(seconds=60)

UNIQUE_ID_DEW_POINT = "dew_point"
UNIQUE_ID_DEW_POINT_SPREAD = "dew_point_spread"

DEW_POINT_METHOD = "Computed from temperature and humidity (Magnus formula)"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors for the values that can be computed."""
    data = hass.data[DOMAIN][entry.entry_id]
    derived = data[DATA_DERIVED]

    entities: list[_DerivedSensor] = []
    if derived.dew_point is not None:
        entities.append(ComputedDewPointSensor(entry, data))
    if derived.spread is not None:
        entities.append(DewPointSpreadSensor(entry, data))

    _remove_stale_entities(hass, entry, {entity.unique_id for entity in entities})
    async_add_entities(entities, True)


def _remove_stale_entities(
    hass: HomeAssistant, entry: ConfigEntry, wanted: set[str]
) -> None:
    """Remove the registry entries of values that cannot be computed any more (the mapping changed)."""
    registry = er.async_get(hass)
    ours = {f"{entry.entry_id}_{UNIQUE_ID_DEW_POINT}", f"{entry.entry_id}_{UNIQUE_ID_DEW_POINT_SPREAD}"}
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registered.unique_id in ours and registered.unique_id not in wanted:
            registry.async_remove(registered.entity_id)


class _DerivedSensor(SensorEntity):
    """A value that the server computes from the ObservingConditions mapping, in degrees Celsius."""

    _attr_has_entity_name = True
    _attr_should_poll = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "°C"
    _attr_suggested_display_precision = 1

    _field = ""  # attribute of DerivedChannels
    _unique_suffix = ""

    def __init__(self, entry: ConfigEntry, data: dict) -> None:
        self._entry = entry
        self._data = data
        self._attr_unique_id = f"{entry.entry_id}_{self._unique_suffix}"
        self._attr_native_value: float | None = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=INTEGRATION_NAME,
        )

    @property
    def available(self) -> bool:
        """The value is there (the sources report)."""
        return self._attr_native_value is not None

    async def async_update(self) -> None:
        """Read the value: the channel follows the current mapping."""
        channel = getattr(self._data[DATA_DERIVED], self._field)
        value = None if channel is None else await channel.get_value()
        self._attr_native_value = None if value is None else round(value, 1)


class ComputedDewPointSensor(_DerivedSensor):
    """The dew point, computed from temperature and humidity (only exists when no dew point is mapped)."""

    _attr_name = "Dew Point"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_extra_state_attributes = {"method": DEW_POINT_METHOD}
    _field = "dew_point"
    _unique_suffix = UNIQUE_ID_DEW_POINT


class DewPointSpreadSensor(_DerivedSensor):
    """Temperature minus dew point.

    A difference of temperatures: no device class "temperature", Home Assistant would convert it like
    an absolute temperature when the user prefers Fahrenheit.
    """

    _attr_name = "Dew Point Spread"
    _attr_icon = "mdi:water-thermometer"
    _field = "spread"
    _unique_suffix = UNIQUE_ID_DEW_POINT_SPREAD
