from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import USER_META_DIR
from .settings import ADMIN_USER_ID, ALLOWED_USER_IDS


ACCESS_FILE = Path(USER_META_DIR) / "access_control.json"


def _now_ts() -> int:
    return int(time.time())


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _default_state() -> dict:
    # Важно: бот по умолчанию приватный.
    # Разрешаем админа всегда, плюс можно «подхватить» TELEGRAM_ALLOWED_USERS как начальный список.
    base_allowed = {int(ADMIN_USER_ID)}
    for u in (ALLOWED_USER_IDS or []):
        try:
            base_allowed.add(int(u))
        except Exception:
            continue
    return {"allowed": sorted(base_allowed), "denied": [], "requests": {}}


def load_state() -> dict:
    if not ACCESS_FILE.exists():
        state = _default_state()
        _atomic_write_json(ACCESS_FILE, state)
        return state
    try:
        raw = json.loads(ACCESS_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("bad state")
    except Exception:
        raw = _default_state()
        _atomic_write_json(ACCESS_FILE, raw)
        return raw

    raw.setdefault("allowed", [])
    raw.setdefault("denied", [])
    raw.setdefault("requests", {})
    return raw


def save_state(state: dict) -> None:
    _atomic_write_json(ACCESS_FILE, state)


def _as_int_set(v: Any) -> set[int]:
    out: set[int] = set()
    if isinstance(v, list):
        for x in v:
            try:
                out.add(int(x))
            except Exception:
                continue
    return out


def is_denied(user_id: int) -> bool:
    if int(user_id) == int(ADMIN_USER_ID):
        return False
    st = load_state()
    return int(user_id) in _as_int_set(st.get("denied"))


def is_allowed(user_id: int) -> bool:
    if int(user_id) == int(ADMIN_USER_ID):
        return True
    st = load_state()
    if int(user_id) in _as_int_set(st.get("denied")):
        return False
    if int(user_id) in _as_int_set(st.get("allowed")):
        return True
    # TELEGRAM_ALLOWED_USERS используем как «белый список по умолчанию», но он НЕ делает бота публичным.
    # Если env пустой — неизвестные пользователи НЕ допускаются.
    try:
        return str(user_id) in (ALLOWED_USER_IDS or [])
    except Exception:
        return False


def allow_user(user_id: int, by_admin: int | None = None) -> None:
    st = load_state()
    allowed = _as_int_set(st.get("allowed"))
    denied = _as_int_set(st.get("denied"))
    allowed.add(int(user_id))
    denied.discard(int(user_id))
    st["allowed"] = sorted(allowed)
    st["denied"] = sorted(denied)
    # закрываем заявку, если была
    reqs: Dict[str, dict] = st.get("requests", {}) or {}
    r = reqs.get(str(user_id))
    if isinstance(r, dict):
        r["status"] = "approved"
        r["resolved_at"] = _now_ts()
        if by_admin is not None:
            r["resolved_by"] = int(by_admin)
        reqs[str(user_id)] = r
        st["requests"] = reqs
    save_state(st)


def deny_user(user_id: int, by_admin: int | None = None) -> None:
    st = load_state()
    allowed = _as_int_set(st.get("allowed"))
    denied = _as_int_set(st.get("denied"))
    denied.add(int(user_id))
    allowed.discard(int(user_id))
    st["allowed"] = sorted(allowed)
    st["denied"] = sorted(denied)
    reqs: Dict[str, dict] = st.get("requests", {}) or {}
    r = reqs.get(str(user_id))
    if isinstance(r, dict):
        r["status"] = "denied"
        r["resolved_at"] = _now_ts()
        if by_admin is not None:
            r["resolved_by"] = int(by_admin)
        reqs[str(user_id)] = r
        st["requests"] = reqs
    save_state(st)


def add_or_touch_request(user: dict, note: str | None = None) -> dict:
    """
    Создаёт/обновляет заявку. Возвращает запись заявки.
    user: {"id": int, "username": str|None, "first_name": str|None, "last_name": str|None}
    """
    st = load_state()
    reqs: Dict[str, dict] = st.get("requests", {}) or {}
    uid = int(user["id"])
    key = str(uid)

    r = reqs.get(key) if isinstance(reqs.get(key), dict) else {}
    if not r:
        r = {
            "user_id": uid,
            "created_at": _now_ts(),
            "status": "pending",
        }
    r["username"] = user.get("username")
    r["first_name"] = user.get("first_name")
    r["last_name"] = user.get("last_name")
    r["updated_at"] = _now_ts()
    if note:
        r["note"] = note
    # request_text может быть добавлен отдельным сообщением
    reqs[key] = r
    st["requests"] = reqs
    save_state(st)
    return r


def set_request_text(user_id: int, request_text: str) -> dict:
    st = load_state()
    reqs: Dict[str, dict] = st.get("requests", {}) or {}
    key = str(int(user_id))
    r = reqs.get(key) if isinstance(reqs.get(key), dict) else None
    if not r:
        r = {"user_id": int(user_id), "created_at": _now_ts(), "status": "pending"}
    r["request_text"] = (request_text or "").strip()
    r["updated_at"] = _now_ts()
    r.setdefault("status", "pending")
    reqs[key] = r
    st["requests"] = reqs
    save_state(st)
    return r


def get_request(user_id: int) -> Optional[dict]:
    st = load_state()
    reqs: Dict[str, dict] = st.get("requests", {}) or {}
    r = reqs.get(str(int(user_id)))
    return r if isinstance(r, dict) else None


def request_needs_text(user_id: int) -> bool:
    r = get_request(user_id)
    if not r:
        return False
    if r.get("status") != "pending":
        return False
    txt = (r.get("request_text") or "").strip()
    return not bool(txt)


def pending_requests() -> list[dict]:
    st = load_state()
    reqs: Dict[str, dict] = st.get("requests", {}) or {}
    out = [v for v in reqs.values() if isinstance(v, dict) and v.get("status") == "pending"]
    out.sort(key=lambda x: int(x.get("updated_at") or x.get("created_at") or 0), reverse=True)
    return out


def stats() -> dict:
    st = load_state()
    allowed = _as_int_set(st.get("allowed"))
    denied = _as_int_set(st.get("denied"))
    pending = pending_requests()
    return {"allowed": len(allowed), "denied": len(denied), "pending": len(pending)}

