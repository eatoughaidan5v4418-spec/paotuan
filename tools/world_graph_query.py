#!/usr/bin/env python3
"Query world_graph.jsonl for audit and cross-NPC memory checks."

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_graph(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with open(path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def cmd_summary(records: list[dict[str, Any]]) -> None:
    node_types: dict[str, int] = {}
    edge_types: dict[str, int] = {}
    npc_ids: set[str] = set()
    for rec in records:
        nt = rec.get('node_type') or rec.get('edge_type')
        if rec.get('record_type') == 'edge' or rec.get('edge_type'):
            key = rec.get('edge_type', 'unknown')
            edge_types[key] = edge_types.get(key, 0) + 1
        else:
            key = rec.get('node_type', 'unknown')
            node_types[key] = node_types.get(key, 0) + 1
        nid = rec.get('npc_id')
        if nid:
            npc_ids.add(str(nid))
    print(f'Total records: {len(records)}')
    print(f'Nodes: {sum(node_types.values())} ({dict(node_types)})')
    print(f'Edges: {sum(edge_types.values())} ({dict(edge_types)})')
    print(f'NPCs referenced: {sorted(npc_ids)}')


def cmd_npc_memories(records: list[dict[str, Any]], npc_id: str) -> None:
    found = [
        rec for rec in records
        if rec.get('npc_id') == npc_id and rec.get('visibility') == 'private'
    ]
    print(f'{npc_id}: {len(found)} private records')
    for rec in found[-20:]:
        summary = str(rec.get('summary', ''))[:100]
        rtype = rec.get('node_type') or rec.get('edge_type') or rec.get('record_type', '?')
        print(f'  [{rtype}] {summary}')


def cmd_check_isolation(records: list[dict[str, Any]]) -> None:
    npc_records: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        nid = rec.get('npc_id')
        if not nid:
            continue
        npc_records.setdefault(str(nid), []).append(rec)

    # Check: does any NPC have a record that references another NPC's id
    # in a way that suggests cross-contamination?
    npc_ids = set(npc_records.keys())
    issues = 0
    for nid, recs in npc_records.items():
        for rec in recs:
            summary = str(rec.get('summary', ''))
            for other_nid in npc_ids:
                if other_nid == nid:
                    continue
                if other_nid in summary:
                    rtype = rec.get('node_type') or rec.get('edge_type', '?')
                    print(f'  [?] {nid} record mentions {other_nid}: [{rtype}] {summary[:100]}')
                    issues += 1
    if issues == 0:
        print('No cross-NPC contamination detected.')
    else:
        print(f'{issues} potential cross-contamination entries found (review manually).')


def main() -> None:
    parser = argparse.ArgumentParser(description='Query world_graph.jsonl')
    parser.add_argument('--file', type=Path, default=Path('campaign/world_graph.jsonl'))
    sub = parser.add_subparsers(dest='command')

    summary_p = sub.add_parser('summary', help='Show record counts by type')
    summary_p.add_argument('--file', type=Path, default=Path('campaign/world_graph.jsonl'))
    npc_parser = sub.add_parser('npc', help='Show records for a specific NPC')
    npc_parser.add_argument('--file', type=Path, default=Path('campaign/world_graph.jsonl'))
    npc_parser.add_argument('npc_id')
    ci_p = sub.add_parser('check-isolation', help='Audit cross-NPC memory contamination')
    ci_p.add_argument('--file', type=Path, default=Path('campaign/world_graph.jsonl'))

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    records = load_graph(args.file)
    if not records:
        print('No records found.')
        return

    if args.command == 'summary':
        cmd_summary(records)
    elif args.command == 'npc':
        cmd_npc_memories(records, args.npc_id)
    elif args.command == 'check-isolation':
        cmd_check_isolation(records)


if __name__ == '__main__':
    main()
