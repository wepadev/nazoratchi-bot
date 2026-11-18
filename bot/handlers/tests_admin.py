"""Nazoratchi: test yaratish (kalit bilan), navbat bilan nashr qilish, statistika, kalitni tuzatish."""
from datetime import timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import services
from .. import texts as T
from ..answers import AnswerError, parse_answers, preview
from ..config import Config
from ..db import Database, Test, User
from ..timeutil import fmt, fmt_left, parse_local, utcnow
from .common import IsAdmin, Registered, menu
from .groups import access, deny

router = Router(name="tests_admin")
router.message.filter(Registered(), IsAdmin())
router.callback_query.filter(Registered(), IsAdmin())

STATUS = {"draft": "📄 Qoralama", "queued": "⏳ Navbatda", "published": "🟢 Faol", "closed": "✅ Yakunlangan"}


class TestForm(StatesGroup):
    title = State()
    file = State()
    key = State()
    deadline = State()
    fixkey = State()


async def test_access(db: Database, test_id: int, user: User, is_super: bool) -> Test | None:
    test = await db.get_test(test_id)
    if test and await access(db, test.group_id, user, is_super):
        return test
    return None


async def card_text(db: Database, t: Test) -> str:
    now = utcnow()
    lines = [f"<b>{escape(t.title)}</b>", "", f"Holat: {STATUS[t.status]}", f"Savollar: {t.n} ta",
             f"Fayl: {'bor' if t.file_id else 'yo‘q'}"]
    if t.status == "queued":
        lines.append(f"Davomiyligi: {t.queue_hours} soat (oldingi test yakunlangach avtomatik nashr qilinadi)")
    if t.published_at:
        lines.append(f"Nashr: {fmt(t.published_at)}")
        left = f" ({fmt_left(t.deadline_at - now)} qoldi)" if t.status == "published" else ""
        lines.append(f"Muddat: {fmt(t.deadline_at)}{left}")
        subs = await db.list_submissions(t.id)
        group = await db.get_group(t.group_id)
        lines.append(f"Topshirdi: {len(subs)} / {group.member_count}")
    lines += ["", "Kalit:", preview(t.answer_key)]
    return "\n".join(lines)


async def show_test(call: CallbackQuery, db: Database, t: Test) -> None:
    await call.message.edit_text((await card_text(db, t))[:4000], reply_markup=kb.test_kb(t))


# ---------- ro'yxat ----------

async def tests_list_text(db: Database, group_id: int) -> str:
    g = await db.get_group(group_id)
    return (f"📝 <b>{escape(g.name)}</b> — testlar\n\n"
            "🟢 faol · ⏳ navbatda · 📄 qoralama · ✅ yakunlangan\n"
            "Testlar navbat bilan nashr qilinadi: bir vaqtda bitta faol test.")


@router.callback_query(kb.GroupCb.filter(F.action == "tests"))
async def tests_list(call: CallbackQuery, callback_data: kb.GroupCb, db: Database, user: User, is_super: bool,
                     state: FSMContext):
    await state.clear()
    g = await access(db, callback_data.group_id, user, is_super)
    if not g:
        return await deny(call)
    await call.answer()
    tests = await db.list_tests(g.id)
    await call.message.edit_text(await tests_list_text(db, g.id), reply_markup=kb.tests_kb(g.id, tests))


@router.callback_query(kb.TestCb.filter(F.action == "open"))
async def open_test(call: CallbackQuery, callback_data: kb.TestCb, db: Database, user: User, is_super: bool,
                    state: FSMContext):
    await state.clear()
    t = await test_access(db, callback_data.test_id, user, is_super)
    if not t:
        return await deny(call)
    await call.answer()
    await show_test(call, db, t)


# ---------- yaratish ----------

@router.callback_query(kb.GroupCb.filter(F.action == "newtest"))
async def new_test(call: CallbackQuery, callback_data: kb.GroupCb, state: FSMContext, db: Database,
                   user: User, is_super: bool):
    g = await access(db, callback_data.group_id, user, is_super)
    if not g:
        return await deny(call)
    await state.set_state(TestForm.title)
    await state.update_data(group_id=g.id)
    await call.answer()
    await call.message.answer(T.ASK_TEST_TITLE, reply_markup=kb.cancel_kb())


