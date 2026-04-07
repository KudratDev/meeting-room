from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters, CallbackQueryHandler
)
from telegram.error import BadRequest
from config import BOT_TOKEN
from storage import add_booking, get_user_bookings, get_bookings_by_date, cancel_booking, is_time_available, \
    get_booked_slots
from languages import t
from datetime import datetime, timedelta

LANG, DATE, TIME_START, TIME_END, COMMENT, CANCEL_ID = range(6)


def get_lang(context) -> str:
    return context.user_data.get("lang", "ru")


def main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[t(lang, "btn_book"), t(lang, "btn_cancel")],
         [t(lang, "btn_my"), t(lang, "btn_day")]],
        resize_keyboard=True
    )


def time_to_minutes(ts: str) -> int:
    h, m = map(int, ts.split(":"))
    return h * 60 + m


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇺🇿 Ўзбекча", callback_data="lang_uz"),
    ]])
    await update.message.reply_text("🌐 Выберите язык / Tilni tanlang:", reply_markup=keyboard)
    return LANG


async def choose_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.replace("lang_", "")
    context.user_data["lang"] = lang
    await query.edit_message_text(t(lang, "welcome"))
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=t(lang, "select_action"),
        reply_markup=main_keyboard(lang)
    )
    return ConversationHandler.END


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

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"datepage_{page - 1}"))
    nav.append(InlineKeyboardButton("▶️", callback_data=f"datepage_{page + 1}"))
    buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    await update.message.reply_text(
        t(lang, "choose_date"),
        reply_markup=date_keyboard(0)
    )
    return DATE


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
    lang = get_lang(context)
    date = query.data.replace("date_", "")
    context.user_data["date"] = date

    await query.edit_message_text(
        f"{t(lang, 'date_chosen', date=date)}\n\n{t(lang, 'choose_time_start')}",
        parse_mode="Markdown",
        reply_markup=time_slots_keyboard("ts", date)
    )
    return TIME_START


def time_slots_keyboard(prefix: str, date: str, start_time: str = None) -> InlineKeyboardMarkup:
    busy_slots = get_booked_slots(date)
    buttons = []
    row = []

    for h in range(9, 18):
        for m in (0, 30):
            t_str = f"{h:02d}:{m:02d}"
            if start_time and time_to_minutes(t_str) <= time_to_minutes(start_time):
                continue
            if t_str in busy_slots:
                label = f"🔴 {t_str}"
                row.append(InlineKeyboardButton(label, callback_data=f"busy_{t_str}"))
            else:
                label = f"🟢 {t_str}"
                row.append(InlineKeyboardButton(label, callback_data=f"{prefix}_{t_str}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(buttons)


async def busy_slot_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = get_lang(context)
    msg = "🔴 Это время уже занято!" if lang == "ru" else "🔴 Бу вақт банд!"
    await query.answer(msg, show_alert=True)


async def book_time_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    time = query.data.replace("ts_", "")
    context.user_data["time_start"] = time
    date = context.user_data["date"]

    await query.edit_message_text(
        f"{t(lang, 'date_chosen', date=date)}\n"
        f"{t(lang, 'time_start_chosen', time=time)}\n\n"
        f"{t(lang, 'choose_time_end')}",
        parse_mode="Markdown",
        reply_markup=time_slots_keyboard("te", date, start_time=time)
    )
    return TIME_END


async def book_time_end_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    time_end = query.data.replace("te_", "")
    time_start = context.user_data["time_start"]
    date = context.user_data["date"]

    if not is_time_available(date, time_start, time_end):
        await query.edit_message_text(
            t(lang, "time_busy", start=time_start, end=time_end, date=date),
            parse_mode="Markdown",
            reply_markup=time_slots_keyboard("ts", date)
        )
        return TIME_START

    context.user_data["time_end"] = time_end
    context.user_data["comment"] = ""

    await query.edit_message_text(
        f"{t(lang, 'date_chosen', date=date)}\n"
        f"{t(lang, 'time_start_chosen', time=time_start)}\n"
        f"{t(lang, 'time_end_chosen', time=time_end)}\n\n"
        f"{t(lang, 'enter_comment')}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(t(lang, "confirm_btn"), callback_data="comment_confirm")
        ]])
    )
    return COMMENT


async def book_comment_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь вводит текст — сохраняем и показываем кнопку подтверждения"""
    lang = get_lang(context)
    context.user_data["comment"] = update.message.text.strip()
    d = context.user_data

    await update.message.reply_text(
        f"{t(lang, 'date_chosen', date=d['date'])}\n"
        f"{t(lang, 'time_start_chosen', time=d['time_start'])}\n"
        f"{t(lang, 'time_end_chosen', time=d['time_end'])}\n"
        f"💬 {d['comment']}\n\n"
        f"{t(lang, 'enter_comment')}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(t(lang, "confirm_btn"), callback_data="comment_confirm")
        ]])
    )
    return COMMENT


async def book_comment_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Нажата кнопка подтверждения"""
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    user = update.effective_user
    d = context.user_data
    comment = d.get("comment", "")

    booking_id = add_booking(
        d["date"], d["time_start"], d["time_end"],
        user.id, user.username or user.first_name, comment
    )

    await query.edit_message_text(
        t(lang, "booking_confirmed",
          id=booking_id, date=d["date"],
          start=d["time_start"], end=d["time_end"],
          comment=comment or "—"),
        parse_mode="Markdown"
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=t(lang, "select_action"),
        reply_markup=main_keyboard(lang)
    )
    return ConversationHandler.END


