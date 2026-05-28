#!/usr/bin/env python3
"""Track and validate faction/NPC resources, cooldowns, and costs.

Resources are stored in campaign/resources.json per entity.
This tool supports list, check, and consume operations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RESOURCE_SCHEMA: dict[str, dict[str, Any]] = {
    "faction": {
        "required": ["money", "manpower", "risk_level"],
        "optional": {
            "supplies": [],
            "cooldowns": {},
            "reputation": 0,
        },
    },
    "npc": {
        "required": ["money", "risk_tolerance"],
        "optional": {
            "stamina": 10,
            "supplies": [],
            "cooldowns": {},
        },
    },
}


def load_resources(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return {"entities": {}}


def save_resources(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_entity(data: dict[str, Any], entity_id: str, entity_type: str) -> dict[str, Any]:
    entities = data.setdefault("entities", {})
    if entity_id not in entities:
        schema = RESOURCE_SCHEMA.get(entity_type, {})
        entity = {"type": entity_type}
        for field in schema.get("required", []):
            entity[field] = 0
        for field, default in schema.get("optional", {}).items():
            entity[field] = default.copy() if isinstance(default, (dict, list)) else default
        entities[entity_id] = entity
    return entities[entity_id]


def list_resources(data: dict[str, Any]) -> None:
    for eid, entity in data.get("entities", {}).items():
        etype = entity.get("type", "?")
        money = entity.get("money", 0)
        mp = entity.get("manpower", "-")
        risk = entity.get("risk_level", entity.get("risk_tolerance", "-"))
        cd = entity.get("cooldowns", {})
        cd_str = ", ".join(f"{k}:{v}" for k, v in cd.items()) if cd else "none"
        print(f"  {eid} [{etype}] money={money} manpower={mp} risk={risk} cooldowns=[{cd_str}]")


def check_resource(data: dict[str, Any], entity_id: str, field: str) -> str:
    entity = data.get("entities", {}).get(entity_id, {})
    val = entity.get(field, f"(not set)")
    return str(val)


def consume(data: dict[str, Any], entity_id: str, field: str, amount: int) -> tuple[bool, str]:
    entity = data.get("entities", {}).get(entity_id)
    if not entity:
        return False, f"Entity '{entity_id}' not found"
    current = entity.get(field, 0)
    if not isinstance(current, (int, float)):
        return False, f"Field '{field}' is not numeric: {current}"
    if current < amount:
        return False, f"Insufficient {field}: have {current}, need {amount}"
    entity[field] = current - amount
    return True, f"{field}: {current} -> {entity[field]} (consumed {amount})"


def add_cooldown(data: dict[str, Any], entity_id: str, action: str, turns: int) -> str:
    entity = data.get("entities", {}).get(entity_id)
    if not entity:
        return f"Entity '{entity_id}' not found"
    entity.setdefault("cooldowns", {})[action] = turns
    return f"Set cooldown '{action}' = {turns} turns for '{entity_id}'"


def tick_cooldowns(data: dict[str, Any]) -> list[str]:
    messages = []
    for eid, entity in data.get("entities", {}).items():
        cds = entity.get("cooldowns", {})
        for action in list(cds):
            if cds[action] > 0:
                cds[action] -= 1
                messages.append(f"{eid}: {action} cooldown {cds[action]+1} -> {cds[action]}")
            if cds[action] <= 0:
                del cds[action]
                messages.append(f"{eid}: {action} cooldown cleared")
    return messages


def main():
    parser = argparse.ArgumentParser(description="Track faction/NPC resources and cooldowns.")
    parser.add_argument("--file", type=Path, default=Path("campaign/resources.json"))
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list")
    list_p.add_argument("--file", type=Path, default=Path("campaign/resources.json"))
    sp = check_p = sub.add_parser("check")
    check_p.add_argument("--file", type=Path, default=Path("campaign/resources.json"))
    sp.add_argument("entity_id")
    sp.add_argument("field")
    sp = consume_p = sub.add_parser("consume")
    consume_p.add_argument("--file", type=Path, default=Path("campaign/resources.json"))
    sp.add_argument("entity_id")
    sp.add_argument("field")
    sp.add_argument("amount", type=int)
    sp = cooldown_p = sub.add_parser("cooldown")
    cooldown_p.add_argument("--file", type=Path, default=Path("campaign/resources.json"))
    sp.add_argument("entity_id")
    sp.add_argument("action")
    sp.add_argument("turns", type=int)
    sp = tick_p = sub.add_parser("tick")
    tick_p.add_argument("--file", type=Path, default=Path("campaign/resources.json"))
    sp = ensure_p = sub.add_parser("ensure")
    ensure_p.add_argument("--file", type=Path, default=Path("campaign/resources.json"))
    sp.add_argument("entity_id")
    sp.add_argument("--type", default="faction", choices=["faction", "npc"])
    sp.add_argument("--write", action="store_true")

    args = parser.parse_args()
    data = load_resources(args.file)

    if args.command == "list":
        list_resources(data)
    elif args.command == "check":
        print(check_resource(data, args.entity_id, args.field))
    elif args.command == "consume":
        ok, msg = consume(data, args.entity_id, args.field, args.amount)
        print(msg)
        if ok:
            save_resources(args.file, data)
        else:
            exit(1)
    elif args.command == "cooldown":
        print(add_cooldown(data, args.entity_id, args.action, args.turns))
        save_resources(args.file, data)
    elif args.command == "tick":
        msgs = tick_cooldowns(data)
        for m in msgs:
            print(m)
        save_resources(args.file, data)
    elif args.command == "ensure":
        entity = ensure_entity(data, args.entity_id, args.type)
        print(f"Ensured {args.entity_id} [{args.type}]")
        if args.write:
            save_resources(args.file, data)


if __name__ == "__main__":
    main()
