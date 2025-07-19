import asyncio
import datetime
import glob
import logging
import os
import shutil
from dataclasses import dataclass
import re

from gamdl.constants import MP4_TAGS_MAP
from mutagen.mp4 import MP4
from telegram import Update, MessageEntity
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from config import TELEGRAM_TOKEN, TELEGRAM_ADMIN_ID

from asyncio.subprocess import Process # noqa

@dataclass
class TaskContext:
    message_id: int
    dl_path:str
    process: Process
    started_at: datetime

application = Application.builder().token(TELEGRAM_TOKEN).build()


async def callback_start(context: ContextTypes.DEFAULT_TYPE):
    task_context: TaskContext = context.job.data
    info_message = await context.bot.send_message(context.job.chat_id, text="Started...", reply_to_message_id=task_context.message_id)
    # progress_message = await context.bot.send_message(context.job.chat_id, text="Waiting...", reply_to_message_id=info_message.message_id)

    return_code = await task_context.process.wait()

    await info_message.edit_text(text=f"Process finished with exit code {return_code}.")

    m4a_files = glob.glob(f"{task_context.dl_path}/**/*.m4a", recursive=True)
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
            await info_message.delete()
        except Exception as e:
            logging.error(e)

        if os.path.exists(task_context.dl_path):
            shutil.rmtree(task_context.dl_path)


async def callback_validate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    if user_id not in TELEGRAM_ADMIN_ID:
        return await update.message.reply_text("You are not authorized!")
    message_text = update.message.text
    url_regex = r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"  # Regular expression for URLs
    urls: list[str] = re.findall(url_regex, message_text)
    if len(urls) <= 0:
        return None

    downloads_path = f"./dl-{update.message.message_id}"

    args = [
        "-c",
        "./data/cookies.txt",
        "-s",
        "--cover-size",
        "320",
        "-o",
        downloads_path,
        *urls,
    ]

    process = await asyncio.create_subprocess_exec(
        "gamdl",
        * args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    task_context = TaskContext(
        message_id=update.message.message_id,
        dl_path=downloads_path,
        process=process,
        started_at=datetime.datetime.now(datetime.UTC),
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
