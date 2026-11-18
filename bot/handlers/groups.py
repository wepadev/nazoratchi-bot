"""Guruhlar: yaratish (bosh admin), nazoratchi tayinlash, ustozlar, reyting, tanga, Excel."""
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .. import keyboards as kb
from .. import services
from .. import texts as T
from ..config import Config
from ..db import Database, Group, User
from ..excel import group_report
from ..timeutil import local, utcnow
from .common import IsAdmin, Registered, menu

router = Router(name="groups")
router.message.filter(Registered(), IsAdmin())
router.callback_query.filter(Registered(), IsAdmin())


class GroupForm(StatesGroup):
    name = State()
    rename = State()
    coins = State()


def valid_name(text: str | None) -> str | None:
    name = " ".join((text or "").split())
    return name if 2 <= len(name) <= 64 else None


async def access(db: Database, group_id: int, user: User, is_super: bool) -> Group | None:
    """Guruhni bosh admin yoki unga tayinlangan nazoratchi boshqaradi."""
    group = await db.get_group(group_id)
    if group and (is_super or await db.is_group_admin(group_id, user.id)):
        return group
    return None


async def card_text(db: Database, g: Group) -> str:
    admins = await db.group_admins(g.id)
    active = await db.active_test(g.id)
    lines = [f"📁 <b>{escape(g.name)}</b>", "",
             f"Qo'shilish kodi: <code>{g.code}</code>",
             f"Ustozlar: {g.member_count} ta",
             "Nazoratchilar: " + (", ".join(escape(a.full_name) for a in admins) if admins else "— tayinlanmagan")]
    if active:
        lines.append(f"Faol test: «{escape(active.title)}»")
    return "\n".join(lines)


async def show_card(call: CallbackQuery, db: Database, g: Group, is_super: bool) -> None:
    await call.message.edit_text(await card_text(db, g), reply_markup=kb.group_kb(g.id, is_super))


async def deny(call: CallbackQuery) -> None:
    await call.answer(T.NOT_FOUND, show_alert=True)


# ---------- ro'yxat ----------

async def _groups(db: Database, user: User, is_super: bool):
    return await db.list_groups(None if is_super else user.id)


@router.message(F.text == T.BTN_GROUPS)
async def list_groups(message: Message, db: Database, user: User, is_super: bool):
    groups = await _groups(db, user, is_super)
    if not groups:
        await message.answer(T.NO_GROUPS_SUPER if is_super else T.NO_GROUPS_ADMIN)
        return
    await message.answer(T.GROUPS_TITLE, reply_markup=kb.groups_kb(groups))


@router.callback_query(kb.GroupCb.filter(F.action == "list"))
async def back_to_list(call: CallbackQuery, db: Database, user: User, is_super: bool):
    groups = await _groups(db, user, is_super)
    await call.answer()
    if not groups:
        await call.message.edit_text(T.NO_GROUPS_SUPER if is_super else T.NO_GROUPS_ADMIN)
    else:
        await call.message.edit_text(T.GROUPS_TITLE, reply_markup=kb.groups_kb(groups))


@router.callback_query(kb.GroupCb.filter(F.action == "open"))
async def open_group(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool,
                     state: FSMContext):
    await state.clear()
    g = await access(db, callback_data.group_id, user, is_super)
    if not g:
        return await deny(call)
    await call.answer()
    await show_card(call, db, g, is_super)


# ---------- yaratish (bosh admin) ----------

@router.message(F.text == T.BTN_CREATE_GROUP)
async def create_start(message: Message, state: FSMContext, is_super: bool):
    if not is_super:
        return
    await state.set_state(GroupForm.name)
    await message.answer(T.ASK_GROUP_NAME, reply_markup=kb.cancel_kb())


@router.message(GroupForm.name, F.text)
async def create_finish(message: Message, state: FSMContext, db: Database, user: User,
                        is_admin: bool, is_super: bool):
    if not is_super:
        return
    name = valid_name(message.text)
    if not name:
        return await message.answer(T.BAD_NAME)
    await state.clear()
    g = await db.create_group(name, user.id)
    await message.answer(f"✅ Guruh yaratildi: <b>{escape(g.name)}</b>\nKod: <code>{g.code}</code>",
                         reply_markup=menu(is_admin, is_super))
    admins = await db.list_admins()
    await message.answer("Endi guruhga nazoratchi tayinlang 👇",
                         reply_markup=kb.assign_kb(g.id, admins, set()))


# ---------- nazoratchi tayinlash (bosh admin) ----------

@router.callback_query(kb.GroupCb.filter(F.action == "admins"))
async def admins_menu(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, is_super: bool):
    if not is_super:
        return await deny(call)
    admins = await db.list_admins()
    assigned = {a.id for a in await db.group_admins(callback_data.group_id)}
    await call.answer()
    text = ("👮 Nazoratchilarni belgilang (bir nechta bo'lishi mumkin):" if admins else
            "Hali nazoratchi yo'q. Avval «👮 Nazoratchilar» menyusidan qo'shing.")
    await call.message.edit_text(text, reply_markup=kb.assign_kb(callback_data.group_id, admins, assigned))


