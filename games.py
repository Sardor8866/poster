# games_module.py
import telebot
from telebot import types
import random
import json
import time
import threading
import logging
import hashlib

# Импорт функций из модуля лидеров
try:
    from leaders import add_game_to_history
except ImportError:
    # Функция-заглушка, если модуль лидеров не найден
    def add_game_to_history(user_id, bet_amount, win_amount, is_win, game_type="dice"):
        logging.warning(f"Модуль лидеров не найден, игра не записана в историю: {user_id}")
        return False

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Потокобезопасный словарь для активных ставок и времени последнего нажатия
active_bets = {}
last_click_time = {}
bet_lock = threading.Lock()
# Словарь для отслеживания активных игр пользователя
active_games = {}
# Словарь для защиты от дублирования ставок
game_session_tokens = {}

# Минимальная и максимальная ставка в рублях
MIN_BET_DICE = 1  # Минимальная ставка для кубов - 1 рубль
MIN_BET_OTHER = 25  # Минимальная ставка для других игр - 25 рублей
MAX_BET = float('inf')  # Максимальная ставка неограничена

def get_min_bet(game_type):
    """Возвращает минимальную ставку в зависимости от типа игры"""
    if game_type == "dice":
        return MIN_BET_DICE
    else:
        return MIN_BET_OTHER

def generate_session_token(user_id, game_type):
    """Генерирует уникальный токен для сессии игры"""
    timestamp = str(time.time())
    data = f"{user_id}_{game_type}_{timestamp}"
    return hashlib.md5(data.encode()).hexdigest()[:8]

def rate_limit(user_id):
    """Проверка ограничения по времени между нажатиями (0.4 секунды)"""
    current_time = time.time()
    with bet_lock:
        if user_id in last_click_time:
            if current_time - last_click_time[user_id] < 0.4:
                return False
        last_click_time[user_id] = current_time
    return True

def load_users_data():
    """Загрузка данных пользователей"""
    try:
        with open('users_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        logging.error("Ошибка декодирования JSON")
        return {}
    except Exception as e:
        logging.error(f"Ошибка загрузки данных: {e}")
        return {}

def save_users_data(data):
    """Сохранение данных пользователей"""
    try:
        with open('users_data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logging.error(f"Ошибка сохранения данных: {e}")
        return False

def add_referral_bonus(user_id, win_amount):
    """
    Начисляет 6% от выигрыша реферала его рефереру
    ВАЖНОЕ ИСПРАВЛЕНИЕ: Делаем начисление БЕЗОПАСНЫМ
    """
    try:
        # Загружаем данные
        users_data = load_users_data()
        
        if user_id not in users_data:
            logging.error(f"Пользователь {user_id} не найден")
            return False

        # Получаем ID реферера
        referrer_id = users_data[user_id].get('referrer_id')
        if not referrer_id:
            logging.info(f"У {user_id} нет реферера")
            return False

        # Проверяем реферера
        if referrer_id not in users_data:
            logging.error(f"Реферер {referrer_id} не найден")
            return False

        # Вычисляем бонус
        bonus = round(win_amount * 0.06, 2)
        if bonus <= 0:
            logging.info(f"Бонус 0 для выигрыша {win_amount}")
            return False

        logging.info(f"=== НАЧИСЛЕНИЕ РЕФЕРАЛЬНОГО БОНУСА ===")
        logging.info(f"Реферал: {user_id}")
        logging.info(f"Реферер: {referrer_id}")
        logging.info(f"Выигрыш: {win_amount}₽")
        logging.info(f"Бонус (6%): {bonus}₽")

        # Загружаем еще раз, чтобы получить свежие данные
        users_data = load_users_data()
        
        # Получаем текущие значения
        old_bonus = users_data[referrer_id].get('referral_bonus', 0)
        old_total = users_data[referrer_id].get('total_referral_income', 0)
        
        logging.info(f"Было у реферера: баланс={old_bonus}₽, всего={old_total}₽")

        # Обновляем значения
        users_data[referrer_id]['referral_bonus'] = round(old_bonus + bonus, 2)
        users_data[referrer_id]['total_referral_income'] = round(old_total + bonus, 2)

        # Сохраняем
        if save_users_data(users_data):
            # Проверяем, что сохранилось
            check_data = load_users_data()
            if referrer_id in check_data:
                new_bonus = check_data[referrer_id].get('referral_bonus', 0)
                new_total = check_data[referrer_id].get('total_referral_income', 0)
                
                logging.info(f"Стало у реферера: баланс={new_bonus}₽, всего={new_total}₽")
                logging.info(f"Успешно! Разница: +{new_bonus - old_bonus}₽")
                logging.info(f"=== НАЧИСЛЕНИЕ ЗАВЕРШЕНО ===")
                return True
            else:
                logging.error(f"Реферер {referrer_id} не найден после сохранения")
                return False
        else:
            logging.error("Ошибка сохранения данных")
            return False

    except Exception as e:
        logging.error(f"Ошибка в add_referral_bonus: {e}", exc_info=True)
        return False

def get_games_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎲 Кости", callback_data="games_dice"),
        types.InlineKeyboardButton("🏀 Баскетбол", callback_data="games_basketball"),
        types.InlineKeyboardButton("⚽ Футбол", callback_data="games_football"),
        types.InlineKeyboardButton("🎯 Дартс", callback_data="games_darts")
    )
    return markup

def get_bet_selection_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=5)
    bets = ["25", "50", "125", "250", "500"]
    buttons = [types.InlineKeyboardButton(f"{bet}₽", callback_data=f"games_bet_{bet}") for bet in bets]
    markup.row(*buttons)
    markup.row(types.InlineKeyboardButton("📝 Ввести вручную", callback_data="games_custom_bet"))
    return markup

# 🎲 КОСТИ
def get_dice_selection_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔴 Чет (1.8x)", callback_data="dice_even"),
        types.InlineKeyboardButton("⚫ Нечет (1.8x)", callback_data="dice_odd"),
        types.InlineKeyboardButton("📈 Больше 3 (1.8x)", callback_data="dice_high"),
        types.InlineKeyboardButton("📉 Меньше 4 (1.8x)", callback_data="dice_low")
    )
    return markup

def play_dice_game_chat(bot, message, bet_type, bet_amount, user_id, username):
    """Игра в кости через чат-команды"""
    try:
        users_data = load_users_data()
        
        # Проверка баланса
        if user_id not in users_data:
            users_data[user_id] = {'balance': 0}
            save_users_data(users_data)
            bot.reply_to(message, "❌ У вас нет баланса. Начните с /start")
            return
        
        balance = users_data[user_id].get('balance', 0)
        
        # Проверки ставки для костей (1 рубль минимальная)
        if bet_amount < MIN_BET_DICE:
            bot.reply_to(message, f"❌ Минимальная ставка: {MIN_BET_DICE}₽!")
            return
        if bet_amount > balance:
            bot.reply_to(message, "❌ Недостаточно средств!")
            return
        
        # Списываем ставку
        users_data[user_id]['balance'] = round(balance - bet_amount, 2)
        save_users_data(users_data)
        
        # Показываем анимацию броска
        dice_msg = bot.send_dice(message.chat.id, emoji='🎲')
        
        # Ждем 3 секунды
        time.sleep(3)
        
        # Получаем результат
        dice_value = dice_msg.dice.value
        
        # Проверяем выигрыш
        win = False
        multiplier = 1.8
        bet_type_name = get_dice_bet_name_chat(bet_type)
        
        if bet_type in ["чет", "even"] and dice_value in [2, 4, 6]:
            win = True
        elif bet_type in ["нечет", "odd"] and dice_value in [1, 3, 5]:
            win = True
        elif bet_type in ["больше", "more", "high"] and dice_value in [4, 5, 6]:
            win = True
        elif bet_type in ["меньше", "less", "low"] and dice_value in [1, 2, 3]:
            win = True
        else:
            multiplier = 0
        
        # Обновляем баланс
        if win:
            win_amount = round(bet_amount * multiplier, 2)
            # Загружаем снова свежие данные
            users_data = load_users_data()
            current_balance = users_data[user_id].get('balance', 0)
            users_data[user_id]['balance'] = round(current_balance + win_amount, 2)
            save_users_data(users_data)
            
            # ЗАПИСЬ ВЫИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=win_amount,
                    is_win=True,
                    game_type="dice"
                )
            except Exception as e:
                logging.error(f"Ошибка записи выигрыша в историю: {e}")
            
            # НАЧИСЛЯЕМ РЕФЕРАЛЬНЫЙ БОНУС
            logging.info(f"🎲 Кости (чат): попытка начисления бонуса для {user_id}, выигрыш: {win_amount}₽")
            add_referral_bonus(user_id, win_amount)
            
            result_text = f"""<b>🎲 Кости</b>

🎮 Игрок: @{username if username else user_id}
🎉 <b>Победа!</b>

<blockquote>🎯 Ставка: {bet_type_name}
🎰 Выпало: {dice_value}
💰 Выигрыш: <b>{win_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id]['balance'], 2)}₽</b>"""
        else:
            users_data = load_users_data()
            
            # ЗАПИСЬ ПРОИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=0.0,
                    is_win=False,
                    game_type="dice"
                )
            except Exception as e:
                logging.error(f"Ошибка записи проигрыша в историю: {e}")
                
            result_text = f"""<b>🎲 Кости</b>

🎮 Игрок: @{username if username else user_id}
❌ <b>Проигрыш!</b>

<blockquote>🎯 Ставка: {bet_type_name}
🎰 Выпало: {dice_value}
💸 Ставка: <b>{bet_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id].get('balance', 0), 2)}₽</b>"""
        
        bot.reply_to(dice_msg, result_text, parse_mode='HTML')
        
    except Exception as e:
        logging.error(f"Ошибка в play_dice_game_chat: {e}")
        bot.reply_to(message, "❌ Произошла ошибка во время игры. Попробуйте еще раз.")

