// Нажатия на inline-кнопки под обращениями и в списке админов.
import { api } from 'sdk';
import * as S from '../lib/support.js';

const { store } = S;

const answer = (query, text = undefined, alert = false) =>
  S.safe(api.answerCallbackQuery({ callback_query_id: query.id, text, show_alert: alert }));

export default async function (query) {
  const uid = query.from.id;
  const data = query.data || '';
  const [action, rawId] = data.split(':');
  const id = Number(rawId);
  const chatId = query.message ? query.message.chat.id : uid;
  const messageId = query.message ? query.message.message_id : null;

  if (!(await S.isAdmin(uid))) return answer(query, '❌ Только для админов', true);
  if (!Number.isSafeInteger(id)) return answer(query);

  try {
    switch (action) {
      case 'reply': {
        const ticket = await store.getTicket(id);
        if (!ticket || ticket.status === 'closed') return answer(query, '❌ Обращение закрыто или не найдено', true);
        await store.setSession(`reply:${uid}`, id);
        await S.safe(api.sendMessage({
          chat_id: chatId,
          text: `✍️ Напишите ответ на обращение #${id} (${S.ticketTitle(ticket)}).\n`
            + 'Можно приложить фото или файл. /cancel — отменить.',
        }));
        return answer(query);
      }

      case 'close': {
        const closed = await S.close(id, uid);
        if (!closed) {
          if (messageId) await S.safe(api.editMessageReplyMarkup({ chat_id: chatId, message_id: messageId }));
          return answer(query, 'ℹ️ Обращение уже закрыто', true);
        }
        return answer(query, `✅ Обращение #${id} закрыто`);
      }

      case 'reopen': {
        if (!(await S.reopen(id, uid))) return answer(query, 'ℹ️ Обращение уже открыто', true);
        if (messageId) {
          await S.safe(api.editMessageReplyMarkup({
            chat_id: chatId, message_id: messageId, reply_markup: S.ticketKeyboard(id),
          }));
          await store.addNotification(chatId, messageId, id, true);
        }
        return answer(query, `♻️ Обращение #${id} снова открыто`);
      }

      case 'view':
        await viewTicket(chatId, id);
        return answer(query);

      case 'deladmin': {
        if (!S.isSuperadmin(uid)) return answer(query, '❌ Только для суперадмина', true);
        const removed = await S.removeAdmin(id);
        const [text, extra] = await S.adminsView();
        if (messageId) {
          await S.safe(api.editMessageText({
            chat_id: chatId, message_id: messageId, text,
            reply_markup: extra.reply_markup || { inline_keyboard: [] },
          }));
        }
        return answer(query, removed ? '✅ Удалён' : 'ℹ️ Уже удалён');
      }
    }
  } catch (e) {
    if (e instanceof S.UserError) return answer(query, `❌ ${e.message}`, true);
    throw e;
  }
  return answer(query);
}

async function viewTicket(chatId, id) {
  const ticket = await store.getTicket(id);
  if (!ticket) {
    await S.safe(api.sendMessage({ chat_id: chatId, text: '❌ Обращение не найдено' }));
    return;
  }
  const messages = await store.getMessages(id);
  const status = ticket.status === 'open' ? 'открыто' : 'закрыто';
  const lines = [`📄 Обращение #${id} (${status})`, `👤 ${S.ticketTitle(ticket)}`, ''];
  if (messages.length > 15) lines.push(`… ещё ${messages.length - 15} сообщений выше`, '');
  for (const m of messages.slice(-15)) {
    let body = m.text || '';
    if (m.media_type) body = `[${S.MEDIA_LABELS[m.media_type] || m.media_type}] ${body}`.trim();
    lines.push(`${m.sender === 'user' ? '👤' : '🛠'} ${body}`);
  }
  let text = lines.join('\n');
  if (text.length > 4000) text = text.slice(0, 3999) + '…';
  const open = ticket.status === 'open';
  const sent = await S.safe(api.sendMessage({
    chat_id: chatId, text,
    reply_markup: open
      ? S.ticketKeyboard(id)
      : { inline_keyboard: [[{ text: '♻️ Открыть заново', callback_data: `reopen:${id}` }]] },
  }));
  if (sent) await store.addNotification(chatId, sent.message_id, id, open);
}
