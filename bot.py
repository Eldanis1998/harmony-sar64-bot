import os
import sqlite3
import logging
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = os.getenv("ADMIN_ID", "")
DARINA_ID = os.getenv("DARINA_ID", "")
ANASTASIA_ID = os.getenv("ANASTASIA_ID", "6140181153")
DB_PATH = os.getenv("DB_PATH", "harmony.db")
PORT = int(os.getenv("PORT", "10000"))

SERVICES = {
    "jump_ind": ("Индивидуальная тренировка по конкуру", 2000),
    "jump_group": ("Групповая тренировка по конкуру", 1500),
    "beginner": ("Индивидуальная тренировка для начинающего спортсмена/любителя", 2000),
    "excursion": ("Экскурсия на конюшню", 1000),
    "photo_horse": ("Аренда лошади для фотосессии", 2500),
    "photo_club": ("Фотосессия с фотографом клуба с лошадью", 6000),
    "field": ("Аллюрная прогулка в поля для опытных всадников", 5000),
    "arena": ("Катание на лошади внутри манежа", 1000),
}

TRAINERS = {
    "Дарина": DARINA_ID,
    "Анастасия": ANASTASIA_ID,
}

FAQ = {
    "1": (
        "Есть ли абонементы и скидки?\n\n"
        "Абонемент на 8 занятий действует 1 месяц.\n"
        "Для начинающих и любителей — 10 000 ₽.\n"
        "По конкуру — 13 000 ₽."
    ),
    "2": (
        "Что надеть на тренировку?\n\n"
        "Удобную эластичную одежду: спортивные брюки или лосины, "
        "закрытую обувь. Зимой — сапоги с небольшим каблуком "
        "или на плоской подошве."
    ),
    "3": (
        "Нужен ли шлем?\n\n"
        "Да. Каждый всадник обязательно использует шлем для безопасности."
    ),
    "4": (
        "Сколько длится занятие?\n\n"
        "Тренировка — примерно 50–60 минут.\n"
        "Экскурсия — около 1–1,5 часа.\n"
        "Прогулка в поля — около 1,5–2 часов.\n"
        "Катание в манеже — около 30 минут."
    ),
    "5": "С какого возраста можно заниматься?\n\nЗанятия доступны с 5 лет.",
    "6": "Есть ли ограничение по весу?\n\nМаксимальный вес — 90 кг.",
    "7": (
        "Можно ли угощать лошадей?\n\n"
        "Да. Разрешены яблоки, морковь и сахар."
    ),
    "8": (
        "За сколько занятий можно научиться ездить верхом?\n\n"
        "Это индивидуально. Базовые навыки обычно осваиваются "
        "примерно за 5–10 занятий."
    ),
    "9": (
        "Безопасно ли кататься? Можно ли упасть?\n\n"
        "Риск падения существует, как и в любом конном спорте. "
        "Его снижают соблюдением правил безопасности и инструкциями тренера."
    ),
    "10": (
        "Какие документы нужны?\n\n"
        "Оформляется договор, выдаётся чек/подтверждение, "
        "а также требуется подпись в журнале техники безопасности."
    ),
    "11": (
        "Что делать при опоздании или отмене записи?\n\n"
        "Пожалуйста, заранее напишите администратору в личные сообщения."
    ),
    "12": (
        "Где находится клуб?\n\n"
        "Саратов, Песчано-Уметский проезд, 58А.\n\n"
        "В Яндекс Картах можно найти по запросу:\n"
        "«конный клуб Гармония»"
    ),
    "13": "Есть ли парковка?\n\nДа, рядом есть большая парковка.",
}

user_state = {}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            name TEXT,
            service TEXT NOT NULL,
            trainer TEXT NOT NULL,
            booking_date TEXT NOT NULL,
            booking_time TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


