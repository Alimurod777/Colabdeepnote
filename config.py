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
# .env fayl config.py bilan bir papkada bo'lishi kerak; parser oddiy (multiline/escape yo'q).
def _strip_outer_quotes(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _has_value(value):
    return value is not None and value != ""


def _coerce_int(value, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _load_dotenv(path):
    """Oddiy .env parser — multiline/escape yo'q, o'qilmasa jim o'tadi."""
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
                result[key.strip()] = _strip_outer_quotes(val.strip())
    except FileNotFoundError:
        return result
    except OSError:
        # .env o'qilmasa ham fallback ishlashi uchun jim o'tamiz.
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
    default_int = _coerce_int(default, 0)
    value = _get_value(key, default_int)
    return _coerce_int(value, default_int)


BOT_TOKEN = _get_value("BOT_TOKEN", _BOT_TOKEN)
API_ID    = _get_int("API_ID", _API_ID)
API_HASH  = _get_value("API_HASH", _API_HASH)
DB_URI    = _get_value("DB_URI", _DB_URI)
