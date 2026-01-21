import telebot
from telebot import types
import json
from datetime import datetime
import re
# ДОБАВЬТЕ ЭТИ ИМПОРТЫ:
import os
from flask import Flask, request
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Импортируем только нужные модули
from leaders import register_leaders_handlers, leaders_start
import mines
import tower
import crash
import leaders
from referrals import register_referrals_handlers, add_referral_bonus, process_referral_join, send_referral_welcome_message, send_referral_notification_to_referrer
from states import register_stats_handlers, stats_manager
from admin_panel import register_admin_handlers
from game_stats_handler import init_stats_handler
from games import register_games_handlers

# ИМПОРТИРУЕМ НОВЫЙ МОДУЛЬ ПЛАТЕЖЕЙ
try:
    from payments import register_crypto_handlers
    PAYMENTS_ENABLED = True
    print("✅ Модуль платежей успешно импортирован")
except ImportError as e:
    PAYMENTS_ENABLED = False
    print(f"⚠️ Модуль платежей не найден: {e}")
    print("⚠️ Функции пополнения и вывода будут недоступны")

bot = telebot.TeleBot("8346191757:AAFFh6fM7sAuuAs1L_q2Di_T1QFMehWld6c")

# ==== КОНФИГУРАЦИЯ ВЕБХУКА ДЛЯ RENDER ====
# ДОЛЖНО БЫТЬ ПОСЛЕ СОЗДАНИЯ БОТА!

# 1. Вариант: Использовать Render автоматически
RENDER = os.environ.get('RENDER', False)

if RENDER:
    # На Render
    WEBHOOK_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'ваш-проект.onrender.com')
else:
    # Для локального тестирования
    WEBHOOK_HOST = 'localhost'

WEBHOOK_PORT = 443 if RENDER else 8443
WEBHOOK_LISTEN = '0.0.0.0'
WEBHOOK_URL_BASE = f"https://{WEBHOOK_HOST}"
WEBHOOK_URL_PATH = f"/webhook/{bot.token}/"

# Создаем Flask приложение
app = Flask(__name__)

# Регистрируем хендлеры из модулей
leaders.register_leaders_handlers(bot)
mines.register_mines_handlers(bot)
tower.register_tower_handlers(bot)
register_referrals_handlers(bot)
register_admin_handlers(bot)
register_games_handlers(bot)

# Регистрируем хендлеры платежей если модуль доступен
if PAYMENTS_ENABLED:
    register_crypto_handlers(bot)
    print("✅ Хендлеры платежей зарегистрированы")
else:
    print("⚠️ Хендлеры платежей НЕ зарегистрированы")

