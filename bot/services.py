"""Biznes-mantiq: test nashri, javoblarni qabul qilish, yakunlash, eslatmalar, reyting."""
from __future__ import annotations

import asyncio
import logging
import re
import secrets
import time
from collections import Counter
from datetime import datetime, timedelta
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from . import keyboards as kb
from . import motivation
from .answers import grade, mistakes, preview
from .config import Config
from .db import Database, Group, Lesson, Test, User
from .timeutil import fmt, fmt_left, from_db, is_quiet, local, to_db, week_start

log = logging.getLogger(__name__)
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
COIN = "🪙"


# ---------------- yuborish ----------------

async def safe_send(bot: Bot, chat_id: int, text: str, reply_markup=None) -> bool:
    for _ in range(2):
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
            await asyncio.sleep(0.04)  # Telegram cheklovlari (~25 xabar/soniya)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError:
            return False  # foydalanuvchi botni bloklagan
        except Exception:
            log.exception("Xabar yuborilmadi: %s", chat_id)
            return False
    return False


async def send_test(bot: Bot, chat_id: int, test: Test, caption: str,
                    reply_markup: InlineKeyboardMarkup | None = None) -> bool:
    if not test.file_id:
        return await safe_send(bot, chat_id, caption, reply_markup)
    try:
        if test.file_type == "photo":
            await bot.send_photo(chat_id, test.file_id, caption=caption, reply_markup=reply_markup)
        else:
            await bot.send_document(chat_id, test.file_id, caption=caption, reply_markup=reply_markup)
        await asyncio.sleep(0.04)
        return True
    except TelegramForbiddenError:
        return False
    except Exception:
        log.exception("Test fayli yuborilmadi: %s", chat_id)
        return await safe_send(bot, chat_id, caption, reply_markup)


async def admin_ids(db: Database, cfg: Config, group_id: int) -> list[int]:
    """Guruh nazoratchilari; tayinlanmagan bo'lsa — bosh adminlar."""
    ids = [a.id for a in await db.group_admins(group_id)]
    return ids or list(cfg.super_admin_ids)


async def notify_admins(bot: Bot, db: Database, cfg: Config, group_id: int, text: str,
                        reply_markup=None) -> None:
    for aid in await admin_ids(db, cfg, group_id):
        await safe_send(bot, aid, text, reply_markup)


# ---------------- nashr ----------------

def deadline_line(test: Test, now: datetime) -> str:
    if not test.deadline_at:
        return "Muddat: <b>cheklanmagan</b> — o'zingizga qulay vaqtda topshiring"
    return f"Muddat: <b>{fmt(test.deadline_at)}</b> gacha ({fmt_left(test.deadline_at - now)} qoldi)"


def announce_text(test: Test, group: Group, cfg: Config, now: datetime) -> str:
    penalty_when = "" if test.deadline_at else " (test yakunlanganda)"
    return (
        f"📝 <b>Yangi test: {escape(test.title)}</b>\n\n"
        f"Guruh: {escape(group.name)}\n"
        f"Test kodi: <b>{test.id}</b>\n"
        f"Savollar: {test.n} ta (A/B/C/D)\n"
        f"{deadline_line(test, now)}\n\n"
        f"Har bir to'g'ri javob: +{cfg.coins_per_correct} {COIN}\n"
        f"Topshirmaslik: −{cfg.penalty_not_submitted} {COIN}{penalty_when}\n\n"
        f"⚡️ Tez yuborish — botga bitta xabar: <code>{test.id}*abcd...</code>\n"
        "Javoblar <b>faqat bir marta</b> qabul qilinadi."
    )


async def publish(bot: Bot, db: Database, cfg: Config, test: Test, deadline: datetime | None, now: datetime) -> bool:
    if not await db.publish_test(test.id, now, deadline):
        return False
    test = await db.get_test(test.id)
    group = await db.get_group(test.group_id)
    text = announce_text(test, group, cfg, now)
    sent = 0
    for member in await db.list_members(test.group_id):
        sent += await send_test(bot, member.id, test, text, kb.answer_kb(test.id))
    await notify_admins(
        bot, db, cfg, test.group_id,
        f"🚀 «{escape(test.title)}» nashr qilindi ({escape(group.name)}). "
        f"{sent} ta ustozga yuborildi. Muddat: {fmt(deadline) if deadline else 'cheklanmagan'}.")
    return True


