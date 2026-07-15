# -*- coding: utf-8 -*-
"""領域 Prompt 模板與自訂詞庫（v2.4.5）。

資料只存本機；注入時由主程式以 has_feature() 閘門控制。
"""

from __future__ import annotations

import datetime as _dt
import json
import uuid
from pathlib import Path

BUILTIN_TEMPLATES: dict[str, dict] = {
    "訪談": {
        "id": "builtin_interview",
        "name": "訪談",
        "body": (
            "這是訪談／對談字幕。請保留口語節奏，修正同音錯字與專有名詞，"
            "不要把問答改成書面摘要，不要合併不同講者的句子。"
        ),
    },
    "新聞": {
        "id": "builtin_news",
        "name": "新聞",
        "body": (
            "這是新聞口播字幕。請使用台灣繁體用語，修正機構名、地名與職稱，"
            "保持客觀陳述語氣，避免口語贅詞擴寫。"
        ),
    },
    "教學": {
        "id": "builtin_teach",
        "name": "教學",
        "body": (
            "這是教學／課程字幕。請保留步驟與因果說明，修正術語拼寫，"
            "不要刪除對學習有用的例子與提醒。"
        ),
    },
    "科技": {
        "id": "builtin_tech",
        "name": "科技",
        "body": (
            "這是科技／產品討論字幕。請正確保留產品名、品牌、型號與英文專有名詞，"
            "台灣常用譯名優先，不要把英文專有名詞硬翻成中文。"
        ),
    },
    "通用": {
        "id": "builtin_general",
        "name": "通用",
        "body": (
            "請在不改變原意的前提下，修正錯別字、簡體字與明顯同音誤植，"
            "維持原句長度與語氣。"
        ),
    },
}


def _iso_now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _safe(text, limit: int = 2000) -> str:
    s = str(text or "").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


