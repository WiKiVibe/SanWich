"""
SanWich main app - CustomTkinter interface wired to the legacy core.

The legacy core is loaded read-only from an internal support file.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import datetime as _dt
import gc
import hashlib
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
APP_VERSION = "2.5"
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


def local_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "SanWich"
    return user_data_dir()


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
PROMPT_TEMPLATES_PATH = user_data_dir() / "prompt_templates.json"
CUSTOM_DICTIONARY_PATH = user_data_dir() / "custom_dictionary.json"
EXPERIMENTS_PATH = user_data_dir() / "experiments.json"
EDIT_HISTORY_LEGACY_PATH = ROOT / "logs" / "srt_edit_history.jsonl"


def version_tuple(value: str) -> tuple[int, int, int, int]:
    numbers = [int(part) for part in re.findall(r"\d+", value or "")[:3]]
    base = tuple((numbers + [0, 0, 0])[:3])
    # 同版號下，beta／alpha／rc 必須低於正式版；否則 2.5b 收不到 2.5 更新。
    prerelease = bool(re.search(r"(?:alpha|beta|rc|\d[ab](?:\d|$))", value or "", flags=re.I))
    return (*base, 0 if prerelease else 1)


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
AI_CHECKED = "#2F855A"
AI_CHECKED_BG = "#173126"
AI_CHECKED_BORDER = "#276749"
AI_UNCHECKED = "#64748B"
AI_UNCHECKED_BG = "#252B33"
AI_UNCHECKED_BORDER = "#475569"
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


def _load_core_module(filename: str, module_name: str) -> types.ModuleType | None:
    path = here() / "core" / filename
    if not path.exists():
        return None
    try:
        source = path.read_text(encoding="utf-8")
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        module.__name__ = module_name
        sys.modules[module_name] = module
        exec(compile(source, str(path), "exec"), module.__dict__)
        return module
    except Exception:
        return None


LEARNING = _load_core_module("learning.py", "SanWich_learning")
PROMPT_TEMPLATES = _load_core_module("prompt_templates.py", "SanWich_prompt_templates")
EXPERIMENTS = _load_core_module("experiments.py", "SanWich_experiments")
LOCAL_LLM = _load_core_module("local_llm.py", "SanWich_local_llm")
AUDIO_PREVIEW = _load_core_module("audio_preview.py", "SanWich_audio_preview")

# 編輯歷史與學習事件：優先 %APPDATA%，舊 logs/ 一次性遷移
if LEARNING is not None:
    try:
        EDIT_HISTORY_PATH = LEARNING.edit_history_path(user_data_dir())
        LEARNING.migrate_edit_history_once(EDIT_HISTORY_LEGACY_PATH, EDIT_HISTORY_PATH)
        FEEDBACK_STORE = LEARNING.FeedbackStore(LEARNING.feedback_path(user_data_dir()))
        PROJECT_PROFILES = LEARNING.ProjectProfileStore(LEARNING.project_profiles_path(user_data_dir()))
    except Exception:
        EDIT_HISTORY_PATH = user_data_dir() / "learning" / "srt_edit_history.jsonl"
        FEEDBACK_STORE = None
        PROJECT_PROFILES = None
else:
    EDIT_HISTORY_PATH = user_data_dir() / "learning" / "srt_edit_history.jsonl"
    FEEDBACK_STORE = None
    PROJECT_PROFILES = None

SUPPLEMENT_HISTORY_STORE = None
if LEARNING is not None:
    try:
        SUPPLEMENT_HISTORY_STORE = LEARNING.SupplementHistoryStore(
            LEARNING.supplement_history_path(user_data_dir())
        )
    except Exception:
        SUPPLEMENT_HISTORY_STORE = None

TEMPLATE_STORE = None
DICTIONARY_STORE = None
if PROMPT_TEMPLATES is not None:
    try:
        TEMPLATE_STORE = PROMPT_TEMPLATES.TemplateStore(PROMPT_TEMPLATES_PATH)
        DICTIONARY_STORE = PROMPT_TEMPLATES.DictionaryStore(CUSTOM_DICTIONARY_PATH)
    except Exception:
        TEMPLATE_STORE = None
        DICTIONARY_STORE = None

EXPERIMENT_CFG = None
if EXPERIMENTS is not None:
    try:
        EXPERIMENT_CFG = EXPERIMENTS.ExperimentConfig(EXPERIMENTS_PATH)
    except Exception:
        EXPERIMENT_CFG = None


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


def load_updater() -> types.ModuleType | None:
    path = here() / "core" / "updater.py"
    if not path.exists():
        return None
    try:
        source = path.read_text(encoding="utf-8")
        module = types.ModuleType("SanWich_updater")
        module.__file__ = str(path)
        module.__name__ = "SanWich_updater"
        sys.modules[module.__name__] = module
        exec(compile(source, str(path), "exec"), module.__dict__)
        return module
    except Exception:
        return None


UPDATER = load_updater()


def _create_license_manager():
    if LICENSE_MODULE is None:
        return None
    try:
        return LICENSE_MODULE.LicenseManager(config_path=CONFIG_PATH, app_version=APP_VERSION)
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
    "learning_loop": "學習閉環",
    "diarization": "語者分離",
    "domain_prompt_templates": "領域 Prompt 模板",
    "custom_dictionary": "自訂詞庫",
    "project_profiles": "專案／系列設定",
    "early_access": "效能實驗入口",
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
    return {"mode": "free", "label": "基本功能可用", "trial_ends_at": "", "days_left": 0}


DEEPSEEK_MODELS = ["deepseek-v4-flash", "deepseek-v4-pro"]
LOCAL_MODELS = [getattr(LOCAL_LLM, "MODEL_LABEL", "Breeze-7B-Instruct v1.0 (Local Q4_K_M)")]
PROVIDER_ORDER = ["local", "gemini", "openai", "claude", "deepseek"]
_LEGACY_OPENROUTER_MODELS = tuple(getattr(CORE, "OPENROUTER_MODELS", ["google/gemma-3-27b-it:free"]))
_LEGACY_LLM_CALL_ONCE = getattr(CORE, "_llm_call_once")


def normalize_provider(provider: str | None) -> str:
    provider = (provider or "gemini").strip().lower()
    if provider in {"local", "local_llm", "llama.cpp", "llama"}:
        return "local"
    return "deepseek" if provider == "openrouter" else provider


def normalize_model(provider: str | None, model: str | None) -> str:
    provider = normalize_provider(provider)
    model = (model or "").strip()
    if provider == "deepseek":
        if not model or model in _LEGACY_OPENROUTER_MODELS or ":free" in model or "/" in model:
            return DEEPSEEK_MODELS[0]
    if provider == "local":
        return LOCAL_MODELS[0]
    allowed = PROVIDER_MODELS.get(provider) if "PROVIDER_MODELS" in globals() else None
    if allowed and model and model not in allowed:
        # 未知型號時回落該供應商預設，避免設定頁卡住
        return allowed[0]
    return model or (allowed[0] if allowed else model)


def _guess_key_home_provider(api_key: str) -> str | None:
    key = (api_key or "").strip()
    if not key:
        return None
    if key.startswith("AQ.") or key.startswith("AIza"):
        return "gemini"
    if key.startswith("sk-ant"):
        return "claude"
    # sk- 可能是 OpenAI 或 DeepSeek，無法單靠前綴斷定
    return None


def ensure_provider_memory(cfg: dict) -> dict:
    """分開記住各供應商的 API Key 與上次選的模型。"""
    provider = normalize_provider(cfg.get("api_provider", "gemini"))
    keys = cfg.get("api_keys_by_provider")
    if not isinstance(keys, dict):
        keys = {}
    models = cfg.get("models_by_provider")
    if not isinstance(models, dict):
        models = {}

    # 正規化既有字典鍵
    keys = {normalize_provider(str(k)): str(v or "") for k, v in keys.items()}
    models = {normalize_provider(str(k)): str(v or "") for k, v in models.items()}

    legacy_key = str(cfg.get("api_key") or "").strip()
    if legacy_key:
        home = _guess_key_home_provider(legacy_key)
        if provider != "local":
            keys.setdefault(provider, legacy_key)
        if home:
            keys.setdefault(home, legacy_key)
        # 若目前是本機，仍把舊 key 掛到猜到的供應商，避免「換過去 key 空白」
        if provider == "local" and home:
            keys.setdefault(home, legacy_key)

    # 預設模型表在 PROVIDER_MODELS 定義之後才完整；此處用已知名單
    default_models = {
        "local": LOCAL_MODELS[0] if LOCAL_MODELS else "",
        "gemini": (GEMINI_MODELS[0] if GEMINI_MODELS else "gemini-3.6-flash"),
        "openai": (OPENAI_MODELS[0] if OPENAI_MODELS else "gpt-5.6-luna"),
        "claude": (CLAUDE_MODELS[0] if CLAUDE_MODELS else "claude-haiku-4-5"),
        "deepseek": DEEPSEEK_MODELS[0],
    }
    for name in PROVIDER_ORDER:
        keys.setdefault(name, "")
        models.setdefault(name, default_models.get(name, ""))
        models[name] = normalize_model(name, models.get(name) or default_models.get(name, ""))

    # 目前啟用的供應商／模型／key 寫回主欄位（相容舊程式路徑）
    cfg["api_provider"] = provider
    cfg["model"] = normalize_model(provider, models.get(provider) or cfg.get("model"))
    models[provider] = cfg["model"]
    if provider == "local":
        cfg["api_key"] = ""
    else:
        cfg["api_key"] = str(keys.get(provider) or "").strip()
        keys[provider] = cfg["api_key"]

    cfg["api_keys_by_provider"] = keys
    cfg["models_by_provider"] = models
    return cfg


def normalize_api_cfg(cfg: dict) -> dict:
    if not isinstance(cfg, dict):
        cfg = {}
    cfg = ensure_provider_memory(cfg)
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


def _default_project_id() -> str:
    if PERSONAL_RULES is not None:
        return str(getattr(PERSONAL_RULES, "DEFAULT_PROJECT_ID", "_default"))
    return "_default"


def _active_project_ids() -> tuple[str, str, str]:
    """回傳 (project_id, series_id, domain)。

    規則庫一律綁專案：未選專案時使用預設庫 id（_default）。
    """
    domain = "通用"
    project_id = _default_project_id()
    series_id = ""
    if PROJECT_PROFILES is not None:
        try:
            active = PROJECT_PROFILES.get_active()
            if active and active.get("id"):
                project_id = str(active.get("id") or project_id)
                series_id = str(active.get("series_id") or "")
                domain = str(active.get("domain") or domain)
        except Exception:
            pass
    if PERSONAL_RULES is not None and hasattr(PERSONAL_RULES, "normalize_project_id"):
        project_id = PERSONAL_RULES.normalize_project_id(project_id)
    return project_id, series_id, domain


def _active_project_label() -> str:
    """UI 顯示用專案名稱。"""
    if PROJECT_PROFILES is not None:
        try:
            active = PROJECT_PROFILES.get_active()
            if active and active.get("name"):
                return str(active.get("name"))
        except Exception:
            pass
    if PERSONAL_RULES is not None:
        return str(getattr(PERSONAL_RULES, "DEFAULT_PROJECT_LABEL", "預設（未選專案）"))
    return "預設（未選專案）"


def _learning_enabled() -> bool:
    return has_feature("learning_loop") or has_feature("custom_rules")


def record_review_feedback(
    *,
    action: str,
    original_text: str = "",
    ai_text: str = "",
    final_text: str = "",
    timecode_start: float | None = None,
    timecode_end: float | None = None,
    input_path: str = "",
    rule_ids: list[str] | None = None,
    source: str = "quick_compare",
) -> None:
    """寫入人工回饋事件（失敗靜默，不影響主流程）。"""
    if not _learning_enabled() or FEEDBACK_STORE is None:
        return
    try:
        project_id, series_id, domain = _active_project_ids()
        # 若設定有 personal_rules_domain 可覆寫
        try:
            cfg_domain = str((getattr(CORE, "load_config", lambda: {})() or {}).get("personal_rules_domain") or "")
        except Exception:
            cfg_domain = ""
        if cfg_domain:
            domain = cfg_domain
        FEEDBACK_STORE.record(
            action=action,
            original_text=original_text,
            ai_text=ai_text,
            final_text=final_text,
            timecode_start=timecode_start,
            timecode_end=timecode_end,
            input_path=input_path,
            project_id=project_id,
            series_id=series_id,
            domain=domain,
            rule_ids=rule_ids or [],
            provider=str((CORE.load_config() or {}).get("api_provider") or ""),
            model=str((CORE.load_config() or {}).get("model") or ""),
            app_version=APP_VERSION,
            source=source,
        )
    except Exception:
        pass


def _llm_call_once_with_deepseek(system: str, user_msg: str, cfg: dict) -> str:
    provider = normalize_provider(cfg.get("api_provider", "gemini"))
    model = normalize_model(provider, cfg.get("model"))
    segmentation_only = bool(cfg.get("_semantic_segmentation_pass", False))

    # ── 個人化規則 / 模板 / 詞庫 / 專案上下文注入 ───────────
    rules_section = ""
    rules_store = None
    rules_used: list[dict] = []
    project_id, series_id, profile_domain = _active_project_ids()
    domain = str(cfg.get("personal_rules_domain") or profile_domain or "通用")

    use_rules = (
        not segmentation_only
        and has_feature("custom_rules")
        and bool(cfg.get("use_personal_rules", True))
        and PERSONAL_RULES is not None
    )
    if use_rules:
        try:
            rules_store = PERSONAL_RULES.RuleStore(PERSONAL_RULES_PATH)
            rules_used = PERSONAL_RULES.select_rules_for_prompt(
                rules_store,
                domain=domain,
                project_id=project_id,
                series_id=series_id,
            )
            if rules_used:
                rules_section = PERSONAL_RULES.build_rules_section(rules_used)
                if rules_section:
                    system = (system or "") + "\n" + rules_section
        except Exception:
            rules_store = None
            rules_used = []

    # 領域 Prompt 模板（Supporter）
    if not segmentation_only and has_feature("domain_prompt_templates") and TEMPLATE_STORE is not None and bool(cfg.get("use_domain_prompt", True)):
        try:
            tpl_domain = str(cfg.get("prompt_template_domain") or domain)
            section = TEMPLATE_STORE.build_section(tpl_domain)
            if section:
                system = (system or "") + "\n" + section
        except Exception:
            pass

    # 自訂詞庫（Supporter）
    if not segmentation_only and has_feature("custom_dictionary") and DICTIONARY_STORE is not None and bool(cfg.get("use_custom_dictionary", True)):
        try:
            entries = DICTIONARY_STORE.select_for_prompt(
                project_id=project_id, series_id=series_id, domain=domain,
            )
            section = DICTIONARY_STORE.build_section(entries)
            if section:
                system = (system or "") + "\n" + section
        except Exception:
            pass

    # 專案上下文
    if not segmentation_only and has_feature("project_profiles") and PROJECT_PROFILES is not None and bool(cfg.get("use_project_context", True)):
        try:
            ctx = PROJECT_PROFILES.context_for_prompt()
            if ctx:
                system = (system or "") + "\n" + ctx
        except Exception:
            pass

    if not segmentation_only:
        system = (system or "") + (
            "\n\n【校正規則衝突優先序】若不同來源的指示互相衝突，必須依序採用："
            "1. 本次補充資料；2. 目前專案的個人化規則、詞庫與專案資料；"
            "3. 總編輯 Prompt；4. 基礎 AI 校正預設。低優先來源不得覆蓋高優先來源。"
        )

    if provider == "local":
        if LOCAL_LLM is None:
            raise RuntimeError("本地 AI 模組不存在，請重新安裝 SanWich。")
        endpoint = LOCAL_LLM.MANAGER.ensure_running()
        result = CORE._post_json(
            f"{endpoint}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            payload={
                "model": getattr(LOCAL_LLM, "LOCAL_MODEL_ALIAS", "breeze-local"),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.2,
                "max_tokens": 4096,
                "stream": False,
            },
            timeout=600,
        )
        try:
            response_text = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"本地 AI 回應格式異常：{result}") from exc
    elif provider == "deepseek":
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

    # 只記模型遵循度，不冒充人類採納
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
OPENAI_MODELS = getattr(CORE, "OPENAI_MODELS", ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"])
CLAUDE_MODELS = getattr(CORE, "CLAUDE_MODELS", ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8", "claude-fable-5"])
GEMINI_MODELS = getattr(
    CORE,
    "GEMINI_MODELS",
    ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"],
)

PROVIDER_MODELS = {
    "local": LOCAL_MODELS,
    "gemini": GEMINI_MODELS,
    "openai": OPENAI_MODELS,
    "claude": CLAUDE_MODELS,
    "deepseek": DEEPSEEK_MODELS,
}

PROVIDER_LABELS = {
    "local": "本機私密 AI",
    "gemini": "Google Gemini",
    "openai": "OpenAI",
    "claude": "Claude",
    "deepseek": "DeepSeek",
}

PROVIDER_HINTS = {
    "local": "字幕校對只在這台電腦執行，不需 API Key；首次使用需下載約 5GB 模型與 llama.cpp 執行核心。",
    "gemini": "速度快，字幕校對建議先用 Gemini 3.6 Flash；要壓低成本可選 Flash-Lite。",
    "openai": "GPT-5.6 Luna 成本較低；Terra 平衡品質與價格；Sol 適合高要求內容。",
    "claude": "Haiku 最省；Sonnet 兼顧速度與品質；Opus／Fable 適合高難度長文。",
    "deepseek": "OpenAI 相容格式，接法簡單，建議優先使用 deepseek-v4-flash。",
}

PROVIDER_SITES = {
    "local": ("下載／檢查本地 AI", ""),
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


def strip_chunks_for_srt_display(chunks: list[dict]) -> list[dict]:
    """SRT 一律無標點：編輯器顯示與匯入／匯出保持一致。"""
    copied = clone_chunks(chunks)
    for chunk in copied:
        chunk["text"] = CORE.strip_punct_for_srt(chunk.get("text") or "")
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
    return peaks, duration


def _preview_cache_dir() -> Path:
    return user_data_dir() / "cache" / "audio_preview"


def _prune_preview_cache(cache_dir: Path, keep_stem: str = "", max_bytes: int = 8 * 1024**3) -> None:
    """Keep preview proxies bounded without touching the currently opened source."""
    try:
        wavs = sorted(cache_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime)
        total = sum(path.stat().st_size for path in wavs)
        now = _dt.datetime.now().timestamp()
        for path in wavs:
            if path.stem == keep_stem:
                continue
            too_old = now - path.stat().st_mtime > 45 * 86400
            if total <= max_bytes and not too_old:
                continue
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            path.with_suffix(".json").unlink(missing_ok=True)
            total -= size
    except Exception:
        pass


def build_waveform_proxy(media_path: str, target_peaks: int = 6000, keep_proxy: bool = True) -> tuple[list[float], float, str | None]:
    source = Path(media_path) if media_path else Path()
    if not media_path or not source.exists():
        return [], 0.0, None
    ffmpeg = CORE.find_ffmpeg()
    if not ffmpeg:
        return [], 0.0, None
    cache_key = ""
    cache_wav = None
    cache_meta = None
    if keep_proxy:
        try:
            stat = source.stat()
            identity = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{target_peaks}|pcm16k-v2"
            cache_key = hashlib.sha256(identity.encode("utf-8", errors="surrogatepass")).hexdigest()[:24]
            cache_dir = _preview_cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_wav = cache_dir / f"{cache_key}.wav"
            cache_meta = cache_dir / f"{cache_key}.json"
            if cache_wav.exists() and cache_meta.exists():
                payload = json.loads(cache_meta.read_text(encoding="utf-8"))
                peaks = [float(v) for v in payload.get("peaks", [])]
                duration = float(payload.get("duration", 0.0) or 0.0)
                if peaks and duration > 0:
                    cache_wav.touch()
                    cache_meta.touch()
                    return peaks, duration, str(cache_wav)
        except Exception:
            cache_key = ""
            cache_wav = None
            cache_meta = None

    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".wav",
        dir=str(cache_wav.parent) if cache_wav is not None else None,
    )
    tmp.close()
    tmp_path = Path(tmp.name)
    moved_to_cache = False
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
            bucket = max(1, frame_count // max(1, target_peaks))
            # 逐桶讀取，避免長訪談一次把整支 PCM 載入記憶體。
            levels: list[float] = []
            remaining = frame_count
            while remaining > 0:
                count = min(bucket, remaining)
                samples = array("h")
                samples.frombytes(wav.readframes(count))
                if sys.byteorder == "big":
                    samples.byteswap()
                if not samples:
                    break
                stride = max(1, len(samples) // 384)
                values = [abs(samples[j]) for j in range(0, len(samples), stride)]
                levels.append(sum(values) / len(values) if values else 0.0)
                remaining -= count
        ordered = sorted(levels)
        if not ordered:
            return [], duration, str(tmp_path) if keep_proxy else None
        floor = ordered[min(len(ordered) - 1, int(len(ordered) * 0.05))] * 0.65
        reference = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        span = max(1.0, reference - floor)
        peaks = [max(0.0, min(1.0, (level - floor) / span)) for level in levels]
        if keep_proxy and cache_wav is not None and cache_meta is not None:
            os.replace(tmp_path, cache_wav)
            moved_to_cache = True
            meta_tmp = cache_meta.with_suffix(".json.tmp")
            meta_tmp.write_text(
                json.dumps({"duration": duration, "peaks": peaks}, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(meta_tmp, cache_meta)
            _prune_preview_cache(cache_wav.parent, keep_stem=cache_wav.stem)
            return peaks, duration, str(cache_wav)
        return peaks, duration, None
    except Exception:
        return [], 0.0, None
    finally:
        if not moved_to_cache:
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
        # v2 舊預設曾把 15 寫進使用者設定，會遮蔽新版的 11 字語意目標。
        # 只遷移空白／舊預設值；使用者自行指定的其它數值完整保留。
        try:
            segmentation_version = int(self.cfg.get("segmentation_rules_version", 0) or 0)
        except Exception:
            segmentation_version = 0
        if segmentation_version < 3:
            old_target = self.cfg.get("srt_max_chars_per_line", "")
            if old_target in (None, "", 0, "0", 11, "11", 15, "15"):
                self.cfg["srt_max_chars_per_line"] = ""
            self.cfg["segmentation_rules_version"] = 3
            CORE.save_config(self.cfg)
        self.input_files: list[str] = []
        self.pipeline = None
        self.cancel_event = threading.Event()
        self.last_compare: dict | None = None
        self.batch_compares: dict = {}
        self.last_result: dict | None = None
        self.batch_results: list[dict] = []
        self.editor_index: int | None = None
        self.preview_process: subprocess.Popen | None = None
        self.preview_player = None
        if AUDIO_PREVIEW is not None:
            try:
                candidate = AUDIO_PREVIEW.AudioPreviewPlayer(latency=0.03, blocksize=256)
                if candidate.available():
                    self.preview_player = candidate
            except Exception:
                self.preview_player = None
        self.notes_placeholder = True
        # 專案列：有明確選過專案就預設收合成細長條
        self.project_bar_expanded = True
        try:
            if PROJECT_PROFILES is not None and PROJECT_PROFILES.get_active():
                self.project_bar_expanded = False
        except Exception:
            self.project_bar_expanded = True

        self.ai_enabled = ctk.BooleanVar(value=bool(self.cfg.get("use_llm", False)))
        self.editor_enabled = ctk.BooleanVar(value=bool(self.cfg.get("use_text_fix", False)))
        self.srt_enabled = ctk.BooleanVar(value=bool(self.cfg.get("output_srt_enabled", True)))
        self.txt_enabled = ctk.BooleanVar(value=bool(self.cfg.get("output_txt_enabled", True)))
        self.diarize_enabled = ctk.BooleanVar(value=bool(self.cfg.get("txt_diarization_enabled", False)))
        self.srt_diarize_enabled = ctk.BooleanVar(value=bool(self.cfg.get("srt_diarization_enabled", False)))
        _diar_n = int(self.cfg.get("diarization_num_speakers", 3) or 3)
        self.diar_speakers = ctk.StringVar(value=f"{max(2, min(6, _diar_n))} 人")
        # 選填：空字串＝用預設；有填才覆寫
        _raw_max = self.cfg.get("srt_max_chars_per_line", "")
        if _raw_max in (None, "", 0, "0"):
            self.srt_max_chars = ctk.StringVar(value="")
        else:
            try:
                self.srt_max_chars = ctk.StringVar(value=str(int(_raw_max)))
            except Exception:
                self.srt_max_chars = ctk.StringVar(value="")
        self.input_path = ctk.StringVar(value="")
        self.output_srt_path = ctk.StringVar(value="")
        self.output_txt_path = ctk.StringVar(value="")
        self.status_text = ctk.StringVar(value="待命")
        self._job_timer_t0 = None

        self.build()
        self.enable_drop_targets()
        self.log("主版已啟動。內部核心以唯讀方式載入。", "success")
        self.log(f"版本 v{APP_VERSION}｜學習資料目錄：{user_data_dir() / 'learning'}", "model")
        if not _HAS_DND:
            self.log("拖放套件未載入；仍可使用「選擇檔案」。", "warn")
        self.after(650, self.show_previous_update_result)
        self.after(1400, self.check_for_updates_async)
        # 依授權快取的重驗週期連線；不在每次啟動時重複呼叫 API。
        self.after(2400, self.refresh_license_if_due_async)

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

    def show_previous_update_result(self):
        path = local_data_dir() / "update_result.json"
        if not path.exists():
            return
        try:
            result = json.loads(path.read_text(encoding="utf-8-sig"))
            path.unlink(missing_ok=True)
        except Exception:
            return
        if result.get("status") == "success":
            version = str(result.get("version") or APP_VERSION)
            messagebox.showinfo("更新完成", f"SanWich v{version} 已更新完成。\n\nAPI Key、個人設定與授權資料均已保留。", parent=self)
        elif result.get("status") == "failed":
            messagebox.showerror("更新失敗", "更新沒有套用，程式已保留或復原原版本。\n\n請改用完整安裝包更新。", parent=self)

    def check_for_updates_async(self, notify_if_current: bool = False):
        def worker():
            try:
                release = fetch_latest_release()
                latest = str(release.get("tag_name") or "")
                if is_newer_version(latest):
                    self.after(0, lambda: self.show_update_notice(release))
                elif notify_if_current:
                    self.after(0, lambda: messagebox.showinfo("檢查更新", f"目前已是最新版 v{APP_VERSION}。", parent=self))
            except Exception:
                if notify_if_current:
                    self.after(0, lambda: messagebox.showerror("無法檢查更新", "目前無法連線更新伺服器，請稍後再試。", parent=self))

        threading.Thread(target=worker, daemon=True).start()

    def show_update_notice(self, release: dict):
        latest = str(release.get("tag_name") or "").strip()
        url = str(release.get("html_url") or GITHUB_RELEASES_URL)
        asset = UPDATER.select_update_asset(release) if UPDATER is not None else None
        packaged_layout = here().name.lower() == "app" and (here() / "update_helper.ps1").is_file()
        can_install = bool(asset and packaged_layout and sys.platform.startswith("win"))
        action_text = "是否立即下載並自動更新？" if can_install else "此版本需要使用完整安裝包更新，是否前往下載頁？"
        should_update = messagebox.askyesno(
            "發現新版本",
            f"SanWich {latest} 已經發佈。\n\n"
            f"目前版本：v{APP_VERSION}\n\n"
            "更新不會重設授權時間，也不會覆寫 API 設定或個人化規則庫。\n"
            f"{action_text}",
            parent=self,
        )
        if not should_update:
            return
        if can_install:
            self.install_update_async(asset, latest)
        else:
            webbrowser.open_new_tab(url)

    def install_update_async(self, asset: dict, latest: str):
        self.status_text.set(f"正在下載 SanWich {latest} 更新…")
        self.log(f"開始下載更新 {asset['name']}。", "model")

        def progress(received: int, total: int):
            percent = min(100, int(received * 100 / max(total, 1)))
            self.after(0, lambda: self.status_text.set(f"正在下載更新… {percent}%"))

        def worker():
            try:
                package = UPDATER.download_verified_asset(asset, progress=progress)
                helper = here() / "update_helper.ps1"
                relaunch = here() / "run_hidden.vbs"
                if not relaunch.exists():
                    relaunch = here() / "run_app.bat"
                UPDATER.launch_installer(
                    package,
                    helper_path=helper,
                    install_root=here().parent,
                    relaunch_path=relaunch,
                    result_path=local_data_dir() / "update_result.json",
                )
                self.after(0, self._close_for_update)
            except Exception as error:
                detail = str(error)
                self.after(0, lambda detail=detail: self._show_update_error(detail))

        threading.Thread(target=worker, daemon=True).start()

    def _close_for_update(self):
        self.status_text.set("更新已下載，正在重新啟動…")
        self.log("更新檔驗證通過，SanWich 將關閉並套用更新。", "success")
        self.after(250, self.destroy)

    def _show_update_error(self, _detail: str):
        self.status_text.set("更新失敗；目前版本未變更")
        self.log("更新下載或驗證失敗，未變更現有程式。", "error")
        messagebox.showerror("更新失敗", "無法安全完成更新，現有版本未被修改。\n\n請稍後重試，或使用完整安裝包。", parent=self)

    def refresh_license_if_due_async(self, *, force: bool = False, always_online: bool = False, callback=None):
        if LICENSE_MANAGER is None or getattr(LICENSE_MANAGER, "server_service", None) is None:
            if force:
                messagebox.showerror("無法驗證", "線上授權服務尚未設定完成。", parent=self)
            return
        service = LICENSE_MANAGER.server_service
        if not service.has_cached_license():
            if force:
                messagebox.showinfo("尚未啟用", "這台電腦目前沒有需要重新驗證的完整版授權。", parent=self)
            return
        try:
            due = service.offline_state().get("mode") == "grace"
        except Exception:
            due = True
        if not force and not always_online and not due:
            return

        def worker():
            ok = LICENSE_MANAGER.refresh_server_license()
            self.after(0, lambda: self._finish_license_refresh(ok, force, callback))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_license_refresh(self, ok: bool, show_message: bool, callback=None):
        if callback:
            callback()
        if ok:
            self.log("完整版授權已完成線上驗證。", "success")
            if show_message:
                messagebox.showinfo("驗證完成", "完整版授權已更新，可以繼續離線使用。", parent=self)
        else:
            self.log("目前無法完成完整版線上驗證；基本功能不受影響。", "warn")
            if show_message:
                messagebox.showerror("驗證失敗", "目前無法完成線上驗證，請確認網路後再試。\n\n基本功能不受影響。", parent=self)

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

        self.project_step_bar(content)
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

    def project_step_bar(self, parent):
        """第 0 步：專案。全寬矮列；選完可收成細長條。"""
        self._project_bar_parent = parent
        bar = ctk.CTkFrame(
            parent,
            fg_color="#1A2426",
            corner_radius=12,
            border_width=1,
            border_color=TEAL_2,
        )
        # 橫跨左欄到步驟 3（AI 卡）整寬
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 8))
        bar.grid_columnconfigure(0, weight=1)
        self.project_bar = bar

        # ── 展開：矮一點的說明列 ─────────────────────────
        self.project_bar_expanded_frame = ctk.CTkFrame(bar, fg_color="transparent")
        self.project_bar_expanded_frame.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            self.project_bar_expanded_frame,
            text="0.",
            text_color=TEAL_2,
            font=(EN_FONT, 16, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(12, 4), pady=6)
        ctk.CTkLabel(
            self.project_bar_expanded_frame,
            text="專案",
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
        ).grid(row=0, column=1, sticky="w", padx=(0, 8), pady=6)

        self.project_btn = ctk.CTkButton(
            self.project_bar_expanded_frame,
            text=self._project_button_label(),
            width=280,
            height=28,
            corner_radius=14,
            fg_color="#24383A",
            hover_color="#2F4A4C",
            text_color="#D8EEEE",
            font=(FONT, 12, "bold"),
            border_width=1,
            border_color=TEAL_2,
            command=self.open_project_profiles_window,
            anchor="w",
        )
        self.project_btn.grid(row=0, column=2, sticky="w", pady=6)

        ctk.CTkLabel(
            self.project_bar_expanded_frame,
            text="可依照專案記憶不同組，個人化規則庫及 AI 校正提示詞資料。",
            text_color="#8AA3A5",
            font=(FONT, 11),
            anchor="w",
            justify="left",
        ).grid(row=0, column=3, sticky="ew", padx=(12, 8), pady=6)

        ctk.CTkButton(
            self.project_bar_expanded_frame,
            text="收合",
            width=52,
            height=26,
            corner_radius=10,
            fg_color="transparent",
            hover_color="#2A383A",
            text_color="#8AA3A5",
            font=(FONT, 11),
            border_width=1,
            border_color="#3A5558",
            command=lambda: self.set_project_bar_expanded(False),
        ).grid(row=0, column=4, sticky="e", padx=(0, 10), pady=6)

        # ── 收合：小小一條長框 ───────────────────────────
        self.project_bar_collapsed_frame = ctk.CTkFrame(bar, fg_color="transparent")
        self.project_bar_collapsed_frame.grid_columnconfigure(1, weight=1)

        self.project_strip_label = ctk.CTkLabel(
            self.project_bar_collapsed_frame,
            text=self._project_strip_text(),
            text_color="#C5DDDF",
            font=(FONT, 12, "bold"),
            anchor="w",
            cursor="hand2",
        )
        self.project_strip_label.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=3)
        self.project_strip_label.bind("<Button-1>", lambda _e: self.open_project_profiles_window())
        # 整條也可點
        self.project_bar_collapsed_frame.bind("<Button-1>", lambda _e: self.open_project_profiles_window())

        ctk.CTkButton(
            self.project_bar_collapsed_frame,
            text="展開",
            width=48,
            height=22,
            corner_radius=8,
            fg_color="transparent",
            hover_color="#2A383A",
            text_color="#8AA3A5",
            font=(FONT, 11),
            border_width=0,
            command=lambda: self.set_project_bar_expanded(True),
        ).grid(row=0, column=2, sticky="e", padx=(0, 8), pady=2)

        self.set_project_bar_expanded(self.project_bar_expanded)

    def set_project_bar_expanded(self, expanded: bool):
        self.project_bar_expanded = bool(expanded)
        try:
            self.project_bar_expanded_frame.grid_forget()
            self.project_bar_collapsed_frame.grid_forget()
        except Exception:
            pass
        if self.project_bar_expanded:
            self.project_bar_expanded_frame.grid(row=0, column=0, sticky="ew")
            try:
                self.project_btn.configure(text=self._project_button_label())
            except Exception:
                pass
        else:
            self.project_bar_collapsed_frame.grid(row=0, column=0, sticky="ew")
            try:
                self.project_strip_label.configure(text=self._project_strip_text())
            except Exception:
                pass

    def _project_strip_text(self) -> str:
        return f"0. 專案　{self._project_button_label()}　·　點此切換"

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
        card.grid(row=1, column=0, sticky="nsew", padx=(0, 14), pady=(0, 14))
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
        btn_row = tk.Frame(card.body, bg=card.body.cget("bg"), highlightthickness=0, bd=0)
        btn_row.grid(row=3, column=0, sticky="w", pady=(16, 0))
        ctk.CTkButton(
            btn_row,
            text="選擇檔案",
            width=148,
            height=50,
            corner_radius=18,
            fg_color=ORANGE,
            hover_color=ORANGE_DARK,
            text_color="#FFFFFF",
            font=(FONT, 16, "bold"),
            command=self.choose_input,
        ).pack(side="left")
        ctk.CTkButton(
            btn_row,
            text="開啟外部 SRT",
            width=148,
            height=50,
            corner_radius=18,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 14, "bold"),
            command=self.open_external_srt,
        ).pack(side="left", padx=(10, 0))

    def output_card(self, parent):
        card = Card(
            parent,
            "輸出格式",
            step="2",
            hint="路徑可手動改或靠原檔名自動產生。顯示語者需 Supporter；首次會下載離線模型。",
            hint_outside=True,
            hint_color=TEXT_ON_DARK,
            hint_tip_fg=SNOW,
            hint_tip_text_color=DARK,
            fg_color=CARD,
            corner_radius=23,
        )
        card.grid(row=2, column=0, sticky="nsew", padx=(0, 14), pady=(0, 14))
        card.body.grid_columnconfigure(1, weight=1)
        # 顯示語者分別跟在「SRT 字幕」「純文字」後面；另存為方便改輸出位置
        self.output_option(
            card.body, 0, "SRT 字幕", "SRT 輸出路徑（可留空自動命名）",
            self.srt_enabled, self.output_srt_path, self.choose_srt,
            speaker_var=self.srt_diarize_enabled, speaker_cmd=self.on_srt_diarize_toggle,
        )
        self.output_option(
            card.body, 1, "純文字", "純文字輸出路徑（可留空自動命名）",
            self.txt_enabled, self.output_txt_path, self.choose_txt,
            speaker_var=self.diarize_enabled, speaker_cmd=self.on_diarize_toggle,
        )
        opts = tk.Frame(card.body, bg=card.body.cget("bg"), highlightthickness=0, bd=0)
        opts.grid(row=2, column=0, columnspan=4, sticky="w", pady=(12, 0))
        ctk.CTkLabel(opts, text="語者人數", text_color=MUTED_ON_DARK, font=(FONT, 13)).pack(side="left")
        InfoBubble(
            opts,
            "開啟任一邊「顯示語者」時使用。請選實際講者人數；不確定時寧可多 1 個。\n"
            "SRT：字幕前加講者標籤，時間碼不變。純文字：講者A／講者B 分段。",
            text_color=MUTED_ON_DARK, tip_fg=SNOW, tip_text_color=DARK,
        ).pack(side="left", padx=(4, 6))
        ctk.CTkOptionMenu(
            opts, values=["2 人", "3 人", "4 人", "5 人", "6 人"],
            variable=self.diar_speakers, command=lambda _v: self.persist_basic_config(),
            width=92, height=30, corner_radius=11,
            fg_color=DARK_2, button_color=ORANGE, button_hover_color=ORANGE_DARK,
            text_color=TEXT_ON_DARK, font=(FONT, 13),
            dropdown_font=(FONT, 13), dropdown_fg_color=CARD, dropdown_text_color=TEXT_ON_DARK,
        ).pack(side="left")
        ctk.CTkLabel(opts, text="SRT 每句目標字數", text_color=MUTED_ON_DARK, font=(FONT, 13)).pack(
            side="left", padx=(18, 6)
        )
        InfoBubble(
            opts,
            "選填。系統會以此為一般閱讀節奏目標；遇到未完成語意時可柔性延長。\n"
            "留空＝系統預設 13；建議 10–18 字。",
            text_color=MUTED_ON_DARK, tip_fg=SNOW, tip_text_color=DARK,
        ).pack(side="left", padx=(0, 6))
        max_entry = ctk.CTkEntry(
            opts,
            textvariable=self.srt_max_chars,
            width=108,
            height=30,
            corner_radius=11,
            fg_color=DARK_2,
            border_color=LINE,
            text_color=TEXT_ON_DARK,
            placeholder_text="建議 10-18 字",
            placeholder_text_color=PLACEHOLDER,
            font=(FONT, 12),
            justify="center",
        )
        max_entry.pack(side="left")
        max_entry.bind("<FocusOut>", lambda _e: self.persist_basic_config())
        max_entry.bind("<Return>", lambda _e: self.persist_basic_config())

    def output_option(
        self,
        parent,
        row,
        title,
        placeholder,
        var,
        path_var,
        open_cmd,
        *,
        speaker_var=None,
        speaker_cmd=None,
    ):
        pad = (0, 12) if row == 0 else (0, 0)
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
        ).grid(row=row, column=0, sticky="w", pady=pad)
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
        ).grid(row=row, column=1, sticky="ew", padx=(10, 8), pady=pad)
        ctk.CTkButton(
            parent,
            text="另存為...",
            width=100,
            height=36,
            corner_radius=14,
            fg_color="#1a1919",
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 12, "bold"),
            command=open_cmd,
        ).grid(row=row, column=2, sticky="e", pady=pad)
        if speaker_var is not None:
            ctk.CTkCheckBox(
                parent,
                text="顯示語者",
                variable=speaker_var,
                command=speaker_cmd or self.persist_basic_config,
                fg_color=ORANGE,
                hover_color=ORANGE_DARK,
                checkmark_color="#FFFFFF",
                text_color=TEXT_ON_DARK,
                font=(FONT, 13, "bold"),
                checkbox_width=22,
                checkbox_height=22,
                corner_radius=5,
                border_width=2,
            ).grid(row=row, column=3, sticky="w", padx=(10, 0), pady=pad)

    def ai_card(self, parent):
        card = Card(
            parent,
            "",
            step="3",
            hint="補充資料可貼整份口播腳本（類似剪映文檔匹配），或短詞庫／「錯 > 對」。腳本會在校對後本機對齊覆寫。",
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
        # 與步驟 1＋2 對齊（專案第 0 步僅左側）
        card.grid(row=1, column=1, rowspan=2, sticky="nsew", pady=(0, 14))
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
        notes_head = ctk.CTkFrame(card.body, fg_color="transparent")
        notes_head.grid(row=4, column=0, sticky="ew", pady=(28, 8))
        notes_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            notes_head, text="補充資料", text_color=TEXT_ON_DARK, font=(FONT, 17, "bold")
        ).grid(row=0, column=0, sticky="w")
        self.notes_history_var = ctk.StringVar(value="選擇記憶")
        self.notes_history_menu = ctk.CTkOptionMenu(
            notes_head,
            values=["尚無記憶"],
            variable=self.notes_history_var,
            command=self.on_notes_history_select,
            width=196,
            height=30,
            corner_radius=11,
            fg_color=DARK_2,
            button_color="#343A43",
            button_hover_color=GARNET,
            text_color=MUTED_ON_DARK,
            font=(FONT, 11),
            dropdown_font=(FONT, 11),
            dropdown_fg_color=DARK_2,
            dropdown_hover_color=GARNET,
            dropdown_text_color=TEXT_ON_DARK,
            dynamic_resizing=False,
            anchor="w",
        )
        self.notes_history_menu.grid(row=0, column=1, sticky="e")
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
        self.refresh_notes_history_menu()

    def action_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=CARD_DARK, corner_radius=26, border_width=0, border_color="#0C0D12", height=214)
        card.grid(row=3, column=0, sticky="nsew", padx=(0, 14), pady=(6, 14))
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
        card.grid(row=3, column=1, sticky="nsew", pady=(6, 14))
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
        ctk.CTkButton(
            row,
            text="外部 SRT",
            width=100,
            height=40,
            corner_radius=14,
            fg_color=DARK,
            hover_color=GARNET,
            text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"),
            command=self.open_external_srt,
        ).pack(side="left", padx=(8, 0))
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
        card.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(0, 14))
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
        text = (
            "用法一｜整份腳本：\n"
            "直接貼上完整口播逐字稿…\n\n"
            "用法二｜短詞庫：\n"
            "葉黃素\n"
            "玻尿酸\n"
            "夜黃素 > 葉黃素"
        )

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

    def refresh_notes_history_menu(self):
        if not hasattr(self, "notes_history_menu"):
            return
        self._notes_history_choices = {}
        values = []
        project_id, _series_id, _domain = _active_project_ids()
        entries = list(
            SUPPLEMENT_HISTORY_STORE.entries_for_project(project_id)
            if SUPPLEMENT_HISTORY_STORE is not None
            and hasattr(SUPPLEMENT_HISTORY_STORE, "entries_for_project")
            else []
        )
        for index, entry in enumerate(entries, 1):
            summary = " ".join(str(entry.get("text") or "").split())
            if len(summary) > 24:
                summary = summary[:24] + "…"
            project_name = str(entry.get("project_name") or "預設").strip() or "預設"
            if len(project_name) > 12:
                project_name = project_name[:12] + "…"
            label = f"{project_name}｜{summary}"
            if label in self._notes_history_choices:
                label = f"{label}（{index}）"
            values.append(label)
            self._notes_history_choices[label] = entry
        if entries:
            values.append("清除目前專案記憶")
            display = "選擇記憶"
        else:
            values = ["尚無記憶"]
            display = "尚無記憶"
        self.notes_history_menu.configure(values=values)
        self.notes_history_var.set(display)

    def on_notes_history_select(self, value: str):
        if value == "清除目前專案記憶":
            project_id, _series_id, _domain = _active_project_ids()
            if messagebox.askyesno("清除補充資料記憶", "確定清除目前專案的補充資料記憶？", parent=self):
                try:
                    SUPPLEMENT_HISTORY_STORE.clear(project_id)
                    self.log("目前專案的補充資料記憶已清除。", "success")
                except Exception as exc:
                    messagebox.showerror("清除失敗", str(exc), parent=self)
            self.refresh_notes_history_menu()
            return
        entry = getattr(self, "_notes_history_choices", {}).get(value)
        if entry is None:
            self.refresh_notes_history_menu()
            return
        self.notes_box.delete("1.0", "end")
        self.notes_box.configure(text_color=TEXT_ON_DARK)
        self.notes_box.insert("1.0", str(entry.get("text") or ""))
        self.notes_placeholder = False
        self.notes_history_var.set("選擇記憶")

    def remember_supplement_notes(self, text: str):
        if not text or SUPPLEMENT_HISTORY_STORE is None:
            return
        try:
            project_id, _series_id, _domain = _active_project_ids()
            SUPPLEMENT_HISTORY_STORE.remember(
                text,
                project_id=project_id,
                project_name=_active_project_label(),
            )
            self.refresh_notes_history_menu()
        except Exception as exc:
            self.log(f"補充資料記憶寫入失敗：{exc}", "warn")

    def persist_basic_config(self):
        self.cfg["use_llm"] = bool(self.ai_enabled.get())
        self.cfg["use_text_fix"] = bool(self.editor_enabled.get())
        self.cfg["output_srt_enabled"] = bool(self.srt_enabled.get())
        self.cfg["output_txt_enabled"] = bool(self.txt_enabled.get())
        self.cfg["txt_diarization_enabled"] = bool(self.diarize_enabled.get())
        self.cfg["srt_diarization_enabled"] = bool(self.srt_diarize_enabled.get())
        try:
            _sel = self.diar_speakers.get()
            self.cfg["diarization_num_speakers"] = int(_sel.split()[0])
        except Exception:
            self.cfg["diarization_num_speakers"] = 3
        raw = (self.srt_max_chars.get() or "").strip()
        if not raw:
            # 選填：空＝不寫死、執行時用預設
            self.cfg["srt_max_chars_per_line"] = ""
        else:
            try:
                self.cfg["srt_max_chars_per_line"] = max(5, min(40, int(raw)))
                self.srt_max_chars.set(str(self.cfg["srt_max_chars_per_line"]))
            except Exception:
                # 非法輸入還原為空（選填）
                self.srt_max_chars.set("")
                self.cfg["srt_max_chars_per_line"] = ""
        CORE.save_config(self.cfg)

    def srt_max_line_width(self) -> float:
        """選填目標字數；空白或無效時回核心目前的語意斷句預設。"""
        raw = ""
        try:
            raw = (self.srt_max_chars.get() or "").strip()
        except Exception:
            raw = str(self.cfg.get("srt_max_chars_per_line") or "").strip()
        if not raw:
            return float(getattr(CORE, "SRT_TARGET_LINE_WIDTH", 13.0))
        try:
            return float(max(5, min(40, int(raw))))
        except Exception:
            return float(getattr(CORE, "SRT_TARGET_LINE_WIDTH", 13.0))

    def write_srt_output(self, path: str, chunks: list[dict], preserve_segments: bool = False) -> None:
        rendered = (
            CORE.chunks_to_srt_preserving_segments(chunks)
            if preserve_segments
            else CORE.chunks_to_srt(chunks, max_line_width=self.srt_max_line_width())
        )
        Path(path).write_text(
            rendered,
            encoding="utf-8-sig",
        )

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

    def on_srt_diarize_toggle(self):
        """SRT 顯示語者：需語者分離權限；不必連動打開純文字語者。"""
        if self.srt_diarize_enabled.get() and not has_feature("diarization"):
            self.srt_diarize_enabled.set(False)
            self.show_supporter_message("diarization")
            return
        self.persist_basic_config()

    def show_supporter_message(self, feature_name: str):
        """完整版功能提示：基本功能仍可用，提供啟用或購買說明。"""
        label = SUPPORTER_FEATURE_LABELS.get(feature_name, feature_name)
        status = license_status_summary()
        if status["mode"] == "trial":
            status_line = (
                f"你正在使用完整版試用，到期日：{status['trial_ends_at']}。\n"
                "試用結束後，SanWich 會回到基本功能，核心工作仍可繼續。"
            )
        elif status["mode"] == "grace":
            status_line = (
                "完整版需要重新驗證，但目前仍在離線寬限期內。\n"
                "請連線一次完成驗證；基本功能不受影響。"
            )
        else:
            status_line = (
                "目前是基本功能模式；SanWich 的核心單檔工作仍可繼續。\n"
                "如果 SanWich 幫你省下時間，歡迎購買完整版支持開發。"
            )

        win = ctk.CTkToplevel(self)
        win.title(f"{label}｜完整版功能")
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
                f"{label}是完整版功能。\n"
                "SanWich 基本功能仍可完成單檔字幕工作（辨識、校對、輸出、編輯）。\n\n"
                f"{status_line}\n\n"
                "啟用完整版可解鎖批次處理、快速對照、個人化規則庫與語者分離。"
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

        ctk.CTkLabel(outer, text="AI 校對設定", text_color=TEXT_ON_DARK, font=(FONT, 26, "bold")).grid(
            row=0, column=0, sticky="w", padx=24, pady=(22, 6)
        )
        ctk.CTkLabel(
            outer,
            text="選擇本機私密 AI 時字幕不離開電腦；選擇雲端供應商時，字幕文字才會傳送至該供應商。",
            text_color=MUTED_ON_DARK,
            font=(FONT, 13),
        ).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 18))

        self.cfg = ensure_provider_memory(self.cfg)
        start_provider = normalize_provider(self.cfg.get("api_provider", "gemini"))
        start_models = PROVIDER_MODELS.get(start_provider, GEMINI_MODELS)
        start_model = normalize_model(
            start_provider,
            (self.cfg.get("models_by_provider") or {}).get(start_provider) or self.cfg.get("model"),
        )
        if start_model not in start_models:
            start_model = start_models[0]
        start_key = ""
        if start_provider != "local":
            start_key = str((self.cfg.get("api_keys_by_provider") or {}).get(start_provider) or self.cfg.get("api_key") or "")

        provider_var = ctk.StringVar(value=start_provider)
        model_var = ctk.StringVar(value=start_model)
        key_var = ctk.StringVar(value=start_key)
        show_key = ctk.BooleanVar(value=False)
        state = {"provider": start_provider, "applying": False}

        provider = ctk.CTkSegmentedButton(
            outer,
            values=list(PROVIDER_ORDER),
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
            values=start_models,
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

        key_label = ctk.CTkLabel(outer, text="API Key", text_color=TEXT_ON_DARK, font=(FONT, 14, "bold"))
        key_label.grid(
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

        show_key_checkbox = ctk.CTkCheckBox(
            key_row,
            text="顯示",
            variable=show_key,
            command=toggle_key,
            fg_color=ORANGE,
            hover_color=ORANGE_DARK,
            font=(FONT, 13),
        )
        show_key_checkbox.grid(row=0, column=1, sticky="e", padx=(12, 0))

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

        local_status_label = ctk.CTkLabel(
            outer,
            text="",
            text_color=MUTED_ON_DARK,
            font=(FONT, 12),
            anchor="w",
            justify="left",
        )
        local_status_label.grid(row=9, column=0, sticky="ew", padx=24, pady=(0, 8))

        memory_hint = ctk.CTkLabel(
            outer,
            text="各供應商的 API Key 與模型會分開記住；切換供應商會自動帶入，關閉視窗也會儲存。",
            text_color=MUTED_ON_DARK,
            font=(FONT, 12),
            anchor="w",
            justify="left",
        )
        memory_hint.grid(row=10, column=0, sticky="ew", padx=24, pady=(0, 4))

        def start_local_download():
            if LOCAL_LLM is None:
                messagebox.showerror("本地 AI 不可用", "本地 AI 模組不存在，請重新安裝 SanWich。", parent=win)
                return
            site_btn.configure(state="disabled", text="準備下載…")

            def progress(label, done, total):
                pct = int(done * 100 / total) if total else 0
                size_text = f"{done / 1024**3:.2f}/{total / 1024**3:.2f} GB" if total else f"{done / 1024**2:.0f} MB"
                win.after(0, lambda: local_status_label.configure(text=f"{label}：{pct}%（{size_text}）"))

            def worker():
                try:
                    status = LOCAL_LLM.MANAGER.ensure_assets(progress_cb=progress, log_fn=lambda msg: self.log(msg, "model"))
                    gpu_name = str((status.get("gpu") or {}).get("name") or "CPU")
                    text = f"本地 AI 已備妥｜{status.get('variant')}｜{gpu_name}"
                    win.after(0, lambda: local_status_label.configure(text=text, text_color=TEAL_2))
                    win.after(0, lambda: site_btn.configure(state="normal", text="重新檢查本地 AI"))
                except Exception as exc:
                    self.log(f"本地 AI 下載失敗：{exc}", "error")
                    win.after(0, lambda: local_status_label.configure(text=f"下載失敗：{exc}", text_color="#FF8E8E"))
                    win.after(0, lambda: site_btn.configure(state="normal", text="重試下載本地 AI"))

            threading.Thread(target=worker, daemon=True).start()

        def apply_settings_to_cfg(*, log_change: bool = False) -> None:
            """立刻寫入 self.cfg 與磁碟，讓關閉視窗／切換供應商都會生效。"""
            p = normalize_provider(provider_var.get())
            models_list = PROVIDER_MODELS.get(p, GEMINI_MODELS)
            chosen_model = model_var.get()
            if chosen_model not in models_list:
                chosen_model = models_list[0]
                model_var.set(chosen_model)
            chosen_model = normalize_model(p, chosen_model)
            key_value = "" if p == "local" else key_var.get().strip()

            keys = dict(self.cfg.get("api_keys_by_provider") or {})
            models = dict(self.cfg.get("models_by_provider") or {})
            if p != "local":
                keys[p] = key_value
            models[p] = chosen_model

            self.cfg["api_provider"] = p
            self.cfg["model"] = chosen_model
            self.cfg["api_key"] = key_value
            self.cfg["api_keys_by_provider"] = keys
            self.cfg["models_by_provider"] = models
            self.cfg = ensure_provider_memory(self.cfg)
            self.persist_basic_config()
            CORE.save_config(self.cfg)
            if log_change:
                self.log(f"設定已儲存：{PROVIDER_LABELS.get(p, p)} / {self.cfg['model']}", "success")

        def refresh_provider_ui(p: str) -> None:
            models = PROVIDER_MODELS.get(p, GEMINI_MODELS)
            model_menu.configure(values=models)
            preferred = str((self.cfg.get("models_by_provider") or {}).get(p) or "")
            if preferred not in models:
                preferred = models[0]
            if model_var.get() != preferred:
                model_var.set(preferred)
            hint_label.configure(text=f"{PROVIDER_LABELS.get(p, p)}｜{PROVIDER_HINTS.get(p, '')}")
            if p == "local":
                key_label.configure(text="API Key（本機模式不需要）")
                key_entry.configure(state="disabled", placeholder_text="本機模式不需 API Key")
                show_key_checkbox.configure(state="disabled")
                site_btn.configure(text="下載／檢查本地 AI", command=start_local_download)
                if LOCAL_LLM is not None:
                    status = LOCAL_LLM.MANAGER.status()
                    local_status_label.configure(
                        text=(
                            f"執行核心：{'就緒' if status['runtime_ready'] else '尚未下載'}｜"
                            f"模型：{'就緒' if status['model_ready'] else '尚未下載'}｜{status['variant']}"
                        )
                    )
            else:
                key_label.configure(text=f"API Key（{PROVIDER_LABELS.get(p, p)}）")
                key_entry.configure(state="normal", placeholder_text=f"此 Key 只給 {PROVIDER_LABELS.get(p, p)} 使用")
                show_key_checkbox.configure(state="normal")
                local_status_label.configure(text="")
                _label, url = PROVIDER_SITES.get(p, ("開啟申請頁", ""))
                site_btn.configure(
                    text="開啟申請頁",
                    command=lambda u=url: webbrowser.open_new_tab(u) if u else None,
                )

        def on_provider_change(*_):
            if state["applying"]:
                return
            new_p = normalize_provider(provider_var.get())
            old_p = state["provider"]
            if new_p == old_p:
                refresh_provider_ui(new_p)
                return
            state["applying"] = True
            try:
                # 先把舊供應商目前畫面上的 key／模型收進記憶
                keys = dict(self.cfg.get("api_keys_by_provider") or {})
                models = dict(self.cfg.get("models_by_provider") or {})
                if old_p != "local":
                    keys[old_p] = key_var.get().strip()
                models[old_p] = model_var.get()
                self.cfg["api_keys_by_provider"] = keys
                self.cfg["models_by_provider"] = models

                # 換成新供應商已記住的 key／模型
                remembered_key = "" if new_p == "local" else str(keys.get(new_p) or "")
                key_var.set(remembered_key)
                state["provider"] = new_p
                refresh_provider_ui(new_p)
                apply_settings_to_cfg(log_change=True)
            finally:
                state["applying"] = False

        def on_model_change(*_):
            if state["applying"]:
                return
            apply_settings_to_cfg(log_change=False)

        def on_key_focus_out(_event=None):
            if state["applying"]:
                return
            apply_settings_to_cfg(log_change=False)

        key_entry.bind("<FocusOut>", on_key_focus_out)
        provider_var.trace_add("write", on_provider_change)
        model_var.trace_add("write", on_model_change)
        refresh_provider_ui(start_provider)

        actions = ctk.CTkFrame(outer, fg_color="transparent")
        actions.grid(row=11, column=0, sticky="ew", padx=24, pady=(8, 22))
        actions.grid_columnconfigure(1, weight=1)

        def save_and_close():
            apply_settings_to_cfg(log_change=True)
            win.destroy()

        def close_and_save():
            # 關閉也儲存：避免「切了 deepseek 但按關閉等於沒換」
            apply_settings_to_cfg(log_change=True)
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
            command=save_and_close,
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
            command=close_and_save,
        ).grid(row=0, column=3, sticky="e")
        win.protocol("WM_DELETE_WINDOW", close_and_save)

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
            text="SanWich 基本功能永久可用。完整版可解鎖批次處理、快速對照、個人化規則庫與語者分離。",
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
            placeholder_text="貼上完整版 Key",
            height=38,
            corner_radius=14,
            fg_color="#222020",
            border_color=LINE,
            font=(EN_FONT, 13),
        )
        sup_key_entry.grid(row=2, column=0, sticky="ew", padx=(16, 10), pady=(0, 12))

        def apply_supporter_key():
            if LICENSE_MANAGER is None:
                messagebox.showerror("無法啟用", "授權模組載入失敗，請確認安裝檔案完整。", parent=win)
                return
            if LICENSE_MANAGER.activate_key(sup_key_var.get()):
                lic_status_var.set(f"版本狀態：{license_status_summary()['label']}")
                sup_key_var.set("")
                self.log("完整版 Key 已啟用，感謝支持 SanWich！", "success")
                messagebox.showinfo("啟用成功", "完整版功能已解鎖，感謝你的支持！", parent=win)
            else:
                error_code = getattr(LICENSE_MANAGER, "last_license_error_code", "")
                if error_code == "DEVICE_LIMIT_REACHED":
                    messagebox.showerror("裝置數量已滿", "這組 Key 已啟用兩台裝置。請先在其中一台停用授權，再重新啟用。", parent=win)
                elif error_code in {"LICENSE_REVOKED", "LICENSE_DISABLED", "LICENSE_EXPIRED"}:
                    messagebox.showerror("授權無法使用", "這組完整版 Key 已停用、撤銷或到期。", parent=win)
                elif error_code in {"LICENSE_NOT_FOUND", "INVALID_REQUEST"}:
                    messagebox.showerror("Key 無效", "請確認完整版 Key 是否輸入正確。", parent=win)
                elif getattr(LICENSE_MANAGER, "last_license_error", ""):
                    messagebox.showerror("無法完成啟用", "目前無法完成線上授權。請確認網路後再試。", parent=win)
                else:
                    messagebox.showerror("Key 無效", "請確認完整版 Key 是否輸入正確。", parent=win)

        def refresh_license_status():
            lic_status_var.set(f"版本狀態：{license_status_summary()['label']}")

        def verify_online_license():
            self.refresh_license_if_due_async(force=True, callback=refresh_license_status)

        def deactivate_this_device():
            if LICENSE_MANAGER is None or not messagebox.askyesno(
                "停用這台電腦",
                "停用成功後會釋放一個裝置名額；這台電腦將回到試用或基本功能。是否繼續？",
                parent=win,
            ):
                return

            def worker():
                ok = LICENSE_MANAGER.deactivate_server_license()
                self.after(0, lambda: finish_deactivate(ok))

            def finish_deactivate(ok: bool):
                refresh_license_status()
                if ok:
                    self.log("這台電腦的完整版授權已停用。", "success")
                    messagebox.showinfo("已停用", "裝置名額已釋放；API Key 與個人設定不受影響。", parent=win)
                else:
                    messagebox.showerror("停用失敗", "目前無法連線授權伺服器，因此沒有清除本機授權。請稍後再試。", parent=win)

            threading.Thread(target=worker, daemon=True).start()

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
        license_actions = ctk.CTkFrame(supporter, fg_color="transparent")
        license_actions.grid(row=3, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 12))
        ctk.CTkButton(
            license_actions,
            text="重新驗證",
            width=92,
            height=30,
            corner_radius=12,
            fg_color="#32333B",
            hover_color="#45464F",
            font=(FONT, 12),
            command=verify_online_license,
        ).pack(side="left")
        ctk.CTkButton(
            license_actions,
            text="停用此裝置",
            width=104,
            height=30,
            corner_radius=12,
            fg_color="#32333B",
            hover_color="#45464F",
            font=(FONT, 12),
            command=deactivate_this_device,
        ).pack(side="left", padx=(8, 0))

        credits = ctk.CTkFrame(outer, fg_color="transparent")
        credits.grid(row=12, column=0, sticky="ew", padx=24, pady=(0, 18))
        credits.grid_columnconfigure(0, weight=1)
        version_area = ctk.CTkFrame(credits, fg_color="transparent")
        version_area.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            version_area,
            text=f"v{APP_VERSION}",
            text_color=TEXT_ON_DARK,
            font=(EN_FONT, 12, "bold"),
        ).pack(side="left")
        ctk.CTkButton(
            version_area,
            text="檢查更新",
            width=76,
            height=26,
            corner_radius=10,
            fg_color="#32333B",
            hover_color="#45464F",
            font=(FONT, 11),
            command=lambda: self.check_for_updates_async(True),
        ).pack(side="left", padx=(10, 0))
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
        if (self.diarize_enabled.get() or self.srt_diarize_enabled.get()) and not has_feature("diarization"):
            self.diarize_enabled.set(False)
            self.srt_diarize_enabled.set(False)
            self.persist_basic_config()
            self.show_supporter_message("diarization")
            return
        if len(input_files) == 1:
            if self.srt_enabled.get() and not self.output_srt_path.get().strip():
                self.output_srt_path.set(str(Path(input_files[0]).with_suffix(".srt")))
            if self.txt_enabled.get() and not self.output_txt_path.get().strip():
                self.output_txt_path.set(str(Path(input_files[0]).with_suffix(".txt")))
        self.persist_basic_config()
        selected_provider = normalize_provider(self.cfg.get("api_provider", "gemini"))
        if self.ai_enabled.get() and selected_provider != "local" and not (self.cfg.get("api_key") or "").strip():
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
        need_diar = bool(self.diarize_enabled.get() or self.srt_diarize_enabled.get())
        context_notes = self.notes_text()
        self.remember_supplement_notes(context_notes)
        args = (jobs, self.ai_enabled.get(), context_notes, self.editor_enabled.get(), need_diar)
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
                "目前使用 CPU，載入與轉寫會比較久。長音訊請預留較多時間（粗估即時倍率 3–8 倍）。"
                "若有 NVIDIA 顯示卡，建議安裝 GPU 版環境以大幅加速。",
                "warn",
            )
        free_gb = None
        if EXPERIMENTS is not None:
            try:
                free_gb = EXPERIMENTS.check_disk_space_gb(Path.home())
            except Exception:
                free_gb = None
        if free_gb is not None and free_gb < 6:
            self.log(f"磁碟剩餘約 {free_gb} GB，Breeze 模型約需 3–4 GB，空間可能不足。", "warn")
        self.log(
            "載入 Breeze-ASR-25；首次使用會自動下載模型（約 3–4 GB）。"
            "下載中斷可重新啟動再試；不完整暫存會在失敗時清理。",
            "model",
        )
        self.set_busy("載入 Breeze 模型中（首次需下載 3-4 GB）")
        self.set_progress(5, "檢查／下載 Breeze 模型…")

        # 先 snapshot_download 以顯示進度；失敗清理 .incomplete
        model_id = CORE.BREEZE_MODEL_ID
        try:
            from huggingface_hub import snapshot_download

            def _hub_progress(progress):
                try:
                    if progress.total:
                        pct = int(progress.completed / progress.total * 100)
                        self.set_progress(
                            min(18, 5 + pct // 8),
                            f"下載 Breeze 模型 {pct}%（{progress.completed}/{progress.total} 檔）",
                        )
                except Exception:
                    pass

            snapshot_download(
                repo_id=model_id,
                resume_download=True,
                # tqdm 類回報在部分環境不可用；改以 log 提示
            )
            self.set_progress(18, "模型檔案就緒，載入中…")
        except Exception as exc:
            self.log(f"模型下載進度提示略過（將改由 transformers 載入）：{exc}", "warn")

        try:
            processor = WhisperProcessor.from_pretrained(model_id)
            model = WhisperForConditionalGeneration.from_pretrained(
                model_id,
                torch_dtype=dtype,
                low_cpu_mem_usage=True,
                use_safetensors=True,
            ).to(device)
            model.eval()
        except Exception as exc:
            self.log(
                f"Breeze 模型載入失敗：{exc}。若剛中斷下載，請確認網路與磁碟空間後重試；"
                "不要手動把半成品資料夾當完成模型使用。",
                "error",
            )
            raise

        self.pipeline = AutomaticSpeechRecognitionPipeline(
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            torch_dtype=dtype,
            device=0 if device == "cuda" else -1,
        )
        self.set_progress(20, "Breeze 模型載入完成")
        return self.pipeline

    def transcribe_breeze(self, audio: dict) -> tuple[list[dict], str]:
        import numpy as np
        import time as _time

        samples = audio["array"]
        sr = audio["sampling_rate"]
        audio_dur = len(samples) / float(sr) if sr else 0.0
        t0 = _time.perf_counter()

        # 效能實驗（VAD 等）暫不開放 UI／預設關閉；一律固定切段
        use_vad = False
        seg_samples = CORE.SEGMENT_SECONDS * sr
        total_segs = max(1, int(np.ceil(len(samples) / seg_samples)))
        spans = [(i * seg_samples, min(len(samples), (i + 1) * seg_samples)) for i in range(total_segs)]

        total_segs = len(spans)
        chunks = []
        texts = []

        for i, (s, e) in enumerate(spans):
            if self.cancel_event.is_set():
                raise TranscriptionCancelled("已取消")
            seg = {"array": samples[s:e], "sampling_rate": sr}
            pct = 20 + int((i / max(total_segs, 1)) * 50)
            elapsed = _time.perf_counter() - t0
            eta = ""
            if EXPERIMENTS is not None:
                eta = "｜" + EXPERIMENTS.estimate_remaining(i, total_segs, elapsed)
            stage = "VAD 段" if use_vad else "段"
            self.set_progress(
                pct,
                f"Breeze 辨識中：第 {i + 1}/{total_segs} {stage}"
                f"（音訊 {EXPERIMENTS.format_duration(audio_dur) if EXPERIMENTS else f'{audio_dur:.0f}s'}）{eta}",
            )
            result = self.pipeline(seg, return_timestamps=True)
            texts.append((result.get("text") or "").strip())
            offset = s / sr
            segment_duration = max(0.0, (e - s) / sr)
            for chunk in result.get("chunks") or []:
                ts = chunk.get("timestamp") or (0.0, 0.0)
                st = max(0.0, min(segment_duration, ts[0] if ts[0] is not None else 0.0))
                en = max(st, min(segment_duration, ts[1] if ts[1] is not None else st + 2.0))
                if en <= st:
                    continue
                nc = dict(chunk)
                nc["timestamp"] = (st + offset, en + offset)
                chunks.append(nc)

        elapsed_total = _time.perf_counter() - t0
        if EXPERIMENTS is not None and audio_dur > 0:
            bench = EXPERIMENTS.run_micro_benchmark(
                audio_seconds=audio_dur,
                backend_name="transformers+VAD" if use_vad else "transformers",
                elapsed_s=elapsed_total,
            )
            self.log(
                f"轉寫耗時 {bench['elapsed_seconds']}s｜音訊 {bench['audio_seconds']}s｜"
                f"即時倍率 {bench['realtime_factor']}",
                "model",
            )
            if EXPERIMENT_CFG is not None:
                try:
                    EXPERIMENT_CFG.set("last_benchmark", bench)
                    EXPERIMENT_CFG.save()
                except Exception:
                    pass

        chunks, removed = CORE.suppress_repeat_hallucination(chunks)
        if removed:
            self.log(f"偵測到連續重複的幻覺字幕，已自動清除 {removed} 組。", "warn")
        chunks, adjusted = CORE.normalize_chunk_timeline(chunks)
        if adjusted:
            self.log(f"已修正 {adjusted} 組跨 60 秒分段的重疊時間碼。", "warn")
        return CORE.punctuate_chunks(chunks), "".join(texts)

    def release_breeze_pipeline(self):
        """Release ASR model references and return CUDA memory before local LLM starts."""
        if self.pipeline is None:
            return
        self.log("Breeze：釋放 ASR 模型，準備交接顯示卡記憶體。", "model")
        pipeline = self.pipeline
        self.pipeline = None
        try:
            del pipeline
            gc.collect()
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                try:
                    torch.cuda.ipc_collect()
                except Exception:
                    pass
        except Exception as exc:
            self.log(f"Breeze 顯存清理提示：{exc}", "warn")

    def prepare_transcription(self, inp: str, diarize: bool = False) -> dict:
        """Run ASR (and optional diarization) without starting any LLM."""
        wav_path = None
        audio = None
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

            speaker_turns = None
            if diarize and DIARIZATION is not None:
                try:
                    self.set_progress(71, "語者分離中（首次需下載模型）")
                    self.log("語者分離：開始（sherpa-onnx + 3D-Speaker ERes2Net）。", "model")
                    num_spk = int(self.cfg.get("diarization_num_speakers", 3) or 0)

                    def diar_progress(done_seg, total_seg):
                        if total_seg:
                            self.set_progress(71 + int((done_seg / total_seg) * 3), "語者分離中")

                    speaker_turns = DIARIZATION.diarize_array(
                        audio["array"], audio["sampling_rate"],
                        num_speakers=(num_spk if num_spk > 0 else None),
                        models_base=ROOT, log=self.log, progress=diar_progress,
                    )
                    self.log("語者分析完成，將在最終字幕套用講者。", "success")
                except Exception as exc:
                    self.log(f"語者分離失敗：{exc}", "warn")
                    speaker_turns = None
            elif diarize and DIARIZATION is None:
                self.log("找不到語者分離模組（core/diarization.py）。", "warn")

            return {
                "chunks": [dict(c) for c in chunks],
                "breeze_text": breeze_text,
                "speaker_turns": speaker_turns,
            }
        finally:
            audio = None
            if wav_path:
                Path(wav_path).unlink(missing_ok=True)

    def apply_script_document_notes(self, chunks: list[dict], context_notes: str) -> list[dict]:
        """無 AI 或 AI 失敗時，仍可用完整腳本做文檔匹配覆寫。"""
        notes = (context_notes or "").strip()
        if not notes or not hasattr(CORE, "is_script_document"):
            return chunks
        try:
            if not CORE.is_script_document(notes):
                return chunks
            script = CORE.extract_script_document(notes)
            if not script:
                return chunks
            texts = [(c.get("text") or "").strip() for c in chunks]
            new_texts, meta = CORE.document_match_texts(texts, script)
            reps = CORE.replacements_from_context(notes)
            phrases = [
                p for p in CORE.required_phrases_from_context(notes)
                if len(re.sub(r"\s+", "", p)) <= 24
            ]
            terms = CORE.canonical_terms_from_context(notes)
            out = []
            for text in new_texts:
                value = text
                if reps:
                    value = CORE.apply_context_replacements(value, reps)
                if phrases:
                    value = CORE.apply_context_required_phrases(value, phrases)
                if terms:
                    value = CORE.apply_context_canonical_terms(value, terms)
                out.append(value)
            updated = [dict(c) for c in chunks]
            for idx, value in enumerate(out):
                updated[idx]["text"] = value
            self.log(
                f"文檔匹配：已對齊腳本並覆寫 {meta.get('matched', 0)}/"
                f"{meta.get('matched', 0) + meta.get('unchanged', 0)} 組"
                f"（平均相似度 {meta.get('avg_score', 0)}）。",
                "success",
            )
            return updated
        except Exception as exc:
            self.log(f"文檔匹配略過：{exc}", "warn")
            return chunks

    def process_one(self, inp: str, srt: str, txt: str, use_llm: bool, context_notes: str,
                    use_text_fix: bool, diarize: bool = False, prepared: dict | None = None) -> bool:
        ai_incomplete = False
        semantic_segmented = False
        if prepared is None:
            prepared = self.prepare_transcription(inp, diarize=diarize)
        chunks = [dict(c) for c in prepared.get("chunks") or []]
        breeze_text = str(prepared.get("breeze_text") or "")
        speaker_turns = prepared.get("speaker_turns")
        try:
            save_text = breeze_text
            before_chunks = [dict(c) for c in chunks]
            provider = normalize_provider(self.cfg.get("api_provider", "gemini"))
            llm_credentials_ready = provider == "local" or bool((self.cfg.get("api_key") or "").strip())
            if use_llm and llm_credentials_ready:
                effective_use_text_fix = resolve_editor_prompt_flag(use_text_fix, self.cfg)
                self.set_chip(self.ai_chip, "running")
                self.set_progress(75, "AI 校對中")
                if effective_use_text_fix:
                    self.log("AI 總編輯：已強制套用總編輯 Prompt。", "model")
                elif (context_notes or "").strip():
                    self.log(
                        "AI 校對：未開總編輯，但補充資料會以「詞庫」先注入，要求模型主動改音近／形近錯辨。",
                        "model",
                    )
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
                    llm_meta = dict(getattr(CORE, "LAST_LLM_MERGE_META", {}) or {})
                    covered_count = int(llm_meta.get("covered_count", len(llm_texts)))
                    coverage_complete = bool(llm_meta.get("complete", covered_count == len(before_chunks)))
                    after_chunks = [dict(c) for c in chunks]
                    if len(after_chunks) != len(before_chunks):
                        ai_incomplete = True
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
                        self.store_compare(
                            inp, srt, txt, before_chunks, after_chunks, breeze_text, llm_plain,
                            ai_meta=llm_meta,
                        )
                        if coverage_complete:
                            self.set_chip(self.ai_chip, "done")
                            self.log(f"AI 校對完整完成，共 {len(llm_plain)} 字。", "success")
                            # 本機 7B 語意斷句常失敗且極耗時（又是一整輪生成）；改走本機安全斷句。
                            skip_ai_semantic = provider == "local"
                            if skip_ai_semantic:
                                semantic_segmented = True
                                self.log(
                                    "本機 AI：略過二次語意斷句；保留校正版文字目前的固定 TC 分配。",
                                    "model",
                                )
                            else:
                                try:
                                    self.set_progress(94, "AI 語意斷句中")

                                    def segmentation_progress(window_i, total):
                                        pct = 94 + int((window_i / max(total, 1)) * 2)
                                        self.set_progress(pct, f"AI 語意斷句第 {window_i + 1}/{total} 段")

                                    semantic_chunks, semantic_meta = CORE.semantic_resegment_chunks(
                                        after_chunks,
                                        llm_cfg,
                                        self.log,
                                        target_width=self.srt_max_line_width(),
                                        progress_cb=segmentation_progress,
                                    )
                                    if semantic_meta.get("usable") and semantic_chunks:
                                        chunks = semantic_chunks
                                        semantic_segmented = True
                                        failed_windows = semantic_meta.get("failed_windows") or []
                                        if failed_windows:
                                            self.log(
                                                f"AI 固定 TC 斷句局部完成：共 {len(semantic_chunks)} 組，"
                                                f"TC 完全不變；失敗窗口 {failed_windows} 保留原校正版分配。",
                                                "warn",
                                            )
                                        else:
                                            self.log(
                                                f"AI 固定 TC 斷句完成：共 {len(semantic_chunks)} 組，"
                                                "TC 起訖與順序完全不變。",
                                                "success",
                                            )
                                    else:
                                        fails = semantic_meta.get("failed_windows") or []
                                        chunks = after_chunks
                                        semantic_segmented = True
                                        self.log(
                                            "AI 固定 TC 斷句沒有可用結果，保留原校正版字幕與 TC。"
                                            f"失敗窗口：{fails or '—'}；"
                                            f"完整性重試 {semantic_meta.get('integrity_retry_count', 0)} 次。",
                                            "warn",
                                        )
                                except Exception as segmentation_exc:
                                    chunks = after_chunks
                                    semantic_segmented = True
                                    self.log(
                                        f"AI 固定 TC 斷句失敗，保留原校正版字幕與 TC：{segmentation_exc}",
                                        "warn",
                                    )
                        else:
                            ai_incomplete = True
                            semantic_segmented = True
                            missing_count = max(0, len(before_chunks) - covered_count)
                            self.set_chip(self.ai_chip, "error")
                            self.log(
                                f"AI 校對未完成：自動重試後仍只有 {covered_count}/{len(before_chunks)} 組可對齊；"
                                f"其餘 {missing_count} 組保留 Breeze 原文並標成灰色。",
                                "error",
                            )
                except Exception as exc:
                    ai_incomplete = True
                    semantic_segmented = True
                    self.log(f"AI 校對失敗：{exc}，改儲存原始辨識結果。", "error")
                    self.set_chip(self.ai_chip, "error")
                    chunks = before_chunks
                    chunks = self.apply_script_document_notes(chunks, context_notes)
                    save_text = CORE.chunks_to_plain(chunks) if hasattr(CORE, "chunks_to_plain") else "\n".join(
                        (c.get("text") or "").strip() for c in chunks if (c.get("text") or "").strip()
                    )
            else:
                # 未開 AI 時，仍可用完整腳本做文檔匹配
                if (context_notes or "").strip():
                    chunks = self.apply_script_document_notes(chunks, context_notes)
                    save_text = CORE.chunks_to_plain(chunks) if hasattr(CORE, "chunks_to_plain") else "\n".join(
                        (c.get("text") or "").strip() for c in chunks if (c.get("text") or "").strip()
                    )
                self.set_chip(self.ai_chip, "idle")

            spk_chunks = None
            if diarize and DIARIZATION is not None and speaker_turns is not None:
                try:
                    spk_chunks = DIARIZATION.assign_speakers_to_chunks(chunks, speaker_turns)
                    n_spk = DIARIZATION.count_speakers(spk_chunks)
                    self.log(f"語者分離完成，偵測到 {n_spk} 位語者。", "success")
                except Exception as exc:
                    self.log(f"語者標籤套用失敗：{exc}", "warn")
                    spk_chunks = None

            # SRT：可選在文字前加講者標籤（不改時間碼）
            srt_chunks = chunks
            if srt and spk_chunks is not None and bool(self.cfg.get("srt_diarization_enabled", False)):
                try:
                    order = DIARIZATION._appearance_order(spk_chunks)
                    srt_chunks = []
                    for c in spk_chunks:
                        nc = dict(c)
                        text = (nc.get("text") or "").strip()
                        spk = nc.get("speaker")
                        label = DIARIZATION.speaker_label(order.get(spk, 0))
                        if text:
                            nc["text"] = f"講者{label}：{text}"
                        srt_chunks.append(nc)
                    self.log("SRT 已加上語者標籤（時間碼不變）。", "success")
                except Exception as exc:
                    self.log(f"SRT 語者標籤略過：{exc}", "warn")
                    srt_chunks = chunks

            if srt:
                self.write_srt_output(srt, srt_chunks, preserve_segments=semantic_segmented)
                if not semantic_segmented:
                    segment_meta = dict(getattr(CORE, "LAST_SRT_SEGMENTATION_META", {}) or {})
                    repaired_count = int(segment_meta.get("repair_count", 0) or 0)
                    if repaired_count:
                        self.log(
                            f"本機備援斷句：已修復 {repaired_count} 個高信心不完整切點。",
                            "success",
                        )
                self.log(f"SRT 已儲存：{srt}（每句目標 {int(self.srt_max_line_width())} 字，語意不完整時可延長）")
            if txt:
                txt_content = save_text
                if spk_chunks is not None and bool(self.cfg.get("txt_diarization_enabled", True)):
                    try:
                        speaker_txt = DIARIZATION.chunks_to_speaker_txt(spk_chunks)
                        if speaker_txt.strip():
                            txt_content = speaker_txt
                        else:
                            self.log("語者分離未產生有效分段，純文字改用無語者版本。", "warn")
                    except Exception as exc:
                        self.log(f"純文字語者套用失敗：{exc}", "warn")
                Path(txt).write_text(txt_content.rstrip("\n") + "\n", encoding="utf-8-sig")
                self.log(f"純文字已儲存：{txt}")
            editor_chunks = strip_chunks_for_srt_display(srt_chunks if srt else chunks)
            if srt and Path(srt).exists():
                try:
                    parsed = parse_srt_text(Path(srt).read_text(encoding="utf-8-sig"))
                    if parsed:
                        editor_chunks = strip_chunks_for_srt_display(parsed)
                except Exception as exc:
                    self.log(f"SRT 編輯器讀取輸出檔失敗，改用內部字幕資料：{exc}", "warn")
            self.store_result(inp, srt, txt, editor_chunks, semantic_segmented=semantic_segmented)
            self.set_progress(100, "完成（AI 校對未完整完成）" if ai_incomplete else "完成")
            return not ai_incomplete
        finally:
            prepared = None

    def batch_worker(self, jobs, use_llm: bool, context_notes: str, use_text_fix: bool, diarize: bool = False):
        total = len(jobs)
        done = 0
        failed = []
        ai_incomplete_files = []
        try:
            provider = normalize_provider(self.cfg.get("api_provider", "gemini"))
            local_two_stage = bool(use_llm and provider == "local")
            if local_two_stage:
                if LOCAL_LLM is None:
                    raise RuntimeError("本地 AI 模組不存在，請重新安裝 SanWich。")
                # A server left running from settings or a previous job still owns VRAM.
                # Stop it before ASR so RTX 2060-class cards never hold both models.
                LOCAL_LLM.MANAGER.stop()
                self.set_chip(self.ai_chip, "idle")
                self.log("本機私密 AI：採兩階段處理，先完成所有 Breeze 轉寫，再釋放顯存後校對。", "model")

                prepared_jobs = []
                try:
                    for idx, (inp, srt, txt) in enumerate(jobs, start=1):
                        if self.cancel_event.is_set():
                            raise TranscriptionCancelled("已取消")
                        prefix = f"[轉寫 {idx}/{total}] " if total > 1 else ""
                        self.log(f"{prefix}開始處理：{inp}")
                        self.set_progress(0, f"{prefix}準備中")
                        try:
                            prepared = self.prepare_transcription(inp, diarize=diarize)
                            prepared_jobs.append((inp, srt, txt, prepared))
                        except TranscriptionCancelled:
                            raise
                        except Exception as exc:
                            failed.append(f"{Path(inp).name}：{exc}")
                            self.log(f"{prefix}錯誤：{exc}", "error")
                            self.set_chip(self.breeze_chip, "error")
                finally:
                    self.release_breeze_pipeline()

                if self.cancel_event.is_set():
                    raise TranscriptionCancelled("已取消")

                local_ready = False
                if prepared_jobs:
                    self.set_progress(72, "準備本地私密 AI")
                    self.set_chip(self.ai_chip, "running")
                    progress_state = {"last": -10}

                    def local_progress(label, done_bytes, total_bytes):
                        pct = int(done_bytes * 100 / total_bytes) if total_bytes else 0
                        if pct >= progress_state["last"] + 10 or pct == 100:
                            progress_state["last"] = pct
                            self.log(f"{label}：{pct}%", "model")
                        self.set_progress(72 + min(3, int(pct * 0.03)), "準備本地私密 AI")

                    try:
                        LOCAL_LLM.MANAGER.ensure_running(
                            progress_cb=local_progress,
                            log_fn=lambda msg: self.log(msg, "model"),
                        )
                        local_ready = True
                    except Exception as exc:
                        self.log(f"本地 AI 無法啟動：{exc}；仍會儲存 Breeze 原始結果。", "error")
                        self.set_chip(self.ai_chip, "error")

                for idx, (inp, srt, txt, prepared) in enumerate(prepared_jobs, start=1):
                    if self.cancel_event.is_set():
                        raise TranscriptionCancelled("已取消")
                    prefix = f"[校對 {idx}/{len(prepared_jobs)}] " if len(prepared_jobs) > 1 else ""
                    self.log(f"{prefix}整理輸出：{inp}")
                    try:
                        ai_complete = self.process_one(
                            inp, srt, txt, local_ready, context_notes, use_text_fix,
                            diarize, prepared=prepared,
                        )
                        done += 1
                        if not local_ready or not ai_complete:
                            ai_incomplete_files.append(Path(inp).name)
                    except TranscriptionCancelled:
                        raise
                    except Exception as exc:
                        failed.append(f"{Path(inp).name}：{exc}")
                        self.log(f"{prefix}錯誤：{exc}", "error")
            else:
                for idx, (inp, srt, txt) in enumerate(jobs, start=1):
                    if self.cancel_event.is_set():
                        raise TranscriptionCancelled("已取消")
                    prefix = f"[{idx}/{total}] " if total > 1 else ""
                    self.log(f"{prefix}開始處理：{inp}")
                    self.set_progress(0, f"{prefix}準備中")
                    try:
                        ai_complete = self.process_one(
                            inp, srt, txt, use_llm, context_notes, use_text_fix, diarize
                        )
                        done += 1
                        if not ai_complete:
                            ai_incomplete_files.append(Path(inp).name)
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
            elif ai_incomplete_files:
                msg = (
                    f"已產生 {done} 個檔案，但其中 {len(ai_incomplete_files)} 個的 AI 校對未完整完成。\n\n"
                    + "\n".join(ai_incomplete_files[:5])
                    + "\n\n灰色字幕保留 Breeze 原文，不能視為 AI 已校對。"
                )
                self.after(0, lambda m=msg: messagebox.showwarning("AI 校對未完成", m))
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

    def store_result(self, inp: str, srt: str, txt: str, chunks: list[dict],
                     semantic_segmented: bool = False):
        result = {
            "inp": inp,
            "srt": srt,
            "txt": txt,
            "chunks": clone_chunks(chunks),
            "semantic_segmented": bool(semantic_segmented),
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
        for before_index, after_index in CORE.align_caption_indices(original, updated):
            before = original[before_index] if before_index is not None else {}
            after = updated[after_index] if after_index is not None else {}
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
                    "index": (after_index + 1) if after_index is not None else (before_index + 1),
                    "original_index": (before_index + 1) if before_index is not None else None,
                    "updated_index": (after_index + 1) if after_index is not None else None,
                    "before_start": before_ts[0],
                    "before_end": before_ts[1],
                    "after_start": after_ts[0],
                    "after_end": after_ts[1],
                    "before_text": before_text,
                    "after_text": after_text,
                }
            )
        if records:
            try:
                EDIT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
                with EDIT_HISTORY_PATH.open("a", encoding="utf-8") as fh:
                    for record in records:
                        # 不寫完整絕對路徑，改存檔名（學習用指紋另記）
                        safe = dict(record)
                        if safe.get("input"):
                            safe["input_name"] = Path(str(safe["input"])).name
                        fh.write(json.dumps(safe, ensure_ascii=False) + "\n")
            except Exception as exc:
                self.log(f"編輯歷史寫入失敗：{exc}", "warn")
            # 匯出差異同時寫入學習事件（manual_edit）
            if _learning_enabled():
                for record in records:
                    try:
                        before_t = (record.get("before_text") or "").strip()
                        after_t = (record.get("after_text") or "").strip()
                        if not before_t or before_t == after_t:
                            continue
                        record_review_feedback(
                            action=LEARNING.ACTION_MANUAL_EDIT if LEARNING else "manual_edit",
                            original_text=before_t,
                            ai_text="",
                            final_text=after_t,
                            timecode_start=record.get("after_start"),
                            timecode_end=record.get("after_end"),
                            input_path=str(record.get("input") or data.get("inp") or ""),
                            source="srt_editor",
                        )
                    except Exception:
                        pass
        return len(records)

    def stop_preview(self):
        if self.preview_player is not None:
            try:
                self.preview_player.stop()
            except Exception:
                pass
        proc = self.preview_process
        self.preview_process = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    def destroy(self):
        if self.preview_player is not None:
            try:
                self.preview_player.close()
            except Exception:
                pass
        if LOCAL_LLM is not None:
            try:
                LOCAL_LLM.MANAGER.stop()
            except Exception:
                pass
        super().destroy()

    def play_srt_segment(self, media_path: str, start: float, end: float):
        if not media_path or not Path(media_path).exists():
            messagebox.showinfo("找不到原始檔", "需要原始音訊或影片檔，才能播放對應片段。")
            return
        if end <= start:
            messagebox.showerror("時間碼錯誤", "結束時間必須晚於開始時間。")
            return
        self.stop_preview()
        duration = max(0.1, end - start)
        if self.preview_player is not None:
            try:
                self.preview_player.play(media_path, start, start + duration)
                return
            except Exception as exc:
                self.log(f"低延遲播放器無法使用，暫時改用 ffplay：{exc}", "warn")
        player = find_ffplay()
        if not player:
            messagebox.showinfo("找不到播放器", "找不到低延遲播放器或 ffplay.exe，請重新執行 setup。")
            return
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
        # 與 SRT 匯出／匯入一致：編輯器內不顯示標點
        original_chunks = strip_chunks_for_srt_display(data.get("chunks") or [])
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
        playback = {"playing": False, "started_at": None, "started_from": 0.0, "after_id": None, "embedded": False}
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
        ai_checked_indices: set[int] = set()
        ai_unchecked_indices: set[int] = set()
        compare_for_file = None
        if getattr(self, "batch_compares", None):
            compare_for_file = self.batch_compares.get(data.get("inp"))
        if compare_for_file is None and self.last_compare and self.last_compare.get("inp") == data.get("inp"):
            compare_for_file = self.last_compare
        if compare_for_file is not None:
            self.last_compare = compare_for_file
            before_chunks_for_review = compare_for_file.get("before_chunks") or []
            after_chunks_for_review = compare_for_file.get("after_chunks") or []
            ai_meta = compare_for_file.get("ai_meta") or {}
            covered = ai_meta.get("covered_indices")
            projected_review, projected_checked, projected_unchecked = CORE.project_ai_review_indices(
                before_chunks_for_review,
                after_chunks_for_review,
                original_chunks,
                covered_indices=covered,
            )
            ai_review_indices.update(projected_review)
            ai_checked_indices.update(projected_checked)
            ai_unchecked_indices.update(projected_unchecked)

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
        if compare_for_file is not None and ai_unchecked_indices:
            initial_status = (
                f"共 {len(original_chunks)} 組｜AI 完成 {len(ai_checked_indices)}/{len(original_chunks)}｜"
                f"灰色 {len(ai_unchecked_indices)} 組未完成"
            )
        else:
            initial_status = f"共 {len(original_chunks)} 組字幕"
        status_var = ctk.StringVar(value=initial_status)
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
        if compare_for_file is not None:
            ctk.CTkLabel(
                tools,
                text="橘：AI 有修改　綠：AI 已檢查未改　灰：AI 未完成",
                text_color=MUTED_ON_DARK,
                font=(FONT, 11),
            ).grid(row=0, column=1, sticky="e", padx=(12, 8))
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
            command=lambda *args: scroll_timeline(*args),
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

        page_size = 160
        page_state = {"index": 0}
        page_label_var = ctk.StringVar(value="")
        pager = ctk.CTkFrame(header, fg_color="transparent")
        pager.grid(row=1, column=0, columnspan=4, sticky="e", pady=(6, 0))
        ctk.CTkButton(
            pager, text="‹ 上一頁", width=82, height=28, corner_radius=10,
            fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK, font=(FONT, 11, "bold"),
            command=lambda: change_caption_page(-1),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            pager, textvariable=page_label_var, text_color=MUTED_ON_DARK, font=(FONT, 11), width=190,
        ).pack(side="left")
        ctk.CTkButton(
            pager, text="下一頁 ›", width=82, height=28, corner_radius=10,
            fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK, font=(FONT, 11, "bold"),
            command=lambda: change_caption_page(1),
        ).pack(side="left", padx=(6, 0))

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
        rendered_row_indices: set[int] = set()
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
            win.after_idle(draw_timeline)

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
            ensure_caption_page(selected_index["value"])
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
                ensure_caption_page(row_index)
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
            if row_index in ai_checked_indices:
                return "ai_checked"
            if row_index in ai_unchecked_indices:
                return "ai_unchecked"
            return "normal"

        def apply_row_styles():
            try:
                focused = win.focus_get()
            except Exception:
                focused = None
            for idx, row in enumerate(rows):
                if len(row.get("widgets") or []) != 4:
                    continue
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
                elif state == "ai_checked":
                    num_btn.configure(bg=AI_CHECKED, activebackground=AI_CHECKED_BORDER)
                    start_entry.configure(bg=DARK_2, highlightbackground=AI_CHECKED_BORDER, highlightcolor=AI_CHECKED)
                    end_entry.configure(bg=DARK_2, highlightbackground=AI_CHECKED_BORDER, highlightcolor=AI_CHECKED)
                    if not skip_text:
                        text_box.configure(bg=AI_CHECKED_BG, highlightbackground=AI_CHECKED_BORDER, highlightcolor=AI_CHECKED)
                elif state == "ai_unchecked":
                    num_btn.configure(bg=AI_UNCHECKED, activebackground=AI_UNCHECKED_BORDER)
                    start_entry.configure(bg=DARK_2, highlightbackground=AI_UNCHECKED_BORDER, highlightcolor=AI_UNCHECKED)
                    end_entry.configure(bg=DARK_2, highlightbackground=AI_UNCHECKED_BORDER, highlightcolor=AI_UNCHECKED)
                    if not skip_text:
                        text_box.configure(bg=AI_UNCHECKED_BG, highlightbackground=AI_UNCHECKED_BORDER, highlightcolor=AI_UNCHECKED)
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
            structure_changed = len(rows) != len(chunks)
            while len(rows) > len(chunks):
                destroy_row(rows.pop())
            while len(rows) < len(chunks):
                rows.append(create_caption_row({"timestamp": (0.0, 0.0), "text": ""}))
            for row, chunk in zip(rows, chunks):
                ts = chunk.get("timestamp") or (0.0, 0.0)
                new_start = CORE.seconds_to_srt_time(ts[0] if ts[0] is not None else 0.0)
                new_end = CORE.seconds_to_srt_time(ts[1] if ts[1] is not None else 0.0)
                new_text = (chunk.get("text") or "").strip()
                if row["start"].get() != new_start:
                    row["start"].set(new_start)
                if row["end"].get() != new_end:
                    row["end"].set(new_end)
                if row["text"].get("1.0", "end").strip() != new_text:
                    row["text"].delete("1.0", "end")
                    row["text"].insert("1.0", new_text)
            if structure_changed:
                reflow_rows()
            else:
                apply_row_styles()
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
            visible_left = timeline_canvas.canvasx(0) - 120
            visible_right = timeline_canvas.canvasx(max(1, timeline_canvas.winfo_width())) + 120
            for idx, row in enumerate(rows):
                try:
                    start, end = row_times(idx)
                except Exception:
                    continue
                x1 = 24 + start * px_per_second
                x2 = max(x1 + 8, 24 + end * px_per_second)
                if x2 < visible_left or x1 > visible_right:
                    continue
                selected = idx in selected_indices
                state = row_visual_state(idx)
                if state == "time_error":
                    fill = TIME_ERROR if selected else TIME_ERROR_BG
                    outline = "#FECACA" if selected else TIME_ERROR
                elif state == "ai_review":
                    fill = AI_REVIEW if selected else AI_REVIEW_BG
                    outline = "#FED7AA" if selected else AI_REVIEW_BORDER
                elif state == "ai_checked":
                    fill = AI_CHECKED if selected else AI_CHECKED_BG
                    outline = "#BBF7D0" if selected else AI_CHECKED_BORDER
                elif state == "ai_unchecked":
                    fill = AI_UNCHECKED if selected else AI_UNCHECKED_BG
                    outline = "#CBD5E1" if selected else AI_UNCHECKED_BORDER
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

        def scroll_timeline(*args):
            timeline_canvas.xview(*args)
            draw_timeline()

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
            if playback["playing"] and playback.get("embedded") and self.preview_player is not None:
                try:
                    set_playhead(self.preview_player.current_time(), center=False, redraw=False)
                except Exception:
                    pass
            elif playback["playing"] and playback["started_at"] is not None:
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
            if playback.get("embedded") and self.preview_player is not None:
                try:
                    player_running = self.preview_player.is_playing()
                    current = min(timeline_duration, self.preview_player.current_time())
                except Exception:
                    player_running = False
                    current = playhead["time"]
                if not player_running:
                    set_playhead(current, center=False, redraw=False)
                    playback["playing"] = False
                    playback["started_at"] = None
                    cancel_playback_timer()
                    update_play_button()
                    return
                set_playhead(current, center=False, redraw=False)
                keep_playhead_visible_for_playback()
                playback["after_id"] = win.after(16, update_playhead_during_playback)
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
            if self.preview_player is not None:
                try:
                    self.preview_player.play(playback_source, start)
                    playback["playing"] = True
                    playback["embedded"] = True
                    playback["started_at"] = None
                    playback["started_from"] = start
                    update_play_button()
                    cancel_playback_timer()
                    playback["after_id"] = win.after(16, update_playhead_during_playback)
                    return
                except Exception as exc:
                    self.log(f"低延遲播放器無法使用，暫時改用 ffplay：{exc}", "warn")
            player = find_ffplay()
            if not player:
                messagebox.showinfo("找不到播放器", "找不到低延遲播放器或 ffplay.exe，請重新執行 setup。")
                return
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
            playback["embedded"] = False
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
            draw_timeline()
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
            text_value = row.get("text")
            if hasattr(text_value, "detach"):
                text_value.detach()
            for widget in list(row.get("widgets", [])):
                try:
                    widget.destroy()
                except Exception:
                    pass
            row["widgets"] = []

        class CaptionTextValue:
            """字幕文字資料與目前頁面的 tk.Text 之間的輕量代理。"""

            def __init__(self, value: str = ""):
                self.value = (value or "").strip()
                self.widget = None
                self.row = None

            def attach(self, widget):
                self.widget = widget
                widget.delete("1.0", "end")
                widget.insert("1.0", self.value)

            def detach(self):
                if self.widget is not None:
                    try:
                        self.value = self.widget.get("1.0", "end").strip()
                    except Exception:
                        pass
                self.widget = None

            def get(self, _start="1.0", _end="end"):
                if self.widget is not None:
                    try:
                        self.value = self.widget.get("1.0", "end").strip()
                    except Exception:
                        pass
                return self.value

            def delete(self, _start="1.0", _end="end"):
                self.value = ""
                if self.widget is not None:
                    self.widget.delete("1.0", "end")

            def insert(self, _index, text):
                self.value = (text or "").strip()
                if self.widget is not None:
                    self.widget.delete("1.0", "end")
                    self.widget.insert("1.0", self.value)

            def focus_set(self):
                if self.row in rows:
                    ensure_caption_page(rows.index(self.row))
                if self.widget is not None:
                    self.widget.focus_set()

            def winfo_y(self):
                return self.widget.winfo_y() if self.widget is not None else 0

        def destroy_row_widgets(row: dict):
            if row.get("widgets"):
                destroy_row(row)

        def create_row_widgets(row: dict, global_index: int, local_index: int):
            num_btn = tk.Button(
                body, text=str(global_index + 1), width=4, bd=0, relief="flat",
                bg="#222020", fg=TEXT_ON_DARK, activebackground=GARNET,
                activeforeground="#FFFFFF", font=(EN_FONT, 12, "bold"),
                cursor="hand2", takefocus=0, highlightthickness=0,
                command=lambda r=row: select_row(row_index_for(r)),
            )
            start_entry = tk.Entry(
                body, textvariable=row["start"], width=13, bg=DARK_2, fg=TEXT_ON_DARK,
                disabledbackground=DARK_2, insertbackground=TEXT_ON_DARK, relief="flat", bd=0,
                highlightthickness=1, highlightbackground=LINE, highlightcolor=ORANGE,
                font=(EN_FONT, 12),
            )
            end_entry = tk.Entry(
                body, textvariable=row["end"], width=13, bg=DARK_2, fg=TEXT_ON_DARK,
                disabledbackground=DARK_2, insertbackground=TEXT_ON_DARK, relief="flat", bd=0,
                highlightthickness=1, highlightbackground=LINE, highlightcolor=ORANGE,
                font=(EN_FONT, 12),
            )
            text_box = tk.Text(
                body, height=2, wrap="word", bg=DARK_2, fg=TEXT_ON_DARK,
                insertbackground=TEXT_ON_DARK, relief="flat", bd=0, highlightthickness=1,
                highlightbackground=LINE, highlightcolor=ORANGE, padx=8, pady=5, font=(FONT, 13),
            )
            mark_english_widget(start_entry)
            mark_english_widget(end_entry)
            mark_cjk_text_widget(text_box)
            row["text"].attach(text_box)
            row["widgets"] = [num_btn, start_entry, end_entry, text_box]
            num_btn.grid(row=local_index, column=0, sticky="nw", padx=(0, 8), pady=(2, 6))
            start_entry.grid(row=local_index, column=1, sticky="nw", padx=(0, 8), pady=(4, 6))
            end_entry.grid(row=local_index, column=2, sticky="nw", padx=(0, 8), pady=(4, 6))
            text_box.grid(row=local_index, column=3, sticky="ew", pady=(2, 6))

            def on_caption_text_focus(_event, r=row):
                idx = row_index_for(r)
                begin_text_edit(idx)
                select_row(idx)

            text_box.bind("<FocusIn>", on_caption_text_focus, add="+")
            text_box.bind("<KeyRelease>", lambda _event: schedule_text_redraw())

        def render_caption_page(page_index: int | None = None):
            if page_index is not None:
                page_state["index"] = int(page_index)
            page_count = max(1, math.ceil(len(rows) / page_size))
            page_state["index"] = max(0, min(page_count - 1, page_state["index"]))
            for row in rows:
                if row.get("widgets"):
                    destroy_row_widgets(row)
            rendered_row_indices.clear()
            start = page_state["index"] * page_size
            end = min(len(rows), start + page_size)
            for local_idx, global_idx in enumerate(range(start, end)):
                create_row_widgets(rows[global_idx], global_idx, local_idx)
                rendered_row_indices.add(global_idx)
            page_label_var.set(
                f"第 {page_state['index'] + 1}/{page_count} 頁｜{start + 1 if rows else 0}-{end} / {len(rows)}"
            )
            try:
                body.update_idletasks()
                body._parent_canvas.yview_moveto(0)
            except Exception:
                pass
            apply_row_styles()

        def change_caption_page(delta: int):
            render_caption_page(page_state["index"] + delta)
            status_var.set(f"字幕列表：{page_label_var.get()}")

        def ensure_caption_page(row_index: int):
            if not rows:
                return
            target = max(0, min(len(rows) - 1, int(row_index))) // page_size
            if target != page_state["index"] or row_index not in rendered_row_indices:
                render_caption_page(target)

        def reflow_rows():
            target = selected_row_index() if rows else 0
            render_caption_page(target // page_size if rows else 0)
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
            text_value = CaptionTextValue((chunk.get("text") or "").strip())
            row.update({"start": start_var, "end": end_var, "text": text_value, "widgets": []})
            text_value.row = row
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
                    chunks = strip_chunks_for_srt_display(chunks)
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

        class TimelineValidationError(ValueError):
            def __init__(self, row_index: int, message: str):
                super().__init__(message)
                self.row_index = row_index

        def collect_chunks() -> list[dict]:
            updated = []
            previous_end = 0.0
            for idx, row in enumerate(rows, start=1):
                try:
                    start = parse_srt_time(row["start"].get())
                    end = parse_srt_time(row["end"].get())
                except Exception as exc:
                    raise TimelineValidationError(idx - 1, f"第 {idx} 組：{exc}") from exc
                if end <= start:
                    raise TimelineValidationError(idx - 1, f"第 {idx} 組結束時間必須晚於開始時間。")
                if idx > 1 and start < previous_end:
                    overlap_ms = round((previous_end - start) * 1000)
                    raise TimelineValidationError(
                        idx - 1,
                        f"第 {idx} 組開始時間早於前一組結束時間（重疊 {overlap_ms} ms）。",
                    )
                # 與匯出 SRT 一致：收集時即剝標點，避免編輯器與檔案不一致
                text = CORE.strip_punct_for_srt(row["text"].get("1.0", "end").strip())
                updated.append({"timestamp": (start, end), "text": text})
                previous_end = end
            return updated

        def check_timeline(show_ok: bool = True) -> list[dict] | None:
            try:
                updated = collect_chunks()
            except Exception as exc:
                status_var.set("時間軸需要修正")
                issue_index = getattr(exc, "row_index", None)
                if issue_index is not None and rows:
                    select_row(issue_index, center=True, update_playhead=True, focus_text=False)
                    scroll_text_row_to_view(issue_index)
                    try:
                        win.update_idletasks()
                    except Exception:
                        pass
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
            if not has_feature("custom_rules"):
                return
            if PERSONAL_RULES is None:
                return
            try:
                rules_path = PERSONAL_RULES_PATH
                history_path = EDIT_HISTORY_PATH
                store = PERSONAL_RULES.RuleStore(rules_path)
                edits = PERSONAL_RULES.iter_edits_for_input(
                    history_path,
                    data.get("inp", ""),
                    since=editor_opened_at,
                )
                # 也用 input_name 比對（新格式可能只存檔名）
                if not edits and data.get("inp"):
                    try:
                        name = Path(data.get("inp")).name
                        all_rows = []
                        if history_path.exists():
                            for line in history_path.read_text(encoding="utf-8-sig").splitlines():
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    row = json.loads(line)
                                except Exception:
                                    continue
                                if Path(str(row.get("input") or row.get("input_name") or "")).name == name:
                                    all_rows.append(row)
                        edits = all_rows
                    except Exception:
                        pass
                if not edits:
                    return
                candidates = PERSONAL_RULES.summarise_candidates(
                    edits,
                    existing_keys=store.existing_keys(),
                )
                if not candidates:
                    return
                # 一次匯出只問一次；候選直接在個人化規則庫顯示
                suggestion_state["done"] = True
                self.open_personal_rules_window(win)
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
        if PERSONAL_RULES is None:
            messagebox.showinfo("規則庫無法開啟", "找不到 core/personal_rules.py，請確認檔案完整。")
            return
        rules_path = PERSONAL_RULES_PATH
        try:
            store = PERSONAL_RULES.RuleStore(rules_path)
        except Exception as exc:
            messagebox.showerror("規則庫載入失敗", str(exc))
            return

        project_id, _, _ = _active_project_ids()
        project_label = _active_project_label()
        is_default = project_id == _default_project_id()

        anchor = parent or self
        win = ctk.CTkToplevel(anchor)
        win.title(f"個人化規則庫｜{project_label}")
        win.geometry("900x680")
        win.minsize(740, 520)
        win.configure(fg_color=BLACK_KITE)
        self.apply_window_icon(win, "_setting.png")
        win.transient(anchor)
        win.grab_set()
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(3, weight=1)

        # ── 標題 ───────────────────────────────────────────
        head = ctk.CTkFrame(win, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 4))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head,
            text=f"個人化規則庫｜{project_label}",
            text_color=TEXT_ON_DARK,
            font=(FONT, 22, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        stats_lbl = ctk.CTkLabel(head, text="", text_color=MUTED_ON_DARK, font=(FONT, 13), anchor="e")
        stats_lbl.grid(row=0, column=1, sticky="e")
        hint = (
            "目前未選專案，顯示「預設」規則庫。切換專案後會換成該專案自己的規則。"
            if is_default
            else f"目前專案：{project_label}。切換專案會看到另一套規則庫；AI 校對只套用此專案的規則。"
        )
        ctk.CTkLabel(
            head,
            text=hint + " 學習在背景累積，達門檻時出現「待確認候選」。",
            text_color=MUTED_ON_DARK, font=(FONT, 12), anchor="w", justify="left", wraplength=820,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # ── 新增詞庫 BAR ───────────────────────────────────
        add_bar = ctk.CTkFrame(win, fg_color=CARD_DARK, corner_radius=12)
        add_bar.grid(row=1, column=0, sticky="ew", padx=24, pady=(10, 4))
        add_bar.grid_columnconfigure(1, weight=1)
        add_bar.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(add_bar, text="新增詞庫", text_color=TEXT_ON_DARK, font=(FONT, 14, "bold")).grid(
            row=0, column=0, padx=(14, 10), pady=12, sticky="w"
        )
        wrong_var = ctk.StringVar(value="")
        right_var = ctk.StringVar(value="")
        ctk.CTkEntry(
            add_bar, textvariable=wrong_var, placeholder_text="錯誤寫法",
            height=36, fg_color=DARK_2, border_color=LINE, text_color=TEXT_ON_DARK, font=(FONT, 13),
        ).grid(row=0, column=1, sticky="ew", pady=12)
        ctk.CTkLabel(add_bar, text="→", text_color=MUTED_ON_DARK, font=(FONT, 16, "bold")).grid(
            row=0, column=2, padx=8
        )
        ctk.CTkEntry(
            add_bar, textvariable=right_var, placeholder_text="正確寫法",
            height=36, fg_color=DARK_2, border_color=LINE, text_color=TEXT_ON_DARK, font=(FONT, 13),
        ).grid(row=0, column=3, sticky="ew", pady=12)

        def add_word():
            b = wrong_var.get().strip()
            a = right_var.get().strip()
            if not b or not a:
                messagebox.showinfo("請填寫", "請輸入錯誤寫法與正確寫法。", parent=win)
                return
            if b == a:
                messagebox.showinfo("無需新增", "兩邊文字相同。", parent=win)
                return
            try:
                store.add(
                    b, a, domain="通用", source="manual", created_by="manual", state="active",
                    project_id=project_id, scope_type="project", scope_id=project_id,
                )
                store.save()
            except Exception as exc:
                messagebox.showerror("新增失敗", str(exc), parent=win)
                return
            wrong_var.set("")
            right_var.set("")
            self.log(f"規則庫新增（{project_label}）：{b} → {a}", "success")
            render_all()

        ctk.CTkButton(
            add_bar, text="新增", width=88, height=36, corner_radius=12,
            fg_color=ORANGE, hover_color=ORANGE_DARK, text_color="#FFFFFF",
            font=(FONT, 13, "bold"), command=add_word,
        ).grid(row=0, column=4, padx=(10, 14), pady=12)

        # ── 搜尋 ───────────────────────────────────────────
        filt = ctk.CTkFrame(win, fg_color="transparent")
        filt.grid(row=2, column=0, sticky="ew", padx=24, pady=(6, 0))
        filt.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(filt, text="搜尋", text_color=MUTED_ON_DARK, font=(FONT, 12)).grid(row=0, column=0, sticky="w")
        search_var = ctk.StringVar(value="")
        ctk.CTkEntry(
            filt, textvariable=search_var, placeholder_text="關鍵字",
            height=32, fg_color=DARK_2, border_color=LINE, text_color=TEXT_ON_DARK, font=(FONT, 12),
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        body = ctk.CTkScrollableFrame(
            win, fg_color=CARD_DARK, corner_radius=13,
            scrollbar_button_color=DARK, scrollbar_button_hover_color=ORANGE_DARK,
        )
        body.grid(row=3, column=0, sticky="nsew", padx=24, pady=(10, 8))
        body.grid_columnconfigure(0, weight=1)

        def load_candidates() -> list[dict]:
            if not _learning_enabled() or FEEDBACK_STORE is None or LEARNING is None:
                return []
            try:
                events = FEEDBACK_STORE.iter_events()
                # 只彙整「目前專案」的學習事件
                def _event_project(ev: dict) -> str:
                    pid = (ev.get("project_id") or "").strip()
                    if not pid:
                        return _default_project_id()
                    return PERSONAL_RULES.normalize_project_id(pid) if hasattr(PERSONAL_RULES, "normalize_project_id") else pid

                events = [e for e in events if _event_project(e) == project_id]
                extract = getattr(PERSONAL_RULES, "extract_candidates", None)
                return LEARNING.aggregate_candidates_from_events(
                    events,
                    extract_fn=extract,
                    existing_keys=store.existing_keys(project_id),
                    threshold=getattr(LEARNING, "DEFAULT_CANDIDATE_THRESHOLD", 2),
                    reject_ids=store.rejected_pair_keys(project_id) if hasattr(store, "rejected_pair_keys") else set(),
                )
            except Exception:
                return []

        def update_stats():
            rules = store.by_project(project_id) if hasattr(store, "by_project") else store.rules
            enabled = sum(1 for r in rules if r.get("enabled", True) and r.get("state", "active") == "active")
            cands = load_candidates()
            stats_lbl.configure(
                text=f"{project_label}｜規則 {len(rules)} 條（啟用 {enabled}）｜候選 {len(cands)}"
            )

        def render_all():
            for child in body.winfo_children():
                child.destroy()
            update_stats()
            row_i = 0
            candidates = load_candidates()
            if candidates:
                ctk.CTkLabel(
                    body,
                    text=f"待確認候選（重複修改達門檻，共 {len(candidates)} 條）",
                    text_color=ORANGE, font=(FONT, 14, "bold"), anchor="w",
                ).grid(row=row_i, column=0, sticky="w", padx=10, pady=(10, 4))
                row_i += 1
                for cand in candidates:
                    frame = ctk.CTkFrame(body, fg_color=DARK_2, corner_radius=10)
                    frame.grid(row=row_i, column=0, sticky="ew", padx=8, pady=3)
                    frame.grid_columnconfigure(0, weight=1)
                    ctk.CTkLabel(
                        frame,
                        text=f"「{cand['before']}」 → 「{cand['after']}」　確認 {cand.get('positive', 0)} 次",
                        text_color=TEXT_ON_DARK, font=(FONT, 13, "bold"), anchor="w",
                    ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
                    src = "、".join((cand.get("sources") or [])[:4])
                    ctk.CTkLabel(
                        frame,
                        text=f"來源：{src or '—'}（背景學習，非自動寫入規則）",
                        text_color=MUTED_ON_DARK, font=(FONT, 11), anchor="w",
                    ).grid(row=1, column=0, sticky="w", padx=12, pady=(2, 8))
                    btns = ctk.CTkFrame(frame, fg_color="transparent")
                    btns.grid(row=0, column=1, rowspan=2, padx=8)

                    def accept_cand(c=cand):
                        try:
                            store.add(
                                c["before"], c["after"], domain="通用",
                                source="learning_candidate", created_by="suggested",
                                state="active",
                                project_id=project_id, scope_type="project", scope_id=project_id,
                                evidence_event_ids=c.get("evidence_event_ids") or [],
                                confidence=c.get("confidence"),
                            )
                            store.save()
                            self.log(f"已加入規則（{project_label}）：{c['before']} → {c['after']}", "success")
                        except Exception as exc:
                            messagebox.showerror("加入失敗", str(exc), parent=win)
                            return
                        render_all()

                    def reject_cand(c=cand):
                        try:
                            if hasattr(store, "reject_pair_permanently"):
                                store.reject_pair_permanently(c["before"], c["after"], project_id=project_id)
                            store.save()
                        except Exception:
                            pass
                        render_all()

                    ctk.CTkButton(
                        btns, text="加入規則庫", width=100, height=30, corner_radius=10,
                        fg_color=ORANGE, hover_color=ORANGE_DARK, text_color="#FFFFFF",
                        font=(FONT, 12, "bold"), command=accept_cand,
                    ).pack(side="left", padx=2)
                    ctk.CTkButton(
                        btns, text="忽略", width=64, height=30, corner_radius=10,
                        fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK,
                        font=(FONT, 12, "bold"), command=reject_cand,
                    ).pack(side="left", padx=2)
                    row_i += 1

            ctk.CTkLabel(
                body, text="已儲存規則", text_color=TEXT_ON_DARK, font=(FONT, 14, "bold"), anchor="w",
            ).grid(row=row_i, column=0, sticky="w", padx=10, pady=(14, 4))
            row_i += 1

            kw = search_var.get().strip()
            visible = []
            project_rules = store.by_project(project_id) if hasattr(store, "by_project") else store.rules
            for r in project_rules:
                if r.get("state") == "rejected":
                    continue
                if kw and kw not in (r.get("before") or "") and kw not in (r.get("after") or ""):
                    continue
                visible.append(r)
            visible.sort(key=lambda r: (
                0 if r.get("state", "active") == "active" else 1,
                -(int(r.get("human_accept_count") or 0) + int(r.get("adopted_count") or 0)),
                r.get("created_at") or "",
            ))

            if not visible:
                ctk.CTkLabel(
                    body, text="（尚無規則。可用上方「新增詞庫」加入，或等候選出現後確認。）",
                    text_color=MUTED_ON_DARK, font=(FONT, 13),
                ).grid(row=row_i, column=0, sticky="w", padx=12, pady=16)
            for rule in visible:
                rid = rule.get("id", "")
                rf = ctk.CTkFrame(body, fg_color="transparent")
                rf.grid(row=row_i, column=0, sticky="ew", padx=8, pady=3)
                rf.grid_columnconfigure(1, weight=1)
                en_var = ctk.BooleanVar(value=bool(rule.get("enabled", True)) and rule.get("state", "active") == "active")

                def on_toggle(rid=rid, var=en_var):
                    store.set_enabled(rid, var.get())
                    if var.get() and hasattr(store, "set_state"):
                        store.set_state(rid, "active")
                    try:
                        store.save()
                    except Exception:
                        pass
                    update_stats()

                ctk.CTkSwitch(
                    rf, text="", variable=en_var, progress_color=ORANGE,
                    button_color="#FFFFFF", button_hover_color="#FFFFFF", fg_color="#5A5F68",
                    width=46, switch_width=44, switch_height=22, command=on_toggle,
                ).grid(row=0, column=0, padx=(2, 10), sticky="w")

                frozen = rule.get("state", "active") == "frozen"
                tag = "（已暫停）" if frozen else ""
                ctk.CTkLabel(
                    rf,
                    text=f"「{rule.get('before', '')}」  →  「{rule.get('after', '')}」{tag}",
                    text_color="#8A92A0" if frozen else TEXT_ON_DARK,
                    font=(FONT, 14, "bold"), anchor="w",
                ).grid(row=0, column=1, sticky="w")

                def on_delete(rid=rid, rule=rule):
                    if not messagebox.askyesno(
                        "刪除規則",
                        f"確定刪除？\n「{rule.get('before', '')}」→「{rule.get('after', '')}」",
                        parent=win,
                    ):
                        return
                    if not store.remove(rid):
                        messagebox.showerror("刪除失敗", "找不到要刪除的規則，請重新開啟規則庫。", parent=win)
                        return
                    try:
                        store.save()
                    except Exception as exc:
                        # 存檔失敗時恢復磁碟內容，避免畫面看似已刪除、重開後又出現。
                        try:
                            store.load()
                        except Exception:
                            pass
                        messagebox.showerror(
                            "刪除失敗",
                            f"規則未能寫入磁碟，因此沒有刪除。\n\n{exc}",
                            parent=win,
                        )
                        render_all()
                        return
                    self.log(
                        f"個人化規則已刪除：{rule.get('before', '')} → {rule.get('after', '')}",
                        "success",
                    )
                    render_all()

                def on_unfreeze(rid=rid):
                    if hasattr(store, "unfreeze"):
                        store.unfreeze(rid)
                    elif hasattr(store, "set_state"):
                        store.set_state(rid, "active")
                        store.set_enabled(rid, True)
                    try:
                        store.save()
                    except Exception:
                        pass
                    render_all()

                btnf = ctk.CTkFrame(rf, fg_color="transparent")
                btnf.grid(row=0, column=2, sticky="e")
                if frozen:
                    ctk.CTkButton(
                        btnf, text="恢復", width=58, height=30, corner_radius=10,
                        fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK,
                        font=(FONT, 12, "bold"), command=on_unfreeze,
                    ).pack(side="left", padx=(0, 4))
                ctk.CTkButton(
                    btnf, text="刪除", width=58, height=30, corner_radius=10,
                    fg_color="#3A2022", hover_color="#5A2B2F", text_color=TEXT_ON_DARK,
                    font=(FONT, 12, "bold"), command=on_delete,
                ).pack(side="left")
                row_i += 1

        search_var.trace_add("write", lambda *_: render_all())

        foot = ctk.CTkFrame(win, fg_color="transparent")
        foot.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 16))
        foot.grid_columnconfigure(0, weight=1)

        def on_enable_all():
            for r in store.by_project(project_id) if hasattr(store, "by_project") else store.rules:
                r["enabled"] = True
                if r.get("state") == "frozen":
                    continue
                r["state"] = "active"
            try:
                store.save()
            except Exception:
                pass
            render_all()

        def on_disable_all():
            for r in store.by_project(project_id) if hasattr(store, "by_project") else store.rules:
                r["enabled"] = False
            try:
                store.save()
            except Exception:
                pass
            render_all()

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
            foot, text="關閉", width=86, height=36, corner_radius=13,
            fg_color="#32333B", hover_color="#45464F", text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"), command=win.destroy,
        ).grid(row=0, column=2, sticky="e")

        render_all()

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

    def store_compare(self, inp, srt, txt, before_chunks, after_chunks, before_text, after_text, ai_meta=None):
        self.last_compare = {
            "inp": inp,
            "srt": srt,
            "txt": txt,
            "before_chunks": before_chunks,
            "after_chunks": after_chunks,
            "before_text": before_text,
            "after_text": after_text,
            "ai_meta": dict(ai_meta or {}),
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
            self.write_srt_output(data["srt"], after_chunks)
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

        def _tc_for(idx: int) -> tuple[float | None, float | None]:
            before_chunks = data.get("before_chunks") or []
            if 0 <= idx < len(before_chunks):
                ts = before_chunks[idx].get("timestamp") or (None, None)
                return ts[0], ts[1]
            return None, None

        def accept_current():
            idx = current_review.get("index")
            if idx is None:
                return
            before_text = chunk_text(data.get("before_chunks") or [], idx)
            ai_text = chunk_text(data.get("after_chunks") or [], idx)
            edited = corrected_box.get("1.0", "end").strip()
            if save_current_text():
                final = edited or ai_text
                t0, t1 = _tc_for(idx)
                # 使用者改過文字 → manual_edit；否則 accept_ai
                action = "manual_edit" if final != ai_text and final != before_text else "accept_ai"
                if final == before_text and final != ai_text:
                    action = "restore_original"
                record_review_feedback(
                    action=action,
                    original_text=before_text,
                    ai_text=ai_text,
                    final_text=final,
                    timecode_start=t0,
                    timecode_end=t1,
                    input_path=str(data.get("inp") or ""),
                    source="quick_compare",
                )
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
                before_text = chunk_text(before_chunks, idx)
                ai_text = chunk_text(after_chunks, idx)
                # 還原時直接剝標點，讓還原結果與 SRT 輸出一致（無標點）
                restored = CORE.strip_punct_for_srt(before_text)
                after_chunks[idx]["text"] = restored
                self.persist_compare_after_chunks()
                t0, t1 = _tc_for(idx)
                record_review_feedback(
                    action="restore_original",
                    original_text=before_text,
                    ai_text=ai_text,
                    final_text=restored,
                    timecode_start=t0,
                    timecode_end=t1,
                    input_path=str(data.get("inp") or ""),
                    source="quick_compare",
                )
                reviewed.add(idx)
                review_pos["value"] += 1
                refresh_summary()
                render_diff_list()
                load_review_item()

        def skip_current():
            idx = current_review.get("index")
            if idx is None:
                return
            before_text = chunk_text(data.get("before_chunks") or [], idx)
            ai_text = chunk_text(data.get("after_chunks") or [], idx)
            t0, t1 = _tc_for(idx)
            record_review_feedback(
                action="skip",
                original_text=before_text,
                ai_text=ai_text,
                final_text=ai_text,
                timecode_start=t0,
                timecode_end=t1,
                input_path=str(data.get("inp") or ""),
                source="quick_compare",
            )
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
            self.write_srt_output(data["srt"], data["before_chunks"])
            count += 1
        if data.get("txt"):
            Path(data["txt"]).write_text((data.get("before_text") or "") + "\n", encoding="utf-8-sig")
            count += 1
        self.log(f"已還原 {count} 個輸出檔案為原始辨識。", "warn")
        messagebox.showinfo("已還原", f"已還原 {count} 個輸出檔案。")

    # ── v2.4：外部 SRT／專案／學習／模板／實驗 ─────────────────

    def open_external_srt(self):
        """直接開啟外部 SRT（不必先跑轉寫）。可選對應媒體以播放／波形。"""
        srt_path = filedialog.askopenfilename(
            title="開啟外部 SRT",
            filetypes=[("SRT 字幕", "*.srt"), ("所有檔案", "*.*")],
        )
        if not srt_path:
            return
        try:
            payload = Path(srt_path).read_text(encoding="utf-8-sig")
            chunks = strip_chunks_for_srt_display(parse_srt_text(payload))
        except Exception as exc:
            messagebox.showerror("讀取失敗", f"無法解析 SRT：\n{exc}")
            return
        if not chunks:
            messagebox.showinfo("沒有字幕", "此 SRT 沒有可解析的字幕段落。")
            return
        media = filedialog.askopenfilename(
            title="選擇對應影音（可取消略過）",
            filetypes=[
                ("影音", " ".join(f"*{e}" for e in sorted(MEDIA_EXTS))),
                ("所有檔案", "*.*"),
            ],
        )
        result = {
            "inp": media or srt_path,
            "srt": srt_path,
            "txt": "",
            "chunks": clone_chunks(chunks),
            "external": True,
        }
        self.last_result = result
        if not getattr(self, "batch_results", None):
            self.batch_results = []
        self.batch_results.append(result)
        self.srt_editor_btn.configure(state="normal")
        self.result_label.configure(text=f"外部 SRT：{Path(srt_path).name}｜{len(chunks)} 組")
        self.log(f"已載入外部 SRT：{srt_path}（{len(chunks)} 組）", "success")
        self.open_srt_editor()

    def _project_button_label(self) -> str:
        """膠囊／細長條上的專案名；未選時寫「預設」。"""
        if PROJECT_PROFILES is not None:
            try:
                act = PROJECT_PROFILES.get_active()
                if act and act.get("name"):
                    name = str(act.get("name")).strip()
                    if len(name) > 36:
                        name = name[:36] + "…"
                    return f"▸ {name}"
            except Exception:
                pass
        return "▸ 預設（可選）"

    def refresh_project_label(self):
        label = self._project_button_label()
        try:
            if hasattr(self, "project_btn") and self.project_btn is not None:
                self.project_btn.configure(text=label)
        except Exception:
            pass
        try:
            if hasattr(self, "project_strip_label") and self.project_strip_label is not None:
                self.project_strip_label.configure(text=self._project_strip_text())
        except Exception:
            pass

    def open_project_profiles_window(self, parent=None):
        if not has_feature("project_profiles") and not has_feature("custom_rules"):
            self.show_supporter_message("project_profiles")
            return
        if PROJECT_PROFILES is None:
            messagebox.showinfo("無法開啟", "專案模組未載入。")
            return
        anchor = parent or self
        win = ctk.CTkToplevel(anchor)
        win.title("選擇專案")
        win.geometry("580x500")
        win.configure(fg_color=BLACK_KITE)
        win.transient(anchor)
        win.overrideredirect(True)

        def _release_project_grab():
            try:
                current = win.grab_current()
                if current is not None:
                    current.grab_release()
            except Exception:
                pass

        def _restore_project_grab():
            try:
                if win.winfo_exists():
                    win.lift()
                    win.focus_force()
            except Exception:
                pass

        def _close_window():
            _release_project_grab()
            try:
                win.destroy()
            finally:
                try:
                    anchor.after_idle(anchor.focus_force)
                except Exception:
                    pass

        def _run_child_modal(callback):
            _release_project_grab()
            try:
                return callback()
            finally:
                _restore_project_grab()

        win.protocol("WM_DELETE_WINDOW", _close_window)
        win.bind("<Escape>", lambda _event: _close_window())

        shell = ctk.CTkFrame(
            win, fg_color=BLACK_KITE, corner_radius=0,
            border_width=1, border_color=LINE,
        )
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(2, weight=1)

        title_bar = ctk.CTkFrame(shell, fg_color=DARK_2, corner_radius=0, height=42)
        title_bar.grid(row=0, column=0, sticky="ew")
        title_bar.grid_columnconfigure(0, weight=1)
        title_label = ctk.CTkLabel(
            title_bar, text="選擇專案", text_color=TEXT_ON_DARK,
            font=(FONT, 14, "bold"), anchor="w",
        )
        title_label.grid(row=0, column=0, sticky="ew", padx=16, pady=8)
        close_button = ctk.CTkButton(
            title_bar, text="×", width=42, height=32, corner_radius=8,
            fg_color="transparent", hover_color=GARNET,
            text_color=TEXT_ON_DARK, font=(FONT, 20), command=_close_window,
        )
        close_button.grid(row=0, column=1, padx=5, pady=5)

        move_state = {"x": 0, "y": 0}

        def start_window_move(event):
            move_state["x"] = event.x_root - win.winfo_x()
            move_state["y"] = event.y_root - win.winfo_y()

        def move_window(event):
            win.geometry(
                f"+{event.x_root - move_state['x']}+{event.y_root - move_state['y']}"
            )

        for widget in (title_bar, title_label):
            widget.bind("<ButtonPress-1>", start_window_move)
            widget.bind("<B1-Motion>", move_window)

        heading = ctk.CTkFrame(shell, fg_color="transparent")
        heading.grid(row=1, column=0, sticky="ew", padx=20, pady=(16, 8))
        ctk.CTkLabel(
            heading, text="選擇這次要用的專案",
            text_color=TEXT_ON_DARK, font=(FONT, 18, "bold"), anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            heading,
            text="可複選、拖曳排序；在專案上按右鍵可複製或刪除。",
            text_color=MUTED_ON_DARK, font=(FONT, 12),
            justify="left", anchor="w",
        ).pack(fill="x", pady=(3, 0))

        body = ctk.CTkFrame(shell, fg_color=CARD_DARK, corner_radius=12)
        body.grid(row=2, column=0, sticky="nsew", padx=20, pady=8)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        canvas = tk.Canvas(
            body, bg=CARD_DARK, highlightthickness=0, bd=0,
            selectborderwidth=0, cursor="arrow",
        )
        canvas.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scrollbar = ctk.CTkScrollbar(body, command=canvas.yview, width=12)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 8), pady=8)
        canvas.configure(yscrollcommand=scrollbar.set)

        selected_ids: set[str] = set()
        row_bounds: list[tuple[str, float, float]] = []
        drag_state = {
            "kind": "", "start_x": 0.0, "start_y": 0.0,
            "dragging": False, "target": None, "base": set(), "last_index": None,
        }
        row_height = 60
        row_top = 8

        def _rounded_points(x1: float, y1: float, x2: float, y2: float, radius: float = 12):
            radius = max(2.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
            points = []
            for cx, cy, start in (
                (x2 - radius, y1 + radius, -90),
                (x2 - radius, y2 - radius, 0),
                (x1 + radius, y2 - radius, 90),
                (x1 + radius, y1 + radius, 180),
            ):
                for offset in range(0, 91, 15):
                    angle = math.radians(start + offset)
                    points.extend((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
            return points

        def _profile_ids() -> list[str]:
            return [str(p.get("id") or "") for p in PROJECT_PROFILES.profiles]

        def _row_index_at(y: float, x: float | None = None) -> int | None:
            if x is not None:
                width = max(canvas.winfo_width(), 460)
                if x < 8 or x > width - 10:
                    return None
            for index, (_pid, top, bottom) in enumerate(row_bounds):
                if top <= y <= bottom:
                    return index
            return None

        def _draw_insert_indicator(target: int | None):
            if target is None:
                return
            y = row_top + max(0, min(target, len(row_bounds))) * row_height - 2
            width = max(canvas.winfo_width(), 420)
            canvas.create_line(
                16, y, width - 18, y, fill=ORANGE, width=4,
                tags=("drag_indicator",),
            )

        def render():
            old_view = canvas.yview()
            canvas.delete("all")
            row_bounds.clear()
            profiles = PROJECT_PROFILES.profiles
            if not profiles:
                canvas.create_text(
                    18, 24, text="尚無專案，請按下方「新增」。",
                    fill=MUTED_ON_DARK, font=(FONT, 13), anchor="nw",
                )
                canvas.configure(scrollregion=(0, 0, 1, 70))
                return
            active = PROJECT_PROFILES.active_id
            width = max(canvas.winfo_width(), 460)
            for i, p in enumerate(profiles):
                pid = str(p.get("id") or "")
                top = row_top + i * row_height
                bottom = top + 52
                row_bounds.append((pid, top, bottom))
                is_selected = pid in selected_ids
                fill = "#46413F" if is_selected else DARK_2
                outline = ORANGE if is_selected else fill
                canvas.create_polygon(
                    *_rounded_points(8, top, width - 10, bottom, 12),
                    fill=fill, outline=outline, width=2 if is_selected else 1,
                    smooth=True,
                )
                mark = "● " if p.get("id") == active else "○ "
                canvas.create_text(
                    24, top + 26, text=f"{mark}{p.get('name')}",
                    fill=TEXT_ON_DARK, font=(FONT, 13), anchor="w",
                )
                canvas.create_polygon(
                    *_rounded_points(width - 100, top + 10, width - 22, top + 42, 10),
                    fill=ORANGE, outline=ORANGE, smooth=True,
                )
                canvas.create_text(
                    width - 61, top + 26, text="選用",
                    fill="#FFFFFF", font=(FONT, 10),
                )
            total_height = row_top * 2 + len(profiles) * row_height
            canvas.configure(scrollregion=(0, 0, width, total_height))
            if old_view and old_view[0] > 0:
                canvas.yview_moveto(old_view[0])

        def _activate(pid):
            PROJECT_PROFILES.set_active(pid)
            PROJECT_PROFILES.save()
            self.refresh_project_label()
            self.refresh_notes_history_menu()
            # 選完收成細長條
            self.set_project_bar_expanded(False)
            _close_window()

        def _delete_selected(_event=None):
            ids = [pid for pid in _profile_ids() if pid in selected_ids]
            if not ids:
                return
            names = [
                str(p.get("name") or "未命名專案")
                for p in PROJECT_PROFILES.profiles if str(p.get("id") or "") in selected_ids
            ]
            preview = "\n".join(f"• {name}" for name in names[:8])
            if len(names) > 8:
                preview += f"\n• 另有 {len(names) - 8} 個專案"
            confirmed = _run_child_modal(lambda: messagebox.askyesno(
                "確認刪除專案",
                f"確定要刪除以下 {len(names)} 個專案嗎？\n\n{preview}\n\n此動作無法復原。",
                parent=win,
            ))
            if not confirmed:
                return
            for pid in ids:
                PROJECT_PROFILES.remove(pid)
            PROJECT_PROFILES.save()
            selected_ids.clear()
            self.refresh_project_label()
            self.refresh_notes_history_menu()
            render()

        def _duplicate_selected():
            ids = [pid for pid in _profile_ids() if pid in selected_ids]
            if not ids:
                return
            copies = PROJECT_PROFILES.duplicate(ids)
            PROJECT_PROFILES.save()
            selected_ids.clear()
            selected_ids.update(str(p.get("id") or "") for p in copies)
            render()

        context_menu = tk.Menu(
            win, tearoff=0, bg=DARK_2, fg=TEXT_ON_DARK,
            activebackground=ORANGE, activeforeground="#FFFFFF",
            relief="flat", bd=0, font=(FONT, 11),
        )
        context_menu.add_command(label="複製", command=_duplicate_selected)
        context_menu.add_separator()
        context_menu.add_command(label="刪除…", command=_delete_selected)

        def on_right_click(event):
            y = canvas.canvasy(event.y)
            x = canvas.canvasx(event.x)
            index = _row_index_at(y, x)
            if index is not None:
                pid = row_bounds[index][0]
                if pid not in selected_ids:
                    selected_ids.clear()
                    selected_ids.add(pid)
                    render()
            if not selected_ids:
                return
            _release_project_grab()
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                try:
                    context_menu.grab_release()
                except Exception:
                    pass
                _restore_project_grab()

        def on_left_press(event):
            y = canvas.canvasy(event.y)
            x = canvas.canvasx(event.x)
            index = _row_index_at(y, x)
            ctrl = bool(event.state & 0x0004)
            shift = bool(event.state & 0x0001)
            drag_state.update({
                "start_x": x, "start_y": y, "dragging": False,
                "target": None, "base": set(selected_ids), "last_index": index,
            })
            if index is None:
                drag_state["kind"] = "marquee"
                if not ctrl:
                    selected_ids.clear()
                drag_state["base"] = set(selected_ids)
                render()
                return
            pid = row_bounds[index][0]
            width = max(canvas.winfo_width(), 460)
            if x >= width - 112:
                _activate(pid)
                return
            drag_state["kind"] = "row"
            if shift and drag_state.get("last_index") is not None and selected_ids:
                selected_indices = [
                    i for i, item_id in enumerate(_profile_ids()) if item_id in selected_ids
                ]
                anchor_index = selected_indices[-1] if selected_indices else index
                lo, hi = sorted((anchor_index, index))
                selected_ids.update(_profile_ids()[lo:hi + 1])
            elif ctrl:
                if pid in selected_ids:
                    selected_ids.remove(pid)
                else:
                    selected_ids.add(pid)
            elif pid not in selected_ids:
                selected_ids.clear()
                selected_ids.add(pid)
            render()

        def on_left_motion(event):
            if not drag_state["kind"]:
                return
            y = canvas.canvasy(event.y)
            x = canvas.canvasx(event.x)
            if event.y < 22:
                canvas.yview_scroll(-1, "units")
                y = canvas.canvasy(event.y)
            elif event.y > canvas.winfo_height() - 22:
                canvas.yview_scroll(1, "units")
                y = canvas.canvasy(event.y)
            if drag_state["kind"] == "row":
                if abs(y - drag_state["start_y"]) < 5:
                    return
                drag_state["dragging"] = True
                target = int((y - row_top + row_height / 2) // row_height)
                drag_state["target"] = max(0, min(target, len(row_bounds)))
                render()
                _draw_insert_indicator(drag_state["target"])
                return
            drag_state["dragging"] = True
            x1, x2 = sorted((drag_state["start_x"], x))
            y1, y2 = sorted((drag_state["start_y"], y))
            selected_ids.clear()
            selected_ids.update(drag_state["base"])
            if x2 >= 8 and x1 <= max(canvas.winfo_width(), 460) - 10:
                for pid, top, bottom in row_bounds:
                    if y2 >= top and y1 <= bottom:
                        selected_ids.add(pid)
            render()
            canvas.create_rectangle(
                x1, y1, x2, y2, outline=ORANGE, width=1,
                dash=(4, 3), tags=("selection_marquee",),
            )

        def on_left_release(_event):
            if drag_state["kind"] == "row" and drag_state["dragging"]:
                target = drag_state.get("target")
                if target is not None and PROJECT_PROFILES.reorder(selected_ids, target):
                    PROJECT_PROFILES.save()
            drag_state.update({"kind": "", "dragging": False, "target": None})
            render()

        def on_double_click(event):
            """雙擊專案列即可直接切換，不必精準點選右側按鈕。"""
            if event.state & 0x0004 or event.state & 0x0001:
                return
            y = canvas.canvasy(event.y)
            x = canvas.canvasx(event.x)
            index = _row_index_at(y, x)
            if index is not None:
                _activate(row_bounds[index][0])

        def select_all(_event=None):
            selected_ids.clear()
            selected_ids.update(_profile_ids())
            render()
            return "break"

        def on_mousewheel(event):
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"

        canvas.bind("<ButtonPress-1>", on_left_press)
        canvas.bind("<B1-Motion>", on_left_motion)
        canvas.bind("<ButtonRelease-1>", on_left_release)
        canvas.bind("<Double-Button-1>", on_double_click)
        canvas.bind("<Button-3>", on_right_click)
        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Control-a>", select_all)
        canvas.bind("<Delete>", _delete_selected)
        canvas.bind("<Configure>", lambda _event: render())
        canvas.configure(takefocus=True)

        def add_profile():
            name = _run_child_modal(
                lambda: simple_prompt(win, "專案名稱")
            )
            if not name:
                return
            guests = _run_child_modal(
                lambda: simple_prompt(win, "固定用語／受訪者（可空白）")
            ) or ""
            profile = PROJECT_PROFILES.upsert(
                name=name, series_name=name, domain="通用", guests=guests, terms=guests,
            )
            PROJECT_PROFILES.set_active(profile.get("id") or "")
            PROJECT_PROFILES.save()
            self.refresh_project_label()
            self.refresh_notes_history_menu()
            self.set_project_bar_expanded(False)
            _close_window()

        def _clear():
            PROJECT_PROFILES.set_active("")
            PROJECT_PROFILES.save()
            self.refresh_project_label()
            # 清回預設後展開說明，方便再選
            self.set_project_bar_expanded(True)
            render()

        foot = ctk.CTkFrame(shell, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=20, pady=(4, 16))
        ctk.CTkButton(
            foot, text="新增", width=90, height=36, corner_radius=12,
            fg_color=ORANGE, hover_color=ORANGE_DARK, text_color="#FFFFFF",
            font=(FONT, 13, "bold"), command=add_profile,
        ).pack(side="left")
        ctk.CTkButton(
            foot, text="清除選用", width=100, height=36, corner_radius=12,
            fg_color=DARK, hover_color=GARNET, text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"), command=_clear,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            foot, text="關閉", width=90, height=36, corner_radius=12,
            fg_color="#32333B", hover_color="#45464F", text_color=TEXT_ON_DARK,
            font=(FONT, 13, "bold"), command=_close_window,
        ).pack(side="right")
        render()
        win.update_idletasks()
        x = anchor.winfo_rootx() + max(0, (anchor.winfo_width() - win.winfo_width()) // 2)
        y = anchor.winfo_rooty() + max(0, (anchor.winfo_height() - win.winfo_height()) // 2)
        win.geometry(f"+{x}+{y}")


def simple_prompt(parent, title: str, default: str = "") -> str | None:
    """簡易單行輸入對話框。"""
    dialog = ctk.CTkToplevel(parent)
    dialog.title(title)
    dialog.geometry("420x160")
    dialog.configure(fg_color=BLACK_KITE)
    dialog.transient(parent)
    dialog.grab_set()
    var = ctk.StringVar(value=default)
    ctk.CTkLabel(dialog, text=title, text_color=TEXT_ON_DARK, font=(FONT, 14, "bold")).pack(
        anchor="w", padx=16, pady=(16, 8)
    )
    entry = ctk.CTkEntry(
        dialog, textvariable=var, height=36, width=360,
        fg_color=DARK_2, border_color=LINE, text_color=TEXT_ON_DARK, font=(FONT, 13),
    )
    entry.pack(padx=16)
    entry.focus_set()
    result = {"value": None}

    def ok():
        result["value"] = var.get().strip()
        dialog.destroy()

    def cancel():
        result["value"] = None
        dialog.destroy()

    row = ctk.CTkFrame(dialog, fg_color="transparent")
    row.pack(fill="x", padx=16, pady=14)
    ctk.CTkButton(
        row, text="確定", width=90, fg_color=ORANGE, hover_color=ORANGE_DARK,
        text_color="#FFFFFF", font=(FONT, 13, "bold"), command=ok,
    ).pack(side="right")
    ctk.CTkButton(
        row, text="取消", width=90, fg_color=DARK, hover_color=GARNET,
        text_color=TEXT_ON_DARK, font=(FONT, 13, "bold"), command=cancel,
    ).pack(side="right", padx=8)
    dialog.bind("<Return>", lambda _e: ok())
    dialog.wait_window()
    return result["value"]

# 2026-07-14：v2.4 學習閉環、專案範圍、外部 SRT、下載體驗、模板詞庫、效能實驗
if __name__ == "__main__":
    enable_dpi_awareness()
    set_app_user_model_id()
    App().mainloop()
