"""Bosh admin: nazoratchilarni qo'shish / olib tashlash va ularning faoliyati."""
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import services
from .. import texts as T
from ..config import Config
from ..db import Database
from ..timeutil import fmt
from .common import IsSuper, Registered, menu

router = Router(name="superadmin")
router.message.filter(Registered(), IsSuper())
router.callback_query.filter(Registered(), IsSuper())


class AddAdmin(StatesGroup):
    target = State()


def admins_text(admins) -> str:
    if not admins:
        return "👮 <b>Nazoratchilar</b>\n\nHozircha nazoratchi yo'q."
    lines = ["👮 <b>Nazoratchilar</b>", ""]
    lines += [f"• {escape(a.full_name)} — <code>{a.phone}</code>" for a in admins]
    lines += ["", "Olib tashlash uchun ismni bosing. Guruhga tayinlash — guruh kartochkasida."]
    return "\n".join(lines)


async def _admins(db: Database, config: Config):
    return [a for a in await db.list_admins() if a.id not in config.super_admin_ids]


@router.message(F.text == T.BTN_ADMINS)
async def admins(message: Message, db: Database, config: Config):
    items = await _admins(db, config)
    await message.answer(admins_text(items), reply_markup=kb.admins_kb(items))


@router.callback_query(kb.AdminCb.filter(F.action == "add"))
async def add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddAdmin.target)
    await call.answer()
    await call.message.answer(T.ASK_ADMIN_PHONE, reply_markup=kb.cancel_kb())


@router.message(AddAdmin.target, F.text | F.contact)
async def add_finish(message: Message, state: FSMContext, db: Database, bot: Bot,
                     is_admin: bool, is_super: bool):
    raw = message.contact.phone_number if message.contact else message.text.strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    target = None
    if digits:
        # avval telefon raqam sifatida, topilmasa Telegram ID sifatida qidiramiz
        target = await db.get_user_by_phone(raw)
        if target is None and not raw.startswith("+"):
            target = await db.get_user(int(digits))
    if target is None:
        return await message.answer(T.ADMIN_USER_NOT_FOUND)
    await state.clear()
    if target.is_admin:
        return await message.answer(f"<b>{escape(target.full_name)}</b> allaqachon nazoratchi.",
                                    reply_markup=menu(is_admin, is_super))
    await db.set_role(target.id, "admin")
    await message.answer(f"✅ <b>{escape(target.full_name)}</b> nazoratchi qilindi.\n"
                         "Endi uni guruhga tayinlang: 🗂 Guruhlar → guruh → 👮 Nazoratchilar.",
                         reply_markup=menu(is_admin, is_super))
    await services.safe_send(bot, target.id, T.YOU_ARE_ADMIN_NOW, menu(True, False))


@router.callback_query(kb.AdminCb.filter(F.action == "remove"))
async def remove(call: CallbackQuery, callback_data: kb.AdminCb, db: Database, config: Config, bot: Bot):
    if callback_data.user_id in config.super_admin_ids:
        return await call.answer("Bosh adminni bot orqali olib bo'lmaydi.", show_alert=True)
    target = await db.get_user(callback_data.user_id)
    if target:
        await db.set_role(target.id, "user")
        await call.answer(f"{target.full_name} nazoratchilikdan olindi")
        await services.safe_send(bot, target.id, T.YOU_ARE_NOT_ADMIN, menu(False, False))
    items = await _admins(db, config)
    await call.message.edit_text(admins_text(items), reply_markup=kb.admins_kb(items))


@router.message(F.text == T.BTN_ACTIVITY)
async def activity(message: Message, db: Database, config: Config):
    rows = [r for r in await db.admin_activity() if r["id"] not in config.super_admin_ids]
    if not rows:
        return await message.answer("📈 Hali nazoratchi yo'q.")
    lines = ["📈 <b>Nazoratchilar faoliyati</b>", ""]
    for r in rows:
        avg = f"{r['avg_resolve_hours']:.1f} soat" if r["avg_resolve_hours"] is not None else "—"
        warn = " ⚠️" if r["appeals_open"] else ""
        lines += [
            f"👤 <b>{escape(r['full_name'])}</b>",
            f"   Guruhlar: {r['groups']} · Testlar: {r['tests_created']} (nashr: {r['tests_published']})",
            f"   Oxirgi test: {fmt(r['last_test'])}",
            f"   E'tirozlar: ko'rildi {r['appeals_resolved']}, ochiq {r['appeals_open']}{warn} · "
            f"o'rtacha javob: {avg}",
            f"   Qo'lda tanga: {r['manual_coins']} marta",
            "",
        ]
    await message.answer("\n".join(lines)[:4000])
