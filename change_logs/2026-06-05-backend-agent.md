# Backend Agent Log - 2026-06-05

## Stage 1: Public API Contract Boundary

Goal:
- Add a React-ready bootstrap contract and make the turn response safe for a player-facing frontend.

Files changed:
- `tools/web_api.py`
- `tools/web_game.py`
- `tests/test_web_api.py`

Agent collaboration:
- API Contract Agent recommended an additive `app_bootstrap()` service and `/api/app/bootstrap` route that composes existing `list_campaigns()`, `visible_state()`, `recent_logs()`, and `api_status()`.
- Memory Safety Agent identified public API excessive-data-exposure risks in raw `run_turn()` payloads, raw `player_knowledge`, raw `open_threads`, and unfiltered resources/progress tracks.
- World Simulation Agent confirmed the web turn flow uses the existing elapsed-time and world-clock preview pipeline, but recommended a sanitized `turn_meta` for frontend display.

Decisions:
- Keep existing routes for compatibility and add `/api/app/bootstrap` for the React client.
- Replace public `run_turn()` raw internals with `turn_meta`, sanitized `apply_report`, and refreshed public `state`.
- Add server-side recursive filtering for `secret`, `private`, `gm_only`, hidden keys, and private records before returning player-visible state.
- Keep GM/debug artifacts stored in local AI run files instead of returning them through the player API.

Runtime protocol impact:
- No NPC memory write behavior was changed in this stage.
- The public API now better enforces player-visible vs GM-hidden separation.
- The implementation still relies on the existing turn runner and state patch validator for event visibility, NPC memory writes, and world clock commits.

Verification:
- RED checks were run before implementation:
  - `python -m unittest tests.test_web_api.WebApiTests.test_app_bootstrap_returns_frontend_contract_without_hidden_payloads tests.test_web_api.WebApiTests.test_turn_returns_even_when_patch_apply_has_no_writes`
  - Expected failures: missing `app_bootstrap`, and raw `state_patch` in turn response.
- GREEN/final checks:
  - `python -m unittest tests.test_web_api` -> 35 tests passed.
  - `python -m unittest tests.test_visibility` -> 12 tests passed.
  - `python -m unittest tests.test_architecture_hardening` -> 33 tests passed.
  - `python validate_project.py` -> all checks passed.
  - `python validate_project.py --root xianxia_campaign` -> all checks passed.

Open risks:
- Strict semantic checking of `visibility_evidence.allowed_memory_scope` is still deeper runtime work.
- Schema alignment for `visibility_path: "none"` remains to be audited separately.
- Route-level HTTP tests for `/api/app/bootstrap` can be added after the React frontend starts consuming it.
