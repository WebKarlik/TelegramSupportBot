import * as S from '../lib/support.js';
import { adminEndpoint, toId } from '../lib/endpoint.js';

export default adminEndpoint(async (input, uid) => {
  const name = String(input.name || '').trim() || null;
  if (!(await S.addAdmin(toId(input.user_id, 'Telegram ID'), name, uid))) {
    throw new S.UserError('Этот пользователь уже админ');
  }
  return { ok: true };
}, { superadmin: true });
