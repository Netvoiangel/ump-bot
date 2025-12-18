import time
import logging

from src.ump_bot.telegram_bot import main

logger = logging.getLogger("ump_bot")


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            logger.exception("Bot crashed, restarting in 5 seconds: %s", e)
            time.sleep(5)
