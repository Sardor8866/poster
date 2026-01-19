import telebot
from telebot import types
import sqlite3
import json
import time
import threading
from datetime import datetime
import random
import string
import re
import html
from flask import Flask, request, jsonify
from channel import WithdrawalChannel  # Импортируем модуль канала

# ========== НАСТРОЙКИ ==========
TOKEN = "8337396229:AAES7rHlibutnscXOHk7t6XB2fK2CUni5eE"
WEBHOOK_URL = "https://poster-x4jl.onrender.com"  # ⚠️ ЗАМЕНИ на свой URL!
WEBHOOK_PATH = f"/webhook/{TOKEN}"
PORT = 8080

# Инициализация бота
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

# Инициализация Flask приложения
app = Flask(__name__)

# Инициализация канала для уведомлений
withdrawal_channel = WithdrawalChannel(TOKEN)

# ID канала для уведомлений (замените на свой)
WITHDRAWAL_CHANNEL_ID = "-1002990005205"  # Пример ID канала

# Установка канала для уведомлений
withdrawal_channel.set_channel(WITHDRAWAL_CHANNEL_ID)

# ID администратора (замените на свой)
ADMIN_IDS = [8118184388]  # Замените на ваш ID телеграм

# Глобальные переменные для каналов
REQUIRED_CHANNELS = []  # Каналы с обязательной подпиской (проверяются)
SIMPLE_LINKS = []    # Простые ссылки (любые ссылки, не проверяются)

# Словарь для хранения соответствия withdrawal_id -> message_id в канале
withdrawal_messages = {}

# ========== УТИЛИТЫ ==========
def sanitize_text(text):
    """Очистка текста от проблемных символов"""
    if not text:
        return ""

    # Удаляем непечатаемые символы
    text = ''.join(char for char in text if char.isprintable())

    # Заменяем проблемные HTML-сущности
    text = html.escape(text)

    # Удаляем лишние пробелы
    text = ' '.join(text.split())

    return text

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С КАНАЛАМИ ==========
def check_user_subscription(user_id, channel_id):
    """Проверка подписки пользователя на канал"""
    try:
        member = bot.get_chat_member(channel_id, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Ошибка при проверке подписки: {e}")
        return False

def check_all_subscriptions(user_id):
    """Проверка ВСЕХ обязательных подписок для пользователя"""
    if not REQUIRED_CHANNELS:
        return True, []  # Нет обязательных каналов

    not_subscribed = []
    all_subscribed = True

    # Проверяем только обязательные каналы
    for channel in REQUIRED_CHANNELS:
        is_subscribed = check_user_subscription(user_id, channel['channel_id'])

        if not is_subscribed:
            all_subscribed = False
            not_subscribed.append(channel)

    return all_subscribed, not_subscribed

def check_subscription_required(user_id):
    """Проверка обязательных подписок"""
    if not REQUIRED_CHANNELS:
        return True, None

    all_subscribed, not_subscribed = check_all_subscriptions(user_id)

    if all_subscribed:
        return True, None
    else:
        # Формируем сообщение с ВСЕМИ каналами и ссылками
        all_items = get_all_items_for_user()

        channels_text = """═══════════════════════════
✨ <b>ПОДПИШИТЕСЬ НА КАНАЛЫ</b> ✨
═══════════════════════════

<blockquote>Для доступа к боту необходимо подписаться на каналы ниже:</blockquote>

<b>🔐 ОБЯЗАТЕЛЬНЫЕ КАНАЛЫ (проверяются):</b>\n"""

        # Показываем сначала обязательные каналы
        for channel in REQUIRED_CHANNELS:
            safe_name = sanitize_text(channel['channel_name'])
            channels_text += f"• {safe_name} 📌\n"

        # Затем показываем простые ссылки
        if SIMPLE_LINKS:
            channels_text += "\n<b>🔗 РЕКОМЕНДУЕМ ПОДПИСАТЬСЯ:</b>\n"
            for link_item in SIMPLE_LINKS:
                safe_name = sanitize_text(link_item['channel_name'])
                channels_text += f"• {safe_name} 🔗\n"

        channels_text += """\n<blockquote>✅ <b>Подпишитесь на обязательные каналы (отмечены 📌) и нажмите кнопку 'Проверить подписку'</b></blockquote>"""

        keyboard = types.InlineKeyboardMarkup()

        # Добавляем кнопки для всех обязательных каналов
        for channel in REQUIRED_CHANNELS:
            safe_name = sanitize_text(channel['channel_name'])
            if 'channel_username' in channel and channel['channel_username']:
                username = channel['channel_username'].replace('@', '')
                if username:
                    keyboard.add(
                        types.InlineKeyboardButton(
                            f"📺 {safe_name}",
                            url=f"https://t.me/{username}"
                        )
                    )
            elif 'channel_link' in channel and channel['channel_link']:
                keyboard.add(
                    types.InlineKeyboardButton(
                        f"📺 {safe_name}",
                        url=channel['channel_link']
                    )
                )

        # Добавляем кнопки для простых ссылок
        for link_item in SIMPLE_LINKS:
            safe_name = sanitize_text(link_item['channel_name'])
            keyboard.add(
                types.InlineKeyboardButton(
                    f"🔗 {safe_name}",
                    url=link_item['channel_link']
                )
            )

        keyboard.add(
            types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription_after")
        )

        return False, (channels_text, keyboard)

def get_all_items_for_user():
    """Получить все каналы и ссылки для показа пользователю"""
    # Объединяем все и перемешиваем
    all_items = REQUIRED_CHANNELS + SIMPLE_LINKS
    random.shuffle(all_items)
    return all_items

def get_all_items_for_admin():
    """Получить все каналы и ссылки с указанием типа для админа"""
    all_items = []
    for ch in REQUIRED_CHANNELS:
        all_items.append({**ch, 'type': 'required'})
    for ch in SIMPLE_LINKS:
        all_items.append({**ch, 'type': 'simple'})
    return all_items

# ========== ФУНКЦИИ ДЛЯ ЧЕКОВ ==========
def init_checks_db():
    """Инициализация таблицы для чеков"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checks (
            check_id INTEGER PRIMARY KEY AUTOINCREMENT,
            check_code TEXT UNIQUE NOT NULL,
            amount INTEGER NOT NULL,
            max_activations INTEGER NOT NULL,
            current_activations INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            description TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS check_activations (
            activation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            check_code TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    conn.commit()
    conn.close()

def generate_check_code(length=8):
    """Генерация уникального кода чека"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def create_check(amount, max_activations, created_by, description=None):
    """Создание нового чека"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    check_code = generate_check_code()
    while True:
        cursor.execute("SELECT check_code FROM checks WHERE check_code = ?", (check_code,))
        if not cursor.fetchone():
            break
        check_code = generate_check_code()

    cursor.execute('''
        INSERT INTO checks (check_code, amount, max_activations, created_by, description)
        VALUES (?, ?, ?, ?, ?)
    ''', (check_code, amount, max_activations, created_by, description))

    conn.commit()
    conn.close()

    return check_code

def activate_check(check_code, user_id):
    """Активация чека пользователем"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    # Проверяем существование чека
    cursor.execute('''
        SELECT amount, max_activations, current_activations, is_active
        FROM checks WHERE check_code = ?
    ''', (check_code,))

    check_data = cursor.fetchone()

    if not check_data:
        conn.close()
        return False, "Чек не найден"

    amount, max_activations, current_activations, is_active = check_data

    if not is_active:
        conn.close()
        return False, "Чек деактивирован"

    if current_activations >= max_activations:
        conn.close()
        return False, "Достигнут лимит активаций"

    # Проверяем, активировал ли уже этот пользователь этот чек
    cursor.execute('''
        SELECT activation_id FROM check_activations
        WHERE check_code = ? AND user_id = ?
    ''', (check_code, user_id))

    if cursor.fetchone():
        conn.close()
        return False, "Вы уже активировали этот чек"

    # Активируем чек
    cursor.execute('''
        UPDATE checks
        SET current_activations = current_activations + 1
        WHERE check_code = ?
    ''', (check_code,))

    # Начисляем звезды пользователю
    cursor.execute("UPDATE users SET stars = stars + ? WHERE user_id = ?", (amount, user_id))

    # Записываем активацию
    cursor.execute('''
        INSERT INTO check_activations (check_code, user_id, amount)
        VALUES (?, ?, ?)
    ''', (check_code, user_id, amount))

    # Записываем транзакцию
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, description)
        VALUES (?, ?, ?, ?)
    ''', (user_id, amount, 'check_activation', f'Активация чека {check_code}'))

    conn.commit()
    conn.close()

    return True, f"🎉 Чек успешно активирован! Получено {amount} звезд ⭐"

def get_check_info(check_code):
    """Получение информации о чеке"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT c.check_code, c.amount, c.max_activations, c.current_activations,
               c.created_at, c.is_active, c.description,
               u.full_name as creator_name
        FROM checks c
        LEFT JOIN users u ON c.created_by = u.user_id
        WHERE c.check_code = ?
    ''', (check_code,))

    check_data = cursor.fetchone()
    conn.close()

    if not check_data:
        return None

    return {
        'check_code': check_data[0],
        'amount': check_data[1],
        'max_activations': check_data[2],
        'current_activations': check_data[3],
        'created_at': check_data[4],
        'is_active': bool(check_data[5]),
        'description': check_data[6],
        'creator_name': check_data[7]
    }

def get_all_checks(limit=50):
    """Получение всех чеков"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT c.check_code, c.amount, c.max_activations, c.current_activations,
               c.created_at, c.is_active, c.description,
               u.full_name as creator_name
        FROM checks c
        LEFT JOIN users u ON c.created_by = u.user_id
        ORDER BY c.created_at DESC
        LIMIT ?
    ''', (limit,))

    checks = cursor.fetchall()
    conn.close()

    result = []
    for check in checks:
        result.append({
            'check_code': check[0],
            'amount': check[1],
            'max_activations': check[2],
            'current_activations': check[3],
            'created_at': check[4],
            'is_active': bool(check[5]),
            'description': check[6],
            'creator_name': check[7]
        })

    return result

def deactivate_check(check_code):
    """Деактивация чека"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("UPDATE checks SET is_active = 0 WHERE check_code = ?", (check_code,))

    conn.commit()
    conn.close()

    return True

