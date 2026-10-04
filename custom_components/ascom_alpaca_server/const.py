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

# --- Data Keys ---
DATA_REGISTRY = "registry"
DATA_SERVER = "server"
