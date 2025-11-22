async def render_map_with_numbers(
    update: Update,
    depot_numbers: List[str],
    selected_park: Optional[str],
    sections: Optional[Dict[str, List[str]]] = None,
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

    # Проверяем токен
    if not ensure_token_with_retry():
        log_print("Не удалось получить токен UMP", "ERROR")
        await update.message.reply_text(
            "❌ Ошибка авторизации в UMP. Проверьте UMP_USER и UMP_PASS."
        )
        return

    await update.message.reply_text("🔄 Генерирую карту... Это может занять время.")

    # Создаем color map
    color_map = build_color_map_from_sections(sections)

    try:
        # Отладочные проверки первых ТС
        sample_results = []
        for dep in depot_numbers[:5]:
            try:
                result = get_position_and_check(dep)
                sample_results.append(result)
                log_print(
                    f"ТС {dep}: ok={result.get('ok')}, park={result.get('park_name')}, in_park={result.get('in_park')}"
                )
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
        if "ump_token" in str(e).lower():
            log_print(f"Token file not found: {e}", "ERROR")
            await update.message.reply_text("🔄 Токен не найден, пытаюсь авторизоваться...")
            if ensure_token_with_retry():
                await update.message.reply_text("✅ Авторизация успешна. Повторите команду.")
            else:
                await update.message.reply_text("❌ Ошибка авторизации. Проверьте настройки.")
        else:
            await update.message.reply_text(f"❌ Файл не найден: {e}")
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
        return color_map
    for category, numbers in sections.items():
        fill, outline = determine_category_color(category)
        for num in numbers:
            color_map[str(num)] = (fill, outline)
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
from typing import Optional, Dict, List
from pathlib import Path

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
from login_token import login_and_save
from config import UMP_TOKEN_FILE, UMP_USER, UMP_PASS

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


def ensure_token_exists() -> bool:
    """Проверяет наличие токена и создает его при необходимости"""
    log_print(f"ensure_token_exists: проверяю {UMP_TOKEN_FILE}")
    token_path = Path(UMP_TOKEN_FILE)
    
    # Если токен существует, проверяем что он не пустой
    if token_path.exists():
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if token:
                    log_print(f"Токен найден, длина: {len(token)}")
                    return True
                else:
                    log_print("Токен пустой", "WARNING")
        except Exception as e:
            log_print(f"Ошибка чтения токена: {e}", "ERROR")
            pass
    else:
        log_print(f"Файл токена не существует: {UMP_TOKEN_FILE}", "WARNING")
    
    # Токена нет или он пустой - пытаемся создать
    if not UMP_USER or not UMP_PASS:
        log_print("UMP_USER или UMP_PASS не установлены в .env. Автологин невозможен.", "ERROR")
        return False
    
    try:
        log_print("Токен не найден, выполняю авторизацию...")
        login_and_save()
        log_print("Авторизация успешна")
        return True
    except Exception as e:
        log_print(f"Ошибка авторизации: {e}", "ERROR")
        import traceback
        log_print(traceback.format_exc(), "ERROR")
        return False


def ensure_token_with_retry() -> bool:
    """Проверяет токен и пытается обновить при необходимости"""
    if ensure_token_exists():
        return True
    
    # Если не удалось - пробуем еще раз
    logger.warning("Повторная попытка авторизации...")
    return ensure_token_exists()


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
        "/help - Справка\n\n"
    )
    
    if user_id in user_park_cache:
        text += f"📍 Выбранный парк: {user_park_cache[user_id]}\n"
    
    await update.message.reply_text(text)


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
        "/help - Эта справка\n\n"
        "Примеры:\n"
        "/status 6569\n"
        "/map 6177 6848\n"
    )
    await update.message.reply_text(text)


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
    
    # Проверяем токен перед выполнением
    if not ensure_token_with_retry():
        await update.message.reply_text(
            "❌ Ошибка авторизации в UMP. Проверьте UMP_USER и UMP_PASS в .env"
        )
        return
    
    try:
        result = get_position_and_check(depot_number)
        
        # Если получили 401 - пробуем перелогиниться и повторить
        if not result.get("ok") and result.get("error") == "http_error":
            status = result.get("status")
            if status == 401:
                logger.warning("Получен 401, пытаюсь перелогиниться...")
                if ensure_token_with_retry():
                    result = get_position_and_check(depot_number)
                else:
                    await update.message.reply_text("❌ Ошибка авторизации. Попробуйте позже.")
                    return
        
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
        if ensure_token_with_retry():
            # Повторяем запрос после создания токена
            try:
                result = get_position_and_check(depot_number)
                if result.get("ok"):
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
                else:
                    await update.message.reply_text(f"❌ Ошибка: {result.get('error', 'unknown')}")
            except Exception as e2:
                await update.message.reply_text(f"❌ Ошибка: {str(e2)}")
        else:
            await update.message.reply_text("❌ Ошибка авторизации. Проверьте настройки.")
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
    )


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
    
    # Пропускаем команды
    if text.startswith("/"):
        log_print("Пропущена команда")
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

        # Сразу генерируем карту с цветами на основе текста
        await render_map_with_numbers(
            update=update,
            depot_numbers=depot_numbers,
            selected_park=user_park_cache.get(update.effective_user.id),
            sections=sections,
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
    
    # Проверка конфигурации
    info_lines.append(f"✅ BOT_TOKEN: {'установлен' if BOT_TOKEN else 'НЕ УСТАНОВЛЕН'}")
    info_lines.append(f"📁 VEHICLES_FILE: {VEHICLES_FILE} ({'существует' if os.path.exists(VEHICLES_FILE) else 'НЕ СУЩЕСТВУЕТ'})")
    info_lines.append(f"📁 OUT_DIR: {OUT_DIR} ({'существует' if os.path.exists(OUT_DIR) else 'НЕ СУЩЕСТВУЕТ'})")
    info_lines.append(f"📁 CACHE_DIR: {CACHE_DIR}")
    
    # Проверка токена
    token_path = Path(UMP_TOKEN_FILE)
    info_lines.append(f"\n🔑 ТОКЕН UMP:")
    info_lines.append(f"   Путь: {UMP_TOKEN_FILE}")
    info_lines.append(f"   Существует: {'ДА' if token_path.exists() else 'НЕТ'}")
    if token_path.exists():
        try:
            with open(token_path, "r") as f:
                token = f.read().strip()
                info_lines.append(f"   Длина: {len(token)} символов")
        except Exception as e:
            info_lines.append(f"   Ошибка чтения: {e}")
    info_lines.append(f"   UMP_USER: {'установлен' if UMP_USER else 'НЕ УСТАНОВЛЕН'}")
    info_lines.append(f"   UMP_PASS: {'установлен' if UMP_PASS else 'НЕ УСТАНОВЛЕН'}")
    
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
    user_id = update.effective_user.id
    selected_park = user_park_cache.get(user_id)
    info_lines.append(f"\n📍 ВЫБРАННЫЙ ПАРК: {selected_park or 'не выбран (все)'}")
    
    # Тест одного ТС
    info_lines.append(f"\n🧪 ТЕСТ ТС 6400:")
    try:
        if ensure_token_with_retry():
            result = get_position_and_check("6400")
            if result.get("ok"):
                info_lines.append(f"   ✅ OK: в парке={result.get('in_park')}, парк={result.get('park_name')}")
            else:
                info_lines.append(f"   ❌ Ошибка: {result.get('error')}")
        else:
            info_lines.append(f"   ❌ Не удалось получить токен")
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
    log_print(f"UMP_TOKEN_FILE: {UMP_TOKEN_FILE}")
    log_print(f"UMP_USER: {'установлен' if UMP_USER else 'НЕ УСТАНОВЛЕН'}")
    log_print(f"UMP_PASS: {'установлен' if UMP_PASS else 'НЕ УСТАНОВЛЕН'}")
    
    # Проверяем и создаем токен UMP при старте
    log_print("Проверяю токен UMP...")
    if not ensure_token_exists():
        log_print("Токен UMP не создан. Бот будет пытаться создать его при первом запросе.", "WARNING")
    else:
        log_print("Токен UMP готов")
    
    # Создаем Application
    log_print("Создаю Application...")
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    log_print("Регистрирую обработчики...")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("test", test_command))
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

