import os
import sqlite3
import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException
import time
import random
import threading
import csv
import io
from flask import Flask

# ==================== FLASK KEEP-ALIVE SERVER ====================
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

# ==================== НАСТРОЙКИ (ЗАПОЛНЕНО) ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8657141354:AAEYU9omJX754PT4FqXsW8Jm6asFVTw7DtY")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7408654429"))
MANAGER_USERNAME = "Nazarow927"
GARANT_USERNAME = "garant_nazarow"
GARANT_MD = GARANT_USERNAME.replace("_", "\\_")  # экранирование _ для Markdown
REQUIRED_CHANNEL = "@nazarowshop"

# --- TON ---
TON_WALLET = os.environ.get("TON_WALLET", "UQC1PIFE4zI6qZmOxn72gCyQWWSq1Uax4kgeOGnTdICT-cC-")
# Курс: сколько грн стоит 1 TON. ОБЯЗАТЕЛЬНО поставьте актуальный (можно через переменную TON_RATE_UAH)
TON_RATE_UAH = float(os.environ.get("TON_RATE_UAH", "65"))
TON_RATE_RUB = float(os.environ.get("TON_RATE_RUB", "122"))
# Курс звезды
STAR_RATE_UAH = 0.83
STAR_RATE_RUB = 1.65

CARD_NUMBER = os.environ.get("CARD_NUMBER", "4400005572759295")
CARD_HOLDER = "А-Банк / Карта UAH"
REVIEWS_CHANNEL_ID = "-1004291767300"
# ===============================================================

bot = telebot.TeleBot(BOT_TOKEN)

BOT_USERNAME = ""
try:
    BOT_USERNAME = bot.get_me().username
except Exception as e:
    print(f"Ошибка получения инфо о боте: {e}")

# ==================== БАЗА ДАННЫХ ====================
conn = sqlite3.connect("store.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0.0,
        currency TEXT DEFAULT 'UAH',
        referred_by INTEGER DEFAULT NULL,
        last_bonus INTEGER DEFAULT 0
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        item_name TEXT,
        price REAL,
        currency TEXT,
        status TEXT DEFAULT 'pending'
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS catalog_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        category TEXT DEFAULT '🔥 Разное',
        price_uah REAL DEFAULT 0.0,
        price_stars REAL DEFAULT 0.0,
        price_rub REAL DEFAULT 0.0
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY,
        reward REAL,
        uses_left INTEGER
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS used_promos (
        user_id INTEGER,
        code TEXT,
        PRIMARY KEY (user_id, code)
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        user_id INTEGER,
        rating INTEGER,
        review_text TEXT
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        payment_id TEXT PRIMARY KEY,
        user_id INTEGER,
        amount REAL,
        status TEXT DEFAULT 'pending'
    )
""")
conn.commit()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS banners (
        menu_key TEXT PRIMARY KEY,
        file_id TEXT
    )
""")
conn.commit()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS referral_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        invited_id INTEGER,
        created_at INTEGER
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS competition (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        active INTEGER DEFAULT 0,
        start_at INTEGER DEFAULT 0,
        end_at INTEGER DEFAULT 0,
        prize1 TEXT DEFAULT '100 грн на баланс',
        prize2 TEXT DEFAULT '50 грн на баланс',
        prize3 TEXT DEFAULT '25 грн на баланс'
    )
