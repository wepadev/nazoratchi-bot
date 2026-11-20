"""Muddatsiz testlar (kunlik umumiy eslatma) va jonli dars yozuvlari."""
import asyncio
from datetime import timedelta

from aiogram import Bot
from aiohttp.test_utils import TestClient, TestServer

from bot import keyboards as kb
from bot import services
from bot import texts as T
from bot.config import Config
from bot.db import Database
from bot.timeutil import utcnow
from bot.web.api import create_app
from tests.test_flow import FakeSession, build_dispatcher, cb_update, msg_update, out_text
from tests.webapp_seed import init_data

SUPER, ADMIN, U1, U2 = 100, 200, 301, 302
TOKEN = "123456:TEST"


async def setup(**cfg_kw):
    db = Database(":memory:")
    await db.connect()
    cfg = Config(bot_token=TOKEN, super_admin_ids=frozenset({SUPER}), db_path=":memory:", **cfg_kw)
    session = FakeSession()
    bot = Bot(TOKEN, session=session)
    now = utcnow()
    await db.create_user(SUPER, "998900000100", "Bosh", None, role="admin")
    await db.create_user(ADMIN, "998900000200", "Nazoratchi", None, role="admin")
    await db.create_user(U1, "998900000301", "Aliyev Ali", None)
    await db.create_user(U2, "998900000302", "Valiyeva Malika", None)
    g = await db.create_group("G", SUPER)
    await db.assign_admin(g.id, ADMIN)
    for u in (U1, U2):
        await db.add_member(g.id, u, now - timedelta(days=1))
    return db, cfg, session, bot, g


def test_daily_reminder():
    async def scenario():
        db, cfg, session, bot, g = await setup(daily_reminder_hour=0, quiet_hours=(0, 0))
        now = utcnow()
        t1 = await db.create_test(g.id, "Uy vazifa 1", "AB", None, None, ADMIN)
        t2 = await db.create_test(g.id, "Uy vazifa 2", "CD", None, None, ADMIN)
        for t in (t1, t2):
            await services.publish(bot, db, cfg, t, None, now)
        await services.submit(db, cfg, await db.get_test(t1.id), await db.get_user(U1), "AB", now)

        session.sent.clear()
        await services.send_reminders(bot, db, cfg, now + timedelta(days=2))
        msgs = {m.chat_id: out_text(m) for m in session.sent}
        assert set(msgs) == {U1, U2}                      # har biriga bitta xabar
        assert "1 ta" in msgs[U1] and "Uy vazifa 2" in msgs[U1] and "Uy vazifa 1" not in msgs[U1]
        assert "2 ta" in msgs[U2]
        session.sent.clear()
        await services.send_reminders(bot, db, cfg, now + timedelta(days=2, minutes=5))
        assert session.sent == []                        # kuniga bir marta
        # muddatsiz test o'z-o'zidan yopilmaydi
        assert await db.due_tests(now + timedelta(days=365)) == []
        await db.close()

    asyncio.run(scenario())


def test_recordings_bot():
    async def scenario():
        db, cfg, session, bot, g = await setup()
        dp = build_dispatcher(db, cfg)
        now = utcnow()
        lesson = await db.create_lesson(g.id, "Hosila", "1234", ADMIN, now, now + timedelta(hours=1))

        async def say(uid, text):
            session.sent.clear()
            await dp.feed_update(bot, msg_update(uid, text))
            return list(session.sent)

        assert T.NO_RECORDINGS in [out_text(m) for m in await say(U1, T.BTN_RECORDINGS)]
        await dp.feed_update(bot, cb_update(ADMIN, kb.LessonCb(action="video", lesson_id=lesson.id)))
        assert any("❌" in out_text(m) for m in await say(ADMIN, "salom"))
        sent = await say(ADMIN, "youtu.be/abc123")
        assert (await db.get_lesson(lesson.id)).video_url == "https://youtu.be/abc123"
        notified = [m for m in sent if m.chat_id in (U1, U2)]
        assert len(notified) == 2 and notified[0].reply_markup.inline_keyboard[0][0].url == "https://youtu.be/abc123"

        out = await say(U1, T.BTN_RECORDINGS)
        assert out[0].reply_markup.inline_keyboard[0][0].url == "https://youtu.be/abc123"
        await db.close()

    asyncio.run(scenario())


def test_recordings_api():
    async def scenario():
        db, cfg, session, bot, g = await setup()
        client = TestClient(TestServer(create_app(db, bot, cfg)))
        await client.start_server()

        async def call(method, path, uid, status=200, **kw):
            r = await client.request(method, path, headers={"X-Telegram-Init-Data": init_data(uid)}, **kw)
            assert r.status == status, (method, path, r.status, await r.text())
            return await r.json()

        await call("POST", f"/api/admin/groups/{g.id}/lessons", ADMIN, 400, json={"video_url": "javascript:alert(1)"})
        l = await call("POST", f"/api/admin/groups/{g.id}/lessons", ADMIN, json={"title": "Integral", "minutes": 30})
        assert l["video_url"] is None
        await call("POST", f"/api/admin/lessons/{l['id']}/video", U1, 403, json={"url": "https://youtu.be/x"})
        r = await call("POST", f"/api/admin/lessons/{l['id']}/video", ADMIN, json={"url": "https://youtu.be/xyz"})
        assert r["sent"] == 2
        r = await call("POST", f"/api/admin/lessons/{l['id']}/video", ADMIN, json={"url": "https://youtu.be/xyz"})
        assert r["sent"] == 0                              # o'sha havola — qayta yuborilmaydi
        home = await call("GET", "/api/home", U1)
        assert home["recordings"][0]["url"] == "https://youtu.be/xyz" and home["recordings"][0]["title"] == "Integral"
        await call("POST", f"/api/admin/lessons/{l['id']}/video", ADMIN, json={"url": ""})
        assert (await call("GET", "/api/home", U1))["recordings"] == []
        await client.close()
        await db.close()

    asyncio.run(scenario())
