# -*- coding: utf-8 -*-
"""SanWich 功能旗標（Free / Supporter）。

核心原則：核心免費，進階支持；防君子，不防小人。
Free 功能永久可用；Supporter 功能於 Trial 期間或輸入 Supporter Key 後解鎖。
詳見 SUPPORTER_PLAN.md（內部文件）。
"""

FREE_FEATURES = {
    "single_transcription",   # 單檔音訊/影片轉寫
    "export_srt",             # SRT 輸出
    "export_txt",             # TXT 輸出
    "basic_ai_proofread",     # 基本 AI 校對
    "basic_srt_editor",       # 基本 SRT 編輯器
    "find_replace",           # 尋找 / 取代
    "import_srt",             # 匯入外部 SRT
    "davinci_tools",          # DaVinci Tools（永久免費）
}

SUPPORTER_FEATURES = {
    "batch_processing",         # 批次處理
    "quick_compare_full",       # AI 修改快速對照完整版
    "custom_rules",             # 個人化規則庫
    "learning_loop",            # 學習閉環（回饋事件／候選規則）
    "diarization",              # 語者分離（TXT／可選 SRT 標註語者）
    "domain_prompt_templates",  # 領域 Prompt 模板
    "custom_dictionary",        # 自訂詞庫
    "project_profiles",         # 專案／系列設定
    "supporter_badge",          # Supporter 標章
    "early_access",             # 早期功能／效能實驗入口
}

# UI 顯示名稱（供提示彈窗使用）
FEATURE_LABELS = {
    "batch_processing": "批次處理",
    "quick_compare_full": "快速對照完整版",
    "custom_rules": "個人化規則庫",
    "learning_loop": "學習閉環",
    "diarization": "語者分離",
    "domain_prompt_templates": "領域 Prompt 模板",
    "custom_dictionary": "自訂詞庫",
    "project_profiles": "專案／系列設定",
    "supporter_badge": "Supporter 標章",
    "early_access": "早期功能測試入口",
}


def is_free_feature(feature_name: str) -> bool:
    return feature_name in FREE_FEATURES


def is_supporter_feature(feature_name: str) -> bool:
    return feature_name in SUPPORTER_FEATURES