# ========== ОБРАБОТЧИКИ ==========
@bot.callback_query_handler(func=lambda call: call.data == "check_subscription_after")
def check_subscription_after_callback(call):
    """Проверка подписки после нажатия кнопки"""
    user_id = call.from_user.id
    all_subscribed, not_subscribed = check_all_subscriptions(user_id)

    if all_subscribed:
        try:
            bot.edit_message_text(
                """═══════════════════════════
✨ <b>ВСЕ ПОДПИСКИ АКТИВНЫ</b> ✨
═══════════════════════════

<blockquote>✅ <b>Отлично! Вы подписаны на все обязательные каналы!</b></blockquote>

Теперь вы можете пользоваться ботом.""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML'
            )
        except:
            pass

        # Показываем главное меню
        bot.send_message(
            call.message.chat.id,
            """═══════════════════════════
✨ <b>ДОБРО ПОЖАЛОВАТЬ</b> ✨
═══════════════════════════

<blockquote>🎉 <b>Добро пожаловать в премиум бот!</b></blockquote>

Выберите действие из меню ниже:""",
            parse_mode='HTML',
            reply_markup=create_main_menu()
        )

        # Проверяем и начисляем реферальные бонусы
        check_and_award_referral_bonus(user_id)
    else:
        # Показываем все каналы снова
        channels_text = """═══════════════════════════
✨ <b>ОБЯЗАТЕЛЬНЫЕ ПОДПИСКИ</b> ✨
═══════════════════════════

<blockquote>❌ <b>Вы еще не подписались на все обязательные каналы!</b></blockquote>

<b>Осталось подписаться на обязательные каналы:</b>\n\n"""

        keyboard = types.InlineKeyboardMarkup()

        # Добавляем только обязательные каналы
        for channel in REQUIRED_CHANNELS:
            safe_name = sanitize_text(channel['channel_name'])
            channels_text += f"• {safe_name} 📌\n"

            if 'channel_username' in channel and channel['channel_username']:
                username = channel['channel_username'].replace('@', '')
                if username:
                    keyboard.add(
                        types.InlineKeyboardButton(
                            f"📺 {safe_name}",
                            url=f"https://t.me/{username}"
                        )
                    )
            elif 'channel_link' in channel and channel['channel_link']:
                keyboard.add(
                    types.InlineKeyboardButton(
                        f"📺 {safe_name}",
                        url=channel['channel_link']
                    )
                )

        # Добавляем простые ссылки (для рекомендаций)
        for link_item in SIMPLE_LINKS:
            safe_name = sanitize_text(link_item['channel_name'])
            keyboard.add(
                types.InlineKeyboardButton(
                    f"🔗 {safe_name}",
                    url=link_item['channel_link']
                )
            )

        channels_text += """\n<blockquote>✅ <b>После подписки на все обязательные каналы нажмите кнопку ниже</b></blockquote>"""

        keyboard.add(
            types.InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_subscription_after")
        )

        try:
            bot.edit_message_text(
                channels_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        except:
            pass

def check_and_award_referral_bonus(user_id):
    """Проверяет и начисляет реферальные бонусы после подписки на все каналы"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    # Получаем информацию о пользователе
    cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if result and result[0]:  # Если у пользователя есть реферер
        referrer_id = result[0]

        # Проверяем, были ли уже начислены бонусы за этого реферала
        cursor.execute('''
            SELECT transaction_id FROM transactions
            WHERE user_id = ? AND type = 'referral_bonus'
            AND description LIKE ?
        ''', (referrer_id, f'%приглашение пользователя {user_id}%'))

        existing_bonus = cursor.fetchone()

        # Если бонусы еще не начислялись - начисляем
        if not existing_bonus:
            # Начисляем рефереру
            cursor.execute("UPDATE users SET stars = stars + 5 WHERE user_id = ?", (referrer_id,))
            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, ?, ?)
            ''', (referrer_id, 5, 'referral_bonus', f'Бонус за приглашение пользователя {user_id}'))

            # Начисляем рефералу приветственный бонус
            cursor.execute("UPDATE users SET stars = stars + 1 WHERE user_id = ?", (user_id,))
            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, ?, ?)
            ''', (user_id, 1, 'welcome_bonus', 'Приветственный бонус за регистрацию по реферальной ссылке'))

            conn.commit()

            # Отправляем уведомление рефереру
            try:
                cursor.execute("SELECT full_name FROM users WHERE user_id = ?", (user_id,))
                user_name = cursor.fetchone()[0] or f"User_{user_id}"

                bot.send_message(
                    referrer_id,
                    f"""═══════════════════════════
✨ <b>НОВЫЙ РЕФЕРАЛ</b> ✨
═══════════════════════════

<blockquote>🎉 <b>Поздравляем!</b></blockquote>

Приглашенный вами пользователь подписался на все обязательные каналы!

<b>👤 Информация о реферале:</b>
<blockquote>Пользователь: {sanitize_text(user_name)}</blockquote>

<b>✅ Начисление:</b>
<blockquote>Вам начислено: +5 звезд! ⭐</blockquote>

<blockquote>🎯 <b>Продолжайте приглашать друзей!</b></blockquote>""",
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Не удалось отправить уведомление рефереру: {e}")

    conn.close()

# ========== АДМИН ПАНЕЛЬ ==========
def create_admin_keyboard():
    """Клавиатура админ панели"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "📊 Статистика бота",
        "📢 Рассылка всем",
        "📺 Управление каналами",
        "💰 Управление выводами",
        "⭐ Добавить звезды",
        "🎫 Управление чеками",
        "⬅️ Главное меню"
    ]
    keyboard.add(*buttons)
    return keyboard

@bot.message_handler(commands=['admin'])
def admin_command(message):
    """Команда /admin для доступа к админ панели"""
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ У вас нет доступа к админ панели")
        return

    admin_text = """═══════════════════════════
⚙️ <b>АДМИН ПАНЕЛЬ</b> ⚙️
═══════════════════════════

<blockquote><b>Добро пожаловать в панель управления!</b></blockquote>

<b>Выберите раздел из меню ниже:</b>"""

    bot.send_message(
        message.chat.id,
        admin_text,
        parse_mode='HTML',
        reply_markup=create_admin_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "📊 Статистика бота" and message.from_user.id in ADMIN_IDS)
def bot_stats_command(message):
    """Статистика бота"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by IS NOT NULL")
        ref_users = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(stars) FROM users")
        total_stars = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'approved'")
        approved_withdrawals = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(amount) FROM withdrawals WHERE status = 'approved'")
        withdrawn_stars = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'")
        pending_withdrawals = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(amount) FROM withdrawals WHERE status = 'pending'")
        pending_stars = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM checks")
        total_checks = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM check_activations")
        total_check_activations = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(amount) FROM check_activations")
        total_check_stars = cursor.fetchone()[0] or 0

        stats_text = f"""═══════════════════════════
📊 <b>СТАТИСТИКА БОТА</b> 📊
═══════════════════════════

<b>👥 ПОЛЬЗОВАТЕЛИ:</b>
• Всего: <b>{total_users}</b> 👤
• По реф.ссылкам: <b>{ref_users}</b> 🔗

<b>⭐ ЗВЕЗДЫ:</b>
• Всего звезд: <b>{total_stars} ⭐</b>
• Средний баланс: <b>{round(total_stars/total_users if total_users > 0 else 0, 1)} ⭐</b>

<b>💰 ВЫВОДЫ:</b>
• Одобрено: <b>{approved_withdrawals}</b> на {withdrawn_stars} ⭐
• Ожидает: <b>{pending_withdrawals}</b> на {pending_stars} ⭐

<b>🎫 ЧЕКИ:</b>
• Всего чеков: <b>{total_checks}</b>
• Активаций: <b>{total_check_activations}</b>
• Выдано через чеки: <b>{total_check_stars} ⭐</b>

<b>📺 КАНАЛЫ И ССЫЛКИ:</b>
• Всего элементов: <b>{len(REQUIRED_CHANNELS) + len(SIMPLE_LINKS)}</b>
• Обязательных каналов: <b>{len(REQUIRED_CHANNELS)}</b>
• Простых ссылок: <b>{len(SIMPLE_LINKS)}</b>"""

        bot.send_message(message.chat.id, stats_text, parse_mode='HTML')

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")
    finally:
        conn.close()

@bot.message_handler(func=lambda message: message.text == "📢 Рассылка всем" and message.from_user.id in ADMIN_IDS)
def mailing_all_command(message):
    """Рассылка всем пользователям"""
    msg = bot.send_message(
        message.chat.id,
        """═══════════════════════════
📢 <b>РАССЫЛКА ВСЕМ ПОЛЬЗОВАТЕЛЯМ</b> 📢
═══════════════════════════

<blockquote>Отправьте сообщение для рассылки:</blockquote>

<i>Поддерживается HTML разметка</i>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_mailing_all)

def process_mailing_all(message):
    """Обработка рассылки всем"""
    mailing_text = sanitize_text(message.text)

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    bot.send_message(
        message.chat.id,
        f"""═══════════════════════════
✨ <b>НАЧАЛО РАССЫЛКИ</b> ✨
═══════════════════════════

<blockquote>⏳ Начинаю рассылку для {len(users)} пользователей...</blockquote>""",
        parse_mode='HTML'
    )

    success_count = 0
    fail_count = 0

    for user in users:
        try:
            bot.send_message(user[0], mailing_text, parse_mode='HTML')
            success_count += 1
            time.sleep(0.05)
        except:
            fail_count += 1

    bot.send_message(
        message.chat.id,
        f"""═══════════════════════════
✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b> ✅
═══════════════════════════

<blockquote>✅ <b>Рассылка завершена!</b></blockquote>

<b>📊 РЕЗУЛЬТАТЫ:</b>
• Успешно: {success_count} пользователей
• Не удалось: {fail_count} пользователей
• Всего: {len(users)} пользователей

<blockquote><i>Рассылка выполнена</i></blockquote>""",
        parse_mode='HTML',
        reply_markup=create_admin_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "📺 Управление каналами" and message.from_user.id in ADMIN_IDS)
def manage_channels_command(message):
    """Управление каналами и ссылками"""
    channels_text = """═══════════════════════════
📺 <b>УПРАВЛЕНИЕ КАНАЛАМИ И ССЫЛКАМИ</b> 📺
═══════════════════════════

<blockquote><b>Для пользователей все показывается в одном списке.</b></blockquote>

<b>📝 КАК ДОБАВИТЬ:</b>
• /addchannel_required - Обязательный канал (проверяется подписка)
• /addlink_simple - Простая ссылка (любая ссылка, не проверяется)

<b>🗑️ КАК УДАЛИТЬ:</b>
Отправьте команду /removechannel

<b>📋 СПИСОК:</b>
Отправьте команду /listchannels

<b>🔍 ПРОВЕРКА:</b>
Отправьте команду /checksubs"""

    bot.send_message(
        message.chat.id,
        channels_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['addchannel_required'])
def add_channel_required_command(message):
    """Добавление обязательного канала"""
    if message.from_user.id not in ADMIN_IDS:
        return

    msg = bot.send_message(
        message.chat.id,
        """═══════════════════════════
➕ <b>ДОБАВЛЕНИЕ ОБЯЗАТЕЛЬНОГО КАНАЛА</b> ➕
═══════════════════════════

<blockquote>Отправьте ссылку на канал в формате:</blockquote>

• @username
• https://t.me/username

<blockquote><i>Бот должен быть администратором в канале!</i></blockquote>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_add_channel, 'required')

