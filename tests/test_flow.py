"""To'liq stsenariy soxta Telegram orqali:
ro'yxat -> bosh admin guruh yaratadi va nazoratchi tayinlaydi -> ustozlar qo'shiladi -> test (kalit bilan)
-> nashr + navbat -> javoblar -> eslatma -> yakunlash (jarima, natijalar) -> e'tiroz -> kalitni tuzatish
-> reyting, Excel, haftalik reyting, faoliyat."""
import asyncio
import datetime as dt
import re
from datetime import timedelta
from io import BytesIO

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Contact, Message, Update
from aiogram.types import User as TgUser
from openpyxl import load_workbook

from bot import keyboards as kb
from bot import scheduler, services
from bot import texts as T
from bot.config import Config
from bot.db import Database
from bot.excel import group_report
from bot.handlers import appeals, common, groups, lessons, superadmin, tests_admin, user
from bot.middlewares import ContextMiddleware
from bot.timeutil import utcnow, week_start

SUPER, ADMIN, U1, U2, U3 = 100, 200, 301, 302, 303


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent: list = []

    async def make_request(self, bot, method, timeout=None):
        self.sent.append(method)
        name = type(method).__name__
        if name.startswith("Send"):
            return Message(message_id=len(self.sent), date=dt.datetime.now(),
                           chat=Chat(id=method.chat_id, type="private"),
                           text=getattr(method, "text", None) or getattr(method, "caption", None) or "")
        return True

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        pass


def build_dispatcher(db, cfg):
    """Har bir test uchun yangi Dispatcher (modul darajasidagi routerlarni qayta ulash)."""
    dp = Dispatcher(storage=MemoryStorage())
    mw = ContextMiddleware(db, cfg)
    dp.message.outer_middleware(mw)
    dp.callback_query.outer_middleware(mw)
    routers = [common.router, superadmin.router, groups.router, tests_admin.router, appeals.router, lessons.router, user.router]
    for r in routers:
        r._parent_router = None
    dp.include_routers(*routers)
    return dp


def tg(uid):
    return TgUser(id=uid, is_bot=False, first_name=f"U{uid}")


def msg_update(uid, text=None, contact=None):
    return Update(update_id=0, message=Message(
        message_id=1, date=dt.datetime.now(), chat=Chat(id=uid, type="private"),
        from_user=tg(uid), text=text, contact=contact))


def cb_update(uid, data):
    return Update(update_id=0, callback_query=CallbackQuery(
        id="1", from_user=tg(uid), chat_instance="c", data=data if isinstance(data, str) else data.pack(),
        message=Message(message_id=5, date=dt.datetime.now(), chat=Chat(id=uid, type="private"), text="x")))


def out_text(m):
    return getattr(m, "text", None) or getattr(m, "caption", None) or ""


def buttons(methods):
    res = []
    for m in methods:
        markup = getattr(m, "reply_markup", None)
        for row in getattr(markup, "inline_keyboard", None) or []:
            res += [(b.text, b.callback_data) for b in row]
    return res


