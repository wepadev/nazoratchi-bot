"""Tez formatlar: nazoratchi '+Nomi*kalit' bilan test yaratadi, ustoz 'kod*javoblar' bilan topshiradi."""
import asyncio
from datetime import timedelta

from aiogram import Bot

from bot import keyboards as kb
from bot import services
from bot.answers import looks_like_answers, split_quick
from bot.config import Config
from bot.db import Database
from bot.timeutil import utcnow
from tests.test_flow import FakeSession, build_dispatcher, cb_update, msg_update, out_text

SUPER, U = 100, 301


def test_helpers():
    assert split_quick("12*abcd") == (12, "abcd")
    assert split_quick(" 12 * 1a 2b") == (12, "1a 2b")
    assert split_quick("abcd") == (None, "abcd")
    assert looks_like_answers("abcd") and looks_like_answers("1a 2b 3c") and looks_like_answers("абсд")
    assert not looks_like_answers("salom") and not looks_like_answers("rahmat ustoz") and not looks_like_answers("a")


def test_quick_flow():
    async def scenario():
        db = Database(":memory:")
        await db.connect()
        cfg = Config(bot_token="1:x", super_admin_ids=frozenset({SUPER}), db_path=":memory:")
        session = FakeSession()
        bot = Bot("123:abc", session=session)
        dp = build_dispatcher(db, cfg)

        async def say(uid, text):
            session.sent.clear()
            await dp.feed_update(bot, msg_update(uid, text))
            return [out_text(m) for m in session.sent]

        async def click(uid, data):
            session.sent.clear()
            await dp.feed_update(bot, cb_update(uid, data))
            return [out_text(m) for m in session.sent]

        now = utcnow()
        await db.create_user(SUPER, "998900000100", "Bosh", None, role="admin")
        await db.create_user(U, "998900000301", "Ustoz", None)
        g1 = await db.create_group("G1", SUPER)
        g2 = await db.create_group("G2", SUPER)
        # eski ma'lumotlar: qoida kiritilishidan oldin ikki guruhga qo'shilgan ustoz ham ishlashi kerak
        for g in (g1, g2):
            await db.add_member(g.id, U, now - timedelta(days=1), exclusive=False)

        # --- nazoratchi: tez yaratish (2 ta guruh -> tanlash) ---
        out = await say(SUPER, "+Tez test*abcd")
        assert "qaysi guruh" in out[0]
        out = await click(SUPER, kb.GroupCb(action="quick", group_id=g1.id))
        assert any("Test saqlandi" in t for t in out)
        t1 = (await db.list_tests(g1.id))[0]
        assert t1.title == "Tez test" and t1.answer_key == "ABCD" and t1.status == "draft"
        assert any("Kalit" in t for t in await say(SUPER, "+Yomon*abce"))

        await services.publish(bot, db, cfg, t1, now + timedelta(hours=5), now)
        assert any(f"{t1.id}*abcd" in out_text(m) for m in session.sent if m.chat_id == U)

        # --- ustoz: oddiy gap e'tiborsiz, kodsiz javob (bitta faol test) ---
        assert await say(U, "salom") == []
        out = await say(U, "abca")
        assert "Javoblaringizni tekshiring" in out[0]
        out = await click(U, kb.TestCb(action="confirm", test_id=t1.id))
        assert any("3/4" in t for t in out)

        # --- ikki faol test: kod so'raladi ---
        t2 = await db.create_test(g2.id, "Ikkinchi", "AAAA", None, None, SUPER)
        t3 = await db.create_test(g1.id, "Uchinchi", "BBBB", None, None, SUPER)
        await services.publish(bot, db, cfg, t2, now + timedelta(hours=5), now)
        await db.close_test(t1.id, now)
        await services.publish(bot, db, cfg, t3, now + timedelta(hours=5), now)
        out = await say(U, "aaaa")
        assert "bir nechta faol test" in out[0] and f"{t2.id}*" in out[0]
        out = await say(U, f"{t2.id}*aaab")
        assert "Ikkinchi" in out[0]
        out = await click(U, kb.TestCb(action="confirm", test_id=t2.id))
        assert any("3/4" in t for t in out)
        assert "allaqachon" in (await say(U, f"{t2.id}*aaaa"))[0]
        assert "faol emas" in (await say(U, "9999*abcd"))[0]
        assert "❌" in (await say(U, f"{t3.id}*bb"))[0]  # savollar soni noto'g'ri
        await db.close()

    asyncio.run(scenario())
