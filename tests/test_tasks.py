"""Kunlik vazifalar: e'lon, har soatda «bajardingizmi?», «Bajardim», kun oxirida nazoratchiga hisobot."""
import asyncio
from datetime import timedelta

from aiogram import Bot
from aiohttp.test_utils import TestClient, TestServer

from bot import keyboards as kb
from bot import scheduler, services
from bot import texts as T
from bot.config import Config
from bot.db import Database
from bot.timeutil import local, utcnow
from bot.web.api import create_app
from tests.test_flow import FakeSession, build_dispatcher, cb_update, msg_update, out_text
from tests.webapp_seed import init_data

SUPER, ADMIN, U1, U2 = 100, 200, 301, 302
TOKEN = "123456:TEST"


async def setup():
    db = Database(":memory:")
    await db.connect()
    # tinch soatlar o'chiq, kun 00:00 dan — natija real vaqtga bog'liq bo'lmasin
    cfg = Config(bot_token=TOKEN, super_admin_ids=frozenset({SUPER}), db_path=":memory:",
                 quiet_hours=(0, 0), task_day_start_hour=0)
    session = FakeSession()
    bot = Bot(TOKEN, session=session)
    await db.create_user(SUPER, "998900000100", "Bosh", None, role="admin")
    await db.create_user(ADMIN, "998900000200", "Nazoratchi", None, role="admin")
    await db.create_user(U1, "998900000301", "Ali", None)
    await db.create_user(U2, "998900000302", "Vali", None)
    g = await db.create_group("G", SUPER)
    await db.assign_admin(g.id, ADMIN)
    for u in (U1, U2):
        await db.add_member(g.id, u, utcnow() - timedelta(days=1))
    return db, cfg, session, bot, g


def sent_to(session, uid):
    return [m for m in session.sent if getattr(m, "chat_id", None) == uid]


def test_hourly_until_done_and_summary():
    async def scenario():
        db, cfg, session, bot, g = await setup()
        now = utcnow()
        session.sent.clear()
        task, sent = await services.create_task(bot, db, cfg, g, "1–20 misollarni yeching", 0,
                                                await db.get_user(ADMIN), now)
        assert sent == 2 and task.is_active(now)
        first = sent_to(session, U1)[0]
        assert "Yangi vazifa" in out_text(first) and first.reply_markup.inline_keyboard[0][0].text == "✅ Bajardim"

        async def tick(at):
            session.sent.clear()
            await services.task_reminders(bot, db, cfg, at)
            return {m.chat_id: out_text(m) for m in session.sent}

        assert await tick(now + timedelta(minutes=30)) == {}        # e'londan keyin darhol so'ramaydi
        r1 = await tick(now + timedelta(minutes=61))
        assert set(r1) == {U1, U2} and "misollarni" in r1[U1]
        await db.mark_task_done(task.id, U1, now + timedelta(minutes=70))
        assert await tick(now + timedelta(minutes=90)) == {}        # soat o'tmagan
        r2 = await tick(now + timedelta(minutes=122))
        assert set(r2) == {U2}                                       # bajargandan keyin so'ralmaydi
        assert r2[U2].split("\n")[0] != r1[U2].split("\n")[0]        # savol har safar boshqacha

        # kun tugagach: nazoratchiga bitta hisobot
        session.sent.clear()
        await scheduler.tick(bot, db, cfg, task.ends_at + timedelta(minutes=1))
        rep = [out_text(m) for m in sent_to(session, ADMIN) if "Kunlik vazifa" in out_text(m)]
        assert len(rep) == 1 and "Bajardi: <b>1</b> / 2" in rep[0] and "Vali" in rep[0]
        session.sent.clear()
        await scheduler.tick(bot, db, cfg, task.ends_at + timedelta(minutes=5))
        assert not [m for m in sent_to(session, ADMIN) if "Kunlik vazifa" in out_text(m)]
        await db.close()

    asyncio.run(scenario())


def test_tomorrow_task():
    async def scenario():
        db, cfg, session, bot, g = await setup()
        now = utcnow()
        session.sent.clear()
        task, sent = await services.create_task(bot, db, cfg, g, "Dars yozuvini ko'ring", 1,
                                                await db.get_user(ADMIN), now)
        assert sent == 0 and not task.is_active(now)                 # ertaga — hozir e'lon yo'q
        assert task.day == local(now + timedelta(days=1)).strftime("%Y-%m-%d")
        session.sent.clear()
        await services.task_reminders(bot, db, cfg, task.starts_at + timedelta(minutes=1))
        assert {m.chat_id for m in session.sent} == {U1, U2}        # ertasi kuni ertalab so'raladi
        await db.close()

    asyncio.run(scenario())


def test_bot_flow():
    async def scenario():
        db, cfg, session, bot, g = await setup()
        dp = build_dispatcher(db, cfg)

        async def say(uid, text):
            session.sent.clear()
            await dp.feed_update(bot, msg_update(uid, text))
            return [out_text(m) for m in sent_to(session, uid)]

        async def click(uid, data):
            session.sent.clear()
            await dp.feed_update(bot, cb_update(uid, data))
            return list(session.sent)

        await click(ADMIN, kb.GroupCb(action="tasks", group_id=g.id))
        await click(ADMIN, kb.GroupCb(action="newtask", group_id=g.id))
        assert "Qaysi kun" in (await say(ADMIN, "45-betdagi misollar"))[0]
        out = await click(ADMIN, kb.TaskCb(action="day", arg=0))
        assert {m.chat_id for m in out if "Yangi vazifa" in out_text(m)} == {U1, U2}
        task = (await db.list_tasks(g.id))[0]

        assert "⬜️ 45-betdagi misollar" in (await say(U1, T.BTN_TASKS))[0]
        await click(U1, kb.TaskCb(action="done", task_id=task.id))
        assert "✅ 45-betdagi misollar" in (await say(U1, T.BTN_TASKS))[0]
        out = await click(ADMIN, kb.TaskCb(action="open", task_id=task.id))
        assert any("Bajardi: <b>1</b> / 2" in out_text(m) for m in out)
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

        await call("POST", f"/api/admin/groups/{g.id}/tasks", U1, 403, json={"text": "x", "day": 0})
        await call("POST", f"/api/admin/groups/{g.id}/tasks", ADMIN, 400, json={"text": "ab", "day": 0})
        t = await call("POST", f"/api/admin/groups/{g.id}/tasks", ADMIN, json={"text": "Misollar 1-20", "day": 0})
        assert t["sent"] == 2 and t["active"]
        home = await call("GET", "/api/home", U1)
        assert home["tasks"] == [{"id": t["id"], "text": "Misollar 1-20", "done": False}]
        await call("POST", f"/api/tasks/{t['id']}/done", U1)
        assert (await call("GET", "/api/home", U1))["tasks"][0]["done"] is True
        info = await call("GET", f"/api/admin/tasks/{t['id']}", ADMIN)
        assert info["done"] == 1 and info["total"] == 2
        lst = await call("GET", f"/api/admin/groups/{g.id}/tasks", ADMIN)
        assert lst["tasks"][0]["done"] == 1
        await call("DELETE", f"/api/admin/tasks/{t['id']}", ADMIN)
        assert (await call("GET", "/api/home", U1))["tasks"] == []
        await client.close()
        await db.close()

    asyncio.run(scenario())
