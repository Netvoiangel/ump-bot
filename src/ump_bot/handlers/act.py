import logging
from datetime import date
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from ..infra.otbivka import load_parks
from ..services import auth
from ..services.warranty_act import (
    get_executor_name,
    save_executor_name,
    generate_warranty_act,
    validate_date_str,
)
from ..domain.warranty_act import WarrantyActData
from ..services.state import user_park_cache
from ..services.settings import ALLOWED_USER_IDS

logger = logging.getLogger("ump_bot")

# Состояния FSM
(
    AWAIT_PARK,
    AWAIT_DATE,
    AWAIT_ADDRESS,
    AWAIT_REQUEST_NO,
    AWAIT_LICENSE_PLATE,
    AWAIT_GARAGE_NO,
    AWAIT_FAULT,
    AWAIT_DIAGNOSTIC,
    AWAIT_WORKS,
    AWAIT_EXECUTOR,
    AWAIT_VALIDATOR_TYPE,
    AWAIT_OLD_VALIDATOR_SN,
    AWAIT_NEW_VALIDATOR_SN,
    AWAIT_OLD_SAM_SN,
    AWAIT_NEW_SAM_SN,
    AWAIT_OLD_SAM_ACT,
    AWAIT_NEW_SAM_ACT,
    AWAIT_CONFIRM,
) = range(18)

VALIDATOR_TYPES = ["BM-20", "BM-20 QR", "BM-20 A"]

async def act_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало процесса заполнения акта."""
    user_id = update.effective_user.id
    if not auth.check_access(user_id, ALLOWED_USER_IDS):
        return ConversationHandler.END

    context.user_data['act'] = {}
    
    # Проверка выбранного парка
    park_name = user_park_cache.get(user_id)
    if not park_name or park_name == "all":
        parks = load_parks()
        keyboard = [[InlineKeyboardButton(p["name"], callback_data=f"act_park_{p['name']}")] for p in parks]
        await update.message.reply_text(
            "📍 Для начала выберите парк:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return AWAIT_PARK
    
    context.user_data['act']['park_name'] = park_name
    return await ask_date(update, context)

async def park_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора парка через callback."""
    query = update.callback_query
    await query.answer()
    
    park_name = query.data.replace("act_park_", "")
    user_id = query.from_user.id
    user_park_cache[user_id] = park_name
    context.user_data['act']['park_name'] = park_name
    
    await query.edit_message_text(f"✅ Выбран парк: {park_name}")
    return await ask_date(query, context, is_query=True)

async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE, is_query=False) -> int:
    """Запрос даты акта."""
    today = date.today().strftime("%d.%m.%Y")
    reply_markup = ReplyKeyboardMarkup([[today]], one_time_keyboard=True, resize_keyboard=True)
    
    msg_text = f"📅 Введите дату акта (ДД.ММ.ГГГГ) или выберите сегодня ({today}):"
    if is_query:
        await context.bot.send_message(update.from_user.id, msg_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg_text, reply_markup=reply_markup)
    return AWAIT_DATE

async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка введенной даты."""
    text = update.message.text
    dt = validate_date_str(text)
    if not dt:
        await update.message.reply_text("❌ Неверный формат даты. Введите в формате ДД.ММ.ГГГГ (например, 31.01.2026):")
        return AWAIT_DATE
    
    context.user_data['act']['act_date'] = dt.date()
    # По ТЗ: даты предоставления и окончания равны дате акта
    context.user_data['act']['start_date'] = dt.date()
    context.user_data['act']['end_date'] = dt.date()
    
    return await ask_address(update, context)

async def ask_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос адреса выполнения работ."""
    park_name = context.user_data['act']['park_name']
    parks = load_parks()
    park = next((p for p in parks if p['name'] == park_name), None)
    
    if not park or not park.get('address_default'):
        await update.message.reply_text(
            f"❌ У парка '{park_name}' не задан адрес в конфигурации. Продолжение невозможно.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    addresses = park.get('addresses', [park['address_default']])
    keyboard = [[addr] for addr in addresses]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        f"🏠 Выберите адрес выполнения работ или введите свой:",
        reply_markup=reply_markup
    )
    return AWAIT_ADDRESS