@bot.message_handler(commands=['addlink_simple'])
def add_link_simple_command(message):
    """Добавление простой ссылки"""
    if message.from_user.id not in ADMIN_IDS:
        return

    msg = bot.send_message(
        message.chat.id,
        """═══════════════════════════
➕ <b>ДОБАВЛЕНИЕ ПРОСТОЙ ССЫЛКИ</b> ➕
═══════════════════════════

<blockquote>Отправьте:</blockquote>

1. Ссылку (любую - канал, сайт и т.д.)
2. Название для кнопки

<b>📋 ПРИМЕР:</b>
<blockquote>https://t.me/my_channel
Мой канал</blockquote>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_add_link_simple)

def process_add_link_simple(message):
    """Обработка добавления простой ссылки"""
    try:
        parts = message.text.split('\n')

        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Отправьте ссылку и название с новой строки")
            return

        channel_link = sanitize_text(parts[0].strip())
        channel_name = sanitize_text(parts[1].strip())

        if not channel_link or not channel_name:
            bot.send_message(message.chat.id, "❌ Ссылка и название не могут быть пустыми")
            return

        # Проверяем, есть ли уже такая ссылка
        global SIMPLE_LINKS
        if any(ch['channel_link'] == channel_link for ch in SIMPLE_LINKS):
            bot.send_message(message.chat.id, "❌ Эта ссылка уже добавлена")
            return

        # Добавляем простую ссылку
        link_data = {
            'channel_id': None,  # У простых ссылок нет ID
            'channel_username': None,
            'channel_name': channel_name,
            'channel_link': channel_link,
            'type': 'simple'
        }

        SIMPLE_LINKS.append(link_data)

        # Сохраняем в базу данных
        conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                channel_username TEXT,
                channel_name TEXT NOT NULL,
                channel_link TEXT NOT NULL,
                channel_type TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                added_by INTEGER,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Добавляем колонку channel_link если её нет
        try:
            cursor.execute("SELECT channel_link FROM channels LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE channels ADD COLUMN channel_link TEXT NOT NULL DEFAULT ''")

        cursor.execute('''
            INSERT INTO channels (channel_id, channel_username, channel_name, channel_link, channel_type, added_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (None, None, channel_name, channel_link, 'simple', message.from_user.id))

        conn.commit()
        conn.close()

        bot.send_message(
            message.chat.id,
            f"""═══════════════════════════
✅ <b>ССЫЛКА ДОБАВЛЕНА</b> ✅
═══════════════════════════

<blockquote>✅ <b>Ссылка успешно добавлена!</b></blockquote>

<b>🔗 ИНФОРМАЦИЯ:</b>
• Название: {channel_name}
• Ссылка: {channel_link}
• Тип: простая ссылка (не проверяется)

<blockquote><i>Пользователи увидят эту ссылку в списке.</i></blockquote>""",
            parse_mode='HTML'
        )

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

def process_add_channel(message, channel_type):
    """Обработка добавления канала"""
    try:
        channel_link = sanitize_text(message.text.strip())

        if not channel_link:
            bot.send_message(message.chat.id, "❌ Ссылка не может быть пустой")
            return

        # Извлекаем username из ссылки
        channel_username = None
        channel_name = channel_link  # По умолчанию используем ссылку как имя

        # Пытаемся получить информацию о канале
        try:
            if channel_link.startswith('@'):
                username = channel_link[1:]
                chat = bot.get_chat(f"@{username}")
            elif 't.me/' in channel_link:
                # Извлекаем username из ссылки
                if '/' in channel_link:
                    username = channel_link.split('/')[-1].replace('@', '')
                else:
                    username = channel_link.replace('https://t.me/', '').replace('@', '')
                chat = bot.get_chat(f"@{username}")
            else:
                # Если это не стандартная ссылка на Telegram
                raise Exception("Не стандартная ссылка Telegram")

            channel_id = chat.id
            channel_name = sanitize_text(chat.title) if chat.title else channel_link

            if channel_link.startswith('@'):
                channel_username = channel_link
            else:
                channel_username = f"@{username}"

            # Для обязательных каналов проверяем права бота
            if channel_type == 'required':
                try:
                    bot.get_chat_member(channel_id, bot.get_me().id)
                except:
                    bot.send_message(
                        message.chat.id,
                        f"""═══════════════════════════
❌ <b>ОШИБКА ПРАВ</b> ❌
═══════════════════════════

<blockquote>❌ Бот не является администратором в канале <b>{channel_name}</b></blockquote>

<blockquote>Добавьте бота как администратора и попробуйте снова.</blockquote>""",
                        parse_mode='HTML'
                    )
                    return

        except Exception as e:
            # Если не удалось получить информацию о канале, используем как простую ссылку
            if channel_type == 'required':
                bot.send_message(
                    message.chat.id,
                    f"""═══════════════════════════
❌ <b>ОШИБКА ПАРСИНГА</b> ❌
═══════════════════════════

<blockquote>❌ Не удалось получить информацию о канале: {str(e)}</blockquote>

<blockquote>Для обязательных каналов используйте правильные ссылки на Telegram каналы.</blockquote>""",
                    parse_mode='HTML'
                )
                return
            else:
                # Для простых ссылок используем как есть
                channel_id = None
                channel_username = None

        # Добавляем канал в соответствующий список
        channel_data = {
            'channel_id': channel_id,
            'channel_username': channel_username,
            'channel_name': channel_name,
            'channel_link': channel_link,
            'type': channel_type
        }

        if channel_type == 'required':
            global REQUIRED_CHANNELS
            # Проверяем, нет ли уже такого канала
            if any(ch['channel_id'] == channel_id for ch in REQUIRED_CHANNELS if ch['channel_id']):
                bot.send_message(message.chat.id, "❌ Этот канал уже добавлен как обязательный")
                return
            REQUIRED_CHANNELS.append(channel_data)
        else:
            global SIMPLE_LINKS
            # Проверяем, нет ли уже такой ссылки
            if any(ch['channel_link'] == channel_link for ch in SIMPLE_LINKS):
                bot.send_message(message.chat.id, "❌ Эта ссылка уже добавлена")
                return
            SIMPLE_LINKS.append(channel_data)

        # Сохраняем в базу данных
        conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                channel_username TEXT,
                channel_name TEXT NOT NULL,
                channel_link TEXT NOT NULL,
                channel_type TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                added_by INTEGER,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Добавляем колонку channel_link если её нет
        try:
            cursor.execute("SELECT channel_link FROM channels LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE channels ADD COLUMN channel_link TEXT NOT NULL DEFAULT ''")

        cursor.execute('''
            INSERT OR REPLACE INTO channels (channel_id, channel_username, channel_name, channel_link, channel_type, added_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (channel_id, channel_username, channel_name, channel_link, channel_type, message.from_user.id))

        conn.commit()
        conn.close()

        type_text = "обязательный (проверяется)" if channel_type == 'required' else "простая ссылка (не проверяется)"
        bot.send_message(
            message.chat.id,
            f"""═══════════════════════════
✅ <b>УСПЕШНО ДОБАВЛЕНО</b> ✅
═══════════════════════════

<blockquote>✅ <b>Успешно добавлено!</b></blockquote>

<b>📺 ИНФОРМАЦИЯ:</b>
• Название: {channel_name}
• Ссылка: {channel_link}
{f'• ID: {channel_id}' if channel_id else ''}
• Тип: {type_text}

<blockquote><i>Пользователи увидят это в списке.</i></blockquote>""",
            parse_mode='HTML'
        )

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(commands=['listchannels'])
def list_channels_command(message):
    """Список каналов и ссылок"""
    if message.from_user.id not in ADMIN_IDS:
        return

    all_items = get_all_items_for_admin()

    if not all_items:
        channels_text = """═══════════════════════════
📋 <b>СПИСОК КАНАЛОВ И ССЫЛОК</b> 📋
═══════════════════════════

<blockquote>📭 <b>Список каналов и ссылок пуст</b></blockquote>

<blockquote>Добавьте каналы или ссылки.</blockquote>"""
    else:
        channels_text = """═══════════════════════════
📋 <b>СПИСОК КАНАЛОВ И ССЫЛОК</b> 📋
═══════════════════════════\n\n"""

        # Разделяем по типам
        required_channels = [ch for ch in all_items if ch['type'] == 'required']
        simple_links = [ch for ch in all_items if ch['type'] == 'simple']

        if required_channels:
            channels_text += "<b>🔐 ОБЯЗАТЕЛЬНЫЕ КАНАЛЫ (проверяются):</b>\n"
            for i, ch in enumerate(required_channels, 1):
                safe_name = sanitize_text(ch['channel_name'])
                channels_text += f'{i}. <b>{safe_name}</b>\n'
                channels_text += f'   🔗 {ch["channel_link"]}'
                if ch.get('channel_id'):
                    channels_text += f' | 🆔 {ch["channel_id"]}'
                channels_text += '\n\n'

        if simple_links:
            channels_text += "<b>🔗 ПРОСТЫЕ ССЫЛКИ (не проверяются):</b>\n"
            for i, ch in enumerate(simple_links, 1):
                safe_name = sanitize_text(ch['channel_name'])
                channels_text += f'{i}. <b>{safe_name}</b>\n'
                channels_text += f'   🔗 {ch["channel_link"]}\n\n'

        channels_text += f"<b>📊 ИТОГО:</b> {len(all_items)} элементов"
        channels_text += f" ({len(required_channels)} обязательных, {len(simple_links)} простых ссылок)"

    bot.send_message(
        message.chat.id,
        channels_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['removechannel'])
def remove_channel_command(message):
    """Удаление канала или ссылки"""
    if message.from_user.id not in ADMIN_IDS:
        return

    all_items = get_all_items_for_admin()

    if not all_items:
        bot.send_message(message.chat.id, "❌ Нет каналов или ссылок для удаления")
        return

    # Показываем список каналов с кнопками
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    for ch in all_items:
        safe_name = sanitize_text(ch['channel_name'])
        channel_type = "🔐" if ch['type'] == 'required' else "🔗"
        # Используем channel_link как идентификатор для удаления
        keyboard.add(
            types.InlineKeyboardButton(
                f"{channel_type} {safe_name}",
                callback_data=f"remove_channel_{ch['channel_link']}_{ch['type']}"
            )
        )

    bot.send_message(
        message.chat.id,
        """═══════════════════════════
➖ <b>УДАЛЕНИЕ КАНАЛА ИЛИ ССЫЛКИ</b> ➖
═══════════════════════════

<blockquote>Выберите что удалить из списка ниже:</blockquote>""",
        parse_mode='HTML',
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('remove_channel_'))
def remove_channel_callback(call):
    """Обработка удаления канала или ссылки"""
    try:
        parts = call.data.replace('remove_channel_', '').split('_')
        channel_link = '_'.join(parts[:-1])  # Восстанавливаем ссылку
        channel_type = parts[-1]

        # Удаляем из соответствующего списка
        if channel_type == 'required':
            global REQUIRED_CHANNELS
            channel_to_remove = next((ch for ch in REQUIRED_CHANNELS if ch['channel_link'] == channel_link), None)
            REQUIRED_CHANNELS = [ch for ch in REQUIRED_CHANNELS if ch['channel_link'] != channel_link]
        else:
            global SIMPLE_LINKS
            channel_to_remove = next((ch for ch in SIMPLE_LINKS if ch['channel_link'] == channel_link), None)
            SIMPLE_LINKS = [ch for ch in SIMPLE_LINKS if ch['channel_link'] != channel_link]

        if channel_to_remove:
            # Удаляем из базы данных
            conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM channels WHERE channel_link = ?", (channel_link,))
            conn.commit()
            conn.close()

            safe_name = sanitize_text(channel_to_remove['channel_name'])
            bot.edit_message_text(
                f"""═══════════════════════════
✅ <b>УДАЛЕНО УСПЕШНО</b> ✅
═══════════════════════════

<blockquote>✅ <b>Удалено успешно!</b></blockquote>

<b>📺 ИНФОРМАЦИЯ:</b>
• Название: {safe_name}
• Ссылка: {channel_link}
• Тип: {'обязательный' if channel_type == 'required' else 'простая ссылка'}""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML'
            )
        else:
            bot.answer_callback_query(call.id, "Не найдено")

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

@bot.message_handler(commands=['checksubs'])
def check_subs_command(message):
    """Проверка подписок пользователя"""
    if message.from_user.id not in ADMIN_IDS:
        return

    msg = bot.send_message(
        message.chat.id,
        """═══════════════════════════
👥 <b>ПРОВЕРКА ПОДПИСОК</b> 👥
═══════════════════════════

<blockquote>Отправьте ID пользователя для проверки его подписок:</blockquote>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_check_subs)

def process_check_subs(message):
    """Обработка проверки подписок"""
    try:
        user_id = int(message.text.strip())
        all_subscribed, not_subscribed = check_all_subscriptions(user_id)

        if all_subscribed:
            bot.send_message(
                message.chat.id,
                f"""═══════════════════════════
✅ <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b> ✅
═══════════════════════════

<blockquote>✅ <b>Пользователь {user_id} подписан на все обязательные каналы!</b></blockquote>

<b>📊 ДОПОЛНИТЕЛЬНО:</b>
<blockquote>Всего элементов показано пользователю: <b>{len(get_all_items_for_user())}</b></blockquote>""",
                parse_mode='HTML'
            )
        else:
            channels_text = "\n".join([f"• {sanitize_text(ch['channel_name'])} ({ch['channel_link']})" for ch in not_subscribed])

            bot.send_message(
                message.chat.id,
                f"""═══════════════════════════
❌ <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b> ❌
═══════════════════════════

<blockquote>❌ <b>Пользователь {user_id} не подписан на обязательные каналы:</b></blockquote>

{channels_text}

<b>📊 ДОПОЛНИТЕЛЬНО:</b>
<blockquote>Всего элементов показано пользователю: <b>{len(get_all_items_for_user())}</b></blockquote>""",
                parse_mode='HTML'
            )

    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат ID пользователя")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "⭐ Добавить звезды" and message.from_user.id in ADMIN_IDS)
def add_stars_manual_command(message):
    """Добавление звезд вручную"""
    msg = bot.send_message(
        message.chat.id,
        """═══════════════════════════
➕ <b>ДОБАВЛЕНИЕ ЗВЕЗД</b> ➕
═══════════════════════════

<blockquote>Введите ID пользователя и количество звезд через пробел:</blockquote>

<b>📋 ПРИМЕР:</b>
<blockquote><code>123456789 100</code></blockquote>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_add_stars_manual)

def process_add_stars_manual(message):
    """Обработка добавления звезд"""
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ Неверный формат!")
            return

        user_id = int(parts[0])
        amount = int(parts[1])

        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Количество должно быть больше 0!")
            return

        conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
        cursor = conn.cursor()

        # Проверяем существование пользователя
        cursor.execute("SELECT username, full_name, stars FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

        if not user:
            bot.send_message(message.chat.id, "❌ Пользователь не найден!")
            return

        # Добавляем звезды
        cursor.execute("UPDATE users SET stars = stars + ? WHERE user_id = ?", (amount, user_id))

        # Записываем транзакцию
        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, 'admin_add', f'Добавлено администратором {message.from_user.id}'))

        conn.commit()

        # Получаем обновленные данные
        cursor.execute("SELECT stars FROM users WHERE user_id = ?", (user_id,))
        new_balance = cursor.fetchone()[0]

        conn.close()

        # Уведомляем пользователя
        try:
            safe_name = sanitize_text(user[1])
            bot.send_message(
                user_id,
                f"""═══════════════════════════
✨ <b>БОНУС НАЧИСЛЕН</b> ✨
═══════════════════════════

<blockquote>🎁 <b>Вам начислен бонус!</b></blockquote>

<b>💰 ИНФОРМАЦИЯ:</b>
<blockquote>Администратор добавил вам <b>{amount} звезд ⭐</b>
Новый баланс: {new_balance} ⭐</blockquote>

<blockquote>🎯 <b>Теперь вы можете выводить звезды!</b></blockquote>""",
                parse_mode='HTML'
            )
        except:
            pass

        safe_name = sanitize_text(user[1])
        bot.send_message(
            message.chat.id,
            f"""═══════════════════════════
✅ <b>ЗВЕЗДЫ ДОБАВЛЕНЫ</b> ✅
═══════════════════════════

<blockquote>✅ <b>Звезды успешно добавлены!</b></blockquote>

<b>👤 ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ:</b>
<blockquote>Пользователь: {safe_name} (@{user[0]})</blockquote>

<b>💰 ИНФОРМАЦИЯ О НАЧИСЛЕНИИ:</b>
<blockquote>Добавлено: +{amount} ⭐
Новый баланс: {new_balance} ⭐</blockquote>""",
            parse_mode='HTML'
        )

    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат данных!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "💰 Управление выводами" and message.from_user.id in ADMIN_IDS)
