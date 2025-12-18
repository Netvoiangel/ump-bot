import logging

from telegram import Update
from telegram.ext import ContextTypes

from ..config import VEHICLES_FILE as CONFIG_VEHICLES_FILE
from ..infra.login_token import login_with_credentials
from ..services import auth
from ..services.map import render_map_with_numbers
from ..services.settings import (
    ALLOWED_USER_IDS,
    OUT_DIR,
    CACHE_DIR,
    MAX_IMAGE_SIZE,
    TILE_PROVIDER,
    TILE_USER_AGENT,
    TILE_REFERER,
    TILE_APIKEY,
    TILE_RATE_TPS,
    MAP_ZOOM,
    VEHICLES_FILE as ENV_VEHICLES_FILE,
)
from ..services.state import user_park_cache
from ..services.vehicles import deduplicate_numbers, is_valid_depot_number, parse_sections_from_text
from ..utils.logging import log_print

logger = logging.getLogger("ump_bot")
VEHICLES_FILE = ENV_VEHICLES_FILE or CONFIG_VEHICLES_FILE


async def map_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /map - рендер карты ТОЛЬКО с явно переданными номерами"""
    log_print(logger, "=" * 50)
    log_print(logger, "map_command вызван")

    if not auth.check_access(update.effective_user.id, ALLOWED_USER_IDS):
        log_print(logger, f"Доступ запрещен для user={update.effective_user.id}", "WARNING")
        return

    user_id = update.effective_user.id
    selected_park = user_park_cache.get(user_id)
    log_print(logger, f"map_command: user={user_id}, park={selected_park}, args={context.args}")

    token_path = await auth.ensure_user_authenticated(update)
    if not token_path:
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Укажите номера ТС. Пример: /map 6683 6719 6306\n\n"
            "Или просто отправьте текст с задачами (без команды /map)"
        )
        return

    depot_numbers = deduplicate_numbers(
        [d for d in context.args if is_valid_depot_number(d)]
    )

    if not depot_numbers:
        await update.message.reply_text(
            "❌ Не найдено валидных номеров ТС в аргументах.\n"
            "Пример: /map 6683 6719 6306"
        )
        return

    await render_map_with_numbers(
        logger=logger,
        update=update,
        depot_numbers=depot_numbers,
        selected_park=selected_park,
        sections=None,
        token_path=token_path,
        out_dir=OUT_DIR,
        max_image_size=MAX_IMAGE_SIZE,
        tile_provider=TILE_PROVIDER,
        tile_cache=CACHE_DIR,
        tile_user_agent=TILE_USER_AGENT,
        tile_referer=TILE_REFERER,
        tile_apikey=TILE_APIKEY,
        tile_rate_tps=TILE_RATE_TPS,
        zoom=MAP_ZOOM,
    )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений: логин-диалог и форматы vehicles.txt"""
    if not auth.check_access(update.effective_user.id, ALLOWED_USER_IDS):
        return

    user_id = update.effective_user.id
    text = (update.message.text or "").strip()

    # ---- Диалог авторизации ----
    stage = auth.auth_flow_stage.get(user_id)
    if stage == "await_login":
        auth.auth_flow_data.setdefault(user_id, {})["username"] = text
        auth.auth_flow_stage[user_id] = "await_password"
        await update.message.reply_text("Введите пароль UMP:")
        return

    if stage == "await_password":
        auth.auth_flow_data.setdefault(user_id, {})["password"] = text
        creds = auth.auth_flow_data.get(user_id, {})
        username = creds.get("username")
        password = creds.get("password")

        if not username or not password:
            auth._reset_auth_flow(user_id)
            await update.message.reply_text("❌ Ошибка: логин или пароль пустые. Попробуйте /login заново.")
            return

        token_path = auth._user_token_path(user_id)
        cookies_path = auth._user_cookies_path(user_id)

        try:
            tok = login_with_credentials(
                username=username,
                password=password,
                token_path=str(token_path),
                cookies_path=str(cookies_path),
            )
            auth._save_user_session(
                user_id, username=username, password=password, token=tok
            )
            auth._reset_auth_flow(user_id)
            await update.message.reply_text("✅ UMP-аккаунт подключен. Автополучение токена включено. Используйте /map или /status.")
        except Exception as e:
            log_print(logger, f"Ошибка авторизации: {e}", "ERROR")
            await update.message.reply_text(f"❌ Ошибка авторизации: {e}")
        return

    # ---- Парсинг текста задач ----
    token_path = await auth.ensure_user_authenticated(update)
    if not token_path:
        return

    try:
        sections = parse_sections_from_text(text)
        depot_numbers = deduplicate_numbers([n for nums in sections.values() for n in nums])
        if not depot_numbers:
            await update.message.reply_text("❌ Не найдено валидных номеров ТС в тексте.")
            return

        await render_map_with_numbers(
            logger=logger,
            update=update,
            depot_numbers=depot_numbers,
            selected_park=user_park_cache.get(update.effective_user.id),
            sections=sections,
            token_path=token_path,
            out_dir=OUT_DIR,
            max_image_size=MAX_IMAGE_SIZE,
            tile_provider=TILE_PROVIDER,
            tile_cache=CACHE_DIR,
            tile_user_agent=TILE_USER_AGENT,
            tile_referer=TILE_REFERER,
            tile_apikey=TILE_APIKEY,
            tile_rate_tps=TILE_RATE_TPS,
            zoom=MAP_ZOOM,
        )

    except Exception as e:
        log_print(logger, f"Error parsing text: {e}", "ERROR")
        import traceback
        log_print(logger, traceback.format_exc(), "ERROR")
        await update.message.reply_text(f"❌ Ошибка парсинга текста: {str(e)}")
