// Бизнес-логика поддержки, общая для обработчиков бота и endpoints мини-приложения.
import { api, BotApiError } from 'sdk';
import * as store from './store.js';
import { SUPERADMIN_IDS, SUPPORT_NAME, WEBAPP_URL, RATE_LIMIT_MESSAGES, RATE_LIMIT_WINDOW } from './config.js';

// Ошибка, текст которой можно показать админу.
export class UserError extends Error {}
export class NotFoundError extends UserError {}

// Порядок важен: у анимации заполнено и поле document.
export const MEDIA_TYPES = ['photo', 'animation', 'video', 'video_note', 'voice', 'audio', 'sticker', 'document'];
export const MEDIA_LABELS = {
  photo: 'фото', animation: 'GIF', video: 'видео', video_note: 'видеосообщение',
  voice: 'голосовое', audio: 'аудио', sticker: 'стикер', document: 'файл',
};

export { SUPPORT_NAME, WEBAPP_URL };

// Вызов Bot API, ошибки которого не должны ронять обработку (например, админ заблокировал бота).
export async function safe(promise) {
  try {
    return await promise;
  } catch (e) {
    if (e instanceof BotApiError) {
      console.warn(`Bot API ${e.method}: ${e.description}`);
      return null;
    }
    throw e;
  }
}

// ---------- роли ----------

export const isSuperadmin = (userId) => SUPERADMIN_IDS.includes(Number(userId));

export async function isAdmin(userId) {
  return isSuperadmin(userId) || store.isDbAdmin(Number(userId));
}

export async function allAdminIds() {
  return [...new Set([...SUPERADMIN_IDS.map(Number), ...(await store.adminIds())])].sort((a, b) => a - b);
}

export async function addAdmin(userId, name, addedBy) {
  userId = Number(userId);
  if (!Number.isSafeInteger(userId) || userId <= 0) throw new UserError('Некорректный Telegram ID');
  if (isSuperadmin(userId)) throw new UserError('Это суперадмин — у него уже есть доступ');
  if (!name) {
    const chat = await safe(api.getChat({ chat_id: userId }));
    if (chat) name = [chat.first_name, chat.last_name].filter(Boolean).join(' ') || null;
  }
  const added = await store.addAdmin(userId, name || null, addedBy);
  if (added) {
    await setupAdminUi(userId);
    await safe(api.sendMessage({
      chat_id: userId,
      text: `🎉 Вас назначили администратором поддержки ${SUPPORT_NAME}.\n`
        + 'Новые обращения будут приходить сюда. Справка: /help',
      reply_markup: panelKeyboard(),
    }));
  }
  return added;
}

// Текст и клавиатура списка админов (для /admins и после удаления).
export async function adminsView() {
  const admins = await store.listAdmins();
  const lines = ['👑 Суперадмины (из настроек SUPERADMIN_IDS):', ...SUPERADMIN_IDS.map((id) => `• ${id}`), '', '🛠 Админы:'];
  const rows = [];
  if (!admins.length) lines.push('— пока никого. Добавить: /addadmin');
  for (const a of admins) {
    const name = a.name || 'Без имени';
    lines.push(`• ${name} — ${a.user_id}`);
    rows.push([{ text: `❌ Удалить ${name}`, callback_data: `deladmin:${a.user_id}` }]);
  }
  return [lines.join('\n'), rows.length ? { reply_markup: { inline_keyboard: rows } } : {}];
}

export async function removeAdmin(userId) {
  userId = Number(userId);
  const removed = await store.removeAdmin(userId);
  if (removed && !isSuperadmin(userId)) {
    await store.clearSession(`reply:${userId}`);
    await safe(api.deleteMyCommands({ scope: { type: 'chat', chat_id: userId } }));
    await safe(api.setChatMenuButton({ chat_id: userId, menu_button: { type: 'default' } }));
  }
  return removed;
}

// ---------- клавиатуры и меню ----------

export function webappButton(text = '🗂 Открыть панель', ticketId = null) {
  if (!WEBAPP_URL) return null;
  const url = ticketId ? `${WEBAPP_URL}#ticket=${ticketId}` : WEBAPP_URL;
  return { text, web_app: { url } };
}

export function panelKeyboard() {
  const b = webappButton();
  return b ? { inline_keyboard: [[b]] } : undefined;
}

export function ticketKeyboard(ticketId) {
  const rows = [[
    { text: '✍️ Ответить', callback_data: `reply:${ticketId}` },
    { text: '✅ Закрыть', callback_data: `close:${ticketId}` },
  ]];
  const b = webappButton('🗂 Открыть в панели', ticketId);
  if (b) rows.push([b]);
  return { inline_keyboard: rows };
}

export async function setupAdminUi(userId) {
  const commands = [
    { command: 'tickets', description: 'Открытые обращения' },
    { command: 'cancel', description: 'Отменить ответ' },
    { command: 'help', description: 'Справка' },
  ];
  if (WEBAPP_URL) commands.unshift({ command: 'panel', description: 'Открыть панель' });
  if (isSuperadmin(userId)) {
    commands.push(
      { command: 'admins', description: 'Список админов' },
      { command: 'addadmin', description: 'Добавить админа' },
    );
  }
  await safe(api.setMyCommands({ commands, scope: { type: 'chat', chat_id: userId } }));
  if (WEBAPP_URL) {
    await safe(api.setChatMenuButton({
      chat_id: userId,
      menu_button: { type: 'web_app', text: 'Панель', web_app: { url: WEBAPP_URL } },
    }));
  }
}

// ---------- обращения ----------

