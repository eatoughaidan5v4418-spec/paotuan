#!/usr/bin/env python3
"""Validate and query spatial zone models in location YAML files."""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path
from typing import Any

import yaml

CONNECTION_DEFAULTS = {
    "open": {"distance": 5, "line_of_sight": True, "sound": "clear", "movement_cost": 1},
    "door": {"distance": 3, "line_of_sight": False, "sound": "muffled", "movement_cost": 1},
    "window": {"distance": 5, "line_of_sight": True, "sound": "muffled", "movement_cost": 3},
    "long_distance": {"distance": 30, "line_of_sight": False, "sound": "faint", "movement_cost": 5},
    "corridor": {"distance": 15, "line_of_sight": True, "sound": "echo", "movement_cost": 2},
    "stairs": {"distance": 8, "line_of_sight": False, "sound": "clear", "movement_cost": 2},
    "hatch": {"distance": 2, "line_of_sight": False, "sound": "muffled", "movement_cost": 2},
    "water": {"distance": 10, "line_of_sight": True, "sound": "distorted", "movement_cost": 4},
    "secret": {"distance": 2, "line_of_sight": False, "sound": "blocked", "movement_cost": 2},
}
VALID_LIGHT = {"bright", "dim", "dark", "pitch_black"}
VALID_NOISE = {"quiet", "moderate", "loud", "deafening"}
SOUND_RANK = {
    "clear": 0,
    "echo": 1,
    "muffled": 2,
    "distorted": 2,
    "faint": 3,
    "blocked": 99,
}


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def parse_zones(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    issues: list[str] = []
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        return [], [], [f"Invalid YAML: {exc}"]
    if not isinstance(data, dict):
        return [], [], ["Location YAML root must be an object"]

    zones = [z for z in as_list(data.get("zones")) if isinstance(z, dict)]
    connections = [c for c in as_list(data.get("zone_connections")) if isinstance(c, dict)]

    zone_ids = {str(z.get("id")) for z in zones if z.get("id")}
    if not zones:
        issues.append("No zones defined")

    for index, zone in enumerate(zones):
        zid = str(zone.get("id") or f"<zone {index}>")
        if not zone.get("id"):
            issues.append(f"Zone {index}: missing id")
        light = zone.get("ambient_light")
        if light and light not in VALID_LIGHT:
            issues.append(f"Zone '{zid}': invalid ambient_light '{light}'")
        noise = zone.get("ambient_noise")
        if noise and noise not in VALID_NOISE:
            issues.append(f"Zone '{zid}': invalid ambient_noise '{noise}'")

    for index, conn in enumerate(connections):
        for endpoint in ("from", "to"):
            ep = conn.get(endpoint)
            if not ep:
                issues.append(f"Connection {index}: missing '{endpoint}'")
            elif str(ep) not in zone_ids:
                issues.append(f"Connection {index}: '{endpoint}' zone '{ep}' not found")
        ctype = conn.get("type", "")
        if ctype and ctype not in CONNECTION_DEFAULTS:
            issues.append(f"Connection {index}: unknown type '{ctype}'")

    return zones, connections, issues


def resolve_connection(conn: dict[str, Any]) -> dict[str, Any]:
    defaults = CONNECTION_DEFAULTS.get(conn.get("type", ""), {})
    merged = dict(defaults)
    merged.update({k: v for k, v in conn.items() if k != "type"})
    merged["type"] = conn.get("type", "unknown")
    return merged


def build_graph(connections: list[dict[str, Any]]) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    graph: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for conn in connections:
        if not conn.get("from") or not conn.get("to"):
            continue
        resolved = resolve_connection(conn)
        fz = str(conn["from"])
        tz = str(conn["to"])
        graph.setdefault(fz, []).append((tz, resolved))
        graph.setdefault(tz, []).append((fz, resolved))
    return graph


def format_path(path: list[str]) -> str:
    return " -> ".join(path)


def find_los_path(fz: str, tz: str, zones: list[dict[str, Any]], connections: list[dict[str, Any]]) -> dict[str, Any]:
    zone_ids = {str(z.get("id")) for z in zones if z.get("id")}
    if fz not in zone_ids or tz not in zone_ids:
        missing = [z for z in (fz, tz) if z not in zone_ids]
        return {"ok": False, "reason": f"unknown zone(s): {', '.join(missing)}", "path": []}
    if fz == tz:
        return {"ok": True, "reason": "same zone", "path": [fz]}

    graph = build_graph(connections)
    queue = deque([(fz, [fz])])
    seen = {fz}
    blocked: list[str] = []
    while queue:
        current, path = queue.popleft()
        for nxt, conn in graph.get(current, []):
            edge = f"{current}->{nxt}"
            if not conn.get("line_of_sight", False):
                blocked.append(f"{edge} ({conn.get('type')})")
                continue
            if nxt == tz:
                return {"ok": True, "reason": "line of sight path", "path": path + [nxt]}
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, path + [nxt]))

    reason = "blocked by " + ", ".join(blocked[:3]) if blocked else "no connected path"
    return {"ok": False, "reason": reason, "path": []}


