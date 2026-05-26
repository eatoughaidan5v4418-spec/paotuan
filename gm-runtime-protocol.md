# GM 运行协议

这个文件规定我在本地担任 GM 时应该怎样运行战役、维护 NPC 记忆图谱，并让每个 NPC 保留连续记忆。

## 核心目标

每个 NPC 都不是“临时生成的对白机器”，而是一个拥有独立记忆、目标、误解、关系和行动计划的角色。GM 每一回合都要从本地状态中读取相关信息，生成叙事后再写回新的事件和记忆。

## 每回合固定流程

本地优先使用 `tools/run_turn.py` 生成回合包：

```powershell
python tools/run_turn.py --player-action "玩家行动" --elapsed-minutes 10 --write
```

1. 读取 `campaign/campaign_state.json`，确认当前时间、地点、在场实体、任务压力。
2. 如果玩家行动消耗时间、切换场景、等待、休息或旅行，先运行世界 Tick：
   - 读取 `campaign/world_tick_policy.yaml`。
   - 读取 `campaign/world_clocks.json`。
   - 使用 `prompts/world-tick-runner.md` 推进离屏 NPC、阵营、地点和威胁。
   - 将离屏事件再交给 `prompts/event-visibility-resolver.md`，判定谁能知道。
3. 读取当前地点文件，例如 `campaign/locations/old_dock.yaml`。
4. 对每个在场 NPC：
   - 读取 `campaign/npcs/{npc_id}.yaml`。
   - 读取 `campaign/npcs/{npc_id}.memory_graph.json`。
   - 按 `campaign/memory_policy.yaml` 计算应召回的记忆和稳定理解。
5. 组装 GM 上下文：
   - 玩家可见场景。
   - GM 隐藏事实。
   - 在场 NPC 的可用记忆、事件理解、稳定理解、错误信念、目标。
   - 当前规则和检定结果。
6. 输出玩家可见正文，使用 `prompts/gm-system.md` 的格式。
7. 回合后整理：
   - 写入玩家行动事件。
   - 使用 `prompts/event-visibility-resolver.md` 判定每个 NPC 是否能知道该事件。
   - 为相关 NPC 生成“这个 NPC 如何理解本事件”的事件理解。
   - 检查新事件理解是否会改变旧稳定理解。
   - 在证据足够时，把多条事件理解巩固成稳定理解。
   - 更新 `campaign/campaign_state.json`。
   - 更新相关 NPC 的 `*.memory_graph.json`。
   - 追加世界级事件到 `campaign/world_graph.jsonl`。
   - 追加本回合原始记录到 `campaign/session_logs/`。

## 三层认知模型

NPC 的长期连续性分成三层：

1. **事件记忆**：这个 NPC 亲历、听说或推断到的具体事件，回答“发生了什么”。
2. **事件理解**：这个 NPC 对某个事件的主观解释，回答“这件事对我意味着什么”。
3. **稳定理解**：多个事件理解沉淀出的信念、偏见、关系判断、行为规则或计划，回答“我以后该怎样看待这个人/地方/阵营/自己”。

这对应资料中常见的 `episodic memory -> reflection/appraisal -> semantic memory / belief` 路径：先保留原始事件，再抽取主观评价，最后在证据足够时巩固成更高层理解。

```text
客观事件
  -> NPC 可知版本
  -> NPC 主观理解
  -> 多条理解聚合
  -> 稳定信念 / 态度 / 关系判断 / 行为规则 / 计划
  -> 后续新事件修正旧理解
```

## 知识隔离与可见性

全局事件不等于 NPC 私有记忆。事件必须先通过可见性判定，才能写入某个 NPC 的记忆图谱。

### 硬规则

- GM 可以知道客观事件，NPC 只能知道自己可观察、被告知或可合理推断的版本。
- A 知道的事不会自动同步给 B。
- 玩家知道的事不会自动同步给 NPC。
- NPC 的内心想法不会自动被其他 NPC 知道。
- 传播必须发生为一个可记录事件，例如说出口、写信、喊叫、公告、眼神暗号、魔法传讯。
- 即使传播发生，接收者也只能记住“收到的信息版本”，不是客观真相。

