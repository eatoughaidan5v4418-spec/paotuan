from __future__ import annotations

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


class WebApiTests(unittest.TestCase):
    def test_visible_state_hides_private_memory_but_shows_play_panels(self) -> None:
        state = web_api.visible_state(ROOT)

        self.assertIn("campaign", state)
        self.assertIn("player", state)
        self.assertIn("npcs", state)
        self.assertIn("quests", state)
        self.assertIn("knowledge", state)
        self.assertNotIn("memory_nodes", state)

    def test_mock_worldgen_creates_playable_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            config = web_api.make_config(ROOT, mock=True)
            world = web_api.play_game.run_worldgen(config, "赛博修仙废城，玩家是拥有词条系统的魂穿者", target, force=True)

            self.assertTrue((target / "campaign" / "campaign_state.json").exists())
            self.assertTrue(world.get("files"))
            state = web_api.visible_state(target)
            self.assertIn("scene", state)
            self.assertTrue(state["quests"])

    def test_mock_turn_returns_visible_text_and_apply_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")

            result = web_api.run_turn(target, "我观察周围的异常痕迹", mock=True)

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

            result = web_api.run_turn(target, "我在码头边等半小时，看看谁出现", mock=True)

            self.assertEqual(result["inferred_action"]["action_type"], "等待")
            self.assertEqual(result["inferred_action"]["elapsed_minutes"], 30)
            self.assertEqual(result["state_patch"]["time_delta"], "30 分钟")

    def test_turn_strips_legacy_action_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "campaign_root"
            shutil.copytree(ROOT / "campaign", target / "campaign")

            result = web_api.run_turn(target, "[交谈] 我问米拉黑灯会什么时候来", mock=True)

            self.assertEqual(result["inferred_action"]["normalized_action"], "我问米拉黑灯会什么时候来")
            self.assertEqual(result["inferred_action"]["action_type"], "交谈")

    def test_status_lookup_does_not_advance_time(self) -> None:
        inferred = web_api.play_game.infer_player_action("查看角色卡和任务面板")

        self.assertEqual(inferred["action_type"], "查看状态")
        self.assertEqual(inferred["elapsed_minutes"], 0)

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

            result = web_api.run_turn(target, "我观察当前局势", mock=True)

            self.assertIn("visible_text", result)
            self.assertIn("apply_report", result)

    def test_turn_packet_includes_active_lore(self) -> None:
        import run_turn

        campaign = run_turn.load_json(ROOT / "campaign" / "campaign_state.json")
        context = run_turn.collect_context(ROOT, campaign, 8, "询问黑灯会旧码头交易")

        self.assertIn("active_lore", context)
        self.assertIn("recent_turn_history", context)


if __name__ == "__main__":
    unittest.main()
