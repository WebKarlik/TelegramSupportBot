// Тесты версии для Telegram Serverless на локальном эмуляторе sdk.
// Запуск: npm test  (Node.js 22.5+)
import './register.mjs';
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

const sdk = await import('sdk');
const schema = await import('../../tgcloud/schema.js');
const config = await import('../../tgcloud/lib/config.js');
const onMessage = (await import('../../tgcloud/handlers/message.js')).default;
const onCallback = (await import('../../tgcloud/handlers/callback_query.js')).default;
const ep = async (name, input, userId) =>
  (await import(`../../tgcloud/endpoints/${name}.js`)).default(input, { initData: { user: { id: userId, first_name: 'T' } } });
const { store } = await import('../../tgcloud/lib/support.js');
const { toBase64 } = await import('../../tgcloud/lib/endpoint.js');

const SUPER = 1000, ADMIN = 2000, USER = 3000;
config.SUPERADMIN_IDS.length = 0;
config.SUPERADMIN_IDS.push(SUPER);

let seq = 1;
const msg = (from, fields = {}) => ({
  message_id: seq++, date: 1700000000, chat: { id: from, type: 'private' },
  from: { id: from, is_bot: false, first_name: `U${from}` }, ...fields,
});
const say = (from, text, extra = {}) => onMessage(msg(from, { text, ...extra }));
const press = (from, data) => onCallback({
  id: String(seq++), from: { id: from }, data, message: { message_id: 1, chat: { id: from, type: 'private' } },
});
const texts = (chatId) => sdk.sent('sendMessage', chatId).map((p) => p.text);

beforeEach(async () => { await sdk.resetSdk(schema); });

