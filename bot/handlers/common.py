from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, Filter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, TelegramObject

from .. import keyboards as kb
from .. import texts as T
from ..db import Database, User

router = Router(name="common")


class Registered(Filter):
    async def __call__(self, event: TelegramObject, user: User | None = None) -> bool:
        return user is not None


class IsAdmin(Filter):
    async def __call__(self, event: TelegramObject, is_admin: bool = False) -> bool:
        return is_admin


class IsSuper(Filter):
    async def __call__(self, event: TelegramObject, is_super: bool = False) -> bool:
        return is_super


class Reg(StatesGroup):
    phone = State()
    full_name = State()


def menu(is_admin: bool, is_super: bool):
    return kb.main_menu(is_admin=is_admin, is_super=is_super)


@router.message(F.text == T.BTN_CANCEL)
@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext, user: User | None, is_admin: bool, is_super: bool):
    await state.clear()
    if user is None:
        await state.set_state(Reg.phone)
        await message.answer(T.WELCOME, reply_markup=kb.share_phone_kb())
        return
    await message.answer(T.CANCELLED, reply_markup=menu(is_admin, is_super))


# ---------------- Ro'yxatdan o'tish ----------------

@router.message(CommandStart())
async def start(message: Message, state: FSMContext, user: User | None, is_admin: bool, is_super: bool):
    await state.clear()
    if user:
        await message.answer(T.MAIN_MENU, reply_markup=menu(is_admin, is_super))
        return
    await state.set_state(Reg.phone)
    await message.answer(T.WELCOME, reply_markup=kb.share_phone_kb())


@router.message(Reg.phone, F.contact)
async def reg_phone(message: Message, state: FSMContext, db: Database):
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer(T.SHARE_OWN_CONTACT, reply_markup=kb.share_phone_kb())
        return
    other = await db.get_user_by_phone(contact.phone_number)
    if other and other.id != message.from_user.id:
        await message.answer(T.PHONE_TAKEN)
        return
    await state.update_data(phone=contact.phone_number)
    await state.set_state(Reg.full_name)
    await message.answer(T.ASK_FULL_NAME, reply_markup=kb.cancel_kb())


@router.message(Reg.phone)
async def reg_phone_wrong(message: Message):
    await message.answer(T.SHARE_OWN_CONTACT, reply_markup=kb.share_phone_kb())


@router.message(Reg.full_name, F.text)
async def reg_full_name(message: Message, state: FSMContext, db: Database, is_super: bool):
    name = " ".join(message.text.split())
    if not (3 <= len(name) <= 64):
        await message.answer(T.BAD_FULL_NAME)
        return
    data = await state.get_data()
    await state.clear()
    user = await db.create_user(
        user_id=message.from_user.id,
        phone=data["phone"],
        full_name=name,
        username=message.from_user.username,
        role="admin" if is_super else "user",
    )
    await message.answer(
        T.REGISTERED.format(name=escape(user.full_name)),
        reply_markup=menu(is_admin=user.is_admin or is_super, is_super=is_super),
    )


@router.message(StateFilter(None), ~Registered())
async def not_registered(message: Message, state: FSMContext):
    await state.set_state(Reg.phone)
    await message.answer(T.WELCOME, reply_markup=kb.share_phone_kb())