def manage_withdrawals_command(message):
    """Управление выводами"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT w.*, u.full_name, u.stars as user_balance
        FROM withdrawals w
        LEFT JOIN users u ON w.user_id = u.user_id
        WHERE w.status = 'pending'
        ORDER BY w.created_at DESC
        LIMIT 10
    ''')

    withdrawals = cursor.fetchall()
    conn.close()

    if not withdrawals:
        withdrawals_text = """═══════════════════════════
💰 <b>УПРАВЛЕНИЕ ВЫВОДАМИ</b> 💰
═══════════════════════════

<blockquote>📭 <b>Нет ожидающих заявок на вывод</b></blockquote>"""
        bot.send_message(
            message.chat.id,
            withdrawals_text,
            parse_mode='HTML'
        )
        return

    withdrawals_text = """═══════════════════════════
💰 <b>ОЖИДАЮЩИЕ ЗАЯВКИ НА ВЫВОД</b> 💰
═══════════════════════════\n\n"""

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    for w in withdrawals:
        withdrawal_id, user_id, username, amount, status, admin_message, created_at, processed_at, full_name, user_balance = w

        safe_name = sanitize_text(full_name) if full_name else f"User_{user_id}"
        withdrawals_text += f'<b>#{withdrawal_id}</b> - {amount} ⭐\n'
        withdrawals_text += f'👤 {safe_name} (ID: {user_id})\n'
        withdrawals_text += f'💰 Баланс: {user_balance} ⭐\n\n'

        keyboard.add(
            types.InlineKeyboardButton(
                f"✅ #{withdrawal_id} - {amount}⭐",
                callback_data=f"admin_approve_{withdrawal_id}"
            ),
            types.InlineKeyboardButton(
                f"❌ #{withdrawal_id}",
                callback_data=f"admin_reject_{withdrawal_id}"
            )
        )

    bot.send_message(
        message.chat.id,
        withdrawals_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_approve_'))
def admin_approve_callback(call):
    """Одобрение заявки админом"""
    try:
        withdrawal_id = int(call.data.replace('admin_approve_', ''))

        # Удаляем сообщение с кнопками
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        msg = bot.send_message(
            call.message.chat.id,
            f"""═══════════════════════════
💬 <b>ОДОБРЕНИЕ ЗАЯВКИ #{withdrawal_id}</b> 💬
═══════════════════════════

<blockquote>Введите сообщение для пользователя (или 'нет' если не нужно):</blockquote>""",
            parse_mode='HTML'
        )

        bot.register_next_step_handler(msg, process_approve_withdrawal, withdrawal_id)

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

def process_approve_withdrawal(message, withdrawal_id):
    """Обработка одобрения заявки"""
    admin_message = sanitize_text(message.text) if message.text.lower() != 'нет' else None

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT user_id, amount, username, created_at FROM withdrawals WHERE withdrawal_id = ?", (withdrawal_id,))
        withdrawal = cursor.fetchone()

        if withdrawal:
            user_id, amount, username, created_at = withdrawal

            cursor.execute('''
                UPDATE withdrawals
                SET status = 'approved', admin_message = ?, processed_at = CURRENT_TIMESTAMP
                WHERE withdrawal_id = ?
            ''', (admin_message, withdrawal_id))

            # Не возвращаем звезды при одобрении - они уже были списаны

            try:
                bot.send_message(
                    user_id,
                    f"""═══════════════════════════
✅ <b>ЗАЯВКА ОДОБРЕНА</b> ✅
═══════════════════════════

<blockquote>✅ <b>Ваша заявка на вывод одобрена!</b></blockquote>

<b>📋 ДЕТАЛИ ЗАЯВКИ:</b>
<blockquote>Сумма: {amount} ⭐
Номер заявки: #{withdrawal_id}
Дата обработки: {datetime.now().strftime('%Y-%m-%d %H:%M')}</blockquote>
{f'<b>💬 СООБЩЕНИЕ:</b>\n<blockquote>{admin_message}</blockquote>' if admin_message else ''}""",
                    parse_mode='HTML'
                )
            except:
                pass

            conn.commit()

            # Обновляем сообщение в канале
            if withdrawal_id in withdrawal_messages:
                channel_data = {
                    'withdrawal_id': withdrawal_id,
                    'user_id': user_id,
                    'username': username,
                    'amount': amount,
                    'created_at': created_at[:19] if created_at else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                withdrawal_channel.update_withdrawal_status(
                    withdrawal_messages[withdrawal_id],
                    channel_data,
                    'approved',
                    admin_message
                )

            bot.send_message(
                message.chat.id,
                f"""═══════════════════════════
✅ <b>ЗАЯВКА ОДОБРЕНА</b> ✅
═══════════════════════════

<blockquote>✅ <b>Заявка #{withdrawal_id} одобрена!</b></blockquote>""",
                parse_mode='HTML',
                reply_markup=create_admin_keyboard()
            )
        else:
            bot.send_message(message.chat.id, "❌ Заявка не найдена!")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_reject_'))
def admin_reject_callback(call):
    """Отклонение заявки админом"""
    try:
        withdrawal_id = int(call.data.replace('admin_reject_', ''))

        # Удаляем сообщение с кнопками
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        msg = bot.send_message(
            call.message.chat.id,
            f"""═══════════════════════════
💬 <b>ОТКЛОНЕНИЕ ЗАЯВКИ #{withdrawal_id}</b> 💬
═══════════════════════════

<blockquote>Введите причину отклонения:</blockquote>""",
            parse_mode='HTML'
        )

        bot.register_next_step_handler(msg, process_reject_withdrawal, withdrawal_id)

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

