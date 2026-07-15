# -*- coding: utf-8 -*-
"""SanWich 學習閉環：人工回饋事件、專案／系列設定、候選規則彙整。

設計原則：
- 學習訊號只來自明確人工行為，不把「模型有照規則輸出」當成人類確認。
- 資料只存在本機 %APPDATA%/SanWich/learning/，不上傳。
- 事件為 append-only JSONL；規則升級需人工確認（候選門檻）。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable

# 行為代碼（與開發計畫一致）
ACTION_ACCEPT_AI = "accept_ai"
ACTION_RESTORE_ORIGINAL = "restore_original"
ACTION_MANUAL_EDIT = "manual_edit"
ACTION_SKIP = "skip"

VALID_ACTIONS = frozenset({
    ACTION_ACCEPT_AI,
    ACTION_RESTORE_ORIGINAL,
    ACTION_MANUAL_EDIT,
    ACTION_SKIP,
})

# 同一替換在相同系列／領域被人工確認至少 N 次才主動建議
DEFAULT_CANDIDATE_THRESHOLD = 2
# 全域規則門檻較高
GLOBAL_CANDIDATE_THRESHOLD = 4
# 連續還原幾次後暫停規則
CONSECUTIVE_RESTORE_PAUSE = 2

SCOPE_TYPES = ("project", "series", "domain", "global")


def appdata_sanwich() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "SanWich"
    if sys_platform_is_darwin():
        return Path.home() / "Library" / "Application Support" / "SanWich"
    return Path.home() / ".config" / "SanWich"


def sys_platform_is_darwin() -> bool:
    import sys
    return sys.platform == "darwin"


def learning_dir(base: Path | None = None) -> Path:
    root = Path(base) if base is not None else appdata_sanwich()
    path = root / "learning"
    path.mkdir(parents=True, exist_ok=True)
    return path


def feedback_path(base: Path | None = None) -> Path:
    return learning_dir(base) / "review_feedback.jsonl"


def edit_history_path(base: Path | None = None) -> Path:
    return learning_dir(base) / "srt_edit_history.jsonl"


def project_profiles_path(base: Path | None = None) -> Path:
    root = Path(base) if base is not None else appdata_sanwich()
    root.mkdir(parents=True, exist_ok=True)
    return root / "project_profiles.json"


def supplement_history_path(base: Path | None = None) -> Path:
    root = Path(base) if base is not None else appdata_sanwich()
    root.mkdir(parents=True, exist_ok=True)
    return root / "supplement_history.json"


def file_fingerprint(path: str | Path | None, max_bytes: int = 2 * 1024 * 1024) -> str:
    """內容指紋：路徑 stem + size + 前段 hash；不保存完整媒體。"""
    if not path:
        return ""
    p = Path(path)
    try:
        if not p.exists() or not p.is_file():
            return f"name:{p.name}"
        st = p.stat()
        h = hashlib.sha256()
        h.update(p.name.encode("utf-8", errors="replace"))
        h.update(str(st.st_size).encode("ascii"))
        h.update(str(int(st.st_mtime)).encode("ascii"))
        with p.open("rb") as fh:
            remaining = max_bytes
            while remaining > 0:
                chunk = fh.read(min(65536, remaining))
                if not chunk:
                    break
                h.update(chunk)
                remaining -= len(chunk)
        return h.hexdigest()[:32]
    except Exception:
        return f"name:{p.name}"


def _iso_now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _safe_str(value, limit: int = 800) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def redact_path(path: str | Path | None) -> str:
    """事件中只留檔名，避免完整本機絕對路徑外流。"""
    if not path:
        return ""
    return Path(path).name


class SupplementHistoryStore:
    """補充資料的本機最近使用紀錄；不保存媒體路徑。"""

    MAX_ENTRIES = 20

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else supplement_history_path()
        self.entries: list[dict] = []
        if self.path.exists():
            self.load()

    @staticmethod
    def _sanitise(item: dict) -> dict | None:
        text = str(item.get("text") or "").strip()
        if not text:
            return None
        return {
            "text": text[:8000],
            "project_id": _safe_str(item.get("project_id"), 120),
            "project_name": _safe_str(item.get("project_name"), 80) or "預設",
            "updated_at": str(item.get("updated_at") or _iso_now()),
        }

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
            items = raw.get("entries", []) if isinstance(raw, dict) else []
        except Exception:
            items = []
        entries = []
        for item in items:
            if isinstance(item, dict):
                clean = self._sanitise(item)
                if clean is not None:
                    entries.append(clean)
        self.entries = entries[: self.MAX_ENTRIES]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"version": 1, "entries": self.entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def remember(self, text: str, *, project_id: str = "", project_name: str = "預設") -> bool:
        clean_text = str(text or "").strip()
        if not clean_text:
            return False
        entry = self._sanitise({
            "text": clean_text,
            "project_id": project_id,
            "project_name": project_name,
            "updated_at": _iso_now(),
        })
        if entry is None:
            return False
        self.entries = [row for row in self.entries if row.get("text") != clean_text]
        self.entries.insert(0, entry)
        self.entries = self.entries[: self.MAX_ENTRIES]
        self.save()
        return True

    def clear(self) -> None:
        self.entries = []
        self.save()


def migrate_edit_history_once(
    legacy_path: Path,
    target_path: Path | None = None,
    *,
    marker_name: str = ".edit_history_migrated",
) -> dict:
    """把舊 logs/srt_edit_history.jsonl 一次性遷到 APPDATA。不覆寫既有目標。"""
    dest = Path(target_path) if target_path is not None else edit_history_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    marker = dest.parent / marker_name
    result = {"migrated": False, "skipped": True, "source": str(legacy_path), "dest": str(dest), "lines": 0}
    if marker.exists():
        return result
    if dest.exists() and dest.stat().st_size > 0:
        try:
            marker.write_text(_iso_now(), encoding="utf-8")
        except Exception:
            pass
        result["skipped"] = True
        return result
    if not legacy_path.exists():
        try:
            marker.write_text(_iso_now(), encoding="utf-8")
        except Exception:
            pass
        return result
    try:
        shutil.copy2(legacy_path, dest)
        with dest.open("r", encoding="utf-8-sig", errors="ignore") as fh:
            lines = sum(1 for _ in fh)
        marker.write_text(_iso_now(), encoding="utf-8")
        result.update({"migrated": True, "skipped": False, "lines": lines})
    except Exception as exc:
        result["error"] = str(exc)
    return result


class FeedbackStore:
    """人工回饋事件 JSONL 存取。"""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else feedback_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict) -> dict:
        row = self._sanitise_event(event)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def record(
        self,
        *,
        action: str,
        original_text: str = "",
        ai_text: str = "",
        final_text: str = "",
        timecode_start: float | None = None,
        timecode_end: float | None = None,
        input_path: str = "",
        project_id: str = "",
        series_id: str = "",
        domain: str = "通用",
        rule_ids: list[str] | None = None,
        provider: str = "",
        model: str = "",
        app_version: str = "",
        source: str = "quick_compare",
        extra: dict | None = None,
    ) -> dict:
        action = (action or "").strip().lower()
        if action not in VALID_ACTIONS:
            raise ValueError(f"未知行為：{action}")
        event = {
            "event_id": str(uuid.uuid4()),
            "time": _iso_now(),
            "app_version": _safe_str(app_version, 32),
            "action": action,
            "project_id": _safe_str(project_id, 80),
            "series_id": _safe_str(series_id, 80),
            "domain": _safe_str(domain, 40) or "通用",
            "input_name": redact_path(input_path),
            "input_fingerprint": file_fingerprint(input_path) if input_path else "",
            "timecode_start": timecode_start,
            "timecode_end": timecode_end,
            "original_text": _safe_str(original_text),
            "ai_text": _safe_str(ai_text),
            "final_text": _safe_str(final_text),
            "rule_ids": [str(x) for x in (rule_ids or []) if x][:40],
            "provider": _safe_str(provider, 40),
            "model": _safe_str(model, 80),
            "source": _safe_str(source, 40),
        }
        if extra and isinstance(extra, dict):
            # 禁止塞敏感欄位
            for key in ("api_key", "authorization", "token", "password"):
                extra.pop(key, None)
            event["extra"] = {str(k): _safe_str(v, 200) for k, v in list(extra.items())[:20]}
        return self.append(event)

    @staticmethod
    def _sanitise_event(event: dict) -> dict:
        action = str(event.get("action") or ACTION_SKIP).lower()
        if action not in VALID_ACTIONS:
            action = ACTION_SKIP
        return {
            "event_id": str(event.get("event_id") or uuid.uuid4()),
            "time": str(event.get("time") or _iso_now()),
            "app_version": _safe_str(event.get("app_version"), 32),
            "action": action,
            "project_id": _safe_str(event.get("project_id"), 80),
            "series_id": _safe_str(event.get("series_id"), 80),
            "domain": _safe_str(event.get("domain"), 40) or "通用",
            "input_name": redact_path(event.get("input_name") or event.get("input_path") or ""),
            "input_fingerprint": _safe_str(event.get("input_fingerprint"), 64),
            "timecode_start": event.get("timecode_start"),
            "timecode_end": event.get("timecode_end"),
            "original_text": _safe_str(event.get("original_text")),
            "ai_text": _safe_str(event.get("ai_text")),
            "final_text": _safe_str(event.get("final_text")),
            "rule_ids": [str(x) for x in (event.get("rule_ids") or []) if x][:40],
            "provider": _safe_str(event.get("provider"), 40),
            "model": _safe_str(event.get("model"), 80),
            "source": _safe_str(event.get("source"), 40),
            "extra": event.get("extra") if isinstance(event.get("extra"), dict) else {},
        }

    def iter_events(self, *, limit: int | None = None, reverse: bool = False) -> list[dict]:
        if not self.path.exists():
            return []
        rows: list[dict] = []
        try:
            for line in self.path.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(self._sanitise_event(row))
        except Exception:
            return []
        if reverse:
            rows.reverse()
        if limit is not None:
            rows = rows[: max(0, int(limit))]
        return rows

    def count(self) -> int:
        if not self.path.exists():
            return 0
        try:
            return sum(1 for line in self.path.open("r", encoding="utf-8-sig", errors="ignore") if line.strip())
        except Exception:
            return 0

    def clear(self) -> None:
        try:
            if self.path.exists():
                self.path.write_text("", encoding="utf-8")
        except Exception:
            pass

    def privacy_scan(self) -> list[str]:
        """粗略檢查事件檔是否含敏感字樣。"""
        issues: list[str] = []
        if not self.path.exists():
            return issues
        try:
            text = self.path.read_text(encoding="utf-8-sig", errors="ignore")
        except Exception as exc:
            return [f"讀取失敗：{exc}"]
        lowered = text.lower()
        for needle in ("api_key", "authorization", "bearer ", "sk-", "AIza"):
            if needle.lower() in lowered:
                issues.append(f"疑似敏感字樣：{needle}")
        # 完整 Windows 路徑（粗略）
        if ":\\\\" in text or ":/" in text:
            # 允許時間碼中的冒號；只抓像 D:\ 這類
            import re
            if re.search(r"[A-Za-z]:[\\/][^\\/\s\"']+", text):
                issues.append("疑似含完整本機路徑")
        return issues


class ProjectProfileStore:
    """本機專案／系列設定。"""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else project_profiles_path()
        self._data: dict = {"version": 1, "active_id": "", "profiles": []}
        if self.path.exists():
            self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except Exception:
            self._data = {"version": 1, "active_id": "", "profiles": []}
            return
        if not isinstance(raw, dict):
            self._data = {"version": 1, "active_id": "", "profiles": []}
            return
        profiles = []
        for item in raw.get("profiles") or []:
            if isinstance(item, dict):
                profiles.append(self._sanitise(item))
        self._data = {
            "version": int(raw.get("version") or 1),
            # 專案選擇只在本次執行期間有效；重新開啟一律回到「預設」。
            "active_id": "",
            "profiles": profiles,
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(self._data)
        # 不把本次選用的專案寫入磁碟，避免下次啟動沿用。
        payload["active_id"] = ""
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _sanitise(item: dict) -> dict:
        return {
            "id": str(item.get("id") or uuid.uuid4()),
            "name": _safe_str(item.get("name"), 80) or "未命名專案",
            "series_id": _safe_str(item.get("series_id"), 80),
            "series_name": _safe_str(item.get("series_name"), 80),
            "domain": _safe_str(item.get("domain"), 40) or "通用",
            "guests": _safe_str(item.get("guests"), 200),
            "terms": _safe_str(item.get("terms"), 400),
            "prompt_scope": _safe_str(item.get("prompt_scope"), 40) or "domain",
            "notes": _safe_str(item.get("notes"), 400),
            "created_at": str(item.get("created_at") or _iso_now()),
            "updated_at": str(item.get("updated_at") or _iso_now()),
        }

    @property
    def profiles(self) -> list[dict]:
        return list(self._data.get("profiles") or [])

    @property
    def active_id(self) -> str:
        return str(self._data.get("active_id") or "")

    def get_active(self) -> dict | None:
        aid = self.active_id
        if not aid:
            return None
        for p in self.profiles:
            if p.get("id") == aid:
                return p
        return None

    def set_active(self, profile_id: str) -> bool:
        pid = str(profile_id or "")
        if not pid:
            self._data["active_id"] = ""
            return True
        for p in self.profiles:
            if p.get("id") == pid:
                self._data["active_id"] = pid
                return True
        return False

    def upsert(
        self,
        *,
        profile_id: str = "",
        name: str = "未命名專案",
        series_id: str = "",
        series_name: str = "",
        domain: str = "通用",
        guests: str = "",
        terms: str = "",
        prompt_scope: str = "domain",
        notes: str = "",
    ) -> dict:
        now = _iso_now()
        if profile_id:
            for p in self._data["profiles"]:
                if p.get("id") == profile_id:
                    p.update({
                        "name": _safe_str(name, 80) or p.get("name"),
                        "series_id": _safe_str(series_id, 80),
                        "series_name": _safe_str(series_name, 80),
                        "domain": _safe_str(domain, 40) or "通用",
                        "guests": _safe_str(guests, 200),
                        "terms": _safe_str(terms, 400),
                        "prompt_scope": _safe_str(prompt_scope, 40) or "domain",
                        "notes": _safe_str(notes, 400),
                        "updated_at": now,
                    })
                    return p
        profile = self._sanitise({
            "id": profile_id or str(uuid.uuid4()),
            "name": name,
            "series_id": series_id or str(uuid.uuid4())[:8],
            "series_name": series_name or name,
            "domain": domain,
            "guests": guests,
            "terms": terms,
            "prompt_scope": prompt_scope,
            "notes": notes,
            "created_at": now,
            "updated_at": now,
        })
        self._data["profiles"].append(profile)
        if not self._data.get("active_id"):
            self._data["active_id"] = profile["id"]
        return profile

    def remove(self, profile_id: str) -> bool:
        before = len(self._data["profiles"])
        self._data["profiles"] = [p for p in self._data["profiles"] if p.get("id") != profile_id]
        if self._data.get("active_id") == profile_id:
            self._data["active_id"] = self._data["profiles"][0]["id"] if self._data["profiles"] else ""
        return len(self._data["profiles"]) != before

    def context_for_prompt(self) -> str:
        active = self.get_active()
        if not active:
            return ""
        parts = []
        if active.get("name"):
            parts.append(f"專案／節目：{active['name']}")
        if active.get("series_name"):
            parts.append(f"系列：{active['series_name']}")
        if active.get("domain"):
            parts.append(f"領域：{active['domain']}")
        if active.get("guests"):
            parts.append(f"受訪者／固定角色：{active['guests']}")
        if active.get("terms"):
            parts.append(f"固定用語：{active['terms']}")
        if active.get("notes"):
            parts.append(f"備註：{active['notes']}")
        if not parts:
            return ""
        return "【目前專案上下文】\n" + "\n".join(f"- {p}" for p in parts) + "\n"


def _pair_key(before: str, after: str) -> tuple[str, str]:
    return ((before or "").strip(), (after or "").strip())


def extract_pairs_from_texts(before: str, after: str, extract_fn: Callable | None = None) -> list[tuple[str, str]]:
    """用 personal_rules.extract_candidates 或整句替換。"""
    b = (before or "").strip()
    a = (after or "").strip()
    if not b or not a or b == a:
        return []
    if extract_fn is not None:
        try:
            pairs = extract_fn(b, a)
            if pairs:
                return [(str(x[0]), str(x[1])) for x in pairs]
        except Exception:
            pass
    # 整句替換也算候選（長度合理時）
    if 1 <= len(b) <= 40 and 1 <= len(a) <= 40:
        return [(b, a)]
    return []


def aggregate_candidates_from_events(
    events: Iterable[dict],
    *,
    extract_fn: Callable | None = None,
    existing_keys: set[tuple[str, str]] | None = None,
    threshold: int = DEFAULT_CANDIDATE_THRESHOLD,
    reject_ids: set[str] | None = None,
) -> list[dict]:
    """
    從回饋事件彙整候選規則。

    計分：
    - accept_ai / manual_edit：正向 +1
    - restore_original：負向 +1（並抵銷）
    - skip：不計分

    只有正向分數 >= threshold 且 before≠after 才列入候選。
    """
    existing = existing_keys or set()
    rejected = reject_ids or set()
    bucket: dict[tuple[str, str, str], dict] = {}
    # key = (before, after, scope_hint)

    for ev in events:
        action = (ev.get("action") or "").lower()
        if action == ACTION_SKIP:
            continue
        original = ev.get("original_text") or ""
        ai = ev.get("ai_text") or ""
        final = ev.get("final_text") or ""
        domain = (ev.get("domain") or "通用").strip() or "通用"
        series_id = (ev.get("series_id") or "").strip()
        project_id = (ev.get("project_id") or "").strip()
        scope_hint = "series" if series_id else ("project" if project_id else "domain")
        scope_id = series_id or project_id or domain

        pairs: list[tuple[str, str]] = []
        if action == ACTION_ACCEPT_AI:
            pairs = extract_pairs_from_texts(original, final or ai, extract_fn)
            weight = 1
            polarity = 1
        elif action == ACTION_MANUAL_EDIT:
            # 以 AI 或原文 → 最終；手動修改排序權重較高，但門檻仍以「次數」計
            base = ai if ai and ai != final else original
            pairs = extract_pairs_from_texts(base, final, extract_fn)
            if not pairs and original and final and original != final:
                pairs = extract_pairs_from_texts(original, final, extract_fn)
            weight = 2
            polarity = 1
        elif action == ACTION_RESTORE_ORIGINAL:
            pairs = extract_pairs_from_texts(original, ai, extract_fn)
            weight = 1
            polarity = -1
        else:
            continue

        for b, a in pairs:
            key = (b, a)
            if key in existing:
                continue
            cand_key = (b, a, f"{scope_hint}:{scope_id}")
            slot = bucket.get(cand_key)
            if slot is None:
                slot = {
                    "before": b,
                    "after": a,
                    "occurrences": 0,
                    "positive": 0,
                    "negative": 0,
                    "score": 0,
                    "domain": domain,
                    "scope_type": scope_hint,
                    "scope_id": scope_id,
                    "series_id": series_id,
                    "project_id": project_id,
                    "evidence_event_ids": [],
                    "samples": [],
                    "sources": set(),
                }
                bucket[cand_key] = slot
            if polarity > 0:
                # positive / occurrences = 人工確認次數（門檻用）；score 含權重供排序
                slot["positive"] += 1
                slot["occurrences"] += 1
                slot["score"] += weight
            else:
                slot["negative"] += 1
                slot["score"] -= weight
            eid = ev.get("event_id")
            if eid and len(slot["evidence_event_ids"]) < 20:
                slot["evidence_event_ids"].append(eid)
            if len(slot["samples"]) < 3:
                slot["samples"].append((
                    _safe_str(original, 60),
                    _safe_str(final or ai, 60),
                ))
            src = ev.get("input_name") or ""
            if src:
                slot["sources"].add(src)

    out: list[dict] = []
    for slot in bucket.values():
        # 永久拒絕 key
        reject_key = f"{slot['before']}→{slot['after']}"
        if reject_key in rejected:
            continue
        # 全域升級門檻較高；此處 scope 仍是 project/series/domain
        need = threshold
        if slot.get("scope_type") == "global":
            need = max(threshold, GLOBAL_CANDIDATE_THRESHOLD)
        # 門檻看「人工確認次數」，不是單次手動的加權分數
        if slot["positive"] < need or slot["occurrences"] < need:
            continue
        if slot["negative"] >= slot["positive"]:
            continue
        item = dict(slot)
        item["sources"] = sorted(item["sources"])[:8]
        item["confidence"] = round(
            max(0.0, min(1.0, item["score"] / float(need + item["negative"] + 1))),
            3,
        )
        out.append(item)
    out.sort(key=lambda x: (-x["score"], -x["positive"], x["before"]))
    return out[:60]


def apply_feedback_to_rule_health(
    store,
    events: Iterable[dict],
    *,
    consecutive_restore: int = CONSECUTIVE_RESTORE_PAUSE,
) -> dict:
    """
    依人工回饋更新規則的 human_* 計數與暫停狀態。
    store 需提供 rules / find / save / set_state 等介面（personal_rules.RuleStore）。
    回傳摘要。
    """
    # 依規則 before/after 比對事件（rule_ids 優先）
    by_id = {r.get("id"): r for r in getattr(store, "rules", [])}
    restore_streak: dict[str, int] = defaultdict(int)
    summary = {"human_accept": 0, "human_reject": 0, "paused": 0}

    for ev in events:
        action = (ev.get("action") or "").lower()
        rule_ids = list(ev.get("rule_ids") or [])
        original = (ev.get("original_text") or "").strip()
        ai = (ev.get("ai_text") or "").strip()
        final = (ev.get("final_text") or "").strip()

        touched: list[str] = []
        if rule_ids:
            touched = [rid for rid in rule_ids if rid in by_id]
        else:
            # 依 before 片段比對
            for rid, rule in by_id.items():
                b = (rule.get("before") or "").strip()
                a = (rule.get("after") or "").strip()
                if not b or not a:
                    continue
                if action == ACTION_ACCEPT_AI and b in original and a in (final or ai):
                    touched.append(rid)
                elif action == ACTION_RESTORE_ORIGINAL and b in original and a in ai:
                    touched.append(rid)
                elif action == ACTION_MANUAL_EDIT and b in original and a not in final and b in final:
                    # 規則建議的 after 沒被採用
                    touched.append(rid)

        for rid in touched:
            rule = by_id.get(rid)
            if not rule:
                continue
            if action == ACTION_ACCEPT_AI:
                rule["human_accept_count"] = int(rule.get("human_accept_count") or 0) + 1
                rule["manual_confirm_count"] = int(rule.get("manual_confirm_count") or 0) + 1
                rule["last_confirmed_at"] = ev.get("time") or _iso_now()
                restore_streak[rid] = 0
                summary["human_accept"] += 1
            elif action == ACTION_RESTORE_ORIGINAL:
                rule["human_reject_count"] = int(rule.get("human_reject_count") or 0) + 1
                restore_streak[rid] = restore_streak.get(rid, 0) + 1
                summary["human_reject"] += 1
                if restore_streak[rid] >= consecutive_restore:
                    rule["state"] = "frozen"
                    rule["enabled"] = False
                    rule["pause_reason"] = "連續還原"
                    summary["paused"] += 1
            elif action == ACTION_MANUAL_EDIT:
                # 手動改成別的：對該規則視為負向（若 after 未採用）
                a = (rule.get("after") or "").strip()
                if a and a not in final:
                    rule["human_reject_count"] = int(rule.get("human_reject_count") or 0) + 1
                    summary["human_reject"] += 1

    try:
        store.save()
    except Exception:
        pass
    return summary


__all__ = [
    "ACTION_ACCEPT_AI",
    "ACTION_MANUAL_EDIT",
    "ACTION_RESTORE_ORIGINAL",
    "ACTION_SKIP",
    "CONSECUTIVE_RESTORE_PAUSE",
    "DEFAULT_CANDIDATE_THRESHOLD",
    "FeedbackStore",
    "GLOBAL_CANDIDATE_THRESHOLD",
    "ProjectProfileStore",
    "VALID_ACTIONS",
    "aggregate_candidates_from_events",
    "appdata_sanwich",
    "apply_feedback_to_rule_health",
    "edit_history_path",
    "feedback_path",
    "file_fingerprint",
    "learning_dir",
    "migrate_edit_history_once",
    "project_profiles_path",
    "redact_path",
]
