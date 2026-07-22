# SanWich 授權現況與遷移計畫

> 文件狀態：盤點與規劃完成，尚未實作  
> 盤點基準：2026-07-22 工作區現況  
> 本次範圍：只新增文件，不修改正式程式碼

## 1. 現況摘要

- 現行授權是本機信任制：30 天 Supporter Trial 加上可永久離線驗證的 `SW2` Supporter Key。
- 第一次啟動會建立試用資料；試用到期只回到 Free，不鎖住核心功能。
- 授權狀態同時寫入 `%APPDATA%`、`%LOCALAPPDATA%` 與 Windows 登錄檔。刪除其中一份會由其他有效副本復原。
- 正式 Supporter 判定只看 `supporter_key` 的 RSA 簽章是否有效；`edition` 與 `supporter_enabled` 不是權限真相來源。
- 現行 Key 不連伺服器、不綁裝置、沒有遠端撤銷、到期日或裝置數限制。
- 本機授權檔的 HMAC salt 隨開源用戶端一起發佈，只能偵測一般誤改，不能視為伺服器等級防偽。
- 新版應保留主程式對外的 `has_feature(feature_name)` 介面，先替換授權來源，再分階段改掉 Supporter 命名，降低功能回歸風險。
- 目前還有一個邊界行為：若既有授權狀態損壞，程式先回到缺少 `trial_started_at` 的 Free 狀態；此時即使 `activate_key()` 當下接受有效 Key，下一次啟動仍會因 `_valid_state()` 要求 `trial_started_at` 而判定無效。新版實作前應補測並修正這條路徑。

## 2. 目前授權流程

### 2.1 啟動載入

1. `SanWich.py` 以動態載入方式讀取 `core/license_manager.py`。
2. 建立 `LicenseManager()`，呼叫 `load_or_create_license()`。
3. 依序讀取三個狀態來源：
   - `%APPDATA%\\SanWich\\license.json`
   - `%LOCALAPPDATA%\\SanWich\\license_anchor.json`
   - `HKEY_CURRENT_USER\\Software\\WiKiVibe\\SanWich` 的 `LicenseState`
4. 只接受具有 `trial_started_at` 且本機 HMAC 正確的資料。
5. 有多份有效資料時：
   - 若任何副本含有效 `SW2` Key，優先從有效 Supporter 狀態選擇。
   - `trial_started_at` 與 `trial_ends_at` 採所有有效副本中最早日期，避免刪除單一檔案重設試用。
   - 選定結果重新簽章後回寫三個位置。
6. 若完全沒有舊狀態，建立 30 天 Trial 並寫入三個位置。
7. 若已存在檔案／登錄資料但全部無效，不建立新 Trial，直接回 Free。
8. 授權模組載入或執行失敗時，主程式備援只開放 Free 功能。

### 2.2 功能判定

- `core/features.py` 定義 `FREE_FEATURES` 與 `SUPPORTER_FEATURES`。
- `LicenseManager.has_feature()` 的順序：
  1. 屬於 `FREE_FEATURES`：永遠 `True`。
  2. 屬於 `SUPPORTER_FEATURES`：Debug 覆寫優先，否則 Trial 有效或 `SW2` Key 有效即為 `True`。
  3. 未知功能：`False`。
- 主程式透過全域 `has_feature()` 包裝 `LICENSE_MANAGER.has_feature()`；授權模組失敗時使用內建 Free 清單。
- `debug_edition.txt` 可覆寫成 `free`、`trial`、`supporter`，已由 `.gitignore` 排除，不應出現在發佈包。

### 2.3 UI 啟用流程

1. 設定頁顯示 `LicenseManager.status_summary()` 的 Free／Supporter Trial／Supporter 狀態。
2. 使用者貼上 Supporter Key。
3. UI 呼叫 `LICENSE_MANAGER.activate_key()`。
4. `verify_supporter_key()` 成功後，Key 正規化並寫入三個授權狀態來源。
5. UI 立即更新狀態；沒有伺服器、帳號、裝置名額或重新驗證步驟。

## 3. 現行授權檔格式

實際欄位如下：

