from datetime import datetime, timezone

from bot.timeutil import fmt_left, is_quiet, parse_local, week_start


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_quiet_hours():
    assert is_quiet(utc(2026, 11, 18, 19, 0), 23, 7)      # 00:00 Toshkent
    assert not is_quiet(utc(2026, 11, 18, 7, 0), 23, 7)   # 12:00 Toshkent
    assert not is_quiet(utc(2026, 11, 18, 19, 0), 0, 0)   # o'chirilgan


def test_parse_local():
    now = utc(2026, 11, 18, 7, 0)
    assert parse_local("25.11.2026 18:00", now) == utc(2026, 11, 25, 13, 0)
    assert parse_local("25.11 18:00", now) == utc(2026, 11, 25, 13, 0)
    assert parse_local("01.01 10:00", now) == utc(2027, 1, 1, 5, 0)  # o'tgan sana -> keyingi yil
    assert parse_local("ertaga", now) is None


def test_week_start_and_left():
    assert week_start(utc(2026, 11, 18, 7, 0)) == utc(2026, 11, 15, 19, 0)  # dushanba 00:00 Toshkent
    from datetime import timedelta
    assert fmt_left(timedelta(days=1, hours=3)) == "1 kun 3 soat"
    assert fmt_left(timedelta(minutes=45)) == "45 daqiqa"
