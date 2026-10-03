# YouTube Telegram Bot for Render

## Files
- `bot.py` — Telegram bot + Render health server
- `requirements.txt` — Python dependencies
- `render.yaml` — optional Render Blueprint

## Render settings
- Service type: Web Service
- Runtime: Python
- Build Command: `pip install -r requirements.txt`
- Start Command: `python bot.py`
- Environment Variable:
  - `BOT_TOKEN` = your NEW Telegram bot token

Do NOT put the bot token inside `bot.py` or commit it to GitHub.

## Important upload limit
The bot intentionally downloads a single audio+video format at up to 480p to avoid FFmpeg merging and reduce RAM/CPU usage.
It checks the resulting file before upload and refuses files over 49 MiB, because Telegram's Bot API currently documents a 50 MB sendDocument limit.

If a file is still too large, use a shorter/lower-resolution source or add a transcoding step on a server with enough CPU/RAM.
