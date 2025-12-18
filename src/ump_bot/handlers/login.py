from telegram import Update
from telegram.ext import ContextTypes

from ..services import auth
from ..services.settings import ALLOWED_USER_IDS
from .access import reply_private


async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запуск ручной авторизации в UMP"""
    if not auth.check_access(update.effective_user.id, ALLOWED_USER_IDS):
        await reply_private(update)
        return
    await auth._prompt_login(update)