def play_dice_game(bot, call, bet_type, bet_amount, user_id, session_token):
    try:
        # Проверяем активную игру пользователя
        with bet_lock:
            if user_id in active_games and active_games[user_id] == session_token:
                return  # Игра уже запущена
            active_games[user_id] = session_token

        # Показываем анимацию броска
        dice_msg = bot.send_dice(call.message.chat.id, emoji='🎲')

        # Ждем 3 секунды
        time.sleep(3)

        # Получаем результат
        dice_value = dice_msg.dice.value
        users_data = load_users_data()

        # Проверяем выигрыш с новой логикой
        win = False
        multiplier = 1.8

        if bet_type == "even" and dice_value in [2, 4, 6]:  # Четные: 2,4,6
            win = True
        elif bet_type == "odd" and dice_value in [1, 3, 5]:  # Нечетные: 1,3,5
            win = True
        elif bet_type == "high" and dice_value in [4, 5, 6]:  # Больше 3: 4,5,6
            win = True
        elif bet_type == "low" and dice_value in [1, 2, 3]:  # Меньше 4: 1,2,3
            win = True
        else:
            multiplier = 0

        # Обновляем баланс
        if win:
            win_amount = round(bet_amount * multiplier, 2)
            current_balance = users_data[user_id].get('balance', 0)
            users_data[user_id]['balance'] = round(current_balance + win_amount, 2)
            save_users_data(users_data)
            
            # ЗАПИСЬ ВЫИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=win_amount,
                    is_win=True,
                    game_type="dice"
                )
            except Exception as e:
                logging.error(f"Ошибка записи выигрыша в историю: {e}")
            
            # НАЧИСЛЯЕМ РЕФЕРАЛЬНЫЙ БОНУС
            logging.info(f"🎲 Кости (инлайн): попытка начисления бонуса для {user_id}, выигрыш: {win_amount}₽")
            success = add_referral_bonus(user_id, win_amount)
            logging.info(f"Результат начисления: {'УСПЕХ' if success else 'ОШИБКА'}")

            result_text = f"""<b>🎲 Кости</b>

🎉 <b>Победа!</b>

<blockquote>🎯 Ставка: {get_dice_bet_name(bet_type)}
🎰 Выпало: {dice_value}
💰 Выигрыш: <b>{win_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id]['balance'], 2)}₽</b>"""
        else:
            users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0), 2)
            save_users_data(users_data)

            # ЗАПИСЬ ПРОИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=0.0,
                    is_win=False,
                    game_type="dice"
                )
            except Exception as e:
                logging.error(f"Ошибка записи проигрыша в историю: {e}")

            result_text = f"""<b>🎲 Кости</b>

❌ <b>Проигрыш!</b>

<blockquote>🎯 Ставка: {get_dice_bet_name(bet_type)}
🎰 Выпало: {dice_value}
💸 Ставка: <b>{bet_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id]['balance'], 2)}₽</b>"""

        # Отправляем результат новым сообщением
        bot.send_message(
            call.message.chat.id,
            result_text,
            parse_mode='HTML'
        )

        # Очищаем активную игру
        with bet_lock:
            if user_id in active_games and active_games[user_id] == session_token:
                del active_games[user_id]
            if user_id in active_bets:
                del active_bets[user_id]
            if user_id in game_session_tokens:
                del game_session_tokens[user_id]

    except Exception as e:
        logging.error(f"Ошибка в игре в кости: {e}")
        # Очищаем активную игру при ошибке
        with bet_lock:
            if user_id in active_games:
                del active_games[user_id]
            if user_id in active_bets:
                del active_bets[user_id]
            if user_id in game_session_tokens:
                del game_session_tokens[user_id]

        try:
            bot.send_message(
                call.message.chat.id,
                "❌ Произошла ошибка во время игры. Попробуйте еще раз."
            )
        except Exception as e2:
            logging.error(f"Не удалось отправить сообщение об ошибке: {e2}")

def get_dice_bet_name(bet_type):
    names = {
        "even": "🔴 Чет",
        "odd": "⚫ Нечет",
        "high": "📈 Больше 3",
        "low": "📉 Меньше 4"
    }
    return names.get(bet_type, bet_type)

def get_dice_bet_name_chat(bet_type):
    """Получение названия ставки для чат-команд"""
    if bet_type in ["чет", "even"]:
        return "🔴 Чет"
    elif bet_type in ["нечет", "odd"]:
        return "⚫ Нечет"
    elif bet_type in ["больше", "more", "high"]:
        return "📈 Больше 3"
    elif bet_type in ["меньше", "less", "low"]:
        return "📉 Меньше 4"
    return bet_type

# 🏀 БАСКЕТБОЛ
def get_basketball_selection_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("❌ Мимо (2x)", callback_data="basketball_miss"),
        types.InlineKeyboardButton("🟢 Гол (2x)", callback_data="basketball_goal"),
        types.InlineKeyboardButton("🎯 3-очковый (3x)", callback_data="basketball_three")
    )
    return markup

def play_basketball_game_chat(bot, message, bet_type, bet_amount, user_id, username):
    """Игра в баскетбол через чат-команды"""
    try:
        users_data = load_users_data()
        
        # Проверка баланса
        if user_id not in users_data:
            users_data[user_id] = {'balance': 0}
            save_users_data(users_data)
            bot.reply_to(message, "❌ У вас нет баланса. Начните с /start")
            return
        
        balance = users_data[user_id].get('balance', 0)
        
        # Проверки ставки для баскетбола (25 рублей минимальная)
        if bet_amount < MIN_BET_OTHER:
            bot.reply_to(message, f"❌ Минимальная ставка: {MIN_BET_OTHER}₽!")
            return
        if bet_amount > balance:
            bot.reply_to(message, "❌ Недостаточно средств!")
            return
        
        # Списываем ставку
        users_data[user_id]['balance'] = round(balance - bet_amount, 2)
        save_users_data(users_data)
        
        # Показываем анимацию броска
        basketball_msg = bot.send_dice(message.chat.id, emoji='🏀')
        
        # Ждем 3 секунды
        time.sleep(3)
        
        # Получаем результат
        dice_value = basketball_msg.dice.value
        
        # Логика баскетбола
        if dice_value == 4:
            result = "goal"      # Обычный гол
        elif dice_value == 5:
            result = "three"     # Трехочковый
        else:  # dice_value 1,2,3
            result = "miss"      # Мяч мимо
        
        win = False
        bet_type_name = get_basketball_bet_name_chat(bet_type)
        
        # Проверяем выигрыш
        if bet_type in ["мимо", "miss"] and result == "miss":
            win = True
            multiplier = 2.0
        elif bet_type in ["гол", "goal"] and result in ["goal", "three"]:
            win = True
            multiplier = 2.0
        elif bet_type in ["3-очковый", "three", "тройка"] and result == "three":
            win = True
            multiplier = 3.0
        else:
            multiplier = 0
        
        # Обновляем баланс
        if win:
            win_amount = round(bet_amount * multiplier, 2)
            users_data = load_users_data()
            current_balance = users_data[user_id].get('balance', 0)
            users_data[user_id]['balance'] = round(current_balance + win_amount, 2)
            save_users_data(users_data)
            
            # ЗАПИСЬ ВЫИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=win_amount,
                    is_win=True,
                    game_type="basketball"
                )
            except Exception as e:
                logging.error(f"Ошибка записи выигрыша в историю: {e}")
            
            # НАЧИСЛЯЕМ РЕФЕРАЛЬНЫЙ БОНУС
            logging.info(f"🏀 Баскетбол (чат): попытка начисления бонуса для {user_id}, выигрыш: {win_amount}₽")
            add_referral_bonus(user_id, win_amount)
            
            result_text = f"""<b>🏀 Баскетбол</b>

🎮 Игрок: @{username if username else user_id}
🎉 <b>Победа!</b>

<blockquote>🎯 Ставка: {bet_type_name}
🏀 Результат: {get_basketball_result_emoji(result)}
💰 Выигрыш: <b>{win_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id]['balance'], 2)}₽</b>"""
        else:
            users_data = load_users_data()
            
            # ЗАПИСЬ ПРОИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=0.0,
                    is_win=False,
                    game_type="basketball"
                )
            except Exception as e:
                logging.error(f"Ошибка записи проигрыша в историю: {e}")
                
            result_text = f"""<b>🏀 Баскетбол</b>

🎮 Игрок: @{username if username else user_id}
❌ <b>Проигрыш!</b>

<blockquote>🎯 Ставка: {bet_type_name}
🏀 Результат: {get_basketball_result_emoji(result)}
💸 Ставка: <b>{bet_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id].get('balance', 0), 2)}₽</b>"""
        
        bot.reply_to(basketball_msg, result_text, parse_mode='HTML')
        
    except Exception as e:
        logging.error(f"Ошибка в play_basketball_game_chat: {e}")
        bot.reply_to(message, "❌ Произошла ошибка во время игры. Попробуйте еще раз.")

