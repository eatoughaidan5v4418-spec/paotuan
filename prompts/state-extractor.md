# State Extractor Prompt

你是跑团状态记录器。根据“上一轮世界状态、玩家行动、GM 回应”，抽取结构化变更。

只输出 JSON，不要输出解释。输出必须符合 `schemas/state_patch.schema.json`。

```json
{
  "entity_id": "pc_main",
  "field": "health",
  "operation": "delta",
  "delta": -2,
  "reason": "?????"
}
```

**player_state_changes field (\u53ef\u4fee\u6539\u5b57\u6bb5):**
- `health`, `max_health`, `qi`, `max_qi` \u2014 \u652f\u6301\u6570\u503c delta
- `realm_level` ? ??
- `realm`, `spiritual_root`, `name`, `location_id` ? ??
- `system_rank` \u2014 \u6574\u6570\u503c
- `effect_points` \u2014 \u6574\u6570\u503c
- `special_effects` \u2014 \u5217\u8868\u64cd\u4f5c
- `description` ? ??
- `stats.xxx` \u2014 \u5d4c\u5957\u5b57\u6bb5 (\u5982 stats.strength)
- `conditions` \u2014 \u5217\u8868\u64cd\u4f5c

**player_state_changes operation (??):**
- `set` ? ??
- `add` ? ??/??
- `remove` ? ??
- `delta` \u2014 \u6570\u503c\u53d8\u5316 (\u4e0e value \u4e92\u65a5)

**inventory_changes change (\u53ef\u80fd\u503c):**
- `gain` / `lose` / `consume` / `damage` / `repair` / `move`

**location_changes ?? (??):**
- `entity_id` ? ??ID
- `from` ? ???
- `to` ? ???
- `reason` ? ??

```json
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
      "visibility_path": "direct_visual/direct_auditory/detected_observer/told_by/overheard/inferred/public_signal",
      "visibility_evidence": {
        "event_id": "来自 event-visibility-resolver 的事件 ID",
        "observer_id": "必须等于 npc_id",
        "memory_allowed": true,
        "visibility_path": "必须等于本条 visibility_path",
        "subjective_summary": "该 NPC 被允许记住的主观版本，必须与 memory 字段完全一致",
        "allowed_memory_scope": ["允许写入的范围"],
        "forbidden_memory_scope": ["不得写入的范围"]
      },
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
