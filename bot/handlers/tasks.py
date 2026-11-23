"""Nazoratchi: kunlik vazifalar (ustozlardan har soatda «bajardingizmi?» deb so'raladi)."""
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import services
from .. import texts as T
from ..config import Config
from ..db import Database, User
from ..timeutil import utcnow
from .common import IsAdmin, Registered, menu
from .groups import access, deny

router = Router(name="tasks")
router.message.filter(Registered(), IsAdmin())
router.callback_query.filter(Registered(), IsAdmin())


class TaskForm(StatesGroup):
    text = State()
    day = State()


async def tasks_text(db: Database, group_id: int) -> str:
    g = await db.get_group(group_id)
    tasks = await db.list_tasks(group_id, limit=10)
    lines = [f"📋 <b>{escape(g.name)}</b> — kunlik vazifalar", ""]
    if not tasks:
        lines.append("Hali vazifa yo'q. «➕ Yangi vazifa» ni bosing: masalan, «Darslikdagi 1–20 misollarni yeching». "
                     "Ustozlar «✅ Bajardim» bosguncha bot har soatda so'rab turadi.")
    for t in tasks:
        roster = await db.task_roster(t)
        done = sum(1 for _, d in roster if d)
        lines.append(f"• {t.day[8:10]}.{t.day[5:7]} · {escape(t.text[:60])} — {done}/{len(roster)}")
    return "\n".join(lines)


@router.callback_query(kb.GroupCb.filter(F.action == "tasks"))
async def tasks_list(call: CallbackQuery, callback_data: kb.GroupCb, state: FSMContext, db: Database,
                     user: User, is_super: bool):
    await state.clear()
    g = await access(db, callback_data.group_id, user, is_super)
    if not g:
        return await deny(call)
    await call.answer()
    await call.message.edit_text(await tasks_text(db, g.id),
                                 reply_markup=kb.tasks_kb(g.id, await db.list_tasks(g.id, limit=10)))


@router.callback_query(kb.GroupCb.filter(F.action == "newtask"))
async def new_task(call: CallbackQuery, callback_data: kb.GroupCb, state: FSMContext, db: Database,
                   user: User, is_super: bool):
    g = await access(db, callback_data.group_id, user, is_super)
    if not g:
        return await deny(call)
    await state.set_state(TaskForm.text)
    await state.update_data(group_id=g.id)
    await call.answer()
    await call.message.answer("📋 Vazifani yozing. Masalan:\n<i>Darslikning 45-betidagi 1–20 misollarni yeching</i>\n"
                              "<i>Kechagi jonli dars yozuvini ko'ring</i>", reply_markup=kb.cancel_kb())


@router.message(TaskForm.text, F.text)
async def new_task_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if not (3 <= len(text) <= 500):
        return await message.answer("Vazifa matni 3–500 belgi bo'lishi kerak.")
    await state.update_data(text=text)
    await state.set_state(TaskForm.day)
    await message.answer("Qaysi kun uchun?", reply_markup=kb.task_day_kb())


@router.callback_query(TaskForm.day, kb.TaskCb.filter(F.action == "day"))
async def new_task_day(call: CallbackQuery, callback_data: kb.TaskCb, state: FSMContext, db: Database, bot: Bot,
                       config: Config, user: User, is_admin: bool, is_super: bool):
    data = await state.get_data()
    g = await access(db, data.get("group_id", 0), user, is_super)
    await state.clear()
    if not g or "text" not in data:
        return await deny(call)
    task, sent = await services.create_task(bot, db, config, g, data["text"], callback_data.arg, user, utcnow())
    await call.answer("Qo'shildi")
    when = (f"{sent} ta ustozga yuborildi" if callback_data.arg == 0 else
            f"ertaga soat {config.task_day_start_hour:02d}:00 dan ustozlardan so'raladi")
    await call.message.edit_text(f"✅ Vazifa qo'shildi: {services.task_label(task)} — {when}.\n"
                                 "Bajarmaganlardan har soatda so'raladi, kun oxirida sizga hisobot keladi.")
    await call.message.answer(T.MAIN_MENU, reply_markup=menu(is_admin, is_super))


async def task_access(db: Database, task_id: int, user: User, is_super: bool):
    t = await db.get_task(task_id)
    return t if t and await access(db, t.group_id, user, is_super) else None


@router.callback_query(kb.TaskCb.filter(F.action == "open"))
async def open_task(call: CallbackQuery, callback_data: kb.TaskCb, db: Database, user: User, is_super: bool):
    t = await task_access(db, callback_data.task_id, user, is_super)
    if not t:
        return await deny(call)
    await call.answer()
    try:
        await call.message.edit_text((await services.task_summary(db, t))[:4000], reply_markup=kb.task_admin_kb(t))
    except TelegramBadRequest:
        pass


@router.callback_query(kb.TaskCb.filter(F.action == "del"))
async def delete_task(call: CallbackQuery, callback_data: kb.TaskCb, db: Database, user: User, is_super: bool):
    t = await task_access(db, callback_data.task_id, user, is_super)
    if not t:
        return await deny(call)
    await call.answer()
    await call.message.edit_text(f"🗑 {services.task_label(t)} vazifasini o'chirasizmi? Eslatmalar to'xtaydi.",
                                 reply_markup=kb.confirm_kb(("Ha, o'chirish", kb.TaskCb(action="del_ok", task_id=t.id)),
                                                            ("Yo'q", kb.TaskCb(action="open", task_id=t.id))))


@router.callback_query(kb.TaskCb.filter(F.action == "del_ok"))
async def delete_task_ok(call: CallbackQuery, callback_data: kb.TaskCb, db: Database, user: User, is_super: bool):
    t = await task_access(db, callback_data.task_id, user, is_super)
    if not t:
        return await deny(call)
    await db.delete_task(t.id)
    await call.answer("O'chirildi")
    await call.message.edit_text(await tasks_text(db, t.group_id),
                                 reply_markup=kb.tasks_kb(t.group_id, await db.list_tasks(t.group_id, limit=10)))
