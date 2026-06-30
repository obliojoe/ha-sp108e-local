# Release Audit

## Repository

- Repo: `ha-sp108e-local`
- Domain: `sp108e_local`
- HACS-ready status: Local structure ready; formal HACS-ready pending GitHub Actions HACS/Hassfest run after publication

## Files found/copied

- `custom_components/sp108e_local/__init__.py`
- `custom_components/sp108e_local/color_order.py`
- `custom_components/sp108e_local/config_flow.py`
- `custom_components/sp108e_local/const.py`
- `custom_components/sp108e_local/coordinator.py`
- `custom_components/sp108e_local/diagnostics.py`
- `custom_components/sp108e_local/effects.py`
- `custom_components/sp108e_local/light.py`
- `custom_components/sp108e_local/manifest.json`
- `custom_components/sp108e_local/number.py`
- `custom_components/sp108e_local/protocol.py`
- `custom_components/sp108e_local/strings.json`
- `custom_components/sp108e_local/translations/en.json`
- `custom_components/sp108e_local/translations/it.json`

## Implemented functions

- Controls SP108E LED controllers over the local TCP protocol.
- Exposes a Home Assistant light entity and effect-speed number entity.
- Implements protocol helpers for state, color, brightness, effects and RGB ordering.

## Home Assistant platforms

light, number, diagnostics

## Python dependencies

- None

## Config flow/options flow

present; host, port, timeout, RGB order and debounce are configurable

## Privacy risks

The original real default host was replaced with 192.0.2.10 placeholder.

Automated scan still requires human review for generic words such as `token`, `password`, `sensor.` and protocol examples.

## License/attribution risks

Original Python implementation; no proprietary assets included.

## Testable without hardware

Static JSON checks, Python syntax compilation and included protocol tests.

## Testable with hardware

Requires an SP108E controller at the configured host.

## Manual review notes

- GitHub placeholders have been replaced with `zampix1`.
- Run HACS validation and Hassfest in GitHub Actions after the repository is created.
- Confirm that README hardware claims match devices actually tested by the maintainer.

## Local verification

- Ruff format/check: passed locally.
- Pytest/static tests: passed locally.
- HACS validation: workflow added, not executed locally.
- Hassfest: workflow added, not executed locally.
- Secret scanners: gitleaks/trufflehog/detect-secrets not available in this environment.

