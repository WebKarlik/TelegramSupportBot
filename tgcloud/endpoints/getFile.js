// Отдаёт вложение из обращения (фото, видео, голосовое…) в base64 для показа в панели.
import { api, BotApiError } from 'sdk';
import * as S from '../lib/support.js';
import { adminEndpoint, toBase64, toId } from '../lib/endpoint.js';

const MIME_BY_EXT = {
  jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp', gif: 'image/gif',
  mp4: 'video/mp4', webm: 'video/webm', mov: 'video/quicktime', oga: 'audio/ogg', ogg: 'audio/ogg',
  mp3: 'audio/mpeg', m4a: 'audio/mp4', pdf: 'application/pdf', txt: 'text/plain',
};
const MIME_BY_TYPE = {
  photo: 'image/jpeg', sticker: 'image/webp', voice: 'audio/ogg', video_note: 'video/mp4',
  animation: 'video/mp4', video: 'video/mp4',
};

export default adminEndpoint(async (input) => {
  const msg = await S.store.getMessage(toId(input.message_id));
  if (!msg || !msg.file_id) throw new S.NotFoundError('Файл не найден');
  let file, bytes;
  try {
    file = await api.getFile({ file_id: msg.file_id });
    bytes = await api.getFileContent(msg.file_id);
  } catch (e) {
    if (e instanceof BotApiError) throw new S.UserError('Файл слишком большой для просмотра (лимит Telegram — 20 МБ)');
    throw e;
  }
  const ext = String((file && file.file_path) || '').split('.').pop().toLowerCase();
  const mime = MIME_BY_EXT[ext] || MIME_BY_TYPE[msg.media_type] || 'application/octet-stream';
  return { mime, data: toBase64(bytes) };
});