```json
{
  "edition": "trial",
  "trial_started_at": "2026-07-22",
  "trial_ends_at": "2026-08-21",
  "supporter_enabled": false,
  "supporter_key": "",
  "signature": "HEX_HMAC_SHA256"
}
```

| 欄位 | 現行用途 | 是否為權限真相 |
| --- | --- | --- |
| `edition` | 顯示／狀態記錄，啟用時寫成 `supporter` | 否 |
| `trial_started_at` | Trial 起日，也是狀態有效性必要欄位 | 是 |
| `trial_ends_at` | `>= date.today()` 時 Trial 有效 | 是 |
| `supporter_enabled` | 啟用時寫入 `true` | 否；目前判定不讀此值 |
| `supporter_key` | 保存完整離線 Key | 是；須通過 RSA 驗證 |
| `signature` | 對前五欄做 HMAC-SHA256 | 只保護本機狀態一致性 |

相容性細節：

- 新 salt：`SanWich-Local-License-State-v2-2026`。
- 舊 salt：`SanWich-TrustBased-License-v1-2026`。
- 讀取時接受新舊 salt，回寫時統一改用新 salt。
- HMAC payload 欄位順序固定為 `edition|trial_started_at|trial_ends_at|supporter_enabled|supporter_key`。

## 4. 現行 Key 驗證方式

- 格式：`SW2-<body>-<base32_signature>`。
- Key 先轉大寫，只保留英數字與 `-`。
- 必須正好三段、prefix 為 `SW2`、body 至少 12 字元。
- signature 經 Base32 解碼後必須為 256 bytes。
- 驗證訊息為 `b"SanWich supporter key v2\\0" + body.encode("ascii")`。
- 雜湊為 SHA-256，簽章格式是 RSA PKCS#1 v1.5 SHA-256；用戶端內建 2048-bit RSA 公開模數與 exponent `65537`。
- 驗證完全離線。Key 內沒有由現行程式解析的到期日、裝置 ID、授權人或遠端狀態。

風險與限制：

- 有效 Key 可複製到其他裝置，沒有同時啟用上限。
- 已發出的 Key 無法由新版伺服器讓舊程式立即失效。
- 完整 Key 目前明文存在三份本機狀態中。
- 本機日期直接決定 Trial 是否到期，沒有可信伺服器時間。
- `supporter_enabled` 或 `edition` 被修改不會單獨開啟 Supporter，但本機 HMAC secret 不是安全邊界。

## 5. Supporter 功能與判定位置

### 5.1 功能集合

`core/features.py` 的 Supporter 功能：

- `batch_processing`
- `quick_compare_full`
- `custom_rules`
- `learning_loop`
- `diarization`
- `domain_prompt_templates`
- `custom_dictionary`
- `project_profiles`
- `supporter_badge`
- `early_access`

`core/license_manager.py` 另有同一份備援集合；兩份清單目前需要人工保持同步。

### 5.2 實際判定與入口

| 位置 | 判定內容 |
| --- | --- |
| `core/license_manager.py` | `is_trial_active()`、`is_supporter_active()`、`has_feature()`、`activate_key()`、`status_summary()` |
| `SanWich.py` 授權 bootstrap | 動態載入、建立 manager、Free fail-open 包裝與狀態摘要 |
| `SanWich.py` Prompt 組裝 | `learning_loop`、`custom_rules`、`domain_prompt_templates`、`custom_dictionary`、`project_profiles` |
| `SanWich.py` 轉寫入口 | 多檔 `batch_processing`、`diarization` |
| `SanWich.py` UI | 語者分離切換、規則庫、快速對照、專案設定、鎖定提示與 Key 啟用 |

目前沒有找到 `supporter_badge` 或 `early_access` 的實際 UI／流程 gate；它們目前只存在功能集合與標籤。`domain_prompt_templates`、`custom_dictionary`、`learning_loop` 則主要在 Prompt／學習資料流程內判定，不一定有獨立鎖定按鈕。

## 6. `license_manager` 相依模組與測試

### 6.1 直接執行相依

| 檔案 | 相依方式 |
| --- | --- |
| `SanWich.py` | 動態讀取並執行 `core/license_manager.py`，建立全域 `LICENSE_MANAGER` |
| `core/features.py` | 被 `license_manager` 動態載入，提供功能集合；方向是授權模組依賴它 |

