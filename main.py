import os
import shutil
import re
import subprocess
import asyncio
import glob
from mutagen.mp4 import MP4
from gamdl.constants import MP4_TAGS_MAP
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CallbackContext, filters
from config import TELEGRAM_TOKEN,TELEGRAM_ADMIN_ID

downloads_path = "./downloads"
ansi_escape = re.compile(r'\x1b\[[0-9;]*m')

def strip_ansi(text: str) -> str:
    return ansi_escape.sub('', text)

def extract_progress(line: str) -> str | None:
    match = re.search(r"\[download\]\s+(.*)", line)
    return match.group(1).strip() if match else None

def extract_info(line: str) -> str | None:
    match = re.search(r"\[INFO\s+[^\]]+\]\s+(.*)", line)
    return match.group(1).strip() if match else None

async def main(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    if user_id not in TELEGRAM_ADMIN_ID:
        return await update.message.reply_text("You are not authorized!")
    message_text = update.message.text
    url_regex = r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"  # Regular expression for URLs
    urls: list[str] = re.findall(url_regex, message_text)
    if len(urls) <= 0:
        return

    command = [
        "gamdl",
        "-c",
        "./data/cookies.txt",
        "-s",
        "--cover-size",
        "320",
        "-o",
        downloads_path,
    ] + urls
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    info_message = await update.message.reply_text("Starting command...")
    progress_message = None

    while True:
        raw_line = process.stdout.readline()
        if raw_line == '' and process.poll() is not None:
            break
        if raw_line:
            line = strip_ansi(raw_line)
            print(line)
            progress = extract_progress(line)
            info = extract_info(line)
            try:
                if progress:
                    if progress_message is None:
                        progress_message = await update.message.reply_text(progress)
                    else:
                        await progress_message.edit_text(progress)
                elif info:
                    await info_message.edit_text(info)
                    if info.lower().startswith("done") and progress_message is not None:
                        await progress_message.delete()
                        progress_message = None
            except Exception as e:
                print(e)
        await asyncio.sleep(0.5)  # avoid flooding Telegram with too many edits

    m4a_files = glob.glob('./downloads/**/*.m4a', recursive=True)
    m4a_files = [os.path.abspath(path) for path in m4a_files]

    for m4a_file in m4a_files:
        music = MP4(m4a_file)
        music.update({
            MP4_TAGS_MAP["comment"]: "t.me/myfuckinglifetimes",
        })
        music.save()
        folder = os.path.dirname(m4a_file)
        cover_path = folder + "/Cover.jpg"
        title = music[MP4_TAGS_MAP["title"]][0]
        artist = music[MP4_TAGS_MAP["artist"]][0]

        try:
            msg = await update.message.reply_text(f"Uploading {artist} - {title}")
            await context.bot.send_audio(
                chat_id=chat_id,
                title=title,
                performer=artist,
                thumbnail=open(cover_path, "rb"),
                audio=open(m4a_file, "rb"),
            )
            await msg.delete()
        except Exception as e:
            print(e)

    if os.path.exists(downloads_path):
        shutil.rmtree(downloads_path)

    try:
        if info_message:
            await info_message.delete()
        if progress_message:
            await progress_message.delete()
    except Exception as e:
        print(e)


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT, main))
    app.run_polling()
