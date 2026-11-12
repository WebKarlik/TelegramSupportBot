"""Хранилище на SQLite: админы, обращения, сообщения и уведомления админам."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
    user_id   INTEGER PRIMARY KEY,
    name      TEXT,
    added_by  INTEGER,
    added_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    user_name   TEXT,
    username    TEXT,
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    closed_at   TEXT,
    closed_by   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status, updated_at);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
    sender      TEXT NOT NULL,            -- 'user' | 'admin'
    admin_id    INTEGER,
    text        TEXT,
    media_type  TEXT,
    file_id     TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_ticket ON messages(ticket_id, id);

-- Сообщения, которые бот отправил админам по обращению (чтобы снимать кнопки
-- при закрытии и понимать, на какое обращение админ отвечает через reply).
CREATE TABLE IF NOT EXISTS notifications (
    chat_id      INTEGER NOT NULL,
    message_id   INTEGER NOT NULL,
    ticket_id    INTEGER NOT NULL REFERENCES tickets(id),
    has_buttons  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_notifications_ticket ON notifications(ticket_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        self.created = False  # True, если база создана при этом запуске

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.created = not self.path.exists()
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def _all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        async with self.conn.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def _one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    # ---------- admins ----------

    async def list_admins(self) -> list[dict]:
        return await self._all("SELECT * FROM admins ORDER BY added_at")

    async def admin_ids(self) -> set[int]:
        return {r["user_id"] for r in await self._all("SELECT user_id FROM admins")}

    async def add_admin(self, user_id: int, name: str | None, added_by: int | None) -> bool:
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO admins (user_id, name, added_by, added_at) VALUES (?, ?, ?, ?)",
            (user_id, name, added_by, now_iso()),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def remove_admin(self, user_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    # ---------- tickets ----------

    async def get_open_ticket(self, user_id: int) -> dict | None:
        return await self._one(
            "SELECT * FROM tickets WHERE user_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            (user_id,),
        )

    async def get_ticket(self, ticket_id: int) -> dict | None:
        return await self._one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))

    async def create_ticket(self, user_id: int, user_name: str | None, username: str | None) -> dict:
        ts = now_iso()
        cur = await self.conn.execute(
            "INSERT INTO tickets (user_id, user_name, username, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'open', ?, ?)",
            (user_id, user_name, username, ts, ts),
        )
        await self.conn.commit()
        return await self.get_ticket(cur.lastrowid)

    async def update_ticket_user(self, ticket_id: int, user_name: str | None, username: str | None) -> None:
        await self.conn.execute(
            "UPDATE tickets SET user_name = ?, username = ? WHERE id = ?", (user_name, username, ticket_id)
        )
        await self.conn.commit()

    async def set_status(self, ticket_id: int, status: str, by: int | None) -> bool:
        """Меняет статус. Возвращает False, если статус уже такой."""
        ts = now_iso()
        if status == "closed":
            sql = ("UPDATE tickets SET status = 'closed', closed_at = ?, closed_by = ?, updated_at = ? "
                   "WHERE id = ? AND status != 'closed'")
            params = (ts, by, ts, ticket_id)
        else:
            sql = ("UPDATE tickets SET status = 'open', closed_at = NULL, closed_by = NULL, updated_at = ? "
                   "WHERE id = ? AND status != 'open'")
            params = (ts, ticket_id)
        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cur.rowcount > 0

    async def list_tickets(self, status: str | None, limit: int = 100, query: str | None = None) -> list[dict]:
        where, params = [], []
        if status:
            where.append("t.status = ?")
            params.append(status)
        if query:
            q = query.strip().lstrip("#@")
            cond = ["t.user_name LIKE ?", "t.username LIKE ?",
                    "EXISTS (SELECT 1 FROM messages m WHERE m.ticket_id = t.id AND m.text LIKE ?)"]
            params += [f"%{q}%"] * 3
            if q.isdigit():
                cond += ["t.id = ?", "t.user_id = ?"]
                params += [int(q), int(q)]
            where.append("(" + " OR ".join(cond) + ")")
        sql = f"""
            SELECT t.*,
                   lm.sender AS last_sender,
                   COALESCE(lm.text, CASE WHEN lm.media_type IS NOT NULL THEN '[' || lm.media_type || ']' END) AS last_text,
                   (SELECT COUNT(*) FROM messages m WHERE m.ticket_id = t.id) AS message_count
            FROM tickets t
            LEFT JOIN messages lm ON lm.id = (SELECT MAX(id) FROM messages WHERE ticket_id = t.id)
            {"WHERE " + " AND ".join(where) if where else ""}
            ORDER BY t.updated_at DESC
            LIMIT ?
        """
        params.append(limit)
        return await self._all(sql, tuple(params))

    async def stats(self) -> dict:
        row = await self._one(
            """SELECT
                 SUM(status = 'open') AS open,
                 SUM(status = 'closed') AS closed,
                 SUM(status = 'open' AND (SELECT sender FROM messages m WHERE m.ticket_id = tickets.id
                                          ORDER BY m.id DESC LIMIT 1) = 'user') AS waiting
               FROM tickets"""
        )
        return {k: row[k] or 0 for k in ("open", "closed", "waiting")}

    # ---------- messages ----------

    async def add_message(self, ticket_id: int, sender: str, text: str | None,
                          media_type: str | None = None, file_id: str | None = None,
                          admin_id: int | None = None, created_at: str | None = None) -> int:
        ts = created_at or now_iso()
        cur = await self.conn.execute(
            "INSERT INTO messages (ticket_id, sender, admin_id, text, media_type, file_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, sender, admin_id, text, media_type, file_id, ts),
        )
        await self.conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (ts, ticket_id))
        await self.conn.commit()
        return cur.lastrowid

    async def get_messages(self, ticket_id: int) -> list[dict]:
        return await self._all(
            "SELECT m.*, a.name AS admin_name FROM messages m "
            "LEFT JOIN admins a ON a.user_id = m.admin_id "
            "WHERE m.ticket_id = ? ORDER BY m.id",
            (ticket_id,),
        )

    async def get_message(self, message_id: int) -> dict | None:
        return await self._one("SELECT * FROM messages WHERE id = ?", (message_id,))

    # ---------- notifications ----------

    async def add_notification(self, chat_id: int, message_id: int, ticket_id: int, has_buttons: bool) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO notifications (chat_id, message_id, ticket_id, has_buttons) VALUES (?, ?, ?, ?)",
            (chat_id, message_id, ticket_id, int(has_buttons)),
        )
        await self.conn.commit()

    async def ticket_by_notification(self, chat_id: int, message_id: int) -> int | None:
        row = await self._one(
            "SELECT ticket_id FROM notifications WHERE chat_id = ? AND message_id = ?", (chat_id, message_id)
        )
        return row["ticket_id"] if row else None

    async def pop_buttons(self, ticket_id: int) -> list[dict]:
        """Возвращает уведомления с кнопками и помечает их как уже без кнопок."""
        rows = await self._all(
            "SELECT chat_id, message_id FROM notifications WHERE ticket_id = ? AND has_buttons = 1", (ticket_id,)
        )
        await self.conn.execute("UPDATE notifications SET has_buttons = 0 WHERE ticket_id = ?", (ticket_id,))
        await self.conn.commit()
        return rows

    # ---------- migration ----------

    async def import_legacy_json(self, path: Path) -> int:
        """Переносит обращения из старого tickets.json (формат первой версии бота)."""
        if not path.exists():
            return 0
        async with self.conn.execute("SELECT COUNT(*) FROM tickets") as cur:
            if (await cur.fetchone())[0]:
                log.warning("%s найден, но база уже не пустая — импорт пропущен", path)
                return 0
        data = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        for user_id, t in data.items():
            created = t.get("time") or now_iso()
            ticket = await self.create_ticket(int(user_id), None, None)
            await self.conn.execute("UPDATE tickets SET created_at = ? WHERE id = ?", (created, ticket["id"]))
            await self.add_message(ticket["id"], "user", t.get("message"), created_at=created)
            for a in t.get("answers", []):
                await self.add_message(ticket["id"], "admin", a.get("text"), admin_id=a.get("admin_id"),
                                       created_at=a.get("time"))
            if t.get("status") == "closed":
                await self.set_status(ticket["id"], "closed", None)
            count += 1
        path.rename(path.with_suffix(".json.imported"))
        log.info("Импортировано %d обращений из %s", count, path)
        return count
