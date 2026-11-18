"""Biznes-mantiq: test nashri, javoblarni qabul qilish, yakunlash, eslatmalar, reyting."""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from . import keyboards as kb
from .answers import grade, mistakes, preview
from .config import Config
from .db import Database, Group, Test, User
from .timeutil import fmt, fmt_left, is_quiet, week_start

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

def announce_text(test: Test, group: Group, cfg: Config, now: datetime) -> str:
    return (
        f"📝 <b>Yangi test: {escape(test.title)}</b>\n\n"
        f"Guruh: {escape(group.name)}\n"
        f"Test kodi: <b>{test.id}</b>\n"
        f"Savollar: {test.n} ta (A/B/C/D)\n"
        f"Muddat: <b>{fmt(test.deadline_at)}</b> gacha ({fmt_left(test.deadline_at - now)} qoldi)\n\n"
        f"Har bir to'g'ri javob: +{cfg.coins_per_correct} {COIN}\n"
        f"Topshirmaslik: −{cfg.penalty_not_submitted} {COIN}\n\n"
        f"⚡️ Tez yuborish — botga bitta xabar: <code>{test.id}*abcd...</code>\n"
        "Javoblar <b>faqat bir marta</b> qabul qilinadi."
    )


async def publish(bot: Bot, db: Database, cfg: Config, test: Test, deadline: datetime, now: datetime) -> bool:
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
        f"{sent} ta ustozga yuborildi. Muddat: {fmt(deadline)}.")
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

async def send_reminders(bot: Bot, db: Database, cfg: Config, now: datetime) -> None:
    interval = timedelta(hours=cfg.reminder_interval_hours)
    final_window = timedelta(minutes=cfg.final_reminder_minutes)
    quiet = is_quiet(now, *cfg.quiet_hours)
    for t in await db.published_tests():
        if not t.deadline_at or t.deadline_at <= now:
            continue
        left = t.deadline_at - now
        final = not t.final_reminded and left <= final_window
        regular = (not quiet and left > final_window
                   and now - (t.reminded_at or t.published_at) >= interval)
        if not (final or regular):
            continue
        icon = "🔥" if final else "⏰"
        text = (f"{icon} <b>Eslatma:</b> «{escape(t.title)}» testini hali topshirmadingiz.\n\n"
                f"Muddat: <b>{fmt(t.deadline_at)}</b> — {fmt_left(left)} qoldi.\n"
                f"Tez yuborish: <code>{t.id}*abcd...</code>\n"
                f"Topshirmaslik: −{cfg.penalty_not_submitted} {COIN}")
        for u in await db.non_submitters(t, only_before_publish=False):
            await safe_send(bot, u.id, text, kb.answer_kb(t.id))
        await db.set_reminded(t.id, now, final=final)


# ---------------- kalitni tuzatish ----------------

async def fix_key(bot: Bot, db: Database, cfg: Config, test: Test, new_key: str, admin_id: int,
                  now: datetime) -> int:
    """Kalitni yangilaydi, barcha natijalarni qayta hisoblaydi. Natijasi o'zgarganlar sonini qaytaradi."""
    await db.update_test(test.id, answer_key=new_key)
    changed = 0
    for s in await db.list_submissions(test.id):
        new = grade(s.answers, new_key)
        diff = new - s.correct
        if not diff:
            continue
        changed += 1
        await db.set_submission_correct(test.id, s.user_id, new)
        amount = diff * cfg.coins_per_correct
        await db.add_coins(s.user_id, test.group_id, amount,
                           f"«{test.title}»: kalit tuzatildi ({s.correct}→{new})", now,
                           test_id=test.id, created_by=admin_id)
        sign = "+" if amount > 0 else "−"
        await safe_send(bot, s.user_id,
                        f"🔑 «{escape(test.title)}» testining kaliti tuzatildi.\n"
                        f"Natijangiz: {s.correct} → <b>{new}</b>/{test.n} ({sign}{abs(amount)} {COIN})")
    return changed


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
    """'published' | 'queued' | 'busy' (faol test bor va aniq sana berilgan — navbatga qo'yib bo'lmaydi)."""
    if await db.active_test(test.group_id):
        if not hours:
            return "busy"
        await db.queue_test(test.id, hours, now)
        return "queued"
    dl = deadline or now + timedelta(hours=hours or 24)
    return "published" if await publish(bot, db, cfg, test, dl, now) else "busy"
