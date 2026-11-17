"""Dispatcher orqali to'liq oqim: ro'yxatdan o'tish -> admin guruh yaratadi -> foydalanuvchi kod bilan qo'shiladi."""
import asyncio
import datetime as dt
import re

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, Contact, Message, Update, User as TgUser

from bot import texts as T
from bot.config import Config
from bot.db import Database
from bot.handlers import admin, common, superadmin, user
from bot.middlewares import ContextMiddleware


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent: list = []

    async def make_request(self, bot, method, timeout=None):
        self.sent.append(method)
        if isinstance(method, SendMessage):
            return Message(message_id=len(self.sent), date=dt.datetime.now(),
                           chat=Chat(id=method.chat_id, type="private"), text=method.text)
        return True

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        pass


SUPER = 100
STUDENT = 200


def tg(uid):
    return TgUser(id=uid, is_bot=False, first_name=f"U{uid}")


def msg(uid, text=None, contact=None):
    return Update(update_id=0, message=Message(
        message_id=1, date=dt.datetime.now(), chat=Chat(id=uid, type="private"),
        from_user=tg(uid), text=text, contact=contact))


def test_flow():
    async def scenario():
        db = Database(":memory:")
        await db.connect()
        config = Config(bot_token="1:x", super_admin_ids=frozenset({SUPER}), db_path=":memory:")
        session = FakeSession()
        bot = Bot("123:abc", session=session)
        dp = Dispatcher(storage=MemoryStorage())
        mw = ContextMiddleware(db, config)
        dp.message.outer_middleware(mw)
        dp.callback_query.outer_middleware(mw)
        dp.include_routers(common.router, superadmin.router, admin.router, user.router)

        async def send(update):
            session.sent.clear()
            await dp.feed_update(bot, update)
            return [m.text for m in session.sent if isinstance(m, SendMessage)]

        async def register(uid, phone, name):
            assert T.WELCOME in await send(msg(uid, "/start"))
            # boshqa birovning kontakti rad etiladi
            assert T.SHARE_OWN_CONTACT in await send(msg(uid, contact=Contact(
                phone_number="998901111111", first_name="x", user_id=uid + 1)))
            out = await send(msg(uid, contact=Contact(phone_number=phone, first_name="x", user_id=uid)))
            assert T.ASK_FULL_NAME in out
            out = await send(msg(uid, name))
            assert "Ro'yxatdan o'tdingiz" in out[0]

        await register(SUPER, "+998900000100", "Bosh Admin")
        await register(STUDENT, "998900000200", "Talaba Aliyev")
        assert (await db.get_user(SUPER)).is_admin
        assert not (await db.get_user(STUDENT)).is_admin

        # oddiy foydalanuvchi guruh yarata olmaydi (tugma hech narsa qilmaydi)
        assert await send(msg(STUDENT, T.BTN_CREATE_GROUP)) == []

        # admin guruh yaratadi
        await send(msg(SUPER, T.BTN_CREATE_GROUP))
        out = await send(msg(SUPER, "Fizika 10-B"))
        code = re.search(r"<code>(\w+)</code>", out[0]).group(1)

        # foydalanuvchi noto'g'ri, keyin to'g'ri kod bilan qo'shiladi
        await send(msg(STUDENT, T.BTN_JOIN))
        assert T.CODE_NOT_FOUND in await send(msg(STUDENT, "ZZZZZZ"))
        out = await send(msg(STUDENT, code.lower()))
        assert "qo'shildingiz" in out[0]
        assert any("yangi a'zo" in t for t in out)  # adminga bildirishnoma

        out = await send(msg(STUDENT, T.BTN_MY_GROUPS))
        assert "Fizika 10-B" in out[0]

        # bosh admin talabani admin qiladi (telefon raqami orqali)
        await send(msg(SUPER, T.BTN_ADMINS))
        cb = Update(update_id=0, callback_query=CallbackQuery(
            id="1", from_user=tg(SUPER), chat_instance="c", data="a:add:0",
            message=Message(message_id=5, date=dt.datetime.now(), chat=Chat(id=SUPER, type="private"), text="x")))
        await send(cb)
        out = await send(msg(SUPER, "90 000 02 00"))
        assert "admin qilindi" in out[0]
        assert (await db.get_user(STUDENT)).is_admin
        await db.close()

    asyncio.run(scenario())
