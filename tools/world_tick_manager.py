#!/usr/bin/env python3
"""Small helper for advancing local living-world clocks.

This is not a full simulator. It keeps the local clock file honest so the GM can
advance off-screen pressure without hand-editing JSON every time.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from time_utils import display_to_tick, tick_to_display, parse_interval_minutes


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_clocks(path: Path) -> None:
    data = load_json(path)
    for clock in data.get("clocks", []):
        next_at = clock.get('next_tick_at', '')
        tick_val = clock.get('_next_tick_at_tick', '')
        print(
            f"{clock['id']}\t{clock['value']}/{clock['max_value']}\t"
            f"{clock['status']}\t{clock['title']}\tnext={next_at}"
        )


def tick_clock(path: Path, clock_id: str, amount: int, reason: str, write: bool) -> None:
    data = load_json(path)
    matched = None
    for clock in data.get("clocks", []):
        if clock.get("id") == clock_id:
            matched = clock
            break

    if matched is None:
        raise SystemExit(f"Clock not found: {clock_id}")

    old_value = int(matched.get("value", 0))
    max_value = int(matched.get("max_value", 1))
    new_value = max(0, min(max_value, old_value + amount))
    matched["value"] = new_value
    matched.setdefault("recent_updates", []).append(
        {
            "old_value": old_value,
            "new_value": new_value,
            "amount": amount,
            "reason": reason,
        }
    )
    if new_value >= max_value:
        matched["status"] = "complete"

    print(f"{clock_id}\t{old_value}/{max_value} -> {new_value}/{max_value}\t{matched['status']}")
    if write:
        save_json(path, data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain living-world clocks.")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("campaign/world_clocks.json"),
        help="Path to world_clocks.json.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List clocks.")
    list_parser.add_argument("--file", type=Path, default=Path("campaign/world_clocks.json"), help="Path to world_clocks.json.")

    tick_parser = subparsers.add_parser("tick", help="Advance one clock.")
    tick_parser.add_argument("--file", type=Path, default=Path("campaign/world_clocks.json"), help="Path to world_clocks.json.")
    tick_parser.add_argument("clock_id")
    tick_parser.add_argument("--amount", type=int, default=1)
    tick_parser.add_argument("--reason", required=True)
    tick_parser.add_argument("--write", action="store_true")

    args = parser.parse_args()
    if args.command == "list":
        list_clocks(args.file)
    elif args.command == "tick":
        tick_clock(args.file, args.clock_id, args.amount, args.reason, args.write)


if __name__ == "__main__":
    main()

