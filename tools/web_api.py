#!/usr/bin/env python3
"""Small Web API service layer for the browser RPG UI.

This module keeps HTTP concerns out of the game runner so tests and the
standard-library web server can both call the same functions.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

import play_game  # noqa: E402
import obsidian_vault  # noqa: E402


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return default


def load_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8-sig")


def decode_escaped_text(value: str) -> str:
    if "\\u" not in value and "\\n" not in value:
        return value
    try:
        return json.loads('"' + value.replace('"', '\\"') + '"')
    except Exception:
        try:
            return value.encode("utf-8").decode("unicode_escape")
        except Exception:
            return value


def clean_visible(value: Any) -> Any:
    if isinstance(value, str):
        return decode_escaped_text(value)
    if isinstance(value, list):
        return [clean_visible(item) for item in value]
    if isinstance(value, dict):
        return {key: clean_visible(item) for key, item in value.items()}
    return value


def as_dict(value: Any, default: dict[str, Any] | None = None) -> dict[str, Any]:
    return value if isinstance(value, dict) else (default or {})


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def condition_label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("id") or "").strip()
    return str(value or "").strip()


def tracked_conditions(conditions: dict[str, Any], entity_id: str) -> list[str]:
    entities = conditions.get("entities", {})
    record: Any = {}
    if isinstance(entities, dict):
        record = entities.get(entity_id, {})
    elif isinstance(entities, list):
        for item in entities:
            if isinstance(item, dict) and (item.get("id") == entity_id or item.get("entity_id") == entity_id):
                record = item
                break
    return [
        label
        for label in (condition_label(item) for item in as_list(as_dict(record).get("conditions")))
        if label
    ]


SECRET_QUEST_KEYS = {
    "gm_notes",
    "secret",
    "secrets",
    "hidden",
    "hidden_clues",
    "hidden_state",
    "private_notes",
}


def is_player_visible_record(item: dict[str, Any]) -> bool:
    if item.get("known_to_players") is False:
        return False
    if item.get("visibility") in {"secret", "private", "gm_only"}:
        return False
    if item.get("player_visible") is False:
        return False
    return True


def public_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in SECRET_QUEST_KEYS and not str(key).startswith("_")
    }


def normalize_quests(raw: Any, *, player_visible_only: bool = True) -> list[dict[str, Any]]:
    quests = []
    for index, item in enumerate(as_list(raw), start=1):
        if isinstance(item, dict):
            if player_visible_only and not is_player_visible_record(item):
                continue
            quests.append(public_record(item))
        else:
            quests.append(
                {
                    "id": str(item) if item else f"quest_{index:04d}",
                    "title": str(item) if item else f"Quest {index}",
                    "status": "active",
                    "known_to_players": True,
                }
            )
    return quests


def normalize_clocks(raw: Any) -> list[dict[str, Any]]:
    data = raw.get("clocks", raw) if isinstance(raw, dict) else raw
    clocks = []
    for index, item in enumerate(as_list(data), start=1):
        if isinstance(item, dict):
            clocks.append(
                {
                    **item,
                    "value": item.get("value", item.get("current", item.get("progress", 0))),
                    "max_value": item.get("max_value", item.get("max", item.get("target", "?"))),
                    "status": item.get("status", "active"),
                    "visibility": item.get("visibility", "public" if item.get("visible", True) else "secret"),
                    "stakes": item.get("stakes", item.get("description", "")),
                }
            )
        else:
            clocks.append(
                {
                    "id": f"clock_{index:04d}",
                    "title": str(item),
                    "value": 0,
                    "max_value": "?",
                    "status": "active",
                    "visibility": "public",
                }
            )
    return clocks


def normalize_resource_entities(raw: Any) -> list[dict[str, Any]]:
    entities = raw.get("entities", raw) if isinstance(raw, dict) else raw
    if isinstance(entities, dict):
        return [
            {"id": str(entity_id), **as_dict(values)}
            for entity_id, values in entities.items()
        ]
    return [item for item in as_list(entities) if isinstance(item, dict)]


def normalize_progress_tracks(raw: Any) -> list[dict[str, Any]]:
    tracks = raw.get("tracks", raw) if isinstance(raw, dict) else raw
    if isinstance(tracks, dict):
        normalized = []
        for track_id, values in tracks.items():
            data = as_dict(values)
            normalized.append(
                {
                    "id": str(track_id),
                    "title": data.get("title") or data.get("label") or str(track_id),
                    "value": data.get("value", data.get("current", data.get("progress", 0))),
                    "max_value": data.get("max_value", data.get("max", data.get("target", "?"))),
                    **data,
                }
            )
        return normalized
    return [item for item in as_list(tracks) if isinstance(item, dict)]


def make_args(
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    no_apply: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        model=model,
        base_url=base_url,
        api_key=api_key,
        no_apply=no_apply,
    )


def make_config(root: Path, *, mock: bool = False, no_apply: bool = False) -> play_game.GameConfig:
    config = play_game.load_config(PROJECT_ROOT.resolve(), make_args(no_apply=no_apply))
    config.root = root.resolve()
    if mock:
        config.model = "__mock__"
        config.api_key = ""
    return config


def is_campaign_root(path: Path) -> bool:
    return (path / "campaign" / "campaign_state.json").exists()


def campaign_key(path: Path) -> str:
    path = path.resolve()
    try:
        rel = path.relative_to(PROJECT_ROOT.resolve())
        key = str(rel).replace("\\", "/")
        return "." if key == "." else key
    except ValueError:
        return str(path)


def safe_campaign_path(key: str) -> Path:
    if not key or key == ".":
        return PROJECT_ROOT.resolve()
    candidate = (PROJECT_ROOT / key).resolve()
    allowed_roots = [
        PROJECT_ROOT.resolve(),
        (PROJECT_ROOT / "generated_campaigns").resolve(),
        (PROJECT_ROOT / "xianxia_campaign").resolve(),
    ]
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise ValueError("campaign path is outside the allowed project roots")
    if not is_campaign_root(candidate):
        raise ValueError(f"not a campaign root: {key}")
    return candidate


def list_campaigns() -> list[dict[str, Any]]:
    roots: list[Path] = []
    for candidate in [PROJECT_ROOT, PROJECT_ROOT / "xianxia_campaign"]:
        if is_campaign_root(candidate):
            roots.append(candidate.resolve())
    generated = PROJECT_ROOT / "generated_campaigns"
    if generated.exists():
        for child in sorted(generated.iterdir()):
            if child.is_dir() and is_campaign_root(child):
                roots.append(child.resolve())

    seen: set[str] = set()
    campaigns = []
    for root in roots:
        key = campaign_key(root)
        if key in seen:
            continue
        seen.add(key)
        state = load_json(root / "campaign" / "campaign_state.json", {})
        campaigns.append(
            {
                "id": key,
                "path": str(root),
                "title": state.get("title") or state.get("campaign_id") or root.name,
                "campaign_id": state.get("campaign_id") or key,
                "current_turn": state.get("current_turn", 1),
                "current_time": state.get("current_time", ""),
                "scene": (state.get("current_scene") or {}).get("summary", ""),
                "deletable": key.startswith("generated_campaigns/"),
            }
        )
    return campaigns


def delete_campaign(key: str) -> dict[str, Any]:
    root = safe_campaign_path(key)
    generated_root = (PROJECT_ROOT / "generated_campaigns").resolve()
    try:
        root.relative_to(generated_root)
    except ValueError as exc:
        raise ValueError("only generated campaigns can be deleted") from exc
    if root == generated_root:
        raise ValueError("refusing to delete generated_campaigns root")
    shutil.rmtree(root)
    campaigns = list_campaigns()
    next_campaign = campaigns[0]["id"] if campaigns else "."
    return {"deleted": key, "next_campaign": next_campaign, "campaigns": campaigns}


def parse_yaml_label(text: str, key: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}:"):
            return stripped.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def load_public_npcs(root: Path, present_ids: list[str], player_ids: set[str] | None = None) -> list[dict[str, Any]]:
    npcs = []
    npc_dir = root / "campaign" / "npcs"
    player_ids = player_ids or set()
    for npc_id in present_ids:
        if npc_id.startswith("pc_") or npc_id.startswith("player_") or npc_id in player_ids:
            continue
        profile = load_text(npc_dir / f"{npc_id}.yaml")
        graph = load_json(npc_dir / f"{npc_id}.memory_graph.json", {})
        npcs.append(
            {
                "id": npc_id,
                "name": parse_yaml_label(profile, "name") or npc_id,
                "role": parse_yaml_label(profile, "role") or parse_yaml_label(profile, "occupation") or parse_yaml_label(profile, "type") or "????",
                "location_id": parse_yaml_label(profile, "location_id"),
                "memory_count": len(graph.get("memory_nodes", [])),
                "understanding_count": len(graph.get("understanding_nodes", [])),
            }
        )
    return npcs


def load_location_summary(root: Path, location_id: str) -> dict[str, Any]:
    loc_dir = root / "campaign" / "locations"
    for path in sorted(loc_dir.glob("*.yaml")):
        text = load_text(path)
        if parse_yaml_label(text, "id") == location_id:
            return {
                "id": location_id,
                "name": parse_yaml_label(text, "name") or location_id,
                "type": parse_yaml_label(text, "type"),
                "summary": parse_yaml_label(text, "summary"),
                "file": str(path.relative_to(root)),
            }
    return {"id": location_id, "name": location_id, "type": "", "summary": "", "file": ""}


def visible_state(root: Path) -> dict[str, Any]:
    state = as_dict(load_json(root / "campaign" / "campaign_state.json", {}))
    knowledge = as_dict(load_json(root / "campaign" / "player_knowledge.json", {}))
    quest_graph = as_dict(load_json(root / "campaign" / "quest_graph.json", {"quests": []}))
    clocks_raw = load_json(root / "campaign" / "world_clocks.json", {"clocks": []})
    resources = as_dict(load_json(root / "campaign" / "resources.json", {"entities": []}))
    progress = as_dict(load_json(root / "campaign" / "progress_tracks.json", {"tracks": []}))
    conditions = as_dict(load_json(root / "campaign" / "conditions.json", {"entities": {}}))

    scene = as_dict(state.get("current_scene"))
    present_ids = [str(item) for item in as_list(scene.get("present_entities"))]
    location_id = scene.get("location_id", "")
    players = [item for item in as_list(state.get("player_characters")) if isinstance(item, dict)]
    player = players[0] if players else {}
    player_id = str(player.get("id", "pc_main"))
    player_conditions = list(dict.fromkeys([
        *[condition_label(item) for item in as_list(player.get("conditions")) if condition_label(item)],
        *tracked_conditions(conditions, player_id),
    ]))
    player_ids = {str(item.get("id")) for item in players if item.get("id")}
    quest_list = normalize_quests(state.get("quests") or quest_graph.get("quests", []))
    player_visible_facts = [
        fact.get("text") or fact.get("fact")
        for fact in as_list(state.get("known_facts"))
        if isinstance(fact, dict)
        and fact.get("valid", True)
        and fact.get("visibility") in {"public", "player_only", player_id}
        and (fact.get("text") or fact.get("fact"))
    ]
    if player_visible_facts:
        knowledge = {**knowledge}
        existing_facts = as_list(knowledge.get("facts_understood"))
        # V31: fix dedup - dict.fromkeys fails on unhashable dict values
        seen = set()
        deduped = []
        for item in [*existing_facts, *player_visible_facts]:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else item
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        knowledge["facts_understood"] = deduped
    open_threads = [
        thread
        for thread in as_list(state.get("open_threads"))
        if isinstance(thread, dict) and thread.get("status", "active") == "active"
    ]
    clocks = normalize_clocks(clocks_raw)

    public_clocks = [
        {
            "id": clock.get("id"),
            "title": clock.get("title"),
            "value": clock.get("value"),
            "max_value": clock.get("max_value"),
            "status": clock.get("status"),
            "stakes": clock.get("stakes"),
            "visibility": clock.get("visibility"),
        }
        for clock in clocks
        if clock.get("visibility") != "secret"
    ]

    return clean_visible({
        "campaign": {
            "id": state.get("campaign_id"),
            "title": state.get("title") or state.get("campaign_id"),
            "root": campaign_key(root),
            "turn": state.get("current_turn", 1),
            "time": state.get("current_time", ""),
        },
        "scene": {
            "id": scene.get("scene_id", ""),
            "summary": scene.get("summary", ""),
            "active_threads": scene.get("active_threads", []),
            "location": load_location_summary(root, location_id),
            "present_entities": present_ids,
        },
        "player": {
            "id": player_id,
            "name": player.get("name", "玩家角色"),
            "health": player.get("health"),
            "max_health": player.get("max_health"),
            "qi": player.get("qi"),
            "max_qi": player.get("max_qi"),
            "realm": player.get("realm"),
            "realm_level": player.get("realm_level"),
            "spiritual_root": player.get("spiritual_root"),
            "location_id": player.get("location_id") or location_id,
            "description": player.get("description"),
            "system_rank": player.get("system_rank"),
            "effect_points": player.get("effect_points"),
            "special_effects": player.get("special_effects", []),
            "stats": player.get("stats", {}),
            "inventory": player.get("inventory", []),
            "conditions": player_conditions,
            "traits": player.get("traits", player.get("tags", [])),
        },
        "npcs": load_public_npcs(root, present_ids, player_ids),
        "quests": quest_list,
        "open_threads": open_threads,
        "quest_graph": {"quests": normalize_quests(quest_graph.get("quests", []))},
        "knowledge": knowledge,
        "clocks": public_clocks,
        "resources": normalize_resource_entities(resources),
        "progress_tracks": normalize_progress_tracks(progress),
        "api": api_status(root),
    })


def api_status(root: Path) -> dict[str, Any]:
    config = make_config(root)
    return {
        "model": config.model,
        "base_url": config.base_url,
        "has_key": bool(config.api_key),
        "auto_apply": config.auto_apply,
        "mode": "api" if config.api_key else "mock_available",
    }


def unique_campaign_target(theme: str, force: bool = False) -> Path:
    slug = play_game.slugify(theme, "ai_campaign")
    base = (PROJECT_ROOT / "generated_campaigns" / slug).resolve()
    if force or not base.exists():
        return base
    for index in range(2, 1000):
        candidate = (PROJECT_ROOT / "generated_campaigns" / f"{slug}_{index:03d}").resolve()
        if not candidate.exists():
            return candidate
    raise RuntimeError("too many campaigns with the same theme")


def create_campaign(theme: str, *, mock: bool = False, force: bool = False) -> dict[str, Any]:
    if not theme.strip():
        raise ValueError("theme is required")
    target = unique_campaign_target(theme, force=force)
    config = make_config(PROJECT_ROOT, mock=mock)
    world = play_game.run_worldgen(config, theme, target, force=force)
    return {
        "campaign": {
            "id": campaign_key(target),
            "path": str(target),
            "title": theme,
            "opening_prompt": world.get("opening_prompt", ""),
        },
        "state": visible_state(target),
    }


def run_turn(root: Path, action: str, *, elapsed_minutes: int | None = None, memory_limit: int = 8, mock: bool = False) -> dict[str, Any]:
    if not action.strip():
        raise ValueError("action is required")
    config = make_config(root, mock=mock)
    result = play_game.run_ai_turn(config, action, elapsed_minutes, memory_limit)
    return {
        "visible_text": result["response"].get("visible_text", {}),
        "rendered": play_game.render_visible(result["response"]),
        "inferred_action": (result.get("packet") or {}).get("inferred_action", {}),
        "state_patch": result["patch"],
        "apply_report": result["apply_report"],
        "artifact_path": str(result["artifact_path"]),
        "tool_results": result.get("tool_results", []),
        "active_lore": (result.get("packet") or {}).get("context", {}).get("active_lore", []),
        "state": visible_state(root),
    }


def roll_dice(expression: str = "1d20") -> dict[str, Any]:
    expr = (expression or "1d20").replace(" ", "").lower()
    match = re.fullmatch(r"(\d*)d(\d+)([+-]\d+)?", expr)
    if not match:
        raise ValueError("dice expression must look like d20, 1d20, 2d6+3")
    count = int(match.group(1) or 1)
    sides = int(match.group(2))
    modifier = int(match.group(3) or 0)
    if count < 1 or count > 50 or sides < 2 or sides > 1000:
        raise ValueError("dice expression is out of range")
    rolls = [random.randint(1, sides) for _ in range(count)]
    return {
        "expression": expr,
        "rolls": rolls,
        "modifier": modifier,
        "total": sum(rolls) + modifier,
    }


def validate(root: Path) -> dict[str, Any]:
    command = [sys.executable, "validate_project.py"]
    if root.resolve() != PROJECT_ROOT.resolve():
        command.extend(["--root", str(root)])
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-20000:],
        "stderr": result.stderr[-8000:],
    }


def recent_logs(root: Path, limit: int = 12) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    ai_dir = root / "campaign" / "ai_runs"
    if ai_dir.exists():
        for path in sorted(ai_dir.glob("*.json"), reverse=True)[:limit]:
            data = load_json(path, {})
            response = data.get("ai_response") or {}
            packet = data.get("packet") or {}
            action = str(packet.get("player_action", ""))
            if "[??]" in action or "????" in action:
                action = "（旧记录行动文本编码损坏）"
            entries.append(
                {
                    "type": "ai_turn",
                    "file": str(path.relative_to(root)),
                    "turn_id": packet.get("turn_id") or path.stem,
                    "player_action": action,
                    "visible_text": response.get("visible_text", {}) if isinstance(response, dict) else {},
                    "rendered": play_game.render_visible(response) if response else "",
                    "applied": bool((data.get("apply_report") or {}).get("applied")),
                }
            )
    return entries


def export_obsidian(root: Path) -> dict[str, Any]:
    return obsidian_vault.export_campaign(root)
