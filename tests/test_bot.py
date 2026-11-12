import pytest
from aiogram.methods import AnswerCallbackQuery, CopyMessage, EditMessageReplyMarkup, SendMessage

from .conftest import ADMIN, SUPER, USER

pytestmark = pytest.mark.asyncio


async def test_user_message_creates_ticket_and_notifies_admins(env):
    await env.service.add_admin(ADMIN, "Админ", SUPER)
    env.session.calls.clear()
    await env.send(USER, "Не работает VPN")
    ticket = await env.db.get_open_ticket(USER)
    assert ticket and ticket["id"] == 1
    assert {c.chat_id for c in env.session.sent()} == {SUPER, ADMIN, USER}
    assert "Не работает VPN" in env.session.sent(SUPER)[0].text
    assert "#1 отправлено" in env.session.sent(USER)[0].text

    # Второе сообщение дописывается в то же обращение, без повторного подтверждения пользователю.
    env.session.calls.clear()
    await env.send(USER, "Ещё деталь")
    assert (await env.db.get_open_ticket(USER))["id"] == 1
    assert len(await env.db.get_messages(1)) == 2
    assert env.session.sent(USER) == []


async def test_cancel_is_not_sent_to_user(env):
    """Регрессия: раньше /cancel админа уходил пользователю как ответ."""
    await env.send(USER, "help")
    await env.press(SUPER, "reply:1")
    env.session.calls.clear()
    await env.send(SUPER, "/cancel")
    assert env.session.sent(USER) == []
    assert "отменён" in env.session.sent(SUPER)[0].text
    # После отмены обычный текст не уходит пользователю.
    env.session.calls.clear()
    await env.send(SUPER, "просто текст")
    assert env.session.sent(USER) == []


async def test_reply_via_button_and_via_quote(env):
    await env.send(USER, "help")
    await env.press(SUPER, "reply:1")
    env.session.calls.clear()
    await env.send(SUPER, "Перезагрузите роутер")
    assert "Перезагрузите роутер" in env.session.sent(USER)[0].text

    notification = await env.db._one("SELECT message_id FROM notifications WHERE chat_id = ? AND has_buttons = 1",
                                     (SUPER,))
    env.session.calls.clear()
    await env.send(SUPER, "И ещё совет", reply_to_message={
        "message_id": notification["message_id"], "date": 1700000000,
        "chat": {"id": SUPER, "type": "private"}, "text": "x"})
    assert "И ещё совет" in env.session.sent(USER)[0].text
    msgs = await env.db.get_messages(1)
    assert [m["sender"] for m in msgs] == ["user", "admin", "admin"]


async def test_media_is_forwarded(env):
    await env.send(USER, caption="скрин", photo=[{"file_id": "PHOTO", "file_unique_id": "u", "width": 1, "height": 1}])
    msgs = await env.db.get_messages(1)
    assert msgs[0]["media_type"] == "photo" and msgs[0]["text"] == "скрин" and msgs[0]["file_id"] == "PHOTO"
    assert any(c.chat_id == SUPER for c in env.session.sent(kind=CopyMessage))


async def test_close_removes_buttons_notifies_user_and_new_message_opens_new_ticket(env):
    await env.send(USER, "help")
    env.session.calls.clear()
    await env.press(SUPER, "close:1")
    assert (await env.db.get_ticket(1))["status"] == "closed"
    assert env.session.sent(kind=EditMessageReplyMarkup)
    assert "закрыто" in env.session.sent(USER)[0].text
    await env.send(USER, "снова я")
    assert (await env.db.get_open_ticket(USER))["id"] == 2
    # Старое обращение не затёрто.
    assert (await env.db.get_messages(1))[0]["text"] == "help"


async def test_non_admin_cannot_press_admin_buttons(env):
    await env.send(USER, "help")
    await env.press(USER, "close:1")
    assert (await env.db.get_ticket(1))["status"] == "open"


async def test_superadmin_manages_admins(env):
    await env.send(SUPER, f"/addadmin {ADMIN}")
    assert env.service.is_admin(ADMIN)
    # обычный админ не может добавлять админов
    await env.send(ADMIN, "/addadmin 5555")
    assert not env.service.is_admin(5555)
    await env.send(SUPER, f"/deladmin {ADMIN}")
    assert not env.service.is_admin(ADMIN)
    # теперь его сообщение — это обращение пользователя
    await env.send(ADMIN, "я больше не админ")
    assert await env.db.get_open_ticket(ADMIN)


async def test_users_shared_adds_admin(env):
    await env.send(SUPER, users_shared={"request_id": 1, "users": [{"user_id": 777, "first_name": "Пётр"}]})
    admins = await env.db.list_admins()
    assert admins[0]["user_id"] == 777 and admins[0]["name"] == "Пётр"


async def test_rate_limit(env):
    for i in range(8):
        await env.send(USER, f"spam {i}")
    assert len(await env.db.get_messages(1)) == env.config.rate_limit_messages
    warnings = [c for c in env.session.sent(USER) if "Слишком много" in c.text]
    assert len(warnings) == 1


async def test_unsupported_message(env):
    await env.send(USER, location={"latitude": 1.0, "longitude": 2.0})
    assert await env.db.get_open_ticket(USER) is None
    assert "не поддерживается" in env.session.sent(USER)[0].text


async def test_legacy_json_import(env, tmp_path):
    import json
    legacy = tmp_path / "tickets.json"
    legacy.write_text(json.dumps({"55": {"message": "старое", "status": "closed", "time": "2026-01-01T00:00:00",
                                         "answers": [{"text": "ответ", "time": "2026-01-01T01:00:00", "admin_id": 1}]},
                                  "66": {"message": "открытое", "status": "open", "time": "2026-01-02T00:00:00"}}),
                      encoding="utf-8")
    assert await env.db.import_legacy_json(legacy) == 2
    assert (await env.db.get_open_ticket(66))["id"] == 2
    assert [m["text"] for m in await env.db.get_messages(1)] == ["старое", "ответ"]
    assert not legacy.exists()
