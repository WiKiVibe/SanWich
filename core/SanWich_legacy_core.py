"""
dual_asr_gui.py
Breeze-ASR-25 語音轉文字 + AI 總編輯校對
搭配多家 AI API 進行台灣國語 / 台語校對
"""

import datetime
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import wave
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _HAS_DND = True
except Exception:
    DND_FILES = None
    TkinterDnD = None
    _HAS_DND = False

try:
    import jieba
    _HAS_JIEBA = True
except Exception:
    jieba = None
    _HAS_JIEBA = False

# ── 模型 ID ──────────────────────────────────────────────
BREEZE_MODEL_ID = "MediaTek-Research/Breeze-ASR-25"

# ── 介面常數 ─────────────────────────────────────────────
FONT_FAMILY    = "Microsoft JhengHei UI"
SEGMENT_SECONDS = 60
SRT_MAX_LINE_WIDTH = 15.0
MEDIA_EXTS = {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".mkv", ".flac", ".aac", ".ogg", ".webm"}
MEDIA_FILETYPES = [("媒體檔案", "*.mp3 *.wav *.m4a *.mp4 *.mov *.mkv *.flac *.aac *.ogg *.webm"),
                   ("所有檔案", "*.*")]

BG           = "#0B0F14"
PANEL        = "#151C24"
PANEL2       = "#1C2534"
BORDER       = "#2A3441"
TEXT         = "#E6EDF3"
MUTED        = "#8B97A6"
ACCENT       = "#DF7959"
ACCENT2      = "#A78BFA"     # AI校對紫
ACCENT_HOVER = "#E79B82"
SUCCESS      = "#4ADE80"
ERROR        = "#F87171"
WARN         = "#FBBF24"
ENTRY_BG     = "#0F151C"

# ── 總編輯 Prompt（SRT 結構鎖死版）─────────────────────────
EDITOR_SYSTEM_PROMPT = (
    "你是一個台灣電視節目的字幕總編輯。我會提供你一段標準的 SRT 字幕檔案。\n"
    "你的任務是校正辨識錯字與專有名詞，讓字幕自然、準確、可播出；不要重寫成摘要。"
    "標點符號僅在明顯錯誤時才修改，不要為了風格或個人偏好重排標點。\n\n"
    "【鋼鐵律令：時間碼框架絕對鎖死，文字允許流動】\n"
    "1. 「序號」與「時間碼」（例如 00:01:23,456 --> 00:01:25,123）是不可觸碰的底線。輸入有幾組，輸出就必須有幾組，絕對不可刪除、合併或修改時間碼。\n"
    "2. 「文字內容」是流動的。你可以為了語意通順，將文字跨組搬移到上一組或下一組，只要確保「時間碼與序號」的框架原封不動即可。\n"
    "3. 如果某一行整句都是無意義的重複字（如：喔喔喔喔）或 AI 幻覺，請「保留序號與時間碼」，只將下方的文字直接「刪除留空」，絕對不可以把那一組時間碼整塊刪掉！\n\n"
    "【文字清洗與校對規則】\n"
    "1. 修正台灣國語與台語錯別字。\n"
    "2. 【「姐」與「姊」的嚴格區分】：口語中的尊稱、稱呼（如：長輩、同事、熟人、車友），一律使用「姐姐」、「姐」。除非上下文明確指出對方是「有血緣關係的親生姊姊」，才可以使用女字旁的「姊姊」、「姊」。\n"
    "3. 只刪除明顯不影響語意的口水詞與重複語氣詞（如：嗯、啊、喔、那個、就是、對對對、然後然後）。如果刪除後會讓原意變短、變弱或少掉資訊，請保留原句。\n"
    "4. 嚴禁把逐字稿改寫成精簡摘要；不得自行濃縮、合併重點、刪掉細節、改變說話者語氣或新增原文沒有的內容。\n"
    "5. 儘量維持原字幕字數與資訊量。除了明顯錯字、斷句、專有名詞與無意義贅詞外，不要大幅縮短句子。\n"
    "6. 數字統一為阿拉伯數字（二零二六→2026）。英文專有名詞統一常用大小寫（AI、API、DaVinci）。人稱指人類用「他」，指非人類（軟體、摩托車、系統）一律用「它」。\n"
    "7. 【「或是」強制跨組搬移】：當某組字幕的結尾是「或是」時，請將「或是」搬移至下一組字幕的開頭。此為合法的文字流動，請安心執行。\n"
    "   例如輸入：\n"
    "   1\n"
    "   00:00:01,000 --> 00:00:03,000\n"
    "   你們的命運將交給老闆或是\n\n"
    "   2\n"
    "   00:00:03,500 --> 00:00:05,000\n"
    "   客人來決定\n\n"
    "   處理後應輸出：\n"
    "   1\n"
    "   00:00:01,000 --> 00:00:03,000\n"
    "   你們的命運將交給老闆\n\n"
    "   2\n"
    "   00:00:03,500 --> 00:00:05,000\n"
    "   或是客人來決定\n\n"
    "輸出格式：直接輸出校對完成後的標準 SRT 內容，嚴禁添加任何額外的解釋與說明。"
    "8. 專有名詞請依照台灣官方或常用譯名，或依照官方網站、新聞媒體、維基百科等可靠來源為準。"
    "9. 請保留原 SRT 的換行格式，一行不超過13個中文字元，沒有標點符號，若超過則自動換行。"
    "10.請主動將中國大陸用語改為台灣慣用語，例如「視頻→影片」「軟件→軟體」「信息→資訊／訊息」「鼠標→滑鼠」「打印→列印」「外賣→外送」「快遞→宅配」「公交→公車」「地鐵→捷運」「出租車→計程車」「酒店→飯店」「質量→品質」。請依上下文判斷，不要機械式替換，並避免不符合台灣語感的句式。"
)

# ── 文字修正 Prompt（可在設定中開關）────────────────────────
TEXT_FIX_PROMPT = (
    "針對原 SRT 與純文字中的『錯別字、簡體字、中國大陸用語、專有名詞』"
    "進行文字修正與替換。"
)

SRT_FORMAT_ONLY_PROMPT = (
    "你是 SRT 字幕格式助手。請嚴格保留輸入的序號與時間碼，不可刪除、合併、重新排序或修改任何時間碼。\n"
    "若沒有其他明確修改指令，請盡量保留字幕文字原樣，只維持標準 SRT 格式並直接輸出結果，不要添加解釋。"
)

# ── 設定檔路徑 ────────────────────────────────────────────
def app_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

CONFIG_PATH = app_dir() / "config.json"


def resource_path(name: str) -> Path:
    base = app_dir()
    candidates = [
        base / name,
        base / "_assets" / name,
        Path(getattr(sys, "_MEIPASS", base)) / name,
        Path(getattr(sys, "_MEIPASS", base)) / "_assets" / name,
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def set_app_user_model_id():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WiKi.SanWich")
    except Exception:
        pass


def relaunch_in_local_venv():
    if getattr(sys, "frozen", False):
        return
    venv_python = app_dir() / ".venv" / "Scripts" / "pythonw.exe"
    if not venv_python.exists():
        venv_python = app_dir() / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        return
    try:
        current = Path(sys.executable).resolve()
        target = venv_python.resolve()
    except Exception:
        current = Path(sys.executable)
        target = venv_python
    if current != target:
        os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])


relaunch_in_local_venv()

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"api_provider": "gemini", "api_key": "", "model": "gemini-2.5-flash", "use_llm": False, "use_text_fix": False, "output_srt_enabled": True, "output_txt_enabled": True}

def save_config(cfg: dict):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
#  UI 元件
# ═══════════════════════════════════════════════════════════

def enable_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class TranscriptionCancelled(Exception):
    pass


