import os
import shutil
import re
import subprocess
import asyncio
import glob
import uuid

from mutagen.mp4 import MP4
from gamdl.constants import MP4_TAGS_MAP
from telegram import Update
from telegram.ext import CallbackContext
from config import TELEGRAM_ADMIN_ID,REDIS_BROKER_URL
from celery import Celery

# Initialize Celery app
app = Celery('apple_music_downloader')
app.conf.broker_url = REDIS_BROKER_URL
app.conf.result_backend = REDIS_BROKER_URL

ansi_escape = re.compile(r'\x1b\[[0-9;]*m')

def strip_ansi(text: str) -> str:
    return ansi_escape.sub('', text)

def extract_progress(line: str) -> str | None:
    match = re.search(r"\[download]\s+(.*)", line)
    return match.group(1).strip() if match else None

def extract_info(line: str) -> str | None:
    match = re.search(r"\[INFO\s+[^]]+]\s+(.*)", line)
    return match.group(1).strip() if match else None

@app.task
async def process_msg(update: Update, context: CallbackContext):
    downloads_path = f"./downloads-{uuid.uuid4()}"
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    if user_id not in TELEGRAM_ADMIN_ID:
        return await update.message.reply_text("You are not authorized!")
    message_text = update.message.text
    url_regex = r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"  # Regular expression for URLs
    urls: list[str] = re.findall(url_regex, message_text)
    if len(urls) <= 0:
        return None

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
        await asyncio.sleep(0.9)  # avoid flooding Telegram with too many edits

    m4a_files = glob.glob(f'{downloads_path}/**/*.m4a', recursive=True)
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

        msg = await update.message.reply_text(f"Uploading {artist} - {title}")
        try:
            await context.bot.send_audio(
                chat_id=chat_id,
                title=title,
                performer=artist,
                thumbnail=open(cover_path, "rb"),
                audio=open(m4a_file, "rb"),
            )
        except Exception as e:
            await msg.delete()
            print(e)

    if os.path.exists(downloads_path):
        shutil.rmtree(downloads_path)

    try:
        if info_message:
            await info_message.delete()
        if progress_message:
            await progress_message.delete()
            return None
        return None
    except Exception as e:
        print(e)
        return None
