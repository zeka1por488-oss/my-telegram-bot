import os
import sqlite3
import telebot
from telebot import types
import time
import random
import threading
import requests
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

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8657141354:AAH_SIZmAGwshiFvbDff_9J8_kNtSvwZ5u4")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7408654429"))
MANAGER_USERNAME = "Nazarow927"
GARANT_USERNAME = "garant_nazarow"
REQUIRED_CHANNEL = "@nazarowshop"

CARD_NUMBER = os.environ.get("CARD_NUMBER", "4400005572759295")
CARD_HOLDER = "А-Банк"
REVIEWS_CHANNEL_ID = "-1004291767300"

XROCKET_API_KEY = os.environ.get("XROCKET_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBJZCI6IjMwMzAwOCIsImp0aSI6ImFwcDozMDMwMDg6NTAyNDFhYWMtY2UxNy00ZDZmLWEwYTMtY2VmM2M3NTc5OWFiIiwiaWF0IjoxNzkwNTk3MDE1fQ.QTDHlScHEBze_LHqE025qq0u7hO9p3NqJrjdtHmKHAg")
XROCKET_API_URL = "https://pay.mypays.co"

MENU_NAMES = {
    "main_menu": "🏠 Главное меню",
    "catalog": "🛒 Каталог товаров",
    "profile": "👤 Профиль и баланс",
    "daily_bonus": "🎁 Ежедневный бонус",
    "ref_system": "👥 Реферальная система",
    "faq_info": "📖 Инфо / Правила"
}

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

bot = telebot.TeleBot(BOT_TOKEN)

BOT_USERNAME = ""
try:
    BOT_USERNAME = bot.get_me().username
except Exception as e:
    print(f"Ошибка получения инфо о боте: {e}")

# ==================== БАЗА ДАННЫХ С БЛОКИРОВКОЙ ПОТОКОВ ====================
db_lock = threading.Lock()
conn = sqlite3.connect("store.db", check_same_thread=False)

def execute_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    """Безопасный запуск запросов к БД в многопоточной среде"""
    with db_lock:
        cursor = conn.cursor()
        cursor.execute(query, params)
        res = None
        if fetchone:
            res = cursor.fetchone()
        elif fetchall:
            res = cursor.fetchall()
        if commit:
            conn.commit()
        return res

# Инициализация таблиц
execute_query("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0.0,
        currency TEXT DEFAULT 'UAH',
        referred_by INTEGER DEFAULT NULL,
        last_bonus INTEGER DEFAULT 0
    )
""", commit=True)

execute_query("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        item_name TEXT,
        price REAL,
        currency TEXT,
        status TEXT DEFAULT 'pending'
    )
""", commit=True)

execute_query("""
    CREATE TABLE IF NOT EXISTS catalog_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        category TEXT DEFAULT '🔥 Разное',
        price_uah REAL DEFAULT 0.0,
        price_stars REAL DEFAULT 0.0,
        price_rub REAL DEFAULT 0.0
    )
""", commit=True)

execute_query("""
    CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY,
        reward REAL,
        uses_left INTEGER
    )
""", commit=True)

execute_query("""
    CREATE TABLE IF NOT EXISTS used_promos (
        user_id INTEGER,
        code TEXT,
        PRIMARY KEY (user_id, code)
    )
""", commit=True)

execute_query("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        user_id INTEGER,
        rating INTEGER,
        review_text TEXT
    )
""", commit=True)

execute_query("""
    CREATE TABLE IF NOT EXISTS payments (
        payment_id TEXT PRIMARY KEY,
        user_id INTEGER,
        amount REAL,
        status TEXT DEFAULT 'pending'
    )
""", commit=True)

execute_query("""
    CREATE TABLE IF NOT EXISTS menu_photos (
        menu_key TEXT PRIMARY KEY,
        file_id TEXT
    )
