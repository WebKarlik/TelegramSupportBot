# TelegramSupportBot

Бот поддержки для Telegram: пользователи пишут боту, администраторы отвечают им анонимно от имени бота —
прямо в чате или через удобную панель (мини-приложение).

## Возможности

- 📩 **Обращения с номерами** (#1, #2, …). Все сообщения пользователя попадают в одно открытое обращение,
  история переписки сохраняется. После закрытия новое сообщение открывает новое обращение.
- 🖼 **Любые вложения** — фото, видео, голосовые, файлы, стикеры — в обе стороны.
- ✍️ **Два способа ответить**: кнопка «Ответить» под обращением или обычный *reply* на уведомление.
- 🗂 **Мини-приложение (панель)**: список обращений с поиском, переписка, ответ, закрытие, статистика.
- 👑 **Роли**: суперадмин (задаётся в настройках) добавляет и удаляет админов прямо из Telegram —
  командой `/addadmin` с выбором пользователя из контактов или в панели.
- 🔔 Пользователь получает уведомление о закрытии обращения; у всех админов пропадают кнопки.
- 🛡 Антиспам, проверка подписи Telegram в панели, данные в SQLite.

## Две версии — выберите одну

| | **Сервер + Docker** (папка `bot/`) | **Telegram Serverless** (папка `tgcloud/`) |
|---|---|---|
| Где работает | ваш VPS | инфраструктура Telegram, свой сервер не нужен |
| Язык | Python (aiogram) | JavaScript |
| Обновление | `docker compose pull && docker compose up -d` | `npm run deploy` или автоматически из GitHub |
| Мини-приложение | нужен домен (HTTPS сделает Caddy) | бесплатный адрес `https://app<id>.tgcloud.ai/` |
| Статус | стабильно | платформа в бета-версии, нужен доступ в BotFather |

Возможности у версий одинаковые, мини-приложение общее (`webapp/index.html`).
**Одновременно может работать только одна версия** — Telegram отдаёт сообщения бота либо серверу, либо Serverless.
Базы данных у версий разные: при переходе с одной на другую история обращений не переносится.

---

## Вариант 1. Сервер + Docker

Docker-образ собирается автоматически (GitHub Actions) при каждом изменении в ветке `main` и публикуется в
`ghcr.io/webkarlik/telegramsupportbot`. На сервере ничего собирать и скачивать вручную не нужно.

### Установка

1. Установите Docker (если ещё не установлен):
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
2. Создайте папку бота и скачайте два файла:
   ```bash
   mkdir -p ~/supportbot && cd ~/supportbot
   ```
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/WebKarlik/TelegramSupportBot/main/docker-compose.yml
   ```
   ```bash
   curl -fsSL -o .env https://raw.githubusercontent.com/WebKarlik/TelegramSupportBot/main/.env.example
   ```
3. Заполните `.env`:
   ```bash
   nano .env
   ```
   - `BOT_TOKEN` — токен от [@BotFather](https://t.me/BotFather);
   - `SUPERADMIN_IDS` — ваш Telegram ID (узнать: [@userinfobot](https://t.me/userinfobot)). Можно несколько через запятую;
   - `ADMINS` — необязательно: стартовый список админов (только при первом запуске, дальше — через `/addadmin`).
4. Запустите:
   ```bash
   docker compose up -d
   ```
5. Напишите боту `/start` со своего аккаунта — придёт справка администратора.

### Обновление

```bash
docker compose pull && docker compose up -d
```

Данные (база SQLite) лежат в Docker-томе `bot-data` и сохраняются при обновлениях.

### Мини-приложение (панель) на своём сервере

Telegram открывает мини-приложения только по HTTPS, поэтому нужен домен (подойдёт и поддомен, например `support.example.com`).

1. В DNS создайте A-запись домена на IP сервера. Откройте порты 80 и 443.
2. В `.env` укажите домен и включите Caddy (он сам получит сертификат Let's Encrypt):
   ```
   WEBAPP_DOMAIN=support.example.com
   COMPOSE_PROFILES=webapp
   ```
3. Перезапустите: `docker compose up -d`.

У всех админов в чате с ботом появится кнопка **«Панель»** (слева от поля ввода) и команда `/panel`.
Если HTTPS у вас уже настроен иначе (nginx, Cloudflare Tunnel), вместо этого укажите `WEBAPP_URL=https://…/`
и проксируйте его на порт 8080 контейнера `bot`.

### Полезные команды

```bash
docker compose logs -f bot
```
```bash
docker compose restart bot
```

### Если `docker compose pull` пишет `denied` / `unauthorized`

Новые пакеты в GitHub Container Registry по умолчанию приватные. Один раз сделайте пакет публичным:
GitHub → ваш профиль → **Packages** → `telegramsupportbot` → **Package settings** → **Change visibility** → **Public**.
Либо войдите на сервере токеном GitHub с правом `read:packages`:
```bash
docker login ghcr.io -u <ваш_логин_GitHub>
```

### Переезд со старой версии (tickets.json)

Старые обращения из `tickets.json` переносятся автоматически. Положите файл в данные бота и перезапустите:
```bash
docker compose cp tickets.json bot:/app/data/tickets.json && docker compose restart bot
```
После импорта файл переименуется в `tickets.json.imported`.

### Запуск без Docker

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
```bash
cp .env.example .env && nano .env
```
```bash
.venv/bin/python main.py
```

---

## Вариант 2. Telegram Serverless

[Telegram Serverless](https://core.telegram.org/bots/serverless) — платформа Telegram, где код бота работает
в облаке Telegram: без сервера, со встроенной базой данных и хостингом мини-приложения.
Сейчас она в **бета-версии**, доступ включается в BotFather.

### 1. Включите Serverless и получите токен для CLI

1. Откройте [@BotFather](https://t.me/BotFather) → ваш бот → **Serverless** и включите переключатель **Serverless**
   (если его нет — нажмите «Get access to Serverless» и дождитесь одобрения).
2. Там же откройте **CLI Access** и скопируйте **Access token** (вида `app123…:…`).
   Это **не** токен бота, а отдельный ключ для деплоя. Никому его не показывайте.

### 2. Настройте проект

Нужен [Node.js](https://nodejs.org) 22 или новее.

```bash
git clone https://github.com/WebKarlik/TelegramSupportBot.git && cd TelegramSupportBot
```
```bash
npm install
```

Откройте `tgcloud/lib/config.js` и впишите свой Telegram ID в `SUPERADMIN_IDS`:
```js
export const SUPERADMIN_IDS = [
  123456789,
];
```

### 3. Задеплойте

```bash
npx tgcloud login
```
Вставьте Access token из шага 1. Затем:
```bash
npm run deploy
```
```bash
npx tgcloud migrate
```

`deploy` загружает код и мини-приложение, `migrate` создаёт таблицы в базе (подтвердите изменения).
Webhook Telegram настраивает сама платформа. Если раньше бот работал на сервере — остановите его (`docker compose down`).

### 4. Подключите мини-приложение

1. `npm run deploy` печатает адрес мини-приложения вида `https://app<id>.tgcloud.ai/`.
2. Вставьте его в `WEBAPP_URL` в `tgcloud/lib/config.js` и снова выполните `npm run deploy`.
3. Напишите боту `/start` — у вас (и у каждого добавленного админа) появится кнопка **«Панель»**.

Обычные пользователи панель не видят, а если откроют ссылку — получат отказ: доступ проверяется по подписи Telegram.

### Проверка и обновление

```bash
npx tgcloud status
```
```bash
npx tgcloud webhook
```

После изменений в коде — `npm run deploy`; если менялась `tgcloud/schema.js` — ещё `npx tgcloud migrate`.

### Автодеплой из GitHub (необязательно)

Добавьте Access token в репозиторий: **Settings → Secrets and variables → Actions → New repository secret**,
имя `TGCLOUD_TOKEN`. После этого каждое изменение в `main` автоматически выкладывается в Serverless
(workflow `.github/workflows/serverless.yml`: тесты → `tgcloud push` → безопасные миграции).
Без секрета этот workflow просто пропускается.

---

## Как пользоваться

**Пользователь** пишет боту что угодно — создаётся обращение, и все админы получают уведомление.

**Админ** отвечает:
- кнопкой **✍️ Ответить** под уведомлением, затем отправляет сообщение (текст, фото, файл…), или
- через **reply** (свайп/«Ответить») на уведомление об обращении, или
- в **панели**.

Закрыть обращение — кнопка **✅ Закрыть** (в чате или в панели).

**Суперадмин** дополнительно управляет командой:
- `/addadmin` → кнопка «Выбрать пользователя» (из контактов) или `/addadmin 123456789`;
- `/admins` — список с кнопками удаления, `/deladmin 123456789`;
- вкладка **👑 Админы** в панели.

Новый админ должен хотя бы раз нажать `/start` у бота, иначе Telegram не даст боту написать ему первым.

| Команда | Кто | Что делает |
|---|---|---|
| `/start`, `/help` | все | приветствие / справка админа |
| `/panel` | админы | открыть панель |
| `/tickets` | админы | открытые обращения (🔴 — ждут ответа) |
| `/cancel` | админы | отменить начатый ответ |
| `/admins`, `/addadmin`, `/deladmin` | суперадмин | управление админами |

## Структура проекта

```
bot/                Python-версия (aiogram): handlers/, services.py, db.py, web.py (API панели)
tgcloud/            версия для Telegram Serverless: handlers/, endpoints/, lib/, schema.js
webapp/index.html   мини-приложение — общее для обеих версий
tests/              тесты: pytest (Python) и node:test (Serverless, на локальном эмуляторе sdk)
Dockerfile, docker-compose.yml, .github/workflows/
```

## Разработка

```bash
pip install -r requirements-dev.txt && pytest
```
```bash
npm test
```
