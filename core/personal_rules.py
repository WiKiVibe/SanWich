# -*- coding: utf-8 -*-
"""
聲文去Sanwich 個人化規則庫（階段 5 輪 A：資料層與規則抽取）

責任：
- RuleStore：JSON 規則庫的載入、存檔、新增、查詢、計次
- extract_candidates：從 before→after 文字對抽出「短字替換」候選規則
- summarise_candidates：把多次出現的相同替換聚合計次

設計原則：
- 純本機儲存（與 config.json 同層），不上傳任何使用者個人規則
- 輪 A 階段先收集規則，「啟用注入 prompt」留到輪 B
- 不在此處呼叫 GUI 或 AI，只做資料處理
"""

from __future__ import annotations

import datetime as _dt
import difflib
import json
import re
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Iterable

# 預設領域：呼叫端可以自訂，但建議至少保留前兩個
DEFAULT_DOMAINS: tuple[str, ...] = (
    "通用",
    "訪談",
    "新聞",
    "科技",
    "教學",
    "自訂",
)

# 規則抽取上限
MAX_RULE_FRAGMENT_LEN = 18      # before / after 任一邊超過這個字數就視為改寫，不收
MIN_RULE_FRAGMENT_LEN = 1       # 至少要有一個字
MAX_RULES_PER_CALL = 60         # 一次匯出最多回傳 N 條候選，避免對話框爆掉

# 視為「口水詞」或無意義差異，不要當規則
_FILLER_PATTERNS = (
    "嗯", "啊", "喔", "哦", "呃", "欸",
    "那個", "就是", "然後", "對啊", "對對對", "對對",
    "你知道", "我覺得", "我跟你說",
)

# 標點 / 控制字元（純標點變動不收）
_PUNCT_RE = re.compile(r"^[\s，。！？、,.!?;:\-–—~～「」『』《》【】〔〕\(\)\[\]\"'`]+$")


def _is_punct_only(text: str) -> bool:
    return bool(_PUNCT_RE.match(text or ""))


