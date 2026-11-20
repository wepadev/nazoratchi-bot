"""Nazoratchi: jonli dars ochish (4 xonali kod), davomat statistikasi va Excel."""
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .. import keyboards as kb
from .. import services
from .. import texts as T
from ..config import Config
from ..db import Database, User
from ..excel import attendance_report
from ..timeutil import local, utcnow
from .common import IsAdmin, Registered, menu
from .groups import access, deny

router = Router(name="lessons")
router.message.filter(Registered(), IsAdmin())
router.callback_query.filter(Registered(), IsAdmin())


class LessonForm(StatesGroup):
    code = State()
    duration = State()
    video = State()


async def lessons_text(db: Database, group_id: int, now) -> str:
    g = await db.get_group(group_id)
    lessons = await db.list_lessons(group_id, limit=10)
    lines = [f"🎥 <b>{escape(g.name)}</b> — jonli darslar", ""]
    if not lessons:
        lines.append("Hali jonli dars yo'q. «➕ Yangi jonli dars» ni bosing: 4 xonali kod qo'yasiz, "
                     "dars oxirida uni aytasiz, ustozlar botga yozadi.")
    for l in lessons:
        roster = await db.lesson_roster(l)
        present = sum(1 for _, p in roster if p)
        mark = "🟢" if l.is_open(now) else "✅"
        lines.append(f"{mark} {local(l.created_at):%d.%m} · {escape(l.title)} — {present}/{len(roster)}")
    return "\n".join(lines)


@router.callback_query(kb.GroupCb.filter(F.action == "lessons"))
async def lessons(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool,
                  state: FSMContext):
    await state.clear()
    g = await access(db, callback_data.group_id, user, is_super)
    if not g:
        return await deny(call)
    now = utcnow()
    await call.answer()
    await call.message.edit_text(await lessons_text(db, g.id, now),
                                 reply_markup=kb.lessons_kb(g.id, await db.list_lessons(g.id, limit=10), now))


# ---------- yangi dars ----------

@router.callback_query(kb.GroupCb.filter(F.action == "newlesson"))
async def new_lesson(call: CallbackQuery, callback_data: kb.GroupCb, state: FSMContext, db: Database,
                     user: User, is_super: bool):
    g = await access(db, callback_data.group_id, user, is_super)
    if not g:
        return await deny(call)
    await state.set_state(LessonForm.code)
    await state.update_data(group_id=g.id)
    await call.answer()
    await call.message.answer(T.ASK_LESSON_CODE, reply_markup=kb.lesson_code_kb())


