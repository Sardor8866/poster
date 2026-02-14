import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime
import json
import re
import os
import threading
import logging
import math
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота
BOT_TOKEN = "8531951028:AAHpjHaMxhUSQQUCuaKaweni-f4AXZ_Tk9A"

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

file_lock = threading.Lock()
user_locks = {}

def get_user_lock(user_id):
    if user_id not in user_locks:
        user_locks[user_id] = threading.Lock()
    return user_locks[user_id]

def validate_amount(amount, min_amount=0, max_amount=1000000):
    try:
        if isinstance(amount, str):
            amount = amount.replace(',', '.')
        
        amount = float(amount)
        
        if math.isnan(amount):
            return None
            
        if math.isinf(amount):
            return None
            
        if amount < min_amount or amount > max_amount:
            return None
            
        return round(amount, 2)
    except:
        return None

def get_games_info():
    text = """
<blockquote>
🎮 <b>ДОСТУПНЫЕ ИГРЫ</b>

🏰 <b>Башня:</b> <code>башня [количество-мин] [сумма]</code>
Пример: <code>башня 3 100</code>

💣 <b>Мины:</b> <code>мины [количество-мин] [сумма]</code>
Пример: <code>мины 5 50</code>

🏀 <b>Баскетбол:</b> <code>баскет [исход] [сумма]</code>
Пример: <code>баскет гол 50</code>

⚽️ <b>Футбол:</b> <code>фут [исход] [сумма]</code>
Пример: <code>фут гол 100</code>

🎯 <b>Дартс:</b> <code>дартс [исход] [сумма]</code>
Пример: <code>дартс центр 75</code>

🎲 <b>Кубик:</b> <code>[исход] [сумма]</code>
Пример: <code>нечет 25</code>

💡 Команды работают с <code>/</code> и без него
</blockquote>
"""
    return text

def is_games_command(text):
    if not text:
        return False
    
    text = text.lower().strip()
    
    games_commands = [
        '/games',
        'games',
        '/игры',
        'игры',
        '/game',
        'game',
        '/игра',
        'игра'
    ]
    
    return text in games_commands

# Импортируем модули
from leaders import register_leaders_handlers, leaders_start
import mines
import tower
import leaders
from referrals import register_referrals_handlers, add_referral_bonus, process_referral_join, send_referral_welcome_message, send_referral_notification_to_referrer
from admin_panel import register_admin_handlers
from games import register_games_handlers
from bonus_system import register_bonus_handlers

try:
    from payments import register_crypto_handlers
    PAYMENTS_ENABLED = True
    print("Модуль платежей загружен")
except ImportError as e:
    PAYMENTS_ENABLED = False
    print(f"Модуль платежей не найден: {e}")
    print("Функции пополнения и вывода недоступны")

RENDER = os.environ.get('RENDER', False)

if RENDER:
    WEBHOOK_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'https://poster-x4jl.onrender.com/')
else:
    WEBHOOK_HOST = 'localhost'

WEBHOOK_PORT = 443 if RENDER else 8443
WEBHOOK_LISTEN = '0.0.0.0'
WEBHOOK_URL_BASE = f"https://{WEBHOOK_HOST}"
WEBHOOK_URL_PATH = f"/webhook/{BOT_TOKEN}/"

# Создаем aiohttp приложение
app = web.Application()

