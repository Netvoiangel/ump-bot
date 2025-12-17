from telegram import Update
from telegram.ext import ContextTypes

from ..services import auth
from ..services.settings import ALLOWED_USER_IDS


async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запуск ручной авторизации в UMP"""
    if not auth.check_access(update.effective_user.id, ALLOWED_USER_IDS):
        return
    await auth._prompt_login(update)
