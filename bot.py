from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters, CallbackQueryHandler
)
from config import BOT_TOKEN
from storage import add_booking, get_user_bookings, get_bookings_by_date, cancel_booking, is_time_available
from datetime import datetime, timedelta

# Состояния диалога
DATE, TIME_START, TIME_END, COMMENT, CANCEL_ID = range(5)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["📅 Забронировать", "❌ Отменить бронь"], ["📋 Мои брони", "📆 Брони на день"]],
    resize_keyboard=True
)


# ─── /start ───────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для бронирования переговорной комнаты.\n\nВыберите действие:",
        reply_markup=MAIN_KEYBOARD
    )


def date_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    today = datetime.now()
    buttons = []
    row = []
    start = page * 15
    end = start + 15

    for i in range(start, end):
        day = today + timedelta(days=i)
        label = day.strftime("%d.%m")
        if i == 0:
            label = f"📍{label}"
        row.append(InlineKeyboardButton(label, callback_data=f"date_{day.strftime('%d.%m.%Y')}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Навигация
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Назад", callback_data=f"datepage_{page - 1}"))
    nav.append(InlineKeyboardButton(f"▶️ Вперёд", callback_data=f"datepage_{page + 1}"))
    buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📅 Выберите дату бронирования:",
        reply_markup=date_keyboard(0)
    )
    return DATE


from telegram.error import BadRequest


async def book_date_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.replace("datepage_", ""))
    try:
        await query.edit_message_reply_markup(reply_markup=date_keyboard(page))
    except BadRequest:
        pass
    return DATE


async def book_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date = query.data.replace("date_", "")
    context.user_data["date"] = date

    await query.edit_message_text(
        f"📅 Дата выбрана: *{date}*\n\n🕐 *Выберите время начала:*",
        parse_mode="Markdown",
        reply_markup=time_slots_keyboard("ts")
    )
    return TIME_START