# Обработчики игр
@dp.callback_query(F.data.in_(["games_mines", "games_tower", "games_darts", "games_basketball", "games_football", "games_dice"]))
async def games_handlers(call: CallbackQuery):
    user_id = str(call.from_user.id)
    
    game_map = {
        "games_mines": "💣 Мины",
        "games_tower": "🏰 Башня",
        "games_darts": "🎯 Дартс",
        "games_basketball": "🏀 Баскетбол",
        "games_football": "⚽ Футбол",
        "games_dice": "🎲 Кости"
    }
    
    game_name = game_map.get(call.data, "Игра")
    
    try:
        try:
            await call.message.delete()
        except:
            pass
        
        try:
            # Создаем объект сообщения для совместимости с существующими модулями
            class FakeMessage:
                def __init__(self, chat_id, from_user, message_id):
                    self.chat = type('obj', (object,), {'id': chat_id, 'type': 'private'})
                    self.from_user = from_user
                    self.message_id = message_id
                    self.text = game_name
                    self.chat.id = chat_id
                    self.chat.type = 'private'
            
            fake_message = FakeMessage(call.message.chat.id, call.from_user, call.message.message_id)
            
            if call.data == "games_mines":
                mines.mines_start(fake_message)
            elif call.data == "games_tower":
                tower.tower_start(fake_message)
            elif call.data == "games_darts":
                from games import darts_start
                darts_start(fake_message)
            elif call.data == "games_basketball":
                from games import basketball_start
                basketball_start(fake_message)
            elif call.data == "games_football":
                from games import football_start
                football_start(fake_message)
            elif call.data == "games_dice":
                from games import dice_start
                dice_start(fake_message)
                
        except Exception as e:
            print(f"Ошибка запуска игры {game_name}: {e}")
            await call.answer(f"❌ Ошибка при запуске игры!")
    
    except Exception as e:
        print(f"Общая ошибка в обработке игры: {e}")
        await call.answer("❌ Ошибка при запуске игры!")

@dp.callback_query(F.data.in_(["deposit", "withdraw", "profile_deposit", "profile_withdraw"]))
async def payment_callback_handler(call: CallbackQuery):
    if call.data in ["deposit", "profile_deposit"]:
        await call.answer("📥 Пополнение баланса временно недоступно!")
    elif call.data in ["withdraw", "profile_withdraw"]:
        await call.answer("📤 Вывод средств временно недоступен!")

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(call: CallbackQuery):
    """Обработчик возврата в главное меню"""
    welcome_text = f"✨ <b>Добро пожаловать, {call.from_user.first_name}!</b>"
    
    try:
        await call.message.edit_text(
            text=welcome_text,
            parse_mode='HTML',
            reply_markup=get_main_inline_menu()
        )
    except:
        await call.message.answer(
            text=welcome_text,
            parse_mode='HTML',
            reply_markup=get_main_inline_menu()
        )

@dp.callback_query(F.data == "show_profile")
async def profile_callback(call: CallbackQuery):
    """Обработчик профиля из инлайн меню"""
    users_data = load_users_data()
    user_id = str(call.from_user.id)

    if user_id not in users_data:
        await call.answer("❌ Сначала зарегистрируйтесь через /start")
        return

    user_info = users_data[user_id]
    username = call.from_user.username if call.from_user.username else call.from_user.first_name
    balance = user_info.get('balance', 0)
    balance_rounded = round(balance, 2)
    first_seen = datetime.fromisoformat(user_info['first_seen'])
    days_in_project = (datetime.now() - first_seen).days

    total_deposits = user_info.get('total_deposits', 0)
    total_withdrawals = user_info.get('total_withdrawals', 0)

    profile_text = f"""
<blockquote expandable>╔══════════════════════╗
   ❄️ <b>FESTERY PROFILE</b> ❄️
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

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 ПОПОЛНИТЬ", callback_data="profile_deposit"),
            InlineKeyboardButton(text="📤 ВЫВЕСТИ", callback_data="profile_withdraw")
        ],
        [
            InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")
        ]
    ])

    try:
        await call.message.edit_text(
            text=profile_text,
            parse_mode='HTML',
            reply_markup=markup
        )
    except:
        await call.message.answer(
            text=profile_text,
            parse_mode='HTML',
            reply_markup=markup
        )

@dp.callback_query(F.data == "show_referrals")
async def referrals_callback(call: CallbackQuery):
    """Обработчик рефералов из инлайн меню"""
    try:
        user_id = str(call.from_user.id)
        users_data = load_users_data()

        if user_id not in users_data:
            await call.answer("❌ Сначала зарегистрируйтесь через /start")
            return

        user_info = users_data[user_id]
        referral_bonus_balance = user_info.get('referral_bonus', 0)
        total_referral_income = user_info.get('total_referral_income', 0)
        referral_count = len(user_info.get('referrals', []))

        try:
            bot_info = await bot.get_me()
            BOT_USERNAME = bot_info.username
        except:
            BOT_USERNAME = "YOUR_BOT_USERNAME"

        referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"

        withdraw_text = "💸 Вывести на баланс"
        if referral_bonus_balance < 300:
            withdraw_text = f"💸 Вывести на баланс (нужно {300-referral_bonus_balance}₽)"

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=withdraw_text, callback_data="withdraw_referral")],
            [InlineKeyboardButton(text="📋 Мои рефералы", callback_data="my_referrals")],
            [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=f"Присоединяйся к игре! 🔥\n{referral_link}")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]
        ])

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

        try:
            await call.message.edit_text(
                text=referral_text,
                parse_mode='HTML',
                reply_markup=markup
            )
        except:
            await call.message.answer(
                text=referral_text,
                parse_mode='HTML',
                reply_markup=markup
            )

    except Exception as e:
        print(f"Ошибка при показе рефералов: {e}")
        await call.answer("❌ Ошибка при загрузке реферальной системы")

@dp.callback_query(F.data == "show_leaders")
async def leaders_callback(call: CallbackQuery):
    """Обработчик ТОПа из инлайн меню"""
    try:
        from leaders import get_leaders_text
        
        leaders_text = get_leaders_text()
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]
        ])
        
        try:
            await call.message.edit_text(
                text=leaders_text,
                parse_mode='HTML',
                reply_markup=markup
            )
        except Exception as e:
            print(f"Ошибка редактирования ТОПа: {e}")
            await call.message.answer(
                text=leaders_text,
                parse_mode='HTML',
                reply_markup=markup
            )
    except Exception as e:
        print(f"Ошибка в leaders_callback: {e}")
        await call.answer("❌ Ошибка загрузки ТОПа")

@dp.callback_query(F.data == "show_games")
async def games_callback(call: CallbackQuery):
    """Обработчик игр из инлайн меню"""
    user_id = str(call.from_user.id)
    balance_text, markup = games_inline_menu(user_id)

    games_text = f"""
