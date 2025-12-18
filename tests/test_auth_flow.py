import asyncio
from types import SimpleNamespace
from pathlib import Path

import pytest

from src.ump_bot import telegram_bot
from src.ump_bot.services import auth
from src.ump_bot.handlers import map as map_handlers
from src.ump_bot.services import map as map_service


class DummyMessage:
    def __init__(self, text: str = ""):
        self.text = text
        self.replies = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append(text)


class DummyUpdate:
    def __init__(self, user_id: int, text: str = ""):
        self.effective_user = SimpleNamespace(id=user_id)
        self.message = DummyMessage(text=text)


@pytest.fixture(autouse=True)
def reset_state(monkeypatch, tmp_path):
    auth.auth_flow_stage.clear()
    auth.auth_flow_data.clear()
    auth.user_sessions.clear()
    # Доступ в тестах не проверяем
    monkeypatch.setattr(auth, "check_access", lambda *_: True)

    token_dir = tmp_path / "tokens"
    cookies_dir = tmp_path / "cookies"
    token_dir.mkdir()
    cookies_dir.mkdir()

    monkeypatch.setattr(auth, "USER_TOKEN_DIR", str(token_dir), raising=False)
    monkeypatch.setattr(auth, "USER_COOKIES_DIR", str(cookies_dir), raising=False)

    yield


def test_token_file_valid(tmp_path):
    ok_file = tmp_path / "tok.txt"
    ok_file.write_text("abc", encoding="utf-8")
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")

    assert auth._token_file_valid(ok_file) is True
    assert auth._token_file_valid(empty_file) is False
    assert auth._token_file_valid(tmp_path / "missing.txt") is False


@pytest.mark.asyncio
async def test_ensure_user_authenticated_without_token(monkeypatch):
    update = DummyUpdate(user_id=1, text="")

    prompted = asyncio.Event()

    async def fake_prompt(u):
        await DummyMessage.reply_text(u.message, "prompt")
        prompted.set()
        telegram_bot.auth_flow_stage[u.effective_user.id] = "await_login"

    monkeypatch.setattr(auth, "_prompt_login", fake_prompt)

    token_path = await auth.ensure_user_authenticated(update)

    assert token_path is None
    assert auth.auth_flow_stage.get(1) == "await_login"
    assert prompted.is_set()


@pytest.mark.asyncio
async def test_login_flow_saves_token(monkeypatch, tmp_path):
    user_id = 42
    token_dir = Path(auth.USER_TOKEN_DIR)
    token_path = token_dir / f"{user_id}_token.txt"

    async def fake_login_with_credentials(username, password, token_path=None, cookies_path=None):
        Path(token_path).write_text("tok123", encoding="utf-8")
        return "tok123"

    monkeypatch.setattr(telegram_bot, "login_with_credentials", fake_login_with_credentials)

    # шаг логина
    auth.auth_flow_stage[user_id] = "await_login"
    update_login = DummyUpdate(user_id=user_id, text="user1")
    await map_handlers.text_handler(update_login, SimpleNamespace(args=[]))
    assert auth.auth_flow_stage[user_id] == "await_password"
    assert "Введите пароль" in update_login.message.replies[-1]

    # шаг пароля
    update_pass = DummyUpdate(user_id=user_id, text="pass1")
    await map_handlers.text_handler(update_pass, SimpleNamespace(args=[]))

    assert token_path.exists()
    assert token_path.read_text(encoding="utf-8") == "tok123"
    assert auth.auth_flow_stage.get(user_id) is None
    assert "UMP-аккаунт подключен" in update_pass.message.replies[-1]


@pytest.mark.asyncio
async def test_render_map_uses_token_path(monkeypatch, tmp_path):
    called = {}

    async def fake_reply_text(self, text, **kwargs):
        self.replies.append(text)

    DummyMessage.reply_text = fake_reply_text

    def fake_get_position(dep, token_path=None, **kwargs):
        called["token_path"] = token_path
        return {"ok": True, "depot_number": dep, "in_park": True, "park_name": "X"}

    def fake_render_parks_with_vehicles(depot_numbers, auth_token_path=None, **kwargs):
        called["render_token_path"] = auth_token_path
        return []

    monkeypatch.setattr(telegram_bot, "get_position_and_check", fake_get_position)
    monkeypatch.setattr(telegram_bot, "render_parks_with_vehicles", fake_render_parks_with_vehicles)

    user_id = 7
    token_path = tmp_path / "tok.txt"
    token_path.write_text("tok", encoding="utf-8")

    update = DummyUpdate(user_id=user_id, text="")
    await map_service.render_map_with_numbers(
        logger=telegram_bot.logger,
        update=update,
        depot_numbers=["1234"],
        selected_park=None,
        sections=None,
        token_path=str(token_path),
    )

    assert called["token_path"] == str(token_path)
    assert called["render_token_path"] == str(token_path)
    assert any("Нет ТС" in r for r in update.message.replies)


