# Don't Remove Credit Tg - @VJ_Botz
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@Tech_VJ
# Ask Doubt on telegram @KingVJ01

import asyncio 
import pyrogram
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, UserAlreadyParticipant, InviteHashExpired, UsernameNotOccupied, ChannelInvalid, ChannelPrivate
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message 
from pyrogram.enums import ChatType, ParseMode, UserStatus, PollType, MessageMediaType, MessageEntityType, SentCodeType, NextCodeType
from pyrogram.raw import functions, types
from pyrogram.raw.base import InputPeer
import time
import os
import threading
import json
import re
import html
from config import API_ID, API_HASH
from database.db import database 
from TechVJ.strings import strings, HELP_TXT
from TechVJ.flood_control import flood_controller
import subprocess
import shutil
import io
import aiofiles
from TechVJ.progress_store import write_progress, read_progress, clear_progress
from TechVJ.buffer_manager import buffer_mgr

logger = logging.getLogger(__name__)

_bot_id_cache = None
_bot_username_cache = None

# TUZATISH: CHANNEL_INVALID — modul darajasida peer keshi
# {chat_id: True} — muvaffaqiyatli resolve qilingan peer'lar
# Bot restart bo'lganda kesh tozalanadi (bu normal — peer qayta resolve qilinadi)
_resolved_peers_cache: dict = {}


async def _get_bot_id(client):
    """Bot ID va username ni bir marta olib keshlaydi."""
    global _bot_id_cache, _bot_username_cache
    if _bot_id_cache is None:
        me = await client.get_me()
        _bot_id_cache = me.id
        _bot_username_cache = me.username
    return _bot_id_cache


async def _resolve_bot_peer(uclient, chat_id):
    """TUZATISH: PEER_ID_INVALID — user session orqali bot peer'ini resolve qiladi.

    Kesh-aware, FloodWait-safe.
    Tartib:
      1) Kesh tekshiruvi
      2) resolve_peer(@bot_username) — username bilan
      3) get_users(bot_username)
      4) resolve_peer(chat_id) — numeric ID
      5) get_chat(bot_id)
      6) get_users(chat_id) — numeric ID
    """
    global _resolved_peers_cache

    # Kesh tekshiruvi
    bot_cache_key = f"bot_{chat_id}"
    if bot_cache_key in _resolved_peers_cache:
        try:
            await uclient.resolve_peer(chat_id)
            return True
        except Exception:
            _resolved_peers_cache.pop(bot_cache_key, None)

    # 1) Username orqali resolve_peer — eng ishonchli
    if _bot_username_cache:
        try:
            await uclient.resolve_peer(f"@{_bot_username_cache}")
            _resolved_peers_cache[bot_cache_key] = True
            logger.debug(f"Bot peer resolved via resolve_peer(@{_bot_username_cache})")
            return True
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
        except Exception:
            pass

    # 2) get_users(username) — username orqali
    if _bot_username_cache:
        try:
            await uclient.get_users(_bot_username_cache)
            _resolved_peers_cache[bot_cache_key] = True
            logger.debug(f"Bot peer resolved via get_users(@{_bot_username_cache})")
            return True
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
        except Exception:
            pass

    # 3) resolve_peer(chat_id) — numeric ID bilan
    try:
        await uclient.resolve_peer(chat_id)
        _resolved_peers_cache[bot_cache_key] = True
        logger.debug(f"Bot peer resolved via resolve_peer({chat_id})")
        return True
    except FloodWait as fw:
        await asyncio.sleep(fw.value)
    except Exception:
        pass

    # 4) get_chat(bot_id)
    if _bot_id_cache:
        try:
            await uclient.get_chat(_bot_id_cache)
            _resolved_peers_cache[bot_cache_key] = True
            logger.debug(f"Bot peer resolved via get_chat({_bot_id_cache})")
            return True
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
        except Exception:
            pass

    # 5) get_users(chat_id) — numeric ID
    try:
        await uclient.get_users(chat_id)
        _resolved_peers_cache[bot_cache_key] = True
        logger.debug(f"Bot peer resolved via get_users({chat_id})")
        return True
    except FloodWait as fw:
        await asyncio.sleep(fw.value)
    except Exception:
        pass

    logger.warning(f"Could not resolve bot peer (chat_id={chat_id}, bot=@{_bot_username_cache}). "
                   f"User may need to /start the bot first.")
    return False


STATIC_FFMPEG_PATH = os.path.join(os.path.dirname(__file__), "..", "staticfiles", "ffmpeg")


def get_ffmpeg():
    """ffmpeg binary yo'lini qaytaradi. System ffmpeg bo'lmasa static ishlatadi."""
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    # static-ffmpeg paketi orqali avtomatik yuklash
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        if shutil.which("ffmpeg"):
            return "ffmpeg"
    except ImportError:
        pass
    # staticfiles/ papkasidagi manual binary (zaxira)
    if os.path.exists(STATIC_FFMPEG_PATH) and os.access(STATIC_FFMPEG_PATH, os.X_OK):
        return STATIC_FFMPEG_PATH
    return None


TWO_GB = 2 * 1024 * 1024 * 1024  # 2GB bytes
FOUR_GB = 4 * 1024 * 1024 * 1024  # 4GB bytes