<blockquote expandable>╔══════════════════════╗
   🎮 <b>FLAME GAMES</b> 🎮
╚══════════════════════╝</blockquote>

{balance_text}
"""
    
    try:
        await call.message.edit_text(
            text=games_text,
            parse_mode='HTML',
            reply_markup=markup
        )
    except:
        await call.message.answer(
            text=games_text,
            parse_mode='HTML',
            reply_markup=markup
        )

@dp.callback_query(F.data == "show_about")
async def about_callback(call: CallbackQuery):
    """Обработчик О проекте из инлайн меню"""
    info_text = """
<blockquote expandable>╔══════════════════════╗
   ❄️ <b>FESTERY GAME</b> ❄️
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

<i>❄️ Присоединяйся к Festery Game сегодня!</i>
"""

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]
    ])
    
    try:
        await call.message.edit_text(
            text=info_text,
            parse_mode='HTML',
            reply_markup=markup
        )
    except:
        await call.message.answer(
            text=info_text,
            parse_mode='HTML',
            reply_markup=markup
        )

# Функции для работы с данными
def load_users_data():
    try:
        with file_lock:
            with open('users_data.json', 'r', encoding='utf-8') as f:
                return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        logger.error("Ошибка декодирования JSON")
        return {}

def save_users_data(data):
    try:
        with file_lock:
            with open('users_data.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")
        return False

async def get_user_avatar(user_id):
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            return file_id
    except Exception as e:
        print(f"Ошибка получения аватарки: {e}")
    return None

def get_main_inline_menu():
    """Главное инлайн меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❄️ Профиль", callback_data="show_profile"),
            InlineKeyboardButton(text="👥 Рефералы", callback_data="show_referrals")
        ],
        [
            InlineKeyboardButton(text="🏆 ТОП Игроков", callback_data="show_leaders"),
            InlineKeyboardButton(text="🎮 Игры", callback_data="show_games")
        ],
        [
            InlineKeyboardButton(text="ℹ️ О проекте", callback_data="show_about")
        ]
    ])

def games_inline_menu(user_id):
    users_data = load_users_data()
    user_info = users_data.get(user_id, {})
    balance = user_info.get('balance', 0)
    balance = validate_amount(balance, min_amount=0)
    if balance is None:
        balance = 0
    balance_rounded = round(balance, 2)

    balance_text = f"""
<blockquote>
💎 <b>Баланс:</b> {balance_rounded}₽
</blockquote>
"""

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💣 Мины", callback_data="games_mines"),
            InlineKeyboardButton(text="🏰 Башня", callback_data="games_tower")
        ],
        [
            InlineKeyboardButton(text="🎯 Дартс", callback_data="games_darts"),
            InlineKeyboardButton(text="🏀 Баскетбол", callback_data="games_basketball")
        ],
        [
            InlineKeyboardButton(text="⚽ Футбол", callback_data="games_football"),
            InlineKeyboardButton(text="🎲 Кости", callback_data="games_dice")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад в меню", callback_data="main_menu")
        ]
    ])

    return balance_text, markup