export function extractContent(message) {
  const text = message.text ?? message.caption ?? null;
  for (const type of MEDIA_TYPES) {
    const obj = message[type];
    if (obj) {
      const fileId = type === 'photo' ? obj[obj.length - 1].file_id : obj.file_id;
      return { text, mediaType: type, fileId };
    }
  }
  if (text) return { text, mediaType: null, fileId: null };
  return null;
}

export const displayName = (u) => [u.first_name, u.last_name].filter(Boolean).join(' ') || 'Без имени';

export function ticketTitle(t) {
  let who = t.user_name || 'Без имени';
  if (t.username) who += ` (@${t.username})`;
  return `${who} · ID ${t.user_id}`;
}

const cut = (s, n = 4000) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

// Антиспам: { allowed, warn }.
export async function checkRateLimit(userId) {
  const since = new Date(Date.now() - RATE_LIMIT_WINDOW * 1000).toISOString();
  if (await store.countRecentUserMessages(userId, since) < RATE_LIMIT_MESSAGES) return { allowed: true, warn: false };
  const key = `ratelimit:${userId}`;
  const s = await store.getSession(key);
  const warn = !s || s.updated_at < since;
  if (warn) await store.setSession(key);
  return { allowed: false, warn };
}

// Сохраняет сообщение пользователя и рассылает его админам. Возвращает { ticket, isNew } или null.
export async function handleUserMessage(message) {
  const content = extractContent(message);
  if (!content) return null;
  const user = message.from;
  const name = displayName(user);
  const username = user.username || null;

  let ticket = await store.getOpenTicket(user.id);
  const isNew = !ticket;
  if (isNew) {
    ticket = await store.createTicket(user.id, name, username);
  } else if (ticket.user_name !== name || ticket.username !== username) {
    await store.updateTicketUser(ticket.id, name, username);
    ticket = { ...ticket, user_name: name, username };
  }
  await store.addMessage(ticket.id, 'user', content);

  const lines = [
    isNew ? `📩 Новое обращение #${ticket.id}` : `📨 Обращение #${ticket.id} — новое сообщение`,
    '',
    `👤 ${ticketTitle(ticket)}`,
  ];
  if (content.mediaType) lines.push(`📎 Вложение: ${MEDIA_LABELS[content.mediaType]}`);
  if (content.text) lines.push('', `💬 ${content.text}`);
  const text = cut(lines.join('\n'));

  for (const adminId of await allAdminIds()) {
    const sent = await safe(api.sendMessage({ chat_id: adminId, text, reply_markup: ticketKeyboard(ticket.id) }));
    if (!sent) continue;
    await store.addNotification(adminId, sent.message_id, ticket.id, true);
    if (content.mediaType) {
      const copy = await safe(api.copyMessage({
        chat_id: adminId, from_chat_id: message.chat.id, message_id: message.message_id,
        reply_parameters: { message_id: sent.message_id },
      }));
      if (copy) await store.addNotification(adminId, copy.message_id, ticket.id, false);
    }
  }
  return { ticket, isNew };
}

// Ответ пользователю: либо text (из мини-приложения), либо source — сообщение админа любого типа.
export async function reply(ticketId, adminId, { text = null, source = null } = {}) {
  const ticket = await store.getTicket(ticketId);
  if (!ticket) throw new NotFoundError('Обращение не найдено');
  if (ticket.status === 'closed') throw new UserError('Обращение уже закрыто');

  let content = { text, mediaType: null, fileId: null };
  if (source) {
    content = extractContent(source);
    if (!content) throw new UserError('Этот тип сообщения нельзя отправить пользователю');
  }
  if (!content.mediaType && !String(content.text || '').trim()) throw new UserError('Пустой ответ');
  if (!content.mediaType && content.text.length > 4000) throw new UserError('Слишком длинный ответ (максимум 4000 символов)');

  const prefix = `💬 Ответ поддержки ${SUPPORT_NAME}:`;
  try {
    if (content.mediaType) {
      await api.sendMessage({ chat_id: ticket.user_id, text: prefix });
      await api.copyMessage({ chat_id: ticket.user_id, from_chat_id: source.chat.id, message_id: source.message_id });
    } else {
      await api.sendMessage({ chat_id: ticket.user_id, text: `${prefix}\n\n${content.text}` });
    }
  } catch (e) {
    if (e instanceof BotApiError) throw new UserError(`Не удалось отправить сообщение пользователю: ${e.description}`);
    throw e;
  }
  await store.addMessage(ticketId, 'admin', { ...content, adminId });
  return ticket;
}

export async function close(ticketId, adminId) {
  const ticket = await store.getTicket(ticketId);
  if (!ticket) throw new NotFoundError('Обращение не найдено');
  if (!(await store.setStatus(ticketId, 'closed', adminId))) return false;
  for (const n of await store.popButtons(ticketId)) {
    await safe(api.editMessageReplyMarkup({ chat_id: n.chat_id, message_id: n.message_id }));
  }
  await safe(api.sendMessage({
    chat_id: ticket.user_id,
    text: `✅ Ваше обращение #${ticketId} закрыто.\n`
      + 'Если вопрос остался — просто напишите сюда, и мы откроем новое обращение.',
  }));
  return true;
}

export async function reopen(ticketId, adminId) {
  const ticket = await store.getTicket(ticketId);
  if (!ticket) throw new NotFoundError('Обращение не найдено');
  if (ticket.status === 'open') return false;
  const other = await store.getOpenTicket(ticket.user_id);
  if (other) throw new UserError(`У пользователя уже есть открытое обращение #${other.id}`);
  return store.setStatus(ticketId, 'open', adminId);
}

export { store };
