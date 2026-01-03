import time
import logging

from src.ump_bot.telegram_bot import main

logger = logging.getLogger("ump_bot")


if __name__ == "__main__":
    while True:
        try:
            main()
            # application.run_polling() возвращается при штатной остановке (SIGTERM/SIGINT или stop).
            # В контейнере/systemd перезапуском должен заниматься оркестратор, а не внутренний цикл.
            logger.warning("Bot stopped (main() returned). Exiting.")
            raise SystemExit(0)
        except (SystemExit, KeyboardInterrupt):
            # Не перехватываем штатное завершение: иначе получаем «Event loop is closed»
            # и контейнер может быть принудительно убит (Exited 137).
            raise
        except Exception as e:
            logger.exception("Bot crashed, restarting in 5 seconds: %s", e)
            # Важно: python-telegram-bot может закрыть event loop при падении/остановке.
            # Перед перезапуском создаём новый loop, иначе add_signal_handler() упадёт.
            try:
                import asyncio

                asyncio.set_event_loop(asyncio.new_event_loop())
            except Exception:
                pass
            time.sleep(5)
