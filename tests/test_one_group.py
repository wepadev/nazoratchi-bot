"""Ustoz bir vaqtda faqat bitta guruhda bo'ladi: boshqasiga o'tish uchun avval chiqadi."""
import asyncio
from datetime import timedelta

from aiogram import Bot

from bot import keyboards as kb
from bot import texts as T
from bot.config import Config
from bot.db import Database
from bot.timeutil import utcnow
from tests.test_flow import FakeSession, build_dispatcher, cb_update, msg_update, out_text

SUPER, ADMIN, U = 100, 200, 301


def test_db_guard():
    async def scenario():
        db = Database(":memory:")
        await db.connect()
        now = utcnow()
        await db.create_user(U, "998900000301", "Ustoz", None)
        g1 = await db.create_group("G1", SUPER)
        g2 = await db.create_group("G2", SUPER)
        assert await db.add_member(g1.id, U, now)
        assert not await db.add_member(g2.id, U, now)        # boshqa guruhda — rad
        assert not await db.add_member(g1.id, U, now)        # o'sha guruh — takror
        # bir vaqtda kelgan ikki so'rov ham faqat bittasini qo'shadi
        await db.remove_member(g1.id, U)
        res = await asyncio.gather(db.add_member(g1.id, U, now), db.add_member(g2.id, U, now))
        assert sorted(res) == [False, True]
        assert len(await db.user_groups(U)) == 1
        await db.close()

    asyncio.run(scenario())


def test_bot_flow():
    async def scenario():
        db = Database(":memory:")
        await db.connect()
        cfg = Config(bot_token="1:x", super_admin_ids=frozenset({SUPER}), db_path=":memory:")
        session = FakeSession()
        bot = Bot("123:abc", session=session)
        dp = build_dispatcher(db, cfg)

        async def say(text):
            session.sent.clear()
            await dp.feed_update(bot, msg_update(U, text))
            return [out_text(m) for m in session.sent if m.chat_id == U]

        await db.create_user(SUPER, "998900000100", "Bosh", None, role="admin")
        await db.create_user(ADMIN, "998900000200", "Nazoratchi", None, role="admin")
        await db.create_user(U, "998900000301", "Aliyev Ali", None)
        g1 = await db.create_group("Attestatsiya 1", SUPER)
        g2 = await db.create_group("Sertifikat 2", SUPER)
        await db.assign_admin(g1.id, ADMIN)

        await say(T.BTN_JOIN)
        assert "qo'shildingiz" in (await say(g1.code))[0]
        # menyudagi tugma darhol ogohlantiradi
        out = await say(T.BTN_JOIN)
        assert "Attestatsiya 1" in out[0] and "faqat bitta guruh" in out[0]
        assert [g.id for g in await db.user_groups(U)] == [g1.id]

        # chiqadi -> nazoratchiga xabar -> boshqa guruhga qo'shila oladi
        session.sent.clear()
        await dp.feed_update(bot, cb_update(U, kb.MyGroupCb(action="leave_ok", group_id=g1.id)))
        assert any("guruhidan chiqdi" in out_text(m) and m.chat_id == ADMIN for m in session.sent)
        await say(T.BTN_JOIN)
        assert "qo'shildingiz" in (await say(g2.code))[0]
        assert [g.id for g in await db.user_groups(U)] == [g2.id]
        await db.close()

    asyncio.run(scenario())
