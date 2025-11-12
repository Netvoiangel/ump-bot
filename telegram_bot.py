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

load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS = os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if os.getenv("TELEGRAM_ALLOWED_USERS") else []
VEHICLES_FILE = os.getenv("VEHICLES_FILE", "vehicles.txt")
OUT_DIR = os.getenv("MAP_OUT_DIR", "out")
CACHE_DIR = os.getenv("MAP_CACHE_DIR", ".tile_cache")
MAX_IMAGE_SIZE = int(os.getenv("MAX_IMAGE_SIZE_MB", "10")) * 1024 * 1024  # 10MB по умолчанию

# Кэш выбранных парков для пользователей
user_park_cache: Dict[int, str] = {}


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
    
    try:
        result = get_position_and_check(depot_number)
        
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
    except Exception as e:
        logger.error(f"Error in status_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def map_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /map - рендер карты"""
    if not check_access(update.effective_user.id):
        return
    
    user_id = update.effective_user.id
    selected_park = user_park_cache.get(user_id)
    
    # Парсим номера ТС из аргументов или используем файл
    depot_numbers = []
    if context.args:
        depot_numbers = [d for d in context.args if d.isdigit()]
    
    # Если номеров нет, используем файл
    if not depot_numbers and os.path.exists(VEHICLES_FILE):
        sections = parse_vehicles_file_with_sections(VEHICLES_FILE)
        for category, numbers in sections.items():
            depot_numbers.extend(numbers)
        depot_numbers = list(set(depot_numbers))  # убираем дубликаты
    
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
        
        # Рендерим карту
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
        )
        
        if not files:
            await update.message.reply_text(
                "❌ Нет ТС внутри парков для отображения.\n"
                "Проверьте номера ТС или выберите другой парк: /parks"
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
        
    except Exception as e:
        logger.error(f"Error in map_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка генерации карты: {str(e)}")


def main() -> None:
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен в .env")
        return
    
    # Создаем Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("parks", parks_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("map", map_command))
    application.add_handler(CallbackQueryHandler(park_callback, pattern="^park_"))
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

