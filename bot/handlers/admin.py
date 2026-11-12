import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..filters import IsAdmin
from ..services import MEDIA_LABELS, SupportService, ticket_title

log = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(F.chat.type == "private", IsAdmin())
router.callback_query.filter(IsAdmin())


class ReplyState(StatesGroup):
    waiting = State()


HELP = (
    "🛠 Вы администратор поддержки.\n\n"
    "Как ответить пользователю:\n"
    "• нажмите «✍️ Ответить» под обращением и отправьте сообщение, или\n"
    "• ответьте (reply) прямо на уведомление об обращении.\n"
    "Можно отправлять текст, фото, видео и файлы.\n\n"
    "/tickets — открытые обращения\n"
    "/cancel — отменить ответ\n"
)


def _ticket_id(data: str) -> int | None:
    try:
        return int(data.split(":", 1)[1])
    except (IndexError, ValueError):
        return None


@router.message(CommandStart())
@router.message(Command("help"))
async def admin_help(message: Message, service: SupportService):
    text = HELP
    if service.config.webapp_url:
        text += "/panel — открыть панель (мини-приложение)\n"
    if service.is_superadmin(message.from_user.id):
        text += "\n👑 Суперадмин:\n/admins — список админов\n/addadmin — добавить админа\n/deladmin ID — удалить админа\n"
    await message.answer(text, reply_markup=service.panel_keyboard())


@router.message(Command("panel"))
async def panel(message: Message, service: SupportService):
    kb = service.panel_keyboard()
    if not kb:
        await message.answer("Мини-приложение не настроено: укажите WEBAPP_DOMAIN или WEBAPP_URL в .env")
        return
    await message.answer("Панель поддержки:", reply_markup=kb)


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    data = await state.get_data()
    if await state.get_state() is None:
        await message.answer("⛔ Нет активного ответа для отмены.")
        return
    await state.clear()
    await message.answer(f"⛔ Ответ на обращение #{data.get('ticket_id')} отменён.")


@router.message(Command("tickets"))
async def tickets_list(message: Message, service: SupportService):
    tickets = await service.db.list_tickets("open", limit=30)
    if not tickets:
        await message.answer("🎉 Открытых обращений нет.", reply_markup=service.panel_keyboard())
        return
    lines = [f"📂 Открытые обращения ({len(tickets)}):", ""]
    buttons = []
    for t in tickets:
        mark = "🔴" if t["last_sender"] == "user" else "🟢"
        preview = (t["last_text"] or "").replace("\n", " ")
        if len(preview) > 50:
            preview = preview[:50] + "…"
        lines.append(f"{mark} #{t['id']} {t['user_name'] or t['user_id']}: {preview}")
        buttons.append(InlineKeyboardButton(text=f"#{t['id']}", callback_data=f"view:{t['id']}"))
    lines += ["", "🔴 — ждёт ответа, 🟢 — отвечено"]
    rows = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("view:"))
async def view_ticket(call: CallbackQuery, service: SupportService):
    ticket_id = _ticket_id(call.data)
    ticket = await service.db.get_ticket(ticket_id) if ticket_id else None
    if not ticket:
        await call.answer("❌ Обращение не найдено", show_alert=True)
        return
    messages = await service.db.get_messages(ticket_id)
    status = "открыто" if ticket["status"] == "open" else "закрыто"
    lines = [f"📄 Обращение #{ticket_id} ({status})", f"👤 {ticket_title(ticket)}", ""]
    for m in messages[-15:]:
        who = "👤" if m["sender"] == "user" else "🛠"
        body = m["text"] or ""
        if m["media_type"]:
            body = f"[{MEDIA_LABELS.get(m['media_type'], m['media_type'])}] {body}".strip()
        lines.append(f"{who} {body}")
    if len(messages) > 15:
        lines.insert(3, f"… ещё {len(messages) - 15} сообщений выше\n")
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3990] + "…"
    if ticket["status"] == "open":
        kb = service.ticket_keyboard(ticket_id)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="♻️ Открыть заново", callback_data=f"reopen:{ticket_id}")
        ]])
    sent = await call.message.answer(text, reply_markup=kb)
    await service.db.add_notification(sent.chat.id, sent.message_id, ticket_id, ticket["status"] == "open")
    await call.answer()


