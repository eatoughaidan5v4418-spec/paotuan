# YAML runtime compatibility

Date: 2026-06-02

## Context

The API-only hardening round exposed a clean-runtime blocker: core CLI paths
used by the GM runtime imported external `PyYAML` directly. The bundled Python
environment did not include that dependency, so `run_turn.py` and
`zone_validator.py` could fail before the project could generate a turn packet
or validate zones.

Before choosing the fix, I checked existing YAML/PyYAML usage patterns and kept
`safe_load` as the public behavior: use PyYAML when it exists, fall back only for
the project-local YAML subset needed by supported campaigns.

## Changes

- Added `tools/yaml_compat.py`.
  - Prefers external PyYAML when available.
  - Falls back to a small stdlib parser for project-local YAML.
  - Supports mappings, lists, booleans, numbers, nulls, inline lists, BOM input,
    simple block scalars, and plain scalar continuation used by current campaign
    files.
- Updated `tools/run_turn.py` and `tools/zone_validator.py` to import
  `yaml_compat` instead of hard-importing `yaml`.
- Added architecture hardening coverage for:
  - CLI tools running without external PyYAML.
  - All official `campaign/` and `xianxia_campaign/` YAML files parsing under
    `python -S`, which skips site packages.
- Updated README, architecture, final report, and test coverage docs to clarify:
  - Core YAML/CLI paths no longer require PyYAML.
  - Full pytest still needs `pytest` installed.

## Verification

```powershell
python -m unittest tests.test_architecture_hardening
# Ran 32 tests: OK

python -m unittest tests.test_web_api
# Ran 25 tests: OK

python validate_project.py
# [OK] All checks passed

python validate_project.py --root xianxia_campaign
# [OK] All checks passed

python -S -c "<scan official campaign YAML through tools.yaml_compat>"
# parsed 28 yaml files
```

## Remaining limits

- The fallback parser is intentionally not a full YAML implementation.
- PyYAML remains preferred when installed for full YAML compatibility.
- Full pytest was not run because the bundled Python environment still lacks
  `pytest`.
