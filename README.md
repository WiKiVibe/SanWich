# 聲文去SanWich

聲文去SanWich 是一個 Windows 桌面語音轉文字工具，提供圖形介面、字幕輸出、文字修正與可選的 LLM 輔助整理流程。

## 功能

- 語音轉文字工作流程
- SRT / TXT 輸出
- CustomTkinter 桌面介面
- 可選 API 文字修正
- 可選 TXT 語者分離
- 可選模型與 FFmpeg 下載流程

## 快速開始

建議在 Windows 上使用安裝腳本：

```bat
聲文去SanWich_setup.bat
```

腳本會建立 `.venv`、安裝必要套件，並依照電腦環境安裝 PyTorch。

也可以手動安裝：

```bat
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip setuptools wheel
.venv\Scripts\python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python 聲文去SanWich.py
```

## 設定 API Key

請先複製範例設定檔：

```bat
copy config.example.json config.json
```

然後把自己的 API Key 填進 `config.json`。`config.json` 已經被 `.gitignore` 排除，不應該上傳到 GitHub。

## 不上傳到 GitHub 的檔案

以下內容會在本機產生或下載，不適合放進 Git：

- `.venv/`
- `logs/`
- `release/`
- `tools/`
- `_diar_candidates/`
- `_語者分離_暫緩備份/models/`
- 音訊檔、快取檔、打包成品

## 上傳到 GitHub

建議先建立 Private repo。GitHub 沒有「知道連結的人可看」的 repo 模式；Private repo 只有你邀請的人能看，確認安全後再改成 Public。

第一次建立 GitHub repo 後，可以使用：

```bat
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/YOUR_REPO.git
git push -u origin main
```

如果已經有遠端 repo，只需要把 `YOUR_NAME/YOUR_REPO` 換成你的 GitHub 帳號與 repo 名稱。

## 安全提醒

- 不要上傳 `config.json`，裡面會有你的 API Key。
- 不要上傳 `.venv/`、模型、音訊、logs、release zip。
- 如果曾經把 API Key 貼到聊天、文件或公開 repo，請到 API 平台重新產生 Key，並停用舊 Key。
- Private repo 仍建議當成「未來可能公開」來整理，避免秘密資訊進入 Git 歷史。