# ─── МОИ БРОНИ ────────────────────────────────────────────
async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    user_id = update.effective_user.id
    bookings = get_user_bookings(user_id)

    if not bookings:
        await update.message.reply_text(t(lang, "no_bookings"))
        return

    text = t(lang, "my_bookings")
    for b in bookings:
        text += f"🆔 `{b['id']}` | {b['date']} | {b['time_start']}–{b['time_end']}"
        if b.get("comment"):
            text += f" | {b['comment']}"
        text += "\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def bookings_today_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    today = datetime.now()
    buttons = []
    row = []

    for i in range(0, 15):
        day = today + timedelta(days=i)
        label = day.strftime("%d.%m")
        if i == 0:
            label = f"📍{label}"
        row.append(InlineKeyboardButton(label, callback_data=f"view_{day.strftime('%d.%m.%Y')}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await update.message.reply_text(
        t(lang, "choose_date_view"),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return DATE


async def bookings_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    date = query.data.replace("view_", "")
    bookings = get_bookings_by_date(date)

    if not bookings:
        await query.edit_message_text(
            t(lang, "no_bookings_date", date=date),
            parse_mode="Markdown"
        )
    else:
        text = t(lang, "bookings_date", date=date)
        for b in sorted(bookings, key=lambda x: x["time_start"]):
            text += f"🕐 {b['time_start']}–{b['time_end']} | @{b['username']}"
            if b.get("comment"):
                text += f" | _{b['comment']}_"
            text += "\n"
        await query.edit_message_text(text, parse_mode="Markdown")

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=t(lang, "select_action"),
        reply_markup=main_keyboard(lang)
    )
    return ConversationHandler.END


async def cancel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    user_id = update.effective_user.id
    bookings = get_user_bookings(user_id)

    if not bookings:
        await update.message.reply_text(
            t(lang, "no_bookings"),
            reply_markup=main_keyboard(lang)
        )
        return ConversationHandler.END

    buttons = []
    for b in bookings:
        label = f"🗑 {b['date']} {b['time_start']}–{b['time_end']}"
        if b.get("comment"):
            label += f" ({b['comment']})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"cancel_{b['id']}")])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cancel_back")])

    await update.message.reply_text(
        t(lang, "choose_cancel"),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return CANCEL_ID


async def cancel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)

    if query.data == "cancel_back":
        await query.edit_message_text(t(lang, "cancelled"))
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=t(lang, "select_action"),
            reply_markup=main_keyboard(lang)
        )
        return ConversationHandler.END

    booking_id = query.data.replace("cancel_", "")
    user_id = update.effective_user.id

    if cancel_booking(booking_id, user_id):
        await query.edit_message_text(
            t(lang, "cancel_confirmed", id=booking_id),
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(t(lang, "cancel_failed"))

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=t(lang, "select_action"),
        reply_markup=main_keyboard(lang)
    )
    return ConversationHandler.END


async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    await update.message.reply_text(t(lang, "cancelled"), reply_markup=main_keyboard(lang))
    return ConversationHandler.END


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Диалог: выбор языка
    lang_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANG: [CallbackQueryHandler(choose_lang, pattern="^lang_")],
        },
        fallbacks=[]
    )

    # Диалог: создание брони
    book_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("📅 Забронировать|📅 Бронлаш"), book_start)],
        states={
            DATE: [
                CallbackQueryHandler(book_date, pattern="^date_"),
                CallbackQueryHandler(book_date_page, pattern="^datepage_"),
            ],
            TIME_START: [
                CallbackQueryHandler(book_time_start_cb, pattern="^ts_"),
                CallbackQueryHandler(busy_slot_cb, pattern="^busy_"),
            ],
            TIME_END: [
                CallbackQueryHandler(book_time_end_cb, pattern="^te_"),
                CallbackQueryHandler(busy_slot_cb, pattern="^busy_"),
            ],
            COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, book_comment_text),
                CallbackQueryHandler(book_comment_confirm, pattern="^comment_confirm"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )

    date_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("📆 Брони на день|📆 Кунлик бронлар"), bookings_today_start)],
        states={
            DATE: [CallbackQueryHandler(bookings_by_date, pattern="^view_")],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )

    cancel_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("❌ Отменить бронь|❌ Бронни бекор қилиш"), cancel_start)],
        states={
            CANCEL_ID: [CallbackQueryHandler(cancel_confirm, pattern="^cancel_")],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )

    app.add_handler(lang_conv)
    app.add_handler(book_conv)
    app.add_handler(date_conv)
    app.add_handler(cancel_conv_handler)
    app.add_handler(MessageHandler(filters.Regex("📋 Мои брони|📋 Менинг бронларим"), my_bookings))

    print("🤖 Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