### 可见性路径

| 路径 | 含义 |
| --- | --- |
| `direct_visual` | 亲眼看见 |
| `direct_auditory` | 亲耳听见 |
| `detected_observer` | 被观察者发现自己被观察 |
| `told_by` | 被明确告知 |
| `overheard` | 偷听或无意听见 |
| `inferred` | 基于证据合理推断 |
| `public_signal` | 爆炸、钟声、公告、群众骚动等公共信号 |
| `none` | 没有可见性路径，不能写入记忆 |

### A/B 示例

```text
客观事件：玩家躲在缆绳堆后观察 A，A 察觉有人在看自己，B 在账房小屋里。

A 的可写记忆：
  “缆绳堆附近有人在观察我，但我不能完全确认是谁。”

B 的可写记忆：
  无。B 不在场、没看见、没听见、没人告诉他。
```

如果 A 之后跑去告诉 B：“刚才有人盯着我”，这才生成新的通信事件。B 可以记住：

```text
B 听 A 说，缆绳堆附近可能有人盯着 A。
```

B 仍然不应该记住“玩家观察了 A”，除非 A 明确说出了玩家身份，或 B 有其他证据能推断。

## 活世界与离屏模拟

世界不会因为玩家在某个地点就冻结。NPC 有自己的生活，阵营有自己的目标，地点和环境也会按时间变化。

### 世界 Tick 何时发生

- 玩家行动明确消耗时间。
- 玩家从一个地点移动到另一个地点。
- 玩家等待、休息、旅行、调查很久。
- 场景结束。
- 某个时钟到达 `next_tick_at`。
- 玩家行动触发离屏后果。

### 世界 Tick 推进什么

| 类型 | 示例 |
| --- | --- |
| `faction_project` | 黑灯会推进交易、城卫搜查街区、教派准备仪式 |
| `npc_schedule` | A 巡逻、B 抄货单、米拉寻找买家 |
| `threat_countdown` | 追兵接近、火势蔓延、仪式完成 |
| `environment_process` | 天气、潮汐、疾病、物资腐坏 |
| `rumor_spread` | 传言、密信、公告、街头消息传播 |

### 推进原则

- 只推进与战役相关、到点、被触发或接近玩家行动范围的时钟。
- 离屏事件要有因果：目标、日程、资源、压力、玩家之前的行动。
- 离屏事件不抢走玩家关键选择，而是制造后果、压力、机会和线索。
- 离屏事件不自动公开，仍要经过可见性判定。
- 很久没处理的区域用 catch up 摘要追赶，不逐分钟模拟。

### 离屏事件例子

```text
玩家在酒馆审问线人，用掉 1 小时。

世界 Tick：
  黑灯会交易时钟 2/6 -> 3/6。
  两名外围成员抵达旧码头外围。
  河潮上涨，低洼栈桥的脚印开始变淡。

玩家当前不一定知道这些事。
若之后回到旧码头，可能看到陌生脚印、湿滑木板、暗号痕迹。
```

## NPC 记忆图谱

每个 NPC 的记忆图谱至少包含：

- `npc_id`：记忆拥有者。
- `current_turn`：当前回合数，用于计算时间衰减。
- `memory_nodes`：记忆节点。
- `interpretation_nodes`：NPC 从单个事件中提取的主观理解。
- `understanding_nodes`：多个事件理解沉淀出的稳定理解。
- `revision_events`：新事件如何改变旧理解的修正记录。
- `relation_edges`：记忆之间、记忆与人物/地点/阵营之间的关系。
- `beliefs`：NPC 当前相信的事实，可以为真、假、传言或过期。
- `plans`：NPC 根据记忆形成的短期计划。

### 记忆节点字段

