// Настройки бота для Telegram Serverless.
// В Serverless нет файла .env, поэтому настройки задаются здесь.

// Telegram ID суперадминов. Суперадмин видит все обращения и может добавлять/удалять админов.
// Узнать свой ID: напишите @userinfobot или @getmyid_bot.
export const SUPERADMIN_IDS = [
  // 123456789,
];

// Название сервиса в приветствии и ответах.
export const SUPPORT_NAME = 'PotatVPN';

// Адрес мини-приложения. После первого `npx tgcloud push` CLI печатает адрес вида
// https://app<id>.tgcloud.ai/ — вставьте его сюда и сделайте push ещё раз.
// Пустая строка — кнопки «Панель» не будет.
export const WEBAPP_URL = '';

// Антиспам: не больше RATE_LIMIT_MESSAGES сообщений от пользователя за RATE_LIMIT_WINDOW секунд.
export const RATE_LIMIT_MESSAGES = 5;
export const RATE_LIMIT_WINDOW = 30;
