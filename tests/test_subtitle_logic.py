from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "core" / "SanWich_legacy_core.py"
SPEC = importlib.util.spec_from_file_location("sanwich_core_test", CORE_PATH)
CORE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CORE)


class SubtitleLogicTests(unittest.TestCase):
    def test_semantic_boundaries_follow_chinese_phrase_structure(self):
        cases = {
            "傳說中見神殺神見佛殺佛的萬哥出現了": ["傳說中見神殺神", "見佛殺佛的萬哥出現了"],
            "因為今天為什麼是萬哥來呢因為我們的那個綺夢小妹她去外景": [
                "因為今天為什麼是萬哥來呢",
                "因為我們的那個綺夢小妹她去外景",
            ],
            "而且我覺得萬哥很適合來聊 podcast": ["而且我覺得", "萬哥很適合來聊podcast"],
            "那回去就是靠一些肌肉記憶慢慢把事情都撈回來": [
                "那回去就是靠一些肌肉記憶",
                "慢慢把事情都撈回來",
            ],
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(CORE.wrap_srt_text(source), expected)

    def test_spacing_and_numeric_punctuation_are_preserved(self):
        cases = {
            "聊 podcast": "聊podcast",
            "使用Threads 最大": "使用Threads最大",
            "澳幣 7.99": "澳幣7.99",
            "版本 2.3.1": "版本2.3.1",
            "冷氣真舒服耶 6月 7月": "冷氣真舒服耶6月 7月",
            "睽違6 7 年": "睽違6 7年",
            "1,000 元": "1,000元",
            "12:30 開始": "12:30開始",
            "6-7年": "6-7年",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(CORE.strip_punct_for_srt(source), expected)

    def test_batch_boundary_overlap_trims_previous_caption(self):
        chunks = [
            {"timestamp": (59.0, 60.2), "text": "前一批"},
            {"timestamp": (60.0, 61.0), "text": "下一批"},
        ]
        normalized, adjusted = CORE.normalize_chunk_timeline(chunks)
        self.assertEqual(adjusted, 1)
        self.assertEqual(normalized[0]["timestamp"], (59.0, 60.0))
        self.assertEqual(normalized[1]["timestamp"], (60.0, 61.0))

    def test_inserted_caption_does_not_shift_edit_history_alignment(self):
        original = [
            {"timestamp": (0.0, 1.0), "text": "甲"},
            {"timestamp": (1.0, 2.0), "text": "乙"},
            {"timestamp": (2.0, 3.0), "text": "丙"},
        ]
        updated = [
            {"timestamp": (0.0, 1.0), "text": "甲"},
            {"timestamp": (1.0, 1.5), "text": "新增"},
            {"timestamp": (1.0, 2.0), "text": "乙"},
            {"timestamp": (2.0, 3.0), "text": "丙"},
        ]
        self.assertEqual(
            CORE.align_caption_indices(original, updated),
            [(0, 0), (None, 1), (1, 2), (2, 3)],
        )

    def test_ai_coverage_reports_partial_response(self):
        chunks = [
            {"timestamp": (0.0, 1.0), "text": "第一句"},
            {"timestamp": (1.0, 2.0), "text": "第二句"},
        ]
        original_call = CORE._llm_call_once
        try:
            CORE._llm_call_once = lambda *_args, **_kwargs: (
                "1\n00:00:00,000 --> 00:00:01,000\n第一句已校對\n"
            )
            CORE.llm_merge(
                chunks,
                {"api_provider": "openai", "api_key": "test", "model": "test"},
                lambda *_args: None,
            )
        finally:
            CORE._llm_call_once = original_call
        self.assertEqual(CORE.LAST_LLM_MERGE_META["covered_count"], 1)
        self.assertEqual(CORE.LAST_LLM_MERGE_META["total_count"], 2)
        self.assertEqual(CORE.LAST_LLM_MERGE_META["covered_indices"], [0])
        self.assertEqual(chunks[1]["text"], "第二句")


if __name__ == "__main__":
    unittest.main()
