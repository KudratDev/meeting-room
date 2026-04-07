from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
from config import BOT_TOKEN
from storage import add_booking, get_user_bookings, get_bookings_by_date, cancel_booking, is_time_available
from datetime import datetime, timedelta

# Состояния диалога
DATE, TIME_START, TIME_END, COMMENT, CANCEL_ID = range(5)


# ─── /start ───────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["📅 Забронировать", "❌ Отменить бронь"],
        ["📋 Мои брони", "📆 Брони на день"]
    ]
    await update.message.reply_text(
        "👋 Привет! Я бот для бронирования переговорной комнаты.\n\nВыберите действие:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )


async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now()
    buttons = []
    row = []

    for i in range(-15, 16):
        day = today + timedelta(days=i)
        label = day.strftime("%d.%m")
        if i == 0:
            label = f"📍 {label}"  # отмечаем сегодня
        callback = day.strftime("%d.%m.%Y")
        row.append(InlineKeyboardButton(label, callback_data=f"date_{callback}"))
        if len(row) == 5:  # 5 кнопок в строке
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await update.message.reply_text(
        "📅 Выберите дату бронирования:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return DATE


async def book_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date = query.data.replace("date_", "")
    context.user_data["date"] = date

    await query.edit_message_text(f"📅 Дата: {date}\n\n🕐 Введите время начала (формат ЧЧ:ММ)\nПример: 10:00")
    return TIME_START


async def book_time_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        datetime.strptime(update.message.text.strip(), "%H:%M")
        context.user_data["time_start"] = update.message.text.strip()
        await update.message.reply_text("🕐 Введите время окончания (формат ЧЧ:ММ)\nПример: 11:00")
        return TIME_END
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Попробуйте ещё раз (ЧЧ:ММ):")
        return TIME_START


async def book_time_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        time_end = update.message.text.strip()
        datetime.strptime(time_end, "%H:%M")
        date = context.user_data["date"]
        time_start = context.user_data["time_start"]

        if time_end <= time_start:
            await update.message.reply_text("❌ Время окончания должно быть позже начала. Попробуйте ещё раз:")
            return TIME_END

        if not is_time_available(date, time_start, time_end):
            await update.message.reply_text("❌ Это время уже занято! Выберите другое время.\nВремя начала:")
            return TIME_START

        context.user_data["time_end"] = time_end
        await update.message.reply_text("💬 Добавьте комментарий (тема встречи) или отправьте /skip")
        return COMMENT
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Попробуйте ещё раз (ЧЧ:ММ):")
        return TIME_END


async def book_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment = update.message.text.strip() if update.message.text != "/skip" else ""
    user = update.effective_user
    d = context.user_data

    booking_id = add_booking(d["date"], d["time_start"], d["time_end"],
                             user.id, user.username or user.first_name, comment)

    keyboard = [["📅 Забронировать", "❌ Отменить бронь"], ["📋 Мои брони", "📆 Брони на день"]]
    await update.message.reply_text(
        f"✅ Бронирование подтверждено!\n\n"
        f"🆔 ID: `{booking_id}`\n"
        f"📅 Дата: {d['date']}\n"
        f"🕐 Время: {d['time_start']} — {d['time_end']}\n"
        f"💬 Тема: {comment or '—'}",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
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
    today = datetime.now().strftime("%d.%m.%Y")
    await update.message.reply_text(
        f"📆 Введите дату (ДД.ММ.ГГГГ) или отправьте /today для просмотра на сегодня ({today}):"
    )
    return DATE


async def bookings_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "/today":
        date = datetime.now().strftime("%d.%m.%Y")
    else:
        try:
            date = datetime.strptime(update.message.text.strip(), "%d.%m.%Y").strftime("%d.%m.%Y")
        except ValueError:
            await update.message.reply_text("❌ Неверный формат. Попробуйте ещё раз (ДД.ММ.ГГГГ):")
            return DATE

    bookings = get_bookings_by_date(date)
    keyboard = [["📅 Забронировать", "❌ Отменить бронь"], ["📋 Мои брони", "📆 Брони на день"]]

    if not bookings:
        await update.message.reply_text(
            f"📭 На {date} бронирований нет. Комната свободна!",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    else:
        text = f"📆 *Бронирования на {date}:*\n\n"
        for b in sorted(bookings, key=lambda x: x["time_start"]):
            text += f"🕐 {b['time_start']}–{b['time_end']} | @{b['username']}"
            if b.get("comment"):
                text += f" | {b['comment']}"
            text += "\n"
        await update.message.reply_text(
            text, parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    return ConversationHandler.END


# ─── ОТМЕНА БРОНИ ─────────────────────────────────────────
async def cancel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Введите ID бронирования для отмены.\nПосмотреть свои ID: нажмите '📋 Мои брони'",
        reply_markup=ReplyKeyboardRemove()
    )
    return CANCEL_ID


async def cancel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    booking_id = update.message.text.strip().upper()
    user_id = update.effective_user.id
    keyboard = [["📅 Забронировать", "❌ Отменить бронь"], ["📋 Мои брони", "📆 Брони на день"]]

    if cancel_booking(booking_id, user_id):
        await update.message.reply_text(
            f"✅ Бронирование `{booking_id}` отменено.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    else:
        await update.message.reply_text(
            "❌ Бронирование не найдено или вы не являетесь его владельцем.",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    return ConversationHandler.END


async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📅 Забронировать", "❌ Отменить бронь"], ["📋 Мои брони", "📆 Брони на день"]]
    await update.message.reply_text(
        "Действие отменено.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return ConversationHandler.END


# ─── MAIN ─────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Диалог: создание брони
    book_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("📅 Забронировать"), book_start)],
        states={
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, book_date)],
            TIME_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, book_time_start)],
            TIME_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, book_time_end)],
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
            DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bookings_by_date),
                CommandHandler("today", bookings_by_date)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )

    # Диалог: отмена брони
    cancel_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("❌ Отменить бронь"), cancel_start)],
        states={
            CANCEL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_confirm)],
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
