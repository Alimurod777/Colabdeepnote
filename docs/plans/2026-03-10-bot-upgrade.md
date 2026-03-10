# Bot Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** VJ-Save-Restricted-Content botni pyrofork ga o'tkazish, Python 3.10-3.13 mosligi, ffmpeg split, auto thumbnail, user session upload, /qrlogin, MongoDB fallback va caching qo'shish.

**Architecture:** Modullar bo'yicha yangilash — mavjud fayl strukturasi saqlanadi, har bir funksiya o'z fayliga qo'shiladi. MongoDB ulanmasa local JSON fallback, in-memory cache bilan DB so'rovlari kamaytiriladi.

**Tech Stack:** pyrofork 2.3.45, pymongo, ffmpeg (system + static binary), Python 3.10-3.13, Google Colab ipynb

---

### Task 1: `config.py` — Default qiymatlarni bo'shatish

**Files:**
- Modify: `config.py`

**Step 1: Hozirgi faylni o'qib chiqing**

```
config.py ni o'qing — hozirda hardcoded token/api_id/api_hash/db_uri bor
```

**Step 2: Yangi config.py yozing**

```python
import os

# Bot token @Botfather
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Your API ID from my.telegram.org
API_ID = int(os.environ.get("API_ID", "0"))

# Your API Hash from my.telegram.org
API_HASH = os.environ.get("API_HASH", "")

# Database — bo'sh qolsa local JSON fallback ishlatiladi
DB_URI = os.environ.get("DB_URI", "")
```

**Step 3: Tekshiring**

```bash
python3 -c "from config import BOT_TOKEN, API_ID, API_HASH, DB_URI; print('OK')"
```
Expected: `OK`

**Step 4: Commit**

```bash
git add config.py
git commit -m "config: remove hardcoded credentials, use env vars only"
```

---

### Task 2: `database/db.py` — MongoDB fallback + in-memory cache

**Files:**
- Modify: `database/db.py`

**Step 1: Yangi db.py yozing**

```python
import json
import os
from config import DB_URI

_cache = {}  # in-memory cache: {chat_id: user_data}
_use_mongo = False
_db = None

def _init():
    global _use_mongo, _db
    if not DB_URI:
        return
    try:
        from pymongo import MongoClient
        client = MongoClient(DB_URI, serverSelectionTimeoutMS=5000)
        client.server_info()  # ulanishni tekshirish
        _db = client.userdb.sessions
        _use_mongo = True
    except Exception as e:
        print(f"MongoDB ulanmadi, local JSON ishlatiladi: {e}")

_LOCAL_FILE = "sessions/local_db.json"

def _load_local():
    if not os.path.exists(_LOCAL_FILE):
        return []
    with open(_LOCAL_FILE, "r") as f:
        return json.load(f)

def _save_local(data):
    os.makedirs("sessions", exist_ok=True)
    with open(_LOCAL_FILE, "w") as f:
        json.dump(data, f)

def find_one(query):
    key = query.get("chat_id")
    if key and key in _cache:
        return _cache[key]
    if _use_mongo:
        result = _db.find_one(query)
        if result and key:
            _cache[key] = result
        return result
    # local fallback
    records = _load_local()
    for r in records:
        if all(r.get(k) == v for k, v in query.items()):
            if key:
                _cache[key] = r
            return r
    return None

def insert_one(doc):
    key = doc.get("chat_id")
    # Agar allaqachon mavjud bo'lsa, qayta qo'shmasin
    existing = find_one({"chat_id": key}) if key else None
    if existing:
        return
    if _use_mongo:
        _db.insert_one(doc)
    else:
        records = _load_local()
        records.append(doc)
        _save_local(records)
    if key:
        _cache[key] = doc

def update_one(filter_query, update):
    key = filter_query.get("chat_id") or (
        _cache_key_by_id(filter_query.get("_id")) if filter_query.get("_id") else None
    )
    set_data = update.get("$set", {})
    if _use_mongo:
        _db.update_one(filter_query, update)
    else:
        records = _load_local()
        for r in records:
            if all(r.get(k) == v for k, v in filter_query.items()):
                r.update(set_data)
        _save_local(records)
    # Cache yangilash
    if key and key in _cache:
        _cache[key].update(set_data)

def _cache_key_by_id(doc_id):
    for k, v in _cache.items():
        if v.get("_id") == doc_id:
            return k
    return None

# Modul import paytida ulanishni boshlash
_init()

# database.database interfeys sifatida — mavjud kod o'zgarmasin
database = type("DB", (), {
    "find_one": staticmethod(find_one),
    "insert_one": staticmethod(insert_one),
    "update_one": staticmethod(update_one),
})()
```

