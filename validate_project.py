#!/usr/bin/env python3
"""Validate the entire paotuan project: JSON structure, required files, schema compliance."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def resolve_campaign_root(value: Path | None) -> tuple[Path, Path, list[str]]:
    """Resolve --root as repo root, campaign container, or campaign data dir.

    Supported inputs:
    - repo/project root containing campaign/
    - a campaign container containing campaign/
    - the campaign data directory itself, containing campaign_state.json
    """
    candidate = (value or ROOT).resolve()
    messages: list[str] = []

    if not candidate.exists():
        return ROOT, candidate / "campaign", [f"root does not exist: {candidate}"]

    if (candidate / "campaign_state.json").exists():
        return ROOT, candidate, messages

    nested = candidate / "campaign"
    if (nested / "campaign_state.json").exists():
        return ROOT, nested, messages

    return ROOT, nested, [f"could not find campaign_state.json under: {candidate}"]


def type_matches(value, expected) -> bool:
    if isinstance(expected, list):
        return any(type_matches(value, item) for item in expected)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def validate_schema_value(value, schema: dict, path: str = "$") -> list[str]:
    """Small local JSON Schema subset validator for project schemas.

    It intentionally supports only the keywords used by this repo's schemas:
    type, required, properties, additionalProperties=false, items, enum,
    minimum, maximum. This avoids adding a runtime dependency just for local
    project integrity checks.
    """
    errors: list[str] = []

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {schema['enum']!r}")
        return errors

    if "type" in schema and not type_matches(value, schema["type"]):
        errors.append(f"{path}: expected type {schema['type']!r}, got {type(value).__name__}")
        return errors

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value!r} < minimum {schema['minimum']!r}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value!r} > maximum {schema['maximum']!r}")

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required field {key!r}")

        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            for key in extra:
                errors.append(f"{path}: additional property {key!r} is not allowed")

        for key, child in properties.items():
            if key in value:
                errors.extend(validate_schema_value(value[key], child, f"{path}.{key}"))

    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            errors.extend(validate_schema_value(item, schema["items"], f"{path}[{index}]"))

    return errors


def check_schema_compliance(data_path: Path, schema_path: Path, label: str) -> bool:
    try:
        data = json.loads(data_path.read_text(encoding="utf-8-sig"))
        schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        fail(f"{label} invalid JSON before schema validation: {e}")
        return False

    errors = validate_schema_value(data, schema)
    if errors:
        fail(f"{label} schema mismatch ({len(errors)} issue(s))")
        for err in errors[:20]:
            print(f"    - {err}")
        if len(errors) > 20:
            print(f"    - ... {len(errors) - 20} more")
        return False

    ok(f"{label} schema compliant")
    return True


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def check_file(path: Path, label: str) -> bool:
    if path.exists():
        ok(f"{label} exists")
        return True
    fail(f"{label} MISSING: {path}")
    return False


def check_json(path: Path, label: str, required_fields: list[str] | None = None) -> bool:
    if not path.exists():
        fail(f"{label} MISSING: {path}")
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        fail(f"{label} INVALID JSON: {e}")
        return False
    ok(f"{label} valid JSON")
    if required_fields:
        if not isinstance(data, dict):
            fail(f"{label} expected JSON object for required field check")
            return False
        missing = [f for f in required_fields if f not in data]
        if missing:
            fail(f"{label} missing fields: {missing}")
            return False
        ok(f"{label} has required fields")
    return True


def check_jsonl(path: Path, label: str) -> bool:
    if not path.exists():
        fail(f"{label} MISSING: {path}")
        return False
    try:
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        if not lines or lines == [""]:
            ok(f"{label} empty (OK)")
            return True
        for i, line in enumerate(lines):
            if line.strip():
                json.loads(line)
        ok(f"{label} valid JSONL ({len(lines)} lines)")
        return True
    except json.JSONDecodeError as e:
        fail(f"{label} INVALID JSONL line: {e}")
        return False


def load_jsonl_records(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            records.append(item)
    return records


def load_npc_memory_ids(campaign_dir: Path) -> dict[str, set[str]]:
    memory_ids: dict[str, set[str]] = {}
    npcs_dir = campaign_dir / "npcs"
    if not npcs_dir.exists():
        return memory_ids
    for graph_path in sorted(npcs_dir.glob("*memory_graph.json")):
        try:
            graph = json.loads(graph_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            continue
        if not isinstance(graph, dict):
            continue
        npc_id = str(graph.get("npc_id") or graph_path.name.removesuffix(".memory_graph.json"))
        memory_ids[npc_id] = {
            item.get("id")
            for item in graph.get("memory_nodes", [])
            if isinstance(item, dict) and item.get("id")
        }
    return memory_ids


def check_world_graph_integrity(campaign_dir: Path) -> bool:
    path = campaign_dir / "world_graph.jsonl"
    if not path.exists():
        return True
    records = load_jsonl_records(path)
    ok_integrity = True
    seen: dict[str, int] = {}
    duplicate_ids: list[str] = []
    for record in records:
        record_id = record.get("id")
        if not record_id:
            continue
        if record_id in seen:
            duplicate_ids.append(str(record_id))
        seen[str(record_id)] = seen.get(str(record_id), 0) + 1
    if duplicate_ids:
        for record_id in sorted(set(duplicate_ids)):
            fail(f"duplicate world_graph id: {record_id}")
        ok_integrity = False
    else:
        ok("world_graph.jsonl ids unique")

    memory_ids = load_npc_memory_ids(campaign_dir)
    for record in records:
        source_memory_id = record.get("source_memory_id")
        npc_id = record.get("npc_id")
        if not source_memory_id or not npc_id:
            continue
        if source_memory_id not in memory_ids.get(str(npc_id), set()):
            fail(
                f"source_memory_id not found in NPC graph: {record.get('id')} "
                f"npc_id={npc_id} source_memory_id={source_memory_id}"
            )
            ok_integrity = False

    return ok_integrity


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=None, help="Campaign root directory")
    args, _ = ap.parse_known_args()
    project_root, c, root_errors = resolve_campaign_root(args.root)
    errors = 0

    print("\n=== Resolved paths ===")
    print(f"  project_root: {project_root}")
    print(f"  campaign_dir: {c}")
    for err in root_errors:
        fail(err)
        errors += 1

    print("\n=== Core files ===")
    if not check_file(project_root / "AGENTS.md", "AGENTS.md"): errors += 1
    if not check_file(project_root / "gm-runtime-protocol.md", "gm-runtime-protocol.md"): errors += 1
    if not check_file(project_root / "gm-self-audit.md", "gm-self-audit.md"): errors += 1
    if not check_file(project_root / ".gitignore", ".gitignore"): errors += 1

    print("\n=== Campaign state ===")
    if not check_json(c / "campaign_state.json", "campaign_state.json",
                      ["campaign_id", "current_turn", "current_time", "current_scene", "player_characters", "quests"]):
        errors += 1

    print("\n=== World clocks ===")
    if not check_json(c / "world_clocks.json", "world_clocks.json", ["clocks"]): errors += 1

    print("\n=== World graph ===")
    world_graph_path = c / "world_graph.jsonl"
    if not check_jsonl(world_graph_path, "world_graph.jsonl"):
        errors += 1
    elif not check_world_graph_integrity(c):
        errors += 1

    print("\n=== Resources ===")
    if not check_json(c / "resources.json", "resources.json", ["entities"]): errors += 1

    print("\n=== Player knowledge ===")
    if not check_json(c / "player_knowledge.json", "player_knowledge.json"): errors += 1

    print("\n=== Quest graph ===")
    if not check_json(c / "quest_graph.json", "quest_graph.json", ["quests"]): errors += 1

    print("\n=== Rumors ===")
    if not check_json(c / "rumors.json", "rumors.json", ["rumors"]): errors += 1

    print("\n=== Chaos factor ===")
    if not check_json(c / "chaos_factor.json", "chaos_factor.json"): errors += 1

    print("\n=== Conditions ===")
    if not check_json(c / "conditions.json", "conditions.json", ["entities"]): errors += 1

    print("\n=== Progress tracks ===")
    if not check_json(c / "progress_tracks.json", "progress_tracks.json", ["tracks"]): errors += 1

    print("\n=== Oracle tables ===")
    if not check_json(c / "oracles.json", "oracles.json", ["tables"]): errors += 1

    print("\n=== NPCs ===")
    npc_graph_schema = project_root / "schemas" / "npc_memory_graph.schema.json"
    for npc_yaml in sorted((c / "npcs").glob("*.yaml")):
        ok(f"NPC profile: {npc_yaml.name}")
    for npc_graph in sorted((c / "npcs").glob("*memory_graph.json")):
        if not check_json(npc_graph, f"NPC graph: {npc_graph.name}",
                          ["npc_id", "current_turn", "memory_nodes"]):
            errors += 1
        elif npc_graph_schema.exists() and not check_schema_compliance(
            npc_graph, npc_graph_schema, f"NPC graph: {npc_graph.name}"
        ):
            errors += 1

    print("\n=== Events ===")
    event_schema = project_root / "schemas" / "event_visibility.schema.json"
    events_dir = c / "events"
    if events_dir.exists():
        for event_file in sorted(events_dir.glob("*.json")):
            if not check_json(event_file, f"Event: {event_file.name}"):
                errors += 1
            elif event_schema.exists() and not check_schema_compliance(
                event_file, event_schema, f"Event: {event_file.name}"
            ):
                errors += 1

    print("\n=== Locations ===")
    for loc in sorted((c / "locations").glob("*.yaml")):
        ok(f"Location: {loc.name}")

    print("\n=== Lore ===")
    for lore_file in sorted((c / "lore").glob("*.yaml")):
        ok(f"Lore: {lore_file.name}")

    print("\n=== Prompts ===")
    prompt_dir = project_root / "prompts"
    if prompt_dir.exists():
        for prompt in sorted(prompt_dir.glob("*.md")):
            ok(f"Prompt: {prompt.name}")

    print("\n=== Schemas ===")
    schema_dir = project_root / "schemas"
    if schema_dir.exists():
        for schema in sorted(schema_dir.glob("*.json")):
            if not check_json(schema, f"Schema: {schema.name}"): errors += 1

    print("\n=== Tools ===")
    tools_dir = project_root / "tools"
    for tool in sorted(tools_dir.glob("*.py")):
        ok(f"Tool: {tool.name}")

    print("\n=== Session logs ===")
    for log in sorted((c / "session_logs").glob("*.md")):
        ok(f"Log: {log.name}")

    print("\n=== Turn packets ===")
    turn_packet_schema = project_root / "schemas" / "turn_packet.schema.json"
    state_patch_schema = project_root / "schemas" / "state_patch.schema.json"
    turn_packets_dir = c / "turn_packets"
    if turn_packets_dir.exists():
        for packet_file in sorted(turn_packets_dir.glob("*.json")):
            if not check_json(packet_file, f"Turn packet: {packet_file.name}"):
                errors += 1
                continue

            if packet_file.name.startswith("turn_"):
                if turn_packet_schema.exists() and not check_schema_compliance(
                    packet_file, turn_packet_schema, f"Turn packet: {packet_file.name}"
                ):
                    errors += 1
            elif state_patch_schema.exists():
                if not check_schema_compliance(
                    packet_file, state_patch_schema, f"State patch: {packet_file.name}"
                ):
                    errors += 1

    print()
    if errors:
        print(f"[FAIL] {errors} issue(s) found")
        return 1
    else:
        print("[OK] All checks passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())

