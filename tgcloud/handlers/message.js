// Все входящие сообщения: пользователи создают обращения, админы отвечают и управляют ботом.
import { api } from 'sdk';
import * as S from '../lib/support.js';

const { store } = S;
const REQUEST_ADMIN_ID = 1;

const send = (chatId, text, extra = {}) => S.safe(api.sendMessage({ chat_id: chatId, text, ...extra }));

function parseCommand(message) {
  const text = message.text || '';
  if (!text.startsWith('/')) return null;
  const [raw, ...rest] = text.trim().split(/\s+/);
  return { cmd: raw.slice(1).split('@')[0].toLowerCase(), args: rest.join(' ').trim() };
}

export default async function (message) {
  if (!message.from || message.from.is_bot || message.chat.type !== 'private') return;
  const uid = message.from.id;
  if (await S.isAdmin(uid)) return handleAdmin(message, uid);
  return handleUser(message, uid);
}

// ---------- пользователь ----------

async function handleUser(message, uid) {
  const command = parseCommand(message);
  if (command) {
    if (command.cmd === 'start') {
      await send(uid, `👋 Поддержка ${S.SUPPORT_NAME}\n\n`
        + 'Опишите вашу проблему — можно приложить скриншот или файл.\n'
        + 'Все обращения обрабатываются в порядке очереди, ответ придёт сюда.');
    } else {
      await send(uid, 'Просто опишите вашу проблему обычным сообщением 🙂');
    }
    return;
  }

  const limit = await S.checkRateLimit(uid);
  if (!limit.allowed) {
    if (limit.warn) await send(uid, '⏳ Слишком много сообщений подряд. Подождите немного и напишите снова.');
    return;
  }

  const result = await S.handleUserMessage(message);
  if (!result) {
    await send(uid, '⚠️ Этот тип сообщений не поддерживается. Отправьте текст, фото, видео или файл.');
    return;
  }
  if (result.isNew) {
    await send(uid, `✅ Ваше обращение #${result.ticket.id} отправлено в поддержку.\n`
      + 'Если хотите что-то добавить — просто напишите ещё.');
  }
}

// ---------- админ ----------

const HELP = '🛠 Вы администратор поддержки.\n\n'
  + 'Как ответить пользователю:\n'
  + '• нажмите «✍️ Ответить» под обращением и отправьте сообщение, или\n'
  + '• ответьте (reply) прямо на уведомление об обращении.\n'
  + 'Можно отправлять текст, фото, видео и файлы.\n\n'
  + '/tickets — открытые обращения\n'
  + '/cancel — отменить ответ\n';

async function handleAdmin(message, uid) {
  const command = parseCommand(message);
  const superadmin = S.isSuperadmin(uid);

  if (command) {
    switch (command.cmd) {
      case 'start':
      case 'help': {
        let text = HELP;
        if (S.WEBAPP_URL) text += '/panel — открыть панель (мини-приложение)\n';
        if (superadmin) {
          text += '\n👑 Суперадмин:\n/admins — список админов\n/addadmin — добавить админа\n/deladmin ID — удалить админа\n';
        }
        await S.setupAdminUi(uid);
        return send(uid, text, { reply_markup: S.panelKeyboard() });
      }
      case 'panel':
        return S.WEBAPP_URL
          ? send(uid, 'Панель поддержки:', { reply_markup: S.panelKeyboard() })
          : send(uid, 'Мини-приложение не настроено: укажите WEBAPP_URL в tgcloud/lib/config.js');
      case 'cancel': {
        const s = await store.getSession(`reply:${uid}`);
        if (!s) return send(uid, '⛔ Нет активного ответа для отмены.');
        await store.clearSession(`reply:${uid}`);
        return send(uid, `⛔ Ответ на обращение #${s.ticket_id} отменён.`, { reply_markup: { remove_keyboard: true } });
      }
      case 'tickets':
        return listOpenTickets(uid);
    }
    if (superadmin) {
      switch (command.cmd) {
        case 'admins':
          return send(uid, ...(await S.adminsView()));
        case 'addadmin':
          return addAdminCommand(uid, command.args);
        case 'deladmin':
          return delAdminCommand(uid, command.args);
      }
    }
    return send(uid, 'Неизвестная команда. Справка: /help');
  }

  // Суперадмин выбрал пользователя кнопкой «Выбрать пользователя».
  if (superadmin && message.users_shared && message.users_shared.request_id === REQUEST_ADMIN_ID) {
    const u = message.users_shared.users[0];
    return addAdminAndReport(uid, u.user_id, S.displayName(u));
  }
  if (superadmin && message.text === 'Отмена') {
    return send(uid, 'Ок, отменено.', { reply_markup: { remove_keyboard: true } });
  }

  // Режим ответа после кнопки «Ответить».
  const session = await store.getSession(`reply:${uid}`);
  if (session) {
    await store.clearSession(`reply:${uid}`);
    return sendReply(message, uid, Number(session.ticket_id));
  }

  // Ответ через reply на уведомление.
  if (message.reply_to_message) {
    const ticketId = await store.ticketByNotification(uid, message.reply_to_message.message_id);
    if (!ticketId) {
      return send(uid, '🤔 Не понял, к какому обращению это относится. Ответьте на уведомление об обращении.');
    }
    return sendReply(message, uid, ticketId);
  }

  return send(uid, 'ℹ️ Чтобы ответить пользователю, нажмите «✍️ Ответить» под обращением '
    + 'или ответьте (reply) на уведомление. Список: /tickets', { reply_markup: S.panelKeyboard() });
}

