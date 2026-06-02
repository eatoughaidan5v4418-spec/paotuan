# Paotuan AI RPG Kit — 架构文档

> 初始生成日期: 2026-05-23
> 最近同步日期: 2026-06-02
> 版本: v2.1-doc-sync
> 基于: Mythic GME Chaos Factor, Ironsworn Progress Tracks, Burning Wheel BITs, PbtA Tags + Instincts, FATE Aspects

## 目录

1. [项目结构](#1-项目结构)
2. [核心设计理念](#2-核心设计理念)
3. [GM 运行协议](#3-gm-运行协议)
4. [数据层：战役状态](#4-数据层战役状态)
5. [数据层：NPC 系统](#5-数据层npc-系统)
6. [数据层：世界模拟](#6-数据层世界模拟)
7. [数据层：玩家侧](#7-数据层玩家侧)
8. [数据层：叙事张力](#8-数据层叙事张力)
9. [工具链](#9-工具链)
10. [测试](#10-测试)
11. [多战局支持](#11-多战局支持)

---

## 1. 项目结构

```
paotuan/
├── AGENTS.md                          # Codex/GM 进入点，必须遵守的协议
├── ARCHITECTURE.md                     # 本文档
├── README.md                          # 项目概览
├── .gitignore
├── validate_project.py                # 全项目校验
│
├── gm-runtime-protocol.md             # GM 每回合运行协议
├── gm-self-audit.md                   # GM 自主审计清单
│
├── prompts/                           # LLM 可直接使用的提示词
│   ├── gm-system.md                   #   主 GM 系统提示词
│   ├── turn-input-template.md         #   回合输入模板
│   ├── event-visibility-resolver.md   #   事件可见性判定
│   ├── state-extractor.md             #   状态抽取
│   ├── npc-memory-writer.md           #   NPC 记忆写入
│   ├── memory-retriever.md            #   记忆检索
│   ├── memory-consolidator.md         #   记忆巩固
│   ├── world-tick-runner.md           #   世界时钟推进
│   ├── event-interpretation-extractor.md
│   ├── understanding-consolidator.md
│   └── understanding-reviser.md
│
├── schemas/                           # JSON Schema 定义
│   ├── state_patch.schema.json
│   ├── turn_packet.schema.json
│   ├── event_visibility.schema.json
│   ├── npc_memory_graph.schema.json
│   ├── npc_memory_write.schema.json
│   ├── npc_interpretation.schema.json
│   ├── npc_understanding_update.schema.json
│   ├── npc_understanding_revision.schema.json
│   └── world_tick.schema.json
│
├── tools/                             # 命令行工具
│   ├── run_turn.py                    #   一键回合运行器
│   ├── apply_patch.py                 #   状态补丁安全应用器
│   ├── memory_manager.py              #   NPC 记忆评分/分层
│   ├── world_tick_manager.py          #   世界时钟管理
│   ├── zone_validator.py              #   空间/感知模型验证
│   ├── resource_manager.py            #   阵营/NPC 资源管理
│   ├── player_knowledge.py            #   玩家已知信息账本
│   ├── quest_viewer.py                #   任务图谱查看
│   ├── time_utils.py                  #   统一时间系统
│   ├── chaos_manager.py               #   混沌因子 + 骰子 + Oracle
│   ├── conditions_manager.py          #   角色状态管理
│   └── progress_tracker.py            #   进度条 (Ironsworn)
│
├── tests/                             # 自动化测试 (67 tests)
│   ├── test_architecture_hardening.py #   工具链、校验器、CLI smoke (30 tests)
│   ├── test_visibility.py             #   可见性、知识隔离、认知图谱 (12 tests)
│   └── test_web_api.py                #   Web API、API turn、worldgen (25 tests)
│
├── campaign/                          #   ★ demo 战局 (码头/黑灯会)
│   ├── campaign_state.json
│   ├── world_clocks.json
│   ├── world_graph.jsonl
│   ├── chaos_factor.json
│   ├── conditions.json
│   ├── progress_tracks.json
│   ├── resources.json
│   ├── player_knowledge.json
│   ├── quest_graph.json
│   ├── rumors.json
│   ├── oracles.json
│   ├── memory_policy.yaml
│   ├── world_tick_policy.yaml
│   ├── npcs/                          #   NPC 角色卡 + 记忆图谱
│   ├── locations/                     #   地点 (含 zone 模型)
│   ├── lore/                          #   阵营、规则
│   ├── events/                        #   全局事件
│   ├── session_logs/                  #   跑团记录
│   └── turn_packets/                  #   GM 回合包
│
└── xianxia_campaign/                  #   ★ 仙侠战局 (青云坊市/血灵芝)
    └── campaign/                      #   (同上结构)
```

## 2. 核心设计理念

### 最小可玩原则
- 玩家可见文本和 GM 隐藏状态分开
- NPC 只记住自己能知道的事
- A 知道的事不会自动同步给 B；传播必须有通信、偷听、公共信号或可推断证据
- 世界不会因玩家视角冻结；离屏 NPC、阵营、地点和威胁按时钟推进
- 所有重要事实都带来源、时间和置信度

### 四层架构
1. **GM 行为提示词** — 主持风格、叙事节奏、输出格式
2. **结构化世界状态** — 角色、地点、阵营、物品、任务、秘密落在可更新的数据里
3. **NPC 私有记忆** — 每个 NPC 有自己的看见、听说、误解、相信、遗忘、反思记忆
4. **记忆图谱 + 检索** — 用实体和关系管理"谁知道什么、何时知道"

---

## 3. GM 运行协议

### 每回合固定流程

```
1. 玩家输入自然语言行动；play_game.py/web_api.py 自动推断行动类型和耗时
2. 运行 run_turn.py 生成回合包；如果玩家行动消耗时间/切换场景 → 预览世界时钟
3. 读取当前地点、在场 NPC、NPC 记忆
4. 组装 GM 上下文，生成玩家可见正文
5. 用 state-extractor 抽取结构化变更
6. 用 event-visibility-resolver 判定谁看见什么
7. 用 npc-memory-writer 给有可见性的 NPC 写记忆
8. 用 apply_patch.py 安全写入所有变更
9. 追加 session_log、world_graph
```

### 混沌因子介入

每回合开局前可运行场景检定：

```powershell
python tools/chaos_manager.py scene-check
```

- 混乱因子 1-10，初始 5
- 场景被中断时，掷 Oracle 神谕表确定随机事件方向

---

## 4. 数据层：战役状态

### campaign_state.json

```json
{
  "campaign_id": "xianxia_001",
  "current_turn": 1,
  "current_time": "第 1 日 辰时",
  "_time_tick": 480,
  "current_scene": {
    "scene_id": "scene_0001",
    "location_id": "loc_azure_cloud_market",
    "summary": "...",
    "present_entities": ["pc_main", "npc_liu_qing"],
    "active_threads": ["thread_blood_spirit_mushroom"]
  },
  "player_characters": [{"id": "pc_main", "inventory": [], "conditions": []}],
  "quests": [...]
}
```

`_time_tick` 是距第 1 日 00:00 的分钟数（规范内部时间）。`current_time` 是展示用的中文格式。所有计算走 tick。

AI 回合造成的玩家角色变化通过 `state_patch.player_state_changes` 写回，覆盖 `health`、`qi`、`realm`、`stats.*`、`condition/conditions` 等角色卡字段。Web UI 每回合刷新时会合并 `campaign_state.json` 与 `conditions.json`，因此叙事中的受伤、恢复、修炼成长不应只停留在正文。

### 统一时间系统 (tools/time_utils.py)

| 函数 | 作用 |
|------|------|
| `display_to_tick("第 1 日 20:00")` | → 1200 |
| `tick_to_display(1200)` | → "第 1 日 20:00" |
| `sync_campaign_time(state)` | 确保 tick 和 display 一致 |
| `parse_time_delta("1 时辰")` | → 120 分钟 |

所有工具都从 `time_utils` 导入时间函数，不再各自实现。

---

## 5. 数据层：NPC 系统

### 5.1 角色卡 (npcs/*.yaml)

```yaml
id: npc_mira
name: 米拉
role: 消息贩子
faction: faction_unaligned_brokers
public_face: "瘦削、警觉..."
core_desire: "用情报换取安全和金钱"
fear: "被黑灯会发现她卖出过他们的消息"
bottom_line: "不会无偿透露会让自己送命的情报"

traits:                           # ★ 新增: 融合 BITs + Tags
  personality_tags: ["谨慎", "多疑", "计算型", "自保优先"]
  instinct: "先试探对方知道多少再决定自己透露什么"
  stress_response: "逃避"
  social_approach: "试探性"
  cognitive_bias: "负面归因"

voice_style:
  pace: "短句，低声，喜欢反问"
  habits: [...]
  forbidden_topics: [...]

relationship_hooks:
  - target_id: pc_main
    trust: 0
    fear: 0
    debt: 0

change_switches:
  trust: ["玩家证明能保护她"]
  threat: ["玩家把她交给黑灯会"]
```

**Traits 设计来源:**
| 字段 | 来源 | 作用 |
|------|------|------|
| `personality_tags` | PbtA Tags + D&D Personality | GM 判断 NPC 倾向 |
| `instinct` | Burning Wheel Instinct | NPC 的默认行为规则 |
| `stress_response` | 心理学 fight/flight/freeze | 压力下的行为模式 |
| `social_approach` | PbtA | 社交策略类型 |
| `cognitive_bias` | 认知心理学 | 信息处理偏差，关联事件理解系统 |

### 5.2 记忆图谱 (npcs/*.memory_graph.json)

三层认知模型：
```
客观事件 → NPC 主观事件记忆 → 事件理解 → 稳定理解
```

| 层 | 回答的问题 | 存储 |
|----|-----------|------|
| 事件记忆 (episodic) | "发生了什么" | memory_nodes |
| 事件理解 (interpretation) | "这对我意味着什么" | interpretation_nodes |
| 稳定理解 (understanding) | "我以后该怎么看这个人/地方/阵营" | understanding_nodes |

**记忆评分公式:**
```
score = importance*0.35 + salience*0.20 + recency*0.15
      + recall*0.15 + emotion*0.10 + confidence*0.05
```

| 层级 | 分数 | 含义 |
|------|------|------|
| core | >= 0.78 | 身份核心/重大创伤/救命恩情，几乎总影响行动 |
| active | >= 0.48 | 当前场景或近期会用，优先放上下文 |
| dormant | >= 0.22 | 不主动加载，相关实体出现时唤起 |
| archive | < 0.22 | 只保留审计和极少数深度检索 |

**理解修正:** 新事件可以 `supports/weakens/contradicts/qualifies/reframes/supersedes/splits` 旧理解。旧理解不删除，只改变状态。

### 5.3 知识隔离

写入 NPC 记忆前，必须通过 `event-visibility-resolver` 判定可见性:

| 路径 | 含义 |
|------|------|
| `direct_visual` | 亲眼看见 |
| `direct_auditory` | 亲耳听见 |
| `detected_observer` | 被发现自己在观察 |
| `told_by` | 被明确告知 |
| `overheard` | 偷听或无意听见 |
| `inferred` | 基于证据合理推断 |
| `public_signal` | 公共信号 (爆炸/钟声/公告) |

**硬规则:**
- A 知道的不自动同步给 B
- 传播必须有记录为通信事件
- 接收者只记住"收到的信息版本"，不是客观真相
- 旧事实被推翻时标记失效，不删除

### 5.4 动态 NPC 生成

`apply_patch.py` 首次给新 NPC 写记忆时，自动创建:
- `{npc_id}.memory_graph.json` — 空记忆图谱
- `{npc_id}.yaml` — 含 traits 骨架的 minimal 角色卡

`run_turn.py` 通过 `collect_context` 自动加载 profile 或 graph 任一存在的 NPC。

---

## 6. 数据层：世界模拟

### 6.1 世界时钟 (world_clocks.json)

| 类型 | 示例 |
|------|------|
| `faction_project` | 阵营计划 |
| `npc_schedule` | NPC 日程/巡逻 |
| `threat_countdown` | 威胁逼近 |
| `environment_process` | 环境变化 |
| `rumor_spread` | 传言扩散 |

每个时钟有 `_next_tick_at_tick`（规范时间）和 `next_tick_at`（展示时间）。触发条件在 `world_tick_policy.yaml` 定义。

### 6.2 空间/感知模型 (locations/*.yaml)

每个地点分为多个 zone，zone 之间有连接定义 LOS 和声音传播:

```yaml
zones:
  - id: zone_market_entrance
    ambient_light: dim
    ambient_noise: moderate
    initial_occupants: [npc_liu_qing]

zone_connections:
  - from: zone_market_entrance
    to: zone_market_stalls
    type: open
    distance: 20
    line_of_sight: true
    sound: clear
```

`tools/zone_validator.py` 使用 YAML 解析地点文件，支持 `--validate`、`--list`、`--can-see`、`--can-hear`。感知查询会返回直接或多跳路径、遮挡原因和声音衰减等级。

### 6.3 世界图谱 (world_graph.jsonl)

每行一个 JSON 记录，记录节点(Node)和关系(Edge)。追加式日志。

---

## 7. 数据层：玩家侧

### 7.1 玩家已知信息 (player_knowledge.json)
- `clues_discovered` — 已发现线索
- `npcs_known` — 已知 NPC 及了解程度
- `locations_explored` — 探索过的地点
- `facts_understood` — 理解的事实 (带置信度)
- `events_witnessed` — 亲历事件

### 7.2 任务图谱 (quest_graph.json)
- 线索 (clues) 指向干预节点
- 障碍 (obstacles) 标注绕过方式
- 干预节点 (intervention_nodes) 定义玩家可做的事
- 倒计时 (countdown) + 失败后果

### 7.3 传言系统 (rumors.json)
- 来源、传播路径、每个听者主观版本
- 支持 variant (变形版本)

---

## 8. 数据层：叙事张力

### 8.1 混沌因子 (chaos_factor.json) — 来自 Mythic GME
- 1-10 量表，初始 5
- 场景检定: 1d10 vs chaos → expected/altered/interrupt
- 调整: `python tools/chaos_manager.py adjust +1 --reason "..."`

### 8.2 进度条 (progress_tracks.json) — 来自 Ironsworn
- 任务/旅行/战斗/项目的 0/N 进度轨
- 推进: `python tools/progress_tracker.py advance <id> --amount 2`
- 进度检定: `python tools/progress_tracker.py progress-roll <id>`

### 8.3 角色状态 (conditions.json)
- PC 和 NPC 共用，支持 8 种预设状态
- add/remove/list: `python tools/conditions_manager.py ...`

### 8.4 资源系统 (resources.json)
- 阵营: money, manpower, risk_level, reputation, cooldowns
- NPC: money, risk_tolerance, stamina, supplies, cooldowns

### 8.5 Oracle 神谕表 (oracles.json)
- action_theme, npc_motivation, location_feature, event_twist, npc_appearance, treasure
- 掷表: `python -c "import json,random;t=json.loads(open('campaign/oracles.json').read());print(random.choice(t['tables']['event_twist']))"`

---

## 9. 工具链

| 工具 | 用途 | 关键参数 |
|------|------|---------|
| `run_turn.py` | 一键回合包生成 | `--player-action`, `--elapsed-minutes`, `--write`, `--commit-world-tick` |
| `play_game.py` | 可玩循环/AI GM 执行器 | `--once`, `--new`；默认自动从玩家文本推断行动类型和耗时 |
| `apply_patch.py` | 安全写入状态变更 | `--write`, `--dry-run`, `--session-id` |
| `memory_manager.py` | 记忆评分/分层/回忆次数 | `rerank`, `recall` |
| `world_tick_manager.py` | 世界时钟查看/推进 | `list`, `tick` |
| `zone_validator.py` | 地点 zone 模型验证 | `--validate`, `--list`, `--can-see`, `--can-hear` |
| `resource_manager.py` | 资源/冷却管理 | `list`, `check`, `consume`, `cooldown`, `tick` |
| `player_knowledge.py` | 玩家知识账本 | `list`, `add-clue`, `add-npc`, `add-location`, `add-fact` |
| `quest_viewer.py` | 任务图谱查看 | `list`, `show` |
| `time_utils.py` | 时间换算 (库) | 被其他工具导入 |
| `chaos_manager.py` | 混沌因子+骰子+Oracle | `show`, `adjust`, `scene-check`, `roll`, `oracle` |
| `conditions_manager.py` | 角色状态 | `list`, `add`, `remove`, `known` |
| `progress_tracker.py` | 进度条 | `list`, `create`, `advance`, `progress-roll` |
| `validate_project.py` | 全项目校验 | `--root <path>`，可传项目根、战局目录或 campaign 数据目录 |

---

## 10. 测试

截至 2026-06-02，自动化套件共有 67 个测试：

> 迁移说明：旧版架构文档曾单列 `tests/test_visibility.py` 的 8 个自动化测试；当前应以完整套件 67 个测试为准。当前 bundled Python 缺少 `pytest` 和 `PyYAML`，完整 pytest 需在依赖齐备后复验。

| 测试文件 | 数量 | 覆盖范围 |
|----------|------|----------|
| `tests/test_architecture_hardening.py` | 30 | `validate_project.py` 路径解析、`apply_patch.py` 语义错误、CLI smoke、世界时钟提交、文档一致性 |
| `tests/test_visibility.py` | 12 | NPC 知识隔离、`visibility_evidence`、记忆图谱、interpretation provenance |
| `tests/test_web_api.py` | 25 | Web API、API turn、worldgen、可见状态过滤、私有世界时钟隔离 |

`tests/test_visibility.py` 的关键验证包括：

| 测试 | 验证 |
|------|------|
| `test_a_sees_B_not_modified` | A 看见玩家，B 的记忆图谱不变 |
| `test_separate_memories_not_mixed` | A 和 B 的记忆内容独立 |
| `test_visibility_path_attached` | 每段记忆带 visibility_path |
| `test_invalid_path_rejected` | 无效 visibility_path 被 validate 拦截 |
| `test_told_by_separate_memory` | B 被 A 告知后只知被告知版本 |
| `test_memory_ids_sequential` | 记忆 ID 唯一且连续 |
| `test_new_npc_creates_graph` | 新 NPC 自动创建记忆图谱 |
| `test_cognitive_layer_writes` | 事件理解、稳定理解和修正事件可写入 |
| `test_memory_write_without_visibility_evidence_rejected` | 缺少可见性证据的记忆写入被拒绝 |
| `test_dangling_interpretation_provenance_rejected` | 悬空 interpretation 来源被拒绝 |

运行:

```powershell
python -m unittest tests.test_web_api
python validate_project.py
python validate_project.py --root xianxia_campaign
```

2026-06-02 本轮复验结果：Web API 定向套件 `25 passed`；默认 demo 与仙侠战役校验均通过；完整 pytest 等待 `pytest` + `PyYAML` 环境复验。

---

## 11. 多战局支持

每个战局是一个独立目录。仓库根的 `campaign/` 是默认 demo 战局数据目录；`xianxia_campaign/` 是战局目录，内部包含自己的 `campaign/` 数据目录。工具通过 `--root` 参数或 cwd 定位当前战局。

```powershell
# demo 战局
python tools/run_turn.py --player-action "我要..." --write

# 仙侠战局
cd xianxia_campaign
python ..\tools\run_turn.py --player-action "我要..." --write
```

`validate_project.py --root <path>` 可指定校验目标：`<path>` 可以是项目根、战局目录（如 `xianxia_campaign`），也可以直接是 campaign 数据目录（如 `campaign` 或 `xianxia_campaign/campaign`）。校验器会在输出中显示解析后的 `project_root` 和 `campaign_dir`。

### 正式支持范围

- `campaign/`：默认 demo 战役，纳入发布校验。
- `xianxia_campaign/`：仙侠战役，纳入发布校验。
- `generated_campaigns/`：历史 worldgen 样例与回归素材，不纳入正式支持承诺。旧样例可能使用过期协议；worldgen prompt 源头修补完成前，新生成战役必须单独执行 `validate_project.py --root <战役目录>`。

---

> 本文档随项目迭代更新。每次新增机制或工具后同步更新。
