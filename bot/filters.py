from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from .services import SupportService


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, service: SupportService) -> bool:
        return event.from_user is not None and service.is_admin(event.from_user.id)


class IsSuperAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, service: SupportService) -> bool:
        return event.from_user is not None and service.is_superadmin(event.from_user.id)
