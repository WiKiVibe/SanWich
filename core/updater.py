# -*- coding: utf-8 -*-
"""SanWich release updater helpers.

The application downloads only a GitHub Release update asset, verifies the
SHA-256 digest supplied by GitHub, then hands installation to a separate
PowerShell process so the running application never overwrites itself.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable


UPDATE_ASSET_PREFIX = "SanWich_update_v"
UPDATE_ASSET_SUFFIX = ".zip"


class UpdateError(RuntimeError):
    pass


def normalized_version(value: str) -> str:
    value = (value or "").strip()
    return value[1:] if value.lower().startswith("v") else value


def expected_asset_name(version: str) -> str:
    clean = normalized_version(version)
    if not clean or not re.fullmatch(r"[0-9A-Za-z._-]+", clean):
        raise UpdateError("invalid release version")
    return f"{UPDATE_ASSET_PREFIX}{clean}{UPDATE_ASSET_SUFFIX}"


def select_update_asset(release: dict) -> dict | None:
    """Return the exact update ZIP asset only when GitHub provides SHA-256."""
    expected = expected_asset_name(str(release.get("tag_name") or ""))
    for raw in release.get("assets") or []:
        if not isinstance(raw, dict) or raw.get("name") != expected:
            continue
        url = str(raw.get("browser_download_url") or "").strip()
        digest = str(raw.get("digest") or "").strip().lower()
        size = raw.get("size")
        if not url.startswith("https://github.com/"):
            return None
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            return None
        if not isinstance(size, int) or size <= 0:
            return None
        return {"name": expected, "url": url, "digest": digest[7:], "size": size}
    return None


def download_verified_asset(
    asset: dict,
    *,
    destination_dir: Path | None = None,
    timeout: float = 60.0,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    destination_dir = destination_dir or Path(tempfile.mkdtemp(prefix="SanWich_update_download_"))
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / str(asset["name"])
    partial = target.with_suffix(target.suffix + ".part")
    expected_size = int(asset["size"])
    digest = hashlib.sha256()
    request = urllib.request.Request(
        str(asset["url"]),
        headers={"User-Agent": "SanWich-Updater", "Accept": "application/octet-stream"},
    )
    try:
        received = 0
        with urllib.request.urlopen(request, timeout=timeout) as response, partial.open("wb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
                digest.update(block)
                received += len(block)
                if progress:
                    progress(received, expected_size)
        if received != expected_size:
            raise UpdateError(f"update size mismatch: expected {expected_size}, got {received}")
        if digest.hexdigest().lower() != str(asset["digest"]).lower():
            raise UpdateError("update SHA-256 verification failed")
        os.replace(partial, target)
        return target
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def launch_installer(
    package_path: Path,
    *,
    helper_path: Path,
    install_root: Path,
    relaunch_path: Path,
    result_path: Path,
    parent_pid: int | None = None,
) -> subprocess.Popen:
    if os.name != "nt":
        raise UpdateError("one-click update is currently available on Windows only")
    if not package_path.is_file() or not helper_path.is_file():
        raise UpdateError("update package or helper is missing")
    helper_copy = package_path.parent / f"apply_update_{os.getpid()}.ps1"
    shutil.copy2(helper_path, helper_copy)
    command = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden", "-File", str(helper_copy),
        "-PackagePath", str(package_path),
        "-InstallRoot", str(install_root),
        "-ParentPid", str(parent_pid or os.getpid()),
        "-RelaunchPath", str(relaunch_path),
        "-ResultPath", str(result_path),
    ]
    return subprocess.Popen(command, cwd=str(package_path.parent), close_fds=True)
