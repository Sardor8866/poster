import telebot
from telebot import types
import json
import logging
import random
import string
import requests
import time
import threading
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    from leaders import update_game_history
except ImportError:
    def update_game_history(user_id, game_data):
        logging.warning(f"Модуль лидеров не найден, транзакция не записана в историю: {user_id}")
        return False

CRYPTOBOT_TOKEN = "477733:AAzooy5vcnCpJuGgTZc1Rdfbu71bqmrRMgr"
ADMIN_ID = "8118184388"


NOTIFICATION_GROUP_ID = "-1003647626166"  

WITHDRAW_IMAGE_URL = "https://iimg.su/i/2GviVX" 
DEPOSIT_IMAGE_URL = "https://iimg.su/i/3yvm27"   

MIN_DEPOSIT_RUB = 50
MIN_WITHDRAW_RUB = 300
MAX_DEPOSIT_RUB = 500000
MAX_WITHDRAW_RUB = 500000

TREASURY_MODE = "real"
PENDING_WITHDRAWALS_FILE = 'pending_withdrawals.json'

user_last_action = {}
pending_invoices = {}
user_states = {}
admin_states = {}

# Блокировка для защиты от дублирования вывода средств
withdraw_lock = threading.Lock()

exchange_rates = {
    "USD_RUB": None,
    "last_updated": None
}

