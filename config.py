import os

# ── Hardcoded defaults — shu yerga to'g'ridan-to'g'ri yozish mumkin ──
# .env yoki environment variable bo'lmasa quyidagi qiymatlar ishlatiladi.
# Haqiqiy qiymatlaringizni shu yerga yozing:
_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"       # misol: "123456:ABCdefGHIjklMNOpqrSTUvwxYZ"
_API_ID    = 0                            # misol: 12345678
_API_HASH  = "YOUR_API_HASH_HERE"        # misol: "abcdef1234567890abcdef1234567890"
_DB_URI    = "YOUR_MONGODB_URI_HERE"     # misol: "mongodb+srv://user:pass@cluster.mongodb.net/dbname"

# ── .env yoki environment variable mavjud bo'lsa, ular ustunlik qiladi ──
# .env fayl mavjud bo'lsa, uning qiymatlarini o'qiydi.
# Colab yoki server muhitida os.environ to'g'ridan-to'g'ri ishlatiladi.
try:
    from decouple import config as _cfg
    BOT_TOKEN = _cfg("BOT_TOKEN", default=_BOT_TOKEN)
    API_ID    = _cfg("API_ID",    default=_API_ID, cast=int)
    API_HASH  = _cfg("API_HASH",  default=_API_HASH)
    DB_URI    = _cfg("DB_URI",    default=_DB_URI)
except Exception:
    # decouple o'rnatilmagan bo'lsa to'g'ridan-to'g'ri os.environ
    BOT_TOKEN = os.environ.get("BOT_TOKEN") or _BOT_TOKEN
    API_ID    = int(os.environ.get("API_ID") or _API_ID)
    API_HASH  = os.environ.get("API_HASH") or _API_HASH
    DB_URI    = os.environ.get("DB_URI") or _DB_URI
