import * as S from '../lib/support.js';
import { adminEndpoint, toId } from '../lib/endpoint.js';

export default adminEndpoint(async (input) => {
  if (!(await S.removeAdmin(toId(input.user_id)))) throw new S.NotFoundError('Админ не найден');
  return { ok: true };
}, { superadmin: true });