async def publish_next_queued(bot: Bot, db: Database, cfg: Config, group_id: int, now: datetime) -> None:
    nxt = await db.next_queued(group_id)
    if nxt and nxt.queue_hours:
        await publish(bot, db, cfg, nxt, now + timedelta(hours=nxt.queue_hours), now)


# ---------------- javob ----------------

async def submit(db: Database, cfg: Config, test: Test, user: User, answers: str, now: datetime) -> int | None:
    """Javobni saqlaydi va tanga beradi. None — qabul qilinmadi (muddat o'tgan yoki oldin topshirgan)."""
    correct = grade(answers, test.answer_key)
    if not await db.submit(test.id, user.id, answers, correct, now):
        return None
    if correct:
        await db.add_coins(user.id, test.group_id, correct * cfg.coins_per_correct,
                           f"«{test.title}»: {correct}/{test.n}", now, test_id=test.id)
    return correct


# ---------------- statistika ----------------

def question_stats(test: Test, answers_list: list[str]) -> list[tuple[int, int, str | None]]:
    """[(savol, xato qilganlar soni, eng ko'p tanlangan noto'g'ri javob)]"""
    out = []
    for i, k in enumerate(test.answer_key):
        wrong = [a[i] for a in answers_list if a[i] != k]
        common = Counter(w for w in wrong if w != "-").most_common(1)
        out.append((i + 1, len(wrong), common[0][0] if common else None))
    return out


async def stats_text(db: Database, test: Test) -> str:
    subs = await db.list_submissions(test.id)
    members = await db.list_members(test.group_id)
    total = len(members)
    lines = [f"📊 <b>{escape(test.title)}</b> — statistika", ""]
    lines.append(f"Topshirdi: <b>{len(subs)}</b> / {total}")
    if not subs:
        return "\n".join(lines)
    avg = sum(s.correct for s in subs) / len(subs)
    lines.append(f"O'rtacha: <b>{avg:.1f}</b> / {test.n} ({100 * avg / test.n:.0f}%)")
    best = max(subs, key=lambda s: s.correct)
    names = {m.id: m.full_name for m in members}
    lines.append(f"Eng yuqori: {best.correct}/{test.n} — {escape(names.get(best.user_id, '—'))}")
    full = sum(1 for s in subs if s.correct == test.n)
    if full:
        lines.append(f"100% natija: {full} ta ustoz")

    qs = sorted(question_stats(test, [s.answers for s in subs]), key=lambda x: -x[1])
    hard = [q for q in qs if q[1] > 0][:7]
    if hard:
        lines += ["", "<b>Eng ko'p xato qilingan savollar:</b>"]
        for num, wrong, common in hard:
            extra = f", ko'pchilik {common} ni tanlagan" if common else ""
            lines.append(f"№{num} — {100 * wrong / len(subs):.0f}% xato "
                         f"(to'g'ri: {test.answer_key[num - 1]}{extra})")
    return "\n".join(lines)


async def at_risk(db: Database, group_id: int) -> list[User]:
    """Oxirgi 2 ta yakunlangan testni ketma-ket topshirmagan ustozlar."""
    tests = [t for t in await db.closed_tests(group_id) if t.status == "closed"]
    if len(tests) < 2:
        return []
    submitted = {t.id: {s.user_id for s in await db.list_submissions(t.id)} for t in tests}
    result = []
    for m in await db.list_members(group_id):
        joined = await db.member_joined_at(group_id, m.id)
        relevant = [t for t in tests if joined and t.published_at and t.published_at >= joined][-2:]
        if len(relevant) == 2 and all(m.id not in submitted[t.id] for t in relevant):
            result.append(m)
    return result


# ---------------- yakunlash ----------------

