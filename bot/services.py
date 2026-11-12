"""Бизнес-логика поддержки, общая для чат-бота и мини-приложения."""
import logging
import time
from collections import defaultdict, deque

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonDefault,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from .config import Config
from .db import Database

log = logging.getLogger(__name__)

# Порядок важен: у анимации заполнено и поле document.
MEDIA_TYPES = ("photo", "animation", "video", "video_note", "voice", "audio", "sticker", "document")
MEDIA_LABELS = {
    "photo": "фото", "animation": "GIF", "video": "видео", "video_note": "видеосообщение",
    "voice": "голосовое", "audio": "аудио", "sticker": "стикер", "document": "файл",
}


def extract_content(message: Message) -> tuple[str | None, str | None, str | None] | None:
    """(text, media_type, file_id) или None, если тип сообщения не поддерживается."""
    text = message.text or message.caption
    for media_type in MEDIA_TYPES:
        obj = getattr(message, media_type)
        if obj:
            file_id = obj[-1].file_id if media_type == "photo" else obj.file_id
            return text, media_type, file_id
    if text:
        return text, None, None
    return None


def display_name(first: str | None, last: str | None = None) -> str:
    return " ".join(p for p in (first, last) if p) or "Без имени"


def ticket_title(ticket: dict) -> str:
    who = ticket.get("user_name") or "Без имени"
    if ticket.get("username"):
        who += f" (@{ticket['username']})"
    return f"{who} · ID {ticket['user_id']}"


class RateLimiter:
    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self.hits: dict[int, deque] = defaultdict(deque)
        self.warned: set[int] = set()

    def check(self, user_id: int) -> tuple[bool, bool]:
        """(разрешено, нужно_предупредить)"""
        now = time.monotonic()
        q = self.hits[user_id]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            warn = user_id not in self.warned
            self.warned.add(user_id)
            return False, warn
        q.append(now)
        self.warned.discard(user_id)
        return True, False


