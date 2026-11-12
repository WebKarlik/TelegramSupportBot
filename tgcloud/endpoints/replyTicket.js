import * as S from '../lib/support.js';
import { adminEndpoint, toId } from '../lib/endpoint.js';

export default adminEndpoint(async (input, uid) => {
  await S.reply(toId(input.id), uid, { text: String(input.text || '').trim() });
  return { ok: true };
});