async def close(bot: Bot, db: Database, cfg: Config, test: Test, now: datetime) -> bool:
    if not await db.close_test(test.id, now):
        return False
    test = await db.get_test(test.id)
    group = await db.get_group(test.group_id)
    title = escape(test.title)

    # 1) topshirmaganlarga jarima (test nashridan keyin qo'shilganlarga emas)
    penalized = await db.non_submitters(test, only_before_publish=True)
    for u in penalized:
        await db.add_coins(u.id, test.group_id, -cfg.penalty_not_submitted,
                           f"«{test.title}»: topshirilmadi", now, test_id=test.id)

    # 2) har bir ustozga batafsil natija + to'g'ri javoblar
    key_block = preview(test.answer_key)
    for s in await db.list_submissions(test.id):
        errs = mistakes(s.answers, test.answer_key)
        lines = [f"✅ <b>{title}</b> yakunlandi.", "",
                 f"Natijangiz: <b>{s.correct}/{test.n}</b> (+{s.correct * cfg.coins_per_correct} {COIN})"]
        if errs:
            lines += ["", "<b>Xatolar:</b>"]
            for num, given, right in errs[:40]:
                g = "javobsiz" if given == "-" else given
                lines.append(f"№{num}: siz — {g}, to'g'ri — <b>{right}</b>")
            if len(errs) > 40:
                lines.append(f"… va yana {len(errs) - 40} ta")
        else:
            lines.append("\n🎉 Barcha javoblar to'g'ri!")
        lines += ["", "To'g'ri javoblar:", key_block]
        await safe_send(bot, s.user_id, "\n".join(lines), kb.appeal_kb(test.id) if errs else None)

    penalized_ids = {u.id for u in penalized}
    for u in await db.non_submitters(test, only_before_publish=False):
        head = (f"❌ Siz <b>{title}</b> testini topshirmadingiz: −{cfg.penalty_not_submitted} {COIN}"
                if u.id in penalized_ids else f"<b>{title}</b> testi yakunlandi.")
        await safe_send(bot, u.id, f"{head}\n\nTo'g'ri javoblar:\n{key_block}")

    # 3) nazoratchilarga hisobot
    report = [f"🏁 <b>{title}</b> yakunlandi ({escape(group.name)})", "", await stats_text(db, test)]
    if penalized:
        report += ["", f"<b>Topshirmaganlar ({len(penalized)}):</b>"]
        report += [f"• {escape(u.full_name)} — <code>{u.phone}</code>" for u in penalized[:50]]
    risky = await at_risk(db, test.group_id)
    if risky:
        report += ["", "⚠️ <b>Ketma-ket 2 ta testni topshirmaganlar:</b>"]
        report += [f"• {escape(u.full_name)} — <code>{u.phone}</code>" for u in risky]
    await notify_admins(bot, db, cfg, test.group_id, "\n".join(report)[:4000])

    # 4) navbatdagi test
    await publish_next_queued(bot, db, cfg, test.group_id, now)
    return True


# ---------------- eslatmalar ----------------

class _ReminderContext:
    """Eslatma matni uchun ma'lumotlar (bir tick ichida keshlanadi)."""

    def __init__(self, db: Database):
        self.db = db
        self._places: dict[int, dict[int, int]] = {}
        self._submitted: dict[int, int] = {}

    async def place(self, group_id: int, user_id: int) -> int | None:
        if group_id not in self._places:
            self._places[group_id] = {u.id: p for p, u, _ in ranked(await self.db.rating(group_id))}
        return self._places[group_id].get(user_id)

    async def submitted(self, test_id: int) -> int:
        if test_id not in self._submitted:
            self._submitted[test_id] = len(await self.db.list_submissions(test_id))
        return self._submitted[test_id]


async def deadline_reminder_text(ctx: _ReminderContext, cfg: Config, uid: int, t: Test, now: datetime,
                                 final: bool) -> str:
    lines = [f"<b>{motivation.headline(uid, final)}</b>", "",
             f"📝 «{escape(t.title)}» — hali topshirilmagan",
             f"⏳ Muddat: {fmt(t.deadline_at)} — {fmt_left(t.deadline_at - now)} qoldi"]
    done = await ctx.submitted(t.id)
    if done:
        lines.append(f"👥 Guruhdoshlaringizdan {done} nafari topshirib bo'ldi")
    lines.append(f"{COIN} +{t.n * cfg.coins_per_correct} tangagacha · ⚠️ topshirmasangiz −{cfg.penalty_not_submitted}")
    place = await ctx.place(t.group_id, uid)
    if place:
        lines.append(f"📍 Hozir reytingda {place}-o'rindasiz")
    lines += [f"⚡️ Tez yuborish: <code>{t.id}*abcd...</code>", "", motivation.cta(uid)]
    return "\n".join(lines)