def play_basketball_game(bot, call, bet_type, bet_amount, user_id, session_token):
    try:
        # Проверяем активную игру пользователя
        with bet_lock:
            if user_id in active_games and active_games[user_id] == session_token:
                return  # Игра уже запущена
            active_games[user_id] = session_token

        # Показываем анимацию броска
        basketball_msg = bot.send_dice(call.message.chat.id, emoji='🏀')

        # Ждем 3 секунды
        time.sleep(3)

        # Получаем результат (значение кости баскетбола)
        dice_value = basketball_msg.dice.value
        users_data = load_users_data()

        # ФИНАЛЬНАЯ ЛОГИКА ДЛЯ БАСКЕТБОЛА
        # Значения dice_value для эмоджи 🏀:
        # 1-3 = мимо или застревает (значение 3 тоже мимо)
        # 4 = обычный гол (2 очка)
        # 5 = трехочковый

        if dice_value == 4:
            result = "goal"      # Обычный гол (2 очка)
        elif dice_value == 5:
            result = "three"     # Трехочковый
        else:  # dice_value 1,2,3
            result = "miss"      # Мяч мимо или застревает

        win = False

        # ЛОГИКА ВЫИГРЫША
        # 3-очковый считается за гол при ставке на гол
        if bet_type == "miss" and result == "miss":
            win = True
            multiplier = 2.0
        elif bet_type == "goal" and result in ["goal", "three"]:  # 3-очковый тоже гол
            win = True
            multiplier = 2.0
        elif bet_type == "three" and result == "three":
            win = True
            multiplier = 3.0
        else:
            multiplier = 0

        # Обновляем баланс
        if win:
            win_amount = round(bet_amount * multiplier, 2)
            current_balance = users_data[user_id].get('balance', 0)
            users_data[user_id]['balance'] = round(current_balance + win_amount, 2)
            save_users_data(users_data)
            
            # ЗАПИСЬ ВЫИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=win_amount,
                    is_win=True,
                    game_type="basketball"
                )
            except Exception as e:
                logging.error(f"Ошибка записи выигрыша в историю: {e}")
            
            # НАЧИСЛЯЕМ РЕФЕРАЛЬНЫЙ БОНУС
            logging.info(f"🏀 Баскетбол (инлайн): попытка начисления бонуса для {user_id}, выигрыш: {win_amount}₽")
            add_referral_bonus(user_id, win_amount)

            result_text = f"""<b>🏀 Баскетбол</b>

🎉 <b>Победа!</b>

<blockquote>🎯 Ставка: {get_basketball_bet_name(bet_type)}
🏀 Результат: {get_basketball_result_emoji(result)}
💰 Выигрыш: <b>{win_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id]['balance'], 2)}₽</b>"""
        else:
            users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0), 2)
            save_users_data(users_data)

            # ЗАПИСЬ ПРОИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=0.0,
                    is_win=False,
                    game_type="basketball"
                )
            except Exception as e:
                logging.error(f"Ошибка записи проигрыша в историю: {e}")

            result_text = f"""<b>🏀 Баскетбол</b>

❌ <b>Проигрыш!</b>

<blockquote>🎯 Ставка: {get_basketball_bet_name(bet_type)}
🏀 Результат: {get_basketball_result_emoji(result)}
💸 Ставка: <b>{bet_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id]['balance'], 2)}₽</b>"""

        # Отправляем результат новым сообщением
        bot.send_message(
            call.message.chat.id,
            result_text,
            parse_mode='HTML'
        )

        # Очищаем активную игру
        with bet_lock:
            if user_id in active_games and active_games[user_id] == session_token:
                del active_games[user_id]
            if user_id in active_bets:
                del active_bets[user_id]
            if user_id in game_session_tokens:
                del game_session_tokens[user_id]

    except Exception as e:
        logging.error(f"Ошибка в игре в баскетбол: {e}")
        # Очищаем активную игру при ошибке
        with bet_lock:
            if user_id in active_games:
                del active_games[user_id]
            if user_id in active_bets:
                del active_bets[user_id]
            if user_id in game_session_tokens:
                del game_session_tokens[user_id]

        try:
            bot.send_message(
                call.message.chat.id,
                "❌ Произошла ошибка во время игры. Попробуйте еще раз."
            )
        except Exception as e2:
            logging.error(f"Не удалось отправить сообщение об ошибке: {e2}")

def get_basketball_bet_name(bet_type):
    names = {
        "miss": "❌ Мимо",
        "goal": "🟢 Гол",
        "three": "🎯 3-очковый"
    }
    return names.get(bet_type, bet_type)

def get_basketball_bet_name_chat(bet_type):
    """Получение названия ставки для чат-команд баскетбола"""
    if bet_type in ["мимо", "miss"]:
        return "❌ Мимо"
    elif bet_type in ["гол", "goal"]:
        return "🟢 Гол"
    elif bet_type in ["3-очковый", "three", "тройка"]:
        return "🎯 3-очковый"
    return bet_type

def get_basketball_result_emoji(result):
    """Возвращает результат с эмоджи для баскетбола"""
    emojis = {
        "miss": "❌ Мимо",
        "goal": "🟢 Гол",
        "three": "🎯 3-очковый"
    }
    return emojis.get(result, result)

# ⚽ ФУТБОЛ
def get_football_selection_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("❌ Мимо (1.8x)", callback_data="football_miss"),
        types.InlineKeyboardButton("🟢 Гол (1.4x)", callback_data="football_goal")
    )
    return markup

def play_football_game_chat(bot, message, bet_type, bet_amount, user_id, username):
    """Игра в футбол через чат-команды"""
    try:
        users_data = load_users_data()
        
        # Проверка баланса
        if user_id not in users_data:
            users_data[user_id] = {'balance': 0}
            save_users_data(users_data)
            bot.reply_to(message, "❌ У вас нет баланса. Начните с /start")
            return
        
        balance = users_data[user_id].get('balance', 0)
        
        # Проверки ставки для футбола (25 рублей минимальная)
        if bet_amount < MIN_BET_OTHER:
            bot.reply_to(message, f"❌ Минимальная ставка: {MIN_BET_OTHER}₽!")
            return
        if bet_amount > balance:
            bot.reply_to(message, "❌ Недостаточно средств!")
            return
        
        # Списываем ставку
        users_data[user_id]['balance'] = round(balance - bet_amount, 2)
        save_users_data(users_data)
        
        # Показываем анимацию удара
        football_msg = bot.send_dice(message.chat.id, emoji='⚽')
        
        # Ждем 3.5 секунды
        time.sleep(3.5)
        
        # Получаем результат
        dice_value = football_msg.dice.value
        
        # Логика футбола
        if dice_value >= 3:  # 3,4,5 - гол
            result = "goal"
        else:  # 1,2 - мимо
            result = "miss"
        
        win = False
        bet_type_name = get_football_bet_name_chat(bet_type)
        
        # Проверяем выигрыш
        if bet_type in ["мимо", "miss"] and result == "miss":
            win = True
            multiplier = 1.8
        elif bet_type in ["гол", "goal"] and result == "goal":
            win = True
            multiplier = 1.4
        else:
            multiplier = 0
        
        # Обновляем баланс
        if win:
            win_amount = round(bet_amount * multiplier, 2)
            users_data = load_users_data()
            current_balance = users_data[user_id].get('balance', 0)
            users_data[user_id]['balance'] = round(current_balance + win_amount, 2)
            save_users_data(users_data)
            
            # ЗАПИСЬ ВЫИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=win_amount,
                    is_win=True,
                    game_type="football"
                )
            except Exception as e:
                logging.error(f"Ошибка записи выигрыша в историю: {e}")
            
            # НАЧИСЛЯЕМ РЕФЕРАЛЬНЫЙ БОНУС
            logging.info(f"⚽ Футбол (чат): попытка начисления бонуса для {user_id}, выигрыш: {win_amount}₽")
            add_referral_bonus(user_id, win_amount)
            
            result_text = f"""<b>⚽ Футбол</b>

🎮 Игрок: @{username if username else user_id}
🎉 <b>Победа!</b>

<blockquote>🎯 Ставка: {bet_type_name}
⚽ Результат: {get_football_result_emoji(result)}
💰 Выигрыш: <b>{win_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id]['balance'], 2)}₽</b>"""
        else:
            users_data = load_users_data()
            
            # ЗАПИСЬ ПРОИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=0.0,
                    is_win=False,
                    game_type="football"
                )
            except Exception as e:
                logging.error(f"Ошибка записи проигрыша в историю: {e}")
                
            result_text = f"""<b>⚽ Футбол</b>

🎮 Игрок: @{username if username else user_id}
❌ <b>Проигрыш!</b>

<blockquote>🎯 Ставка: {bet_type_name}
⚽ Результат: {get_football_result_emoji(result)}
💸 Ставка: <b>{bet_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id].get('balance', 0), 2)}₽</b>"""
        
        bot.reply_to(football_msg, result_text, parse_mode='HTML')
        
    except Exception as e:
        logging.error(f"Ошибка в play_football_game_chat: {e}")
        bot.reply_to(message, "❌ Произошла ошибка во время игры. Попробуйте еще раз.")

