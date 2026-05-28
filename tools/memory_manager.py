#!/usr/bin/env python3
"""Rank and maintain NPC memory graph tiers.

This tool is intentionally small and local-first. It updates memory tiers from
turn age, importance, salience, recall count, emotion, and confidence.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_WEIGHTS = {
    "importance": 0.35,
    "salience": 0.20,
    "recency": 0.15,
    "recall": 0.15,
    "emotion": 0.10,
    "confidence": 0.05,
}


def memory_score(memory: dict[str, Any], current_turn: int, half_life_turns: int) -> float:
    last_recalled = int(memory.get("last_recalled_turn", memory.get("created_turn", 0)))
    turns_since = max(0, current_turn - last_recalled)
    recency = 1 / (1 + turns_since / max(1, half_life_turns))
    recall = min(1, math.log2(1 + int(memory.get("recall_count", 0))) / 4)
    emotion = abs(float(memory.get("emotional_valence", 0))) / 2

    score = (
        float(memory.get("importance", 0)) * DEFAULT_WEIGHTS["importance"]
        + float(memory.get("salience", 0)) * DEFAULT_WEIGHTS["salience"]
        + recency * DEFAULT_WEIGHTS["recency"]
        + recall * DEFAULT_WEIGHTS["recall"]
        + emotion * DEFAULT_WEIGHTS["emotion"]
        + float(memory.get("confidence", 0)) * DEFAULT_WEIGHTS["confidence"]
    )
    return round(max(0, min(1, score)), 4)


def tier_for_score(score: float, pinned: bool = False) -> str:
    if pinned or score >= 0.78:
        return "core"
    if score >= 0.48:
        return "active"
    if score >= 0.22:
        return "dormant"
    return "archive"


def load_graph(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))


def save_graph(path: Path | str, graph: dict[str, Any]) -> None:
    path = Path(path)
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rerank(path: Path, current_turn: int | None, half_life_turns: int, write: bool) -> None:
    graph = load_graph(path)
    turn = current_turn if current_turn is not None else int(graph.get("current_turn", 0))
    graph["current_turn"] = turn

    ranked = []
    for memory in graph.get("memory_nodes", []):
        score = memory_score(memory, turn, half_life_turns)
        memory["score"] = score
        memory["tier"] = tier_for_score(score, bool(memory.get("pinned", False)))
        ranked.append(memory)

    ranked.sort(key=lambda item: item.get("score", 0), reverse=True)

    for memory in ranked:
        print(f"{memory['id']}\t{memory['tier']}\t{memory['score']}\t{memory['content']}")

    if write:
        graph["memory_nodes"] = ranked
        save_graph(path, graph)


def recall(path: Path, memory_ids: list[str], current_turn: int, write: bool) -> None:
    graph = load_graph(path)
    graph["current_turn"] = current_turn
    wanted = set(memory_ids)

    for memory in graph.get("memory_nodes", []):
        if memory.get("id") in wanted:
            memory["recall_count"] = int(memory.get("recall_count", 0)) + 1
            memory["last_recalled_turn"] = current_turn

    if write:
        save_graph(path, graph)
    else:
        print(json.dumps(graph, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain NPC memory graph tiers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    rerank_parser = subparsers.add_parser("rerank", help="Recompute memory scores and tiers.")
    rerank_parser.add_argument("graph", type=Path)
    rerank_parser.add_argument("--turn", type=int, default=None)
    rerank_parser.add_argument("--half-life", type=int, default=12)
    rerank_parser.add_argument("--write", action="store_true")

    recall_parser = subparsers.add_parser("recall", help="Increment recall counts for used memories.")
    recall_parser.add_argument("graph", type=Path)
    recall_parser.add_argument("memory_ids", nargs="+")
    recall_parser.add_argument("--turn", type=int, required=True)
    recall_parser.add_argument("--write", action="store_true")

    args = parser.parse_args()
    if args.command == "rerank":
        rerank(args.graph, args.turn, args.half_life, args.write)
    elif args.command == "recall":
        recall(args.graph, args.memory_ids, args.turn, args.write)


if __name__ == "__main__":
    main()

