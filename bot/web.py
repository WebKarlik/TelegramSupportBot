"""HTTP API и статика мини-приложения (Telegram Web App).

API устроено так же, как endpoints в Telegram Serverless: POST /api/<имя> с JSON,
поэтому одно и то же мини-приложение работает с обеими версиями бота.

Каждый запрос к /api подписан initData от Telegram — проверяем подпись токеном бота,
так что подделать пользователя нельзя, а доступ есть только у админов.
"""
import base64
import logging
import mimetypes
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from aiogram.exceptions import TelegramAPIError
from aiogram.utils.web_app import safe_parse_webapp_init_data
from aiohttp import web

from .services import SupportService

log = logging.getLogger(__name__)

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"
INIT_DATA_TTL = timedelta(hours=24)
MEDIA_MIME = {"photo": "image/jpeg", "sticker": "image/webp", "voice": "audio/ogg", "video_note": "video/mp4",
              "animation": "video/mp4", "video": "video/mp4"}

SERVICE = web.AppKey("service", SupportService)
USER_ID = web.RequestKey("user_id", int)


def _err(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)
    service = request.app[SERVICE]
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("tma "):
        return _err(401, "Откройте панель из Telegram")
    try:
        data = safe_parse_webapp_init_data(service.config.bot_token, auth[4:])
    except ValueError:
        return _err(401, "Неверная подпись Telegram")
    if not data.user or datetime.now(timezone.utc) - data.auth_date > INIT_DATA_TTL:
        return _err(401, "Сессия устарела — переоткройте панель")
    if not service.is_admin(data.user.id):
        return _err(403, "Доступ только для администраторов")
    request[USER_ID] = data.user.id
    return await handler(request)


def _int(value: str, what: str = "ID") -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Некорректный {what}") from None


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEBAPP_DIR / "index.html", headers={"Cache-Control": "no-cache"})


async def health(request: web.Request) -> web.Response:
    return web.Response(text="ok")


# ---------- RPC-методы: (service, user_id, input) -> dict ----------

async def me(service: SupportService, uid: int, data: dict) -> dict:
    return {
        "user_id": uid,
        "is_superadmin": service.is_superadmin(uid),
        "support_name": service.config.support_name,
        "stats": await service.db.stats(),
    }


async def list_tickets(service: SupportService, uid: int, data: dict) -> dict:
    status = data.get("status") or "open"
    if status not in ("open", "closed", "all"):
        raise ValueError("Некорректный статус")
    q = str(data.get("q") or "").strip() or None
    tickets = await service.db.list_tickets(None if status == "all" else status, limit=200, query=q)
    return {"tickets": tickets, "stats": await service.db.stats()}


async def get_ticket(service: SupportService, uid: int, data: dict) -> dict:
    ticket_id = _int(data.get("id"))
    ticket = await service.db.get_ticket(ticket_id)
    if not ticket:
        raise LookupError("Обращение не найдено")
    messages = await service.db.get_messages(ticket_id)
    for m in messages:
        m["has_file"] = bool(m.pop("file_id", None))
    return {"ticket": ticket, "messages": messages}


async def reply_ticket(service: SupportService, uid: int, data: dict) -> dict:
    text = str(data.get("text") or "").strip()
    if len(text) > 4000:
        raise ValueError("Слишком длинный ответ (максимум 4000 символов)")
    await service.reply(_int(data.get("id")), uid, text=text)
    return {"ok": True}


async def close_ticket(service: SupportService, uid: int, data: dict) -> dict:
    return {"ok": True, "changed": await service.close(_int(data.get("id")), uid)}


async def reopen_ticket(service: SupportService, uid: int, data: dict) -> dict:
    return {"ok": True, "changed": await service.reopen(_int(data.get("id")), uid)}


async def get_file(service: SupportService, uid: int, data: dict) -> dict:
    msg = await service.db.get_message(_int(data.get("message_id")))
    if not msg or not msg["file_id"]:
        raise LookupError("Файл не найден")
    try:
        file = await service.bot.get_file(msg["file_id"])
    except TelegramAPIError:
        raise ValueError("Файл слишком большой для просмотра (лимит Telegram — 20 МБ)") from None
    buf = BytesIO()
    await service.bot.download_file(file.file_path, buf)
    mime = mimetypes.guess_type(file.file_path or "")[0] or MEDIA_MIME.get(msg["media_type"]) \
        or "application/octet-stream"
    return {"mime": mime, "data": base64.b64encode(buf.getvalue()).decode()}


def _superadmin_only(service: SupportService, uid: int) -> None:
    if not service.is_superadmin(uid):
        raise PermissionError("Только для суперадмина")


async def list_admins(service: SupportService, uid: int, data: dict) -> dict:
    _superadmin_only(service, uid)
    return {"superadmins": sorted(service.config.superadmin_ids), "admins": await service.db.list_admins()}


async def add_admin(service: SupportService, uid: int, data: dict) -> dict:
    _superadmin_only(service, uid)
    user_id = _int(str(data.get("user_id", "")).strip(), "Telegram ID")
    if service.is_superadmin(user_id):
        raise ValueError("Это суперадмин — у него уже есть доступ")
    name = str(data.get("name") or "").strip() or None
    if not name:
        try:
            chat = await service.bot.get_chat(user_id)
            name = " ".join(p for p in (chat.first_name, chat.last_name) if p) or None
        except TelegramAPIError:
            pass
    if not await service.add_admin(user_id, name, uid):
        raise ValueError("Этот пользователь уже админ")
    return {"ok": True}


async def delete_admin(service: SupportService, uid: int, data: dict) -> dict:
    _superadmin_only(service, uid)
    if not await service.remove_admin(_int(data.get("user_id"))):
        raise LookupError("Админ не найден")
    return {"ok": True}


METHODS = {
    "me": me,
    "listTickets": list_tickets,
    "getTicket": get_ticket,
    "replyTicket": reply_ticket,
    "closeTicket": close_ticket,
    "reopenTicket": reopen_ticket,
    "getFile": get_file,
    "listAdmins": list_admins,
    "addAdmin": add_admin,
    "deleteAdmin": delete_admin,
}


async def rpc(request: web.Request) -> web.Response:
    method = METHODS.get(request.match_info["method"])
    if method is None:
        return _err(404, "Неизвестный метод")
    try:
        data = await request.json() if request.can_read_body else {}
    except ValueError:
        return _err(400, "Некорректный JSON")
    if not isinstance(data, dict):
        return _err(400, "Ожидается JSON-объект")
    service = request.app[SERVICE]
    try:
        return web.json_response(await method(service, request[USER_ID], data))
    except PermissionError as e:
        return _err(403, str(e))
    except LookupError as e:
        return _err(404, str(e))
    except ValueError as e:
        return _err(400, str(e))
    except TelegramAPIError as e:
        return _err(502, f"Ошибка Telegram: {e.message}")
    except Exception:
        log.exception("Ошибка в методе API %s", request.match_info["method"])
        return _err(500, "Внутренняя ошибка сервера")


def create_app(service: SupportService) -> web.Application:
    app = web.Application(middlewares=[auth_middleware], client_max_size=64 * 1024)
    app[SERVICE] = service
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_post("/api/{method}", rpc)
    return app
