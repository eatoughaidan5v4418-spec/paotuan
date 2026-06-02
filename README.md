# Paotuan AI RPG Kit

这是一个本地 AI 跑团工程骨架，用来把“提示词”升级成可持续运行的战役状态系统。

## 文件说明

- `AGENTS.md`：告诉未来的 Codex/GM 进入本项目后必须遵守本地跑团记忆协议。
- `gm-runtime-protocol.md`：我担任 GM 时每回合如何读取、检索、写回记忆。
- `gm-self-audit.md`：GM 主动检查世界冻结、全知 NPC、因果断裂等系统漏洞。
- `ai-rpg-prompts-memory-design.md`：完整设计说明、来源、提示词总览。
- `prompts/`：可直接复制到模型或程序里的提示词。
- `campaign/campaign_state.json`：当前战役的权威状态。
- `campaign/world_graph.jsonl`：世界图谱追加日志，每行一个节点或关系事件。
- `campaign/world_clocks.json`：活世界时钟，负责离屏 NPC、阵营、环境和威胁推进。
- `campaign/world_tick_policy.yaml`：世界 Tick 触发条件、推进优先级和 catch up 规则。
- `campaign/npcs/`：NPC 角色卡与私有记忆流。
- `campaign/npcs/*.memory_graph.json`：每个 NPC 的独立记忆图谱，按时间、重要程度、回忆次数等分层。
- `campaign/memory_policy.yaml`：记忆评分、分层、回忆次数和写入规则。
- `prompts/event-visibility-resolver.md`：写入 NPC 记忆前判断谁能知道什么。
- `prompts/world-tick-runner.md`：玩家耗时或换场景时推进离屏世界。
- `campaign/events/`：全局事件和每个角色的可见性判定示例。
- `campaign/locations/`：地点资料。
- `campaign/lore/`：阵营、规则和世界设定。
- `campaign/session_logs/`：每次跑团原始记录与摘要。
- `campaign/turn_packets/`：一键回合运行器生成的 GM 输入包。
- `schemas/`：状态抽取和 NPC 记忆写入的 JSON Schema。
- `tools/memory_manager.py`：本地记忆分层与回忆次数维护工具。
- `tools/world_tick_manager.py`：本地世界时钟查看与推进工具。
- `tools/run_turn.py`：一键回合运行器，读取状态并生成完整 GM 回合包。

## 推荐使用流程

1. 开局时读取 `prompts/gm-system.md`。
2. 每回合把玩家行动填入 `prompts/turn-input-template.md`。
3. 如果玩家行动消耗时间或切换场景，先用 `prompts/world-tick-runner.md` 推进世界时钟。
4. 从 `campaign_state.json`、当前地点、在场 NPC、NPC 记忆中检索相关信息。
5. 让 GM 模型输出玩家可见叙事。
6. 用 `prompts/state-extractor.md` 抽取结构化状态变更。
7. 用 `prompts/event-visibility-resolver.md` 判定每个 NPC 是否知道本事件。
8. 用 `prompts/npc-memory-writer.md` 只为允许知道的 NPC 写入私有记忆。
9. 把结果追加到 `session_logs/`、`world_graph.jsonl`，并写入对应 NPC 的 `*.memory_graph.json`。
10. 用 `tools/memory_manager.py` 更新 `*.memory_graph.json` 的回忆次数、分数和层级；旧版 `*.memories.jsonl` 仅作为历史/兼容素材保留。

## 直接游玩

现在可以用本地游戏循环直接跑团：

```powershell
$env:AI_API_KEY="你的 API Key"
$env:AI_MODEL="gpt-4.1-mini"
python tools/play_game.py
```

如果使用 OpenAI 兼容接口，例如本地网关、DeepSeek、通义等兼容 `/chat/completions` 的服务：

```powershell
$env:AI_BASE_URL="https://api.example.com/v1"
$env:AI_API_KEY="你的 API Key"
$env:AI_MODEL="你的模型名"
python tools/play_game.py
```

运行 `tools/play_game.py` 需要配置 API Key；无 API Key 时，先运行 `python validate_project.py` 做本地结构校验。

也可以让 AI 从零生成一个新世界观和开局战役，不依赖现有 `campaign/`：

```powershell
python tools/play_game.py --new "赛博修仙废城，玩家是刚觉醒的巡城医师"
```

生成目录默认在 `generated_campaigns/<主题slug>/`。生成后会自动切到这个新战役继续游玩。

`generated_campaigns/` 下保留了一些历史 worldgen 样例。它们不是正式支持战役，也不作为当前发布校验门槛；旧样例可能仍使用过期协议。当前正式支持范围是仓库根 `campaign/` 和 `xianxia_campaign/`。worldgen 源头仍在持续修补，新增战役应先运行 `python validate_project.py --root <战役目录>`。

