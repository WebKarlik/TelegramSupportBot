import * as S from '../lib/support.js';
import { adminEndpoint } from '../lib/endpoint.js';

export default adminEndpoint(async (input, uid) => ({
  user_id: uid,
  is_superadmin: S.isSuperadmin(uid),
  support_name: S.SUPPORT_NAME,
  stats: await S.store.stats(),
}));
