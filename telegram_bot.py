from __future__ import annotations


async def render_map_with_numbers(
    update: Update,
    depot_numbers: List[str],
    selected_park: Optional[str],
    sections: Optional[Dict[str, List[str]]] = None,
    token_path: Optional[str] = None,
) -> None:
    """Рендер карты для указанного списка ТС"""
    if not depot_numbers:
        await update.message.reply_text("❌ Не переданы номера ТС для построения карты.")
        return

    # Ограничение количества ТС
    if len(depot_numbers) > 50:
        depot_numbers = depot_numbers[:50]
        await update.message.reply_text(
            f"⚠️ Обрабатываю только первые 50 ТС. Остальные обрезаны."
        )

    log_print(f"render_map_with_numbers: {len(depot_numbers)} ТС, парк={selected_park}")

    if not token_path:
        await update.message.reply_text("❌ Нет токена UMP для запроса.")
        return

    await update.message.reply_text("🔄 Генерирую карту... Это может занять время.")

    # Создаем color map
    color_map = build_color_map_from_sections(sections)
    log_print(f"color_map создан: {len(color_map)} ТС с цветами")
    if color_map:
        log_print(f"Примеры цветов: {list(color_map.items())[:3]}")
    if sections:
        log_print(f"sections: {list(sections.keys())}")
        for cat, nums in sections.items():
            log_print(f"  {cat}: {nums[:3]}... (всего {len(nums)})")

    try:
        # Отладочные проверки первых ТС
        sample_results = []
        for dep in depot_numbers[:5]:
            try:
                result = get_position_and_check(dep, token_path=token_path)
                sample_results.append(result)
                log_print(
                    f"ТС {dep}: ok={result.get('ok')}, park={result.get('park_name')}, in_park={result.get('in_park')}"
                )
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    await update.message.reply_text("❌ Сессия UMP истекла. Введите /login для повторной авторизации.")
                    return
                log_print(f"HTTP error проверки ТС {dep}: {e}", "ERROR")
            except Exception as e:
                log_print(f"Ошибка проверки ТС {dep}: {e}", "ERROR")

        files = render_parks_with_vehicles(
            depot_numbers=depot_numbers,
            out_dir=OUT_DIR,
            size="1200x800",
            use_real_map=True,
            zoom=17,
            tile_provider=os.getenv("MAP_PROVIDER", ""),
            tile_cache=CACHE_DIR,
            tile_user_agent=os.getenv("MAP_USER_AGENT", ""),
            tile_referer=os.getenv("MAP_REFERER", ""),
            tile_apikey=os.getenv("MAPTILER_API_KEY", ""),
            tile_rate_tps=3.0,
            park_filter=selected_park,
            color_map=color_map,
            debug=True,
            auth_token_path=token_path,
        )

        if not files:
            debug_info = f"Обработано ТС: {len(depot_numbers)}\n"
            debug_info += f"Парк: {selected_park or 'все'}\n"
            if sample_results:
                debug_info += "\nПримеры:\n"
                for r in sample_results:
                    if r.get("ok"):
                        status = "✅ в парке" if r.get("in_park") else "❌ вне парка"
                        debug_info += f"  {r.get('depot_number')}: {status} ({r.get('park_name') or '—'})\n"
                    else:
                        debug_info += f"  {r.get('depot_number')}: ошибка {r.get('error')}\n"
            await update.message.reply_text(
                "❌ Нет ТС внутри парков для отображения.\n\n" + debug_info
            )
            return

        for file_path in files:
            try:
                file_size = os.path.getsize(file_path)
                if file_size > MAX_IMAGE_SIZE:
                    await update.message.reply_text(
                        f"⚠️ Изображение слишком большое ({file_size // 1024 // 1024}MB)"
                    )
                    continue
                with open(file_path, "rb") as photo:
                    park_name = Path(file_path).stem.replace("park_", "")
                    caption = f"📍 Парк: {park_name}\n🚌 ТС: {len(depot_numbers)}"
                    await update.message.reply_photo(photo=photo, caption=caption)
            except Exception as e:
                log_print(f"Ошибка отправки изображения {file_path}: {e}", "ERROR")
                await update.message.reply_text(f"❌ Ошибка отправки изображения: {e}")
    except FileNotFoundError as e:
        await update.message.reply_text(
            "❌ Токен UMP не найден. Введите /login и авторизуйтесь заново."
        )
    except Exception as e:
        log_print(f"Error in render_map_with_numbers: {e}", "ERROR")
        import traceback
        log_print(traceback.format_exc(), "ERROR")
        await update.message.reply_text(f"❌ Ошибка генерации карты: {e}")

