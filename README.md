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
  - **Switch**: Map multiple HA `switch` entities to an Alpaca Switch device.
  - **ObservingConditions**: Map HA `sensor` entities to astronomical metrics (Temperature, Humidity, Pressure, Wind, etc.). Supports **Multi-Entity Fallback**: assign multiple sensors to one metric; the first available/valid sensor will be used. Values are converted to ASCOM units (°C, hPa, m/s, mm/h) based on each entity's `unit_of_measurement`.
  - **CoverCalibrator**: Map HA `light`, `switch`, or `number` entities to control a flat panel/calibrator. Supports flexible on/off and brightness control mapping. With a `number` entity, `MaxBrightness` is taken from the entity's `max` attribute; lights and switches use 0–255.
- **Standalone Alpaca Logic**: The core Alpaca protocol implementation is separated from the Home Assistant bridge, making it robust and modular.

## Installation

1. Copy the `custom_components/ascom_alpaca_server` folder to your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Go to **Settings -> Devices & Services -> Add Integration** and search for **ASCOM Alpaca Server**.

## Configuration

The integration is configured entirely through the Home Assistant UI. Use the **Options** menu of the integration to:
- Set the Alpaca Listen Port (default 5555).
- Enable/Disable UDP Discovery.
- Map HA entities to Alpaca device types.

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

The `handler` is an `async` function `(action: str, params: dict) -> dict`. It returns a dict with the Alpaca `Value` and, in case of an error, `ErrorNumber`, `ErrorMessage` and optionally `HttpStatus`. The returned `unregister()` callback removes the device again.

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
