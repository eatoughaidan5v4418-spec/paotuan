#!/usr/bin/env python3
"""Quick player state check. GM runs this before any NPC reaction to player claims."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Quick player state check.")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()

    cs_path = args.root / "campaign" / "campaign_state.json"
    cs = json.loads(cs_path.read_text(encoding="utf-8-sig"))
    players = cs.get("player_characters", [])
    if not players:
        print("??????????? /new ??????????")
        return
    pc = players[0]

    print("=== 玩家角色状态 ===")
    print(f"  姓名:     {pc.get('name', '?')}")
    print(f"  修为:     {pc.get('realm', '?')} (lv.{pc.get('realm_level', 0)})")
    print(f"  灵根:     {pc.get('spiritual_root', '?')}")
    print(f"  生命:     {pc.get('health', '?')}/{pc.get('max_health', '?')}")
    print(f"  灵力:     {pc.get('qi', '?')}/{pc.get('max_qi', '?')}")
    print(f"  物品栏:   {pc.get('inventory', [])}")
    print(f"  异常状态: {pc.get('conditions', [])}")
    print(f"  位置:     {pc.get('location_id', '?')}")
    stats = pc.get('stats', {})
    print(f"  战力: +{stats.get('combat',0)}  感知: +{stats.get('perception',0)}  社交: +{stats.get('social',0)}")
    print()
    print("=== 当前场景 ===")
    scene = cs.get("current_scene", {})
    print(f"  地点:   {scene.get('location_id')}")
    print(f"  在场:   {scene.get('present_entities')}")
    print(f"  时间:   {cs.get('current_time')}")


if __name__ == "__main__":
    main()
