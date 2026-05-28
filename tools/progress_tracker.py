#!/usr/bin/env python3
"""Progress tracks (Ironsworn-style) for quests, journeys, and conflicts.

Each track has current progress and a target (e.g., 0/10).
Advancement is done via progress rolls against the track.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


def load_tracks(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return {"tracks": []}


def save_tracks(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def create_track(data: dict[str, Any], track_id: str, title: str, target: int = 10,
                 track_type: str = "quest") -> str:
    for t in data.get("tracks", []):
        if t["id"] == track_id:
            return f"Track '{track_id}' already exists"
    data.setdefault("tracks", []).append({
        "id": track_id, "title": title, "type": track_type,
        "progress": 0, "target": target, "status": "active",
        "history": [],
    })
    return f"Created track '{track_id}': {title} (0/{target})"


def advance(data: dict[str, Any], track_id: str, amount: int = 1, note: str = "") -> str:
    for t in data.get("tracks", []):
        if t["id"] == track_id:
            old = t["progress"]
            t["progress"] = min(t["target"], old + amount)
            t.setdefault("history", []).append(
                f"+{amount}: {old}/{t['target']} -> {t['progress']}/{t['target']} ({note})" if note
                else f"+{amount}: {old}/{t['target']} -> {t['progress']}/{t['target']}"
            )
            if t["progress"] >= t["target"]:
                t["status"] = "complete"
                return f"Track '{track_id}' COMPLETE! {old}/{t['target']} -> {t['progress']}/{t['target']}"
            return f"Advanced '{track_id}': {old}/{t['target']} -> {t['progress']}/{t['target']}"
    return f"Track '{track_id}' not found"


def progress_roll(data: dict[str, Any], track_id: str) -> str:
    """Ironsworn-style progress roll: roll 2d10 vs progress, success if progress > both."""
    for t in data.get("tracks", []):
        if t["id"] == track_id:
            challenge1, challenge2 = random.randint(1, 10), random.randint(1, 10)
            progress = t["progress"]
            challenge = max(challenge1, challenge2)
            if progress > challenge:
                result = "STRONG HIT"
            elif progress > min(challenge1, challenge2):
                result = "WEAK HIT"
            else:
                result = "MISS"
            return (
                f"Progress roll for '{track_id}': "
                f"progress={progress} vs d10={challenge1},{challenge2} "
                f"-> {result}"
            )
    return f"Track '{track_id}' not found"


def list_tracks(data: dict[str, Any]) -> None:
    for t in data.get("tracks", []):
        bar_len = 10
        filled = int(t["progress"] / t["target"] * bar_len) if t["target"] > 0 else 0
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"  [{t['status'][:4]:4s}] {t['id']}: [{bar}] {t['progress']}/{t['target']} {t['title']}")


def main():
    parser = argparse.ArgumentParser(description="Progress tracks for quests, journeys, conflicts.")
    parser.add_argument("--file", type=Path, default=Path("campaign/progress_tracks.json"))
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list")
    list_p.add_argument("--file", type=Path, default=Path("campaign/progress_tracks.json"))
    sp = create_p = sub.add_parser("create")
    create_p.add_argument("--file", type=Path, default=Path("campaign/progress_tracks.json"))
    sp.add_argument("track_id")
    sp.add_argument("title")
    sp.add_argument("--target", type=int, default=10)
    sp.add_argument("--type", default="quest", choices=["quest", "journey", "combat", "project"])
    sp = advance_p = sub.add_parser("advance")
    advance_p.add_argument("--file", type=Path, default=Path("campaign/progress_tracks.json"))
    sp.add_argument("track_id")
    sp.add_argument("--amount", type=int, default=1)
    sp.add_argument("--note", default="")
    pr_p = sub.add_parser("progress-roll")
    pr_p.add_argument("--file", type=Path, default=Path("campaign/progress_tracks.json"))
    sp.add_argument("track_id")

    args = parser.parse_args()
    data = load_tracks(args.file)

    if args.command == "list":
        list_tracks(data)
    elif args.command == "create":
        print(create_track(data, args.track_id, args.title, args.target, args.type))
        save_tracks(args.file, data)
    elif args.command == "advance":
        print(advance(data, args.track_id, args.amount, args.note))
        save_tracks(args.file, data)
    elif args.command == "progress-roll":
        print(progress_roll(data, args.track_id))


if __name__ == "__main__":
    main()
