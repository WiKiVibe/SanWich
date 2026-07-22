# WiKiVibe License API 契約

> 文件狀態：設計稿，尚未實作  
> API 版本：`v1`  
> 適用產品：SanWich 桌面版  
> 對外授權名稱：基本功能／完整版（Full）

## 1. 目標與邊界

- 正式完整版授權由 WiKiVibe License API 與伺服器簽章 Token 判定。
- 啟用、重新驗證、停用與舊授權遷移都透過 HTTPS。
- 一組正式 Key 預設最多同時啟用 2 台裝置；試用不占正式裝置名額。
- 免費功能不依賴 API。API、網路或本機授權資料失敗時，只能關閉完整版功能，不能阻止基本功能使用。
- API 不接收字幕、音訊、影片、Prompt、第三方 API Key、個人規則或專案內容。
- SanWich 是公開原始碼軟體。本設計用來管理正常授權、裝置名額與一般 Key 分享，不宣稱能防止修改程式繞過檢查。

## 2. 共通規則

### 2.1 基本設定

- API origin：`https://license.wikivibe.example`，正式上線前替換為實際網域；本文件端點都已包含 `/v1`。
- Content-Type：`application/json; charset=utf-8`。
- 時間：UTC、RFC 3339，例如 `2026-07-22T10:30:00Z`。
- ID：不可猜測的 UUID 或等級相當的隨機識別字。
- 每個回應都回傳 `request_id` 與 `server_time`。
- `activate`、`deactivate`、`migrate-legacy` 必須支援 `Idempotency-Key`；相同 Key 與相同內容重送時不得重複占用或釋放裝置名額。
- 若回應包含只顯示一次的 Key／復原碼，冪等紀錄可將完整回應加密保存最多 24 小時，讓回應遺失時能用相同 `Idempotency-Key` 取回；逾期後只能走撤銷補發流程。
- 伺服器不得在日誌中寫入完整 License Key、Legacy Key、Token、復原碼或裝置私鑰。

### 2.2 裝置身分與請求證明

- 用戶端第一次正式啟用前產生 Ed25519 裝置金鑰對。
- 裝置私鑰使用 Windows DPAPI 保護，只留在本機；伺服器只保存公開金鑰。
- `device_id` 由伺服器建立，不以 CPU、主機板、硬碟或 MAC 位址直接充當裝置 ID。
- 已啟用裝置的敏感操作需附 `device_proof`，內容至少綁定 HTTP method、path、`request_id`、UTC 時間、Token 雜湊與 request body 雜湊，再由裝置私鑰簽章。
- 伺服器只接受短時間窗內的 proof，並依 `request_id` 防止重播。
- `device_name` 與 `os_summary` 只供使用者辨識裝置，不參與硬性授權判定。

`device_proof` 格式：

```json
{
  "algorithm": "Ed25519",
  "public_key": "BASE64URL_PUBLIC_KEY",
  "signed_at": "2026-07-22T10:30:00Z",
  "signature": "BASE64URL_SIGNATURE"
}
```

簽章輸入使用 UTF-8 與 RFC 8785 JSON Canonicalization Scheme（JCS）：

```text
METHOD\n
PATH\n
REQUEST_ID\n
SIGNED_AT\n
BASE64URL(SHA256(BEARER_TOKEN_OR_EMPTY))\n
BASE64URL(SHA256(JCS(REQUEST_BODY_WITHOUT_DEVICE_PROOF)))
```

- `verify`、`deactivate` 的 Token 放在 `Authorization: Bearer <license_token>`，不重複放進 JSON body。
- 伺服器與邊緣代理必須遮蔽 `Authorization`，不得把完整 header 寫入 access log。

### 2.3 成功回應外框

```json
{
  "ok": true,
  "request_id": "018f...",
  "server_time": "2026-07-22T10:30:00Z",
  "data": {}
}
```

### 2.4 錯誤回應外框

```json
{
  "ok": false,
  "request_id": "018f...",
  "server_time": "2026-07-22T10:30:00Z",
  "error": {
    "code": "DEVICE_LIMIT_REACHED",
    "message": "This license already has the maximum number of active devices.",
    "retryable": false,
    "details": {
      "max_devices": 2
    }
  }
}
```

穩定錯誤碼：

