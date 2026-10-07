"""Convert Home Assistant sensor values to the units ASCOM Alpaca expects.

Home Assistant sensors report in whatever unit the user (or the source
integration) chose, while ASCOM ObservingConditions properties have fixed
units. Values are converted using the entity's ``unit_of_measurement``.

Pure Python, no Home Assistant imports.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

_LOGGER = logging.getLogger(__name__)

# Each table maps a source unit to (factor, offset): result = value * factor + offset

# Target: degrees Celsius
_TEMPERATURE: dict[str, tuple[float, float]] = {
    "°C": (1.0, 0.0),
    "°F": (5.0 / 9.0, -32.0 * 5.0 / 9.0),
    "K": (1.0, -273.15),
}

# Target: hPa
_PRESSURE: dict[str, tuple[float, float]] = {
    "hPa": (1.0, 0.0),
    "mbar": (1.0, 0.0),
    "Pa": (0.01, 0.0),
    "kPa": (10.0, 0.0),
    "cbar": (10.0, 0.0),
    "bar": (1000.0, 0.0),
    "mmHg": (1.33322387415, 0.0),
    "inHg": (33.8638866667, 0.0),
    "psi": (68.9475729318, 0.0),
}

# Target: m/s
_SPEED: dict[str, tuple[float, float]] = {
    "m/s": (1.0, 0.0),
    "km/h": (1.0 / 3.6, 0.0),
    "mph": (0.44704, 0.0),
    "kn": (1852.0 / 3600.0, 0.0),
    "ft/s": (0.3048, 0.0),
    "in/s": (0.0254, 0.0),
}

# Target: mm/h
_RAIN_RATE: dict[str, tuple[float, float]] = {
    "mm/h": (1.0, 0.0),
    "in/h": (25.4, 0.0),
    "mm/d": (1.0 / 24.0, 0.0),
    "in/d": (25.4 / 24.0, 0.0),
}

# ObservingConditions property -> conversion table. Properties not listed here
# (humidity, cloud cover, wind direction, sky quality, ...) are passed through.
_TABLES: dict[str, dict[str, tuple[float, float]]] = {
    "temperature": _TEMPERATURE,
    "dewpoint": _TEMPERATURE,
    "skytemperature": _TEMPERATURE,
    "pressure": _PRESSURE,
    "windspeed": _SPEED,
    "windgust": _SPEED,
    "rainrate": _RAIN_RATE,
}

# A Home Assistant weather entity keeps its values in attributes. ObservingConditions property ->
# (attribute with the value, attribute with its unit). Properties that are not listed (rain rate,
# sky brightness, sky quality, sky temperature, star FWHM) are not available from a weather entity.
_WEATHER_ATTRIBUTES: dict[str, tuple[str, str | None]] = {
    "temperature": ("temperature", "temperature_unit"),
    "dewpoint": ("dew_point", "temperature_unit"),
    "humidity": ("humidity", None),
    "pressure": ("pressure", "pressure_unit"),
    "windspeed": ("wind_speed", "wind_speed_unit"),
    "windgust": ("wind_gust_speed", "wind_speed_unit"),
    "winddirection": ("wind_bearing", None),
    "cloudcover": ("cloud_coverage", None),
}

# A weather entity may report the wind direction as a compass point
_COMPASS: dict[str, float] = {
    name: index * 22.5
    for index, name in enumerate(
        ("n", "nne", "ne", "ene", "e", "ese", "se", "sse",
         "s", "ssw", "sw", "wsw", "w", "wnw", "nw", "nnw")
    )
}

_warned: set[tuple[str, str]] = set()


def to_alpaca_unit(prop: str, value: float, unit: str | None) -> float:
    """Convert ``value`` (given in ``unit``) to the Alpaca unit of ``prop``.

    Returns the value unchanged if the property has no fixed conversion, the
    entity reports no unit, or the unit is not known (logged once).
    """
    table = _TABLES.get(prop)
    if table is None or not unit:
        return value

    conversion = table.get(unit.strip())
    if conversion is None:
        if (prop, unit) not in _warned:
            _warned.add((prop, unit))
            _LOGGER.warning(
                "Unsupported unit '%s' for %s — passing value through unchanged",
                unit,
                prop,
            )
        return value

    factor, offset = conversion
    return value * factor + offset


def _bearing(raw: Any) -> float | None:
    """A wind direction in degrees from a number or a compass point ("NNE")."""
    try:
        return float(raw)
    except (ValueError, TypeError):
        return _COMPASS.get(str(raw).strip().casefold())


def weather_value(prop: str, attributes: Mapping[str, Any]) -> float | None:
    """The value of an ObservingConditions property from a weather entity, in the Alpaca unit.

    None if the weather entity does not provide the property (or it has no usable value). The unit
    comes from the unit attribute of the weather entity; without one the value is passed through.
    """
    names = _WEATHER_ATTRIBUTES.get(prop)
    if names is None:
        return None
    attribute, unit_attribute = names

    raw = attributes.get(attribute)
    if raw is None:
        return None
    if prop == "winddirection":
        value = _bearing(raw)
    else:
        try:
            value = float(raw)
        except (ValueError, TypeError):
            value = None
    if value is None:
        return None

    unit = attributes.get(unit_attribute) if unit_attribute else None
    return to_alpaca_unit(prop, value, unit)
