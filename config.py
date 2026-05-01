import os

# ── Hardcoded defaults — shu yerga to'g'ridan-to'g'ri yozish mumkin ──
# .env yoki environment variable bo'lmasa quyidagi qiymatlar ishlatiladi.
# Haqiqiy qiymatlaringizni shu yerga yozing.
# DIQQAT: Haqiqiy tokenlarni git'ga push qilmang — .gitignore ga qo'shing yoki .env ishlatishni tavsiya etamiz.
_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"       # misol: "123456:ABCdefGHIjklMNOpqrSTUvwxYZ"
_API_ID    = 0                            # misol: 12345678
_API_HASH  = "YOUR_API_HASH_HERE"        # misol: "abcdef1234567890abcdef1234567890"
_DB_URI    = "YOUR_MONGODB_URI_HERE"     # misol: "mongodb+srv://user:pass@cluster.mongodb.net/dbname"

# ── Ustuvorlik tartibi: 1) loyiha ichidagi .env 2) tizim env 3) config.py ──
def _load_dotenv(path):
    """Oddiy .env parser — python-dotenv shart emas."""
    result = {}
    if not os.path.exists(path):
        return result
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                    val = val[1:-1]
                result[key.strip()] = val
    except OSError:
        return result
    return result


_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
_DOTENV = _load_dotenv(_ENV_PATH)


def _get_value(key, default=None):
    dotenv_val = _DOTENV.get(key)
    if _has_value(dotenv_val):
        return dotenv_val
    env_val = os.environ.get(key)
    if _has_value(env_val):
        return env_val
    return default


def _get_int(key, default=0):
    value = _get_value(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(default)
        except (TypeError, ValueError):
            return 0


def _has_value(value):
    return value is not None and value != ""


BOT_TOKEN = _get_value("BOT_TOKEN", _BOT_TOKEN)
API_ID    = _get_int("API_ID", _API_ID)
API_HASH  = _get_value("API_HASH", _API_HASH)
DB_URI    = _get_value("DB_URI", _DB_URI)
