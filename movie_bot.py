# movie_bot.py
import os
import sqlite3
import logging
from datetime import datetime
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    constants,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# --- CONFIG: o'zgartiring ---
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "8132125682:AAFTDA7908hIn-E0W4om5xqRvcQcXJhmOGI"
ADMIN_ID = int(os.environ.get("ADMIN_ID") or 6829390664)
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME") or "@ibrokhimov_o777"
# -----------------------------

DB_PATH = "movies.db"
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- DB helperlar ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS movies (
            code TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_name TEXT,
            added_by INTEGER,
            added_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()

def save_movie(code: str, file_id: str, file_type: str, file_name: str, added_by: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO movies (code, file_id, file_type, file_name, added_by, added_at) VALUES (?, ?, ?, ?, ?, ?)",
        (code, file_id, file_type, file_name, added_by, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

def get_movie(code: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT file_id, file_type, file_name FROM movies WHERE code = ?", (code,))
    row = cur.fetchone()
    conn.close()
    return row

def delete_movie(code: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM movies WHERE code = ?", (code,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted > 0

def count_movies():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM movies")
    total = cur.fetchone()[0]
    conn.close()
    return total

# --- Utility: kanalga obuna tekshirish ---
async def is_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ("member", "creator", "administrator")
    except Exception as e:
        logger.exception("Kanal a'zoligini tekshirishda xato: %s", e)
        return False

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.full_name or user.username or str(user.id)
    text = f"Assalomu alaykum, {name}!\n\nBotdan foydalanish uchun kanalimizga obuna bo'lishingiz kerak."
    keyboard = [
        [InlineKeyboardButton("Kanalga obuna bo'lish", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
        [InlineKeyboardButton("Obunani tekshirish", callback_data="check_sub")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "check_sub":
        ok = await is_subscribed(context, query.from_user.id)
        if ok:
            await query.edit_message_text("Obuna tasdiqlandi ✅\nKino kodini yuboring (masalan: 1).")
        else:
            keyboard = [
                [InlineKeyboardButton("Kanalga obuna bo'lish", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
                [InlineKeyboardButton("Qayta tekshirish", callback_data="check_sub")],
            ]
            await query.edit_message_text(
                "❌ Siz kanalga obuna bo'lmadingiz.\nObuna bo‘ling va qayta tekshiring.",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

# --- Admin buyruqlari ---
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = update.effective_user
    if user.id != ADMIN_ID:
        return await msg.reply_text("❌ Bu buyruq faqat admin uchun.")

    if not msg.reply_to_message:
        return await msg.reply_text("Faylga javoban `/add <kod>` yuboring. (masalan: /add 1)")

    if not context.args:
        return await msg.reply_text("Kod kiriting. Masalan: `/add 1`", parse_mode=constants.ParseMode.MARKDOWN)

    code = context.args[0].strip()
    reply = msg.reply_to_message

    file_id, file_type, file_name = None, None, None
    if reply.video:
        file_id, file_type, file_name = reply.video.file_id, "video", reply.video.file_name or ""
    elif reply.document:
        file_id, file_type, file_name = reply.document.file_id, "document", reply.document.file_name or ""
    elif reply.audio:
        file_id, file_type, file_name = reply.audio.file_id, "audio", reply.audio.file_name or ""
    elif reply.voice:
        file_id, file_type, file_name = reply.voice.file_id, "voice", ""
    elif reply.photo:
        file_id, file_type, file_name = reply.photo[-1].file_id, "photo", ""
    else:
        return await msg.reply_text("❌ Media topilmadi. Video/Document/Audio/Photo yuboring.")

    save_movie(code, file_id, file_type, file_name, user.id)
    await msg.reply_text(f"✅ Kod *{code}* saqlandi.", parse_mode=constants.ParseMode.MARKDOWN)

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
    if not context.args:
        return await update.message.reply_text("❌ Qaysi kodni o‘chirish kerak?\nMasalan: /delete 1")

    code = context.args[0].strip()
    if delete_movie(code):
        await update.message.reply_text(f"🗑 Kod *{code}* o‘chirildi.", parse_mode=constants.ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("❌ Bunday kod topilmadi.")

# --- LIST (yangisi) ---
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT code, file_type, file_name, added_by, added_at FROM movies ORDER BY added_at DESC")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return await update.message.reply_text("📭 Hozircha kino kodi saqlanmagan.")

    text_lines = []
    for r in rows:
        code, ftype, fname, added_by, added_at = r
        text_lines.append(
            f"🔑 Kod: {code}\n📂 Turi: {ftype}\n📄 Fayl: {fname or '-'}\n👤 Qo‘shgan: {added_by}\n🕒 Sana: {added_at[:19]}\n---"
        )

    # 4096 belgidan oshib ketmasligi uchun bo‘lib yuboramiz
    chunk = ""
    for line in text_lines:
        if len(chunk) + len(line) > 3500:
            await update.message.reply_text(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk:
        await update.message.reply_text(chunk)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")

    total = count_movies()
    await update.message.reply_text(f"📊 Hozircha {total} ta kino kodi saqlangan.")

# --- User text handler ---
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = (msg.text or "").strip()
    if text.startswith("/"):
        return

    if not await is_subscribed(context, msg.from_user.id):
        keyboard = [
            [InlineKeyboardButton("Kanalga obuna bo‘lish", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("Obunani tekshirish", callback_data="check_sub")],
        ]
        return await msg.reply_text("❌ Avval kanalga obuna bo‘ling.", reply_markup=InlineKeyboardMarkup(keyboard))

    row = get_movie(text)
    if not row:
        return await msg.reply_text("❌ Bunday kod topilmadi.")
    file_id, file_type, _ = row
    try:
        if file_type == "video":
            await context.bot.send_video(chat_id=msg.chat.id, video=file_id, caption=f"🎬 Kod: {text}")
        elif file_type == "document":
            await context.bot.send_document(chat_id=msg.chat.id, document=file_id, caption=f"📂 Kod: {text}")
        elif file_type == "audio":
            await context.bot.send_audio(chat_id=msg.chat.id, audio=file_id, caption=f"🎵 Kod: {text}")
        elif file_type == "voice":
            await context.bot.send_voice(chat_id=msg.chat.id, voice=file_id)
        elif file_type == "photo":
            await context.bot.send_photo(chat_id=msg.chat.id, photo=file_id, caption=f"🖼 Kod: {text}")
    except Exception as e:
        logger.exception("Xato: %s", e)
        await msg.reply_text("❌ Faylni yuborishda xato bo‘ldi.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/start — Botni boshlash\n"
        "/help — Yordam\n\n"
        "👑 Admin buyruqlari:\n"
        "/add <kod> — faylni saqlash\n"
        "/delete <kod> — kodni o‘chirish\n"
        "/list — kodlar ro‘yxati\n"
        "/stats — statistika"
    )
    await update.message.reply_text(text)

# --- Keep alive (UptimeRobot uchun) ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write("Bot ishlayapti ✅")

def run_server():
    server = HTTPServer(("0.0.0.0", 8080), SimpleHandler)
    server.serve_forever()

def keep_alive():
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()

# --- Main ---
def main():
    init_db()
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("Bot ishga tushdi 🚀")
    app.run_polling()

if __name__ == "__main__":
    main()
