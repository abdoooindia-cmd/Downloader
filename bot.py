import os
import asyncio
import tempfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import yt_dlp
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", "10000"))

# Telegram Bot API currently allows bots to send files up to 50 MB.
# Keep a safety margin below the limit.
MAX_UPLOAD_BYTES = 49 * 1024 * 1024


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            body = b"OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Keep Render logs cleaner.
        return


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"Health server listening on 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أرسل رابط المحتوى الذي تملك حق تنزيله.\n"
        "سأحاول تنزيله بجودة مناسبة للرفع على Telegram."
    )


def find_downloaded_file(folder: Path):
    files = [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in {
            ".mp4", ".webm", ".mkv", ".mov", ".m4v"
        }
    ]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def download_video(url: str, folder: Path):
    output_template = str(folder / "%(title).80s-%(id)s.%(ext)s")

    # Prefer a single audio+video file. This avoids FFmpeg merging,
    # which saves RAM/CPU and avoids the previous "Killed" problem.
    # 480p is used to keep the resulting file more likely to fit Telegram's
    # current 50 MB bot upload limit.
    ydl_opts = {
        "format": "best[height<=480]/best[height<=360]/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 1,
        "quiet": False,
        "no_warnings": False,
        "restrictfilenames": True,
        "socket_timeout": 30,
        "overwrites": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return info


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("ابعت رابط صحيح يبدأ بـ http أو https.")
        return

    status = await update.message.reply_text("⏬ جاري التحميل...")

    try:
        with tempfile.TemporaryDirectory(prefix="ytbot_") as tmp:
            folder = Path(tmp)

            await asyncio.to_thread(download_video, url, folder)

            file_path = find_downloaded_file(folder)
            if not file_path or not file_path.exists():
                await status.edit_text("❌ التحميل انتهى لكن لم أجد ملف الفيديو.")
                return

            size = file_path.stat().st_size
            size_mb = size / (1024 * 1024)
            print(f"Downloaded: {file_path.name} ({size_mb:.2f} MB)", flush=True)

            if size > MAX_UPLOAD_BYTES:
                await status.edit_text(
                    f"❌ الملف حجمه {size_mb:.1f} MB، وهو أكبر من الحد المسموح "
                    "للرفع عبر Telegram Bot API (50 MB).\n\n"
                    "جرّب فيديو أقصر أو أقل جودة."
                )
                return

            await status.edit_text(
                f"⬆️ جاري الرفع إلى Telegram...\nالحجم: {size_mb:.1f} MB"
            )

            with file_path.open("rb") as video_file:
                await update.message.reply_document(
                    document=video_file,
                    filename=file_path.name,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30,
                    pool_timeout=30,
                )

            await status.delete()

    except yt_dlp.utils.DownloadError as e:
        print(f"yt-dlp error: {e}", flush=True)
        await status.edit_text(
            "❌ حصل خطأ أثناء تنزيل الفيديو.\n"
            "جرّب رابطًا آخر أو أرسل لي رسالة الخطأ من Logs."
        )
    except Exception as e:
        print(f"Unhandled error: {type(e).__name__}: {e}", flush=True)
        try:
            await status.edit_text(
                f"❌ حصل خطأ أثناء الرفع أو المعالجة:\n{type(e).__name__}: {e}"
            )
        except Exception:
            pass


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is missing. "
            "Add BOT_TOKEN in Render Environment Variables."
        )

    Thread(target=start_health_server, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url)
    )

    print("Bot is running...", flush=True)
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