async def open_reminder_text(ctx: _ReminderContext, cfg: Config, uid: int, tests: list[Test]) -> str:
    lines = [f"<b>{motivation.headline(uid)}</b>", "", f"Sizni <b>{len(tests)} ta</b> test kutyapti:"]
    for t in tests[:15]:
        done = await ctx.submitted(t.id)
        extra = f" · {done} nafar topshirdi" if done else ""
        lines.append(f"• «{escape(t.title)}» — {t.n} savol · kod <code>{t.id}</code>{extra}")
    total = sum(t.n for t in tests) * cfg.coins_per_correct
    lines += ["", f"{COIN} Hammasini ishlasangiz: <b>+{total}</b> tangagacha",
              f"⚠️ Topshirilmagan har bir test: −{cfg.penalty_not_submitted} (test yakunlanganda)"]
    place = await ctx.place(tests[0].group_id, uid)
    if place:
        lines.append(f"📍 Hozir reytingda {place}-o'rindasiz")
    lines += ["⚡️ Tez yuborish: <code>kod*abcd...</code>", "", motivation.cta(uid)]
    return "\n".join(lines)


async def send_reminders(bot: Bot, db: Database, cfg: Config, now: datetime) -> None:
    interval = timedelta(hours=cfg.reminder_interval_hours)
    final_window = timedelta(minutes=cfg.final_reminder_minutes)
    quiet = is_quiet(now, *cfg.quiet_hours)
    ctx = _ReminderContext(db)
    # muddatli testlar: har test uchun alohida, muddatdan oldin oxirgi eslatma (tunda ham)
    for t in await db.published_tests():
        if not t.deadline_at or t.deadline_at <= now:
            continue
        left = t.deadline_at - now
        final = not t.final_reminded and left <= final_window
        regular = (not quiet and left > final_window
                   and now - (t.reminded_at or t.published_at) >= interval)
        if not (final or regular):
            continue
        for u in await db.non_submitters(t, only_before_publish=False):
            await safe_send(bot, u.id, await deadline_reminder_text(ctx, cfg, u.id, t, now, final), kb.answer_kb(t.id))
        await db.set_reminded(t.id, now, final=final)
    await open_tests_reminder(bot, db, cfg, now, ctx)


async def open_tests_reminder(bot: Bot, db: Database, cfg: Config, now: datetime,
                              ctx: _ReminderContext | None = None) -> None:
    """Muddatsiz testlar: har REMINDER_INTERVAL_HOURS da (tunda emas) har bir ustozga BITTA umumiy xabar.
    Test nashr qilinganidan keyin kamida shuncha vaqt o'tgan bo'lishi kerak (e'londan darhol keyin eslatma bormaydi)."""
    if is_quiet(now, *cfg.quiet_hours):
        return
    interval = timedelta(hours=cfg.reminder_interval_hours)
    last = from_db(await db.get_setting("open_reminder_at"))
    if last and now - last < interval:
        return
    pending: dict[int, list[Test]] = {}
    for t in await db.published_tests():
        if t.deadline_at or now - t.published_at < interval:
            continue
        for u in await db.non_submitters(t, only_before_publish=False):
            pending.setdefault(u.id, []).append(t)
    if not pending:
        return
    await db.set_setting("open_reminder_at", to_db(now))
    ctx = ctx or _ReminderContext(db)
    for uid, tests in pending.items():
        await safe_send(bot, uid, await open_reminder_text(ctx, cfg, uid, tests), kb.pending_tests_kb(tests[:15]))


# ---------------- kalitni tuzatish ----------------

