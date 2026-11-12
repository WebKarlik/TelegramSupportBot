// Доступ к базе данных. Используем сырой SQL через тег sql`` — значения
// подставляются как параметры, так что SQL-инъекции невозможны.
import { db } from 'sdk';
import { sql } from 'sdk/db';

export const nowIso = () => new Date().toISOString();

const one = async (q) => (await db.get(q)) || null;

// ---------- admins ----------

export const listAdmins = () => db.all(sql`
  SELECT user_id, name, added_by, added_at FROM admins ORDER BY added_at`);

export async function isDbAdmin(userId) {
  return !!(await one(sql`SELECT 1 AS x FROM admins WHERE user_id = ${userId}`));
}

export async function adminIds() {
  return (await db.all(sql`SELECT user_id FROM admins`)).map((r) => Number(r.user_id));
}

export async function addAdmin(userId, name, addedBy) {
  const r = await db.run(sql`
    INSERT INTO admins (user_id, name, added_by, added_at) VALUES (${userId}, ${name}, ${addedBy}, ${nowIso()})
    ON CONFLICT (user_id) DO NOTHING`);
  return r.rowsAffected > 0;
}

export async function removeAdmin(userId) {
  const r = await db.run(sql`DELETE FROM admins WHERE user_id = ${userId}`);
  return r.rowsAffected > 0;
}

// ---------- tickets ----------

export const getTicket = (id) => one(sql`SELECT * FROM tickets WHERE id = ${id}`);

export const getOpenTicket = (userId) => one(sql`
  SELECT * FROM tickets WHERE user_id = ${userId} AND status = 'open' ORDER BY id DESC LIMIT 1`);

export async function createTicket(userId, userName, username) {
  const ts = nowIso();
  const r = await db.run(sql`
    INSERT INTO tickets (user_id, user_name, username, status, created_at, updated_at)
    VALUES (${userId}, ${userName}, ${username}, 'open', ${ts}, ${ts}) RETURNING *`);
  return r.rows[0];
}

export async function updateTicketUser(id, userName, username) {
  await db.run(sql`UPDATE tickets SET user_name = ${userName}, username = ${username} WHERE id = ${id}`);
}

// Меняет статус. Возвращает false, если статус уже такой.
export async function setStatus(id, status, by) {
  const ts = nowIso();
  const r = status === 'closed'
    ? await db.run(sql`
        UPDATE tickets SET status = 'closed', closed_at = ${ts}, closed_by = ${by}, updated_at = ${ts}
        WHERE id = ${id} AND status != 'closed'`)
    : await db.run(sql`
        UPDATE tickets SET status = 'open', closed_at = NULL, closed_by = NULL, updated_at = ${ts}
        WHERE id = ${id} AND status != 'open'`);
  return r.rowsAffected > 0;
}

