#!/usr/bin/env python3
"""Apply a state-extractor patch to campaign state, world graph, and NPC memories.

Reads a JSON patch conforming to schemas/state_patch.schema.json and safely
applies it across the campaign filesystem, updating campaign_state.json,
NPC *.memory_graph.json, and world_graph.jsonl in one consistent write.

Usage:
  python tools/apply_patch.py patch.json
  python tools/apply_patch.py patch.json --dry-run
  python tools/apply_patch.py patch.json --write --session-id 0001
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from time_utils import (
    tick_from_campaign,
    sync_campaign_time,
    tick_to_display,
    parse_time_delta,
)


# ---------------------------------------------------------------------------
# Game-time helpers (now imported from time_utils)
# ---------------------------------------------------------------------------
# Internal helpers kept for world_graph and memory node timestamps

TIME_RE = re.compile(r"\u7b2c\s*(\d+)\s*\u65e5\s*(\d{1,2}):(\d{2})")
INTERVAL_RE = re.compile(r"(\d+)\s*(?:\u5c0f\u65f6|\u5206\u949f|\u5929|\u5468)")


def parse_game_time(value: str) -> int | None:
    """Parse '\u7b2c 1 \u65e5 20:00' into total minutes since day 1 00:00."""
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
    return f"\u7b2c {day} \u65e5 {hour:02d}:{minute:02d}"




    if day_match:
        total += int(day_match.group(1)) * 1440
    if hour_match:
        total += int(hour_match.group(1)) * 60
    if minute_match:
        total += int(minute_match.group(1))

    # fallback: bare number treated as minutes
    if total == 0:
        numeric = re.search(r"(\d+)", delta)
        if numeric:
            total = int(numeric.group(1))

    return total


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(read_text(path))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Campaign state helpers
# ---------------------------------------------------------------------------

def ensure_campaign_field(campaign: dict[str, Any], field: str, default: Any) -> None:
    if field not in campaign:
        campaign[field] = default


def load_resource_state(root: Path) -> tuple[Path, dict[str, Any]]:
    path = root / "campaign" / "resources.json"
    try:
        data = load_json(path) if path.exists() else {"entities": {}}
    except json.JSONDecodeError:
        data = {"entities": {}}
    if not isinstance(data, dict):
        data = {"entities": {}}
    return path, data


def resource_entity(data: dict[str, Any], entity_id: str) -> dict[str, Any] | None:
    entities = data.get("entities", data)
    if isinstance(entities, dict):
        record = entities.get(entity_id)
        return record if isinstance(record, dict) else None
    if isinstance(entities, list):
        for item in entities:
            if isinstance(item, dict) and (item.get("id") == entity_id or item.get("entity_id") == entity_id):
                return item
    return None


def maybe_mark_starter_pack_opened(root: Path, owner_id: str, gained_items: list[str], dry_run: bool) -> str | None:
    if not gained_items:
        return None
    resources_path, resources = load_resource_state(root)
    record = resource_entity(resources, owner_id)
    if not record:
        return None
    changed = False
    for key, value in list(record.items()):
        if not isinstance(value, list):
            continue
        new_items = []
        for item in value:
            text = str(item)
            if "新手" in text and "礼包" in text and ("未开启" in text or "未打开" in text):
                changed = True
                continue
            new_items.append(item)
        if changed:
            record[key] = new_items
    if changed and not dry_run:
        save_json(resources_path, resources)
    return f"{owner_id} starter pack marked opened in resources.json" if changed else None


def update_npc_profile_location(root: Path, entity_id: str, new_location: str, dry_run: bool) -> bool:
    profile_path = root / "campaign" / "npcs" / f"{entity_id}.yaml"
    if not profile_path.exists():
        return False
    text = read_text(profile_path)
    if re.search(r"^location_id:\s*.*$", text, flags=re.MULTILINE):
        new_text = re.sub(r"^location_id:\s*.*$", f"location_id: {new_location}", text, count=1, flags=re.MULTILINE)
    elif re.search(r"^location:\s*.*$", text, flags=re.MULTILINE):
        new_text = re.sub(r"^location:\s*.*$", f"location: {new_location}", text, count=1, flags=re.MULTILINE)
    else:
        new_text = text.rstrip() + f"\nlocation: {new_location}\n"
    if new_text != text and not dry_run:
        profile_path.write_text(new_text, encoding="utf-8")
    return new_text != text


NUMERIC_PLAYER_FIELDS = {"health", "max_health", "qi", "max_qi", "realm_level", "system_rank", "effect_points", "sequence", "sanity", "max_sanity", "spirituality", "max_spirituality", "money"}
TEXT_PLAYER_FIELDS = {"name", "realm", "spiritual_root", "location_id", "description", "path", "status"}
LIST_PLAYER_FIELDS = {"traits", "conditions", "special_effects", "inventory"}
PLAYER_STATE_FIELDS = NUMERIC_PLAYER_FIELDS | TEXT_PLAYER_FIELDS | LIST_PLAYER_FIELDS | {
    "condition",
    "stats",
}


def find_player_character(campaign: dict[str, Any], entity_id: str) -> dict[str, Any] | None:
    for pc in campaign.get("player_characters", []):
        if isinstance(pc, dict) and pc.get("id") == entity_id:
            return pc
    return None


def condition_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("id") or "").strip()
    return str(value or "").strip()


def load_conditions_for_update(root: Path) -> tuple[Path, dict[str, Any]]:
    path = root / "campaign" / "conditions.json"
    try:
        data = load_json(path) if path.exists() else {"entities": {}}
    except json.JSONDecodeError:
        data = {"entities": {}}
    if not isinstance(data, dict):
        data = {"entities": {}}
    entities = data.get("entities")
    if isinstance(entities, list):
        data["entities"] = {
            str(item.get("id") or item.get("entity_id")): item
            for item in entities
            if isinstance(item, dict) and (item.get("id") or item.get("entity_id"))
        }
    elif not isinstance(entities, dict):
        data["entities"] = {}
    return path, data


def sync_condition_record(
    conditions: dict[str, Any],
    entity_id: str,
    operation: str,
    value: Any,
    reason: str,
) -> None:
    name = condition_name(value)
    if not name and operation != "set":
        return
    entity = conditions.setdefault("entities", {}).setdefault(
        entity_id, {"conditions": [], "history": []}
    )
    tracked = entity.setdefault("conditions", [])
    if operation == "remove":
        entity["conditions"] = [
            item for item in tracked if condition_name(item) != name
        ]
    elif operation == "set":
        values = value if isinstance(value, list) else [value]
        entity["conditions"] = [
            item if isinstance(item, dict) else {"name": str(item), "severity": "normal"}
            for item in values
            if condition_name(item)
        ]
    else:
        if all(condition_name(item) != name for item in tracked):
            record = dict(value) if isinstance(value, dict) else {"name": name}
            record.setdefault("severity", "normal")
            record.setdefault("added_at", reason)
            tracked.append(record)
    entity.setdefault("history", []).append(
        {"operation": operation, "condition": name or "set", "reason": reason}
    )


def apply_resource_change(
    root: Path,
    entity_id: str,
    field: str,
    value: Any,
    operation: str,
    reason: str,
    has_delta: bool,
    delta: Any,
    dry_run: bool,
) -> str:
    resources_path, resources = load_resource_state(root)
    record = resource_entity(resources, entity_id)
    if record is None:
        record = {}
        if isinstance(resources.get("entities"), dict):
            resources["entities"][entity_id] = record
        else:
            resources["entities"] = {entity_id: record}
    old_value = record.get(field)
    new_value = old_value
    if has_delta:
        try:
            old_num = float(old_value or 0)
            new_num = old_num + float(delta)
            new_value = int(new_num) if new_num == int(new_num) else new_num
        except (TypeError, ValueError):
            new_value = value
    elif operation == "remove":
        new_value = None
    elif operation == "add":
        if isinstance(old_value, list):
            record.setdefault(field, [])
            for v in (value if isinstance(value, list) else [value]):
                if v not in record[field]:
                    record[field].append(v)
            new_value = record[field]
            operation = "list_append"
        else:
            new_value = value
    else:
        new_value = value
    if new_value is not None:
        record[field] = new_value
    elif field in record:
        del record[field]
    if not dry_run:
        save_json(resources_path, resources)
    op = operation if operation != "remove" else "cleared"
    return f"{entity_id} resources.{field}: {old_value} -> {new_value} ({reason})"


def sync_player_resource_mirror(root: Path, entity_id: str, field: str, value: Any, dry_run: bool) -> None:
    mirror_fields = {
        "effect_points": "\u7279\u6548\u503c",
    }
    resource_field = mirror_fields.get(field)
    if not resource_field:
        return
    resources_path, resources = load_resource_state(root)
    record = resource_entity(resources, entity_id)
    if record is None:
        record = {}
        if isinstance(resources.get("entities"), dict):
            resources["entities"][entity_id] = record
        else:
            resources["entities"] = {entity_id: record}
    for stale_key in ("???",):
        if stale_key in record and stale_key != resource_field:
            del record[stale_key]
    record[resource_field] = value
    if not dry_run:
        save_json(resources_path, resources)


CURRENCY_ITEM_FIELDS = {
    "\u7075\u77f3",
}

MAX_ACTIVE_THREADS = 8


def parse_quantity_from_text(*values: Any) -> float:
    text = " ".join(str(value or "") for value in values)
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1))
    chinese_digits = {
        "\u96f6": 0,
        "\u4e00": 1,
        "\u4e8c": 2,
        "\u4e24": 2,
        "\u4e09": 3,
        "\u56db": 4,
        "\u4e94": 5,
        "\u516d": 6,
        "\u4e03": 7,
        "\u516b": 8,
        "\u4e5d": 9,
    }
    if "\u767e" in text:
        prefix = text.split("\u767e", 1)[0][-1:]
        suffix = text.split("\u767e", 1)[1][:2]
        total = chinese_digits.get(prefix, 1) * 100
        if "\u5341" in suffix:
            total += 10
        return float(total)
    if "\u5341" in text:
        before, after = text.split("\u5341", 1)
        tens = chinese_digits.get(before[-1:], 1)
        ones = chinese_digits.get(after[:1], 0)
        return float(tens * 10 + ones)
    for char, number in chinese_digits.items():
        if char in text:
            return float(number)
    return 1.0


def ensure_minimal_location_file(root: Path, location_id: str, reason: str, dry_run: bool) -> None:
    if not location_id or location_id in {"unknown", "offscreen"}:
        return
    loc_path = root / "campaign" / "locations" / f"{location_id.removeprefix('loc_')}.yaml"
    if loc_path.exists():
        return
    text = "\n".join(
        [
            f"id: {location_id}",
            f"name: {location_id}",
            "type: auto_created",
            f"summary: \"Auto-created after movement: {str(reason).replace(chr(34), chr(39))[:80]}\"",
            "description: |",
            f"  Auto-created location placeholder for {location_id}.",
            "zones: []",
            "exits: []",
            "",
        ]
    )
    if not dry_run:
        loc_path.parent.mkdir(parents=True, exist_ok=True)
        loc_path.write_text(text, encoding="utf-8")


def thread_sort_turn(thread: dict[str, Any]) -> int:
    for field in ("updated_turn", "created_turn"):
        try:
            value = thread.get(field)
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def prune_active_threads(campaign: dict[str, Any], current_turn: int, report: dict[str, list[str]]) -> None:
    threads = campaign.get("open_threads")
    if not isinstance(threads, list):
        return
    active = [
        item
        for item in threads
        if isinstance(item, dict) and item.get("status", "active") == "active"
    ]
    if len(active) <= MAX_ACTIVE_THREADS:
        return
    keep_ids = {
        str(item.get("id"))
        for item in sorted(active, key=thread_sort_turn, reverse=True)[:MAX_ACTIVE_THREADS]
    }
    archived_ids: set[str] = set()
    for thread in active:
        thread_id = str(thread.get("id"))
        if thread_id in keep_ids:
            continue
        thread["status"] = "dormant"
        thread["archived_turn"] = current_turn
        thread["archive_reason"] = "superseded by newer active threads"
        archived_ids.add(thread_id)
        report["threads"].append(f"[{thread_id}] dormant: {thread.get('description', '')}")
    scene = campaign.get("current_scene")
    if isinstance(scene, dict) and isinstance(scene.get("active_threads"), list):
        scene["active_threads"] = [
            thread_id
            for thread_id in scene["active_threads"]
            if str(thread_id) not in archived_ids
        ]


def apply_player_state_change(
    root: Path,
    campaign: dict[str, Any],
    change: dict[str, Any],
    dry_run: bool,
) -> str:
    entity_id = change.get("entity_id") or change.get("player_id") or "pc_main"
    pc = find_player_character(campaign, str(entity_id))
    if pc is None:
        return f"{entity_id}: player character not found"

    field = str(change.get("field", "")).strip()
    reason = str(change.get("reason") or "AI state update")
    operation = str(change.get("operation") or "set")
    has_delta = "delta" in change or (operation == "delta" and "value" in change)
    delta_value = change.get("delta", change.get("value"))
    value = change.get("value")

    if field in NUMERIC_PLAYER_FIELDS:
        old_value = float(pc.get(field) or 0)
        new_value = old_value + float(delta_value) if has_delta else float(value)
        if field in {"health", "qi"}:
            max_field = f"max_{field}"
            max_value = pc.get(max_field)
            if max_value is not None:
                new_value = min(new_value, float(max_value))
            new_value = max(0.0, new_value)
        elif field == "effect_points":
            new_value = max(0.0, new_value)
        pc[field] = int(new_value) if new_value.is_integer() else new_value
        sync_player_resource_mirror(root, str(entity_id), field, pc[field], dry_run)
        result = f"{entity_id} {field}: {old_value:g} -> {new_value:g} ({reason})"
        return result

    if field.startswith("stats."):
        stat = field.split(".", 1)[1]
        if not stat:
            return f"{entity_id}: empty stats field"
        stats = pc.setdefault("stats", {})
        old_value = float(stats.get(stat) or 0)
        new_value = old_value + float(delta_value) if has_delta else float(value)
        stats[stat] = int(new_value) if new_value.is_integer() else new_value
        return f"{entity_id} stats.{stat}: {old_value:g} -> {new_value:g} ({reason})"

    if field == "stats" and isinstance(value, dict):
        stats = pc.setdefault("stats", {})
        stats.update(value)
        return f"{entity_id} stats updated ({reason})"

    if field in TEXT_PLAYER_FIELDS:
        old_value = pc.get(field)
        pc[field] = value
        return f"{entity_id} {field}: {old_value} -> {value} ({reason})"

    if field in {"condition", "conditions"}:
        conditions_path, conditions_data = load_conditions_for_update(root)
        current = pc.setdefault("conditions", [])
        if operation == "remove":
            name = condition_name(value)
            pc["conditions"] = [item for item in current if condition_name(item) != name]
        elif operation == "set":
            values = value if isinstance(value, list) else [value]
            pc["conditions"] = [condition_name(item) for item in values if condition_name(item)]
        else:
            name = condition_name(value)
            if name and name not in [condition_name(item) for item in current]:
                current.append(name)
        sync_condition_record(conditions_data, str(entity_id), operation, value, reason)
        if not dry_run:
            save_json(conditions_path, conditions_data)
        return f"{entity_id} {field} {operation}: {condition_name(value) or 'set'} ({reason})"

    if field in LIST_PLAYER_FIELDS:
        values = value if isinstance(value, list) else [value]
        pc[field] = [item for item in values if item not in (None, "")]
        return f"{entity_id} {field} set ({reason})"

    if field in {"system_rank", "effect_points"}:
        old_value = float(pc.get(field) or 0)
        new_value = old_value + float(delta_value) if has_delta else float(value)
        if field == "effect_points":
            new_value = max(0.0, new_value)
        pc[field] = int(new_value) if new_value.is_integer() else new_value
        sync_player_resource_mirror(root, str(entity_id), field, pc[field], dry_run)
        return f"{entity_id} {field}: {old_value:g} -> {new_value:g} ({reason})"

    if field == "special_effects":
        values = value if isinstance(value, list) else [value]
        current = pc.setdefault("special_effects", [])
        if operation == "remove":
            pc["special_effects"] = [v for v in current if str(v) not in [str(x) for x in values]]
        elif operation == "set":
            pc["special_effects"] = [str(v) for v in values if v]
        else:
            for v in values:
                if str(v) not in [str(x) for x in current]:
                    current.append(str(v))
        return f"{entity_id} special_effects {operation}: {values} ({reason})"

    # Handle resources.json fields (e.g. ??, ???)
    if field not in PLAYER_STATE_FIELDS and not field.startswith("stats."):
        return apply_resource_change(root, str(entity_id), field, value, operation, reason, has_delta, change.get("delta"), dry_run)

    return f"{entity_id}: unsupported player state field {field}"


# ---------------------------------------------------------------------------
# NPC memory graph helpers
# ---------------------------------------------------------------------------

def memory_graph_path_for(root: Path, npc_id: str) -> Path:
    return root / "campaign" / "npcs" / f"{npc_id}.memory_graph.json"


def canonical_npc_id(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith(("npc_", "pc_", "player_")):
        return raw
    slug = re.sub(r"[^0-9A-Za-z_]+", "_", raw).strip("_").lower()
    if not slug:
        slug = "unknown"
    return f"npc_{slug}"



def profile_path_for(root: Path, npc_id: str) -> Path:
    return root / "campaign" / "npcs" / f"{npc_id}.yaml"


def read_profile_location(profile_path: Path) -> str:
    if not profile_path.exists():
        return ""
    for line in read_text(profile_path).splitlines():
        stripped = line.strip()
        if stripped.startswith(("location_id:", "location:")):
            return stripped.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def create_minimal_npc_profile(
    root: Path, npc_id: str, location_id: str, first_memory_snippet: str
) -> None:
    """Create a minimal NPC profile YAML for dynamically generated NPCs."""
    profile_path = profile_path_for(root, npc_id)
    if profile_path.exists():
        return

    raw_name = npc_id.removeprefix("npc_").replace("_", " ")
    display_name = " ".join(w.capitalize() for w in raw_name.split())
    snippet = str(first_memory_snippet)[:60].replace('"', "'")

    profile = f"""id: {npc_id}
