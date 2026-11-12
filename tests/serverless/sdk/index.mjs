// Мини-эмулятор `sdk`: db поверх node:sqlite и api, который записывает вызовы.
import { DatabaseSync } from 'node:sqlite';
import { Fragment, ddl } from './db.mjs';

export class BotApiError extends Error {
  constructor(method, code, description) { super(description); Object.assign(this, { method, code, description }); }
}
export class EndpointError extends Error {
  constructor(description, parameters) { super(description); this.description = description; this.parameters = parameters; }
}
export class InputFile { constructor(bytes, name, o) { Object.assign(this, { bytes, name, ...o }); } }

let conn;
const q = (f) => (f instanceof Fragment ? f.toQuery() : { text: f, params: [] });
export const db = {
  async all(f) { const { text, params } = q(f); return conn.prepare(text).all(...params).map((r) => ({ ...r })); },
  async get(f) { const { text, params } = q(f); const r = conn.prepare(text).get(...params); return r ? { ...r } : undefined; },
  async run(f) {
    const { text, params } = q(f);
    const st = conn.prepare(text);
    if (/\bRETURNING\b/i.test(text)) { const rows = st.all(...params).map((r) => ({ ...r })); return { rowsAffected: rows.length, lastInsertRowid: 0, rows }; }
    const r = st.run(...params);
    return { rowsAffected: Number(r.changes), lastInsertRowid: Number(r.lastInsertRowid), rows: [] };
  },
};

// Тестовые помощники
export const calls = [];
export const failFor = new Set(); // chat_id, для которых sendMessage падает (бот заблокирован)
let nextId = 500;
export async function resetSdk(schema) {
  conn = new DatabaseSync(':memory:');
  for (const t of Object.values(schema)) for (const s of ddl(t)) conn.exec(s);
  calls.length = 0; failFor.clear();
}
export const sent = (method, chatId) =>
  calls.filter((c) => c.method === method && (chatId === undefined || c.params.chat_id === chatId)).map((c) => c.params);

export const api = new Proxy({}, {
  get(_, method) {
    return async (params = {}) => {
      calls.push({ method, params });
      if (failFor.has(params.chat_id)) throw new BotApiError(method, 403, 'Forbidden: bot was blocked by the user');
      switch (method) {
        case 'sendMessage': return { message_id: nextId++, chat: { id: params.chat_id }, text: params.text };
        case 'copyMessage': return { message_id: nextId++ };
        case 'getChat': return { id: params.chat_id, first_name: 'Иван', last_name: 'Петров' };
        case 'getFile': return { file_id: params.file_id, file_path: 'photos/file_1.jpg' };
        case 'getFileContent': return new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1]);
        default: return true;
      }
    };
  },
});
export const fetch = () => { throw new Error('fetch is not used'); };
