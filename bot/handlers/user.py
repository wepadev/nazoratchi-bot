"""Ustoz: guruhga qo'shilish, test javoblarini yuborish, reyting, profil, e'tiroz."""
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import services
from .. import texts as T
from ..answers import AnswerError, looks_like_answers, parse_answers, preview, split_quick
from ..config import Config
from ..db import Database, Test, User
from ..timeutil import fmt, fmt_left, utcnow
from .appeals import appeal_text
from .common import Registered, menu

router = Router(name="user")
router.message.filter(Registered())
router.callback_query.filter(Registered())


class Join(StatesGroup):
    code = State()


class Answer(StatesGroup):
    text = State()
    confirm = State()


class AppealForm(StatesGroup):
    text = State()


class Attend(StatesGroup):
    code = State()


# ---------------- guruhga qo'shilish ----------------

@router.message(F.text == T.BTN_JOIN)
async def join_start(message: Message, state: FSMContext):
    await state.set_state(Join.code)
    await message.answer(T.ASK_CODE, reply_markup=kb.cancel_kb())


@router.message(Join.code, F.text)
async def join_code(message: Message, state: FSMContext, db: Database, bot: Bot, config: Config,
                    user: User, is_admin: bool, is_super: bool):
    group = await db.get_group_by_code(message.text)
    if not group:
        return await message.answer(T.CODE_NOT_FOUND)
    await state.clear()
    added = await db.add_member(group.id, user.id, utcnow())
    text = (T.JOINED if added else T.ALREADY_MEMBER).format(name=escape(group.name))
    active = await db.active_test(group.id)
    if added and active:
        text += f"\n\n📝 Guruhda faol test bor: «{escape(active.title)}». «{T.BTN_TESTS}» bo'limiga kiring."
    await message.answer(text, reply_markup=menu(is_admin, is_super))
    if added:
        await services.notify_admins(bot, db, config, group.id, T.NEW_MEMBER_NOTIFY.format(
            group=escape(group.name), name=escape(user.full_name), phone=user.phone))


@router.message(F.text == T.BTN_MY_GROUPS)
async def my_groups(message: Message, db: Database, user: User):
    groups = await db.user_groups(user.id)
    if not groups:
        return await message.answer(T.NO_GROUPS_USER)
    lines = ["📚 <b>Guruhlarim</b>", ""] + [f"• <b>{escape(g.name)}</b> — {g.member_count} ustoz" for g in groups]
    await message.answer("\n".join(lines), reply_markup=kb.my_groups_kb(groups))


@router.callback_query(kb.MyGroupCb.filter(F.action == "leave"))
async def leave_ask(call: CallbackQuery, callback_data: kb.MyGroupCb, db: Database):
    g = await db.get_group(callback_data.group_id)
    if not g:
        return await call.answer(T.NOT_FOUND, show_alert=True)
    await call.answer()
    await call.message.edit_text(T.CONFIRM_LEAVE.format(name=escape(g.name)), reply_markup=kb.confirm_kb(
        ("Ha, chiqish", kb.MyGroupCb(action="leave_ok", group_id=g.id)),
        ("Yo'q", kb.MyGroupCb(action="rating", group_id=g.id))))


@router.callback_query(kb.MyGroupCb.filter(F.action == "leave_ok"))
async def leave(call: CallbackQuery, callback_data: kb.MyGroupCb, db: Database, user: User):
    g = await db.get_group(callback_data.group_id)
    await db.remove_member(callback_data.group_id, user.id)
    await call.answer()
    await call.message.edit_text(T.LEFT_GROUP.format(name=escape(g.name) if g else "—"))


# ---------------- testlar ----------------

@router.message(F.text == T.BTN_TESTS)
async def my_tests(message: Message, db: Database, user: User):
    tests = await db.user_open_tests(user.id)
    if not tests:
        return await message.answer(T.NO_ACTIVE_TESTS)
    now = utcnow()
    for t in tests:
        sub = await db.get_submission(t.id, user.id)
        head = f"📝 <b>{escape(t.title)}</b> — {t.n} ta savol\nMuddat: {fmt(t.deadline_at)} ({fmt_left(t.deadline_at - now)} qoldi)"
        if sub:
            await message.answer(f"{head}\n\n✅ Topshirilgan: <b>{sub.correct}/{t.n}</b>")
        else:
            await services.send_test(message.bot, user.id, t, head + "\n\n❗️ Hali topshirilmagan", kb.answer_kb(t.id))


async def _open_test_for(db: Database, test_id: int, user: User) -> tuple[Test | None, str | None]:
    t = await db.get_test(test_id)
    if not t or t.status != "published" or t.deadline_at <= utcnow() or not await db.is_member(t.group_id, user.id):
        return None, T.TEST_NOT_ACTIVE
    sub = await db.get_submission(t.id, user.id)
    if sub:
        return None, T.ALREADY_SUBMITTED.format(correct=sub.correct, n=t.n)
    return t, None


