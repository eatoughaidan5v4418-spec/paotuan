# 2026-06-02 API-only hardening

## Context

User objective: iterate the project until directly usable, upgrade frontend/backend, run tests, use agents, push to Git, and stop building mock-side behavior. GM protocol requirements still apply for memory isolation, visibility, world clocks, and hidden/player-visible state separation.

Before naming fixes, related concepts were checked online: Event Sourcing, Command Query Separation, and game-loop elapsed-time update patterns. The local design direction follows those terms: state changes happen through committed events/patches, normalization is side-effect free, and elapsed player time advances world clocks through the runner commit path.

## Changes made

- `tools/play_game.py`
  - Made `normalize_patch()` side-effect free for campaign state files.
  - Moved effect point initialization into `apply_state_patch()` where actual writes belong.
  - Added `commit_world_clock_preview()` so API runner world-clock commits preserve `current_turn` and `recent_updates`.
  - Removed public/core `__mock__` branches from `call_chat_api()` and `run_worldgen()`.
  - Removed CLI `--mock` handling.
- `tools/web_api.py`
  - Public service helpers now reject `mock=True`.
  - API status reports `api_unconfigured` when no key is configured.
- `tools/web_game.py`
  - Removed server-wide mock state, request-body mock forwarding, `/api/config.mock`, and `--mock`.
- `tests/test_architecture_hardening.py`
  - Added regression coverage for side-effect-free `normalize_patch()`.
  - Added API runner world-clock commit coverage.
- `tests/test_web_api.py`
  - Added public mock rejection and API status tests.
  - Migrated previous public mock tests to private API-call stubs.
- Docs
  - Removed mock CLI/browser instructions from `README.md` and `WEB_UI.md`.
- Frontend
  - Removed the visible Mock toggle from the browser UI.
  - Removed Mock labels and `mock` fields from turn/worldgen request payloads.
  - Kept the UI API-only with explicit API key status text.
  - Updated release/test docs to distinguish verified results from dependency-limited full pytest.

## Verification run in this iteration

- Web API module: 25 tests passed through `unittest` with a local YAML import shim.
- Architecture hardening module: 26 tests passed; 4 YAML/CLI tests failed because the bundled Python lacks `PyYAML`.
- `validate_project.py`: passed for the default campaign.
- `validate_project.py --root xianxia_campaign`: passed.
- Full `pytest` was not available in the bundled Python environment (`No module named pytest`), and dependency installation was not approved in this turn.

## Agents used

- Docs cleanup worker updated stale `VULNERABILITY_AUDIT.md` test-count text.
- API-only migration explorer audited all mock-mode public entry points and test couplings.

## Frontend status

Frontend skills were loaded for UI work. Proposed API-only UI direction:

- Remove the visible Mock toggle.
- Remove all Mock labels and mock request payload fields.
- Show API model/key state in the top/status area.
- Keep turn/new-world controls visible, with clear API-key-required errors if unconfigured.

Implemented in this round to satisfy the explicit API-only requirement before commit. Further visual redesign should still go through the frontend skill/design approval flow.

## Next handoff

1. Re-run full pytest in an environment with `pytest` and `PyYAML`.
2. Decide whether to add a project-local dependency bootstrap or YAML fallback in a later iteration.
3. Run browser/Playwright visual checks for the API-only UI.
4. Continue frontend redesign through the required skill/design workflow.