""", commit=True)

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

def get_menu_photo(menu_key):
    """Получение file_id фото для конкретного меню"""
    res = execute_query("SELECT file_id FROM menu_photos WHERE menu_key=?", (menu_key,), fetchone=True)
    return res[0] if res and res[0] else None

def send_or_edit_menu(chat_id, message_id, text, reply_markup=None, menu_key=None, parse_mode="Markdown"):
    """
    Универсальная отправка меню: если есть фото — отправляет фото с описанием,
    удаляя старое сообщение для предотвращения Telegram API ошибок формата.
    """
    photo_id = get_menu_photo(menu_key) if menu_key else None
    
    if message_id:
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    if photo_id:
        try:
            return bot.send_photo(chat_id, photo_id, caption=text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception as e:
            print(f"Ошибка отправки фото для {menu_key}: {e}")
            return bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
    else:
        return bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)

def create_xrocket_invoice(amount_crypto, currency="TON", description="Пополнение баланса в боте"):
    headers = {
        "Rocket-Pay-Key": XROCKET_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "amount": amount_crypto,
        "currency": currency,
        "description": description,
        "numPayments": 1
    }
    try:
        response = requests.post(f"{XROCKET_API_URL}/invoice/create", json=payload, headers=headers)
        res_data = response.json()
        if res_data.get("success"):
            return res_data["data"]
    except Exception as e:
        print(f"Ошибка создания инвойса xRocket: {e}")
    return None

def check_xrocket_invoice(invoice_id):
    headers = {"Rocket-Pay-Key": XROCKET_API_KEY}
    try:
        response = requests.get(f"{XROCKET_API_URL}/invoice/{invoice_id}", headers=headers)
        res_data = response.json()
        if res_data.get("success"):
            return res_data["data"]["status"] == "PAID"
    except Exception as e:
        print(f"Ошибка проверки инвойса xRocket: {e}")
    return False

def convert_currency(amount, from_curr, to_curr):
    amount_in_stars = amount
    if from_curr == "UAH":
        amount_in_stars = amount / 0.75
    elif from_curr == "RUB":
        amount_in_stars = amount / 2.0
        
    if to_curr == "STARS":
        return round(amount_in_stars, 1)
    elif to_curr == "UAH":
        return round(amount_in_stars * 0.75, 2)
    elif to_curr == "RUB":
        return round(amount_in_stars * 2.0, 2)
    
    return amount

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

def get_admin_keyboard():
    markup = types.InlineKeyboardMarkup()
    b1 = types.InlineKeyboardButton("🖼 Настройка фото меню", callback_data="admin_photos")
    b2 = types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")
    b3 = types.InlineKeyboardButton("➕ Добавить товар", callback_data="admin_add_item")
    b4 = types.InlineKeyboardButton("🗑 Удалить товар", callback_data="admin_del_item")
    b5 = types.InlineKeyboardButton("📢 Массовая рассылка", callback_data="admin_broadcast")
    b6 = types.InlineKeyboardButton("💰 Выдать баланс", callback_data="admin_give_info")
    b7 = types.InlineKeyboardButton("🎁 Промокоды", callback_data="admin_promo_info")
    markup.add(b1)
    markup.add(b2, b3)
    markup.add(b4, b5)
    markup.add(b6, b7)
    return markup

def save_review(order_id, user_id, rating, text, first_name, username):
    execute_query("INSERT INTO reviews (order_id, user_id, rating, review_text) VALUES (?, ?, ?, ?)",
                  (order_id, user_id, rating, text), commit=True)

    if rating == 5:
        u_curr_row = execute_query("SELECT currency FROM users WHERE user_id=?", (user_id,), fetchone=True)
        u_curr = u_curr_row[0] if u_curr_row else "UAH"
        
        bonus_val = 10.0 if u_curr == "UAH" else (15.0 if u_curr == "STARS" else 25.0)
        sym = CURRENCY_SYMBOLS.get(u_curr, "грн")

        execute_query("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus_val, user_id), commit=True)

        try:
            bot.send_message(
                user_id, 
                f"🎉 **Спасибо за отзыв 5★!**\n💰 Вам автоматически зачислено **+{bonus_val} {sym}** на баланс!", 
                parse_mode="Markdown"
            )
        except Exception:
            pass

    res = execute_query("SELECT item_name FROM orders WHERE order_id=?", (order_id,), fetchone=True)
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

    existing_user = execute_query("SELECT user_id FROM users WHERE user_id=?", (user_id,), fetchone=True)
    
    referred_by = None
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id:
            referred_by = ref_id

    if not existing_user:
        execute_query("INSERT INTO users (user_id, referred_by) VALUES (?, ?)", (user_id, referred_by), commit=True)

        if referred_by:
            ref_row = execute_query("SELECT currency FROM users WHERE user_id=?", (referred_by,), fetchone=True)
            if ref_row:
                ref_curr = ref_row[0]
                rew_val, rew_sym = REF_REWARDS.get(ref_curr, (3.0, "грн"))
                
                execute_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (rew_val, referred_by), commit=True)
                
                try:
                    bot.send_message(
                        referred_by,
                        f"🎉 **Новый реферал!** По вашей ссылке присоединился {message.from_user.first_name}.\n"
                        f"💰 Вам начислено **+{rew_val} {rew_sym}** на баланс!",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Ошибка отправки рефереру: {e}")

    text = get_main_menu_text(message.from_user.first_name)
    markup = get_main_menu_keyboard()
    send_or_edit_menu(message.chat.id, None, text, reply_markup=markup, menu_key="main_menu")

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, f"❌ Отказано в доступе. Ваш ID: `{message.from_user.id}`", parse_mode="Markdown")
        return
    
    markup = get_admin_keyboard()
    text = "🛠 **Панель Администратора**\n\nУправляйте магазином с помощью кнопок ниже:"
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    if message.from_user.id != ADMIN_ID: return
    bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
    msg = bot.send_message(message.chat.id, "📢 **Массовая рассылка**\n\nОтправьте сообщение для рассылки (или /cancel):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_broadcast)

@bot.message_handler(commands=['add_promo'])
def add_promo_command(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, code, reward, uses = message.text.split()
        execute_query("INSERT OR REPLACE INTO promocodes (code, reward, uses_left) VALUES (?, ?, ?)", 
                      (code, float(reward), int(uses)), commit=True)
        bot.reply_to(message, f"✅ Промокод `{code}` на **{reward}** ({uses} активаций) создан!", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "Формат: `/add_promo КОД СУММА КОЛ_ВО`\nПример: `/add_promo START100 100 5`", parse_mode="Markdown")

@bot.message_handler(commands=['give_balance'])
def give_balance(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        _, target_id, amount = message.text.split()
        execute_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (float(amount), int(target_id)), commit=True)
        bot.reply_to(message, f"💰 Выдано **{amount}** пользователю `{target_id}`.", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "Формат: `/give_balance ID СУММА`", parse_mode="Markdown")

# ==================== CALLBACK HANDLER ====================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    
    if call.data == "check_subscription":
        if check_subscription(user_id):
            bot.answer_callback_query(call.id, "✅ Подписка подтверждена!", show_alert=False)
            text = get_main_menu_text(call.from_user.first_name)
            markup = get_main_menu_keyboard()
            send_or_edit_menu(call.message.chat.id, call.message.message_id, text, reply_markup=markup, menu_key="main_menu")
        else:
            bot.answer_callback_query(call.id, "❌ Вы всё ещё не подписаны на канал!", show_alert=True)
        return

    if not check_subscription(user_id):
        bot.answer_callback_query(call.id, "⚠️ Доступ ограничен! Подпишитесь на канал.", show_alert=True)
        text = f"⚠️ **Для продолжения работы подпишитесь на наш канал:**\n👉 {REQUIRED_CHANNEL}"
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=get_sub_keyboard())
        return

    u_row = execute_query("SELECT balance, currency, last_bonus FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if not u_row:
        execute_query("INSERT INTO users (user_id) VALUES (?)", (user_id,), commit=True)
        balance, curr, last_bonus = 0.0, "UAH", 0
    else:
        balance, curr, last_bonus = u_row[0], u_row[1], u_row[2]

    sym = CURRENCY_SYMBOLS.get(curr, "грн")

    # --- АДМИН-ПАНЕЛЬ: НАСТРОЙКА ФОТО ---
    if call.data == "admin_photos":
        if user_id != ADMIN_ID: return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, name in MENU_NAMES.items():
            has_photo = "✅ (с фото)" if get_menu_photo(key) else "❌ (без фото)"
            markup.add(types.InlineKeyboardButton(f"{name} {has_photo}", callback_data=f"setphoto_{key}"))
        
        markup.add(types.InlineKeyboardButton("🗑 Удалить фото у раздела", callback_data="delphoto_menu"))
        markup.add(types.InlineKeyboardButton("⬅️ В админ меню", callback_data="admin_main"))
        
        bot.send_message(
            call.message.chat.id, 
            "🖼 **Управление фото для меню:**\n\nВыберите раздел, для которого хотите установить или изменить изображение:", 
            parse_mode="Markdown", 
            reply_markup=markup
        )

    elif call.data.startswith("setphoto_"):
        if user_id != ADMIN_ID: return
        key = call.data.split("_", 1)[1]
        menu_display = MENU_NAMES.get(key, key)
        
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id, 
            f"📸 **Установка фото для:** {menu_display}\n\n"
            f"Отправьте изображение (картинку) сообщением.\nДля отмены напишите `/cancel`.", 
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_save_photo_step, key)

    elif call.data == "delphoto_menu":
        if user_id != ADMIN_ID: return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, name in MENU_NAMES.items():
            if get_menu_photo(key):
                markup.add(types.InlineKeyboardButton(f"❌ Удалить: {name}", callback_data=f"actdelphoto_{key}"))
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_photos"))
        
        bot.send_message(call.message.chat.id, "🗑 Выберите раздел, фото которого нужно удалить:", reply_markup=markup)

    elif call.data.startswith("actdelphoto_"):
        if user_id != ADMIN_ID: return
        key = call.data.split("_", 1)[1]
        execute_query("DELETE FROM menu_photos WHERE menu_key=?", (key,), commit=True)
        bot.send_message(call.message.chat.id, f"✅ Фото для раздела **{MENU_NAMES.get(key, key)}** удалено!", parse_mode="Markdown")

    elif call.data == "admin_main":
        if user_id != ADMIN_ID: return
        markup = get_admin_keyboard()
        text = "🛠 **Панель Администратора**\n\nУправляйте магазином с помощью кнопок ниже:"
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "admin_add_item":
        if user_id != ADMIN_ID: return
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id, 
            "➕ **Добавление товара / номера**\n\n"
            "Отправьте данные через запятую:\n"
            "`Название, Категория, Цена_UAH, Цена_STARS, Цена_RUB`\n\n"
            "*Пример 1:*\n`+380991234567, 📲 Номера, 150, 200, 350`\n\n"
            "*Пример 2 (простой):*\n`TG Премиум, 💎 Премиум, 120`", 
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_add_item)

    elif call.data == "daily_bonus":
        now = int(time.time())
        cooldown = 86400
        
        if now - last_bonus >= cooldown:
            bonus_amount = round(random.uniform(1.0, 5.0), 2)
            if curr == "STARS":
                bonus_amount = round(bonus_amount * 1.5, 1)
            elif curr == "RUB":
                bonus_amount = round(bonus_amount * 2.5, 2)

            execute_query("UPDATE users SET balance = balance + ?, last_bonus = ? WHERE user_id = ?", (bonus_amount, now, user_id), commit=True)
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu"))
            text = (
                f"🎁 **Ежедневный бонус забран!**\n\n"
                f"💰 На ваш баланс зачислено: **+{bonus_amount} {sym}**\n\n"
                f"Возвращайтесь через 24 часа за новым бонусом!"
            )
            send_or_edit_menu(call.message.chat.id, call.message.message_id, text, reply_markup=markup, menu_key="daily_bonus")
        else:
            time_left = cooldown - (now - last_bonus)
            hours = time_left // 3600
            minutes = (time_left % 3600) // 60
            bot.send_message(call.message.chat.id, f"⏳ Бонус уже получен! Заходите через {hours} ч. {minutes} мин.")

    elif call.data == "catalog_cats":
        items = execute_query("SELECT id, name, price_uah, price_stars, price_rub FROM catalog_items", fetchall=True)
        
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
        send_or_edit_menu(call.message.chat.id, call.message.message_id, text, reply_markup=markup, menu_key="catalog")

    elif call.data.startswith("item_"):
        item_id = call.data.split("_")[1]
        item = execute_query("SELECT name, category, price_uah, price_stars, price_rub FROM catalog_items WHERE id=?", (item_id,), fetchone=True)
        
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
        send_or_edit_menu(call.message.chat.id, call.message.message_id, text, reply_markup=markup)

    elif call.data.startswith("req_"):
        item_id = call.data.split("_")[1]
        item = execute_query("SELECT name, price_uah, price_stars, price_rub FROM catalog_items WHERE id=?", (item_id,), fetchone=True)
        
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

        execute_query("UPDATE users SET balance = balance - ? WHERE user_id=?", (price, user_id), commit=True)
        execute_query("INSERT INTO orders (user_id, item_name, price, currency) VALUES (?, ?, ?, ?)", (user_id, name, price, curr), commit=True)
        
        res_ord = execute_query("SELECT last_insert_rowid()", fetchone=True)
        order_id = res_ord[0] if res_ord else 0

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💬 Перейти к менеджеру", url=f"https://t.me/{MANAGER_USERNAME}"))
        
        send_or_edit_menu(
            call.message.chat.id, 
            call.message.message_id,
            f"✅ **Оплата прошла успешно!**\n\n"
            f"📦 Товар / Номер: **{name}**\n"
            f"💰 Списано: **{price:.2f} {sym}**\n"
            f"🧾 Заказ #{order_id}\n\n"
            f"Напишите нашему менеджеру @{MANAGER_USERNAME} для получения товара/номера.",
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
            "• Автоматическое зачисление через xRocket или под подтверждение админом.\n"
            "• В случае вопросов по оплате пишите менеджеру: @" + MANAGER_USERNAME
        )
        send_or_edit_menu(call.message.chat.id, call.message.message_id, text, reply_markup=markup, menu_key="faq_info")

    elif call.data.startswith("done_"):
        _, order_id, client_id = call.data.split("_")
        execute_query("UPDATE orders SET status='completed' WHERE order_id=?", (order_id,), commit=True)

        bot.send_message(call.message.chat.id, f"✅ **Заказ #{order_id} выполнен!**", parse_mode="Markdown")
        
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
        msg = bot.send_message(
            call.message.chat.id,
            f"⭐️ Вы поставили оценку **{rating}/5 ⭐**.\n\n"
            f"✍️ **Напишите краткий отзыв о покупке** (или нажмите кнопку «Пропустить»):",
            parse_mode="Markdown",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_review_text, order_id, rating)

    elif call.data.startswith("skip_rev_"):
        _, _, order_id, rating = call.data.split("_")
        rating = int(rating)
        save_review(order_id, user_id, rating, "Без текстового отзыва", call.from_user.first_name, call.from_user.username)
        bot.send_message(call.message.chat.id, "🙏 **Спасибо за вашу оценку!** Нам очень важно ваше мнение.", parse_mode="Markdown")

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
        send_or_edit_menu(call.message.chat.id, call.message.message_id, text, reply_markup=markup, menu_key="profile")

    elif call.data == "top_up_balance":
        markup = types.InlineKeyboardMarkup()
        b_uah = types.InlineKeyboardButton("💳 UAH (Карта)", callback_data="topup_method_uah")
        b_stars = types.InlineKeyboardButton("⭐ STARS (Telegram Подарок)", callback_data="topup_method_stars")
        b_xrocket = types.InlineKeyboardButton("🚀 xRocket (TON / Crypto)", callback_data="topup_method_xrocket")
        b_back = types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile")
        
        markup.add(b_uah, b_stars)
        markup.add(b_xrocket)
        markup.add(b_back)

        send_or_edit_menu(call.message.chat.id, call.message.message_id, "💳 **Выберите способ пополнения баланса:**", reply_markup=markup)

    elif call.data == "topup_method_uah":
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id, 
            "💳 **Пополнение баланса картой (UAH / грн)**\n\n"
            "Введите сумму пополнения в **грн** (или напишите `/cancel`):", 
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_topup_amount)

    elif call.data == "topup_method_stars":
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id, 
            "⭐ **Пополнение баланса Звёздами (Telegram Gifts)**\n\n"
            "Введите количество звёзд, на которое хотите пополнить (или напишите `/cancel`):", 
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_topup_stars_amount)

    elif call.data == "topup_method_xrocket":
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id, 
            "🚀 **Пополнение через xRocket (TON)**\n\n"
            "Введите сумму в **TON**, на которую хотите пополнить (или напишите `/cancel`):", 
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_topup_xrocket)

    elif call.data.startswith("check_xr_"):
        parts = call.data.split("_")
        invoice_id = parts[2]
        payment_db_id = parts[3]

        p_row = execute_query("SELECT amount, status FROM payments WHERE payment_id=?", (payment_db_id,), fetchone=True)

        if not p_row:
            bot.send_message(call.message.chat.id, "❌ Заявка не найдена!")
            return

        p_amount, p_status = p_row

        if p_status == "completed":
            bot.answer_callback_query(call.id, "✅ Эта оплата уже зачислена!", show_alert=True)
            return

        if check_xrocket_invoice(invoice_id):
            u_curr_res = execute_query("SELECT currency FROM users WHERE user_id=?", (user_id,), fetchone=True)
            u_curr = u_curr_res[0] if u_curr_res else "UAH"

            final_amount = convert_currency(p_amount, "STARS", u_curr)

            execute_query("UPDATE payments SET status='completed' WHERE payment_id=?", (payment_db_id,), commit=True)
            execute_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (final_amount, user_id), commit=True)

            sym = CURRENCY_SYMBOLS.get(u_curr, "")
            bot.send_message(
                call.message.chat.id,
                f"🎉 **Оплата успешно подтверждена!**\n\n"
                f"💰 На ваш баланс зачислено: **+{final_amount:.2f} {sym}**",
                parse_mode="Markdown"
            )
        else:
            bot.answer_callback_query(call.id, "❌ Оплата еще не поступила! Сначала оплатите чек в xRocket.", show_alert=True)

    elif call.data.startswith("paid_"):
        payment_id = call.data.split("_", 1)[1]
        p_row = execute_query("SELECT amount, status FROM payments WHERE payment_id=?", (payment_id,), fetchone=True)
        
        if not p_row:
            bot.send_message(call.message.chat.id, "❌ Счет не найден!")
            return

        p_amount, p_status = p_row

        if p_status == "completed":
            bot.send_message(call.message.chat.id, "✅ Этот платеж уже подтвержден!")
            return

        send_or_edit_menu(
            call.message.chat.id,
            call.message.message_id,
            f"⏳ **Заявка отправлена администратору!**\n\n"
            f"💰 Сумма: **{p_amount:.2f} грн**\n"
            f"🆔 ID платежа: `{payment_id}`\n\n"
            "После проверки администратор зачислит средства."
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
        p_row = execute_query("SELECT amount, status FROM payments WHERE payment_id=?", (payment_id,), fetchone=True)

        if not p_row:
            bot.send_message(call.message.chat.id, "❌ Заявка не найдена!")
            return

        p_amount, p_status = p_row

        if p_status == "completed":
            bot.send_message(call.message.chat.id, "✅ Эти звёзды уже были зачислены!")
            return

        send_or_edit_menu(
            call.message.chat.id,
            call.message.message_id,
            f"⏳ **Заявка на проверку подарка отправлена!**\n\n"
            f"⭐ Заявлено: **{int(p_amount)} ⭐**\n"
            f"🆔 ID заявки: `{payment_id}`\n\n"
            f"Администратор проверит получение подарка на **@{GARANT_USERNAME}** и зачислит баланс."
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
            f"📌 **Проверьте получение подарка на @{GARANT_USERNAME}** и нажмите кнопку ниже:"
        )
        try:
            bot.send_message(ADMIN_ID, adm_text, parse_mode="Markdown", reply_markup=adm_markup)
        except Exception as e:
            print(f"Ошибка отправки админу: {e}")

    elif call.data.startswith("admconfirm_"):
        if user_id != ADMIN_ID: return
        payment_id = call.data.split("_", 1)[1]

        p_row = execute_query("SELECT user_id, amount, status FROM payments WHERE payment_id=?", (payment_id,), fetchone=True)
        if not p_row: return

        p_uid, p_amount, p_status = p_row
        if p_status == "completed":
            bot.answer_callback_query(call.id, "⚠️ Платеж уже обработан!", show_alert=True)
            return

        u_curr_row = execute_query("SELECT currency FROM users WHERE user_id=?", (p_uid,), fetchone=True)
        u_curr = u_curr_row[0] if u_curr_row else "UAH"

        final_amount = convert_currency(p_amount, "UAH", u_curr)

        execute_query("UPDATE payments SET status='completed' WHERE payment_id=?", (payment_id,), commit=True)
        execute_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (final_amount, p_uid), commit=True)

        sym = CURRENCY_SYMBOLS.get(u_curr, "")
        bot.send_message(call.message.chat.id, f"✅ **Оплата #{payment_id} подтверждена!** Зачислено +{final_amount:.2f} {sym}.", parse_mode="Markdown")
        try:
            bot.send_message(p_uid, f"🎉 **Баланс успешно пополнен!**\n💰 Вам зачислено **+{final_amount:.2f} {sym}**.", parse_mode="Markdown")
        except Exception: pass

    elif call.data.startswith("admconfirmstars_"):
        if user_id != ADMIN_ID: return
        payment_id = call.data.split("_", 1)[1]

        p_row = execute_query("SELECT user_id, amount, status FROM payments WHERE payment_id=?", (payment_id,), fetchone=True)
        if not p_row: return

        p_uid, p_amount, p_status = p_row
        if p_status == "completed":
            bot.answer_callback_query(call.id, "⚠️ Эта заявка уже обработана!", show_alert=True)
            return

        u_curr_row = execute_query("SELECT currency FROM users WHERE user_id=?", (p_uid,), fetchone=True)
        u_curr = u_curr_row[0] if u_curr_row else "STARS"

        final_amount = convert_currency(p_amount, "STARS", u_curr)

        execute_query("UPDATE payments SET status='completed' WHERE payment_id=?", (payment_id,), commit=True)
        execute_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (final_amount, p_uid), commit=True)

        sym = CURRENCY_SYMBOLS.get(u_curr, "")
        bot.send_message(call.message.chat.id, f"✅ **Подарок подтверждён!** Пользователю `{p_uid}` зачислено **+{final_amount:.2f} {sym}**.", parse_mode="Markdown")
        try:
            bot.send_message(p_uid, f"🎉 **Подарок проверен и подтверждён!**\n\n⭐ На ваш баланс зачислено: **+{final_amount:.2f} {sym}**", parse_mode="Markdown")
        except Exception: pass

    elif call.data.startswith("admreject_"):
        if user_id != ADMIN_ID: return
        payment_id = call.data.split("_", 1)[1]

        p_row = execute_query("SELECT user_id, amount FROM payments WHERE payment_id=?", (payment_id,), fetchone=True)
        if not p_row: return
        p_uid, p_amount = p_row

        execute_query("UPDATE payments SET status='rejected' WHERE payment_id=?", (payment_id,), commit=True)

        bot.send_message(call.message.chat.id, f"❌ **Заявка #{payment_id} отклонена.**", parse_mode="Markdown")
        try:
            bot.send_message(p_uid, f"❌ **Заявка на пополнение была отклонена.** Средства/подарок не поступили.", parse_mode="Markdown")
        except Exception: pass

    elif call.data == "change_currency":
        markup = types.InlineKeyboardMarkup()
        b1 = types.InlineKeyboardButton("🇺🇦 UAH (грн)", callback_data="set_curr_UAH")
        b2 = types.InlineKeyboardButton("⭐ Stars (звёзды)", callback_data="set_curr_STARS")
        b3 = types.InlineKeyboardButton("🇷🇺 RUB (₽)", callback_data="set_curr_RUB")
        b_back = types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile")
        markup.add(b1, b2, b3)
        markup.add(b_back)
        send_or_edit_menu(call.message.chat.id, call.message.message_id, "🌐 **Выберите удобную валюту:**", reply_markup=markup)

    elif call.data.startswith("set_curr_"):
        new_curr = call.data.split("_")[2]
        
        c_bal_row = execute_query("SELECT balance FROM users WHERE user_id=?", (user_id,), fetchone=True)
        current_bal = c_bal_row[0] if c_bal_row else 0.0
        
        if current_bal > 0:
            bot.answer_callback_query(call.id, "❌ Сменить валюту можно только при нулевом балансе!", show_alert=True)
            return

        execute_query("UPDATE users SET currency=? WHERE user_id=?", (new_curr, user_id), commit=True)
        new_sym = CURRENCY_SYMBOLS.get(new_curr, "грн")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 Пополнить баланс", callback_data="top_up_balance"))
        markup.add(types.InlineKeyboardButton("👥 Реферальная система", callback_data="ref_system"))
        markup.add(types.InlineKeyboardButton(f"🌐 Валюта: {new_curr}", callback_data="change_currency"), types.InlineKeyboardButton("📜 Мои заказы", callback_data="my_orders"))
        markup.add(types.InlineKeyboardButton("🎁 Активировать промокод", callback_data="use_promo"))
        markup.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu"))
        
        text = f"👤 **Профиль**\n\n🆔 Ваш ID: `{user_id}`\n💰 Баланс: **0.00 {new_sym}**\n🌐 Выбранная валюта: **{new_curr}**"
        send_or_edit_menu(call.message.chat.id, call.message.message_id, text, reply_markup=markup, menu_key="profile")

    elif call.data == "ref_system":
        res_ref = execute_query("SELECT COUNT(*) FROM users WHERE referred_by=?", (user_id,), fetchone=True)
        ref_count = res_ref[0] if res_ref else 0
        
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
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile"))
        send_or_edit_menu(call.message.chat.id, call.message.message_id, text, reply_markup=markup, menu_key="ref_system")

    elif call.data == "my_orders":
        orders = execute_query("SELECT order_id, item_name, price, currency, status FROM orders WHERE user_id=? ORDER BY order_id DESC LIMIT 10", (user_id,), fetchall=True)
        
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

        send_or_edit_menu(call.message.chat.id, call.message.message_id, text, reply_markup=markup)

    elif call.data == "use_promo":
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(call.message.chat.id, "🎁 **Введите промокод:** (или напишите `/cancel`)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_promo_activation)

    elif call.data == "main_menu":
        text = get_main_menu_text(call.from_user.first_name)
        markup = get_main_menu_keyboard()
        send_or_edit_menu(call.message.chat.id, call.message.message_id, text, reply_markup=markup, menu_key="main_menu")

    elif call.data == "admin_del_item":
        if user_id != ADMIN_ID: return
        items = execute_query("SELECT id, name, price_uah FROM catalog_items", fetchall=True)
        
        markup = types.InlineKeyboardMarkup()
        if not items:
            bot.send_message(call.message.chat.id, "❌ В каталоге нет товаров для удаления.")
            return

        for item_id, name, price_uah in items:
            markup.add(types.InlineKeyboardButton(f"❌ Удалить: {name} ({price_uah} грн)", callback_data=f"delitem_{item_id}"))

        bot.send_message(call.message.chat.id, "🗑 **Выберите товар для удаления:**", reply_markup=markup)

    elif call.data.startswith("delitem_"):
        if user_id != ADMIN_ID: return
        item_id = call.data.split("_")[1]
        execute_query("DELETE FROM catalog_items WHERE id=?", (item_id,), commit=True)
        bot.send_message(call.message.chat.id, "✅ Товар успешно удален из каталога!")

    elif call.data == "admin_broadcast":
        if user_id != ADMIN_ID: return
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(call.message.chat.id, "📢 **Массовая рассылка**\n\nОтправьте сообщение для рассылки (или /cancel):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_broadcast)

    elif call.data == "admin_stats":
        if user_id != ADMIN_ID: return
        u_cnt = execute_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
        o_cnt = execute_query("SELECT COUNT(*) FROM orders WHERE status='completed'", fetchone=True)[0]
        i_cnt = execute_query("SELECT COUNT(*) FROM catalog_items", fetchone=True)[0]

        rev_data = execute_query("SELECT AVG(rating), COUNT(*) FROM reviews", fetchone=True)
        avg_rev = rev_data[0] if rev_data and rev_data[0] else None
        count_rev = rev_data[1] if rev_data else 0
        avg_rev_str = f"{avg_rev:.1f}" if avg_rev else "Нет оценок"

        text = (
            f"📊 **Статистика магазина:**\n\n"
            f"👥 Всего пользователей: **{u_cnt}**\n"
            f"🛒 Товаров в каталоге: **{i_cnt}**\n"
            f"📦 Выполнено заказов: **{o_cnt}**\n\n"
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

# ==================== STEP HANDLERS (ОБРАБОТКА ВВОДА) ====================
def process_save_photo_step(message, menu_key):
    """Сохранение полученного фото для выбранного меню"""
    if message.text and message.text.lower() in ['/cancel', 'отмена']:
        bot.reply_to(message, "❌ Установка фото отменена.")
        return

    if not message.photo:
        msg = bot.reply_to(message, "⚠️ Это не изображение! Пожалуйста, отправьте фото сообщением (или напишите `/cancel`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_save_photo_step, menu_key)
        return

    file_id = message.photo[-1].file_id
    execute_query("INSERT OR REPLACE INTO menu_photos (menu_key, file_id) VALUES (?, ?)", (menu_key, file_id), commit=True)
    
    menu_display = MENU_NAMES.get(menu_key, menu_key)
    bot.reply_to(
        message, 
        f"✅ Фото для раздела **{menu_display}** успешно установлено!", 
        parse_mode="Markdown"
    )

def process_topup_amount(message):
    if message.text and message.text.lower() in ['/cancel', 'отмена']:
        bot.reply_to(message, "❌ Пополнение отменено.")
        return

    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount < 10:
            msg = bot.reply_to(message, "❌ Минимальная сумма пополнения: **10 грн**.\nВведите сумму ещё раз (или /cancel):", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_topup_amount)
            return
        
        user_id = message.from_user.id
        payment_id = f"pay_{user_id}_{int(time.time())}"

        execute_query("INSERT INTO payments (payment_id, user_id, amount) VALUES (?, ?, ?)", (payment_id, user_id, amount), commit=True)

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
        msg = bot.reply_to(message, "❌ **Ошибка ввода!** Введите число (например: `100` или `250.50`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_topup_amount)

def process_topup_stars_amount(message):
    if message.text and message.text.lower() in ['/cancel', 'отмена']:
        bot.reply_to(message, "❌ Пополнение отменено.")
        return

    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount <= 0:
            msg = bot.reply_to(message, "❌ Сумма должна быть больше 0 ⭐.\nВведите количество звёзд ещё раз (или /cancel):")
            bot.register_next_step_handler(msg, process_topup_stars_amount)
            return
        
        user_id = message.from_user.id
        payment_id = f"paystars_{user_id}_{int(time.time())}"

        execute_query("INSERT INTO payments (payment_id, user_id, amount) VALUES (?, ?, ?)", (payment_id, user_id, amount), commit=True)

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
            f"👉 **@{GARANT_USERNAME}**\n\n"
            f"2. После успешной отправки подарка нажмите кнопку **«🎁 Я отправил подарок»** ниже."
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

    except ValueError:
        msg = bot.reply_to(message, "❌ **Ошибка ввода!** Введите целое число (например: `50` или `100`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_topup_stars_amount)

def process_topup_xrocket(message):
    if message.text and message.text.lower() in ['/cancel', 'отмена']:
        bot.reply_to(message, "❌ Пополнение отменено.")
        return

    try:
        amount_ton = float(message.text.replace(",", ".").strip())
        if amount_ton <= 0:
            msg = bot.reply_to(message, "❌ Сумма должна быть больше 0 TON.\nВведите сумму ещё раз (или /cancel):")
            bot.register_next_step_handler(msg, process_topup_xrocket)
            return

        user_id = message.from_user.id
        payment_db_id = f"payxr_{user_id}_{int(time.time())}"

        invoice_data = create_xrocket_invoice(amount_ton, currency="TON", description=f"Пополнение баланса #{user_id}")

        if not invoice_data:
            bot.send_message(message.chat.id, "❌ Ошибка связи с xRocket API. Попробуйте позже или выберите другой способ оплаты.")
            return

        invoice_id = invoice_data["id"]
        pay_url = invoice_data["linkUrl"]

        execute_query("INSERT INTO payments (payment_id, user_id, amount) VALUES (?, ?, ?)", (payment_db_id, user_id, amount_ton), commit=True)

        markup = types.InlineKeyboardMarkup()
        btn_pay = types.InlineKeyboardButton("💳 Оплатить в xRocket", url=pay_url)
        btn_check = types.InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_xr_{invoice_id}_{payment_db_id}")
        btn_back = types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile")
        
        markup.add(btn_pay)
        markup.add(btn_check)
        markup.add(btn_back)

        text = (
            f"🚀 **Счет на оплату через xRocket создан!**\n\n"
            f"💰 Сумма: **{amount_ton} TON**\n"
            f"🆔 ID счета: `{invoice_id}`\n\n"
            f"📌 **Инструкция:**\n"
            f"1. Нажмите кнопку **«Оплатить в xRocket»** и подтвердите перевод.\n"
            f"2. После оплаты вернитесь сюда и нажмите **«Проверить оплату»**."
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

    except ValueError:
        msg = bot.reply_to(message, "❌ **Ошибка ввода!** Введите число (например: `0.5` или `2`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_topup_xrocket)

def process_review_text(message, order_id, rating):
    if message.text and message.text.lower() in ['/cancel', 'отмена']:
        save_review(order_id, message.from_user.id, rating, "Без текстового отзыва", message.from_user.first_name, message.from_user.username)
        bot.reply_to(message, "🙏 **Спасибо за вашу оценку!**", parse_mode="Markdown")
        return
        
    text = message.text if message.text else "Без текстового отзыва"
    save_review(order_id, message.from_user.id, rating, text, message.from_user.first_name, message.from_user.username)
    bot.reply_to(message, "🎉 **Спасибо за ваш отзыв!** Мы ценим ваше мнение.", parse_mode="Markdown")

def process_broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    if message.text and message.text.lower() in ['/cancel', 'отмена']:
        bot.reply_to(message, "❌ Рассылка отменена.")
        return

    users = execute_query("SELECT user_id FROM users", fetchall=True)

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
    if message.text and message.text.lower() in ['/cancel', 'отмена']:
        bot.reply_to(message, "❌ Добавление товара отменено.")
        return
    try:
        parts = [p.strip() for p in message.text.split(",")]
        name = parts[0]
        
        if len(parts) == 1:
            bot.reply_to(message, "❌ Забыли указать цену! Пример:\n`+380991234567, Номера, 100`", parse_mode="Markdown")
            return
            
        category = parts[1] if len(parts) > 2 else "🔥 Разное"
        p_uah = float(parts[2]) if len(parts) > 2 else float(parts[1])
        p_stars = float(parts[3]) if len(parts) > 3 else round(p_uah * 1.5, 1)
        p_rub = float(parts[4]) if len(parts) > 4 else round(p_uah * 2.5, 2)
        
        execute_query(
            "INSERT INTO catalog_items (name, category, price_uah, price_stars, price_rub) VALUES (?, ?, ?, ?, ?)", 
            (name, category, p_uah, p_stars, p_rub),
            commit=True
        )
        
        bot.reply_to(
            message, 
            f"✅ Товар/номер **{name}** успешно добавлен!\n\n"
            f"📂 Категория: **{category}**\n"
            f"💰 Цены: **{p_uah} грн** | **{p_stars} ⭐** | **{p_rub} ₽**", 
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Ошибка добавления товара: {e}")
        bot.reply_to(
            message, 
            "❌ **Ошибка формата!** Отправьте вот так:\n"
            "`Название, Категория, Цена_UAH`\n\n"
            "*Пример:*\n`+380991234567, Номера, 150`", 
            parse_mode="Markdown"
        )

def process_promo_activation(message):
    if message.text and message.text.lower() in ['/cancel', 'отмена']:
        bot.reply_to(message, "❌ Активация отменена.")
        return

    user_id = message.from_user.id
    code = message.text.strip()

    promo = execute_query("SELECT reward, uses_left FROM promocodes WHERE code=?", (code,), fetchone=True)

    if not promo:
        bot.reply_to(message, "❌ Такой промокод не существует!")
        return

    reward, uses_left = promo

    if uses_left <= 0:
        bot.reply_to(message, "❌ Этот промокод уже закончился!")
        return

    used = execute_query("SELECT * FROM used_promos WHERE user_id=? AND code=?", (user_id, code), fetchone=True)
    if used:
        bot.reply_to(message, "❌ Вы уже активировали этот промокод!")
        return

    execute_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (reward, user_id), commit=True)
    execute_query("UPDATE promocodes SET uses_left = uses_left - 1 WHERE code=?", (code,), commit=True)
    execute_query("INSERT INTO used_promos (user_id, code) VALUES (?, ?)", (user_id, code), commit=True)

    bot.reply_to(message, f"🎉 **Промокод активирован!** Вам зачислено **{reward:.2f}** на баланс.", parse_mode="Markdown")

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    keep_alive()
    print("🤖 Бот запущен и готов к работе!")
    bot.infinity_polling(timeout=60, long_polling_timeout=30) 
