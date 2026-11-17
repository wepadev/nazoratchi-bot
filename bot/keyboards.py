from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import texts as T
from .db import Group, User


class GroupCb(CallbackData, prefix="g"):
    action: str  # open | members | newcode | rename | delete | delete_ok | list
    group_id: int = 0


class MemberCb(CallbackData, prefix="m"):
    action: str  # kick
    group_id: int
    user_id: int


class MyGroupCb(CallbackData, prefix="mg"):
    action: str  # leave
    group_id: int


class AdminCb(CallbackData, prefix="a"):
    action: str  # add | remove
    user_id: int = 0


def share_phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=T.BTN_SHARE_PHONE, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=T.BTN_CANCEL)]], resize_keyboard=True)


def main_menu(is_admin: bool, is_super: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=T.BTN_JOIN), KeyboardButton(text=T.BTN_MY_GROUPS)],
    ]
    if is_admin or is_super:
        rows.append([KeyboardButton(text=T.BTN_CREATE_GROUP), KeyboardButton(text=T.BTN_MANAGE_GROUPS)])
    last = [KeyboardButton(text=T.BTN_PROFILE)]
    if is_super:
        last.append(KeyboardButton(text=T.BTN_ADMINS))
    rows.append(last)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def groups_list_kb(groups: list[Group]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for g in groups:
        b.button(text=f"📁 {g.name} · {g.member_count}", callback_data=GroupCb(action="open", group_id=g.id))
    b.adjust(1)
    return b.as_markup()


def group_card_kb(group_id: int) -> InlineKeyboardMarkup:
    cb = lambda a: GroupCb(action=a, group_id=group_id).pack()  # noqa: E731
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=T.IB_MEMBERS, callback_data=cb("members")),
             InlineKeyboardButton(text=T.IB_NEW_CODE, callback_data=cb("newcode"))],
            [InlineKeyboardButton(text=T.IB_RENAME, callback_data=cb("rename")),
             InlineKeyboardButton(text=T.IB_DELETE, callback_data=cb("delete"))],
            [InlineKeyboardButton(text=T.IB_BACK, callback_data=GroupCb(action="list").pack())],
        ]
    )


def confirm_delete_kb(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=T.IB_YES_DELETE,
                                 callback_data=GroupCb(action="delete_ok", group_id=group_id).pack()),
            InlineKeyboardButton(text=T.IB_NO, callback_data=GroupCb(action="open", group_id=group_id).pack()),
        ]]
    )


def members_kb(group_id: int, members: list[User]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for u in members:
        b.button(text=f"{T.IB_REMOVE} {u.full_name}",
                 callback_data=MemberCb(action="kick", group_id=group_id, user_id=u.id))
    b.button(text=T.IB_BACK, callback_data=GroupCb(action="open", group_id=group_id))
    b.adjust(1)
    return b.as_markup()


def my_groups_kb(groups: list[Group]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for g in groups:
        b.button(text=f"{T.IB_LEAVE}: {g.name}", callback_data=MyGroupCb(action="leave", group_id=g.id))
    b.adjust(1)
    return b.as_markup()


def admins_kb(admins: list[User]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for u in admins:
        b.button(text=f"{T.IB_REMOVE} {u.full_name}", callback_data=AdminCb(action="remove", user_id=u.id))
    b.button(text=T.IB_ADD_ADMIN, callback_data=AdminCb(action="add"))
    b.adjust(1)
    return b.as_markup()
