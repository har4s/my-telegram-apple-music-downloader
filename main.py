import datetime
import glob
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
import re
from subprocess import Popen
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
    started_at: datetime
    uuid: str
    urls: list[str]
    downloads_path: str
    user_id: int
    chat_id: int
    msg_id: int
    info_message_id: int | None = None
    progress_message_id: int | None = None


tasks_cache: dict[str,tuple[Popen[str],TaskContext]] = {}

application = Application.builder().token(TELEGRAM_TOKEN).build()

async def callback_cleanup(context:ContextTypes.DEFAULT_TYPE):
    cache_copy = tasks_cache.copy()
    for uuid in cache_copy.keys():
        _, task_context = tasks_cache[uuid]
        if task_context.started_at + datetime.timedelta(minutes=15) < datetime.datetime.now(datetime.UTC):
            context.bot.delete_message(chat_id=task_context.chat_id, message_id=task_context.progress_message_id)
            context.bot.delete_message(chat_id=task_context.chat_id, message_id=task_context.info_message_id)
            del tasks_cache[uuid]

async def callback_done(context: ContextTypes.DEFAULT_TYPE):
    m4a_files = glob.glob(f"{context.job.data.downloads_path}/**/*.m4a", recursive=True)
    m4a_files = [os.path.abspath(path) for path in m4a_files]

    for m4a_file in m4a_files:
        music = MP4(m4a_file)
        music.update(
            {
                MP4_TAGS_MAP["comment"]: "t.me/myfuckinglifetimes",
            }
        )
        music.save()
        folder = os.path.dirname(m4a_file)
        cover_path = folder + "/Cover.jpg"
        title = music[MP4_TAGS_MAP["title"]][0]
        artist = music[MP4_TAGS_MAP["artist"]][0]

        try:
            msg = await application.send_message(
                context.job.chat_id, text=f"Uploading {artist} - {title}"
            )
            await application.send_audio(
                chat_id=context.job.chat_id,
                title=title,
                performer=artist,
                thumbnail=open(cover_path, "rb"),
                audio=open(m4a_file, "rb"),
            )
            await msg.delete()
            await context.bot.deleteMessage(
                chat_id=context.job.chat_id,
                message_id=context.job.data.info_message_id,
            )

        except Exception as e:
            logging.error(e)

        if os.path.exists(context.job.data.downloads_path):
            shutil.rmtree(context.job.data.downloads_path)


async def callback_process(context: ContextTypes.DEFAULT_TYPE):
    cache_copy = tasks_cache.copy()
    for uuid in cache_copy.keys():
        process, task_context = tasks_cache[uuid]
        raw_line = process.stdout.readline()
        if raw_line == "" and process.poll() is not None:
            context.job_queue.run_once(callback_done, 0, data=task_context, chat_id=task_context.chat_id)
            del tasks_cache[uuid]
            return
        if raw_line:
            line = strip_ansi(raw_line)
            progress = extract_progress(line)
            info = extract_info(line)
            try:
                if progress:
                    await context.bot.editMessageText(
                        chat_id=context.job.chat_id,
                        message_id=task_context.progress_message_id,
                        text=progress,
                    )
                elif info:
                    await context.bot.editMessageText(
                        chat_id=task_context.chat_id,
                        message_id=task_context.info_message_id,
                        text=info,
                    )
                    if info.lower().startswith("done") and task_context.progress_message_id is not None:
                        await context.bot.deleteMessage(
                            chat_id=task_context.chat_id,
                            message_id=task_context.progress_message_id,
                        )
                        task_context.progress_message_id = None
            except Exception as e:
                print(e)


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
    progress_message = await context.bot.send_message(context.job.chat_id, text="Downloading...", reply_to_message_id=info_message.message_id)

    context.job.data.info_message_id = info_message.message_id
    context.job.data.progress_message_id = progress_message.message_id

    tasks_cache[context.job.data.uuid] = (process, context.job.data,)


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
        started_at=datetime.datetime.now(datetime.UTC),
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
application.job_queue.run_repeating(callback_process, 6)
application.job_queue.run_repeating(callback_cleanup, 300)


# try:
application.run_polling()
# except Exception: ...
