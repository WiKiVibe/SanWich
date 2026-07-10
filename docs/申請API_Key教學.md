# SanWich — API Key 申請教學

> 想開啟 AI 校對，請先申請任一家 API Key，然後填到軟體的「設定（齒輪）→ API Key」。
> 更新日期：2026-06-17

---

## 先看結論

- **首選 Google Gemini**：免費額度通常最友善、速度快、繁中校對也穩。
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
5. 回到軟體 → 供應商選 **Google Gemini** → 貼上 Key → 模型建議選 `gemini-2.5-flash` → 儲存。

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
- **校對結果怪怪的**：先換一個模型試試看；Gemini 建議 `gemini-2.5-flash`，DeepSeek 建議 `deepseek-v4-flash`。
