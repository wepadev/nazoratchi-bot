"""Bosh admin: adminlarni qo'shish / olib tashlash."""
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import texts as T
from ..config import Config
from ..db import Database
from .common import IsSuper, Registered, menu

router = Router(name="superadmin")
router.message.filter(Registered(), IsSuper())
router.callback_query.filter(Registered(), IsSuper())


class AddAdmin(StatesGroup):
    target = State()


def admins_text(admins) -> str:
    if not admins:
        return f"{T.ADMINS_TITLE}\n\n{T.NO_ADMINS}"
    lines = [T.ADMINS_TITLE, ""]
    lines += [f"• {escape(a.full_name)} — <code>{a.phone}</code>" for a in admins]
    return "\n".join(lines)


async def _admins(db: Database, config: Config):
    # bosh adminlar ro'yxatda ko'rinmaydi — ularni sozlamadan boshqariladi
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
        await message.answer(T.ADMIN_USER_NOT_FOUND)
        return
    await state.clear()
    if target.is_admin:
        await message.answer(T.ADMIN_ALREADY.format(name=escape(target.full_name)),
                             reply_markup=menu(is_admin, is_super))
        return
    await db.set_role(target.id, "admin")
    await message.answer(T.ADMIN_ADDED.format(name=escape(target.full_name)),
                         reply_markup=menu(is_admin, is_super))
    try:
        await bot.send_message(target.id, T.YOU_ARE_ADMIN_NOW, reply_markup=menu(True, False))
    except Exception:
        pass


@router.callback_query(kb.AdminCb.filter(F.action == "remove"))
async def remove(call: CallbackQuery, callback_data: kb.AdminCb, db: Database, config: Config, bot: Bot):
    if callback_data.user_id in config.super_admin_ids:
        await call.answer(T.CANT_REMOVE_SUPER, show_alert=True)
        return
    target = await db.get_user(callback_data.user_id)
    if target:
        await db.set_role(target.id, "user")
        await call.answer(T.ADMIN_REMOVED.format(name=target.full_name).replace("<b>", "").replace("</b>", ""))
        try:
            await bot.send_message(target.id, T.YOU_ARE_NOT_ADMIN, reply_markup=menu(False, False))
        except Exception:
            pass
    items = await _admins(db, config)
    await call.message.edit_text(admins_text(items), reply_markup=kb.admins_kb(items))
