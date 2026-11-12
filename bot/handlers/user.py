from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from ..services import SupportService

router = Router(name="user")
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def start(message: Message, service: SupportService):
    await message.answer(
        f"👋 Поддержка {service.config.support_name}\n\n"
        "Опишите вашу проблему — можно приложить скриншот или файл.\n"
        "Все обращения обрабатываются в порядке очереди, ответ придёт сюда."
    )


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message):
    await message.answer("Просто опишите вашу проблему обычным сообщением 🙂")


@router.message()
async def user_message(message: Message, service: SupportService):
    allowed, warn = service.rate_limiter.check(message.from_user.id)
    if not allowed:
        if warn:
            await message.answer("⏳ Слишком много сообщений подряд. Подождите немного и напишите снова.")
        return

    existing = await service.db.get_open_ticket(message.from_user.id)
    ticket = await service.handle_user_message(message)
    if ticket is None:
        await message.answer("⚠️ Этот тип сообщений не поддерживается. Отправьте текст, фото, видео или файл.")
        return
    if existing is None:
        await message.answer(
            f"✅ Ваше обращение #{ticket['id']} отправлено в поддержку.\n"
            "Если хотите что-то добавить — просто напишите ещё."
        )
