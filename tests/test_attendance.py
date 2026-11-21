"""Jonli dars davomati: nazoratchi kod qo'yadi, ustozlar kiritadi, yopilganda hisobot, statistika va Excel."""
import asyncio
from datetime import timedelta
from io import BytesIO

from aiogram import Bot
from aiohttp.test_utils import TestClient, TestServer
from openpyxl import load_workbook

from bot import keyboards as kb
from bot import scheduler, services
from bot import texts as T
from bot.config import Config
from bot.db import Database
from bot.excel import attendance_report
from bot.timeutil import utcnow
from bot.web.api import create_app
from tests.test_flow import FakeSession, build_dispatcher, cb_update, msg_update, out_text
from tests.webapp_seed import init_data

SUPER, ADMIN, U1, U2, U3, LATE = 100, 200, 301, 302, 303, 304
TOKEN = "123456:TEST"


async def setup():
    services._wrong_codes.clear()
    db = Database(":memory:")
    await db.connect()
    cfg = Config(bot_token=TOKEN, super_admin_ids=frozenset({SUPER}), db_path=":memory:")
    session = FakeSession()
    bot = Bot(TOKEN, session=session)
    now = utcnow()
    await db.create_user(SUPER, "998900000100", "Bosh", None, role="admin")
    await db.create_user(ADMIN, "998900000200", "Nazoratchi", None, role="admin")
    for uid, name in ((U1, "Aliyev Ali"), (U2, "Valiyeva Malika"), (U3, "Karimov Jasur"), (LATE, "Kech Qo'shilgan")):
        await db.create_user(uid, f"99890000{uid:04d}", name, None)
    g = await db.create_group("Attestatsiya 1", SUPER)
    await db.assign_admin(g.id, ADMIN)
    for uid in (U1, U2, U3):
        await db.add_member(g.id, uid, now - timedelta(days=5))
    return db, cfg, session, bot, g


def test_bot_flow():
    async def scenario():
        db, cfg, session, bot, g = await setup()
        dp = build_dispatcher(db, cfg)

        async def say(uid, text):
            session.sent.clear()
            await dp.feed_update(bot, msg_update(uid, text))
            return [out_text(m) for m in session.sent]

        async def click(uid, data):
            session.sent.clear()
            await dp.feed_update(bot, cb_update(uid, data))
            return list(session.sent)

        # nazoratchi dars ochadi
        await click(ADMIN, kb.GroupCb(action="lessons", group_id=g.id))
        await click(ADMIN, kb.GroupCb(action="newlesson", group_id=g.id))
        assert T.BAD_LESSON_CODE in await say(ADMIN, "12a4")
        assert "Qancha vaqt" in (await say(ADMIN, "4821"))[0]
        out = await click(ADMIN, kb.LessonCb(action="dur", arg=60))
        assert any("4821" in out_text(m) for m in out)
        lesson = (await db.list_lessons(g.id))[0]
        assert lesson.code == "4821" and lesson.is_open(utcnow())

        # ustozlar: oddiy xabar va tugma orqali
        assert "qayd etildi" in (await say(U1, "4821"))[0]
        assert "allaqachon" in (await say(U1, "4821"))[0]
        await say(U2, T.BTN_ATTEND)
        assert "topilmadi" in (await say(U2, "1111"))[0]
        assert "qayd etildi" in (await say(U2, "4821"))[0]
        # guruhga a'zo bo'lmagan foydalanuvchi kodni bilsa ham qatnasha olmaydi
        assert "topilmadi" in (await say(LATE, "4821"))[0]

        # kod muddati tugadi -> nazoratchiga hisobot
        session.sent.clear()
        await scheduler.tick(bot, db, cfg, lesson.closes_at + timedelta(minutes=1))
        report = "\n".join(out_text(m) for m in session.sent if m.chat_id == ADMIN)
        assert "Qatnashdi: <b>2</b> / 3" in report and "Karimov Jasur" in report
        assert "topilmadi" in (await say(U3, "4821"))[0]  # yopilgandan keyin kech

        out = await click(ADMIN, kb.LessonCb(action="xls"))
        assert any(type(m).__name__ == "SendDocument" for m in out)
        await db.close()

    asyncio.run(scenario())