def is_private_chat(message: Message):
    return message.chat.type == 'private'

@dp.message(Command('start'))
async def start_message(message: Message):
    users_data = load_users_data()
    user_id = str(message.from_user.id)
    user_first_name = message.from_user.first_name or "Игрок"

    is_new_user = user_id not in users_data
    is_referral_join = False
    referrer_data = None
    referral_code = None

    print(f"=== НАЧАЛО ОБРАБОТКИ /start ===")
    print(f"User ID: {user_id}")
    print(f"Is new user: {is_new_user}")

    if len(message.text.split()) > 1:
        referral_code = message.text.split()[1]
        print(f"Referral code from URL: {referral_code}")

        if is_new_user:
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

            result = process_referral_join(
                new_user_id=user_id,
                referral_code=referral_code,
                user_data=user_data
            )

            print(f"Результат process_referral_join: {result}")

            if result and result.get('success'):
                is_referral_join = True
                referrer_data = result.get('referrer_data')
                print(f"Новый пользователь {user_id} зарегистрирован как реферал {referral_code}")
            else:
                error_msg = result.get('message', 'Неизвестная ошибка') if result else 'Ошибка обработки'
                print(f"Не удалось обработать реферала {user_id}: {error_msg}")

                user_lock = get_user_lock(user_id)
                with user_lock:
                    users_data = load_users_data()
                    if user_id not in users_data:
                        users_data[user_id] = user_data
                        users_data[user_id]['referrer_id'] = None
                        users_data[user_id]['is_referral'] = False
                        save_users_data(users_data)
                        print(f"Создан обычный пользователь {user_id}")
        else:
            print(f"Существующий пользователь {user_id} не может стать рефералом")
    else:
        if is_new_user:
            user_lock = get_user_lock(user_id)
            with user_lock:
                users_data = load_users_data()
                if user_id not in users_data:
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
                    print(f"Создан обычный пользователь {user_id} без реферала")

    users_data = load_users_data()

    if is_referral_join and referrer_data and is_new_user:
        referrer_id = users_data.get(user_id, {}).get('referrer_id')
        if referrer_id:
            send_referral_notification_to_referrer(referrer_id, user_id)
            print(f"Отправлено уведомление рефереру {referrer_id}")

    # Простое приветствие
    welcome_text = f"✨ <b>Добро пожаловать, {user_first_name}!</b>"

    if is_private_chat(message):
        await message.answer(
            text=welcome_text,
            reply_markup=get_main_inline_menu(),
            parse_mode='HTML'
        )
    else:
        await message.answer(
            text=welcome_text,
            parse_mode='HTML'
        )

    print(f"=== ЗАВЕРШЕНО ОБРАБОТКА /start ===\n")

@dp.message(Command('бал', 'баланс', 'balance'))
async def balance_command(message: Message):
    users_data = load_users_data()
    user_id = str(message.from_user.id)

    if user_id not in users_data:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")
        return

    user_info = users_data[user_id]
    balance = user_info.get('balance', 0)
    balance = validate_amount(balance, min_amount=0)
    if balance is None:
        balance = 0
    balance_rounded = round(balance, 2)

    username = message.from_user.username
    first_name = message.from_user.first_name

    if username:
        user_display = f"@{username}"
    else:
        user_display = first_name

    balance_text = f"""
👤 <b>{user_display}</b>
💰 <b>Баланс:</b> {balance_rounded}₽
"""

    await message.answer(
        text=balance_text,
        parse_mode='HTML',
        reply_to_message_id=message.message_id
    )

