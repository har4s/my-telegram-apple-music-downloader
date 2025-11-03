import json
import logging
import re
import shutil
from io import BytesIO
from pathlib import Path

from gamdl.api import AppleMusicApi
from gamdl.downloader import (
    AppleMusicBaseDownloader,
    AppleMusicDownloader,
    AppleMusicMusicVideoDownloader,
    AppleMusicSongDownloader,
    AppleMusicUploadedVideoDownloader,
)
from gamdl.downloader.downloader_song import SongCodec
from mutagen.mp4 import MP4
from PIL import Image, ImageOps
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
SYLT_ATOM = "----:com.apple.iTunes:SYLT"
COMMENT_TEXT = "t.me/myfuckinglifetimes"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


LRC_TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?]")

# Codec priority list - try from highest to lowest quality
CODEC_PRIORITY = [
    SongCodec.ALAC,
    SongCodec.ATMOS,
    SongCodec.AC3,
    SongCodec.AAC,
    SongCodec.AAC_LEGACY,
]

# Global API instance
_api: AppleMusicApi | None = None


async def get_api() -> AppleMusicApi:
    """Get or initialize the global API instance."""
    global _api
    if _api is None:
        _api = AppleMusicApi.from_netscape_cookies(cookies_path="./data/cookies.txt")
        await _api.setup()
        logger.info("Initialized Apple Music API")
    return _api


async def create_downloader(
    output_path: Path, codec: SongCodec = SongCodec.ALAC
) -> AppleMusicDownloader:
    """Create a downloader instance with per-message configuration."""
    api = await get_api()

    # Initialize base downloader with message-specific config
    base_downloader = AppleMusicBaseDownloader(
        apple_music_api=api,
        output_path=str(output_path),
        save_cover=True,
    )
    base_downloader.setup()

    song_downloader = AppleMusicSongDownloader(base_downloader, codec=codec)
    song_downloader.setup()

    music_video_downloader = AppleMusicMusicVideoDownloader(base_downloader)
    music_video_downloader.setup()

    uploaded_video_downloader = AppleMusicUploadedVideoDownloader(base_downloader)
    uploaded_video_downloader.setup()

    # Create main downloader
    downloader = AppleMusicDownloader(
        base_downloader,
        song_downloader,
        music_video_downloader,
        uploaded_video_downloader,
        skip_music_videos=True,
    )
    return downloader


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


def parse_lrc_file(path: Path) -> tuple[list[tuple[int, str]], str]:
    entries: list[tuple[int, str]] = []
    plain_lines: list[str] = []

    with path.open("r", encoding="utf-8") as lyrics:
        for raw_line in lyrics:
            line = raw_line.strip()
            if not line:
                continue

            timestamps = list(LRC_TIMESTAMP_RE.finditer(line))
            if not timestamps:
                continue

            text = LRC_TIMESTAMP_RE.sub("", line).strip()
            if not text:
                continue

            plain_lines.append(text)
            for match in timestamps:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                raw_fraction = match.group(3) or ""
                fraction_ms = int((raw_fraction + "000")[:3]) if raw_fraction else 0
                total_ms = minutes * 60000 + seconds * 1000 + fraction_ms
                entries.append((total_ms, text))

    entries.sort(key=lambda item: item[0])
    return entries, "\n".join(plain_lines)


def load_lyrics(path: Path) -> tuple[list[tuple[int, str]], str]:
    lrc_path = path.with_suffix(".lrc")
    if not lrc_path.exists():
        logger.debug("Lyrics file not found for %s", path.name)
        return [], ""

    try:
        entries, plain_text = parse_lrc_file(lrc_path)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to parse lyrics file %s: %s", lrc_path, exc)
        return [], ""

    if not entries and not plain_text:
        logger.warning("No timestamped lyrics found in %s", lrc_path.name)
    return entries, plain_text


