import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import texts as T
from ..db import Database, User
from .common import Registered, menu

router = Router(name="user")
router.message.filter(Registered())
router.callback_query.filter(Registered())
log = logging.getLogger(__name__)


class Join(StatesGroup):
    code = State()


@router.message(F.text == T.BTN_JOIN)
async def join_start(message: Message, state: FSMContext):
    await state.set_state(Join.code)
    await message.answer(T.ASK_CODE, reply_markup=kb.cancel_kb())


@router.message(Join.code, F.text)
async def join_code(message: Message, state: FSMContext, db: Database, bot: Bot,
                    user: User, is_admin: bool, is_super: bool):
    group = await db.get_group_by_code(message.text)
    if not group:
        await message.answer(T.CODE_NOT_FOUND)
        return
    await state.clear()
    added = await db.add_member(group.id, user.id)
    text = T.JOINED if added else T.ALREADY_MEMBER
    await message.answer(text.format(name=escape(group.name)), reply_markup=menu(is_admin, is_super))
    if added and group.owner_id != user.id:
        try:
            await bot.send_message(
                group.owner_id,
                T.NEW_MEMBER_NOTIFY.format(group=escape(group.name), name=escape(user.full_name),
                                           phone=user.phone),
            )
        except Exception:  # admin botni bloklagan bo'lishi mumkin
            log.warning("Adminga xabar yuborilmadi: %s", group.owner_id)


@router.message(F.text == T.BTN_MY_GROUPS)
async def my_groups(message: Message, db: Database, user: User):
    groups = await db.user_groups(user.id)
    if not groups:
        await message.answer(T.NO_GROUPS_USER)
        return
    lines = [T.MY_GROUPS_TITLE, ""]
    lines += [f"• <b>{escape(g.name)}</b> — {g.member_count} a'zo" for g in groups]
    await message.answer("\n".join(lines), reply_markup=kb.my_groups_kb(groups))


@router.callback_query(kb.MyGroupCb.filter(F.action == "leave"))
async def leave_group(call: CallbackQuery, callback_data: kb.MyGroupCb, db: Database, user: User):
    group = await db.get_group(callback_data.group_id)
    await db.remove_member(callback_data.group_id, user.id)
    await call.answer()
    name = escape(group.name) if group else "—"
    await call.message.edit_text(T.LEFT_GROUP.format(name=name))


@router.message(F.text == T.BTN_PROFILE)
async def profile(message: Message, db: Database, user: User, is_admin: bool, is_super: bool):
    role = T.ROLE_SUPER if is_super else T.ROLE_ADMIN if is_admin else T.ROLE_USER
    groups = await db.user_groups(user.id)
    await message.answer(
        T.PROFILE.format(name=escape(user.full_name), phone=user.phone, role=role, groups=len(groups))
    )
