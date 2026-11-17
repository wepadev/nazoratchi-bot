"""Admin: guruh yaratish va boshqarish."""
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import texts as T
from ..db import Database, Group, User
from .common import IsAdmin, Registered, menu

router = Router(name="admin")
router.message.filter(Registered(), IsAdmin())
router.callback_query.filter(Registered(), IsAdmin())


class GroupForm(StatesGroup):
    name = State()
    rename = State()


def valid_name(text: str | None) -> str | None:
    name = " ".join((text or "").split())
    return name if 2 <= len(name) <= 64 else None


async def own_group(db: Database, group_id: int, user: User, is_super: bool) -> Group | None:
    """Guruhni faqat egasi yoki bosh admin boshqara oladi."""
    group = await db.get_group(group_id)
    if group and (group.owner_id == user.id or is_super):
        return group
    return None


def card_text(g: Group) -> str:
    return T.GROUP_CARD.format(name=escape(g.name), code=g.code, count=g.member_count)


# ---------- Yaratish ----------

@router.message(F.text == T.BTN_CREATE_GROUP)
async def create_start(message: Message, state: FSMContext):
    await state.set_state(GroupForm.name)
    await message.answer(T.ASK_GROUP_NAME, reply_markup=kb.cancel_kb())


@router.message(GroupForm.name, F.text)
async def create_finish(message: Message, state: FSMContext, db: Database, user: User,
                        is_admin: bool, is_super: bool):
    name = valid_name(message.text)
    if not name:
        await message.answer(T.BAD_GROUP_NAME)
        return
    await state.clear()
    group = await db.create_group(name, user.id)
    await message.answer(
        T.GROUP_CREATED.format(name=escape(group.name), code=group.code, btn=T.BTN_JOIN),
        reply_markup=menu(is_admin, is_super),
    )


# ---------- Ro'yxat va kartochka ----------

async def _groups_for(db: Database, user: User, is_super: bool) -> list[Group]:
    return await db.list_groups(None if is_super else user.id)


@router.message(F.text == T.BTN_MANAGE_GROUPS)
async def list_groups(message: Message, db: Database, user: User, is_super: bool):
    groups = await _groups_for(db, user, is_super)
    if not groups:
        await message.answer(T.NO_GROUPS_ADMIN)
        return
    await message.answer(T.GROUPS_TITLE, reply_markup=kb.groups_list_kb(groups))


@router.callback_query(kb.GroupCb.filter(F.action == "list"))
async def back_to_list(call: CallbackQuery, db: Database, user: User, is_super: bool):
    groups = await _groups_for(db, user, is_super)
    await call.answer()
    if not groups:
        await call.message.edit_text(T.NO_GROUPS_ADMIN)
        return
    await call.message.edit_text(T.GROUPS_TITLE, reply_markup=kb.groups_list_kb(groups))


@router.callback_query(kb.GroupCb.filter(F.action == "open"))
async def open_group(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool):
    group = await own_group(db, callback_data.group_id, user, is_super)
    if not group:
        await call.answer(T.NOT_FOUND, show_alert=True)
        return
    await call.answer()
    await call.message.edit_text(card_text(group), reply_markup=kb.group_card_kb(group.id))


@router.callback_query(kb.GroupCb.filter(F.action == "members"))
async def members(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool):
    group = await own_group(db, callback_data.group_id, user, is_super)
    if not group:
        await call.answer(T.NOT_FOUND, show_alert=True)
        return
    users = await db.list_members(group.id)
    await call.answer()
    if not users:
        text = T.NO_MEMBERS
    else:
        lines = [T.MEMBERS_TITLE.format(name=escape(group.name), count=len(users)), ""]
        for i, u in enumerate(users, 1):
            uname = f" @{u.username}" if u.username else ""
            lines.append(f"{i}. {escape(u.full_name)} — <code>{u.phone}</code>{uname}")
        text = "\n".join(lines)
    await call.message.edit_text(text, reply_markup=kb.members_kb(group.id, users))


@router.callback_query(kb.MemberCb.filter(F.action == "kick"))
async def kick(call: CallbackQuery, callback_data: kb.MemberCb, db: Database, user: User, is_super: bool):
    group = await own_group(db, callback_data.group_id, user, is_super)
    if not group:
        await call.answer(T.NOT_FOUND, show_alert=True)
        return
    await db.remove_member(group.id, callback_data.user_id)
    await call.answer(T.MEMBER_REMOVED)
    users = await db.list_members(group.id)
    await call.message.edit_reply_markup(reply_markup=kb.members_kb(group.id, users))


@router.callback_query(kb.GroupCb.filter(F.action == "newcode"))
async def new_code(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool):
    group = await own_group(db, callback_data.group_id, user, is_super)
    if not group:
        await call.answer(T.NOT_FOUND, show_alert=True)
        return
    code = await db.regenerate_code(group.id)
    group.code = code
    await call.answer()
    await call.message.edit_text(
        card_text(group) + "\n\n" + T.CODE_REGENERATED.format(code=code),
        reply_markup=kb.group_card_kb(group.id),
    )


# ---------- Nomini o'zgartirish ----------

@router.callback_query(kb.GroupCb.filter(F.action == "rename"))
async def rename_start(call: CallbackQuery, callback_data: kb.GroupCb, state: FSMContext,
                       db: Database, user: User, is_super: bool):
    group = await own_group(db, callback_data.group_id, user, is_super)
    if not group:
        await call.answer(T.NOT_FOUND, show_alert=True)
        return
    await state.set_state(GroupForm.rename)
    await state.update_data(group_id=group.id)
    await call.answer()
    await call.message.answer(T.ASK_RENAME, reply_markup=kb.cancel_kb())


@router.message(GroupForm.rename, F.text)
async def rename_finish(message: Message, state: FSMContext, db: Database, user: User,
                        is_admin: bool, is_super: bool):
    name = valid_name(message.text)
    if not name:
        await message.answer(T.BAD_GROUP_NAME)
        return
    data = await state.get_data()
    await state.clear()
    group = await own_group(db, data.get("group_id", 0), user, is_super)
    if not group:
        await message.answer(T.NOT_FOUND, reply_markup=menu(is_admin, is_super))
        return
    await db.rename_group(group.id, name)
    await message.answer(T.RENAMED.format(name=escape(name)), reply_markup=menu(is_admin, is_super))


# ---------- O'chirish ----------

@router.callback_query(kb.GroupCb.filter(F.action == "delete"))
async def delete_ask(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool):
    group = await own_group(db, callback_data.group_id, user, is_super)
    if not group:
        await call.answer(T.NOT_FOUND, show_alert=True)
        return
    await call.answer()
    await call.message.edit_text(T.CONFIRM_DELETE.format(name=escape(group.name)),
                                 reply_markup=kb.confirm_delete_kb(group.id))


@router.callback_query(kb.GroupCb.filter(F.action == "delete_ok"))
async def delete_ok(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool):
    group = await own_group(db, callback_data.group_id, user, is_super)
    if not group:
        await call.answer(T.NOT_FOUND, show_alert=True)
        return
    await db.delete_group(group.id)
    await call.answer(T.GROUP_DELETED)
    await call.message.edit_text(T.GROUP_DELETED)