export async function listTickets(status, limit = 100, query = '') {
  const conds = [];
  if (status) conds.push(sql`t.status = ${status}`);
  const q = String(query || '').trim().replace(/^[#@]+/, '');
  if (q) {
    const like = `%${q}%`;
    let c = sql`t.user_name LIKE ${like} OR t.username LIKE ${like}
      OR EXISTS (SELECT 1 FROM messages m WHERE m.ticket_id = t.id AND m.text LIKE ${like})`;
    if (/^\d+$/.test(q)) c = sql`${c} OR t.id = ${Number(q)} OR t.user_id = ${Number(q)}`;
    conds.push(sql`(${c})`);
  }
  const where = conds.length
    ? sql`WHERE ${conds.reduce((acc, c) => sql`${acc} AND ${c}`)}`
    : sql``;
  return db.all(sql`
    SELECT t.*,
           lm.sender AS last_sender,
           COALESCE(lm.text, CASE WHEN lm.media_type IS NOT NULL THEN '[' || lm.media_type || ']' END) AS last_text,
           (SELECT COUNT(*) FROM messages mc WHERE mc.ticket_id = t.id) AS message_count
    FROM tickets t
    LEFT JOIN messages lm ON lm.id = (SELECT MAX(id) FROM messages WHERE ticket_id = t.id)
    ${where}
    ORDER BY t.updated_at DESC
    LIMIT ${limit}`);
}

export async function stats() {
  const r = await one(sql`
    SELECT
      SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open,
      SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS closed,
      SUM(CASE WHEN status = 'open' AND (SELECT sender FROM messages m WHERE m.ticket_id = tickets.id
                                        ORDER BY m.id DESC LIMIT 1) = 'user' THEN 1 ELSE 0 END) AS waiting
    FROM tickets`);
  return { open: Number(r?.open || 0), closed: Number(r?.closed || 0), waiting: Number(r?.waiting || 0) };
}

// ---------- messages ----------

export async function addMessage(ticketId, sender, { text = null, mediaType = null, fileId = null, adminId = null } = {}) {
  const ts = nowIso();
  const r = await db.run(sql`
    INSERT INTO messages (ticket_id, sender, admin_id, text, media_type, file_id, created_at)
    VALUES (${ticketId}, ${sender}, ${adminId}, ${text}, ${mediaType}, ${fileId}, ${ts}) RETURNING id`);
  await db.run(sql`UPDATE tickets SET updated_at = ${ts} WHERE id = ${ticketId}`);
  return Number(r.rows[0].id);
}

export const getMessages = (ticketId) => db.all(sql`
  SELECT m.id, m.ticket_id, m.sender, m.admin_id, m.text, m.media_type, m.created_at,
         CASE WHEN m.file_id IS NULL THEN 0 ELSE 1 END AS has_file, a.name AS admin_name
  FROM messages m LEFT JOIN admins a ON a.user_id = m.admin_id
  WHERE m.ticket_id = ${ticketId} ORDER BY m.id`);

export const getMessage = (id) => one(sql`SELECT * FROM messages WHERE id = ${id}`);

export async function countRecentUserMessages(userId, sinceIso) {
  const r = await one(sql`
    SELECT COUNT(*) AS n FROM messages m JOIN tickets t ON t.id = m.ticket_id
    WHERE t.user_id = ${userId} AND m.sender = 'user' AND m.created_at > ${sinceIso}`);
  return Number(r?.n || 0);
}

// ---------- notifications ----------

export async function addNotification(chatId, messageId, ticketId, hasButtons) {
  await db.run(sql`
    INSERT INTO notifications (chat_id, message_id, ticket_id, has_buttons)
    VALUES (${chatId}, ${messageId}, ${ticketId}, ${hasButtons ? 1 : 0})
    ON CONFLICT (chat_id, message_id) DO UPDATE SET ticket_id = excluded.ticket_id, has_buttons = excluded.has_buttons`);
}

export async function ticketByNotification(chatId, messageId) {
  const r = await one(sql`
    SELECT ticket_id FROM notifications WHERE chat_id = ${chatId} AND message_id = ${messageId}`);
  return r ? Number(r.ticket_id) : null;
}

// Возвращает уведомления с кнопками и помечает их как уже без кнопок.
export async function popButtons(ticketId) {
  const r = await db.run(sql`
    UPDATE notifications SET has_buttons = 0 WHERE ticket_id = ${ticketId} AND has_buttons = 1
    RETURNING chat_id, message_id`);
  return r.rows;
}

// ---------- sessions ----------

export async function getSession(key) {
  return one(sql`SELECT * FROM sessions WHERE key = ${key}`);
}

export async function setSession(key, ticketId = null) {
  await db.run(sql`
    INSERT INTO sessions (key, ticket_id, updated_at) VALUES (${key}, ${ticketId}, ${nowIso()})
    ON CONFLICT (key) DO UPDATE SET ticket_id = excluded.ticket_id, updated_at = excluded.updated_at`);
}

export async function clearSession(key) {
  const r = await db.run(sql`DELETE FROM sessions WHERE key = ${key}`);
  return r.rowsAffected > 0;
}
