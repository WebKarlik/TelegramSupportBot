import * as S from '../lib/support.js';
import { adminEndpoint } from '../lib/endpoint.js';

export default adminEndpoint(async (input) => {
  const status = input.status || 'open';
  if (!['open', 'closed', 'all'].includes(status)) throw new S.UserError('Некорректный статус');
  const tickets = await S.store.listTickets(status === 'all' ? null : status, 200, String(input.q || ''));
  return { tickets, stats: await S.store.stats() };
});
