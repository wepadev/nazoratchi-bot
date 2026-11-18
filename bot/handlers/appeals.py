"""Nazoratchi: ustozlarning e'tirozlarini ko'rib chiqish."""
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import services
from .. import texts as T
from ..config import Config
from ..db import Appeal, Database, User
from ..timeutil import fmt, utcnow
from .common import IsAdmin, Registered
from .tests_admin import start_fixkey, test_access

router = Router(name="appeals")
router.message.filter(Registered(), IsAdmin())
router.callback_query.filter(Registered(), IsAdmin())


async def appeal_text(db: Database, a: Appeal) -> str:
    t = await db.get_test(a.test_id)
    g = await db.get_group(t.group_id)
    u = await db.get_user(a.user_id)
    sub = await db.get_submission(t.id, u.id)
    lines = [f"⚖️ <b>E'tiroz #{a.id}</b> ({fmt(a.created_at)})", "",
             f"Test: «{escape(t.title)}» — {escape(g.name)}",
             f"Ustoz: {escape(u.full_name)} — <code>{u.phone}</code>"]
    if sub:
        lines.append(f"Natija: {sub.correct}/{t.n}")
        if a.question and 1 <= a.question <= t.n:
            given = sub.answers[a.question - 1]
            lines.append(f"Savol №{a.question}: ustoz — {given}, kalit — <b>{t.answer_key[a.question - 1]}</b>")
    lines += ["", f"«{escape(a.text)}»"]
    return "\n".join(lines)


@router.message(F.text == T.BTN_APPEALS)
async def list_appeals(message: Message, db: Database, user: User, is_super: bool):
    appeals = await db.open_appeals(None if is_super else user.id)
    if not appeals:
        return await message.answer("📨 Ochiq e'tiroz yo'q. 👍")
    await message.answer(f"📨 Ochiq e'tirozlar: {len(appeals)} ta")
    for a in appeals[:15]:
        await message.answer(await appeal_text(db, a), reply_markup=kb.appeal_admin_kb(a.id))


@router.callback_query(kb.AppealCb.filter())
async def resolve(call: CallbackQuery, callback_data: kb.AppealCb, db: Database, bot: Bot, config: Config,
                  state: FSMContext, user: User, is_super: bool):
    a = await db.get_appeal(callback_data.appeal_id)
    t = await test_access(db, a.test_id, user, is_super) if a else None
    if not a or not t:
        return await call.answer(T.NOT_FOUND, show_alert=True)
    now = utcnow()
    action = callback_data.action
    status = "rejected" if action == "reject" else "accepted"
    if not await db.resolve_appeal(a.id, status, user.id, now):
        return await call.answer("Bu e'tiroz allaqachon ko'rib chiqilgan.", show_alert=True)

    q = f" (№{a.question})" if a.question else ""
    if action == "accept":
        await db.add_coins(a.user_id, t.group_id, 1, f"«{t.title}»: e'tiroz qabul qilindi{q}", now,
                           test_id=t.id, created_by=user.id)
        await services.safe_send(bot, a.user_id, f"✅ «{escape(t.title)}» bo'yicha e'tirozingiz{q} qabul qilindi: +1 🪙")
        verdict = "✅ Qabul qilindi (+1 🪙)"
    elif action == "reject":
        await services.safe_send(bot, a.user_id, f"❌ «{escape(t.title)}» bo'yicha e'tirozingiz{q} rad etildi.")
        verdict = "❌ Rad etildi"
    else:
        await services.safe_send(bot, a.user_id,
                                 f"✅ «{escape(t.title)}» bo'yicha e'tirozingiz{q} qabul qilindi — kalit tuzatiladi.")
        verdict = "🔑 Kalit tuzatilmoqda"
    await call.answer()
    await call.message.edit_text(call.message.html_text + f"\n\n<b>{verdict}</b> — {escape(user.full_name)}")
    if action == "fixkey":
        await start_fixkey(call.message, state, t)
