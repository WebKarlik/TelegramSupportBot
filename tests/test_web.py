import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bot.web import create_app

from .conftest import ADMIN, SUPER, TOKEN, USER

pytestmark = pytest.mark.asyncio


def init_data(user_id: int, token: str = TOKEN, age: int = 0) -> str:
    fields = {"auth_date": str(int(time.time()) - age), "query_id": "q",
              "user": json.dumps({"id": user_id, "first_name": "T"})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
async def client(env):
    c = TestClient(TestServer(create_app(env.service)))
    await c.start_server()

    async def call(method, data=None, user=SUPER, **kw):
        headers = {"Authorization": "tma " + init_data(user, **kw)}
        r = await c.post(f"/api/{method}", json=data or {}, headers=headers)
        return r.status, await r.json()

    c.call = call
    yield c
    await c.close()


async def test_auth(client, env):
    r = await client.post("/api/me", json={})
    assert r.status == 401
    assert (await client.call("me", token="1:wrong"))[0] == 401
    assert (await client.call("me", age=3 * 24 * 3600))[0] == 401
    assert (await client.call("me", user=USER))[0] == 403
    status, body = await client.call("me")
    assert status == 200 and body["is_superadmin"] is True


async def test_ticket_flow(client, env):
    await env.send(USER, "помогите")
    status, body = await client.call("listTickets", {"status": "open"})
    assert status == 200 and body["tickets"][0]["last_sender"] == "user" and body["stats"]["waiting"] == 1
    status, body = await client.call("replyTicket", {"id": 1, "text": "Уже чиним"})
    assert status == 200
    assert "Уже чиним" in env.session.sent(USER)[-1].text
    status, body = await client.call("getTicket", {"id": 1})
    assert [m["sender"] for m in body["messages"]] == ["user", "admin"]
    assert "file_id" not in body["messages"][0]
    assert (await client.call("closeTicket", {"id": 1}))[1]["changed"] is True
    assert (await client.call("replyTicket", {"id": 1, "text": "x"}))[0] == 400
    assert (await client.call("reopenTicket", {"id": 1}))[1]["changed"] is True
    assert (await client.call("getTicket", {"id": 99}))[0] == 404
    status, body = await client.call("listTickets", {"status": "all", "q": "помог"})
    assert len(body["tickets"]) == 1


async def test_admin_management(client, env):
    status, _ = await client.call("addAdmin", {"user_id": ADMIN, "name": "Петя"})
    assert status == 200 and env.service.is_admin(ADMIN)
    # обычному админу управление админами недоступно, но тикеты видны
    assert (await client.call("listAdmins", user=ADMIN))[0] == 403
    assert (await client.call("listTickets", user=ADMIN))[0] == 200
    status, body = await client.call("listAdmins")
    assert body["admins"][0]["name"] == "Петя"
    assert (await client.call("addAdmin", {"user_id": ADMIN}))[0] == 400
    assert (await client.call("deleteAdmin", {"user_id": ADMIN}))[0] == 200
    assert (await client.call("me", user=ADMIN))[0] == 403


async def test_unknown_method_and_index(client):
    assert (await client.call("dropDatabase"))[0] == 404
    r = await client.get("/health")
    assert r.status == 200
