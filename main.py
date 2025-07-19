import asyncio
import glob
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
import re
from uuid import uuid4
from gamdl.constants import MP4_TAGS_MAP
from mutagen.mp4 import MP4
from telegram import Update, MessageEntity
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from config import TELEGRAM_TOKEN, TELEGRAM_ADMIN_ID

ansi_escape = re.compile(r'\x1b\[[0-9;]*m')

def strip_ansi(text: str) -> str:
    return ansi_escape.sub('', text)

def extract_progress(line: str) -> str | None:
    match = re.search(r"\[download]\s+(.*)", line)
    return match.group(1).strip() if match else None

def extract_info(line: str) -> str | None:
    match = re.search(r"\[INFO\s+[^]]+]\s+(.*)", line)
    return match.group(1).strip() if match else None

@dataclass
class TaskContext:
    uuid: str
    urls: list[str]
    downloads_path: str
    user_id: int
    chat_id: int
    msg_id: int

application = Application.builder().token(TELEGRAM_TOKEN).build()


async def callback_start(context: ContextTypes.DEFAULT_TYPE):
    command = [
        "gamdl",
        "-c",
        "./data/cookies.txt",
        "-s",
        "--cover-size",
        "320",
        "-o",
        context.job.data.downloads_path,
        *context.job.data.urls,
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

    info_message = await context.bot.send_message(context.job.chat_id, text="Started...", reply_to_message_id=context.job.data.msg_id)
    progress_message = None

    while True:
        raw_line = process.stdout.readline()
        if raw_line == "" and process.poll() is not None:
            break
        if raw_line:
            line = strip_ansi(raw_line)
            progress = extract_progress(line)
            info = extract_info(line)
            try:
                if progress:
                    if progress_message is None:
                        progress_message = await application.send_message(
                            context.job.chat_id,
                            text=progress,
                        )
                elif info:
                    await info_message.edit_text(info)
                    if info.lower().startswith("done") and progress_message is not None:
                        await progress_message.delete()
                        progress_message = None
            except Exception as e:
                print(e)
        await asyncio.sleep(0.9)  # avoid flooding Telegram with too many edits

        m4a_files = glob.glob(f'{context.job.data.downloads_path}/**/*.m4a', recursive=True)
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
                msg = await application.send_message(context.job.chat_id,text=f"Uploading {artist} - {title}")
                await application.send_audio(
                    chat_id=context.job.chat_id,
                    title=title,
                    performer=artist,
                    thumbnail=open(cover_path, "rb"),
                    audio=open(m4a_file, "rb"),
                )
                await msg.delete()

            except Exception as e:
                logging.error(e)

        if os.path.exists(context.job.data.downloads_path):
            shutil.rmtree(context.job.data.downloads_path)


async def callback_validate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    msg_id = update.message.message_id
    if user_id not in TELEGRAM_ADMIN_ID:
        return await update.message.reply_text("You are not authorized!")
    message_text = update.message.text
    url_regex = r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"  # Regular expression for URLs
    urls: list[str] = re.findall(url_regex, message_text)
    if len(urls) <= 0:
        return None

    task_id = str(uuid4())
    downloads_path = f"./downloads-{task_id}"
    task_context = TaskContext(
        uuid=task_id,
        urls=urls,
        downloads_path=downloads_path,
        user_id=user_id,
        chat_id=chat_id,
        msg_id=msg_id,
    )
    return context.job_queue.run_once(callback_start, 0, data=task_context, chat_id=chat_id)

msg_handler = MessageHandler(
    filters.TEXT & (
      filters.Entity(MessageEntity.URL) |
      filters.Entity(MessageEntity.TEXT_LINK)
   ),
    callback_validate,
)

application.add_handler(msg_handler)

# try:
application.run_polling()
# except Exception: ...
