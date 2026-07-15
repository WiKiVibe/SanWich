# -*- coding: utf-8 -*-
"""v2.4.6 效能實驗開關與評測工具。

Silero VAD、CTranslate2／faster-whisper 後端預設關閉。
通過同一批素材評測後，才由設定開啟；失敗可一鍵回退。
"""

from __future__ import annotations

import datetime as _dt
import json
import time
from pathlib import Path
from typing import Callable


DEFAULT_FLAGS = {
    "use_silero_vad": False,
    "use_ctranslate2": False,
    "vad_min_silence_ms": 500,
    "vad_speech_pad_ms": 200,
    "ct2_compute_type": "float16",  # float16 / int8_float16 / int8
    "ct2_beam_size": 1,
    "last_benchmark": None,
}


def experiments_path(user_data: Path) -> Path:
    return Path(user_data) / "experiments.json"


class ExperimentConfig:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.flags = dict(DEFAULT_FLAGS)
        if self.path.exists():
            self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        for key in DEFAULT_FLAGS:
            if key in raw:
                self.flags[key] = raw[key]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(self.flags)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, key: str, default=None):
        return self.flags.get(key, default)

    def set(self, key: str, value) -> None:
        self.flags[key] = value

    def enabled_summary(self) -> str:
        parts = []
        if self.flags.get("use_silero_vad"):
            parts.append("Silero VAD")
        if self.flags.get("use_ctranslate2"):
            parts.append(f"CTranslate2({self.flags.get('ct2_compute_type')})")
        return "、".join(parts) if parts else "皆關閉（官方 Breeze transformers）"


def try_load_silero_vad():
    """嘗試載入 Silero VAD；失敗回 (None, error)。"""
    try:
        import torch
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
            verbose=False,
        )
        get_speech_timestamps = utils[0]
        return (model, get_speech_timestamps), None
    except Exception as exc:
        return None, str(exc)


def split_by_vad(
    samples,
    sample_rate: int,
    *,
    min_silence_ms: int = 500,
    speech_pad_ms: int = 200,
    max_segment_s: float = 30.0,
    log: Callable | None = None,
) -> list[tuple[int, int]]:
    """
    回傳樣本 index 區間 [(start, end), ...]。
    失敗時回傳單一全段，呼叫端可回退固定切段。
    """
    import numpy as np

    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=-1)
    loaded, err = try_load_silero_vad()
    if loaded is None:
        if log:
            log(f"Silero VAD 無法載入，改用固定切段：{err}", "warn")
        return [(0, len(audio))]
    model, get_speech_timestamps = loaded
    try:
        import torch
        tensor = torch.from_numpy(audio)
        if sample_rate != 16000:
            # 簡易重採樣提示：呼叫端應已是 16k
            if log:
                log(f"VAD 收到 {sample_rate} Hz（建議 16k）", "warn")
        timestamps = get_speech_timestamps(
            tensor,
            model,
            sampling_rate=sample_rate,
            min_silence_duration_ms=min_silence_ms,
            speech_pad_ms=speech_pad_ms,
            return_seconds=False,
        )
        if not timestamps:
            return [(0, len(audio))]
        max_len = int(max_segment_s * sample_rate)
        spans: list[tuple[int, int]] = []
        for ts in timestamps:
            s = int(ts["start"])
            e = int(ts["end"])
            while e - s > max_len:
                spans.append((s, s + max_len))
                s += max_len
            if e > s:
                spans.append((s, e))
        if log:
            log(f"Silero VAD：切成 {len(spans)} 段語音。", "model")
        return spans or [(0, len(audio))]
    except Exception as exc:
        if log:
            log(f"Silero VAD 失敗，回退固定切段：{exc}", "warn")
        return [(0, len(audio))]


def try_ctranslate2_available() -> tuple[bool, str]:
    try:
        import ctranslate2  # noqa: F401
        import faster_whisper  # noqa: F401
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def run_micro_benchmark(
    *,
    audio_seconds: float,
    backend_name: str,
    elapsed_s: float,
    extra: dict | None = None,
) -> dict:
    """記錄一次微評測結果（不自動改設定）。"""
    rtf = (elapsed_s / audio_seconds) if audio_seconds > 0 else None
    result = {
        "time": _dt.datetime.now().isoformat(timespec="seconds"),
        "backend": backend_name,
        "audio_seconds": round(float(audio_seconds), 2),
        "elapsed_seconds": round(float(elapsed_s), 2),
        "realtime_factor": round(rtf, 3) if rtf is not None else None,
        "extra": extra or {},
    }
    return result


class Timer:
    def __init__(self):
        self.t0 = time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self.t0


def estimate_remaining(done: int, total: int, elapsed_s: float) -> str:
    if done <= 0 or total <= 0 or elapsed_s <= 0:
        return "估算中…"
    rate = done / elapsed_s
    left = max(0, total - done)
    sec = int(left / rate) if rate > 0 else 0
    if sec < 60:
        return f"約剩餘 {sec} 秒"
    mins, s = divmod(sec, 60)
    if mins < 60:
        return f"約剩餘 {mins} 分 {s} 秒"
    hours, m = divmod(mins, 60)
    return f"約剩餘 {hours} 小時 {m} 分"


def format_duration(seconds: float) -> str:
    sec = max(0, int(seconds))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def check_disk_space_gb(path: Path | None = None) -> float | None:
    try:
        import shutil
        target = Path(path) if path else Path.home()
        usage = shutil.disk_usage(str(target))
        return round(usage.free / (1024 ** 3), 2)
    except Exception:
        return None


__all__ = [
    "DEFAULT_FLAGS",
    "ExperimentConfig",
    "Timer",
    "check_disk_space_gb",
    "estimate_remaining",
    "experiments_path",
    "format_duration",
    "run_micro_benchmark",
    "split_by_vad",
    "try_ctranslate2_available",
    "try_load_silero_vad",
]