def _is_filler_only(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    return stripped in _FILLER_PATTERNS


def _normalise(text: str) -> str:
    return (text or "").strip()


# ─────────────────────────────────────────────────────────────
# 規則抽取
# ─────────────────────────────────────────────────────────────

def _diff_replace_blocks(before: str, after: str) -> list[tuple[str, str]]:
    """
    回傳 [(before_chunk, after_chunk), ...]，只保留 SequenceMatcher 視為 'replace' 的片段。
    純 insert / delete 不保留（避免把「刪贅詞」當成規則）。
    """
    sm = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    blocks: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "replace":
            continue
        bchunk = before[i1:i2]
        achunk = after[j1:j2]
        if not bchunk or not achunk:
            continue
        blocks.append((bchunk, achunk))
    return blocks


def _qualify(before_chunk: str, after_chunk: str) -> bool:
    """判斷一對 (before, after) 是否合格成為規則候選。"""
    b = _normalise(before_chunk)
    a = _normalise(after_chunk)
    if not b or not a:
        return False
    if b == a:
        return False
    if not (MIN_RULE_FRAGMENT_LEN <= len(b) <= MAX_RULE_FRAGMENT_LEN):
        return False
    if not (MIN_RULE_FRAGMENT_LEN <= len(a) <= MAX_RULE_FRAGMENT_LEN):
        return False
    if _is_punct_only(b) and _is_punct_only(a):
        return False
    if _is_filler_only(b) or _is_filler_only(a):
        return False
    return True


def extract_candidates(before_text: str, after_text: str) -> list[tuple[str, str]]:
    """從單筆 before/after 文字抽出合格的 (before, after) 替換候選。"""
    bt = _normalise(before_text)
    at = _normalise(after_text)
    if not bt or not at or bt == at:
        return []
    # 全行改寫（長度差距 > 40% 或長度本身 > 60）視為改寫，不收
    if len(bt) > 60 or len(at) > 60:
        return []
    if max(len(bt), len(at)) > 0:
        length_ratio = abs(len(bt) - len(at)) / max(len(bt), len(at))
        if length_ratio > 0.5:
            return []
    pairs = _diff_replace_blocks(bt, at)
    return [(b, a) for b, a in pairs if _qualify(b, a)]


def summarise_candidates(
    rows: Iterable[dict],
    existing_keys: set[tuple[str, str]] | None = None,
) -> list[dict]:
    """
    rows: iterable of edit history rows，每個 row 至少要有 before_text / after_text。
    回傳：聚合後的候選清單，依出現次數遞減排序，最多 MAX_RULES_PER_CALL 條。

    每個候選格式：
        {
            "before": str,
            "after": str,
            "occurrences": int,
            "samples": [(before_text, after_text), ...]  # 最多 3 個原始上下文
        }

    existing_keys：已在規則庫的 (before, after) 集合，這裡會直接過濾掉以免重複建議。
    """
    existing = existing_keys or set()
    bucket: dict[tuple[str, str], dict] = {}
    for row in rows:
        before = row.get("before_text") or ""
        after = row.get("after_text") or ""
        for b, a in extract_candidates(before, after):
            key = (b, a)
            if key in existing:
                continue
            slot = bucket.get(key)
            if slot is None:
                slot = {"before": b, "after": a, "occurrences": 0, "samples": []}
                bucket[key] = slot
            slot["occurrences"] += 1
            if len(slot["samples"]) < 3:
                slot["samples"].append((before[:60], after[:60]))
    ordered = sorted(bucket.values(), key=lambda x: (-x["occurrences"], x["before"]))
    return ordered[:MAX_RULES_PER_CALL]


# 防膨脹預設參數（輪 C）— 必須定義在 RuleStore 之前，
# 因為 class 內多個方法把它們當預設參數，def 執行當下就會求值。
DEFAULT_CAP_PER_DOMAIN = 100      # 每個領域 active 上限
DEFAULT_FREEZE_DAYS = 90          # 超過 N 天未使用 → 冷凍
MERGE_SIMILARITY_THRESHOLD = 0.86 # SequenceMatcher ratio ≥ 此值且 after 完全相同 → 合併

# 規則一律綁專案：未選專案時使用預設庫 id
DEFAULT_PROJECT_ID = "_default"
DEFAULT_PROJECT_LABEL = "預設（未選專案）"


def normalize_project_id(project_id: str | None) -> str:
    pid = (project_id or "").strip()
    return pid if pid else DEFAULT_PROJECT_ID


# ─────────────────────────────────────────────────────────────
# RuleStore：規則庫的存取
# ─────────────────────────────────────────────────────────────

class RuleStore:
    """個人化規則庫。檔案格式 JSON，schema version 2（相容 v1 遷移）。"""

    SCHEMA_VERSION = 2

    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: dict = {
            "version": self.SCHEMA_VERSION,
            "rules": [],
            "rejected_pairs": [],  # 永久忽略的 before→after
        }
        if self.path.exists():
            self.load()

    # ── 載入 / 存檔 ────────────────────────────────────────
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except Exception:
            # 檔案損毀就視為空，避免整個 App 啟動失敗
            self._data = {"version": self.SCHEMA_VERSION, "rules": [], "rejected_pairs": []}
            return
        if not isinstance(raw, dict):
            self._data = {"version": self.SCHEMA_VERSION, "rules": [], "rejected_pairs": []}
            return
        old_ver = int(raw.get("version", 1) or 1)
        rules = [self._sanitise_rule(r) for r in raw.get("rules", []) if isinstance(r, dict)]
        # v1 → v2：active + domain，保留原採納統計
        if old_ver < 2:
            for r in rules:
                r["state"] = r.get("state") or "active"
                r["created_by"] = "migrated"
                # 舊 adopted_count 視為 model_follow，不冒充 human
                r["model_follow_count"] = int(r.get("model_follow_count") or r.get("adopted_count") or 0)
                r["human_accept_count"] = int(r.get("human_accept_count") or 0)
                r["human_reject_count"] = int(r.get("human_reject_count") or 0)
                r["manual_confirm_count"] = int(r.get("manual_confirm_count") or 0)
        # 一律歸專案：舊 domain/global 規則遷入預設專案庫
        for r in rules:
            st = (r.get("scope_type") or "").lower()
            sid = (r.get("scope_id") or "").strip()
            if st == "project" and sid:
                r["scope_type"] = "project"
                r["scope_id"] = sid
            else:
                r["scope_type"] = "project"
                r["scope_id"] = DEFAULT_PROJECT_ID
        rejected = []
        for item in raw.get("rejected_pairs") or []:
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                rejected.append([str(item[0]), str(item[1]), str(item[2])])
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                # 舊格式 [before, after] → 歸預設專案
                rejected.append([DEFAULT_PROJECT_ID, str(item[0]), str(item[1])])
            elif isinstance(item, str) and "→" in item:
                b, a = item.split("→", 1)
                rejected.append([DEFAULT_PROJECT_ID, b, a])
        self._data = {
            "version": self.SCHEMA_VERSION,
            "rules": rules,
            "rejected_pairs": rejected,
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _sanitise_rule(rule: dict) -> dict:
        state = str(rule.get("state") or "active").lower()
        if state not in ("active", "frozen", "candidate", "rejected"):
            state = "active"
        # 規則一律綁專案（一專案一規則庫）
        scope_type = "project"
        domain = str(rule.get("domain") or "通用").strip() or "通用"
        scope_id = normalize_project_id(rule.get("scope_id") or rule.get("project_id"))
        created_by = str(rule.get("created_by") or rule.get("source") or "manual").lower()
        if created_by in ("auto", "srt_editor_export"):
            created_by = "suggested"
        if created_by not in ("manual", "suggested", "migrated"):
            created_by = "manual"
        human_accept = int(rule.get("human_accept_count") or 0)
        human_reject = int(rule.get("human_reject_count") or 0)
        model_follow = int(rule.get("model_follow_count") or rule.get("adopted_count") or 0)
        model_ignore = int(rule.get("model_ignore_count") or rule.get("rejected_count") or 0)
        # confidence：以人類確認為主，模型遵循為輔
        conf = rule.get("confidence")
        if conf is None:
            total_h = human_accept + human_reject
            conf = (human_accept / total_h) if total_h else min(0.5, 0.1 + model_follow * 0.02)
        try:
            conf = float(conf)
        except Exception:
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        return {
            "id": str(rule.get("id") or uuid.uuid4()),
            "before": str(rule.get("before") or "").strip(),
            "after": str(rule.get("after") or "").strip(),
            "context_hint": str(rule.get("context_hint") or "").strip(),
            "domain": domain,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "project_id": scope_id,
            "note": str(rule.get("note") or "").strip(),
            "created_at": str(rule.get("created_at") or _dt.datetime.now().isoformat(timespec="seconds")),
            "last_used_at": str(rule.get("last_used_at") or ""),
            "last_confirmed_at": str(rule.get("last_confirmed_at") or ""),
            # 向後相容欄位（UI 舊顯示）
            "adopted_count": model_follow,
            "rejected_count": model_ignore,
            "model_follow_count": model_follow,
            "model_ignore_count": model_ignore,
            "human_accept_count": human_accept,
            "human_reject_count": human_reject,
            "manual_confirm_count": int(rule.get("manual_confirm_count") or 0),
            "evidence_event_ids": list(rule.get("evidence_event_ids") or [])[:40],
            "confidence": conf,
            "enabled": bool(rule.get("enabled", True)),
            "source": str(rule.get("source") or "auto"),
            "created_by": created_by,
            "state": state,
            "pause_reason": str(rule.get("pause_reason") or ""),
        }

    # ── 查詢 ──────────────────────────────────────────────
    @property
    def rules(self) -> list[dict]:
        return list(self._data["rules"])

    def project_id_of(self, rule: dict) -> str:
        return normalize_project_id(rule.get("project_id") or rule.get("scope_id"))

    def by_project(self, project_id: str | None, *, include_rejected: bool = False) -> list[dict]:
        """只回傳指定專案的規則（一專案一規則庫）。"""
        pid = normalize_project_id(project_id)
        out = []
        for r in self._data["rules"]:
            if self.project_id_of(r) != pid:
                continue
            if not include_rejected and r.get("state") == "rejected":
                continue
            out.append(r)
        return out

    def existing_keys(self, project_id: str | None = None) -> set[tuple[str, str]]:
        if project_id is None:
            rules = self._data["rules"]
        else:
            rules = self.by_project(project_id, include_rejected=True)
        return {(r["before"], r["after"]) for r in rules}

    def find(self, before: str, after: str, project_id: str | None = None) -> dict | None:
        b = _normalise(before)
        a = _normalise(after)
        pid = None if project_id is None else normalize_project_id(project_id)
        for r in self._data["rules"]:
            if r["before"] == b and r["after"] == a:
                if pid is not None and self.project_id_of(r) != pid:
                    continue
                return r
        return None

    def by_domain(self, domain: str | None = None, enabled_only: bool = True) -> list[dict]:
        out = []
        for r in self._data["rules"]:
            if enabled_only and not r.get("enabled", True):
                continue
            if domain and r.get("domain") != domain:
                continue
            out.append(r)
        return out

    # ── 寫入 ──────────────────────────────────────────────
    def add(
        self,
        before: str,
        after: str,
        *,
        domain: str = "通用",
        context_hint: str = "",
        note: str = "",
        source: str = "auto",
        scope_type: str = "project",
        scope_id: str = "",
        project_id: str = "",
        state: str = "active",
        created_by: str = "",
        evidence_event_ids: list | None = None,
        confidence: float | None = None,
    ) -> dict:
        """新增規則到指定專案庫。同專案內 (before, after) 已存在則更新並回傳。"""
        b = _normalise(before)
        a = _normalise(after)
        if not b or not a:
            raise ValueError("before / after 不可為空")
        pid = normalize_project_id(project_id or scope_id)
        existing = self.find(b, a, project_id=pid)
        if existing is not None:
            existing["domain"] = domain or existing.get("domain", "通用")
            if context_hint:
                existing["context_hint"] = context_hint
            if note:
                existing["note"] = note
            existing["scope_type"] = "project"
            existing["scope_id"] = pid
            existing["project_id"] = pid
            existing["enabled"] = True
            if state:
                existing["state"] = state
            return existing
        rule = self._sanitise_rule({
            "before": b,
            "after": a,
            "domain": domain or "通用",
            "context_hint": context_hint,
            "note": note,
            "source": source,
            "scope_type": "project",
            "scope_id": pid,
            "project_id": pid,
            "state": state or "active",
            "created_by": created_by or ("suggested" if source not in ("manual", "") else "manual"),
            "evidence_event_ids": evidence_event_ids or [],
            "confidence": confidence,
        })
        self._data["rules"].append(rule)
        return rule

    def rejected_pair_keys(self, project_id: str | None = None) -> set[str]:
        """回傳 before→after 字串集合；可限單一專案。"""
        pid = None if project_id is None else normalize_project_id(project_id)
        out = set()
        for pair in self._data.get("rejected_pairs") or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 3:
                p_id, b, a = str(pair[0]), str(pair[1]), str(pair[2])
                if pid is not None and normalize_project_id(p_id) != pid:
                    continue
                out.add(f"{b}→{a}")
            elif isinstance(pair, (list, tuple)) and len(pair) >= 2:
                if pid is not None and pid != DEFAULT_PROJECT_ID:
                    continue
                out.add(f"{pair[0]}→{pair[1]}")
        return out

    def reject_pair_permanently(self, before: str, after: str, project_id: str | None = None) -> None:
        b, a = _normalise(before), _normalise(after)
        if not b or not a:
            return
        pid = normalize_project_id(project_id)
        pairs = self._data.setdefault("rejected_pairs", [])
        key = [pid, b, a]
        if key not in pairs:
            pairs.append(key)
        existing = self.find(b, a, project_id=pid)
        if existing is not None:
            existing["state"] = "rejected"
            existing["enabled"] = False

    def mark_human_accept(self, rule_id: str) -> None:
        for r in self._data["rules"]:
            if r.get("id") == rule_id:
                r["human_accept_count"] = int(r.get("human_accept_count") or 0) + 1
                r["manual_confirm_count"] = int(r.get("manual_confirm_count") or 0) + 1
                r["last_confirmed_at"] = _dt.datetime.now().isoformat(timespec="seconds")
                total = r["human_accept_count"] + int(r.get("human_reject_count") or 0)
                r["confidence"] = r["human_accept_count"] / total if total else r.get("confidence", 0.5)
                return

    def mark_human_reject(self, rule_id: str) -> None:
        for r in self._data["rules"]:
            if r.get("id") == rule_id:
                r["human_reject_count"] = int(r.get("human_reject_count") or 0) + 1
                total = int(r.get("human_accept_count") or 0) + r["human_reject_count"]
                r["confidence"] = (int(r.get("human_accept_count") or 0) / total) if total else 0.0
                return

    def unfreeze(self, rule_id: str) -> bool:
        for r in self._data["rules"]:
            if r.get("id") == rule_id:
                r["state"] = "active"
                r["enabled"] = True
                r["pause_reason"] = ""
                return True
        return False

    def remove(self, rule_id: str) -> bool:
        before = len(self._data["rules"])
        self._data["rules"] = [r for r in self._data["rules"] if r.get("id") != rule_id]
        return len(self._data["rules"]) != before

    def set_enabled(self, rule_id: str, enabled: bool) -> bool:
        for r in self._data["rules"]:
            if r.get("id") == rule_id:
                r["enabled"] = bool(enabled)
                return True
        return False

    def mark_adopted(self, rule_id: str) -> None:
        for r in self._data["rules"]:
            if r.get("id") == rule_id:
                r["adopted_count"] = int(r.get("adopted_count", 0)) + 1
                r["last_used_at"] = _dt.datetime.now().isoformat(timespec="seconds")
                return

    def mark_rejected(self, rule_id: str) -> None:
        for r in self._data["rules"]:
            if r.get("id") == rule_id:
                r["rejected_count"] = int(r.get("rejected_count", 0)) + 1
                return

    # ── 輪 C：冷凍 / 解凍 / 合併 / 上限 ───────────────
    def set_state(self, rule_id: str, state: str) -> bool:
        state = (state or "active").lower()
        if state not in ("active", "frozen", "candidate", "rejected"):
            state = "active"
        for r in self._data["rules"]:
            if r.get("id") == rule_id:
                r["state"] = state
                if state in ("frozen", "rejected"):
                    r["enabled"] = False
                return True
        return False

    def freeze_unused(self, days: int = DEFAULT_FREEZE_DAYS) -> int:
        """超過 days 天未使用的 active 規則 → frozen。回傳冷凍幾條。"""
        cutoff = _dt.datetime.now() - _dt.timedelta(days=max(1, days))
        frozen = 0
        for r in self._data["rules"]:
            if r.get("state", "active") != "active":
                continue
            last = r.get("last_used_at") or ""
            created = r.get("created_at") or ""
            # 從未被採納過就用建立時間作為基準
            ref = last or created
            try:
                ts = _dt.datetime.fromisoformat(ref)
            except Exception:
                continue
            if ts >= cutoff:
                continue
            # 從未採納（adopted_count == 0）且超過時間 → 冷凍
            # 採納過但長期未被觸發 → 冷凍
            r["state"] = "frozen"
            frozen += 1
        return frozen

    def enforce_domain_cap(self, cap: int = DEFAULT_CAP_PER_DOMAIN) -> int:
        """每個領域只保留 cap 個 active；超出的依採納分數最低者冷凍。回傳冷凍幾條。"""
        by_dom: dict[str, list[dict]] = defaultdict(list)
        for r in self._data["rules"]:
            if r.get("state", "active") == "active":
                by_dom[r.get("domain", "通用")].append(r)
        frozen = 0
        for dom, rules in by_dom.items():
            if len(rules) <= cap:
                continue
            rules.sort(key=_rule_strength, reverse=True)
            for r in rules[cap:]:
                r["state"] = "frozen"
                frozen += 1
        return frozen

    def merge_similar(self, threshold: float = MERGE_SIMILARITY_THRESHOLD) -> int:
        """
        合併「after 完全相同 + before 高相似」的規則。
        保留採納分數較高（或較新）的，把另一條的計數加進來再刪除。
        回傳合併幾條。
        """
        by_after: dict[str, list[dict]] = defaultdict(list)
        for r in self._data["rules"]:
            if not (r.get("after") or "").strip():
                continue
            by_after[r["after"]].append(r)
        merged_ids: set[str] = set()
        for after, group in by_after.items():
            if len(group) < 2:
                continue
            # 兩兩比對 before
            i = 0
            while i < len(group):
                base = group[i]
                if base.get("id") in merged_ids:
                    i += 1
                    continue
                j = i + 1
                while j < len(group):
                    other = group[j]
                    if other.get("id") in merged_ids:
                        j += 1
                        continue
                    ratio = difflib.SequenceMatcher(
                        a=base.get("before") or "",
                        b=other.get("before") or "",
                        autojunk=False,
                    ).ratio()
                    if ratio < threshold:
                        j += 1
                        continue
                    # 選保留者
                    keep, drop = base, other
                    if _rule_strength(other) > _rule_strength(base):
                        keep, drop = other, base
                    keep["adopted_count"] = int(keep.get("adopted_count", 0)) + int(drop.get("adopted_count", 0))
                    keep["rejected_count"] = int(keep.get("rejected_count", 0)) + int(drop.get("rejected_count", 0))
                    # 採用較新 last_used
                    last_k = keep.get("last_used_at") or ""
                    last_d = drop.get("last_used_at") or ""
                    if last_d > last_k:
                        keep["last_used_at"] = last_d
                    merged_ids.add(drop.get("id"))
                    # base 可能變了；繼續往下找
                    if keep is other:
                        base = other
                    j += 1
                i += 1
        if merged_ids:
            self._data["rules"] = [r for r in self._data["rules"] if r.get("id") not in merged_ids]
        return len(merged_ids)

    def summarise_state(self) -> dict:
        active = sum(1 for r in self._data["rules"] if r.get("state", "active") == "active")
        frozen = sum(1 for r in self._data["rules"] if r.get("state", "active") == "frozen")
        return {"total": len(self._data["rules"]), "active": active, "frozen": frozen}


# ─────────────────────────────────────────────────────────────
# 從 edit history 讀取本次匯出涵蓋的修改
# ─────────────────────────────────────────────────────────────

def iter_edits_for_input(history_path: Path, input_path: str, since: _dt.datetime | None = None) -> list[dict]:
    """
    讀 srt_edit_history.jsonl，過濾出指定 input 檔的修改紀錄。
    since：只取這個時間點以後的（用來限制「本次匯出產生的修改」）。
    """
    if not history_path.exists():
        return []
    target = _normalise(input_path)
    out: list[dict] = []
    try:
        for line in history_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            row_inp = _normalise(str(row.get("input") or ""))
            if target and row_inp != target:
                continue
            if since is not None:
                try:
                    ts = _dt.datetime.fromisoformat(str(row.get("time") or ""))
                except Exception:
                    ts = None
                if ts is None or ts < since:
                    continue
            out.append(row)
    except Exception:
        return out
    return out


# ─────────────────────────────────────────────────────────────
# 輪 B：規則注入 prompt 與採納率追蹤
# ─────────────────────────────────────────────────────────────

# 規則注入的硬上限，避免 prompt 過長吃 token
MAX_RULE_SECTION_CHARS = 1500
MAX_RULES_INJECTED = 30


def _rule_strength(rule: dict) -> tuple:
    """規則重要性：人類確認 > 信心 > 模型遵循 > 最近使用。"""
    human = int(rule.get("human_accept_count") or 0) - int(rule.get("human_reject_count") or 0)
    conf = float(rule.get("confidence") or 0)
    model = int(rule.get("model_follow_count") or rule.get("adopted_count") or 0)
    last = rule.get("last_confirmed_at") or rule.get("last_used_at") or rule.get("created_at") or ""
    return (human, conf, model, last)


def select_rules_for_prompt(
    store: "RuleStore",
    *,
    domain: str | None = None,
    project_id: str = "",
    series_id: str = "",
    top_k: int = MAX_RULES_INJECTED,
    max_chars: int = MAX_RULE_SECTION_CHARS,
) -> list[dict]:
    """挑選要塞進 system prompt 的規則。

    一專案一規則庫：只取「目前專案」的 enabled + active 規則。
    未傳 project_id 時使用預設庫 DEFAULT_PROJECT_ID。
    """
    pid = normalize_project_id(project_id)
    enabled = [
        r for r in store.by_project(pid)
        if r.get("enabled", True) and r.get("state", "active") == "active"
    ]
    if not enabled:
        return []
    # domain 參數僅作排序加權，不再跨專案混入
    preferred = []
    others = []
    for r in enabled:
        d = r.get("domain") or "通用"
        if domain and d == domain:
            preferred.append(r)
        else:
            others.append(r)
    for bucket in (preferred, others):
        bucket.sort(key=_rule_strength, reverse=True)
    ordered = (preferred + others)[: max(1, top_k)]

    if max_chars <= 0:
        return ordered
    out: list[dict] = []
    total = 0
    for r in ordered:
        line_cost = len(r.get("before") or "") + len(r.get("after") or "") + 24
        if total + line_cost > max_chars:
            break
        out.append(r)
        total += line_cost
    return out


def build_rules_section(rules: list[dict]) -> str:
    """把規則清單格式化成可貼進 system prompt 的中文段落。"""
    if not rules:
        return ""
    lines = [
        "",
        "【個人化規則（使用者偏好替換，請優先套用）】",
        "凡輸入文字中出現左側寫法，請改為右側寫法；若上下文明顯衝突可保留原文。",
    ]
    for r in rules:
        b = (r.get("before") or "").strip()
        a = (r.get("after") or "").strip()
        if not b or not a:
            continue
        human = int(r.get("human_accept_count") or 0)
        model = int(r.get("model_follow_count") or r.get("adopted_count") or 0)
        if human:
            suffix = f"（人類確認 {human}）"
        elif model:
            suffix = f"（模型曾遵循 {model}）"
        else:
            suffix = ""
        lines.append(f"- 「{b}」→「{a}」{suffix}")
    lines.append("")
    return "\n".join(lines)


def track_rule_adoption(
    store: "RuleStore",
    original_text: str,
    response_text: str,
    rules_used: list[dict] | None = None,
    *,
    persist: bool = True,
) -> dict:
    """
    比對 LLM 輸出 vs 輸入，只更新「模型遵循度」，不計入人類採納。

    判定：
      - before 在 original、after 在 response 增加 → model_follow
      - before 仍在 response → model_ignore
      - before 不在 original：跳過

    回傳 {rule_id: "followed" | "ignored"}。
    """
    rules = rules_used if rules_used is not None else [r for r in store.rules if r.get("enabled", True)]
    if not rules or not original_text:
        return {}
    orig = original_text
    resp = response_text or ""
    result: dict[str, str] = {}
    for r in rules:
        b = (r.get("before") or "").strip()
        a = (r.get("after") or "").strip()
        rid = r.get("id") or ""
        if not b or not a or not rid:
            continue
        if b not in orig:
            continue
        orig_b = orig.count(b)
        resp_b = resp.count(b)
        orig_a = orig.count(a)
        resp_a = resp.count(a)
        if resp_b < orig_b and resp_a > orig_a:
            # 模型遵循：更新 model_follow，同步舊 adopted_count 欄位
            for item in store._data["rules"]:
                if item.get("id") == rid:
                    item["model_follow_count"] = int(item.get("model_follow_count") or 0) + 1
                    item["adopted_count"] = item["model_follow_count"]
                    item["last_used_at"] = _dt.datetime.now().isoformat(timespec="seconds")
                    break
            result[rid] = "followed"
        elif resp_b >= orig_b:
            for item in store._data["rules"]:
                if item.get("id") == rid:
                    item["model_ignore_count"] = int(item.get("model_ignore_count") or 0) + 1
                    item["rejected_count"] = item["model_ignore_count"]
                    break
            result[rid] = "ignored"
    if persist and result:
        try:
            store.save()
        except Exception:
            pass
    return result


__all__ = [
    "DEFAULT_DOMAINS",
    "DEFAULT_PROJECT_ID",
    "DEFAULT_PROJECT_LABEL",
    "MAX_RULES_INJECTED",
    "MAX_RULE_SECTION_CHARS",
    "RuleStore",
    "build_rules_section",
    "extract_candidates",
    "iter_edits_for_input",
    "normalize_project_id",
    "select_rules_for_prompt",
    "summarise_candidates",
    "track_rule_adoption",
]