@router.callback_query(kb.TestCb.filter(F.action.in_({"answer", "retry"})))
async def answer_start(call: CallbackQuery, callback_data: kb.TestCb, state: FSMContext, db: Database, user: User):
    t, err = await _open_test_for(db, callback_data.test_id, user)
    if err:
        return await call.answer(err, show_alert=True)
    await state.set_state(Answer.text)
    await state.update_data(test_id=t.id)
    await call.answer()
    await call.message.answer(
        T.ASK_ANSWERS.format(title=escape(t.title), n=t.n, deadline=fmt(t.deadline_at),
                             left=fmt_left(t.deadline_at - utcnow()), code=t.id),
        reply_markup=kb.cancel_kb())


@router.message(Answer.text, F.text)
async def answer_text(message: Message, state: FSMContext, db: Database, user: User):
    data = await state.get_data()
    t, err = await _open_test_for(db, data.get("test_id", 0), user)
    if err:
        await state.clear()
        return await message.answer(err)
    _, body = split_quick(message.text)
    await _ask_confirm(message, state, t, body)


async def _ask_confirm(message: Message, state: FSMContext, t: Test, text: str) -> None:
    """Javoblarni o'qib, tasdiqlash uchun ko'rsatadi (xato bo'lsa — sababini aytadi)."""
    try:
        answers = parse_answers(text, t.n, allow_blank=True)
    except AnswerError as e:
        await state.set_state(Answer.text)
        await state.update_data(test_id=t.id)
        return await message.answer(f"❌ «{escape(t.title)}»: {e}\n\nQaytadan yuboring.")
    blanks = [str(i + 1) for i, ch in enumerate(answers) if ch == "-"]
    blank_note = f"Javobsiz savollar: {', '.join(blanks)}\n" if blanks else ""
    await state.set_state(Answer.confirm)
    await state.update_data(test_id=t.id, answers=answers)
    await message.answer(f"📝 <b>{escape(t.title)}</b>\n" + T.CONFIRM_ANSWERS.format(preview=preview(answers), blank=blank_note),
                         reply_markup=kb.confirm_answers_kb(t.id))


@router.callback_query(kb.TestCb.filter(F.action == "confirm"))
async def answer_confirm(call: CallbackQuery, callback_data: kb.TestCb, state: FSMContext, db: Database,
                         config: Config, user: User, is_admin: bool, is_super: bool):
    data = await state.get_data()
    if data.get("test_id") != callback_data.test_id or "answers" not in data:
        return await call.answer("Javoblarni qaytadan yuboring.", show_alert=True)
    t, err = await _open_test_for(db, callback_data.test_id, user)
    await state.clear()
    if err:
        await call.answer(err, show_alert=True)
        return await call.message.edit_reply_markup(reply_markup=None)
    correct = await services.submit(db, config, t, user, data["answers"], utcnow())
    await call.answer()
    await call.message.edit_reply_markup(reply_markup=None)
    if correct is None:
        return await call.message.answer(T.TEST_NOT_ACTIVE, reply_markup=menu(is_admin, is_super))
    await call.message.answer(
        T.SUBMITTED.format(correct=correct, n=t.n, coins=correct * config.coins_per_correct),
        reply_markup=menu(is_admin, is_super))


# ---------------- e'tiroz ----------------

@router.callback_query(kb.TestCb.filter(F.action == "appeal"))
async def appeal_start(call: CallbackQuery, callback_data: kb.TestCb, state: FSMContext, db: Database, user: User):
    t = await db.get_test(callback_data.test_id)
    if not t or t.status != "closed" or not await db.get_submission(t.id, user.id):
        return await call.answer(T.NOT_FOUND, show_alert=True)
    await state.set_state(AppealForm.text)
    await state.update_data(test_id=t.id)
    await call.answer()
    await call.message.answer(T.ASK_APPEAL, reply_markup=kb.cancel_kb())


@router.message(AppealForm.text, F.text)
async def appeal_finish(message: Message, state: FSMContext, db: Database, bot: Bot, config: Config,
                        user: User, is_admin: bool, is_super: bool):
    text = message.text.strip()
    if len(text) < 5:
        return await message.answer("Batafsilroq yozing (qaysi savol va nima uchun).")
    data = await state.get_data()
    await state.clear()
    t = await db.get_test(data.get("test_id", 0))
    if not t:
        return await message.answer(T.NOT_FOUND, reply_markup=menu(is_admin, is_super))
    m = re.match(r"\D*?(\d{1,3})", text)
    question = int(m.group(1)) if m and 1 <= int(m.group(1)) <= t.n else None
    appeal_id = await db.create_appeal(t.id, user.id, question, text[:1000], utcnow())
    await message.answer(T.APPEAL_SENT, reply_markup=menu(is_admin, is_super))
    a = await db.get_appeal(appeal_id)
    await services.notify_admins(bot, db, config, t.group_id, await appeal_text(db, a), kb.appeal_admin_kb(a.id))


# ---------------- reyting ----------------

