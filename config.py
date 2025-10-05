from decouple import config

REDIS_BROKER_URL = config("REDIS", default="redis://redis:6379/0")
TELEGRAM_TOKEN = config("TELEGRAM_TOKEN", default="")


def _parse_admins(raw_value: str) -> list[int]:
    return [int(chunk.strip()) for chunk in raw_value.split(",") if chunk.strip()]


TELEGRAM_ADMIN_ID = config(
    "TELEGRAM_ADMIN_ID",
    default="",
    cast=_parse_admins,
)