def load_users_data():
    try:
        with open('users_data.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_users_data(data):
    with open('users_data.json', 'w') as f:
        json.dump(data, f, indent=2)

def get_user_avatar(user_id):
    """Получает URL аватарки пользователя"""
    try:
        photos = bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            # Получаем file_id самой большой аватарки
            file_id = photos.photos[0][-1].file_id
            return file_id
    except Exception as e:
        print(f"Ошибка получения аватарки: {e}")
    return None

def main_menu():
    """Главное меню с обычными кнопками - ТОЛЬКО ДЛЯ ЛИЧНЫХ ЧАТОВ"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("🔥 Профиль"), types.KeyboardButton("👥 Рефералы"))
    markup.row(types.KeyboardButton("🏆 ТОП Игроков"))
    markup.row(types.KeyboardButton("🎮 Игры"))
    markup.row(types.KeyboardButton("ℹ️ О проекте"))
    return markup

def games_inline_menu(user_id):
    """Инлайн-меню для игр с балансом пользователя"""
    users_data = load_users_data()
    user_info = users_data.get(user_id, {})
    balance = user_info.get('balance', 0)
    balance_rounded = round(balance, 2)

    markup = types.InlineKeyboardMarkup(row_width=2)

    # Баланс в блоке
    balance_text = f"""
<blockquote>
💎 <b>Баланс:</b> {balance_rounded}₽
</blockquote>
"""

    # Первая строка - 2 кнопки
    markup.row(
        types.InlineKeyboardButton("💣 Мины", callback_data="game_mines"),
        types.InlineKeyboardButton("🏰 Башня", callback_data="game_tower")
    )

    # Вторая строка - 2 кнопки
    markup.row(
        types.InlineKeyboardButton("🚀 Краш", callback_data="game_crash"),
        types.InlineKeyboardButton("🎯 Дартс", callback_data="games_darts")
    )

    # Третья строка - 2 кнопки
    markup.row(
        types.InlineKeyboardButton("🏀 Баскетбол", callback_data="games_basketball"),
        types.InlineKeyboardButton("⚽ Футбол", callback_data="games_football")
    )

    # Четвертая строка - 1 кнопка по центру
    markup.row(types.InlineKeyboardButton("🎲 Кости", callback_data="games_dice"))

    return balance_text, markup

def is_private_chat(message):
    """Проверяет, что сообщение из личного чата"""
    return message.chat.type == 'private'

@bot.message_handler(commands=['start'])
def start_message(message):
    users_data = load_users_data()
    user_id = str(message.from_user.id)
    user_first_name = message.from_user.first_name or "Игрок"
    user_username = f"@{message.from_user.username}" if message.from_user.username else user_first_name

    is_new_user = user_id not in users_data
    is_referral_join = False
    referrer_data = None
    referral_code = None

    print(f"=== НАЧАЛО ОБРАБОТКИ /start ===")
    print(f"User ID: {user_id}")
    print(f"Is new user: {is_new_user}")

    # Обработка реферальной ссылки
    if len(message.text.split()) > 1:
        referral_code = message.text.split()[1]
        print(f"Referral code from URL: {referral_code}")

        # ВАЖНОЕ ИЗМЕНЕНИЕ: Обрабатываем реферала ТОЛЬКО если это новый пользователь
        if is_new_user:
            # Подготавливаем данные пользователя
            user_data = {
                'first_name': message.from_user.first_name,
                'username': message.from_user.username,
                'balance': 0.0,
                'referral_bonus': 0.0,
                'total_referral_income': 0.0,
                'referrals': [],
                'games_played': 0,
                'games_won': 0,
                'total_wagered': 0,
                'total_deposits': 0,
                'total_withdrawals': 0,
                'registration_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'referral_code': user_id[-6:].upper(),
                'level': 1,
                'first_seen': datetime.now().isoformat(),
                'referral_notifications_sent': []
            }

            # ВАЖНО: Для новых пользователей сначала обрабатываем реферальное присоединение
            result = process_referral_join(
                new_user_id=user_id,
                referral_code=referral_code,
                user_data=user_data
            )

            print(f"Результат process_referral_join: {result}")

            if result and result.get('success'):
                is_referral_join = True
                referrer_data = result.get('referrer_data')
                print(f"✅ Новый пользователь {user_id} успешно зарегистрирован как реферал {referral_code}")
            else:
                error_msg = result.get('message', 'Неизвестная ошибка') if result else 'Ошибка обработки'
                print(f"⚠️ Не удалось обработать реферала {user_id}: {error_msg}")

                # Если реферальная обработка не удалась, создаем обычного пользователя
                users_data[user_id] = user_data
                users_data[user_id]['referrer_id'] = None
                users_data[user_id]['is_referral'] = False
                save_users_data(users_data)
                print(f"✅ Создан обычный пользователь {user_id}")
        else:
            # Существующий пользователь - не может стать рефералом
            print(f"⚠️ Существующий пользователь {user_id} не может стать рефералом")
    else:
        # Обычная регистрация (без реферальной ссылки)
        if is_new_user:
            # Создаем обычного пользователя без реферала
            users_data[user_id] = {
                'first_seen': datetime.now().isoformat(),
                'balance': 0,
                'level': 1,
                'referrals': [],
                'referral_bonus': 0,
                'total_referral_income': 0,
                'referral_code': user_id[-6:].upper(),
                'referrer_id': None,
                'is_referral': False,
                'username': message.from_user.username,
                'first_name': message.from_user.first_name,
                'total_deposits': 0,
                'total_withdrawals': 0,
                'games_played': 0,
                'games_won': 0,
                'total_wagered': 0,
                'referral_notifications_sent': []
            }
            save_users_data(users_data)
            print(f"✅ Создан обычный пользователь {user_id} без реферала")

    # Загружаем обновленные данные
    users_data = load_users_data()

    # Получаем информацию о реферере (если есть)
    user_info = users_data.get(user_id, {})
    referrer_id = user_info.get('referrer_id')
    has_referrer = referrer_id is not None and referrer_id in users_data

    # РАЗНЫЕ ПРИВЕТСТВИЯ
    if is_referral_join and referrer_data and is_new_user:
        # ПРИВЕТСТВИЕ ДЛЯ НОВЫХ РЕФЕРАЛОВ (ТОЛЬКО НОВЫЕ!)
        welcome_text = f"""
<blockquote expandable>╔══════════════════════╗
   🔥 <b>FLAME GAME</b> 🔥
╚══════════════════════╝</blockquote>

✨ <b>Добро пожаловать, {user_first_name}!</b>

<blockquote>
🎮 <b>Присоединился по приглашению</b>
├ 👤 Игрок: <b>{user_username}</b>
├ 🆔 ID: <code>{user_id}</code>
└ 🤝 Пригласил: <b>{referrer_data.get('referrer_name', 'Друг')}</b>
</blockquote>

<blockquote>
<b>🔥 ДОСТУПНЫЕ ИГРЫ:</b>
<code>💣 Мины | 🏰 Башня | 🚀 Краш</code>
<code>🎯 Дартс | 🏀 Баскетбол | ⚽ Футбол | 🎲 Кости</code>
</blockquote>

<i>🔥 Удачной игры и больших побед!</i>
"""

        # Отправляем уведомление рефереру
        if referrer_id:
            send_referral_notification_to_referrer(referrer_id, user_id)
            print(f"📨 Отправлено уведомление рефереру {referrer_id}")

        # Отправляем отдельное приветственное сообщение
        send_referral_welcome_message(message.chat.id, referrer_data)

    elif is_new_user:
        # ПРИВЕТСТВИЕ ДЛЯ НОВЫХ ОБЫЧНЫХ ПОЛЬЗОВАТЕЛЕЙ
        welcome_text = f"""
<blockquote expandable>╔══════════════════════╗
   🔥 <b>FLAME GAME</b> 🔥
╚══════════════════════╝</blockquote>

✨ <b>Добро пожаловать, {user_first_name}!</b>

<blockquote>
🎮 <b>Твой игровой путь начинается</b>
├ 👤 Игрок: <b>{user_username}</b>
├ 🆔 ID: <code>{user_id}</code>
└ 📅 Регистрация: <b>сегодня</b>
</blockquote>

<blockquote>
<b>🔥 ДОСТУПНЫЕ ИГРЫ:</b>
<code>💣 Мины | 🏰 Башня | 🚀 Краш</code>
<code>🎯 Дартс | 🏀 Баскетбол | ⚽ Футбол | 🎲 Кости</code>
</blockquote>

<blockquote>
<b>👥 РЕФЕРАЛЬНАЯ СИСТЕМА:</b>
Приглашай друзей и получай <b>6%</b>
от их выигрышных ставок!
</blockquote>

<i>💫 Выбирай игру и начинай! Удачи! 🚀</i>
"""
    else:
        # ПРИВЕТСТВИЕ ДЛЯ СУЩЕСТВУЮЩИХ ПОЛЬЗОВАТЕЛЕЙ
        if has_referrer:
            referrer_name = users_data.get(referrer_id, {}).get('first_name', 'Ваш друг')
            referrer_text = f"└ 🤝 Ваш реферер: <b>{referrer_name}</b>"
        else:
            referrer_text = "└ 📈 Пригласи друзей и получай бонусы!"

        welcome_text = f"""
<blockquote expandable>╔══════════════════════╗
   🔥 <b>FLAME GAME</b> 🔥
╚══════════════════════╝</blockquote>

✨ <b>С возвращением, {user_first_name}!</b>

<blockquote>
🎮 <b>Снова в игре</b>
├ 👤 Игрок: <b>{user_username}</b>
├ 🆔 ID: <code>{user_id}</code>
{referrer_text}
</blockquote>

<blockquote>
<b>🔥 ДОСТУПНЫЕ ИГРЫ:</b>
<code>💣 Мины | 🏰 Башня | 🚀 Краш</code>
<code>🎯 Дартс | 🏀 Баскетбол | ⚽ Футбол | 🎲 Кости</code>
</blockquote>

<i>💫 Выбирай игру и продолжай! Удачи! 🚀</i>
"""

    # ВАЖНОЕ ИЗМЕНЕНИЕ: В чатах отправляем без меню, в личных - с меню
    if is_private_chat(message):
        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
    else:
        # В групповых чатах отправляем только текст без меню
        bot.send_message(
            message.chat.id,
            welcome_text,
            parse_mode='HTML'
        )

    print(f"=== ЗАВЕРШЕНО ОБРАБОТКА /start ===\n")

# ====== НОВЫЕ КОМАНДЫ ДЛЯ ЧАТА ======

@bot.message_handler(func=lambda message: message.text and message.text.lower() in ['баланс', '/баланс', 'balance', '/balance'])
def balance_command(message):
    """Показать баланс (работает с командой и без слеша) - ТОЛЬКО БАЛАНС И НИК"""
    users_data = load_users_data()
    user_id = str(message.from_user.id)

    if user_id not in users_data:
        bot.send_message(message.chat.id, "❌ Сначала зарегистрируйтесь через /start")
        return

    user_info = users_data[user_id]
    balance = user_info.get('balance', 0)
    balance_rounded = round(balance, 2)

    username = message.from_user.username
    first_name = message.from_user.first_name

    # Формируем имя пользователя
    if username:
        user_display = f"@{username}"
    else:
        user_display = first_name

    # ПРОСТОЙ ТЕКСТ - ТОЛЬКО БАЛАНС И НИК
    balance_text = f"""
👤 <b>{user_display}</b>
💰 <b>Баланс:</b> {balance_rounded}₽
"""

    # Отправляем ответ на сообщение с командой
    bot.send_message(
        message.chat.id,
        balance_text,
        parse_mode='HTML',
        reply_to_message_id=message.message_id
    )

@bot.message_handler(func=lambda message: message.text and message.text.lower() in ['профиль', 'профил', '/профиль', '/profile', 'profile'])
def profile_command(message):
    """Показать профиль с меню (работает с командой и без слеша)"""
    users_data = load_users_data()
    user_id = str(message.from_user.id)

    if user_id not in users_data:
        bot.send_message(message.chat.id, "❌ Сначала зарегистрируйтесь через /start")
        return

    user_info = users_data[user_id]
    username = message.from_user.username if message.from_user.username else message.from_user.first_name
    balance = user_info.get('balance', 0)
    balance_rounded = round(balance, 2)
    first_seen = datetime.fromisoformat(user_info['first_seen'])
    days_in_project = (datetime.now() - first_seen).days

    # Статистика
    total_deposits = user_info.get('total_deposits', 0)
    total_withdrawals = user_info.get('total_withdrawals', 0)

    # Получаем аватарку пользователя
    avatar_file_id = get_user_avatar(message.from_user.id)

    # СТИЛЬНЫЙ КОРОТКИЙ ПРОФИЛЬ
    profile_text = f"""
<blockquote expandable>╔══════════════════════╗
   🔥 <b>FLAME PROFILE</b> 🔥
╚══════════════════════╝</blockquote>

<b>👤 Игрок:</b> @{username}
<b>🆔 ID:</b> <code>{user_id}</code>
━━━━━━━━━━━━━━━━━━━━
<b>💰 Баланс:</b> <code>{balance_rounded}₽</code>
<b>📥 Депозиты:</b> <code>{total_deposits}₽</code>
<b>📤 Выводы:</b> <code>{total_withdrawals}₽</code>
━━━━━━━━━━━━━━━━━━━━
<b>📅 В проекте:</b> {days_in_project} дней
"""

    # КНОПКИ С ИСПОЛЬЗОВАНИЕМ PAYMENTS_MODULE
    markup = types.InlineKeyboardMarkup(row_width=2)
    if PAYMENTS_ENABLED:
        markup.row(
            types.InlineKeyboardButton("📥 ПОПОЛНИТЬ", callback_data="profile_deposit"),
            types.InlineKeyboardButton("📤 ВЫВЕСТИ", callback_data="profile_withdraw")
        )
    else:
        markup.row(
            types.InlineKeyboardButton("📥 ПОПОЛНИТЬ (скоро)", callback_data="deposit"),
            types.InlineKeyboardButton("📤 ВЫВЕСТИ (скоро)", callback_data="withdraw")
        )

    # Отправляем сообщение с фото или без
    if avatar_file_id:
        try:
            # Отправляем фото с подписью (ответ на сообщение с командой)
            bot.send_photo(
                message.chat.id,
                photo=avatar_file_id,
                caption=profile_text,
                reply_markup=markup,
                parse_mode='HTML',
                reply_to_message_id=message.message_id
            )
        except Exception as e:
            print(f"Ошибка отправки фото: {e}")
            # Если не удалось отправить фото, отправляем просто текст
            bot.send_message(
                message.chat.id,
                profile_text,
                reply_markup=markup,
                parse_mode='HTML',
                reply_to_message_id=message.message_id
            )
    else:
        # Если нет аватарки, отправляем просто текст (ответ на сообщение с командой)
        bot.send_message(
            message.chat.id,
            profile_text,
            reply_markup=markup,
            parse_mode='HTML',
            reply_to_message_id=message.message_id
        )

@bot.message_handler(func=lambda message: any(word in message.text.lower() for word in ['/pay', 'дать', 'перевести', 'перевод']))
def pay_command(message):
    """Перевод денег другому пользователю в ответ на сообщение - КОРОТКИЙ ФОРМАТ"""
    users_data = load_users_data()
    sender_id = str(message.from_user.id)

    if sender_id not in users_data:
        bot.send_message(message.chat.id, "❌ Сначала зарегистрируйтесь через /start")
        return

    # Проверяем, что сообщение является ответом на другое сообщение
    if not message.reply_to_message:
        bot.send_message(
            message.chat.id,
            "❌ Ответьте на сообщение пользователя для перевода\n"
            "Пример: <code>/pay 100</code>",
            reply_to_message_id=message.message_id
        )
        return

    # Получаем получателя
    recipient = message.reply_to_message.from_user
    recipient_id = str(recipient.id)

    # Проверяем, что не перевод самому себе
    if sender_id == recipient_id:
        bot.send_message(
            message.chat.id,
            "❌ Нельзя переводить самому себе!",
            reply_to_message_id=message.message_id
        )
        return

    # Проверяем, что получатель зарегистрирован
    if recipient_id not in users_data:
        bot.send_message(
            message.chat.id,
            f"❌ Пользователь не зарегистрирован!",
            reply_to_message_id=message.message_id
        )
        return

    # Парсим сумму из команды
    try:
        # Ищем число в сообщении
        numbers = re.findall(r'\d+\.?\d*', message.text)

        if not numbers:
            raise ValueError

        amount = float(numbers[0])

        # Проверяем минимальную и максимальную сумму
        if amount < 1:
            bot.send_message(
                message.chat.id,
                "❌ Мин: 1₽",
                reply_to_message_id=message.message_id
            )
            return

        if amount > 1000:
            bot.send_message(
                message.chat.id,
                "❌ Макс: 1000₽",
                reply_to_message_id=message.message_id
            )
            return

        # Проверяем баланс отправителя
        sender_balance = users_data[sender_id].get('balance', 0)
        if sender_balance < amount:
            bot.send_message(
                message.chat.id,
                f"❌ Недостаточно средств!",
                reply_to_message_id=message.message_id
            )
            return

        # Выполняем перевод
        users_data[sender_id]['balance'] = round(sender_balance - amount, 2)
        users_data[recipient_id]['balance'] = round(users_data[recipient_id].get('balance', 0) + amount, 2)

        # Сохраняем изменения
        save_users_data(users_data)

        # КОРОТКОЕ УВЕДОМЛЕНИЕ - ТОЛЬКО В ЧАТЕ
        recipient_name = recipient.username or recipient.first_name

        bot.send_message(
            message.chat.id,
            f"✅ Перевод завершен\n"
            f"💸 {amount}₽ → @{recipient_name}",
            parse_mode='HTML',
            reply_to_message_id=message.message_id
        )

    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ Используйте: /pay [сумма]\n"
            "Пример: <code>/pay 100</code>",
            parse_mode='HTML',
            reply_to_message_id=message.message_id
        )

@bot.message_handler(content_types=['text'])
def menu_handler(message):
    # ПРОВЕРЯЕМ ТИП ЧАТА
    if not is_private_chat(message):
        # В групповых чатах игнорируем текстовые сообщения (кроме команд)
        return

    text = message.text
    user = message.from_user
    user_id = str(user.id)
    users_data = load_users_data()

    if text == "🔥 Профиль":
        if user_id in users_data:
            user_info = users_data[user_id]
            username = user.username if user.username else user.first_name
            balance = user_info.get('balance', 0)
            balance_rounded = round(balance, 2)
            first_seen = datetime.fromisoformat(user_info['first_seen'])
            days_in_project = (datetime.now() - first_seen).days

            # Статистика
            total_deposits = user_info.get('total_deposits', 0)
            total_withdrawals = user_info.get('total_withdrawals', 0)

            # Получаем аватарку пользователя
            avatar_file_id = get_user_avatar(user.id)

            # СТИЛЬНЫЙ КОРОТКИЙ ПРОФИЛЬ
            profile_text = f"""
<blockquote expandable>╔══════════════════════╗
   🔥 <b>FLAME PROFILE</b> 🔥
╚══════════════════════╝</blockquote>

<b>👤 Игрок:</b> @{username}
<b>🆔 ID:</b> <code>{user_id}</code>
━━━━━━━━━━━━━━━━━━━━
<b>💰 Баланс:</b> <code>{balance_rounded}₽</code>
<b>📥 Депозиты:</b> <code>{total_deposits}₽</code>
<b>📤 Выводы:</b> <code>{total_withdrawals}₽</code>
━━━━━━━━━━━━━━━━━━━━
<b>📅 В проекте:</b> {days_in_project} дней
"""

            # КНОПКИ С ИСПОЛЬЗОВАНИЕМ PAYMENTS_MODULE
            markup = types.InlineKeyboardMarkup(row_width=2)
            if PAYMENTS_ENABLED:
                markup.row(
                    types.InlineKeyboardButton("📥 ПОПОЛНИТЬ", callback_data="profile_deposit"),
                    types.InlineKeyboardButton("📤 ВЫВЕСТИ", callback_data="profile_withdraw")
                )
            else:
                markup.row(
                    types.InlineKeyboardButton("📥 ПОПОЛНИТЬ (скоро)", callback_data="deposit"),
                    types.InlineKeyboardButton("📤 ВЫВЕСТИ (скоро)", callback_data="withdraw")
                )

            # Отправляем сообщение с фото или без
            if avatar_file_id:
                try:
                    # Отправляем фото с подписью
                    bot.send_photo(
                        message.chat.id,
                        photo=avatar_file_id,
                        caption=profile_text,
                        reply_markup=markup,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    print(f"Ошибка отправки фото: {e}")
                    # Если не удалось отправить фото, отправляем просто текст
                    bot.send_message(
                        message.chat.id,
                        profile_text,
                        reply_markup=markup,
                        parse_mode='HTML'
                    )
            else:
                # Если нет аватарки, отправляем просто текст
                bot.send_message(
                    message.chat.id,
                    profile_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
        else:
            bot.send_message(message.chat.id, "❌ Профиль не найден. Нажмите /start", reply_markup=main_menu())

    elif text == "👥 Рефералы":
        # СРАЗУ ПОКАЗЫВАЕМ РЕФЕРАЛЬНУЮ СИСТЕМУ
        try:
            user_id = str(message.from_user.id)
            users_data = load_users_data()

            if user_id not in users_data:
                bot.send_message(message.chat.id, "❌ Сначала зарегистрируйтесь через /start")
                return

            # Получаем данные пользователя
            user_info = users_data[user_id]
            referral_bonus_balance = user_info.get('referral_bonus', 0)
            total_referral_income = user_info.get('total_referral_income', 0)
            referral_count = len(user_info.get('referrals', []))

            # Получаем username бота
            try:
                bot_info = bot.get_me()
                BOT_USERNAME = bot_info.username
            except:
                BOT_USERNAME = "YOUR_BOT_USERNAME"

            # Формируем реферальную ссылку
            referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"

            # Создаем кнопки БЕЗ КНОПКИ НАЗАД
            markup = types.InlineKeyboardMarkup(row_width=1)

            # Кнопка вывода
            withdraw_text = "💸 Вывести на баланс"
            if referral_bonus_balance < 300:
                withdraw_text = f"💸 Вывести на баланс (нужно {300-referral_bonus_balance}₽)"

            markup.add(
                types.InlineKeyboardButton(withdraw_text, callback_data="withdraw_referral"),
                types.InlineKeyboardButton("📋 Мои рефералы", callback_data="my_referrals"),
                types.InlineKeyboardButton("📤 Поделиться", switch_inline_query=f"Присоединяйся к игре! 🔥\n{referral_link}")
            )

            # Текст реферальной системы
            referral_text = f"""
<blockquote expandable>╔══════════════════════╗
   👥 <b>РЕФЕРАЛЬНАЯ СИСТЕМА</b> 👥
╚══════════════════════╝</blockquote>

<blockquote>
<b>💰 РЕФЕРАЛЬНЫЙ БАЛАНС:</b>
├ 💎 Доступно: <b>{referral_bonus_balance}₽</b>
├ 🎯 Всего рефералов: <b>{referral_count}</b>
├ 📊 Всего получено: <b>{total_referral_income}₽</b>
└ 🎯 Процент: <b>6%</b> от выигрышных ставок
</blockquote>

<blockquote>
<b>🔗 ВАША РЕФЕРАЛЬНАЯ ССЫЛКА:</b>
<code>{referral_link}</code>
</blockquote>

<blockquote>
<b>🎯 УСЛОВИЯ ВЫВОДА:</b>
├ 💸 Минимальная сумма: <b>300₽</b>
├ ⚡ Вывод в любой момент
└ 🔄 На основной баланс
</blockquote>

<b>⚠️ Для вывода нажмите кнопку "💸 Вывести на баланс"</b>
"""

            bot.send_message(
                message.chat.id,
                referral_text,
                parse_mode='HTML',
                reply_markup=markup
            )

        except Exception as e:
            print(f"Ошибка при показе рефералов: {e}")
            bot.send_message(message.chat.id, "❌ Ошибка при загрузке реферальной системы", reply_markup=main_menu())

    elif text == "🏆 ТОП Игроков":
        # Используем модуль leaders.py
        from leaders import show_leaders
        show_leaders(bot, message)

    elif text == "ℹ️ О проекте":
        info_text = """
<blockquote expandable>╔══════════════════════╗
   🔥 <b>FLAME GAME</b> 🔥
╚══════════════════════╝</blockquote>

<blockquote>
<b>🌟 О ПРОЕКТЕ:</b>
Flame Game - это современная игровая
платформа с уникальными механиками
и честной монетизацией.

<b>🎮 НАША МИССИЯ:</b>
Создать лучшее игровое сообщество
где каждый может проявить себя
и заработать на своих навыках.

<b>💎 ПРЕИМУЩЕСТВА:</b>
├ 🔥 Быстрые выплаты
├ 💫 Честные игры
├ 🚀 Современный дизайн
└ 👥 Активное сообщество

<b>🔒 БЕЗОПАСНОСТЬ:</b>
Все транзакции защищены
Ваши данные в безопасности
</blockquote>

<i>🔥 Присоединяйся к Flame Game сегодня!</i>
"""
        bot.send_message(message.chat.id, info_text, parse_mode='HTML', reply_markup=main_menu())

    elif text == "🎮 Игры":
        # Получаем баланс и меню
        balance_text, markup = games_inline_menu(user_id)

        # МИНИМАЛИСТИЧНОЕ МЕНЮ ИГР
        games_text = f"""
<blockquote expandable>╔══════════════════════╗
   🎮 <b>FLAME GAMES</b> 🎮
╚══════════════════════╝</blockquote>

{balance_text}
"""
        bot.send_message(
            message.chat.id,
            games_text,
            parse_mode='HTML',
            reply_markup=markup
        )

    # КНОПКИ ИГР ИЗ ТЕКСТОВОГО МЕНЮ (кости, баскетбол, футбол, дартс)
    elif text in ["🎲 Кости", "🏀 Баскетбол", "⚽ Футбол", "🎯 Дартс"]:
        # Загружаем данные пользователя
        users_data = load_users_data()
        if user_id not in users_data:
            users_data[user_id] = {'balance': 0}
            save_users_data(users_data)

        balance = users_data[user_id].get('balance', 0)
        balance_rounded = round(balance, 2)

        # Определяем игру
        if text == "🎲 Кости":
            game_name = "🎲 Кости"
            callback_data = "games_dice"
        elif text == "🏀 Баскетбол":
            game_name = "🏀 Баскетбол"
            callback_data = "games_basketball"
        elif text == "⚽ Футбол":
            game_name = "⚽ Футбол"
            callback_data = "games_football"
        elif text == "🎯 Дартс":
            game_name = "🎯 Дартс"
            callback_data = "games_darts"

        # Создаем сообщение с callback для обработки в games.py
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🎮 Начать игру", callback_data=callback_data))

        bot.send_message(
            message.chat.id,
            f"""<b>{game_name}</b>

<blockquote>💵 Баланс: {balance_rounded}₽</blockquote>

Нажмите кнопку ниже для запуска игры:""",
            parse_mode='HTML',
            reply_markup=markup
        )

    else:
        bot.send_message(message.chat.id, "❌ Используй меню ниже для навигации.", reply_markup=main_menu())

# ВАЖНЫЙ ОБРАБОТЧИК ДЛЯ КНОПОК ИГР
@bot.callback_query_handler(func=lambda call: call.data in ["game_mines", "game_tower", "game_crash", "deposit", "withdraw"])
def callback_handler(call):
    user_id = str(call.from_user.id)

    # Обрабатываем кнопки игр
    if call.data == "game_mines":
        try:
            from mines import mines_start
            fake_message = type('obj', (object,), {
                'chat': type('obj', (object,), {'id': call.message.chat.id}),
                'from_user': call.from_user,
                'message_id': call.message.message_id,
                'text': "💣 Мины"
            })()
            mines_start(fake_message)
        except Exception as e:
            print(f"Ошибка запуска игры Мины: {e}")
            bot.answer_callback_query(call.id, "❌ Произошла ошибка при запуске игры!")

    elif call.data == "game_tower":
        try:
            from tower import tower_start
            fake_message = type('obj', (object,), {
                'chat': type('obj', (object,), {'id': call.message.chat.id}),
                'from_user': call.from_user,
                'message_id': call.message.message_id,
                'text': "🏰 Башня"
            })()
            tower_start(fake_message)
        except Exception as e:
            print(f"Ошибка запуска игры Башня: {e}")
            bot.answer_callback_query(call.id, "❌ Произошла ошибка при запуске игры!")

    elif call.data == "game_crash":
        try:
            from crash import crash_start
            fake_message = type('obj', (object,), {
                'chat': type('obj', (object,), {'id': call.message.chat.id}),
                'from_user': call.from_user,
                'message_id': call.message.message_id,
                'text': "🚀 Краш"
            })()
            crash_start(fake_message)
        except Exception as e:
            print(f"Ошибка запуска игры Краш: {e}")
            bot.answer_callback_query(call.id, "❌ Произошла ошибка при запуске игры!")

    elif call.data == "deposit":
        # Для кнопок "скоро"
        bot.answer_callback_query(call.id, "📥 Пополнение баланса скоро будет доступно!")

    elif call.data == "withdraw":
        # Для кнопок "скоро"
        bot.answer_callback_query(call.id, "📤 Вывод средств скоро будет доступен!")

#ВЕБХУК
# ... (весь ваш существующий код остается) ...

# ... (весь ваш существующий код остается) ...

print("🔥 Flame Game запущен...")
print(f"✅ Модуль платежей: {'ВКЛЮЧЕН' if PAYMENTS_ENABLED else 'ОТКЛЮЧЕН'}")
print(f"🌐 Вебхук: {WEBHOOK_URL_BASE + WEBHOOK_URL_PATH}")

# ==== ДОБАВЬТЕ ЭТИ ФУНКЦИИ ВЕБХУКА В КОНЦЕ ФАЙЛА ====

# Обработчик для вебхука
@app.route(WEBHOOK_URL_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        abort(403)

@app.route('/')
def index():
    return 'Bot is running!'

@app.route('/health')
def health():
    return 'OK', 200

# Для Render - установка вебхука
@app.route('/set_webhook')
def set_webhook_route():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)
        return f'✅ Вебхук установлен: {WEBHOOK_URL_BASE + WEBHOOK_URL_PATH}'
    except Exception as e:
        return f'❌ Ошибка: {str(e)}'

# Функция для установки вебхука при запуске
def set_webhook():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)
        print(f"✅ Вебхук установлен: {WEBHOOK_URL_BASE + WEBHOOK_URL_PATH}")
        return True
    except Exception as e:
        print(f"⚠️ Ошибка установки вебхука: {e}")
        return False

# Запуск Flask приложения для Render
if __name__ == '__main__':
    if set_webhook():
        # Получаем порт из переменной окружения Render
        port = int(os.environ.get('PORT', 10000))
        print(f"🚀 Запуск на порту: {port}")
        
        if RENDER:
            # На Render без SSL (они управляют этим)
            app.run(host='0.0.0.0', port=port)
        else:
            # Для локального тестирования (нужны SSL файлы)
            app.run(host='0.0.0.0', port=port, debug=True)
    else:
        print("❌ Не удалось установить вебхук")
