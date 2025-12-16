# config.py
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _ensure_parent_dir(path: str):
    """Создает родительский каталог для файла, если его еще нет."""
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)


def _ensure_dir(path: str):
    """Создает каталог, если его еще нет."""
    Path(path).mkdir(parents=True, exist_ok=True)


def _load_json_env(name: str, default: str = "{}"):
    """Безопасно читает JSON из переменной окружения."""
    try:
        return json.loads(os.getenv(name, default))
    except Exception:
        return {}

UMP_BASE_URL      = os.getenv("UMP_BASE_URL", "http://ump.piteravto.ru").rstrip("/")
UMP_USER          = os.getenv("UMP_USER", "")
UMP_PASS          = os.getenv("UMP_PASS", "")
UMP_TOKEN_FILE    = os.getenv("UMP_TOKEN_FILE", ".secrets/ump_token.txt")
UMP_COOKIES_FILE  = os.getenv("UMP_COOKIES", ".secrets/ump_cookies.txt")
PARKS_FILE        = os.getenv("PARKS_FILE", "parks.json")
UMP_TZ_OFFSET     = os.getenv("UMP_TIMEZONE_OFFSET", "180")
REQUEST_TIMEOUT   = float(os.getenv("REQUEST_TIMEOUT", "20"))
LOG_LEVEL         = os.getenv("LOG_LEVEL", "INFO").upper()

# --- Пользовательские данные авторизации ---
USER_TOKEN_DIR   = os.getenv("USER_TOKEN_DIR", ".secrets/user_tokens")
USER_COOKIES_DIR = os.getenv("USER_COOKIES_DIR", ".secrets/user_cookies")
UMP_BRANCH_MAP   = _load_json_env("UMP_BRANCH_MAP", "{}")  # {"Екатерининский": 1382, ...}
UMP_USER_ID      = os.getenv("UMP_USER_ID")  # числовой ID пользователя UMP (для diag)
USER_META_DIR    = os.getenv("USER_META_DIR", ".secrets/user_meta")

# --- Caching / Stability ---
CACHE_DIR         = os.getenv("CACHE_DIR", ".secrets/cache")
CACHE_TTL_SEC     = int(os.getenv("CACHE_TTL", "120"))
ANTI_FLAP_GRACE_M = float(os.getenv("ANTI_FLAP_GRACE_M", "3"))

_ensure_parent_dir(UMP_TOKEN_FILE)
_ensure_parent_dir(UMP_COOKIES_FILE)
_ensure_parent_dir(CACHE_DIR)
_ensure_dir(USER_TOKEN_DIR)
_ensure_dir(USER_COOKIES_DIR)
_ensure_dir(USER_META_DIR)
