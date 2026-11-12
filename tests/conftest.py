import itertools
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import CopyMessage, GetChat, SendMessage, TelegramMethod
from aiogram.types import Chat, ChatFullInfo, Message, MessageId, Update

from bot.config import Config
from bot.db import Database
from bot.handlers import setup_routers
from bot.services import SupportService

SUPER = 1000
ADMIN = 2000
USER = 3000
TOKEN = "42:TEST_TOKEN_FOR_UNIT_TESTS_ONLY_xxxxxxxxx"


class FakeSession(BaseSession):
    """Ничего не отправляет в Telegram, только запоминает вызовы."""

    def __init__(self):
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self.ids = itertools.count(100)

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message(message_id=next(self.ids), date=datetime.now(timezone.utc),
                           chat=Chat(id=method.chat_id, type="private"), text=method.text)
        if isinstance(method, CopyMessage):
            return MessageId(message_id=next(self.ids))
        if isinstance(method, GetChat):
            return ChatFullInfo.model_construct(id=method.chat_id, type="private", first_name="Иван",
                                                last_name=None)
        return True

    async def stream_content(self, *a, **kw):  # pragma: no cover
        yield b""

    async def close(self):
        pass

    def sent(self, chat_id=None, kind=SendMessage):
        return [c for c in self.calls if isinstance(c, kind) and (chat_id is None or c.chat_id == chat_id)]


_DP: Dispatcher | None = None


def _dispatcher() -> Dispatcher:
    # Роутеры aiogram подключаются один раз, поэтому Dispatcher общий на все тесты.
    global _DP
    if _DP is None:
        _DP = Dispatcher(storage=MemoryStorage())
        _DP.include_router(setup_routers())
    _DP.fsm.storage = MemoryStorage()
    return _DP


@pytest_asyncio.fixture
async def env(tmp_path):
    config = Config(
        bot_token=TOKEN, superadmin_ids=frozenset({SUPER}), initial_admin_ids=(), support_name="Test",
        db_path=tmp_path / "bot.db", webapp_url="https://example.com/", web_host="127.0.0.1", web_port=0,
    )
    db = Database(config.db_path)
    await db.connect()
    session = FakeSession()
    bot = Bot(token=TOKEN, session=session)
    service = SupportService(bot, db, config)
    await service.refresh_admins()
    dp = _dispatcher()
    dp["service"] = service
    counter = itertools.count(1)

    async def send(user_id, text=None, **extra):
        msg = {"message_id": next(counter), "date": 1700000000, "chat": {"id": user_id, "type": "private"},
               "from": {"id": user_id, "is_bot": False, "first_name": f"U{user_id}"}}
        if text is not None:
            msg["text"] = text
            if text.startswith("/"):
                msg["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        msg.update(extra)
        await dp.feed_update(bot, Update.model_validate({"update_id": next(counter), "message": msg},
                                                        context={"bot": bot}))

    async def press(user_id, data, message_id=1):
        cq = {"id": str(next(counter)), "chat_instance": "x", "data": data,
              "from": {"id": user_id, "is_bot": False, "first_name": "A"},
              "message": {"message_id": message_id, "date": 1700000000,
                          "chat": {"id": user_id, "type": "private"}, "text": "x"}}
        await dp.feed_update(bot, Update.model_validate({"update_id": next(counter), "callback_query": cq},
                                                        context={"bot": bot}))

    class Env:
        pass

    e = Env()
    e.db, e.bot, e.session, e.service, e.dp, e.send, e.press, e.config = db, bot, session, service, dp, send, press, config
    yield e
    await db.close()

