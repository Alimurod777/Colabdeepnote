# User Session Upload Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fayllarni bot API o'rniga user session string orqali to'g'ridan-to'g'ri user ↔ bot chatiga yuborish.

**Architecture:** `upload_via_user_session()` funksiyasi kengaytiriladi — `target_chat`, `msg_type`, `extra` parametrlari qo'shiladi va media type aware qilinadi. Asosiy handler (1736-1944 qatorlar) dagi barcha `client.send_*` bloklari ushbu funksiya chaqiruvi bilan almashtiriladi. Bot ID bir marta keshlanadi.

**Tech Stack:** pyrofork, user session string (uclient), asyncio, FloodWait handling

---

### Task 1: `upload_via_user_session()` — kengaytirish

**Files:**
- Modify: `TechVJ/save.py` (lines 168-252 — mavjud funksiya)

**Kontekst:** Hozirgi funksiya faqat `send_document()` ishlatadi va `chat_id=user_id` ga yuboradi. Kerak: bot ID ga, media type bo'yicha to'g'ri method bilan yuborish.

**Step 1: Bot ID keshi uchun modul darajasida o'zgaruvchi qo'shing**

`save.py` faylining imports qismidan keyin (STATIC_FFMPEG_PATH dan oldin) qo'shing:

```python
_bot_id_cache = None

async def _get_bot_id(client):
    """Bot ID ni bir marta olib keshlaydi."""
    global _bot_id_cache
    if _bot_id_cache is None:
        me = await client.get_me()
        _bot_id_cache = me.id
    return _bot_id_cache
```

**Step 2: Mavjud `upload_via_user_session()` funksiyasini quyidagi versiya bilan to'liq almashtiring**