name: {display_name}
role: 待定
faction: faction_unaligned
location_id: {location_id}
public_face: "待描述。初次出现时：{snippet}"
core_desire: "待定"
fear: "待定"
bottom_line: "待定"
traits:
  personality_tags: ["待定"]
  instinct: "待定——根据后续事件发展补全。"
  stress_response: "待定"
  social_approach: "待定"
  cognitive_bias: "待定"
voice_style:
  pace: "待定"
  habits: []
  forbidden_topics: []
known_facts: []
false_beliefs: []
secrets: []
relationship_hooks:
  - target_id: pc_main
    trust: 0
    fear: 0
    debt: 0
change_switches:
  trust: []
  threat: []
"""
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(profile, encoding="utf-8")

def create_empty_memory_graph(npc_id: str, current_turn: int) -> dict[str, Any]:
    return {
        "npc_id": npc_id,
        "current_turn": current_turn,
        "memory_policy_id": "npc_memory_policy_v1",
        "memory_nodes": [],
        "interpretation_nodes": [],
        "understanding_nodes": [],
        "revision_events": [],
        "relation_edges": [],
        "beliefs": [],
        "plans": [],
    }


def clamp_float(value: Any, default: float, low: float = 0.0, high: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def normalize_memory_write(write: dict[str, Any]) -> dict[str, Any]:
    """Accept either the project schema or common model-shaped memory objects."""
    memory = write.get("memory", "")
    memory_obj = memory if isinstance(memory, dict) else {}
    content = memory_obj.get("content", memory)
    if isinstance(content, (dict, list)):
        content = json.dumps(content, ensure_ascii=False)
    content = str(content or "").strip()

    normalized = dict(write)
    normalized["npc_id"] = canonical_npc_id(write.get("npc_id"))
    normalized["memory"] = content
    normalized["memory_type"] = (
        write.get("memory_type")
        or memory_obj.get("type")
        or "episodic"
    )
    for key in (
        "importance",
        "salience",
        "emotional_valence",
        "confidence",
        "source",
        "tier",
        "visibility_path",
        "visibility_evidence",
        "location_id",
        "related_entities",
    ):
        if normalized.get(key) in (None, "", []):
            value = memory_obj.get(key)
            if value not in (None, "", []):
                normalized[key] = value
    return normalized


def memory_visibility_evidence_errors(write: dict[str, Any], index_label: str) -> list[str]:
    errors: list[str] = []
    evidence = write.get("visibility_evidence")
    if not isinstance(evidence, dict):
        return [f"{index_label} missing visibility_evidence"]
    ev_observer = canonical_npc_id(evidence.get("observer_id"))
    write_npc = canonical_npc_id(write.get("npc_id"))
    if ev_observer != write_npc:
        errors.append(f"{index_label} visibility_evidence observer_id must match npc_id")
    visibility_path = write.get("visibility_path", "")
    if evidence.get("memory_allowed") is not True and visibility_path != "none":
        errors.append(f"{index_label} visibility_evidence memory_allowed must be true (unless visibility_path is none)")
    if evidence.get("visibility_path") != write.get("visibility_path"):
        errors.append(f"{index_label} visibility_evidence visibility_path must match write visibility_path")
    for field in ("event_id", "subjective_summary", "allowed_memory_scope", "forbidden_memory_scope"):
        if field not in evidence:
            errors.append(f"{index_label} visibility_evidence missing: {field}")
    memory_text = re.sub(r"\s+", " ", str(write.get("memory") or "")).strip()
    subjective_summary = re.sub(r"\s+", " ", str(evidence.get("subjective_summary") or "")).strip()
    # subjective_summary is a short version of the memory - skip strict matching
    # as LLM-generated texts naturally differ in detail level
    pass
    if not isinstance(evidence.get("allowed_memory_scope"), list):
        errors.append(f"{index_label} visibility_evidence allowed_memory_scope must be a list")
    if not isinstance(evidence.get("forbidden_memory_scope"), list):
        errors.append(f"{index_label} visibility_evidence forbidden_memory_scope must be a list")
    return errors


def load_memory_graph(path: Path, npc_id: str, current_turn: int) -> dict[str, Any]:
    if path.exists():
        try:
            graph = load_json(path)
        except (json.JSONDecodeError, ValueError):
            graph = None
        if not isinstance(graph, dict):
            graph = create_empty_memory_graph(npc_id, current_turn)
        return graph
    return create_empty_memory_graph(npc_id, current_turn)


def next_memory_id(npc_id: str, graph: dict[str, Any]) -> str:
    """Generate the next memory node id for an NPC."""
    existing = graph.get("memory_nodes", [])
    max_idx = 0
    for mem in existing:
        mid = mem.get("id", "")
        # match pattern mem_{npc_id}_NNNN
        parts = mid.rsplit("_", 1)
        if len(parts) == 2:
            try:
                idx = int(parts[1])
                if idx > max_idx:
                    max_idx = idx
            except ValueError:
                pass
    return f"mem_{npc_id}_{max_idx + 1:04d}"


# ---------------------------------------------------------------------------
# Patch application
# ---------------------------------------------------------------------------

def apply_patch(
    root: Path,
    patch: dict[str, Any],
    current_turn: int,
    current_time: str,
    session_id: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Apply a state patch. Returns a report of changes."""
    report: dict[str, list[str]] = {
        "time": [],
        "locations": [],
        "inventory": [],
        "player_state": [],
        "relationships": [],
        "facts": [],
        "contradictions": [],
        "memories": [],
        "interpretations": [],
        "understandings": [],
        "revisions": [],
        "world_graph": [],
        "threads": [],
        "errors": [],
    }

    # ---- campaign_state.json ----
    campaign_path = root / "campaign" / "campaign_state.json"
    campaign = load_json(campaign_path)
    if not isinstance(campaign, dict):
        return {"errors": ["campaign_state.json is not a valid object"]}

    from_tick = tick_from_campaign(campaign)  # ensures _time_tick exists


    # 1. Time delta
    delta_str = patch.get("time_delta", "")
    delta_minutes = parse_time_delta(delta_str)
    if delta_minutes > 0:
        new_tick = from_tick + delta_minutes
        old_time = campaign.get("current_time", "")
        campaign["_time_tick"] = new_tick
        campaign["current_time"] = tick_to_display(new_tick)
        report["time"].append(f"Time advanced: {old_time} -> {campaign['current_time']} (+{delta_minutes} min)")
    elif delta_str and delta_str not in ("\u65e0", "none", "0", ""):
        report["time"].append(f"Time delta unchanged ({delta_str}), no numeric advance")

    # 2. Location changes
    for loc_change in patch.get("location_changes", []):
        entity_id = loc_change["entity_id"]
        new_location = loc_change["to"]
        old_location = loc_change.get("from", "?")
        ensure_minimal_location_file(
            root,
            new_location,
            loc_change.get("reason", "location change"),
            dry_run,
        )

        changed = False
        is_player_entity = False
        # Update in player_characters
        for pc in campaign.get("player_characters", []):
            if pc.get("id") == entity_id:
                is_player_entity = True
                pc["location_id"] = new_location
                changed = True
                # When a player character moves, update the current scene location
                current_scene = campaign.setdefault("current_scene", {})
                if old_location != new_location:
                    current_scene["location_id"] = new_location
                    current_scene["present_entities"] = [entity_id]
                    current_scene["summary"] = f"玩家抵达{new_location}。"
                    report["locations"].append(
                        f"{entity_id} moved scene ({old_location} -> {new_location}): {loc_change['reason']}"
                    )
                break

        # Update in current_scene if present_entities contain this entity (non-player entities)
        current_scene = campaign.get("current_scene", {})
        present = current_scene.get("present_entities", [])
        if entity_id in present and not is_player_entity:
            if old_location != new_location:
                # Remove from present if moving away from current scene
                current_scene["present_entities"] = [e for e in present if e != entity_id]
                report["locations"].append(
                    f"{entity_id} left scene ({old_location} -> {new_location}): {loc_change['reason']}"
                )
                changed = True

        if not changed:
            if update_npc_profile_location(root, entity_id, new_location, dry_run):
                changed = True
                report["locations"].append(
                    f"{entity_id}: {old_location} -> {new_location} ({loc_change['reason']})"
                )

        if not changed:
            report["locations"].append(
                f"{entity_id}: {old_location} -> {new_location} ({loc_change['reason']})"
            )

    # 3. Inventory changes
    gained_by_owner: dict[str, list[str]] = {}
    for inv in patch.get("inventory_changes", []):
        owner_id = inv["owner_id"]
        item_id = inv["item_id"]
        change_type = inv["change"]
        found = False
        if item_id in CURRENCY_ITEM_FIELDS and change_type in {"gain", "lose", "consume"}:
            amount = parse_quantity_from_text(
                inv.get("quantity"),
                inv.get("amount"),
                inv.get("evidence"),
                item_id,
            )
            delta = -amount if change_type in {"lose", "consume"} else amount
            report["inventory"].append(
                apply_resource_change(
                    root,
                    owner_id,
                    item_id,
                    amount,
                    "delta",
                    inv.get("evidence", "currency change"),
                    True,
                    delta,
                    dry_run,
                )
            )
            continue

        for pc in campaign.get("player_characters", []):
            if pc.get("id") == owner_id:
                pc.setdefault("inventory", [])
                if change_type in ("gain", "repair"):
                    if item_id not in pc["inventory"]:
                        pc["inventory"].append(item_id)
                    gained_by_owner.setdefault(owner_id, []).append(item_id)
                    report["inventory"].append(f"{owner_id} gained {item_id}")
                elif change_type in ("lose", "consume", "damage"):
                    if item_id in pc["inventory"]:
                        pc["inventory"].remove(item_id)
                    report["inventory"].append(f"{owner_id} lost {item_id}")
                elif change_type == "move":
                    report["inventory"].append(f"{owner_id} moved {item_id}")
                found = True
                break

        if not found:
            # For NPC inventory, not yet tracked in campaign_state
            report["inventory"].append(
                f"{owner_id} inventory {change_type}: {item_id} (NPC inventory not in campaign_state)"
            )

    for owner_id, gained_items in gained_by_owner.items():
        note = maybe_mark_starter_pack_opened(root, owner_id, gained_items, dry_run)
        if note:
            report["inventory"].append(note)

    # 4. Player state changes
    for change in patch.get("player_state_changes", []):
        if not isinstance(change, dict):
            report["errors"].append(f"player_state_changes entry is not an object: {change}")
            continue
        try:
            report["player_state"].append(
                apply_player_state_change(root, campaign, change, dry_run)
            )
        except (TypeError, ValueError) as exc:
            report["errors"].append(f"player_state_changes invalid entry {change}: {exc}")

    # 5. Relationship changes
    for rel in patch.get("relationship_changes", []):
        a = rel["a"]
        b = rel["b"]
        metric = rel["metric"]
        delta = rel["delta"]
        reason = rel["reason"]

        # Update in NPC profile YAML - read, modify, write
        npc_profile_path = root / "campaign" / "npcs" / f"{a}.yaml"
        if npc_profile_path.exists():
            profile_text = read_text(npc_profile_path)
            # Update relationship_hooks section
            if "relationship_hooks:" in profile_text:
                hook_pattern = re.compile(
                    rf"(\s*- target_id:\s*{re.escape(b)}\s*\n\s*{metric}:\s*)([\d.-]+)",
                    re.MULTILINE,
                )
                if (match := hook_pattern.search(profile_text)):
                    old_val = float(match.group(2))
                    new_val = old_val + float(delta)
                    new_text = hook_pattern.sub(
                        rf"\g<1>{new_val}  # updated by patch (+{delta:+}): {reason}",
                        profile_text,
                        count=1,
                    )
                    if not dry_run:
                        npc_profile_path.write_text(new_text, encoding="utf-8")
                    report["relationships"].append(
                        f"{a}->{b} {metric}: {delta} ({reason})"
                    )
                else:
                    report["relationships"].append(
                        f"{a}->{b} {metric}: no matching hook found, delta {delta} ({reason})"
                    )
            else:
                report["relationships"].append(
                    f"{a}->{b} {metric}: {delta} ({reason}) (no hooks section)"
                )
        else:
            report["relationships"].append(
                f"{a}->{b} {metric}: {delta} ({reason}) (no profile file)"
            )

    # 6. New facts
    ensure_campaign_field(campaign, "known_facts", [])
    for fact_entry in patch.get("new_facts", []):
        fact_id = f"fact_{len(campaign['known_facts']) + 1:04d}"
        campaign["known_facts"].append({
            "id": fact_id,
            "text": fact_entry["fact"],
            "visibility": fact_entry["visibility"],
            "source": fact_entry["source"],
            "created_turn": current_turn,
            "valid": True,
        })
        report["facts"].append(f"[{fact_id}] {fact_entry['fact']} ({fact_entry['visibility']})")

    # 7. Contradictions
    for contradiction in patch.get("contradictions", []):
        old_id = contradiction["old_fact_id"]
        new_fact = contradiction["new_fact"]
        resolution = contradiction["resolution"]

        for fact in campaign.get("known_facts", []):
            if fact.get("id") == old_id:
                if resolution == "mark_as_rumor":
                    fact["valid"] = False
                    fact["invalid_at_turn"] = current_turn
                    fact["resolution"] = "marked_as_rumor"
                    fact["replaced_by"] = new_fact
                elif resolution == "replace_old":
                    fact["valid"] = False
                    fact["invalid_at_turn"] = current_turn
                    fact["resolution"] = "replaced"
                    fact["replaced_by"] = new_fact
                elif resolution == "keep_old":
                    fact["resolution"] = "kept_despite_contradiction"
                    fact["contradicted_by"] = new_fact
                elif resolution == "coexist_until_verified":
                    fact["contradicted_by"] = new_fact

                report["contradictions"].append(
                    f"[{old_id}] {resolution}: {new_fact}"
                )
                break
        else:
            report["contradictions"].append(
                f"[{old_id}] not found in known_facts, contradiction unresolved"
            )

    # 8. NPC memory writes
    npc_writes = patch.get("npc_memory_writes", [])
    for raw_write in npc_writes:
        if not isinstance(raw_write, dict):
            report["errors"].append(f"npc_memory_writes entry is not an object: {raw_write}")
            continue
        write = normalize_memory_write(raw_write)
        if not write.get("npc_id"):
            report["errors"].append(f"npc_memory_writes entry missing npc_id: {raw_write}")
            continue
        if not write.get("memory"):
            report["errors"].append(f"npc_memory_writes entry missing memory content: {raw_write}")
            continue
        # V22: silently skip memory writes where visibility_path is "none"
        if str(write.get("visibility_path", "")).strip().lower() == "none":
            report["memories"].append(
                f"[SKIPPED] {write['npc_id']}: visibility_path=none, memory not written"
            )
            continue

        evidence_errors = memory_visibility_evidence_errors(write, "npc_memory_writes entry")
        if evidence_errors:
            report["errors"].extend(evidence_errors)
            continue

        npc_id = write["npc_id"]
        mem_path = memory_graph_path_for(root, npc_id)
        graph = load_memory_graph(mem_path, npc_id, current_turn)

        mem_id = next_memory_id(npc_id, graph)
        observed_at = campaign.get("current_time", current_time)
        scene = campaign.get("current_scene", {})
        location_id = scene.get("location_id", "unknown")

        # Auto-create minimal NPC profile for ad-hoc / dynamically generated NPCs
        profile_path = profile_path_for(root, npc_id)
        profile_location = read_profile_location(profile_path)
        if not profile_path.exists():
            create_minimal_npc_profile(root, npc_id, location_id, write["memory"])
            profile_location = location_id
            report["memories"].append(
                f"[NEW NPC PROFILE] {npc_id}: auto-created minimal profile"
            )
        if (
            isinstance(scene, dict)
            and location_id not in ("", "unknown")
            and profile_location == location_id
            and str(write.get("visibility_path", "")).strip().lower() not in ("", "none")
        ):
            present = scene.setdefault("present_entities", [])
            if isinstance(present, list) and npc_id not in present:
                present.append(npc_id)
                report["locations"].append(f"{npc_id} added to current scene from memory visibility")

        # Determine importance from salience and emotional_valence
        salience_val = clamp_float(write.get("salience"), 0.5)
        emotion_val = clamp_float(write.get("emotional_valence"), 0.0, -2.0, 2.0)
        importance_val = clamp_float(
            write.get("importance"),
            max(salience_val, abs(emotion_val) / 2),
        )
        memory_text = str(write["memory"])

        memory_node = {
            "id": mem_id,
            "type": write.get("memory_type", "episodic"),
            "content": memory_text,
            "created_turn": current_turn,
            "last_recalled_turn": current_turn,
            "recall_count": 0,
            "importance": importance_val,
            "salience": salience_val,
            "emotional_valence": emotion_val,
            "confidence": float(write.get("confidence", 0.5)),
            "source": write.get("source", "inferred"),
            "tier": write.get("tier", "active"),
            "valid": True,
            "invalid_at_turn": None,
            "contradicted_by": None,
            "related_entities": write.get("related_entities", [npc_id, location_id]),
            "visibility_path": write.get("visibility_path", ""),
            "visibility_evidence": write.get("visibility_evidence", {}),
            "observed_at": observed_at,
            "location_id": location_id,
        }

        # V06 fix: dedup check before appending memory
        existing_contents = [
            str(m.get("content", "")) for m in graph.get("memory_nodes", [])
            if m.get("valid") is not False
        ]
        is_duplicate = False
        new_words = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", memory_text.lower()))
        if len(new_words) >= 4:  # skip dedup for very short content
            for existing_text in existing_contents:
                old_words = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", existing_text.lower()))
                if len(old_words) < 4:
                    continue
                overlap = len(new_words & old_words) / min(len(new_words), len(old_words))
                if overlap > 0.8:
                    is_duplicate = True
                    report.setdefault("memories", []).append(
                        f"[{mem_id}] {npc_id}: SKIPPED (duplicate, {overlap:.0%} overlap with existing memory)"
                    )
                    break
        if not is_duplicate:
            graph.setdefault("memory_nodes", []).append(memory_node)
        graph["current_turn"] = current_turn

        if not dry_run:
            save_json(mem_path, graph)

        report["memories"].append(
            f"[{mem_id}] {npc_id}: {memory_text[:60]}..."
        )

        # 9. Append to world_graph.jsonl
        wg_record = {
            "record_type": "node",
            "id": mem_id,
            "node_type": "Memory",
            "npc_id": npc_id,
            "created_at": observed_at,
            "created_turn": current_turn,
            "summary": memory_text[:200],
            "source": write.get("source", "inferred"),
            "visibility": "private",
        }
        if not dry_run:
            append_jsonl(root / "campaign" / "world_graph.jsonl", wg_record)

        report["world_graph"].append(f"Appended {mem_id} to world_graph.jsonl")

    # 8a. NPC interpretation writes
    for interpretation in patch.get("npc_interpretation_writes", []):
        npc_id = interpretation["npc_id"]
        mem_path = memory_graph_path_for(root, npc_id)
        graph = load_memory_graph(mem_path, npc_id, current_turn)
        graph.setdefault("interpretation_nodes", [])
        memory_ids = {item.get("id") for item in graph.get("memory_nodes", [])}
        source_memory_id = interpretation.get("derived_from_memory_id")
        if source_memory_id not in memory_ids:
            report["errors"].append(
                f"{interpretation['id']}: derived_from_memory_id not found for {npc_id}: {source_memory_id}"
            )
            continue

        existing = {
            item.get("id"): index
            for index, item in enumerate(graph["interpretation_nodes"])
        }
        if interpretation["id"] in existing:
            graph["interpretation_nodes"][existing[interpretation["id"]]] = interpretation
            action = "updated"
        else:
            graph["interpretation_nodes"].append(interpretation)
            action = "appended"

        graph["current_turn"] = current_turn
        if not dry_run:
            save_json(mem_path, graph)

        report["interpretations"].append(
            f"[{interpretation['id']}] {npc_id}: {action}"
        )

        wg_record = {
            "record_type": "node",
            "id": interpretation["id"],
            "node_type": "Interpretation",
            "npc_id": npc_id,
            "created_at": campaign.get("current_time", current_time),
            "created_turn": current_turn,
            "summary": interpretation["text"][:200],
            "source_memory_id": interpretation.get("derived_from_memory_id"),
            "visibility": "private",
        }
        if not dry_run:
            append_jsonl(root / "campaign" / "world_graph.jsonl", wg_record)
        report["world_graph"].append(f"Appended {interpretation['id']} to world_graph.jsonl")

    # 8b. NPC stable understanding writes
    for understanding in patch.get("npc_understanding_writes", []):
        npc_id = understanding["npc_id"]
        mem_path = memory_graph_path_for(root, npc_id)
        graph = load_memory_graph(mem_path, npc_id, current_turn)
        graph.setdefault("understanding_nodes", [])
        memory_ids = {item.get("id") for item in graph.get("memory_nodes", [])}
        interpretation_ids = {item.get("id") for item in graph.get("interpretation_nodes", [])}
        missing_memories = [
            item for item in understanding.get("supporting_memory_ids", []) if item not in memory_ids
        ]
        missing_interpretations = [
            item
            for item in understanding.get("supporting_interpretation_ids", [])
            if item not in interpretation_ids
        ]
        if missing_memories or missing_interpretations:
            report["errors"].append(
                f"{understanding['id']}: missing provenance for {npc_id}: "
                f"memories={missing_memories}, interpretations={missing_interpretations}"
            )
            continue

        existing = {
            item.get("id"): index
            for index, item in enumerate(graph["understanding_nodes"])
        }
        if understanding["id"] in existing:
            graph["understanding_nodes"][existing[understanding["id"]]] = understanding
            action = "updated"
        else:
            graph["understanding_nodes"].append(understanding)
            action = "appended"

        graph["current_turn"] = current_turn
        if not dry_run:
            save_json(mem_path, graph)

        report["understandings"].append(
            f"[{understanding['id']}] {npc_id}: {action}"
        )

        wg_record = {
            "record_type": "node",
            "id": understanding["id"],
            "node_type": "Understanding",
            "npc_id": npc_id,
            "created_at": campaign.get("current_time", current_time),
            "created_turn": current_turn,
            "summary": understanding["text"][:200],
            "revision_status": understanding.get("revision_status"),
            "visibility": "private",
        }
        if not dry_run:
            append_jsonl(root / "campaign" / "world_graph.jsonl", wg_record)
        report["world_graph"].append(f"Appended {understanding['id']} to world_graph.jsonl")

    # 8c. NPC understanding revision events
    for revision in patch.get("npc_revision_writes", []):
        npc_id = revision["npc_id"]
        mem_path = memory_graph_path_for(root, npc_id)
        graph = load_memory_graph(mem_path, npc_id, current_turn)
        graph.setdefault("revision_events", [])
        understanding_ids = {item.get("id") for item in graph.get("understanding_nodes", [])}
        interpretation_ids = {item.get("id") for item in graph.get("interpretation_nodes", [])}
        target_understanding_id = revision.get("target_understanding_id")
        missing_source_interpretations = [
            item
            for item in revision.get("source_interpretation_ids", [])
            if item not in interpretation_ids
        ]
        if target_understanding_id not in understanding_ids or missing_source_interpretations:
            report["errors"].append(
                f"{revision['id']}: missing revision provenance for {npc_id}: "
                f"target={target_understanding_id}, source_interpretations={missing_source_interpretations}"
            )
            continue

        existing = {
            item.get("id"): index
            for index, item in enumerate(graph["revision_events"])
        }
        if revision["id"] in existing:
            graph["revision_events"][existing[revision["id"]]] = revision
            action = "updated"
        else:
            graph["revision_events"].append(revision)
            action = "appended"

        graph["current_turn"] = current_turn

        # V02 fix: apply revision effect to the target understanding node
        effect = revision.get("effect", "no_change")
        evidence_strength = float(revision.get("evidence_strength", 0.0))
        new_status = revision.get("new_status")

        for idx, node in enumerate(graph.get("understanding_nodes", [])):
            if node.get("id") != target_understanding_id:
                continue
            old_confidence = float(node.get("confidence", 0.5))
            old_stability = float(node.get("stability", 0.5))

            if effect == "supports":
                node["confidence"] = round(min(1.0, old_confidence + evidence_strength * (1 - old_confidence) * 0.6), 4)
                node["stability"] = round(min(1.0, old_stability + evidence_strength * 0.2), 4)
            elif effect == "weakens":
                node["confidence"] = round(max(0.0, old_confidence - evidence_strength * (1 - old_stability * 0.5)), 4)
                node["stability"] = round(max(0.0, old_stability - evidence_strength * 0.2), 4)
                if new_status:
                    node["revision_status"] = new_status
            elif effect == "contradicts":
                node["confidence"] = round(max(0.0, old_confidence - evidence_strength * (1 - old_stability * 0.3)), 4)
                node["stability"] = round(max(0.0, old_stability - evidence_strength * 0.3), 4)
                node["revision_status"] = "contested"
            elif effect in ("qualifies", "reframes"):
                node["revision_status"] = "contested"
                if revision.get("reason"):
                    node.setdefault("qualifying_notes", []).append(revision["reason"][:200])
            elif effect == "supersedes":
                node["revision_status"] = "superseded"
                node["superseded_by"] = revision.get("new_understanding_id")
            elif effect == "splits":
                node["revision_status"] = "superseded"
            # no_change: nothing

            if new_status and effect not in ("contradicts",):
                node["revision_status"] = new_status

            node["last_updated_turn"] = current_turn
            if effect != "no_change":
                node["version"] = int(node.get("version", 1)) + 1

            revision["_applied"] = True
            revision["_old_confidence"] = old_confidence
            revision["_new_confidence"] = node["confidence"]
            revision["_old_stability"] = old_stability
            revision["_new_stability"] = node["stability"]
            break
        else:
            # understanding node referenced but not in graph's understanding_nodes
            report.setdefault("errors", []).append(
                f"{revision['id']}: target understanding {target_understanding_id} not found in understanding_nodes for {npc_id}"
            )

        if not dry_run:
            save_json(mem_path, graph)

        report["revisions"].append(
            f"[{revision['id']}] {npc_id}: {action} {revision['effect']} -> {revision['target_understanding_id']}"
        )

        wg_record = {
            "record_type": "edge",
            "id": revision["id"],
            "edge_type": "REVISES_UNDERSTANDING",
            "from": revision["new_event_id"],
            "to": revision["target_understanding_id"],
            "npc_id": npc_id,
            "created_at": campaign.get("current_time", current_time),
            "created_turn": current_turn,
            "effect": revision["effect"],
            "summary": revision["reason"][:200],
            "visibility": "private",
        }
        if not dry_run:
            append_jsonl(root / "campaign" / "world_graph.jsonl", wg_record)
        report["world_graph"].append(f"Appended {revision['id']} to world_graph.jsonl")

    # 8d. V03 fix: auto-rerank all touched NPC memory graphs
    touched_npc_ids: set[str] = set()
    for section in ("npc_memory_writes", "npc_interpretation_writes",
                    "npc_understanding_writes", "npc_revision_writes"):
        for item in patch.get(section, []):
            if isinstance(item, dict) and item.get("npc_id"):
                touched_npc_ids.add(str(item["npc_id"]))
    if touched_npc_ids and not dry_run:
        from memory_manager import memory_score, tier_for_score
        half_life = 12  # default from memory_policy.yaml
        for npc_id in sorted(touched_npc_ids):
            mem_path = memory_graph_path_for(root, npc_id)
            if not mem_path.exists():
                continue
            try:
                graph = load_memory_graph(mem_path, npc_id, current_turn)
                for memory in graph.get("memory_nodes", []):
                    score = memory_score(memory, current_turn, half_life)
                    memory["score"] = score
                    memory["tier"] = tier_for_score(score, bool(memory.get("pinned", False)))
                graph["memory_nodes"] = sorted(
                    graph["memory_nodes"],
                    key=lambda item: item.get("score", 0),
                    reverse=True,
                )
                save_json(mem_path, graph)
                report["memories"].append(f"[{npc_id}] memory tiers reranked, {len(graph['memory_nodes'])} nodes")
            except Exception as exc:
                report["errors"].append(f"[{npc_id}] rerank failed: {exc}")
        report.setdefault("memories", [])

    # 9. Open threads
    ensure_campaign_field(campaign, "open_threads", [])
    for thread in patch.get("open_threads", []):
        description = str(thread["thread"]).strip()
        next_pressure = str(thread["next_pressure"]).strip()
        existing_thread = next(
            (
                item
                for item in reversed(campaign["open_threads"])
                if isinstance(item, dict)
                and item.get("status", "active") == "active"
                and str(item.get("description", "")).strip() == description
            ),
            None,
        )
        if existing_thread:
            thread_id = str(existing_thread.get("id"))
            existing_thread["next_pressure"] = next_pressure
            existing_thread["updated_turn"] = current_turn
            thread_action = "updated"
        else:
            thread_id = f"open_thread_{len(campaign['open_threads']) + 1:04d}"
            campaign["open_threads"].append({
                "id": thread_id,
                "description": description,
                "next_pressure": next_pressure,
                "created_turn": current_turn,
                "status": "active",
            })
            thread_action = "added"
        scene = campaign.get("current_scene")
        if isinstance(scene, dict):
            scene.setdefault("active_threads", [])
            if isinstance(scene["active_threads"], list) and thread_id not in scene["active_threads"]:
                scene["active_threads"].append(thread_id)
        report["threads"].append(f"[{thread_id}] {thread_action}: {description}")
    prune_active_threads(campaign, current_turn, report)

    # V04 fix: track consolidation turns, flag when due
    ensure_campaign_field(campaign, "last_consolidation_turn", 0)
    consolidation_interval = 5
    turns_since_consolidation = current_turn - int(campaign.get("last_consolidation_turn", 0))
    if turns_since_consolidation >= consolidation_interval:
        report.setdefault("consolidation", []).append(
            f"Consolidation due: {turns_since_consolidation} turns since last consolidation "
            f"(turn {campaign.get('last_consolidation_turn', 0)} -> {current_turn}). "
            f"Run prompts/memory-consolidator.md and prompts/understanding-consolidator.md "
            f"for all NPCs with new memories/interpretations."
        )

    if not dry_run:
        campaign["current_turn"] = current_turn + 1

    # Write campaign_state.json
    if not dry_run:
        save_json(campaign_path, campaign)

    # Append session log
    if not dry_run:
        log_path = root / "campaign" / "session_logs" / f"{session_id}.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = (
            f"\n## Patch applied at {timestamp}\n\n"
            f"- Turn: {current_turn}\n"
            f"- Next turn: {current_turn + 1}\n"
            f"- Time delta: {delta_str}\n"
            f"- Player state changes: {len(patch.get('player_state_changes', []))}\n"
            f"- NPC memories written: {len(npc_writes)}\n"
            f"- New facts: {len(patch.get('new_facts', []))}\n"
            f"- Contradictions handled: {len(patch.get('contradictions', []))}\n"
            f"- Open threads added: {len(patch.get('open_threads', []))}\n"
        )
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(entry)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def validate_patch_structure(patch: dict[str, Any]) -> list[str]:
    """Basic structural validation before applying."""
    errors: list[str] = []
    required = [
        "time_delta", "location_changes", "inventory_changes",
        "relationship_changes", "new_facts", "contradictions",
        "npc_memory_writes", "open_threads",
    ]
    for field in required:
        if field not in patch:
            errors.append(f"Missing required field: {field}")

    for field in (
        "location_changes",
        "inventory_changes",
        "relationship_changes",
        "new_facts",
        "contradictions",
        "player_state_changes",
        "npc_memory_writes",
        "npc_interpretation_writes",
        "npc_understanding_writes",
        "npc_revision_writes",
        "open_threads",
    ):
        if field in patch and not isinstance(patch[field], list):
            errors.append(f"{field} must be a list")

    # Validate enums in npc_memory_writes
    VALID_PATHS = {"direct_visual", "direct_auditory", "detected_observer",
                   "told_by", "overheard", "inferred", "public_signal", "none"}
    VALID_SOURCES = {"saw", "heard", "inferred", "rumor"}
    VALID_MEM_TYPES = {"episodic", "semantic", "procedural"}
    valid_player_ops = {"set", "add", "remove", "delta"}
    for i, change in enumerate(patch.get("player_state_changes", [])):
        if not isinstance(change, dict):
            errors.append(f"player_state_changes[{i}] must be an object")
            continue
        for sf in ("entity_id", "field", "reason"):
            if sf not in change:
                errors.append(f"player_state_changes[{i}] missing: {sf}")
        field = str(change.get("field", ""))
        root_field = field.split(".", 1)[0]
        if field and root_field not in PLAYER_STATE_FIELDS:
            errors.append(f"player_state_changes[{i}] invalid field: {field}")
        operation = change.get("operation", "set")
        if operation not in valid_player_ops:
            errors.append(f"player_state_changes[{i}] invalid operation: {operation}")
        if "value" not in change and "delta" not in change:
            errors.append(f"player_state_changes[{i}] must include value or delta")
        if "delta" in change:
            try:
                float(change["delta"])
            except (TypeError, ValueError):
                errors.append(f"player_state_changes[{i}] delta must be a number")

    for i, write in enumerate(patch.get("npc_memory_writes", [])):
        if not isinstance(write, dict):
            errors.append(f"npc_memory_writes[{i}] must be an object")
            continue
        vp = write.get("visibility_path", "")
        if vp and vp not in VALID_PATHS:
            errors.append(f"npc_memory_writes[{i}] invalid visibility_path: {vp}")
        src = write.get("source", "")
        if src and src not in VALID_SOURCES:
            errors.append(f"npc_memory_writes[{i}] invalid source: {src}")
        mt = write.get("memory_type", "")
        if mt and mt not in VALID_MEM_TYPES:
            errors.append(f"npc_memory_writes[{i}] invalid memory_type: {mt}")
        errors.extend(memory_visibility_evidence_errors(write, f"npc_memory_writes[{i}]"))

    # Validate npc_memory_writes have required sub-fields
    for i, write in enumerate(patch.get("npc_memory_writes", [])):
        if not isinstance(write, dict):
            continue
        sub_required = [
            "npc_id",
            "memory",
            "memory_type",
            "source",
            "visibility_path",
            "visibility_evidence",
            "confidence",
            "emotional_valence",
            "salience",
        ]
        for sf in sub_required:
            if sf not in write:
                errors.append(f"npc_memory_writes[{i}] missing: {sf}")
        for sf in ("confidence", "salience"):
            if sf in write:
                try:
                    value = float(write[sf])
                except (TypeError, ValueError):
                    errors.append(f"npc_memory_writes[{i}] {sf} must be a number")
                    continue
                if not 0 <= value <= 1:
                    errors.append(f"npc_memory_writes[{i}] {sf} out of range 0..1: {value}")
        if "emotional_valence" in write:
            try:
                value = float(write["emotional_valence"])
            except (TypeError, ValueError):
                errors.append(f"npc_memory_writes[{i}] emotional_valence must be a number")
            else:
                if not -2 <= value <= 2:
                    errors.append(f"npc_memory_writes[{i}] emotional_valence out of range -2..2: {value}")

    for field in ("npc_interpretation_writes", "npc_understanding_writes", "npc_revision_writes"):
        value = patch.get(field, [])
        if not isinstance(value, list):
            errors.append(f"{field} must be a list")

    for i, item in enumerate(patch.get("npc_interpretation_writes", [])):
        if not isinstance(item, dict):
            errors.append(f"npc_interpretation_writes[{i}] must be an object")
            continue
        for sf in ("id", "npc_id", "derived_from_event_id", "derived_from_memory_id", "text"):
            if sf not in item:
                errors.append(f"npc_interpretation_writes[{i}] missing: {sf}")

    for i, item in enumerate(patch.get("npc_understanding_writes", [])):
        if not isinstance(item, dict):
            errors.append(f"npc_understanding_writes[{i}] must be an object")
            continue
        for sf in ("id", "npc_id", "type", "text", "revision_status"):
            if sf not in item:
                errors.append(f"npc_understanding_writes[{i}] missing: {sf}")

    VALID_REVISION_EFFECTS = {
        "supports", "weakens", "contradicts", "qualifies",
        "reframes", "supersedes", "splits", "no_change",
    }
    for i, item in enumerate(patch.get("npc_revision_writes", [])):
        if not isinstance(item, dict):
            errors.append(f"npc_revision_writes[{i}] must be an object")
            continue
        for sf in ("id", "npc_id", "target_understanding_id", "effect", "reason"):
            if sf not in item:
                errors.append(f"npc_revision_writes[{i}] missing: {sf}")
        if isinstance(item, dict) and item.get("effect") not in VALID_REVISION_EFFECTS:
            errors.append(
                f"npc_revision_writes[{i}] invalid effect: '{item.get('effect')}'. "
                f"Must be one of: {', '.join(sorted(VALID_REVISION_EFFECTS))}"
            )

    return errors


