import asyncio
from types import SimpleNamespace

from src.ump_bot.handlers import map as map_handlers
from src.ump_bot.handlers import status as status_handlers
from src.ump_bot.handlers import diagnostics as diag_handlers
from src.ump_bot.services import auth
from src.ump_bot.services.state import user_park_cache


class DummyMessage:
    def __init__(self, text: str = ""):
        self.text = text
        self.replies = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append(text)

    async def reply_photo(self, *args, **kwargs):
        # ignore in smoke tests
        return None


class DummyUpdate:
    def __init__(self, user_id: int = 1, text: str = ""):
        self.effective_user = SimpleNamespace(id=user_id)
        self.message = DummyMessage(text=text)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_map_smoke(monkeypatch):
    called = {}
    user_park_cache.clear()
    user_park_cache[1] = "PARK-1"

    async def fake_render_map_with_numbers(**kwargs):
        called.update(kwargs)

    async def fake_auth(update):
        return "tok"

    monkeypatch.setattr(map_handlers, "render_map_with_numbers", fake_render_map_with_numbers)
    monkeypatch.setattr(auth, "ensure_user_authenticated", fake_auth)
    monkeypatch.setattr(auth, "check_access", lambda *_: True)

    update = DummyUpdate(1)
    ctx = SimpleNamespace(args=["1234", "bad"])

    run(map_handlers.map_command(update, ctx))

    assert called["selected_park"] == "PARK-1"
    assert called["depot_numbers"] == ["1234"]


def test_status_smoke(monkeypatch):
    async def fake_auth(update):
        return "tok"

    def fake_get_position(dep, token_path=None, **kwargs):
        return {
            "ok": True,
            "depot_number": dep,
            "in_park": True,
            "park_name": "X",
            "vehicle_id": 10,
            "time": "now",
            "lat": 1.0,
            "lon": 2.0,
        }

    monkeypatch.setattr(auth, "ensure_user_authenticated", fake_auth)
    monkeypatch.setattr(auth, "check_access", lambda *_: True)
    monkeypatch.setattr(status_handlers, "get_position_and_check", fake_get_position)

    update = DummyUpdate(2)
    ctx = SimpleNamespace(args=["5555"])

    run(status_handlers.status_command(update, ctx))

    assert any("ТС 5555" in r for r in update.message.replies)


def test_diag_smoke(monkeypatch):
    async def fake_auth(update):
        return "tok"

    monkeypatch.setattr(auth, "ensure_user_authenticated", fake_auth)
    monkeypatch.setattr(auth, "check_access", lambda *_: True)
    monkeypatch.setattr(auth, "_load_saved_token", lambda *_: None)
    monkeypatch.setattr(diag_handlers, "_resolve_branch_id", lambda name: 1)
    monkeypatch.setattr(diag_handlers, "fetch_branch_diagnostics", lambda **kwargs: {})
    monkeypatch.setattr(diag_handlers, "filter_issues_with_details", lambda raw: [])
    monkeypatch.setattr(diag_handlers, "extract_red_issues", lambda issues: [])
    monkeypatch.setattr(diag_handlers, "format_issues_compact", lambda issues: "нет проблем")

    update = DummyUpdate(3)
    ctx = SimpleNamespace(args=["AnyBranch"])

    run(diag_handlers.diag_command(update, ctx))

    assert any("нет проблем" in r for r in update.message.replies)
