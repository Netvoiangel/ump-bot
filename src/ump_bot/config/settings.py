from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # UMP
    ump_base_url: str = Field("http://ump.piteravto.ru", alias="UMP_BASE_URL")
    ump_user: str = Field("", alias="UMP_USER")
    ump_pass: str = Field("", alias="UMP_PASS")
    ump_token_file: str = Field("var/ump_token.txt", alias="UMP_TOKEN_FILE")
    ump_cookies_file: str = Field("var/ump_cookies.txt", alias="UMP_COOKIES")
    ump_tz_offset: str = Field("180", alias="UMP_TIMEZONE_OFFSET")
    request_timeout: float = Field(20.0, alias="REQUEST_TIMEOUT")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    # User auth data
    user_token_dir: str = Field("var/user_tokens", alias="USER_TOKEN_DIR")
    user_cookies_dir: str = Field("var/user_cookies", alias="USER_COOKIES_DIR")
    user_creds_dir: str = Field("var/user_creds", alias="USER_CREDS_DIR")
    user_meta_dir: str = Field("var/user_meta", alias="USER_META_DIR")
    ump_branch_map: dict = Field(default_factory=dict, alias="UMP_BRANCH_MAP")
    ump_user_id: Optional[str] = Field(None, alias="UMP_USER_ID")

    # Caching / stability
    cache_dir: str = Field("var/cache", alias="CACHE_DIR")
    cache_ttl_sec: int = Field(120, alias="CACHE_TTL")
    anti_flap_grace_m: float = Field(3.0, alias="ANTI_FLAP_GRACE_M")

    # Bot / map
    bot_token: str = Field("", alias="TELEGRAM_BOT_TOKEN")
    allowed_user_ids_raw: str = Field("", alias="TELEGRAM_ALLOWED_USERS")
    vehicles_file: str = Field("src/ump_bot/data/vehicles.sample.txt", alias="VEHICLES_FILE")
    parks_file: str = Field("src/ump_bot/data/parks.json", alias="PARKS_FILE")
    map_out_dir: str = Field("out", alias="MAP_OUT_DIR")
    map_cache_dir: str = Field("var/tile_cache", alias="MAP_CACHE_DIR")
    max_image_size_mb: int = Field(10, alias="MAX_IMAGE_SIZE_MB")
    map_provider: str = Field("", alias="MAP_PROVIDER")
    map_user_agent: str = Field("", alias="MAP_USER_AGENT")
    map_referer: str = Field("", alias="MAP_REFERER")
    map_api_key: str = Field("", alias="MAPTILER_API_KEY")
    map_tps: float = Field(3.0, alias="MAP_TPS")
    map_zoom: int = Field(17, alias="MAP_ZOOM")

    @property
    def allowed_user_ids(self) -> List[str]:
        return [u for u in self.allowed_user_ids_raw.split(",") if u] if self.allowed_user_ids_raw else []

    @property
    def max_image_size_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