async def fix_key(bot: Bot, db: Database, cfg: Config, test: Test, new_key: str, admin_id: int,
                  now: datetime) -> int:
    """Kalitni yangilaydi, barcha natijalarni qayta hisoblaydi. Natijasi o'zgarganlar sonini qaytaradi.

    Xabarlar:
    - test yakunlangan (kalit allaqachon hammaga ochiq) — guruhdagi BARCHA ustozlarga qaysi savol o'zgargani
      va yangi to'g'ri javob; natijasi o'zgarganlarga shu xabarning o'zida yangi ball;
    - test hali faol — kalit sir qoladi, faqat natijasi o'zgarganlarga yangi ball."""
    old_key = test.answer_key
    await db.update_test(test.id, answer_key=new_key)
    title = escape(test.title)
    score_lines: dict[int, str] = {}
    for s in await db.list_submissions(test.id):
        new = grade(s.answers, new_key)
        diff = new - s.correct
        if not diff:
            continue
        await db.set_submission_correct(test.id, s.user_id, new)
        amount = diff * cfg.coins_per_correct
        await db.add_coins(s.user_id, test.group_id, amount,
                           f"«{test.title}»: kalit tuzatildi ({s.correct}→{new})", now,
                           test_id=test.id, created_by=admin_id)
        sign = "+" if amount > 0 else "−"
        score_lines[s.user_id] = f"Natijangiz: {s.correct} → <b>{new}</b>/{test.n} ({sign}{abs(amount)} {COIN})"

    if test.status == "closed":
        changes = [(i + 1, o, n) for i, (o, n) in enumerate(zip(old_key, new_key)) if o != n]
        head = [f"🔑 <b>«{title}» testining kaliti tuzatildi:</b>"]
        head += [f"№{num} — to'g'ri javob <b>{new}</b> (avval {old} edi)" for num, old, new in changes[:30]]
        recipients = {m.id for m in await db.list_members(test.group_id)} | set(score_lines)
        for uid in recipients:
            tail = score_lines.get(uid, "Natijangiz o'zgarmadi.")
            await safe_send(bot, uid, "\n".join(head) + "\n\n" + tail)
    else:
        for uid, line in score_lines.items():
            await safe_send(bot, uid, f"🔑 «{title}» testining kaliti tuzatildi.\n{line}")
    return len(score_lines)


# ---------------- reyting ----------------

PERIOD_TITLES = {"all": "umumiy", "week": "shu hafta", "lastweek": "o'tgan hafta"}


def period_range(period: str, now: datetime) -> tuple[datetime | None, datetime | None]:
    ws = week_start(now)
    if period == "week":
        return ws, None
    if period == "lastweek":
        return ws - timedelta(days=7), ws
    return None, None


def ranked(rows: list[tuple[User, int]]) -> list[tuple[int, User, int]]:
    """Teng tangali ustozlar bir xil o'rinda turadi (1, 2, 2, 4 ...)."""
    out, place = [], 0
    for i, (u, c) in enumerate(rows):
        if i == 0 or c != rows[i - 1][1]:
            place = i + 1
        out.append((place, u, c))
    return out


async def rating_text(db: Database, group: Group, period: str, now: datetime,
                      viewer_id: int | None = None, limit: int = 10) -> str:
    since, until = period_range(period, now)
    rows = ranked(await db.rating(group.id, since, until))
    lines = [f"🏆 <b>{escape(group.name)}</b> — reyting ({PERIOD_TITLES[period]})", ""]
    if not rows:
        return "\n".join(lines + ["Guruhda hali ustoz yo'q."])
    for place, u, c in rows[:limit]:
        mark = MEDALS.get(place, f"{place}.")
        me = " ← siz" if u.id == viewer_id else ""
        lines.append(f"{mark} {escape(u.full_name)} — <b>{c}</b> {COIN}{me}")
    if viewer_id is not None:
        mine = next(((p, c) for p, u, c in rows if u.id == viewer_id), None)
        if mine:
            place, coins = mine
            lines += ["", f"📍 Siz: <b>{place}-o'rin</b> ({len(rows)} tadan), {coins} {COIN}"]
            if place > limit and len(rows) >= limit:
                need = rows[limit - 1][2] - coins + 1
                lines.append(f"TOP-{limit} ga kirish uchun yana <b>{need}</b> {COIN} kerak 💪")
            elif place > 1:
                above = min(c for _, _, c in rows if c > coins)
                lines.append(f"Yuqoriroq o'ringa chiqish uchun {above - coins + 1} {COIN} kerak")
    return "\n".join(lines)


async def weekly_rating(bot: Bot, db: Database, cfg: Config, now: datetime) -> None:
    """Har dushanba (sozlamadagi soatda) o'tgan hafta reytingini yuboradi."""
    ws = week_start(now)
    since_start = now - ws
    if since_start < timedelta(hours=cfg.weekly_rating_hour):
        return
    week_id = ws.strftime("%Y-%m-%d")
    if await db.get_setting("weekly_rating_sent") == week_id:
        return
    await db.set_setting("weekly_rating_sent", week_id)
    for group in await db.list_groups():
        if not await db.has_activity(group.id, ws - timedelta(days=7), ws):
            continue
        for m in await db.list_members(group.id):
            text = await rating_text(db, group, "lastweek", now, viewer_id=m.id)
            await safe_send(bot, m.id, "📅 <b>Haftalik natijalar</b>\n\n" + text)
        admin_text = await rating_text(db, group, "lastweek", now, limit=30)
        await notify_admins(bot, db, cfg, group.id, "📅 <b>Haftalik natijalar</b>\n\n" + admin_text)


