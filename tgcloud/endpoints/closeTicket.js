import * as S from '../lib/support.js';
import { adminEndpoint, toId } from '../lib/endpoint.js';

export default adminEndpoint(async (input, uid) => ({ ok: true, changed: await S.close(toId(input.id), uid) }));
