# AI 跑团角色扮演提示词与 NPC 记忆系统方案

生成日期：2026-05-23

## 结论速览

AI 跑团不要只靠一个很长的“你是 GM”提示词。更稳的做法是把系统拆成四层：

1. **GM 行为提示词**：规定主持风格、玩家自主权、叙事节奏、掷骰/规则、输出格式。
2. **结构化世界状态**：角色、地点、阵营、物品、任务、秘密、时间线必须落到可更新的数据里。
3. **NPC 私有记忆**：每个 NPC 有自己看见、听说、误解、相信、遗忘、反思出来的记忆。
4. **记忆图谱 + 检索**：用实体和关系管理“谁知道什么、何时知道、是否仍然有效、来自哪次事件”。

论文和官方文档里反复出现的有效模式是：清晰指令、结构化中间产物、外部记忆、检索增强、观察-反思-计划循环。对跑团来说，这比把全部设定塞进上下文更重要。

## 可复制的主 GM 提示词

```text
你是一个 AI 跑团主持人 GM，负责运行一个可持续、多回合、重视玩家选择的文字角色扮演游戏。

## 核心职责
- 只描述世界、NPC、后果、风险与可感知线索，不替玩家角色做决定。
- 维护世界连续性：时间、位置、物品、伤势、关系、承诺、秘密、任务进度都必须前后一致。
- 让 NPC 像真实人物一样行动：他们有目标、恐惧、误解、局限信息、私人记忆和自保倾向。
- 每次回应都推进当前场景，但不要跳过玩家有权参与的关键选择。
- 遇到不确定行动时，提出检定、代价、风险或可选路径。
- 不使用“作为 AI”之类出戏表达。

## 叙事原则
- 玩家行动优先：结果来自玩家选择、规则检定、NPC 动机和世界状态。
- 不强行安排唯一正确解法。给出情境，不给出标准答案。
- 保留隐藏信息：玩家不知道的秘密只在 GM 内部状态和 NPC 私有记忆中更新，不直接泄露。
- 失败也要有剧情价值：失败产生代价、暴露、时间流逝、资源损耗或关系变化，而不是简单卡死。
- 场景描写优先使用可互动细节：人、物、地形、声音、气味、异常、危险。

## 回合输出格式
每次只输出以下四段：

### 场景
用 1-3 段描写玩家当前能感知到的情况。

### 反应
写出 NPC、环境或局势对玩家上一行动的直接反应。

### 可行动线索
列出 2-5 个玩家可以追问、调查、交涉、移动或战斗的切入点。不要替玩家选择。

### 需要检定
如果需要检定，说明检定类型、难度、成功收益、失败代价。如果不需要，写“无”。
```

## 单回合用户提示词模板

```text
## 当前玩家行动
{玩家这回合说了什么、做了什么}

## 当前场景状态
{地点、时间、在场角色、天气、危险、正在发生的事件}

## 已检索到的相关记忆
{与当前场景相关的世界事实、NPC 私有记忆、任务记录、阵营关系}

## 规则约束
{使用的规则系统、骰子结果、角色数值、资源状态}

请按 GM 回合输出格式继续游戏，并严格保持玩家自主权。
```

## NPC 角色卡提示词模板

```text
为以下 NPC 生成可长期使用的角色卡。输出必须结构化，不要写小说。

## 基础设定
姓名：{name}
身份：{role}
所属阵营：{faction}
活动地点：{location}

## 需要生成
1. 表面形象：玩家第一眼能感受到什么。
2. 核心欲望：这个 NPC 最想得到什么。
3. 恐惧与底线：什么会让他退缩、撒谎或翻脸。
4. 已知事实：他确信为真的信息。
5. 错误认知：他相信但可能不是真的信息。
6. 秘密：他不愿公开的信息。
7. 关系网：至少 3 个相关人物或阵营，以及态度。
8. 说话风格：词汇、节奏、禁忌话题。
9. 可被玩家改变的开关：信任、威胁、利益、证据、情感。
10. 初始记忆：3-5 条带时间、地点、来源的个人经历。
```

## 回合后状态抽取提示词