# ---------- Helpers ----------
def determine_category_color(category: str) -> Tuple[str, str]:
    """Возвращает цвет точки по названию категории"""
    cat_lower = (category or "").lower().strip()
    cat_clean = cat_lower.rstrip(":")

    if "проверка гк" in cat_clean or cat_clean.startswith("проверка гк"):
        return "#ffd43b", "#fab005"
    if ("заявки redmine" in cat_clean
            or cat_clean.startswith("заявки redmine")
            or ("redmine" in cat_clean and "заявк" in cat_clean)):
        return "#4dabf7", "#339af0"
    if "текущие задачи" in cat_clean or cat_clean.startswith("текущие задачи"):
        return "#ff922b", "#fd7e14"
    if ("перенос камеры" in cat_clean
            or cat_clean.startswith("перенос камеры")
            or ("камера" in cat_clean and "перенос" in cat_clean)):
        return "#9775fa", "#845ef7"
    return "#fa5252", "#c92a2a"


def build_color_map_from_sections(sections: Optional[Dict[str, List[str]]]) -> Dict[str, Tuple[str, str]]:
    """Создает карту цветов по секциям"""
    color_map: Dict[str, Tuple[str, str]] = {}
    if not sections:
        log_print("build_color_map_from_sections: sections пустые или None")
        return color_map
    
    log_print(f"build_color_map_from_sections: обрабатываю {len(sections)} категорий")
    for category, numbers in sections.items():
        fill, outline = determine_category_color(category)
        log_print(f"  Категория '{category}': цвет {fill}, ТС: {numbers}")
        for num in numbers:
            # Нормализуем номер (убираем пробелы, приводим к строке)
            normalized_num = str(num).strip()
            color_map[normalized_num] = (fill, outline)
    
    log_print(f"build_color_map_from_sections: создано {len(color_map)} записей в color_map")
    return color_map


def deduplicate_numbers(numbers: List[str]) -> List[str]:
    seen = set()
    result = []
    for n in numbers:
        n = str(n).strip()
        if not n or n in seen:
            continue
        seen.add(n)
        result.append(n)
    return result

# telegram_bot.py
import os
import json
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Dict, List
from pathlib import Path

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from dotenv import load_dotenv

from otbivka import load_parks, batch_get_positions, get_position_and_check
from render_map import (
    render_parks_with_vehicles,
    parse_vehicles_file_with_sections,
    parse_sections_from_text,
)
from login_token import login_with_credentials
from diagnostic import (
    fetch_branch_diagnostics,
    extract_red_issues,
    format_issues_compact,
    extract_user_id_from_token,
    filter_issues_with_details,
)
from config import USER_TOKEN_DIR, USER_COOKIES_DIR, UMP_BRANCH_MAP, UMP_USER_ID

load_dotenv()

# Настройка логирования - принудительно в stdout/stderr
import sys
logging.basicConfig(
    format='%(asctime)s - [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),  # Принудительно stdout
        logging.StreamHandler(sys.stderr),  # И stderr для надежности
    ],
    force=True  # Перезаписываем существующую конфигурацию
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Дополнительно - print для критичных моментов (гарантированно видно)
def log_print(msg: str, level: str = "INFO"):
    """Дублирует логи в print для гарантированной видимости"""
    print(f"[{level}] {msg}", file=sys.stderr, flush=True)
    if level == "ERROR":
        logger.error(msg)
    elif level == "WARNING":
        logger.warning(msg)
    else:
        logger.info(msg)

# Конфигурация
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS = os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if os.getenv("TELEGRAM_ALLOWED_USERS") else []
VEHICLES_FILE = os.getenv("VEHICLES_FILE", "vehicles.txt")
OUT_DIR = os.getenv("MAP_OUT_DIR", "out")
CACHE_DIR = os.getenv("MAP_CACHE_DIR", ".tile_cache")
MAX_IMAGE_SIZE = int(os.getenv("MAX_IMAGE_SIZE_MB", "10")) * 1024 * 1024  # 10MB по умолчанию

# Кэш выбранных парков
user_park_cache: Dict[int, str] = {}


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


