import os

# .env fayl mavjud bo'lsa, uning qiymatlarini o'qiydi.
# Colab yoki server muhitida os.environ to'g'ridan-to'g'ri ishlatiladi.
try:
    from decouple import config as _cfg
    BOT_TOKEN = _cfg("BOT_TOKEN", default="")
    API_ID    = _cfg("API_ID",    default=0, cast=int)
    API_HASH  = _cfg("API_HASH",  default="")
    DB_URI    = _cfg("DB_URI",    default="")
except Exception:
    # decouple o'rnatilmagan bo'lsa to'g'ridan-to'g'ri os.environ
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    API_ID    = int(os.environ.get("API_ID", "0") or "0")
    API_HASH  = os.environ.get("API_HASH", "")
    DB_URI    = os.environ.get("DB_URI", "")
