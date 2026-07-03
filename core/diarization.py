"""
SanWich 語者分離（Speaker Diarization）模組  v2.1

設計原則：
  * 只服務 TXT 輸出。SRT 完全不經過這裡，維持原本格式、不含語者。
  * 離線、輕量：使用 sherpa-onnx（純 ONNX runtime，不需 PyTorch）。
  * 中文準確度：embedding 採用 3D-Speaker ERes2Net（經實測在四人訪談勝過 CAM++）。
  * 一律用「指定人數」分群（自動偵測不可靠）。指定人數會收斂到自然群數，指定偏多也安全。
  * 首次使用自動下載模型到 core/models/diarization/，之後離線可用、可隨程式打包。

對外主要函式：
  diarize_array(samples, sr, num_speakers, ...)  -> [(start, end, speaker_int), ...]
  assign_speakers_to_chunks(chunks, turns)       -> chunks（每段多一個 "speaker"）[純函式]
  chunks_to_speaker_txt(chunks)                  -> 帶「講者A：」分段的純文字       [純函式]

此模組不可 import 專案內其他模組（主程式以 importlib 載入它）。
"""

from __future__ import annotations

import os
import shutil
import tarfile
import urllib.request
from pathlib import Path

# 切段模型（pyannote segmentation 3.0）
SEG_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
)
# 語者特徵模型（3D-Speaker ERes2Net base，中文；tag 是官方拼錯的 recongition）
EMB_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
)

SEG_FILENAME = "seg-pyannote-segmentation-3.onnx"
EMB_FILENAME = "3dspeaker_eres2net_base_zh.onnx"

_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# ===== 純函式（不需模型／網路，可單元測試）=====

def speaker_label(idx) -> str:
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        return "?"
    if 0 <= idx < len(_LABELS):
        return _LABELS[idx]
    return f"S{idx + 1}"


def _chunk_span(chunk):
    ts = chunk.get("timestamp")
    if ts is None:
        ts = (chunk.get("start", 0.0), chunk.get("end", 0.0))
    start = ts[0] if ts[0] is not None else 0.0
    end = ts[1] if ts[1] is not None else start
    if end < start:
        end = start
    return float(start), float(end)


def _overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _nearest_speaker(t, turns, default=0):
    best, best_dist = default, None
    for (t0, t1, spk) in turns:
        dist = 0.0 if t0 <= t <= t1 else min(abs(t - t0), abs(t - t1))
        if best_dist is None or dist < best_dist:
            best_dist, best = dist, spk
    return best


def assign_speakers_to_chunks(chunks, turns):
    """每個字幕 chunk 依時間重疊最久的語者指派；平手時選時間段較短(較貼近)者；無重疊取最近。"""
    out = []
    last_spk = turns[0][2] if turns else 0
    for chunk in chunks:
        nc = dict(chunk)
        start, end = _chunk_span(nc)
        best_spk, best_key = None, None
        for (t0, t1, spk) in turns:
            ov = _overlap(start, end, t0, t1)
            if ov <= 0.0:
                continue
            key = (ov, -(t1 - t0))
            if best_key is None or key > best_key:
                best_key, best_spk = key, spk
        if best_spk is None:
            best_spk = _nearest_speaker((start + end) / 2.0, turns, default=last_spk) if turns else last_spk
        nc["speaker"] = best_spk
        last_spk = best_spk
        out.append(nc)
    return out


def _appearance_order(chunks):
    order = {}
    for chunk in chunks:
        if not (chunk.get("text") or "").strip():
            continue
        spk = chunk.get("speaker")
        if spk not in order:
            order[spk] = len(order)
    return order


def chunks_to_speaker_txt(chunks, label_map=None):
    """連續同語者句子併段，前面加「講者A：」；中文不加空白直接相接。"""
    order = _appearance_order(chunks)
    paragraphs = []
    cur_spk = object()
    buf = []
    for chunk in chunks:
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        spk = chunk.get("speaker")
        if spk != cur_spk and buf:
            paragraphs.append((cur_spk, "".join(buf)))
            buf = []
        cur_spk = spk
        buf.append(text)
    if buf:
        paragraphs.append((cur_spk, "".join(buf)))
    lines = []
    for spk, body in paragraphs:
        label = label_map.get(spk) if (label_map and spk in label_map) else speaker_label(order.get(spk, 0))
        lines.append(f"講者{label}：{body.strip()}")
    return ("\n\n".join(lines).strip() + "\n") if lines else ""


def count_speakers(chunks):
    return len({c.get("speaker") for c in chunks if (c.get("text") or "").strip()})


# ===== 模型管理（首次自動下載）=====

def models_dir(base):
    base = Path(base) if base else Path(__file__).resolve().parent.parent
    return base / "core" / "models" / "diarization"