@dp.message(F.text & (F.text.lower().in_(['профиль', 'профил', '/профиль', '/profile', 'profile'])))
async def profile_command(message: Message):
    users_data = load_users_data()
    user_id = str(message.from_user.id)

    if user_id not in users_data:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")
        return

    user_info = users_data[user_id]
    username = message.from_user.username if message.from_user.username else message.from_user.first_name
    balance = user_info.get('balance', 0)
    balance_rounded = round(balance, 2)
    first_seen = datetime.fromisoformat(user_info['first_seen'])
    days_in_project = (datetime.now() - first_seen).days

    total_deposits = user_info.get('total_deposits', 0)
    total_withdrawals = user_info.get('total_withdrawals', 0)

    avatar_file_id = await get_user_avatar(message.from_user.id)

    profile_text = f"""
<blockquote expandable>╔══════════════════════╗
   ❄️ <b>FESTERY PROFILE</b> ❄️
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

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 ПОПОЛНИТЬ", callback_data="profile_deposit"),
            InlineKeyboardButton(text="📤 ВЫВЕСТИ", callback_data="profile_withdraw")
        ],
        [
            InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")
        ]
    ])

    if avatar_file_id:
        try:
            await message.answer_photo(
                photo=avatar_file_id,
                caption=profile_text,
                reply_markup=markup,
                parse_mode='HTML',
                reply_to_message_id=message.message_id
            )
        except Exception as e:
            print(f"Ошибка отправки фото: {e}")
            await message.answer(
                text=profile_text,
                reply_markup=markup,
                parse_mode='HTML',
                reply_to_message_id=message.message_id
            )
    else:
        await message.answer(
            text=profile_text,
            reply_markup=markup,
            parse_mode='HTML',
            reply_to_message_id=message.message_id
        )

@dp.message(F.text.regexp(r'^/(pay|дать|перевести|перевод)\s+\d+'))
async def pay_command(message: Message):
    users_data = load_users_data()
    sender_id = str(message.from_user.id)

    if sender_id not in users_data:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")
        return

    if not message.reply_to_message:
        await message.answer(
            text="❌ Ответьте на сообщение пользователя для перевода\n"
                 "Пример: <code>/pay 100</code>",
            reply_to_message_id=message.message_id
        )
        return

    recipient = message.reply_to_message.from_user
    recipient_id = str(recipient.id)

    if sender_id == recipient_id:
        await message.answer(
            text="❌ Нельзя переводить самому себе!",
            reply_to_message_id=message.message_id
        )
        return

    if recipient_id not in users_data:
        await message.answer(
            text="❌ Пользователь не зарегистрирован!",
            reply_to_message_id=message.message_id
        )
        return

    try:
        numbers = re.findall(r'\d+\.?\d*', message.text)

        if not numbers:
            raise ValueError

        amount = float(numbers[0])
        
        amount = validate_amount(amount, min_amount=1, max_amount=1000)
        if amount is None:
            await message.answer(
                text="❌ Некорректная сумма!",
                reply_to_message_id=message.message_id
            )
            return

        if amount < 1:
            await message.answer(
                text="❌ Мин: 1₽",
                reply_to_message_id=message.message_id
            )
            return

        if amount > 1000:
            await message.answer(
                text="❌ Макс: 1000₽",
                reply_to_message_id=message.message_id
            )
            return

        sender_lock = get_user_lock(sender_id)
        recipient_lock = get_user_lock(recipient_id)
        
        locks = sorted([sender_lock, recipient_lock], key=lambda x: id(x))
        
        with locks[0]:
            with locks[1]:
                users_data = load_users_data()
                
                sender_balance = users_data[sender_id].get('balance', 0)
                sender_balance = validate_amount(sender_balance, min_amount=0)
                if sender_balance is None:
                    sender_balance = 0
                    users_data[sender_id]['balance'] = 0
                
                if sender_balance < amount:
                    await message.answer(
                        text="❌ Недостаточно средств!",
                        reply_to_message_id=message.message_id
                    )
                    return

                new_sender_balance = round(sender_balance - amount, 2)
                
                if new_sender_balance < 0:
                    await message.answer(
                        text="❌ Ошибка: баланс не может быть отрицательным!",
                        reply_to_message_id=message.message_id
                    )
                    return
                
                users_data[sender_id]['balance'] = new_sender_balance
                
                recipient_balance = users_data[recipient_id].get('balance', 0)
                recipient_balance = validate_amount(recipient_balance, min_amount=0)
                if recipient_balance is None:
                    recipient_balance = 0
                
                new_recipient_balance = round(recipient_balance + amount, 2)
                users_data[recipient_id]['balance'] = new_recipient_balance

                save_users_data(users_data)

        recipient_name = recipient.username or recipient.first_name

        await message.answer(
            text=f"✅ Перевод завершен\n"
                 f"💸 {amount}₽ → @{recipient_name}",
            parse_mode='HTML',
            reply_to_message_id=message.message_id
        )

    except ValueError:
        await message.answer(
            text="❌ Используйте: /pay [сумма]\n"
                 "Пример: <code>/pay 100</code>",
            parse_mode='HTML',
            reply_to_message_id=message.message_id
        )

@dp.message(F.text)
async def menu_handler(message: Message):
    if not is_private_chat(message):
        # Обработка сообщений в группах
        text = message.text.strip()
        text_lower = text.lower()
        user = message.from_user
        user_id = str(user.id)
        users_data = load_users_data()

        if text_lower in ['бал', 'баланс', 'balance', '/бал', '/баланс', '/balance']:
            if user_id in users_data:
                user_info = users_data[user_id]
                balance = user_info.get('balance', 0)
                balance_rounded = round(balance, 2)

                if user.username:
                    user_display = f"@{user.username}"
                else:
                    user_display = user.first_name

                balance_text = f"""
