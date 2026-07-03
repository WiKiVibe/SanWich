# Security Notes

This project should be prepared as if it may become public later.

Before pushing:

1. Keep `config.json` local only.
2. Keep API keys, tokens, passwords, audio files, logs, model downloads, and build output out of Git.
3. Use a private GitHub repository first.
4. Rotate any API key that was accidentally shared or committed.
5. Check Git status before every push.

Files intentionally ignored include:

- `.venv/`
- `config.json`
- `logs/`
- `release/`
- `tools/`
- downloaded model folders
- audio/video exports
- local backup files
