#!/usr/bin/env python3
"""World lore manager. View, search, and expand world setting entries.

Stored in campaign/lore/world_lore.yaml with sections, entries, and revealed flags.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def parse_lore(text: str) -> dict[str, list[dict[str, str]]]:
    """Parse world_lore.yaml into sections with entries."""
    sections: dict[str, list[dict[str, str]]] = {}
    current_section = ""
    current_entry: dict[str, str] = {}
    in_content = False
    content_lines: list[str] = []

    for line in text.split("\n"):
        # Section header: "## Section Name"
        if line.startswith("## "):
            if current_entry and current_section:
                current_entry["content"] = "\n".join(content_lines).strip()
                sections.setdefault(current_section, []).append(current_entry)
            current_section = line[3:].strip()
            current_entry = {}
            content_lines = []
            in_content = False
            continue

        # Entry field: "- id: xxx"
        if line.startswith("- id: "):
            if current_entry and current_section:
                current_entry["content"] = "\n".join(content_lines).strip()
                sections.setdefault(current_section, []).append(current_entry)
            current_entry = {"id": line[5:].strip()}
            content_lines = []
            in_content = False
            continue

        # Field: "  title: xxx" or "  revealed: true"
        m = re.match(r"  (\w+):\s*(.*)", line)
        if m and not in_content:
            key, val = m.group(1), m.group(2).strip()
            current_entry[key] = val
            continue

        # Content start
        if line.strip() == "content: |":
            in_content = True
            continue

        # Content continuation (indented)
        if in_content and line.startswith("    "):
            content_lines.append(line[4:])
            continue
        elif in_content and line.strip():
            content_lines.append(line.strip())
            continue
        elif in_content and not line.strip():
            # blank line in content
            content_lines.append("")
            continue

    # Don't forget last entry
    if current_entry and current_section:
        current_entry["content"] = "\n".join(content_lines).strip()
        sections.setdefault(current_section, []).append(current_entry)

    return sections


def main():
    parser = argparse.ArgumentParser(description="World lore manager.")
    parser.add_argument("--file", type=Path, default=Path("campaign/lore/world_lore.yaml"))
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sections_p = sub.add_parser("sections")
    sections_p.add_argument("--file", type=Path, default=Path("campaign/lore/world_lore.yaml"))
    sp = list_p = sub.add_parser("list")
    list_p.add_argument("--file", type=Path, default=Path("campaign/lore/world_lore.yaml"))
    sp.add_argument("--section", default=None)
    sp.add_argument("--revealed-only", action="store_true")
    sp = show_p = sub.add_parser("show")
    show_p.add_argument("--file", type=Path, default=Path("campaign/lore/world_lore.yaml"))
    sp.add_argument("entry_id")
    sp = search_p = sub.add_parser("search")
    search_p.add_argument("--file", type=Path, default=Path("campaign/lore/world_lore.yaml"))
    sp.add_argument("keyword")

    args = parser.parse_args()
    lore_path = args.file.resolve()

    if not lore_path.exists():
        print(f"Lore file not found: {lore_path}")
        return

    text = lore_path.read_text(encoding="utf-8")
    sections = parse_lore(text)

    if args.command == "sections":
        for name, entries in sections.items():
            revealed = sum(1 for e in entries if e.get("revealed", "true") == "true")
            print(f"  {name} ({len(entries)} entries, {revealed} revealed)")

    elif args.command == "list":
        for name, entries in sections.items():
            if args.section and name != args.section:
                continue
            print(f"\n## {name}")
            for e in entries:
                if args.revealed_only and e.get("revealed", "true") != "true":
                    continue
                status = "[公开]" if e.get("revealed", "true") == "true" else "[隐藏]"
                print(f"  {status} {e.get('id', '?')}: {e.get('title', '?')}")

    elif args.command == "show":
        for name, entries in sections.items():
            for e in entries:
                if e.get("id") == args.entry_id:
                    print(f"## {e.get('title', '?')}  ({name})")
                    print(f"  公开: {e.get('revealed', 'true')}")
                    print(f"  ID: {e.get('id', '?')}")
                    print()
                    print(e.get("content", "(no content)"))
                    return
        print(f"Entry '{args.entry_id}' not found")

    elif args.command == "search":
        keyword = args.keyword.lower()
        for name, entries in sections.items():
            for e in entries:
                haystack = (e.get("title", "") + " " + e.get("content", "")).lower()
                if keyword in haystack:
                    print(f"  [{name}] {e.get('id')}: {e.get('title', '?')}")


if __name__ == "__main__":
    main()