async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка адреса."""
    context.user_data['act']['address'] = update.message.text
    await update.message.reply_text("🔢 Введите номер заявки:", reply_markup=ReplyKeyboardRemove())
    return AWAIT_REQUEST_NO

async def handle_request_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка номера заявки."""
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ Номер заявки не может быть пустым. Введите номер:")
        return AWAIT_REQUEST_NO
    context.user_data['act']['request_no'] = text
    await update.message.reply_text("🆔 Введите госномер ТС:")
    return AWAIT_LICENSE_PLATE

async def handle_license_plate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка госномера."""
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ Госномер не может быть пустым. Введите госномер:")
        return AWAIT_LICENSE_PLATE
    context.user_data['act']['license_plate'] = text
    await update.message.reply_text("🚌 Введите гаражный номер ТС:")
    return AWAIT_GARAGE_NO

async def handle_garage_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка гаражного номера."""
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ Гаражный номер не может быть пустым. Введите номер:")
        return AWAIT_GARAGE_NO
    context.user_data['act']['garage_no'] = text
    await update.message.reply_text("❓ Заявленная неисправность:")
    return AWAIT_FAULT

async def handle_fault(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка неисправности."""
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ Поле не может быть пустым. Введите описание:")
        return AWAIT_FAULT
    context.user_data['act']['reported_fault'] = text
    await update.message.reply_text("🔍 Результат диагностики:")
    return AWAIT_DIAGNOSTIC

async def handle_diagnostic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка результата диагностики."""
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ Поле не может быть пустым. Введите описание:")
        return AWAIT_DIAGNOSTIC
    context.user_data['act']['diagnostic_result'] = text
    await update.message.reply_text("🛠 Выполненные работы:")
    return AWAIT_WORKS

async def handle_works(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выполненных работ."""
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ Поле не может быть пустым. Введите описание:")
        return AWAIT_WORKS
    context.user_data['act']['performed_works'] = text
    
    # Проверка ФИО исполнителя
    user_id = update.effective_user.id
    executor = get_executor_name(user_id)
    if executor:
        context.user_data['act']['executor_name'] = executor
        return await ask_validator_type(update, context)
    
    await update.message.reply_text("👤 Введите ФИО исполнителя (один раз, будет сохранено):")
    return AWAIT_EXECUTOR

async def handle_executor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ФИО исполнителя."""
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ ФИО не может быть пустым. Введите ФИО:")
        return AWAIT_EXECUTOR
    
    user_id = update.effective_user.id
    save_executor_name(user_id, text)
    context.user_data['act']['executor_name'] = text
    return await ask_validator_type(update, context)

async def ask_validator_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос типа валидатора."""
    reply_markup = ReplyKeyboardMarkup([[t] for t in VALIDATOR_TYPES], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("📟 Выберите тип валидатора:", reply_markup=reply_markup)
    return AWAIT_VALIDATOR_TYPE

async def handle_validator_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка типа валидатора."""
    text = update.message.text
    if text not in VALIDATOR_TYPES:
        await update.message.reply_text("❌ Выберите тип из списка:")
        return AWAIT_VALIDATOR_TYPE
    
    context.user_data['act']['validator_type'] = text
    await update.message.reply_text("🔢 Серийный номер ДЕМОНТИРОВАННОГО валидатора:", reply_markup=ReplyKeyboardRemove())
    return AWAIT_OLD_VALIDATOR_SN

async def handle_old_validator_sn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['act']['old_validator_sn'] = update.message.text.strip()
    await update.message.reply_text("🔢 Серийный номер СМОНТИРОВАННОГО валидатора:")
    return AWAIT_NEW_VALIDATOR_SN

async def handle_new_validator_sn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['act']['new_validator_sn'] = update.message.text.strip()
    await update.message.reply_text("🔢 Серийный номер СТАРОГО SAM:")
    return AWAIT_OLD_SAM_SN

async def handle_old_sam_sn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['act']['old_sam_sn'] = update.message.text.strip()
    await update.message.reply_text("🔢 Серийный номер НОВОГО SAM:")
    return AWAIT_NEW_SAM_SN

async def handle_new_sam_sn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['act']['new_sam_sn'] = update.message.text.strip()
    reply_markup = ReplyKeyboardMarkup([["Пропустить"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("🔢 Номер активации СТАРОГО SAM (опционально):", reply_markup=reply_markup)
    return AWAIT_OLD_SAM_ACT

async def handle_old_sam_act(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data['act']['old_sam_activation_no'] = "-" if text.lower() == "пропустить" else text
    reply_markup = ReplyKeyboardMarkup([["Пропустить"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("🔢 Номер активации НОВОГО SAM (опционально):", reply_markup=reply_markup)
    return AWAIT_NEW_SAM_ACT

async def handle_new_sam_act(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data['act']['new_sam_activation_no'] = "-" if text.lower() == "пропустить" else text
    return await show_preview(update, context)

async def show_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показ сводки перед генерацией."""
    data = context.user_data['act']
    preview = (
        "📝 **Сводка данных акта:**\n\n"
        f"📅 Дата: {data['act_date'].strftime('%d.%m.%Y')}\n"
        f"📍 Парк: {data['park_name']}\n"
        f"🏠 Адрес: {data['address']}\n"
        f"🔢 Заявка: {data['request_no']}\n"
        f"🚌 ТС: {data['license_plate']} ({data['garage_no']})\n"
        f"📟 Валидатор: {data['validator_type']}\n"
        f"SN Старый: {data['old_validator_sn']}\n"
        f"SN Новый: {data['new_validator_sn']}\n"
        f"SAM Старый: {data['old_sam_sn']} ({data['old_sam_activation_no']})\n"
        f"SAM Новый: {data['new_sam_sn']} ({data['new_sam_activation_no']})\n"
        f"👤 Исполнитель: {data['executor_name']}\n"
        f"❓ Неисправность: {data['reported_fault']}\n"
        f"🔍 Диагностика: {data['diagnostic_result']}\n"
        f"🛠 Работы: {data['performed_works']}"
    )
    
    reply_markup = ReplyKeyboardMarkup([["Сгенерировать"], ["Изменить"], ["Отмена"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(preview, reply_markup=reply_markup, parse_mode='Markdown')
    return AWAIT_CONFIRM

async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка финального подтверждения."""
    text = update.message.text
    if text == "Сгенерировать":
        await update.message.reply_text("⏳ Генерирую файл...", reply_markup=ReplyKeyboardRemove())
        try:
            act_data = WarrantyActData(**context.user_data['act'])
            file_path = generate_warranty_act(act_data)
            await update.message.reply_document(document=open(file_path, 'rb'))
            return ConversationHandler.END
        except Exception as e:
            logger.exception("Ошибка при генерации акта")
            await update.message.reply_text(f"❌ Не удалось сформировать акт: {e}")
            return ConversationHandler.END
    elif text == "Изменить":
        # Для упрощения возвращаемся к началу (дате)
        # В идеале можно сделать выбор поля, но по ТЗ "как удобнее"
        await update.message.reply_text("🔄 Начнем сначала.")
        return await ask_date(update, context)
    else:
        return await cancel(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена процесса."""
    await update.message.reply_text("❌ Заполнение акта отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

act_handler = ConversationHandler(
    entry_points=[CommandHandler("act", act_command)],
    states={
        AWAIT_PARK: [CallbackQueryHandler(park_selection_callback, pattern="^act_park_")],
        AWAIT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date)],
        AWAIT_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address)],
        AWAIT_REQUEST_NO: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_request_no)],
        AWAIT_LICENSE_PLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_license_plate)],
        AWAIT_GARAGE_NO: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_garage_no)],
        AWAIT_FAULT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_fault)],
        AWAIT_DIAGNOSTIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_diagnostic)],
        AWAIT_WORKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_works)],
        AWAIT_EXECUTOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_executor)],
        AWAIT_VALIDATOR_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_validator_type)],
        AWAIT_OLD_VALIDATOR_SN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_old_validator_sn)],
        AWAIT_NEW_VALIDATOR_SN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_validator_sn)],
        AWAIT_OLD_SAM_SN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_old_sam_sn)],
        AWAIT_NEW_SAM_SN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_sam_sn)],
        AWAIT_OLD_SAM_ACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_old_sam_act)],
        AWAIT_NEW_SAM_ACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_sam_act)],
        AWAIT_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirm)],
    },
    fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^Отмена$"), cancel)],
)
