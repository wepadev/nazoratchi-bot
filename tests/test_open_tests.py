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


def test_open_reminder_every_interval():
    async def scenario():
        db, cfg, session, bot, g = await setup(quiet_hours=(0, 0))
        now = utcnow()
        t1 = await db.create_test(g.id, "Uy vazifa 1", "AB", None, None, ADMIN)
        t2 = await db.create_test(g.id, "Uy vazifa 2", "CD", None, None, ADMIN)
        for t in (t1, t2):
            await services.publish(bot, db, cfg, t, None, now)
        await services.submit(db, cfg, await db.get_test(t1.id), await db.get_user(U1), "AB", now)

        async def tick(at):
            session.sent.clear()
            await services.send_reminders(bot, db, cfg, at)
            return {m.chat_id: out_text(m) for m in session.sent}

        assert await tick(now + timedelta(hours=1)) == {}           # e'londan keyin darhol emas
        first = await tick(now + timedelta(hours=3, minutes=1))
        assert set(first) == {U1, U2}                              # har biriga bitta xabar
        assert "1 ta" in first[U1] and "Uy vazifa 2" in first[U1] and "Uy vazifa 1" not in first[U1]
        assert "2 ta" in first[U2] and "+4</b> tangagacha" in first[U2]
        assert await tick(now + timedelta(hours=4)) == {}           # 3 soat o'tmagan
        second = await tick(now + timedelta(hours=6, minutes=2))
        assert set(second) == {U1, U2}
        # har safar boshqa sarlavha
        assert first[U2].split("\n")[0] != second[U2].split("\n")[0]
        assert await db.due_tests(now + timedelta(days=365)) == []  # muddatsiz test o'zi yopilmaydi
        await db.close()

    asyncio.run(scenario())


def test_motivation_never_repeats_back_to_back():
    from bot import motivation
    seen = [motivation.headline(999) for _ in range(len(motivation.HEADLINES))]
    assert len(set(seen)) == len(seen)                             # bir aylanishda takror yo'q
    for _ in range(200):
        a, b = motivation.headline(998), motivation.headline(998)
        assert a != b


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
