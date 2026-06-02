from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import web_api  # noqa: E402
import obsidian_vault  # noqa: E402


def api_turn_response() -> str:
    return json.dumps(
        {
            "tool_requests": [],
            "visible_text": {
                "scene": "你观察当前局势，离屏压力仍在推进。",
                "action_result": "你保留了主动权。",
                "actionable_clues": ["继续观察", "主动交谈"],
                "check": "无",
            },
            "state_patch": {
                "time_delta": "无",
                "location_changes": [],
                "inventory_changes": [],
                "relationship_changes": [],
                "new_facts": [],
                "contradictions": [],
                "npc_memory_writes": [],
                "open_threads": [],
            },
        },
        ensure_ascii=False,
    )


def api_worldgen_response() -> str:
    world = web_api.play_game.fallback_worldgen("赛博修仙废城，玩家是拥有词条系统的魂穿者")
    return json.dumps(world, ensure_ascii=False)


class StubChatApi:
    def __init__(self, response: str) -> None:
        self.response = response
        self.original = web_api.play_game.call_chat_api

    def __enter__(self) -> None:
        web_api.play_game.call_chat_api = lambda _config, _messages: self.response  # type: ignore[assignment]

    def __exit__(self, *args: object) -> None:
        web_api.play_game.call_chat_api = self.original  # type: ignore[assignment]