(168-252 qatorlar o'rniga)

```python
async def upload_via_user_session(
    bot,
    user_id: int,
    file_path: str,
    caption: str = "",
    progress_msg=None,
    target_chat=None,
    msg_type: str = "Document",
    extra: dict = None,
):
    """
    Faylni user session orqali target_chat ga yuboradi.
    target_chat = bot.id bo'lsa, user va bot orasidagi chatga yuboriladi.
    Bot API emas — userbot client (uclient) ishlatiladi.
    FloodWait avtomatik boshqariladi.
    """
    from database.db import database as _db
    from config import API_ID, API_HASH

    if extra is None:
        extra = {}

    user_data = _db.find_one({"chat_id": user_id})
    if not user_data or not user_data.get("session"):
        await bot.send_message(user_id, "**Avval /login yoki /qrlogin qiling.**")
        return False

    session_string = user_data["session"]

    # Target chat: bot bilan private chat yoki fallback user_id
    chat_id = target_chat or user_id

    # Thumbnail faqat document/video uchun
    thumb = None
    if msg_type in ("Document", "Video", "Audio"):
        thumb = extra.get("thumb") or await make_thumbnail(file_path)

    parts = await split_file(file_path)

    uclient = Client(
        f"sessions/user_{user_id}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
    )

    success = True
    parts_to_cleanup = [p for p in parts if p != file_path]

    try:
        try:
            await uclient.connect()
        except Exception as conn_err:
            await bot.send_message(user_id, f"**Ulanish xatosi:** `{conn_err}`")
            return False

        for i, part_path in enumerate(parts):
            part_caption = caption
            if len(parts) > 1:
                part_caption = f"{caption}\n**Part {i+1}/{len(parts)}**"

            uploaded = False
            for attempt in range(5):
                try:
                    if msg_type == "Video":
                        await uclient.send_video(
                            chat_id=chat_id,
                            video=part_path,
                            caption=part_caption,
                            duration=extra.get("duration"),
                            width=extra.get("width"),
                            height=extra.get("height"),
                            thumb=thumb,
                        )
                    elif msg_type == "Audio":
                        await uclient.send_audio(
                            chat_id=chat_id,
                            audio=part_path,
                            caption=part_caption,
                            duration=extra.get("duration"),
                            performer=extra.get("performer"),
                            title=extra.get("title"),
                            thumb=thumb,
                        )
                    elif msg_type == "Voice":
                        await uclient.send_voice(
                            chat_id=chat_id,
                            voice=part_path,
                            caption=part_caption,
                            duration=extra.get("duration"),
                        )
                    elif msg_type == "Photo":
                        await uclient.send_photo(
                            chat_id=chat_id,
                            photo=part_path,
                            caption=part_caption,
                        )
                    elif msg_type == "Animation":
                        await uclient.send_animation(
                            chat_id=chat_id,
                            animation=part_path,
                            caption=part_caption,
                        )
                    elif msg_type == "VideoNote":
                        await uclient.send_video_note(
                            chat_id=chat_id,
                            video_note=part_path,
                            duration=extra.get("duration"),
                            length=extra.get("length"),
                        )
                    elif msg_type == "Sticker":
                        await uclient.send_sticker(
                            chat_id=chat_id,
                            sticker=part_path,
                        )
                    else:
                        # Default: Document
                        await uclient.send_document(
                            chat_id=chat_id,
                            document=part_path,
                            caption=part_caption,
                            thumb=thumb,
                            force_document=False,
                        )
                    uploaded = True
                    break
                except FloodWait as e:
                    wait = e.value
                    if progress_msg:
                        try:
                            await progress_msg.edit(f"**FloodWait:** {wait} soniya kutilmoqda...")
                        except Exception:
                            pass
                    await asyncio.sleep(wait)
                except Exception as upload_err:
                    await bot.send_message(user_id, f"**Upload xatosi:** `{upload_err}`")
                    success = False
                    break

            if not uploaded and success:
                await bot.send_message(user_id, "**Upload: FloodWait — maksimal urinishlar tugadi.**")
                success = False

            if not success:
                break

        # Split qilingan temp fayllarni tozalash
        for part_path in parts_to_cleanup:
            try:
                os.remove(part_path)
            except Exception:
                pass

    finally:
        try:
            await uclient.disconnect()
        except Exception:
            pass
        # Funksiya tomonidan yaratilgan thumbnail ni tozalash
        if thumb and thumb != file_path and not extra.get("thumb") and os.path.exists(thumb):
            try:
                os.remove(thumb)
            except Exception:
                pass

    return success
```

**Step 3: Syntax check**

```bash
python -m py_compile TechVJ/save.py && echo "OK"
```
Run from: `C:/Users/User/loyiha/new deepnote/new`
Expected: `OK`

---

### Task 2: `_get_bot_id()` ni `save.py` ga qo'shish

**Files:**
- Modify: `TechVJ/save.py` (STATIC_FFMPEG_PATH dan oldin)

**Step 1: `_bot_id_cache` va `_get_bot_id()` ni qo'shing**

`STATIC_FFMPEG_PATH = ...` qatoridan oldin quyidagini qo'shing:

```python
_bot_id_cache = None


async def _get_bot_id(client):
    """Bot ID ni bir marta olib keshlaydi."""
    global _bot_id_cache
    if _bot_id_cache is None:
        me = await client.get_me()
        _bot_id_cache = me.id
    return _bot_id_cache
```

**Step 2: Syntax check**

```bash
python -m py_compile TechVJ/save.py && echo "OK"
```
Expected: `OK`

---

### Task 3: Asosiy handler — `client.send_*` bloklarini `upload_via_user_session()` bilan almashtirish

**Files:**
- Modify: `TechVJ/save.py` (lines 1736-1944)

**Kontekst:** Bu qatorlarda `client.send_video(...)`, `client.send_document(...)` va h.k. ishlatilmoqda. Ularni `upload_via_user_session()` chaqiruvi bilan almashtirish kerak.

**Step 1: Download tugagandan keyin bot_id olish qo'shing**

`file` o'zgaruvchisi mavjud bo'lgan joydan keyin (1700-1704 qatorlar atrofida), `chat` o'zgaruvchisi e'lon qilingan joyda:

```python
# Bot ID olish (user session upload uchun)
bot_id = await _get_bot_id(client)
```

Buni `upstatus` task yaratilgan qatordan keyin qo'shing.

**Step 2: `Document` msg_type blokini almashtiring (1736-1815)**

O'chirish kerak bo'lgan blok (`if "Document" == msg_type:` dan `elif "Video" == msg_type:` gacha).

O'rniga:

```python
if "Document" == msg_type:
    # video extension bo'lsa Video sifatida yuborish
    if file.endswith(('.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm')):
        doc_msg_type = "Video"
        extra = {}
        if hasattr(msg, 'document') and msg.document:
            for attr in msg.document.attributes:
                if hasattr(attr, 'duration'):
                    extra["duration"] = attr.duration
                if hasattr(attr, 'width'):
                    extra["width"] = attr.width
                if hasattr(attr, 'height'):
                    extra["height"] = attr.height
    elif file.endswith('.ogg'):
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
    )
    if second_caption:
        await client.send_message(message.chat.id, second_caption, reply_to_message_id=message.id)
```

**Step 3: `Video` msg_type blokini almashtiring (1817-1835)**

O'chirish kerak bo'lgan blok (`elif "Video" == msg_type:` dan `elif "VideoNote" == msg_type:` gacha).

O'rniga:

```python
elif "Video" == msg_type:
    extra = {
        "duration": msg.video.duration if hasattr(msg.video, 'duration') else None,
        "width": msg.video.width if hasattr(msg.video, 'width') else None,
        "height": msg.video.height if hasattr(msg.video, 'height') else None,
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
    )
    if second_caption:
        await client.send_message(message.chat.id, second_caption, reply_to_message_id=message.id)
```

**Step 4: `VideoNote` msg_type blokini almashtiring (1837-1845)**

O'rniga:

```python
elif "VideoNote" == msg_type:
    extra = {
        "duration": msg.video_note.duration if hasattr(msg.video_note, 'duration') else None,
        "length": msg.video_note.length if hasattr(msg.video_note, 'length') else None,
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
    )
```

**Step 5: `Voice` msg_type blokini almashtiring (1847-1861)**

O'rniga:

```python
elif "Voice" == msg_type:
    extra = {
        "duration": msg.voice.duration if hasattr(msg.voice, 'duration') else None,
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
    )
    if second_caption:
        await client.send_message(message.chat.id, second_caption, reply_to_message_id=message.id)
```

**Step 6: `Audio` msg_type blokini almashtiring (1863-1887)**

O'rniga:

```python
elif "Audio" == msg_type:
    extra = {
        "duration": msg.audio.duration if hasattr(msg.audio, 'duration') else None,
        "performer": msg.audio.performer if hasattr(msg.audio, 'performer') else None,
        "title": msg.audio.title if hasattr(msg.audio, 'title') else None,
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
    )
    if second_caption:
        await client.send_message(message.chat.id, second_caption, reply_to_message_id=message.id)
```

**Step 7: `Photo` msg_type blokini almashtiring (1889-1900)**

O'rniga:

```python
elif "Photo" == msg_type:
    await upload_via_user_session(
        bot=client,
        user_id=message.from_user.id,
        file_path=file,
        caption=first_caption,
        progress_msg=smsg,
        target_chat=bot_id,
        msg_type="Photo",
    )
    if second_caption:
        await client.send_message(message.chat.id, second_caption, reply_to_message_id=message.id)
```

**Step 8: `Animation` msg_type blokini almashtiring (1902-1912)**

O'rniga:

```python
elif "Animation" == msg_type:
    await upload_via_user_session(
        bot=client,
        user_id=message.from_user.id,
        file_path=file,
        caption=first_caption,
        progress_msg=smsg,
        target_chat=bot_id,
        msg_type="Animation",
    )
    if second_caption:
        await client.send_message(message.chat.id, second_caption, reply_to_message_id=message.id)
```

**Step 9: `Sticker` msg_type blokini almashtiring (1914-1918)**

O'rniga:

```python
elif "Sticker" == msg_type:
    await upload_via_user_session(
        bot=client,
        user_id=message.from_user.id,
        file_path=file,
        caption=first_caption,
        progress_msg=smsg,
        target_chat=bot_id,
        msg_type="Sticker",
    )
```

**Step 10: `else` blokini almashtiring (1933-1944)**

O'rniga:

```python
else:
    await upload_via_user_session(
        bot=client,
        user_id=message.from_user.id,
        file_path=file,
        caption=first_caption,
        progress_msg=smsg,
        target_chat=bot_id,
        msg_type="Document",
    )
    if second_caption:
        await client.send_message(message.chat.id, second_caption, reply_to_message_id=message.id)
```

**Step 11: Syntax check**

```bash
python -m py_compile TechVJ/save.py && echo "OK"
```
Expected: `OK`

---

### Task 4: Yakuniy tekshiruv

**Step 1: Barcha fayllar syntax OK**

```bash
cd "C:/Users/User/loyiha/new deepnote/new"
python -m py_compile config.py && echo "config OK"
python -m py_compile database/db.py && echo "db OK"
python -m py_compile TechVJ/generate.py && echo "generate OK"
python -m py_compile TechVJ/save.py && echo "save OK"
```
Expected: barcha `OK`

**Step 2: `upload_via_user_session` signature tekshiruv**

```bash
python -c "
import ast, sys
with open('TechVJ/save.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.AsyncFunctionDef) and node.name == 'upload_via_user_session':
        args = [a.arg for a in node.args.args]
        print('Args:', args)
        assert 'target_chat' in args, 'target_chat parametri yo\\'q!'
        assert 'msg_type' in args, 'msg_type parametri yo\\'q!'
        assert 'extra' in args, 'extra parametri yo\\'q!'
        print('OK - barcha parametrlar mavjud')
"
```
Expected: `OK - barcha parametrlar mavjud`