### 6.2 發佈相依

| 檔案 | 相依方式 |
| --- | --- |
| `scripts/release/聲文去SanWich_build_zip.ps1` | 將 `core/license_manager.py` 與 `core/features.py` 複製進發佈 staging |
| `scripts/release/聲文去SanWich.spec` | 將兩個檔案列為 PyInstaller data |

### 6.3 測試相依

| 測試 | 相依方式 |
| --- | --- |
| `tests/test_license_and_rules.py` | 直接載入 `core/license_manager.py`；測 Trial 復原、無效狀態回 Free、Free／Supporter feature gate；另載入 `SanWich.py` 測規則注入 gate |
| `tests/test_v25_local_and_audio.py` | 載入 `SanWich.py`，因此間接建立 `LICENSE_MANAGER` |
| `tests/editor_gui_smoke.py` | 載入 `SanWich.py`，因此間接走授權 bootstrap 與 UI gate |

其餘測試未找到 `license_manager`、`LicenseManager`、`LICENSE_MANAGER` 或 `has_feature()` 的直接參照。

目前測試沒有直接覆蓋 `verify_supporter_key()` 的有效／無效 RSA fixture、`activate_key()` 後重啟、三份狀態衝突時 Supporter Key 的選擇，以及 Registry 真實讀寫。新版不能只改原測試，必須補上這些回歸案例。

## 7. 新舊狀態的共存原則

- 新版正式授權使用 `license_v2.json`、DPAPI 裝置私鑰與伺服器簽章 Token。
- 舊 `license.json` 的 Trial 錨點先保留，避免更新後重新取得 30 天試用。
- 新版 Full Token 有效時，正式權限只由 Token 判定，不再由 `supporter_key` 判定。
- 舊 `SW2` Key 只在遷移入口驗證，不應在遷移後繼續作為新版完整版的長期 fallback。
- 新版 API 暫時不可用時，已啟用者使用未過期 Token；沒有 Token 的舊 Key 使用者可繼續用舊版程式，但新版是否給予短期遷移寬限必須在發布前明確決定。
- 不可把「刪除本機新版 Token」視為停用裝置；只有伺服器成功停用才釋放名額。

## 8. 舊版離線 Key 遷移流程

### Phase 0：先整理合格名單

1. 蒐集過去實際發出的 Legacy Key 紀錄、訂單參照與授權對象。
2. 在離線管理工具中驗證每組 `SW2` 簽章。
3. 以伺服器 Secret HMAC 產生 `legacy_fingerprint`，匯入 `legacy_licenses`；不得匯入完整 Key。
4. 若沒有可靠發放紀錄，不開放任何有效 SW2 Key 自動換發：
   - 已知使用者改發一次性 migration code；或
   - 要求付款／支持證明後人工核准。
5. 決定遷移截止日、舊授權換發權益、最大裝置數及是否有到期日。

### Phase 1：發布前相容版本

1. 新版仍能讀取現有 Trial 起訖日，且不重設 Trial。
2. 偵測到有效 `SW2` Key 時顯示「可遷移舊版授權」，不在背景自動上傳 Key。
3. 清楚告知會傳送舊 Key 以驗證資格、建立裝置公開金鑰，以及伺服器保存哪些資料。
4. 使用者明確確認後才呼叫 `migrate-legacy`。
5. 網路失敗或使用者取消時，不破壞舊 `license.json`，也不誤標成遷移完成。

### Phase 2：原子遷移

1. 本機建立 Ed25519 裝置金鑰對，私鑰先以 DPAPI 保護。
2. 呼叫 `POST /v1/license/migrate-legacy`。
3. Worker 再次驗證 RSA 簽章、合格名單／migration code 與未遷移狀態。
4. D1 在同一交易中：
   - 鎖定 `legacy_fingerprint`。
   - 建立新 Full License。
   - 建立第一台裝置。
   - 產生新 `SWF` Key 的雜湊。
   - 標記 Legacy 已遷移。
   - 寫入 audit log。
5. Worker 回傳只顯示一次的新 Key、復原碼與裝置綁定 Token。
6. 用戶端先驗證 Token 簽章與 claims，成功原子寫入 `license_v2.json` 後才顯示完成。
7. 使用者確認已保存新 Key／復原碼後，在本機寫入遷移完成標記。

