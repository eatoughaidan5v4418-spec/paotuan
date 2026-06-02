from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

import apply_patch as patcher  # noqa: E402
import player_knowledge  # noqa: E402
import validate_project  # noqa: E402
import web_api  # noqa: E402
import play_game  # noqa: E402
import time_utils  # noqa: E402
import zone_validator  # noqa: E402
import run_turn  # noqa: E402


def run_cmd(args: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=30,
    )


def run_cmd_with_env(
    args: list[str],
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=30,
        env=env,
    )


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def minimal_campaign(root: Path) -> None:
    campaign = root / "campaign"
    for path in (campaign / "npcs", campaign / "locations", campaign / "lore", campaign / "session_logs"):
        path.mkdir(parents=True, exist_ok=True)
    write_json(
        campaign / "campaign_state.json",
        {
            "campaign_id": "test",
            "current_turn": 1,
            "current_time": "第 1 日 20:00",
            "current_scene": {"location_id": "loc_test", "present_entities": ["npc_a"], "active_threads": []},
            "player_characters": [
                {
                    "id": "pc_main",
                    "inventory": [],
                    "health": 10,
                    "max_health": 12,
                    "qi": 5,
                    "max_qi": 8,
                    "effect_points": 500,
                    "stats": {"body": 1},
                    "conditions": [],
                }
            ],
            "quests": [],
        },
    )
    write_json(campaign / "world_clocks.json", {"clocks": []})
    write_json(campaign / "conditions.json", {"entities": {}})
    write_json(campaign / "resources.json", {"entities": {"pc_main": {"特效值": 500}}, "pc_main": {"特殊物品": ["系统新手礼包（未开启）"]}})
    write_json(campaign / "player_knowledge.json", {})
    write_json(campaign / "quest_graph.json", {"quests": []})
    write_json(campaign / "rumors.json", {"rumors": []})
    write_json(campaign / "chaos_factor.json", {})
    write_json(campaign / "progress_tracks.json", {"tracks": []})
    write_json(campaign / "oracles.json", {"tables": {}})
    (campaign / "world_graph.jsonl").write_text("", encoding="utf-8")
    write_json(
        campaign / "npcs" / "npc_a.memory_graph.json",
        {
            "npc_id": "npc_a",
            "current_turn": 1,
            "memory_policy_id": "npc_memory_policy_v1",
            "memory_nodes": [],
            "interpretation_nodes": [],
            "understanding_nodes": [],
            "revision_events": [],
            "relation_edges": [],
            "beliefs": [],
            "plans": [],
        },
    )


def valid_patch() -> dict[str, object]:
    return {
        "time_delta": "无",
        "location_changes": [],
        "inventory_changes": [],
        "relationship_changes": [],
        "new_facts": [],
        "contradictions": [],
        "npc_memory_writes": [
            {
                "npc_id": "npc_a",
                "memory": "A terrifying event happened.",
                "memory_type": "episodic",
                "source": "saw",
                "visibility_path": "direct_visual",
                "visibility_evidence": {
                    "event_id": "event_test_visibility",
                    "observer_id": "npc_a",
                    "memory_allowed": True,
                    "visibility_path": "direct_visual",
                    "subjective_summary": "A terrifying event happened.",
                    "allowed_memory_scope": ["event_summary"],
                    "forbidden_memory_scope": [],
                },
                "confidence": 0.9,
                "emotional_valence": -2,
                "salience": 0.8,
            }
        ],
        "open_threads": [],
    }


