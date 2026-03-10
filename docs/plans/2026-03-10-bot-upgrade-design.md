# VJ-Save-Restricted-Content Bot — Upgrade Design

**Date:** 2026-03-10
**Approach:** Variant 1 — Modullar bo'yicha bosqichma-bosqich yangilash

---

## Maqsad

Mavjud `pyrogram` bazali botni `pyrofork` ga o'tkazish, Python 3.10–3.13 mosligi ta'minlash, va quyidagi yangi funksiyalarni qo'shish:

- `/qrlogin` buyrug'i
- 2GB+ medialar uchun ffmpeg split
- Auto thumbnail
- User session orqali upload (bot API emas)
- FloodWait oldini olish
- MongoDB fallback (local JSON)
- MongoDB so'rovlari caching

---

## 1. `config.py`

- Barcha default qiymatlar bo'sh string/0 — credentials kod ichida saqlanmaydi
- `os.environ.get()` orqali environment variable dan o'qiladi
- Colab da foydalanuvchi Hujayra 2 da o'zi kiritadi

---

## 2. `database/db.py`

- MongoDB ulanishga urinadi
- Ulanmasa `sessions/local_db.json` faylida ishlaydi
- In-memory cache (dict) — read operatsiyalari tezlashadi
- Faqat write/update paytida DB ga yoziladi

---

## 3. `TechVJ/generate.py` — `/qrlogin`

- Mavjud `/login` (telefon + OTP) **saqlanadi**
- Yangi `/qrlogin` qo'shiladi:
  1. Pyrogram `qr_code_login` orqali QR generatsiya
  2. QR rasmini foydalanuvchiga yuborish
  3. Foydalanuvchi boshqa qurilmadan skan qiladi
  4. Session string olinib saqlanadi
  5. 2FA bo'lsa parol so'raladi

---

## 4. `TechVJ/save.py`

### 4a. Fayl Split
- Yuklab keyin hajm tekshiriladi
- 2GB+ bo'lsa `ffmpeg -c copy` bilan qismlarga bo'linadi
- `ffmpeg` yo'q bo'lsa static ffmpeg binary ishlatiladi (`staticfiles/`)
- Har qism alohida upload, temp fayllar o'chiriladi

### 4b. Auto Thumbnail
- Video: `ffmpeg` bilan 1-soniya kadridan PNG olinadi
- Rasm: o'zi thumbnail
- Upload da `thumb` parametriga beriladi

### 4c. Upload (User Session)
- Bot API emas — foydalanuvchi session string bilan `userbot` Client
- Bot va foydalanuvchi orasidagi private chat ga yuboriladi
- `FloodWait` ushlanadi → `asyncio.sleep(e.value)` → qayta urinish

---

## 5. `WOODcraft/VJ-WOODcraft-Colab.ipynb`

### Hujayra 1 — Setup
- `apt-get install ffmpeg`
- Static ffmpeg binary yuklab olish
- Python 3.10–3.13 versiya tekshiruvi

### Hujayra 2 — Config (foydalanuvchi to'ldiradi)
- `API_ID`, `API_HASH`, `BOT_TOKEN`, `DB_URI` — Colab form
- `DB_URI` bo'sh qolsa local JSON haqida eslatma

### Hujayra 3 — Run
- `python3 bot.py`

---

## Python versiya mosligi

- `pyrofork==2.3.45` — Python 3.10–3.13 da ishlaydi
- `uvloop` faqat Linux da (Colab), Windows da o'tkazib yuboriladi
- `asyncio` API o'zgarishlari (3.10 vs 3.12) hisobga olinadi

---

## Fayl o'zgarishlari xulasasi

| Fayl | O'zgarish |
|------|-----------|
| `config.py` | Default qiymatlar bo'shatiladi |
| `database/db.py` | MongoDB fallback + cache |
| `TechVJ/generate.py` | `/qrlogin` qo'shiladi |
| `TechVJ/save.py` | Split, thumbnail, user session upload, FloodWait |
| `WOODcraft/*.ipynb` | 3 hujayrali yangi struktura |
| `requirements.txt` | Versiyalar tekshiriladi |
