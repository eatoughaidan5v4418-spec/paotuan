# Paotuan \u9879\u76ee\u6d4b\u8bd5\u8986\u76d6\u62a5\u544a

> \u751f\u6210\u65f6\u95f4: 2026-05-28
> \u5ba1\u8ba1\u8f6e\u6b21: 13 \u8f6e
> \u6f0f\u6d1e\u4fee\u590d: 38 \u4e2a
> Git commits: 18

---

## \u4e00\u3001\u81ea\u52a8\u5316\u6d4b\u8bd5

### pytest (59 tests, 9 subtests)

| \u6d4b\u8bd5\u6587\u4ef6 | \u6d4b\u8bd5\u6570 | \u8986\u76d6\u8303\u56f4 |
|----------|--------|----------|
| test_architecture_hardening.py | 26 | apply_patch, run_turn, zone_validator, CLI smoke |
| test_visibility.py | 11 | \u53ef\u89c1\u6027\u9694\u79bb, \u8bb0\u5fc6\u56fe\u8c31\u5b8c\u6574\u6027 |
| test_web_api.py | 22 | Web API, mock turn, worldgen, obsidian |

### validate_project.py

\u5168\u9879\u76ee\u7ed3\u6784\u6821\u9a8c: campaign state, world clocks, NPC profiles, memory graphs, schemas, prompts, tools, session logs, turn packets

---

## \u4e8c\u3001CLI \u5de5\u5177\u6d4b\u8bd5

| \u5de5\u5177 | \u72b6\u6001 |
|------|------|
| apply_patch.py | \u901a\u8fc7 |
| chaos_manager.py | \u901a\u8fc7 |
| conditions_manager.py | \u901a\u8fc7 |
| lore_manager.py | \u901a\u8fc7 |
| memory_manager.py | \u901a\u8fc7 |
| obsidian_vault.py | \u901a\u8fc7 |
| player_knowledge.py | \u901a\u8fc7 |
| player_state.py | \u901a\u8fc7 |
| progress_tracker.py | \u901a\u8fc7 |
| quest_viewer.py | \u901a\u8fc7 |
| resource_manager.py | \u901a\u8fc7 |
| run_turn.py | \u901a\u8fc7 |
| session_summarizer.py | \u901a\u8fc7 |
| web_game.py | \u901a\u8fc7 |
| world_graph_query.py | \u901a\u8fc7 |
| world_tick_manager.py | \u901a\u8fc7 |
| zone_validator.py | \u901a\u8fc7 |

---

## \u4e09\u3001API \u7aef\u5230\u7aef\u6d4b\u8bd5

| \u7aef\u70b9 | \u65b9\u6cd5 | \u72b6\u6001 |
|------|------|------|
| /api/config | GET | \u901a\u8fc7 |
| /api/campaigns | GET | \u901a\u8fc7 |
| /api/state | GET | \u901a\u8fc7 |
| /api/logs | GET | \u901a\u8fc7 |
| /api/campaigns/new | POST | \u901a\u8fc7 |
| /api/campaigns/select | POST | \u901a\u8fc7 |
| /api/campaigns/delete | POST | \u901a\u8fc7 |
| /api/turn | POST | \u901a\u8fc7 |
| /api/roll | POST | \u901a\u8fc7 |
| /api/validate | POST | \u901a\u8fc7 |
| /api/obsidian/export | POST | \u901a\u8fc7 |

---

## \u56db\u3001\u8fb9\u7f18 case \u6d4b\u8bd5

| \u6d4b\u8bd5 | \u7ed3\u679c |
|------|------|
| \u65e0\u6548\u9ab0\u5b50 | 400 |
| \u7a7a\u884c\u52a8 | 400 |
| visibility_path=none \u8df3\u8fc7 | \u901a\u8fc7 |
| \u65b0NPC\u81ea\u52a8\u521b\u5efa | \u901a\u8fc7 |
| \u96f6\u65f6\u95f4 (None/0) | \u901a\u8fc7 |
| \u91cd\u590d\u6761\u4ef6\u4e0d\u5199 | \u901a\u8fc7 |
| slug \u8def\u5f84\u7a7f\u8d8a | \u901a\u8fc7 |

---

## \u4e94\u3001\u6570\u636e\u5b8c\u6574\u6027

| \u68c0\u67e5\u9879 | \u72b6\u6001 |
|--------|--------|
| NPC YAML | 8 \u5168\u90e8\u5408\u6cd5 |
| NPC memory graphs | 8 \u5168\u90e8\u5408\u89c4 |
| \u60ac\u6302\u5f15\u7528 | 0 |
| JSON Schemas | 9 \u5168\u90e8\u5408\u6cd5 |
| Prompt templates | 13 \u5168\u90e8\u5b58\u5728 |
| Generated campaigns | 4 \u7ed3\u6784\u5b8c\u6574 |

---

## \u516d\u3001\u5b89\u5168\u626b\u63cf

| \u68c0\u67e5\u9879 | \u7ed3\u679c |
|--------|------|
| \u786c\u7f16\u7801 API \u5bc6\u94a5 | \u65e0 |
| .env gitignore | \u6b63\u786e |
| shutil.rmtree \u8def\u5f84 | \u5df2\u4fee\u590d (V27) |
| XSS | escapeHtml() |
| \u8def\u5f84\u7a7f\u8d8a (slug) | \u5df2\u4fee\u590d (V27) |

---

## \u4e03\u3001\u5df2\u77e5\u9650\u5236

1. PowerShell \u7f16\u7801: \u7ba1\u9053\u4f20\u9012\u4e2d\u6587\u53ef\u80fd\u635f\u574f
2. \u4ee3\u7801\u91cd\u590d (V37): run_turn.py \u548c apply_patch.py \u91cd\u590d\u65f6\u95f4\u51fd\u6570
3. \u6d4b\u8bd5\u8986\u76d6: \u7f3a\u5c11 LLM \u96c6\u6210\u6d4b\u8bd5

---

## \u516b\u3001\u6f0f\u6d1e\u7edf\u8ba1

| \u4e25\u91cd\u5ea6 | \u6570\u91cf |
|--------|------|
| HIGH | 4 |
| MEDIUM | 16 |
| LOW | 18 |
| \u603b\u8ba1 | 38 |

---

## \u4e5d\u3001Git \u5386\u53f2

18 commits\uff0c\u5168\u90e8\u5df2\u63a8\u9001\u5230 GitHub\u3002
