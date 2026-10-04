"""Bridge between Home Assistant entities and the Alpaca protocol layer.

This module is the **only** place where HA-specific I/O (state reads, service
calls) is wired into the abstract Alpaca handler callbacks.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .alpaca import (
    AlpacaDevice,
    AlpacaDeviceRegistry,
    CalibratorChannel,
    OCSensorChannel,
    SwitchChannel,
    DEVICE_TYPE_COVERCALIBRATOR,
    DEVICE_TYPE_OBSERVINGCONDITIONS,
    DEVICE_TYPE_SWITCH,
)
from .alpaca.handlers import (
    create_covercalibrator_handler,
    create_oc_handler,
    create_switch_handler,
)
from .const import (
    CONF_CALIBRATOR_BRIGHTNESS_ENTITY,
    CONF_CALIBRATOR_ONOFF_ENTITY,
    CONF_OBSERVING_CONDITIONS,
    CONF_SWITCH_ENTITIES,
    CONF_SWITCH_NAMES,
)
from .unit_conversion import to_alpaca_unit

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def rebuild_devices(
    registry: AlpacaDeviceRegistry,
    hass: HomeAssistant,
    options: dict[str, Any],
) -> None:
    """Rebuild all internal devices from HA config options.

    Called on startup and whenever options change. External devices are
    preserved automatically by the registry.
    """
    registry.remove_internal_devices()

    # --- Switch container ---
    switch_entity_ids: list[str] = options.get(CONF_SWITCH_ENTITIES, [])
    switch_names: dict[str, str] = options.get(CONF_SWITCH_NAMES, {})
    if switch_entity_ids:
        channels = _build_switch_channels(hass, switch_entity_ids, switch_names)
        handler = create_switch_handler(channels, device_name="HA Switches")
        device_number = registry.allocate_number(DEVICE_TYPE_SWITCH)
        registry.add_device(
            AlpacaDevice(
                device_type=DEVICE_TYPE_SWITCH,
                device_number=device_number,
                device_name="HA Switches",
                unique_id="int_switch_container",
                handler=handler,
                is_external=False,
            )
        )

    # --- ObservingConditions ---
    oc_mapping: dict[str, str] = options.get(CONF_OBSERVING_CONDITIONS, {})
    if any(oc_mapping.values()):
        channels_oc = _build_oc_channels(hass, oc_mapping)
        handler_oc = create_oc_handler(
            channels_oc, device_name="HA ObservingConditions"
        )
        device_number_oc = registry.allocate_number(
            DEVICE_TYPE_OBSERVINGCONDITIONS
        )
        registry.add_device(
            AlpacaDevice(
                device_type=DEVICE_TYPE_OBSERVINGCONDITIONS,
                device_number=device_number_oc,
                device_name="HA ObservingConditions",
                unique_id="int_observingconditions",
                handler=handler_oc,
                is_external=False,
            )
        )

    # --- CoverCalibrator ---
    cal_onoff: str = options.get(CONF_CALIBRATOR_ONOFF_ENTITY, "")
    cal_brightness: str = options.get(CONF_CALIBRATOR_BRIGHTNESS_ENTITY, "")
    if cal_onoff or cal_brightness:
        channel_cal = _build_calibrator_channel(
            hass, cal_onoff, cal_brightness
        )
        handler_cal = create_covercalibrator_handler(
            channel_cal, device_name="HA CoverCalibrator"
        )
        device_number_cal = registry.allocate_number(
            DEVICE_TYPE_COVERCALIBRATOR
        )
        registry.add_device(
            AlpacaDevice(
                device_type=DEVICE_TYPE_COVERCALIBRATOR,
                device_number=device_number_cal,
                device_name="HA CoverCalibrator",
                unique_id="int_covercalibrator",
                handler=handler_cal,
                is_external=False,
            )
        )

    internal = len([d for d in registry.get_all_devices() if not d.is_external])
    external = len([d for d in registry.get_all_devices() if d.is_external])
    _LOGGER.info(
        "Internal devices rebuilt: %d total (%d internal, %d external)",
        internal + external,
        internal,
        external,
    )


# ---------------------------------------------------------------------------
# Switch channel factory
# ---------------------------------------------------------------------------


def _build_switch_channels(
    hass: HomeAssistant,
    entity_ids: list[str],
    switch_names: dict[str, str] | None = None,
) -> list[SwitchChannel]:
    """Create SwitchChannel instances for the given HA switch entity IDs."""
    channels: list[SwitchChannel] = []
    
    if switch_names is None:
        switch_names = {}

    for entity_id in entity_ids:

        async def _get_state(eid: str = entity_id) -> bool | None:
            state = hass.states.get(eid)
            if state is None:
                return None
            return state.state == "on"

        async def _set_state(
            target: bool, eid: str = entity_id
        ) -> None:
            service = "turn_on" if target else "turn_off"
            await hass.services.async_call(
                "switch", service, {"entity_id": eid}
            )

        # Determine the name to expose via Alpaca
        custom_name = switch_names.get(entity_id)
        if custom_name:
            export_name = custom_name
        else:
            # Fallback to HA friendly name, or just the entity_id
            state = hass.states.get(entity_id)
            if state and state.name:
                export_name = state.name
            else:
                export_name = entity_id

        channels.append(
            SwitchChannel(
                name=export_name,
                description=f"HA entity: {entity_id}",
                get_state=_get_state,
                set_state=_set_state,
            )
        )

    return channels


# ---------------------------------------------------------------------------
# ObservingConditions channel factory
# ---------------------------------------------------------------------------


def _build_oc_channels(
    hass: HomeAssistant,
    oc_mapping: dict[str, list[str]],
) -> dict[str, OCSensorChannel]:
    """Create OCSensorChannel instances with multi-entity fallback."""
    channels: dict[str, OCSensorChannel] = {}

    for prop_name, entity_ids in oc_mapping.items():
        if not entity_ids:
            continue

        async def _get_value(
            prop: str = prop_name, eids: list[str] = entity_ids
        ) -> float | None:
            for eid in eids:
                state = hass.states.get(eid)
                if state is None or state.state in (
                    "unavailable", "unknown",
                ):
                    continue
                try:
                    value = float(state.state)
                except (ValueError, TypeError):
                    continue
                return to_alpaca_unit(
                    prop, value, state.attributes.get("unit_of_measurement")
                )
            return None

        async def _get_seconds(eids: list[str] = entity_ids) -> float:
            for eid in eids:
                state = hass.states.get(eid)
                if state is None or state.state in (
                    "unavailable", "unknown",
                ):
                    continue
                if state.last_updated:
                    now = dt_util.utcnow()
                    return (now - state.last_updated).total_seconds()
            return 0.0

        desc_parts = ", ".join(entity_ids)
        channels[prop_name] = OCSensorChannel(
            property_name=prop_name,
            description=f"HA entities: {desc_parts}",
            get_value=_get_value,
            get_seconds_since_update=_get_seconds,
        )

    return channels


# ---------------------------------------------------------------------------
# CoverCalibrator channel factory
# ---------------------------------------------------------------------------


_CALIBRATOR_MAX_BRIGHTNESS = 255


def _build_calibrator_channel(
    hass: HomeAssistant,
    onoff_entity: str,
    brightness_entity: str,
) -> CalibratorChannel:
    """Create a CalibratorChannel from one or two HA entities.

    Supported combinations:
    - light only           → on/off + brightness from the light
    - switch only          → on/off only, brightness is binary (0 or max)
    - switch + number      → on/off from switch, brightness from number
    - number only          → on = value > 0, brightness from number
    - light + number       → on/off from light, brightness from number
    - switch + light       → on/off from switch, brightness from the light

    The brightness scale is 0-255 for lights and switches; for a number
    entity it is 0 up to the entity's ``max`` attribute.
    """
    # Determine the on/off entity domain
    onoff_domain = ""
    if onoff_entity:
        onoff_domain = onoff_entity.split(".", 1)[0]  # "light", "switch", etc.

    brightness_domain = ""
    if brightness_entity:
        brightness_domain = brightness_entity.split(".", 1)[0]

    # Determine if we have brightness control
    has_brightness = (
        brightness_entity  # explicit brightness entity (number/light)
        or onoff_domain == "light"  # light entities have brightness attribute
    )

    # A light that only provides brightness (distinct from the on/off entity)
    separate_light = bool(
        brightness_entity
        and brightness_domain == "light"
        and brightness_entity != onoff_entity
    )

    # --- get_max_brightness ---
    def _get_max_brightness() -> int:
        if brightness_entity and brightness_domain in ("number", "input_number"):
            state = hass.states.get(brightness_entity)
            if state is not None:
                try:
                    return max(1, int(float(state.attributes.get("max"))))
                except (ValueError, TypeError):
                    pass
        return _CALIBRATOR_MAX_BRIGHTNESS

    # --- get_is_on ---
    if onoff_entity:
        async def _get_is_on() -> bool | None:
            state = hass.states.get(onoff_entity)
            if state is None:
                return None
            return state.state == "on"
    else:
        # number-only: on = value > 0
        async def _get_is_on() -> bool | None:
            state = hass.states.get(brightness_entity)
            if state is None:
                return None
            try:
                return float(state.state) > 0
            except (ValueError, TypeError):
                return None

    # --- get_brightness ---
    if brightness_entity and brightness_domain in ("number", "input_number"):
        # Brightness from a number entity (value assumed 0–max)
        async def _get_brightness() -> int | None:
            state = hass.states.get(brightness_entity)
            if state is None:
                return None
            try:
                return int(float(state.state))
            except (ValueError, TypeError):
                return 0
    elif onoff_domain == "light" or brightness_domain == "light":
        # Brightness from a light entity's brightness attribute
        light_eid = brightness_entity or onoff_entity

        async def _get_brightness() -> int | None:
            state = hass.states.get(light_eid)
            if state is None:
                return None
            if state.state != "on":
                return 0
            raw = state.attributes.get("brightness", 0)
            try:
                return int(raw) if raw is not None else 0
            except (ValueError, TypeError):
                return 0
    else:
        # switch-only: binary brightness
        async def _get_brightness() -> int | None:
            state = hass.states.get(onoff_entity)
            if state is None:
                return None
            return _CALIBRATOR_MAX_BRIGHTNESS if state.state == "on" else 0

    # --- turn_on ---
    async def _turn_on(brightness: int) -> None:
        # Set brightness first if separate entity
        if brightness_entity and brightness_domain in ("number", "input_number"):
            await hass.services.async_call(
                brightness_domain,
                "set_value",
                {"entity_id": brightness_entity, "value": brightness},
            )

        # A separate brightness light always receives the brightness
        if separate_light:
            await hass.services.async_call(
                "light",
                "turn_on",
                {"entity_id": brightness_entity, "brightness": brightness},
            )

        # Turn on the on/off entity
        if onoff_entity and onoff_domain == "light":
            service_data: dict[str, Any] = {"entity_id": onoff_entity}
            # Only pass brightness if this light itself controls it
            if not brightness_entity or brightness_entity == onoff_entity:
                service_data["brightness"] = brightness
            await hass.services.async_call("light", "turn_on", service_data)
        elif onoff_entity and onoff_domain == "switch":
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": onoff_entity}
            )
        elif not onoff_entity and brightness_domain in (
            "number", "input_number"
        ):
            # number-only: setting value > 0 is "turning on"
            pass  # already set above

    # --- turn_off ---
    async def _turn_off() -> None:
        if brightness_entity and brightness_domain in ("number", "input_number"):
            await hass.services.async_call(
                brightness_domain,
                "set_value",
                {"entity_id": brightness_entity, "value": 0},
            )
        if separate_light:
            await hass.services.async_call(
                "light", "turn_off", {"entity_id": brightness_entity}
            )
        if onoff_entity and onoff_domain == "light":
            await hass.services.async_call(
                "light", "turn_off", {"entity_id": onoff_entity}
            )
        elif onoff_entity and onoff_domain == "switch":
            await hass.services.async_call(
                "switch", "turn_off", {"entity_id": onoff_entity}
            )

    # Build description
    parts = []
    if onoff_entity:
        parts.append(f"on/off: {onoff_entity}")
    if brightness_entity:
        parts.append(f"brightness: {brightness_entity}")
    description = f"HA CoverCalibrator ({', '.join(parts)})"
    name = onoff_entity or brightness_entity

    return CalibratorChannel(
        name=name,
        description=description,
        get_max_brightness=_get_max_brightness,
        get_brightness=_get_brightness,
        get_is_on=_get_is_on,
        turn_on=_turn_on,
        turn_off=_turn_off,
    )
