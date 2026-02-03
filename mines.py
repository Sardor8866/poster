import telebot
from telebot import types
import random
import json
import time
import threading
import logging
import hashlib
from contextlib import contextmanager

import referrals

try:
    from leaders import add_game_to_history
except ImportError:
    def add_game_to_history(user_id, bet_amount, win_amount, is_win, game_type="mines"):
        logging.warning(f"Модуль лидеров не найден, игра не записана в историю: {user_id}")
        return False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MinesGame:
    def __init__(self, user_id, mines_count, bet_amount, chat_id=None, message_id=None):
        self.user_id = user_id
        self.mines_count = mines_count
        self.bet_amount = bet_amount
        self.grid_size = 5
        self.grid = [[0 for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        self.revealed = [[False for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        self.mines_positions = []
        self.multiplier = 1.0
        self.previous_multiplier = 1.0
        self.opened_cells = 0
        self.game_active = True
        self.session_token = generate_session_token(user_id, 'mines')
        self.place_mines()
        self.last_action_time = time.time()
        self.action_lock = threading.Lock()
        self.created_time = time.time()
        self.chat_id = chat_id
        self.message_id = message_id

    def place_mines(self):
        positions = [(i, j) for i in range(self.grid_size) for j in range(self.grid_size)]
        self.mines_positions = random.sample(positions, self.mines_count)

    def get_multiplier_for_opened_cells(self, opened_safe_cells):
        multipliers = {
            2: [1.08, 1.17, 1.29, 1.41, 1.56, 1.74, 1.94, 2.18, 2.48, 2.83, 3.26, 3.81, 4.5, 5.4, 6.6, 8.25, 10.61, 14.14, 19.8, 29.7, 49.5, 99.0, 297.0],
            3: [1.12, 1.29, 1.48, 1.71, 2.0, 2.35, 2.79, 3.35, 4.07, 5.0, 6.26, 7.96, 10.35, 13.8, 18.98, 27.11, 40.66, 65.06, 113.85, 227.7, 569.25, 2277.0],
            4: [1.18, 1.41, 1.71, 2.09, 2.58, 3.23, 4.09, 5.26, 6.88, 9.17, 12.51, 17.52, 25.3, 37.95, 59.64, 99.39, 178.91, 357.81, 834.9, 2504.7, 12523.5],
            5: [1.24, 1.56, 2.0, 2.58, 3.39, 4.52, 6.14, 8.5, 12.04, 17.52, 26.27, 40.87, 66.41, 113.85, 208.72, 417.45, 939.26, 2504.7, 8766.45],
            6: [1.3, 1.74, 2.35, 3.23, 4.52, 6.46, 9.44, 14.17, 21.89, 35.03, 58.38, 102.17, 189.75, 379.5, 834.9, 2087.25, 6261.75, 25047.0],
            7: [1.38, 1.94, 2.79, 3.82, 6.14, 9.44, 14.95, 24.47, 41.6, 73.95, 138.66, 277.33, 600.88, 1442.1, 3965.78, 13219.25],
            8: [1.46, 2.18, 3.35, 5.26, 8.5, 14.17, 24.47, 44.05, 83.2, 166.4, 356.56, 831.98, 2163.15, 6489.45, 23794.65],
            9: [1.55, 2.48, 3.67, 5.88, 10.04, 21.89, 41.6, 83.2, 176.8, 404.1, 1010.26, 2828.73, 9193.39, 36773.55],
            10: [1.65, 2.83, 4.8, 9.17, 16.52, 35.03, 73.95, 166.4, 404.1, 1077.61, 3232.84, 11314.94],
            11: [1.77, 3.26, 6.26, 11.51, 26.27, 58.38, 138.66, 356.56, 1010.26, 3232.84, 12123.15],
            12: [1.85, 3.61, 7.96, 17.52, 40.87, 102.17, 277.33, 831.98, 2828.73, 11314.94],
            13: [2.06, 4.5, 10.35, 25.3, 66.41, 189.75, 600.88, 2163.15, 9193.39],
            14: [2.25, 5.4, 13.8, 37.95, 113.85, 379.5, 1442.1, 6489.45, 36773.55],
            15: [2.48, 6.6, 18.98, 59.64, 208.72, 834.9, 3965.78, 23794.65],
            16: [2.75, 8.25, 27.11, 99.39, 417.45, 2087.25, 13219.25],
            17: [3.09, 10.61, 40.66, 178.91, 939.26, 6261.75],
            18: [3.54, 14.14, 65.06, 357.81, 2504.7, 25047.0],
            19: [4.12, 19.8, 113.85, 834.9, 8766.45],
            20: [4.95, 29.7, 227.7, 2504.7],
            21: [6.19, 49.5, 569.25, 12523.5],
            22: [8.25, 99.0, 2277.0],
            23: [12.38, 297.0],
            24: [24.75],
        }
        
        if self.mines_count in multipliers:
            multipliers_list = multipliers[self.mines_count]
            if opened_safe_cells <= len(multipliers_list):
                return multipliers_list[opened_safe_cells - 1]
            else:
                return multipliers_list[-1]
        return 1.0

    def reveal_cell(self, x, y):
        if not (0 <= x < self.grid_size and 0 <= y < self.grid_size):
            return False

        if self.revealed[x][y]:
            return True

        self.revealed[x][y] = True

        self.previous_multiplier = self.multiplier

        if (x, y) in self.mines_positions:
            self.game_active = False
            return False

        self.opened_cells += 1
        self.multiplier = self.get_multiplier_for_opened_cells(self.opened_cells)

        return True

    def get_next_multiplier(self):
        next_opened = self.opened_cells + 1
        return self.get_multiplier_for_opened_cells(next_opened)

users_data_lock = threading.Lock()

def load_users_data():
    """Загружает данные пользователей"""
    try:
        with users_data_lock:
            with open('users_data.json', 'r', encoding='utf-8') as f:
                return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.error(f"Ошибка загрузки данных: {e}")
        return {}

def save_users_data(data):
    try:
        with users_data_lock:
            with open('users_data.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения данных: {e}")

def generate_session_token(user_id, game_type):
    """Генерирует уникальный токен для сессии игры"""
    timestamp = str(time.time())
    data = f"{user_id}_{game_type}_{timestamp}"
    return hashlib.md5(data.encode()).hexdigest()[:8]

active_games = {}
user_temp_data = {}
last_click_time = {}
mines_lock = threading.Lock()
processing_actions = {}
processing_lock = threading.Lock()

MIN_BET = 10
MAX_BET = float('inf')

GAME_TIMEOUT = 300

def cleanup_inactive_games():
    """Очистка неактивных игр и возврат ставок"""
    current_time = time.time()
    games_to_remove = []
    
    with mines_lock:
        for user_id, game in list(active_games.items()):
            if current_time - game.created_time > GAME_TIMEOUT:
                logging.info(f"Удаление неактивной игры пользователя {user_id}, созданной {current_time - game.created_time:.1f} секунд назад")
                games_to_remove.append((user_id, game))
    
    for user_id, game in games_to_remove:
        try:
            users_data = load_users_data()
            if user_id in users_data:
                users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0) + game.bet_amount, 2)
                save_users_data(users_data)
                logging.info(f"Возвращена ставка {game.bet_amount} пользователю {user_id} за неактивную игру")
            
            if game.chat_id and game.message_id:
                try:
                    timeout_message = f"""
<blockquote expandable>╔══════════════════════╗
   ⏰ <b>ИГРА ЗАКРЫТА</b> ⏰
╚══════════════════════╝</blockquote>

<blockquote>
<b>⏱️ Игра была автоматически закрыта</b>
<b>📝 Причина:</b> 5 минут бездействия

<b>💰 Результат:</b>
├ 💸 Ставка: <b>{game.bet_amount}₽</b>
├ 🔄 Возвращено: <b>{game.bet_amount}₽</b>
└ 📊 Открыто ячеек: <b>{game.opened_cells}</b>
</blockquote>

<i>Ваша ставка возвращена на баланс! ✅</i>
"""
                    bot.edit_message_text(
                        timeout_message,
                        game.chat_id,
                        game.message_id,
                        parse_mode='HTML'
                    )
                    time.sleep(3)
                except Exception as e:
                    if "message is not modified" not in str(e) and "message to edit not found" not in str(e):
                        logging.error(f"Ошибка при редактировании сообщения игры {user_id}: {e}")
            
            with mines_lock:
                if user_id in active_games and active_games[user_id].session_token == game.session_token:
                    del active_games[user_id]
            
            with mines_lock:
                if user_id in user_temp_data:
                    del user_temp_data[user_id]
            
            with mines_lock:
                if user_id in last_click_time:
                    del last_click_time[user_id]
            
            with processing_lock:
                keys_to_remove = [k for k in processing_actions.keys() if k.startswith(f"{user_id}_")]
                for k in keys_to_remove:
                    del processing_actions[k]
                    
        except Exception as e:
            logging.error(f"Ошибка при удалении неактивной игры пользователя {user_id}: {e}")

def start_cleanup_thread():
    """Запускает поток для периодической очистки неактивных игр"""
    def cleanup_worker():
        while True:
            try:
                cleanup_inactive_games()
                time.sleep(60)
            except Exception as e:
                logging.error(f"Ошибка в cleanup_worker: {e}")
                time.sleep(60)
    
    thread = threading.Thread(target=cleanup_worker, daemon=True)
    thread.start()
    return thread

def rate_limit_mines(user_id):
    """Проверка ограничения по времени между нажатиями (0.3 секунды)"""
    current_time = time.time()
    with mines_lock:
        if user_id in last_click_time:
            if current_time - last_click_time[user_id] < 0.3:
                return False
        last_click_time[user_id] = current_time
    return True

def is_action_processing(user_id, action_key=""):
    """Проверяет, обрабатывается ли уже действие пользователя"""
    key = f"{user_id}_{action_key}"
    with processing_lock:
        if key in processing_actions:
            if time.time() - processing_actions[key] < 0.3:
                return True
            else:
                del processing_actions[key]
        return False

def mark_action_processing(user_id, action_key=""):
    """Отмечает начало обработки действия"""
    key = f"{user_id}_{action_key}"
    with processing_lock:
        processing_actions[key] = time.time()

def clear_action_processing(user_id, action_key=""):
    """Очищает отметку о обработке действия"""
    key = f"{user_id}_{action_key}"
    with processing_lock:
        if key in processing_actions:
            del processing_actions[key]

def get_bet_selection_keyboard():
    """Клавиатура выбора ставки с новыми значениями"""
    markup = types.InlineKeyboardMarkup(row_width=5)
    bets = ["25", "50", "125", "250", "500"]
    buttons = [types.InlineKeyboardButton(f"{bet}₽", callback_data=f"mine_bet_{bet}") for bet in bets]
    markup.row(*buttons)
    markup.row(types.InlineKeyboardButton("📝 Ввести вручную", callback_data="mine_custom_bet"))
    return markup

def get_mines_selection_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=5)
    mines_counts = ["2", "5", "10", "15", "18"]
    buttons = [types.InlineKeyboardButton(f"{count}", callback_data=f"mine_count_{count}") for count in mines_counts]
    markup.row(*buttons)
    markup.row(types.InlineKeyboardButton("📝 Ввести вручную", callback_data="mine_custom_count"))
    return markup

def get_game_keyboard(game, game_over=False):
    markup = types.InlineKeyboardMarkup(row_width=5)

    buttons = []
    for i in range(game.grid_size):
        row_buttons = []
        for j in range(game.grid_size):
            if game_over:
                if (i, j) in game.mines_positions:
                    if game.revealed[i][j]:
                        emoji = "💢"
                    else:
                        emoji = "💢"
                elif game.revealed[i][j]:
                    emoji = "💎"
                else:
                    emoji = "◾️"
                callback_data = "mine_ignore"
            else:
                if game.revealed[i][j]:
                    if (i, j) in game.mines_positions:
                        emoji = "💢"
                    else:
                        emoji = "💎"
                    callback_data = "mine_ignore"
                else:
                    emoji = "◽️"
                    callback_data = f"mine_cell_{i}_{j}"

            button = types.InlineKeyboardButton(
                emoji,
                callback_data=callback_data
            )
            row_buttons.append(button)
        buttons.append(row_buttons)

    for row in buttons:
        markup.row(*row)

    if not game_over and game.opened_cells > 0:
        markup.row(types.InlineKeyboardButton(
            f"💰 ЗАБРАТЬ {round(game.bet_amount * game.multiplier, 2)}₽",
            callback_data="mine_cashout"
        ))

    return markup

def format_game_info(game):
    """Форматирует информацию об игре в красивый вид"""
    next_mult = game.get_next_multiplier()
    
    game_lifetime = time.time() - game.created_time
    minutes = int(game_lifetime // 60)
    seconds = int(game_lifetime % 60)
    
    time_left = GAME_TIMEOUT - game_lifetime
    if time_left > 0:
        minutes_left = int(time_left // 60)
        seconds_left = int(time_left % 60)
        time_info = f"{minutes} мин {seconds} сек (автоудаление через {minutes_left}:{seconds_left:02d})"
    else:
        time_info = f"{minutes} мин {seconds} сек (ожидание удаления)"

    game_info = f"""
<blockquote expandable>╔══════════════════════╗
   💣 <b>ИГРА МИНЫ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
<b>🎯 Конфигурация:</b>
├ 💸Ставка: <b>{game.bet_amount}₽</b>
├ 💣Мины: <b>{game.mines_count}</b>
└ 💹Открыто: <b>{game.opened_cells}</b> ячеек

<b>📊 Множители:</b>
├ ⬅️ Прошлый: <b>x{game.previous_multiplier:.2f}</b>
├ ✅ Текущий: <b>x{game.multiplier:.2f}</b>
└ ➡️ Следующий: <b>x{next_mult:.2f}</b>

<b>⏰ Время игры:</b>
└ {time_info}
</blockquote>

<i>Выберите безопасную ячейку! Игра будет закрыта через 5 минут бездействия.</i>
"""
    return game_info

def format_game_result(game, win_amount, is_win=False):
    """Форматирует результат игры"""
    if is_win:
        return f"""
<blockquote expandable>╔══════════════════════╗
   🎉 <b>ПОБЕДА!</b> 🎉
╚══════════════════════╝</blockquote>

<blockquote>
<b>💰 Результат:</b>
├ 💸Ставка: <b>{game.bet_amount}₽</b>
├ 🍀Выигрыш: <b>{round(win_amount, 2)}₽</b>
└ 📌Множитель: <b>x{game.multiplier:.2f}</b>

<b>📊 Статистика:</b>
├ Открыто ячеек: <b>{game.opened_cells}</b>
└ Всего мин💣: <b>{game.mines_count}</b>
</blockquote>

<i>Отличная игра! Поздравляем с победой! 🥳</i>
"""
    else:
        return f"""
<blockquote expandable>╔══════════════════════╗
   💥 <b>ПОРАЖЕНИЕ</b> 💥
╚══════════════════════╝</blockquote>

<blockquote>
<b>💰 Результат:</b>
├ 💸Ставка: <b>{game.bet_amount}₽</b>
├ 📉Потеряно: <b>{game.bet_amount}₽</b>
└ 📌Множитель: <b>x{game.multiplier:.2f}</b>

<b>📊 Статистика:</b>
├ Открыто ячеек: <b>{game.opened_cells}</b>
└ Попал на мину: <b>💣</b>
</blockquote>

<i>Не повезло в этот раз! Попробуйте еще! 💪</i>
"""

bot = None

def cancel_user_game(user_id, notify_user=True):
    """Принудительно отменяет игру пользователя и возвращает ставку"""
    try:
        with mines_lock:
            if user_id not in active_games:
                return False
            
            game = active_games[user_id]
            
            users_data = load_users_data()
            if user_id in users_data:
                users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0) + game.bet_amount, 2)
                save_users_data(users_data)
                logging.info(f"Принудительно возвращена ставка {game.bet_amount} пользователю {user_id}")
            
            if notify_user and game.chat_id and game.message_id:
                try:
                    cancel_message = f"""
<blockquote expandable>╔══════════════════════╗
   🚫 <b>ИГРА ОТМЕНЕНА</b> 🚫
╚══════════════════════╝</blockquote>

<blockquote>
<b>⏱️ Игра была отменена</b>

<b>💰 Результат:</b>
├ 💸 Ставка: <b>{game.bet_amount}₽</b>
├ 🔄 Возвращено: <b>{game.bet_amount}₽</b>
└ 📊 Открыто ячеек: <b>{game.opened_cells}</b>
</blockquote>

<i>Ваша ставка возвращена на баланс! ✅</i>
"""
                    bot.edit_message_text(
                        cancel_message,
                        game.chat_id,
                        game.message_id,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    if "message is not modified" not in str(e) and "message to edit not found" not in str(e):
                        logging.error(f"Ошибка при редактировании сообщения отмены {user_id}: {e}")
                        try:
                            bot.send_message(game.chat_id, cancel_message, parse_mode='HTML')
                        except:
                            pass
            
            del active_games[user_id]
            
            if user_id in user_temp_data:
                del user_temp_data[user_id]
            
            if user_id in last_click_time:
                del last_click_time[user_id]
            
            with processing_lock:
                keys_to_remove = [k for k in processing_actions.keys() if k.startswith(f"{user_id}_")]
                for k in keys_to_remove:
                    del processing_actions[k]
            
            return True
            
    except Exception as e:
        logging.error(f"Ошибка при отмене игры пользователя {user_id}: {e}")
        return False

def start_mines_game_from_command(user_id, mines_count, bet_amount, message=None, chat_id=None, message_id=None):
    """Функция для запуска игры через команду"""
    try:
        if not rate_limit_mines(user_id):
            if message:
                bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.3 секунды.")
            return False

        with mines_lock:
            if user_id in active_games:
                game = active_games[user_id]
                current_time = time.time()
                if current_time - game.created_time > GAME_TIMEOUT:
                    cancel_user_game(user_id)
                else:
                    if message:
                        bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                    return False

        if mines_count < 2 or mines_count > 24:
            if message:
                bot.send_message(message.chat.id, "❌ Количество мин должно быть от 2 до 24!")
            return False

        if bet_amount < MIN_BET:
            if message:
                bot.send_message(message.chat.id, f"❌ Минимальная ставка: {MIN_BET}₽")
            return False

        users_data = load_users_data()
        
        if user_id not in users_data:
            users_data[user_id] = {'balance': 0}
            save_users_data(users_data)

        balance = users_data[user_id].get('balance', 0)
        if bet_amount > balance:
            if message:
                bot.send_message(message.chat.id, "❌ Недостаточно средств!")
            return False

        if message:
            game = MinesGame(user_id, mines_count, bet_amount, chat_id=message.chat.id)
        elif chat_id:
            game = MinesGame(user_id, mines_count, bet_amount, chat_id=chat_id, message_id=message_id)
        else:
            game = MinesGame(user_id, mines_count, bet_amount)

        with mines_lock:
            active_games[user_id] = game

        users_data[user_id]['balance'] = round(balance - bet_amount, 2)
        save_users_data(users_data)

        if message:
            sent_message = bot.send_message(
                message.chat.id,
                format_game_info(game),
                parse_mode='HTML',
                reply_markup=get_game_keyboard(game)
            )
            game.message_id = sent_message.message_id
        elif chat_id and message_id:
            try:
                bot.edit_message_text(
                    format_game_info(game),
                    chat_id,
                    message_id,
                    parse_mode='HTML',
                    reply_markup=get_game_keyboard(game)
                )
                game.message_id = message_id
            except Exception as e:
                if "message is not modified" not in str(e):
                    logging.error(f"Ошибка edit_message_text при запуске игры: {e}")
                    sent_message = bot.send_message(
                        chat_id,
                        format_game_info(game),
                        parse_mode='HTML',
                        reply_markup=get_game_keyboard(game)
                    )
                    game.message_id = sent_message.message_id
        elif chat_id:
            sent_message = bot.send_message(
                chat_id,
                format_game_info(game),
                parse_mode='HTML',
                reply_markup=get_game_keyboard(game)
            )
            game.message_id = sent_message.message_id
        
        return True
    except Exception as e:
        logging.error(f"Ошибка в start_mines_game_from_command: {e}")
        if message:
            bot.send_message(message.chat.id, "❌ Произошла ошибка при запуске игры!")
        return False

def parse_mines_command(text):
    """Парсит команду /мины или /mines и возвращает (количество_мин, сумма_ставки)"""
    try:
        parts = text.strip().split()
        
        if len(parts) < 3:
            return None, None
        
        if parts[0].lower() not in ['/мины', '/mines', 'мины', 'mines']:
            return None, None
        
        mines_count = None
        bet_amount = None
        
        for i in range(1, len(parts)):
            if not mines_count:
                try:
                    mines_count = int(parts[i])
                    if not (2 <= mines_count <= 24):
                        mines_count = None
                except:
                    pass
            
            if mines_count and i + 1 < len(parts):
                try:
                    bet_amount = float(parts[i + 1])
                    if bet_amount < MIN_BET:
                        bet_amount = None
                    break
                except:
                    pass
        
        return mines_count, bet_amount
    except Exception as e:
        logging.error(f"Ошибка при парсинге команды: {e}")
        return None, None

def register_mines_handlers(bot_instance):
    global bot
    bot = bot_instance
    
    start_cleanup_thread()

    @bot.message_handler(func=lambda message: message.text and 
                        (message.text.lower().startswith('/мины') or 
                         message.text.lower().startswith('/mines') or
                         message.text.lower().startswith('мины ') or
                         message.text.lower().startswith('mines ')))
    def mines_command_handler(message):
        user_id = str(message.from_user.id)
        
        mines_count, bet_amount = parse_mines_command(message.text)
        
        if mines_count is None or bet_amount is None:
            help_text = """<blockquote expandable>╔══════════════════════╗
   💣 <b>ИГРА МИНЫ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
<b>📖 Как играть:</b>
• Напишите <code>/мины 10 100</code> чтобы начать игру с 10 минами и ставкой 100₽
• Или используйте меню для настройки игры

<b>🎯 Правила:</b>
• Открывайте безопасные ячейки без мин
• Каждая открытая ячейка увеличивает множитель
• Заберите выигрыш в любой момент
• Если наступите на мину - проигрываете ставку

<b>⚙️ Параметры:</b>
• Мины: от 2 до 24
• Минимальная ставка: 10₽
• Игра автоматически закрывается через 5 минут бездействия (ставка возвращается)
</blockquote>"""
            bot.send_message(message.chat.id, help_text, parse_mode='HTML')
            return
        
        start_mines_game_from_command(user_id, mines_count, bet_amount, message=message)

    def process_custom_bet(message):
        try:
            user_id = str(message.from_user.id)

            bet_amount = float(message.text)

            if bet_amount < MIN_BET:
                bot.send_message(message.chat.id, f"❌ Минимальная ставка: {MIN_BET}₽")
                return

            if bet_amount > MAX_BET:
                bot.send_message(message.chat.id, f"❌ Максимальная ставка: {MAX_BET}₽")
                return

            users_data = load_users_data()
            
            if user_id not in users_data:
                users_data[user_id] = {'balance': 0}

            balance = users_data[user_id].get('balance', 0)
            if bet_amount > balance:
                bot.send_message(message.chat.id, "❌ Недостаточно средств!")
                return

            with mines_lock:
                user_temp_data[user_id] = {'bet_amount': bet_amount}

            bot.send_message(
                message.chat.id,
                """<blockquote expandable>╔══════════════════════╗
   💣 <b>ИГРА МИНЫ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
Выберите количество мин (2-24):
</blockquote>""",
                parse_mode='HTML',
                reply_markup=get_mines_selection_keyboard()
            )
        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите корректную сумму!")
        except Exception as e:
            logging.error(f"Ошибка в process_custom_bet: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка!")

    def process_custom_mines(message):
        try:
            user_id = str(message.from_user.id)

            mines_count = int(message.text)
            if not 2 <= mines_count <= 24:
                bot.send_message(message.chat.id, "❌ Введите число от 2 до 24!")
                return

            users_data = load_users_data()

            with mines_lock:
                if user_id in active_games:
                    game = active_games[user_id]
                    current_time = time.time()
                    if current_time - game.created_time > GAME_TIMEOUT:
                        cancel_user_game(user_id)
                    else:
                        bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                        return

                if user_id not in user_temp_data or 'bet_amount' not in user_temp_data[user_id]:
                    bot.send_message(message.chat.id, "❌ Ошибка данных! Начните заново.")
                    return

                bet_amount = user_temp_data[user_id]['bet_amount']

            balance = users_data[user_id].get('balance', 0)
            if bet_amount > balance:
                bot.send_message(message.chat.id, "❌ Недостаточно средств!")
                return

            success = start_mines_game_from_command(
                user_id=user_id,
                mines_count=mines_count,
                bet_amount=bet_amount,
                message=message
            )

            if success:
                with mines_lock:
                    if user_id in user_temp_data:
                        del user_temp_data[user_id]

        except ValueError:
            bot.send_message(message.chat.id, "❌ Введите корректное число!")
        except Exception as e:
            logging.error(f"Ошибка в process_custom_mines: {e}")
            bot.send_message(message.chat.id, "❌ Произошла ошибка!")

    @bot.message_handler(func=lambda message: message.text in ["💣 Мины", "мины", "Mines"])
    def mines_start_internal(message):
        user_id = str(message.from_user.id)

        if not rate_limit_mines(user_id):
            bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.3 секунды.")
            return

        with mines_lock:
            if user_id in active_games:
                game = active_games[user_id]
                current_time = time.time()
                if current_time - game.created_time > GAME_TIMEOUT:
                    cancel_user_game(user_id)
                else:
                    bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                    return

        users_data = load_users_data()

        if user_id not in users_data:
            users_data[user_id] = {'balance': 0}
            save_users_data(users_data)

        balance = users_data[user_id].get('balance', 0)
        balance_rounded = round(balance, 2)

        bot.send_message(
            message.chat.id,
            f"""<blockquote expandable>╔══════════════════════╗
   💣 <b>ИГРА МИНЫ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
💎 Баланс: <b>{balance_rounded}₽</b>
</blockquote>

<i>Выберите сумму ставки:</i>""",
            parse_mode='HTML',
            reply_markup=get_bet_selection_keyboard()
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('mine_'))
    def mines_callback_handler(call):
        try:
            user_id = str(call.from_user.id)

            
            action_key = ""
            if call.data.startswith("mine_cell_"):
                parts = call.data.split("_")
                x, y = int(parts[2]), int(parts[3])
                action_key = f"cell_{x}_{y}"
            elif call.data == "mine_cashout":
                action_key = "cashout"
            elif call.data.startswith("mine_bet_"):
                bet = call.data.split("_")[2]
                action_key = f"bet_{bet}"
            elif call.data.startswith("mine_count_"):
                count = call.data.split("_")[2]
                action_key = f"count_{count}"
            else:
                action_key = call.data

            if is_action_processing(user_id, action_key):
                try:
                    bot.answer_callback_query(call.id, "⏳ Действие уже обрабатывается...", show_alert=False)
                except:
                    pass
                return

            mark_action_processing(user_id, action_key)

            if call.data.startswith("mine_bet_"):
                with mines_lock:
                    if user_id in active_games:
                        game = active_games[user_id]
                        current_time = time.time()
                        if current_time - game.created_time > GAME_TIMEOUT:
                            cancel_user_game(user_id)
                        else:
                            try:
                                bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                            except:
                                pass
                            clear_action_processing(user_id, action_key)
                            return

                bet_amount = float(call.data.split("_")[2])

                users_data = load_users_data()
                balance = users_data[user_id].get('balance', 0)
                if bet_amount > balance:
                    try:
                        bot.answer_callback_query(call.id, "❌ Недостаточно средств!")
                    except:
                        pass
                    clear_action_processing(user_id, action_key)
                    return

                with mines_lock:
                    user_temp_data[user_id] = {'bet_amount': bet_amount}

                try:
                    bot.edit_message_text(
                        """<blockquote expandable>╔══════════════════════╗
   💣 <b>ИГРА МИНЫ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
Выберите количество мин (2-24):
</blockquote>""",
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='HTML',
                        reply_markup=get_mines_selection_keyboard()
                    )
                except Exception as e:
                    if "message is not modified" not in str(e):
                        logging.error(f"Ошибка edit_message_text mine_bet: {e}")
                finally:
                    clear_action_processing(user_id, action_key)
                return

            elif call.data.startswith("mine_count_"):
                mines_count = int(call.data.split("_")[2])

                with mines_lock:
                    if user_id in active_games:
                        game = active_games[user_id]
                        current_time = time.time()
                        if current_time - game.created_time > GAME_TIMEOUT:
                            cancel_user_game(user_id)
                        else:
                            try:
                                bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                            except:
                                pass
                            clear_action_processing(user_id, action_key)
                            return

                    if user_id not in user_temp_data or 'bet_amount' not in user_temp_data[user_id]:
                        try:
                            bot.answer_callback_query(call.id, "❌ Ошибка данных!")
                        except:
                            pass
                        clear_action_processing(user_id, action_key)
                        return

                    bet_amount = user_temp_data[user_id]['bet_amount']

                users_data = load_users_data()
                balance = users_data[user_id].get('balance', 0)
                if bet_amount > balance:
                    try:
                        bot.answer_callback_query(call.id, "❌ Недостаточно средств!")
                    except:
                        pass
                    clear_action_processing(user_id, action_key)
                    return

                success = start_mines_game_from_command(
                    user_id=user_id,
                    mines_count=mines_count,
                    bet_amount=bet_amount,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id
                )

                if success:
                    with mines_lock:
                        if user_id in user_temp_data:
                            del user_temp_data[user_id]

                clear_action_processing(user_id, action_key)
                return

            elif call.data == "mine_custom_bet":
                with mines_lock:
                    if user_id in active_games:
                        game = active_games[user_id]
                        current_time = time.time()
                        if current_time - game.created_time > GAME_TIMEOUT:
                            cancel_user_game(user_id)
                        else:
                            try:
                                bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                            except:
                                pass
                            clear_action_processing(user_id, action_key)
                            return

                try:
                    bot.send_message(
                        call.message.chat.id,
                        """<blockquote expandable>╔══════════════════════╗
   📝 <b>ВВОД СТАВКИ</b> 📝
╚══════════════════════╝</blockquote>

<blockquote>
Введите сумму ставки (мин. 10₽):
</blockquote>""",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logging.error(f"Ошибка отправки сообщения mine_custom_bet: {e}")
                    clear_action_processing(user_id, action_key)
                    return
                
                try:
                    bot.register_next_step_handler(call.message, process_custom_bet)
                except Exception as e:
                    logging.error(f"Ошибка register_next_step_handler: {e}")
                finally:
                    clear_action_processing(user_id, action_key)
                return

            elif call.data == "mine_custom_count":
                with mines_lock:
                    if user_id in active_games:
                        game = active_games[user_id]
                        current_time = time.time()
                        if current_time - game.created_time > GAME_TIMEOUT:
                            cancel_user_game(user_id)
                        else:
                            try:
                                bot.answer_callback_query(call.id, "❌ У вас уже есть активная игра!", show_alert=True)
                            except:
                                pass
                            clear_action_processing(user_id, action_key)
                            return

                try:
                    bot.send_message(
                        call.message.chat.id,
                        """<blockquote expandable>╔══════════════════════╗
   📝 <b>ВВОД КОЛИЧЕСТВА МИН</b> 📝
╚══════════════════════╝</blockquote>

<blockquote>
Введите количество мин (2-24):
</blockquote>""",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logging.error(f"Ошибка отправки сообщения mine_custom_count: {e}")
                    clear_action_processing(user_id, action_key)
                    return
                
                try:
                    bot.register_next_step_handler(call.message, process_custom_mines)
                except Exception as e:
                    logging.error(f"Ошибка register_next_step_handler: {e}")
                finally:
                    clear_action_processing(user_id, action_key)
                return

            with mines_lock:
                if user_id not in active_games:
                    try:
                        bot.answer_callback_query(call.id, "❌ Игра не найдена")
                    except:
                        pass
                    clear_action_processing(user_id, action_key)
                    return

                game = active_games[user_id]

            if not game.game_active:
                try:
                    bot.answer_callback_query(call.id, "❌ Игра уже завершена!")
                except:
                    pass
                clear_action_processing(user_id, action_key)
                return

            if call.data.startswith("mine_cell_"):
                parts = call.data.split("_")
                x, y = int(parts[2]), int(parts[3])

                if game.revealed[x][y]:
                    try:
                        bot.answer_callback_query(call.id, "❌ Уже открыто!")
                    except:
                        pass
                    clear_action_processing(user_id, action_key)
                    return

                with game.action_lock:
                    current_time = time.time()
                    if current_time - game.last_action_time < 0.3:
                        try:
                            bot.answer_callback_query(call.id, "⏳ Подождите немного...", show_alert=False)
                        except:
                            pass
                        clear_action_processing(user_id, action_key)
                        return
                    
                    game.last_action_time = current_time
                    
                    success = game.reveal_cell(x, y)

                    if not success:
                        users_data = load_users_data()
                        users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0), 2)
                        save_users_data(users_data)

                        try:
                            add_game_to_history(
                                user_id=int(user_id),
                                bet_amount=game.bet_amount,
                                win_amount=0.0,
                                is_win=False,
                                game_type="mines"
                            )
                        except Exception as e:
                            logging.error(f"Ошибка записи проигрыша в историю: {e}")

                        with mines_lock:
                            if user_id in active_games:
                                del active_games[user_id]

                        try:
                            bot.edit_message_text(
                                format_game_result(game, 0, False),
                                call.message.chat.id,
                                call.message.message_id,
                                parse_mode='HTML',
                                reply_markup=get_game_keyboard(game, game_over=True)
                            )
                        except Exception as e:
                            if "message is not modified" not in str(e):
                                logging.error(f"Ошибка edit_message_text mine_cell проигрыш: {e}")
                        finally:
                            clear_action_processing(user_id, action_key)
                        return
                    else:
                        try:
                            bot.edit_message_text(
                                format_game_info(game),
                                call.message.chat.id,
                                call.message.message_id,
                                parse_mode='HTML',
                                reply_markup=get_game_keyboard(game)
                            )
                        except Exception as e:
                            if "message is not modified" not in str(e):
                                logging.error(f"Ошибка edit_message_text mine_cell успех: {e}")
                        finally:
                            clear_action_processing(user_id, action_key)
                        return

            elif call.data == "mine_cashout":
                with game.action_lock:
                    current_time = time.time()
                    if current_time - game.last_action_time < 0.3:
                        try:
                            bot.answer_callback_query(call.id, "⏳ Подождите немного...", show_alert=False)
                        except:
                            pass
                        clear_action_processing(user_id, action_key)
                        return
                    
                    game.last_action_time = current_time
                    
                    if not game.game_active:
                        try:
                            bot.answer_callback_query(call.id, "❌ Игра уже завершена!")
                        except:
                            pass
                        clear_action_processing(user_id, action_key)
                        return
                    
                    game.game_active = False
                    
                    win_amount = game.bet_amount * game.multiplier
                    
                    users_data = load_users_data()
                    users_data[user_id]['balance'] = round(users_data[user_id].get('balance', 0) + win_amount, 2)
                    save_users_data(users_data)

                    try:
                        add_game_to_history(
                            user_id=int(user_id),
                            bet_amount=game.bet_amount,
                            win_amount=win_amount,
                            is_win=True,
                            game_type="mines"
                        )
                    except Exception as e:
                        logging.error(f"Ошибка записи выигрыша в историю: {e}")

                    threading.Thread(
                        target=lambda: referrals.add_referral_bonus(user_id, win_amount),
                        daemon=True
                    ).start()

                    with mines_lock:
                        if user_id in active_games:
                            del active_games[user_id]

                    try:
                        bot.edit_message_text(
                            format_game_result(game, win_amount, True),
                            call.message.chat.id,
                            call.message.message_id,
                            parse_mode='HTML',
                            reply_markup=get_game_keyboard(game, game_over=True)
                        )
                    except Exception as e:
                        if "message is not modified" not in str(e):
                            logging.error(f"Ошибка edit_message_text mine_cashout: {e}")
                    finally:
                        clear_action_processing(user_id, action_key)
                    return

            elif call.data == "mine_ignore":
                try:
                    bot.answer_callback_query(call.id)
                except:
                    pass
                finally:
                    clear_action_processing(user_id, action_key)
                return

        except Exception as e:
            if "query is too old" in str(e) or "query ID is invalid" in str(e):
                return
            elif "message is not modified" in str(e):
                pass
            else:
                logging.error(f"Ошибка в mines_callback_handler: {e}")
                try:
                    bot.answer_callback_query(call.id, "❌ Произошла ошибка!")
                except:
                    pass
            clear_action_processing(user_id, action_key if 'action_key' in locals() else "")

def mines_start(message):
    """Функция для запуска игры Мины из внешних модулей"""
    user_id = str(message.from_user.id)

    if not rate_limit_mines(user_id):
        bot.send_message(message.chat.id, "❌ Слишком быстро! Подождите 0.3 секунды.")
        return

    with mines_lock:
        if user_id in active_games:
            game = active_games[user_id]
            current_time = time.time()
            if current_time - game.created_time > GAME_TIMEOUT:
                cancel_user_game(user_id)
            else:
                bot.send_message(message.chat.id, "❌ У вас уже есть активная игра!")
                return

    users_data = load_users_data()

    if user_id not in users_data:
        users_data[user_id] = {'balance': 0}
        save_users_data(users_data)

    balance = users_data[user_id].get('balance', 0)
    balance_rounded = round(balance, 2)

    bot.send_message(
        message.chat.id,
        f"""<blockquote expandable>╔══════════════════════╗
   💣 <b>ИГРА МИНЫ</b> 💣
╚══════════════════════╝</blockquote>

<blockquote>
💎 Баланс: <b>{balance_rounded}₽</b>
</blockquote>

<i>Выберите сумму ставки:</i>""",
        parse_mode='HTML',
        reply_markup=get_bet_selection_keyboard()
    )

def cancel_game(user_id):
    """Внешняя функция для отмены игры пользователя"""
    return cancel_user_game(str(user_id))

def get_active_games():
    """Возвращает список активных игр (для админки)"""
    with mines_lock:
        return {user_id: {
            'bet_amount': game.bet_amount,
            'mines_count': game.mines_count,
            'opened_cells': game.opened_cells,
            'created_time': game.created_time,
            'last_action_time': game.last_action_time,
            'age_seconds': time.time() - game.created_time,
            'chat_id': game.chat_id,
            'message_id': game.message_id
        } for user_id, game in active_games.items()}


