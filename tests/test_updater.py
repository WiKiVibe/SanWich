from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from test_license_and_rules import ROOT, load_module


UPDATER = load_module("sanwich_updater_test", ROOT / "core" / "updater.py")


class UpdaterTests(unittest.TestCase):
    def test_selects_only_exact_github_asset_with_digest(self):
        release = {
            "tag_name": "v2.5",
            "assets": [{
                "name": "SanWich_update_v2.5.zip",
                "browser_download_url": "https://github.com/WiKiVibe/SanWich/releases/download/v2.5/SanWich_update_v2.5.zip",
                "digest": "sha256:" + "a" * 64,
                "size": 123,
            }],
        }
        asset = UPDATER.select_update_asset(release)
        self.assertEqual(asset["name"], "SanWich_update_v2.5.zip")

        release["assets"][0]["digest"] = None
        self.assertIsNone(UPDATER.select_update_asset(release))

    def test_download_verifies_size_and_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.zip"
            source.write_bytes(b"verified update")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            asset = {
                "name": "SanWich_update_v2.5.zip",
                "url": source.as_uri(),
                "digest": digest,
                "size": source.stat().st_size,
            }
            target = UPDATER.download_verified_asset(asset, destination_dir=root / "download")
            self.assertEqual(target.read_bytes(), source.read_bytes())

            asset["digest"] = "0" * 64
            with self.assertRaises(UPDATER.UpdateError):
                UPDATER.download_verified_asset(asset, destination_dir=root / "bad")

    @unittest.skipUnless(os.name == "nt", "PowerShell update helper is Windows-only")
    def test_powershell_helper_preserves_config_and_venv(self):
        with tempfile.TemporaryDirectory(prefix="SanWich_update_helper_test_") as tmp:
            root = Path(tmp)
            install = root / "install"
            (install / "app" / ".venv").mkdir(parents=True)
            (install / "app" / "config.json").write_text('{"api_key":"KEEP_ME"}', encoding="utf-8")
            (install / "app" / ".venv" / "keep.txt").write_text("KEEP_VENV", encoding="ascii")

            payload = b"updated"
            manifest = {
                "format": 1,
                "version": "test",
                "files": [{"path": "app/probe.txt", "sha256": hashlib.sha256(payload).hexdigest()}],
            }
            package = root / "update.zip"
            with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("update-manifest.json", json.dumps(manifest))
                archive.writestr("payload/app/probe.txt", payload)

            result = root / "result.json"
            completed = subprocess.run([
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(ROOT / "scripts" / "update" / "apply_update.ps1"),
                "-PackagePath", str(package), "-InstallRoot", str(install),
                "-ParentPid", "999999", "-RelaunchPath", str(root / "missing.vbs"),
                "-ResultPath", str(result),
            ], check=False, capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(result.read_text(encoding="utf-8-sig"))["status"], "success")
            self.assertEqual((install / "app" / "probe.txt").read_bytes(), payload)
            self.assertIn("KEEP_ME", (install / "app" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual((install / "app" / ".venv" / "keep.txt").read_text(), "KEEP_VENV")


if __name__ == "__main__":
    unittest.main()
