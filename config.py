# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  

def _ensure_parent_dir(path: str):
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)

UMP_BASE_URL        = os.getenv("UMP_BASE_URL", "http://ump.piteravto.ru").rstrip("/")
UMP_USER            = os.getenv("UMP_USER", "")
UMP_PASS            = os.getenv("UMP_PASS", "")
UMP_TOKEN_FILE      = os.getenv("UMP_TOKEN_FILE", ".secrets/ump_token.txt")
UMP_COOKIES_FILE    = os.getenv("UMP_COOKIES", ".secrets/ump_cookies.txt")
PARKS_FILE          = os.getenv("PARKS_FILE", "parks.json")
UMP_TZ_OFFSET       = os.getenv("UMP_TIMEZONE_OFFSET", "180")
REQUEST_TIMEOUT     = float(os.getenv("REQUEST_TIMEOUT", "20"))
LOG_LEVEL           = os.getenv("LOG_LEVEL", "INFO").upper()

# --- Caching / Stability ---
CACHE_DIR           = os.getenv("CACHE_DIR", ".secrets/cache")
CACHE_TTL_SEC       = int(os.getenv("CACHE_TTL", "120"))
ANTI_FLAP_GRACE_M   = float(os.getenv("ANTI_FLAP_GRACE_M", "3"))

_ensure_parent_dir(UMP_TOKEN_FILE)
_ensure_parent_dir(UMP_COOKIES_FILE)
_ensure_parent_dir(CACHE_DIR)