class ValidateProjectRootTests(unittest.TestCase):
    def test_resolves_project_root_campaign_dir_and_container(self) -> None:
        _, campaign_dir, errors = validate_project.resolve_campaign_root(ROOT)
        self.assertEqual(campaign_dir, ROOT / "campaign")
        self.assertEqual(errors, [])

        _, direct_dir, direct_errors = validate_project.resolve_campaign_root(ROOT / "campaign")
        self.assertEqual(direct_dir, ROOT / "campaign")
        self.assertEqual(direct_errors, [])

        _, xianxia_dir, xianxia_errors = validate_project.resolve_campaign_root(ROOT / "xianxia_campaign")
        self.assertEqual(xianxia_dir, ROOT / "xianxia_campaign" / "campaign")
        self.assertEqual(xianxia_errors, [])

    def test_validate_project_cli_accepts_direct_campaign_dir(self) -> None:
        result = run_cmd(["validate_project.py", "--root", "campaign"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("campaign_dir:", result.stdout)

    def test_validate_project_cli_reports_missing_root(self) -> None:
        result = run_cmd(["validate_project.py", "--root", "does_not_exist"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("root does not exist", result.stdout)

    def test_validate_project_reports_duplicate_world_graph_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            world_graph = root / "campaign" / "world_graph.jsonl"
            world_graph.write_text(
                "\n".join(
                    [
                        json.dumps({"record_type": "node", "id": "event_duplicate", "node_type": "Event"}, ensure_ascii=False),
                        json.dumps({"record_type": "node", "id": "event_duplicate", "node_type": "Event"}, ensure_ascii=False),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_cmd(["validate_project.py", "--root", str(root)])

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate world_graph id", result.stdout)

    def test_validate_project_reports_world_graph_missing_source_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            world_graph = root / "campaign" / "world_graph.jsonl"
            world_graph.write_text(
                json.dumps(
                    {
                        "record_type": "node",
                        "id": "interp_missing_source",
                        "node_type": "Interpretation",
                        "npc_id": "npc_a",
                        "source_memory_id": "mem_missing",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_cmd(["validate_project.py", "--root", str(root)])

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("source_memory_id not found", result.stdout)


class ApplyPatchHardeningTests(unittest.TestCase):
    def test_patch_validation_requires_visibility_and_ranges(self) -> None:
        patch = valid_patch()
        write = dict(patch["npc_memory_writes"][0])  # type: ignore[index]
        write.pop("visibility_path")
        write["confidence"] = 1.5
        write["emotional_valence"] = -3
        patch["npc_memory_writes"] = [write]

        errors = patcher.validate_patch_structure(patch)  # type: ignore[arg-type]

        self.assertTrue(any("visibility_path" in err for err in errors))
        self.assertTrue(any("confidence out of range" in err for err in errors))
        self.assertTrue(any("emotional_valence out of range" in err for err in errors))

    def test_apply_patch_preserves_minus_two_emotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            patch = valid_patch()

            patcher.apply_patch(root, patch, 1, "第 1 日 20:00", "0001", dry_run=False)  # type: ignore[arg-type]

            graph = json.loads((root / "campaign" / "npcs" / "npc_a.memory_graph.json").read_text(encoding="utf-8"))
            self.assertEqual(graph["memory_nodes"][0]["emotional_valence"], -2.0)

    def test_bare_npc_id_is_canonicalized_and_added_to_scene(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            patch = valid_patch()
            patch["npc_memory_writes"] = [
                {
                    "npc_id": "laochen",
                    "memory": "老陈在巷尾和玩家交谈。",
                    "memory_type": "episodic",
                    "source": "saw",
                    "visibility_path": "direct_visual",
                    "visibility_evidence": {
                        "event_id": "event_laochen_talk",
                        "observer_id": "laochen",
                        "memory_allowed": True,
                        "visibility_path": "direct_visual",
                        "subjective_summary": "老陈在巷尾和玩家交谈。",
                        "allowed_memory_scope": ["conversation"],
                        "forbidden_memory_scope": [],
                    },
                    "confidence": 0.9,
                    "emotional_valence": 0,
                    "salience": 0.7,
                }
            ]

            normalized = play_game.normalize_patch(patch, None, None)  # type: ignore[arg-type]
            self.assertEqual(normalized["npc_memory_writes"][0]["npc_id"], "npc_laochen")

            patcher.apply_patch(root, normalized, 1, "第 1 日 20:00", "0001", dry_run=False)  # type: ignore[arg-type]

            state = json.loads((root / "campaign" / "campaign_state.json").read_text(encoding="utf-8"))
            self.assertIn("npc_laochen", state["current_scene"]["present_entities"])
            self.assertTrue((root / "campaign" / "npcs" / "npc_laochen.memory_graph.json").exists())

    def test_apply_patch_advances_turn_counter(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            patch = valid_patch()
            patch["npc_memory_writes"] = []

            patcher.apply_patch(root, patch, 1, "第 1 日 20:00", "0001", dry_run=False)  # type: ignore[arg-type]

            state = json.loads((root / "campaign" / "campaign_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["current_turn"], 2)

    def test_open_threads_update_existing_description(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            state_path = root / "campaign" / "campaign_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["open_threads"] = [
                {
                    "id": "open_thread_0001",
                    "description": "老陈的阵法师招募",
                    "next_pressure": "旧压力",
                    "created_turn": 1,
                    "status": "active",
                }
            ]
            state["current_scene"]["active_threads"] = ["open_thread_0001"]
            write_json(state_path, state)
            patch = valid_patch()
            patch["npc_memory_writes"] = []
            patch["open_threads"] = [
                {
                    "thread": "老陈的阵法师招募",
                    "next_pressure": "新压力",
                }
            ]

            patcher.apply_patch(root, patch, 2, "第 1 日 20:00", "0001", dry_run=False)  # type: ignore[arg-type]

            updated = json.loads(state_path.read_text(encoding="utf-8"))
            active_threads = [item for item in updated["open_threads"] if item.get("status") == "active"]
            self.assertEqual(len(active_threads), 1)
            self.assertEqual(active_threads[0]["id"], "open_thread_0001")
            self.assertEqual(active_threads[0]["next_pressure"], "新压力")
            self.assertEqual(updated["current_scene"]["active_threads"], ["open_thread_0001"])

    def test_open_threads_prune_old_active_items_to_current_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            state_path = root / "campaign" / "campaign_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["open_threads"] = [
                {
                    "id": f"open_thread_{index:04d}",
                    "description": f"old thread {index}",
                    "next_pressure": "old pressure",
                    "created_turn": index,
                    "status": "active",
                }
                for index in range(1, 10)
            ]
            state["current_scene"]["active_threads"] = [
                item["id"] for item in state["open_threads"]
            ]
            write_json(state_path, state)
            patch = valid_patch()
            patch["npc_memory_writes"] = []
            patch["open_threads"] = [
                {"thread": "new urgent thread", "next_pressure": "new pressure"}
            ]

            patcher.apply_patch(root, patch, 10, "第 1 日 20:00", "0001", dry_run=False)  # type: ignore[arg-type]

            updated = json.loads(state_path.read_text(encoding="utf-8"))
            active_threads = [
                item for item in updated["open_threads"] if item.get("status") == "active"
            ]
            dormant_threads = [
                item for item in updated["open_threads"] if item.get("status") == "dormant"
            ]
            self.assertEqual(len(active_threads), patcher.MAX_ACTIVE_THREADS)
            self.assertEqual({item["id"] for item in dormant_threads}, {"open_thread_0001", "open_thread_0002"})
            self.assertNotIn("open_thread_0001", updated["current_scene"]["active_threads"])

    def test_apply_patch_updates_player_state_for_character_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            resources_path = root / "campaign" / "resources.json"
            write_json(resources_path, {"entities": {"pc_main": {"特效值": 500}}})
            patch = valid_patch()
            patch["npc_memory_writes"] = []
            patch["player_state_changes"] = [
                {
                    "entity_id": "pc_main",
                    "field": "health",
                    "delta": -3,
                    "reason": "trap damage",
                },
                {
                    "entity_id": "pc_main",
                    "field": "condition",
                    "operation": "add",
                    "value": {"name": "injured", "severity": "minor"},
                    "reason": "trap damage",
                },
                {
                    "entity_id": "pc_main",
                    "field": "stats.body",
                    "delta": 1,
                    "reason": "training progress",
                },
                {
                    "entity_id": "pc_main",
                    "field": "effect_points",
                    "operation": "delta",
                    "value": -50,
                    "reason": "effect use",
                },
            ]

            errors = patcher.validate_patch_structure(patch)  # type: ignore[arg-type]
            self.assertEqual(errors, [])
            patcher.apply_patch(root, patch, 1, "绗?1 鏃?20:00", "0001", dry_run=False)  # type: ignore[arg-type]

            state = json.loads((root / "campaign" / "campaign_state.json").read_text(encoding="utf-8"))
            pc = state["player_characters"][0]
            self.assertEqual(pc["health"], 7)
            self.assertEqual(pc["stats"]["body"], 2)
            self.assertEqual(pc["effect_points"], 450)
            self.assertIn("injured", pc["conditions"])
            resources = json.loads(resources_path.read_text(encoding="utf-8"))
            self.assertEqual(resources["entities"]["pc_main"]["特效值"], 450)

            visible = web_api.visible_state(root)
            self.assertEqual(visible["player"]["health"], 7)
            self.assertEqual(visible["player"]["effect_points"], 450)
            self.assertIn("injured", visible["player"]["conditions"])

    def test_apply_patch_accepts_manifest_player_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            state_path = root / "campaign" / "campaign_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["rules"] = {
                "capabilities": {"system": False, "cultivation": False},
                "character_sheet": {
                    "sections": [
                        {
                            "id": "mystery_path",
                            "title": "\u9014\u5f84",
                            "items": [
                                {"field": "sequence", "label": "\u5e8f\u5217"},
                                {"field": "potion_stage", "label": "\u9b54\u836f"},
                            ],
                        }
                    ]
                },
            }
            state["player_characters"][0]["sequence"] = 9
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

            patch = valid_patch()
            patch["npc_memory_writes"] = []
            patch["player_state_changes"] = [
                {
                    "entity_id": "pc_main",
                    "field": "potion_stage",
                    "operation": "set",
                    "value": "\u5360\u535c\u5bb6\u9b54\u836f\u6d88\u5316 40%",
                    "reason": "potion digestion progressed",
                }
            ]

            errors = patcher.validate_patch_structure(patch)  # type: ignore[arg-type]
            self.assertEqual(errors, [])
            patcher.apply_patch(root, patch, 1, "\u7b2c 1 \u65e5 20:00", "0001", dry_run=False)  # type: ignore[arg-type]

            updated = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["player_characters"][0]["potion_stage"], "\u5360\u535c\u5bb6\u9b54\u836f\u6d88\u5316 40%")
            visible = web_api.visible_state(root)
            sheet_values = {
                item["field"]: item["value"]
                for section in visible["character_sheet"]["sections"]
                for item in section["items"]
            }
            self.assertEqual(sheet_values["potion_stage"], "\u5360\u535c\u5bb6\u9b54\u836f\u6d88\u5316 40%")

    def test_inventory_gain_marks_starter_pack_opened(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            patch = valid_patch()
            patch["npc_memory_writes"] = []
            patch["inventory_changes"] = [
                {
                    "owner_id": "pc_main",
                    "item_id": "归元诀玉简",
                    "change": "gain",
                    "evidence": "starter pack opened",
                }
            ]

            patcher.apply_patch(root, patch, 1, "绗?1 鏃?20:00", "0001", dry_run=False)  # type: ignore[arg-type]

            state = json.loads((root / "campaign" / "campaign_state.json").read_text(encoding="utf-8"))
            self.assertIn("归元诀玉简", state["player_characters"][0]["inventory"])
            resources = json.loads((root / "campaign" / "resources.json").read_text(encoding="utf-8"))
            self.assertEqual(resources["pc_main"]["特殊物品"], [])

    def test_currency_inventory_change_updates_resources_not_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            resources_path = root / "campaign" / "resources.json"
            write_json(resources_path, {"entities": {"pc_main": {"\u7075\u77f3": 50}}})
            patch = valid_patch()
            patch["npc_memory_writes"] = []
            patch["inventory_changes"] = [
                {
                    "owner_id": "pc_main",
                    "item_id": "\u7075\u77f3",
                    "change": "gain",
                    "evidence": "\u4e94\u5341\u5757\u7075\u77f3\u5b9a\u91d1",
                }
            ]

            patcher.apply_patch(root, patch, 1, "\u7b2c 1 \u65e5 20:00", "0001", dry_run=False)  # type: ignore[arg-type]

            state = json.loads((root / "campaign" / "campaign_state.json").read_text(encoding="utf-8"))
            resources = json.loads(resources_path.read_text(encoding="utf-8"))
            self.assertEqual(resources["entities"]["pc_main"]["\u7075\u77f3"], 100)
            self.assertNotIn("\u7075\u77f3", state["player_characters"][0]["inventory"])

    def test_player_move_to_unknown_location_creates_minimal_location_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            patch = valid_patch()
            patch["npc_memory_writes"] = []
            patch["location_changes"] = [
                {
                    "entity_id": "pc_main",
                    "from": "loc_test",
                    "to": "qingyun_valley",
                    "reason": "accepted a job outside town",
                }
            ]

            patcher.apply_patch(root, patch, 1, "\u7b2c 1 \u65e5 20:00", "0001", dry_run=False)  # type: ignore[arg-type]

            state = json.loads((root / "campaign" / "campaign_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["current_scene"]["location_id"], "qingyun_valley")
            self.assertEqual(state["current_scene"]["present_entities"], ["pc_main"])
            self.assertTrue((root / "campaign" / "locations" / "qingyun_valley.yaml").exists())

    def test_normalize_patch_infers_npc_departure_and_inventory_shape(self) -> None:
        packet = {
            "campaign_before": {
                "current_scene": {
                    "location_id": "loc_test",
                    "present_entities": ["pc_main", "npc_liu"],
                },
                "player_characters": [{"id": "pc_main"}],
            },
            "context": {
                "present_npcs": [{"id": "npc_liu", "profile_text": "id: npc_liu\nname: 刘师兄\n"}],
            },
        }
        response = {
            "visible_text": {
                "scene": "刘师兄的气息已经彻底离开感知范围。",
            }
        }
        patch = valid_patch()
        patch["npc_memory_writes"] = []
        patch["inventory_changes"] = [{"action": "add", "item": "归元诀玉简"}]

        normalized = play_game.normalize_patch(patch, response, packet)  # type: ignore[arg-type]

        self.assertEqual(normalized["inventory_changes"][0]["owner_id"], "pc_main")
        self.assertEqual(normalized["inventory_changes"][0]["change"], "gain")
        self.assertEqual(normalized["location_changes"][0]["entity_id"], "npc_liu")
        self.assertEqual(normalized["location_changes"][0]["to"], "offscreen")

    def test_normalize_patch_does_not_depart_npc_for_unrelated_disappearance(self) -> None:
        packet = {
            "campaign_before": {
                "current_scene": {
                    "location_id": "loc_test",
                    "present_entities": ["pc_main", "npc_liu"],
                },
                "player_characters": [{"id": "pc_main"}],
            },
            "context": {
                "present_npcs": [{"id": "npc_liu", "profile_text": "id: npc_liu\nname: 刘师兄\n"}],
            },
        }
        response = {
            "visible_text": {
                "scene": "刘师兄站在你身侧。远处一只妖兽的影子一闪而过，很快消失在林中。",
            }
        }
        patch = valid_patch()
        patch["npc_memory_writes"] = []

        normalized = play_game.normalize_patch(patch, response, packet)  # type: ignore[arg-type]

        self.assertEqual(normalized["location_changes"], [])

    def test_normalize_patch_does_not_mutate_project_campaign_state(self) -> None:
        project_state_path = ROOT / "campaign" / "campaign_state.json"
        before = project_state_path.read_text(encoding="utf-8-sig")
        before_mtime = project_state_path.stat().st_mtime_ns
        packet = {
            "campaign_before": {
                "current_scene": {"location_id": "loc_test", "present_entities": ["pc_main"]},
                "player_characters": [{"id": "pc_main", "effect_points": 0}],
            },
        }
        patch = valid_patch()
        patch["npc_memory_writes"] = []

        play_game.normalize_patch(patch, None, packet)  # type: ignore[arg-type]

        self.assertEqual(project_state_path.read_text(encoding="utf-8-sig"), before)
        self.assertEqual(project_state_path.stat().st_mtime_ns, before_mtime)

    def test_normalize_patch_infers_split_party_sub_locations(self) -> None:
        packet = {
            "player_action": "我让老陈留在谷口看守退路，不要跟进阵眼；我自己进入古阵核心观察。",
            "campaign_before": {
                "current_scene": {
                    "location_id": "qingyun_valley",
                    "present_entities": ["player_lin", "npc_laochen"],
                },
                "player_characters": [{"id": "player_lin"}],
            },
            "context": {
                "present_npcs": [{"id": "npc_laochen", "profile_text": "id: npc_laochen\nname: 老陈\n"}],
            },
        }
        response = {
            "visible_text": {
                "action_result": "老陈留在谷口看守工具箱，你独自进入阵眼。",
            }
        }
        patch = valid_patch()
        patch["npc_memory_writes"] = []

        normalized = play_game.normalize_patch(patch, response, packet)  # type: ignore[arg-type]

        by_entity = {item["entity_id"]: item["to"] for item in normalized["location_changes"]}
        self.assertEqual(by_entity["player_lin"], "qingyun_valley_core")
        self.assertEqual(by_entity["npc_laochen"], "qingyun_valley_entrance")

    def test_apply_patch_cli_invalid_json_has_no_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            bad = Path(temp) / "bad.json"
            bad.write_text("not json", encoding="utf-8")

            result = run_cmd(["tools/apply_patch.py", str(bad), "--dry-run"])

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not valid JSON", result.stderr + result.stdout)
            self.assertNotIn("Traceback", result.stderr + result.stdout)

    def test_apply_state_patch_reports_semantic_apply_errors_as_not_applied(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            config = play_game.GameConfig(
                root=root,
                base_url="",
                api_key="",
                model="api-test-model",
                auto_apply=True,
                max_tool_rounds=0,
                allowed_roots=["campaign"],
            )
            patch = valid_patch()
            patch["npc_memory_writes"] = []
            patch["npc_interpretation_writes"] = [
                {
                    "id": "interp_bad",
                    "npc_id": "npc_a",
                    "derived_from_event_id": "event_missing",
                    "derived_from_memory_id": "mem_missing",
                    "text": "Bad dangling interpretation.",
                    "appraisal": {
                        "goal_impact": "neutral",
                        "threat_level": 0,
                        "opportunity_level": 0,
                        "agency": "unknown",
                        "moral_judgment": "unknown",
                        "relationship_signal": "none",
                    },
                    "emotion": {"label": "none", "valence": 0, "intensity": 0},
                    "confidence": 0.5,
                    "importance": 0.5,
                    "related_entities": ["npc_a"],
                    "possible_misunderstanding": True,
                }
            ]

            result = play_game.apply_state_patch(config, patch)  # type: ignore[arg-type]

            self.assertFalse(result["applied"])
            self.assertTrue(result["report"]["errors"])

    def test_run_ai_turn_commits_world_clock_preview_with_audit_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            write_json(
                root / "campaign" / "world_clocks.json",
                {
                    "current_turn": 1,
                    "clocks": [
                        {
                            "id": "clock_test",
                            "type": "threat_countdown",
                            "owner_id": "faction_test",
                            "title": "Test pressure",
                            "value": 0,
                            "max_value": 3,
                            "status": "active",
                            "visibility": "secret",
                            "next_tick_at": "第 1 日 20:10",
                            "tick_interval": "10 分钟",
                            "recent_updates": [],
                        }
                    ],
                },
            )
            config = play_game.GameConfig(
                root=root,
                base_url="",
                api_key="test-key",
                model="api-test-model",
                auto_apply=True,
                max_tool_rounds=0,
                allowed_roots=["campaign"],
            )
            original_call_chat_api = play_game.call_chat_api
            try:
                play_game.call_chat_api = lambda _config, _messages: json.dumps(  # type: ignore[assignment]
                    {
                        "tool_requests": [],
                        "visible_text": {"scene": "你等待片刻，离屏压力继续推进。"},
                        "state_patch": valid_patch() | {"npc_memory_writes": []},
                    },
                    ensure_ascii=False,
                )
                play_game.run_ai_turn(config, "我等待半小时", 30, 5)
            finally:
                play_game.call_chat_api = original_call_chat_api  # type: ignore[assignment]

            clocks = json.loads((root / "campaign" / "world_clocks.json").read_text(encoding="utf-8"))
            self.assertEqual(clocks["current_turn"], 2)
            clock = clocks["clocks"][0]
            self.assertEqual(clock["value"], 3)
            self.assertEqual(clock["status"], "complete")
            self.assertTrue(clock["recent_updates"])
            self.assertEqual(clock["recent_updates"][-1]["clock_id"], "clock_test")

    def test_apply_patch_semantic_error_does_not_leave_partial_memory_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            minimal_campaign(root)
            patch = valid_patch()
            patch["npc_interpretation_writes"] = [
                {
                    "id": "interp_bad",
                    "npc_id": "npc_a",
                    "derived_from_event_id": "event_missing",
                    "derived_from_memory_id": "mem_missing",
                    "text": "Bad dangling interpretation.",
                    "appraisal": {
                        "goal_impact": "neutral",
                        "threat_level": 0,
                        "opportunity_level": 0,
                        "agency": "unknown",
                        "moral_judgment": "unknown",
                        "relationship_signal": "none",
                    },
                    "emotion": {"label": "none", "valence": 0, "intensity": 0},
                    "confidence": 0.5,
                    "importance": 0.5,
                    "related_entities": ["npc_a"],
                    "possible_misunderstanding": True,
                }
            ]

            report = patcher.apply_patch(root, patch, 1, "第 1 日 20:00", "0001", dry_run=False)  # type: ignore[arg-type]

            graph = json.loads((root / "campaign" / "npcs" / "npc_a.memory_graph.json").read_text(encoding="utf-8"))
            world_graph = (root / "campaign" / "world_graph.jsonl").read_text(encoding="utf-8")
            self.assertTrue(report["errors"])
            self.assertEqual(graph["memory_nodes"], [])
            self.assertEqual(world_graph, "")


class ZoneValidatorTests(unittest.TestCase):
    def test_multihop_los_and_blocked_door(self) -> None:
        text = (ROOT / "campaign" / "locations" / "old_dock.yaml").read_text(encoding="utf-8")
        zones, connections, issues = zone_validator.parse_zones(text)
        self.assertEqual(issues, [])

        visible = zone_validator.find_los_path("zone_main_pier", "zone_dock_entrance", zones, connections)
        blocked = zone_validator.find_los_path("zone_main_pier", "zone_warehouse", zones, connections)

        self.assertTrue(visible["ok"])
        self.assertFalse(blocked["ok"])
        self.assertIn("blocked", blocked["reason"])

    def test_multihop_sound_and_unknown_zone(self) -> None:
        text = (ROOT / "campaign" / "locations" / "old_dock.yaml").read_text(encoding="utf-8")
        zones, connections, _ = zone_validator.parse_zones(text)

        sound = zone_validator.find_sound_path("zone_main_pier", "zone_warehouse", zones, connections)
        unknown = zone_validator.find_sound_path("zone_missing", "zone_warehouse", zones, connections)

        self.assertTrue(sound["ok"])
        self.assertEqual(sound["sound"], "muffled")
        self.assertFalse(unknown["ok"])
        self.assertIn("unknown zone", unknown["reason"])


class PlayerKnowledgeTests(unittest.TestCase):
    def test_decodes_double_escaped_text_for_display(self) -> None:
        data = {"npc": "\\u7c73\\u62c9", "nested": [{"fact": "\\u65e7\\u7801\\u5934"}]}

        decoded = player_knowledge.decode_escaped_text(data)

        self.assertEqual(decoded["npc"], "米拉")
        self.assertEqual(decoded["nested"][0]["fact"], "旧码头")


class CliSmokeTests(unittest.TestCase):
    def test_run_turn_loads_clock_and_action_relevant_npcs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(ROOT / "campaign", root / "campaign")
            state_path = root / "campaign" / "campaign_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["current_scene"]["location_id"] = "loc_old_dock"
            state["current_scene"]["present_entities"] = ["pc_main", "npc_mira"]
            clocks_path = root / "campaign" / "world_clocks.json"
            clocks = json.loads(clocks_path.read_text(encoding="utf-8"))
            for clock in clocks["clocks"]:
                if clock["id"] == "clock_b_ledger_copy":
                    clock["status"] = "active"
            write_json(clocks_path, clocks)

            context = run_turn.collect_context(
                root,
                state,
                3,
                "我在旧码头观察 npc_a_sentry，并确认 npc_b_clerk 是否听到动静。",
            )

        npc_ids = {npc["id"] for npc in context["present_npcs"]}
        self.assertIn("npc_mira", npc_ids)
        self.assertIn("npc_a_sentry", npc_ids)
        self.assertIn("npc_b_clerk", npc_ids)
        reasons = {
            npc["id"]: set(npc.get("relevance_reasons", []))
            for npc in context["present_npcs"]
        }
        self.assertIn("mentioned_in_player_action", reasons["npc_a_sentry"])
        self.assertTrue(
            any(reason.startswith("active_clock:") for reason in reasons["npc_b_clerk"])
        )

    def test_read_only_cli_smoke_paths(self) -> None:
        commands = [
            ["tools/world_tick_manager.py", "list"],
            ["tools/memory_manager.py", "rerank", "campaign/npcs/npc_mira.memory_graph.json", "--turn", "1"],
            ["tools/zone_validator.py", "campaign/locations/old_dock.yaml", "--validate"],
            ["tools/chaos_manager.py", "show"],
            ["tools/progress_tracker.py", "list"],
            ["tools/conditions_manager.py", "list"],
            ["tools/resource_manager.py", "list"],
            ["tools/quest_viewer.py", "list"],
            ["tools/player_knowledge.py", "list"],
        ]
        for command in commands:
            with self.subTest(command=command):
                result = run_cmd(command)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_yaml_cli_tools_work_without_external_pyyaml(self) -> None:
        env = dict(os.environ)
        env["PYTHONNOUSERSITE"] = "1"
        commands = [
            ["tools/zone_validator.py", "campaign/locations/old_dock.yaml", "--validate"],
            [
                str(ROOT / "tools" / "run_turn.py"),
                "--player-action",
                "我观察旧码头",
                "--elapsed-minutes",
                "0",
            ],
        ]
        for command in commands:
            with self.subTest(command=command):
                result = run_cmd_with_env(command, env=env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_project_yaml_files_parse_without_external_pyyaml(self) -> None:
        script = """
import sys
from pathlib import Path

sys.path.insert(0, str(Path("tools").resolve()))
import yaml_compat

if yaml_compat._pyyaml is not None:
    raise SystemExit("expected fallback parser")

paths = sorted(list(Path("campaign").rglob("*.yaml")) + list(Path("xianxia_campaign").rglob("*.yaml")))
for path in paths:
    yaml_compat.safe_load(path.read_text(encoding="utf-8"))
print(f"parsed {len(paths)} yaml files")
"""
        env = dict(os.environ)
        env["PYTHONNOUSERSITE"] = "1"
        result = subprocess.run(
            [sys.executable, "-S", "-c", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_run_turn_commit_world_tick_on_temp_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(ROOT / "campaign", root / "campaign")
            state_path = root / "campaign" / "campaign_state.json"
            initial_state = json.loads(state_path.read_text(encoding="utf-8"))
            expected_time = time_utils.tick_to_display(
                time_utils.display_to_tick(initial_state["current_time"]) + 60
            )

            result = run_cmd(
                [
                    str(ROOT / "tools" / "run_turn.py"),
                    "--player-action",
                    "我等待一小时",
                    "--elapsed-minutes",
                    "60",
                    "--commit-world-tick",
                ],
                cwd=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["current_time"], expected_time)
            clocks = json.loads((root / "campaign" / "world_clocks.json").read_text(encoding="utf-8"))
            quests = json.loads((root / "campaign" / "quest_graph.json").read_text(encoding="utf-8"))
            by_clock = {clock["id"]: clock for clock in clocks["clocks"]}
            by_quest = {quest["id"]: quest for quest in quests["quests"]}
            self.assertEqual(
                by_quest["thread_black_lantern_deal"]["countdown_ticks"],
                by_clock["clock_black_lantern_deal"]["value"],
            )
            self.assertEqual(
                by_quest["thread_black_lantern_deal"]["clock_id"],
                "clock_black_lantern_deal",
            )


class DocumentationTests(unittest.TestCase):
    def test_architecture_mentions_current_test_count_and_root_semantics(self) -> None:
        text = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")

        self.assertIn("8 个自动化测试", text)
        self.assertIn("可传项目根、战局目录或 campaign 数据目录", text)


if __name__ == "__main__":
    unittest.main()
