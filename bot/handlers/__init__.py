from aiogram import Router

from . import admin, superadmin, user


def setup_routers() -> Router:
    root = Router()
    # Порядок важен: сначала роли с большими правами, пользовательский роутер — последним.
    root.include_routers(superadmin.router, admin.router, user.router)
    return root