@router.callback_query(kb.AssignCb.filter())
async def toggle_assign(call: CallbackQuery, callback_data: kb.AssignCb, db: Database, bot: Bot, is_super: bool):
    if not is_super:
        return await deny(call)
    g = await db.get_group(callback_data.group_id)
    if not g:
        return await deny(call)
    gid, aid = callback_data.group_id, callback_data.admin_id
    if await db.is_group_admin(gid, aid):
        await db.unassign_admin(gid, aid)
        await call.answer("Olib tashlandi")
    else:
        await db.assign_admin(gid, aid)
        await call.answer("Tayinlandi ✅")
        await services.safe_send(bot, aid, T.YOU_ASSIGNED.format(name=escape(g.name)))
    admins = await db.list_admins()
    assigned = {a.id for a in await db.group_admins(gid)}
    await call.message.edit_reply_markup(reply_markup=kb.assign_kb(gid, admins, assigned))


# ---------- ustozlar ----------

@router.callback_query(kb.GroupCb.filter(F.action == "members"))
async def members(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool):
    g = await access(db, callback_data.group_id, user, is_super)
    if not g:
        return await deny(call)
    users = await db.list_members(g.id)
    await call.answer()
    if not users:
        text = f"👥 <b>{escape(g.name)}</b>\n\nHali ustoz yo'q. Kodni tarqating: <code>{g.code}</code>"
    else:
        lines = [f"👥 <b>{escape(g.name)}</b> — ustozlar ({len(users)}):", ""]
        for i, u in enumerate(users, 1):
            uname = f" @{u.username}" if u.username else ""
            lines.append(f"{i}. {escape(u.full_name)} — <code>{u.phone}</code>{uname}")
        lines += ["", "Guruhdan chiqarish uchun ismni bosing."]
        text = "\n".join(lines)[:4000]
    await call.message.edit_text(text, reply_markup=kb.members_kb(g.id, users, "kick"))


@router.callback_query(kb.MemberCb.filter(F.action == "kick"))
async def kick_ask(call: CallbackQuery, callback_data: kb.MemberCb, db: Database, user: User, is_super: bool):
    g = await access(db, callback_data.group_id, user, is_super)
    target = await db.get_user(callback_data.user_id)
    if not g or not target:
        return await deny(call)
    await call.answer()
    await call.message.edit_text(f"⚠️ <b>{escape(target.full_name)}</b> ni «{escape(g.name)}» guruhidan chiqarasizmi?",
                                 reply_markup=kb.confirm_kick_kb(g.id, target.id))


@router.callback_query(kb.MemberCb.filter(F.action == "kick_ok"))
async def kick(call: CallbackQuery, callback_data: kb.MemberCb, db: Database, user: User, is_super: bool):
    g = await access(db, callback_data.group_id, user, is_super)
    if not g:
        return await deny(call)
    await db.remove_member(g.id, callback_data.user_id)
    await call.answer("Chiqarildi")
    g = await db.get_group(g.id)
    await show_card(call, db, g, is_super)


# ---------- kod ----------

@router.callback_query(kb.GroupCb.filter(F.action == "code"))
async def new_code(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool):
    g = await access(db, callback_data.group_id, user, is_super)
    if not g:
        return await deny(call)
    g.code = await db.regenerate_code(g.id)
    await call.answer("Yangi kod yaratildi. Eski kod endi ishlamaydi.", show_alert=True)
    await show_card(call, db, g, is_super)


# ---------- reyting ----------

@router.callback_query(kb.GroupCb.filter(F.action == "rating"))
async def rating(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool):
    await _rating(call, db, user, is_super, callback_data.group_id, "all")


@router.callback_query(kb.RatingCb.filter(F.admin))
async def rating_period(call: CallbackQuery, callback_data: kb.RatingCb, db: Database, user: User, is_super: bool):
    await _rating(call, db, user, is_super, callback_data.group_id, callback_data.period)


async def _rating(call: CallbackQuery, db: Database, user: User, is_super: bool, group_id: int, period: str):
    g = await access(db, group_id, user, is_super)
    if not g:
        return await deny(call)
    text = await services.rating_text(db, g, period, utcnow(), limit=50)
    await call.answer()
    await call.message.edit_text(text[:4000], reply_markup=kb.rating_kb(g.id, period, admin=True))


# ---------- Excel ----------

