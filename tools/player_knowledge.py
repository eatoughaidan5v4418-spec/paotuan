#!/usr/bin/env python3
"""Manage player-known information ledger.

Tracks what the player character has discovered, who they've met,
where they've been, and what they (think they) understand.
Separate from GM truth and NPC private memories.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_knowledge(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return {
        "clues_discovered": [],
        "npcs_known": [],
        "locations_explored": [],
        "facts_understood": [],
        "events_witnessed": [],
    }


def save_knowledge(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def decode_escaped_text(value: Any) -> Any:
    """Decode accidentally double-escaped JSON strings for display or cleanup."""
    if isinstance(value, str):
        text = value
        for _ in range(2):
            if "\\u" not in text and "\\n" not in text and "\\t" not in text:
                break
            try:
                decoded = json.loads(f'"{text}"')
            except json.JSONDecodeError:
                break
            if not isinstance(decoded, str) or decoded == text:
                break
            text = decoded
        return text
    if isinstance(value, list):
        return [decode_escaped_text(item) for item in value]
    if isinstance(value, dict):
        return {key: decode_escaped_text(item) for key, item in value.items()}
    return value


def add_clue(data: dict[str, Any], clue_id: str, description: str, location: str,
             turn: int, time_str: str) -> str:
    for c in data["clues_discovered"]:
        if c["id"] == clue_id:
            return f"Clue '{clue_id}' already recorded"
    data["clues_discovered"].append({
        "id": clue_id, "description": description, "location": location,
        "discovered_turn": turn, "discovered_at": time_str,
    })
    return f"Recorded clue: {clue_id}"


def add_npc(data: dict[str, Any], npc_id: str, known_as: str, role: str,
            turn: int) -> str:
    for n in data["npcs_known"]:
        if n["id"] == npc_id:
            n["last_interaction_turn"] = turn
            return f"Updated NPC '{npc_id}' last interaction to turn {turn}"
    data["npcs_known"].append({
        "id": npc_id, "known_as": known_as, "known_role": role,
        "first_met_turn": turn, "last_interaction_turn": turn,
    })
    return f"Recorded NPC: {npc_id} ({known_as})"


def add_location(data: dict[str, Any], loc_id: str, name: str, notes: str = "") -> str:
    for loc in data["locations_explored"]:
        if loc["id"] == loc_id:
            if notes:
                loc["notes"] = notes
            return f"Updated location '{loc_id}'"
    data["locations_explored"].append({"id": loc_id, "name": name, "notes": notes})
    return f"Recorded location: {loc_id} ({name})"


def add_fact(data: dict[str, Any], fact: str, confidence: str, source: str, turn: int) -> str:
    data["facts_understood"].append({
        "fact": fact, "confidence": confidence, "source": source,
        "learned_turn": turn,
    })
    return f"Recorded fact: {fact[:50]}..."


def list_knowledge(data: dict[str, Any]) -> None:
    data = decode_escaped_text(data)
    print(f"Clues discovered: {len(data['clues_discovered'])}")
    for c in data["clues_discovered"]:
        print(f"  [{c['id']}] {c['description'][:60]} (turn {c.get('discovered_turn','?')})")
    print(f"\nNPCs known: {len(data['npcs_known'])}")
    for n in data["npcs_known"]:
        print(f"  {n['id']} as '{n.get('known_as','?')}' role={n.get('known_role','?')}")
    print(f"\nLocations explored: {len(data['locations_explored'])}")
    for loc in data["locations_explored"]:
        print(f"  {loc['id']} ({loc.get('name','?')})")
    print(f"\nFacts understood: {len(data['facts_understood'])}")
    for f in data["facts_understood"]:
        print(f"  [{f.get('confidence','?')}] {f['fact'][:70]} (via {f.get('source','?')})")


def main():
    parser = argparse.ArgumentParser(description="Manage player-known information ledger.")
    parser.add_argument("--file", type=Path, default=Path("campaign/player_knowledge.json"))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")
    sub.add_parser("normalize", help="Decode double-escaped text and write the ledger back.")
    sp = sub.add_parser("add-clue")
    sp.add_argument("clue_id")
    sp.add_argument("description")
    sp.add_argument("--location", default="")
    sp.add_argument("--turn", type=int, default=1)
    sp.add_argument("--time", default="")
    sp = sub.add_parser("add-npc")
    sp.add_argument("npc_id")
    sp.add_argument("known_as")
    sp.add_argument("--role", default="")
    sp.add_argument("--turn", type=int, default=1)
    sp = sub.add_parser("add-location")
    sp.add_argument("loc_id")
    sp.add_argument("name")
    sp.add_argument("--notes", default="")
    sp = sub.add_parser("add-fact")
    sp.add_argument("fact")
    sp.add_argument("--confidence", default="unknown", choices=["true", "false", "rumor", "unknown", "confirmed", "suspected"])
    sp.add_argument("--source", default="")
    sp.add_argument("--turn", type=int, default=1)

    args = parser.parse_args()
    data = load_knowledge(args.file)

    if args.command == "list":
        list_knowledge(data)
    elif args.command == "normalize":
        data = decode_escaped_text(data)
        save_knowledge(args.file, data)
        print(f"Normalized escaped text in {args.file}")
    else:
        if args.command == "add-clue":
            print(add_clue(data, args.clue_id, args.description, args.location, args.turn, args.time))
        elif args.command == "add-npc":
            print(add_npc(data, args.npc_id, args.known_as, args.role, args.turn))
        elif args.command == "add-location":
            print(add_location(data, args.loc_id, args.name, args.notes))
        elif args.command == "add-fact":
            print(add_fact(data, args.fact, args.confidence, args.source, args.turn))
        save_knowledge(args.file, data)


if __name__ == "__main__":
    main()