def _download(url, dest, log=None, label=""):
    if log:
        log(f"語者分離：下載{label}中…（首次使用，請保持網路連線）", "model")
    tmp = Path(str(dest) + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "SanWich/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(tmp, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    tmp.replace(dest)
    if log:
        log(f"語者分離：{label}下載完成。", "success")


def _download_segmentation(d, seg_dest, log=None):
    archive = d / "_seg.tar.bz2"
    _download(SEG_URL, archive, log=log, label="切段模型")
    try:
        with tarfile.open(archive, "r:bz2") as tar:
            member = next((m for m in tar.getmembers() if m.name.endswith("model.onnx")), None)
            if member is None:
                raise RuntimeError("切段模型壓縮檔內找不到 model.onnx。")
            member.name = Path(member.name).name
            tar.extract(member, path=str(d))
        (d / "model.onnx").replace(seg_dest)
    finally:
        archive.unlink(missing_ok=True)


def ensure_models(base, log=None):
    d = models_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    seg = d / SEG_FILENAME
    emb = d / EMB_FILENAME
    if not seg.exists():
        _download_segmentation(d, seg, log=log)
    if not emb.exists():
        _download(EMB_URL, emb, log=log, label="3D-Speaker 語者模型")
    return seg, emb


# ===== 執行語者分離 =====

def _import_sherpa(log=None):
    try:
        import sherpa_onnx  # noqa: F401
        return sherpa_onnx
    except ImportError:
        pass
    import sys
    if getattr(sys, "frozen", False):
        raise RuntimeError("此版本未內建語者分離元件（sherpa-onnx），請重新執行安裝程式。")
    if log:
        log("語者分離：未偵測到 sherpa-onnx，正在自動安裝（首次使用，約需 1 分鐘）…", "model")
    import subprocess
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "sherpa-onnx"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:
        raise RuntimeError("未安裝 sherpa-onnx 且自動安裝失敗。請在 .venv 執行：pip install sherpa-onnx\n"
                           f"（錯誤：{exc}）") from exc
    import sherpa_onnx  # noqa: F401
    if log:
        log("語者分離：sherpa-onnx 安裝完成。", "success")
    return sherpa_onnx


def _ascii_safe_model_path(path, log=None):
    """sherpa-onnx 在 Windows 對非 ASCII（中文）路徑開檔常失敗；回傳純 ASCII 可用路徑。"""
    p = str(path)
    if all(ord(c) < 128 for c in p):
        return p
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            _short = ctypes.windll.kernel32.GetShortPathNameW
            _short.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
            _short.restype = wintypes.DWORD
            buf = ctypes.create_unicode_buffer(1024)
            if _short(p, buf, 1024) and all(ord(c) < 128 for c in buf.value):
                return buf.value
        except Exception:
            pass
    import tempfile
    for base in (Path(tempfile.gettempdir()) / "sanwich_diar", Path("C:/sanwich_diar")):
        try:
            base.mkdir(parents=True, exist_ok=True)
            dest = base / Path(path).name
            if (not dest.exists()) or dest.stat().st_size != Path(path).stat().st_size:
                shutil.copy2(str(path), str(dest))
            if all(ord(c) < 128 for c in str(dest)):
                if log:
                    log(f"語者分離：模型複製到 ASCII 路徑 {dest}", "model")
                return str(dest)
        except Exception:
            continue
    return p


def _resample(audio, sr_in, sr_out):
    import numpy as np
    if sr_in == sr_out:
        return audio.astype(np.float32)
    n_out = int(round(len(audio) * sr_out / float(sr_in)))
    if n_out <= 0:
        return audio.astype(np.float32)
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def diarize_array(samples, sr, num_speakers=None, threshold=0.5,
                  models_base=None, log=None, progress=None):
    """
    對 16k mono float32 音訊做語者分離。
    num_speakers：>0 -> 指定人數（建議；可填實際人數，偏多也安全）；None/<=0 -> 自動(不建議)。
    回傳依開始時間排序的 [(start, end, speaker_int), ...]。
    """
    import numpy as np
    sherpa_onnx = _import_sherpa(log=log)
    seg_model, emb_model = ensure_models(models_base, log=log)
    seg_model = _ascii_safe_model_path(seg_model, log=log)
    emb_model = _ascii_safe_model_path(emb_model, log=log)

    nthreads = max(1, min(4, (os.cpu_count() or 2)))
    num_clusters = int(num_speakers) if (num_speakers and num_speakers > 0) else -1
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(seg_model)),
            num_threads=nthreads,
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(emb_model), num_threads=nthreads),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=num_clusters, threshold=float(threshold)),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise RuntimeError(
            "語者分離設定無效（模型無法載入）。"
            f"seg存在={os.path.exists(str(seg_model))}, emb存在={os.path.exists(str(emb_model))}"
        )
    sd = sherpa_onnx.OfflineSpeakerDiarization(config)
    audio = np.asarray(samples, dtype=np.float32)
    if sr != sd.sample_rate:
        audio = _resample(audio, sr, sd.sample_rate)

    def _cb(processed, total, *_):
        if progress:
            try:
                progress(processed, total)
            except Exception:
                pass
        return 0

    try:
        result = sd.process(audio, callback=_cb)
    except TypeError:
        result = sd.process(audio)
    segments = result.sort_by_start_time()
    return [(float(s.start), float(s.end), int(s.speaker)) for s in segments]