def play_football_game(bot, call, bet_type, bet_amount, user_id, session_token):
    try:
        # Проверяем активную игру пользователя
        with bet_lock:
            if user_id in active_games and active_games[user_id] == session_token:
                return  # Игра уже запущена
            active_games[user_id] = session_token

        # Показываем анимацию удара
        football_msg = bot.send_dice(call.message.chat.id, emoji='⚽')

        # Ждем 3.5 секунды
        time.sleep(3.5)

        # Получаем результат (значение кости футбола)
        dice_value = football_msg.dice.value
        users_data = load_users_data()

        # ПРАВИЛЬНАЯ ЛОГИКА ДЛЯ ФУТБОЛА
        # dice_value: 1-2 = мимо, 3-5 = гол
        if dice_value >= 3:  # 3,4,5 - гол
            result = "goal"
        else:  # 1,2 - мимо
            result = "miss"

        win = False

        # Проверяем выигрыш с новыми множителями
        if bet_type == "miss" and result == "miss":
            win = True
            multiplier = 1.8
        elif bet_type == "goal" and result == "goal":
            win = True
            multiplier = 1.4
        else:
            multiplier = 0

        # Обновляем баланс
        if win:
            win_amount = round(bet_amount * multiplier, 2)
            current_balance = users_data[user_id].get('balance', 0)
            users_data[user_id]['balance'] = round(current_balance + win_amount, 2)
            save_users_data(users_data)
            
            # ЗАПИСЬ ВЫИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=win_amount,
                    is_win=True,
                    game_type="football"
                )
            except Exception as e:
                logging.error(f"Ошибка записи выигрыша в историю: {e}")
            
            # НАЧИСЛЯЕМ РЕФЕРАЛЬНЫЙ БОНУС
            logging.info(f"⚽ Футбол (инлайн): попытка начисления бонуса для {user_id}, выигрыш: {win_amount}₽")
            add_referral_bonus(user_id, win_amount)

            result_text = f"""<b>⚽ Футбол</b>

🎉 <b>Победа!</b>

<blockquote>🎯 Ставка: {get_football_bet_name(bet_type)}
⚽ Результат: {get_football_result_emoji(result)}
💰 Выигрыш: <b>{win_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id]['balance'], 2)}₽</b>"""
        else:
            users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0), 2)
            save_users_data(users_data)

            # ЗАПИСЬ ПРОИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=0.0,
                    is_win=False,
                    game_type="football"
                )
            except Exception as e:
                logging.error(f"Ошибка записи проигрыша в историю: {e}")

            result_text = f"""<b>⚽ Футбол</b>

❌ <b>Проигрыш!</b>

<blockquote>🎯 Ставка: {get_football_bet_name(bet_type)}
⚽ Результат: {get_football_result_emoji(result)}
💸 Ставка: <b>{bet_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id]['balance'], 2)}₽</b>"""

        # Отправляем результат новым сообщением
        bot.send_message(
            call.message.chat.id,
            result_text,
            parse_mode='HTML'
        )

        # Очищаем активную игру
        with bet_lock:
            if user_id in active_games and active_games[user_id] == session_token:
                del active_games[user_id]
            if user_id in active_bets:
                del active_bets[user_id]
            if user_id in game_session_tokens:
                del game_session_tokens[user_id]

    except Exception as e:
        logging.error(f"Ошибка в игре в футбол: {e}")
        # Очищаем активную игру при ошибке
        with bet_lock:
            if user_id in active_games:
                del active_games[user_id]
            if user_id in active_bets:
                del active_bets[user_id]
            if user_id in game_session_tokens:
                del game_session_tokens[user_id]

        try:
            bot.send_message(
                call.message.chat.id,
                "❌ Произошла ошибка во время игры. Попробуйте еще раз."
            )
        except Exception as e2:
            logging.error(f"Не удалось отправить сообщение об ошибке: {e2}")

def get_football_bet_name(bet_type):
    names = {
        "miss": "❌ Мимо",
        "goal": "🟢 Гол"
    }
    return names.get(bet_type, bet_type)

def get_football_bet_name_chat(bet_type):
    """Получение названия ставки для чат-команд футбола"""
    if bet_type in ["мимо", "miss"]:
        return "❌ Мимо"
    elif bet_type in ["гол", "goal"]:
        return "🟢 Гол"
    return bet_type

def get_football_result_emoji(result):
    """Возвращает результат с эмоджи для футбола"""
    emojis = {
        "miss": "❌ Мимо",
        "goal": "🟢 Гол"
    }
    return emojis.get(result, result)

# 🎯 ДАРТС
def get_darts_selection_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("❌ Мимо (2.5x)", callback_data="darts_miss"),
        types.InlineKeyboardButton("🔴 Красное (1.8x)", callback_data="darts_red"),
        types.InlineKeyboardButton("⚪ Белое (1.8x)", callback_data="darts_white"),
        types.InlineKeyboardButton("🎯 Центр (4.3x)", callback_data="darts_bullseye")
    )
    return markup

def play_darts_game_chat(bot, message, bet_type, bet_amount, user_id, username):
    """Игра в дартс через чат-команды"""
    try:
        users_data = load_users_data()
        
        # Проверка баланса
        if user_id not in users_data:
            users_data[user_id] = {'balance': 0}
            save_users_data(users_data)
            bot.reply_to(message, "❌ У вас нет баланса. Начните с /start")
            return
        
        balance = users_data[user_id].get('balance', 0)
        
        # Проверки ставки для дартса (25 рублей минимальная)
        if bet_amount < MIN_BET_OTHER:
            bot.reply_to(message, f"❌ Минимальная ставка: {MIN_BET_OTHER}₽!")
            return
        if bet_amount > balance:
            bot.reply_to(message, "❌ Недостаточно средств!")
            return
        
        # Списываем ставку
        users_data[user_id]['balance'] = round(balance - bet_amount, 2)
        save_users_data(users_data)
        
        # Показываем анимацию броска
        darts_msg = bot.send_dice(message.chat.id, emoji='🎯')
        
        # Ждем 3 секунды
        time.sleep(3)
        
        # Получаем результат
        dice_value = darts_msg.dice.value
        
        # Логика дартса
        if dice_value == 1:
            result = "miss"      # ❌ Мимо
        elif dice_value == 6:
            result = "bullseye"  # 🎯 Центр (красный)
        elif dice_value in [2, 4]:
            result = "red"       # 🔴 Красное кольцо
        else:  # 3, 5
            result = "white"     # ⚪ Белое кольцо
        
        win = False
        bet_type_name = get_darts_bet_name_chat(bet_type)
        
        # Множители для дартса
        multipliers = {
            "miss": 2.5,
            "red": 1.8,
            "white": 1.8,
            "bullseye": 4.3
        }
        
        # Проверяем выигрыш
        if bet_type in ["мимо", "miss"] and result == "miss":
            win = True
            multiplier = multipliers["miss"]
        elif bet_type in ["красное", "red", "красный"] and result in ["red", "bullseye"]:
            win = True
            multiplier = multipliers["red"]
        elif bet_type in ["белое", "white", "белый"] and result == "white":
            win = True
            multiplier = multipliers["white"]
        elif bet_type in ["центр", "bullseye", "яблочко"] and result == "bullseye":
            win = True
            multiplier = multipliers["bullseye"]
        else:
            multiplier = 0
        
        # Обновляем баланс
        if win:
            win_amount = round(bet_amount * multiplier, 2)
            users_data = load_users_data()
            current_balance = users_data[user_id].get('balance', 0)
            users_data[user_id]['balance'] = round(current_balance + win_amount, 2)
            save_users_data(users_data)
            
            # ЗАПИСЬ ВЫИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=win_amount,
                    is_win=True,
                    game_type="darts"
                )
            except Exception as e:
                logging.error(f"Ошибка записи выигрыша в историю: {e}")
            
            # НАЧИСЛЯЕМ РЕФЕРАЛЬНЫЙ БОНУС
            logging.info(f"🎯 Дартс (чат): попытка начисления бонуса для {user_id}, выигрыш: {win_amount}₽")
            add_referral_bonus(user_id, win_amount)
            
            result_text = f"""<b>🎯 Дартс</b>

🎮 Игрок: @{username if username else user_id}
🎉 <b>Победа!</b>

<blockquote>🎯 Ставка: {bet_type_name}
🎯 Результат: {get_darts_result_emoji(result)}
💰 Выигрыш: <b>{win_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id]['balance'], 2)}₽</b>"""
        else:
            users_data = load_users_data()
            
            # ЗАПИСЬ ПРОИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=0.0,
                    is_win=False,
                    game_type="darts"
                )
            except Exception as e:
                logging.error(f"Ошибка записи проигрыша в историю: {e}")
                
            result_text = f"""<b>🎯 Дартс</b>

🎮 Игрок: @{username if username else user_id}
❌ <b>Проигрыш!</b>

<blockquote>🎯 Ставка: {bet_type_name}
🎯 Результат: {get_darts_result_emoji(result)}
💸 Ставка: <b>{bet_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id].get('balance', 0), 2)}₽</b>"""
        
        bot.reply_to(darts_msg, result_text, parse_mode='HTML')
        
    except Exception as e:
        logging.error(f"Ошибка в play_darts_game_chat: {e}")
        bot.reply_to(message, "❌ Произошла ошибка во время игры. Попробуйте еще раз.")

