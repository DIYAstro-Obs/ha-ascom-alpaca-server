"""Constants for the ASCOM Alpaca Server integration.

Only Home Assistant–specific configuration and data keys live here.
Protocol-level constants (device types, OC properties, server info) are
in the ``alpaca.const`` module.
"""

DOMAIN = "ascom_alpaca_server"
INTEGRATION_NAME = "ASCOM Alpaca Server"

# --- External API key (used by client integrations like ASCOM Alpaca Safety) ---
ALPACA_SERVER_API_KEY = "ascom_alpaca_server_api"

# --- Networking (HA config keys) ---
CONF_ALPACA_PORT = "alpaca_port"
DEFAULT_ALPACA_PORT = 5555
CONF_ALPACA_DISCOVERY = "alpaca_discovery"
DEFAULT_ALPACA_DISCOVERY = True

# --- Configuration Keys ---
CONF_SWITCH_ENTITIES = "switch_entities"
CONF_SWITCH_NAMES = "switch_names"
CONF_OBSERVING_CONDITIONS = "observing_conditions"
CONF_CALIBRATOR_ONOFF_ENTITY = "calibrator_onoff_entity"
CONF_CALIBRATOR_BRIGHTNESS_ENTITY = "calibrator_brightness_entity"
CONF_DOME_COVER_ENTITY = "dome_cover_entity"

# Entities that can be exposed as an Alpaca switch: each has turn_on and turn_off in its own domain
SWITCH_DOMAINS = ("switch", "input_boolean", "light", "fan")

# Entities that can provide ObservingConditions values: a sensor per value, or a weather entity
# with several values as attributes
OC_DOMAINS = ("sensor", "weather")

# --- Data Keys ---
DATA_REGISTRY = "registry"
DATA_SERVER = "server"
DATA_LISTEN = "listen"  # (port, discovery) the running server was started with
DATA_DERIVED = "derived"  # DerivedChannels of the current mapping (read by the sensors)
DATA_FLAGS = "derived_flags"  # which sensors were created at setup: a change needs a reload

PLATFORMS = ["sensor"]
