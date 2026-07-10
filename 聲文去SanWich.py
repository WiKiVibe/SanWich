"""
SanWich main app - CustomTkinter interface wired to the legacy core.

The legacy core is loaded read-only from an internal support file.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import datetime as _dt
import importlib.util
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import urllib.request
import wave
import webbrowser
from array import array
from pathlib import Path
from tkinter import filedialog, messagebox


ROOT = Path(__file__).resolve().parent
APP_VERSION = "2.3.1"
GITHUB_RELEASE_API = "https://api.github.com/repos/WiKiVibe/SanWich/releases/latest"
GITHUB_TAGS_API = "https://api.github.com/repos/WiKiVibe/SanWich/tags?per_page=1"
GITHUB_RELEASES_URL = "https://github.com/WiKiVibe/SanWich/releases/latest"


def here() -> Path:
    return ROOT


def user_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "SanWich"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SanWich"
    return Path.home() / ".config" / "SanWich"


def prepare_user_file(filename: str, legacy_path: Path) -> Path:
    """Return a persistent user-data path and migrate once without overwriting."""
    target = user_data_dir() / filename
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() and legacy_path.exists():
            shutil.copy2(legacy_path, target)
        return target
    except Exception:
        return legacy_path


CONFIG_PATH = prepare_user_file("config.json", ROOT / "config.json")
PERSONAL_RULES_PATH = prepare_user_file(
    "personal_rules.json",
    ROOT / "core" / "personal_rules.json",
)


def version_tuple(value: str) -> tuple[int, int, int]:
    numbers = [int(part) for part in re.findall(r"\d+", value or "")[:3]]
    return tuple((numbers + [0, 0, 0])[:3])


def fetch_latest_release(timeout: float = 5.0) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"SanWich/{APP_VERSION}",
    }
    try:
        request = urllib.request.Request(GITHUB_RELEASE_API, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        if isinstance(data, dict) and data.get("tag_name"):
            return data
    except Exception:
        pass

    request = urllib.request.Request(GITHUB_TAGS_API, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        tags = json.loads(response.read().decode("utf-8"))
    if not isinstance(tags, list) or not tags or not tags[0].get("name"):
        raise ValueError("GitHub response is missing a release or version tag")
    tag = str(tags[0]["name"])
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/WiKiVibe/SanWich/releases/tag/{tag}",
    }


def is_newer_version(latest: str, current: str = APP_VERSION) -> bool:
    return version_tuple(latest) > version_tuple(current)


def asset_path(*parts: str) -> Path:
    candidates = [
        here().joinpath("assets", "images", *parts),
        here().joinpath("assets", *parts),
        here().joinpath(*parts),
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def relaunch_with_project_python() -> None:
    venv_python = here() / ".venv" / "Scripts" / "python.exe"
    venv_pythonw = here() / ".venv" / "Scripts" / "pythonw.exe"
    if not venv_python.exists():
        return
    candidates = [venv_python]
    if venv_pythonw.exists():
        candidates.append(venv_pythonw)
    current = Path(sys.executable).resolve()
    if any(current == p.resolve() for p in candidates):
        return
    if os.environ.get("SANWICH_MAIN_RELAUNCHED") == "1":
        return
    env = os.environ.copy()
    env["SANWICH_MAIN_RELAUNCHED"] = "1"
    launcher = venv_pythonw if venv_pythonw.exists() else venv_python
    subprocess.Popen([str(launcher), str(Path(__file__).resolve())], cwd=str(here()), env=env)
    raise SystemExit(0)


def fix_tcl_paths() -> None:
    candidates = [
        here() / ".venv" / "tcl",
        Path(sys.base_prefix) / "tcl",
        Path(sys.prefix) / "tcl",
    ]
    for base in candidates:
        tcl = base / "tcl8.6"
        tk_dir = base / "tk8.6"
        if (tcl / "init.tcl").exists() and (tk_dir / "tk.tcl").exists():
            os.environ["TCL_LIBRARY"] = str(tcl)
            os.environ["TK_LIBRARY"] = str(tk_dir)
            return


relaunch_with_project_python()
fix_tcl_paths()

import tkinter as tk
from tkinter import font as tkfont
try:
    from PIL import Image, ImageOps
except Exception:
    Image = None
    ImageOps = None

try:
    import customtkinter as ctk
except Exception as exc:
    msg = f"無法啟動 聲文去SanWich，缺少 customtkinter。\n\n錯誤：{exc}"
    try:
        ctypes.windll.user32.MessageBoxW(None, msg, "聲文去SanWich", 0x10)
    except Exception:
        print(msg)
    raise SystemExit(1)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _HAS_DND = True
except Exception:
    DND_FILES = None
    TkinterDnD = None
    _HAS_DND = False


FONT = "Noto Sans TC"
EN_FONT = "TASA Explorer"

BG = "#121314"
BG_2 = "#121314"
CARD = "#262626"
CARD_DARK = "#1A1919"
LINE = "#434343"
TEXT = "#FBFBFB"
TEXT_ON_DARK = "#FBFBFB"
INK = "#151419"
MUTED = "#878787"
MUTED_ON_DARK = "#BDAEAA"
SNOW = "#F5F4ED"
AQUA = "#A0C9CB"
ORANGE = "#e0833a"
ORANGE_DARK = "#F56E0F"
GARNET = "#000000"
BLACK_KITE = "#27272b"
DARK = BLACK_KITE
DARK_2 = "#313131"
TEAL_2 = "#508A8C"
PLACEHOLDER = "#878787"
SUCCESS = "#4ADE80"
WARN = "#FBBF24"
ERROR = "#F87171"
RED_TEXT = "#B42318"
WIKIVIBE_URL = "https://portaly.cc/WiKiVibe"
GREEN_TEXT = "#027A48"
# Inspired by Breeze-ASR-25 and SubDesk's AI subtitle review workflow:
# https://github.com/mtkresearch/Breeze-ASR-25
# https://github.com/ji4/subdesk
AI_REVIEW = "#D97706"
AI_REVIEW_BG = "#3A2A17"
AI_REVIEW_BORDER = "#B45309"
TIME_ERROR = "#DC2626"
TIME_ERROR_BG = "#3B1818"

KLF_ACTIVATE = 0x00000001
ENGLISH_US_KEYBOARD = "00000409"
_WIN32_INPUT_API_READY = False


def init_win32_input_api() -> bool:
    global _WIN32_INPUT_API_READY
    if sys.platform != "win32":
        return False
    if _WIN32_INPUT_API_READY:
        return True
    try:
        user32 = ctypes.windll.user32
        imm32 = ctypes.windll.imm32
        user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
        user32.GetKeyboardLayout.restype = wintypes.HANDLE
        user32.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, wintypes.UINT]
        user32.LoadKeyboardLayoutW.restype = wintypes.HANDLE
        user32.ActivateKeyboardLayout.argtypes = [wintypes.HANDLE, wintypes.UINT]
        user32.ActivateKeyboardLayout.restype = wintypes.HANDLE
        imm32.ImmGetContext.argtypes = [wintypes.HWND]
        imm32.ImmGetContext.restype = wintypes.HANDLE
        imm32.ImmGetOpenStatus.argtypes = [wintypes.HANDLE]
        imm32.ImmGetOpenStatus.restype = wintypes.BOOL
        imm32.ImmSetOpenStatus.argtypes = [wintypes.HANDLE, wintypes.BOOL]
        imm32.ImmSetOpenStatus.restype = wintypes.BOOL
        imm32.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
        imm32.ImmReleaseContext.restype = wintypes.BOOL
    except Exception:
        return False
    _WIN32_INPUT_API_READY = True
    return True


def win32_keyboard_layout() -> int | None:
    if not init_win32_input_api():
        return None
    try:
        return int(ctypes.windll.user32.GetKeyboardLayout(0))
    except Exception:
        return None


def win32_ime_open(widget=None) -> bool | None:
    if not init_win32_input_api() or widget is None:
        return None
    try:
        hwnd = wintypes.HWND(int(widget.winfo_id()))
        himc = ctypes.windll.imm32.ImmGetContext(hwnd)
        if not himc:
            return None
        try:
            return bool(ctypes.windll.imm32.ImmGetOpenStatus(himc))
        finally:
            ctypes.windll.imm32.ImmReleaseContext(hwnd, himc)
    except Exception:
        return None


def win32_set_ime_open(widget=None, open_status: bool = False) -> None:
    if not init_win32_input_api() or widget is None:
        return
    try:
        hwnd = wintypes.HWND(int(widget.winfo_id()))
        himc = ctypes.windll.imm32.ImmGetContext(hwnd)
        if not himc:
            return
        try:
            ctypes.windll.imm32.ImmSetOpenStatus(himc, bool(open_status))
        finally:
            ctypes.windll.imm32.ImmReleaseContext(hwnd, himc)
    except Exception:
        pass


def win32_activate_keyboard_layout(layout: int | None) -> None:
    if not init_win32_input_api() or not layout:
        return
    try:
        ctypes.windll.user32.ActivateKeyboardLayout(wintypes.HANDLE(layout), 0)
    except Exception:
        pass


def win32_force_english_input(widget=None) -> None:
    if not init_win32_input_api():
        return
    try:
        english_layout = ctypes.windll.user32.LoadKeyboardLayoutW(ENGLISH_US_KEYBOARD, KLF_ACTIVATE)
        if english_layout:
            ctypes.windll.user32.ActivateKeyboardLayout(english_layout, 0)
        win32_set_ime_open(widget, False)
    except Exception:
        pass


def load_local_fonts() -> None:
    font_dir = here() / "assets" / "fonts"
    if not font_dir.exists():
        return
    try:
        add_font = ctypes.windll.gdi32.AddFontResourceExW
    except Exception:
        return
    for font_path in font_dir.rglob("*"):
        if font_path.suffix.lower() in {".ttf", ".otf"}:
            try:
                add_font(str(font_path), 0x10, 0)
            except Exception:
                pass


def choose_font(preferred: list[str], fallback: str) -> str:
    available = set(tkfont.families())
    for name in preferred:
        if name in available:
            return name
    return fallback


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def set_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WiKi.SanWich.main")
    except Exception:
        pass


def find_legacy_path() -> Path:
    preferred = here() / "core" / "SanWich_legacy_core.py"
    if preferred.exists():
        return preferred
    fallback = here() / "聲文去SanWich.py"
    if fallback.exists():
        return fallback
    for path in here().glob("*.py"):
        name = path.name.lower()
        if path.name == Path(__file__).name:
            continue
        if path.name == "ui_prototype.py":
            continue
        if "sanwich" in name:
            return path
    raise FileNotFoundError("找不到內部核心檔案 SanWich_legacy_core.py")


def load_legacy_core() -> types.ModuleType:
    path = find_legacy_path()
    source = path.read_text(encoding="utf-8")
    source = source.replace("\nrelaunch_in_local_venv()\n", "\n# main loader: legacy relaunch disabled.\n")
    module = types.ModuleType("SanWich_legacy_core")
    module.__file__ = str(path)
    module.__name__ = "SanWich_legacy_core"
    sys.modules[module.__name__] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


CORE = load_legacy_core()
# 導正路徑：core 以 importlib 載入，其 __file__ 位於 core/ 子資料夾，
# 會使 app_dir() 多算一層；強制以主程式所在資料夾(ROOT)為基準。
CORE.app_dir = lambda: ROOT
CORE.CONFIG_PATH = CONFIG_PATH


def load_personal_rules() -> types.ModuleType | None:
    """載入 core/personal_rules.py，找不到就回 None（不影響主流程）。"""
    path = here() / "core" / "personal_rules.py"
    if not path.exists():
        return None
    try:
        source = path.read_text(encoding="utf-8")
        module = types.ModuleType("SanWich_personal_rules")
        module.__file__ = str(path)
        module.__name__ = "SanWich_personal_rules"
        sys.modules[module.__name__] = module
        exec(compile(source, str(path), "exec"), module.__dict__)
        return module
    except Exception:
        return None


PERSONAL_RULES = load_personal_rules()


def load_diarization() -> types.ModuleType | None:
    """載入 core/diarization.py（語者分離，僅用於 TXT）。找不到或失敗回 None，不影響主流程。"""
    path = here() / "core" / "diarization.py"
    if not path.exists():
        return None
    try:
        source = path.read_text(encoding="utf-8")
        module = types.ModuleType("SanWich_diarization")
        module.__file__ = str(path)
        module.__name__ = "SanWich_diarization"
        sys.modules[module.__name__] = module
        exec(compile(source, str(path), "exec"), module.__dict__)
        return module
    except Exception:
        return None


DIARIZATION = load_diarization()


def load_license_manager() -> types.ModuleType | None:
    """載入 core/license_manager.py。失敗回 None，Free 功能不受任何影響。"""
    path = here() / "core" / "license_manager.py"
    if not path.exists():
        return None
    try:
        source = path.read_text(encoding="utf-8")
        module = types.ModuleType("SanWich_license_manager")
        module.__file__ = str(path)
        module.__name__ = "SanWich_license_manager"
        sys.modules[module.__name__] = module
        exec(compile(source, str(path), "exec"), module.__dict__)
        return module
    except Exception:
        return None


LICENSE_MODULE = load_license_manager()


def _create_license_manager():
    if LICENSE_MODULE is None:
        return None
    try:
        return LICENSE_MODULE.LicenseManager()
    except Exception:
        return None


LICENSE_MANAGER = _create_license_manager()

# 授權模組不可用時的備援：Free 功能一律照常，Supporter 功能保守關閉。
_FALLBACK_FREE_FEATURES = {
    "single_transcription", "export_srt", "export_txt",
    "basic_ai_proofread", "basic_srt_editor", "find_replace",
    "import_srt", "davinci_tools",
}

SUPPORTER_FEATURE_LABELS = {
    "batch_processing": "批次處理",
    "quick_compare_full": "快速對照完整版",
    "custom_rules": "個人化規則庫",
    "diarization": "語者分離",
    "domain_prompt_templates": "領域 Prompt 模板",
    "custom_dictionary": "自訂詞庫",
}


def has_feature(feature_name: str) -> bool:
    if LICENSE_MANAGER is not None:
        try:
            return LICENSE_MANAGER.has_feature(feature_name)
        except Exception:
            pass
    return feature_name in _FALLBACK_FREE_FEATURES


def license_status_summary() -> dict:
    if LICENSE_MANAGER is not None:
        try:
            return LICENSE_MANAGER.status_summary()
        except Exception:
            pass
    return {"mode": "free", "label": "Free", "trial_ends_at": "", "days_left": 0}


DEEPSEEK_MODELS = ["deepseek-v4-flash", "deepseek-v4-pro"]
_LEGACY_OPENROUTER_MODELS = tuple(getattr(CORE, "OPENROUTER_MODELS", ["google/gemma-3-27b-it:free"]))
_LEGACY_LLM_CALL_ONCE = getattr(CORE, "_llm_call_once")


def normalize_provider(provider: str | None) -> str:
    provider = (provider or "gemini").strip().lower()
    return "deepseek" if provider == "openrouter" else provider


def normalize_model(provider: str | None, model: str | None) -> str:
    provider = normalize_provider(provider)
    model = (model or "").strip()
    if provider == "deepseek":
        if not model or model in _LEGACY_OPENROUTER_MODELS or ":free" in model or "/" in model:
            return DEEPSEEK_MODELS[0]
    return model


def normalize_api_cfg(cfg: dict) -> dict:
    provider = normalize_provider(cfg.get("api_provider", "gemini"))
    cfg["api_provider"] = provider
    cfg["model"] = normalize_model(provider, cfg.get("model"))
    return cfg


def resolve_editor_prompt_flag(runtime_flag: bool, cfg: dict) -> bool:
    return bool(runtime_flag or cfg.get("use_text_fix", False))


def _resolve_personal_rules_state():
    """回傳 (store, rules_used, enabled_flag)。失敗一律回 None，不影響呼叫流程。"""
    if PERSONAL_RULES is None:
        return None, [], False
    try:
        store = PERSONAL_RULES.RuleStore(PERSONAL_RULES_PATH)
        return store, [], True
    except Exception:
        return None, [], False


def _llm_call_once_with_deepseek(system: str, user_msg: str, cfg: dict) -> str:
    provider = normalize_provider(cfg.get("api_provider", "gemini"))
    model = normalize_model(provider, cfg.get("model"))

    # ── 個人化規則注入（階段 5 輪 B）─────────────────────
    rules_section = ""
    rules_store = None
    rules_used: list[dict] = []
    use_rules = bool(cfg.get("use_personal_rules", True)) and PERSONAL_RULES is not None
    if use_rules:
        try:
            rules_store = PERSONAL_RULES.RuleStore(PERSONAL_RULES_PATH)
            rules_used = PERSONAL_RULES.select_rules_for_prompt(
                rules_store,
                domain=str(cfg.get("personal_rules_domain") or "通用"),
            )
            if rules_used:
                rules_section = PERSONAL_RULES.build_rules_section(rules_used)
                if rules_section:
                    system = (system or "") + "\n" + rules_section
        except Exception:
            rules_store = None
            rules_used = []

    if provider == "deepseek":
        api_key = (cfg.get("api_key") or "").strip()
        result = CORE._post_json(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            payload={
                "model": model or DEEPSEEK_MODELS[0],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.2,
                "max_tokens": 4096,
                "thinking": {"type": "disabled"},
            },
        )
        try:
            response_text = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"DeepSeek 回應格式異常：{result}") from exc
    else:
        patched_cfg = dict(cfg)
        patched_cfg["api_provider"] = provider
        patched_cfg["model"] = model
        response_text = _LEGACY_LLM_CALL_ONCE(system, user_msg, patched_cfg)

    # 採納率追蹤（best effort，失敗不影響回傳）
    if use_rules and rules_store is not None and rules_used:
        try:
            PERSONAL_RULES.track_rule_adoption(
                rules_store,
                user_msg,
                response_text,
                rules_used=rules_used,
                persist=True,
            )
        except Exception:
            pass

    return response_text


CORE._llm_call_once = _llm_call_once_with_deepseek

MEDIA_EXTS = getattr(CORE, "MEDIA_EXTS", {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".mkv", ".flac", ".aac", ".ogg", ".webm"})
OPENAI_MODELS = getattr(CORE, "OPENAI_MODELS", ["gpt-4o-mini", "gpt-4o"])
CLAUDE_MODELS = getattr(CORE, "CLAUDE_MODELS", ["claude-sonnet-4-5", "claude-haiku-4-5"])
GEMINI_MODELS = getattr(
    CORE,
    "GEMINI_MODELS",
    ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"],
)

PROVIDER_MODELS = {
    "gemini": GEMINI_MODELS,
    "openai": OPENAI_MODELS,
    "claude": CLAUDE_MODELS,
    "deepseek": DEEPSEEK_MODELS,
}

PROVIDER_LABELS = {
    "gemini": "Google Gemini",
    "openai": "OpenAI",
    "claude": "Claude",
    "deepseek": "DeepSeek",
}

PROVIDER_HINTS = {
    "gemini": "速度快、免費額度友善，建議優先使用 Gemini 2.5 Flash。",
    "openai": "穩定、通用性高，適合正式內容與較複雜的字幕校對。",
    "claude": "長文理解能力好，適合訪談、講座、議題式內容。",
    "deepseek": "OpenAI 相容格式，接法簡單，建議優先使用 deepseek-v4-flash。",
}

PROVIDER_SITES = {
    "gemini": ("Google AI Studio", "https://aistudio.google.com/apikey"),
    "openai": ("OpenAI API Keys", "https://platform.openai.com/api-keys"),
    "claude": ("Anthropic Console", "https://console.anthropic.com/"),
    "deepseek": ("DeepSeek API Keys", "https://platform.deepseek.com/api_keys"),
}

SRT_TIME_RE = re.compile(
    r"^\s*(\d{1,2}):([0-5]\d):([0-5]\d)[,.](\d{1,3})\s*$"
)
SRT_TIMECODE_RE = re.compile(
    r"^\s*(\d{1,2}:[0-5]\d:[0-5]\d[,.]\d{1,3})\s*-->\s*"
    r"(\d{1,2}:[0-5]\d:[0-5]\d[,.]\d{1,3})"
)


def parse_srt_time(value: str) -> float:
    match = SRT_TIME_RE.match(value or "")
    if not match:
        raise ValueError(f"時間碼格式不正確：{value}")
    hours, minutes, seconds, millis = match.groups()
    ms = int(millis.ljust(3, "0")[:3])
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + ms / 1000


def parse_srt_text(payload: str) -> list[dict]:
    chunks: list[dict] = []
    blocks = re.split(r"\n\s*\n", (payload or "").replace("\r\n", "\n").replace("\r", "\n").strip())
    for block in blocks:
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        time_line_index = 0
        if "-->" not in lines[0] and len(lines) > 1:
            time_line_index = 1
        if time_line_index >= len(lines):
            continue
        match = SRT_TIMECODE_RE.match(lines[time_line_index])
        if not match:
            continue
        start, end = parse_srt_time(match.group(1)), parse_srt_time(match.group(2))
        text = "\n".join(lines[time_line_index + 1 :]).strip()
        chunks.append({"timestamp": (start, end), "text": text})
    return chunks


def clone_chunks(chunks: list[dict]) -> list[dict]:
    copied = []
    for chunk in chunks:
        nc = dict(chunk)
        ts = nc.get("timestamp") or (nc.get("start", 0.0), nc.get("end", 0.0))
        nc["timestamp"] = (
            ts[0] if ts[0] is not None else 0.0,
            ts[1] if ts[1] is not None else (ts[0] or 0.0) + 2.0,
        )
        nc["text"] = (nc.get("text") or "").strip()
        copied.append(nc)
    return copied


def chunks_to_editable_srt(chunks: list[dict]) -> str:
    lines = []
    for idx, chunk in enumerate(chunks, start=1):
        ts = chunk.get("timestamp") or (0.0, 0.0)
        start = CORE.seconds_to_srt_time(ts[0] if ts[0] is not None else 0.0)
        end = CORE.seconds_to_srt_time(ts[1] if ts[1] is not None else (ts[0] or 0.0) + 2.0)
        # SRT 一律無標點（與 chunks_to_srt 一致）；保留使用者手動的換行
        text = CORE.strip_punct_for_srt((chunk.get("text") or "").strip())
        lines.extend([str(idx), f"{start} --> {end}", text, ""])
    return "\n".join(lines).strip() + "\n"


def chunks_to_editable_plain(chunks: list[dict]) -> str:
    return "\n".join((chunk.get("text") or "").replace("\n", " ").strip() for chunk in chunks if (chunk.get("text") or "").strip())


def find_ffplay() -> str | None:
    ffmpeg = CORE.find_ffmpeg()
    candidates = []
    if ffmpeg:
        candidates.append(Path(ffmpeg).with_name("ffplay.exe"))
    candidates.extend(
        [
            here() / "tools" / "ffmpeg" / "bin" / "ffplay.exe",
            here() / "ffmpeg" / "bin" / "ffplay.exe",
            here() / "ffplay.exe",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffplay")


def build_waveform_peaks(media_path: str, target_peaks: int = 6000) -> tuple[list[float], float]:
    peaks, duration, proxy_path = build_waveform_proxy(media_path, target_peaks=target_peaks, keep_proxy=False)
    if proxy_path:
        Path(proxy_path).unlink(missing_ok=True)
    return peaks, duration


def build_waveform_proxy(media_path: str, target_peaks: int = 6000, keep_proxy: bool = True) -> tuple[list[float], float, str | None]:
    if not media_path or not Path(media_path).exists():
        return [], 0.0, None
    ffmpeg = CORE.find_ffmpeg()
    if not ffmpeg:
        return [], 0.0, None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            media_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-sample_fmt",
            "s16",
            str(tmp_path),
        ]
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        with wave.open(str(tmp_path), "rb") as wav:
            frame_count = wav.getnframes()
            sample_rate = wav.getframerate() or 8000
            duration = frame_count / sample_rate if frame_count else 0.0
            if frame_count <= 0:
                return [], duration, str(tmp_path) if keep_proxy else None
            samples = array("h")
            samples.frombytes(wav.readframes(frame_count))
            if sys.byteorder == "big":
                samples.byteswap()
        if not samples:
            return [], duration, str(tmp_path) if keep_proxy else None
        bucket = max(1, len(samples) // max(1, target_peaks))
        peaks = []
        max_amp = 1
        for i in range(0, len(samples), bucket):
            peak = max(abs(v) for v in samples[i : i + bucket]) if samples[i : i + bucket] else 0
            peaks.append(peak)
            if peak > max_amp:
                max_amp = peak
        return [p / max_amp for p in peaks], duration, str(tmp_path) if keep_proxy else None
    except Exception:
        return [], 0.0, None
    finally:
        if not keep_proxy:
            tmp_path.unlink(missing_ok=True)


class TranscriptionCancelled(Exception):
    pass


class InfoBubble(ctk.CTkLabel):
    def __init__(
        self,
        parent,
        text: str,
        text_color: str = "#FFFFFF",
        tip_fg: str = SNOW,
        tip_text_color: str = DARK,
    ):
        super().__init__(
            parent,
            text="i",
            width=24,
            height=24,
            corner_radius=9,
            fg_color="transparent",
            text_color=text_color,
            font=(FONT, 12, "bold"),
            cursor="question_arrow",
        )
        self.tip_text = text
        self.tip = None
        self.tip_fg = tip_fg
        self.tip_text_color = tip_text_color
        self.bind("<Enter>", self.show)
        self.bind("<Leave>", self.hide)

    def show(self, _event=None):
        if self.tip:
            return
        self.tip = tk.Toplevel(self)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        transparent = "#010203"
        self.tip.configure(bg=transparent)
        if sys.platform == "win32":
            try:
                self.tip.wm_attributes("-transparentcolor", transparent)
            except Exception:
                pass
        self.tip.geometry(f"+{self.winfo_rootx()+18}+{self.winfo_rooty()+28}")
        box = ctk.CTkFrame(self.tip, fg_color=self.tip_fg, corner_radius=10, border_width=0)
        box.pack(padx=1, pady=1)
        ctk.CTkLabel(
            box,
            text=self.tip_text,
            text_color=self.tip_text_color,
            fg_color="transparent",
            font=(FONT, 12),
            justify="left",
            wraplength=340,
        ).pack(padx=14, pady=10)

    def hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class WikiVibeLink(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        bubble_image=None,
        qr_image=None,
        text_color: str = TEXT_ON_DARK,
    ):
        super().__init__(parent, fg_color="transparent")
        self.qr_image = qr_image
        self.qr_popup = None

        ctk.CTkLabel(
            self,
            text="By WiKiVibe",
            text_color=text_color,
            font=(EN_FONT, 12, "bold"),
        ).pack(side="left")

        self.link_widget = ctk.CTkLabel(
            self,
            image=bubble_image,
            text="" if bubble_image is not None else "WiKiVibe",
            width=28,
            height=28,
            fg_color="transparent",
            cursor="hand2",
            font=(FONT, 16),
        )
        self.link_widget.pack(side="left", padx=(6, 0))
        self.link_widget.bind("<Button-1>", self.open_link)
        self.link_widget.bind("<Enter>", self.show_qr)
        self.link_widget.bind("<Leave>", self.hide_qr)
        self.bind("<Destroy>", self.hide_qr, add="+")

    def open_link(self, _event=None):
        webbrowser.open_new_tab(WIKIVIBE_URL)

    def show_qr(self, _event=None):
        if self.qr_popup is not None:
            return
        self.qr_popup = tk.Toplevel(self)
        self.qr_popup.overrideredirect(True)
        self.qr_popup.attributes("-topmost", True)
        transparent_color = "#010203"
        popup_bg = "#FFFFFF"
        if sys.platform == "win32":
            try:
                self.qr_popup.wm_attributes("-transparentcolor", transparent_color)
                if str(self.qr_popup.wm_attributes("-transparentcolor")).lower() == transparent_color:
                    popup_bg = transparent_color
            except Exception:
                popup_bg = "#FFFFFF"
        self.qr_popup.configure(bg=popup_bg)

        box = ctk.CTkFrame(
            self.qr_popup,
            fg_color="#FFFFFF",
            corner_radius=13,
            border_width=1,
            border_color="#E5E7EB",
        )
        box.pack(padx=1, pady=1)
        label = ctk.CTkLabel(
            box,
            image=self.qr_image,
            text="" if self.qr_image is not None else "WiKiVibe",
            text_color=DARK,
            fg_color="transparent",
            font=(EN_FONT, 13, "bold"),
        )
        label.pack(padx=12, pady=12)

        self.qr_popup.update_idletasks()
        popup_w = self.qr_popup.winfo_width()
        popup_h = self.qr_popup.winfo_height()
        x = self.link_widget.winfo_rootx() + self.link_widget.winfo_width() - popup_w
        y = self.link_widget.winfo_rooty() - popup_h - 8
        if y < 0:
            y = self.link_widget.winfo_rooty() + self.link_widget.winfo_height() + 8
        x = max(8, min(x, self.winfo_screenwidth() - popup_w - 8))
        self.qr_popup.geometry(f"+{x}+{y}")

    def hide_qr(self, _event=None):
        if self.qr_popup is not None:
            try:
                self.qr_popup.destroy()
            except Exception:
                pass
            self.qr_popup = None


class GradientBackdrop(tk.Canvas):
    def __init__(self, parent, top=GARNET, bottom=GARNET):
        super().__init__(parent, highlightthickness=0, bd=0, bg=top)
        self.top = top
        self.bottom = bottom
        self.bind("<Configure>", self.draw)

    def draw(self, _event=None):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        # 拖動視窗只會改位置不改尺寸：尺寸沒變就不重畫，避免拖動卡頓
        if getattr(self, "_last_size", None) == (width, height):
            return
        self._last_size = (width, height)
        self.delete("all")
        t_rgb = self.winfo_rgb(self.top)
        b_rgb = self.winfo_rgb(self.bottom)
        for y in range(height):
            ratio = y / max(1, height - 1)
            rgb = tuple(int(t_rgb[i] + (b_rgb[i] - t_rgb[i]) * ratio) // 256 for i in range(3))
            color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            self.create_line(0, y, width, y, fill=color)


class GradientBar(tk.Canvas):
    def __init__(self, parent, left=ORANGE, right=GARNET, height=8, bg=CARD_DARK):
        super().__init__(parent, height=height, highlightthickness=0, bd=0, bg=bg)
        self.left = left
        self.right = right
        self.bind("<Configure>", self.draw)

    def draw(self, _event=None):
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        # 尺寸沒變就不重畫（拖動視窗不觸發重繪）
        if getattr(self, "_last_size", None) == (width, height):
            return
        self._last_size = (width, height)
        self.delete("all")
        l_rgb = self.winfo_rgb(self.left)
        r_rgb = self.winfo_rgb(self.right)
        for x in range(width):
            ratio = x / max(1, width - 1)
            rgb = tuple(int(l_rgb[i] + (r_rgb[i] - l_rgb[i]) * ratio) // 256 for i in range(3))
            color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            self.create_line(x, 0, x, height, fill=color)


class Card(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        title: str,
        step: str | None = None,
        hint: str | None = None,
        hint_outside: bool = False,
        hint_color: str = "#FFFFFF",
        hint_tip_fg: str | None = None,
        hint_tip_text_color: str | None = None,
        step_action: str | None = None,
        step_action_image=None,
        step_command=None,
        step_action_fg: str = "transparent",
        step_action_hover: str = "#2A2424",
        step_action_text_color: str = "#FFFFFF",
        step_action_font=None,
        step_action_width: int = 30,
        step_action_height: int = 30,
        fg_color: str = CARD,
        corner_radius: int = 23,
        **kwargs,
    ):
        is_light = fg_color == SNOW
        super().__init__(
            parent,
            fg_color=fg_color,
            corner_radius=corner_radius,
            border_width=0,
            border_color="#D7D3C5" if is_light else LINE,
            **kwargs,
        )
        self.is_light = is_light
        self.grid_columnconfigure(0, weight=1)

        header = tk.Frame(self, bg=fg_color, highlightthickness=0, bd=0)
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 10))
        header.grid_columnconfigure(3, weight=1)

        col = 0
        if step:
            ctk.CTkLabel(
                header,
                text=f"{step}.",
                fg_color="transparent",
                text_color=ORANGE,
                font=(EN_FONT, 22, "bold"),
            ).grid(row=0, column=0, sticky="w", padx=(0, 10))
            col = 1
            if step_action_image is not None:
                icon = ctk.CTkLabel(
                    header,
                    image=step_action_image,
                    text="",
                    fg_color="transparent",
                    cursor="hand2",
                )
                if step_command:
                    icon.bind("<Button-1>", lambda _event: step_command())
                icon.grid(row=0, column=1, sticky="w", padx=(0, 10))
                col = 2
            elif step_action:
                ctk.CTkButton(
                    header,
                    text=step_action,
                    width=step_action_width,
                    height=step_action_height,
                    corner_radius=max(8, max(step_action_width, step_action_height) // 3),
                    fg_color=step_action_fg,
                    hover_color=step_action_hover,
                    text_color=step_action_text_color,
                    font=step_action_font or ("Segoe UI Symbol", 15, "bold"),
                    command=step_command,
                    border_width=0,
                ).grid(row=0, column=1, sticky="w", padx=(0, 10))
                col = 2

        ctk.CTkLabel(
            header,
            text=title,
            text_color=INK if is_light else TEXT_ON_DARK,
            font=(FONT, 21, "bold"),
            anchor="w",
        ).grid(row=0, column=col, sticky="w")

        if hint and hint_outside:
            InfoBubble(
                self,
                hint,
                text_color=hint_color,
                tip_fg=hint_tip_fg or SNOW,
                tip_text_color=hint_tip_text_color or DARK,
            ).place(relx=1.0, x=-22, y=22, anchor="ne")
        elif hint:
            InfoBubble(
                header,
                hint,
                text_color=hint_color,
                tip_fg=hint_tip_fg or SNOW,
                tip_text_color=hint_tip_text_color or DARK,
            ).grid(row=0, column=4, sticky="e", padx=(10, 0))

        self.body = tk.Frame(self, bg=fg_color, highlightthickness=0, bd=0)
        self.body.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 22))
        self.body.grid_columnconfigure(0, weight=1)


class StatusChip(ctk.CTkLabel):
    COLORS = {
        "idle": ("待命", MUTED),
        "running": ("執行中", WARN),
        "done": ("完成", SUCCESS),
        "error": ("錯誤", ERROR),
    }

    def __init__(self, parent, label: str):
        self.label = label
        super().__init__(
            parent,
            text=f"{label}：待命",
            text_color=MUTED_ON_DARK,
            fg_color="#222020",
            corner_radius=12,
            font=(FONT, 12, "bold"),
            padx=12,
            pady=5,
        )

    def set(self, status: str):
        text, color = self.COLORS.get(status, self.COLORS["idle"])
        self.configure(text=f"{self.label}：{text}", text_color=color)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        # Apply after loading the theme so dynamic dialogs inherit the same scale.
        ctk.ThemeManager.theme["CTkScrollbar"]["corner_radius"] = 6
        load_local_fonts()
        self.apply_fonts()
        self.apply_logo()
        self.load_ui_assets()

        self.title("聲文去SanWich")
        self.geometry("1220x820")
        self.minsize(960, 640)
        self.configure(fg_color=GARNET)

        self.cfg = normalize_api_cfg(CORE.load_config())
        self.input_files: list[str] = []
        self.pipeline = None
        self.cancel_event = threading.Event()
        self.last_compare: dict | None = None
        self.batch_compares: dict = {}
        self.last_result: dict | None = None
        self.batch_results: list[dict] = []
        self.editor_index: int | None = None
        self.preview_process: subprocess.Popen | None = None
        self.notes_placeholder = True

        self.ai_enabled = ctk.BooleanVar(value=bool(self.cfg.get("use_llm", False)))
        self.editor_enabled = ctk.BooleanVar(value=bool(self.cfg.get("use_text_fix", False)))
        self.srt_enabled = ctk.BooleanVar(value=bool(self.cfg.get("output_srt_enabled", True)))
        self.txt_enabled = ctk.BooleanVar(value=bool(self.cfg.get("output_txt_enabled", True)))
        self.diarize_enabled = ctk.BooleanVar(value=bool(self.cfg.get("txt_diarization_enabled", False)))
        _diar_n = int(self.cfg.get("diarization_num_speakers", 3) or 3)
        self.diar_speakers = ctk.StringVar(value=f"{max(2, min(6, _diar_n))} 人")

        self.input_path = ctk.StringVar(value="")
        self.output_srt_path = ctk.StringVar(value="")
        self.output_txt_path = ctk.StringVar(value="")
        self.status_text = ctk.StringVar(value="待命")

        self.build()
        self.enable_drop_targets()
        self.log("主版已啟動。內部核心以唯讀方式載入。", "success")
        if not _HAS_DND:
            self.log("拖放套件未載入；仍可使用「選擇檔案」。", "warn")
        self.after(1400, self.check_for_updates_async)

    def apply_fonts(self):
        global FONT, EN_FONT
        FONT = choose_font(["Noto Sans TC", "NotoSansTC", "Microsoft JhengHei UI"], "Microsoft JhengHei UI")
        EN_FONT = choose_font(["TASA Explorer", "TASAExplorer", "Segoe UI"], "Segoe UI")

    def apply_logo(self):
        ico_path = asset_path("_LOGO.ico")
        if ico_path.exists():
            try:
                self.iconbitmap(str(ico_path))
            except Exception:
                pass
        png_path = asset_path("_LOGO.png")
        if png_path.exists():
            try:
                photo = tk.PhotoImage(file=str(png_path))
                self._logo_photo_ref = photo
                self.iconphoto(True, photo)
            except Exception:
                pass

    def _resolve_icon_path(self, image_name: str) -> Path | None:
        candidates: list[str] = []
        name = (image_name or "").strip()
        if name:
            stem = Path(name).stem
            if name.lower().endswith(".ico"):
                candidates.append(name)
            else:
                candidates.append(f"{stem}.ico")
                candidates.append(name)
        candidates.append("_LOGO.ico")
        seen: set[str] = set()
        for cand in candidates:
            if cand in seen:
                continue
            seen.add(cand)
            path = asset_path(cand)
            if path.exists():
                return path
        return None

    def apply_window_icon(self, win, image_name: str = "_setting.png", invert: bool = False):
        ico_path = self._resolve_icon_path(image_name)
        if ico_path is not None and ico_path.suffix.lower() == ".ico":
            def _set_ico():
                try:
                    win.iconbitmap(str(ico_path))
                    win._iconbitmap_ref = str(ico_path)
                except Exception:
                    pass
            _set_ico()
            try:
                win.after(150, _set_ico)
                win.after(400, _set_ico)
            except Exception:
                pass
        png_path = asset_path(image_name)
        if png_path.exists() and png_path.suffix.lower() == ".png":
            try:
                if invert and Image is not None and ImageOps is not None:
                    image = Image.open(png_path).convert("RGBA")
                    alpha = image.getchannel("A")
                    rgb = ImageOps.invert(image.convert("RGB"))
                    image = rgb.convert("RGBA")
                    image.putalpha(alpha)
                    image.thumbnail((64, 64), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    image.save(buf, format="PNG")
                    photo = tk.PhotoImage(data=buf.getvalue())
                else:
                    photo = tk.PhotoImage(file=str(png_path))
                win._iconphoto_ref = photo
                win.iconphoto(False, photo)
            except Exception:
                pass

    def load_ui_assets(self):
        self.setting_step_icon = self.load_tk_png("_setting.png", (20, 20))
        self.bubble_tea_icon = self.load_tk_png("_Bubble-tea.png", (24, 24))
        self.wikivibe_qr_image = self.load_tk_png("_portaly_wikivibe.png", (260, 260))
        self.fallback_setting_text = "⚙"

    def load_tk_png(self, name: str, size: tuple[int, int], invert: bool = False):
        path = asset_path(name)
        if not path.exists():
            return None
        try:
            if invert and Image is not None and ImageOps is not None:
                image = Image.open(path).convert("RGBA")
                alpha = image.getchannel("A")
                rgb = ImageOps.invert(image.convert("RGB"))
                image = rgb.convert("RGBA")
                image.putalpha(alpha)
                image.thumbnail(size, Image.Resampling.LANCZOS)
                return ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            image = tk.PhotoImage(file=str(path))
            if image.width() > size[0] or image.height() > size[1]:
                sx = max(1, math.ceil(image.width() / size[0]))
                sy = max(1, math.ceil(image.height() / size[1]))
                image = image.subsample(sx, sy)
            return image
        except Exception:
            return None

    def check_for_updates_async(self):
        def worker():
            try:
                release = fetch_latest_release()
                latest = str(release.get("tag_name") or "")
                if is_newer_version(latest):
                    self.after(0, lambda: self.show_update_notice(release))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def show_update_notice(self, release: dict):
        latest = str(release.get("tag_name") or "").strip()
        url = str(release.get("html_url") or GITHUB_RELEASES_URL)
        should_open = messagebox.askyesno(
            "發現新版本",
            f"SanWich {latest} 已經發佈。\n\n"
            f"目前版本：v{APP_VERSION}\n\n"
            "更新不會重設授權時間，也不會覆寫 API 設定或個人化規則庫。\n"
            "是否前往 GitHub 下載新版？",
            parent=self,
        )
        if should_open:
            webbrowser.open_new_tab(url)

    def build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        shell = tk.Frame(self, bg=GARNET, highlightthickness=0, bd=0)
        shell.grid(row=0, column=0, sticky="nsew", padx=(28, 14), pady=28)
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)

        self.main_canvas = tk.Canvas(
            shell,
            bg=GARNET,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.main_canvas.grid(row=0, column=0, sticky="nsew")

        self.main_scrollbar = tk.Scrollbar(
            shell,
            orient="vertical",
            command=self.main_canvas.yview,
            width=18,
            troughcolor="#2B1716",
            bg="#4A2927",
            activebackground=ORANGE_DARK,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.main_scrollbar.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        self.main_canvas.configure(yscrollcommand=self.main_scrollbar.set)

        content = tk.Frame(self.main_canvas, bg=GARNET, highlightthickness=0, bd=0)
        content.grid_columnconfigure(0, weight=5)
        content.grid_columnconfigure(1, weight=4)
        self.content_window = self.main_canvas.create_window((0, 0), window=content, anchor="nw")
        self._main_canvas_width_job = None
        self._pending_main_canvas_width = None
        self._last_main_canvas_width = None
        content.bind("<Configure>", self._sync_main_scrollregion)
        self.main_canvas.bind("<Configure>", self._sync_main_canvas_width)
        self.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

        self.hero_file(content)
        self.output_card(content)
        self.ai_card(content)
        self.action_card(content)
        self.result_card(content)
        self.log_card(content)

    def _sync_main_scrollregion(self, _event=None):
        if hasattr(self, "main_canvas"):
            self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))

    def _sync_main_canvas_width(self, event):
        self._pending_main_canvas_width = max(1, int(event.width))

        # First layout must be immediate; live resize events are coalesced so the
        # entire two-column page is not reflowed for every single pixel.
        if self._last_main_canvas_width is None:
            self._apply_pending_main_canvas_width()
            return

        if self._main_canvas_width_job is not None:
            try:
                self.after_cancel(self._main_canvas_width_job)
            except Exception:
                pass
        self._main_canvas_width_job = self.after(70, self._apply_pending_main_canvas_width)

    def _apply_pending_main_canvas_width(self):
        self._main_canvas_width_job = None
        width = self._pending_main_canvas_width
        if width is None or width == self._last_main_canvas_width:
            return
        if not hasattr(self, "content_window"):
            return
        try:
            self.main_canvas.itemconfigure(self.content_window, width=width)
        except tk.TclError:
            return
        self._last_main_canvas_width = width

    def _on_mousewheel(self, event):
        try:
            self.main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def hero_file(self, parent):
        card = Card(
            parent,
            "匯入影音",
            step="1",
            hint="可拖放或選擇多個檔案。支援 mp3、wav、m4a、mp4、mov、mkv、flac、aac、ogg、webm。",
            hint_outside=True,
            hint_color=TEXT_ON_DARK,
            hint_tip_fg=SNOW,
            hint_tip_text_color=DARK,
            fg_color=CARD,
            corner_radius=26,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 14), pady=(0, 14))
        ctk.CTkLabel(card.body, text="拖放音訊或影片", text_color=TEXT_ON_DARK, font=(FONT, 15, "bold"), anchor="w").grid(
            row=0, column=0, sticky="w", pady=(4, 4)
        )
        ctk.CTkLabel(
            card.body,
            text="或直接選擇檔案，可一次處理多個檔案。",
            text_color=MUTED_ON_DARK,
            font=(FONT, 14),
            anchor="w",
        ).grid(row=1, column=0, sticky="w")
        self.input_entry = ctk.CTkEntry(
            card.body,
            textvariable=self.input_path,
            height=46,
            corner_radius=16,
            fg_color=DARK_2,
            border_color=LINE,
            text_color=TEXT_ON_DARK,
            placeholder_text="尚未選擇檔案",
            placeholder_text_color=PLACEHOLDER,
            font=(FONT, 14),
        )
        self.input_entry.grid(row=2, column=0, sticky="ew", pady=(24, 0))
        ctk.CTkButton(
            card.body,
            text="選擇檔案",
            width=164,
            height=50,
            corner_radius=18,
            fg_color=ORANGE,
            hover_color=ORANGE_DARK,
            text_color="#FFFFFF",
            font=(FONT, 16, "bold"),
            command=self.choose_input,
        ).grid(row=3, column=0, sticky="w", pady=(16, 0))

    def output_card(self, parent):
        card = Card(
            parent,
            "輸出格式",
            step="2",
            hint="單一檔案可自訂輸出路徑；批次模式會自動使用各原檔名輸出。",
            hint_outside=True,
            hint_color=TEXT_ON_DARK,
            hint_tip_fg=SNOW,
            hint_tip_text_color=DARK,
            fg_color=CARD,
            corner_radius=23,
        )
        card.grid(row=1, column=0, sticky="nsew", padx=(0, 14), pady=(0, 14))
        card.body.grid_columnconfigure(1, weight=1)
        self.output_option(card.body, 0, "SRT 字幕", "保留時間碼輸出路徑", self.srt_enabled, self.output_srt_path, self.choose_srt, self.open_srt_folder)
        self.output_option(card.body, 1, "純文字", "純文字輸出路徑", self.txt_enabled, self.output_txt_path, self.choose_txt, self.open_txt_folder)
        diar_row = tk.Frame(card.body, bg=card.body.cget("bg"), highlightthickness=0, bd=0)
        diar_row.grid(row=2, column=0, columnspan=4, sticky="w", pady=(14, 0))
        ctk.CTkCheckBox(
            diar_row,
            text="純文字標註語者（語者分離）",
            variable=self.diarize_enabled,
            command=self.on_diarize_toggle,
            fg_color=ORANGE, hover_color=ORANGE_DARK, checkmark_color="#FFFFFF",
            text_color=TEXT_ON_DARK, font=(FONT, 14, "bold"),
            checkbox_width=24, checkbox_height=24, corner_radius=5, border_width=2,
        ).pack(side="left")
        InfoBubble(
            diar_row,
            "僅影響純文字（TXT）：自動分辨不同說話者，輸出「講者A／講者B…」分段。\n"
            "SRT 字幕不受影響，維持原本格式、不含語者。\n"
            "首次使用會自動下載離線模型（約 45MB），需保持網路連線。\n"
            "請選實際講者人數；不確定時寧可選多 1 個（選太少會把兩人併在一起）。",
            text_color=MUTED_ON_DARK, tip_fg=SNOW, tip_text_color=DARK,
        ).pack(side="left", padx=(6, 0))
        ctk.CTkLabel(diar_row, text="語者人數", text_color=MUTED_ON_DARK, font=(FONT, 13)).pack(side="left", padx=(16, 6))
        ctk.CTkOptionMenu(
            diar_row, values=["2 人", "3 人", "4 人", "5 人", "6 人"],
            variable=self.diar_speakers, command=lambda _v: self.persist_basic_config(),
            width=92, height=30, corner_radius=11,
            fg_color=DARK_2, button_color=ORANGE, button_hover_color=ORANGE_DARK,
            text_color=TEXT_ON_DARK, font=(FONT, 13), dropdown_fg_color=CARD, dropdown_text_color=TEXT_ON_DARK,
        ).pack(side="left")

    def output_option(self, parent, row, title, placeholder, var, path_var, choose_cmd, open_cmd):
        ctk.CTkCheckBox(
            parent,
            text=title,
            variable=var,
            command=self.persist_basic_config,
            fg_color=ORANGE,
            hover_color=ORANGE_DARK,
            checkmark_color="#FFFFFF",
            text_color=TEXT_ON_DARK,
            font=(FONT, 15, "bold"),
            checkbox_width=28,
            checkbox_height=28,
            corner_radius=6,
            border_width=2,
        ).grid(row=row, column=0, sticky="w", pady=(0, 16) if row == 0 else (0, 0))
        ctk.CTkEntry(
            parent,
            height=42,
            corner_radius=15,
            fg_color=DARK_2,
            border_color=LINE,
            text_color=TEXT_ON_DARK,
            textvariable=path_var,
            placeholder_text=placeholder,
            placeholder_text_color=PLACEHOLDER,
            font=(FONT, 14),
        ).grid(row=row, column=1, sticky="ew", padx=(14, 10), pady=(0, 16) if row == 0 else (0, 0))
        ctk.CTkButton(
            parent,
            text="另存為...",
            width=112,
            height=38,
            corner_radius=14,
            fg_color="#1a1919",
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=choose_cmd,
        ).grid(row=row, column=2, sticky="e", pady=(0, 16) if row == 0 else (0, 0))
        ctk.CTkButton(
            parent,
            text="開啟資料夾",
            width=112,
            height=38,
            corner_radius=14,
            fg_color="#1a1919",
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=open_cmd,
        ).grid(row=row, column=3, sticky="e", padx=(8, 0), pady=(0, 16) if row == 0 else (0, 0))

    def ai_card(self, parent):
        card = Card(
            parent,
            "",
            step="3",
            hint="AI 校對是主要功能；總編輯是進階修字規則。補充資料會一起送入校對提示。",
            hint_color=TEXT_ON_DARK,
            step_action="" if self.setting_step_icon is not None else self.fallback_setting_text,
            step_action_image=self.setting_step_icon,
            step_command=self.open_settings,
            step_action_fg="transparent",
            step_action_hover="#211919",
            step_action_text_color="#FFFFFF",
            step_action_font=("Segoe UI Symbol", 24, "bold"),
            step_action_width=46,
            step_action_height=46,
            fg_color=CARD_DARK,
            corner_radius=26,
        )
        card.grid(row=0, column=1, rowspan=2, sticky="nsew", pady=(0, 14))
        card.body.grid_columnconfigure(0, weight=1)
        self.ai_switch = ctk.CTkSwitch(
            card.body,
            text="AI校對",
            variable=self.ai_enabled,
            command=self.on_ai_toggle,
            progress_color=ORANGE,
            button_color="#FFFFFF",
            button_hover_color="#FFFFFF",
            fg_color="#7C7F89",
            text_color=TEXT_ON_DARK,
            font=(FONT, 18, "bold"),
            switch_width=82,
            switch_height=40,
        )
        self.ai_switch.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            card.body,
            text="保留時間碼，修正字幕文字。",
            text_color=MUTED_ON_DARK,
            font=(FONT, 13),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.editor_switch = ctk.CTkSwitch(
            card.body,
            text="啟用總編輯",
            variable=self.editor_enabled,
            command=self.persist_basic_config,
            progress_color=TEAL_2,
            button_color="#FFFFFF",
            button_hover_color="#FFFFFF",
            fg_color="#7C7F89",
            text_color=TEXT_ON_DARK,
            font=(FONT, 18, "bold"),
            switch_width=82,
            switch_height=40,
        )
        self.editor_switch.grid(row=2, column=0, sticky="w", pady=(24, 0))
        ctk.CTkLabel(
            card.body,
            text="修正錯別字、簡體字、簡中用語、專有名詞",
            text_color=MUTED_ON_DARK,
            font=(FONT, 13),
        ).grid(row=3, column=0, sticky="w", pady=(6, 0))
        ctk.CTkLabel(card.body, text="補充資料", text_color=TEXT_ON_DARK, font=(FONT, 17, "bold")).grid(
            row=4, column=0, sticky="w", pady=(28, 8)
        )
        self.notes_box = ctk.CTkTextbox(
            card.body,
            height=182,
            corner_radius=17,
            fg_color=DARK_2,
            border_width=1,
            border_color=LINE,
            text_color=TEXT_ON_DARK,
            font=(FONT, 12),
        )
        self.notes_box.grid(row=5, column=0, sticky="ew")
        self.install_notes_placeholder()

    def action_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=CARD_DARK, corner_radius=26, border_width=0, border_color="#0C0D12", height=214)
        card.grid(row=2, column=0, sticky="nsew", padx=(0, 14), pady=(6, 14))
        card.grid_propagate(False)
        card.grid_columnconfigure(0, weight=1)
        top = tk.Frame(card, bg=CARD_DARK, highlightthickness=0, bd=0)
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 8))
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text="4.", text_color=ORANGE, font=(EN_FONT, 22, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        chips = tk.Frame(top, bg=CARD_DARK, highlightthickness=0, bd=0)
        chips.grid(row=0, column=1, sticky="w", padx=(14, 0))
        self.breeze_chip = StatusChip(chips, "Breeze")
        self.breeze_chip.pack(side="left", padx=(0, 8))
        self.ai_chip = StatusChip(chips, "AI")
        self.ai_chip.pack(side="left")
        self.device_chip = ctk.CTkLabel(
            chips,
            text="裝置：偵測中",
            text_color=MUTED_ON_DARK,
            fg_color="#222020",
            corner_radius=12,
            font=(FONT, 12, "bold"),
            padx=12,
            pady=5,
        )
        self.device_chip.pack(side="left", padx=(8, 0))

        def _detect_device():
            try:
                import torch
                ok = bool(torch.cuda.is_available())
            except Exception:
                ok = False
            def _upd():
                if ok:
                    self.device_chip.configure(text="GPU", text_color=SUCCESS)
                else:
                    self.device_chip.configure(text="CPU待命", text_color=MUTED_ON_DARK)
            try:
                self.after(0, _upd)
            except Exception:
                pass

        threading.Thread(target=_detect_device, daemon=True).start()
        ctk.CTkLabel(
            card,
            textvariable=self.status_text,
            text_color=MUTED_ON_DARK,
            font=(FONT, 13),
        ).grid(row=3, column=0, sticky="w", padx=24, pady=(0, 8))
        self.progress = ctk.CTkProgressBar(card, height=18, corner_radius=7, progress_color=ORANGE, fg_color="#5E5654")
        self.progress.grid(row=2, column=0, sticky="ew", padx=24, pady=(18, 12))
        self.progress.set(0)
        actions = tk.Frame(card, bg=CARD_DARK, highlightthickness=0, bd=0)
        actions.grid(row=4, column=0, sticky="e", padx=24, pady=(0, 22))
        self.run_btn = ctk.CTkButton(
            actions,
            text="開始轉寫",
            width=164,
            height=54,
            corner_radius=19,
            fg_color=ORANGE,
            hover_color=TEAL_2,
            text_color="#FFFFFF",
            font=(FONT, 17, "bold"),
            command=self.start,
        )
        self.run_btn.pack(side="left")
        self.cancel_btn = ctk.CTkButton(
            actions,
            text="取消",
            width=98,
            height=44,
            corner_radius=15,
            fg_color="#32333B",
            hover_color="#45464F",
            text_color=MUTED_ON_DARK,
            font=(FONT, 13, "bold"),
            state="disabled",
            command=self.cancel,
        )
        self.cancel_btn.pack(side="left", padx=(14, 0))

    def result_card(self, parent):
        card = Card(
            parent,
            "校對結果",
            step="5",
            hint="完成轉寫後可開啟字幕編輯器；AI 校對後可用快速對照核對修改或還原原始辨識。",
            fg_color=CARD_DARK,
            corner_radius=23,
            height=234,
        )
        card.grid(row=2, column=1, sticky="nsew", pady=(6, 14))
        card.grid_propagate(False)
        self.result_label = ctk.CTkLabel(
            card.body,
            text="尚未產生校對結果",
            text_color=MUTED_ON_DARK,
            font=(FONT, 14),
            anchor="w",
        )
        self.result_label.grid(row=0, column=0, sticky="w", pady=(0, 14))
        row = tk.Frame(card.body, bg=card.body.cget("bg"), highlightthickness=0, bd=0)
        row.grid(row=1, column=0, sticky="ew")
        self.srt_editor_btn = ctk.CTkButton(
            row,
            text="開啟字幕編輯器",
            width=152,
            height=40,
            corner_radius=14,
            fg_color=ORANGE,
            hover_color=ORANGE_DARK,
            text_color="#FFFFFF",
            font=(FONT, 14, "bold"),
            state="disabled",
            command=self.open_srt_editor,
        )
        self.srt_editor_btn.pack(side="left")
        self.compare_btn = ctk.CTkButton(
            row,
            text="快速對照",
            width=124,
            height=40,
            corner_radius=14,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 14, "bold"),
            state="disabled",
            command=self.show_comparison,
        )
        self.compare_btn.pack(side="left", padx=(10, 0))

    def log_card(self, parent):
        card = Card(
            parent,
            "執行紀錄",
            hint="這裡顯示轉檔、辨識、AI 校對與儲存狀態。",
            fg_color=CARD,
            corner_radius=23,
        )
        card.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(0, 14))
        self.log_box = ctk.CTkTextbox(
            card.body,
            height=190,
            corner_radius=17,
            fg_color=DARK_2,
            border_width=1,
            border_color="#0C0D12",
            text_color=MUTED_ON_DARK,
            font=(FONT, 13),
        )
        self.log_box.grid(row=0, column=0, sticky="ew")

    def build_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", padx=32, pady=(0, 12))
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            footer,
            text="main",
            text_color=MUTED_ON_DARK,
            font=(EN_FONT, 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        WikiVibeLink(
            footer,
            bubble_image=self.bubble_tea_icon,
            qr_image=self.wikivibe_qr_image,
            text_color=MUTED_ON_DARK,
        ).grid(row=0, column=1, sticky="e")

    def install_notes_placeholder(self):
        text = "例如：受訪者｜黃先生（老黃）\n地點｜北投士林科技園區\n術語｜生成式 AI、RAG、向量資料庫"

        def show():
            self.notes_box.delete("1.0", "end")
            self.notes_box.configure(text_color=PLACEHOLDER)
            self.notes_box.insert("1.0", text)
            self.notes_placeholder = True

        def clear(_event=None):
            if self.notes_placeholder:
                self.notes_box.delete("1.0", "end")
                self.notes_box.configure(text_color=TEXT_ON_DARK)
                self.notes_placeholder = False

        def restore(_event=None):
            if not self.notes_box.get("1.0", "end").strip():
                show()

        show()
        self.notes_box.bind("<FocusIn>", clear)
        self.notes_box.bind("<Button-1>", clear)
        self.notes_box.bind("<FocusOut>", restore)

    def notes_text(self) -> str:
        if self.notes_placeholder:
            return ""
        return self.notes_box.get("1.0", "end").strip()

    def persist_basic_config(self):
        self.cfg["use_llm"] = bool(self.ai_enabled.get())
        self.cfg["use_text_fix"] = bool(self.editor_enabled.get())
        self.cfg["output_srt_enabled"] = bool(self.srt_enabled.get())
        self.cfg["output_txt_enabled"] = bool(self.txt_enabled.get())
        self.cfg["txt_diarization_enabled"] = bool(self.diarize_enabled.get())
        try:
            _sel = self.diar_speakers.get()
            self.cfg["diarization_num_speakers"] = int(_sel.split()[0])
        except Exception:
            self.cfg["diarization_num_speakers"] = 3
        CORE.save_config(self.cfg)

    def on_ai_toggle(self):
        if self.ai_enabled.get():
            self.editor_enabled.set(True)
        self.persist_basic_config()

    def enable_drop_targets(self):
        if not _HAS_DND:
            return
        try:
            TkinterDnD._require(self)
        except Exception as exc:
            message = str(exc)
            self.after(200, lambda msg=message: self.log(f"拖放初始化失敗：{msg}", "warn"))
            return

        registered = 0
        for widget in (self.input_entry,):
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self.on_file_drop)
                registered += 1
            except Exception as exc:
                message = str(exc)
                self.after(200, lambda msg=message: self.log(f"拖放目標註冊失敗：{msg}", "warn"))
        if registered:
            self.log("拖放已啟用。")
        else:
            self.log("拖放未啟用；請使用「選擇檔案」。", "warn")

    def preflight_dependencies(self) -> bool:
        if not CORE.find_ffmpeg():
            messagebox.showerror(
                "找不到 FFmpeg",
                "轉寫前需要 FFmpeg 轉換音訊格式。\n請先執行 setup 或安裝 FFmpeg 後再試。",
            )
            self.log("找不到 FFmpeg，無法開始轉寫。", "error")
            return False
        missing = []
        for module_name in ("torch", "transformers", "numpy"):
            if importlib.util.find_spec(module_name) is None:
                missing.append(module_name)
        if missing:
            messagebox.showerror(
                "缺少模型套件",
                "Breeze 轉寫需要以下套件：\n\n" + "\n".join(missing) + "\n\n請先執行 setup 後再試。",
            )
            self.log("缺少模型套件，無法開始轉寫。", "error")
            return False
        return True

    def on_file_drop(self, event):
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = [event.data]
        self.set_input_files(paths)

    def choose_input(self):
        patterns = " ".join(f"*{ext}" for ext in sorted(MEDIA_EXTS))
        paths = filedialog.askopenfilenames(title="選擇音訊或影片", filetypes=[("音訊或影片", patterns), ("所有檔案", "*.*")])
        if paths:
            self.set_input_files(paths)

    def set_input_files(self, paths):
        valid = []
        skipped = []
        for raw in paths:
            path = Path(str(raw).strip("{}\""))
            if path.exists() and path.suffix.lower() in MEDIA_EXTS:
                valid.append(str(path))
            else:
                skipped.append(str(path))
        if not valid:
            messagebox.showerror("沒有可用檔案", "請選擇支援的音訊或影片檔。")
            return
        self.input_files = valid
        first = Path(valid[0])
        self.input_path.set(str(first) if len(valid) == 1 else f"{first.name} 等 {len(valid)} 個檔案")
        self.output_srt_path.set(str(first.with_suffix(".srt")))
        self.output_txt_path.set(str(first.with_suffix(".txt")))
        self.log(f"已選擇 {len(valid)} 個檔案。", "success")
        if skipped:
            self.log(f"略過 {len(skipped)} 個不支援的檔案。", "warn")

    def choose_srt(self):
        path = filedialog.asksaveasfilename(title="儲存 SRT", defaultextension=".srt", filetypes=[("SRT 字幕", "*.srt")])
        if path:
            self.output_srt_path.set(path)

    def choose_txt(self):
        path = filedialog.asksaveasfilename(title="儲存純文字", defaultextension=".txt", filetypes=[("文字檔", "*.txt")])
        if path:
            self.output_txt_path.set(path)

    def open_srt_folder(self):
        self.open_folder(self.output_srt_path.get())

    def open_txt_folder(self):
        self.open_folder(self.output_txt_path.get())

    def open_folder(self, path: str):
        if not path.strip():
            messagebox.showerror("缺少路徑", "請先指定輸出檔案位置。")
            return
        folder = Path(path).expanduser().parent
        if not folder.exists():
            messagebox.showerror("找不到資料夾", str(folder))
            return
        os.startfile(folder)

    def on_diarize_toggle(self):
        """語者分離開關：Supporter 功能，未解鎖時自動關回並提示。"""
        if self.diarize_enabled.get() and not has_feature("diarization"):
            self.diarize_enabled.set(False)
            self.show_supporter_message("diarization")
            return
        self.persist_basic_config()

    def show_supporter_message(self, feature_name: str):
        """Supporter 功能提示：說明 Free 仍可完成核心工作，提供支持連結。"""
        label = SUPPORTER_FEATURE_LABELS.get(feature_name, feature_name)
        status = license_status_summary()
        if status["mode"] == "trial":
            status_line = (
                f"你正在使用 Supporter Trial，到期日：{status['trial_ends_at']}。\n"
                "試用結束後，SanWich 會回到 Free 模式，核心功能仍可繼續使用。"
            )
        else:
            status_line = (
                "你的 Supporter Trial 已結束。SanWich Free 仍可繼續使用。\n"
                "如果 SanWich 幫你省下時間，歡迎用 NT$99 起支持開發。"
            )

        win = ctk.CTkToplevel(self)
        win.title(f"{label}｜Supporter 功能")
        win.geometry("520x360")
        win.configure(fg_color=BG)
        self.apply_window_icon(win, "_setting.png")
        win.transient(self)
        win.grab_set()

        box = ctk.CTkFrame(win, fg_color=CARD, corner_radius=19, border_width=1, border_color=LINE)
        box.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(
            box, text=f"🔒 {label}", text_color=TEXT_ON_DARK, font=(FONT, 22, "bold")
        ).pack(anchor="w", padx=24, pady=(22, 8))
        ctk.CTkLabel(
            box,
            text=(
                f"{label}是 Supporter 功能。\n"
                "SanWich Free 仍可完成單檔字幕工作（辨識、校對、輸出、編輯）。\n\n"
                f"{status_line}\n\n"
                "支持開發可解鎖批次處理、快速對照完整版、個人化規則庫與語者分離。"
            ),
            text_color=MUTED_ON_DARK,
            font=(FONT, 14),
            justify="left",
            anchor="w",
            wraplength=440,
        ).pack(anchor="w", padx=24, pady=(0, 16))

        btns = ctk.CTkFrame(box, fg_color="transparent")
        btns.pack(fill="x", padx=24, pady=(4, 22))
        ctk.CTkButton(
            btns, text="支持開發", width=140, height=42, corner_radius=15,
            fg_color=ORANGE, hover_color=ORANGE_DARK, font=(FONT, 14, "bold"),
            command=lambda: webbrowser.open_new_tab(WIKIVIBE_URL),
        ).pack(side="left")
        ctk.CTkButton(
            btns, text="繼續使用 Free", width=140, height=42, corner_radius=15,
            fg_color="#32333B", hover_color="#45464F", font=(FONT, 14),
            command=win.destroy,
        ).pack(side="left", padx=(12, 0))

    def open_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("設定")
        # 高度依螢幕自動封頂，內容超出時可捲動
        win_h = min(840, max(560, win.winfo_screenheight() - 160))
        win.geometry(f"760x{win_h}")
        win.minsize(640, 520)
        win.configure(fg_color=BG)
        self.apply_window_icon(win, "_setting.png")
        win.transient(self)
        win.grab_set()

        outer = ctk.CTkScrollableFrame(win, fg_color=CARD, corner_radius=23, border_width=1, border_color=LINE)
        outer.pack(fill="both", expand=True, padx=24, pady=24)
        outer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(outer, text="API 設定", text_color=TEXT_ON_DARK, font=(FONT, 26, "bold")).grid(
            row=0, column=0, sticky="w", padx=24, pady=(22, 6)
        )
        ctk.CTkLabel(
            outer,
            text="Key 儲存在 %APPDATA%\\SanWich\\config.json；更新不會覆寫。啟用 AI 校對時字幕文字會傳送到所選供應商。",
            text_color=MUTED_ON_DARK,
            font=(FONT, 13),
        ).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 18))

        provider_var = ctk.StringVar(value=normalize_provider(self.cfg.get("api_provider", "gemini")))
        model_var = ctk.StringVar(value=self.cfg.get("model", "gemini-2.5-flash"))
        key_var = ctk.StringVar(value=self.cfg.get("api_key", ""))
        show_key = ctk.BooleanVar(value=False)

        provider = ctk.CTkSegmentedButton(
            outer,
            values=["gemini", "openai", "claude", "deepseek"],
            variable=provider_var,
            selected_color=ORANGE,
            selected_hover_color=ORANGE_DARK,
            unselected_color="#222020",
            unselected_hover_color="#2F2D2D",
            font=(EN_FONT, 13, "bold"),
            height=42,
        )
        provider.grid(row=2, column=0, sticky="ew", padx=24)

        hint_label = ctk.CTkLabel(
            outer,
            text="",
            text_color=MUTED_ON_DARK,
            fg_color=DARK_2,
            corner_radius=13,
            font=(FONT, 13),
            anchor="w",
            justify="left",
            wraplength=660,
        )
        hint_label.grid(row=3, column=0, sticky="ew", padx=24, pady=(14, 14))

        ctk.CTkLabel(outer, text="模型", text_color=TEXT_ON_DARK, font=(FONT, 14, "bold")).grid(
            row=4, column=0, sticky="w", padx=24, pady=(0, 6)
        )
        model_menu = ctk.CTkOptionMenu(
            outer,
            values=PROVIDER_MODELS.get(provider_var.get(), GEMINI_MODELS),
            variable=model_var,
            fg_color=DARK_2,
            button_color=DARK_2,
            button_hover_color="#2A2424",
            text_color=TEXT_ON_DARK,
            font=(EN_FONT, 13),
            dropdown_font=(EN_FONT, 12),
            dropdown_fg_color=DARK_2,
            dropdown_hover_color=GARNET,
            dropdown_text_color=TEXT_ON_DARK,
            corner_radius=15,
            height=42,
            anchor="w",
            dynamic_resizing=False,
        )
        model_menu.grid(row=5, column=0, sticky="ew", padx=24)

        ctk.CTkLabel(outer, text="API Key", text_color=TEXT_ON_DARK, font=(FONT, 14, "bold")).grid(
            row=6, column=0, sticky="w", padx=24, pady=(18, 6)
        )
        key_row = ctk.CTkFrame(outer, fg_color="transparent")
        key_row.grid(row=7, column=0, sticky="ew", padx=24)
        key_row.grid_columnconfigure(0, weight=1)
        key_entry = ctk.CTkEntry(
            key_row,
            textvariable=key_var,
            show="●",
            height=42,
            corner_radius=15,
            fg_color=DARK_2,
            border_color=LINE,
            font=(EN_FONT, 13),
        )
        key_entry.grid(row=0, column=0, sticky="ew")

        def toggle_key():
            key_entry.configure(show="" if show_key.get() else "●")

        ctk.CTkCheckBox(
            key_row,
            text="顯示",
            variable=show_key,
            command=toggle_key,
            fg_color=ORANGE,
            hover_color=ORANGE_DARK,
            font=(FONT, 13),
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))

        site_btn = ctk.CTkButton(
            outer,
            text="開啟申請頁",
            height=38,
            corner_radius=14,
            fg_color="#222020",
            hover_color="#2D2A2A",
            font=(FONT, 13),
        )
        site_btn.grid(row=8, column=0, sticky="w", padx=24, pady=(14, 18))

        def refresh_provider(*_):
            p = provider_var.get()
            models = PROVIDER_MODELS.get(p, GEMINI_MODELS)
            model_menu.configure(values=models)
            if model_var.get() not in models:
                model_var.set(models[0])
            hint_label.configure(text=f"{PROVIDER_LABELS.get(p, p)}｜{PROVIDER_HINTS.get(p, '')}")
            _, url = PROVIDER_SITES.get(p, ("", ""))
            site_btn.configure(command=lambda u=url: webbrowser.open_new_tab(u) if u else None)

        provider_var.trace_add("write", refresh_provider)
        refresh_provider()

        actions = ctk.CTkFrame(outer, fg_color="transparent")
        actions.grid(row=9, column=0, sticky="ew", padx=24, pady=(8, 22))
        actions.grid_columnconfigure(1, weight=1)

        def save():
            self.cfg["api_provider"] = normalize_provider(provider_var.get())
            self.cfg["model"] = normalize_model(self.cfg["api_provider"], model_var.get())
            self.cfg["api_key"] = key_var.get().strip()
            self.persist_basic_config()
            CORE.save_config(self.cfg)
            self.log(f"設定已儲存：{self.cfg['api_provider']} / {self.cfg['model']}", "success")
            win.destroy()

        ctk.CTkButton(
            actions,
            text=("個人化規則庫" if has_feature("custom_rules") else "個人化規則庫 🔒"),
            width=140,
            height=44,
            corner_radius=15,
            fg_color=DARK_2,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 14, "bold"),
            command=lambda: self.open_personal_rules_window(win),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            actions,
            text="儲存設定",
            width=140,
            height=44,
            corner_radius=15,
            fg_color=ORANGE,
            hover_color=TEAL_2,
            font=(FONT, 15, "bold"),
            command=save,
        ).grid(row=0, column=2, sticky="e", padx=(0, 10))
        ctk.CTkButton(
            actions,
            text="關閉",
            width=100,
            height=44,
            corner_radius=15,
            fg_color="#32333B",
            hover_color="#45464F",
            font=(FONT, 14),
            command=win.destroy,
        ).grid(row=0, column=3, sticky="e")

        # ── Supporter 狀態與 Key ──────────────────────────────
        supporter = ctk.CTkFrame(outer, fg_color=DARK_2, corner_radius=13)
        supporter.grid(row=10, column=0, sticky="ew", padx=24, pady=(0, 14))
        supporter.grid_columnconfigure(0, weight=1)

        lic_status = license_status_summary()
        lic_status_var = ctk.StringVar(value=f"版本狀態：{lic_status['label']}")
        ctk.CTkLabel(
            supporter,
            textvariable=lic_status_var,
            text_color=TEXT_ON_DARK,
            font=(FONT, 14, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 2))
        ctk.CTkLabel(
            supporter,
            text="SanWich Free 永久可用。Supporter 解鎖批次處理、快速對照完整版、個人化規則庫與語者分離。",
            text_color=MUTED_ON_DARK,
            font=(FONT, 12),
            anchor="w",
            justify="left",
            wraplength=620,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 8))

        sup_key_var = ctk.StringVar(value="")
        sup_key_entry = ctk.CTkEntry(
            supporter,
            textvariable=sup_key_var,
            placeholder_text="貼上 Supporter Key",
            height=38,
            corner_radius=14,
            fg_color="#222020",
            border_color=LINE,
            font=(EN_FONT, 13),
        )
        sup_key_entry.grid(row=2, column=0, sticky="ew", padx=(16, 10), pady=(0, 12))

        def apply_supporter_key():
            if LICENSE_MANAGER is None:
                messagebox.showerror("無法啟用", "授權模組載入失敗，請確認 core/license_manager.py 存在。", parent=win)
                return
            if LICENSE_MANAGER.activate_key(sup_key_var.get()):
                lic_status_var.set(f"版本狀態：{license_status_summary()['label']}")
                sup_key_var.set("")
                self.log("Supporter Key 已啟用，感謝支持 SanWich！", "success")
                messagebox.showinfo("啟用成功", "Supporter 功能已解鎖，感謝你的支持！", parent=win)
            else:
                messagebox.showerror("Key 無效", "請確認 Supporter Key 是否輸入正確。", parent=win)

        ctk.CTkButton(
            supporter,
            text="啟用 Key",
            width=110,
            height=38,
            corner_radius=14,
            fg_color=ORANGE,
            hover_color=ORANGE_DARK,
            font=(FONT, 13, "bold"),
            command=apply_supporter_key,
        ).grid(row=2, column=1, sticky="e", padx=(0, 16), pady=(0, 12))

        credits = ctk.CTkFrame(outer, fg_color="transparent")
        credits.grid(row=11, column=0, sticky="ew", padx=24, pady=(0, 18))
        credits.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            credits,
            text=f"v{APP_VERSION}",
            text_color=TEXT_ON_DARK,
            font=(EN_FONT, 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        brand = ctk.CTkFrame(credits, fg_color="transparent")
        brand.grid(row=0, column=1, sticky="e")
        WikiVibeLink(
            brand,
            bubble_image=self.bubble_tea_icon,
            qr_image=self.wikivibe_qr_image,
            text_color=TEXT_ON_DARK,
        ).pack(side="left")

    def log(self, msg: str, tag: str = ""):
        def append():
            now = _dt.datetime.now().strftime("%H:%M:%S")
            prefix = {"success": "✓", "warn": "!", "error": "×", "model": "AI"}.get(tag, "•")
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{now}] {prefix} {msg}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, append)

    def set_progress(self, pct: int, status: str | None = None):
        def update():
            self.progress.configure(mode="determinate")
            self.progress.set(max(0, min(100, pct)) / 100)
            if status:
                self.status_text.set(status)
        self.after(0, update)

    def set_busy(self, status: str):
        self.after(0, lambda: self.status_text.set(status))

    def set_chip(self, chip: StatusChip, status: str):
        self.after(0, lambda: chip.set(status))

    def cancel(self):
        self.cancel_event.set()
        self.cancel_btn.configure(state="disabled")
        self.status_text.set("正在取消，會在目前段落完成後停止")
        self.log("已要求取消。", "warn")

    def start(self):
        if not self.preflight_dependencies():
            return
        input_files = [p for p in self.input_files if Path(p).exists()]
        typed = self.input_path.get().strip()
        if not input_files and typed and Path(typed).exists():
            input_files = [typed]
        if not input_files:
            messagebox.showerror("找不到檔案", "請先選擇要轉寫的音訊或影片檔。")
            return
        if not self.srt_enabled.get() and not self.txt_enabled.get():
            messagebox.showerror("未啟用任何輸出", "請至少開啟 SRT 或純文字其中一種輸出。")
            return
        if len(input_files) > 1 and not has_feature("batch_processing"):
            self.show_supporter_message("batch_processing")
            return
        if self.diarize_enabled.get() and not has_feature("diarization"):
            self.diarize_enabled.set(False)
            self.persist_basic_config()
            self.show_supporter_message("diarization")
            return
        if len(input_files) == 1:
            if self.srt_enabled.get() and not self.output_srt_path.get().strip():
                self.output_srt_path.set(str(Path(input_files[0]).with_suffix(".srt")))
            if self.txt_enabled.get() and not self.output_txt_path.get().strip():
                self.output_txt_path.set(str(Path(input_files[0]).with_suffix(".txt")))
        self.persist_basic_config()
        if self.ai_enabled.get() and not (self.cfg.get("api_key") or "").strip():
            ok = messagebox.askyesno(
                "尚未設定 API Key",
                "AI 校對已開啟，但尚未設定 API Key。\n要繼續只輸出原始辨識結果嗎？",
            )
            if not ok:
                self.open_settings()
                return

        jobs = []
        for inp in input_files:
            base = str(Path(inp).with_suffix(""))
            if len(input_files) == 1:
                srt = self.output_srt_path.get().strip() if self.srt_enabled.get() else ""
                txt = self.output_txt_path.get().strip() if self.txt_enabled.get() else ""
            else:
                srt = base + ".srt" if self.srt_enabled.get() else ""
                txt = base + ".txt" if self.txt_enabled.get() else ""
            jobs.append((inp, srt, txt))

        self.cancel_event.clear()
        self.last_compare = None
        self.batch_compares = {}
        self.last_result = None
        self.batch_results = []
        self.editor_index = None
        self.compare_btn.configure(state="disabled")
        self.srt_editor_btn.configure(state="disabled")
        self.result_label.configure(text="尚未產生校對結果")
        self.run_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.set_chip(self.breeze_chip, "idle")
        self.set_chip(self.ai_chip, "idle")
        self.set_progress(0, "準備中")
        args = (jobs, self.ai_enabled.get(), self.notes_text(), self.editor_enabled.get(), self.diarize_enabled.get())
        threading.Thread(target=self.batch_worker, args=args, daemon=True).start()

    def load_breeze_pipeline(self):
        if self.pipeline is not None:
            return self.pipeline
        import torch
        from transformers import AutomaticSpeechRecognitionPipeline, WhisperForConditionalGeneration, WhisperProcessor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        self.log(f"PyTorch {torch.__version__}")
        self.log(f"裝置：{device.upper()}")
        if device == "cpu":
            self.log(
                "目前使用 CPU，載入與轉寫會比較久。若有 NVIDIA 顯示卡，建議安裝 GPU 版環境以大幅加速。",
                "warn",
            )
        self.log(
            "載入 Breeze-ASR-25；首次使用會自動下載模型，大約需要 3-4 GB，請保持網路連線並耐心等待。",
            "model",
        )
        self.set_busy("載入 Breeze 模型中（首次需下載 3-4 GB）")

        processor = WhisperProcessor.from_pretrained(CORE.BREEZE_MODEL_ID)
        model = WhisperForConditionalGeneration.from_pretrained(
            CORE.BREEZE_MODEL_ID,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
            use_safetensors=True,
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

        samples = audio["array"]
        sr = audio["sampling_rate"]
        seg_samples = CORE.SEGMENT_SECONDS * sr
        total_segs = max(1, int(np.ceil(len(samples) / seg_samples)))
        chunks = []
        texts = []

        for i in range(total_segs):
            if self.cancel_event.is_set():
                raise TranscriptionCancelled("已取消")
            s = i * seg_samples
            e = min(len(samples), s + seg_samples)
            seg = {"array": samples[s:e], "sampling_rate": sr}
            pct = 20 + int((i / total_segs) * 40)
            self.set_progress(pct, f"Breeze 辨識中：第 {i + 1}/{total_segs} 段")
            result = self.pipeline(seg, return_timestamps=True)
            texts.append((result.get("text") or "").strip())
            offset = s / sr
            for chunk in result.get("chunks") or []:
                ts = chunk.get("timestamp") or (0.0, 0.0)
                st = ts[0] if ts[0] is not None else 0.0
                en = ts[1] if ts[1] is not None else st + 2.0
                nc = dict(chunk)
                nc["timestamp"] = (st + offset, en + offset)
                chunks.append(nc)

        chunks, removed = CORE.suppress_repeat_hallucination(chunks)
        if removed:
            self.log(f"偵測到連續重複的幻覺字幕，已自動清除 {removed} 組。", "warn")
        return CORE.punctuate_chunks(chunks), "".join(texts)

    def process_one(self, inp: str, srt: str, txt: str, use_llm: bool, context_notes: str, use_text_fix: bool, diarize: bool = False):
        wav_path = None
        try:
            wav_path = CORE.convert_to_wav(inp, self.log)
            self.set_progress(10, "讀取音訊")
            audio = CORE.read_wav_mono_16k(wav_path)

            self.set_chip(self.breeze_chip, "running")
            self.load_breeze_pipeline()
            self.log("Breeze：開始辨識。")
            chunks, raw_text = self.transcribe_breeze(audio)
            breeze_text = CORE.chunks_to_plain(chunks, raw_text)
            self.log(f"Breeze 完成，共 {len(breeze_text)} 字。", "success")
            self.set_chip(self.breeze_chip, "done")

            save_text = breeze_text
            before_chunks = [dict(c) for c in chunks]
            if use_llm and (self.cfg.get("api_key") or "").strip():
                effective_use_text_fix = resolve_editor_prompt_flag(use_text_fix, self.cfg)
                self.set_chip(self.ai_chip, "running")
                self.set_progress(75, "AI 校對中")
                if effective_use_text_fix:
                    self.log("AI 總編輯：已強制套用總編輯 Prompt。", "model")
                else:
                    self.log("AI 校對：未啟用總編輯 Prompt，使用純 SRT 格式保護模式。", "model")
                try:
                    def progress(batch_i, total):
                        pct = 75 + int((batch_i / max(total, 1)) * 20)
                        self.set_progress(pct, f"AI 校對第 {batch_i + 1}/{total} 批")

                    llm_cfg = dict(self.cfg)
                    llm_cfg["use_text_fix"] = effective_use_text_fix
                    llm_texts, llm_plain = CORE.llm_merge(
                        chunks,
                        llm_cfg,
                        self.log,
                        context_notes=context_notes,
                        use_text_fix=effective_use_text_fix,
                        progress_cb=progress,
                    )
                    after_chunks = [dict(c) for c in chunks]
                    if len(llm_texts) != len(before_chunks):
                        self.log(
                            f"AI 校對只回傳 {len(llm_texts)}/{len(before_chunks)} 組可對齊文字；已保護時間碼，但校對內容可能不完整，建議開啟字幕編輯器檢查。",
                            "warn",
                        )
                    if len(after_chunks) != len(before_chunks):
                        mismatch_msg = (
                            f"AI 校對後字幕組數從 {len(before_chunks)} 變成 {len(after_chunks)}，"
                            "為保護時間碼框架，已自動回退為原始辨識結果。\n\n"
                            "可能原因：所選模型把 SRT 結構改壞。建議：\n"
                            "  ① 換個模型再試（例如 gemini-2.5-flash）\n"
                            "  ② 或暫時關閉「AI 校對」只用 Breeze 結果"
                        )
                        self.log("警告：校對後字幕組數不一致，已回退原始辨識。", "error")
                        chunks = before_chunks
                        save_text = breeze_text
                        self.set_chip(self.ai_chip, "error")
                        self.after(0, lambda m=mismatch_msg: messagebox.showwarning("AI 校對已自動回退", m))
                    else:
                        chunks = after_chunks
                        save_text = llm_plain
                        self.set_chip(self.ai_chip, "done")
                        self.store_compare(inp, srt, txt, before_chunks, after_chunks, breeze_text, llm_plain)
                        self.log(f"AI 校對完成，共 {len(llm_plain)} 字。", "success")
                except Exception as exc:
                    self.log(f"AI 校對失敗：{exc}，改儲存原始辨識結果。", "error")
                    self.set_chip(self.ai_chip, "error")
                    chunks = before_chunks
                    save_text = breeze_text
            else:
                self.set_chip(self.ai_chip, "idle")

            if srt:
                Path(srt).write_text(CORE.chunks_to_srt(chunks), encoding="utf-8-sig")
                self.log(f"SRT 已儲存：{srt}")
            if txt:
                txt_content = save_text
                if diarize and DIARIZATION is not None:
                    try:
                        self.set_progress(96, "語者分離中（首次需下載模型）")
                        self.log("語者分離：開始（sherpa-onnx + 3D-Speaker ERes2Net，僅套用於純文字）。", "model")
                        num_spk = int(self.cfg.get("diarization_num_speakers", 3) or 0)

                        def diar_progress(done_seg, total_seg):
                            if total_seg:
                                self.set_progress(96 + int((done_seg / total_seg) * 3), "語者分離中")

                        turns = DIARIZATION.diarize_array(
                            audio["array"], audio["sampling_rate"],
                            num_speakers=(num_spk if num_spk > 0 else None),
                            models_base=ROOT, log=self.log, progress=diar_progress,
                        )
                        spk_chunks = DIARIZATION.assign_speakers_to_chunks(chunks, turns)
                        n_spk = DIARIZATION.count_speakers(spk_chunks)
                        speaker_txt = DIARIZATION.chunks_to_speaker_txt(spk_chunks)
                        if speaker_txt.strip():
                            txt_content = speaker_txt
                            self.log(f"語者分離完成，偵測到 {n_spk} 位語者，已套用於純文字。", "success")
                        else:
                            self.log("語者分離未產生有效分段，純文字改用無語者版本。", "warn")
                    except Exception as exc:
                        self.log(f"語者分離失敗：{exc}；純文字改用無語者版本。", "warn")
                        txt_content = save_text
                elif diarize and DIARIZATION is None:
                    self.log("找不到語者分離模組（core/diarization.py），純文字改用無語者版本。", "warn")
                Path(txt).write_text(txt_content.rstrip("\n") + "\n", encoding="utf-8-sig")
                self.log(f"純文字已儲存：{txt}")
            editor_chunks = clone_chunks(chunks)
            if srt and Path(srt).exists():
                try:
                    parsed = parse_srt_text(Path(srt).read_text(encoding="utf-8-sig"))
                    if parsed:
                        editor_chunks = parsed
                except Exception as exc:
                    self.log(f"SRT 編輯器讀取輸出檔失敗，改用內部字幕資料：{exc}", "warn")
            self.store_result(inp, srt, txt, editor_chunks)
            self.set_progress(100, "完成")
        finally:
            if wav_path:
                Path(wav_path).unlink(missing_ok=True)

    def batch_worker(self, jobs, use_llm: bool, context_notes: str, use_text_fix: bool, diarize: bool = False):
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
                    self.process_one(inp, srt, txt, use_llm, context_notes, use_text_fix, diarize)
                    done += 1
                except TranscriptionCancelled:
                    raise
                except Exception as exc:
                    failed.append(f"{Path(inp).name}：{exc}")
                    self.log(f"{prefix}錯誤：{exc}", "error")
                    self.set_chip(self.breeze_chip, "error")
                    continue
            if failed:
                msg = f"已完成 {done}/{total} 個檔案；{len(failed)} 個失敗。\n\n" + "\n".join(failed[:5])
                self.after(0, lambda: messagebox.showwarning("批次完成", msg))
            else:
                msg = f"已完成 {done} 個檔案。" if total > 1 else "轉寫與校對完成。"
                self.after(0, lambda: messagebox.showinfo("完成", msg))
        except TranscriptionCancelled:
            self.log(f"已取消，完成 {done}/{total} 個檔案。", "warn")
            self.set_progress(0, "已取消")
            self.after(0, lambda: messagebox.showinfo("已取消", f"已完成 {done}/{total} 個檔案。"))
        except Exception as exc:
            self.log(f"錯誤：{exc}", "error")
            self.set_progress(0, "發生錯誤")
            self.after(0, lambda: messagebox.showerror("轉寫失敗", str(exc)))
        finally:
            self.after(0, lambda: self.run_btn.configure(state="normal"))
            self.after(0, lambda: self.cancel_btn.configure(state="disabled"))

    def store_result(self, inp: str, srt: str, txt: str, chunks: list[dict]):
        result = {
            "inp": inp,
            "srt": srt,
            "txt": txt,
            "chunks": clone_chunks(chunks),
        }
        self.last_result = result
        self.batch_results.append(result)

        def enable():
            self.srt_editor_btn.configure(state="normal")
            if not self.last_compare:
                self.result_label.configure(text=f"共 {len(chunks)} 組字幕，可開啟字幕編輯器")

        self.after(0, enable)

    def record_srt_edits(self, original: list[dict], updated: list[dict], data: dict, action: str) -> int:
        records = []
        now = _dt.datetime.now().isoformat(timespec="seconds")
        max_len = max(len(original), len(updated))
        for i in range(max_len):
            before = original[i] if i < len(original) else {}
            after = updated[i] if i < len(updated) else {}
            before_ts = before.get("timestamp") or (None, None)
            after_ts = after.get("timestamp") or (None, None)
            before_text = (before.get("text") or "").strip()
            after_text = (after.get("text") or "").strip()
            changed = before_text != after_text or before_ts != after_ts
            if not changed:
                continue
            records.append(
                {
                    "time": now,
                    "action": action,
                    "input": data.get("inp", ""),
                    "srt": data.get("srt", ""),
                    "txt": data.get("txt", ""),
                    "index": i + 1,
                    "before_start": before_ts[0],
                    "before_end": before_ts[1],
                    "after_start": after_ts[0],
                    "after_end": after_ts[1],
                    "before_text": before_text,
                    "after_text": after_text,
                }
            )
        if records:
            log_dir = here() / "logs"
            log_dir.mkdir(exist_ok=True)
            with (log_dir / "srt_edit_history.jsonl").open("a", encoding="utf-8") as fh:
                for record in records:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return len(records)

    def stop_preview(self):
        proc = self.preview_process
        self.preview_process = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    def play_srt_segment(self, media_path: str, start: float, end: float):
        if not media_path or not Path(media_path).exists():
            messagebox.showinfo("找不到原始檔", "需要原始音訊或影片檔，才能播放對應片段。")
            return
        if end <= start:
            messagebox.showerror("時間碼錯誤", "結束時間必須晚於開始時間。")
            return
        player = find_ffplay()
        if not player:
            messagebox.showinfo("找不到播放器", "找不到 ffplay.exe，請先確認 FFmpeg 工具完整安裝。")
            return
        self.stop_preview()
        duration = max(0.1, end - start)
        cmd = [
            player,
            "-hide_banner",
            "-loglevel",
            "error",
            "-autoexit",
            "-nodisp",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            media_path,
        ]
        try:
            self.preview_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            messagebox.showerror("播放失敗", str(exc))

    def open_srt_editor(self, index=None):
        if not getattr(self, "batch_results", None):
            self.batch_results = []
        if index is not None and 0 <= index < len(self.batch_results):
            data = dict(self.batch_results[index])
            self.editor_index = index
        else:
            if not self.last_result:
                messagebox.showinfo("尚無字幕", "請先完成一次轉寫。")
                return
            data = dict(self.last_result)
            self.editor_index = next(
                (i for i, r in enumerate(self.batch_results) if r.get("inp") == data.get("inp")),
                None,
            )
        original_chunks = clone_chunks(data.get("chunks") or [])
        if not original_chunks:
            messagebox.showinfo("尚無字幕", "目前沒有可編輯的字幕段落。")
            return

        editor_opened_at = _dt.datetime.now()
        suggestion_state = {"done": False}

        waveform_peaks, waveform_duration, waveform_proxy_path = build_waveform_proxy(data.get("inp", ""))
        playback_source = waveform_proxy_path or data.get("inp", "")
        subtitle_duration = max(
            ((chunk.get("timestamp") or (0.0, 0.0))[1] or 0.0 for chunk in original_chunks),
            default=0.0,
        )
        timeline_duration = max(1.0, waveform_duration, subtitle_duration)
        selected_index = {"value": 0}
        selected_indices: set[int] = {0}
        drag_state = {"index": None, "mode": "", "offset": 0.0, "duration": 0.0, "moved": False}
        playhead = {"time": 0.0}
        playback = {"playing": False, "started_at": None, "started_from": 0.0, "after_id": None}
        saved_snapshot = {"chunks": clone_chunks(original_chunks)}
        undo_stack: list[list[dict]] = []
        redo_stack: list[list[dict]] = []
        text_edit_started = {"index": None}
        playhead_items = {"line": None, "head": None}
        inline_editor = {"window": None, "text": None, "index": None}
        scrub_preview = {"after_id": None}
        pan_state = {"active": False, "x": 0, "view": 0.0}
        selection_drag = {"active": False, "x0": 0.0, "x1": 0.0, "rect": None}
        ai_review_indices: set[int] = set()
        compare_for_file = None
        if getattr(self, "batch_compares", None):
            compare_for_file = self.batch_compares.get(data.get("inp"))
        if compare_for_file is None and self.last_compare and self.last_compare.get("inp") == data.get("inp"):
            compare_for_file = self.last_compare
        if compare_for_file is not None:
            self.last_compare = compare_for_file
            before_chunks_for_review = compare_for_file.get("before_chunks") or []
            for i, (before, current) in enumerate(zip(before_chunks_for_review, original_chunks)):
                # 剝標點再比對：純標點差異（例如還原後少了逗號）不算 AI 修改
                bt = CORE.strip_punct_for_srt((before.get("text") or "").strip())
                at = CORE.strip_punct_for_srt((current.get("text") or "").strip())
                if bt != at:
                    ai_review_indices.add(i)

        win = ctk.CTkToplevel(self)
        win.title("SRT 字幕編輯器")
        win.geometry("1280x920")
        win.minsize(1000, 780)
        win.configure(fg_color=BLACK_KITE)
        self.apply_window_icon(win, "_LOGO.png")
        win.transient(self)
        win.grab_set()
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(2, weight=0)
        win.grid_rowconfigure(3, weight=1)

        head = ctk.CTkFrame(win, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 10))
        head.grid_columnconfigure(3, weight=1)
        batch_count = len(getattr(self, "batch_results", []) or [])
        if batch_count > 1 and self.editor_index is not None:
            ctk.CTkButton(
                head, text="＜", width=40, height=32, corner_radius=12,
                fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK,
                font=(EN_FONT, 16, "bold"), command=lambda: switch_file(-1),
            ).grid(row=0, column=0, sticky="w", padx=(0, 6))
            ctk.CTkLabel(
                head, text=f"檔案 {self.editor_index + 1}/{batch_count}",
                text_color=MUTED_ON_DARK, font=(FONT, 12, "bold"),
            ).grid(row=0, column=1, sticky="w", padx=(0, 6))
            ctk.CTkButton(
                head, text="＞", width=40, height=32, corner_radius=12,
                fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK,
                font=(EN_FONT, 16, "bold"), command=lambda: switch_file(1),
            ).grid(row=0, column=2, sticky="w", padx=(0, 14))
        ctk.CTkLabel(
            head,
            text=f"SRT 字幕編輯器｜{Path(data.get('inp', '')).name}",
            text_color=TEXT_ON_DARK,
            font=(FONT, 22, "bold"),
            anchor="w",
        ).grid(row=0, column=3, sticky="w")
        status_var = ctk.StringVar(value=f"共 {len(original_chunks)} 組字幕")
        ctk.CTkLabel(
            head,
            textvariable=status_var,
            text_color=MUTED_ON_DARK,
            font=(FONT, 13),
        ).grid(row=0, column=4, sticky="e")

        tools = ctk.CTkFrame(win, fg_color="transparent")
        tools.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 8))
        tools.grid_columnconfigure(1, weight=1)
        click_play_enabled = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            tools,
            text="點選自動播放",
            variable=click_play_enabled,
            progress_color=ORANGE,
            button_color="#FFFFFF",
            button_hover_color="#FFFFFF",
            fg_color="#7C7F89",
            text_color=MUTED_ON_DARK,
            font=(FONT, 13, "bold"),
            switch_width=56,
            switch_height=28,
        ).grid(row=0, column=0, sticky="w")
        zoom_var = ctk.DoubleVar(value=90.0 if timeline_duration <= 180 else 45.0)
        ctk.CTkLabel(tools, text="時間軸縮放", text_color=MUTED_ON_DARK, font=(FONT, 12)).grid(row=0, column=2, sticky="e", padx=(12, 8))
        zoom_slider = ctk.CTkSlider(
            tools,
            from_=24,
            to=180,
            variable=zoom_var,
            width=190,
            button_color=ORANGE,
            button_hover_color=ORANGE_DARK,
            progress_color=TEAL_2,
            fg_color="#4B5057",
        )
        zoom_slider.grid(row=0, column=3, sticky="e")

        def show_shortcuts_popup():
            tip = ctk.CTkToplevel(win)
            tip.title("快捷鍵")
            tip.configure(fg_color=BLACK_KITE)
            tip.geometry("380x470")
            tip.transient(win)
            try:
                tip.grab_set()
            except Exception:
                pass
            ctk.CTkLabel(tip, text="字幕編輯器快捷鍵", text_color=TEXT_ON_DARK, font=(FONT, 16, "bold")).pack(anchor="w", padx=20, pady=(18, 4))
            shortcut_lines = [
                ("空白鍵", "播放 / 暫停"),
                ("滑鼠滾輪", "移動 playhead（微調）"),
                ("Ctrl + 滾輪", "縮放時間軸"),
                ("滑鼠中鍵拖曳", "平移時間軸"),
                ("雙擊字幕方塊", "編輯文字"),
                ("Shift + 左鍵", "範圍連續選取字幕"),
                ("Ctrl + 右鍵 / 左鍵", "加選 / 取消選取字幕"),
                ("拖曳下方空白區", "框選多個字幕"),
                ("C", "在 playhead 處切開字幕"),
                ("I / O", "設選取字幕的 進點 / 出點 為 playhead"),
                ("U", "設進點並對齊上一則出點"),
                ("P", "設出點並對齊下一則進點"),
                ("↑ / ↓", "playhead 跳到選取字幕 進點 / 出點"),
                ("Delete", "刪除選取字幕"),
                ("Ctrl + Z", "復原"),
                ("Ctrl + Shift + Z", "重做"),
                ("Ctrl + F / Ctrl + H", "尋找 / 取代"),
            ]
            list_box = ctk.CTkScrollableFrame(tip, fg_color="transparent")
            list_box.pack(fill="both", expand=True, padx=14, pady=(0, 14))
            for key, desc in shortcut_lines:
                line = ctk.CTkFrame(list_box, fg_color="transparent")
                line.pack(fill="x", pady=2)
                ctk.CTkLabel(line, text=key, text_color=ORANGE, font=(FONT, 12, "bold"), width=150, anchor="w").pack(side="left")
                ctk.CTkLabel(line, text=desc, text_color=TEXT_ON_DARK, font=(FONT, 12), anchor="w", justify="left").pack(side="left", fill="x", expand=True)

        info_btn = ctk.CTkButton(
            tools,
            text="ⓘ",
            width=30,
            height=28,
            corner_radius=10,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(EN_FONT, 15, "bold"),
            command=show_shortcuts_popup,
        )
        info_btn.grid(row=0, column=4, sticky="e", padx=(8, 0))

        timeline_shell = ctk.CTkFrame(win, fg_color=CARD_DARK, corner_radius=14, border_width=1, border_color=LINE)
        timeline_shell.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 6))
        timeline_shell.grid_columnconfigure(0, weight=1)
        timeline_canvas = tk.Canvas(
            timeline_shell,
            height=420,
            bg="#202428",
            highlightthickness=0,
            bd=0,
            relief="flat",
            takefocus=1,
        )
        timeline_canvas.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        transport = ctk.CTkFrame(timeline_shell, fg_color="transparent")
        transport.grid(row=1, column=0, sticky="ew", padx=14, pady=(8, 0))
        transport.grid_columnconfigure(2, weight=1)
        transport.grid_columnconfigure(9, weight=1)
        prev_btn = ctk.CTkButton(
            transport,
            text="⏮",
            width=48,
            height=36,
            corner_radius=13,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(EN_FONT, 16, "bold"),
            command=lambda: goto_previous_caption(),
        )
        prev_btn.grid(row=0, column=5, sticky="e", padx=(0, 8))
        play_btn = ctk.CTkButton(
            transport,
            text="▶",
            width=58,
            height=38,
            corner_radius=14,
            fg_color=ORANGE,
            hover_color=ORANGE_DARK,
            text_color="#FFFFFF",
            font=(EN_FONT, 17, "bold"),
            command=lambda: toggle_playback(),
        )
        play_btn.grid(row=0, column=6, sticky="e", padx=(0, 8))
        next_btn = ctk.CTkButton(
            transport,
            text="⏭",
            width=48,
            height=36,
            corner_radius=13,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(EN_FONT, 16, "bold"),
            command=lambda: goto_next_caption(),
        )
        next_btn.grid(row=0, column=7, sticky="e", padx=(0, 8))
        split_btn = ctk.CTkButton(
            transport,
            text="✂",
            width=42,
            height=34,
            corner_radius=12,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(EN_FONT, 16, "bold"),
            command=lambda: split_caption_at_playhead(),
        )
        split_btn.grid(row=0, column=8, sticky="e")
        undo_btn = ctk.CTkButton(
            transport,
            text="↶",
            width=38,
            height=34,
            corner_radius=12,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(EN_FONT, 16, "bold"),
            command=lambda: undo_last(),
        )
        undo_btn.grid(row=0, column=3, sticky="e", padx=(0, 8))
        redo_btn = ctk.CTkButton(
            transport,
            text="↷",
            width=38,
            height=34,
            corner_radius=12,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(EN_FONT, 16, "bold"),
            command=lambda: redo_last(),
        )
        redo_btn.grid(row=0, column=4, sticky="e", padx=(0, 8))
        add_btn = ctk.CTkButton(
            transport,
            text="＋ 新增字幕",
            width=112,
            height=36,
            corner_radius=13,
            fg_color="#243A2E",
            hover_color="#2F5140",
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=lambda: add_caption_at_playhead(),
        )
        add_btn.grid(row=0, column=0, sticky="w", padx=(0, 8))
        merge_btn = ctk.CTkButton(
            transport,
            text="⇄ 合併",
            width=92,
            height=36,
            corner_radius=13,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=lambda: merge_selected_captions(),
        )
        merge_btn.grid(row=0, column=1, sticky="w", padx=(0, 8))
        replace_btn = ctk.CTkButton(
            transport,
            text="🔎 取代",
            width=92,
            height=36,
            corner_radius=13,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=lambda: show_find_replace(True),
        )
        replace_btn.grid(row=0, column=10, sticky="e", padx=(0, 6))
        delete_btn = ctk.CTkButton(
            transport,
            text="刪除",
            width=78,
            height=36,
            corner_radius=13,
            fg_color="#3A2022",
            hover_color="#5A2B2F",
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=lambda: delete_selected_captions(),
        )
        delete_btn.grid(row=0, column=11, sticky="e")
        timeline_scroll = tk.Scrollbar(
            timeline_shell,
            orient="horizontal",
            command=timeline_canvas.xview,
            width=16,
            troughcolor="#2A3036",
            bg="#58616B",
            activebackground=ORANGE_DARK,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        timeline_scroll.grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 8))
        timeline_canvas.configure(xscrollcommand=timeline_scroll.set)

        table_shell = ctk.CTkFrame(win, fg_color=CARD_DARK, corner_radius=17, border_width=1, border_color=LINE, height=200)
        table_shell.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 8))
        table_shell.grid_columnconfigure(0, weight=1)
        table_shell.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(table_shell, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        for col, weight in ((0, 0), (1, 0), (2, 0), (3, 1)):
            header.grid_columnconfigure(col, weight=weight)
        labels = [("序號", 58), ("開始", 126), ("結束", 126), ("字幕文字", 420)]
        for col, (label, width) in enumerate(labels):
            ctk.CTkLabel(
                header,
                text=label,
                width=width,
                text_color=MUTED_ON_DARK,
                font=(FONT, 12, "bold"),
                anchor="w",
            ).grid(row=0, column=col, sticky="ew", padx=(0, 8))

        body = ctk.CTkScrollableFrame(
            table_shell,
            fg_color="transparent",
            scrollbar_button_color=DARK,
            scrollbar_button_hover_color=ORANGE_DARK,
        )
        body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        for col, weight in ((0, 0), (1, 0), (2, 0), (3, 1)):
            body.grid_columnconfigure(col, weight=weight)
        try:
            body._scrollbar.configure(width=16, corner_radius=6, button_color="#2C2222", button_hover_color=ORANGE_DARK)
        except Exception:
            pass

        rows = []
        timeline_redraw_job = {"id": None, "text_id": None, "resize_id": None}
        # 靜態層（背景/刻度/聲波）快取：只有縮放或畫布寬度改變才需要重建
        static_cache = {"zoom": None, "width": None}
        input_mode_state = {
            "layout": win32_keyboard_layout(),
            "ime_open": win32_ime_open(win),
            "english_active": False,
        }

        def remember_text_input_mode(widget=None):
            if input_mode_state["english_active"]:
                return
            layout = win32_keyboard_layout()
            if layout:
                input_mode_state["layout"] = layout
            ime_open = win32_ime_open(widget)
            if ime_open is not None:
                input_mode_state["ime_open"] = ime_open

        def force_editor_english(widget=None):
            remember_text_input_mode(widget)
            win32_force_english_input(widget)
            input_mode_state["english_active"] = True

        def restore_text_input_mode(widget=None):
            layout = input_mode_state.get("layout")
            if layout:
                win32_activate_keyboard_layout(layout)
            ime_open = input_mode_state.get("ime_open")
            if ime_open is not None:
                win32_set_ime_open(widget, bool(ime_open))
            input_mode_state["english_active"] = False

        def input_widget_targets(widget):
            seen = set()
            for target in (widget, getattr(widget, "_entry", None), getattr(widget, "_textbox", None)):
                if target is None:
                    continue
                ident = id(target)
                if ident in seen:
                    continue
                seen.add(ident)
                yield target

        def mark_cjk_text_widget(widget):
            for target in input_widget_targets(widget):
                setattr(target, "_sanwich_allow_cjk_ime", True)
                target.bind("<FocusIn>", lambda event: restore_text_input_mode(event.widget), add="+")
                target.bind("<FocusOut>", lambda event: force_editor_english(event.widget), add="+")

        def mark_english_widget(widget):
            for target in input_widget_targets(widget):
                setattr(target, "_sanwich_allow_cjk_ime", False)
                target.bind("<FocusIn>", lambda event: force_editor_english(event.widget), add="+")

        def sync_editor_input_mode(event):
            widget = getattr(event, "widget", None)
            if bool(getattr(widget, "_sanwich_allow_cjk_ime", False)):
                restore_text_input_mode(widget)
            else:
                force_editor_english(widget)

        def chunks_equal(left: list[dict], right: list[dict]) -> bool:
            if len(left) != len(right):
                return False
            for a, b in zip(left, right):
                ats = a.get("timestamp") or (0.0, 0.0)
                bts = b.get("timestamp") or (0.0, 0.0)
                if abs((ats[0] or 0.0) - (bts[0] or 0.0)) > 0.001:
                    return False
                if abs((ats[1] or 0.0) - (bts[1] or 0.0)) > 0.001:
                    return False
                if (a.get("text") or "").strip() != (b.get("text") or "").strip():
                    return False
            return True

        def play_row(row_index: int):
            row = rows[row_index]
            try:
                start = parse_srt_time(row["start"].get())
                end = parse_srt_time(row["end"].get())
            except Exception as exc:
                messagebox.showerror("時間碼錯誤", str(exc))
                return
            set_playhead(start, center=True, redraw=False)
            start_playback()

        def selected_row_index() -> int:
            return max(0, min(len(rows) - 1, int(selected_index["value"]))) if rows else 0

        def timeline_width() -> int:
            canvas_width = max(900, timeline_canvas.winfo_width() or 900)
            px_per_second = max(1.0, float(zoom_var.get()))
            return max(canvas_width, int(timeline_duration * px_per_second) + 48)

        def center_on_time(seconds: float, ratio: float = 0.5):
            px_per_second = max(1.0, float(zoom_var.get()))
            total_width = timeline_width()
            visible = max(1, timeline_canvas.winfo_width() or 1)
            if total_width <= visible:
                timeline_canvas.xview_moveto(0)
                return
            x = 24 + max(0.0, min(timeline_duration, seconds)) * px_per_second
            # Tk xview_moveto(f) 真實行為：xOrigin = f * total_width
            # 想讓 playhead 落在 view 內 ratio 的位置 → xOrigin = x - visible*ratio
            # 並且 xOrigin 必須夾在 [0, total - visible] 之間，避免捲過頭、
            # 把 playhead 推到畫面左側看不見的地方（原本 bug 用錯分母 total - visible
            # 造成接近時間軸尾端時 fraction > 1，被 clamp 到 1.0 → 整段過捲）。
            target_origin = x - visible * ratio
            max_origin = float(total_width - visible)
            target_origin = max(0.0, min(max_origin, target_origin))
            fraction = target_origin / float(total_width)
            timeline_canvas.xview_moveto(max(0.0, min(1.0, fraction)))

        def set_playhead(seconds: float, *, center: bool = False, redraw: bool = True):
            playhead["time"] = max(0.0, min(timeline_duration, seconds))
            selection_changed = sync_selection_to_playhead() if rows else False
            if selection_changed:
                scroll_text_row_to_view(selected_index["value"])
            if redraw:
                draw_timeline()
            elif selection_changed:
                draw_timeline()
            else:
                update_playhead_visual()
            if center:
                win.after_idle(lambda sec=playhead["time"]: center_on_time(sec))

        def keep_playhead_visible_for_playback():
            # DaVinci / Edius 風格的 follow 行為：
            #   - playhead 跑到可視範圍右側 80% 時，把它推回左側 20%，
            #     一次捲一大段、避免持續微捲造成抖動。
            #   - 如果手動捲動讓 playhead 跑到畫面左側外面，也拉回左側 20%。
            #   - 其他情況不動畫面，由使用者自己控制視窗。
            px_per_second = max(1.0, float(zoom_var.get()))
            total_width = timeline_width()
            visible = max(1, timeline_canvas.winfo_width() or 1)
            if total_width <= visible:
                return
            left = timeline_canvas.canvasx(0)
            x = 24 + playhead["time"] * px_per_second
            if x > left + visible * 0.8 or x < left:
                center_on_time(playhead["time"], ratio=0.2)

        def cancel_scrub_preview():
            after_id = scrub_preview.get("after_id")
            if after_id is not None:
                try:
                    win.after_cancel(after_id)
                except Exception:
                    pass
            scrub_preview["after_id"] = None

        def schedule_scrub_preview(delay_ms: int = 35):
            if playback["playing"]:
                return
            if scrub_preview.get("after_id") is not None:
                return

            def play_preview():
                scrub_preview["after_id"] = None
                if playback_source and Path(playback_source).exists():
                    self.play_srt_segment(playback_source, playhead["time"], min(timeline_duration, playhead["time"] + 0.18))

            scrub_preview["after_id"] = win.after(max(70, delay_ms), play_preview)

        def caption_index_at_time(seconds: float) -> int | None:
            for idx, row in enumerate(rows):
                try:
                    start, end = parse_srt_time(row["start"].get()), parse_srt_time(row["end"].get())
                except Exception:
                    continue
                if start <= seconds < end:
                    return idx
            return None

        def sync_selection_to_playhead() -> bool:
            idx = caption_index_at_time(playhead["time"])
            if idx is None:
                return False
            if idx == selected_index["value"] and selected_indices == {idx}:
                return False
            selected_index["value"] = idx
            selected_indices.clear()
            selected_indices.add(idx)
            status_var.set(f"已預選第 {idx + 1} 組字幕")
            return True

        def select_row(row_index: int, *, play: bool = False, center: bool = True, update_playhead: bool = True, focus_text: bool = True):
            if not rows:
                return
            selected_index["value"] = max(0, min(len(rows) - 1, row_index))
            selected_indices.clear()
            selected_indices.add(selected_index["value"])
            if update_playhead:
                try:
                    start, _end = row_times(selected_index["value"])
                    set_playhead(start, center=center, redraw=False)
                except Exception:
                    pass
            if focus_text:
                try:
                    rows[selected_index["value"]]["text"].focus_set()
                except Exception:
                    pass
            status_var.set(f"已選取第 {selected_index['value'] + 1} 組字幕")
            draw_timeline()
            if center:
                try:
                    start, _end = row_times(selected_index["value"])
                    win.after_idle(lambda sec=start: center_on_time(sec))
                except Exception:
                    pass
            if play or click_play_enabled.get():
                play_row(selected_index["value"])

        def scroll_text_row_to_view(row_index: int):
            try:
                body.update_idletasks()
                canvas = getattr(body, "_parent_canvas", None)
                if canvas is None:
                    return
                y = max(0, rows[row_index]["text"].winfo_y() - 8)
                total = max(1, body.winfo_height())
                canvas.yview_moveto(max(0.0, min(1.0, y / total)))
            except Exception:
                pass

        def format_short_time(seconds: float) -> str:
            total = max(0, int(seconds))
            h, r = divmod(total, 3600)
            m, s = divmod(r, 60)
            return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

        def tick_interval(px_per_second: float) -> int:
            if px_per_second >= 140:
                return 1
            if px_per_second >= 80:
                return 2
            if px_per_second >= 45:
                return 5
            if px_per_second >= 24:
                return 10
            return 30

        def timeline_to_seconds(x: float) -> float:
            px_per_second = max(1.0, float(zoom_var.get()))
            return max(0.0, min(timeline_duration, (x - 24) / px_per_second))

        def row_times(row_index: int) -> tuple[float, float]:
            row = rows[row_index]
            return parse_srt_time(row["start"].get()), parse_srt_time(row["end"].get())

        def current_chunks_relaxed() -> list[dict]:
            current = []
            for row in rows:
                try:
                    start = parse_srt_time(row["start"].get())
                    end = parse_srt_time(row["end"].get())
                except Exception:
                    start, end = 0.0, 0.0
                current.append({"timestamp": (start, end), "text": row["text"].get("1.0", "end").strip()})
            return current

        def row_has_time_error(row_index: int) -> bool:
            if not (0 <= row_index < len(rows)):
                return False
            try:
                start = parse_srt_time(rows[row_index]["start"].get())
                end = parse_srt_time(rows[row_index]["end"].get())
                if end <= start:
                    return True
                if row_index > 0:
                    prev_end = parse_srt_time(rows[row_index - 1]["end"].get())
                    if start < prev_end:
                        return True
            except Exception:
                return True
            return False

        def row_visual_state(row_index: int) -> str:
            if row_has_time_error(row_index):
                return "time_error"
            if row_index in ai_review_indices:
                return "ai_review"
            return "normal"

        def apply_row_styles():
            try:
                focused = win.focus_get()
            except Exception:
                focused = None
            for idx, row in enumerate(rows):
                state = row_visual_state(idx)
                num_btn, start_entry, end_entry, text_box = row["widgets"]
                # 正在編輯（有焦點）的文字框：組字期間不要 reconfigure，否則注音會被打斷、亂飛
                skip_text = focused is text_box
                if state == "time_error":
                    num_btn.configure(bg=TIME_ERROR, activebackground=TIME_ERROR)
                    start_entry.configure(bg=TIME_ERROR_BG, highlightbackground=TIME_ERROR, highlightcolor=TIME_ERROR)
                    end_entry.configure(bg=TIME_ERROR_BG, highlightbackground=TIME_ERROR, highlightcolor=TIME_ERROR)
                    if not skip_text:
                        text_box.configure(bg=TIME_ERROR_BG, highlightbackground=TIME_ERROR, highlightcolor=TIME_ERROR)
                elif state == "ai_review":
                    num_btn.configure(bg=AI_REVIEW, activebackground=AI_REVIEW_BORDER)
                    start_entry.configure(bg=DARK_2, highlightbackground=LINE, highlightcolor=ORANGE)
                    end_entry.configure(bg=DARK_2, highlightbackground=LINE, highlightcolor=ORANGE)
                    if not skip_text:
                        text_box.configure(bg=AI_REVIEW_BG, highlightbackground=AI_REVIEW_BORDER, highlightcolor=AI_REVIEW_BORDER)
                else:
                    num_btn.configure(bg="#222020", activebackground=GARNET)
                    start_entry.configure(bg=DARK_2, highlightbackground=LINE, highlightcolor=ORANGE)
                    end_entry.configure(bg=DARK_2, highlightbackground=LINE, highlightcolor=ORANGE)
                    if not skip_text:
                        text_box.configure(bg=DARK_2, highlightbackground=LINE, highlightcolor=ORANGE)
        def limit_history_stack(stack: list[list[dict]]) -> None:
            if len(stack) > 80:
                del stack[0 : len(stack) - 80]

        def push_undo(clear_redo: bool = True):
            snapshot = clone_chunks(current_chunks_relaxed())
            if not undo_stack or not chunks_equal(undo_stack[-1], snapshot):
                undo_stack.append(snapshot)
                limit_history_stack(undo_stack)
            if clear_redo:
                redo_stack.clear()

        def apply_chunks_to_rows(chunks: list[dict]):
            while len(rows) > len(chunks):
                destroy_row(rows.pop())
            while len(rows) < len(chunks):
                rows.append(create_caption_row({"timestamp": (0.0, 0.0), "text": ""}))
            for row, chunk in zip(rows, chunks):
                ts = chunk.get("timestamp") or (0.0, 0.0)
                row["start"].set(CORE.seconds_to_srt_time(ts[0] if ts[0] is not None else 0.0))
                row["end"].set(CORE.seconds_to_srt_time(ts[1] if ts[1] is not None else 0.0))
                row["text"].delete("1.0", "end")
                row["text"].insert("1.0", (chunk.get("text") or "").strip())
            reflow_rows()
            draw_timeline()

        def undo_last(_event=None):
            if isinstance(getattr(_event, "widget", None), (tk.Text, tk.Entry)):
                return None
            if not undo_stack:
                status_var.set("沒有可復原的動作")
                return "break"
            redo_stack.append(clone_chunks(current_chunks_relaxed()))
            limit_history_stack(redo_stack)
            apply_chunks_to_rows(undo_stack.pop())
            status_var.set("已復原上一個動作")
            return "break"

        def redo_last(_event=None):
            if isinstance(getattr(_event, "widget", None), (tk.Text, tk.Entry)):
                return None
            if not redo_stack:
                status_var.set("沒有可重做的動作")
                return "break"
            undo_stack.append(clone_chunks(current_chunks_relaxed()))
            limit_history_stack(undo_stack)
            apply_chunks_to_rows(redo_stack.pop())
            status_var.set("已重做上一個動作")
            return "break"

        def snap_time(value: float, candidates: list[float], threshold: float = 0.12) -> float:
            best = value
            best_dist = threshold
            for candidate in candidates:
                dist = abs(value - candidate)
                if dist <= best_dist:
                    best = candidate
                    best_dist = dist
            return best

        def schedule_timeline_draw(*_):
            if timeline_redraw_job["id"] is not None:
                return
            timeline_redraw_job["id"] = win.after_idle(run_scheduled_timeline_draw)

        def run_scheduled_timeline_draw():
            timeline_redraw_job["id"] = None
            apply_row_styles()
            draw_timeline()

        def schedule_text_redraw(*_):
            # 打字（含注音組字）時：用較長防抖，且只重畫便宜的動態層，不 restyle 正在編輯的文字框
            if timeline_redraw_job.get("text_id") is not None:
                try:
                    win.after_cancel(timeline_redraw_job["text_id"])
                except Exception:
                    pass
            timeline_redraw_job["text_id"] = win.after(300, run_text_redraw)

        def run_text_redraw():
            timeline_redraw_job["text_id"] = None
            draw_timeline()

        def schedule_resize_redraw(_event=None):
            # 拖動/縮放視窗時 <Configure> 會連續狂發：用防抖，停下來才重畫
            if timeline_redraw_job.get("resize_id") is not None:
                try:
                    win.after_cancel(timeline_redraw_job["resize_id"])
                except Exception:
                    pass
            timeline_redraw_job["resize_id"] = win.after(120, run_resize_redraw)

        def run_resize_redraw():
            timeline_redraw_job["resize_id"] = None
            draw_timeline()

        def draw_static_layer(px_per_second, total_width):
            # 背景、刻度尺、聲波：最貴的部分（聲波最多 6000 條線），只在縮放/寬度改變時重建
            timeline_canvas.delete("static")
            timeline_canvas.create_rectangle(0, 0, total_width, 420, fill="#202428", outline="", tags=("static",))

            major = tick_interval(px_per_second)
            minor = max(0.5, major / 4)
            minor_count = int(math.ceil(timeline_duration / minor))
            for i in range(minor_count + 1):
                sec = i * minor
                x = 24 + sec * px_per_second
                if x > total_width - 12:
                    break
                is_major = abs(sec / major - round(sec / major)) < 0.001
                tick_h = 15 if is_major else 7
                color = "#AEB5BE" if is_major else "#69717A"
                timeline_canvas.create_line(x, 30, x, 30 + tick_h, fill=color, width=1, tags=("static",))
                if is_major:
                    timeline_canvas.create_text(
                        x,
                        17,
                        text=format_short_time(sec),
                        fill="#D4D8DD",
                        font=(EN_FONT, 10, "bold"),
                        tags=("static",),
                    )
                    timeline_canvas.create_line(x, 56, x, 200, fill="#2D353C", width=1, tags=("static",))

            mid_y = 140
            timeline_canvas.create_line(24, mid_y, total_width - 24, mid_y, fill="#38424B", width=1, tags=("static",))
            if waveform_peaks:
                peak_count = len(waveform_peaks)
                # 整段波形只用「一個」canvas item（填色包絡多邊形）：物件數約 6000 → 1，
                # 大幅降低畫布重繪成本，拖動視窗才會順。以像素欄位取最大振幅避免點數爆炸。
                col_amp: dict[int, float] = {}
                for i, peak in enumerate(waveform_peaks):
                    sec = (i / max(1, peak_count - 1)) * max(0.001, waveform_duration)
                    if sec > timeline_duration:
                        break
                    xi = int(24 + sec * px_per_second)
                    a = max(1.0, peak * 80)
                    if xi not in col_amp or a > col_amp[xi]:
                        col_amp[xi] = a
                xs = sorted(col_amp)
                if len(xs) >= 2:
                    pts = []
                    for xi in xs:
                        pts.extend((xi, mid_y - col_amp[xi]))
                    for xi in reversed(xs):
                        pts.extend((xi, mid_y + col_amp[xi]))
                    timeline_canvas.create_polygon(*pts, fill="#2F79E6", outline="", tags=("static",))
            else:
                timeline_canvas.create_text(
                    34,
                    mid_y,
                    text="尚無聲波預覽；請確認 FFmpeg 可用，或先完成一次轉寫後再開啟。",
                    anchor="w",
                    fill="#9EA7AF",
                    font=(FONT, 12),
                    tags=("static",),
                )
            timeline_canvas.tag_lower("static")

        def draw_timeline(_event=None):
            if not rows:
                return
            px_per_second = max(1.0, float(zoom_var.get()))
            total_width = timeline_width()
            # 只有縮放或畫布寬度改變時才重建靜態層（聲波/刻度），其餘沿用快取 → 打字/拖動/移動 playhead 都很便宜
            if static_cache["zoom"] != px_per_second or static_cache["width"] != total_width:
                timeline_canvas.configure(scrollregion=(0, 0, total_width, 420))
                draw_static_layer(px_per_second, total_width)
                static_cache["zoom"] = px_per_second
                static_cache["width"] = total_width

            timeline_canvas.delete("dynamic")
            block_y1, block_y2 = 240, 390
            for idx, row in enumerate(rows):
                try:
                    start, end = row_times(idx)
                except Exception:
                    continue
                x1 = 24 + start * px_per_second
                x2 = max(x1 + 8, 24 + end * px_per_second)
                selected = idx in selected_indices
                state = row_visual_state(idx)
                if state == "time_error":
                    fill = TIME_ERROR if selected else TIME_ERROR_BG
                    outline = "#FECACA" if selected else TIME_ERROR
                elif state == "ai_review":
                    fill = AI_REVIEW if selected else AI_REVIEW_BG
                    outline = "#FED7AA" if selected else AI_REVIEW_BORDER
                else:
                    fill = "#423A67" if not selected else "#52447F"
                    outline = "#F2EEFF" if selected else "#514873"
                timeline_canvas.create_rectangle(
                    x1,
                    block_y1,
                    x2,
                    block_y2,
                    fill=fill,
                    outline=outline,
                    width=2 if selected else 1,
                    tags=(f"block_{idx}", "caption_block", "dynamic"),
                )
                label = (row["text"].get("1.0", "end").strip().replace("\n", " ") or "（空白）")
                available_width = max(0, x2 - x1 - 18)
                max_chars = max(0, int(available_width / 9))
                if max_chars > 2:
                    if len(label) > max_chars:
                        label = label[: max_chars - 1] + "…"
                    timeline_canvas.create_text(
                        x1 + 10,
                        (block_y1 + block_y2) / 2,
                        text=label,
                        fill="#FFFFFF",
                        font=(FONT, 12, "bold"),
                        anchor="w",
                        width=available_width,
                        tags=(f"block_{idx}", "caption_block", "dynamic"),
                    )
            playhead_x = 24 + playhead["time"] * px_per_second
            playhead_items["line"] = timeline_canvas.create_line(playhead_x, 48, playhead_x, 410, fill="#F87366", width=2, tags=("playhead", "dynamic"))
            playhead_items["head"] = timeline_canvas.create_polygon(
                playhead_x - 7,
                48,
                playhead_x + 7,
                48,
                playhead_x + 7,
                59,
                playhead_x,
                66,
                playhead_x - 7,
                59,
                fill="#F87366",
                outline="",
                tags=("playhead", "dynamic"),
            )

        def update_playhead_visual():
            px_per_second = max(1.0, float(zoom_var.get()))
            playhead_x = 24 + playhead["time"] * px_per_second
            if playhead_items.get("line"):
                timeline_canvas.coords(playhead_items["line"], playhead_x, 48, playhead_x, 410)
            if playhead_items.get("head"):
                timeline_canvas.coords(
                    playhead_items["head"],
                    playhead_x - 7,
                    48,
                    playhead_x + 7,
                    48,
                    playhead_x + 7,
                    59,
                    playhead_x,
                    66,
                    playhead_x - 7,
                    59,
                )

        def parse_timeline_tag(tags: tuple[str, ...]) -> tuple[str, int] | None:
            for tag in tags:
                if tag.startswith("start_"):
                    return "start", int(tag.split("_", 1)[1])
                if tag.startswith("end_"):
                    return "end", int(tag.split("_", 1)[1])
                if tag.startswith("block_"):
                    return "block", int(tag.split("_", 1)[1])
            return None

        def close_inline_editor(commit: bool = True):
            editor = inline_editor.get("text")
            idx = inline_editor.get("index")
            if editor is not None and idx is not None and commit:
                push_undo()
                rows[idx]["text"].delete("1.0", "end")
                rows[idx]["text"].insert("1.0", editor.get("1.0", "end").strip())
            if inline_editor.get("window") is not None:
                try:
                    timeline_canvas.delete(inline_editor["window"])
                except Exception:
                    pass
            inline_editor.update({"window": None, "text": None, "index": None})
            draw_timeline()

        def open_inline_editor(row_index: int):
            close_inline_editor(commit=True)
            select_row(row_index, center=False, update_playhead=False, focus_text=False)
            try:
                start, end = row_times(row_index)
            except Exception:
                return
            px_per_second = max(1.0, float(zoom_var.get()))
            x1 = 24 + start * px_per_second
            x2 = max(x1 + 120, 24 + end * px_per_second)
            editor = tk.Text(
                timeline_canvas,
                height=3,
                wrap="word",
                bg="#2C254B",
                fg="#FFFFFF",
                insertbackground="#FFFFFF",
                relief="flat",
                borderwidth=0,
                padx=8,
                pady=6,
                font=(FONT, 12, "bold"),
                undo=True,
            )
            mark_cjk_text_widget(editor)
            editor.insert("1.0", rows[row_index]["text"].get("1.0", "end").strip())
            window_id = timeline_canvas.create_window(
                x1 + 10,
                250,
                anchor="nw",
                width=max(160, min(520, x2 - x1 - 20)),
                height=110,
                window=editor,
            )
            inline_editor.update({"window": window_id, "text": editor, "index": row_index})
            editor.focus_set()
            editor.bind("<FocusOut>", lambda _event: close_inline_editor(commit=True), add="+")
            editor.bind("<Control-Return>", lambda _event: close_inline_editor(commit=True) or "break")
            editor.bind("<Escape>", lambda _event: close_inline_editor(commit=False) or "break")

        def update_play_button():
            try:
                play_btn.configure(text="⏸" if playback["playing"] else "▶")
            except Exception:
                pass

        def cancel_playback_timer():
            after_id = playback.get("after_id")
            if after_id is not None:
                try:
                    win.after_cancel(after_id)
                except Exception:
                    pass
            playback["after_id"] = None

        def pause_playback():
            if playback["playing"] and playback["started_at"] is not None:
                elapsed = (_dt.datetime.now() - playback["started_at"]).total_seconds()
                set_playhead(float(playback["started_from"]) + elapsed, center=False, redraw=False)
            playback["playing"] = False
            playback["started_at"] = None
            cancel_playback_timer()
            self.stop_preview()
            update_play_button()

        def update_playhead_during_playback():
            if not playback["playing"]:
                return
            proc = self.preview_process
            if proc is not None and proc.poll() is not None:
                playback["playing"] = False
                playback["started_at"] = None
                cancel_playback_timer()
                update_play_button()
                return
            elapsed = (_dt.datetime.now() - playback["started_at"]).total_seconds() if playback["started_at"] else 0.0
            current = min(timeline_duration, float(playback["started_from"]) + elapsed)
            set_playhead(current, center=False, redraw=False)
            keep_playhead_visible_for_playback()
            if current >= timeline_duration:
                pause_playback()
                return
            playback["after_id"] = win.after(16, update_playhead_during_playback)

        def start_playback():
            if not playback_source or not Path(playback_source).exists():
                messagebox.showinfo("找不到原始檔", "需要原始音訊或影片檔，才能從時間軸播放。")
                return
            player = find_ffplay()
            if not player:
                messagebox.showinfo("找不到播放器", "找不到 ffplay.exe，請先確認 FFmpeg 工具完整安裝。")
                return
            self.stop_preview()
            start = max(0.0, min(timeline_duration, playhead["time"]))
            # 跟剪輯軟體一致：playhead 在可視範圍內就不動畫面，
            # 只有在範圍外才把它拉回左側 20%（保留前方視野給之後的播放）。
            px_per_second = max(1.0, float(zoom_var.get()))
            visible = max(1, timeline_canvas.winfo_width() or 1)
            left = timeline_canvas.canvasx(0)
            x = 24 + start * px_per_second
            if x < left or x > left + visible - 90:
                center_on_time(start, ratio=0.2)
            cmd = [
                player,
                "-hide_banner",
                "-loglevel",
                "error",
                "-autoexit",
                "-nodisp",
                "-ss",
                f"{start:.3f}",
                playback_source,
            ]
            try:
                self.preview_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception as exc:
                messagebox.showerror("播放失敗", str(exc))
                return
            playback["playing"] = True
            playback["started_at"] = _dt.datetime.now()
            playback["started_from"] = start
            update_play_button()
            cancel_playback_timer()
            playback["after_id"] = win.after(16, update_playhead_during_playback)

        def toggle_playback():
            if playback["playing"]:
                pause_playback()
            else:
                start_playback()

        def goto_caption(row_index: int):
            if not rows:
                return
            row_index = max(0, min(len(rows) - 1, row_index))
            select_row(row_index, center=True, update_playhead=True)

        def goto_previous_caption():
            goto_caption(selected_row_index() - 1)

        def goto_next_caption():
            goto_caption(selected_row_index() + 1)

        def zoom_timeline(factor: float):
            old = max(1.0, float(zoom_var.get()))
            new = max(24.0, min(180.0, old * factor))
            if abs(new - old) < 0.001:
                return
            anchor_time = float(playhead["time"])
            zoom_var.set(new)
            draw_timeline()
            win.after_idle(lambda t=anchor_time: center_on_time(t))
            win.after(60, lambda t=anchor_time: center_on_time(t))

        def on_timeline_mousewheel(event):
            ctrl_down = bool(event.state & 0x0004)
            direction = 1 if event.delta > 0 else -1
            if ctrl_down:
                zoom_timeline(1.12 if direction > 0 else 1 / 1.12)
            else:
                step = 0.20 if float(zoom_var.get()) >= 90 else 0.50
                set_playhead(playhead["time"] - direction * step, center=False, redraw=False)
                if playback["playing"]:
                    pause_playback()
            return "break"

        def on_middle_press(event):
            pan_state["active"] = True
            pan_state["x"] = event.x
            try:
                pan_state["view"] = timeline_canvas.xview()[0]
            except Exception:
                pan_state["view"] = 0.0
            timeline_canvas.configure(cursor="fleur")
            return "break"

        def on_middle_drag(event):
            if not pan_state.get("active"):
                return "break"
            total_width = timeline_width()
            visible = max(1, timeline_canvas.winfo_width() or 1)
            if total_width <= visible:
                return "break"
            dx = event.x - int(pan_state.get("x", 0))
            denom = max(1, total_width - visible)
            fraction = float(pan_state.get("view", 0.0)) - dx / denom
            timeline_canvas.xview_moveto(max(0.0, min(1.0, fraction)))
            return "break"

        def on_middle_release(_event):
            pan_state["active"] = False
            timeline_canvas.configure(cursor="")
            return "break"

        def on_editor_space(event):
            if isinstance(event.widget, (tk.Text, tk.Entry)):
                return None
            toggle_playback()
            return "break"

        def clear_text_focus(event):
            if isinstance(event.widget, (tk.Text, tk.Entry)):
                return None
            text_edit_started["index"] = None
            force_editor_english(event.widget)
            try:
                timeline_canvas.focus_set()
            except Exception:
                pass
            return None

        def begin_text_edit(row_index: int):
            if text_edit_started["index"] != row_index:
                push_undo()
                text_edit_started["index"] = row_index

        def set_selected_in_to_playhead(_event=None):
            if isinstance(getattr(_event, "widget", None), (tk.Text, tk.Entry)):
                return None
            idx = selected_row_index()
            try:
                _start, end = row_times(idx)
            except Exception:
                return "break"
            new_start = min(playhead["time"], end - 0.10)
            if idx > 0:
                new_start = max(row_times(idx - 1)[1], new_start)
            push_undo()
            rows[idx]["start"].set(CORE.seconds_to_srt_time(new_start))
            status_var.set(f"第 {idx + 1} 組 IN 已設為 playhead")
            draw_timeline()
            return "break"

        def set_selected_out_to_playhead(_event=None):
            if isinstance(getattr(_event, "widget", None), (tk.Text, tk.Entry)):
                return None
            idx = selected_row_index()
            try:
                start, _end = row_times(idx)
            except Exception:
                return "break"
            new_end = max(playhead["time"], start + 0.10)
            if idx + 1 < len(rows):
                new_end = min(row_times(idx + 1)[0], new_end)
            push_undo()
            rows[idx]["end"].set(CORE.seconds_to_srt_time(new_end))
            status_var.set(f"第 {idx + 1} 組 OUT 已設為 playhead")
            draw_timeline()
            return "break"

        def set_in_and_previous_out_to_playhead(_event=None):
            if isinstance(getattr(_event, "widget", None), (tk.Text, tk.Entry)):
                return None
            idx = selected_row_index()
            try:
                _start, end = row_times(idx)
            except Exception:
                return "break"
            new_start = min(playhead["time"], end - 0.10)
            if idx > 0:
                prev_start, _prev_end = row_times(idx - 1)
                new_start = max(prev_start + 0.10, new_start)
            push_undo()
            rows[idx]["start"].set(CORE.seconds_to_srt_time(new_start))
            if idx > 0:
                rows[idx - 1]["end"].set(CORE.seconds_to_srt_time(new_start))
            status_var.set(f"第 {idx + 1} 組 IN 已貼到 playhead，前一組 OUT 已貼齊")
            draw_timeline()
            return "break"

        def set_out_and_next_in_to_playhead(_event=None):
            if isinstance(getattr(_event, "widget", None), (tk.Text, tk.Entry)):
                return None
            idx = selected_row_index()
            try:
                start, _end = row_times(idx)
            except Exception:
                return "break"
            new_end = max(playhead["time"], start + 0.10)
            if idx + 1 < len(rows):
                _next_start, next_end = row_times(idx + 1)
                new_end = min(next_end - 0.10, new_end)
            push_undo()
            rows[idx]["end"].set(CORE.seconds_to_srt_time(new_end))
            if idx + 1 < len(rows):
                rows[idx + 1]["start"].set(CORE.seconds_to_srt_time(new_end))
            status_var.set(f"第 {idx + 1} 組 OUT 已貼到 playhead，下一組 IN 已貼齊")
            draw_timeline()
            return "break"

        def jump_playhead_to_selected_in(_event=None):
            idx = selected_row_index()
            try:
                start, _end = row_times(idx)
            except Exception:
                return "break"
            set_playhead(start, center=True, redraw=False)
            status_var.set(f"playhead 已到第 {idx + 1} 組 IN")
            return "break"

        def jump_playhead_to_selected_out(_event=None):
            idx = selected_row_index()
            try:
                _start, end = row_times(idx)
            except Exception:
                return "break"
            set_playhead(end, center=True, redraw=False)
            status_var.set(f"playhead 已到第 {idx + 1} 組 OUT")
            return "break"

        def on_timeline_press(event):
            timeline_canvas.focus_set()
            force_editor_english(timeline_canvas)
            if inline_editor.get("text") is not None and event.widget is timeline_canvas:
                close_inline_editor(commit=True)
            found = timeline_canvas.find_withtag("current")
            if not found:
                if playback["playing"]:
                    pause_playback()
                if event.y >= 205:
                    x = timeline_canvas.canvasx(event.x)
                    selection_drag.update({"active": True, "x0": x, "x1": x})
                    drag_state.update({"index": None, "mode": "select_range", "offset": 0.0, "duration": 0.0, "moved": False})
                else:
                    set_playhead(timeline_to_seconds(timeline_canvas.canvasx(event.x)), center=False)
                    drag_state.update({"index": None, "mode": "playhead", "offset": 0.0, "duration": 0.0, "moved": False})
                return
            parsed = parse_timeline_tag(timeline_canvas.gettags(found[0]))
            if not parsed:
                if playback["playing"]:
                    pause_playback()
                if event.y >= 205:
                    x = timeline_canvas.canvasx(event.x)
                    selection_drag.update({"active": True, "x0": x, "x1": x})
                    drag_state.update({"index": None, "mode": "select_range", "offset": 0.0, "duration": 0.0, "moved": False})
                else:
                    set_playhead(timeline_to_seconds(timeline_canvas.canvasx(event.x)), center=False)
                    drag_state.update({"index": None, "mode": "playhead", "offset": 0.0, "duration": 0.0, "moved": False})
                return
            mode, idx = parsed
            start, end = row_times(idx)
            if mode == "block":
                px_per_second = max(1.0, float(zoom_var.get()))
                canvas_x = timeline_canvas.canvasx(event.x)
                x1 = 24 + start * px_per_second
                x2 = 24 + end * px_per_second
                if abs(canvas_x - x1) <= 10:
                    mode = "start"
                elif abs(canvas_x - x2) <= 10:
                    mode = "end"
            select_row(idx, center=False, update_playhead=False, focus_text=False)
            scroll_text_row_to_view(idx)
            push_undo()
            sec = timeline_to_seconds(timeline_canvas.canvasx(event.x))
            drag_state.update(
                {
                    "index": idx,
                    "mode": mode,
                    "offset": sec - start,
                    "duration": end - start,
                    "moved": False,
                }
            )

        def on_timeline_drag(event):
            idx = drag_state.get("index")
            mode = drag_state.get("mode")
            if idx is None or not mode:
                if mode == "playhead":
                    if playback["playing"]:
                        pause_playback()
                    set_playhead(timeline_to_seconds(timeline_canvas.canvasx(event.x)), center=False, redraw=False)
                    schedule_scrub_preview()
                    drag_state["moved"] = True
                elif mode == "select_range":
                    selection_drag["x1"] = timeline_canvas.canvasx(event.x)
                    x0, x1 = sorted((selection_drag["x0"], selection_drag["x1"]))
                    selected_indices.clear()
                    px_per_second = max(1.0, float(zoom_var.get()))
                    for i, row in enumerate(rows):
                        try:
                            start, end = row_times(i)
                        except Exception:
                            continue
                        bx1 = 24 + start * px_per_second
                        bx2 = 24 + end * px_per_second
                        if bx2 >= x0 and bx1 <= x1:
                            selected_indices.add(i)
                    if selected_indices:
                        selected_index["value"] = min(selected_indices)
                    draw_timeline()
                    if selection_drag.get("rect"):
                        try:
                            timeline_canvas.delete(selection_drag["rect"])
                        except Exception:
                            pass
                    selection_drag["rect"] = timeline_canvas.create_rectangle(
                        x0, 212, x1, 328, outline="#FFFFFF", dash=(4, 3), width=1
                    )
                    drag_state["moved"] = True
                return
            sec = timeline_to_seconds(timeline_canvas.canvasx(event.x))
            try:
                start, end = row_times(idx)
            except Exception:
                return
            min_len = 0.10
            prev_end = row_times(idx - 1)[1] if idx > 0 else 0.0
            next_start = row_times(idx + 1)[0] if idx + 1 < len(rows) else timeline_duration
            snap_candidates = [playhead["time"]]
            if idx > 0:
                snap_candidates.append(prev_end)
            if idx + 1 < len(rows):
                snap_candidates.append(next_start)
            if mode == "start":
                start = max(prev_end, min(snap_time(sec, snap_candidates), end - min_len))
            elif mode == "end":
                end = min(next_start, max(snap_time(sec, snap_candidates), start + min_len))
            elif mode == "block":
                length = max(min_len, float(drag_state.get("duration") or (end - start)))
                new_start = sec - float(drag_state.get("offset") or 0.0)
                snapped_start = snap_time(new_start, [c for c in snap_candidates if c <= next_start - length])
                snapped_end_start = snap_time(new_start + length, [c for c in snap_candidates if c >= prev_end]) - length
                if abs(snapped_start - new_start) <= abs(snapped_end_start - new_start):
                    new_start = snapped_start
                else:
                    new_start = snapped_end_start
                new_start = max(prev_end, min(new_start, next_start - length))
                start, end = new_start, new_start + length
            rows[idx]["start"].set(CORE.seconds_to_srt_time(start))
            rows[idx]["end"].set(CORE.seconds_to_srt_time(end))
            drag_state["moved"] = True
            status_var.set(f"第 {idx + 1} 組：{CORE.seconds_to_srt_time(start)} → {CORE.seconds_to_srt_time(end)}")
            draw_timeline()

        def on_timeline_release(_event):
            idx = drag_state.get("index")
            moved = bool(drag_state.get("moved"))
            mode = drag_state.get("mode")
            if mode == "select_range":
                if selection_drag.get("rect"):
                    try:
                        timeline_canvas.delete(selection_drag["rect"])
                    except Exception:
                        pass
                selection_drag.update({"active": False, "rect": None})
                draw_timeline()
            drag_state.update({"index": None, "mode": "", "offset": 0.0, "duration": 0.0, "moved": False})
            if idx is not None and not moved and click_play_enabled.get():
                play_row(int(idx))

        def on_timeline_double_click(event):
            found = timeline_canvas.find_withtag("current")
            if not found:
                return
            parsed = parse_timeline_tag(timeline_canvas.gettags(found[0]))
            if parsed and parsed[0] == "block":
                open_inline_editor(parsed[1])
                return "break"

        def block_index_at_event(event):
            # 找出游標下的字幕方塊 index（先用 current tag，再用座標後備）
            for it in timeline_canvas.find_withtag("current"):
                parsed = parse_timeline_tag(timeline_canvas.gettags(it))
                if parsed and parsed[0] == "block":
                    return parsed[1]
            x = timeline_canvas.canvasx(event.x)
            px_per_second = max(1.0, float(zoom_var.get()))
            for i in range(len(rows)):
                try:
                    s0, e0 = row_times(i)
                except Exception:
                    continue
                bx1 = 24 + s0 * px_per_second
                bx2 = max(bx1 + 8, 24 + e0 * px_per_second)
                if bx1 <= x <= bx2 and 240 <= event.y <= 390:
                    return i
            return None

        def on_timeline_shift_press(event):
            # Shift+左鍵：從目前主選取到點擊處，範圍連續選取（供合併使用）
            timeline_canvas.focus_set()
            force_editor_english(timeline_canvas)
            drag_state.update({"index": None, "mode": "", "offset": 0.0, "duration": 0.0, "moved": False})
            idx = block_index_at_event(event)
            if idx is None:
                return "break"
            anchor = selected_index.get("value", idx)
            if not (0 <= anchor < len(rows)):
                anchor = idx
            lo, hi = sorted((anchor, idx))
            selected_indices.clear()
            for i in range(lo, hi + 1):
                selected_indices.add(i)
            scroll_text_row_to_view(idx)
            draw_timeline()
            status_var.set(f"已選取第 {lo + 1}～{hi + 1} 組（共 {hi - lo + 1} 組）")
            return "break"

        def on_timeline_ctrl_toggle(event):
            # Ctrl+右鍵（或 Ctrl+左鍵）：加選 / 取消選取單一字幕方塊
            timeline_canvas.focus_set()
            force_editor_english(timeline_canvas)
            drag_state.update({"index": None, "mode": "", "offset": 0.0, "duration": 0.0, "moved": False})
            idx = block_index_at_event(event)
            if idx is None:
                return "break"
            if idx in selected_indices:
                selected_indices.discard(idx)
                if selected_index.get("value") == idx and selected_indices:
                    selected_index["value"] = min(selected_indices)
            else:
                selected_indices.add(idx)
                selected_index["value"] = idx
                scroll_text_row_to_view(idx)
            draw_timeline()
            status_var.set(f"已選取 {len(selected_indices)} 組字幕")
            return "break"

        def row_index_for(row: dict) -> int:
            try:
                return rows.index(row)
            except ValueError:
                return 0

        def destroy_row(row: dict):
            for widget in row.get("widgets", []):
                try:
                    widget.destroy()
                except Exception:
                    pass

        def reflow_rows():
            for idx, row in enumerate(rows):
                num_btn, start_entry, end_entry, text_box = row["widgets"]
                num_btn.configure(text=str(idx + 1))
                num_btn.grid_configure(row=idx)
                start_entry.grid_configure(row=idx)
                end_entry.grid_configure(row=idx)
                text_box.grid_configure(row=idx)
            apply_row_styles()
            draw_timeline()

        def selected_sorted() -> list[int]:
            return sorted(i for i in selected_indices if 0 <= i < len(rows))

        def delete_selected_captions(_event=None):
            if isinstance(getattr(_event, "widget", None), (tk.Text, tk.Entry)):
                return None
            targets = selected_sorted()
            if not targets:
                return "break"
            push_undo()
            for idx in reversed(targets):
                destroy_row(rows.pop(idx))
            if rows:
                new_idx = min(targets[0], len(rows) - 1)
                selected_indices.clear()
                selected_indices.add(new_idx)
                selected_index["value"] = new_idx
            else:
                selected_indices.clear()
                selected_index["value"] = 0
            reflow_rows()
            status_var.set(f"已刪除 {len(targets)} 組字幕")
            return "break"

        def merge_selected_captions():
            targets = selected_sorted()
            if len(targets) < 2:
                status_var.set("請先選取兩個以上字幕塊")
                return
            push_undo()
            first, last = targets[0], targets[-1]
            start, _ = row_times(first)
            _, end = row_times(last)
            merged_text = "".join(rows[i]["text"].get("1.0", "end").strip() for i in targets if rows[i]["text"].get("1.0", "end").strip())
            rows[first]["start"].set(CORE.seconds_to_srt_time(start))
            rows[first]["end"].set(CORE.seconds_to_srt_time(end))
            rows[first]["text"].delete("1.0", "end")
            rows[first]["text"].insert("1.0", merged_text)
            for idx in reversed(targets[1:]):
                destroy_row(rows.pop(idx))
            selected_indices.clear()
            selected_indices.add(first)
            selected_index["value"] = first
            reflow_rows()
            status_var.set(f"已合併 {len(targets)} 組字幕")

        def show_find_replace(replace_mode: bool = False):
            dialog = ctk.CTkToplevel(win)
            dialog.title("尋找與取代" if replace_mode else "尋找")
            dialog.geometry("540x270" if replace_mode else "540x200")
            dialog.configure(fg_color=BLACK_KITE)
            self.apply_window_icon(dialog, "_LOGO.png")
            dialog.transient(win)
            dialog.grab_set()
            dialog.grid_columnconfigure(0, weight=1)

            box = ctk.CTkFrame(dialog, fg_color=CARD_DARK, corner_radius=14, border_width=1, border_color=LINE)
            box.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
            box.grid_columnconfigure(1, weight=1)
            find_var = ctk.StringVar(value="")
            repl_var = ctk.StringVar(value="")

            ctk.CTkLabel(box, text="尋找", text_color=TEXT_ON_DARK, font=(FONT, 14, "bold")).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))
            find_entry = ctk.CTkEntry(box, textvariable=find_var, height=38, fg_color=DARK_2, border_color=LINE, text_color=TEXT_ON_DARK, font=(FONT, 14))
            find_entry.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=(16, 8))
            mark_cjk_text_widget(find_entry)
            if replace_mode:
                ctk.CTkLabel(box, text="取代為", text_color=TEXT_ON_DARK, font=(FONT, 14, "bold")).grid(row=1, column=0, sticky="w", padx=16, pady=8)
                repl_entry = ctk.CTkEntry(box, textvariable=repl_var, height=38, fg_color=DARK_2, border_color=LINE, text_color=TEXT_ON_DARK, font=(FONT, 14))
                repl_entry.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=8)
                mark_cjk_text_widget(repl_entry)

            search_state = {"pos": -1}

            def find_next():
                needle = find_var.get()
                if not needle:
                    return
                count = len(rows)
                for step in range(1, count + 1):
                    idx = (search_state["pos"] + step) % count
                    hay = rows[idx]["text"].get("1.0", "end")
                    if needle in hay:
                        search_state["pos"] = idx
                        select_row(idx, center=True, update_playhead=True, focus_text=False)
                        scroll_text_row_to_view(idx)
                        status_var.set(f"找到第 {idx + 1} 組")
                        return
                status_var.set("找不到符合文字")

            def replace_current():
                idx = search_state["pos"]
                if idx < 0 or idx >= len(rows):
                    find_next()
                    idx = search_state["pos"]
                needle = find_var.get()
                if not needle or idx < 0:
                    return
                text = rows[idx]["text"].get("1.0", "end")
                if needle in text:
                    push_undo()
                    rows[idx]["text"].delete("1.0", "end")
                    rows[idx]["text"].insert("1.0", text.replace(needle, repl_var.get(), 1).strip())
                    draw_timeline()
                find_next()

            def replace_all():
                needle = find_var.get()
                if not needle:
                    return
                push_undo()
                n = 0
                for row in rows:
                    text = row["text"].get("1.0", "end")
                    if needle in text:
                        row["text"].delete("1.0", "end")
                        row["text"].insert("1.0", text.replace(needle, repl_var.get()).strip())
                        n += 1
                draw_timeline()
                status_var.set(f"已取代 {n} 組字幕")

            actions = ctk.CTkFrame(box, fg_color="transparent")
            actions.grid(row=3, column=0, columnspan=2, sticky="e", padx=16, pady=(14, 16))
            ctk.CTkButton(actions, text="下一個", width=92, height=36, corner_radius=13, fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK, font=(FONT, 13, "bold"), command=find_next).pack(side="left", padx=(0, 8))
            if replace_mode:
                ctk.CTkButton(actions, text="取代", width=84, height=36, corner_radius=13, fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK, font=(FONT, 13, "bold"), command=replace_current).pack(side="left", padx=(0, 8))
                ctk.CTkButton(actions, text="全部取代", width=110, height=36, corner_radius=13, fg_color=ORANGE, hover_color=ORANGE_DARK, text_color="#FFFFFF", font=(FONT, 13, "bold"), command=replace_all).pack(side="left", padx=(0, 8))
            ctk.CTkButton(actions, text="關閉", width=84, height=36, corner_radius=13, fg_color="#32333B", hover_color="#45464F", text_color=TEXT_ON_DARK, font=(FONT, 13, "bold"), command=dialog.destroy).pack(side="left")
            find_entry.focus_set()

        def create_caption_row(chunk: dict) -> dict:
            row: dict = {}
            ts = chunk.get("timestamp") or (0.0, 0.0)
            start_var = ctk.StringVar(value=CORE.seconds_to_srt_time(ts[0] if ts[0] is not None else 0.0))
            end_var = ctk.StringVar(value=CORE.seconds_to_srt_time(ts[1] if ts[1] is not None else (ts[0] or 0.0) + 2.0))
            # 用原生 tk 元件（非 CTk）：每列重量大幅下降，清單捲動與視窗拖動更順
            num_btn = tk.Button(
                body,
                text="",
                width=4,
                bd=0,
                relief="flat",
                bg="#222020",
                fg=TEXT_ON_DARK,
                activebackground=GARNET,
                activeforeground="#FFFFFF",
                font=(EN_FONT, 12, "bold"),
                cursor="hand2",
                takefocus=0,
                highlightthickness=0,
                command=lambda r=row: select_row(row_index_for(r)),
            )
            start_entry = tk.Entry(
                body,
                textvariable=start_var,
                width=13,
                bg=DARK_2,
                fg=TEXT_ON_DARK,
                disabledbackground=DARK_2,
                insertbackground=TEXT_ON_DARK,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=LINE,
                highlightcolor=ORANGE,
                font=(EN_FONT, 12),
            )
            end_entry = tk.Entry(
                body,
                textvariable=end_var,
                width=13,
                bg=DARK_2,
                fg=TEXT_ON_DARK,
                disabledbackground=DARK_2,
                insertbackground=TEXT_ON_DARK,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=LINE,
                highlightcolor=ORANGE,
                font=(EN_FONT, 12),
            )
            text_box = tk.Text(
                body,
                height=2,
                wrap="word",
                bg=DARK_2,
                fg=TEXT_ON_DARK,
                insertbackground=TEXT_ON_DARK,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground=LINE,
                highlightcolor=ORANGE,
                padx=8,
                pady=5,
                font=(FONT, 13),
            )
            mark_english_widget(start_entry)
            mark_english_widget(end_entry)
            mark_cjk_text_widget(text_box)
            text_box.insert("1.0", (chunk.get("text") or "").strip())
            row.update({"start": start_var, "end": end_var, "text": text_box, "widgets": [num_btn, start_entry, end_entry, text_box]})
            num_btn.grid(row=0, column=0, sticky="nw", padx=(0, 8), pady=(2, 6))
            start_entry.grid(row=0, column=1, sticky="nw", padx=(0, 8), pady=(4, 6))
            end_entry.grid(row=0, column=2, sticky="nw", padx=(0, 8), pady=(4, 6))
            text_box.grid(row=0, column=3, sticky="ew", pady=(2, 6))

            def on_caption_text_focus(_event, r=row):
                idx = row_index_for(r)
                begin_text_edit(idx)
                select_row(idx)

            text_box.bind("<FocusIn>", on_caption_text_focus, add="+")
            text_box.bind("<KeyRelease>", lambda _event: schedule_text_redraw())
            start_var.trace_add("write", schedule_timeline_draw)
            end_var.trace_add("write", schedule_timeline_draw)
            return row

        def split_caption_at_playhead(_event=None):
            if isinstance(getattr(_event, "widget", None), (tk.Text, tk.Entry)):
                return None
            idx = caption_index_at_time(playhead["time"])
            if idx is None:
                status_var.set("playhead 不在任何字幕段內，無法切開")
                return "break"
            start, end = row_times(idx)
            split_at = playhead["time"]
            if split_at <= start + 0.10 or split_at >= end - 0.10:
                status_var.set("切割點太靠近字幕邊界")
                return "break"
            push_undo()
            original_text = rows[idx]["text"].get("1.0", "end").strip()
            rows[idx]["end"].set(CORE.seconds_to_srt_time(split_at))
            new_row = create_caption_row({"timestamp": (split_at, end), "text": original_text})
            rows.insert(idx + 1, new_row)
            selected_index["value"] = idx + 1
            selected_indices.clear()
            selected_indices.add(idx + 1)
            reflow_rows()
            status_var.set(f"已在第 {idx + 1} 組切開字幕")
            return "break"

        def add_caption_at_playhead(_event=None):
            # 在目前 playhead 位置新增一則 1.5 秒空白字幕，並依開始時間插入正確位置
            push_undo()
            start = float(playhead["time"])
            end = start + 1.5
            insert_idx = len(rows)
            for i in range(len(rows)):
                try:
                    s0, _e0 = row_times(i)
                except Exception:
                    continue
                if s0 > start:
                    insert_idx = i
                    break
            new_row = create_caption_row({"timestamp": (start, end), "text": ""})
            rows.insert(insert_idx, new_row)
            selected_index["value"] = insert_idx
            selected_indices.clear()
            selected_indices.add(insert_idx)
            reflow_rows()
            scroll_text_row_to_view(insert_idx)
            status_var.set(f"已在 {format_short_time(start)} 新增 1.5 秒空白字幕（第 {insert_idx + 1} 組）")
            return "break"

        def import_srt_file():
            # 可一次多選 SRT 與聲音/影片檔；分開匯入時依副檔名自動判斷該放哪
            nonlocal waveform_peaks, waveform_duration, waveform_proxy_path, playback_source, timeline_duration
            paths = filedialog.askopenfilenames(
                title="匯入 SRT 字幕與／或聲音檔（可一次多選）",
                filetypes=[
                    ("字幕或聲音檔", ("*.srt", "*.wav", "*.mp3", "*.m4a", "*.aac", "*.flac", "*.mp4", "*.mov")),
                    ("SRT 字幕", "*.srt"),
                    ("聲音／影片檔", ("*.wav", "*.mp3", "*.m4a", "*.aac", "*.flac", "*.mp4", "*.mov")),
                    ("所有檔案", "*.*"),
                ],
            )
            if not paths:
                return
            audio_exts = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wma", ".mp4", ".mov", ".mkv"}
            srt_paths = [p for p in paths if str(p).lower().endswith(".srt")]
            audio_paths = [p for p in paths if Path(p).suffix.lower() in audio_exts]
            if not srt_paths and not audio_paths:
                messagebox.showinfo("未匯入", "請選擇 .srt 字幕，或 .wav/.mp3 等聲音檔。")
                return
            loaded = []
            # 1) 聲音／影片檔 → 重建波形與播放來源
            if audio_paths:
                audio_path = audio_paths[0]
                status_var.set(f"正在載入聲音波形：{Path(audio_path).name} …")
                try:
                    win.update_idletasks()
                except Exception:
                    pass
                peaks, dur, proxy = build_waveform_proxy(audio_path)
                if dur > 0:
                    waveform_peaks = peaks
                    waveform_duration = dur
                    waveform_proxy_path = proxy
                    playback_source = proxy or audio_path
                    loaded.append(f"聲音檔 {Path(audio_path).name}")
                else:
                    messagebox.showwarning("匯入聲音失敗", f"無法讀取聲音波形：\n{Path(audio_path).name}\n請確認 FFmpeg 可用。")
            # 2) SRT → 載入字幕
            if srt_paths:
                srt_path = srt_paths[0]
                chunks = []
                try:
                    chunks = parse_srt_text(Path(srt_path).read_text(encoding="utf-8-sig"))
                except Exception as exc:
                    messagebox.showerror("匯入失敗", f"無法讀取 SRT：\n{exc}")
                if chunks:
                    push_undo()
                    apply_chunks_to_rows(chunks)
                    loaded.append(f"{len(chunks)} 組字幕")
                else:
                    messagebox.showwarning("匯入失敗", "這個 SRT 檔沒有可解析的字幕。")
            # 3) 依新的波形/字幕重算時間軸長度並重畫
            try:
                sub_dur = max((row_times(i)[1] for i in range(len(rows))), default=0.0)
            except Exception:
                sub_dur = 0.0
            timeline_duration = max(1.0, waveform_duration, sub_dur)
            static_cache["zoom"] = None
            static_cache["width"] = None
            draw_timeline()
            if loaded:
                status_var.set("已匯入：" + "、".join(loaded))

        def switch_file(delta):
            if self.editor_index is None:
                return
            new_index = self.editor_index + delta
            if not (0 <= new_index < len(self.batch_results)):
                status_var.set("已經是第一個／最後一個檔案了")
                return
            try:
                save_current(show_message=False)
            except Exception:
                pass
            win.destroy()
            self.open_srt_editor(new_index)

        for chunk in original_chunks:
            rows.append(create_caption_row(chunk))
        reflow_rows()

        timeline_canvas.bind("<Configure>", schedule_resize_redraw)
        timeline_canvas.bind("<ButtonPress-1>", on_timeline_press)
        timeline_canvas.bind("<Shift-ButtonPress-1>", on_timeline_shift_press)
        timeline_canvas.bind("<Control-ButtonPress-1>", on_timeline_ctrl_toggle)
        timeline_canvas.bind("<Control-ButtonPress-3>", on_timeline_ctrl_toggle)
        timeline_canvas.bind("<Double-Button-1>", on_timeline_double_click)
        timeline_canvas.bind("<B1-Motion>", on_timeline_drag)
        timeline_canvas.bind("<ButtonRelease-1>", on_timeline_release)
        timeline_canvas.bind("<MouseWheel>", on_timeline_mousewheel)
        timeline_canvas.bind("<ButtonPress-2>", on_middle_press)
        timeline_canvas.bind("<B2-Motion>", on_middle_drag)
        timeline_canvas.bind("<ButtonRelease-2>", on_middle_release)
        win.bind("<FocusIn>", sync_editor_input_mode, add="+")
        win.bind("<Button-1>", clear_text_focus, add="+")
        timeline_canvas.bind("<KeyPress-space>", on_editor_space)
        timeline_canvas.bind("<Control-z>", undo_last)
        timeline_canvas.bind("<Control-Z>", undo_last)
        timeline_canvas.bind("<Control-Shift-z>", redo_last)
        timeline_canvas.bind("<Control-Shift-Z>", redo_last)
        timeline_canvas.bind("<Control-f>", lambda _event: show_find_replace(False) or "break")
        timeline_canvas.bind("<Control-F>", lambda _event: show_find_replace(False) or "break")
        timeline_canvas.bind("<Control-h>", lambda _event: show_find_replace(True) or "break")
        timeline_canvas.bind("<Control-H>", lambda _event: show_find_replace(True) or "break")
        timeline_canvas.bind("<Up>", jump_playhead_to_selected_in)
        timeline_canvas.bind("<Down>", jump_playhead_to_selected_out)
        timeline_canvas.bind("<Delete>", delete_selected_captions)
        timeline_canvas.bind("<KeyPress-i>", set_selected_in_to_playhead)
        timeline_canvas.bind("<KeyPress-I>", set_selected_in_to_playhead)
        timeline_canvas.bind("<KeyPress-o>", set_selected_out_to_playhead)
        timeline_canvas.bind("<KeyPress-O>", set_selected_out_to_playhead)
        timeline_canvas.bind("<KeyPress-u>", set_in_and_previous_out_to_playhead)
        timeline_canvas.bind("<KeyPress-U>", set_in_and_previous_out_to_playhead)
        timeline_canvas.bind("<KeyPress-p>", set_out_and_next_in_to_playhead)
        timeline_canvas.bind("<KeyPress-P>", set_out_and_next_in_to_playhead)
        timeline_canvas.bind("<KeyPress-c>", split_caption_at_playhead)
        timeline_canvas.bind("<KeyPress-C>", split_caption_at_playhead)
        win.bind("<Control-z>", undo_last, add="+")
        win.bind("<Control-Z>", undo_last, add="+")
        win.bind("<Control-Shift-z>", redo_last, add="+")
        win.bind("<Control-Shift-Z>", redo_last, add="+")
        def on_zoom_slider(_value):
            anchor_time = float(playhead["time"])
            draw_timeline()
            win.after_idle(lambda t=anchor_time: center_on_time(t))
            win.after(60, lambda t=anchor_time: center_on_time(t))

        zoom_slider.configure(command=on_zoom_slider)
        draw_timeline()
        win.after_idle(lambda: force_editor_english(timeline_canvas))

        def collect_chunks() -> list[dict]:
            updated = []
            previous_end = 0.0
            for idx, row in enumerate(rows, start=1):
                start = parse_srt_time(row["start"].get())
                end = parse_srt_time(row["end"].get())
                if end <= start:
                    raise ValueError(f"第 {idx} 組結束時間必須晚於開始時間。")
                if idx > 1 and start < previous_end:
                    raise ValueError(f"第 {idx} 組開始時間早於前一組結束時間。")
                text = row["text"].get("1.0", "end").strip()
                updated.append({"timestamp": (start, end), "text": text})
                previous_end = end
            return updated

        def check_timeline(show_ok: bool = True) -> list[dict] | None:
            try:
                updated = collect_chunks()
            except Exception as exc:
                status_var.set("時間軸需要修正")
                messagebox.showerror("時間軸檢查未通過", str(exc))
                return None
            status_var.set(f"時間軸正常，共 {len(updated)} 組字幕")
            if show_ok:
                messagebox.showinfo("時間軸正常", "所有字幕時間碼皆可輸出。")
            return updated

        def write_outputs(updated: list[dict], *, srt_path: str = "", txt_path: str = "", action: str = "save"):
            wrote = []
            if srt_path:
                Path(srt_path).write_text(chunks_to_editable_srt(updated), encoding="utf-8-sig")
                data["srt"] = srt_path
                wrote.append("SRT")
            if txt_path:
                Path(txt_path).write_text(chunks_to_editable_plain(updated) + "\n", encoding="utf-8-sig")
                data["txt"] = txt_path
                wrote.append("TXT")
            changed = self.record_srt_edits(original_chunks, updated, data, action)
            self.last_result = {
                "inp": data.get("inp", ""),
                "srt": data.get("srt", ""),
                "txt": data.get("txt", ""),
                "chunks": clone_chunks(updated),
            }
            saved_snapshot["chunks"] = clone_chunks(updated)
            status_var.set(f"已儲存 {' / '.join(wrote)}，修改 {changed} 行")
            self.result_label.configure(text=f"共 {len(updated)} 組字幕，可開啟字幕編輯器")
            self.srt_editor_btn.configure(state="normal")
            self.log(f"SRT 編輯器已儲存 {' / '.join(wrote)}。", "success")

        def save_current(show_message: bool = True) -> bool:
            updated = check_timeline(show_ok=False)
            if updated is None:
                return False
            srt_path = (data.get("srt") or "").strip()
            txt_path = (data.get("txt") or "").strip()
            if not srt_path and not txt_path:
                srt_path = filedialog.asksaveasfilename(
                    title="儲存 SRT",
                    defaultextension=".srt",
                    filetypes=[("SRT 字幕", "*.srt")],
                    initialfile=Path(data.get("inp", "字幕")).with_suffix(".srt").name,
                )
            if not srt_path and not txt_path:
                return False
            write_outputs(updated, srt_path=srt_path, txt_path=txt_path, action="save")
            if show_message:
                messagebox.showinfo("已儲存", "字幕修改已儲存。")
            return True

        def suggest_rules_after_export():
            """匯出後嘗試從本次修改抽出個人化規則建議，跳對話框讓使用者決定。"""
            if suggestion_state["done"]:
                return
            if PERSONAL_RULES is None:
                return
            try:
                rules_path = PERSONAL_RULES_PATH
                history_path = here() / "logs" / "srt_edit_history.jsonl"
                store = PERSONAL_RULES.RuleStore(rules_path)
                edits = PERSONAL_RULES.iter_edits_for_input(
                    history_path,
                    data.get("inp", ""),
                    since=editor_opened_at,
                )
                if not edits:
                    return
                candidates = PERSONAL_RULES.summarise_candidates(
                    edits,
                    existing_keys=store.existing_keys(),
                )
                if not candidates:
                    return
                # 一次匯出只問一次；下次重新打開編輯器才會再問
                suggestion_state["done"] = True
                self.open_rule_suggestion_dialog(win, candidates, store, rules_path)
            except Exception as exc:
                # 任何錯誤都不能擋住匯出流程
                self.log(f"個人化規則建議跳過：{exc}", tag="warn")

        def export_srt() -> bool:
            updated = check_timeline(show_ok=False)
            if updated is None:
                return False
            path = filedialog.asksaveasfilename(
                title="另存 SRT",
                defaultextension=".srt",
                filetypes=[("SRT 字幕", "*.srt")],
                initialfile=Path(data.get("srt") or data.get("inp", "字幕")).with_suffix(".srt").name,
            )
            if path:
                write_outputs(updated, srt_path=path, action="export_srt")
                messagebox.showinfo("已匯出", f"SRT 已匯出：\n{path}")
                suggest_rules_after_export()
                return True
            return False

        def export_txt() -> bool:
            updated = check_timeline(show_ok=False)
            if updated is None:
                return False
            path = filedialog.asksaveasfilename(
                title="另存 TXT",
                defaultextension=".txt",
                filetypes=[("文字檔", "*.txt")],
                initialfile=Path(data.get("txt") or data.get("inp", "字幕")).with_suffix(".txt").name,
            )
            if path:
                write_outputs(updated, txt_path=path, action="export_txt")
                messagebox.showinfo("已匯出", f"TXT 已匯出：\n{path}")
                suggest_rules_after_export()
                return True
            return False

        def has_unsaved_changes() -> bool:
            try:
                current = collect_chunks()
            except Exception:
                return True
            return not chunks_equal(current, saved_snapshot["chunks"])

        def close_editor():
            pause_playback()
            cancel_scrub_preview()
            if has_unsaved_changes():
                choice = messagebox.askyesnocancel(
                    "尚未儲存",
                    "目前字幕有修改但尚未儲存。\n\n要先儲存再關閉嗎？",
                )
                if choice is None:
                    return
                if choice and not save_current(show_message=False):
                    return
            self.stop_preview()
            if waveform_proxy_path:
                Path(waveform_proxy_path).unlink(missing_ok=True)
            win.destroy()

        foot = ctk.CTkFrame(win, fg_color="transparent")
        foot.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 14))
        foot.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            foot,
            text="⤓ 匯入",
            width=112,
            height=42,
            corner_radius=15,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=lambda: import_srt_file(),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            foot,
            text="檢查時間軸",
            width=128,
            height=42,
            corner_radius=15,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=check_timeline,
        ).grid(row=0, column=2, sticky="e", padx=(0, 8))
        ctk.CTkButton(
            foot,
            text="另存 TXT",
            width=112,
            height=42,
            corner_radius=15,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=export_txt,
        ).grid(row=0, column=3, sticky="e", padx=(0, 8))
        ctk.CTkButton(
            foot,
            text="另存 SRT",
            width=112,
            height=42,
            corner_radius=15,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=export_srt,
        ).grid(row=0, column=4, sticky="e", padx=(0, 8))
        ctk.CTkButton(
            foot,
            text="儲存修改",
            width=124,
            height=42,
            corner_radius=15,
            fg_color=ORANGE,
            hover_color=ORANGE_DARK,
            text_color="#FFFFFF",
            font=(FONT, 13, "bold"),
            command=save_current,
        ).grid(row=0, column=5, sticky="e", padx=(0, 8))
        ctk.CTkButton(
            foot,
            text="關閉",
            width=94,
            height=42,
            corner_radius=15,
            fg_color="#32333B",
            hover_color="#45464F",
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=close_editor,
        ).grid(row=0, column=6, sticky="e")
        win.protocol("WM_DELETE_WINDOW", close_editor)

    def open_personal_rules_window(self, parent=None):
        if not has_feature("custom_rules"):
            self.show_supporter_message("custom_rules")
            return
        """個人化規則庫管理視窗（階段 5 輪 B）。"""
        if PERSONAL_RULES is None:
            messagebox.showinfo("規則庫無法開啟", "找不到 core/personal_rules.py，請確認檔案完整。")
            return
        rules_path = PERSONAL_RULES_PATH
        try:
            store = PERSONAL_RULES.RuleStore(rules_path)
        except Exception as exc:
            messagebox.showerror("規則庫載入失敗", str(exc))
            return

        anchor = parent or self
        win = ctk.CTkToplevel(anchor)
        win.title("個人化規則庫")
        win.geometry("880x620")
        win.minsize(720, 480)
        win.configure(fg_color=BLACK_KITE)
        self.apply_window_icon(win, "_setting.png")
        win.transient(anchor)
        win.grab_set()
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(2, weight=1)

        domains = list(getattr(PERSONAL_RULES, "DEFAULT_DOMAINS", ("通用",)))

        # ── 標題列 ─────────────────────────────────────────
        head = ctk.CTkFrame(win, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 4))
        head.grid_columnconfigure(0, weight=1)
        title_lbl = ctk.CTkLabel(
            head,
            text="個人化規則庫",
            text_color=TEXT_ON_DARK,
            font=(FONT, 22, "bold"),
            anchor="w",
        )
        title_lbl.grid(row=0, column=0, sticky="w")
        stats_lbl = ctk.CTkLabel(
            head,
            text="",
            text_color=MUTED_ON_DARK,
            font=(FONT, 13),
            anchor="e",
        )
        stats_lbl.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(
            head,
            text=f"檔案：{rules_path}",
            text_color=MUTED_ON_DARK,
            font=(FONT, 11),
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # ── 篩選列 ─────────────────────────────────────────
        filt = ctk.CTkFrame(win, fg_color="transparent")
        filt.grid(row=1, column=0, sticky="ew", padx=24, pady=(8, 0))
        filt.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(filt, text="領域：", text_color=MUTED_ON_DARK, font=(FONT, 12)).grid(row=0, column=0, sticky="w")
        domain_filter_var = ctk.StringVar(value="全部")
        ctk.CTkOptionMenu(
            filt,
            variable=domain_filter_var,
            values=["全部"] + domains,
            width=110,
            fg_color=DARK,
            button_color=DARK,
            button_hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 12, "bold"),
            dropdown_font=(FONT, 12),
        ).grid(row=0, column=1, padx=(4, 12), sticky="w")
        ctk.CTkLabel(filt, text="搜尋：", text_color=MUTED_ON_DARK, font=(FONT, 12)).grid(row=0, column=2, sticky="w")
        search_var = ctk.StringVar(value="")
        ctk.CTkEntry(
            filt,
            textvariable=search_var,
            placeholder_text="輸入 before / after 關鍵字",
            height=32,
            fg_color=DARK_2,
            border_color=LINE,
            text_color=TEXT_ON_DARK,
            font=(FONT, 12),
        ).grid(row=0, column=3, sticky="ew", padx=(4, 8))
        show_frozen_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            filt,
            text="顯示冷凍",
            variable=show_frozen_var,
            checkbox_width=18,
            checkbox_height=18,
            corner_radius=4,
            fg_color=ORANGE,
            hover_color=ORANGE_DARK,
            border_color=LINE,
            text_color=MUTED_ON_DARK,
            font=(FONT, 12),
        ).grid(row=0, column=4, sticky="e")

        # ── 規則列表 ───────────────────────────────────────
        body = ctk.CTkScrollableFrame(
            win,
            fg_color=CARD_DARK,
            corner_radius=13,
            scrollbar_button_color=DARK,
            scrollbar_button_hover_color=ORANGE_DARK,
        )
        body.grid(row=2, column=0, sticky="nsew", padx=24, pady=(10, 8))
        body.grid_columnconfigure(1, weight=1)

        row_widgets: list[dict] = []

        def update_stats():
            rules = store.rules
            summary = store.summarise_state() if hasattr(store, "summarise_state") else {
                "total": len(rules),
                "active": sum(1 for r in rules if r.get("state", "active") == "active"),
                "frozen": sum(1 for r in rules if r.get("state", "active") == "frozen"),
            }
            enabled = sum(1 for r in rules if r.get("enabled", True))
            adopted = sum(int(r.get("adopted_count") or 0) for r in rules)
            stats_lbl.configure(
                text=f"共 {summary['total']} 條（啟用 {summary['active']} / 冷凍 {summary['frozen']}），採納次數 {adopted}",
            )

        def matches_filter(rule: dict) -> bool:
            if not show_frozen_var.get() and rule.get("state", "active") == "frozen":
                return False
            df = domain_filter_var.get()
            if df != "全部" and rule.get("domain") != df:
                return False
            kw = search_var.get().strip()
            if kw:
                if kw not in (rule.get("before") or "") and kw not in (rule.get("after") or ""):
                    return False
            return True

        def render():
            for w in row_widgets:
                try:
                    w["frame"].destroy()
                except Exception:
                    pass
            row_widgets.clear()
            visible = [r for r in store.rules if matches_filter(r)]
            visible.sort(key=lambda r: (-int(r.get("adopted_count") or 0), r.get("created_at", "")))
            for i, rule in enumerate(visible):
                rid = rule.get("id", "")
                rf = ctk.CTkFrame(body, fg_color="transparent")
                rf.grid(row=i, column=0, columnspan=5, sticky="ew", padx=8, pady=3)
                rf.grid_columnconfigure(1, weight=1)

                en_var = ctk.BooleanVar(value=bool(rule.get("enabled", True)))

                def on_toggle(rid=rid, var=en_var):
                    store.set_enabled(rid, var.get())
                    try:
                        store.save()
                    except Exception:
                        pass
                    update_stats()

                ctk.CTkSwitch(
                    rf,
                    text="",
                    variable=en_var,
                    progress_color=ORANGE,
                    button_color="#FFFFFF",
                    button_hover_color="#FFFFFF",
                    fg_color="#5A5F68",
                    width=46,
                    switch_width=44,
                    switch_height=22,
                    command=on_toggle,
                ).grid(row=0, column=0, padx=(2, 10), sticky="w")

                tf = ctk.CTkFrame(rf, fg_color="transparent")
                tf.grid(row=0, column=1, sticky="ew")
                tf.grid_columnconfigure(0, weight=1)
                state_tag = "❄ 冷凍" if rule.get("state", "active") == "frozen" else ""
                tag_text = f"  {state_tag}" if state_tag else ""
                ctk.CTkLabel(
                    tf,
                    text=f"「{rule.get('before','')}」  →  「{rule.get('after','')}」{tag_text}",
                    text_color="#8A92A0" if state_tag else TEXT_ON_DARK,
                    font=(FONT, 14, "bold"),
                    anchor="w",
                ).grid(row=0, column=0, sticky="w")
                last_used = rule.get("last_used_at") or "—"
                meta = (
                    f"領域：{rule.get('domain','通用')}　│　採納 {rule.get('adopted_count',0)} / 拒絕 {rule.get('rejected_count',0)}"
                    f"　│　建立：{(rule.get('created_at') or '')[:10]}　│　最近使用：{last_used[:10]}"
                )
                ctk.CTkLabel(
                    tf,
                    text=meta,
                    text_color=MUTED_ON_DARK,
                    font=(FONT, 11),
                    anchor="w",
                ).grid(row=1, column=0, sticky="w", pady=(2, 0))

                dom_var = ctk.StringVar(value=rule.get("domain", "通用"))

                def on_domain_change(_v=None, rid=rid, var=dom_var):
                    for r in store.rules:
                        if r.get("id") == rid:
                            r["domain"] = var.get()
                            break
                    try:
                        store.save()
                    except Exception:
                        pass

                ctk.CTkOptionMenu(
                    rf,
                    variable=dom_var,
                    values=domains,
                    width=98,
                    fg_color=DARK,
                    button_color=DARK,
                    button_hover_color=GARNET,
                    text_color=TEXT_ON_DARK,
                    font=(FONT, 12, "bold"),
                    dropdown_font=(FONT, 12),
                    command=on_domain_change,
                ).grid(row=0, column=2, padx=(8, 6), sticky="ne")

                def on_delete(rid=rid):
                    if not messagebox.askyesno("刪除規則", f"確定要刪除這條規則？\n「{rule.get('before','')}」→「{rule.get('after','')}」"):
                        return
                    store.remove(rid)
                    try:
                        store.save()
                    except Exception:
                        pass
                    render()
                    update_stats()

                state_btn_frame = ctk.CTkFrame(rf, fg_color="transparent")
                state_btn_frame.grid(row=0, column=3, sticky="ne")
                is_frozen = rule.get("state", "active") == "frozen"

                def on_toggle_state(rid=rid, frozen=is_frozen):
                    new_state = "active" if frozen else "frozen"
                    if hasattr(store, "set_state"):
                        store.set_state(rid, new_state)
                        try:
                            store.save()
                        except Exception:
                            pass
                        render()
                        update_stats()

                ctk.CTkButton(
                    state_btn_frame,
                    text="解凍" if is_frozen else "冷凍",
                    width=58,
                    height=30,
                    corner_radius=11,
                    fg_color=DARK,
                    hover_color=GARNET,
                    text_color=TEXT_ON_DARK,
                    font=(FONT, 12, "bold"),
                    command=on_toggle_state,
                ).pack(side="left", padx=(0, 4))

                ctk.CTkButton(
                    state_btn_frame,
                    text="刪除",
                    width=58,
                    height=30,
                    corner_radius=11,
                    fg_color="#3A2022",
                    hover_color="#5A2B2F",
                    text_color=TEXT_ON_DARK,
                    font=(FONT, 12, "bold"),
                    command=on_delete,
                ).pack(side="left")

                row_widgets.append({"frame": rf})

            if not visible:
                empty = ctk.CTkLabel(
                    body,
                    text="（沒有符合條件的規則）",
                    text_color=MUTED_ON_DARK,
                    font=(FONT, 13),
                )
                empty.grid(row=0, column=0, padx=12, pady=20, sticky="w")
                row_widgets.append({"frame": empty})

        def on_filter_changed(*_):
            render()

        domain_filter_var.trace_add("write", on_filter_changed)
        search_var.trace_add("write", on_filter_changed)
        show_frozen_var.trace_add("write", on_filter_changed)

        # ── 底部按鈕 ───────────────────────────────────────
        foot = ctk.CTkFrame(win, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 16))
        foot.grid_columnconfigure(0, weight=1)

        def on_enable_all():
            for r in store.rules:
                r["enabled"] = True
            try:
                store.save()
            except Exception:
                pass
            render()
            update_stats()

        def on_disable_all():
            for r in store.rules:
                r["enabled"] = False
            try:
                store.save()
            except Exception:
                pass
            render()
            update_stats()

        def on_open_folder():
            try:
                rules_path.parent.mkdir(parents=True, exist_ok=True)
                os.startfile(str(rules_path.parent))
            except Exception as exc:
                messagebox.showerror("無法開啟資料夾", str(exc))

        ctk.CTkButton(
            foot, text="全部啟用", width=98, height=36, corner_radius=13,
            fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"), command=on_enable_all,
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ctk.CTkButton(
            foot, text="全部停用", width=98, height=36, corner_radius=13,
            fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"), command=on_disable_all,
        ).grid(row=0, column=1, sticky="w", padx=(0, 6))
        ctk.CTkButton(
            foot, text="開啟資料夾", width=110, height=36, corner_radius=13,
            fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"), command=on_open_folder,
        ).grid(row=0, column=2, sticky="w", padx=(0, 6))

        def on_cleanup():
            if not hasattr(store, "merge_similar"):
                messagebox.showinfo("無法整理", "目前載入的 personal_rules.py 版本不含整理功能，請更新檔案。")
                return
            cap_default = int(getattr(PERSONAL_RULES, "DEFAULT_CAP_PER_DOMAIN", 100))
            days_default = int(getattr(PERSONAL_RULES, "DEFAULT_FREEZE_DAYS", 90))
            if not messagebox.askyesno(
                "整理規則庫",
                "將執行：\n"
                f"  ① 自動合併「替換結果相同 + 來源字高相似」的規則\n"
                f"  ② 將 {days_default} 天未使用的規則冷凍\n"
                f"  ③ 每個領域只保留採納分數最高的 {cap_default} 條，其餘冷凍\n\n"
                "冷凍後規則仍會留在檔案，可隨時解凍。要繼續嗎？",
            ):
                return
            merged = store.merge_similar()
            frozen_old = store.freeze_unused()
            frozen_cap = store.enforce_domain_cap()
            try:
                store.save()
            except Exception as exc:
                messagebox.showerror("規則庫存檔失敗", str(exc))
                return
            render()
            update_stats()
            messagebox.showinfo(
                "整理完成",
                f"合併 {merged} 條相似規則\n冷凍 {frozen_old} 條長期未用規則\n冷凍 {frozen_cap} 條超過領域上限的規則",
            )

        ctk.CTkButton(
            foot, text="整理規則庫", width=122, height=36, corner_radius=13,
            fg_color=ORANGE, hover_color=ORANGE_DARK, text_color="#FFFFFF",
            font=(FONT, 13, "bold"), command=on_cleanup,
        ).grid(row=0, column=3, sticky="w", padx=(0, 6))
        ctk.CTkButton(
            foot, text="關閉", width=86, height=36, corner_radius=13,
            fg_color="#32333B", hover_color="#45464F", text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"), command=win.destroy,
        ).grid(row=0, column=4, sticky="e")

        update_stats()
        render()

    def open_rule_suggestion_dialog(self, parent, candidates: list, store, rules_path):
        """匯出後彈出的「個人化規則建議」視窗（階段 5 輪 A）。"""
        if not candidates or PERSONAL_RULES is None:
            return
        domains = tuple(getattr(PERSONAL_RULES, "DEFAULT_DOMAINS", ("通用",)))
        default_domain = domains[0] if domains else "通用"

        dialog = ctk.CTkToplevel(parent)
        dialog.title("個人化規則建議")
        dialog.geometry("760x560")
        dialog.minsize(640, 460)
        dialog.configure(fg_color=BLACK_KITE)
        self.apply_window_icon(dialog, "_LOGO.png")
        dialog.transient(parent)
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(dialog, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 4))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head,
            text=f"從本次修改抽出了 {len(candidates)} 條候選規則",
            text_color=TEXT_ON_DARK,
            font=(FONT, 17, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            head,
            text="勾選你要加進「個人化規則庫」的項目，並指定領域。輪 A 階段規則只儲存，輪 B 才會注入 AI 校對。",
            text_color=MUTED_ON_DARK,
            font=(FONT, 12),
            anchor="w",
            justify="left",
            wraplength=700,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        body = ctk.CTkScrollableFrame(
            dialog,
            fg_color=CARD_DARK,
            corner_radius=13,
            scrollbar_button_color=DARK,
            scrollbar_button_hover_color=ORANGE_DARK,
        )
        body.grid(row=1, column=0, sticky="nsew", padx=20, pady=(10, 10))
        body.grid_columnconfigure(1, weight=1)

        rows: list[dict] = []
        for i, cand in enumerate(candidates):
            check_var = ctk.BooleanVar(value=True)
            domain_var = ctk.StringVar(value=default_domain)

            row_frame = ctk.CTkFrame(body, fg_color="transparent")
            row_frame.grid(row=i, column=0, columnspan=4, sticky="ew", padx=8, pady=4)
            row_frame.grid_columnconfigure(1, weight=1)

            ctk.CTkCheckBox(
                row_frame,
                text="",
                variable=check_var,
                checkbox_width=20,
                checkbox_height=20,
                corner_radius=5,
                fg_color=ORANGE,
                hover_color=ORANGE_DARK,
                border_color=LINE,
            ).grid(row=0, column=0, padx=(4, 10), pady=4, sticky="nw")

            text_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            text_frame.grid(row=0, column=1, sticky="ew")
            text_frame.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                text_frame,
                text=f"「{cand['before']}」  →  「{cand['after']}」",
                text_color=TEXT_ON_DARK,
                font=(FONT, 14, "bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="w")
            sample = cand.get("samples") or []
            if sample:
                first = sample[0]
                ctk.CTkLabel(
                    text_frame,
                    text=f"例：{first[0]}  →  {first[1]}",
                    text_color=MUTED_ON_DARK,
                    font=(FONT, 11),
                    anchor="w",
                    justify="left",
                    wraplength=480,
                ).grid(row=1, column=0, sticky="w", pady=(2, 0))

            ctk.CTkLabel(
                row_frame,
                text=f"× {cand['occurrences']}",
                text_color=MUTED_ON_DARK,
                font=(FONT, 12, "bold"),
                width=46,
            ).grid(row=0, column=2, padx=(8, 8), sticky="ne")

            ctk.CTkOptionMenu(
                row_frame,
                variable=domain_var,
                values=list(domains),
                width=98,
                fg_color=DARK,
                button_color=DARK,
                button_hover_color=GARNET,
                text_color=TEXT_ON_DARK,
                font=(FONT, 12, "bold"),
                dropdown_font=(FONT, 12),
            ).grid(row=0, column=3, padx=(0, 4), sticky="ne")

            rows.append({"cand": cand, "check": check_var, "domain": domain_var})

        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 18))
        actions.grid_columnconfigure(2, weight=1)

        def toggle_all(value: bool):
            for r in rows:
                r["check"].set(value)

        ctk.CTkButton(
            actions,
            text="全選",
            width=70,
            height=36,
            corner_radius=13,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=lambda: toggle_all(True),
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ctk.CTkButton(
            actions,
            text="全不選",
            width=78,
            height=36,
            corner_radius=13,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=lambda: toggle_all(False),
        ).grid(row=0, column=1, sticky="w", padx=(0, 6))

        def commit():
            selected = [r for r in rows if r["check"].get()]
            if not selected:
                dialog.destroy()
                return
            added = 0
            for r in selected:
                try:
                    store.add(
                        r["cand"]["before"],
                        r["cand"]["after"],
                        domain=r["domain"].get() or default_domain,
                        source="srt_editor_export",
                    )
                    added += 1
                except Exception:
                    continue
            try:
                store.save()
            except Exception as exc:
                messagebox.showerror("規則庫存檔失敗", str(exc))
                return
            self.log(f"個人化規則庫：新增 {added} 條（檔案：{rules_path}）", tag="success")
            messagebox.showinfo("已加入規則庫", f"新增 {added} 條規則，總計 {len(store.rules)} 條。\n（輪 A 只儲存，輪 B 啟用後會自動注入 AI 校對）")
            dialog.destroy()

        ctk.CTkButton(
            actions,
            text="取消",
            width=86,
            height=36,
            corner_radius=13,
            fg_color="#32333B",
            hover_color="#45464F",
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=dialog.destroy,
        ).grid(row=0, column=3, sticky="e", padx=(0, 6))
        ctk.CTkButton(
            actions,
            text="加入規則庫",
            width=128,
            height=36,
            corner_radius=13,
            fg_color=ORANGE,
            hover_color=ORANGE_DARK,
            text_color="#FFFFFF",
            font=(FONT, 13, "bold"),
            command=commit,
        ).grid(row=0, column=4, sticky="e")

    def store_compare(self, inp, srt, txt, before_chunks, after_chunks, before_text, after_text):
        self.last_compare = {
            "inp": inp,
            "srt": srt,
            "txt": txt,
            "before_chunks": before_chunks,
            "after_chunks": after_chunks,
            "before_text": before_text,
            "after_text": after_text,
        }
        self.batch_compares[inp] = self.last_compare

        def enable():
            diffs = self.comparison_diffs()
            self.result_label.configure(text=f"共 {len(after_chunks)} 組字幕，AI 修改了 {len(diffs)} 行")
            self.compare_btn.configure(state="normal")
        self.after(0, enable)

    def comparison_diffs(self):
        if not self.last_compare:
            return []
        before = self.last_compare["before_chunks"]
        after = self.last_compare["after_chunks"]
        diffs = []
        for i, (b, a) in enumerate(zip(before, after), start=1):
            bt = (b.get("text") or "").strip()
            at = (a.get("text") or "").strip()
            # 只改標點的行不列入對照（SRT 輸出前標點會全部移除，對字幕無影響）
            if CORE.strip_punct_for_srt(bt) != CORE.strip_punct_for_srt(at):
                ts = b.get("timestamp") or (b.get("start", 0.0), b.get("end", 0.0))
                start = CORE.format_timestamp(ts[0] if ts[0] is not None else 0.0)
                end = CORE.format_timestamp(ts[1] if ts[1] is not None else 0.0)
                diffs.append((i, f"{start} --> {end}", bt, at))
        return diffs

    def comparison_text(self) -> str:
        if not self.last_compare:
            return ""
        diffs = self.comparison_diffs()
        data = self.last_compare
        lines = [
            f"檔名：{Path(data['inp']).name}",
            f"字幕組數：{len(data['after_chunks'])}",
            f"修改行數：{len(diffs)}",
            "=" * 48,
            "",
        ]
        if not diffs:
            lines.append("AI 未修改任何字幕文字。")
        for idx, timecode, before, after in diffs:
            lines.append(f"第 {idx} 組｜{timecode}")
            lines.append(f"原文：{before or '（空）'}")
            lines.append(f"校對：{after or '（空）'}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def persist_compare_after_chunks(self, action: str = "quick_compare") -> int:
        if not self.last_compare:
            return 0
        data = self.last_compare
        after_chunks = clone_chunks(data.get("after_chunks") or [])
        after_text = chunks_to_editable_plain(after_chunks)
        data["after_chunks"] = after_chunks
        data["after_text"] = after_text

        wrote = 0
        if data.get("srt"):
            # 用正規版 chunks_to_srt（剝標點＋自動換行），與第一版 SRT 行為一致
            Path(data["srt"]).write_text(CORE.chunks_to_srt(after_chunks), encoding="utf-8-sig")
            wrote += 1
        if data.get("txt"):
            Path(data["txt"]).write_text(after_text + "\n", encoding="utf-8-sig")
            wrote += 1

        self.last_result = {
            "inp": data.get("inp", ""),
            "srt": data.get("srt", ""),
            "txt": data.get("txt", ""),
            "chunks": clone_chunks(after_chunks),
        }
        diffs = self.comparison_diffs()
        self.result_label.configure(text=f"共 {len(after_chunks)} 組字幕，AI 修改了 {len(diffs)} 行")
        self.srt_editor_btn.configure(state="normal")
        self.log(f"快速對照已更新輸出，AI 修改行數：{len(diffs)}。", "success")
        return wrote

    def show_comparison(self):
        if not has_feature("quick_compare_full"):
            self.show_supporter_message("quick_compare_full")
            return
        if not self.last_compare:
            messagebox.showinfo("尚無對照資料", "請先完成一次 AI 校對。")
            return
        diffs = self.comparison_diffs()
        data = self.last_compare

        # Quick review flow inspired by SubDesk's compact AI correction workflow:
        # https://github.com/ji4/subdesk
        win = ctk.CTkToplevel(self)
        win.title("快速對照")
        win.geometry("980x740")
        win.minsize(720, 520)
        win.configure(fg_color=BLACK_KITE)
        win.transient(self)
        win.grab_set()
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(2, weight=1)

        review_queue = [idx - 1 for idx, _timecode, _before, _after in diffs]
        review_pos = {"value": 0}
        reviewed: set[int] = set()
        current_review = {"index": None}

        head = ctk.CTkFrame(win, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head,
            text=f"檔案：{Path(data['inp']).name}",
            text_color=TEXT_ON_DARK,
            font=(FONT, 20, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        summary_label = ctk.CTkLabel(
            head,
            text=f"共 {len(data['after_chunks'])} 組字幕，AI 修改了 {len(diffs)} 行",
            text_color=MUTED_ON_DARK,
            font=(FONT, 13),
        )
        summary_label.grid(row=0, column=1, sticky="e")

        review = ctk.CTkFrame(win, fg_color=AI_REVIEW_BG, corner_radius=14, border_width=1, border_color=AI_REVIEW_BORDER)
        review.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))
        review.grid_columnconfigure(0, weight=1)
        review_status = ctk.StringVar(value="")
        ctk.CTkLabel(
            review,
            textvariable=review_status,
            text_color=AI_REVIEW,
            font=(FONT, 14, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=4, sticky="ew", padx=16, pady=(14, 8))
        original_box = ctk.CTkTextbox(
            review,
            height=72,
            corner_radius=10,
            fg_color=DARK_2,
            border_width=1,
            border_color=LINE,
            text_color=RED_TEXT,
            font=(FONT, 14),
            wrap="word",
        )
        original_box.grid(row=1, column=0, columnspan=4, sticky="ew", padx=16, pady=(0, 8))
        corrected_box = ctk.CTkTextbox(
            review,
            height=78,
            corner_radius=10,
            fg_color=DARK_2,
            border_width=1,
            border_color=AI_REVIEW_BORDER,
            text_color=TEXT_ON_DARK,
            font=(FONT, 14),
            wrap="word",
        )
        corrected_box.grid(row=2, column=0, columnspan=4, sticky="ew", padx=16, pady=(0, 12))

        def set_box_text(box, value: str, *, readonly: bool = False):
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("1.0", value)
            if readonly:
                box.configure(state="disabled")

        def chunk_text(chunks: list[dict], zero_index: int) -> str:
            if 0 <= zero_index < len(chunks):
                return (chunks[zero_index].get("text") or "").strip()
            return ""

        def is_review_item(zero_index: int) -> bool:
            before_text = chunk_text(data.get("before_chunks") or [], zero_index)
            after_text = chunk_text(data.get("after_chunks") or [], zero_index)
            return bool(before_text != after_text)

        def active_review_index() -> int | None:
            while review_pos["value"] < len(review_queue):
                idx = review_queue[review_pos["value"]]
                if idx not in reviewed and is_review_item(idx):
                    return idx
                review_pos["value"] += 1
            return None

        def refresh_summary():
            now_diffs = self.comparison_diffs()
            summary_label.configure(text=f"共 {len(data['after_chunks'])} 組字幕，AI 修改了 {len(now_diffs)} 行")

        def save_current_text() -> bool:
            idx = current_review.get("index")
            if idx is None:
                return False
            after_chunks = data.get("after_chunks") or []
            if not (0 <= idx < len(after_chunks)):
                return False
            after_chunks[idx]["text"] = corrected_box.get("1.0", "end").strip()
            self.persist_compare_after_chunks()
            refresh_summary()
            return True

        def load_review_item():
            idx = active_review_index()
            current_review["index"] = idx
            if idx is None:
                review_status.set("快速核對完成：目前沒有剩下的 AI 修改片段。")
                set_box_text(original_box, "沒有待確認內容。", readonly=True)
                set_box_text(corrected_box, "", readonly=False)
                corrected_box.configure(state="disabled")
                return
            before_chunks = data.get("before_chunks") or []
            after_chunks = data.get("after_chunks") or []
            ts = (before_chunks[idx].get("timestamp") if idx < len(before_chunks) else None) or (0.0, 0.0)
            start = CORE.format_timestamp(ts[0] if ts[0] is not None else 0.0)
            end = CORE.format_timestamp(ts[1] if ts[1] is not None else 0.0)
            remaining = sum(1 for n in review_queue if n not in reviewed and is_review_item(n))
            review_status.set(f"待確認 {review_pos['value'] + 1}/{len(review_queue)}｜第 {idx + 1} 組｜{start} --> {end}｜剩餘 {remaining}")
            set_box_text(original_box, f"原文：{chunk_text(before_chunks, idx) or '（空）'}", readonly=True)
            corrected_box.configure(state="normal")
            set_box_text(corrected_box, chunk_text(after_chunks, idx), readonly=False)

        def render_diff_list():
            for child in body.winfo_children():
                child.destroy()
            now_diffs = self.comparison_diffs()
            if not now_diffs:
                ctk.CTkLabel(body, text="AI 未修改任何字幕文字。", text_color=TEXT_ON_DARK, font=(FONT, 16)).grid(
                    row=0, column=0, sticky="w", pady=20
                )
                return
            for row, (idx, timecode, before, after) in enumerate(now_diffs):
                item = ctk.CTkFrame(body, fg_color=DARK_2, corner_radius=13, border_width=1, border_color=AI_REVIEW_BORDER)
                item.grid(row=row, column=0, sticky="ew", pady=(0, 10))
                item.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(item, text=f"{idx}. {timecode}", text_color=AI_REVIEW, font=(EN_FONT, 12, "bold")).grid(
                    row=0, column=0, sticky="w", padx=16, pady=(12, 4)
                )
                ctk.CTkLabel(item, text=f"原文：{before or '（空）'}", text_color=RED_TEXT, font=(FONT, 14), wraplength=860, justify="left").grid(
                    row=1, column=0, sticky="w", padx=16, pady=(0, 4)
                )
                ctk.CTkLabel(item, text=f"校對：{after or '（空）'}", text_color=GREEN_TEXT, font=(FONT, 14), wraplength=860, justify="left").grid(
                    row=2, column=0, sticky="w", padx=16, pady=(0, 14)
                )

        def play_current():
            idx = current_review.get("index")
            if idx is None:
                return
            before_chunks = data.get("before_chunks") or []
            if not (0 <= idx < len(before_chunks)):
                return
            ts = before_chunks[idx].get("timestamp") or (0.0, 0.0)
            start = max(0.0, (ts[0] if ts[0] is not None else 0.0) - 0.35)
            end = (ts[1] if ts[1] is not None else start + 2.0) + 0.35
            if end <= start:
                end = start + 2.0
            self.play_srt_segment(data.get("inp", ""), start, end)

        def accept_current():
            idx = current_review.get("index")
            if idx is None:
                return
            if save_current_text():
                reviewed.add(idx)
                review_pos["value"] += 1
                render_diff_list()
                load_review_item()

        def restore_current():
            idx = current_review.get("index")
            if idx is None:
                return
            before_chunks = data.get("before_chunks") or []
            after_chunks = data.get("after_chunks") or []
            if 0 <= idx < len(before_chunks) and 0 <= idx < len(after_chunks):
                # 還原時直接剝標點，讓還原結果與 SRT 輸出一致（無標點）
                after_chunks[idx]["text"] = CORE.strip_punct_for_srt(chunk_text(before_chunks, idx))
                self.persist_compare_after_chunks()
                reviewed.add(idx)
                review_pos["value"] += 1
                refresh_summary()
                render_diff_list()
                load_review_item()

        def skip_current():
            idx = current_review.get("index")
            if idx is None:
                return
            reviewed.add(idx)
            review_pos["value"] += 1
            load_review_item()

        ctk.CTkButton(review, text="播放片段", width=104, height=38, corner_radius=14, fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK, font=(FONT, 13, "bold"), command=play_current).grid(
            row=3, column=0, sticky="w", padx=(16, 8), pady=(0, 14)
        )
        ctk.CTkButton(review, text="還原並下一個", width=124, height=38, corner_radius=14, fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK, font=(FONT, 13, "bold"), command=restore_current).grid(
            row=3, column=1, sticky="w", padx=(0, 8), pady=(0, 14)
        )
        ctk.CTkButton(review, text="略過", width=84, height=38, corner_radius=14, fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK, font=(FONT, 13, "bold"), command=skip_current).grid(
            row=3, column=2, sticky="w", padx=(0, 8), pady=(0, 14)
        )
        ctk.CTkButton(review, text="接受並下一個", width=128, height=38, corner_radius=14, fg_color=ORANGE, hover_color=ORANGE_DARK, text_color="#FFFFFF", font=(FONT, 13, "bold"), command=accept_current).grid(
            row=3, column=3, sticky="e", padx=(0, 16), pady=(0, 14)
        )

        body = ctk.CTkScrollableFrame(
            win,
            fg_color="transparent",
            scrollbar_button_color=DARK,
            scrollbar_button_hover_color=GARNET,
        )
        body.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 12))
        body.grid_columnconfigure(0, weight=1)
        try:
            body._scrollbar.configure(width=16, corner_radius=6, button_color="#2C2222", button_hover_color=ORANGE_DARK)
        except Exception:
            pass
        render_diff_list()
        load_review_item()

        foot = ctk.CTkFrame(win, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 20))
        foot.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(foot, text="關閉", width=100, height=40, corner_radius=14, fg_color="#32333B", hover_color="#45464F", text_color=TEXT_ON_DARK, font=(FONT, 13, "bold"), command=win.destroy).grid(row=0, column=3, sticky="e")
        ctk.CTkButton(foot, text="複製全部對照", width=144, height=40, corner_radius=14, fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK, font=(FONT, 13, "bold"), command=self.copy_comparison).grid(
            row=0, column=2, sticky="e", padx=(0, 8)
        )
        ctk.CTkButton(foot, text="另存對照 .txt", width=148, height=40, corner_radius=14, fg_color=ORANGE, hover_color=ORANGE_DARK, text_color="#FFFFFF", font=(FONT, 13, "bold"), command=self.save_comparison_txt).grid(
            row=0, column=1, sticky="e", padx=(0, 8)
        )
        # 不滿意 AI 改太多時，可直接把輸出還原回語音模型的原始辨識
        ctk.CTkButton(foot, text="↩ 還原原始辨識", width=168, height=40, corner_radius=14, fg_color="#3A2A22", hover_color="#5A3B2F", text_color=TEXT_ON_DARK, font=(FONT, 13, "bold"), command=self.restore_original).grid(
            row=0, column=0, sticky="w"
        )

        def quick_key(event):
            if isinstance(getattr(event, "widget", None), (tk.Text, tk.Entry)):
                if event.keysym == "Escape":
                    win.destroy()
                    return "break"
                return None
            if event.keysym in {"Return", "KP_Enter"}:
                accept_current()
                return "break"
            if event.keysym == "BackSpace":
                restore_current()
                return "break"
            if event.keysym == "space":
                play_current()
                return "break"
            if event.keysym in {"e", "E"}:
                corrected_box.focus_set()
                return "break"
            if event.keysym == "Escape":
                win.destroy()
                return "break"
            return None

        win.bind("<KeyPress>", quick_key)

    def copy_comparison(self):
        payload = self.comparison_text()
        self.clipboard_clear()
        self.clipboard_append(payload)
        self.log("已複製校對對照。", "success")

    def save_comparison_txt(self) -> str | None:
        if not self.last_compare:
            return None
        default_name = Path(self.last_compare["inp"]).stem + "_校對對照.txt"
        path = filedialog.asksaveasfilename(
            title="另存校對前後對照",
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")],
        )
        if not path:
            return None
        Path(path).write_text(self.comparison_text(), encoding="utf-8-sig")
        self.log(f"已另存校對對照：{path}", "success")
        messagebox.showinfo("已儲存", f"對照已儲存：\n{path}")
        return path

    def restore_original(self):
        if not self.last_compare:
            messagebox.showinfo("尚無資料", "請先完成一次 AI 校對。")
            return
        save_first = messagebox.askyesnocancel(
            "還原前留底",
            "還原會覆寫輸出檔案為 AI 校對前的原始辨識。\n\n是否先另存校對對照？",
        )
        if save_first is None:
            return
        if save_first:
            self.save_comparison_txt()
        if not messagebox.askyesno("還原原始辨識", "確定要覆寫輸出檔案，還原為原始辨識結果嗎？"):
            return
        data = self.last_compare
        count = 0
        if data.get("srt"):
            # 用正規版 chunks_to_srt（剝標點＋自動換行），與第一版 SRT 行為一致
            Path(data["srt"]).write_text(CORE.chunks_to_srt(data["before_chunks"]), encoding="utf-8-sig")
            count += 1
        if data.get("txt"):
            Path(data["txt"]).write_text((data.get("before_text") or "") + "\n", encoding="utf-8-sig")
            count += 1
        self.log(f"已還原 {count} 個輸出檔案為原始辨識。", "warn")
        messagebox.showinfo("已還原", f"已還原 {count} 個輸出檔案。")


# 2026-07-10：還原寫檔改用 chunks_to_srt（剝標點＋換行）、新增連續重複幻覺過濾
if __name__ == "__main__":
    enable_dpi_awareness()
    set_app_user_model_id()
    App().mainloop()
