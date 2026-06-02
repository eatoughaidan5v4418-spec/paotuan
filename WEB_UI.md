# Browser RPG UI

Launch the local browser interface instead of the shell loop:

```powershell
python tools/web_game.py
```

Then open `http://127.0.0.1:8765/`.

The browser UI is API-only. Configure `AI_API_KEY` / `OPENAI_API_KEY` before
running turns or generating a new world.

The UI provides campaign selection, new world generation, a GM narrative feed,
natural-language action input, character sheet, NPC panel, quest and clue panels,
world clocks, validation, and automatic state patch write-back after local
validation.

Players do not need to choose an action type or manually enter elapsed time. The
backend infers the action category and time cost from the submitted text, then
uses that estimate to advance the world.

Long GM text now uses page-level scrolling: the sidebars stay sticky in the
viewport, while the action bar remains reachable at the bottom of the page. The
character sheet is refreshed after each turn from `campaign_state.json` plus
tracked `conditions.json`; AI state patches can update HP, qi, realm, stats, and
conditions through `player_state_changes`.
