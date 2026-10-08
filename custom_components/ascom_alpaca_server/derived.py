"""Values the server computes from other values, without Home Assistant imports."""

from __future__ import annotations

import math

# Magnus formula (constants of Sonntag, 1990): the dew point from the temperature and the relative
# humidity, good to about +-0.4 degrees Celsius within the range below.
_MAGNUS_B = 17.62
_MAGNUS_C = 243.12  # degrees Celsius
_TEMPERATURE_RANGE = (-45.0, 60.0)


def dew_point(temperature_c: float | None, humidity_percent: float | None) -> float | None:
    """The dew point in degrees Celsius, or None if a value is missing or outside the valid range.

    The humidity has to be above 0 and at most 100 per cent, the temperature between -45 and 60 degrees.
    """
    if temperature_c is None or humidity_percent is None:
        return None
    low, high = _TEMPERATURE_RANGE
    if not low <= temperature_c <= high or not 0 < humidity_percent <= 100:
        return None
    gamma = math.log(humidity_percent / 100) + _MAGNUS_B * temperature_c / (_MAGNUS_C + temperature_c)
    return _MAGNUS_C * gamma / (_MAGNUS_B - gamma)


def dew_point_spread(temperature_c: float | None, dew_point_c: float | None) -> float | None:
    """Temperature minus dew point in degrees Celsius (None if one of them is missing).

    A small spread means that dew forms on cold optics and mirrors.
    """
    if temperature_c is None or dew_point_c is None:
        return None
    return temperature_c - dew_point_c
