#!/usr/bin/env python3
"""View and update quest/threat graphs.

Stored in campaign/quest_graph.json.
Each quest has clues, obstacles, countdowns, failure consequences, and intervention nodes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_graph(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return {"quests": []}


def save_graph(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_quests(data: dict[str, Any]) -> None:
    for q in data.get("quests", []):
        status = q.get("status", "?")
        qid = q.get("id", "?")
        title = q.get("title", "?")
        clues = len(q.get("clues", []))
        obs = len(q.get("obstacles", []))
        nodes = len(q.get("intervention_nodes", []))
        cd = q.get("countdown_ticks", "?")
        cd_max = q.get("countdown_max", "?")
        fail = q.get("failure_consequence", "")[:60]
        print(f"  [{status}] {qid}: {title}")
        print(f"       clues={clues} obstacles={obs} nodes={nodes} countdown={cd}/{cd_max}")
        if fail:
            print(f"       failure: {fail}")


def main():
    parser = argparse.ArgumentParser(description="View quest/threat graphs.")
    parser.add_argument("--file", type=Path, default=Path("campaign/quest_graph.json"))
    sub = parser.add_subparsers(dest="command", required=True)
    list_p = sub.add_parser("list")
    list_p.add_argument("--file", type=Path, default=Path("campaign/quest_graph.json"))
    sp = show_p = sub.add_parser("show")
    show_p.add_argument("--file", type=Path, default=Path("campaign/quest_graph.json"))
    sp.add_argument("quest_id")

    args = parser.parse_args()
    data = load_graph(args.file)

    if args.command == "list":
        list_quests(data)
    elif args.command == "show":
        for q in data.get("quests", []):
            if q.get("id") == args.quest_id:
                print(json.dumps(q, ensure_ascii=False, indent=2))
                return
        print(f"Quest '{args.quest_id}' not found")


if __name__ == "__main__":
    main()