👤 <b>{user_display}</b>
💰 <b>Баланс:</b> {balance_rounded}₽
"""
                await message.answer(
                    text=balance_text,
                    parse_mode='HTML',
                    reply_to_message_id=message.message_id
                )
            else:
                await message.answer(
                    text="❌ Сначала напишите /start в личные сообщения боту",
                    reply_to_message_id=message.message_id
                )
        return

    # Обработка в личных сообщениях
    text = message.text
    user = message.from_user
    user_id = str(user.id)
    users_data = load_users_data()

    if text == "❄️ Профиль" or text.lower() in ['профиль', 'профил', '/профиль', '/profile', 'profile']:
        if user_id not in users_data:
            await message.answer("❌ Сначала зарегистрируйтесь через /start")
            return

        user_info = users_data[user_id]
        username = user.username if user.username else user.first_name
        balance = user_info.get('balance', 0)
        balance_rounded = round(balance, 2)
        first_seen = datetime.fromisoformat(user_info['first_seen'])
        days_in_project = (datetime.now() - first_seen).days

        total_deposits = user_info.get('total_deposits', 0)
        total_withdrawals = user_info.get('total_withdrawals', 0)

        avatar_file_id = await get_user_avatar(user.id)

        profile_text = f"""
<blockquote expandable>╔══════════════════════╗
   ❄️ <b>FESTERY PROFILE</b> ❄️
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

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📥 ПОПОЛНИТЬ", callback_data="profile_deposit"),
                InlineKeyboardButton(text="📤 ВЫВЕСТИ", callback_data="profile_withdraw")
            ],
            [
                InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")
            ]
        ])

        if avatar_file_id:
            try:
                await message.answer_photo(
                    photo=avatar_file_id,
                    caption=profile_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Ошибка отправки фото: {e}")
                await message.answer(
                    text=profile_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
        else:
            await message.answer(
                text=profile_text,
                reply_markup=markup,
                parse_mode='HTML'
            )

    elif text == "👥 Рефералы" or text.lower() in ['/рефералы', 'рефералы']:
        try:
            user_id = str(message.from_user.id)
            users_data = load_users_data()

            if user_id not in users_data:
                await message.answer("❌ Сначала зарегистрируйтесь через /start")
                return

            user_info = users_data[user_id]
            referral_bonus_balance = user_info.get('referral_bonus', 0)
            total_referral_income = user_info.get('total_referral_income', 0)
            referral_count = len(user_info.get('referrals', []))

            try:
                bot_info = await bot.get_me()
                BOT_USERNAME = bot_info.username
            except:
                BOT_USERNAME = "YOUR_BOT_USERNAME"

            referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"

            withdraw_text = "💸 Вывести на баланс"
            if referral_bonus_balance < 300:
                withdraw_text = f"💸 Вывести на баланс (нужно {300-referral_bonus_balance}₽)"

            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=withdraw_text, callback_data="withdraw_referral")],
                [InlineKeyboardButton(text="📋 Мои рефералы", callback_data="my_referrals")],
                [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=f"Присоединяйся к игре! 🔥\n{referral_link}")],
                [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]
            ])

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

            await message.answer(
                text=referral_text,
                parse_mode='HTML',
                reply_markup=markup
            )

        except Exception as e:
            print(f"Ошибка при показе рефералов: {e}")
            await message.answer(
                text="❌ Ошибка при загрузке реферальной системы",
                reply_markup=get_main_inline_menu()
            )

    elif text == "🏆 ТОП Игроков" or text.lower() in ['/топ', 'топ']:
        from leaders import show_leaders
        await show_leaders(bot, message)

    elif text == "ℹ️ О проекте" or text.lower() in ['/о проекте', 'о проекте']:
        info_text = """
<blockquote expandable>╔══════════════════════╗
   ❄️ <b>FESTERY GAME</b> ❄️
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

<i>❄️ Присоединяйся к Festery Game сегодня!</i>
"""

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]
        ])

        await message.answer(
            text=info_text,
            parse_mode='HTML',
            reply_markup=markup
        )

    elif text == "🎮 Игры" or text.lower() in ['/games', 'games', '/игры', 'игры']:
        if user_id not in users_data:
            await message.answer("❌ Сначала зарегистрируйтесь через /start")
            return

        balance_text, markup = games_inline_menu(user_id)

        games_text = f"""
<blockquote expandable>╔══════════════════════╗
   🎮 <b>FLAME GAMES</b> 🎮
╚══════════════════════╝</blockquote>

{balance_text}
"""
        await message.answer(
            text=games_text,
            parse_mode='HTML',
            reply_markup=markup
        )

    elif text.strip().lower() in ['бал', 'баланс', 'balance', '/бал', '/баланс', '/balance']:
        if user_id in users_data:
            user_info = users_data[user_id]
            balance = user_info.get('balance', 0)
            balance_rounded = round(balance, 2)

            if user.username:
                user_display = f"@{user.username}"
            else:
                user_display = user.first_name

            balance_text = f"""
👤 <b>{user_display}</b>
💰 <b>Баланс:</b> {balance_rounded}₽
"""
            await message.answer(
                text=balance_text,
                parse_mode='HTML',
                reply_to_message_id=message.message_id
            )
        else:
            await message.answer("❌ Сначала зарегистрируйтесь через /start")

    else:
        await message.answer(
            text=f"✨ <b>Добро пожаловать, {user.first_name}!</b>",
            parse_mode='HTML',
            reply_markup=get_main_inline_menu()
        )