def test_rate_limit_and_report():
    async def scenario():
        db, cfg, session, bot, g = await setup()
        now = utcnow()
        u1 = await db.get_user(U1)
        l1 = await db.create_lesson(g.id, "1-dars", "1111", ADMIN, now - timedelta(days=2),
                                    now - timedelta(days=2) + timedelta(hours=1))
        l2 = await db.create_lesson(g.id, "2-dars", "2222", ADMIN, now, now + timedelta(hours=1))
        await db.mark_attendance(l1.id, U1, now - timedelta(days=2))
        await db.mark_attendance(l1.id, U2, now - timedelta(days=2))
        # dars yopilgandan keyin qo'shilgan a'zo 1-darsda hisobga olinmaydi
        await db.add_member(g.id, LATE, now - timedelta(days=1))
        assert {u.id for u, _ in await db.lesson_roster(l1)} == {U1, U2, U3}
        assert {u.id for u, _ in await db.lesson_roster(l2)} == {U1, U2, U3, LATE}

        # 5 ta xato urinishdan keyin bloklanadi, hatto to'g'ri kod ham
        for _ in range(5):
            assert (await services.attend(db, u1, "9999", now))[0] == "wrong"
        assert (await services.attend(db, u1, "2222", now))[0] == "blocked"
        services._wrong_codes.clear()
        assert (await services.attend(db, u1, "2222", now))[0] == "ok"

        data = await attendance_report(db, await db.list_groups(), now)
        wb = load_workbook(BytesIO(data))
        assert wb.sheetnames == ["Umumiy", "Darslar", "Attestatsiya 1"]
        summary = {r[1]: r for r in wb["Umumiy"].iter_rows(min_row=2, values_only=True)}
        assert summary["Karimov Jasur"][5] == 1          # 1-darsda qatnashmagan (2-dars hali ochiq)
        assert summary["Aliyev Ali"][5] == 0
        assert summary["Kech Qo'shilgan"][3] == 0         # yopilgan darslardan hech biri unga tegishli emas
        matrix = list(wb["Attestatsiya 1"].iter_rows(min_row=2, values_only=True))
        late = next(r for r in matrix if r[0] == "Kech Qo'shilgan")
        assert late[4] == "—" and late[5] == "…"
        await db.close()

    asyncio.run(scenario())


def test_api():
    async def scenario():
        db, cfg, session, bot, g = await setup()
        client = TestClient(TestServer(create_app(db, bot, cfg)))
        await client.start_server()

        async def call(method, path, uid, status=200, **kw):
            r = await client.request(method, path, headers={"X-Telegram-Init-Data": init_data(uid)}, **kw)
            assert r.status == status, (method, path, r.status, await r.text())
            return await r.json()

        await call("POST", f"/api/admin/groups/{g.id}/lessons", U1, 403, json={})
        await call("POST", f"/api/admin/groups/{g.id}/lessons", ADMIN, 400, json={"code": "12"})
        l = await call("POST", f"/api/admin/groups/{g.id}/lessons", ADMIN, json={"code": "5050", "minutes": 30, "title": "Hosila"})
        assert l["open"] and l["title"] == "Hosila"
        await call("POST", f"/api/admin/groups/{g.id}/lessons", ADMIN, 409, json={"code": "5050"})
        auto = await call("POST", f"/api/admin/groups/{g.id}/lessons", ADMIN, json={"minutes": 0})
        assert len(auto["code"]) == 4 and auto["code"].isdigit()

        assert (await call("POST", "/api/attend", U1, json={"code": "5050"}))["status"] == "ok"
        await call("POST", "/api/attend", U2, 404, json={"code": "0000"})
        await call("POST", "/api/attend", U2, 400, json={"code": "abc"})

        info = await call("GET", f"/api/admin/lessons/{l['id']}", ADMIN)
        assert info["present"] == 1 and info["total"] == 3
        await call("POST", f"/api/admin/lessons/{l['id']}/mark", ADMIN, json={"user_id": U3, "present": True})
        await call("POST", f"/api/admin/lessons/{l['id']}/close", ADMIN)
        info = await call("GET", f"/api/admin/lessons/{l['id']}", ADMIN)
        assert info["present"] == 2 and not info["open"]

        lst = await call("GET", f"/api/admin/groups/{g.id}/lessons", ADMIN)
        assert len(lst["lessons"]) == 2
        m = {x["name"]: x for x in lst["members"]}
        assert m["Valiyeva Malika"]["missed"] and not m["Aliyev Ali"]["missed"]

        session.sent.clear()
        await call("POST", "/api/admin/attendance/excel", ADMIN)
        assert any(type(x).__name__ == "SendDocument" and x.chat_id == ADMIN for x in session.sent)
        await call("DELETE", f"/api/admin/lessons/{auto['id']}", ADMIN)
        assert len((await call("GET", f"/api/admin/groups/{g.id}/lessons", ADMIN))["lessons"]) == 1

        await db.create_user(201, "998900000201", "Begona", None, role="admin")
        await call("GET", f"/api/admin/lessons/{l['id']}", 201, 403)
        await client.close()
        await db.close()

    asyncio.run(scenario())


