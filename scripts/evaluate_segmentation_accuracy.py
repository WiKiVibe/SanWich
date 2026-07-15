#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""以訓練資料夾的正解 SRT 驗證文字與斷句相似度。

斷句分數會先用文字 alignment 消除錯字／漏字造成的累積位移，再比較切點。
切點落在一個「目標字幕長度」範圍內視為相同語意鄰域；這比直接用第 N 字
硬比可靠，也不會把純文字辨識錯誤重複扣分。
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "core" / "SanWich_legacy_core.py"
SRT_TIME_RE = re.compile(
    r"(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*"
    r"(\d\d):(\d\d):(\d\d),(\d\d\d)"
)
NORMALIZE_RE = re.compile(r"[\s，。！？、,.!?;；:：\"「」『』（）()\[\]【】…—-]+")


def load_core():
    spec = importlib.util.spec_from_file_location("sanwich_segmentation_eval_core", CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"無法載入核心：{CORE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seconds(parts: list[int]) -> float:
    h, m, s, ms = parts
    return h * 3600 + m * 60 + s + ms / 1000


def parse_srt(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    rows: list[dict] = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        match = SRT_TIME_RE.fullmatch(lines[1].strip())
        if not match:
            continue
        values = [int(value) for value in match.groups()]
        rows.append({
            "timestamp": (_seconds(values[:4]), _seconds(values[4:])),
            "text": "".join(line.strip() for line in lines[2:]),
        })
    return rows


def normalize_text(text: str) -> str:
    return NORMALIZE_RE.sub("", text or "")


def flatten_with_boundaries(rows: list[dict]) -> tuple[str, list[int]]:
    pieces: list[str] = []
    boundaries: list[int] = []
    position = 0
    for index, row in enumerate(rows):
        text = normalize_text(row.get("text") or "")
        pieces.append(text)
        position += len(text)
        if index < len(rows) - 1:
            boundaries.append(position)
    return "".join(pieces), boundaries


def align_boundary_positions(source: str, reference: str, positions: list[int]) -> list[int]:
    opcodes = difflib.SequenceMatcher(None, source, reference, autojunk=False).get_opcodes()
    aligned: list[int] = []
    opcode_index = 0
    for position in positions:
        while opcode_index + 1 < len(opcodes) and position > opcodes[opcode_index][2]:
            opcode_index += 1
        tag, a1, a2, b1, b2 = opcodes[opcode_index]
        if a2 == a1:
            mapped = b1
        elif tag == "equal":
            mapped = b1 + (position - a1)
        else:
            mapped = round(b1 + (position - a1) * (b2 - b1) / (a2 - a1))
        aligned.append(mapped)
    return aligned


def boundary_f1(predicted: list[int], reference: list[int], tolerance: int) -> float:
    i = j = hits = 0
    while i < len(predicted) and j < len(reference):
        delta = predicted[i] - reference[j]
        if abs(delta) <= tolerance:
            hits += 1
            i += 1
            j += 1
        elif delta < -tolerance:
            i += 1
        else:
            j += 1
    precision = hits / len(predicted) if predicted else 1.0
    recall = hits / len(reference) if reference else 1.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def evaluate(candidate_rows: list[dict], reference_rows: list[dict], target_width: float) -> dict:
    candidate_text, candidate_boundaries = flatten_with_boundaries(candidate_rows)
    reference_text, reference_boundaries = flatten_with_boundaries(reference_rows)
    matcher = difflib.SequenceMatcher(None, candidate_text, reference_text, autojunk=False)
    content_score = matcher.ratio()
    aligned_boundaries = align_boundary_positions(candidate_text, reference_text, candidate_boundaries)
    # 允許一個目標字幕長度的語意鄰域；文字差異已由 alignment 先行消除。
    tolerance = max(12, int(math.ceil(target_width)))
    segmentation_score = boundary_f1(aligned_boundaries, reference_boundaries, tolerance)
    overall_score = 0.5 * content_score + 0.5 * segmentation_score
    return {
        "candidate_entries": len(candidate_rows),
        "reference_entries": len(reference_rows),
        "content": content_score,
        "segmentation": segmentation_score,
        "overall": overall_score,
        "boundary_tolerance_chars": tolerance,
    }


def find_pairs(folder: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for reference in sorted(folder.glob("*_正解.srt")):
        candidate = reference.with_name(reference.name.replace("_正解.srt", ".srt"))
        if candidate.exists():
            pairs.append((candidate, reference))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", nargs="?", type=Path, default=ROOT / "test_footage")
    parser.add_argument("--rewrite-candidates", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.90)
    args = parser.parse_args()

    core = load_core()
    target_width = float(core.SRT_TARGET_LINE_WIDTH)
    pairs = find_pairs(args.folder)
    if not pairs:
        raise SystemExit(f"找不到候選／正解 SRT 配對：{args.folder}")

    failed = False
    for candidate, reference in pairs:
        rows = parse_srt(candidate)
        if args.rewrite_candidates:
            # 安全護欄：正解檔永遠不能成為寫入目標。
            if "_正解" in candidate.stem:
                raise RuntimeError(f"拒絕覆寫正解：{candidate}")
            rendered = core.chunks_to_srt(rows, max_line_width=target_width)
            candidate.write_text(rendered, encoding="utf-8-sig")
            rows = parse_srt(candidate)
        reference_rows = parse_srt(reference)
        score = evaluate(rows, reference_rows, target_width)
        passed = score["overall"] >= args.threshold and score["segmentation"] >= args.threshold
        failed = failed or not passed
        print(
            f"{candidate.name}: entries {score['candidate_entries']}/{score['reference_entries']} | "
            f"text {score['content']:.2%} | segmentation {score['segmentation']:.2%} | "
            f"overall {score['overall']:.2%} | {'PASS' if passed else 'FAIL'}"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
