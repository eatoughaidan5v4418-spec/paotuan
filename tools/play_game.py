#!/usr/bin/env python3
"""Interactive AI-powered local RPG game runner.

This turns the project from a state kit into a playable loop:

1. Build a deterministic GM turn packet from local campaign files.
2. Send it to an OpenAI-compatible API.
3. Let the model request bounded read-only local tools.
4. Render player-visible narration.
5. Validate and apply the model's state patch.

The AI never writes arbitrary files directly. It can read/list allowed project
files, then emits a structured state_patch that this script applies through the
existing apply_patch.py safety layer.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

import apply_patch as patcher  # noqa: E402
import run_turn  # noqa: E402


DEFAULT_PATCH = {
    "time_delta": "无",
    "location_changes": [],
    "inventory_changes": [],
    "player_state_changes": [],
    "relationship_changes": [],
    "new_facts": [],
    "contradictions": [],
    "npc_memory_writes": [],
    "npc_interpretation_writes": [],
    "npc_understanding_writes": [],
    "npc_revision_writes": [],
    "open_threads": [],
}

MAX_NEW_OPEN_THREADS = 5


ACTION_PREFIX_RE = re.compile(r"^\s*\[(?P<kind>[^\]]+)\]\s*(?P<body>.*)$")


def canonical_npc_id(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith(("npc_", "pc_", "player_")):
        return raw
    slug = re.sub(r"[^0-9A-Za-z_]+", "_", raw).strip("_").lower()
    if not slug:
        slug = slugify(raw, "npc").removeprefix("npc_")
    return f"npc_{slug}"


def strip_action_prefix(text: str) -> tuple[str, str | None]:
    match = ACTION_PREFIX_RE.match(text or "")
    if not match:
        return (text or "").strip(), None
    return match.group("body").strip(), match.group("kind").strip() or None


def explicit_minutes_from_text(text: str) -> int | None:
    lowered = text.lower()
    if "半小时" in text or "半个小时" in text:
        return 30
    if "一刻钟" in text:
        return 15
    if "片刻" in text or "一会" in text or "一小会" in text:
        return 5
    day_match = re.search(r"(\d+)\s*(?:天|日)", text)
    hour_match = re.search(r"(\d+)\s*(?:小时|个小时|时辰|hour|hours|h)", lowered)
    minute_match = re.search(r"(\d+)\s*(?:分钟|分|minute|minutes|min|m)", lowered)
    total = 0
    if day_match:
        total += int(day_match.group(1)) * 1440
    if hour_match:
        multiplier = 120 if "时辰" in hour_match.group(0) else 60
        total += int(hour_match.group(1)) * multiplier
    if minute_match:
        total += int(minute_match.group(1))
    return total if total > 0 else None


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def infer_player_action(player_input: str, elapsed_override: int | None = None) -> dict[str, Any]:
    """Infer an action category and elapsed minutes from natural player input."""
    cleaned, explicit_kind = strip_action_prefix(player_input)
    text = cleaned or player_input.strip()
    lowered = text.lower()
    explicit_minutes = explicit_minutes_from_text(text)

    if explicit_kind:
        kind = explicit_kind
        confidence = 0.95
        reason = "input included an explicit action prefix"
    elif contains_any(lowered, ("状态", "角色卡", "背包", "物品栏", "任务面板", "日志", "查看面板")):
        kind, confidence, reason = "查看状态", 0.82, "status or UI lookup wording"
    elif contains_any(lowered, ("攻击", "砍", "刺", "射", "施法", "战斗", "格挡", "拔剑", "开枪")):
        kind, confidence, reason = "战斗", 0.86, "hostile or combat verb"
    elif contains_any(lowered, ("休息", "睡", "打坐", "疗伤", "恢复", "冥想")):
        kind, confidence, reason = "休息", 0.86, "rest or recovery verb"
    elif contains_any(lowered, ("等待", "等半", "等一", "等到", "等候", "守候", "蹲守", "埋伏", "拖延")):
        kind, confidence, reason = "等待", 0.84, "waiting or holding-position verb"
    elif contains_any(lowered, ("调查", "搜索", "搜查", "检查", "查看", "浏览", "阅读", "翻找", "研究", "追踪", "侦查", "潜行")):
        kind, confidence, reason = "调查", 0.82, "investigation verb"
    elif contains_any(lowered, ("前往", "去", "走向", "走到", "移动", "离开", "进入", "回到", "赶往", "穿过")):
        kind, confidence, reason = "移动", 0.78, "movement or travel verb"
    elif contains_any(lowered, ("询问", "问", "交谈", "告诉", "说", "劝", "威胁", "谈判", "套话", "打听")):
        if contains_any(lowered, ("不交谈", "不主动交谈", "不和任何人交谈", "不说话", "不主动和任何人交谈")):
            kind, confidence, reason = "观察", 0.74, "social verb was negated by player wording"
        else:
            kind, confidence, reason = "交谈", 0.8, "social verb"
    elif contains_any(lowered, ("观察", "看看", "环顾", "聆听", "偷听", "盯", "留意", "整理", "确认")):
        kind, confidence, reason = "观察", 0.78, "observation verb"
    elif contains_any(lowered, ("使用", "拿出", "打开", "喝下", "装备", "点燃")):
        kind, confidence, reason = "使用物品", 0.72, "item-use verb"
    else:
        kind, confidence, reason = "自由行动", 0.45, "no strong action keyword matched"

    defaults = {
        "查看状态": 0,
        "战斗": 1,
        "休息": 60,
        "等待": 30,
        "移动": 10,
        "交谈": 5,
        "调查": 10,
        "观察": 5,
        "使用物品": 5,
        "自由行动": 5,
    }
    if kind == "移动" and contains_any(lowered, ("远行", "赶路", "出城", "去往", "前往")):
        defaults[kind] = 30
    if kind == "调查" and contains_any(lowered, ("仔细", "彻底", "地毯式", "慢慢")):
        defaults[kind] = 20
    if kind == "休息" and contains_any(lowered, ("睡觉", "过夜", "睡到", "休整")):
        defaults[kind] = 120

    inferred_minutes = defaults.get(kind, 5)
    elapsed = elapsed_override if elapsed_override is not None else (explicit_minutes if explicit_minutes is not None else inferred_minutes)
    elapsed = max(0, min(int(elapsed), 1440))
    return {
        "raw_input": player_input,
        "normalized_action": text,
        "action_type": kind,
        "elapsed_minutes": elapsed,
        "confidence": confidence,
        "reason": reason,
        "explicit_minutes": explicit_minutes,
        "elapsed_overridden": elapsed_override is not None,
    }


@dataclass
class GameConfig:
    root: Path
    base_url: str
    api_key: str
    model: str
    auto_apply: bool
    max_tool_rounds: int
    allowed_roots: list[str]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def load_dotenv(root: Path) -> None:
    """Load simple KEY=VALUE lines from .env files without overriding env vars.
    Checks both campaign root and project root (TOOLS_DIR.parent) so subdirectory
    campaigns inherit the project-level .env configuration."""
    project_root = TOOLS_DIR.parent
    for name in (".env", ".env.local"):
        path = root / name
        if not path.exists() and project_root != root:
            path = project_root / name
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def load_config(root: Path, args: argparse.Namespace) -> GameConfig:
    load_dotenv(root)
    config_path = root / "game_config.json"
    raw = load_json(config_path) if config_path.exists() else {}

    base_url = args.base_url or os.getenv(raw.get("base_url_env", "AI_BASE_URL")) or raw.get(
        "default_base_url", "https://api.openai.com/v1"
    )
    api_key = (
        args.api_key
        or os.getenv(raw.get("api_key_env", "AI_API_KEY"))
        or os.getenv(raw.get("fallback_api_key_env", "OPENAI_API_KEY"))
        or ""
    )
    model = args.model or os.getenv(raw.get("model_env", "AI_MODEL")) or raw.get(
        "default_model", "gpt-4.1-mini"
    )
    auto_apply = raw.get("auto_apply_patches", True)
    if args.no_apply:
        auto_apply = False

    return GameConfig(
        root=root,
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=model,
        auto_apply=bool(auto_apply),
        max_tool_rounds=int(raw.get("max_tool_rounds", 4)),
        allowed_roots=list(raw.get("allowed_roots", ["campaign", "prompts", "schemas"])),
    )


def ensure_allowed_path(config: GameConfig, requested: str) -> Path:
    normalized = requested.replace("\\", "/").lstrip("/")
    path = (config.root / normalized).resolve()
    root = config.root.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path outside project root: {requested}") from exc

    allowed = False
    for allowed_root in config.allowed_roots:
        try:
            path.relative_to((config.root / allowed_root).resolve())
            allowed = True
            break
        except ValueError:
            continue
    if not allowed:
        raise ValueError(f"path not under allowed roots {config.allowed_roots}: {requested}")
    return path


def tool_list_files(config: GameConfig, args: dict[str, Any]) -> dict[str, Any]:
    requested = args.get("path", "campaign")
    path = ensure_allowed_path(config, requested)
    if not path.exists():
        return {"error": f"not found: {requested}"}
    if path.is_file():
        return {"files": [str(path.relative_to(config.root))]}
    files = []
    for child in sorted(path.rglob("*")):
        if child.is_file():
            files.append(str(child.relative_to(config.root)))
            if len(files) >= int(args.get("limit", 200)):
                break
    return {"files": files}


def tool_read_file(config: GameConfig, args: dict[str, Any]) -> dict[str, Any]:
    requested = args.get("path", "")
    if not requested:
        return {"error": "missing path"}
    path = ensure_allowed_path(config, requested)
    if not path.exists() or not path.is_file():
        return {"error": f"not a file: {requested}"}
    text = read_text(path)
    max_chars = int(args.get("max_chars", 20000))
    return {
        "path": str(path.relative_to(config.root)),
        "content": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


def tool_validate_project(config: GameConfig, args: dict[str, Any]) -> dict[str, Any]:
    command = [sys.executable, "validate_project.py"]
    if args.get("root"):
        command.extend(["--root", str(args["root"])])
    result = subprocess.run(
        command,
        cwd=config.root,
        text=True,
        capture_output=True,
        timeout=120,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-4000:],
    }


def run_tool(config: GameConfig, request: dict[str, Any]) -> dict[str, Any]:
    tool = request.get("tool")
    args = request.get("args") or {}
    try:
        if tool == "list_files":
            result = tool_list_files(config, args)
        elif tool == "read_file":
            result = tool_read_file(config, args)
        elif tool == "validate_project":
            result = tool_validate_project(config, args)
        else:
            result = {"error": f"unknown tool: {tool}"}
    except Exception as exc:  # keep tool errors inside the AI loop
        result = {"error": str(exc)}
    return {"request": request, "result": result}


def call_chat_api(config: GameConfig, messages: list[dict[str, str]]) -> str:
    if config.model == "__mock__":
        return json.dumps(
            {
                "tool_requests": [],
                "visible_text": {
                    "scene": "你停在当前场景边缘，潮湿的空气里有旧木头、冷水和金属锈蚀混在一起的味道。近处的地面留下几道新旧交叠的痕迹，有些来自匆忙经过的人，有些像是被故意擦去。远处传来断续的低语，声音被风切碎，只剩下几个含混的词。这个地方不是静止的布景，至少有两股力量正在它背后拉扯：一个想把事情压下去，一个想在你看清之前把证据带走。\n\n你能感觉到当前场景已经被整理成可执行的本地回合包：在场 NPC、地点特征、世界时钟和任务压力都已进入判断。你现在的每个选择都会决定下一次写入谁的记忆、谁会误解你、以及哪条线索会先变得昂贵。",
                    "action_result": "这次行动没有直接触发战斗或检定，但它建立了当前回合的观察姿态：你没有贸然暴露敌意，也没有立刻交出承诺。周围 NPC 会把你归类为一个正在评估局势的人，而不是已经站队的人。这个结果让你暂时保留主动权，但也意味着对方会开始试探你。",
                    "npc_actions": [
                        "最近的 NPC 没有立刻摊牌，而是用问题、沉默或站位来试探你的来意。",
                        "远处的环境压力继续推进：有人可能正在移动、整理证据，或等待你离开视线。"
                    ],
                    "world_motion": "系统会根据你的自然语言行动自动估算耗时，并据此推进任务压力、NPC 记忆和世界变化。当前最重要的是：场景不会因为你停下观察而冻结。",
                    "tension": "你需要在继续观察、主动交涉和抢先调查之间做选择；拖得越久，某些线索越可能变质或被他人先处理。",
                    "actionable_clues": [
                        "继续询问在场 NPC，重点追问他们刚才看见或隐瞒了什么。",
                        "调查当前地点最显眼的异常痕迹，确认它是新出现还是被伪造。",
                        "花费 5-10 分钟静观其变，换取更多环境变化和离屏推进。",
                        "移动到更高或更隐蔽的位置，尝试扩大视野但承担暴露风险。"
                    ],
                    "check": "无",
                    "state_summary": {
                        "time": "本回合会按后端推断的耗时写入时间变化。",
                        "memory": "正式回合中，相关 NPC 会按可见性获得独立记忆和主观理解。",
                        "quests": "正式回合中，任务压力会随等待、移动和调查推进。",
                        "unresolved": [
                            "谁正在推动当前场景背后的压力？",
                            "哪些线索会因为玩家拖延而消失或变质？"
                        ]
                    }
                },
                "elapsed_minutes": 0,
                "state_patch": DEFAULT_PATCH,
                "gm_notes": ["mock mode: no API call was made"]
            },
            ensure_ascii=False,
        )

    if not config.api_key:
        raise RuntimeError(
            "Missing API key. Set AI_API_KEY or OPENAI_API_KEY, or pass --api-key."
        )

    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{config.base_url}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API error {exc.code}: {body}") from exc

    return raw["choices"][0]["message"]["content"]


def parse_ai_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI did not return valid JSON: {exc}\n{text[:1000]}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("AI response JSON must be an object")
    return data


def slugify(value: str, fallback: str = "ai_campaign") -> str:
    # Truncate very long inputs to avoid filesystem errors
    value = value.strip()[:200]
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.lower()).strip("_")
    if slug:
        return slug[:80]
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"{fallback}_{digest}"


def default_memory_policy() -> str:
    path = PROJECT_ROOT / "campaign" / "memory_policy.yaml"
    return read_text(path) if path.exists() else "id: npc_memory_policy_v1\n"


def default_world_tick_policy() -> str:
    path = PROJECT_ROOT / "campaign" / "world_tick_policy.yaml"
    return read_text(path) if path.exists() else "id: world_tick_policy_v1\n"


def default_oracles() -> dict[str, Any]:
    path = PROJECT_ROOT / "campaign" / "oracles.json"
    return load_json(path) if path.exists() else {"tables": {}}


def default_chaos_factor() -> dict[str, Any]:
    path = PROJECT_ROOT / "campaign" / "chaos_factor.json"
    return load_json(path) if path.exists() else {"chaos_factor": 5}


def minimal_memory_graph(npc_id: str) -> dict[str, Any]:
    return {
        "npc_id": npc_id,
        "current_turn": 1,
        "memory_policy_id": "npc_memory_policy_v1",
        "memory_nodes": [],
        "interpretation_nodes": [],
        "understanding_nodes": [],
        "revision_events": [],
        "relation_edges": [],
        "beliefs": [],
        "plans": [],
    }


def fallback_worldgen(theme: str) -> dict[str, Any]:
    slug = slugify(theme, "ai_campaign")
    location_id = "loc_first_scene"
    npc_ids = ["npc_gatekeeper", "npc_informant"]
    title = theme.strip() or "新战役"
    return {
        "campaign_id": slug,
        "opening_prompt": f"{title} 已生成。你站在第一个场景里，局势刚刚开始倾斜。",
        "files": [
            {
                "path": "campaign/campaign_state.json",
                "content": {
                    "campaign_id": slug,
                    "title": title,
                    "current_turn": 1,
                    "current_time": "第 1 日 08:00",
                    "_time_tick": 480,
                    "current_scene": {
                        "scene_id": "scene_0001",
                        "location_id": location_id,
                        "summary": "玩家抵达第一个关键地点，主要矛盾刚刚浮现。",
                        "present_entities": ["pc_main", *npc_ids],
                        "active_threads": ["thread_opening_crisis"],
                    },
                    "player_characters": [
                        {
                            "id": "pc_main",
                            "name": "玩家角色",
                            "location_id": location_id,
                            "inventory": [],
                            "conditions": [],
                            "health": 10,
                            "max_health": 10,
                            "stats": {"combat": 0, "perception": 0, "social": 0},
                        }
                    ],
                    "quests": [
                        {
                            "id": "thread_opening_crisis",
                            "title": "开局危机",
                            "status": "active",
                            "known_to_players": True,
                            "pressure": "若玩家不介入，局势会在数小时内恶化。",
                        }
                    ],
                    "rules": {
                        "system": "rules_lightweight_d20",
                        "dice_policy": "玩家或程序掷骰，GM 根据结果描述后果。",
                    },
                },
            },
            {
                "path": "campaign/world_clocks.json",
                "content": {
                    "current_turn": 1,
                    "clocks": [
                        {
                            "id": "clock_opening_crisis",
                            "type": "threat_countdown",
                            "owner_id": "thread_opening_crisis",
                            "title": "开局危机升级",
                            "value": 1,
                            "max_value": 6,
                            "status": "active",
                            "visibility": "secret",
                            "location_id": location_id,
                            "next_tick_at": "第 1 日 09:00",
                            "tick_interval": "1 小时",
                            "stakes": "危机会带来新的敌人、损失或误解。",
                            "on_complete": "危机爆发，玩家失去一个轻松解决的机会。",
                            "recent_updates": [],
                            "_next_tick_at_tick": 540,
                        }
                    ],
                },
            },
            {
                "path": "campaign/world_graph.jsonl",
                "content": json.dumps(
                    {
                        "record_type": "node",
                        "id": location_id,
                        "node_type": "Location",
                        "name": "初始地点",
                        "created_at": "第 1 日 08:00",
                        "summary": "新战役的第一个可玩场景。",
                    },
                    ensure_ascii=False,
                )
                + "\n",
            },
            {"path": "campaign/resources.json", "content": {"entities": []}},
            {"path": "campaign/player_knowledge.json", "content": {"clues_discovered": [], "npcs_known": [], "locations_explored": [], "facts_understood": [], "events_witnessed": []}},
            {"path": "campaign/quest_graph.json", "content": {"quests": [{"id": "thread_opening_crisis", "title": "开局危机", "status": "active"}]}},
            {"path": "campaign/rumors.json", "content": {"rumors": []}},
            {"path": "campaign/chaos_factor.json", "content": default_chaos_factor()},
            {"path": "campaign/conditions.json", "content": {"entities": []}},
            {"path": "campaign/progress_tracks.json", "content": {"tracks": []}},
            {"path": "campaign/oracles.json", "content": default_oracles()},
            {"path": "campaign/memory_policy.yaml", "content": default_memory_policy()},
            {"path": "campaign/world_tick_policy.yaml", "content": default_world_tick_policy()},
            {
                "path": "campaign/locations/first_scene.yaml",
                "content": f"""id: {location_id}
