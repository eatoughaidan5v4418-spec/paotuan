# 2026-06-02 World Mechanics Manifest

## Summary

- Added campaign-level mechanics capability detection so system/effect-point and cultivation fields are only exposed or auto-updated when the world enables them.
- Added a `rules.character_sheet.sections[].items[]` path for world-specific player mechanics such as `sequence` and `potion_stage`.
- Updated the browser state API and UI to render character sheet sections from the world manifest instead of assuming every world has system/effect-point fields.
- Allowed safe custom ASCII player fields in state patches so manifest-declared mechanics can update without code changes.
- Updated GM, state extraction, and worldgen prompts to require explicit capabilities and manifest-driven custom fields.

## Verification

- `python -m unittest tests.test_web_api`
- `python -m unittest tests.test_architecture_hardening`
- `python validate_project.py`
- `python validate_project.py --root xianxia_campaign`
- `node --check web/static/app.js`