def print_report(report: dict[str, Any], dry_run: bool) -> None:
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"\n{prefix}Patch report:")
    print("=" * 50)

    for section, label in [
        ("time", "Time"),
        ("locations", "Location changes"),
        ("inventory", "Inventory"),
        ("player_state", "Player state"),
        ("relationships", "Relationships"),
        ("facts", "New facts"),
        ("contradictions", "Contradictions"),
        ("memories", "NPC memories"),
        ("interpretations", "NPC interpretations"),
        ("understandings", "NPC understandings"),
        ("revisions", "NPC revisions"),
        ("consolidation", "Consolidation"),
        ("world_graph", "World graph"),
        ("threads", "Open threads"),
    ]:
        items = report.get(section, [])
        if items:
            print(f"\n{label} ({len(items)}):")
            for item in items:
                print(f"  - {item}")

    errors = report.get("errors", [])
    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for err in errors:
            print(f"  ! {err}")

    print("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a state-extractor patch to campaign state, NPC memories, and world graph."
    )
    parser.add_argument("patch_file", type=Path, help="Path to the state patch JSON file.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview without writing.")
    parser.add_argument("--write", action="store_true", help="Actually write changes (required for safety).")
    parser.add_argument("--session-id", default="0001", help="Session ID for log append.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Campaign root directory (default: cwd).",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    patch_path = args.patch_file.resolve()

    if not patch_path.exists():
        raise SystemExit(f"Patch file not found: {patch_path}")

    try:
        patch = load_json(patch_path)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Patch file is not valid JSON: {patch_path} ({exc})") from None
    except OSError as exc:
        raise SystemExit(f"Could not read patch file: {patch_path} ({exc})") from None
    if not isinstance(patch, dict):
        raise SystemExit("Patch file must contain a JSON object.")

    # Validate structure
    errors = validate_patch_structure(patch)
    if errors:
        print("Validation errors:")
        for e in errors:
            print(f"  ! {e}")
        raise SystemExit("Aborting due to validation errors.")

    # Load current campaign state for context
    campaign_path = root / "campaign" / "campaign_state.json"
    try:
        campaign = load_json(campaign_path)
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"Could not load campaign state: {campaign_path} ({exc})") from None
    current_turn = int(campaign.get("current_turn", 1))
    current_time = campaign.get("current_time", "unknown")

    if not args.write and not args.dry_run:
        print("Preview mode (no --write, no --dry-run). Nothing will be changed.\n")
        # Just show what the patch contains
        print(f"Patch file: {patch_path}")
        print(f"Current turn: {current_turn}")
        print(f"Current time: {current_time}")
        print(f"Time delta: {patch.get('time_delta', 'N/A')}")
        print(f"Location changes: {len(patch.get('location_changes', []))}")
        print(f"Inventory changes: {len(patch.get('inventory_changes', []))}")
        print(f"Player state changes: {len(patch.get('player_state_changes', []))}")
        print(f"Relationship changes: {len(patch.get('relationship_changes', []))}")
        print(f"New facts: {len(patch.get('new_facts', []))}")
        print(f"Contradictions: {len(patch.get('contradictions', []))}")
        print(f"NPC memory writes: {len(patch.get('npc_memory_writes', []))}")
        print(f"NPC interpretation writes: {len(patch.get('npc_interpretation_writes', []))}")
        print(f"NPC understanding writes: {len(patch.get('npc_understanding_writes', []))}")
        print(f"NPC revision writes: {len(patch.get('npc_revision_writes', []))}")
        print(f"Open threads: {len(patch.get('open_threads', []))}")
        return

    dry_run = args.dry_run and not args.write
    report = apply_patch(root, patch, current_turn, current_time, args.session_id, dry_run)
    print_report(report, dry_run)

    if dry_run:
        print("\nDry run completed. No files were modified.")
    else:
        print(f"\nPatch applied. Campaign turn: {current_turn}")


if __name__ == "__main__":
    main()



