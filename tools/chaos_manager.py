#!/usr/bin/env python3
"""Chaos factor manager (Mythic GME-style) + dice roller.

Tools:
  chaos.py scene-check  -- roll 1d10 vs chaos factor
  chaos.py adjust +1    -- increase chaos by N
  chaos.py adjust -2    -- decrease chaos by N
  chaos.py show         -- display current chaos
  chaos.py roll d20     -- basic dice roll
  chaos.py roll d20 --advantage
  chaos.py oracle       -- roll on a simple yes/no oracle
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


def load_chaos(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return {"chaos_level": 5, "min": 1, "max": 10, "history": []}


def save_chaos(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def scene_check(chaos_level: int) -> tuple[str, int]:
    """Roll 1d10 vs chaos. Returns (result_label, roll_value)."""
    roll = random.randint(1, 10)
    if roll <= chaos_level // 2:
        return "interrupt", roll
    elif roll <= chaos_level:
        return "altered", roll
    else:
        return "expected", roll


def roll_dice(dice_str: str, advantage: bool = False, disadvantage: bool = False) -> tuple[int, str]:
    """Parse and roll dice like 'd20', '2d6', 'd100'. Returns (total, detail)."""
    import re
    m = re.match(r"(\d+)?d(\d+)", dice_str.lower())
    if not m:
        raise ValueError(f"Invalid dice: {dice_str}. Use format like d20, 2d6, d100.")
    count = int(m.group(1) or 1)
    sides = int(m.group(2))
    rolls = [random.randint(1, sides) for _ in range(count)]
    if advantage and sides == 20:
        rolls = [max(random.randint(1, sides), random.randint(1, sides))]
    elif disadvantage and sides == 20:
        rolls = [min(random.randint(1, sides), random.randint(1, sides))]
    total = sum(rolls)
    detail = f"{dice_str} -> {rolls} = {total}"
    if advantage:
        detail += " (advantage)"
    elif disadvantage:
        detail += " (disadvantage)"
    return total, detail


def oracle(odds: str = "50/50") -> tuple[str, int]:
    """Simple yes/no oracle. odds: 'likely', '50/50', 'unlikely', 'impossible', 'sure_thing'."""
    roll = random.randint(1, 100)
    thresholds = {
        "impossible": 10,      # 10% yes
        "unlikely": 30,        # 30% yes
        "50/50": 50,           # 50% yes
        "likely": 70,          # 70% yes
        "sure_thing": 90,      # 90% yes
    }
    threshold = thresholds.get(odds, 50)
    if roll <= threshold // 10:
        return "exceptional_yes", roll
    elif roll <= threshold:
        return "yes", roll
    elif roll <= threshold + (100 - threshold) // 2:
        return "no", roll
    else:
        return "exceptional_no", roll


def main():
    parser = argparse.ArgumentParser(description="Chaos factor manager + dice roller.")
    parser.add_argument("--file", type=Path, default=Path("campaign/chaos_factor.json"))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("show")
    sp = sub.add_parser("adjust")
    sp.add_argument("delta", type=int)
    sp.add_argument("--reason", default="")
    sp = sub.add_parser("scene-check")
    sp = sub.add_parser("roll")
    sp.add_argument("dice", default="d20", nargs="?")
    sp.add_argument("--advantage", action="store_true")
    sp.add_argument("--disadvantage", action="store_true")
    sp = sub.add_parser("oracle")
    sp.add_argument("--odds", default="50/50", choices=["impossible", "unlikely", "50/50", "likely", "sure_thing"])

    args = parser.parse_args()
    data = load_chaos(args.file)

    if args.command == "show":
        level = data["chaos_level"]
        bar = "#" * level + "-" * (10 - level)
        print(f"Chaos: [{bar}] {level}/10")
        print("History:")
        for h in data.get("history", [])[-5:]:
            print(f"  turn {h['turn']}: {h['from']} -> {h['to']} ({h['reason']})")

    elif args.command == "adjust":
        old = data["chaos_level"]
        new = max(1, min(10, old + args.delta))
        data["chaos_level"] = new
        data.setdefault("history", []).append({
            "turn": data.get("current_turn", 0),
            "from": old, "to": new,
            "reason": args.reason or f"手动调整 {args.delta:+d}",
        })
        save_chaos(args.file, data)
        bar = "#" * new + "-" * (10 - new)
        print(f"Chaos: {old} -> {new} [{bar}]")

    elif args.command == "scene-check":
        level = data["chaos_level"]
        result, roll = scene_check(level)
        labels = {
            "expected": "场景按预期进行",
            "altered": "场景被改变（增加意外因素）",
            "interrupt": "场景被中断！随机事件插入",
        }
        print(f"Scene check: 1d10={roll} vs chaos={level}")
        print(f"Result: {result.upper()} — {labels[result]}")

    elif args.command == "roll":
        total, detail = roll_dice(args.dice, args.advantage, args.disadvantage)
        print(detail)

    elif args.command == "oracle":
        result, roll = args.odds, 0
        result, roll = oracle(args.odds)
        labels = {
            "exceptional_yes": "极可能是（Exceptional Yes）",
            "yes": "是",
            "no": "否",
            "exceptional_no": "极可能否（Exceptional No）",
        }
        print(f"Oracle [{args.odds}]: d100={roll} -> {labels[result]}")


if __name__ == "__main__":
    main()