# ---------------- umumiy amallar (bot va Mini App uchun) ----------------

async def resolve_appeal(bot: Bot, db: Database, appeal, test: Test, action: str, admin: User,
                         now: datetime) -> str | None:
    """action: accept | reject | fixkey. Natija matnini qaytaradi; allaqachon hal qilingan bo'lsa None."""
    status = "rejected" if action == "reject" else "accepted"
    if not await db.resolve_appeal(appeal.id, status, admin.id, now):
        return None
    q = f" (№{appeal.question})" if appeal.question else ""
    title = escape(test.title)
    if action == "accept":
        await db.add_coins(appeal.user_id, test.group_id, 1, f"«{test.title}»: e'tiroz qabul qilindi{q}", now,
                           test_id=test.id, created_by=admin.id)
        await safe_send(bot, appeal.user_id, f"✅ «{title}» bo'yicha e'tirozingiz{q} qabul qilindi: +1 {COIN}")
        return f"✅ Qabul qilindi (+1 {COIN})"
    if action == "reject":
        await safe_send(bot, appeal.user_id, f"❌ «{title}» bo'yicha e'tirozingiz{q} rad etildi.")
        return "❌ Rad etildi"
    await safe_send(bot, appeal.user_id, f"✅ «{title}» bo'yicha e'tirozingiz{q} qabul qilindi — kalit tuzatiladi.")
    return "🔑 Kalit tuzatilmoqda"


async def manual_coins(bot: Bot, db: Database, group: Group, target: User, amount: int, reason: str,
                       admin: User, now: datetime) -> None:
    await db.add_coins(target.id, group.id, amount, reason, now, created_by=admin.id)
    sign = "+" if amount > 0 else "−"
    await safe_send(bot, target.id, f"{COIN} <b>{sign}{abs(amount)} tanga</b> ({escape(group.name)})\nSabab: {escape(reason)}")


async def publish_or_queue(bot: Bot, db: Database, cfg: Config, test: Test, now: datetime,
                           hours: int | None = None, deadline: datetime | None = None) -> str:
    """Testni darhol nashr qiladi ('published'; nashr bo'lmasa 'busy'). Bir guruhda bir nechta faol test bo'lishi mumkin.
    deadline ham, hours ham berilmasa (yoki hours=0) — muddatsiz test."""
    dl = deadline or (now + timedelta(hours=hours) if hours else None)
    return "published" if await publish(bot, db, cfg, test, dl, now) else "busy"


# ---------------- jonli dars davomati ----------------

LESSON_DURATIONS = [(30, "30 daqiqa"), (60, "1 soat"), (120, "2 soat"), (0, "Kun oxirigacha")]
_CODE_RE = re.compile(r"^\d{4}$")
MAX_WRONG_CODES, WRONG_WINDOW = 5, 600  # 10 daqiqada 5 ta xato urinish
_wrong_codes: dict[int, list[float]] = {}


def valid_lesson_code(code: str) -> bool:
    return bool(_CODE_RE.match(code or ""))


def lesson_closes_at(now: datetime, minutes: int) -> datetime:
    """minutes = 0 — Toshkent vaqti bilan kun oxirigacha."""
    if minutes > 0:
        return now + timedelta(minutes=minutes)
    end = local(now).replace(hour=23, minute=59, second=59, microsecond=0)
    return end.astimezone(now.tzinfo)


async def new_lesson_code(db: Database, group_id: int, now: datetime) -> str:
    while True:
        code = f"{secrets.randbelow(10000):04d}"
        if not await db.open_code_in_group(group_id, code, now):
            return code


def lesson_label(lesson: Lesson) -> str:
    return f"«{escape(lesson.title)}» · {local(lesson.created_at):%d.%m.%Y}"


