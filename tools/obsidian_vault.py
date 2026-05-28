#!/usr/bin/env python3
"""Export a campaign into an Obsidian-friendly Markdown vault.

The JSON/YAML campaign files remain the canonical runtime state. This exporter
creates a readable linked mirror for Obsidian: notes with YAML frontmatter,
wikilinks, indexes, and private NPC memory notes kept separate from player
visible notes.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "obsidian_vaults"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return default


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig") if path.exists() else ""


def decode_escaped_text(value: str) -> str:
    if "\\u" not in value and "\\n" not in value:
        return value
    try:
        return json.loads('"' + value.replace('"', '\\"') + '"')
    except Exception:
        try:
            return value.encode("utf-8").decode("unicode_escape")
        except Exception:
            return value


def clean(value: Any) -> Any:
    if isinstance(value, str):
        return decode_escaped_text(value)
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    return value


def slug(value: str, fallback: str = "note") -> str:
    value = clean(str(value or "")).strip()
    ascii_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
    if ascii_slug:
        return ascii_slug[:80]
    safe = re.sub(r'[\\/:*?"<>|#^\[\].]+', "_", value).strip(" _")
    result = (safe or fallback)[:80]
    # V27: prevent path traversal via . or .. slugs
    if result in (".", "..") or result.startswith("..") and len(result) > 2 and all(c == "." for c in result):
        result = fallback
    return result


def yaml_scalar(value: Any) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = clean(str(value)).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            if value:
                for item in value:
                    lines.append(f"  - {yaml_scalar(item)}")
            else:
                lines.append("  []")
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def write_note(path: Path, meta: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter(meta) + body.strip() + "\n", encoding="utf-8")


def parse_yaml_label(text: str, key: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}:"):
            return clean(stripped.split(":", 1)[1].strip().strip('"').strip("'"))
    return ""


def wikilink(title: str, alias: str | None = None) -> str:
    title = clean(title)
    if alias and alias != title:
        return f"[[{title}|{clean(alias)}]]"
    return f"[[{title}]]"


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def quest_title(quest: Any) -> str:
    if isinstance(quest, dict):
        return clean(quest.get("title") or quest.get("id") or "Quest")
    return clean(str(quest))


def export_campaign(root: Path, out_root: Path = DEFAULT_OUT, force: bool = True) -> dict[str, Any]:
    root = root.resolve()
    state = clean(read_json(root / "campaign" / "campaign_state.json", {}))
    if not isinstance(state, dict):
        raise RuntimeError(f"campaign_state.json must be an object: {root}")

    campaign_id = slug(str(state.get("campaign_id") or root.name), "campaign")
    title = clean(str(state.get("title") or state.get("campaign_id") or root.name))
    vault = (out_root / campaign_id).resolve()
    if vault.exists() and force:
        shutil.rmtree(vault)
    vault.mkdir(parents=True, exist_ok=True)

    (vault / ".obsidian").mkdir(exist_ok=True)
    (vault / ".obsidian" / "app.json").write_text(
        json.dumps({"newFileLocation": "folder", "newFileFolderPath": "Inbox"}, indent=2) + "\n",
        encoding="utf-8",
    )

    scene = state.get("current_scene") if isinstance(state.get("current_scene"), dict) else {}
    players = [item for item in as_list(state.get("player_characters")) if isinstance(item, dict)]
    quests = [item for item in as_list(state.get("quests"))]
    location_id = clean(str(scene.get("location_id", "")))

    index_links = [
        wikilink("Campaign State"),
        wikilink("Player Characters"),
        wikilink("NPC Index"),
        wikilink("Quest Index"),
        wikilink("Location Index"),
        wikilink("World Clocks"),
        wikilink("Player Knowledge"),
    ]
    write_note(
        vault / "Home.md",
        {
            "type": "campaign_index",
            "campaign_id": state.get("campaign_id"),
            "source_root": str(root),
            "tags": ["paotuan", "campaign"],
        },
        f"# {title}\n\n" + "\n".join(f"- {link}" for link in index_links),
    )

    write_note(
        vault / "Campaign State.md",
        {
            "type": "campaign_state",
            "campaign_id": state.get("campaign_id"),
            "turn": state.get("current_turn", 1),
            "time": state.get("current_time", ""),
            "location": location_id,
            "tags": ["paotuan/state"],
        },
        "\n".join(
            [
                "# Campaign State",
                "",
                f"- Current scene: {clean(scene.get('summary', ''))}",
                f"- Location: {wikilink('Location - ' + location_id) if location_id else 'unknown'}",
                f"- Present: {', '.join(wikilink('NPC - ' + str(e)) if str(e).startswith('npc_') else wikilink('PC - ' + str(e)) for e in as_list(scene.get('present_entities')))}",
                "",
                "## Active Threads",
                "\n".join(f"- {clean(item)}" for item in as_list(scene.get("active_threads"))) or "- None",
            ]
        ),
    )

    player_lines = ["# Player Characters"]
    for pc in players:
        pc_id = clean(str(pc.get("id", "pc")))
        pc_name = clean(str(pc.get("name") or pc_id))
        note_title = f"PC - {pc_id}"
        player_lines.append(f"- {wikilink(note_title, pc_name)}")
        stats = pc.get("stats") if isinstance(pc.get("stats"), dict) else {}
        body = [
            f"# {pc_name}",
            "",
            f"- Realm: {clean(pc.get('realm', ''))}",
            f"- Spiritual root: {clean(pc.get('spiritual_root', ''))}",
            f"- Health: {pc.get('health', '')}/{pc.get('max_health', '')}",
            f"- Qi: {pc.get('qi', '')}/{pc.get('max_qi', '')}",
            f"- Location: {wikilink('Location - ' + str(pc.get('location_id')))}",
            "",
            "## Stats",
            "\n".join(f"- {key}: {value}" for key, value in stats.items()) or "- None",
            "",
            "## Inventory",
            "\n".join(f"- {clean(item)}" for item in as_list(pc.get("inventory"))) or "- None",
            "",
            "## Conditions",
            "\n".join(f"- {clean(item)}" for item in as_list(pc.get("conditions"))) or "- None",
        ]
        write_note(
            vault / "Characters" / f"{note_title}.md",
            {"type": "pc", "id": pc_id, "name": pc_name, "location": pc.get("location_id"), "tags": ["paotuan/pc"]},
            "\n".join(body),
        )
    write_note(vault / "Player Characters.md", {"type": "index", "tags": ["paotuan/index"]}, "\n".join(player_lines))

    npc_lines = ["# NPC Index"]
    npc_dir = root / "campaign" / "npcs"
    for profile_path in sorted(npc_dir.glob("*.yaml")):
        npc_id = profile_path.stem
        profile = read_text(profile_path)
        graph = clean(read_json(npc_dir / f"{npc_id}.memory_graph.json", {}))
        if not isinstance(graph, dict):
            graph = {}
        name = parse_yaml_label(profile, "name") or npc_id
        role = parse_yaml_label(profile, "role") or parse_yaml_label(profile, "occupation")
        note_title = f"NPC - {npc_id}"
        npc_lines.append(f"- {wikilink(note_title, name)}")
        memories = graph.get("memory_nodes", []) if isinstance(graph.get("memory_nodes"), list) else []
        understandings = graph.get("understanding_nodes", []) if isinstance(graph.get("understanding_nodes"), list) else []
        body = [
            f"# {name}",
            "",
            f"- Role: {role or 'unknown'}",
            f"- Source profile: `{profile_path.relative_to(root)}`",
            "",
            "## Profile",
            "```yaml",
            profile.strip(),
            "```",
            "",
            "## Private Memory Nodes",
            "\n".join(
                f"- **{clean(mem.get('id', 'memory'))}** ({clean(mem.get('tier', ''))}, confidence {mem.get('confidence', '')}): {clean(mem.get('content', ''))}"
                for mem in memories
                if isinstance(mem, dict)
            )
            or "- None",
            "",
            "## Understandings",
            "\n".join(
                f"- **{clean(item.get('id', 'understanding'))}** ({clean(item.get('type', ''))}): {clean(item.get('text', ''))}"
                for item in understandings
                if isinstance(item, dict)
            )
            or "- None",
        ]
        write_note(
            vault / "NPCs" / f"{note_title}.md",
            {
                "type": "npc",
                "id": npc_id,
                "name": name,
                "role": role,
                "memory_count": len(memories),
                "understanding_count": len(understandings),
                "tags": ["paotuan/npc"],
            },
            "\n".join(body),
        )
    write_note(vault / "NPC Index.md", {"type": "index", "tags": ["paotuan/index"]}, "\n".join(npc_lines))

    quest_graph = clean(read_json(root / "campaign" / "quest_graph.json", {}))
    graph_quests = quest_graph.get("quests", []) if isinstance(quest_graph, dict) else []
    all_quests = graph_quests or quests
    quest_lines = ["# Quest Index"]
    for index, quest in enumerate(as_list(all_quests), start=1):
        q = quest if isinstance(quest, dict) else {"id": str(quest), "title": str(quest), "status": "active"}
        qid = clean(str(q.get("id") or f"quest_{index:04d}"))
        title_text = quest_title(q)
        note_title = f"Quest - {qid}"
        quest_lines.append(f"- {wikilink(note_title, title_text)}")
        clues = q.get("clues", []) if isinstance(q.get("clues"), list) else []
        body = [
            f"# {title_text}",
            "",
            f"- Status: {clean(q.get('status', ''))}",
            f"- Pressure: {clean(q.get('pressure') or q.get('failure_consequence') or '')}",
            "",
            "## Clues",
            "\n".join(
                f"- [{'x' if clue.get('found') else ' '}] {clean(clue.get('text', clue.get('id', '')))}"
                for clue in clues
                if isinstance(clue, dict)
            )
            or "- None",
            "",
            "## Raw",
            "```json",
            json.dumps(q, ensure_ascii=False, indent=2),
            "```",
        ]
        write_note(
            vault / "Quests" / f"{note_title}.md",
            {"type": "quest", "id": qid, "status": q.get("status"), "tags": ["paotuan/quest"]},
            "\n".join(body),
        )
    write_note(vault / "Quest Index.md", {"type": "index", "tags": ["paotuan/index"]}, "\n".join(quest_lines))

    loc_lines = ["# Location Index"]
    for loc_path in sorted((root / "campaign" / "locations").glob("*.yaml")):
        text = read_text(loc_path)
        loc_id = parse_yaml_label(text, "id") or loc_path.stem
        name = parse_yaml_label(text, "name") or loc_id
        note_title = f"Location - {loc_id}"
        loc_lines.append(f"- {wikilink(note_title, name)}")
        write_note(
            vault / "Locations" / f"{note_title}.md",
            {"type": "location", "id": loc_id, "name": name, "tags": ["paotuan/location"]},
            f"# {name}\n\n```yaml\n{text.strip()}\n```",
        )
    write_note(vault / "Location Index.md", {"type": "index", "tags": ["paotuan/index"]}, "\n".join(loc_lines))

    for source, title_name, note_name in [
        ("world_clocks.json", "World Clocks", "World Clocks.md"),
        ("player_knowledge.json", "Player Knowledge", "Player Knowledge.md"),
        ("world_graph.jsonl", "World Graph", "World Graph.md"),
        ("resources.json", "Resources", "Resources.md"),
        ("rumors.json", "Rumors", "Rumors.md"),
    ]:
        raw = read_text(root / "campaign" / source)
        fence = "jsonl" if source.endswith(".jsonl") else "json"
        write_note(
            vault / "World" / note_name,
            {"type": slug(title_name), "source": source, "tags": ["paotuan/world"]},
            f"# {title_name}\n\n```{fence}\n{raw.strip()}\n```",
        )

    exported = len(list(vault.rglob("*.md")))
    return {"vault": str(vault), "notes": exported, "campaign_id": campaign_id, "title": title}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a campaign as an Obsidian vault.")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args()
    result = export_campaign(args.root, args.out, force=not args.no_force)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
