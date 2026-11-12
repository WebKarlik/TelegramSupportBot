// Настройки бота для Telegram Serverless.
//
// Личные значения (ID суперадминов и т.п.) НЕ хранятся в репозитории: перед деплоем
// `npm run deploy` запускает scripts/configure.mjs, который создаёт tgcloud/lib/settings.js
// из файла .env или из секретов GitHub Actions. settings.js в .gitignore, но выкладывается на платформу.
import * as settings from './settings.js';

// Telegram ID суперадминов: видят все обращения и добавляют/удаляют админов.
export const SUPERADMIN_IDS = [...(settings.SUPERADMIN_IDS || [])];

// Название сервиса в приветствии и ответах.
export const SUPPORT_NAME = settings.SUPPORT_NAME || 'PotatVPN';

// Адрес мини-приложения (https://app<id>.tgcloud.ai/). Пусто — кнопки «Панель» не будет.
export const WEBAPP_URL = settings.WEBAPP_URL || '';

// Антиспам: не больше RATE_LIMIT_MESSAGES сообщений от пользователя за RATE_LIMIT_WINDOW секунд.
export const RATE_LIMIT_MESSAGES = settings.RATE_LIMIT_MESSAGES || 5;
export const RATE_LIMIT_WINDOW = settings.RATE_LIMIT_WINDOW || 30;
