import json, sys, tempfile, unittest, shutil
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))


def make_minimal_campaign(turn=1, time_str="\u7b2c 1 \u65e5 20:00"):
    return {
        "campaign_id": "test", "title": "test campaign",
        "current_turn": turn, "current_time": time_str,
        "current_scene": {"scene_id": "s1", "location_id": "loc_test_dock",
                          "summary": "test", "present_entities": ["pc_main", "npc_a"], "active_threads": []},
        "player_characters": [{"id": "pc_main", "name": "player", "location_id": "loc_test_dock", "inventory": [], "conditions": []}],
        "quests": [], "rules": {"system": "rules_lightweight_d20"},
    }

def make_empty_graph(npc_id, turn=1):
    return {"npc_id": npc_id, "current_turn": turn, "memory_policy_id": "npc_memory_policy_v1",
            "memory_nodes": [], "interpretation_nodes": [], "understanding_nodes": [],
            "revision_events": [], "relation_edges": [], "beliefs": [], "plans": []}

def make_patch(writes, time_delta="\u65e0"):
    return {"time_delta": time_delta, "location_changes": [], "inventory_changes": [],
            "relationship_changes": [], "new_facts": [], "contradictions": [],
            "npc_memory_writes": writes, "open_threads": []}

def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


class VisibilityIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        c = self.tmp / "campaign"
        for d in [c, c/"npcs", c/"locations", c/"lore", c/"session_logs"]:
            d.mkdir(parents=True, exist_ok=True)
        write_json(c/"campaign_state.json", make_minimal_campaign())
        write_json(c/"world_clocks.json", {"current_turn": 1, "clocks": []})
        (c/"world_graph.jsonl").write_text("", encoding="utf-8")
        write_json(c/"npcs/npc_a.memory_graph.json", make_empty_graph("npc_a"))
        write_json(c/"npcs/npc_b.memory_graph.json", make_empty_graph("npc_b"))
        (c/"locations/test_dock.yaml").write_text("id: loc_test_dock\n", encoding="utf-8")
        (c/"lore/rules.yaml").write_text("id: rules_test\n", encoding="utf-8")
        (c/"lore/factions.yaml").write_text("factions: []\n", encoding="utf-8")
        (c/"session_logs/0001.md").write_text("# test\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _graph(self, npc_id):
        return read_json(self.tmp / "campaign" / "npcs" / f"{npc_id}.memory_graph.json")

    # ----------------------------------------------------------------
    # Test 1: A sees player -> B NOT modified
    # ----------------------------------------------------------------
    def test_a_sees_B_not_modified(self):
        import apply_patch
        patch = make_patch([{
            "npc_id": "npc_a", "memory": "A saw player hiding.", "memory_type": "episodic",
            "source": "saw", "visibility_path": "direct_visual",
            "confidence": 0.9, "emotional_valence": -0.5, "salience": 0.7,
        }])
        b_before = self._graph("npc_b")
        apply_patch.apply_patch(self.tmp, patch, 1, "\u7b2c 1 \u65e5 20:00", "0001", dry_run=False)
        b_after = self._graph("npc_b")
        self.assertEqual(len(b_before["memory_nodes"]), len(b_after["memory_nodes"]),
                         "B's memory count changed! Knowledge leaked from A to B.")
        self.assertEqual(b_before, b_after, "B's memory graph was modified (knowledge leak).")
        a = self._graph("npc_a")
        self.assertEqual(len(a["memory_nodes"]), 1)

    # ----------------------------------------------------------------
    # Test 2: Separate NPC memories not mixed
    # ----------------------------------------------------------------
    def test_separate_memories_not_mixed(self):
        import apply_patch
        patch = make_patch([
            {"npc_id": "npc_a", "memory": "A saw the player.", "memory_type": "episodic",
             "source": "saw", "visibility_path": "direct_visual",
             "confidence": 0.9, "emotional_valence": -0.5, "salience": 0.7},
            {"npc_id": "npc_b", "memory": "B heard footsteps.", "memory_type": "episodic",
             "source": "heard", "visibility_path": "direct_auditory",
             "confidence": 0.5, "emotional_valence": 0, "salience": 0.3},
        ])
        apply_patch.apply_patch(self.tmp, patch, 1, "\u7b2c 1 \u65e5 20:00", "0001", dry_run=False)
        a = self._graph("npc_a"); b = self._graph("npc_b")
        self.assertEqual(len(a["memory_nodes"]), 1)
        self.assertEqual(len(b["memory_nodes"]), 1)
        self.assertIn("saw the player", a["memory_nodes"][0]["content"])
        self.assertNotIn("footsteps", a["memory_nodes"][0]["content"], "A has B's content!")
        self.assertIn("footsteps", b["memory_nodes"][0]["content"])
        self.assertNotIn("saw the player", b["memory_nodes"][0]["content"], "B has A's content!")

    # ----------------------------------------------------------------
    # Test 3: Visibility path attached
    # ----------------------------------------------------------------
    def test_visibility_path_attached(self):
        import apply_patch
        patch = make_patch([{
            "npc_id": "npc_a", "memory": "A saw player.", "memory_type": "episodic",
            "source": "saw", "visibility_path": "direct_visual",
            "confidence": 0.9, "emotional_valence": -0.5, "salience": 0.7,
        }])
        apply_patch.apply_patch(self.tmp, patch, 1, "\u7b2c 1 \u65e5 20:00", "0001", dry_run=False)
        m = self._graph("npc_a")["memory_nodes"][0]
        self.assertEqual(m["visibility_path"], "direct_visual")

    # ----------------------------------------------------------------
    # Test 4: Invalid visibility_path caught by validator
    # ----------------------------------------------------------------
    def test_invalid_path_rejected(self):
        import apply_patch
        patch = make_patch([{
            "npc_id": "npc_a", "memory": "test", "memory_type": "episodic",
            "source": "saw", "visibility_path": "INVALID_GHOST_PATH",
            "confidence": 0.9, "emotional_valence": 0, "salience": 0.5,
        }])
        errors = apply_patch.validate_patch_structure(patch)
        self.assertTrue(len(errors) > 0, "Should catch invalid visibility_path")
        self.assertTrue(any("visibility_path" in e.lower() for e in errors),
                        f"Error should mention visibility_path, got: {errors}")
        patch_none = make_patch([{
            "npc_id": "npc_a", "memory": "test", "memory_type": "episodic",
            "source": "saw", "visibility_path": "none",
            "confidence": 0.9, "emotional_valence": 0, "salience": 0.5,
        }])
        errors_none = apply_patch.validate_patch_structure(patch_none)
        self.assertTrue(any("visibility_path" in e.lower() for e in errors_none),
                        "Should reject visibility_path=none for actual memory writes")
        # Also check invalid source
        patch2 = make_patch([{
            "npc_id": "npc_a", "memory": "test", "memory_type": "episodic",
            "source": "telepathy", "visibility_path": "direct_visual",
            "confidence": 0.9, "emotional_valence": 0, "salience": 0.5,
        }])
        errors2 = apply_patch.validate_patch_structure(patch2)
        self.assertTrue(any("source" in e.lower() for e in errors2), "Should catch invalid source")

    # ----------------------------------------------------------------
    # Test 5: told_by creates separate memory
    # ----------------------------------------------------------------
    def test_told_by_separate_memory(self):
        import apply_patch
        # Round 1: A sees
        apply_patch.apply_patch(self.tmp, make_patch([{
            "npc_id": "npc_a", "memory": "A saw player with a dagger near crane.",
            "memory_type": "episodic", "source": "saw", "visibility_path": "direct_visual",
            "confidence": 0.9, "emotional_valence": -0.5, "salience": 0.7,
        }]), 1, "\u7b2c 1 \u65e5 20:00", "0001", dry_run=False)
        # Round 2: A tells B (B only knows what A said)
        apply_patch.apply_patch(self.tmp, make_patch([{
            "npc_id": "npc_b", "memory": "A said someone suspicious was near crane.",
            "memory_type": "episodic", "source": "heard", "visibility_path": "told_by",
            "confidence": 0.7, "emotional_valence": -0.3, "salience": 0.5,
        }]), 1, "\u7b2c 1 \u65e5 20:15", "0001", dry_run=False)
        a = self._graph("npc_a"); b = self._graph("npc_b")
        self.assertEqual(len(a["memory_nodes"]), 1)
        self.assertIn("dagger", a["memory_nodes"][0]["content"])
        self.assertEqual(a["memory_nodes"][0]["visibility_path"], "direct_visual")
        self.assertEqual(len(b["memory_nodes"]), 1)
        self.assertEqual(b["memory_nodes"][0]["source"], "heard")
        self.assertEqual(b["memory_nodes"][0]["visibility_path"], "told_by")
        self.assertNotIn("dagger", b["memory_nodes"][0]["content"],
                         "B knows about dagger even though A didn't mention it!")


class MemoryGraphIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        c = self.tmp / "campaign"
        for d in [c, c/"npcs", c/"locations", c/"lore", c/"session_logs"]:
            d.mkdir(parents=True, exist_ok=True)
        write_json(c/"campaign_state.json", make_minimal_campaign())
        write_json(c/"world_clocks.json", {"current_turn": 1, "clocks": []})
        (c/"world_graph.jsonl").write_text("", encoding="utf-8")
        write_json(c/"npcs/npc_c.memory_graph.json", make_empty_graph("npc_c"))
        (c/"locations/test_dock.yaml").write_text("id: loc_test_dock\n", encoding="utf-8")
        (c/"lore/rules.yaml").write_text("id: rules_test\n", encoding="utf-8")
        (c/"lore/factions.yaml").write_text("factions: []\n", encoding="utf-8")
        (c/"session_logs/0001.md").write_text("# test\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _graph(self, npc_id):
        return read_json(self.tmp / "campaign" / "npcs" / f"{npc_id}.memory_graph.json")

    # ----------------------------------------------------------------
    # Test 6: Memory IDs unique and sequential
    # ----------------------------------------------------------------
    def test_memory_ids_sequential(self):
        import apply_patch
        writes = []
        for i in range(3):
            writes.append({
                "npc_id": "npc_c", "memory": f"event {i+1}",
                "memory_type": "episodic", "source": "saw",
                "visibility_path": "direct_visual",
                "confidence": 0.8, "emotional_valence": 0, "salience": 0.5,
            })
        apply_patch.apply_patch(self.tmp, make_patch(writes), 1, "\u7b2c 1 \u65e5 20:00", "0001", dry_run=False)
        g = self._graph("npc_c")
        ids = [m["id"] for m in g["memory_nodes"]]
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(set(ids)), 3, "Memory IDs not unique!")
        self.assertEqual(ids, ["mem_npc_c_0001", "mem_npc_c_0002", "mem_npc_c_0003"])

    # ----------------------------------------------------------------
    # Test 7: Write to nonexistent NPC creates graph
    # ----------------------------------------------------------------
    def test_new_npc_creates_graph(self):
        import apply_patch
        apply_patch.apply_patch(self.tmp, make_patch([{
            "npc_id": "npc_new", "memory": "First memory.", "memory_type": "episodic",
            "source": "saw", "visibility_path": "direct_visual",
            "confidence": 0.8, "emotional_valence": 0, "salience": 0.5,
        }]), 1, "\u7b2c 1 \u65e5 20:00", "0001", dry_run=False)
        gp = self.tmp / "campaign" / "npcs" / "npc_new.memory_graph.json"
        self.assertTrue(gp.exists(), "Memory graph not created for new NPC")
        g = read_json(gp)
        self.assertEqual(g["npc_id"], "npc_new")
        self.assertEqual(len(g["memory_nodes"]), 1)

    # ----------------------------------------------------------------
    # Test 8: Interpretation, understanding, and revision writes persist
    # ----------------------------------------------------------------
    def test_cognitive_layer_writes(self):
        import apply_patch
        patch = make_patch([{
            "npc_id": "npc_c", "memory": "C saw player spare a rival.",
            "memory_type": "episodic", "source": "saw",
            "visibility_path": "direct_visual",
            "confidence": 0.8, "emotional_valence": 0.4, "salience": 0.7,
        }])
        patch["npc_interpretation_writes"] = [{
            "id": "interp_c_0001",
            "npc_id": "npc_c",
            "derived_from_event_id": "event_player_spared_rival",
            "derived_from_memory_id": "mem_npc_c_0001",
            "text": "The player may prefer mercy when it costs little.",
            "appraisal": {
                "goal_impact": "neutral",
                "threat_level": 0.2,
                "opportunity_level": 0.4,
                "agency": "player",
                "moral_judgment": "good",
                "relationship_signal": "trust",
            },
            "emotion": {"label": "curiosity", "valence": 0.4, "intensity": 0.5},
            "confidence": 0.7,
            "importance": 0.6,
            "related_entities": ["pc_main", "npc_c"],
            "possible_misunderstanding": True,
        }]
        patch["npc_understanding_writes"] = [{
            "id": "under_c_0001",
            "npc_id": "npc_c",
            "type": "relationship_judgment",
            "text": "The player is not automatically cruel.",
            "supporting_interpretation_ids": ["interp_c_0001"],
            "supporting_memory_ids": ["mem_npc_c_0001"],
            "contradicting_interpretation_ids": [],
            "confidence": 0.65,
            "stability": 0.35,
            "importance": 0.55,
            "tier": "active",
            "revision_status": "active",
            "version": 1,
            "last_updated_turn": 1,
            "superseded_by": None,
            "behavior_effect": "C may test the player before assuming hostility.",
        }]
        patch["npc_revision_writes"] = [{
            "id": "rev_c_0001",
            "npc_id": "npc_c",
            "turn": 1,
            "new_event_id": "event_player_spared_rival",
            "target_understanding_id": "under_c_0001",
            "effect": "supports",
            "evidence_strength": 0.4,
            "confidence_delta": 0.05,
            "stability_delta": 0.02,
            "new_status": "active",
            "reason": "The event supports a cautious but less hostile reading.",
            "source_interpretation_ids": ["interp_c_0001"],
        }]

        errors = apply_patch.validate_patch_structure(patch)
        self.assertEqual(errors, [])
        apply_patch.apply_patch(self.tmp, patch, 1, "\u7b2c 1 \u65e5 20:00", "0001", dry_run=False)

        graph = self._graph("npc_c")
        self.assertEqual(graph["interpretation_nodes"][0]["id"], "interp_c_0001")
        self.assertEqual(graph["understanding_nodes"][0]["id"], "under_c_0001")
        self.assertEqual(graph["revision_events"][0]["id"], "rev_c_0001")


if __name__ == "__main__":
    unittest.main(verbosity=2)
