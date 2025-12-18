import time
import logging

from src.ump_bot.telegram_bot import main

logger = logging.getLogger("ump_bot")


if __name__ == "__main__":
    while True:
        try:
            main()
            logger.error("Bot stopped (main() returned). Restarting in 5 seconds.")
            time.sleep(5)
        except BaseException as e:
            # В контейнере python-telegram-bot может завершать процесс через SystemExit/KeyboardInterrupt
            # при сигнале/внутреннем stop. Здесь перезапускаем, чтобы бот не «засыпал».
            logger.exception("Bot stopped unexpectedly, restarting in 5 seconds: %s", e)
            time.sleep(5)