""")
cursor.execute("INSERT OR IGNORE INTO competition (id) VALUES (1)")
conn.commit()

# Проверка/миграция недостающих колонок
try:
    cursor.execute("ALTER TABLE users ADD COLUMN last_bonus INTEGER DEFAULT 0")
    conn.commit()
except Exception:
    pass

try:
    cursor.execute("ALTER TABLE users ADD COLUMN curr_set INTEGER DEFAULT 0")
    # все уже существующие пользователи считаются выбравшими валюту
    cursor.execute("UPDATE users SET curr_set=1")
    conn.commit()
except Exception:
    pass

try:
    cursor.execute("ALTER TABLE catalog_items ADD COLUMN category TEXT DEFAULT '🔥 Разное'")
    conn.commit()
except Exception:
    pass

CURRENCY_SYMBOLS = {
    "UAH": "грн",
    "STARS": "⭐",
    "RUB": "₽"
}

REF_REWARDS = {
    "UAH": (3.0, "грн"),
    "STARS": (5.0, "⭐"),
    "RUB": (7.0, "₽")
}

# ==================== БАННЕРЫ МЕНЮ ====================
BANNER_MENUS = {
    "main": "🏠 Главное меню",
    "catalog": "🛒 Каталог",
    "item": "📦 Карточка товара",
    "profile": "👤 Профиль",
    "topup": "💳 Пополнение баланса",
    "currency": "🌐 Выбор валюты",
    "ref": "👥 Рефералка",
    "orders": "📜 Мои заказы",
    "faq": "📖 Инфо / Правила",
}

def get_banner(menu_key):
    try:
        cursor.execute("SELECT file_id FROM banners WHERE menu_key=?", (menu_key,))
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        print(f"Ошибка чтения баннера: {e}")
        return None

def edit_text(text, chat_id, message_id, parse_mode=None, reply_markup=None):
    """Редактирует текст. Если сообщение с фото — удаляет его и отправляет текстовое."""
    try:
        return bot.edit_message_text(text, chat_id, message_id, parse_mode=parse_mode, reply_markup=reply_markup)
    except ApiTelegramException as e:
        err = str(e)
        if "message is not modified" in err:
            return None
        if "no text in the message to edit" in err:
            try:
                bot.delete_message(chat_id, message_id)
            except Exception:
                pass
            return bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        raise

def show_menu(message, menu_key, text, markup=None, chat_id=None, parse_mode="Markdown"):
    """Показывает меню; если для menu_key задан баннер — с фото (подпись до 1024 символов)."""
    if message is not None:
        chat_id = message.chat.id
    banner = get_banner(menu_key)
    is_photo = message is not None and message.content_type == "photo"
    use_banner = bool(banner) and len(text) <= 1024
    try:
        if use_banner and is_photo:
            try:
                return bot.edit_message_media(
                    types.InputMediaPhoto(banner, caption=text, parse_mode=parse_mode),
                    chat_id, message.message_id, reply_markup=markup
                )
            except ApiTelegramException as e:
                if "message is not modified" in str(e):
                    return None
                raise
        if use_banner:
            sent = bot.send_photo(chat_id, banner, caption=text, parse_mode=parse_mode, reply_markup=markup)
            if message is not None:
                try:
                    bot.delete_message(chat_id, message.message_id)
                except Exception:
                    pass
            return sent
        if message is None:
            return bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=markup)
        return edit_text(text, chat_id, message.message_id, parse_mode, markup)
    except Exception as e:
        print(f"Ошибка показа меню {menu_key}: {e}")
        try:
            return bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=markup)
        except Exception as e2:
            print(f"Ошибка отправки меню: {e2}")

def get_admin_markup():
    markup = types.InlineKeyboardMarkup()
    b1 = types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")
    b2 = types.InlineKeyboardButton("➕ Добавить товар", callback_data="admin_add_item")
    b3 = types.InlineKeyboardButton("🗑 Удалить товар", callback_data="admin_del_item")
    b4 = types.InlineKeyboardButton("📢 Массовая рассылка", callback_data="admin_broadcast")
    b5 = types.InlineKeyboardButton("💰 Выдать баланс", callback_data="admin_give_info")
    b6 = types.InlineKeyboardButton("🎁 Промокоды", callback_data="admin_promo_info")
    b7 = types.InlineKeyboardButton("🖼 Баннеры меню", callback_data="admin_banners")
    b8 = types.InlineKeyboardButton("🏆 Инвайт-топ", callback_data="admin_contest")
    b9 = types.InlineKeyboardButton("🔎 Поиск юзера", callback_data="admin_search_user")
    b10 = types.InlineKeyboardButton("📤 Экспорт заказов", callback_data="admin_export_orders")
    markup.add(b1)
    markup.add(b2, b3)
    markup.add(b4)
    markup.add(b5, b6)
    markup.add(b7)
    markup.add(b8)
    markup.add(b9, b10)
    return markup

def get_competition():
    cursor.execute("SELECT active, start_at, end_at, prize1, prize2, prize3 FROM competition WHERE id=1")
    row = cursor.fetchone()
    return {
        "active": bool(row[0]), "start_at": row[1], "end_at": row[2],
        "prize1": row[3], "prize2": row[4], "prize3": row[5]
    }

def get_leaderboard(limit=10):
    comp = get_competition()
    if comp["active"]:
        cursor.execute(
            "SELECT referrer_id, COUNT(*) as cnt FROM referral_events WHERE created_at BETWEEN ? AND ? GROUP BY referrer_id ORDER BY cnt DESC LIMIT ?",
            (comp["start_at"], comp["end_at"], limit)
        )
    else:
        cursor.execute(
            "SELECT referrer_id, COUNT(*) as cnt FROM referral_events GROUP BY referrer_id ORDER BY cnt DESC LIMIT ?",
            (limit,)
        )
    return cursor.fetchall()

def get_display_name(uid):
    try:
        chat = bot.get_chat(uid)
        if chat.username:
            return f"@{chat.username}"
        return chat.first_name or f"ID {uid}"
    except Exception:
        return f"ID {uid}"

ADMIN_PANEL_TEXT = "🛠 **Панель Администратора**\n\nУправляйте магазином с помощью кнопок ниже:"

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def check_subscription(user_id):
    """Проверка подписки пользователя на обязательный канал"""
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        return True

def get_sub_keyboard():
    markup = types.InlineKeyboardMarkup()
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    btn_sub = types.InlineKeyboardButton("📢 Подписаться на канал", url=channel_url)
    btn_check = types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")
    markup.add(btn_sub)
    markup.add(btn_check)
    return markup

def convert_currency(amount, from_curr, to_curr):
    """
    Курсы:
    1 TON = TON_RATE_UAH грн = TON_RATE_RUB руб
    1 STAR = 0.83 грн = 1.65 руб
    """
    if from_curr == to_curr:
        return amount

    # переводим в "внутреннюю" единицу — гривны/рубли/звёзды напрямую
    if from_curr == "TON":
        if to_curr == "UAH":
            return round(amount * TON_RATE_UAH, 2)
        if to_curr == "RUB":
            return round(amount * TON_RATE_RUB, 2)
        if to_curr == "STARS":
            return round(amount * TON_RATE_UAH / STAR_RATE_UAH, 1)
        return amount

    if from_curr == "STARS":
        stars = amount
    elif from_curr == "UAH":
        stars = amount / STAR_RATE_UAH
    elif from_curr == "RUB":
        stars = amount / STAR_RATE_RUB
    else:
        return amount

    if to_curr == "STARS":
        return round(stars, 1)
    if to_curr == "UAH":
        return round(stars * STAR_RATE_UAH, 2)
    if to_curr == "RUB":
        return round(stars * STAR_RATE_RUB, 2)
    return amount

def get_rates_text():
    return (
        "📊 **Курс:**\n"
        f"💎 1 TON = **{TON_RATE_UAH:g} грн** = **{TON_RATE_RUB:g} ₽**\n"
        f"⭐ 1 звезда = **{str(STAR_RATE_UAH).replace('.', ',')} грн** = **{str(STAR_RATE_RUB).replace('.', ',')} ₽**"
    )

def get_currency_markup(back_to_profile=False):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🇺🇦 UAH (грн)", callback_data="set_curr_UAH"))
    markup.add(types.InlineKeyboardButton("⭐ Stars (звёзды)", callback_data="set_curr_STARS"))
    markup.add(types.InlineKeyboardButton("🇷🇺 RUB (₽)", callback_data="set_curr_RUB"))
    if back_to_profile:
        markup.add(types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile"))
    return markup

def get_currency_text(first_time=False):
    head = "🌐 **Выберите удобную валюту**\n\n"
    if first_time:
        head = ("✅ **Подписка подтверждена!**\n\n"
                "Остался последний шаг — выберите удобную валюту, в которой вы будете пользоваться ботом:\n\n")
    return head + get_rates_text()

def is_currency_set(user_id):
    cursor.execute("SELECT curr_set FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return bool(row and row[0])

def get_main_menu_text(first_name):
    return (
        f"👋 **Привет, {first_name}!**\n\n"
        f"🔥 **Добро пожаловать в наш шоп!**\n\n"
        f"🛒 **У нас ты можешь купить:**\n"
        f"• 📲 Физические SIM-карты и номера\n"
        f"• 📱 Telegram аккаунты (TData / Session+Json)\n"
        f"• ⚡ Виртуальные номера под любые сервисы\n"
        f"• 💎 Telegram Premium и звёзды (Stars)\n\n"
        f"📢 **Наш канал:** {REQUIRED_CHANNEL}\n"
        f"👨‍💻 **Менеджер / Поддержка:** @{MANAGER_USERNAME}\n\n"
        f"👇 Выберите нужный раздел ниже:"
    )

def get_main_menu_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🛒 Каталог товаров", callback_data="catalog_cats")
    btn2 = types.InlineKeyboardButton("👤 Профиль и Баланс", callback_data="profile")
    btn3 = types.InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="daily_bonus")
    btn4 = types.InlineKeyboardButton("👥 Рефералка", callback_data="ref_system")
    btn5 = types.InlineKeyboardButton("👨‍💻 Написать менеджеру", url=f"https://t.me/{MANAGER_USERNAME}")
    btn6 = types.InlineKeyboardButton("📖 Инфо / Правила", callback_data="faq_info")
    markup.add(btn1, btn2)
    markup.add(btn3, btn4)
    markup.add(btn5, btn6)
    return markup

def save_review(order_id, user_id, rating, text, first_name, username):
    cursor.execute("INSERT INTO reviews (order_id, user_id, rating, review_text) VALUES (?, ?, ?, ?)",
                   (order_id, user_id, rating, text))
    conn.commit()

    if rating == 5:
        cursor.execute("SELECT currency FROM users WHERE user_id=?", (user_id,))
        u_curr_row = cursor.fetchone()
        u_curr = u_curr_row[0] if u_curr_row else "UAH"
        
        bonus_val = 2.5 if u_curr == "UAH" else (2.0 if u_curr == "STARS" else 5.0)
        sym = CURRENCY_SYMBOLS.get(u_curr, "грн")

        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus_val, user_id))
        conn.commit()

        try:
            bot.send_message(
                user_id, 
                f"🎉 **Спасибо за отзыв 5★!**\n💰 Вам автоматически зачислено **+{bonus_val} {sym}** на баланс!", 
                parse_mode="Markdown"
            )
        except Exception:
            pass

    cursor.execute("SELECT item_name FROM orders WHERE order_id=?", (order_id,))
    res = cursor.fetchone()
    item_name = res[0] if res else "Товар"

    user_str = f"@{username}" if username else first_name
    stars_str = "⭐" * int(rating)

    review_msg = (
        f"📣 **Новый отзыв о покупке!**\n\n"
        f"📦 Товар: **{item_name}** (Заказ #{order_id})\n"
        f"👤 Покупатель: {user_str}\n"
        f"⭐️ Оценка: **{stars_str}** ({rating}/5)\n"
        f"💬 Отзыв: _{text}_"
    )

    try:
        bot.send_message(ADMIN_ID, review_msg, parse_mode="Markdown")
    except Exception:
        pass

    if REVIEWS_CHANNEL_ID:
        try:
            bot.send_message(REVIEWS_CHANNEL_ID, review_msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка отправки в канал отзывов: {e}")

# ==================== КОМАНДЫ ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
    
    if not check_subscription(user_id):
        text = (
            f"👋 **Привет, {message.from_user.first_name}!**\n\n"
            f"⚠️ **Для доступа к боту необходимо подписаться на наш официальный канал:**\n"
            f"👉 {REQUIRED_CHANNEL}\n\n"
            f"После подписки нажмите кнопку **«✅ Я подписался»** ниже:"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=get_sub_keyboard())
        return

    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    existing_user = cursor.fetchone()
    
    referred_by = None
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id:
            referred_by = ref_id

    if not existing_user:
        cursor.execute("INSERT INTO users (user_id, referred_by) VALUES (?, ?)", (user_id, referred_by))
        conn.commit()

        if referred_by:
            cursor.execute("SELECT currency FROM users WHERE user_id=?", (referred_by,))
            ref_row = cursor.fetchone()
            if ref_row:
                ref_curr = ref_row[0]
                rew_val, rew_sym = REF_REWARDS.get(ref_curr, (3.0, "грн"))
                
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (rew_val, referred_by))
                cursor.execute("INSERT INTO referral_events (referrer_id, invited_id, created_at) VALUES (?, ?, ?)", (referred_by, user_id, int(time.time())))
                conn.commit()
                
                try:
                    bot.send_message(
                        referred_by,
                        f"🎉 **Новый реферал!** По вашей ссылке присоединился {message.from_user.first_name}.\n"
                        f"💰 Вам начислено **+{rew_val} {rew_sym}** на баланс!",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Ошибка отправки рефереру: {e}")

    if not is_currency_set(user_id):
        show_menu(None, "currency", get_currency_text(first_time=True), get_currency_markup(), chat_id=message.chat.id)
        return

    text = get_main_menu_text(message.from_user.first_name)
    markup = get_main_menu_keyboard()
    show_menu(None, "main", text, markup, chat_id=message.chat.id)

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, f"❌ Отказано в доступе. Ваш ID: `{message.from_user.id}`", parse_mode="Markdown")
        return
    
    markup = get_admin_markup()
    text = ADMIN_PANEL_TEXT
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    if message.from_user.id != ADMIN_ID: return
    bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
    msg = bot.send_message(message.chat.id, "📢 **Массовая рассылка**\n\nОтправьте сообщение для рассылки:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_broadcast)

@bot.message_handler(commands=['add_promo'])
def add_promo_command(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, code, reward, uses = message.text.split()
        cursor.execute("INSERT OR REPLACE INTO promocodes (code, reward, uses_left) VALUES (?, ?, ?)", 
                       (code, float(reward), int(uses)))
        conn.commit()
        bot.reply_to(message, f"✅ Промокод `{code}` на **{reward}** ({uses} активаций) создан!", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "Формат: `/add_promo КОД СУММА КОЛ_ВО`\nПример: `/add_promo START100 100 5`", parse_mode="Markdown")

@bot.message_handler(commands=['give_balance'])
def give_balance(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, target_id, amount = message.text.split()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (float(amount), int(target_id)))
        conn.commit()
        bot.reply_to(message, f"💰 Выдано **{amount}** пользователю `{target_id}`.", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "Формат: `/give_balance ID СУММА`", parse_mode="Markdown")

# ==================== CALLBACK HANDLER ====================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.from_user.id

    # Telegram позволяет ответить на callback ТОЛЬКО ОДИН РАЗ.
    # Для кнопок, где ниже показывается alert, заранее не отвечаем.
    if not (call.data == "check_subscription" or call.data.startswith("set_curr_")):
        bot.answer_callback_query(call.id)

    def safe_answer(text=None, alert=False):
        try:
            bot.answer_callback_query(call.id, text, show_alert=alert)
        except Exception:
            pass

    if call.data == "check_subscription":
        if check_subscription(user_id):
            safe_answer("✅ Подписка подтверждена!")
            cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            conn.commit()
            if not is_currency_set(user_id):
                show_menu(call.message, "currency", get_currency_text(first_time=True), get_currency_markup())
            else:
                text = get_main_menu_text(call.from_user.first_name)
                markup = get_main_menu_keyboard()
                show_menu(call.message, "main", text, markup)
        else:
            safe_answer("❌ Вы всё ещё не подписаны на канал!", True)
        return

    if not check_subscription(user_id):
        safe_answer("⚠️ Доступ ограничен! Подпишитесь на канал.", True)
        text = (
            f"⚠️ **Для продолжения работы подпишитесь на наш канал:**\n"
            f"👉 {REQUIRED_CHANNEL}"
        )
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=get_sub_keyboard())
        return

    cursor.execute("SELECT balance, currency, last_bonus FROM users WHERE user_id=?", (user_id,))
    u_row = cursor.fetchone()
    if not u_row:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        balance, curr, last_bonus = 0.0, "UAH", 0
    else:
        balance, curr, last_bonus = u_row[0], u_row[1], u_row[2]

    sym = CURRENCY_SYMBOLS.get(curr, "грн")

    # Пока валюта не выбрана — доступен только выбор валюты (админ не блокируется)
    if user_id != ADMIN_ID and not call.data.startswith("set_curr_") and not is_currency_set(user_id):
        safe_answer()
        show_menu(call.message, "currency", get_currency_text(first_time=True), get_currency_markup())
        return

    if call.data.startswith("set_curr_"):
        pass  # ответ даётся в самом обработчике ниже

    if call.data == "admin_add_item":
        if user_id != ADMIN_ID:
            bot.send_message(call.message.chat.id, "❌ Вы не администратор!")
            return
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id, 
            "➕ **Добавление товара / номера**\n\n"
            "Пишите **название и цену в грн** — цены в ⭐ и ₽ посчитаются сами по курсу.\n\n"
            "`Название, Цена_грн`\n"
            "`Название, Категория, Цена_грн`\n\n"
            "*Пример:*\n`США +1, 100`\n`+380991234567, 📲 Номера, 150`\n\n"
            "📋 Можно сразу несколько — каждый товар с новой строки.\n"
            "Десятичные — через точку (`2.5`).", 
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_add_item)
        return

    elif call.data == "admin_home":
        if user_id != ADMIN_ID: return
        edit_text(ADMIN_PANEL_TEXT, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_admin_markup())

    elif call.data == "admin_banners":
        if user_id != ADMIN_ID: return
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        markup = types.InlineKeyboardMarkup()
        for key, title in BANNER_MENUS.items():
            mark = "✅" if get_banner(key) else "➕"
            markup.add(types.InlineKeyboardButton(f"{mark} {title}", callback_data=f"bn_menu_{key}"))
        markup.add(types.InlineKeyboardButton("⬅️ Админ-панель", callback_data="admin_home"))
        edit_text("🖼 **Баннеры меню**\n\n✅ — баннер установлен, ➕ — не задан.\nВыберите раздел:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("bn_menu_"):
        if user_id != ADMIN_ID: return
        key = call.data.split("_", 2)[2]
        if key not in BANNER_MENUS: return
        has = bool(get_banner(key))
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Заменить фото" if has else "📤 Загрузить фото", callback_data=f"bn_set_{key}"))
        if has:
            markup.add(types.InlineKeyboardButton("👁 Посмотреть", callback_data=f"bn_view_{key}"))
            markup.add(types.InlineKeyboardButton("🗑 Убрать баннер", callback_data=f"bn_del_{key}"))
        markup.add(types.InlineKeyboardButton("⬅️ К списку", callback_data="admin_banners"))
        status = "установлен ✅" if has else "не задан"
        edit_text(f"🖼 **{BANNER_MENUS[key]}**\n\nБаннер: {status}", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("bn_set_"):
        if user_id != ADMIN_ID: return
        key = call.data.split("_", 2)[2]
        if key not in BANNER_MENUS: return
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id,
            f"📤 Отправьте **фото** для раздела «{BANNER_MENUS[key]}» (именно как фото, не как файл).\n\nОтмена: /cancel",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_banner_upload, key)

    elif call.data.startswith("bn_view_"):
        if user_id != ADMIN_ID: return
        key = call.data.split("_", 2)[2]
        file_id = get_banner(key)
        if not file_id:
            bot.send_message(call.message.chat.id, "❌ Баннер не задан.")
            return
        try:
            bot.send_photo(call.message.chat.id, file_id, caption=f"🖼 Баннер: {BANNER_MENUS.get(key, key)}")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Не удалось показать баннер: {e}")

    elif call.data.startswith("bn_del_"):
        if user_id != ADMIN_ID: return
        key = call.data.split("_", 2)[2]
        cursor.execute("DELETE FROM banners WHERE menu_key=?", (key,))
        conn.commit()
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📤 Загрузить фото", callback_data=f"bn_set_{key}"))
        markup.add(types.InlineKeyboardButton("⬅️ К списку", callback_data="admin_banners"))
        edit_text(f"🗑 Баннер раздела «{BANNER_MENUS.get(key, key)}» убран.", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "daily_bonus":
        now = int(time.time())
        cooldown = 86400
        
        if now - last_bonus >= cooldown:
            bonus_amount = round(random.uniform(1.0, 5.0), 2)
            if curr == "STARS":
                bonus_amount = round(bonus_amount * 1.5, 1)
            elif curr == "RUB":
                bonus_amount = round(bonus_amount * 2.5, 2)

            cursor.execute("UPDATE users SET balance = balance + ?, last_bonus = ? WHERE user_id = ?", (bonus_amount, now, user_id))
            conn.commit()
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu"))
            edit_text(
                f"🎁 **Ежедневный бонус забран!**\n\n"
                f"💰 На ваш баланс зачислено: **+{bonus_amount} {sym}**\n\n"
                f"Возвращайтесь через 24 часа за новым бонусом!",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            time_left = cooldown - (now - last_bonus)
            hours = time_left // 3600
            minutes = (time_left % 3600) // 60
            bot.send_message(call.message.chat.id, f"⏳ Бонус уже получен! Заходите через {hours} ч. {minutes} мин.")

    elif call.data == "catalog_cats":
        cursor.execute("SELECT id, name, price_uah, price_stars, price_rub FROM catalog_items")
        items = cursor.fetchall()
        
        markup = types.InlineKeyboardMarkup()
        if not items:
            text = "🛒 **Каталог товаров пока пуст.**\nОжидайте пополнения!"
        else:
            text = f"📱 **Выберите номер / товар для покупки:**\n\nВаша валюта: **{curr}**"
            for item_id, name, p_uah, p_stars, p_rub in items:
                price = p_uah if curr == "UAH" else (p_stars if curr == "STARS" else p_rub)
                btn_text = f"📱 {name} — {price:.2f} {sym}"
                markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"item_{item_id}"))
        
        markup.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu"))
        show_menu(call.message, "catalog", text, markup)

    elif call.data.startswith("item_"):
        item_id = call.data.split("_")[1]
        cursor.execute("SELECT name, category, price_uah, price_stars, price_rub FROM catalog_items WHERE id=?", (item_id,))
        item = cursor.fetchone()
        
        if not item:
            bot.send_message(call.message.chat.id, "❌ Товар не найден!")
            return

        name, cat_name, p_uah, p_stars, p_rub = item
        price = p_uah if curr == "UAH" else (p_stars if curr == "STARS" else p_rub)

        markup = types.InlineKeyboardMarkup()
        btn_req = types.InlineKeyboardButton("🛍 Купить с баланса", callback_data=f"req_{item_id}")
        btn_contact = types.InlineKeyboardButton("💬 Написать менеджеру", url=f"https://t.me/{MANAGER_USERNAME}")
        btn_back = types.InlineKeyboardButton("⬅️ К выбору номеров", callback_data="catalog_cats")
        markup.add(btn_req)
        markup.add(btn_contact)
        markup.add(btn_back)

        text = (
            f"📱 **Товар / Номер:** {name}\n"
            f"💰 **Цена:** {price:.2f} {sym}\n"
            f"📊 **Статус:** ✅ В наличии\n\n"
            "Нажмите **«Купить с баланса»** для автоматической оплаты."
        )
        show_menu(call.message, "item", text, markup)

    elif call.data.startswith("req_"):
        item_id = call.data.split("_")[1]
        cursor.execute("SELECT name, price_uah, price_stars, price_rub FROM catalog_items WHERE id=?", (item_id,))
        item = cursor.fetchone()
        
        if not item:
            bot.send_message(call.message.chat.id, "❌ Товар не найден!")
            return

        name, p_uah, p_stars, p_rub = item
        price = p_uah if curr == "UAH" else (p_stars if curr == "STARS" else p_rub)

        if balance < price:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Пополнить баланс", callback_data="top_up_balance"))
            markup.add(types.InlineKeyboardButton("⬅️ К выбору номеров", callback_data="catalog_cats"))
            
            bot.send_message(
                call.message.chat.id,
                f"❌ **Недостаточно средств на балансе!**\n\n"
                f"💵 Стоимость: **{price:.2f} {sym}**\n"
                f"💰 Ваш баланс: **{balance:.2f} {sym}**\n\n"
                f"Пополните баланс для совершения покупки.",
                parse_mode="Markdown",
                reply_markup=markup
            )
            return

        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (price, user_id))
        cursor.execute("INSERT INTO orders (user_id, item_name, price, currency) VALUES (?, ?, ?, ?)", (user_id, name, price, curr))
        conn.commit()
        order_id = cursor.lastrowid

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💬 Перейти к менеджеру", url=f"https://t.me/{MANAGER_USERNAME}"))
        
        edit_text(
            f"✅ **Оплата прошла успешно!**\n\n"
            f"📦 Товар / Номер: **{name}**\n"
            f"💰 Списано: **{price:.2f} {sym}**\n"
            f"🧾 Заказ #{order_id}\n\n"
            f"Напишите нашему менеджеру @{MANAGER_USERNAME} для получения товара/номера.", 
            call.message.chat.id, 
            call.message.message_id, 
            parse_mode="Markdown",
            reply_markup=markup
        )

        username = f"@{call.from_user.username}" if call.from_user.username else "без username"
        admin_markup = types.InlineKeyboardMarkup()
        btn_done = types.InlineKeyboardButton("✅ Выдано (Завершить)", callback_data=f"done_{order_id}_{user_id}")
        admin_markup.add(btn_done)

        admin_text = (
            f"📥 **ОПЛАЧЕННЫЙ ЗАКАЗ #{order_id}!**\n\n"
            f"👤 Покупатель: {call.from_user.first_name} ({username})\n"
            f"🆔 ID: `{user_id}`\n"
            f"📦 Товар: **{name}**\n"
            f"💵 Оплачено с баланса: **{price:.2f} {sym}** ({curr})"
        )
        try:
            bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=admin_markup)
        except Exception as e:
            print(f"Ошибка отправки админу: {e}")

    elif call.data == "faq_info":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💬 Написать менеджеру", url=f"https://t.me/{MANAGER_USERNAME}"))
        markup.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu"))

        text = (
            "📖 **Информация и Правила магазина**\n\n"
            "⏰ **Режим работы:** 24/7 (Поддержка ответит в течение 10–15 минут).\n\n"
            "🛡 **Гарантия и условия:**\n"
            "• Все товары проходят строгую проверку перед выдачей.\n"
            "• Замена товара или возврат осуществляется при наличии видеозаписи с момента покупки.\n"
            "• Время на замену невалида — 20 минут с момента выдачи.\n\n"
            "💳 **Пополнение и Оплата:**\n"
            "• Автоматическое зачисление после подтверждения платежа админом.\n"
            "• В случае вопросов по оплате пишите менеджеру: @" + MANAGER_USERNAME
        )
        show_menu(call.message, "faq", text, markup)

    elif call.data.startswith("done_"):
        _, order_id, client_id = call.data.split("_")
        cursor.execute("UPDATE orders SET status='completed' WHERE order_id=?", (order_id,))
        conn.commit()

        edit_text(f"✅ **Заказ #{order_id} выполнен!**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
        markup = types.InlineKeyboardMarkup(row_width=5)
        btns = [types.InlineKeyboardButton(f"⭐ {i}", callback_data=f"rate_{order_id}_{i}") for i in range(1, 6)]
        markup.add(*btns)

        try:
            bot.send_message(
                client_id, 
                f"🎉 **Заказ #{order_id} выполнен!** Менеджер подтвердил выдачу товара.\n\n"
                f"⭐ **Пожалуйста, оцените качество обслуживания:**\n"
                f"💡 *За отзыв 5★ вы автоматически получите бонус на баланс!*", 
                parse_mode="Markdown",
                reply_markup=markup
            )
        except Exception as e:
            print(f"Ошибка отправки клиенту: {e}")

    elif call.data.startswith("rate_"):
        _, order_id, rating = call.data.split("_")
        rating = int(rating)

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⏭ Пропустить отзыв", callback_data=f"skip_rev_{order_id}_{rating}"))

        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = edit_text(
            f"⭐️ Вы поставили оценку **{rating}/5 ⭐**.\n\n"
            f"✍️ **Напишите краткий отзыв о покупке** (или нажмите кнопку «Пропустить»):",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_review_text, order_id, rating)

    elif call.data.startswith("skip_rev_"):
        _, _, order_id, rating = call.data.split("_")
        rating = int(rating)
        save_review(order_id, user_id, rating, "Без текстового отзыва", call.from_user.first_name, call.from_user.username)
        edit_text("🙏 **Спасибо за вашу оценку!** Нам очень важно ваше мнение.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

    elif call.data == "profile":
        markup = types.InlineKeyboardMarkup()
        btn_topup = types.InlineKeyboardButton("💳 Пополнить баланс", callback_data="top_up_balance")
        btn_ref = types.InlineKeyboardButton("👥 Реферальная система", callback_data="ref_system")
        btn_curr = types.InlineKeyboardButton(f"🌐 Валюта: {curr}", callback_data="change_currency")
        btn_orders = types.InlineKeyboardButton("📜 Мои заказы", callback_data="my_orders")
        btn_promo = types.InlineKeyboardButton("🎁 Активировать промокод", callback_data="use_promo")
        btn_back = types.InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")
        
        markup.add(btn_topup)
        markup.add(btn_ref)
        markup.add(btn_curr, btn_orders)
        markup.add(btn_promo)
        markup.add(btn_back)
        
        text = f"👤 **Профиль**\n\n🆔 Ваш ID: `{user_id}`\n💰 Баланс: **{balance:.2f} {sym}**\n🌐 Выбранная валюта: **{curr}**"
        show_menu(call.message, "profile", text, markup)

    # ==================== ВЫБОР МЕТОДА ПОПОЛНЕНИЯ БАЛАНСА (ТОЧНО КАК В MAIN 3) ====================
    elif call.data == "top_up_balance":
        markup = types.InlineKeyboardMarkup()
        b_uah = types.InlineKeyboardButton("💳 UAH (Карта)", callback_data="topup_method_uah")
        b_stars = types.InlineKeyboardButton("⭐ STARS (Telegram Подарок)", callback_data="topup_method_stars")
        b_back = types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile")
        b_ton = types.InlineKeyboardButton("💎 TON (Кошелёк)", callback_data="topup_method_ton")
        b_rub = types.InlineKeyboardButton("🇷🇺 Рубли (RUB)", callback_data="topup_method_rub")
        markup.add(b_uah, b_stars)
        markup.add(b_ton, b_rub)
        markup.add(b_back)

        show_menu(call.message, "topup", "💳 **Выберите способ пополнения баланса:**", markup)

    elif call.data == "topup_method_uah":
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id, 
            "💳 **Пополнение баланса картой (UAH / грн)**\n\n"
            "Введите сумму пополнения в **грн** (например: `100` или `250`):", 
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_topup_amount)

    elif call.data == "topup_method_stars":
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id, 
            "⭐ **Пополнение баланса Звёздами (Telegram Gifts)**\n\n"
            "Введите количество звёзд, на которое хотите пополнить (например: `50`, `100`, `500`):", 
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_topup_stars_amount)

    elif call.data == "topup_method_ton":
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id,
            "💎 **Пополнение баланса через TON**\n\n"
            f"Курс: 1 TON = {TON_RATE_UAH:g} грн = {TON_RATE_RUB:g} ₽\n\n"
            "Введите количество **TON**, на которое хотите пополнить (например: `1` или `2.5`):",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_topup_ton_amount)

    elif call.data.startswith("paidton_"):
        payment_id = call.data.split("_", 1)[1]
        cursor.execute("SELECT amount, status FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()

        if not p_row:
            bot.send_message(call.message.chat.id, "❌ Заявка не найдена!")
            return

        p_amount, p_status = p_row

        if p_status == "completed":
            bot.send_message(call.message.chat.id, "✅ Этот платёж уже был зачислен!")
            return

        edit_text(
            f"⏳ **Заявка на проверку TON-перевода отправлена!**\n\n"
            f"💎 Сумма: **{p_amount:g} TON**\n"
            f"🆔 ID заявки: `{payment_id}`\n\n"
            "Администратор проверит поступление и зачислит баланс.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )

        username = f"@{call.from_user.username}" if call.from_user.username else "без username"
        adm_markup = types.InlineKeyboardMarkup()
        btn_confirm = types.InlineKeyboardButton("✅ Подтвердить (Начислить)", callback_data=f"admconfirmton_{payment_id}")
        btn_reject = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"admreject_{payment_id}")
        adm_markup.add(btn_confirm, btn_reject)

        adm_text = (
            f"💎 **ЗАЯВКА НА ПОПОЛНЕНИЕ TON!**\n\n"
            f"👤 Покупатель: {call.from_user.first_name} ({username})\n"
            f"🆔 ID пользователя: `{user_id}`\n"
            f"💎 Ожидаемая сумма: **{p_amount:g} TON**\n"
            f"🧾 Комментарий к переводу (должен совпадать): `{payment_id}`\n\n"
            f"📌 Проверьте поступление на кошелёк и нажмите кнопку ниже:"
        )
        try:
            bot.send_message(ADMIN_ID, adm_text, parse_mode="Markdown", reply_markup=adm_markup)
        except Exception as e:
            print(f"Ошибка отправки админу: {e}")

    elif call.data.startswith("admconfirmton_"):
        if user_id != ADMIN_ID: return
        payment_id = call.data.split("_", 1)[1]

        cursor.execute("SELECT user_id, amount, status FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()
        if not p_row: return

        p_uid, p_amount, p_status = p_row
        if p_status == "completed":
            bot.answer_callback_query(call.id, "⚠️ Эта заявка уже обработана!", show_alert=True)
            return

        cursor.execute("SELECT currency FROM users WHERE user_id=?", (p_uid,))
        u_curr_row = cursor.fetchone()
        u_curr = u_curr_row[0] if u_curr_row else "UAH"

        final_amount = convert_currency(p_amount, "TON", u_curr)

        cursor.execute("UPDATE payments SET status='completed' WHERE payment_id=?", (payment_id,))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (final_amount, p_uid))
        conn.commit()

        sym = CURRENCY_SYMBOLS.get(u_curr, "")
        edit_text(f"✅ TON-платёж подтверждён! Пользователю {p_uid} зачислено +{final_amount:.2f} {sym}.", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(p_uid, f"🎉 **Платёж TON подтверждён!**\n\n💰 На ваш баланс зачислено: **+{final_amount:.2f} {sym}**", parse_mode="Markdown")
        except Exception: pass

    elif call.data == "topup_method_rub":
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id,
            "🇷🇺 **Пополнение баланса рублями (RUB)**\n\n"
            f"Курс: 2 ₽ = 1 ⭐\n\n"
            "Введите сумму в **рублях**, на которую хотите пополнить (например: `500`):",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_topup_rub_amount)

    elif call.data.startswith("paidrub_"):
        payment_id = call.data.split("_", 1)[1]
        cursor.execute("SELECT amount, status FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()

        if not p_row:
            bot.send_message(call.message.chat.id, "❌ Заявка не найдена!")
            return

        p_amount, p_status = p_row

        if p_status == "completed":
            bot.send_message(call.message.chat.id, "✅ Этот платёж уже был зачислен!")
            return

        edit_text(
            f"⏳ **Заявка на проверку RUB-перевода отправлена!**\n\n"
            f"🇷🇺 Сумма: **{p_amount:g} ₽**\n"
            f"🆔 ID заявки: `{payment_id}`\n\n"
            "Администратор проверит поступление и зачислит баланс.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )

        username = f"@{call.from_user.username}" if call.from_user.username else "без username"
        adm_markup = types.InlineKeyboardMarkup()
        btn_confirm = types.InlineKeyboardButton("✅ Подтвердить (Начислить)", callback_data=f"admconfirmrub_{payment_id}")
        btn_reject = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"admreject_{payment_id}")
        adm_markup.add(btn_confirm, btn_reject)

        adm_text = (
            f"🇷🇺 **ЗАЯВКА НА ПОПОЛНЕНИЕ RUB!**\n\n"
            f"👤 Покупатель: {call.from_user.first_name} ({username})\n"
            f"🆔 ID пользователя: `{user_id}`\n"
            f"🇷🇺 Ожидаемая сумма: **{p_amount:g} ₽**\n"
            f"🧾 ID заявки: `{payment_id}`\n\n"
            f"📌 Проверьте поступление на карту и нажмите кнопку ниже:"
        )
        try:
            bot.send_message(ADMIN_ID, adm_text, parse_mode="Markdown", reply_markup=adm_markup)
        except Exception as e:
            print(f"Ошибка отправки админу: {e}")

    elif call.data.startswith("admconfirmrub_"):
        if user_id != ADMIN_ID: return
        payment_id = call.data.split("_", 1)[1]

        cursor.execute("SELECT user_id, amount, status FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()
        if not p_row: return

        p_uid, p_amount, p_status = p_row
        if p_status == "completed":
            bot.answer_callback_query(call.id, "⚠️ Эта заявка уже обработана!", show_alert=True)
            return

        cursor.execute("SELECT currency FROM users WHERE user_id=?", (p_uid,))
        u_curr_row = cursor.fetchone()
        u_curr = u_curr_row[0] if u_curr_row else "UAH"

        final_amount = convert_currency(p_amount, "RUB", u_curr)

        cursor.execute("UPDATE payments SET status='completed' WHERE payment_id=?", (payment_id,))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (final_amount, p_uid))
        conn.commit()

        sym = CURRENCY_SYMBOLS.get(u_curr, "")
        edit_text(f"✅ RUB-платёж подтверждён! Пользователю {p_uid} зачислено +{final_amount:.2f} {sym}.", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(p_uid, f"🎉 **Платёж рублями подтверждён!**\n\n💰 На ваш баланс зачислено: **+{final_amount:.2f} {sym}**", parse_mode="Markdown")
        except Exception: pass

    elif call.data.startswith("paid_"):
        payment_id = call.data.split("_", 1)[1]
        cursor.execute("SELECT amount, status FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()
        
        if not p_row:
            bot.send_message(call.message.chat.id, "❌ Счет не найден!")
            return

        p_amount, p_status = p_row

        if p_status == "completed":
            bot.send_message(call.message.chat.id, "✅ Этот платеж уже подтвержден!")
            return

        edit_text(
            f"⏳ **Заявка отправлена администратору!**\n\n"
            f"💰 Сумма: **{p_amount:.2f} грн**\n"
            f"🆔 ID платежа: `{payment_id}`\n\n"
            "После проверки администратор зачислит средства.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )

        username = f"@{call.from_user.username}" if call.from_user.username else "без username"
        adm_markup = types.InlineKeyboardMarkup()
        btn_confirm = types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"admconfirm_{payment_id}")
        btn_reject = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"admreject_{payment_id}")
        adm_markup.add(btn_confirm, btn_reject)

        adm_text = (
            f"📥 **Заявка на пополнение UAH!**\n\n"
            f"👤 Покупатель: {call.from_user.first_name} ({username})\n"
            f"🆔 ID пользователя: `{user_id}`\n"
            f"💰 Сумма: **{p_amount:.2f} грн**\n"
            f"🧾 ID платежа: `{payment_id}`"
        )
        try:
            bot.send_message(ADMIN_ID, adm_text, parse_mode="Markdown", reply_markup=adm_markup)
        except Exception as e:
            print(f"Ошибка отправки админу: {e}")

    elif call.data.startswith("paidstars_"):
        payment_id = call.data.split("_", 1)[1]
        cursor.execute("SELECT amount, status FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()

        if not p_row:
            bot.send_message(call.message.chat.id, "❌ Заявка не найдена!")
            return

        p_amount, p_status = p_row

        if p_status == "completed":
            bot.send_message(call.message.chat.id, "✅ Эти звёзды уже были зачислены!")
            return

        edit_text(
            f"⏳ **Заявка на проверку подарка отправлена!**\n\n"
            f"⭐ Заявлено: **{int(p_amount)} ⭐**\n"
            f"🆔 ID заявки: `{payment_id}`\n\n"
            f"Администратор проверит получение подарка на **@{GARANT_MD}** и зачислит баланс.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )

        username = f"@{call.from_user.username}" if call.from_user.username else "без username"
        adm_markup = types.InlineKeyboardMarkup()
        btn_confirm = types.InlineKeyboardButton("✅ Подтвердить (Начислить)", callback_data=f"admconfirmstars_{payment_id}")
        btn_reject = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"admreject_{payment_id}")
        adm_markup.add(btn_confirm, btn_reject)

        adm_text = (
            f"🎁 **ЗАЯВКА НА ПОПОЛНЕНИЕ ЗВЁЗДАМИ (GIFT)!**\n\n"
            f"👤 Покупатель: {call.from_user.first_name} ({username})\n"
            f"🆔 ID пользователя: `{user_id}`\n"
            f"⭐ Ожидаемый подарок на сумму: **{int(p_amount)} ⭐**\n"
            f"🧾 ID заявки: `{payment_id}`\n\n"
            f"📌 **Проверьте получение подарка на @{GARANT_MD}** и нажмите кнопку ниже:"
        )
        try:
            bot.send_message(ADMIN_ID, adm_text, parse_mode="Markdown", reply_markup=adm_markup)
        except Exception as e:
            print(f"Ошибка отправки админу: {e}")

    elif call.data.startswith("admconfirm_"):
        if user_id != ADMIN_ID: return
        payment_id = call.data.split("_", 1)[1]

        cursor.execute("SELECT user_id, amount, status FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()
        if not p_row: return

        p_uid, p_amount, p_status = p_row
        if p_status == "completed":
            bot.answer_callback_query(call.id, "⚠️ Платеж уже обработан!", show_alert=True)
            return

        cursor.execute("SELECT currency FROM users WHERE user_id=?", (p_uid,))
        u_curr_row = cursor.fetchone()
        u_curr = u_curr_row[0] if u_curr_row else "UAH"

        final_amount = convert_currency(p_amount, "UAH", u_curr)

        cursor.execute("UPDATE payments SET status='completed' WHERE payment_id=?", (payment_id,))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (final_amount, p_uid))
        conn.commit()

        sym = CURRENCY_SYMBOLS.get(u_curr, "")
        edit_text(f"✅ **Оплата #{payment_id} подтверждена!** Зачислено +{final_amount:.2f} {sym}.", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(p_uid, f"🎉 **Баланс успешно пополнен!**\n💰 Вам зачислено **+{final_amount:.2f} {sym}**.", parse_mode="Markdown")
        except Exception: pass

    elif call.data.startswith("admconfirmstars_"):
        if user_id != ADMIN_ID: return
        payment_id = call.data.split("_", 1)[1]

        cursor.execute("SELECT user_id, amount, status FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()
        if not p_row: return

        p_uid, p_amount, p_status = p_row
        if p_status == "completed":
            bot.answer_callback_query(call.id, "⚠️ Эта заявка уже обработана!", show_alert=True)
            return

        cursor.execute("SELECT currency FROM users WHERE user_id=?", (p_uid,))
        u_curr_row = cursor.fetchone()
        u_curr = u_curr_row[0] if u_curr_row else "STARS"

        final_amount = convert_currency(p_amount, "STARS", u_curr)

        cursor.execute("UPDATE payments SET status='completed' WHERE payment_id=?", (payment_id,))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (final_amount, p_uid))
        conn.commit()

        sym = CURRENCY_SYMBOLS.get(u_curr, "")
        edit_text(f"✅ **Подарок подтверждён!** Пользователю `{p_uid}` зачислено **+{final_amount:.2f} {sym}**.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        try:
            bot.send_message(p_uid, f"🎉 **Подарок проверен и подтверждён!**\n\n⭐ На ваш баланс зачислено: **+{final_amount:.2f} {sym}**", parse_mode="Markdown")
        except Exception: pass

    elif call.data.startswith("admreject_"):
        if user_id != ADMIN_ID: return
        payment_id = call.data.split("_", 1)[1]

        cursor.execute("SELECT user_id, amount FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()
        if not p_row: return
        p_uid, p_amount = p_row

        cursor.execute("UPDATE payments SET status='rejected' WHERE payment_id=?", (payment_id,))
        conn.commit()

        edit_text(f"❌ **Заявка #{payment_id} отклонена.**", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(p_uid, f"❌ **Заявка на пополнение была отклонена.** Средства/подарок не поступили.", parse_mode="Markdown")
        except Exception: pass

    elif call.data == "change_currency":
        show_menu(call.message, "currency", get_currency_text(), get_currency_markup(back_to_profile=True))

    elif call.data.startswith("set_curr_"):
        new_curr = call.data[len("set_curr_"):]
        if new_curr not in CURRENCY_SYMBOLS:
            safe_answer("❌ Неизвестная валюта", True)
            return

        first_time = not is_currency_set(user_id)

        cursor.execute("SELECT balance, currency FROM users WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        old_bal = row[0] if row and row[0] is not None else 0.0
        old_curr = row[1] if row and row[1] else "UAH"

        # Баланс автоматически переводится в выбранную валюту по курсу
        if old_curr != new_curr and old_bal > 0:
            current_bal = convert_currency(old_bal, old_curr, new_curr)
        else:
            current_bal = old_bal

        cursor.execute("UPDATE users SET currency=?, balance=?, curr_set=1 WHERE user_id=?", (new_curr, current_bal, user_id))
        conn.commit()
        safe_answer(f"✅ Валюта: {new_curr}")

        if first_time:
            text = get_main_menu_text(call.from_user.first_name)
            show_menu(call.message, "main", text, get_main_menu_keyboard())
            return

        new_sym = CURRENCY_SYMBOLS.get(new_curr, "грн")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 Пополнить баланс", callback_data="top_up_balance"))
        markup.add(types.InlineKeyboardButton("👥 Реферальная система", callback_data="ref_system"))
        markup.add(types.InlineKeyboardButton(f"🌐 Валюта: {new_curr}", callback_data="change_currency"), types.InlineKeyboardButton("📜 Мои заказы", callback_data="my_orders"))
        markup.add(types.InlineKeyboardButton("🎁 Активировать промокод", callback_data="use_promo"))
        markup.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu"))

        text = f"👤 **Профиль**\n\n🆔 Ваш ID: `{user_id}`\n💰 Баланс: **{current_bal:.2f} {new_sym}**\n🌐 Выбранная валюта: **{new_curr}**"
        show_menu(call.message, "profile", text, markup)

    elif call.data == "ref_system":
        cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (user_id,))
        ref_count = cursor.fetchone()[0]
        
        bot_username = BOT_USERNAME if BOT_USERNAME else "your_bot"
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        rew_val, rew_sym = REF_REWARDS.get(curr, (3.0, "грн"))

        text = (
            f"👥 **Реферальная система**\n\n"
            f"Приглашайте друзей и получайте пассивный доход!\n\n"
            f"💰 Награда за 1 друга: **+{rew_val} {rew_sym}**\n"
            f"📊 Приглашено друзей: **{ref_count}**\n\n"
            f"🔗 **Ваша реферальная ссылка:**\n`{ref_link}`"
        )

        comp = get_competition()
        if comp["active"]:
            days_left = max(0, int((comp["end_at"] - time.time()) // 86400))
            hours_left = max(0, int(((comp["end_at"] - time.time()) % 86400) // 3600))
            board = get_leaderboard(1000)
            place = next((i + 1 for i, r in enumerate(board) if r[0] == user_id), None)
            my_cnt = next((r[1] for r in board if r[0] == user_id), 0)
            place_str = f"#{place}" if place else "вне топа"
            text += (
                f"\n\n🏆 **Идёт конкурс на самых активных приглашающих!**\n"
                f"🥇 {comp['prize1']}\n🥈 {comp['prize2']}\n🥉 {comp['prize3']}\n\n"
                f"⏳ Осталось: **{days_left}д {hours_left}ч**\n"
                f"📍 Ваше место: **{place_str}** ({my_cnt} реф. за конкурс)"
            )

        markup = types.InlineKeyboardMarkup()
        if comp["active"]:
            markup.add(types.InlineKeyboardButton("🏆 Топ участников", callback_data="contest_top_user"))
        markup.add(types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile"))
        show_menu(call.message, "ref", text, markup)

    elif call.data == "contest_top_user":
        board = get_leaderboard(10)
        if not board:
            text = "🏆 **Топ участников конкурса**\n\nПока никто не пригласил друзей."
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for i, (uid, cnt) in enumerate(board):
                mark = medals[i] if i < 3 else f"{i+1}."
                lines.append(f"{mark} {get_display_name(uid)} — {cnt} реф.")
            text = "🏆 **Топ участников конкурса**\n\n" + "\n".join(lines)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="ref_system"))
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "my_orders":
        cursor.execute("SELECT order_id, item_name, price, currency, status FROM orders WHERE user_id=? ORDER BY order_id DESC LIMIT 10", (user_id,))
        orders = cursor.fetchall()
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile"))

        if not orders:
            text = "📜 **У вас пока нет заказов.**"
        else:
            text = "📜 **История ваших последних заказов:**\n\n"
            for order_id, item_name, price, o_curr, status in orders:
                st_text = "✅ Выполнен" if status == "completed" else "⏳ В обработке"
                o_sym = CURRENCY_SYMBOLS.get(o_curr, "грн")
                text += f"📦 **Заказ #{order_id}** | {item_name}\n💰 Сумма: {price:.2f} {o_sym} | Статус: `{st_text}`\n---\n"

        show_menu(call.message, "orders", text, markup)

    elif call.data == "use_promo":
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(call.message.chat.id, "🎁 **Введите промокод:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_promo_activation)

    elif call.data == "main_menu":
        text = get_main_menu_text(call.from_user.first_name)
        markup = get_main_menu_keyboard()
        show_menu(call.message, "main", text, markup)

    elif call.data == "admin_del_item":
        if user_id != ADMIN_ID: return
        cursor.execute("SELECT id, name, price_uah, category FROM catalog_items")
        items = cursor.fetchall()
        
        markup = types.InlineKeyboardMarkup()
        if not items:
            bot.send_message(call.message.chat.id, "❌ В каталоге нет товаров для удаления.")
            return

        for item_id, name, price_uah, category in items:
            markup.add(types.InlineKeyboardButton(f"❌ Удалить: {name} ({price_uah} грн)", callback_data=f"delitem_{item_id}"))

        bot.send_message(call.message.chat.id, "🗑 **Выберите товар для удаления:**", reply_markup=markup)

    elif call.data.startswith("delitem_"):
        if user_id != ADMIN_ID: return
        item_id = call.data.split("_")[1]
        cursor.execute("DELETE FROM catalog_items WHERE id=?", (item_id,))
        conn.commit()
        edit_text("✅ Товар успешно удален из каталога!", call.message.chat.id, call.message.message_id)

    elif call.data == "admin_broadcast":
        if user_id != ADMIN_ID: return
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(call.message.chat.id, "📢 **Массовая рассылка**\n\nОтправьте сообщение для рассылки:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_broadcast)

    elif call.data == "admin_stats":
        if user_id != ADMIN_ID: return
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status='completed'")
        total_orders = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM catalog_items")
        total_items = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(rating), COUNT(*) FROM reviews")
        avg_rev, count_rev = cursor.fetchone()
        avg_rev_str = f"{avg_rev:.1f}" if avg_rev else "Нет оценок"

        text = (
            f"📊 **Статистика магазина:**\n\n"
            f"👥 Всего пользователей: **{total_users}**\n"
            f"🛒 Товаров в каталоге: **{total_items}**\n"
            f"📦 Выполнено заказов: **{total_orders}**\n\n"
            f"⭐ Средний рейтинг: **{avg_rev_str} / 5**\n"
            f"💬 Всего отзывов: **{count_rev}**"
        )
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

    elif call.data == "admin_give_info":
        if user_id != ADMIN_ID: return
        bot.send_message(call.message.chat.id, "💰 Чтобы выдать баланс, отправьте команду:\n`/give_balance ID СУММА`\n\n*Пример:* `/give_balance 7408654429 100`", parse_mode="Markdown")

    elif call.data == "admin_promo_info":
        if user_id != ADMIN_ID: return
        bot.send_message(call.message.chat.id, "🎁 Чтобы создать промокод, отправьте команду:\n`/add_promo КОД СУММА КОЛИЧЕСТВО`\n\n*Пример:* `/add_promo BONUS50 50 10`", parse_mode="Markdown")

    elif call.data == "admin_contest":
        if user_id != ADMIN_ID: return
        comp = get_competition()
        markup = types.InlineKeyboardMarkup()
        if comp["active"]:
            days_left = max(0, int((comp["end_at"] - time.time()) // 86400))
            status = f"🟢 Активен, осталось {days_left} дн."
            markup.add(types.InlineKeyboardButton("⏹ Остановить", callback_data="contest_stop"))
            markup.add(types.InlineKeyboardButton("🏁 Завершить и наградить", callback_data="contest_finish"))
        else:
            status = "🔴 Не запущен"
            markup.add(types.InlineKeyboardButton("▶️ 3 дня", callback_data="contest_start_3"),
                       types.InlineKeyboardButton("▶️ 7 дней", callback_data="contest_start_7"))
            markup.add(types.InlineKeyboardButton("▶️ 14 дней", callback_data="contest_start_14"),
                       types.InlineKeyboardButton("▶️ 30 дней", callback_data="contest_start_30"))
        markup.add(types.InlineKeyboardButton("🎁 Изменить призы", callback_data="contest_set_prizes"))
        markup.add(types.InlineKeyboardButton("📊 Топ сейчас", callback_data="contest_top_admin"))
        markup.add(types.InlineKeyboardButton("⬅️ Админ-панель", callback_data="admin_home"))

        text = (
            f"🏆 **Инвайт-соревнование**\n\n"
            f"Статус: {status}\n\n"
            f"🥇 {comp['prize1']}\n🥈 {comp['prize2']}\n🥉 {comp['prize3']}\n\n"
            f"Побеждают те, кто пригласил больше всего новых пользователей за время конкурса."
        )
        edit_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("contest_start_"):
        if user_id != ADMIN_ID: return
        days = int(call.data.split("_")[-1])
        now = int(time.time())
        cursor.execute("UPDATE competition SET active=1, start_at=?, end_at=? WHERE id=1", (now, now + days * 86400))
        conn.commit()
        bot.answer_callback_query(call.id, f"✅ Конкурс запущен на {days} дн.!", show_alert=True)
        comp = get_competition()
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⏹ Остановить", callback_data="contest_stop"))
        markup.add(types.InlineKeyboardButton("🏁 Завершить и наградить", callback_data="contest_finish"))
        markup.add(types.InlineKeyboardButton("🎁 Изменить призы", callback_data="contest_set_prizes"))
        markup.add(types.InlineKeyboardButton("📊 Топ сейчас", callback_data="contest_top_admin"))
        markup.add(types.InlineKeyboardButton("⬅️ Админ-панель", callback_data="admin_home"))
        text = (
            f"🏆 **Инвайт-соревнование**\n\nСтатус: 🟢 Активен, {days} дн.\n\n"
            f"🥇 {comp['prize1']}\n🥈 {comp['prize2']}\n🥉 {comp['prize3']}"
        )
        edit_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "contest_stop":
        if user_id != ADMIN_ID: return
        cursor.execute("UPDATE competition SET active=0 WHERE id=1")
        conn.commit()
        bot.answer_callback_query(call.id, "⏹ Конкурс остановлен.", show_alert=True)

    elif call.data == "contest_set_prizes":
        if user_id != ADMIN_ID: return
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id,
            "🎁 Отправьте 3 приза, каждый с новой строки (1 место, 2 место, 3 место).\n\n"
            "*Пример:*\n100 грн на баланс\n50 грн на баланс\n25 грн на баланс",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_contest_prizes)

    elif call.data == "contest_top_admin":
        if user_id != ADMIN_ID: return
        board = get_leaderboard(10)
        if not board:
            text = "🏆 **Топ участников**\n\nПока никто не пригласил друзей."
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for i, (uid, cnt) in enumerate(board):
                mark = medals[i] if i < 3 else f"{i+1}."
                lines.append(f"{mark} {get_display_name(uid)} (`{uid}`) — {cnt} реф.")
            text = "🏆 **Топ участников**\n\n" + "\n".join(lines)
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

    elif call.data == "contest_finish":
        if user_id != ADMIN_ID: return
        comp = get_competition()
        board = get_leaderboard(3)
        cursor.execute("UPDATE competition SET active=0 WHERE id=1")
        conn.commit()

        if not board:
            bot.send_message(call.message.chat.id, "🏁 Конкурс завершён. Участников не было.")
            return

        prizes = [comp["prize1"], comp["prize2"], comp["prize3"]]
        medals = ["🥇", "🥈", "🥉"]
        summary_lines = []
        for i, (uid, cnt) in enumerate(board):
            prize = prizes[i] if i < len(prizes) else "приз"
            summary_lines.append(f"{medals[i]} {get_display_name(uid)} (`{uid}`) — {cnt} реф. → {prize}")
            try:
                bot.send_message(
                    uid,
                    f"🏆 **Конкурс завершён!**\n\n"
                    f"Вы заняли **{i+1} место** ({cnt} приглашённых друзей)!\n"
                    f"🎁 Ваш приз: **{prize}**\n\n"
                    f"Администратор свяжется с вами для вручения приза.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Не удалось уведомить победителя {uid}: {e}")

        bot.send_message(call.message.chat.id, "🏁 **Конкурс завершён! Результаты:**\n\n" + "\n".join(summary_lines), parse_mode="Markdown")

    elif call.data == "admin_search_user":
        if user_id != ADMIN_ID: return
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(call.message.chat.id, "🔎 Отправьте ID пользователя для поиска:")
        bot.register_next_step_handler(msg, process_search_user)

    elif call.data == "admin_export_orders":
        if user_id != ADMIN_ID: return
        cursor.execute("SELECT order_id, user_id, item_name, price, currency, status FROM orders ORDER BY order_id DESC")
        rows = cursor.fetchall()
        if not rows:
            bot.send_message(call.message.chat.id, "📤 Заказов пока нет.")
            return
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["order_id", "user_id", "item_name", "price", "currency", "status"])
        writer.writerows(rows)
        data = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
        data.name = f"orders_{int(time.time())}.csv"
        bot.send_document(call.message.chat.id, data, caption=f"📤 Экспорт заказов: {len(rows)} шт.")

# ==================== STEP HANDLERS (ОБРАБОТКА ВВОДА) ====================
def process_topup_amount(message):
    if message.text and message.text.startswith('/'):
        return

    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount < 10:
            msg = bot.reply_to(message, "❌ Минимальная сумма пополнения: **10 грн**.\nВведите сумму ещё раз:", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_topup_amount)
            return
        
        user_id = message.from_user.id
        payment_id = f"pay_{user_id}_{int(time.time())}"

        cursor.execute("INSERT INTO payments (payment_id, user_id, amount) VALUES (?, ?, ?)", (payment_id, user_id, amount))
        conn.commit()

        markup = types.InlineKeyboardMarkup()
        btn_paid = types.InlineKeyboardButton("✅ Я оплатил", callback_data=f"paid_{payment_id}")
        btn_back = types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile")
        markup.add(btn_paid)
        markup.add(btn_back)

        text = (
            f"💳 **Пополнение баланса #{payment_id}**\n\n"
            f"💰 Сумма к оплате: **{amount:.2f} грн**\n\n"
            f"📌 **Реквизиты для перевода:**\n"
            f"💳 Карта: `{CARD_NUMBER}`\n"
            f"🏦 Банк: **{CARD_HOLDER}**\n\n"
            "⚠️ **Инструкция:**\n"
            "1. Скопируйте номер карты (нажмите на него).\n"
            f"2. Переведите ровно **{amount:.2f} грн** через приложение вашего банка.\n"
            "3. После совершения перевода нажмите кнопку **«✅ Я оплатил»** ниже."
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

    except ValueError:
        msg = bot.reply_to(message, "❌ **Ошибка ввода!** Введите только число (например: `100` или `250.50`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_topup_amount)

def process_topup_stars_amount(message):
    if message.text and message.text.startswith('/'):
        return

    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount <= 0:
            msg = bot.reply_to(message, "❌ Сумма должна быть больше 0 ⭐.\nВведите количество звёзд ещё раз:")
            bot.register_next_step_handler(msg, process_topup_stars_amount)
            return
        
        user_id = message.from_user.id
        payment_id = f"paystars_{user_id}_{int(time.time())}"

        cursor.execute("INSERT INTO payments (payment_id, user_id, amount) VALUES (?, ?, ?)", (payment_id, user_id, amount))
        conn.commit()

        markup = types.InlineKeyboardMarkup()
        btn_paid = types.InlineKeyboardButton("🎁 Я отправил подарок", callback_data=f"paidstars_{payment_id}")
        btn_back = types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile")
        markup.add(btn_paid)
        markup.add(btn_back)

        text = (
            f"⭐ **Пополнение баланса Звёздами (Telegram Gift)**\n\n"
            f"💰 Заявленная сумма: **{int(amount)} ⭐**\n\n"
            f"📌 **Инструкция по пополнению:**\n"
            f"1. Отправьте Telegram-подарок (например, Кольцо / Gift) эквивалентом **{int(amount)} ⭐** на аккаунт:\n"
            f"👉 **@{GARANT_MD}**\n\n"
            f"2. После успешной отправки подарка нажмите кнопку **«🎁 Я отправил подарок»** ниже."
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

    except ValueError:
        msg = bot.reply_to(message, "❌ **Ошибка ввода!** Введите только целое число (например: `50` или `100`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_topup_stars_amount)

def process_topup_ton_amount(message):
    if message.text and message.text.startswith('/'):
        return

    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount <= 0:
            msg = bot.reply_to(message, "❌ Сумма должна быть больше 0 TON.\nВведите количество TON ещё раз:")
            bot.register_next_step_handler(msg, process_topup_ton_amount)
            return

        amount = round(amount, 4)
        user_id = message.from_user.id
        payment_id = f"payton_{user_id}_{int(time.time())}"

        cursor.execute("INSERT INTO payments (payment_id, user_id, amount) VALUES (?, ?, ?)", (payment_id, user_id, amount))
        conn.commit()

        markup = types.InlineKeyboardMarkup()
        btn_paid = types.InlineKeyboardButton("✅ Я оплатил", callback_data=f"paidton_{payment_id}")
        btn_back = types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile")
        markup.add(btn_paid)
        markup.add(btn_back)

        text = (
            f"💎 **Пополнение баланса через TON**\n\n"
            f"💰 Сумма к оплате: **{amount:g} TON**\n\n"
            f"📌 **Инструкция:**\n"
            f"1. Переведите ровно **{amount:g} TON** на кошелёк:\n"
            f"`{TON_WALLET}`\n\n"
            f"2. В поле **Комментарий (Memo)** обязательно укажите:\n"
            f"`{payment_id}`\n\n"
            f"3. После перевода нажмите кнопку **«✅ Я оплатил»** ниже.\n\n"
            f"⚠️ Без комментария платёж могут не засчитать."
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

    except (ValueError, AttributeError):
        msg = bot.reply_to(message, "❌ **Ошибка ввода!** Введите число (например: `1` или `2.5`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_topup_ton_amount)

def process_banner_upload(message, menu_key):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text and message.text.startswith('/'):
        bot.reply_to(message, "❌ Загрузка баннера отменена.")
        return
    if message.content_type != "photo" or not message.photo:
        msg = bot.reply_to(message, "❌ Нужно отправить именно фото. Попробуйте ещё раз или /cancel:")
        bot.register_next_step_handler(msg, process_banner_upload, menu_key)
        return

    file_id = message.photo[-1].file_id
    cursor.execute("INSERT OR REPLACE INTO banners (menu_key, file_id) VALUES (?, ?)", (menu_key, file_id))
    conn.commit()

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🖼 К баннерам", callback_data="admin_banners"))
    bot.reply_to(message, f"✅ Баннер для «{BANNER_MENUS.get(menu_key, menu_key)}» сохранён!", reply_markup=markup)

def process_topup_rub_amount(message):
    if message.text and message.text.startswith('/'):
        return

    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount <= 0:
            msg = bot.reply_to(message, "❌ Сумма должна быть больше 0 ₽.\nВведите сумму ещё раз:")
            bot.register_next_step_handler(msg, process_topup_rub_amount)
            return

        amount = round(amount, 2)
        user_id = message.from_user.id
        payment_id = f"payrub_{user_id}_{int(time.time())}"

        cursor.execute("INSERT INTO payments (payment_id, user_id, amount) VALUES (?, ?, ?)", (payment_id, user_id, amount))
        conn.commit()

        markup = types.InlineKeyboardMarkup()
        btn_manager = types.InlineKeyboardButton("💬 Написать менеджеру", url=f"https://t.me/{MANAGER_USERNAME}")
        btn_paid = types.InlineKeyboardButton("✅ Я оплатил", callback_data=f"paidrub_{payment_id}")
        btn_back = types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile")
        markup.add(btn_manager)
        markup.add(btn_paid)
        markup.add(btn_back)

        text = (
            f"🇷🇺 **Пополнение баланса рублями**\n\n"
            f"💰 Сумма к оплате: **{amount:g} ₽**\n\n"
            f"📌 **Инструкция:**\n"
            f"1. Напишите менеджеру @{MANAGER_USERNAME} — он пришлёт номер карты для перевода.\n"
            f"2. Переведите ровно **{amount:g} ₽** и укажите менеджеру ID заявки:\n"
            f"`{payment_id}`\n\n"
            f"3. После перевода нажмите кнопку **«✅ Я оплатил»** ниже.\n\n"
            f"⚠️ Без ID заявки платёж могут не засчитать."
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

    except (ValueError, AttributeError):
        msg = bot.reply_to(message, "❌ **Ошибка ввода!** Введите число (например: `500`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_topup_rub_amount)

def process_contest_prizes(message):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text and message.text.startswith('/'):
        bot.reply_to(message, "❌ Изменение призов отменено.")
        return
    lines = [l.strip() for l in message.text.split("\n") if l.strip()]
    if len(lines) < 3:
        msg = bot.reply_to(message, "❌ Нужно 3 строки (1, 2 и 3 место). Отправьте ещё раз или /cancel:")
        bot.register_next_step_handler(msg, process_contest_prizes)
        return
    cursor.execute("UPDATE competition SET prize1=?, prize2=?, prize3=? WHERE id=1", (lines[0], lines[1], lines[2]))
    conn.commit()
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🏆 К конкурсу", callback_data="admin_contest"))
    bot.reply_to(message, f"✅ Призы обновлены:\n🥇 {lines[0]}\n🥈 {lines[1]}\n🥉 {lines[2]}", reply_markup=markup)

def process_search_user(message):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text and message.text.startswith('/'):
        bot.reply_to(message, "❌ Поиск отменён.")
        return
    if not message.text or not message.text.strip().isdigit():
        msg = bot.reply_to(message, "❌ ID должен быть числом. Отправьте ещё раз или /cancel:")
        bot.register_next_step_handler(msg, process_search_user)
        return

    uid = int(message.text.strip())
    cursor.execute("SELECT balance, currency, referred_by, last_bonus FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    if not row:
        bot.reply_to(message, f"❌ Пользователь с ID `{uid}` не найден в базе.", parse_mode="Markdown")
        return

    balance, currency, referred_by, last_bonus = row
    sym = CURRENCY_SYMBOLS.get(currency, "")
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (uid,))
    orders_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='completed'", (uid,))
    completed_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (uid,))
    ref_count = cursor.fetchone()[0]

    name = get_display_name(uid)
    text = (
        f"🔎 **Пользователь {name}**\n\n"
        f"🆔 ID: `{uid}`\n"
        f"💰 Баланс: **{balance:.2f} {sym}**\n"
        f"📦 Заказов всего / выполнено: **{orders_count} / {completed_count}**\n"
        f"👥 Приглашено рефералов: **{ref_count}**\n"
        f"🔗 Пригласил его: {referred_by if referred_by else '—'}"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔎 Искать ещё", callback_data="admin_search_user"))
    bot.reply_to(message, text, parse_mode="Markdown", reply_markup=markup)

def process_review_text(message, order_id, rating):
    text = message.text if message.text else "Без текстового отзыва"
    user_id = message.from_user.id
    save_review(order_id, user_id, rating, text, message.from_user.first_name, message.from_user.username)
    bot.reply_to(message, "🎉 **Спасибо за ваш отзыв!** Мы ценим ваше мнение.", parse_mode="Markdown")

def process_broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    success, failed = 0, 0
    bot.send_message(message.chat.id, f"🚀 Рассылка запущена на {len(users)} пользователей...")

    for u in users:
        uid = u[0]
        try:
            bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
        except Exception:
            failed += 1

    bot.send_message(
        message.chat.id, 
        f"✅ **Рассылка завершена!**\n\n"
        f"🟢 Успешно отправлено: **{success}**\n"
        f"🔴 Не доставлено (заблокировали): **{failed}**", 
        parse_mode="Markdown"
    )

def process_add_item(message):
    """Добавление товаров. Можно несколько за раз — каждый товар с новой строки.
    Формат строки: Название, Цена_грн   или   Название, Категория, Цена_грн
    Цены в звёздах и рублях считаются автоматически по курсу
    (можно вручную задать 4-м и 5-м значением)."""
    if not message.text:
        bot.reply_to(message, "❌ Отправьте текстом.")
        return

    added, errors = [], []
    for line in message.text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                raise ValueError("нет цены")

            name = parts[0]
            if len(parts) == 2:
                category = "🔥 Разное"
                p_uah = float(parts[1].replace(" ", ""))
                extra = []
            else:
                category = parts[1] or "🔥 Разное"
                p_uah = float(parts[2].replace(" ", ""))
                extra = parts[3:]

            # автоконвертация по курсу: 1 ⭐ = 0,83 грн = 1,65 ₽
            p_stars = float(extra[0]) if len(extra) > 0 else convert_currency(p_uah, "UAH", "STARS")
            p_rub = float(extra[1]) if len(extra) > 1 else convert_currency(p_uah, "UAH", "RUB")

            cursor.execute(
                "INSERT INTO catalog_items (name, category, price_uah, price_stars, price_rub) VALUES (?, ?, ?, ?, ?)",
                (name, category, p_uah, p_stars, p_rub)
            )
            conn.commit()
            added.append(f"• **{name}** ({category}) — {p_uah:g} грн | {p_stars:g} ⭐ | {p_rub:g} ₽")
        except Exception as e:
            print(f"Ошибка добавления товара '{line}': {e}")
            errors.append(f"• `{line}`")

    text = ""
    if added:
        text += f"✅ **Добавлено товаров: {len(added)}**\n\n" + "\n".join(added)
    if errors:
        text += ("\n\n" if text else "") + "❌ **Не удалось добавить (проверьте формат):**\n" + "\n".join(errors)
    bot.reply_to(message, text or "❌ Пустое сообщение.", parse_mode="Markdown")

def process_promo_activation(message):
    user_id = message.from_user.id
    code = message.text.strip()

    cursor.execute("SELECT reward, uses_left FROM promocodes WHERE code=?", (code,))
    promo = cursor.fetchone()

    if not promo:
        bot.reply_to(message, "❌ Такой промокод не существует!")
        return

    reward, uses_left = promo

    if uses_left <= 0:
        bot.reply_to(message, "❌ Этот промокод уже закончился!")
        return

    cursor.execute("SELECT * FROM used_promos WHERE user_id=? AND code=?", (user_id, code))
    if cursor.fetchone():
        bot.reply_to(message, "❌ Вы уже активировали этот промокод!")
        return

    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (reward, user_id))
    cursor.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE code=?", (code,))
    cursor.execute("INSERT INTO used_promos (user_id, code) VALUES (?, ?)", (user_id, code))
    conn.commit()

    bot.reply_to(message, f"🎉 **Промокод активирован!** Вам зачислено **{reward:.2f}** на баланс.", parse_mode="Markdown")

# ==================== ЗАПУСК БОТА И СЕРВЕРА ====================
if __name__ == '__main__':
    keep_alive()
    print("🤖 Бот запущен и готов к работе!")
    bot.infinity_polling(timeout=60, long_polling_timeout=30) 