如果想指定生成位置：

```powershell
python tools/play_game.py --new "黑暗童话边境城" --new-root .\my_campaign
```

`tools/play_game.py` 会自动：

1. 读取战役状态、地点、NPC 私有记忆和世界时钟。
2. 根据玩家输入的自然语言自动推断行动类型和耗时，再生成 GM 回合包。
3. 调用 AI API，让 AI 按 `prompts/ai-game-runner.md` 扮演自动 GM。
4. 允许 AI 通过白名单工具读取 `campaign/`、`prompts/`、`schemas/` 下的文件。
5. 要求 AI 输出玩家可见正文和结构化 `state_patch`。
6. 用 `tools/apply_patch.py` 校验并写回状态、NPC 记忆、事件理解、稳定理解和修正记录。

AI 不能直接任意写文件；它只能输出结构化 patch，由本地工具验证后执行。

玩家不需要手动选择“交谈/调查/移动”等行动类型，也不需要填写耗时；例如“我在旧码头边等半小时，看看谁出现”会被推断为等待 30 分钟，“我查看角色卡和任务面板”不会推进时间。需要覆盖自动推断时，CLI 仍可显式传 `--elapsed-minutes`。

角色卡会在每回合后从最新状态重绘。AI 若让玩家受伤、恢复、消耗灵力、获得状态词条或属性成长，应通过 `state_patch.player_state_changes` 写入，避免只在叙事文字里出现而数据不变。

## 研究优先原则

当 GM/设计者准备新增一个具体机制或指出一个系统问题时，先上网搜索相关概念、已有实现和常用术语，再把结论写入本地协议或数据结构。

## 最小可玩原则

- 玩家可见文本和隐藏状态更新分开。
- NPC 只记住自己能知道的事。
- A 知道的事不会自动同步给 B；传播必须有通信、偷听、公共信号或可推断证据。
- 世界不会因玩家视角冻结；离屏 NPC、阵营、地点和威胁会按时钟推进。
- 所有重要事实都带来源、时间和置信度。
- 每条记忆都有 `importance`、`recall_count`、`last_recalled_turn` 和 `tier`。
- 重要事件会先变成 NPC 的主观“事件理解”，多个事件理解再沉淀成稳定信念、态度、关系判断或行为规则。
- 新事件会检查是否改变旧理解，可能强化、削弱、反驳、限定、重构或替换它，并保留修正历史。
- 旧事实被推翻时标记失效，不直接删除。
- 骰子、库存、位置、数值尽量由结构化状态维护。

## 记忆工具示例

生成一个 GM 回合包：

```powershell
python tools/run_turn.py --player-action "我观察旧码头的巡夜人和缆绳堆" --elapsed-minutes 10 --write
```

如果确认这次行动确实消耗时间，并要立刻写回世界时钟和战役时间：

```powershell
python tools/run_turn.py --player-action "我在旧码头附近等待半小时" --elapsed-minutes 30 --write --commit-world-tick
```

查看米拉当前记忆排序：

```powershell
python tools/memory_manager.py rerank campaign/npcs/npc_mira.memory_graph.json --turn 1
```

当 GM 实际使用了某条记忆后，增加回忆次数并写回：

```powershell
python tools/memory_manager.py recall campaign/npcs/npc_mira.memory_graph.json mem_mira_0001 --turn 2 --write
python tools/memory_manager.py rerank campaign/npcs/npc_mira.memory_graph.json --turn 2 --write
```

查看活世界时钟：

```powershell
python tools/world_tick_manager.py list
```

推进一个离屏时钟：

```powershell
python tools/world_tick_manager.py tick clock_black_lantern_deal --amount 1 --reason "玩家在酒馆调查消耗 1 小时" --write
```

## 当前验证状态

以下结果于 2026-06-02 在当前环境内重新验证：

```powershell
python validate_project.py
# [OK] All checks passed

python validate_project.py --root xianxia_campaign
# [OK] All checks passed

python -m unittest tests.test_web_api
# 25 passed
```

当前 bundled Python 环境缺少 `pytest`；核心 YAML/CLI 路径已有 stdlib fallback，`PyYAML` 为可选增强。完整 pytest 需在具备 `pytest` 的环境中复验。

正式支持战役：

- `campaign/`：默认 demo 战役。
- `xianxia_campaign/`：仙侠战役。

`generated_campaigns/` 是历史样例与 worldgen 回归素材集合，不应被描述为全部可用或全部兼容当前 schema。