def prepare_track(path: Path) -> tuple[str, str]:
    synced_entries, plain_text = load_lyrics(path)
    track = MP4(path)
    if track.tags is None:
        track.add_tags()
    tags = track.tags
    tags[TAGS["comment"]] = [COMMENT_TEXT]
    if plain_text:
        tags[TAGS["lyrics"]] = [plain_text]
    if synced_entries:
        sylt_entries = [{"time_ms": ms, "text": text} for ms, text in synced_entries]
        try:
            payload = json.dumps(sylt_entries, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:  # pragma: no cover
            logger.warning(
                "Failed to serialize synchronized lyrics for %s: %s", path.name, exc
            )
        else:
            tags[SYLT_ATOM] = [payload]
    title = (tags.get(TAGS["title"]) or [path.stem])[0]
    artist = (tags.get(TAGS["artist"]) or ["Unknown artist"])[0]
    track.save()
    return title, artist


def prepare_thumbnail(path: Path) -> BytesIO | None:
    if not path.exists():
        return None

    try:
        with path.open("rb") as source:
            image = Image.open(source)
            resample = (
                Image.Resampling.LANCZOS
                if hasattr(Image, "Resampling")
                else Image.LANCZOS
            )
            fitted = ImageOps.fit(image.convert("RGB"), (320, 320), method=resample)
    except Exception:  # pragma: no cover - best effort thumbnail handling
        logger.exception("Failed to prepare cover thumbnail at %s", path)
        return None

    buffer = BytesIO()
    fitted.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer


async def download_url(url: str, downloader: AppleMusicDownloader) -> bool:
    """Download a single URL using gamdl API. Returns True on success."""
    try:
        url_info = downloader.get_url_info(url)
        if not url_info:
            logger.warning("Failed to get URL info for: %s", url)
            return False

        download_queue = await downloader.get_download_queue(url_info)
        if not download_queue:
            logger.warning("Empty download queue for: %s", url)
            return False

        for download_item in download_queue:
            await downloader.download(download_item)

        return True
    except Exception as exc:
        logger.exception("Failed to download %s: %s", url, exc)
        return False


async def watch_download(
    chat_id: int, reply_to: int, download_dir: Path, urls: list[str], bot
) -> None:
    logger.info(
        "Watching download for chat=%s reply_to=%s with %s URL(s)",
        chat_id,
        reply_to,
        len(urls),
    )
    info = await bot.send_message(
        chat_id=chat_id, text="Started...", reply_to_message_id=reply_to
    )
    try:
        # Try downloading with codec fallback
        success_count = 0
        for codec in CODEC_PRIORITY:
            logger.info("Attempting download with codec: %s", codec.name)
            # Create downloader instance with message-specific config and codec
            downloader = await create_downloader(download_dir, codec=codec)

            # Download all URLs with current codec
            current_success = 0
            for url in urls:
                if await download_url(url, downloader):
                    current_success += 1

            success_count = current_success
            if success_count > 0:
                logger.info("Successfully downloaded with codec: %s", codec.name)
                break

            # Clean up failed attempts before trying next codec
            if download_dir.exists():
                shutil.rmtree(download_dir, ignore_errors=True)
                download_dir.mkdir(parents=True, exist_ok=True)

        if success_count == 0:
            logger.error(
                "All downloads failed for chat=%s after trying all codecs", chat_id
            )
            await info.edit_text("Download failed with all codecs.")
            return

        tracks = sorted(download_dir.rglob("*.m4a"))
        if not tracks:
            logger.warning("No .m4a tracks found in %s", download_dir)
            await info.edit_text("Nothing to upload.")
            return

        logger.info("Uploading %s track(s) from %s", len(tracks), download_dir)
        await info.edit_text("Uploading audio...")
        for track in tracks:
            title, artist = prepare_track(track)
            cover = track.with_name("Cover.jpg")
            thumbnail = prepare_thumbnail(cover)
            with track.open("rb") as audio:
                payload = dict(
                    chat_id=chat_id, audio=audio, title=title, performer=artist
                )
                if thumbnail:
                    payload["thumbnail"] = thumbnail
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
        "Starting download for message %s into %s with %s link(s)",
        message.message_id,
        download_dir,
        len(urls),
    )

    context.application.create_task(
        watch_download(
            chat_id=message.chat_id,
            reply_to=message.message_id,
            download_dir=download_dir,
            urls=urls,
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

if __name__ == "__main__":
    application.run_polling()