def main_menu():
    keyboard = [
        [
            InlineKeyboardButton("📅 Записаться", callback_data="book"),
            InlineKeyboardButton("📋 Моя запись", callback_data="my_booking"),
        ],
        [
            InlineKeyboardButton("💰 Услуги и цены", callback_data="prices"),
            InlineKeyboardButton("👥 Тренеры", callback_data="trainers"),
        ],
        [
            InlineKeyboardButton("❓ Частые вопросы", callback_data="faq"),
            InlineKeyboardButton("📍 Адрес", callback_data="address"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🐴 Добро пожаловать в конный клуб «Гармония»!\n\n"
        "Здесь вы можете выбрать услугу, тренера, дату и время "
        "для записи."
    )
    await update.message.reply_text(text, reply_markup=main_menu())


async def show_prices(update, context):
    text = "💰 УСЛУГИ И ЦЕНЫ\n\n"
    for name, price in SERVICES.values():
        text += f"• {name} — {price:,} ₽\n".replace(",", " ")
    text += "\n💳 Предоплата при онлайн-оплате — 500 ₽."
    await update.callback_query.message.edit_text(
        text, reply_markup=back_menu()
    )


async def show_trainers(update, context):
    text = (
        "👥 ТРЕНЕРЫ\n\n"
        "🏇 Дарина — тренер\n"
        "🏇 Анастасия — инструктор"
    )
    await update.callback_query.message.edit_text(
        text, reply_markup=back_menu()
    )


def back_menu():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ В меню", callback_data="home")]]
    )


async def show_address(update, context):
    text = (
        "📍 АДРЕС\n\n"
        "Саратов, Песчано-Уметский проезд, 58А\n\n"
        "Яндекс Карты:\n"
        "«конный клуб Гармония»\n\n"
        "🚗 Рядом есть большая парковка."
    )
    await update.callback_query.message.edit_text(
        text, reply_markup=back_menu()
    )


async def show_faq(update, context):
    buttons = [
        [InlineKeyboardButton(f"{i}. {q[:45]}", callback_data=f"faq_{i}")]
        for i, q in enumerate(
            [
                "Есть ли абонементы и скидки?",
                "Что надеть?",
                "Нужен ли шлем?",
                "Сколько длится занятие?",
                "С какого возраста?",
                "Есть ли ограничение по весу?",
                "Можно ли угощать лошадей?",
                "За сколько занятий можно научиться?",
                "Безопасно ли кататься?",
                "Какие документы нужны?",
                "Что делать при опоздании или отмене?",
                "Где находится клуб?",
                "Есть ли парковка?",
            ],
            1,
        )
    ]
    buttons.append([InlineKeyboardButton("⬅️ В меню", callback_data="home")])
    await update.callback_query.message.edit_text(
        "❓ ЧАСТЫЕ ВОПРОСЫ\n\nВыберите вопрос:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def faq_answer(update, context):
    number = update.callback_query.data.split("_")[1]
    text = FAQ[number]
    await update.callback_query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("⬅️ К вопросам", callback_data="faq")],
                [InlineKeyboardButton("🏠 В меню", callback_data="home")],
            ]
        ),
    )


