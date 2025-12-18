from __future__ import annotations

import asyncio
import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Iterable, Optional

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..config import (
    CACHE_DIR,
    UMP_BASE_URL,
    USER_COOKIES_DIR,
    USER_CREDS_DIR,
    USER_META_DIR,
    USER_TOKEN_DIR,
)
from ..services import auth
from ..services.settings import ADMIN_USER_ID, ALLOWED_USER_IDS, UMP_BOT_LOG_FILE
from ..services.state import user_park_cache


def _is_admin(user_id: int) -> bool:
    return int(user_id) == int(ADMIN_USER_ID)


async def _deny(update: Update) -> None:
    if update.message:
        await update.message.reply_text("❌ Доступ запрещён.")
    elif update.callback_query:
        await update.callback_query.answer("Доступ запрещён.", show_alert=True)


def _fmt_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    for u in units:
        if v < 1024.0 or u == units[-1]:
            if u == "B":
                return f"{int(v)} {u}"
            return f"{v:.1f} {u}"
        v /= 1024.0
    return f"{int(n)} B"


def _safe_list_dir(path: str) -> list[Path]:
    p = Path(path)
    if not p.exists() or not p.is_dir():
        return []
    return [x for x in p.iterdir() if x.is_file()]


def _tail_lines(path: Path, max_lines: int = 200, chunk_size: int = 4096) -> list[str]:
    if max_lines <= 0:
        return []
    if not path.exists() or not path.is_file():
        return []

    # Быстрый tail: читаем с конца небольшими кусками.
    data = b""
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        pos = size
        while pos > 0 and data.count(b"\n") <= max_lines:
            read_size = min(chunk_size, pos)
            pos -= read_size
            f.seek(pos)
            data = f.read(read_size) + data
            if pos == 0:
                break
    lines = data.splitlines()[-max_lines:]
    out: list[str] = []
    for raw in lines:
        try:
            out.append(raw.decode("utf-8", errors="replace"))
        except Exception:
            out.append(str(raw))
    return out


def _detect_docker() -> bool:
    if Path("/.dockerenv").exists():
        return True
    cgroup = Path("/proc/1/cgroup")
    if cgroup.exists():
        try:
            txt = cgroup.read_text(encoding="utf-8", errors="ignore")
            return ("docker" in txt) or ("kubepods" in txt) or ("containerd" in txt)
        except Exception:
            return False
    return False


def _read_proc_uptime() -> Optional[float]:
    p = Path("/proc/uptime")
    if not p.exists():
        return None
    try:
        first = p.read_text(encoding="utf-8").split()[0]
        return float(first)
    except Exception:
        return None


def _fmt_duration_s(seconds: float) -> str:
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}д {h}ч {m}м"
    if h:
        return f"{h}ч {m}м"
    if m:
        return f"{m}м {s}с"
    return f"{s}с"


def _try_git_rev() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=1.5,
        )
        return out.decode("utf-8", errors="ignore").strip() or None
    except Exception:
        return None


def _try_journalctl_tail(unit: str, n: int = 200) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["journalctl", "-u", unit, "-n", str(n), "--no-pager"],
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
        txt = out.decode("utf-8", errors="replace").strip()
        return txt or None
    except Exception:
        return None


def _try_systemctl_is_active(unit: str) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["systemctl", "is-active", unit],
            stderr=subprocess.DEVNULL,
            timeout=1.5,
        )
        return out.decode("utf-8", errors="ignore").strip() or None
    except Exception:
        return None


