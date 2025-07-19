import datetime
import glob
import logging
import os
import shutil
from dataclasses import dataclass
import re
from pathlib import Path
from uuid import uuid4

import colorama
from gamdl.apple_music_api import AppleMusicApi
from gamdl.constants import X_NOT_FOUND_STRING, LEGACY_CODECS, MP4_TAGS_MAP
from gamdl.downloader import Downloader
from gamdl.downloader_music_video import DownloaderMusicVideo
from gamdl.downloader_post import DownloaderPost
from gamdl.downloader_song import DownloaderSong
from gamdl.downloader_song_legacy import DownloaderSongLegacy
from gamdl.enums import (
    SongCodec,
    RemuxMode,
    DownloadMode,
    CoverFormat,
    SyncedLyricsFormat,
    RemuxFormatMusicVideo,
    PostQuality,
    MusicVideoCodec,
)
from gamdl.itunes_api import ItunesApi
from gamdl.utils import prompt_path, color_text
from mutagen.mp4 import MP4
from telegram import Update, MessageEntity
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from config import TELEGRAM_TOKEN, TELEGRAM_ADMIN_ID

@dataclass
class TaskContext:
    started_at: datetime.datetime
    urls: list[str]
    uuid: str
    downloads_path: str
    user_id: int
    chat_id: int
    errors: int = 0
    process_msg_id: str | None = None

in_memory_process_cache: dict[str,tuple[bool, list[str], TaskContext]] = {}

logger = logging.getLogger("my-telegram-apple-music-downloader")

application = Application.builder().token(TELEGRAM_TOKEN).build()
job_queue = application.job_queue


async def callback_finish(context: ContextTypes.DEFAULT_TYPE):

    del in_memory_process_cache[context.job.data.uuid]

    if context.job.data.process_msg_id:
        await context.bot.deleteMessage(
            chat_id=context.job.data.chat_id, message_id=context.job.data.process_msg_id,
        )

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
            msg = await application.send_message(context.job.data.chat_id, text=f"Uploading {artist} - {title}")
            await application.send_audio(
                chat_id=context.job.data.chat_id,
                title=title,
                performer=artist,
                thumbnail=open(cover_path, "rb"),
                audio=open(m4a_file, "rb"),
            )
            await msg.delete()
        except Exception as e:
            print(e)

    if os.path.exists(context.job.data.downloads_path):
        shutil.rmtree(context.job.data.downloads_path)


async def callback_process(context: ContextTypes.DEFAULT_TYPE):
    copied_mem = in_memory_process_cache.copy()
    for task_id, (done, messages, task_context) in copied_mem.items():
        if done and task_context.started_at + datetime.timedelta(minutes=1) < datetime.datetime.now(datetime.UTC):
            context.job_queue.run_once(
                callback_finish, 0, data=task_context, chat_id=task_context.chat_id
            )
        elif task_context.process_msg_id:
            await context.bot.editMessageText(chat_id=task_context.chat_id, message_id=task_context.process_msg_id, text="\n".join(messages[:5]))