def play_darts_game(bot, call, bet_type, bet_amount, user_id, session_token):
    try:
        # Проверяем активную игру пользователя
        with bet_lock:
            if user_id in active_games and active_games[user_id] == session_token:
                return  # Игра уже запущена
            active_games[user_id] = session_token

        # Показываем анимацию броска
        darts_msg = bot.send_dice(call.message.chat.id, emoji='🎯')

        # Ждем 3 секунды
        time.sleep(3)

        # Получаем результат (значение кости дартса)
        dice_value = darts_msg.dice.value
        users_data = load_users_data()

        # ПРАВИЛЬНАЯ СТРУКТУРА МИШЕНИ ДАРТСА:
        # Центр (красный) -> Белое кольцо -> Красное кольцо -> Белое кольцо -> Красное кольцо (внешнее)
        # dice_value:
        # 1 = мимо доски
        # 2 = внешнее красное кольцо (самый большой)
        # 3 = белое кольцо (второе по размеру)
        # 4 = красное кольцо (третье по размеру)
        # 5 = белое кольцо (четвертое по размеру)
        # 6 = центр (красный, самый маленький)

        if dice_value == 1:
            result = "miss"      # ❌ Мимо
        elif dice_value == 6:
            result = "bullseye"  # 🎯 Центр (красный)
        elif dice_value in [2, 4]:
            result = "red"       # 🔴 Красное кольцо
        else:  # 3, 5
            result = "white"     # ⚪ Белое кольцо

        win = False
        # Множители для дартса
        multipliers = {
            "miss": 2.5,
            "red": 1.8,
            "white": 1.8,
            "bullseye": 4.3
        }

        # Проверяем выигрыш
        if bet_type == "red" and result in ["red", "bullseye"]:
            win = True
            multiplier = multipliers["red"]
        elif bet_type == "white" and result == "white":
            win = True
            multiplier = multipliers["white"]
        elif bet_type == "miss" and result == "miss":
            win = True
            multiplier = multipliers["miss"]
        elif bet_type == "bullseye" and result == "bullseye":
            win = True
            multiplier = multipliers["bullseye"]
        else:
            multiplier = 0

        # Обновляем баланс
        if win:
            win_amount = round(bet_amount * multiplier, 2)
            current_balance = users_data[user_id].get('balance', 0)
            users_data[user_id]['balance'] = round(current_balance + win_amount, 2)
            save_users_data(users_data)
            
            # ЗАПИСЬ ВЫИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=win_amount,
                    is_win=True,
                    game_type="darts"
                )
            except Exception as e:
                logging.error(f"Ошибка записи выигрыша в историю: {e}")
            
            # НАЧИСЛЯЕМ РЕФЕРАЛЬНЫЙ БОНУС
            logging.info(f"🎯 Дартс (инлайн): попытка начисления бонуса для {user_id}, выигрыш: {win_amount}₽")
            add_referral_bonus(user_id, win_amount)

            result_text = f"""<b>🎯 Дартс</b>

🎉 <b>Победа!</b>

<blockquote>🎯 Ставка: {get_darts_bet_name(bet_type)}
🎯 Результат: {get_darts_result_emoji(result)}
💰 Выигрыш: <b>{win_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id]['balance'], 2)}₽</b>"""
        else:
            users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0), 2)
            save_users_data(users_data)

            # ЗАПИСЬ ПРОИГРЫША В ИСТОРИЮ ДЛЯ ЛИДЕРОВ
            try:
                add_game_to_history(
                    user_id=int(user_id),
                    bet_amount=bet_amount,
                    win_amount=0.0,
                    is_win=False,
                    game_type="darts"
                )
            except Exception as e:
                logging.error(f"Ошибка записи проигрыша в историю: {e}")

            result_text = f"""<b>🎯 Дартс</b>

❌ <b>Проигрыш!</b>

<blockquote>🎯 Ставка: {get_darts_bet_name(bet_type)}
🎯 Результат: {get_darts_result_emoji(result)}
💸 Ставка: <b>{bet_amount}₽</b></blockquote>

💰 Баланс: <b>{round(users_data[user_id]['balance'], 2)}₽</b>"""

        # Отправляем результат новым сообщением
        bot.send_message(
            call.message.chat.id,
            result_text,
            parse_mode='HTML'
        )

        # Очищаем активную игру
        with bet_lock:
            if user_id in active_games and active_games[user_id] == session_token:
                del active_games[user_id]
            if user_id in active_bets:
                del active_bets[user_id]
            if user_id in game_session_tokens:
                del game_session_tokens[user_id]

    except Exception as e:
        logging.error(f"Ошибка в игре в дартс: {e}")
        # Очищаем активную игру при ошибке
        with bet_lock:
            if user_id in active_games:
                del active_games[user_id]
            if user_id in active_bets:
                del active_bets[user_id]
            if user_id in game_session_tokens:
                del game_session_tokens[user_id]

        try:
            bot.send_message(
                call.message.chat.id,
                "❌ Произошла ошибка во время игры. Попробуйте еще раз."
            )
        except Exception as e2:
            logging.error(f"Не удалось отправить сообщение об ошибке: {e2}")

def get_darts_bet_name(bet_type):
    names = {
        "miss": "❌ Мимо",
        "red": "🔴 Красное",
        "white": "⚪ Белое",
        "bullseye": "🎯 Центр"
    }
    return names.get(bet_type, bet_type)

def get_darts_bet_name_chat(bet_type):
    """Получение названия ставки для чат-команд дартса"""
    if bet_type in ["мимо", "miss"]:
        return "❌ Мимо"
    elif bet_type in ["красное", "red", "красный"]:
        return "🔴 Красное"
    elif bet_type in ["белое", "white", "белый"]:
        return "⚪ Белое"
    elif bet_type in ["центр", "bullseye", "яблочко"]:
        return "🎯 Центр"
    return bet_type

def get_darts_result_emoji(result):
    """Возвращает результат с эмоджи для дартса"""
    emojis = {
        "miss": "❌ Мимо",
        "red": "🔴 Красное",
        "white": "⚪ Белое",
        "bullseye": "🎯 Центр"
    }
    return emojis.get(result, result)

# ДОБАВЛЯЕМ ФУНКЦИИ ДЛЯ РЕГИСТРАЦИИ ХЕНДЛЕРОВ
def process_custom_bet_games(message):
    try:
        user_id = str(message.from_user.id)

        # Проверяем ограничение по времени
        if not rate_limit(user_id):
            bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.4 секунды.")
            return

        # Проверяем активную игру
        with bet_lock:
            if user_id in active_games:
                bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                return

        bet_amount = float(message.text)
        users_data = load_users_data()

        if user_id not in users_data:
            users_data[user_id] = {'balance': 0}

        balance = users_data[user_id].get('balance', 0)

        # Получаем тип игры для проверки минимальной ставки
        with bet_lock:
            if user_id not in active_bets:
                bot.send_message(message.chat.id, "❌ Сначала выберите игру!")
                return
            game_type = active_bets[user_id]['game_type']
            min_bet = get_min_bet(game_type)

        # Проверяем минимальную ставку в зависимости от игры
        if bet_amount < min_bet:
            bot.send_message(message.chat.id, f"❌ Минимальная ставка: {min_bet}₽!")
            return
        if bet_amount > balance:
            bot.send_message(message.chat.id, "❌ Недостаточно средств!")
            return

        # Списываем ставку
        users_data[user_id]['balance'] = round(balance - bet_amount, 2)
        save_users_data(users_data)

        # Показываем выбор для выбранной игры
        with bet_lock:
            active_bets[user_id]['bet_amount'] = bet_amount

            # Генерируем токен сессии
            session_token = generate_session_token(user_id, game_type)
            game_session_tokens[user_id] = session_token

            if game_type == "dice":
                bot.send_message(message.chat.id,
                               f"""<b>🎲 Кости</b>

<blockquote>💵 Сумма ставки: {bet_amount}₽</blockquote>

Выберите исход:""",
                               parse_mode='HTML', reply_markup=get_dice_selection_keyboard())
            elif game_type == "basketball":
                bot.send_message(message.chat.id,
                               f"""<b>🏀 Баскетбол</b>

<blockquote>💵 Сумма ставки: {bet_amount}₽</blockquote>

Выберите исход:""",
                               parse_mode='HTML', reply_markup=get_basketball_selection_keyboard())
            elif game_type == "football":
                bot.send_message(message.chat.id,
                               f"""<b>⚽ Футбол</b>

<blockquote>💵 Сумма ставки: {bet_amount}₽</blockquote>

Выберите исход:""",
                               parse_mode='HTML', reply_markup=get_football_selection_keyboard())
            elif game_type == "darts":
                bot.send_message(message.chat.id,
                               f"""<b>🎯 Дартс</b>

<blockquote>💵 Сумма ставки: {bet_amount}₽</blockquote>

Выберите исход:""",
                               parse_mode='HTML', reply_markup=get_darts_selection_keyboard())

    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите корректную сумму!")
    except Exception as e:
        logging.error(f"Ошибка в process_custom_bet_games: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка!")

