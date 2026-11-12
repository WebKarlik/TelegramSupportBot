import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from .config import load_config
from .db import Database
from .handlers import setup_routers
from .services import SupportService
from .web import create_app

log = logging.getLogger("bot")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()

    db = Database(config.db_path)
    await db.connect()
    await db.import_legacy_json(config.db_path.parent / "tickets.json")

    bot = Bot(token=config.bot_token)
    service = SupportService(bot, db, config)
    if db.created:
        # ADMINS из .env — только стартовый список; дальше админами управляет суперадмин.
        for admin_id in config.initial_admin_ids:
            if admin_id not in config.superadmin_ids:
                await db.add_admin(admin_id, None, None)
    await service.refresh_admins()

    dp = Dispatcher(storage=MemoryStorage())
    dp["service"] = service
    dp.include_router(setup_routers())

    runner = web.AppRunner(create_app(service), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, config.web_host, config.web_port).start()
    log.info("Веб-сервер запущен на %s:%s, мини-приложение: %s",
             config.web_host, config.web_port, config.webapp_url or "не настроено")

    try:
        try:
            await service.setup_all_ui()
            # Если раньше бот работал в Telegram Serverless, там стоял webhook — polling с ним не работает.
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            log.exception("Не удалось настроить меню бота — продолжаю запуск")
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await db.close()
        await bot.session.close()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