**Step 2: Tekshiring**

```bash
python3 -c "from database.db import database; database.insert_one({'chat_id': 999}); r = database.find_one({'chat_id': 999}); print('OK' if r else 'FAIL')"
```
Expected: `OK` (MongoDB bo'lmasa ham local JSON da ishlaydi)

**Step 3: Commit**

```bash
git add database/db.py
git commit -m "db: add MongoDB fallback to local JSON + in-memory cache"
```

---

### Task 3: `TechVJ/generate.py` — `/qrlogin` buyrug'ini qo'shish

**Files:**
- Modify: `TechVJ/generate.py`

**Step 1: Hozirgi generate.py ni o'qing (login/logout handlers mavjud)**

**Step 2: Faylning oxiriga `/qrlogin` handler qo'shing**

```python
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import SessionPasswordNeeded
from config import API_ID, API_HASH
from database.db import database


@Client.on_message(filters.private & ~filters.forwarded & filters.command(["qrlogin"]))
async def qr_login(bot: Client, message: Message):
    user_id = message.from_user.id

    database.insert_one({"chat_id": user_id})
    user_data = database.find_one({"chat_id": user_id})

    if user_data and user_data.get("logged_in"):
        await message.reply("**Siz allaqachon login qilgansiz.**\nQayta login uchun avval /logout qiling.")
        return

    status_msg = await message.reply("**QR kod tayyorlanmoqda...**")

    session_path = f"sessions/temp_qr_{user_id}"
    os.makedirs("sessions", exist_ok=True)
    client = Client(session_path, API_ID, API_HASH)

    try:
        await client.connect()

        # QR login loop
        qr_login_obj = await client.qr_login()

        # QR kodini rasm sifatida yuborish
        import qrcode
        import io
        qr_img = qrcode.make(qr_login_obj.url)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)

        await status_msg.delete()
        qr_msg = await bot.send_photo(
            chat_id=user_id,
            photo=buf,
            caption=(
                "**QR kod orqali login:**\n\n"
                "1. Telegramni oching (boshqa qurilmada)\n"
                "2. Settings → Devices → Scan QR Code\n"
                "3. Ushbu QR kodni skanlang\n\n"
                "_QR kod 30 soniyada yangilanadi_"
            )
        )

        # Skan qilinishini kutish (30 soniya timeout)
        try:
            await asyncio.wait_for(qr_login_obj.wait(), timeout=30)
        except asyncio.TimeoutError:
            # QR ni yangilash
            await qr_login_obj.recreate()
            qr_img2 = qrcode.make(qr_login_obj.url)
            buf2 = io.BytesIO()
            qr_img2.save(buf2, format="PNG")
            buf2.seek(0)
            await qr_msg.delete()
            qr_msg = await bot.send_photo(
                chat_id=user_id,
                photo=buf2,
                caption="**Yangilangan QR kod** (30 soniya):\n\nTelegramda Scan QR Code bosing."
            )
            await asyncio.wait_for(qr_login_obj.wait(), timeout=30)

    except SessionPasswordNeeded:
        pwd_msg = await bot.ask(
            user_id,
            "**2FA parol kerak. Iltimos parolni kiriting:**\n\n/cancel — bekor qilish",
            filters=filters.text,
            timeout=300
        )
        if pwd_msg.text == "/cancel":
            await pwd_msg.reply("**Bekor qilindi.**")
            return
        try:
            await client.check_password(pwd_msg.text)
        except Exception:
            await pwd_msg.reply("**Noto'g'ri parol.**")
            return
    except asyncio.TimeoutError:
        await bot.send_message(user_id, "**QR kod muddati tugadi. /qrlogin ni qayta yuboring.**")
        return
    except Exception as e:
        await bot.send_message(user_id, f"**Xato:** `{e}`")
        return
    finally:
        try:
            await qr_msg.delete()
        except Exception:
            pass

    # Session string olish va saqlash
    string_session = await client.export_session_string()
    await client.disconnect()

    if len(string_session) < 351:
        await bot.send_message(user_id, "**Noto'g'ri session string. Qayta urinib ko'ring.**")
        return

    data = {"session": string_session, "logged_in": True}
    database.update_one({"chat_id": user_id}, {"$set": data})

    # Temp fayl tozalash
    try:
        if os.path.exists(f"{session_path}.session"):
            os.remove(f"{session_path}.session")
    except Exception:
        pass

    await bot.send_message(user_id, "**QR orqali login muvaffaqiyatli!**\n\nAgar xato chiqsa /logout va /qrlogin ni qayta ishlating.")
```

**Step 3: requirements.txt ga qrcode qo'shing**

```
qrcode[pil]==7.4.2
```

**Step 4: Tekshiring (import)**

```bash
python3 -c "from TechVJ.generate import qr_login; print('OK')"
```
Expected: `OK`

**Step 5: Commit**

```bash
git add TechVJ/generate.py requirements.txt
git commit -m "feat: add /qrlogin command with QR code image"
```

---

### Task 4: Media split funksiyasi — `TechVJ/save.py` ga qo'shish

**Files:**
- Modify: `TechVJ/save.py` (faylning boshiga helper funksiyalar qo'shiladi)

**Step 1: ffmpeg yo'lini topuvchi helper**

`save.py` faylining import qismidan keyin quyidagini qo'shing:

```python
import subprocess
import shutil

STATIC_FFMPEG_PATH = os.path.join(os.path.dirname(__file__), "..", "staticfiles", "ffmpeg")

def get_ffmpeg():
    """ffmpeg binary yo'lini qaytaradi. System ffmpeg bo'lmasa static ishlatadi."""
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    if os.path.exists(STATIC_FFMPEG_PATH) and os.access(STATIC_FFMPEG_PATH, os.X_OK):
        return STATIC_FFMPEG_PATH
    return None

TWO_GB = 2 * 1024 * 1024 * 1024  # 2GB bytes

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
        # ffmpeg yo'q — faylni oddiy binary split
        return await _binary_split(file_path, chunk_size_bytes)

    ext = os.path.splitext(file_path)[1]
    base = os.path.splitext(file_path)[0]

    # Video/audio uchun segment duration hisoblash
    # Avval duration olamiz
    probe = subprocess.run(
        [ffmpeg.replace("ffmpeg", "ffprobe") if "ffmpeg" in ffmpeg else "ffprobe",
         "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", file_path],
        capture_output=True, text=True
    )

    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}
    audio_exts = {".mp3", ".m4a", ".ogg", ".flac", ".wav"}

    if ext.lower() in video_exts or ext.lower() in audio_exts:
        try:
            duration = float(probe.stdout.strip())
            # Segment soni = ceil(fayl_hajmi / chunk_hajmi)
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

            parts = sorted([
                f for f in os.listdir(os.path.dirname(file_path) or ".")
                if f.startswith(os.path.basename(base) + "_part") and f.endswith(ext)
            ])
            if parts:
                dir_path = os.path.dirname(file_path) or "."
                return [os.path.join(dir_path, p) for p in parts]
        except Exception:
            pass

    # Fallback: binary split
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
```

**Step 2: Tekshiring**

```bash
python3 -c "from TechVJ.save import get_ffmpeg, split_file; print('ffmpeg:', get_ffmpeg())"
```
Expected: `ffmpeg: ffmpeg` yoki `ffmpeg: None`

**Step 3: Commit**

```bash
git add TechVJ/save.py
git commit -m "feat: add ffmpeg-based file splitter for 2GB+ media"
```

---

### Task 5: Auto thumbnail funksiyasi — `TechVJ/save.py`

**Step 1: `save.py` ga thumbnail helper qo'shing**

```python
async def make_thumbnail(file_path: str) -> str | None:
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
```

**Step 2: Tekshiring**

```bash
python3 -c "from TechVJ.save import make_thumbnail; print('OK')"
```
Expected: `OK`

**Step 3: Commit**

```bash
git add TechVJ/save.py
git commit -m "feat: add auto thumbnail generation from video first frame"
```

---

### Task 6: User session orqali upload + FloodWait — `TechVJ/save.py`

**Step 1: Upload helper funksiyasini qo'shing**

Mavjud upload logikasini topib, quyidagi `upload_via_user_session` funksiyasini qo'shing yoki mavjud upload qismini shu pattern bilan yangilang:

```python
async def upload_via_user_session(bot: Client, user_id: int, file_path: str, caption: str = "", progress_msg=None):
    """
    Faylni user session orqali bot va user orasidagi chatga yuboradi.
    Bot API emas — userbot client ishlatiladi.
    FloodWait avtomatik boshqariladi.
    """
    from database.db import database

    user_data = database.find_one({"chat_id": user_id})
    if not user_data or not user_data.get("session"):
        await bot.send_message(user_id, "**Avval /login yoki /qrlogin qiling.**")
        return False

    session_string = user_data["session"]

    # Thumbnail
    thumb = await make_thumbnail(file_path)

    # Fayl hajmini tekshirish — split kerakmi?
    parts = await split_file(file_path)

    # Userbot client
    uclient = Client(
        f"sessions/user_{user_id}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string
    )

    try:
        await uclient.connect()

        for i, part_path in enumerate(parts):
            part_caption = caption
            if len(parts) > 1:
                part_caption = f"{caption}\n**Part {i+1}/{len(parts)}**"

            # FloodWait bilan qayta urinish
            for attempt in range(5):
                try:
                    await uclient.send_document(
                        chat_id=user_id,
                        document=part_path,
                        caption=part_caption,
                        thumb=thumb,
                        force_document=False
                    )
                    break
                except FloodWait as e:
                    wait = e.value
                    if progress_msg:
                        try:
                            await progress_msg.edit(f"**FloodWait:** {wait} soniya kutilmoqda...")
                        except Exception:
                            pass
                    await asyncio.sleep(wait)
                except Exception as e:
                    await bot.send_message(user_id, f"**Upload xatosi:** `{e}`")
                    break

            # Agar split qilingan qismlar bo'lsa va original fayl emas — temp ni o'chir
            if len(parts) > 1 and part_path != file_path:
                try:
                    os.remove(part_path)
                except Exception:
                    pass
    finally:
        try:
            await uclient.disconnect()
        except Exception:
            pass
        # Thumbnail temp faylni o'chirish
        if thumb and thumb != file_path and os.path.exists(thumb):
            try:
                os.remove(thumb)
            except Exception:
                pass

    return True
```

**Step 2: Mavjud upload qismlarida `FloodWait` import ni tekshiring**

`save.py` boshida `FloodWait` import mavjud — agar yo'q bo'lsa qo'shing:
```python
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, ...
```
(allaqachon mavjud — tekshiring)

**Step 3: Tekshiring**

```bash
python3 -c "from TechVJ.save import upload_via_user_session; print('OK')"
```
Expected: `OK`

**Step 4: Commit**

```bash
git add TechVJ/save.py
git commit -m "feat: upload via user session with FloodWait handling and auto-split"
```

---

### Task 7: `staticfiles/` — Static ffmpeg binary

**Files:**
- Create: `staticfiles/.gitkeep`

**Step 1: Papka yarating**

```bash
mkdir -p staticfiles
touch staticfiles/.gitkeep
```

**Step 2: README yozing (foydalanuvchi uchun)**

```bash
echo "# Static FFmpeg
Linux uchun static ffmpeg binary shu yerga joylang:
- staticfiles/ffmpeg
- staticfiles/ffprobe

Yuklab olish: https://johnvansickle.com/ffmpeg/
chmod +x staticfiles/ffmpeg staticfiles/ffprobe" > staticfiles/README.txt
```

**Step 3: `.gitignore` ga binary qo'shing**

```bash
echo "staticfiles/ffmpeg" >> .gitignore
echo "staticfiles/ffprobe" >> .gitignore
```

**Step 4: Commit**

```bash
git add staticfiles/.gitkeep staticfiles/README.txt .gitignore
git commit -m "chore: add staticfiles dir for static ffmpeg binary"
```

---

### Task 8: `requirements.txt` — Python 3.10-3.13 mosligi

**Files:**
- Modify: `requirements.txt`

**Step 1: Yangilang**

```
pyrofork==2.3.45
tgcrypto==1.2.5
pymongo[srv]==4.6.1
qrcode[pil]==7.4.2
Pillow>=10.0.0
python-decouple==3.8
```

**Olib tashlang:**
- `Flask`, `gunicorn`, `Jinja2`, `werkzeug`, `itsdangerous` — faqat `app.py` uchun, Colab da kerak emas (ixtiyoriy, foydalanuvchi bilan kelishib)

**Step 2: Tekshiring**

```bash
pip install -r requirements.txt --dry-run 2>&1 | tail -5
```

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: update requirements for Python 3.10-3.13 compatibility"
```

---

### Task 9: `WOODcraft/VJ-WOODcraft-Colab.ipynb` — Yangilash

**Files:**
- Modify: `WOODcraft/VJ-WOODcraft-Colab.ipynb`

**Step 1: Notebook ni 3 asosiy hujayra bilan yangilang**

**Hujayra 1 — Setup:**
```python
import os
import shutil
import sys
from IPython.display import clear_output

# GitHub repo
GITHUB_URL = "https://github.com/Ali777666/VJ-Save-Restricted-Content-Colab"  #@param {type:"string"}

base_dir = './repo'

def clone_or_update_repo(repo_url, base_directory):
    repo_name = os.path.basename(repo_url).replace('.git', '')
    project_dir = os.path.join(base_directory, repo_name)
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)
    os.system(f"git clone {repo_url} {project_dir}")
    return project_dir

project_dir = clone_or_update_repo(GITHUB_URL, base_dir)
os.chdir(project_dir)

# Python versiya tekshiruvi
version = sys.version_info
assert (3, 10) <= (version.major, version.minor) <= (3, 13), \
    f"Python 3.10-3.13 kerak, sizda: {version.major}.{version.minor}"
print(f"✅ Python {version.major}.{version.minor} — OK")

# Dependencies
os.system("pip install -r requirements.txt -q")
print("✅ Dependencies o'rnatildi")

# FFmpeg
os.system("apt-get install -y ffmpeg -qq")
print("✅ FFmpeg o'rnatildi")

# Static ffmpeg (zaxira)
STATIC_FFMPEG_URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
if not os.path.exists("staticfiles/ffmpeg"):
    os.makedirs("staticfiles", exist_ok=True)
    os.system(f"wget -q {STATIC_FFMPEG_URL} -O /tmp/ffmpeg.tar.xz")
    os.system("tar -xf /tmp/ffmpeg.tar.xz -C /tmp/")
    import glob
    bins = glob.glob("/tmp/ffmpeg-*-amd64-static/ffmpeg")
    if bins:
        shutil.copy(bins[0], "staticfiles/ffmpeg")
        os.chmod("staticfiles/ffmpeg", 0o755)
        print("✅ Static ffmpeg saqlandi")

clear_output()
print("✅ Setup tugadi — Hujayra 2 ga o'ting")
```

**Hujayra 2 — Config (foydalanuvchi to'ldiradi):**
```python
import os

#@markdown ## ⚙️ Bot konfiguratsiyasi
#@markdown ---

#@markdown **API ID** — my.telegram.org dan oling
API_ID = ""  #@param {type:"string"}
os.environ['API_ID'] = API_ID

#@markdown **API HASH** — my.telegram.org dan oling
API_HASH = ""  #@param {type:"string"}
os.environ['API_HASH'] = API_HASH

#@markdown **BOT TOKEN** — @BotFather dan oling
BOT_TOKEN = ""  #@param {type:"string"}
os.environ['BOT_TOKEN'] = BOT_TOKEN

#@markdown **MongoDB URI** — bo'sh qolsa local JSON ishlatiladi
DB_URI = ""  #@param {type:"string"}
os.environ['DB_URI'] = DB_URI

if not DB_URI:
    print("⚠️  DB_URI kiritilmadi — local JSON fallback ishlatiladi (sessions/local_db.json)")
else:
    print("✅ MongoDB URI saqlandi")

print("✅ Config tayyor — Hujayra 3 ni ishga tushiring")
```

**Hujayra 3 — Run:**
```python
import os
os.system("python3 bot.py")
```

**Step 2: Commit**

```bash
git add WOODcraft/VJ-WOODcraft-Colab.ipynb
git commit -m "colab: update notebook with 3-cell structure, static ffmpeg, Python 3.10-3.13 check"
```

---

### Task 10: Yakuniy tekshiruv

**Step 1: Import zanjirini tekshiring**

```bash
python3 -c "
from config import BOT_TOKEN, API_ID, API_HASH, DB_URI
from database.db import database
from TechVJ.generate import qr_login
from TechVJ.save import split_file, make_thumbnail, upload_via_user_session
print('✅ Barcha importlar OK')
"
```
Expected: `✅ Barcha importlar OK`

**Step 2: Yakuniy commit**

```bash
git add -A
git status  # tekshiring — keraksiz fayl yo'qligini
git commit -m "chore: final cleanup and verification"
```