async def split_file(file_path: str, chunk_size_bytes: int = TWO_GB) -> list:
    """
    Faylni chunk_size_bytes dan oshmaydigan qismlarga bo'ladi.
    Video/audio uchun ffmpeg -c copy ishlatiladi.
    Qaytaradi: [part_path1, part_path2, ...]
    """
    size = os.path.getsize(file_path)
    if size <= chunk_size_bytes:
        return [file_path]

    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return await _binary_split(file_path, chunk_size_bytes)

    ext = os.path.splitext(file_path)[1]
    base = os.path.splitext(file_path)[0]

    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe") if "ffmpeg" in ffmpeg else "ffprobe"
    probe_proc = await asyncio.create_subprocess_exec(
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    probe_stdout, _ = await probe_proc.communicate()
    probe_output = probe_stdout.decode().strip()

    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}
    audio_exts = {".mp3", ".m4a", ".ogg", ".flac", ".wav"}

    if ext.lower() in video_exts or ext.lower() in audio_exts:
        try:
            duration = float(probe_output)
            n_parts = -(-size // chunk_size_bytes)  # ceiling division
            seg_duration = duration / n_parts

            output_pattern = f"{base}_part%03d{ext}"
            cmd = [
                ffmpeg, "-i", file_path,
                "-c", "copy",
                "-f", "segment",
                "-segment_time", str(int(seg_duration)),
                "-reset_timestamps", "1",
                output_pattern, "-y"
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()

            dir_path = os.path.dirname(file_path) or "."
            parts = sorted([
                os.path.join(dir_path, f)
                for f in os.listdir(dir_path)
                if f.startswith(os.path.basename(base) + "_part") and f.endswith(ext)
            ])
            if parts:
                return parts
        except Exception:
            pass

    return await _binary_split(file_path, chunk_size_bytes)


async def _binary_split(file_path: str, chunk_size: int) -> list:
    """ffmpeg yo'q bo'lsa oddiy binary split."""
    parts = []
    base, ext = os.path.splitext(file_path)
    i = 0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            part_path = f"{base}_part{i:03d}{ext}"
            with open(part_path, "wb") as pf:
                pf.write(chunk)
            parts.append(part_path)
            i += 1
    return parts


async def make_thumbnail(file_path: str):
    """
    Video uchun 1-soniya kadridan thumbnail yaratadi.
    Rasm uchun o'zini qaytaradi.
    Muvaffaqiyatsiz bo'lsa None qaytaradi.
    """
    ext = os.path.splitext(file_path)[1].lower()
    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}

    if ext in image_exts:
        return file_path

    if ext not in video_exts:
        return None

    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return None

    thumb_path = os.path.splitext(file_path)[0] + "_thumb.jpg"
    cmd = [
        ffmpeg, "-ss", "00:00:01",
        "-i", file_path,
        "-vframes", "1",
        "-q:v", "2",
        thumb_path, "-y"
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()

    if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
        return thumb_path
    return None


async def get_video_metadata(file_path: str) -> dict:
    """
    FFprobe orqali video fayldan duration, width, height oladi.
    Qaytaradi: {"duration": int, "width": int, "height": int}
    FFprobe topilmasa yoki xato bo'lsa bo'sh dict qaytaradi.
    """
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return {}

    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe") if "ffmpeg" in ffmpeg else "ffprobe"

    try:
        proc = await asyncio.create_subprocess_exec(
            ffprobe,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-show_entries", "format=duration",
            "-of", "json",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return {}

        import json as _json
        data = _json.loads(stdout.decode())

        width = 0
        height = 0
        duration = 0.0

        # Stream dan olish
        streams = data.get("streams", [])
        if streams:
            s = streams[0]
            width = int(s.get("width", 0) or 0)
            height = int(s.get("height", 0) or 0)
            # Ba'zi formatlarda stream.duration bo'ladi
            if s.get("duration"):
                try:
                    duration = float(s["duration"])
                except (ValueError, TypeError):
                    pass

        # Format dan duration olish (aniqroq)
        fmt = data.get("format", {})
        if fmt.get("duration"):
            try:
                duration = float(fmt["duration"])
            except (ValueError, TypeError):
                pass

        return {
            "duration": int(duration),
            "width": width,
            "height": height,
        }
    except Exception as e:
        logger.debug(f"get_video_metadata xato: {e}")
        return {}


async def write_buffer_to_disk(bio: io.BytesIO, path: str) -> None:
    """BytesIO ni diskka async yozadi (bloklovchi open() o'rniga)."""
    async with aiofiles.open(path, "wb") as f:
        await f.write(bio.getvalue())


async def upload_via_user_session(
    bot,
    user_id: int,
    file_path,                      # str | io.BytesIO
    caption: str = "",
    progress_msg=None,
    target_chat=None,
    msg_type: str = "Document",
    extra: dict = None,
    file_size: int = 0,             # RAM release uchun
    use_ram: bool = False,          # RAM buffer bo'ldimi?
    existing_client=None,           # Tayyor ulanish (acc) — yangi session yaratmaydi
):
    """
    Faylni user session orqali target_chat ga yuboradi.
    target_chat = bot.id bo'lsa, user va bot orasidagi chatga yuboriladi.
    Bot API emas — userbot client (uclient) ishlatiladi.
    FloodWait avtomatik boshqariladi.
    file_path str yoki io.BytesIO bo'lishi mumkin.
    existing_client berilsa — yangi ulanish yaratmaydi, shu clientni ishlatadi
    va disconnect QILMAYDI (tashqi kod javobgar).
    """
    from database.db import database as _db
    from config import API_ID, API_HASH

    if extra is None:
        extra = {}

    # Absolute path va mavjudlik tekshiruvi — faqat str uchun
    if isinstance(file_path, str):
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            await safe_send_message(bot, user_id, f"**Upload xatosi:** fayl topilmadi: `{file_path}`")
            return False
        # TUZATISH: DOCUMENT_INVALID — bo'sh fayl yuborilsa 400 xato chiqadi
        if os.path.getsize(file_path) == 0:
            logger.warning(f"User {user_id}: upload skipped — file is empty: {file_path}")
            await safe_send_message(bot, user_id, "**Upload xatosi:** fayl bo'sh (0 bayt).")
            return False
    # io.BytesIO uchun tekshiruv
    elif isinstance(file_path, io.BytesIO):
        # TUZATISH: DOCUMENT_INVALID — bo'sh BytesIO yuborilsa 400 xato chiqadi
        if file_path.getbuffer().nbytes == 0:
            logger.warning(f"User {user_id}: upload skipped — BytesIO is empty")
            await safe_send_message(bot, user_id, "**Upload xatosi:** fayl bo'sh (0 bayt).")
            return False
        file_path.seek(0)  # Pozitsiyani boshiga qaytarish

    # Target chat: bot bilan private chat yoki fallback user_id
    chat_id = target_chat or user_id

    # Thumbnail faqat document/video uchun, faqat str path uchun (BytesIO emas)
    thumb = None
    if msg_type in ("Document", "Video", "Audio") and isinstance(file_path, str):
        thumb = extra.get("thumb") or await make_thumbnail(file_path)

    # ── existing_client bo'lsa — yangi session yaratmaymiz ──
    own_client = existing_client is None  # Biz yaratgan client mi?

    if existing_client:
        uclient = existing_client
    else:
        user_data = _db.find_one({"chat_id": user_id})
        if not user_data or not user_data.get("session"):
            await safe_send_message(bot, user_id, "**Avval /login yoki /qrlogin qiling.**")
            return False
        session_string = user_data["session"]
        uclient = Client(
            f"user_{user_id}",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_string,
            in_memory=True,
            no_updates=True,
            sleep_threshold=60,
            max_concurrent_transmissions=1,
        )

    success = True

    try:
        try:
            if own_client:
                await uclient.connect()
                # self.me ni to'ldirish — save_file.py ichida is_premium tekshiriladi
                uclient.me = await uclient.get_me()
                # TUZATISH: PEER_ID_INVALID — bot peer'ini uclient keshiga yuklash
                # Bir necha usulda urinib ko'ramiz
                await _resolve_bot_peer(uclient, chat_id)
            else:
                # existing_client da me bo'lmasa to'ldiramiz
                # Avval ulanishni tekshiramiz
                if not uclient.is_connected:
                    logger.warning("existing_client disconnected — reconnecting...")
                    await uclient.connect()
                if not getattr(uclient, 'me', None):
                    uclient.me = await uclient.get_me()
                    # TUZATISH: PEER_ID_INVALID — bot peer resolve faqat me yangi olinganda
                    await _resolve_bot_peer(uclient, chat_id)
            # ── Premium check → split qaror ──
            is_premium = getattr(uclient.me, 'is_premium', False)
            # BytesIO uchun getsize ishlamaydi — tashqaridan kelgan file_size ishlatiladi
            if isinstance(file_path, str):
                upload_file_size = os.path.getsize(file_path)
            else:
                upload_file_size = file_size  # BytesIO: tashqaridan uzatilgan qiymat

            if isinstance(file_path, io.BytesIO):
                # BytesIO split qilinmaydi — har doim <300MB bo'ladi
                parts = [file_path]
            elif is_premium and upload_file_size < FOUR_GB:
                parts = [file_path]
            elif is_premium and upload_file_size >= FOUR_GB:
                parts = await split_file(file_path, TWO_GB)
            else:
                parts = await split_file(file_path, TWO_GB)

            parts_to_cleanup = [p for p in parts if isinstance(p, str) and p != file_path]
        except Exception as conn_err:
            await safe_send_message(bot, user_id, f"**Ulanish xatosi:** `{conn_err}`")
            return False

        # ── Helper: bitta partni yuborish (DRY) + Flood Protection ──
        async def _do_send_part(part_path, part_caption, part_idx, total_parts):
            """Bitta part ni uclient orqali yuboradi. True/False qaytaradi."""

            # Upload progress uchun callback — RAMga yozadi
            def _up_progress(current, total):
                if progress_msg:
                    write_progress(f"{progress_msg.id}_up", current, total)

            # Exponential backoff: 10s, 20s, 40s, 60s, 120s
            RETRY_DELAYS = [10, 20, 40, 60, 120]
            MAX_UPLOAD_RETRIES = len(RETRY_DELAYS)

            for attempt in range(MAX_UPLOAD_RETRIES):
                try:
                    # Flood wait tekshiruvi
                    await flood_controller.wait_if_needed(user_id)

                    # Upload orasida connection tekshiruvi
                    if not uclient.is_connected:
                        logger.warning(f"User {user_id}: uclient disconnected before upload attempt {attempt+1}, reconnecting...")
                        try:
                            await uclient.connect()
                            uclient.me = await uclient.get_me()
                        except Exception as rc_err:
                            logger.error(f"User {user_id}: reconnect failed: {rc_err}")
                            if attempt < MAX_UPLOAD_RETRIES - 1:
                                await asyncio.sleep(RETRY_DELAYS[attempt])
                                continue
                            raise

                    # BytesIO qayta urinishda pointer oxirida qolib ketmasligi uchun
                    if isinstance(part_path, io.BytesIO):
                        part_path.seek(0)

                    if msg_type == "Video":
                        await uclient.send_video(
                            chat_id=chat_id, video=part_path,
                            caption=part_caption,
                            duration=extra.get("duration") or 0,
                            width=extra.get("width") or 0,
                            height=extra.get("height") or 0, thumb=thumb,
                            supports_streaming=True,
                            progress=_up_progress,
                        )
                    elif msg_type == "Audio":
                        await uclient.send_audio(
                            chat_id=chat_id, audio=part_path,
                            caption=part_caption,
                            duration=extra.get("duration") or 0,
                            performer=extra.get("performer"),
                            title=extra.get("title"), thumb=thumb,
                            progress=_up_progress,
                        )
                    elif msg_type == "Voice":
                        await uclient.send_voice(
                            chat_id=chat_id, voice=part_path,
                            caption=part_caption,
                            duration=extra.get("duration") or 0,
                            progress=_up_progress,
                        )
                    elif msg_type == "Photo":
                        await uclient.send_photo(
                            chat_id=chat_id, photo=part_path,
                            caption=part_caption,
                            progress=_up_progress,
                        )
                    elif msg_type == "Animation":
                        await uclient.send_animation(
                            chat_id=chat_id, animation=part_path,
                            caption=part_caption,
                            progress=_up_progress,
                        )
                    elif msg_type == "VideoNote":
                        await uclient.send_video_note(
                            chat_id=chat_id, video_note=part_path,
                            duration=extra.get("duration") or 0,
                            length=extra.get("length") or 0,
                            progress=_up_progress,
                        )
                    elif msg_type == "Sticker":
                        await uclient.send_sticker(
                            chat_id=chat_id, sticker=part_path,
                            progress=_up_progress,
                        )
                    else:
                        # TUZATISH: DOCUMENT_INVALID — force_document=True bo'lishi kerak
                        await uclient.send_document(
                            chat_id=chat_id, document=part_path,
                            caption=part_caption, thumb=thumb,
                            force_document=True,
                            progress=_up_progress,
                        )
                    return True
                except FloodWait as e:
                    wait = e.value
                    # Flood controller'ga xabar berish
                    await flood_controller.handle_flood_wait(user_id, wait)

                    if progress_msg:
                        try:
                            if total_parts > 1:
                                await progress_msg.edit(
                                    f"⏳ **Part {part_idx+1}/{total_parts}** — FloodWait: {wait}s kutilmoqda..."
                                )
                            else:
                                await progress_msg.edit(
                                    f"⏳ **FloodWait:** {wait} soniya kutilmoqda..."
                                )
                        except Exception:
                            pass
                    await asyncio.sleep(wait)
                except (ConnectionError, OSError, TimeoutError) as send_err:
                    # TCP/Network xatolar — exponential backoff bilan retry
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"User {user_id}: Upload attempt {attempt+1}/{MAX_UPLOAD_RETRIES} failed: "
                        f"{type(send_err).__name__}: {send_err}. Retrying in {delay}s..."
                    )
                    if progress_msg:
                        try:
                            await progress_msg.edit(
                                f"⚠️ **Upload xatosi** (urinish {attempt+1}/{MAX_UPLOAD_RETRIES}): "
                                f"`{type(send_err).__name__}`\n"
                                f"⏳ {delay}s dan keyin qayta uriniladi..."
                            )
                        except Exception:
                            pass

                    if attempt < MAX_UPLOAD_RETRIES - 1:
                        await asyncio.sleep(delay)
                        # Reconnect attempt
                        try:
                            if not uclient.is_connected:
                                await uclient.connect()
                                uclient.me = await uclient.get_me()
                                logger.info(f"User {user_id}: reconnected after upload error")
                        except Exception as rc_err:
                            logger.error(f"User {user_id}: reconnect after upload error failed: {rc_err}")
                        continue
                    # Max urinishlar tugadi
                    logger.error(f"User {user_id}: Upload failed after {MAX_UPLOAD_RETRIES} attempts")
                    await safe_send_message(
                        bot, user_id,
                        f"❌ **Upload muvaffaqiyatsiz** ({MAX_UPLOAD_RETRIES} urinishdan keyin).\n"
                        f"Xato: `{type(send_err).__name__}: {send_err}`"
                    )
                    raise
                except RuntimeError as send_err:
                    # "unable to perform operation on <TCPTransport closed=True>"
                    error_str = str(send_err).lower()
                    if "closed" in error_str or "transport" in error_str:
                        delay = RETRY_DELAYS[attempt]
                        logger.warning(
                            f"User {user_id}: TCPTransport closed, attempt {attempt+1}/{MAX_UPLOAD_RETRIES}. "
                            f"Retrying in {delay}s..."
                        )
                        if progress_msg:
                            try:
                                await progress_msg.edit(
                                    f"⚠️ **Ulanish uzildi** (urinish {attempt+1}/{MAX_UPLOAD_RETRIES})\n"
                                    f"⏳ {delay}s dan keyin qayta ulaniladi..."
                                )
                            except Exception:
                                pass
                        if attempt < MAX_UPLOAD_RETRIES - 1:
                            await asyncio.sleep(delay)
                            try:
                                await uclient.connect()
                                uclient.me = await uclient.get_me()
                                logger.info(f"User {user_id}: reconnected after TCPTransport close")
                            except Exception as rc_err:
                                logger.error(f"User {user_id}: reconnect failed: {rc_err}")
                            continue
                        logger.error(f"User {user_id}: Upload failed — TCPTransport repeatedly closed")
                        await safe_send_message(
                            bot, user_id,
                            f"❌ **Upload muvaffaqiyatsiz** — ulanish barqaror emas.\n"
                            f"Iltimos biroz kutib qayta urinib ko'ring."
                        )
                        raise
                    else:
                        raise
                except Exception as send_err:
                    err_str = str(send_err).lower()
                    # TUZATISH: FILE_PART_INVALID — upload media session buzilgan bo'lishi mumkin
                    if "file_part_invalid" in err_str:
                        logger.warning(
                            f"User {user_id}: FILE_PART_INVALID on upload (attempt {attempt+1}/{MAX_UPLOAD_RETRIES})"
                        )
                        if attempt < MAX_UPLOAD_RETRIES - 1:
                            try:
                                if uclient.is_connected:
                                    await uclient.disconnect()
                            except Exception:
                                pass
                            try:
                                await asyncio.sleep(1)
                                await uclient.connect()
                                uclient.me = await uclient.get_me()
                                await _resolve_bot_peer(uclient, chat_id)
                            except Exception as rc_err:
                                logger.error(f"User {user_id}: reconnect after FILE_PART_INVALID failed: {rc_err}")
                            await asyncio.sleep(RETRY_DELAYS[attempt])
                            continue
                        await safe_send_message(
                            bot, user_id,
                            "❌ **Upload xatosi:** `FILE_PART_INVALID`.\n"
                            "Iltimos qayta urinib ko'ring."
                        )
                        raise

                    # TUZATISH: PEER_ID_INVALID — bot peer keshdan tushib ketgan
                    if "peer_id_invalid" in err_str or "peer id" in err_str:
                        logger.warning(f"User {user_id}: PEER_ID_INVALID — re-resolving bot peer (attempt {attempt+1})")
                        if attempt < MAX_UPLOAD_RETRIES - 1:
                            # Bot peer'ni qayta resolve qilish
                            await _resolve_bot_peer(uclient, chat_id)
                            await asyncio.sleep(RETRY_DELAYS[attempt])
                            continue
                        await safe_send_message(
                            bot, user_id,
                            "❌ **Upload xatosi:** Bot peer topilmadi.\n"
                            "Iltimos botga /start yuboring va qayta urinib ko'ring."
                        )
                        raise
                    # TUZATISH: DOCUMENT_INVALID — fayl noto'g'ri
                    if "document_invalid" in err_str:
                        logger.error(f"User {user_id}: DOCUMENT_INVALID for {msg_type}")
                        await safe_send_message(
                            bot, user_id,
                            f"❌ **Upload xatosi:** Fayl noto'g'ri formatda (`DOCUMENT_INVALID`).\n"
                            f"Fayl buzilgan yoki bo'sh bo'lishi mumkin."
                        )
                        raise
                    logger.error(f"[UPLOAD] unexpected error attempt={attempt}: {type(send_err).__name__}: {send_err}")
                    import traceback
                    traceback.print_exc()
                    raise
            return False

        # ── Helper: barcha partlarni yuborish (DRY) ──
        async def _upload_parts(parts_list):
            """parts_list dagi har bir partni upload qiladi. (ok, err) qaytaradi."""
            for idx, p_path in enumerate(parts_list):
                p_caption = caption
                if len(parts_list) > 1:
                    p_caption = f"{caption}\n**Part {idx+1}/{len(parts_list)}**"

                if len(parts_list) > 1 and progress_msg:
                    try:
                        await progress_msg.edit(f"📤 **Part {idx+1}/{len(parts_list)}** yuklanmoqda...")
                    except Exception:
                        pass

                uploaded = False
                try:
                    uploaded = await _do_send_part(p_path, p_caption, idx, len(parts_list))
                except Exception as err:
                    return False, err
                if not uploaded:
                    return False, None
                # Minimal delay between parts to prevent flood
                if idx < len(parts_list) - 1:
                    await asyncio.sleep(2)
            return True, None

        # ── Primary upload ──
        ok, err = await _upload_parts(parts)

        if not ok and err is not None:
            # Exception bo'ldi
            if is_premium and file_size > TWO_GB and len(parts) == 1:
                # Premium fallback: split qilib qayta urinish
                if progress_msg:
                    try:
                        await progress_msg.edit(
                            "⚠️ **Splitiz upload muvaffaqiyatsiz. Split bilan qayta urinilmoqda...**"
                        )
                    except Exception:
                        pass
                parts = await split_file(file_path, TWO_GB)
                parts_to_cleanup = [p for p in parts if isinstance(p, str) and p != file_path]
                ok, err = await _upload_parts(parts)
                if not ok:
                    if err is not None:
                        await safe_send_message(bot, user_id, f"**Upload xatosi:** `{err}`")
                    else:
                        await safe_send_message(bot, user_id, "**Upload: FloodWait — maksimal urinishlar tugadi.**")
                    success = False
            else:
                await safe_send_message(bot, user_id, f"**Upload xatosi:** `{err}`")
                success = False
        elif not ok:
            # FloodWait tugadi (exception yo'q)
            await safe_send_message(bot, user_id, "**Upload: FloodWait — maksimal urinishlar tugadi.**")
            success = False

        # ── Multi-part muvaffaqiyat xabari ──
        if success and len(parts) > 1 and progress_msg:
            try:
                await progress_msg.edit(f"✅ **{len(parts)} ta part muvaffaqiyatli yuklandi!**")
            except Exception:
                pass

        # Split qilingan temp fayllarni tozalash
        for part_path in parts_to_cleanup:
            try:
                os.remove(part_path)
            except Exception:
                pass

    finally:
        # Faqat o'zimiz yaratgan clientni disconnect qilamiz
        # existing_client berilgan bo'lsa — disconnect tashqi kodda (process_posts finally)
        if own_client:
            try:
                await uclient.disconnect()
            except Exception:
                pass
        # RAM yoki disk tozalash
        if use_ram and file_size > 0:
            await buffer_mgr.release(file_size)
        # Thumbnail tozalash
        if thumb and not extra.get("thumb") and isinstance(thumb, str) and os.path.exists(thumb):
            try:
                os.remove(thumb)
            except Exception:
                pass

    return success


# Dictionary to track active user tasks
user_tasks = {}

# Maximum retries for connection issues
MAX_RETRIES = 3
RETRY_DELAY = 2

def get(obj, key, default=None):
    try:
        return obj[key]
    except:
        return default

# Helper function to sanitize HTML content and fix unclosed tags
def sanitize_html(content):
    """
    Fixes common HTML issues like unclosed tags.
    """
    if not content:
        return content
        
    # Common HTML tags we need to check
    tags = ['b', 'i', 'u', 'a', 'code', 'pre']
    
    # Simple regex-based approach to check for unclosed tags
    for tag in tags:
        # Count opening and closing tags
        open_tags = len(re.findall(f'<{tag}[^>]*>', content))
        close_tags = len(re.findall(f'</{tag}>', content))
        
        # Add closing tags as needed
        if open_tags > close_tags:
            content += f'</{tag}>' * (open_tags - close_tags)
            
    return content

# Helper function to sanitize Markdown content and fix common issues
def sanitize_markdown(content):
    """
    Fixes common Markdown issues that might cause parsing problems.
    """
    if not content:
        return content
    
    # Fix for unclosed brackets in URLs
    # Look for [text]( without closing )
    pattern = r'\[([^\]]+)\]\(([^)]*[^)])'
    matches = re.findall(pattern, content)
    
    # Fix each broken link
    for text, url in matches:
        old = f'[{text}]({url}'
        new = f'[{text}]({url})'
        content = content.replace(old, new)
    
    # Fix for incorrect escaping in URLs
    # Common issues with backslashes in URLs
    content = re.sub(r'\\\(', '(', content)
    content = re.sub(r'\\\)', ')', content)
    
    # Ensure code blocks are properly formatted
    # Convert single ` to triple ``` if it spans multiple lines
    if '`' in content and '\n' in content:
        lines = content.split('\n')
        in_code_block = False
        for i in range(len(lines)):
            if lines[i].count('`') % 2 == 1:  # Odd number of backticks
                if not in_code_block:
                    lines[i] = lines[i].replace('`', '```', 1)
                    in_code_block = True
                else:
                    lines[i] = lines[i].replace('`', '```', 1)
                    in_code_block = False
        content = '\n'.join(lines)
    
    return content

# Helper function to manually convert text with entities to markdown with hyperlinks
def extract_hyperlinks(text, entities):
    """
    Manually extract and format hyperlinks from text with entities.
    This is a fallback method when other approaches fail.
    
    Enhanced version using MessageEntityType enum.
    """
    if not text or not entities:
        return text
    
    # Make a copy of the text to avoid modifying the original
    result = text
    
    # Track offsets as we modify the text
    offset_change = 0
    
    # Sort entities by offset for proper processing
    sorted_entities = sorted(entities, key=lambda x: x.offset)
    
    for entity in sorted_entities:
        if not hasattr(entity, 'type'):
            continue
        
        # Calculate positions accounting for previous changes
        start = entity.offset + offset_change
        end = start + entity.length
        
        if start < 0 or end > len(result):
            continue  # Skip invalid positions
        
        # Extract the link text
        entity_text = result[start:end]
        formatted_text = entity_text  # Default to no change
        
        # Format based on entity type using MessageEntityType enum
        if entity.type == MessageEntityType.TEXT_LINK and hasattr(entity, 'url'):
            # Create markdown link
            formatted_text = f'[{entity_text}]({entity.url})'
            
        elif entity.type == MessageEntityType.BOLD:
            formatted_text = f'**{entity_text}**'
            
        elif entity.type == MessageEntityType.ITALIC:
            formatted_text = f'*{entity_text}*'
            
        elif entity.type == MessageEntityType.CODE:
            formatted_text = f'`{entity_text}`'
            
        elif entity.type == MessageEntityType.PRE:
            if hasattr(entity, 'language') and entity.language:
                formatted_text = f'```{entity.language}\n{entity_text}\n```'
            else:
                formatted_text = f'```\n{entity_text}\n```'
            
        elif entity.type == MessageEntityType.UNDERLINE:
            # Markdown doesn't have underline, so we skip it
            pass
            
        elif entity.type == MessageEntityType.STRIKETHROUGH:
            formatted_text = f'~~{entity_text}~~'
        
        # Apply the formatting change if there was one
        if formatted_text != entity_text:
            # Replace in the result
            result = result[:start] + formatted_text + result[end:]
            
            # Update offset change for future entities
            offset_change += len(formatted_text) - entity.length
    
    return result

# Helper function to get user status information
async def get_user_status_info(client, user_id):
    """
    Get a user's online status and return a formatted string using Raw API
    
    Parameters:
        client (Client): Pyrogram client instance
        user_id (int): Telegram user ID or username to check
        
    Returns:
        str: A string describing the user's status
    """
    try:
        # First try to get user information to resolve the user ID/username
        user = await client.get_users(user_id)
        
        if not user:
            return "User not found"
        
        # Convert user_id to InputPeer for raw API calls
        peer = await client.resolve_peer(user.id)
        
        # Use raw API to get more detailed user status
        try:
            users = await client.send(
                functions.users.GetUsers(
                    id=[peer]
                )
            )
            
            if not users or len(users) == 0:
                return "User not found"
                
            raw_user = users[0]
            status_text = "Unknown"
            
            # Get more detailed status information
            if hasattr(raw_user, "status"):
                if isinstance(raw_user.status, types.UserStatusOnline):
                    status_text = "Online"
                    if hasattr(raw_user.status, "expires"):
                        # Calculate when online status expires
                        expires_in = raw_user.status.expires - int(time.time())
                        if expires_in > 0:
                            status_text = f"Online (for {expires_in // 60} more minutes)"
                
                elif isinstance(raw_user.status, types.UserStatusOffline):
                    # Get precise last seen time
                    if hasattr(raw_user.status, "was_online"):
                        last_seen = raw_user.status.was_online
                        last_seen_delta = int(time.time()) - last_seen
                        
                        if last_seen_delta < 60:
                            status_text = "last seen just now"
                        elif last_seen_delta < 3600:
                            minutes = int(last_seen_delta // 60)
                            status_text = f"last seen {minutes} minute{'s' if minutes > 1 else ''} ago"
                        elif last_seen_delta < 86400:
                            hours = int(last_seen_delta // 3600)
                            status_text = f"last seen {hours} hour{'s' if hours > 1 else ''} ago"
                        else:
                            # Format actual date and time
                            from datetime import datetime
                            date_str = datetime.fromtimestamp(last_seen).strftime("%Y-%m-%d %H:%M:%S")
                            days = int(last_seen_delta // 86400)
                            status_text = f"last seen on {date_str} ({days} day{'s' if days > 1 else ''} ago)"
                    else:
                        status_text = "Offline"
                
                elif isinstance(raw_user.status, types.UserStatusRecently):
                    status_text = "last seen recently"
                
                elif isinstance(raw_user.status, types.UserStatusLastWeek):
                    status_text = "last seen within a week"
                
                elif isinstance(raw_user.status, types.UserStatusLastMonth):
                    status_text = "last seen within a month"
                
                else:
                    status_text = "last seen a long time ago"
            
            # Get additional user information
            user_info = f"**{user.first_name}**"
            if user.last_name:
                user_info += f" {user.last_name}"
            if user.username:
                user_info += f" (@{user.username})"
            
            user_info += f" - `{user.id}`"
            
            # Add premium status if available
            if hasattr(raw_user, "premium") and raw_user.premium:
                user_info += " - Premium User ⭐"
                
            # Add verification status if available
            if hasattr(raw_user, "verified") and raw_user.verified:
                user_info += " - Verified ✓"
                
            # Add bot status if applicable
            if user.is_bot:
                user_info += " - Bot 🤖"
                
            # Add status
            result = f"{user_info}\n\n**Status:** {status_text}"
            
            # Try to get common chats information
            try:
                common_chats = await client.send(
                    functions.messages.GetCommonChats(
                        user_id=peer,
                        max_id=0,
                        limit=100
                    )
                )
                
                if hasattr(common_chats, "chats") and common_chats.chats:
                    common_count = len(common_chats.chats)
                    result += f"\n\n**Common Chats:** {common_count}"
                    
                    # List some common chats
                    if common_count > 0:
                        result += "\n"
                        max_chats_to_show = min(5, common_count)
                        for i in range(max_chats_to_show):
                            chat = common_chats.chats[i]
                            chat_name = chat.title if hasattr(chat, "title") else "Private Group"
                            result += f"- {chat_name}\n"
                            
                        if common_count > max_chats_to_show:
                            result += f"- ...and {common_count - max_chats_to_show} more"
            except Exception:
                # Common chats might not be accessible
                pass
                
            return result
        
        except Exception as raw_err:
            # Fall back to high-level API if raw API fails
            pass
            
        # Fallback to high-level API
        status_text = "Unknown"
        
        if user.status:
            if user.status == UserStatus.ONLINE:
                status_text = "Online"
            elif user.status == UserStatus.OFFLINE:
                # Calculate time since last seen if available
                if user.last_online_date:
                    last_seen_delta = time.time() - user.last_online_date
                    if last_seen_delta < 60:
                        status_text = "last seen just now"
                    elif last_seen_delta < 3600:
                        minutes = int(last_seen_delta // 60)
                        status_text = f"last seen {minutes} minute{'s' if minutes > 1 else ''} ago"
                    elif last_seen_delta < 86400:
                        hours = int(last_seen_delta // 3600)
                        status_text = f"last seen {hours} hour{'s' if hours > 1 else ''} ago"
                    else:
                        days = int(last_seen_delta // 86400)
                        status_text = f"last seen {days} day{'s' if days > 1 else ''} ago"
                else:
                    status_text = "Offline"
            elif user.status == UserStatus.RECENTLY:
                status_text = "last seen recently"
            elif user.status == UserStatus.LAST_WEEK:
                status_text = "last seen within a week"
            elif user.status == UserStatus.LAST_MONTH:
                status_text = "last seen within a month"
            elif user.status == UserStatus.LONG_AGO:
                status_text = "last seen a long time ago"
        
        return f"{user.first_name} is {status_text}"
    except Exception as e:
        return f"Error checking user status: {str(e)}"

# Helper function to create and connect client with retry logic
async def ensure_connected(client):
    """acc (user session) transport yopilgan bo'lsa qayta ulanadi.
    Agar ulanish imkoni bo'lmasa False qaytaradi."""
    MAX_RECONNECT_ATTEMPTS = 3

    for reconnect_attempt in range(MAX_RECONNECT_ATTEMPTS):
        try:
            # 1) Pyrofork `is_connected` flagi (connect/disconnect da o'zgaradi)
            if client.is_connected is False or client.is_connected is None:
                logger.warning(f"User session disconnected (is_connected=False) — reconnecting (attempt {reconnect_attempt+1})...")
                await client.connect()
                if not getattr(client, 'me', None):
                    client.me = await client.get_me()
                logger.info("User session reconnected successfully")
                return True

            # 2) Transport yopilgan bo'lishi mumkin (TCPTransport closed=True)
            #    is_connected hali True bo'lib qolgan, lekin session.connection yopilgan
            session = getattr(client, 'session', None)
            if session:
                conn = getattr(session, 'connection', None)
                if conn:
                    transport = getattr(conn, 'transport', None)
                    if transport and getattr(transport, '_closed', False):
                        logger.warning(f"User session transport closed — reconnecting (attempt {reconnect_attempt+1})...")
                        # Avval eski sessionni to'xtatamiz
                        try:
                            client.is_connected = False
                            await session.stop()
                        except Exception:
                            pass
                        await client.connect()
                        if not getattr(client, 'me', None):
                            client.me = await client.get_me()
                        logger.info("User session reconnected after transport close")
                        return True

            # 3) Ping-test: get_me() bilan haqiqiy ulanishni tekshirish
            try:
                await client.get_me()
            except Exception as ping_err:
                error_str = str(ping_err).lower()
                if any(kw in error_str for kw in ["closed", "transport", "timeout", "connection", "reset"]):
                    logger.warning(f"Ping test failed: {ping_err} — reconnecting (attempt {reconnect_attempt+1})...")
                    try:
                        client.is_connected = False
                        await client.disconnect()
                    except Exception:
                        pass
                    await asyncio.sleep(2 * (reconnect_attempt + 1))
                    await client.connect()
                    if not getattr(client, 'me', None):
                        client.me = await client.get_me()
                    logger.info("User session reconnected after ping failure")
                    return True
                else:
                    # get_me boshqa xato (masalan FloodWait) — ulanish bor deb hisoblaymiz
                    pass

            return True
        except Exception as e:
            logger.error(f"Reconnect attempt {reconnect_attempt+1} failed: {type(e).__name__}: {e}")
            if reconnect_attempt < MAX_RECONNECT_ATTEMPTS - 1:
                await asyncio.sleep(3 * (reconnect_attempt + 1))
                continue
            return False

    return False


async def resolve_channel_peer(client, chat_id):
    """Production-grade kanal peer resolver.

    TUZATISH: CHANNEL_INVALID — to'g'ri access_hash bilan resolve qiladi.

    Qoidalar:
    - HECH QACHON access_hash=0 ishlatilmaydi
    - Har doim client.get_chat yoki resolve_peer orqali haqiqiy access_hash olinadi
    - Kesh mavjud — takroriy so'rovlar serverga borilmaydi
    - Exponential backoff bilan retry (3 urinish)
    - FloodWait aniq handle qilinadi
    - Public (@username) va private (t.me/c/...) linklar qo'llab-quvvatlanadi
    - User a'zo bo'lmasa graceful fail

    chat_id: int (-100...) yoki str (username).
    Muvaffaqiyatli bo'lsa True, aks holda False qaytaradi.
    """
    global _resolved_peers_cache

    # ── Kesh tekshiruvi — agar avval resolve qilingan bo'lsa, qayta so'rov kerak emas ──
    cache_key = str(chat_id)
    if cache_key in _resolved_peers_cache:
        # Keshda bor, lekin peer hali ham validmi tekshiramiz (resolve_peer kesh ichida)
        try:
            await client.resolve_peer(chat_id)
            return True
        except Exception:
            # Kesh eskirgan — o'chirib, qayta resolve qilamiz
            _resolved_peers_cache.pop(cache_key, None)
            logger.debug(f"Cached peer for {chat_id} is stale, re-resolving...")

    RESOLVE_MAX_RETRIES = 3
    RESOLVE_BASE_DELAY = 2  # sekundda

    for attempt in range(RESOLVE_MAX_RETRIES):
        try:
            # ── 1-usul: resolve_peer — ichki peer keshidan (eng tez) ──
            try:
                peer = await client.resolve_peer(chat_id)
                if peer:
                    _resolved_peers_cache[cache_key] = True
                    logger.debug(f"Channel {chat_id} resolved via resolve_peer (attempt {attempt+1})")
                    return True
            except (ChannelInvalid, ChannelPrivate, KeyError, ValueError):
                pass
            except FloodWait as fw:
                wait = fw.value
                logger.warning(f"FloodWait {wait}s during resolve_peer({chat_id})")
                await asyncio.sleep(wait)
                continue
            except Exception:
                pass

            # ── 2-usul: get_chat — serverdan to'liq ma'lumot + access_hash ──
            try:
                chat = await client.get_chat(chat_id)
                if chat:
                    _resolved_peers_cache[cache_key] = True
                    logger.info(f"Channel {chat_id} resolved via get_chat (attempt {attempt+1})")
                    return True
            except (ChannelInvalid, ChannelPrivate):
                # User a'zo emas yoki kanal private — get_dialogs bilan urinib ko'ramiz
                pass
            except FloodWait as fw:
                wait = fw.value
                logger.warning(f"FloodWait {wait}s during get_chat({chat_id})")
                await asyncio.sleep(wait)
                continue
            except Exception as e:
                logger.debug(f"get_chat({chat_id}) failed: {type(e).__name__}: {e}")

            # ── 3-usul: get_dialogs — barcha dialoglar orasidan qidirish ──
            # Bu eng sekin usul, lekin eng ishonchli
            # Faqat int chat_id uchun (username uchun get_chat ishlashi kerak)
            try:
                logger.info(f"Resolving channel {chat_id} via get_dialogs scan (attempt {attempt+1})...")
                target_id = chat_id
                found = False
                async for dialog in client.get_dialogs():
                    if dialog.chat and dialog.chat.id == target_id:
                        found = True
                        break
                if found:
                    _resolved_peers_cache[cache_key] = True
                    logger.info(f"Channel {chat_id} found via get_dialogs")
                    # Endi resolve_peer ishlashi kerak (peer keshga tushdi)
                    return True
            except FloodWait as fw:
                wait = fw.value
                logger.warning(f"FloodWait {wait}s during get_dialogs for {chat_id}")
                await asyncio.sleep(wait)
                continue
            except Exception as e:
                logger.debug(f"get_dialogs scan for {chat_id} failed: {e}")

            # Barcha usullar muvaffaqiyatsiz — retry bilan
            if attempt < RESOLVE_MAX_RETRIES - 1:
                delay = RESOLVE_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"Channel {chat_id} resolve failed (attempt {attempt+1}/{RESOLVE_MAX_RETRIES}). "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.warning(f"Channel {chat_id} could not be resolved after {RESOLVE_MAX_RETRIES} attempts")

        except FloodWait as fw:
            # Tashqi FloodWait
            wait = fw.value
            logger.warning(f"FloodWait {wait}s at resolve attempt {attempt+1}")
            await asyncio.sleep(wait)
        except Exception as outer_err:
            logger.error(f"Unexpected error resolving {chat_id} (attempt {attempt+1}): {outer_err}")
            if attempt < RESOLVE_MAX_RETRIES - 1:
                await asyncio.sleep(RESOLVE_BASE_DELAY * (2 ** attempt))

    return False


async def create_client_session(session_string, client_name="saverestricted"):
    client = None
    # Bir xil session nomi bilan parallel clientlar to'qnashmasligi uchun
    if not client_name:
        client_name = "saverestricted"
    unique_client_name = f"{client_name}_{int(time.time() * 1000)}_{abs(hash(session_string)) % 10000}"
    for attempt in range(MAX_RETRIES):
        try:
            client = Client(
                unique_client_name,
                session_string=session_string,
                api_hash=API_HASH,
                api_id=API_ID,
                no_updates=True,
                in_memory=True,
                sleep_threshold=60,
                max_concurrent_transmissions=1,
                device_model="Telegram Desktop",
                system_version="Windows 10"
            )
            await client.connect()
            # me ni darhol to'ldirish — keyinchalik is_premium va boshqa tekshiruvlar uchun
            try:
                client.me = await client.get_me()
            except Exception:
                pass
            logger.info(f"Client session '{unique_client_name}' connected (attempt {attempt+1})")
            return client, None
        except Exception as e:
            if client:
                try:
                    await client.disconnect()
                except:
                    pass

            error_str = str(e).lower()
            # Auth xatolari — retry qilmaslik kerak
            if "auth_key" in error_str or "unregistered" in error_str:
                return None, f"Session yaroqsiz: {e}"

            # For connection errors, retry with backoff
            if any(kw in error_str for kw in ["connection", "network", "timeout", "reset", "closed", "transport"]):
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (2 ** attempt)  # exponential backoff
                    logger.warning(f"Client '{client_name}' connection failed (attempt {attempt+1}): {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue

            return None, f"Failed to establish connection: {str(e)}"

    return None, "Connection failed after multiple attempts"

# Helper function to safely disconnect client
async def safe_disconnect(client):
    if client:
        try:
            # First, disable updates to prevent new tasks from being created
            if hasattr(client, "no_updates"):
                client.no_updates = True
                
            # Cancel any pending downloads/uploads
            if hasattr(client, "_media_sessions"):
                for media_session in client._media_sessions.values():
                    if hasattr(media_session, "stop") and callable(media_session.stop):
                        media_session.stop()
            
            # Properly disconnect
            if hasattr(client, "disconnect") and callable(client.disconnect):
                await client.disconnect()
                
            # Wait a moment to allow disconnection to complete
            await asyncio.sleep(0.5)
        except Exception as e:
            # Just log the error and continue
            print(f"Error during client disconnection: {e}")
        finally:
            # Ensure we clear the reference
            client = None

async def downstatus(
    client: Client,
    msg_id: int,
    message: Message,
    stop_event: asyncio.Event,
) -> None:
    """Download progressini RAMdan o'qib xabarni yangilaydi (har 3 soniyada)."""
    key = f"{msg_id}_down"
    await asyncio.sleep(1)
    last_txt = ""
    while not stop_event.is_set():
        txt = read_progress(key)
        if txt != last_txt:
            try:
                await client.edit_message_text(
                    message.chat.id, message.id,
                    f"📥 **Yuklab olinmoqda...**\n`{txt}`"
                )
                last_txt = txt
            except Exception:
                pass
        await asyncio.sleep(3)
    clear_progress(key)


# upload status
async def upstatus(
    client: Client,
    msg_id: int,
    message: Message,
    stop_event: asyncio.Event,
) -> None:
    """Upload progressini RAMdan o'qib xabarni yangilaydi (har 3 soniyada)."""
    key = f"{msg_id}_up"
    await asyncio.sleep(1)
    last_txt = ""
    while not stop_event.is_set():
        txt = read_progress(key)
        if txt != last_txt:
            try:
                await client.edit_message_text(
                    message.chat.id, message.id,
                    f"📤 **Yuklanmoqda...**\n`{txt}`"
                )
                last_txt = txt
            except Exception:
                pass
        await asyncio.sleep(3)
    clear_progress(key)


# progress writer — RAMga yozadi (disk fayl yo'q)
def progress(current, total, key_or_msg, ptype):
    """Progress foizini RAMga yozadi (disk fayl yo'q).
    key_or_msg — int (msgid) yoki Message ob'ekti bo'lishi mumkin."""
    if isinstance(key_or_msg, int):
        key = f"{key_or_msg}_{ptype}"
    else:
        key = f"{key_or_msg.id}_{ptype}"
    write_progress(key, current, total)


# start command
@Client.on_message(filters.command(["start"]))
async def send_start(client: Client, message: Message):
    await client.send_message(message.chat.id, f"<b>👋 Hi {message.from_user.mention}, I am Save Restricted Content Bot, I can send you restricted content by its post link.\n\nFor downloading restricted content, send me the link of the post you want to save.</b>")
    return


# help command
@Client.on_message(filters.command(["help"]))
async def send_help(client: Client, message: Message):
    await client.send_message(message.chat.id, f"{HELP_TXT}")

# status command
@Client.on_message(filters.command(["status"]))
async def check_user_status(client: Client, message: Message):
    """Check the online status of a user by username or user ID"""
    # Check if user has provided a username or user ID
    if len(message.text.split()) < 2:
        await message.reply("Please provide a username or user ID to check their status.\n\nExample: `/status @username` or `/status 123456789`")
        return

    # Get the target user
    target = message.text.split(None, 1)[1].strip()
    
    # Get user session string
    user_data = database.find_one({'chat_id': message.chat.id})
    
    # Check if user is logged in
    if user_data is None or not user_data.get('logged_in', False) or not user_data.get('session'):
        await client.send_message(message.chat.id, strings['need_login'], reply_to_message_id=message.id)
        return
        
    session_string = user_data.get('session')
    
    # Create user client
    acc, err = await create_client_session(session_string, f"status_check_{message.chat.id}")
    if err:
        await client.send_message(message.chat.id, f"Failed to login: {err}", reply_to_message_id=message.id)
        return
        
    try:
        # Send "checking" message
        status_msg = await message.reply("Checking user status...")
        
        # Get the user status
        status_text = await get_user_status_info(acc, target)
        
        # Update the message with the status
        await status_msg.edit_text(status_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await message.reply(f"Error: {str(e)}")
    finally:
        # Always disconnect the client when done
        await safe_disconnect(acc)

# chatinfo command
@Client.on_message(filters.command(["chatinfo"]))
async def chat_info_command(client: Client, message: Message):
    """Get detailed information about a chat"""
    # Check if chat ID or username is provided
    if len(message.text.split()) < 2:
        # If no chat ID provided, use the current chat
        chat_id = message.chat.id
    else:
        # Get the chat ID or username
        chat_id = message.text.split(None, 1)[1].strip()
    
    # Get user session string
    user_data = database.find_one({'chat_id': message.chat.id})
    
    # Check if user is logged in
    if user_data is None or not user_data.get('logged_in', False) or not user_data.get('session'):
        await client.send_message(message.chat.id, strings['need_login'], reply_to_message_id=message.id)
        return
        
    session_string = user_data.get('session')
    
    # Create user client
    acc, err = await create_client_session(session_string, f"chat_info_{message.chat.id}")
    if err:
        await client.send_message(message.chat.id, f"Failed to login: {err}", reply_to_message_id=message.id)
        return
        
    try:
        # Send "checking" message
        info_msg = await message.reply("Fetching chat information...")
        
        # Get the chat information
        chat_info = await get_chat_info(acc, chat_id)
        
        if "error" in chat_info:
            await info_msg.edit_text(f"Error fetching chat info: {chat_info['error']}")
            return
            
        # Format chat information
        info_text = "**Chat Information**\n\n"
        info_text += f"**Type:** {chat_info['type']}\n"
        
        if chat_info['title']:
            info_text += f"**Title:** {chat_info['title']}\n"
            
        if chat_info['username']:
            info_text += f"**Username:** @{chat_info['username']}\n"
            
        info_text += f"**ID:** `{chat_info['id']}`\n"
        info_text += f"**Members:** {chat_info['members_count']}\n"
        
        # Add type-specific information
        if chat_info['type'] in [ChatType.PRIVATE, ChatType.BOT]:
            if chat_info.get('first_name'):
                info_text += f"**First Name:** {chat_info['first_name']}\n"
            if chat_info.get('last_name'):
                info_text += f"**Last Name:** {chat_info['last_name']}\n"
            if chat_info.get('status'):
                info_text += f"**Status:** {chat_info['status']}\n"
                
        elif chat_info['type'] in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
            if chat_info.get('description'):
                info_text += f"**Description:** {chat_info['description']}\n"
                
            if chat_info.get('invite_link'):
                info_text += f"**Invite Link:** {chat_info['invite_link']}\n"
                
            if chat_info.get('is_verified') is not None:
                info_text += f"**Verified:** {'Yes' if chat_info['is_verified'] else 'No'}\n"
                
            if chat_info.get('is_restricted') is not None:
                info_text += f"**Restricted:** {'Yes' if chat_info['is_restricted'] else 'No'}\n"
                
            if chat_info.get('has_protected_content') is not None:
                info_text += f"**Protected Content:** {'Yes' if chat_info['has_protected_content'] else 'No'}\n"
        
        # Update the message with the info
        await info_msg.edit_text(info_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        await message.reply(f"Error: {str(e)}")
    finally:
        # Always disconnect the client when done
        await safe_disconnect(acc)

# cancel command
@Client.on_message(filters.command(["cancel"]))
async def cancel_command(client: Client, message: Message):
    task = user_tasks.get(message.chat.id)
    if task:
        task.cancel()
        del user_tasks[message.chat.id]
        await client.send_message(message.chat.id, "Your task has been cancelled.", reply_to_message_id=message.id)
    else:
        await client.send_message(message.chat.id, "There is no ongoing task to cancel.", reply_to_message_id=message.id)

@Client.on_message(filters.text & filters.private & ~filters.command(["start", "help", "cancel", "info", "login", "logout", "qrlogin", "status", "chatinfo"]))
async def save(client: Client, message: Message):
    # Avval post limit input tekshiruvi (custom post count so'ralganda)
    post_limit_data = database.find_one({
        'chat_id': message.chat.id,
        'expecting_post_limit': True
    })
    if post_limit_data and 'post_limit_data' in post_limit_data:
        await handle_post_limit_input(client, message)
        # Agar URL bo'lmasa, qaytib chiqamiz (raqam yoki noto'g'ri kiritish)
        if "https://t.me/" not in message.text:
            return
    try:
        if "https://t.me/" in message.text:
            # Process the URL to determine what type of link it is
            url = message.text.strip()
            
            # Check for QuizBot quizzes
            if "t.me/quizbot" in url.lower() or "quizbot" in url.lower():
                await handle_quizbot(client, message, url)
                return
                
            # Check for comment threads
            if "?thread=" in url:
                # Handle comment section links: https://t.me/c/2317039197/359?thread=358
                await handle_comment_thread(client, message, url)
                return
                
            # Check for topics with improved regex to handle different formats
            # Format: https://t.me/c/CHATID/TOPICID/MSGID or https://t.me/c/CHATID/TOPICID/MSGID-ENDID
            topic_match = re.search(r'https://t\.me/c/(\d+)/(\d+)/(\d+)(?:-(\d+))?', url)
            if topic_match:
                # Handle topic links: https://t.me/c/2346917200/923/924-948
                await handle_topic(client, message, url)
                return
                
            # Standard post link processing
            datas = url.split("/")
            
            # Fix for URLs with "/c/" but not enough segments
            if "https://t.me/c/" in url and len(datas) < 5:
                await client.send_message(message.chat.id, "Invalid URL format. Please provide a valid Telegram post link.", reply_to_message_id=message.id)
                return
            
            # Parse message IDs from the URL
            try:
                temp = datas[-1].replace("?single","").split("-")
                fromID = int(temp[0].strip())
                try:
                    toID = int(temp[1].strip())
                    # If there is a range of posts, ask the user how many posts they want to retrieve
                    if toID - fromID > 5:
                        # Calculate post count for different options
                        total_posts = toID - fromID + 1
                        half_posts = total_posts // 2
                        quarter_posts = total_posts // 4
                        
                        # Create inline keyboard with options
                        keyboard = InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton(f"All ({total_posts})", callback_data=f"postlimit_{fromID}_{toID}_{total_posts}"),
                                InlineKeyboardButton(f"Half ({half_posts})", callback_data=f"postlimit_{fromID}_{toID}_{half_posts}")
                            ],
                            [
                                InlineKeyboardButton(f"Quarter ({quarter_posts})", callback_data=f"postlimit_{fromID}_{toID}_{quarter_posts}"),
                                InlineKeyboardButton("Custom", callback_data=f"postcustom_{fromID}_{toID}")
                            ],
                            [
                                InlineKeyboardButton("Cancel", callback_data="cancelpost")
                            ]
                        ])
                        
                        # Send message with options
                        sent_msg = await client.send_message(
                            message.chat.id,
                            f"You are trying to retrieve {total_posts} posts. How many would you like to download? (Automatically selecting ALL in 10 seconds)",
                            reply_markup=keyboard,
                            reply_to_message_id=message.id
                        )
                        
                        # Create a task that will wait 10 seconds and then auto-select "All" option
                        async def auto_select_all():
                            await asyncio.sleep(10)
                            try:
                                # Check if the message still exists and hasn't been updated (meaning no selection was made)
                                try:
                                    msg = await client.get_messages(message.chat.id, sent_msg.id)
                                    if msg and msg.reply_markup:  # Message still has reply markup, no selection was made
                                        await client.edit_message_text(
                                            message.chat.id, 
                                            sent_msg.id, 
                                            f"Time expired. Automatically selecting ALL ({total_posts}) posts..."
                                        )
                                        # Process all posts
                                        await process_posts(client, message, url, fromID, toID)
                                except Exception:
                                    # Message might have been deleted or already processed
                                    pass
                            except Exception as e:
                                print(f"Auto-selection error: {str(e)}")
                        
                        # Start the auto-selection task
                        asyncio.create_task(auto_select_all())
                        return
                except:
                    toID = fromID
            except Exception as e:
                await client.send_message(message.chat.id, f"Error parsing message IDs: {e}", reply_to_message_id=message.id)
                return
            
            # Proceed with downloading posts
            await process_posts(client, message, url, fromID, toID)
    except Exception as e:
        await message.reply(f"Error processing URL: {str(e)}")

# Process posts with given range
async def process_posts(client: Client, message: Message, url: str, fromID: int, toID: int):
    # Status message for long operations
    total = toID - fromID + 1
    status_msg = None
    if total > 1:
        status_msg = await client.send_message(
            message.chat.id,
            f"⏳ {total} ta xabar qayta ishlanmoqda...",
            reply_to_message_id=message.id
        )

    processed = 0

    # ── Private kanal: https://t.me/c/CHATID/MSGID ──
    if "https://t.me/c/" in url:
        user_data = database.find_one({'chat_id': message.chat.id})
        if not get(user_data, 'logged_in', False) or not user_data.get('session'):
            txt = strings['need_login']
            if status_msg:
                await client.edit_message_text(message.chat.id, status_msg.id, txt)
            else:
                await client.send_message(message.chat.id, txt, reply_to_message_id=message.id)
            return

        # chat_id URL dan bir marta olinadi
        try:
            chat_id_str = ''.join(filter(str.isdigit, url.split('/')[4]))
            chatid = int("-100" + chat_id_str)
        except Exception as e:
            await client.send_message(message.chat.id, f"URL xatosi: {e}", reply_to_message_id=message.id)
            return

        # acc bir marta yaratiladi — loop davomida qayta ishlatiladi
        acc, error = await create_client_session(user_data['session'])
        if error:
            txt = f"Ulanish xatosi: {error}"
            if status_msg:
                await client.edit_message_text(message.chat.id, status_msg.id, txt)
            else:
                await client.send_message(message.chat.id, txt, reply_to_message_id=message.id)
            return

        try:
            # ── CHANNEL_INVALID oldini olish: peer'ni resolve qilish ──
            if not await resolve_channel_peer(acc, chatid):
                txt = (
                    "❌ **Kanalga ulanib bo'lmadi.**\n\n"
                    "Sabablari:\n"
                    "• Siz bu kanalga a'zo emassiz\n"
                    "• Kanal o'chirilgan yoki mavjud emas\n"
                    "• Session eskirgan — /logout va /login qayta qiling"
                )
                if status_msg:
                    await client.edit_message_text(message.chat.id, status_msg.id, txt)
                else:
                    await client.send_message(message.chat.id, txt, reply_to_message_id=message.id)
                return

            for msgid in range(fromID, toID + 1):
                try:
                    if not await ensure_connected(acc):
                        await safe_send_message(client, message.chat.id,
                            "❌ Session uzildi, qayta ulanib bo'lmadi.",
                            reply_to_message_id=message.id)
                        break
                    await handle_private(client, acc, message, chatid, msgid)
                    processed += 1
                except Exception as e:
                    print(f"[process_posts] msgid={msgid} xatosi: {type(e).__name__}: {e}")
                if status_msg and processed % 5 == 0 and processed > 0:
                    await client.edit_message_text(
                        message.chat.id, status_msg.id,
                        f"⏳ {processed}/{total} xabar..."
                    )
                await asyncio.sleep(2)
        finally:
            await safe_disconnect(acc)

    # ── Bot chat: https://t.me/b/BOTUSERNAME/MSGID ──
    elif "https://t.me/b/" in url:
        user_data = database.find_one({"chat_id": message.chat.id})
        if not get(user_data, 'logged_in', False) or not user_data.get('session'):
            txt = strings['need_login']
            if status_msg:
                await client.edit_message_text(message.chat.id, status_msg.id, txt)
            else:
                await client.send_message(message.chat.id, txt, reply_to_message_id=message.id)
            return

        username = url.split("/")[4]
        acc, error = await create_client_session(user_data['session'])
        if error:
            txt = f"Ulanish xatosi: {error}"
            if status_msg:
                await client.edit_message_text(message.chat.id, status_msg.id, txt)
            else:
                await client.send_message(message.chat.id, txt, reply_to_message_id=message.id)
            return

        try:
            for msgid in range(fromID, toID + 1):
                try:
                    if not await ensure_connected(acc):
                        await safe_send_message(client, message.chat.id,
                            "❌ Session uzildi, qayta ulanib bo'lmadi.",
                            reply_to_message_id=message.id)
                        break
                    await handle_private(client, acc, message, username, msgid)
                    processed += 1
                except Exception:
                    pass
                if status_msg and processed % 5 == 0 and processed > 0:
                    await client.edit_message_text(
                        message.chat.id, status_msg.id,
                        f"⏳ {processed}/{total} xabar..."
                    )
                await asyncio.sleep(2)
        finally:
            await safe_disconnect(acc)

    # ── Ochiq kanal: https://t.me/USERNAME/MSGID ──
    else:
        username = url.split("/")[3]
        # Ochiq kanallar uchun acc faqat copy_message ishlamasa kerak bo'ladi
        acc = None
        user_data = None

        try:
            for msgid in range(fromID, toID + 1):
                try:
                    msg = await client.get_messages(username, msgid)
                except UsernameNotOccupied:
                    txt = "Username mavjud emas"
                    if status_msg:
                        await client.edit_message_text(message.chat.id, status_msg.id, txt)
                    else:
                        await client.send_message(message.chat.id, txt, reply_to_message_id=message.id)
                    return
                except Exception:
                    await asyncio.sleep(2)
                    continue

                try:
                    # copy_message — bot orqali to'g'ridan-to'g'ri ko'chirish
                    await client.copy_message(
                        message.chat.id, msg.chat.id, msg.id,
                        reply_to_message_id=message.id
                    )
                    processed += 1
                except Exception:
                    # copy_message ishlamasa user session bilan yuborish
                    if user_data is None:
                        user_data = database.find_one({"chat_id": message.chat.id})
                    if not get(user_data, 'logged_in', False) or not user_data.get('session'):
                        txt = strings['need_login']
                        if status_msg:
                            await client.edit_message_text(message.chat.id, status_msg.id, txt)
                        else:
                            await client.send_message(message.chat.id, txt, reply_to_message_id=message.id)
                        return
                    if acc is None:
                        acc, error = await create_client_session(user_data['session'])
                        if error:
                            txt = f"Ulanish xatosi: {error}"
                            if status_msg:
                                await client.edit_message_text(message.chat.id, status_msg.id, txt)
                            else:
                                await client.send_message(message.chat.id, txt, reply_to_message_id=message.id)
                            return
                    try:
                        await handle_private(client, acc, message, username, msgid)
                        processed += 1
                    except Exception:
                        pass

                if status_msg and processed % 5 == 0 and processed > 0:
                    await client.edit_message_text(
                        message.chat.id, status_msg.id,
                        f"⏳ {processed}/{total} xabar..."
                    )
                await asyncio.sleep(2)
        finally:
            if acc:
                await safe_disconnect(acc)

    # Yakuniy status
    if status_msg:
        await client.edit_message_text(
            message.chat.id, status_msg.id,
            f"✅ Tayyor! {processed}/{total} xabar yuborildi."
        )

# Handle comment threads
async def handle_comment_thread(client: Client, message: Message, url):
    # Parse the URL to extract chat_id, message_id, and thread_id
    # Example: https://t.me/c/2317039197/359?thread=358
    chat_id_match = re.search(r'https://t\.me/c/(\d+)/(\d+)', url)
    thread_id_match = re.search(r'\?thread=(\d+)', url)
    range_match = re.search(r'&range(\d+)-(\d+)', url)
    
    if not chat_id_match or not thread_id_match:
        await client.send_message(message.chat.id, "Invalid comment section link format. Please use format: https://t.me/c/{chat_id}/{message_id}?thread={thread_id}&range{start}-{end}", reply_to_message_id=message.id)
        return
    
    chat_id = int("-100" + chat_id_match.group(1))
    message_id = int(chat_id_match.group(2))
    thread_id = int(thread_id_match.group(1))
    
    # Check if range is specified
    start_id = message_id  # Default to the message_id
    end_id = message_id    # Default to the message_id
    
    if range_match:
        start_id = int(range_match.group(1))
        end_id = int(range_match.group(2))
    
    # Get user session
    user_data = database.find_one({'chat_id': message.chat.id})
    if not get(user_data, 'logged_in', False) or user_data['session'] is None:
        await client.send_message(message.chat.id, strings['need_login'])
        return
    
    # Connect with user's session
    acc, error = await create_client_session(user_data['session'])
    if error:
        await client.send_message(message.chat.id, error)
        return
    
    try:
        # Inform the user about processing
        status_msg = await client.send_message(message.chat.id, f"Processing comments from {start_id} to {end_id} in thread {thread_id}...", reply_to_message_id=message.id)
        
        # Get messages from the comment section
        processed_count = 0
        for msg_id in range(start_id, end_id + 1):
            try:
                # Get message by ID from the thread
                msg = await acc.get_messages(chat_id, msg_id)
                
                # Skip if message doesn't exist or isn't part of the thread
                if not msg or (hasattr(msg, 'reply_to_message_id') and msg.reply_to_message_id != thread_id):
                    continue
                
                # Check if this is a text-only message
                msg_type = get_message_type(msg)
                if msg_type == "Text":
                    try:
                        # Process text messages directly
                        reply_markup = None
                        if hasattr(msg, 'reply_markup') and msg.reply_markup:
                            reply_markup = msg.reply_markup
                            
                        await client.send_message(
                            message.chat.id,
                            msg.text,
                            entities=msg.entities,
                            reply_to_message_id=message.id,
                            reply_markup=reply_markup,
                            parse_mode=None  # Explicitly disable any additional parsing
                        )
                        processed_count += 1
                    except Exception:
                        # Completely suppress all errors for text messages
                        pass
                else:
                    # For media messages, use regular handler
                    try:
                        await handle_private(client, acc, message, chat_id, msg_id)
                        processed_count += 1
                    except Exception:
                        # Completely suppress all errors
                        pass
                
                await asyncio.sleep(2)  # Add delay between messages
                
            except Exception:
                # Completely suppress all errors for individual messages
                pass
        
        # Update status when complete
        if processed_count > 0:
            await client.edit_message_text(message.chat.id, status_msg.id, f"Comment thread download completed! Processed {processed_count} messages.")
        else:
            await client.edit_message_text(message.chat.id, status_msg.id, "No messages could be processed from this thread.")
        
    except Exception as e:
        await client.send_message(message.chat.id, f"Error processing comment thread: {e}", reply_to_message_id=message.id)
    finally:
        await safe_disconnect(acc)

# Handle topic posts
async def safe_send_message(client: Client, user_id: int, text: str, **kwargs):
    """
    Safely send a message using bot client, fallback to logging if USER_IS_BOT error occurs.
    This handles cases where the recipient is a bot or restricted.
    """
    try:
        return await client.send_message(user_id, text, **kwargs)
    except Exception as e:
        error_str = str(e)
        # Check if the error is because recipient is a bot
        if "USER_IS_BOT" in error_str or "user is bot" in error_str.lower():
            logger.warning(f"Cannot send message to {user_id}: Bot cannot message other bots. Error: {e}")
            print(f"[safe_send_message] Cannot send to {user_id}: {e}")
            return None
        else:
            # Re-raise other errors
            raise

async def handle_topic(client: Client, message: Message, url):
    # Parse the URL to extract chat_id, topic_id, and message range
    # Example: https://t.me/c/2346917200/923/924-948
    topic_match = re.search(r'https://t\.me/c/(\d+)/(\d+)/(\d+)(?:-(\d+))?', url)
    
    if not topic_match:
        await safe_send_message(client, message.chat.id, "Invalid topic link format. Please use format: https://t.me/c/{chat_id}/{topic_id}/{message_id} or https://t.me/c/{chat_id}/{topic_id}/{start_id}-{end_id}", reply_to_message_id=message.id)
        return
    
    chat_id = int("-100" + topic_match.group(1))
    topic_id = int(topic_match.group(2))
    start_id = int(topic_match.group(3))
    
    # Default end_id to start_id if not provided
    end_id = int(topic_match.group(4)) if topic_match.group(4) else start_id
    
    # Ensure start_id and end_id are used correctly regardless of which is smaller
    min_id = min(start_id, end_id)
    max_id = max(start_id, end_id)
    
    # Get user session
    user_data = database.find_one({'chat_id': message.chat.id})
    if not get(user_data, 'logged_in', False) or user_data['session'] is None:
        await safe_send_message(client, message.chat.id, strings['need_login'])
        return
    
    # Connect with user's session
    acc, error = await create_client_session(user_data['session'])
    if error:
        await safe_send_message(client, message.chat.id, error)
        return
    
    try:
        # Inform the user about processing
        status_msg = await safe_send_message(client, message.chat.id, f"Processing topic posts from {min_id} to {max_id} in topic {topic_id}...", reply_to_message_id=message.id)
        
        # Get messages from the topic
        processed_count = 0
        for msg_id in range(min_id, max_id + 1):
            try:
                if not await ensure_connected(acc):
                    await safe_send_message(client, message.chat.id,
                        "❌ Session uzildi, qayta ulanib bo'lmadi.",
                        reply_to_message_id=message.id)
                    break
                # For topic messages, we need to use a different approach since topic_id might not be supported
                # Get the message by regular ID first
                try:
                    # Instead of using topic_id parameter, we'll get messages normally and filter
                    msg = await acc.get_messages(chat_id, message_ids=[msg_id])
                    
                    if not msg or not msg[0]:
                        continue
                    
                    # Process the message
                    msg = msg[0]  # get_messages returns a list
                    
                    # Check if this message belongs to the topic we're interested in
                    # This might be imperfect, but it's a workaround for the topic_id parameter issue
                    msg_type = get_message_type(msg)
                    
                    # Process based on message type
                    if msg_type == "Text":
                        try:
                            reply_markup = None
                            if hasattr(msg, 'reply_markup') and msg.reply_markup:
                                reply_markup = msg.reply_markup
                            
                            # Check if the message has any entities (like URLs)
                            if hasattr(msg, 'entities') and msg.entities:
                                await safe_send_message(
                                    client,
                                    message.chat.id,
                                    msg.text,
                                    entities=msg.entities,
                                    reply_to_message_id=message.id,
                                    reply_markup=reply_markup,
                                    disable_web_page_preview=False,  # Allow web page previews for URLs
                                    parse_mode=None  # Explicitly disable any additional parsing
                                )
                            else:
                                # If no entities, send regular text
                                await safe_send_message(
                                    client,
                                    message.chat.id,
                                    msg.text,
                                    reply_to_message_id=message.id,
                                    reply_markup=reply_markup,
                                    parse_mode=None  # Explicitly disable any additional parsing
                                )
                            processed_count += 1
                        except Exception:
                            # Silently ignore all errors for text messages
                            pass
                    else:
                        # For media messages, use regular handler
                        try:
                            await handle_private(client, acc, message, chat_id, msg_id)
                            processed_count += 1
                        except Exception as hp_err:
                            # Xatoni loglash (jimgina o'tkazib yuborish o'rniga)
                            print(f"[handle_topic] msg_id={msg_id} xatosi: {type(hp_err).__name__}: {hp_err}")
                except Exception as inner_err:
                    # Individual message xatosi
                    print(f"[handle_topic] inner msg_id={msg_id}: {type(inner_err).__name__}: {inner_err}")
                    pass

                await asyncio.sleep(1)  # Shorter delay between messages

            except Exception as outer_err:
                # Suppress all errors for individual messages
                print(f"[handle_topic] outer msg_id={msg_id}: {type(outer_err).__name__}: {outer_err}")
                continue
        
        # Update status when complete (use safe send in case status_msg is None)
        if status_msg:
            try:
                if processed_count > 0:
                    await client.edit_message_text(message.chat.id, status_msg.id, f"Topic download completed! Processed {processed_count} messages.")
                else:
                    await client.edit_message_text(message.chat.id, status_msg.id, "No messages could be processed from this topic.")
            except Exception as edit_err:
                logger.warning(f"Could not edit status message: {edit_err}")
        
    except Exception as e:
        await safe_send_message(client, message.chat.id, f"Error processing topic: {e}", reply_to_message_id=message.id)
    finally:
        await safe_disconnect(acc)

# handle private
async def handle_private(client: Client, acc, message: Message, chatid: int, msgid: int):
    """Wrapper — download qilingan faylni har qanday holatda tozalaydi."""
    file = None
    smsg = None
    down_event = None
    up_event = None
    dosta = None
    upsta = None
    try:
        file, smsg, down_event, up_event, dosta, upsta = await _handle_private_inner(
            client, acc, message, chatid, msgid
        )
    except BaseException:
        # CancelledError ham ushlanadi
        raise
    finally:
        # ── Fayl tozalash — har doim (success, error, cancel) ──
        if isinstance(file, str) and file and os.path.exists(file):
            try:
                os.remove(file)
            except Exception:
                pass
        # upstatus va progress tozalash
        if up_event and not up_event.is_set():
            up_event.set()
        if upsta and not upsta.done():
            upsta.cancel()
        if down_event and not down_event.is_set():
            down_event.set()
        if dosta and not dosta.done():
            dosta.cancel()
        if smsg:
            try:
                await client.delete_messages(message.chat.id, [smsg.id])
            except Exception:
                pass


_EMPTY = (None, None, None, None, None, None)  # file, smsg, down_event, up_event, dosta, upsta


async def _handle_private_inner(client: Client, acc, message: Message, chatid: int, msgid: int):
    # Bot ID ni olish — user session bot chatiga yuborish uchun
    bot_id = await _get_bot_id(client)
    # Add retry mechanism for network errors
    for attempt in range(MAX_RETRIES):
        try:
            msg: Message = await acc.get_messages(chatid, msgid)
            if not msg:
                return _EMPTY  # Silently ignore if message not found

            msg_type = get_message_type(msg)
            
            # Handle polls specially
            if msg_type == "Poll" and hasattr(msg, "poll") and msg.poll is not None:
                await handle_poll(client, message, msg.poll)
                return _EMPTY
            elif msg_type == "Poll" and (not hasattr(msg, "poll") or msg.poll is None):
                # If it's a poll type but the poll object is missing, send a more helpful message
                await safe_send_message(
                    client,
                    message.chat.id,
                    "This message contains a poll, but the poll data couldn't be retrieved. This might be due to restricted access or the poll has expired.",
                    reply_to_message_id=message.id
                )
                return _EMPTY

            # Handle WebPage specially - treat it as a text message with web preview
            if msg_type == "WebPage":
                try:
                    # Get reply markup from original message
                    reply_markup = None
                    if hasattr(msg, 'reply_markup') and msg.reply_markup:
                        reply_markup = msg.reply_markup
                    
                    # Use the text with proper markdown formatting
                    if msg.text or msg.caption:
                        text_content = msg.text or msg.caption
                        try:
                            if hasattr(msg, 'text') and msg.text:
                                text_content = msg.text.markdown
                            elif hasattr(msg, 'caption') and msg.caption:
                                text_content = msg.caption.markdown
                                
                            # Apply additional sanitization
                            text_content = sanitize_markdown(text_content)
                        except Exception:
                            # If that fails, try direct entity conversion for hyperlinks
                            entities = msg.entities if hasattr(msg, 'entities') and msg.entities else (msg.caption_entities if hasattr(msg, 'caption_entities') else None)
                            if entities:
                                text_content = extract_hyperlinks(text_content, entities)
                        
                        # Send the message with web_page preview enabled
                        await safe_send_message(
                            client,
                            message.chat.id,
                            text_content,
                            reply_to_message_id=message.id,
                            reply_markup=reply_markup,
                            disable_web_page_preview=False,  # Explicitly enable web preview
                            parse_mode=ParseMode.MARKDOWN
                        )
                    else:
                        # If no text, just send a message about the link
                        await safe_send_message(
                            client,
                            message.chat.id,
                            "This message contains a web link preview.",
                            reply_to_message_id=message.id,
                            reply_markup=reply_markup
                        )
                    return _EMPTY
                except Exception as e:
                    # Handle WebPage errors gracefully
                    if "WEBPAGE_NOT_FOUND" in str(e) or "WEBPAGE_CURL_FAILED" in str(e):
                        await safe_send_message(
                            client,
                            message.chat.id,
                            f"Error: Could not generate preview for the webpage link. The website might be unavailable or blocking Telegram's preview feature.",
                            reply_to_message_id=message.id
                        )
                    else:
                        await safe_send_message(client, message.chat.id, f"Error: {e}", reply_to_message_id=message.id)
                    return _EMPTY

            # If it's text-only message and has no downloadable media, handle it directly without showing errors
            if msg_type == "Text":
                try:
                    # Get reply markup from original message
                    reply_markup = None
                    if hasattr(msg, 'reply_markup') and msg.reply_markup:
                        reply_markup = msg.reply_markup
                    
                    # Use the text with proper markdown formatting to preserve all hyperlinks
                    if msg.text:
                        try:
                            # First try the markdown property
                            text_content = msg.text.markdown
                            # Apply additional sanitization
                            text_content = sanitize_markdown(text_content)
                        except Exception:
                            # If that fails, try direct entity conversion for hyperlinks
                            if hasattr(msg, 'entities') and msg.entities:
                                text_content = extract_hyperlinks(msg.text, msg.entities)
                            else:
                                # Fallback to plain text
                                text_content = msg.text
                        
                        # If text is too long for a single message, split it
                        if len(text_content) > 4096:  # Telegram message limit
                            parts = [text_content[i:i+4096] for i in range(0, len(text_content), 4096)]
                            for part in parts:
                                await safe_send_message(
                                    client,
                                    message.chat.id,
                                    part,
                                    reply_to_message_id=message.id if parts.index(part) == 0 else None,
                                    reply_markup=reply_markup if parts.index(part) == 0 else None,
                                    parse_mode=ParseMode.MARKDOWN
                                )
                        else:
                            await safe_send_message(
                                client,
                                message.chat.id,
                                text_content,
                                reply_to_message_id=message.id,
                                reply_markup=reply_markup,
                                parse_mode=ParseMode.MARKDOWN
                            )
                    else:
                        # If no text, just send a blank message with the reply markup
                        await safe_send_message(
                            client,
                            message.chat.id,
                            "",
                            reply_to_message_id=message.id,
                            reply_markup=reply_markup
                        )
                    
                    return _EMPTY
                except Exception as e:
                    # Only show error for non-empty message errors
                    if "400 MESSAGE_EMPTY" in str(e):
                        await safe_send_message(client, message.chat.id, f"Post ID: {msgid}", reply_to_message_id=message.id)
                    # Silently ignore "downloadable media" errors
                    elif "downloadable media" not in str(e).lower():
                        await safe_send_message(client, message.chat.id, f"Error: {e}", reply_to_message_id=message.id)
                return _EMPTY
            
            break  # Success, exit retry loop
        except NotImplementedError:
            # Pyrofork bu media turini qo'llab-quvvatlamaydi
            # (masalan giveaway, story, invoice va h.k.)
            await safe_send_message(
                client, message.chat.id,
                f"⚠️ **Post {msgid}:** Bu media turini yuklash hozircha qo'llab-quvvatlanmaydi.",
                reply_to_message_id=message.id
            )
            return _EMPTY
        except (ChannelInvalid, ChannelPrivate) as ch_err:
            # Kanal topilmadi yoki ruxsat yo'q
            logger.warning(f"Channel error for chatid={chatid}, msgid={msgid}: {ch_err}")
            # Peer'ni resolve qilib qayta urinish
            if attempt < MAX_RETRIES - 1:
                resolved = await resolve_channel_peer(acc, chatid)
                if resolved:
                    logger.info(f"Channel {chatid} resolved, retrying...")
                    await asyncio.sleep(1)
                    continue
            await safe_send_message(
                client, message.chat.id,
                f"❌ **Kanal xatosi:** `{ch_err}`\n\n"
                f"Bu kanal mavjud emas yoki siz a'zo emassiz.\n"
                f"Iltimos /logout va /login qayta qiling.",
                reply_to_message_id=message.id
            )
            return _EMPTY
        except Exception as e:
            error_str = str(e).lower()
            # Completely suppress these specific errors
            if "downloadable media" in error_str or "message_empty" in error_str or "400 message" in error_str:
                return _EMPTY  # Silently ignore

            # CHANNEL_INVALID string bilan ham tekshirish
            if "channel_invalid" in error_str or "channel_private" in error_str:
                if attempt < MAX_RETRIES - 1:
                    resolved = await resolve_channel_peer(acc, chatid)
                    if resolved:
                        logger.info(f"Channel {chatid} resolved via string check, retrying...")
                        await asyncio.sleep(1)
                        continue
                await safe_send_message(
                    client, message.chat.id,
                    f"❌ **Kanal xatosi:** Kanalga kirish imkoni yo'q.\n"
                    f"Iltimos /logout va /login qayta qiling.",
                    reply_to_message_id=message.id
                )
                return _EMPTY

            # For network errors, retry
            if any(kw in error_str for kw in ["connection", "network", "timeout", "reset", "closed", "transport"]):
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                    continue
            
            # For other errors, we'll still show them - except specific ones we want to handle
            if "400 MESSAGE_EMPTY" in str(e):
                await safe_send_message(client, message.chat.id, f"Post ID: {msgid}", reply_to_message_id=message.id)
            else:
                await safe_send_message(client, message.chat.id, f"Error: {e}", reply_to_message_id=message.id)
            return _EMPTY

    # Check if the message has downloadable media
    has_media = False
    for media_type in ["Document", "Video", "VideoNote", "Voice", "Audio", "Photo", "Animation", "Sticker"]:
        if media_type == msg_type:
            has_media = True
            break
            
    # If there's no downloadable media, silently return
    if not has_media:
        return _EMPTY

    # Check file size to determine if we need to show progress
    show_progress = True
    file_size = 0

    # Get file size based on message type
    if "Document" == msg_type and hasattr(msg, 'document') and hasattr(msg.document, 'file_size'):
        file_size = msg.document.file_size or 0
    elif "Video" == msg_type and hasattr(msg, 'video') and hasattr(msg.video, 'file_size'):
        file_size = msg.video.file_size or 0
    elif "Audio" == msg_type and hasattr(msg, 'audio') and hasattr(msg.audio, 'file_size'):
        file_size = msg.audio.file_size or 0
    elif "Photo" == msg_type:
        show_progress = False  # Never show progress for photos

    # Skip status messages for files smaller than 20MB (20971520 bytes)
    if file_size > 0 and file_size < 20971520:
        show_progress = False

    # Only show status message for large files
    smsg = None
    dosta = None
    upsta = None
    down_event = None
    up_event = None
    file = None
    use_ram = False

    # msgid — unique key for progress tracking (not message.id which is shared across all calls)
    prog_key = msgid

    if show_progress:
        smsg = await safe_send_message(client, message.chat.id, 'Downloading', reply_to_message_id=message.id)
        if smsg:
            down_event = asyncio.Event()
            dosta = asyncio.create_task(downstatus(client, prog_key, smsg, down_event))

    # Download — har doim diskka (progress RAMda saqlanadi)
    request_scope_id = message.from_user.id if getattr(message, "from_user", None) else message.chat.id
    user_temp_dir = os.path.join("downloads", f"user_{request_scope_id}")
    os.makedirs(user_temp_dir, exist_ok=True)

    default_extensions = {
        "Video": ".mp4",
        "Audio": ".mp3",
        "Photo": ".jpg",
    }
    file_ext = default_extensions.get(msg_type, "")
    if msg_type == "Document" and getattr(msg, "document", None) and getattr(msg.document, "file_name", None):
        raw_ext = os.path.splitext(msg.document.file_name)[1]
        file_ext = re.sub(r"[^A-Za-z0-9.]", "", raw_ext)[:15]
        if file_ext and not file_ext.startswith("."):
            file_ext = f".{file_ext}"

    download_path = os.path.join(user_temp_dir, f"{chatid}_{msgid}{file_ext}")

    for dl_attempt in range(MAX_RETRIES):
            try:
                if show_progress:
                    file = await acc.download_media(
                        msg,
                        file_name=download_path,
                        progress=progress,
                        progress_args=[prog_key, "down"]
                    )
                else:
                    file = await acc.download_media(msg, file_name=download_path)

                # downstatus loopini to'xtatish
                if down_event:
                    down_event.set()
                break  # Muvaffaqiyat
            except Exception as e:
                error_str = str(e).lower()
                if "downloadable media" in error_str:
                    if smsg:
                        try:
                            await client.delete_messages(message.chat.id, [smsg.id])
                        except Exception:
                            pass
                        smsg = None
                    if down_event:
                        down_event.set()
                    return _EMPTY

                # For network errors, retry
                if "connection" in error_str or "network" in error_str or "timeout" in error_str:
                    if dl_attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAY * (dl_attempt + 1))
                        continue

                # For other errors, show error and return
                if smsg:
                    try:
                        await client.delete_messages(message.chat.id, [smsg.id])
                    except Exception:
                        pass
                    smsg = None
                if down_event:
                    down_event.set()
                if "error downloading" not in error_str:
                    await safe_send_message(
                        client,
                        message.chat.id,
                        f"❌ **Download xatosi ({msgid}):** `{e}`",
                        reply_to_message_id=message.id
                    )
                return _EMPTY

    if not file:
        if smsg:
            try:
                await client.delete_messages(message.chat.id, [smsg.id])
            except Exception:
                pass
            smsg = None
        if down_event:
            down_event.set()
        await safe_send_message(
            client,
            message.chat.id,
            f"❌ **Download muvaffaqiyatsiz ({msgid})**",
            reply_to_message_id=message.id
        )
        return _EMPTY

    # TUZATISH: DOCUMENT_INVALID — download qilingan fayl bo'sh bo'lsa
    if isinstance(file, str):
        file = os.path.abspath(file)
        if not os.path.exists(file) or os.path.getsize(file) == 0:
            if smsg:
                try:
                    await client.delete_messages(message.chat.id, [smsg.id])
                except Exception:
                    pass
                smsg = None
            if down_event:
                down_event.set()
            await safe_send_message(
                client,
                message.chat.id,
                f"**Download xatosi:** fayl topilmadi: `{file}`",
                reply_to_message_id=message.id
            )
            return _EMPTY

    if show_progress and smsg:
        up_event = asyncio.Event()
        upsta = asyncio.create_task(upstatus(client, smsg.id, smsg, up_event))

    # Handle captions with proper markdown formatting
    caption = None
    
    if msg.caption:
        try:
            # Use the markdown property to get properly formatted caption
            caption = msg.caption.markdown
            # Apply additional sanitization for markdown
            caption = sanitize_markdown(caption)
        except Exception:
            # If that fails, try direct entity conversion for hyperlinks
            if hasattr(msg, 'caption_entities') and msg.caption_entities:
                caption = extract_hyperlinks(msg.caption, msg.caption_entities)
            else:
                # In case of any issues, fall back to plain text
                caption = msg.caption

    # Split caption if needed for Telegram's caption limit
    if caption and len(caption) > 1024:  # Telegram caption limit
        first_caption = caption[:1024]
        second_caption = caption[1024:]
    else:
        first_caption = caption
        second_caption = None

    # Get reply markup (buttons) if available
    reply_markup = None
    if hasattr(msg, 'reply_markup') and msg.reply_markup:
        reply_markup = msg.reply_markup


    if "Document" == msg_type:
        # video extension bo'lsa Video sifatida yuborish
        if isinstance(file, str) and file.endswith(('.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm')):
            doc_msg_type = "Video"
            extra = {}
            # Pyrofork Document da video metadata yo'q —
            # avval msg.video dan olishga urinamiz, bo'lmasa ffprobe bilan aniqlaymiz
            if hasattr(msg, 'video') and msg.video:
                extra["duration"] = getattr(msg.video, 'duration', None)
                extra["width"] = getattr(msg.video, 'width', None)
                extra["height"] = getattr(msg.video, 'height', None)
            # ffprobe bilan aniqlaymiz (msg.video bo'lmasa yoki qiymatlari None/0 bo'lsa)
            if not extra.get("duration") or not extra.get("width"):
                probe = await get_video_metadata(file)
                if probe:
                    extra["duration"] = extra.get("duration") or probe.get("duration", 0)
                    extra["width"] = extra.get("width") or probe.get("width", 0)
                    extra["height"] = extra.get("height") or probe.get("height", 0)
        elif isinstance(file, str) and file.endswith('.ogg'):
            doc_msg_type = "Voice"
            extra = {}
        else:
            doc_msg_type = "Document"
            extra = {}

        await upload_via_user_session(
            bot=client,
            user_id=message.from_user.id,
            file_path=file,
            caption=first_caption,
            progress_msg=smsg,
            target_chat=bot_id,
            msg_type=doc_msg_type,
            extra=extra,
            file_size=file_size,
            use_ram=use_ram,
            existing_client=acc,
        )
        if second_caption:
            await safe_send_message(client, message.chat.id, second_caption, reply_to_message_id=message.id)

    elif "Video" == msg_type:
        extra = {
            "duration": getattr(msg.video, 'duration', 0) if msg.video else 0,
            "width": getattr(msg.video, 'width', 0) if msg.video else 0,
            "height": getattr(msg.video, 'height', 0) if msg.video else 0,
        }
        await upload_via_user_session(
            bot=client,
            user_id=message.from_user.id,
            file_path=file,
            caption=first_caption,
            progress_msg=smsg,
            target_chat=bot_id,
            msg_type="Video",
            extra=extra,
            file_size=file_size,
            use_ram=use_ram,
            existing_client=acc,
        )
        if second_caption:
            await safe_send_message(client, message.chat.id, second_caption, reply_to_message_id=message.id)

    elif "VideoNote" == msg_type:
        extra = {
            "duration": getattr(msg.video_note, 'duration', 0) if msg.video_note else 0,
            "length": getattr(msg.video_note, 'length', 0) if msg.video_note else 0,
        }
        await upload_via_user_session(
            bot=client,
            user_id=message.from_user.id,
            file_path=file,
            caption=first_caption,
            progress_msg=smsg,
            target_chat=bot_id,
            msg_type="VideoNote",
            extra=extra,
            file_size=file_size,
            use_ram=use_ram,
            existing_client=acc,
        )

    elif "Voice" == msg_type:
        extra = {
            "duration": getattr(msg.voice, 'duration', 0) if msg.voice else 0,
        }
        await upload_via_user_session(
            bot=client,
            user_id=message.from_user.id,
            file_path=file,
            caption=first_caption,
            progress_msg=smsg,
            target_chat=bot_id,
            msg_type="Voice",
            extra=extra,
            file_size=file_size,
            use_ram=use_ram,
            existing_client=acc,
        )
        if second_caption:
            await safe_send_message(client, message.chat.id, second_caption, reply_to_message_id=message.id)

    elif "Audio" == msg_type:
        extra = {
            "duration": getattr(msg.audio, 'duration', 0) if msg.audio else 0,
            "performer": getattr(msg.audio, 'performer', None) if msg.audio else None,
            "title": getattr(msg.audio, 'title', None) if msg.audio else None,
        }
        await upload_via_user_session(
            bot=client,
            user_id=message.from_user.id,
            file_path=file,
            caption=first_caption,
            progress_msg=smsg,
            target_chat=bot_id,
            msg_type="Audio",
            extra=extra,
            file_size=file_size,
            use_ram=use_ram,
            existing_client=acc,
        )
        if second_caption:
            await safe_send_message(client, message.chat.id, second_caption, reply_to_message_id=message.id)

    elif "Photo" == msg_type:
        await upload_via_user_session(
            bot=client,
            user_id=message.from_user.id,
            file_path=file,
            caption=first_caption,
            progress_msg=smsg,
            target_chat=bot_id,
            msg_type="Photo",
            file_size=file_size,
            use_ram=use_ram,
            existing_client=acc,
        )
        if second_caption:
            await safe_send_message(client, message.chat.id, second_caption, reply_to_message_id=message.id)

    elif "Animation" == msg_type:
        await upload_via_user_session(
            bot=client,
            user_id=message.from_user.id,
            file_path=file,
            caption=first_caption,
            progress_msg=smsg,
            target_chat=bot_id,
            msg_type="Animation",
            file_size=file_size,
            use_ram=use_ram,
            existing_client=acc,
        )
        if second_caption:
            await safe_send_message(client, message.chat.id, second_caption, reply_to_message_id=message.id)

    elif "Sticker" == msg_type:
        await upload_via_user_session(
            bot=client,
            user_id=message.from_user.id,
            file_path=file,
            caption=first_caption,
            progress_msg=smsg,
            target_chat=bot_id,
            msg_type="Sticker",
            file_size=file_size,
            use_ram=use_ram,
            existing_client=acc,
        )

    else:
        await upload_via_user_session(
            bot=client,
            user_id=message.from_user.id,
            file_path=file,
            caption=first_caption,
            progress_msg=smsg,
            target_chat=bot_id,
            msg_type="Document",
            file_size=file_size,
            use_ram=use_ram,
            existing_client=acc,
        )
        if second_caption:
            await safe_send_message(client, message.chat.id, second_caption, reply_to_message_id=message.id)

    # Wrapper ga qaytarish — u finally da tozalaydi
    return file, smsg, down_event, up_event, dosta, upsta

# get the type of message
def get_message_type(msg: pyrogram.types.messages_and_media.message.Message):
    """
    Enhanced function to detect message type using MessageMediaType when available.
    Falls back to traditional attribute checking for backward compatibility.
    """
    # First try using the media attribute with MessageMediaType
    if hasattr(msg, 'media') and msg.media:
        if msg.media == MessageMediaType.VIDEO_NOTE:
            return "VideoNote"
        elif msg.media == MessageMediaType.DOCUMENT:
            return "Document"
        elif msg.media == MessageMediaType.VIDEO:
            return "Video"
        elif msg.media == MessageMediaType.ANIMATION:
            return "Animation"
        elif msg.media == MessageMediaType.STICKER:
            return "Sticker"
        elif msg.media == MessageMediaType.VOICE:
            return "Voice"
        elif msg.media == MessageMediaType.AUDIO:
            return "Audio"
        elif msg.media == MessageMediaType.PHOTO:
            return "Photo"
        elif msg.media == MessageMediaType.POLL:
            # Additional check to make sure poll object exists
            if hasattr(msg, 'poll') and msg.poll:
                return "Poll"
        elif msg.media == MessageMediaType.CONTACT:
            return "Contact"
        elif msg.media == MessageMediaType.LOCATION:
            return "Location"
        elif msg.media == MessageMediaType.VENUE:
            return "Venue"
        elif msg.media == 'web_page':
            try:
                # Check for web preview more safely
                if getattr(msg, 'web_preview', None) or getattr(msg, 'web_page', None):
                    return "WebPage"
                return "Text"  # Fallback to text if web_page attribute is empty
            except Exception:
                return "Text"  # Fallback to text if any error occurs with web_page
        elif msg.media == MessageMediaType.DICE:
            return "Dice"
    
    # Fall back to traditional attribute checking for compatibility
    try:
        msg.video_note.file_id
        return "VideoNote"
    except:
        pass
    try:
        msg.document.file_id
        return "Document"
    except:
        pass
    try:
        msg.video.file_id
        return "Video"
    except:
        pass
    try:
        msg.animation.file_id
        return "Animation"
    except:
        pass
    try:
        msg.sticker.file_id
        return "Sticker"
    except:
        pass
    try:
        msg.voice.file_id
        return "Voice"
    except:
        pass
    try:
        msg.audio.file_id
        return "Audio"
    except:
        pass
    try:
        msg.photo.file_id
        return "Photo"
    except:
        pass
    try:
        # More thorough check for polls
        if hasattr(msg, 'poll') and msg.poll:
            if hasattr(msg.poll, 'question') and msg.poll.question:
                return "Poll"
    except:
        pass
    try:
        msg.text
        return "Text"
    except:
        pass
    
    # If we got here, we couldn't determine the type
    return "Unknown"
        

# info command for channels and groups
@Client.on_message(filters.command(["info"]))
async def channel_info(client: Client, message: Message):
    # Check if a link was provided after the command
    if len(message.text.split()) < 2:
        await client.send_message(message.chat.id, "Please provide a link to a Telegram post after the /info command.", reply_to_message_id=message.id)
        return
        
    # Get the link from the command
    post_link = message.text.split(None, 1)[1].strip()
    
    # Check if it's a valid Telegram link
    if "https://t.me/" not in post_link:
        await client.send_message(message.chat.id, "Please provide a valid Telegram post link.", reply_to_message_id=message.id)
        return
    
    # Get user session string
    user_data = database.find_one({'chat_id': message.chat.id})
    
    # Check if user is logged in
    if user_data is None or not user_data.get('logged_in', False) or not user_data.get('session'):
        await client.send_message(message.chat.id, strings['need_login'], reply_to_message_id=message.id)
        return
    
    # Create client with user's session
    acc, error = await create_client_session(user_data.get('session'), "infoclient")
    
    if error:
        error_lower = str(error).lower()
        if "auth_key_unregistered" in error_lower or "key is not registered" in error_lower:
            # Reset user's session and tell them to log in again
            database.update_one({'_id': user_data['_id']}, {'$set': {'session': None, 'logged_in': False}})
            await client.send_message(
                message.chat.id, 
                "Your session is no longer valid. Please /logout and /login again.", 
                reply_to_message_id=message.id
            )
        else:
            await client.send_message(message.chat.id, f"Connection error: {error}", reply_to_message_id=message.id)
        return
    
    try:
        status_msg = await client.send_message(message.chat.id, "Retrieving group/channel information...", reply_to_message_id=message.id)
        
        # Extract chat_id and message_id from the link
        chat_id = None
        message_id = None
        
        if "/c/" in post_link:
            # Private channel/group with format https://t.me/c/1234567890/123
            parts = post_link.split("/")
            chat_id_parts = []
            msg_id_parts = []
            
            for i, part in enumerate(parts):
                if part == "c" and i+1 < len(parts):
                    chat_id_parts = parts[i+1:i+2]
                    if i+2 < len(parts):
                        msg_id_parts = parts[i+2:i+3]
                    break
            
            if chat_id_parts:
                chat_id_str = ''.join(filter(str.isdigit, chat_id_parts[0]))
                if chat_id_str:
                    # Always use -100 prefix for channels/supergroups
                    chat_id = int("-100" + chat_id_str)
            
            if msg_id_parts:
                message_id = int(''.join(filter(str.isdigit, msg_id_parts[0])))
        
        elif "/b/" in post_link:
            # Bot chat format https://t.me/b/botusername/123
            parts = post_link.split("/")
            bot_username = None
            
            for i, part in enumerate(parts):
                if part == "b" and i+1 < len(parts):
                    bot_username = parts[i+1]
                    if i+2 < len(parts):
                        message_id = int(''.join(filter(str.isdigit, parts[i+2])))
                    break
            
            if bot_username:
                chat_id = bot_username
        
        else:
            # Public channel/group with format https://t.me/username/123
            parts = post_link.split("/")
            if len(parts) > 3:
                username = parts[3]
                if username.startswith("@"):
                    username = username[1:]
                chat_id = username
                
                if len(parts) > 4:
                    message_id = int(''.join(filter(str.isdigit, parts[4])))
        
        if not chat_id:
            await client.edit_message_text(message.chat.id, status_msg.id, "Could not extract chat ID from the link.")
            await safe_disconnect(acc)
            return
        
        try:
            # Try different approaches to get the chat information
            chat = None
            error_msg = None
            
            # First, try to check if the user has access to this chat via dialogs
            try:
                found_in_dialogs = False
                async for dialog in acc.get_dialogs():
                    if isinstance(chat_id, int) and dialog.chat.id == chat_id:
                        chat = dialog.chat
                        found_in_dialogs = True
                        break
                    elif isinstance(chat_id, str) and hasattr(dialog.chat, 'username') and dialog.chat.username and dialog.chat.username.lower() == chat_id.lower():
                        chat = dialog.chat
                        found_in_dialogs = True
                        break
                
                if not found_in_dialogs and message_id:
                    # If not found in dialogs but we have a message ID, try to get the message
                    msg = await acc.get_messages(chat_id, message_id)
                    if msg and hasattr(msg, 'chat'):
                        chat = msg.chat
                    else:
                        # If message retrieval failed, try to get chat directly
                        chat = await acc.get_chat(chat_id)
                elif not found_in_dialogs:
                    # Direct chat access as last resort
                    chat = await acc.get_chat(chat_id)
            except Exception as e:
                error_msg = str(e)
                # If the first approach fails, try direct chat access
                try:
                    chat = await acc.get_chat(chat_id)
                    error_msg = None
                except Exception as direct_e:
                    error_msg = str(direct_e)
            
            if not chat:
                if "auth_key_unregistered" in error_msg.lower() or "key is not registered" in error_msg.lower():
                    # Reset user's session and tell them to log in again
                    database.update_one({'_id': user_data['_id']}, {'$set': {'session': None, 'logged_in': False}})
                    await client.edit_message_text(
                        message.chat.id, 
                        status_msg.id,
                        "Your session is no longer valid. Please /logout and /login again."
                    )
                elif "chat_id_invalid" in error_msg.lower() or "chat not found" in error_msg.lower():
                    await client.edit_message_text(
                        message.chat.id, 
                        status_msg.id,
                        "**Access Error:** You don't have access to this chat or the chat ID is invalid.\n\n"
                        "Possible solutions:\n"
                        "• Join the chat/channel first\n"
                        "• Make sure the chat/channel exists\n"
                        "• Check if you've been banned from the chat\n\n"
                        f"Technical error: {error_msg}"
                    )
                else:
                    await client.edit_message_text(
                        message.chat.id, 
                        status_msg.id,
                        f"Error retrieving chat information: {error_msg}"
                    )
                return
            
            # Build the information text with ID and name
            info_text = f"**Channel/Group Name**: {chat.title}\n**Channel/Group ID**: `{chat.id}`\n"
            
            # Add username if available
            if getattr(chat, 'username', None):
                info_text += f"**Username**: @{chat.username}\n"
                
            # Add members count if available
            if hasattr(chat, 'members_count') and chat.members_count:
                info_text += f"**Members**: {chat.members_count}\n"
            
            # Add description if available
            if getattr(chat, 'description', None):
                # Trim long descriptions
                description = chat.description
                if len(description) > 100:
                    description = description[:97] + "..."
                info_text += f"**Description**: {description}\n"
            
            # Send the information
            await client.edit_message_text(message.chat.id, status_msg.id, info_text)
            
        except Exception as e:
            error_str = str(e).lower()
            
            if "auth_key_unregistered" in error_str or "key is not registered" in error_str:
                # Reset user's session and tell them to log in again
                database.update_one({'_id': user_data['_id']}, {'$set': {'session': None, 'logged_in': False}})
                await client.edit_message_text(
                    message.chat.id, 
                    status_msg.id,
                    "Your session is no longer valid. Please /logout and /login again."
                )
            elif "chat_id_invalid" in error_str or "chat not found" in error_str:
                await client.edit_message_text(
                    message.chat.id, 
                    status_msg.id,
                    "**Access Error:** You don't have access to this chat or the chat ID is invalid.\n\n"
                    "Possible solutions:\n"
                    "• Join the chat/channel first\n"
                    "• Make sure the chat/channel exists\n"
                    "• Check if you've been banned from the chat\n\n"
                    f"Technical error: {str(e)}"
                )
            else:
                await client.edit_message_text(message.chat.id, status_msg.id, f"Error retrieving chat information: {e}")
    
    except Exception as e:
        error_str = str(e).lower()
        if "auth_key_unregistered" in error_str or "key is not registered" in error_str:
            # Reset user's session and tell them to log in again
            database.update_one({'_id': user_data['_id']}, {'$set': {'session': None, 'logged_in': False}})
            await client.send_message(
                message.chat.id, 
                "Your session is no longer valid. Please /logout and /login again.", 
                reply_to_message_id=message.id
            )
        else:
            await client.send_message(message.chat.id, f"Error retrieving information: {e}", reply_to_message_id=message.id)
    finally:
        await safe_disconnect(acc)

# Handle QuizBot quizzes
async def handle_quizbot(client: Client, message: Message, url):
    # Get user session
    user_data = database.find_one({'chat_id': message.chat.id})
    if not get(user_data, 'logged_in', False) or user_data['session'] is None:
        await client.send_message(message.chat.id, strings['need_login'])
        return
    
    # Extract the quiz or quiz-related information
    # Example: https://t.me/quizbot?start=quizXYZ123
    quiz_param_match = re.search(r't\.me/quizbot\?start=([a-zA-Z0-9_-]+)', url)
    if quiz_param_match:
        quiz_param = quiz_param_match.group(1)
    else:
        # If no valid quiz parameter is found
        await client.send_message(message.chat.id, "Invalid QuizBot link. Please provide a valid quiz sharing link.", reply_to_message_id=message.id)
        return
    
    # Connect with user session
    acc, error = await create_client_session(user_data['session'], "quizbot_client")
    if error:
        await client.send_message(message.chat.id, error)
        return
    
    try:
        # Inform the user that we're processing
        status_msg = await client.send_message(message.chat.id, "Processing QuizBot quiz link...", reply_to_message_id=message.id)
        
        # Send the quiz link directly using the user's session to ensure it works
        # This way the quiz will be shared properly in the chat
        quizbot_username = "QuizBot"
        
        # First, extract quiz information by starting the conversation with QuizBot
        await acc.send_message(quizbot_username, f"/start {quiz_param}")
        
        # Wait for QuizBot to respond
        await asyncio.sleep(2)
        
        # Get the last few messages from QuizBot
        messages = await acc.get_history(quizbot_username, limit=5)
        
        # Look for the share quiz button in recent messages
        quiz_message = None
        for msg in messages:
            # Check if this message has inline buttons
            if msg.reply_markup and isinstance(msg.reply_markup, InlineKeyboardMarkup):
                for row in msg.reply_markup.inline_keyboard:
                    for button in row:
                        # Look for buttons with "share" text
                        if button.text.lower().find("share") != -1:
                            quiz_message = msg
                            break
            if quiz_message:
                break
        
        if not quiz_message:
            await client.edit_message_text(message.chat.id, status_msg.id, "Could not find the quiz in QuizBot's messages. Please try again.")
            return
            
        # Extract quiz title and description
        quiz_title = ""
        quiz_description = ""
        if quiz_message.text:
            lines = quiz_message.text.split('\n')
            if lines:
                quiz_title = lines[0].strip()
                if len(lines) > 1:
                    quiz_description = '\n'.join(lines[1:]).strip()
        
        # Create direct quiz link - this is the key part that ensures the quiz works
        direct_quiz_link = f"https://t.me/quizbot?start={quiz_param}"
        
        # Create buttons for the quiz
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Play Quiz", url=direct_quiz_link)]
        ])
        
        # Create a message with quiz information
        info_text = f"**Quiz: {quiz_title}**\n\n"
        if quiz_description:
            info_text += f"{quiz_description}\n\n"
        info_text += f"To play this quiz, click the button below or use this link:\n[Play Quiz]({direct_quiz_link})"
        
        # Send the quiz information with the button
        await client.edit_message_text(
            message.chat.id, 
            status_msg.id,
            info_text,
            reply_markup=buttons,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await client.edit_message_text(message.chat.id, status_msg.id, f"Error processing QuizBot quiz: {e}")
    finally:
        await safe_disconnect(acc)

# Handle post limit callback queries
@Client.on_callback_query(filters.regex(r'^postlimit_'))
async def post_limit_callback(client: Client, callback_query):
    # Extract parameters from callback data
    params = callback_query.data.split('_')
    from_id = int(params[1])
    to_id = int(params[2])
    limit = int(params[3])
    
    # Calculate actual to_id based on limit
    actual_to_id = from_id + limit - 1
    if actual_to_id > to_id:
        actual_to_id = to_id
    
    await client.edit_message_text(
        callback_query.message.chat.id, 
        callback_query.message.id, 
        f"Processing {limit} posts..."
    )
    
    # Extract the URL from the replied message
    if callback_query.message.reply_to_message and callback_query.message.reply_to_message.text:
        url = callback_query.message.reply_to_message.text.strip()
        
        # Process the posts with the selected limit
        await process_posts(client, callback_query.message.reply_to_message, url, from_id, actual_to_id)
    else:
        await client.edit_message_text(
            callback_query.message.chat.id, 
            callback_query.message.id, 
            "Error: Could not find the original URL. Please send the link again."
        )

# Handle custom post limit request
@Client.on_callback_query(filters.regex(r'^postcustom_'))
async def post_custom_callback(client: Client, callback_query):
    # Extract parameters from callback data
    params = callback_query.data.split('_')
    from_id = int(params[1])
    to_id = int(params[2])
    
    total_posts = to_id - from_id + 1
    
    await client.edit_message_text(
        callback_query.message.chat.id, 
        callback_query.message.id, 
        f"Please enter how many posts you want to download (1-{total_posts}):"
    )
    
    # Set a flag in the database to indicate we're expecting a number input
    database.update_one(
        {'chat_id': callback_query.message.chat.id},
        {'$set': {
            'expecting_post_limit': True,
            'post_limit_data': {
                'from_id': from_id,
                'to_id': to_id,
                'url': callback_query.message.reply_to_message.text.strip() if callback_query.message.reply_to_message else None,
                'message_id': callback_query.message.reply_to_message.id if callback_query.message.reply_to_message else None
            }
        }},
        upsert=True
    )

# Handle cancel post download
@Client.on_callback_query(filters.regex(r'^cancelpost$'))
async def cancel_post_callback(client: Client, callback_query):
    await client.edit_message_text(
        callback_query.message.chat.id, 
        callback_query.message.id, 
        "Post download cancelled."
    )

# Post limit input handler (decorator yo'q — save() ichidan chaqiriladi)
async def handle_post_limit_input(client: Client, message: Message):
    # Check if we're expecting a post limit input from this user
    user_data = database.find_one({
        'chat_id': message.chat.id,
        'expecting_post_limit': True
    })
    
    if user_data and 'post_limit_data' in user_data:
        # Check if the message is a number
        try:
            limit = int(message.text.strip())
            from_id = user_data['post_limit_data']['from_id']
            to_id = user_data['post_limit_data']['to_id']
            url = user_data['post_limit_data']['url']
            original_message_id = user_data['post_limit_data']['message_id']
            
            total_posts = to_id - from_id + 1
            
            if 1 <= limit <= total_posts:
                # Reset the expecting flag
                database.update_one(
                    {'_id': user_data['_id']},
                    {'$unset': {'expecting_post_limit': "", 'post_limit_data': ""}}
                )
                
                # Calculate the actual to_id
                actual_to_id = from_id + limit - 1
                
                await client.send_message(
                    message.chat.id,
                    f"Processing {limit} posts...",
                    disable_web_page_preview=False
                )
                
                # Create a message object for the original message
                if original_message_id:
                    try:
                        original_message = await client.get_messages(message.chat.id, original_message_id)
                        if original_message and url:
                            await process_posts(client, original_message, url, from_id, actual_to_id)
                            return
                    except Exception as e:
                        pass
                
                # If we couldn't get the original message, use the current one
                await process_posts(client, message, url, from_id, actual_to_id)
                
            else:
                await client.send_message(
                    message.chat.id,
                    f"Please enter a valid number between 1 and {total_posts}."
                )
                
        except ValueError:
            # Check if this is a URL - if so, this might be a new request, not a response to our prompt
            if "https://t.me/" in message.text:
                # This is a new URL, not a response to our post limit prompt
                # Reset the expecting flag and process normally
                database.update_one(
                    {'_id': user_data['_id']},
                    {'$unset': {'expecting_post_limit': "", 'post_limit_data': ""}}
                )
                # Let the save handler process this new URL by not returning here
            else:
                await client.send_message(
                    message.chat.id,
                    "Please enter a valid number."
                )
                return
    
    # If we reach here, either it's not a post limit response or we processed it and allowed normal URL handling
    if "https://t.me/" not in message.text:
        # If not a Telegram URL and not a post limit response, ignore
        return
        
    # Otherwise, it's a new URL, let the save function handle it through the other handler
    # We don't call save() directly to avoid duplicate processing
        
async def handle_poll(client: Client, message: Message, poll):
    """
    Handle poll messages by recreating them with the same options.
    
    Args:
        client (Client): The client to send the poll with
        message (Message): The original message containing the request
        poll: The poll object to recreate
    """
    try:
        # Check if poll is None or doesn't have required attributes
        if poll is None:
            await client.send_message(
                message.chat.id,
                "Error: Unable to process poll - poll object is missing.",
                reply_to_message_id=message.id
            )
            return
            
        # Check if poll has question attribute
        if not hasattr(poll, 'question') or poll.question is None:
            await client.send_message(
                message.chat.id,
                "Error: Unable to process poll - poll question is missing.",
                reply_to_message_id=message.id
            )
            return
            
        # Check if poll has options attribute
        if not hasattr(poll, 'options') or poll.options is None:
            await client.send_message(
                message.chat.id,
                "Error: Unable to process poll - poll options are missing.",
                reply_to_message_id=message.id
            )
            return
        
        # Determine poll type
        is_quiz = hasattr(poll, 'type') and poll.type == PollType.QUIZ
        
        # Extract poll options
        options = [option.text for option in poll.options]
        
        # Handle Quiz polls specially
        correct_option_id = None
        if is_quiz and hasattr(poll, 'correct_option_id'):
            correct_option_id = poll.correct_option_id
        
        # Check for explanation in quizzes
        explanation = None
        explanation_entities = None
        if is_quiz and hasattr(poll, 'explanation'):
            explanation = poll.explanation
            if hasattr(poll, 'explanation_entities'):
                explanation_entities = poll.explanation_entities
        
        # Get poll properties with safe defaults
        is_anonymous = getattr(poll, 'is_anonymous', True)
        poll_type = getattr(poll, 'type', PollType.REGULAR)
        allows_multiple_answers = getattr(poll, 'allows_multiple_answers', False)
        
        # Recreate the poll
        await client.send_poll(
            chat_id=message.chat.id,
            question=poll.question,
            options=options,
            is_anonymous=is_anonymous,
            type=poll_type,
            allows_multiple_answers=allows_multiple_answers,
            correct_option_id=correct_option_id,
            explanation=explanation,
            explanation_entities=explanation_entities,
            reply_to_message_id=message.id
        )
        
    except Exception as e:
        # If we can't recreate the poll exactly, send a message with the poll details
        try:
            if hasattr(poll, 'question'):
                poll_info = f"**Poll: {poll.question}**\n\nOptions:\n"
                
                if hasattr(poll, 'options'):
                    for i, option in enumerate(poll.options):
                        voter_count = getattr(option, 'voter_count', 0)
                        poll_info += f"{i+1}. {option.text} - {voter_count} votes\n"
                    
                    if is_quiz and hasattr(poll, 'correct_option_id') and poll.correct_option_id is not None:
                        poll_info += f"\nCorrect answer: {poll.options[poll.correct_option_id].text}"
                    
                if is_quiz and hasattr(poll, 'explanation') and poll.explanation:
                    poll_info += f"\n\nExplanation: {poll.explanation}"
                
                await client.send_message(
                    message.chat.id,
                    poll_info,
                    reply_to_message_id=message.id,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await client.send_message(
                    message.chat.id,
                    f"Error processing poll: {str(e)}",
                    reply_to_message_id=message.id
                )
        except Exception as inner_e:
            await client.send_message(
                message.chat.id,
                f"Error processing poll: {str(inner_e)}",
                reply_to_message_id=message.id
            )

# Helper function to extract special entities from message
def extract_entities_by_type(msg, entity_type=None):
    """
    Extract entities of a specific type from a message.
    
    Args:
        msg: The message to extract entities from
        entity_type: The MessageEntityType to extract, or None for all entities
        
    Returns:
        A list of entity content with their types
    """
    entities = []
    
    # Get all message entities
    msg_entities = None
    if hasattr(msg, 'entities') and msg.entities:
        msg_entities = msg.entities
        text = msg.text
    elif hasattr(msg, 'caption_entities') and msg.caption_entities:
        msg_entities = msg.caption_entities
        text = msg.caption
    else:
        return entities
        
    # Process each entity
    for entity in msg_entities:
        if not hasattr(entity, 'type'):
            continue
            
        # Filter by type if requested
        if entity_type is not None and entity.type != entity_type:
            continue
            
        start = entity.offset
        end = entity.offset + entity.length
        
        if start < 0 or end > len(text):
            continue
            
        content = text[start:end]
        entity_info = {
            'type': entity.type,
            'content': content
        }
        
        # Add URL for text_link entity type
        if entity.type == MessageEntityType.TEXT_LINK and hasattr(entity, 'url'):
            entity_info['url'] = entity.url
            
        # Add user info for mention entity type
        if entity.type == MessageEntityType.MENTION:
            entity_info['mention'] = content
            
        # Add language for code blocks
        if entity.type == MessageEntityType.PRE and hasattr(entity, 'language'):
            entity_info['language'] = entity.language
            
        entities.append(entity_info)
        
    return entities
        
async def get_chat_info(client, chat_id):
    """
    Get detailed information about a chat using Raw API functions
    
    Args:
        client: The pyrogram client
        chat_id: Chat ID or username
        
    Returns:
        Dictionary with detailed chat information
    """
    try:
        # First try to get basic chat info through high-level API
        chat = await client.get_chat(chat_id)
        
        # Basic chat info
        chat_info = {
            "id": chat.id,
            "type": chat.type,
            "title": chat.title if hasattr(chat, "title") else None,
            "username": chat.username if hasattr(chat, "username") else None,
            "first_name": chat.first_name if hasattr(chat, "first_name") else None,
            "last_name": chat.last_name if hasattr(chat, "last_name") else None,
            "description": chat.description if hasattr(chat, "description") else None,
            "members_count": chat.members_count if hasattr(chat, "members_count") else None,
            "is_verified": chat.is_verified if hasattr(chat, "is_verified") else None,
            "is_restricted": chat.is_restricted if hasattr(chat, "is_restricted") else None,
            "is_scam": chat.is_scam if hasattr(chat, "is_scam") else None,
            "has_protected_content": chat.has_protected_content if hasattr(chat, "has_protected_content") else None,
            "invite_link": chat.invite_link if hasattr(chat, "invite_link") else None
        }
        
        # Convert chat ID to InputPeer for raw API calls
        peer = await client.resolve_peer(chat_id)
        
        # Get additional details based on chat type
        if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
            try:
                # Get full channel info
                if chat.type in [ChatType.SUPERGROUP, ChatType.CHANNEL]:
                    full_chat = await client.send(
                        functions.channels.GetFullChannel(
                            channel=peer
                        )
                    )
                    
                    # Extract additional information from full_chat
                    if hasattr(full_chat, "full_chat"):
                        fc = full_chat.full_chat
                        
                        # Add statistics if available
                        if hasattr(fc, "stats_dc"):
                            chat_info["stats_available"] = True
                            chat_info["stats_dc"] = fc.stats_dc
                            
                            # Try to get channel stats
                            try:
                                stats = await client.send(
                                    functions.stats.GetBroadcastStats(
                                        channel=peer
                                    )
                                )
                                
                                # Process stats data if available
                                if hasattr(stats, "period"):
                                    chat_info["stats"] = {
                                        "followers": stats.followers.current if hasattr(stats, "followers") and hasattr(stats.followers, "current") else None,
                                        "views_per_post": stats.views_per_post.current if hasattr(stats, "views_per_post") and hasattr(stats.views_per_post, "current") else None,
                                        "shares_per_post": stats.shares_per_post.current if hasattr(stats, "shares_per_post") and hasattr(stats.shares_per_post, "current") else None
                                    }
                            except Exception:
                                # Stats might not be available for all channels
                                pass
                        
                        # Add available about info
                        if hasattr(fc, "about") and fc.about:
                            chat_info["about"] = fc.about
                            
                        # Add online member count if available
                        if hasattr(fc, "online_count"):
                            chat_info["online_count"] = fc.online_count
                            
                        # Add linked chat info if available
                        if hasattr(fc, "linked_chat_id") and fc.linked_chat_id:
                            chat_info["linked_chat_id"] = fc.linked_chat_id
                            try:
                                linked_chat = await client.get_chat(fc.linked_chat_id)
                                if linked_chat:
                                    chat_info["linked_chat"] = {
                                        "id": linked_chat.id,
                                        "title": linked_chat.title if hasattr(linked_chat, "title") else None,
                                        "username": linked_chat.username if hasattr(linked_chat, "username") else None,
                                        "type": linked_chat.type
                                    }
                            except Exception:
                                # Linked chat might not be accessible
                                pass
                
                # For regular groups, use a different method
                elif chat.type == ChatType.GROUP:
                    full_chat = await client.send(
                        functions.messages.GetFullChat(
                            chat_id=chat.id
                        )
                    )
                    
                    # Extract additional information
                    if hasattr(full_chat, "full_chat"):
                        fc = full_chat.full_chat
                        
                        # Add participant count
                        if hasattr(fc, "participants_count"):
                            chat_info["participants_count"] = fc.participants_count
                            
                        # Add about info
                        if hasattr(fc, "about") and fc.about:
                            chat_info["about"] = fc.about
                            
                    
            except Exception as channel_error:
                chat_info["full_chat_error"] = str(channel_error)
                
        # For private chats/bots, get user status
        elif chat.type in [ChatType.PRIVATE, ChatType.BOT]:
            try:
                # Get user status
                users = await client.send(
                    functions.users.GetUsers(
                        id=[peer]
                    )
                )
                
                if users and len(users) > 0:
                    user = users[0]
                    
                    # Add user status
                    if hasattr(user, "status"):
                        if isinstance(user.status, types.UserStatusOnline):
                            chat_info["status"] = "online"
                        elif isinstance(user.status, types.UserStatusOffline):
                            chat_info["status"] = "offline"
                            chat_info["last_online"] = user.status.was_online
                        elif isinstance(user.status, types.UserStatusRecently):
                            chat_info["status"] = "recently"
                        elif isinstance(user.status, types.UserStatusLastWeek):
                            chat_info["status"] = "last_week"
                        elif isinstance(user.status, types.UserStatusLastMonth):
                            chat_info["status"] = "last_month"
                        else:
                            chat_info["status"] = "unknown"
                            
                    # Check if user is bot
                    if hasattr(user, "bot") and user.bot:
                        chat_info["is_bot"] = True
                        
                        # For bots, try to get bot info
                        try:
                            bot_info = await client.send(
                                functions.help.GetUserInfo(
                                    user_id=peer
                                )
                            )
                            
                            if bot_info and hasattr(bot_info, "bot_info"):
                                chat_info["bot_info"] = {
                                    "description": bot_info.bot_info.description if hasattr(bot_info.bot_info, "description") else None
                                }
                        except Exception:
                            # Bot full info might not be available
                            pass
                            
            except Exception as user_error:
                chat_info["user_info_error"] = str(user_error)
                
        return chat_info
        
    except Exception as e:
        return {"error": str(e)}
        
async def download_media_with_raw_api(client, message, file_path=None, progress_callback=None):
    """
    Download media using pyrogram's built-in download_media.
    Raw API approach removed — pyrofork high-level types do not expose
    raw attributes (file_access_hash, file_reference, dc_id).

    Args:
        client: The pyrogram client
        message: Message containing media
        file_path: Path to save the file (optional)
        progress_callback: Function to call with download progress (optional)

    Returns:
        Path to downloaded file or error dict
    """
    try:
        if not message.media:
            return {"error": "No media in message"}

        # Determine file save path from media attributes
        if not file_path:
            file_extension = ""
            if message.document and getattr(message.document, 'file_name', None):
                file_extension = os.path.splitext(message.document.file_name)[1]
            elif message.video:
                file_extension = ".mp4"
            elif message.audio:
                file_extension = ".mp3"
            elif message.photo:
                file_extension = ".jpg"
            file_path = f"{message.chat.id}_{message.id}{file_extension}"

        return await client.download_media(
            message, file_path,
            progress=progress_callback
        )

    except Exception as e:
        return {"error": str(e)}
        
async def download_media(client, message, msg_id, progress=None):
    """
    Download media from a Telegram message
    
    Args:
        client: The pyrogram client
        message: The message containing media
        msg_id: Message ID for progress tracking
        progress: Progress callback function
        
    Returns:
        Path to the downloaded file or error message
    """
    try:
        # Create downloads directory if it doesn't exist
        if not os.path.exists("downloads"):
            os.makedirs("downloads")
            
        # Create file path
        fname = f"downloads/{message.chat.id}_{message.id}"
        if hasattr(message, "document") and message.document and hasattr(message.document, "file_name") and message.document.file_name:
            # Get file extension from original file name
            ext = os.path.splitext(message.document.file_name)[1]
            if ext:
                fname += ext
        
        # First try to download using optimized raw API method
        try:
            result = await download_media_with_raw_api(
                client, 
                message, 
                file_path=fname,
                progress_callback=progress
            )
            
            # If successful, return the file path
            if isinstance(result, str):
                return result
                
            # If there's an error in raw API download, fall back to regular method
            if isinstance(result, dict) and "error" in result:
                print(f"Raw API download failed: {result['error']}, falling back to regular method")
        except Exception as raw_err:
            print(f"Raw API download failed with exception: {str(raw_err)}, falling back to regular method")
        
        # Fall back to regular download method
        return await client.download_media(
            message,
            file_name=fname,
            progress=progress
        )
        
    except Exception as e:
        return f"Error downloading media: {str(e)}"
        
        
