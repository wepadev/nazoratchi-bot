from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from .config import Config
from .db import Database


class ContextMiddleware(BaseMiddleware):
    """Har bir handlerga db, config, joriy foydalanuvchi va uning huquqlarini uzatadi."""

    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        user = await self.db.get_user(tg_user.id) if tg_user else None
        is_super = bool(tg_user and tg_user.id in self.config.super_admin_ids)
        data.update(
            db=self.db,
            config=self.config,
            user=user,
            is_super=is_super,
            is_admin=is_super or bool(user and user.is_admin),
        )
        return await handler(event, data)
