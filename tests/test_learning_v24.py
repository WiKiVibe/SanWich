# -*- coding: utf-8 -*-
"""v2.4 學習閉環、規則 schema v2、模板詞庫單元測試。"""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


LEARNING = load_module("sanwich_learning_test", ROOT / "core" / "learning.py")
RULES = load_module("sanwich_rules_v24_test", ROOT / "core" / "personal_rules.py")
TEMPLATES = load_module("sanwich_templates_test", ROOT / "core" / "prompt_templates.py")
EXPERIMENTS = load_module("sanwich_exp_test", ROOT / "core" / "experiments.py")


class LearningFeedbackTests(unittest.TestCase):
    def test_feedback_events_four_actions_and_no_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review_feedback.jsonl"
            store = LEARNING.FeedbackStore(path)
            for action in (
                LEARNING.ACTION_ACCEPT_AI,
                LEARNING.ACTION_RESTORE_ORIGINAL,
                LEARNING.ACTION_MANUAL_EDIT,
                LEARNING.ACTION_SKIP,
            ):
                store.record(
                    action=action,
                    original_text="萬歌來了",
                    ai_text="萬哥來了",
                    final_text="萬哥來了" if action != LEARNING.ACTION_RESTORE_ORIGINAL else "萬歌來了",
                    input_path=r"D:\secret\episode01.mp4",
                    app_version="2.4.6",
                    source="quick_compare",
                )
            rows = store.iter_events()
            self.assertEqual(len(rows), 4)
            self.assertEqual({r["action"] for r in rows}, set(LEARNING.VALID_ACTIONS))
            # 不含完整路徑與 API key
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn(r"D:\secret", raw)
            self.assertIn("episode01.mp4", raw)
            self.assertNotIn("api_key", raw.lower())

    def test_candidate_needs_repeated_human_confirm(self):
        events = []
        for i in range(2):
            events.append({
                "event_id": f"e{i}",
                "action": LEARNING.ACTION_MANUAL_EDIT,
                "original_text": "萬歌說",
                "ai_text": "萬歌說",
                "final_text": "萬哥說",
                "domain": "訪談",
                "series_id": "show1",
                "input_name": f"ep{i}.srt",
            })
        # 單次不應達門檻；重複確認才建議（使用規則抽取）
        one = LEARNING.aggregate_candidates_from_events(
            events[:1], threshold=2, extract_fn=RULES.extract_candidates,
        )
        self.assertEqual(one, [])
        two = LEARNING.aggregate_candidates_from_events(
            events, threshold=2, extract_fn=RULES.extract_candidates,
        )
        self.assertGreaterEqual(len(two), 1)
        self.assertGreaterEqual(two[0]["positive"], 2)
        self.assertNotEqual(two[0]["before"], two[0]["after"])
        # 應包含 萬歌→萬哥 或抽取後的短替換
        pair_ok = any(
            (c["before"] in ("萬歌", "歌") and c["after"] in ("萬哥", "哥"))
            for c in two
        )
        self.assertTrue(pair_ok, msg=str(two))

    def test_edit_history_migrate_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "logs" / "srt_edit_history.jsonl"
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"before_text":"a","after_text":"b"}\n', encoding="utf-8")
            dest = Path(tmp) / "learning" / "srt_edit_history.jsonl"
            r1 = LEARNING.migrate_edit_history_once(legacy, dest)
            self.assertTrue(r1["migrated"])
            r2 = LEARNING.migrate_edit_history_once(legacy, dest)
            self.assertTrue(r2["skipped"])
            self.assertTrue(dest.exists())


