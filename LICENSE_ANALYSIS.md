# SanWich 授權現況分析

分析入口：`SanWich.py`  2026-07-23

## 現行實際流程

1. `SanWich.py` 在啟動時動態載入 `core/license_manager.py`。
2. 建立全域 `LICENSE_MANAGER = LicenseManager()`。
3. `LicenseManager.load_or_create_license()` 依序讀取：
   - `%APPDATA%\\SanWich\\license.json`
   - `%LOCALAPPDATA%\\SanWich\\license_anchor.json`
   - `HKCU\\Software\\WiKiVibe\\SanWich\\LicenseState`
4. 有效副本以內建 HMAC salt 驗證；多份副本會採最早 Trial 日期，並優先保留有效 `SW2` Key。
5. 未存在任何狀態時建立 14 天 Trial；已有損壞狀態時回 Free，不重置 Trial。
6. `SanWich.py` 的所有功能入口透過全域 `has_feature()` 呼叫 `LicenseManager.has_feature()`。
7. 設定頁直接呼叫 `LICENSE_MANAGER.activate_key()`，現行啟用完全離線。

## 現行權限真相

| 判斷 | 來源 |
| --- | --- |
| 免費功能 | `core/features.py` 的 `FREE_FEATURES` |
| Trial | `trial_ends_at >= date.today()` |
| 舊版完整版 | `verify_supporter_key(supporter_key)` 的 RSA 簽章 |
| `edition`、`supporter_enabled` | 狀態紀錄，不是最終權限真相 |
| Debug | 根目錄 `debug_edition.txt`，不應進發佈包 |

## 主要使用位置

- Prompt／學習：`learning_loop`、`custom_rules`、`domain_prompt_templates`、`custom_dictionary`、`project_profiles`
- 批次轉寫：`batch_processing`
- 語者分離：`diarization`
- 設定頁：狀態摘要、Key 輸入、啟用按鈕
- 鎖定提示：`show_supporter_message()`

## 與新版 Server 的差異

| 項目 | 現行 | 新版 |
| --- | --- | --- |
| Key | `SW2`，本機 RSA 驗證 | Worker/D1 管理，Key 雜湊不落明文 |
| 裝置 | 無綁定 | 每組 Key 預設 2 台 |
| 遠端撤銷 | 不支援 | 支援，下一次線上 Verify 生效 |
| 離線 | 永久 | 30 天複驗，逾期進 Grace，最後回基本功能 |
| Token | 無 | Ed25519 簽章 Token |
| 舊 Key | 直接解鎖 | 只在明確 Migration 流程使用 |
| 本機狀態 | 三份 `license.json` | `license_v2.json` 與備援 Token，裝置密鑰另存 DPAPI |

## 整合風險與處理原則

- 不刪除現有 `license.json`、Trial 錨點或 Registry；新版沒有 Token 時仍保留舊流程，避免升級重置試用。
- 新版有 Token 時，正式完整版權限只由簽章 Token 決定，不再用舊 `SW2` Key 當長期 fallback。
- 沒有 Server 設定或 `cryptography` 尚未安裝時，保留舊版離線流程，避免現有版本立即失效。
- 舊 Key 遷移必須由使用者在 UI 明確觸發；不在背景自動上傳完整 Key。
- 目前 Server API 使用 fingerprint claim，尚未實作 nonce challenge；DPAPI 裝置密鑰先作為本機穩定裝置身分，不能宣稱已完成公鑰持有證明。
- SanWich 與正式 WiKiVibe License Server 均使用 14 天 Grace。

## 本階段修改範圍

- 新增 `core/license_service.py`。
- 下一步由 `core/license_manager.py` 做相容 facade 接入。
- `SanWich.py` 的 UI 先保留內部 `supporter` 識別字，對外文字再逐段改成「完整版／Full」。
- 真正線上啟用前，需在設定或環境提供 API URL、Issuer 與公開金鑰；沒有這三項不會發出網路請求。
