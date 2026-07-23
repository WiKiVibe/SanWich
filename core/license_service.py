"""Server-managed WiKiVibe license client for SanWich.

This module deliberately has no UI dependency. ``license_manager.py`` keeps the
existing ``has_feature`` facade and delegates to this service when the server
configuration is present. The local token is signed by the server and is safe to
check without a network connection.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except Exception:  # Optional until the application is upgraded with requirements.txt.
    InvalidSignature = Exception  # type: ignore[assignment,misc]
    serialization = None  # type: ignore[assignment]
    Ed25519PublicKey = None  # type: ignore[assignment,misc]


class LicenseServiceError(RuntimeError):
    def __init__(self, code: str, message: str, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _machine_secret_path() -> Path:
    if sys_platform_windows():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = str(Path.home() / ".config")
    return Path(base) / "SanWich" / "device_secret.bin"


def sys_platform_windows() -> bool:
    return os.name == "nt"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi_protect(raw: bytes) -> bytes:
    if not sys_platform_windows():
        return raw
    buffer = ctypes.create_string_buffer(raw)
    source = _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    destination = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptProtectData(ctypes.byref(source), "SanWich device identity", None, None, None, 0, ctypes.byref(destination)):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)


def _dpapi_unprotect(raw: bytes) -> bytes:
    if not sys_platform_windows():
        return raw
    buffer = ctypes.create_string_buffer(raw)
    source = _DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    destination = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(destination)):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)


class LicenseService:
    """Network and offline license operations for one WiKiVibe product."""

    def __init__(
        self,
        *,
        product_id: str,
        api_base_url: str,
        issuer: str,
        public_key_spki: str,
        app_version: str,
        storage_dir: Path | None = None,
        timeout: float = 8.0,
    ):
        self.product_id = product_id
        self.api_base_url = api_base_url.rstrip("/")
        self.issuer = issuer
        self.app_version = app_version
        self.timeout = timeout
        self._public_key = self._load_public_key(public_key_spki)

        if storage_dir is None:
            roaming = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            self.primary_path = Path(roaming) / "SanWich" / "license_v2.json"
            self.anchor_path = Path(local) / "SanWich" / "license_v2_anchor.json"
        else:
            self.primary_path = storage_dir / "license_v2.json"
            self.anchor_path = storage_dir / "license_v2_anchor.json"
        self.device_path = _machine_secret_path() if storage_dir is None else storage_dir / "device_secret.bin"

    @staticmethod
    def _load_public_key(encoded: str):
        if not encoded or serialization is None or Ed25519PublicKey is None:
            return None
        try:
            key = serialization.load_der_public_key(_b64url_decode(encoded))
            return key if isinstance(key, Ed25519PublicKey) else None
        except Exception:
            return None

    @property
    def configured(self) -> bool:
        return bool(self.api_base_url and self.issuer and self._public_key is not None)

    def _device_secret(self) -> bytes:
        try:
            raw = _dpapi_unprotect(self.device_path.read_bytes())
            if len(raw) >= 32:
                return raw
        except Exception:
            pass
        raw = secrets.token_bytes(32)
        self.device_path.parent.mkdir(parents=True, exist_ok=True)
        self.device_path.write_bytes(_dpapi_protect(raw))
        try:
            os.chmod(self.device_path, 0o600)
        except OSError:
            pass
        return raw

    def device_fingerprint(self) -> str:
        secret = self._device_secret()
        return hashlib.sha256(b"wikivibe-device-v1:" + secret).hexdigest()

    def _device(self, name: str | None = None) -> dict[str, str]:
        return {
            "fingerprint": self.device_fingerprint(),
            "name": name or platform.node() or "Windows PC",
            "platform": f"{platform.system()} {platform.release()}",
        }

    def _claim(self, fingerprint: str) -> str:
        return _b64url_encode(hashlib.sha256(f"device-claim-v1:{fingerprint}".encode("utf-8")).digest())

    def _verify_token(self, token: str) -> dict[str, Any] | None:
        if self._public_key is None:
            return None
        try:
            header_part, payload_part, signature_part = token.split(".")
            header = json.loads(_b64url_decode(header_part))
            if header.get("alg") != "EdDSA" or header.get("typ") != "WKV-LICENSE":
                return None
            self._public_key.verify(
                _b64url_decode(signature_part),
                f"{header_part}.{payload_part}".encode("ascii"),
            )
            payload = json.loads(_b64url_decode(payload_part))
            if not isinstance(payload, dict) or payload.get("ver") != 1:
                return None
            return payload
        except (ValueError, TypeError, json.JSONDecodeError, InvalidSignature):
            return None

    def _read_cache(self) -> dict[str, Any] | None:
        for path in (self.primary_path, self.anchor_path):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("license_token"), str):
                    if path != self.primary_path and not self.primary_path.exists():
                        self._write_atomic(self.primary_path, data)
                    return data
            except (OSError, json.JSONDecodeError):
                continue
        return None

    def has_cached_license(self) -> bool:
        return self._read_cache() is not None

    def _clear_cache(self) -> None:
        self.primary_path.unlink(missing_ok=True)
        self.anchor_path.unlink(missing_ok=True)

    @staticmethod
    def _write_atomic(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _save_token(self, token: str) -> dict[str, Any]:
        payload = self._verify_token(token)
        if not payload:
            raise LicenseServiceError("INVALID_TOKEN", "授權伺服器回傳的 Token 無法驗證。")
        if payload.get("iss") != self.issuer or payload.get("product_id") != self.product_id:
            raise LicenseServiceError("INVALID_TOKEN", "授權 Token 的產品或簽發者不符。")
        if payload.get("device_fingerprint_claim") != self._claim(self.device_fingerprint()):
            raise LicenseServiceError("DEVICE_MISMATCH", "授權 Token 不屬於這台裝置。")
        data = {"license_token": token, "saved_at": _now().isoformat()}
        self._write_atomic(self.primary_path, data)
        self._write_atomic(self.anchor_path, data)
        return payload

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise LicenseServiceError("NOT_CONFIGURED", "尚未設定 License Server 或公開金鑰。")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_base_url}{path}", data=body,
            headers={"Content-Type": "application/json", "User-Agent": f"SanWich/{self.app_version}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8")).get("error", {})
            except Exception:
                detail = {}
            raise LicenseServiceError(str(detail.get("code", "HTTP_ERROR")), str(detail.get("message", error.reason)), error.code) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise LicenseServiceError("NETWORK_ERROR", "目前無法連線到授權伺服器。") from error
        if not isinstance(result, dict):
            raise LicenseServiceError("INVALID_RESPONSE", "授權伺服器回傳格式錯誤。")
        return result

    def activate(self, license_key: str, *, device_name: str | None = None) -> dict[str, Any]:
        result = self._post("/v1/license/activate", {
            "license_key": license_key,
            "product_id": self.product_id,
            "device": self._device(device_name),
            "app_version": self.app_version,
        })
        token = result.get("license_token")
        if not isinstance(token, str):
            raise LicenseServiceError("INVALID_RESPONSE", "啟用回應缺少授權 Token。")
        self._save_token(token)
        return result

    def migrate_legacy(self, legacy_key: str, *, device_name: str | None = None) -> dict[str, Any]:
        result = self._post("/v1/license/migrate-legacy", {
            "legacy_key": legacy_key,
            "product_id": self.product_id,
            "device": self._device(device_name),
            "app_version": self.app_version,
        })
        token = result.get("license_token")
        if not isinstance(token, str):
            raise LicenseServiceError("INVALID_RESPONSE", "遷移回應缺少授權 Token。")
        self._save_token(token)
        return result

    def refresh(self) -> dict[str, Any]:
        cache = self._read_cache()
        if not cache:
            raise LicenseServiceError("NO_LICENSE", "這台裝置尚未有新版授權。")
        try:
            result = self._post("/v1/license/verify", {
                "license_token": cache["license_token"],
                "device": self._device(),
                "app_version": self.app_version,
            })
        except LicenseServiceError as error:
            definitive = {
                "INVALID_TOKEN", "DEVICE_MISMATCH", "DEVICE_DEACTIVATED",
                "LICENSE_NOT_FOUND", "LICENSE_REVOKED", "LICENSE_DISABLED", "LICENSE_EXPIRED",
                "PRODUCT_DISABLED",
            }
            if error.code in definitive and error.status in {401, 403, 404}:
                self._clear_cache()
            raise
        token = result.get("license_token")
        if not isinstance(token, str):
            raise LicenseServiceError("INVALID_RESPONSE", "驗證回應缺少授權 Token。")
        self._save_token(token)
        return result

    def deactivate(self) -> dict[str, Any]:
        cache = self._read_cache()
        if not cache:
            return {"status": "deactivated"}
        result = self._post("/v1/license/deactivate", {
            "license_token": cache["license_token"],
            "device": self._device(),
        })
        self._clear_cache()
        return result

    def offline_state(self, now: datetime | None = None) -> dict[str, Any]:
        cache = self._read_cache()
        if not cache:
            return {"mode": "free", "label": "基本功能可用", "features": [], "reason": "no_license"}
        payload = self._verify_token(str(cache.get("license_token", "")))
        if not payload:
            return {"mode": "free", "label": "基本功能可用", "features": [], "reason": "invalid_token"}
        if payload.get("iss") != self.issuer or payload.get("product_id") != self.product_id:
            return {"mode": "free", "label": "基本功能可用", "features": [], "reason": "wrong_product"}
        if payload.get("device_fingerprint_claim") != self._claim(self.device_fingerprint()):
            return {"mode": "free", "label": "基本功能可用", "features": [], "reason": "wrong_device"}
        current = (now or _now()).astimezone(timezone.utc)
        expires = _parse_time(payload.get("entitlement_expires_at"))
        revalidate = _parse_time(payload.get("revalidate_after"))
        grace = _parse_time(payload.get("grace_until"))
        features = [item for item in payload.get("features", []) if isinstance(item, str)]
        if expires and current >= expires:
            return {"mode": "free", "label": "完整版授權已失效，基本功能可用", "features": [], "reason": "expired"}
        if not revalidate or not grace:
            return {"mode": "free", "label": "基本功能可用", "features": [], "reason": "invalid_dates"}
        state = {"mode": "full", "label": "完整版", "features": features, "revalidate_after": revalidate.isoformat(), "grace_until": grace.isoformat()}
        if current <= revalidate:
            return state
        if current <= grace:
            state.update(mode="grace", label="完整版（等待重新驗證）")
            return state
        return {"mode": "free", "label": "完整版驗證已逾期，基本功能可用", "features": [], "reason": "grace_expired"}

    def has_feature(self, feature_name: str, *, free_features: set[str]) -> bool:
        if feature_name in free_features:
            return True
        state = self.offline_state()
        return feature_name in state.get("features", []) and state.get("mode") in {"full", "grace"}
