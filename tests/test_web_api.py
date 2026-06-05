from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import web_api  # noqa: E402
import web_game  # noqa: E402
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

    def test_app_bootstrap_returns_frontend_contract_without_hidden_payloads(self) -> None:
        bootstrap = web_api.app_bootstrap(ROOT)

        self.assertEqual(bootstrap["contract_version"], 1)
        self.assertIn("config", bootstrap)
        self.assertIn("campaigns", bootstrap)
        self.assertIn("current_campaign", bootstrap)
        self.assertIn("state", bootstrap)
        self.assertIn("logs", bootstrap)
        self.assertIn("api", bootstrap)
        self.assertEqual(bootstrap["current_campaign"], web_api.campaign_key(ROOT))
        self.assertEqual(bootstrap["state"]["campaign"]["root"], web_api.campaign_key(ROOT))
        self.assertIsInstance(bootstrap["campaigns"], list)
        self.assertIsInstance(bootstrap["logs"], list)

        encoded = json.dumps(bootstrap, ensure_ascii=False)
        for forbidden in ["memory_nodes", "state_patch", "tool_results", "artifact_path", "gm_notes", "hidden_state"]:
            self.assertNotIn(forbidden, encoded)

    def test_web_game_routes_app_bootstrap(self) -> None:
        state = web_game.GameServer()
        handler_cls = web_game.make_handler(state)
        handler = object.__new__(handler_cls)
        handler.path = "/api/app/bootstrap"
        handler.command = "GET"
        handler.request_version = "HTTP/1.1"
        handler.wfile = Mock()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()

        handler.route_get()

        handler.send_response.assert_called_once_with(200)
        body = b"".join(call.args[0] for call in handler.wfile.write.call_args_list)
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["contract_version"], 1)
        self.assertIn("state", payload)
        self.assertIn("logs", payload)

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

    def test_visible_state_hides_disabled_world_mechanics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            campaign = root / "campaign"
            (campaign / "locations").mkdir(parents=True)
            (campaign / "npcs").mkdir(parents=True)
            state = {
                "campaign_id": "ordinary",
                "current_turn": 1,
                "current_time": "\u7b2c 1 \u65e5 08:00",
                "current_scene": {"location_id": "town", "present_entities": ["pc_main"]},
                "player_characters": [
                    {
                        "id": "pc_main",
                        "name": "\u666e\u901a\u4eba",
                        "location_id": "town",
                        "health": 10,
                        "max_health": 10,
                        "effect_points": 99,
                        "system_rank": 7,
                        "special_effects": ["legacy leak"],
                    }
                ],
                "rules": {"system": "rules_lightweight_d20", "capabilities": {"system": False}},
            }
            (campaign / "campaign_state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            (campaign / "player_knowledge.json").write_text("{}", encoding="utf-8")
            (campaign / "quest_graph.json").write_text('{"quests":[]}', encoding="utf-8")
            (campaign / "world_clocks.json").write_text('{"clocks":[]}', encoding="utf-8")
            (campaign / "resources.json").write_text('{"entities":{}}', encoding="utf-8")
            (campaign / "progress_tracks.json").write_text('{"tracks":[]}', encoding="utf-8")
            (campaign / "conditions.json").write_text('{"entities":{}}', encoding="utf-8")

            visible = web_api.visible_state(root)

            self.assertNotIn("effect_points", visible["player"])
            self.assertNotIn("system_rank", visible["player"])
            self.assertNotIn("special_effects", visible["player"])
            self.assertEqual(visible["mechanics"]["system"], False)
            sheet_fields = {
                item["field"]
                for section in visible["character_sheet"]["sections"]
                for item in section["items"]
            }
            self.assertNotIn("effect_points", sheet_fields)
            self.assertNotIn("system_rank", sheet_fields)

    def test_visible_state_uses_world_character_sheet_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            campaign = root / "campaign"
            (campaign / "locations").mkdir(parents=True)
            (campaign / "npcs").mkdir(parents=True)
            state = {
                "campaign_id": "sequence_world",
                "current_turn": 1,
                "current_time": "\u7b2c 1 \u65e5 08:00",
                "current_scene": {"location_id": "fog_city", "present_entities": ["pc_main"]},
                "player_characters": [
                    {
                        "id": "pc_main",
                        "name": "\u5360\u535c\u5bb6",
                        "location_id": "fog_city",
                        "health": 9,
                        "max_health": 10,
                        "sequence": 9,
                        "potion_stage": "\u5360\u535c\u5bb6\u9b54\u836f\u5df2\u6d88\u5316 20%",
                    }
                ],
                "rules": {
                    "system": "rules_lightweight_d20",
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
                },
            }
            (campaign / "campaign_state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            (campaign / "player_knowledge.json").write_text("{}", encoding="utf-8")
            (campaign / "quest_graph.json").write_text('{"quests":[]}', encoding="utf-8")
            (campaign / "world_clocks.json").write_text('{"clocks":[]}', encoding="utf-8")
            (campaign / "resources.json").write_text('{"entities":{}}', encoding="utf-8")
            (campaign / "progress_tracks.json").write_text('{"tracks":[]}', encoding="utf-8")
            (campaign / "conditions.json").write_text('{"entities":{}}', encoding="utf-8")

            visible = web_api.visible_state(root)

            section = visible["character_sheet"]["sections"][0]
            self.assertEqual(section["id"], "mystery_path")
            self.assertEqual(
                {item["field"]: item["value"] for item in section["items"]},
                {"sequence": 9, "potion_stage": "\u5360\u535c\u5bb6\u9b54\u836f\u5df2\u6d88\u5316 20%"},
            )

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
            self.assertEqual(result["turn_meta"]["inferred_action"]["action_type"], "观察")
            self.assertEqual(result["turn_meta"]["elapsed_minutes"], 5)
            self.assertIn("apply_report", result)
            self.assertTrue((target / "campaign" / "ai_runs").exists())

    def test_turn_infers_wait_duration_from_natural_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")

            with StubChatApi(api_turn_response()):
                result = web_api.run_turn(target, "我在码头边等半小时，看看谁出现")

            self.assertEqual(result["turn_meta"]["inferred_action"]["action_type"], "等待")
            self.assertEqual(result["turn_meta"]["elapsed_minutes"], 30)
            self.assertEqual(result["turn_meta"]["time_delta"], "30 分钟")

    def test_turn_strips_legacy_action_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")

            with StubChatApi(api_turn_response()):
                result = web_api.run_turn(target, "[交谈] 我问米拉黑灯会什么时候来")

            self.assertEqual(result["turn_meta"]["inferred_action"]["normalized_action"], "我问米拉黑灯会什么时候来")
            self.assertEqual(result["turn_meta"]["inferred_action"]["action_type"], "交谈")

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
            {
                "campaign_before": {
                    "rules": {"capabilities": {"system": True, "effect_points": True}},
                    "player_characters": [{"id": "player_lin", "effect_points": 0}],
                }
            },
        )

        deltas = [item.get("delta", item.get("value")) for item in patch["player_state_changes"] if item["field"] == "effect_points"]
        self.assertEqual(deltas, [-50.0, 10])

    def test_effect_point_reward_ignored_when_mechanic_disabled(self) -> None:
        patch = web_api.play_game.normalize_patch(
            {},
            {"visible_text": {"state_summary": {"quests": "\u83b7\u5f9710\u70b9\u7279\u6548\u503c\u3002"}}},
            {
                "campaign_before": {
                    "rules": {"capabilities": {"system": False}},
                    "player_characters": [{"id": "pc_main"}],
                }
            },
        )

        self.assertEqual(
            [item for item in patch["player_state_changes"] if item["field"] == "effect_points"],
            [],
        )

    def test_worldgen_write_does_not_inject_disabled_mechanics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            world = web_api.play_game.fallback_worldgen("\u666e\u901a\u5c0f\u9547\u60ac\u7591")
            web_api.play_game.write_worldgen_files(target, world, force=True)

            state = json.loads((target / "campaign" / "campaign_state.json").read_text(encoding="utf-8"))
            player = state["player_characters"][0]

            self.assertNotIn("qi", player)
            self.assertNotIn("realm", player)
            self.assertNotIn("realm_level", player)
            self.assertNotIn("spiritual_root", player)
            self.assertNotIn("effect_points", player)
            self.assertNotIn("system_rank", player)

    def test_worldgen_write_preserves_manifest_fields_without_code_support(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            world = web_api.play_game.fallback_worldgen("\u5e8f\u5217\u9b54\u836f\u60ac\u7591")
            state_file = next(item for item in world["files"] if item["path"] == "campaign/campaign_state.json")
            state = state_file["content"]
            state["rules"]["capabilities"] = {"system": False, "cultivation": False}
            state["rules"]["character_sheet"] = {
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
            }
            state["player_characters"][0]["sequence"] = 9
            state["player_characters"][0]["potion_stage"] = "\u672a\u6d88\u5316"

            web_api.play_game.write_worldgen_files(target, world, force=True)
            visible = web_api.visible_state(target)
            section = visible["character_sheet"]["sections"][0]

            self.assertEqual(section["id"], "mystery_path")
            self.assertEqual(
                {item["field"]: item["value"] for item in section["items"]},
                {"sequence": 9, "potion_stage": "\u672a\u6d88\u5316"},
            )

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

    def test_visible_state_sanitizes_player_knowledge_threads_resources_and_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")

            state_path = target / "campaign" / "campaign_state.json"
            state_data = json.loads(state_path.read_text(encoding="utf-8"))
            state_data["open_threads"] = [
                {
                    "id": "thread_public",
                    "description": "Public unresolved situation",
                    "next_pressure": "GM-only pressure escalation",
                    "visibility": "public",
                    "status": "active",
                },
                {
                    "id": "thread_secret",
                    "description": "Hidden ambush",
                    "visibility": "secret",
                    "status": "active",
                },
            ]
            state_path.write_text(json.dumps(state_data, ensure_ascii=False, indent=2), encoding="utf-8")
            (target / "campaign" / "player_knowledge.json").write_text(
                json.dumps(
                    {
                        "facts_understood": [
                            {"fact": "Public clue", "visibility": "public"},
                            {"fact": "GM-only clue", "visibility": "gm_only"},
                        ],
                        "private_notes": "do not show",
                        "nested": {"hidden_state": "secret engine detail", "public_note": "safe"},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (target / "campaign" / "resources.json").write_text(
                json.dumps(
                    {
                        "entities": {
                            "pc_main": {"money": 10},
                            "faction_secret": {"money": 999, "visibility": "secret"},
                            "npc_private": {"money": 5, "visibility": "private", "gm_notes": "hidden"},
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (target / "campaign" / "progress_tracks.json").write_text(
                json.dumps(
                    {
                        "tracks": [
                            {"id": "track_public", "title": "Public", "value": 1, "max_value": 3},
                            {"id": "track_secret", "title": "Secret", "visibility": "private", "value": 2},
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            visible = web_api.visible_state(target)
            encoded = json.dumps(visible, ensure_ascii=False)

            self.assertIn("Public clue", encoded)
            self.assertIn("Public unresolved situation", encoded)
            self.assertIn("track_public", encoded)
            self.assertIn("pc_main", encoded)
            for forbidden in [
                "GM-only clue",
                "private_notes",
                "hidden_state",
                "GM-only pressure escalation",
                "Hidden ambush",
                "faction_secret",
                "npc_private",
                "gm_notes",
                "track_secret",
            ]:
                self.assertNotIn(forbidden, encoded)

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
            self.assertIn("state", result)
            self.assertNotIn("state_patch", result)
            self.assertNotIn("tool_results", result)
            self.assertNotIn("artifact_path", result)
            self.assertNotIn("active_lore", result)

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
