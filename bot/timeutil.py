"""Vaqt bilan ishlash. Bazada hamma vaqt UTC da saqlanadi, foydalanuvchiga Toshkent vaqtida ko'rsatiladi."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Asia/Tashkent")
except Exception:  # tzdata yo'q bo'lsa (Windows) — Toshkentda yozgi vaqt yo'q, +5 doimiy
    TZ = timezone(timedelta(hours=5))

DB_FMT = "%Y-%m-%d %H:%M:%S"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_db(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(DB_FMT)


def from_db(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, DB_FMT).replace(tzinfo=timezone.utc)


def local(dt: datetime) -> datetime:
    return dt.astimezone(TZ)


def fmt(dt: datetime | None) -> str:
    return local(dt).strftime("%d.%m.%Y %H:%M") if dt else "—"


def fmt_left(delta: timedelta) -> str:
    minutes = max(0, int(delta.total_seconds() // 60))
    days, rem = divmod(minutes, 24 * 60)
    hours, mins = divmod(rem, 60)
    if days:
        return f"{days} kun {hours} soat" if hours else f"{days} kun"
    if hours:
        return f"{hours} soat {mins} daqiqa" if mins else f"{hours} soat"
    return f"{mins} daqiqa"


def parse_local(text: str, now: datetime) -> datetime | None:
    """'25.11.2026 18:00' yoki '25.11 18:00' (Toshkent vaqti) -> UTC datetime."""
    text = " ".join(text.split())
    year = local(now).year
    for has_year in (True, False):
        try:
            if has_year:
                parsed = datetime.strptime(text, "%d.%m.%Y %H:%M")
            else:  # yilni o'zimiz qo'shamiz (29-fevral muammosidan qochish uchun)
                day_month, _, hm = text.partition(" ")
                parsed = datetime.strptime(f"{day_month}.{year} {hm}", "%d.%m.%Y %H:%M")
        except ValueError:
            continue
        dt = parsed.replace(tzinfo=TZ)
        if not has_year and dt < now:
            dt = dt.replace(year=dt.year + 1)
        return dt.astimezone(timezone.utc)
    return None


def week_start(now: datetime) -> datetime:
    """Joriy haftaning dushanba 00:00 (Toshkent) vaqti, UTC da."""
    loc = local(now)
    monday = (loc - timedelta(days=loc.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(timezone.utc)


def is_quiet(now: datetime, start_hour: int, end_hour: int) -> bool:
    """Tungi tinch vaqtmi (masalan 23:00–07:00) — bu vaqtda eslatma yuborilmaydi."""
    h = local(now).hour
    if start_hour == end_hour:
        return False
    if start_hour > end_hour:
        return h >= start_hour or h < end_hour
    return start_hour <= h < end_hour