| 字段 | 含义 |
| --- | --- |
| `id` | 记忆 ID |
| `type` | `episodic` 事件记忆、`semantic` 事实记忆、`procedural` 习惯/办法 |
| `content` | NPC 自己会如何记住这件事 |
| `created_turn` | 产生回合 |
| `last_recalled_turn` | 上次被召回回合 |
| `recall_count` | 被召回次数 |
| `importance` | 0-1，剧情/目标/生存重要性 |
| `salience` | 0-1，当前显著性 |
| `emotional_valence` | -2 到 2，负面到正面 |
| `confidence` | 0-1，NPC 对它的确信程度 |
| `source` | `saw` / `heard` / `inferred` / `rumor` |
| `tier` | `core` / `active` / `dormant` / `archive` |
| `valid` | 是否仍有效 |
| `invalid_at_turn` | 失效回合 |
| `contradicted_by` | 推翻它的新记忆 ID |
| `related_entities` | 相关人物、地点、阵营、任务 |

### 事件理解字段

| 字段 | 含义 |
| --- | --- |
| `id` | 理解 ID |
| `derived_from_event_id` | 来自哪个客观事件 |
| `derived_from_memory_id` | 来自 NPC 哪条事件记忆 |
| `text` | NPC 对事件的主观解释 |
| `appraisal` | 目标影响、威胁、机会、责任归因、道德判断、关系信号 |
| `emotion` | 这条理解带来的情绪 |
| `confidence` | NPC 对该解释的确信程度 |
| `importance` | 该理解对 NPC 的重要性 |
| `possible_misunderstanding` | 是否可能是误解 |

### 稳定理解字段

| 字段 | 含义 |
| --- | --- |
| `id` | 稳定理解 ID |
| `type` | `belief` / `attitude` / `relationship_judgment` / `schema` / `plan_rule` / `self_understanding` |
| `text` | 多个事件沉淀出的长期理解 |
| `supporting_interpretation_ids` | 支持它的事件理解 |
| `supporting_memory_ids` | 支持它的事件记忆 |
| `contradicting_interpretation_ids` | 反驳它的事件理解 |
| `confidence` | 当前置信度 |
| `stability` | 稳定程度，越高越难被单次事件推翻 |
| `tier` | `core` / `active` / `dormant` / `archive` |
| `behavior_effect` | 它会如何影响 NPC 行动和说话 |
| `revision_status` | `active` / `contested` / `weakened` / `superseded` / `archived` |
| `superseded_by` | 如果被新理解替代，指向新理解 ID |

## 理解修正机制

新事件可能改变 NPC 原本的理解。每次产生新事件理解后，必须检索相关旧稳定理解，并判断它们之间的关系。

### 新事件对旧理解的影响

| effect | 含义 | 处理 |
| --- | --- | --- |
| `supports` | 新事件支持旧理解 | 提高 `confidence`，可能提高 `stability` |
| `weakens` | 新事件削弱旧理解 | 降低 `confidence`，可能标记 `weakened` |
| `contradicts` | 新事件直接反驳旧理解 | 降低 `confidence`，标记 `contested` |
| `qualifies` | 新事件给旧理解增加条件 | 保留旧理解，但修改适用范围 |
| `reframes` | 新事件改变解释角度 | 旧理解保留，新解释成为竞争理解 |
| `supersedes` | 新理解替代旧理解 | 旧理解标记 `superseded`，新理解接管行为影响 |
| `splits` | 旧理解过于笼统，需要拆分 | 生成多个更具体理解 |
| `no_change` | 新证据不足 | 不改或只追加审计记录 |

### 修正原则

- 旧理解不删除，只改变状态、置信度、稳定度和层级。
- 亲历证据比传言强；高置信度证据比低置信度证据强。
- `stability` 高的理解不容易被单次普通事件推翻，但可以被标记为 `contested`。
- 核心理解被反复反驳时，不要立即消失，而应表现为犹豫、辩解、试探、矛盾行为。
- 被替代的理解仍可在压力、创伤或旧关系被触发时短暂回潮。

### 简化修正公式

```text
evidence_strength =
  新事件相关性 * 新理解置信度 * 新理解重要性 * 来源可靠度

supports:
  confidence += evidence_strength * (1 - confidence) * 0.6
  stability += evidence_strength * 0.2

weakens / contradicts:
  confidence -= evidence_strength * (1 - stability * 0.5)
  stability -= evidence_strength * 0.2

qualifies / reframes:
  confidence 小幅变化
  behavior_effect 必须更新
  revision_status 可能变为 contested
```

