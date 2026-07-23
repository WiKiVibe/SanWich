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
    def test_context_terms_force_user_casing_without_touching_longer_words(self):
        terms = CORE.canonical_terms_from_context("DemoMark 請統一寫成 DEMOMARK；另外使用 Siri AI")
        self.assertEqual(terms["demomark"], "DEMOMARK")
        self.assertEqual(
            CORE.apply_context_canonical_terms("DemoMark與demomark，但DemoMarker不變", terms),
            "DEMOMARK與DEMOMARK，但DemoMarker不變",
        )

    def test_context_is_sent_and_casing_is_enforced_without_editor_prompt(self):
        chunks = [{"timestamp": (0.0, 1.0), "text": "DemoMark推出Demo Glass新功能"}]
        captured = []
        original_call = CORE._llm_call_once
        try:
            def fake_call(system, user_msg, _cfg):
                captured.append((system, user_msg))
                return "1\n00:00:00,000 --> 00:00:01,000\nDemoMark推出Demo Glass新功能\n"

            CORE._llm_call_once = fake_call
            result, _plain = CORE.llm_merge(
                chunks,
                {
                    "api_provider": "openai", "api_key": "test", "model": "test",
                    "_llm_retry_delays": [],
                },
                lambda *_args: None,
                context_notes="DemoMark > DEMOMARK\nDemo Glass > 示範眼鏡",
                use_text_fix=False,
            )
        finally:
            CORE._llm_call_once = original_call

        self.assertEqual(result, ["DEMOMARK推出示範眼鏡新功能"])
        self.assertIn("DemoMark > DEMOMARK", captured[0][1])
        self.assertLess(captured[0][1].find("DEMOMARK"), captured[0][1].find("00:00:00,000"))
        self.assertIn("補充資料優先規則", captured[0][0])

    def test_script_document_matching_uses_script_spelling(self):
        matched, meta = CORE.document_match_texts(
            ["今天介紹 DemoMark", "示範眼鏡的新功能"],
            "今天介紹 DEMOMARK 示範眼鏡的新功能",
        )

        self.assertEqual(matched, ["今天介紹DEMOMARK", "示範眼鏡的新功能"])
        self.assertEqual(meta["matched"], 2)
        self.assertEqual(meta["low_score"], 0)

    def test_arrow_context_replacement_is_deterministic(self):
        replacements = CORE.replacements_from_context("痘痘要 > 痘痘藥")
        self.assertEqual(
            CORE.apply_context_replacements("痘痘要很好用", replacements),
            "痘痘藥很好用",
        )

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

    def test_ai_review_colors_follow_time_after_resegmentation(self):
        before = [
            {"timestamp": (0.0, 2.0), "text": "第一句"},
            {"timestamp": (2.0, 4.0), "text": "第二句"},
        ]
        after = [
            {"timestamp": (0.0, 2.0), "text": "第一句"},
            {"timestamp": (2.0, 4.0), "text": "第二句已校對"},
        ]
        output = [
            {"timestamp": (0.0, 1.0), "text": "第一"},
            {"timestamp": (1.0, 2.0), "text": "句"},
            {"timestamp": (2.0, 3.0), "text": "第二句"},
            {"timestamp": (3.0, 4.0), "text": "已校對"},
        ]

        reviewed, checked, unchecked = CORE.project_ai_review_indices(
            before, after, output, covered_indices=[0, 1]
        )
        self.assertEqual(checked, {0, 1, 2, 3})
        self.assertEqual(reviewed, {2, 3})
        self.assertEqual(unchecked, set())

        reviewed, checked, unchecked = CORE.project_ai_review_indices(
            before, after, output, covered_indices=[0]
        )
        self.assertEqual(checked, {0, 1})
        self.assertEqual(reviewed, set())
        self.assertEqual(unchecked, {2, 3})

    def test_ai_coverage_retries_only_missing_groups(self):
        chunks = [
            {"timestamp": (0.0, 1.0), "text": "第一句"},
            {"timestamp": (1.0, 2.0), "text": "第二句"},
        ]
        original_call = CORE._llm_call_once
        responses = iter([
            "1\n00:00:00,000 --> 00:00:01,000\n第一句已校對\n",
            "2\n00:00:01,000 --> 00:00:02,000\n第二句已校對\n",
        ])
        try:
            CORE._llm_call_once = lambda *_args, **_kwargs: next(responses)
            CORE.llm_merge(
                chunks,
                {
                    "api_provider": "openai", "api_key": "test", "model": "test",
                    "_llm_retry_delays": [], "_semantic_integrity_retries": 0,
                },
                lambda *_args: None,
            )
        finally:
            CORE._llm_call_once = original_call
        self.assertEqual(CORE.LAST_LLM_MERGE_META["covered_count"], 2)
        self.assertEqual(CORE.LAST_LLM_MERGE_META["total_count"], 2)
        self.assertEqual(CORE.LAST_LLM_MERGE_META["covered_indices"], [0, 1])
        self.assertTrue(CORE.LAST_LLM_MERGE_META["complete"])
        self.assertGreaterEqual(CORE.LAST_LLM_MERGE_META["partial_retry_count"], 1)
        self.assertEqual(chunks[1]["text"], "第二句已校對")

    def test_ai_coverage_reports_partial_after_retry_limit(self):
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
                {
                    "api_provider": "openai", "api_key": "test", "model": "test",
                    "_llm_retry_delays": [], "_llm_partial_retry_depth": 1,
                },
                lambda *_args: None,
            )
        finally:
            CORE._llm_call_once = original_call
        self.assertEqual(CORE.LAST_LLM_MERGE_META["covered_count"], 1)
        self.assertFalse(CORE.LAST_LLM_MERGE_META["complete"])
        self.assertEqual(CORE.LAST_LLM_MERGE_META["uncovered_indices"], [1])
        self.assertEqual(chunks[1]["text"], "第二句")

    def test_ai_request_retries_transient_failure(self):
        chunks = [{"timestamp": (0.0, 1.0), "text": "第一句"}]
        original_call = CORE._llm_call_once
        call_count = {"value": 0}

        def fake_call(*_args, **_kwargs):
            call_count["value"] += 1
            if call_count["value"] == 1:
                raise RuntimeError("請求太頻繁，請稍後再試")
            return "1\n00:00:00,000 --> 00:00:01,000\n第一句已校對\n"

        try:
            CORE._llm_call_once = fake_call
            CORE.llm_merge(
                chunks,
                {
                    "api_provider": "openai", "api_key": "test", "model": "test",
                    "_llm_retry_delays": [0],
                },
                lambda *_args: None,
            )
        finally:
            CORE._llm_call_once = original_call
        self.assertEqual(call_count["value"], 2)
        self.assertEqual(CORE.LAST_LLM_MERGE_META["retry_count"], 1)
        self.assertTrue(CORE.LAST_LLM_MERGE_META["complete"])

    def test_ai_batching_caps_short_caption_group_count(self):
        chunks = [
            {"timestamp": (float(i), float(i + 1)), "text": f"短句{i}"}
            for i in range(90)
        ]
        original_call = CORE._llm_call_once
        groups_per_request = []

        def echo_srt(_system, user_msg, _cfg):
            srt_body = user_msg.split("\n\n", 1)[1]
            groups_per_request.append(srt_body.count("-->"))
            return srt_body

        try:
            CORE._llm_call_once = echo_srt
            CORE.llm_merge(
                chunks,
                {
                    "api_provider": "openai", "api_key": "test", "model": "test",
                    "_llm_retry_delays": [],
                },
                lambda *_args: None,
                use_text_fix=False,
            )
        finally:
            CORE._llm_call_once = original_call

        self.assertEqual(CORE.LAST_LLM_MERGE_META["covered_count"], 90)
        self.assertTrue(CORE.LAST_LLM_MERGE_META["complete"])
        self.assertEqual(CORE.LAST_LLM_MERGE_META["total_batches"], 3)
        self.assertLessEqual(max(groups_per_request), CORE.LLM_BATCH_MAX_GROUPS)

    def test_semantic_resegmentation_redistributes_corrected_master_over_fixed_timecodes(self):
        chunks = [
            {"timestamp": (1.12, 2.475), "text": "這一次的教育"},
            {"timestamp": (2.475, 3.92), "text": "改革是希望讓"},
            {"timestamp": (3.92, 5.817), "text": "大家都可以看到"},
        ]
        expected = [
            "這一次的教育改革",
            "是希望讓大家",
            "都可以看到",
        ]
        response = __import__("json").dumps({
            "assignments": [
                {"id": f"TC{i + 1:04d}", "text": text}
                for i, text in enumerate(expected)
            ]
        }, ensure_ascii=False)
        original_call = CORE._llm_call_once
        captured_messages = []
        try:
            CORE._llm_call_once = lambda _system, user_msg, _cfg: (
                captured_messages.append(user_msg) or response
            )
            result, meta = CORE.semantic_resegment_chunks(
                chunks,
                {
                    "api_provider": "openai", "api_key": "test", "model": "test",
                    "_llm_retry_delays": [],
                },
                lambda *_args: None,
                target_width=13,
            )
        finally:
            CORE._llm_call_once = original_call

        self.assertTrue(meta["complete"])
        self.assertTrue(meta["usable"])
        self.assertTrue(meta["text_preserved"])
        self.assertTrue(meta["fixed_timecodes"])
        self.assertEqual(len(captured_messages), 1)
        self.assertIn("這一次的教育改革｜是希望讓大家｜都可以看到", CORE.SEMANTIC_SEGMENTATION_PROMPT)
        self.assertIn("這一次｜的教育改革是希望｜讓大家都可以看到", CORE.SEMANTIC_SEGMENTATION_PROMPT)
        self.assertEqual([row["text"] for row in result], expected)
        original_text = "".join(CORE.strip_punct_for_srt(row["text"]).replace(" ", "") for row in chunks)
        result_text = "".join(row["text"].replace(" ", "") for row in result)
        self.assertEqual(result_text, original_text)
        self.assertAlmostEqual(result[0]["timestamp"][0], 1.12, places=3)
        self.assertEqual(
            [row["timestamp"] for row in result],
            [row["timestamp"] for row in chunks],
        )

    def test_semantic_resegmentation_uses_five_group_readonly_context(self):
        chunks = [
            {"timestamp": (float(i), float(i + 1)), "text": f"第{i + 1}組文字"}
            for i in range(12)
        ]
        original_call = CORE._llm_call_once
        captured_messages = []

        def echo_fixed_groups(_system, user_msg, _cfg):
            captured_messages.append(user_msg)
            ids_text = user_msg.split("【本次寫入槽位】\n", 1)[1].split("\n", 1)[0]
            expected_ids = [item.strip() for item in ids_text.split(",")]
            master = user_msg.split("【本次校正版母稿】\n", 1)[1].split("\n【驗證】", 1)[0]
            original_rows = {
                f"TC{i + 1:04d}": CORE.strip_punct_for_srt(chunks[i]["text"])
                for i in range(len(chunks))
            }
            assignments = [
                {"id": tc_id, "text": original_rows[tc_id]}
                for tc_id in expected_ids
            ]
            self.assertEqual("".join(row["text"] for row in assignments), master)
            return __import__("json").dumps({"assignments": assignments}, ensure_ascii=False)

        try:
            CORE._llm_call_once = echo_fixed_groups
            result, meta = CORE.semantic_resegment_chunks(
                chunks,
                {
                    "api_provider": "openai", "api_key": "test", "model": "test",
                    "_llm_retry_delays": [],
                },
                lambda *_args: None,
            )
        finally:
            CORE._llm_call_once = original_call

        self.assertEqual(len(captured_messages), 3)
        self.assertIn("【寫入】 TC0001", captured_messages[0])
        self.assertIn("【參考】 TC0006", captured_messages[0])
        self.assertNotIn("TC0011", captured_messages[0])
        self.assertIn("【參考】 TC0005", captured_messages[1])
        self.assertIn("【寫入】 TC0006", captured_messages[1])
        self.assertIn("【參考】 TC0011", captured_messages[1])
        self.assertTrue(meta["complete"])
        self.assertEqual([row["timestamp"] for row in result], [row["timestamp"] for row in chunks])

    def test_semantic_resegmentation_rejects_text_change_but_keeps_fixed_tc_window(self):
        chunks = [{"timestamp": (0.0, 2.0), "text": "我做了一張生日賀卡"}]
        original_call = CORE._llm_call_once
        try:
            CORE._llm_call_once = lambda *_args, **_kwargs: (
                '{"assignments":[{"id":"TC0001","text":"我做了一張生日卡片"}]}'
            )
            result, meta = CORE.semantic_resegment_chunks(
                chunks,
                {
                    "api_provider": "openai", "api_key": "test", "model": "test",
                    "_llm_retry_delays": [], "_semantic_integrity_retries": 0,
                },
                lambda *_args: None,
            )
        finally:
            CORE._llm_call_once = original_call

        self.assertEqual(result, chunks)
        self.assertFalse(meta["complete"])
        self.assertTrue(meta["usable"])
        self.assertEqual(meta["failed_windows"], [1])
        self.assertEqual(meta["integrity_failures"], 1)

    def test_semantic_resegmentation_keeps_only_failed_window_original(self):
        chunks = [
            {"timestamp": (float(i), float(i + 1)), "text": f"第{i + 1}組"}
            for i in range(6)
        ]
        responses = iter([
            __import__("json").dumps({
                "assignments": [
                    {"id": "TC0001", "text": "第1組第2組"},
                    {"id": "TC0002", "text": "第3組"},
                    {"id": "TC0003", "text": "第4組"},
                    {"id": "TC0004", "text": "第5"},
                    {"id": "TC0005", "text": "組"},
                ]
            }, ensure_ascii=False),
            '{"assignments":[{"id":"TC0006","text":"錯誤文字"}]}',
        ])
        original_call = CORE._llm_call_once
        try:
            CORE._llm_call_once = lambda *_args, **_kwargs: next(responses)
            result, meta = CORE.semantic_resegment_chunks(
                chunks,
                {
                    "api_provider": "openai", "api_key": "test", "model": "test",
                    "_llm_retry_delays": [], "_semantic_integrity_retries": 0,
                },
                lambda *_args: None,
            )
        finally:
            CORE._llm_call_once = original_call

        self.assertFalse(meta["complete"])
        self.assertTrue(meta["partial"])
        self.assertEqual(meta["applied_windows"], [1])
        self.assertEqual(meta["failed_windows"], [2])
        self.assertEqual(result[0]["text"], "第1組第2組")
        self.assertEqual(result[5]["text"], "第6組")
        self.assertEqual([row["timestamp"] for row in result], [row["timestamp"] for row in chunks])

    def test_semantic_resegmentation_retries_integrity_violation(self):
        chunks = [{"timestamp": (0.0, 2.0), "text": "每個題結束之後我會給一個排名"}]
        responses = iter([
            '{"assignments":[{"id":"TC0001","text":"每題結束之後我會給一個排名"}]}',
            '{"assignments":[{"id":"TC0001","text":"每個題結束之後我會給一個排名"}]}',
        ])
        original_call = CORE._llm_call_once
        try:
            CORE._llm_call_once = lambda *_args, **_kwargs: next(responses)
            result, meta = CORE.semantic_resegment_chunks(
                chunks,
                {
                    "api_provider": "openai", "api_key": "test", "model": "test",
                    "_llm_retry_delays": [], "_semantic_integrity_retries": 1,
                },
                lambda *_args: None,
            )
        finally:
            CORE._llm_call_once = original_call

        self.assertTrue(meta["complete"])
        self.assertEqual(meta["integrity_failures"], 1)
        self.assertEqual(meta["integrity_retry_count"], 1)
        self.assertEqual([row["text"] for row in result], ["每個題結束之後我會給一個排名"])


if __name__ == "__main__":
    unittest.main()