def _menu() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton("🔑 Токены/файлы", callback_data="admin_tokens"),
        ],
        [
            InlineKeyboardButton("🧾 Логи (tail)", callback_data="admin_logs"),
            InlineKeyboardButton("📦 Окружение", callback_data="admin_env"),
        ],
        [
            InlineKeyboardButton("🌐 UMP healthcheck", callback_data="admin_ump"),
            InlineKeyboardButton("🔄 Обновить меню", callback_data="admin_menu"),
        ],
    ]
    return InlineKeyboardMarkup(kb)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_admin(user_id):
        await _deny(update)
        return

    text = (
        "🛠 Админ‑панель\n\n"
        f"👤 Ваш id: `{user_id}`\n"
        f"✅ Разрешённые пользователи (TELEGRAM_ALLOWED_USERS): {', '.join(ALLOWED_USER_IDS) if ALLOWED_USER_IDS else 'не ограничено'}\n\n"
        "Выберите действие:"
    )
    await update.message.reply_text(text, reply_markup=_menu(), parse_mode="Markdown")


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    user_id = q.from_user.id
    if not _is_admin(user_id):
        await _deny(update)
        return

    action = (q.data or "").strip()
    if action == "admin_menu":
        await q.edit_message_text("🛠 Админ‑панель\n\nВыберите действие:", reply_markup=_menu())
        return

    if action == "admin_stats":
        token_files = _safe_list_dir(USER_TOKEN_DIR)
        cookies_files = _safe_list_dir(USER_COOKIES_DIR)
        creds_files = _safe_list_dir(USER_CREDS_DIR)
        meta_files = _safe_list_dir(USER_META_DIR)

        selected_park = user_park_cache.get(user_id)

        lines: list[str] = []
        lines.append("📊 Статистика\n")
        lines.append(f"👥 Сессий в памяти (user_sessions): {len(auth.user_sessions)}")
        lines.append(f"🧭 Выбранный парк (для вас): {selected_park or 'не выбран (все)'}")
        lines.append("")
        lines.append("📁 Файлы по пользователям:")
        lines.append(f"- tokens: {len(token_files)} ({USER_TOKEN_DIR})")
        lines.append(f"- cookies: {len(cookies_files)} ({USER_COOKIES_DIR})")
        lines.append(f"- creds: {len(creds_files)} ({USER_CREDS_DIR})")
        lines.append(f"- meta: {len(meta_files)} ({USER_META_DIR})")
        lines.append("")
        lines.append("🔐 Ваш UMP токен:")
        p = auth._user_token_path(user_id)
        if p.exists():
            try:
                tok = p.read_text(encoding="utf-8").strip()
                age_s = max(0.0, time.time() - p.stat().st_mtime)
                lines.append(f"- файл: {p}")
                lines.append(f"- длина: {len(tok)}")
                lines.append(f"- возраст: {_fmt_duration_s(age_s)}")
            except Exception as e:
                lines.append(f"- файл: {p}")
                lines.append(f"- ошибка чтения: {e}")
        else:
            lines.append(f"- файла нет: {p}")
            lines.append("- авторизуйтесь через /login")

        await q.edit_message_text("\n".join(lines), reply_markup=_menu())
        return

    if action == "admin_tokens":
        token_dir = Path(USER_TOKEN_DIR)
        cookies_dir = Path(USER_COOKIES_DIR)
        creds_dir = Path(USER_CREDS_DIR)

        def short_list(files: Iterable[Path], limit: int = 10) -> list[str]:
            out = []
            files_sorted = sorted(files, key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True)
            for f in files_sorted[:limit]:
                try:
                    st = f.stat()
                    age = max(0.0, time.time() - st.st_mtime)
                    out.append(f"- {f.name} ({_fmt_bytes(st.st_size)}, {_fmt_duration_s(age)} назад)")
                except Exception:
                    out.append(f"- {f.name}")
            if len(files_sorted) > limit:
                out.append(f"... и ещё {len(files_sorted) - limit}")
            return out

        t_files = _safe_list_dir(str(token_dir))
        c_files = _safe_list_dir(str(cookies_dir))
        cr_files = _safe_list_dir(str(creds_dir))

        lines: list[str] = []
        lines.append("🔑 Токены/файлы\n")
        lines.append(f"BOT_TOKEN: {'установлен' if bool(os.getenv('TELEGRAM_BOT_TOKEN')) else 'НЕ УСТАНОВЛЕН'}")
        lines.append(f"MAPTILER_API_KEY: {'установлен' if bool(os.getenv('MAPTILER_API_KEY')) else 'нет'}")
        lines.append("")
        lines.append(f"📁 {token_dir} (tokens): {len(t_files)}")
        lines.extend(short_list(t_files))
        lines.append("")
        lines.append(f"📁 {cookies_dir} (cookies): {len(c_files)}")
        lines.extend(short_list(c_files))
        lines.append("")
        lines.append(f"📁 {creds_dir} (creds): {len(cr_files)}")
        lines.extend(short_list(cr_files))

        await q.edit_message_text("\n".join(lines), reply_markup=_menu())
        return

    if action == "admin_logs":
        candidates = [
            Path(UMP_BOT_LOG_FILE),
            Path("ump_bot.log"),
            Path("var/ump_bot.log"),
            Path("/var/log/ump_bot.log"),
        ]
        log_path = next((p for p in candidates if p.exists() and p.is_file()), None)
        if not log_path:
            # systemd/journald fallback (частый кейс в этом проекте)
            journal = _try_journalctl_tail("ump-bot", n=200)
            if journal:
                text = "🧾 Логи (journalctl -u ump-bot -n 200)\n\n" + journal
                if len(text) > 3800:
                    text = "…(обрезано)\n" + text[-3800:]
                await q.edit_message_text(text, reply_markup=_menu())
                return

            await q.edit_message_text(
                "🧾 Логи\n\n❌ Лог‑файл не найден и `journalctl` недоступен.\n"
                f"Файлы: {', '.join(str(p) for p in candidates)}\n\n"
                "Подсказка: можно задать env `UMP_BOT_LOG_FILE` и писать логи в файл, либо смотреть `journalctl -u ump-bot` на сервере.",
                reply_markup=_menu(),
            )
            return

        lines = _tail_lines(log_path, max_lines=200)
        header = f"🧾 Логи (последние {len(lines)} строк)\nФайл: {log_path}\n"
        body = "\n".join(lines) if lines else "(пусто)"
        text = header + "\n" + body

        # Telegram ограничивает длину сообщений — подрежем аккуратно.
        if len(text) > 3800:
            text = text[-3800:]
            text = "…(обрезано)\n" + text

        await q.edit_message_text(text, reply_markup=_menu())
        return

    if action == "admin_env":
        is_docker = _detect_docker()
        uptime = _read_proc_uptime()
        git_rev = _try_git_rev()
        svc = _try_systemctl_is_active("ump-bot") or _try_systemctl_is_active("ump-bot.service")

        du_root = shutil.disk_usage("/")
        du_here = shutil.disk_usage(os.getcwd())

        lines: list[str] = []
        lines.append("📦 Окружение/контейнер\n")
        lines.append(f"🐍 Python: {platform.python_version()}")
        lines.append(f"🧠 Платформа: {platform.platform()}")
        lines.append(f"🖥 Hostname: {socket.gethostname()}")
        lines.append(f"🧩 Docker: {'да' if is_docker else 'нет/не определено'}")
        if svc:
            lines.append(f"🧰 systemd: ump-bot is-active = {svc}")
        if uptime is not None:
            lines.append(f"⏱ Uptime (по /proc/uptime): {_fmt_duration_s(uptime)}")
        if git_rev:
            lines.append(f"🔖 git: {git_rev}")
        try:
            la = os.getloadavg()
            lines.append(f"📈 Loadavg: {la[0]:.2f} {la[1]:.2f} {la[2]:.2f}")
        except Exception:
            pass
        lines.append("")
        lines.append("💾 Диск:")
        lines.append(f"- /: свободно {_fmt_bytes(du_root.free)} из {_fmt_bytes(du_root.total)}")
        lines.append(f"- cwd: свободно {_fmt_bytes(du_here.free)} из {_fmt_bytes(du_here.total)}")
        lines.append("")
        lines.append(f"🗂 CACHE_DIR: {CACHE_DIR} ({'есть' if Path(CACHE_DIR).exists() else 'нет'})")

        await q.edit_message_text("\n".join(lines), reply_markup=_menu())
        return

    if action == "admin_ump":
        async def do_check() -> str:
            try:
                def req() -> tuple[int, float]:
                    t0 = time.time()
                    r = requests.get(UMP_BASE_URL, timeout=3.0)
                    dt = time.time() - t0
                    return r.status_code, dt

                code, dt = await asyncio.to_thread(req)
                return f"🌐 UMP healthcheck\n\n✅ {UMP_BASE_URL}\nHTTP: {code}\nВремя: {dt:.2f}s"
            except Exception as e:
                return f"🌐 UMP healthcheck\n\n❌ {UMP_BASE_URL}\nОшибка: {e}"

        await q.edit_message_text(await do_check(), reply_markup=_menu())
        return

    await q.edit_message_text(f"Неизвестное действие: {action}", reply_markup=_menu())

