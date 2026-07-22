# SanWich — API Key 申請教學

## v2.5b：本機私密 AI 不需要 API Key

- 在「設定」選擇 **本機私密 AI**。
- 按「下載／檢查本地 AI」，或直接開始第一次 AI 校對。
- 第一次會下載 Breeze-7B GGUF（約 4.54GB）與 llama.cpp 執行核心。
- 本機 AI 所在磁碟至少要有 7GB 可用空間，建議先保留 10GB。
- 轉寫時會先完成 Breeze-ASR 並釋放顯存，再啟動本機 LLM 校對，降低 6GB 顯卡同時載入兩個模型的風險。
- 完成後字幕、Prompt、個人化規則只會送到本機 `127.0.0.1`，不會傳給雲端 LLM。
- 只有選擇 Gemini、OpenAI、Claude 或 DeepSeek 時，才需要依下列教學申請 API Key。

> 本機私密 AI 不需 Key；只有使用雲端 AI 時，才需申請並填入供應商 API Key。
> 更新日期：2026-07-18

---

## 先看結論

- **隱私首選本機私密 AI**：不需 API Key，字幕內容不送往雲端。
- **雲端首選 Google Gemini**：免費額度通常最友善、速度快、繁中校對也穩。
- **如果你要改用 DeepSeek**：現在軟體已支援 DeepSeek，可在設定裡直接選 **DeepSeek**。
- 其他家（OpenAI / Claude / DeepSeek）請依自己的使用習慣與預算選擇。

申請完成後，在軟體裡：

1. 打開 **設定**。
2. 選擇 **供應商**。
3. 把申請到的 Key 貼到 **API Key** 欄位。
4. 選擇 **模型**。
5. 按 **儲存**。

> Key 只會儲存在本機 `%APPDATA%\SanWich\config.json`，更新程式不會覆寫。但只要你開啟 AI 校對，字幕文字就會傳送到你選擇的 API 供應商做校對。

---

## 一、Google Gemini（推薦首選）

1. 開啟 <https://aistudio.google.com/apikey>
2. 用你的 Google 帳號登入。
3. 點 **Create API key**。
4. 複製產生的 Key（通常是 `AIza...` 開頭）。
5. 回到軟體 → 供應商選 **Google Gemini** → 貼上 Key → 模型建議選 `gemini-3.6-flash` → 儲存。

---

## 二、OpenAI

1. 開啟 <https://platform.openai.com/>
2. 登入後進入 **API keys**。
3. 建立新的 secret key。
4. 複製 `sk-...` Key。
5. 回到軟體 → 供應商選 **OpenAI** → 貼 Key → 選模型 → 儲存。

---

## 三、Anthropic Claude

1. 開啟 <https://console.anthropic.com/>
2. 登入後進入 **API Keys**。
3. 點 **Create Key**。
4. 複製 `sk-ant-...` Key。
5. 回到軟體 → 供應商選 **Claude** → 貼 Key → 選模型 → 儲存。

---

## 四、DeepSeek

1. 開啟 <https://platform.deepseek.com/api_keys>
2. 登入或註冊 DeepSeek 帳號。
3. 進入 **API Keys** 頁面後，建立新的 API Key。
4. 複製產生的 Key。
5. 如果平台提示餘額不足，依 DeepSeek 頁面指示處理後再使用。
6. 回到軟體 → 供應商選 **DeepSeek** → 貼 Key → 模型建議選 `deepseek-v4-flash` → 儲存。

> DeepSeek 官方文件目前提供的 OpenAI 相容 Base URL 是 `https://api.deepseek.com`，`deepseek-v4-flash` 與 `deepseek-v4-pro` 都可直接使用。

---

## 常見問題

- **跳出「API Key 無效或已過期」**：Key 可能貼錯、複製不完整，或已被刪除。回供應商頁面重新產生一次再貼上。
- **跳出「今日免費額度已用完」**：通常是免費方案或試用額度已經用完，請明天再試或更換供應商。
- **跳出「連線逾時／無法連上 API」**：先檢查網路；公司、學校或防毒軟體有時會擋住外部 API。
- **校對結果怪怪的**：先換一個模型試試看；Gemini 建議 `gemini-3.6-flash`，OpenAI 建議 `gpt-5.6-luna`，Claude 建議 `claude-haiku-4-5`，DeepSeek 建議 `deepseek-v4-flash`。