### Phase 3：失敗與復原

| 失敗點 | 行為 |
| --- | --- |
| 請求送出前失敗 | 不建立任何伺服器狀態；保留舊授權 |
| 伺服器交易失敗 | 全部 rollback；同一 Idempotency-Key 可安全重試 |
| 伺服器成功但回應遺失 | 24 小時內以同一 Idempotency-Key 取回加密暫存的同一結果；逾期後撤銷補發 |
| Token 驗證失敗 | 不覆蓋舊狀態；記錄 request ID 並停止 |
| 本機寫入失敗 | 伺服器保留裝置；UI 提供重新驗證／復原，不再占第二個名額 |
| Legacy 已被遷移 | 不建立第二組 License；使用新 Key／復原碼或人工查核 |
| 發現 Key 外流爭議 | 暫停該遷移紀錄，由購買證明與 audit log 人工處理 |

### Phase 4：結束舊 Key 接受

1. 到遷移截止日前持續顯示提醒，但不阻止基本功能。
2. 截止後新版只接受 `SW2` Key 進入人工遷移／客服流程，不直接開啟 Full。
3. 後續移除新版執行路徑中的 `is_supporter_active()` 舊 Key fallback，但保留受測試覆蓋的遷移解析器。
4. 無法讓未更新的舊版程式遠端停用 `SW2` Key；發布說明必須明確承認這個限制。

## 9. Trial 遷移規則

- 三份舊狀態中選出「最早有效 Trial 起日與最早有效到期日」，沿用現行防重設規則。
- 新版本第一次啟動不得因 `license_v2.json` 不存在而重建 Trial。
- 已到期 Trial 保持到期；不因安裝新版、遷移失敗或移除舊 Key 而延長。
- Trial 仍可完全本機運作，不占正式裝置名額。
- 未來若 Trial 改由伺服器管理，應另設 Trial 契約與隱私告知，不混入本次 Legacy Full Key 遷移。

## 10. 分階段實作順序

1. 鎖定產品規則：舊 Key 換發資格、期限、Full 類型、裝置上限與 Beta 截止日。
2. 建立 Worker／D1 schema、簽章金鑰、四個授權端點、限流與 audit log。
3. 建立用戶端 API、Token 驗證、DPAPI 裝置身分與原子狀態寫入。
4. 保留 `LicenseManager.has_feature()` facade，將正式權限來源切到有效 Token。
5. 新增設定頁的啟用、驗證、停用、遷移、離線寬限與復原提示。
6. 完成 Legacy 合格名單與 migration code 管理工具。
7. 通過單元、契約、故障注入、兩台／第三台與 Windows 實機測試。
8. 先小批 Beta，再正式開放；確認穩定後才移除新版的舊 Key 直接解鎖路徑。
9. 第二階段才把內部 `supporter` 命名改為 `full`，避免授權來源與大量識別字同時改動。

## 11. 預計修改檔案清單

以下是後續實作預估，這次沒有修改：

### 11.1 現有用戶端檔案

| 檔案 | 預計變更 |
| --- | --- |
| `core/license_manager.py` | 保留 `has_feature()` facade；加入 v1／v2 狀態協調、Token 狀態與 Legacy 遷移入口 |
| `core/features.py` | 第一階段維持既有識別字；第二階段再評估 `SUPPORTER_FEATURES` 改名與移除 `supporter_badge` |
| `SanWich.py` | 設定頁改為 Full 啟用／驗證／停用／遷移 UI，顯示下次驗證與離線期限 |
| `requirements.txt` | 加入經確認的 Ed25519/JWS 驗證套件；若採純既有依賴方案則不改 |
| `scripts/release/聲文去SanWich_build_zip.ps1` | 將新增授權模組與公開金鑰資料納入 staging，不包含任何 Secret |
| `scripts/release/聲文去SanWich.spec` | 將新增模組／套件納入 PyInstaller，驗證 Windows 打包 |
| `README.md` | 對外名稱、連網需求、離線期限、裝置上限與 Legacy 遷移說明 |
| `SUPPORTER_PLAN.md` | 保留為歷史文件並連到新版規格，不再作為新功能依據 |
| `WORKERS_FULL_LICENSE_PLAN.md` | 在實作決策確定後同步狀態、實際端點與尚未完成項目 |