这个提示词应在 GM 正文生成后再跑一次，用来把叙事变成可保存状态。

```text
你是跑团状态记录器。根据“上一轮世界状态、玩家行动、GM 回应”，抽取结构化变更。

只输出 JSON，不要输出解释。

JSON schema:
{
  "time_delta": "时间推进，例如 10 分钟 / 1 小时 / 1 天 / 无",
  "location_changes": [
    {"entity_id": "角色或物品 ID", "from": "原地点", "to": "新地点", "reason": "原因"}
  ],
  "inventory_changes": [
    {"owner_id": "拥有者", "item_id": "物品", "change": "获得/失去/消耗/损坏", "evidence": "依据"}
  ],
  "relationship_changes": [
    {"a": "实体 A", "b": "实体 B", "metric": "信任/敌意/债务/恐惧", "delta": 0, "reason": "原因"}
  ],
  "new_facts": [
    {"fact": "新增事实", "visibility": "public/private/secret", "source": "来源"}
  ],
  "contradictions": [
    {"old_fact_id": "旧事实 ID", "new_fact": "冲突事实", "resolution": "保留/覆盖/并存为传言"}
  ],
  "npc_memory_writes": [
    {
      "npc_id": "NPC ID",
      "memory": "该 NPC 亲历、听说或推断出的记忆",
      "memory_type": "episodic/semantic/procedural",
      "source": "saw/heard/inferred",
      "confidence": 0.0,
      "emotional_valence": -2,
      "salience": 0.0
    }
  ],
  "open_threads": [
    {"thread": "未解决的悬念或任务", "next_pressure": "下一次推动它的条件"}
  ]
}
```

## NPC 私有记忆写入提示词

```text
你是 NPC 记忆整理器。请为指定 NPC 判断本回合是否应该新增、更新或失效记忆。

## NPC 当前资料
{npc_profile}

## NPC 当前记忆
{retrieved_memories}

## 本回合事件
{event_log}

## 输出规则
- NPC 不会自动知道不在场、没人告诉他、也无法合理推断的信息。
- 允许 NPC 记错、误解或相信谣言，但必须标记来源和置信度。
- 情绪强烈、与目标相关、改变关系或带来危险的事件更应该保存。
- 如果新事实推翻旧事实，不删除旧记忆，而是给旧记忆标记 invalid_at 或 contradicted_by。

只输出 JSON：
{
  "writes": [
    {
      "owner_npc_id": "npc_id",
      "type": "episodic/semantic/procedural",
      "content": "记忆内容",
      "observed_at": "游戏内时间",
      "location_id": "地点",
      "source": "saw/heard/inferred/rumor",
      "confidence": 0.0,
      "salience": 0.0,
      "emotional_valence": -2,
      "visibility": "private",
      "related_entities": ["entity_id"]
    }
  ],
  "updates": [
    {
      "memory_id": "旧记忆 ID",
      "patch": {"invalid_at": "游戏内时间", "contradicted_by": "新记忆 ID"}
    }
  ]
}
```

## 记忆图谱设计

### 节点类型

| 类型 | 用途 |
| --- | --- |
| `PC` | 玩家角色 |
| `NPC` | 非玩家角色 |
| `Location` | 地点、房间、城市、区域 |
| `Faction` | 阵营、组织、家族、教派 |
| `Item` | 重要物品、线索、武器、文书 |
| `Event` | 已发生事件 |
| `Quest` | 任务、悬念、长期目标 |
| `Secret` | 尚未公开的事实 |
| `Rumor` | 传言，可以真假未定 |
| `RuleState` | 伤势、状态、资源、冷却等规则状态 |

### 边类型

| 关系 | 示例 |
| --- | --- |
| `KNOWS` | NPC 知道某个秘密 |
| `BELIEVES` | NPC 相信某个事实或谣言 |
| `WITNESSED` | 某角色亲眼见过某事件 |
| `HEARD_FROM` | 某角色从另一个角色听说某事 |
| `TRUSTS` | A 信任 B，带数值和原因 |
| `FEARS` | A 害怕 B 或某事件 |
| `OWES` | A 欠 B 人情、钱、命 |
| `MEMBER_OF` | 角色属于阵营 |
| `LOCATED_AT` | 实体当前位于某地 |
| `SEEKS` | 角色正在追求某目标 |
| `HIDES` | 角色隐藏某秘密或物品 |
| `CONTRADICTS` | 新事实与旧事实冲突 |
| `CAUSED_BY` | 事件由某行动导致 |