def find_sound_path(fz: str, tz: str, zones: list[dict[str, Any]], connections: list[dict[str, Any]]) -> dict[str, Any]:
    zone_ids = {str(z.get("id")) for z in zones if z.get("id")}
    if fz not in zone_ids or tz not in zone_ids:
        missing = [z for z in (fz, tz) if z not in zone_ids]
        return {"ok": False, "sound": "blocked", "reason": f"unknown zone(s): {', '.join(missing)}", "path": []}
    if fz == tz:
        return {"ok": True, "sound": "clear", "reason": "same zone", "path": [fz]}

    graph = build_graph(connections)
    queue = deque([(fz, [fz], "clear")])
    best_rank = {fz: 0}
    while queue:
        current, path, sound = queue.popleft()
        for nxt, conn in graph.get(current, []):
            edge_sound = str(conn.get("sound", "blocked"))
            if SOUND_RANK.get(edge_sound, 99) >= SOUND_RANK["blocked"]:
                continue
            combined = edge_sound if SOUND_RANK[edge_sound] > SOUND_RANK[sound] else sound
            rank = SOUND_RANK[combined]
            if nxt == tz:
                return {
                    "ok": True,
                    "sound": combined,
                    "reason": "sound path",
                    "path": path + [nxt],
                }
            if rank < best_rank.get(nxt, 100):
                best_rank[nxt] = rank
                queue.append((nxt, path + [nxt], combined))

    return {"ok": False, "sound": "blocked", "reason": "no unblocked sound path", "path": []}


def can_see(fz: str, tz: str, connections: list[dict[str, Any]], zones: list[dict[str, Any]] | None = None) -> bool | None:
    if zones is None:
        zones = [{"id": c.get("from")} for c in connections] + [{"id": c.get("to")} for c in connections]
    result = find_los_path(fz, tz, zones, connections)
    return True if result["ok"] else False


def can_hear(fz: str, tz: str, connections: list[dict[str, Any]], zones: list[dict[str, Any]] | None = None) -> str | None:
    if zones is None:
        zones = [{"id": c.get("from")} for c in connections] + [{"id": c.get("to")} for c in connections]
    result = find_sound_path(fz, tz, zones, connections)
    return result["sound"] if result["ok"] else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and query location zone models.")
    parser.add_argument("location_file", type=Path)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--can-see", nargs=2, metavar=("FROM", "TO"))
    parser.add_argument("--can-hear", nargs=2, metavar=("FROM", "TO"))
    args = parser.parse_args()

    try:
        text = args.location_file.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SystemExit(f"Could not read location file: {args.location_file} ({exc})") from None

    zones, connections, issues = parse_zones(text)

    if args.validate:
        if issues:
            print(f"Issues ({len(issues)}):")
            for issue in issues:
                print(f"  ! {issue}")
            sys.exit(1)
        print(f"Valid. {len(zones)} zones, {len(connections)} connections.")

    if args.list:
        for zone in zones:
            occ = zone.get("initial_occupants", [])
            print(
                f"  {zone['id']} | {zone.get('name','?')} | "
                f"light={zone.get('ambient_light','?')} noise={zone.get('ambient_noise','?')} occupants={occ}"
            )
        print()
        for conn in connections:
            resolved = resolve_connection(conn)
            los = "LOS" if resolved.get("line_of_sight") else "no-LOS"
            print(
                f"  {conn['from']} -> {conn['to']} | {conn.get('type','?')} | "
                f"dist={resolved.get('distance','?')}m {los} sound={resolved.get('sound','?')}"
            )

    if args.can_see:
        fz, tz = args.can_see
        result = find_los_path(fz, tz, zones, connections)
        label = "YES" if result["ok"] else "NO"
        path = f" path={format_path(result['path'])}" if result["path"] else ""
        print(f"LOS {fz} -> {tz}: {label} ({result['reason']}){path}")

    if args.can_hear:
        fz, tz = args.can_hear
        result = find_sound_path(fz, tz, zones, connections)
        label = result["sound"].upper() if result["ok"] else "BLOCKED"
        path = f" path={format_path(result['path'])}" if result["path"] else ""
        print(f"Sound {fz} -> {tz}: {label} ({result['reason']}){path}")


if __name__ == "__main__":
    main()
