from __future__ import annotations

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from .config import LOG_LEVEL
from .infra.login_token import login_with_credentials
from .infra.otbivka import get_position_and_check
from .infra.render_map import render_parks_with_vehicles
from .services import auth
from .services.settings import BOT_TOKEN
from .handlers import start as start_handlers
from .handlers import map as map_handlers
from .handlers import status as status_handlers
from .handlers import login as login_handlers
from .handlers import diagnostics as diag_handlers
from .handlers import admin as admin_handlers
from .handlers import access as access_handlers
from .utils.logging import configure_logging, log_print

logger = configure_logging(LOG_LEVEL)

# re-exports for тестов и обратной совместимости
auth_flow_stage = auth.auth_flow_stage
auth_flow_data = auth.auth_flow_data
user_sessions = auth.user_sessions
_token_file_valid = auth._token_file_valid
_prompt_login = auth._prompt_login
_reset_auth_flow = auth._reset_auth_flow
_ensure_user_authenticated = auth.ensure_user_authenticated
_user_token_path = auth._user_token_path
_user_cookies_path = auth._user_cookies_path
_load_saved_token = auth._load_saved_token
check_access = auth.check_access

render_map_with_numbers = map_handlers.render_map_with_numbers
text_handler = map_handlers.text_handler
map_command = map_handlers.map_command
status_command = status_handlers.status_command
diag_command = diag_handlers.diag_command
test_command = diag_handlers.test_command
start = start_handlers.start
help_command = start_handlers.help_command
parks_command = start_handlers.parks_command
park_callback = start_handlers.park_callback
login_command = login_handlers.login_command
admin_command = admin_handlers.admin_command
admin_callback = admin_handlers.admin_callback
access_callback = access_handlers.access_callback

# для monkeypatch в тестах
login_with_credentials = login_with_credentials
render_parks_with_vehicles = render_parks_with_vehicles
get_position_and_check = get_position_and_check


def main() -> None:
    log_print(logger, "=" * 60)
    log_print(logger, "ЗАПУСК БОТА")
    log_print(logger, "=" * 60)

    if not BOT_TOKEN:
        log_print(logger, "TELEGRAM_BOT_TOKEN не установлен в .env", "ERROR")
        return

    application = Application.builder().token(BOT_TOKEN).concurrent_updates(8).build()

    def _on_error(update: object, context) -> None:
        # Никогда не даём исключениям "молчаливо" уронить обработку.
        try:
            logger.exception("Unhandled error while processing update: %s", context.error)
        except Exception:
            pass

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("diag", diag_command))
    application.add_handler(CommandHandler("parks", parks_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("map", map_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(park_callback, pattern="^park_"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(access_callback, pattern="^access_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    application.add_error_handler(_on_error)

    log_print(logger, "Обработчики зарегистрированы, запускаю polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
