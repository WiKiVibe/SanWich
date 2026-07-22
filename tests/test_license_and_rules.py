from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


LICENSE = load_module("sanwich_license_test", ROOT / "core" / "license_manager.py")
RULES = load_module("sanwich_rules_test", ROOT / "core" / "personal_rules.py")


class LicenseAndRulesTests(unittest.TestCase):
    def test_trial_survives_primary_file_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            roaming = Path(tmp) / "roaming"
            local = Path(tmp) / "local"
            env = {
                "APPDATA": str(roaming),
                "LOCALAPPDATA": str(local),
                "SANWICH_LICENSE_REGISTRY_DISABLED": "1",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                first = LICENSE.LicenseManager()
                started_at = first.license_data["trial_started_at"]
                LICENSE.license_path().unlink()
                recovered = LICENSE.LicenseManager()

                self.assertEqual(recovered.license_data["trial_started_at"], started_at)
                self.assertTrue(LICENSE.license_path().exists())
                self.assertTrue(recovered.has_feature("single_transcription"))
                self.assertTrue(recovered.has_feature("custom_rules"))

    def test_invalid_existing_license_falls_back_to_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            roaming = Path(tmp) / "roaming"
            local = Path(tmp) / "local"
            env = {
                "APPDATA": str(roaming),
                "LOCALAPPDATA": str(local),
                "SANWICH_LICENSE_REGISTRY_DISABLED": "1",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                path = LICENSE.license_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{"edition":"trial","trial_started_at":"2099-01-01"}', encoding="utf-8")
                manager = LICENSE.LicenseManager()

                self.assertFalse(manager.is_trial_active())
                self.assertTrue(manager.has_feature("single_transcription"))
                self.assertFalse(manager.has_feature("custom_rules"))

    def test_rule_selection_and_human_counts_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "personal_rules.json"
            store = RULES.RuleStore(path)
            rule = store.add("萬歌", "萬哥", domain="訪談")
            store.save()

            selected = RULES.select_rules_for_prompt(store, domain="訪談")
            self.assertEqual([item["id"] for item in selected], [rule["id"]])
            store.mark_adopted(rule["id"])
            store.save()

            reloaded = RULES.RuleStore(path)
            saved = reloaded.find("萬歌", "萬哥")
            self.assertIsNotNone(saved)
            self.assertEqual(saved["adopted_count"], 1)

    def test_personal_rules_are_not_injected_when_supporter_feature_is_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "APPDATA": str(Path(tmp) / "roaming"),
                "LOCALAPPDATA": str(Path(tmp) / "local"),
                "SANWICH_LICENSE_REGISTRY_DISABLED": "1",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                app_path = ROOT / "SanWich.py"
                app = load_module("sanwich_app_rule_gate_test", app_path)
                rules_path = Path(tmp) / "personal_rules.json"
                store = app.PERSONAL_RULES.RuleStore(rules_path)
                store.add("萬歌", "萬哥", domain="訪談")
                store.save()
                app.PERSONAL_RULES_PATH = rules_path

                captured = []

                def fake_llm(system, _user_msg, _cfg):
                    captured.append(system)
                    return "萬哥"

                app._LEGACY_LLM_CALL_ONCE = fake_llm
                cfg = {
                    "api_provider": "openai",
                    "api_key": "test",
                    "model": "test",
                    "use_personal_rules": True,
                    "personal_rules_domain": "訪談",
                }

                app.has_feature = lambda _name: False
                app._llm_call_once_with_deepseek("基本指令", "萬歌", cfg)
                self.assertNotIn("「萬歌」→「萬哥」", captured[-1])

                app.has_feature = lambda _name: True
                app._llm_call_once_with_deepseek("基本指令", "萬歌", cfg)
                self.assertIn("「萬歌」→「萬哥」", captured[-1])


if __name__ == "__main__":
    unittest.main()