class SupportService:
    def __init__(self, bot: Bot, db: Database, config: Config):
        self.bot, self.db, self.config = bot, db, config
        self.rate_limiter = RateLimiter(config.rate_limit_messages, config.rate_limit_window)
        self._admin_cache: set[int] = set()

    # ---------- роли ----------

    async def refresh_admins(self) -> None:
        self._admin_cache = await self.db.admin_ids()

    def is_superadmin(self, user_id: int) -> bool:
        return user_id in self.config.superadmin_ids

    def is_admin(self, user_id: int) -> bool:
        return self.is_superadmin(user_id) or user_id in self._admin_cache

    def all_admin_ids(self) -> list[int]:
        return sorted(self.config.superadmin_ids | self._admin_cache)

    async def add_admin(self, user_id: int, name: str | None, added_by: int) -> bool:
        added = await self.db.add_admin(user_id, name, added_by)
        await self.refresh_admins()
        if added:
            await self.setup_admin_ui(user_id)
            try:
                await self.bot.send_message(
                    user_id,
                    f"🎉 Вас назначили администратором поддержки {self.config.support_name}.\n"
                    "Новые обращения будут приходить сюда. Справка: /help",
                    reply_markup=self.panel_keyboard(),
                )
            except TelegramAPIError:
                log.info("Не удалось уведомить нового админа %s (он ещё не запускал бота)", user_id)
        return added

    async def remove_admin(self, user_id: int) -> bool:
        removed = await self.db.remove_admin(user_id)
        await self.refresh_admins()
        if removed and not self.is_admin(user_id):
            await self.reset_admin_ui(user_id)
        return removed

    # ---------- интерфейс админа в Telegram ----------

    def webapp_button(self, text: str = "🗂 Открыть панель", ticket_id: int | None = None) -> InlineKeyboardButton | None:
        if not self.config.webapp_url:
            return None
        url = self.config.webapp_url
        if ticket_id is not None:
            url += f"#ticket={ticket_id}"
        return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))

    def panel_keyboard(self) -> InlineKeyboardMarkup | None:
        btn = self.webapp_button()
        return InlineKeyboardMarkup(inline_keyboard=[[btn]]) if btn else None

    def ticket_keyboard(self, ticket_id: int) -> InlineKeyboardMarkup:
        rows = [[
            InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{ticket_id}"),
            InlineKeyboardButton(text="✅ Закрыть", callback_data=f"close:{ticket_id}"),
        ]]
        btn = self.webapp_button("🗂 Открыть в панели", ticket_id)
        if btn:
            rows.append([btn])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def setup_admin_ui(self, user_id: int) -> None:
        commands = [
            BotCommand(command="tickets", description="Открытые обращения"),
            BotCommand(command="cancel", description="Отменить ответ"),
            BotCommand(command="help", description="Справка"),
        ]
        if self.config.webapp_url:
            commands.insert(0, BotCommand(command="panel", description="Открыть панель"))
        if self.is_superadmin(user_id):
            commands += [
                BotCommand(command="admins", description="Список админов"),
                BotCommand(command="addadmin", description="Добавить админа"),
            ]
        try:
            await self.bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=user_id))
            if self.config.webapp_url:
                await self.bot.set_chat_menu_button(
                    chat_id=user_id,
                    menu_button=MenuButtonWebApp(text="Панель", web_app=WebAppInfo(url=self.config.webapp_url)),
                )
        except TelegramAPIError as e:
            log.info("Не удалось настроить меню для %s: %s", user_id, e)

    async def reset_admin_ui(self, user_id: int) -> None:
        try:
            await self.bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=user_id))
            await self.bot.set_chat_menu_button(chat_id=user_id, menu_button=MenuButtonDefault())
        except TelegramAPIError as e:
            log.info("Не удалось сбросить меню для %s: %s", user_id, e)

    async def setup_all_ui(self) -> None:
        await self.bot.set_my_commands(
            [BotCommand(command="start", description="Написать в поддержку")], scope=BotCommandScopeDefault()
        )
        for admin_id in self.all_admin_ids():
            await self.setup_admin_ui(admin_id)

    # ---------- обращения ----------

    async def handle_user_message(self, message: Message) -> dict | None:
        """Сохраняет сообщение пользователя и уведомляет админов. Возвращает обращение."""
        content = extract_content(message)
        if content is None:
            return None
        text, media_type, file_id = content
        user = message.from_user
        name = display_name(user.first_name, user.last_name)

        ticket = await self.db.get_open_ticket(user.id)
        is_new = ticket is None
        if is_new:
            ticket = await self.db.create_ticket(user.id, name, user.username)
        elif (ticket["user_name"], ticket["username"]) != (name, user.username):
            await self.db.update_ticket_user(ticket["id"], name, user.username)
            ticket.update(user_name=name, username=user.username)

        await self.db.add_message(ticket["id"], "user", text, media_type, file_id)

        header = f"📩 Новое обращение #{ticket['id']}" if is_new else f"📨 Обращение #{ticket['id']} — новое сообщение"
        lines = [header, "", f"👤 {ticket_title(ticket)}"]
        if media_type:
            lines.append(f"📎 Вложение: {MEDIA_LABELS[media_type]}")
        if text:
            lines += ["", f"💬 {text}"]
        notification_text = "\n".join(lines)
        if len(notification_text) > 4000:
            notification_text = notification_text[:3990] + "…"

        for admin_id in self.all_admin_ids():
            try:
                sent = await self.bot.send_message(
                    admin_id, notification_text, reply_markup=self.ticket_keyboard(ticket["id"])
                )
                await self.db.add_notification(admin_id, sent.message_id, ticket["id"], True)
                if media_type:
                    copy = await self.bot.copy_message(
                        admin_id, message.chat.id, message.message_id, reply_to_message_id=sent.message_id
                    )
                    await self.db.add_notification(admin_id, copy.message_id, ticket["id"], False)
            except TelegramAPIError as e:
                log.warning("Не удалось отправить обращение #%s админу %s: %s", ticket["id"], admin_id, e)
        return ticket

    async def reply(self, ticket_id: int, admin_id: int, *, text: str | None = None,
                    source: Message | None = None) -> dict:
        """Отправляет ответ пользователю. Либо text, либо source (сообщение админа, любой тип)."""
        ticket = await self.db.get_ticket(ticket_id)
        if not ticket:
            raise LookupError("Обращение не найдено")
        if ticket["status"] == "closed":
            raise ValueError("Обращение уже закрыто")

        media_type = file_id = None
        if source is not None:
            content = extract_content(source)
            if content is None:
                raise ValueError("Этот тип сообщения нельзя отправить пользователю")
            text, media_type, file_id = content
        if not media_type and not (text or "").strip():
            raise ValueError("Пустой ответ")

        prefix = f"💬 Ответ поддержки {self.config.support_name}:"
        if media_type:
            await self.bot.send_message(ticket["user_id"], prefix)
            await self.bot.copy_message(ticket["user_id"], source.chat.id, source.message_id)
        else:
            await self.bot.send_message(ticket["user_id"], f"{prefix}\n\n{text}")

        await self.db.add_message(ticket_id, "admin", text, media_type, file_id, admin_id=admin_id)
        return ticket

    async def close(self, ticket_id: int, admin_id: int | None) -> bool:
        ticket = await self.db.get_ticket(ticket_id)
        if not ticket:
            raise LookupError("Обращение не найдено")
        if not await self.db.set_status(ticket_id, "closed", admin_id):
            return False
        for n in await self.db.pop_buttons(ticket_id):
            try:
                await self.bot.edit_message_reply_markup(
                    chat_id=n["chat_id"], message_id=n["message_id"], reply_markup=None
                )
            except TelegramAPIError:
                pass
        try:
            await self.bot.send_message(
                ticket["user_id"],
                f"✅ Ваше обращение #{ticket_id} закрыто.\n"
                "Если вопрос остался — просто напишите сюда, и мы откроем новое обращение.",
            )
        except TelegramAPIError as e:
            log.info("Не удалось уведомить пользователя %s о закрытии: %s", ticket["user_id"], e)
        return True

    async def reopen(self, ticket_id: int, admin_id: int) -> bool:
        ticket = await self.db.get_ticket(ticket_id)
        if not ticket:
            raise LookupError("Обращение не найдено")
        if ticket["status"] == "open":
            return False
        other = await self.db.get_open_ticket(ticket["user_id"])
        if other:
            raise ValueError(f"У пользователя уже есть открытое обращение #{other['id']}")
        return await self.db.set_status(ticket_id, "open", admin_id)