| HTTP | `code` | 用戶端行為 |
| --- | --- | --- |
| 400 | `INVALID_REQUEST` | 不重試；提示資料格式錯誤 |
| 401 | `INVALID_KEY` | 不重試；不得透露 Key 是否接近正確 |
| 401 | `INVALID_DEVICE_PROOF` | 重新建立一次 proof；仍失敗則停止 |
| 403 | `LICENSE_SUSPENDED` | 關閉完整版，保留基本功能 |
| 403 | `LICENSE_REVOKED` | 關閉完整版並清除可用 Token |
| 403 | `LICENSE_EXPIRED` | 關閉完整版，顯示到期資訊 |
| 403 | `DEVICE_DEACTIVATED` | 清除本機正式授權狀態 |
| 409 | `DEVICE_LIMIT_REACHED` | 引導停用舊裝置 |
| 409 | `LEGACY_ALREADY_MIGRATED` | 進入復原／人工查核，不得再建立授權 |
| 409 | `IDEMPOTENCY_CONFLICT` | 停止重試並記錄 request ID |
| 422 | `LEGACY_NOT_ELIGIBLE` | 引導使用遷移碼或購買證明查核 |
| 426 | `CLIENT_UPDATE_REQUIRED` | 保留基本功能並要求更新 |
| 429 | `RATE_LIMITED` | 依 `Retry-After` 延後重試 |
| 500/503 | `SERVER_UNAVAILABLE` | 使用尚未到期的離線 Token；背景重試 |

## 3. `POST /v1/license/activate`

### 3.1 用途

- 使用新的 `SWF`／`SWB` Key 啟用目前裝置。
- 同一裝置重送視為重新取得 Token，不得增加裝置數。
- 第 3 台裝置在上限為 2 時回傳 `DEVICE_LIMIT_REACHED`。

### 3.2 Request

```json
{
  "request_id": "018f...",
  "license_key": "SWF-XXXX-XXXX-XXXX-XXXX",
  "device": {
    "public_key": "BASE64URL_PUBLIC_KEY",
    "key_algorithm": "Ed25519",
    "name": "WiKi 的剪輯工作站",
    "os_summary": "Windows 11 24H2"
  },
  "client": {
    "product": "sanwich",
    "version": "2.6.0",
    "platform": "windows",
    "locale": "zh-TW"
  },
  "device_proof": {
    "algorithm": "Ed25519",
    "public_key": "BASE64URL_PUBLIC_KEY",
    "signed_at": "2026-07-22T10:30:00Z",
    "signature": "BASE64URL_SIGNATURE"
  }
}
```

### 3.3 Response `200`

```json
{
  "ok": true,
  "request_id": "018f...",
  "server_time": "2026-07-22T10:30:00Z",
  "data": {
    "license_id": "lic_...",
    "device_id": "dev_...",
    "license_type": "full",
    "status": "active",
    "max_devices": 2,
    "active_devices": 1,
    "license_token": "eyJhbGciOiJFZERTQSIs...",
    "refresh_after": "2026-08-21T10:30:00Z",
    "grace_until": "2026-09-05T10:30:00Z",
    "recovery_code": "XXXX-XXXX-XXXX-XXXX"
  }
}
```

- `recovery_code` 只在這組授權第一次成功啟用時回傳一次；伺服器只保存其雜湊。
- `license_key` 不在回應中回傳，也不得寫入一般應用程式日誌。

## 4. `POST /v1/license/verify`

### 4.1 用途

- 每 30 天主動重新驗證，或在使用者要求時手動驗證。
- 驗證授權、裝置與 Beta／正式期限後輪替離線 Token。
- 同一裝置驗證不增加裝置名額。

### 4.2 Request

```json
{
  "request_id": "018f...",
  "client": {
    "product": "sanwich",
    "version": "2.6.0",
    "platform": "windows"
  },
  "device_proof": {
    "algorithm": "Ed25519",
    "signed_at": "2026-08-21T10:30:00Z",
    "signature": "BASE64URL_SIGNATURE"
  }
}
```

Header：`Authorization: Bearer <license_token>`。

### 4.3 Response `200`

```json
{
  "ok": true,
  "request_id": "018f...",
  "server_time": "2026-08-21T10:30:00Z",
  "data": {
    "license_id": "lic_...",
    "device_id": "dev_...",
    "license_type": "full",
    "status": "active",
    "license_token": "NEW_SIGNED_TOKEN",
    "refresh_after": "2026-09-20T10:30:00Z",
    "grace_until": "2026-10-05T10:30:00Z"
  }
}
```

- 每次成功驗證都回傳新 Token；舊 Token 可保留極短重疊期處理原子寫入，但不得延長原本期限。
- 若伺服器明確回覆 `revoked`、`expired`、`suspended` 或 `device_deactivated`，用戶端立即停止以現有 Token 開啟新的完整版工作。
- 只有連線失敗或 5xx 才可沿用尚未超過 `offline_until` 的 Token；401／403 不得當成網路錯誤而進入寬限。

