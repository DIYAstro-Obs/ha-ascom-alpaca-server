"""Protocol-level constants for the ASCOM Alpaca library."""

from __future__ import annotations

# --- Alpaca Device Types ---
DEVICE_TYPE_SWITCH = "switch"
DEVICE_TYPE_SAFETYMONITOR = "safetymonitor"
DEVICE_TYPE_OBSERVINGCONDITIONS = "observingconditions"
DEVICE_TYPE_COVERCALIBRATOR = "covercalibrator"
DEVICE_TYPE_DOME = "dome"

# --- ObservingConditions property names ---
# Maps Alpaca property names (lowercase) to human-readable labels.
OC_PROPERTIES: dict[str, str] = {
    "temperature": "Temperature",
    "humidity": "Humidity",
    "pressure": "Pressure",
    "dewpoint": "Dew Point",
    "windspeed": "Wind Speed",
    "windgust": "Wind Gust",
    "winddirection": "Wind Direction",
    "cloudcover": "Cloud Cover",
    "skybrightness": "Sky Brightness",
    "skyquality": "Sky Quality",
    "skytemperature": "Sky Temperature",
    "rainrate": "Rain Rate",
    "starfwhm": "Star FWHM",
}

# --- Commands ---
# Actions that change something (move the roof, switch, trigger a refresh): the server accepts them
# only as PUT. A GET or POST can be sent by any web page the browser of a LAN computer opens, a PUT cannot.
COMMAND_ACTIONS = frozenset(
    {
        # Dome
        "openshutter",
        "closeshutter",
        "abortslew",
        "findhome",
        "park",
        "setpark",
        "slewtoaltitude",
        "slewtoazimuth",
        "synctoazimuth",
        # Switch
        "setswitch",
        "setswitchvalue",
        "setswitchname",
        # CoverCalibrator
        "calibratoron",
        "calibratoroff",
        "opencover",
        "closecover",
        "haltcover",
        # ObservingConditions
        "refresh",
        # every device type: a custom action of the device
        "action",
    }
)

# --- Server Info ---
SERVER_NAME = "ASCOM Alpaca Server"
SERVER_MANUFACTURER = "ASCOM Alpaca Server"
SERVER_VERSION = "0.11.0"

# --- Networking ---
ALPACA_DISCOVERY_PORT = 32227
