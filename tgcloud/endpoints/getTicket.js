import * as S from '../lib/support.js';
import { adminEndpoint, toId } from '../lib/endpoint.js';

export default adminEndpoint(async (input) => {
  const id = toId(input.id);
  const ticket = await S.store.getTicket(id);
  if (!ticket) throw new S.NotFoundError('Обращение не найдено');
  const messages = (await S.store.getMessages(id)).map((m) => ({ ...m, has_file: !!m.has_file }));
  return { ticket, messages };
});
