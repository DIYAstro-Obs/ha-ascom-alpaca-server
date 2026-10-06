"""Config flow and Options flow for ASCOM Alpaca Server."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .alpaca.const import OC_PROPERTIES
from .const import (
    CONF_ALPACA_DISCOVERY,
    CONF_ALPACA_PORT,
    CONF_CALIBRATOR_BRIGHTNESS_ENTITY,
    CONF_CALIBRATOR_ONOFF_ENTITY,
    CONF_DOME_COVER_ENTITY,
    CONF_OBSERVING_CONDITIONS,
    CONF_SWITCH_ENTITIES,
    CONF_SWITCH_NAMES,
    DEFAULT_ALPACA_DISCOVERY,
    DEFAULT_ALPACA_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class AlpacaServerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle initial config flow for ASCOM Alpaca Server."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle initial setup."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="ASCOM Alpaca Server",
                data={
                    CONF_ALPACA_PORT: int(
                        user_input.get(CONF_ALPACA_PORT, DEFAULT_ALPACA_PORT)
                    ),
                    CONF_ALPACA_DISCOVERY: user_input.get(
                        CONF_ALPACA_DISCOVERY, DEFAULT_ALPACA_DISCOVERY
                    ),
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ALPACA_PORT, default=DEFAULT_ALPACA_PORT
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1024,
                            max=65535,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_ALPACA_DISCOVERY, default=DEFAULT_ALPACA_DISCOVERY
                    ): selector.BooleanSelector(),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> AlpacaServerOptionsFlow:
        return AlpacaServerOptionsFlow(config_entry)


class AlpacaServerOptionsFlow(config_entries.OptionsFlow):
    """Handle options for entity mapping."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    # ---- Main Menu ----

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show options menu."""
        if user_input is not None:
            choice = user_input.get("menu")
            if choice == "general_settings":
                return await self.async_step_general_settings()
            if choice == "map_switches":
                return await self.async_step_map_switches()
            if choice == "map_calibrator":
                return await self.async_step_map_calibrator()
            if choice == "map_dome":
                return await self.async_step_map_dome()
            if choice == "map_observing":
                return await self.async_step_map_observing()

        switch_count = len(
            self._config_entry.options.get(CONF_SWITCH_ENTITIES, [])
        )
        oc_count = sum(
            1
            for v in self._config_entry.options.get(
                CONF_OBSERVING_CONDITIONS, {}
            ).values()
            if v  # works for both str and list
        )
        cal_onoff = self._config_entry.options.get(
            CONF_CALIBRATOR_ONOFF_ENTITY, ""
        )
        cal_brightness = self._config_entry.options.get(
            CONF_CALIBRATOR_BRIGHTNESS_ENTITY, ""
        )
        cal_configured = cal_onoff or cal_brightness
        cal_summary = ""
        if cal_configured:
            parts = []
            if cal_onoff:
                parts.append(cal_onoff)
            if cal_brightness:
                parts.append(cal_brightness)
            cal_summary = "✅ " + ", ".join(parts)
        else:
            cal_summary = "not configured"

        dome_cover = self._config_entry.options.get(CONF_DOME_COVER_ENTITY, "")
        dome_summary = f"✅ {dome_cover}" if dome_cover else "not configured"

        menu_options = {
            "general_settings": "⚙️ General settings (Port, Discovery)",
            "map_switches": f"🔌 Map Switch devices ({switch_count} mapped)",
            "map_calibrator": (
                f"💡 Map CoverCalibrator (Flat Panel) "
                f"({cal_summary})"
            ),
            "map_dome": f"🏠 Map Dome (roll-off roof) ({dome_summary})",
            "map_observing": f"🌡️ Map ObservingConditions sensors ({oc_count} mapped)",
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("menu"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=k, label=v)
                                for k, v in menu_options.items()
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    # ---- General Settings ----

    async def async_step_general_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit port and discovery."""
        if user_input is not None:
            options = dict(self._config_entry.options)
            options[CONF_ALPACA_PORT] = int(
                user_input.get(CONF_ALPACA_PORT, DEFAULT_ALPACA_PORT)
            )
            options[CONF_ALPACA_DISCOVERY] = user_input.get(
                CONF_ALPACA_DISCOVERY, DEFAULT_ALPACA_DISCOVERY
            )
            return self.async_create_entry(title="", data=options)

        current_port = self._config_entry.options.get(
            CONF_ALPACA_PORT,
            self._config_entry.data.get(CONF_ALPACA_PORT, DEFAULT_ALPACA_PORT),
        )
        current_discovery = self._config_entry.options.get(
            CONF_ALPACA_DISCOVERY,
            self._config_entry.data.get(
                CONF_ALPACA_DISCOVERY, DEFAULT_ALPACA_DISCOVERY
            ),
        )

        return self.async_show_form(
            step_id="general_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ALPACA_PORT, default=int(current_port)
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1024,
                            max=65535,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_ALPACA_DISCOVERY, default=current_discovery
                    ): selector.BooleanSelector(),
                }
            ),
        )

    # ---- Map Switches ----

    async def async_step_map_switches(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select switch entities to expose as Alpaca Switch devices."""
        if user_input is not None:
            self._temp_switch_entities = user_input.get(CONF_SWITCH_ENTITIES, [])
            if not self._temp_switch_entities:
                # If no switches selected, clean up names and save directly
                options = dict(self._config_entry.options)
                options[CONF_SWITCH_ENTITIES] = []
                options[CONF_SWITCH_NAMES] = {}
                return self.async_create_entry(title="", data=options)

            # Move to the name configuration step
            return await self.async_step_map_switch_names()

        current = self._config_entry.options.get(CONF_SWITCH_ENTITIES, [])

        return self.async_show_form(
            step_id="map_switches",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SWITCH_ENTITIES, default=current
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="switch",
                            multiple=True,
                        )
                    ),
                }
            ),
        )

    async def async_step_map_switch_names(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure custom names for selected switch entities."""
        if user_input is not None:
            options = dict(self._config_entry.options)
            options[CONF_SWITCH_ENTITIES] = getattr(
                self, "_temp_switch_entities", []
            )
            options[CONF_SWITCH_NAMES] = user_input
            return self.async_create_entry(title="", data=options)

        switch_entities = getattr(self, "_temp_switch_entities", [])
        if not switch_entities:
            # Should not happen if coming from map_switches normally,
            # but safeguard just in case.
            return await self.async_step_map_switches()

        current_names = self._config_entry.options.get(CONF_SWITCH_NAMES, {})
        schema_dict: dict[Any, Any] = {}

        for entity_id in switch_entities:
            # Determine default string
            default_val = current_names.get(entity_id)
            if not default_val:
                # Try to get the HA friendly name as fallback
                state = self.hass.states.get(entity_id)
                if state and state.name:
                    default_val = state.name
                else:
                    default_val = entity_id

            schema_dict[
                vol.Required(entity_id, default=default_val)
            ] = selector.TextSelector()

        return self.async_show_form(
            step_id="map_switch_names",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "count": str(len(switch_entities)),
            },
        )

    # ---- Map CoverCalibrator ----

    async def async_step_map_calibrator(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select entities for the Alpaca CoverCalibrator."""
        if user_input is not None:
            options = dict(self._config_entry.options)
            options[CONF_CALIBRATOR_ONOFF_ENTITY] = user_input.get(
                CONF_CALIBRATOR_ONOFF_ENTITY, ""
            )
            options[CONF_CALIBRATOR_BRIGHTNESS_ENTITY] = user_input.get(
                CONF_CALIBRATOR_BRIGHTNESS_ENTITY, ""
            )
            return self.async_create_entry(title="", data=options)

        current_onoff = self._config_entry.options.get(
            CONF_CALIBRATOR_ONOFF_ENTITY, ""
        )
        current_brightness = self._config_entry.options.get(
            CONF_CALIBRATOR_BRIGHTNESS_ENTITY, ""
        )

        # Build schema — only set default when there's a stored entity
        onoff_kwargs: dict[str, Any] = {}
        if current_onoff:
            onoff_kwargs["default"] = current_onoff
        brightness_kwargs: dict[str, Any] = {}
        if current_brightness:
            brightness_kwargs["default"] = current_brightness

        return self.async_show_form(
            step_id="map_calibrator",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CALIBRATOR_ONOFF_ENTITY,
                        **onoff_kwargs,
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["light", "switch"],
                        )
                    ),
                    vol.Optional(
                        CONF_CALIBRATOR_BRIGHTNESS_ENTITY,
                        **brightness_kwargs,
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["light", "number", "input_number"],
                        )
                    ),
                }
            ),
        )

    # ---- Map Dome ----

    async def async_step_map_dome(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select the cover entity of the roll-off roof (Alpaca Dome)."""
        if user_input is not None:
            options = dict(self._config_entry.options)
            options[CONF_DOME_COVER_ENTITY] = user_input.get(
                CONF_DOME_COVER_ENTITY, ""
            )
            return self.async_create_entry(title="", data=options)

        current = self._config_entry.options.get(CONF_DOME_COVER_ENTITY, "")

        # Only set a default when there is a stored entity (an empty field removes the Dome)
        cover_kwargs: dict[str, Any] = {}
        if current:
            cover_kwargs["default"] = current

        return self.async_show_form(
            step_id="map_dome",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DOME_COVER_ENTITY, **cover_kwargs
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="cover"),
                    ),
                }
            ),
        )

    # ---- Map ObservingConditions ----

    async def async_step_map_observing(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Map sensor entities to ObservingConditions properties."""
        if user_input is not None:
            options = dict(self._config_entry.options)
            oc_mapping: dict[str, list[str]] = {}
            for prop_key in OC_PROPERTIES:
                oc_mapping[prop_key] = user_input.get(prop_key, [])
            options[CONF_OBSERVING_CONDITIONS] = oc_mapping
            return self.async_create_entry(title="", data=options)

        current_oc = self._config_entry.options.get(
            CONF_OBSERVING_CONDITIONS, {}
        )

        schema_dict: dict[Any, Any] = {}
        for prop_key, prop_label in OC_PROPERTIES.items():
            current_val = current_oc.get(prop_key, [])
            # Only set default when there are stored entities
            opt_kwargs: dict[str, Any] = {}
            if current_val:
                opt_kwargs["default"] = current_val
            schema_dict[
                vol.Optional(prop_key, **opt_kwargs)
            ] = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    multiple=True,
                )
            )

        return self.async_show_form(
            step_id="map_observing",
            data_schema=vol.Schema(schema_dict),
        )
