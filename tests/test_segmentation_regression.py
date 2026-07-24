# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_core():
    path = ROOT / "core" / "SanWich_legacy_core.py"
    spec = importlib.util.spec_from_file_location("sanwich_segmentation_test_core", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


CORE = load_core()


class SegmentationRegressionTests(unittest.TestCase):
    def test_clause_taking_verb_is_not_preferred_boundary(self):
        conditional_cost = CORE._boundary_linguistic_cost("如果你真的覺得", "這件事", "v", "n")
        parenthetical_cost = CORE._boundary_linguistic_cost("而且我覺得", "來賓", "v", "n")
        self.assertGreater(conditional_cost, 0)
        self.assertLess(parenthetical_cost, 0)

    def test_resegment_can_split_one_breeze_chunk(self):
        chunks = [{
            "text": "就是戴一戴然後跟大家分享一下到底好不好用舒不舒服",
            "timestamp": (8.04, 11.72),
        }]
        result = CORE.resegment_chunks_for_srt(chunks, max_line_width=11)
        self.assertGreaterEqual(len(result), 2)
        self.assertEqual("".join(row["text"] for row in result), chunks[0]["text"])

    def test_resegment_merges_incomplete_clause_without_losing_text(self):
        chunks = [
            {"text": "如果你現在真的覺得", "timestamp": (0.0, 2.5)},
            {"text": "自己在職場上面被欺負", "timestamp": (2.5, 5.4)},
        ]
        result = CORE.resegment_chunks_for_srt(chunks, max_line_width=11)
        self.assertEqual("".join(row["text"] for row in result), "".join(row["text"] for row in chunks))
        self.assertFalse(any(row["text"].endswith("覺得") for row in result[:-1]))

    def test_resegment_never_starts_a_caption_with_aspect_particle(self):
        source = "那這個應該是我見過的Apple最誇張的一次洩密了"
        chunks = [{"text": source, "timestamp": (29.96, 33.68)}]
        result = CORE.resegment_chunks_for_srt(chunks, max_line_width=13)
        texts = [row["text"] for row in result]

        self.assertEqual("".join(texts), source)
        self.assertFalse(any(text.startswith(CORE._FORBIDDEN_SRT_STARTS) for text in texts[1:]))
        self.assertFalse(any(left.endswith("見") and right.startswith("過")
                             for left, right in zip(texts, texts[1:])))
        self.assertFalse(any(left.endswith("誇") and right.startswith("張")
                             for left, right in zip(texts, texts[1:])))

    def test_resegment_repairs_protected_word_split_across_breeze_chunks(self):
        chunks = [
            {"text": "不管是自拍視", "timestamp": (0.0, 1.0)},
            {"text": "訊拍一個vlog", "timestamp": (1.0, 2.0)},
        ]
        result = CORE.resegment_chunks_for_srt(chunks, max_line_width=13)
        texts = [row["text"] for row in result]

        self.assertEqual("".join(texts), "不管是自拍視訊拍一個vlog")
        self.assertFalse(any(left.endswith("視") and right.startswith("訊")
                             for left, right in zip(texts, texts[1:])))

    def test_editor_prompt_preserves_meaning_but_allows_redundant_fillers(self):
        self.assertIn("保留會影響語氣、立場或人物個性", CORE.EDITOR_SYSTEM_PROMPT)
        self.assertIn("可適度刪除", CORE.EDITOR_SYSTEM_PROMPT)
        self.assertIn("不得刪掉事實、例子、程度、否定", CORE.EDITOR_SYSTEM_PROMPT)
        self.assertIn("不要把文字跨組搬", CORE.EDITOR_SYSTEM_PROMPT)
        self.assertIn("全文專名一致性", CORE.EDITOR_SYSTEM_PROMPT)

    def test_full_srt_pass_repairs_incomplete_modal_boundaries(self):
        chunks = [
            {"text": "第一個就是它能不能", "timestamp": (81.48, 83.258)},
            {"text": "畫出正確的中文", "timestamp": (83.258, 84.64)},
            {"text": "第二個就是它", "timestamp": (84.64, 85.852)},
            {"text": "能不能按照我們的要求", "timestamp": (85.852, 87.872)},
            {"text": "去做修改", "timestamp": (87.872, 88.68)},
        ]
        result = CORE.resegment_chunks_for_srt(chunks, max_line_width=13)
        texts = [row["text"] for row in result]

        self.assertFalse(any(left.endswith("能不能") for left in texts[:-1]))
        self.assertFalse(any(left.endswith("就是它") for left in texts[:-1]))
        self.assertFalse(any(left.endswith("要求") and right.startswith("去")
                             for left, right in zip(texts, texts[1:])))
        self.assertTrue(CORE.LAST_SRT_SEGMENTATION_META["local_full_pass"])

    def test_full_srt_pass_does_not_merge_natural_then_boundary(self):
        entries = [
            {"text": "這邊講完了", "timestamp": (0.0, 1.0)},
            {"text": "然後換下一題", "timestamp": (1.0, 2.0)},
        ]
        repaired, count = CORE.validate_and_repair_srt_segmentation(entries, target=13)
        self.assertEqual(count, 0)
        self.assertEqual([row["text"] for row in repaired], ["這邊講完了", "然後換下一題"])

    def test_full_srt_pass_repairs_object_and_conjunction_boundaries(self):
        entries = [
            {"text": "於是我要叫", "timestamp": (0.0, 1.0)},
            {"text": "它把沒用的東西拿掉", "timestamp": (1.0, 2.2)},
            {"text": "那Claude", "timestamp": (2.2, 3.0)},
            {"text": "和Grok都有分隔線", "timestamp": (3.0, 4.2)},
        ]
        repaired, count = CORE.validate_and_repair_srt_segmentation(entries, target=13)
        texts = [row["text"] for row in repaired]
        self.assertGreaterEqual(count, 2)
        self.assertFalse(any(left.endswith("叫") for left in texts[:-1]))
        self.assertFalse(any(right.startswith("和") for right in texts[1:]))


if __name__ == "__main__":
    unittest.main()