@router.message(TestForm.title, F.text)
async def new_test_title(message: Message, state: FSMContext):
    title = " ".join(message.text.split())
    if not (2 <= len(title) <= 80):
        return await message.answer("Nom 2–80 belgi oralig'ida bo'lishi kerak.")
    await state.update_data(title=title)
    await state.set_state(TestForm.file)
    await message.answer(T.ASK_TEST_FILE, reply_markup=kb.skip_cancel_kb())


@router.message(TestForm.file, F.document)
async def new_test_document(message: Message, state: FSMContext):
    await state.update_data(file_id=message.document.file_id, file_type="document")
    await _ask_key(message, state)


@router.message(TestForm.file, F.photo)
async def new_test_photo(message: Message, state: FSMContext):
    await state.update_data(file_id=message.photo[-1].file_id, file_type="photo")
    await _ask_key(message, state)


@router.message(TestForm.file, F.text == T.BTN_SKIP)
async def new_test_skip_file(message: Message, state: FSMContext):
    await state.update_data(file_id=None, file_type=None)
    await _ask_key(message, state)


@router.message(TestForm.file)
async def new_test_file_wrong(message: Message):
    await message.answer(T.ASK_TEST_FILE)


async def _ask_key(message: Message, state: FSMContext):
    await state.set_state(TestForm.key)
    await message.answer(T.ASK_TEST_KEY, reply_markup=kb.cancel_kb())


@router.message(TestForm.key, F.text)
async def new_test_key(message: Message, state: FSMContext, db: Database, user: User,
                       is_admin: bool, is_super: bool):
    try:
        key = parse_answers(message.text, None, allow_blank=False)
    except AnswerError as e:
        return await message.answer(f"❌ {e}")
    data = await state.get_data()
    await state.clear()
    if not await access(db, data["group_id"], user, is_super):
        return await message.answer(T.NOT_FOUND, reply_markup=menu(is_admin, is_super))
    t = await db.create_test(data["group_id"], data["title"], key, data.get("file_id"), data.get("file_type"),
                             user.id)
    await message.answer(f"✅ Test saqlandi ({t.n} ta savol). Kalitni tekshiring va nashr qiling.",
                         reply_markup=menu(is_admin, is_super))
    await message.answer((await card_text(db, t))[:4000], reply_markup=kb.test_kb(t))


# ---------- nashr / navbat ----------

@router.callback_query(kb.TestCb.filter(F.action == "publish"))
async def publish_menu(call: CallbackQuery, callback_data: kb.TestCb, db: Database, user: User, is_super: bool):
    t = await test_access(db, callback_data.test_id, user, is_super)
    if not t or t.status != "draft":
        return await deny(call)
    active = await db.active_test(t.group_id)
    await call.answer()
    if active:
        text = (f"Guruhda faol test bor: «{escape(active.title)}» (muddat {fmt(active.deadline_at)}).\n\n"
                f"«{escape(t.title)}» <b>navbatga</b> qo'yiladi va oldingisi yakunlanishi bilan avtomatik "
                "nashr qilinadi. Davomiyligini tanlang:")
    else:
        text = f"«{escape(t.title)}» uchun muddatni tanlang (nashr vaqtidan boshlab):"
    await call.message.edit_text(text, reply_markup=kb.publish_kb(t.id, queue=bool(active)))


@router.callback_query(kb.TestCb.filter(F.action == "pub"))
async def publish_duration(call: CallbackQuery, callback_data: kb.TestCb, db: Database, bot: Bot, config: Config,
                           user: User, is_super: bool):
    t = await test_access(db, callback_data.test_id, user, is_super)
    hours = callback_data.arg
    if not t or t.status != "draft" or not (1 <= hours <= 24 * 31):
        return await deny(call)
    now = utcnow()
    if await db.active_test(t.group_id):
        await db.queue_test(t.id, hours, now)
        await call.answer("Navbatga qo'yildi ⏳")
    else:
        await call.answer("Nashr qilinmoqda…")
        if not await services.publish(bot, db, config, t, now + timedelta(hours=hours), now):
            return await call.message.answer("Nashr qilib bo'lmadi: guruhda boshqa faol test paydo bo'ldi.")
    await show_test(call, db, await db.get_test(t.id))


