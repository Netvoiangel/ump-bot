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
from render_map import render_parks_with_vehicles, parse_vehicles_file_with_sections
from login_token import login_and_save
from config import UMP_TOKEN_FILE, UMP_USER, UMP_PASS

load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),  # Вывод в консоль
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Конфигурация
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS = os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if os.getenv("TELEGRAM_ALLOWED_USERS") else []
VEHICLES_FILE = os.getenv("VEHICLES_FILE", "vehicles.txt")
OUT_DIR = os.getenv("MAP_OUT_DIR", "out")
CACHE_DIR = os.getenv("MAP_CACHE_DIR", ".tile_cache")
MAX_IMAGE_SIZE = int(os.getenv("MAX_IMAGE_SIZE_MB", "10")) * 1024 * 1024  # 10MB по умолчанию

# Кэш выбранных парков для пользователей
user_park_cache: Dict[int, str] = {}


def ensure_token_exists() -> bool:
    """Проверяет наличие токена и создает его при необходимости"""
    logger.info(f"ensure_token_exists: проверяю {UMP_TOKEN_FILE}")
    token_path = Path(UMP_TOKEN_FILE)
    
    # Если токен существует, проверяем что он не пустой
    if token_path.exists():
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if token:
                    logger.info(f"Токен найден, длина: {len(token)}")
                    return True
                else:
                    logger.warning("Токен пустой")
        except Exception as e:
            logger.error(f"Ошибка чтения токена: {e}")
            pass
    else:
        logger.warning(f"Файл токена не существует: {UMP_TOKEN_FILE}")
    
    # Токена нет или он пустой - пытаемся создать
    if not UMP_USER or not UMP_PASS:
        logger.error("UMP_USER или UMP_PASS не установлены в .env. Автологин невозможен.")
        return False
    
    try:
        logger.info("Токен не найден, выполняю авторизацию...")
        login_and_save()
        logger.info("Авторизация успешна")
        return True
    except Exception as e:
        logger.error(f"Ошибка авторизации: {e}", exc_info=True)
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
    """Команда /map - рендер карты"""
    logger.info("=" * 50)
    logger.info("map_command вызван")
    
    if not check_access(update.effective_user.id):
        logger.warning(f"Доступ запрещен для user={update.effective_user.id}")
        return
    
    # Проверяем токен перед выполнением
    logger.info("Проверяю токен UMP...")
    if not ensure_token_with_retry():
        logger.error("Ошибка авторизации в UMP")
        await update.message.reply_text(
            "❌ Ошибка авторизации в UMP. Проверьте UMP_USER и UMP_PASS в .env"
        )
        return
    logger.info("Токен UMP готов")
    
    user_id = update.effective_user.id
    selected_park = user_park_cache.get(user_id)
    logger.info(f"map_command: user={user_id}, park={selected_park}, args={context.args}")
    
    # Парсим номера ТС из аргументов или используем файл
    depot_numbers = []
    if context.args:
        depot_numbers = [d for d in context.args if d.isdigit()]
        logger.info(f"Номера из аргументов: {depot_numbers}")
    
    # Если номеров нет, используем файл
    if not depot_numbers and os.path.exists(VEHICLES_FILE):
        logger.info(f"Читаю файл {VEHICLES_FILE}")
        sections = parse_vehicles_file_with_sections(VEHICLES_FILE)
        for category, numbers in sections.items():
            depot_numbers.extend(numbers)
        depot_numbers = list(set(depot_numbers))  # убираем дубликаты
        logger.info(f"Номера из файла: {len(depot_numbers)} ТС")
    
    if not depot_numbers:
        await update.message.reply_text(
            "❌ Не указаны номера ТС и файл vehicles.txt не найден.\n"
            "Использование: /map [номера] или создайте vehicles.txt"
        )
        return
    
    # Ограничение количества ТС для слабого сервера
    if len(depot_numbers) > 50:
        depot_numbers = depot_numbers[:50]
        await update.message.reply_text(
            f"⚠️ Обрабатывается только первые 50 ТС из {len(depot_numbers)}"
        )
    
    await update.message.reply_text("🔄 Генерирую карту... Это может занять время.")
    
    try:
        # Создаем color_map из файла, если есть
        color_map = None
        if os.path.exists(VEHICLES_FILE):
            sections = parse_vehicles_file_with_sections(VEHICLES_FILE)
            if sections:
                def get_category_color(cat: str):
                    cat_lower = cat.lower()
                    if "проверка гк" in cat_lower:
                        return "#ffd43b", "#fab005"
                    elif "заявки redmine" in cat_lower or "redmine" in cat_lower:
                        return "#4dabf7", "#339af0"
                    elif "текущие задачи" in cat_lower:
                        return "#ff922b", "#fd7e14"
                    elif "перенос камеры" in cat_lower or "камера" in cat_lower:
                        return "#9775fa", "#845ef7"
                    else:
                        return "#fa5252", "#c92a2a"
                
                color_map = {}
                for category, numbers in sections.items():
                    fill, outline = get_category_color(category)
                    for num in numbers:
                        color_map[num] = (fill, outline)
        
        # Сначала проверяем статус ТС для отладки
        logger.info(f"Проверяю статус {len(depot_numbers)} ТС...")
        sample_results = []
        for i, dep_num in enumerate(depot_numbers[:5]):  # Проверяем первые 5 для отладки
            try:
                result = get_position_and_check(dep_num)
                sample_results.append(result)
                logger.info(f"ТС {dep_num}: ok={result.get('ok')}, in_park={result.get('in_park')}, park={result.get('park_name')}")
            except Exception as e:
                logger.error(f"Ошибка проверки ТС {dep_num}: {e}")
        
        # Рендерим карту
        logger.info(f"Рендеринг карты: {len(depot_numbers)} ТС, парк={selected_park}")
        files = render_parks_with_vehicles(
            depot_numbers=depot_numbers,
            out_dir=OUT_DIR,
            size="1200x800",  # Оптимизированный размер для слабого сервера
            use_real_map=True,
            zoom=17,  # Можно снизить до 16 для экономии ресурсов
            tile_provider=os.getenv("MAP_PROVIDER", ""),
            tile_cache=CACHE_DIR,
            tile_user_agent=os.getenv("MAP_USER_AGENT", ""),
            tile_referer=os.getenv("MAP_REFERER", ""),
            tile_apikey=os.getenv("MAPTILER_API_KEY", ""),
            tile_rate_tps=3.0,  # Снижено для слабого сервера
            park_filter=selected_park,
            color_map=color_map,
            debug=True,  # Включаем отладку
        )
        logger.info(f"Сгенерировано файлов: {len(files) if files else 0}")
        
        if not files:
            # Подробная информация для отладки
            in_park_count = sum(1 for r in sample_results if r.get('ok') and r.get('in_park'))
            error_count = sum(1 for r in sample_results if not r.get('ok'))
            logger.warning(
                f"Нет файлов для отправки. "
                f"ТС: {len(depot_numbers)}, "
                f"Парк: {selected_park}, "
                f"В парке (из 5 проверенных): {in_park_count}, "
                f"Ошибок: {error_count}"
            )
            
            # Формируем детальное сообщение
            debug_info = f"Обработано ТС: {len(depot_numbers)}\n"
            debug_info += f"Парк: {selected_park or 'все'}\n"
            if sample_results:
                debug_info += f"\nПримеры (первые 5):\n"
                for r in sample_results[:3]:
                    if r.get('ok'):
                        status = "✅ в парке" if r.get('in_park') else "❌ вне парка"
                        debug_info += f"  ТС {r.get('depot_number')}: {status} ({r.get('park_name') or '—'})\n"
                    else:
                        debug_info += f"  ТС {r.get('depot_number')}: ошибка {r.get('error')}\n"
            
            await update.message.reply_text(
                f"❌ Нет ТС внутри парков для отображения.\n\n{debug_info}\n"
                f"Попробуйте: /parks для выбора парка или /status [номер] для проверки ТС"
            )
            return
        
        # Отправляем изображения
        for file_path in files:
            try:
                file_size = os.path.getsize(file_path)
                if file_size > MAX_IMAGE_SIZE:
                    await update.message.reply_text(
                        f"⚠️ Изображение слишком большое ({file_size // 1024 // 1024}MB). "
                        f"Попробуйте указать меньше ТС."
                    )
                    continue
                
                with open(file_path, "rb") as photo:
                    park_name = Path(file_path).stem.replace("park_", "")
                    caption = f"📍 Парк: {park_name}\n🚌 ТС: {len(depot_numbers)}"
                    await update.message.reply_photo(photo=photo, caption=caption)
            except Exception as e:
                logger.error(f"Error sending image {file_path}: {e}", exc_info=True)
                await update.message.reply_text(f"❌ Ошибка отправки изображения: {str(e)}")
        
    except FileNotFoundError as e:
        if "ump_token" in str(e) or "token" in str(e).lower():
            logger.error(f"Token file not found: {e}", exc_info=True)
            await update.message.reply_text("🔄 Токен не найден, пытаюсь авторизоваться...")
            if ensure_token_with_retry():
                await update.message.reply_text("✅ Авторизация успешна. Попробуйте команду снова.")
            else:
                await update.message.reply_text("❌ Ошибка авторизации. Проверьте настройки.")
        else:
            logger.error(f"File not found: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Файл не найден: {str(e)}")
    except Exception as e:
        logger.error(f"Error in map_command: {e}", exc_info=True)
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        await update.message.reply_text(f"❌ Ошибка генерации карты: {str(e)}")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений в формате vehicles.txt"""
    logger.info(f"text_handler вызван: user={update.effective_user.id}")
    
    if not check_access(update.effective_user.id):
        logger.warning(f"Доступ запрещен для user={update.effective_user.id}")
        return
    
    if not update.message or not update.message.text:
        logger.warning("Нет текста в сообщении")
        return
    
    text = update.message.text.strip()
    logger.info(f"Получен текст ({len(text)} символов): {text[:100]}...")
    
    # Пропускаем команды
    if text.startswith("/"):
        logger.debug("Пропущена команда")
        return
    
    # Парсим текст как vehicles.txt
    try:
        # Создаем временный файл
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(text)
            temp_file = f.name
        
        # Парсим секции
        sections = parse_vehicles_file_with_sections(temp_file)
        depot_numbers = []
        for category, numbers in sections.items():
            depot_numbers.extend(numbers)
        depot_numbers = list(set(depot_numbers))
        
        # Удаляем временный файл
        os.unlink(temp_file)
        
        if not depot_numbers:
            await update.message.reply_text("❌ Не найдено номеров ТС в сообщении.")
            return
        
        logger.info(f"Парсинг текста: найдено {len(depot_numbers)} ТС")
        
        # Вызываем map_command с этими номерами
        # Создаем фейковый context с аргументами
        class FakeContext:
            def __init__(self, args):
                self.args = args
        
        fake_context = FakeContext(depot_numbers)
        await map_command(update, fake_context)
        
    except Exception as e:
        logger.error(f"Error parsing text: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка парсинга текста: {str(e)}")


def main() -> None:
    """Запуск бота"""
    logger.info("=" * 60)
    logger.info("ЗАПУСК БОТА")
    logger.info("=" * 60)
    
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен в .env")
        return
    
    logger.info(f"BOT_TOKEN установлен (длина: {len(BOT_TOKEN)})")
    logger.info(f"VEHICLES_FILE: {VEHICLES_FILE} (существует: {os.path.exists(VEHICLES_FILE)})")
    logger.info(f"OUT_DIR: {OUT_DIR}")
    logger.info(f"CACHE_DIR: {CACHE_DIR}")
    
    # Проверяем и создаем токен UMP при старте
    logger.info("Проверяю токен UMP...")
    if not ensure_token_exists():
        logger.warning("Токен UMP не создан. Бот будет пытаться создать его при первом запросе.")
    else:
        logger.info("Токен UMP готов")
    
    # Создаем Application
    logger.info("Создаю Application...")
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    logger.info("Регистрирую обработчики...")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("parks", parks_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("map", map_command))
    application.add_handler(CallbackQueryHandler(park_callback, pattern="^park_"))
    # Обработчик текстовых сообщений (для формата vehicles.txt) - должен быть последним
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    logger.info("Обработчики зарегистрированы")
    
    # Запускаем бота
    logger.info("=" * 60)
    logger.info("БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ")
    logger.info("=" * 60)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