@router.callback_query(kb.GroupCb.filter(F.action == "excel"))
async def excel(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool):
    g = await access(db, callback_data.group_id, user, is_super)
    if not g:
        return await deny(call)
    await call.answer("Tayyorlanmoqda…")
    now = utcnow()
    data = await group_report(db, g, now)
    safe = re.sub(r"[^\w\-]+", "_", g.name).strip("_") or "guruh"
    fname = f"{safe}_{local(now):%Y-%m-%d}.xlsx"
    await call.message.answer_document(
        BufferedInputFile(data, filename=fname),
        caption=f"📥 <b>{escape(g.name)}</b>: reyting, natijalar, savollar tahlili, tangalar tarixi")


# ---------- tanga berish / ayirish ----------

@router.callback_query(kb.GroupCb.filter(F.action == "coins"))
async def coins_menu(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool):
    g = await access(db, callback_data.group_id, user, is_super)
    if not g:
        return await deny(call)
    users = await db.list_members(g.id)
    await call.answer()
    await call.message.edit_text("🪙 Kimga tanga berasiz yoki ayirasiz?" if users else "Guruhda ustoz yo'q.",
                                 reply_markup=kb.members_kb(g.id, users, "coin"))


@router.callback_query(kb.MemberCb.filter(F.action == "coin"))
async def coins_ask(call: CallbackQuery, callback_data: kb.MemberCb, state: FSMContext, db: Database,
                    user: User, is_super: bool):
    g = await access(db, callback_data.group_id, user, is_super)
    target = await db.get_user(callback_data.user_id)
    if not g or not target:
        return await deny(call)
    await state.set_state(GroupForm.coins)
    await state.update_data(group_id=g.id, user_id=target.id)
    await call.answer()
    await call.message.answer(T.ASK_COINS.format(name=escape(target.full_name)), reply_markup=kb.cancel_kb())


@router.message(GroupForm.coins, F.text)
async def coins_finish(message: Message, state: FSMContext, db: Database, bot: Bot, user: User,
                       is_admin: bool, is_super: bool):
    m = re.fullmatch(r"\s*([+-]?\d{1,4})\s+(.{3,200})", message.text, re.S)
    if not m or int(m.group(1)) == 0:
        return await message.answer(T.BAD_COINS)
    data = await state.get_data()
    g = await access(db, data.get("group_id", 0), user, is_super)
    await state.clear()
    if not g:
        return await message.answer(T.NOT_FOUND, reply_markup=menu(is_admin, is_super))
    amount, reason = int(m.group(1)), " ".join(m.group(2).split())
    await db.add_coins(data["user_id"], g.id, amount, reason, utcnow(), created_by=user.id)
    target = await db.get_user(data["user_id"])
    sign = "+" if amount > 0 else "−"
    await message.answer(f"✅ {escape(target.full_name)}: {sign}{abs(amount)} 🪙 ({escape(reason)})",
                         reply_markup=menu(is_admin, is_super))
    await services.safe_send(bot, target.id,
                             f"🪙 <b>{sign}{abs(amount)} tanga</b> ({escape(g.name)})\nSabab: {escape(reason)}")


# ---------- nomini o'zgartirish / o'chirish (bosh admin) ----------

@router.callback_query(kb.GroupCb.filter(F.action == "rename"))
async def rename_start(call: CallbackQuery, callback_data: kb.GroupCb, state: FSMContext, is_super: bool):
    if not is_super:
        return await deny(call)
    await state.set_state(GroupForm.rename)
    await state.update_data(group_id=callback_data.group_id)
    await call.answer()
    await call.message.answer("Guruhning yangi nomini yozing:", reply_markup=kb.cancel_kb())


@router.message(GroupForm.rename, F.text)
async def rename_finish(message: Message, state: FSMContext, db: Database, is_admin: bool, is_super: bool):
    if not is_super:
        return
    name = valid_name(message.text)
    if not name:
        return await message.answer(T.BAD_NAME)
    data = await state.get_data()
    await state.clear()
    await db.rename_group(data["group_id"], name)
    await message.answer(f"✏️ Yangi nom: <b>{escape(name)}</b>", reply_markup=menu(is_admin, is_super))


@router.callback_query(kb.GroupCb.filter(F.action == "delete"))
async def delete_ask(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, is_super: bool):
    g = await db.get_group(callback_data.group_id)
    if not is_super or not g:
        return await deny(call)
    await call.answer()
    await call.message.edit_text(
        f"⚠️ <b>{escape(g.name)}</b> guruhini o'chirasizmi?\n"
        "Testlar, natijalar va tangalar ham butunlay o'chadi. Avval Excel'ni yuklab oling.",
        reply_markup=kb.confirm_group_delete_kb(g.id))


@router.callback_query(kb.GroupCb.filter(F.action == "delete_ok"))
async def delete_ok(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, is_super: bool):
    if not is_super:
        return await deny(call)
    await db.delete_group(callback_data.group_id)
    await call.answer("O'chirildi")
    await call.message.edit_text("🗑 Guruh o'chirildi.")