def register_games_handlers(bot_instance):
    global bot
    bot = bot_instance

    # КОМАНДЫ ДЛЯ ЧАТА (КОСТИ) - БЕЗ СЛЭША
    @bot.message_handler(func=lambda message: any(word in message.text.lower() for word in ['чет', 'even', 'нечет', 'odd', 'больше', 'more', 'high', 'меньше', 'less', 'low']) and not message.text.startswith('/'))
    def dice_no_slash_commands(message):
        try:
            text = message.text.lower()
            user_id = str(message.from_user.id)
            username = message.from_user.username
            
            # Парсим текст
            parts = text.split()
            if len(parts) < 2:
                return
            
            # Определяем тип ставки
            bet_type_word = parts[0]
            bet_amount_str = parts[1]
            
            # Маппинг слов на типы ставок
            bet_type_map = {
                'чет': 'чет', 'even': 'чет',
                'нечет': 'нечет', 'odd': 'нечет',
                'больше': 'больше', 'more': 'больше', 'high': 'больше',
                'меньше': 'меньше', 'less': 'меньше', 'low': 'меньше'
            }
            
            if bet_type_word not in bet_type_map:
                return
            
            bet_type = bet_type_map[bet_type_word]
            
            try:
                bet_amount = float(bet_amount_str)
            except ValueError:
                return
            
            # Проверяем минимальную ставку для костей
            if bet_amount < MIN_BET_DICE:
                bot.reply_to(message, f"❌ Минимальная ставка для костей: {MIN_BET_DICE}₽!")
                return
            
            # Запускаем игру в отдельном потоке
            threading.Thread(
                target=play_dice_game_chat,
                args=(bot, message, bet_type, bet_amount, user_id, username),
                daemon=True
            ).start()
            
        except Exception as e:
            logging.error(f"Ошибка в dice_no_slash_commands: {e}")

    # КОМАНДЫ ДЛЯ ЧАТА (КОСТИ) - СО СЛЭШЕМ
    @bot.message_handler(commands=['чет', 'even'])
    def dice_even_command(message):
        try:
            user_id = str(message.from_user.id)
            username = message.from_user.username
            
            # Проверяем аргументы
            if len(message.text.split()) < 2:
                bot.reply_to(message, "❌ Используйте: /чет [сумма] или /even [сумма]")
                return
            
            try:
                bet_amount = float(message.text.split()[1])
            except ValueError:
                bot.reply_to(message, "❌ Введите корректную сумму!")
                return
            
            # Проверяем минимальную ставку для костей
            if bet_amount < MIN_BET_DICE:
                bot.reply_to(message, f"❌ Минимальная ставка для костей: {MIN_BET_DICE}₽!")
                return
            
            # Запускаем игру в отдельном потоке
            threading.Thread(
                target=play_dice_game_chat,
                args=(bot, message, "чет", bet_amount, user_id, username),
                daemon=True
            ).start()
            
        except Exception as e:
            logging.error(f"Ошибка в dice_even_command: {e}")
            bot.reply_to(message, "❌ Произошла ошибка!")

    @bot.message_handler(commands=['нечет', 'odd'])
    def dice_odd_command(message):
        try:
            user_id = str(message.from_user.id)
            username = message.from_user.username
            
            # Проверяем аргументы
            if len(message.text.split()) < 2:
                bot.reply_to(message, "❌ Используйте: /нечет [сумма] или /odd [сумма]")
                return
            
            try:
                bet_amount = float(message.text.split()[1])
            except ValueError:
                bot.reply_to(message, "❌ Введите корректную сумму!")
                return
            
            # Проверяем минимальную ставку для костей
            if bet_amount < MIN_BET_DICE:
                bot.reply_to(message, f"❌ Минимальная ставка для костей: {MIN_BET_DICE}₽!")
                return
            
            # Запускаем игру в отдельном потоке
            threading.Thread(
                target=play_dice_game_chat,
                args=(bot, message, "нечет", bet_amount, user_id, username),
                daemon=True
            ).start()
            
        except Exception as e:
            logging.error(f"Ошибка в dice_odd_command: {e}")
            bot.reply_to(message, "❌ Произошла ошибка!")

    @bot.message_handler(commands=['больше', 'more'])
    def dice_high_command(message):
        try:
            user_id = str(message.from_user.id)
            username = message.from_user.username
            
            # Проверяем аргументы
            if len(message.text.split()) < 2:
                bot.reply_to(message, "❌ Используйте: /больше [сумма] или /more [сумма]")
                return
            
            try:
                bet_amount = float(message.text.split()[1])
            except ValueError:
                bot.reply_to(message, "❌ Введите корректную сумму!")
                return
            
            # Проверяем минимальную ставку для костей
            if bet_amount < MIN_BET_DICE:
                bot.reply_to(message, f"❌ Минимальная ставка для костей: {MIN_BET_DICE}₽!")
                return
            
            # Запускаем игру в отдельном потоке
            threading.Thread(
                target=play_dice_game_chat,
                args=(bot, message, "больше", bet_amount, user_id, username),
                daemon=True
            ).start()
            
        except Exception as e:
            logging.error(f"Ошибка в dice_high_command: {e}")
            bot.reply_to(message, "❌ Произошла ошибка!")

    @bot.message_handler(commands=['меньше', 'less'])
    def dice_low_command(message):
        try:
            user_id = str(message.from_user.id)
            username = message.from_user.username
            
            # Проверяем аргументы
            if len(message.text.split()) < 2:
                bot.reply_to(message, "❌ Используйте: /меньше [сумма] или /less [сумма]")
                return
            
            try:
                bet_amount = float(message.text.split()[1])
            except ValueError:
                bot.reply_to(message, "❌ Введите корректную сумму!")
                return
            
            # Проверяем минимальную ставку для костей
            if bet_amount < MIN_BET_DICE:
                bot.reply_to(message, f"❌ Минимальная ставка для костей: {MIN_BET_DICE}₽!")
                return
            
            # Запускаем игру в отдельном потоке
            threading.Thread(
                target=play_dice_game_chat,
                args=(bot, message, "меньше", bet_amount, user_id, username),
                daemon=True
            ).start()
            
        except Exception as e:
            logging.error(f"Ошибка в dice_low_command: {e}")
            bot.reply_to(message, "❌ Произошла ошибка!")

    # КОМАНДЫ ДЛЯ ЧАТА (БАСКЕТБОЛ) - БЕЗ СЛЭША
    @bot.message_handler(func=lambda message: any(word in message.text.lower() for word in ['баскетбол', 'баскет', 'basketball', 'basket']) and not message.text.startswith('/'))
    def basketball_no_slash_commands(message):
        try:
            text = message.text.lower()
            user_id = str(message.from_user.id)
            username = message.from_user.username
            
            # Парсим текст
            parts = text.split()
            if len(parts) < 3:
                bot.reply_to(message, "❌ Используйте: баскетбол [тип] [сумма]\nТипы: мимо, гол, 3-очковый")
                return
            
            bet_type_word = parts[1].lower()
            bet_amount_str = parts[2]
            
            # Маппинг слов на типы ставок
            bet_type_map = {
                'мимо': 'мимо', 'miss': 'мимо',
                'гол': 'гол', 'goal': 'гол',
                '3-очковый': '3-очковый', 'three': '3-очковый', 'тройка': '3-очковый'
            }
            
            if bet_type_word not in bet_type_map:
                bot.reply_to(message, "❌ Неверный тип ставки! Используйте: мимо, гол, 3-очковый")
                return
            
            bet_type = bet_type_map[bet_type_word]
            
            try:
                bet_amount = float(bet_amount_str)
            except ValueError:
                bot.reply_to(message, "❌ Введите корректную сумму!")
                return
            
            # Проверяем минимальную ставку для баскетбола
            if bet_amount < MIN_BET_OTHER:
                bot.reply_to(message, f"❌ Минимальная ставка для баскетбола: {MIN_BET_OTHER}₽!")
                return
            
            # Запускаем игру в отдельном потоке
            threading.Thread(
                target=play_basketball_game_chat,
                args=(bot, message, bet_type, bet_amount, user_id, username),
                daemon=True
            ).start()
            
        except Exception as e:
            logging.error(f"Ошибка в basketball_no_slash_commands: {e}")
            bot.reply_to(message, "❌ Произошла ошибка!")

    # КОМАНДЫ ДЛЯ ЧАТА (БАСКЕТБОЛ) - СО СЛЭШЕМ
    @bot.message_handler(commands=['баскетбол', 'basketball'])
    def basketball_command(message):
        try:
            user_id = str(message.from_user.id)
            username = message.from_user.username
            
            # Проверяем аргументы
            if len(message.text.split()) < 3:
                bot.reply_to(message, "❌ Используйте: /баскетбол [тип] [сумма]\nТипы: мимо, гол, 3-очковый")
                return
            
            bet_type = message.text.split()[1].lower()
            try:
                bet_amount = float(message.text.split()[2])
            except ValueError:
                bot.reply_to(message, "❌ Введите корректную сумму!")
                return
            
            # Проверяем тип ставки
            if bet_type not in ["мимо", "гол", "3-очковый", "miss", "goal", "three"]:
                bot.reply_to(message, "❌ Неверный тип ставки! Используйте: мимо, гол, 3-очковый")
                return
            
            # Проверяем минимальную ставку для баскетбола
            if bet_amount < MIN_BET_OTHER:
                bot.reply_to(message, f"❌ Минимальная ставка для баскетбола: {MIN_BET_OTHER}₽!")
                return
            
            # Нормализуем тип ставки
            if bet_type in ["miss"]:
                bet_type = "мимо"
            elif bet_type in ["goal"]:
                bet_type = "гол"
            elif bet_type in ["three"]:
                bet_type = "3-очковый"
            
            # Запускаем игру в отдельном потоке
            threading.Thread(
                target=play_basketball_game_chat,
                args=(bot, message, bet_type, bet_amount, user_id, username),
                daemon=True
            ).start()
            
        except Exception as e:
            logging.error(f"Ошибка в basketball_command: {e}")
            bot.reply_to(message, "❌ Произошла ошибка!")

    # КОМАНДЫ ДЛЯ ЧАТА (ФУТБОЛ) - БЕЗ СЛЭША
    @bot.message_handler(func=lambda message: any(word in message.text.lower() for word in ['футбол', 'фут', 'football', 'foot']) and not message.text.startswith('/'))
    def football_no_slash_commands(message):
        try:
            text = message.text.lower()
            user_id = str(message.from_user.id)
            username = message.from_user.username
            
            # Парсим текст
            parts = text.split()
            if len(parts) < 3:
                bot.reply_to(message, "❌ Используйте: футбол [тип] [сумма]\nТипы: мимо, гол")
                return
            
            bet_type_word = parts[1].lower()
            bet_amount_str = parts[2]
            
            # Маппинг слов на типы ставок
            bet_type_map = {
                'мимо': 'мимо', 'miss': 'мимо',
                'гол': 'гол', 'goal': 'гол'
            }
            
            if bet_type_word not in bet_type_map:
                bot.reply_to(message, "❌ Неверный тип ставки! Используйте: мимо, гол")
                return
            
            bet_type = bet_type_map[bet_type_word]
            
            try:
                bet_amount = float(bet_amount_str)
            except ValueError:
                bot.reply_to(message, "❌ Введите корректную сумму!")
                return
            
            # Проверяем минимальную ставку для футбола
            if bet_amount < MIN_BET_OTHER:
                bot.reply_to(message, f"❌ Минимальная ставка для футбола: {MIN_BET_OTHER}₽!")
                return
            
            # Запускаем игру в отдельном потоке
            threading.Thread(
                target=play_football_game_chat,
                args=(bot, message, bet_type, bet_amount, user_id, username),
                daemon=True
            ).start()
            
        except Exception as e:
            logging.error(f"Ошибка в football_no_slash_commands: {e}")
            bot.reply_to(message, "❌ Произошла ошибка!")

    # КОМАНДЫ ДЛЯ ЧАТА (ФУТБОЛ) - СО СЛЭШЕМ
    @bot.message_handler(commands=['футбол', 'football'])
    def football_command(message):
        try:
            user_id = str(message.from_user.id)
            username = message.from_user.username
            
            # Проверяем аргументы
            if len(message.text.split()) < 3:
                bot.reply_to(message, "❌ Используйте: /футбол [тип] [сумма]\nТипы: мимо, гол")
                return
            
            bet_type = message.text.split()[1].lower()
            try:
                bet_amount = float(message.text.split()[2])
            except ValueError:
                bot.reply_to(message, "❌ Введите корректную сумму!")
                return
            
            # Проверяем тип ставки
            if bet_type not in ["мимо", "гол", "miss", "goal"]:
                bot.reply_to(message, "❌ Неверный тип ставки! Используйте: мимо, гол")
                return
            
            # Проверяем минимальную ставку для футбола
            if bet_amount < MIN_BET_OTHER:
                bot.reply_to(message, f"❌ Минимальная ставка для футбола: {MIN_BET_OTHER}₽!")
                return
            
            # Нормализуем тип ставки
            if bet_type in ["miss"]:
                bet_type = "мимо"
            elif bet_type in ["goal"]:
                bet_type = "гол"
            
            # Запускаем игру в отдельном потоке
            threading.Thread(
                target=play_football_game_chat,
                args=(bot, message, bet_type, bet_amount, user_id, username),
                daemon=True
            ).start()
            
        except Exception as e:
            logging.error(f"Ошибка в football_command: {e}")
            bot.reply_to(message, "❌ Произошла ошибка!")

    # КОМАНДЫ ДЛЯ ЧАТА (ДАРТС) - БЕЗ СЛЭША
    @bot.message_handler(func=lambda message: any(word in message.text.lower() for word in ['дартс', 'дарт', 'darts', 'dart']) and not message.text.startswith('/'))
    def darts_no_slash_commands(message):
        try:
            text = message.text.lower()
            user_id = str(message.from_user.id)
            username = message.from_user.username
            
            # Парсим текст
            parts = text.split()
            if len(parts) < 3:
                bot.reply_to(message, "❌ Используйте: дартс [тип] [сумма]\nТипы: мимо, красное, белое, центр")
                return
            
            bet_type_word = parts[1].lower()
            bet_amount_str = parts[2]
            
            # Маппинг слов на типы ставок
            bet_type_map = {
                'мимо': 'мимо', 'miss': 'мимо',
                'красное': 'красное', 'red': 'красное', 'красный': 'красное',
                'белое': 'белое', 'white': 'белое', 'белый': 'белое',
                'центр': 'центр', 'bullseye': 'центр', 'яблочко': 'центр'
            }
            
            if bet_type_word not in bet_type_map:
                bot.reply_to(message, "❌ Неверный тип ставки! Используйте: мимо, красное, белое, центр")
                return
            
            bet_type = bet_type_map[bet_type_word]
            
            try:
                bet_amount = float(bet_amount_str)
            except ValueError:
                bot.reply_to(message, "❌ Введите корректную сумму!")
                return
            
            # Проверяем минимальную ставку для дартса
            if bet_amount < MIN_BET_OTHER:
                bot.reply_to(message, f"❌ Минимальная ставка для дартса: {MIN_BET_OTHER}₽!")
                return
            
            # Запускаем игру в отдельном потоке
            threading.Thread(
                target=play_darts_game_chat,
                args=(bot, message, bet_type, bet_amount, user_id, username),
                daemon=True
            ).start()
            
        except Exception as e:
            logging.error(f"Ошибка в darts_no_slash_commands: {e}")
            bot.reply_to(message, "❌ Произошла ошибка!")

    # КОМАНДЫ ДЛЯ ЧАТА (ДАРТС) - СО СЛЭШЕМ
    @bot.message_handler(commands=['дартс', 'darts'])
    def darts_command(message):
        try:
            user_id = str(message.from_user.id)
            username = message.from_user.username
            
            # Проверяем аргументы
            if len(message.text.split()) < 3:
                bot.reply_to(message, "❌ Используйте: /дартс [тип] [сумма]\nТипы: мимо, красное, белое, центр")
                return
            
            bet_type = message.text.split()[1].lower()
            try:
                bet_amount = float(message.text.split()[2])
            except ValueError:
                bot.reply_to(message, "❌ Введите корректную сумму!")
                return
            
            # Проверяем тип ставки
            valid_types = ["мимо", "красное", "белое", "центр", "miss", "red", "white", "bullseye"]
            if bet_type not in valid_types:
                bot.reply_to(message, "❌ Неверный тип ставки! Используйте: мимо, красное, белое, центр")
                return
            
            # Проверяем минимальную ставку для дартса
            if bet_amount < MIN_BET_OTHER:
                bot.reply_to(message, f"❌ Минимальная ставка для дартса: {MIN_BET_OTHER}₽!")
                return
            
            # Нормализуем тип ставки
            type_map = {
                "miss": "мимо",
                "red": "красное",
                "white": "белое",
                "bullseye": "центр"
            }
            if bet_type in type_map:
                bet_type = type_map[bet_type]
            
            # Запускаем игру в отдельном потоке
            threading.Thread(
                target=play_darts_game_chat,
                args=(bot, message, bet_type, bet_amount, user_id, username),
                daemon=True
            ).start()
            
        except Exception as e:
            logging.error(f"Ошибка в darts_command: {e}")
            bot.reply_to(message, "❌ Произошла ошибка!")

    # ДОБАВЛЕН: Обработчик для нажатия на кнопки игр из инлайн-меню
    @bot.callback_query_handler(func=lambda call: call.data in ["games_dice", "games_basketball", "games_football", "games_darts"])
    def handle_game_selection(call):
        try:
            user_id = str(call.from_user.id)

            # Проверяем ограничение по времени
            if not rate_limit(user_id):
                bot.answer_callback_query(call.id, "❌ Слишком быстро! Подождите 0.4 секунды.", show_alert=True)
                return

            # Проверяем активную игру
            with bet_lock:
                if user_id in active_games:
                    bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                    return

            users_data = load_users_data()

            if user_id not in users_data:
                users_data[user_id] = {'balance': 0}
                save_users_data(users_data)

            balance = users_data[user_id].get('balance', 0)
            balance_rounded = round(balance, 2)

            # Определяем тип игры
            game_types = {
                "games_dice": ("🎲 Кости", "dice"),
                "games_basketball": ("🏀 Баскетбол", "basketball"),
                "games_football": ("⚽ Футбол", "football"),
                "games_darts": ("🎯 Дартс", "darts")
            }

            game_name, game_type = game_types[call.data]

            with bet_lock:
                active_bets[user_id] = {'game_type': game_type}

            bot.edit_message_text(
                f"""<b>{game_name}</b>

<blockquote>💵 Баланс: {balance_rounded}₽</blockquote>

Выберите сумму ставки:""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=get_bet_selection_keyboard()
            )

        except Exception as e:
            logging.error(f"Ошибка в handle_game_selection: {e}")
            try:
                bot.answer_callback_query(call.id, "❌ Произошла ошибка при запуске игры!")
            except:
                pass

    @bot.message_handler(func=lambda message: message.text in ["🎲 Кости", "🏀 Баскетбол", "🎯 Дартс", "⚽ Футбол"])
    def games_start(message):
        try:
            user_id = str(message.from_user.id)

            # Проверяем ограничение по времени
            if not rate_limit(user_id):
                bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.4 секунды.")
                return

            # Проверяем активную игру
            with bet_lock:
                if user_id in active_games:
                    bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                    return

            users_data = load_users_data()

            if user_id not in users_data:
                users_data[user_id] = {'balance': 0}
                save_users_data(users_data)

            balance = users_data[user_id].get('balance', 0)
            balance_rounded = round(balance, 2)

            with bet_lock:
                if message.text == "🎲 Кости":
                    active_bets[user_id] = {'game_type': 'dice'}
                    game_name = "🎲 Кости"
                elif message.text == "🏀 Баскетбол":
                    active_bets[user_id] = {'game_type': 'basketball'}
                    game_name = "🏀 Баскетбол"
                elif message.text == "⚽ Футбол":
                    active_bets[user_id] = {'game_type': 'football'}
                    game_name = "⚽ Футбол"
                elif message.text == "🎯 Дартс":
                    active_bets[user_id] = {'game_type': 'darts'}
                    game_name = "🎯 Дартс"

            bot.send_message(
                message.chat.id,
                f"""<b>{game_name}</b>

<blockquote>💵 Баланс: {balance_rounded}₽</blockquote>

Выберите сумму ставки:""",
                parse_mode='HTML',
                reply_markup=get_bet_selection_keyboard()
            )
        except Exception as e:
            logging.error(f"Ошибка в games_start: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка при запуске игры!")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('games_'))
    def games_callback_handler(call):
        try:
            user_id = str(call.from_user.id)

            # Проверяем ограничение по времени
            if not rate_limit(user_id):
                bot.answer_callback_query(call.id, "❌ Слишком быстро! Подождите 0.4 секунды.", show_alert=True)
                return

            # Проверяем активную игру
            with bet_lock:
                if user_id in active_games:
                    bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                    return

            users_data = load_users_data()

            if call.data.startswith("games_bet_"):
                bet_amount = float(call.data.split("_")[2])

                balance = users_data[user_id].get('balance', 0)
                if bet_amount > balance:
                    bot.answer_callback_query(call.id, "❌ Недостаточно средств!")
                    return

                # Сохраняем сумму ставку
                with bet_lock:
                    if user_id not in active_bets:
                        bot.answer_callback_query(call.id, "❌ Сначала выберите игру!", show_alert=True)
                        return

                    active_bets[user_id]['bet_amount'] = bet_amount
                    game_type = active_bets[user_id]['game_type']

                # Списываем ставку
                users_data[user_id]['balance'] = round(balance - bet_amount, 2)
                save_users_data(users_data)

                # Генерируем токен сессии
                session_token = generate_session_token(user_id, game_type)
                with bet_lock:
                    game_session_tokens[user_id] = session_token

                if game_type == "dice":
                    bot.edit_message_text(
                        f"""<b>🎲 Кости</b>

<blockquote>💵 Сумма ставки: {bet_amount}₽</blockquote>

Выберите исход:""",
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='HTML',
                        reply_markup=get_dice_selection_keyboard()
                    )
                elif game_type == "basketball":
                    bot.edit_message_text(
                        f"""<b>🏀 Баскетбол</b>

<blockquote>💵 Сумма ставки: {bet_amount}₽</blockquote>

Выберите исход:""",
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='HTML',
                        reply_markup=get_basketball_selection_keyboard()
                    )
                elif game_type == "football":
                    bot.edit_message_text(
                        f"""<b>⚽ Футбол</b>

<blockquote>💵 Сумма ставки: {bet_amount}₽</blockquote>

Выберите исход:""",
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='HTML',
                        reply_markup=get_football_selection_keyboard()
                    )
                elif game_type == "darts":
                    bot.edit_message_text(
                        f"""<b>🎯 Дартс</b>

<blockquote>💵 Сумма ставки: {bet_amount}₽</blockquote>

Выберите исход:""",
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='HTML',
                        reply_markup=get_darts_selection_keyboard()
                    )
                return

            elif call.data == "games_custom_bet":
                with bet_lock:
                    if user_id not in active_bets:
                        bot.answer_callback_query(call.id, "❌ Сначала выберите игру!", show_alert=True)
                        return

                bot.send_message(call.message.chat.id,
                               """<b>📝 Ввод суммы</b>

<blockquote>Введите сумму ставки:</blockquote>""",
                               parse_mode='HTML')
                bot.register_next_step_handler(call.message, process_custom_bet_games)
                return

        except Exception as e:
            logging.error(f"Ошибка в games_callback_handler: {e}")
            try:
                bot.answer_callback_query(call.id, "❌ Произошла ошибка!")
            except:
                pass

    # ОБРАБОТЧИКИ ДЛЯ ВЫБОРА РЕЖИМОВ В ИГРАХ
    @bot.callback_query_handler(func=lambda call: call.data.startswith(('dice_', 'basketball_', 'football_', 'darts_')))
    def games_mode_callback_handler(call):
        try:
            user_id = str(call.from_user.id)

            # Проверяем ограничение по времени
            if not rate_limit(user_id):
                bot.answer_callback_query(call.id, "❌ Слишком быстро! Подождите 0.4 секунды.", show_alert=True)
                return

            with bet_lock:
                if user_id not in active_bets or 'bet_amount' not in active_bets[user_id]:
                    bot.answer_callback_query(call.id, "❌ Сначала сделайте ставку!")
                    return

                if user_id in active_games:
                    bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                    return

                bet_amount = active_bets[user_id]['bet_amount']
                game_type = active_bets[user_id]['game_type']
                session_token = game_session_tokens.get(user_id, generate_session_token(user_id, game_type))

            # Обработка выбора в играх
            if call.data.startswith("dice_"):
                bet_type = call.data.split("_")[1]
                threading.Thread(
                    target=play_dice_game,
                    args=(bot, call, bet_type, bet_amount, user_id, session_token),
                    daemon=True
                ).start()

            elif call.data.startswith("basketball_"):
                bet_type = call.data.split("_")[1]
                threading.Thread(
                    target=play_basketball_game,
                    args=(bot, call, bet_type, bet_amount, user_id, session_token),
                    daemon=True
                ).start()

            elif call.data.startswith("football_"):
                bet_type = call.data.split("_")[1]
                threading.Thread(
                    target=play_football_game,
                    args=(bot, call, bet_type, bet_amount, user_id, session_token),
                    daemon=True
                ).start()

            elif call.data.startswith("darts_"):
                bet_type = call.data.split("_")[1]
                threading.Thread(
                    target=play_darts_game,
                    args=(bot, call, bet_type, bet_amount, user_id, session_token),
                    daemon=True
                ).start()

            # Показываем загрузку
            bot.answer_callback_query(call.id, "🎮 Запускаем игру...")

        except Exception as e:
            logging.error(f"Ошибка в games_mode_callback_handler: {e}")
            try:
                bot.answer_callback_query(call.id, "❌ Ошибка запуска игры")
            except:
                pass