test('сообщение пользователя создаёт обращение и уходит всем админам', async () => {
  await store.addAdmin(ADMIN, 'Админ', SUPER);
  await say(USER, 'Не работает VPN');
  const t = await store.getOpenTicket(USER);
  assert.equal(t.id, 1);
  assert.match(texts(SUPER)[0], /Новое обращение #1[\s\S]*Не работает VPN/);
  assert.match(texts(ADMIN)[0], /Не работает VPN/);
  assert.match(texts(USER)[0], /#1 отправлено/);

  sdk.calls.length = 0;
  await say(USER, 'Ещё деталь');
  assert.equal((await store.getMessages(1)).length, 2);
  assert.deepEqual(texts(USER), [], 'повторное подтверждение пользователю не нужно');
  assert.match(texts(SUPER)[0], /Обращение #1 — новое сообщение/);
});

test('/cancel админа не уходит пользователю', async () => {
  await say(USER, 'help');
  await press(SUPER, 'reply:1');
  sdk.calls.length = 0;
  await say(SUPER, '/cancel');
  assert.deepEqual(texts(USER), []);
  assert.match(texts(SUPER)[0], /отменён/);
  sdk.calls.length = 0;
  await say(SUPER, 'просто текст');
  assert.deepEqual(texts(USER), []);
});

test('ответ кнопкой и через reply на уведомление', async () => {
  await say(USER, 'help');
  await press(SUPER, 'reply:1');
  sdk.calls.length = 0;
  await say(SUPER, 'Перезагрузите роутер');
  assert.match(texts(USER)[0], /Ответ поддержки PotatVPN:\n\nПерезагрузите роутер/);

  const notif = sdk.calls.length && (await sdk.db.get(
    (await import('sdk/db')).sql`SELECT message_id FROM notifications WHERE chat_id = ${SUPER} AND has_buttons = 1 LIMIT 1`));
  sdk.calls.length = 0;
  await say(SUPER, 'И ещё совет', { reply_to_message: { message_id: notif.message_id, chat: { id: SUPER } } });
  assert.match(texts(USER)[0], /И ещё совет/);
  assert.deepEqual((await store.getMessages(1)).map((m) => m.sender), ['user', 'admin', 'admin']);
});

test('фото пересылается админам и сохраняется', async () => {
  await onMessage(msg(USER, { caption: 'скрин', photo: [{ file_id: 'small' }, { file_id: 'BIG' }] }));
  const [m] = await store.getMessages(1);
  assert.equal(m.media_type, 'photo'); assert.equal(m.text, 'скрин'); assert.equal(m.has_file, 1);
  assert.ok(sdk.sent('copyMessage', SUPER).length === 1);
  assert.equal((await store.getMessage(m.id)).file_id, 'BIG');
});

test('закрытие: кнопки снимаются, пользователь уведомлён, новое сообщение — новое обращение', async () => {
  await say(USER, 'help');
  sdk.calls.length = 0;
  await press(SUPER, 'close:1');
  assert.equal((await store.getTicket(1)).status, 'closed');
  assert.ok(sdk.sent('editMessageReplyMarkup').length >= 1);
  assert.match(texts(USER)[0], /закрыто/);
  await say(USER, 'снова я');
  assert.equal((await store.getOpenTicket(USER)).id, 2);
  assert.equal((await store.getMessages(1))[0].text, 'help');
});

test('не-админ не может нажимать кнопки админа', async () => {
  await say(USER, 'help');
  await press(USER, 'close:1');
  assert.equal((await store.getTicket(1)).status, 'open');
  assert.equal(sdk.sent('answerCallbackQuery').at(-1).show_alert, true);
});

test('суперадмин управляет админами командами и кнопкой выбора пользователя', async () => {
  await say(SUPER, `/addadmin ${ADMIN}`);
  assert.equal((await store.listAdmins())[0].name, 'Иван Петров');
  await say(ADMIN, '/addadmin 5555');
  assert.equal((await store.listAdmins()).length, 1, 'обычный админ не может добавлять');
  await onMessage(msg(SUPER, { users_shared: { request_id: 1, users: [{ user_id: 777, first_name: 'Пётр' }] } }));
  assert.ok((await store.listAdmins()).some((a) => a.user_id === 777 && a.name === 'Пётр'));
  await press(SUPER, 'deladmin:777');
  await say(SUPER, `/deladmin ${ADMIN}`);
  assert.equal((await store.listAdmins()).length, 0);
  await say(ADMIN, 'я больше не админ');
  assert.ok(await store.getOpenTicket(ADMIN));
});

test('антиспам', async () => {
  for (let i = 0; i < 8; i++) await say(USER, `spam ${i}`);
  assert.equal((await store.getMessages(1)).length, config.RATE_LIMIT_MESSAGES);
  assert.equal(texts(USER).filter((t) => /Слишком много/.test(t)).length, 1);
});

test('неподдерживаемые сообщения и чужие команды', async () => {
  await onMessage(msg(USER, { location: { latitude: 1, longitude: 2 } }));
  assert.equal(await store.getOpenTicket(USER), null);
  await say(USER, '/cancel');
  assert.equal(await store.getOpenTicket(USER), null);
  assert.match(texts(USER).at(-1), /опишите/);
});

test('админ заблокировал бота — остальные всё равно получают обращение', async () => {
  await store.addAdmin(ADMIN, 'A', SUPER);
  sdk.failFor.add(SUPER);
  await say(USER, 'help');
  assert.match(texts(ADMIN)[0], /help/);
});

test('endpoints мини-приложения', async () => {
  await say(USER, 'помогите');
  await assert.rejects(ep('me', {}, USER), sdk.EndpointError);
  const me = await ep('me', {}, SUPER);
  assert.equal(me.is_superadmin, true); assert.equal(me.stats.waiting, 1);

  const list = await ep('listTickets', { status: 'open' }, SUPER);
  assert.equal(list.tickets[0].last_sender, 'user');
  assert.equal((await ep('listTickets', { status: 'all', q: 'помог' }, SUPER)).tickets.length, 1);
  assert.equal((await ep('listTickets', { status: 'all', q: '#1' }, SUPER)).tickets.length, 1);
  assert.equal((await ep('listTickets', { status: 'all', q: 'нет такого' }, SUPER)).tickets.length, 0);

  await ep('replyTicket', { id: 1, text: 'Уже чиним' }, SUPER);
  assert.match(texts(USER).at(-1), /Уже чиним/);
  const t = await ep('getTicket', { id: 1 }, SUPER);
  assert.deepEqual(t.messages.map((m) => m.sender), ['user', 'admin']);
  assert.ok(!('file_id' in t.messages[0]));
  await assert.rejects(ep('replyTicket', { id: 1, text: '   ' }, SUPER), /Пустой ответ/);
  assert.equal((await ep('closeTicket', { id: 1 }, SUPER)).changed, true);
  await assert.rejects(ep('replyTicket', { id: 1, text: 'x' }, SUPER), /закрыто/);
  assert.equal((await ep('reopenTicket', { id: 1 }, SUPER)).changed, true);
  await assert.rejects(ep('getTicket', { id: 99 }, SUPER), /не найдено/);
});

test('endpoints: файлы и админы', async () => {
  await onMessage(msg(USER, { photo: [{ file_id: 'P' }] }));
  const f = await ep('getFile', { message_id: 1 }, SUPER);
  assert.equal(f.mime, 'image/jpeg'); assert.equal(f.data, '/9j/4AE=');

  await ep('addAdmin', { user_id: ADMIN, name: 'Петя' }, SUPER);
  await assert.rejects(ep('listAdmins', {}, ADMIN), /суперадмина/);
  assert.ok(await ep('listTickets', {}, ADMIN));
  assert.equal((await ep('listAdmins', {}, SUPER)).admins[0].name, 'Петя');
  await assert.rejects(ep('addAdmin', { user_id: ADMIN }, SUPER), /уже админ/);
  await assert.rejects(ep('addAdmin', { user_id: SUPER }, SUPER), /суперадмин/);
  await ep('deleteAdmin', { user_id: ADMIN }, SUPER);
  await assert.rejects(ep('me', {}, ADMIN), /только для администраторов/i);
});

test('base64 совпадает с эталоном', () => {
  for (const len of [0, 1, 2, 3, 4, 5, 100]) {
    const bytes = Uint8Array.from({ length: len }, (_, i) => (i * 37 + 11) % 256);
    assert.equal(toBase64(bytes), Buffer.from(bytes).toString('base64'));
  }
});