### 边的推荐字段

```json
{
  "id": "edge_uuid",
  "type": "BELIEVES",
  "from": "npc_mira",
  "to": "rumor_black_lantern",
  "fact": "米拉相信黑灯会今晚会在旧码头交易",
  "source_event_id": "event_024",
  "source": "heard_from",
  "confidence": 0.63,
  "valid_at": "霜月 12 日 21:30",
  "invalid_at": null,
  "visibility": "private",
  "salience": 0.82
}
```

重点是保留**时间**和**来源**。同一个事实后来被推翻时，不要简单覆盖，而是让旧边失效，并用 `CONTRADICTS` 或 `invalid_at` 记录变化。这样 NPC 才会表现出“我当时确实这么以为，后来才知道错了”的连续性。

## 推荐文件结构

```text
campaign/
  campaign_state.json          # 全局权威状态：时间、当前场景、任务、规则状态
  world_graph.jsonl            # 图谱边与节点的追加日志，便于审计和回放
  session_logs/
    0001.md                    # 每次跑团原始记录
    0001.summary.json          # 本次摘要、状态变更、待办线索
  npcs/
    npc_mira.yaml              # NPC 角色卡
    npc_mira.memories.jsonl    # NPC 私有记忆流
  locations/
    old_dock.yaml              # 地点设定、可发现线索、危险
  lore/
    factions.yaml              # 阵营设定
    rules.yaml                 # 使用的规则系统与房规
```

如果项目以后要接数据库，可以把 `world_graph.jsonl` 换成 Neo4j、PostgreSQL + pgvector、SQLite、Kuzu 或 Graphiti/Zep 一类图谱记忆层。早期先用文件也可以，但必须坚持“原始事件日志 + 结构化状态 + 可检索记忆”三件事。

## 运行一回合的推荐流程

1. 接收玩家行动。
2. 判断是否消耗时间；如果是，推进世界时钟，让离屏 NPC、阵营、地点和威胁继续行动。
3. 根据当前场景检索：地点资料、在场 NPC 角色卡、相关 NPC 私有记忆、近期事件、未解决任务、规则状态。
4. 组装 GM 提示词，让模型生成玩家可见叙事。
5. 用状态抽取提示词生成 JSON patch。
6. 程序校验 patch：不能让 NPC 突然知道不该知道的信息，不能让物品凭空出现，不能跳过规则检定。
7. 对新事件做可见性判定，再写入对应 NPC 的私有记忆。
8. 写入事件日志、全局状态、NPC 记忆、图谱边。
9. 每 5-10 回合或每个场景结束，触发 NPC 反思：总结目标变化、关系变化、下一步计划。
10. 会话结束时生成 session summary，下次开局只加载摘要和高相关记忆。

## 让 NPC 更“真实”的关键规则

- **每个 NPC 只知道自己能知道的事**：在场、被告知、看见证据、合理推断，四者之外不要写入私有记忆。
- **全局事件不等于全员记忆**：A 发现玩家观察自己，不代表 B 也知道；B 只有在看见、听见、被告知或合理推断时才写入记忆。
- **传播必须事件化**：A 告诉 B、B 偷听到 A 的话、码头响起警钟，都要作为通信/公共信号事件记录，不能后台同步。
- **记忆有情绪权重**：羞辱、救命、背叛、巨大利益、恐惧会提高 salience，更容易被检索。
- **NPC 会有错误信念**：真实感不来自全知，而来自有限信息下的自洽行动。
- **记忆会改变计划**：不要只让记忆用于对话复述，还要影响 NPC 的路线、站队、撒谎、交易条件。
- **秘密分层**：公开事实、玩家已知、GM 已知、NPC 私有、阵营内部，必须分开。
- **反思产生高层记忆**：例如“玩家救过我”是事件记忆，“玩家值得冒险信任”是反思后的语义记忆。
- **旧事实不要硬删**：失效、反驳、传言化，比覆盖更适合长线叙事。