class TemplateStore:
    """自訂領域模板（可覆寫內建 body）。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._data = {"version": 1, "templates": [], "active_domain": "通用"}
        if self.path.exists():
            self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        items = []
        for t in raw.get("templates") or []:
            if isinstance(t, dict) and (t.get("name") or t.get("domain")):
                items.append({
                    "id": str(t.get("id") or uuid.uuid4()),
                    "name": _safe(t.get("name") or t.get("domain"), 40),
                    "body": _safe(t.get("body"), 2000),
                    "created_at": str(t.get("created_at") or _iso_now()),
                })
        self._data = {
            "version": int(raw.get("version") or 1),
            "templates": items,
            "active_domain": _safe(raw.get("active_domain") or "通用", 40),
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def active_domain(self) -> str:
        return str(self._data.get("active_domain") or "通用")

    def set_active_domain(self, domain: str) -> None:
        self._data["active_domain"] = _safe(domain, 40) or "通用"

    def list_domains(self) -> list[str]:
        names = list(BUILTIN_TEMPLATES.keys())
        for t in self._data.get("templates") or []:
            n = t.get("name")
            if n and n not in names:
                names.append(n)
        return names

    def get_body(self, domain: str | None = None) -> str:
        domain = (domain or self.active_domain or "通用").strip()
        for t in self._data.get("templates") or []:
            if t.get("name") == domain and t.get("body"):
                return t["body"]
        builtin = BUILTIN_TEMPLATES.get(domain) or BUILTIN_TEMPLATES.get("通用")
        return (builtin or {}).get("body") or ""

    def upsert(self, name: str, body: str) -> dict:
        name = _safe(name, 40) or "自訂"
        body = _safe(body, 2000)
        for t in self._data["templates"]:
            if t.get("name") == name:
                t["body"] = body
                return t
        item = {"id": str(uuid.uuid4()), "name": name, "body": body, "created_at": _iso_now()}
        self._data["templates"].append(item)
        return item

    def remove(self, name: str) -> bool:
        before = len(self._data["templates"])
        self._data["templates"] = [t for t in self._data["templates"] if t.get("name") != name]
        return len(self._data["templates"]) != before

    def build_section(self, domain: str | None = None) -> str:
        body = self.get_body(domain)
        if not body:
            return ""
        d = domain or self.active_domain
        return f"\n【領域校對指引：{d}】\n{body}\n"


class DictionaryStore:
    """自訂詞庫：姓名、品牌、地名、術語。"""

    CATEGORIES = ("姓名", "品牌", "地名", "術語", "其他")

    def __init__(self, path: Path):
        self.path = Path(path)
        self._data = {"version": 1, "entries": []}
        if self.path.exists():
            self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        entries = []
        for e in raw.get("entries") or []:
            if not isinstance(e, dict):
                continue
            wrong = _safe(e.get("wrong") or e.get("from") or "", 40)
            right = _safe(e.get("right") or e.get("to") or "", 40)
            if not wrong or not right or wrong == right:
                continue
            entries.append({
                "id": str(e.get("id") or uuid.uuid4()),
                "wrong": wrong,
                "right": right,
                "category": _safe(e.get("category") or "其他", 20),
                "scope_type": _safe(e.get("scope_type") or "global", 20),
                "scope_id": _safe(e.get("scope_id"), 80),
                "enabled": bool(e.get("enabled", True)),
                "created_at": str(e.get("created_at") or _iso_now()),
            })
        self._data = {"version": int(raw.get("version") or 1), "entries": entries}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def entries(self) -> list[dict]:
        return list(self._data.get("entries") or [])

    def add(
        self,
        wrong: str,
        right: str,
        *,
        category: str = "其他",
        scope_type: str = "global",
        scope_id: str = "",
    ) -> dict:
        item = {
            "id": str(uuid.uuid4()),
            "wrong": _safe(wrong, 40),
            "right": _safe(right, 40),
            "category": _safe(category, 20) or "其他",
            "scope_type": _safe(scope_type, 20) or "global",
            "scope_id": _safe(scope_id, 80),
            "enabled": True,
            "created_at": _iso_now(),
        }
        if not item["wrong"] or not item["right"]:
            raise ValueError("詞庫項目不可為空")
        # 去重
        for e in self._data["entries"]:
            if e["wrong"] == item["wrong"] and e["right"] == item["right"]:
                e["enabled"] = True
                e["category"] = item["category"]
                e["scope_type"] = item["scope_type"]
                e["scope_id"] = item["scope_id"]
                return e
        self._data["entries"].append(item)
        return item

    def remove(self, entry_id: str) -> bool:
        before = len(self._data["entries"])
        self._data["entries"] = [e for e in self._data["entries"] if e.get("id") != entry_id]
        return len(self._data["entries"]) != before

    def set_enabled(self, entry_id: str, enabled: bool) -> bool:
        for e in self._data["entries"]:
            if e.get("id") == entry_id:
                e["enabled"] = bool(enabled)
                return True
        return False

    def select_for_prompt(
        self,
        *,
        project_id: str = "",
        series_id: str = "",
        domain: str = "",
        top_k: int = 40,
    ) -> list[dict]:
        out = []
        for e in self._data["entries"]:
            if not e.get("enabled", True):
                continue
            st = e.get("scope_type") or "global"
            sid = e.get("scope_id") or ""
            if st == "project" and sid and sid != project_id:
                continue
            if st == "series" and sid and sid != series_id:
                continue
            if st == "domain" and sid and sid != domain:
                continue
            out.append(e)
            if len(out) >= top_k:
                break
        return out

    def build_section(self, entries: list[dict] | None = None) -> str:
        items = entries if entries is not None else self.select_for_prompt()
        if not items:
            return ""
        lines = [
            "",
            "【自訂詞庫（請優先套用）】",
            "左側寫法請改為右側；若上下文衝突可保留原文。",
        ]
        for e in items:
            lines.append(f"- 「{e['wrong']}」→「{e['right']}」（{e.get('category') or '其他'}）")
        lines.append("")
        return "\n".join(lines)

    def summary_for_ui(self, entries: list[dict] | None = None) -> str:
        items = entries if entries is not None else [e for e in self.entries if e.get("enabled", True)]
        if not items:
            return "（無詞庫項目）"
        return "；".join(f"{e['wrong']}→{e['right']}" for e in items[:12]) + ("…" if len(items) > 12 else "")


__all__ = [
    "BUILTIN_TEMPLATES",
    "DictionaryStore",
    "TemplateStore",
]