## 5. `POST /v1/license/deactivate`

### 5.1 用途

- 從仍可使用的裝置停用自己並釋放一個裝置名額。
- 不支援純離線停用；用戶端收到成功回應後才清除本機 Token 與裝置授權狀態。

### 5.2 Request

```json
{
  "request_id": "018f...",
  "reason": "user_requested",
  "device_proof": {
    "algorithm": "Ed25519",
    "signed_at": "2026-07-22T10:30:00Z",
    "signature": "BASE64URL_SIGNATURE"
  }
}
```

Header：`Authorization: Bearer <license_token>`。

### 5.3 Response `200`

```json
{
  "ok": true,
  "request_id": "018f...",
  "server_time": "2026-07-22T10:30:00Z",
  "data": {
    "license_id": "lic_...",
    "device_id": "dev_...",
    "status": "deactivated",
    "deactivated_at": "2026-07-22T10:30:00Z",
    "active_devices": 1,
    "max_devices": 2
  }
}
```

- 對同一裝置重送停用請求應回傳相同終態，不重複計算替換次數。
- 壞機或已重灌裝置不走此端點，改由裝置管理頁使用 Key 加復原碼處理。

## 6. `POST /v1/license/migrate-legacy`

### 6.1 用途與安全門檻

- 將目前 `SW2-<body>-<signature>` 離線 Supporter Key 換成新版 Full License、`SWF` Key 與裝置 Token。
- 伺服器必須獨立驗證舊 Key 的 RSA 簽章；不可相信用戶端傳來的 `legacy_valid=true`。
- 舊 Key 簽章有效只是必要條件，不是充分條件。伺服器還必須確認該 Key 在預先匯入的合格清單中，或要求一次性遷移碼／購買證明。
- 不可開放「任何簽章有效的 SW2 Key 都能匿名先搶先贏」；否則外流副本可能搶先取得新版授權。
- 伺服器以 Secret HMAC 計算 `legacy_fingerprint`，資料庫不保存完整舊 Key。
- 同一 `legacy_fingerprint` 只能建立一組新版授權；整個資料庫交易必須具原子性。

### 6.2 Request

```json
{
  "request_id": "018f...",
  "legacy_key": "SW2-BODY-SIGNATURE",
  "migration_code": "OPTIONAL-ONE-TIME-CODE",
  "device": {
    "public_key": "BASE64URL_PUBLIC_KEY",
    "key_algorithm": "Ed25519",
    "name": "WiKi 的剪輯工作站",
    "os_summary": "Windows 11 24H2"
  },
  "client": {
    "product": "sanwich",
    "version": "2.6.0",
    "platform": "windows",
    "locale": "zh-TW"
  },
  "device_proof": {
    "algorithm": "Ed25519",
    "public_key": "BASE64URL_PUBLIC_KEY",
    "signed_at": "2026-07-22T10:30:00Z",
    "signature": "BASE64URL_SIGNATURE"
  }
}
```

### 6.3 Response `200`

```json
{
  "ok": true,
  "request_id": "018f...",
  "server_time": "2026-07-22T10:30:00Z",
  "data": {
    "migration_id": "mig_...",
    "license_id": "lic_...",
    "device_id": "dev_...",
    "license_type": "full",
    "status": "active",
    "replacement_key": "SWF-XXXX-XXXX-XXXX-XXXX",
    "license_token": "eyJhbGciOiJFZERTQSIs...",
    "refresh_after": "2026-08-21T10:30:00Z",
    "grace_until": "2026-09-05T10:30:00Z",
    "recovery_code": "XXXX-XXXX-XXXX-XXXX"
  }
}
```

- `replacement_key` 與 `recovery_code` 只顯示一次。UI 必須要求使用者先複製或另存，再完成畫面。
- 新 Key 只保存強雜湊或伺服器端 HMAC；遺失時撤銷舊 Key 並補發，不提供明文查回。只有 24 小時內的冪等回應可從加密暫存取回同一份一次性資料。
- 遷移成功後，本機可保留舊 Key 的不可逆指紋與遷移完成標記，但不再以舊 Key 開啟完整版。

## 7. 客戶端離線 License Token

### 7.1 格式

- 使用 JWS Compact Serialization（`header.payload.signature`）。
- 簽章演算法：Ed25519／`EdDSA`。
- 伺服器私鑰只放在 Workers Secret；SanWich 僅內建可輪替的公開金鑰集合。
- Token 是可讀但不可竄改的授權聲明，不放入 License Key、電子郵件、訂單資料或任何使用者內容。

Header：