async def sync_lesson_coins(db: Database, cfg: Config, lesson: Lesson, user_id: int, now: datetime,
                            admin_id: int | None = None, note: str | None = None) -> int:
    """Shu dars bo'yicha ustozning tangasini qoidaga moslaydi va farqini qaytaradi.
    Qatnashdi: +coins_per_lesson; dars yopilgan va qatnashmadi: −penalty_missed_lesson; dars ochiq va hali yo'q: 0.
    Qayta chaqirilsa ham tanga ikki marta yozilmaydi (ledger bo'yicha farq hisoblanadi)."""
    present = user_id in await db.lesson_present_ids(lesson.id)
    if present:
        target, what = cfg.coins_per_lesson, "qatnashdi"
    elif not lesson.is_open(now):
        target, what = -cfg.penalty_missed_lesson, "qatnashmadi"
    else:
        target, what = 0, "belgi olib tashlandi"
    diff = target - await db.lesson_coins(lesson.id, user_id)
    if diff:
        await db.add_coins(user_id, lesson.group_id, diff,
                           f"Jonli dars «{lesson.title}» {local(lesson.created_at):%d.%m}: {note or what}", now,
                           lesson_id=lesson.id, created_by=admin_id)
    return diff


async def attend(db: Database, user: User, code: str, now: datetime,
                 cfg: Config | None = None) -> tuple[str, list[Lesson]]:
    """'ok' | 'already' | 'wrong' | 'blocked'. Xato kodlar sanaladi — taxmin qilib topishning oldini olish uchun."""
    clock = time.monotonic()
    tries = [t for t in _wrong_codes.get(user.id, []) if clock - t < WRONG_WINDOW]
    if len(tries) >= MAX_WRONG_CODES:
        _wrong_codes[user.id] = tries
        return "blocked", []
    lessons = await db.open_lessons_by_code(user.id, code, now)
    if not lessons:
        _wrong_codes[user.id] = tries + [clock]
        return "wrong", []
    marked = [lesson for lesson in lessons if await db.mark_attendance(lesson.id, user.id, now)]
    if cfg:
        for lesson in marked:
            await sync_lesson_coins(db, cfg, lesson, user.id, now)
    return ("ok" if marked else "already"), lessons


ATTEND_REPLIES = {
    "wrong": "❌ Bunday kod topilmadi yoki uning muddati tugagan. Kodni tekshirib, qaytadan yuboring.",
    "blocked": "⏳ Juda ko'p xato urinish. 10 daqiqadan keyin qayta urinib ko'ring.",
}


def attend_reply(status: str, lessons: list[Lesson], cfg: Config | None = None) -> str:
    if status in ATTEND_REPLIES:
        return ATTEND_REPLIES[status]
    names = ", ".join(lesson_label(lesson) for lesson in lessons)
    if status == "already":
        return f"Siz bu darsda allaqachon qatnashgan deb belgilangansiz: {names}"
    bonus = f" (+{cfg.coins_per_lesson * len(lessons)} {COIN})" if cfg and cfg.coins_per_lesson else ""
    return f"✅ Davomat qayd etildi: {names}{bonus}"


async def lesson_summary(db: Database, lesson: Lesson, now: datetime) -> str:
    roster = await db.lesson_roster(lesson)
    absent = [u for u, present in roster if not present]
    status = (f"🟢 kod {local(lesson.closes_at):%H:%M} gacha ishlaydi" if lesson.is_open(now) else "kod yopilgan")
    lines = [f"🎥 <b>{lesson_label(lesson)}</b>", f"Kod: <code>{lesson.code}</code> · {status}",
             f"Qatnashdi: <b>{len(roster) - len(absent)}</b> / {len(roster)}"]
    lines.append(f"📺 Yozuv: {escape(lesson.video_url)}" if lesson.video_url else "📺 Yozuv: hali qo'shilmagan")
    if absent:
        lines += ["", f"<b>Qatnashmaganlar ({len(absent)}):</b>"]
        lines += [f"• {escape(u.full_name)} — <code>{u.phone}</code>" for u in absent[:60]]
    return "\n".join(lines)