def process_reject_withdrawal(message, withdrawal_id):
    """Обработка отклонения заявки - НЕ ВОЗВРАЩАЕМ ЗВЕЗДЫ"""
    reject_reason = sanitize_text(message.text)

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT user_id, amount, username, created_at FROM withdrawals WHERE withdrawal_id = ?", (withdrawal_id,))
        withdrawal = cursor.fetchone()

        if withdrawal:
            user_id, amount, username, created_at = withdrawal

            cursor.execute('''
                UPDATE withdrawals
                SET status = 'rejected', admin_message = ?, processed_at = CURRENT_TIMESTAMP
                WHERE withdrawal_id = ?
            ''', (reject_reason, withdrawal_id))

            # НЕ возвращаем звезды - они сгорают при отклонении заявки

            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, ?, ?)
            ''', (user_id, 0, 'withdrawal_rejected', f'Заявка на вывод #{withdrawal_id} отклонена. Звезды не возвращаются'))

            try:
                bot.send_message(
                    user_id,
                    f"""═══════════════════════════
❌ <b>ЗАЯВКА ОТКЛОНЕНА</b> ❌
═══════════════════════════

<blockquote>❌ <b>Ваша заявка на вывод отклонена</b></blockquote>

<b>📋 ДЕТАЛИ ЗАЯВКИ:</b>
<blockquote>Сумма: {amount} ⭐
Номер заявки: #{withdrawal_id}
Дата обработки: {datetime.now().strftime('%Y-%m-%d %H:%M')}</blockquote>

<blockquote>⚠️ <b>Звезды НЕ возвращаются на баланс при отклонении</b></blockquote>

<b>💬 ПРИЧИНА:</b>
<blockquote>{reject_reason}</blockquote>""",
                    parse_mode='HTML'
                )
            except:
                pass

            conn.commit()

            # Обновляем сообщение в канале
            if withdrawal_id in withdrawal_messages:
                channel_data = {
                    'withdrawal_id': withdrawal_id,
                    'user_id': user_id,
                    'username': username,
                    'amount': amount,
                    'created_at': created_at[:19] if created_at else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                withdrawal_channel.update_withdrawal_status(
                    withdrawal_messages[withdrawal_id],
                    channel_data,
                    'rejected',
                    reject_reason
                )

            bot.send_message(
                message.chat.id,
                f"""═══════════════════════════
❌ <b>ЗАЯВКА ОТКЛОНЕНА</b> ❌
═══════════════════════════

<blockquote>❌ <b>Заявка #{withdrawal_id} отклонена!</b></blockquote>

<blockquote>⚠️ Звезды не возвращены пользователю (сгорели).</blockquote>""",
                parse_mode='HTML',
                reply_markup=create_admin_keyboard()
            )
        else:
            bot.send_message(message.chat.id, "❌ Заявка не найдена!")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('channel_approve_'))
def channel_approve_callback(call):
    """Одобрение заявки из канала"""
    try:
        withdrawal_id = int(call.data.replace('channel_approve_', ''))

        # Проверяем, является ли пользователь админом
        if call.from_user.id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для одобрения заявок")
            return

        # Удаляем клавиатуру из сообщения
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None
            )
        except:
            pass

        bot.answer_callback_query(call.id, "✅ Заявка будет одобрена через админ-панель")

        # Перенаправляем в админ-панель для завершения
        bot.send_message(
            call.from_user.id,
            f"""═══════════════════════════
🎯 <b>ОДОБРЕНИЕ ЗАЯВКИ #{withdrawal_id}</b> 🎯
═══════════════════════════

<blockquote>Перейдите в админ-панель для завершения обработки.</blockquote>""",
            parse_mode='HTML'
        )

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('channel_reject_'))
def channel_reject_callback(call):
    """Отклонение заявки из канала"""
    try:
        withdrawal_id = int(call.data.replace('channel_reject_', ''))

        # Проверяем, является ли пользователь админом
        if call.from_user.id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для отклонения заявок")
            return

        # Удаляем клавиатуру из сообщения
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None
            )
        except:
            pass

        bot.answer_callback_query(call.id, "❌ Заявка будет отклонена через админ-панель")

        # Перенаправляем в админ-панель для завершения
        bot.send_message(
            call.from_user.id,
            f"""═══════════════════════════
🎯 <b>ОТКЛОНЕНИЕ ЗАЯВКИ #{withdrawal_id}</b> 🎯
═══════════════════════════

<blockquote>Перейдите в админ-панель для завершения обработки.</blockquote>""",
            parse_mode='HTML'
        )

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "🎫 Управление чеками" and message.from_user.id in ADMIN_IDS)
def manage_checks_command(message):
    """Управление чеками"""
    checks_text = """═══════════════════════════
🎫 <b>УПРАВЛЕНИЕ ЧЕКАМИ</b> 🎫
═══════════════════════════

<blockquote><b>Что такое чеки?</b>
Чеки - это промо-коды, которые можно активировать для получения звезд.</blockquote>

<b>📝 ДОСТУПНЫЕ ДЕЙСТВИЯ:</b>
• /createcheck - Создать новый чек
• /listchecks - Список всех чеков
• /checkinfo [код] - Информация о чеке
• /deactivatecheck [код] - Деактивировать чек
• /checkstats - Статистика по чекам"""

    bot.send_message(
        message.chat.id,
        checks_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['createcheck'])
def create_check_command(message):
    """Создание чека"""
    if message.from_user.id not in ADMIN_IDS:
        return

    msg = bot.send_message(
        message.chat.id,
        """═══════════════════════════
🎫 <b>СОЗДАНИЕ ЧЕКА</b> 🎫
═══════════════════════════

<blockquote>Введите данные в формате:</blockquote>

<code>сумма_звезд количество_активаций описание(опционально)</code>

<b>📋 ПРИМЕРЫ:</b>
<blockquote><code>100 10 Приветственный бонус</code>
<code>50 5</code>
<code>500 1 Специальный приз</code></blockquote>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_create_check)

def process_create_check(message):
    """Обработка создания чека"""
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат!")
            return

        amount = int(parts[0])
        max_activations = int(parts[1])
        description = sanitize_text(' '.join(parts[2:])) if len(parts) > 2 else None

        if amount <= 0 or max_activations <= 0:
            bot.send_message(message.chat.id, "❌ Сумма и количество активаций должны быть больше 0!")
            return

        # Создаем чек
        check_code = create_check(amount, max_activations, message.from_user.id, description)

        # Формируем ссылку для активации
        try:
            bot_username = bot.get_me().username
            activation_link = f"https://t.me/{bot_username}?start=check_{check_code}"
        except:
            activation_link = f"https://t.me/ваш_бот?start=check_{check_code}"

        response_text = f"""═══════════════════════════
✅ <b>ЧЕК УСПЕШНО СОЗДАН</b> ✅
═══════════════════════════

<blockquote>✅ <b>Чек успешно создан!</b> 🎫</blockquote>

<b>📋 ИНФОРМАЦИЯ О ЧЕКЕ:</b>
<blockquote>• Код: <code>{check_code}</code>
• Сумма: <b>{amount} ⭐</b>
• Активаций: <b>{max_activations}</b>
• Описание: <b>{description or 'Не указано'}</b></blockquote>

<b>🔗 ССЫЛКА ДЛЯ АКТИВАЦИИ:</b>
<blockquote><code>{activation_link}</code></blockquote>

<b>📝 КОМАНДА ДЛЯ АКТИВАЦИИ:</b>
<blockquote><code>/activate {check_code}</code></blockquote>

<blockquote>💡 <b>Как активировать:</b>
1. Отправьте пользователю ссылку
2. Или попросите ввести команду /activate {check_code}
3. После активации пользователь получит {amount} звезд</blockquote>"""

        bot.send_message(
            message.chat.id,
            response_text,
            parse_mode='HTML'
        )

    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат чисел!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(commands=['listchecks'])
def list_checks_command(message):
    """Список всех чеков"""
    if message.from_user.id not in ADMIN_IDS:
        return

    checks = get_all_checks(20)

    if not checks:
        checks_text = """═══════════════════════════
📋 <b>СПИСОК ЧЕКОВ</b> 📋
═══════════════════════════

<blockquote>📭 <b>Список чеков пуст</b></blockquote>

<blockquote>Создайте первый чек командой /createcheck</blockquote>"""
    else:
        checks_text = """═══════════════════════════
📋 <b>СПИСОК ЧЕКОВ</b> 📋
═══════════════════════════\n\n"""

        for check in checks:
            status = "✅ Активен" if check['is_active'] else "❌ Деактивирован"
            safe_desc = sanitize_text(check['description']) if check['description'] else ""
            checks_text += f"🎫 <b>{check['check_code']}</b>\n"
            checks_text += f"   💰 {check['amount']} ⭐ | 👥 {check['current_activations']}/{check['max_activations']}\n"
            checks_text += f"   📅 {check['created_at'][:10]} | {status}\n"
            if safe_desc:
                checks_text += f"   📝 {safe_desc}\n"
            checks_text += "\n"

    bot.send_message(
        message.chat.id,
        checks_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['checkinfo'])
def check_info_command(message):
    """Информация о чеке"""
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ Укажите код чека: /checkinfo КОД")
        return

    check_code = parts[1].upper()
    check_info = get_check_info(check_code)

    if not check_info:
        bot.send_message(message.chat.id, f"❌ Чек с кодом {check_code} не найден")
        return

    status = "✅ Активен" if check_info['is_active'] else "❌ Деактивирован"
    safe_desc = sanitize_text(check_info['description']) if check_info['description'] else "Не указано"
    safe_creator = sanitize_text(check_info['creator_name']) if check_info['creator_name'] else "Неизвестно"

    check_text = f"""═══════════════════════════
🎫 <b>ИНФОРМАЦИЯ О ЧЕКЕ {check_code}</b> 🎫
═══════════════════════════

<b>📋 ОСНОВНАЯ ИНФОРМАЦИЯ:</b>
<blockquote>• Код: <code>{check_info['check_code']}</code>
• Сумма: <b>{check_info['amount']} ⭐</b>
• Активаций: <b>{check_info['current_activations']}/{check_info['max_activations']}</b>
• Статус: <b>{status}</b>
• Создал: <b>{safe_creator}</b>
• Дата создания: <b>{check_info['created_at']}</b>
• Описание: <b>{safe_desc}</b></blockquote>\n"""

    try:
        bot_username = bot.get_me().username
        activation_link = f"https://t.me/{bot_username}?start=check_{check_code}"
        check_text += f"<b>🔗 ССЫЛКА ДЛЯ АКТИВАЦИИ:</b>\n<blockquote><code>{activation_link}</code></blockquote>\n\n"
    except:
        check_text += f"<b>🔗 ССЫЛКА ДЛЯ АКТИВАЦИИ:</b>\n<blockquote><code>https://t.me/ваш_бот?start=check_{check_code}</code></blockquote>\n\n"

    check_text += f"<b>📝 КОМАНДА ДЛЯ АКТИВАЦИИ:</b>\n<blockquote><code>/activate {check_code}</code></blockquote>"

    bot.send_message(
        message.chat.id,
        check_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['deactivatecheck'])
def deactivate_check_command(message):
    """Деактивация чека"""
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ Укажите код чека: /deactivatecheck КОД")
        return

    check_code = parts[1].upper()

    # Проверяем существование чека
    check_info = get_check_info(check_code)
    if not check_info:
        bot.send_message(message.chat.id, f"❌ Чек с кодом {check_code} не найден")
        return

    if not check_info['is_active']:
        bot.send_message(message.chat.id, f"❌ Чек {check_code} уже деактивирован")
        return

    # Деактивируем чек
    deactivate_check(check_code)

    bot.send_message(
        message.chat.id,
        f"""═══════════════════════════
✅ <b>ЧЕК ДЕАКТИВИРОВАН</b> ✅
═══════════════════════════

<blockquote>✅ <b>Чек {check_code} успешно деактивирован!</b></blockquote>

<blockquote>Теперь его нельзя активировать.</blockquote>""",
        parse_mode='HTML'
    )

@bot.message_handler(commands=['checkstats'])
def check_stats_command(message):
    """Статистика по чекам"""
    if message.from_user.id not in ADMIN_IDS:
        return

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM checks")
    total_checks = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM checks WHERE is_active = 1")
    active_checks = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(amount * max_activations) FROM checks")
    total_potential = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(amount * current_activations) FROM checks")
    total_distributed = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM check_activations")
    total_activations = cursor.fetchone()[0]

    conn.close()

    stats_text = f"""═══════════════════════════
📊 <b>СТАТИСТИКА ПО ЧЕКАМ</b> 📊
═══════════════════════════

<b>🎫 ОБЩАЯ СТАТИСТИКА:</b>
<blockquote>• Всего чеков: <b>{total_checks}</b>
• Активных чеков: <b>{active_checks}</b>
• Всего активаций: <b>{total_activations}</b></blockquote>

<b>💰 РАСПРЕДЕЛЕНИЕ ЗВЕЗД:</b>
<blockquote>• Потенциально к выдаче: <b>{total_potential} ⭐</b>
• Уже выдано: <b>{total_distributed} ⭐</b>
• Осталось выдать: <b>{total_potential - total_distributed} ⭐</b></blockquote>

<b>📈 ЭФФЕКТИВНОСТЬ:</b>
<blockquote>• Процент активаций: <b>{round((total_distributed / total_potential * 100) if total_potential > 0 else 0, 1)}%</b>
• Средний чек: <b>{round(total_distributed / total_activations if total_activations > 0 else 0, 1)} ⭐</b></blockquote>"""

    bot.send_message(
        message.chat.id,
        stats_text,
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda message: message.text == "⬅️ Главное меню" and message.from_user.id in ADMIN_IDS)
def admin_back_to_main_menu(message):
    """Возврат в главное меню из админ панели"""
    bot.send_message(
        message.chat.id,
        """═══════════════════════════
🏠 <b>ГЛАВНОЕ МЕНЮ</b> 🏠
═══════════════════════════

<blockquote>🏠 <b>Вы вернулись в главное меню</b></blockquote>""",
        parse_mode='HTML',
        reply_markup=create_main_menu()
    )

# ========== ФУНКЦИИ ОСНОВНОГО БОТА ==========
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            referred_by INTEGER DEFAULT NULL,
            stars INTEGER DEFAULT 0,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referred_by) REFERENCES users(user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            type TEXT,
            description TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            withdrawal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            admin_message TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT,
            channel_username TEXT,
            channel_name TEXT NOT NULL,
            channel_link TEXT NOT NULL DEFAULT '',
            channel_type TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            added_by INTEGER,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

def load_channels_from_db():
    """Загрузка каналов из базы данных при запуске"""
    global REQUIRED_CHANNELS, SIMPLE_LINKS

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    # Сначала создаем таблицу если её нет
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT,
            channel_username TEXT,
            channel_name TEXT NOT NULL,
            channel_link TEXT NOT NULL DEFAULT '',
            channel_type TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            added_by INTEGER,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Проверяем наличие колонки channel_link
    cursor.execute("PRAGMA table_info(channels)")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]

    if 'channel_link' not in column_names:
        cursor.execute("ALTER TABLE channels ADD COLUMN channel_link TEXT NOT NULL DEFAULT ''")

    cursor.execute("SELECT channel_id, channel_username, channel_name, channel_link, channel_type FROM channels WHERE is_active = 1")
    channels = cursor.fetchall()

    for ch in channels:
        channel_data = {
            'channel_id': ch[0],
            'channel_username': ch[1],
            'channel_name': sanitize_text(ch[2]),
            'channel_link': ch[3] if ch[3] else ch[1],  # Если нет прямой ссылки, используем username
            'type': ch[4]
        }
        if ch[4] == 'required':
            REQUIRED_CHANNELS.append(channel_data)
        else:
            SIMPLE_LINKS.append(channel_data)

    conn.close()
    print(f"📺 Загружено {len(REQUIRED_CHANNELS)} обязательных каналов и {len(SIMPLE_LINKS)} простых ссылок")

def register_user(user_id, username, full_name, referrer_id=None):
    """Регистрация пользователя с проверкой дублирования реферальных начислений"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        safe_username = sanitize_text(username) if username else ""
        safe_full_name = sanitize_text(full_name) if full_name else f"User_{user_id}"

        cursor.execute('''
            INSERT INTO users (user_id, username, full_name, referred_by, stars)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, safe_username, safe_full_name, referrer_id, 0))
        conn.commit()

        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, 0, 'registration', 'Регистрация в боте'))

        conn.commit()

        if referrer_id:
            try:
                bot.send_message(
                    referrer_id,
                    f"""═══════════════════════════
✨ <b>НОВЫЙ РЕФЕРАЛ</b> ✨
═══════════════════════════

<blockquote>🎉 <b>Новый реферал зарегистрировался!</b></blockquote>

<b>👤 Информация о реферале:</b>
<blockquote>Пользователь: {safe_full_name}</blockquote>

<blockquote>📢 <b>Бонусы будут начислены после того, как пользователь подпишется на все обязательные каналы.</b></blockquote>""",
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Не удалось отправить уведомление рефереру: {e}")

    else:
        if referrer_id and not user[3]:
            cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
            current_referrer = cursor.fetchone()[0]

            if not current_referrer:
                # Обновляем реферера
                cursor.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
                conn.commit()

                safe_full_name = sanitize_text(full_name) if full_name else f"User_{user_id}"
                try:
                    bot.send_message(
                        referrer_id,
                        f"""═══════════════════════════
✨ <b>НОВЫЙ РЕФЕРАЛ</b> ✨
═══════════════════════════

<blockquote>🎉 <b>Новый реферал зарегистрировался!</b></blockquote>

<b>👤 Информация о реферале:</b>
<blockquote>Пользователь: {safe_full_name}</blockquote>

<blockquote>📢 <b>Бонусы будут начислены после того, как пользователь подпишется на все обязательные каналы.</b></blockquote>""",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    print(f"Не удалось отправить уведомление рефереру: {e}")

    conn.close()

def get_user_info(user_id):
    """Получение информации о пользователе"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT u.user_id, u.username, u.full_name, u.referred_by, u.stars,
               u.registration_date, COUNT(r.user_id) as referrals_count
        FROM users u
        LEFT JOIN users r ON u.user_id = r.referred_by
        WHERE u.user_id = ?
        GROUP BY u.user_id, u.username, u.full_name, u.referred_by, u.stars, u.registration_date
    ''', (user_id,))

    user = cursor.fetchone()
    conn.close()

    if user:
        reg_date = user[5]
        if reg_date:
            if isinstance(reg_date, str):
                reg_date_str = reg_date[:10] if len(reg_date) >= 10 else reg_date
            else:
                reg_date_str = str(reg_date)[:10]
        else:
            reg_date_str = "Неизвестно"

        safe_username = sanitize_text(user[1]) if user[1] else ""
        safe_full_name = sanitize_text(user[2]) if user[2] else f"User_{user_id}"

        return {
            'user_id': user[0],
            'username': safe_username,
            'full_name': safe_full_name,
            'referred_by': user[3],
            'stars': user[4],
            'registration_date': reg_date_str,
            'referrals_count': user[6] if user[6] else 0
        }
    return None

def create_withdrawal(user_id, username, amount):
    """Создание заявки на вывод"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("SELECT stars FROM users WHERE user_id = ?", (user_id,))
    user_stars = cursor.fetchone()

    if not user_stars or user_stars[0] < amount:
        conn.close()
        return False, "Недостаточно звезд на балансе"

    if amount < 50:
        conn.close()
        return False, "Минимальная сумма вывода: 50⭐"

    # Вставляем заявку на вывод
    safe_username = sanitize_text(username)
    cursor.execute('''
        INSERT INTO withdrawals (user_id, username, amount, status)
        VALUES (?, ?, ?, 'pending')
    ''', (user_id, safe_username, amount))

    withdrawal_id = cursor.lastrowid

    cursor.execute("UPDATE users SET stars = stars - ? WHERE user_id = ?", (amount, user_id))

    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, description)
        VALUES (?, ?, ?, ?)
    ''', (user_id, -amount, 'withdrawal', f'Заявка на вывод {amount} звезд'))

    conn.commit()

    # Получаем время создания
    cursor.execute("SELECT created_at FROM withdrawals WHERE withdrawal_id = ?", (withdrawal_id,))
    created_at = cursor.fetchone()[0]

    conn.close()

    # Отправляем уведомление в канал
    withdrawal_data = {
        'withdrawal_id': withdrawal_id,
        'user_id': user_id,
        'username': safe_username,
        'amount': amount,
        'created_at': created_at[:19] if created_at else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    # Отправляем уведомление в канал
    message_id = withdrawal_channel.send_withdrawal_notification(withdrawal_data)

    # Сохраняем ID сообщения
    if message_id:
        withdrawal_messages[withdrawal_id] = message_id

    return True, "Заявка на вывод успешно создана"

def get_user_withdrawals(user_id, limit=10):
    """Получение истории выводов пользователя"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT withdrawal_id, amount, status, created_at, processed_at, admin_message
        FROM withdrawals
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, limit))

    withdrawals = cursor.fetchall()
    conn.close()

    result = []
    for w in withdrawals:
        safe_admin_message = sanitize_text(w[5]) if w[5] else None
        result.append({
            'id': w[0],
            'amount': w[1],
            'status': w[2],
            'created_at': w[3],
            'processed_at': w[4],
            'admin_message': safe_admin_message
        })

    return result

def generate_referral_link(user_id):
    """Генерация реферальной ссылки"""
    try:
        bot_username = bot.get_me().username
        return f"https://t.me/{bot_username}?start=ref_{user_id}"
    except:
        return f"https://t.me/ваш_бот?start=ref_{user_id}"

def get_top_referrers(limit=10):
    """Получение топ пользователей ПО КОЛИЧЕСТВУ РЕФЕРАЛОВ"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    # ИСПРАВЛЕННЫЙ ЗАПРОС - получаем всех пользователей с количеством рефералов
    cursor.execute('''
        SELECT u.user_id, u.username, u.full_name, u.stars, 
               COUNT(r.user_id) as referrals_count
        FROM users u
        LEFT JOIN users r ON u.user_id = r.referred_by
        GROUP BY u.user_id, u.username, u.full_name, u.stars
        HAVING COUNT(r.user_id) > 0
        ORDER BY referrals_count DESC, u.stars DESC
        LIMIT ?
    ''', (limit,))

    top_users = cursor.fetchall()
    conn.close()

    return top_users

def get_transactions(user_id, limit=10):
    """Получение истории транзакций"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT amount, type, description, timestamp
        FROM transactions
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (user_id, limit))

    transactions = cursor.fetchall()
    conn.close()

    result = []
    for t in transactions:
        safe_desc = sanitize_text(t[2]) if t[2] else ""
        result.append({
            'amount': t[0],
            'type': t[1],
            'description': safe_desc,
            'timestamp': t[3]
        })

    return result

def create_main_menu():
    """Главное меню"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "⭐ Мой профиль",
        "🔗 Пригласить друзей",
        "💰 Вывод звезд",
        "📊 Моя статистика",
        "🏆 Топ рефереров",
        "🎫 Активировать чек",
        "📋 Мои заявки"
    ]
    keyboard.add(*buttons)
    return keyboard

def create_referral_keyboard(user_id):
    """Упрощенная клавиатура для реферальной ссылки"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    referral_link = generate_referral_link(user_id)
    share_text = "Привет! Присоединяйся к крутому боту с реферальной системой! За каждого друга дают 5 звезд! 👇"

    import urllib.parse
    encoded_text = urllib.parse.quote(share_text)

    keyboard.add(
        types.InlineKeyboardButton(
            "📱 Поделиться ссылкой",
            url=f"https://t.me/share/url?url={referral_link}&text={encoded_text}"
        )
    )

    return keyboard

def create_withdrawal_keyboard():
    """Клавиатура для вывода средств"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        types.InlineKeyboardButton("50⭐", callback_data="withdraw_50"),
        types.InlineKeyboardButton("100⭐", callback_data="withdraw_100"),
        types.InlineKeyboardButton("200⭐", callback_data="withdraw_200"),
        types.InlineKeyboardButton("500⭐", callback_data="withdraw_500"),
        types.InlineKeyboardButton("1000⭐", callback_data="withdraw_1000"),
        types.InlineKeyboardButton("Другая сумма", callback_data="withdraw_custom")
    )

    return keyboard

@bot.callback_query_handler(func=lambda call: call.data.startswith('withdraw_'))
def handle_withdrawal_callback(call):
    """Обработчик инлайн-кнопок вывода"""
    user_id = call.from_user.id
    user_info = get_user_info(user_id)

    if not user_info:
        bot.answer_callback_query(call.id, "❌ Ошибка: пользователь не найден")
        return

    action = call.data

    if action == "withdraw_custom":
        msg = bot.send_message(
            call.message.chat.id,
            """═══════════════════════════
💎 <b>ВЫВОД СРЕДСТВ</b> 💎
═══════════════════════════

<blockquote><b>💎 Введите сумму для вывода</b></blockquote>

<b>📋 ТРЕБОВАНИЯ:</b>
<blockquote>Минимальная сумма: 50 звезд
Введите число кратное 10:</blockquote>""",
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_custom_withdrawal)
        bot.answer_callback_query(call.id)
        return

    if action.startswith("withdraw_"):
        try:
            amount_str = action.replace("withdraw_", "")
            if amount_str.isdigit():
                amount = int(amount_str)
            else:
                bot.answer_callback_query(call.id, "❌ Неверная сумма")
                return
        except:
            bot.answer_callback_query(call.id, "❌ Неверная сумма")
            return

    if user_info['stars'] < amount:
        bot.answer_callback_query(
            call.id,
            f"❌ Недостаточно звезд! У вас {user_info['stars']}⭐",
            show_alert=True
        )
        return

    if amount < 50:
        bot.answer_callback_query(
            call.id,
            "❌ Минимальная сумма вывода 50 ⭐",
            show_alert=True
        )
        return

    user_data = {'amount': amount, 'user_id': user_id}

    msg = bot.send_message(
        call.message.chat.id,
        f"""═══════════════════════════
📝 <b>ПОДТВЕРЖДЕНИЕ ВЫВОДА</b> 📝
═══════════════════════════

<blockquote><b>📝 Подтверждение вывода</b></blockquote>

<b>💰 ДЕТАЛИ ВЫВОДА:</b>
<blockquote>Сумма вывода: {amount} ⭐
Ваш баланс: {user_info['stars']} ⭐
Баланс после вывода: {user_info['stars'] - amount} ⭐</blockquote>

<blockquote>✍️ <b>Введите ваш @username для связи:</b></blockquote>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_withdrawal_username, user_data)
    bot.answer_callback_query(call.id)

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = sanitize_text(message.from_user.username) if message.from_user.username else ""
    full_name = sanitize_text(message.from_user.full_name) if message.from_user.full_name else f"User_{user_id}"

    # Проверяем, активируется ли чек
    if len(message.text.split()) > 1:
        start_param = message.text.split()[1]

        if start_param.startswith('check_'):
            check_code = start_param.replace('check_', '')

            # Сначала регистрируем пользователя
            register_user(user_id, username, full_name, None)

            # Проверяем подписку на каналы
            if REQUIRED_CHANNELS:
                is_subscribed, subscription_data = check_subscription_required(user_id)
                if not is_subscribed:
                    channels_text, keyboard = subscription_data
                    bot.send_message(
                        message.chat.id,
                        channels_text,
                        parse_mode='HTML',
                        reply_markup=keyboard
                    )
                    return
                else:
                    check_and_award_referral_bonus(user_id)

            # Активируем чек
            success, result_message = activate_check(check_code, user_id)

            if success:
                user_info = get_user_info(user_id)
                if user_info:
                    bot.send_message(
                        message.chat.id,
                        f"""═══════════════════════════
✅ <b>ЧЕК АКТИВИРОВАН</b> ✅
═══════════════════════════

<blockquote>✅ <b>Чек активирован успешно!</b> 🎉</blockquote>

<b>💰 НАЧИСЛЕНИЕ:</b>
<blockquote>Получено: {result_message.split('! Получено ')[1]}
Ваш баланс: {user_info['stars']} звезд</blockquote>

<blockquote>🎯 <b>Теперь вы можете выводить звезды!</b></blockquote>""",
                        parse_mode='HTML'
                    )
                else:
                    bot.send_message(
                        message.chat.id,
                        f"""═══════════════════════════
✅ <b>ЧЕК АКТИВИРОВАН</b> ✅
═══════════════════════════

<blockquote>✅ {result_message}</blockquote>""",
                        parse_mode='HTML'
                    )
            else:
                bot.send_message(
                    message.chat.id,
                    f"""═══════════════════════════
❌ <b>ОШИБКА АКТИВАЦИИ</b> ❌
═══════════════════════════

<blockquote>❌ <b>Не удалось активировать чек:</b></blockquote>

{result_message}""",
                    parse_mode='HTML'
                )

            # Показываем главное меню
            bot.send_message(
                message.chat.id,
                """═══════════════════════════
🏠 <b>ГЛАВНОЕ МЕНЮ</b> 🏠
═══════════════════════════

<blockquote>🏠 <b>Добро пожаловать!</b></blockquote>

Выберите действие из меню ниже:""",
                parse_mode='HTML',
                reply_markup=create_main_menu()
            )
            return

        elif start_param.startswith('ref_'):
            referrer_id = None
            try:
                referrer_id = int(start_param.split('_')[1])
                if referrer_id == user_id:
                    referrer_id = None
                else:
                    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
                    referrer_exists = cursor.fetchone()
                    conn.close()

                    if not referrer_exists:
                        referrer_id = None
            except ValueError:
                referrer_id = None

            register_user(user_id, username, full_name, referrer_id)

            # После регистрации проверяем подписку на каналы
            if REQUIRED_CHANNELS:
                is_subscribed, subscription_data = check_subscription_required(user_id)
                if not is_subscribed:
                    channels_text, keyboard = subscription_data
                    bot.send_message(
                        message.chat.id,
                        channels_text,
                        parse_mode='HTML',
                        reply_markup=keyboard
                    )
                    return
                else:
                    check_and_award_referral_bonus(user_id)

                    welcome_text = f"""═══════════════════════════
✨ <b>ДОБРО ПОЖАЛОВАТЬ</b> ✨
═══════════════════════════

<blockquote>✨ <b>Добро пожаловать, {full_name}!</b></blockquote>

<blockquote><b>Добро пожаловать в премиум бот с реферальной системой!</b></blockquote>

<blockquote>✅ <b>Вы уже подписаны на все обязательные каналы!</b></blockquote>

<b>👇 НАВИГАЦИЯ:</b>
<blockquote>Используйте кнопки ниже для навигации:</blockquote>"""

                    bot.send_message(
                        message.chat.id,
                        welcome_text,
                        parse_mode='HTML',
                        reply_markup=create_main_menu()
                    )
                    return

        else:
            register_user(user_id, username, full_name, None)
    else:
        register_user(user_id, username, full_name, None)

    # ПРОВЕРКА ПОДПИСКИ НА КАНАЛЫ ДЛЯ ВСЕХ НОВЫХ ПОЛЬЗОВАТЕЛЕЙ
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(user_id)

        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return
        else:
            check_and_award_referral_bonus(user_id)

    welcome_text = f"""═══════════════════════════
✨ <b>ДОБРО ПОЖАЛОВАТЬ</b> ✨
═══════════════════════════

<blockquote>✨ <b>Добро пожаловать, {full_name}!</b></blockquote>

<blockquote><b>Добро пожаловать в премиум бот с реферальной системой!</b></blockquote>

<b>🌟 КАК РАБОТАЕТ СИСТЕМА:</b>
<blockquote>1️⃣ Приглашайте друзей по своей реферальной ссылке
2️⃣ За каждого приглашенного друга получайте <b>+5 звезд</b> (только после подписки реферала на все обязательные каналы)
3️⃣ Ваш друг тоже получает <b>+1 звезду</b> за регистрацию
4️⃣ Выводите звезды от <b>50</b> и более!
5️⃣ Активируйте чеки для получения бонусных звезд!</blockquote>

<b>👇 НАВИГАЦИЯ:</b>
<blockquote>Используйте кнопки ниже для навигации:</blockquote>"""

    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode='HTML',
        reply_markup=create_main_menu()
    )

@bot.message_handler(func=lambda message: message.text == "⭐ Мой профиль")
def profile_command(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    user_info = get_user_info(message.from_user.id)

    if user_info:
        referral_link = generate_referral_link(message.from_user.id)
        username_display = f"@{user_info['username']}" if user_info['username'] else "не указан"

        profile_text = f"""═══════════════════════════
👤 <b>ВАШ ПРОФИЛЬ</b> 👤
═══════════════════════════

<b>👤 ЛИЧНАЯ ИНФОРМАЦИЯ:</b>
<blockquote>Имя: {user_info['full_name']}
Username: {username_display}
ID: {user_info['user_id']}</blockquote>

<b>⭐ ФИНАНСОВАЯ ИНФОРМАЦИЯ:</b>
<blockquote>Баланс звезд: <b>{user_info['stars']} ⭐</b>
Приглашено друзей: {user_info['referrals_count']}
Заработано с рефералов: {user_info['referrals_count'] * 5} ⭐
Дата регистрации: {user_info['registration_date']}</blockquote>

<b>🔗 РЕФЕРАЛЬНАЯ ССЫЛКА:</b>
<blockquote><code>{referral_link}</code></blockquote>

<b>💸 ВЫВОД СРЕДСТВ:</b>
<blockquote>Доступно для вывода: {user_info['stars']} ⭐
Минимальный вывод: 50 ⭐</blockquote>

<blockquote>🎯 <b>Делитесь ссылкой и зарабатывайте звезды!</b></blockquote>"""

        bot.send_message(
            message.chat.id,
            profile_text,
            parse_mode='HTML',
            reply_markup=create_referral_keyboard(message.from_user.id)
        )

@bot.message_handler(func=lambda message: message.text == "🔗 Пригласить друзей")
def invite_command(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    user_info = get_user_info(message.from_user.id)

    if user_info:
        referral_link = generate_referral_link(message.from_user.id)

        referrals_count = user_info['referrals_count']
        if referrals_count % 5 == 0:
            next_reward = 5
        else:
            next_reward = 5 - (referrals_count % 5)

        invite_text = f"""═══════════════════════════
🎁 <b>ПРИГЛАСИТЬ ДРУЗЕЙ</b> 🎁
═══════════════════════════

<blockquote>🎁 <b>Пригласите друга и получите 5 звезд!</b> 🎁</blockquote>

<b>🔗 РЕФЕРАЛЬНАЯ ССЫЛКА:</b>
<blockquote><code>{referral_link}</code></blockquote>

<b>📊 СТАТИСТИКА ПРИГЛАШЕНИЙ:</b>
<blockquote>✅ Приглашено: {referrals_count} друзей
⭐ Заработано звезд: {referrals_count * 5} ⭐
🎯 До следующей награды: {next_reward} друзей</blockquote>

<b>💸 ФИНАНСОВАЯ ИНФОРМАЦИЯ:</b>
<blockquote>💰 Заработано на вывод: {user_info['stars']} ⭐
💸 Минимальный вывод: 50 ⭐</blockquote>

<blockquote>💬 <b>Сообщение для друга:</b>
"Привет! Перейди по этой ссылке и нажми START - получишь бонусную звезду, а я заработаю 5 звезд!"</blockquote>"""

        bot.send_message(
            message.chat.id,
            invite_text,
            parse_mode='HTML',
            reply_markup=create_referral_keyboard(message.from_user.id)
        )

@bot.message_handler(func=lambda message: message.text == "💰 Вывод звезд")
def withdrawal_command(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    user_info = get_user_info(message.from_user.id)

    if not user_info:
        bot.send_message(message.chat.id, "❌ Ошибка: пользователь не найден")
        return

    withdrawal_text = f"""═══════════════════════════
💰 <b>ВЫВОД ЗВЕЗД</b> 💰
═══════════════════════════

<blockquote><b>💰 Вывод звезд</b></blockquote>

<b>⭐ ИНФОРМАЦИЯ О БАЛАНСЕ:</b>
<blockquote>Ваш текущий баланс: {user_info['stars']} ⭐
Минимальная сумма вывода: 50 ⭐
Время обработки: до 24 часов
Необходимо указать: Ваш username для связи</blockquote>

<blockquote>👇 <b>Выберите сумму для вывода:</b></blockquote>"""

    bot.send_message(
        message.chat.id,
        withdrawal_text,
        parse_mode='HTML',
        reply_markup=create_withdrawal_keyboard()
    )

def process_custom_withdrawal(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    try:
        amount = int(message.text)

        if amount < 50:
            bot.send_message(
                message.chat.id,
                """═══════════════════════════
❌ <b>ОШИБКА ВЫВОДА</b> ❌
═══════════════════════════

<blockquote>❌ <b>Минимальная сумма вывода 50 ⭐!</b></blockquote>""",
                parse_mode='HTML'
            )
            return

        if amount % 10 != 0:
            bot.send_message(
                message.chat.id,
                """═══════════════════════════
❌ <b>ОШИБКА ВЫВОДА</b> ❌
═══════════════════════════

<blockquote>❌ <b>Сумма должна быть кратной 10!</b></blockquote>""",
                parse_mode='HTML'
            )
            return

        user_info = get_user_info(message.from_user.id)

        if not user_info:
            bot.send_message(message.chat.id, "❌ Ошибка: пользователь не найден")
            return

        if user_info['stars'] < amount:
            bot.send_message(
                message.chat.id,
                f"""═══════════════════════════
❌ <b>ОШИБКА ВЫВОДА</b> ❌
═══════════════════════════

<blockquote>❌ <b>Недостаточно звезд!</b></blockquote>

<b>💰 ДЕТАЛИ:</b>
<blockquote>Вы хотите вывести: {amount} ⭐
Ваш баланс: {user_info['stars']} ⭐
Не хватает: {amount - user_info['stars']} ⭐</blockquote>""",
                parse_mode='HTML'
            )
            return

        user_data = {'amount': amount, 'user_id': message.from_user.id}

        msg = bot.send_message(
            message.chat.id,
            f"""═══════════════════════════
📝 <b>ПОДТВЕРЖДЕНИЕ ВЫВОДА</b> 📝
═══════════════════════════

<blockquote><b>📝 Подтверждение вывода</b></blockquote>

<b>💰 ДЕТАЛИ ВЫВОДА:</b>
<blockquote>Сумма вывода: {amount} ⭐
Ваш баланс: {user_info['stars']} ⭐
Баланс после вывода: {user_info['stars'] - amount} ⭐</blockquote>

<blockquote>✍️ <b>Введите ваш @username для связи:</b></blockquote>""",
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_withdrawal_username, user_data)

    except ValueError:
        bot.send_message(
            message.chat.id,
            """═══════════════════════════
❌ <b>ОШИБКА ВВОДА</b> ❌
═══════════════════════════

<blockquote>❌ <b>Пожалуйста, введите число!</b></blockquote>""",
            parse_mode='HTML'
        )

def process_withdrawal_username(message, user_data):
    username = sanitize_text(message.text.strip())

    if username.startswith('@'):
        username = username[1:]

    if not username or username == '':
        bot.send_message(
            message.chat.id,
            """═══════════════════════════
❌ <b>ОШИБКА ВВОДА</b> ❌
═══════════════════════════

<blockquote>❌ <b>Пожалуйста, укажите ваш @username!</b></blockquote>""",
            parse_mode='HTML'
        )
        return

    amount = user_data['amount']
    user_id = user_data['user_id']

    success, message_text = create_withdrawal(user_id, username, amount)

    if success:
        user_info = get_user_info(user_id)

        bot.send_message(
            message.chat.id,
            f"""═══════════════════════════
✅ <b>ЗАЯВКА СОЗДАНА</b> ✅
═══════════════════════════

<blockquote>✅ <b>Заявка на вывод создана!</b></blockquote>

<b>📋 ДЕТАЛИ ЗАЯВКИ:</b>
<blockquote>• Сумма: <b>{amount} ⭐</b>
• Username: <b>@{username}</b>
• Ваш баланс: <b>{user_info['stars']} ⭐</b>
• Статус: <b>⏳ На рассмотрении</b></blockquote>

<b>⏱️ ИНФОРМАЦИЯ:</b>
<blockquote>Время обработки: до 24 часов
С вами свяжутся: @{username}</blockquote>

<blockquote>🎯 <b>Следите за статусом заявки в разделе "Мои заявки"</b></blockquote>""",
            parse_mode='HTML',
            reply_markup=create_main_menu()
        )
    else:
        bot.send_message(
            message.chat.id,
            f"""═══════════════════════════
❌ <b>ОШИБКА СОЗДАНИЯ</b> ❌
═══════════════════════════

<blockquote>❌ <b>Ошибка!</b></blockquote>

{message_text}""",
            parse_mode='HTML',
            reply_markup=create_main_menu()
        )

@bot.message_handler(func=lambda message: message.text == "🎫 Активировать чек")
def activate_check_menu_command(message):
    """Активация чека из меню"""
    user_id = message.from_user.id

    # Проверка подписки на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(user_id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    msg = bot.send_message(
        message.chat.id,
        """═══════════════════════════
🎫 <b>АКТИВАЦИЯ ЧЕКА</b> 🎫
═══════════════════════════

<blockquote>Введите код чека:</blockquote>

<b>📋 ПРИМЕР:</b>
<blockquote><code>ABC123XY</code></blockquote>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_activate_check_menu)

def process_activate_check_menu(message):
    """Обработка активации чека из меню"""
    user_id = message.from_user.id
    check_code = sanitize_text(message.text.strip().upper())

    if not check_code:
        bot.send_message(
            message.chat.id,
            """═══════════════════════════
❌ <b>ОШИБКА ВВОДА</b> ❌
═══════════════════════════

<blockquote>❌ <b>Введите код чека!</b></blockquote>""",
            parse_mode='HTML'
        )
        return

    # Активируем чек
    success, result_message = activate_check(check_code, user_id)

    if success:
        user_info = get_user_info(user_id)
        if user_info:
            bot.send_message(
                message.chat.id,
                f"""═══════════════════════════
✅ <b>ЧЕК АКТИВИРОВАН</b> ✅
═══════════════════════════

<blockquote>✅ <b>Чек активирован успешно!</b> 🎉</blockquote>

<b>💰 НАЧИСЛЕНИЕ:</b>
<blockquote>Получено: {result_message.split('! Получено ')[1]}
Ваш новый баланс: {user_info['stars']} звезд</blockquote>

<blockquote>🎯 <b>Теперь вы можете выводить звезды!</b></blockquote>""",
                parse_mode='HTML',
                reply_markup=create_main_menu()
            )
        else:
            bot.send_message(
                message.chat.id,
                f"""═══════════════════════════
✅ <b>ЧЕК АКТИВИРОВАН</b> ✅
═══════════════════════════

<blockquote>✅ {result_message}</blockquote>""",
                parse_mode='HTML',
                reply_markup=create_main_menu()
            )
    else:
        bot.send_message(
            message.chat.id,
            f"""═══════════════════════════
❌ <b>ОШИБКА АКТИВАЦИИ</b> ❌
═══════════════════════════

<blockquote>❌ <b>Не удалось активировать чек:</b></blockquote>

{result_message}""",
            parse_mode='HTML',
            reply_markup=create_main_menu()
        )

@bot.message_handler(commands=['activate'])
def activate_check_command(message):
    """Активация чека пользователем"""
    user_id = message.from_user.id

    # Проверка подписки на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(user_id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(
            message.chat.id,
            """═══════════════════════════
🎫 <b>АКТИВАЦИЯ ЧЕКА</b> 🎫
═══════════════════════════

<blockquote>Использование: <code>/activate КОД_ЧЕКА</code></blockquote>

<b>📋 ПРИМЕР:</b>
<blockquote><code>/activate ABC123XY</code></blockquote>""",
            parse_mode='HTML'
        )
        return

    check_code = parts[1].upper()

    # Активируем чек
    success, result_message = activate_check(check_code, user_id)

    if success:
        user_info = get_user_info(user_id)
        if user_info:
            bot.send_message(
                message.chat.id,
                f"""═══════════════════════════
✅ <b>ЧЕК АКТИВИРОВАН</b> ✅
═══════════════════════════

<blockquote>✅ <b>Чек активирован успешно!</b> 🎉</blockquote>

<b>💰 НАЧИСЛЕНИЕ:</b>
<blockquote>Получено: {result_message.split('! Получено ')[1]}
Ваш новый баланс: {user_info['stars']} звезд</blockquote>

<blockquote>🎯 <b>Теперь вы можете выводить звезды!</b></blockquote>""",
                parse_mode='HTML'
            )
        else:
            bot.send_message(
                message.chat.id,
                f"""═══════════════════════════
✅ <b>ЧЕК АКТИВИРОВАН</b> ✅
═══════════════════════════

<blockquote>✅ {result_message}</blockquote>""",
                parse_mode='HTML'
            )
    else:
        bot.send_message(
            message.chat.id,
            f"""═══════════════════════════
❌ <b>ОШИБКА АКТИВАЦИИ</b> ❌
═══════════════════════════

<blockquote>❌ <b>Не удалось активировать чек:</b></blockquote>

{result_message}""",
            parse_mode='HTML'
        )

@bot.message_handler(func=lambda message: message.text == "📋 Мои заявки")
def my_withdrawals_command(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    user_id = message.from_user.id
    withdrawals = get_user_withdrawals(user_id, 10)

    if not withdrawals:
        withdrawals_text = """═══════════════════════════
📋 <b>МОИ ЗАЯВКИ НА ВЫВОД</b> 📋
═══════════════════════════

<blockquote>У вас еще нет заявок на вывод.</blockquote>

<b>💰 СОЗДАНИЕ ПЕРВОЙ ЗАЯВКИ:</b>
<blockquote>1. Нажмите "💰 Вывод звезд"
2. Выберите сумму (от 50 звезд)
3. Укажите ваш @username
4. Ожидайте подтверждения от администратора</blockquote>"""
    else:
        withdrawals_text = """═══════════════════════════
📋 <b>МОИ ЗАЯВКИ НА ВЫВОД</b> 📋
═══════════════════════════\n\n"""

        for i, w in enumerate(withdrawals, 1):
            status_emoji = "⏳" if w['status'] == 'pending' else "✅" if w['status'] == 'approved' else "❌"
            status_text = "На рассмотрении" if w['status'] == 'pending' else "Одобрено" if w['status'] == 'approved' else "Отклонено"

            created_date = w['created_at'][:10] if w['created_at'] and len(w['created_at']) >= 10 else "Неизвестно"

            withdrawals_text += f'{i}. <b>{w["amount"]} ⭐</b> - {status_emoji} <b>{status_text}</b>\n'
            withdrawals_text += f'   📅 {created_date} | 🆔 #{w["id"]}\n'

            if w['admin_message']:
                withdrawals_text += f'   💬 {w["admin_message"]}\n'

            withdrawals_text += '\n'

        withdrawals_text += '<b>💡 СТАТУСЫ:</b>\n<blockquote>⏳ - На рассмотрении\n✅ - Одобрено\n❌ - Отклонено</blockquote>'

    bot.send_message(
        message.chat.id,
        withdrawals_text,
        parse_mode='HTML',
        reply_markup=create_main_menu()
    )

@bot.message_handler(func=lambda message: message.text == "📊 Моя статистика")
def stats_command(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    user_info = get_user_info(message.from_user.id)
    transactions = get_transactions(message.from_user.id, 5)
    withdrawals = get_user_withdrawals(message.from_user.id, 3)

    if user_info:
        referrals_count = user_info['referrals_count']
        if referrals_count > 0:
            avg_earnings = user_info['stars'] / referrals_count
        else:
            avg_earnings = 0

        total_withdrawn = 0
        pending_withdrawals = 0
        for w in withdrawals:
            if w['status'] == 'approved':
                total_withdrawn += w['amount']
            elif w['status'] == 'pending':
                pending_withdrawals += w['amount']

        stats_text = f"""═══════════════════════════
📊 <b>ВАША СТАТИСТИКА</b> 📊
═══════════════════════════

<b>⭐ ОБЩАЯ ИНФОРМАЦИЯ:</b>
<blockquote>Всего звезд: {user_info['stars']} ⭐
Приглашено друзей: {referrals_count}
Заработано с рефералов: {referrals_count * 5} ⭐
Средний заработок: {avg_earnings:.1f} ⭐ за друга</blockquote>

<b>💸 СТАТИСТИКА ВЫВОДОВ:</b>
<blockquote>• Выведено: {total_withdrawn} ⭐
• На рассмотрении: {pending_withdrawals} ⭐
• Доступно для вывода: {user_info['stars']} ⭐</blockquote>\n"""

        progress = min(user_info['stars'], 50)
        bar_length = 10
        filled = int(progress / 50 * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)
        stats_text += f"<b>🎯 ПРОГРЕСС ДО 50 ЗВЕЗД:</b>\n<blockquote>{bar} {progress}/50 ⭐</blockquote>\n\n"

        stats_text += "<b>🔄 ПОСЛЕДНИЕ ОПЕРАЦИИ:</b>\n<blockquote>"

        if transactions:
            for i, trans in enumerate(transactions, 1):
                amount = trans['amount'] if trans['amount'] else 0
                trans_type = trans['type'] or ""
                desc = trans['description'] or ""
                time_str = str(trans['timestamp'])[:16] if trans['timestamp'] else ""

                if amount > 0:
                    amount_str = f"+{amount} ⭐"
                    emoji = "🔼"
                elif amount < 0:
                    amount_str = f"{amount} ⭐"
                    emoji = "🔽"
                else:
                    amount_str = "0 ⭐"
                    emoji = "⚪"

                stats_text += f'\n{emoji} <b>{amount_str}</b> - {desc}\n   <i>{time_str}</i>\n'
        else:
            stats_text += "Операций пока нет"

        stats_text += '</blockquote>\n\n<blockquote>🎯 <b>Цель: накопить 50 звезд для вывода!</b></blockquote>'

        bot.send_message(
            message.chat.id,
            stats_text,
            parse_mode='HTML'
        )

@bot.message_handler(func=lambda message: message.text == "🏆 Топ рефереров")
def top_command(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    top_users = get_top_referrers(10)

    if top_users:
        top_text = """═══════════════════════════
🏆 <b>ТОП 10 РЕФЕРЕРОВ</b> 🏆
═══════════════════════════

<blockquote><b>🏆 Топ 10 рефереров (по количеству приглашенных друзей)</b></blockquote>\n\n"""

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

        for i, user in enumerate(top_users):
            if i < len(medals):
                medal = medals[i]
            else:
                medal = f"{i+1}."

            safe_username = sanitize_text(user[1]) if user[1] else ""
            safe_full_name = sanitize_text(user[2]) if user[2] else f"User_{user[0]}"

            username = f"@{safe_username}" if safe_username else safe_full_name
            stars = user[3] if user[3] else 0
            referrals = user[4] if user[4] else 0

            top_text += f'{medal} <b>{username}</b>\n<b>👥 Рефералов:</b> {referrals} | <b>⭐ Звезд:</b> {stars}\n\n'

        bot.send_message(
            message.chat.id,
            top_text,
            parse_mode='HTML'
        )
    else:
        bot.send_message(
            message.chat.id,
            """═══════════════════════════
🏆 <b>ТОП РЕФЕРЕРОВ</b> 🏆
═══════════════════════════

<blockquote>🏆 <b>Топ рефереров</b></blockquote>

<blockquote>Пока никто не пригласил друзей. Будьте первым!</blockquote>""",
            parse_mode='HTML'
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("copy_link_"))
def copy_link_callback(call):
    """Обработка кнопки копирования ссылки"""
    if call.data.startswith("copy_link_"):
        user_id = call.data.replace("copy_link_", "")
        try:
            user_id = int(user_id)
            referral_link = generate_referral_link(user_id)

            bot.answer_callback_query(
                call.id,
                f"Ссылка скопирована в буфер обмена! Отправьте ее другу.",
                show_alert=False
            )

            bot.send_message(
                call.message.chat.id,
                f"""═══════════════════════════
📋 <b>КОПИРОВАНИЕ ССЫЛКИ</b> 📋
═══════════════════════════

<blockquote><b>📋 Ваша ссылка для копирования:</b></blockquote>

<blockquote><code>{referral_link}</code></blockquote>

<blockquote>💡 <b>Скопируйте и отправьте другу</b></blockquote>""",
                parse_mode='HTML'
            )
        except ValueError:
            bot.answer_callback_query(call.id, "Ошибка при обработке ссылки", show_alert=True)

@bot.message_handler(commands=['invite'])
def invite_link_command(message):
    user_id = message.from_user.id
    referral_link = generate_referral_link(user_id)

    invite_text = f"""═══════════════════════════
🔗 <b>РЕФЕРАЛЬНАЯ ССЫЛКА</b> 🔗
═══════════════════════════

<blockquote><b>🔗 Ваша реферальная ссылка:</b></blockquote>

<blockquote><code>{referral_link}</code></blockquote>"""

    bot.send_message(
        message.chat.id,
        invite_text,
        parse_mode='HTML',
        reply_markup=create_referral_keyboard(user_id)
    )

@bot.message_handler(commands=['withdraw'])
def withdraw_link_command(message):
    withdrawal_command(message)

@bot.message_handler(commands=['profile'])
def profile_link_command(message):
    profile_command(message)

@bot.message_handler(commands=['top'])
def top_link_command(message):
    top_command(message)

@bot.message_handler(commands=['stats'])
def stats_link_command(message):
    stats_command(message)

@bot.message_handler(commands=['mywithdrawals'])
def my_withdrawals_link_command(message):
    my_withdrawals_command(message)

def send_daily_notifications():
    """Функция для отправки уведомлений"""
    while True:
        try:
            conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users")
            users = cursor.fetchall()

            for user_tuple in users:
                try:
                    user_id = user_tuple[0]
                    user_info = get_user_info(user_id)
                    if user_info and user_info['stars'] >= 50:
                        bot.send_message(
                            user_id,
                            f"""═══════════════════════════
💰 <b>ДОСТАТОЧНО ЗВЕЗД</b> 💰
═══════════════════════════

<blockquote><b>💰 У вас достаточно звезд для вывода!</b></blockquote>

<b>⭐ ИНФОРМАЦИЯ О БАЛАНСЕ:</b>
<blockquote>Ваш баланс: {user_info['stars']} ⭐
Минимальная сумма вывода: 50 ⭐</blockquote>

<blockquote>🎯 <b>Вы можете вывести свои звезды!</b>
Нажмите "💰 Вывод звезд" в меню</blockquote>""",
                            parse_mode='HTML'
                        )
                except:
                    continue

            conn.close()
        except Exception as e:
            print(f"Ошибка в потоке уведомлений: {e}")

        time.sleep(24 * 3600)

# ========== WEBHOOK НАСТРОЙКИ ==========
@app.route('/')
def index():
    return "✅ Бот работает! Используются вебхуки."

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        return 'Bad request', 400

def set_webhook():
    """Установка вебхука"""
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=f"{WEBHOOK_URL}{WEBHOOK_PATH}")
        print(f"✅ Вебхук установлен: {WEBHOOK_URL}{WEBHOOK_PATH}")
    except Exception as e:
        print(f"❌ Ошибка установки вебхука: {e}")

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 ЗВЕЗДНЫЙ РЕФЕРАЛЬНЫЙ БОТ (ВЕБХУКИ)")
    print("=" * 50)

    init_db()
    init_checks_db()
    load_channels_from_db()

    try:
        bot_info = bot.get_me()
        print(f"👤 Имя бота: @{bot_info.username}")
        print(f"🌐 Вебхук URL: {WEBHOOK_URL}{WEBHOOK_PATH}")
        print(f"📺 Обязательных каналов: {len(REQUIRED_CHANNELS)}")
        print(f"🔗 Простых ссылок: {len(SIMPLE_LINKS)}")
        print(f"👑 Админов: {len(ADMIN_IDS)}")

        # Устанавливаем вебхук
        set_webhook()

    except Exception as e:
        print(f"⚠️ Не удалось получить информацию о боте: {e}")

    print("=" * 50)

    # Запускаем Flask сервер
    app.run(host='0.0.0.0', port=PORT)
