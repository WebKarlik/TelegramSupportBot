from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from ..filters import IsSuperAdmin
from ..services import SupportService, display_name

router = Router(name="superadmin")
router.message.filter(F.chat.type == "private", IsSuperAdmin())
router.callback_query.filter(IsSuperAdmin())

REQUEST_ADMIN_ID = 1


async def _admins_view(service: SupportService) -> tuple[str, InlineKeyboardMarkup | None]:
    admins = await service.db.list_admins()
    lines = ["👑 Суперадмины (из .env):"]
    lines += [f"• {uid}" for uid in sorted(service.config.superadmin_ids)]
    lines += ["", "🛠 Админы:"]
    rows = []
    if not admins:
        lines.append("— пока никого. Добавить: /addadmin")
    for a in admins:
        name = a["name"] or "Без имени"
        lines.append(f"• {name} — {a['user_id']}")
        rows.append([InlineKeyboardButton(text=f"❌ Удалить {name}", callback_data=f"deladmin:{a['user_id']}")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


@router.message(Command("admins"))
async def list_admins(message: Message, service: SupportService):
    text, kb = await _admins_view(service)
    await message.answer(text, reply_markup=kb)


async def _add(message: Message, service: SupportService, user_id: int, name: str | None):
    if service.is_superadmin(user_id):
        await message.answer("ℹ️ Это суперадмин — он и так видит все обращения.", reply_markup=ReplyKeyboardRemove())
        return
    if await service.add_admin(user_id, name, message.from_user.id):
        await message.answer(
            f"✅ {name or user_id} добавлен в админы.\n"
            "Если он ещё не запускал бота — пусть нажмёт /start, иначе бот не сможет присылать ему обращения.",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await message.answer("ℹ️ Этот пользователь уже админ.", reply_markup=ReplyKeyboardRemove())


@router.message(Command("addadmin"))
async def add_admin(message: Message, command: CommandObject, service: SupportService):
    if command.args:
        arg = command.args.strip()
        if not arg.lstrip("-").isdigit():
            await message.answer("Укажите числовой Telegram ID: /addadmin 123456789")
            return
        user_id = int(arg)
        name = None
        try:
            chat = await message.bot.get_chat(user_id)
            name = display_name(chat.first_name, chat.last_name)
        except TelegramAPIError:
            pass
        await _add(message, service, user_id, name)
        return

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="👤 Выбрать пользователя",
                request_users=KeyboardButtonRequestUsers(
                    request_id=REQUEST_ADMIN_ID, user_is_bot=False, max_quantity=1,
                    request_name=True, request_username=True,
                ),
            )],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        "Выберите пользователя из контактов кнопкой ниже\nили отправьте команду с ID: /addadmin 123456789",
        reply_markup=kb,
    )


@router.message(F.users_shared.request_id == REQUEST_ADMIN_ID)
async def admin_shared(message: Message, service: SupportService):
    shared = message.users_shared.users[0]
    await _add(message, service, shared.user_id, display_name(shared.first_name, shared.last_name))


@router.message(F.text == "Отмена")
async def cancel_keyboard(message: Message):
    await message.answer("Ок, отменено.", reply_markup=ReplyKeyboardRemove())


@router.message(Command("deladmin"))
async def del_admin(message: Message, command: CommandObject, service: SupportService):
    arg = (command.args or "").strip()
    if not arg.isdigit():
        text, kb = await _admins_view(service)
        await message.answer("Укажите ID: /deladmin 123456789 — или нажмите кнопку ниже.\n\n" + text, reply_markup=kb)
        return
    if await service.remove_admin(int(arg)):
        await message.answer(f"✅ Админ {arg} удалён.")
    else:
        await message.answer("ℹ️ Такого админа нет (суперадминов можно убрать только в .env).")


@router.callback_query(F.data.startswith("deladmin:"))
async def del_admin_button(call: CallbackQuery, service: SupportService):
    user_id = int(call.data.split(":", 1)[1])
    removed = await service.remove_admin(user_id)
    await call.answer("✅ Удалён" if removed else "ℹ️ Уже удалён")
    text, kb = await _admins_view(service)
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except TelegramAPIError:
        pass