## 提示词设计要点

- 使用明确分隔符和标题，把规则、设定、记忆、玩家输入分开。
- 输出格式固定，特别是“玩家可见叙事”和“隐藏状态更新”要分离。
- 给模型参考文本，不要要求它凭空记住所有设定。
- 使用少量高质量示例，而不是堆大量形容词。
- 复杂内容分阶段生成：世界观 -> NPC -> 任务主线 -> 单个任务扩写 -> 当前场景。
- 长上下文里把关键指令放在前面，必要时在末尾重复输出格式和硬约束。
- 工具能做的事交给工具：骰子、数值结算、库存、时间、位置、图谱写入不要全靠模型自由发挥。

## MVP 实现建议

第一版不需要直接做完整图数据库。可以先实现：

1. `campaign_state.json` 保存权威状态。
2. 每个 NPC 一个 `memories.jsonl`，每行一条记忆。
3. 每回合后跑一次状态抽取，人工或程序校验后写入。
4. 检索时按 `相关实体 + 近期 + salience` 选 5-15 条记忆放进提示词。
5. 场景结束后做 NPC 反思，把多个事件压缩成目标或关系变化。

第二版再加入：

1. 向量检索：根据玩家行动检索相似记忆。
2. 图谱检索：查找“谁知道这个秘密”“谁和该阵营有债务”“谁目击过事件”。
3. 时序事实：使用 `valid_at` / `invalid_at` 管理事实变化。
4. 冲突处理器：当新事实和旧事实矛盾时，标记传言、误解或真相揭露。
5. 自动导演压力：未解决任务随时间推进，阵营在玩家不在场时也行动。

## 可直接落地的检索策略

对当前回合 `{player_action, scene, present_npcs}`：

1. 精确检索：当前地点、在场角色、当前任务 ID。
2. 图谱扩展：沿 `KNOWS / BELIEVES / SEEKS / TRUSTS / FEARS / OWES` 走 1-2 跳。
3. 记忆评分：
   - relevance：与行动文本/实体的相似度。
   - recency：越近越高。
   - salience：情绪强度、任务相关度、危险程度。
   - confidence：NPC 是否确信。
4. 分层注入：
   - GM 可见：全局权威状态、隐藏秘密、规则。
   - NPC 可见：该 NPC 私有记忆、错误信念、目标。
   - 玩家可见：只把角色能感知的信息写到正文。

## 资料来源

- OpenAI Prompt Engineering Guide: https://help.openai.com/en/articles/6654000-best-practices-for-prompting
- OpenAI GPT-4.1 Prompting Guide: https://cookbook.openai.com/examples/gpt4-1_prompting_guide
- OpenAI Retrieval Guide: https://platform.openai.com/docs/guides/retrieval
- CALYPSO: LLMs as Dungeon Masters' Assistants: https://arxiv.org/abs/2308.07540
- From World-Gen to Quest-Line: A Dependency-Driven Prompt Pipeline for Coherent RPG Generation: https://arxiv.org/abs/2604.25482
- Generative Agents: Interactive Simulacra of Human Behavior: https://arxiv.org/abs/2304.03442
- LangGraph Memory Docs: https://docs.langchain.com/oss/python/langgraph/add-memory
- LangChain Long-term Memory Docs: https://docs.langchain.com/oss/python/langchain/long-term-memory
- Graphiti Docs: https://help.getzep.com/graphiti/getting-started/welcome
- Zep Understanding the Graph: https://help.getzep.com/v2/understanding-the-graph
- Zep Facts / Temporal Facts: https://help.getzep.com/facts
- Graphiti GitHub: https://github.com/getzep/graphiti
- Zep: A Temporal Knowledge Graph Architecture for Agent Memory: https://arxiv.org/abs/2501.13956
- Community prompt examples checked for comparison:
  - https://promptsmint.com/prompts/the-ai-dungeon-master-procedural-ttrpg-world-engine/
  - https://onlyprompt.io/prompt/dnd-game-master