async def close_lesson(bot: Bot, db: Database, cfg: Config, lesson: Lesson, now: datetime) -> bool:
    if not await db.close_lesson(lesson.id, now):
        return False
    lesson = await db.get_lesson(lesson.id)
    g = await db.get_group(lesson.group_id)
    # qoldirganlarga jarima (qatnashganlar tangasini kod kiritganda olgan)
    for u, present in await db.lesson_roster(lesson):
        if present:
            continue
        if await sync_lesson_coins(db, cfg, lesson, u.id, now) and cfg.penalty_missed_lesson:
            await safe_send(bot, u.id, f"❌ {lesson_label(lesson)} jonli darsida qatnashmadingiz: "
                                       f"−{cfg.penalty_missed_lesson} {COIN}")
    await notify_admins(bot, db, cfg, lesson.group_id,
                        f"🏁 Jonli dars yakunlandi ({escape(g.name)})\n\n" + await lesson_summary(db, lesson, now))
    return True



# ---------------- dars yozuvlari ----------------

_URL_RE = re.compile(r"^https?://[^\s<>\"']{4,490}$")


def clean_video_url(raw: str | None) -> str | None:
    """To'g'ri havola bo'lsa uni qaytaradi (bo'sh — None), aks holda ValueError."""
    url = (raw or "").strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")) and re.match(r"^(www\.)?(youtube\.com|youtu\.be)/", url):
        url = "https://" + url
    if not _URL_RE.match(url):
        raise ValueError("Havola noto'g'ri. Masalan: https://youtu.be/abc123")
    return url


async def announce_recording(bot: Bot, db: Database, lesson: Lesson) -> int:
    """Guruh a'zolariga yozuv qo'shilgani haqida xabar (havola tugmasi bilan)."""
    sent = 0
    text = (f"📺 Jonli dars yozuvi qo'shildi: {lesson_label(lesson)}\n\n"
            "Barcha yozuvlar: botdagi «📺 Dars yozuvlari» bo'limida.")
    for m in await db.list_members(lesson.group_id):
        sent += await safe_send(bot, m.id, text, kb.video_kb(lesson.video_url))
    return sent



# ---------------- test fayli ----------------

async def send_test_file(bot: Bot, db: Database, test: Test, updated: bool = False) -> int:
    """Nashr qilingan test faylini guruhdagi barcha ustozlarga yuboradi (fayl keyin qo'shilganda/almashtirilganda)."""
    caption = (f"📎 <b>{escape(test.title)}</b> — test fayli{' (yangilandi)' if updated else ''}\n"
               f"Kod: <code>{test.id}</code> · {test.n} ta savol\n"
               f"⚡️ Tez yuborish: <code>{test.id}*abcd...</code>")
    sent = 0
    for m in await db.list_members(test.group_id):
        sub = await db.get_submission(test.id, m.id)
        sent += await send_test(bot, m.id, test, caption, None if sub else kb.answer_kb(test.id))
    return sent


async def resync_lesson_coins(db: Database, cfg: Config, now: datetime) -> int:
    """Barcha yopilgan darslar tangalarini joriy qoidaga moslaydi (masalan, jarima bekor qilinganda qaytariladi).
    Idempotent: hech narsa o'zgarmagan bo'lsa hech narsa yozmaydi. O'zgargan yozuvlar sonini qaytaradi."""
    changed = 0
    for g in await db.list_groups():
        for lesson in await db.list_lessons(g.id):
            if lesson.is_open(now):
                continue
            for u, _ in await db.lesson_roster(lesson):
                if await sync_lesson_coins(db, cfg, lesson, u.id, now, note="tanga qoidasi yangilandi"):
                    changed += 1
    return changed



# ---------------- rejalashtirilgan nashr ----------------

def scheduled_deadline(test: Test, now: datetime) -> datetime | None:
    """Rejalangan test nashr bo'lganda qo'llanadigan muddat: aniq sana yoki nashrdan keyin N soat (yo'q — muddatsiz)."""
    if test.deadline_at:
        return test.deadline_at if test.deadline_at > now else None
    return now + timedelta(hours=test.queue_hours) if test.queue_hours else None


async def publish_scheduled(bot: Bot, db: Database, cfg: Config, test: Test, now: datetime) -> bool:
    return await publish(bot, db, cfg, test, scheduled_deadline(test, now), now)


def schedule_summary(test: Test) -> str:
    if test.deadline_at:
        dur = f"muddat {fmt(test.deadline_at)} gacha"
    elif test.queue_hours:
        dur = f"muddat nashrdan keyin {test.queue_hours} soat"
    else:
        dur = "♾ muddatsiz"
    return f"⏰ {fmt(test.publish_at)} da avtomatik nashr qilinadi · {dur}"