@router.callback_query(kb.TestCb.filter(F.action == "date"))
async def publish_date(call: CallbackQuery, callback_data: kb.TestCb, state: FSMContext, db: Database,
                       user: User, is_super: bool):
    t = await test_access(db, callback_data.test_id, user, is_super)
    if not t or t.status != "draft":
        return await deny(call)
    await state.set_state(TestForm.deadline)
    await state.update_data(test_id=t.id)
    await call.answer()
    await call.message.answer(T.ASK_DEADLINE_DATE, reply_markup=kb.cancel_kb())


@router.message(TestForm.deadline, F.text)
async def publish_date_finish(message: Message, state: FSMContext, db: Database, bot: Bot, config: Config,
                              user: User, is_admin: bool, is_super: bool):
    now = utcnow()
    deadline = parse_local(message.text, now)
    if not deadline or deadline < now + timedelta(minutes=30):
        return await message.answer(T.BAD_DEADLINE + "\nMuddat kamida 30 daqiqadan keyin bo'lishi kerak.")
    data = await state.get_data()
    await state.clear()
    t = await test_access(db, data.get("test_id", 0), user, is_super)
    if not t or t.status != "draft":
        return await message.answer(T.NOT_FOUND, reply_markup=menu(is_admin, is_super))
    ok = await services.publish(bot, db, config, t, deadline, now)
    await message.answer("🚀 Nashr qilindi!" if ok else "Nashr qilib bo'lmadi: guruhda boshqa faol test bor.",
                         reply_markup=menu(is_admin, is_super))
    t = await db.get_test(t.id)
    await message.answer((await card_text(db, t))[:4000], reply_markup=kb.test_kb(t))


@router.callback_query(kb.TestCb.filter(F.action == "unqueue"))
async def unqueue(call: CallbackQuery, callback_data: kb.TestCb, db: Database, user: User, is_super: bool):
    t = await test_access(db, callback_data.test_id, user, is_super)
    if not t:
        return await deny(call)
    await db.unqueue_test(t.id)
    await call.answer("Navbatdan olindi")
    await show_test(call, db, await db.get_test(t.id))


# ---------- faol test ----------

@router.callback_query(kb.TestCb.filter(F.action == "stats"))
async def stats(call: CallbackQuery, callback_data: kb.TestCb, db: Database, user: User, is_super: bool):
    t = await test_access(db, callback_data.test_id, user, is_super)
    if not t:
        return await deny(call)
    await call.answer()
    text = await services.stats_text(db, t)
    if t.status == "published":
        missing = await db.non_submitters(t, only_before_publish=False)
        if missing:
            text += f"\n\n<b>Hali topshirmaganlar ({len(missing)}):</b>\n"
            text += "\n".join(f"• {escape(u.full_name)}" for u in missing[:60])
    markup = kb.confirm_kb(("🔄 Yangilash", kb.TestCb(action="stats", test_id=t.id)),
                           (kb.BACK, kb.TestCb(action="open", test_id=t.id)))
    try:
        await call.message.edit_text(text[:4000], reply_markup=markup)
    except TelegramBadRequest:  # "message is not modified" — yangilashda o'zgarish bo'lmasa
        pass


@router.callback_query(kb.TestCb.filter(F.action == "resend"))
async def resend(call: CallbackQuery, callback_data: kb.TestCb, db: Database, bot: Bot, config: Config,
                 user: User, is_super: bool):
    t = await test_access(db, callback_data.test_id, user, is_super)
    if not t or t.status != "published":
        return await deny(call)
    await call.answer("Yuborilmoqda…")
    group = await db.get_group(t.group_id)
    text = services.announce_text(t, group, config, utcnow())
    sent = 0
    for u in await db.non_submitters(t, only_before_publish=False):
        sent += await services.send_test(bot, u.id, t, text, kb.answer_kb(t.id))
    await call.message.answer(f"📣 Topshirmagan {sent} ta ustozga qayta yuborildi.")


