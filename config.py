from decouple import config

REDIS_BROKER_URL = config("REDIS", default="redis://redis:6379/0")
TELEGRAM_TOKEN = config("TELEGRAM_TOKEN", default="")
TELEGRAM_ADMIN_ID = config(
    'TELEGRAM_ADMIN_ID',
    default="",
    cast=lambda v: [int(i) for i in filter(str.isdigit, (s.strip() for s in v.split(',')))]
)