def test_full_flow():
    async def scenario():
        db = Database(":memory:")
        await db.connect()
        cfg = Config(bot_token="1:x", super_admin_ids=frozenset({SUPER}), db_path=":memory:",
                     quiet_hours=(0, 0))
        session = FakeSession()
        bot = Bot("123:abc", session=session)
        dp = build_dispatcher(db, cfg)

        async def send(update):
            session.sent.clear()
            await dp.feed_update(bot, update)
            return list(session.sent)

        async def say(uid, text=None, **kw):
            return [out_text(m) for m in await send(msg_update(uid, text, **kw))]

        async def click(uid, data):
            return await send(cb_update(uid, data))

        def to(methods, uid):
            return [out_text(m) for m in methods if getattr(m, "chat_id", None) == uid]

        async def register(uid, phone, name):
            assert T.WELCOME in await say(uid, "/start")
            assert T.SHARE_OWN_CONTACT in await say(uid, contact=Contact(
                phone_number="998901111111", first_name="x", user_id=uid + 1))
            assert T.ASK_FULL_NAME in await say(uid, contact=Contact(phone_number=phone, first_name="x", user_id=uid))
            assert "Ro'yxatdan o'tdingiz" in (await say(uid, name))[0]

        await register(SUPER, "+998900000100", "Bosh Admin")
        await register(ADMIN, "998900000200", "Nazoratchi Karimov")
        for uid, name in ((U1, "Aliyev Ali"), (U2, "Valiyev Vali"), (U3, "Soliyev Soli")):
            await register(uid, f"99890000{uid:04d}", name)

        # --- bosh admin nazoratchi qo'shadi ---
        await click(SUPER, kb.AdminCb(action="add"))
        assert "nazoratchi qilindi" in (await say(SUPER, "90 000 02 00"))[0]
        assert (await db.get_user(ADMIN)).is_admin

        # --- nazoratchi guruh yarata olmaydi, bosh admin yaratadi ---
        assert await say(ADMIN, T.BTN_CREATE_GROUP) == []
        await say(SUPER, T.BTN_CREATE_GROUP)
        out = await say(SUPER, "Attestatsiya 1-guruh")
        code = re.search(r"<code>(\w+)</code>", out[0]).group(1)
        gid = (await db.get_group_by_code(code)).id

        # nazoratchi hali tayinlanmagan -> guruhni ko'ra olmaydi
        assert T.NO_GROUPS_ADMIN in await say(ADMIN, T.BTN_GROUPS)
        out = await click(SUPER, kb.AssignCb(group_id=gid, admin_id=ADMIN))
        assert any("nazoratchi etib tayinlandingiz" in t for t in to(out, ADMIN))
        assert await db.is_group_admin(gid, ADMIN)

        # --- ustozlar kod bilan qo'shiladi ---
        for uid in (U1, U2, U3):
            await say(uid, T.BTN_JOIN)
            out = await say(uid, code.lower())
            assert "qo'shildingiz" in out[0]

        # --- nazoratchi test yaratadi ---
        await click(ADMIN, kb.GroupCb(action="newtest", group_id=gid))
        await say(ADMIN, "1-hafta: Logarifmlar")
        await say(ADMIN, T.BTN_SKIP)
        assert any("❌" in t for t in await say(ADMIN, "abce"))
        await say(ADMIN, "1a 2b 3c 4d 5d")
        t1 = (await db.list_tests(gid))[0]
        assert t1.answer_key == "ABCDD" and t1.status == "draft"

        # ikkinchi test
        await click(ADMIN, kb.GroupCb(action="newtest", group_id=gid))
        await say(ADMIN, "2-hafta")
        await say(ADMIN, T.BTN_SKIP)
        await say(ADMIN, "aaaa")
        t2 = next(t for t in await db.list_tests(gid) if t.title == "2-hafta")

        # --- nashr: birinchisi darhol, ikkinchisi navbatga ---
        out = await click(ADMIN, kb.TestCb(action="pub", test_id=t1.id, arg=24))
        for uid in (U1, U2, U3):
            assert any("Yangi test" in t for t in to(out, uid))
        assert (await db.get_test(t1.id)).status == "published"
        await click(ADMIN, kb.TestCb(action="pub", test_id=t2.id, arg=48))
        assert (await db.get_test(t2.id)).status == "queued"

        # --- javoblar ---
        await click(U1, kb.TestCb(action="answer", test_id=t1.id))
        assert any("❌" in t for t in await say(U1, "abc"))
        out = await say(U1, "abcda")
        assert "Javoblaringizni tekshiring" in out[0]
        out = await click(U1, kb.TestCb(action="confirm", test_id=t1.id))
        assert any("4/5" in t for t in to(out, U1))
        out = await click(U1, kb.TestCb(action="answer", test_id=t1.id))  # qayta topshirish
        assert any("allaqachon" in (getattr(m, "text", "") or "") for m in out)

        await click(U2, kb.TestCb(action="answer", test_id=t1.id))
        out = await say(U2, "1a 2b")
        assert "Javobsiz savollar: 3, 4, 5" in out[0]
        out = await click(U2, kb.TestCb(action="confirm", test_id=t1.id))
        assert any("2/5" in t for t in to(out, U2))

        # --- eslatma faqat topshirmaganga (U3) ---
        session.sent.clear()
        await services.send_reminders(bot, db, cfg, utcnow() + timedelta(hours=3, minutes=5))
        assert [m.chat_id for m in session.sent] == [U3]
        assert "Eslatma" in out_text(session.sent[0])

        # --- muddat tugadi: yakunlash ---
        t1 = await db.get_test(t1.id)
        session.sent.clear()
        await scheduler.tick(bot, db, cfg, t1.deadline_at + timedelta(minutes=1))
        sent = list(session.sent)
        assert (await db.get_test(t1.id)).status == "closed"
        assert any("−5" in t for t in to(sent, U3))
        u1_msgs = to(sent, U1)
        assert any("№5: siz — A, to'g'ri — <b>D</b>" in t for t in u1_msgs)
        assert any("E'tiroz" in b[0] for b in buttons([m for m in sent if getattr(m, "chat_id", 0) == U1]))
        admin_report = "\n".join(to(sent, ADMIN))
        assert "Topshirmaganlar (1)" in admin_report and "Soliyev Soli" in admin_report
        assert "№5" in admin_report  # eng ko'p xato qilingan savol
        # navbatdagi test avtomatik nashr qilindi
        assert (await db.get_test(t2.id)).status == "published"
        assert any("2-hafta" in t for t in to(sent, U3))

        rating = {u.id: c for u, c in await db.rating(gid)}
        assert rating == {U1: 4, U2: 2, U3: -5}

        # --- e'tiroz ---
        await click(U1, kb.TestCb(action="appeal", test_id=t1.id))
        out = await say(U1, "5 — javob A bo'lishi kerak")
        assert T.APPEAL_SENT in out
        appeal = (await db.open_appeals(ADMIN))[0]
        assert appeal.question == 5
        out = await click(ADMIN, kb.AppealCb(action="accept", appeal_id=appeal.id))
        assert any("qabul qilindi" in t for t in to(out, U1))
        assert (await db.open_appeals(ADMIN)) == []

        # --- kalitni tuzatish: 5-savol aslida A ---
        await click(ADMIN, kb.TestCb(action="fixkey", test_id=t1.id))
        out = await say(ADMIN, "5a")
        assert any("Natijasi o'zgargan ustozlar: 1" in t for t in out)
        assert (await db.get_submission(t1.id, U1)).correct == 5
        rating = {u.id: c for u, c in await db.rating(gid)}
        assert rating == {U1: 6, U2: 2, U3: -5}  # 4 + 1 (e'tiroz) + 1 (kalit)

        # --- qo'lda tanga ---
        await click(ADMIN, kb.MemberCb(action="coin", group_id=gid, user_id=U2))
        assert any("Format" in t for t in await say(ADMIN, "+3"))
        await say(ADMIN, "+3 Darsda faol")
        assert {u.id: c for u, c in await db.rating(gid)}[U2] == 5

        # --- reyting (ustoz ko'rinishi) ---
        out = await say(U3, T.BTN_RATING)
        assert "🥇 Aliyev Ali" in out[0] and "3-o'rin" in out[0]

        # --- Excel ---
        out = await click(ADMIN, kb.GroupCb(action="excel", group_id=gid))
        assert any(type(m).__name__ == "SendDocument" for m in out)
        g = await db.get_group(gid)
        wb = load_workbook(BytesIO(await group_report(db, g, utcnow())))
        assert wb.sheetnames == ["Reyting", "Natijalar", "Savollar tahlili", "Testlar", "Tangalar tarixi"]
        assert wb["Reyting"]["B2"].value == "Aliyev Ali"

        # --- begona nazoratchi bu guruhni boshqara olmaydi ---
        await db.create_user(999, "998909999999", "Boshqa Nazoratchi", None, role="admin")
        out = await click(999, kb.GroupCb(action="open", group_id=gid))
        assert not any(type(m).__name__ == "EditMessageText" for m in out)

        # --- haftalik reyting (keyingi dushanba 10:00) ---
        session.sent.clear()
        monday = week_start(utcnow()) + timedelta(days=7, hours=10)
        await services.weekly_rating(bot, db, cfg, monday)
        weekly = [m for m in session.sent if "Haftalik" in out_text(m)]
        assert {m.chat_id for m in weekly} >= {U1, U2, U3, ADMIN}
        session.sent.clear()
        await services.weekly_rating(bot, db, cfg, monday + timedelta(hours=1))  # ikki marta yuborilmaydi
        assert session.sent == []

        # --- faoliyat ---
        out = await say(SUPER, T.BTN_ACTIVITY)
        assert "Nazoratchi Karimov" in out[0] and "Testlar: 2" in out[0]
        await db.close()

    asyncio.run(scenario())
