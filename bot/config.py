import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)


def _parse_ids(raw: str | None, var_name: str) -> list[int]:
    ids: list[int] = []
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            raise ValueError(f"{var_name}: '{part}' не является числовым Telegram ID") from None
    return ids


@dataclass(frozen=True)
class Config:
    bot_token: str
    superadmin_ids: frozenset[int]
    initial_admin_ids: tuple[int, ...]
    support_name: str
    db_path: Path
    webapp_url: str | None
    web_host: str
    web_port: int
    rate_limit_messages: int = 5
    rate_limit_window: int = 30


def load_config() -> Config:
    load_dotenv()

    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise ValueError("Не задана переменная окружения BOT_TOKEN")

    initial_admins = _parse_ids(os.getenv("ADMINS"), "ADMINS")
    superadmins = _parse_ids(os.getenv("SUPERADMIN_IDS"), "SUPERADMIN_IDS")
    if not superadmins and initial_admins:
        # Обратная совместимость со старым .env, где был только ADMINS.
        superadmins = [initial_admins[0]]
        log.warning(
            "SUPERADMIN_IDS не задан — суперадмином назначен первый ID из ADMINS (%s). "
            "Лучше явно указать SUPERADMIN_IDS в .env",
            initial_admins[0],
        )
    if not superadmins:
        raise ValueError("Не задана переменная окружения SUPERADMIN_IDS (ваш Telegram ID)")

    webapp_url = (os.getenv("WEBAPP_URL") or "").strip() or None
    if not webapp_url:
        domain = (os.getenv("WEBAPP_DOMAIN") or "").strip()
        if domain:
            webapp_url = f"https://{domain}/"
    if webapp_url and not webapp_url.startswith("https://"):
        raise ValueError("WEBAPP_URL должен начинаться с https:// — Telegram не открывает мини-приложения по http")

    data_dir = Path(os.getenv("DATA_DIR", "data"))
    return Config(
        bot_token=token,
        superadmin_ids=frozenset(superadmins),
        initial_admin_ids=tuple(initial_admins),
        support_name=os.getenv("SUPPORT_NAME", "PotatVPN").strip(),
        db_path=data_dir / "bot.db",
        webapp_url=webapp_url,
        web_host=os.getenv("WEB_HOST", "0.0.0.0"),
        web_port=int(os.getenv("WEB_PORT", "8080")),
        rate_limit_messages=int(os.getenv("RATE_LIMIT_MESSAGES", "5")),
        rate_limit_window=int(os.getenv("RATE_LIMIT_WINDOW", "30")),
    )
