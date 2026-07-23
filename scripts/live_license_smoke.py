"""Production license smoke test. Requires SANWICH_LICENSE_ADMIN_KEY.

No license key, token, admin key, or device fingerprint is printed or written to
the repository. The generated smoke license is revoked before exit.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
API_BASE = "https://wikivibe-license-server.wikivibe.workers.dev"
PUBLIC_KEY = "MCowBQYDK2VwAyEAkSWQwsY0BGQ5CUYgTuY8cy3VyF1L5a-_3o4mRnVb9rU"
FEATURES = [
    "batch_processing", "quick_compare_full", "custom_rules", "learning_loop",
    "diarization", "domain_prompt_templates", "custom_dictionary", "project_profiles",
    "supporter_badge", "early_access",
]


def load_service_module():
    path = ROOT / "core" / "license_service.py"
    spec = importlib.util.spec_from_file_location("sanwich_live_license_service", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_license_manager_module():
    path = ROOT / "core" / "license_manager.py"
    spec = importlib.util.spec_from_file_location("sanwich_live_license_manager", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def api(path: str, *, method: str = "GET", body: dict | None = None, admin_key: str = "") -> dict:
    headers = {"User-Agent": "SanWich-License-Smoke/2.5", "Accept": "application/json"}
    if admin_key:
        headers["Authorization"] = f"Bearer {admin_key}"
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(API_BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = json.loads(error.read().decode("utf-8"))
        code = str(detail.get("error", {}).get("code", "HTTP_ERROR"))
        raise RuntimeError(f"{error.code}:{code}") from error
    if not isinstance(result, dict):
        raise RuntimeError("invalid API response")
    return result


def main() -> None:
    admin_key = os.environ.get("SANWICH_LICENSE_ADMIN_KEY", "").strip()
    if not admin_key:
        raise SystemExit("SANWICH_LICENSE_ADMIN_KEY is required")
    service_module = load_service_module()
    license_id = ""
    try:
        try:
            api("/v1/admin/products", method="POST", admin_key=admin_key, body={
                "id": "sanwich", "name": "SanWich", "default_features": FEATURES,
            })
        except RuntimeError as error:
            if "409:PRODUCT_EXISTS" not in str(error):
                raise

        created = api("/v1/admin/licenses", method="POST", admin_key=admin_key, body={
            "product_id": "sanwich",
            "customer_ref": f"release-smoke-{uuid.uuid4().hex[:12]}",
            "features": FEATURES,
            "max_devices": 2,
            "metadata": {"purpose": "automated release smoke"},
        })
        license_id = str(created["id"])
        license_key = str(created["license_key"])

        with tempfile.TemporaryDirectory(prefix="SanWich_license_smoke_") as temp:
            temp_root = Path(temp)
            previous_env = {name: os.environ.get(name) for name in ("APPDATA", "LOCALAPPDATA", "SANWICH_LICENSE_REGISTRY_DISABLED")}
            os.environ.update({
                "APPDATA": str(temp_root / "manager_roaming"),
                "LOCALAPPDATA": str(temp_root / "manager_local"),
                "SANWICH_LICENSE_REGISTRY_DISABLED": "1",
            })
            manager_module = load_license_manager_module()
            manager = manager_module.LicenseManager(app_version="2.5")
            if not manager.activate_key(license_key):
                raise RuntimeError(f"LicenseManager activation failed: {manager.last_license_error_code}")
            if manager.status_summary()["mode"] != "full" or not manager.has_feature("batch_processing"):
                raise RuntimeError("LicenseManager facade did not unlock Full")

            stores = [temp_root / name for name in ("device2", "device3")]
            services = [service_module.LicenseService(
                product_id="sanwich",
                api_base_url=API_BASE,
                issuer=API_BASE,
                public_key_spki=PUBLIC_KEY,
                app_version="2.5",
                storage_dir=store,
                timeout=20,
            ) for store in stores]

            services[0].activate(license_key, device_name="Smoke Device 2")
            try:
                services[1].activate(license_key, device_name="Smoke Device 3")
                raise RuntimeError("third device was unexpectedly accepted")
            except service_module.LicenseServiceError as error:
                if error.code != "DEVICE_LIMIT_REACHED":
                    raise

            if not manager.refresh_server_license():
                raise RuntimeError("LicenseManager online refresh failed")
            services[0].deactivate()
            services[1].activate(license_key, device_name="Smoke Device 3")

            api(f"/v1/admin/licenses/{license_id}/status", method="POST", admin_key=admin_key, body={"status": "revoked"})
            try:
                services[1].refresh()
                raise RuntimeError("revoked license was unexpectedly verified")
            except service_module.LicenseServiceError as error:
                if error.code != "LICENSE_REVOKED":
                    raise
            if services[1].has_cached_license() or services[1].offline_state()["mode"] != "free":
                raise RuntimeError("definitive revocation did not clear the local token")
            if manager.refresh_server_license() or manager.server_service.has_cached_license():
                raise RuntimeError("LicenseManager retained a definitively revoked token")

            for name, value in previous_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        print(json.dumps({
            "status": "PASS",
            "activation": "two_devices",
            "third_device": "rejected",
            "deactivation": "slot_released",
            "revocation": "verify_rejected",
        }, ensure_ascii=False))
    finally:
        if license_id:
            try:
                api(f"/v1/admin/licenses/{license_id}/status", method="POST", admin_key=admin_key, body={"status": "revoked"})
            except Exception:
                pass


if __name__ == "__main__":
    main()
