"""Alpaca device protocol handlers."""

from __future__ import annotations

from .switch import create_switch_handler
from .observing_conditions import create_oc_handler
from .covercalibrator import create_covercalibrator_handler
from .dome import create_dome_handler

__all__ = [
    "create_switch_handler",
    "create_oc_handler",
    "create_covercalibrator_handler",
    "create_dome_handler",
]
