import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    super_admin_ids: frozenset[int]
    db_path: str


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN topilmadi. .env faylini to'ldiring (.env.example ga qarang).")
    ids = frozenset(
        int(x) for x in os.getenv("SUPER_ADMIN_IDS", "").replace(" ", "").split(",") if x
    )
    return Config(
        bot_token=token,
        super_admin_ids=ids,
        db_path=os.getenv("DB_PATH", "data/bot.db"),
    )
