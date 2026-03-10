import os

# Bot token @Botfather
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Your API ID from my.telegram.org
API_ID = int(os.environ.get("API_ID", "0"))

# Your API Hash from my.telegram.org
API_HASH = os.environ.get("API_HASH", "")

# Database — bo'sh qolsa local JSON fallback ishlatiladi
DB_URI = os.environ.get("DB_URI", "")