class PillButton(tk.Canvas):
    def __init__(self, parent, text, command=None, *, min_width=112, height=38,
                 bg_color=ACCENT, hover_color=ACCENT_HOVER, fg_color="#061018",
                 disabled_color=BORDER, disabled_fg=MUTED, font_size=10, bold=False):
        self.text        = text
        self.command     = command
        self.state       = "normal"
        self.bg_color    = bg_color
        self.hover_color = hover_color
        self.fg_color    = fg_color
        self.disabled_color = disabled_color
        self.disabled_fg    = disabled_fg
        self.normal_font = tkfont.Font(family=FONT_FAMILY, size=font_size, weight="bold" if bold else "normal")
        width = max(min_width, self.normal_font.measure(text) + 34)
        super().__init__(parent, width=width, height=height,
                         bg=parent.cget("bg"), highlightthickness=0, bd=0, cursor="hand2")
        self.width  = width
        self.height = height
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda _e: self._draw(hover=True))
        self.bind("<Leave>", lambda _e: self._draw(hover=False))
        self._draw()

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kw):
        pts = [x1+radius,y1, x2-radius,y1, x2,y1, x2,y1+radius,
               x2,y2-radius, x2,y2, x2-radius,y2, x1+radius,y2,
               x1,y2, x1,y2-radius, x1,y1+radius, x1,y1]
        return self.create_polygon(pts, smooth=True, splinesteps=18, **kw)

    def _draw(self, hover=False):
        self.delete("all")
        enabled = self.state != "disabled"
        fill = self.hover_color if (hover and enabled) else self.bg_color
        fg   = self.fg_color
        if not enabled:
            fill, fg = self.disabled_color, self.disabled_fg
        self._rounded_rect(1, 1, self.width-1, self.height-1, self.height//2, fill=fill, outline=fill)
        self.create_text(self.width//2, self.height//2, text=self.text, fill=fg, font=self.normal_font)

    def _click(self, _e):
        if self.state != "disabled" and self.command:
            self.command()

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        for attr in ("state", "text", "command"):
            if attr in kw:
                setattr(self, attr, kw.pop(attr))
                if attr != "command":
                    self._draw()
        if kw:
            super().configure(**kw)
    config = configure


class StatusDot(tk.Canvas):
    """三色狀態點：idle / running / done / error"""
    COLORS = {"idle": MUTED, "running": WARN, "done": SUCCESS, "error": ERROR}
    def __init__(self, parent, size=10):
        super().__init__(parent, width=size, height=size,
                         bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self._size   = size
        self._status = "idle"
        self._draw()
    def set(self, status: str):
        self._status = status
        self._draw()
    def _draw(self):
        self.delete("all")
        c = self.COLORS.get(self._status, MUTED)
        s = self._size
        self.create_oval(1, 1, s-1, s-1, fill=c, outline=c)


# ═══════════════════════════════════════════════════════════
#  音訊工具
# ═══════════════════════════════════════════════════════════

def find_ffmpeg() -> str | None:
    candidates = [
        app_dir() / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
        app_dir() / "ffmpeg" / "bin" / "ffmpeg.exe",
        app_dir() / "ffmpeg.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which("ffmpeg")


def convert_to_wav(input_path: str, log_fn) -> str:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "找不到 ffmpeg.exe。\n\n"
            "請安裝 FFmpeg，或把 ffmpeg.exe 放在本程式旁邊的 tools\\ffmpeg\\bin\\ 裡。"
        )
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.close()
    log_fn("正在轉成 16 kHz 單聲道 WAV...")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-i", input_path, "-vn", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", tmp.name]
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.run(cmd, check=True, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=creationflags)
    except subprocess.CalledProcessError as e:
        Path(tmp.name).unlink(missing_ok=True)
        raise RuntimeError(f"FFmpeg 轉檔失敗：\n{(e.stderr or e.stdout or '').strip()}")
    return tmp.name


def read_wav_mono_16k(wav_path: str) -> dict:
    import numpy as np
    with wave.open(wav_path, "rb") as w:
        channels     = w.getnchannels()
        sample_width = w.getsampwidth()
        sample_rate  = w.getframerate()
        frames       = w.readframes(w.getnframes())
    if channels != 1 or sample_width != 2 or sample_rate != 16000:
        raise RuntimeError("WAV 格式不正確，預期 16 kHz / mono / 16-bit PCM。")
    audio = __import__("numpy").frombuffer(frames, dtype=__import__("numpy").int16).astype(__import__("numpy").float32) / 32768.0
    return {"array": audio, "sampling_rate": 16000}


# ═══════════════════════════════════════════════════════════
#  SRT 工具
# ═══════════════════════════════════════════════════════════

def seconds_to_srt_time(seconds: float) -> str:
    seconds   = max(0.0, float(seconds or 0.0))
    total_ms  = int(round(seconds * 1000))
    h, r      = divmod(total_ms, 3_600_000)
    m, r      = divmod(r, 60_000)
    s, ms     = divmod(r, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_timestamp(seconds: float) -> str:
    """Backwards-compatible alias used by the AI proofreading path."""
    return seconds_to_srt_time(seconds)


# 所有需要從 SRT 文字中移除的標點符號
def _build_srt_punct():
    zh = (
        "\uff0c\u3002\uff01\uff1f\uff1b\uff1a\u3001"
        "\u300c\u300d\u300e\u300f\u3010\u3011\u3014\u3015"
        "\u3008\u3009\u300a\u300b\u3016\u3017"
        "\u201c\u201d\u2018\u2019\u2014\u2013\u2026\u00b7"
        "\uff5e\uff08\uff09\uff0e\uff1c\uff1e"
    )
    asc = r""",\.!?;:\'\"()\-_+=|<>/@#^&*~`[]{}\\"""
    import re as _re
    return _re.compile("[" + _re.escape(zh + asc) + "]")

_SRT_PUNCT_RE = _build_srt_punct()

def strip_punct_for_srt(text: str) -> str:
    """移除 SRT 字幕文字中所有標點符號，保留文字、數字、英文與空格。"""
    return _SRT_PUNCT_RE.sub("", text).strip()


def srt_char_width(ch: str) -> float:
    if ch.isspace():
        return 0.5
    return 0.5 if ch.isascii() else 1.0


def srt_text_width(text: str) -> float:
    return sum(srt_char_width(ch) for ch in text)


def _hard_split_token(token: str, max_width: float) -> list[str]:
    """單一詞本身就比一行還寬（例如超長英文單字），只能逐字硬切。"""
    parts: list[str] = []
    line = ""
    width = 0.0
    for ch in token:
        ch_width = srt_char_width(ch)
        if line and width + ch_width > max_width:
            parts.append(line)
            line, width = "", 0.0
        line += ch
        width += ch_width
    if line:
        parts.append(line)
    return parts


def _balanced_split(tokens: list[str], max_width: float,
                    min_tail: float = 4.0) -> list[str]:
    """在詞界中找最佳切點，遞迴切到每行都不超寬。
    評分：越平衡越好；斷在空格（自然停頓）大加分；產生過短行大扣分。"""
    text = "".join(tokens).strip()
    if not text:
        return []
    if srt_text_width(text) <= max_width:
        return [text]

    best_i = None
    best_score = None
    for i in range(1, len(tokens)):
        left = "".join(tokens[:i]).strip()
        right = "".join(tokens[i:]).strip()
        if not left or not right:
            continue
        wl = srt_text_width(left)
        wr = srt_text_width(right)
        score = abs(wl - wr)                      # 兩邊越平均越好
        if tokens[i - 1].isspace() or tokens[i].isspace():
            score -= 8.0                          # 優先斷在空格（自然停頓）
        if wl < min_tail or wr < min_tail:
            score += 100.0                        # 避免「人」「知道」這種孤兒行
        if best_score is None or score < best_score:
            best_i, best_score = i, score

    if best_i is None:
        return _hard_split_token(text, max_width)
    return (_balanced_split(tokens[:best_i], max_width, min_tail)
            + _balanced_split(tokens[best_i:], max_width, min_tail))


def wrap_srt_text(text: str, max_width: float = SRT_MAX_LINE_WIDTH) -> list[str]:
    """超寬時不再貪婪塞滿：優先斷在空格，其次在 jieba 詞界找最平衡的切點，
    並避免產生過短的孤兒行。未安裝 jieba 時退回逐字為單位做平衡切分。"""
    text = text.replace("\r", "").replace("\n", "").strip()
    if not text:
        return []
    if srt_text_width(text) <= max_width:
        return [text]

    if _HAS_JIEBA:
        tokens = [w for w in jieba.cut(text) if w]
    else:
        tokens = list(text)

    # 先處理本身就超寬的單一詞（例如超長英文單字）
    fixed: list[str] = []
    for w in tokens:
        if srt_text_width(w) > max_width:
            fixed.extend(_hard_split_token(w, max_width))
        else:
            fixed.append(w)

    lines = [ln.strip() for ln in _balanced_split(fixed, max_width)]
    return [ln for ln in lines if ln] or [text]


def chunks_to_srt(chunks: list[dict]) -> str:
    entries = []
    idx = 1
    for chunk in chunks:
        text = strip_punct_for_srt((chunk.get("text") or "").strip())
        ts   = chunk.get("timestamp") or (0.0, 0.0)
        if not text:
            continue
        start = ts[0] if ts[0] is not None else 0.0
        end   = ts[1] if ts[1] is not None else start + 2.0
        if end <= start:
            end = start + 2.0

        # wrap_srt_text 會自動依據 jieba 詞彙來斷句，確保詞彙完整性
        lines = wrap_srt_text(text)
        if not lines:
            continue
            
        # 若只有一行，直接輸出為單句字幕
        if len(lines) == 1:
            entries += [
                str(idx),
                f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}",
                lines[0],
                "",
            ]
            idx += 1
        else:
            # 若超過字數被切成多行，依照字數比例均分時間碼，強制變成獨立的下一句
            total_chars = sum(len(l) for l in lines)
            duration = end - start
            current_start = start
            
            for line in lines:
                line_chars = len(line)
                # 依字數比例計算這句切斷的字幕應分配到的時間長度
                line_duration = duration * (line_chars / total_chars) if total_chars > 0 else duration
                line_end = current_start + line_duration
                
                entries += [
                    str(idx),
                    f"{seconds_to_srt_time(current_start)} --> {seconds_to_srt_time(line_end)}",
                    line,
                    "",
                ]
                idx += 1
                current_start = line_end

    return "\n".join(entries).strip() + "\n"


def _needs_punct(text: str) -> bool:
    return bool(text) and text[-1] not in "。！？!?.,，；;：:"


def punctuate_chunks(chunks: list[dict]) -> list[dict]:
    result = []
    for i, chunk in enumerate(chunks):
        nc   = dict(chunk)
        text = (nc.get("text") or "").strip()
        if _needs_punct(text):
            cur_end    = (nc.get("timestamp") or (0.0, 0.0))[1]
            next_start = None
            if i + 1 < len(chunks):
                next_start = (chunks[i+1].get("timestamp") or (None, None))[0]
            if next_start is None or cur_end is None:
                mark = "。"
            else:
                mark = "。" if max(0.0, next_start - cur_end) >= 0.8 else "，"
            nc["text"] = text + mark
        result.append(nc)
    return result


def chunks_to_plain(chunks: list[dict], fallback: str = "") -> str:
    text = "".join((c.get("text") or "").strip() for c in chunks).strip()
    if text:
        return text
    fallback = fallback.strip()
    return fallback + ("。" if fallback and _needs_punct(fallback) else "")


def suppress_repeat_hallucination(chunks: list[dict], min_run: int = 5,
                                  max_len: int = 6) -> tuple[list[dict], int]:
    """清除 Whisper 類模型在靜音／音樂段常見的重複幻覺（例如 OK 連續數十組）。
    連續 min_run 組以上、文字完全相同且很短（≤ max_len 字）→ 保留第一組、其餘刪除。
    真人不會以固定節奏連續講數十次相同短句，誤殺風險極低。
    回傳 (清理後的 chunks, 被刪除的組數)。"""
    def _norm(c: dict) -> str:
        return strip_punct_for_srt((c.get("text") or "").strip()).casefold()

    result: list[dict] = []
    removed = 0
    i = 0
    n = len(chunks)
    while i < n:
        key = _norm(chunks[i])
        j = i + 1
        while j < n and key and _norm(chunks[j]) == key:
            j += 1
        run = j - i
        if key and run >= min_run and len(key) <= max_len:
            result.append(chunks[i])   # 保留第一組，其餘視為幻覺刪除
            removed += run - 1
        else:
            result.extend(chunks[i:j])
        i = j
    return result, removed



# ═══════════════════════════════════════════════════════════
#  AI校對
# ═══════════════════════════════════════════════════════════

def apply_llm_to_chunks(chunks: list[dict], llm_lines: list[str]) -> list[dict]:
    """
    把 AI 逐行校對結果套回 chunks（保留時間碼）。
    一對一對應：第 N 條非空 chunk 對應第 N 行 AI 輸出。
    行數不足時保留原文。
    """
    result = []
    non_empty = [i for i, c in enumerate(chunks) if (c.get("text") or "").strip()]
    for i, chunk in enumerate(chunks):
        nc = dict(chunk)
        if i in non_empty:
            pos = non_empty.index(i)
            if pos < len(llm_lines):
                nc["text"] = llm_lines[pos].strip()
            # 若 AI 行數不足，保留原文
        result.append(nc)
    return result


OPENAI_MODELS   = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
CLAUDE_MODELS   = ["claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-5"]
GEMINI_MODELS   = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"]
OPENROUTER_MODELS = [
    "google/gemma-3-27b-it:free",
    "meta-llama/llama-4-scout:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "mistralai/mistral-7b-instruct:free",
]

# ── 各供應商設定說明（顯示於設定視窗）──────────────────────
PROVIDER_HINTS = {
    "openai": (
        "OpenAI ｜ 付費方案\n"
        "取得 Key：platform.openai.com → API keys\n"
        "建議模型：gpt-4o-mini（便宜）｜ gpt-4o（品質最佳）"
    ),
    "claude": (
        "Anthropic Claude ｜ 付費方案（品質最佳、繁中理解強）\n"
        "取得 Key：console.anthropic.com → API Keys\n"
        "建議模型：claude-haiku-4-5（快速便宜）｜ claude-sonnet-4-5（均衡首選）"
    ),
    "openrouter": (
        "OpenRouter ｜ 聚合平台，有多個完全免費模型 ★另一免費選項★\n"
        "取得 Key：openrouter.ai → Keys（免費申請）\n"
        "模型名稱結尾含 :free 者為完全免費，如 google/gemma-3-27b-it:free"
    ),
    "gemini": (
        "Google Gemini ｜ 速度快、智商高，免費額度給得最大方 ★推薦首選★\n"
        "取得 Key：aistudio.google.com → Get API key（免費申請）\n"
        "建議模型：gemini-2.5-flash（速度與品質首選）"
    ),
}

PROVIDER_SITES = {
    "openai": ("OpenAI 官方網站", "https://platform.openai.com/"),
    "claude": ("Anthropic 官方網站", "https://console.anthropic.com/"),
    "openrouter": ("OpenRouter 官方網站", "https://openrouter.ai/keys"),
    "gemini": ("Google AI Studio", "https://aistudio.google.com/apikey"),
}


def _post_json(url: str, headers: dict, payload: dict, timeout: int = 120) -> dict:
    import urllib.request, urllib.error, socket, ssl
    _headers = {
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    _headers.update(headers)
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data, headers=_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode(errors="replace")
        except Exception:
            body = ""
        body_low = body.lower()
        code = e.code
        if code in (401, 403):
            raise RuntimeError(
                "API Key 無效或已過期。請打開「設定」→ 重新貼上正確的 API Key 並儲存。"
            ) from None
        if code == 404:
            raise RuntimeError(
                "找不到指定的模型（HTTP 404）。請到「設定」→ 切換成有效的模型名稱。"
                + (f"\n細節：{body[:200]}" if body.strip() else "")
            ) from None
        if code == 429:
            if any(k in body_low for k in ("credit", "billing", "exceeded", "quota", "daily")):
                raise RuntimeError(
                    "API 額度／配額已用完，今日不會自動恢復。\n"
                    "可能原因：①金鑰綁了計費專案但餘額為 0；②今日免費額度已耗盡。\n"
                    "建議到「設定」改用新的免費金鑰，或稍後改天再試。"
                ) from None
            raise RuntimeError(
                "請求太頻繁，API 暫時限流（HTTP 429）。請等 30~60 秒後再試一次。"
            ) from None
        if code == 400:
            raise RuntimeError(
                "請求被 API 拒絕（HTTP 400）：通常是模型名稱錯誤、欄位格式不合或 prompt 過長。\n"
                "請打開「設定」確認模型名稱拼字正確。"
                + (f"\n細節：{body[:200]}" if body.strip() else "")
            ) from None
        if code == 408:
            raise RuntimeError(
                "API 處理逾時（HTTP 408），請稍後再試。"
            ) from None
        if code in (502, 503, 504):
            raise RuntimeError(
                f"API 伺服器忙碌或維護中（HTTP {code}），請稍後再試。"
            ) from None
        if 500 <= code <= 599:
            raise RuntimeError(
                f"API 伺服器發生錯誤（HTTP {code}），請稍後再試或回報開發者。"
            ) from None
        raise RuntimeError(
            f"API 回應異常（HTTP {code}）。"
            + (f"\n細節：{body[:200]}" if body.strip() else "")
        ) from None
    except (socket.timeout, TimeoutError):
        raise RuntimeError(
            "連線逾時：無法在時間內連上 API，請檢查網路是否正常後再試一次。"
        ) from None
    except ssl.SSLError as e:
        raise RuntimeError(
            "SSL 連線錯誤：可能是系統時間不對、防毒軟體攔截，或公司網路代理導致。\n"
            f"細節：{e}"
        ) from None
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise RuntimeError(
                "連線逾時：無法在時間內連上 API，請檢查網路是否正常後再試一次。"
            ) from None
        if isinstance(reason, ssl.SSLError):
            raise RuntimeError(
                "SSL 連線錯誤：可能是系統時間不對、防毒軟體攔截，或公司網路代理導致。\n"
                f"細節：{reason}"
            ) from None
        reason_text = str(reason).lower()
        if "name or service" in reason_text or "getaddrinfo" in reason_text or "name resolution" in reason_text:
            raise RuntimeError(
                "無法解析 API 網址，請確認電腦可以連上網際網路（試著開瀏覽器看看）。"
            ) from None
        raise RuntimeError(
            f"無法連上 API，請確認網路與防火牆設定。\n細節：{reason}"
        ) from None


# ── 每批最多送出的字數（中文約 500 字 ≈ 安全範圍）────────
LLM_BATCH_CHARS = 500


def _llm_call_once(system: str, user_msg: str, cfg: dict) -> str:
    """對單一供應商發出一次 AI 請求，回傳原始字串。"""
    provider = cfg.get("api_provider", "gemini")
    api_key  = (cfg.get("api_key") or "").strip()
    model    = (cfg.get("model") or "").strip()

    if provider == "claude":
        model = model or CLAUDE_MODELS[0]
        result = _post_json(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
            },
            payload={
                "model":      model,
                "max_tokens": 4096,
                "system":     system,
                "messages":   [{"role": "user", "content": user_msg}],
            },
        )
        try:
            return result["content"][0]["text"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Claude 回傳格式異常：{result}") from e

    elif provider == "gemini":
        model = model or GEMINI_MODELS[0]
        url   = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096},
        }
        result = _post_json(url, headers={"Content-Type": "application/json"}, payload=payload)
        try:
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Gemini 回傳格式異常：{result}") from e

    elif provider == "openrouter":
        model = model or OPENROUTER_MODELS[0]
        result = _post_json(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer":  "https://github.com/dual-asr",
            },
            payload={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                "temperature": 0.2,
                "max_tokens":  4096,
            },
        )
        return result["choices"][0]["message"]["content"]

    else:  # openai
        model = model or OPENAI_MODELS[0]
        result = _post_json(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            payload={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                "temperature": 0.2,
                "max_tokens":  4096,
            },
        )
        return result["choices"][0]["message"]["content"]


