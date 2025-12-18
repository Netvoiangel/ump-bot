from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from telegram import Update

from ..config import (
    USER_TOKEN_DIR,
    USER_COOKIES_DIR,
    USER_CREDS_DIR,
    USER_META_DIR,
)
from ..infra.login_token import login_with_credentials
from ..utils.logging import log_print

logger = logging.getLogger("ump_bot")


# Состояние авторизации пользователей
@dataclass
class UserSession:
    username: str
    password: Optional[str]
    token: str
    token_path: str
    cookies_path: str


user_sessions: Dict[int, UserSession] = {}
# auth_flow_stage: user_id -> "await_login" | "await_password"
auth_flow_stage: Dict[int, str] = {}
auth_flow_data: Dict[int, Dict[str, str]] = {}


def check_access(user_id: int, allowed_user_ids: Optional[list[str]]) -> bool:
    if not allowed_user_ids:
        return True
    return str(user_id) in allowed_user_ids


def _reset_auth_flow(user_id: int) -> None:
    auth_flow_stage.pop(user_id, None)
    auth_flow_data.pop(user_id, None)


def _token_file_valid(path: Path) -> bool:
    try:
        return path.exists() and bool(path.read_text(encoding="utf-8").strip())
    except Exception:
        return False


def _user_token_ready(user_id: int) -> bool:
    return _token_file_valid(_user_token_path(user_id))


def _user_creds_path(user_id: int) -> Path:
    return Path(USER_CREDS_DIR) / f"{user_id}_creds.json"


def _load_user_creds(user_id: int) -> Optional[Dict[str, str]]:
    path = _user_creds_path(user_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("username") and data.get("password"):
            return data
    except Exception:
        return None
    return None


def _save_user_creds(user_id: int, username: str, password: str) -> None:
    path = _user_creds_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"username": username, "password": password}), encoding="utf-8")


def _user_token_path(user_id: int) -> Path:
    return Path(USER_TOKEN_DIR) / f"{user_id}_token.txt"


def _user_cookies_path(user_id: int) -> Path:
    return Path(USER_COOKIES_DIR) / f"{user_id}_cookies.txt"


def _load_saved_token(user_id: int) -> Optional[str]:
    token_file = _user_token_path(user_id)
    if token_file.exists():
        try:
            tok = token_file.read_text(encoding="utf-8").strip()
            if tok:
                return tok
        except Exception:
            return None
    return None


def _save_user_session(user_id: int, username: str, password: Optional[str], token: str) -> None:
    token_path = str(_user_token_path(user_id))
    cookies_path = str(_user_cookies_path(user_id))
    user_sessions[user_id] = UserSession(
        username=username,
        password=password,
        token=token,
        token_path=token_path,
        cookies_path=cookies_path,
    )
    if password:
        _save_user_creds(user_id, username, password)
    # Пишем токен сразу в файл, чтобы следующие команды его видели
    try:
        Path(token_path).parent.mkdir(parents=True, exist_ok=True)
        Path(token_path).write_text(token, encoding="utf-8")
    except Exception as e:
        log_print(logger, f"Не удалось записать токен в {token_path}: {e}", "ERROR")


def _try_autologin(user_id: int) -> Optional[str]:
    creds = _load_user_creds(user_id)
    if not creds:
        return None
    username = creds["username"]
    password = creds["password"]
    token_path = _user_token_path(user_id)
    cookies_path = _user_cookies_path(user_id)
    try:
        tok = login_with_credentials(
            username=username,
            password=password,
            token_path=str(token_path),
            cookies_path=str(cookies_path),
        )
        _save_user_session(user_id, username=username, password=password, token=tok)
        return str(token_path)
    except Exception as e:
        log_print(logger, f"Автологин не удался: {e}", "ERROR")
        return None


def refresh_session(user_id: int) -> Optional[str]:
    """
    Пытается обновить UMP-сессию пользователя по сохранённым учётным данным.
    Возвращает путь к файлу токена при успехе.
    """
    return _try_autologin(user_id)


async def _prompt_login(update: Update) -> None:
    """Запускает диалог авторизации: сначала логин, потом пароль."""
    user_id = update.effective_user.id
    _reset_auth_flow(user_id)
    auth_flow_stage[user_id] = "await_login"
    auth_flow_data[user_id] = {}
    await update.message.reply_text(
        "🔐 Для работы бота подключите свой UMP-аккаунт.\n"
        "Введите логин UMP:"
    )


async def ensure_user_authenticated(update: Update) -> Optional[str]:
    """Проверяет наличие токена пользователя. Если нет — запускает запрос логина."""
    user_id = update.effective_user.id
    token_path = _user_token_path(user_id)
    if _token_file_valid(token_path):
        return str(token_path)
    # если токен есть в памяти — пытаемся сохранить и использовать
    session = user_sessions.get(user_id)
    if session and session.token:
        try:
            Path(session.token_path).parent.mkdir(parents=True, exist_ok=True)
            Path(session.token_path).write_text(session.token, encoding="utf-8")
            return session.token_path
        except Exception as e:
            log_print(logger, f"Не удалось восстановить токен из памяти: {e}", "ERROR")
    # пробуем автологин по сохранённым учетным данным
    autologin_path = _try_autologin(user_id)
    if autologin_path:
        await update.message.reply_text("✅ Сессия UMP обновлена автоматически.")
        return autologin_path
    await update.message.reply_text("ℹ️ Нужна авторизация в UMP. Введите /login.")
    await _prompt_login(update)
    return None
