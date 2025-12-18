import logging

import asyncio
import requests
from telegram import Update
from telegram.ext import ContextTypes

from ..infra.otbivka import get_position_and_check
from ..services import auth
from ..services.settings import ALLOWED_USER_IDS
from ..utils.logging import log_print

logger = logging.getLogger("ump_bot")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /status [номер]"""
    if not auth.check_access(update.effective_user.id, ALLOWED_USER_IDS):
        return

    if not context.args:
        await update.message.reply_text("❌ Укажите номер ТС. Пример: /status 6569")
        return

    depot_number = context.args[0]
    token_path = await auth.ensure_user_authenticated(update)
    if not token_path:
        return

    try:
        result = await asyncio.to_thread(get_position_and_check, depot_number, token_path=token_path)

        if not result.get("ok"):
            error = result.get("error", "unknown")
            await update.message.reply_text(f"❌ Ошибка: {error}")
            return

        in_park = "✅ В парке" if result.get("in_park") else "❌ Вне парка"
        park_name = result.get("park_name", "—")

        text = (
            f"🚌 ТС {result.get('depot_number')}\n\n"
            f"📍 Статус: {in_park}\n"
            f"🏢 Парк: {park_name}\n"
            f"🆔 ID: {result.get('vehicle_id')}\n"
            f"⏰ Время: {result.get('time', '—')}\n"
            f"🌐 Координаты:\n"
            f"   Lat: {result.get('lat', 0):.6f}\n"
            f"   Lon: {result.get('lon', 0):.6f}"
        )

        await update.message.reply_text(text)
    except FileNotFoundError as e:
        logger.error(f"Token file not found: {e}", exc_info=True)
        await update.message.reply_text("❌ Нет токена UMP. Используйте /login для авторизации.")
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        logger.error(f"HTTP error in status_command: {status}", exc_info=True)
        if status == 401:
            # пробуем автологин по сохранённым учётным данным, без запроса пароля
            new_path = auth.refresh_session(update.effective_user.id)
            if new_path:
                try:
                    result = await asyncio.to_thread(get_position_and_check, depot_number, token_path=new_path)
                    in_park = "✅ В парке" if result.get("in_park") else "❌ Вне парка"
                    park_name = result.get("park_name", "—")
                    text = (
                        f"🚌 ТС {result.get('depot_number')}\n\n"
                        f"📍 Статус: {in_park}\n"
                        f"🏢 Парк: {park_name}\n"
                        f"🆔 ID: {result.get('vehicle_id')}\n"
                        f"⏰ Время: {result.get('time', '—')}\n"
                        f"🌐 Координаты:\n"
                        f"   Lat: {result.get('lat', 0):.6f}\n"
                        f"   Lon: {result.get('lon', 0):.6f}"
                    )
                    await update.message.reply_text(text)
                    return
                except Exception as e2:
                    log_print(logger, f"Автологин выполнен, но повторный запрос не удался: {e2}", "ERROR")
            await update.message.reply_text("❌ Сессия UMP истекла. Введите /login для повторной авторизации.")
        else:
            await update.message.reply_text(f"❌ HTTP ошибка {status}: {e}")
    except Exception as e:
        logger.error(f"Error in status_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
