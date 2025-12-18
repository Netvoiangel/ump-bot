from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..services.access_control import (
    add_or_touch_request,
    allow_user,
    deny_user,
    get_request,
    is_allowed,
    is_denied,
    request_needs_text,
    set_request_text,
)
from ..services.settings import ADMIN_USER_ID


def _private_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("📨 Отправить заявку на доступ", callback_data="access_request")]]
    )


def private_text(user_id: int) -> str:
    return (
        "🔒 Этот бот приватный.\n\n"
        "Чтобы получить доступ, отправьте заявку — я передам её администратору.\n\n"
        f"Ваш Telegram ID: {user_id}\n"
        "Нажмите кнопку ниже:"
    )


def _admin_request_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Разрешить", callback_data=f"access_approve_{user_id}"),
                InlineKeyboardButton("⛔ Запретить", callback_data=f"access_deny_{user_id}"),
            ]
        ]
    )


async def reply_private(update: Update) -> None:
    uid = update.effective_user.id if update.effective_user else 0
    if is_denied(uid):
        await update.message.reply_text(
            "⛔ Доступ к боту запрещён.\n\nЕсли считаете, что это ошибка — свяжитесь с администратором."
        )
        return
    await update.message.reply_text(private_text(uid), reply_markup=_private_keyboard())


async def access_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    data = (q.data or "").strip()
    from_user = q.from_user
    from_uid = from_user.id

    # Пользователь нажал «Отправить заявку»
    if data == "access_request":
        if is_allowed(from_uid):
            await q.edit_message_text("✅ Доступ уже разрешён. Напишите /start.")
            return
        if is_denied(from_uid):
            await q.edit_message_text("⛔ Доступ запрещён. Если это ошибка — свяжитесь с администратором.")
            return

        r = add_or_touch_request(
            {
                "id": from_uid,
                "username": getattr(from_user, "username", None),
                "first_name": getattr(from_user, "first_name", None),
                "last_name": getattr(from_user, "last_name", None),
            },
            note="button_request",
        )

        # Если текста ещё нет — попросим написать одним сообщением
        if request_needs_text(from_uid):
            await q.edit_message_text(
                "📝 Ок, заявка создана.\n\n"
                "Одним сообщением отправьте:\n"
                "- ваше имя/должность\n"
                "- зачем нужен доступ\n"
                "- (опционально) контакт/отдел\n\n"
                f"Ваш Telegram ID: {from_uid}"
            )
        else:
            await q.edit_message_text("✅ Заявка уже отправлена и ждёт решения администратора.")
        return

    # Админские решения
    if data.startswith("access_approve_") or data.startswith("access_deny_"):
        if int(from_uid) != int(ADMIN_USER_ID):
            await q.answer("Недостаточно прав.", show_alert=True)
            return

        try:
            target_id = int(data.split("_")[-1])
        except Exception:
            await q.edit_message_text("❌ Некорректный формат запроса.")
            return

        if data.startswith("access_approve_"):
            allow_user(target_id, by_admin=from_uid)
            await q.edit_message_text(f"✅ Пользователь {target_id} добавлен в доступ.")
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="✅ Доступ к боту предоставлен. Напишите /start.",
                )
            except Exception:
                # пользователь мог не открыть диалог с ботом — это ок
                pass
            return

        deny_user(target_id, by_admin=from_uid)
        await q.edit_message_text(f"⛔ Пользователь {target_id} добавлен в запрет.")
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="⛔ Доступ к боту отклонён. Если это ошибка — свяжитесь с администратором.",
            )
        except Exception:
            pass
        return


async def maybe_accept_request_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Возвращает True, если сообщение было обработано как «текст заявки» и дальнейшую обработку делать не нужно.
    """
    if not update.effective_user or not update.message:
        return False
    uid = update.effective_user.id

    # если пользователь уже допущен — это точно не заявка
    if is_allowed(uid):
        return False

    # если он в бан-листе — отвечаем и прекращаем
    if is_denied(uid):
        await update.message.reply_text(
            "⛔ Доступ к боту запрещён.\n\nЕсли считаете, что это ошибка — свяжитесь с администратором."
        )
        return True

    # если есть «пустая» заявка — считаем это сообщение текстом заявки
    if request_needs_text(uid):
        txt = (update.message.text or "").strip()
        if not txt:
            await update.message.reply_text("Пожалуйста, отправьте текст заявки одним сообщением.")
            return True

        r = set_request_text(uid, txt)

        # уведомляем админа
        req = get_request(uid) or r
        username = req.get("username")
        name = " ".join([x for x in [req.get("first_name"), req.get("last_name")] if x]) or "—"
        who = f"{name} (@{username})" if username else name
        msg = (
            "📨 Новая заявка на доступ\n\n"
            f"👤 {who}\n"
            f"🆔 user_id: {uid}\n\n"
            f"📝 Текст:\n{txt}"
        )
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USER_ID,
                text=msg,
                reply_markup=_admin_request_keyboard(uid),
            )
        except Exception:
            # если админ не писал боту — отправка может не пройти
            pass

        await update.message.reply_text("✅ Заявка отправлена администратору. Ожидайте решения.")
        return True

    return False