### 11.2 預計新增的用戶端檔案

| 檔案 | 用途 |
| --- | --- |
| `core/license_api.py` | HTTPS request、錯誤碼、重試、Idempotency-Key 與逾時策略 |
| `core/license_token.py` | JWS/Ed25519 驗證、claims、時限與公開金鑰輪替 |
| `core/device_identity.py` | Ed25519 裝置金鑰與 Windows DPAPI 保護 |
| `tests/test_license_api.py` | activate／verify／deactivate 契約與錯誤降級 |
| `tests/test_license_token.py` | 簽章、claim、裝置綁定、到期與時間倒退 |
| `tests/test_license_migration.py` | 舊 Key、Trial、冪等、回應遺失與遷移衝突 |
| `tests/fixtures/license/` | 只放測試簽章與假 Token，不放正式 Key 或私鑰 |

### 11.3 Worker／D1（若放在同一 repository）

| 檔案／目錄 | 用途 |
| --- | --- |
| `license-worker/wrangler.toml` | Worker 與 D1 綁定；只寫 Secret 名稱，不寫值 |
| `license-worker/src/index.ts` | 路由入口、共通回應與 request ID |
| `license-worker/src/routes/license.ts` | activate／verify／deactivate／migrate-legacy |
| `license-worker/src/services/token.ts` | Token 簽發與簽章金鑰輪替 |
| `license-worker/src/services/legacy.ts` | 舊 RSA Key 驗證、fingerprint 與遷移資格 |
| `license-worker/src/services/audit.ts` | 操作紀錄與敏感資料遮罩 |
| `license-worker/migrations/0001_license_schema.sql` | licenses、devices、legacy_licenses、audit_log、idempotency |
| `license-worker/test/` | API 契約、D1 交易、限流與撤銷測試 |

若授權後端採獨立 private repository，上述 Worker 檔案不應硬塞進桌面程式 repository；但 API spec、公開金鑰與不含 Secret 的客戶端契約仍可留在 SanWich。

## 12. 必測情境與完成標準

- 現有 Trial 起日與到期日升級後完全不變。
- 刪除任一舊 Trial 錨點不會取得新 Trial。
- 有效 Token 在離線期限內可用，過期後只關閉 Full。
- Token 被修改、換裝置、`kid` 未知、`aud` 錯誤或 `alg=none` 一律無效。
- 30 天重新驗證加 15 天離線寬限符合伺服器時間。
- 伺服器 5xx／斷網與明確 401／403 的行為不同。
- 第 1、2 台可啟用；第 3 台拒絕；同裝置重試不增加名額。
- 成功停用後才清除本機授權，重送不重複釋放。
- Legacy 簽章有效但不在合格名單時不能自動換發。
- 同一 Legacy Key 並發遷移只建立一組新版 License。
- 回應遺失後用同一 Idempotency-Key 可安全恢復。
- Beta Token 不得超過 Beta 截止日。
- 發佈 ZIP、Git 歷史、測試 fixture 與日誌不含 Worker Secret、私鑰、完整正式 Key、復原碼或真實客戶資料。
- `tests/test_license_and_rules.py`、`tests/test_v25_local_and_audio.py` 與 `tests/editor_gui_smoke.py` 全部通過，並補齊新的 API／Token／遷移測試。
- Worker 無法使用時，單檔轉寫、SRT／TXT 輸出、基本校對、基本編輯器與 DaVinci Tools 仍可使用。

## 13. 實作前仍需產品決策

- 舊 `SW2` Key 是否全部換成永久 Full，或依原始支持方案分級。
- 無完整發放名單時採 migration code、購買證明人工核准，或不提供自動遷移。
- 遷移開始日、截止日與舊版使用者通知方式。
- 正式 Full 是永久授權、年度授權，或兩者並存。
- Beta 明確截止日與是否允許轉正式授權。
- 新授權 API 正式網域與 Worker repository 所在位置。
- 裝置管理頁、90 天自助替換與人工客服流程是否與第一版同時上線。
