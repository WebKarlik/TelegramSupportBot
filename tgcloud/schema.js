// Таблицы базы данных бота поддержки (Telegram Serverless, SQLite).
// Применить изменения схемы: npx tgcloud push && npx tgcloud migrate
import { table, integer, text, index, uniqueIndex } from 'sdk/db';

// Админы, которых добавил суперадмин. Суперадмины задаются в lib/config.js.
export const admins = table('admins', {
  userId: integer('user_id').primaryKey(),
  name: text('name'),
  addedBy: integer('added_by'),
  addedAt: text('added_at').notNull(),
});

export const tickets = table('tickets', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  userId: integer('user_id').notNull(),
  userName: text('user_name'),
  username: text('username'),
  status: text('status').notNull().default('open'), // 'open' | 'closed'
  createdAt: text('created_at').notNull(),
  updatedAt: text('updated_at').notNull(),
  closedAt: text('closed_at'),
  closedBy: integer('closed_by'),
}, (t) => ({
  userIdx: index('idx_tickets_user').on(t.userId, t.status),
  statusIdx: index('idx_tickets_status').on(t.status, t.updatedAt),
}));

export const messages = table('messages', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  ticketId: integer('ticket_id').notNull(),
  sender: text('sender').notNull(), // 'user' | 'admin'
  adminId: integer('admin_id'),
  text: text('text'),
  mediaType: text('media_type'),
  fileId: text('file_id'),
  createdAt: text('created_at').notNull(),
}, (t) => ({
  ticketIdx: index('idx_messages_ticket').on(t.ticketId, t.id),
}));

// Сообщения, которые бот отправил админам по обращению: чтобы снимать кнопки
// при закрытии и понимать, на какое обращение админ отвечает через reply.
export const notifications = table('notifications', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  chatId: integer('chat_id').notNull(),
  messageId: integer('message_id').notNull(),
  ticketId: integer('ticket_id').notNull(),
  hasButtons: integer('has_buttons').notNull().default(0),
}, (t) => ({
  msgIdx: uniqueIndex('idx_notifications_msg').on(t.chatId, t.messageId),
  ticketIdx: index('idx_notifications_ticket').on(t.ticketId),
}));

// Состояние диалога: какой админ сейчас пишет ответ и на какое обращение,
// а также служебные отметки (например, предупреждение об антиспаме).
export const sessions = table('sessions', {
  key: text('key').primaryKey(),
  ticketId: integer('ticket_id'),
  updatedAt: text('updated_at').notNull(),
});
