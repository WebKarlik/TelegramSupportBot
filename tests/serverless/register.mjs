// Подменяет модули платформы `sdk`, `sdk/db`, … локальным эмулятором для тестов.
import { register } from 'node:module';
register('./hooks.mjs', import.meta.url);
