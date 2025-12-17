import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from ..services import auth
from ..services.diagnostic import (
    fetch_branch_diagnostics,
    extract_red_issues,
    format_issues_compact,
    extract_user_id_from_token,
    filter_issues_with_details,
    _resolve_branch_id,
    _known_branches_text,
)
from ..services.settings import ALLOWED_USER_IDS
from ..config import UMP_USER_ID
from ..utils.logging import log_print

logger = logging.getLogger("ump_bot")


async def diag_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /diag [филиал]"""
    if not auth.check_access(update.effective_user.id, ALLOWED_USER_IDS):
        return

    args = context.args or []
    branch_name = " ".join(args).strip() if args else None
    branch_id = _resolve_branch_id(branch_name) if branch_name else None

    token_path = await auth.ensure_user_authenticated(update)
    if not token_path:
        return

    try:
        user_token = auth._load_saved_token(update.effective_user.id)
        inferred_id = extract_user_id_from_token(user_token) if user_token else None
        if inferred_id:
            log_print(logger, f"diag: user_id from token: {inferred_id}")

        if branch_name and branch_id is None:
            await update.message.reply_text(
                f"❌ Неизвестный филиал '{branch_name}'. {_known_branches_text()}"
            )
            return

        if branch_id is None:
            await update.message.reply_text(
                "❌ Укажите филиал. Пример: /diag Екатерининский\n" + _known_branches_text()
            )
            return

        uid = inferred_id or (int(UMP_USER_ID) if UMP_USER_ID else None)
        if not uid:
            await update.message.reply_text("❌ Не задан user_id (env UMP_USER_ID) и не удалось извлечь из токена.")
            return

        raw = fetch_branch_diagnostics(branch_id=branch_id, token_path=token_path, user_id=uid)
        issues = filter_issues_with_details(raw, token_path=token_path, user_id=uid)
        red = extract_red_issues(issues)
        text = format_issues_compact(red)
        await update.message.reply_text(text)
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}")
    except Exception as e:
        log_print(logger, f"Ошибка /diag: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка диагностики: {e}")


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /test - диагностика"""
    if not auth.check_access(update.effective_user.id, ALLOWED_USER_IDS):
        return

    log_print(logger, "=== TEST COMMAND ВЫЗВАН ===")

    info_lines = []
    info_lines.append("🔍 ДИАГНОСТИКА БОТА\n")
    user_id = update.effective_user.id

    # Проверка конфигурации
    from ..services import settings

    info_lines.append(f"✅ BOT_TOKEN: {'установлен' if settings.BOT_TOKEN else 'НЕ УСТАНОВЛЕН'}")
    info_lines.append(f"📁 VEHICLES_FILE: {settings.VEHICLES_FILE} ({'существует' if settings.VEHICLES_FILE and os.path.exists(settings.VEHICLES_FILE) else 'НЕ СУЩЕСТВУЕТ'})")
    info_lines.append(f"📁 OUT_DIR: {settings.OUT_DIR} ({'существует' if os.path.exists(settings.OUT_DIR) else 'НЕ СУЩЕСТВУЕТ'})")
    info_lines.append(f"📁 CACHE_DIR: {settings.CACHE_DIR}")

    token_path = auth._user_token_path(user_id)
    info_lines.append(f"\n🔑 ТОКЕН UMP (user={user_id}):")
    info_lines.append(f"   Путь: {token_path}")
    info_lines.append(f"   Существует: {'ДА' if token_path.exists() else 'НЕТ'}")
    if token_path.exists():
        try:
            with open(token_path, "r") as f:
                token = f.read().strip()
                info_lines.append(f"   Длина: {len(token)} символов")
        except Exception as e:
            info_lines.append(f"   Ошибка чтения: {e}")
    else:
        info_lines.append("   Требуется авторизация через /login")

    # Проверка парков
    from ..infra.otbivka import load_parks

    try:
        parks = load_parks()
        info_lines.append(f"\n🏢 ПАРКИ: найдено {len(parks)}")
        for p in parks:
            info_lines.append(f"   - {p['name']}")
    except Exception as e:
        info_lines.append(f"\n🏢 ПАРКИ: ошибка загрузки - {e}")

    # Проверка vehicles.txt
    from ..infra.render_map import parse_vehicles_file_with_sections

    if settings.VEHICLES_FILE and os.path.exists(settings.VEHICLES_FILE):
        try:
            sections = parse_vehicles_file_with_sections(settings.VEHICLES_FILE)
            total = sum(len(nums) for nums in sections.values())
            info_lines.append(f"\n🚌 VEHICLES.TXT:")
            info_lines.append(f"   Всего ТС: {total}")
            info_lines.append(f"   Категорий: {len(sections)}")
            for cat, nums in list(sections.items())[:3]:
                info_lines.append(f"   - {cat}: {len(nums)} ТС")
        except Exception as e:
            info_lines.append(f"\n🚌 VEHICLES.TXT: ошибка парсинга - {e}")

    from ..services.state import user_park_cache

    selected_park = user_park_cache.get(user_id)
    info_lines.append(f"\n📍 ВЫБРАННЫЙ ПАРК: {selected_park or 'не выбран (все)'}")

    response = "\n".join(info_lines)
    log_print(logger, f"TEST RESPONSE:\n{response}")
    await update.message.reply_text(response)