def chunks_to_srt_string(chunks_list: list[dict], start_idx: int = 1) -> str:
    """將傳入的 chunks 清單轉成標準 SRT 格式字串，序號從 start_idx 開始"""
    lines = []
    for i, c in enumerate(chunks_list):
        idx = start_idx + i
        ts = c.get("timestamp") or (c.get("start", 0.0), c.get("end", 0.0))
        s_ts = format_timestamp(ts[0] if ts[0] is not None else 0.0)
        e_ts = format_timestamp(ts[1] if ts[1] is not None else 0.0)
        text = (c.get("text") or "").strip()
        lines.append(f"{idx}\n{s_ts} --> {e_ts}\n{text}\n")
    return "\n".join(lines)

def llm_merge(chunks: list[dict], cfg: dict, log_fn,
              context_notes: str = "", use_text_fix: bool = True,
              progress_cb=None) -> tuple[list[str], str]:
    """
    分批將 chunks 組合為標準 SRT 格式送給 AI校對。
    利用安全回填機制：若 AI 將幻覺行文字刪空，該時間碼保留並留白，後續時間碼絕不跑掉。
    """
    provider = cfg.get("api_provider", "gemini")
    api_key  = (cfg.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("請先在設定中填入 API Key。")

    log_fn(f"AI：使用 {provider} / {cfg.get('model', '（預設）')}")

    # ── 組合 system prompt ────────────────────────────────
    if use_text_fix:
        system = EDITOR_SYSTEM_PROMPT
        if 'TEXT_FIX_PROMPT' in globals():
            system += "\n\n" + TEXT_FIX_PROMPT
        log_fn("AI：已啟動修改指令，將套用總編輯 Prompt。")
    else:
        system = SRT_FORMAT_ONLY_PROMPT
        log_fn("AI：修改指令關閉，不套用總編輯 Prompt。")

    # 補充資料
    context_suffix = ""
    if context_notes.strip():
        context_suffix = (
            f"\n\n【補充資料：大綱 / 人名 / 專有名詞等】\n{context_notes.strip()}\n"
            "（請優先以上方補充資料中的正確寫法為準，修正辨識結果中的錯誤。）"
        )

    # ── 分批處理：根據字數將 chunks 分組 ─────────────────────
    batches: list[list[dict]] = []
    current_batch: list[dict] = []
    current_chars = 0
    
    for c in chunks:
        text = (c.get("text") or "").strip()
        if not text:
            continue
        if current_batch and current_chars + len(text) > LLM_BATCH_CHARS:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0
        current_batch.append(c)
        current_chars += len(text)
    if current_batch:
        batches.append(current_batch)

    total_batches = len(batches)
    log_fn(f"AI：共分成 {total_batches} 批送出標準 SRT 校對")
    expected_timecode_groups = sum(len(batch) for batch in batches)
    matched_timecode_groups = 0

    # 用來存放最終校對後文字的清單（與原始 chunks 一一對應）
    # 初始化先填入 Breeze ASR 的原始文字，確保萬一 API 失敗時有安全底牌
    final_text_results = [ (c.get("text") or "").strip() for c in chunks ]

    # 建立一個全局的對照表：(開始時間字串, 結束時間字串) -> chunks 的 index
    # 用時間戳記當作絕對鑰匙，不管 AI 怎麼刪行、怎麼改行號，只要時間碼對得上就能精準回填
    ts_map = {}
    for idx, c in enumerate(chunks):
        ts = c.get("timestamp") or (c.get("start", 0.0), c.get("end", 0.0))
        s_ts = format_timestamp(ts[0] if ts[0] is not None else 0.0)
        e_ts = format_timestamp(ts[1] if ts[1] is not None else 0.0)
        ts_map[(s_ts, e_ts)] = idx

    # ── 逐批呼叫 ─────────────────────────────────────────
    start_srt_idx = 1
    for i, batch in enumerate(batches):
        if progress_cb:
            progress_cb(i, total_batches)
        log_fn(f"AI校對第 {i+1}/{total_batches} 批（{len(batch)} 組字幕）...")

        # 直接將這一批 chunks 轉成標準的 SRT 格式文本
        srt_input_text = chunks_to_srt_string(batch, start_idx=start_srt_idx)
        start_srt_idx += len(batch)

        if use_text_fix:
            user_msg = f"【請校對以下標準 SRT 字幕，嚴禁變動時間碼結構】\n\n{srt_input_text}{context_suffix}"
        else:
            user_msg = f"【請以相同標準 SRT 格式回傳以下字幕，嚴禁變動時間碼結構】\n\n{srt_input_text}"

        try:
            raw_response = _llm_call_once(system, user_msg, cfg)
            
            # 解析 AI 回傳的 SRT 格式
            # 邏輯：抓取時間碼行，並將其下方的文字塞回對應的 chunk index
            srt_lines = raw_response.strip().splitlines()
            current_ts_key = None
            current_text_lines = []
            seen_batch_keys = set()

            def flush_current_group():
                nonlocal matched_timecode_groups
                if current_ts_key and current_ts_key in ts_map:
                    target_idx = ts_map[current_ts_key]
                    final_text_results[target_idx] = " ".join(current_text_lines).strip()
                    if current_ts_key not in seen_batch_keys:
                        seen_batch_keys.add(current_ts_key)
                        matched_timecode_groups += 1

            for line in srt_lines:
                line_str = line.strip()
                if not line_str:
                    continue
                
                # 判斷是否為時間碼行 (例如 00:00:17,800 --> 00:00:21,069)
                if "-->" in line_str:
                    # 在進入下一個時間碼前，先把上一個時間碼累積的文字存進去
                    flush_current_group()
                    
                    # 解析新的時間碼
                    parts = line_str.split("-->")
                    if len(parts) == 2:
                        current_ts_key = (parts[0].strip(), parts[1].strip())
                    current_text_lines = []
                elif line_str.isdigit():
                    # 這是 SRT 的序號行，忽略不處理
                    continue
                else:
                    # 這是字幕文字行，累積起來
                    if current_ts_key:
                        current_text_lines.append(line_str)
            
            # 處理最後一組殘留的字幕
            flush_current_group()

        except Exception as e:
            log_fn(f"警告：第 {i+1} 批 AI 請求失敗（{e}），此批將沿用原始辨識結果。")

    if matched_timecode_groups != expected_timecode_groups:
        log_fn(
            f"提示：AI 回傳可對齊的時間碼組數為 {matched_timecode_groups}/{expected_timecode_groups}，"
            "已用安全回填保護缺漏組，時間碼框架不受影響。"
        )

    # ── 將校對後的文字同步回原始 chunks 結構中 ──────────────────
    for idx, cleaned_text in enumerate(final_text_results):
        chunks[idx]["text"] = cleaned_text

    # 建立純文字輸出
    all_out_lines = [cleaned_text for cleaned_text in final_text_results if cleaned_text]
    plain = "\n".join(all_out_lines)
    
    return final_text_results, plain

# ═══════════════════════════════════════════════════════════
#  主視窗
# ═══════════════════════════════════════════════════════════

BaseTk = TkinterDnD.Tk if _HAS_DND else tk.Tk


class DualASRApp(BaseTk):
    def __init__(self):
        super().__init__()
        self.title("聲文去SanWich")
        self._apply_logo()
        
        # 1. 定義你想要的視窗寬度與高度
        window_width = 1259
        window_width = 1259
        window_height = 1123
        
        # 2. 取得螢幕解析度的寬度與高度
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = min(window_width, int(screen_width * 0.92))
        window_height = min(window_height, int(screen_height * 0.88))
        window_width = max(window_width, 482)
        window_height = max(window_height, 381)
        
        # 3. 計算置中時，視窗左上角的 X 和 Y 座標
        center_x = max(0, int((screen_width - window_width) / 2))
        center_y = max(0, int((screen_height - window_height) / 2))
        
        # 4. 設定視窗大小與置中位置 (格式為 "寬x高+X+Y")
        self.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")
        
        self.minsize(482, 381)
        self.option_add("*Font", (FONT_FAMILY, 10))

        self.cfg = load_config()

        self.input_path      = tk.StringVar()
        self.output_srt_path = tk.StringVar()
        self.output_txt_path = tk.StringVar()
        self.status_text     = tk.StringVar(value="")
        self.input_files     = []

        self.use_llm      = tk.BooleanVar(value=self.cfg.get("use_llm", False))
        self.use_text_fix = tk.BooleanVar(value=self.cfg.get("use_text_fix", False))
        self.output_srt_enabled = tk.BooleanVar(value=self.cfg.get("output_srt_enabled", True))
        self.output_txt_enabled = tk.BooleanVar(value=self.cfg.get("output_txt_enabled", True))

        self.pipeline     = None   # Breeze pipeline（快取）
        self.cancel_event = threading.Event()
        self.last_compare = None   # 最近一次校對的前後對照資料

        self._build_ui()

        if not _HAS_JIEBA:
            self.log("提示：未安裝 jieba 套件，字幕換行將使用舊版逐字斷行方式。"
                     "可執行 01_setup.bat 重新安裝以啟用智慧斷詞換行。", tag="warn")
        if not _HAS_DND:
            self.log("提示：未安裝 tkinterdnd2，拖放檔案功能暫不可用；仍可用「選擇檔案」一次選多個檔案。", tag="warn")

    def _apply_logo(self):
        for path in (resource_path("_LOGO.ico"), resource_path("_LOGO.png"), resource_path("_LOGO.gif")):
            if not path.exists():
                continue
            try:
                if path.suffix.lower() == ".ico":
                    self.iconbitmap(str(path))
                    logo_png = resource_path("_LOGO.png")
                    self._logo_image = tk.PhotoImage(file=str(logo_png)) if logo_png.exists() else None
                    if self._logo_image:
                        self.iconphoto(True, self._logo_image)
                else:
                    self._logo_image = tk.PhotoImage(file=str(path))
                    self.iconphoto(True, self._logo_image)
                return
            except Exception:
                continue

    # ── 建立 UI ──────────────────────────────────────────

    def _build_ui(self):
        self.configure(bg=BG)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame",       background=BG)
        style.configure("TLabel",       background=BG,    foreground=TEXT,  font=(FONT_FAMILY, 10))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT,  font=(FONT_FAMILY, 10))
        style.configure("Title.TLabel", background=BG,    foreground=TEXT,  font=(FONT_FAMILY, 18, "bold"))
        style.configure("Sub.TLabel",   background=BG,    foreground=MUTED, font=(FONT_FAMILY, 10))
        style.configure("Hint.TLabel",  background=PANEL, foreground=MUTED, font=(FONT_FAMILY, 9))
        style.configure("TCheckbutton", background=BG,    foreground=TEXT,  font=(FONT_FAMILY, 10),
                        indicatorcolor=ENTRY_BG, selectcolor=ACCENT)
        style.configure("TProgressbar",
                        troughcolor=ENTRY_BG, background=ACCENT,
                        bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT, thickness=9)

        scroll_host = tk.Frame(self, bg=BG)
        scroll_host.pack(fill="both", expand=True)

        main_canvas = tk.Canvas(scroll_host, bg=BG, highlightthickness=0, borderwidth=0)
        main_scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=main_canvas.yview)
        main_canvas.configure(yscrollcommand=main_scrollbar.set)
        main_canvas.pack(side="left", fill="both", expand=True)
        main_scrollbar.pack(side="right", fill="y")

        main = tk.Frame(main_canvas, bg=BG, padx=22, pady=18)
        main_window = main_canvas.create_window((0, 0), window=main, anchor="nw")

        def _refresh_scroll_region(_event=None):
            main_canvas.configure(scrollregion=main_canvas.bbox("all"))

        def _fit_main_width(event):
            main_canvas.itemconfigure(main_window, width=event.width)

        def _on_mousewheel(event):
            main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(_event):
            self.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(_event):
            self.unbind_all("<MouseWheel>")

        main.bind("<Configure>", _refresh_scroll_region)
        main_canvas.bind("<Configure>", _fit_main_width)
        main_canvas.bind("<Enter>", _bind_mousewheel)
        main_canvas.bind("<Leave>", _unbind_mousewheel)

        # ── 模型狀態列 ───────────────────────────────────────
        model_row = tk.Frame(main, bg=PANEL, highlightbackground=BORDER,
                             highlightthickness=1, padx=14, pady=12)
        model_row.pack(fill="x", pady=(0, 10))

        settings_btn = tk.Label(model_row, text="⚙", bg=PANEL, fg=TEXT,
                                activebackground=PANEL, activeforeground=ACCENT,
                                font=(FONT_FAMILY, 17), cursor="hand2")
        settings_btn.bind("<Button-1>", lambda _e: self.open_settings())
        settings_btn.bind("<Enter>", lambda _e: settings_btn.configure(fg=ACCENT))
        settings_btn.bind("<Leave>", lambda _e: settings_btn.configure(fg=TEXT))
        settings_btn.pack(side="left", padx=(0, 14))

        # Breeze 狀態（左側）
        self.dot_breeze = StatusDot(model_row)
        self.dot_breeze.pack(side="left", padx=(0, 4))
        tk.Label(model_row, text="Breeze-ASR-25(主模型)", bg=PANEL, fg=ACCENT,
                 font=(FONT_FAMILY, 11, "bold")).pack(side="left")

        # AI校對大型切換開關（右側）
        self.dot_llm = StatusDot(model_row, size=12)
        self.llm_toggle_btn = self._make_toggle_btn(
            model_row, self.use_llm,
            label_on="● AI校對  開啟",
            label_off="○ AI校對  關閉",
            color_on=SUCCESS,
            color_off=MUTED,
            font_size=11,
        )
        self.llm_toggle_btn.pack(side="right", padx=(0, 6))

        # ── 輸入檔 ────────────────────────────────────────
        input_panel = self._panel(main)
        input_panel.pack(fill="x", pady=(0, 10))
        ttk.Label(input_panel, text="音訊或影片檔", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(input_panel,
                  text="可拖放檔案到這裡，或一次選多個檔案；支援 mp3、wav、m4a、mp4、mov、mkv、flac、aac、ogg、webm",
                  style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 8))
        input_panel.columnconfigure(0, weight=1)
        self.input_entry = self._entry(input_panel, self.input_path)
        self.input_entry.grid(row=2, column=0, sticky="ew", padx=(0, 8))
        PillButton(input_panel, text="選擇檔案", command=self.choose_input,
                    min_width=118, bold=True, font_size=12).grid(row=2, column=1)
        self._enable_file_drop(self, input_panel, self.input_entry)

        # ── 輸出路徑 ──────────────────────────────────────
        out_panel = self._panel(main)
        out_panel.pack(fill="x", pady=(0, 10))
        out_panel.columnconfigure(0, weight=1)
        out_panel.columnconfigure(1, weight=1)

        out_hint = tk.Label(
            out_panel, bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 9), justify="left",
            text="啟用 AI校對後：①字幕文字會傳送至你選擇的 API 供應商（如 Google Gemini）進行校對，"
                 "敏感題材（醫療／法律／個資）請自行斟酌；②輸出檔案將直接覆寫為校對後版本（SRT 保留時間碼）。"
        )
        out_hint.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        # ── SRT 開關 + 路徑列 ─────────────────────────────
        srt_header = tk.Frame(out_panel, bg=PANEL)
        srt_header.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.srt_toggle_btn = self._make_toggle_btn(
            srt_header, self.output_srt_enabled,
            label_on="● SRT 字幕  輸出",
            label_off="○ SRT 字幕  關閉",
            color_on=ACCENT, color_off=MUTED, font_size=10,
        )
        self.srt_toggle_btn.pack(side="left")

        srt_path_row = tk.Frame(out_panel, bg=PANEL)
        srt_path_row.grid(row=2, column=0, sticky="ew", pady=(0, 4))
        srt_path_row.columnconfigure(0, weight=1)
        self._entry(srt_path_row, self.output_srt_path).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        srt_btn_row = tk.Frame(out_panel, bg=PANEL)
        srt_btn_row.grid(row=3, column=0, sticky="w", pady=(0, 4))
        PillButton(srt_btn_row, text="另存 SRT", command=self.choose_srt,
                   min_width=96, height=32, bg_color=BORDER,
                   hover_color="#3A4655", fg_color=TEXT).pack(side="left")
        PillButton(srt_btn_row, text="開資料夾",
                   command=lambda: self.open_folder(self.output_srt_path),
                   min_width=88, height=32, bg_color=BORDER,
                   hover_color="#3A4655", fg_color=TEXT).pack(side="left", padx=(6, 0))

        # ── TXT 開關 + 路徑列 ─────────────────────────────
        txt_header = tk.Frame(out_panel, bg=PANEL)
        txt_header.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))
        self.txt_toggle_btn = self._make_toggle_btn(
            txt_header, self.output_txt_enabled,
            label_on="● 純文字  輸出",
            label_off="○ 純文字  關閉",
            color_on=ACCENT2, color_off=MUTED, font_size=10,
        )
        self.txt_toggle_btn.pack(side="left")

        txt_path_row = tk.Frame(out_panel, bg=PANEL)
        txt_path_row.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))
        txt_path_row.columnconfigure(0, weight=1)
        self._entry(txt_path_row, self.output_txt_path).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        txt_btn_row = tk.Frame(out_panel, bg=PANEL)
        txt_btn_row.grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(0, 4))
        PillButton(txt_btn_row, text="另存文字", command=self.choose_txt,
                   min_width=96, height=32, bg_color=BORDER,
                   hover_color="#3A4655", fg_color=TEXT).pack(side="left")
        PillButton(txt_btn_row, text="開資料夾",
                   command=lambda: self.open_folder(self.output_txt_path),
                   min_width=88, height=32, bg_color=BORDER,
                   hover_color="#3A4655", fg_color=TEXT).pack(side="left", padx=(6, 0))

        # ── 進度列 ────────────────────────────────────────
        ctrl = tk.Frame(main, bg=BG)
        ctrl.pack(fill="x", pady=(6, 4))
        self.progress = ttk.Progressbar(ctrl, maximum=100, mode="determinate")
        self.progress.pack(fill="x", side="left", expand=True, padx=(0, 10))
        self.cancel_btn = PillButton(ctrl, text="取消", command=self.cancel,
                                     min_width=80, bg_color=BORDER,
                                     hover_color="#3A4655", fg_color=TEXT)
        self.cancel_btn.pack(side="right", padx=(0, 8))
        self.cancel_btn.configure(state="disabled")
        self.run_btn = PillButton(ctrl, text="開始轉寫", command=self.start,
                                  min_width=120, height=40, bold=True, font_size=12)
        self.run_btn.pack(side="right")

        ttk.Label(main, textvariable=self.status_text).pack(anchor="w", pady=(2, 6))

        # ── 文字修正開關（主介面）────────────────────────
        fix_panel = self._panel(main)
        fix_panel.pack(fill="x", pady=(0, 10))
        fix_row = tk.Frame(fix_panel, bg=PANEL)
        fix_row.pack(fill="x")
        self.fix_toggle_btn = self._make_toggle_btn(
            fix_row, self.use_text_fix,
            label_on="● 啟動修改指令  開啟",
            label_off="○ 啟動修改指令  關閉",
            color_on=SUCCESS,
            color_off=MUTED,
        )
        self.fix_toggle_btn.pack(side="left")
        tk.Label(fix_row,
                 text="檢查錯別字、簡體字、中國大陸用語、專有名詞修正",
                 bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 9)).pack(side="left", padx=(12, 0))

        # ── 校對前後對照 / 還原（階段三）─────────────────────
        cmp_panel = self._panel(main)
        cmp_panel.pack(fill="x", pady=(0, 10))
        cmp_row = tk.Frame(cmp_panel, bg=PANEL)
        cmp_row.pack(fill="x")
        tk.Label(cmp_row, text="校對結果", bg=PANEL, fg=ACCENT2,
                 font=(FONT_FAMILY, 11, "bold")).pack(side="left")
        self.restore_btn = PillButton(cmp_row, text="還原原始辨識", command=self.restore_original,
                                      min_width=120, height=32, bg_color=BORDER,
                                      hover_color="#3A4655", fg_color=TEXT)
        self.restore_btn.pack(side="right")
        self.compare_btn = PillButton(cmp_row, text="開啟對照文字檔", command=self.show_comparison,
                                      min_width=140, height=32, bg_color=BORDER,
                                      hover_color="#3A4655", fg_color=TEXT)
        self.compare_btn.pack(side="right", padx=(0, 6))
        tk.Label(cmp_row, text="（完成一次 AI 校對後可用）", bg=PANEL, fg=MUTED,
                 font=(FONT_FAMILY, 9)).pack(side="left", padx=(12, 0))
        self.compare_btn.configure(state="disabled")
        self.restore_btn.configure(state="disabled")

        # ── 補充資料輸入區 ────────────────────────────────
        ctx_panel = self._panel(main)
        ctx_panel.pack(fill="x", pady=(0, 10))
        ctx_header = tk.Frame(ctx_panel, bg=PANEL)
        ctx_header.pack(fill="x", pady=(0, 2))
        tk.Label(ctx_header, text="補充資料（供 AI校對參考）", bg=PANEL, fg=ACCENT2,
                 font=(FONT_FAMILY, 10, "bold")).pack(side="left")
        tk.Label(ctx_panel,
                 text="輸入大綱、人名、地名、公司名、專有名詞等，AI校對時會優先以此為準\n"
                      "範例：受訪者｜黃先生（老黃）  地點｜北投士林科技園區  術語｜生成式AI、RAG、向量資料庫",
                 justify="left",
                 bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 9)).pack(anchor="w", pady=(0, 8))
        ctx_text_frame = tk.Frame(ctx_panel, bg=PANEL)
        ctx_text_frame.pack(fill="x")
        self.context_box = tk.Text(
            ctx_text_frame, height=4, wrap="word",
            bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
            selectbackground=ACCENT, selectforeground="#061018",
            relief="flat", borderwidth=0,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT,
            font=(FONT_FAMILY, 10),
        )
        ctx_sb = ttk.Scrollbar(ctx_text_frame, command=self.context_box.yview)
        self.context_box.configure(yscrollcommand=ctx_sb.set)
        self.context_box.pack(side="left", fill="both", expand=True)
        ctx_sb.pack(side="right", fill="y")

        # ── 日誌區 ────────────────────────────────────────
        log_panel = self._panel(main)
        log_panel.pack(fill="both", expand=True)
        self.log_box = tk.Text(log_panel, height=12, wrap="word",
                               bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                               selectbackground=ACCENT, selectforeground="#061018",
                               relief="flat", borderwidth=0, font=(FONT_FAMILY, 10))
        self.log_box.configure(state="disabled")
        self.log_box.tag_configure("error",   foreground=ERROR)
        self.log_box.tag_configure("success", foreground=SUCCESS)
        self.log_box.tag_configure("warn",    foreground=WARN)
        self.log_box.tag_configure("model",   foreground=ACCENT2)
        sb = ttk.Scrollbar(log_panel, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=sb.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _panel(self, parent) -> tk.Frame:
        return tk.Frame(parent, bg=PANEL, highlightbackground=BORDER,
                        highlightthickness=1, padx=14, pady=14)

    def _make_toggle_btn(self, parent, bool_var: tk.BooleanVar,
                         label_on: str, label_off: str,
                         color_on: str, color_off: str, font_size: int = 12) -> tk.Label:
        """建立一個大型文字切換開關，點擊切換 BooleanVar 並更新外觀。"""
        lbl = tk.Label(
            parent,
            text=label_on if bool_var.get() else label_off,
            bg=PANEL,
            fg=color_on if bool_var.get() else color_off,
            font=(FONT_FAMILY, font_size, "bold"),
            cursor="hand2",
            padx=14, pady=4,
        )

        def _toggle(_event=None):
            new_val = not bool_var.get()
            bool_var.set(new_val)
            lbl.configure(
                text=label_on if new_val else label_off,
                fg=color_on if new_val else color_off,
            )

        lbl.bind("<Button-1>", _toggle)
        return lbl

    def _entry(self, parent, var):
        return tk.Entry(parent, textvariable=var,
                        bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                        readonlybackground=ENTRY_BG, relief="flat",
                        highlightthickness=1, highlightbackground=BORDER,
                        highlightcolor=ACCENT, font=(FONT_FAMILY, 10))

    def _is_media_file(self, path: str) -> bool:
        p = Path(path)
        return p.is_file() and p.suffix.lower() in MEDIA_EXTS

    def _set_input_files(self, paths):
        valid = []
        skipped = []
        for path in paths:
            p = str(Path(path))
            if self._is_media_file(p):
                valid.append(p)
            else:
                skipped.append(p)
        if not valid:
            if skipped:
                messagebox.showerror("沒有可用檔案", "請拖放或選擇支援的音訊／影片檔。")
            return

        self.input_files = valid
        first = Path(valid[0])
        if len(valid) == 1:
            self.input_path.set(valid[0])
        else:
            self.input_path.set(f"{len(valid)} 個檔案，第一個：{valid[0]}")

        base = str(first.with_suffix(""))
        self.output_srt_path.set(base + ".srt")
        self.output_txt_path.set(base + ".txt")
        if len(valid) > 1:
            self.log(f"已加入 {len(valid)} 個檔案，將依序批次轉寫。", tag="success")
        if skipped:
            self.log(f"略過 {len(skipped)} 個不支援或不存在的檔案。", tag="warn")

    def _enable_file_drop(self, *widgets):
        if not _HAS_DND:
            return
        for widget in widgets:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_file_drop)
            except Exception:
                pass

    def _on_file_drop(self, event):
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        self._set_input_files(paths)

    # ── 檔案對話框 ───────────────────────────────────────

    def choose_input(self):
        paths = filedialog.askopenfilenames(
            title="選擇音訊或影片檔",
            filetypes=MEDIA_FILETYPES)
        if paths:
            self._set_input_files(paths)

    def choose_srt(self):
        p = filedialog.asksaveasfilename(title="儲存 SRT", defaultextension=".srt",
                                         filetypes=[("SRT 字幕", "*.srt")])
        if p: self.output_srt_path.set(p)

    def choose_txt(self):
        p = filedialog.asksaveasfilename(title="儲存純文字", defaultextension=".txt",
                                         filetypes=[("文字檔", "*.txt")])
        if p: self.output_txt_path.set(p)


    def open_folder(self, path_var: tk.StringVar):
        p = path_var.get().strip()
        if not p:
            messagebox.showerror("缺少路徑", "請先指定輸出檔案位置。")
            return
        folder = Path(p).expanduser().parent
        if not folder.exists():
            messagebox.showerror("找不到資料夾", f"{folder}")
            return
        try:
            os.startfile(folder)
        except Exception as e:
            messagebox.showerror("無法開啟", str(e))

    # ── 校對前後對照 / 還原（階段三）──────────────────────

    def _store_compare(self, inp, srt, txt, before_chunks, after_chunks,
                       before_text, after_text):
        """保存最近一次 AI 校對的前後資料，並啟用對照／還原按鈕。"""
        self.last_compare = {
            "inp": inp, "srt": srt, "txt": txt,
            "before_chunks": before_chunks, "after_chunks": after_chunks,
            "before_text": before_text, "after_text": after_text,
        }
        def _enable():
            try:
                self.compare_btn.configure(state="normal")
                self.restore_btn.configure(state="normal")
            except Exception:
                pass
        self.after(0, _enable)

    def show_comparison(self):
        """開啟視窗，列出 AI 校對前後有變動的字幕行。"""
        data = self.last_compare
        if not data:
            messagebox.showinfo("尚無對照資料", "請先完成一次 AI 校對。")
            return
        before = data["before_chunks"]
        after  = data["after_chunks"]
        diffs = []
        for i, (b, a) in enumerate(zip(before, after), start=1):
            bt = (b.get("text") or "").strip()
            at = (a.get("text") or "").strip()
            if bt != at:
                ts = b.get("timestamp") or (b.get("start", 0.0), b.get("end", 0.0))
                s_ts = format_timestamp(ts[0] if ts[0] is not None else 0.0)
                e_ts = format_timestamp(ts[1] if ts[1] is not None else 0.0)
                diffs.append((i, f"{s_ts} --> {e_ts}", bt, at))

        def _compare_text() -> str:
            header = [
                f"檔案：{Path(data['inp']).name}",
                f"字幕組數：{len(after)}",
                f"修改行數：{len(diffs)}",
                "=" * 48,
                "",
            ]
            if not diffs:
                return "\n".join(header + ["（AI 未變動任何文字）", ""])
            lines = header
            for idx, timecode, bt, at in diffs:
                lines.append(f"第 {idx} 組｜{timecode}")
                lines.append(f"原文：{bt or '（空）'}")
                lines.append(f"校對：{at or '（空）'}")
                lines.append("")
            return "\n".join(lines).rstrip() + "\n"

        safe_stem = "".join(ch if ch not in r'\/:*?"<>|' else "_" for ch in Path(data["inp"]).stem)
        preview_path = Path(tempfile.gettempdir()) / f"{safe_stem}_校對對照_預覽.txt"
        payload = _compare_text()
        try:
            preview_path.write_text(payload, encoding="utf-8-sig")
            self.clipboard_clear()
            self.clipboard_append(payload)
            os.startfile(str(preview_path))
            self.log(f"已開啟校對對照文字檔：{preview_path}", tag="success")
        except Exception as e:
            fallback = filedialog.asksaveasfilename(
                title="另存校對前後對照",
                defaultextension=".txt",
                initialfile=Path(data["inp"]).stem + "_校對對照.txt",
                filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")]
            )
            if fallback:
                try:
                    Path(fallback).write_text(payload, encoding="utf-8-sig")
                    self.log(f"已另存校對對照：{fallback}", tag="success")
                    messagebox.showinfo("已儲存", f"對照已儲存：\n{fallback}")
                except Exception as save_error:
                    messagebox.showerror("開啟/儲存失敗", f"{e}\n\n另存也失敗：{save_error}")
            else:
                messagebox.showerror("開啟失敗", str(e))
        return

        win = tk.Toplevel(self)
        win.title("校對前後對照")
        win_bg = "#F4F6F8"
        card_bg = "#FFFFFF"
        ink = "#101828"
        sub_ink = "#667085"
        before_color = "#B42318"
        after_color = "#027A48"
        win.configure(bg=win_bg)
        win.minsize(760, 500)
        win.grab_set()
        win_w = min(1080, max(820, int(self.winfo_screenwidth() * 0.78)))
        win_h = min(760, max(560, int(self.winfo_screenheight() * 0.72)))
        sx = self.winfo_rootx() + (self.winfo_width()  - win_w) // 2
        sy = self.winfo_rooty() + (self.winfo_height() - win_h) // 2
        win.geometry(f"{win_w}x{win_h}+{max(0,sx)}+{max(0,sy)}")
        win.grid_rowconfigure(1, weight=1)
        win.grid_columnconfigure(0, weight=1)

        head = tk.Frame(win, bg=win_bg, padx=22, pady=14)
        head.grid(row=0, column=0, sticky="ew")
        title_text = f"檔案：{Path(data['inp']).name}"
        tk.Label(head, text=title_text, bg=win_bg, fg=ink,
                 font=(FONT_FAMILY, 12, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
        tk.Label(head, text=f"共 {len(after)} 組字幕，AI 修改了 {len(diffs)} 行",
                 bg=win_bg, fg=sub_ink, font=(FONT_FAMILY, 10), anchor="e").pack(side="right")

        def _copy_all():
            payload = _compare_text()
            win.clipboard_clear()
            win.clipboard_append(payload)
            self.log(f"已複製 {len(diffs)} 行對照到剪貼簿。", tag="success")

        def _save_txt():
            default_name = Path(data["inp"]).stem + "_校對對照.txt"
            path = filedialog.asksaveasfilename(
                title="另存校對前後對照", defaultextension=".txt",
                initialfile=default_name,
                filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")])
            if not path:
                return
            try:
                Path(path).write_text(_compare_text(), encoding="utf-8-sig")
                self.log(f"已另存校對對照：{path}", tag="success")
                messagebox.showinfo("已儲存", f"對照已儲存：\n{path}")
            except Exception as e:
                messagebox.showerror("儲存失敗", str(e))

        foot = tk.Frame(win, bg=win_bg, padx=22, pady=14)
        foot.grid(row=2, column=0, sticky="ew")

        def _footer_button(text, command, primary=False):
            return tk.Button(
                foot, text=text, command=command,
                bg=ACCENT if primary else "#344054",
                fg="#FFFFFF", activebackground="#2563EB",
                activeforeground="#FFFFFF", relief="flat",
                font=(FONT_FAMILY, 10, "bold" if primary else "normal"),
                padx=14, pady=7, cursor="hand2",
            )

        _footer_button("關閉", win.destroy).pack(side="right")
        _footer_button("複製全部對照", _copy_all).pack(side="right", padx=(0, 8))
        _footer_button("另存對照 .txt", _save_txt, primary=True).pack(side="right", padx=(0, 8))

        body = tk.Frame(win, bg=win_bg, padx=22, pady=(0, 12))
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        text_host = tk.Frame(body, bg=card_bg, highlightthickness=1, highlightbackground="#D0D5DD")
        text_host.grid(row=0, column=0, sticky="nsew")
        text_host.grid_rowconfigure(0, weight=1)
        text_host.grid_columnconfigure(0, weight=1)

        view = tk.Text(
            text_host,
            bg=card_bg,
            fg=ink,
            insertbackground=ink,
            relief="flat",
            wrap="word",
            font=(FONT_FAMILY, 11),
            padx=16,
            pady=14,
            undo=False,
        )
        y_scroll = ttk.Scrollbar(text_host, orient="vertical", command=view.yview)
        view.configure(yscrollcommand=y_scroll.set)
        view.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        view.insert("1.0", _compare_text())
        view.mark_set("insert", "1.0")
        view.see("1.0")
        view.focus_set()

    def restore_original(self):
        """把最近一次輸出的 SRT／純文字還原為 AI 校對前的原始辨識結果。"""
        data = self.last_compare
        if not data:
            messagebox.showinfo("尚無資料", "請先完成一次 AI 校對。")
            return
        save_first = messagebox.askyesnocancel(
            "還原前留底",
            "還原會把輸出的檔案覆寫回 AI 校對前的原始辨識結果。\n\n"
            "是否先開啟校對對照文字檔留底？\n\n"
            "是：先開啟對照文字檔\n否：繼續還原\n取消：不還原"
        )
        if save_first is None:
            return
        if save_first:
            self.show_comparison()
            return
        if not messagebox.askyesno(
            "還原原始辨識",
            "將把輸出的 SRT／純文字檔覆寫回 AI 校對前的原始辨識結果。\n確定要還原嗎？"):
            return
        try:
            srt = data.get("srt")
            txt = data.get("txt")
            n = 0
            if srt:
                Path(srt).write_text(chunks_to_srt(data["before_chunks"]), encoding="utf-8-sig")
                self.log(f"已還原 SRT 為原始辨識：{srt}", tag="warn")
                n += 1
            if txt:
                Path(txt).write_text((data["before_text"] or "") + "\n", encoding="utf-8-sig")
                self.log(f"已還原純文字為原始辨識：{txt}", tag="warn")
                n += 1
            messagebox.showinfo("已還原", f"已將 {n} 個檔案還原為 AI 校對前的原始辨識結果。")
        except Exception as e:
            messagebox.showerror("還原失敗", str(e))

    # ── 設定視窗 ──────────────────────────────────────────

    def open_settings(self):
        win = tk.Toplevel(self)
        win.title("AI API 設定")
        win.configure(bg=BG)
        win.resizable(True, True)
        win.minsize(640, 560)
        win.grab_set()

        win_w, win_h = 780, 660
        sx = self.winfo_rootx() + (self.winfo_width()  - win_w) // 2
        sy = self.winfo_rooty() + (self.winfo_height() - win_h) // 2
        win.geometry(f"{win_w}x{win_h}+{max(0,sx)}+{max(0,sy)}")

        # ══════════════════════════════════════════════════
        # 底部固定區：先 pack 確保永遠可見
        # ══════════════════════════════════════════════════
        footer_frame = tk.Frame(win, bg=BG, padx=28, pady=10)
        footer_frame.pack(side="bottom", fill="x")

        tk.Frame(footer_frame, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))

        ver_row = tk.Frame(footer_frame, bg=BG)
        ver_row.pack(fill="x")
        tk.Label(ver_row, text="v1.0", bg=BG, fg=MUTED,
                 font=(FONT_FAMILY, 8)).pack(side="left")
        tk.Label(ver_row, text="By WiKi", bg=BG, fg=MUTED,
                 font=(FONT_FAMILY, 8)).pack(side="right")

        # ══════════════════════════════════════════════════
        # 主內容區（可捲動空間）
        # ══════════════════════════════════════════════════
        outer = tk.Frame(win, bg=BG, padx=28, pady=20)
        outer.pack(fill="both", expand=True)

        def _sep():
            tk.Frame(outer, bg=BORDER, height=1).pack(fill="x", pady=(4, 14))

        # ──────────────────────────────────────────────────
        # 區塊 1：API 供應商
        # ──────────────────────────────────────────────────
        tk.Label(outer, text="API 供應商", bg=BG, fg=MUTED,
                 font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", pady=(0, 10))

        PROVIDERS = [
            ("gemini",     "Google Gemini  ★推薦首選★", SUCCESS),
            ("openai",     "OpenAI",                 TEXT),
            ("claude",     "Claude（Anthropic）",     ACCENT),
            ("openrouter", "OpenRouter（多免費模型）", ACCENT2),
        ]
        provider_var = tk.StringVar(value=self.cfg.get("api_provider", "gemini"))

        # 每行 3 個，自動折行排列
        prov_frame = tk.Frame(outer, bg=BG)
        prov_frame.pack(anchor="w", pady=(0, 4))
        for i, (val, label, color) in enumerate(PROVIDERS):
            tk.Radiobutton(
                prov_frame, text=label, variable=provider_var, value=val,
                bg=BG, fg=color, selectcolor=BG,
                activebackground=BG, activeforeground=color,
                font=(FONT_FAMILY, 10),
            ).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 24), pady=3)

        _sep()

        # ──────────────────────────────────────────────────
        # 區塊 2：模型 / 網站 / 介紹
        # ──────────────────────────────────────────────────
        tk.Label(outer, text="模型", bg=BG, fg=MUTED,
                 font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", pady=(0, 6))

        model_var = tk.StringVar(value=self.cfg.get("model", "gemini-2.5-flash"))
        model_cb  = ttk.Combobox(outer, textvariable=model_var,
                                  font=(FONT_FAMILY, 10), state="normal")
        model_cb.pack(fill="x", pady=(0, 10))

        # 網站連結列
        site_row = tk.Frame(outer, bg=BG)
        site_row.pack(anchor="w", pady=(0, 10))
        tk.Label(site_row, text="網站：", bg=BG, fg=MUTED,
                 font=(FONT_FAMILY, 9)).pack(side="left")
        site_lbl = tk.Label(site_row, text="", bg=BG, fg=ACCENT,
                             font=(FONT_FAMILY, 9, "underline"), cursor="hand2")
        site_lbl.pack(side="left")

        # 介紹說明區
        hint_lbl = tk.Label(
            outer,
            text="",
            bg=PANEL2, fg=MUTED,
            font=(FONT_FAMILY, 9),
            justify="left", anchor="nw",
            wraplength=680,
            padx=12, pady=10,
        )
        hint_lbl.pack(fill="x", pady=(0, 4))

        _sep()

        # ──────────────────────────────────────────────────
        # 區塊 3：API Key
        # ──────────────────────────────────────────────────
        key_header = tk.Frame(outer, bg=BG)
        key_header.pack(fill="x", pady=(0, 6))
        tk.Label(key_header, text="API Key", bg=BG, fg=MUTED,
                 font=(FONT_FAMILY, 9, "bold")).pack(side="left")
        tk.Label(key_header, text="  Key 僅儲存在本機 config.json、絕不上傳；但啟用校對時，字幕文字會送往該供應商",
                 bg=BG, fg=MUTED, font=(FONT_FAMILY, 9)).pack(side="left")

        key_var  = tk.StringVar(value=self.cfg.get("api_key", ""))
        show_var = tk.BooleanVar(value=False)
        key_row  = tk.Frame(outer, bg=BG)
        key_row.pack(fill="x", pady=(0, 14))
        key_entry = tk.Entry(
            key_row, textvariable=key_var, show="•",
            bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
            relief="flat", highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT,
            font=(FONT_FAMILY, 10),
        )
        key_entry.pack(side="left", fill="x", expand=True)

        def toggle_show():
            key_entry.configure(show="" if show_var.get() else "•")
        tk.Checkbutton(
            key_row, text="顯示", variable=show_var, command=toggle_show,
            bg=BG, fg=MUTED, selectcolor=BG, activebackground=BG,
            font=(FONT_FAMILY, 9),
        ).pack(side="left", padx=(8, 0))

        _sep()

        # ──────────────────────────────────────────────────
        # 儲存 / 取消按鈕列（置中）
        # ──────────────────────────────────────────────────
        def save():
            self.cfg["api_provider"]        = provider_var.get()
            self.cfg["api_key"]             = key_var.get().strip()
            self.cfg["model"]               = model_var.get().strip()
            self.cfg["use_llm"]             = self.use_llm.get()
            self.cfg["use_text_fix"]        = self.use_text_fix.get()
            self.cfg["output_srt_enabled"]  = self.output_srt_enabled.get()
            self.cfg["output_txt_enabled"]  = self.output_txt_enabled.get()
            save_config(self.cfg)
            win.destroy()
            self.log(f"設定已儲存（供應商：{self.cfg['api_provider']} / 模型：{self.cfg['model']}）。",
                     tag="success")

        def cancel_settings():
            win.destroy()

        action_row = tk.Frame(outer, bg=BG)
        action_row.pack(pady=(0, 4))
        PillButton(action_row, text="✓ 儲存設定", command=save,
                   min_width=140, height=40, bold=True).pack(side="left", padx=(0, 12))
        PillButton(action_row, text="取消", command=cancel_settings,
                   min_width=90, height=40,
                   bg_color=BORDER, hover_color="#3A4655", fg_color=TEXT).pack(side="left")

        # ══════════════════════════════════════════════════
        # 動態邏輯：供應商切換
        # ══════════════════════════════════════════════════
        def open_provider_site(url: str):
            if url:
                webbrowser.open_new_tab(url)

        PROVIDER_MODELS = {
            "openai":     OPENAI_MODELS,
            "claude":     CLAUDE_MODELS,
            "gemini":     GEMINI_MODELS,
            "openrouter": OPENROUTER_MODELS,
        }

        def on_provider_change(*_):
            p  = provider_var.get()
            ml = PROVIDER_MODELS.get(p, GEMINI_MODELS)
            model_cb["values"] = ml
            if model_var.get() not in ml:
                model_var.set(ml[0])
            hint_lbl.configure(text=PROVIDER_HINTS.get(p, ""))
            site_name, site_url = PROVIDER_SITES.get(p, ("", ""))
            site_lbl.configure(text=site_name,
                               cursor="hand2" if site_url else "arrow")
            site_lbl.unbind("<Button-1>")
            if site_url:
                site_lbl.bind("<Button-1>",
                              lambda _e, url=site_url: open_provider_site(url))

        provider_var.trace_add("write", on_provider_change)

        def _update_wraplength(event=None):
            hint_lbl.configure(wraplength=max(300, win.winfo_width() - 80))
        win.bind("<Configure>", _update_wraplength)

        # 初始化
        on_provider_change()
        model_var.set(self.cfg.get("model", "gemini-2.5-flash"))

    # ── 日誌 / 進度 ───────────────────────────────────────

    def log(self, msg: str, tag: str = ""):
        def _append():
            now = datetime.datetime.now().strftime("%H:%M:%S")
            if not tag:
                _tag = "error" if msg.startswith("錯誤") else ""
            else:
                _tag = tag
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{now}] {msg}\n", _tag)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _append)

    def set_progress(self, val: int, status: str | None = None):
        def _up():
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=100)
            self.progress["value"] = val
            if status:
                self.status_text.set(status)
        self.after(0, _up)

    def set_busy(self, status: str):
        def _up():
            self.progress.configure(mode="indeterminate", maximum=100)
            self.progress.start(12)
            self.status_text.set(status)
        self.after(0, _up)

    def _dot(self, dot: StatusDot, status: str):
        self.after(0, lambda: dot.set(status))

    # ── 控制 ──────────────────────────────────────────────

    def cancel(self):
        self.cancel_event.set()
        self.cancel_btn.configure(state="disabled")
        self.status_text.set("正在停止，會在目前片段結束後中止")
        self.log("已要求取消。", tag="warn")

    def start(self):
        input_files = [p for p in self.input_files if Path(p).exists()]
        if not input_files:
            typed_path = self.input_path.get().strip()
            if typed_path and Path(typed_path).exists():
                input_files = [typed_path]

        if not input_files:
            messagebox.showerror("找不到檔案", "請先選擇要轉寫的音訊或影片檔。")
            return
        if not self.output_srt_enabled.get() and not self.output_txt_enabled.get():
            messagebox.showerror("未啟用任何輸出", "請至少開啟 SRT 或純文字其中一種輸出。")
            return
        if len(input_files) == 1:
            if not self.output_srt_path.get().strip() and self.output_srt_enabled.get():
                self.output_srt_path.set(str(Path(input_files[0]).with_suffix(".srt")))
            if not self.output_txt_path.get().strip() and self.output_txt_enabled.get():
                self.output_txt_path.set(str(Path(input_files[0]).with_suffix(".txt")))
        if self.use_llm.get() and not self.cfg.get("api_key"):
            if not messagebox.askyesno("尚未設定 API Key",
                                       "AI校對已啟用，但尚未設定 API Key。\n要繼續（只輸出原始辨識結果）嗎？"):
                return

        jobs = []
        for inp in input_files:
            base = str(Path(inp).with_suffix(""))
            if len(input_files) == 1:
                srt = self.output_srt_path.get().strip() if self.output_srt_enabled.get() else ""
                txt = self.output_txt_path.get().strip() if self.output_txt_enabled.get() else ""
            else:
                srt = base + ".srt" if self.output_srt_enabled.get() else ""
                txt = base + ".txt" if self.output_txt_enabled.get() else ""
            jobs.append((inp, srt, txt))

        self.cancel_event.clear()
        self.last_compare = None
        try:
            self.compare_btn.configure(state="disabled")
            self.restore_btn.configure(state="disabled")
        except Exception:
            pass
        self.run_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.set_progress(0, "準備中")
        self._dot(self.dot_breeze, "idle")
        self._dot(self.dot_llm,    "idle")

        context_notes = self.context_box.get("1.0", "end").strip()
        args = (jobs, self.use_llm.get(), context_notes, self.use_text_fix.get())
        threading.Thread(target=self.batch_worker, args=args, daemon=True).start()

    # ── 工作執行緒 ───────────────────────────────────────

    def load_breeze_pipeline(self):
        if self.pipeline is not None:
            return self.pipeline

        import torch
        from transformers import (AutomaticSpeechRecognitionPipeline,
                                   WhisperForConditionalGeneration, WhisperProcessor)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype  = torch.float16 if device == "cuda" else torch.float32
        self.log(f"PyTorch {torch.__version__}")
        self.log(f"裝置：{device.upper()}")
        if device == "cpu":
            self.log("提示：目前為 CPU 模式，辨識速度較慢（長音訊可能需數倍於播放長度的時間），"
                     "建議用於測試；若有 NVIDIA 顯示卡，請重跑安裝程式安裝 GPU 版以大幅加速。", tag="warn")
        self.log("載入 Breeze-ASR-25...首次使用會自動下載模型（約 3-4 GB），"
                 "下載期間視窗可能看起來沒反應，這是正常的，請保持網路連線並耐心等候；"
                 "若中途關閉視窗會中斷下載，下次會從未完成處續傳。", tag="model")
        self.set_busy("載入 Breeze 模型中（首次需下載 3-4 GB）")

        processor = WhisperProcessor.from_pretrained(BREEZE_MODEL_ID)
        model     = WhisperForConditionalGeneration.from_pretrained(
            BREEZE_MODEL_ID, torch_dtype=dtype, low_cpu_mem_usage=True, use_safetensors=True
        ).to(device)
        model.eval()
        self.pipeline = AutomaticSpeechRecognitionPipeline(
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            torch_dtype=dtype,
            device=0 if device == "cuda" else -1,
        )
        return self.pipeline

    def transcribe_breeze(self, audio: dict) -> tuple[list[dict], str]:
        import numpy as np
        samples      = audio["array"]
        sr           = audio["sampling_rate"]
        seg_samples  = SEGMENT_SECONDS * sr
        total_segs   = max(1, int(np.ceil(len(samples) / seg_samples)))
        chunks, texts = [], []

        for i in range(total_segs):
            if self.cancel_event.is_set():
                raise TranscriptionCancelled("已取消")
            s = i * seg_samples
            e = min(len(samples), s + seg_samples)
            seg = {"array": samples[s:e], "sampling_rate": sr}
            pct = 20 + int((i / total_segs) * 40)
            self.set_progress(pct, f"Breeze 辨識中：第 {i+1}/{total_segs} 段")
            result = self.pipeline(seg, return_timestamps=True)
            texts.append((result.get("text") or "").strip())
            offset = s / sr
            for chunk in result.get("chunks") or []:
                ts   = chunk.get("timestamp") or (0.0, 0.0)
                st   = ts[0] if ts[0] is not None else 0.0
                en   = ts[1] if ts[1] is not None else st + 2.0
                nc   = dict(chunk)
                nc["timestamp"] = (st + offset, en + offset)
                chunks.append(nc)

        chunks, removed = suppress_repeat_hallucination(chunks)
        if removed:
            self.log(f"偵測到連續重複的幻覺字幕，已自動清除 {removed} 組。", tag="warn")
        return punctuate_chunks(chunks), "".join(texts)

    def _process_one(self, inp: str, srt: str, txt: str,
                     use_llm: bool, context_notes: str = "", use_text_fix: bool = True):
        wav_path = None
        try:
            # ── 1. 轉 WAV ────────────────────────────────
            wav_path = convert_to_wav(inp, self.log)
            self.set_progress(10, "讀取音訊中")
            audio = read_wav_mono_16k(wav_path)

            # ── 2. Breeze ────────────────────────────────
            self._dot(self.dot_breeze, "running")
            pipe   = self.load_breeze_pipeline()
            self.log("Breeze：開始辨識...")
            chunks, raw_text = self.transcribe_breeze(audio)
            breeze_text = chunks_to_plain(chunks, raw_text)
            self.log(f"Breeze 完成，共 {len(breeze_text)} 字。", tag="success")
            self._dot(self.dot_breeze, "done")

            # ── 3. AI校對（若啟用，先校對再儲存）────────
            if use_llm and self.cfg.get("api_key"):
                self._dot(self.dot_llm, "running")
                self.set_progress(75, "AI校對中")
                self.log("AI 總編輯：送出校對請求...", tag="model")
                try:
                    total_batches_ref = [1]
                    def _llm_progress(batch_i, total):
                        total_batches_ref[0] = total
                        pct = 75 + int((batch_i / max(total, 1)) * 20)
                        self.set_progress(pct, f"AI校對第 {batch_i+1}/{total} 批")

                    before_chunks = [dict(c) for c in chunks]
                    llm_texts, llm_plain = llm_merge(
                        chunks, self.cfg, self.log,
                        context_notes=context_notes,
                        use_text_fix=use_text_fix,
                        progress_cb=_llm_progress,
                    )
                    after_chunks = [dict(c) for c in chunks]
                    if len(llm_texts) != len(before_chunks):
                        self.log(f"提示：AI 校對結果文字列數為 {len(llm_texts)}，原字幕為 {len(before_chunks)} 組，"
                                 "已用安全回填對齊，時間碼框架不受影響。", tag="warn")
                    # 鋼鐵律令：校對後時間碼組數必須與校對前一致，否則回退保護
                    if len(after_chunks) != len(before_chunks):
                        self.log(f"警告：校對後時間碼組數（{len(after_chunks)}）與校對前（{len(before_chunks)}）不一致，"
                                 "為保護時間碼框架，已回退為原始辨識結果。", tag="error")
                        chunks    = before_chunks
                        save_text = breeze_text
                        self._dot(self.dot_llm, "error")
                    else:
                        chunks    = after_chunks
                        save_text = llm_plain
                        self.log(f"AI校對完成，共 {len(llm_plain)} 字。", tag="success")
                        self._dot(self.dot_llm, "done")
                        self._store_compare(inp, srt, txt, before_chunks, after_chunks,
                                            breeze_text, llm_plain)
                except Exception as e:
                    self.log(f"錯誤：AI校對失敗：{e}，改儲存原始辨識結果。", tag="error")
                    self._dot(self.dot_llm, "error")
                    save_text = breeze_text
            else:
                self._dot(self.dot_llm, "idle")
                save_text = breeze_text

            # ── 4. 儲存（SRT 與純文字皆為最終版）────────
            if srt:
                Path(srt).write_text(chunks_to_srt(chunks), encoding="utf-8-sig")
                self.log(f"SRT 已儲存：{srt}")
            if txt:
                Path(txt).write_text(save_text + "\n", encoding="utf-8-sig")
                self.log(f"純文字已儲存：{txt}")

            self.set_progress(100, "完成 ✓")
        finally:
            if wav_path:
                Path(wav_path).unlink(missing_ok=True)

    def batch_worker(self, jobs: list[tuple[str, str, str]],
                     use_llm: bool, context_notes: str = "", use_text_fix: bool = True):
        total = len(jobs)
        done = 0
        failed = []
        try:
            for idx, (inp, srt, txt) in enumerate(jobs, start=1):
                if self.cancel_event.is_set():
                    raise TranscriptionCancelled("已取消")
                prefix = f"[{idx}/{total}] " if total > 1 else ""
                self.log(f"{prefix}開始處理：{inp}")
                self.set_progress(0, f"{prefix}準備中")
                try:
                    self._process_one(inp, srt, txt, use_llm, context_notes, use_text_fix)
                    done += 1
                except TranscriptionCancelled:
                    raise
                except Exception as e:
                    failed.append(f"{Path(inp).name}：{e}")
                    self.log(f"{prefix}錯誤：{e}", tag="error")
                    self._dot(self.dot_breeze, "error")
                    continue

            if failed:
                msg = f"已完成 {done}/{total} 個檔案，{len(failed)} 個失敗。\n\n" + "\n".join(failed[:5])
                self.set_progress(100 if done else 0, "批次完成（部分失敗）")
                self.after(0, lambda: messagebox.showwarning("批次完成", msg))
            else:
                msg = f"已完成 {done} 個檔案。" if total > 1 else "轉寫與校對完成。"
                self.after(0, lambda: messagebox.showinfo("完成", msg))

        except TranscriptionCancelled as e:
            self.log(str(e), tag="warn")
            self.set_progress(0, "已取消")
            self.after(0, lambda: messagebox.showinfo("已取消", f"已完成 {done}/{total} 個檔案。"))
        except Exception as e:
            self.log(f"錯誤：{e}")
            self.set_progress(0, "發生錯誤")
            self.after(0, lambda: messagebox.showerror("轉寫失敗", str(e)))
        finally:
            self.after(0, lambda: self.run_btn.configure(state="normal"))
            self.after(0, lambda: self.cancel_btn.configure(state="disabled"))


if __name__ == "__main__":
    enable_dpi_awareness()
    set_app_user_model_id()
    app = DualASRApp()
    app.mainloop()
