# login_token.py
import json
from pathlib import Path
from typing import Optional

import requests
from http.cookiejar import MozillaCookieJar

from config import UMP_BASE_URL, UMP_USER, UMP_PASS, UMP_COOKIES_FILE, UMP_TOKEN_FILE, REQUEST_TIMEOUT


def _extract_token(response: requests.Response) -> str:
    """Достает токен из тела или заголовков ответа."""
    token: Optional[str] = None
    try:
        data = response.json()
        token = data.get("token") or data.get("auth") or data.get("accessToken")
        if not token and isinstance(data.get("data"), dict):
            token = data["data"].get("token")
    except Exception:
        token = None
    token = token or response.headers.get("token") or response.headers.get("auth")
    if not token:
        raise RuntimeError("Логин выполнен, но токен в ответе не найден")
    return token.strip()


def login_with_credentials(
    username: str,
    password: str,
    token_path: Optional[str] = None,
    cookies_path: Optional[str] = None,
) -> str:
    """
    Авторизуется в UMP с указанными учетными данными и возвращает токен.

    Args:
        username: логин UMP
        password: пароль UMP
        token_path: если указан — сохранить токен в файл
        cookies_path: если указано — сохранить cookies в файл
    """
    if not username or not password:
        raise ValueError("Не заданы логин и пароль UMP")

    session = requests.Session()
    if cookies_path:
        session.cookies = MozillaCookieJar(cookies_path)

    session.headers.update({
        "User-Agent": "UMPClient/1.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": UMP_BASE_URL,
        "Referer": f"{UMP_BASE_URL}/",
    })

    response = session.post(
        f"{UMP_BASE_URL}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    token = _extract_token(response)

    if token_path:
        path = Path(token_path)
        if path.parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(token, encoding="utf-8")

    if cookies_path:
        try:
            session.cookies.save(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass

    return token


def login_and_save(
    username: Optional[str] = None,
    password: Optional[str] = None,
    token_path: Optional[str] = None,
    cookies_path: Optional[str] = None,
) -> str:
    """
    Обратная совместимость: пытается использовать переданные или окружение UMP_USER/UMP_PASS.
    """
    user = username or UMP_USER
    pwd = password or UMP_PASS
    return login_with_credentials(
        user,
        pwd,
        token_path=token_path or UMP_TOKEN_FILE,
        cookies_path=cookies_path or UMP_COOKIES_FILE,
    )


if __name__ == "__main__":
    # CLI: использует данные из окружения, если они заданы
    login_and_save()
