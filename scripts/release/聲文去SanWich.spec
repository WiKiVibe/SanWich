# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for 聲文去SanWich
# 使用方式（在專案根目錄）：
#   .venv\Scripts\pip install pyinstaller
#   .venv\Scripts\pyinstaller --clean scripts\release\聲文去SanWich.spec
# 產出：dist\SanWich\SanWich.exe

from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH).resolve().parents[1]

datas = [
    ('assets/images/_LOGO.ico',   'assets/images'),
    ('assets/images/_LOGO.png',   'assets/images'),
    ('assets/images/_setting.ico','assets/images'),
    ('assets/images/_setting.png','assets/images'),
    ('assets/images/_Bubble-tea.png','assets/images'),
    ('assets/images/_portaly_wikivibe.png','assets/images'),
    ('assets/fonts/Noto_Sans_TC/NotoSansTC-VariableFont_wght.ttf', 'assets/fonts/Noto_Sans_TC'),
    ('assets/fonts/Noto_Sans_TC/README.txt', 'assets/fonts/Noto_Sans_TC'),
    ('assets/fonts/Noto_Sans_TC/OFL.txt',    'assets/fonts/Noto_Sans_TC'),
    ('assets/fonts/TASA_Explorer/TASAExplorer-VariableFont_wght.ttf', 'assets/fonts/TASA_Explorer'),
    ('assets/fonts/TASA_Explorer/README.txt', 'assets/fonts/TASA_Explorer'),
    ('assets/fonts/TASA_Explorer/OFL.txt',    'assets/fonts/TASA_Explorer'),
    ('core/SanWich_legacy_core.py', 'core'),
    ('core/features.py', 'core'),
    ('core/license_manager.py', 'core'),
    ('core/license_service.py', 'core'),
    ('core/updater.py', 'core'),
    ('core/personal_rules.py', 'core'),
    ('core/learning.py', 'core'),
    ('core/prompt_templates.py', 'core'),
    ('core/experiments.py', 'core'),
    ('core/diarization.py', 'core'),
    # 安全：絕不打包含真實 API Key 的 config.json；缺檔時程式會用預設值自動重建
    ('config.example.json', '.'),
    ('docs/申請API_Key教學.md', 'docs'),
    ('scripts/update/update_helper.ps1', '.'),
]

# 只保留真的存在的檔案，並轉成絕對路徑，避免 PyInstaller 以 spec 目錄解析。
datas = [(str(ROOT / src), dst) for src, dst in datas if (ROOT / src).exists()]

hiddenimports = [
    'customtkinter',
    'tkinterdnd2',
    'PIL._tkinter_finder',
]

# 跑得起來的最低需求；torch/transformers 由獨立 .venv 提供，
# 不要塞進 EXE（會 3GB 起跳）。EXE 啟動後再去找系統 .venv 或 PATH 上的 Python。
excludes = [
    'torch',
    'torchaudio',
    'torchvision',
    'transformers',
    'accelerate',
    'numpy.tests',
    'tests',
]

a = Analysis(
    [str(ROOT / 'SanWich.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SanWich',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'assets/images/_LOGO.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SanWich',
)
