import os
import json
import asyncio
from datetime import datetime

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMINS = list(map(int, os.getenv("ADMINS").split(",")))

if not TOKEN:
    raise ValueError("BOT_TOKEN env variable not found")

dp = Dispatcher()
TICKETS_FILE = "tickets.json"
admin_reply_flags = {}

def load_tickets():
    if not os.path.exists(TICKETS_FILE):
        return {}
    with open(TICKETS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_tickets(data):
    with open(TICKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

tickets = load_tickets()

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Поддержка PotatVPN\n\n"
        "Опишите вашу проблему одним сообщением.\n"
        "Все обращения обрабатываются в порядке очереди."
    )

@dp.message()
async def user_message(message: Message, bot: Bot):
    if message.from_user.id in ADMINS:
        admin_id = message.from_user.id
        if admin_id in admin_reply_flags:
            await process_admin_reply(message, bot)
        return

    user_id = str(message.from_user.id)

    tickets[user_id] = {
        "message": message.text,
        "status": "open",
        "time": datetime.now().isoformat()
    }
    save_tickets(tickets)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Ответить", callback_data=f"reply:{user_id}"),
                InlineKeyboardButton(text="Закрыть", callback_data=f"close:{user_id}")
            ]
        ]
    )

    text = (
        f"📩 Новое обращение\n\n"
        f"👤 ID: {user_id}\n"
        f"💬 {message.text}"
    )

    for admin in ADMINS:
        try:
            await bot.send_message(admin, text, reply_markup=keyboard)
        except Exception:
            pass

    await message.answer("✅ Ваше обращение отправлено в поддержку.")

@dp.callback_query(lambda c: c.data and c.data.startswith("reply:"))
async def handle_reply(call: CallbackQuery):
    if call.from_user.id not in ADMINS:
        await call.answer("❌ Только для админов", show_alert=True)
        return

    user_id = call.data.split(":")[1]

    if user_id not in tickets or tickets[user_id]["status"] == "closed":
        await call.answer("❌ Обращение закрыто или не найдено", show_alert=True)
        return

    admin_reply_flags[call.from_user.id] = user_id

    await call.message.answer(f"💬 Напишите ответ пользователю {user_id}:")
    await call.answer()

async def process_admin_reply(message: Message, bot: Bot):
    admin_id = message.from_user.id
    user_id = admin_reply_flags.get(admin_id)

    if not user_id:
        return

    if user_id not in tickets:
        await message.answer("❌ Обращение не найдено. Возможно, оно было удалено.")
        del admin_reply_flags[admin_id]
        return

    if tickets[user_id]["status"] == "closed":
        await message.answer("❌ Обращение уже закрыто. Ответ не отправлен.")
        del admin_reply_flags[admin_id]
        return

    reply_text = message.text

    try:
        await bot.send_message(int(user_id), f"💬 Ответ поддержки:\n\n{reply_text}")
        await message.answer("✅ Ответ успешно отправлен пользователю.")

        if "answers" not in tickets[user_id]:
            tickets[user_id]["answers"] = []
        tickets[user_id]["answers"].append({
            "text": reply_text,
            "time": datetime.now().isoformat(),
            "admin_id": admin_id
        })
        save_tickets(tickets)

    except Exception as e:
        await message.answer(f"❌ Не удалось отправить сообщение пользователю.\nОшибка: {e}")

    del admin_reply_flags[admin_id]

@dp.callback_query(lambda c: c.data and c.data.startswith("close:"))
async def handle_close(call: CallbackQuery):
    if call.from_user.id not in ADMINS:
        await call.answer("❌ Только для админов", show_alert=True)
        return

    user_id = call.data.split(":")[1]

    if user_id not in tickets:
        await call.answer("❌ Обращение не найдено", show_alert=True)
        return

    if tickets[user_id]["status"] == "closed":
        await call.answer("❌ Обращение уже закрыто", show_alert=True)
        return

    tickets[user_id]["status"] = "closed"
    save_tickets(tickets)
    await call.answer(f"✅ Обращение {user_id} закрыто", show_alert=True)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

@dp.message(Command("cancel"))
async def cancel_reply(message: Message):
    if message.from_user.id in ADMINS and message.from_user.id in admin_reply_flags:
        user_id = admin_reply_flags.pop(message.from_user.id)
        await message.answer(f"⛔ Ответ пользователю {user_id} отменён.")
    else:
        await message.answer("⛔ Нет активного ответа для отмены.")

async def main():
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())