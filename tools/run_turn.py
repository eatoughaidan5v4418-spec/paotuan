#!/usr/bin/env python3
"""Prepare a complete local GM turn packet.

The runner does not call an LLM. It performs the deterministic orchestration:
load campaign state, preview living-world clock ticks, gather current scene and
NPC memory context, then write a turn packet that a GM model can consume.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from time_utils import sync_campaign_time, tick_to_display
from zone_validator import parse_zones, build_graph, find_los_path, find_sound_path


TIME_RE = re.compile(r"第\s*(\d+)\s*日\s*(\d{1,2}):(\d{2})")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return read_text(path)


def load_json(path: Path) -> Any:
    return json.loads(read_text(path))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_dict(value: Any, default: dict[str, Any] | None = None) -> dict[str, Any]:
    return value if isinstance(value, dict) else (default or {})


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def normalize_world_clocks(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        clocks = value.get("clocks", [])
        if isinstance(clocks, list):
            return {**value, "clocks": [clock for clock in clocks if isinstance(clock, dict)]}
        return {**value, "clocks": []}
    if isinstance(value, list):
        return {"clocks": [clock for clock in value if isinstance(clock, dict)]}
    return {"clocks": []}


def keyword_hits(text: str, haystack: str) -> int:
    words = {
        word.lower()
        for word in re.findall(r"[\w\u4e00-\u9fff]{2,}", text or "")
        if len(word.strip()) >= 2
    }
    lower = (haystack or "").lower()
    return sum(1 for word in words if word in lower)


def retrieve_active_lore(root: Path, campaign_state: dict[str, Any], player_action: str, limit: int = 8) -> list[dict[str, str]]:
    scene = as_dict(campaign_state.get("current_scene"))
    anchors = " ".join(
        [
            player_action or "",
            str(scene.get("location_id", "")),
            " ".join(str(item) for item in as_list(scene.get("present_entities"))),
            " ".join(str(item) for item in as_list(scene.get("active_threads"))),
        ]
    )
    candidates: list[dict[str, Any]] = []
    files = [
        root / "campaign" / "lore" / "world_lore.yaml",
        root / "campaign" / "lore" / "factions.yaml",
        root / "campaign" / "lore" / "rules.yaml",
        root / "campaign" / "player_knowledge.json",
        root / "campaign" / "quest_graph.json",
        root / "campaign" / "rumors.json",
    ]
    for path in files:
        text = read_text_if_exists(path)
        if not text.strip():
            continue
        chunks = re.split(r"\n(?=-\s+id:|[A-Za-z0-9_\u4e00-\u9fff-]+:)", text)
        if len(chunks) <= 1:
            chunks = [text]
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            score = keyword_hits(anchors, chunk)
            if score > 0:
                candidates.append({"source": str(path.relative_to(root)), "score": score, "text": chunk[:1600]})
    if not candidates:
        for path in files[:3]:
            text = read_text_if_exists(path).strip()
            if text:
                candidates.append({"source": str(path.relative_to(root)), "score": 0, "text": text[:1600]})
    candidates.sort(key=lambda item: (item["score"], len(item["text"])), reverse=True)
    return [
        {"source": item["source"], "reason": f"keyword_score={item['score']}", "text": item["text"]}
        for item in candidates[:limit]
    ]


def summarize_visible_text(visible: Any) -> str:
    if isinstance(visible, str):
        return visible[:700]
    if not isinstance(visible, dict):
        return ""
    parts = []
    for key in ("scene", "action_result", "world_motion", "tension"):
        if visible.get(key):
            parts.append(str(visible[key]))
    clues = visible.get("actionable_clues")
    if isinstance(clues, list) and clues:
        parts.append("可行动线索：" + "；".join(str(item) for item in clues[:4]))
    summary = visible.get("state_summary")
    if isinstance(summary, dict):
        for key in ("time", "memory", "quests"):
            if summary.get(key):
                parts.append(str(summary[key]))
    return "\n".join(parts)[:1400]


def load_recent_turn_history(root: Path, limit: int = 6) -> list[dict[str, str]]:
    ai_dir = root / "campaign" / "ai_runs"
    if not ai_dir.exists():
        return []
    history = []
    for path in sorted(ai_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            continue
        packet = as_dict(data.get("packet"))
        response = as_dict(data.get("ai_response"))
        action = str(packet.get("player_action", ""))
        if "[??]" in action or "????" in action:
            action = "（旧记录行动文本编码损坏）"
        state_patch = as_dict(data.get("state_patch"))
        patch_summary_parts = []
        loc_changes = state_patch.get("location_changes", [])
        if isinstance(loc_changes, list):
            for lc in loc_changes[:3]:
                if isinstance(lc, dict):
                    patch_summary_parts.append(f"{lc.get('entity_id','?')}: {lc.get('from','?')} -> {lc.get('to','?')}")
        inv_changes = state_patch.get("inventory_changes", [])
        if isinstance(inv_changes, list):
            for ic in inv_changes[:3]:
                if isinstance(ic, dict):
                    patch_summary_parts.append(f"??: {ic.get('change','?')} {ic.get('item_id','?')}")
        ps_changes = state_patch.get("player_state_changes", [])
        if isinstance(ps_changes, list) and ps_changes:
            patch_summary_parts.append(f"????: {len(ps_changes)}?")
        time_delta = state_patch.get("time_delta", "")
        if time_delta and time_delta not in ("无", "none", "0", ""):
            patch_summary_parts.insert(0, f"时间: +{time_delta}")

        history.append(
            {
                "turn_id": str(packet.get("turn_id") or path.stem),
                "player_action": action,
                "gm_summary": summarize_visible_text(response.get("visible_text")),
                "patch_summary": "; ".join(patch_summary_parts) if patch_summary_parts else "无重大变更",
                "artifact": str(path.relative_to(root)),
            }
        )
    return list(reversed(history))


def parse_game_time(value: str) -> int | None:
    match = TIME_RE.search(value or "")
    if not match:
        return None
    day = int(match.group(1))
    hour = int(match.group(2))
    minute = int(match.group(3))
    return (day - 1) * 1440 + hour * 60 + minute


def format_game_time(total_minutes: int) -> str:
    day = total_minutes // 1440 + 1
    minute_of_day = total_minutes % 1440
    hour = minute_of_day // 60
    minute = minute_of_day % 60
    return f"第 {day} 日 {hour:02d}:{minute:02d}"


def parse_interval_minutes(value: str) -> int | None:
    text = value or ""
    hour_match = re.search(r"(\d+)\s*小时", text)
    minute_match = re.search(r"(\d+)\s*分钟", text)
    total = 0
    if hour_match:
        total += int(hour_match.group(1)) * 60
    if minute_match:
        total += int(minute_match.group(1))
    if total:
        return total
    numeric_match = re.search(r"(\d+)", text)
    if numeric_match:
        return int(numeric_match.group(1))
    return None


def profile_path_for(root: Path, entity_id: str) -> Path:
    return root / "campaign" / "npcs" / f"{entity_id}.yaml"


def memory_graph_path_for(root: Path, entity_id: str) -> Path:
    return root / "campaign" / "npcs" / f"{entity_id}.memory_graph.json"


def append_unique(values: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def location_initial_occupants(location_text: str) -> list[str]:
    try:
        data = yaml.safe_load(location_text) or {}
    except yaml.YAMLError:
        return []
    occupants: list[str] = []
    if not isinstance(data, dict):
        return occupants
    for zone in as_list(data.get("zones")):
        if not isinstance(zone, dict):
            continue
        for entity_id in as_list(zone.get("initial_occupants")):
            append_unique(occupants, entity_id)
    return occupants


def mentioned_npc_ids(player_action: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\bnpc_[A-Za-z0-9_]+\b", player_action or "")))


def summarize_memory_graph(path: Path, limit: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "top_memories": [],
            "beliefs": [],
            "plans": [],
            "understandings": [],
        }

    graph = load_json(path)
    memories = graph.get("memory_nodes", [])
    memories = sorted(
        memories,
        key=lambda item: (
            item.get("tier") == "core",
            float(item.get("score", item.get("importance", 0))),
            int(item.get("recall_count", 0)),
        ),
        reverse=True,
    )
    understandings = sorted(
        graph.get("understanding_nodes", []),
        key=lambda item: (
            item.get("tier") == "core",
            float(item.get("importance", 0)),
            float(item.get("confidence", 0)),
        ),
        reverse=True,
    )
    return {
        "path": str(path),
        "exists": True,
        "top_memories": memories[:limit],
        "beliefs": graph.get("beliefs", [])[:limit],
        "plans": graph.get("plans", [])[:limit],
        "understandings": understandings[:limit],
        "revision_events": graph.get("revision_events", [])[-limit:],
    }


def advance_clock_preview(
    world_clocks: Any,
    from_minutes: int | None,
    to_minutes: int | None,
    reason: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    preview = normalize_world_clocks(copy.deepcopy(world_clocks))
    updates: list[dict[str, Any]] = []
    hints: list[str] = []
    if from_minutes is None or to_minutes is None or to_minutes <= from_minutes:
        return preview, updates, hints

    for clock in preview.get("clocks", []):
        if clock.get("status") != "active":
            continue

        next_tick = parse_game_time(clock.get("next_tick_at", ""))
        interval = parse_interval_minutes(clock.get("tick_interval", ""))
        if next_tick is None or interval is None or interval <= 0:
            continue

        old_value = int(clock.get("value", 0))
        max_value = int(clock.get("max_value", 1))
        tick_count = 0
        while next_tick <= to_minutes and old_value + tick_count < max_value:
            tick_count += 1
            next_tick += interval

        if tick_count <= 0:
            continue

        new_value = min(max_value, old_value + tick_count)
        clock["value"] = new_value
        clock["next_tick_at"] = format_game_time(next_tick)
        if new_value >= max_value:
            clock["status"] = "complete"

        update = {
            "clock_id": clock.get("id"),
            "owner_id": clock.get("owner_id"),
            "title": clock.get("title"),
            "old_value": old_value,
            "new_value": new_value,
            "max_value": max_value,
            "reason": reason,
            "visibility": clock.get("visibility", "secret"),
        }
        updates.append(update)
        clock.setdefault("recent_updates", []).append(update)

        if clock.get("on_complete") and new_value >= max_value:
            hints.append(f"{clock.get('title')}: {clock.get('on_complete')}")
        elif clock.get("stakes"):
            hints.append(f"{clock.get('title')}: {clock.get('stakes')}")

    return preview, updates, hints


def quest_clock_ids(quest: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    explicit = quest.get("clock_id")
    if explicit:
        append_unique(ids, explicit)
    quest_id = str(quest.get("id") or "")
    if quest_id.startswith("thread_"):
        append_unique(ids, "clock_" + quest_id.removeprefix("thread_"))
    if quest_id:
        append_unique(ids, "clock_" + quest_id)
    return ids


def sync_quest_countdowns_from_clocks(
    quest_graph: dict[str, Any],
    world_clocks: dict[str, Any],
) -> list[dict[str, Any]]:
    clocks_by_id = {
        str(clock.get("id")): clock
        for clock in as_list(world_clocks.get("clocks"))
        if isinstance(clock, dict) and clock.get("id")
    }
    updates: list[dict[str, Any]] = []
    for quest in as_list(quest_graph.get("quests")):
        if not isinstance(quest, dict):
            continue
        matched_clock = None
        for clock_id in quest_clock_ids(quest):
            if clock_id in clocks_by_id:
                matched_clock = clocks_by_id[clock_id]
                break
        if not matched_clock:
            continue
        old_ticks = quest.get("countdown_ticks")
        old_max = quest.get("countdown_max")
        new_ticks = matched_clock.get("value")
        new_max = matched_clock.get("max_value")
        if old_ticks == new_ticks and old_max == new_max:
            continue
        quest["clock_id"] = matched_clock.get("id")
        quest["countdown_ticks"] = new_ticks
        quest["countdown_max"] = new_max
        if matched_clock.get("status") == "complete" and quest.get("status") == "active":
            quest["status"] = "failed"
        updates.append(
            {
                "quest_id": quest.get("id"),
                "clock_id": matched_clock.get("id"),
                "old_ticks": old_ticks,
                "new_ticks": new_ticks,
                "old_max": old_max,
                "new_max": new_max,
            }
        )
    return updates


def collect_context(root: Path, campaign_state: dict[str, Any], memory_limit: int, player_action: str = "") -> dict[str, Any]:
    current_scene = as_dict(campaign_state.get("current_scene"))
    location_id = current_scene.get("location_id", "")
    location_path = root / "campaign" / "locations" / f"{location_id.removeprefix('loc_')}.yaml"
    if not location_path.exists() and location_id == "loc_old_dock":
        location_path = root / "campaign" / "locations" / "old_dock.yaml"
    location_text = read_text_if_exists(location_path)

    # V05 fix: parse spatial zones and compute visibility between entities
    spatial_context = {}
    if location_text.strip():
        try:
            zones, connections, _ = parse_zones(location_text)
            if zones and connections:
                graph = build_graph(connections)
                zone_ids = [str(z.get("id")) for z in zones if z.get("id")]
                # Determine player zone (first zone or from campaign state)
                player_zone = current_scene.get("player_zone", zone_ids[0] if zone_ids else None)
                # Find which NPCs in which zones can see/hear each other
                npc_zones = {}
                for zone in zones:
                    for occ in zone.get("initial_occupants", []):
                        npc_zones[str(occ)] = str(zone.get("id"))
                spatial_context = {
                    "player_zone": player_zone,
                    "zone_count": len(zones),
                    "zone_ids": zone_ids,
                    "npc_zones": npc_zones,
                }
                # Per-NPC visibility from player zone
                if player_zone:
                    los_map = {}
                    sound_map = {}
                    for npc_id, npc_zone in npc_zones.items():
                        los = find_los_path(player_zone, npc_zone, zones, connections)
                        sound = find_sound_path(player_zone, npc_zone, zones, connections)
                        los_map[npc_id] = los.get("ok", False)
                        sound_map[npc_id] = sound.get("sound", "blocked") if sound.get("ok") else "blocked"
                    spatial_context["player_los_to_npc"] = los_map
                    spatial_context["player_sound_to_npc"] = sound_map
        except Exception:
            spatial_context = {"error": "zone parsing failed"}

    present_entities = current_scene.get("present_entities", [])
    if not isinstance(present_entities, list):
        present_entities = [present_entities]
    present_entities = [str(entity_id) for entity_id in present_entities if str(entity_id or "").strip()]

    world_clocks_path = root / "campaign" / "world_clocks.json"
    world_clocks = normalize_world_clocks(load_json(world_clocks_path) if world_clocks_path.exists() else {"clocks": []})
    active_clocks = [
        clock
        for clock in world_clocks.get("clocks", [])
        if clock.get("status") == "active"
        and (
            clock.get("location_id") == location_id
            or clock.get("owner_id") in present_entities
            or clock.get("id") in current_scene.get("active_threads", [])
        )
    ]

    relevant_entities: list[str] = []
    relevance_reasons: dict[str, list[str]] = {}

    def add_relevant(entity_id: Any, reason: str) -> None:
        text = str(entity_id or "").strip()
        if not text:
            return
        append_unique(relevant_entities, text)
        relevance_reasons.setdefault(text, [])
        if reason not in relevance_reasons[text]:
            relevance_reasons[text].append(reason)

    for entity_id in present_entities:
        add_relevant(entity_id, "present_in_current_scene")
    for entity_id in location_initial_occupants(location_text):
        add_relevant(entity_id, "listed_in_location_zone")
    for entity_id in mentioned_npc_ids(player_action):
        add_relevant(entity_id, "mentioned_in_player_action")
    for clock in active_clocks:
        owner_id = str(clock.get("owner_id") or "")
        if owner_id.startswith("npc_"):
            add_relevant(owner_id, f"active_clock:{clock.get('id')}")

    present_npcs = []
    for entity_id in relevant_entities:
        profile_path = profile_path_for(root, entity_id)
        graph_path = memory_graph_path_for(root, entity_id)
        if not profile_path.exists() and not graph_path.exists():
            continue
        present_npcs.append(
            {
                "id": entity_id,
                "relevance_reasons": relevance_reasons.get(entity_id, []),
                "profile_path": str(profile_path),
                "profile_text": read_text_if_exists(profile_path),
                "memory_graph": summarize_memory_graph(graph_path, memory_limit),
            }
        )

    resources_data = {}
    resources_path = root / "campaign" / "resources.json"
    if resources_path.exists():
        try:
            with open(resources_path, "r", encoding="utf-8-sig") as rf:
                raw_res = json.loads(rf.read())
            entities = raw_res.get("entities", raw_res) if isinstance(raw_res, dict) else {}
            if isinstance(entities, dict):
                for eid, data in entities.items():
                    if isinstance(data, dict):
                        resources_data[eid] = data
        except Exception:
            pass

    return {
        "location": {
            "id": location_id,
            "path": str(location_path),
            "text": location_text,
        },
        "present_entities": present_entities,
        "relevant_entities": relevant_entities,
        "present_npcs": present_npcs,
        "active_local_clocks": active_clocks,
        "active_lore": retrieve_active_lore(root, campaign_state, player_action),
        "recent_turn_history": load_recent_turn_history(root),
        "rules_text": read_text_if_exists(root / "campaign" / "lore" / "rules.yaml"),
        "factions_text": read_text_if_exists(root / "campaign" / "lore" / "factions.yaml"),
        "spatial_context": spatial_context,
        "player_resources": resources_data,
    }


def render_gm_input(packet: dict[str, Any], root: Path) -> str:
    gm_system = read_text_if_exists(root / "prompts" / "gm-system.md")
    context = packet["context"]
    npc_sections = []
    for npc in context.get("present_npcs", []):
        memory = npc.get("memory_graph", {})
        npc_sections.append(
            "\n".join(
                [
                    f"### {npc['id']}",
                    "",
                    "纳入原因：",
                    "```json",
                    json.dumps(npc.get("relevance_reasons", []), ensure_ascii=False, indent=2),
                    "```",
                    "",
                    "角色卡：",
                    "```yaml",
                    npc.get("profile_text", "").strip(),
                    "```",
                    "",
                    "高相关记忆/理解：",
                    "```json",
                    json.dumps(memory, ensure_ascii=False, indent=2),
                    "```",
                ]
            )
        )

    return "\n".join(
        [
            "# GM Turn Packet",
            "",
            "## GM System",
            "",
            gm_system.strip(),
            "",
            "## 当前玩家行动",
            "",
            packet["player_action"],
            "",
            "## 时间",
            "",
            f"- 当前回合：{packet['campaign_before'].get('current_turn')}",
            f"- 当前时间：{packet['time_preview']['from_time']}",
            f"- 预览推进到：{packet['time_preview']['to_time']}",
            f"- 消耗分钟：{packet['elapsed_minutes']}",
            "",
            "## 玩家角色",
            "",
            "```json",
            json.dumps(packet["campaign_before"].get("player_characters", []), ensure_ascii=False, indent=2),
            "```",
            "",
            "## 玩家资源",
            "",
            "```json",
            json.dumps(context.get("player_resources", {}), ensure_ascii=False, indent=2),
            "```",
            "",
            "## 当前场景状态",
            "",
            "```json",
            json.dumps(packet["campaign_before"].get("current_scene", {}), ensure_ascii=False, indent=2),
            "```",
            "",
            "## 地点资料",
            "",
            "```yaml",
            context.get("location", {}).get("text", "").strip(),
            "```",
            "",
            "## 世界 Tick 预览",
            "",
            "```json",
            json.dumps(packet["world_tick_preview"], ensure_ascii=False, indent=2),
            "```",
            "",
            "## 在场 / 本回合相关 NPC 与私有记忆",
            "",
            "\n\n".join(npc_sections) if npc_sections else "无",
            "",
            "## 规则约束",
            "",
            "```yaml",
            context.get("rules_text", "").strip(),
            "```",
            "",
            "## 阵营资料",
            "",
            "```yaml",
            context.get("factions_text", "").strip(),
            "```",
            "",
            "## 本回合触发的世界信息 / Lorebook",
            "",
            "```json",
            json.dumps(context.get("active_lore", []), ensure_ascii=False, indent=2),
            "```",
            "",
            "## 最近历史对话 / Chat History",
            "",
            "```json",
            json.dumps(context.get("recent_turn_history", []), ensure_ascii=False, indent=2),
            "```",
            "",
            "## 回合后必须执行",
            "",
            "1. 对玩家行动和离屏事件做可见性判定。",
            "2. 只给允许知道的 NPC 写入记忆。",
            "3. 为重要事件抽取 NPC 主观理解。",
            "4. 检查新理解是否修正旧稳定理解。",
            "5. 输出玩家可见正文时不要泄露 GM 隐藏信息。",
        ]
    )


def append_session_log(root: Path, session_id: str, packet: dict[str, Any], md_path: Path) -> None:
    log_path = root / "campaign" / "session_logs" / f"{session_id}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = "\n".join(
        [
            "",
            f"## {packet['turn_id']} prepared",
            "",
            f"- 玩家行动：{packet['player_action']}",
            f"- 时间预览：{packet['time_preview']['from_time']} -> {packet['time_preview']['to_time']}",
            f"- 回合包：{md_path}",
            "",
        ]
    )
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(entry)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a one-click GM turn packet.")
    parser.add_argument("--player-action", help="The player's action for this turn.")
    parser.add_argument("--action-file", type=Path, help="Read the player action from a UTF-8 text file.")
    parser.add_argument("--elapsed-minutes", type=int, default=0, help="In-game minutes consumed by this action.")
    parser.add_argument("--memory-limit", type=int, default=6, help="Number of memories/understandings to include per NPC.")
    parser.add_argument("--session-id", default="0001")
    parser.add_argument("--write", action="store_true", help="Write the packet to campaign/turn_packets and append session log.")
    parser.add_argument(
        "--commit-world-tick",
        action="store_true",
        help="Also write world clock preview and campaign time/turn back to disk. (Default: auto when elapsed-minutes > 0)",
    )
    parser.add_argument(
        "--no-commit-world-tick",
        action="store_true",
        help="Skip writing world clock advancement even when time passes.",
    )
    args = parser.parse_args()

    root = Path.cwd()
    if args.action_file:
        player_action = read_text(args.action_file).strip()
    else:
        player_action = (args.player_action or "").strip()
    if not player_action:
        raise SystemExit("Provide --player-action or --action-file.")

    campaign_path = root / "campaign" / "campaign_state.json"
    clocks_path = root / "campaign" / "world_clocks.json"
    campaign_state = load_json(campaign_path)
    world_clocks = load_json(clocks_path)

    current_turn = int(campaign_state.get("current_turn", 1))
    turn_id = f"turn_{current_turn:04d}"
    from_time = campaign_state.get("current_time", "")
    from_minutes = parse_game_time(from_time)
    to_minutes = None if from_minutes is None else from_minutes + args.elapsed_minutes
    to_time = from_time if to_minutes is None else format_game_time(to_minutes)

    tick_reason = f"{turn_id}: player action consumed {args.elapsed_minutes} minutes"
    clocks_preview, clock_updates, event_hints = advance_clock_preview(
        world_clocks,
        from_minutes,
        to_minutes,
        tick_reason,
    )

    # V09: run chaos scene check and include in turn packet
    chaos_info = {"enabled": False}
    try:
        chaos_path = root / "campaign" / "chaos_factor.json"
        if chaos_path.exists():
            chaos_data = load_json(chaos_path)
            from chaos_manager import scene_check
            result, roll = scene_check(int(chaos_data.get("chaos_level", 5)))
            chaos_info = {
                "enabled": True,
                "chaos_level": chaos_data.get("chaos_level", 5),
                "scene_check_roll": roll,
                "scene_check_result": result,
            }
    except Exception:
        pass

    context = collect_context(root, campaign_state, args.memory_limit, player_action)
    packet: dict[str, Any] = {
        "turn_id": turn_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "player_action": player_action,
        "elapsed_minutes": args.elapsed_minutes,
        "campaign_before": {
            "current_turn": campaign_state.get("current_turn"),
            "current_time": campaign_state.get("current_time"),
            "current_scene": campaign_state.get("current_scene"),
            "quests": campaign_state.get("quests", []),
            "rules": campaign_state.get("rules", {}),
        },
        "time_preview": {
            "from_time": from_time,
            "to_time": to_time,
        },
        "chaos_scene_check": chaos_info,
        "world_tick_preview": {
            "clock_updates": clock_updates,
            "offscreen_event_hints": event_hints,
            "requires_visibility_resolution": bool(clock_updates),
        },
        "context": context,
        "gm_input_markdown": "",
        "next_steps": [
            "Send gm_input_markdown to the GM model or use it directly as the GM context.",
            "After producing GM narration, run state extraction and event visibility resolution.",
            "Write only permitted memories to each NPC memory graph.",
            "Apply accepted state patches with a dedicated patch applier.",
        ],
    }
    packet["gm_input_markdown"] = render_gm_input(packet, root)

    if args.write:
        output_dir = root / "campaign" / "turn_packets"
        json_path = output_dir / f"{turn_id}.json"
        md_path = output_dir / f"{turn_id}.md"
        save_json(json_path, packet)
        md_path.write_text(packet["gm_input_markdown"] + "\n", encoding="utf-8")
        append_session_log(root, args.session_id, packet, md_path)
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
    else:
        print(packet["gm_input_markdown"])

    # V01 fix: auto-commit world tick when time passes (unless explicitly disabled)
    should_commit_world_tick = (
        args.commit_world_tick
        or (args.elapsed_minutes > 0 and not args.no_commit_world_tick)
    )
    if should_commit_world_tick:
        world_clocks_committed = clocks_preview
        world_clocks_committed["current_turn"] = current_turn + 1
        save_json(clocks_path, world_clocks_committed)
        quest_updates: list[dict[str, Any]] = []
        quest_path = root / "campaign" / "quest_graph.json"
        if quest_path.exists():
            quest_graph = load_json(quest_path)
            if isinstance(quest_graph, dict):
                quest_updates = sync_quest_countdowns_from_clocks(quest_graph, world_clocks_committed)
                if quest_updates:
                    save_json(quest_path, quest_graph)
        campaign_state["current_turn"] = current_turn + 1
        if to_minutes is not None:
            campaign_state["_time_tick"] = to_minutes
        campaign_state["current_time"] = to_time
        sync_campaign_time(campaign_state)
        save_json(campaign_path, campaign_state)
        print(f"Committed world tick to {clocks_path}")
        if quest_updates:
            print(f"Synced quest countdowns in {quest_path}")
        print(f"Committed campaign time to {campaign_path}")


if __name__ == "__main__":
    main()

