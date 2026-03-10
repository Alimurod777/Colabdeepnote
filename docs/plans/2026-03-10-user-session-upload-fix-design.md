# Upload via User Session — Fix Design

**Date:** 2026-03-10

## Muammo

Asosiy upload handler `client.send_*` (bot API) ishlatmoqda. Kerak: user o'z session stringi orqali bot bilan chatga yuborsin.

## Maqsad

User session (`uclient`) → `chat_id = bot.id` → faylni bot chatiga yuboradi.
Natija: Telegramda foydalanuvchi bot chatini ochganda fayl xuddi o'zi yuborgandek ko'rinadi.

## O'zgarishlar

### 1. `upload_via_user_session()` — kengaytirish

- `target_chat` parametri qo'shiladi (bot.id uzatiladi)
- Media type aware: `msg_type` asosida `send_video`, `send_audio`, `send_photo`, `send_document` tanlaydi
- Mavjud split + thumbnail + FloodWait logikasi saqlanadi

```python
async def upload_via_user_session(
    bot, user_id, file_path, caption="",
    progress_msg=None, target_chat=None, msg_type="Document",
    extra=None  # duration, width, height kabi
):
    # target_chat = bot.me.id (bot bilan private chat)
    chat_id = target_chat or user_id
    ...
    if msg_type == "Video":
        await uclient.send_video(chat_id=chat_id, video=part_path, ...)
    elif msg_type == "Audio":
        await uclient.send_audio(chat_id=chat_id, audio=part_path, ...)
    elif msg_type == "Photo":
        await uclient.send_photo(chat_id=chat_id, photo=part_path, ...)
    else:
        await uclient.send_document(chat_id=chat_id, document=part_path, ...)
```

### 2. Asosiy handler — `client.send_*` o'rniga `upload_via_user_session()`

Download qilingan `file` mavjud bo'lgandan keyin:

```python
bot_id = (await client.get_me()).id
await upload_via_user_session(
    bot=client,
    user_id=message.from_user.id,
    file_path=file,
    caption=first_caption,
    target_chat=bot_id,
    msg_type=msg_type,
    extra={"duration": ..., "width": ..., "height": ..., "thumb": ph_path}
)
```

Barcha `client.send_video(...)`, `client.send_document(...)`, `client.send_audio(...)`, `client.send_photo(...)` bloklari shu chaqiruv bilan almashtiriladi.

### 3. Bot ID keshlanadi

`bot.me.id` har safar API ga murojaat qilmaslik uchun modul darajasida bir marta olinadi:

```python
_bot_id = None

async def get_bot_id(client):
    global _bot_id
    if not _bot_id:
        me = await client.get_me()
        _bot_id = me.id
    return _bot_id
```