class RuleSchemaV2Tests(unittest.TestCase):
    def test_removed_rule_stays_deleted_after_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            store = RULES.RuleStore(path)
            rule = store.add("測試舊名", "測試新名", project_id="_default")
            store.save()

            self.assertTrue(store.remove(rule["id"]))
            store.save()
            self.assertEqual(RULES.RuleStore(path).rules, [])

    def test_v1_migrates_and_select_by_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "personal_rules.json"
            # 模擬 v1 檔
            path.write_text(
                '{"version":1,"rules":[{"before":"萬歌","after":"萬哥","domain":"訪談","adopted_count":3,"enabled":true}]}',
                encoding="utf-8",
            )
            store = RULES.RuleStore(path)
            self.assertEqual(store._data["version"], 2)
            rule = store.rules[0]
            self.assertEqual(rule["created_by"], "migrated")
            self.assertEqual(rule["model_follow_count"], 3)
            self.assertEqual(rule["human_accept_count"], 0)
            # 舊規則遷入預設專案庫
            self.assertEqual(rule["scope_id"], RULES.DEFAULT_PROJECT_ID)
            selected = RULES.select_rules_for_prompt(store, domain="訪談")
            self.assertEqual(len(selected), 1)

    def test_rules_are_isolated_per_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            store = RULES.RuleStore(path)
            store.add("萬歌", "萬哥", project_id="proj_a")
            store.add("萬歌", "王哥", project_id="proj_b")
            store.save()
            a = RULES.select_rules_for_prompt(store, project_id="proj_a")
            b = RULES.select_rules_for_prompt(store, project_id="proj_b")
            self.assertEqual(len(a), 1)
            self.assertEqual(a[0]["after"], "萬哥")
            self.assertEqual(len(b), 1)
            self.assertEqual(b[0]["after"], "王哥")
            self.assertEqual(len(store.by_project("proj_a")), 1)
            self.assertEqual(len(store.by_project("proj_b")), 1)

    def test_track_adoption_is_model_follow_not_human(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            store = RULES.RuleStore(path)
            rule = store.add("萬歌", "萬哥", domain="訪談", source="manual", project_id="p1")
            RULES.track_rule_adoption(store, "萬歌來了", "萬哥來了", rules_used=[rule], persist=True)
            reloaded = RULES.RuleStore(path).find("萬歌", "萬哥", project_id="p1")
            self.assertEqual(reloaded["model_follow_count"], 1)
            self.assertEqual(reloaded["human_accept_count"], 0)


class TemplatesDictionaryTests(unittest.TestCase):
    def test_template_and_dictionary_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            tpl = TEMPLATES.TemplateStore(Path(tmp) / "tpl.json")
            body = tpl.get_body("訪談")
            self.assertIn("訪談", body or "訪談")
            section = tpl.build_section("科技")
            self.assertIn("領域校對指引", section)
            dic = TEMPLATES.DictionaryStore(Path(tmp) / "dic.json")
            dic.add("threads", "Threads", category="品牌")
            dic.save()
            sec = dic.build_section()
            self.assertIn("threads", sec)
            self.assertIn("Threads", sec)


class ExperimentHelpersTests(unittest.TestCase):
    def test_estimate_remaining_and_flags(self):
        msg = EXPERIMENTS.estimate_remaining(2, 10, 20.0)
        self.assertIn("剩餘", msg)
        with tempfile.TemporaryDirectory() as tmp:
            cfg = EXPERIMENTS.ExperimentConfig(Path(tmp) / "exp.json")
            self.assertFalse(cfg.get("use_silero_vad"))
            cfg.set("use_silero_vad", True)
            cfg.save()
            cfg2 = EXPERIMENTS.ExperimentConfig(Path(tmp) / "exp.json")
            self.assertTrue(cfg2.get("use_silero_vad"))


class ProjectProfileTests(unittest.TestCase):
    def test_active_project_is_session_only_and_reopens_as_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.json"
            store = LEARNING.ProjectProfileStore(path)
            profile = store.upsert(name="本次專案")
            store.set_active(profile["id"])
            self.assertEqual(store.get_active()["name"], "本次專案")
            store.save()

            reopened = LEARNING.ProjectProfileStore(path)
            self.assertIsNone(reopened.get_active())
            self.assertEqual(reopened.active_id, "")
            self.assertEqual(len(reopened.profiles), 1)

    def test_project_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"APPDATA": str(Path(tmp) / "roaming"), "LOCALAPPDATA": str(Path(tmp) / "local")}
            with mock.patch.dict(os.environ, env, clear=False):
                store = LEARNING.ProjectProfileStore(Path(tmp) / "profiles.json")
                store.upsert(name="萬哥來了", series_name="Podcast", domain="訪談", guests="萬哥")
                store.save()
                ctx = store.context_for_prompt()
                self.assertIn("萬哥來了", ctx)
                self.assertIn("訪談", ctx)


class SupplementHistoryTests(unittest.TestCase):
    def test_history_remembers_recent_projects_deduplicates_and_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "supplement_history.json"
            store = LEARNING.SupplementHistoryStore(path)
            self.assertTrue(store.remember("第一份補充資料", project_id="p1", project_name="專案一"))
            self.assertTrue(store.remember("第二份補充資料", project_id="p2", project_name="專案二"))
            self.assertTrue(store.remember("第一份補充資料", project_id="p3", project_name="專案三"))

            reloaded = LEARNING.SupplementHistoryStore(path)
            self.assertEqual(len(reloaded.entries), 2)
            self.assertEqual(reloaded.entries[0]["text"], "第一份補充資料")
            self.assertEqual(reloaded.entries[0]["project_name"], "專案三")

            reloaded.clear()
            self.assertEqual(LEARNING.SupplementHistoryStore(path).entries, [])


if __name__ == "__main__":
    unittest.main()