@router.message(LessonForm.code, F.text)
async def new_lesson_code(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    now = utcnow()
    if message.text == T.BTN_AUTO_CODE:
        code = await services.new_lesson_code(db, data["group_id"], now)
    else:
        code = re.sub(r"\s+", "", message.text)
        if not services.valid_lesson_code(code):
            return await message.answer(T.BAD_LESSON_CODE)
        if await db.open_code_in_group(data["group_id"], code, now):
            return await message.answer(T.LESSON_CODE_BUSY)
    await state.update_data(code=code)
    await state.set_state(LessonForm.duration)
    await message.answer(T.ASK_LESSON_DURATION.format(code=code),
                         reply_markup=kb.lesson_duration_kb(services.LESSON_DURATIONS))


@router.callback_query(LessonForm.duration, kb.LessonCb.filter(F.action == "dur"))
async def new_lesson_duration(call: CallbackQuery, callback_data: kb.LessonCb, state: FSMContext, db: Database,
                              user: User, is_admin: bool, is_super: bool):
    data = await state.get_data()
    g = await access(db, data.get("group_id", 0), user, is_super)
    await state.clear()
    if not g:
        return await deny(call)
    now = utcnow()
    if await db.open_code_in_group(g.id, data["code"], now):
        await call.answer(T.LESSON_CODE_BUSY, show_alert=True)
        return
    lesson = await db.create_lesson(g.id, "Jonli dars", data["code"], user.id, now,
                                    services.lesson_closes_at(now, callback_data.arg))
    await call.answer("Dars ochildi")
    await call.message.edit_text(
        f"🎥 Jonli dars ochildi: <b>{escape(g.name)}</b>\n\n"
        f"Kod: <code>{lesson.code}</code> — dars oxirida ayting.\n"
        f"Kod <b>{local(lesson.closes_at):%H:%M}</b> gacha ishlaydi. Ustozlar uni botga yozib yuboradi.\n"
        f"Yopilganda qatnashmaganlar ro'yxati sizga keladi.",
        reply_markup=kb.lesson_kb(lesson, now))
    await call.message.answer(T.MAIN_MENU, reply_markup=menu(is_admin, is_super))


# ---------- dars kartochkasi ----------

async def lesson_access(db: Database, lesson_id: int, user: User, is_super: bool):
    lesson = await db.get_lesson(lesson_id)
    if lesson and await access(db, lesson.group_id, user, is_super):
        return lesson
    return None


@router.callback_query(kb.LessonCb.filter(F.action == "open"))
async def open_lesson(call: CallbackQuery, callback_data: kb.LessonCb, db: Database, user: User, is_super: bool):
    lesson = await lesson_access(db, callback_data.lesson_id, user, is_super)
    if not lesson:
        return await deny(call)
    now = utcnow()
    await call.answer()
    try:
        await call.message.edit_text((await services.lesson_summary(db, lesson, now))[:4000],
                                     reply_markup=kb.lesson_kb(lesson, now))
    except TelegramBadRequest:
        pass  # o'zgarish yo'q


@router.callback_query(kb.LessonCb.filter(F.action == "close"))
async def close_lesson(call: CallbackQuery, callback_data: kb.LessonCb, db: Database, bot: Bot, config: Config,
                       user: User, is_super: bool):
    lesson = await lesson_access(db, callback_data.lesson_id, user, is_super)
    if not lesson:
        return await deny(call)
    now = utcnow()
    await services.close_lesson(bot, db, config, lesson, now)
    await call.answer("Kod yopildi")
    lesson = await db.get_lesson(lesson.id)
    await call.message.edit_text((await services.lesson_summary(db, lesson, now))[:4000],
                                 reply_markup=kb.lesson_kb(lesson, now))


@router.callback_query(kb.LessonCb.filter(F.action == "xls"))
async def excel(call: CallbackQuery, db: Database, user: User, is_super: bool):
    groups = await db.list_groups(None if is_super else user.id)
    if not groups:
        return await deny(call)
    await call.answer("Tayyorlanmoqda…")
    now = utcnow()
    data = await attendance_report(db, groups, now)
    await call.message.answer_document(
        BufferedInputFile(data, filename=f"davomat_{local(now):%Y-%m-%d}.xlsx"),
        caption=f"🎥 Jonli darslar davomati: {len(groups)} ta guruh, barchasi bitta faylda")


# ---------- dars yozuvi (YouTube) ----------

@router.callback_query(kb.LessonCb.filter(F.action == "video"))
async def video_start(call: CallbackQuery, callback_data: kb.LessonCb, state: FSMContext, db: Database,
                      user: User, is_super: bool):
    lesson = await lesson_access(db, callback_data.lesson_id, user, is_super)
    if not lesson:
        return await deny(call)
    await state.set_state(LessonForm.video)
    await state.update_data(lesson_id=lesson.id)
    await call.answer()
    await call.message.answer(T.ASK_VIDEO_URL, reply_markup=kb.cancel_kb())


@router.message(LessonForm.video, F.text)
async def video_finish(message: Message, state: FSMContext, db: Database, bot: Bot, user: User,
                       is_admin: bool, is_super: bool):
    data = await state.get_data()
    lesson = await lesson_access(db, data.get("lesson_id", 0), user, is_super)
    if not lesson:
        await state.clear()
        return await message.answer(T.NOT_FOUND, reply_markup=menu(is_admin, is_super))
    try:
        url = None if message.text.strip() == "-" else services.clean_video_url(message.text)
    except ValueError as e:
        return await message.answer(f"❌ {e}")
    await state.clear()
    await db.set_lesson_video(lesson.id, url)
    lesson = await db.get_lesson(lesson.id)
    if not url:
        return await message.answer("📺 Yozuv olib tashlandi.", reply_markup=menu(is_admin, is_super))
    sent = await services.announce_recording(bot, db, lesson)
    await message.answer(f"📺 Yozuv saqlandi va {sent} ta ustozga yuborildi.", reply_markup=menu(is_admin, is_super))
    now = utcnow()
    await message.answer((await services.lesson_summary(db, lesson, now))[:4000], reply_markup=kb.lesson_kb(lesson, now))