name: 初始地点
type: opening_scene
summary: "新战役的第一个关键地点。"
zones:
  - id: zone_center
    name: "中心区域"
    description: "玩家、关键 NPC 和第一个线索都在这里。"
    ambient_light: dim
    ambient_noise: moderate
    features:
      - id: feature_first_clue
        text: "一个明显不该出现在这里的线索。"
    initial_occupants:
      - pc_main
      - npc_gatekeeper
      - npc_informant
zone_connections: []
sensory_details:
  sight:
    - "空气里有一种事情刚刚发生过的痕迹。"
  sound:
    - "远处传来不安的低语。"
  smell: []
hidden_clues:
  - id: clue_hidden_motive
    location_zone: zone_center
    discover_with: "调查或逼问"
    text: "其中一个 NPC 隐瞒了危机真正的源头。"
hazards: []
""",
            },
            {
                "path": "campaign/lore/factions.yaml",
                "content": "factions:\n  - id: faction_local_power\n    name: 本地势力\n    type: local_power\n    goals:\n      - \"维持表面秩序。\"\n    secrets: []\n",
            },
            {
                "path": "campaign/lore/rules.yaml",
                "content": "id: rules_lightweight_d20\nname: 轻量 d20 跑团规则\ndice:\n  main: \"1d20 + 属性/技能修正\"\nchecks:\n  easy: 8\n  normal: 12\n  hard: 16\n  extreme: 20\nfailure_policy:\n  - \"失败产生代价，而不是让剧情停止。\"\n",
            },
            {
                "path": "campaign/lore/world_lore.yaml",
                "content": f"id: lore_{slug}\ntitle: {title}\nsummary: \"由 AI 生成的新战役世界观，等待游玩中扩展。\"\n",
            },
            {"path": "campaign/session_logs/0001.md", "content": f"# {title}\n\n{title} 开始。\n"},
            {
                "path": "campaign/npcs/npc_gatekeeper.yaml",
                "content": "id: npc_gatekeeper\nname: 守门人\nrole: 阻拦者\nfaction: faction_local_power\nlocation_id: loc_first_scene\npublic_face: \"谨慎、紧绷，像是知道麻烦已经靠近。\"\ncore_desire: \"维持秩序。\"\nfear: \"局势失控。\"\nbottom_line: \"不会主动暴露上级秘密。\"\ntraits:\n  personality_tags: [\"谨慎\", \"守规矩\"]\n  instinct: \"先拦住陌生人。\"\n  stress_response: \"硬撑\"\n  social_approach: \"盘问\"\n  cognitive_bias: \"怀疑外来者\"\nvoice_style:\n  pace: \"短句\"\n  habits: []\n  forbidden_topics: []\nknown_facts: []\nfalse_beliefs: []\nsecrets: []\nrelationship_hooks:\n  - target_id: pc_main\n    trust: 0\n    fear: 0\n    debt: 0\nchange_switches:\n  trust: []\n  threat: []\n",
            },
            {
                "path": "campaign/npcs/npc_informant.yaml",
                "content": "id: npc_informant\nname: 线人\nrole: 线索持有者\nfaction: faction_unaligned\nlocation_id: loc_first_scene\npublic_face: \"眼神游移，说话总留半截。\"\ncore_desire: \"用消息换取安全。\"\nfear: \"被真正的幕后者灭口。\"\nbottom_line: \"不会白白送死。\"\ntraits:\n  personality_tags: [\"多疑\", \"自保\"]\n  instinct: \"先确认对方能不能保护自己。\"\n  stress_response: \"逃避\"\n  social_approach: \"试探\"\n  cognitive_bias: \"负面归因\"\nvoice_style:\n  pace: \"低声短句\"\n  habits: []\n  forbidden_topics: []\nknown_facts: []\nfalse_beliefs: []\nsecrets: []\nrelationship_hooks:\n  - target_id: pc_main\n    trust: 0\n    fear: 0\n    debt: 0\nchange_switches:\n  trust: []\n  threat: []\n",
            },
            {"path": "campaign/npcs/npc_gatekeeper.memory_graph.json", "content": minimal_memory_graph("npc_gatekeeper")},
            {"path": "campaign/npcs/npc_informant.memory_graph.json", "content": minimal_memory_graph("npc_informant")},
        ],
    }


def assert_campaign_relative(path: str) -> Path:
    normalized = path.replace("\\", "/").lstrip("/")
    if not normalized.startswith("campaign/"):
        raise ValueError(f"worldgen file must live under campaign/: {path}")
    if ".." in Path(normalized).parts:
        raise ValueError(f"worldgen path may not contain '..': {path}")
    return Path(normalized)


def write_worldgen_files(target_root: Path, world: dict[str, Any], force: bool) -> None:
    campaign_dir = target_root / "campaign"
    if campaign_dir.exists():
        if not force:
            raise RuntimeError(f"campaign already exists: {campaign_dir}. Use --force-new to overwrite.")
        shutil.rmtree(campaign_dir)

    for item in world.get("files", []):
        rel = assert_campaign_relative(str(item.get("path", "")))
        path = target_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        content = item.get("content", "")
        if path.suffix == ".json":
            save_json(path, content)
        elif path.suffix == ".jsonl":
            if isinstance(content, str):
                path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
            else:
                lines = [json.dumps(row, ensure_ascii=False) for row in content]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            path.write_text(str(content), encoding="utf-8")

    for directory in ("campaign/events", "campaign/turn_packets", "campaign/ai_runs"):
        (target_root / directory).mkdir(parents=True, exist_ok=True)
    (target_root / "campaign/turn_packets/.gitkeep").write_text("", encoding="utf-8")
    # V19: Normalize player characters to ensure all required fields exist
    cs_path = target_root / "campaign" / "campaign_state.json"
    if cs_path.exists():
        try:
            cs = json.loads(cs_path.read_text(encoding="utf-8-sig"))
            pcs = cs.get("player_characters", [])
            if isinstance(pcs, list):
                for pc in pcs:
                    if isinstance(pc, dict):
                        pc.setdefault("health", 10)
                        pc.setdefault("max_health", 10)
                        pc.setdefault("qi", 5)
                        pc.setdefault("max_qi", 5)
                        pc.setdefault("realm_level", pc.get("sequence", 1))
                        pc.setdefault("realm", pc.get("path", "unknown"))
                        pc.setdefault("spiritual_root", "none")
                        pc.setdefault("location_id", cs.get("current_scene", {}).get("location_id", ""))
                        pc.setdefault("inventory", [])
                        pc.setdefault("conditions", [])
                        pc.setdefault("stats", {"combat": 0, "perception": 0, "social": 0})
                        pc.setdefault("description", "")
                cs_path.write_text(json.dumps(cs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass



def run_worldgen(config: GameConfig, theme: str, target_root: Path, force: bool) -> dict[str, Any]:
    if config.model == "__mock__":
        world = fallback_worldgen(theme)
    else:
        prompt = read_text(config.root / "prompts" / "worldgen-runner.md")
        raw = call_chat_api(
            config,
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "theme": theme,
                            "instruction": "Generate a complete new playable campaign file package.",
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        world = parse_ai_json(raw)

    write_worldgen_files(target_root, world, force)
    return world


def build_turn_packet(root: Path, player_action: str, elapsed_minutes: int | None, memory_limit: int) -> dict[str, Any]:
    inferred_action = infer_player_action(player_action, elapsed_minutes)
    normalized_action = inferred_action["normalized_action"]
    elapsed_minutes = int(inferred_action["elapsed_minutes"])
    campaign_state = run_turn.load_json(root / "campaign" / "campaign_state.json")
    world_clocks = run_turn.load_json(root / "campaign" / "world_clocks.json")
    current_turn = int(campaign_state.get("current_turn", 1))
    turn_id = f"turn_{current_turn:04d}"
    from_time = campaign_state.get("current_time", "")
    from_minutes = run_turn.parse_game_time(from_time)
    to_minutes = None if from_minutes is None else from_minutes + elapsed_minutes
    to_time = from_time if to_minutes is None else run_turn.format_game_time(to_minutes)

    clocks_preview, clock_updates, event_hints = run_turn.advance_clock_preview(
        world_clocks,
        from_minutes,
        to_minutes,
        f"{turn_id}: inferred {inferred_action['action_type']} consumed {elapsed_minutes} minutes",
    )
    context = run_turn.collect_context(root, campaign_state, memory_limit, normalized_action)
    packet = {
        "turn_id": turn_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "player_action": normalized_action,
        "raw_player_input": player_action,
        "inferred_action": inferred_action,
        "elapsed_minutes": elapsed_minutes,
        "campaign_before": {
            "current_turn": campaign_state.get("current_turn"),
            "current_time": campaign_state.get("current_time"),
            "current_scene": campaign_state.get("current_scene"),
            "quests": campaign_state.get("quests", []),
            "rules": campaign_state.get("rules", {}),
            "player_characters": campaign_state.get("player_characters", []),
            "player_resources": context.get("player_resources", {}),
        },
        "time_preview": {"from_time": from_time, "to_time": to_time},
        "world_tick_preview": {
            "clock_updates": clock_updates,
            "offscreen_event_hints": event_hints,
            "requires_visibility_resolution": bool(clock_updates),
        },
        "context": context,
        "gm_input_markdown": "",
        "next_steps": [
            "Resolve visibility before memory writes.",
            "Write only permitted NPC memories.",
            "Extract interpretations and revise understandings.",
            "Apply accepted state patches.",
        ],
    }
    packet["gm_input_markdown"] = run_turn.render_gm_input(packet, root)
    return packet


def visibility_for_source(source: str) -> str:
    return {
        "saw": "direct_visual",
        "heard": "direct_auditory",
        "inferred": "inferred",
        "rumor": "told_by",
    }.get(source, "inferred")


def normalize_visibility_path(value: Any, source: str = "inferred") -> str:
    text = str(value or "").strip()
    aliases = {
        "direct_observation": "direct_visual",
        "direct": "direct_visual",
        "visual": "direct_visual",
        "auditory": "direct_auditory",
        "hearsay": "told_by",
        "rumour": "told_by",
        "rumor": "told_by",
        "public": "public_signal",
        "none": "none",
    }
    text = aliases.get(text, text)
    valid = {
        "direct_visual",
        "direct_auditory",
        "detected_observer",
        "told_by",
        "overheard",
        "inferred",
        "public_signal",
        "none",
    }
    return text if text in valid else visibility_for_source(source)


def normalize_time_delta(value: Any, response: dict[str, Any] | None, packet: dict[str, Any] | None) -> str:
    text = str(value or "").strip()
    packet_elapsed = int((packet or {}).get("elapsed_minutes") or 0)
    if not text or text in {"无", "none", "0"}:
        elapsed = packet_elapsed
    elif "分钟" in text or "小时" in text or "天" in text:
        return text
    else:
        elapsed = int((response or {}).get("elapsed_minutes") or packet_elapsed)
    return "无" if elapsed <= 0 else f"{elapsed} 分钟"


def normalize_relationship_changes(items: Any) -> list[dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        if {"a", "b", "metric", "delta", "reason"}.issubset(item):
            normalized.append(item)
            continue
        a = item.get("a") or item.get("npc_id") or item.get("entity")
        b = item.get("b") or item.get("target_id") or item.get("target") or "pc_main"
        reason = item.get("reason") or item.get("note") or item.get("change") or "AI state update"
        if not a:
            continue
        for metric in ("trust", "fear", "debt", "hostility", "affection", "respect", "suspicion"):
            if metric in item and float(item.get(metric) or 0) != 0:
                normalized.append({"a": a, "b": b, "metric": metric, "delta": item[metric], "reason": reason})
        if not any(metric in item for metric in ("trust", "fear", "debt", "hostility", "affection", "respect", "suspicion")):
            value = item.get("value")
            if value is not None:
                normalized.append({"a": a, "b": b, "metric": "trust", "delta": value, "reason": reason})
    return normalized


def normalize_location_changes(items: Any, packet: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        entity_id = item.get("entity_id") or item.get("owner_id") or item.get("player_id") or ""
        from_loc = item.get("from") or item.get("from_location") or item.get("current_location") or ""
        to_loc = item.get("to") or item.get("to_location") or item.get("new_location") or ""
        reason = item.get("reason") or item.get("evidence") or item.get("note") or item.get("description") or "AI state update"
        if not entity_id or not to_loc:
            continue
        normalized.append({
            "entity_id": str(entity_id),
            "from": str(from_loc),
            "to": str(to_loc),
            "reason": str(reason),
        })
    return normalized



def normalize_inventory_changes(items: Any, packet: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    player_id = "pc_main"
    players = ((packet or {}).get("campaign_before") or {}).get("player_characters") or []
    if players and isinstance(players[0], dict) and players[0].get("id"):
        player_id = players[0]["id"]
    action_map = {
        # English
        "add": "gain",
        "gain": "gain",
        "get": "gain",
        "receive": "gain",
        "remove": "lose",
        "lose": "lose",
        "use": "consume",
        "consume": "consume",
        "open": "consume",
        "damage": "damage",
        "repair": "repair",
        "move": "move",
        # Chinese (AI often outputs Chinese labels)
        "获得": "gain",
        "得到": "gain",
        "拾取": "gain",
        "丢失": "lose",
        "失去": "lose",
        "使用": "consume",
        "消耗": "consume",
        "打开": "consume",
        "损坏": "damage",
        "损坏1": "damage",
        "修复": "repair",
        "修理": "repair",
        "移动": "move",
        "转移": "move",
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        owner_id = item.get("owner_id") or item.get("entity_id") or item.get("player_id") or player_id
        item_id = item.get("item_id") or item.get("item") or item.get("name")
        change = item.get("change") or item.get("action") or "gain"
        change = action_map.get(str(change).lower(), change)
        if change not in {"gain", "lose", "consume", "damage", "repair", "move", "unknown"}:
            change = "gain"
        if not item_id:
            continue
        normalized.append({
            "owner_id": owner_id,
            "item_id": str(item_id),
            "change": change,
            "evidence": item.get("evidence") or item.get("description") or item.get("reason") or "AI state update",
        })
    return normalized


def normalize_player_state_changes(items: Any) -> list[dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    allowed_ops = {"set", "add", "remove", "delta"}
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_field = item.get("field") or item.get("stat") or ""
        field_map = {
            # Chinese -> English (AI often outputs Chinese field names)
            "生命": "health",
            "最大生命": "max_health",
            "灵力": "qi",
            "最大灵力": "max_qi",
            "境界": "realm",
            "境界等级": "realm_level",
            "灵根": "spiritual_root",
            "名称": "name",
            "位置": "location_id",
            "等级": "system_rank",
            "系统等级": "system_rank",
            "特效值": "effect_points",
            "效果点数": "effect_points",
            "特殊效果": "special_effects",
            "特效": "special_effects",
            "描述": "description",
            "身份": "description",
        }
        raw = str(raw_field).strip()
        field = field_map.get(raw, raw)
        if item.get("stat") and not field.startswith("stats."):
            field = f"stats.{field}"
        if not field:
            continue
        change = {
            "entity_id": item.get("entity_id") or item.get("player_id") or "pc_main",
            "field": field,
            "reason": item.get("reason") or item.get("evidence") or item.get("note") or "AI state update",
        }
        operation = item.get("operation")
        if operation in allowed_ops:
            change["operation"] = operation
        elif "delta" in item:
            change["operation"] = "delta"
        elif field in {"condition", "conditions"} and item.get("remove"):
            change["operation"] = "remove"
        else:
            change["operation"] = "set"
        if "delta" in item:
            try:
                change["delta"] = float(item["delta"])
            except (TypeError, ValueError):
                continue
        elif change["operation"] == "delta" and "value" in item:
            try:
                change["delta"] = float(item["value"])
            except (TypeError, ValueError):
                continue
        if "value" in item:
            change["value"] = item["value"]
        elif "condition" in item:
            change["value"] = item["condition"]
        elif "conditions" in item:
            change["value"] = item["conditions"]
        if "value" not in change and "delta" not in change:
            continue
        normalized.append(change)
    return normalized


def parse_profile_name(profile_text: str, fallback: str) -> str:
    for line in profile_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("name:"):
            return stripped.split(":", 1)[1].strip().strip('"').strip("'") or fallback
    return fallback


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(flatten_text(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(flatten_text(item) for item in value.values())
    return ""


def display_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def sentence_containing(text: str, needle: str) -> str:
    index = text.find(needle)
    if index < 0:
        return ""
    start = max(text.rfind(mark, 0, index) for mark in ("。", "！", "？", "\n"))
    end_candidates = [text.find(mark, index) for mark in ("。", "！", "？", "\n")]
    end_candidates = [end for end in end_candidates if end >= 0]
    end = min(end_candidates) if end_candidates else len(text)
    return text[start + 1:end]


def infer_departure_location_changes(
    response: dict[str, Any] | None,
    packet: dict[str, Any] | None,
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not response or not packet:
        return existing
    scene = ((packet.get("campaign_before") or {}).get("current_scene") or {})
    location_id = scene.get("location_id", "unknown")
    present = set(scene.get("present_entities") or [])
    already = {item.get("entity_id") for item in existing if isinstance(item, dict)}
    visible_text = flatten_text(response.get("visible_text"))
    if not visible_text:
        return existing

    departure_words = ("离开", "离去", "走远", "离开视线", "离开感知范围", "不在场", "远去")
    if not any(word in visible_text for word in departure_words):
        return existing
    context = ((packet.get("context") or {}).get("present_npcs") or [])
    inferred = list(existing)
    for npc in context:
        if not isinstance(npc, dict):
            continue
        npc_id = npc.get("id")
        if not npc_id or npc_id not in present or npc_id in already:
            continue
        name = parse_profile_name(str(npc.get("profile_text") or ""), npc_id)
        sentence = sentence_containing(visible_text, name)
        if not sentence:
            continue
        subject_markers = (name, "他", "她", "其", "对方", "这名", "那名")
        has_subject = any(marker in sentence for marker in subject_markers)
        has_departure = any(word in sentence for word in departure_words)
        if has_subject and has_departure:
            inferred.append({
                "entity_id": npc_id,
                "from": location_id,
                "to": "offscreen",
                "reason": f"AI narration says {name} left the active scene",
            })
            already.add(npc_id)
    return inferred


def infer_split_party_location_changes(
    response: dict[str, Any] | None,
    packet: dict[str, Any] | None,
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not packet:
        return existing
    campaign_before = (packet.get("campaign_before") or {})
    scene = campaign_before.get("current_scene") or {}
    location_id = str(scene.get("location_id") or "unknown")
    if location_id in {"", "unknown", "offscreen"}:
        return existing
    text = "\n".join(
        item for item in (
            str(packet.get("player_action") or ""),
            flatten_text((response or {}).get("visible_text")),
        )
        if item
    )
    if not text:
        return existing

    entrance_words = ("谷口", "入口", "原地", "退路", "后方", "外面")
    core_words = ("阵眼", "古阵核心", "阵盘", "核心区域", "自己进入", "独自进入")
    keep_words = ("留在", "留下", "看守", "不要跟", "别跟", "等着")
    if not (
        any(word in text for word in entrance_words)
        and any(word in text for word in core_words)
        and any(word in text for word in keep_words)
    ):
        return existing

    inferred = list(existing)
    already = {item.get("entity_id") for item in inferred if isinstance(item, dict)}
    player_id = first_player_id(packet)
    present = set(scene.get("present_entities") or [])
    if player_id not in already:
        inferred.append(
            {
                "entity_id": player_id,
                "from": location_id,
                "to": f"{location_id}_core",
                "reason": "player entered the active core area while party split at the entrance",
            }
        )
        already.add(player_id)

    for npc in ((packet.get("context") or {}).get("present_npcs") or []):
        if not isinstance(npc, dict):
            continue
        npc_id = npc.get("id")
        if not npc_id or npc_id in already or npc_id not in present:
            continue
        name = parse_profile_name(str(npc.get("profile_text") or ""), str(npc_id))
        sentence = sentence_containing(text, name) or text
        if any(word in sentence for word in keep_words) and any(word in sentence for word in entrance_words):
            inferred.append(
                {
                    "entity_id": str(npc_id),
                    "from": location_id,
                    "to": f"{location_id}_entrance",
                    "reason": f"{name} stayed at the entrance while the player entered the core",
                }
            )
            already.add(npc_id)
    return inferred


def normalize_memory_writes(items: Any) -> list[dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict) or not item.get("npc_id"):
            continue
        memory_obj = item.get("memory") if isinstance(item.get("memory"), dict) else {}
        source = item.get("source") or memory_obj.get("source") or "inferred"
        memory_type = item.get("memory_type") or item.get("type") or memory_obj.get("type") or "episodic"
        if memory_type not in {"episodic", "semantic", "procedural"}:
            memory_type = "episodic"
        memory = memory_obj.get("content") or item.get("memory") or item.get("content") or item.get("text")
        if not memory:
            continue
        if isinstance(memory, (dict, list)):
            memory = json.dumps(memory, ensure_ascii=False)
        normalized_item = {
            "npc_id": canonical_npc_id(item["npc_id"]),
            "memory": str(memory),
            "memory_type": memory_type,
            "source": source if source in {"saw", "heard", "inferred", "rumor"} else "inferred",
            "visibility_path": normalize_visibility_path(
                item.get("visibility_path") or memory_obj.get("visibility_path"),
                source,
            ),
            "confidence": float(item.get("confidence", memory_obj.get("confidence", 0.6))),
            "emotional_valence": float(item.get("emotional_valence", memory_obj.get("emotional_valence", 0))),
            "salience": float(item.get("salience", memory_obj.get("salience", item.get("importance", memory_obj.get("importance", 0.5))))),
            "importance": float(item.get("importance", memory_obj.get("importance", item.get("salience", memory_obj.get("salience", 0.5))))),
            "related_entities": item.get("related_entities") or memory_obj.get("related_entities") or [],
        }
        evidence = item.get("visibility_evidence") or memory_obj.get("visibility_evidence")
        if not isinstance(evidence, dict):
            evidence = {}
        # V17 fix: auto-fill required visibility_evidence fields
        normalized_item["visibility_evidence"] = {
            "observer_id": normalized_item["npc_id"],
            "memory_allowed": True,
            "visibility_path": normalized_item["visibility_path"],
            "event_id": evidence.get("event_id", ""),
            "subjective_summary": evidence.get("subjective_summary", str(memory)[:200]),
            "allowed_memory_scope": evidence.get("allowed_memory_scope", ["observed_event"]),
            "forbidden_memory_scope": evidence.get("forbidden_memory_scope", []),
        }
        normalized.append(normalized_item)
    return normalized


def normalize_interpretation_writes(items: Any) -> list[dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not item.get("npc_id"):
            continue
        interp_obj = item.get("interpretation") if isinstance(item.get("interpretation"), dict) else {}
        text = item.get("text") or item.get("content") or interp_obj.get("content") or interp_obj.get("text")
        if not text:
            continue
        npc_id = item["npc_id"]
        derived_memory = (
            item.get("derived_from_memory_id")
            or (item.get("supporting_memory_ids") or [""])[0]
            or f"mem_{npc_id}_0001"
        )
        normalized.append({
            "id": item.get("id") or f"interp_{npc_id}_{index:04d}",
            "npc_id": npc_id,
            "derived_from_event_id": item.get("derived_from_event_id") or "event_current_turn",
            "derived_from_memory_id": derived_memory,
            "text": text,
            "appraisal": item.get("appraisal") or {
                "goal_impact": "unclear",
                "threat_level": 0.3,
                "opportunity_level": 0.3,
                "agency": "unknown",
                "moral_judgment": "unknown",
                "relationship_signal": "none",
            },
            "emotion": item.get("emotion") or {"label": "none", "valence": 0, "intensity": 0},
            "confidence": float(item.get("confidence", interp_obj.get("confidence", 0.6))),
            "importance": float(item.get("importance", interp_obj.get("importance", 0.5))),
            "related_entities": item.get("related_entities") or interp_obj.get("related_entities") or [],
            "possible_misunderstanding": bool(item.get("possible_misunderstanding", True)),
        })
    return normalized


def normalize_understanding_writes(items: Any) -> list[dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not item.get("npc_id") or not item.get("text"):
            continue
        npc_id = item["npc_id"]
        normalized.append({
            "id": item.get("id") or f"under_{npc_id}_{index:04d}",
            "npc_id": npc_id,
            "type": item.get("type") if item.get("type") in {
                "belief", "attitude", "relationship_judgment", "schema", "plan_rule", "self_understanding"
            } else "belief",
            "text": item["text"],
            "supporting_interpretation_ids": item.get("supporting_interpretation_ids", []),
            "supporting_memory_ids": item.get("supporting_memory_ids", []),
            "contradicting_interpretation_ids": item.get("contradicting_interpretation_ids", []),
            "confidence": float(item.get("confidence", 0.6)),
            "stability": float(item.get("stability", 0.4)),
            "importance": float(item.get("importance", 0.5)),
            "tier": item.get("tier") if item.get("tier") in {"core", "active", "dormant", "archive"} else "active",
            "revision_status": item.get("revision_status") if item.get("revision_status") in {
                "active", "contested", "weakened", "superseded", "archived"
            } else "active",
            "version": int(item.get("version", 1)),
            "last_updated_turn": int(item.get("last_updated_turn", 1)),
            "superseded_by": item.get("superseded_by"),
            "behavior_effect": item.get("behavior_effect", "影响该 NPC 后续判断与行动。"),
        })
    return normalized


def normalize_revision_writes(items: Any) -> list[dict[str, Any]]:
    """Normalize npc_revision_writes from AI response, dropping non-dict items."""
    normalized = []
    if not isinstance(items, list):
        return normalized
    VALID_EFFECTS = {
        "supports", "weakens", "contradicts", "qualifies",
        "reframes", "supersedes", "splits", "no_change",
    }
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not item.get("npc_id"):
            continue
        npc_id = item["npc_id"]
        effect = item.get("effect", "no_change")
        if effect not in VALID_EFFECTS:
            effect = "no_change"
        normalized.append({
            "id": item.get("id") or f"rev_{npc_id}_{index:04d}",
            "npc_id": npc_id,
            "turn": int(item.get("turn", 1)),
            "new_event_id": item.get("new_event_id", ""),
            "target_understanding_id": item.get("target_understanding_id", ""),
            "effect": effect,
            "evidence_strength": float(item.get("evidence_strength", 0.5)),
            "confidence_delta": float(item.get("confidence_delta", 0.0)),
            "stability_delta": float(item.get("stability_delta", 0.0)),
            "new_status": item.get("new_status"),
            "reason": str(item.get("reason", "")),
            "source_interpretation_ids": item.get("source_interpretation_ids", []),
            "new_understanding_id": item.get("new_understanding_id"),
        })
    return normalized


def normalize_open_threads(items: Any) -> list[dict[str, Any]]:
    normalized = []
    if not isinstance(items, list):
        return normalized
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        thread = item.get("thread") or item.get("description") or item.get("summary") or item.get("title") or item.get("note") or item.get("id")
        if looks_like_thread_id(thread) and (item.get("description") or item.get("summary") or item.get("title") or item.get("note")):
            thread = item.get("description") or item.get("summary") or item.get("title") or item.get("note")
        if not thread:
            continue
        thread_key = re.sub(r"\s+", "", str(thread).strip().lower())
        if thread_key in seen:
            continue
        seen.add(thread_key)
        pressure = item.get("next_pressure") or item.get("pressure") or item.get("note") or item.get("summary") or item.get("description") or "后续局势继续推进。"
        normalized.append({
            "thread": thread,
            "next_pressure": pressure,
        })
        if len(normalized) >= MAX_NEW_OPEN_THREADS:
            break
    return normalized


def looks_like_thread_id(value: Any) -> bool:
    return bool(re.fullmatch(r"(open_)?thread_\d+", str(value or "").strip()))


def unresolved_from_response(response: dict[str, Any] | None) -> list[str]:
    visible = response.get("visible_text") if isinstance(response, dict) else {}
    summary = visible.get("state_summary") if isinstance(visible, dict) else {}
    return [
        str(item).strip()
        for item in (summary.get("unresolved") if isinstance(summary, dict) else []) or []
        if str(item).strip()
    ]


def first_player_id(packet: dict[str, Any] | None) -> str:
    players = ((packet or {}).get("campaign_before") or {}).get("player_characters") or []
    if isinstance(players, list):
        for player in players:
            if isinstance(player, dict) and player.get("id"):
                return str(player["id"])
    return "pc_main"


def append_inferred_effect_point_rewards(
    changes: list[dict[str, Any]],
    response: dict[str, Any] | None,
    packet: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    visible_text = flatten_text((response or {}).get("visible_text"))
    if not visible_text:
        return changes
    has_positive_effect_delta = any(
        item.get("field") == "effect_points"
        and item.get("operation") == "delta"
        and float(item.get("delta", item.get("value", 0)) or 0) > 0
        for item in changes
        if isinstance(item, dict)
    )
    if has_positive_effect_delta:
        return changes
    reward = 0
    patterns = (
        r"(?:获得|增加|奖励)[^。；，\n]{0,12}?(\d+)\s*点?特效值",
        r"特效值[^。；，\n]{0,8}?(?:获得|增加|奖励)\s*(\d+)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, visible_text):
            reward = max(reward, int(match.group(1)))
    if reward <= 0:
        return changes
    return [
        *changes,
        {
            "entity_id": first_player_id(packet),
            "field": "effect_points",
            "operation": "delta",
            "delta": reward,
            "reason": "inferred from visible reward text",
        },
    ]


REALM_LEVEL_TO_NAME = {
    1: '炼气一层', 2: '炼气二层', 3: '炼气三层',
    4: '炼气四层', 5: '炼气五层', 6: '炼气六层',
    7: '炼气七层', 8: '炼气八层', 9: '炼气九层',
    10: '筑基初期', 11: '筑基中期', 12: '筑基后期',
    13: '金丹初期', 14: '金丹中期', 15: '金丹后期',
    16: '元婴初期', 17: '元婴中期', 18: '元婴后期',
    19: '化神期', 20: '渡劫期',
}
REALM_NAME_TO_LEVEL = {v: k for k, v in REALM_LEVEL_TO_NAME.items()}
CHINESE_NUM_MAP = {
    '零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
}
STAT_NAME_MAP = {
    '战力': 'stats.combat', '战斗': 'stats.combat',
    '感知': 'stats.perception',
    '社交': 'stats.social',
}
QI_FROM_TO_PAT = re.compile(
    r'灵力(?:\u4ece|\u7531)\s*(\d+)\s*/\s*(\d+)\s*'
    r'(?:\u63d0\u5347\u5230|\u63d0\u5347\u81f3|\u6da8\u5230|\u6da8\u81f3|'
    r'\u589e\u81f3|\u589e\u52a0\u5230|\u6062\u590d\u81f3|\u6062\u590d\u5230)\s*(\d+)\s*/\s*(\d+)'
)
HEALTH_FROM_TO_PAT = re.compile(
    r'\u751f\u547d(?:\u4ece|\u7531)\s*(\d+)\s*/\s*(\d+)\s*'
    r'(?:\u964d\u5230|\u964d\u81f3|\u51cf\u5c11\u5230|\u53d8\u4e3a|\u53d8\u6210|'
    r'\u63d0\u5347\u5230|\u63d0\u5347\u81f3|\u6da8\u5230|\u6062\u590d\u81f3|\u6062\u590d\u5230)\s*(\d+)\s*/\s*(\d+)'
)
REALM_BREAK_PAT = re.compile(
    r'\u7a81\u7834(?:\u81f3|\u5230\u4e86|\u5230)\s*'
    r'(\u70bc\u6c14[\u671f\u5c42]?\s*\d+|'
    r'\u7b51\u57fa[\u671f]?\s*[\u521d\u4e2d\u540e]|'
    r'\u91d1\u4e39[\u671f]?\s*[\u521d\u4e2d\u540e]|'
    r'\u5143\u5a74[\u671f]?\s*[\u521d\u4e2d\u540e]|'
    r'\u5316\u795e[\u671f]?|\u6e21\u52ab[\u671f]?)'
)
STAT_PLUS_PAT = re.compile(r'(\u6218\u529b|\u6218\u6597|\u611f\u77e5|\u793e\u4ea4)\s*[+\uff0b]\s*(\d+)')
CONSUME_PAT = re.compile(
    r'\u6d88\u8017(?:\u4e86|\u6389)?\s*(?:\u7ea6|\u5927\u6982)?\s*(\d+|[{nums}])\s*'
    r'(?:\u5757|\u679a|\u9897|\u5f20|\u5305|\u74f6|\u682a|\u67c4|\u628a)\s*'
    r'(\u7075\u77f3|\u7075\u7802|\u8349\u836f|\u7b26[\u7bb8\u7c59]|\u4e39\u836f|\u4e39[\u836f\u85e5])'
    .format(nums=''.join(CHINESE_NUM_MAP.keys()))
)

def parse_chinese_number(text):
    if not text:
        return None
    text = text.strip()
    try:
        return int(text)
    except ValueError:
        pass
    if text in CHINESE_NUM_MAP:
        return CHINESE_NUM_MAP[text]
    return None

def parse_realm_level(realm_text):
    realm_text = realm_text.strip()
    if realm_text in REALM_NAME_TO_LEVEL:
        return REALM_NAME_TO_LEVEL[realm_text]
    qi_pat = re.compile(r'\u70bc\u6c14[\u671f\u5c42]?\s*(\d+)')
    match = qi_pat.search(realm_text)
    if match:
        return int(match.group(1))
    return None

def append_inferred_state_changes_from_narrative(
    changes, inventory_changes, response, packet,
):
    visible_text = flatten_text((response or {}).get('visible_text'))
    if not visible_text:
        return changes, inventory_changes
    player_id = first_player_id(packet)
    existing = {str(c.get('field')) for c in changes if isinstance(c, dict) and c.get('field')}

    # Qi extraction
    if 'qi' not in existing:
        for m in QI_FROM_TO_PAT.finditer(visible_text):
            old_qi, old_max, new_qi, new_max = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            qi_delta = new_qi - old_qi
            if qi_delta != 0:
                changes.append({'entity_id': player_id, 'field': 'qi', 'operation': 'delta',
                    'delta': qi_delta, 'reason': f'narrative: qi {old_qi}/{old_max} -> {new_qi}/{new_max}'})
            break

    # Health extraction
    if 'health' not in existing:
        for m in HEALTH_FROM_TO_PAT.finditer(visible_text):
            groups = m.groups()
            old_hp = int(groups[0])
            # groups may have 2 or 4 elements depending on whether /max was present
            new_hp = int(groups[2]) if len(groups) >= 4 and groups[2] is not None else int(groups[1]) if len(groups) >= 2 and groups[1] is not None else old_hp
            hp_delta = new_hp - old_hp
            if hp_delta != 0:
                changes.append({'entity_id': player_id, 'field': 'health', 'operation': 'delta',
                    'delta': hp_delta, 'reason': f'narrative: health {old_hp} -> {new_hp}'})
            break

    # Realm extraction
    if 'realm_level' not in existing and 'realm' not in existing:
        m = REALM_BREAK_PAT.search(visible_text)
        if m:
            realm_name = m.group(1)
            new_level = parse_realm_level(realm_name)
            if new_level is not None:
                changes.append({'entity_id': player_id, 'field': 'realm_level', 'operation': 'set',
                    'value': new_level, 'reason': f'narrative: breakthrough to {realm_name}'})
                changes.append({'entity_id': player_id, 'field': 'realm', 'operation': 'set',
                    'value': realm_name, 'reason': f'narrative: breakthrough to {realm_name}'})
                existing.update(['realm_level', 'realm'])

    # Stat extraction
    for m in STAT_PLUS_PAT.finditer(visible_text):
        stat_name, delta = m.group(1), int(m.group(2))
        field = STAT_NAME_MAP.get(stat_name)
        if field and field not in existing:
            changes.append({'entity_id': player_id, 'field': field, 'operation': 'delta',
                'delta': delta, 'reason': f'narrative: {stat_name}+{delta}'})
            existing.add(field)

    # Inventory consumption extraction
    existing_inv = {str(c.get('item_id','')).split('(')[0].strip().rstrip('0123456789')
        for c in inventory_changes if isinstance(c, dict)}
    for m in CONSUME_PAT.finditer(visible_text):
        qty_text, item_type = m.group(1), m.group(2)
        qty = parse_chinese_number(qty_text) or 1
        if item_type and item_type not in existing_inv:
            inventory_changes.append({'owner_id': player_id,
                'item_id': f'{item_type}(-{qty})', 'change': 'consume',
                'quantity': qty, 'evidence': f'narrative: consumed {qty} {item_type}'})
            existing_inv.add(item_type)

    return changes, inventory_changes


def normalize_patch(value: Any, response: dict[str, Any] | None = None, packet: dict[str, Any] | None = None) -> dict[str, Any]:
    patch = dict(DEFAULT_PATCH)
    if isinstance(value, dict):
        for key in patch:
            if key in value:
                patch[key] = value[key]
    patch["time_delta"] = normalize_time_delta(patch.get("time_delta"), response, packet)
    patch["inventory_changes"] = normalize_inventory_changes(patch.get("inventory_changes"), packet)
    normalized_locs = normalize_location_changes(patch.get("location_changes"), packet)
    patch["location_changes"] = infer_departure_location_changes(
        response,
        packet,
        normalized_locs,
    )
    patch["location_changes"] = infer_split_party_location_changes(
        response,
        packet,
        patch["location_changes"],
    )
    patch["relationship_changes"] = normalize_relationship_changes(patch.get("relationship_changes"))
    patch["new_facts"] = [
        {
            "fact": item.get("fact") or item.get("text"),
            "visibility": item.get("visibility", "private"),
            "source": item.get("source", "AI state extraction"),
        }
        for item in patch.get("new_facts", [])
        if isinstance(item, dict) and (item.get("fact") or item.get("text"))
    ]
    patch["player_state_changes"] = append_inferred_effect_point_rewards(
        normalize_player_state_changes(patch.get("player_state_changes")),
        response,
        packet,
    )
    patch["player_state_changes"], patch["inventory_changes"] = append_inferred_state_changes_from_narrative(
        patch["player_state_changes"],
        patch["inventory_changes"],
        response,
        packet,
    )
    patch["npc_memory_writes"] = normalize_memory_writes(patch.get("npc_memory_writes"))
    patch["npc_interpretation_writes"] = normalize_interpretation_writes(patch.get("npc_interpretation_writes"))
    patch["npc_understanding_writes"] = normalize_understanding_writes(patch.get("npc_understanding_writes"))
    patch["npc_revision_writes"] = normalize_revision_writes(patch.get("npc_revision_writes"))
    patch["open_threads"] = normalize_open_threads(patch.get("open_threads"))
    unresolved = unresolved_from_response(response)
    for thread in patch["open_threads"]:
        if looks_like_thread_id(thread.get("thread")) and unresolved:
            replacement = unresolved.pop(0)
            thread["thread"] = replacement
            if thread.get("next_pressure") in {"后续局势继续推进。", "", None}:
                thread["next_pressure"] = replacement
    return patch


def save_turn_artifacts(root: Path, packet: dict[str, Any], ai_response: dict[str, Any], patch: dict[str, Any], apply_report: dict[str, Any] | None = None) -> Path:
    turn_id = packet["turn_id"]
    out_dir = root / "campaign" / "ai_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "packet": packet,
        "ai_response": ai_response,
        "state_patch": patch,
    }
    if apply_report is not None:
        artifact["apply_report"] = apply_report
    path = out_dir / f"{turn_id}.json"
    save_json(path, artifact)
    return path


def apply_state_patch(config: GameConfig, patch: dict[str, Any]) -> dict[str, Any]:
    errors = patcher.validate_patch_structure(patch)
    if errors:
        return {"applied": False, "errors": errors}
    campaign = patcher.load_json(config.root / "campaign" / "campaign_state.json")
    current_turn = int(campaign.get("current_turn", 1))
    current_time = campaign.get("current_time", "unknown")
    report = patcher.apply_patch(
        config.root,
        patch,
        current_turn,
        current_time,
        "0001",
        dry_run=not config.auto_apply,
    )
    errors = report.get("errors", []) if isinstance(report, dict) else []
    return {"applied": config.auto_apply and not errors, "report": report}


def render_visible(response: dict[str, Any]) -> str:
    visible = response.get("visible_text") or {}
    if isinstance(visible, str):
        return visible
    if not isinstance(visible, dict):
        return display_text(response)
    scene = display_text(visible.get("scene", ""))
    action_result = display_text(visible.get("action_result", ""))
    reaction = display_text(visible.get("reaction", ""))
    npc_actions = visible.get("npc_actions", [])
    world_motion = display_text(visible.get("world_motion", ""))
    tension = display_text(visible.get("tension", ""))
    clues = visible.get("actionable_clues", [])
    check = display_text(visible.get("check", "无"))
    state_summary = visible.get("state_summary") or {}
    lines = []
    if scene:
        lines.extend(["### 场景", scene, ""])
    if action_result:
        lines.extend(["### 行动结果", action_result, ""])
    if reaction:
        lines.extend(["### 反应", reaction, ""])
    if npc_actions:
        lines.append("### NPC 动作")
        for item in npc_actions:
            lines.append(f"- {display_text(item)}")
        lines.append("")
    if world_motion or tension:
        lines.append("### 局势推进")
        if world_motion:
            lines.append(world_motion)
        if tension:
            lines.append("")
            lines.append(f"当前压力：{tension}")
        lines.append("")
    if clues:
        lines.append("### 可行动线索")
        for item in clues:
            lines.append(f"- {display_text(item)}")
        lines.append("")
    lines.extend(["### 需要检定", check or "无"])
    if state_summary:
        lines.extend(["", "### 状态变化"])
        for key, label in [("time", "时间"), ("memory", "记忆/态度"), ("quests", "任务")]:
            if state_summary.get(key):
                lines.append(f"- {label}：{display_text(state_summary[key])}")
        unresolved = state_summary.get("unresolved") or []
        if unresolved:
            lines.append("- 未解决悬念：")
            for item in unresolved:
                lines.append(f"  - {display_text(item)}")
    return "\n".join(lines).strip()


def strip_wrapping_quotes(text: str) -> str:
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"', "“", "”"}:
        return stripped[1:-1].strip()
    return stripped


def looks_like_worldgen_request(text: str) -> bool:
    cleaned = strip_wrapping_quotes(text)
    markers = ("玩家是", "世界观", "设定", "开局", "魂穿", "系统", "废城", "修仙", "赛博")
    action_verbs = ("我 ", "我要", "我想", "观察", "询问", "攻击", "移动", "调查", "检查", "打开", "跟")
    if any(cleaned.startswith(verb) for verb in action_verbs):
        return False
    return len(cleaned) >= 8 and any(marker in cleaned for marker in markers)


def run_ai_turn(config: GameConfig, player_action: str, elapsed_minutes: int | None, memory_limit: int) -> dict[str, Any]:
    packet = build_turn_packet(config.root, player_action, elapsed_minutes, memory_limit)
    runner_prompt_path = config.root / "prompts" / "ai-game-runner.md"
    if not runner_prompt_path.exists():
        runner_prompt_path = PROJECT_ROOT / "prompts" / "ai-game-runner.md"
    runner_prompt = read_text(runner_prompt_path)
    messages = [
        {"role": "system", "content": runner_prompt},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "run_one_game_turn",
                    "turn_packet": packet,
                    "required_patch_keys": list(DEFAULT_PATCH),
                    "action_inference_policy": (
                        "The local runner has already inferred action_type and elapsed_minutes "
                        "from the player's natural language input. Use turn_packet.inferred_action "
                        "as the default unless the fiction strongly proves it wrong."
                    ),
                },
                ensure_ascii=False,
            ),
        },
    ]

    response: dict[str, Any] = {}
    tool_results: list[dict[str, Any]] = []
    for _ in range(config.max_tool_rounds + 1):
        raw = call_chat_api(config, messages)
        response = parse_ai_json(raw)
        requests = response.get("tool_requests") or []
        if not requests:
            break
        tool_results = [run_tool(config, request) for request in requests]
        messages.append({"role": "assistant", "content": json.dumps(response, ensure_ascii=False)})
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    {"tool_results": tool_results, "instruction": "Finish the turn JSON now if possible."},
                    ensure_ascii=False,
                ),
            }
        )

    patch = normalize_patch(response.get("state_patch"), response, packet)
    try:
        apply_report = apply_state_patch(config, patch)
    except Exception as exc:
        apply_report = {
            "applied": False,
            "errors": [f"state patch apply failed: {exc}"],
        }
    artifact_path = save_turn_artifacts(config.root, packet, response, patch, apply_report)
    return {
        "packet": packet,
        "response": response,
        "patch": patch,
        "artifact_path": artifact_path,
        "apply_report": apply_report,
        "tool_results": tool_results,
    }


def interactive_loop(config: GameConfig, args: argparse.Namespace) -> None:
    print("Paotuan AI RPG 已启动。输入 /new 主题 创建新世界，/quit 退出，/validate 校验项目。")
    print(f"模型: {config.model} | API: {config.base_url} | 自动写回: {config.auto_apply}")
    first_input = True
    while True:
        try:
            action = input("\n你> ").strip()
        except EOFError:
            break
        if not action:
            continue
        if action in {"/quit", "/exit"}:
            break
        if action == "/validate":
            print(tool_validate_project(config, {})["stdout"])
            continue

        new_theme = None
        if action.startswith("/new "):
            new_theme = action.removeprefix("/new ").strip()
        elif first_input and looks_like_worldgen_request(action):
            new_theme = strip_wrapping_quotes(action)

        if new_theme:
            target_root = (args.new_root or (PROJECT_ROOT / "generated_campaigns" / slugify(new_theme))).resolve()
            world = run_worldgen(config, new_theme, target_root, force=True)
            config.root = target_root
            print(f"\n[本地] 已创建并切换到新战役: {target_root}")
            if world.get("opening_prompt"):
                print("\n开场：")
                print(world["opening_prompt"])
            first_input = False
            continue

        result = run_ai_turn(config, action, args.elapsed_minutes, args.memory_limit)
        print("\nGM>")
        print(render_visible(result["response"]))
        print(f"\n[本地] 回合记录: {result['artifact_path']}")
        if result["apply_report"].get("errors"):
            print(f"[本地] patch 未写入: {result['apply_report']['errors']}")
        elif result["apply_report"].get("applied"):
            print("[本地] 状态已写回。")
        else:
            print("[本地] dry-run，状态未写回。")
        first_input = False


def main() -> None:
    parser = argparse.ArgumentParser(description="Play paotuan as an AI-powered local game.")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="Project/campaign root.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--no-apply", action="store_true", help="Do not write state patches.")
    parser.add_argument("--mock", action="store_true", help="Run without an API call for local smoke tests.")
    parser.add_argument("--elapsed-minutes", type=int, default=None, help="Override automatic elapsed-time inference.")
    parser.add_argument("--memory-limit", type=int, default=8)
    parser.add_argument("--once", help="Run one player action and exit.")
    parser.add_argument("--new", help="Generate a new campaign from this theme before playing.")
    parser.add_argument("--new-root", type=Path, default=None, help="Directory for the generated campaign project.")
    parser.add_argument("--force-new", action="store_true", help="Overwrite an existing generated campaign directory.")
    args = parser.parse_args()

    root = args.root.resolve()
    config = load_config(root, args)
    if args.mock:
        config.model = "__mock__"
        config.api_key = ""
    if args.new:
        target_root = (args.new_root or (root / "generated_campaigns" / slugify(args.new))).resolve()
        world = run_worldgen(config, args.new, target_root, args.force_new)
        print(f"新战役已生成: {target_root}")
        if world.get("opening_prompt"):
            print("\n开场：")
            print(world["opening_prompt"])
        config = load_config(root, args)
        config.root = target_root
        if args.mock:
            config.model = "__mock__"
            config.api_key = ""
    elif args.once and looks_like_worldgen_request(args.once):
        theme = strip_wrapping_quotes(args.once)
        target_root = (args.new_root or (root / "generated_campaigns" / slugify(theme))).resolve()
        world = run_worldgen(config, theme, target_root, force=True)
        print(f"新战役已生成: {target_root}")
        if world.get("opening_prompt"):
            print("\n开场：")
            print(world["opening_prompt"])
        config.root = target_root
        if args.mock:
            config.model = "__mock__"
            config.api_key = ""
        args.once = "我观察周围"
    if args.once:
        result = run_ai_turn(config, args.once, args.elapsed_minutes, args.memory_limit)
        print(render_visible(result["response"]))
        print(f"\n[本地] 回合记录: {result['artifact_path']}")
    else:
        interactive_loop(config, args)


if __name__ == "__main__":
    main()