# Вебхук обработчик
async def webhook_handler(request):
    try:
        update = types.Update(**await request.json())
        await dp.feed_update(bot, update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {e}")
        return web.Response(status=500)

@app.route(WEBHOOK_URL_PATH, methods=['POST'])
async def webhook(request):
    return await webhook_handler(request)

@app.route('/')
async def index(request):
    return web.Response(text='Bot is running!')

@app.route('/health')
async def health(request):
    return web.Response(text='OK', status=200)

@app.route('/set_webhook')
async def set_webhook_route(request):
    try:
        await bot.delete_webhook()
        await bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)
        return web.Response(text=f'Вебхук установлен: {WEBHOOK_URL_BASE + WEBHOOK_URL_PATH}')
    except Exception as e:
        return web.Response(text=f'Ошибка: {str(e)}')

async def set_webhook():
    try:
        await bot.delete_webhook()
        await bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)
        print(f"Вебхук установлен: {WEBHOOK_URL_BASE + WEBHOOK_URL_PATH}")
        return True
    except Exception as e:
        print(f"Ошибка установки вебхука: {e}")
        return False

async def on_startup():
    await set_webhook()

async def on_shutdown():
    await bot.delete_webhook()
    await dp.storage.close()

async def main():
    if RENDER:
        # Запуск с вебхуком
        port = int(os.environ.get('PORT', 10000))
        app.on_startup.append(lambda app: asyncio.create_task(on_startup()))
        app.on_shutdown.append(lambda app: asyncio.create_task(on_shutdown()))
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"Сервер запущен на порту {port}")
        
        # Держим приложение запущенным
        await asyncio.Event().wait()
    else:
        # Запуск в режиме long polling
        print("Запуск в режиме long polling")
        await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
