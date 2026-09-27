import os
import sqlite3
import telebot
from telebot import types
import time
import random
import threading
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
GIFTS_PROFILE = "@garant_nazarow" # Профиль для приема подарков
REVIEWS_CHANNEL_ID = ""  # Укажите ID канала отзывов, если есть

CARD_NUMBER = os.environ.get("CARD_NUMBER", "4400005572759295")
CARD_HOLDER = "А-Банк / Карта UAH"
# ===================================================

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
        method TEXT DEFAULT 'uah',
        status TEXT DEFAULT 'pending'
    )
""")
conn.commit()

# Проверка/миграция недостающих колонок
try:
    cursor.execute("ALTER TABLE users ADD COLUMN last_bonus INTEGER DEFAULT 0")
    conn.commit()
except Exception:
    pass

try:
    cursor.execute("ALTER TABLE catalog_items ADD COLUMN category TEXT DEFAULT '🔥 Разное'")
    conn.commit()
except Exception:
    pass

try:
    cursor.execute("ALTER TABLE payments ADD COLUMN method TEXT DEFAULT 'uah'")
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

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def get_main_menu_text(first_name):
    return (
        f"👋 **Привет, {first_name}!**\n\n"
        f"🔥 **Добро пожаловать в наш шоп!**\n\n"
        f"🛒 **У нас ты можешь купить:**\n"
        f"• 📲 Физические SIM-карты и номера\n"
        f"• 📱 Telegram аккаунты (TData / Session+Json)\n"
        f"• ⚡ Виртуальные номера под любые сервисы\n"
        f"• 💎 Telegram Premium и звёзды (Stars)\n\n"
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
    b1 = types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")
    b2 = types.InlineKeyboardButton("👤 Управление пользователем", callback_data="admin_user_manage")
    b3 = types.InlineKeyboardButton("➕ Добавить товар", callback_data="admin_add_item")
    b4 = types.InlineKeyboardButton("🗑 Удалить товар", callback_data="admin_del_item")
    b5 = types.InlineKeyboardButton("📢 Массовая рассылка", callback_data="admin_broadcast")
    b6 = types.InlineKeyboardButton("🎁 Создать промокод", callback_data="admin_create_promo")
    b7 = types.InlineKeyboardButton("📥 Скачать БД", callback_data="admin_download_db")
    
    markup.add(b1)
    markup.add(b2)
    markup.add(b3, b4)
    markup.add(b5, b6)
    markup.add(b7)
    return markup

# ==================== КОМАНДЫ ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
    
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

    text = get_main_menu_text(message.from_user.first_name)
    markup = get_main_menu_keyboard()
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, f"❌ Отказано в доступе. Ваш ID: `{message.from_user.id}`", parse_mode="Markdown")
        return
    
    markup = get_admin_keyboard()
    text = "🛠 **Панель Администратора**\n\nУправляйте магазином с помощью интерактивных кнопок ниже:"
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

# ==================== CALLBACK HANDLER ====================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    
    cursor.execute("SELECT balance, currency, last_bonus FROM users WHERE user_id=?", (user_id,))
    u_row = cursor.fetchone()
    if not u_row:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        balance, curr, last_bonus = 0.0, "UAH", 0
    else:
        balance, curr, last_bonus = u_row[0], u_row[1], u_row[2]

    sym = CURRENCY_SYMBOLS.get(curr, "грн")

    if call.data == "admin_add_item":
        if user_id != ADMIN_ID: return
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id, 
            "➕ **Добавление товара**\n\n"
            "Отправьте данные через запятую:\n"
            "`Название, Категория, Цена_UAH, Цена_STARS, Цена_RUB`\n\n"
            "*Пример:*\n`+380991234567, 📲 Номера, 150, 200, 350`", 
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_add_item)
        return

    elif call.data == "admin_user_manage":
        if user_id != ADMIN_ID: return
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(call.message.chat.id, "👤 **Введите Telegram ID пользователя:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_admin_find_user)

    elif call.data == "admin_create_promo":
        if user_id != ADMIN_ID: return
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(
            call.message.chat.id,
            "🎁 **Создание промокода**\n\nВведите данные через пробел:\n`КОД СУММА КОЛИЧЕСТВО`\n\n*Пример:* `BONUS100 100 10`",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_admin_create_promo)

    elif call.data == "admin_download_db":
        if user_id != ADMIN_ID: return
        try:
            with open("store.db", "rb") as db_file:
                bot.send_document(call.message.chat.id, db_file, caption="📥 **Файл базы данных store.db**")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Ошибка отправки БД: {e}")

    elif call.data.startswith("admbal_"):
        if user_id != ADMIN_ID: return
        action, target_uid = call.data.split("_")[1], int(call.data.split("_")[2])
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(call.message.chat.id, f"💰 Введите сумму для {'начисления' if action == 'add' else 'списания'}:")
        bot.register_next_step_handler(msg, process_admin_change_balance, target_uid, action)

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
            bot.edit_message_text(
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
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

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
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

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
        
        bot.edit_message_text(
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
            "⏰ **Режим работы:** 24/7\n\n"
            "🛡 **Гарантия и условия:**\n"
            "• Все товары проходят строгую проверку перед выдачей.\n"
            "• Замена товара или возврат осуществляется при наличии видеозаписи с момента покупки.\n\n"
            "💳 **Пополнение и Оплата:**\n"
            "• Вы можете пополнить баланс картой или через Подарки (Stars).\n"
            "• В случае вопросов пишите менеджеру: @" + MANAGER_USERNAME
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("done_"):
        _, order_id, client_id = call.data.split("_")
        cursor.execute("UPDATE orders SET status='completed' WHERE order_id=?", (order_id,))
        conn.commit()

        bot.edit_message_text(f"✅ **Заказ #{order_id} выполнен!**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
        markup = types.InlineKeyboardMarkup(row_width=5)
        btns = [types.InlineKeyboardButton(f"⭐ {i}", callback_data=f"rate_{order_id}_{i}") for i in range(1, 6)]
        markup.add(*btns)

        try:
            bot.send_message(
                client_id, 
                f"🎉 **Заказ #{order_id} выполнен!** Менеджер подтвердил выдачу товара.\n\n"
                f"⭐ **Пожалуйста, оцените качество обслуживания:**", 
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
        msg = bot.edit_message_text(
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
        bot.edit_message_text("🙏 **Спасибо за вашу оценку!** Нам очень важно ваше мнение.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

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
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "top_up_balance":
        markup = types.InlineKeyboardMarkup()
        b_uah = types.InlineKeyboardButton("💳 UAH (Карта)", callback_data="topup_method_uah")
        b_stars = types.InlineKeyboardButton("🎁 Telegram Stars (Подарки)", callback_data="topup_method_stars")
        b_back = types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile")
        markup.add(b_uah)
        markup.add(b_stars)
        markup.add(b_back)

        bot.edit_message_text(
            "💳 **Выберите способ пополнения баланса:**", 
            call.message.chat.id, 
            call.message.message_id, 
            parse_mode="Markdown", 
            reply_markup=markup
        )

    elif call.data == "topup_method_uah":
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile"))

        text = (
            f"💳 **Пополнение баланса картой (UAH / грн)**\n\n"
            f"Введите сумму пополнения в **грн** (например: `100` или `250`):"
        )
        
        sent_msg = bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
        bot.register_next_step_handler(sent_msg, process_topup_amount_uah)

    # ==================== ВЫБОР ПОДАРКОВ КНОПКАМИ ====================
    elif call.data == "topup_method_stars":
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        b1 = types.InlineKeyboardButton("🧸 Мишка (15 ⭐)", callback_data="gift_choice_15")
        b2 = types.InlineKeyboardButton("🎁 Подарочек (25 ⭐)", callback_data="gift_choice_25")
        b3 = types.InlineKeyboardButton("🍾 Шампанское (50 ⭐)", callback_data="gift_choice_50")
        b4 = types.InlineKeyboardButton("💍 Колечко (100 ⭐)", callback_data="gift_choice_100")
        b_back = types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile")
        
        markup.add(b1, b2)
        markup.add(b3, b4)
        markup.add(b_back)

        text = (
            f"🎁 **Пополнение баланса через Telegram Подарки**\n\n"
            f"Выберите подарок из списка ниже, чтобы получить реквизиты для отправки на **{GIFTS_PROFILE}**:"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("gift_choice_"):
        amount = int(call.data.split("_")[2]) # 15, 25, 50 или 100
        payment_id = f"gift_{user_id}_{int(time.time())}"

        cursor.execute("INSERT INTO payments (payment_id, user_id, amount, method) VALUES (?, ?, ?, 'stars')", (payment_id, user_id, amount))
        conn.commit()

        markup = types.InlineKeyboardMarkup()
        btn_paid = types.InlineKeyboardButton("✅ Я отправл подарок", callback_data=f"paid_stars_{payment_id}")
        btn_back = types.InlineKeyboardButton("⬅️ Назад к выбору", callback_data="topup_method_stars")
        markup.add(btn_paid)
        markup.add(btn_back)

        text = (
            f"🎁 **Заявка на пополнение #{payment_id}**\n\n"
            f"💎 Сумма: **{amount} ⭐**\n\n"
            f"📌 **Реквизиты для отправки:**\n"
            f"👤 Получатель: **{GIFTS_PROFILE}**\n\n"
            f"⚠️ **Инструкция:**\n"
            f"1. Отправьте выбранный подарок стоимостью **{amount} ⭐** на профиль **{GIFTS_PROFILE}**.\n"
            f"2. После отправки нажмите кнопку **«✅ Я отправл подарок»** ниже."
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("paid_stars_"):
        payment_id = call.data.split("_", 2)[2]

        cursor.execute("SELECT amount, status FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()
        if not p_row: return

        p_amount, p_status = p_row
        if p_status == "completed":
            bot.send_message(call.message.chat.id, "✅ Этот платеж уже подтвержден!")
            return

        bot.edit_message_text(
            f"⏳ **Заявка на пополнение звёздами отправлена!**\n\n"
            f"💎 Сумма: **{int(p_amount)} ⭐**\n"
            f"🆔 ID заявки: `{payment_id}`\n\n"
            "Администратор проверяет отправку подарка в профиле **" + GIFTS_PROFILE + "**.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )

        username = f"@{call.from_user.username}" if call.from_user.username else "без username"
        adm_markup = types.InlineKeyboardMarkup()
        btn_confirm = types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"admgift_confirm_{payment_id}")
        btn_reject = types.InlineKeyboardButton("❌ Отклонить", callback_data=f"admgift_reject_{payment_id}")
        adm_markup.add(btn_confirm, btn_reject)

        adm_text = (
            f"📥 **Новая заявка на пополнение Stars (Подарок)!**\n\n"
            f"👤 Пользователь: {call.from_user.first_name} ({username})\n"
            f"🆔 ID: `{user_id}`\n"
            f"💎 Сумма: **{int(p_amount)} ⭐**\n"
            f"🧾 ID заявки: `{payment_id}`\n"
            f"📌 Профиль для приема: {GIFTS_PROFILE}"
        )
        try:
            bot.send_message(ADMIN_ID, adm_text, parse_mode="Markdown", reply_markup=adm_markup)
        except Exception as e:
            print(f"Ошибка отправки админу: {e}")

    elif call.data.startswith("admgift_confirm_"):
        if user_id != ADMIN_ID: return
        payment_id = call.data.split("_", 2)[2]

        cursor.execute("SELECT user_id, amount, status FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()
        if not p_row: return

        p_uid, p_amount, p_status = p_row
        if p_status == "completed":
            bot.send_message(call.message.chat.id, "⚠️ Платеж уже обработан!")
            return

        cursor.execute("UPDATE payments SET status='completed' WHERE payment_id=?", (payment_id,))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (p_amount, p_uid))
        conn.commit()

        bot.edit_message_text(f"✅ **Заявка #{payment_id} подтверждена!** Пользователю зачислено +{int(p_amount)} ⭐.", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(p_uid, f"🎉 **Баланс успешно пополнен!**\n💰 Администратор подтвердил получение подарка. Вам зачислено **+{int(p_amount)} ⭐**.", parse_mode="Markdown")
        except Exception: pass

    elif call.data.startswith("admgift_reject_"):
        if user_id != ADMIN_ID: return
        payment_id = call.data.split("_", 2)[2]

        cursor.execute("SELECT user_id FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()
        if not p_row: return
        p_uid = p_row[0]

        cursor.execute("UPDATE payments SET status='rejected' WHERE payment_id=?", (payment_id,))
        conn.commit()

        bot.edit_message_text(f"❌ **Заявка #{payment_id} отклонена.**", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(p_uid, f"❌ **Ваша заявка на пополнение через Подарок была отклонена администратором.**", parse_mode="Markdown")
        except Exception: pass

    elif call.data.startswith("paid_"):
        payment_id = call.data.split("_", 1)[1]
        cursor.execute("SELECT amount, status FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()
        if not p_row: return

        p_amount, p_status = p_row
        if p_status == "completed":
            bot.send_message(call.message.chat.id, "✅ Этот платеж уже подтвержден!")
            return

        bot.edit_message_text(
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

    elif call.data.startswith("admconfirm_"):
        if user_id != ADMIN_ID: return
        payment_id = call.data.split("_", 1)[1]

        cursor.execute("SELECT user_id, amount, status FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()
        if not p_row: return

        p_uid, p_amount, p_status = p_row
        if p_status == "completed":
            bot.send_message(call.message.chat.id, "⚠️ Платеж уже обработан!")
            return

        cursor.execute("UPDATE payments SET status='completed' WHERE payment_id=?", (payment_id,))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (p_amount, p_uid))
        conn.commit()

        bot.edit_message_text(f"✅ **Оплата #{payment_id} подтверждена!** Зачислено +{p_amount:.2f} грн.", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(p_uid, f"🎉 **Баланс успешно пополнен!**\n💰 Вам зачислено **+{p_amount:.2f} грн**.", parse_mode="Markdown")
        except Exception: pass

    elif call.data.startswith("admreject_"):
        if user_id != ADMIN_ID: return
        payment_id = call.data.split("_", 1)[1]

        cursor.execute("SELECT user_id FROM payments WHERE payment_id=?", (payment_id,))
        p_row = cursor.fetchone()
        if not p_row: return
        p_uid = p_row[0]

        cursor.execute("UPDATE payments SET status='rejected' WHERE payment_id=?", (payment_id,))
        conn.commit()

        bot.edit_message_text(f"❌ **Заявка #{payment_id} отклонена.**", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(p_uid, f"❌ **Ваша заявка на пополнение была отклонена.**", parse_mode="Markdown")
        except Exception: pass

    elif call.data == "change_currency":
        markup = types.InlineKeyboardMarkup()
        b1 = types.InlineKeyboardButton("🇺🇦 UAH (грн)", callback_data="set_curr_UAH")
        b2 = types.InlineKeyboardButton("⭐ Stars (звёзды)", callback_data="set_curr_STARS")
        b3 = types.InlineKeyboardButton("🇷🇺 RUB (₽)", callback_data="set_curr_RUB")
        b_back = types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile")
        markup.add(b1, b2, b3)
        markup.add(b_back)
        bot.edit_message_text("🌐 **Выберите удобную валюту:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data.startswith("set_curr_"):
        new_curr = call.data.split("_")[2]
        cursor.execute("UPDATE users SET currency=? WHERE user_id=?", (new_curr, user_id))
        conn.commit()
        
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        new_bal = cursor.fetchone()[0]
        new_sym = CURRENCY_SYMBOLS.get(new_curr, "грн")
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 Пополнить баланс", callback_data="top_up_balance"))
        markup.add(types.InlineKeyboardButton("👥 Реферальная система", callback_data="ref_system"))
        markup.add(types.InlineKeyboardButton(f"🌐 Валюта: {new_curr}", callback_data="change_currency"), types.InlineKeyboardButton("📜 Мои заказы", callback_data="my_orders"))
        markup.add(types.InlineKeyboardButton("🎁 Активировать промокод", callback_data="use_promo"))
        markup.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu"))
        
        text = f"👤 **Профиль**\n\n🆔 Ваш ID: `{user_id}`\n💰 Баланс: **{new_bal:.2f} {new_sym}**\n🌐 Выбранная валюта: **{new_curr}**"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

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
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ В профиль", callback_data="profile"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

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

        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "use_promo":
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        msg = bot.send_message(call.message.chat.id, "🎁 **Введите промокод:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_promo_activation)

    elif call.data == "main_menu":
        text = get_main_menu_text(call.from_user.first_name)
        markup = get_main_menu_keyboard()
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "admin_del_item":
        if user_id != ADMIN_ID: return
        cursor.execute("SELECT id, name, price_uah FROM catalog_items")
        items = cursor.fetchall()
        
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
        cursor.execute("DELETE FROM catalog_items WHERE id=?", (item_id,))
        conn.commit()
        bot.edit_message_text("✅ Товар успешно удален из каталога!", call.message.chat.id, call.message.message_id)

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

# ==================== STEP HANDLERS (ОБРАБОТКА ВВОДА) ====================

def process_topup_amount_uah(message):
    if message.text and message.text.startswith('/'): return
    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount < 10:
            msg = bot.reply_to(message, "❌ Минимальная сумма пополнения: **10 грн**.\nВведите сумму ещё раз:", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_topup_amount_uah)
            return
        
        user_id = message.from_user.id
        payment_id = f"pay_{user_id}_{int(time.time())}"

        cursor.execute("INSERT INTO payments (payment_id, user_id, amount, method) VALUES (?, ?, ?, 'uah')", (payment_id, user_id, amount))
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
            "1. Скопируйте номер карты.\n"
            f"2. Переведите ровно **{amount:.2f} грн**.\n"
            "3. Нажмите кнопку **«✅ Я оплатил»** ниже."
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
    except ValueError:
        msg = bot.reply_to(message, "❌ Введите число (например: `100`):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_topup_amount_uah)

def process_admin_find_user(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_uid = int(message.text.strip())
        cursor.execute("SELECT balance, currency FROM users WHERE user_id=?", (target_uid,))
        row = cursor.fetchone()

        if not row:
            bot.reply_to(message, "❌ Пользователь с таким ID не найден в базе.")
            return

        bal, u_curr = row
        u_sym = CURRENCY_SYMBOLS.get(u_curr, "грн")

        markup = types.InlineKeyboardMarkup()
        b_add = types.InlineKeyboardButton("➕ Начислить баланс", callback_data=f"admbal_add_{target_uid}")
        b_sub = types.InlineKeyboardButton("➖ Списать баланс", callback_data=f"admbal_sub_{target_uid}")
        markup.add(b_add, b_sub)

        bot.send_message(
            message.chat.id,
            f"👤 **Информация о пользователе:**\n\n"
            f"🆔 ID: `{target_uid}`\n"
            f"💰 Баланс: **{bal:.2f} {u_sym}** ({u_curr})\n\n"
            f"Выберите действие:",
            parse_mode="Markdown",
            reply_markup=markup
        )
    except ValueError:
        bot.reply_to(message, "❌ Некорректный Telegram ID. Введите число.")

def process_admin_change_balance(message, target_uid, action):
    if message.from_user.id != ADMIN_ID: return
    try:
        val = float(message.text.replace(",", ".").strip())
        if action == "sub": val = -val

        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (val, target_uid))
        conn.commit()

        cursor.execute("SELECT balance, currency FROM users WHERE user_id=?", (target_uid,))
        new_bal, u_curr = cursor.fetchone()
        u_sym = CURRENCY_SYMBOLS.get(u_curr, "грн")

        bot.reply_to(
            message,
            f"✅ Баланс пользователя `{target_uid}` успешно изменен!\n"
            f"💰 Новый баланс: **{new_bal:.2f} {u_sym}**",
            parse_mode="Markdown"
        )
        try:
            bot.send_message(target_uid, f"🔔 Ваш баланс был изменён администратором.\n💰 Текущий баланс: **{new_bal:.2f} {u_sym}**", parse_mode="Markdown")
        except Exception: pass
    except ValueError:
        bot.reply_to(message, "❌ Ошибка! Введите числовое значение.")

def process_admin_create_promo(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        code, reward, uses = message.text.split()
        cursor.execute("INSERT OR REPLACE INTO promocodes (code, reward, uses_left) VALUES (?, ?, ?)", 
                       (code, float(reward), int(uses)))
        conn.commit()
        bot.reply_to(message, f"✅ Промокод `{code}` на **{reward}** ({uses} активаций) создан!", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "❌ Ошибка формата! Отправьте: `КОД СУММА КОЛ_ВО`", parse_mode="Markdown")

def process_review_text(message, order_id, rating):
    text = message.text if message.text else "Без текстового отзыва"
    user_id = message.from_user.id
    save_review(order_id, user_id, rating, text, message.from_user.first_name, message.from_user.username)
    bot.reply_to(message, "🎉 **Спасибо за ваш отзыв!** Мы ценим ваше мнение.", parse_mode="Markdown")

def save_review(order_id, user_id, rating, text, first_name, username):
    cursor.execute("INSERT INTO reviews (order_id, user_id, rating, review_text) VALUES (?, ?, ?, ?)",
                   (order_id, user_id, rating, text))
    conn.commit()

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
    except Exception: pass

    if REVIEWS_CHANNEL_ID:
        try:
            bot.send_message(REVIEWS_CHANNEL_ID, review_msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка отправки в канал отзывов: {e}")

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
    try:
        parts = [p.strip() for p in message.text.split(",")]
        name = parts[0]
        category = parts[1] if len(parts) > 2 else "🔥 Разное"
        p_uah = float(parts[2]) if len(parts) > 2 else float(parts[1])
        p_stars = float(parts[3]) if len(parts) > 3 else round(p_uah * 1.5, 1)
        p_rub = float(parts[4]) if len(parts) > 4 else round(p_uah * 2.5, 2)
        
        cursor.execute("INSERT INTO catalog_items (name, category, price_uah, price_stars, price_rub) VALUES (?, ?, ?, ?, ?)", 
                       (name, category, p_uah, p_stars, p_rub))
        conn.commit()
        
        bot.reply_to(
            message, 
            f"✅ Товар/номер **{name}** успешно добавлен!\n\n"
            f"📂 Категория: **{category}**\n"
            f"💰 Цены: **{p_uah} грн** | **{p_stars} ⭐** | **{p_rub} ₽**", 
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, "❌ **Ошибка формата!** Пример:\n`+380991234567, Номера, 150`", parse_mode="Markdown")

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