async function sendReply(message, uid, ticketId) {
  let ticket;
  try {
    ticket = await S.reply(ticketId, uid, { source: message });
  } catch (e) {
    if (e instanceof S.UserError) return send(uid, `❌ ${e.message}. Ответ не отправлен.`);
    throw e;
  }
  const confirm = await send(uid, `✅ Ответ на обращение #${ticket.id} отправлен.`, {
    reply_markup: { inline_keyboard: [[{ text: '✅ Закрыть обращение', callback_data: `close:${ticket.id}` }]] },
  });
  if (confirm) await store.addNotification(uid, confirm.message_id, ticket.id, true);
}

async function listOpenTickets(uid) {
  const tickets = await store.listTickets('open', 30);
  if (!tickets.length) return send(uid, '🎉 Открытых обращений нет.', { reply_markup: S.panelKeyboard() });
  const lines = [`📂 Открытые обращения (${tickets.length}):`, ''];
  const buttons = [];
  for (const t of tickets) {
    const mark = t.last_sender === 'user' ? '🔴' : '🟢';
    let preview = String(t.last_text || '').replace(/\n/g, ' ');
    if (preview.length > 50) preview = preview.slice(0, 50) + '…';
    lines.push(`${mark} #${t.id} ${t.user_name || t.user_id}: ${preview}`);
    buttons.push({ text: `#${t.id}`, callback_data: `view:${t.id}` });
  }
  lines.push('', '🔴 — ждёт ответа, 🟢 — отвечено');
  const rows = [];
  for (let i = 0; i < buttons.length; i += 5) rows.push(buttons.slice(i, i + 5));
  return send(uid, lines.join('\n'), { reply_markup: { inline_keyboard: rows } });
}

// ---------- управление админами ----------

async function addAdminAndReport(uid, userId, name) {
  try {
    const added = await S.addAdmin(userId, name, uid);
    return send(uid, added
      ? `✅ ${name || userId} добавлен в админы.\n`
        + 'Если он ещё не запускал бота — пусть нажмёт /start, иначе бот не сможет присылать ему обращения.'
      : 'ℹ️ Этот пользователь уже админ.', { reply_markup: { remove_keyboard: true } });
  } catch (e) {
    if (e instanceof S.UserError) return send(uid, `ℹ️ ${e.message}`, { reply_markup: { remove_keyboard: true } });
    throw e;
  }
}

async function addAdminCommand(uid, args) {
  if (args) {
    if (!/^\d+$/.test(args)) return send(uid, 'Укажите числовой Telegram ID: /addadmin 123456789');
    return addAdminAndReport(uid, Number(args), null);
  }
  return send(uid, 'Выберите пользователя из контактов кнопкой ниже\nили отправьте команду с ID: /addadmin 123456789', {
    reply_markup: {
      keyboard: [
        [{
          text: '👤 Выбрать пользователя',
          request_users: {
            request_id: REQUEST_ADMIN_ID, user_is_bot: false, max_quantity: 1,
            request_name: true, request_username: true,
          },
        }],
        [{ text: 'Отмена' }],
      ],
      resize_keyboard: true,
      one_time_keyboard: true,
    },
  });
}

async function delAdminCommand(uid, args) {
  if (!/^\d+$/.test(args)) {
    const [text, extra] = await S.adminsView();
    return send(uid, 'Укажите ID: /deladmin 123456789 — или нажмите кнопку ниже.\n\n' + text, extra);
  }
  return send(uid, (await S.removeAdmin(Number(args)))
    ? `✅ Админ ${args} удалён.`
    : 'ℹ️ Такого админа нет (суперадминов можно убрать только в lib/config.js).');
}
