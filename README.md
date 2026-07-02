# SP108E Local

Home Assistant custom integration for local control of SP108E LED controllers.

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zampix1&repository=ha-sp108e-local&category=integration)

This project is not affiliated with, endorsed by or supported by the controller manufacturer.

## What works

- Tested with an SP108E LED controller on a local network.
- Installable as a HACS custom repository or by manual copy.
- Uses the local TCP protocol; no vendor cloud account is required.
- Exposes a Home Assistant `light` entity and an effect speed `number`.
- Includes protocol helpers for state, color, brightness, effects and RGB ordering.

## What it does

- Controls SP108E LED controllers over the local TCP protocol.
- Exposes a Home Assistant light entity and effect-speed number entity.
- Implements protocol helpers for state, color, brightness, effects and RGB ordering.

## Tested hardware

SP108E LED controller on a local network.

## Known limits

Device protocol is local TCP; no discovery is included.

## Installation With HACS

1. In HACS, add this repository as a custom repository.
2. Select category `Integration`.
3. Install the integration.
4. Restart Home Assistant.
5. Add the integration from **Settings > Devices & services**.

Repository URL:

```text
https://github.com/zampix1/ha-sp108e-local
```

## Manual Installation

Copy `custom_components/sp108e_local` into your Home Assistant `custom_components/` directory and restart Home Assistant.

## Configuration

Configuration is UI-based through Home Assistant config flow.

Use placeholders in documentation and bug reports:

- Host/IP: `YOUR_DEVICE_HOST` or `192.0.2.10`
- BLE address: `AA:BB:CC:DD:EE:FF`
- Serial: `YOUR_SERIAL`
- Entity IDs: `sensor.example_temperature`

## Entities

Platforms: light, number, diagnostics.

The exact entity set depends on hardware capabilities and the selected options.

## Services

No custom HA services.

## Troubleshooting

- Confirm the device or gateway is reachable from the Home Assistant host.
- Increase timeout or polling interval if the device is slow or BLE/network quality is poor.
- Check Home Assistant logs, but do not paste real tokens, serials, MAC addresses, hostnames or entity IDs in public issues.

## Privacy And Security

The original real default host was replaced with 192.0.2.10 placeholder.

Do not publish real LAN IPs, hostnames, MAC addresses, serial numbers, SSIDs, tokens, cloud credentials, Home Assistant entity IDs, coordinates or personal automation details in issues.

## Reverse Engineering Note

Original Python implementation; no proprietary assets included. This project is not affiliated with, endorsed by or supported by the manufacturer.

## Alternatives

Before using a custom integration, check whether Home Assistant core or another maintained integration already supports your device. For LED controllers, WLED or UniLED may be better choices when compatible firmware or protocol support exists.

## Status

Public HACS custom repository release. Tester feedback is welcome, especially for hardware variants and effect behavior.

