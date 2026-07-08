# -*- coding: utf-8 -*-
"""SanWich 輕量授權管理（信任制）。

原則（見 SUPPORTER_PLAN.md）：
- 不做強制登入、不連網驗證、不做硬體綁定。
- Trial 到期只回到 Free 模式，絕不鎖住 Free 功能。
- 授權任何環節失敗，Free 功能一律照常可用。
- 簽章僅為基本提醒（防君子，不防小人）。

license.json 位置：
  Windows: %APPDATA%/SanWich/license.json
  macOS:   ~/Library/Application Support/SanWich/license.json
  其他:    ~/.config/SanWich/license.json
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

TRIAL_DAYS = 30

# 信任制簽章鹽值：僅用於防止「不小心」手改日期，
# 原始碼公開後任何人都能重算，這是刻意的設計取捨（防君子，不防小人）。
_SALT = b"SanWich-TrustBased-License-v1-2026"

# ── 功能集合：優先讀取同目錄 features.py，失敗用內建備援 ──────────

_FALLBACK_FREE = {
    "single_transcription", "export_srt", "export_txt",
    "basic_ai_proofread", "basic_srt_editor", "find_replace",
    "import_srt", "davinci_tools",
}
_FALLBACK_SUPPORTER = {
    "batch_processing", "quick_compare_full", "custom_rules",
    "diarization", "domain_prompt_templates", "custom_dictionary",
    "supporter_badge", "early_access",
}


def _load_feature_sets():
    try:
        path = Path(__file__).resolve().parent / "features.py"
        ns: dict = {}
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)
        return set(ns["FREE_FEATURES"]), set(ns["SUPPORTER_FEATURES"])
    except Exception:
        return set(_FALLBACK_FREE), set(_FALLBACK_SUPPORTER)


FREE_FEATURES, SUPPORTER_FEATURES = _load_feature_sets()

# ── Debug 覆寫（開發用）──────────────────────────────────────────
# 在主程式資料夾放 debug_edition.txt，內容寫 free / trial / supporter，
# 即可強制以該版本運作；刪除檔案就回復正常授權判斷。
# 此檔已列入 .gitignore，發佈版不會攜帶。

_VALID_OVERRIDES = ("free", "trial", "supporter")


def debug_override() -> str | None:
    """只看第一個非空白、非 # 開頭的行；其餘行可自由寫說明。"""
    try:
        path = Path(__file__).resolve().parent.parent / "debug_edition.txt"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                return line.lower() if line.lower() in _VALID_OVERRIDES else None
    except Exception:
        pass
    return None


# ── 路徑 ─────────────────────────────────────────────────────────


def license_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "SanWich"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SanWich"
    return Path.home() / ".config" / "SanWich"


def license_path() -> Path:
    return license_dir() / "license.json"


# ── 簽章 ─────────────────────────────────────────────────────────