def time_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def time_slots_keyboard(prefix: str, selected: str = None, start_time: str = None) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for h in range(9, 18):
        for m in (0, 30):
            t = f"{h:02d}:{m:02d}"
            # Пропускаем слоты раньше или равные времени начала
            if start_time and time_to_minutes(t) <= time_to_minutes(start_time):
                continue
            label = f"✅ {t}" if t == selected else t
            row.append(InlineKeyboardButton(label, callback_data=f"{prefix}_{t}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


async def book_time_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    time = query.data.replace("ts_", "")
    context.user_data["time_start"] = time

    await query.edit_message_text(
        f"📅 Дата: *{context.user_data['date']}*\n"
        f"✅ Начало: *{time}*\n\n"
        f"🕕 *Выберите время окончания:*",
        parse_mode="Markdown",
        reply_markup=time_slots_keyboard("te", start_time=time)
    )
    return TIME_END


async def book_time_end_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    time_end = query.data.replace("te_", "")
    time_start = context.user_data["time_start"]
    date = context.user_data["date"]

    if not is_time_available(date, time_start, time_end):
        await query.edit_message_text(
            f"❌ *{time_start}–{time_end}* уже занято!\n\n"
            f"📅 Дата: *{date}*\n\n"
            f"🕐 *Выберите другое время начала:*",
            parse_mode="Markdown",
            reply_markup=time_slots_keyboard("ts")
        )
        return TIME_START

    context.user_data["time_end"] = time_end
    await query.edit_message_text(
        f"📅 Дата: *{date}*\n"
        f"✅ Начало: *{time_start}*\n"
        f"✅ Конец:  *{time_end}*\n\n"
        f"💬 Добавьте комментарий или отправьте /skip",
        parse_mode="Markdown"
    )
    return COMMENT


async def book_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment = "" if update.message.text == "/skip" else update.message.text.strip()
    user = update.effective_user
    d = context.user_data

    booking_id = add_booking(
        d["date"], d["time_start"], d["time_end"],
        user.id, user.username or user.first_name, comment
    )

    await update.message.reply_text(
        f"✅ *Бронирование подтверждено!*\n\n"
        f"🆔 ID: `{booking_id}`\n"
        f"📅 Дата: {d['date']}\n"
        f"🕐 Время: {d['time_start']} — {d['time_end']}\n"
        f"💬 Тема: {comment or '—'}",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD
    )
    return ConversationHandler.END


# ─── МОИ БРОНИ ────────────────────────────────────────────
async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bookings = get_user_bookings(user_id)

    if not bookings:
        await update.message.reply_text("📭 У вас нет активных бронирований.")
        return

    text = "📋 *Ваши бронирования:*\n\n"
    for b in bookings:
        text += f"🆔 `{b['id']}` | {b['date']} | {b['time_start']}–{b['time_end']}"
        if b.get("comment"):
            text += f" | {b['comment']}"
        text += "\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# ─── БРОНИ НА ДЕНЬ ────────────────────────────────────────
async def bookings_today_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now()
    buttons = []
    row = []

    for i in range(0, 15):
        day = today + timedelta(days=i)
        label = day.strftime("%d.%m")
        if i == 0:
            label = f"📍{label}"
        callback = day.strftime("%d.%m.%Y")
        row.append(InlineKeyboardButton(label, callback_data=f"view_{callback}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await update.message.reply_text(
        "📆 Выберите дату для просмотра броней:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return DATE


async def bookings_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date = query.data.replace("view_", "")
    bookings = get_bookings_by_date(date)

    if not bookings:
        await query.edit_message_text(
            f"📭 На *{date}* бронирований нет. Комната свободна! 🟢",
            parse_mode="Markdown"
        )
    else:
        text = f"📆 *Бронирования на {date}:*\n\n"
        for b in sorted(bookings, key=lambda x: x["time_start"]):
            text += f"🕐 {b['time_start']}–{b['time_end']} | @{b['username']}"
            if b.get("comment"):
                text += f" | _{b['comment']}_"
            text += "\n"
        await query.edit_message_text(text, parse_mode="Markdown")

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите действие:",
        reply_markup=MAIN_KEYBOARD
    )
    return ConversationHandler.END


# ─── ОТМЕНА БРОНИ ─────────────────────────────────────────
async def cancel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bookings = get_user_bookings(user_id)

    if not bookings:
        await update.message.reply_text(
            "📭 У вас нет активных бронирований.",
            reply_markup=MAIN_KEYBOARD
        )
        return ConversationHandler.END

    buttons = []
    for b in bookings:
        label = f"🗑 {b['date']} {b['time_start']}–{b['time_end']}"
        if b.get("comment"):
            label += f" ({b['comment']})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"cancel_{b['id']}")])

    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="cancel_back")])

    await update.message.reply_text(
        "❌ Выберите бронирование для отмены:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return CANCEL_ID


async def cancel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_back":
        await query.edit_message_text("Действие отменено.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите действие:",
            reply_markup=MAIN_KEYBOARD
        )
        return ConversationHandler.END

    booking_id = query.data.replace("cancel_", "")
    user_id = update.effective_user.id

    if cancel_booking(booking_id, user_id):
        await query.edit_message_text(
            f"✅ Бронирование `{booking_id}` отменено.",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text("❌ Не удалось отменить бронирование.")

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите действие:",
        reply_markup=MAIN_KEYBOARD
    )
    return ConversationHandler.END


async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Диалог: создание брони
    book_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("📅 Забронировать"), book_start)],
        states={
            DATE: [CallbackQueryHandler(book_date, pattern="^date_"),
                   CallbackQueryHandler(book_date_page, pattern="^datepage_"), ],
            TIME_START: [CallbackQueryHandler(book_time_start_cb, pattern="^ts_")],
            TIME_END: [CallbackQueryHandler(book_time_end_cb, pattern="^te_")],
            COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, book_comment),
                CommandHandler("skip", book_comment)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )

    # Диалог: брони на день
    date_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("📆 Брони на день"), bookings_today_start)],
        states={
            DATE: [CallbackQueryHandler(bookings_by_date, pattern="^view_")],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )

    # Диалог: отмена брони
    cancel_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("❌ Отменить бронь"), cancel_start)],
        states={
            CANCEL_ID: [CallbackQueryHandler(cancel_confirm, pattern="^cancel_")],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(book_conv)
    app.add_handler(date_conv)
    app.add_handler(cancel_conv_handler)
    app.add_handler(MessageHandler(filters.Regex("📋 Мои брони"), my_bookings))

    print("🤖 Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
