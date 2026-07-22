"""Private local LLM runtime management for SanWich v2.5b.

Downloads verified llama.cpp release assets from the official GitHub project,
downloads a pinned Traditional-Chinese Breeze GGUF, and exposes only a
loopback OpenAI-compatible endpoint.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


MODEL_ID = "YC-Chen/Breeze-7B-Instruct-v1_0-GGUF"
MODEL_FILENAME = "breeze-7b-instruct-v1_0-q4_k_m.gguf"
MODEL_LABEL = "Breeze-7B-Instruct v1.0（本機 Q4_K_M）"
MODEL_URL = f"https://huggingface.co/{MODEL_ID}/resolve/main/{MODEL_FILENAME}?download=true"
MODEL_SIZE = 4_538_717_088
MODEL_SHA256 = "151a564e14fe47d18e3bf1a6dd2fe3e687cdc386fb3083471522e512131a72ec"
LLAMA_RELEASE_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
LOCAL_MODEL_ALIAS = "breeze-local"
MIN_DOWNLOAD_FREE_GB = 7.0
RECOMMENDED_DOWNLOAD_FREE_GB = 10.0


def local_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "SanWich" / "local_ai"
    return Path.home() / ".local" / "share" / "SanWich" / "local_ai"


class LocalLLMError(RuntimeError):
    pass


class LocalLLMManager:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = Path(base_dir) if base_dir else local_data_dir()
        self.runtime_dir = self.base_dir / "llama.cpp"
        self.model_dir = self.base_dir / "models"
        self.download_dir = self.base_dir / "downloads"
        self.log_dir = self.base_dir / "logs"
        self.model_path = self.model_dir / MODEL_FILENAME
        self.manifest_path = self.runtime_dir / "sanwich_runtime.json"
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._port: int | None = None
        self._log_handle = None
        self._last_gpu_layers: int = 0
        self._cuda_init_failed: bool = False
        self._running_on_cpu: bool = False
        self._variant_override: str | None = None

    @property
    def server_path(self) -> Path:
        direct = self.runtime_dir / "llama-server.exe"
        if direct.exists():
            return direct
        found = next(self.runtime_dir.rglob("llama-server.exe"), None) if self.runtime_dir.exists() else None
        return found or direct

    @staticmethod
    def _runtime_payload_ready(directory: Path, variant: str) -> bool:
        if not directory.exists():
            return False
        server = next(directory.rglob("llama-server.exe"), None)
        if server is None or server.stat().st_size < 8_000:
            return False
        root = server.parent
        required = [root / "llama-server-impl.dll", root / "llama.dll"]
        if not all(path.exists() and path.stat().st_size > 500_000 for path in required):
            return False
        if not any(path.stat().st_size > 100_000 for path in root.glob("ggml*.dll")):
            return False
        if variant.startswith("cuda-"):
            cuda_major = variant.split("-", 1)[1].split(".", 1)[0]
            cuda_required = [
                root / "ggml-cuda.dll",
                root / f"cudart64_{cuda_major}.dll",
                root / f"cublas64_{cuda_major}.dll",
            ]
            if not all(path.exists() and path.stat().st_size > 100_000 for path in cuda_required):
                return False
        return True

    def _creationflags(self) -> int:
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if sys.platform == "win32" else 0

    def _run_capture(self, cmd: list[str], timeout: float = 8.0) -> str:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=self._creationflags(),
            )
            return (result.stdout or result.stderr or "").strip()
        except Exception:
            return ""

    def gpu_info(self) -> dict:
        output = self._run_capture(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"]
        )
        if not output:
            return {"name": "", "vram_mb": 0, "driver": "", "driver_cuda": ""}
        first = output.splitlines()[0]
        parts = [part.strip() for part in first.split(",")]
        try:
            vram = int(float(parts[1]))
        except Exception:
            vram = 0
        return {
            "name": parts[0] if parts else "",
            "vram_mb": vram,
            "driver": parts[2] if len(parts) > 2 else "",
            "driver_cuda": self.driver_cuda_version(),
        }

    def driver_cuda_version(self) -> str:
        """nvidia-smi 標示的「此驅動最高支援 CUDA 版本」，例如 12.9。"""
        output = self._run_capture(["nvidia-smi"])
        match = re.search(r"CUDA\s+Version:\s*([0-9]+(?:\.[0-9]+)?)", output or "")
        return match.group(1) if match else ""

    def _cuda_version_tuple(self, value: str) -> tuple[int, int]:
        parts = re.findall(r"\d+", value or "")
        if not parts:
            return (0, 0)
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        return (major, minor)

    def runtime_variant(self) -> str:
        """依 GPU 與驅動可支援的 CUDA 版本選擇 llama.cpp 套件。

        重要：CUDA *runtime* 不可高於驅動支援上限。
        例：驅動 CUDA Version 12.9 時不能用 cuda-13.3 套件，否則會
        ``ggml_cuda_init: failed to initialize CUDA: (null)`` 並退化成 CPU。
        """
        if self._variant_override:
            return self._variant_override
        gpu = self.gpu_info()
        name = (gpu.get("name") or "").lower()
        has_nvidia = any(token in name for token in ("nvidia", "geforce", "quadro", "rtx"))
        if not has_nvidia:
            return "cpu"

        driver_cuda = self._cuda_version_tuple(gpu.get("driver_cuda") or self.driver_cuda_version())
        is_blackwell = bool(
            re.search(r"rtx\s*50\d\d", name)
            or any(token in name for token in ("blackwell", "b100", "b200"))
        )
        # 驅動支援 CUDA 13+ 才用 13.3；否則一律 12.4（含 RTX 50 + 舊驅動）。
        if driver_cuda >= (13, 0) and is_blackwell:
            return "cuda-13.3"
        if driver_cuda >= (12, 0) or has_nvidia:
            return "cuda-12.4"
        return "cpu"

    def runtime_ready(self) -> bool:
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            variant = self.runtime_variant()
            return str(manifest.get("variant") or "") == variant and self._runtime_payload_ready(self.runtime_dir, variant)
        except Exception:
            return False

    def model_ready(self) -> bool:
        marker = self.model_path.with_suffix(self.model_path.suffix + ".sha256")
        if not self.model_path.exists() or self.model_path.stat().st_size != MODEL_SIZE:
            return False
        try:
            return marker.read_text(encoding="ascii").strip().lower() == MODEL_SHA256
        except Exception:
            return False

    def status(self) -> dict:
        return {
            "runtime_ready": self.runtime_ready(),
            "model_ready": self.model_ready(),
            "running": self.is_running(),
            "port": self._port,
            "variant": self.runtime_variant(),
            "gpu": self.gpu_info(),
            "base_dir": str(self.base_dir),
            "model_path": str(self.model_path),
            "gpu_layers": self._last_gpu_layers,
            "cuda_init_failed": self._cuda_init_failed,
            "running_on_cpu": self._running_on_cpu,
        }

    def _recent_log_text(self, max_bytes: int = 24_000) -> str:
        log_path = self.log_dir / "llama-server.log"
        try:
            with log_path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - max_bytes))
                return handle.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _detect_cuda_failure(self) -> bool:
        """Inspect recent llama-server log for CUDA init failure after launch."""
        text = self._recent_log_text()
        if not text:
            return False
        markers = (
            "failed to initialize CUDA",
            "ggml_cuda_init: failed",
            "no CUDA devices found",
            "CUDA error",
        )
        # Prefer the latest launch block if timestamps exist.
        chunks = re.split(r"\n(?=\[\d{4}-\d{2}-\d{2} )", text)
        recent = chunks[-1] if chunks else text
        return any(marker in recent for marker in markers)

    def disk_space_status(self) -> dict:
        """Return free-space status for the drive that stores local AI assets."""
        target = self.base_dir
        while not target.exists() and target.parent != target:
            target = target.parent
        usage = shutil.disk_usage(str(target))
        free_gb = usage.free / (1024 ** 3)
        return {
            "path": str(target),
            "free_gb": free_gb,
            "minimum_gb": MIN_DOWNLOAD_FREE_GB,
            "recommended_gb": RECOMMENDED_DOWNLOAD_FREE_GB,
        }

    def preflight_disk_space(self, log_fn=None) -> dict:
        """Block a first-time asset download when the destination drive is too full."""
        status = self.disk_space_status()
        free_gb = float(status["free_gb"])
        if free_gb < MIN_DOWNLOAD_FREE_GB:
            raise LocalLLMError(
                f"本地 AI 所在磁碟只剩 {free_gb:.1f} GB；首次下載至少需要 "
                f"{MIN_DOWNLOAD_FREE_GB:.0f} GB 可用空間，建議先保留 "
                f"{RECOMMENDED_DOWNLOAD_FREE_GB:.0f} GB。位置：{status['path']}"
            )
        if free_gb < RECOMMENDED_DOWNLOAD_FREE_GB and log_fn:
            log_fn(
                f"本地 AI：磁碟剩餘 {free_gb:.1f} GB，已達最低需求；"
                f"建議保留 {RECOMMENDED_DOWNLOAD_FREE_GB:.0f} GB，避免下載與解壓縮空間過緊。"
            )
        return status

    def _request_json(self, url: str, timeout: float = 30.0) -> dict:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "SanWich/2.5b",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _sha256(self, path: Path, progress_cb=None, label: str = "驗證檔案") -> str:
        digest = hashlib.sha256()
        total = path.stat().st_size
        done = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(4 * 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(label, done, total)
        return digest.hexdigest()

    def _download(self, url: str, destination: Path, *, size: int = 0, sha256: str = "", progress_cb=None, label: str) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".part")
        if destination.exists() and (not size or destination.stat().st_size == size):
            if not sha256 or self._sha256(destination, progress_cb, f"{label} SHA256").lower() == sha256.lower():
                return
            destination.unlink(missing_ok=True)
        if partial.exists() and size and partial.stat().st_size == size:
            if not sha256 or self._sha256(partial, progress_cb, f"{label} SHA256").lower() == sha256.lower():
                os.replace(partial, destination)
                return
            partial.unlink(missing_ok=True)
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "SanWich/2.5b"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=120) as response:
            status = getattr(response, "status", response.getcode())
            if offset and status != 206:
                offset = 0
                partial.unlink(missing_ok=True)
            mode = "ab" if offset else "wb"
            response_total = int(response.headers.get("Content-Length") or 0)
            total = size or (offset + response_total)
            done = offset
            with partial.open(mode) as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    if progress_cb:
                        progress_cb(label, done, total)
        if size and partial.stat().st_size != size:
            raise LocalLLMError(f"{label}大小不正確：{partial.stat().st_size} / {size}")
        if sha256:
            actual = self._sha256(partial, progress_cb, f"{label} SHA256")
            if actual.lower() != sha256.lower():
                partial.unlink(missing_ok=True)
                raise LocalLLMError(f"{label} SHA256 驗證失敗，已刪除不安全的下載檔。")
        os.replace(partial, destination)

    @staticmethod
    def _asset_sha(asset: dict) -> str:
        value = str(asset.get("digest") or "")
        return value.split(":", 1)[1] if value.startswith("sha256:") else ""

    def _select_release_assets(self, release: dict, variant: str) -> list[dict]:
        assets = list(release.get("assets") or [])
        if variant.startswith("cuda-"):
            cuda = variant.split("-", 1)[1]
            wanted = [
                (f"bin-win-cuda-{cuda}-x64.zip", "llama-"),
                (f"cudart-llama-bin-win-cuda-{cuda}-x64.zip", "cudart-"),
            ]
        elif variant == "vulkan":
            wanted = [("bin-win-vulkan-x64.zip", "llama-")]
        else:
            wanted = [("bin-win-cpu-x64.zip", "llama-")]
        selected = []
        for suffix, prefix in wanted:
            match = next(
                (
                    asset for asset in assets
                    if str(asset.get("name") or "").startswith(prefix)
                    and str(asset.get("name") or "").endswith(suffix)
                ),
                None,
            )
            if match is None:
                raise LocalLLMError(f"llama.cpp release 缺少資產：{suffix}")
            if not self._asset_sha(match):
                raise LocalLLMError(f"llama.cpp 資產沒有 SHA256：{match.get('name')}")
            selected.append(match)
        return selected

    @staticmethod
    def _safe_extract(archive: Path, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        base = destination.resolve()
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                target = (destination / info.filename).resolve()
                if os.path.commonpath([str(base), str(target)]) != str(base):
                    raise LocalLLMError(f"ZIP 內含不安全路徑：{info.filename}")
            zf.extractall(destination)

    @staticmethod
    def _copy_archive_payload(extracted: Path, destination: Path) -> None:
        children = list(extracted.iterdir())
        root = children[0] if len(children) == 1 and children[0].is_dir() else extracted
        for source in root.rglob("*"):
            if not source.is_file():
                continue
            relative = source.relative_to(root)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def installed_variant(self) -> str:
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return str(manifest.get("variant") or "")
        except Exception:
            return ""

    def reinstall_runtime(self, variant: str | None = None, progress_cb=None, log_fn=None) -> Path:
        """Stop server, wipe runtime dir, and install a specific llama.cpp variant."""
        with self._lock:
            self.stop()
            if variant:
                self._variant_override = variant
            target = self.runtime_variant()
            if log_fn:
                log_fn(f"本地 AI：準備重裝執行核心為 {target}（清除舊版 {self.installed_variant() or '無'}）。")
            if self.runtime_dir.exists():
                shutil.rmtree(self.runtime_dir, ignore_errors=True)
            # Force ensure_runtime to download even if partial files remain.
            return self.ensure_runtime(progress_cb=progress_cb, log_fn=log_fn, preflight=True)

    def ensure_runtime(self, progress_cb=None, log_fn=None, *, preflight: bool = True) -> Path:
        with self._lock:
            if self.runtime_ready():
                return self.server_path
            if preflight:
                self.preflight_disk_space(log_fn=log_fn)
            variant = self.runtime_variant()
            installed = self.installed_variant()
            if installed and installed != variant and log_fn:
                log_fn(
                    f"本地 AI：偵測到執行核心版本不符（已裝 {installed}，需要 {variant}），"
                    "將重新下載以啟用 GPU。"
                )
            if log_fn:
                driver_cuda = self.driver_cuda_version() or "未知"
                log_fn(
                    f"本地 AI：下載 llama.cpp 官方 {variant} 執行核心"
                    f"（驅動最高 CUDA {driver_cuda}）。"
                )
            release = self._request_json(LLAMA_RELEASE_API)
            assets = self._select_release_assets(release, variant)
            self.download_dir.mkdir(parents=True, exist_ok=True)
            archives = []
            for asset in assets:
                name = str(asset["name"])
                archive = self.download_dir / name
                self._download(
                    str(asset["browser_download_url"]),
                    archive,
                    size=int(asset.get("size") or 0),
                    sha256=self._asset_sha(asset),
                    progress_cb=progress_cb,
                    label=f"llama.cpp {name}",
                )
                archives.append(archive)

            self.base_dir.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix="runtime-", dir=str(self.base_dir)))
            merged = staging / "merged"
            merged.mkdir()
            try:
                for index, archive in enumerate(archives):
                    extracted = staging / f"archive-{index}"
                    self._safe_extract(archive, extracted)
                    self._copy_archive_payload(extracted, merged)
                if not self._runtime_payload_ready(merged, variant):
                    raise LocalLLMError("llama.cpp 主程式或必要 DLL 不完整。")
                if self.runtime_dir.exists():
                    shutil.rmtree(self.runtime_dir)
                shutil.move(str(merged), str(self.runtime_dir))
                manifest = {
                    "release": release.get("tag_name"),
                    "variant": variant,
                    "assets": [asset.get("name") for asset in assets],
                    "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "driver_cuda": self.driver_cuda_version(),
                }
                self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            finally:
                shutil.rmtree(staging, ignore_errors=True)
            if not self.runtime_ready():
                raise LocalLLMError("llama.cpp 執行核心安裝後仍無法通過完整性檢查。")
            return self.server_path

    def ensure_model(self, progress_cb=None, log_fn=None, *, preflight: bool = True) -> Path:
        with self._lock:
            if self.model_ready():
                return self.model_path
            if preflight:
                self.preflight_disk_space(log_fn=log_fn)
            if self.model_path.exists() and self.model_path.stat().st_size == MODEL_SIZE:
                if log_fn:
                    log_fn("本地 AI：驗證既有 Breeze 模型，不會重新下載。")
                actual = self._sha256(self.model_path, progress_cb, "Breeze-7B 模型 SHA256")
                if actual.lower() == MODEL_SHA256:
                    self.model_path.with_suffix(self.model_path.suffix + ".sha256").write_text(MODEL_SHA256, encoding="ascii")
                    return self.model_path
                self.model_path.unlink(missing_ok=True)
            if log_fn:
                log_fn("本地 AI：下載 Breeze-7B-Instruct v1.0 Q4_K_M（約 4.54GB）。")
            self.model_dir.mkdir(parents=True, exist_ok=True)
            self._download(
                MODEL_URL,
                self.model_path,
                size=MODEL_SIZE,
                sha256=MODEL_SHA256,
                progress_cb=progress_cb,
                label="Breeze-7B 模型",
            )
            self.model_path.with_suffix(self.model_path.suffix + ".sha256").write_text(MODEL_SHA256, encoding="ascii")
            return self.model_path

    def ensure_assets(self, progress_cb=None, log_fn=None) -> dict:
        if not self.runtime_ready() or not self.model_ready():
            self.preflight_disk_space(log_fn=log_fn)
        self.ensure_runtime(progress_cb=progress_cb, log_fn=log_fn, preflight=False)
        self.ensure_model(progress_cb=progress_cb, log_fn=log_fn, preflight=False)
        return self.status()

    @staticmethod
    def _find_port(start: int = 8080, stop: int = 8180) -> int:
        for port in range(start, stop + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _engine_tuning(self) -> dict:
        gpu = self.gpu_info()
        vram = int(gpu.get("vram_mb") or 0)
        if vram >= 10_000:
            return {"context": 8192, "gpu_layers": 99}
        if vram >= 7_000:
            return {"context": 6144, "gpu_layers": 99}
        if vram >= 5_500:
            return {"context": 4096, "gpu_layers": 24}
        if vram >= 3_500:
            return {"context": 4096, "gpu_layers": 12}
        return {"context": 4096, "gpu_layers": 0}

    def _health_ok(self, port: int, timeout: float = 2.0) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as response:
                return response.status == 200
        except Exception:
            return False

    def is_running(self) -> bool:
        process = self._process
        return bool(process is not None and process.poll() is None and self._port and self._health_ok(self._port, 0.5))

    def _launch_env(self) -> dict:
        """Prefer bundled llama CUDA DLLs over any system CUDA Toolkit on PATH.

        RTX 50 / CUDA 13 套件若先載入本機 Toolkit 13.0 的 cudart，可能出現
        ``failed to initialize CUDA: (null)``，最後退化成極慢的 CPU 推論。
        """
        env = os.environ.copy()
        runtime = str(self.server_path.parent.resolve())
        path_parts = [part for part in env.get("PATH", "").split(os.pathsep) if part]
        filtered: list[str] = []
        for part in path_parts:
            low = part.replace("/", "\\").lower()
            # 略過系統 CUDA Toolkit，避免與 llama 內建 cudart/cublas 混用
            if "nvidia gpu computing toolkit" in low:
                continue
            if "\\cuda\\v" in low and "\\bin" in low:
                continue
            if part not in filtered:
                filtered.append(part)
        env["PATH"] = os.pathsep.join([runtime] + filtered)
        # 不要沿用可能指向 Toolkit 的 CUDA_PATH
        for key in ("CUDA_PATH", "CUDA_PATH_V13_0", "CUDA_PATH_V12_4", "CUDA_HOME"):
            env.pop(key, None)
        return env

    def _launch(self, *, gpu_layers: int, flash_attention: bool, log_fn=None) -> None:
        port = self._find_port()
        tuning = self._engine_tuning()
        threads = max(1, min(8, os.cpu_count() or 4))
        cmd = [
            str(self.server_path),
            "-m", str(self.model_path),
            "--host", "127.0.0.1",
            "--port", str(port),
            "-c", str(tuning["context"]),
            "-ngl", str(gpu_layers),
            "-t", str(threads),
            "--alias", LOCAL_MODEL_ALIAS,
        ]
        if flash_attention:
            cmd.extend(["-fa", "on"])
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_dir / "llama-server.log"
        self._log_handle = log_path.open("a", encoding="utf-8")
        launch_env = self._launch_env()
        self._log_handle.write("\n" + time.strftime("[%Y-%m-%d %H:%M:%S] ") + " ".join(cmd) + "\n")
        self._log_handle.write(
            time.strftime("[%Y-%m-%d %H:%M:%S] ")
            + f"PATH(head)={launch_env.get('PATH', '').split(os.pathsep)[0]}\n"
        )
        self._log_handle.flush()
        self._process = subprocess.Popen(
            cmd,
            cwd=str(self.server_path.parent),
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            creationflags=self._creationflags(),
            env=launch_env,
        )
        self._port = port
        self._last_gpu_layers = int(gpu_layers)
        if log_fn:
            mode = f"GPU layers={gpu_layers}" if gpu_layers else "CPU 備援"
            log_fn(f"本地 AI：正在啟動 {mode}，連接埠 {port}。")

    def _report_runtime_mode(self, *, requested_gpu_layers: int, log_fn=None) -> None:
        """After health OK, warn clearly if CUDA failed and inference is CPU-like."""
        cuda_failed = self._detect_cuda_failure()
        self._cuda_init_failed = cuda_failed
        on_cpu = (requested_gpu_layers <= 0) or cuda_failed
        self._running_on_cpu = on_cpu
        if not log_fn:
            return
        gpu = self.gpu_info()
        gpu_name = gpu.get("name") or "（未偵測到 NVIDIA GPU）"
        if cuda_failed and requested_gpu_layers > 0:
            log_fn(
                f"本地 AI：警告 — CUDA 初始化失敗，雖然啟動參數含 GPU layers={requested_gpu_layers}，"
                f"但目前很可能以 CPU 推論（顯示卡：{gpu_name}）。"
                "速度會慢很多，漏回／逾時風險也較高。"
                "已嘗試優先載入 SanWich 內建 CUDA DLL；若仍失敗請更新 NVIDIA 驅動、"
                "關閉佔用 VRAM 的程式，或暫時改用 DeepSeek／Gemini 雲端校對。"
                f"詳見 {self.log_dir / 'llama-server.log'}。"
            )
        elif requested_gpu_layers <= 0:
            log_fn(
                f"本地 AI：目前為 CPU 備援模式（顯示卡：{gpu_name}）。"
                "若本機有可用 NVIDIA GPU，建議檢查驅動與 CUDA runtime。"
            )
        else:
            log_fn(
                f"本地 AI：GPU 模式就緒（layers={requested_gpu_layers}，{gpu_name}）；"
                f"字幕內容只送往 127.0.0.1:{self._port}。"
            )

    def ensure_running(self, progress_cb=None, log_fn=None, timeout: float = 150.0) -> str:
        with self._lock:
            # 舊行程若已是 CUDA 失敗的 CPU 慢速實例，強制重啟以套用新 runtime。
            if self.is_running() and not self._running_on_cpu and not self._cuda_init_failed:
                return f"http://127.0.0.1:{self._port}"
            if self.is_running() and (self._running_on_cpu or self._cuda_init_failed):
                if log_fn:
                    log_fn("本地 AI：偵測到先前 CUDA 失敗／CPU 模式，正在重新啟動以嘗試 GPU…")
                self.stop()

            # 裝錯 CUDA 大版號時（例如驅動 12.9 卻裝 13.3）自動重裝正確套件。
            desired = self.runtime_variant()
            installed = self.installed_variant()
            if installed and installed != desired:
                if log_fn:
                    log_fn(
                        f"本地 AI：執行核心不符（已裝 {installed} → 需要 {desired}），自動重裝。"
                    )
                self.reinstall_runtime(variant=desired, progress_cb=progress_cb, log_fn=log_fn)
            else:
                self.ensure_assets(progress_cb=progress_cb, log_fn=log_fn)

            tuning = self._engine_tuning()
            attempts = [
                (int(tuning["gpu_layers"]), True),
                (int(tuning["gpu_layers"]), False),
            ]
            if tuning["gpu_layers"]:
                attempts.append((0, False))
            last_error = ""
            cuda_reinstall_tried = False
            for gpu_layers, flash in attempts:
                self.stop()
                self._launch(gpu_layers=gpu_layers, flash_attention=flash, log_fn=log_fn)
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if self._process is not None and self._process.poll() is not None:
                        last_error = f"llama-server 結束碼 {self._process.returncode}"
                        break
                    if self._port and self._health_ok(self._port):
                        # Give the server a moment to flush CUDA init errors into the log.
                        time.sleep(0.35)
                        self._report_runtime_mode(requested_gpu_layers=gpu_layers, log_fn=log_fn)
                        # 若 CUDA 仍失敗且目前是 13.3，降級重裝 12.4 再試一次。
                        if (
                            self._cuda_init_failed
                            and gpu_layers > 0
                            and not cuda_reinstall_tried
                            and self.runtime_variant() == "cuda-13.3"
                        ):
                            cuda_reinstall_tried = True
                            if log_fn:
                                log_fn(
                                    "本地 AI：cuda-13.3 仍無法初始化 CUDA，改裝 cuda-12.4 重試"
                                    "（常見於驅動最高僅支援 CUDA 12.x）。"
                                )
                            self.stop()
                            self.reinstall_runtime(
                                variant="cuda-12.4",
                                progress_cb=progress_cb,
                                log_fn=log_fn,
                            )
                            # Restart attempt loop with new runtime.
                            return self.ensure_running(
                                progress_cb=progress_cb,
                                log_fn=log_fn,
                                timeout=timeout,
                            )
                        if log_fn:
                            log_fn(f"本地 AI：已就緒，字幕內容只送往 127.0.0.1:{self._port}。")
                        return f"http://127.0.0.1:{self._port}"
                    time.sleep(0.4)
                else:
                    last_error = "模型載入逾時"
            self.stop()
            log_path = self.log_dir / "llama-server.log"
            raise LocalLLMError(f"本地 AI 啟動失敗：{last_error}。請查看 {log_path}")

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
            self._port = None
            self._last_gpu_layers = 0
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
            if self._log_handle is not None:
                try:
                    self._log_handle.close()
                except Exception:
                    pass
            self._log_handle = None


MANAGER = LocalLLMManager()
