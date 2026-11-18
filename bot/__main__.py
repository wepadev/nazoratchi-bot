import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from .config import load_config
from .db import Database
from . import keyboards, scheduler
from .web.api import start_server
from .handlers import appeals, common, groups, superadmin, tests_admin, user
from .middlewares import ContextMiddleware


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()
    db = Database(config.db_path)
    await db.connect()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    mw = ContextMiddleware(db, config)
    dp.message.outer_middleware(mw)
    dp.callback_query.outer_middleware(mw)

    # Tartib muhim: avval umumiy (start / bekor qilish / ro'yxatdan o'tish)
    dp.include_routers(common.router, superadmin.router, groups.router, tests_admin.router,
                       appeals.router, user.router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Asosiy menyu"),
        BotCommand(command="cancel", description="Bekor qilish"),
    ])
    # Mini App: veb-server doim ishlaydi, menyu tugmasi faqat WEBAPP_URL berilganda
    runner = await start_server(db, bot, config)
    keyboards.WEBAPP_URL = config.webapp_url
    if config.webapp_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text="Ilova", web_app=WebAppInfo(url=config.webapp_url + "/")))

    # muddatlar, eslatmalar va haftalik reyting uchun fon jarayoni
    bg = asyncio.create_task(scheduler.run(bot, db, config))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        bg.cancel()
        await runner.cleanup()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