@router.callback_query(F.data.startswith("reply:"))
async def reply_button(call: CallbackQuery, service: SupportService, state: FSMContext):
    ticket_id = _ticket_id(call.data)
    ticket = await service.db.get_ticket(ticket_id) if ticket_id else None
    if not ticket or ticket["status"] == "closed":
        await call.answer("❌ Обращение закрыто или не найдено", show_alert=True)
        return
    await state.set_state(ReplyState.waiting)
    await state.update_data(ticket_id=ticket_id)
    await call.message.answer(
        f"✍️ Напишите ответ на обращение #{ticket_id} ({ticket_title(ticket)}).\n"
        "Можно приложить фото или файл. /cancel — отменить."
    )
    await call.answer()


@router.callback_query(F.data.startswith("close:"))
async def close_button(call: CallbackQuery, service: SupportService):
    ticket_id = _ticket_id(call.data)
    try:
        closed = await service.close(ticket_id, call.from_user.id) if ticket_id else None
    except LookupError:
        closed = None
    if closed is None:
        await call.answer("❌ Обращение не найдено", show_alert=True)
    elif not closed:
        await call.answer("ℹ️ Обращение уже закрыто", show_alert=True)
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except TelegramAPIError:
            pass
    else:
        await call.answer(f"✅ Обращение #{ticket_id} закрыто")


@router.callback_query(F.data.startswith("reopen:"))
async def reopen_button(call: CallbackQuery, service: SupportService):
    ticket_id = _ticket_id(call.data)
    try:
        ok = await service.reopen(ticket_id, call.from_user.id)
    except (LookupError, ValueError) as e:
        await call.answer(f"❌ {e}", show_alert=True)
        return
    if not ok:
        await call.answer("ℹ️ Обращение уже открыто", show_alert=True)
        return
    await call.answer(f"♻️ Обращение #{ticket_id} снова открыто")
    try:
        await call.message.edit_reply_markup(reply_markup=service.ticket_keyboard(ticket_id))
        await service.db.add_notification(call.message.chat.id, call.message.message_id, ticket_id, True)
    except TelegramAPIError:
        pass


async def _send_reply(message: Message, service: SupportService, ticket_id: int) -> bool:
    try:
        ticket = await service.reply(ticket_id, message.from_user.id, source=message)
    except (LookupError, ValueError) as e:
        await message.answer(f"❌ {e}. Ответ не отправлен.")
        return False
    except TelegramAPIError as e:
        log.warning("Не удалось отправить ответ по #%s: %s", ticket_id, e)
        await message.answer(f"❌ Не удалось отправить сообщение пользователю.\nОшибка: {e.message}")
        return False
    confirm = await message.answer(
        f"✅ Ответ на обращение #{ticket_id} отправлен.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Закрыть обращение", callback_data=f"close:{ticket_id}")
        ]]),
    )
    await service.db.add_notification(confirm.chat.id, confirm.message_id, ticket["id"], True)
    return True


@router.message(StateFilter(ReplyState.waiting))
async def reply_from_state(message: Message, service: SupportService, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await _send_reply(message, service, data["ticket_id"])


@router.message(F.reply_to_message)
async def reply_by_quote(message: Message, service: SupportService):
    ticket_id = await service.db.ticket_by_notification(message.chat.id, message.reply_to_message.message_id)
    if ticket_id is None:
        await message.answer("🤔 Не понял, к какому обращению это относится. Ответьте на уведомление об обращении.")
        return
    await _send_reply(message, service, ticket_id)


@router.message()
async def admin_fallback(message: Message, service: SupportService):
    await message.answer(
        "ℹ️ Чтобы ответить пользователю, нажмите «✍️ Ответить» под обращением "
        "или ответьте (reply) на уведомление. Список: /tickets",
        reply_markup=service.panel_keyboard(),
    )
