from pathlib import Path

from .settings import settings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def _ensure_parent_dir(path: str):
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)


def _ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)


UMP_BASE_URL = settings.ump_base_url.rstrip("/")
UMP_USER = settings.ump_user
UMP_PASS = settings.ump_pass
UMP_TOKEN_FILE = settings.ump_token_file
UMP_COOKIES_FILE = settings.ump_cookies_file
PARKS_FILE = settings.parks_file
VEHICLES_FILE = settings.vehicles_file
UMP_TZ_OFFSET = settings.ump_tz_offset
REQUEST_TIMEOUT = settings.request_timeout
LOG_LEVEL = settings.log_level.upper()

# --- Пользовательские данные авторизации ---
USER_TOKEN_DIR = settings.user_token_dir
USER_COOKIES_DIR = settings.user_cookies_dir
UMP_BRANCH_MAP = settings.ump_branch_map
UMP_USER_ID = settings.ump_user_id
USER_CREDS_DIR = settings.user_creds_dir
USER_META_DIR = settings.user_meta_dir

# --- Caching / Stability ---
CACHE_DIR = settings.cache_dir
CACHE_TTL_SEC = settings.cache_ttl_sec
ANTI_FLAP_GRACE_M = settings.anti_flap_grace_m

_ensure_parent_dir(UMP_TOKEN_FILE)
_ensure_parent_dir(UMP_COOKIES_FILE)
_ensure_parent_dir(CACHE_DIR)
_ensure_dir(USER_TOKEN_DIR)
_ensure_dir(USER_COOKIES_DIR)
_ensure_dir(USER_CREDS_DIR)
_ensure_dir(USER_META_DIR)
_ensure_dir(DATA_DIR)
