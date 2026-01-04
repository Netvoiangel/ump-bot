import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ..infra.otbivka import load_parks
from ..services import auth
from ..services.settings import ADMIN_USER_ID, ALLOWED_USER_IDS
from ..services.state import user_park_cache
from ..utils.logging import log_print
from .access import reply_private

logger = logging.getLogger("ump_bot")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    if not auth.check_access(update.effective_user.id, ALLOWED_USER_IDS):
        await reply_private(update)
        return

    user_id = update.effective_user.id
    parks = load_parks()
    park_names = [p["name"] for p in parks]

    text = (
        "🚌 Бот для отслеживания ТС в парках\n\n"
        "Доступные команды:\n"
        "/map - Карта парка с ТС\n"
        "/parks - Список парков\n"
        "/status [номер] - Статус ТС\n"
        "/login - Подключить UMP-аккаунт\n"
        "/diag [филиал] - Ошибки оборудования по филиалу\n"
        "/help - Справка\n\n"
    )

    if update.effective_user and int(update.effective_user.id) == int(ADMIN_USER_ID):
        text += "/admin - Админ‑панель\n\n"

    if user_id in user_park_cache:
        text += f"📍 Выбранный парк: {user_park_cache[user_id]}\n"

    await update.message.reply_text(text)

    if not auth._user_token_ready(user_id):
        await auth._prompt_login(update)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help"""
    if not auth.check_access(update.effective_user.id, ALLOWED_USER_IDS):
        await reply_private(update)
        return

    text = (
        "📖 Справка по командам:\n\n"
        "/start - Начать работу\n"
        "/map - Показать карту парка с ТС\n"
        "/parks - Выбрать парк\n"
        "/status [номер] - Проверить статус ТС\n"
        "/diag [филиал] - Ошибки оборудования\n"
        "/login - Авторизоваться в UMP\n"
    )
    if update.effective_user and int(update.effective_user.id) == int(ADMIN_USER_ID):
        text += "/admin - Админ‑панель\n"
    text += (
        "/help - Эта справка\n\n"
        "Примеры:\n"
        "/status 6569\n"
        "/map 6177 6848\n"
    )
    await update.message.reply_text(text)


async def parks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /parks - выбор парка"""
    if not auth.check_access(update.effective_user.id, ALLOWED_USER_IDS):
        await reply_private(update)
        return

    parks = load_parks()
    if not parks:
        await update.message.reply_text("❌ Парки не найдены в конфигурации.")
        return

    keyboard = []
    for park in parks:
        keyboard.append(
            [
                InlineKeyboardButton(
                    park["name"],
                    callback_data=f"park_{park['name']}"
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("Все парки", callback_data="park_all")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    current_park = user_park_cache.get(update.effective_user.id, "не выбран")
    text = f"📍 Выберите парк:\n\nТекущий: {current_park}"

    await update.message.reply_text(text, reply_markup=reply_markup)


async def park_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка выбора парка"""
    query = update.callback_query
    await query.answer()

    if not auth.check_access(query.from_user.id, ALLOWED_USER_IDS):
        await query.edit_message_text("❌ Доступ запрещен.")
        return

    park_name = query.data.replace("park_", "")
    user_id = query.from_user.id

    if park_name == "all":
        if user_id in user_park_cache:
            del user_park_cache[user_id]
        await query.edit_message_text("✅ Выбраны все парки")
    else:
        user_park_cache[user_id] = park_name
        await query.edit_message_text(f"✅ Выбран парк: {park_name}")
