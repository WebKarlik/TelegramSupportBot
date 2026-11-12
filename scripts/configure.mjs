#!/usr/bin/env node
// Генерирует tgcloud/lib/settings.js — личные настройки бота для Telegram Serverless.
// Этот файл НЕ хранится в git (он в .gitignore), но `tgcloud push` выкладывает его на платформу,
// поэтому в публичном репозитории ваши ID не видны.
//
// Откуда берутся значения (по приоритету):
//   1. переменные окружения (в GitHub Actions — из Secrets/Variables);
//   2. файл .env в корне проекта (тот же формат, что у серверной версии).
//
//   SUPERADMIN_IDS   — обязательно, ID через запятую
//   SUPPORT_NAME     — название сервиса (по умолчанию PotatVPN)
//   WEBAPP_URL       — адрес мини-приложения; если не задан, вычисляется из CLI-токена
//                      (app<id>:… → https://app<id>.tgcloud.ai/)
//   RATE_LIMIT_MESSAGES, RATE_LIMIT_WINDOW — антиспам
//
// Флаг --allow-empty: не требовать SUPERADMIN_IDS (для тестов).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(root, 'tgcloud', 'lib', 'settings.js');
const allowEmpty = process.argv.includes('--allow-empty');

function readDotEnv() {
  const file = path.join(root, '.env');
  if (!fs.existsSync(file)) return {};
  const env = {};
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const m = /^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/.exec(line);
    if (m && !line.trimStart().startsWith('#')) env[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2');
  }
  return env;
}

function cliToken() {
  if (process.env.TGCLOUD_TOKEN) return process.env.TGCLOUD_TOKEN;
  try {
    return JSON.parse(fs.readFileSync(path.join(root, '.tgcloud', 'credentials'), 'utf8')).token || '';
  } catch {
    return '';
  }
}

const dotenv = readDotEnv();
const get = (name) => (process.env[name] ?? dotenv[name] ?? '').trim();

const superadmins = get('SUPERADMIN_IDS').split(/[,;\s]+/).filter(Boolean);
const bad = superadmins.filter((id) => !/^\d+$/.test(id));
if (bad.length) {
  console.error(`✗ SUPERADMIN_IDS: «${bad.join(', ')}» — это не числовые Telegram ID`);
  process.exit(1);
}
if (!superadmins.length && !allowEmpty) {
  console.error('✗ Не задан SUPERADMIN_IDS — ваш Telegram ID (узнать: @userinfobot).\n'
    + '  Локально: добавьте строку SUPERADMIN_IDS=123456789 в файл .env\n'
    + '  В GitHub: Settings → Secrets and variables → Actions → секрет SUPERADMIN_IDS');
  process.exit(1);
}

let webappUrl = get('WEBAPP_URL');
const appId = /^(app\d+):/.exec(cliToken())?.[1];
if (!webappUrl && appId) webappUrl = `https://${appId}.tgcloud.ai/`;
if (webappUrl && !webappUrl.startsWith('https://')) {
  console.error('✗ WEBAPP_URL должен начинаться с https://');
  process.exit(1);
}
if (webappUrl && !webappUrl.endsWith('/')) webappUrl += '/';

const int = (name, def) => {
  const v = get(name);
  return /^\d+$/.test(v) ? Number(v) : def;
};

const content = `// СГЕНЕРИРОВАНО scripts/configure.mjs — не редактируйте и не добавляйте в git.
// Значения берутся из переменных окружения или файла .env.
export const SUPERADMIN_IDS = [${superadmins.join(', ')}];
export const SUPPORT_NAME = ${JSON.stringify(get('SUPPORT_NAME') || 'PotatVPN')};
export const WEBAPP_URL = ${JSON.stringify(webappUrl)};
export const RATE_LIMIT_MESSAGES = ${int('RATE_LIMIT_MESSAGES', 5)};
export const RATE_LIMIT_WINDOW = ${int('RATE_LIMIT_WINDOW', 30)};
`;
fs.writeFileSync(out, content);
console.log(`✓ Настройки записаны в tgcloud/lib/settings.js: суперадминов — ${superadmins.length}, `
  + `мини-приложение — ${webappUrl || 'не настроено'}`);
