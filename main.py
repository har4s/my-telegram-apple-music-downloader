import asyncio
import asyncio.subprocess
import logging
import shutil
from contextlib import nullcontext
from pathlib import Path

from mutagen.mp4 import MP4
from telegram import MessageEntity, Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from config import TELEGRAM_ADMIN_ID, TELEGRAM_TOKEN


TAGS = {
    "album": "\xa9alb",
    "album_artist": "aART",
    "album_id": "plID",
    "album_sort": "soal",
    "artist": "\xa9ART",
    "artist_id": "atID",
    "artist_sort": "soar",
    "comment": "\xa9cmt",
    "composer": "\xa9wrt",
    "composer_id": "cmID",
    "composer_sort": "soco",
    "copyright": "cprt",
    "date": "\xa9day",
    "genre": "\xa9gen",
    "genre_id": "geID",
    "lyrics": "\xa9lyr",
    "media_type": "stik",
    "rating": "rtng",
    "storefront": "sfID",
    "title": "\xa9nam",
    "title_id": "cnID",
    "title_sort": "sonm",
    "xid": "xid ",
}
COMMENT_TEXT = "t.me/myfuckinglifetimes"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_urls(message) -> list[str]:
    if not message or not message.entities:
        return []
    text = message.text or ""
    urls: list[str] = []
    for entity in message.entities:
        if entity.type == MessageEntity.TEXT_LINK and entity.url:
            urls.append(entity.url)
        elif entity.type == MessageEntity.URL:
            start, end = entity.offset, entity.offset + entity.length
            urls.append(text[start:end])
    if urls:
        logger.info(
            "Extracted %s URL(s) from message %s",
            len(urls),
            getattr(message, "message_id", "?"),
        )
    else:
        logger.debug(
            "No URLs detected in message %s", getattr(message, "message_id", "?")
        )
    return urls


def prepare_track(path: Path) -> tuple[str, str]:
    track = MP4(path)
    tags = track.MP4Tags() or {}
    tags[TAGS["comment"]] = [COMMENT_TEXT]
    title = (tags.get(TAGS["title"]) or [path.stem])[0]
    artist = (tags.get(TAGS["artist"]) or ["Unknown artist"])[0]
    track.save()
    return title, artist


async def watch_download(
    chat_id: int, reply_to: int, download_dir: Path, process, bot
) -> None:
    logger.info("Watching download for chat=%s reply_to=%s", chat_id, reply_to)
    info = await bot.send_message(
        chat_id=chat_id, text="Started...", reply_to_message_id=reply_to
    )
    try:
        return_code = await process.wait()
        output_bytes = (
            await process.stdout.read() if getattr(process, "stdout", None) else b""
        )
        output_text = output_bytes.decode(errors="ignore").strip()

        if return_code:
            logger.error(
                "gamdl exited with code %s for chat=%s\n%s",
                return_code,
                chat_id,
                output_text,
            )
            message = (
                "Download failed."
                if not return_code
                else f"Download failed (exit {return_code})."
            )
            if output_text:
                message += "\nCheck logs for details."
            await info.edit_text(message)
            return

        tracks = sorted(download_dir.rglob("*.m4a"))
        if not tracks:
            logger.warning("No .m4a tracks found in %s", download_dir)
            if output_text:
                logger.info("gamdl output:\n%s", output_text)
            await info.edit_text("Nothing to upload.")
            return

        if output_text:
            logger.info("gamdl output:\n%s", output_text)

        logger.info("Uploading %s track(s) from %s", len(tracks), download_dir)
        await info.edit_text("Uploading audio...")
        for track in tracks:
            title, artist = prepare_track(track)
            cover = track.with_name("Cover.jpg")
            with (
                track.open("rb") as audio,
                cover.open("rb") if cover.exists() else nullcontext() as thumb,
            ):
                payload = dict(
                    chat_id=chat_id, audio=audio, title=title, performer=artist
                )
                if thumb:
                    payload["thumbnail"] = thumb
                await bot.send_audio(**payload)
        await info.delete()
    except Exception:  # pragma: no cover
        logger.exception("Download job failed")
        await bot.send_message(
            chat_id=chat_id, text="Download finished but upload failed."
        )
    finally:
        shutil.rmtree(download_dir, ignore_errors=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    if message.from_user and message.from_user.id not in TELEGRAM_ADMIN_ID:
        await message.reply_text("You are not authorized!")
        return

    user_id = message.from_user.id if message.from_user else "?"
    logger.info("Handling message %s from user %s", message.message_id, user_id)

    urls = extract_urls(message)
    if not urls:
        return

    download_dir = Path(f"dl-{message.message_id}")
    logger.info(
        "Launching gamdl for message %s into %s with %s link(s)",
        message.message_id,
        download_dir,
        len(urls),
    )
    process = await asyncio.create_subprocess_exec(
        "gamdl",
        "-c",
        "./data/cookies.txt",
        "-s",
        "--cover-size",
        "320",
        "-o",
        str(download_dir),
        *urls,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    logger.debug("Spawned gamdl pid=%s", getattr(process, "pid", "?"))

    context.application.create_task(
        watch_download(
            chat_id=message.chat_id,
            reply_to=message.message_id,
            download_dir=download_dir,
            process=process,
            bot=context.bot,
        )
    )


application = Application.builder().token(TELEGRAM_TOKEN).build()

application.add_handler(
    MessageHandler(
        filters.TEXT
        & (filters.Entity(MessageEntity.URL) | filters.Entity(MessageEntity.TEXT_LINK)),
        handle_message,
    )
)

application.run_polling()