```json
{
  "alg": "EdDSA",
  "typ": "WIKIVIBE-LICENSE",
  "kid": "license-signing-2026-01"
}
```

Payload：

```json
{
  "iss": "https://license.wikivibe.example",
  "aud": "sanwich-desktop",
  "sub": "lic_...",
  "jti": "tok_...",
  "schema": 1,
  "license_type": "full",
  "license_status": "active",
  "device_id": "dev_...",
  "device_key_thumbprint": "BASE64URL_SHA256",
  "entitlements": ["full"],
  "max_devices": 2,
  "iat": 1784716200,
  "refresh_after": 1787308200,
  "grace_until": 1788604200,
  "exp": 1788604200
}
```

### 7.2 驗證順序

1. 限制 Token 最大長度，確認恰為三段 Base64URL。
2. Header 只接受白名單中的 `alg`、`typ` 與 `kid`；不得接受 `alg=none` 或 Token 自帶的公開金鑰／URL。
3. 使用程式內建且與 `kid` 對應的 Ed25519 公開金鑰驗證 JWS。
4. 驗證 `iss`、`aud`、`schema`、`license_status` 與必要 claims。
5. 確認 `device_id` 與本機紀錄一致，且 `device_key_thumbprint` 對應本機裝置公開金鑰。
6. 以 UTC 判斷 `refresh_after`、`grace_until` 與 `exp`；Beta Token 期限不得超過 Beta 授權到期日。
7. 到達 `refresh_after` 後嘗試連線驗證；連線失敗時可用至 `grace_until`。超過後只保留基本功能。
8. 本機保存可信時間高水位，時間倒退不得讓 Token 延長；異常倒退時要求連線驗證。

### 7.3 本機保存格式

建議新增 `%APPDATA%\\SanWich\\license_v2.json`：

```json
{
  "schema": 2,
  "license_token": "JWS_COMPACT_TOKEN",
  "device_id": "dev_...",
  "device_key_id": "local-device-key-1",
  "key_hint": "SWF-XXXX...XXXX",
  "last_verified_at": "2026-07-22T10:30:00Z",
  "last_trusted_utc": "2026-07-22T10:30:00Z",
  "migration": {
    "legacy_fingerprint": "LOCAL_SHA256_OR_EMPTY",
    "migrated_at": "2026-07-22T10:30:00Z"
  }
}
```

- 裝置私鑰放在獨立的 DPAPI 保護資料中，不寫進 `license_v2.json`。
- `license_v2.json` 可備份，但 Token 必須綁定裝置公開金鑰；複製到其他電腦不得生效。
- 本機資料損壞時先嘗試安全復原；無法復原就回到基本功能，不自動建立新的正式授權。

## 8. Key 與 Token 的責任分工

| 項目 | 用途 | 是否可離線判定 | 是否綁裝置 |
| --- | --- | --- | --- |
| `SWF`／`SWB` Key | 新裝置啟用與帳戶復原入口 | 否 | 否 |
| Legacy `SW2` Key | 僅供限期遷移 | 舊版可以 | 否 |
| License Token | 已啟用裝置的離線完整版權限 | 是，至 `grace_until` | 是 |
| Device private key | 證明目前裝置身分 | 是 | 是 |
| Recovery code | 壞機／重灌後管理裝置 | 否 | 對應授權 |

## 9. 伺服器資料與安全要求

- License Key：只存高成本密碼雜湊或伺服器 Secret HMAC；查詢可搭配非敏感 prefix。
- Legacy Key：只存 Secret HMAC fingerprint 與遷移狀態。
- Recovery code：只存高成本雜湊。
- Token 簽章私鑰、管理 API Secret、付款 Webhook Secret：只放 Workers Secrets。
- 所有狀態變更寫入 append-only audit log，至少包含 actor、action、license ID、device ID、reason、request ID 與時間。
- 啟用、遷移與復原端點依 IP、Key fingerprint 與裝置公開金鑰限流。
- 管理者 API 使用獨立身分驗證與多因素驗證，不與桌面版端點共用憑證。
- 簽章金鑰輪替時，舊公開金鑰至少保留到所有舊 Token 的 `exp` 之後。

## 10. 契約相容性

- 新增回應欄位屬向後相容；用戶端必須忽略不認識的非必要欄位。
- 刪除欄位、改變欄位型別、改變錯誤碼語意或 Token claim 語意，需要新 API／Token schema 版本。
- API 可用 `minimum_client_version` 要求安全更新，但舊版基本功能仍不能被伺服器封鎖。
- 所有正式範例、測試 fixture 與日誌必須使用假 Key、假 Token 與 `.example` 網域。