def test_coins():
    async def scenario():
        db, cfg, session, bot, g = await setup()
        now = utcnow()

        def coins():
            async def get():
                return {u.id: c for u, c in await db.rating(g.id)}
            return get()

        lesson = await db.create_lesson(g.id, "Hosila", "7777", ADMIN, now, now + timedelta(hours=1))
        status, _ = await services.attend(db, await db.get_user(U1), "7777", now, cfg)
        assert status == "ok"
        assert "(+5" in services.attend_reply(status, [lesson], cfg)
        assert (await coins()) == {U1: 5, U2: 0, U3: 0}
        await services.attend(db, await db.get_user(U1), "7777", now, cfg)  # qayta kiritish tanga bermaydi
        assert (await coins())[U1] == 5

        # kod yopildi: qoldirganlarga −5 va xabar; ikkinchi marta yopish hech narsa o'zgartirmaydi
        session.sent.clear()
        later = now + timedelta(hours=2)
        await scheduler.tick(bot, db, cfg, later)
        assert (await coins()) == {U1: 5, U2: -5, U3: -5}
        assert {m.chat_id for m in session.sent if "qatnashmadingiz" in out_text(m)} == {U2, U3}
        await services.close_lesson(bot, db, cfg, lesson, later)
        lesson = await db.get_lesson(lesson.id)
        for uid in (U1, U2, U3):
            await services.sync_lesson_coins(db, cfg, lesson, uid, later)
        assert (await coins()) == {U1: 5, U2: -5, U3: -5}

        # nazoratchi yopilgandan keyin qo'lda belgilaydi / belgini oladi
        await db.mark_attendance(lesson.id, U2, later, marked_by=ADMIN)
        assert await services.sync_lesson_coins(db, cfg, lesson, U2, later, ADMIN) == 10
        await db.unmark_attendance(lesson.id, U1)
        assert await services.sync_lesson_coins(db, cfg, lesson, U1, later, ADMIN) == -10
        assert (await coins()) == {U1: -5, U2: 5, U3: -5}

        # dars o'chirilsa, uning tangalari ham o'chadi
        await db.delete_lesson(lesson.id)
        assert (await coins()) == {U1: 0, U2: 0, U3: 0}
        await db.close()

    asyncio.run(scenario())


def test_code_inside_other_action():
    """«Javob yuborish» yoki «Guruhga qo'shilish» bosilgan holatda ham 4 xonali kod davomat sifatida qabul qilinadi."""
    async def scenario():
        db, cfg, session, bot, g = await setup()
        dp = build_dispatcher(db, cfg)
        now = utcnow()
        await db.create_lesson(g.id, "Hosila", "4821", ADMIN, now, now + timedelta(hours=1))
        t = await db.create_test(g.id, "Test", "ABCD", None, None, ADMIN)
        await services.publish(bot, db, cfg, t, None, now)

        async def say(uid, text):
            session.sent.clear()
            await dp.feed_update(bot, msg_update(uid, text))
            return [out_text(m) for m in session.sent if m.chat_id == uid]

        await dp.feed_update(bot, cb_update(U1, kb.TestCb(action="answer", test_id=t.id)))
        assert "qayd etildi" in (await say(U1, "4821"))[0]
        # davomatdan keyin holat tozalangan: oddiy javob yozish jarayoni qayta ishlaydi
        await dp.feed_update(bot, cb_update(U1, kb.TestCb(action="answer", test_id=t.id)))
        assert "tekshiring" in (await say(U1, "abcd"))[0]

        # noto'g'ri 4 xonali raqam — odatdagi javob xatosi (holat saqlanadi)
        await dp.feed_update(bot, cb_update(U2, kb.TestCb(action="answer", test_id=t.id)))
        assert "❌" in (await say(U2, "9999"))[0]
        assert "tekshiring" in (await say(U2, "abca"))[0]
        await db.close()

    asyncio.run(scenario())


def test_code_field_only_while_open():
    """Kod maydoni (API: home.lessons) faqat ochiq dars va hali qatnashilmagan bo'lsa; kod oshkor qilinmaydi."""
    async def scenario():
        db, cfg, session, bot, g = await setup()
        client = TestClient(TestServer(create_app(db, bot, cfg)))
        await client.start_server()
        dp = build_dispatcher(db, cfg)

        async def home(uid):
            r = await client.get("/api/home", headers={"X-Telegram-Init-Data": init_data(uid)})
            return (await r.json())["lessons"]

        async def say(uid, text):
            session.sent.clear()
            await dp.feed_update(bot, msg_update(uid, text))
            return [out_text(m) for m in session.sent if m.chat_id == uid]

        assert await home(U1) == []
        assert T.NO_OPEN_LESSON in await say(U1, T.BTN_ATTEND)          # dars yo'q — kod so'ralmaydi

        now = utcnow()
        lesson = await db.create_lesson(g.id, "Hosila", "4821", ADMIN, now, now + timedelta(hours=1))
        ls = await home(U1)
        assert len(ls) == 1 and not ls[0]["attended"] and "code" not in ls[0]
        assert T.ASK_ATTEND_CODE in await say(U2, T.BTN_ATTEND)

        await services.attend(db, await db.get_user(U1), "4821", now, cfg)
        assert (await home(U1))[0]["attended"] is True                  # qatnashgandan keyin maydon yashirinadi
        assert "qatnashgan" in (await say(U1, T.BTN_ATTEND))[0]

        await db.close_lesson(lesson.id, now)                           # muddati tugadi / yopildi
        assert await home(U3) == []
        assert T.NO_OPEN_LESSON in await say(U3, T.BTN_ATTEND)
        await client.close()
        await db.close()

    asyncio.run(scenario())