async def callback_start(context: ContextTypes.DEFAULT_TYPE):
    urls: list[str] = context.job.data.urls
    cookies_path: Path = Path("./data/cookies.txt")
    output_path: Path = Path(context.job.data.downloads_path)
    ffmpeg_path: str | Path = "ffmpeg"
    save_cover: bool = True
    overwrite: bool = True
    disable_music_video_skip: bool = False
    read_urls_as_txt: bool = False
    save_playlist: bool = False
    synced_lyrics_only: bool = False
    no_synced_lyrics: bool = False
    log_level: str = "INFO"
    language: str = "en-US"
    temp_path: Path = Path("./temp")
    wvd_path: Path | None = None
    nm3u8dlre_path: str = "N_m3u8DL-RE"
    mp4decrypt_path: str = "mp4decrypt"
    mp4box_path: str = "MP4Box"
    download_mode: DownloadMode = DownloadMode.YTDLP
    remux_mode: RemuxMode = RemuxMode.FFMPEG
    cover_format: CoverFormat = CoverFormat.JPG
    template_folder_album: str = "{album_artist}/{album}"
    template_folder_compilation: str = "Compilations/{album}"
    template_file_single_disc: str = "{track:02d} {title}"
    template_file_multi_disc: str = "{disc}-{track:02d} {title}"
    template_folder_no_album: str = "{artist}/Unknown Album"
    template_file_no_album: str = "{title}"
    template_file_playlist: str = "Playlists/{playlist_artist}/{playlist_title}"
    template_date: str = "%Y-%m-%dT%H:%M:%SZ"
    exclude_tags: str | None = None
    cover_size: int = 320
    truncate: int | None = None
    codec_song: SongCodec = SongCodec.AAC_LEGACY
    synced_lyrics_format: SyncedLyricsFormat = SyncedLyricsFormat.LRC
    codec_music_video: MusicVideoCodec = MusicVideoCodec.H264
    remux_format_music_video: RemuxFormatMusicVideo = RemuxFormatMusicVideo.M4V
    quality_post: PostQuality = PostQuality.BEST


    cookies_path = prompt_path(True, cookies_path, "Cookies file")
    apple_music_api = AppleMusicApi.from_netscape_cookies(
        cookies_path,
        language,
    )
    itunes_api = ItunesApi(
        apple_music_api.storefront,
        apple_music_api.language,
    )
    downloader = Downloader(
        apple_music_api,
        itunes_api,
        output_path,
        temp_path,
        wvd_path,
        nm3u8dlre_path,
        mp4decrypt_path,
        ffmpeg_path,
        mp4box_path,
        download_mode,
        remux_mode,
        cover_format,
        template_folder_album,
        template_folder_compilation,
        template_file_single_disc,
        template_file_multi_disc,
        template_folder_no_album,
        template_file_no_album,
        template_file_playlist,
        template_date,
        exclude_tags,
        cover_size,
        truncate,
        log_level in ("WARNING", "ERROR"),
    )
    downloader_song = DownloaderSong(
        downloader,
        codec_song,
        synced_lyrics_format,
    )
    downloader_song_legacy = DownloaderSongLegacy(
        downloader,
        codec_song,
    )
    downloader_music_video = DownloaderMusicVideo(
        downloader,
        codec_music_video,
        remux_format_music_video,
    )
    downloader_post = DownloaderPost(
        downloader,
        quality_post,
    )

    msg_start = await context.bot.send_message(
        chat_id=context.job.chat_id,
        text="Starting!",
    )
    context.job.data.process_msg_id = msg_start.id

    skip_mv = True
    if not synced_lyrics_only:
        # if wvd_path:
        #     wvd_path = prompt_path(True, wvd_path, ".wvd file")
        downloader.set_cdm()
        if not downloader.ffmpeg_path_full and (
            remux_mode == RemuxMode.FFMPEG or download_mode == DownloadMode.NM3U8DLRE
        ):
            logger.critical(X_NOT_FOUND_STRING.format("ffmpeg", ffmpeg_path))
            msg_start.edit_text("Error: Failed to start!")
            return
        if not downloader.mp4box_path_full and remux_mode == RemuxMode.MP4BOX:
            logger.critical(X_NOT_FOUND_STRING.format("MP4Box", mp4box_path))
            msg_start.edit_text("Error: Failed to start!")
            return
        if (
            not downloader.mp4decrypt_path_full
            and codec_song
            not in (
                SongCodec.AAC_LEGACY,
                SongCodec.AAC_HE_LEGACY,
            )
            or (remux_mode == RemuxMode.MP4BOX and not downloader.mp4decrypt_path_full)
        ):
            logger.critical(X_NOT_FOUND_STRING.format("mp4decrypt", mp4decrypt_path))
            msg_start.edit_text("Error: Failed to start!")
            return
        if (
            download_mode == DownloadMode.NM3U8DLRE
            and not downloader.nm3u8dlre_path_full
        ):
            logger.critical(X_NOT_FOUND_STRING.format("N_m3u8DL-RE", nm3u8dlre_path))
            msg_start.edit_text("Error: Failed to start!")
            return
        # if not downloader.mp4decrypt_path_full:
            # logger.warning(
            #     X_NOT_FOUND_STRING.format("mp4decrypt", mp4decrypt_path)
            #     + ", music videos will not be downloaded"
            # )
            # skip_mv = True
        if codec_song not in LEGACY_CODECS:
            logger.warning(
                "You have chosen an experimental codec. "
                "They're not guaranteed to work due to API limitations."
            )

    in_memory_process_cache[context.job.data.uuid] = (False, [msg_start.text], context.job.data,)

    error_count = 0

    if read_urls_as_txt:
        _urls = []
        for url in urls:
            if Path(url).exists():
                _urls.extend(Path(url).read_text(encoding="utf-8").splitlines())
        urls = _urls
    for url_index, url in enumerate(urls, start=1):
        url_progress = color_text(f"URL {url_index}/{len(urls)}", colorama.Style.DIM)
        try:
            # logger.info(f'({url_progress}) Checking "{url}"')
            in_memory_process_cache[context.job.data.uuid] = (False, in_memory_process_cache[context.job.data.uuid][1] + [f'({url_progress}) Checking "{url}"'], context.job.data,)
            url_info = downloader.get_url_info(url)
            download_queue = downloader.get_download_queue(url_info)
            download_queue_medias_metadata = download_queue.medias_metadata
        except Exception:
            error_count += 1
            # logger.error(
            #     f'({url_progress}) Failed to check "{url}"',
            #     exc_info=not no_exceptions,
            #
            in_memory_process_cache[context.job.data.uuid] = (False, in_memory_process_cache[context.job.data.uuid][1] + [f'({url_progress}) Failed to check "{url}"'], context.job.data,)

            continue
        for download_index, media_metadata in enumerate(
            download_queue_medias_metadata, start=1
        ):
            queue_progress = f"Track {download_index}/{len(download_queue_medias_metadata)} from URL {url_index}/{len(urls)}",

            try:
                media_id = downloader.get_media_id(media_metadata)
                remuxed_path = None
                if download_queue.playlist_attributes:
                    playlist_track = download_index
                else:
                    playlist_track = None
                # logger.info(
                #     f'({queue_progress}) Downloading "{media_metadata["attributes"]["name"]}"'
                # )
                in_memory_process_cache[context.job.data.uuid] = (
                    False,
                    in_memory_process_cache[context.job.data.uuid][1] + [f'({queue_progress}) Downloading "{media_metadata["attributes"]["name"]}"'],
                    context.job.data,
                )
                if media_id is None:
                    # logger.warning(
                    #     f"({queue_progress}) Track is not streamable or downloadable, skipping"
                    # )
                    continue
                if (
                    (synced_lyrics_only and media_metadata["type"] != "songs")
                    or (media_metadata["type"] == "music-videos" and skip_mv)
                    or (
                        media_metadata["type"] == "music-videos"
                        and url_info.type == "album"
                        and not disable_music_video_skip
                    )
                ):
                    # logger.warning(
                    #     f"({queue_progress}) Track is not downloadable with current configuration, skipping"
                    # )
                    continue
                elif media_metadata["type"] in ("songs", "library-songs"):
                    # logger.debug("Getting lyrics")
                    lyrics = downloader_song.get_lyrics(media_metadata)
                    # logger.debug("Getting webplayback")
                    webplayback = apple_music_api.get_webplayback(media_id)
                    tags = downloader_song.get_tags(
                        webplayback,
                        lyrics.unsynced if lyrics else None,
                    )
                    if playlist_track:
                        tags = {
                            **tags,
                            **downloader.get_playlist_tags(
                                download_queue.playlist_attributes,
                                playlist_track,
                            ),
                        }
                    final_path = downloader.get_final_path(tags, ".m4a")
                    lyrics_synced_path = downloader_song.get_lyrics_synced_path(
                        final_path
                    )
                    cover_url = downloader.get_cover_url(media_metadata)
                    cover_file_extesion = downloader.get_cover_file_extension(cover_url)
                    if cover_file_extesion:
                        cover_path = downloader_song.get_cover_path(
                            final_path,
                            cover_file_extesion,
                        )
                    else:
                        cover_path = None
                    if synced_lyrics_only:
                        pass
                    elif final_path.exists() and not overwrite:
                        # logger.warning(
                        #     f'({queue_progress}) Song already exists at "{final_path}", skipping'
                        # )
                        ...
                    else:
                        # logger.debug("Getting stream info")
                        if codec_song in LEGACY_CODECS:
                            stream_info = downloader_song_legacy.get_stream_info(
                                webplayback
                            )
                            # logger.debug("Getting decryption key")
                            decryption_key = downloader_song_legacy.get_decryption_key(
                                stream_info.audio_track.widevine_pssh,
                                media_id,
                            )
                        else:
                            stream_info = downloader_song.get_stream_info(
                                media_metadata
                            )
                            if (
                                stream_info is None
                                or not stream_info.audio_track.widevine_pssh
                            ):
                                # logger.warning(
                                #     f"({queue_progress}) Song is not downloadable or is not"
                                #     " available in the chosen codec, skipping"
                                # )
                                continue
                            # logger.debug("Getting decryption key")
                            decryption_key = downloader.get_decryption_key(
                                stream_info.audio_track.widevine_pssh,
                                media_id,
                            )
                        encrypted_path = downloader_song.get_encrypted_path(media_id)
                        decrypted_path = downloader_song.get_decrypted_path(media_id)
                        remuxed_path = downloader_song.get_remuxed_path(
                            media_id,
                            stream_info.file_format,
                        )
                        # logger.debug(f'Downloading to "{encrypted_path}"')
                        downloader.download(
                            encrypted_path,
                            stream_info.audio_track.stream_url,
                        )
                        if codec_song in LEGACY_CODECS:
                            # logger.debug(
                            #     f'Decrypting/Remuxing to "{decrypted_path}"/"{remuxed_path}"'
                            # )
                            downloader_song_legacy.remux(
                                encrypted_path,
                                decrypted_path,
                                remuxed_path,
                                decryption_key,
                            )
                        else:
                            # logger.debug(f'Decrypting to "{decrypted_path}"')
                            downloader_song.decrypt(
                                encrypted_path,
                                decrypted_path,
                                decryption_key,
                            )
                            # logger.debug(f'Remuxing to "{final_path}"')
                            downloader_song.remux(
                                decrypted_path,
                                remuxed_path,
                            )
                    if no_synced_lyrics or not lyrics or not lyrics.synced:
                        pass
                    elif lyrics_synced_path.exists() and not overwrite:
                        # logger.debug(
                        #     f'Synced lyrics already exists at "{lyrics_synced_path}", skipping'
                        # )
                        ...
                    else:
                        # logger.debug(f'Saving synced lyrics to "{lyrics_synced_path}"')
                        downloader_song.save_lyrics_synced(
                            lyrics_synced_path, lyrics.synced
                        )
                elif media_metadata["type"] in ("music-videos", "library-music-videos"):
                    music_video_id_alt = (
                        downloader_music_video.get_music_video_id_alt(media_metadata)
                        or media_id
                    )
                    # logger.debug("Getting iTunes page")
                    itunes_page = itunes_api.get_itunes_page(
                        "music-video", music_video_id_alt
                    )
                    if music_video_id_alt == media_id:
                        stream_url = (
                            downloader_music_video.get_stream_url_from_itunes_page(
                                itunes_page
                            )
                        )
                    else:
                        # logger.debug("Getting webplayback")
                        webplayback = apple_music_api.get_webplayback(media_id)
                        stream_url = (
                            downloader_music_video.get_stream_url_from_webplayback(
                                webplayback
                            )
                        )
                    # logger.debug("Getting tags")
                    tags = downloader_music_video.get_tags(
                        music_video_id_alt,
                        itunes_page,
                        media_metadata,
                    )
                    if playlist_track:
                        tags = {
                            **tags,
                            **downloader.get_playlist_tags(
                                download_queue.playlist_attributes,
                                playlist_track,
                            ),
                        }
                    # logger.debug("Getting M3U8 data")
                    m3u8_data = downloader_music_video.get_m3u8_master_data(stream_url)
                    stream_info_av = downloader_music_video.get_stream_info(
                        m3u8_data,
                    )
                    final_file_extesion = downloader.get_final_file_extension(
                        stream_info_av.file_format,
                    )
                    final_path = downloader.get_final_path(
                        tags,
                        final_file_extesion,
                    )
                    cover_url = downloader.get_cover_url(media_metadata)
                    cover_file_extesion = downloader.get_cover_file_extension(cover_url)
                    if cover_file_extesion:
                        cover_path = downloader_music_video.get_cover_path(
                            final_path,
                            cover_file_extesion,
                        )
                    else:
                        cover_path = None
                    if final_path.exists() and not overwrite:
                        # logger.warning(
                        #     f'({queue_progress}) Music video already exists at "{final_path}", skipping'
                        # )
                        ...
                    else:
                        decryption_key_video = downloader.get_decryption_key(
                            stream_info_av.video_track.widevine_pssh,
                            media_id,
                        )
                        decryption_key_audio = downloader.get_decryption_key(
                            stream_info_av.audio_track.widevine_pssh,
                            media_id,
                        )
                        encrypted_path_video = (
                            downloader_music_video.get_encrypted_path_video(media_id)
                        )
                        encrypted_path_audio = (
                            downloader_music_video.get_encrypted_path_audio(media_id)
                        )
                        decrypted_path_video = (
                            downloader_music_video.get_decrypted_path_video(media_id)
                        )
                        decrypted_path_audio = (
                            downloader_music_video.get_decrypted_path_audio(media_id)
                        )
                        remuxed_path = downloader_music_video.get_remuxed_path(
                            media_id,
                            final_file_extesion,
                        )
                        # logger.debug(f'Downloading video to "{encrypted_path_video}"')
                        downloader.download(
                            encrypted_path_video,
                            stream_info_av.video_track.stream_url,
                        )
                        # logger.debug(f'Downloading audio to "{encrypted_path_audio}"')
                        downloader.download(
                            encrypted_path_audio,
                            stream_info_av.audio_track.stream_url,
                        )
                        # logger.debug(f'Decrypting video to "{decrypted_path_video}"')
                        downloader_music_video.decrypt(
                            encrypted_path_video,
                            decryption_key_video,
                            decrypted_path_video,
                        )
                        # logger.debug(f'Decrypting audio to "{decrypted_path_audio}"')
                        downloader_music_video.decrypt(
                            encrypted_path_audio,
                            decryption_key_audio,
                            decrypted_path_audio,
                        )
                        # logger.debug(f'Remuxing to "{remuxed_path}"')
                        downloader_music_video.remux(
                            decrypted_path_video,
                            decrypted_path_audio,
                            remuxed_path,
                        )
                elif media_metadata["type"] == "uploaded-videos":
                    stream_url = downloader_post.get_stream_url(media_metadata)
                    tags = downloader_post.get_tags(media_metadata)
                    final_path = downloader.get_final_path(tags, ".m4v")
                    cover_url = downloader.get_cover_url(media_metadata)
                    cover_file_extesion = downloader.get_cover_file_extension(cover_url)
                    if cover_file_extesion:
                        cover_path = downloader_music_video.get_cover_path(
                            final_path,
                            cover_file_extesion,
                        )
                    else:
                        cover_path = None
                    if final_path.exists() and not overwrite:
                        # logger.warning(
                        #     f'({queue_progress}) Post video already exists at "{final_path}", skipping'
                        # )
                        ...
                    else:
                        remuxed_path = downloader_post.get_post_temp_path(media_id)
                        # logger.debug(f'Downloading to "{remuxed_path}"')
                        downloader.download_ytdlp(remuxed_path, stream_url)
                if synced_lyrics_only or not save_cover or cover_path is None:
                    pass
                elif cover_path.exists() and not overwrite:
                    # logger.debug(f'Cover already exists at "{cover_path}", skipping')
                    ...
                else:
                    # logger.debug(f'Saving cover to "{cover_path}"')
                    downloader.save_cover(cover_path, cover_url)
                if remuxed_path:
                    # logger.debug("Applying tags")
                    downloader.apply_tags(remuxed_path, tags, cover_url)
                    # logger.debug(f'Moving to "{final_path}"')
                    downloader.move_to_output_path(remuxed_path, final_path)
                if (
                    not synced_lyrics_only
                    and save_playlist
                    and download_queue.playlist_attributes
                ):
                    playlist_file_path = downloader.get_playlist_file_path(tags)
                    # logger.debug(f'Updating M3U8 playlist from "{playlist_file_path}"')
                    downloader.update_playlist_file(
                        playlist_file_path,
                        final_path,
                        playlist_track,
                    )
            except Exception:
                error_count += 1
                # logger.error(
                #     f'({queue_progress}) Failed to download "{media_metadata["attributes"]["name"]}"',
                #     exc_info=not no_exceptions,
                # )
                in_memory_process_cache[context.job.data.uuid] = (
                    False,
                    in_memory_process_cache[context.job.data.uuid][1] + [f'({queue_progress}) Failed to download "{media_metadata["attributes"]["name"]}"'],
                    context.job.data,
                )
            finally:
                if temp_path.exists():
                    # logger.debug(f'Cleaning up "{temp_path}"')
                    # in_memory_process_cache[context.job.data.uuid] = (
                    #     False,
                    #     f'Cleaning up "{temp_path}"',
                    #     context.job.data,
                    # )
                    downloader.cleanup_temp_path()
    # logger.info(f"Done ({error_count} error(s))")
    context.job.data.errors = error_count
    in_memory_process_cache[context.job.data.uuid] = (
        True,
        in_memory_process_cache[context.job.data.uuid][1] + [f"Done ({error_count} error(s))"],
        context.job.data,
    )

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

    task_id = str(uuid4())
    downloads_path = f"./downloads-{task_id}"
    task_context = TaskContext(
        started_at=datetime.datetime.now(datetime.UTC),
        urls=urls,
        uuid=task_id,
        downloads_path=downloads_path,
        user_id=user_id,
        chat_id=chat_id,
    )
    context.job_queue.run_once(callback_start, 0, data=task_context, chat_id=chat_id)
    return None

msg_handler = MessageHandler(
    filters.TEXT & (
      filters.Entity(MessageEntity.URL) |
      filters.Entity(MessageEntity.TEXT_LINK)
   ),
    callback_validate,
)

application.add_handler(msg_handler)

job_processing = job_queue.run_repeating(callback_process, interval=10)

# try:
application.run_polling()
# except Exception: ...
