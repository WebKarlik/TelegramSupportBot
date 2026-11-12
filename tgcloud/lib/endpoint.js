// Обёртка для endpoints мини-приложения: проверка прав и понятные ошибки.
import { EndpointError } from 'sdk';
import * as S from './support.js';

// Оборачивает обработчик: пускает только админов (или только суперадминов),
// а ошибки UserError превращает в EndpointError, которые мини-приложение показывает как есть.
export function adminEndpoint(fn, { superadmin = false } = {}) {
  return async function (input, ctx) {
    const user = ctx && ctx.initData && ctx.initData.user;
    if (!user) throw new EndpointError('Откройте панель из Telegram');
    if (!(await S.isAdmin(user.id))) throw new EndpointError('Доступ только для администраторов');
    if (superadmin && !S.isSuperadmin(user.id)) throw new EndpointError('Только для суперадмина');
    try {
      return await fn(input || {}, user.id);
    } catch (e) {
      if (e instanceof S.UserError) throw new EndpointError(e.message);
      throw e;
    }
  };
}

export function toId(value, what = 'ID') {
  const n = Number(value);
  if (!Number.isSafeInteger(n) || n <= 0) throw new S.UserError(`Некорректный ${what}`);
  return n;
}

// base64 без Buffer/btoa — в рантайме Serverless есть только стандартный JS.
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
export function toBase64(bytes) {
  let out = '';
  let i = 0;
  for (; i + 2 < bytes.length; i += 3) {
    const n = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2];
    out += ALPHABET[(n >> 18) & 63] + ALPHABET[(n >> 12) & 63] + ALPHABET[(n >> 6) & 63] + ALPHABET[n & 63];
  }
  const rest = bytes.length - i;
  if (rest === 1) {
    const n = bytes[i] << 16;
    out += ALPHABET[(n >> 18) & 63] + ALPHABET[(n >> 12) & 63] + '==';
  } else if (rest === 2) {
    const n = (bytes[i] << 16) | (bytes[i + 1] << 8);
    out += ALPHABET[(n >> 18) & 63] + ALPHABET[(n >> 12) & 63] + ALPHABET[(n >> 6) & 63] + '=';
  }
  return out;
}
