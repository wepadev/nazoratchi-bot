"""Nashr qilingan testga faylni keyin qo'shish / almashtirish (bot va Mini App API)."""
import asyncio
import datetime as dt
from datetime import timedelta

import aiohttp
from aiogram import Bot
from aiogram.types import Chat, Document, Message, Update
from aiogram.types import User as TgUser
from aiohttp.test_utils import TestClient, TestServer

from bot import keyboards as kb
from bot import services
from bot.config import Config
from bot.db import Database
from bot.timeutil import utcnow
from bot.web.api import create_app
from tests.test_flow import FakeSession, build_dispatcher, cb_update, out_text
from tests.webapp_seed import init_data

SUPER, ADMIN, U1, U2 = 100, 200, 301, 302
TOKEN = "123456:TEST"


async def setup():
    db = Database(":memory:")
    await db.connect()
    cfg = Config(bot_token=TOKEN, super_admin_ids=frozenset({SUPER}), db_path=":memory:")
    session = FakeSession()
    bot = Bot(TOKEN, session=session)
    now = utcnow()
    await db.create_user(SUPER, "998900000100", "Bosh", None, role="admin")
    await db.create_user(ADMIN, "998900000200", "Nazoratchi", None, role="admin")
    await db.create_user(U1, "998900000301", "Ali", None)
    await db.create_user(U2, "998900000302", "Vali", None)
    g = await db.create_group("G", SUPER)
    await db.assign_admin(g.id, ADMIN)
    for u in (U1, U2):
        await db.add_member(g.id, u, now - timedelta(days=1))
    t = await db.create_test(g.id, "Uy vazifa", "ABCD", None, None, ADMIN)  # faylsiz
    await services.publish(bot, db, cfg, t, None, now)
    await services.submit(db, cfg, await db.get_test(t.id), await db.get_user(U2), "ABCD", now)
    return db, cfg, session, bot, g, t


def doc_update(uid):
    return Update(update_id=0, message=Message(
        message_id=1, date=dt.datetime.now(), chat=Chat(id=uid, type="private"),
        from_user=TgUser(id=uid, is_bot=False, first_name="A"),
        document=Document(file_id="pdf-123", file_unique_id="x", file_name="test.pdf")))


def test_attach_bot():
    async def scenario():
        db, cfg, session, bot, g, t = await setup()
        dp = build_dispatcher(db, cfg)
        await dp.feed_update(bot, cb_update(ADMIN, kb.TestCb(action="attach", test_id=t.id)))
        session.sent.clear()
        await dp.feed_update(bot, doc_update(ADMIN))
        t = await db.get_test(t.id)
        assert t.file_id == "pdf-123" and t.file_type == "document"
        docs = [m for m in session.sent if type(m).__name__ == "SendDocument"]
        assert sorted(m.chat_id for m in docs) == [U1, U2]
        # topshirmaganga javob tugmasi bor, topshirganga yo'q
        by = {m.chat_id: m for m in docs}
        assert by[U1].reply_markup is not None and by[U2].reply_markup is None
        assert any("2 ta ustozga yuborildi" in out_text(m) for m in session.sent if m.chat_id == ADMIN)
        await db.close()

    asyncio.run(scenario())


def test_attach_api():
    async def scenario():
        db, cfg, session, bot, g, t = await setup()
        client = TestClient(TestServer(create_app(db, bot, cfg)))
        await client.start_server()

        async def post_file(uid, status=200):
            form = aiohttp.FormData()
            form.add_field("file", b"%PDF-1.4", filename="t.pdf", content_type="application/pdf")
            r = await client.post(f"/api/admin/tests/{t.id}/file", data=form,
                                  headers={"X-Telegram-Init-Data": init_data(uid)})
            assert r.status == status, await r.text()
            return await r.json()

        await post_file(U1, 403)
        session.sent.clear()
        r = await post_file(ADMIN)
        assert r["sent"] == 2
        assert (await db.get_test(t.id)).file_id
        # bo'sh so'rov — aniq xato, jimgina o'tkazib yuborilmaydi
        r2 = await client.post(f"/api/admin/tests/{t.id}/file", data=aiohttp.FormData({"x": "1"}),
                               headers={"X-Telegram-Init-Data": init_data(ADMIN)})
        assert r2.status == 400
        await client.close()
        await db.close()

    asyncio.run(scenario())
