# ASCOM Alpaca Server for Home Assistant

**ASCOM Alpaca Server** is a Home Assistant integration that acts as an ASCOM Alpaca server. It allows astronomy software (such as N.I.N.A., Sequence Generator Pro, or Stellarium) to interact with Home Assistant entities as if they were native ASCOM devices.

![Alpaca Server Logo](custom_components/ascom_alpaca_server/brand/icon@2x.png)

> [!CAUTION]
> **AS-IS / EXPERIMENTAL**
> This project is provided "as-is" without any warranty. It has not yet been tested in a real-life observatory environment. Use it at your own risk.
>
> The project is **under active development**. Testing is very welcome! Please report any bugs by opening an [issue](https://github.com/DIYAstro-Obs/ha-ascom-alpaca-server/issues). Contributions are also highly appreciated.

## Features

- **ASCOM Alpaca Server**: Implements the Alpaca protocol to expose HA entities via network.
- **Discovery**: Supports Alpaca UDP discovery (optional/configurable).
- **Supported Device Types**:
  - **Switch**: Map multiple HA `switch`, `input_boolean`, `light` or `fan` entities to an Alpaca Switch device. Each switch needs its own, unique name.
  - **ObservingConditions**: Map HA `sensor` entities to astronomical metrics (Temperature, Humidity, Pressure, Wind, etc.). Supports **Multi-Entity Fallback**: assign multiple sensors to one metric; the first available/valid sensor will be used. Values are converted to ASCOM units (°C, hPa, m/s, mm/h) based on each entity's `unit_of_measurement`.
  - **CoverCalibrator**: Map HA `light`, `switch`, or `number` entities to control a flat panel/calibrator. Supports flexible on/off and brightness control mapping. With a `number` entity, `MaxBrightness` is taken from the entity's `max` attribute; lights and switches use 0–255.
  - **Dome** (roll-off roof): Map one HA `cover` entity to an Alpaca Dome that only has a shutter (`OpenShutter`, `CloseShutter`, `AbortSlew`, `ShutterStatus`; no azimuth, altitude, slaving or park). ASCOM has no "observatory" device type: a roll-off roof is a Dome. See "Dome (roll-off roof)" below.
- **Standalone Alpaca Logic**: The core Alpaca protocol implementation is separated from the Home Assistant bridge, making it robust and modular.

## Installation

1. Copy the `custom_components/ascom_alpaca_server` folder to your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Go to **Settings -> Devices & Services -> Add Integration** and search for **ASCOM Alpaca Server**.

## Configuration

The integration is configured entirely through the Home Assistant UI. Use the **Options** menu of the integration to:
- Set the Alpaca Listen Port (default 5555). The dialog refuses a port that another program uses; if the port is taken when Home Assistant starts, the integration says so and tries again later.
- Enable/Disable UDP Discovery.
- Map HA entities to Alpaca device types.

## Dome (roll-off roof)

In the options menu choose **Map Dome (roll-off roof)** and select the `cover` entity of the roof, for example the `Observatory Roof` cover of an [ESPHome RoRo controller](https://github.com/DIYAstro-Obs/esphome-roro). Astronomy software then sees a Dome with a shutter. `OpenShutter`, `CloseShutter` and `AbortSlew` call `cover.open_cover`, `cover.close_cover` and `cover.stop_cover` and return at once; the client polls `ShutterStatus` until the roof stands.

`ShutterStatus` follows the cover:

| Cover | ShutterStatus |
|-------|---------------|
| `opening` / `closing` | 2 Opening / 3 Closing |
| position 100 % | 0 Open |
| position 0 % | 1 Closed |
| standing halfway (idle, position between 0 and 100) | 4 Error |
| `unavailable`, `unknown`, entity missing | 4 Error |
| cover without a position: `open` / `closed` | 0 Open / 1 Closed |

The position decides, not the state text: Home Assistant reports a cover that stands halfway as `open`, but a roof that is neither on its open nor on its closed limit must not be reported as open. The Dome has no park (`CanPark` is false) and is not slaved to a mount.

A command that the cover accepts but does not carry out (for example a locked E-STOP in the firmware) is not an Alpaca error, the shutter status simply stays as it is. If Home Assistant itself refuses the command, the client gets an error with the reason. For safety decisions use a SafetyMonitor ([ASCOM Alpaca Safety](https://github.com/DIYAstro-Obs/ha-ascom-alpaca-safety)) as well.

## Behaviour of the Alpaca API

- **Commands need PUT.** `OpenShutter`, `CloseShutter`, `AbortSlew`, `SetSwitch`, `SetSwitchValue`, `CalibratorOn`, `CalibratorOff` and the other commands that change something are refused with HTTP 400 when they come as GET or POST. Astronomy software uses PUT; a link or a form on a web page opened in the browser of a computer in your network cannot trigger them. Opening such an address in the browser address bar no longer moves the roof.
- **Commands wait for Home Assistant.** `OpenShutter`, `SetSwitch`, `CalibratorOn` and the others return when the Home Assistant service has finished (after 10 seconds at the latest). If the service fails, the client gets an ASCOM error (`0x500`) with the reason instead of a success.
- **An entity without a value is not "off".** A switch whose entity is `unavailable` or `unknown` answers `GetSwitch` with an error (`0x500`), not with `false`. A flat panel in that state reports `CalibratorState` Unknown and no brightness. An ObservingConditions sensor without a value answers with `ValueNotSet` (`0x402`), so clients show "no value" instead of hiding the property as "not implemented".
- **`TimeSinceLastUpdate`** is the time since the sensor last reported (not since its value last changed). It is an error (`ValueNotSet`) when no mapped sensor has a value.
- The names of the switches are set in Home Assistant, `SetSwitchName` answers "not implemented".

## For Integration Developers

Other Home Assistant integrations can publish their own devices through ASCOM Alpaca Server. While the server is running, it exposes a registration function under `hass.data["ascom_alpaca_server_api"]`:

```python
api = hass.data.get("ascom_alpaca_server_api")
if api is not None and "async_register_device" in api:
    unregister = await api["async_register_device"](
        device_type="SafetyMonitor",
        device_name="My Device",
        handler=handle_alpaca_request,
    )
```

The `handler` is an `async` function `(action: str, params: dict) -> dict`. It returns a dict with the Alpaca `Value` and, in case of an error, `ErrorNumber` and `ErrorMessage`. The returned `unregister()` callback removes the device again.

What the server does for every device, so that a handler does not have to:

- **`Connected`** is kept per client (`ClientID`) by the server and never reaches the handler. A GET tells whether the client of the request has connected, a PUT connects or disconnects it, so a second client that disconnects does not disconnect the first one. Requests without a `ClientID` count as client 0. The server does not refuse other requests of a client that has not connected.
- **Registering again**: a device that registers under the same type and name as an earlier one replaces it and keeps its number.
- **HTTP status**: a request that was understood gets **200**; an exception of the device (not implemented, invalid value, ...) is the `ErrorNumber` in the JSON body, which the client raises as the matching ASCOM exception. A handler that did not understand the request (unknown action, missing or malformed parameter) returns `"HttpStatus": 400`: the server answers 400 with the `ErrorMessage` as plain text. An exception in the handler is answered with 500 and a text. A request for a device that does not exist is 400.

[ASCOM Alpaca Safety](https://github.com/DIYAstro-Obs/ha-ascom-alpaca-safety) uses this API to expose its `SafetyMonitor`.

## Development

The project is structured with a strict separation between:
- `alpaca/`: Standalone Alpaca protocol implementation (handlers, server, discovery).
- `ha_bridge.py`: The bridge layer connecting Home Assistant's state engine and services to the Alpaca logic.
- `config_flow.py`: UI configuration and entity mapping logic.

Run the unit tests with `python -m pytest`. Only `pytest` is required; Home Assistant is stubbed (see `tests/ha_stubs.py`).

## Development Deployment

`deploy.ps1` copies the integration to `/config/custom_components/` on your Home Assistant via SCP and restarts Home Assistant Core. Copy `deployconf` to `deployconf.secrets` (ignored by git) and set:

| Key | Purpose |
|-----|---------|
| `SSH_URL` | Host or `host:port` of the SSH add-on (required, port defaults to 22) |
| `SSH_USER` | SSH user (default `root`) |
| `SSH_PW` | Optional SSH password. Stored in plain text, so use it only for test systems. Leave empty to be asked on every deploy. |

`HA_URL` and `HA_TOKEN` may stay in the file, but `deploy.ps1` does not use them.

Run `.\deploy.ps1 -DryRun` first: it prints the target (`user@host:port`), the auth mode and the planned steps without connecting.