def _resolve_branch_id(branch_name: str) -> Optional[int]:
    if not branch_name:
        return None
    name_norm = branch_name.strip().lower()
    for k, v in (UMP_BRANCH_MAP or {}).items():
        try:
            if k.strip().lower() == name_norm:
                return int(v)
        except Exception:
            continue
    return None


def _known_branches_text() -> str:
    if not UMP_BRANCH_MAP:
        return "Настройте переменную UMP_BRANCH_MAP, например: {\"Екатерининский\":1382}"
    keys = ", ".join(UMP_BRANCH_MAP.keys())
    return f"Доступные филиалы: {keys}"


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


async def _ensure_user_authenticated(update: Update) -> Optional[str]:
    """Проверяет наличие токена пользователя. Если нет — запускает запрос логина."""
    user_id = update.effective_user.id
    token_path = _user_token_path(user_id)
    if _token_file_valid(token_path):
        return str(token_path)
    await update.message.reply_text("ℹ️ Нужна авторизация в UMP.")
    await _prompt_login(update)
    return None


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


def check_access(user_id: int) -> bool:
    """Проверка доступа пользователя"""
    if not ALLOWED_USER_IDS:
        return True  # Если список пуст, доступ открыт
    return str(user_id) in ALLOWED_USER_IDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /start"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещен.")
        return
    
    user_id = update.effective_user.id
    parks = load_parks()
    park_names = [p["name"] for p in parks]
    
    text = (
        "🚌 Бот для отслеживания ТС в парках\n\n"
        "Доступные команды:\n"
        "/map - Карта парка с ТС\n"
        "/parks - Список парков\n"
        "/status [номер] - Статус ТС\n"
        "/login - Подключить UMP-аккаунт\n"
        "/diag [филиал] - Ошибки оборудования по филиалу\n"
        "/help - Справка\n\n"
    )
    
    if user_id in user_park_cache:
        text += f"📍 Выбранный парк: {user_park_cache[user_id]}\n"
    
    await update.message.reply_text(text)

    # Запрос авторизации, если пользователь ещё не вошёл
    if not _user_token_ready(user_id):
        await _prompt_login(update)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /help"""
    if not check_access(update.effective_user.id):
        return
    
    text = (
        "📖 Справка по командам:\n\n"
        "/start - Начать работу\n"
        "/map - Показать карту парка с ТС\n"
        "/parks - Выбрать парк\n"
        "/status [номер] - Проверить статус ТС\n"
        "/diag [филиал] - Ошибки оборудования\n"
        "/login - Авторизоваться в UMP\n"
        "/help - Эта справка\n\n"
        "Примеры:\n"
        "/status 6569\n"
        "/map 6177 6848\n"
    )
    await update.message.reply_text(text)


async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запуск ручной авторизации в UMP"""
    if not check_access(update.effective_user.id):
        return
    await _prompt_login(update)