class WebApiTests(unittest.TestCase):
    def test_api_status_reports_unconfigured_api_instead_of_mock_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")

            status = web_api.api_status(target)

            if not status["has_key"]:
                self.assertEqual(status["mode"], "api_unconfigured")

    def test_public_web_api_rejects_mock_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")

            with self.assertRaisesRegex(ValueError, "mock mode has been removed"):
                web_api.run_turn(target, "我观察周围", mock=True)
            with self.assertRaisesRegex(ValueError, "mock mode has been removed"):
                web_api.create_campaign("边境小城", mock=True, force=True)

    def test_visible_state_hides_private_memory_but_shows_play_panels(self) -> None:
        state = web_api.visible_state(ROOT)

        self.assertIn("campaign", state)
        self.assertIn("player", state)
        self.assertIn("npcs", state)
        self.assertIn("quests", state)
        self.assertIn("knowledge", state)
        self.assertNotIn("memory_nodes", state)

    def test_visible_state_exposes_player_location_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            campaign = root / "campaign"
            (campaign / "locations").mkdir(parents=True)
            (campaign / "npcs").mkdir(parents=True)
            state = {
                "campaign_id": "test",
                "current_turn": 1,
                "current_time": "\u7b2c 1 \u65e5 08:00",
                "current_scene": {"location_id": "qingyun_valley", "present_entities": ["pc_main"]},
                "player_characters": [{"id": "pc_main", "name": "\u6797\u5915", "location_id": "qingyun_valley"}],
            }
            (campaign / "campaign_state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            (campaign / "player_knowledge.json").write_text("{}", encoding="utf-8")
            (campaign / "quest_graph.json").write_text('{"quests":[]}', encoding="utf-8")
            (campaign / "world_clocks.json").write_text('{"clocks":[]}', encoding="utf-8")
            (campaign / "resources.json").write_text('{"entities":[]}', encoding="utf-8")
            (campaign / "progress_tracks.json").write_text('{"tracks":[]}', encoding="utf-8")
            (campaign / "conditions.json").write_text('{"entities":{}}', encoding="utf-8")

            visible = web_api.visible_state(root)

            self.assertEqual(visible["player"]["location_id"], "qingyun_valley")

    def test_api_worldgen_creates_playable_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            config = web_api.make_config(ROOT)
            config.api_key = "test-key"
            with StubChatApi(api_worldgen_response()):
                world = web_api.play_game.run_worldgen(config, "赛博修仙废城，玩家是拥有词条系统的魂穿者", target, force=True)

            self.assertTrue((target / "campaign" / "campaign_state.json").exists())
            self.assertTrue(world.get("files"))
            state = web_api.visible_state(target)
            self.assertIn("scene", state)
            self.assertTrue(state["quests"])

    def test_api_turn_returns_visible_text_and_apply_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")

            with StubChatApi(api_turn_response()):
                result = web_api.run_turn(target, "我观察周围的异常痕迹")

            self.assertIn("visible_text", result)
            self.assertEqual(result["inferred_action"]["action_type"], "观察")
            self.assertEqual(result["inferred_action"]["elapsed_minutes"], 5)
            self.assertIn("state_patch", result)
            self.assertIn("apply_report", result)
            self.assertTrue((target / "campaign" / "ai_runs").exists())

    def test_turn_infers_wait_duration_from_natural_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")

            with StubChatApi(api_turn_response()):
                result = web_api.run_turn(target, "我在码头边等半小时，看看谁出现")

            self.assertEqual(result["inferred_action"]["action_type"], "等待")
            self.assertEqual(result["inferred_action"]["elapsed_minutes"], 30)
            self.assertEqual(result["state_patch"]["time_delta"], "30 分钟")

    def test_turn_strips_legacy_action_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")

            with StubChatApi(api_turn_response()):
                result = web_api.run_turn(target, "[交谈] 我问米拉黑灯会什么时候来")

            self.assertEqual(result["inferred_action"]["normalized_action"], "我问米拉黑灯会什么时候来")
            self.assertEqual(result["inferred_action"]["action_type"], "交谈")

    def test_status_lookup_does_not_advance_time(self) -> None:
        inferred = web_api.play_game.infer_player_action("查看角色卡和任务面板")

        self.assertEqual(inferred["action_type"], "查看状态")
        self.assertEqual(inferred["elapsed_minutes"], 0)

    def test_negated_social_observation_is_not_conversation(self) -> None:
        inferred = web_api.play_game.infer_player_action("我不主动和任何人交谈，只观察街面和身上物品")

        self.assertEqual(inferred["action_type"], "观察")

    def test_notice_board_lookup_is_investigation(self) -> None:
        inferred = web_api.play_game.infer_player_action("我走到坊市告示栏前，快速查看最新悬赏")

        self.assertEqual(inferred["action_type"], "调查")

    def test_social_action_with_observation_clause_is_conversation(self) -> None:
        inferred = web_api.play_game.infer_player_action("我对老陈说我略懂阵法，同时留意他是否隐瞒风险。")

        self.assertEqual(inferred["action_type"], "交谈")

    def test_effect_point_reward_text_adds_state_delta(self) -> None:
        patch = web_api.play_game.normalize_patch(
            {
                "player_state_changes": [
                    {
                        "entity_id": "player_lin",
                        "field": "effect_points",
                        "operation": "delta",
                        "value": -50,
                    }
                ]
            },
            {"visible_text": {"state_summary": {"quests": "获得至少10点特效值。"}}},
            {"campaign_before": {"player_characters": [{"id": "player_lin"}]}},
        )

        deltas = [item.get("delta", item.get("value")) for item in patch["player_state_changes"] if item["field"] == "effect_points"]
        self.assertEqual(deltas, [-50.0, 10])

    def test_render_visible_accepts_structured_check_and_clues(self) -> None:
        rendered = web_api.play_game.render_visible(
            {
                "visible_text": {
                    "scene": "古阵核心",
                    "actionable_clues": [{"text": "检查第四处阵纹"}],
                    "check": {"type": "阵法", "difficulty": "medium"},
                    "state_summary": {"unresolved": [{"text": "潜伏者是谁"}]},
                }
            }
        )

        self.assertIn("古阵核心", rendered)
        self.assertIn("检查第四处阵纹", rendered)
        self.assertIn("阵法", rendered)
        self.assertIn("潜伏者是谁", rendered)

    def test_open_thread_summary_survives_normalization(self) -> None:
        patch = web_api.play_game.normalize_patch(
            {
                "open_threads": [
                    {
                        "id": "open_thread_0010",
                        "summary": "阵法师招募令：铁匠铺巷尾老陈，纸张有烧焦痕迹。",
                        "status": "active",
                    }
                ]
            },
            {
                "visible_text": {
                    "state_summary": {
                        "unresolved": ["阵法师招募令是谁发布的？"]
                    }
                }
            },
        )

        self.assertIn("阵法师招募令", patch["open_threads"][0]["thread"])

    def test_open_thread_normalization_caps_new_threads(self) -> None:
        patch = web_api.play_game.normalize_patch(
            {
                "open_threads": [
                    {"thread": f"thread {index}", "next_pressure": "pressure"}
                    for index in range(10)
                ]
            }
        )

        self.assertEqual(len(patch["open_threads"]), web_api.play_game.MAX_NEW_OPEN_THREADS)

    def test_world_clock_current_max_fields_render(self) -> None:
        clocks = web_api.normalize_clocks({
            "clocks": [
                {"id": "clock_01", "title": "妖兽异动", "current": 1, "max": 6, "visible": True},
            ]
        })

        self.assertEqual(clocks[0]["value"], 1)
        self.assertEqual(clocks[0]["max_value"], 6)
        self.assertEqual(clocks[0]["visibility"], "public")

    def test_visible_state_hides_private_and_secret_world_clocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")
            (target / "campaign" / "world_clocks.json").write_text(
                json.dumps(
                    {
                    "clocks": [
                        {"id": "public_clock", "title": "public", "value": 1, "max_value": 4, "visibility": "public"},
                        {"id": "private_clock", "title": "private", "value": 1, "max_value": 4, "visibility": "private"},
                        {"id": "secret_clock", "title": "secret", "value": 1, "max_value": 4, "visibility": "secret"},
                    ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            state = web_api.visible_state(target)

            self.assertEqual([clock["id"] for clock in state["clocks"]], ["public_clock"])

    def test_visible_state_hides_secret_quests_and_gm_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")
            state_path = target / "campaign" / "campaign_state.json"
            state_data = json.loads(state_path.read_text(encoding="utf-8"))
            state_data["quests"] = [
                {"id": "visible_q", "title": "Visible", "status": "active", "known_to_players": True},
                {
                    "id": "secret_q",
                    "title": "GM SECRET: traitor",
                    "status": "active",
                    "known_to_players": False,
                    "gm_notes": "Do not reveal",
                },
            ]
            state_path.write_text(json.dumps(state_data, ensure_ascii=False, indent=2), encoding="utf-8")
            graph_path = target / "campaign" / "quest_graph.json"
            graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
            graph_data["quests"].append({
                "id": "secret_graph_q",
                "title": "GM SECRET GRAPH",
                "status": "active",
                "visibility": "secret",
                "gm_notes": "hidden plot",
            })
            graph_path.write_text(json.dumps(graph_data, ensure_ascii=False, indent=2), encoding="utf-8")

            visible = web_api.visible_state(target)
            encoded = json.dumps(visible, ensure_ascii=False)

            self.assertEqual([quest["id"] for quest in visible["quests"]], ["visible_q"])
            self.assertNotIn("secret_q", encoded)
            self.assertNotIn("secret_graph_q", encoded)
            self.assertNotIn("GM SECRET", encoded)
            self.assertNotIn("gm_notes", encoded)

    def test_validate_reports_failure_for_invalid_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "bad_root"
            (target / "campaign").mkdir(parents=True)

            result = web_api.validate(target)

            self.assertFalse(result["ok"])
            self.assertNotEqual(result["returncode"], 0)

    def test_obsidian_export_creates_markdown_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "vaults"

            result = obsidian_vault.export_campaign(ROOT, out)
            vault = Path(result["vault"])

            self.assertTrue((vault / "Home.md").exists())
            self.assertTrue((vault / "NPC Index.md").exists())
            self.assertTrue((vault / "Quest Index.md").exists())
            home = (vault / "Home.md").read_text(encoding="utf-8")
            self.assertIn("[[Campaign State]]", home)
            self.assertGreaterEqual(result["notes"], 6)

    def test_roll_dice_returns_total(self) -> None:
        result = web_api.roll_dice("2d6+3")

        self.assertEqual(result["expression"], "2d6+3")
        self.assertEqual(len(result["rolls"]), 2)
        self.assertEqual(result["total"], sum(result["rolls"]) + 3)

    def test_turn_returns_even_when_patch_apply_has_no_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")

            with StubChatApi(api_turn_response()):
                result = web_api.run_turn(target, "我观察当前局势")

            self.assertIn("visible_text", result)
            self.assertIn("apply_report", result)

    def test_recent_logs_expose_applied_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")

            with StubChatApi(api_turn_response()):
                web_api.run_turn(target, "我观察当前局势")
            logs = web_api.recent_logs(target)

            self.assertTrue(logs)
            self.assertTrue(logs[0]["applied"])

    def test_turn_packet_includes_active_lore(self) -> None:
        import run_turn

        campaign = run_turn.load_json(ROOT / "campaign" / "campaign_state.json")
        context = run_turn.collect_context(ROOT, campaign, 8, "询问黑灯会旧码头交易")

        self.assertIn("active_lore", context)
        self.assertIn("recent_turn_history", context)


if __name__ == "__main__":
    unittest.main()