## 记忆分层规则

记忆分层不是简单按新旧排序，而是综合计算。

### 推荐评分

```text
recency_score = 1 / (1 + turns_since_last_recalled / half_life_turns)
recall_score = min(1, log2(1 + recall_count) / 4)
emotion_score = abs(emotional_valence) / 2

memory_score =
  importance * 0.35 +
  salience * 0.20 +
  recency_score * 0.15 +
  recall_score * 0.15 +
  emotion_score * 0.10 +
  confidence * 0.05
```

### 层级含义

| tier | 条件 | 用途 |
| --- | --- | --- |
| `core` | 分数 >= 0.78，或被手动钉住 | 身份核心、重大创伤、救命恩情、长期目标，几乎总能影响行动 |
| `active` | 分数 >= 0.48 | 当前场景或近期会用到，优先放进上下文 |
| `dormant` | 分数 >= 0.22 | 不主动加载，但相关实体出现时可被唤起 |
| `archive` | 分数 < 0.22 | 只保留审计和极少数深度检索，不主动影响行动 |

## 回忆次数机制

当某条记忆被用于以下任一情况时，增加 `recall_count` 并更新 `last_recalled_turn`：

- 影响 NPC 对玩家的态度。
- 影响 NPC 的行动计划。
- 被 NPC 在对话中提及。
- 被 GM 用来判断 NPC 是否知道某个秘密。
- 被用来解释 NPC 为什么撒谎、回避、帮助或背叛。

不要因为“检索出来但没用”就增加回忆次数。

## 事件理解与稳定理解

每个 NPC 在事件后可以产生自己的“事件理解”。同一事件对不同 NPC 的意义不同：

- 玩家拔剑保护米拉：米拉可能理解为“这个人愿意冒险保护我”；黑灯会成员可能理解为“玩家正在干涉交易”。
- 玩家沉默旁观：米拉可能理解为“此人不值得托付”；旁观水手可能理解为“外乡人懂规矩”。

事件理解不等于真相。它是 NPC 的主观解释，所以必须保留 `confidence`、`source`、`possible_misunderstanding` 和证据链。

多个事件理解会沉淀成稳定理解：

```text
事件 A：玩家付钱买情报，没有压价。
事件 B：玩家没有当众说出米拉的秘密。
事件 C：玩家在黑灯会靠近时提醒米拉躲避。

稳定理解：玩家重视交易信用，暂时值得低风险合作。
```

稳定理解也不是永恒真理。后续反证会降低它的置信度或生成竞争理解：

```text
反证事件：玩家把米拉的藏身处告诉黑灯会。
更新：旧理解降级；新理解“玩家会在高压下出卖我”进入 active。
```

处理这个步骤时使用 `prompts/understanding-reviser.md`。

## 写入新记忆的标准

满足任一条件就应该写入：

- NPC 亲眼见到玩家的重要行动。
- NPC 听到可信或有用的传言。
- NPC 的目标、恐惧、关系、利益发生变化。
- 玩家做出救助、欺骗、威胁、背叛、交易、承诺。
- 某个秘密被揭露、误解、证伪或传播。
- NPC 因事件形成新计划。

## 其他功能同样图谱化

不仅 NPC 记忆要这样做，以下内容也应保留结构化状态：

- 任务图谱：任务、线索、阻碍、倒计时、后果。
- 关系图谱：信任、敌意、债务、恐惧、把柄。
- 地点图谱：可互动特征、已破坏物件、隐藏通道、控制者。
- 物品图谱：所有权、来源、状态、秘密属性。
- 阵营图谱：目标、资源、敌友关系、正在执行的计划。
- 传言图谱：来源、传播路径、真假状态、相信者列表。

## GM 隐藏输出建议

每回合给玩家正文后，内部应该形成以下隐藏记录：

```json
{
  "turn_id": 1,
  "visible_summary": "玩家看见和做了什么",
  "hidden_state_patch": {},
  "npc_memory_updates": [],
  "quest_updates": [],
  "relationship_updates": [],
  "next_pressures": []
}
```

如果是在纯聊天里跑团，隐藏记录可以写入本地文件，不必全部展示给玩家。