def _payload_signature(data: dict) -> str:
    fields = ["edition", "trial_started_at", "trial_ends_at",
              "supporter_enabled", "supporter_key"]
    payload = "|".join(str(data.get(k, "")) for k in fields)
    return hmac.new(_SALT, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _sign(data: dict) -> dict:
    data["signature"] = _payload_signature(data)
    return data


def _signature_ok(data: dict) -> bool:
    sig = str(data.get("signature", ""))
    try:
        return hmac.compare_digest(sig, _payload_signature(data))
    except Exception:
        return False


# ── Supporter Key ────────────────────────────────────────────────
# 格式：SW-XXXX-XXXX-YYYY-YYYY
#   X…X = 8 碼隨機識別碼（hex 大寫）
#   Y…Y = HMAC(_SALT, "SW" + 識別碼) 前 8 碼（hex 大寫）


def _key_signature(body: str) -> str:
    digest = hmac.new(_SALT, ("SW" + body).encode("ascii"), hashlib.sha256)
    return digest.hexdigest()[:8].upper()


def normalize_key(key: str) -> str:
    return "".join(ch for ch in (key or "").upper() if ch.isalnum())


def verify_supporter_key(key: str) -> bool:
    raw = normalize_key(key)
    if len(raw) != 18 or not raw.startswith("SW"):
        return False
    body, sig = raw[2:10], raw[10:18]
    try:
        return hmac.compare_digest(sig, _key_signature(body))
    except Exception:
        return False


def generate_supporter_key(seed_bytes: bytes | None = None) -> str:
    """供內部小工具產 Key 使用（不在 UI 呼叫）。"""
    import secrets
    body = (seed_bytes.hex() if seed_bytes else secrets.token_hex(4)).upper()[:8]
    sig = _key_signature(body)
    return f"SW-{body[:4]}-{body[4:]}-{sig[:4]}-{sig[4:]}"


# ── License Manager ──────────────────────────────────────────────


class LicenseManager:
    def __init__(self):
        self.license_data = self.load_or_create_license()

    # 建立 / 讀取 --------------------------------------------------

    def _new_trial(self) -> dict:
        today = date.today()
        data = {
            "edition": "trial",
            "trial_started_at": today.isoformat(),
            "trial_ends_at": (today + timedelta(days=TRIAL_DAYS)).isoformat(),
            "supporter_enabled": False,
            "supporter_key": "",
        }
        return _sign(data)

    def _write(self, data: dict) -> None:
        try:
            license_dir().mkdir(parents=True, exist_ok=True)
            license_path().write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass  # 寫入失敗不影響使用

    def load_or_create_license(self) -> dict:
        path = license_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("trial_started_at"):
                    return data
            except Exception:
                pass
        data = self._new_trial()
        self._write(data)
        return data

    # 狀態判斷 ------------------------------------------------------

    def is_trial_active(self) -> bool:
        data = self.license_data
        if not _signature_ok(data):
            return False  # 檔案被改壞：回 Free，不鎖任何核心功能
        try:
            ends = date.fromisoformat(str(data.get("trial_ends_at", "")))
        except Exception:
            return False
        return ends >= date.today()

    def is_supporter_active(self) -> bool:
        return verify_supporter_key(str(self.license_data.get("supporter_key", "")))

    def has_feature(self, feature_name: str) -> bool:
        if feature_name in FREE_FEATURES:
            return True
        if feature_name in SUPPORTER_FEATURES:
            override = debug_override()
            if override is not None:
                return override in ("trial", "supporter")
            return self.is_trial_active() or self.is_supporter_active()
        return False

    # 啟用 Key ------------------------------------------------------

    def activate_key(self, key: str) -> bool:
        if not verify_supporter_key(key):
            return False
        data = dict(self.license_data)
        data["edition"] = "supporter"
        data["supporter_enabled"] = True
        data["supporter_key"] = normalize_key(key)
        self.license_data = _sign(data)
        self._write(self.license_data)
        return True

    # 給 UI 用的摘要 -------------------------------------------------

    def status_summary(self) -> dict:
        override = debug_override()
        if override is not None:
            labels = {"free": "Free", "trial": "Supporter Trial", "supporter": "Supporter"}
            return {"mode": override,
                    "label": f"{labels[override]}（Debug 覆寫）",
                    "trial_ends_at": "", "days_left": -1}
        if self.is_supporter_active():
            return {"mode": "supporter", "label": "Supporter（感謝支持！）",
                    "trial_ends_at": "", "days_left": -1}
        ends = str(self.license_data.get("trial_ends_at", ""))
        if self.is_trial_active():
            try:
                days = (date.fromisoformat(ends) - date.today()).days
            except Exception:
                days = 0
            return {"mode": "trial",
                    "label": f"Supporter Trial（剩 {days} 天）",
                    "trial_ends_at": ends, "days_left": days}
        return {"mode": "free", "label": "Free", "trial_ends_at": ends, "days_left": 0}