def load_users_data():
    try:
        with open('users_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_users_data(data):
    try:
        with open('users_data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения данных: {e}")

def load_transactions():
    """Загружает историю транзакций"""
    try:
        with open('transactions.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        logging.error(f"Ошибка загрузки транзакций: {e}")
        return []

def save_transactions(transactions):
    """Сохраняет историю транзакций"""
    try:
        with open('transactions.json', 'w', encoding='utf-8') as f:
            json.dump(transactions, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logging.error(f"Ошибка сохранения транзакций: {e}")
        return False

def load_pending_withdrawals():
    """Загружает ожидающие выводы"""
    try:
        with open(PENDING_WITHDRAWALS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        logging.error(f"Ошибка загрузки ожидающих выводов: {e}")
        return []

def save_pending_withdrawals(withdrawals):
    """Сохраняет ожидающие выводы"""
    try:
        with open(PENDING_WITHDRAWALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(withdrawals, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logging.error(f"Ошибка сохранения ожидающих выводов: {e}")
        return False

def add_pending_withdrawal(user_id, amount_rub, username, crypto_type="USDT"):
    """Добавляет вывод в ожидание"""
    try:
        with withdraw_lock:
            # Повторная проверка баланса внутри блокировки
            users_data = load_users_data()
            user_id_str = str(user_id)
            current_balance = users_data.get(user_id_str, {}).get('balance', 0)
            
            if current_balance < amount_rub:
                logging.warning(f"Недостаточно средств для вывода: {user_id}, баланс: {current_balance}, запрошено: {amount_rub}")
                return None
            
            withdrawals = load_pending_withdrawals()

            withdrawal = {
                'id': len(withdrawals) + 1,
                'user_id': int(user_id),
                'username': username,
                'amount_rub': float(amount_rub),
                'amount_usd': round(float(amount_rub) / get_exchange_rate(), 6),
                'crypto_type': crypto_type,
                'status': 'pending',
                'created_at': int(time.time()),
                'processed_by': None,
                'processed_at': None
            }

            withdrawals.append(withdrawal)

            if save_pending_withdrawals(withdrawals):
                logging.info(f"✅ Вывод добавлен в ожидание: {user_id}, {amount_rub} ₽")
                return withdrawal['id']
            else:
                logging.error(f"❌ Ошибка сохранения вывода для {user_id}")
                return None

    except Exception as e:
        logging.error(f"Ошибка в add_pending_withdrawal: {e}")
        return None

def remove_pending_withdrawal(withdrawal_id):
    """Удаляет вывод из ожидания"""
    try:
        withdrawals = load_pending_withdrawals()

        for i, withdrawal in enumerate(withdrawals):
            if withdrawal['id'] == withdrawal_id:
                del withdrawals[i]
                if save_pending_withdrawals(withdrawals):
                    logging.info(f"✅ Вывод {withdrawal_id} удален из ожидания")
                    return True

        return False
    except Exception as e:
        logging.error(f"Ошибка удаления вывода: {e}")
        return False

def get_pending_withdrawal(withdrawal_id):
    """Получает информацию о выводе"""
    try:
        withdrawals = load_pending_withdrawals()

        for withdrawal in withdrawals:
            if withdrawal['id'] == withdrawal_id:
                return withdrawal

        return None
    except Exception as e:
        logging.error(f"Ошибка получения вывода: {e}")
        return None

def update_pending_withdrawal_status(withdrawal_id, status, admin_id=None):
    """Обновляет статус вывода"""
    try:
        withdrawals = load_pending_withdrawals()

        for withdrawal in withdrawals:
            if withdrawal['id'] == withdrawal_id:
                withdrawal['status'] = status
                withdrawal['processed_at'] = int(time.time())
                if admin_id:
                    withdrawal['processed_by'] = int(admin_id)

                if save_pending_withdrawals(withdrawals):
                    logging.info(f"✅ Статус вывода {withdrawal_id} обновлен на {status}")
                    return True

        return False
    except Exception as e:
        logging.error(f"Ошибка обновления статуса вывода: {e}")
        return False

def add_transaction(user_id, amount, transaction_type, status="completed", crypto_type="USDT", withdrawal_id=None):
    """Добавляет транзакцию в историю"""
    try:
        transactions = load_transactions()

        transaction = {
            'user_id': int(user_id),
            'amount': float(amount),
            'type': transaction_type,
            'status': status,
            'crypto_type': crypto_type,
            'timestamp': int(time.time()),
            'withdrawal_id': withdrawal_id
        }

        transactions.append(transaction)

        if len(transactions) > 1000:
            transactions = transactions[-1000:]

        if save_transactions(transactions):
            logging.info(f"✅ Транзакция добавлена: {user_id}, {transaction_type}, {amount} ₽")

            try:
                if transaction_type == 'deposit':
                    update_game_history(user_id, {
                        'game_type': 'deposit',
                        'bet_amount': 0,
                        'win_amount': float(amount),
                        'is_win': True,
                        'timestamp': int(time.time())
                    })
                elif transaction_type == 'withdraw' and status == 'completed':
                    update_game_history(user_id, {
                        'game_type': 'withdraw',
                        'bet_amount': 0,
                        'win_amount': -float(amount),
                        'is_win': False,
                        'timestamp': int(time.time())
                    })
            except Exception as e:
                logging.error(f"Ошибка добавления транзакции в историю лидеров: {e}")

            return True
        else:
            logging.error(f"❌ Ошибка сохранения транзакции для {user_id}")
            return False

    except Exception as e:
        logging.error(f"Ошибка в add_transaction: {e}")
        return False

def send_notification_to_group(bot, transaction_type, username, amount_rub):
    """
    Отправляет уведомление в групповой чат с изображением
    
    Args:
        bot: экземпляр TeleBot
        transaction_type: 'deposit' или 'withdraw'
        username: имя пользователя
        amount_rub: сумма в рублях
    """
    try:
        # Работает только для реальной казны
        if TREASURY_MODE != "real":
            logging.info(f"Уведомления отключены для тестового режима")
            return
        
        if transaction_type == "deposit":
            image_url = DEPOSIT_IMAGE_URL
            emoji = "✅"
            action = "ПОПОЛНЕНИЕ"
        elif transaction_type == "withdraw":
            image_url = WITHDRAW_IMAGE_URL
            emoji = "✅"
            action = "ВЫВОД"
        else:
            logging.error(f"Неизвестный тип транзакции: {transaction_type}")
            return
        
        # Формируем текст сообщения
        message_text = f"""
{emoji} <b>УСПЕШНЫЙ {action}</b>

👤Игрок: @{username}
💸Сумма: {amount_rub:.2f} ₽
"""
        
        # Отправляем фото с текстом в группу
        bot.send_photo(
            chat_id=NOTIFICATION_GROUP_ID,
            photo=image_url,
            caption=message_text,
            parse_mode='HTML'
        )
        
        logging.info(f"✅ Уведомление о {action} отправлено в группу")
        
    except Exception as e:
        logging.error(f"❌ Ошибка отправки уведомления в группу: {e}")

def get_exchange_rate():
    """Получает актуальный курс USD/RUB"""
    try:
        response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
        if response.status_code == 200:
            data = response.json()
            usd_rate = data['Valute']['USD']['Value']
            exchange_rates["USD_RUB"] = usd_rate
            exchange_rates["last_updated"] = time.time()
            logging.info(f"Курс обновлен: 1 USD = {usd_rate} RUB")
            return usd_rate

        response = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
        if response.status_code == 200:
            data = response.json()
            usd_rate = data['rates']['RUB']
            exchange_rates["USD_RUB"] = usd_rate
            exchange_rates["last_updated"] = time.time()
            logging.info(f"Курс обновлен: 1 USD = {usd_rate} RUB")
            return usd_rate

        logging.warning("API курсов недоступны, использую фиксированный курс 90")
        return 90.0

    except Exception as e:
        logging.error(f"Ошибка получения курса: {e}")
        return exchange_rates.get("USD_RUB", 90.0)

def convert_rub_to_usd(rub_amount):
    """Конвертирует рубли в доллары по текущему курсу"""
    usd_rate = get_exchange_rate()
    usd_amount = rub_amount / usd_rate
    return round(usd_amount, 6)

def convert_usd_to_rub(usd_amount):
    """Конвертирует доллары в рубли по текущему курсу"""
    usd_rate = get_exchange_rate()
    rub_amount = usd_amount * usd_rate
    return round(rub_amount, 2)

def test_cryptobot_connection():
    """Тестирует подключение к CryptoBot API"""
    try:
        result = cryptobot_api_request("getMe")
        if result and result.get('ok'):
            logging.info(f"CryptoBot подключение успешно: {result['result']}")
            return True
        else:
            logging.error(f"Ошибка подключения к CryptoBot: {result}")
            return False
    except Exception as e:
        logging.error(f"Ошибка тестирования подключения: {e}")
        return False

def get_treasury_balance():
    """Получает баланс казны в USDT и конвертирует в рубли"""
    try:
        result = cryptobot_api_request("getBalance")

        if result and result.get('ok'):
            balances = result['result']

            for balance in balances:
                currency_code = balance.get('currency_code', '')
                available = float(balance.get('available', 0))

                if currency_code.upper() == 'USDT':
                    rub_amount = convert_usd_to_rub(available)
                    logging.info(f"USDT баланс: ${available} ≈ {rub_amount} RUB")
                    return available, rub_amount

            logging.warning("USDT баланс не найден среди доступных валют")
            return 0, 0

        else:
            error_msg = result.get('error', {}).get('name', 'Unknown error') if result else 'No response'
            logging.error(f"Ошибка получения баланса казны: {error_msg}")
            return 0, 0

    except Exception as e:
        logging.error(f"Исключение при получении баланса казны: {e}")
        return 0, 0

def get_test_treasury_balance():
    """Получает тестовый баланс казны из файла"""
    try:
        with open('test_treasury.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('balance_usd', 0), data.get('balance_rub', 0)
    except FileNotFoundError:
        initial_balance = {'balance_usd': 1000.0, 'balance_rub': 90000.0}
        with open('test_treasury.json', 'w', encoding='utf-8') as f:
            json.dump(initial_balance, f, ensure_ascii=False, indent=2)
        return 1000.0, 90000.0
    except Exception as e:
        logging.error(f"Ошибка получения тестового баланса: {e}")
        return 0, 0

def set_test_treasury_balance(amount_rub):
    """Устанавливает тестовый баланс казны"""
    try:
        amount_usd = convert_rub_to_usd(amount_rub)
        data = {'balance_usd': amount_usd, 'balance_rub': amount_rub}
        with open('test_treasury.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logging.info(f"Тестовый баланс установлен: {amount_usd} USD ≈ {amount_rub} RUB")
        return True
    except Exception as e:
        logging.error(f"Ошибка установки тестового баланса: {e}")
        return False

def adjust_test_treasury_balance(amount_rub, operation='add'):
    """Корректирует тестовый баланс казны"""
    try:
        current_usd, current_rub = get_test_treasury_balance()

        if operation == 'add':
            new_rub = current_rub + amount_rub
        elif operation == 'subtract':
            new_rub = current_rub - amount_rub
            if new_rub < 0:
                new_rub = 0
        else:
            return False

        new_usd = convert_rub_to_usd(new_rub)
        data = {'balance_usd': new_usd, 'balance_rub': new_rub}

        with open('test_treasury.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logging.info(f"Тестовый баланс скорректирован: {new_usd} USD ≈ {new_rub} RUB")
        return True
    except Exception as e:
        logging.error(f"Ошибка корректировки тестового баланса: {e}")
        return False

def check_cooldown(user_id, action_type):
    """Проверяет задержку между действиями"""
    current_time = time.time()
    key = f"{user_id}_{action_type}"

    if key in user_last_action:
        elapsed = current_time - user_last_action[key]

        if action_type == "deposit" and elapsed < 120:
            return False, f"⏳ Пополнение доступно через {120 - int(elapsed)} сек."
        elif action_type == "withdraw" and elapsed < 180:
            return False, f"⏳ Вывод доступен через {180 - int(elapsed)} сек."
        elif action_type == "button" and elapsed < 2:
            return False, "⏳ Не так быстро!"

    user_last_action[key] = current_time
    return True, ""

def generate_invoice_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

def cryptobot_api_request(method, data=None):
    """Упрощенный запрос к CryptoBot API"""
    try:
        headers = {
            'Crypto-Pay-API-Token': CRYPTOBOT_TOKEN,
            'Content-Type': 'application/json'
        }

        url = f"https://pay.crypt.bot/api/{method}"

        logging.info(f"CryptoBot API Request: {method}")

        if data:
            response = requests.post(url, json=data, headers=headers, timeout=10)
        else:
            response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            result = response.json()
            return result
        else:
            logging.error(f"HTTP Error {response.status_code}: {response.text}")
            return None

    except Exception as e:
        logging.error(f"CryptoBot API Error: {e}")
        return None

def get_invoice_status(invoice_id):
    """Получает статус инвойса"""
    try:
        result = cryptobot_api_request("getInvoices", {
            "invoice_ids": str(invoice_id)
        })

        if result and result.get('ok') and result['result'].get('items'):
            return result['result']['items'][0]
        return None
    except Exception as e:
        logging.error(f"Ошибка получения статуса инвойса: {e}")
        return None

def create_cryptobot_invoice(amount_rub, crypto_type="USDT"):
    """Создает инвойс для пополнения в указанной криптовалюте"""
    try:
        amount_usd = convert_rub_to_usd(amount_rub)

        min_crypto_amount = 0.01
        if amount_usd < min_crypto_amount:
            amount_usd = min_crypto_amount

        data = {
            "asset": crypto_type,
            "amount": str(amount_usd),
            "description": f"Пополнение баланса на {amount_rub} RUB",
            "paid_btn_name": "openBot",
            "paid_btn_url": "https://t.me/your_bot",
            "payload": generate_invoice_id(),
            "allow_comments": False,
            "allow_anonymous": False,
            "expires_in": 600
        }

        result = cryptobot_api_request("createInvoice", data)

        if result and result.get('ok'):
            invoice_data = result['result']
            invoice_data['amount_rub'] = amount_rub
            invoice_data['amount_usd'] = amount_usd
            return invoice_data
        else:
            error_msg = result.get('error', {}).get('name', 'Unknown error') if result else 'No response'
            logging.error(f"Ошибка создания инвойса: {error_msg}")
            return None

    except Exception as e:
        logging.error(f"Exception in create_cryptobot_invoice: {e}")
        return None

def create_cryptobot_check(amount_rub, user_id, crypto_type="USDT"):
    """Создает чек для вывода в указанной криптовалюте"""
    try:
        amount_usd = convert_rub_to_usd(amount_rub)

        min_crypto_amount = 0.01
        if amount_usd < min_crypto_amount:
            amount_usd = min_crypto_amount

        data = {
            "asset": crypto_type,
            "amount": str(amount_usd),
            "pin_to_user_id": int(user_id),
            "description": f"Вывод средств {amount_rub} RUB",
        }

        result = cryptobot_api_request("createCheck", data)

        if result and result.get('ok'):
            check_data = result['result']
            check_data['amount_rub'] = amount_rub
            check_data['amount_usd'] = amount_usd
            return check_data
        else:
            error_msg = result.get('error', {}).get('name', 'Unknown error') if result else 'No response'
            logging.error(f"Ошибка создания чека: {error_msg}")
            return None

    except Exception as e:
        logging.error(f"Exception in create_cryptobot_check: {e}")
        return None

def get_deposit_keyboard():
    markup = types.InlineKeyboardMarkup()
    amounts_rub = ["50", "100", "300", "500", "1000", "5000"]
    buttons = [types.InlineKeyboardButton(f"{amount} ₽", callback_data=f"crypto_deposit_{amount}") for amount in amounts_rub]
    markup.row(*buttons[:3])
    markup.row(*buttons[3:])
    markup.row(types.InlineKeyboardButton("📝 Другая сумма", callback_data="crypto_deposit_custom"))
    markup.row(types.InlineKeyboardButton("⬅️ Назад", callback_data="crypto_back_profile"))
    return markup

def get_withdraw_keyboard():
    markup = types.InlineKeyboardMarkup()
    amounts_rub = ["300", "500", "1000", "5000", "10000", "50000"]
    buttons = [types.InlineKeyboardButton(f"{amount} ₽", callback_data=f"crypto_withdraw_{amount}") for amount in amounts_rub]
    markup.row(*buttons[:3])
    markup.row(*buttons[3:])
    markup.row(types.InlineKeyboardButton("📝 Другая сумма", callback_data="crypto_withdraw_custom"))
    markup.row(types.InlineKeyboardButton("⬅️ Назад", callback_data="crypto_back_profile"))
    return markup

def get_crypto_choice_keyboard():
    """Клавиатура выбора криптовалюты для пополнения"""
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("💎 USDT (TRC20)", callback_data="crypto_type_usdt"),
        types.InlineKeyboardButton("⚡ TON", callback_data="crypto_type_ton")
    )
    markup.row(types.InlineKeyboardButton("⬅️ Назад", callback_data="profile_deposit"))
    return markup

def register_crypto_handlers(bot):
    """Регистрация обработчиков"""

    logging.info("Тестируем подключение к CryptoBot API...")
    if test_cryptobot_connection():
        logging.info("✅ Подключение к CryptoBot API успешно")
    else:
        logging.error("❌ Ошибка подключения к CryptoBot API")

    initial_balance_usd, initial_balance_rub = get_treasury_balance()
    logging.info(f"Начальный баланс казны: ${initial_balance_usd} ≈ {initial_balance_rub} ₽")

    current_rate = get_exchange_rate()
    logging.info(f"Текущий курс: 1 USD = {current_rate} RUB")


    """
    📋 ДОСТУПНЫЕ КОМАНДЫ АДМИНА:

    1. /admin - Главное меню админ-панели
    2. /check - Управление выводами (основные команды)
    3. /kazna - Управление казной (основные команды)

    📁 КОМАНДЫ УПРАВЛЕНИЯ ВЫВОДАМИ (/check):
    - /check pending - Показать ожидающие выводы
    - /check list - Список всех выводов
    - /check completed - Завершенные выводы
    - /check rejected - Отклоненные выводы
    - /check approve [ID] - Одобрить вывод (пример: /check approve 5)
    - /check reject [ID] - Отклонить вывод (пример: /check reject 5)
    - /check info [ID] - Информация о выводе

    💰 КОМАНДЫ УПРАВЛЕНИЯ КАЗНОЙ (/kazna):
    - /kazna balance - Показать баланс казны
    - /kazna mode - Показать/изменить режим казны
    - /kazna real - Переключить в реальный режим
    - /kazna test - Переключить в тестовый режим
    - /kazna adjust [сумма] - Изменить баланс (пример: /kazna adjust 1000)
    - /kazna rate - Показать курс валют
    - /kazna update - Обновить курс вручную
    """

    @bot.message_handler(commands=['admin'])
    def admin_command(message):
        try:
            user_id = str(message.from_user.id)

            if user_id != ADMIN_ID:
                bot.send_message(message.chat.id, "❌ Команда доступна только администратору")
                return

            display = f"""
<blockquote expandable>╔══════════════════════╗
   🔧 <b>АДМИН ПАНЕЛЬ</b> 🔧
╚══════════════════════╝</blockquote>

<blockquote>
👤 <b>Администратор:</b> @{message.from_user.username or message.from_user.first_name}
🆔 <b>ID:</b> <code>{user_id}</code>
📅 <b>Дата:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
</blockquote>

📋 <b>ОСНОВНЫЕ КОМАНДЫ:</b>

<code>/check</code> - Управление выводами
<code>/kazna</code> - Управление казной

━━━━━━━━━━━━━━━━━━━━
📁 <b>КОМАНДЫ УПРАВЛЕНИЯ ВЫВОДАМИ:</b>
<code>/check pending</code> - Ожидающие выводы
<code>/check list</code> - Список всех выводов
<code>/check completed</code> - Завершенные выводы
<code>/check rejected</code> - Отклоненные выводы
<code>/check approve [ID]</code> - Одобрить вывод
<code>/check reject [ID]</code> - Отклонить вывод

━━━━━━━━━━━━━━━━━━━━
💰 <b>КОМАНДЫ УПРАВЛЕНИЯ КАЗНОЙ:</b>
<code>/kazna balance</code> - Баланс казны
<code>/kazna mode</code> - Режим казны
<code>/kazna real</code> - Реальный режим
<code>/kazna test</code> - Тестовый режим
<code>/kazna adjust [сумма]</code> - Изменить баланс
<code>/kazna rate</code> - Курс валют
<code>/kazna update</code> - Обновить курс
"""

            remove_keyboard = types.ReplyKeyboardRemove()

            bot.send_message(
                message.chat.id,
                display,
                parse_mode='HTML',
                reply_markup=remove_keyboard
            )

        except Exception as e:
            logging.error(f"Ошибка в admin_command: {e}")
            bot.send_message(message.chat.id, "❌ Ошибка")


    @bot.message_handler(commands=['check'])
    def check_command(message):
        try:
            user_id = str(message.from_user.id)

            if user_id != ADMIN_ID:
                bot.send_message(message.chat.id, "❌ Команда доступна только администратору")
                return

            args = message.text.split()

            if len(args) == 1:
                pending_count = len([w for w in load_pending_withdrawals() if w['status'] == 'pending'])
                completed_count = len([w for w in load_pending_withdrawals() if w['status'] == 'completed'])
                rejected_count = len([w for w in load_pending_withdrawals() if w['status'] == 'rejected'])

                display = f"""
<blockquote expandable>╔══════════════════════╗
   📋 <b>УПРАВЛЕНИЕ ВЫВОДАМИ</b> 📋
╚══════════════════════╝</blockquote>

<blockquote>
👤 <b>Администратор:</b> @{message.from_user.username or message.from_user.first_name}
🆔 <b>ID:</b> <code>{user_id}</code>
📅 <b>Дата:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━
📊 <b>Статистика выводов:</b>
⏳ <b>Ожидают:</b> {pending_count}
✅ <b>Завершены:</b> {completed_count}
❌ <b>Отклонены:</b> {rejected_count}
</blockquote>

📁 <b>КОМАНДЫ:</b>

<code>/check pending</code> - Ожидающие выводы
<code>/check list</code> - Список всех выводов
<code>/check completed</code> - Завершенные выводы
<code>/check rejected</code> - Отклоненные выводы
<code>/check approve [ID]</code> - Одобрить вывод
<code>/check reject [ID]</code> - Отклонить вывод
<code>/check info [ID]</code> - Информация о выводе

📝 <b>Примеры:</b>
<code>/check approve 5</code> - одобрить вывод
<code>/check reject 3</code> - отклонить вывод
<code>/check info 1</code> - информация о выводе
"""

                bot.send_message(
                    message.chat.id,
                    display,
                    parse_mode='HTML'
                )

            elif len(args) >= 2:
                command = args[1].lower()

                if command == "pending":
                    withdrawals = load_pending_withdrawals()
                    pending_withdrawals = [w for w in withdrawals if w['status'] == 'pending']

                    if not pending_withdrawals:
                        bot.send_message(message.chat.id, "📭 <b>Нет ожидающих выводов</b>", parse_mode='HTML')
                        return

                    display = f"<b>⏳ ОЖИДАЮЩИЕ ВЫВОДЫ ({len(pending_withdrawals)}):</b>\n\n"

                    for w in pending_withdrawals:
                        created_time = datetime.fromtimestamp(w['created_at']).strftime('%d.%m %H:%M')
                        display += f"<b>#{w['id']}</b> | {w['amount_rub']:.0f}₽ | @{w['username']} | {created_time}\n"
                        display += f"   <code>/check approve {w['id']}</code> - одобрить\n"
                        display += f"   <code>/check reject {w['id']}</code> - отклонить\n\n"

                    bot.send_message(message.chat.id, display, parse_mode='HTML')

                elif command == "list":
                    withdrawals = load_pending_withdrawals()

                    if not withdrawals:
                        bot.send_message(message.chat.id, "📭 <b>История выводов пуста</b>", parse_mode='HTML')
                        return

                    recent_withdrawals = sorted(withdrawals, key=lambda x: x['created_at'], reverse=True)[:20]

                    display = f"<b>📋 ПОСЛЕДНИЕ ВЫВОДЫ ({len(recent_withdrawals)} из {len(withdrawals)}):</b>\n\n"

                    for w in recent_withdrawals:
                        status_icon = "⏳" if w['status'] == 'pending' else "✅" if w['status'] == 'completed' else "❌"
                        time_str = datetime.fromtimestamp(w['created_at']).strftime('%d.%m %H:%M')
                        display += f"{status_icon} <b>#{w['id']}</b> | {w['amount_rub']:.0f}₽ | @{w['username']} | {time_str}\n"

                    bot.send_message(message.chat.id, display, parse_mode='HTML')

                elif command == "completed":
                    withdrawals = load_pending_withdrawals()
                    completed_withdrawals = [w for w in withdrawals if w['status'] == 'completed']

                    if not completed_withdrawals:
                        bot.send_message(message.chat.id, "📭 <b>Нет завершенных выводов</b>", parse_mode='HTML')
                        return

                    recent_withdrawals = sorted(completed_withdrawals, key=lambda x: x['processed_at'] if x['processed_at'] else x['created_at'], reverse=True)[:20]

                    display = f"<b>✅ ЗАВЕРШЕННЫЕ ВЫВОДЫ ({len(recent_withdrawals)} из {len(completed_withdrawals)}):</b>\n\n"

                    for w in recent_withdrawals:
                        time_str = datetime.fromtimestamp(w['created_at']).strftime('%d.%m %H:%M')
                        admin_info = f" | админ: {w['processed_by']}" if w['processed_by'] else ""
                        display += f"✅ <b>#{w['id']}</b> | {w['amount_rub']:.0f}₽ | @{w['username']} | {time_str}{admin_info}\n"

                    bot.send_message(message.chat.id, display, parse_mode='HTML')

                elif command == "rejected":
                    withdrawals = load_pending_withdrawals()
                    rejected_withdrawals = [w for w in withdrawals if w['status'] == 'rejected']

                    if not rejected_withdrawals:
                        bot.send_message(message.chat.id, "📭 <b>Нет отклоненных выводов</b>", parse_mode='HTML')
                        return

                    recent_withdrawals = sorted(rejected_withdrawals, key=lambda x: x['processed_at'] if x['processed_at'] else x['created_at'], reverse=True)[:20]

                    display = f"<b>❌ ОТКЛОНЕННЫЕ ВЫВОДЫ ({len(recent_withdrawals)} из {len(rejected_withdrawals)}):</b>\n\n"

                    for w in recent_withdrawals:
                        time_str = datetime.fromtimestamp(w['created_at']).strftime('%d.%m %H:%M')
                        admin_info = f" | админ: {w['processed_by']}" if w['processed_by'] else ""
                        display += f"❌ <b>#{w['id']}</b> | {w['amount_rub']:.0f}₽ | @{w['username']} | {time_str}{admin_info}\n"

                    bot.send_message(message.chat.id, display, parse_mode='HTML')

                elif command == "approve":
                    if len(args) < 3:
                        bot.send_message(message.chat.id, "❌ Укажите ID вывода\nПример: <code>/check approve 5</code>", parse_mode='HTML')
                        return

                    try:
                        withdrawal_id = int(args[2])
                        withdrawal = get_pending_withdrawal(withdrawal_id)

                        if not withdrawal:
                            bot.send_message(message.chat.id, f"❌ Вывод #{withdrawal_id} не найден")
                            return

                        if withdrawal['status'] != 'pending':
                            bot.send_message(message.chat.id, f"❌ Вывод #{withdrawal_id} уже обработан")
                            return

                        if TREASURY_MODE == "real":
                            check = create_cryptobot_check(withdrawal['amount_rub'], withdrawal['user_id'], withdrawal['crypto_type'])

                            if not check:
                                bot.send_message(message.chat.id, "❌ Ошибка создания чека")
                                return

                            update_pending_withdrawal_status(withdrawal_id, 'completed', user_id)

                            try:
                                user_display = f"""
<blockquote expandable>╔══════════════════════╗
   ✅ <b>ВЫВОД ОДОБРЕН</b> ✅
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Сумма:</b> {withdrawal['amount_rub']:.2f} ₽
💎 <b>Крипта:</b> {withdrawal['crypto_type']}
🔢 <b>К получению:</b> {check['amount_usd']} {withdrawal['crypto_type']}
</blockquote>

💎 <i>Для получения нажмите кнопку:</i>
"""

                                markup = types.InlineKeyboardMarkup()
                                markup.row(types.InlineKeyboardButton("💳 Получить чек", url=check['bot_check_url']))

                                bot.send_message(
                                    withdrawal['user_id'],
                                    user_display,
                                    parse_mode='HTML',
                                    reply_markup=markup
                                )
                            except Exception as e:
                                logging.error(f"Ошибка отправки чека пользователю: {e}")

                            bot.send_message(message.chat.id, f"✅ Вывод #{withdrawal_id} одобрен, чек создан")

                        else:
                            update_pending_withdrawal_status(withdrawal_id, 'completed', user_id)

                            try:
                                user_display = f"""
<blockquote expandable>╔══════════════════════╗
   ✅ <b>ВЫВОД ОДОБРЕН</b> ✅
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Сумма:</b> {withdrawal['amount_rub']:.2f} ₽
💎 <b>Крипта:</b> {withdrawal['crypto_type']}
🔢 <b>К получению:</b> {withdrawal['amount_usd']:.6f} {withdrawal['crypto_type']}
</blockquote>

✅ <i>Вывод успешно обработан администратором</i>
"""

                                bot.send_message(
                                    withdrawal['user_id'],
                                    user_display,
                                    parse_mode='HTML'
                                )
                            except Exception as e:
                                logging.error(f"Ошибка отправки уведомления пользователю: {e}")

                            bot.send_message(message.chat.id, f"✅ Вывод #{withdrawal_id} одобрен")

                        add_transaction(withdrawal['user_id'], withdrawal['amount_rub'], 'withdraw', 'completed', withdrawal['crypto_type'], withdrawal_id)

                    except ValueError:
                        bot.send_message(message.chat.id, "❌ Неверный ID вывода")

                elif command == "reject":
                    if len(args) < 3:
                        bot.send_message(message.chat.id, "❌ Укажите ID вывода\nПример: <code>/check reject 5</code>", parse_mode='HTML')
                        return

                    try:
                        withdrawal_id = int(args[2])
                        withdrawal = get_pending_withdrawal(withdrawal_id)

                        if not withdrawal:
                            bot.send_message(message.chat.id, f"❌ Вывод #{withdrawal_id} не найден")
                            return

                        if withdrawal['status'] != 'pending':
                            bot.send_message(message.chat.id, f"❌ Вывод #{withdrawal_id} уже обработан")
                            return

                        update_pending_withdrawal_status(withdrawal_id, 'rejected', user_id)

                        users_data = load_users_data()
                        user_id_str = str(withdrawal['user_id'])

                        if user_id_str in users_data:
                            users_data[user_id_str]['balance'] = round(
                                users_data[user_id_str].get('balance', 0) + withdrawal['amount_rub'], 2
                            )
                            save_users_data(users_data)

                        try:
                            user_display = f"""
<blockquote expandable>╔══════════════════════╗
   ❌ <b>ВЫВОД ОТКЛОНЕН</b> ❌
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Сумма:</b> {withdrawal['amount_rub']:.2f} ₽
💎 <b>Крипта:</b> {withdrawal['crypto_type']}
</blockquote>

💡 <i>Средства возвращены на ваш баланс</i>
"""

                            bot.send_message(
                                withdrawal['user_id'],
                                user_display,
                                parse_mode='HTML'
                            )
                        except Exception as e:
                            logging.error(f"Ошибка отправки уведомления пользователю: {e}")

                        bot.send_message(message.chat.id, f"❌ Вывод #{withdrawal_id} отклонен, средства возвращены пользователю")

                    except ValueError:
                        bot.send_message(message.chat.id, "❌ Неверный ID вывода")

                elif command == "info":
                    if len(args) < 3:
                        bot.send_message(message.chat.id, "❌ Укажите ID вывода\nПример: <code>/check info 5</code>", parse_mode='HTML')
                        return

                    try:
                        withdrawal_id = int(args[2])
                        withdrawal = get_pending_withdrawal(withdrawal_id)

                        if not withdrawal:
                            bot.send_message(message.chat.id, f"❌ Вывод #{withdrawal_id} не найден")
                            return

                        status_text = "⏳ ожидает" if withdrawal['status'] == 'pending' else "✅ завершен" if withdrawal['status'] == 'completed' else "❌ отклонен"
                        created_time = datetime.fromtimestamp(withdrawal['created_at']).strftime('%d.%m.%Y %H:%M:%S')

                        if withdrawal['processed_at']:
                            processed_time = datetime.fromtimestamp(withdrawal['processed_at']).strftime('%d.%m.%Y %H:%M:%S')
                            processed_info = f"📅 <b>Обработан:</b> {processed_time}\n👤 <b>Админ:</b> {withdrawal['processed_by']}"
                        else:
                            processed_info = ""

                        display = f"""
<blockquote expandable>╔══════════════════════╗
   📋 <b>ИНФОРМАЦИЯ О ВЫВОДЕ
╚══════════════════════╝</blockquote>

<blockquote>
👤 <b>Пользователь:</b> @{withdrawal['username']}
🆔 <b>ID:</b> <code>{withdrawal['user_id']}</code>
━━━━━━━━━━━━━━━━━━━━
💰 <b>Сумма:</b> {withdrawal['amount_rub']:.2f} ₽
💎 <b>Крипта:</b> {withdrawal['crypto_type']}
🔢 <b>К выдаче:</b> {withdrawal['amount_usd']:.6f} {withdrawal['crypto_type']}
━━━━━━━━━━━━━━━━━━━━
🎯 <b>Статус:</b> {status_text}
📅 <b>Создан:</b> {created_time}
{processed_info}
</blockquote>
"""

                        bot.send_message(message.chat.id, display, parse_mode='HTML')

                    except ValueError:
                        bot.send_message(message.chat.id, "❌ Неверный ID вывода")

                else:
                    bot.send_message(message.chat.id, "❌ Неизвестная команда. Используйте <code>/check</code> для списка команд", parse_mode='HTML')

        except Exception as e:
            logging.error(f"Ошибка в check_command: {e}")
            bot.send_message(message.chat.id, "❌ Ошибка")


    @bot.message_handler(commands=['kazna'])
    def kazna_command(message):
        try:
            user_id = str(message.from_user.id)

            if user_id != ADMIN_ID:
                bot.send_message(message.chat.id, "❌ Команда доступна только администратору")
                return

            args = message.text.split()

            if len(args) == 1:
                current_rate = get_exchange_rate()

                if TREASURY_MODE == "real":
                    balance_usd, balance_rub = get_treasury_balance()
                    mode_display = "💎 Реальный режим (CryptoBot)"
                else:
                    balance_usd, balance_rub = get_test_treasury_balance()
                    mode_display = "🧪 Тестовый режим"

                display = f"""
<blockquote expandable>╔══════════════════════╗
   💰 <b>УПРАВЛЕНИЕ КАЗНОЙ</b> 💰
╚══════════════════════╝</blockquote>

<blockquote>
👤 <b>Администратор:</b> @{message.from_user.username or message.from_user.first_name}
🆔 <b>ID:</b> <code>{user_id}</code>
📅 <b>Дата:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━
📊 <b>Режим:</b> {mode_display}
💰 <b>Баланс:</b> ${balance_usd:.2f} ≈ {balance_rub:.2f} ₽
📈 <b>Курс:</b> 1$ ≈ {current_rate} ₽
</blockquote>

💰 <b>КОМАНДЫ:</b>

<code>/kazna balance</code> - Баланс казны
<code>/kazna mode</code> - Режим казны
<code>/kazna real</code> - Реальный режим
<code>/kazna test</code> - Тестовый режим
<code>/kazna adjust [сумма]</code> - Изменить баланс
<code>/kazna rate</code> - Курс валют
<code>/kazna update</code> - Обновить курс

📝 <b>Примеры:</b>
<code>/kazna adjust 1000</code> - добавить 1000₽
<code>/kazna adjust -500</code> - списать 500₽
"""

                bot.send_message(
                    message.chat.id,
                    display,
                    parse_mode='HTML'
                )

            elif len(args) >= 2:
                command = args[1].lower()

                if command == "balance":
                    current_rate = get_exchange_rate()

                    if TREASURY_MODE == "real":
                        balance_usd, balance_rub = get_treasury_balance()
                        mode_display = "💎 Реальный режим (CryptoBot)"
                        source = "CryptoBot API"
                    else:
                        balance_usd, balance_rub = get_test_treasury_balance()
                        mode_display = "🧪 Тестовый режим"
                        source = "локальный файл"

                    display = f"""
<blockquote expandable>╔══════════════════════╗
   📊 <b>БАЛАНС КАЗНЫ</b> 📊
╚══════════════════════╝</blockquote>

<blockquote>
🔧 <b>Режим:</b> {mode_display}
📡 <b>Источник:</b> {source}
━━━━━━━━━━━━━━━━━━━━
💰 <b>В USDT:</b> ${balance_usd:.2f}
💵 <b>В RUB:</b> {balance_rub:.2f} ₽
📈 <b>Курс:</b> 1$ ≈ {current_rate} ₽
━━━━━━━━━━━━━━━━━━━━
⏰ <b>Обновлено:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
</blockquote>
"""

                    bot.send_message(message.chat.id, display, parse_mode='HTML')

                elif command == "mode":
                    display = f"""
<blockquote expandable>╔══════════════════════╗
   🔄 <b>РЕЖИМ КАЗНЫ</b> 🔄
╚══════════════════════╝</blockquote>

<blockquote>
<b>Текущий режим:</b> {TREASURY_MODE}
━━━━━━━━━━━━━━━━━━━━
💎 <b>Реальный режим:</b>
• Использует реальный CryptoBot
• Выводы через чеки
• Настоящие транзакции
━━━━━━━━━━━━━━━━━━━━
🧪 <b>Тестовый режим:</b>
• Использует виртуальную казну
• Выводы как заявки
• Требует ручного одобрения
</blockquote>

<b>КОМАНДЫ:</b>
<code>/kazna real</code> - переключить на реальный режим
<code>/kazna test</code> - переключить на тестовый режим
"""

                    bot.send_message(message.chat.id, display, parse_mode='HTML')

                elif command == "real":
                    def change_treasury_mode(new_mode):
                        global TREASURY_MODE
                        TREASURY_MODE = new_mode

                    change_treasury_mode("real")

                    if test_cryptobot_connection():
                        bot.send_message(message.chat.id, "✅ <b>Режим изменен на Реальный</b>\n\n💎 <i>Используется реальный CryptoBot API</i>", parse_mode='HTML')
                    else:
                        bot.send_message(message.chat.id, "⚠️ <b>Режим изменен на Реальный, но есть проблемы с подключением к CryptoBot</b>", parse_mode='HTML')

                elif command == "test":
                    def change_treasury_mode(new_mode):
                        global TREASURY_MODE
                        TREASURY_MODE = new_mode

                    change_treasury_mode("test")
                    bot.send_message(message.chat.id, "✅ <b>Режим изменен на Тестовый</b>\n\n🧪 <i>Используется виртуальная казна</i>", parse_mode='HTML')

                elif command == "adjust":
                    if TREASURY_MODE == "real":
                        bot.send_message(message.chat.id, "❌ В реальном режиме нельзя изменять баланс через команды")
                        return

                    if len(args) < 3:
                        bot.send_message(message.chat.id, "❌ Укажите сумму\nПример: <code>/kazna adjust 1000</code> - добавить 1000₽\n<code>/kazna adjust -500</code> - списать 500₽", parse_mode='HTML')
                        return

                    try:
                        amount_rub = float(args[2])

                        old_usd, old_rub = get_test_treasury_balance()

                        if amount_rub > 0:
                            adjust_test_treasury_balance(amount_rub, 'add')
                            operation = "добавлено"
                        elif amount_rub < 0:
                            adjust_test_treasury_balance(abs(amount_rub), 'subtract')
                            operation = "списано"
                        else:
                            bot.send_message(message.chat.id, "❌ Сумма не может быть нулевой")
                            return

                        new_usd, new_rub = get_test_treasury_balance()

                        display = f"""
<blockquote expandable>╔══════════════════════╗
   ✅ <b>БАЛАНС ИЗМЕНЕН</b> ✅
╚══════════════════════╝</blockquote>

<blockquote>
📊 <b>Операция:</b> {operation} {abs(amount_rub):.2f} ₽
━━━━━━━━━━━━━━━━━━━━
📉 <b>Было:</b> {old_rub:.2f} ₽ (${old_usd:.2f})
📈 <b>Стало:</b> {new_rub:.2f} ₽ (${new_usd:.2f})
</blockquote>

✅ <i>Баланс казны успешно обновлен</i>
"""

                        bot.send_message(message.chat.id, display, parse_mode='HTML')

                    except ValueError:
                        bot.send_message(message.chat.id, "❌ Введите число!")

                elif command == "rate":
                    current_rate = get_exchange_rate()
                    last_updated = exchange_rates.get("last_updated")

                    if last_updated:
                        updated_time = datetime.fromtimestamp(last_updated).strftime('%d.%m.%Y %H:%M:%S')
                    else:
                        updated_time = "никогда"

                    display = f"""
<blockquote expandable>╔══════════════════════╗
   📈 <b>КУРС ВАЛЮТ</b> 📈
╚══════════════════════╝</blockquote>

<blockquote>
💱 <b>Пара:</b> USD/RUB
💰 <b>Курс:</b> 1$ ≈ {current_rate} ₽
⏰ <b>Обновлен:</b> {updated_time}
</blockquote>

<i>Курс автоматически обновляется при каждой операции</i>

<b>КОМАНДА:</b>
<code>/kazna update</code> - обновить курс вручную
"""

                    bot.send_message(message.chat.id, display, parse_mode='HTML')

                elif command == "update":
                    old_rate = exchange_rates.get("USD_RUB")
                    new_rate = get_exchange_rate()

                    display = f"""
<blockquote expandable>╔══════════════════════╗
   📈 <b>КУРС ОБНОВЛЕН</b> 📈
╚══════════════════════╝</blockquote>

<blockquote>
💱 <b>Пара:</b> USD/RUB
📉 <b>Старый курс:</b> 1$ ≈ {old_rate} ₽
📈 <b>Новый курс:</b> 1$ ≈ {new_rate} ₽
📊 <b>Изменение:</b> {new_rate - old_rate:.2f} ₽
⏰ <b>Обновлен:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
</blockquote>

✅ <i>Курс успешно обновлен</i>
"""

                    bot.send_message(message.chat.id, display, parse_mode='HTML')

                else:
                    bot.send_message(message.chat.id, "❌ Неизвестная команда. Используйте <code>/kazna</code> для списка команд", parse_mode='HTML')

        except Exception as e:
            logging.error(f"Ошибка в kazna_command: {e}")
            bot.send_message(message.chat.id, "❌ Ошибка")


    @bot.callback_query_handler(func=lambda call: True)
    def user_callback_handler(call):
        """Обрабатывает пользовательские колбэки (только для обычных пользователей)"""
        try:
            user_id = str(call.from_user.id)

            if user_id == ADMIN_ID:
                if call.data.startswith('admin_') or call.data.startswith('withdrawal_'):
                    bot.answer_callback_query(call.id, "⚠️ Используйте команды: /check и /kazna")
                    return

            allowed, message = check_cooldown(user_id, "button")
            if not allowed:
                bot.answer_callback_query(call.id, message)
                return

            if call.data == "profile_deposit":
                current_rate = get_exchange_rate()

                display = f"""
<blockquote expandable>╔══════════════════════╗
   💳 <b>ПОПОЛНЕНИЕ БАЛАНСА</b> 💳
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Минимальная сумма:</b> {MIN_DEPOSIT_RUB} ₽
📈 <b>Курс:</b> 1$ ≈ {current_rate} ₽
💎 <b>Доступные криптовалюты:</b> USDT, TON
⚡ <b>Зачисление:</b> Автоматически
⏰ <b>Действует:</b> 10 минут
</blockquote>

🎯 <i>Сначала выберите криптовалюту:</i>
"""

                bot.delete_message(call.message.chat.id, call.message.message_id)
                bot.send_message(
                    call.message.chat.id,
                    display,
                    parse_mode='HTML',
                    reply_markup=get_crypto_choice_keyboard()
                )

            elif call.data == "profile_withdraw":
                users_data = load_users_data()
                balance = users_data.get(user_id, {}).get('balance', 0)

                if TREASURY_MODE == "real":
                    treasury_balance_usd, treasury_balance_rub = get_treasury_balance()
                else:
                    treasury_balance_usd, treasury_balance_rub = get_test_treasury_balance()

                current_rate = get_exchange_rate()

                display = f"""
<blockquote expandable>╔══════════════════════╗
   📤 <b>ВЫВОД СРЕДСТВ</b> 📤
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Доступно:</b> {balance:.2f} ₽
🏦 <b>Баланс казны:</b> {treasury_balance_rub:.2f} ₽
💸 <b>Минимум:</b> {MIN_WITHDRAW_RUB} ₽
📈 <b>Курс:</b> 1$ ≈ {current_rate} ₽
💎 <b>Метод:</b> {'Чек CryptoBot (USDT)' if TREASURY_MODE == 'real' else '@cryptobot'}
⚡ <b>Вывод:</b> {'Автоматически' if TREASURY_MODE == 'real' else 'До 24ч⌛️'}
</blockquote>

🎯 <i>Выберите сумму:</i>
"""

                bot.delete_message(call.message.chat.id, call.message.message_id)
                bot.send_message(
                    call.message.chat.id,
                    display,
                    parse_mode='HTML',
                    reply_markup=get_withdraw_keyboard()
                )

            elif call.data in ["crypto_type_usdt", "crypto_type_ton"]:
                crypto_type = "USDT" if call.data == "crypto_type_usdt" else "TON"
                current_rate = get_exchange_rate()

                if user_id not in user_states:
                    user_states[user_id] = {}
                user_states[user_id]['selected_crypto'] = crypto_type

                crypto_name = "USDT (TRC20)" if crypto_type == "USDT" else "TON"

                display = f"""
<blockquote expandable>╔══════════════════════╗
   💳 <b>ПОПОЛНЕНИЕ {crypto_name}</b> 💳
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Минимальная сумма:</b> {MIN_DEPOSIT_RUB} ₽
📈 <b>Курс:</b> 1$ ≈ {current_rate} ₽
💎 <b>Криптовалюта:</b> {crypto_name}
⚡ <b>Зачисление:</b> Автоматически
⏰ <b>Действует:</b> 10 минут
</blockquote>

🎯 <i>Выберите сумму в рублях:</i>
"""
                markup = get_deposit_keyboard()

                bot.delete_message(call.message.chat.id, call.message.message_id)
                bot.send_message(
                    call.message.chat.id,
                    display,
                    parse_mode='HTML',
                    reply_markup=markup
                )

            elif call.data == "crypto_back_profile":
                users_data = load_users_data()
                user_info = users_data.get(user_id, {})
                username = call.from_user.username or call.from_user.first_name
                balance = user_info.get('balance', 0)

                profile_text = f"""
<blockquote expandable>╔══════════════════════╗
   🔥 <b>FLAME PROFILE</b> 🔥
╚══════════════════════╝</blockquote>

<b>👤 Игрок:</b> @{username}
<b>🆔 ID:</b> <code>{user_id}</code>
━━━━━━━━━━━━━━━━━━━━
<b>💰 Баланс:</b> <code>{balance:.2f}₽</code>
<b>📅 В проекте:</b> активен
"""

                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.row(
                    types.InlineKeyboardButton("📥 ПОПОЛНИТЬ", callback_data="profile_deposit"),
                    types.InlineKeyboardButton("📤 ВЫВЕСТИ", callback_data="profile_withdraw")
                )

                bot.delete_message(call.message.chat.id, call.message.message_id)
                bot.send_message(
                    call.message.chat.id,
                    profile_text,
                    parse_mode='HTML',
                    reply_markup=markup
                )

            elif call.data == "crypto_deposit_custom":
                if user_id not in user_states or 'selected_crypto' not in user_states[user_id]:
                    bot.answer_callback_query(call.id, "❌ Сначала выберите криптовалюту")
                    return

                user_states[user_id]["action"] = "waiting_deposit_amount"
                current_rate = get_exchange_rate()

                bot.delete_message(call.message.chat.id, call.message.message_id)
                msg = bot.send_message(
                    call.message.chat.id,
                    f"💳 <b>Введите сумму в рублях для пополнения:</b>\n\n"
                    f"<blockquote>💰 Минимум: {MIN_DEPOSIT_RUB} ₽\n"
                    f"📈 Курс: 1$ ≈ {current_rate} ₽\n"
                    f"💎 Крипта: {user_states[user_id]['selected_crypto']}</blockquote>\n\n"
                    f"<i>Введите сумму от {MIN_DEPOSIT_RUB} до {MAX_DEPOSIT_RUB} ₽</i>",
                    parse_mode='HTML'
                )
                bot.register_next_step_handler(msg, lambda m: process_custom_deposit(m, bot))

            elif call.data.startswith("crypto_deposit_"):
                allowed, message = check_cooldown(user_id, "deposit")
                if not allowed:
                    bot.answer_callback_query(call.id, message)
                    return

                if user_id not in user_states or 'selected_crypto' not in user_states[user_id]:
                    bot.answer_callback_query(call.id, "❌ Сначала выберите криптовалюту")
                    return

                amount_rub = float(call.data.split("_")[2])
                process_deposit(call, amount_rub, bot)

            elif call.data == "crypto_withdraw_custom":
                user_states[user_id] = {"action": "waiting_withdraw_amount"}
                current_rate = get_exchange_rate()

                bot.delete_message(call.message.chat.id, call.message.message_id)
                msg = bot.send_message(
                    call.message.chat.id,
                    f"📤 <b>Введите сумму в рублях для вывода:</b>\n\n"
                    f"<blockquote>💰 Минимум: {MIN_WITHDRAW_RUB} ₽\n"
                    f"📈 Курс: 1$ ≈ {current_rate} ₽\n"
                    f"💎 Получите: USDT (TRC20)</blockquote>\n\n"
                    f"<i>Введите сумму от {MIN_WITHDRAW_RUB} до {MAX_WITHDRAW_RUB} ₽</i>",
                    parse_mode='HTML'
                )
                bot.register_next_step_handler(msg, lambda m: process_custom_withdraw(m, bot))

            elif call.data.startswith("crypto_withdraw_"):
                allowed, message = check_cooldown(user_id, "withdraw")
                if not allowed:
                    bot.answer_callback_query(call.id, message)
                    return

                amount_rub = float(call.data.split("_")[2])
                process_withdraw(call, amount_rub, bot)

            else:
                bot.answer_callback_query(call.id, "⚠️ Неизвестная команда")

        except Exception as e:
            logging.exception(f"Ошибка в user_callback_handler: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка")


    def process_deposit(call, amount_rub, bot):
        """Обрабатывает пополнение в рублях"""
        try:
            user_id = str(call.from_user.id)

            if amount_rub < MIN_DEPOSIT_RUB:
                bot.answer_callback_query(call.id, f"❌ Минимальная сумма {MIN_DEPOSIT_RUB} ₽")
                return

            if amount_rub > MAX_DEPOSIT_RUB:
                bot.answer_callback_query(call.id, f"❌ Максимальная сумма {MAX_DEPOSIT_RUB} ₽")
                return

            bot.answer_callback_query(call.id, "⏳ Создаем счет...")

            crypto_type = user_states.get(user_id, {}).get('selected_crypto', 'USDT')

            invoice = create_cryptobot_invoice(amount_rub, crypto_type)

            if not invoice:
                bot.answer_callback_query(call.id, "❌ Ошибка создания счета. Попробуйте позже.")
                return

            invoice_id = invoice['invoice_id']
            pending_invoices[invoice_id] = {
                'user_id': user_id,
                'amount_rub': amount_rub,
                'amount_usd': invoice['amount_usd'],
                'crypto_type': crypto_type,
                'status': 'pending',
                'created_at': time.time()
            }

            current_rate = get_exchange_rate()
            crypto_name = "USDT (TRC20)" if crypto_type == "USDT" else "TON"

            display = f"""
<blockquote expandable>╔══════════════════════╗
   💳 <b>СЧЕТ ДЛЯ ОПЛАТЫ</b> 💳
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Сумма:</b> {amount_rub} ₽
💎 <b>Крипта:</b> {crypto_name}
📈 <b>Курс:</b> 1$ ≈ {current_rate} ₽
🔢 <b>К оплате:</b> {invoice['amount_usd']} {crypto_type}
🔗 <b>Ссылка:</b> <code>{invoice['pay_url']}</code>
⏰ <b>Действует:</b> 10 минут
</blockquote>

🎯 <i>Для оплаты нажмите кнопку:</i>
"""

            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("💳 Оплатить", url=invoice['pay_url']))

            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(
                call.message.chat.id,
                display,
                parse_mode='HTML',
                reply_markup=markup
            )

            start_payment_check(call.message.chat.id, amount_rub, invoice_id, user_id, crypto_type, bot)

        except Exception as e:
            logging.exception(f"Ошибка process_deposit: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка создания счета")

    def start_payment_check(chat_id, amount_rub, invoice_id, user_id, crypto_type, bot):
        """Запускает автоматическую проверку оплаты на 10 минут"""
        def check_loop():
            max_checks = 120
            check_interval = 5

            for i in range(max_checks):
                try:
                    time.sleep(check_interval)

                    invoice_info = get_invoice_status(invoice_id)
                    if not invoice_info:
                        continue

                    status = invoice_info.get('status', 'active')

                    if status == 'paid':
                        users_data = load_users_data()
                        if user_id not in users_data:
                            users_data[user_id] = {'balance': 0}

                        users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0) + amount_rub, 2)
                        save_users_data(users_data)

                        pending_invoices[invoice_id]['status'] = 'paid'

                        add_transaction(user_id, amount_rub, 'deposit', 'completed', crypto_type)

                        # ====== ОТПРАВКА УВЕДОМЛЕНИЯ В ГРУППУ ======
                        try:
                            # Получаем username пользователя
                            from telebot.apihelper import ApiTelegramException
                            try:
                                user_info = bot.get_chat(user_id)
                                username = user_info.username or user_info.first_name or "Пользователь"
                            except:
                                username = "Пользователь"
                            
                            send_notification_to_group(bot, "deposit", username, amount_rub)
                        except Exception as notify_error:
                            logging.error(f"Ошибка отправки уведомления: {notify_error}")
                        # ===========================================

                        success_display = f"""
<blockquote expandable>╔══════════════════════╗
   ✅ <b>ОПЛАТА ПРОШЛА УСПЕШНО</b> ✅
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Сумма:</b> {amount_rub} ₽
🎯 <b>Статус:</b> Зачислено на баланс
💎 <b>Крипта:</b> {crypto_type}
</blockquote>

💎 <i>Баланс пополнен!</i>
"""

                        markup = types.InlineKeyboardMarkup()
                        markup.row(types.InlineKeyboardButton("⬅️ В профиль", callback_data="crypto_back_profile"))

                        bot.send_message(
                            chat_id,
                            success_display,
                            parse_mode='HTML',
                            reply_markup=markup
                        )
                        return

                    elif status == 'expired':
                        expired_display = f"""
<blockquote expandable>╔══════════════════════╗
   ❌ <b>СЧЕТ ПРОСРОЧЕН</b> ❌
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Сумма:</b> {amount_rub} ₽
⏰ <b>Статус:</b> Истек срок действия
💎 <b>Крипта:</b> {crypto_type}
</blockquote>

💡 <i>Создайте новый счет</i>
"""

                        markup = types.InlineKeyboardMarkup()
                        markup.row(types.InlineKeyboardButton("🔄 Создать новый", callback_data="profile_deposit"))
                        markup.row(types.InlineKeyboardButton("⬅️ В профиль", callback_data="crypto_back_profile"))

                        bot.send_message(
                            chat_id,
                            expired_display,
                            parse_mode='HTML',
                            reply_markup=markup
                        )
                        return

                except Exception as e:
                    logging.error(f"Ошибка при проверке оплаты: {e}")
                    continue

            timeout_display = f"""
<blockquote expandable>╔══════════════════════╗
   ⏰ <b>ВРЕМЯ ОПЛАТЫ ИСТЕКЛО</b> ⏰
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Сумма:</b> {amount_rub} ₽
⏰ <b>Статус:</b> Время ожидания истекло (10 минут)
💎 <b>Крипта:</b> {crypto_type}
</blockquote>

💡 <i>Создайте новый счет</i>
"""

            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("🔄 Создать новый", callback_data="profile_deposit"))
            markup.row(types.InlineKeyboardButton("⬅️ В профиль", callback_data="crypto_back_profile"))

            try:
                bot.send_message(
                    chat_id,
                    timeout_display,
                    parse_mode='HTML',
                    reply_markup=markup
                )
            except Exception as e:
                logging.error(f"Ошибка при обновлении сообщения таймаута: {e}")

        import threading
        thread = threading.Thread(target=check_loop)
        thread.daemon = True
        thread.start()

    def process_custom_deposit(message, bot):
        """Обрабатывает кастомное пополнение в рублях"""
        try:
            user_id = str(message.from_user.id)
            if user_id not in user_states or user_states[user_id].get("action") != "waiting_deposit_amount":
                bot.send_message(message.chat.id, "❌ Ошибка. Начните заново.")
                return

            user_states.pop(user_id, None)

            try:
                amount_rub = float(message.text)

                if amount_rub < MIN_DEPOSIT_RUB:
                    bot.send_message(message.chat.id, f"❌ Минимум {MIN_DEPOSIT_RUB} ₽")
                    return

                if amount_rub > MAX_DEPOSIT_RUB:
                    bot.send_message(message.chat.id, f"❌ Максимум {MAX_DEPOSIT_RUB} ₽")
                    return

                allowed, message_text = check_cooldown(user_id, "deposit")
                if not allowed:
                    bot.send_message(message.chat.id, message_text)
                    return

                crypto_type = user_states.get(user_id, {}).get('selected_crypto', 'USDT')

                bot.send_message(message.chat.id, "⏳ Создаем счет...")
                invoice = create_cryptobot_invoice(amount_rub, crypto_type)

                if not invoice:
                    bot.send_message(message.chat.id, "❌ Ошибка создания счета")
                    return

                invoice_id = invoice['invoice_id']
                pending_invoices[invoice_id] = {
                    'user_id': user_id,
                    'amount_rub': amount_rub,
                    'amount_usd': invoice['amount_usd'],
                    'crypto_type': crypto_type,
                    'status': 'pending',
                    'created_at': time.time()
                }

                current_rate = get_exchange_rate()
                crypto_name = "USDT (TRC20)" if crypto_type == "USDT" else "TON"

                display = f"""
<blockquote expandable>╔══════════════════════╗
   💳 <b>СЧЕТ ДЛЯ ОПЛАТЫ</b> 💳
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Сумма:</b> {amount_rub} ₽
💎 <b>Крипта:</b> {crypto_name}
📈 <b>Курс:</b> 1$ ≈ {current_rate} ₽
🔢 <b>К оплате:</b> {invoice['amount_usd']} {crypto_type}
🔗 <b>Ссылка:</b> <code>{invoice['pay_url']}</code>
⏰ <b>Действует:</b> 10 минут
</blockquote>
"""

                markup = types.InlineKeyboardMarkup()
                markup.row(types.InlineKeyboardButton("💳 Оплатить", url=invoice['pay_url']))

                bot.send_message(
                    message.chat.id,
                    display,
                    parse_mode='HTML',
                    reply_markup=markup
                )

                start_payment_check(message.chat.id, amount_rub, invoice_id, user_id, crypto_type, bot)

            except ValueError:
                bot.send_message(message.chat.id, "❌ Введите число!")

        except Exception as e:
            logging.exception(f"Ошибка process_custom_deposit: {e}")
            bot.send_message(message.chat.id, "❌ Ошибка")

    def process_withdraw(call, amount_rub, bot):
        """Обрабатывает вывод в рублях"""
        try:
            user_id = str(call.from_user.id)
            
            # Защита от дублирования вывода
            with withdraw_lock:
                users_data = load_users_data()
                balance_rub = users_data.get(user_id, {}).get('balance', 0)

                if amount_rub < MIN_WITHDRAW_RUB:
                    bot.answer_callback_query(call.id, f"❌ Минимум {MIN_WITHDRAW_RUB} ₽")
                    return

                if amount_rub > MAX_WITHDRAW_RUB:
                    bot.answer_callback_query(call.id, f"❌ Максимум {MAX_WITHDRAW_RUB} ₽")
                    return

                if balance_rub < amount_rub:
                    bot.answer_callback_query(call.id, "❌ Недостаточно средств")
                    return

                if TREASURY_MODE == "real":
                    treasury_balance_usd, treasury_balance_rub = get_treasury_balance()
                    logging.info(f"Баланс казны для вывода: {treasury_balance_rub} ₽, запрошено: {amount_rub} ₽")

                    if treasury_balance_rub < amount_rub:
                        bot.answer_callback_query(call.id, f"❌ Недостаточно средств в казне\n🏦 Доступно: {treasury_balance_rub:.2f} ₽")
                        return

                    bot.answer_callback_query(call.id, "⏳ Создаем чек...")

                    check = create_cryptobot_check(amount_rub, user_id, "USDT")

                    if not check:
                        bot.answer_callback_query(call.id, "❌ Ошибка создания чека")
                        return

                    users_data[user_id]['balance'] = round(balance_rub - amount_rub, 2)
                    save_users_data(users_data)

                    add_transaction(user_id, amount_rub, 'withdraw', 'completed', 'USDT')

                    current_rate = get_exchange_rate()

                    display = f"""
<blockquote expandable>╔══════════════════════╗
   ✅ <b>ВЫВОД ОФОРМЛЕН</b> ✅
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Сумма:</b> {amount_rub} ₽
💎 <b>Крипта:</b> USDT (TRC20)
📈 <b>Курс:</b> 1$ ≈ {current_rate} ₽
🔢 <b>К получению:</b> {check['amount_usd']} USDT
🎯 <b>Статус:</b> Чек создан
</blockquote>

💎 <i>Для получения нажмите кнопку:</i>
"""

                    markup = types.InlineKeyboardMarkup()
                    markup.row(types.InlineKeyboardButton("💳 Получить чек", url=check['bot_check_url']))
                    markup.row(types.InlineKeyboardButton("⬅️ В профиль", callback_data="crypto_back_profile"))

                    bot.delete_message(call.message.chat.id, call.message.message_id)
                    bot.send_message(
                        call.message.chat.id,
                        display,
                        parse_mode='HTML',
                        reply_markup=markup
                    )

                    # ====== ОТПРАВКА УВЕДОМЛЕНИЯ В ГРУППУ ПОСЛЕ ВЫДАЧИ ЧЕКА ======
                    try:
                        username = call.from_user.username or call.from_user.first_name or "Пользователь"
                        send_notification_to_group(bot, "withdraw", username, amount_rub)
                    except Exception as notify_error:
                        logging.error(f"Ошибка отправки уведомления: {notify_error}")
                    # ==============================================================

                else:
                    bot.answer_callback_query(call.id, "⏳ Создаем заявку на вывод...")

                    username = call.from_user.username or call.from_user.first_name or "Пользователь"

                    withdrawal_id = add_pending_withdrawal(user_id, amount_rub, username, "USDT")

                    if not withdrawal_id:
                        bot.answer_callback_query(call.id, "❌ Ошибка создания заявки")
                        return

                    users_data[user_id]['balance'] = round(balance_rub - amount_rub, 2)
                    save_users_data(users_data)

                    add_transaction(user_id, amount_rub, 'withdraw', 'pending', 'USDT', withdrawal_id)

                    current_rate = get_exchange_rate()
                    amount_usd = convert_rub_to_usd(amount_rub)

                    display = f"""
<blockquote expandable>╔══════════════════════╗
   ⏳ <b>ЗАЯВКА СОЗДАНА
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Сумма:</b> {amount_rub} ₽
💎 <b>Крипта:</b> USDT (TRC20)
📈 <b>Курс:</b> 1$ ≈ {current_rate} ₽
🔢 <b>К получению:</b> {amount_usd:.6f} USDT
🎯 <b>Статус:</b> Ожидает одобрения
</blockquote>

📋 <i>Заявка отправлена администратору</i>
<i>Средства будут заморожены до обработки</i>
"""

                    markup = types.InlineKeyboardMarkup()
                    markup.row(types.InlineKeyboardButton("⬅️ В профиль", callback_data="crypto_back_profile"))

                    bot.delete_message(call.message.chat.id, call.message.message_id)
                    bot.send_message(
                        call.message.chat.id,
                        display,
                        parse_mode='HTML',
                        reply_markup=markup
                    )

                    try:
                        admin_display = f"""
<blockquote expandable>╔══════════════════════╗
   ⏳ <b>НОВАЯ ЗАЯВКА
╚══════════════════════╝</blockquote>

<blockquote>
👤 <b>Пользователь:</b> @{username}
🆔 <b>ID:</b> <code>{user_id}</code>
━━━━━━━━━━━━━━━━━━━━
💰 <b>Сумма:</b> {amount_rub:.2f} ₽
💎 <b>Крипта:</b> USDT (TRC20)
🔢 <b>К выдаче:</b> {amount_usd:.6f} USDT
</blockquote>

📋 <i>Новая заявка на вывод ожидает обработки</i>

💻 <b>Используйте команды:</b>
<code>/check pending</code> - посмотреть ожидающие
<code>/check approve {withdrawal_id}</code> - одобрить
<code>/check reject {withdrawal_id}</code> - отклонить
"""

                        bot.send_message(
                            ADMIN_ID,
                            admin_display,
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logging.error(f"Ошибка уведомления администратора: {e}")

        except Exception as e:
            logging.exception(f"Ошибка process_withdraw: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка")

    def process_custom_withdraw(message, bot):
        """Обрабатывает кастомный вывод в рублях"""
        try:
            user_id = str(message.from_user.id)
            if user_id not in user_states or user_states[user_id].get("action") != "waiting_withdraw_amount":
                bot.send_message(message.chat.id, "❌ Ошибка. Начните заново.")
                return

            user_states.pop(user_id, None)

            try:
                amount_rub = float(message.text)
                
                # Защита от дублирования вывода
                with withdraw_lock:
                    users_data = load_users_data()
                    balance_rub = users_data.get(user_id, {}).get('balance', 0)

                    if amount_rub < MIN_WITHDRAW_RUB:
                        bot.send_message(message.chat.id, f"❌ Минимум {MIN_WITHDRAW_RUB} ₽")
                        return

                    if amount_rub > MAX_WITHDRAW_RUB:
                        bot.send_message(message.chat.id, f"❌ Максимум {MAX_WITHDRAW_RUB} ₽")
                        return

                    if balance_rub < amount_rub:
                        bot.send_message(message.chat.id, "❌ Недостаточно средств")
                        return

                    allowed, message_text = check_cooldown(user_id, "withdraw")
                    if not allowed:
                        bot.send_message(message.chat.id, message_text)
                        return

                    if TREASURY_MODE == "real":
                        treasury_balance_usd, treasury_balance_rub = get_treasury_balance()
                        logging.info(f"Баланс казны для кастомного вывода: {treasury_balance_rub} ₽, запрошено: {amount_rub} ₽")

                        if treasury_balance_rub < amount_rub:
                            bot.send_message(message.chat.id, f"❌ Недостаточно средств в казне\n🏦 Доступно: {treasury_balance_rub:.2f} ₽")
                            return

                        bot.send_message(message.chat.id, "⏳ Создаем чек...")

                        check = create_cryptobot_check(amount_rub, user_id, "USDT")

                        if not check:
                            bot.send_message(message.chat.id, "❌ Ошибка создания чека")
                            return

                        users_data[user_id]['balance'] = round(balance_rub - amount_rub, 2)
                        save_users_data(users_data)

                        add_transaction(user_id, amount_rub, 'withdraw', 'completed', 'USDT')

                        current_rate = get_exchange_rate()

                        display = f"""
<blockquote expandable>╔══════════════════════╗
   ✅ <b>ВЫВОД ОФОРМЛЕН</b> ✅
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Сумма:</b> {amount_rub} ₽
💎 <b>Крипта:</b> USDT (TRC20)
📈 <b>Курс:</b> 1$ ≈ {current_rate} ₽
🔢 <b>К получению:</b> {check['amount_usd']} USDT
🎯 <b>Статус:</b> Чек создан
</blockquote>

💎 <i>Для получения нажмите кнопку:</i>
"""

                        markup = types.InlineKeyboardMarkup()
                        markup.row(types.InlineKeyboardButton("💳 Получить чек", url=check['bot_check_url']))
                        markup.row(types.InlineKeyboardButton("⬅️ В профиль", callback_data="crypto_back_profile"))

                        bot.send_message(
                            message.chat.id,
                            display,
                            parse_mode='HTML',
                            reply_markup=markup
                        )

                        # ====== ОТПРАВКА УВЕДОМЛЕНИЯ В ГРУППУ ПОСЛЕ ВЫДАЧИ ЧЕКА ======
                        try:
                            username = message.from_user.username or message.from_user.first_name or "Пользователь"
                            send_notification_to_group(bot, "withdraw", username, amount_rub)
                        except Exception as notify_error:
                            logging.error(f"Ошибка отправки уведомления: {notify_error}")
                    # ==============================================================

                    else:
                        bot.send_message(message.chat.id, "⏳ Создаем заявку на вывод...")

                        username = message.from_user.username or message.from_user.first_name or "Пользователь"

                        withdrawal_id = add_pending_withdrawal(user_id, amount_rub, username, "USDT")

                        if not withdrawal_id:
                            bot.send_message(message.chat.id, "❌ Ошибка создания заявки")
                            return

                        users_data[user_id]['balance'] = round(balance_rub - amount_rub, 2)
                        save_users_data(users_data)

                        add_transaction(user_id, amount_rub, 'withdraw', 'pending', 'USDT', withdrawal_id)

                        current_rate = get_exchange_rate()
                        amount_usd = convert_rub_to_usd(amount_rub)

                        display = f"""
<blockquote expandable>╔══════════════════════╗
   ⏳ <b>ЗАЯВКА СОЗДАНА
╚══════════════════════╝</blockquote>

<blockquote>
💰 <b>Сумма:</b> {amount_rub} ₽
💎 <b>Крипта:</b> USDT (TRC20)
📈 <b>Курс:</b> 1$ ≈ {current_rate} ₽
🔢 <b>К получению:</b> {amount_usd:.6f} USDT
🎯 <b>Статус:</b> Ожидает одобрения
</blockquote>

📋 <i>Заявка отправлена администратору</i>
<i>Средства будут заморожены до обработки</i>
"""

                        markup = types.InlineKeyboardMarkup()
                        markup.row(types.InlineKeyboardButton("⬅️ В профиль", callback_data="crypto_back_profile"))

                        bot.send_message(
                            message.chat.id,
                            display,
                            parse_mode='HTML',
                            reply_markup=markup
                        )

                        try:
                            admin_display = f"""
<blockquote expandable>╔══════════════════════╗
   ⏳ <b>НОВАЯ ЗАЯВКА
╚══════════════════════╝</blockquote>

<blockquote>
👤 <b>Пользователь:</b> @{username}
🆔 <b>ID:</b> <code>{user_id}</code>
━━━━━━━━━━━━━━━━━━━━
💰 <b>Сумма:</b> {amount_rub:.2f} ₽
💎 <b>Крипта:</b> USDT (TRC20)
🔢 <b>К выдаче:</b> {amount_usd:.6f} USDT
</blockquote>

📋 <i>Новая заявка на вывод ожидает обработки</i>

💻 <b>Используйте команды:</b>
<code>/check pending</code> - посмотреть ожидающие
<code>/check approve {withdrawal_id}</code> - одобрить
<code>/check reject {withdrawal_id}</code> - отклонить
"""

                            bot.send_message(
                                ADMIN_ID,
                                admin_display,
                                parse_mode='HTML'
                            )
                        except Exception as e:
                            logging.error(f"Ошибка уведомления администратора: {e}")

            except ValueError:
                bot.send_message(message.chat.id, "❌ Введите число!")

        except Exception as e:
            logging.exception(f"Ошибка process_custom_withdraw: {e}")
            bot.send_message(message.chat.id, "❌ Ошибка")
