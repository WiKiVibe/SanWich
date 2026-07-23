# -*- coding: utf-8 -*-
"""SanWich 輕量授權管理（信任制）。

原則（見 SUPPORTER_PLAN.md）：
- 不做強制登入、不連網驗證、不做硬體綁定。
- Trial 到期只回到 Free 模式，絕不鎖住 Free 功能。
- 授權任何環節失敗，Free 功能一律照常可用。

license.json 位置：
  Windows: %APPDATA%/SanWich/license.json
  macOS:   ~/Library/Application Support/SanWich/license.json
  其他:    ~/.config/SanWich/license.json
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

try:
    import winreg
except Exception:
    winreg = None

# 新使用者可使用 14 個曆日的完整版試用；起始日算第 1 天。
# 舊版已寫入的 trial_ends_at 永遠沿用，不會因更新而縮短或重設。
TRIAL_DAYS = 14

DEFAULT_LICENSE_PRODUCT_ID = "sanwich"
DEFAULT_LICENSE_API_BASE_URL = "https://wikivibe-license-server.wikivibe.workers.dev"
DEFAULT_LICENSE_ISSUER = "https://wikivibe-license-server.wikivibe.workers.dev"
DEFAULT_LICENSE_PUBLIC_KEY_SPKI = "MCowBQYDK2VwAyEAkSWQwsY0BGQ5CUYgTuY8cy3VyF1L5a-_3o4mRnVb9rU"

_LOCAL_STATE_SALT = b"SanWich-Local-License-State-v2-2026"
_LEGACY_LOCAL_STATE_SALT = b"SanWich-TrustBased-License-v1-2026"
_SUPPORTER_KEY_PREFIX = "SW2"
_SUPPORTER_MESSAGE_PREFIX = b"SanWich supporter key v2\0"
_SHA256_DER_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
_SUPPORTER_PUBLIC_N = int(
    "13812019485706679660590446948791603793822765697603914583237325443061621194568002993754301496261106604493558872178779984044205123465743310816421995828947077608261231035125189987663058874108818250805280266941042176657281356788902010093607218412722896791106438628821462785010854796639733244744826936673196787750955393699752576964183215502673372943492206632367202867861902762877803463854661831440673268462145092966268102785401644058612662355432603990165815362488837024426213890937789245666328947795274771118518256004451345941742617732263876335522042707277623919650961913732820830960203135489770887667868382906564612668669"
)
_SUPPORTER_PUBLIC_E = 65537
_SUPPORTER_SIGNATURE_BYTES = 256
_REGISTRY_PATH = r"Software\WiKiVibe\SanWich"
_REGISTRY_VALUE = "LicenseState"


def _load_license_service_module():
    """Load the optional server client without making it a package dependency."""
    path = Path(__file__).resolve().parent / "license_service.py"
    if not path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("SanWich_license_service", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


_LICENSE_SERVICE_MODULE = _load_license_service_module()

# ── 功能集合：優先讀取同目錄 features.py，失敗用內建備援 ──────────

_FALLBACK_FREE = {
    "single_transcription", "export_srt", "export_txt",
    "basic_ai_proofread", "basic_srt_editor", "find_replace",
    "import_srt", "davinci_tools",
}
_FALLBACK_SUPPORTER = {
    "batch_processing", "quick_compare_full", "custom_rules",
    "learning_loop", "diarization", "domain_prompt_templates",
    "custom_dictionary", "project_profiles",
    "supporter_badge", "early_access",
}  # 與 features.py 同步；載入失敗時備援


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


def license_anchor_path() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "SanWich" / "license_anchor.json"
    return license_dir() / ".license_anchor.json"


def _read_json_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _read_registry_state() -> dict | None:
    if winreg is None or os.environ.get("SANWICH_LICENSE_REGISTRY_DISABLED") == "1":
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_PATH) as key:
            raw, _value_type = winreg.QueryValueEx(key, _REGISTRY_VALUE)
        data = json.loads(str(raw))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_registry_state(data: dict) -> None:
    if winreg is None or os.environ.get("SANWICH_LICENSE_REGISTRY_DISABLED") == "1":
        return
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _REGISTRY_PATH) as key:
            winreg.SetValueEx(
                key,
                _REGISTRY_VALUE,
                0,
                winreg.REG_SZ,
                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            )
    except Exception:
        pass


# ── 簽章 ─────────────────────────────────────────────────────────


def _payload_signature(data: dict, salt: bytes = _LOCAL_STATE_SALT) -> str:
    fields = ["edition", "trial_started_at", "trial_ends_at",
              "supporter_enabled", "supporter_key"]
    payload = "|".join(str(data.get(k, "")) for k in fields)
    return hmac.new(salt, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _sign(data: dict) -> dict:
    data["signature"] = _payload_signature(data)
    return data


def _signature_ok(data: dict) -> bool:
    sig = str(data.get("signature", ""))
    try:
        return hmac.compare_digest(sig, _payload_signature(data)) or hmac.compare_digest(
            sig, _payload_signature(data, _LEGACY_LOCAL_STATE_SALT)
        )
    except Exception:
        return False


# ── Supporter Key ────────────────────────────────────────────────


def _b32_decode(value: str) -> bytes:
    value = "".join(ch for ch in (value or "").upper() if ch.isalnum())
    if not value:
        return b""
    return base64.b32decode(value + "=" * ((8 - len(value) % 8) % 8))


def _supporter_message(body: str) -> bytes:
    return _SUPPORTER_MESSAGE_PREFIX + body.encode("ascii")


def _expected_encoded_digest(body: str) -> bytes:
    digest = hashlib.sha256(_supporter_message(body)).digest()
    payload = _SHA256_DER_PREFIX + digest
    padding_len = _SUPPORTER_SIGNATURE_BYTES - len(payload) - 3
    if padding_len < 8:
        return b""
    return b"\x00\x01" + b"\xff" * padding_len + b"\x00" + payload


def normalize_key(key: str) -> str:
    key = (key or "").strip().upper()
    return "".join(ch for ch in key if ch.isalnum() or ch == "-")


def verify_supporter_key(key: str) -> bool:
    raw = normalize_key(key)
    parts = raw.split("-")
    if len(parts) != 3 or parts[0] != _SUPPORTER_KEY_PREFIX:
        return False
    body, signature_text = parts[1], parts[2]
    if len(body) < 12:
        return False
    try:
        signature = _b32_decode(signature_text)
        if len(signature) != _SUPPORTER_SIGNATURE_BYTES:
            return False
        decoded = pow(
            int.from_bytes(signature, "big"),
            _SUPPORTER_PUBLIC_E,
            _SUPPORTER_PUBLIC_N,
        ).to_bytes(_SUPPORTER_SIGNATURE_BYTES, "big")
        return hmac.compare_digest(decoded, _expected_encoded_digest(body))
    except Exception:
        return False


# ── License Manager ──────────────────────────────────────────────


class LicenseManager:
    def __init__(self, config_path: Path | None = None, app_version: str = ""):
        self.server_service = self._create_server_service(config_path, app_version)
        self.last_license_error = ""
        self.last_license_error_code = ""
        self.license_data = self.load_or_create_license()

    @staticmethod
    def _create_server_service(config_path: Path | None, app_version: str):
        if _LICENSE_SERVICE_MODULE is None:
            return None
        values: dict[str, str] = {
            "license_product_id": DEFAULT_LICENSE_PRODUCT_ID,
            "license_api_base_url": DEFAULT_LICENSE_API_BASE_URL,
            "license_issuer": DEFAULT_LICENSE_ISSUER,
            "license_public_key_spki": DEFAULT_LICENSE_PUBLIC_KEY_SPKI,
        }
        if config_path and config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for key in ("license_api_base_url", "license_issuer", "license_public_key_spki", "license_product_id"):
                        value = data.get(key)
                        if isinstance(value, str) and value.strip():
                            values[key] = value.strip()
            except Exception:
                pass
        for env_name, config_name in (
            ("SANWICH_LICENSE_API_URL", "license_api_base_url"),
            ("SANWICH_LICENSE_ISSUER", "license_issuer"),
            ("SANWICH_LICENSE_PUBLIC_KEY_SPKI", "license_public_key_spki"),
            ("SANWICH_LICENSE_PRODUCT_ID", "license_product_id"),
        ):
            raw = os.environ.get(env_name, "").strip()
            if raw:
                values[config_name] = raw
        if not values.get("license_api_base_url") or not values.get("license_issuer") or not values.get("license_public_key_spki"):
            return None
        try:
            return _LICENSE_SERVICE_MODULE.LicenseService(
                product_id=values.get("license_product_id", "sanwich"),
                api_base_url=values["license_api_base_url"],
                issuer=values["license_issuer"],
                public_key_spki=values["license_public_key_spki"],
                app_version=app_version,
            )
        except Exception:
            return None

    # 建立 / 讀取 --------------------------------------------------

    def _new_trial(self) -> dict:
        today = date.today()
        data = {
            "edition": "trial",
            "trial_started_at": today.isoformat(),
            "trial_ends_at": (today + timedelta(days=TRIAL_DAYS - 1)).isoformat(),
            "supporter_enabled": False,
            "supporter_key": "",
        }
        return _sign(data)

    def _write_file(self, path: Path, data: dict) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _write(self, data: dict) -> None:
        self._write_file(license_path(), data)
        self._write_file(license_anchor_path(), data)
        _write_registry_state(data)

    @staticmethod
    def _valid_state(data: dict | None) -> bool:
        return bool(
            isinstance(data, dict)
            and data.get("trial_started_at")
            and _signature_ok(data)
        )

    @staticmethod
    def _oldest_trial_state(states: list[dict]) -> dict:
        def start_value(data: dict) -> str:
            try:
                return date.fromisoformat(str(data.get("trial_started_at", ""))).isoformat()
            except Exception:
                return "9999-12-31"

        supporter_states = [
            data for data in states
            if verify_supporter_key(str(data.get("supporter_key", "")))
        ]
        selected = dict(min(supporter_states or states, key=start_value))
        selected["trial_started_at"] = min(start_value(data) for data in states)

        valid_ends = []
        for data in states:
            try:
                valid_ends.append(date.fromisoformat(str(data.get("trial_ends_at", ""))).isoformat())
            except Exception:
                pass
        if valid_ends:
            selected["trial_ends_at"] = min(valid_ends)
        return _sign(selected)

    def load_or_create_license(self) -> dict:
        primary_path = license_path()
        anchor_path = license_anchor_path()
        raw_states = [
            _read_json_file(primary_path),
            _read_json_file(anchor_path),
            _read_registry_state(),
        ]
        valid_states = [data for data in raw_states if self._valid_state(data)]
        if valid_states:
            data = self._oldest_trial_state(valid_states)
            self._write(data)
            return data

        # Existing but invalid state must never be replaced with a fresh trial.
        if primary_path.exists() or anchor_path.exists() or any(raw_states):
            return {
                "edition": "free",
                "trial_started_at": "",
                "trial_ends_at": "",
                "supporter_enabled": False,
                "supporter_key": "",
                "signature": "",
            }
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
            if self.server_service is not None and self.server_service.has_cached_license():
                try:
                    return self.server_service.has_feature(feature_name, free_features=FREE_FEATURES)
                except Exception:
                    return False
            return self.is_trial_active() or self.is_supporter_active()
        return False

    # 啟用 Key ------------------------------------------------------

    def activate_key(self, key: str) -> bool:
        if self.server_service is not None:
            try:
                self.server_service.activate(key)
                self._retire_legacy_key_after_server_activation()
                self.last_license_error = ""
                self.last_license_error_code = ""
                return True
            except Exception as error:
                self.last_license_error = str(error)
                self.last_license_error_code = str(getattr(error, "code", ""))
                return False
        if not verify_supporter_key(key):
            return False
        data = dict(self.license_data)
        data["edition"] = "supporter"
        data["supporter_enabled"] = True
        data["supporter_key"] = normalize_key(key)
        self.license_data = _sign(data)
        self._write(self.license_data)
        return True

    def migrate_legacy_key(self, key: str) -> dict | None:
        """Explicitly migrate a verified legacy key through the new server."""
        if self.server_service is None:
            return None
        try:
            result = self.server_service.migrate_legacy(key)
            self._retire_legacy_key_after_server_activation()
            return result
        except Exception:
            return None

    def _retire_legacy_key_after_server_activation(self) -> None:
        """Prevent a migrated SW2 key from bypassing later server revocation."""
        data = dict(self.license_data)
        if not data.get("trial_started_at"):
            return
        data["edition"] = "free"
        data["supporter_enabled"] = False
        data["supporter_key"] = ""
        self.license_data = _sign(data)
        self._write(self.license_data)

    def refresh_server_license(self) -> bool:
        """Refresh a cached server token; network failures are non-fatal."""
        if self.server_service is None or not self.server_service.has_cached_license():
            return False
        try:
            self.server_service.refresh()
            return True
        except Exception:
            return False

    def deactivate_server_license(self) -> bool:
        if self.server_service is None:
            return False
        try:
            self.server_service.deactivate()
            return True
        except Exception:
            return False

    # 給 UI 用的摘要 -------------------------------------------------

    def status_summary(self) -> dict:
        override = debug_override()
        if override is not None:
            labels = {"free": "基本功能可用", "trial": "完整版試用", "supporter": "完整版"}
            return {"mode": override,
                    "label": f"{labels[override]}（Debug 覆寫）",
                    "trial_ends_at": "", "days_left": -1}
        if self.server_service is not None and self.server_service.has_cached_license():
            try:
                state = self.server_service.offline_state()
                return {
                    **state,
                    "trial_ends_at": "",
                    "days_left": -1,
                    "server_managed": True,
                }
            except Exception:
                pass
        if self.is_supporter_active():
            return {"mode": "supporter", "label": "完整版（感謝支持！）",
                    "trial_ends_at": "", "days_left": -1}
        ends = str(self.license_data.get("trial_ends_at", ""))
        if self.is_trial_active():
            try:
                days = (date.fromisoformat(ends) - date.today()).days + 1
            except Exception:
                days = 0
            return {"mode": "trial",
                    "label": f"完整版試用（剩 {days} 天）",
                    "trial_ends_at": ends, "days_left": days}
        return {"mode": "free", "label": "基本功能可用", "trial_ends_at": ends, "days_left": 0}
