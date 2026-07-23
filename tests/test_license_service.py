from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from test_license_and_rules import load_module, ROOT


SERVICE = load_module("sanwich_license_service_test", ROOT / "core" / "license_service.py")


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class LicenseServiceOfflineTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        public_der = self.private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.temp = tempfile.TemporaryDirectory()
        self.storage = Path(self.temp.name)
        self.service = SERVICE.LicenseService(
            product_id="sanwich",
            api_base_url="https://license.test",
            issuer="https://license.test",
            public_key_spki=b64url(public_der),
            app_version="2.6.0",
            storage_dir=self.storage,
        )

    def tearDown(self):
        self.temp.cleanup()

    def make_token(self, revalidate: datetime, grace: datetime) -> str:
        fingerprint = self.service.device_fingerprint()
        claim = b64url(hashlib.sha256(f"device-claim-v1:{fingerprint}".encode()).digest())
        header = b64url(json.dumps({"alg": "EdDSA", "typ": "WKV-LICENSE", "kid": "test"}, separators=(",", ":")).encode())
        payload = b64url(json.dumps({
            "iss": "https://license.test",
            "ver": 1,
            "license_id": "lic_test",
            "product_id": "sanwich",
            "device_id": "dev_test",
            "device_fingerprint_hash": "server-only",
            "device_fingerprint_claim": claim,
            "features": ["batch_processing", "custom_rules"],
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "entitlement_expires_at": None,
            "revalidate_after": revalidate.isoformat(),
            "grace_until": grace.isoformat(),
        }, separators=(",", ":")).encode())
        signing_input = f"{header}.{payload}".encode("ascii")
        return f"{header}.{payload}.{b64url(self.private_key.sign(signing_input))}"

    def test_full_grace_free_and_anchor_recovery(self):
        now = datetime(2026, 7, 23, tzinfo=timezone.utc)
        self.service._save_token(self.make_token(now + timedelta(days=30), now + timedelta(days=45)))

        self.assertEqual(self.service.offline_state(now)["mode"], "full")
        self.assertEqual(self.service.offline_state(now + timedelta(days=31))["mode"], "grace")
        self.assertEqual(self.service.offline_state(now + timedelta(days=46))["mode"], "free")

        self.service.primary_path.unlink()
        self.assertEqual(self.service.offline_state(now)["mode"], "full")
        self.assertTrue(self.service.primary_path.exists())

    def test_tampered_token_and_device_do_not_unlock_features(self):
        now = datetime(2026, 7, 23, tzinfo=timezone.utc)
        token = self.make_token(now + timedelta(days=30), now + timedelta(days=45))
        self.service._save_token(token)
        cached = json.loads(self.service.primary_path.read_text(encoding="utf-8"))
        parts = cached["license_token"].split(".")
        parts[1] = ("A" if parts[1][0] != "A" else "B") + parts[1][1:]
        cached["license_token"] = ".".join(parts)
        self.service.primary_path.write_text(json.dumps(cached), encoding="utf-8")
        self.service.anchor_path.write_text(json.dumps(cached), encoding="utf-8")
        self.assertEqual(self.service.offline_state(now)["mode"], "free")

        self.service._save_token(token)
        self.service.device_path.unlink()
        self.assertEqual(self.service.offline_state(now)["mode"], "free")
        self.assertEqual(self.service.offline_state(now)["reason"], "wrong_device")

    def test_definitive_online_revocation_clears_token_but_network_error_keeps_it(self):
        now = datetime(2026, 7, 23, tzinfo=timezone.utc)
        token = self.make_token(now + timedelta(days=30), now + timedelta(days=44))
        self.service._save_token(token)
        revoked = SERVICE.LicenseServiceError("LICENSE_REVOKED", "revoked", 403)
        with mock.patch.object(self.service, "_post", side_effect=revoked):
            with self.assertRaises(SERVICE.LicenseServiceError):
                self.service.refresh()
        self.assertFalse(self.service.has_cached_license())

        self.service._save_token(token)
        offline = SERVICE.LicenseServiceError("NETWORK_ERROR", "offline")
        with mock.patch.object(self.service, "_post", side_effect=offline):
            with self.assertRaises(SERVICE.LicenseServiceError):
                self.service.refresh()
        self.assertTrue(self.service.has_cached_license())


if __name__ == "__main__":
    unittest.main()