async def start_booking(update, context):
    user_id = update.effective_user.id
    user_state[user_id] = {}

    buttons = []
    for key, (name, price) in SERVICES.items():
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{name} — {price} ₽",
                    callback_data=f"service_{key}",
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton("⬅️ В меню", callback_data="home")]
    )

    await update.callback_query.message.edit_text(
        "📅 Выберите услугу:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def choose_service(update, context):
    user_id = update.effective_user.id
    key = update.callback_query.data.replace("service_", "")
    user_state[user_id]["service"] = key

    buttons = [
        [
            InlineKeyboardButton(
                f"🏇 {trainer}",
                callback_data=f"trainer_{trainer}",
            )
        ]
        for trainer in TRAINERS
    ]

    buttons.append(
        [InlineKeyboardButton("⬅️ Назад", callback_data="book")]
    )

    await update.callback_query.message.edit_text(
        "Выберите тренера / инструктора:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def choose_trainer(update, context):
    user_id = update.effective_user.id
    trainer = update.callback_query.data.replace("trainer_", "")
    user_state[user_id]["trainer"] = trainer

    today = date.today()
    buttons = []

    for i in range(14):
        d = today + timedelta(days=i)
        buttons.append(
            [
                InlineKeyboardButton(
                    d.strftime("%d.%m.%Y"),
                    callback_data=f"date_{d.isoformat()}",
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"service_back")]
    )

    await update.callback_query.message.edit_text(
        "Выберите дату:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def choose_date(update, context):
    user_id = update.effective_user.id
    booking_date = update.callback_query.data.replace("date_", "")
    user_state[user_id]["booking_date"] = booking_date

    buttons = []
    for hour in range(10, 20):
        time_text = f"{hour:02d}:00"
        buttons.append(
            [
                InlineKeyboardButton(
                    time_text,
                    callback_data=f"time_{time_text}",
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_date")]
    )

    await update.callback_query.message.edit_text(
        "Выберите время:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def choose_time(update, context):
    user_id = update.effective_user.id
    booking_time = update.callback_query.data.replace("time_", "")
    state = user_state.get(user_id, {})

    state["booking_time"] = booking_time

    service_key = state.get("service")
    trainer = state.get("trainer")
    booking_date = state.get("booking_date")

    if not service_key or not trainer or not booking_date:
        await update.callback_query.message.edit_text(
            "Сессия записи устарела. Начните запись заново.",
            reply_markup=back_menu(),
        )
        return

    service_name, price = SERVICES[service_key]

    text = (
        "📋 ПРОВЕРЬТЕ ЗАПИСЬ\n\n"
        f"Услуга: {service_name}\n"
        f"Стоимость: {price} ₽\n"
        f"Тренер: {trainer}\n"
        f"Дата: {booking_date}\n"
        f"Время: {booking_time}\n\n"
        "Предоплата онлайн: 500 ₽\n\n"
        "Всё верно?"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="home"),
        ]
    ]

    await update.callback_query.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def confirm_booking(update, context):
    user_id = update.effective_user.id
    state = user_state.get(user_id, {})

    service_key = state.get("service")
    trainer = state.get("trainer")
    booking_date = state.get("booking_date")
    booking_time = state.get("booking_time")

    if not all([service_key, trainer, booking_date, booking_time]):
        await update.callback_query.message.edit_text(
            "Не удалось получить данные записи. Начните заново.",
            reply_markup=back_menu(),
        )
        return

    service_name, price = SERVICES[service_key]
    conn = db()

    existing = conn.execute(
        """
        SELECT id FROM bookings
        WHERE booking_date=? AND booking_time=? AND trainer=?
        """,
        (booking_date, booking_time, trainer),
    ).fetchone()

    if existing:
        conn.close()
        await update.callback_query.message.edit_text(
            "❌ Это время уже занято.\n\n"
            "Пожалуйста, выберите другое время.",
            reply_markup=back_menu(),
        )
        return

    user = update.effective_user
    full_name = user.full_name or "Без имени"
    username = f"@{user.username}" if user.username else "нет username"

    cursor = conn.execute(
        """
        INSERT INTO bookings
        (user_id, username, name, service, trainer, booking_date, booking_time)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            username,
            full_name,
            service_name,
            trainer,
            booking_date,
            booking_time,
        ),
    )
    booking_id = cursor.lastrowid
    conn.commit()
    conn.close()

    notification = (
        "🔔 НОВАЯ ЗАПИСЬ\n\n"
        f"№ {booking_id}\n"
        f"👤 Клиент: {full_name}\n"
        f"Username: {username}\n"
        f"Telegram ID: {user_id}\n\n"
        f"🐴 Услуга: {service_name}\n"
        f"💰 Стоимость: {price} ₽\n"
        f"👥 Тренер: {trainer}\n"
        f"📅 Дата: {booking_date}\n"
        f"⏰ Время: {booking_time}\n"
        f"💳 Предоплата: 500 ₽"
    )

    recipients = set()

    if ADMIN_ID.isdigit():
        recipients.add(int(ADMIN_ID))

    trainer_id = TRAINERS.get(trainer)
    if trainer_id and trainer_id.isdigit():
        recipients.add(int(trainer_id))

    for recipient in recipients:
        try:
            await context.bot.send_message(
                chat_id=recipient,
                text=notification,
            )
        except Exception:
            logger.exception(
                "Не удалось отправить уведомление %s", recipient
            )

    user_state.pop(user_id, None)

    await update.callback_query.message.edit_text(
        "✅ ЗАПИСЬ ПОДТВЕРЖДЕНА!\n\n"
        f"Услуга: {service_name}\n"
        f"Тренер: {trainer}\n"
        f"Дата: {booking_date}\n"
        f"Время: {booking_time}\n"
        f"Стоимость: {price} ₽\n\n"
        "Предоплата — 500 ₽.\n"
        "Администратор свяжется с вами для подтверждения оплаты.",
        reply_markup=back_menu(),
    )


async def my_booking(update, context):
    user_id = update.effective_user.id
    conn = db()

    rows = conn.execute(
        """
        SELECT id, service, trainer, booking_date, booking_time
        FROM bookings
        WHERE user_id=?
        ORDER BY booking_date, booking_time
        """,
        (user_id,),
    ).fetchall()

    conn.close()

    if not rows:
        text = "📋 У вас пока нет записей."
    else:
        text = "📋 ВАШИ ЗАПИСИ\n\n"
        for row in rows:
            text += (
                f"№ {row[0]}\n"
                f"🐴 {row[1]}\n"
                f"👥 {row[2]}\n"
                f"📅 {row[3]}\n"
                f"⏰ {row[4]}\n\n"
            )

    await update.callback_query.message.edit_text(
        text, reply_markup=back_menu()
    )


async def bookings_command(update, context):
    if not ADMIN_ID.isdigit():
        return

    if update.effective_user.id != int(ADMIN_ID):
        return

    conn = db()
    rows = conn.execute(
        """
        SELECT id, name, username, service, trainer, booking_date, booking_time
        FROM bookings
        ORDER BY booking_date, booking_time
        """
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("Записей пока нет.")
        return

    text = "📋 ВСЕ ЗАПИСИ\n\n"

    for row in rows:
        text += (
            f"№ {row[0]}\n"
            f"👤 {row[1]} ({row[2]})\n"
            f"🐴 {row[3]}\n"
            f"👥 {row[4]}\n"
            f"📅 {row[5]} {row[6]}\n\n"
        )

    await update.message.reply_text(text)


async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "home":
        await query.message.edit_text(
            "🐴 Конный клуб «Гармония»\n\n"
            "Выберите нужный раздел:",
            reply_markup=main_menu(),
        )

    elif data == "book":
        await start_booking(update, context)

    elif data.startswith("service_"):
        if data == "service_back":
            await start_booking(update, context)
        else:
            await choose_service(update, context)

    elif data.startswith("trainer_"):
        await choose_trainer(update, context)

    elif data.startswith("date_"):
        await choose_date(update, context)

    elif data.startswith("time_"):
        await choose_time(update, context)

    elif data == "confirm":
        await confirm_booking(update, context)

    elif data == "my_booking":
        await my_booking(update, context)

    elif data == "prices":
        await show_prices(update, context)

    elif data == "trainers":
        await show_trainers(update, context)

    elif data == "faq":
        await show_faq(update, context)

    elif data.startswith("faq_"):
        await faq_answer(update, context)

    elif data == "address":
        await show_address(update, context)

    elif data == "back_date":
        user_id = update.effective_user.id
        trainer = user_state.get(user_id, {}).get("trainer", "")

        if trainer:
            buttons = []
            today = date.today()

            for i in range(14):
                d = today + timedelta(days=i)
                buttons.append(
                    [
                        InlineKeyboardButton(
                            d.strftime("%d.%m.%Y"),
                            callback_data=f"date_{d.isoformat()}",
                        )
                    ]
                )

            await query.message.edit_text(
                "Выберите дату:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )


def start_health_server():
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/health"):
                body = b"OK"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    logger.info("Health server started on port %s", PORT)
    return server


def build_app():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("bookings", bookings_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    return application


if __name__ == "__main__":
    start_health_server()

    app = build_app()

    logger.info("Harmony booking bot started")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )
