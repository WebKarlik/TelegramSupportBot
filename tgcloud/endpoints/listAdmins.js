import * as S from '../lib/support.js';
import { SUPERADMIN_IDS } from '../lib/config.js';
import { adminEndpoint } from '../lib/endpoint.js';

export default adminEndpoint(async () => ({
  superadmins: [...SUPERADMIN_IDS],
  admins: await S.store.listAdmins(),
}), { superadmin: true });
