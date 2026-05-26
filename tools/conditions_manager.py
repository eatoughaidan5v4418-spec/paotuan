#!/usr/bin/env python3
"""Character conditions tracker.

Manages conditions (injured, exhausted, poisoned, etc.) for PCs and NPCs.
Stored in campaign/conditions.json alongside campaign_state.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

KNOWN_CONDITIONS = {
    # Physical
    "injured": {"severity": "moderate", "effect": "体力行动劣势", "recovery": "休息或治疗"},
    "wounded": {"severity": "severe", "effect": "所有行动劣势，持续恶化", "recovery": "紧急治疗"},
    "exhausted": {"severity": "moderate", "effect": "体力消耗加倍", "recovery": "完整休息"},
    "poisoned": {"severity": "moderate", "effect": "每时辰恶化", "recovery": "解毒"},
    # Mental/Spiritual
    "shaken": {"severity": "light", "effect": "意志检定劣势", "recovery": "短暂休息"},
    "traumatized": {"severity": "severe", "effect": "触发相关场景时失控", "recovery": "长期休息或剧情"},
    # Cultivation-specific
    "qi_depleted": {"severity": "moderate", "effect": "无法使用中品以上法术", "recovery": "调息恢复灵力"},
    "qi_deviation": {"severity": "severe", "effect": "灵力失控，每次施法可能反噬", "recovery": "闭关调息或丹药"},
}


def load_conditions(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return {"entities": {}}


def save_conditions(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add_condition(data: dict[str, Any], entity_id: str, condition: str, note: str = "") -> str:
    entities = data.setdefault("entities", {})
    entity = entities.setdefault(entity_id, {"conditions": [], "history": []})
    for c in entity["conditions"]:
        if c["name"] == condition:
            return f"'{entity_id}' already has '{condition}'"
    info = KNOWN_CONDITIONS.get(condition, {"severity": "unknown", "effect": "待定", "recovery": "待定"})
    entity["conditions"].append({"name": condition, "severity": info["severity"], "added_at": note})
    entity.setdefault("history", []).append(f"+{condition}: {note}" if note else f"+{condition}")
    return f"Added '{condition}' to '{entity_id}'"


def remove_condition(data: dict[str, Any], entity_id: str, condition: str, note: str = "") -> str:
    entities = data.get("entities", {})
    entity = entities.get(entity_id, {})
    conds = entity.get("conditions", [])
    for i, c in enumerate(conds):
        if c["name"] == condition:
            conds.pop(i)
            entity.setdefault("history", []).append(f"-{condition}: {note}" if note else f"-{condition}")
            return f"Removed '{condition}' from '{entity_id}'"
    return f"'{entity_id}' does not have '{condition}'"


def list_conditions(data: dict[str, Any]) -> None:
    for eid, entity in data.get("entities", {}).items():
        conds = entity.get("conditions", [])
        if conds:
            labels = [f"{c['name']}({c['severity']})" for c in conds]
            print(f"  {eid}: {', '.join(labels)}")
    if not data.get("entities"):
        print("  (no conditions tracked)")


def main():
    parser = argparse.ArgumentParser(description="Character conditions tracker.")
    parser.add_argument("--file", type=Path, default=Path("campaign/conditions.json"))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")
    sp = sub.add_parser("add")
    sp.add_argument("entity_id")
    sp.add_argument("condition")
    sp.add_argument("--note", default="")
    sp = sub.add_parser("remove")
    sp.add_argument("entity_id")
    sp.add_argument("condition")
    sp.add_argument("--note", default="")
    sp = sub.add_parser("known")

    args = parser.parse_args()
    data = load_conditions(args.file)

    if args.command == "list":
        list_conditions(data)
    elif args.command == "add":
        print(add_condition(data, args.entity_id, args.condition, args.note))
        save_conditions(args.file, data)
    elif args.command == "remove":
        print(remove_condition(data, args.entity_id, args.condition, args.note))
        save_conditions(args.file, data)
    elif args.command == "known":
        for name, info in KNOWN_CONDITIONS.items():
            print(f"  {name}: {info['effect']} (recovery: {info['recovery']})")


if __name__ == "__main__":
    main()
