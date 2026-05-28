#!/usr/bin/env python3
"Generate a session summary from campaign state and logs."

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except json.JSONDecodeError:
        return default


def cmd_summarize(root: Path, session_id: str, write: bool) -> dict[str, Any]:
    state = load_json(root / "campaign" / "campaign_state.json", {})
    clocks = load_json(root / "campaign" / "world_clocks.json", {"clocks": []})
    quests = load_json(root / "campaign" / "quest_graph.json", {"quests": []})
    
    npc_dir = root / "campaign" / "npcs"
    npc_summaries = {}
    if npc_dir.exists():
        for graph_path in sorted(npc_dir.glob("*.memory_graph.json")):
            graph = load_json(graph_path, {})
            npc_id = graph.get("npc_id", graph_path.stem)
            mem_count = len(graph.get("memory_nodes", []))
            interp_count = len(graph.get("interpretation_nodes", []))
            under_count = len(graph.get("understanding_nodes", []))
            active_beliefs = [
                u.get("text", "")[:100]
                for u in graph.get("understanding_nodes", [])
                if u.get("tier") in ("core", "active")
            ]
            npc_summaries[npc_id] = {
                "memories": mem_count,
                "interpretations": interp_count,
                "understandings": under_count,
                "active_beliefs": active_beliefs[:5],
            }

    summary = {
        "session_id": session_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "campaign": {
            "id": state.get("campaign_id", "unknown"),
            "turn": state.get("current_turn", 0),
            "time": state.get("current_time", "unknown"),
        },
        "scene": state.get("current_scene", {}),
        "active_clocks": [
            {"id": c.get("id"), "title": c.get("title"), "value": c.get("value"),
             "max": c.get("max_value"), "status": c.get("status")}
            for c in clocks.get("clocks", [])
            if c.get("status") == "active"
        ],
        "active_quests": [
            {"id": q.get("id"), "title": q.get("title"), "status": q.get("status", "active")}
            for q in quests.get("quests", [])
            if isinstance(q, dict) and q.get("status") == "active"
        ],
        "npc_states": npc_summaries,
        "player_characters": state.get("player_characters", []),
    }

    out_path = root / "campaign" / "session_logs" / f"{session_id}.summary.json"
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate session summary.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--session-id", default="0001")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    cmd_summarize(args.root, args.session_id, args.write)


if __name__ == "__main__":
    main()