async def parks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /parks - выбор парка"""
    if not check_access(update.effective_user.id):
        return
    
    parks = load_parks()
    if not parks:
        await update.message.reply_text("❌ Парки не найдены в конфигурации.")
        return
    
    keyboard = []
    for park in parks:
        keyboard.append([
            InlineKeyboardButton(
                park["name"],
                callback_data=f"park_{park['name']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("Все парки", callback_data="park_all")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current_park = user_park_cache.get(update.effective_user.id, "не выбран")
    text = f"📍 Выберите парк:\n\nТекущий: {current_park}"
    
    await update.message.reply_text(text, reply_markup=reply_markup)


async def park_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка выбора парка"""
    query = update.callback_query
    await query.answer()
    
    if not check_access(query.from_user.id):
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    park_name = query.data.replace("park_", "")
    user_id = query.from_user.id
    
    if park_name == "all":
        if user_id in user_park_cache:
            del user_park_cache[user_id]
        await query.edit_message_text("✅ Выбраны все парки")
    else:
        user_park_cache[user_id] = park_name
        await query.edit_message_text(f"✅ Выбран парк: {park_name}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /status [номер]"""
    if not check_access(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажите номер ТС. Пример: /status 6569")
        return
    
    depot_number = context.args[0]
    
    token_path = await _ensure_user_authenticated(update)
    if not token_path:
        return
    
    try:
        result = get_position_and_check(depot_number, token_path=token_path)
        
        if not result.get("ok"):
            error = result.get("error", "unknown")
            await update.message.reply_text(f"❌ Ошибка: {error}")
            return
        
        in_park = "✅ В парке" if result.get("in_park") else "❌ Вне парка"
        park_name = result.get("park_name", "—")
        
        text = (
            f"🚌 ТС {result.get('depot_number')}\n\n"
            f"📍 Статус: {in_park}\n"
            f"🏢 Парк: {park_name}\n"
            f"🆔 ID: {result.get('vehicle_id')}\n"
            f"⏰ Время: {result.get('time', '—')}\n"
            f"🌐 Координаты:\n"
            f"   Lat: {result.get('lat', 0):.6f}\n"
            f"   Lon: {result.get('lon', 0):.6f}"
        )
        
        await update.message.reply_text(text)
    except FileNotFoundError as e:
        logger.error(f"Token file not found: {e}", exc_info=True)
        await update.message.reply_text("❌ Нет токена UMP. Используйте /login для авторизации.")
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        logger.error(f"HTTP error in status_command: {status}", exc_info=True)
        if status == 401:
            await update.message.reply_text("❌ Сессия UMP истекла. Введите /login и авторизуйтесь снова.")
        else:
            await update.message.reply_text(f"❌ HTTP ошибка {status}: {e}")
    except Exception as e:
        logger.error(f"Error in status_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def map_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /map - рендер карты ТОЛЬКО с явно переданными номерами"""
    log_print("=" * 50)
    log_print("map_command вызван")
    
    if not check_access(update.effective_user.id):
        log_print(f"Доступ запрещен для user={update.effective_user.id}", "WARNING")
        return
    
    user_id = update.effective_user.id
    selected_park = user_park_cache.get(user_id)
    log_print(f"map_command: user={user_id}, park={selected_park}, args={context.args}")

    token_path = await _ensure_user_authenticated(update)
    if not token_path:
        return

    # ТОЛЬКО явно переданные аргументы
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите номера ТС. Пример: /map 6683 6719 6306\n\n"
            "Или просто отправьте текст с задачами (без команды /map)"
        )
        return

    depot_numbers = deduplicate_numbers(
        [d for d in context.args if is_valid_depot_number(d)]
    )
    
    if not depot_numbers:
        await update.message.reply_text(
            "❌ Не найдено валидных номеров ТС в аргументах.\n"
            "Пример: /map 6683 6719 6306"
        )
        return

    log_print(f"Номера из аргументов: {depot_numbers}")

    # Без категорий для /map с аргументами - все точки будут красными
    await render_map_with_numbers(
        update=update,
        depot_numbers=depot_numbers,
        selected_park=selected_park,
        sections=None,  # Нет категорий для явных номеров
        token_path=token_path,
    )


async def diag_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /diag - проверка красных индикаторов оборудования по филиалу"""
    if not check_access(update.effective_user.id):
        return

    user_id = update.effective_user.id
    branch_name = " ".join(context.args).strip() if context.args else user_park_cache.get(user_id)

    if not branch_name:
        await update.message.reply_text(
            "❌ Укажите филиал: /diag <название> или выберите парк через /parks."
        )
        return

    branch_id = _resolve_branch_id(branch_name)
    if branch_id is None:
        await update.message.reply_text(
            f"❌ Филиал '{branch_name}' не найден. {_known_branches_text()}"
        )
        return
    token_path = await _ensure_user_authenticated(update)
    if not token_path:
        return
    user_token = ""
    try:
        user_token = Path(token_path).read_text(encoding="utf-8").strip()
    except Exception:
        pass
    user_id_value = extract_user_id_from_token(user_token) or (int(UMP_USER_ID) if UMP_USER_ID else None)
    if not user_id_value:
        await update.message.reply_text(
            "❌ Не удалось определить user_id из токена. Добавьте UMP_USER_ID в .env."
        )
        return

    def _split_and_send(text: str, limit: int = 3500):
        # Делит длинное сообщение на части, чтобы не превысить лимит Telegram
        chunks = []
        while text:
            chunks.append(text[:limit])
            text = text[limit:]
        return chunks

    try:
        data = fetch_branch_diagnostics(
            branch_id,
            token_path=str(token_path),
            user_id=user_id_value,
        )
        issues = extract_red_issues(data)
        issues = filter_issues_with_details(
            issues,
            token_path=str(token_path),
            user_id=user_id_value,
        )
        full_text = format_issues_compact(issues)
        for chunk in _split_and_send(full_text):
            await update.message.reply_text(chunk)
    except FileNotFoundError:
        await update.message.reply_text("❌ Нет токена UMP. Введите /login.")
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        log_print(f"HTTP error in diag_command: {status}", "ERROR")
        if status == 401:
            await update.message.reply_text("❌ Сессия UMP истекла. Повторите /login.")
        else:
            detail = (e.response.text or "")[:300] if e.response is not None else str(e)
            await update.message.reply_text(f"❌ HTTP ошибка {status}: {detail}")
    except Exception as e:
        log_print(f"Error in diag_command: {e}", "ERROR")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений в формате vehicles.txt"""
    log_print(f"text_handler вызван: user={update.effective_user.id}")
    
    if not check_access(update.effective_user.id):
        log_print(f"Доступ запрещен для user={update.effective_user.id}", "WARNING")
        return
    
    if not update.message or not update.message.text:
        log_print("Нет текста в сообщении", "WARNING")
        return
    
    text = update.message.text.strip()
    log_print(f"Получен текст ({len(text)} символов): {text[:100]}...")

    # Шаги авторизации (логин/пароль)
    user_id = update.effective_user.id
    stage = auth_flow_stage.get(user_id)
    if stage == "await_login":
        auth_flow_data[user_id] = {"username": text}
        auth_flow_stage[user_id] = "await_password"
        await update.message.reply_text("Введите пароль UMP:")
        return
    if stage == "await_password":
        username = auth_flow_data.get(user_id, {}).get("username") or ""
        password = text
        token_path = _user_token_path(user_id)
        cookies_path = _user_cookies_path(user_id)
        try:
            token = login_with_credentials(
                username=username,
                password=password,
                token_path=str(token_path),
                cookies_path=str(cookies_path),
            )
            _save_user_session(user_id, username=username, password=None, token=token)
            _reset_auth_flow(user_id)
            await update.message.reply_text("✅ UMP-аккаунт подключен. Теперь можно отправлять запросы.")
        except Exception as e:
            _reset_auth_flow(user_id)
            auth_flow_stage[user_id] = "await_login"
            auth_flow_data[user_id] = {}
            await update.message.reply_text(f"❌ Не удалось авторизоваться: {e}\nВведите логин ещё раз:")
        return
    
    # Пропускаем команды
    if text.startswith("/"):
        log_print("Пропущена команда")
        return

    token_path = await _ensure_user_authenticated(update)
    if not token_path:
        return
    
    try:
        sections = parse_sections_from_text(text)
        depot_numbers = deduplicate_numbers(
            [num for nums in sections.values() for num in nums]
        )
        
        if not depot_numbers:
            log_print("Не найдено номеров ТС в сообщении", "WARNING")
            await update.message.reply_text("❌ Не найдено номеров ТС в сообщении.")
            return
        
        log_print(f"Парсинг текста: найдено {len(depot_numbers)} ТС из {len(sections)} категорий")
        log_print(f"Категории: {list(sections.keys())}")
        for cat, nums in sections.items():
            log_print(f"  {cat}: {nums}")

        # Сразу генерируем карту с цветами на основе текста
        await render_map_with_numbers(
            update=update,
            depot_numbers=depot_numbers,
            selected_park=user_park_cache.get(update.effective_user.id),
            sections=sections,
            token_path=token_path,
        )
        
    except Exception as e:
        log_print(f"Error parsing text: {e}", "ERROR")
        import traceback
        log_print(traceback.format_exc(), "ERROR")
        await update.message.reply_text(f"❌ Ошибка парсинга текста: {str(e)}")


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /test - диагностика"""
    if not check_access(update.effective_user.id):
        return
    
    log_print("=== TEST COMMAND ВЫЗВАН ===")
    
    info_lines = []
    info_lines.append("🔍 ДИАГНОСТИКА БОТА\n")
    user_id = update.effective_user.id
    
    # Проверка конфигурации
    info_lines.append(f"✅ BOT_TOKEN: {'установлен' if BOT_TOKEN else 'НЕ УСТАНОВЛЕН'}")
    info_lines.append(f"📁 VEHICLES_FILE: {VEHICLES_FILE} ({'существует' if os.path.exists(VEHICLES_FILE) else 'НЕ СУЩЕСТВУЕТ'})")
    info_lines.append(f"📁 OUT_DIR: {OUT_DIR} ({'существует' if os.path.exists(OUT_DIR) else 'НЕ СУЩЕСТВУЕТ'})")
    info_lines.append(f"📁 CACHE_DIR: {CACHE_DIR}")
    
    # Проверка токена пользователя
    token_path = _user_token_path(user_id)
    info_lines.append(f"\n🔑 ТОКЕН UMP (user={user_id}):")
    info_lines.append(f"   Путь: {token_path}")
    info_lines.append(f"   Существует: {'ДА' if token_path.exists() else 'НЕТ'}")
    if token_path.exists():
        try:
            with open(token_path, "r") as f:
                token = f.read().strip()
                info_lines.append(f"   Длина: {len(token)} символов")
        except Exception as e:
            info_lines.append(f"   Ошибка чтения: {e}")
    else:
        info_lines.append("   Требуется авторизация через /login")
    
    # Проверка парков
    try:
        parks = load_parks()
        info_lines.append(f"\n🏢 ПАРКИ: найдено {len(parks)}")
        for p in parks:
            info_lines.append(f"   - {p['name']}")
    except Exception as e:
        info_lines.append(f"\n🏢 ПАРКИ: ошибка загрузки - {e}")
    
    # Проверка vehicles.txt
    if os.path.exists(VEHICLES_FILE):
        try:
            sections = parse_vehicles_file_with_sections(VEHICLES_FILE)
            total = sum(len(nums) for nums in sections.values())
            info_lines.append(f"\n🚌 VEHICLES.TXT:")
            info_lines.append(f"   Всего ТС: {total}")
            info_lines.append(f"   Категорий: {len(sections)}")
            for cat, nums in list(sections.items())[:3]:
                info_lines.append(f"   - {cat}: {len(nums)} ТС")
        except Exception as e:
            info_lines.append(f"\n🚌 VEHICLES.TXT: ошибка парсинга - {e}")
    
    # Проверка выбранного парка
    selected_park = user_park_cache.get(user_id)
    info_lines.append(f"\n📍 ВЫБРАННЫЙ ПАРК: {selected_park or 'не выбран (все)'}")
    
    # Тест одного ТС
    info_lines.append(f"\n🧪 ТЕСТ ТС 6400:")
    try:
        if _token_file_valid(token_path):
            result = get_position_and_check("6400", token_path=str(token_path))
            if result.get("ok"):
                info_lines.append(f"   ✅ OK: в парке={result.get('in_park')}, парк={result.get('park_name')}")
            else:
                info_lines.append(f"   ❌ Ошибка: {result.get('error')}")
        else:
            info_lines.append(f"   ❌ Нет токена. Авторизуйтесь через /login.")
    except Exception as e:
        info_lines.append(f"   ❌ Исключение: {e}")
    
    response = "\n".join(info_lines)
    log_print(f"TEST RESPONSE:\n{response}")
    await update.message.reply_text(response)


def main() -> None:
    """Запуск бота"""
    log_print("=" * 60)
    log_print("ЗАПУСК БОТА")
    log_print("=" * 60)
    
    if not BOT_TOKEN:
        log_print("TELEGRAM_BOT_TOKEN не установлен в .env", "ERROR")
        return
    
    log_print(f"BOT_TOKEN установлен (длина: {len(BOT_TOKEN)})")
    log_print(f"VEHICLES_FILE: {VEHICLES_FILE} (существует: {os.path.exists(VEHICLES_FILE)})")
    log_print(f"OUT_DIR: {OUT_DIR}")
    log_print(f"CACHE_DIR: {CACHE_DIR}")
    log_print(f"USER_TOKEN_DIR: {USER_TOKEN_DIR}")
    log_print("Авторизация в UMP выполняется каждым пользователем вручную через /login.")
    
    # Создаем Application
    log_print("Создаю Application...")
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    log_print("Регистрирую обработчики...")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("diag", diag_command))
    application.add_handler(CommandHandler("parks", parks_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("map", map_command))
    application.add_handler(CallbackQueryHandler(park_callback, pattern="^park_"))
    # Обработчик текстовых сообщений (для формата vehicles.txt) - должен быть последним
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    log_print("Обработчики зарегистрированы")
    
    # Запускаем бота
    log_print("=" * 60)
    log_print("БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ")
    log_print("=" * 60)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