@router.message(F.text == T.BTN_RATING)
async def rating(message: Message, db: Database, user: User):
    groups = await db.user_groups(user.id)
    if not groups:
        return await message.answer(T.NO_GROUPS_USER)
    if len(groups) > 1:
        return await message.answer("Qaysi guruh reytingi?", reply_markup=kb.pick_group_kb(groups, "rating"))
    text = await services.rating_text(db, groups[0], "all", utcnow(), viewer_id=user.id)
    await message.answer(text, reply_markup=kb.rating_kb(groups[0].id, "all", admin=False))


@router.callback_query(kb.MyGroupCb.filter(F.action == "rating"))
async def rating_pick(call: CallbackQuery, callback_data: kb.MyGroupCb, db: Database, user: User):
    await _show_rating(call, db, user, callback_data.group_id, "all")


@router.callback_query(kb.RatingCb.filter(~F.admin))
async def rating_period(call: CallbackQuery, callback_data: kb.RatingCb, db: Database, user: User):
    await _show_rating(call, db, user, callback_data.group_id, callback_data.period)


async def _show_rating(call: CallbackQuery, db: Database, user: User, group_id: int, period: str):
    g = await db.get_group(group_id)
    if not g or not await db.is_member(group_id, user.id):
        return await call.answer(T.NOT_FOUND, show_alert=True)
    await call.answer()
    text = await services.rating_text(db, g, period, utcnow(), viewer_id=user.id)
    await call.message.edit_text(text, reply_markup=kb.rating_kb(g.id, period, admin=False))


# ---------------- profil ----------------

@router.message(F.text == T.BTN_PROFILE)
async def profile(message: Message, db: Database, user: User, is_admin: bool, is_super: bool):
    role = "bosh admin" if is_super else "nazoratchi" if is_admin else "ustoz"
    lines = ["👤 <b>Profil</b>", "", f"Ism: <b>{escape(user.full_name)}</b>",
             f"Telefon: <code>{user.phone}</code>", f"Holat: {role}"]
    if is_admin:
        groups = await db.list_groups(None if is_super else user.id)
        lines.append(f"Guruhlar: {len(groups)} ta")
    else:
        groups = await db.user_groups(user.id)
        if groups:
            lines += ["", "<b>Guruhlar bo'yicha:</b>"]
        for g in groups:
            rows = services.ranked(await db.rating(g.id))
            place, coins = next(((p, c) for p, u, c in rows if u.id == user.id), (None, 0))
            cnt, avg = await db.user_test_stats(user.id, g.id)
            avg_s = f", o'rtacha {avg:.0f}%" if avg is not None else ""
            lines.append(f"📁 {escape(g.name)}: <b>{coins}</b> 🪙 · {place}-o'rin · {cnt} ta test{avg_s}")
    await message.answer("\n".join(lines))


# ---------------- jonli dars davomati ----------------

@router.message(F.text == T.BTN_ATTEND)
async def attend_start(message: Message, state: FSMContext):
    await state.set_state(Attend.code)
    await message.answer(T.ASK_ATTEND_CODE, reply_markup=kb.cancel_kb())


@router.message(Attend.code, F.text)
async def attend_code(message: Message, state: FSMContext, db: Database, user: User,
                      is_admin: bool, is_super: bool):
    code = "".join(message.text.split())
    if not services.valid_lesson_code(code):
        return await message.answer(T.BAD_LESSON_CODE)
    status, lessons = await services.attend(db, user, code, utcnow())
    if status == "wrong":
        return await message.answer(services.attend_reply(status, lessons))
    await state.clear()
    await message.answer(services.attend_reply(status, lessons), reply_markup=menu(is_admin, is_super))


@router.message(StateFilter(None), F.text.regexp(r"^\s*\d{4}\s*$"))
async def attend_quick(message: Message, db: Database, user: User):
    status, lessons = await services.attend(db, user, message.text.strip(), utcnow())
    await message.answer(services.attend_reply(status, lessons))


# ---------------- tez yuborish: "kod*javoblar" yoki shunchaki "abcd..." ----------------

@router.message(StateFilter(None), F.text)
async def quick_answers(message: Message, state: FSMContext, db: Database, user: User):
    code, body = split_quick(message.text)
    if code is None and not looks_like_answers(message.text):
        return  # oddiy gap — e'tiborsiz qoldiramiz
    if code is not None:
        t, err = await _open_test_for(db, code, user)
        if err:
            return await message.answer(f"Test kodi {code}: {err}")
        return await _ask_confirm(message, state, t, body)

    pending = [t for t in await db.user_open_tests(user.id) if not await db.get_submission(t.id, user.id)]
    if not pending:
        return await message.answer(T.NO_ACTIVE_TESTS)
    if len(pending) > 1:
        lines = ["Sizda bir nechta faol test bor. Kod bilan yuboring:", ""]
        lines += [f"• <code>{t.id}*...</code> — {escape(t.title)} ({t.n} ta savol)" for t in pending]
        return await message.answer("\n".join(lines))
    await _ask_confirm(message, state, pending[0], body)
