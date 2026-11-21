"""Testni oldindan rejalashtirish: belgilangan vaqtda avtomatik nashr (bot, API, scheduler)."""
import asyncio
from datetime import timedelta

from aiogram import Bot
from aiohttp.test_utils import TestClient, TestServer

from bot import keyboards as kb
from bot import scheduler
from bot.config import Config
from bot.db import Database
from bot.timeutil import local, utcnow
from bot.web.api import create_app
from tests.test_flow import FakeSession, build_dispatcher, cb_update, msg_update, out_text
from tests.webapp_seed import init_data

SUPER, ADMIN, U1 = 100, 200, 301
TOKEN = "123456:TEST"


async def setup():
    db = Database(":memory:")
    await db.connect()
    cfg = Config(bot_token=TOKEN, super_admin_ids=frozenset({SUPER}), db_path=":memory:")
    session = FakeSession()
    bot = Bot(TOKEN, session=session)
    await db.create_user(SUPER, "998900000100", "Bosh", None, role="admin")
    await db.create_user(ADMIN, "998900000200", "Nazoratchi", None, role="admin")
    await db.create_user(U1, "998900000301", "Ali", None)
    g = await db.create_group("G", SUPER)
    await db.assign_admin(g.id, ADMIN)
    await db.add_member(g.id, U1, utcnow() - timedelta(days=1))
    return db, cfg, session, bot, g


def test_scheduler_publishes_on_time():
    async def scenario():
        db, cfg, session, bot, g = await setup()
        now = utcnow()
        t1 = await db.create_test(g.id, "Ertalabki test", "ABCD", None, None, ADMIN)
        t2 = await db.create_test(g.id, "Kunlik test", "ABCD", None, None, ADMIN)
        t3 = await db.create_test(g.id, "Aniq muddat", "ABCD", None, None, ADMIN)
        at = now + timedelta(hours=2)
        assert await db.schedule_test(t1.id, at, 0, None)                       # muddatsiz
        assert await db.schedule_test(t2.id, at, 24, None)                      # nashrdan keyin 1 kun
        assert await db.schedule_test(t3.id, at, None, at + timedelta(days=3))  # aniq muddat

        session.sent.clear()
        await scheduler.tick(bot, db, cfg, at - timedelta(minutes=1))
        assert (await db.get_test(t1.id)).status == "scheduled" and session.sent == []

        await scheduler.tick(bot, db, cfg, at + timedelta(seconds=30))
        p1, p2, p3 = [await db.get_test(t.id) for t in (t1, t2, t3)]
        assert {p1.status, p2.status, p3.status} == {"published"}
        assert p1.deadline_at is None and p1.publish_at is None
        assert abs((p2.deadline_at - (at + timedelta(seconds=30) + timedelta(hours=24))).total_seconds()) < 2
        assert p3.deadline_at == (at + timedelta(days=3)).replace(microsecond=0)
        assert sum(1 for m in session.sent if m.chat_id == U1 and "Yangi test" in out_text(m)) == 3
        assert any(m.chat_id == ADMIN and "nashr qilindi" in out_text(m) for m in session.sent)

        # bekor qilish -> qoralama; o'chirish mumkin
        t4 = await db.create_test(g.id, "Bekor", "AB", None, None, ADMIN)
        await db.schedule_test(t4.id, at, 0, None)
        await db.unqueue_test(t4.id)
        t4 = await db.get_test(t4.id)
        assert t4.status == "draft" and t4.publish_at is None
        await db.schedule_test(t4.id, at, 0, None)
        await db.delete_test(t4.id)
        assert await db.get_test(t4.id) is None
        await db.close()

    asyncio.run(scenario())


def test_bot_flow():
    async def scenario():
        db, cfg, session, bot, g = await setup()
        dp = build_dispatcher(db, cfg)
        t = await db.create_test(g.id, "3-hafta", "ABCD", None, None, ADMIN)

        async def say(text):
            session.sent.clear()
            await dp.feed_update(bot, msg_update(ADMIN, text))
            return [out_text(m) for m in session.sent]

        await dp.feed_update(bot, cb_update(ADMIN, kb.TestCb(action="sched", test_id=t.id)))
        assert "noto'g'ri" in (await say("01.01.2000 09:00"))[0]
        when = local(utcnow() + timedelta(days=1)).replace(hour=9, minute=0)
        out = await say(when.strftime("%d.%m.%Y %H:%M"))
        assert "muddatini tanlang" in out[0]
        await dp.feed_update(bot, cb_update(ADMIN, kb.TestCb(action="schedd", test_id=t.id, arg=48)))
        t = await db.get_test(t.id)
        assert t.status == "scheduled" and t.queue_hours == 48 and local(t.publish_at).hour == 9

        session.sent.clear()
        await dp.feed_update(bot, cb_update(ADMIN, kb.TestCb(action="pubnow", test_id=t.id)))
        t = await db.get_test(t.id)
        assert t.status == "published" and t.deadline_at is not None
        assert any(getattr(m, "chat_id", None) == U1 for m in session.sent)
        await db.close()

    asyncio.run(scenario())


def test_api():
    async def scenario():
        db, cfg, session, bot, g = await setup()
        client = TestClient(TestServer(create_app(db, bot, cfg)))
        await client.start_server()
        t = await db.create_test(g.id, "API test", "ABCD", None, None, ADMIN)

        async def call(path, status=200, **kw):
            r = await client.post(path, headers={"X-Telegram-Init-Data": init_data(ADMIN)}, **kw)
            assert r.status == status, (path, r.status, await r.text())
            return await r.json()

        past = "2000-01-01T09:00:00+05:00"
        future = (local(utcnow() + timedelta(days=2))).strftime("%Y-%m-%dT09:00:00+05:00")
        await call(f"/api/admin/tests/{t.id}/publish", 400, json={"publish_at": past, "hours": 0})
        await call(f"/api/admin/tests/{t.id}/publish", 400,
                   json={"publish_at": future, "deadline": future})                   # muddat nashrdan oldin
        r = await call(f"/api/admin/tests/{t.id}/publish", json={"publish_at": future, "hours": 0})
        assert r["result"] == "scheduled"
        info = await (await client.get(f"/api/admin/tests/{t.id}",
                                       headers={"X-Telegram-Init-Data": init_data(ADMIN)})).json()
        assert info["status"] == "scheduled" and info["publish_at"]
        # vaqtni o'zgartirish ham mumkin (scheduled -> scheduled)
        await call(f"/api/admin/tests/{t.id}/publish", json={"publish_at": future, "hours": 24})
        assert (await db.get_test(t.id)).queue_hours == 24
        session.sent.clear()
        await call(f"/api/admin/tests/{t.id}/publish_now")
        assert (await db.get_test(t.id)).status == "published"
        assert any(getattr(m, "chat_id", None) == U1 for m in session.sent)
        await call(f"/api/admin/tests/{t.id}/publish_now", 409)
        await client.close()
        await db.close()

    asyncio.run(scenario())
