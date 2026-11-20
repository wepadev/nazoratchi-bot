import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    super_admin_ids: frozenset[int]
    db_path: str
    reminder_interval_hours: float = 3.0     # topshirmaganlarga eslatma oralig'i
    final_reminder_minutes: int = 60          # muddat tugashidan oldingi oxirgi eslatma
    quiet_hours: tuple[int, int] = (23, 7)    # tunda eslatma yuborilmaydi (Toshkent vaqti)
    penalty_not_submitted: int = 5            # topshirmaganlik uchun ayiriladigan tanga
    coins_per_correct: int = 1
    coins_per_lesson: int = 5                 # jonli darsda qatnashgani uchun
    penalty_missed_lesson: int = 5            # jonli darsni qoldirgani uchun
    weekly_rating_weekday: int = 0            # 0 = dushanba
    weekly_rating_hour: int = 9
    daily_reminder_hour: int = 19             # muddatsiz testlar uchun kunlik eslatma soati
    web_port: int = 8080                      # Mini App serveri porti
    webapp_url: str = ""                       # Mini App'ning ochiq HTTPS manzili


def _quiet(raw: str) -> tuple[int, int]:
    try:
        a, b = raw.split("-")
        return int(a), int(b)
    except ValueError:
        return 23, 7


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
        reminder_interval_hours=float(os.getenv("REMINDER_INTERVAL_HOURS", "3")),
        final_reminder_minutes=int(os.getenv("FINAL_REMINDER_MINUTES", "60")),
        quiet_hours=_quiet(os.getenv("QUIET_HOURS", "23-7")),
        penalty_not_submitted=int(os.getenv("PENALTY_NOT_SUBMITTED", "5")),
        coins_per_correct=int(os.getenv("COINS_PER_CORRECT", "1")),
        coins_per_lesson=int(os.getenv("COINS_PER_LESSON", "5")),
        penalty_missed_lesson=int(os.getenv("PENALTY_MISSED_LESSON", "5")),
        weekly_rating_hour=int(os.getenv("WEEKLY_RATING_HOUR", "9")),
        daily_reminder_hour=int(os.getenv("DAILY_REMINDER_HOUR", "19")),
        web_port=int(os.getenv("PORT", "8080")),
        webapp_url=os.getenv("WEBAPP_URL", "").strip().rstrip("/"),
    )
