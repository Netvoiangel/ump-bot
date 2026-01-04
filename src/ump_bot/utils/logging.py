import logging
import sys


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Инициализирует базовое логирование в stdout/stderr."""
    logging.basicConfig(
        format="%(asctime)s - [%(levelname)s] %(name)s: %(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.StreamHandler(sys.stderr),
        ],
        force=True,
    )
    # Важно: http-клиенты (httpx/httpcore) могут логировать URL, включая токен Telegram в пути.
    # Чтобы не светить секреты в логах, держим их на WARNING+.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logger = logging.getLogger("ump_bot")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


def log_print(logger: logging.Logger, msg: str, level: str = "INFO") -> None:
    """Дублирует логи в print для гарантированной видимости."""
    print(f"[{level}] {msg}", file=sys.stderr, flush=True)
    level_upper = level.upper()
    if level_upper == "ERROR":
        logger.error(msg)
    elif level_upper == "WARNING":
        logger.warning(msg)
    else:
        logger.info(msg)