@router.callback_query(kb.TestCb.filter(F.action == "close"))
async def close_ask(call: CallbackQuery, callback_data: kb.TestCb, db: Database, user: User, is_super: bool):
    t = await test_access(db, callback_data.test_id, user, is_super)
    if not t or t.status != "published":
        return await deny(call)
    await call.answer()
    await call.message.edit_text(
        f"⚠️ «{escape(t.title)}» ni hozir yakunlaysizmi?\n"
        "Topshirmaganlarga jarima beriladi va hammaga to'g'ri javoblar yuboriladi.",
        reply_markup=kb.confirm_kb(("Ha, yakunlash", kb.TestCb(action="close_ok", test_id=t.id)),
                                   ("Yo'q", kb.TestCb(action="open", test_id=t.id))))


@router.callback_query(kb.TestCb.filter(F.action == "close_ok"))
async def close_ok(call: CallbackQuery, callback_data: kb.TestCb, db: Database, bot: Bot, config: Config,
                   user: User, is_super: bool):
    t = await test_access(db, callback_data.test_id, user, is_super)
    if not t:
        return await deny(call)
    await call.answer("Yakunlanmoqda…")
    await services.close(bot, db, config, t, utcnow())
    await show_test(call, db, await db.get_test(t.id))


# ---------- kalitni tuzatish ----------

async def start_fixkey(message: Message, state: FSMContext, t: Test) -> None:
    await state.set_state(TestForm.fixkey)
    await state.update_data(test_id=t.id)
    await message.answer(T.ASK_FIX_KEY + "\n\nHozirgi kalit:\n" + preview(t.answer_key), reply_markup=kb.cancel_kb())


@router.callback_query(kb.TestCb.filter(F.action == "fixkey"))
async def fixkey(call: CallbackQuery, callback_data: kb.TestCb, state: FSMContext, db: Database,
                 user: User, is_super: bool):
    t = await test_access(db, callback_data.test_id, user, is_super)
    if not t:
        return await deny(call)
    await call.answer()
    await start_fixkey(call.message, state, t)


@router.message(TestForm.fixkey, F.text)
async def fixkey_finish(message: Message, state: FSMContext, db: Database, bot: Bot, config: Config,
                        user: User, is_admin: bool, is_super: bool):
    data = await state.get_data()
    t = await test_access(db, data.get("test_id", 0), user, is_super)
    if not t:
        await state.clear()
        return await message.answer(T.NOT_FOUND, reply_markup=menu(is_admin, is_super))
    try:
        changes = parse_answers(message.text, t.n, allow_blank=True)
    except AnswerError as e:
        return await message.answer(f"❌ {e}")
    new_key = "".join(c if c != "-" else old for c, old in zip(changes, t.answer_key))
    await state.clear()
    if new_key == t.answer_key:
        return await message.answer("Kalit o'zgarmadi.", reply_markup=menu(is_admin, is_super))
    diff = [f"№{i + 1}: {a} → <b>{b}</b>" for i, (a, b) in enumerate(zip(t.answer_key, new_key)) if a != b]
    changed = await services.fix_key(bot, db, config, t, new_key, user.id, utcnow())
    await message.answer("🔑 Kalit yangilandi:\n" + "\n".join(diff)
                         + f"\n\nNatijasi o'zgargan ustozlar: {changed} ta (tangalar to'g'rilandi).",
                         reply_markup=menu(is_admin, is_super))


# ---------- o'chirish ----------

@router.callback_query(kb.TestCb.filter(F.action == "delete"))
async def delete_ask(call: CallbackQuery, callback_data: kb.TestCb, db: Database, user: User, is_super: bool):
    t = await test_access(db, callback_data.test_id, user, is_super)
    if not t or t.status not in ("draft", "queued"):
        return await deny(call)
    await call.answer()
    await call.message.edit_text(
        f"«{escape(t.title)}» testini o'chirasizmi?",
        reply_markup=kb.confirm_kb(("Ha, o'chirish", kb.TestCb(action="delete_ok", test_id=t.id)),
                                   ("Yo'q", kb.TestCb(action="open", test_id=t.id))))


@router.callback_query(kb.TestCb.filter(F.action == "delete_ok"))
async def delete_ok(call: CallbackQuery, callback_data: kb.TestCb, db: Database, user: User, is_super: bool):
    t = await test_access(db, callback_data.test_id, user, is_super)
    if not t:
        return await deny(call)
    await db.delete_test(t.id)
    await call.answer("O'chirildi")
    tests = await db.list_tests(t.group_id)
    await call.message.edit_text(await tests_list_text(db, t.group_id), reply_markup=kb.tests_kb(t.group_id, tests))
